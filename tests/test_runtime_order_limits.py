"""Reconstruction D-6 — mandatory runtime order-limit controls.

Covers the verified G-04 gap: the runtime risk gate had NO order
submission-rate control and NO maximum open-order control (venue-side
emulation only, uncapped on the authoritative paper venue).

Pinned behavior (all fail-closed):

- two NEW mandatory gate checks: ``order_rate_limit`` and
  ``max_open_orders`` (24 mandatory checks total);
- boundary semantics: the Nth submission within the window is allowed
  while count < limit; at-limit (count >= limit) refuses NEW exposure
  with an explicit reason; closing (risk-reducing) orders are exempt
  from both blocks — the same fail-safe carve-out discipline as the
  kill-switch/drawdown checks;
- unknown/missing measured state fails CLOSED, never neutral;
- RuntimeRiskLimits: strictly validated, frozen, honest provisional
  paper-mode defaults (5/60s mirror the venue-capability emulation;
  max_open_orders=10 has no prior design value and REQUIRES operator
  review);
- runtime wiring: governed-time (bar timestamp) rate accounting with
  window pruning; open orders = OMS LIVE + AMBIGUOUS states; the
  open-order control survives export/restore (restarts); duplicate
  intents do not consume rate capacity; blocked orders are never
  submitted.

No production limits are claimed anywhere; live execution stays
structurally refused.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest
from pydantic import ValidationError

from data_engine.risk.engine import RiskEngine, RiskLimits
from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    TradePlan,
    UncertaintyReport,
)
from data_engine.runtime.kill_switch import KillSwitchManager
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.risk_gate import (
    MANDATORY_CHECKS,
    RiskContext,
    RiskGate,
    RuntimeRiskLimits,
)

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
UNC = UncertaintyReport(confidence=0.7, entropy=0.4, ensemble_disagreement=0.05)

LIMITS = RiskLimits(
    max_position_units=Decimal("100"),
    max_leverage=Decimal("1.0"),
    max_single_asset_weight=Decimal("0.30"),
    max_sector_weight=Decimal("1.0"),
    max_portfolio_heat=Decimal("1.0"),
)


def _plan(qty="10", side=DecisionAction.BUY, sl="95", tp="110",
          seq=1):
    return TradePlan(
        trade_plan_id=f"tp-d6-{seq}",
        decision_id=f"d-d6-{seq}",
        symbol="TEST/USD",
        side=side,
        quantity=Decimal(qty),
        notional=Decimal(qty) * Decimal("100"),
        entry=EntryConstraints(
            order_type="MARKET", time_in_force="GTC", limit_price=None,
        ),
        stop_loss=Decimal(sl) if sl else None,
        take_profit=Decimal(tp) if tp else None,
        risk_budget=Decimal("500"),
        expected_return=0.01,
        risk_reward_ratio=2.0,
        uncertainty=UNC,
        crash_risk={"probability": 0.05},
        model_context={"model": "L@1"},
        correlation_id=f"c-d6-{seq}",
    )


def _gate():
    ledger = LedgerFamily()
    ks = KillSwitchManager(ledger)
    engine = RiskEngine(LIMITS)
    return RiskGate(engine, ks), ks, engine, ledger


def _ctx(**over):
    defaults = dict(
        equity=Decimal("100000"),
        current_units=Decimal("0"),
        reference_price=Decimal("100"),
        bar_volume=Decimal("5000"),
        last_bar_age_bars=0,
        market_open=True,
        paper_mode=True,
        model_valid=True,
        uncertainty=UNC,
        crash_probability=0.05,
        max_drawdown_fraction=0.02,
        account_drawdown_fraction=0.0,
        volatility=0.01,
        daily_realized_return=0.001,
        half_spread=Decimal("0.05"),
        # D-6 in-limit defaults (the fail-closedunknown case is tested
        # explicitly by removing them).
        open_order_count=0,
        max_open_orders=10,
        orders_submitted_in_window=0,
        max_orders_per_window=5,
        order_rate_window_seconds=60.0,
    )
    defaults.update(over)
    return RiskContext(**defaults)


# ---------------------------------------------------------------------------
# Gate-level: the two new mandatory checks
# ---------------------------------------------------------------------------


class TestNewMandatoryChecks:
    def test_in_limit_order_passes_all_24_checks(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(), _ctx(), "c-1", ledger=None)
        assert assessment.passed
        names = {c.check for c in assessment.checks}
        assert names == set(MANDATORY_CHECKS)
        assert {"order_rate_limit", "max_open_orders"} <= names

    def test_rate_boundary_limit_minus_one_passes(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(orders_submitted_in_window=4), "c-1"
        )
        assert assessment.passed

    def test_rate_boundary_at_limit_refuses_with_reason(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(orders_submitted_in_window=5), "c-1"
        )
        assert not assessment.passed
        failed = {c.check: c.reason for c in assessment.failed_checks}
        assert "order_rate_limit" in failed
        assert "ORDER RATE LIMIT" in failed["order_rate_limit"]
        assert "5" in failed["order_rate_limit"]

    def test_open_orders_boundary_limit_minus_one_passes(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(open_order_count=9), "c-1"
        )
        assert assessment.passed

    def test_open_orders_boundary_at_limit_refuses_with_reason(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(open_order_count=10), "c-1"
        )
        assert not assessment.passed
        failed = {c.check: c.reason for c in assessment.failed_checks}
        assert "max_open_orders" in failed
        assert "MAX OPEN ORDERS" in failed["max_open_orders"]

    def test_unknown_rate_state_fails_closed(self):
        gate, *_ = _gate()
        for over in (
            {"orders_submitted_in_window": None},
            {"max_orders_per_window": None},
            {"order_rate_window_seconds": None},
        ):
            assessment = gate.evaluate(_plan(), _ctx(**over), "c-1")
            assert not assessment.passed, over
            failed = {c.check for c in assessment.failed_checks}
            assert "order_rate_limit" in failed, over

    def test_unknown_open_order_state_fails_closed(self):
        gate, *_ = _gate()
        for over in (
            {"open_order_count": None},
            {"max_open_orders": None},
        ):
            assessment = gate.evaluate(_plan(), _ctx(**over), "c-1")
            assert not assessment.passed, over
            failed = {c.check for c in assessment.failed_checks}
            assert "max_open_orders" in failed, over

    def test_closing_orders_exempt_even_with_unknown_state(self):
        gate, *_ = _gate()
        closing = _ctx(
            current_units=Decimal("10"),
            open_order_count=None,
            max_open_orders=None,
            orders_submitted_in_window=None,
            max_orders_per_window=None,
            order_rate_window_seconds=None,
        )
        assessment = gate.evaluate(
            _plan(side=DecisionAction.SELL), closing, "c-1"
        )
        checks = {c.check: c for c in assessment.checks}
        assert checks["order_rate_limit"].passed
        assert checks["max_open_orders"].passed
        assert "exempt" in checks["order_rate_limit"].reason

    def test_closing_orders_exempt_even_over_limit(self):
        gate, *_ = _gate()
        closing = _ctx(
            current_units=Decimal("10"),
            open_order_count=999,
            max_open_orders=10,
            orders_submitted_in_window=999,
            max_orders_per_window=5,
        )
        assessment = gate.evaluate(
            _plan(side=DecisionAction.SELL), closing, "c-1"
        )
        assert assessment.passed


# ---------------------------------------------------------------------------
# RuntimeRiskLimits: provisional defaults + strict validation
# ---------------------------------------------------------------------------


class TestRuntimeRiskLimits:
    def test_provisional_defaults_are_pinned(self):
        limits = RuntimeRiskLimits()
        assert limits.max_orders_per_window == 5
        assert limits.window_seconds == 60.0
        assert limits.max_open_orders == 10

    def test_limits_are_frozen(self):
        limits = RuntimeRiskLimits()
        with pytest.raises(ValidationError):
            limits.max_open_orders = 999

    @pytest.mark.parametrize("field,value", [
        ("max_orders_per_window", 0),
        ("max_orders_per_window", -3),
        ("max_open_orders", 0),
        ("max_open_orders", -1),
        ("window_seconds", 0),
        ("window_seconds", -60.0),
    ])
    def test_misconfiguration_fails_closed(self, field, value):
        with pytest.raises(ValidationError):
            RuntimeRiskLimits(**{field: value})

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            RuntimeRiskLimits(unlimited=True)


# ---------------------------------------------------------------------------
# Runtime wiring: governed-time accounting, OMS state counting,
# restart survival, duplicate semantics, end-path blocking
# ---------------------------------------------------------------------------

BAR = {
    "timestamp": T0,
    "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
    "volume": 5000.0,
}


def _bars(n, start=100.0, interval=300):
    out = []
    price = start
    for i in range(n):
        o = price
        c = price + 0.5
        out.append({
            "timestamp": T0 + timedelta(seconds=interval * i),
            "open": o, "high": max(o, c) + 0.25,
            "low": min(o, c) - 0.25, "close": c, "volume": 5000.0,
        })
        price = c
    return out


def _fit_world():
    from data_engine.runtime import (
        DeterministicBaseline,
        DeterministicEnsemble,
        LSTMClassifier,
        RuntimeCalibrator,
        SequenceSpec,
        build_sequence_set,
    )
    train = _bars(120)
    spec = SequenceSpec(symbol="TEST/USD", timeframe="5m", lookback=8,
                        horizon=2, feature_version="fv-1",
                        dataset_version="dv-synth")
    sset = build_sequence_set(train, spec, train[-1]["timestamp"], "train",
                              expected_interval_seconds=300)
    labeled = list(sset.labeled)
    X = [list(s.features) for s in labeled]
    y = [s.target for s in labeled]
    b = DeterministicBaseline(model_id="B", feature_version="fv-1",
                              dataset_version="dv-synth", lookback=8,
                              horizon=2).fit(X, y)
    l = LSTMClassifier(hidden_units=3, epochs=2, seed=5, model_id="L",
                       feature_version="fv-1", dataset_version="dv-synth",
                       lookback=8, horizon=2).fit(X, y)
    ens = DeterministicEnsemble([b, l], [0.5, 0.5])
    cal = RuntimeCalibrator(dataset_version="dv-synth").fit(
        [ens.predict(x).probability for x in X], y)
    return ens, cal


def _config(session="d6"):
    from data_engine.runtime import RuntimeConfig

    return RuntimeConfig(
        symbol="TEST/USD", timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        ephemeral_test_fixture=True,
    )


@pytest.fixture(scope="module")
def world():
    return _fit_world()


def _assessment_for(rt, plan):
    """A real passing RiskAssessment for the plan, produced by the
    runtime's OWN gate (the OMS refuses verbal approvals)."""
    ctx = RiskContext(
        equity=Decimal("100000"),
        current_units=Decimal("0"),
        reference_price=Decimal("100"),
        bar_volume=Decimal("5000"),
        last_bar_age_bars=0,
        market_open=True,
        paper_mode=True,
        model_valid=True,
        uncertainty=UNC,
        crash_probability=0.05,
        max_drawdown_fraction=0.02,
        account_drawdown_fraction=0.0,
        volatility=0.01,
        daily_realized_return=0.001,
        half_spread=Decimal("0.05"),
        open_order_count=0,
        max_open_orders=1000,
        orders_submitted_in_window=0,
        max_orders_per_window=1000,
        order_rate_window_seconds=60.0,
    )
    return rt._risk_gate.evaluate(plan, ctx, plan.correlation_id)


def _created_order(rt, plan):
    order, created = rt._oms.create_order(
        plan=plan, session_id=rt._config.session_id,
        created_at=T0, ttl_bars=None,
    )
    assert created
    rt._oms.validate_order(order.order_id)
    rt._oms.risk_approve(order.order_id, _assessment_for(rt, plan))
    return order


class TestRuntimeWiring:
    def test_default_limits_active_and_governed_time_accounting(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(_config("d6-a"), ens, calibrator=cal)
        assert rt._risk_limits == RuntimeRiskLimits()
        for _ in range(5):
            rt._record_submission(T0)
        assert rt._submissions_in_window(T0) == 5
        # window pruning on governed time (60s default)
        assert rt._submissions_in_window(T0 + timedelta(seconds=61)) == 0

    def test_open_order_counting_includes_ambiguous_states(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(_config("d6-b"), ens, calibrator=cal)
        o1 = _created_order(rt, _plan(seq=1))
        o2 = _created_order(rt, _plan(seq=2))
        rt._oms.submit(o1.order_id, submitted_at=T0, bar_index=0)
        rt._oms.acknowledge(o1.order_id)
        # second order: ambiguous outcome (UNKNOWN + RECONCILING)
        rt._oms.submit(o2.order_id, submitted_at=T0, bar_index=0)
        rt._oms.mark_unknown(o2.order_id, "synthetic ambiguous outcome")
        rt._oms.start_reconciling(o2.order_id)
        assert rt._open_order_count() == 2

    def test_open_order_control_survives_restart_restore(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(_config("d6-c"), ens, calibrator=cal)
        o1 = _created_order(rt, _plan(seq=1))
        rt._oms.submit(o1.order_id, submitted_at=T0, bar_index=0)
        rt._oms.acknowledge(o1.order_id)
        o2 = _created_order(rt, _plan(seq=2))
        rt._oms.submit(o2.order_id, submitted_at=T0, bar_index=0)
        rt._oms.mark_unknown(o2.order_id, "synthetic ambiguous outcome")
        rt._oms.start_reconciling(o2.order_id)
        assert rt._open_order_count() == 2

        # restart: state export -> fresh runtime restore
        state = rt._oms.export_state()
        rt2 = TradingRuntime(_config("d6-c-restored"), ens, calibrator=cal)
        restored = rt2._oms.restore_state(state)
        assert restored == 2
        assert rt2._open_order_count() == 2, (
            "the open-order control must see restored (live + ambiguous) "
            "orders after a restart — capacity is not silently reset"
        )

    def test_rate_limit_blocks_fourth_same_window_submission(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(
            _config("d6-d"), ens, calibrator=cal,
            risk_limits=RuntimeRiskLimits(
                max_orders_per_window=2,
                window_seconds=10**9,
                max_open_orders=100,
            ),
        )
        # admit bar history so the volatility window has real data
        rt._bars.extend(_bars(25))
        outcomes = []
        for i in (1, 2, 3):
            orders, failed = rt._execute_plan(
                _plan(seq=i), BAR, 0, f"c-d6-{i}",
                Decimal("100"), Decimal("100000"),
            )
            outcomes.append((len(orders), failed))
        assert outcomes[0][0] == 1 and not outcomes[0][1]
        assert outcomes[1][0] == 1 and not outcomes[1][1]
        assert outcomes[2][0] == 0
        assert "order_rate_limit" in outcomes[2][1]
        # blocked order was never submitted — rate accounting stays at 2
        assert rt._submissions_in_window(T0) == 2

    def test_max_open_orders_blocks_when_capacity_exhausted(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(
            _config("d6-e"), ens, calibrator=cal,
            risk_limits=RuntimeRiskLimits(
                max_orders_per_window=1000,
                window_seconds=10**9,
                max_open_orders=1,
            ),
        )
        rt._bars.extend(_bars(25))
        orders1, failed1 = rt._execute_plan(
            _plan(seq=1), BAR, 0, "c-d6-e1",
            Decimal("100"), Decimal("100000"),
        )
        assert len(orders1) == 1 and not failed1
        orders2, failed2 = rt._execute_plan(
            _plan(seq=2), BAR, 0, "c-d6-e2",
            Decimal("100"), Decimal("100000"),
        )
        assert orders2 == []
        assert "max_open_orders" in failed2

    def test_duplicate_intent_does_not_consume_rate_capacity(self, world):
        from data_engine.runtime import TradingRuntime

        ens, cal = world
        rt = TradingRuntime(
            _config("d6-f"), ens, calibrator=cal,
            risk_limits=RuntimeRiskLimits(
                max_orders_per_window=5,
                window_seconds=10**9,
                max_open_orders=100,
            ),
        )
        rt._bars.extend(_bars(25))
        same_plan = _plan(seq=1)
        orders1, failed1 = rt._execute_plan(
            same_plan, BAR, 0, "c-dup",
            Decimal("100"), Decimal("100000"),
        )
        assert len(orders1) == 1 and not failed1
        orders2, failed2 = rt._execute_plan(
            same_plan, BAR, 0, "c-dup",
            Decimal("100"), Decimal("100000"),
        )
        assert orders2 == []
        assert "duplicate_order" in failed2
        # the duplicate was refused BEFORE submission: still one submission
        assert rt._submissions_in_window(T0) == 1
        assert rt._open_order_count() == 1
