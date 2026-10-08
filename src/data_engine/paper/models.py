"""Phase 11 — Paper trading models (blueprint 5.51).

NO REAL MONEY. NO BROKER CREDENTIALS. By construction:

- ``PaperOrder``: market or limit order with a client order id
  (duplicate protection key). There is no broker, no account, and no
  credential field anywhere in this model.
- ``Fill``: simulated execution record with explicit realism fields
  (commission, slippage, spread cost) — every cost is recorded, not
  hidden.
- ``PaperPosition``: average-cost position state.

Identity: orders ``paper11.`` (69 chars), fills ``fill11.`` (69).
"""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 11 contract version.
PHASE_11_CONTRACT_VERSION = "1.0.0"


def _require_utc(v: datetime, name: str) -> datetime:
    if v is None or v.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return v.astimezone(UTC)


def _positive(v: Decimal) -> Decimal:
    if v is None or not v.is_finite() or v <= 0:
        raise ValueError("quantity must be a positive finite Decimal")
    return v


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(str, Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class PaperOrder(BaseModel):
    """One paper order — no broker, no credentials, no real money."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    submitted_at: datetime

    @field_validator("client_order_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("order identifiers must be non-empty strings")
        return v.strip().upper()

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, v: Decimal) -> Decimal:
        return _positive(v)

    @field_validator("limit_price")
    @classmethod
    def _validate_limit(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None:
            if not v.is_finite() or v <= 0:
                raise ValueError("limit price must be positive")
        return v

    @field_validator("submitted_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "submitted_at")

    @model_validator(mode="after")
    def _validate_limit_presence(self) -> "PaperOrder":
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require a limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("market orders must not carry a limit_price")
        return self

    @property
    def order_hash(self) -> str:
        return "paper11." + deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "client_order_id": self.client_order_id,
                "symbol": self.symbol,
                "side": self.side.value,
                "order_type": self.order_type.value,
                "quantity": str(self.quantity),
                "limit_price": str(self.limit_price) if self.limit_price else None,
                "submitted_at": self.submitted_at,
            }
        )


class Fill(BaseModel):
    """One simulated fill with full cost transparency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str
    client_order_id: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    slippage_cost: Decimal
    spread_cost: Decimal
    filled_at: datetime

    @field_validator("fill_id", "client_order_id", "symbol")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("fill identifiers must be non-empty strings")
        return v.strip().upper()

    @field_validator("quantity", "price")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        return _positive(v)

    @field_validator("commission", "slippage_cost", "spread_cost")
    @classmethod
    def _validate_costs(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v < 0:
            raise ValueError("costs must be non-negative Decimals")
        return v

    @field_validator("filled_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "filled_at")

    @property
    def gross_notional(self) -> Decimal:
        return self.quantity * self.price

    @property
    def total_cost(self) -> Decimal:
        return self.commission + self.slippage_cost + self.spread_cost

    @property
    def fill_hash(self) -> str:
        return "fill11." + deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "fill_id": self.fill_id,
                "client_order_id": self.client_order_id,
                "symbol": self.symbol,
                "side": self.side.value,
                "quantity": str(self.quantity),
                "price": str(self.price),
                "commission": str(self.commission),
                "slippage_cost": str(self.slippage_cost),
                "spread_cost": str(self.spread_cost),
                "filled_at": self.filled_at,
            }
        )


class PaperPosition(BaseModel):
    """Average-cost position state for one symbol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("symbol must be non-empty")
        return v.strip().upper()

    def apply_fill(self, fill: Fill) -> "PaperPosition":
        """Return a NEW position with ``fill`` applied (average cost)."""
        if fill.symbol != self.symbol:
            raise ValueError(
                f"fill symbol {fill.symbol} does not match position "
                f"{self.symbol}"
            )
        signed = fill.quantity if fill.side is OrderSide.BUY else -fill.quantity
        per_unit_cost = fill.total_cost / fill.quantity
        if fill.side is OrderSide.BUY:
            price_incl = fill.price + per_unit_cost  # costs add to basis
        else:
            price_incl = fill.price - per_unit_cost  # costs cut proceeds
        if self.quantity == 0:
            return PaperPosition(
                symbol=self.symbol,
                quantity=signed,
                average_cost=price_incl,
                realized_pnl=self.realized_pnl,
            )
        if (self.quantity > 0 and signed > 0) or (self.quantity < 0 and signed < 0):
            total_cost = self.average_cost * abs(self.quantity) + price_incl * fill.quantity
            total_qty = abs(self.quantity + signed)
            return PaperPosition(
                symbol=self.symbol,
                quantity=self.quantity + signed,
                average_cost=total_cost / total_qty,
                realized_pnl=self.realized_pnl,
            )
        # Reducing or flipping
        closing = min(abs(signed), abs(self.quantity))
        pnl_per_unit = (
            price_incl - self.average_cost
            if self.quantity > 0
            else self.average_cost - price_incl
        )
        realized = self.realized_pnl + pnl_per_unit * closing
        new_qty = self.quantity + signed
        if new_qty == 0:
            # Full close: no basis, no residual position.
            new_average_cost = Decimal("0")
        elif (new_qty > 0) != (self.quantity > 0):
            # BUG-002 correction: position FLIP — the residual opposite
            # side OPENS at the flip fill's all-in price. The closed
            # side's average cost must never carry into the new side
            # (it would double-count the basis and corrupt every later
            # realized-P&L computation on the flipped position).
            new_average_cost = price_incl
        else:
            # Same-sign partial reduction: the remaining basis is the
            # original average cost (unchanged).
            new_average_cost = self.average_cost
        return PaperPosition(
            symbol=self.symbol,
            quantity=new_qty,
            average_cost=new_average_cost,
            realized_pnl=realized,
        )


__all__ = [
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "PaperOrder",
    "Fill",
    "PaperPosition",
    "PHASE_11_CONTRACT_VERSION",
]
