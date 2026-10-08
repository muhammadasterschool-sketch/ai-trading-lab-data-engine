"""Uncertainty engine (§19).

Every prediction output includes uncertainty. Methods: empirical
intervals from history, analytic probability bands (Wald), ensemble
dispersion. When uncertainty is excessive the prediction status becomes
MODEL_UNCERTAIN — uncertainty is never hidden (§57).
"""

import math
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import PredictionContractError

#: Closed set of supported confidence levels with their z-scores.
#: Deterministic by table — no scipy, no runtime approximation.
_Z_SCORES = {
    0.80: 1.2815515655446004,
    0.90: 1.6448536269514722,
    0.95: 1.959963984540054,
}


def z_score(level: float) -> float:
    """z-score for a supported confidence level (closed set)."""
    if level not in _Z_SCORES:
        raise PredictionContractError(
            f"unsupported confidence level {level!r}; supported: "
            f"{sorted(_Z_SCORES)}"
        )
    return _Z_SCORES[level]


class UncertaintyBand(BaseModel):
    """One uncertainty band around a point estimate (§19)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    point: Optional[float]
    lower: float
    upper: float
    level: float
    dispersion: Optional[float] = None

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def relative_width(self) -> Optional[float]:
        if self.point is None or self.point == 0:
            return None
        return self.width / abs(self.point)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Deterministic linear-interpolation quantile (inclusive method)."""
    if not sorted_values:
        raise PredictionContractError("quantile of empty sequence")
    if not (0.0 <= q <= 1.0):
        raise PredictionContractError("q must be in [0, 1]")
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def empirical_interval(
    values: Sequence[float],
    *,
    level: float = 0.8,
    point: Optional[float] = None,
) -> UncertaintyBand:
    """Empirical quantile interval over a historical sample (§19)."""
    if not values:
        raise PredictionContractError("values must be non-empty")
    for v in values:
        if v != v:
            raise PredictionContractError("NaN values are not allowed")
    ordered = sorted(float(v) for v in values)
    tail = (1.0 - level) / 2.0
    lower = _quantile(ordered, tail)
    upper = _quantile(ordered, 1.0 - tail)
    return UncertaintyBand(
        method="empirical-quantile",
        point=point if point is not None else ordered[len(ordered) // 2],
        lower=lower,
        upper=upper,
        level=level,
    )


def probability_band(
    probability: float,
    *,
    n_effective: int,
    level: float = 0.8,
) -> UncertaintyBand:
    """Analytic (Wald) band for a probability given effective sample size.

    The band is clamped to [0, 1]. Small effective samples produce WIDE
    bands — that width is the honest uncertainty, never shrunk.
    """
    if not (0.0 <= probability <= 1.0):
        raise PredictionContractError(
            f"probability out of range: {probability!r}"
        )
    if n_effective < 1:
        raise PredictionContractError("n_effective must be >= 1")
    z = z_score(level)
    half = z * math.sqrt(max(probability * (1.0 - probability), 0.0) / n_effective)
    return UncertaintyBand(
        method="wald-probability",
        point=probability,
        lower=max(0.0, probability - half),
        upper=min(1.0, probability + half),
        level=level,
    )


def ensemble_band(
    member_values: Sequence[float],
    *,
    level: float = 0.8,
) -> UncertaintyBand:
    """Ensemble dispersion band: member min..max (§19)."""
    if not member_values:
        raise PredictionContractError("member_values must be non-empty")
    for v in member_values:
        if not (0.0 <= v <= 1.0):
            raise PredictionContractError(
                "ensemble members must be probabilities in [0, 1]"
            )
    members = sorted(float(v) for v in member_values)
    point = members[len(members) // 2]
    return UncertaintyBand(
        method="ensemble-dispersion",
        point=point,
        lower=members[0],
        upper=members[-1],
        level=level,
        dispersion=members[-1] - members[0],
    )


#: Width above which a probability band declares MODEL_UNCERTAIN (§19).
MAX_PROBABILITY_BAND_WIDTH = 0.5


def is_uncertain(band: UncertaintyBand) -> bool:
    """Excessive-uncertainty test for probability bands (§19)."""
    return band.width >= MAX_PROBABILITY_BAND_WIDTH


__all__ = [
    "z_score",
    "UncertaintyBand",
    "empirical_interval",
    "probability_band",
    "ensemble_band",
    "is_uncertain",
    "MAX_PROBABILITY_BAND_WIDTH",
]
