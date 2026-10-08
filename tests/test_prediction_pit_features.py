"""Prediction Intelligence acceptance tests — PIT correctness & leakage.

Mandate test-matrix coverage (§47):

- T-PRED-001  PIT prediction: only candles at/before the cutoff are used
- T-PRED-002  future leakage: differing post-cutoff tail leaves the
              prediction inputs unchanged
- T-PRED-003  label leakage: label/feature boundary is structural
- T-PRED-004  survivorship leakage: PIT universe membership
- T-PRED-005  revision leakage: later-arriving duplicate bars are dropped
- T-PRED-016  horizon separation: labels differ across horizons; windows
              stay disjoint from feature sources
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.prediction.data_access import (
    pit_candle_view,
    universe_at,
)
from data_engine.prediction.features import (
    build_feature_rows,
    feature_data_hash,
)
from data_engine.prediction.labels import (
    CrashLabelDefinition,
    assert_label_feature_boundary,
    compute_crash_labels,
    forward_max_drawdown,
)
from data_engine.prediction.contracts import PredictionContractError


def utc_day(offset: int) -> datetime:
    return datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=offset)


def make_candles(closes, start=0):
    return [
        {"timestamp": utc_day(start + i), "close": close}
        for i, close in enumerate(closes)
    ]


def flat_closes(n=60, level=100.0):
    return [level] * n


# ─── T-PRED-001: PIT prediction uses only past candles ───


def test_t_pred_001_pit_view_excludes_future_candles():
    closes = flat_closes(40)
    candles = make_candles(closes)
    cutoff = utc_day(19)
    view = pit_candle_view(candles, cutoff)
    assert view.visible_count == 20
    assert view.dropped_future_bars == 20
    assert view.bars[-1]["timestamp"] <= cutoff


def test_t_pred_001_features_unchanged_when_future_candles_appended():
    """The exact FE-02 discipline of feat6., applied to pred features:
    identical pre-cutoff closes + a differing post-cutoff tail ->
    IDENTICAL feature data hash."""
    closes = flat_closes(50)
    candles_a = make_candles(closes)
    candles_b = make_candles(closes) + make_candles(
        [55.0, 40.0, 20.0], start=50
    )  # a catastrophic future tail must be invisible at the cutoff
    cutoff = utc_day(49)

    def features_at_cutoff(candles):
        view = pit_candle_view(candles, cutoff)
        rows = build_feature_rows(
            [bar["close"] for bar in view.bars],
            timestamps=[bar["timestamp"] for bar in view.bars],
        )
        return feature_data_hash(rows)

    assert features_at_cutoff(candles_a) == features_at_cutoff(candles_b)


# ─── T-PRED-002: no future data in features ───


def test_t_pred_002_future_tail_cannot_reach_features():
    base = flat_closes(40, level=100.0)
    tampered = list(base)
    tampered[35:] = [10.0] * 5  # rewrite the future tail
    cutoff = utc_day(34)
    hashes = []
    for closes in (base, tampered):
        view = pit_candle_view(make_candles(closes), cutoff)
        rows = build_feature_rows([b["close"] for b in view.bars])
        hashes.append(feature_data_hash(rows))
    assert hashes[0] == hashes[1]


def test_t_pred_002_cutoff_must_be_timezone_aware():
    with pytest.raises(PredictionContractError):
        pit_candle_view(make_candles(flat_closes(5)), datetime(2020, 1, 1))


# ─── T-PRED-003: label/feature boundary is structural ───


def test_t_pred_003_boundary_holds_for_real_rows():
    closes = flat_closes(60)
    definition = CrashLabelDefinition(
        threshold=0.20, measurement_window=10, forward_horizon=20,
        asset_scope="TEST", calibration_period="2020",
    )
    rows = build_feature_rows(closes)
    labels = compute_crash_labels(closes, definition)
    assert_label_feature_boundary(rows, labels)  # must NOT raise


def test_t_pred_003_boundary_violation_is_representable_only_as_error():
    from data_engine.prediction.features import FeatureRow

    closes = flat_closes(60)
    definition = CrashLabelDefinition(
        threshold=0.20, measurement_window=10, forward_horizon=20,
        asset_scope="TEST", calibration_period="2020",
    )
    labels = compute_crash_labels(closes, definition)
    forged = FeatureRow(
        row_index=30, timestamp=None,
        source_start=10, source_end=40,  # forged: overlaps the label window
        values=(0.0,) * 6,
    )
    with pytest.raises(PredictionContractError, match="LABEL LEAKAGE"):
        assert_label_feature_boundary([forged], labels)


def test_t_pred_003_label_windows_start_after_their_own_bar():
    closes = flat_closes(40)
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=5, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    labels = compute_crash_labels(closes, definition)
    for point in labels:
        assert point.window_start == point.index + 1
        assert point.window_end == point.index + definition.measurement_window


# ─── T-PRED-004: survivorship leakage / PIT universe ───


def test_t_pred_004_universe_excludes_not_yet_listed_symbols():
    cutoff = utc_day(50)
    listed = make_candles(flat_closes(60))          # listed since day 0
    future_listing = make_candles(flat_closes(30), start=100)  # day 100+
    view = universe_at(
        {"AAA": listed, "FUTURE": future_listing}, cutoff,
        min_history_bars=10,
    )
    assert view.included == ("AAA",)
    assert view.excluded_not_listed == ("FUTURE",)


def test_t_pred_004_universe_flags_insufficient_history():
    cutoff = utc_day(50)
    long_history = make_candles(flat_closes(60))
    short_history = make_candles(flat_closes(5), start=10)
    view = universe_at(
        {"LONG": long_history, "SHORT": short_history}, cutoff,
        min_history_bars=20,
    )
    assert view.included == ("LONG",)
    assert view.excluded_insufficient_history == ("SHORT",)


def test_t_pred_004_future_listed_symbol_cannot_change_membership():
    """Adding a symbol that lists AFTER the cutoff never changes the
    universe (no future universe membership, §34)."""
    cutoff = utc_day(50)
    base = {"AAA": make_candles(flat_closes(60))}
    with_future = {
        "AAA": make_candles(flat_closes(60)),
        "LATER": make_candles(flat_closes(40), start=200),
    }
    a = universe_at(base, cutoff, min_history_bars=10)
    b = universe_at(with_future, cutoff, min_history_bars=10)
    assert a.included == b.included == ("AAA",)


# ─── T-PRED-005: revision leakage ───


def test_t_pred_005_first_arrival_wins_over_revisions():
    candles = make_candles(flat_closes(30))
    revised = dict(candles[10])  # same timestamp, different close
    revised["close"] = 42.0
    doctored = list(candles) + [revised]
    view = pit_candle_view(doctored, utc_day(29))
    assert view.dropped_revision_bars == 1
    assert view.bars[10]["close"] == 100.0  # original, not the revision


def test_t_pred_005_revision_cannot_change_features():
    candles = make_candles(flat_closes(40))
    revised = dict(candles[15])
    revised["close"] = 7.0
    doctored = list(candles) + [revised]
    cutoff = utc_day(39)

    def features(cands):
        view = pit_candle_view(cands, cutoff)
        rows = build_feature_rows([b["close"] for b in view.bars])
        return feature_data_hash(rows)

    assert features(candles) == features(doctored)


# ─── T-PRED-016: horizon separation ───


def crash_path(n=60, crash_at=30, depth=0.25, width=5):
    closes = [100.0] * n
    for i in range(crash_at, min(crash_at + width, n)):
        closes[i] = 100.0 * (1.0 - depth * (i - crash_at + 1) / width)
    for i in range(crash_at + width, n):
        closes[i] = 100.0 * (1.0 - depth)
    return closes


def test_t_pred_016_labels_differ_across_horizons():
    closes = crash_path()
    short = CrashLabelDefinition(
        threshold=0.20, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    long = CrashLabelDefinition(
        threshold=0.20, measurement_window=20, forward_horizon=20,
        asset_scope="TEST", calibration_period="2020",
    )
    short_labels = {p.index: p.label for p in compute_crash_labels(closes, short)}
    long_labels = {p.index: p.label for p in compute_crash_labels(closes, long)}
    # At bar 20: the 10-bar window (21..30) misses most of the crash;
    # the 20-bar window (21..40) contains all of it.
    assert short_labels[20] is False
    assert long_labels[20] is True
    assert short_labels[25] is True  # window 26..35 sees the crash
    # Definitions are distinct identities (no hidden definition drift)
    assert short.label_definition_id != long.label_definition_id


def test_t_pred_016_label_identity_covers_every_field():
    base = dict(threshold=0.20, measurement_window=10, forward_horizon=10,
                asset_scope="TEST", calibration_period="2020")
    original = CrashLabelDefinition(**base)
    drifted = CrashLabelDefinition(**{**base, "threshold": 0.15})
    assert original.label_definition_id != drifted.label_definition_id


def test_t_pred_016_incoherent_definitions_rejected():
    with pytest.raises(ValueError):
        CrashLabelDefinition(
            threshold=0.20, measurement_window=30, forward_horizon=10,
            asset_scope="TEST", calibration_period="2020",
        )


def test_forward_max_drawdown_known_values():
    closes = [100.0, 100.0, 80.0, 80.0, 100.0]
    assert forward_max_drawdown(closes, 0, 3) == pytest.approx(0.20)
    assert forward_max_drawdown(closes, 4, 3) is None  # window unavailable


def test_unknown_outcomes_are_none_not_imputed():
    closes = flat_closes(15)
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=5, forward_horizon=5,
        asset_scope="TEST", calibration_period="2020",
    )
    labels = compute_crash_labels(closes, definition)
    assert labels[-1].label is None
    assert labels[-1].outcome_known is False
    assert labels[0].label is not None
