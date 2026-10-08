"""Prediction Intelligence — status vocabulary and control contracts.

Mandate reference: "AI Trading Lab — Prediction & Crash Intelligence
Master Architecture + Implementation Mandate" (§0, §4, §7, §20, §27, §30,
§37, §57).

Core principle (§0): this system NEVER claims deterministic crash
prediction. A crash prediction is always a probabilistic forecast or a
risk estimate. The vocabulary below exists so the system can say

    NO_SIGNAL / LOW_RISK / ELEVATED_RISK / HIGH_RISK / EXTREME_RISK
    MODEL_UNCERTAIN / DATA_INSUFFICIENT / REGIME_UNKNOWN /
    PREDICTION_BLOCKED

instead of forcing a prediction. The most important prediction the
system can make is "I DON'T KNOW" (§57).

Invariants:
- PC-01  the risk vocabulary is closed and machine-readable (enums only)
- PC-02  every refused prediction carries a machine-readable reason
- PC-03  control states (refusals) are distinct from risk levels
- PC-04  drift and model-lifecycle state machines are explicit (§20/§30)
- PC-05  prediction NEVER executes trades and NEVER overrides risk (§28)
"""

from enum import Enum


class PredictionContractError(ValueError):
    """Raised on prediction-contract violations (fail closed)."""


class RiskLevel(str, Enum):
    """Probabilistic risk band for a crash-risk estimate (§4F).

    A risk level is a classified probability band — never a deterministic
    claim that a crash will or will not occur.
    """

    NO_SIGNAL = "NO_SIGNAL"
    LOW_RISK = "LOW_RISK"
    ELEVATED_RISK = "ELEVATED_RISK"
    HIGH_RISK = "HIGH_RISK"
    EXTREME_RISK = "EXTREME_RISK"


class PredictionControlState(str, Enum):
    """Refusal / control states — the system declines to predict (§0, §27)."""

    MODEL_UNCERTAIN = "MODEL_UNCERTAIN"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    REGIME_UNKNOWN = "REGIME_UNKNOWN"
    PREDICTION_BLOCKED = "PREDICTION_BLOCKED"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"


class RegimeState(str, Enum):
    """Market regime states (§7). UNKNOWN is a first-class state."""

    NORMAL = "NORMAL"
    TRENDING = "TRENDING"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    STRESSED = "STRESSED"
    CRISIS = "CRISIS"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


class StressState(str, Enum):
    """Market-stress classification (§4E)."""

    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    STRESSED = "STRESSED"
    SEVERE = "SEVERE"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class DriftState(str, Enum):
    """Model drift states (§20) with mandated failure actions (§37).

    STABLE   continue
    WATCH    increase monitoring
    DEGRADED restrict usage
    DRIFTED  block or require review
    INVALID  retire the model
    """

    STABLE = "STABLE"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    DRIFTED = "DRIFTED"
    INVALID = "INVALID"


class ModelLifecycleState(str, Enum):
    """Predictive model lifecycle (§30). No model self-approves.

    DISCOVER -> TRAIN -> VALIDATE -> CALIBRATE -> ADVERSARIAL_TEST ->
    REGISTER -> HUMAN_REVIEW -> PAPER -> MONITOR -> GRADUATE
    or -> REJECT / RETIRE (terminal).
    """

    DISCOVER = "DISCOVER"
    TRAIN = "TRAIN"
    VALIDATE = "VALIDATE"
    CALIBRATE = "CALIBRATE"
    ADVERSARIAL_TEST = "ADVERSARIAL_TEST"
    REGISTER = "REGISTER"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    PAPER = "PAPER"
    MONITOR = "MONITOR"
    GRADUATE = "GRADUATE"
    REJECT = "REJECT"
    RETIRE = "RETIRE"


class BlockReason(str, Enum):
    """Machine-readable no-prediction reasons (§27).

    Every refusal MUST carry one of these — a blocked prediction is
    always inspectable.
    """

    DATA_QUALITY_FAILED = "DATA_QUALITY_FAILED"
    PIT_UNPROVEN = "PIT_UNPROVEN"
    MODEL_DRIFT_UNACCEPTABLE = "MODEL_DRIFT_UNACCEPTABLE"
    REGIME_UNKNOWN = "REGIME_UNKNOWN"
    TRAINING_SAMPLE_INSUFFICIENT = "TRAINING_SAMPLE_INSUFFICIENT"
    CALIBRATION_INVALID = "CALIBRATION_INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    FEATURE_SCHEMA_MISMATCH = "FEATURE_SCHEMA_MISMATCH"
    MODEL_ARTIFACT_MISMATCH = "MODEL_ARTIFACT_MISMATCH"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    HORIZON_INVALID = "HORIZON_INVALID"
    HISTORICAL_COVERAGE_INADEQUATE = "HISTORICAL_COVERAGE_INADEQUATE"
    CRISIS_SAMPLE_INSUFFICIENT = "CRISIS_SAMPLE_INSUFFICIENT"
    UNCERTAINTY_EXCESSIVE = "UNCERTAINTY_EXCESSIVE"


class CalibrationStatus(str, Enum):
    """Calibration validity (§18)."""

    CALIBRATION_VALID = "CALIBRATION_VALID"
    CALIBRATION_INVALID = "CALIBRATION_INVALID"
    UNCALIBRATED = "UNCALIBRATED"


class InsufficiencyState(str, Enum):
    """Explicit insufficiency declarations (§9, §12, §22, §39, §44).

    These states are recorded rather than hidden: the system never
    silently substitutes or fabricates to avoid them.
    """

    CRISIS_SAMPLE_INSUFFICIENT = "CRISIS_SAMPLE_INSUFFICIENT"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MICROSTRUCTURE_UNAVAILABLE = "MICROSTRUCTURE_UNAVAILABLE"
    EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"
    MODEL_NOT_JUSTIFIED = "MODEL_NOT_JUSTIFIED"
    MODEL_ARTIFACT_UNTRUSTED = "MODEL_ARTIFACT_UNTRUSTED"


#: Prediction-intelligence contract version (part of every identity
#: payload produced by this package).
PREDICTION_CONTRACT_VERSION = "1.0.0"


__all__ = [
    "PredictionContractError",
    "RiskLevel",
    "PredictionControlState",
    "RegimeState",
    "StressState",
    "DriftState",
    "ModelLifecycleState",
    "BlockReason",
    "CalibrationStatus",
    "InsufficiencyState",
    "PREDICTION_CONTRACT_VERSION",
]
