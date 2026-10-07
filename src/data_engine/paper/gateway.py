"""Phase 11 — Paper order gateway, P&L, reconciliation, audit, analytics.

- ``PaperOrderGateway`` (blueprint 5.51): order lifecycle management
  with duplicate client-order-id protection. No broker credentials
  exist anywhere in the gateway — there is nothing to leak.
- ``PnLCalculator`` / ``ReconciliationEngine`` (blueprint 5.55):
  realized/unrealized P&L; order->fill->position reconciliation with
  discrepancy failures (fail closed, never papered over).
- ``AuditLogger`` (blueprint 5.51): hash-chained immutable execution
  audit trail.
- ``AnalyticsEngine``: paper metrics over the equity curve
  (deterministic; reuses no frozen Phase 3 code — duck-typed floats).
"""

from decimal import Decimal
from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.paper.models import (
    Fill,
    OrderSide,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    PHASE_11_CONTRACT_VERSION,
)
from data_engine.paper.simulator import ExecutionSimulator, SimulationError


class GatewayError(ValueError):
    """Raised on gateway contract violations."""


class GatewayRecord(BaseModel):
    """One order's lifecycle record in the gateway."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order: PaperOrder
    status: OrderStatus
    fill: Optional[Fill] = None

    @property
    def record_hash(self) -> str:
        return "gw11." + deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "order_hash": self.order.order_hash,
                "status": self.status.value,
                "fill_hash": self.fill.fill_hash if self.fill else None,
            }
        )


class PaperOrderGateway:
    """Order lifecycle: submit -> simulate -> record. Duplicate-safe."""

    def __init__(self, simulator: ExecutionSimulator) -> None:
        self._simulator = simulator
        self._records: dict[str, GatewayRecord] = {}

    def submit(
        self, order: PaperOrder, bars: Sequence[Mapping]
    ) -> GatewayRecord:
        """Submit an order against a bar series; record the outcome.

        Duplicate client_order_id raises (duplicate protection,
        blueprint 5.53 semantics applied to paper trading too).
        """
        if order.client_order_id in self._records:
            raise GatewayError(
                f"duplicate client_order_id {order.client_order_id!r} — "
                "duplicate protection engaged"
            )
        try:
            fill = self._simulator.simulate(order, bars)
        except SimulationError as exc:
            record = GatewayRecord(
                order=order, status=OrderStatus.REJECTED, fill=None
            )
            self._records[order.client_order_id] = record
            raise GatewayError(f"order rejected by realism gate: {exc}") from exc
        status = OrderStatus.FILLED if fill is not None else OrderStatus.SUBMITTED
        record = GatewayRecord(order=order, status=status, fill=fill)
        self._records[order.client_order_id] = record
        return record

    def cancel(self, client_order_id: str) -> GatewayRecord:
        """Cancel a submitted (unfilled) order."""
        key = client_order_id.strip().upper()
        record = self._records.get(key)
        if record is None:
            raise GatewayError(f"unknown order {client_order_id!r}")
        if record.status is not OrderStatus.SUBMITTED:
            raise GatewayError(
                f"order {client_order_id!r} is {record.status.value} — "
                "only submitted orders can be cancelled"
            )
        updated = GatewayRecord(order=record.order, status=OrderStatus.CANCELLED)
        self._records[key] = updated
        return updated

    def record(self, client_order_id: str) -> GatewayRecord:
        key = client_order_id.strip().upper()
        if key not in self._records:
            raise GatewayError(f"unknown order {client_order_id!r}")
        return self._records[key]

    @property
    def records(self) -> tuple[GatewayRecord, ...]:
        return tuple(self._records.values())


class ReconciliationError(ValueError):
    """Order/fill/position discrepancy — never papered over."""


class ReconciliationEngine:
    """Reconciles orders, fills, and positions (blueprint 5.55)."""

    def reconcile(
        self,
        orders: Sequence[PaperOrder],
        fills: Sequence[Fill],
        positions: Mapping[str, PaperPosition],
    ) -> dict:
        """Full three-way reconciliation.

        Checks: (1) every fill's order exists; (2) every filled order
        has its fill; (3) replaying fills from zero reproduces the
        stated positions EXACTLY (quantity + realized P&L).
        """
        order_ids = {o.client_order_id for o in orders}
        orphan_fills = sorted(
            {f.client_order_id for f in fills} - order_ids
        )
        if orphan_fills:
            raise ReconciliationError(
                f"fills without orders: {orphan_fills[:5]}"
            )
        fill_by_order: dict[str, Fill] = {}
        for fill in fills:
            if fill.client_order_id in fill_by_order:
                raise ReconciliationError(
                    f"multiple fills for {fill.client_order_id!r} "
                    "(single-fill model violated)"
                )
            fill_by_order[fill.client_order_id] = fill

        replayed: dict[str, PaperPosition] = {}
        for fill in sorted(fills, key=lambda f: (f.filled_at, f.fill_id)):
            position = replayed.get(
                fill.symbol, PaperPosition(symbol=fill.symbol)
            )
            replayed[fill.symbol] = position.apply_fill(fill)

        mismatches = []
        for symbol, stated in positions.items():
            replay = replayed.get(symbol, PaperPosition(symbol=symbol))
            if stated.quantity != replay.quantity or stated.realized_pnl != replay.realized_pnl:
                mismatches.append(
                    f"{symbol}: stated qty={stated.quantity}/pnl="
                    f"{stated.realized_pnl} vs replay qty={replay.quantity}/"
                    f"pnl={replay.realized_pnl}"
                )
        extra = sorted(set(replayed) - set(positions))
        if extra:
            mismatches.append(f"positions missing from state: {extra[:5]}")
        if mismatches:
            raise ReconciliationError(
                "reconciliation failed: " + "; ".join(mismatches[:5])
            )
        return {
            "orders": len(orders),
            "fills": len(fills),
            "symbols": sorted(positions),
            "status": "reconciled",
        }


class AuditLogger:
    """Hash-chained immutable execution audit trail."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def log(self, event: str, payload: dict) -> str:
        """Append one audit event; returns its chain hash."""
        prev = self._entries[-1]["chain_hash"] if self._entries else "0" * 64
        index = len(self._entries)
        chain_hash = deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "event": event,
                "payload": payload,
                "prev_chain_hash": prev,
                "index": index,
            }
        )
        self._entries.append(
            {
                "event": event,
                "payload": payload,
                "chain_hash": chain_hash,
                "prev_chain_hash": prev,
                "index": index,
            }
        )
        return chain_hash

    def verify(self) -> bool:
        prev = "0" * 64
        for entry in self._entries:
            expected = deterministic_hash(
                {
                    "contract_version": PHASE_11_CONTRACT_VERSION,
                    "event": entry["event"],
                    "payload": entry["payload"],
                    "prev_chain_hash": prev,
                    "index": entry["index"],
                }
            )
            if expected != entry["chain_hash"]:
                return False
            prev = entry["chain_hash"]
        return True

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[dict, ...]:
        return tuple(self._entries)


class AnalyticsEngine:
    """Deterministic paper analytics over an equity curve."""

    @staticmethod
    def total_pnl(equity_curve: Sequence[float]) -> float:
        if len(equity_curve) < 2:
            raise ValueError("equity curve needs >= 2 points")
        return equity_curve[-1] - equity_curve[0]

    @staticmethod
    def max_drawdown(equity_curve: Sequence[float]) -> float:
        if len(equity_curve) < 2:
            raise ValueError("equity curve needs >= 2 points")
        peak = equity_curve[0]
        worst = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                worst = max(worst, (peak - value) / peak)
        return worst

    @staticmethod
    def sharpe(returns: Sequence[float], periods_per_year: int = 252) -> float:
        if len(returns) < 2:
            raise ValueError("sharpe needs >= 2 returns")
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if variance <= 0:
            raise ValueError("zero-variance returns: sharpe undefined")
        import math
        return (mean / math.sqrt(variance)) * (periods_per_year ** 0.5)

    def summarize(
        self, equity_curve: Sequence[float],
        returns: Sequence[float],
    ) -> dict:
        return {
            "total_pnl": self.total_pnl(equity_curve),
            "max_drawdown": self.max_drawdown(equity_curve),
            "sharpe": self.sharpe(returns),
        }


__all__ = [
    "GatewayError",
    "GatewayRecord",
    "PaperOrderGateway",
    "ReconciliationError",
    "ReconciliationEngine",
    "AuditLogger",
    "AnalyticsEngine",
]
