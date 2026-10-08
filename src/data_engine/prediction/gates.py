"""No-prediction gates (§27) — the system refuses, with a reason.

The gate evaluates every refusal condition in a FIXED order and fails
closed: the first failed check blocks the prediction with a
machine-readable :class:`BlockReason`. DEGRADED drift does not block but
marks the prediction RESTRICTED (§37 'restrict usage'); DRIFTED/INVALID
drift blocks. A prediction that cannot be made honestly is not made.
"""

from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import BlockReason, DriftState


class GateCheck(BaseModel):
    """One named gate check with its verdict and detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    detail: str


class PredictionGateInput(BaseModel):
    """Inputs to the no-prediction gate evaluation (§27 conditions)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    data_quality_ok: bool = True
    pit_proven: bool = True
    drift_state: DriftState = DriftState.STABLE
    regime_known: bool = True
    training_samples: int = 0
    min_training_samples: int = 30
    calibration_valid: bool = True
    validation_passed: bool = True
    feature_schema_match: bool = True
    model_artifact_hash_match: bool = True
    input_hash_match: bool = True
    horizon_bars: int = 20
    max_horizon_bars: int = 252
    history_bars: int = 0
    min_history_bars: int = 21

    @field_validator("min_training_samples", "min_history_bars",
                     "max_horizon_bars")
    @classmethod
    def _validate_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("gate thresholds must be positive ints")
        return v


class PredictionGateResult(BaseModel):
    """Verdict of the gate evaluation (§27)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    restricted: bool
    blocked_reason: Optional[BlockReason]
    checks: Tuple[GateCheck, ...]


def evaluate_prediction_gates(request: PredictionGateInput) -> PredictionGateResult:
    """Evaluate every §27 refusal condition; first failure blocks."""

    checks: list[GateCheck] = []

    def _fail(reason: BlockReason) -> PredictionGateResult:
        return PredictionGateResult(
            allowed=False,
            restricted=False,
            blocked_reason=reason,
            checks=tuple(checks),
        )

    checks.append(GateCheck(
        name="data_quality", passed=request.data_quality_ok,
        detail="data quality verdict",
    ))
    if not request.data_quality_ok:
        return _fail(BlockReason.DATA_QUALITY_FAILED)

    checks.append(GateCheck(
        name="pit_proof", passed=request.pit_proven,
        detail="PIT correctness proven for the input window",
    ))
    if not request.pit_proven:
        return _fail(BlockReason.PIT_UNPROVEN)

    drift_blocked = request.drift_state in (DriftState.DRIFTED, DriftState.INVALID)
    drift_restricted = request.drift_state is DriftState.DEGRADED
    checks.append(GateCheck(
        name="drift", passed=not drift_blocked,
        detail=f"drift state {request.drift_state.value}",
    ))
    if drift_blocked:
        return _fail(BlockReason.MODEL_DRIFT_UNACCEPTABLE)

    checks.append(GateCheck(
        name="regime_known", passed=request.regime_known,
        detail="regime classified at the PIT cutoff",
    ))
    if not request.regime_known:
        return _fail(BlockReason.REGIME_UNKNOWN)

    samples_ok = request.training_samples >= request.min_training_samples
    checks.append(GateCheck(
        name="training_samples", passed=samples_ok,
        detail=f"{request.training_samples} >= {request.min_training_samples}",
    ))
    if not samples_ok:
        return _fail(BlockReason.TRAINING_SAMPLE_INSUFFICIENT)

    checks.append(GateCheck(
        name="calibration", passed=request.calibration_valid,
        detail="calibration validity verdict",
    ))
    if not request.calibration_valid:
        return _fail(BlockReason.CALIBRATION_INVALID)

    checks.append(GateCheck(
        name="validation", passed=request.validation_passed,
        detail="out-of-sample validation verdict",
    ))
    if not request.validation_passed:
        return _fail(BlockReason.VALIDATION_FAILED)

    checks.append(GateCheck(
        name="feature_schema", passed=request.feature_schema_match,
        detail="feature schema matches the model contract",
    ))
    if not request.feature_schema_match:
        return _fail(BlockReason.FEATURE_SCHEMA_MISMATCH)

    checks.append(GateCheck(
        name="model_artifact_hash", passed=request.model_artifact_hash_match,
        detail="model artifact hash verified (§44)",
    ))
    if not request.model_artifact_hash_match:
        return _fail(BlockReason.MODEL_ARTIFACT_MISMATCH)

    checks.append(GateCheck(
        name="input_hash", passed=request.input_hash_match,
        detail="input snapshot hash verified",
    ))
    if not request.input_hash_match:
        return _fail(BlockReason.INPUT_HASH_MISMATCH)

    horizon_ok = 1 <= request.horizon_bars <= request.max_horizon_bars
    checks.append(GateCheck(
        name="horizon", passed=horizon_ok,
        detail=f"horizon {request.horizon_bars} in [1, {request.max_horizon_bars}]",
    ))
    if not horizon_ok:
        return _fail(BlockReason.HORIZON_INVALID)

    history_ok = request.history_bars >= request.min_history_bars
    checks.append(GateCheck(
        name="history_coverage", passed=history_ok,
        detail=f"{request.history_bars} bars >= {request.min_history_bars}",
    ))
    if not history_ok:
        return _fail(BlockReason.HISTORICAL_COVERAGE_INADEQUATE)

    return PredictionGateResult(
        allowed=True,
        restricted=drift_restricted,
        blocked_reason=None,
        checks=tuple(checks),
    )


__all__ = [
    "GateCheck",
    "PredictionGateInput",
    "PredictionGateResult",
    "evaluate_prediction_gates",
]
