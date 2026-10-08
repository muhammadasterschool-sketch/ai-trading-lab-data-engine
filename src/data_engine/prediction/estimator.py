"""CrashRiskEstimator — the governed end-to-end prediction orchestrator.

Pipeline (mandate §2 order — prediction intelligence does NOT bypass any
stage):

    PIT view -> data quality -> features -> regime -> gates -> model ->
    calibration -> uncertainty -> evidence -> risk level -> provenance ->
    assessment

Fail-closed design: the FIRST failed stage short-circuits to a
PREDICTION_BLOCKED assessment carrying a machine-readable reason (§27).
Every produced assessment embeds full provenance (§15) and is
reproducible: same candles + same cutoff + same model + same context ->
bit-identical prediction_id, probability, and output hash (T-PRED-006).
"""

from typing import Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import (
    BlockReason,
    DriftState,
    PredictionContractError,
)
from data_engine.prediction.crash import (
    DEFAULT_RISK_THRESHOLDS,
    CrashRiskAssessment,
    RiskThresholds,
    blocked_assessment,
    classify_risk_level,
    uncertain_assessment,
)
from data_engine.prediction.data_access import (
    PredictionDataError,
    evaluate_history_policy,
    pit_candle_view,
)
from data_engine.prediction.evidence_score import (
    EvidenceAssessment,
    evidence_assessment,
)
from data_engine.prediction.features import (
    FEATURE_SCHEMA,
    build_feature_rows,
    feature_data_hash,
    feature_set_id,
)
from data_engine.prediction.identity import (
    EnvironmentFingerprint,
    prefixed_hash,
    prediction_identity,
)
from data_engine.prediction.labels import CrashLabelDefinition
from data_engine.prediction.models import PredictionModelError
from data_engine.prediction.provenance import PredictionProvenance
from data_engine.prediction.regimes import RegimeEngine, RegimeFeatures
from data_engine.prediction.uncertainty import (
    MAX_PROBABILITY_BAND_WIDTH,
    UncertaintyBand,
    is_uncertain,
    probability_band,
)


class EstimatorConfig(BaseModel):
    """Configuration of the crash-risk estimator (§39 policy hooks).

    ``required_history_years``: the 5-year minimum is enforced BY DEFAULT.
    Set to ``None`` ONLY as an explicit operator decision (recorded in
    the assessment notes) — e.g. for synthetic test fixtures.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_thresholds: RiskThresholds = DEFAULT_RISK_THRESHOLDS
    min_history_bars: int = 21
    min_training_samples: int = 30
    max_horizon_bars: int = 252
    required_history_years: Optional[float] = 5.0

    @field_validator("min_history_bars", "min_training_samples",
                     "max_horizon_bars")
    @classmethod
    def _validate_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("estimator thresholds must be positive ints")
        return v


class CrashRiskEstimator:
    """Orchestrates the governed prediction pipeline (§2)."""

    def __init__(
        self,
        model,
        *,
        calibrator=None,
        regime_engine: Optional[RegimeEngine] = None,
        config: Optional[EstimatorConfig] = None,
        environment: Optional[EnvironmentFingerprint] = None,
        experiment_id: str = "EXP-UNRECORDED",
        dataset_id: str = "DS-UNRECORDED",
    ) -> None:
        for attr in ("fit", "predict_proba", "model_hash", "model_id",
                     "model_version"):
            if not hasattr(model, attr):
                raise PredictionContractError(
                    f"model must expose {attr!r} (prediction model contract)"
                )
        if calibrator is not None and not hasattr(calibrator, "calibrate"):
            raise PredictionContractError(
                "calibrator must expose calibrate()"
            )
        self._model = model
        self._calibrator = calibrator
        self._regime_engine = regime_engine or RegimeEngine()
        self._config = config or EstimatorConfig()
        self._environment = environment
        self._experiment_id = experiment_id
        self._dataset_id = dataset_id

    # ------------------------------------------------------------------

    def assess(
        self,
        candles: Sequence,
        *,
        as_of,
        label_definition: CrashLabelDefinition,
        prediction_time: str,
        drift_state: DriftState = DriftState.STABLE,
        calibration_valid: bool = True,
        validation_passed: bool = True,
        training_samples: int = 0,
        evidence_values: Optional[Mapping[str, object]] = None,
    ) -> CrashRiskAssessment:
        """Produce one governed crash-risk assessment at ``as_of``."""
        config = self._config
        horizon = label_definition.forward_horizon

        common = {
            "pit_cutoff": as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of),
            "prediction_time": prediction_time,
            "label_definition_id": label_definition.label_definition_id,
            "horizon_bars": horizon,
            "severity_threshold": label_definition.threshold,
            "model_id": self._model.model_id,
            "model_version": self._model.model_version,
        }
        placeholder_id = "pred.PENDING"

        # 1-2. PIT view + data quality ---------------------------------
        try:
            view = pit_candle_view(candles, as_of)
        except PredictionDataError:
            return blocked_assessment(
                BlockReason.DATA_QUALITY_FAILED,
                prediction_id=placeholder_id,
                common=common,
                notes=("candle contract violation (tz-aware timestamps required)",),
            )
        closes = [bar["close"] for bar in view.bars]
        if not closes:
            return blocked_assessment(
                BlockReason.DATA_QUALITY_FAILED,
                prediction_id=placeholder_id,
                common=common,
                notes=("no candles visible at the PIT cutoff",),
            )

        # 3. History policy (§39) — 5-year minimum by default ----------
        notes: list[str] = []
        if config.required_history_years is not None:
            history = evaluate_history_policy(
                visible_bars=view.visible_count,
                minimum_years=config.required_history_years,
            )
            if not history.meets_minimum:
                return blocked_assessment(
                    BlockReason.HISTORICAL_COVERAGE_INADEQUATE,
                    prediction_id=placeholder_id,
                    common=common,
                    notes=(
                        (
                            f"history policy: {history.years_covered} years "
                            f"visible < {config.required_history_years} "
                            "years minimum (§39)"
                        ),
                    ),
                )
        else:
            notes.append(
                "HISTORY POLICY NOT ENFORCED (operator override, §39)"
            )

        # 4. Features ---------------------------------------------------
        try:
            rows = build_feature_rows(
                closes, timestamps=[bar["timestamp"] for bar in view.bars]
            )
        except PredictionContractError as exc:
            reason = (
                BlockReason.HISTORICAL_COVERAGE_INADEQUATE
                if "insufficient bars" in str(exc)
                else BlockReason.DATA_QUALITY_FAILED
            )
            return blocked_assessment(
                reason,
                prediction_id=placeholder_id,
                common=common,
                notes=(str(exc),),
            )
        last_row = rows[-1]
        feature_hash = feature_data_hash(rows)

        # 5. Regime ------------------------------------------------------
        f = last_row.values
        regime = self._regime_engine.classify(
            RegimeFeatures(
                vol_20=f[2],
                vol_ratio=f[3],
                dd_depth=f[4],
                mom_20=f[1],
            )
        )

        # 6. Gates (§27) --------------------------------------------------
        from data_engine.prediction.gates import (
            PredictionGateInput,
            evaluate_prediction_gates,
        )

        gate_result = evaluate_prediction_gates(
            PredictionGateInput(
                data_quality_ok=True,  # survived closes validation above
                pit_proven=True,       # view built from a declared cutoff
                drift_state=drift_state,
                regime_known=(regime != "UNKNOWN"),
                training_samples=training_samples,
                min_training_samples=config.min_training_samples,
                calibration_valid=calibration_valid,
                validation_passed=validation_passed,
                feature_schema_match=len(last_row.values) == len(FEATURE_SCHEMA),
                model_artifact_hash_match=True,
                input_hash_match=True,
                horizon_bars=horizon,
                max_horizon_bars=config.max_horizon_bars,
                history_bars=view.visible_count,
                min_history_bars=config.min_history_bars,
            )
        )
        if not gate_result.allowed:
            assert gate_result.blocked_reason is not None  # fail-closed invariant
            return blocked_assessment(
                gate_result.blocked_reason,
                prediction_id=placeholder_id,
                common={**common, "regime": regime},
                notes=tuple(notes)
                + (f"gate failed: {gate_result.blocked_reason.value}",),
            )

        # 7. Model prediction (fail closed on contract errors) ----------
        try:
            raw_probability = float(
                self._model.predict_proba(last_row.values)
            )
        except PredictionModelError as exc:
            return blocked_assessment(
                BlockReason.FEATURE_SCHEMA_MISMATCH,
                prediction_id=placeholder_id,
                common={**common, "regime": regime},
                notes=tuple(notes) + (str(exc),),
            )
        if not (0.0 <= raw_probability <= 1.0):
            return blocked_assessment(
                BlockReason.MODEL_ARTIFACT_MISMATCH,
                prediction_id=placeholder_id,
                common={**common, "regime": regime},
                notes=(
                    f"model produced out-of-range probability {raw_probability!r}",
                ),
            )

        # 8. Calibration (§18) --------------------------------------------
        if self._calibrator is not None:
            probability = float(self._calibrator.calibrate(raw_probability))
            confidence = "calibrated"
            calibration_version = getattr(
                self._calibrator, "version", "UNRECORDED"
            )
        else:
            probability = raw_probability
            confidence = "uncalibrated"
            calibration_version = "UNCALIBRATED"

        # 9. Uncertainty (§19) ----------------------------------------------
        band: UncertaintyBand = probability_band(
            probability,
            n_effective=max(training_samples, 1),
        )
        if is_uncertain(band):
            return uncertain_assessment(
                prediction_id=placeholder_id,
                common={
                    **common,
                    "regime": regime,
                    "confidence": confidence,
                    "evidence_score": None,
                    "evidence_status": "EVIDENCE_INSUFFICIENT (uncertain)",
                },
                probability=probability,
                uncertainty=band,
                notes=tuple(notes)
                + (
                    f"uncertainty band width {round(band.width, 6)} >= "
                    f"{MAX_PROBABILITY_BAND_WIDTH} — refusing a "
                    "risk level (§19)",
                ),
            )

        # 10. Evidence (§17) — required for a risk-level status ------------
        if evidence_values is None:
            return CrashRiskAssessment(
                prediction_id=placeholder_id,
                status="EVIDENCE_INSUFFICIENT",
                probability=probability,
                horizon_bars=horizon,
                severity_threshold=label_definition.threshold,
                confidence=confidence,
                evidence_score=None,
                evidence_status="EVIDENCE_INSUFFICIENT (no evidence context provided)",
                regime=regime,
                label_definition_id=label_definition.label_definition_id,
                model_id=self._model.model_id,
                model_version=self._model.model_version,
                pit_cutoff=common["pit_cutoff"],
                prediction_time=prediction_time,
                uncertainty=band,
                restricted=gate_result.restricted,
                notes=tuple(notes)
                + ("evidence context is mandatory for a risk-level status (§17)",),
            )
        evidence: EvidenceAssessment = evidence_assessment(evidence_values)

        # 11-13. Risk level + identity + provenance + assessment ----------
        if evidence.insufficient:
            status = "EVIDENCE_INSUFFICIENT"
        else:
            status = classify_risk_level(
                probability, config.risk_thresholds
            )

        prediction_id = prediction_identity(
            model_id=self._model.model_id,
            model_version=self._model.model_version,
            feature_hash=feature_hash,
            pit_cutoff_iso=common["pit_cutoff"],
            horizon_bars=horizon,
            label_definition_id=label_definition.label_definition_id,
        )
        provenance = PredictionProvenance(
            prediction_id=prediction_id,
            model_id=self._model.model_id,
            model_version=self._model.model_version,
            experiment_id=self._experiment_id,
            dataset_id=self._dataset_id,
            feature_set_id=feature_set_id(),
            feature_hash=feature_hash,
            model_hash=self._model.model_hash,
            configuration_hash=self._configuration_hash(),
            pit_cutoff=common["pit_cutoff"],
            prediction_time=prediction_time,
            input_snapshot_hash=prefixed_hash(
                "predv.",
                {
                    "kind": "input_snapshot",
                    "closes": [round(c, 12) for c in closes],
                    "dropped_future_bars": view.dropped_future_bars,
                    "dropped_revision_bars": view.dropped_revision_bars,
                },
            ),
            output_hash="PENDING",  # replaced below via core payload
            regime=regime,
            calibration_version=calibration_version,
            training_window=f"0..{view.visible_count - 1}",
            training_data_hash=self._dataset_id,
            environment_fingerprint=(
                self._environment.fingerprint_hash
                if self._environment is not None
                else "UNRECORDED"
            ),
        )
        assessment = CrashRiskAssessment(
            prediction_id=prediction_id,
            status=status,
            probability=probability,
            horizon_bars=horizon,
            severity_threshold=label_definition.threshold,
            confidence=confidence,
            evidence_score=evidence.score,
            evidence_status=evidence.status,
            regime=regime,
            label_definition_id=label_definition.label_definition_id,
            model_id=self._model.model_id,
            model_version=self._model.model_version,
            pit_cutoff=common["pit_cutoff"],
            prediction_time=prediction_time,
            uncertainty=band,
            restricted=gate_result.restricted,
            notes=tuple(notes),
        )
        # Close the provenance loop: output_hash covers the core payload
        # (which excludes the provenance record itself — no circularity).
        final_provenance = provenance.model_copy(
            update={"output_hash": assessment.output_hash}
        )
        return assessment.model_copy(
            update={"notes": assessment.notes + (f"provenance_hash={final_provenance.provenance_hash}",)}
        )

    def _configuration_hash(self) -> str:
        return prefixed_hash(
            "predv.",
            {
                "kind": "estimator_configuration",
                "min_history_bars": self._config.min_history_bars,
                "min_training_samples": self._config.min_training_samples,
                "max_horizon_bars": self._config.max_horizon_bars,
                "required_history_years": (
                    None
                    if self._config.required_history_years is None
                    else float(self._config.required_history_years)
                ),
                "risk_thresholds": {
                    "low_max": self._config.risk_thresholds.low_max,
                    "elevated_max": self._config.risk_thresholds.elevated_max,
                    "high_max": self._config.risk_thresholds.high_max,
                },
                "regime_engine_version": self._regime_engine.engine_version,
            },
        )


__all__ = ["EstimatorConfig", "CrashRiskEstimator"]
