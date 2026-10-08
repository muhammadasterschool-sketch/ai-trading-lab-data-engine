"""Crash-event evaluation over historical stress episodes (mandate §8).

Event discipline (all structural, all tested):
- event definition is EXPLICIT: episodes are contiguous runs of
  positive crash labels under a declared ``CrashLabelDefinition``
  (threshold/window/horizon are part of the label identity);
- event boundaries are DETERMINISTIC: first/last positive bar of the
  run — no smoothing, no merging across gaps, no hand-editing;
- no future information enters pre-event predictions: warnings are
  derived ONLY from probabilities at indices strictly BEFORE the
  event (warning lookback window ends at t-1);
- labels are used only for measurement — they are derived from
  permitted future information during label construction, never fed
  back into features (§14 boundary, asserted elsewhere);
- the WARNING HORIZON [t-lookback, t-1] is separate from the EVENT
  WINDOW [t, t+forward] — detection asks "was a warning active before
  the event?", false alarms ask "did an event follow the warning?";
- train/test contamination is prevented by evaluating PER SEGMENT:
  an event belongs to the segment containing its START index, and
  metrics are reported per segment — never pooled across the
  train/test boundary;
- survivorship and revision leakage are upstream concerns (PIT views,
  first-arrival-wins) — this module measures on what the PIT layer
  actually delivered.

Metric discipline (mandate §8: never optimize a single metric):
detection rate, missed-event count, false-positive rate, precision,
recall, F1, mean/median lead time, warning frequency, Brier score,
log loss, reliability, and regime-conditioned performance are all
reported together in one immutable, hash-stable report.
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.calibration import (
    brier_score,
    log_loss,
)
from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import EVENT_PREFIX, prefixed_hash


class CrashEventEpisode(BaseModel):
    """One historical crash episode with deterministic boundaries."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_index: int  # ordinal among extracted episodes
    start_index: int  # first positive-label bar (inclusive)
    end_index: int  # last positive-label bar (inclusive)
    crisis: bool = False  # severity flag (e.g. regime CRISIS overlap)

    @field_validator("event_index", "start_index", "end_index")
    @classmethod
    def _validate_indices(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("episode indices must be non-negative ints")
        return v

    @property
    def length_bars(self) -> int:
        return self.end_index - self.start_index + 1

    @property
    def event_hash(self) -> str:
        return prefixed_hash(
            EVENT_PREFIX,
            {
                "kind": "crash_event_episode",
                "event_index": self.event_index,
                "start_index": self.start_index,
                "end_index": self.end_index,
                "crisis": self.crisis,
            },
        )


def extract_crash_events(
    labels: Sequence[Optional[bool]],
    *,
    crisis_flags: Optional[Sequence[bool]] = None,
) -> Tuple[CrashEventEpisode, ...]:
    """Extract episodes as contiguous runs of positive labels.

    ``None`` labels (outcome not yet known) break a run — an episode
    never extends into unknown-outcome territory. Boundaries are the
    first and last positive bar of each run: deterministic, unedited.
    """
    if crisis_flags is not None and len(crisis_flags) != len(labels):
        raise PredictionContractError(
            "crisis_flags must align with labels"
        )
    episodes: list[CrashEventEpisode] = []
    run_start: Optional[int] = None
    for i, label in enumerate(labels):
        positive = label is True
        if positive and run_start is None:
            run_start = i
        elif not positive and run_start is not None:
            episodes.append((run_start, i - 1))
            run_start = None
    if run_start is not None:
        episodes.append((run_start, len(labels) - 1))

    out: list[CrashEventEpisode] = []
    for ordinal, (start, end) in enumerate(episodes):
        crisis = bool(
            crisis_flags is not None
            and any(crisis_flags[start:end + 1])
        )
        out.append(CrashEventEpisode(
            event_index=ordinal,
            start_index=start,
            end_index=end,
            crisis=crisis,
        ))
    return tuple(out)


class EventEvaluationConfig(BaseModel):
    """Explicit event-evaluation protocol (mandate §8).

    ``warning_lookback_bars`` — how far BEFORE an event a warning may
    count as detection (the warning horizon).
    ``forward_event_window_bars`` — how far AFTER a warning an event
    may occur for the warning to count as true (the event window).
    The two windows are deliberately separate measurements.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label_definition_id: str
    label_threshold: float
    horizon_bars: int
    warning_threshold: float = 0.25  # probability >= threshold => warning
    warning_lookback_bars: int = 10
    forward_event_window_bars: int = 10
    min_crisis_events: int = 5

    @field_validator("label_definition_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PredictionContractError(
                "label_definition_id is mandatory (event definition is "
                "explicit, never implicit)"
            )
        return v

    @field_validator("warning_threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("warning_threshold must be in (0, 1)")
        return v

    @field_validator(
        "horizon_bars", "warning_lookback_bars",
        "forward_event_window_bars", "min_crisis_events",
    )
    @classmethod
    def _validate_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("window/event parameters must be >= 1")
        return v


class RegimeConditionedMetrics(BaseModel):
    """Event metrics restricted to one regime bucket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    regime: str
    n_bars: int
    n_events: int
    detected_events: int
    mean_lead_time_bars: Optional[float] = None

    @property
    def detection_rate(self) -> Optional[float]:
        if self.n_events == 0:
            return None
        return self.detected_events / self.n_events


class CrashEventEvaluation(BaseModel):
    """Full event-level evaluation report (mandate §8 field set)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    config: EventEvaluationConfig
    segment: str  # e.g. "train" / "validation" / "test" / "all"
    n_bars: int
    total_events: int
    detected_events: int
    missed_events: int
    total_warnings: int
    true_positive_warnings: int
    false_positive_warnings: int
    true_negative_bars: int
    mean_lead_time_bars: Optional[float] = None
    median_lead_time_bars: Optional[float] = None
    warning_frequency: Optional[float] = None
    brier: Optional[float] = None
    log_loss_value: Optional[float] = None
    mean_probability: Optional[float] = None
    base_rate: Optional[float] = None
    regimes: Tuple[RegimeConditionedMetrics, ...] = ()
    crisis_events: int = 0
    crisis_detected: int = 0
    crisis_sample_status: str = "CRISIS_SAMPLE_INSUFFICIENT"
    events: Tuple[CrashEventEpisode, ...] = ()

    @property
    def detection_rate(self) -> Optional[float]:
        if self.total_events == 0:
            return None
        return self.detected_events / self.total_events

    @property
    def miss_rate(self) -> Optional[float]:
        if self.total_events == 0:
            return None
        return self.missed_events / self.total_events

    @property
    def recall(self) -> Optional[float]:
        """Event recall — same as detection rate (explicit alias)."""
        return self.detection_rate

    @property
    def precision(self) -> Optional[float]:
        if self.total_warnings == 0:
            return None
        return self.true_positive_warnings / self.total_warnings

    @property
    def false_positive_rate(self) -> Optional[float]:
        """FP / (FP + TN) over bars — classic bar-level FPR."""
        denominator = self.false_positive_warnings + self.true_negative_bars
        if denominator == 0:
            return None
        return self.false_positive_warnings / denominator

    @property
    def f1(self) -> Optional[float]:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2.0 * p * r / (p + r)

    @property
    def crisis_recall(self) -> Optional[float]:
        if self.crisis_events == 0:
            return None
        return self.crisis_detected / self.crisis_events

    @property
    def evaluation_hash(self) -> str:
        return prefixed_hash(
            EVENT_PREFIX,
            {
                "kind": "crash_event_evaluation",
                "config": {
                    "label_definition_id": self.config.label_definition_id,
                    "label_threshold": self.config.label_threshold,
                    "horizon_bars": self.config.horizon_bars,
                    "warning_threshold": self.config.warning_threshold,
                    "warning_lookback_bars": (
                        self.config.warning_lookback_bars
                    ),
                    "forward_event_window_bars": (
                        self.config.forward_event_window_bars
                    ),
                },
                "segment": self.segment,
                "n_bars": self.n_bars,
                "total_events": self.total_events,
                "detected_events": self.detected_events,
                "missed_events": self.missed_events,
                "total_warnings": self.total_warnings,
                "true_positive_warnings": self.true_positive_warnings,
                "false_positive_warnings": self.false_positive_warnings,
                "true_negative_bars": self.true_negative_bars,
                "crisis_events": self.crisis_events,
                "crisis_detected": self.crisis_detected,
            },
        )


def evaluate_crash_events(
    *,
    probabilities: Sequence[float],
    labels: Sequence[Optional[bool]],
    config: EventEvaluationConfig,
    segment: str = "all",
    regimes: Optional[Sequence[str]] = None,
    crisis_flags: Optional[Sequence[bool]] = None,
    segment_start: int = 0,
) -> CrashEventEvaluation:
    """Evaluate warning quality against extracted crash events (§8).

    ``probabilities[i]`` is the forecast made AT bar i (using only
    PIT information at i); ``labels[i]`` is the eventual outcome for
    bar i. ``segment_start`` is the absolute index of
    ``probabilities[0]`` when evaluating a sub-segment.

    Event ownership rule (deterministic): episodes are extracted from
    the PASSED arrays (indices relative to them). An episode that
    starts at relative index 0 while ``segment_start > 0`` is a
    boundary-carried run — its true start may lie in an earlier
    segment and is NOT provable from the slice — so it is NOT owned
    by this segment. Every other episode provably starts inside the
    segment and is owned. Metrics are therefore per-segment and never
    pooled across the train/test boundary.
    """
    n = len(probabilities)
    if len(labels) != n:
        raise PredictionContractError(
            "probabilities and labels must align 1:1"
        )
    if n == 0:
        raise PredictionContractError("empty evaluation segment")
    if regimes is not None and len(regimes) != n:
        raise PredictionContractError("regimes must align 1:1")
    for p in probabilities:
        if not (0.0 <= p <= 1.0):
            raise PredictionContractError(
                f"probability out of range: {p!r}"
            )

    events = extract_crash_events(labels, crisis_flags=crisis_flags)
    # Ownership: boundary-carried runs (relative start 0 in a slice)
    # are not provably owned by this segment — excluded, never pooled.
    owned = tuple(
        e for e in events
        if not (e.start_index == 0 and segment_start > 0)
    )

    warnings = [p >= config.warning_threshold for p in probabilities]

    # Detection: an owned event at relative index t is caught when a
    # warning was active in [t - lookback, t - 1] — strictly BEFORE it.
    detected = 0
    lead_times: list[int] = []
    crisis_events = 0
    crisis_detected = 0
    for event in owned:
        t_rel = event.start_index
        window_start = max(0, t_rel - config.warning_lookback_bars)
        warning_idx = [
            w for w in range(window_start, t_rel) if warnings[w]
        ]
        caught = bool(warning_idx)
        if caught:
            detected += 1
            lead_times.append(t_rel - max(warning_idx))
        if event.crisis:
            crisis_events += 1
            if caught:
                crisis_detected += 1

    # Bar-level confusion for precision / FPR: a warning at t is TP when
    # an event (label True) occurs in [t, t + forward]; TN = non-warning
    # bar with no event in its forward window; FP = warning with no
    # subsequent event.
    tp = 0
    fp = 0
    tn = 0
    for t in range(n):
        window_end = min(n - 1, t + config.forward_event_window_bars)
        event_follows = any(
            labels[j] is True for j in range(t, window_end + 1)
        )
        if warnings[t]:
            if event_follows:
                tp += 1
            else:
                fp += 1
        else:
            if not event_follows:
                tn += 1

    total_warnings = sum(1 for w in warnings if w)
    known = [
        (float(p), 1 if lab else 0)
        for p, lab in zip(probabilities, labels)
        if lab is not None
    ]
    brier: Optional[float] = None
    ll: Optional[float] = None
    if known:
        brier = brier_score(
            [p for p, _ in known], [o for _, o in known]
        )
        ll = log_loss([p for p, _ in known], [o for _, o in known])

    sorted_leads = sorted(lead_times)
    median_lead: Optional[float] = (
        sorted_leads[len(sorted_leads) // 2]
        if sorted_leads else None
    )

    regime_metrics: list[RegimeConditionedMetrics] = []
    if regimes is not None:
        by_regime: dict[str, dict] = {}
        for i, regime in enumerate(regimes):
            bucket = by_regime.setdefault(
                regime,
                {"n_bars": 0, "events": [], "leads": []},
            )
            bucket["n_bars"] += 1
        for event in owned:
            t_rel = event.start_index
            if 0 <= t_rel < n:
                regime = regimes[t_rel]
                by_regime[regime]["events"].append(event)
                window_start = max(0, t_rel - config.warning_lookback_bars)
                warning_idx = [
                    w for w in range(window_start, t_rel) if warnings[w]
                ]
                if warning_idx:
                    by_regime[regime]["leads"].append(
                        t_rel - max(warning_idx)
                    )
        for regime in sorted(by_regime):
            bucket = by_regime[regime]
            detected_here = len(bucket["leads"])
            regime_metrics.append(RegimeConditionedMetrics(
                regime=regime,
                n_bars=bucket["n_bars"],
                n_events=len(bucket["events"]),
                detected_events=detected_here,
                mean_lead_time_bars=(
                    math.fsum(bucket["leads"]) / len(bucket["leads"])
                    if bucket["leads"] else None
                ),
            ))

    crisis_status = (
        "OK"
        if crisis_events >= config.min_crisis_events
        else "CRISIS_SAMPLE_INSUFFICIENT"
    )

    return CrashEventEvaluation(
        config=config,
        segment=segment,
        n_bars=n,
        total_events=len(owned),
        detected_events=detected,
        missed_events=len(owned) - detected,
        total_warnings=total_warnings,
        true_positive_warnings=tp,
        false_positive_warnings=fp,
        true_negative_bars=tn,
        mean_lead_time_bars=(
            math.fsum(lead_times) / len(lead_times)
            if lead_times else None
        ),
        median_lead_time_bars=median_lead,
        warning_frequency=total_warnings / n,
        brier=brier,
        log_loss_value=ll,
        mean_probability=math.fsum(float(p) for p in probabilities) / n,
        base_rate=(
            sum(1 for lab in labels if lab is True) / n
        ),
        regimes=tuple(regime_metrics),
        crisis_events=crisis_events,
        crisis_detected=crisis_detected,
        crisis_sample_status=crisis_status,
        events=owned,
    )


def evaluate_by_split(
    *,
    probabilities: Sequence[float],
    labels: Sequence[Optional[bool]],
    config: EventEvaluationConfig,
    split,
    regimes: Optional[Sequence[str]] = None,
    crisis_flags: Optional[Sequence[bool]] = None,
) -> Tuple[CrashEventEvaluation, ...]:
    """Evaluate events PER SPLIT SEGMENT (mandate §8 anti-contamination).

    Train, validation, test, final-OOS and paper segments are evaluated
    separately — metrics are never pooled across the boundary, and an
    event's owning segment is the one containing its start index.
    Requires a :class:`evaluation.ChronologicalSplit`-like object
    exposing ``train_indices()`` / ``validation_indices()`` /
    ``test_indices()`` / ``final_oos_indices()`` / ``paper_indices()``.
    """
    def _segment(name: str, indices) -> Optional[CrashEventEvaluation]:
        idx = list(indices)
        if not idx:
            return None
        start = idx[0]
        return evaluate_crash_events(
            probabilities=[probabilities[i] for i in idx],
            labels=[labels[i] for i in idx],
            config=config,
            segment=name,
            regimes=(
                [regimes[i] for i in idx]
                if regimes is not None else None
            ),
            crisis_flags=(
                [crisis_flags[i] for i in idx]
                if crisis_flags is not None else None
            ),
            segment_start=start,
        )

    results = []
    for name, indices in (
        ("train", split.train_indices()),
        ("validation", split.validation_indices()),
        ("test", split.test_indices()),
        ("final_oos", split.final_oos_indices()),
        ("paper", split.paper_indices()),
    ):
        segment_result = _segment(name, indices)
        if segment_result is not None:
            results.append(segment_result)
    return tuple(results)


__all__ = [
    "CrashEventEpisode",
    "extract_crash_events",
    "EventEvaluationConfig",
    "RegimeConditionedMetrics",
    "CrashEventEvaluation",
    "evaluate_crash_events",
    "evaluate_by_split",
]
