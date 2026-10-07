"""Performance benchmark suite (mandate Phase 30, blueprint scale).

Benchmarks the mandated workload surfaces:

- data ingestion (candle construction + dataset validation)
- PIT queries (PitViewBuilder cutoff filtering)
- feature generation (Phase 6 FeaturePipeline)
- strategy evaluation (frozen Phase 3 condition comparator)
- backtesting (frozen Phase 3 BacktestEngine)
- portfolio construction (Phase 8 inverse-volatility allocator)
- risk evaluation (Phase 8 hard-limit engine)
- paper trading (Phase 11 execution simulator)
- agent orchestration (Phase 9 Hermes dispatch)

Honesty contract (no false assurance):

- The DETERMINISTIC part of every benchmark is its WORKLOAD and
  OPERATION COUNT: same input → same operations, every run, every
  process. ``report_hash`` covers workloads + operation counts only.
- Elapsed times are INFORMATIONAL (machine-dependent) and are
  deliberately EXCLUDED from the report identity.
- Every case exercises the REAL production component — no stubs, no
  mocks, no timing-only loops.
- The suite asserts NO-TRADE capability: the system must be able to
  choose NO TRADE when no valid opportunity exists (blueprint 5.60
  invariant; not a fixed trade-count objective).
- Synthetic benchmark candles always carry an EXPLICIT
  ``provider_timestamp`` (H-1 containment hygiene: the frozen
  ``Candle.to_hash()`` unset path is never exercised here).
"""

from data_engine.benchmarks.runner import (
    BENCHMARK_CONTRACT_VERSION,
    BENCHMARK_HASH_PREFIX,
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkSuite,
    DEFAULT_WORKLOADS,
    build_default_suite,
)

__all__ = [
    "BENCHMARK_CONTRACT_VERSION",
    "BENCHMARK_HASH_PREFIX",
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkResult",
    "BenchmarkSuite",
    "DEFAULT_WORKLOADS",
    "build_default_suite",
]
