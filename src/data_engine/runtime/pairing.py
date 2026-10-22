"""Invitation-code pairing service (v4.0, PART 5 B1 — owner mandate P3/P4).

Fail-closed invitation-code verification for onboarding the monitoring
client (APK) against a cloud server OR the local Windows monitor.

Contract (fail-closed at every boundary):

- **Salted hash only**: the invitation code is stored ONLY as
  ``SHA256(salt_hex || code_utf8)`` next to a random per-config salt.
  The code VALUE is never stored, logged, echoed, or committed — only
  the salt + hash are committed config data (non-reversible).
- **Constant-time comparison**: ``hmac.compare_digest`` on the computed
  digest; no early-exit code oracle.
- **Rate limiting**: per-client-IP fixed-window limiter (default 5
  attempts/minute, configurable via ``max_attempts_per_minute``),
  independent from the monitoring API's general 60/min limit —
  brute-force friction on the onboarding secret specifically.
- **Stable reason codes**: ``E_PAIRING_DISABLED``,
  ``E_PAIRING_CODE_INVALID``, ``E_PAIRING_RATE_LIMITED`` — a wrong,
  missing, or absent code NEVER fabricates a pairing.
- **Redaction (P7)**: email is an IDENTITY field only — it is stored
  nowhere by this module and is redacted to ``***@domain`` in every
  audit line. The code and the returned token are NEVER logged.
- **Honest trust statement**: whoever holds the invitation code AND
  network access to the pairing endpoint can obtain the monitoring
  bearer token. The code is the onboarding secret; rotation (regenerate
  salt+hash, restart) remains available and documented.

Pairing is wired ONLY when the server is started with
``--pairing-config <path>`` (CLI) — absent flag = pairing DISABLED
(503 fail-closed; cloud default). A malformed or missing config at the
given path REFUSES startup, mirroring the token-file posture
(``cli.py`` ``_read_token_file``).

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

#: Stable, machine-readable pairing failure reason codes (B1).
E_PAIRING_DISABLED = "E_PAIRING_DISABLED"
E_PAIRING_CODE_INVALID = "E_PAIRING_CODE_INVALID"
E_PAIRING_RATE_LIMITED = "E_PAIRING_RATE_LIMITED"

#: Allowed pairing modes (audit/UX metadata only — this module never
#: alters transport posture; TLS-for-cloud is enforced by the APK
#: profile flag and the server's own TLS posture).
PAIRING_MODES = frozenset({"cloud", "local"})

_PAIRING_WINDOW_SECONDS = 60.0
_HEX_RE = re.compile(r"^[0-9a-f]+$")


class PairingConfigError(Exception):
    """Raised when a pairing config is missing or malformed (fail-closed)."""


def redact_email(email: Any) -> str:
    """Redact an email address to the ``***@domain`` form (P7).

    A malformed or missing value redacts to ``***`` entirely — identity
    material never crosses a boundary unredacted.
    """
    text = str(email or "").strip()
    if "@" not in text:
        return "***"
    domain = text.split("@", 1)[1]
    if not domain:
        return "***"
    return f"***@{domain}"


def load_pairing_config(path: str | Path) -> dict:
    """Load + strictly validate a pairing config JSON (fail-closed).

    Schema (version 1)::

        {
          "version": 1,
          "enabled": true,
          "salt_hex": "<32 hex chars>",
          "code_sha256_hex": "<64 hex chars>",
          "max_attempts_per_minute": 5
        }

    Unknown keys are ignored (forward compatibility); known keys are
    validated strictly. Missing file or ANY malformed value raises
    :class:`PairingConfigError` — the caller (CLI serve) refuses to
    start, mirroring the monitor-token-file posture.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise PairingConfigError(f"pairing config not found: {config_path}")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PairingConfigError(
            f"pairing config unreadable/invalid JSON at {config_path}: "
            f"{type(exc).__name__}"
        ) from exc
    if not isinstance(raw, dict):
        raise PairingConfigError(
            f"pairing config must be a JSON object at {config_path}"
        )
    if raw.get("version") != 1:
        raise PairingConfigError(
            f"pairing config version must be exactly 1 (got {raw.get('version')!r})"
        )
    enabled = raw.get("enabled")
    if not isinstance(enabled, bool):
        raise PairingConfigError("'enabled' must be a boolean")
    salt_hex = raw.get("salt_hex")
    if not (
        isinstance(salt_hex, str)
        and len(salt_hex) == 32
        and _HEX_RE.fullmatch(salt_hex)
    ):
        raise PairingConfigError(
            "'salt_hex' must be exactly 32 lowercase hex characters"
        )
    code_hash = raw.get("code_sha256_hex")
    if not (
        isinstance(code_hash, str)
        and len(code_hash) == 64
        and _HEX_RE.fullmatch(code_hash)
    ):
        raise PairingConfigError(
            "'code_sha256_hex' must be exactly 64 lowercase hex characters"
        )
    cap = raw.get("max_attempts_per_minute", 5)
    if not isinstance(cap, int) or isinstance(cap, bool) or not 1 <= cap <= 1000:
        raise PairingConfigError(
            "'max_attempts_per_minute' must be an integer in [1, 1000]"
        )
    return {
        "version": 1,
        "enabled": enabled,
        "salt_hex": salt_hex,
        "code_sha256_hex": code_hash,
        "max_attempts_per_minute": cap,
        "source_path": str(config_path),
    }


def hash_invitation_code(salt_hex: str, code: str) -> str:
    """Compute the salted SHA-256 digest of an invitation code.

    Deterministic: ``SHA256(salt_hex || code_utf8)``. Used both at
    config-generation time (installers) and at verification time.
    """
    return hashlib.sha256((salt_hex + code).encode("utf-8")).hexdigest()


def verify_invitation_code(config: dict, supplied: Any) -> bool:
    """Constant-time verification of a supplied code against the config.

    Returns ``False`` for ANY wrong, missing, or malformed input —
    never raises, never leaks which check failed.
    """
    supplied_text = supplied if isinstance(supplied, str) else ""
    if not supplied_text:
        return False
    digest = hash_invitation_code(config["salt_hex"], supplied_text)
    return hmac.compare_digest(digest, config["code_sha256_hex"])


class PairingRateLimiter:
    """Fixed-window per-client-IP pairing attempt limiter.

    Thread-safe, in-memory, injectable clock — same pattern as the
    monitoring API's general limiter, kept separate so pairing
    attempts cannot exhaust (nor be exhausted by) the general budget.
    """

    def __init__(self, max_attempts: int, window_seconds: float = _PAIRING_WINDOW_SECONDS) -> None:
        if max_attempts < 1:
            raise PairingConfigError("max_attempts must be >= 1")
        if window_seconds <= 0:
            raise PairingConfigError("window_seconds must be positive")
        self._max = int(max_attempts)
        self._window = float(window_seconds)
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[float, int]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            window_start, count = self._counts.get(key, (moment, 0))
            if moment - window_start >= self._window:
                window_start, count = moment, 0
            count += 1
            self._counts[key] = (window_start, count)
            return count <= self._max

    def retry_after_seconds(self, key: str, now: Optional[float] = None) -> int:
        """Seconds until the rate-limit window for ``key`` resets (>= 1)."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            window_start, _ = self._counts.get(key, (moment, 0))
            return max(1, int(self._window - (moment - window_start)) + 1)


def format_pairing_status(config: dict) -> str:
    """Human-readable one-shot status for the CLI (B4) — NEVER the code."""
    return (
        "invitation pairing: "
        + ("ENABLED" if config["enabled"] else "DISABLED")
        + f"\n  config: {config.get('source_path', '<unknown>')}"
        + f"\n  max attempts/min/IP: {config['max_attempts_per_minute']}"
        + "\n  live attempt counters live in the serving process console"
        + "\n  the invitation code itself is never displayed"
    )


class PairingService:
    """Server-side pairing gate wired into the monitoring API (B1).

    The service verifies invitation codes against a loaded config,
    rate-limits attempts per client IP, and composes the endpoint
    response. It never logs the code or the token; the audit line
    carries IP, mode, outcome, and the REDACTED email only.
    """

    def __init__(
        self,
        config: dict,
        *,
        rate_limiter: Optional[PairingRateLimiter] = None,
        clock: Optional[Callable[[], float]] = None,
        audit_sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._config = config
        self._limiter = rate_limiter or PairingRateLimiter(
            config["max_attempts_per_minute"]
        )
        self._clock = clock or time.monotonic
        self._audit_sink = audit_sink or (lambda line: print(line, flush=True))

    @property
    def config(self) -> dict:
        return self._config

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled"))

    def _audit(self, line: str) -> None:
        try:
            self._audit_sink(line)
        except Exception:  # noqa: BLE001 — auditing must never break pairing
            pass

    def attempt(
        self,
        *,
        client_ip: str,
        payload: dict,
        token: str,
        health_provider: Callable[[], dict],
    ) -> tuple[int, dict]:
        """Process one pairing attempt; return ``(http_status, payload)``.

        Order (fail-closed): rate limit → request validation → code
        verification → success. A disabled config answers 503 with
        ``E_PAIRING_DISABLED`` (never fabricated success).
        """
        now = self._clock()

        if not self.enabled:
            self._audit(
                f"[pairing] attempt from {client_ip} -> {E_PAIRING_DISABLED}"
            )
            return 503, {"error": E_PAIRING_DISABLED}

        if not self._limiter.allow(client_ip, now):
            retry_after = self._limiter.retry_after_seconds(client_ip, now)
            self._audit(
                f"[pairing] attempt from {client_ip} -> {E_PAIRING_RATE_LIMITED}"
            )
            return 429, {
                "error": E_PAIRING_RATE_LIMITED,
                "retry_after_seconds": retry_after,
            }

        name = payload.get("name")
        email = payload.get("email")
        mode = payload.get("mode")
        code = payload.get("invitation_code")

        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(code, str)
            or not code.strip()
            or mode not in PAIRING_MODES
            or (email is not None and not isinstance(email, str))
        ):
            self._audit(
                f"[pairing] attempt from {client_ip} -> invalid_request"
            )
            return 400, {"error": "invalid_request"}

        if not verify_invitation_code(self._config, code):
            self._audit(
                f"[pairing] attempt from {client_ip} mode={mode} "
                f"name={name.strip()[:64]} email={redact_email(email)} "
                f"-> {E_PAIRING_CODE_INVALID}"
            )
            return 403, {"error": E_PAIRING_CODE_INVALID}

        # Success: hand over the monitoring bearer token (the same
        # token the API authenticates with) + an honest health snapshot.
        # The code and the token are NEVER logged (Rule 3 / P7).
        try:
            health = health_provider()
        except Exception:  # noqa: BLE001 — honest, never fabricated
            health = {"engine_state": "ERROR", "detail": "health unavailable"}
        self._audit(
            f"[pairing] attempt from {client_ip} mode={mode} "
            f"name={name.strip()[:64]} email={redact_email(email)} -> OK"
        )
        return 200, {
            "status": "paired",
            "token": token,
            "health": health,
            "pairing": {
                "email_redacted": redact_email(email),
                "mode": mode,
            },
        }


__all__ = [
    "E_PAIRING_DISABLED",
    "E_PAIRING_CODE_INVALID",
    "E_PAIRING_RATE_LIMITED",
    "PAIRING_MODES",
    "PairingConfigError",
    "PairingRateLimiter",
    "PairingService",
    "format_pairing_status",
    "hash_invitation_code",
    "load_pairing_config",
    "redact_email",
    "verify_invitation_code",
]
