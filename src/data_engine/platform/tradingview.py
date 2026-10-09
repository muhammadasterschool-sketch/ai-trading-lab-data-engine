"""TradingView signal ingestion contract (platform mandate Phase G).

Validates inbound TradingView alert/webhook payloads into advisory
signals and nothing more: a TradingView alert is a SIGNAL, never proof
of an order or fill. Validated signals are typed records that must pass
the standard instrument validation, risk gate and OMS path — this
module has no execution surface at all.

Security (fail-closed):
- Authentication via a caller-supplied shared-secret VERIFIER (the raw
  secret is never stored here, never logged; digests compared with
  ``hmac.compare_digest``).
- Replay protection: payload timestamps older than ``max_age`` are
  refused as stale.
- Duplicate delivery: nonce dedup — the same nonce is refused on retry.
- Payload schema validation is strict (unknown fields rejected by the
  pydantic model config).
- External content is untrusted data: it is validated and classified,
  never executed or interpreted as instructions.

Deployment of an actual HTTP endpoint is BLOCKED on infrastructure and
is honestly NOT claimed here; the validator + router contract is tested
with a mocked transport.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field


class TVEventCategory(str, Enum):
    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT = "exit"
    ALERT = "alert"
    OTHER = "other"


class TVRefusalReason(str, Enum):
    INVALID_SCHEMA = "invalid_schema"
    AUTH_FAILED = "auth_failed"
    STALE_TIMESTAMP = "stale_timestamp"
    DUPLICATE_NONCE = "duplicate_nonce"
    UNKNOWN_INSTRUMENT = "unknown_instrument"
    ROUTER_REJECTED = "router_rejected"


class TVSignalPayload(BaseModel):
    """Strict inbound payload schema (extra fields forbidden)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str = Field(..., min_length=1)
    instrument: str = Field(..., min_length=1)
    event_type: TVEventCategory
    event_timestamp: datetime
    timeframe: str
    signal: dict[str, Any] = Field(default_factory=dict)
    nonce: str = Field(..., min_length=1)
    auth_digest: str = Field(..., min_length=8)


class TVSignalRefusal(BaseModel):
    """Fail-closed refusal with explicit reason."""

    model_config = ConfigDict(frozen=True)

    reason: TVRefusalReason
    detail: str = ""


class ValidatedTVSignal(BaseModel):
    """Advisory signal — NO order authority anywhere in this record."""

    model_config = ConfigDict(frozen=True)

    payload: TVSignalPayload
    received_at: datetime
    advisory_only: bool = True

    def to_advisory_intent(self, internal_instrument_id: str) -> "TVAdvisoryIntent":
        """Typed intent for downstream routing through the standard
        decision -> risk -> OMS path (never direct execution)."""
        return TVAdvisoryIntent(
            internal_instrument_id=internal_instrument_id,
            strategy_id=self.payload.strategy_id,
            event_type=self.payload.event_type,
            event_timestamp=self.payload.event_timestamp,
            timeframe=self.payload.timeframe,
            signal=dict(self.payload.signal),
        )


class TVAdvisoryIntent(BaseModel):
    """Routing record handed to the decision layer (advisory only)."""

    model_config = ConfigDict(frozen=True)

    internal_instrument_id: str
    strategy_id: str
    event_type: TVEventCategory
    event_timestamp: datetime
    timeframe: str
    signal: dict[str, Any]


def expected_digest(secret: str, payload: TVSignalPayload) -> str:
    """HMAC-SHA256 over the canonical payload fields (hex, first 32 chars).

    Covers EVERY semantically meaningful field INCLUDING the signal body
    (canonical JSON) — mutating any payload content after signing must
    break the digest. ``auth_digest`` itself is excluded (it IS the
    signature)."""
    canonical = "|".join(
        (
            payload.strategy_id,
            payload.instrument,
            payload.event_type.value,
            payload.event_timestamp.isoformat(),
            payload.timeframe,
            json.dumps(payload.signal, sort_keys=True, separators=(",", ":")),
            payload.nonce,
        )
    )
    return hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


class TVSignalValidator:
    """Validates raw webhook payloads fail-closed."""

    def __init__(
        self,
        secret_provider: Callable[[], str],
        max_age: timedelta = timedelta(minutes=5),
        seen_nonce_capacity: int = 4096,
        instrument_resolver: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self._secret_provider = secret_provider
        self._max_age = max_age
        self._resolver = instrument_resolver
        self._seen_nonces: list[str] = []
        self._capacity = seen_nonce_capacity

    def validate(self, raw: dict[str, Any], received_at: datetime):
        """Returns (ValidatedTVSignal, None) or (None, TVSignalRefusal)."""
        try:
            payload = TVSignalPayload(**raw)
        except Exception as exc:  # noqa: BLE001 — any schema failure is a refusal
            return None, TVSignalRefusal(
                reason=TVRefusalReason.INVALID_SCHEMA, detail=str(exc)[:200]
            )

        secret = self._secret_provider()
        expected = expected_digest(secret, payload)
        if not hmac.compare_digest(expected, payload.auth_digest):
            return None, TVSignalRefusal(
                reason=TVRefusalReason.AUTH_FAILED,
                detail="auth digest mismatch (constant-time compare)",
            )

        age = received_at - payload.event_timestamp
        if age > self._max_age or age < -self._max_age:
            return None, TVSignalRefusal(
                reason=TVRefusalReason.STALE_TIMESTAMP,
                detail=f"event age {age} outside replay window ±{self._max_age}",
            )

        if payload.nonce in self._seen_nonces:
            return None, TVSignalRefusal(
                reason=TVRefusalReason.DUPLICATE_NONCE,
                detail="nonce already delivered — duplicate refused",
            )
        self._seen_nonces.append(payload.nonce)
        if len(self._seen_nonces) > self._capacity:
            self._seen_nonces = self._seen_nonces[-self._capacity:]

        return ValidatedTVSignal(payload=payload, received_at=received_at), None

    def route(self, raw: dict[str, Any], received_at: datetime):
        """Validate + resolve instrument + produce advisory intent.

        Returns (TVAdvisoryIntent, None) or (None, TVSignalRefusal).
        Unknown instruments fail closed — a chart symbol is not proof of
        a registered instrument.
        """
        signal, refusal = self.validate(raw, received_at)
        if refusal is not None:
            return None, refusal
        assert signal is not None
        if self._resolver is None:
            return None, TVSignalRefusal(
                reason=TVRefusalReason.ROUTER_REJECTED,
                detail="no instrument resolver configured — fail closed",
            )
        internal_id = self._resolver(signal.payload.instrument)
        if internal_id is None:
            return None, TVSignalRefusal(
                reason=TVRefusalReason.UNKNOWN_INSTRUMENT,
                detail=(
                    f"instrument {signal.payload.instrument!r} is not a verified "
                    "registered instrument — TradingView visibility is not "
                    "registration proof"
                ),
            )
        return signal.to_advisory_intent(internal_id), None
