"""Prediction Intelligence closure tests — crash-event evaluation (§8)
and crash-intelligence completion (§7).

Covers:
- deterministic episode extraction (boundaries, None-label breaks)
- detection / miss / lead-time semantics (warnings strictly BEFORE)
- precision / FPR / F1 / warning frequency
- warning-horizon vs event-window separation
- calibration over the evaluation segment
- regime-conditioned metrics
- crisis-sample insufficiency (recorded, never hidden)
- per-split evaluation (no train/test pooling)
- warning-state derivation + mandate vocabulary mapping
"""

import pytest

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.crash import (
    RISK_STATE_VOCABULARY_MAP,
    crash_warning_state,
)
from data_engine.prediction.event_evaluation import (
    CrashEventEpisode,
    EventEvaluationConfig,
    evaluate_by_split,
    evaluate_crash_events,
    extract_crash_events,
)
from data_engine.prediction.evaluation import chronological_partitions


def _config(**overrides) -> EventEvaluationConfig:
    base = dict(
        label_definition_id="predl.test",
        label_threshold=0.10,
        horizon_bars=5,
        warning_threshold=0.5,
        warning_lookback_bars=10,
        forward_event_window_bars=5,
        min_crisis_events=5,
    )
    base.update(overrides)
    return EventEvaluationConfig(**base)


# ─── episode extraction ────────────────────────────────────────────────

class TestExtractCrashEvents:

    def test_contiguous_runs_merge_into_one_episode(self):
        labels = [False, True, True, True, False, False]
        episodes = extract_crash_events(labels)
        assert len(episodes) == 1
        assert episodes[0].start_index == 1
        assert episodes[0].end_index == 3
        assert episodes[0].length_bars == 3

    def test_separated_runs_are_separate_episodes(self):
        labels = [True, False, True, False, True]
        episodes = extract_crash_events(labels)
        assert len(episodes) == 3
        assert [e.start_index for e in episodes] == [0, 2, 4]

    def test_none_labels_break_runs(self):
        labels = [True, True, None, True, False]
        episodes = extract_crash_events(labels)
        assert len(episodes) == 2
        assert episodes[0] == CrashEventEpisode(
            event_index=0, start_index=0, end_index=1
        )
        assert episodes[1].start_index == 3

    def test_crisis_flags_mark_episodes(self):
        labels = [True, True, False, True, False]
        episodes = extract_crash_events(
            labels, crisis_flags=[True, False, False, False, False]
        )
        assert episodes[0].crisis is True
        assert episodes[1].crisis is False

    def test_all_negative_gives_no_episodes(self):
        assert extract_crash_events([False] * 20) == ()

    def test_crisis_flags_must_align(self):
        with pytest.raises(PredictionContractError):
            extract_crash_events([True, False], crisis_flags=[True])

    def test_episode_hash_deterministic(self):
        e1 = extract_crash_events([True, False])[0]
        e2 = extract_crash_events([True, False])[0]
        assert e1.event_hash == e2.event_hash


# ─── event evaluation ──────────────────────────────────────────────────

class TestEvaluateCrashEvents:

    def test_detection_with_prior_warning(self):
        # warning at t=3; event at t=5 -> detected, lead 2
        probabilities = [0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1]
        labels = [False] * 5 + [True] + [False] * 2
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(),
        )
        assert evaluation.total_events == 1
        assert evaluation.detected_events == 1
        assert evaluation.mean_lead_time_bars == 2.0
        assert evaluation.detection_rate == 1.0
        assert evaluation.recall == 1.0

    def test_missed_event_without_warning(self):
        probabilities = [0.1] * 8
        labels = [False] * 4 + [True] + [False] * 3
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert evaluation.detected_events == 0
        assert evaluation.missed_events == 1
        assert evaluation.miss_rate == 1.0

    def test_warning_at_event_index_does_not_count(self):
        # warning exactly AT the event bar is NOT a prior warning
        probabilities = [0.1, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1]
        labels = [False] * 4 + [True] + [False] * 3
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert evaluation.detected_events == 0

    def test_false_alarm_metrics(self):
        # warning at t=0 with no following event -> FP
        probabilities = [0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        labels = [False] * 8
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert evaluation.false_positive_warnings == 1
        assert evaluation.true_positive_warnings == 0
        assert evaluation.precision == 0.0
        assert evaluation.false_positive_rate is not None

    def test_precision_and_f1_together(self):
        # TP: warning at 0, event at 2 within the forward window
        # FP: warning at 6, no event after it
        probabilities = [0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.1]
        labels = [False, False, True, False, False, False, False, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert evaluation.true_positive_warnings == 1
        assert evaluation.false_positive_warnings == 1
        assert evaluation.precision == 0.5
        assert evaluation.detected_events == 1  # warning at 0 precedes event at 2
        assert evaluation.recall == 1.0
        assert evaluation.f1 == pytest.approx(
            2 * 0.5 * 1.0 / (0.5 + 1.0)
        )

    def test_calibration_metrics_present(self):
        probabilities = [0.2, 0.8, 0.3, 0.9, 0.1, 0.4, 0.6, 0.2]
        labels = [False, True, False, True, False, False, True, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert evaluation.brier is not None
        assert evaluation.log_loss_value is not None
        assert 0.0 <= evaluation.brier <= 1.0

    def test_regime_conditioned_metrics(self):
        probabilities = [0.9, 0.1, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1]
        labels = [False, False, False, True, False, False, False, False]
        regimes = ["NORMAL"] * 4 + ["STRESSED"] * 4
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(), regimes=regimes,
        )
        by_regime = {m.regime: m for m in evaluation.regimes}
        assert set(by_regime) == {"NORMAL", "STRESSED"}
        assert by_regime["NORMAL"].n_events == 1
        assert by_regime["NORMAL"].detected_events == 1
        assert by_regime["STRESSED"].n_events == 0

    def test_crisis_sample_insufficient_recorded(self):
        probabilities = [0.9, 0.1, 0.1, 0.1, 0.1, 0.1]
        labels = [False, False, False, False, True, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(min_crisis_events=5),
            crisis_flags=[False, False, False, False, True, False],
        )
        assert evaluation.crisis_events == 1
        assert evaluation.crisis_sample_status == (
            "CRISIS_SAMPLE_INSUFFICIENT"
        )

    def test_crisis_sample_sufficient_ok(self):
        # crisis event at 3 with a prior warning at 0 -> detected
        probabilities = [0.9, 0.1, 0.1, 0.1] + [0.1] * 8
        labels = [False, False, False, True] + [False] * 8
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(min_crisis_events=1),
            crisis_flags=[False, False, False, True] + [False] * 8,
        )
        assert evaluation.crisis_sample_status == "OK"
        assert evaluation.crisis_detected == 1
        assert evaluation.crisis_recall == 1.0

    def test_event_ownership_respects_segment_start(self):
        # a run starting AT the slice boundary is boundary-carried:
        # its true start may lie in an earlier segment -> NOT owned
        probabilities = [0.9, 0.1, 0.1, 0.1]
        labels = [True, True, False, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(), segment="tail", segment_start=2,
        )
        assert evaluation.total_events == 0

    def test_event_starting_inside_segment_is_owned(self):
        probabilities = [0.1, 0.1, 0.9, 0.1]
        labels = [False, False, True, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(), segment="tail", segment_start=2,
        )
        assert evaluation.total_events == 1

    def test_whole_series_owns_boundary_event(self):
        probabilities = [0.9, 0.1, 0.1, 0.1]
        labels = [True, False, False, False]
        evaluation = evaluate_crash_events(
            probabilities=probabilities, labels=labels,
            config=_config(), segment="all", segment_start=0,
        )
        assert evaluation.total_events == 1

    def test_probability_range_validated(self):
        with pytest.raises(PredictionContractError):
            evaluate_crash_events(
                probabilities=[1.5], labels=[False], config=_config()
            )

    def test_alignment_validated(self):
        with pytest.raises(PredictionContractError):
            evaluate_crash_events(
                probabilities=[0.1, 0.2], labels=[False], config=_config()
            )

    def test_evaluation_hash_deterministic(self):
        probabilities = [0.9, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
        labels = [False] * 4 + [True] + [False] * 3
        e1 = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        e2 = evaluate_crash_events(
            probabilities=probabilities, labels=labels, config=_config()
        )
        assert e1.evaluation_hash == e2.evaluation_hash


class TestEvaluateBySplit:

    def test_per_split_no_pooling(self):
        n = 120
        probabilities = [0.1 + (0.8 if i % 40 == 35 else 0.0)
                         for i in range(n)]
        labels = [i % 40 == 39 for i in range(n)]
        split = chronological_partitions(n, purge=2, embargo=3)
        results = evaluate_by_split(
            probabilities=probabilities, labels=labels,
            config=_config(), split=split,
        )
        segments = [r.segment for r in results]
        assert segments == [
            "train", "validation", "test", "final_oos", "paper"
        ]
        # segments are contiguous and non-overlapping by construction
        covered = []
        for r in results:
            covered.append(r.n_bars)
        assert sum(covered) <= n

    def test_events_owned_by_starting_segment(self):
        n = 120
        probabilities = [0.1] * n
        labels = [False] * n
        labels[75] = True  # inside the test segment region
        split = chronological_partitions(n, purge=2, embargo=3)
        results = evaluate_by_split(
            probabilities=probabilities, labels=labels,
            config=_config(), split=split,
        )
        owners = [
            r.segment for r in results if r.total_events > 0
        ]
        assert len(owners) == 1  # exactly one segment owns the event


# ─── crash completion (§7) ─────────────────────────────────────────────

class TestCrashCompletion:

    def test_warning_state_mapping(self):
        assert crash_warning_state("NO_SIGNAL") == "WARNING_INACTIVE"
        assert crash_warning_state("LOW_RISK") == "WARNING_INACTIVE"
        assert crash_warning_state("ELEVATED_RISK") == "WARNING_ACTIVE"
        assert crash_warning_state("HIGH_RISK") == "WARNING_ACTIVE"
        assert crash_warning_state("EXTREME_RISK") == "WARNING_ACTIVE"
        for refused in (
            "MODEL_UNCERTAIN", "DATA_INSUFFICIENT", "REGIME_UNKNOWN",
            "PREDICTION_BLOCKED", "EVIDENCE_INSUFFICIENT",
        ):
            assert crash_warning_state(refused) == "REFUSED"

    def test_mandate_vocabulary_map_is_total(self):
        required = {
            "NORMAL", "ELEVATED_RISK", "HIGH_RISK", "CRISIS",
            "INSUFFICIENT_EVIDENCE", "INVALID",
        }
        assert set(RISK_STATE_VOCABULARY_MAP) == required
        # every mapped target is a real project state
        for targets in RISK_STATE_VOCABULARY_MAP.values():
            for target in targets:
                assert isinstance(target, str) and target.isupper()
