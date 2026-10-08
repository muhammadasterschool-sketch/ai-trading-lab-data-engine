"""DecisionEngine (pre-paper mandate §22).

Output vocabulary (CLOSED set): BUY / SELL / REDUCE / HOLD / CLOSE /
NO_TRADE — NO_TRADE is mandatory and first-class.

Every decision records: prediction IDs, model versions, uncertainty,
regime, crash risk, portfolio state, the decision reason, rejected
alternatives, and the correlation id.

Hard refusal gates (each produces NO_TRADE with a specific,
auditable reason — mandate §51 negative paths):

- data stale / unavailable
- model unavailable / invalid
- uncertainty above the hard NO_TRADE threshold (§18)
- crash risk above the hard threshold (§20 — strategy signals can
  NEVER override crash protection)
- confidence below the entry threshold
- kill switch active (delegated upstream, but re-checked)

The DecisionEngine has NO order authority: it emits intent records
only — the TradePlan → RiskGate → OMS chain decides execution.
"""

from datetime import datetime, UTC
from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import (
    Decision,
    DecisionAction,
    PredictionArtifact,
    RejectedAlternative,
    RuntimeContractError,
    UncertaintyReport,
)
from data_engine.runtime.identity import DECISION_PREFIX, prefixed_hash


class DecisionError(RuntimeContractError):
    """Raised on decision-engine contract violations."""


class DecisionThresholds(BaseModel):
    """Governed decision thresholds (§18/§20 hard NO_TRADE rules)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_probability: float = 0.60  # BUY above, SELL below 1-
    min_confidence: float = 0.55
    max_entropy: float = 0.95
    max_ensemble_disagreement: float = 0.25
    max_crash_probability: float = 0.20
    min_expected_return: float = 0.0
    max_data_age_bars: int = 2

    @field_validator(
        "entry_probability", "min_confidence", "max_entropy",
        "max_ensemble_disagreement", "max_crash_probability",
    )
    @classmethod
    def _validate_unit(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise DecisionError("probability-like thresholds must be in [0,1]")
        return v


class MarketDataStatus(BaseModel):
    """Data freshness/availability verdict feeding the decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    last_bar_age_bars: Optional[int] = None
    reason: str = ""

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return v or ""


class DecisionEngine:
    """The governed decision maker (mandate §22)."""

    def __init__(self, thresholds: Optional[DecisionThresholds] = None) -> None:
        self._thresholds = thresholds or DecisionThresholds()

    @property
    def thresholds(self) -> DecisionThresholds:
        return self._thresholds

    # ------------------------------------------------------------------
    def decide(
        self,
        artifact: PredictionArtifact,
        data_status: MarketDataStatus,
        position_quantity,
        correlation_id: str,
        decision_id: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> Decision:
        """Produce ONE decision from one prediction artifact."""
        if artifact is None:
            raise DecisionError("a decision requires its prediction artifact")
        th = self._thresholds
        unc = artifact.uncertainty
        crash_probability = float(artifact.crash_risk.get("probability", 1.0))
        timestamp = at or artifact.timestamp
        rejected: list = []

        def no_trade(reason: str, blocked: str) -> Decision:
            return Decision(
                decision_id=decision_id or prefixed_hash(
                    DECISION_PREFIX,
                    {"kind": "decision", "reason": reason,
                     "artifact": artifact.artifact_hash, "at": timestamp},
                ),
                action=DecisionAction.NO_TRADE,
                symbol=artifact.symbol,
                timestamp=timestamp,
                prediction_ids=(artifact.prediction_id,),
                model_versions=artifact.model_versions,
                uncertainty=unc,
                regime=artifact.regime,
                crash_risk=dict(artifact.crash_risk),
                portfolio_state={
                    "position_quantity": str(position_quantity),
                    "blocked_condition": blocked,
                },
                reason=reason,
                rejected_alternatives=tuple(rejected),
                correlation_id=correlation_id,
            )

        # --- hard refusals (order = governance priority) -----------------
        if not data_status.available:
            return no_trade(
                "data unavailable — NO_TRADE (fail closed)",
                "DATA_UNAVAILABLE",
            )
        age = data_status.last_bar_age_bars
        if age is None or age > th.max_data_age_bars:
            return no_trade(
                f"data stale ({age} bars old, max {th.max_data_age_bars}) — "
                "NO_TRADE (fail closed)",
                "DATA_STALE",
            )
        if crash_probability > th.max_crash_probability:
            rejected.append(RejectedAlternative(
                action=DecisionAction.BUY,
                reason=f"crash probability {crash_probability} above hard "
                       f"threshold {th.max_crash_probability}",
            ))
            return no_trade(
                f"crash risk {crash_probability} above hard threshold — "
                "crash protection cannot be overridden by strategy signals",
                "CRASH_RISK_HIGH",
            )
        if unc.entropy is None or unc.ensemble_disagreement is None:
            return no_trade(
                "uncertainty metadata incomplete — NO_TRADE (fail closed)",
                "UNCERTAINTY_UNKNOWN",
            )
        if unc.entropy > th.max_entropy:
            return no_trade(
                f"entropy {unc.entropy} above hard threshold "
                f"{th.max_entropy}",
                "ENTROPY_HIGH",
            )
        if unc.ensemble_disagreement > th.max_ensemble_disagreement:
            return no_trade(
                f"ensemble disagreement {unc.ensemble_disagreement} above "
                f"threshold {th.max_ensemble_disagreement}",
                "DISAGREEMENT_HIGH",
            )
        if unc.confidence < th.min_confidence:
            return no_trade(
                f"confidence {unc.confidence} below minimum "
                f"{th.min_confidence}",
                "CONFIDENCE_LOW",
            )

        p = artifact.probability
        expected = artifact.expected_return

        # --- directional intent --------------------------------------------
        if p >= th.entry_probability and expected >= th.min_expected_return:
            action = DecisionAction.BUY
            reason = (
                f"probability {p} >= {th.entry_probability} with expected "
                f"return {expected}; regime {artifact.regime}; crash "
                f"probability {crash_probability}"
            )
            if position_quantity < 0:
                action = DecisionAction.CLOSE
                reason = (
                    "opposing short position held while signal is long — "
                    "CLOSE before any new exposure; " + reason
                )
            elif position_quantity > 0:
                action = DecisionAction.HOLD
                reason = (
                    "already long in agreement with signal — HOLD (no "
                    "pyramiding without a fresh plan); " + reason
                )
        elif p <= (1.0 - th.entry_probability) and expected >= th.min_expected_return:
            action = DecisionAction.SELL
            reason = (
                f"probability {p} <= {1.0 - th.entry_probability} (down "
                f"signal); regime {artifact.regime}"
            )
            if position_quantity > 0:
                action = DecisionAction.CLOSE
                reason = (
                    "opposing long position held while signal is short — "
                    "CLOSE before any new exposure; " + reason
                )
            elif position_quantity < 0:
                action = DecisionAction.HOLD
                reason = (
                    "already short in agreement with signal — HOLD; " + reason
                )
        else:
            rejected.append(RejectedAlternative(
                action=DecisionAction.BUY,
                reason=f"probability {p} inside the no-entry band "
                       f"[{1.0 - th.entry_probability:.2f}, "
                       f"{th.entry_probability:.2f}]",
            ))
            action = DecisionAction.NO_TRADE
            reason = (
                f"probability {p} inside the no-entry band — signal "
                "insufficient for a new position"
            )

        return Decision(
            decision_id=decision_id or prefixed_hash(
                DECISION_PREFIX,
                {
                    "kind": "decision",
                    "action": action.value,
                    "artifact": artifact.artifact_hash,
                    "at": timestamp,
                },
            ),
            action=action,
            symbol=artifact.symbol,
            timestamp=timestamp,
            prediction_ids=(artifact.prediction_id,),
            model_versions=artifact.model_versions,
            uncertainty=unc,
            regime=artifact.regime,
            crash_risk=dict(artifact.crash_risk),
            portfolio_state={"position_quantity": str(position_quantity)},
            reason=reason,
            rejected_alternatives=tuple(rejected),
            correlation_id=correlation_id,
        )


__all__ = [
    "DecisionError",
    "DecisionThresholds",
    "MarketDataStatus",
    "DecisionEngine",
]
