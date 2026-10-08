"""Benchmark runner (mandate Phase 30).

See ``__init__`` for the honesty contract. Timings are informational;
operation counts and workloads are deterministic and hash-covered.
"""

import platform
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.immutable import freeze

#: Benchmark-layer contract version.
BENCHMARK_CONTRACT_VERSION = "1.0.0"

#: Report identity prefix.
BENCHMARK_HASH_PREFIX = "bmk30."

#: Default workload sizes (deterministic; kept modest so the suite
#: runs inside the test budget while still exercising real paths).
DEFAULT_WORKLOADS: dict[str, int] = {
    "ingestion_candles": 200,
    "pit_candles": 200,
    "feature_candles": 200,
    "strategy_evaluations": 2000,
    "backtest_bars": 60,
    "portfolio_symbols": 8,
    "risk_orders": 500,
    "paper_orders": 100,
    "orchestration_dispatches": 200,
}


class BenchmarkError(ValueError):
    """Raised when a benchmark case violates its contract."""


class BenchmarkCase(BaseModel):
    """One benchmark case: declarative workload + runner."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    workload: dict[str, int]
    operations: int = Field(ge=1)

    @field_validator("workload")
    @classmethod
    def _freeze_workload(cls, v: dict) -> dict:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v


class BenchmarkResult(BaseModel):
    """One measured case result (timings informational)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    operations: int = Field(ge=1)
    elapsed_seconds: float = Field(ge=0.0)
    ops_per_second: float = Field(ge=0.0)
    detail: str = ""


class BenchmarkReport(BaseModel):
    """The composed benchmark report.

    ``report_hash`` covers case names + workloads + operation counts
    ONLY — never timings — so the same workload is the same report
    identity on any machine, while timings remain informational.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    results: tuple[BenchmarkResult, ...] = ()
    environment: dict[str, str] = Field(
        default_factory=dict, validate_default=True
    )
    no_trade_capable: bool = False

    @field_validator("environment")
    @classmethod
    def _freeze_environment(cls, v: dict) -> dict:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    @property
    def report_hash(self) -> str:
        payload = {
            "contract_version": BENCHMARK_CONTRACT_VERSION,
            "cases": [
                {
                    "name": r.name,
                    "operations": r.operations,
                }
                for r in self.results
            ],
            "no_trade_capable": self.no_trade_capable,
        }
        return BENCHMARK_HASH_PREFIX + deterministic_hash(payload)


# ---------------------------------------------------------------------------
# Synthetic workload factories (deterministic, H-1-hygiene compliant)
# ---------------------------------------------------------------------------


def _ts(day: int, hour: int = 10, minute: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, minute, tzinfo=UTC)


def _explicit_provider_ts(day: int) -> datetime:
    """EXPLICIT provider_timestamp — never the F-04 unset default."""
    return _ts(day, 9, 55)


def _make_candles(n: int) -> list:
    """Deterministic synthetic OHLCV series (valid, explicit stamps)."""
    from data_engine.schemas import Candle, Timeframe

    candles = []
    base = 100.0
    origin = _ts(1, 10)
    for i in range(n):
        base = base * 1.001 + (i % 7) * 0.05
        o = round(base, 4)
        c = round(base * 1.002 + 0.1, 4)
        h = round(max(o, c) + 0.5, 4)
        low = round(min(o, c) - 0.5, 4)
        day_ts = origin + timedelta(days=i)
        candles.append(
            Candle(
                timestamp=day_ts,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=1000.0 + (i % 13) * 10.0,
                timeframe=Timeframe.D1,
                provider_timestamp=day_ts - timedelta(minutes=5),
            )
        )
    return candles


def _make_dataset(candles: Sequence):
    """Wrap candles in a canonical Dataset (REAL evidence provenance)."""
    from data_engine.schemas import (
        AssetClass,
        Dataset,
        DatasetVersion,
        EvidenceProvenance,
        Instrument,
        ProvenanceRecord,
    )

    instrument = Instrument(
        symbol="XAU/USD",
        asset_class=AssetClass.METAL,
        base_asset="XAU",
        quote_asset="USD",
        exchange="OTC",
    )
    start = candles[0].timestamp if candles else _ts(1)
    end = candles[-1].timestamp if candles else _ts(1)
    provenance = ProvenanceRecord(
        dataset_id="bench-ds",
        dataset_version="v1.0.0",
        provider="benchmark",
        source="synthetic",
        instrument=instrument,
        timeframe=candles[0].timeframe if candles else None,
        start_timestamp=start,
        end_timestamp=end,
        retrieval_timestamp=_ts(1),  # FIXED stamp — no wall clock
        timezone="UTC",
        evidence_provenance=EvidenceProvenance("REAL"),
    )
    return Dataset(
        dataset_id="bench-ds",
        version=DatasetVersion(
            dataset_id="bench-ds",
            version="v1.0.0",
            source="benchmark",
            instrument=instrument,
            timeframe=candles[0].timeframe if candles else None,
            time_period_start=start,
            time_period_end=end,
            ingestion_version="1.0",
            transformation_version="1.0",
            validation_version="1.0",
        ),
        candles=list(candles),
        provenance=provenance,
        total_rows=len(candles),
    )


class _DuckVersion:
    def __init__(self, version: str = "v1") -> None:
        self.version = version


class _DuckDataset:
    """Duck-typed dataset for the PIT layer (never imports Phase 3)."""

    def __init__(self, candles: Sequence) -> None:
        self.candles = list(candles)
        self.dataset_id = "bench-pit"
        self.version = _DuckVersion("v1")


def _make_sidecars(n: int, candles: Sequence) -> dict[int, Any]:
    """Sidecars derived from the candle timestamps themselves."""
    from data_engine.pit.sidecar import PitSidecar

    sidecars: dict[int, Any] = {}
    for i in range(min(n, len(candles))):
        event = candles[i].timestamp
        sidecars[i] = PitSidecar(
            dataset_id="bench-pit",
            dataset_version="v1",
            event_time=event,
            observation_time=event + timedelta(minutes=30),
            publication_time=event + timedelta(hours=6),
            effective_time=event,
        )
    return sidecars


# ---------------------------------------------------------------------------
# Benchmark suite
# ---------------------------------------------------------------------------


class BenchmarkSuite:
    """Runs the mandated benchmark surfaces over real components."""

    def __init__(self, workloads: Optional[Mapping[str, int]] = None) -> None:
        self._workloads = dict(workloads or DEFAULT_WORKLOADS)

    @property
    def workloads(self) -> dict[str, int]:
        return dict(self._workloads)

    # -- individual cases ---------------------------------------------------

    def _time(self, fn: Callable[[], Any]) -> tuple[float, Any]:
        start = time.perf_counter()
        outcome = fn()
        elapsed = time.perf_counter() - start
        return elapsed, outcome

    def run_ingestion(self) -> BenchmarkResult:
        from data_engine.validation import DataValidator

        n = self._workloads["ingestion_candles"]
        candles = _make_candles(n)

        def work() -> int:
            dataset = _make_dataset(candles)
            validator = DataValidator()
            results = validator.validate_dataset(dataset)
            failed = sum(
                1 for r in results if r.status.value not in {"valid", "VALID"}
            )
            if failed:
                raise BenchmarkError(
                    f"ingestion benchmark produced {failed} invalid candles"
                )
            return n

        elapsed, ops = self._time(work)
        return BenchmarkResult(
            name="data_ingestion",
            operations=ops,
            elapsed_seconds=elapsed,
            ops_per_second=ops / elapsed if elapsed > 0 else float(ops),
            detail=f"candle construction + dataset validation ({n} candles)",
        )

    def run_pit_query(self) -> BenchmarkResult:
        from data_engine.pit.tiebreaker import TieBreakerPolicy
        from data_engine.pit.view import PitViewBuilder

        n = self._workloads["pit_candles"]
        candles = _make_candles(n)
        dataset = _DuckDataset(candles)
        cutoff = candles[-1].timestamp + timedelta(hours=23)
        sidecars = _make_sidecars(n, candles)
        tie_breaker = TieBreakerPolicy(
            name="ts-order", version="1.0.0", keys=("timestamp",)
        )

        def work() -> int:
            view = PitViewBuilder().build(
                dataset, cutoff, sidecars, tie_breaker
            )
            return len(view.items)

        elapsed, included = self._time(work)
        return BenchmarkResult(
            name="pit_query",
            operations=n,
            elapsed_seconds=elapsed,
            ops_per_second=n / elapsed if elapsed > 0 else float(n),
            detail=f"cutoff filtering ({n} items, {included} included)",
        )

    def run_feature_generation(self) -> BenchmarkResult:
        from data_engine.quant.features import FeaturePipeline, FeatureSpec

        n = self._workloads["feature_candles"]
        candles = _make_candles(n)
        # FeaturePipeline consumes duck-typed mappings (timestamp/close).
        rows = [
            {"timestamp": c.timestamp, "close": c.close} for c in candles
        ]
        pipeline = FeaturePipeline(
            specs=(
                FeatureSpec(
                    output_name="sma_5",
                    indicator="sma",
                    parameters={"period": 5},
                ),
                FeatureSpec(
                    output_name="ema_5",
                    indicator="ema",
                    parameters={"period": 5},
                ),
            )
        )
        as_of = candles[-1].timestamp + timedelta(hours=12)

        def work() -> int:
            dataset = pipeline.compute(rows, as_of)
            return len(dataset.rows)

        elapsed, rows = self._time(work)
        return BenchmarkResult(
            name="feature_generation",
            operations=n,
            elapsed_seconds=elapsed,
            ops_per_second=n / elapsed if elapsed > 0 else float(n),
            detail=f"PIT feature pipeline ({n} candles, {rows} rows)",
        )

    def run_strategy_evaluation(self) -> BenchmarkResult:
        from data_engine.strategy.schemas import EntryCondition

        m = self._workloads["strategy_evaluations"]
        conditions = [
            EntryCondition(indicator="momentum_5", operator=">", threshold=t)
            for t in (0.0, 0.25, 0.5)
        ]
        values = [float(i % 100) / 100.0 for i in range(m)]

        def work() -> int:
            evaluations = 0
            for i, value in enumerate(values):
                cond = conditions[i % len(conditions)]
                cond.evaluate(value)
                evaluations += 1
            return evaluations

        elapsed, ops = self._time(work)
        return BenchmarkResult(
            name="strategy_evaluation",
            operations=ops,
            elapsed_seconds=elapsed,
            ops_per_second=ops / elapsed if elapsed > 0 else float(ops),
            detail=f"frozen condition comparator ({ops} evaluations)",
        )

    def run_backtest(self) -> BenchmarkResult:
        from data_engine.strategy.backtest import BacktestEngine

        n = self._workloads["backtest_bars"]
        candles = _make_candles(n)
        dataset = _make_dataset(candles)

        def work() -> int:
            engine = BacktestEngine()
            result = engine.run(_bench_strategy_spec(), dataset)
            return len(dataset.candles)

        elapsed, bars = self._time(work)
        return BenchmarkResult(
            name="backtest",
            operations=bars,
            elapsed_seconds=elapsed,
            ops_per_second=bars / elapsed if elapsed > 0 else float(bars),
            detail=f"frozen Phase 3 engine ({bars} bars)",
        )

    def run_portfolio(self) -> BenchmarkResult:
        from data_engine.risk.engine import RiskEngine, RiskLimits
        from data_engine.risk.portfolio import PortfolioConstructor

        k = self._workloads["portfolio_symbols"]
        limits = RiskLimits(
            max_position_units=Decimal("100"),
            max_leverage=Decimal("3"),
            max_single_asset_weight=Decimal("0.4"),
            max_sector_weight=Decimal("0.8"),
            max_portfolio_heat=Decimal("1.0"),
        )
        engine = RiskEngine(limits, trip_on_breach=False)
        constructor = PortfolioConstructor(engine)
        vols = {
            f"SYM{i}": Decimal("0.1") + Decimal(i) * Decimal("0.02")
            for i in range(k)
        }
        sectors = {f"SYM{i}": f"sector-{i % 2}" for i in range(k)}

        def work() -> int:
            allocation = constructor.allocate(
                vols, Decimal("1.0"), sectors=sectors
            )
            return len(allocation.weights)

        elapsed, symbols = self._time(work)
        return BenchmarkResult(
            name="portfolio_construction",
            operations=symbols,
            elapsed_seconds=elapsed,
            ops_per_second=symbols / elapsed if elapsed > 0 else float(symbols),
            detail=f"inverse-volatility + limit gauntlet ({symbols} symbols)",
        )

    def run_risk(self) -> BenchmarkResult:
        from data_engine.risk.engine import RiskEngine, RiskLimits

        m = self._workloads["risk_orders"]
        limits = RiskLimits(
            max_position_units=Decimal("100"),
            max_leverage=Decimal("3"),
            max_single_asset_weight=Decimal("0.4"),
            max_sector_weight=Decimal("0.8"),
            max_portfolio_heat=Decimal("1.0"),
        )
        engine = RiskEngine(limits, trip_on_breach=False)
        units = [Decimal("1") + Decimal(i % 10) for i in range(m)]

        def work() -> int:
            for unit in units:
                engine.check_order("XAU/USD", unit)
            return len(units)

        elapsed, ops = self._time(work)
        return BenchmarkResult(
            name="risk_evaluation",
            operations=ops,
            elapsed_seconds=elapsed,
            ops_per_second=ops / elapsed if elapsed > 0 else float(ops),
            detail=f"hard-limit order checks ({ops} orders)",
        )

    def run_paper_trading(self) -> BenchmarkResult:
        from data_engine.paper.models import OrderSide, OrderType, PaperOrder
        from data_engine.paper.simulator import (
            ExecutionRealism,
            ExecutionSimulator,
        )
        from data_engine.paper.gateway import PaperOrderGateway

        # RT-F12 correction: the benchmark paper-orders workload now
        # routes through the AUTHORITATIVE PaperOrderGateway (duplicate
        # protection + lifecycle records) instead of calling the
        # simulator directly. This workload is RESEARCH-ONLY
        # performance measurement — it is NOT a trading path and must
        # never be confused with the authoritative runtime chain
        # (data_engine.runtime.TradingRuntime), which is the only
        # path with order authority.
        m = self._workloads["paper_orders"]
        candles = _make_candles(30)
        bars = [
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
        realism = ExecutionRealism(
            half_spread=Decimal("0.01"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.1"),
            fill_lag_bars=1,
        )
        simulator = ExecutionSimulator(realism)
        gateway = PaperOrderGateway(simulator)
        orders = [
            PaperOrder(
                client_order_id=f"bench-{i}",
                symbol="XAU/USD",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=Decimal("1"),
                submitted_at=bars[i % 20]["timestamp"],
            )
            for i in range(m)
        ]

        def work() -> int:
            fills = 0
            for order in orders:
                # RT-F12: through the authoritative gateway (not the
                # simulator directly). A GatewayError from duplicate
                # ids or realism rejection is counted as a non-fill —
                # benchmark semantics, honestly reported.
                try:
                    record = gateway.submit(order, bars)
                    if record.fill is not None:
                        fills += 1
                except Exception:
                    continue
            return len(orders)

        elapsed, ops = self._time(work)
        return BenchmarkResult(
            name="paper_trading",
            operations=ops,
            elapsed_seconds=elapsed,
            ops_per_second=ops / elapsed if elapsed > 0 else float(ops),
            detail=f"paper gateway submit path ({ops} orders, RT-F12 contained)",
        )

    def run_orchestration(self) -> BenchmarkResult:
        from data_engine.hermes.contracts import (
            AgentContract,
            AgentPermission,
        )
        from data_engine.hermes.orchestrator import (
            HermesOrchestrator,
            TaskAssignment,
        )

        m = self._workloads["orchestration_dispatches"]
        orchestrator = HermesOrchestrator()
        orchestrator.register_agent(
            AgentContract(
                agent_id="researcher-1",
                role="researcher",
                permissions=frozenset(
                    {AgentPermission.READ_MARKET_DATA}
                ),
            )
        )
        assignments = [
            TaskAssignment(
                task_id=f"bench-task-{i}",
                agent_id="researcher-1",
                task_kind="read",
                required_permission=AgentPermission.READ_MARKET_DATA,
                description="benchmark dispatch",
            )
            for i in range(m)
        ]

        def work() -> int:
            dispatched = 0
            for assignment in assignments:
                entry = orchestrator.dispatch(assignment)
                if entry.action == "dispatch":
                    dispatched += 1
            return dispatched

        elapsed, dispatched = self._time(work)
        return BenchmarkResult(
            name="agent_orchestration",
            operations=m,
            elapsed_seconds=elapsed,
            ops_per_second=m / elapsed if elapsed > 0 else float(m),
            detail=f"Hermes dispatch ({m} assignments, {dispatched} ok)",
        )

    def run_no_trade_capability(self) -> BenchmarkResult:
        """The system chooses NO TRADE when no opportunity exists."""
        from data_engine.discovery import (
            CandidateEvaluator,
            CandidateValidator,
            RuleBasedGenerator,
            RuleTemplate,
            SignalAction,
        )

        template = RuleTemplate(
            template_id="bench-no-trade",
            indicator="momentum_5",
            entry_operator=">",
            entry_thresholds=(0.9,),
            exit_thresholds=(0.0,),
        )
        candidates = RuleBasedGenerator([template]).generate(
            hypothesis_hash="h" * 64,
            dataset_hash="d" * 64,
            instrument="XAU/USD",
            timeframe="D1",
        )
        validated = CandidateValidator().validate(
            candidates[0],
            available_history_bars=30,
            available_feature_outputs=["momentum_5"],
        )

        def work() -> int:
            # Flat market: momentum 0.0 never crosses the 0.9 threshold.
            decision = CandidateEvaluator().evaluate(
                validated, {"momentum_5": 0.0}
            )
            if decision.action is not SignalAction.NO_TRADE:
                raise BenchmarkError(
                    "NO-TRADE capability failed: flat market must yield "
                    "NO TRADE, not a forced entry"
                )
            return 1

        elapsed, ops = self._time(work)
        return BenchmarkResult(
            name="no_trade_capability",
            operations=ops,
            elapsed_seconds=elapsed,
            ops_per_second=1.0 / elapsed if elapsed > 0 else 1.0,
            detail="flat conditions → NO TRADE (not a forced trade)",
        )

    # -- composition ----------------------------------------------------------

    def run_all(self) -> BenchmarkReport:
        results = (
            self.run_ingestion(),
            self.run_pit_query(),
            self.run_feature_generation(),
            self.run_strategy_evaluation(),
            self.run_backtest(),
            self.run_portfolio(),
            self.run_risk(),
            self.run_paper_trading(),
            self.run_orchestration(),
            self.run_no_trade_capability(),
        )
        environment = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        }
        return BenchmarkReport(
            results=results,
            environment=environment,
            no_trade_capable=True,
        )


def _bench_strategy_spec():
    """A minimal valid frozen Phase 3 spec for the backtest benchmark."""
    import json

    from data_engine.strategy.schemas import EntryCondition, StrategySpec

    entry = EntryCondition(
        indicator="close", operator=">", threshold=90.0
    )
    return StrategySpec(
        strategy_id="bench-strategy-1",
        strategy_version="3.0.0",
        strategy_name="benchmark",
        instrument="XAU/USD",
        timeframe="D1",
        entry_conditions_serialized=json.dumps(
            [entry.to_dict()], sort_keys=True
        ),
        position_sizing_serialized=json.dumps(
            {"method": "fixed", "fixed_quantity": 1.0}, sort_keys=True
        ),
        required_indicators=["close"],
        author="benchmark-suite",
    )


def build_default_suite(
    workloads: Optional[Mapping[str, int]] = None,
) -> BenchmarkSuite:
    """Construct the default benchmark suite."""
    return BenchmarkSuite(workloads)
