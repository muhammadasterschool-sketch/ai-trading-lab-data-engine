"""Prediction Intelligence acceptance tests — gates & evaluation.

Mandate test-matrix coverage (§47):

- T-PRED-017  walk-forward evaluation (leakage-free windows, refit)
- T-PRED-018  false alarm / miss / lead-time measurement
- T-PRED-020  no-prediction state (machine-readable refusal reasons)
- T-PRED-021  insufficient-history state (5-year policy)
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.prediction.labels import CrashLabelDefinition
from data_engine.prediction.data_access import (
    evaluate_history_policy,
    pit_candle_view,
)
from data_engine.prediction.estimator import (
    CrashRiskEstimator,
    EstimatorConfig,
)
from data_engine.prediction.evaluation import (
    chronological_partitions,
    crash_warning_quality,
    evaluate_walk_forward,
)
from data_engine.prediction.gates import (
    BlockReason,
    DriftState,
    PredictionGateInput,
    evaluate_prediction_gates,
)
from data_engine.prediction.models import BaseRateBaseline


# ─── T-PRED-020: no-prediction states (§27) ───

# Every case is constructed so its intended check is the FIRST failure
# (checks run in the fixed §27 order; all earlier checks must pass).
_LATE_DEFAULTS = dict(training_samples=100, history_bars=1300, horizon_bars=20)

FAILING_INPUTS = [
    ("data_quality", PredictionGateInput(data_quality_ok=False),
     BlockReason.DATA_QUALITY_FAILED),
    ("pit_proof", PredictionGateInput(pit_proven=False),
     BlockReason.PIT_UNPROVEN),
    ("drift_drifted", PredictionGateInput(drift_state=DriftState.DRIFTED),
     BlockReason.MODEL_DRIFT_UNACCEPTABLE),
    ("drift_invalid", PredictionGateInput(drift_state=DriftState.INVALID),
     BlockReason.MODEL_DRIFT_UNACCEPTABLE),
    ("regime_unknown", PredictionGateInput(regime_known=False),
     BlockReason.REGIME_UNKNOWN),
    ("training_samples", PredictionGateInput(training_samples=5),
     BlockReason.TRAINING_SAMPLE_INSUFFICIENT),
    ("calibration",
     PredictionGateInput(**{**_LATE_DEFAULTS, "calibration_valid": False}),
     BlockReason.CALIBRATION_INVALID),
    ("validation",
     PredictionGateInput(**{**_LATE_DEFAULTS, "validation_passed": False}),
     BlockReason.VALIDATION_FAILED),
    ("feature_schema",
     PredictionGateInput(**{**_LATE_DEFAULTS, "feature_schema_match": False}),
     BlockReason.FEATURE_SCHEMA_MISMATCH),
    ("model_artifact",
     PredictionGateInput(**{**_LATE_DEFAULTS,
                            "model_artifact_hash_match": False}),
     BlockReason.MODEL_ARTIFACT_MISMATCH),
    ("input_hash",
     PredictionGateInput(**{**_LATE_DEFAULTS, "input_hash_match": False}),
     BlockReason.INPUT_HASH_MISMATCH),
    ("horizon_zero",
     PredictionGateInput(**{**_LATE_DEFAULTS, "history_bars": 1300,
                            "horizon_bars": 0}),
     BlockReason.HORIZON_INVALID),
    ("horizon_excess",
     PredictionGateInput(**{**_LATE_DEFAULTS, "horizon_bars": 300}),
     BlockReason.HORIZON_INVALID),
    ("history",
     PredictionGateInput(training_samples=100, history_bars=5),
     BlockReason.HISTORICAL_COVERAGE_INADEQUATE),
]


@pytest.mark.parametrize(
    "name,gate_request,expected_reason",
    FAILING_INPUTS,
    ids=[case[0] for case in FAILING_INPUTS],
)
def test_t_pred_020_each_refusal_condition_blocks(name, gate_request, expected_reason):
    result = evaluate_prediction_gates(gate_request)
    assert result.allowed is False
    assert result.blocked_reason is expected_reason


def test_t_pred_020_all_conditions_pass_allows():
    result = evaluate_prediction_gates(
        PredictionGateInput(
            training_samples=100, history_bars=1300, horizon_bars=20,
        )
    )
    assert result.allowed is True
    assert result.blocked_reason is None
    assert result.restricted is False
    assert len(result.checks) == 12


def test_t_pred_020_degraded_drift_restricts_but_does_not_block():
    result = evaluate_prediction_gates(
        PredictionGateInput(
            training_samples=100, history_bars=1300,
            drift_state=DriftState.DEGRADED,
        )
    )
    assert result.allowed is True
    assert result.restricted is True  # §37: DEGRADED -> restrict usage


# ─── T-PRED-021: insufficient-history state (§39 policy) ───


def test_t_pred_021_history_policy_five_year_minimum():
    ok = evaluate_history_policy(visible_bars=252 * 5)
    short = evaluate_history_policy(visible_bars=252 * 2)
    preferred = evaluate_history_policy(visible_bars=252 * 12)
    assert ok.meets_minimum and ok.status == "OK"
    assert not short.meets_minimum and short.status == "INSUFFICIENT_HISTORY"
    assert preferred.meets_preferred


def _synthetic_candles(n=80):
    closes = [100.0]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + (0.001 if i % 3 else -0.0005)))
    return [
        {"timestamp": datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i),
         "close": close}
        for i, close in enumerate(closes)
    ]


@pytest.fixture
def label_definition():
    return CrashLabelDefinition(
        threshold=0.10, measurement_window=10, forward_horizon=10,
        asset_scope="TEST", calibration_period="2020",
    )


def _fitted_estimator(candles, definition, required_history_years=None):
    from data_engine.prediction import (
        LogisticCrashModel,
        build_feature_rows,
        compute_crash_labels,
    )

    closes = [c["close"] for c in candles]
    model = LogisticCrashModel(
        ["ret_1", "mom_20", "vol_20", "vol_ratio_5_20",
         "dd_depth_20", "range_20"]
    )
    rows = build_feature_rows(closes)
    label_by_index = {
        p.index: p for p in compute_crash_labels(closes, definition)
    }
    X = [row.values for row in rows]
    y = [int(label_by_index[row.row_index].label or 0) for row in rows]
    model.fit(X, y)
    return (
        CrashRiskEstimator(
            model,
            config=EstimatorConfig(
                required_history_years=required_history_years
            ),
        ),
        len(y),
    )


def test_t_pred_021_estimator_blocks_short_history_by_default(
    label_definition,
):
    candles = _synthetic_candles(80)
    estimator, samples = _fitted_estimator(
        candles, label_definition, required_history_years=5.0
    )  # 5y policy explicitly ON (the production default)
    assessment = estimator.assess(
        candles, as_of=candles[-1]["timestamp"],
        label_definition=label_definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=samples,
    )
    assert assessment.status == "PREDICTION_BLOCKED"
    assert (
        assessment.blocked_reason
        is BlockReason.HISTORICAL_COVERAGE_INADEQUATE
    )
    assert any("history policy" in note for note in assessment.notes)


def test_t_pred_021_policy_override_is_recorded_not_silent(
    label_definition,
):
    candles = _synthetic_candles(80)
    estimator, samples = _fitted_estimator(
        candles, label_definition, required_history_years=None
    )
    assessment = estimator.assess(
        candles, as_of=candles[-1]["timestamp"],
        label_definition=label_definition,
        prediction_time="2021-01-01T00:00:00+00:00",
        training_samples=samples,
        evidence_values=None,
    )
    # Override is visible in notes, and evidence remains mandatory.
    assert any("NOT ENFORCED" in note for note in assessment.notes)
    assert assessment.status == "EVIDENCE_INSUFFICIENT"


def test_t_pred_021_no_visible_candles_blocks(label_definition):
    candles = _synthetic_candles(80)
    estimator, _ = _fitted_estimator(
        candles, label_definition, required_history_years=None
    )
    assessment = estimator.assess(
        candles, as_of=datetime(2019, 1, 1, tzinfo=UTC),  # before any bar
        label_definition=label_definition,
        prediction_time="2019-01-01T00:00:00+00:00",
        training_samples=100,
    )
    assert assessment.status == "PREDICTION_BLOCKED"
    assert assessment.blocked_reason is BlockReason.DATA_QUALITY_FAILED


# ─── T-PRED-017: walk-forward evaluation (§35) ───


def test_t_pred_017_chronological_partitions_are_ordered_and_gapped():
    split = chronological_partitions(1000, purge=5, embargo=10)
    assert split.train_end < split.validation_start
    assert split.validation_start - split.train_end - 1 >= 5  # purge gap
    assert split.validation_end < split.test_start
    assert split.test_start - split.validation_end - 1 >= 10  # embargo
    assert split.test_end < split.final_oos_start
    assert split.final_oos_end < split.paper_start
    assert split.paper_end == 999


def test_t_pred_017_chronological_partitions_reject_tight_data():
    with pytest.raises(Exception):
        chronological_partitions(12, purge=5, embargo=10)


def test_t_pred_017_walk_forward_refits_per_window_and_pairs_outcomes():
    n = 120
    X = [[float(i % 10)] for i in range(n)]
    y = [i % 3 == 0 for i in range(n)]
    factory_calls = []

    def factory():
        factory_calls.append(1)
        return BaseRateBaseline()

    pairs = evaluate_walk_forward(
        model_factory=factory, X=X, y=y, data_length=n,
        train_size=40, test_size=10, embargo=5, horizon_bars=1,
    )
    assert len(factory_calls) >= 3  # one fresh model per window (no bleed)
    assert all(0.0 <= p.forecast_probability <= 1.0 for p in pairs)
    # every prediction is paired with its realized outcome at that index
    for pair in pairs:
        assert pair.actual == bool(y[pair.index])
    # windows never overlap their own train block (wf7 plan guarantee)
    by_window: dict = {}
    for pair in pairs:
        by_window.setdefault(pair.window_index, []).append(pair.index)
    indices = sorted(i for v in by_window.values() for i in v)
    assert indices == sorted(set(indices))


def test_t_pred_017_embargo_separates_train_from_test():
    from data_engine.research_validation.walk_forward import (
        build_walk_forward_plan,
    )

    plan = build_walk_forward_plan(200, train_size=50, test_size=10, embargo=7)
    assert plan
    for window in plan:
        assert window.test_start >= window.train_end + 1 + 7


# ─── T-PRED-018: crash warning quality (§33) ───


def test_t_pred_018_false_alarms_misses_and_lead_times():
    n = 35
    warnings = [False] * n
    events = [False] * n
    crisis = [False] * n
    # events at 15 and 28; warnings at 13, 14 (catch 15) and 26 (catch 28);
    # stray warnings at 0, 1, 2 with no event within 10 bars.
    for t in (13, 14, 26, 0, 1, 2):
        warnings[t] = True
    events[15] = True
    events[28] = True
    crisis[28] = True
    quality = crash_warning_quality(
        warnings=warnings, events=events, crisis_flags=crisis,
        warning_lookback_bars=10, forward_window_bars=10,
    )
    assert quality.total_events == 2
    assert quality.caught_events == 2
    assert quality.miss_rate == 0.0
    assert quality.total_warnings == 6
    assert quality.false_alarm_warnings == 3
    assert quality.false_alarm_rate == pytest.approx(0.5)
    # lead time: event 15 caught by warning at 14 -> 1; event 28 by 26 -> 2
    assert quality.mean_lead_time_bars == pytest.approx(1.5)
    assert quality.crisis_events == 1
    assert quality.crisis_recall == pytest.approx(1.0)
    assert quality.warning_persistence == pytest.approx(2.0)  # runs 3,2,1


def test_t_pred_018_missed_events_are_counted():
    n = 20
    warnings = [False] * n
    events = [False] * n
    events[10] = True  # never warned
    quality = crash_warning_quality(
        warnings=warnings, events=events,
        warning_lookback_bars=5, forward_window_bars=5,
    )
    assert quality.caught_events == 0
    assert quality.missed_events == 1
    assert quality.miss_rate == 1.0
    assert quality.mean_lead_time_bars is None
    assert quality.warning_persistence is None  # no warning runs at all


def test_t_pred_018_no_events_means_no_recall_claims():
    quality = crash_warning_quality(
        warnings=[True, False, True],
        events=[False, False, False],
        warning_lookback_bars=2, forward_window_bars=2,
    )
    assert quality.miss_rate is None  # 0 events -> no claim
    assert quality.false_alarm_rate == pytest.approx(1.0)
