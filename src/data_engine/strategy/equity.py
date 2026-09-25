"""Equity tracking for Phase 3 backtests.

Implements the accounting invariant from the design spec:
    equity(t) = cash(t) + position_market_value(t)

This identity holds at every bar, for every position state
(flat, long, short), with zero exceptions.

All models are frozen (immutable). Updates return new instances.
"""

from datetime import datetime, UTC
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, model_validator


class EquityPoint(BaseModel):
    """A single point on the equity curve.

    Invariant: total_equity == cash + position_market_value
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    total_equity: float
    cash: float
    position_market_value: float
    # Additional tracking fields
    position: float = 0.0  # Current position quantity
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    cumulative_fees: float = 0.0
    drawdown: float = 0.0
    cumulative_return: float = 0.0
    daily_return: Optional[float] = None

    @model_validator(mode='after')
    def validate_equity_invariant(self) -> "EquityPoint":
        """Verify equity = cash + position_market_value."""
        if abs(self.total_equity - (self.cash + self.position_market_value)) > 1e-10:
            raise ValueError(
                f"Equity invariant violated: total_equity={self.total_equity} "
                f"!= cash + position_market_value = {self.cash + self.position_market_value}"
            )
        return self


class EquityTracker(BaseModel):
    """Immutable equity curve tracker.

    Tracks the equity curve through time, maintaining the invariant:
        total_equity == cash + position_market_value
    at every point.
    """

    model_config = ConfigDict(frozen=True)

    initial_capital: float
    equity_curve: List[EquityPoint] = Field(default_factory=list)
    running_peak: float = 0.0

    def add_point(self, point: EquityPoint) -> "EquityTracker":
        """Add a new equity point. Returns new tracker.

        Validates the invariant equity == cash + position_market_value.
        Updates the running peak.
        """
        # Verify invariant
        if abs(point.total_equity - (point.cash + point.position_market_value)) > 1e-10:
            raise ValueError(
                f"Equity invariant violated: {point.total_equity} != "
                f"{point.cash} + {point.position_market_value}"
            )
        new_equity = point.total_equity
        new_peak = max(self.running_peak, new_equity) if self.equity_curve else new_equity
        return self.model_copy(update={
            "equity_curve": self.equity_curve + [point],
            "running_peak": new_peak,
        })

    def get_current_equity(self) -> float:
        """Return the latest total equity. Returns initial_capital if no points."""
        if self.equity_curve:
            return self.equity_curve[-1].total_equity
        return self.initial_capital

    def get_equity_values(self) -> List[float]:
        """Return list of total_equity values from the equity curve."""
        return [p.total_equity for p in self.equity_curve]

    def get_timestamps(self) -> List[datetime]:
        """Return list of timestamps."""
        return [p.timestamp for p in self.equity_curve]

    def to_dict(self) -> dict:
        """Return a dict representation."""
        return {
            "initial_capital": self.initial_capital,
            "current_equity": self.get_current_equity(),
            "current_drawdown": self.get_current_drawdown(),
            "num_points": len(self.equity_curve),
        }

    def get_current_drawdown(self) -> float:
        """Return the current drawdown."""
        if self.equity_curve:
            return self.equity_curve[-1].drawdown
        return 0.0
