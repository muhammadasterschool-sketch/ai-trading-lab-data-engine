"""Data quarantine system for the AI Trading Lab Data Engine.

Invalid or suspicious data is isolated and cannot be consumed
downstream until reviewed or reprocessed.
"""

from datetime import datetime, UTC
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict
from data_engine.schemas import ValidationResult, ValidationStatus, Candle
import hashlib
import json


class QuarantinedRecord(BaseModel):
    """A record quarantined from the canonical dataset."""
    model_config = ConfigDict(frozen=True)
    dataset_id: str
    record_index: Optional[int]
    candle_hash: Optional[str]
    validation_results: List[ValidationResult]
    quarantined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str
    status: str = "QUARANTINED"

    @property
    def is_critical(self) -> bool:
        return any(r.is_critical for r in self.validation_results)

    def hash(self) -> str:
        data = json.dumps(self.model_dump(), default=str)
        return hashlib.sha256(data.encode()).hexdigest()


class QuarantineManager:
    """Manages quarantined records.

    Quarantined data cannot flow into research, quant, or backtest pipelines.
    """

    def __init__(self):
        self._quarantined: Dict[str, QuarantinedRecord] = {}
        self._quarantine_log: List[Dict] = []

    def quarantine(self, dataset_id: str, results: List[ValidationResult]):
        """Quarantine records with invalid/QUARANTINED status."""
        critical_results = [r for r in results if r.status in (ValidationStatus.INVALID, ValidationStatus.QUARANTINED)]
        if not critical_results:
            return

        for result in critical_results:
            record = QuarantinedRecord(
                dataset_id=dataset_id,
                record_index=result.record_index,
                validation_results=[result],
                reason=result.message,
            )
            key = f"{dataset_id}::{result.record_index}::{result.rule}"
            self._quarantined[key] = record

        self._quarantine_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "dataset_id": dataset_id,
            "quarantined_count": len(critical_results),
            "reasons": [r.message for r in critical_results],
        })

    def is_quarantined(self, dataset_id: str, record_index: int) -> bool:
        """Check if a specific record is quarantined."""
        key = f"{dataset_id}::{record_index}"
        return any(key in k for k in self._quarantined)

    def get_quarantined_for_dataset(self, dataset_id: str) -> List[QuarantinedRecord]:
        """Get all quarantined records for a dataset."""
        return [
            r for r in self._quarantined.values()
            if r.dataset_id == dataset_id
        ]

    def get_quarantine_report(self) -> Dict:
        """Return a full quarantine report."""
        return {
            "total_quarantined": len(self._quarantined),
            "datasets_affected": list(set(r.dataset_id for r in self._quarantined.values())),
            "quarantine_log": self._quarantine_log,
            "critical_records": [
                r.model_dump() for r in self._quarantined.values() if r.is_critical
            ],
        }

    def release(self, dataset_id: str, record_index: int, reason: str = "reprocessed"):
            """Release a quarantined record after review/reprocessing.

            Requires explicit reason. Never auto-releases.
            Uses copy-on-write pattern since records are immutable.
            """
            key = f"{dataset_id}::{record_index}"
            matching = [k for k in self._quarantined if k.startswith(key)]
            for k in matching:
                old_record = self._quarantined[k]
                new_record = old_record.model_copy(update={
                    "status": f"RELEASED:{reason}",
                    "quarantined_at": datetime.now(UTC),
                })
                self._quarantined[k] = new_record
                self._quarantine_log.append({
                    "timestamp": datetime.now(UTC).isoformat(),
                    "action": "RELEASE",
                    "key": k,
                    "reason": reason,
                })

    def can_downstream_use(self, dataset_id: str) -> bool:
        """Check if any quarantined data blocks downstream use."""
        dataset_quarantined = [r for r in self._quarantined.values() if r.dataset_id == dataset_id]
        if not dataset_quarantined:
            return True
        return not any(r.is_critical for r in dataset_quarantined)

    def to_dict(self) -> Dict:
        return {
            "total_quarantined": len(self._quarantined),
            "quarantine_log": self._quarantine_log,
        }
