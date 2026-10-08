"""Evidence score (§17) — explicit, inspectable, never subjective.

The evidence score is NOT a confidence number invented by a model. It is
a weighted composite over EXPLICIT dimensions, each individually
inspectable, each mapped to [0, 1] from a declared raw input. Missing
dimensions score 0 and drag the verdict toward EVIDENCE_INSUFFICIENT —
insufficient evidence is a recorded state, never hidden (§57).
"""

import math
from typing import Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import (
    DriftState,
    InsufficiencyState,
    PredictionContractError,
)
from data_engine.prediction.identity import EVIDENCE_PREFIX, prefixed_hash

#: The eleven evidence dimensions (§17) with their weights.
#: Weights sum to 1.0; every component is inspectable.
EVIDENCE_DIMENSIONS: Tuple[Tuple[str, float], ...] = (
    ("data_quality", 0.12),
    ("sample_size", 0.08),
    ("historical_coverage", 0.10),
    ("regime_coverage", 0.10),
    ("model_calibration", 0.10),
    ("out_of_sample_performance", 0.12),
    ("stability", 0.10),
    ("cross_validation_consistency", 0.08),
    ("feature_integrity", 0.08),
    ("drift_status", 0.06),
    ("prediction_freshness", 0.06),
)

#: DriftState -> evidence contribution (§17 drift dimension).
DRIFT_STATE_VALUE = {
    DriftState.STABLE: 1.0,
    DriftState.WATCH: 0.6,
    DriftState.DEGRADED: 0.3,
    DriftState.DRIFTED: 0.1,
    DriftState.INVALID: 0.0,
}

#: Composite score floor; below this the verdict is insufficient.
EVIDENCE_SCORE_FLOOR = 0.5

#: String value -> DriftState lookup (callers may pass either form).
_DRIFT_STATE_BY_VALUE = {state.value: state for state in DriftState}


class EvidenceComponent(BaseModel):
    """One inspectable evidence dimension (§17)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str
    raw: Optional[str]
    value: float
    weight: float

    @property
    def weighted_contribution(self) -> float:
        return self.value * self.weight


class EvidenceAssessment(BaseModel):
    """Composite evidence verdict (§17)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    components: Tuple[EvidenceComponent, ...]
    score: Optional[float]
    status: str

    @property
    def insufficient(self) -> bool:
        return self.status == InsufficiencyState.EVIDENCE_INSUFFICIENT.value

    @property
    def evidence_hash(self) -> str:
        return prefixed_hash(
            EVIDENCE_PREFIX,
            {
                "kind": "evidence_assessment",
                "components": [
                    {
                        "dimension": c.dimension,
                        "raw": c.raw,
                        "value": c.value,
                        "weight": c.weight,
                    }
                    for c in self.components
                ],
                "score": self.score,
                "status": self.status,
            },
        )


def evidence_assessment(
    values: Mapping[str, object],
    *,
    weights: Optional[Mapping[str, float]] = None,
) -> EvidenceAssessment:
    """Compose the evidence score from explicit dimension inputs (§17).

    Each input is 0..1, a DriftState, or None/missing (treated as 0).
    Verdict rules (fail toward insufficiency):
    - any dimension contributing 0 -> EVIDENCE_INSUFFICIENT
    - composite score < 0.5 -> EVIDENCE_INSUFFICIENT
    """
    weight_map = dict(weights) if weights is not None else dict(
        EVIDENCE_DIMENSIONS
    )
    components: list[EvidenceComponent] = []
    for dimension, default_weight in EVIDENCE_DIMENSIONS:
        weight = float(weight_map.get(dimension, default_weight))
        if weight < 0:
            raise PredictionContractError("evidence weights must be >= 0")
        raw = values.get(dimension)
        if raw is None:
            value = 0.0
        elif isinstance(raw, DriftState):
            value = DRIFT_STATE_VALUE[raw]
        elif isinstance(raw, str) and raw in _DRIFT_STATE_BY_VALUE:
            value = DRIFT_STATE_VALUE[_DRIFT_STATE_BY_VALUE[raw]]
        else:
            try:
                numeric = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise PredictionContractError(
                    f"evidence dimension {dimension!r} must be numeric, a "
                    f"DriftState, or None — got {raw!r}"
                ) from exc
            if not (0.0 <= numeric <= 1.0):
                raise PredictionContractError(
                    f"evidence dimension {dimension!r} must map to [0, 1] "
                    f"— got {numeric}"
                )
            value = numeric
        components.append(
            EvidenceComponent(
                dimension=dimension,
                raw=(None if raw is None else str(raw)),
                value=value,
                weight=weight,
            )
        )
    total_weight = math.fsum(c.weight for c in components)
    if total_weight <= 0:
        raise PredictionContractError("total evidence weight must be > 0")
    score = math.fsum(c.weighted_contribution for c in components) / total_weight
    any_zero = any(c.value == 0.0 for c in components)
    insufficient = any_zero or score < EVIDENCE_SCORE_FLOOR
    return EvidenceAssessment(
        components=tuple(components),
        score=score,
        status=(
            InsufficiencyState.EVIDENCE_INSUFFICIENT.value
            if insufficient
            else "OK"
        ),
    )


__all__ = [
    "EVIDENCE_DIMENSIONS",
    "DRIFT_STATE_VALUE",
    "EVIDENCE_SCORE_FLOOR",
    "EvidenceComponent",
    "EvidenceAssessment",
    "evidence_assessment",
]
