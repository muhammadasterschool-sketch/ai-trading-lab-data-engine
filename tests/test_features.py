"""Phase 6 acceptance tests — feature engineering pipeline.

Blueprint 5.21 invariants:

- FE-01  PIT correctness: candles after the as_of cutoff are invisible
- FE-02  no future data: identical pre-cutoff candles + a differing
          post-cutoff tail -> IDENTICAL feature dataset hash
- FE-03  determinism: same inputs -> same feat6. hash across pipelines
- FE-04  spec validation: unknown indicator and duplicate output names
          rejected
- FE-05  warm-up semantics: SMA(3) returns None for the first two rows
          (features never fabricate warm-up values)
- FE-06  empty visible window fails closed
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.quant.features import (
    FeatureSpec,
    FeatureDataset,
    FeaturePipeline,
    FeaturePipelineError,
    FEATURE_PREFIX,
)


def utc(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def make_candles(n=8, start_day=1):
    return [
        {
            "timestamp": utc(2020, 1, start_day + i),
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 1000.0,
        }
        for i in range(n)
    ]


SPECS = (
    FeatureSpec(output_name="sma3", indicator="sma", parameters={"period": 3}),
    FeatureSpec(output_name="ema5", indicator="ema", parameters={"period": 5}),
)


class TestFeaturePipeline:

    def test_fe_01_as_of_cutoff(self):
        """FE-01: candles after as_of are invisible to the pipeline."""
        candles = make_candles(8)  # Jan 1..8
        pipeline = FeaturePipeline(SPECS)
        dataset = pipeline.compute(candles, as_of=utc(2020, 1, 5))
        assert len(dataset.rows) == 5  # only Jan 1..5 visible
        assert dataset.rows[-1]["timestamp"] == utc(2020, 1, 5)
        # Boundary: candle AT the cutoff is visible (inclusive)
        assert dataset.as_of == utc(2020, 1, 5)

    def test_fe_02_no_future_data_in_hash(self):
        """FE-02: differing future tail -> identical dataset hash."""
        pipeline = FeaturePipeline(SPECS)
        a = make_candles(8)
        b = make_candles(8)
        # Corrupt everything strictly after the cutoff
        for candle in b[5:]:
            candle["close"] = 999.0
            candle["high"] = 999.0
        da = pipeline.compute(a, as_of=utc(2020, 1, 5))
        db = pipeline.compute(b, as_of=utc(2020, 1, 5))
        assert da.feature_dataset_hash == db.feature_dataset_hash

    def test_fe_03_determinism(self):
        """FE-03: same inputs -> same hash, across pipeline instances."""
        d1 = FeaturePipeline(SPECS).compute(make_candles(6), utc(2020, 1, 6))
        d2 = FeaturePipeline(
            (
                FeatureSpec(output_name="sma3", indicator="sma", parameters={"period": 3}),
                FeatureSpec(output_name="ema5", indicator="ema", parameters={"period": 5}),
            )
        ).compute(make_candles(6), utc(2020, 1, 6))
        assert d1.feature_dataset_hash == d2.feature_dataset_hash
        assert d1.feature_dataset_hash.startswith(FEATURE_PREFIX)
        assert len(d1.feature_dataset_hash) == 70
        # Different as_of -> different hash
        d3 = FeaturePipeline(SPECS).compute(make_candles(6), utc(2020, 1, 5))
        assert d1.feature_dataset_hash != d3.feature_dataset_hash

    def test_fe_04_spec_validation(self):
        with pytest.raises(FeaturePipelineError, match="unknown indicator"):
            FeaturePipeline(
                (FeatureSpec(output_name="x", indicator="nope"),)
            )
        with pytest.raises(FeaturePipelineError, match="duplicate"):
            FeaturePipeline(
                (
                    FeatureSpec(output_name="x", indicator="sma", parameters={"period": 3}),
                    FeatureSpec(output_name="x", indicator="ema", parameters={"period": 5}),
                )
            )
        with pytest.raises(FeaturePipelineError, match="at least one"):
            FeaturePipeline(())

    def test_fe_05_warmup_none(self):
        """FE-05: SMA(3) yields None for rows 0..1 (no fabrication)."""
        pipeline = FeaturePipeline(
            (FeatureSpec(output_name="sma3", indicator="sma", parameters={"period": 3}),)
        )
        dataset = pipeline.compute(make_candles(6), utc(2020, 1, 6))
        assert dataset.rows[0]["features"]["sma3"] is None
        assert dataset.rows[1]["features"]["sma3"] is None
        assert dataset.rows[2]["features"]["sma3"] == 101.0  # mean(100,101,102)

    def test_fe_06_empty_window_fails_closed(self):
        pipeline = FeaturePipeline(SPECS)
        with pytest.raises(FeaturePipelineError, match="no candles visible"):
            pipeline.compute(make_candles(4), as_of=utc(2019, 1, 1))
