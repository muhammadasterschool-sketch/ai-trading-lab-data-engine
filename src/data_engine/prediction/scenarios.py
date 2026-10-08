"""Scenario engine (§24) — scenarios are NOT forecasts.

Each scenario records inputs, assumptions, affected assets, estimated
impact, uncertainty, and limitations. Running a scenario is a PURE
function: it copies its inputs, computes estimated stressed exposures,
and returns them with ``is_forecast=False``. Scenario runs are isolated
(T-PRED-025): they cannot mutate portfolio state, risk limits, or any
other subsystem — the engine holds no writable references.
"""

from typing import Mapping, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import OUTPUT_PREFIX, prefixed_hash

#: Closed vocabulary of scenario kinds (§24).
SCENARIO_KINDS: Tuple[str, ...] = (
    "VOLATILITY_SHOCK", "GAP_DOWN", "LIQUIDITY_SHOCK",
    "CORRELATION_SPIKE", "SECTOR_CRASH", "INDEX_CRASH", "FX_SHOCK",
    "COMMODITY_SHOCK", "RATE_SHOCK", "MULTI_ASSET_CONTAGION",
)

#: Standing disclaimer: scenarios are never forecasts (§24).
SCENARIO_DISCLAIMER = (
    "Scenarios are structured what-if analyses, NOT forecasts; "
    "estimated impacts carry no probability claim (mandate §24)."
)


class ScenarioDefinition(BaseModel):
    """One declared scenario (§24 required fields)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    kind: str
    assumptions: Tuple[str, ...]
    affected_assets: Tuple[str, ...]
    estimated_impact: Tuple[Tuple[str, float], ...]
    uncertainty: str
    limitations: Tuple[str, ...]
    inputs: Tuple[Tuple[str, float], ...] = ()

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, v: str) -> str:
        if v not in SCENARIO_KINDS:
            raise ValueError(
                f"unknown scenario kind {v!r}; supported: {SCENARIO_KINDS}"
            )
        return v

    @field_validator("scenario_id", "uncertainty")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("scenario text fields must be non-empty")
        return v

    @field_validator("assumptions", "limitations", "affected_assets")
    @classmethod
    def _validate_non_empty(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if not v:
            raise ValueError(
                "scenarios must declare assumptions/limitations/affected "
                "assets — hidden assumptions are forbidden (§24)"
            )
        return v

    @property
    def definition_hash(self) -> str:
        return prefixed_hash(
            OUTPUT_PREFIX,
            {
                "kind": "scenario_definition",
                "scenario_id": self.scenario_id,
                "scenario_kind": self.kind,
                "assumptions": list(self.assumptions),
                "affected_assets": list(self.affected_assets),
                "estimated_impact": [list(p) for p in self.estimated_impact],
                "inputs": [list(p) for p in self.inputs],
            },
        )


class ScenarioResult(BaseModel):
    """Result of one scenario run — explicitly not a forecast (§24)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    kind: str
    estimated_exposures: Tuple[Tuple[str, float], ...]
    total_estimated_exposure: float
    is_forecast: bool = False
    disclaimer: str = (
        "Scenarios are structured what-if analyses, NOT forecasts; "
        "estimated impacts carry no probability claim (mandate §24)."
    )

    @field_validator("is_forecast")
    @classmethod
    def _validate_not_forecast(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "a scenario result can never be a forecast (§24)"
            )
        return v


class ScenarioEngine:
    """Pure scenario evaluation over immutable copies (§24, T-PRED-025)."""

    def run(
        self,
        definition: ScenarioDefinition,
        exposures: Mapping[str, float],
    ) -> ScenarioResult:
        """Apply the scenario's impact factors to a copied exposure map.

        Unaffected assets keep their exposure; affected assets are scaled
        by (1 + impact). The input mapping is NEVER mutated.
        """
        if not exposures:
            raise PredictionContractError(
                "exposures must be non-empty — a scenario over an empty "
                "portfolio is meaningless"
            )
        impact = dict(definition.estimated_impact)
        estimated: list[tuple[str, float]] = []
        total = 0.0
        for asset in sorted(exposures):
            base = float(exposures[asset])
            factor = 1.0 + impact.get(asset, 0.0)
            stressed = base * factor
            estimated.append((asset, round(stressed, 12)))
            total += stressed
        return ScenarioResult(
            scenario_id=definition.scenario_id,
            kind=definition.kind,
            estimated_exposures=tuple(estimated),
            total_estimated_exposure=round(total, 12),
        )


__all__ = [
    "SCENARIO_KINDS",
    "ScenarioDefinition",
    "ScenarioResult",
    "ScenarioEngine",
    "SCENARIO_DISCLAIMER",
]
