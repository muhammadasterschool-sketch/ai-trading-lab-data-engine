"""v1.5.0 TOTP — RFC 6238 two-factor codes (stdlib only).

Owner mandate (2026-10-28): "email koi bhi ai-trading-lab-data-engine
par login kare to two factors verification ke baghair na ho" — no
login without 2FA. This module implements the standard TOTP algorithm
(HMAC-SHA1, 30-second step, 6 digits, +-1 step drift window) that
Google Authenticator / Microsoft Authenticator / Authy all speak, plus
the ``otpauth://`` provisioning URI for enrollment.

Deterministic and dependency-free; the wall clock is ALWAYS injected
(``at``) so tests are hermetic.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

DEFAULT_PERIOD = 30
DEFAULT_DIGITS = 6
DEFAULT_ISSUER = "AI-Trading-Lab"
#: accepted drift window (steps) — covers clock skew on phones
DRIFT_STEPS = 1


def generate_secret(num_bytes: int = 20) -> str:
    """Cryptographically random base32 secret (32 chars for 20 bytes)."""
    if num_bytes < 16:
        raise ValueError("TOTP secrets must be at least 16 bytes")
    raw = secrets.token_bytes(num_bytes)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _decode_secret(secret: str) -> bytes:
    cleaned = "".join(c for c in (secret or "").upper() if c.isalnum())
    if not cleaned:
        raise ValueError("empty TOTP secret")
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    try:
        return base64.b32decode(cleaned + padding, casefold=True)
    except Exception as exc:
        raise ValueError("invalid base32 TOTP secret") from exc


def totp_at(
    secret: str,
    at: datetime,
    *,
    period: int = DEFAULT_PERIOD,
    digits: int = DEFAULT_DIGITS,
) -> str:
    """Compute the TOTP code for an instant (aware UTC datetime)."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    counter = int(at.timestamp() // period)
    return hotp_at(secret, counter, digits=digits)


def hotp_at(secret: str, counter: int, *, digits: int = DEFAULT_DIGITS) -> str:
    """RFC 4226 HOTP (the TOTP building block)."""
    key = _decode_secret(secret)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        (struct.unpack(">I", digest[offset: offset + 4])[0] & 0x7FFFFFFF)
        % (10 ** digits)
    )
    return str(code).zfill(digits)


def verify(
    secret: str,
    code: str,
    at: datetime,
    *,
    period: int = DEFAULT_PERIOD,
    drift: int = DRIFT_STEPS,
) -> bool:
    """Constant-time verify a code within +- ``drift`` steps."""
    supplied = "".join(c for c in str(code or "") if c.isdigit())
    if len(supplied) != DEFAULT_DIGITS:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    counter = int(at.timestamp() // period)
    candidate_times = []
    for step in range(-drift, drift + 1):
        expected = hotp_at(secret, counter + step)
        candidate_times.append(expected)
    # constant-time compare across all accepted windows
    accepted = False
    for expected in candidate_times:
        if hmac.compare_digest(expected, supplied):
            accepted = True
    return accepted


def provisioning_uri(
    email: str,
    secret: str,
    *,
    issuer: str = DEFAULT_ISSUER,
    account_name: Optional[str] = None,
) -> str:
    """``otpauth://`` URI for authenticator apps (manual entry also OK)."""
    account = account_name or email
    label = urllib.parse.quote(f"{issuer}:{account}", safe=":@")
    query = urllib.parse.urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": str(DEFAULT_DIGITS),
            "period": str(DEFAULT_PERIOD),
        }
    )
    return f"otpauth://totp/{label}?{query}"


def utc_now() -> datetime:
    """Wall clock (used by production paths only; tests inject ``at``)."""
    return datetime.now(timezone.utc)


__all__ = [
    "generate_secret",
    "totp_at",
    "hotp_at",
    "verify",
    "provisioning_uri",
    "utc_now",
    "DEFAULT_ISSUER",
    "DRIFT_STEPS",
]
