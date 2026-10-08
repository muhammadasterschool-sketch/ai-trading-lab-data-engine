"""Safety-domain tests: risk gate, kill-switch hierarchy, vocabulary
bridge, reconciliation, P&L/SL-TP, memory (mandate §25/§26/§31/§32/
§35/§41; RT-F1/RT-F6/ARCH-F2/RT-F5).
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.risk.engine import (
    KillSwitchActiveError,
    RiskEngine,
    RiskLimits,
    RiskViolationError,
)
from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    ExitReason,
    UncertaintyReport,
)
from data_engine.runtime.exits import ExitError, ExitManager
from data_engine.runtime.kill_switch import (
    CRITICAL_SCOPES,
    KillSwitchActive,
    KillSwitchError,
    KillSwitchManager,
    KillSwitchScope,
)
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.memory import MemoryCategory, TradingMemory
from data_engine.runtime.pnl import PnLEngine, PositionState
from data_engine.runtime.reconciliation import (
    ReconciliationFailure,
    RuntimeReconciliation,
)
from data_engine.runtime.risk_gate import MANDATORY_CHECKS, RiskContext, RiskGate
from data_engine.runtime.vocabulary import (
    VocabularyError,
    freeze_strategy_boundary,
    lifecycle_to_paper_status,
    paper_status_to_lifecycle,
    runtime_side_to_paper,
    strategy_quantity_to_decimal,
    strategy_side_to_runtime,
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
          order_type="MARKET", limit=None):
    from data_engine.runtime.contracts import TradePlan
    return TradePlan(
        trade_plan_id=f"tp-{qty}-{side.value}-{sl}",
        decision_id="d-1",
        symbol="TEST/USD",
        side=side,
        quantity=Decimal(qty),
        notional=Decimal(qty) * Decimal("100"),
        entry=EntryConstraints(
            order_type=order_type, time_in_force="GTC",
            limit_price=Decimal(limit) if limit else None,
        ),
        stop_loss=Decimal(sl) if sl else None,
        take_profit=Decimal(tp) if tp else None,
        risk_budget=Decimal("500"),
        expected_return=0.01,
        risk_reward_ratio=2.0,
        uncertainty=UNC,
        crash_risk={"probability": 0.05},
        model_context={"model": "L@1"},
        correlation_id="c-1",
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
        volatility=0.01,
        daily_realized_return=0.001,
        half_spread=Decimal("0.05"),
    )
    defaults.update(over)
    return RiskContext(**defaults)


class TestRiskGate:
    def test_clean_entry_passes_all_mandatory_checks(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(), _ctx(), "c-1", ledger=None)
        assert assessment.passed
        names = {c.check for c in assessment.checks}
        assert names == set(MANDATORY_CHECKS)
        assert assessment.assessment_id.startswith("rtrg.")

    def test_stale_data_blocks_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(), _ctx(last_bar_age_bars=5), "c-1")
        assert not assessment.passed
        assert "data_staleness" in {c.check for c in assessment.failed_checks}

    def test_crash_risk_blocks_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(), _ctx(crash_probability=0.5), "c-1")
        assert not assessment.passed
        assert "crash_risk" in {c.check for c in assessment.failed_checks}

    def test_missing_stop_loss_blocks_entry(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(sl=None), _ctx(), "c-1")
        assert not assessment.passed
        assert "stop_loss_presence" in {c.check for c in assessment.failed_checks}

    def test_high_uncertainty_blocks_order(self):
        gate, *_ = _gate()
        unc = UncertaintyReport(confidence=0.3, entropy=0.99,
                                ensemble_disagreement=0.4)
        assessment = gate.evaluate(_plan(), _ctx(uncertainty=unc), "c-1")
        assert not assessment.passed
        assert "uncertainty" in {c.check for c in assessment.failed_checks}

    def test_position_limit_blocks_oversized_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(qty="500"), _ctx(), "c-1")
        assert not assessment.passed
        assert "position_limit" in {c.check for c in assessment.failed_checks}

    def test_duplicate_intent_blocks_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(duplicate_order_id="rtord.dup"), "c-1")
        assert not assessment.passed
        assert "duplicate_order" in {c.check for c in assessment.failed_checks}

    def test_non_paper_mode_blocks_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(_plan(), _ctx(paper_mode=False), "c-1")
        assert not assessment.passed
        assert "paper_mode" in {c.check for c in assessment.failed_checks}

    def test_drawdown_limit_blocks_order(self):
        gate, *_ = _gate()
        assessment = gate.evaluate(
            _plan(), _ctx(max_drawdown_fraction=0.5), "c-1")
        assert not assessment.passed
        assert "drawdown" in {c.check for c in assessment.failed_checks}

    def test_closing_order_permitted_under_active_switch(self):
        """Fail-safe direction: risk-REDUCING orders remain executable
        while the switch blocks NEW exposure."""
        gate, ks, *_ = _gate()
        ks.trip(KillSwitchScope.SYMBOL, "stress", "test", target="TEST/USD")
        with pytest.raises(KillSwitchActive):
            ks.check(symbol="TEST/USD")
        closing = _plan(qty="10", side=DecisionAction.SELL, sl=None, tp=None)
        assessment = gate.evaluate(
            closing, _ctx(current_units=Decimal("10")), "c-1")
        kill = next(c for c in assessment.checks if c.check == "kill_switch")
        assert kill.passed and "fail-safe" in kill.reason

    def test_new_order_blocked_under_active_switch(self):
        gate, ks, *_ = _gate()
        ks.trip(KillSwitchScope.SYMBOL, "stress", "test", target="TEST/USD")
        assessment = gate.evaluate(_plan(), _ctx(), "c-1")
        assert not assessment.passed
        assert "kill_switch" in {c.check for c in assessment.failed_checks}

    def test_assessment_ledgered(self):
        gate, _, _, ledger = _gate()
        gate.evaluate(_plan(), _ctx(), "c-1", ledger=ledger)
        events = [e.event_type for e in ledger.events("trade_plan")]
        assert "RISK_ASSESSMENT_PASS" in events

    def test_failed_assessment_ledgered_with_reasons(self):
        gate, _, _, ledger = _gate()
        gate.evaluate(_plan(), _ctx(crash_probability=0.5), "c-1",
                      ledger=ledger)
        events = ledger.events("trade_plan")
        fail = [e for e in events if e.event_type == "RISK_ASSESSMENT_FAIL"]
        assert fail and "crash_risk" in fail[0].payload["failed_checks"]

    def test_unknown_context_fails_closed(self):
        """Missing volatility/drawdown/daily P&L knowledge = failure,
        never neutral (mandate §53 fail-closed)."""
        gate, *_ = _gate()
        a = gate.evaluate(_plan(), _ctx(volatility=None), "c-1")
        assert not a.passed
        b = gate.evaluate(_plan(), _ctx(max_drawdown_fraction=None), "c-1")
        assert not b.passed
        c = gate.evaluate(_plan(), _ctx(daily_realized_return=None), "c-1")
        assert not c.passed


class TestKillSwitchHierarchy:
    def _ks(self):
        return KillSwitchManager(LedgerFamily())

    def test_seven_scopes_exist(self):
        assert {s.value for s in KillSwitchScope} == {
            "ORDER", "STRATEGY", "SYMBOL", "MODEL", "PORTFOLIO",
            "ACCOUNT", "GLOBAL",
        }

    def test_symbol_switch_blocks_symbol_only(self):
        ks = self._ks()
        ks.trip(KillSwitchScope.SYMBOL, "vol spike", "risk", target="AAA/USD")
        with pytest.raises(KillSwitchActive):
            ks.check(symbol="AAA/USD")
        ks.check(symbol="BBB/USD")  # unaffected

    def test_global_switch_blocks_everything(self):
        ks = self._ks()
        ks.trip(KillSwitchScope.GLOBAL, "operator halt", "human")
        with pytest.raises(KillSwitchActive):
            ks.check(symbol="ANY/USD")
        assert ks.any_critical_active()

    def test_machine_reset_refused(self):
        ks = self._ks()
        ks.trip(KillSwitchScope.SYMBOL, "x", "t", target="A/USD")
        with pytest.raises(KillSwitchError, match="HUMAN"):
            ks.reset(KillSwitchScope.SYMBOL, "ai-agent", "machine",
                     target="A/USD")

    def test_human_reset_requires_authorization_for_critical(self):
        ks = self._ks()
        ks.trip(KillSwitchScope.GLOBAL, "halt", "human")
        with pytest.raises(KillSwitchError, match="authorization"):
            ks.reset(KillSwitchScope.GLOBAL, "operator-1", "human")
        ks.request_reset(KillSwitchScope.GLOBAL, "operator-1")
        ks.authorize_reset(KillSwitchScope.GLOBAL, "operator-1")
        state = ks.reset(KillSwitchScope.GLOBAL, "operator-1", "human")
        assert not state.active

    def test_trip_and_reset_are_ledgered_rt_f5(self):
        ks = self._ks()
        ledger = ks._ledger
        ks.trip(KillSwitchScope.PORTFOLIO, "drawdown breach", "risk")
        ks.request_reset(KillSwitchScope.PORTFOLIO, "op")
        types = [e.event_type for e in ledger.events("incident")]
        assert "KILL_SWITCH_TRIPPED" in types
        assert "KILL_SWITCH_RESET_REQUESTED" in types

    def test_critical_scopes_are_account_and_global(self):
        assert CRITICAL_SCOPES == {KillSwitchScope.ACCOUNT,
                                   KillSwitchScope.GLOBAL}

    def test_persistence_roundtrip(self):
        ks = self._ks()
        ks.trip(KillSwitchScope.SYMBOL, "x", "t", target="A/USD")
        state = ks.export_state()
        ks2 = KillSwitchManager(LedgerFamily())
        ks2.restore_state(state)
        with pytest.raises(KillSwitchActive):
            ks2.check(symbol="A/USD")


class TestRiskEngineRTF5ARCHF2:
    def test_trip_emits_violation_record(self):
        engine = RiskEngine(LIMITS)
        engine.trip_kill_switch()
        rules = [r.rule for r in engine.violation_log]
        assert "kill_switch_trip" in rules

    def test_reset_refusal_audited(self):
        engine = RiskEngine(LIMITS)
        engine.trip_kill_switch()
        with pytest.raises(RiskViolationError):
            engine.reset_kill_switch(principal="ai", principal_kind="machine")
        rules = [r.rule for r in engine.violation_log]
        assert "kill_switch_reset_refused" in rules

    def test_violation_log_verifies_arch_f2(self):
        engine = RiskEngine(LIMITS)
        engine.trip_kill_switch()
        engine.reset_kill_switch(principal="human-1", principal_kind="human")
        assert engine.verify_violation_log()
        # Tamper with a record (replace the frozen instance) → chain
        # verification FAILS: the recomputed hash no longer matches.
        engine._records[0] = engine._records[0].model_copy(
            update={"rule": "tampered"}
        )
        assert not engine.verify_violation_log()

    def test_exposure_report_enforce_mode_rt_f9(self):
        from data_engine.risk.engine import ExposureManager
        engine = RiskEngine(LIMITS)
        engine.trip_kill_switch()
        mgr = ExposureManager(LIMITS)
        with pytest.raises(KillSwitchActiveError):
            mgr.build_report(
                positions={"A": Decimal("1")}, prices={"A": Decimal("100")},
                equity=Decimal("1000"), enforce=True, guard=engine,
            )
        # Breach without switch → raises under enforce.
        engine2 = RiskEngine(LIMITS)
        with pytest.raises(RiskViolationError, match="RT-F9"):
            mgr.build_report(
                positions={"A": Decimal("100")}, prices={"A": Decimal("100")},
                equity=Decimal("1000"), enforce=True, guard=engine2,
            )


class TestVocabularyBridgeRTF6:
    def test_side_translations(self):
        assert strategy_side_to_runtime("LONG") is DecisionAction.BUY
        assert strategy_side_to_runtime("SHORT") is DecisionAction.SELL
        assert runtime_side_to_paper(DecisionAction.BUY).value == "buy"
        with pytest.raises(VocabularyError):
            strategy_side_to_runtime("SIDEWAYS")

    def test_quantity_translation_deterministic(self):
        assert strategy_quantity_to_decimal(12.345678901234) == Decimal(
            "12.3456789012")
        with pytest.raises(VocabularyError):
            strategy_quantity_to_decimal(float("nan"))

    def test_status_translations(self):
        assert paper_status_to_lifecycle("filled").value == "FILLED"
        assert lifecycle_to_paper_status(
            paper_status_to_lifecycle("submitted")) == "submitted"
        # Partial fills map down to the paper 'submitted' vocabulary.
        from data_engine.runtime.contracts import OrderLifecycle
        assert lifecycle_to_paper_status(
            OrderLifecycle.PARTIALLY_FILLED) == "submitted"

    def test_strategy_boundary_snapshot_bug_008(self):
        """BUG-008 runtime-boundary adapter: frozen-domain models
        crossing into the runtime are deep-copied read-only snapshots —
        the ORIGINAL is never retained or mutated."""
        class FakeStrategyModel:
            def __init__(self):
                self.data = {"positions": [1, 2, 3]}
            def model_dump(self):
                return {"data": self.data}
        m = FakeStrategyModel()
        snap = freeze_strategy_boundary(m)
        assert snap["data"]["positions"] == [1, 2, 3]
        m.data["positions"].append(99)
        assert snap["data"]["positions"] == [1, 2, 3], \
            "boundary snapshot must be independent of later mutation"


class TestReconciliation:
    def _world(self):
        ledger = LedgerFamily()
        from data_engine.runtime.oms import OMS
        from data_engine.runtime.contracts import TradePlan
        oms = OMS(ledger)
        plan = _plan(qty="100")
        order, _ = oms.create_order(plan, "s", T0)
        oms.validate_order(order.order_id)
        class _A:
            passed = True
            assessment_id = "rtrg.t"
            failed_checks = ()
            order_fingerprint = {
                "trade_plan_id": order.trade_plan_id,
                "symbol": order.symbol, "side": order.side,
                "quantity": str(order.quantity),
                "order_type": order.order_type,
                "limit_price": None,
            }
        oms.risk_approve(order.order_id, _A())
        oms.submit(order.order_id, T0, 10)
        return oms, order

    def _fill(self, oid, qty, idx=0, bar=1):
        from data_engine.runtime.execution import RuntimeFill
        return RuntimeFill(
            fill_id="pending", order_id=oid, symbol="TEST/USD", side="BUY",
            quantity=Decimal(qty), price=Decimal("100"),
            commission=Decimal("0.1"), slippage_cost=Decimal("0.05"),
            spread_cost=Decimal("0.02"),
            filled_at=T0 + timedelta(minutes=5), fill_index=idx,
            bar_index=bar,
        )

    def test_clean_state_reconciles(self):
        oms, order = self._world()
        oms.apply_fill(order.order_id, self._fill(order.order_id, "100"))
        positions = {"TEST/USD": PositionState(symbol="TEST/USD")}
        positions["TEST/USD"] = positions["TEST/USD"].apply_fill(
            Decimal("100"), Decimal("100"), "BUY",
            Decimal("0.1"), Decimal("0.05"), Decimal("0.02"),
            T0, "f1",
        )
        recon = RuntimeReconciliation(LedgerFamily())
        report = recon.reconcile(oms, positions)
        assert report.ok

    def test_position_mismatch_detected(self):
        oms, order = self._world()
        oms.apply_fill(order.order_id, self._fill(order.order_id, "100"))
        positions = {"TEST/USD": PositionState(symbol="TEST/USD")}
        recon = RuntimeReconciliation(LedgerFamily())
        report = recon.reconcile(oms, positions)
        assert not report.ok
        with pytest.raises(ReconciliationFailure, match="STOPPED"):
            recon.require_ok(report)

    def test_partial_fill_quantity_consistency(self):
        oms, order = self._world()
        oms.apply_fill(order.order_id, self._fill(order.order_id, "40"))
        recon = RuntimeReconciliation(LedgerFamily())
        report = recon.reconcile(oms, {  # state claims nothing
        })
        # PARTIALLY_FILLED with 40/100 is internally consistent; the
        # position replay check reports the unstated position instead.
        assert not report.ok  # position with fills but no stated state


class TestExitsSLTP:
    def _exit_manager(self):
        return ExitManager(LedgerFamily())

    def _position(self, qty="10", avg="100", sl=None, tp=None):
        return PositionState(
            symbol="TEST/USD", quantity=Decimal(qty),
            average_cost=Decimal(avg), realized_pnl=Decimal("0"),
            stop_loss=Decimal(sl) if sl else None,
            take_profit=Decimal(tp) if tp else None,
        )

    def test_sl_hit_long(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100", sl="95")
        bar = {"low": Decimal("94"), "high": Decimal("101")}
        hit = em.evaluate_bar(pos, bar)
        assert hit is not None and hit[0] is ExitReason.SL_HIT

    def test_tp_hit_long(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100", tp="110")
        bar = {"low": Decimal("99"), "high": Decimal("111")}
        hit = em.evaluate_bar(pos, bar)
        assert hit is not None and hit[0] is ExitReason.TP_HIT

    def test_both_hit_resolves_conservatively_to_sl(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100", sl="95", tp="110")
        bar = {"low": Decimal("94"), "high": Decimal("111")}
        hit = em.evaluate_bar(pos, bar)
        assert hit[0] is ExitReason.SL_HIT

    def test_sl_hit_short(self):
        em = self._exit_manager()
        pos = self._position(qty="-10", avg="100", sl="105")
        bar = {"low": Decimal("99"), "high": Decimal("106")}
        hit = em.evaluate_bar(pos, bar)
        assert hit[0] is ExitReason.SL_HIT

    def test_set_and_modify_sl_ledgered(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100")
        pos, _ = em.set_stop_loss(pos, Decimal("95"), "c-1", T0)
        pos, _ = em.set_stop_loss(pos, Decimal("96"), "c-1", T0)
        events = [e.event_type for e in em._ledger.events("position")]
        assert "SL_SET" in events and "SL_MODIFIED" in events

    def test_inverted_sl_rejected(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100")
        with pytest.raises(ExitError, match="below"):
            em.set_stop_loss(pos, Decimal("110"), "c-1", T0)

    def test_exit_record_linkage(self):
        em = self._exit_manager()
        pos = self._position(qty="10", avg="100")
        record = em.record_exit(
            reason=ExitReason.SL_HIT, state=pos, timestamp=T0,
            order_ids=("o1",), fill_ids=("f1", "f2"),
            correlation_id="c-1",
        )
        assert record.exit_id.startswith("rtxit.")
        assert record.reason is ExitReason.SL_HIT
        assert record.fill_ids == ("f1", "f2")
        events = [e.event_type for e in em._ledger.events("trade")]
        assert "EXIT_SL_HIT" in events


class TestPnLAccounting:
    def test_partial_fills_and_average_cost(self):
        pos = PositionState(symbol="TEST/USD")
        pos = pos.apply_fill(Decimal("20"), Decimal("100"), "BUY",
                             filled_at=T0, source_event="f1")
        assert pos.quantity == Decimal("20") and pos.average_cost == Decimal("100")
        pos = pos.apply_fill(Decimal("30"), Decimal("110"), "BUY",
                             filled_at=T0, source_event="f2")
        assert pos.quantity == Decimal("50")
        assert pos.average_cost == (Decimal(2000) + Decimal(3300)) / Decimal(50)

    def test_close_realizes_pnl(self):
        pos = PositionState(symbol="TEST/USD")
        pos = pos.apply_fill(Decimal("10"), Decimal("100"), "BUY",
                             filled_at=T0, source_event="f1")
        pos = pos.apply_fill(Decimal("10"), Decimal("120"), "SELL",
                             filled_at=T0, source_event="f2")
        assert pos.quantity == Decimal("0")
        assert pos.realized_pnl == Decimal("200")

    def test_position_flip_bug_002_semantics(self):
        """Flip residual opens at the flip fill's all-in price."""
        pos = PositionState(symbol="TEST/USD")
        pos = pos.apply_fill(Decimal("10"), Decimal("100"), "BUY",
                             filled_at=T0, source_event="f1")
        pos = pos.apply_fill(Decimal("25"), Decimal("110"), "SELL",
                             filled_at=T0, source_event="f2")
        # Closed 10 long at 110 → +100 realized; residual short 15 @ 110.
        assert pos.quantity == Decimal("-15")
        assert pos.realized_pnl == Decimal("100")
        assert pos.average_cost == Decimal("110")

    def test_unrealized_mark_to_market(self):
        engine = PnLEngine()
        pos = PositionState(symbol="TEST/USD")
        pos = pos.apply_fill(Decimal("10"), Decimal("100"), "BUY",
                             filled_at=T0, source_event="f1")
        assert engine.unrealized(pos, Decimal("105")) == Decimal("50")
        assert engine.unrealized(pos, Decimal("95")) == Decimal("-50")

    def test_pnl_record_chain_linkage(self):
        engine = PnLEngine()
        pos = PositionState(symbol="TEST/USD")
        pos = pos.apply_fill(Decimal("10"), Decimal("100"), "BUY",
                             filled_at=T0, source_event="f1")
        rec = engine.record(
            pos, Decimal("105"), Decimal("0.17"),
            entry_fill_ids=["f1"], exit_fill_ids=[], order_ids=["o1"],
            correlation_id="c-1",
        )
        assert rec.entry_fill_ids == ("f1",)
        assert rec.order_ids == ("o1",)
        assert rec.unrealized_pnl == Decimal("50")


class TestTradingMemory:
    def test_categories_complete(self):
        assert len(MemoryCategory) == 12

    def test_append_and_verify(self):
        mem = TradingMemory()
        mem.record(MemoryCategory.MARKET, {"close": "100"}, correlation_id="c1")
        mem.record(MemoryCategory.DECISION, {"action": "NO_TRADE"},
                   correlation_id="c1")
        assert len(mem) == 2
        assert mem.verify_integrity()
        assert len(mem.by_category(MemoryCategory.DECISION)) == 1

    def test_capacity_fail_closed(self):
        mem = TradingMemory()
        mem.MAX_RECORDS = 3
        for i in range(3):
            mem.record(MemoryCategory.OPERATIONS, {"i": i})
        with pytest.raises(Exception, match="capacity"):
            mem.record(MemoryCategory.OPERATIONS, {"i": 3})

    def test_no_safety_override_surface(self):
        """Memory never overrides safety controls: the store exposes NO
        mutation API for risk/kill-switch/OMS state (structural read-
        only separation, mandate §41)."""
        mem = TradingMemory()
        banned = ("risk", "kill", "switch", "order", "approve", "reset",
                  "submit", "trip")
        for attr in dir(mem):
            if attr.startswith("_"):
                continue
            assert not any(b in attr.lower() for b in banned), attr
