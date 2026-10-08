"""Prediction evaluation (§13, §32, §33, §34, §35).

- ``chronological_partitions``: TRAIN -> VALIDATION -> TEST -> FINAL OOS
  -> PAPER with mandated purge/embargo gaps; no future period can leak
  into fitting, scaling, or selection (§13).
- ``evaluate_walk_forward``: walk-forward prediction evaluation that
  REUSES the Phase 7 plan builder (``research_validation.walk_forward``)
  — leakage-free windows are already unrepresentable there; this module
  adds the prediction-outcome pairing (§35).
- ``crash_warning_quality``: HOW EARLY? HOW OFTEN WRONG? HOW OFTEN
  MISSED? — the mandated crash-warning quality measurements (§33). No
  usefulness claim is possible without them.
"""

import math
from typing import Callable, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import OUTPUT_PREFIX, prefixed_hash
from data_engine.research_validation.walk_forward import (
    WalkForwardWindow,
    build_walk_forward_plan,
)


class ChronologicalSplit(BaseModel):
    """Chronological data partition with purge/embargo gaps (§13).

    Inclusive integer index ranges. ``purge`` separates TRAIN end from
    VALIDATION start (label-horizon overlap removal); ``embargo``
    separates every later block. Random shuffling of history is not
    representable — ranges are ordered and disjoint BY CONSTRUCTION.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_bars: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int
    final_oos_start: int
    final_oos_end: int
    paper_start: int
    paper_end: int
    purge: int
    embargo: int

    @field_validator("n_bars", "purge", "embargo")
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("must be a non-negative int")
        return v

    def train_indices(self) -> range:
        return range(self.train_start, self.train_end + 1)

    def validation_indices(self) -> range:
        return range(self.validation_start, self.validation_end + 1)

    def test_indices(self) -> range:
        return range(self.test_start, self.test_end + 1)

    def final_oos_indices(self) -> range:
        return range(self.final_oos_start, self.final_oos_end + 1)

    def paper_indices(self) -> range:
        return range(self.paper_start, self.paper_end + 1)


def chronological_partitions(
    n: int,
    *,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.15,
    test_fraction: float = 0.15,
    purge: int = 5,
    embargo: int = 10,
) -> ChronologicalSplit:
    """Build the mandated chronological partition (§13).

    Fractions apply to TRAIN/VALIDATION/TEST; the remainder is split
    evenly between FINAL OOS and PAPER. Raises when the data cannot
    support the partition with the mandated gaps — never silently
    shrinks them.
    """
    if n < 8:
        raise PredictionContractError(
            "chronological partition needs at least 8 bars"
        )
    if train_fraction <= 0 or validation_fraction <= 0 or test_fraction <= 0:
        raise PredictionContractError("fractions must be positive")
    if train_fraction + validation_fraction + test_fraction >= 1.0:
        raise PredictionContractError(
            "train + validation + test fractions must leave room for "
            "final OOS + paper"
        )
    if purge < 0 or embargo < 0:
        raise PredictionContractError("purge/embargo must be >= 0")

    train_end = int(n * train_fraction) - 1
    validation_start = train_end + 1 + purge
    validation_end = validation_start + int(n * validation_fraction) - 1
    test_start = validation_end + 1 + embargo
    test_end = test_start + int(n * test_fraction) - 1
    remaining = n - 1 - test_end
    if remaining < 2:
        raise PredictionContractError(
            "not enough bars for final OOS + paper blocks with the "
            "mandated gaps (§13)"
        )
    half = remaining // 2
    final_oos_start = test_end + 1 + embargo
    final_oos_end = final_oos_start + half - 1
    paper_start = final_oos_end + 1
    paper_end = n - 1
    if paper_end < paper_start:
        raise PredictionContractError(
            "paper block empty — partition cannot be represented (§13)"
        )
    return ChronologicalSplit(
        n_bars=n,
        train_start=0,
        train_end=train_end,
        validation_start=validation_start,
        validation_end=validation_end,
        test_start=test_start,
        test_end=test_end,
        final_oos_start=final_oos_start,
        final_oos_end=final_oos_end,
        paper_start=paper_start,
        paper_end=paper_end,
        purge=purge,
        embargo=embargo,
    )


class PredictionOutcomePair(BaseModel):
    """One walk-forward forecast with its eventual outcome (§35)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    window_index: int
    forecast_probability: float
    actual: Optional[bool]
    horizon_bars: int

    @property
    def squared_error(self) -> Optional[float]:
        if self.actual is None:
            return None
        return (self.forecast_probability - (1.0 if self.actual else 0.0)) ** 2


def evaluate_walk_forward(
    *,
    model_factory: Callable[[], object],
    X: Sequence[Sequence[float]],
    y: Sequence[int],
    data_length: int,
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
    embargo: int = 0,
    horizon_bars: int = 1,
) -> Tuple[PredictionOutcomePair, ...]:
    """Walk-forward prediction evaluation (§35).

    For every window in a leakage-free Phase 7 plan: a FRESH model is
    fitted on the train block (no state bleed across windows) and
    evaluated on the test block. Every prediction is paired with its
    eventual outcome.
    """
    if len(X) != len(y):
        raise PredictionContractError("X and y must align 1:1")
    if data_length != len(X):
        raise PredictionContractError("data_length must equal len(X)")
    if horizon_bars < 1:
        raise PredictionContractError("horizon_bars must be >= 1")
    plan: Tuple[WalkForwardWindow, ...] = build_walk_forward_plan(
        data_length,
        train_size,
        test_size,
        step=step,
        embargo=embargo,
    )
    pairs: list[PredictionOutcomePair] = []
    for window in plan:
        model = model_factory()
        fit = getattr(model, "fit", None)
        predict = getattr(model, "predict_proba", None)
        if fit is None or predict is None:
            raise PredictionContractError(
                "model_factory must produce objects with fit() and "
                "predict_proba()"
            )
        train_X = [X[i] for i in window.train_indices()]
        train_y = [y[i] for i in window.train_indices()]
        fit(train_X, train_y)
        for i in window.test_indices():
            forecast = float(predict(X[i]))
            actual_index = i + horizon_bars - 1
            actual: Optional[bool]
            if actual_index < len(y):
                actual = bool(y[actual_index])
            else:
                actual = None  # outcome beyond available data — not imputed
            pairs.append(
                PredictionOutcomePair(
                    index=i,
                    window_index=window.window_index,
                    forecast_probability=forecast,
                    actual=actual,
                    horizon_bars=horizon_bars,
                )
            )
    return tuple(pairs)


class CrashWarningQuality(BaseModel):
    """Crash-warning quality measurements (§33).

    Answers the mandated questions: how early (mean lead time), how
    often wrong (false alarm rate), how often missed (miss rate), how
    stable (warning persistence), crisis recall, and how regime-aware
    the measurements are (per-crisis recall).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    warning_lookback_bars: int
    forward_window_bars: int
    total_events: int
    caught_events: int
    missed_events: int
    miss_rate: Optional[float]
    total_warnings: int
    false_alarm_warnings: int
    false_alarm_rate: Optional[float]
    mean_lead_time_bars: Optional[float]
    warning_persistence: Optional[float]
    crisis_events: int = 0
    crisis_caught: int = 0

    @property
    def crisis_recall(self) -> Optional[float]:
        if self.crisis_events == 0:
            return None
        return self.crisis_caught / self.crisis_events

    @property
    def quality_hash(self) -> str:
        return prefixed_hash(
            OUTPUT_PREFIX,
            {
                "kind": "crash_warning_quality",
                "warning_lookback_bars": self.warning_lookback_bars,
                "forward_window_bars": self.forward_window_bars,
                "total_events": self.total_events,
                "caught_events": self.caught_events,
                "missed_events": self.missed_events,
                "total_warnings": self.total_warnings,
                "false_alarm_warnings": self.false_alarm_warnings,
            },
        )


def crash_warning_quality(
    *,
    warnings: Sequence[bool],
    events: Sequence[bool],
    crisis_flags: Optional[Sequence[bool]] = None,
    warning_lookback_bars: int = 10,
    forward_window_bars: int = 10,
) -> CrashWarningQuality:
    """Measure crash-warning quality over aligned boolean series (§33).

    - an event at t is CAUGHT when a warning was active in
      [t - lookback, t - 1]; lead time = t - latest warning in window
    - a warning at t is a FALSE ALARM when no event occurs in
      [t, t + forward]
    - persistence = mean run length of consecutive warning bars
    - crisis recall is measured over crisis-flagged events only
    """
    if len(warnings) != len(events) or not warnings:
        raise PredictionContractError(
            "warnings and events must be aligned and non-empty"
        )
    if warning_lookback_bars < 1 or forward_window_bars < 1:
        raise PredictionContractError("windows must be >= 1 bar")
    if crisis_flags is not None and len(crisis_flags) != len(events):
        raise PredictionContractError("crisis_flags must align with events")
    n = len(events)

    total_events = sum(1 for e in events if e)
    caught = 0
    missed = 0
    lead_times: list[int] = []
    crisis_events = 0
    crisis_caught = 0
    for t in range(n):
        if not events[t]:
            continue
        window_start = max(0, t - warning_lookback_bars)
        warning_indices = [
            w for w in range(window_start, t) if warnings[w]
        ]
        event_caught = bool(warning_indices)
        if event_caught:
            caught += 1
            lead_times.append(t - max(warning_indices))
        else:
            missed += 1
        if crisis_flags is not None and crisis_flags[t]:
            crisis_events += 1
            if event_caught:
                crisis_caught += 1

    total_warnings = sum(1 for w in warnings if w)
    false_alarms = 0
    for t in range(n):
        if not warnings[t]:
            continue
        window_end = min(n - 1, t + forward_window_bars)
        if not any(events[j] for j in range(t, window_end + 1)):
            false_alarms += 1

    runs: list[int] = []
    run = 0
    for w in warnings:
        if w:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    persistence = (
        math.fsum(runs) / len(runs) if runs else None
    )
    return CrashWarningQuality(
        warning_lookback_bars=warning_lookback_bars,
        forward_window_bars=forward_window_bars,
        total_events=total_events,
        caught_events=caught,
        missed_events=missed,
        miss_rate=(missed / total_events) if total_events else None,
        total_warnings=total_warnings,
        false_alarm_warnings=false_alarms,
        false_alarm_rate=(false_alarms / total_warnings) if total_warnings else None,
        mean_lead_time_bars=(
            math.fsum(lead_times) / len(lead_times) if lead_times else None
        ),
        warning_persistence=persistence,
        crisis_events=crisis_events,
        crisis_caught=crisis_caught,
    )


__all__ = [
    "ChronologicalSplit",
    "chronological_partitions",
    "PredictionOutcomePair",
    "evaluate_walk_forward",
    "CrashWarningQuality",
    "crash_warning_quality",
]
