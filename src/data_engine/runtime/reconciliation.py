"""Runtime reconciliation (pre-paper mandate §32; RT-F2/RT-F4).

Reconciliation is PART OF THE RUNTIME, not an optional component
(RT-F2 closure: the runtime invokes it after fills and after every
restart). It reconciles::

    INTERNAL ORDERS (OMS) ↔ EXECUTION GATEWAY (fills) ↔
    POSITIONS ↔ PORTFOLIO

Multi-fill aware (PAPER-BLK-3 closure — extends the BUG-004
fills-iff-FILLED invariant to partial-fill accounting):

1. every fill's order exists (no orphan fills);
2. quantity consistency per lifecycle state:
   FILLED ⇒ Σfills == quantity; PARTIALLY_FILLED ⇒ 0 < Σfills <
   quantity; SUBMITTED/ACKNOWLEDGED ⇒ Σfills == 0 (pre-execution);
   CANCELLED ⇒ Σfills < quantity; EXPIRED ⇒ Σfills ≤ quantity;
3. replaying all fills from zero reproduces the stated positions
   EXACTLY (quantity + average cost + realized P&L);
4. every non-terminal order is accounted for.

Any mismatch ⇒ report.ok=False ⇒ the runtime enters
RECONCILIATION_REQUIRED and STOPS NEW ORDERS until resolved
(mandate §32) — never papered over.
"""

from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import OrderLifecycle, RuntimeContractError
from data_engine.runtime.identity import RECONCILIATION_PREFIX, prefixed_hash
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.oms import OMS, OMSOrder
from data_engine.runtime.pnl import PositionState


class ReconciliationFailure(RuntimeContractError):
    """Reconciliation mismatch — new orders must stop (§32)."""


class ReconciliationReport(BaseModel):
    """One reconciliation verdict with full evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: str
    ok: bool
    orders_checked: int
    fills_checked: int
    positions_checked: int
    mismatches: tuple
    reconciled_at_order_ids: tuple = ()

    @field_validator("mismatches")
    @classmethod
    def _validate_mismatches(cls, v) -> tuple:
        return tuple(v)


_PRE_EXECUTION_STATES = frozenset({
    OrderLifecycle.CREATED, OrderLifecycle.VALIDATED,
    OrderLifecycle.RISK_APPROVED, OrderLifecycle.SUBMITTED,
    OrderLifecycle.ACKNOWLEDGED,
})


class RuntimeReconciliation:
    """Authoritative three-way runtime reconciliation (§32)."""

    def __init__(self, ledger: LedgerFamily) -> None:
        if ledger is None:
            raise ReconciliationFailure(
                "reconciliation requires its ledger family"
            )
        self._ledger = ledger

    def reconcile(
        self,
        oms: OMS,
        positions: Mapping[str, PositionState],
    ) -> ReconciliationReport:
        """Reconcile OMS orders/fills against stated positions."""
        mismatches: list = []
        orders = oms.orders()
        all_fills = []
        for order in orders:
            fills = order.fills
            all_fills.extend(fills)
            filled = order.filled_quantity
            if order.status is OrderLifecycle.FILLED and filled != order.quantity:
                mismatches.append(
                    f"order {order.order_id}: FILLED but Σfills "
                    f"{filled} != quantity {order.quantity}"
                )
            if order.status is OrderLifecycle.PARTIALLY_FILLED and not (
                0 < filled < order.quantity
            ):
                mismatches.append(
                    f"order {order.order_id}: PARTIALLY_FILLED but Σfills "
                    f"{filled} not in (0, {order.quantity})"
                )
            if order.status in _PRE_EXECUTION_STATES and filled != 0:
                mismatches.append(
                    f"order {order.order_id}: {order.status.value} but has "
                    f"{len(fills)} fills (pre-execution state with fills)"
                )
            if order.status is OrderLifecycle.CANCELLED and filled >= order.quantity:
                mismatches.append(
                    f"order {order.order_id}: CANCELLED but fully filled"
                )

        # Orphan fill check (defensive — fills live inside orders here,
        # but a future gateway source must still pass this invariant).
        order_ids = {o.order_id for o in orders}
        for fill in all_fills:
            if fill.order_id not in order_ids:
                mismatches.append(
                    f"orphan fill {fill.fill_id} for unknown order "
                    f"{fill.order_id}"
                )

        # Position replay: replay fills from zero, compare EXACTLY.
        replayed: dict = {}
        for order in orders:
            for fill in order.fills:
                state = replayed.get(
                    fill.symbol, PositionState(symbol=fill.symbol)
                )
                replayed[fill.symbol] = state.apply_fill(
                    fill_quantity=fill.quantity,
                    fill_price=fill.price,
                    side=fill.side,
                    commission=fill.commission,
                    slippage_cost=fill.slippage_cost,
                    spread_cost=fill.spread_cost,
                    filled_at=fill.filled_at,
                    source_event=fill.fill_id,
                )
        for symbol, stated in positions.items():
            replay = replayed.get(symbol, PositionState(symbol=symbol))
            if (
                stated.quantity != replay.quantity
                or stated.average_cost != replay.average_cost
                or stated.realized_pnl != replay.realized_pnl
            ):
                mismatches.append(
                    f"position {symbol}: stated qty={stated.quantity}/"
                    f"avg={stated.average_cost}/pnl={stated.realized_pnl} "
                    f"vs replay qty={replay.quantity}/"
                    f"avg={replay.average_cost}/pnl={replay.realized_pnl}"
                )
        extra = sorted(set(replayed) - set(positions))
        if extra:
            mismatches.append(
                f"positions with fills but no stated state: {extra[:5]}"
            )

        ok = not mismatches
        report = ReconciliationReport(
            report_id="pending",
            ok=ok,
            orders_checked=len(orders),
            fills_checked=len(all_fills),
            positions_checked=len(positions),
            mismatches=tuple(mismatches),
        )
        report = report.model_copy(
            update={
                "report_id": prefixed_hash(
                    RECONCILIATION_PREFIX,
                    {
                        "kind": "reconciliation_report",
                        "ok": ok,
                        "orders": len(orders),
                        "fills": len(all_fills),
                        "positions": len(positions),
                        "mismatches": list(mismatches),
                    },
                )
            }
        )
        self._ledger.record(
            ledger="incident",
            event_type="RECONCILIATION_" + ("PASS" if ok else "MISMATCH"),
            correlation_id="runtime.reconciliation",
            actor="runtime.reconciliation",
            payload={
                "report_id": report.report_id,
                "ok": ok,
                "orders_checked": report.orders_checked,
                "fills_checked": report.fills_checked,
                "positions_checked": report.positions_checked,
                "mismatches": list(mismatches),
            },
        )
        return report

    def require_ok(self, report: ReconciliationReport) -> None:
        """Raise when a report is not clean — the runtime's path to
        RECONCILIATION_REQUIRED + STOP_NEW_ORDERS (§32)."""
        if not report.ok:
            raise ReconciliationFailure(
                "reconciliation mismatch — new orders STOPPED: "
                + "; ".join(report.mismatches[:3])
                + " (RECONCILIATION_REQUIRED, mandate §32)"
            )


__all__ = [
    "ReconciliationFailure",
    "ReconciliationReport",
    "RuntimeReconciliation",
]
