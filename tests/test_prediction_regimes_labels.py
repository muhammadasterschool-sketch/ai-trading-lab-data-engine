"""Prediction Intelligence acceptance tests — regimes & crash labels.

Mandate test-matrix coverage (§47):

- T-PRED-014  regime transition events
- T-PRED-015  crash labeling on known price paths
plus regime-engine state coverage and crisis-sample sufficiency (§12).
"""

import pytest

from data_engine.prediction.labels import (
    CrashLabelDefinition,
    crisis_sample_status,
    compute_crash_labels,
)
from data_engine.prediction.regimes import RegimeEngine, RegimeFeatures


# ─── T-PRED-014: regime engine & transitions ───


def test_t_pred_014_regime_classification_matrix():
    engine = RegimeEngine()
    cases = [
        (RegimeFeatures(vol_20=0.040, vol_ratio=1.0, dd_depth=0.25, mom_20=0.0), "CRISIS"),
        (RegimeFeatures(vol_20=0.020, vol_ratio=2.5, dd_depth=0.12, mom_20=0.0), "STRESSED"),
        (RegimeFeatures(vol_20=0.040, vol_ratio=2.5, dd_depth=0.05, mom_20=0.0), "HIGH_VOLATILITY"),
        (RegimeFeatures(vol_20=0.003, vol_ratio=1.0, dd_depth=0.0, mom_20=0.0), "LOW_VOLATILITY"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=2.5, dd_depth=0.0, mom_20=0.0), "TRANSITION"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=1.0, dd_depth=0.0, mom_20=0.15, breadth=0.7), "RISK_ON"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=1.0, dd_depth=0.0, mom_20=-0.15, breadth=0.2), "RISK_OFF"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=1.0, dd_depth=0.0, mom_20=0.15), "TRENDING"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=1.0, dd_depth=0.0, mom_20=0.01), "RANGE"),
        (RegimeFeatures(vol_20=0.010, vol_ratio=1.0, dd_depth=0.0, mom_20=0.05), "NORMAL"),
        (RegimeFeatures(vol_20=None, vol_ratio=1.0, dd_depth=0.0, mom_20=0.0), "UNKNOWN"),
    ]
    for features, expected in cases:
        assert engine.classify(features) == expected, (
            f"{features} should classify as {expected}"
        )


def test_t_pred_014_transitions_are_recorded_as_events():
    engine = RegimeEngine()
    states = ("NORMAL", "NORMAL", "HIGH_VOLATILITY", "CRISIS", "CRISIS", "NORMAL")
    events = RegimeEngine.regime_transitions(states)
    assert [(e.index, e.from_state, e.to_state) for e in events] == [
        (2, "NORMAL", "HIGH_VOLATILITY"),
        (3, "HIGH_VOLATILITY", "CRISIS"),
        (5, "CRISIS", "NORMAL"),
    ]
    for event in events:
        assert event.engine_version == RegimeEngine.engine_version
        # ARCH-F7 correction: regime transition events carry their own
        # ``predn.`` identity namespace (previously reused ``predv.``).
        assert event.event_id.startswith("predn.")


def test_t_pred_014_classify_series_matches_pointwise():
    engine = RegimeEngine()
    seq = [
        RegimeFeatures(vol_20=0.004, vol_ratio=1.0, dd_depth=0.0, mom_20=0.0),
        RegimeFeatures(vol_20=0.040, vol_ratio=2.5, dd_depth=0.25, mom_20=0.0),
    ]
    assert engine.classify_series(seq) == (
        "LOW_VOLATILITY", "CRISIS",
    )


def test_t_pred_014_transition_timestamps_must_align():
    with pytest.raises(Exception):
        RegimeEngine.regime_transitions(("NORMAL", "CRISIS"), timestamps=[None])


# ─── T-PRED-015: crash labeling on known paths ───


def crash_path(n=120, crash_at=95, depth=0.25, width=5):
    closes = [100.0] * n
    for i in range(crash_at, min(crash_at + width, n)):
        closes[i] = 100.0 * (1.0 - depth * (i - crash_at + 1) / width)
    for i in range(crash_at + width, n):
        closes[i] = 100.0 * (1.0 - depth)
    return closes


@pytest.fixture
def crash_definition():
    return CrashLabelDefinition(
        threshold=0.20, measurement_window=20, forward_horizon=20,
        asset_scope="TEST", calibration_period="2020",
    )


def test_t_pred_015_known_path_labels(crash_definition):
    closes = crash_path()
    labels = {p.index: p.label for p in compute_crash_labels(closes, crash_definition)}
    assert labels[70] is False   # window 71..90: flat, no crash
    assert labels[80] is True    # window 81..100: contains the 25% drawdown
    assert labels[99] is False   # window 100..119: flat at the post-crash level
    assert labels[110] is None   # outcome window beyond available data


def test_t_pred_015_threshold_drives_labels(crash_definition):
    """A 25% drawdown is a crash at threshold 0.20 but not 0.30."""
    closes = crash_path()
    stricter = CrashLabelDefinition(
        threshold=0.30, measurement_window=20, forward_horizon=20,
        asset_scope="TEST", calibration_period="2020",
    )
    base = {p.index: p.label for p in compute_crash_labels(closes, crash_definition)}
    strict = {p.index: p.label for p in compute_crash_labels(closes, stricter)}
    assert base[80] is True
    assert strict[80] is False


def test_t_pred_015_crisis_sample_sufficiency(crash_definition):
    closes = crash_path()
    labels = compute_crash_labels(closes, crash_definition)
    reading = crisis_sample_status(labels, min_positive_labels=5)
    assert reading.status == "OK"
    assert reading.positive_labels >= 5
    starved = crisis_sample_status(labels, min_positive_labels=1000)
    assert starved.status == "CRISIS_SAMPLE_INSUFFICIENT"


def test_t_pred_015_flat_market_has_no_crash_labels(crash_definition):
    labels = compute_crash_labels([100.0] * 60, crash_definition)
    known = [p.label for p in labels if p.label is not None]
    assert not any(known)
