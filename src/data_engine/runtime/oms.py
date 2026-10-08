"""Authoritative Order Management System (pre-paper mandate §27–§30,
§39, §28).

State machine (mandate §27 — CLOSED set, no skips)::

    CREATED → VALIDATED → RISK_APPROVED → SUBMITTED → ACKNOWLEDGED
        → PARTIALLY_FILLED ⇄ (more fills) → FILLED
    SUBMITTED/ACKNOWLEDGED/PARTIALLY_FILLED → CANCEL_PENDING → CANCELLED
    live states → EXPIRED (TTL) / UNKNOWN (ambiguous) → RECONCILING
        → FILLED / CANCELLED / FAILED
    CREATED/VALIDATED/RISK_APPROVED → REJECTED / FAILED

Guarantees:

- **No decision-to-filled jump**: CREATED cannot reach FILLED/PARTIALLY_FILLED
  — an order must pass validation, risk approval, submission, and at
  least one real fill (tests pin this).
- **Idempotent order identity (§28)**: the order id is a deterministic
  hash of governed fields (session + plan + decision + correlation +
  symbol + side + type + quantity + limit). A retry with the same
  intent returns the EXISTING order — never a duplicate.
- **Ambiguous-result protection (§28)**: submitting an order in
  UNKNOWN/RECONCILING raises :class:`AmbiguousOrderError` — the ONLY
  legal path is reconciliation first, retry after.
- **Partial fills (§30)**: fills accumulate with running
  filled/remaining/average-price; cancel-after-partial cancels only
  the remainder; every transition ledgered.
- **TTL (§39)**: ``expire_if_elapsed`` moves live orders to EXPIRED
  with the ledger record.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.contracts import (
    OrderLifecycle,
    RuntimeContractError,
    TradePlan,
)
from data_engine.runtime.identity import ORDER_PREFIX, prefixed_hash
from data_engine.runtime.execution import RuntimeFill
from data_engine.runtime.ledgers import LedgerFamily

#: Authoritative transition table (mandate §27).
TRANSITIONS: dict = {
    OrderLifecycle.CREATED: frozenset({
        OrderLifecycle.VALIDATED, OrderLifecycle.REJECTED,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.VALIDATED: frozenset({
        OrderLifecycle.RISK_APPROVED, OrderLifecycle.REJECTED,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.RISK_APPROVED: frozenset({
        OrderLifecycle.SUBMITTED, OrderLifecycle.REJECTED,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.SUBMITTED: frozenset({
        OrderLifecycle.ACKNOWLEDGED, OrderLifecycle.PARTIALLY_FILLED,
        OrderLifecycle.FILLED, OrderLifecycle.CANCEL_PENDING,
        OrderLifecycle.REJECTED, OrderLifecycle.EXPIRED,
        OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.ACKNOWLEDGED: frozenset({
        OrderLifecycle.PARTIALLY_FILLED, OrderLifecycle.FILLED,
        OrderLifecycle.CANCEL_PENDING, OrderLifecycle.EXPIRED,
        OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.PARTIALLY_FILLED: frozenset({
        OrderLifecycle.PARTIALLY_FILLED, OrderLifecycle.FILLED,
        OrderLifecycle.CANCEL_PENDING, OrderLifecycle.UNKNOWN,
        OrderLifecycle.RECONCILING, OrderLifecycle.FAILED,
    }),
    OrderLifecycle.CANCEL_PENDING: frozenset({
        OrderLifecycle.CANCELLED, OrderLifecycle.PARTIALLY_FILLED,
        OrderLifecycle.FILLED, OrderLifecycle.UNKNOWN,
        OrderLifecycle.FAILED,
    }),
    OrderLifecycle.UNKNOWN: frozenset({
        OrderLifecycle.RECONCILING, OrderLifecycle.FAILED,
    }),
    OrderLifecycle.RECONCILING: frozenset({
        OrderLifecycle.FILLED, OrderLifecycle.PARTIALLY_FILLED,
        OrderLifecycle.CANCELLED, OrderLifecycle.FAILED,
        OrderLifecycle.SUBMITTED,
    }),
    # Terminal states:
    OrderLifecycle.FILLED: frozenset(),
    OrderLifecycle.CANCELLED: frozenset(),
    OrderLifecycle.REJECTED: frozenset(),
    OrderLifecycle.EXPIRED: frozenset(),
    OrderLifecycle.FAILED: frozenset(),
}

#: States in which an order is still live (TTL/cancel applicable).
LIVE_STATES = frozenset({
    OrderLifecycle.SUBMITTED, OrderLifecycle.ACKNOWLEDGED,
    OrderLifecycle.PARTIALLY_FILLED, OrderLifecycle.CANCEL_PENDING,
})

#: Ambiguous states — retry is forbidden until reconciled (§28).
AMBIGUOUS_STATES = frozenset({
    OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
})


class OMSError(RuntimeContractError):
    """Raised on OMS contract violations."""


class InvalidTransitionError(OMSError):
    """A requested state jump is not in the authoritative machine."""


class AmbiguousOrderError(OMSError):
    """Retry on an ambiguous order — reconcile first (mandate §28)."""


def idempotent_order_id(
    session_id: str,
    trade_plan_id: str,
    decision_id: str,
    correlation_id: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    limit_price: Optional[Decimal],
) -> str:
    """Deterministic order identity from governed fields (§28).

    Same intent (same session, plan, decision, order parameters) ⇒
    same id ⇒ duplicate submissions are structurally detected.
    """
    return prefixed_hash(
        ORDER_PREFIX,
        {
            "kind": "idempotent_order_id",
            "session_id": session_id,
            "trade_plan_id": trade_plan_id,
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "symbol": symbol.strip().upper(),
            "side": side.strip().upper(),
            "order_type": order_type.strip().upper(),
            "quantity": str(quantity),
            "limit_price": str(limit_price) if limit_price is not None else None,
        },
    )


class OMSOrder(BaseModel):
    """One order's authoritative lifecycle record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    session_id: str
    trade_plan_id: str
    decision_id: str
    correlation_id: str
    symbol: str
    side: str  # BUY / SELL
    order_type: str  # MARKET / LIMIT
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    created_at: datetime
    status: OrderLifecycle = OrderLifecycle.CREATED
    fills: Tuple[RuntimeFill, ...] = ()
    rejection_reason: Optional[str] = None
    ttl_bars: Optional[int] = None
    submitted_at_bar: Optional[int] = None
    submitted_at: Optional[datetime] = None

    @field_validator("order_id", "session_id", "trade_plan_id",
                     "decision_id", "correlation_id", "symbol", "side",
                     "order_type")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise OMSError("order text fields must be non-empty")
        return v.strip()

    @field_validator("side")
    @classmethod
    def _validate_side(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("BUY", "SELL"):
            raise OMSError("order side must be BUY or SELL")
        return v

    @field_validator("order_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("MARKET", "LIMIT"):
            raise OMSError("order type must be MARKET or LIMIT")
        return v

    @field_validator("quantity")
    @classmethod
    def _validate_quantity(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise OMSError("quantity must be a positive finite Decimal")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise OMSError("created_at must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_limit_presence(self) -> "OMSOrder":
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise OMSError("LIMIT orders require a limit_price")
        return self

    @property
    def filled_quantity(self) -> Decimal:
        return sum((f.quantity for f in self.fills), Decimal("0"))

    @property
    def remaining_quantity(self) -> Decimal:
        return self.quantity - self.filled_quantity

    @property
    def average_fill_price(self) -> Optional[Decimal]:
        """Volume-weighted average fill price (None before any fill)."""
        if not self.fills:
            return None
        notional = sum((f.quantity * f.price for f in self.fills), Decimal("0"))
        return notional / self.filled_quantity

    @property
    def total_fees(self) -> Decimal:
        return sum(
            (f.commission + f.slippage_cost + f.spread_cost for f in self.fills),
            Decimal("0"),
        )

    @property
    def is_terminal(self) -> bool:
        return not TRANSITIONS[self.status]


class OMS:
    """The ONE authoritative order management system (mandate §27)."""

    def __init__(self, ledger: LedgerFamily) -> None:
        if ledger is None:
            raise OMSError("OMS requires its ledger family (no unledgered orders)")
        self._ledger = ledger
        self._orders: dict = {}
        self._idempotency: dict = {}

    # ------------------------------------------------------------------
    # Creation + idempotency (§28)
    # ------------------------------------------------------------------
    def create_order(
        self,
        plan: TradePlan,
        session_id: str,
        created_at: datetime,
        ttl_bars: Optional[int] = None,
    ) -> Tuple[OMSOrder, bool]:
        """Create an order from an approved trade plan.

        Returns ``(order, created)``. A duplicate intent (same
        idempotency key) returns the EXISTING order with
        ``created=False`` — retries are idempotent, never duplicated.
        """
        order_id = idempotent_order_id(
            session_id=session_id,
            trade_plan_id=plan.trade_plan_id,
            decision_id=plan.decision_id,
            correlation_id=plan.correlation_id,
            symbol=plan.symbol,
            side=plan.side.value,
            order_type=plan.entry.order_type,
            quantity=plan.quantity,
            limit_price=plan.entry.limit_price,
        )
        existing = self._idempotency.get(order_id)
        if existing is not None:
            return self._orders[existing], False
        order = OMSOrder(
            order_id=order_id,
            session_id=session_id,
            trade_plan_id=plan.trade_plan_id,
            decision_id=plan.decision_id,
            correlation_id=plan.correlation_id,
            symbol=plan.symbol,
            side=plan.side.value,
            order_type=plan.entry.order_type,
            quantity=plan.quantity,
            limit_price=plan.entry.limit_price,
            created_at=created_at,
            ttl_bars=ttl_bars,
        )
        self._orders[order_id] = order
        self._idempotency[order_id] = order_id
        self._ledger.record(
            ledger="order",
            event_type="ORDER_CREATED",
            correlation_id=plan.correlation_id,
            actor="runtime.oms",
            payload={
                "order_id": order_id,
                "trade_plan_id": plan.trade_plan_id,
                "decision_id": plan.decision_id,
                "symbol": plan.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": str(plan.quantity),
                "limit_price": str(plan.entry.limit_price)
                if plan.entry.limit_price is not None
                else None,
                "ttl_bars": ttl_bars,
            },
            parent_id=plan.trade_plan_id,
        )
        return order, True

    # ------------------------------------------------------------------
    # State machine core
    # ------------------------------------------------------------------
    def _transition(
        self,
        order_id: str,
        new_status: OrderLifecycle,
        event_type: str,
        payload: Optional[Mapping[str, Any]] = None,
    ) -> OMSOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise OMSError(f"unknown order {order_id!r}")
        if new_status not in TRANSITIONS[order.status]:
            raise InvalidTransitionError(
                f"order {order_id} cannot transition "
                f"{order.status.value} → {new_status.value} "
                "(authoritative state machine, mandate §27)"
            )
        updated = order.model_copy(update={"status": new_status})
        self._orders[order_id] = updated
        body = {"order_id": order_id, "from": order.status.value,
                "to": new_status.value}
        if payload:
            body.update(payload)
        self._ledger.record(
            ledger="order",
            event_type=event_type,
            correlation_id=order.correlation_id,
            actor="runtime.oms",
            payload=body,
            parent_id=order.trade_plan_id,
        )
        return updated

    def validate_order(self, order_id: str) -> OMSOrder:
        """Contract validation: CREATED → VALIDATED (or REJECTED)."""
        order = self._require(order_id)
        if order.order_type == "LIMIT":
            if order.limit_price is None or order.limit_price <= 0:
                return self.reject_order(order_id, "limit price missing/invalid")
        if order.quantity <= 0:
            return self.reject_order(order_id, "quantity not positive")
        return self._transition(order_id, OrderLifecycle.VALIDATED,
                                "ORDER_VALIDATED")

    def risk_approve(
        self,
        order_id: str,
        assessment=None,
    ) -> OMSOrder:
        """Record risk approval — ONLY with a PASSING assessment whose
        order fingerprint matches THIS order exactly (mandate §25:
        no component may bypass the RiskEngine; the OMS refuses
        approval without gate evidence — RT-F1 structural closure)."""
        order = self._require(order_id)
        if assessment is None:
            raise OMSError(
                "risk approval requires the RiskAssessment object — "
                "assessments are structural, never verbal (mandate §25)"
            )
        if not getattr(assessment, "passed", False):
            failed = [
                getattr(c, "check", str(c))
                for c in getattr(assessment, "failed_checks", ())
            ]
            raise OMSError(
                f"risk approval REFUSED: assessment "
                f"{getattr(assessment, 'assessment_id', '?')} did not pass "
                f"({failed})"
            )
        fingerprint = assessment.order_fingerprint
        matches = (
            fingerprint["trade_plan_id"] == order.trade_plan_id
            and fingerprint["symbol"] == order.symbol
            and fingerprint["side"] == order.side
            and fingerprint["quantity"] == str(order.quantity)
            and fingerprint["order_type"] == order.order_type
            and (fingerprint["limit_price"] == (
                str(order.limit_price) if order.limit_price is not None else None
            ))
        )
        if not matches:
            raise OMSError(
                "risk approval REFUSED: assessment fingerprint does not "
                "match this order (stale/foreign assessments are invalid)"
            )
        return self._transition(order_id, OrderLifecycle.RISK_APPROVED,
                                "ORDER_RISK_APPROVED",
                                payload={"assessment_id": assessment.assessment_id})

    def reject_order(self, order_id: str, reason: str) -> OMSOrder:
        order = self._require(order_id)
        return self._transition(
            order_id, OrderLifecycle.REJECTED, "ORDER_REJECTED",
            payload={"reason": reason},
        )

    def submit(
        self,
        order_id: str,
        submitted_at: datetime,
        bar_index: int,
    ) -> OMSOrder:
        """Submit to the execution gateway: RISK_APPROVED → SUBMITTED.

        Ambiguous orders (UNKNOWN/RECONCILING) are REFUSED —
        reconciliation must resolve them first (mandate §28).
        """
        order = self._require(order_id)
        if order.status in AMBIGUOUS_STATES:
            raise AmbiguousOrderError(
                f"order {order_id} is {order.status.value} — retry is "
                "forbidden until reconciliation resolves the prior "
                "outcome (mandate §28)"
            )
        updated = self._transition(order_id, OrderLifecycle.SUBMITTED,
                                   "ORDER_SUBMITTED")
        updated = updated.model_copy(
            update={
                "submitted_at": submitted_at,
                "submitted_at_bar": bar_index,
            }
        )
        self._orders[order_id] = updated
        return updated

    def acknowledge(self, order_id: str) -> OMSOrder:
        return self._transition(order_id, OrderLifecycle.ACKNOWLEDGED,
                                "ORDER_ACKNOWLEDGED")

    # ------------------------------------------------------------------
    # Partial fills (§30)
    # ------------------------------------------------------------------
    def apply_fill(self, order_id: str, fill: RuntimeFill) -> OMSOrder:
        """Apply one (possibly partial) fill; updates the fill list,
        filled/remaining/average price, and the lifecycle state."""
        order = self._require(order_id)
        if fill.order_id != order_id:
            raise OMSError(
                f"fill {fill.fill_id} belongs to order {fill.order_id!r}, "
                f"not {order_id!r}"
            )
        if order.status not in (
            OrderLifecycle.SUBMITTED, OrderLifecycle.ACKNOWLEDGED,
            OrderLifecycle.PARTIALLY_FILLED, OrderLifecycle.RECONCILING,
        ):
            raise OMSError(
                f"order {order_id} is {order.status.value} — cannot "
                "accept fills in this state"
            )
        if fill.quantity > order.remaining_quantity:
            raise OMSError(
                f"fill {fill.fill_id} quantity {fill.quantity} exceeds "
                f"remaining {order.remaining_quantity} (overfill refused)"
            )
        new_fills = order.fills + (fill,)
        new_filled = order.filled_quantity + fill.quantity
        new_status = (
            OrderLifecycle.FILLED if new_filled == order.quantity
            else OrderLifecycle.PARTIALLY_FILLED
        )
        event = (
            "ORDER_FILLED" if new_status is OrderLifecycle.FILLED
            else "ORDER_PARTIAL_FILL"
        )
        updated = order.model_copy(
            update={"fills": new_fills, "status": new_status}
        )
        self._orders[order_id] = updated
        self._ledger.record(
            ledger="fill",
            event_type=event,
            correlation_id=order.correlation_id,
            actor="runtime.oms",
            payload={
                "order_id": order_id,
                "fill_id": fill.fill_id,
                "fill_index": fill.fill_index,
                "fill_quantity": str(fill.quantity),
                "fill_price": str(fill.price),
                "filled_quantity": str(new_filled),
                "remaining_quantity": str(order.quantity - new_filled),
                "average_fill_price": str(updated.average_fill_price),
                "fees": str(fill.commission + fill.slippage_cost + fill.spread_cost),
            },
            parent_id=order_id,
        )
        self._ledger.record(
            ledger="order",
            event_type=event,
            correlation_id=order.correlation_id,
            actor="runtime.oms",
            payload={"order_id": order_id, "status": new_status.value},
            parent_id=order.trade_plan_id,
        )
        return updated

    # ------------------------------------------------------------------
    # Cancellation / TTL / ambiguity (§28/§39)
    # ------------------------------------------------------------------
    def request_cancel(self, order_id: str) -> OMSOrder:
        return self._transition(order_id, OrderLifecycle.CANCEL_PENDING,
                                "ORDER_CANCEL_REQUESTED")

    def finalize_cancel(self, order_id: str) -> OMSOrder:
        """Cancel: any unfilled remainder is cancelled (cancel-after-
        partial is a distinct, ledgered event)."""
        order = self._require(order_id)
        event = (
            "ORDER_CANCELLED_AFTER_PARTIAL"
            if order.filled_quantity > 0
            else "ORDER_CANCELLED"
        )
        return self._transition(
            order_id, OrderLifecycle.CANCELLED, event,
            payload={
                "filled_quantity": str(order.filled_quantity),
                "cancelled_quantity": str(order.remaining_quantity),
            },
        )

    def expire_if_elapsed(self, order_id: str, current_bar_index: int) -> Optional[OMSOrder]:
        """TTL enforcement (§39): live orders past their TTL → EXPIRED."""
        order = self._require(order_id)
        if order.status not in (
            OrderLifecycle.SUBMITTED, OrderLifecycle.ACKNOWLEDGED,
            OrderLifecycle.PARTIALLY_FILLED,
        ):
            return None
        if order.ttl_bars is None or order.submitted_at_bar is None:
            return None
        expiry_bar = order.submitted_at_bar + order.ttl_bars
        if current_bar_index > expiry_bar:
            return self._transition(
                order_id, OrderLifecycle.EXPIRED, "ORDER_EXPIRED",
                payload={
                    "ttl_bars": order.ttl_bars,
                    "submitted_at_bar": order.submitted_at_bar,
                    "current_bar_index": current_bar_index,
                    "filled_quantity": str(order.filled_quantity),
                    "expired_quantity": str(order.remaining_quantity),
                },
            )
        return None

    def mark_unknown(self, order_id: str, reason: str) -> OMSOrder:
        return self._transition(
            order_id, OrderLifecycle.UNKNOWN, "ORDER_UNKNOWN",
            payload={"reason": reason},
        )

    def start_reconciling(self, order_id: str) -> OMSOrder:
        return self._transition(order_id, OrderLifecycle.RECONCILING,
                                "ORDER_RECONCILING")

    def resolve_reconciling(
        self, order_id: str, resolved: OrderLifecycle
    ) -> OMSOrder:
        """Resolve an ambiguous order post-reconciliation (terminal or
        re-submitted)."""
        order = self._require(order_id)
        if order.status is not OrderLifecycle.RECONCILING:
            raise OMSError(
                f"order {order_id} is {order.status.value} — only "
                "RECONCILING orders can be resolved"
            )
        if resolved not in TRANSITIONS[OrderLifecycle.RECONCILING]:
            raise InvalidTransitionError(
                f"{resolved.value} is not a reconciliation resolution"
            )
        return self._transition(
            order_id, resolved, f"ORDER_RECONCILED_{resolved.value}"
        )

    # ------------------------------------------------------------------
    # Access + persistence bridge
    # ------------------------------------------------------------------
    @property
    def ledgers(self) -> LedgerFamily:
        """The OMS ledger family (order/fill event chains)."""
        return self._ledger

    def _require(self, order_id: str) -> OMSOrder:
        order = self._orders.get(order_id)
        if order is None:
            raise OMSError(f"unknown order {order_id!r}")
        return order

    def order(self, order_id: str) -> OMSOrder:
        return self._require(order_id)

    def orders(self) -> Tuple[OMSOrder, ...]:
        return tuple(self._orders.values())

    def live_orders(self) -> Tuple[OMSOrder, ...]:
        return tuple(o for o in self._orders.values() if o.status in LIVE_STATES)

    def export_state(self) -> list:
        """Serializable order records for the persistence snapshot."""
        return [o.model_dump(mode="json") for o in self._orders.values()]

    def restore_state(self, records: Sequence[Mapping[str, Any]]) -> int:
        """Restore orders after restart; rebuilds the idempotency map.
        Returns the number of restored orders."""
        restored = 0
        for record in records:
            order = OMSOrder.model_validate(record)
            self._orders[order.order_id] = order
            self._idempotency[order.order_id] = order.order_id
            restored += 1
        return restored


__all__ = [
    "TRANSITIONS",
    "LIVE_STATES",
    "AMBIGUOUS_STATES",
    "OMSError",
    "InvalidTransitionError",
    "AmbiguousOrderError",
    "idempotent_order_id",
    "OMSOrder",
    "OMS",
]
