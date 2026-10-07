"""Phase 11 — Execution simulator with market realism (blueprint 5.51).

Deterministic fill model with the realism knobs the blueprint
mandates (spread, fees, slippage, latency):

- **Latency**: market orders fill at the NEXT bar's open (a market
  order submitted during bar t executes against bar t+1 — never
  against the bar that triggered it, which would be look-ahead).
- **Spread**: cost = half-spread applied adversely (buy at ask = mid
  + half-spread; sell at bid = mid - half-spread).
- **Commission**: fixed per-unit rate.
- **Slippage**: deterministic impact = impact_rate * (quantity /
  bar_volume), applied adversely. Oversized orders (quantity >
  participation_cap * bar_volume) are REJECTED — a paper fill that
  real markets could not execute is a realism failure, not a feature.

All realism parameters arrive in an immutable ``ExecutionRealism``
config; every fill records its full cost decomposition.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.paper.models import (
    Fill,
    OrderSide,
    OrderType,
    PaperOrder,
    PHASE_11_CONTRACT_VERSION,
)


class SimulationError(ValueError):
    """Raised on execution-simulation contract violations."""


def _bar_time(bar: Mapping) -> datetime:
    ts = bar.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise SimulationError("bars need timezone-aware timestamps")
    return ts.astimezone(UTC)


class ExecutionRealism(BaseModel):
    """Immutable realism parameters (all costs explicit, none hidden)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    half_spread: Decimal
    commission_per_unit: Decimal
    impact_rate: Decimal  # slippage fraction per (qty/volume)
    participation_cap: Decimal  # max fraction of bar volume fillable
    fill_lag_bars: int = 1  # latency: bars until a market order fills

    @field_validator("half_spread", "commission_per_unit", "impact_rate")
    @classmethod
    def _validate_non_negative(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v < 0:
            raise ValueError("realism costs must be non-negative Decimals")
        return v

    @field_validator("participation_cap")
    @classmethod
    def _validate_cap(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or not 0 < v <= 1:
            raise ValueError("participation cap must be in (0, 1]")
        return v

    @field_validator("fill_lag_bars")
    @classmethod
    def _validate_lag(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("fill_lag_bars must be >= 1 (no same-bar fills)")
        return v

    @property
    def realism_hash(self) -> str:
        return "real11." + deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "half_spread": str(self.half_spread),
                "commission_per_unit": str(self.commission_per_unit),
                "impact_rate": str(self.impact_rate),
                "participation_cap": str(self.participation_cap),
                "fill_lag_bars": self.fill_lag_bars,
            }
        )


class ExecutionSimulator:
    """Deterministic fill engine over duck-typed bars.

    Bars are mappings with timezone-aware ``timestamp``, ``open``,
    ``high``, ``low``, ``close``, ``volume`` (Decimal or float).
    """

    def __init__(self, realism: ExecutionRealism) -> None:
        self._realism = realism

    @property
    def realism(self) -> ExecutionRealism:
        return self._realism

    def simulate(
        self,
        order: PaperOrder,
        bars: Sequence[Mapping],
    ) -> Optional[Fill]:
        """Simulate ``order`` over the bar series.

        Returns the Fill, or None when the order does not fill:

        - MARKET orders fill at the open of bar index ``fill_lag_bars``
          after the submission bar (latency).
        - LIMIT orders fill only on a bar (at/after the lag) whose
          price crosses the limit (buy: low <= limit; sell: high >=
          limit), at the limit price.

        Oversized orders (participation cap) raise SimulationError —
        they are realism failures, not silent partial fills.
        """
        if not bars:
            raise SimulationError("no bars to simulate against")
        # Locate the submission bar (last bar at or before submitted_at)
        submit_idx = None
        for idx, bar in enumerate(bars):
            if _bar_time(bar) <= order.submitted_at:
                submit_idx = idx
        if submit_idx is None:
            raise SimulationError(
                "order submitted before the first bar — no market context"
            )

        fill_idx = submit_idx + self._realism.fill_lag_bars
        if fill_idx >= len(bars):
            return None  # latency window extends past available data

        bar = bars[fill_idx]
        volume = Decimal(str(bar.get("volume") or 0))
        if volume <= 0:
            raise SimulationError("fill bar has no volume")
        if order.quantity > self._realism.participation_cap * volume:
            raise SimulationError(
                f"order quantity {order.quantity} exceeds participation "
                f"cap ({self._realism.participation_cap} * {volume}) — "
                "the market could not absorb this fill"
            )

        if order.order_type is OrderType.MARKET:
            reference = Decimal(str(bar["open"]))
            return self._fill_at_reference(order, reference, fill_idx, bar)
        # LIMIT
        low = Decimal(str(bar["low"]))
        high = Decimal(str(bar["high"]))
        if order.side is OrderSide.BUY and low <= order.limit_price:
            return self._fill_at_reference(order, order.limit_price, fill_idx, bar)
        if order.side is OrderSide.SELL and high >= order.limit_price:
            return self._fill_at_reference(order, order.limit_price, fill_idx, bar)
        return None

    def _fill_at_reference(
        self, order: PaperOrder, reference: Decimal, fill_idx: int, bar: Mapping
    ) -> Fill:
        """Build the fill at ``reference`` with adverse spread + impact."""
        volume = Decimal(str(bar.get("volume") or 0))
        impact_price = (
            self._realism.impact_rate * (order.quantity / volume) * reference
        )
        if order.side is OrderSide.BUY:
            price = reference + self._realism.half_spread + impact_price
        else:
            price = reference - self._realism.half_spread - impact_price
        return Fill(
            fill_id=f"{order.client_order_id}-F{fill_idx}",
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            commission=self._realism.commission_per_unit * order.quantity,
            slippage_cost=impact_price * order.quantity,
            spread_cost=self._realism.half_spread * order.quantity,
            filled_at=_bar_time(bar),
        )


__all__ = [
    "SimulationError",
    "ExecutionRealism",
    "ExecutionSimulator",
]
