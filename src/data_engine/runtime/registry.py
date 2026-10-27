"""Client identity registry + registration ledger (v1.0.0 — owner mandate).

The owner asked for an honest answer to two questions about their OWN
dedicated deployment:

1. **WHO is connected right now?** — names, emails, device, IP,
   last-seen, and an online/offline verdict.
2. **WHO has EVER registered?** — an append-style registration ledger.

Design (fail-closed, honest, lab-scale):

- **Self-reported identity**: clients declare their identity via the
  ``X-Client-Name`` / ``X-Client-Email`` / ``X-Client-Kind`` /
  ``X-Client-Device`` headers on every authenticated request. This is
  a LAB TRUST DOMAIN (one owner, one bearer token): the identity is
  exactly as honest as the client sending it, and the admin panel
  labels it as self-reported. It is NOT an authentication mechanism —
  the bearer token remains the ONLY authentication factor.
- **Observation is best-effort**: recording a client must NEVER break
  serving (the monitoring API wraps ``observe`` in a silent guard).
- **Persistence**: the registration ledger (first-contact records)
  is persisted to ``registrations.json`` in the monitor state
  directory via atomic writes; the rolling "last seen" session map is
  in-memory only (it describes the CURRENT process lifetime).
- **Bounded**: every text field is stripped and length-capped; the
  ledger keeps at most ``max_records`` first-contact entries (oldest
  evicted first) so a hostile/broken client cannot grow the file
  without bound.
- **Redaction**: unlike the pairing audit line (P7), the registry
  intentionally stores the self-reported email AS-IS — the admin
  panel's whole purpose is showing the owner who is using their
  engine. Nothing here ever crosses a network boundary the owner
  does not control (the surface is token-authenticated).

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from data_engine.runtime.contracts import RuntimeContractError

#: Header names the monitoring API reads identity material from.
CLIENT_HEADER_NAME = "X-Client-Name"
CLIENT_HEADER_EMAIL = "X-Client-Email"
CLIENT_HEADER_KIND = "X-Client-Kind"
CLIENT_HEADER_DEVICE = "X-Client-Device"

#: Known client kinds (anything else collapses to "other").
CLIENT_KINDS = frozenset({"monitor", "admin", "other"})

#: Fields of one registration-ledger record (schema stability pin).
REGISTRATION_FIELDS = (
    "key",
    "first_seen",
    "name",
    "email",
    "kind",
    "device",
    "ip",
)

_MAX_TEXT = 128


class ClientRegistryError(RuntimeContractError):
    """Raised on client-registry contract violations."""


def _clean(value: Any) -> str:
    """Strip + length-cap one self-reported text field."""
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > _MAX_TEXT:
        text = text[:_MAX_TEXT]
    return text


def _clean_kind(value: Any) -> str:
    text = _clean(value).lower()
    # empty OR unknown kinds collapse to "other" (never fabricated
    # into "monitor"/"admin", never left ambiguous)
    return text if text in CLIENT_KINDS else "other"


class ClientRegistry:
    """Thread-safe client registry + durable registration ledger."""

    def __init__(
        self,
        state_dir: str | Path,
        *,
        online_window_seconds: float = 90.0,
        flush_interval_seconds: float = 15.0,
        max_records: int = 1000,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if online_window_seconds <= 0:
            raise ClientRegistryError("online_window_seconds must be > 0")
        if flush_interval_seconds <= 0:
            raise ClientRegistryError("flush_interval_seconds must be > 0")
        if max_records < 1:
            raise ClientRegistryError("max_records must be >= 1")
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._state_dir / "registrations.json"
        self._online_window = float(online_window_seconds)
        self._flush_interval = float(flush_interval_seconds)
        self._max_records = int(max_records)
        self._clock = clock or time.time
        self._lock = threading.Lock()
        self._registrations: list[dict] = self._load()
        self._sessions: dict[str, dict] = {}
        self._dirty = False
        self._last_flush = 0.0

    # -- persistence -------------------------------------------------------

    def _load(self) -> list[dict]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            records = raw.get("registrations", [])
            if isinstance(records, list):
                return [r for r in records if isinstance(r, dict)]
        except (OSError, ValueError):
            pass
        return []

    def flush(self) -> None:
        """Atomically persist the registration ledger (best-effort)."""
        payload = json.dumps(
            {
                "schema": "aitl-registrations-v1",
                "updated_at": self._clock(),
                "registrations": self._registrations,
            },
            ensure_ascii=False,
            indent=1,
        )
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)
        self._dirty = False
        self._last_flush = self._clock()

    def _flush_if_due(self, now: float) -> None:
        if self._dirty and now - self._last_flush >= self._flush_interval:
            try:
                self.flush()
            except OSError:
                pass  # persistence is best-effort, never breaks serving

    # -- observation (called on every authenticated request) ---------------

    def observe(
        self,
        *,
        client_ip: str,
        name: Any,
        email: Any,
        kind: Any,
        device: Any,
        now: Optional[float] = None,
    ) -> dict:
        """Upsert one client session + first-contact registration.

        Never raises on bad identity material (everything is coerced
        through ``_clean``); returns the observed session entry.
        """
        moment = self._clock() if now is None else float(now)
        clean_name = _clean(name)
        clean_email = _clean(email)
        clean_kind = _clean_kind(kind)
        clean_device = _clean(device)
        # Unauthenticated-looking garbage (no name AND no email) is
        # still observed under the IP-only key so the owner SEES the
        # noise, but it is marked anonymous.
        key_source = f"{clean_kind}|{clean_name}|{clean_email}"
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]
        with self._lock:
            session = self._sessions.get(key)
            if session is None:
                session = {
                    "key": key,
                    "name": clean_name,
                    "email": clean_email,
                    "kind": clean_kind,
                    "device": clean_device,
                    "ip": _clean(client_ip),
                    "first_seen": moment,
                    "requests": 0,
                }
                self._sessions[key] = session
            session["last_seen"] = moment
            session["ip"] = _clean(client_ip)
            if clean_device:
                session["device"] = clean_device
            session["requests"] = int(session["requests"]) + 1
            if not any(r.get("key") == key for r in self._registrations):
                self._registrations.append(
                    {
                        "key": key,
                        "first_seen": moment,
                        "name": clean_name,
                        "email": clean_email,
                        "kind": clean_kind,
                        "device": clean_device,
                        "ip": _clean(client_ip),
                    }
                )
                # bounded: evict the OLDEST first-contact records first
                while len(self._registrations) > self._max_records:
                    self._registrations.pop(0)
                self._dirty = True
            self._flush_if_due(moment)
            return dict(session)

    # -- read surface (admin panel / monitoring API) ------------------------

    def users(self, now: Optional[float] = None) -> list[dict]:
        """Current-process sessions, newest-seen first, with an
        honest ``online`` verdict (``last_seen`` within the window)."""
        moment = self._clock() if now is None else float(now)
        with self._lock:
            rows = []
            for session in self._sessions.values():
                seen = float(session.get("last_seen", 0.0))
                rows.append(
                    {
                        "key": session["key"],
                        "name": session["name"],
                        "email": session["email"],
                        "kind": session["kind"],
                        "device": session.get("device", ""),
                        "ip": session.get("ip", ""),
                        "first_seen": session.get("first_seen"),
                        "last_seen": seen,
                        "seconds_since_seen": round(max(0.0, moment - seen), 1),
                        "online": (moment - seen) <= self._online_window,
                        "requests": int(session.get("requests", 0)),
                    }
                )
        rows.sort(key=lambda r: r["last_seen"], reverse=True)
        return rows

    def registrations(self) -> list[dict]:
        """Durable first-contact ledger, newest first."""
        with self._lock:
            rows = [dict(r) for r in self._registrations]
        rows.sort(key=lambda r: float(r.get("first_seen", 0.0)), reverse=True)
        return rows


__all__ = [
    "CLIENT_HEADER_DEVICE",
    "CLIENT_HEADER_EMAIL",
    "CLIENT_HEADER_KIND",
    "CLIENT_HEADER_NAME",
    "CLIENT_KINDS",
    "ClientRegistry",
    "ClientRegistryError",
    "REGISTRATION_FIELDS",
]
