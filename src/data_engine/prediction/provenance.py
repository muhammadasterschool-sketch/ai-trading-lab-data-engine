"""Prediction provenance (§15) — every prediction reproducible.

Every prediction carries a full provenance record covering identity,
model, dataset, features, configuration, PIT cutoff, input/output
hashes, regime, calibration, training window, and the environment
fingerprint. All timestamps are CALLER-SUPPLIED logical times — the
record never samples the wall clock (ID-WC discipline), so prediction
identity never depends on clock noise (§15: "Prediction identity must
never depend on wall-clock noise").
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.identity import prefixed_hash, PROVENANCE_PREFIX


class PredictionProvenance(BaseModel):
    """Full provenance record for one prediction (§15 field set)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: str
    model_id: str
    model_version: str
    experiment_id: str
    dataset_id: str
    feature_set_id: str
    feature_hash: str
    model_hash: str
    configuration_hash: str
    pit_cutoff: str
    prediction_time: str
    input_snapshot_hash: str
    output_hash: str
    regime: str
    calibration_version: str
    training_window: str
    training_data_hash: str
    environment_fingerprint: str

    _TEXT_FIELDS = (
        "prediction_id", "model_id", "model_version", "experiment_id",
        "dataset_id", "feature_set_id", "feature_hash", "model_hash",
        "configuration_hash", "pit_cutoff", "prediction_time",
        "input_snapshot_hash", "output_hash", "regime",
        "calibration_version", "training_window", "training_data_hash",
        "environment_fingerprint",
    )

    @field_validator(*_TEXT_FIELDS)
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(
                "provenance fields must be non-empty strings "
                "(use explicit 'UNRECORDED' when a value is genuinely "
                "unavailable — never fabricate)"
            )
        return v

    @property
    def provenance_hash(self) -> str:
        """Identity of the provenance record itself (``predv.``)."""
        return prefixed_hash(
            PROVENANCE_PREFIX,
            {
                "kind": "prediction_provenance",
                **{name: getattr(self, name) for name in self._TEXT_FIELDS},
            },
        )

    def to_record(self) -> dict:
        """Canonical, order-stable record for audit and serialization."""
        return {
            "prediction_id": self.prediction_id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "experiment_id": self.experiment_id,
            "dataset_id": self.dataset_id,
            "feature_set_id": self.feature_set_id,
            "feature_hash": self.feature_hash,
            "model_hash": self.model_hash,
            "configuration_hash": self.configuration_hash,
            "pit_cutoff": self.pit_cutoff,
            "prediction_time": self.prediction_time,
            "input_snapshot_hash": self.input_snapshot_hash,
            "output_hash": self.output_hash,
            "regime": self.regime,
            "calibration_version": self.calibration_version,
            "training_window": self.training_window,
            "training_data_hash": self.training_data_hash,
            "environment_fingerprint": self.environment_fingerprint,
            "provenance_hash": self.provenance_hash,
        }


__all__ = ["PredictionProvenance"]
