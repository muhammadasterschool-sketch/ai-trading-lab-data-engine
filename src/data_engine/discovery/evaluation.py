"""Candidate validation and signal evaluation (mandate Phase 11/15).

``CandidateValidator`` applies the candidate's own validation
requirements plus structural checks (spec parses, dependencies
declared, grid coherent). Validation FAILURE produces a REJECTED
candidate — a strategy is allowed to fail, with evidence.

``CandidateEvaluator`` evaluates a candidate's frozen declarative
conditions against a feature row. The DEFAULT outcome is
``NO_TRADE``: a signal exists only when every entry condition is
satisfied by present values. No condition injection, no code
execution — evaluation reuses the frozen Phase 3 ``EntryCondition``
comparator.
"""

from enum import Enum
from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from data_engine.discovery.models import (
    DISCOVERY_CONTRACT_VERSION,
    CandidateStatus,
    StrategyCandidate,
)
from data_engine.strategy.schemas import EntryCondition


class ValidationFailure(ValueError):
    """A candidate failed objective validation gates."""


class SignalAction(str, Enum):
    """Outcome of evaluating a candidate's conditions at a point."""

    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    NO_TRADE = "no_trade"


class SignalDecision(BaseModel):
    """One evaluated decision — NO TRADE is a first-class result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: SignalAction
    candidate_id: str
    conditions_met: tuple[str, ...] = ()
    conditions_missed: tuple[str, ...] = ()
    reason: str = ""


class CandidateValidator:
    """Objective validation gates applied to generated candidates."""

    validator_id = "candidate-validator-v1"

    def validate(
        self,
        candidate: StrategyCandidate,
        *,
        available_history_bars: int = 0,
        available_feature_outputs: Sequence[str] = (),
    ) -> StrategyCandidate:
        """Validate a candidate; return it VALIDATED or REJECTED.

        Does not raise on candidate defects — rejection is recorded on
        the candidate (strategies are allowed to fail). Raises only on
        caller contract violations (non-DRAFT lifecycle misuse).
        """
        if candidate.status is not CandidateStatus.DRAFT:
            raise ValidationFailure(
                "only DRAFT candidates enter validation "
                f"(got {candidate.status.value})"
            )
        reasons: list[str] = []

        # 1. The frozen spec must parse its own condition payloads.
        try:
            entries = candidate.spec.entry_conditions
        except ValueError as exc:
            entries = []
            reasons.append(f"entry conditions unparseable: {exc}")
        if not entries:
            reasons.append("spec declares no entry conditions")

        # 2. Operators must be within the frozen comparator set.
        for cond in entries:
            if cond.operator not in {">", "<", ">=", "<=", "=="}:
                reasons.append(
                    f"unsupported operator {cond.operator!r}"
                )

        # 3. Feature dependencies must be available where declared.
        declared = candidate.data_dependencies.feature_outputs
        if declared and available_feature_outputs:
            missing = [
                name
                for name in declared
                if name not in set(available_feature_outputs)
            ]
            if missing:
                reasons.append(
                    f"feature dependencies unavailable: {sorted(missing)}"
                )

        # 4. History must satisfy the candidate's own minimum.
        if available_history_bars < candidate.validation_requirements.min_history_bars:
            reasons.append(
                "insufficient history: "
                f"{available_history_bars} < "
                f"{candidate.validation_requirements.min_history_bars}"
            )

        # 5. Risk assumptions must be coherent.
        if (
            candidate.risk_assumptions.stop_loss_pct is not None
            and candidate.risk_assumptions.take_profit_pct is not None
            and candidate.risk_assumptions.take_profit_pct
            <= candidate.risk_assumptions.stop_loss_pct
        ):
            reasons.append("take-profit must exceed stop-loss when both set")

        if reasons:
            return candidate.with_status(
                CandidateStatus.REJECTED, "; ".join(reasons)
            )
        return candidate.with_status(CandidateStatus.VALIDATED)


class CandidateEvaluator:
    """Evaluates validated candidates' conditions against feature rows."""

    evaluator_id = "candidate-evaluator-v1"

    def evaluate(
        self,
        candidate: StrategyCandidate,
        features: Mapping[str, Optional[float]],
        previous_features: Optional[Mapping[str, Optional[float]]] = None,
    ) -> SignalDecision:
        """Evaluate entry conditions against one feature row.

        The default outcome is NO TRADE. ENTRY requires every entry
        condition to be satisfied with present (non-None) values.
        ``features`` maps indicator/feature names to current values;
        ``previous_features`` (optional) supplies the prior row for
        conditions declared with ``requires_previous``.
        """
        if candidate.status is not CandidateStatus.VALIDATED:
            raise ValidationFailure(
                "only VALIDATED candidates may be evaluated "
                f"(got {candidate.status.value})"
            )
        entries: list[EntryCondition] = []
        try:
            entries = list(candidate.spec.entry_conditions)
        except ValueError as exc:  # defensive: validator gates this earlier
            return SignalDecision(
                action=SignalAction.NO_TRADE,
                candidate_id=candidate.candidate_id,
                reason=f"conditions unparseable: {exc}",
            )
        if not entries:
            return SignalDecision(
                action=SignalAction.NO_TRADE,
                candidate_id=candidate.candidate_id,
                reason="no entry conditions declared",
            )

        met: list[str] = []
        missed: list[str] = []
        all_met = True
        for cond in entries:
            current = features.get(cond.indicator)
            previous = (
                previous_features.get(cond.indicator)
                if previous_features is not None
                else None
            )
            if current is None and not cond.requires_previous:
                all_met = False
                missed.append(f"{cond.indicator}:{cond.operator}:missing")
                continue
            try:
                satisfied = cond.evaluate(current, previous)
            except ValueError as exc:
                all_met = False
                missed.append(f"{cond.indicator}:{cond.operator}:{exc}")
                continue
            if satisfied:
                met.append(cond.canonical_serialize())
            else:
                all_met = False
                missed.append(
                    f"{cond.indicator}:{cond.operator}:{cond.threshold}"
                )

        if all_met and met:
            action = (
                SignalAction.ENTRY_SHORT
                if candidate.spec.allow_short
                else SignalAction.ENTRY_LONG
            )
            return SignalDecision(
                action=action,
                candidate_id=candidate.candidate_id,
                conditions_met=tuple(met),
            )
        return SignalDecision(
            action=SignalAction.NO_TRADE,
            candidate_id=candidate.candidate_id,
            conditions_met=tuple(met),
            conditions_missed=tuple(missed),
            reason="entry conditions not satisfied",
        )


def evaluate_no_trade_default(
    candidate_id: str,
    reason: str = "no valid opportunity",
) -> SignalDecision:
    """Explicit NO TRADE construction used at decision boundaries."""
    return SignalDecision(
        action=SignalAction.NO_TRADE,
        candidate_id=candidate_id,
        reason=reason,
    )
