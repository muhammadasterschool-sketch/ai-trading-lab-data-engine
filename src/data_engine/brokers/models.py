"""Broker-neutral execution domain models (multi-broker architecture
mandate, Phase M1).

These models are the ONE normalized vocabulary every execution venue
adapter must speak. They are deliberately SEPARATE from the frozen
Phase-11 paper models (``data_engine/paper/models.py``) and the frozen
runtime OMS models (``data_engine/runtime/oms.py``): those describe the
INTERNAL paper pipeline; these describe the VENUE BOUNDARY where
broker-specific semantics (lot steps, tick sizes, min notional, hedging
vs netting, attached vs separate stop-loss) actually differ.

Discipline (mirrors the repository's standing paper-only rules):

- NO adapter built on these models performs real execution in this
  phase — the four shipped adapters are deterministic in-memory MOCKS
  (paper/MT5-style/Binance-style/Bybit-style) with no network, no
  threads, no RNG and no wall clock (an injectable ``clock`` is
  mandatory).
- No credential material ever enters these models. Credentials live
  exclusively in :mod:`data_engine.brokers.redaction` opaque holders.
- ``UNKNOWN`` is a first-class venue order status: an ambiguous
  submission outcome is recorded, never guessed away (the session
  blocks new submissions until reconciliation resolves it — mandate
  requirement "normalized errors + reconciliation").
- Fail-closed validation everywhere: an unaligned quantity, a missing
  limit price, or an unknown symbol is a REFUSAL, never a silent
  quantize-and-continue (a silently modified order would diverge from
  the risk-approved fingerprint the runtime bound it to).

Contract version: ``BROKER_NEUTRAL_CONTRACT_VERSION`` (semver; bump on
any incompatible change to the normalized vocabulary).
"""

from datetime import datetime, UTC
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

#: Broker-neutral execution contract version.
BROKER_NEUTRAL_CONTRACT_VERSION = "1.0.0"


def _require_utc(v: datetime, name: str) -> datetime:
    if v is None or v.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return v.astimezone(UTC)


def _positive_decimal(v: Decimal, name: str) -> Decimal:
    if v is None or not isinstance(v, Decimal) or not v.is_finite() or v <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")
    return v


# ---------------------------------------------------------------------------
# Enumerations (the normalized vocabulary)
# ---------------------------------------------------------------------------

class Side(str, Enum):
    """Normalized order side."""
    BUY = "BUY"
    SELL = "SELL"


class OrderKind(str, Enum):
    """Normalized order kinds.

    Venues that lack a kind (e.g. Binance spot has no plain STOP)
    simply do not declare it in their capability descriptor — the
    session refuses the request BEFORE any venue call (fail-closed),
    and the descriptor's ``sl_tp`` semantics state the venue-native
    alternative (separate orders).
    """
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(str, Enum):
    """Normalized time-in-force."""
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    DAY = "DAY"


class VenueOrderStatus(str, Enum):
    """Normalized venue-side order status.

    ``PENDING_NEW`` — accepted by the adapter, not yet acknowledged as
    working by the venue (two-phase venues).
    ``OPEN`` — working at the venue (resting limit / stop).
    ``PARTIALLY_FILLED`` / ``FILLED`` / ``CANCELLED`` / ``REJECTED`` /
    ``EXPIRED`` — terminal or progressing states.
    ``UNKNOWN`` — AMBIGUOUS submission outcome: the venue may or may
    not have accepted the order (e.g. ack timeout after accept). This
    is a hard signal: the session must reconcile before ANY new
    submission. It is never silently upgraded to another status.
    """
    PENDING_NEW = "PENDING_NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


#: Statuses that are definitive at the venue (usable as reconciliation
#: resolutions for an UNKNOWN record).
DEFINITIVE_STATUSES = frozenset({
    VenueOrderStatus.OPEN,
    VenueOrderStatus.PARTIALLY_FILLED,
    VenueOrderStatus.FILLED,
    VenueOrderStatus.CANCELLED,
    VenueOrderStatus.REJECTED,
    VenueOrderStatus.EXPIRED,
})


class ConnectionState(str, Enum):
    """Normalized adapter connection state (fail-closed semantics).

    ``UNAVAILABLE`` — structurally cannot connect (package/platform
    absent — mirrors the MT5 read adapter's discipline).
    ``DISCONNECTED`` — not connected right now.
    ``CONNECTED`` — healthy. Submissions are only legal in this state.
    """
    UNAVAILABLE = "UNAVAILABLE"
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"


class AccountMode(str, Enum):
    """Account mode discipline (mirrors ``platform/mt5.py``).

    REAL accounts are REFUSED by every mock adapter in this phase:
    live trading is NOT AUTHORIZED in this repository. A REAL mode
    exists in the vocabulary so the future, separately-reviewed real
    adapters can express it — and so every layer can fail closed on it
    today.
    """
    DEMO = "DEMO"
    REAL = "REAL"
    UNKNOWN = "UNKNOWN"


class PositionMode(str, Enum):
    """How the venue represents open exposure."""
    NETTING = "NETTING"              # one net position per symbol
    HEDGING = "HEDGING"              # per-order position tickets
    BALANCES_ONLY = "BALANCES_ONLY"  # spot-style: no position object


# ---------------------------------------------------------------------------
# Instrument metadata (precision / lot size / minimum notional)
# ---------------------------------------------------------------------------

class InstrumentSpec(BaseModel):
    """Venue-normalized instrument metadata.

    This is the single source of truth for precision, lot size and
    minimum-notional rules — the fields venues name differently
    (Binance ``filters``, Bybit ``lotSizeFilter``/``minOrderAmt``,
    MT5 ``volume_step``/``volume_min``). Adapters translate their
    native metadata INTO this model; nothing downstream ever sees
    venue-native precision fields again.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    symbol: str                    # canonical symbol (adapter-normalized)
    broker_symbol: str             # venue-native symbol spelling
    base_asset: Optional[str] = None
    quote_asset: Optional[str] = None
    tick_size: Decimal             # price increment (> 0)
    lot_step: Decimal              # quantity increment (> 0)
    min_quantity: Decimal          # venue minimum order quantity
    max_quantity: Decimal = Decimal("0")  # 0 = uncapped
    min_notional: Decimal = Decimal("0")   # minimum order value in quote asset
    contract_size: Decimal = Decimal("1")
    reference_price: Decimal = Decimal("0")  # mock fill price (0 = no mock fills)

    @field_validator("broker_id", "symbol", "broker_symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("instrument identifiers must be non-empty")
        return v.strip()

    @field_validator("tick_size", "lot_step", "min_quantity")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        return _positive_decimal(v, "tick_size/lot_step/min_quantity")

    @field_validator("min_notional", "contract_size", "reference_price", "max_quantity")
    @classmethod
    def _validate_non_negative(cls, v: Decimal) -> Decimal:
        if v is None or not isinstance(v, Decimal) or not v.is_finite() or v < 0:
            raise ValueError("instrument limits must be non-negative finite Decimals")
        return v

    # -- normalization helpers ------------------------------------------

    def quantize_price(self, price: Decimal) -> Decimal:
        """Round one price to the venue tick (half-up). Pure helper —
        the SESSION still refuses unaligned ORDER requests; this exists
        for adapters that must quantize internally consistent values."""
        if price is None or not price.is_finite() or price <= 0:
            raise ValueError("price must be positive and finite")
        ticks = (price / self.tick_size).to_integral_value(rounding=ROUND_HALF_UP)
        return (ticks * self.tick_size).normalize()

    def quantize_quantity(self, quantity: Decimal) -> Decimal:
        """Round one quantity to the venue lot step (half-up)."""
        if quantity is None or not quantity.is_finite() or quantity <= 0:
            raise ValueError("quantity must be positive and finite")
        steps = (quantity / self.lot_step).to_integral_value(rounding=ROUND_HALF_UP)
        return (steps * self.lot_step).normalize()

    def order_problems(
        self,
        quantity: Decimal,
        price: Optional[Decimal] = None,
    ) -> Tuple[str, ...]:
        """Fail-closed order validation against venue precision rules.

        Returns the (possibly empty) tuple of human-readable problems:
        lot-step misalignment, min/max quantity, tick misalignment,
        minimum notional. NO problem is ever auto-corrected — a request
        with any problem is refused, because a silently modified order
        would diverge from the risk-approved intent.
        """
        problems: list = []
        if quantity is None or not quantity.is_finite() or quantity <= 0:
            problems.append("quantity must be positive and finite")
            return tuple(problems)
        if quantity != self.quantize_quantity(quantity):
            problems.append(
                f"quantity {quantity} is not aligned to lot step {self.lot_step}"
            )
        if quantity < self.min_quantity:
            problems.append(
                f"quantity {quantity} is below the venue minimum {self.min_quantity}"
            )
        if self.max_quantity > 0 and quantity > self.max_quantity:
            problems.append(
                f"quantity {quantity} is above the venue maximum {self.max_quantity}"
            )
        if price is not None:
            if not price.is_finite() or price <= 0:
                problems.append("price must be positive and finite")
            elif price != self.quantize_price(price):
                problems.append(
                    f"price {price} is not aligned to tick size {self.tick_size}"
                )
        if self.min_notional > 0 and price is not None:
            notional = quantity * price
            if notional < self.min_notional:
                problems.append(
                    f"notional {notional} is below the venue minimum "
                    f"{self.min_notional}"
                )
        return tuple(problems)


# ---------------------------------------------------------------------------
# Orders, acknowledgements, fills
# ---------------------------------------------------------------------------

class OrderRequest(BaseModel):
    """One broker-neutral order request.

    ``client_order_id`` is the MANDATORY idempotency key (never
    optional, never auto-generated): every venue maps it onto its own
    mechanism (Binance ``newClientOrderId``, Bybit ``orderLinkId``,
    MT5 order comment, paper internal journal) and every duplicate
    submission of the same key resolves to the SAME outcome — no
    double execution, ever.

    ``account_id`` is the MANDATORY isolation key: the request must
    name the account it trades for, and both the session and the
    adapter refuse mismatches (defense in depth).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_order_id: str
    account_id: str
    symbol: str
    side: Side
    order_kind: OrderKind
    quantity: Decimal
    price: Optional[Decimal] = None          # required for LIMIT / STOP_LIMIT
    stop_price: Optional[Decimal] = None     # required for STOP / STOP_LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC
    stop_loss: Optional[Decimal] = None      # attached SL (capability-gated)
    take_profit: Optional[Decimal] = None    # attached TP (capability-gated)
    reduce_only: bool = False

    @field_validator("client_order_id", "account_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("order identifiers must be non-empty strings")
        return v.strip()

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, v: Decimal) -> Decimal:
        return _positive_decimal(v, "quantity")

    @field_validator("price", "stop_price", "stop_loss", "take_profit")
    @classmethod
    def _validate_prices(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is None:
            return None
        return _positive_decimal(v, "order price fields")

    @model_validator(mode="after")
    def _validate_kind_presence(self) -> "OrderRequest":
        needs_price = self.order_kind in (OrderKind.LIMIT, OrderKind.STOP_LIMIT)
        needs_stop = self.order_kind in (OrderKind.STOP, OrderKind.STOP_LIMIT)
        if needs_price and self.price is None:
            raise ValueError(f"{self.order_kind.value} orders require a price")
        if not needs_price and self.price is not None:
            raise ValueError(
                f"{self.order_kind.value} orders must not carry a price"
            )
        if needs_stop and self.stop_price is None:
            raise ValueError(f"{self.order_kind.value} orders require a stop_price")
        if not needs_stop and self.stop_price is not None:
            raise ValueError(
                f"{self.order_kind.value} orders must not carry a stop_price"
            )
        return self

    def request_digest_fields(self) -> Mapping[str, str]:
        """Canonical field mapping for idempotency digests (stable
        string serialization of every governed field)."""
        return {
            "client_order_id": self.client_order_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_kind": self.order_kind.value,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price is not None else "",
            "stop_price": str(self.stop_price) if self.stop_price is not None else "",
            "time_in_force": self.time_in_force.value,
            "stop_loss": str(self.stop_loss) if self.stop_loss is not None else "",
            "take_profit": str(self.take_profit) if self.take_profit is not None else "",
            "reduce_only": str(self.reduce_only),
        }


class OrderAck(BaseModel):
    """The normalized acknowledgement of one submitted order.

    A definitive venue rejection is a NORMAL ack with status
    ``REJECTED`` (+ ``venue_code``/``reject_reason``) — the outcome is
    known and terminal. Transport-level failures (connectivity,
    timeout, rate-limit exhaustion, ambiguous outcome) raise typed
    errors instead (:mod:`data_engine.brokers.errors`) because no
    order-level verdict exists.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_order_id: str
    venue_order_id: str
    account_id: str
    broker_id: str
    symbol: str
    side: Side
    order_kind: OrderKind
    quantity: Decimal
    status: VenueOrderStatus
    submitted_at: datetime
    reject_reason: Optional[str] = None
    venue_code: Optional[str] = None

    @field_validator("client_order_id", "venue_order_id", "account_id",
                     "broker_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("ack identifiers must be non-empty strings")
        return v.strip()

    @field_validator("submitted_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "submitted_at")

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            VenueOrderStatus.FILLED, VenueOrderStatus.CANCELLED,
            VenueOrderStatus.REJECTED, VenueOrderStatus.EXPIRED,
        )


class VenueFill(BaseModel):
    """One venue execution report (possibly partial)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str
    venue_order_id: str
    client_order_id: str
    account_id: str
    broker_id: str
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")   # venue fee in quote asset (>= 0)
    filled_at: datetime

    @field_validator("fill_id", "venue_order_id", "client_order_id",
                     "account_id", "broker_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("fill identifiers must be non-empty strings")
        return v.strip()

    @field_validator("quantity", "price")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        return _positive_decimal(v, "fill quantity/price")

    @field_validator("fee")
    @classmethod
    def _validate_fee(cls, v: Decimal) -> Decimal:
        if v is None or not isinstance(v, Decimal) or not v.is_finite() or v < 0:
            raise ValueError("fill fee must be a non-negative finite Decimal")
        return v

    @field_validator("filled_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "filled_at")


# ---------------------------------------------------------------------------
# Positions, balances, account information
# ---------------------------------------------------------------------------

class PositionRecord(BaseModel):
    """One position snapshot.

    NETTING venues return one record per symbol (signed net quantity);
    HEDGING venues (MT5-class) return one record per open ticket, with
    ``ticket`` naming the venue ticket id; BALANCES_ONLY spot venues
    return no records at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    broker_id: str
    symbol: str
    quantity: Decimal          # signed net quantity (+ long / - short)
    average_entry_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    ticket: Optional[str] = None  # HEDGING venues: venue ticket id

    @field_validator("account_id", "broker_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("position identifiers must be non-empty strings")
        return v.strip()


class BalanceRecord(BaseModel):
    """One asset balance of the connected account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    broker_id: str
    asset: str
    free: Decimal
    locked: Decimal = Decimal("0")

    @field_validator("account_id", "broker_id", "asset")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("balance identifiers must be non-empty strings")
        return v.strip()

    @field_validator("free", "locked")
    @classmethod
    def _validate_amounts(cls, v: Decimal) -> Decimal:
        if v is None or not isinstance(v, Decimal) or not v.is_finite() or v < 0:
            raise ValueError("balance amounts must be non-negative finite Decimals")
        return v


class AccountInfo(BaseModel):
    """Normalized account information for the connected account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    account_id: str
    account_mode: AccountMode
    currency: str
    position_mode: PositionMode
    leverage: Optional[int] = None
    display_name: str = ""

    @field_validator("broker_id", "account_id", "currency")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("account identifiers must be non-empty strings")
        return v.strip()


# ---------------------------------------------------------------------------
# Venue reconciliation (journal ↔ venue truth)
# ---------------------------------------------------------------------------

class ExpectedOrderState(BaseModel):
    """What the session journal believes about one submitted order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_order_id: str
    status: VenueOrderStatus
    filled_quantity: Decimal = Decimal("0")

    @field_validator("client_order_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("expected-order id must be non-empty")
        return v.strip()

    @field_validator("filled_quantity")
    @classmethod
    def _validate_filled(cls, v: Decimal) -> Decimal:
        if v is None or not isinstance(v, Decimal) or not v.is_finite() or v < 0:
            raise ValueError("filled_quantity must be non-negative finite Decimal")
        return v


class ReconciliationMismatchKind(str, Enum):
    """Why a journal↔venue reconciliation failed (fail-closed list)."""
    ORDER_MISSING_AT_VENUE = "ORDER_MISSING_AT_VENUE"      # journal knows, venue does not
    PHANTOM_ORDER_AT_VENUE = "PHANTOM_ORDER_AT_VENUE"      # venue knows, journal does not
    STATUS_DIVERGENCE = "STATUS_DIVERGENCE"                # both known, statuses conflict
    FILL_QUANTITY_DIVERGENCE = "FILL_QUANTITY_DIVERGENCE"  # both known, filled qty conflicts


class ReconciliationMismatch(BaseModel):
    """One reconciliation mismatch with full evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ReconciliationMismatchKind
    client_order_id: str
    journal_status: Optional[VenueOrderStatus] = None
    venue_status: Optional[VenueOrderStatus] = None
    journal_filled_quantity: Optional[Decimal] = None
    venue_filled_quantity: Optional[Decimal] = None
    detail: str = ""

    @field_validator("client_order_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("mismatch order id must be non-empty")
        return v.strip()

    @field_validator("detail")
    @classmethod
    def _validate_detail(cls, v: str) -> str:
        return v if isinstance(v, str) else ""


class VenueReconciliationReport(BaseModel):
    """Reconciliation verdict: journal expectations vs venue truth.

    ``ok`` is True only when there are ZERO mismatches. UNKNOWN
    journal records that the venue resolves to a definitive status are
    reported in ``resolved`` (venue truth wins — it is the execution
    authority) and do NOT count as mismatches. Phantom/missing/conflicting
    records are mismatches and keep the session degraded: the operator
    investigates; nothing is papered over.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    account_id: str
    ok: bool
    checked_orders: int = 0
    mismatches: Tuple[ReconciliationMismatch, ...] = ()
    resolved: Tuple[ExpectedOrderState, ...] = ()  # venue truth for resolved UNKNOWNs

    @field_validator("broker_id", "account_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("reconciliation identifiers must be non-empty")
        return v.strip()


__all__ = [
    "BROKER_NEUTRAL_CONTRACT_VERSION",
    "Side",
    "OrderKind",
    "TimeInForce",
    "VenueOrderStatus",
    "DEFINITIVE_STATUSES",
    "ConnectionState",
    "AccountMode",
    "PositionMode",
    "InstrumentSpec",
    "OrderRequest",
    "OrderAck",
    "VenueFill",
    "PositionRecord",
    "BalanceRecord",
    "AccountInfo",
    "ExpectedOrderState",
    "ReconciliationMismatchKind",
    "ReconciliationMismatch",
    "VenueReconciliationReport",
]
