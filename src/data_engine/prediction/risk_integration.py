"""Prediction -> Risk interface (§23, §29).

Crash-risk output may INFORM position sizing, risk budget, exposure
limits, hedging research, NO-TRADE decisions, and scenario analysis. It
may NEVER bypass hard risk limits, the kill switch, governance, human
approval, or paper-trading requirements (§29).

This module integrates with the REAL Phase 8 risk engine
(``data_engine.risk.engine``): hard limits come from the actual
``RiskLimits`` contract, and the authority over the final decision is
explicitly the RISK ENGINE — prediction output is advisory input only
(§28: prediction never executes trades).
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.crash import CrashRiskAssessment
from data_engine.prediction.identity import OUTPUT_PREFIX, prefixed_hash
from data_engine.risk.engine import RiskLimits

#: Risk-level -> sizing multiplier (§29 advisory scaling).
#: Control states (refusals) contribute NO sizing input at all.
LEVEL_SIZING = {
    "LOW_RISK": Decimal("1.00"),
    "NO_SIGNAL": Decimal("0.50"),
    "ELEVATED_RISK": Decimal("0.75"),
    "HIGH_RISK": Decimal("0.50"),
    "EXTREME_RISK": Decimal("0.25"),
}


class PredictionRiskDecision(BaseModel):
    """Advisory risk decision derived from one assessment (§29).

    ``authority`` is always the RISK ENGINE; ``source`` is always the
    prediction layer. A suppressed decision carries zero sizing input.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str  # ADVISE_SIZE | ADVISORY_ONLY | NO_TRADE
    sizing_multiplier: Decimal
    proposed_max_position_units: Decimal
    proposed_risk_budget_fraction: Decimal
    suppressed: bool
    suppressed_reason: Optional[str]
    authority: str = "RISK_ENGINE"
    source: str = "PREDICTION"
    notes: tuple = ()

    @property
    def decision_hash(self) -> str:
        return prefixed_hash(
            OUTPUT_PREFIX,
            {
                "kind": "prediction_risk_decision",
                "action": self.action,
                "sizing_multiplier": str(self.sizing_multiplier),
                "proposed_max_position_units": str(
                    self.proposed_max_position_units
                ),
                "proposed_risk_budget_fraction": str(
                    self.proposed_risk_budget_fraction
                ),
                "suppressed": self.suppressed,
                "suppressed_reason": self.suppressed_reason,
            },
        )


def prediction_risk_decision(
    assessment: CrashRiskAssessment,
    limits: RiskLimits,
    *,
    kill_switch_active: bool = False,
) -> PredictionRiskDecision:
    """Translate one crash-risk assessment into advisory risk input.

    Guarantees (T-PRED-026/T-PRED-027):
    - proposed values NEVER exceed the hard limits (clamped by design:
      multiplier <= 1 applied to the limit itself)
    - an active kill switch suppresses ALL prediction-derived input
    - refused/uncertain assessments produce NO sizing input (NO_TRADE)
    """
    if kill_switch_active:
        return PredictionRiskDecision(
            action="NO_TRADE",
            sizing_multiplier=Decimal("0"),
            proposed_max_position_units=Decimal("0"),
            proposed_risk_budget_fraction=Decimal("0"),
            suppressed=True,
            suppressed_reason=(
                "kill switch active — all prediction-derived risk input "
                "suppressed (risk engine remains authoritative)"
            ),
            notes=assessment.notes,
        )

    if assessment.refused or assessment.status == "MODEL_UNCERTAIN":
        return PredictionRiskDecision(
            action="NO_TRADE",
            sizing_multiplier=Decimal("0"),
            proposed_max_position_units=Decimal("0"),
            proposed_risk_budget_fraction=Decimal("0"),
            suppressed=False,
            suppressed_reason=(
                f"prediction refused/uncertain (status={assessment.status}) "
                "— no sizing input from a refused prediction"
            ),
            notes=assessment.notes,
        )

    multiplier = LEVEL_SIZING.get(assessment.status)
    if multiplier is None:
        raise PredictionContractError(
            f"unmapped assessment status {assessment.status!r} — refusing "
            "to invent a sizing multiplier"
        )
    proposed_position = limits.max_position_units * multiplier
    proposed_budget = limits.max_portfolio_heat * multiplier
    notes: tuple = ()
    if assessment.restricted:
        notes = assessment.notes + (
            "prediction marked RESTRICTED (degraded drift) — risk engine "
            "should treat sizing input with heightened scrutiny",
        )
    return PredictionRiskDecision(
        action=(
            "ADVISE_SIZE"
            if multiplier < Decimal("1")
            else "ADVISORY_ONLY"
        ),
        sizing_multiplier=multiplier,
        proposed_max_position_units=proposed_position,
        proposed_risk_budget_fraction=proposed_budget,
        suppressed=False,
        suppressed_reason=None,
        notes=notes if notes else assessment.notes,
    )


__all__ = [
    "LEVEL_SIZING",
    "PredictionRiskDecision",
    "prediction_risk_decision",
]
