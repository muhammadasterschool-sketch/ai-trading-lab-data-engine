"""Data quality blocked exception and status for the AI Trading Lab Data Engine.

When data quality is insufficient, downstream analysis MUST stop.
The system returns DATA_QUALITY_BLOCKED instead of continuing
with guessed or fabricated values.
"""

from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, List, Dict


DATA_QUALITY_BLOCKED = "DATA_QUALITY_BLOCKED"


class DataQualityBlockedError(Exception):
    """Raised when data quality is insufficient for downstream processing.

    The downstream system must receive:
    - status: DATA_QUALITY_BLOCKED
    - dataset ID
    - instrument
    - timeframe
    - affected period
    - exact failure reason
    - validation rule
    - severity

    No LLM-generated repair is allowed.
    Any automatic repair must be deterministic, documented,
    reproducible, and explicitly enabled.
    """

    def __init__(
        self,
        dataset_id: str,
        instrument: str,
        timeframe: str,
        period_start: str,
        period_end: str,
        failure_reason: str,
        validation_rule: str,
        severity: str = "CRITICAL",
    ):
        self.status = DATA_QUALITY_BLOCKED
        self.dataset_id = dataset_id
        self.instrument = instrument
        self.timeframe = timeframe
        self.period_start = period_start
        self.period_end = period_end
        self.failure_reason = failure_reason
        self.validation_rule = validation_rule
        self.severity = severity
        self.timestamp = datetime.now(UTC)
        super().__init__(
            f"{DATA_QUALITY_BLOCKED}: {failure_reason} "
            f"(dataset={dataset_id}, rule={validation_rule})"
        )

    def to_report(self) -> Dict:
        """Return the blocked status report."""
        return {
            "status": self.status,
            "dataset_id": self.dataset_id,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "affected_period_start": self.period_start,
            "affected_period_end": self.period_end,
            "exact_failure_reason": self.failure_reason,
            "validation_rule": self.validation_rule,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "no_llm_repair": True,
            "message": (
                "Downstream analysis must STOP. "
                "No LLM-generated repair is permitted. "
                "Resolve data quality issues before continuing."
            ),
        }


class DataQualityGate:
    """Hard downstream safety boundary.

    Validates that data meets minimum quality requirements
    before allowing downstream processing.
    """

    def __init__(self):
        self._blocked_datasets: Dict[str, DataQualityBlockedError] = {}

    def check(
        self,
        dataset,
        min_candles: int = 1,
        require_known_provenance: bool = True,
        require_valid_validation: bool = True,
    ) -> tuple[bool, Optional[DataQualityBlockedError]]:
        """Check if a dataset passes quality gate.

        Returns (passed, error_if_blocked).
        """
        # Check candle count
        if len(dataset.candles) < min_candles:
            error = DataQualityBlockedError(
                dataset_id=dataset.dataset_id,
                instrument=dataset.provenance.instrument.symbol,
                timeframe=dataset.provenance.timeframe.value,
                period_start=dataset.provenance.start_timestamp.isoformat(),
                period_end=dataset.provenance.end_timestamp.isoformat(),
                failure_reason=f"Insufficient candles: {len(dataset.candles)} < {min_candles}",
                validation_rule="minimum_candle_count",
                severity="CRITICAL",
            )
            self._blocked_datasets[dataset.dataset_id] = error
            return False, error

        # Check provenance
        if require_known_provenance:
            if dataset.provenance.evidence_provenance.value == "UNKNOWN":
                error = DataQualityBlockedError(
                    dataset_id=dataset.dataset_id,
                    instrument=dataset.provenance.instrument.symbol,
                    timeframe=dataset.provenance.timeframe.value,
                    period_start=dataset.provenance.start_timestamp.isoformat(),
                    period_end=dataset.provenance.end_timestamp.isoformat(),
                    failure_reason="UNKNOWN evidence provenance. Cannot be treated as strong research evidence.",
                    validation_rule="provenance_check",
                    severity="HIGH",
                )
                self._blocked_datasets[dataset.dataset_id] = error
                return False, error

            if dataset.provenance.evidence_provenance.value == "SYNTHETIC":
                # SYNTHETIC data is blocked from production/research eligibility.
                # It may only be used for unit tests, simulation, or development.
                error = DataQualityBlockedError(
                    dataset_id=dataset.dataset_id,
                    instrument=dataset.provenance.instrument.symbol,
                    timeframe=dataset.provenance.timeframe.value,
                    period_start=dataset.provenance.start_timestamp.isoformat(),
                    period_end=dataset.provenance.end_timestamp.isoformat(),
                    failure_reason="SYNTHETIC evidence provenance. Cannot be treated as REAL market evidence or used for production/research eligibility.",
                    validation_rule="synthetic_policy",
                    severity="HIGH",
                )
                self._blocked_datasets[dataset.dataset_id] = error
                return False, error

            if dataset.provenance.evidence_provenance.value == "SIMULATED":
                # SIMULATED data is blocked from production/research eligibility.
                error = DataQualityBlockedError(
                    dataset_id=dataset.dataset_id,
                    instrument=dataset.provenance.instrument.symbol,
                    timeframe=dataset.provenance.timeframe.value,
                    period_start=dataset.provenance.start_timestamp.isoformat(),
                    period_end=dataset.provenance.end_timestamp.isoformat(),
                    failure_reason="SIMULATED evidence provenance. Cannot be treated as REAL market evidence or used for production/research eligibility.",
                    validation_rule="simulated_policy",
                    severity="HIGH",
                )
                self._blocked_datasets[dataset.dataset_id] = error
                return False, error

        # Check validation status
        if require_valid_validation:
            if dataset.provenance.validation_status.value == "INVALID":
                error = DataQualityBlockedError(
                    dataset_id=dataset.dataset_id,
                    instrument=dataset.provenance.instrument.symbol,
                    timeframe=dataset.provenance.timeframe.value,
                    period_start=dataset.provenance.start_timestamp.isoformat(),
                    period_end=dataset.provenance.end_timestamp.isoformat(),
                    failure_reason="Dataset has INVALID validation status.",
                    validation_rule="validation_status",
                    severity="CRITICAL",
                )
                self._blocked_datasets[dataset.dataset_id] = error
                return False, error

            if dataset.provenance.validation_status.value == "QUARANTINED":
                error = DataQualityBlockedError(
                    dataset_id=dataset.dataset_id,
                    instrument=dataset.provenance.instrument.symbol,
                    timeframe=dataset.provenance.timeframe.value,
                    period_start=dataset.provenance.start_timestamp.isoformat(),
                    period_end=dataset.provenance.end_timestamp.isoformat(),
                    failure_reason="Dataset is QUARANTINED. Must not enter downstream research.",
                    validation_rule="quarantine_status",
                    severity="CRITICAL",
                )
                self._blocked_datasets[dataset.dataset_id] = error
                return False, error

        return True, None

    def is_blocked(self, dataset_id: str) -> bool:
        return dataset_id in self._blocked_datasets

    def get_blocked_report(self, dataset_id: str) -> Optional[DataQualityBlockedError]:
        return self._blocked_datasets.get(dataset_id)

    def to_dict(self) -> Dict:
        return {
            "blocked_datasets": [
                e.to_report() for e in self._blocked_datasets.values()
            ],
            "total_blocked": len(self._blocked_datasets),
        }
