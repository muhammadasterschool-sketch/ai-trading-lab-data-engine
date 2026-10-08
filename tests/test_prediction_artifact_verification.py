"""Prediction Intelligence closure tests — external artifact verification
(PRED-F3) and estimator integration.

Covers:
- recomputed artifact hashes vs declared vs expected (registry-bound)
- serialization integrity (JSON round-trip)
- model/schema compatibility (unconditional baselines by contract)
- dataset compatibility and model-version validity
- caller-asserted verification NEVER trusted
- estimator.assess() blocks on verification failure (fail closed)
- input snapshot re-verification with expected-hash binding
"""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.prediction.artifact_verification import (
    verify_input_snapshot,
    verify_model_artifact,
)
from data_engine.prediction.contracts import (
    BlockReason,
    PredictionContractError,
)
from data_engine.prediction.estimator import (
    CrashRiskEstimator,
    EstimatorConfig,
)
from data_engine.prediction.features import FEATURE_SCHEMA
from data_engine.prediction.labels import CrashLabelDefinition
from data_engine.prediction.models import (
    BaseRateBaseline,
    LogisticCrashModel,
)


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


def _fitted_logistic(candles):
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


GOOD_EVIDENCE = {
    "data_quality": 0.9, "sample_size": 0.8,
    "historical_coverage": 0.9, "regime_coverage": 0.8,
    "model_calibration": 0.7, "out_of_sample_performance": 0.6,
    "stability": 0.7, "cross_validation_consistency": 0.7,
    "feature_integrity": 1.0, "drift_status": "STABLE",
    "prediction_freshness": 0.9,
}


class _OpaqueModel:
    model_id = "OPAQUE-1"
    model_version = "1"

    @property
    def model_hash(self):
        return "predm.opaque"

    def fit(self, X, y):
        return self

    def predict_proba(self, x):
        return 0.5


class _TamperedModel(LogisticCrashModel):
    """Declares a hash that differs from its recomputed artifact."""

    @property
    def model_hash(self):
        return "predm.TAMPERED"


# ─── verification report semantics ─────────────────────────────────────

class TestVerifyModelArtifact:

    def test_honest_logistic_verifies(self):
        model = _fitted_logistic(_candles())
        report = verify_model_artifact(
            model,
            expected_feature_count=len(FEATURE_SCHEMA),
        )
        assert report.verified is True
        assert report.hash_self_consistent is True
        assert report.serialization_integrity is True
        assert report.schema_compatible is True
        assert report.failures == ()

    def test_baseline_compatible_by_contract(self):
        model = BaseRateBaseline()
        model.fit([[0.0]] * 5, [0, 0, 1, 0, 1])
        report = verify_model_artifact(
            model, expected_feature_count=len(FEATURE_SCHEMA)
        )
        assert report.verified is True
        assert "unconditional baseline" in report.schema_detail

    def test_tampered_declared_hash_detected(self):
        candles = _candles()
        model = _TamperedModel(
            ("ret1", "mom20", "vol20", "volr", "dd", "range")
        )
        from data_engine.prediction.labels import compute_crash_labels
        from data_engine.prediction.features import build_feature_rows
        closes = [c["close"] for c in candles]
        labeled = compute_crash_labels(closes, _label_def())
        rows = build_feature_rows(closes)
        usable = [
            r for r in rows if labeled[r.row_index].label is not None
        ]
        model.fit(
            [list(r.values) for r in usable],
            [int(labeled[r.row_index].label) for r in usable],
        )
        report = verify_model_artifact(model)
        assert report.hash_self_consistent is False
        assert report.verified is False
        assert any("tampered" in f for f in report.failures)

    def test_expected_hash_mismatch_rejected(self):
        model = _fitted_logistic(_candles())
        report = verify_model_artifact(
            model, expected_hash="predm.REGISTRY-BINDING-XYZ"
        )
        assert report.verified is False
        assert report.expected_hash_match is False

    def test_expected_hash_match_accepted(self):
        model = _fitted_logistic(_candles())
        report = verify_model_artifact(
            model, expected_hash=model.model_hash
        )
        assert report.verified is True
        assert report.expected_hash_match is True

    def test_opaque_model_fails_closed(self):
        report = verify_model_artifact(_OpaqueModel())
        assert report.verified is False
        assert any("artifact()" in f for f in report.failures)
        assert any("documented boundary" in n for n in report.notes)

    def test_schema_incompatibility_detected(self):
        candles = _candles()
        from data_engine.prediction.labels import compute_crash_labels
        from data_engine.prediction.features import build_feature_rows
        closes = [c["close"] for c in candles]
        labeled = compute_crash_labels(closes, _label_def())
        rows = build_feature_rows(closes)
        usable = [
            r for r in rows if labeled[r.row_index].label is not None
        ]
        wrong = LogisticCrashModel(("a", "b", "c"))
        wrong.fit(
            [list(r.values)[:3] for r in usable],
            [int(labeled[r.row_index].label) for r in usable],
        )
        report = verify_model_artifact(
            wrong, expected_feature_count=len(FEATURE_SCHEMA)
        )
        assert report.schema_compatible is False
        assert report.verified is False

    def test_dataset_compatibility(self):
        model = _fitted_logistic(_candles())
        ok = verify_model_artifact(
            model,
            expected_dataset_id="DS-A",
            declared_dataset_id="DS-A",
        )
        bad = verify_model_artifact(
            model,
            expected_dataset_id="DS-A",
            declared_dataset_id="DS-B",
        )
        assert ok.dataset_compatible is True
        assert bad.dataset_compatible is False
        assert bad.verified is False
        assert any("version mismatch" in f for f in bad.failures)

    def test_none_model_rejected(self):
        report = verify_model_artifact(None)
        assert report.artifact_exists is False
        assert report.verified is False

    def test_verification_hash_deterministic(self):
        model = _fitted_logistic(_candles())
        r1 = verify_model_artifact(model)
        r2 = verify_model_artifact(model)
        assert r1.verification_hash == r2.verification_hash
        assert r1.verification_hash.startswith("predx.")


class TestVerifyInputSnapshot:

    def test_self_consistent_snapshot(self):
        closes = [100.0, 101.0, 99.5, 100.25]
        report = verify_input_snapshot(closes, 0, 1)
        assert report.verified is True
        assert report.hash_self_consistent is True

    def test_expected_hash_binding(self):
        closes = [100.0, 101.0, 99.5]
        baseline = verify_input_snapshot(closes, 0, 0)
        matched = verify_input_snapshot(
            closes, 0, 0, expected_hash=baseline.artifact_hash_recomputed
        )
        mismatched = verify_input_snapshot(
            [100.0, 101.0, 98.5], 0, 0,
            expected_hash=baseline.artifact_hash_recomputed,
        )
        assert matched.verified is True
        assert mismatched.verified is False
        assert mismatched.expected_hash_match is False


# ─── estimator integration (PRED-F3 wiring) ────────────────────────────

class TestEstimatorArtifactVerification:

    def _estimator(self, model, dataset_id="DS-RT"):
        return CrashRiskEstimator(
            model,
            config=EstimatorConfig(required_history_years=None),
            dataset_id=dataset_id,
        )

    def _assess(self, est, candles, **kwargs):
        base = dict(
            as_of=candles[50]["timestamp"],
            label_definition=_label_def(),
            prediction_time="T",
            training_samples=100,
            evidence_values=GOOD_EVIDENCE,
        )
        base.update(kwargs)
        return est.assess(candles, **base)

    def test_honest_model_still_predicts(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles))
        result = self._assess(est, candles)
        assert result.status not in ("PREDICTION_BLOCKED",)
        assert result.blocked_reason is None

    def test_stale_expected_hash_blocks(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles))
        result = self._assess(
            est, candles, expected_model_hash="predm.STALE"
        )
        assert result.status == "PREDICTION_BLOCKED"
        assert result.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
        assert any("stale" in n for n in result.notes)

    def test_matched_expected_hash_predicts(self):
        candles = _candles()
        model = _fitted_logistic(candles)
        est = self._estimator(model)
        result = self._assess(
            est, candles, expected_model_hash=model.model_hash
        )
        assert result.status != "PREDICTION_BLOCKED"

    def test_dataset_mismatch_blocks(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles), "DS-OLD")
        result = self._assess(
            est, candles, expected_dataset_id="DS-NEW"
        )
        assert result.status == "PREDICTION_BLOCKED"
        assert any("version mismatch" in n for n in result.notes)

    def test_opaque_model_blocks(self):
        candles = _candles()
        est = self._estimator(_OpaqueModel())
        result = self._assess(est, candles)
        assert result.status == "PREDICTION_BLOCKED"
        assert result.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
        assert any("artifact()" in n for n in result.notes)

    def test_expected_input_hash_mismatch_blocks(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles))
        result = self._assess(
            est, candles, expected_input_hash="predv.WRONG"
        )
        assert result.status == "PREDICTION_BLOCKED"
        assert result.blocked_reason is BlockReason.INPUT_HASH_MISMATCH

    def test_backward_compatible_defaults(self):
        """No expected hashes supplied -> internal verification only."""
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles))
        r1 = self._assess(est, candles)
        r2 = self._assess(est, candles)
        assert r1.prediction_id == r2.prediction_id
        assert r1.output_hash == r2.output_hash

    def test_assessment_carries_dataset_version_and_evidence_window(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles), "DS-V2")
        result = self._assess(est, candles)
        assert result.dataset_version == "DS-V2"
        assert result.evidence_window_start == (
            candles[0]["timestamp"].isoformat()
        )
        assert result.evidence_window_end == (
            candles[50]["timestamp"].isoformat()
        )
        assert result.warning_state in (
            "WARNING_ACTIVE", "WARNING_INACTIVE"
        )

    def test_blocked_assessment_warning_state_is_refused(self):
        candles = _candles()
        est = self._estimator(_fitted_logistic(candles))
        result = self._assess(
            est, candles, expected_model_hash="predm.X"
        )
        assert result.warning_state == "REFUSED"
