"""Crash-risk assessment contract (§4F, §5, §27, §29).

A crash-risk output is a PROBABILISTIC forecast — never a deterministic
claim (§0, §57). The assessment carries: probability, horizon, severity
threshold, confidence, evidence, regime, uncertainty, machine-readable
block reason, and full provenance. The output hash covers the core
payload so the assessment is tamper-evident and reproducible.
"""

from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import (
    BlockReason,
    PredictionContractError,
    PredictionControlState,
    RiskLevel,
)
from data_engine.prediction.identity import OUTPUT_PREFIX, prefixed_hash
from data_engine.prediction.uncertainty import UncertaintyBand


class RiskThresholds(BaseModel):
    """Probability bands for risk-level classification (documented)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    low_max: float = 0.10
    elevated_max: float = 0.25
    high_max: float = 0.50

    @field_validator("low_max", "elevated_max", "high_max")
    @classmethod
    def _validate_bands(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("risk bands must be in (0, 1)")
        return v


DEFAULT_RISK_THRESHOLDS = RiskThresholds()

_VALID_STATUS_VALUES = frozenset(
    {level.value for level in RiskLevel}
) | frozenset({state.value for state in PredictionControlState})


def classify_risk_level(
    probability: Optional[float],
    thresholds: RiskThresholds = DEFAULT_RISK_THRESHOLDS,
) -> str:
    """Classify a probability into a risk band (§4F). None -> NO_SIGNAL."""
    if probability is None:
        return RiskLevel.NO_SIGNAL.value
    if not (0.0 <= probability <= 1.0):
        raise PredictionContractError(
            f"probability out of range: {probability!r}"
        )
    if probability < thresholds.low_max:
        return RiskLevel.LOW_RISK.value
    if probability < thresholds.elevated_max:
        return RiskLevel.ELEVATED_RISK.value
    if probability < thresholds.high_max:
        return RiskLevel.HIGH_RISK.value
    return RiskLevel.EXTREME_RISK.value


class CrashRiskAssessment(BaseModel):
    """One governed crash-risk output (§4F field set).

    ``status`` is a RiskLevel value when a probabilistic band was
    produced, or a PredictionControlState value when the system refused.
    ``blocked_reason`` is mandatory for every refusal (§27).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: str
    status: str
    probability: Optional[float]
    horizon_bars: int
    severity_threshold: float
    confidence: str  # "calibrated" | "uncalibrated" | "none"
    evidence_score: Optional[float]
    evidence_status: str
    regime: str
    label_definition_id: str
    model_id: str
    model_version: str
    pit_cutoff: str
    prediction_time: str
    uncertainty: Optional[UncertaintyBand] = None
    blocked_reason: Optional[BlockReason] = None
    restricted: bool = False
    notes: Tuple[str, ...] = ()

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: str) -> str:
        if v not in _VALID_STATUS_VALUES:
            raise PredictionContractError(
                f"invalid assessment status {v!r} — must be a RiskLevel "
                "or PredictionControlState value"
            )
        return v

    @field_validator("horizon_bars")
    @classmethod
    def _validate_horizon(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("horizon_bars must be a positive int")
        return v

    @field_validator("severity_threshold")
    @classmethod
    def _validate_threshold(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("severity_threshold must be in (0, 1)")
        return v

    @property
    def refused(self) -> bool:
        return self.status in {
            state.value for state in PredictionControlState
        }

    def output_payload(self) -> dict:
        """Canonical core payload — the hashed output content."""
        from data_engine.prediction.identity import freeze_number

        return {
            "kind": "crash_risk_assessment",
            "prediction_id": self.prediction_id,
            "status": self.status,
            "probability": freeze_number(self.probability),
            "horizon_bars": self.horizon_bars,
            "severity_threshold": freeze_number(self.severity_threshold),
            "confidence": self.confidence,
            "evidence_score": freeze_number(self.evidence_score),
            "evidence_status": self.evidence_status,
            "regime": self.regime,
            "label_definition_id": self.label_definition_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "pit_cutoff": self.pit_cutoff,
            "prediction_time": self.prediction_time,
            "uncertainty": (
                None
                if self.uncertainty is None
                else {
                    "method": self.uncertainty.method,
                    "point": freeze_number(self.uncertainty.point),
                    "lower": freeze_number(self.uncertainty.lower),
                    "upper": freeze_number(self.uncertainty.upper),
                    "level": freeze_number(self.uncertainty.level),
                }
            ),
            "blocked_reason": (
                None if self.blocked_reason is None
                else self.blocked_reason.value
            ),
            "restricted": self.restricted,
            "notes": list(self.notes),
        }

    @property
    def output_hash(self) -> str:
        """Tamper-evident output identity (``predo.``) over the core payload."""
        return prefixed_hash(OUTPUT_PREFIX, self.output_payload())


def _common_defaults(
    *,
    pit_cutoff: str,
    prediction_time: str,
    label_definition_id: str,
    horizon_bars: int,
    severity_threshold: float,
    model_id: str,
    model_version: str,
    regime: str = "UNKNOWN",
) -> dict:
    return {
        "pit_cutoff": pit_cutoff,
        "prediction_time": prediction_time,
        "label_definition_id": label_definition_id,
        "horizon_bars": horizon_bars,
        "severity_threshold": severity_threshold,
        "model_id": model_id,
        "model_version": model_version,
        "regime": regime,
    }


def blocked_assessment(
    reason: BlockReason,
    *,
    prediction_id: str,
    common: dict,
    notes: Tuple[str, ...] = (),
) -> CrashRiskAssessment:
    """Refusing assessment: PREDICTION_BLOCKED with machine reason (§27)."""
    payload = {**_common_defaults(**common), "prediction_id": prediction_id}
    payload.setdefault("regime", "UNKNOWN")
    return CrashRiskAssessment(
        **payload,
        status=PredictionControlState.PREDICTION_BLOCKED.value,
        probability=None,
        confidence="none",
        evidence_score=None,
        evidence_status="EVIDENCE_INSUFFICIENT (prediction refused)",
        blocked_reason=reason,
        notes=notes,
    )


def uncertain_assessment(
    *,
    prediction_id: str,
    common: dict,
    probability: float,
    uncertainty: UncertaintyBand,
    notes: Tuple[str, ...] = (),
) -> CrashRiskAssessment:
    """MODEL_UNCERTAIN assessment — probability recorded, never hidden (§19)."""
    payload = {**_common_defaults(**common), "prediction_id": prediction_id}
    return CrashRiskAssessment(
        **payload,
        status=PredictionControlState.MODEL_UNCERTAIN.value,
        probability=probability,
        confidence=common.get("confidence", "uncalibrated"),
        evidence_score=common.get("evidence_score"),
        evidence_status=common.get("evidence_status", "EVIDENCE_INSUFFICIENT"),
        uncertainty=uncertainty,
        notes=notes,
    )


__all__ = [
    "RiskThresholds",
    "DEFAULT_RISK_THRESHOLDS",
    "classify_risk_level",
    "CrashRiskAssessment",
    "blocked_assessment",
    "uncertain_assessment",
]
