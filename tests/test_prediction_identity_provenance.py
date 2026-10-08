"""Prediction Intelligence acceptance tests — identity & provenance.

Mandate test-matrix coverage (§47):

- T-PRED-006  deterministic prediction (same inputs -> same outputs)
- T-PRED-007  cross-process prediction identity
- T-PRED-008  feature hash stability & sensitivity
- T-PRED-009  model hash stability & sensitivity
- T-PRED-010  provenance completeness (§15 field set)
- T-PRED-029  reproducibility (bit-identical repeated runs)
- T-PRED-030  environment fingerprint fields & determinism
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, UTC

import pytest

from data_engine.prediction import (
    CrashLabelDefinition,
    CrashRiskEstimator,
    EstimatorConfig,
    LogisticCrashModel,
    PredictionProvenance,
    build_feature_rows,
    compute_crash_labels,
    capture_environment,
    feature_data_hash,
    prediction_identity,
)
from data_engine.prediction.contracts import PredictionContractError


def utc_day(offset: int) -> datetime:
    return datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=offset)


def synthetic_candles(n=80):
    closes = [100.0]
    for i in range(1, n):
        drift = 0.001 if i % 3 else -0.0005
        closes.append(closes[-1] * (1 + drift))
    return [
        {"timestamp": utc_day(i), "close": close}
        for i, close in enumerate(closes)
    ]


def fitted_model(candles):
    model = LogisticCrashModel(
        ["ret_1", "mom_20", "vol_20", "vol_ratio_5_20",
         "dd_depth_20", "range_20"]
    )
    closes = [c["close"] for c in candles]
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    rows = build_feature_rows(closes)
    label_by_index = {p.index: p for p in compute_crash_labels(closes, definition)}
    X = [row.values for row in rows]
    y = [int(label_by_index[row.row_index].label or 0) for row in rows]
    model.fit(X, y)
    return model, y


EVIDENCE = {
    "data_quality": 0.9, "sample_size": 0.5, "historical_coverage": 0.3,
    "regime_coverage": 0.4, "model_calibration": 0.7,
    "out_of_sample_performance": 0.6, "stability": 0.8,
    "cross_validation_consistency": 0.7, "feature_integrity": 0.9,
    "drift_status": "STABLE", "prediction_freshness": 0.9,
}

SYNTH_CONFIG = EstimatorConfig(required_history_years=None)


# ─── T-PRED-006: deterministic prediction ───


def test_t_pred_006_repeated_assessments_are_identical():
    candles = synthetic_candles()
    model, y = fitted_model(candles)
    estimator = CrashRiskEstimator(model, config=SYNTH_CONFIG)
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    first = estimator.assess(
        candles, as_of=candles[-1]["timestamp"], label_definition=definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=len(y), evidence_values=EVIDENCE,
    )
    second = estimator.assess(
        candles, as_of=candles[-1]["timestamp"], label_definition=definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=len(y), evidence_values=EVIDENCE,
    )
    assert first.prediction_id == second.prediction_id
    assert first.probability == second.probability
    assert first.output_hash == second.output_hash


# ─── T-PRED-007: cross-process identity ───


def test_t_pred_007_identity_is_stable_across_processes():
    import data_engine

    src_root = os.path.dirname(os.path.dirname(data_engine.__file__))
    code = (
        "from data_engine.prediction.identity import prediction_identity;"
        "print(prediction_identity("
        "model_id='M', model_version='1', feature_hash='f'*64,"
        "pit_cutoff_iso='2020-01-01T00:00:00+00:00', horizon_bars=20,"
        "label_definition_id='predl.' + 'a'*64))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = src_root + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, check=True, env=env,
    )
    expected = prediction_identity(
        model_id="M", model_version="1", feature_hash="f" * 64,
        pit_cutoff_iso="2020-01-01T00:00:00+00:00", horizon_bars=20,
        label_definition_id="predl." + "a" * 64,
    )
    assert result.stdout.strip() == expected


def test_t_pred_007_identity_rejects_invalid_horizon():
    with pytest.raises(PredictionContractError):
        prediction_identity(
            model_id="M", model_version="1", feature_hash="f" * 64,
            pit_cutoff_iso="2020-01-01T00:00:00+00:00", horizon_bars=0,
            label_definition_id="predl." + "a" * 64,
        )


# ─── T-PRED-008: feature hash ───


def test_t_pred_008_feature_hash_stable_and_sensitive():
    candles = synthetic_candles(60)
    closes = [c["close"] for c in candles]
    rows = build_feature_rows(closes)
    assert feature_data_hash(rows) == feature_data_hash(
        build_feature_rows(closes)
    )
    tampered = list(closes)
    tampered[40] *= 1.05  # one close changes -> hash changes
    assert feature_data_hash(rows) != feature_data_hash(
        build_feature_rows(tampered)
    )


# ─── T-PRED-009: model hash ───


def test_t_pred_009_model_hash_stable_and_sensitive():
    candles = synthetic_candles()
    model_a, _ = fitted_model(candles)
    model_b, _ = fitted_model(candles)  # identical training -> identical
    assert model_a.model_hash == model_b.model_hash

    other = synthetic_candles()
    other[41]["close"] *= 1.10  # different training data
    model_c, _ = fitted_model(other)
    assert model_a.model_hash != model_c.model_hash


# ─── T-PRED-010: provenance completeness (§15) ───


def test_t_pred_010_provenance_covers_the_full_field_set():
    record = PredictionProvenance(
        prediction_id="pred." + "0" * 64,
        model_id="LOGISTIC-1",
        model_version="1",
        experiment_id="EXP-1",
        dataset_id="DS-1",
        feature_set_id="predf." + "1" * 64,
        feature_hash="predf." + "2" * 64,
        model_hash="predm." + "3" * 64,
        configuration_hash="predv." + "4" * 64,
        pit_cutoff="2020-01-01T00:00:00+00:00",
        prediction_time="2020-01-02T00:00:00+00:00",
        input_snapshot_hash="predv." + "5" * 64,
        output_hash="predo." + "6" * 64,
        regime="NORMAL",
        calibration_version="platt-v1",
        training_window="0..1259",
        training_data_hash="DS-1",
        environment_fingerprint="predv." + "7" * 64,
    )
    payload = record.to_record()
    mandated_fields = {
        "prediction_id", "model_id", "model_version", "experiment_id",
        "dataset_id", "feature_set_id", "feature_hash", "model_hash",
        "configuration_hash", "pit_cutoff", "prediction_time",
        "input_snapshot_hash", "output_hash", "regime",
        "calibration_version", "training_window", "training_data_hash",
        "environment_fingerprint",
    }
    assert mandated_fields <= set(payload)
    assert record.provenance_hash.startswith("predv.")


def test_t_pred_010_provenance_rejects_empty_fields():
    with pytest.raises(ValueError):
        PredictionProvenance(
            prediction_id="pred." + "0" * 64,
            model_id="",
            model_version="1",
            experiment_id="EXP-1",
            dataset_id="DS-1",
            feature_set_id="predf." + "1" * 64,
            feature_hash="predf." + "2" * 64,
            model_hash="predm." + "3" * 64,
            configuration_hash="predv." + "4" * 64,
            pit_cutoff="2020-01-01T00:00:00+00:00",
            prediction_time="2020-01-02T00:00:00+00:00",
            input_snapshot_hash="predv." + "5" * 64,
            output_hash="predo." + "6" * 64,
            regime="NORMAL",
            calibration_version="platt-v1",
            training_window="0..1259",
            training_data_hash="DS-1",
            environment_fingerprint="predv." + "7" * 64,
        )


def test_t_pred_010_estimator_records_provenance_hash():
    candles = synthetic_candles()
    model, y = fitted_model(candles)
    estimator = CrashRiskEstimator(model, config=SYNTH_CONFIG)
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    assessment = estimator.assess(
        candles, as_of=candles[-1]["timestamp"], label_definition=definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=len(y), evidence_values=EVIDENCE,
    )
    provenance_notes = [
        n for n in assessment.notes if n.startswith("provenance_hash=")
    ]
    assert provenance_notes, "assessment must carry its provenance hash"
    assert provenance_notes[0].startswith("provenance_hash=predv.")


# ─── T-PRED-029: reproducibility ───


def test_t_pred_029_full_pipeline_reproducible_across_instances():
    candles = synthetic_candles()
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    outputs = []
    for _ in range(2):
        model, y = fitted_model(candles)  # fresh model, fresh fit
        estimator = CrashRiskEstimator(model, config=SYNTH_CONFIG)
        assessment = estimator.assess(
            candles, as_of=candles[-1]["timestamp"],
            label_definition=definition,
            prediction_time="2021-01-01T00:00:00+00:00",
            training_samples=len(y), evidence_values=EVIDENCE,
        )
        outputs.append(
            (assessment.prediction_id, assessment.probability,
             assessment.output_hash)
        )
    assert outputs[0] == outputs[1]


def test_t_pred_029_output_hash_reacts_to_status_changes():
    candles = synthetic_candles()
    model, y = fitted_model(candles)
    estimator = CrashRiskEstimator(model, config=SYNTH_CONFIG)
    definition = CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )
    base = estimator.assess(
        candles, as_of=candles[-1]["timestamp"], label_definition=definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=len(y), evidence_values=EVIDENCE,
    )
    weaker_evidence = dict(EVIDENCE, stability=0.0)
    weaker = estimator.assess(
        candles, as_of=candles[-1]["timestamp"], label_definition=definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=len(y), evidence_values=weaker_evidence,
    )
    assert base.output_hash != weaker.output_hash  # status moved to refusal


# ─── T-PRED-030: environment fingerprint ───


def test_t_pred_030_environment_fingerprint_fields():
    env = capture_environment(git_commit="228bf208", seeds=(0, 1))
    assert env.python_version == sys.version.split()[0]
    assert env.git_commit == "228bf208"
    assert env.seeds == (0, 1)
    assert env.fingerprint_hash.startswith("predv.")
    assert env.fingerprint_hash == capture_environment(
        git_commit="228bf208", seeds=(0, 1)
    ).fingerprint_hash
    assert env.fingerprint_hash != capture_environment(
        git_commit="0000000", seeds=(0, 1)
    ).fingerprint_hash


def test_t_pred_030_environment_fingerprint_requires_commit():
    with pytest.raises(ValueError):
        capture_environment(git_commit="   ")
