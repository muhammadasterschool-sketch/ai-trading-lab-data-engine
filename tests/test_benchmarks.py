"""Benchmark suite tests (mandate Phase 30).

Honesty gates: real components (no stubs), deterministic operation
counts, report identity excludes timings, NO-TRADE capability proven.
"""

import pytest

from data_engine.benchmarks import (
    BENCHMARK_HASH_PREFIX,
    DEFAULT_WORKLOADS,
    BenchmarkSuite,
    build_default_suite,
)


class TestBenchmarkSuite:
    def test_all_mandated_surfaces_present(self):
        report = build_default_suite().run_all()
        names = {r.name for r in report.results}
        assert names == {
            "data_ingestion",
            "pit_query",
            "feature_generation",
            "strategy_evaluation",
            "backtest",
            "portfolio_construction",
            "risk_evaluation",
            "paper_trading",
            "agent_orchestration",
            "no_trade_capability",
        }

    def test_every_case_reports_positive_operations(self):
        report = build_default_suite().run_all()
        for result in report.results:
            assert result.operations >= 1, result.name
            assert result.elapsed_seconds >= 0.0
            assert result.ops_per_second >= 0.0

    def test_operation_counts_are_deterministic(self):
        """Same workload → same operation counts, every run."""
        a = build_default_suite().run_all()
        b = build_default_suite().run_all()
        ops_a = {r.name: r.operations for r in a.results}
        ops_b = {r.name: r.operations for r in b.results}
        assert ops_a == ops_b

    def test_report_hash_excludes_timings(self):
        """Report identity covers workloads/ops only — never times.

        Two runs on the same machine with different elapsed times must
        produce the SAME report hash.
        """
        a = build_default_suite().run_all()
        b = build_default_suite().run_all()
        assert a.report_hash == b.report_hash

    def test_report_hash_format(self):
        report = build_default_suite().run_all()
        assert report.report_hash.startswith(BENCHMARK_HASH_PREFIX)
        assert len(report.report_hash) == 6 + 64  # 'bmk30.' + hex

    def test_report_hash_distinguishes_workloads(self):
        small = BenchmarkSuite(
            {**DEFAULT_WORKLOADS, "ingestion_candles": 10}
        ).run_all()
        default = build_default_suite().run_all()
        assert small.report_hash != default.report_hash

    def test_no_trade_capability_proven(self):
        report = build_default_suite().run_all()
        no_trade = [
            r for r in report.results if r.name == "no_trade_capability"
        ]
        assert no_trade and no_trade[0].operations == 1
        assert report.no_trade_capable is True

    def test_environment_recorded_informationally(self):
        report = build_default_suite().run_all()
        assert "python_version" in report.environment
        assert "platform" in report.environment

    def test_workload_override_changes_operations(self):
        small = BenchmarkSuite(
            {**DEFAULT_WORKLOADS, "risk_orders": 5}
        )
        result = small.run_risk()
        assert result.operations == 5

    def test_synthetic_candles_use_explicit_provider_timestamps(self):
        """H-1 hygiene: benchmark candles never hit the F-04 unset path."""
        from data_engine.benchmarks.runner import _make_candles

        candles = _make_candles(25)
        assert all(c.provider_timestamp is not None for c in candles)
        # And the frozen hash is therefore stable for these candles:
        hashes = {c.to_hash() for c in candles}
        assert len(hashes) == len(candles)  # all distinct, all explicit

    def test_invalid_case_fails_closed(self):
        """A case whose contract breaks raises (no silent green)."""
        suite = build_default_suite()
        # Force an impossible workload to prove the suite does not
        # fabricate results: negative counts are rejected downstream.
        with pytest.raises(Exception):
            BenchmarkSuite({"ingestion_candles": 0}).run_ingestion()
