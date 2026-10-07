"""Phase 7 — Robustness testing (blueprint 5.27).

Strategy stability across parameter variations and market regimes:

- ``sweep``: evaluate a deterministic runner over a parameter grid
  (every combination, bounded by a hard combination cap — runaway
  sweeps are a defect, not a feature).
- ``plateau_analysis``: for each parameter axis, measure result
  dispersion around the median — a strategy whose score collapses
  when a parameter moves one notch is fragile (no plateau).
- ``regime_analysis``: evaluate per-segment (regime) runners; a
  strategy profitable in only one regime carries regime risk that
  MUST surface in the report.

Report identity: ``rob7.`` prefix. All analysis is pure functions of
the sweep results — no randomness, no environment dependence.
"""

from itertools import product
from typing import Any, Callable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from data_engine.pit.hashing import deterministic_hash

#: Identity prefix for robustness report hashes.
ROBUSTNESS_PREFIX = "rob7."

#: Phase 7 contract version (shared).
PHASE_7_CONTRACT_VERSION = "1.0.0"

#: Hard cap on grid combinations (runaway-sweep guard).
MAX_GRID_COMBINATIONS = 10_000


class RobustnessError(ValueError):
    """Raised on robustness-testing contract violations."""


class RobustnessReport(BaseModel):
    """Aggregate robustness result over a sweep or regime analysis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluations: tuple[dict, ...]
    plateau: dict
    stable: bool

    @property
    def report_hash(self) -> str:
        return ROBUSTNESS_PREFIX + deterministic_hash(
            {
                "contract_version": PHASE_7_CONTRACT_VERSION,
                "evaluations": list(self.evaluations),
                "plateau": self.plateau,
                "stable": self.stable,
            }
        )


def sweep(
    parameter_grid: Mapping[str, Sequence[Any]],
    evaluate: Callable[[Mapping[str, Any]], float],
    score_key: str = "score",
) -> tuple[dict, ...]:
    """Evaluate ``evaluate`` over every grid combination.

    Returns tuples of dicts: {param..., score_key: float}. The grid
    size is capped; exceeding the cap raises (a sweep the operator
    cannot review is a defect).
    """
    if not parameter_grid:
        raise RobustnessError("parameter grid must not be empty")
    for name, values in parameter_grid.items():
        if not values:
            raise RobustnessError(
                f"parameter {name!r} has an empty value list"
            )
    total = 1
    for values in parameter_grid.values():
        total *= len(values)
    if total > MAX_GRID_COMBINATIONS:
        raise RobustnessError(
            f"grid has {total} combinations (cap {MAX_GRID_COMBINATIONS}) — "
            "reduce the grid"
        )
    names = sorted(parameter_grid.keys())
    results = []
    for combo in product(*(parameter_grid[n] for n in names)):
        params = dict(zip(names, combo))
        score = evaluate(params)
        if not isinstance(score, (int, float)):
            raise RobustnessError(
                "evaluate must return a numeric score "
                f"(got {type(score).__name__})"
            )
        entry = dict(params)
        entry[score_key] = score
        results.append(entry)
    return tuple(results)


def plateau_analysis(
    evaluations: Sequence[Mapping[str, Any]],
    score_key: str = "score",
    tolerance: float = 0.25,
) -> dict:
    """Plateau detection per parameter axis.

    For each parameter axis: split evaluations into slices along that
    axis (other parameters held at each combination), and measure the
    maximum relative deviation of the slice's scores around the global
    median. An axis whose deviation exceeds ``tolerance`` is fragile.
    """
    if not evaluations:
        raise RobustnessError("no evaluations to analyze")
    param_names = sorted(
        {k for e in evaluations for k in e if k != score_key}
    )

    axis_report: dict[str, dict] = {}
    for axis in param_names:
        other_axes = [p for p in param_names if p != axis]
        groups: dict[tuple, list[float]] = {}
        for e in evaluations:
            key = tuple(e[o] for o in other_axes)
            groups.setdefault(key, []).append(float(e[score_key]))
        values = sorted({e[axis] for e in evaluations})
        if len(values) < 2:
            axis_report[axis] = {
                "levels": len(values),
                "max_slice_spread": 0.0,
                "fragile": False,
                "note": "single level — no variation to test",
            }
            continue
        worst_spread = 0.0
        for scores in groups.values():
            if len(scores) < 2:
                continue
            spread = max(scores) - min(scores)
            center = sorted(scores)[len(scores) // 2]
            denom = abs(center) if center != 0 else 1.0
            worst_spread = max(worst_spread, spread / denom)
        axis_report[axis] = {
            "levels": len(values),
            "max_slice_spread": round(worst_spread, 6),
            "fragile": worst_spread > tolerance,
        }
    scores = [float(e[score_key]) for e in evaluations]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    median = (
        scores_sorted[n // 2]
        if n % 2 == 1
        else 0.5 * (scores_sorted[n // 2 - 1] + scores_sorted[n // 2])
    )
    return {
        "median_score": median,
        "tolerance": tolerance,
        "axes": axis_report,
    }


def robustness_report(
    evaluations: Sequence[Mapping[str, Any]],
    score_key: str = "score",
    tolerance: float = 0.25,
) -> RobustnessReport:
    """Build the aggregate robustness report from sweep evaluations."""
    plateau = plateau_analysis(evaluations, score_key, tolerance)
    axes = plateau.get("axes", {})
    stable = all(
        (axis.get("fragile", True) is False) for axis in axes.values()
    ) if axes else False
    return RobustnessReport(
        evaluations=tuple(dict(e) for e in evaluations),
        plateau=plateau,
        stable=stable,
    )


def regime_analysis(
    regimes: Mapping[str, Sequence[int]],
    evaluate_regime: Callable[[str, Sequence[int]], float],
    tolerance: float = 0.25,
) -> RobustnessReport:
    """Evaluate per-regime performance; sign consistency required.

    ``regimes`` maps regime name -> bar indices. A strategy whose
    per-regime scores disagree in SIGN across regimes is regime-
    fragile: the report is unstable (stable=False).
    """
    if not regimes:
        raise RobustnessError("regimes must not be empty")
    evaluations = []
    for name in sorted(regimes.keys()):
        indices = list(regimes[name])
        score = evaluate_regime(name, indices)
        if not isinstance(score, (int, float)):
            raise RobustnessError("evaluate_regime must return a number")
        evaluations.append({"regime": name, "bars": len(indices), "score": score})
    scores = [e["score"] for e in evaluations]
    has_positive = any(s > 0 for s in scores)
    has_negative = any(s < 0 for s in scores)
    sign_consistent = not (has_positive and has_negative)
    magnitude = max(abs(s) for s in scores) or 1.0
    min_magnitude = min(abs(s) for s in scores)
    balanced = (magnitude - min_magnitude) / magnitude <= tolerance * 4
    plateau = {
        "sign_consistent": sign_consistent,
        "scores": {e["regime"]: e["score"] for e in evaluations},
        "relative_spread": round((magnitude - min_magnitude) / magnitude, 6),
    }
    return RobustnessReport(
        evaluations=tuple(evaluations),
        plateau=plateau,
        stable=bool(sign_consistent and balanced),
    )


__all__ = [
    "RobustnessError",
    "RobustnessReport",
    "sweep",
    "plateau_analysis",
    "robustness_report",
    "regime_analysis",
    "ROBUSTNESS_PREFIX",
    "MAX_GRID_COMBINATIONS",
]
