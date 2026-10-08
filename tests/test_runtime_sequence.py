"""Runtime sequence engine tests (pre-paper mandate §12).

Coverage: PIT cutoff semantics, no future leakage, boundary windows,
missing bars/gaps, irregular timestamps, horizon overlap, purge,
embargo, train/validation/test separation, walk-forward windows,
duplicate sequence ids, determinism/reproducibility.
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.runtime.sequence import (
    FEATURE_DIM,
    SequenceError,
    SequenceSpec,
    build_sequence_set,
    build_walk_forward_splits,
    train_validation_test_split,
)


def _bars(n=60, start=100.0, phase=6, drift=0.5, interval=300):
    base = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    bars = []
    price = start
    for i in range(n):
        d = drift if (i // phase) % 2 == 0 else -drift * 0.8
        o = price
        c = price + d
        bars.append({
            "timestamp": base + timedelta(seconds=interval * i),
            "open": o, "high": max(o, c) + 0.1, "low": min(o, c) - 0.1,
            "close": c, "volume": 1000.0 + i,
        })
        price = c
    return bars


SPEC = SequenceSpec(
    symbol="TEST/USD", timeframe="5m", lookback=8, horizon=2,
    feature_version="fv-1", dataset_version="dv-1",
)


class TestPITCorrectness:
    def test_features_never_beyond_cutoff(self):
        bars = _bars(40)
        for cut_index in (10, 20, 39):
            sset = build_sequence_set(
                bars, SPEC, bars[cut_index]["timestamp"], "dch",
                expected_interval_seconds=300,
            )
            for s in sset.sequences:
                assert s.anchor_timestamp <= bars[cut_index]["timestamp"]

    def test_label_requires_knowable_horizon(self):
        bars = _bars(40)
        cut = bars[20]["timestamp"]  # horizon bar 22 exists and <= cut
        sset = build_sequence_set(bars, SPEC, cut, "dch",
                                  expected_interval_seconds=300)
        labeled = {s.anchor_timestamp: s for s in sset.sequences if s.target is not None}
        unlabeled = [s for s in sset.sequences if s.target is None]
        assert unlabeled, "anchors whose horizon extends past the cutoff must lack labels"
        for s in unlabeled:
            assert s.horizon_end is None
        # An anchor at index t has a label iff t + horizon <= cut index.
        for ts, s in labeled.items():
            assert s.horizon_end is not None and s.horizon_end <= cut

    def test_no_future_leakage_in_features(self):
        """Mutating future bars must not change any emitted sequence
        whose anchor precedes them (features are window-local)."""
        bars_a = _bars(40)
        bars_b = [dict(b) for b in bars_a]
        # Corrupt bars after anchor 25.
        for i in range(26, 40):
            bars_b[i]["close"] = 999.0
            bars_b[i]["high"] = 1000.0
        cut = bars_a[25]["timestamp"]
        sa = build_sequence_set(bars_a, SPEC, cut, "dch",
                                expected_interval_seconds=300)
        sb = build_sequence_set(bars_b, SPEC, cut, "dch",
                                expected_interval_seconds=300)
        fa = {s.sequence_id for s in sa.sequences}
        fb = {s.sequence_id for s in sb.sequences}
        assert fa == fb, "future corruption leaked into past features"

    def test_duplicate_timestamps_rejected(self):
        bars = _bars(20)
        bars[10] = dict(bars[9])  # duplicate
        with pytest.raises(SequenceError, match="strictly"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch")

    def test_non_monotonic_timestamps_rejected(self):
        bars = _bars(20)
        bars[10], bars[11] = bars[11], bars[10]
        with pytest.raises(SequenceError, match="strictly"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch")

    def test_naive_timestamps_rejected(self):
        bars = _bars(20)
        bars[10]["timestamp"] = bars[10]["timestamp"].replace(tzinfo=None)
        with pytest.raises(SequenceError, match="timezone-aware"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch")


class TestWindowConstruction:
    def test_boundary_window_lookback_one(self):
        spec = SequenceSpec(symbol="T/USD", timeframe="5m", lookback=1,
                            horizon=1, feature_version="fv-1",
                            dataset_version="dv-1")
        sset = build_sequence_set(_bars(10), spec, _bars(10)[-1]["timestamp"], "dch")
        assert all(len(s.features) == 1 for s in sset.sequences)

    def test_feature_dim_is_stable(self):
        sset = build_sequence_set(_bars(20), SPEC,
                                  _bars(20)[-1]["timestamp"], "dch")
        assert all(len(row) == FEATURE_DIM for s in sset.sequences for row in s.features)

    def test_missing_bars_flagged_and_strict_rejected(self):
        bars = _bars(40)
        # Remove a bar → 1.5x interval gap.
        del bars[20]
        with pytest.raises(SequenceError, match="missing bars"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch",
                               expected_interval_seconds=300)
        sset = build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch",
                                  expected_interval_seconds=300, allow_gaps=True)
        assert any(s.has_gaps for s in sset.sequences)

    def test_impossible_ohlc_rejected(self):
        bars = _bars(20)
        bars[5]["high"] = bars[5]["low"] - 10  # high < low
        with pytest.raises(SequenceError, match="impossible OHLC"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch")

    def test_non_finite_prices_rejected(self):
        bars = _bars(20)
        bars[5]["close"] = float("nan")
        with pytest.raises(SequenceError, match="not finite"):
            build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch")


class TestDeterminismAndIdentity:
    def test_reproducible_from_spec_and_cutoff(self):
        bars = _bars(50)
        a = build_sequence_set(bars, SPEC, bars[40]["timestamp"], "dch",
                               expected_interval_seconds=300)
        b = build_sequence_set(bars, SPEC, bars[40]["timestamp"], "dch",
                               expected_interval_seconds=300)
        assert a.sequence_set_id == b.sequence_set_id
        assert [s.sequence_id for s in a.sequences] == [s.sequence_id for s in b.sequences]

    def test_different_cutoff_changes_identity(self):
        bars = _bars(50)
        a = build_sequence_set(bars, SPEC, bars[40]["timestamp"], "dch")
        b = build_sequence_set(bars, SPEC, bars[41]["timestamp"], "dch")
        assert a.sequence_set_id != b.sequence_set_id

    def test_sequences_ordered_by_anchor(self):
        sset = build_sequence_set(_bars(30), SPEC,
                                  _bars(30)[-1]["timestamp"], "dch")
        anchors = [s.anchor_timestamp for s in sset.sequences]
        assert anchors == sorted(anchors)


class TestWalkForwardAndSplits:
    def test_purge_is_sequence_scaled_to_horizon(self):
        splits = build_walk_forward_splits(200, horizon=5, train_size=50,
                                           test_size=20)
        assert all(sp.purge == 5 for sp in splits)

    def test_train_test_disjoint_and_embargoed(self):
        splits = build_walk_forward_splits(200, horizon=3, train_size=50,
                                           test_size=20, embargo=2)
        for sp in splits:
            assert not (set(sp.train_indices) & set(sp.test_indices))
            assert min(sp.test_indices) - max(sp.train_indices) >= 3 + 2

    def test_insufficient_data_raises(self):
        with pytest.raises(SequenceError, match="cannot fit"):
            build_walk_forward_splits(10, horizon=3, train_size=50, test_size=20)

    def test_train_validation_test_separated_by_horizon(self):
        train, val, test = train_validation_test_split(100, horizon=3)
        assert max(train) + 1 + 3 <= min(val)
        assert max(val) + 1 + 3 <= min(test)
        assert not (set(train) & set(val) | set(val) & set(test))

    def test_arch_f8_embargo_below_label_horizon_raises(self):
        from data_engine.research_validation.walk_forward import (
            build_walk_forward_plan, WalkForwardPlanError,
        )
        with pytest.raises(WalkForwardPlanError, match="label_horizon"):
            build_walk_forward_plan(
                data_length=200, train_size=50, test_size=20,
                embargo=1, label_horizon=5,
            )
        # A horizon-scaled embargo is accepted.
        plan = build_walk_forward_plan(
            data_length=200, train_size=50, test_size=20,
            embargo=5, label_horizon=5,
        )
        assert plan

    def test_horizon_overlap_excluded_from_splits(self):
        """The purge equals the horizon: train label windows cannot
        overlap test feature windows (ARCH-F8/F12 correction)."""
        splits = build_walk_forward_splits(150, horizon=4, train_size=40,
                                           test_size=15)
        for sp in splits:
            # Last train anchor + horizon must be < first test anchor.
            assert sp.train_indices[-1] + 4 < sp.test_indices[0]


class TestSpecValidation:
    def test_invalid_lookback_rejected(self):
        with pytest.raises(Exception, match="lookback/horizon/stride"):
            SequenceSpec(symbol="T", timeframe="5m", lookback=0, horizon=1,
                         feature_version="f", dataset_version="d")

    def test_empty_bars_rejected(self):
        with pytest.raises(SequenceError, match="non-empty"):
            build_sequence_set([], SPEC, datetime(2026, 1, 1, tzinfo=UTC), "d")
