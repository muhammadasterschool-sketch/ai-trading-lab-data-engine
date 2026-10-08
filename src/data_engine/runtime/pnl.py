"""Authoritative position state and P&L accounting (mandate §36/§37).

Position accounting deliberately REUSES the BUG-002-corrected
average-cost engine (``PaperPosition.apply_fill``) as its accounting
core — flip semantics (residual opens at the flip fill's all-in
price) were independently re-verified by P2, so the runtime inherits
proven math instead of reimplementing a divergent copy.

On top of that core, :class:`PositionState` adds the runtime
mandates: SL/TP levels, exposure, last-update source event linkage,
and exactly-one-authoritative-position semantics per symbol
(§37). :class:`PnLEngine` produces P&L records that link back to the
trade/order/fill chain (§36), including fees, spread, slippage,
partial fills, and position flips.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.paper.models import Fill as _PaperFill, PaperPosition
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import POSITION_PREFIX, prefixed_hash


class AccountingError(RuntimeContractError):
    """Raised on position/P&L contract violations."""


def _require_utc(v: datetime, name: str) -> datetime:
    if v is None or v.tzinfo is None:
        raise AccountingError(f"{name} must be timezone-aware")
    return v.astimezone(UTC)


class PositionState(BaseModel):
    """Exactly-one authoritative position for one symbol (§37).

    ``core`` is the proven average-cost engine state; ``sl``/``tp``
    are the governed protective levels; ``last_update_source`` links
    the latest mutation to its source event (fill/exit).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    quantity: Decimal = Decimal("0")
    average_cost: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    last_update: Optional[datetime] = None
    last_update_source: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise AccountingError("symbol must be non-empty")
        return v.strip().upper()

    @field_validator("last_update")
    @classmethod
    def _validate_time(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _require_utc(v, "last_update") if v else v

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def side(self) -> Optional[str]:
        if self.quantity > 0:
            return "LONG"
        if self.quantity < 0:
            return "SHORT"
        return None

    @property
    def exposure_units(self) -> Decimal:
        return abs(self.quantity)

    @property
    def position_id(self) -> str:
        return prefixed_hash(
            POSITION_PREFIX,
            {
                "kind": "position_state",
                "symbol": self.symbol,
                "quantity": str(self.quantity),
                "average_cost": str(self.average_cost),
                "realized_pnl": str(self.realized_pnl),
                "stop_loss": str(self.stop_loss) if self.stop_loss is not None else None,
                "take_profit": str(self.take_profit) if self.take_profit is not None else None,
            },
        )

    # -- mutations (return NEW state; no in-place mutation) ------------------
    def apply_fill(
        self,
        fill_quantity: Decimal,
        fill_price: Decimal,
        side: str,
        commission: Decimal = Decimal("0"),
        slippage_cost: Decimal = Decimal("0"),
        spread_cost: Decimal = Decimal("0"),
        filled_at: Optional[datetime] = None,
        source_event: Optional[str] = None,
    ) -> "PositionState":
        """Apply one (possibly partial) fill; returns the new state.

        Uses the BUG-002-corrected engine semantics via a transient
        ``PaperPosition`` — average cost, reduction, flip (residual at
        flip all-in price), full close.
        """
        if side not in ("BUY", "SELL"):
            raise AccountingError("fill side must be BUY or SELL")
        if fill_quantity is None or not fill_quantity.is_finite() or fill_quantity <= 0:
            raise AccountingError("fill quantity must be positive")
        core = PaperPosition(
            symbol=self.symbol,
            quantity=self.quantity,
            average_cost=self.average_cost,
            realized_pnl=self.realized_pnl,
        )
        paper_fill = _PaperFill(
            fill_id="transient",
            client_order_id="transient",
            symbol=self.symbol,
            side=side.lower(),  # paper vocabulary via the bridge rule
            quantity=fill_quantity,
            price=fill_price,
            commission=commission,
            slippage_cost=slippage_cost,
            spread_cost=spread_cost,
            filled_at=filled_at or datetime.now(UTC),
        )
        new_core = core.apply_fill(paper_fill)
        return PositionState(
            symbol=self.symbol,
            quantity=new_core.quantity,
            average_cost=new_core.average_cost,
            realized_pnl=new_core.realized_pnl,
            stop_loss=self.stop_loss,
            take_profit=self.take_profit,
            last_update=filled_at or datetime.now(UTC),
            last_update_source=source_event,
        )

    def with_protection(
        self,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
        source_event: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> "PositionState":
        """Return the state with updated SL/TP levels (SL/TP lifecycle
        mutations are recorded by the ExitManager's ledger events)."""
        return PositionState(
            symbol=self.symbol,
            quantity=self.quantity,
            average_cost=self.average_cost,
            realized_pnl=self.realized_pnl,
            stop_loss=stop_loss if stop_loss is not None else self.stop_loss,
            take_profit=take_profit if take_profit is not None else self.take_profit,
            last_update=at or datetime.now(UTC),
            last_update_source=source_event,
        )


class PnlRecord(BaseModel):
    """One P&L record linked to the trade/order/fill chain (§36)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pnl_id: str
    symbol: str
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees_paid: Decimal
    entry_fill_ids: Tuple[str, ...]
    exit_fill_ids: Tuple[str, ...]
    order_ids: Tuple[str, ...]
    mark_price: Optional[Decimal] = None
    correlation_id: str

    @field_validator("pnl_id", "symbol", "correlation_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise AccountingError("pnl record text fields must be non-empty")
        return v.strip()


class PnLEngine:
    """Authoritative accounting: realized/unrealized/fees per symbol
    with full chain linkage (mandate §36)."""

    def unrealized(self, state: PositionState, mark_price: Decimal) -> Decimal:
        """Unrealized P&L at ``mark_price`` (zero when flat)."""
        if mark_price is None or not mark_price.is_finite() or mark_price <= 0:
            raise AccountingError("mark price must be positive finite")
        if state.is_flat:
            return Decimal("0")
        if state.quantity > 0:
            return (mark_price - state.average_cost) * state.quantity
        return (state.average_cost - mark_price) * abs(state.quantity)

    def record(
        self,
        state: PositionState,
        mark_price: Optional[Decimal],
        fees_paid: Decimal,
        entry_fill_ids: Sequence[str],
        exit_fill_ids: Sequence[str],
        order_ids: Sequence[str],
        correlation_id: str,
    ) -> PnlRecord:
        """Build one P&L record for the ledger (§36 linkage)."""
        unrealized = (
            self.unrealized(state, mark_price) if mark_price is not None else Decimal("0")
        )
        pnl_id = prefixed_hash(
            POSITION_PREFIX,
            {
                "kind": "pnl_record",
                "symbol": state.symbol,
                "realized": str(state.realized_pnl),
                "unrealized": str(unrealized),
                "fees": str(fees_paid),
                "entry_fills": list(entry_fill_ids),
                "exit_fills": list(exit_fill_ids),
                "orders": list(order_ids),
                "correlation_id": correlation_id,
            },
        )
        return PnlRecord(
            pnl_id=pnl_id,
            symbol=state.symbol,
            realized_pnl=state.realized_pnl,
            unrealized_pnl=unrealized,
            fees_paid=fees_paid,
            entry_fill_ids=tuple(entry_fill_ids),
            exit_fill_ids=tuple(exit_fill_ids),
            order_ids=tuple(order_ids),
            mark_price=mark_price,
            correlation_id=correlation_id,
        )


__all__ = [
    "AccountingError",
    "PositionState",
    "PnlRecord",
    "PnLEngine",
]
