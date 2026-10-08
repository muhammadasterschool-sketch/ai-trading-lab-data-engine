"""Prediction Intelligence closure tests — governed benchmark harness
(PRED-F1: performance benchmark protocol + blocked/refusal path).

Covers:
- empirical mode REFUSES non-REAL_VERIFIED datasets (blocked harness)
- contract-verification mode stamps SYNTHETIC evidence class everywhere
- split manifests: reproducibility, intervals, cutoff, versions
- baseline comparison + justification verdict (§9)
- calibration temporal separation (Platt fitted on validation only)
- crash-event evaluation embedded in the benchmark
- drift summary per feature
- refusal analysis over test predictions
- determinism of the full benchmark artifact
"""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.prediction.benchmark import (
    EVIDENCE_CLASS_BLOCKED,
    EVIDENCE_CLASS_SYNTHETIC,
    BenchmarkProtocol,
    blocked_benchmark,
    run_prediction_benchmark,
)
from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.datasets import (
    DatasetManifest,
    DatasetState,
    dataset_content_hash,
    synthetic_dataset_manifest,
)
from data_engine.prediction.labels import CrashLabelDefinition
from data_engine.prediction.models import (
    BaseRateBaseline,
    NaivePersistenceBaseline,
    RandomClassifierBaseline,
    LogisticCrashModel,
)

FEATURE_NAMES = ("ret1", "mom20", "vol20", "volr", "dd", "range")


def _candles(n: int = 400, *, crash_indices=None) -> list[dict]:
    """Deterministic daily series with injected drawdown episodes."""
    crash_indices = crash_indices or {120, 240, 360}
    start = datetime(2019, 1, 1, tzinfo=UTC)
    price = 100.0
    out = []
    for i in range(n):
        if i in crash_indices:
            price *= 0.85  # 15% single-bar drawdown
        else:
            price *= 1.0 + (0.004 if i % 3 else -0.002)
        out.append({
            "timestamp": start + timedelta(days=i),
            "close": round(price, 10),
        })
    return out


def _label_def() -> CrashLabelDefinition:
    return CrashLabelDefinition(
        threshold=0.08, measurement_window=5, forward_horizon=5,
        asset_scope="TEST", calibration_period="2019-2024",
    )


def _model_factory():
    return LogisticCrashModel(FEATURE_NAMES)


def _synthetic_dataset(candles):
    return synthetic_dataset_manifest(
        dataset_name="benchmark-fixture",
        symbol="TEST",
        row_count=len(candles),
        content_checksum=dataset_content_hash(candles),
        coverage_start=candles[0]["timestamp"].date().isoformat(),
        coverage_end=candles[-1]["timestamp"].date().isoformat(),
        generator="arithmetic-walk-with-crashes",
        seed=7,
    )


def _real_dataset(candles, **overrides):
    base = dict(
        dataset_name="benchmark-real",
        source_name="stooq-daily-ohlcv",
        source_version="2024-01",
        acquisition_timestamp="2024-06-01T00:00:00+00:00",
        coverage_start=candles[0]["timestamp"].date().isoformat(),
        coverage_end=candles[-1]["timestamp"].date().isoformat(),
        symbol="TEST",
        timezone="UTC",
        frequency="1D",
        corporate_action_treatment="split-adjusted",
        adjustment_policy="back-adjusted",
        missing_data_policy="explicit-gap",
        revision_policy="append-only-first-arrival",
        license_basis="public-domain",
        provenance_metadata=(("origin", "test"),),
        content_checksum=dataset_content_hash(candles),
        row_count=len(candles),
        data_state=DatasetState.REAL_VERIFIED,
    )
    base.update(overrides)
    return DatasetManifest(**base)


# ─── the blocked harness (PRED-F1 refusal path) ────────────────────────

class TestBlockedBenchmark:

    def test_synthetic_dataset_blocks_empirical_mode(self):
        candles = _candles()
        dataset = _synthetic_dataset(candles)
        result = run_prediction_benchmark(
            dataset=dataset,
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="empirical",
        )
        assert result.mode == "blocked"
        assert result.evidence_class == EVIDENCE_CLASS_BLOCKED
        assert result.real_data_validation == "BLOCKED"
        assert result.empirical_valid is False
        assert result.block_reason is not None
        assert "not REAL_VERIFIED" in result.block_reason

    def test_unverified_real_dataset_blocks_empirical_mode(self):
        candles = _candles()
        dataset = _real_dataset(
            candles, data_state=DatasetState.REAL_UNVERIFIED
        )
        result = run_prediction_benchmark(
            dataset=dataset,
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="empirical",
        )
        assert result.mode == "blocked"
        assert result.real_data_validation == "BLOCKED"

    def test_blocked_result_is_machine_readable_and_honest(self):
        result = blocked_benchmark(
            dataset=None,
            protocol=BenchmarkProtocol(),
            reason="no verified real dataset in the repository",
        )
        assert result.real_data_validation == "BLOCKED"
        assert result.dataset_state == "ABSENT"
        summary = result.summary()
        assert "BLOCKED" in summary
        assert "NO empirical claim" in summary
        assert result.benchmark_hash.startswith("predb.")

    def test_contract_mode_rejects_real_dataset(self):
        """Synthetic and real datasets are never mixed (mandate §1.3)."""
        candles = _candles()
        dataset = _real_dataset(candles)
        result = run_prediction_benchmark(
            dataset=dataset,
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        assert result.mode == "blocked"
        assert "SYNTHETIC" in result.block_reason

    def test_unknown_mode_rejected(self):
        candles = _candles()
        with pytest.raises(PredictionContractError):
            run_prediction_benchmark(
                dataset=_synthetic_dataset(candles),
                closes=[c["close"] for c in candles],
                label_definition=_label_def(),
                model_factory=_model_factory,
                mode="production",
            )


# ─── contract-verification mode (machinery proof, never evidence) ──────

class TestContractVerificationRun:

    def test_full_run_produces_stamped_artifact(self):
        candles = _candles()
        dataset = _synthetic_dataset(candles)
        result = run_prediction_benchmark(
            dataset=dataset,
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            baseline_factories=[
                BaseRateBaseline,
                RandomClassifierBaseline,
                NaivePersistenceBaseline,
            ],
            mode="contract-verification",
        )
        assert result.mode == "contract-verification"
        assert result.evidence_class == EVIDENCE_CLASS_SYNTHETIC
        assert result.empirical_valid is False
        assert result.real_data_validation == "BLOCKED"
        # machinery actually exercised
        assert result.candidate is not None
        assert len(result.baselines) == 3
        assert result.split_manifest is not None
        assert result.crash_event_evaluation is not None
        assert result.calibration is not None
        assert result.refusal_analysis is not None
        assert result.drift_summary
        summary = result.summary()
        assert "SYNTHETIC" in summary
        assert "NO empirical claim" in summary

    def test_benchmark_deterministic(self):
        candles_a = _candles()
        candles_b = _candles()
        kwargs = dict(
            label_definition=_label_def(),
            model_factory=_model_factory,
            baseline_factories=[BaseRateBaseline],
            mode="contract-verification",
        )
        r1 = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles_a),
            closes=[c["close"] for c in candles_a],
            timestamps=[c["timestamp"] for c in candles_a],
            **kwargs,
        )
        r2 = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles_b),
            closes=[c["close"] for c in candles_b],
            timestamps=[c["timestamp"] for c in candles_b],
            **kwargs,
        )
        assert r1.benchmark_hash == r2.benchmark_hash
        assert r1.candidate.brier == r2.candidate.brier

    def test_justification_verdict_recorded(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            baseline_factories=[RandomClassifierBaseline],
            mode="contract-verification",
        )
        assert result.justification is not None
        assert result.justification.status in (
            "JUSTIFIED", "MODEL_NOT_JUSTIFIED"
        )
        # beating a random 0.5-classifier should be feasible on this fixture
        assert result.justification.improvement > 0

    def test_calibration_fitted_on_validation_only(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        assert result.calibration.fitted_on == "validation"
        assert result.calibration.raw_test_brier >= 0.0
        assert result.calibration.calibrated_test_brier >= 0.0

    def test_split_manifest_records_intervals_and_versions(self):
        candles = _candles()
        dataset = _synthetic_dataset(candles)
        result = run_prediction_benchmark(
            dataset=dataset,
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        sm = result.split_manifest
        assert sm.dataset_id == dataset.manifest_hash
        assert sm.dataset_state == "SYNTHETIC"
        assert sm.label_horizon_bars == 5
        assert sm.feature_cutoff == sm.train_end
        assert sm.train_end < sm.validation_start  # purge gap
        assert sm.validation_end < sm.test_start  # embargo gap
        assert sm.split_hash.startswith("predb.")

    def test_history_policy_recorded_not_hidden(self):
        candles = _candles()  # 400 days ~ 1.6 years < 5y minimum
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        assert result.coverage_years < 5.0
        assert result.history_policy_status == "INSUFFICIENT_HISTORY"
        assert any(
            "HISTORY POLICY NOT MET" in n for n in result.notes
        )

    def test_event_evaluation_in_benchmark(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        ev = result.crash_event_evaluation
        assert ev.segment == "test"
        assert ev.config.label_definition_id == (
            _label_def().label_definition_id
        )

    def test_refusal_analysis_counts_statuses(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        ra = result.refusal_analysis
        assert ra.n_assessments > 0
        assert sum(c for _, c in ra.status_counts) == ra.n_assessments
        assert 0.0 <= ra.refusal_rate <= 1.0

    def test_drift_summary_per_feature(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        assert len(result.drift_summary) == len(FEATURE_NAMES)
        for d in result.drift_summary:
            assert d.state in (
                "STABLE", "WATCH", "DEGRADED", "DRIFTED", "INVALID"
            )

    def test_evaluation_randomness_declared(self):
        candles = _candles()
        result = run_prediction_benchmark(
            dataset=_synthetic_dataset(candles),
            closes=[c["close"] for c in candles],
            timestamps=[c["timestamp"] for c in candles],
            label_definition=_label_def(),
            model_factory=_model_factory,
            mode="contract-verification",
        )
        assert any(
            "seed=" in n and "evaluation-only" in n
            for n in result.notes
        )


# ─── protocol ──────────────────────────────────────────────────────────

class TestBenchmarkProtocol:

    def test_protocol_hash_deterministic(self):
        p1 = BenchmarkProtocol()
        p2 = BenchmarkProtocol()
        assert p1.protocol_hash == p2.protocol_hash
        assert p1.protocol_hash.startswith("predb.")

    def test_invalid_fractions_rejected(self):
        with pytest.raises(Exception):
            BenchmarkProtocol(train_fraction=1.5)

    def test_embargo_zero_allowed(self):
        BenchmarkProtocol(embargo=0)

    def test_default_protocol_temporal_separation(self):
        proto = BenchmarkProtocol()
        assert proto.purge > 0 and proto.embargo > 0
        assert (
            proto.train_fraction + proto.validation_fraction
            + proto.test_fraction
        ) < 1.0
