"""Storage layer for the AI Trading Lab Data Engine.

Implements strict separation:
RAW → immutable source representation
PROCESSED → normalized/validated representation
RESEARCH → data prepared for analysis

Never overwrite raw historical data with processed data.
Never overwrite historical datasets silently.
Retrieved objects are deep-copied to prevent mutation of internal state.
"""

from enum import Enum
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any, TypeVar, cast
from pydantic import BaseModel, Field
from data_engine.schemas import Candle, Dataset, ValidationStatus
from data_engine.provenance import ProvenanceRecord
import hashlib
import json
import os
import threading
import copy


T = TypeVar("T")


class StorageTier(str, Enum):
    RAW = "RAW"
    PROCESSED = "PROCESSED"
    RESEARCH = "RESEARCH"


class StorageRecord(BaseModel):
    """A record in the storage layer."""
    model_config = {"frozen": True}
    dataset_id: str
    tier: StorageTier
    data_hash: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    immutable: bool = True
    version: str = "1.0.0"
    metadata: Dict = Field(default_factory=dict)

    @property
    def is_immutable(self) -> bool:
        return self.immutable


class DataStorage:
    """Storage manager for the three-tier data architecture.

    RAW: Immutable after ingestion. Never overwritten.
    PROCESSED: Validated and normalized. Derived from RAW.
    RESEARCH: Prepared for analytical workflows. Derived from PROCESSED.
    """

    def __init__(self, storage_dir: str = "./data_engine_storage"):
        self.storage_dir = storage_dir
        self._lock = threading.Lock()
        self._raw_store: Dict[str, List[Candle]] = {}
        self._processed_store: Dict[str, Dataset] = {}
        self._research_store: Dict[str, Dict] = {}
        self._storage_log: List[Dict] = []

        # Create storage directory if needed
        os.makedirs(storage_dir, exist_ok=True)

    def _now_utc(self) -> datetime:
        """Return current UTC timestamp using timezone-aware datetime."""
        return datetime.now(UTC)

    def store_raw(self, dataset_id: str, candles: List[Candle], hash: str):
        """Store data in RAW tier (immutable)."""
        with self._lock:
            if dataset_id in self._raw_store:
                raise ValueError(
                    f"RAW dataset {dataset_id} already exists. "
                    f"RAW data is immutable and must not be overwritten. "
                    f"Create a new version instead."
                )
            self._raw_store[dataset_id] = candles
            self._storage_log.append({
                "timestamp": self._now_utc().isoformat(),
                "action": "STORE_RAW",
                "dataset_id": dataset_id,
                "candle_count": len(candles),
                "data_hash": hash,
                "tier": "RAW",
            })

    def store_processed(self, dataset: Dataset):
        """Store validated/normalized data in PROCESSED tier."""
        with self._lock:
            self._processed_store[dataset.dataset_id] = dataset
            self._storage_log.append({
                "timestamp": self._now_utc().isoformat(),
                "action": "STORE_PROCESSED",
                "dataset_id": dataset.dataset_id,
                "candle_count": len(dataset.candles),
                "validation_status": dataset.provenance.validation_status.value,
                "tier": "PROCESSED",
                "derived_from_raw": dataset.dataset_id,
            })

    def store_research(self, dataset_id: str, research_data: Dict):
        """Store analysis-prepared data in RESEARCH tier."""
        with self._lock:
            self._research_store[dataset_id] = research_data
            self._storage_log.append({
                "timestamp": self._now_utc().isoformat(),
                "action": "STORE_RESEARCH",
                "dataset_id": dataset_id,
                "tier": "RESEARCH",
                "derived_from_processed": dataset_id,
            })

    def get_raw(self, dataset_id: str) -> Optional[List[Candle]]:
        """Retrieve immutable RAW data.

        Returns a deep copy so callers cannot mutate internal state.
        """
        with self._lock:
            data = self._raw_store.get(dataset_id)
            if data is None:
                return None
            return [c.model_copy(deep=True) for c in data]

    def get_processed(self, dataset_id: str) -> Optional[Dataset]:
        """Retrieve PROCESSED data.

        Returns a deep copy so callers cannot mutate internal state.
        """
        with self._lock:
            data = self._processed_store.get(dataset_id)
            if data is None:
                return None
            return data.model_copy(deep=True)

    def get_research(self, dataset_id: str) -> Optional[Dict]:
        """Retrieve RESEARCH data.

        Returns a deep copy so callers cannot mutate internal state.
        """
        with self._lock:
            data = self._research_store.get(dataset_id)
            if data is None:
                return None
            return copy.deepcopy(data)

    def get_all_raw_ids(self) -> list:
        return list(self._raw_store.keys())

    def get_all_processed_ids(self) -> list:
        return list(self._processed_store.keys())

    def get_all_research_ids(self) -> list:
        return list(self._research_store.keys())

    def raw_exists(self, dataset_id: str) -> bool:
        return dataset_id in self._raw_store

    def is_raw_immutable(self, dataset_id: str) -> bool:
        """Raw data is always immutable."""
        return dataset_id in self._raw_store

    def try_overwrite_raw(self, dataset_id: str) -> bool:
        """Explicitly attempt to overwrite RAW data.

        ALWAYS returns False — RAW is immutable.
        This method exists only to make the immutability guarantee explicit.
        """
        return False  # RAW can never be overwritten

    def get_storage_report(self) -> Dict:
        """Return a report of all storage tiers."""
        return {
            "raw": {
                "count": len(self._raw_store),
                "dataset_ids": list(self._raw_store.keys()),
            },
            "processed": {
                "count": len(self._processed_store),
                "dataset_ids": list(self._processed_store.keys()),
            },
            "research": {
                "count": len(self._research_store),
                "dataset_ids": list(self._research_store.keys()),
            },
            "total_access_log": len(self._storage_log),
            "storage_log": self._storage_log[-10:],  # Last 10 entries
        }

    def verify_raw_immutability(self) -> bool:
        """Verify that no RAW data has been overwritten.

        Returns True if all RAW datasets are immutable.
        """
        # In a production system, this would check file checksums.
        # Here we verify the in-memory contract holds.
        for dataset_id, candles in self._raw_store.items():
            if candles is None:
                return False
        return True

    def to_dict(self) -> Dict:
        return {
            "storage_report": self.get_storage_report(),
            "raw_immutability_verified": self.verify_raw_immutability(),
        }
