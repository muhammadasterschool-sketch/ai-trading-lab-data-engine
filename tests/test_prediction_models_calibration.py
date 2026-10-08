"""Prediction Intelligence acceptance tests — models, calibration,
uncertainty, drift, evidence.

Mandate test-matrix coverage (§47):

- T-PRED-011  calibration (Brier, log loss, reliability, ECE, Platt)
- T-PRED-012  uncertainty representation
- T-PRED-013  drift monitoring states and actions
plus baseline-first models (§9) and the justification gate
(MODEL_NOT_JUSTIFIED) and the evidence score (§17).
"""

import math

import pytest

from data_engine.prediction.calibration import (
    CalibrationReport,
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
    log_loss,
    reliability_curve,
)
from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.drift import (
    DRIFT_ACTIONS,
    DriftState,
    classify_drift,
    data_source_drift,
    drift_action,
    drift_report,
    population_stability_index,
)
from data_engine.prediction.evidence_score import (
    evidence_assessment,
)
from data_engine.prediction.models import (
    BaseRateBaseline,
    LogisticCrashModel,
    NaivePersistenceBaseline,
    RandomClassifierBaseline,
    RegimeConditionalBaseline,
    RollingBaseRateBaseline,
    bootstrap_improvement_ci,
    justify_model,
)
from data_engine.prediction.uncertainty import (
    ensemble_band,
    empirical_interval,
    is_uncertain,
    probability_band,
    z_score,
)


# ─── baselines (§9) ───


def test_base_rate_baseline_laplace_smoothing():
    model = BaseRateBaseline().fit([[0.0]] * 9 + [[1.0]], [0] * 9 + [1])
    assert model.predict_proba([0.0]) == pytest.approx((1 + 1) / (10 + 2))


def test_naive_persistence_predicts_last_outcome():
    model = NaivePersistenceBaseline().fit([[0.0]] * 3, [0, 0, 1])
    assert model.predict_proba([0.0]) == pytest.approx(0.9)
    model2 = NaivePersistenceBaseline().fit([[0.0]] * 3, [1, 1, 0])
    assert model2.predict_proba([0.0]) == pytest.approx(0.1)


def test_random_classifier_is_the_no_skill_floor():
    model = RandomClassifierBaseline().fit([[0.0]] * 4, [0, 1, 0, 1])
    assert model.predict_proba([0.0]) == 0.5


def test_rolling_base_rate_uses_only_recent_window():
    model = RollingBaseRateBaseline(window=3).fit(
        [[0.0]] * 4, [1, 0, 1, 1]
    )
    # recent labels [0, 1, 1] -> (2 + 1) / (3 + 2)
    assert model.predict_proba([0.0]) == pytest.approx(0.6)


def test_regime_conditional_baseline_falls_back_to_global():
    model = RegimeConditionalBaseline().fit(
        [[0.0]] * 4, [1, 1, 0, 0],
        regimes=["CRISIS", "CRISIS", "NORMAL", "NORMAL"],
    )
    crisis_rate = model.predict_proba([0.0], regime="CRISIS")
    normal_rate = model.predict_proba([0.0], regime="NORMAL")
    unseen_rate = model.predict_proba([0.0], regime="TRANSITION")
    assert crisis_rate > normal_rate
    assert unseen_rate == pytest.approx((2 + 1) / (4 + 2))


def test_logistic_model_learns_separable_structure():
    rng_x = [(-2.0 - i * 0.1, 1.0) for i in range(20)]
    rng_y = [(2.0 + i * 0.1, 1.0) for i in range(20)]
    X = rng_x + rng_y
    y = [0] * 20 + [1] * 20
    model = LogisticCrashModel(["x0", "x1"], iterations=200).fit(X, y)
    assert model.predict_proba((-3.0, 1.0)) < 0.2
    assert model.predict_proba((3.0, 1.0)) > 0.8


def test_logistic_model_schema_mismatch_fails_closed():
    model = LogisticCrashModel(["a", "b"]).fit(
        [(0.0, 0.0), (1.0, 1.0)], [0, 1]
    )
    with pytest.raises(Exception, match="schema mismatch"):
        model.predict_proba((1.0, 2.0, 3.0))


def test_justification_gate_blocks_unimproved_models():
    verdict = justify_model(
        model_id="ADV-1", baseline_id="RANDOM",
        model_metrics={"brier": 0.24}, baseline_metrics={"brier": 0.25},
        metric="brier", min_improvement=0.05,
    )
    assert verdict.status == "MODEL_NOT_JUSTIFIED"
    assert not verdict.justified


def test_justification_gate_accepts_improved_models():
    verdict = justify_model(
        model_id="ADV-1", baseline_id="RANDOM",
        model_metrics={"brier": 0.10}, baseline_metrics={"brier": 0.25},
        metric="brier", min_improvement=0.05,
    )
    assert verdict.status == "JUSTIFIED"
    assert verdict.improvement == pytest.approx(0.6)


def test_bootstrap_ci_is_deterministic_for_seed():
    losses_m = [0.1, 0.2, 0.3, 0.4]
    losses_b = [0.3, 0.4, 0.5, 0.6]
    ci_a = bootstrap_improvement_ci(losses_m, losses_b, seed=7)
    ci_b = bootstrap_improvement_ci(losses_m, losses_b, seed=7)
    assert ci_a == ci_b
    assert ci_a[0] < ci_a[1]


# ─── T-PRED-011: calibration ───


def test_t_pred_011_brier_score_known_values():
    assert brier_score([0.1, 0.9], [0, 1]) == pytest.approx(0.01)


def test_t_pred_011_log_loss_known_values():
    # p=0.1 with outcome 0 contributes -log(0.9); p=0.9 with outcome 1
    # contributes -log(0.9); the mean is -log(0.9).
    assert log_loss([0.1, 0.9], [0, 1]) == pytest.approx(-math.log(0.9))


def test_t_pred_011_matched_probabilities_have_zero_ece():
    # bin-2 mean predicted 0.25 == empirical rate 0.25 -> ECE is 0.
    probs = [0.25, 0.25, 0.25, 0.25]
    outcomes = [1, 0, 0, 0]
    assert expected_calibration_error(probs, outcomes) == pytest.approx(0.0)


def test_t_pred_011_miscalibration_produces_positive_ece():
    probs = [0.9, 0.9, 0.9, 0.9]
    outcomes = [0, 0, 1, 1]  # claims 90%, realizes 50%
    assert expected_calibration_error(probs, outcomes) == pytest.approx(0.4)


def test_t_pred_011_reliability_curve_bins():
    bins = reliability_curve([0.05, 0.15, 0.95], [0, 1, 1])
    by_index = {b.bin_index: b for b in bins}
    assert by_index[0].count == 1 and by_index[0].empirical_rate == 0.0
    assert by_index[1].count == 1 and by_index[1].empirical_rate == 1.0
    assert by_index[9].count == 1 and by_index[9].empirical_rate == 1.0


def test_t_pred_011_platt_calibrator_deterministic_and_effective():
    probs = [0.05, 0.15, 0.85, 0.95] * 10
    outcomes = [0, 1, 1, 1] * 10  # overconfident model
    cal_a = PlattCalibrator().fit(probs, outcomes)
    cal_b = PlattCalibrator().fit(probs, outcomes)
    assert cal_a.calibration_hash() == cal_b.calibration_hash()
    calibrated = [cal_a.calibrate(p) for p in probs]
    ece_raw = expected_calibration_error(probs, outcomes)
    ece_cal = expected_calibration_error(calibrated, outcomes)
    assert ece_cal < ece_raw  # calibration moved probabilities toward reality


def test_t_pred_011_calibration_report_status():
    probs = [0.05, 0.15, 0.85, 0.95] * 10
    outcomes = [0, 0, 1, 1] * 10
    calibrator = PlattCalibrator().fit(probs, outcomes)
    report = calibrator.report(probs, outcomes, dataset_id="DS-CAL")
    assert report.n_samples == 40
    assert report.status in {"CALIBRATION_VALID", "CALIBRATION_INVALID"}
    assert report.brier >= 0.0


def test_t_pred_011_out_of_range_probability_rejected():
    with pytest.raises(PredictionContractError):
        brier_score([1.5], [1])


# ─── T-PRED-012: uncertainty ───


def test_t_pred_012_z_score_closed_set():
    assert z_score(0.80) == pytest.approx(1.2815515655446004)
    with pytest.raises(PredictionContractError):
        z_score(0.77)


def test_t_pred_012_empirical_interval_known_quantiles():
    band = empirical_interval([float(i) for i in range(1, 101)], level=0.8)
    assert band.lower == pytest.approx(10.9)
    assert band.upper == pytest.approx(90.1)
    assert band.lower < (band.point or 0) < band.upper


def test_t_pred_012_small_samples_are_flagged_uncertain():
    band = probability_band(0.5, n_effective=1)
    assert is_uncertain(band)  # honest refusal, not a shrunk band


def test_t_pred_012_large_samples_produce_tight_bands():
    band = probability_band(0.3, n_effective=10000)
    assert not is_uncertain(band)
    assert band.width < 0.05


def test_t_pred_012_ensemble_dispersion():
    band = ensemble_band([0.2, 0.4, 0.6])
    assert band.lower == pytest.approx(0.2)
    assert band.upper == pytest.approx(0.6)
    assert band.dispersion == pytest.approx(0.4)


def test_t_pred_012_probability_band_clamped_to_unit_interval():
    band = probability_band(0.999, n_effective=4)
    assert band.upper <= 1.0
    band_low = probability_band(0.001, n_effective=4)
    assert band_low.lower >= 0.0


# ─── T-PRED-013: drift ───


def _uniform(n, lo, hi, seed):
    import random

    rng = random.Random(seed)
    return [lo + (hi - lo) * rng.random() for _ in range(n)]


def test_t_pred_013_psi_states():
    reference = _uniform(200, 0.0, 1.0, seed=1)
    same = _uniform(200, 0.0, 1.0, seed=2)
    shifted = _uniform(200, 5.0, 6.0, seed=3)
    assert classify_drift(population_stability_index(reference, same)) is DriftState.STABLE
    assert classify_drift(
        population_stability_index(reference, shifted)
    ) is DriftState.DRIFTED


def test_t_pred_013_psi_is_deterministic():
    reference = _uniform(100, 0.0, 1.0, seed=4)
    current = _uniform(100, 0.2, 1.2, seed=5)
    a = population_stability_index(reference, current)
    b = population_stability_index(reference, current)
    assert a == b


def test_t_pred_013_drift_actions_follow_the_mandate():
    assert drift_action(DriftState.STABLE) == "continue"
    assert drift_action(DriftState.WATCH) == "increase monitoring"
    assert drift_action(DriftState.DEGRADED) == "restrict usage"
    assert drift_action(DriftState.DRIFTED) == "block or require review"
    assert drift_action(DriftState.INVALID) == "retire model"
    assert set(DRIFT_ACTIONS) == set(DriftState)


def test_t_pred_013_degenerate_input_is_invalid():
    report = drift_report([], [], metric="feature_0")
    assert report.state is DriftState.INVALID
    assert report.action == "retire model"


def test_t_pred_013_data_source_drift_detected():
    assert data_source_drift(["SRC-A"], ["SRC-A"]) is False
    assert data_source_drift(["SRC-A"], ["SRC-B"]) is True


# ─── evidence score (§17) ───


def test_evidence_score_full_marks_are_ok():
    values = {name: 1.0 for name in (
        "data_quality", "sample_size", "historical_coverage",
        "regime_coverage", "model_calibration", "out_of_sample_performance",
        "stability", "cross_validation_consistency", "feature_integrity",
        "drift_status", "prediction_freshness",
    )}
    assessment = evidence_assessment(values)
    assert assessment.status == "OK"
    assert assessment.score == pytest.approx(1.0)


def test_evidence_missing_dimension_fails_toward_insufficient():
    values = {name: 1.0 for name in (
        "data_quality", "sample_size", "historical_coverage",
        "regime_coverage", "model_calibration", "out_of_sample_performance",
        "stability", "cross_validation_consistency", "feature_integrity",
        "prediction_freshness",
    )}  # drift_status missing entirely
    assessment = evidence_assessment(values)
    assert assessment.insufficient
    assert assessment.score is not None and assessment.score < 1.0


def test_evidence_drift_state_accepted_in_both_forms():
    base = {name: 1.0 for name in (
        "data_quality", "sample_size", "historical_coverage",
        "regime_coverage", "model_calibration", "out_of_sample_performance",
        "stability", "cross_validation_consistency", "feature_integrity",
        "prediction_freshness",
    )}
    from_enum = evidence_assessment({**base, "drift_status": DriftState.STABLE})
    from_string = evidence_assessment({**base, "drift_status": "STABLE"})
    assert from_enum.score == from_string.score == pytest.approx(1.0)
    drifted = evidence_assessment({**base, "drift_status": DriftState.DRIFTED})
    # DRIFTED contributes 0.1: weaker evidence, but the gate (not the
    # score) is what blocks a drifted model (§20/§37 separation).
    assert drifted.score < from_enum.score
    assert not drifted.insufficient
    invalid = evidence_assessment({**base, "drift_status": DriftState.INVALID})
    assert invalid.insufficient  # a zero component fails toward refusal


def test_evidence_components_are_inspectable():
    assessment = evidence_assessment({"data_quality": 0.5})
    names = {c.dimension for c in assessment.components}
    assert "data_quality" in names
    assert len(assessment.components) == 11
