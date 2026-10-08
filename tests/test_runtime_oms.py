"""OMS state machine tests (pre-paper mandate §27–§30, §39).

Coverage: full lifecycle transitions, no decision→filled jump,
idempotent order identity, ambiguous-order retry protection,
partial-fill accounting (20+30+50=100), cancel-after-partial,
TTL expiry, overfill refusal.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    OrderLifecycle,
    UncertaintyReport,
)
from data_engine.runtime.execution import RuntimeFill, PaperExecutionAdapter
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.oms import (
    AmbiguousOrderError,
    InvalidTransitionError,
    OMS,
    OMSOrder,
    idempotent_order_id,
)
from data_engine.paper.simulator import ExecutionRealism

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
UNC = UncertaintyReport(confidence=0.7, entropy=0.4, ensemble_disagreement=0.05)


def _plan(qty="100", side=DecisionAction.BUY, plan_id="tp-1", corr="c-1"):
    from data_engine.runtime.contracts import TradePlan
    return TradePlan(
        trade_plan_id=plan_id,
        decision_id="d-1",
        symbol="TEST/USD",
        side=side,
        quantity=Decimal(qty),
        notional=Decimal(qty) * Decimal("100"),
        entry=EntryConstraints(order_type="MARKET", time_in_force="GTC"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("110"),
        risk_budget=Decimal("500"),
        expected_return=0.01,
        risk_reward_ratio=2.0,
        uncertainty=UNC,
        crash_risk={"probability": 0.05},
        model_context={"model": "L@1"},
        correlation_id=corr,
    )


def _fill(order_id, qty, price="100", idx=0, bar=0, side="BUY"):
    return RuntimeFill(
        fill_id="pending",
        order_id=order_id,
        symbol="TEST/USD",
        side=side,
        quantity=Decimal(qty),
        price=Decimal(price),
        commission=Decimal("0.1"),
        slippage_cost=Decimal("0.05"),
        spread_cost=Decimal("0.02"),
        filled_at=T0 + timedelta(minutes=5 * (bar + 1)),
        fill_index=idx,
        bar_index=bar,
    )


def _fingerprinting_assessment(order, passed=True):
    """A minimal duck-typed assessment matching the OMS contract."""
    class A:
        def __init__(self, passed, order):
            self.passed = passed
            self.assessment_id = "rtrg.test"
            self.failed_checks = () if passed else ("paper_mode",)
            self.order_fingerprint = {
                "trade_plan_id": order.trade_plan_id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": str(order.quantity),
                "order_type": order.order_type,
                "limit_price": str(order.limit_price)
                if order.limit_price is not None else None,
            }
    return A(passed, order)


def _submitted_order(oms, plan=None, ttl=3):
    plan = plan or _plan()
    order, _ = oms.create_order(plan, "sess-1", T0, ttl_bars=ttl)
    oms.validate_order(order.order_id)
    oms.risk_approve(order.order_id, _fingerprinting_assessment(order))
    oms.submit(order.order_id, T0, bar_index=10)
    oms.acknowledge(order.order_id)
    return oms.order(order.order_id)


class TestStateMachine:
    def test_full_lifecycle_created_to_filled(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        assert order.status is OrderLifecycle.ACKNOWLEDGED
        oms.apply_fill(order.order_id, _fill(order.order_id, "100"))
        assert oms.order(order.order_id).status is OrderLifecycle.FILLED

    def test_no_decision_to_filled_jump(self):
        """CREATED orders cannot accept fills — the machine forces
        validate → risk-approve → submit before any fill exists."""
        oms = OMS(LedgerFamily())
        plan = _plan()
        order, _ = oms.create_order(plan, "sess-1", T0)
        with pytest.raises(Exception, match="cannot accept fills"):
            oms.apply_fill(order.order_id, _fill(order.order_id, "100"))

    def test_invalid_transitions_rejected(self):
        oms = OMS(LedgerFamily())
        plan = _plan()
        order, _ = oms.create_order(plan, "sess-1", T0)
        # CREATED → FILLED / SUBMITTED / CANCELLED are all illegal.
        for bad in (OrderLifecycle.FILLED, OrderLifecycle.SUBMITTED,
                    OrderLifecycle.CANCELLED):
            with pytest.raises(InvalidTransitionError):
                oms._transition(order.order_id, bad, "TEST")

    def test_reject_from_created(self):
        oms = OMS(LedgerFamily())
        plan = _plan()
        order, _ = oms.create_order(plan, "sess-1", T0)
        oms.reject_order(order.order_id, "validation failure")
        assert oms.order(order.order_id).status is OrderLifecycle.REJECTED

    def test_terminal_states_absorb_no_transitions(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oms.apply_fill(order.order_id, _fill(order.order_id, "100"))
        with pytest.raises(InvalidTransitionError):
            oms._transition(order.order_id, OrderLifecycle.SUBMITTED,
                            "TEST")


class TestIdempotency:
    def test_same_intent_same_order_id(self):
        a = idempotent_order_id(
            session_id="s", trade_plan_id="tp", decision_id="d",
            correlation_id="c", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("10"),
            limit_price=None,
        )
        b = idempotent_order_id(
            session_id="s", trade_plan_id="tp", decision_id="d",
            correlation_id="c", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("10"),
            limit_price=None,
        )
        assert a == b and a.startswith("rtord.")

    def test_different_quantity_different_id(self):
        a = idempotent_order_id("s", "tp", "d", "c", "T/USD", "BUY",
                                "MARKET", Decimal("10"), None)
        b = idempotent_order_id("s", "tp", "d", "c", "T/USD", "BUY",
                                "MARKET", Decimal("11"), None)
        assert a != b

    def test_duplicate_create_returns_existing(self):
        oms = OMS(LedgerFamily())
        plan = _plan()
        o1, created1 = oms.create_order(plan, "sess-1", T0)
        o2, created2 = oms.create_order(plan, "sess-1", T0)
        assert created1 and not created2
        assert o1.order_id == o2.order_id
        assert len(oms.orders()) == 1


class TestPartialFills:
    def test_partial_fill_lifecycle_20_30_50(self):
        """Mandate §30 exact example: 100 = 20 + 30 + 50."""
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oid = order.order_id
        o1 = oms.apply_fill(oid, _fill(oid, "20", idx=0, bar=1))
        assert o1.status is OrderLifecycle.PARTIALLY_FILLED
        assert o1.filled_quantity == Decimal("20")
        assert o1.remaining_quantity == Decimal("80")
        o2 = oms.apply_fill(oid, _fill(oid, "30", idx=1, bar=2))
        assert o2.status is OrderLifecycle.PARTIALLY_FILLED
        assert o2.filled_quantity == Decimal("50")
        o3 = oms.apply_fill(oid, _fill(oid, "50", idx=2, bar=3))
        assert o3.status is OrderLifecycle.FILLED
        assert o3.filled_quantity == Decimal("100")
        assert o3.remaining_quantity == Decimal("0")

    def test_average_price_weighted(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oid = order.order_id
        oms.apply_fill(oid, _fill(oid, "20", price="100", idx=0, bar=1))
        oms.apply_fill(oid, _fill(oid, "30", price="110", idx=1, bar=2))
        o = oms.order(oid)
        assert o.average_fill_price == (Decimal(20) * Decimal(100)
                                        + Decimal(30) * Decimal(110)) / Decimal(50)

    def test_overfill_refused(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oid = order.order_id
        oms.apply_fill(oid, _fill(oid, "80", idx=0, bar=1))
        with pytest.raises(Exception, match="overfill"):
            oms.apply_fill(oid, _fill(oid, "30", idx=1, bar=2))

    def test_fill_for_wrong_order_refused(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        with pytest.raises(Exception, match="belongs to order"):
            oms.apply_fill(order.order_id, _fill("other-order", "10"))

    def test_cancel_after_partial(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oid = order.order_id
        oms.apply_fill(oid, _fill(oid, "40", idx=0, bar=1))
        oms.request_cancel(oid)
        oms.finalize_cancel(oid)
        final = oms.order(oid)
        assert final.status is OrderLifecycle.CANCELLED
        assert final.filled_quantity == Decimal("40")
        assert final.remaining_quantity == Decimal("60")

    def test_fill_events_ledgered(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oid = order.order_id
        oms.apply_fill(oid, _fill(oid, "20", idx=0, bar=1))
        oms.apply_fill(oid, _fill(oid, "30", idx=1, bar=2))
        events = [e.event_type for e in oms.ledgers.events("fill")]
        assert events.count("ORDER_PARTIAL_FILL") == 2
        assert "ORDER_FILLED" not in events


class TestTTLAndAmbiguity:
    def test_ttl_expiry(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms, ttl=2)  # submitted at bar 10
        expired = oms.expire_if_elapsed(order.order_id, 13)  # 13 > 12
        assert expired is not None
        assert expired.status is OrderLifecycle.EXPIRED
        # expiry is ledgered
        events = [e.event_type for e in oms.ledgers.events("order")]
        assert "ORDER_EXPIRED" in events

    def test_ttl_not_yet_elapsed_no_expiry(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms, ttl=3)
        assert oms.expire_if_elapsed(order.order_id, 12) is None

    def test_ambiguous_retry_refused(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oms.mark_unknown(order.order_id, "gateway timeout")
        with pytest.raises(AmbiguousOrderError, match="reconcil"):
            oms.submit(order.order_id, T0, bar_index=99)

    def test_reconciliation_resolution_allows_resubmission(self):
        oms = OMS(LedgerFamily())
        plan = _plan(plan_id="tp-2", corr="c-2")
        order, _ = oms.create_order(plan, "sess-1", T0)
        oms.validate_order(order.order_id)
        oms.risk_approve(order.order_id, _fingerprinting_assessment(order))
        oms.submit(order.order_id, T0, bar_index=10)
        oms.mark_unknown(order.order_id, "timeout")
        oms.start_reconciling(order.order_id)
        resolved = oms.resolve_reconciling(
            order.order_id, OrderLifecycle.CANCELLED
        )
        assert resolved.status is OrderLifecycle.CANCELLED

    def test_risk_approval_requires_passing_assessment(self):
        oms = OMS(LedgerFamily())
        plan = _plan()
        order, _ = oms.create_order(plan, "sess-1", T0)
        oms.validate_order(order.order_id)
        with pytest.raises(Exception, match="did not pass"):
            oms.risk_approve(order.order_id, _fingerprinting_assessment(order, passed=False))
        with pytest.raises(Exception, match="structural"):
            oms.risk_approve(order.order_id, None)

    def test_risk_approval_fingerprint_mismatch_refused(self):
        oms = OMS(LedgerFamily())
        order, _ = oms.create_order(_plan(), "sess-1", T0)
        oms.validate_order(order.order_id)
        other = OMSOrder(
            order_id="rtord.other", session_id="s", trade_plan_id="OTHER",
            decision_id="d", correlation_id="c", symbol="TEST/USD",
            side="SELL", order_type="MARKET", quantity=Decimal("999"),
            created_at=T0,
        )
        with pytest.raises(Exception, match="fingerprint"):
            oms.risk_approve(order.order_id,
                             _fingerprinting_assessment(other))

    def test_state_export_restore(self):
        oms = OMS(LedgerFamily())
        order = _submitted_order(oms)
        oms.apply_fill(order.order_id, _fill(order.order_id, "100"))
        state = oms.export_state()
        oms2 = OMS(LedgerFamily())
        assert oms2.restore_state(state) == 1
        restored = oms2.order(order.order_id)
        assert restored.status is OrderLifecycle.FILLED
        assert restored.filled_quantity == Decimal("100")


class TestExecutionAdapter:
    REALISM = ExecutionRealism(
        half_spread=Decimal("0.05"), commission_per_unit=Decimal("0.001"),
        impact_rate=Decimal("0.0001"), participation_cap=Decimal("0.35"),
        fill_lag_bars=1,
    )

    def _bars(self, n=8, volume=100.0):
        bars = []
        price = 100.0
        for i in range(n):
            o = price
            c = price + 0.2
            bars.append({
                "timestamp": T0 + timedelta(minutes=5 * i),
                "open": o, "high": max(o, c) + 0.1,
                "low": min(o, c) - 0.1, "close": c,
                "volume": volume,
            })
            price = c
        return bars

    def test_market_order_fills_after_latency(self):
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars()
        fills = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("10"), bars=bars,
            submitted_at=bars[0]["timestamp"],
        )
        assert len(fills) == 1
        assert fills[0].bar_index == 1
        # adverse stack: price >= open + half_spread
        assert fills[0].price >= Decimal(str(bars[1]["open"])) + Decimal("0.05")

    def test_partial_fills_across_bars(self):
        """Volume-limited bars force partial fills spilling to later bars."""
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars(n=6, volume=20.0)  # capacity 0.35*20 = 7/bar
        fills = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("20"), bars=bars,
            submitted_at=bars[0]["timestamp"],
        )
        assert [f.bar_index for f in fills] == [1, 2, 3]
        assert sum(f.quantity for f in fills) == Decimal("20")
        assert [f.fill_index for f in fills] == [0, 1, 2]

    def test_limit_order_never_fills_through_limit(self):
        """BUG-001 semantics in the runtime adapter: BUY limit caps price."""
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars(n=4)
        fills = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="LIMIT", quantity=Decimal("10"), bars=bars,
            submitted_at=bars[0]["timestamp"], limit_price=Decimal("99.5"),
        )
        for f in fills:
            assert f.price <= Decimal("99.5")

    def test_limit_order_unfillable_returns_empty(self):
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars(n=4)
        fills = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="LIMIT", quantity=Decimal("10"), bars=bars,
            submitted_at=bars[0]["timestamp"], limit_price=Decimal("50"),
        )
        assert fills == []

    def test_no_same_bar_fill(self):
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars(n=2)
        fills = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("5"), bars=bars,
            submitted_at=bars[1]["timestamp"],
        )
        assert all(f.bar_index > 1 for f in fills)

    def test_cursor_prevents_duplicate_fills(self):
        adapter = PaperExecutionAdapter(self.REALISM)
        bars = self._bars(n=6, volume=20.0)
        first = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("14"), bars=bars,
            submitted_at=bars[0]["timestamp"], from_bar=1, max_bars=3,
        )
        # Resume from the cursor: only unfilled remainder on new bars.
        second = adapter.execute(
            order_id="o1", symbol="T/USD", side="BUY",
            order_type="MARKET", quantity=Decimal("7"), bars=bars,
            submitted_at=bars[0]["timestamp"], from_bar=3, max_bars=3,
            start_index=len(first),
        )
        bars_hit = [f.bar_index for f in first] + [f.bar_index for f in second]
        assert len(bars_hit) == len(set(bars_hit)), "duplicate bar fills"
        assert all(f.fill_index == i for i, f in enumerate(first + second))

    def test_structural_isolation_marker(self):
        from data_engine.runtime.execution import (
            PAPER_MODE_STRUCTURAL_ISOLATION,
        )
        assert PAPER_MODE_STRUCTURAL_ISOLATION is True
        # No network/credential surface on the adapter.
        adapter = PaperExecutionAdapter(self.REALISM)
        banned = ("url", "endpoint", "host", "token", "password",
                  "api_key", "credential")
        for attr in vars(adapter):
            assert not any(b in attr.lower() for b in banned), attr
