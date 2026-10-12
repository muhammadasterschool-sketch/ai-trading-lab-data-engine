"""Explicit broker capability registry (multi-broker mandate, Phase M1).

NEVER assume two adapters support the same order types, symbols,
stop-loss/take-profit behavior, position mode, idempotency mechanism,
rate-limit shape or reconciliation style. Every adapter carries a
frozen :class:`BrokerCapabilities` descriptor registered in the
:class:`CapabilityRegistry`; the session consults it BEFORE any venue
call, so an unsupported request fails closed at the boundary — the
venue never sees it.

The four descriptors shipped here describe the four DETERMINISTIC MOCK
adapters in :mod:`data_engine.brokers.adapters` (Phase M1). They encode
REAL venue semantics (as documented by each venue's public API) so the
matrix is the design contract for the future real adapters:

- ``paper-mock``     — paper/simulation venue (all features, DEMO only)
- ``mt5-mock``       — MT5-compatible broker class (Exness/XM-class
                       retail semantics: hedging, attached SL/TP,
                       volume-step lots, comment-field idempotency)
- ``binance-mock``   — Binance spot REST semantics (filters, weights,
                       newClientOrderId, balances-only, separate SL/TP)
- ``bybit-mock``     — Bybit v5 spot/linear semantics (lotSizeFilter,
                       orderLinkId, attached SL/TP, one-way netting)

Registration validates internal consistency (non-empty kinds, TIFs
non-empty, SL/TP semantics consistent with the position mode,
rate-limit shape) — an incoherent descriptor cannot be registered, so
the registry itself cannot drift.
"""

from enum import Enum
from typing import Dict, Iterable, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.brokers.models import (
    AccountMode,
    OrderKind,
    PositionMode,
    Side,
    TimeInForce,
)


class SlTpSemantics(str, Enum):
    """How a venue expresses stop-loss / take-profit."""
    ATTACHED = "ATTACHED"                  # order carries SL/TP fields (MT5, Bybit v5, paper)
    SEPARATE_ORDERS = "SEPARATE_ORDERS"    # SL/TP are distinct order submissions (Binance spot)
    UNSUPPORTED = "UNSUPPORTED"            # no SL/TP mechanism at all


class IdempotencyKeyMechanism(str, Enum):
    """How the venue deduplicates a client-supplied order key."""
    NATIVE_CLIENT_ID = "NATIVE_CLIENT_ID"  # first-class field (newClientOrderId / orderLinkId)
    COMMENT_FIELD = "COMMENT_FIELD"        # rides the free-text comment (MT5 discipline)
    INTERNAL_JOURNAL = "INTERNAL_JOURNAL"  # no venue key — adapter-side journal dedupes


class ReconciliationStyle(str, Enum):
    """Authoritative reconciliation input for the venue."""
    ORDER_FILL_POLL = "ORDER_FILL_POLL"          # poll order + fill endpoints (MT5 history)
    BALANCE_SNAPSHOT = "BALANCE_SNAPSHOT"        # balances + fills cross-check (Binance spot)
    POSITION_STATEMENT = "POSITION_STATEMENT"    # position statement + fills (Bybit v5)


class ExecutionMode(str, Enum):
    """What the adapter physically does when submitting orders.

    Every adapter shipped in Phase M1 is ``MOCK_DETERMINISTIC`` — an
    in-memory simulation. ``REAL`` exists in the vocabulary for the
    future, separately-authorized adapters; the session REFUSES to
    construct against a REAL-mode descriptor until the operator
    authorization protocol exists (live trading is NOT AUTHORIZED in
    this repository).
    """
    MOCK_DETERMINISTIC = "MOCK_DETERMINISTIC"
    REAL = "REAL"


class RateLimitPolicy(BaseModel):
    """Descriptive venue throttling shape (mocks enforce it
    deterministically; real adapters map their native limits onto it)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_orders_per_window: int = 0      # 0 = uncapped (paper mock)
    max_requests_per_window: int = 0    # 0 = uncapped
    window_seconds: float = 60.0
    retry_after_seconds: Optional[float] = None

    @field_validator("max_orders_per_window", "max_requests_per_window")
    @classmethod
    def _validate_counts(cls, v: int) -> int:
        if v is None or v < 0:
            raise ValueError("rate-limit counts must be non-negative integers")
        return v

    @field_validator("window_seconds")
    @classmethod
    def _validate_window(cls, v: float) -> float:
        if v is None or v <= 0:
            raise ValueError("rate-limit window must be positive")
        return float(v)


class BrokerCapabilities(BaseModel):
    """The frozen capability descriptor of ONE adapter.

    Single source of truth for "what can this venue do" — the session's
    pre-venue checks, the capability matrix in the architecture doc and
    the tests all read from here; nothing hard-codes venue facts
    elsewhere.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    display_name: str
    execution_mode: ExecutionMode = ExecutionMode.MOCK_DETERMINISTIC
    order_kinds: Tuple[OrderKind, ...]  # REQUIRED — never assume a venue's kinds
    time_in_force: Tuple[TimeInForce, ...] = (TimeInForce.GTC,)
    sl_tp: SlTpSemantics = SlTpSemantics.UNSUPPORTED
    position_mode: PositionMode = PositionMode.NETTING
    idempotency_key: IdempotencyKeyMechanism = IdempotencyKeyMechanism.INTERNAL_JOURNAL
    supports_reduce_only: bool = False
    account_modes: Tuple[AccountMode, ...] = (AccountMode.DEMO,)
    rate_limit: RateLimitPolicy = RateLimitPolicy()
    reconciliation_style: ReconciliationStyle = ReconciliationStyle.ORDER_FILL_POLL
    provides_market_data: bool = False   # execution-only vs data-capable adapter
    venue_notes: str = ""

    @field_validator("broker_id", "display_name")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("capability identifiers must be non-empty")
        return v.strip()

    @field_validator("order_kinds", "time_in_force", "account_modes")
    @classmethod
    def _validate_non_empty_tuples(cls, v) -> tuple:
        if v is None or len(v) == 0:
            raise ValueError("capability tuples must be non-empty")
        return tuple(v)

    @model_validator(mode="after")
    def _validate_coherence(self) -> "BrokerCapabilities":
        if len(set(self.order_kinds)) != len(self.order_kinds):
            raise ValueError("order_kinds contains duplicates")
        if len(set(self.time_in_force)) != len(self.time_in_force):
            raise ValueError("time_in_force contains duplicates")
        if (
            self.position_mode is PositionMode.BALANCES_ONLY
            and self.sl_tp is SlTpSemantics.ATTACHED
        ):
            raise ValueError(
                "BALANCES_ONLY venues have no position object to attach "
                "SL/TP to — declare SEPARATE_ORDERS or UNSUPPORTED"
            )
        if (
            self.execution_mode is ExecutionMode.REAL
            and AccountMode.REAL in self.account_modes
        ):
            raise ValueError(
                "REAL execution-mode descriptors are not registrable in "
                "this phase — live trading is NOT AUTHORIZED (register "
                "the mock descriptor; real adapters require a separate, "
                "operator-authorized review)"
            )
        return self

    # -- capability queries ----------------------------------------------

    def supports_order_kind(self, order_kind: OrderKind) -> bool:
        return order_kind in self.order_kinds

    def supports_time_in_force(self, tif: TimeInForce) -> bool:
        return tif in self.time_in_force

    def supports_account_mode(self, mode: AccountMode) -> bool:
        return mode in self.account_modes

    def supports_side(self, side: Side) -> bool:
        """All shipped venues support both sides — the hook exists so
        exotic one-sided venues (issuance-only, closing-only halts)
        fail closed instead of surprising the caller."""
        return side in (Side.BUY, Side.SELL)


class CapabilityRegistryError(ValueError):
    """Raised on registry contract violations (duplicate/unknown)."""


class CapabilityRegistry:
    """Registry of the known adapter capability descriptors.

    Register-only-at-startup discipline: descriptors are immutable once
    registered, re-registration of the same broker_id with a DIFFERENT
    descriptor is refused (capability drift must be an explicit event —
    a new descriptor version — never a silent overwrite).
    """

    def __init__(self) -> None:
        self._descriptors: Dict[str, BrokerCapabilities] = {}

    def register(self, descriptor: BrokerCapabilities) -> BrokerCapabilities:
        if not isinstance(descriptor, BrokerCapabilities):
            raise CapabilityRegistryError(
                "only BrokerCapabilities descriptors are registrable"
            )
        existing = self._descriptors.get(descriptor.broker_id)
        if existing is not None:
            if existing == descriptor:
                return existing  # idempotent re-registration of the same descriptor
            raise CapabilityRegistryError(
                f"broker {descriptor.broker_id!r} is already registered with a "
                "DIFFERENT descriptor — capability drift must be an explicit "
                "versioned change, never a silent overwrite"
            )
        self._descriptors[descriptor.broker_id] = descriptor
        return descriptor

    def get(self, broker_id: str) -> BrokerCapabilities:
        descriptor = self._descriptors.get(broker_id)
        if descriptor is None:
            raise CapabilityRegistryError(
                f"broker {broker_id!r} is not registered — refusing to "
                "assume capabilities (fail closed)"
            )
        return descriptor

    def require(self, broker_id: str) -> BrokerCapabilities:
        return self.get(broker_id)

    def has(self, broker_id: str) -> bool:
        return broker_id in self._descriptors

    def broker_ids(self) -> Tuple[str, ...]:
        return tuple(sorted(self._descriptors))

    def descriptors(self) -> Tuple[BrokerCapabilities, ...]:
        return tuple(self._descriptors[b] for b in self.broker_ids())

    def __len__(self) -> int:
        return len(self._descriptors)


# ---------------------------------------------------------------------------
# Phase M1 descriptors (the four deterministic mock venues)
# ---------------------------------------------------------------------------

#: Paper/simulation venue — the reference "everything works" adapter.
PAPER_MOCK_CAPABILITIES = BrokerCapabilities(
    broker_id="paper-mock",
    display_name="Paper simulation venue (deterministic mock)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT, OrderKind.STOP, OrderKind.STOP_LIMIT),
    time_in_force=(TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK, TimeInForce.DAY),
    sl_tp=SlTpSemantics.ATTACHED,
    position_mode=PositionMode.NETTING,
    idempotency_key=IdempotencyKeyMechanism.INTERNAL_JOURNAL,
    supports_reduce_only=True,
    account_modes=(AccountMode.DEMO,),
    rate_limit=RateLimitPolicy(),  # uncapped: simulation never throttles
    reconciliation_style=ReconciliationStyle.ORDER_FILL_POLL,
    provides_market_data=False,
    venue_notes=(
        "Reference adapter proving the full neutral surface. Play-money "
        "only; the operational paper pipeline remains the frozen runtime "
        "simulator (integration is Phase M2, separately reviewed)."
    ),
)

#: MT5-compatible broker class (Exness/XM-class retail semantics).
MT5_MOCK_CAPABILITIES = BrokerCapabilities(
    broker_id="mt5-mock",
    display_name="MT5-compatible broker — Exness/XM-class semantics (deterministic mock)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT, OrderKind.STOP, OrderKind.STOP_LIMIT),
    time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    sl_tp=SlTpSemantics.ATTACHED,
    position_mode=PositionMode.HEDGING,
    idempotency_key=IdempotencyKeyMechanism.COMMENT_FIELD,
    supports_reduce_only=False,   # MT5 closes tickets; it has no native reduce-only flag
    account_modes=(AccountMode.DEMO,),
    rate_limit=RateLimitPolicy(
        max_orders_per_window=5,
        max_requests_per_window=0,
        window_seconds=60.0,
        retry_after_seconds=1.0,
    ),
    reconciliation_style=ReconciliationStyle.ORDER_FILL_POLL,
    provides_market_data=False,   # market data lives in platform/mt5.py (read-only surface)
    venue_notes=(
        "Encodes COMMON MT5 terminal semantics: hedging position tickets, "
        "attached SL/TP, volume_min/step lots, order-comment idempotency "
        "(MT5 has no native client-order-id). Exness/XM account support is "
        "verified per-account by the operator (symbol suffixes, server "
        "names, account modes) BEFORE any real adapter activation — "
        "UNVERIFIED brokers are not connectable by design."
    ),
)

#: Binance spot REST semantics.
BINANCE_MOCK_CAPABILITIES = BrokerCapabilities(
    broker_id="binance-mock",
    display_name="Binance spot — REST/filter semantics (deterministic mock)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT),
    time_in_force=(TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK),
    sl_tp=SlTpSemantics.SEPARATE_ORDERS,
    position_mode=PositionMode.BALANCES_ONLY,
    idempotency_key=IdempotencyKeyMechanism.NATIVE_CLIENT_ID,
    supports_reduce_only=False,   # spot: no reduce-only (futures-only concept)
    account_modes=(AccountMode.DEMO,),   # testnet-class; REAL refused this phase
    rate_limit=RateLimitPolicy(
        max_orders_per_window=0,
        max_requests_per_window=10,      # request-weight style cap
        window_seconds=60.0,
        retry_after_seconds=1.0,
    ),
    reconciliation_style=ReconciliationStyle.BALANCE_SNAPSHOT,
    provides_market_data=False,   # market data lives in providers/binance_public.py
    venue_notes=(
        "No plain STOP kind on spot; no attached SL/TP — stops are "
        "SEPARATE order submissions (STOP_LOSS_LIMIT / TAKE_PROFIT_LIMIT / "
        "OCO). newClientOrderId is the idempotency key. Filters: tickSize, "
        "stepSize, MIN_NOTIONAL. Representative error codes: -1013 filter "
        "failure, -2010 insufficient balance, HTTP 429/418 throttling."
    ),
)

#: Bybit v5 spot/linear semantics.
BYBIT_MOCK_CAPABILITIES = BrokerCapabilities(
    broker_id="bybit-mock",
    display_name="Bybit v5 spot/linear — order/link semantics (deterministic mock)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT),
    time_in_force=(TimeInForce.GTC, TimeInForce.IOC, TimeInForce.FOK),
    sl_tp=SlTpSemantics.ATTACHED,
    position_mode=PositionMode.NETTING,   # one-way mode (hedge mode is a per-account switch)
    idempotency_key=IdempotencyKeyMechanism.NATIVE_CLIENT_ID,
    supports_reduce_only=True,
    account_modes=(AccountMode.DEMO,),
    rate_limit=RateLimitPolicy(
        max_orders_per_window=5,
        max_requests_per_window=0,
        window_seconds=60.0,
        retry_after_seconds=1.0,
    ),
    reconciliation_style=ReconciliationStyle.POSITION_STATEMENT,
    provides_market_data=False,
    venue_notes=(
        "orderLinkId is the idempotency key. Filters: lotSizeFilter "
        "(minOrderQty/qtyStep) + minOrderAmt. Attached SL/TP supported on "
        "order placement (v5). One-way position mode default. "
        "Representative retCodes: 10004 rate-limited, 10010 order not "
        "exists, 10014 insufficient available balance."
    ),
)


def default_registry() -> CapabilityRegistry:
    """A fresh registry pre-loaded with the four Phase M1 descriptors."""
    registry = CapabilityRegistry()
    for descriptor in (
        PAPER_MOCK_CAPABILITIES,
        MT5_MOCK_CAPABILITIES,
        BINANCE_MOCK_CAPABILITIES,
        BYBIT_MOCK_CAPABILITIES,
    ):
        registry.register(descriptor)
    return registry


__all__ = [
    "SlTpSemantics",
    "IdempotencyKeyMechanism",
    "ReconciliationStyle",
    "ExecutionMode",
    "RateLimitPolicy",
    "BrokerCapabilities",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "PAPER_MOCK_CAPABILITIES",
    "MT5_MOCK_CAPABILITIES",
    "BINANCE_MOCK_CAPABILITIES",
    "BYBIT_MOCK_CAPABILITIES",
    "default_registry",
]
