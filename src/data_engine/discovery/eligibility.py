"""Execution eligibility — the mandate Phase 15 decision chain.

Required chain (fail-closed at every stage):

    DATA VALID → PIT VALID → STRATEGY VALID → RISK VALID →
    PORTFOLIO VALID → EXECUTION ELIGIBLE → EXECUTION AUTHORIZED

Any failure (or any unevaluated stage — ``None`` is failure) yields
``NO TRADE`` with machine-checkable reasons.

Scope boundary (absolute): this layer TERMINATES at
EXECUTION_ELIGIBLE. It does not implement, imply, or grant execution
AUTHORIZATION. Live authorization belongs exclusively to
``data_engine.paper.evaluation.LiveAuthorizationGate``, which DENIES
by default and requires a human-issued token that this codebase never
mints (blueprint 5.59). A strategy may generate a signal while
execution is denied — signal generation and execution eligibility
are separate concerns (mandate Phase 15).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from data_engine.pit.hashing import deterministic_hash

#: Eligibility-layer contract version.
ELIGIBILITY_CONTRACT_VERSION = "1.0.0"

#: Identity prefix for eligibility decisions.
ELIGIBILITY_HASH_PREFIX = "elig20."


class EligibilityStage(str, Enum):
    """The mandate's fixed decision-chain stages, in order."""

    DATA_VALID = "data_valid"
    PIT_VALID = "pit_valid"
    STRATEGY_VALID = "strategy_valid"
    RISK_VALID = "risk_valid"
    PORTFOLIO_VALID = "portfolio_valid"
    EXECUTION_ELIGIBLE = "execution_eligible"
    EXECUTION_AUTHORIZED = "execution_authorized"


#: Stages whose evidence must be supplied (None = fail-closed).
_REQUIRED_STAGES: tuple[EligibilityStage, ...] = (
    EligibilityStage.DATA_VALID,
    EligibilityStage.PIT_VALID,
    EligibilityStage.STRATEGY_VALID,
    EligibilityStage.RISK_VALID,
    EligibilityStage.PORTFOLIO_VALID,
)


class EligibilityStageResult(BaseModel):
    """One stage's evaluation outcome."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: EligibilityStage
    passed: bool
    detail: str = ""


class EligibilityDecision(BaseModel):
    """The composed chain outcome — NO TRADE is the default verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: str = Field(pattern="^(EXECUTION_ELIGIBLE|NO_TRADE)$")
    stages: tuple[EligibilityStageResult, ...] = ()
    reasons: tuple[str, ...] = ()

    @property
    def decision_hash(self) -> str:
        payload = {
            "contract_version": ELIGIBILITY_CONTRACT_VERSION,
            "decision": self.decision,
            "stages": [
                {"stage": s.stage.value, "passed": s.passed,
                 "detail": s.detail}
                for s in self.stages
            ],
            "reasons": list(self.reasons),
        }
        return ELIGIBILITY_HASH_PREFIX + deterministic_hash(payload)


class ExecutionEligibility:
    """Composes stage evidence into the fail-closed decision chain.

    Stage evidence is supplied by the caller from the authoritative
    components (data-quality gate, PIT validator, candidate validator,
    risk engine, portfolio constructor). This class NEVER invents a
    passing stage: absent evidence is a failure.
    """

    #: Live authorization is a SEPARATE governance event (blueprint 5.59).
    LIVE_AUTHORIZATION_STATUS = "NOT_AUTHORIZED"

    def evaluate(
        self,
        *,
        data_valid: Optional[bool] = None,
        data_detail: str = "",
        pit_valid: Optional[bool] = None,
        pit_detail: str = "",
        strategy_valid: Optional[bool] = None,
        strategy_detail: str = "",
        signal_is_no_trade: bool = True,
        signal_detail: str = "",
        risk_valid: Optional[bool] = None,
        risk_detail: str = "",
        portfolio_valid: Optional[bool] = None,
        portfolio_detail: str = "",
    ) -> EligibilityDecision:
        """Evaluate the chain. Any failure or missing stage: NO TRADE.

        ``signal_is_no_trade`` (default True) encodes the mandate rule
        that a NO-TRADE signal denies execution even when the strategy
        itself is valid — signal generation and eligibility remain
        separate, and no signal means nothing to execute.
        """
        provided: dict[EligibilityStage, tuple[Optional[bool], str]] = {
            EligibilityStage.DATA_VALID: (data_valid, data_detail),
            EligibilityStage.PIT_VALID: (pit_valid, pit_detail),
            EligibilityStage.STRATEGY_VALID: (strategy_valid, strategy_detail),
            EligibilityStage.RISK_VALID: (risk_valid, risk_detail),
            EligibilityStage.PORTFOLIO_VALID: (portfolio_valid, portfolio_detail),
        }

        results: list[EligibilityStageResult] = []
        reasons: list[str] = []
        all_passed = True

        for stage in _REQUIRED_STAGES:
            value, detail = provided[stage]
            if value is None:
                results.append(
                    EligibilityStageResult(
                        stage=stage,
                        passed=False,
                        detail=detail or "stage not evaluated (fail-closed)",
                    )
                )
                reasons.append(f"{stage.value}: not evaluated")
                all_passed = False
                continue
            passed = bool(value)
            results.append(
                EligibilityStageResult(
                    stage=stage, passed=passed, detail=detail
                )
            )
            if not passed:
                reasons.append(f"{stage.value}: {detail or 'failed'}")
                all_passed = False

        # Signal gate: NO TRADE signals deny execution even when the
        # strategy itself is valid (signal generation and eligibility
        # are separate; no signal means nothing to execute).
        if signal_is_no_trade:
            reasons.append(
                f"signal: {signal_detail or 'NO TRADE'}"
            )
            all_passed = False

        eligible = all_passed
        results.append(
            EligibilityStageResult(
                stage=EligibilityStage.EXECUTION_ELIGIBLE,
                passed=eligible,
                detail=(
                    "all upstream stages passed"
                    if eligible
                    else "upstream failure denies eligibility"
                ),
            )
        )
        if not eligible:
            reasons.append("execution: NO TRADE")

        # Authorization is ALWAYS recorded as not granted here: the
        # live gate is a separate human governance event (5.59) and is
        # deny-by-default. Paper execution flows through the paper
        # gateway, not through this record.
        results.append(
            EligibilityStageResult(
                stage=EligibilityStage.EXECUTION_AUTHORIZED,
                passed=False,
                detail=(
                    "live authorization is a separate human governance "
                    "event (LiveAuthorizationGate denies by default; "
                    "blueprint 5.59) — this layer never authorizes"
                ),
            )
        )

        decision = "EXECUTION_ELIGIBLE" if eligible else "NO_TRADE"
        return EligibilityDecision(
            decision=decision,
            stages=tuple(results),
            reasons=tuple(reasons),
        )

    def default_decision(self) -> EligibilityDecision:
        """The decision with NO evidence supplied: pure NO TRADE."""
        return self.evaluate()
