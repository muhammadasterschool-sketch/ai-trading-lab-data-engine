"""Normalized broker-error taxonomy (multi-broker mandate, Phase M1).

Every adapter raises ONE family of typed errors. Venue-native error
codes (Binance ``-1013`` filter failures, Bybit ``retCode`` 10004 rate
limits, MT5 ``TRADE_RETCODE`` 10019 no-money) are TRANSLATED into a
normalized :class:`BrokerErrorCategory` at the adapter boundary, with
the native code preserved in ``venue_code`` for audit — downstream
risk/retry logic NEVER sees venue-specific codes.

Fail-closed rules:

- Retryability is a property of the CATEGORY, not of the message:
  only CONNECTIVITY / TIMEOUT / RATE_LIMIT are retryable, and only the
  session's bounded retry policy may act on that. Every other
  category is terminal for the attempt.
- ``UNKNOWN_STATE`` is special: the venue MAY have accepted the order.
  It must be journaled as UNKNOWN and the session must reconcile
  before any new submission — never retried blindly (a retry could
  double-execute).
- Error messages are constructed REDACTED-SAFE: constructors strip
  nothing (they never receive credential material by construction —
  credentials never leave :mod:`data_engine.brokers.redaction` holders),
  and the scrub utilities exist for defense in depth when composing
  messages from caller-supplied maps.
"""

from enum import Enum
from typing import Iterable, Mapping, Optional

from data_engine.brokers.models import (
    BROKER_NEUTRAL_CONTRACT_VERSION,
    Side,
    OrderKind,
    TimeInForce,
)

#: Placeholder that replaces credential material in any scrubbed output.
REDACTED_PLACEHOLDER = "<redacted>"


class BrokerErrorCategory(str, Enum):
    """Normalized error categories (closed set)."""
    CONNECTIVITY = "CONNECTIVITY"          # transport unreachable — retryable
    TIMEOUT = "TIMEOUT"                    # request timed out — retryable
    RATE_LIMIT = "RATE_LIMIT"              # venue throttled us — retryable (bounded)
    AUTH = "AUTH"                          # credential rejected / account refused
    INVALID_ORDER = "INVALID_ORDER"        # venue rejected the order shape (definitive)
    UNSUPPORTED = "UNSUPPORTED"            # capability mismatch (definitive, pre-venue)
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"  # venue rejected: no funds (definitive)
    MARKET_CLOSED = "MARKET_CLOSED"        # venue rejected: session closed (definitive)
    GATE_REFUSED = "GATE_REFUSED"          # session-level fail-closed refusal
    UNKNOWN_STATE = "UNKNOWN_STATE"        # ambiguous outcome — reconcile first
    INTERNAL = "INTERNAL"                  # adapter invariant breach — bug signal


#: Categories the session's bounded retry policy may retry.
RETRYABLE_CATEGORIES = frozenset({
    BrokerErrorCategory.CONNECTIVITY,
    BrokerErrorCategory.TIMEOUT,
    BrokerErrorCategory.RATE_LIMIT,
})


class BrokerExecutionError(RuntimeError):
    """Base typed error for the broker-neutral execution surface.

    Attributes
    ----------
    category:
        The normalized :class:`BrokerErrorCategory`.
    broker_id:
        The adapter that raised (normalized errors always name their
        venue).
    venue_code:
        The venue-native code preserved verbatim for audit (e.g.
        ``"-1013"``, ``"10004"``, ``"10019"``) — None when the error
        originates above the venue (session gates).
    retryable:
        Derived EXCLUSIVELY from the category — never overridden by
        callers (a venue calling a limit "retryable" must not create
        a retry storm).
    """

    def __init__(
        self,
        message: str,
        *,
        category: BrokerErrorCategory,
        broker_id: str,
        venue_code: Optional[str] = None,
    ) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("broker error message must be a non-empty string")
        if not isinstance(broker_id, str) or not broker_id.strip():
            raise ValueError("broker error must name its broker_id")
        super().__init__(message)
        self.category = category
        self.broker_id = broker_id
        self.venue_code = venue_code
        self.retryable = category in RETRYABLE_CATEGORIES

    def __reduce__(self):
        # Keep typed errors picklable across process boundaries (the
        # repository's cross-process replay discipline).
        return (
            self.__class__,
            (self.args[0],),
            {
                "category": self.category,
                "broker_id": self.broker_id,
                "venue_code": self.venue_code,
            },
        )


class RateLimitError(BrokerExecutionError):
    """Venue throttling, with the venue-advertised cool-down if any."""

    def __init__(
        self,
        message: str,
        *,
        broker_id: str,
        venue_code: Optional[str] = None,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(
            message,
            category=BrokerErrorCategory.RATE_LIMIT,
            broker_id=broker_id,
            venue_code=venue_code,
        )
        self.retry_after_seconds = (
            float(retry_after_seconds)
            if retry_after_seconds is not None and retry_after_seconds > 0
            else None
        )


class UnknownOrderStateError(BrokerExecutionError):
    """AMBIGUOUS submission outcome — the venue may hold a live order.

    Raised only when the adapter cannot prove acceptance or rejection
    (e.g. ack timeout after the venue accepted). The session journals
    the order as UNKNOWN and blocks all new submissions until
    reconciliation resolves it. Never retried blindly.
    """

    def __init__(
        self,
        message: str,
        *,
        broker_id: str,
        client_order_id: str,
        venue_code: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            category=BrokerErrorCategory.UNKNOWN_STATE,
            broker_id=broker_id,
            venue_code=venue_code,
        )
        if not isinstance(client_order_id, str) or not client_order_id.strip():
            raise ValueError("UNKNOWN_STATE errors must name the client_order_id")
        self.client_order_id = client_order_id


class OrderRefusedError(BrokerExecutionError):
    """Session-level fail-closed refusal (gates, isolation, health).

    Raised BEFORE any venue call: risk gate not provided / not
    approved, kill switch active, adapter unhealthy, reconciliation
    required, account isolation mismatch, capability/precision
    mismatch. The venue never saw the order.
    """

    def __init__(self, message: str, *, broker_id: str, reason_code: str) -> None:
        super().__init__(
            message,
            category=BrokerErrorCategory.GATE_REFUSED,
            broker_id=broker_id,
            venue_code=None,
        )
        if not isinstance(reason_code, str) or not reason_code.strip():
            raise ValueError("refusals must carry a reason_code for audit")
        self.reason_code = reason_code


class UnsupportedOrderError(BrokerExecutionError):
    """The venue's capability descriptor does not cover this request.

    Constructed with a human-readable venue-native alternative so the
    caller knows what the venue WOULD accept (e.g. "Binance spot has
    no attached stop-loss: submit STOP_LOSS_LIMIT as a separate
    order"). Fail-closed: raised before any venue state changes.
    """

    def __init__(self, message: str, *, broker_id: str, alternative: str = "") -> None:
        super().__init__(
            message,
            category=BrokerErrorCategory.UNSUPPORTED,
            broker_id=broker_id,
        )
        self.alternative = alternative if isinstance(alternative, str) else ""


def capability_mismatch_reason(
    broker_id: str,
    order_kind: Optional[OrderKind] = None,
    time_in_force: Optional[TimeInForce] = None,
    side: Optional[Side] = None,
) -> str:
    """Compose the standardized UNSUPPORTED message body."""
    parts = []
    if order_kind is not None:
        parts.append(f"order kind {order_kind.value}")
    if time_in_force is not None:
        parts.append(f"time-in-force {time_in_force.value}")
    if side is not None:
        parts.append(f"side {side.value}")
    what = ", ".join(parts) if parts else "this request shape"
    return (
        f"broker {broker_id} does not support {what} "
        f"(broker-neutral contract {BROKER_NEUTRAL_CONTRACT_VERSION})"
    )


def scrub_text(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of any secret in ``text``.

    Defense in depth for composing diagnostic strings from
    caller-supplied mappings. Never raises on non-str input to
    ``text`` (returns it unchanged) — scrubbing must never crash the
    error path.
    """
    if not isinstance(text, str):
        return text
    out = text
    for secret in secrets:
        if isinstance(secret, str) and secret:
            out = out.replace(secret, REDACTED_PLACEHOLDER)
    return out


def redact_mapping(obj: Mapping, secrets: Iterable[str]) -> dict:
    """Deep-copy a mapping with every secret string value replaced.

    Used before journaling/serializing anything that might carry
    credential material (by construction it should not — this is the
    second lock on the door).
    """
    secret_list = [s for s in secrets if isinstance(s, str) and s]
    out = {}
    for key, value in obj.items():
        if isinstance(value, str):
            out[key] = scrub_text(value, secret_list)
        elif isinstance(value, Mapping):
            out[key] = redact_mapping(value, secret_list)
        else:
            out[key] = value
    return out


__all__ = [
    "REDACTED_PLACEHOLDER",
    "BrokerErrorCategory",
    "RETRYABLE_CATEGORIES",
    "BrokerExecutionError",
    "RateLimitError",
    "UnknownOrderStateError",
    "OrderRefusedError",
    "UnsupportedOrderError",
    "capability_mismatch_reason",
    "scrub_text",
    "redact_mapping",
]
