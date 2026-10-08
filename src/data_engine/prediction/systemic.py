"""Systemic-risk / contagion layer (§25).

Measurements: pairwise cross-asset correlations, average correlation,
correlation dispersion, and correlation-spike detection against a
baseline period. Sector synchronization and concentration are recorded
as inputs to systemic readings.

Epistemic discipline (§25): correlation is NOT prediction, and neither
is causation. This module measures co-movement only; causal hypotheses
require separate evidence and are never claimed here.
"""

import math
from typing import Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import OUTPUT_PREFIX, prefixed_hash


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        raise PredictionContractError(
            "correlation needs aligned series with >= 2 observations"
        )
    n = len(xs)
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    cov = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = math.fsum((x - mean_x) ** 2 for x in xs)
    var_y = math.fsum((y - mean_y) ** 2 for y in ys)
    if var_x == 0.0 or var_y == 0.0:
        raise PredictionContractError(
            "correlation undefined for zero-variance series — record the "
            "input as unusable rather than guessing"
        )
    return cov / math.sqrt(var_x * var_y)


def correlation_matrix(
    returns_by_symbol: Mapping[str, Sequence[float]],
) -> Tuple[Tuple[str, str, float], ...]:
    """Pairwise Pearson correlations, deterministic symbol order.

    Returns a flat, sorted tuple of (symbol_a, symbol_b, correlation).
    Deterministic: symbols sorted, ``math.fsum`` accumulation.
    """
    symbols = sorted(returns_by_symbol)
    for symbol in symbols:
        if len(returns_by_symbol[symbol]) < 2:
            raise PredictionContractError(
                f"symbol {symbol!r} has fewer than 2 return observations"
            )
    out: list[tuple[str, str, float]] = []
    for i, a in enumerate(symbols):
        for b in symbols[i + 1:]:
            rho = _pearson(returns_by_symbol[a], returns_by_symbol[b])
            out.append((a, b, round(rho, 12)))
    return tuple(out)


def average_correlation(
    matrix: Sequence[Tuple[str, str, float]],
) -> Optional[float]:
    """Mean pairwise correlation (None when no pairs exist)."""
    if not matrix:
        return None
    return math.fsum(rho for _, _, rho in matrix) / len(matrix)


def correlation_dispersion(
    matrix: Sequence[Tuple[str, str, float]],
) -> Optional[float]:
    """Population std of pairwise correlations (None when < 2 pairs)."""
    if len(matrix) < 2:
        return None
    mean = average_correlation(matrix)
    assert mean is not None
    return math.sqrt(
        math.fsum((rho - mean) ** 2 for _, _, rho in matrix) / len(matrix)
    )


class SystemicRiskReading(BaseModel):
    """One systemic-risk reading (§25).

    ``correlation_spike`` is True when the current average correlation
    exceeds the baseline by the declared margin. The reading records its
    own epistemics: measured correlation only, no causal claim.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    average_correlation: Optional[float]
    correlation_dispersion: Optional[float]
    correlation_spike: Optional[bool]
    baseline_average_correlation: Optional[float]
    spike_margin: Optional[float]
    concentration: Optional[float] = None
    label: str

    @property
    def reading_hash(self) -> str:
        return prefixed_hash(
            OUTPUT_PREFIX,
            {
                "kind": "systemic_risk_reading",
                "average_correlation": self.average_correlation,
                "correlation_dispersion": self.correlation_dispersion,
                "correlation_spike": self.correlation_spike,
                "baseline_average_correlation": self.baseline_average_correlation,
                "spike_margin": self.spike_margin,
                "concentration": self.concentration,
                "label": self.label,
            },
        )

    @property
    def epistemic_note(self) -> str:
        return (
            "Correlation is not prediction and not causation (§25); this "
            "reading measures co-movement only."
        )


#: Average-correlation bands for the systemic label (documented).
_CORR_LOW = 0.25
_CORR_ELEVATED = 0.50
_CORR_HIGH = 0.75


def systemic_risk_reading(
    returns_by_symbol: Mapping[str, Sequence[float]],
    *,
    baseline_returns_by_symbol: Optional[Mapping[str, Sequence[float]]] = None,
    spike_margin: float = 0.15,
    concentration: Optional[float] = None,
) -> SystemicRiskReading:
    """Compute one systemic-risk reading (§25).

    ``concentration`` is an optional caller-declared concentration
    measure (e.g. largest portfolio weight) — recorded, never invented.
    """
    matrix = correlation_matrix(returns_by_symbol)
    avg = average_correlation(matrix)
    disp = correlation_dispersion(matrix)
    baseline_avg: Optional[float] = None
    spike: Optional[bool] = None
    if baseline_returns_by_symbol is not None:
        baseline_matrix = correlation_matrix(baseline_returns_by_symbol)
        baseline_avg = average_correlation(baseline_matrix)
        if baseline_avg is not None and avg is not None:
            spike = (avg - baseline_avg) >= spike_margin
    if avg is None:
        label = "UNKNOWN"
    elif avg < _CORR_LOW:
        label = "LOW_RISK"
    elif avg < _CORR_ELEVATED:
        label = "ELEVATED_RISK"
    elif avg < _CORR_HIGH:
        label = "HIGH_RISK"
    else:
        label = "EXTREME_RISK"
    return SystemicRiskReading(
        average_correlation=avg,
        correlation_dispersion=disp,
        correlation_spike=spike,
        baseline_average_correlation=baseline_avg,
        spike_margin=spike_margin if baseline_avg is not None else None,
        concentration=concentration,
        label=label,
    )


__all__ = [
    "correlation_matrix",
    "average_correlation",
    "correlation_dispersion",
    "SystemicRiskReading",
    "systemic_risk_reading",
]
