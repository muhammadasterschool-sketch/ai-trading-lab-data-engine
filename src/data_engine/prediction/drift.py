"""Model drift monitoring (§20, §37) — PSI-based, fail-closed.

Monitors feature/prediction/performance distribution shift via the
population stability index. Drift states carry MANDATED actions (§37):

    STABLE   continue
    WATCH    increase monitoring
    DEGRADED restrict usage
    DRIFTED  block or require review
    INVALID  retire the model

A drifted model never silently continues as if healthy; a degenerate
monitoring input is INVALID — the monitor itself fails closed.
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import DriftState, PredictionContractError
from data_engine.prediction.identity import DRIFT_PREFIX, prefixed_hash
from data_engine.prediction.uncertainty import _quantile


def population_stability_index(
    reference: Sequence[float],
    current: Sequence[float],
    *,
    n_bins: int = 10,
) -> float:
    """Population stability index between two samples (§20).

    Bin edges come from REFERENCE quantiles (the training distribution);
    both samples are counted against those edges. Deterministic: fixed
    quantile interpolation, ``math.fsum`` accumulation, epsilon-floored
    proportions.
    """
    if len(reference) < 2 or len(current) < 1:
        raise PredictionContractError(
            "PSI needs >= 2 reference values and >= 1 current value"
        )
    if n_bins < 2:
        raise PredictionContractError("n_bins must be >= 2")
    ref_sorted = sorted(float(v) for v in reference)
    edges: list[float] = []
    for i in range(1, n_bins):
        q = i / n_bins
        edge = _quantile(ref_sorted, q)
        if not edges or edge > edges[-1]:
            edges.append(edge)
    if not edges:
        # Degenerate reference (all values identical): one implicit bin.
        edges = [ref_sorted[0]]

    def _counts(values: Sequence[float]) -> list[float]:
        counts = [0.0] * (len(edges) + 1)
        for v in values:
            placed = False
            for idx, edge in enumerate(edges):
                if float(v) <= edge:
                    counts[idx] += 1.0
                    placed = True
                    break
            if not placed:
                counts[len(edges)] += 1.0
        return counts

    ref_counts = _counts(reference)
    cur_counts = _counts(current)
    ref_total = math.fsum(ref_counts)
    cur_total = math.fsum(cur_counts)
    eps = 1e-6
    psi = 0.0
    for r, c in zip(ref_counts, cur_counts):
        rp = max(r / ref_total, eps) if ref_total > 0 else eps
        cp = max(c / cur_total, eps) if cur_total > 0 else eps
        psi += (cp - rp) * math.log(cp / rp)
    return psi


#: PSI state boundaries (documented, deterministic).
PSI_STABLE = 0.10
PSI_WATCH = 0.25
PSI_DEGRADED = 0.50


def classify_drift(psi: Optional[float]) -> DriftState:
    """Map a PSI value to a drift state (§20)."""
    if psi is None or psi != psi or psi < 0:
        return DriftState.INVALID
    if psi < PSI_STABLE:
        return DriftState.STABLE
    if psi < PSI_WATCH:
        return DriftState.WATCH
    if psi < PSI_DEGRADED:
        return DriftState.DEGRADED
    return DriftState.DRIFTED


class DriftReport(BaseModel):
    """One monitored quantity's drift verdict (§20, §37)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str
    psi: Optional[float]
    state: DriftState
    reference_n: int
    current_n: int

    @property
    def action(self) -> str:
        return DRIFT_ACTIONS[self.state]

    @property
    def drift_hash(self) -> str:
        return prefixed_hash(
            DRIFT_PREFIX,
            {
                "kind": "drift_report",
                "metric": self.metric,
                "psi": self.psi,
                "state": self.state.value,
                "reference_n": self.reference_n,
                "current_n": self.current_n,
            },
        )


#: Mandated drift failure actions (§37) — exhaustive over DriftState.
DRIFT_ACTIONS = {
    DriftState.STABLE: "continue",
    DriftState.WATCH: "increase monitoring",
    DriftState.DEGRADED: "restrict usage",
    DriftState.DRIFTED: "block or require review",
    DriftState.INVALID: "retire model",
}


def drift_action(state: DriftState) -> str:
    """The mandated action for a drift state (§37)."""
    return DRIFT_ACTIONS[state]


def drift_report(
    reference: Sequence[float],
    current: Sequence[float],
    *,
    metric: str,
    n_bins: int = 10,
) -> DriftReport:
    """PSI drift report for one monitored quantity.

    Degenerate inputs (empty / single-valued reference, NaN) yield an
    INVALID-state report — the monitor never guesses.
    """
    try:
        psi: Optional[float] = population_stability_index(
            reference, current, n_bins=n_bins
        )
    except PredictionContractError:
        psi = None
    if psi is None:
        state = DriftState.INVALID
    else:
        state = classify_drift(psi)
    return DriftReport(
        metric=metric,
        psi=psi,
        state=state,
        reference_n=len(reference),
        current_n=len(current),
    )


def data_source_drift(
    reference_sources: Sequence[str],
    current_sources: Sequence[str],
) -> bool:
    """Data-source drift: True when the source set changed (§20)."""
    return set(reference_sources) != set(current_sources)


__all__ = [
    "population_stability_index",
    "classify_drift",
    "DriftReport",
    "drift_report",
    "drift_action",
    "DRIFT_ACTIONS",
    "data_source_drift",
    "PSI_STABLE",
    "PSI_WATCH",
    "PSI_DEGRADED",
]
