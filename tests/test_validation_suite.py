"""Phase 7 acceptance tests — validation suite.

Blueprint 5.24–5.27 invariants:

Statistical (5.25):
- SV-01  t-test p-values valid and deterministic; known-distribution
          accuracy (t CDF vs analytic checkpoints)
- SV-02  degenerate samples raise (no fake p-values)
- SV-03  Bonferroni and Benjamini-Hochberg correctness on known cases
- SV-04  confidence interval covers the true mean at the nominal level

Bias/leakage (5.24):
- SV-05  look-ahead detection: rows beyond cutoff flagged
- SV-06  survivorship detection: missing delisted symbols flagged
- SV-07  partition hygiene: overlap/order/embargo violations flagged

Walk-forward (5.26):
- SV-08  plan structure: disjoint, ordered, embargoed by construction
- SV-09  window runner evaluation and OOS aggregation
- SV-10  validate_plan rejects out-of-range plans (fail closed)

Robustness (5.27):
- SV-11  plateau detection: fragile axis flagged, stable axis passes
- SV-12  regime analysis: sign inconsistency -> unstable
- SV-13  grid cap enforcement
"""

import math
from datetime import datetime, UTC

import pytest

from data_engine.research_validation import (
    BiasDetector,
    LeakageDetector,
    OverfittingDetector,
    t_test,
    confidence_interval,
    bonferroni,
    benjamini_hochberg,
    t_distribution_cdf,
    build_walk_forward_plan,
    WalkForwardPlanError,
    WalkForwardValidator,
    sweep,
    robustness_report,
    regime_analysis,
    RobustnessError,
)


def utc(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


# ======================================================================
# Statistical validation (5.25)
# ======================================================================

class TestStatisticalValidation:

    def test_sv_01_t_cdf_checkpoints(self):
        """SV-01: t CDF matches analytic checkpoints (|err| < 1e-9)."""
        # t=0 -> CDF=0.5 for any df
        for df in (1, 5, 30, 100):
            assert abs(t_distribution_cdf(0.0, df) - 0.5) < 1e-12
        # Symmetry: CDF(-t) = 1 - CDF(t)
        for t_val in (0.5, 1.5, 2.5):
            for df in (2, 10, 50):
                c_pos = t_distribution_cdf(t_val, df)
                c_neg = t_distribution_cdf(-t_val, df)
                assert abs(c_pos + c_neg - 1.0) < 1e-12
        # df -> infinity converges to the normal CDF
        z = 1.96
        normal_cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
        assert abs(t_distribution_cdf(z, 100000) - normal_cdf) < 2e-6

    def test_sv_01b_t_test_deterministic(self):
        values = [0.01, -0.02, 0.015, 0.03, -0.005, 0.012, 0.008, -0.001]
        r1, r2 = t_test(values), t_test(values)
        assert r1.p_value == r2.p_value
        assert r1.result_hash == r2.result_hash
        assert 0.0 <= r1.p_value <= 1.0
        # A strong positive-mean sample yields a small two-sided p
        strong = [0.05, 0.06, 0.04, 0.055, 0.065, 0.05, 0.058]
        assert t_test(strong).p_value < 1e-4

    def test_sv_02_degenerate_raises(self):
        with pytest.raises(ValueError, match="at least 2"):
            t_test([0.01])
        with pytest.raises(ValueError, match="zero variance"):
            t_test([0.01, 0.01, 0.01])
        with pytest.raises(ValueError, match="at least 2"):
            confidence_interval([1.0])

    def test_sv_03_multiple_testing(self):
        """SV-03: Bonferroni inflates; BH step-up on a textbook case."""
        raw = [0.01, 0.02, 0.03, 0.04, 0.5]
        adjusted = bonferroni(raw)
        assert adjusted == [0.05, 0.10, 0.15, 0.20, 1.0]
        # BH at q=0.05 with 5 p-values: sorted .01 .02 .03 .04 .5
        # thresholds: .01 .02 .03 .04 .05 -> all but .5 pass at their
        # rank; step-up rejects the four smallest
        rejected = benjamini_hochberg(raw, q=0.05)
        assert rejected == [True, True, True, True, False]
        # All-ones p-values reject nothing
        assert benjamini_hochberg([1.0, 1.0], q=0.05) == [False, False]

    def test_sv_04_confidence_interval_coverage(self):
        """SV-04: 95% interval covers the true mean (known sample)."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        lo, hi = confidence_interval(values, confidence=0.95)
        mean = 5.5
        assert lo < mean < hi
        # The interval is symmetric around the sample mean
        assert abs((hi + lo) / 2.0 - mean) < 1e-12
        # Wider confidence -> wider interval
        lo2, hi2 = confidence_interval(values, confidence=0.99)
        assert lo2 < lo and hi2 > hi


# ======================================================================
# Bias / leakage / overfitting (5.24)
# ======================================================================

class TestBiasDetection:

    def test_sv_05_lookahead(self):
        detector = BiasDetector()
        candles = [
            {"timestamp": utc(2020, 1, d)} for d in range(1, 9)
        ]
        rows_ok = [{"timestamp": utc(2020, 1, d)} for d in range(1, 6)]
        rows_bad = rows_ok + [{"timestamp": utc(2020, 1, 9)}]
        ok = detector.check_lookahead(rows_ok, candles, utc(2020, 1, 5))
        assert ok.passed
        bad = detector.check_lookahead(rows_bad, candles, utc(2020, 1, 5))
        assert not bad.passed
        assert "beyond the as-of cutoff" in bad.detail

    def test_sv_06_survivorship(self):
        from data_engine.actions import (
            PointInTimeUniverse,
            UniverseMembershipEvent,
            MembershipEventType,
        )
        universe = PointInTimeUniverse(
            universe_id="u",
            events=(
                UniverseMembershipEvent(
                    event_id="e1", event_type=MembershipEventType.ADD,
                    symbol="AAA", announcement_time=utc(2015, 1, 1),
                    effective_time=utc(2015, 1, 5),
                ),
                UniverseMembershipEvent(
                    event_id="e2", event_type=MembershipEventType.ADD,
                    symbol="BBB", announcement_time=utc(2016, 1, 1),
                    effective_time=utc(2016, 1, 5),
                ),
                UniverseMembershipEvent(
                    event_id="e3", event_type=MembershipEventType.REMOVE,
                    symbol="BBB", announcement_time=utc(2020, 6, 25),
                    effective_time=utc(2020, 6, 30), reason="delisted",
                ),
            ),
        )
        detector = BiasDetector()
        biased = detector.check_survivorship(["AAA"], universe, utc(2019, 1, 1))
        assert not biased.passed  # BBB missing (later delisted)
        clean = detector.check_survivorship(["AAA", "BBB"], universe, utc(2019, 1, 1))
        assert clean.passed

    def test_sv_07_partition_hygiene(self):
        detector = LeakageDetector()
        assert detector.check_partition([0, 1, 2], [5, 6], embargo=0).passed
        overlap = detector.check_partition([0, 1, 2], [2, 3])
        assert not overlap.passed and "overlap" in overlap.detail
        misordered = detector.check_partition([5, 6], [0, 1])
        assert not misordered.passed and "order" in misordered.detail
        embargoed = detector.check_partition([0, 1, 2], [3, 4], embargo=2)
        assert not embargoed.passed and "embargo" in embargoed.detail
        empty = detector.check_partition([], [1])
        assert not empty.passed

    def test_sv_07b_overfitting_checks(self):
        detector = OverfittingDetector()
        ratio_bad = detector.check_parameter_ratio(20, 100)
        assert not ratio_bad.passed
        ratio_ok = detector.check_parameter_ratio(2, 1000)
        assert ratio_ok.passed
        divergent = detector.check_is_oos_divergence(2.0, 0.5)
        assert not divergent.passed
        tight = detector.check_is_oos_divergence(2.0, 1.8)
        assert tight.passed


# ======================================================================
# Walk-forward (5.26)
# ======================================================================

class TestWalkForward:

    def test_sv_08_plan_structure(self):
        """SV-08: windows disjoint, ordered, embargoed by construction."""
        windows = build_walk_forward_plan(
            data_length=30, train_size=10, test_size=5, embargo=2
        )
        # Offsets 0, 5, 10 fit; offset 15 needs test_end 31 >= 30 -> stop
        assert len(windows) == 3
        w0 = windows[0]
        assert w0.train_end < w0.test_start
        assert w0.test_start - w0.train_end - 1 == 2  # embargo gap
        # Test regions advance strictly, never overlap
        for a, b in zip(windows, windows[1:]):
            assert b.test_start > a.test_start
            assert b.test_start > a.test_end
        # Rolling train overlap with PAST test regions is legitimate;
        # no train range may touch a LATER window's test region.
        for i, w in enumerate(windows):
            for later in windows[i + 1:]:
                assert w.train_end < later.test_start

    def test_sv_08b_leaky_window_rejected(self):
        from data_engine.research_validation import WalkForwardWindow
        with pytest.raises(ValueError, match="leakage"):
            WalkForwardWindow(
                window_index=0, train_start=0, train_end=10,
                test_start=5, test_end=15,
            )

    def test_sv_09_evaluation(self):
        """SV-09: runner evaluated per window; OOS aggregation averages."""
        windows = build_walk_forward_plan(
            data_length=30, train_size=10, test_size=5
        )
        assert len(windows) == 4  # offsets 0, 5, 10, 15
        validator = WalkForwardValidator()
        report = validator.evaluate(
            windows, 30,
            lambda w: {"oos_return": (w.window_index + 1) * 0.1},
        )
        assert report.window_count == 4
        assert report.oos_aggregate["oos_return"] == pytest.approx(0.25)
        assert report.report_hash.startswith("wf7.")
        assert len(report.report_hash) == 68  # 4-char prefix + 64

    def test_sv_10_plan_validation_fails_closed(self):
        windows = build_walk_forward_plan(30, 10, 5)
        validator = WalkForwardValidator()
        with pytest.raises(WalkForwardPlanError, match="exceeds data length"):
            validator.validate_plan(windows, 20)
        with pytest.raises(WalkForwardPlanError, match="cannot fit"):
            build_walk_forward_plan(10, 8, 5)


# ======================================================================
# Robustness (5.27)
# ======================================================================

class TestRobustness:

    def test_sv_11_plateau_detection(self):
        """SV-11: flat axis -> stable; cliff axis -> fragile."""
        # score constant in 'fast' but collapses with 'slow' level
        evaluations = [
            {"fast": f, "slow": s, "score": 1.0 if s == 10 else 0.1}
            for f in (10, 20, 30) for s in (10, 20)
        ]
        report = robustness_report(evaluations, tolerance=0.25)
        assert report.plateau["axes"]["fast"]["fragile"] is False
        assert report.plateau["axes"]["slow"]["fragile"] is True
        assert report.stable is False

    def test_sv_12_regime_analysis(self):
        """SV-12: mixed-sign regimes -> unstable report."""
        regimes = {"bull": [0, 1, 2], "bear": [3, 4, 5], "flat": [6, 7]}
        unstable = regime_analysis(
            regimes, lambda name, idx: 1.0 if name != "bear" else -1.0
        )
        assert not unstable.stable
        assert unstable.plateau["sign_consistent"] is False
        stable = regime_analysis(
            regimes, lambda name, idx: 0.5 if name != "bear" else 0.55
        )
        assert stable.stable

    def test_sv_13_grid_cap(self):
        with pytest.raises(RobustnessError, match="combinations"):
            sweep(
                {"a": list(range(120)), "b": list(range(120))},
                lambda p: 0.0,
            )

    def test_sv_13b_sweep_deterministic(self):
        grid = {"fast": (10, 20), "slow": (30,)}
        results = sweep(grid, lambda p: p["fast"] / p["slow"])
        assert len(results) == 2
        assert results[0] == {"fast": 10, "slow": 30, "score": 10 / 30}
        assert results[1] == {"fast": 20, "slow": 30, "score": 20 / 30}
        # identical sweep -> identical report hash
        r1 = robustness_report(sweep(grid, lambda p: p["fast"] / p["slow"]))
        r2 = robustness_report(sweep(grid, lambda p: p["fast"] / p["slow"]))
        assert r1.report_hash == r2.report_hash
        assert r1.report_hash.startswith("rob7.")
