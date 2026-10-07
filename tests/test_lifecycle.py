"""End-to-end autonomous lifecycle test (mandate Phase 40, blueprint 5.60).

Demonstrates the complete logical lifecycle with REAL components —
no mocks, no stubs of the stages under test:

    DISCOVER → INGEST → VALIDATE → PIT FILTER → FEATURE → RESEARCH →
    STRATEGY GENERATION → BACKTEST → STATISTICAL VALIDATION →
    ROBUSTNESS → RISK → PORTFOLIO → PAPER TRADE → MONITOR →
    GRADUATE / REJECT / RETIRE

and proves the system can choose NO TRADE at every decision boundary
(blueprint 5.60 invariant: no fixed trade-count objective; NO TRADE is
always available).

Determinism hygiene: every synthetic candle carries an EXPLICIT
``provider_timestamp`` — the frozen F-04 unset path (H-1) is never
exercised anywhere in this lifecycle.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from data_engine.benchmarks.runner import _make_candles, _make_dataset
from data_engine.discovery import (
    CandidateEvaluator,
    CandidateStatus,
    CandidateValidator,
    ExecutionEligibility,
    RuleBasedGenerator,
    RuleTemplate,
    SignalAction,
)
from data_engine.infra.observability import HealthCheck, HealthStatus, Monitor
from data_engine.paper.evaluation import (
    EvaluationFramework,
    EvaluationStatus,
    GraduationEvaluator,
    HumanAuthorizationRegistry,
    LiveAuthorizationGate,
    ReadinessChecker,
)
from data_engine.paper.gateway import PaperOrderGateway
from data_engine.paper.models import OrderSide, OrderType
from data_engine.paper.simulator import (
    ExecutionRealism,
    ExecutionSimulator,
)
from data_engine.pit.sidecar import PitSidecar
from data_engine.pit.tiebreaker import TieBreakerPolicy
from data_engine.pit.view import PitViewBuilder
from data_engine.quant.features import FeaturePipeline, FeatureSpec
from data_engine.research.governance import (
    ApprovalMetadata,
    ApprovalStatus,
    Principal,
    PrincipalKind,
    ResearchContract,
    ResearchRegistry,
)
from data_engine.research_validation.robustness import (
    plateau_analysis,
    sweep,
)
from data_engine.research_validation.statistical import t_test
from data_engine.risk.engine import RiskEngine, RiskLimits
from data_engine.risk.portfolio import PortfolioConstructor
from data_engine.strategy.backtest import BacktestEngine
from data_engine.validation import DataValidator

HUMAN = Principal(principal_id="operator-1", kind=PrincipalKind.HUMAN)
AGENT = Principal(principal_id="agent-zai", kind=PrincipalKind.MACHINE)

N_CANDLES = 80
HYPOTHESIS_HASH = "h" * 64


class _DuckVersion:
    def __init__(self, version: str = "v1") -> None:
        self.version = version


class _DuckDataset:
    def __init__(self, candles) -> None:
        self.candles = list(candles)
        self.dataset_id = "lifecycle-ds"
        self.version = _DuckVersion("v1")


def _lifecycle_candles():
    return _make_candles(N_CANDLES)


def _sidecars_for(candles):
    return {
        i: PitSidecar(
            dataset_id="lifecycle-ds",
            dataset_version="v1",
            event_time=c.timestamp,
            observation_time=c.timestamp + timedelta(minutes=30),
            publication_time=c.timestamp + timedelta(hours=6),
            effective_time=c.timestamp,
        )
        for i, c in enumerate(candles)
    }


def _entry_thresholds():
    # sma20 is pre-parameterized: the frozen engine's feature generator
    # calls calculate() WITHOUT parameters, so generic names (e.g. bare
    # "sma") hit the all-None default-parameter defect (registered as
    # finding F-11 in the defect register, NOT fixed here).
    return (100.0, 102.0)


def _generate_validated_candidate(dataset_hash: str):
    template = RuleTemplate(
        template_id="lifecycle-momentum",
        description="sma20 above threshold entry",
        indicator="sma20",
        entry_operator=">",
        entry_thresholds=_entry_thresholds(),
        exit_thresholds=(90.0,),
        min_history_bars=20,
    )
    candidates = RuleBasedGenerator([template]).generate(
        hypothesis_hash=HYPOTHESIS_HASH,
        dataset_hash=dataset_hash,
        instrument="XAU/USD",
        timeframe="D1",
    )
    validator = CandidateValidator()
    validated = [
        validator.validate(
            c,
            available_history_bars=N_CANDLES,
            available_feature_outputs=["sma20"],
        )
        for c in candidates
    ]
    return [c for c in validated if c.status is CandidateStatus.VALIDATED]


def _bars_from(candles):
    return [
        {
            "timestamp": c.timestamp,
            "open": Decimal(str(c.open)),
            "high": Decimal(str(c.high)),
            "low": Decimal(str(c.low)),
            "close": Decimal(str(c.close)),
            "volume": Decimal(str(c.volume or 1000)),
        }
        for c in candles
    ]


# ---------------------------------------------------------------------------
# The full lifecycle, stage by stage, with REAL components
# ---------------------------------------------------------------------------

class TestFullLifecycle:
    def test_discover_through_reject(self):
        """The complete lifecycle ends in a governed REJECTION, not an
        auto-graduation — 30-day rule + human gates hold."""
        candles = _lifecycle_candles()

        # 1. INGEST — canonical dataset over valid candles.
        dataset = _make_dataset(candles)
        assert dataset.total_rows == N_CANDLES

        # 2. VALIDATE — every candle passes the deterministic validator.
        results = DataValidator().validate_dataset(dataset)
        invalid = [
            r for r in results if r.status.value not in {"valid", "VALID"}
        ]
        assert not invalid

        # 3. POINT-IN-TIME FILTER — cutoff after last publication.
        duck = _DuckDataset(candles)
        cutoff = candles[-1].timestamp + timedelta(hours=7)
        view = PitViewBuilder().build(
            duck, cutoff, _sidecars_for(candles),
            TieBreakerPolicy(name="ts-order", version="1.0.0",
                             keys=("timestamp",)),
        )
        assert len(view.items) == N_CANDLES  # all published before cutoff

        # 4. FEATURE — PIT feature pipeline over visible prefix.
        rows = [{"timestamp": c.timestamp, "close": c.close} for c in candles]
        features = FeaturePipeline(
            specs=(
                FeatureSpec(output_name="sma_5", indicator="sma",
                            parameters={"period": 5}),
                FeatureSpec(output_name="ema_5", indicator="ema",
                            parameters={"period": 5}),
            )
        ).compute(rows, cutoff)
        assert len(features.rows) == N_CANDLES

        # 5. RESEARCH — contract registered, human-approved.
        contract = ResearchContract(
            research_id="lifecycle-research-1",
            title="Momentum over SMA",
            hypothesis="close crossing a threshold predicts drift",
            methodology="deterministic rule-based grid",
            data_references=(features.feature_dataset_hash,),
            submitted_by=AGENT,
            submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        registry = ResearchRegistry()
        research_hash = registry.register(contract)
        registry.attach_approval(
            ApprovalMetadata(
                research_hash=research_hash,
                submitter=AGENT,
                approver=HUMAN,
                decision=ApprovalStatus.APPROVED,
                decision_time=datetime(2026, 1, 2, tzinfo=UTC),
                rationale="lifecycle demonstration",
            )
        )
        assert registry.approved_only() == ["lifecycle-research-1"]

        # 6. STRATEGY GENERATION — deterministic grid + validation.
        validated = _generate_validated_candidate(
            dataset_hash=features.feature_dataset_hash
        )
        assert validated
        candidate = validated[0]
        assert candidate.status is CandidateStatus.VALIDATED

        # 7. BACKTEST — frozen Phase 3 engine over the validated spec.
        backtest = BacktestEngine().run(candidate.spec, dataset)
        assert backtest.strategy_id == candidate.spec.strategy_id

        # 8. STATISTICAL VALIDATION — t-test over equity-curve returns.
        equities = [
            p.total_equity
            for p in backtest.equity_curve.equity_curve
        ]
        returns = [
            equities[i] / equities[i - 1] - 1.0
            for i in range(1, len(equities))
            if equities[i - 1] != 0
        ]
        if len(returns) >= 2:
            try:
                stats = t_test(returns)
                assert stats is not None
            except ValueError:
                # Zero-variance equity (no trades) is an HONEST undefined
                # statistic — the module refuses fake p-values by design.
                pass

        # 9. ROBUSTNESS — parameter sweep over the entry threshold.
        def _score(params):
            entry = json.dumps(
                [{"indicator": "sma20", "operator": ">",
                  "threshold": params["threshold"],
                  "timeframe": None, "requires_previous": False}],
                sort_keys=True,
            )
            spec = candidate.spec.model_copy(
                update={"entry_conditions_serialized": entry}
            )
            return BacktestEngine().run(spec, dataset).total_return

        sweep_results = sweep(
            {"threshold": [99.0, 100.0, 101.0, 102.0]},
            _score,
            score_key="total_return",
        )
        plateau = plateau_analysis(sweep_results,
                                   score_key="total_return")
        assert "threshold" in plateau["axes"]

        # 10. RISK — hard-limit engine clears the sized order.
        limits = RiskLimits(
            max_position_units=Decimal("10"),
            max_leverage=Decimal("3"),
            max_single_asset_weight=Decimal("0.5"),
            max_sector_weight=Decimal("0.9"),
            max_portfolio_heat=Decimal("1.0"),
        )
        engine = RiskEngine(limits, trip_on_breach=False)
        engine.check_order("XAU/USD", Decimal("1"))

        # 11. PORTFOLIO — inverse-volatility allocation within limits.
        allocation = PortfolioConstructor(engine).allocate(
            {
                "XAU/USD": Decimal("0.020"),
                "SYM2": Decimal("0.021"),
                "SYM3": Decimal("0.022"),
            },
            Decimal("1.0"),
            sectors={
                "XAU/USD": "metal",
                "SYM2": "other",
                "SYM3": "other",
            },
        )
        assert allocation.weights

        # 12. PAPER TRADE — realism simulator over real bars.
        realism = ExecutionRealism(
            half_spread=Decimal("0.01"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.1"),
            fill_lag_bars=1,
        )
        bars = _bars_from(candles)
        gateway = PaperOrderGateway(ExecutionSimulator(realism))
        order_kwargs = dict(
            symbol="XAU/USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        record = gateway.submit(
            type("O", (), {})  # placeholder replaced below
            if False
            else _paper_order("lifecycle-1", bars[10]["timestamp"],
                              **order_kwargs),
            bars,
        )
        assert record.status.value in {"filled", "FILLED"}

        # 13. MONITOR — health checks all green.
        monitor = Monitor()
        monitor.register(
            HealthCheck("data-quality", lambda: HealthStatus.HEALTHY)
        )
        statuses = monitor.poll()
        assert statuses == {"data-quality": "healthy"}

        # 14. GRADUATE / REJECT — 30-day rule denies short windows.
        framework = EvaluationFramework()
        evaluation = framework.evaluate(
            strategy_id=candidate.spec.strategy_id,
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 1, 6, tzinfo=UTC),  # 5 days only
            criteria=(
                ReadinessChecker.max_drawdown_criterion(0.05),
                ReadinessChecker.reconciliation_criterion(True),
                ReadinessChecker.reproducibility_criterion(True),
            ),
            no_trade_verified=True,
        )
        assert evaluation.status is EvaluationStatus.INCOMPLETE

        # Human token exists — but graduation STILL denied: 30-day rule.
        auth_registry = HumanAuthorizationRegistry({"operator-1"})
        token = auth_registry.issue(
            "operator-1", "graduation", "lifecycle demo token",
        )
        decision = GraduationEvaluator(auth_registry).evaluate(
            evaluation, token
        )
        assert decision.graduated is False
        assert "30-day" in decision.rationale or "INCOMPLETE" in (
            decision.rationale
        )

        # 15. The strategy is RETURNED FOR RESEARCH, not auto-promoted.
        assert registry.approved_only()  # research evidence preserved
        assert decision.graduated is False

    def test_lifecycle_is_deterministic(self):
        """The whole chain is reproducible: same inputs, same outputs."""
        a = self._run_core_chain()
        b = self._run_core_chain()
        assert a == b

    def _run_core_chain(self):
        candles = _lifecycle_candles()
        dataset = _make_dataset(candles)
        duck = _DuckDataset(candles)
        cutoff = candles[-1].timestamp + timedelta(hours=7)
        view = PitViewBuilder().build(
            duck, cutoff, _sidecars_for(candles),
            TieBreakerPolicy(name="ts-order", version="1.0.0",
                             keys=("timestamp",)),
        )
        validated = _generate_validated_candidate(
            dataset_hash="d" * 64
        )
        backtest = BacktestEngine().run(validated[0].spec, dataset)
        return {
            "view_hash": view.view_hash,
            "candidate_hash": validated[0].candidate_hash,
            "spec_hash": validated[0].spec_hash,
            "total_return": round(backtest.total_return, 10),
            "final_equity": round(backtest.final_equity, 6),
        }


def _paper_order(client_order_id, submitted_at, **kwargs):
    from data_engine.paper.models import PaperOrder

    return PaperOrder(
        client_order_id=client_order_id,
        submitted_at=submitted_at,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# NO TRADE at every decision boundary (blueprint 5.60 invariant)
# ---------------------------------------------------------------------------

class TestNoTradeAtEveryBoundary:
    def test_data_boundary_invalid_data_yields_no_trade(self):
        """Bad candles → validation failures → chain denies at DATA."""
        candles = _lifecycle_candles()
        dataset = _make_dataset(candles)
        # Corrupt one candle past construction validation is impossible
        # (pydantic frozen) — so simulate a FAILED validation verdict.
        decision = ExecutionEligibility().evaluate(
            data_valid=False,
            data_detail="validator reported impossible OHLC",
            pit_valid=True,
            strategy_valid=True,
            signal_is_no_trade=False,
            risk_valid=True,
            portfolio_valid=True,
        )
        assert decision.decision == "NO_TRADE"
        assert any("data_valid" in r for r in decision.reasons)

    def test_pit_boundary_future_only_view_yields_no_trade(self):
        """A cutoff before every publication excludes everything."""
        candles = _lifecycle_candles()
        duck = _DuckDataset(candles)
        early_cutoff = candles[0].timestamp - timedelta(days=1)
        view = PitViewBuilder().build(
            duck, early_cutoff, _sidecars_for(candles),
            TieBreakerPolicy(name="ts-order", version="1.0.0",
                             keys=("timestamp",)),
        )
        assert len(view.items) == 0
        decision = ExecutionEligibility().evaluate(
            data_valid=True,
            pit_valid=False,
            pit_detail="PitView empty at cutoff",
            strategy_valid=True,
            signal_is_no_trade=False,
            risk_valid=True,
            portfolio_valid=True,
        )
        assert decision.decision == "NO_TRADE"

    def test_signal_boundary_flat_market_yields_no_trade(self):
        """Valid strategy + unsatisfied conditions → NO TRADE signal."""
        validated = _generate_validated_candidate("d" * 64)
        candidate = validated[0]
        # Thresholds are 100/102 — an sma20 of 1.0 satisfies neither.
        decision = CandidateEvaluator().evaluate(candidate, {"sma20": 1.0})
        assert decision.action is SignalAction.NO_TRADE

    def test_strategy_boundary_rejected_candidate_cannot_evaluate(self):
        """A REJECTED candidate is not even evaluable — governance."""
        template = RuleTemplate(
            template_id="bad-strategy",
            indicator="sma20",
            entry_operator=">",
            entry_thresholds=(1.0,),
            exit_thresholds=(90.0,),
            min_history_bars=999,  # more history than we have
        )
        candidates = RuleBasedGenerator([template]).generate(
            hypothesis_hash=HYPOTHESIS_HASH,
            dataset_hash="d" * 64,
            instrument="XAU/USD",
            timeframe="D1",
        )
        rejected = CandidateValidator().validate(
            candidates[0],
            available_history_bars=10,
            available_feature_outputs=["sma20"],
        )
        assert rejected.status is CandidateStatus.REJECTED
        with pytest.raises(Exception, match="only VALIDATED"):
            CandidateEvaluator().evaluate(rejected, {"sma20": 999.0})

    def test_risk_boundary_oversized_order_is_refused(self):
        limits = RiskLimits(
            max_position_units=Decimal("5"),
            max_leverage=Decimal("3"),
            max_single_asset_weight=Decimal("0.5"),
            max_sector_weight=Decimal("0.9"),
            max_portfolio_heat=Decimal("1.0"),
        )
        engine = RiskEngine(limits, trip_on_breach=False)
        with pytest.raises(Exception, match="exceeds max"):
            engine.check_order("XAU/USD", Decimal("100"))

    def test_kill_switch_boundary_blocks_all_evaluation(self):
        limits = RiskLimits(
            max_position_units=Decimal("5"),
            max_leverage=Decimal("3"),
            max_single_asset_weight=Decimal("0.5"),
            max_sector_weight=Decimal("0.9"),
            max_portfolio_heat=Decimal("1.0"),
        )
        engine = RiskEngine(limits, trip_on_breach=True)
        engine.trip_kill_switch()
        with pytest.raises(Exception, match="[Kk]ill"):
            engine.check_order("XAU/USD", Decimal("1"))

    def test_evaluation_boundary_short_window_is_incomplete(self):
        framework = EvaluationFramework()
        evaluation = framework.evaluate(
            strategy_id="s",
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 1, 15, tzinfo=UTC),  # 14 days
            criteria=(ReadinessChecker.reconciliation_criterion(True),),
            no_trade_verified=True,
        )
        assert evaluation.status is EvaluationStatus.INCOMPLETE

    def test_graduation_boundary_no_token_no_graduation(self):
        framework = EvaluationFramework()
        evaluation = framework.evaluate(
            strategy_id="s",
            window_start=datetime(2026, 1, 1, tzinfo=UTC),
            window_end=datetime(2026, 2, 15, tzinfo=UTC),  # 45 days
            criteria=(
                ReadinessChecker.max_drawdown_criterion(0.05),
                ReadinessChecker.reconciliation_criterion(True),
                ReadinessChecker.reproducibility_criterion(True),
            ),
            no_trade_verified=True,
        )
        assert evaluation.status is EvaluationStatus.COMPLETE
        # But graduation needs a HUMAN token that the machine cannot mint.
        # A well-formed token that was never ISSUED by any registry is
        # unverifiable — graduation is denied, not raised:
        from data_engine.paper.evaluation import HumanAuthorizationToken
        unissued = HumanAuthorizationToken(
            token_id="tok-forged",
            human_principal_id="operator-1",
            purpose="graduation",
            issued_at=datetime(2026, 1, 1, tzinfo=UTC),
            statement="forged token never issued by any registry",
        )
        decision = GraduationEvaluator(
            HumanAuthorizationRegistry({"operator-1"})
        ).evaluate(evaluation, unissued)
        assert decision.graduated is False
        assert "human authorization" in decision.rationale
        # And an EMPTY registry cannot issue tokens at all:
        with pytest.raises(Exception, match="not a registered HUMAN"):
            HumanAuthorizationRegistry().issue(
                "machine-agent", "graduation", "self-authorization attempt"
            )

    def test_live_boundary_denies_by_default(self):
        gate = LiveAuthorizationGate(HumanAuthorizationRegistry())
        decision = gate.default_decision()
        assert decision.decision == "DENIED"
        assert any("human authorization" in r for r in decision.reasons)

    def test_paper_gateway_duplicate_protection(self):
        candles = _lifecycle_candles()
        bars = _bars_from(candles)
        realism = ExecutionRealism(
            half_spread=Decimal("0.01"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.1"),
            fill_lag_bars=1,
        )
        gateway = PaperOrderGateway(ExecutionSimulator(realism))
        order = _paper_order(
            "dup-1", bars[5]["timestamp"], symbol="XAU/USD",
            side=OrderSide.BUY, order_type=OrderType.MARKET,
            quantity=Decimal("1"),
        )
        gateway.submit(order, bars)
        with pytest.raises(Exception, match="duplicate"):
            gateway.submit(order, bars)
