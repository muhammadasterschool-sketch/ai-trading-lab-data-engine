"""AI Trading Lab — Data Engine.

Production-grade deterministic market-data engine.
Provides canonical schemas, validation, provenance, and data-quality
safeguards for all downstream research, quant, and backtesting components.

This module does NOT implement trading strategies and does NOT determine
whether any strategy is profitable.
"""

__version__ = "0.1.0"

from data_engine.schemas import (
    Candle,
    Dataset,
    DatasetVersion,
    Instrument,
    ProviderConfig,
    ProvenanceRecord,
    ValidationResult,
    ValidationStatus,
)
from data_engine.data_blocked import DATA_QUALITY_BLOCKED, DataQualityBlockedError
from data_engine.ingestion import DataIngester, IngestionResult
from data_engine.provider import MarketDataProvider, ProviderFactory
from data_engine.storage import DataStorage
from data_engine.validation import DataValidator
from data_engine.data_blocked import DataQualityGate
from data_engine.evidence import EvidenceLabel, EvidenceProvenance
from data_engine.quality_report import DataQualityReport
from data_engine.quarantine import QuarantineManager
from data_engine.provenance import ProvenanceTracker

__all__ = [
    "Candle",
    "Dataset",
    "DatasetVersion",
    "Instrument",
    "ProviderConfig",
    "ProvenanceRecord",
    "ValidationResult",
    "ValidationStatus",
    "DATA_QUALITY_BLOCKED",
    "DataQualityBlockedError",
    "DataIngester",
    "IngestionResult",
    "MarketDataProvider",
    "ProviderFactory",
    "DataStorage",
    "DataValidator",
    "DataQualityGate",
    "EvidenceLabel",
    "EvidenceProvenance",
    "DataQualityReport",
    "QuarantineManager",
    "ProvenanceTracker",
    "__version__",
]
