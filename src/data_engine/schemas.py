"""Canonical Pydantic schemas for the AI Trading Lab Data Engine.

All market data flows through these schemas. They enforce structure,
type safety, and validation at the schema level before any data
enters the canonical dataset.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict
import hashlib
import json


class Timeframe(str, Enum):
    """Supported timeframes. Must be preserved; never silently converted."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    def validate(self):
        if self not in Timeframe:
            raise ValueError(f"Unsupported timeframe: {self}")


class AssetClass(str, Enum):
    CRYPTO = "cryptocurrency"
    FX = "forex"
    EQUITY = "equity"
    INDEX = "index"
    COMMODITY = "commodity"
    METAL = "metal"


class ContractType(str, Enum):
    SPOT = "spot"
    FUTURES = "futures"
    CFD = "cfd"
    OPTION = "option"
    UNKNOWN = "unknown"


# EvidenceProvenance re-exported from evidence.py per R-03 (spec §1.3).
# Canonical definition with is_strong_evidence() / is_valid_for_research()
# lives in evidence.py:18. The 'is' identity check must pass:
#   assert EvidenceProvenance is evidence.EvidenceProvenance
from data_engine.evidence import EvidenceProvenance  # canonical: evidence.py:18


class ValidationStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    QUARANTINED = "QUARANTINED"


def _now_utc() -> datetime:
    return datetime.now(UTC)


class Candle(BaseModel):
    """A single OHLCV candle with strict validation.

    Models are frozen (immutable) — post-construction mutation is not permitted.
    This ensures validation at construction time cannot be bypassed.
    """
    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    open: float = Field(..., gt=0, description="Must be positive")
    high: float = Field(..., gt=0, description="Must be positive")
    low: float = Field(..., gt=0, description="Must be positive")
    close: float = Field(..., gt=0, description="Must be positive")
    volume: Optional[float] = Field(None, ge=0, description="Must be non-negative or None")
    timeframe: Timeframe
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    currency: str = "USD"
    provider_timestamp: Optional[datetime] = Field(default_factory=_now_utc)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        """Validate OHLC relationships after all fields are populated."""
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) < low ({self.low}). Impossible.")
        if self.high < max(self.open, self.close):
            raise ValueError(f"high ({self.high}) < max(open, close) ({max(self.open, self.close)}). OHLC violation.")
        if self.low > min(self.open, self.close):
            raise ValueError(f"low ({self.low}) > min(open, close) ({min(self.open, self.close)}). OHLC violation.")
        if self.low > self.high:
            raise ValueError(f"low ({self.low}) > high ({self.high}). Impossible.")
        self._validate_bid_ask()
        return self

    def _validate_bid_ask(self) -> None:
        """Validate bid/ask consistency. Bid and ask are validated independently
        when present, enforcing finiteness, positivity, and bid <= ask."""
        # Validate bid independently when present
        if self.bid is not None:
            if not (float('-inf') < self.bid < float('inf')):
                raise ValueError(f"bid ({self.bid}) must be finite and positive")
            if self.bid <= 0:
                raise ValueError(f"bid ({self.bid}) must be positive when present")
        # Validate ask independently when present
        if self.ask is not None:
            if not (float('-inf') < self.ask < float('inf')):
                raise ValueError(f"ask ({self.ask}) must be finite and positive")
            if self.ask <= 0:
                raise ValueError(f"ask ({self.ask}) must be positive when present")
        # Cross-validate when both present
        if self.bid is not None and self.ask is not None:
            if self.bid > self.ask:
                raise ValueError(
                    f"bid ({self.bid}) > ask ({self.ask}). "
                    f"Bid must be less than or equal to ask."
                )
        # Spread must be non-negative when present
        if self.spread is not None and self.spread < 0:
            raise ValueError(f"spread ({self.spread}) must be non-negative")
        # If spread provided but no ask, check consistency with bid
        if self.bid is not None and self.spread is not None and self.ask is None:
            if self.bid + self.spread <= self.bid:
                raise ValueError(f"bid + spread must be > bid when spread is present")

    def to_hash(self) -> str:
        """Return a SHA-256 hash of this candle's contents."""
        data = self.model_dump_json()
        return hashlib.sha256(data.encode()).hexdigest()


class Instrument(BaseModel):
    """Canonical instrument representation."""
    model_config = ConfigDict(frozen=True)
    symbol: str = Field(..., description="Canonical symbol, e.g. XAU/USD")
    asset_class: AssetClass
    base_asset: str = Field(..., description="Base asset, e.g. XAU")
    quote_asset: str = Field(..., description="Quote asset, e.g. USD")
    exchange: Optional[str] = None
    venue: Optional[str] = None
    contract_type: ContractType = ContractType.SPOT
    currency: str = "USD"
    provider_symbol: Optional[str] = None

    def __str__(self):
        return f"{self.symbol} ({self.asset_class.value})"


class ProviderConfig(BaseModel):
    """Provider configuration and connection parameters.

    Phase 4A.1 filesystem security (spec SECTION 11):
    - extra='forbid' (FS-17): unknown config keys raise — a strict
      config must never silently degrade through a typo
    - approved_data_root (FS-04): explicit approved data root for
      file-backed providers; file I/O fails closed without it (FS-06)
    - endpoint validated at construction when it is an absolute
      filesystem path (FS-18)
    - instrument_allowlist (FS-14): instruments validated before path
      construction
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    provider_name: str
    provider_type: str = Field(..., description="e.g. 'api', 'file', 'database', 'websocket'")
    endpoint: Optional[str] = None
    api_key_env_var: Optional[str] = Field(None, description="Environment variable name for API key")
    timezone: str = "UTC"
    supports_bid_ask: bool = False
    supports_volume: bool = True
    rate_limit_per_minute: Optional[int] = None
    approved_data_root: Optional[str] = Field(
        None,
        description="Approved data root for file-backed providers (FS-04). "
                    "File I/O fails closed when unset (FS-06).",
    )
    instrument_allowlist: Optional[list[str]] = Field(
        None,
        description="Allowed instrument identifiers (FS-14); validated "
                    "before any path construction (FS-16).",
    )
    audit_trail_path: Optional[str] = Field(
        None,
        description="Path to the structured security audit trail (FS-21/22).",
    )

    @model_validator(mode="after")
    def _validate_endpoint_at_construction(self) -> "ProviderConfig":
        """Validate endpoint at construction, not at first use (FS-18).

        When the endpoint is an absolute filesystem path, an approved
        data root MUST be configured and the endpoint MUST resolve
        inside it (FS-07). Non-path endpoints (URLs, relative paths)
        are validated at use time by the provider's containment layer.
        """
        endpoint = self.endpoint
        if endpoint is None:
            return self
        is_absolute_path = endpoint.startswith("/") or endpoint.startswith("\\\\")
        if len(endpoint) >= 2 and endpoint[1] == ":" and endpoint[0].isalpha():
            is_absolute_path = True
        if is_absolute_path:
            if self.approved_data_root is None:
                raise ValueError(
                    f"FS-06/FS-18 violation: endpoint {endpoint!r} is an "
                    f"absolute path but no approved_data_root is configured. "
                    f"Filesystem access fails closed without an approved root."
                )
            from pathlib import Path
            resolved = Path(endpoint).resolve()
            root = Path(self.approved_data_root).resolve()
            if resolved != root and root not in resolved.parents:
                raise ValueError(
                    f"FS-07 violation: absolute endpoint {endpoint!r} resolves "
                    f"to {resolved}, which is outside the approved data root "
                    f"{root}.",
                )
        return self


class ProvenanceRecord(BaseModel):
    """Complete provenance record for a dataset."""
    model_config = ConfigDict(frozen=True)
    dataset_id: str
    dataset_version: str
    provider: str
    source: str
    instrument: Instrument
    timeframe: Timeframe
    start_timestamp: datetime
    end_timestamp: datetime
    retrieval_timestamp: datetime
    timezone: str
    source_hash: Optional[str] = None
    transformation_history: list[dict] = Field(default_factory=list)
    validation_status: ValidationStatus = ValidationStatus.VALID
    evidence_provenance: EvidenceProvenance = EvidenceProvenance.UNKNOWN

    def add_transformation(self, name: str, description: str, version: str):
        """Append an immutable transformation record.

        Note: Because this model is frozen, the transformation_history list
        is extended via a copy-on-write pattern. The list object itself is
        replaced, not mutated.
        """
        new_history = self.transformation_history + [{
            "name": name,
            "description": description,
            "version": version,
            "timestamp": datetime.now(UTC).isoformat(),
        }]
        # Return a new instance with updated history
        return self.model_copy(update={"transformation_history": new_history})

    def to_hash(self) -> str:
        """Return SHA-256 hash of the provenance record."""
        data = self.model_dump_json()
        return hashlib.sha256(data.encode()).hexdigest()


class DatasetVersion(BaseModel):
    """Immutable dataset version identifier."""
    model_config = ConfigDict(frozen=True)
    dataset_id: str
    version: str
    source: str
    instrument: Instrument
    timeframe: Timeframe
    time_period_start: datetime
    time_period_end: datetime
    ingestion_version: str
    transformation_version: str
    validation_version: str
    created_at: datetime = Field(default_factory=_now_utc)
    is_immutable: bool = True

    def __str__(self):
        return f"{self.dataset_id}@v{self.version}"


class Dataset(BaseModel):
    """Canonical dataset container."""
    model_config = ConfigDict(frozen=True)
    dataset_id: str
    version: DatasetVersion
    candles: list[Candle]
    provenance: ProvenanceRecord
    raw_data_hash: Optional[str] = None
    total_rows: int = Field(..., ge=0)
    expected_rows: Optional[int] = None

    @model_validator(mode="after")
    def validate_total_rows(self) -> "Dataset":
        if self.total_rows != len(self.candles):
            raise ValueError(f"total_rows ({self.total_rows}) must equal len(candles) ({len(self.candles)})")
        return self

    def quality_report(self) -> "DataQualityReport":
        """Generate a data quality report for this dataset."""
        from data_engine.quality_report import DataQualityReport
        from data_engine.validation import DataValidator
        validator = DataValidator()
        results = validator.validate_dataset(self)
        return DataQualityReport.from_dataset_and_results(self, results)

class ValidationResult(BaseModel):
    """Result of validation for a single candle or dataset."""
    model_config = ConfigDict(frozen=True)
    status: ValidationStatus
    record_index: Optional[int] = None
    record_id: Optional[str] = None
    rule: str
    severity: str = "WARNING"
    message: str
    details: Optional[dict] = None
    timestamp: datetime = Field(default_factory=_now_utc)

    @property
    def is_passing(self) -> bool:
        return self.status in (ValidationStatus.VALID, ValidationStatus.WARNING)

    @property
    def is_critical(self) -> bool:
        return self.status in (ValidationStatus.INVALID, ValidationStatus.QUARANTINED)
