"""Phase 11 — Paper order gateway, P&L, reconciliation, audit, analytics.

- ``PaperOrderGateway`` (blueprint 5.51): order lifecycle management
  with duplicate client-order-id protection. No broker credentials
  exist anywhere in the gateway — there is nothing to leak.
- ``PnLCalculator`` / ``ReconciliationEngine`` (blueprint 5.55):
  realized/unrealized P&L; order->fill->position reconciliation with
  discrepancy failures (fail closed, never papered over). Since the
  BUG-004 correction, ``reconcile`` additionally accepts gateway
  records (status-aware input) and enforces the fills-if-and-only-if-
  FILLED invariant.
- ``AuditLogger`` (blueprint 5.51): hash-chained immutable execution
  audit trail. Since the BUG-005 correction, payloads are deep-copied
  on write and on read, and entries carry ``timestamp`` /
  ``component`` / ``event_id`` observability fields.
- ``AnalyticsEngine``: paper metrics over the equity curve
  (deterministic; reuses no frozen Phase 3 code — duck-typed floats).
  Since the BUG-009 correction, non-finite curve points fail closed.
"""

import copy
import math
from datetime import datetime, UTC
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
        orders: Sequence,
        fills: Sequence[Fill],
        positions: Mapping[str, PaperPosition],
    ) -> dict:
        """Full three-way reconciliation.

        ``orders`` may be either:

        - a sequence of :class:`PaperOrder` — legacy, status-blind
          input: check (2) is NOT verifiable without statuses and is
          honestly skipped; or
        - a sequence of :class:`GatewayRecord` — status-aware input
          (BUG-004 correction): check (2) is enforced — a fill exists
          if and only if the order's status is FILLED.

        Checks: (1) every fill's order exists; (2) [status-aware
        input only] every FILLED order has exactly one fill and no
        SUBMITTED/CANCELLED/REJECTED order has any; (3) replaying
        fills from zero reproduces the stated positions EXACTLY
        (quantity + realized P&L).
        """
        status_by_order: Optional[dict[str, OrderStatus]] = None
        if orders and all(
            hasattr(o, "status") and hasattr(o, "order") for o in orders
        ):
            # Status-aware input (GatewayRecord sequence).
            status_by_order = {
                r.order.client_order_id: r.status for r in orders
            }
            order_list = [r.order for r in orders]
        else:
            order_list = list(orders)

        order_ids = {o.client_order_id for o in order_list}
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

        if status_by_order is not None:
            # BUG-004: the docstring's check (2) is now implemented for
            # status-aware input — a FILLED order whose fill record went
            # missing no longer reconciles clean.
            missing_fills = sorted(
                order_id
                for order_id, status in status_by_order.items()
                if status is OrderStatus.FILLED
                and order_id not in fill_by_order
            )
            if missing_fills:
                raise ReconciliationError(
                    f"filled orders without fills: {missing_fills[:5]}"
                )
            ghost_status_fills = sorted(
                order_id
                for order_id, status in status_by_order.items()
                if status is not OrderStatus.FILLED
                and order_id in fill_by_order
            )
            if ghost_status_fills:
                raise ReconciliationError(
                    "fills attached to non-filled orders: "
                    f"{ghost_status_fills[:5]}"
                )

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
            "orders": len(order_list),
            "fills": len(fills),
            "symbols": sorted(positions),
            "status": "reconciled",
        }


class AuditLogger:
    """Hash-chained immutable execution audit trail.

    BUG-005 hardening: ``log()`` deep-copies the caller's payload and
    ``entries`` returns deep copies — historical records can no longer
    be mutated through caller references or through the returned
    tuple. Entries additionally carry ``timestamp``, ``component``
    and ``event_id`` observability fields (audit timestamps are
    wall-clock BY DESIGN, mirroring the security audit trail FS-21
    convention; they never participate in any Phase 4 identity).

    The chain remains UNKEYED (SHA-256): it is tamper-EVIDENT against
    accidental corruption and in-place rewrites, but a full history
    rewrite with chain recompute can still verify — the keyed-MAC
    custody decision is a registered pending HUMAN decision (pre-paper
    forensic report §5.5) and is deliberately NOT made here.
    """

    def __init__(self) -> None:
        self._entries: list[dict] = []

    def log(
        self, event: str, payload: dict, component: str = "paper.gateway"
    ) -> str:
        """Append one audit event; returns its chain hash.

        ``payload`` is deep-copied on write: later mutation of the
        caller's dict cannot alter the historical record (BUG-005).
        """
        payload_copy = copy.deepcopy(payload) if payload is not None else {}
        timestamp = datetime.now(UTC).isoformat()
        index = len(self._entries)
        event_id = f"evt-{index:06d}-{event}"
        prev = self._entries[-1]["chain_hash"] if self._entries else "0" * 64
        chain_hash = deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "event": event,
                "payload": payload_copy,
                "component": component,
                "event_id": event_id,
                "timestamp": timestamp,
                "prev_chain_hash": prev,
                "index": index,
            }
        )
        self._entries.append(
            {
                "event": event,
                "payload": payload_copy,
                "component": component,
                "event_id": event_id,
                "timestamp": timestamp,
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
                    "component": entry["component"],
                    "event_id": entry["event_id"],
                    "timestamp": entry["timestamp"],
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
        """Deep copies of the entries (BUG-005): read-only by value."""
        return tuple(copy.deepcopy(entry) for entry in self._entries)


class AnalyticsEngine:
    """Deterministic paper analytics over an equity curve.

    BUG-009: non-finite curve points (NaN/inf) fail closed with
    ``ValueError`` — plausible-but-wrong metrics computed over
    silently-skipped NaN points are exactly the failure mode the
    pre-paper forensic forbids.
    """

    @staticmethod
    def _require_finite(values: Sequence[float], name: str) -> None:
        for i, value in enumerate(values):
            if not math.isfinite(value):
                raise ValueError(
                    f"{name}[{i}] is not finite (NaN/inf) — analytics "
                    "fail closed on non-finite equity data (BUG-009)"
                )

    @classmethod
    def total_pnl(cls, equity_curve: Sequence[float]) -> float:
        if len(equity_curve) < 2:
            raise ValueError("equity curve needs >= 2 points")
        cls._require_finite(equity_curve, "equity_curve")
        return equity_curve[-1] - equity_curve[0]

    @classmethod
    def max_drawdown(cls, equity_curve: Sequence[float]) -> float:
        if len(equity_curve) < 2:
            raise ValueError("equity curve needs >= 2 points")
        cls._require_finite(equity_curve, "equity_curve")
        peak = equity_curve[0]
        worst = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                worst = max(worst, (peak - value) / peak)
        return worst

    @classmethod
    def sharpe(cls, returns: Sequence[float], periods_per_year: int = 252) -> float:
        if len(returns) < 2:
            raise ValueError("sharpe needs >= 2 returns")
        cls._require_finite(returns, "returns")
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if variance <= 0:
            raise ValueError("zero-variance returns: sharpe undefined")
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
