"""Provenance and dataset versioning for the AI Trading Lab Data Engine.

Every dataset has a complete provenance record that answers:
'Exactly which data produced this backtest?'

Dataset versions are immutable. A new ingestion creates a new version.
"""

from datetime import datetime, UTC
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from data_engine.schemas import (
    ProvenanceRecord, DatasetVersion, ValidationStatus, Candle, Instrument
)
from data_engine.schemas import Timeframe
import hashlib
import json


class ProvenanceTracker:
    """Tracks provenance and versioning for all datasets."""

    def __init__(self):
        self._versions: Dict[str, List[DatasetVersion]] = {}
        self._provenance: Dict[str, ProvenanceRecord] = {}
        self._access_log: List[Dict] = []

    def register_dataset(self, dataset, provenance: ProvenanceRecord):
        """Register a dataset version."""
        dataset_id = provenance.dataset_id
        version = provenance.dataset_version

        if dataset_id not in self._versions:
            self._versions[dataset_id] = []

        dv = DatasetVersion(
            dataset_id=dataset_id,
            version=version,
            source=provenance.provider,
            instrument=provenance.instrument,
            timeframe=provenance.timeframe,
            time_period_start=provenance.start_timestamp,
            time_period_end=provenance.end_timestamp,
            ingestion_version="1.0",
            transformation_version=str(len(self._versions.get(dataset_id, [])) + 1),
            validation_version="1.0",
        )

        self._versions[dataset_id].append(dv)
        self._provenance[dataset_id] = provenance

    def get_version_history(self, dataset_id: str) -> List[DatasetVersion]:
        """Return all versions of a dataset."""
        return self._versions.get(dataset_id, [])

    def get_current_version(self, dataset_id: str) -> Optional[DatasetVersion]:
        """Return the latest version."""
        history = self._versions.get(dataset_id, [])
        return history[-1] if history else None

    def get_provenance(self, dataset_id: str) -> Optional[ProvenanceRecord]:
        """Return provenance for a dataset."""
        return self._provenance.get(dataset_id)

    def can_downstream_use(self, dataset_id: str) -> tuple[bool, Optional[str]]:
        """Check if a dataset can be used downstream.

        Returns (can_use, reason_if_blocked).
        """
        provenance = self._provenance.get(dataset_id)
        if provenance is None:
            return False, f"Dataset {dataset_id} not found in provenance tracker."

        if provenance.evidence_provenance.value == "UNKNOWN":
            return False, (
                f"Dataset {dataset_id} has UNKNOWN provenance. "
                f"Cannot be treated as strong research evidence."
            )

        if provenance.evidence_provenance.value == "SYNTHETIC":
            return False, (
                f"Dataset {dataset_id} is SYNTHETIC. "
                f"Must not be represented as REAL market data."
            )

        if provenance.validation_status == ValidationStatus.INVALID:
            return False, (
                f"Dataset {dataset_id} has INVALID validation status."
            )

        if provenance.validation_status == ValidationStatus.QUARANTINED:
            return False, (
                f"Dataset {dataset_id} is QUARANTINED. "
                f"Must not enter downstream research."
            )

        return True, None

    def log_access(self, dataset_id: str, operation: str, user: str = "system"):
        """Log dataset access for audit trail."""
        self._access_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "dataset_id": dataset_id,
            "operation": operation,
            "user": user,
        })

    def answer_provenance_query(self, dataset_id: str) -> Dict:
        """Answer: 'Exactly which data produced this backtest?'"""
        provenance = self._provenance.get(dataset_id)
        if provenance is None:
            return {"dataset_id": dataset_id, "error": "Not found"}

        return {
            "dataset_id": provenance.dataset_id,
            "dataset_version": provenance.dataset_version,
            "provider": provenance.provider,
            "source_type": provenance.source,
            "instrument": provenance.instrument.model_dump() if provenance.instrument else None,
            "timeframe": provenance.timeframe.value,
            "start": provenance.start_timestamp.isoformat(),
            "end": provenance.end_timestamp.isoformat(),
            "retrieved_at": provenance.retrieval_timestamp.isoformat(),
            "timezone": provenance.timezone,
            "source_hash": provenance.source_hash,
            "transformations": provenance.transformation_history,
            "validation_status": provenance.validation_status.value,
            "evidence_provenance": provenance.evidence_provenance.value,
            "access_log": self._access_log[:10],  # Last 10 accesses
        }

    def create_new_version(
        self,
        old_dataset_id: str,
        new_data: List[Candle],
        transformation: str,
        description: str,
    ) -> DatasetVersion:
        """Create a new immutable version from an existing dataset.

        Never mutates the old version. Creates a new one.
        """
        old_provenance = self._provenance.get(old_dataset_id)
        if old_provenance is None:
            raise ValueError(f"Cannot create new version of unknown dataset {old_dataset_id}")

        import uuid
        new_version = f"v{len(self._versions.get(old_dataset_id, [])) + 1}.{uuid.uuid4().hex[:8]}"
        new_dataset_id = f"{old_dataset_id}_{new_version}"

        new_provenance = ProvenanceRecord(
            dataset_id=new_dataset_id,
            dataset_version=new_version,
            provider=old_provenance.provider,
            source=old_provenance.source,
            instrument=old_provenance.instrument,
            timeframe=old_provenance.timeframe,
            start_timestamp=old_provenance.start_timestamp,
            end_timestamp=old_provenance.end_timestamp,
            retrieval_timestamp=datetime.now(UTC),
            timezone=old_provenance.timezone,
            source_hash=old_provenance.source_hash,
            evidence_provenance=old_provenance.evidence_provenance,
        )
        new_provenance = new_provenance.add_transformation(transformation, description, new_version)

        self.register_dataset(None, new_provenance)
        return self.get_current_version(new_dataset_id)

    def to_dict(self) -> Dict:
        """Serialize provenance tracker state."""
        return {
            "versions": {
                did: [v.model_dump() for v in versions]
                for did, versions in self._versions.items()
            },
            "provenance": {
                did: p.model_dump()
                for did, p in self._provenance.items()
            },
            "access_log_count": len(self._access_log),
        }
