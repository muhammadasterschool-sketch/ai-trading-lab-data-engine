"""Complete trade ledger for Phase 3 backtests.

Every completed trade records:
- trade_id
- side, entry/exit prices and commissions
- quantity, gross_pnl, net_pnl
- entry/exit timestamps, holding_period_bars, exit_reason
- slippage (informational, embedded in fill price)

All trade records are immutable (frozen Pydantic models).
Trade IDs are deterministic: trade-000001, trade-000002, etc.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from data_engine.strategy.schemas import OrderSide, OrderStatus, ExitReason


class Trade(BaseModel):
    """Immutable record of a completed trade.

    Fields follow the canonical trade_serialization format from Section I.
    """
    model_config = ConfigDict(frozen=True)

    trade_id: str
    side: OrderSide
    entry_fill_price: float
    exit_fill_price: Optional[float] = None
    quantity: float
    entry_commission: float
    exit_commission: float
    gross_pnl: float
    net_pnl: float
    entry_timestamp: Optional[datetime] = None
    exit_timestamp: Optional[datetime] = None
    holding_period_bars: Optional[int] = None
    exit_reason: Optional[ExitReason] = None
    # Informational fields (embedded in fill price, not in canonical serialization)
    slippage: float = 0.0

    @property
    def is_closed(self) -> bool:
        """Return True if the trade has been closed."""
        return self.exit_timestamp is not None and self.exit_fill_price is not None

    def close(
        self,
        exit_timestamp: datetime,
        exit_fill_price: float,
        exit_reason: ExitReason,
        exit_commission: float,
    ) -> "Trade":
        """Return a closed version of this trade.

        Computes gross_pnl based on side, and net_pnl = gross_pnl - entry_commission - exit_commission.
        Holding period is computed from entry to exit timestamps.
        """
        if self.side == OrderSide.LONG:
            gross_pnl = (exit_fill_price - self.entry_fill_price) * self.quantity
        else:
            gross_pnl = (self.entry_fill_price - exit_fill_price) * self.quantity

        net_pnl = gross_pnl - self.entry_commission - exit_commission
        holding_period_bars = None
        if self.entry_timestamp is not None:
            holding_period_bars = (exit_timestamp - self.entry_timestamp).days

        return self.model_copy(update={
            "exit_timestamp": exit_timestamp,
            "exit_fill_price": exit_fill_price,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "exit_commission": exit_commission,
            "exit_reason": exit_reason,
            "holding_period_bars": holding_period_bars,
        })

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return self.model_dump()


class TradeLedger(BaseModel):
    """Immutable ledger of all trades in a backtest.

    Trade IDs are assigned deterministically in chronological order:
    trade-000001, trade-000002, etc.
    """
    model_config = ConfigDict(frozen=True)

    trades: List[Trade] = Field(default_factory=list)

    def add_trade(self, trade: Trade) -> "TradeLedger":
        """Return a new ledger with the trade added.

        Assigns the next deterministic trade ID (trade-000001, trade-000002, ...).
        """
        trade_id = f"trade-{len(self.trades) + 1:06d}"
        new_trade = trade.model_copy(update={"trade_id": trade_id})
        return self.model_copy(update={"trades": self.trades + [new_trade]})

    def get_trades(self) -> List[Trade]:
        """Return all trades."""
        return self.trades.copy()

    def get_closed_trades(self) -> List[Trade]:
        """Return only closed trades."""
        return [t for t in self.trades if t.is_closed]

    def total_trades(self) -> int:
        """Return total number of trades."""
        return len(self.trades)

    def total_closed(self) -> int:
        """Return number of closed trades."""
        return len(self.get_closed_trades())

    def total_net_pnl(self) -> float:
        """Return sum of all closed trade net P&L."""
        return sum(t.net_pnl for t in self.get_closed_trades())

    def total_commissions(self) -> float:
        """Return total commissions paid across all trades."""
        return sum(t.entry_commission + t.exit_commission for t in self.trades)

    def total_slippage(self) -> float:
        """Return total slippage across all trades (informational)."""
        return sum(t.slippage for t in self.trades)

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return {
            "total_trades": self.total_trades(),
            "total_net_pnl": self.total_net_pnl(),
            "total_commissions": self.total_commissions(),
            "total_slippage": self.total_slippage(),
            "trades": [t.to_dict() for t in self.trades],
        }
