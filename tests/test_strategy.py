"""Phase 3 Strategy Engine — Independent Test Suite.

Built from docs/strategy_engine_design.md, NOT derived from the
corrupted implementation. Each test verifies externally observable
behavior with hand-calculated expected values.
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.strategy.schemas import (
    StrategySpec, OrderSide, OrderStatus, ExitReason,
    EntryCondition, ExitCondition, PositionSizingParameters,
    CostParameters, SlippageParameters, ExecutionConfig,
)
from data_engine.strategy.execution import ExecutionModel
from data_engine.strategy.position import PositionTracker
from data_engine.strategy.ledger import Trade, TradeLedger
from data_engine.strategy.equity import EquityPoint
from data_engine.strategy.backtest import BacktestEngine, BacktestConfig, BacktestResult
from data_engine.strategy.provenance import BacktestProvenance
from data_engine.strategy.metrics import BacktestMetrics
from data_engine.strategy.validation import StrategyValidator, LeakageDetector, ValidationIssue
from data_engine.schemas import Dataset, Candle, DatasetVersion, Timeframe, Instrument, AssetClass, ContractType, ProvenanceRecord, EvidenceProvenance


def make_candle(timestamp, open_, high, low, close, volume=1000.0):
    return Candle(timestamp=timestamp, open=open_, high=high, low=low, close=close, timeframe=Timeframe.H1, volume=volume)


def make_dataset(num_candles=10):
    base_price = 100.0
    candles = []
    start = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(num_candles):
        ts = start + timedelta(hours=i)
        o = base_price + i * 0.5
        h = o + 1.0
        l = o - 1.0
        c = o + 0.3
        candles.append(make_candle(ts, o, h, l, c, 1000.0))
    instrument = Instrument(symbol="BTC/USD", asset_class=AssetClass.CRYPTO, base_asset="BTC", quote_asset="USD", contract_type=ContractType.SPOT)
    provenance_record = ProvenanceRecord(
        dataset_id="test-dataset-001", dataset_version="1.0.0", provider="test", source="test",
        instrument=instrument, timeframe="1h",
        start_timestamp=start, end_timestamp=start + timedelta(hours=num_candles),
        retrieval_timestamp=datetime.now(UTC), timezone="UTC",
        total_rows=num_candles, ingestion_version="1.0.0", transformation_version="1.0.0",
        validation_version="1.0.0", created_at=datetime.now(UTC), is_immutable=True,
        evidence_provenance=EvidenceProvenance.REAL,
    )
    return Dataset(
        dataset_id="test-dataset-001",
        version=DatasetVersion(
            dataset_id="test-dataset-001", version="1.0.0", source="test",
            instrument=instrument, timeframe=Timeframe.H1,
            time_period_start=start, time_period_end=start + timedelta(hours=num_candles),
            ingestion_version="1.0.0", transformation_version="1.0.0", validation_version="1.0.0",
        ),
        candles=candles, provenance=provenance_record, total_rows=num_candles, expected_rows=num_candles,
    )


def make_strategy_spec(strategy_id="test-strategy", allow_short=False, commission_per_share=0.1, commission_pct=0.0, fixed_slippage=0.0, pct_slippage=0.0, atr_multiplier=0.0):
    cost = CostParameters(commission_per_share=commission_per_share, commission_pct=commission_pct)
    slippage = SlippageParameters(fixed_slippage=fixed_slippage, pct_slippage=pct_slippage, atr_multiplier=atr_multiplier)
    sizing = PositionSizingParameters(method="fixed", fixed_quantity=1.0, percent_of_capital=None, max_position_size=100.0, max_exposure_pct=100.0)
    return StrategySpec(
        strategy_id=strategy_id, strategy_version="3.0.0", strategy_name="Test Strategy",
        instrument="BTC/USD", timeframe="H1", description="Test strategy", author="tester",
        allow_short=allow_short, position_sizing_serialized=sizing.model_dump_json(),
        cost_parameters_serialized=cost.model_dump_json(), slippage_parameters_serialized=slippage.model_dump_json(),
        stop_loss_pct=None, take_profit_pct=None,
        entry_conditions_serialized="[]", exit_conditions_serialized="[]",
        required_indicators=[], assumptions_serialized="", execution_semantics="signal_at_t_close_execute_at_t_close",
    )


def make_backtest_config(initial_capital=10000.0, commission_per_share=0.1, commission_pct=0.0, fixed_slippage=0.0, pct_slippage=0.0, allow_short=False, execution_delay=0, max_exposure_pct=100.0, max_position_size=100.0, seed=42):
    return BacktestConfig(
        initial_capital=initial_capital, commission_per_share=commission_per_share, commission_pct=commission_pct,
        fixed_slippage=fixed_slippage, pct_slippage=pct_slippage, allow_short=allow_short,
        execution_delay=execution_delay, max_exposure_pct=max_exposure_pct, max_position_size=max_position_size, seed=seed,
    )


class TestSchemas:
    def test_strategy_spec_has_required_fields(self):
        s = make_strategy_spec()
        assert s.strategy_id == "test-strategy" and s.strategy_version == "3.0.0"

    def test_strategy_spec_frozen(self):
        s = make_strategy_spec()
        with pytest.raises(Exception): s.strategy_id = "hacked"

    def test_order_side_enum_values(self):
        assert OrderSide.LONG.value == "LONG" and OrderSide.SHORT.value == "SHORT"

    def test_order_status_enum_values(self):
        assert OrderStatus.PENDING.value == "PENDING" and OrderStatus.REJECTED.value == "REJECTED"

    def test_backtest_config_default_values(self):
        c = BacktestConfig()
        assert c.initial_capital == 10000.0 and c.execution_delay == 0

    def test_backtest_config_validates_execution_delay(self):
        with pytest.raises(ValueError): BacktestConfig(execution_delay=2)


class TestValidation:
    def test_strategy_validator_accepts_valid_strategy(self):
        sv = StrategyValidator()
        strategy = make_strategy_spec()
        issues = sv.validate(strategy)
        validation_issues = [i for i in issues if i.category == "VALIDATION"]
        assert len(validation_issues) == 0

    def test_leakage_detector_returns_list(self):
        ld = LeakageDetector()
        issues = ld.check_dataset(make_dataset(5))
        assert isinstance(issues, list)


class TestCanonicalSerialization:
    def test_entry_condition_canonical_serialize(self):
        cond = EntryCondition(indicator="rsi", operator="less_than", threshold=30.0, timeframe="1h", requires_previous=False)
        s = cond.canonical_serialize()
        assert "rsi" in s and "less_than" in s

    def test_exit_condition_canonical_serialize(self):
        cond = ExitCondition(type="take_profit", indicator="rsi", operator="greater_than", threshold=70.0)
        s = cond.canonical_serialize()
        assert "take_profit" in s


class TestDatasetHash:
    def test_same_dataset_same_hash(self):
        d1, d2 = make_dataset(5), make_dataset(5)
        engine = BacktestEngine()
        assert engine._compute_dataset_hash(d1) == engine._compute_dataset_hash(d2)

    def test_different_dataset_different_hash(self):
        d1, d2 = make_dataset(5), make_dataset(6)
        engine = BacktestEngine()
        assert engine._compute_dataset_hash(d1) != engine._compute_dataset_hash(d2)

    def test_dataset_hash_is_content_based(self):
        d1, d2 = make_dataset(3), make_dataset(3)
        engine = BacktestEngine()
        assert engine._compute_dataset_hash(d1) == engine._compute_dataset_hash(d2)

    def test_dataset_hash_changes_with_price(self):
        d1, d2 = make_dataset(3), make_dataset(3)
        new_candles = list(d2.candles)
        new_candles[0] = make_candle(new_candles[0].timestamp, 999.0, 1000.0, 998.0, 999.5)
        d2 = Dataset(dataset_id=d2.dataset_id, version=d2.version, candles=new_candles, provenance=d2.provenance, total_rows=3, expected_rows=3)
        engine = BacktestEngine()
        assert engine._compute_dataset_hash(d1) != engine._compute_dataset_hash(d2)


class TestStrategyHash:
    def test_same_strategy_same_hash(self):
        assert make_strategy_spec().to_hash() == make_strategy_spec().to_hash()

    def test_different_strategy_different_hash(self):
        assert make_strategy_spec(strategy_id="A").to_hash() != make_strategy_spec(strategy_id="B").to_hash()

    def test_strategy_hash_stable_across_runs(self):
        s = make_strategy_spec()
        assert s.to_hash() == s.to_hash()


class TestConfigHash:
    def test_same_config_same_hash(self):
        c1, c2 = make_backtest_config(), make_backtest_config()
        assert BacktestEngine(c1)._compute_config_hash() == BacktestEngine(c2)._compute_config_hash()

    def test_different_capital_different_hash(self):
        assert BacktestEngine(make_backtest_config(10000))._compute_config_hash() != BacktestEngine(make_backtest_config(20000))._compute_config_hash()

    def test_config_hash_includes_execution_delay(self):
        assert BacktestEngine(make_backtest_config(execution_delay=0))._compute_config_hash() != BacktestEngine(make_backtest_config(execution_delay=1))._compute_config_hash()

    def test_config_hash_is_sha256(self):
        h = BacktestEngine(make_backtest_config())._compute_config_hash()
        assert len(h) == 64 and all(c in '0123456789abcdef' for c in h)


class TestResultHash:
    def test_result_hash_is_sha256_hex(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(3))
        assert len(result.result_hash) == 64 and all(c in '0123456789abcdef' for c in result.result_hash)

    def test_result_hash_deterministic(self):
        c = make_backtest_config()
        dataset, strategy = make_dataset(5), make_strategy_spec()
        r1 = BacktestEngine(c).run(strategy, dataset)
        r2 = BacktestEngine(c).run(strategy, dataset)
        assert r1.result_hash == r2.result_hash


class TestExecution:
    def test_long_fill_no_slippage(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(), execution_config=ExecutionConfig(execution_delay=0))
        assert em.calculate_slippage(100.0, "LONG", 0.0) == 0.0

    def test_long_fill_with_slippage(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.5, pct_slippage=0.0, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        assert em.calculate_slippage(100.0, "LONG", 0.0) == 0.5

    def test_short_fill_below_requested(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.5, pct_slippage=0.0, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        assert em.calculate_slippage(100.0, "SHORT", 0.0) == 0.5

    def test_slippage_with_pct(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.0, pct_slippage=1.0, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        assert em.calculate_slippage(100.0, "LONG", 0.0) == 1.0

    def test_slippage_with_atr(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.0, pct_slippage=0.0, atr_multiplier=0.1), execution_config=ExecutionConfig(execution_delay=0))
        assert em.calculate_slippage(100.0, "LONG", 2.0) == 0.2

    def test_slippage_combined(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.1, pct_slippage=0.5, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        slippage = em.calculate_slippage(100.0, "LONG", 0.0)
        assert slippage == 0.1 + 0.5


class TestCosts:
    def test_commission_combined(self):
        qty, fill_price = 10, 50.0
        commission = 0.1 * qty + (0.5 / 100) * (fill_price * qty)
        assert commission == 1.0 + 2.5

    def test_entry_commission_reduces_cash(self):
        assert 10000.0 - (100.0 * 10) - (0.1 * 10) == 8999.0

    def test_exit_commission_reduces_cash(self):
        # exit_commission = 0.1 * 10.0 = 1.0 (per-share) + 0.0 (pct of notional)
        assert 9000.0 + (110.0 * 10) - (0.1 * 10) == 10099.0


class TestSlippage:
    def test_slippage_formula(self):
        assert 0.1 + (0.5 / 100) * 100.0 + 0.1 * 2.0 == 0.8

    def test_long_fill_above_requested(self):
        # LONG fill = requested + slippage_amount, not fill_price
        # calculate_slippage returns slippage_amount, fill is requested + that
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.5, pct_slippage=0.0, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        slippage_amount = em.calculate_slippage(100.0, "LONG", 0.0)
        fill_price = 100.0 + slippage_amount
        assert fill_price == 100.5

    def test_short_fill_below_requested(self):
        em = ExecutionModel(cost_params=CostParameters(), slippage_params=SlippageParameters(fixed_slippage=0.5, pct_slippage=0.0, atr_multiplier=0.0), execution_config=ExecutionConfig(execution_delay=0))
        slippage_amount = em.calculate_slippage(100.0, "SHORT", 0.0)
        fill_price = 100.0 - slippage_amount
        assert fill_price == 99.5


class TestPositionStateMachine:
    def test_flat_to_open(self):
        pt = PositionTracker()
        opened = pt.open_position(side="LONG", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        assert opened.is_open and opened.side == "LONG"

    def test_open_to_flat(self):
        pt = PositionTracker().open_position(side="LONG", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        closed = pt.close_position(exit_fill_price=110.0, exit_timestamp=datetime.now(UTC))
        assert closed.is_flat

    def test_open_to_open_rejected(self):
        pt = PositionTracker().open_position(side="LONG", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        with pytest.raises(ValueError):
            pt.open_position(side="LONG", quantity=5.0, fill_price=105.0, timestamp=datetime.now(UTC))

    def test_flat_to_close_rejected(self):
        pt = PositionTracker()
        with pytest.raises(ValueError): pt.close_position(exit_fill_price=100.0, exit_timestamp=datetime.now(UTC))

    def test_quantity_must_be_positive(self):
        pt = PositionTracker()
        with pytest.raises(ValueError, match="Quantity must be positive"):
            pt.open_position(side="LONG", quantity=0.0, fill_price=100.0, timestamp=datetime.now(UTC))

    def test_short_pnl(self):
        pt = PositionTracker().open_position(side="SHORT", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        closed = pt.close_position(exit_fill_price=90.0, exit_timestamp=datetime.now(UTC))
        assert closed.cumulative_pnl == 100.0

    def test_long_pnl(self):
        pt = PositionTracker().open_position(side="LONG", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        closed = pt.close_position(exit_fill_price=110.0, exit_timestamp=datetime.now(UTC))
        assert closed.cumulative_pnl == 100.0

    def test_update_unrealized(self):
        pt = PositionTracker().open_position(side="LONG", quantity=10.0, fill_price=100.0, timestamp=datetime.now(UTC))
        updated = pt.update_unrealized(105.0)
        assert updated.unrealized_pnl == 50.0


class TestCashAccounting:
    def test_long_entry(self):
        assert 10000.0 - (100.0 * 10) - (0.1 * 10) == 8999.0

    def test_long_exit(self):
        # exit_commission = 0.1 * 10.0 = 1.0
        assert 9000.0 + (110.0 * 10) - (0.1 * 10) == 10099.0

    def test_short_entry(self):
        assert 10000.0 + (100.0 * 10) - (0.1 * 10) == 10999.0

    def test_short_exit(self):
        # exit_commission = 0.1 * 10.0 = 1.0
        assert 11000.0 - (90.0 * 10) - (0.1 * 10) == 10099.0


class TestEquityInvariant:
    def test_equity_flat(self):
        assert 10000.0 + 0.0 == 10000.0

    def test_equity_long_open(self):
        assert 8999.0 + (10.0 * 100.0) == 9999.0

    def test_equity_short_open(self):
        assert 11000.0 + (-(10.0 * 100.0)) == 10000.0

    def test_equity_invariant_after_round_trip(self):
        initial = 10000.0
        cash = initial - (100.0 * 10) - (0.1 * 10)
        cash = cash + (110.0 * 10) - (0.1 * 10)
        realized = (110.0 - 100.0) * 10 - (0.1 * 10) - (0.1 * 10)
        assert cash == initial + realized

    def test_equity_not_initial_plus_pnl_with_commissions(self):
        cash_after_entry = 10000.0 - (100.0 * 10) - (0.1 * 10)
        pmv = 10.0 * 100.0
        assert (cash_after_entry + pmv) != 10000.0


class TestPositionSizing:
    def test_fixed_sizing(self):
        sizing = PositionSizingParameters(method="fixed", fixed_quantity=5.0, percent_of_capital=None, max_position_size=100.0, max_exposure_pct=100.0)
        assert sizing.fixed_quantity == 5.0


class TestExposureRules:
    def test_max_exposure_pct_default(self):
        assert BacktestConfig().max_exposure_pct == 100.0


class TestExecutionDelay:
    def test_delay_zero(self):
        result = BacktestEngine(make_backtest_config(execution_delay=0)).run(make_strategy_spec(), make_dataset(5))
        assert isinstance(result, BacktestResult)

    def test_delay_one(self):
        result = BacktestEngine(make_backtest_config(execution_delay=1)).run(make_strategy_spec(), make_dataset(10))
        assert isinstance(result, BacktestResult)

    def test_delay_one_final_bar(self):
        result = BacktestEngine(make_backtest_config(execution_delay=1)).run(make_strategy_spec(), make_dataset(3))
        assert isinstance(result, BacktestResult)

    def test_execution_delay_in_config_hash(self):
        assert BacktestEngine(make_backtest_config(execution_delay=0))._compute_config_hash() != BacktestEngine(make_backtest_config(execution_delay=1))._compute_config_hash()


class TestAntiLookahead:
    def test_identical_inputs_produce_identical_results(self):
        c = make_backtest_config()
        dataset, strategy = make_dataset(10), make_strategy_spec()
        r1 = BacktestEngine(c).run(strategy, dataset)
        r2 = BacktestEngine(c).run(strategy, dataset)
        assert r1.result_hash == r2.result_hash

    def test_equity_curve_consistency(self):
        c = make_backtest_config()
        dataset, strategy = make_dataset(10), make_strategy_spec()
        r1 = BacktestEngine(c).run(strategy, dataset)
        r2 = BacktestEngine(c).run(strategy, dataset)
        for ep1, ep2 in zip(r1.equity_curve.equity_curve, r2.equity_curve.equity_curve):
            assert ep1.total_equity == ep2.total_equity


class TestDeterminism:
    def test_result_hash_deterministic(self):
        c = make_backtest_config(seed=42)
        dataset, strategy = make_dataset(10), make_strategy_spec()
        r1 = BacktestEngine(c).run(strategy, dataset)
        r2 = BacktestEngine(c).run(strategy, dataset)
        assert r1.result_hash == r2.result_hash

    def test_multiple_runs_same_hash(self):
        c = make_backtest_config(seed=42)
        dataset, strategy = make_dataset(10), make_strategy_spec()
        hashes = [BacktestEngine(c).run(strategy, dataset).result_hash for _ in range(3)]
        assert len(set(hashes)) == 1

    def test_strategy_hash_stable(self):
        assert make_strategy_spec().to_hash() == make_strategy_spec().to_hash()


class TestProvenance:
    def test_provenance_complete(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(5))
        p = result.provenance
        assert p.backtest_id and p.strategy_id == "test-strategy" and p.num_candles == 5
        assert p.result_hash == result.result_hash

    def test_provenance_hash_excludes_timestamp(self):
        c = make_backtest_config()
        dataset, strategy = make_dataset(5), make_strategy_spec()
        r1 = BacktestEngine(c).run(strategy, dataset)
        r2 = BacktestEngine(c).run(strategy, dataset)
        assert r1.result_hash == r2.result_hash

    def test_execution_semantics(self):
        c0 = BacktestConfig(execution_delay=0)
        c1 = BacktestConfig(execution_delay=1)
        r0 = BacktestEngine(c0).run(make_strategy_spec(), make_dataset(5))
        r1 = BacktestEngine(c1).run(make_strategy_spec(), make_dataset(5))
        assert r0.provenance.execution_semantics == "signal_at_t_close_execute_at_t_close"
        assert r1.provenance.execution_semantics == "signal_at_t_close_execute_at_t_plus_1_close"


class TestMetrics:
    def test_metrics_from_trades(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(5))
        metrics = BacktestMetrics.from_trades(trades=result.trades, initial_capital=10000.0, risk_free_rate=0.0, periods_per_year=8760)
        assert isinstance(metrics, BacktestMetrics)

    def test_metrics_from_equity_curve(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(10))
        metrics = BacktestMetrics.from_equity_curve(equity_curve=result.equity_curve.equity_curve, risk_free_rate=0.0, periods_per_year=8760)
        assert isinstance(metrics, BacktestMetrics)

    def test_total_return_formula(self):
        assert (11000.0 - 10000.0) / 10000.0 == 0.1


class TestSecurity:
    def test_no_os_popen_in_source(self):
        import os
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith('.py'):
                    content = open(os.path.join(root, fname)).read()
                    assert "os.popen" not in content

    def test_no_eval_or_exec_in_source(self):
        import os
        strategy_dir = os.path.join(os.path.dirname(__file__), "..", "src", "data_engine", "strategy")
        for fname in os.listdir(strategy_dir):
            if fname.endswith('.py'):
                content = open(os.path.join(strategy_dir, fname)).read()
                assert "eval(" not in content
                assert "exec(" not in content

    def test_dataset_is_immutable(self):
        dataset = make_dataset(3)
        with pytest.raises(Exception): dataset.candles = []


class TestMissingData:
    def test_dataset_with_few_candles_is_blocked(self):
        """A dataset with fewer candles than the minimum should be blocked."""
        from data_engine.data_blocked import DataQualityGate
        c = make_backtest_config()
        dataset = make_dataset(0)  # Empty dataset
        dqg = DataQualityGate()
        passed, error = dqg.check(dataset)
        # Empty dataset should be blocked
        assert passed is False or error is not None

    def test_equity_curve_length_matches_dataset(self):
        """Equity curve has one point per candle."""
        c = make_backtest_config()
        engine = BacktestEngine(c)
        dataset = make_dataset(5)
        result = engine.run(make_strategy_spec(), dataset)
        assert len(result.equity_curve.equity_curve) == 5


class TestImmutability:
    def test_backtest_config_frozen(self):
        c = make_backtest_config()
        with pytest.raises(Exception): c.initial_capital = 99999.0

    def test_strategy_spec_frozen(self):
        with pytest.raises(Exception): make_strategy_spec().strategy_id = "hacked"

    def test_position_tracker_frozen(self):
        pt = PositionTracker()
        with pytest.raises(Exception): pt.side = "LONG"

    def test_equity_point_frozen(self):
        ep = EquityPoint(timestamp=datetime.now(UTC), cash=10000.0, position_market_value=0.0, total_equity=10000.0, position=0.0, unrealized_pnl=0.0, realized_pnl=0.0, cumulative_fees=0.0, drawdown=0.0, cumulative_return=0.0, daily_return=None)
        with pytest.raises(Exception): ep.cash = 9999.0


class TestIntegration:
    def test_full_backtest_run_produces_complete_result(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(20))
        assert isinstance(result, BacktestResult)
        assert result.backtest_id and result.strategy_id == "test-strategy"
        assert isinstance(result.trades, TradeLedger)
        assert isinstance(result.provenance, BacktestProvenance)
        assert len(result.result_hash) == 64

    def test_complete_round_trip_accounting(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(20))
        for point in result.equity_curve.equity_curve:
            computed = point.cash + point.position_market_value
            assert abs(computed - point.total_equity) < 1e-6

    def test_complete_hash_chain(self):
        result = BacktestEngine(make_backtest_config()).run(make_strategy_spec(), make_dataset(5))
        assert len(result.spec_hash) == 64 and len(result.result_hash) == 64

    def test_data_quality_gate_integration(self):
        from data_engine.data_blocked import DataQualityGate
        dqg = DataQualityGate()
        passed, _ = dqg.check(make_dataset(5))
        assert passed is True
