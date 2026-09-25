"""Position state machine for Phase 3 backtests.

Implements the position state machine from the design spec:
- FLAT → OPEN via open_position()
- OPEN → FLAT via close_position()
- OPEN → OPEN via update_unrealized() (mark-to-market only, no state transition)
- FLAT → FLAT via update_unrealized() (no-op)

All models are frozen (immutable). Updates return new instances.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class PositionState(str, Enum):
    """Position state enumeration."""
    FLAT = "FLAT"
    OPEN = "OPEN"


class PositionTracker(BaseModel):
    """Immutable position tracker with enforced state machine.

    Fields:
        side: "NONE", "LONG", or "SHORT"
        quantity: >0 when open, 0 when flat
        entry_fill_price: fill price at entry (None when flat)
        entry_timestamp: timestamp when position was opened (None when flat)
        cumulative_pnl: sum of realized P&L from all closed positions
        unrealized_pnl: mark-to-market P&L while open (0 when flat)
    """

    model_config = ConfigDict(frozen=True)

    side: str = "NONE"
    quantity: float = 0.0
    entry_fill_price: Optional[float] = None
    entry_timestamp: Optional[datetime] = None
    cumulative_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def is_open(self) -> bool:
        """True if currently in an open position."""
        return self.side in ("LONG", "SHORT") and self.quantity > 0

    @property
    def is_flat(self) -> bool:
        """True if currently flat (no position)."""
        return self.side == "NONE" or self.quantity == 0

    def open_position(
        self,
        side: str,
        quantity: float,
        fill_price: float,
        timestamp: datetime,
    ) -> "PositionTracker":
        """Open a new position. Returns new tracker.

        Raises ValueError if already in a position (side != "NONE").
        Raises ValueError if quantity <= 0.
        Raises ValueError if side is not LONG or SHORT.
        """
        if self.side != "NONE":
            raise ValueError("Cannot open position when already in a position")
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if side not in ("LONG", "SHORT"):
            raise ValueError(f"Invalid side: {side}. Must be 'LONG' or 'SHORT'.")
        return self.model_copy(update={
            "side": side,
            "quantity": quantity,
            "entry_fill_price": fill_price,
            "entry_timestamp": timestamp,
            "unrealized_pnl": 0.0,
        })

    def update_unrealized(self, current_price: float) -> "PositionTracker":
        """Mark-to-market update. Returns new tracker with updated unrealized_pnl.

        NO STATE TRANSITION — side and quantity remain unchanged.
        When flat, unrealized_pnl is 0.0.
        """
        if not self.is_open or self.entry_fill_price is None:
            return self.model_copy(update={"unrealized_pnl": 0.0})
        if self.side == "LONG":
            unrealized = (current_price - self.entry_fill_price) * self.quantity
        elif self.side == "SHORT":
            unrealized = (self.entry_fill_price - current_price) * self.quantity
        else:
            unrealized = 0.0
        return self.model_copy(update={"unrealized_pnl": unrealized})

    def close_position(
        self,
        exit_fill_price: float,
        exit_timestamp: datetime,
    ) -> "PositionTracker":
        """Close the current position. Returns new tracker.

        Raises ValueError if flat (no open position).
        Sets side to "NONE", quantity to 0.0, clears entry fields.
        Adds realized P&L to cumulative_pnl.
        """
        if not self.is_open:
            raise ValueError("Cannot close position when flat")
        if self.entry_fill_price is None:
            raise ValueError("Cannot close position without entry fill price")
        side = self.side
        entry_price = self.entry_fill_price
        if side == "LONG":
            pnl = (exit_fill_price - entry_price) * self.quantity
        else:
            pnl = (entry_price - exit_fill_price) * self.quantity
        return self.model_copy(update={
            "side": "NONE",
            "quantity": 0.0,
            "entry_fill_price": None,
            "entry_timestamp": None,
            "cumulative_pnl": self.cumulative_pnl + pnl,
            "unrealized_pnl": 0.0,
        })

    def to_dict(self) -> dict:
        """Return a dict representation."""
        return self.model_dump()
