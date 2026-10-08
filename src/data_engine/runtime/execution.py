"""Paper execution adapter — partial fills, TTL realism, structural
isolation (pre-paper mandate §30/§38/§59; RT-F10).

The adapter is the runtime-side execution gateway. It is
STRUCTURALLY isolated in PAPER mode (mandate §59):

- no broker credentials (there is no credential field anywhere),
- no production endpoints (no network import, no URL field),
- no real capital (notional is play-money by construction),
- no account mutation (fills exist only inside this simulator).

Fill model (deterministic, mirrors the BUG-001-corrected simulator
cost semantics, extended to MULTI-BAR PARTIAL fills):

- **Latency**: filling starts at ``submit bar + fill_lag_bars``.
- **Per-bar liquidity**: at most ``participation_cap * bar_volume``
  units fill per bar; the REMAINDER spills to subsequent bars —
  never one unrealistic perfect fill (mandate §38).
- **MARKET price**: open ± half_spread ± impact (adverse stack),
  with impact computed on THIS partial fill's quantity.
- **LIMIT price**: BUG-001 protection — BUY never above the limit,
  SELL never below it; fills only on bars that cross the limit.
- Every fill records its full cost decomposition (commission,
  slippage/impact, spread) — nothing hidden (§36).

An order whose quantity exceeds every bar's capacity simply leaves
an unfilled remainder (→ EXPIRED by TTL, ledgered) — never a fake
perfect fill and never a silent drop.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.paper.simulator import ExecutionRealism, SimulationError
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import FILL_PREFIX, prefixed_hash

#: Structural isolation marker (mandate §59) — tests assert this and
#: the absence of any credential/endpoint/network surface.
PAPER_MODE_STRUCTURAL_ISOLATION = True


class ExecutionAdapterError(RuntimeContractError):
    """Raised on execution-adapter contract violations."""


def _bar_time(bar: Mapping) -> datetime:
    ts = bar.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise ExecutionAdapterError("bars need timezone-aware timestamps")
    return ts.astimezone(UTC)


class RuntimeFill(BaseModel):
    """One (possibly partial) fill with full cost decomposition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str
    order_id: str
    symbol: str
    side: str  # BUY / SELL (runtime vocabulary)
    quantity: Decimal
    price: Decimal
    commission: Decimal
    slippage_cost: Decimal
    spread_cost: Decimal
    filled_at: datetime
    fill_index: int  # 0-based sequence within the order
    bar_index: int  # index of the filling bar in the input series

    @field_validator("symbol", "side")
    @classmethod
    def _validate_vocab(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ExecutionAdapterError("fill symbol/side must be non-empty")
        return v.strip().upper()

    @field_validator("fill_id", "order_id")
    @classmethod
    def _validate_hash_ids(cls, v: str) -> str:
        # Hash identifiers are case-sensitive — strip only, never case-fold.
        if not isinstance(v, str) or not v.strip():
            raise ExecutionAdapterError("fill hash ids must be non-empty")
        return v.strip()

    @field_validator("quantity", "price")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise ExecutionAdapterError("quantity/price must be positive")
        return v

    @field_validator("commission", "slippage_cost", "spread_cost")
    @classmethod
    def _validate_costs(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v < 0:
            raise ExecutionAdapterError("costs must be non-negative")
        return v

    @field_validator("filled_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ExecutionAdapterError("filled_at must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def fill_hash(self) -> str:
        return prefixed_hash(
            FILL_PREFIX,
            {
                "kind": "runtime_fill",
                "order_id": self.order_id,
                "fill_index": self.fill_index,
                "symbol": self.symbol,
                "side": self.side,
                "quantity": str(self.quantity),
                "price": str(self.price),
                "commission": str(self.commission),
                "slippage_cost": str(self.slippage_cost),
                "spread_cost": str(self.spread_cost),
                "filled_at": self.filled_at,
                "bar_index": self.bar_index,
            },
        )


class PaperExecutionAdapter:
    """Multi-bar partial-fill paper executor (PAPER only, §59).

    Deterministic: ``execute`` is a pure function of
    (order parameters, bar series, realism config). No RNG, no
    wall-clock, no network, no credentials.
    """

    def __init__(self, realism: ExecutionRealism) -> None:
        if realism is None:
            raise ExecutionAdapterError("realism config is required")
        self._realism = realism

    @property
    def realism(self) -> ExecutionRealism:
        return self._realism

    # ------------------------------------------------------------------
    def execute(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        bars: Sequence[Mapping],
        submitted_at: datetime,
        limit_price: Optional[Decimal] = None,
        max_bars: Optional[int] = None,
        from_bar: Optional[int] = None,
        start_index: int = 0,
    ) -> list:
        """Execute one order; returns the list of NEW partial fills.

        ``from_bar``: resume scanning at this bar index (pending-order
        re-invocation across bars — prevents duplicate fills for bars
        already consumed). ``start_index``: continue the order's fill
        index numbering (prevents duplicate fill identities).
        ``max_bars`` bounds the fill window (TTL). Empty list ⇒ no
        fill on the scanned window (order stays live for TTL, then
        EXPIRES — mandate §39).
        """
        if side not in ("BUY", "SELL"):
            raise ExecutionAdapterError("side must be BUY or SELL")
        if order_type not in ("MARKET", "LIMIT"):
            raise ExecutionAdapterError("order_type must be MARKET or LIMIT")
        if quantity is None or not quantity.is_finite() or quantity <= 0:
            raise ExecutionAdapterError("quantity must be positive")
        if not bars:
            raise ExecutionAdapterError("no bars to execute against")
        if order_type == "LIMIT" and limit_price is None:
            raise ExecutionAdapterError("LIMIT orders require a limit price")

        # BUG-007 discipline: strictly increasing bar timestamps.
        previous = None
        for idx, bar in enumerate(bars):
            ts = _bar_time(bar)
            if previous is not None and ts <= previous:
                raise SimulationError(
                    f"bar {idx} timestamp not strictly increasing "
                    "(BUG-007 discipline)"
                )
            previous = ts

        submit_idx = None
        for idx, bar in enumerate(bars):
            if _bar_time(bar) <= submitted_at:
                submit_idx = idx
        if submit_idx is None:
            raise ExecutionAdapterError(
                "order submitted before the first bar — no market context"
            )

        latency_start = submit_idx + self._realism.fill_lag_bars
        start = latency_start if from_bar is None else max(latency_start, from_bar)
        end = len(bars) if max_bars is None else min(
            len(bars), latency_start + max_bars
        )

        fills: list = []
        remaining = quantity
        fill_index = start_index
        for bar_idx in range(start, end):
            if remaining <= 0:
                break
            bar = bars[bar_idx]
            volume = Decimal(str(bar.get("volume") or 0))
            if volume <= 0:
                continue  # no liquidity on this bar — spill to the next
            capacity = self._realism.participation_cap * volume
            fill_qty = min(remaining, capacity)
            if fill_qty <= 0:
                continue
            open_ = Decimal(str(bar["open"]))
            low = Decimal(str(bar["low"]))
            high = Decimal(str(bar["high"]))
            impact = (
                self._realism.impact_rate
                * (fill_qty / volume)
                * open_
            )
            if order_type == "MARKET":
                if side == "BUY":
                    price = open_ + self._realism.half_spread + impact
                else:
                    price = open_ - self._realism.half_spread - impact
            else:  # LIMIT — BUG-001 protection, never through the limit
                crosses = (low <= limit_price) if side == "BUY" else (high >= limit_price)
                if not crosses:
                    continue  # resting; no fill on this bar
                if side == "BUY":
                    price = min(limit_price, open_ + self._realism.half_spread + impact)
                else:
                    price = max(limit_price, open_ - self._realism.half_spread - impact)
            commission = self._realism.commission_per_unit * fill_qty
            # Cost decomposition for the ledger: adverse stack actually
            # charged above/below the bar open.
            adverse = abs(price - open_)
            spread_cost = min(self._realism.half_spread, adverse)
            slippage_cost = adverse - spread_cost
            fill = RuntimeFill(
                fill_id="pending",
                order_id=order_id,
                symbol=symbol,
                side=side,
                quantity=fill_qty,
                price=price,
                commission=commission,
                slippage_cost=slippage_cost,
                spread_cost=spread_cost,
                filled_at=_bar_time(bar),
                fill_index=fill_index,
                bar_index=bar_idx,
            )
            fill = fill.model_copy(
                update={"fill_id": fill.fill_hash}
            )
            fills.append(fill)
            remaining -= fill_qty
            fill_index += 1
        return fills


__all__ = [
    "PAPER_MODE_STRUCTURAL_ISOLATION",
    "ExecutionAdapterError",
    "RuntimeFill",
    "PaperExecutionAdapter",
]
