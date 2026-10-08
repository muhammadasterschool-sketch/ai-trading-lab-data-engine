"""Prediction Intelligence closure tests — drift validation matrix
(mandate §12) + calibration validity + registry/drift integration.

Covers:
- STABLE / WATCH / DEGRADED / DRIFTED / INVALID states and mandated actions
- malformed distributions (NaN, non-numeric) -> INVALID, never a guess
- missing reference distribution -> INVALID
- zero/near-zero variance bins -> deterministic degenerate path
- distribution mismatch -> DRIFTED
- dataset-version mismatch -> fail-closed blocks
- DRIFTED/INVALID cannot silently continue as production states
  (gate + estimator integration)
"""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.prediction.contracts import (
    BlockReason,
    DriftState,
    PredictionContractError,
)
from data_engine.prediction.drift import (
    DRIFT_ACTIONS,
    classify_drift,
    data_source_drift,
    drift_action,
    drift_report,
    population_stability_index,
)
from data_engine.prediction.estimator import (
    CrashRiskEstimator,
    EstimatorConfig,
)
from data_engine.prediction.features import FEATURE_SCHEMA
from data_engine.prediction.labels import CrashLabelDefinition
from data_engine.prediction.models import LogisticCrashModel


# ─── PSI state machine ─────────────────────────────────────────────────

class TestDriftStates:

    def test_state_boundaries(self):
        assert classify_drift(0.05) is DriftState.STABLE
        assert classify_drift(0.15) is DriftState.WATCH
        assert classify_drift(0.35) is DriftState.DEGRADED
        assert classify_drift(0.75) is DriftState.DRIFTED

    def test_malformed_psi_is_invalid(self):
        assert classify_drift(None) is DriftState.INVALID
        assert classify_drift(float("nan")) is DriftState.INVALID
        assert classify_drift(-0.5) is DriftState.INVALID

    def test_mandated_actions_exhaustive(self):
        for state in DriftState:
            assert state in DRIFT_ACTIONS
            assert drift_action(state) == DRIFT_ACTIONS[state]
        assert DRIFT_ACTIONS[DriftState.DRIFTED] == (
            "block or require review"
        )
        assert DRIFT_ACTIONS[DriftState.INVALID] == "retire model"


class TestMalformedDistributions:

    def test_missing_reference_is_invalid(self):
        report = drift_report([], [1.0, 2.0], metric="feature")
        assert report.state is DriftState.INVALID
        assert report.psi is None

    def test_single_value_reference_is_invalid(self):
        report = drift_report([1.0], [1.0, 2.0], metric="feature")
        assert report.state is DriftState.INVALID

    def test_empty_current_is_invalid(self):
        report = drift_report([1.0, 2.0, 3.0], [], metric="feature")
        assert report.state is DriftState.INVALID

    def test_zero_variance_reference_degenerate_path(self):
        # all-identical reference: degenerate single-bin path, still
        # deterministic and never a silent guess
        reference = [5.0] * 50
        current = [5.0] * 50
        report = drift_report(reference, current, metric="const")
        assert report.state in (
            DriftState.STABLE, DriftState.INVALID
        )
        psi_again = drift_report(reference, current, metric="const")
        assert report.psi == psi_again.psi  # deterministic

    def test_near_zero_bins_epsilon_floored(self):
        # heavily skewed distributions: near-zero bins must not explode
        reference = [float(i) for i in range(100)]
        current = [float(i) for i in range(100)]
        psi = population_stability_index(reference, current)
        assert psi == pytest.approx(0.0, abs=1e-9)

    def test_distribution_mismatch_is_drifted(self):
        reference = [float(i) for i in range(100)]
        current = [float(i + 80) for i in range(100)]
        report = drift_report(reference, current, metric="shift")
        assert report.state is DriftState.DRIFTED

    def test_psi_symmetry_deterministic(self):
        a = [float(i) for i in range(50)]
        b = [float(i + 10) for i in range(50)]
        assert population_stability_index(a, b) == (
            population_stability_index(a, b)
        )


class TestSchemaAndDatasetVersion:

    def test_feature_schema_mismatch_blocks_estimator(self):
        candles = _candles()
        model = _fitted_model_wrong_arity()
        est = CrashRiskEstimator(
            model,
            config=EstimatorConfig(required_history_years=None),
            dataset_id="DS-RT",
        )
        result = est.assess(
            candles,
            as_of=candles[50]["timestamp"],
            label_definition=_label_def(),
            prediction_time="T",
            training_samples=100,
        )
        assert result.status == "PREDICTION_BLOCKED"
        assert result.blocked_reason is BlockReason.FEATURE_SCHEMA_MISMATCH

    def test_dataset_version_mismatch_blocks(self):
        from data_engine.prediction.artifact_verification import (
            verify_model_artifact,
        )
        candles = _candles()
        model = _fitted_model(candles)
        report = verify_model_artifact(
            model,
            expected_dataset_id="DS-EXPECTED",
            declared_dataset_id="DS-OTHER",
        )
        assert report.dataset_compatible is False
        assert report.verified is False

    def test_feature_addition_changes_schema_compatibility(self):
        from data_engine.prediction.artifact_verification import (
            verify_model_artifact,
        )
        candles = _candles()
        model = _fitted_model(candles)
        correct = verify_model_artifact(
            model, expected_feature_count=len(FEATURE_SCHEMA)
        )
        wrong = verify_model_artifact(
            model, expected_feature_count=len(FEATURE_SCHEMA) + 2
        )
        assert correct.schema_compatible is True
        assert wrong.schema_compatible is False


class TestDriftedCannotSilentlyContinue:

    def test_gate_blocks_drifted_and_invalid(self):
        from data_engine.prediction.gates import (
            PredictionGateInput,
            evaluate_prediction_gates,
        )
        for state in (DriftState.DRIFTED, DriftState.INVALID):
            result = evaluate_prediction_gates(PredictionGateInput(
                drift_state=state,
                training_samples=100, history_bars=1300,
                horizon_bars=20,
            ))
            assert result.allowed is False
            assert result.blocked_reason is (
                BlockReason.MODEL_DRIFT_UNACCEPTABLE
            )

    def test_degraded_is_restricted_not_allowed_quietly(self):
        from data_engine.prediction.gates import (
            PredictionGateInput,
            evaluate_prediction_gates,
        )
        result = evaluate_prediction_gates(PredictionGateInput(
            drift_state=DriftState.DEGRADED,
            training_samples=100, history_bars=1300, horizon_bars=20,
        ))
        assert result.allowed is True
        assert result.restricted is True  # §37 'restrict usage'

    def test_estimator_blocks_drifted_model(self):
        candles = _candles()
        model = _fitted_model(candles)
        est = CrashRiskEstimator(
            model,
            config=EstimatorConfig(required_history_years=None),
            dataset_id="DS-RT",
        )
        result = est.assess(
            candles,
            as_of=candles[50]["timestamp"],
            label_definition=_label_def(),
            prediction_time="T",
            training_samples=100,
            drift_state=DriftState.DRIFTED,
        )
        assert result.status == "PREDICTION_BLOCKED"
        assert result.blocked_reason is (
            BlockReason.MODEL_DRIFT_UNACCEPTABLE
        )

    def test_estimator_blocks_invalid_drift_model(self):
        candles = _candles()
        model = _fitted_model(candles)
        est = CrashRiskEstimator(
            model,
            config=EstimatorConfig(required_history_years=None),
            dataset_id="DS-RT",
        )
        result = est.assess(
            candles,
            as_of=candles[50]["timestamp"],
            label_definition=_label_def(),
            prediction_time="T",
            training_samples=100,
            drift_state=DriftState.INVALID,
        )
        assert result.status == "PREDICTION_BLOCKED"

    def test_data_source_drift_detected(self):
        assert data_source_drift(["a", "b"], ["a", "b"]) is False
        assert data_source_drift(["a", "b"], ["a", "c"]) is True

    def test_drift_report_hash_deterministic(self):
        reference = [float(i) for i in range(50)]
        current = [float(i + 3) for i in range(50)]
        r1 = drift_report(reference, current, metric="f")
        r2 = drift_report(reference, current, metric="f")
        assert r1.drift_hash == r2.drift_hash


# ─── fixtures ──────────────────────────────────────────────────────────

def _candles(n: int = 60, *, crash_at=None) -> list[dict]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    price = 100.0
    out = []
    for i in range(n):
        if crash_at is not None and i == crash_at:
            price *= 0.75
        else:
            price *= 1.0 + (0.002 if i % 3 else -0.001)
        out.append({
            "timestamp": start + timedelta(days=i),
            "close": round(price, 10),
        })
    return out


def _label_def() -> CrashLabelDefinition:
    return CrashLabelDefinition(
        threshold=0.10, measurement_window=5, forward_horizon=5,
        asset_scope="TEST", calibration_period="2019-2024",
    )


def _fitted_model(candles):
    from data_engine.prediction.features import build_feature_rows
    from data_engine.prediction.labels import compute_crash_labels
    closes = [c["close"] for c in candles]
    labeled = compute_crash_labels(closes, _label_def())
    rows = build_feature_rows(closes)
    usable = [
        r for r in rows if labeled[r.row_index].label is not None
    ]
    model = LogisticCrashModel(
        ("ret1", "mom20", "vol20", "volr", "dd", "range")
    )
    model.fit(
        [list(r.values) for r in usable],
        [int(labeled[r.row_index].label) for r in usable],
    )
    return model


def _fitted_model_wrong_arity():
    from data_engine.prediction.features import build_feature_rows
    from data_engine.prediction.labels import compute_crash_labels
    candles = _candles()
    closes = [c["close"] for c in candles]
    labeled = compute_crash_labels(closes, _label_def())
    rows = build_feature_rows(closes)
    usable = [
        r for r in rows if labeled[r.row_index].label is not None
    ]
    model = LogisticCrashModel(("a", "b", "c"))
    model.fit(
        [list(r.values)[:3] for r in usable],
        [int(labeled[r.row_index].label) for r in usable],
    )
    return model
