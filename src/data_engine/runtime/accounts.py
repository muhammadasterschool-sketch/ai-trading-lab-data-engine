"""v1.5.0 accounts + mandatory two-factor login.

Owner mandate (2026-10-28): the monitor app carries an ADMIN user who
sees the normal trading system PLUS a Users screen (all other users),
and "email koi bhi ai-trading-lab-data-engine par login kare to two
factors verification ke baghair na ho" — NO login without TOTP 2FA.

Design (fail-closed, no magic):

- ``AccountStore`` — durable JSON account book under the monitor state
  dir (atomic writes, same posture as registrations.json). Passwords
  are PBKDF2-HMAC-SHA256 (200k iterations, per-account salt); TOTP
  secrets are base32; NOTHING is ever logged or returned raw except
  during the explicit enrollment handshake (which itself requires the
  password first).
- ``SessionManager`` — in-memory bearer sessions (12h TTL) issued ONLY
  after password + TOTP both verify. Pairing-token auth (the owner's
  monitor-token.txt) remains a separate, coexisting factor.
- ``AccountService`` — the login state machine: bad-credential vs
  locked vs enrollment-required vs bad-TOTP, with per-account lockout
  (5 consecutive failures -> 15 minutes) and an inspectable login
  history per account.
- Admin operations (create user / reset 2FA / lock) require the admin
  role (or the owner pairing token at the HTTP layer).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from data_engine.runtime import totp as totp_mod

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_ROLES = ("admin", "trader")
_PBKDF2_ITERATIONS = 200_000
_MAX_LOGIN_HISTORY = 50
_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15
_SESSION_TTL_SECONDS = 12 * 3600
_MIN_PASSWORD_CHARS = 10


class AccountError(RuntimeError):
    """Raised on account-contract violations (fail closed)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        salt.hex(),
        digest.hex(),
    )


def _verify_password(stored: str, password: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, AttributeError):
        return False
    return secrets.compare_digest(actual, expected)


class AccountStore:
    """Durable account book (atomic JSON, per-store lock)."""

    def __init__(self, state_dir) -> None:
        from pathlib import Path

        self._path = Path(state_dir) / "accounts.json"
        self._lock = threading.Lock()

    # -- persistence ------------------------------------------------------

    def _read(self) -> Dict[str, Any]:
        try:
            payload = json.loads(
                self._path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return {"version": 1, "accounts": {}}
        if not isinstance(payload, dict) or not isinstance(
            payload.get("accounts"), dict
        ):
            return {"version": 1, "accounts": {}}
        return payload

    def _write(self, payload: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8"
        )
        os.replace(tmp, self._path)

    def _mutate(self, fn) -> Any:
        with self._lock:
            payload = self._read()
            result = fn(payload)
            self._write(payload)
            return result

    # -- account lifecycle --------------------------------------------------

    def create_account(
        self,
        email: str,
        name: str,
        password: str,
        role: str,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        email = (email or "").strip().lower()
        moment = now or _utc_now()

        def _create(payload: Dict[str, Any]) -> Any:
            if not _EMAIL_RE.match(email):
                raise AccountError("invalid email address")
            if email in payload["accounts"]:
                raise AccountError("an account with this email exists")
            if not name or len(name) > 80:
                raise AccountError("name required (max 80 chars)")
            if role not in _ROLES:
                raise AccountError(f"role must be one of {list(_ROLES)}")
            if len(password or "") < _MIN_PASSWORD_CHARS:
                raise AccountError(
                    f"password must be at least {_MIN_PASSWORD_CHARS} "
                    "characters"
                )
            payload["accounts"][email] = {
                "email": email,
                "name": name,
                "role": role,
                "password_pbkdf2": _hash_password(password),
                "totp_secret": None,
                "totp_enrolled": False,
                "created_at": moment.isoformat(),
                "last_login_at": None,
                "failed_attempts": 0,
                "locked_until": None,
                "login_history": [],
            }
            return self._sanitize(payload["accounts"][email])

        return self._mutate(_create)

    def get(self, email: str) -> Optional[Dict[str, Any]]:
        email = (email or "").strip().lower()
        payload = self._read()
        record = payload["accounts"].get(email)
        return dict(record) if record else None

    def _sanitize(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "email": record.get("email"),
            "name": record.get("name"),
            "role": record.get("role"),
            "totp_enrolled": bool(record.get("totp_enrolled")),
            "created_at": record.get("created_at"),
            "last_login_at": record.get("last_login_at"),
            "locked": bool(record.get("locked_until")),
            "failed_attempts": int(record.get("failed_attempts", 0)),
        }

    def list_accounts(self) -> List[Dict[str, Any]]:
        payload = self._read()
        return [
            self._sanitize(record)
            for _, record in sorted(payload["accounts"].items())
        ]

    def login_history(self, email: str) -> List[Dict[str, Any]]:
        record = self.get(email)
        if not record:
            raise AccountError("unknown account")
        history = record.get("login_history") or []
        return [
            dict(entry)
            for entry in history[-_MAX_LOGIN_HISTORY:]
        ]

    # -- 2FA lifecycle ------------------------------------------------------

    def set_totp_pending(
        self, email: str, secret: str, *, now: Optional[datetime] = None
    ) -> None:
        def _set(payload: Dict[str, Any]) -> None:
            record = payload["accounts"].get(email)
            if not record:
                raise AccountError("unknown account")
            if record.get("totp_enrolled"):
                raise AccountError("account already enrolled")
            # pending secret is sticky: the SAME secret is returned on
            # each enrollment attempt until a valid code confirms it
            if not record.get("totp_secret"):
                record["totp_secret"] = secret

        self._mutate(_set)

    def pending_totp_secret(self, email: str) -> Optional[str]:
        record = self.get(email)
        if not record or record.get("totp_enrolled"):
            return None
        return record.get("totp_secret")

    def confirm_totp_enrollment(self, email: str) -> None:
        def _confirm(payload: Dict[str, Any]) -> None:
            record = payload["accounts"].get(email)
            if not record or not record.get("totp_secret"):
                raise AccountError("no pending enrollment for account")
            record["totp_enrolled"] = True
            record["failed_attempts"] = 0
            record["locked_until"] = None

        self._mutate(_confirm)

    def reset_totp(self, email: str) -> None:
        def _reset(payload: Dict[str, Any]) -> None:
            record = payload["accounts"].get(email)
            if not record:
                raise AccountError("unknown account")
            record["totp_secret"] = None
            record["totp_enrolled"] = False

        self._mutate(_reset)

    def enrolled_totp_secret(self, email: str) -> Optional[str]:
        record = self.get(email)
        if not record or not record.get("totp_enrolled"):
            return None
        return record.get("totp_secret")

    # -- lockout / history ---------------------------------------------------

    def is_locked(
        self, email: str, *, now: Optional[datetime] = None
    ) -> bool:
        record = self.get(email)
        if not record:
            return False
        until = record.get("locked_until")
        if not until:
            return False
        try:
            until_dt = datetime.fromisoformat(str(until))
        except ValueError:
            return False
        if until_dt.tzinfo is None:
            until_dt = until_dt.replace(tzinfo=timezone.utc)
        return (now or _utc_now()) < until_dt

    def record_login(
        self,
        email: str,
        *,
        ok: bool,
        ip: str,
        reason: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utc_now()

        def _record(payload: Dict[str, Any]) -> None:
            record = payload["accounts"].get(email)
            if not record:
                return
            history = record.setdefault("login_history", [])
            history.append(
                {
                    "ts": moment.isoformat(),
                    "ip": str(ip)[:64],
                    "ok": bool(ok),
                    "reason": str(reason)[:64],
                }
            )
            del history[:-_MAX_LOGIN_HISTORY]
            if ok:
                record["failed_attempts"] = 0
                record["locked_until"] = None
                record["last_login_at"] = moment.isoformat()
            else:
                attempts = int(record.get("failed_attempts", 0)) + 1
                record["failed_attempts"] = attempts
                if attempts >= _LOCKOUT_ATTEMPTS:
                    record["locked_until"] = (
                        moment + timedelta(minutes=_LOCKOUT_MINUTES)
                    ).isoformat()

        self._mutate(_record)

    def set_locked(
        self, email: str, locked: bool, *, now: Optional[datetime] = None
    ) -> None:
        moment = now or _utc_now()

        def _set(payload: Dict[str, Any]) -> None:
            record = payload["accounts"].get(email)
            if not record:
                raise AccountError("unknown account")
            if locked:
                record["locked_until"] = (
                    moment + timedelta(minutes=_LOCKOUT_MINUTES)
                ).isoformat()
            else:
                record["locked_until"] = None
                record["failed_attempts"] = 0

        self._mutate(_set)


class SessionManager:
    """In-memory bearer sessions (12h TTL, revocable)."""

    def __init__(self, ttl_seconds: int = _SESSION_TTL_SECONDS) -> None:
        self._ttl = int(ttl_seconds)
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def issue(
        self,
        email: str,
        role: str,
        *,
        now: Optional[datetime] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        moment = now or _utc_now()
        token = token or secrets.token_urlsafe(32)
        expires = moment + timedelta(seconds=self._ttl)
        with self._lock:
            self._sessions[token] = {
                "email": email,
                "role": role,
                "issued_at": moment.isoformat(),
                "expires_at": expires,
            }
        return {"token": token, "expires_at": expires.isoformat()}

    def validate(
        self, token: str, *, now: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        moment = now or _utc_now()
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            expires = session["expires_at"]
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if moment >= expires:
                del self._sessions[token]
                return None
            return {
                "email": session["email"],
                "role": session["role"],
                "expires_at": session["expires_at"].isoformat(),
            }

    def revoke(self, token: str) -> bool:
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def revoke_all_for(self, email: str) -> int:
        with self._lock:
            doomed = [
                t for t, s in self._sessions.items()
                if s["email"] == email
            ]
            for t in doomed:
                del self._sessions[t]
            return len(doomed)


class AccountService:
    """Login state machine + admin operations (2FA ALWAYS required)."""

    def __init__(self, state_dir) -> None:
        self.store = AccountStore(state_dir)
        self.sessions = SessionManager()

    # -- login ----------------------------------------------------------------

    def login(
        self,
        email: str,
        password: str,
        totp_code: str,
        *,
        ip: str = "unknown",
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Password + TOTP login. Returns an inspectable outcome dict.

        Outcomes: ``SESSION`` (token issued), ``E_BAD_CREDENTIALS``,
        ``E_ACCOUNT_LOCKED``, ``E_TOTP_ENROLLMENT_REQUIRED`` (carries
        the enrollment secret + otpauth URI — the password has already
        verified at that point), ``E_TOTP_INVALID``.
        """
        email = (email or "").strip().lower()
        moment = now or _utc_now()
        record = self.store.get(email)
        if not record or not _verify_password(
            str(record.get("password_pbkdf2", "")), str(password or "")
        ):
            if record:
                self.store.record_login(
                    email, ok=False, ip=ip,
                    reason="bad-credentials", now=moment,
                )
            return {"outcome": "E_BAD_CREDENTIALS"}
        if self.store.is_locked(email, now=moment):
            self.store.record_login(
                email, ok=False, ip=ip, reason="locked", now=moment
            )
            return {
                "outcome": "E_ACCOUNT_LOCKED",
                "locked_until": record.get("locked_until"),
            }

        if not record.get("totp_enrolled"):
            # enrollment handshake: password verified -> hand out the
            # (sticky) pending secret; a valid code confirms enrollment
            pending = self.store.pending_totp_secret(email)
            if not pending:
                pending = totp_mod.generate_secret()
                self.store.set_totp_pending(email, pending, now=moment)
            if totp_mod.verify(pending, str(totp_code or ""), moment):
                self.store.confirm_totp_enrollment(email)
            else:
                # brute-force posture: wrong codes during enrollment
                # also count toward the account lockout
                self.store.record_login(
                    email, ok=False, ip=ip, reason="enroll-bad-totp",
                    now=moment,
                )
                return {
                    "outcome": "E_TOTP_ENROLLMENT_REQUIRED",
                    "totp_secret": pending,
                    "otpauth_uri": totp_mod.provisioning_uri(
                        email, pending
                    ),
                }
        else:
            secret = str(record.get("totp_secret") or "")
            if not totp_mod.verify(secret, str(totp_code or ""), moment):
                self.store.record_login(
                    email, ok=False, ip=ip, reason="bad-totp", now=moment
                )
                return {"outcome": "E_TOTP_INVALID"}

        session = self.sessions.issue(
            email, str(record.get("role", "trader")), now=moment
        )
        self.store.record_login(
            email, ok=True, ip=ip, reason="password+totp", now=moment
        )
        return {
            "outcome": "SESSION",
            "token": session["token"],
            "expires_at": session["expires_at"],
            "user": {
                "email": email,
                "name": record.get("name"),
                "role": record.get("role"),
            },
        }

    # -- admin operations -------------------------------------------------------

    def create_user(
        self,
        *,
        actor_role: str,
        email: str,
        name: str,
        password: str,
        role: str,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if actor_role != "admin":
            raise AccountError("admin role required (fail closed)")
        return self.store.create_account(
            email, name, password, role, now=now
        )

    def reset_2fa(self, *, actor_role: str, email: str) -> Dict[str, Any]:
        if actor_role != "admin":
            raise AccountError("admin role required (fail closed)")
        email = (email or "").strip().lower()
        self.store.reset_totp(email)
        self.sessions.revoke_all_for(email)
        return {
            "email": email,
            "totp_enrolled": False,
            "note": (
                "2FA reset; the user re-enrolls on next login "
                "(password + new authenticator code)"
            ),
        }

    def set_lock(
        self,
        *,
        actor_role: str,
        email: str,
        locked: bool,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if actor_role != "admin":
            raise AccountError("admin role required (fail closed)")
        email = (email or "").strip().lower()
        self.store.set_locked(email, locked, now=now)
        if locked:
            self.sessions.revoke_all_for(email)
        return {"email": email, "locked": bool(locked)}

    def accounts(self, *, actor_role: str) -> Dict[str, Any]:
        if actor_role != "admin":
            raise AccountError("admin role required (fail closed)")
        rows = []
        for account in self.store.list_accounts():
            row = dict(account)
            row["login_history"] = self.store.login_history(
                str(account["email"])
            )[-10:]
            rows.append(row)
        return {"accounts": rows, "count": len(rows)}


__all__ = [
    "AccountError",
    "AccountStore",
    "AccountService",
    "SessionManager",
]
