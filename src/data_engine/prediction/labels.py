"""Crash label engine (§5, §14).

Crash labels are FUTURE-DEFINED by construction: the label at index t is
computed from closes[t+1 .. t+H] ONLY. The label/feature boundary is
structural — feature rows stop at t (``source_end == t``, see
``prediction.features``) and label windows start at t+1
(``window_start >= t+1``), so a boundary violation cannot be
represented without failing ``assert_label_feature_boundary`` (§14).

Label definitions are explicit and versioned (§5): threshold,
measurement window, forward horizon, asset scope, calibration period,
and creation version are ALL part of the label identity. Hidden label
definitions are impossible — the identity hash covers every field.
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.prediction.identity import (
    LABEL_DEFINITION_PREFIX,
    prefixed_hash,
)
from data_engine.prediction.contracts import (
    InsufficiencyState,
    PredictionContractError,
)


class CrashLabelDefinition(BaseModel):
    """One configurable crash label definition (§5).

    Example (the mandate's 20%-drawdown label):
        threshold=0.20, measurement_window=20, forward_horizon=20,
        asset_scope="SPX", calibration_period="2005-2024".

    ``measurement_window`` <= ``forward_horizon`` is enforced: the label
    measures a drawdown over the measurement window embedded within the
    forward horizon.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float
    measurement_window: int
    forward_horizon: int
    asset_scope: str
    calibration_period: str
    creation_version: str = "1.0.0"

    @field_validator("threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError(
                "crash threshold must be a drawdown fraction in (0, 1) — "
                "e.g. 0.10 / 0.15 / 0.20 / 0.30"
            )
        return v

    @field_validator("measurement_window", "forward_horizon")
    @classmethod
    def _validate_windows(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("windows must be positive integers (bars)")
        return v

    @model_validator(mode="after")
    def _validate_coherence(self) -> "CrashLabelDefinition":
        if self.measurement_window > self.forward_horizon:
            raise ValueError(
                "measurement_window cannot exceed forward_horizon"
            )
        return self

    @property
    def label_definition_id(self) -> str:
        """Identity covering EVERY definition field (``predl.``).

        Two definitions that differ in ANY field (threshold, windows,
        scope, calibration period, creation version) are DIFFERENT
        labels — no hidden definition drift.
        """
        return prefixed_hash(
            LABEL_DEFINITION_PREFIX,
            {
                "kind": "crash_label_definition",
                "threshold": self.threshold,
                "measurement_window": self.measurement_window,
                "forward_horizon": self.forward_horizon,
                "asset_scope": self.asset_scope,
                "calibration_period": self.calibration_period,
                "creation_version": self.creation_version,
            },
        )


class LabeledPoint(BaseModel):
    """One labeled historical point (§14).

    ``label`` is None when the forward window extends beyond available
    data — the outcome is NOT YET KNOWN and is never imputed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    timestamp: Optional[str]
    label: Optional[bool]
    label_definition_id: str
    window_start: int
    window_end: int

    @property
    def outcome_known(self) -> bool:
        return self.label is not None


def forward_max_drawdown(
    closes: Sequence[float],
    index: int,
    window: int,
) -> Optional[float]:
    """Max drawdown over closes[index+1 .. index+window] (or None).

    Returns None when the full window is not available (fail-closed:
    partial windows are never silently truncated).
    """
    end = index + window
    if end >= len(closes):
        return None
    peak = closes[index + 1]
    max_dd = 0.0
    for j in range(index + 1, end + 1):
        price = closes[j]
        if price > peak:
            peak = price
        dd = 1.0 - price / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def compute_crash_labels(
    closes: Sequence[float],
    definition: CrashLabelDefinition,
    *,
    timestamps: Optional[Sequence[object]] = None,
) -> Tuple[LabeledPoint, ...]:
    """Compute crash labels with a strict label/feature boundary (§14).

    The label at t uses closes[t+1..t+measurement_window] ONLY — future
    information enters LABELS, never features (T-PREV-002/T-PREV-003).
    Points whose outcome window is incomplete carry ``label=None``.
    """
    if timestamps is not None and len(timestamps) != len(closes):
        raise PredictionContractError("timestamps must align with closes")
    points: list[LabeledPoint] = []
    for t in range(len(closes)):
        dd = forward_max_drawdown(closes, t, definition.measurement_window)
        ts = None
        if timestamps is not None:
            ts_obj = timestamps[t]
            ts = (
                ts_obj.isoformat()
                if hasattr(ts_obj, "isoformat")
                else str(ts_obj)
            )
        points.append(
            LabeledPoint(
                index=t,
                timestamp=ts,
                label=None if dd is None else dd >= definition.threshold,
                label_definition_id=definition.label_definition_id,
                window_start=t + 1,
                window_end=t + definition.measurement_window,
            )
        )
    return tuple(points)


def assert_label_feature_boundary(
    feature_rows: Sequence,
    labeled_points: Sequence,
) -> None:
    """Prove the label/feature boundary (§14, T-PREV-003).

    Feature rows and labeled points are aligned BY BAR INDEX (feature
    rows begin at the warm-up index; labels exist for every bar). For
    every aligned pair: the feature row's source range must END at or
    before the label window STARTS. A violation raises (fail closed) —
    leakage is a defect, not a warning.
    """
    labels_by_index = {point.index: point for point in labeled_points}
    for feature in feature_rows:
        label = labels_by_index.get(feature.row_index)
        if label is None:
            raise PredictionContractError(
                f"no labeled point at bar index {feature.row_index} — "
                "features and labels must cover the same bars"
            )
        if feature.source_end >= label.window_start:
            raise PredictionContractError(
                "LABEL LEAKAGE: feature row at index "
                f"{feature.row_index} uses source index "
                f"{feature.source_end} which overlaps the label window "
                f"[{label.window_start}, {label.window_end}]"
            )


class CrisisSampleReading(BaseModel):
    """Crisis-sample sufficiency reading (§12).

    Crash intelligence requires enough crisis events for statistical
    claims. When positives are too few the status is
    CRISIS_SAMPLE_INSUFFICIENT and NO statistical robustness is claimed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    positive_labels: int
    total_labels: int
    min_positive_labels: int

    @property
    def status(self) -> str:
        if self.positive_labels < self.min_positive_labels:
            return InsufficiencyState.CRISIS_SAMPLE_INSUFFICIENT.value
        return "OK"

    @property
    def positive_rate(self) -> float:
        if self.total_labels == 0:
            return 0.0
        return self.positive_labels / self.total_labels


def crisis_sample_status(
    labeled_points: Sequence[LabeledPoint],
    *,
    min_positive_labels: int = 10,
) -> CrisisSampleReading:
    """Count realized positive labels and assess sufficiency (§12)."""
    known = [p for p in labeled_points if p.label is not None]
    positives = sum(1 for p in known if p.label)
    return CrisisSampleReading(
        positive_labels=positives,
        total_labels=len(known),
        min_positive_labels=min_positive_labels,
    )


__all__ = [
    "CrashLabelDefinition",
    "LabeledPoint",
    "compute_crash_labels",
    "forward_max_drawdown",
    "assert_label_feature_boundary",
    "CrisisSampleReading",
    "crisis_sample_status",
]
