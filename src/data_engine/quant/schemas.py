"""Typed result structures for the Quant Engine.

Every calculation result is traceable to:
- dataset_id, dataset_version
- instrument, timeframe
- indicator name, parameters
- calculation convention
- engine version
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator

from data_engine.pit.immutable import freeze


class QuantEngineVersion:
    """Quant Engine version for calculation traceability."""
    MAJOR = 2
    MINOR = 0
    PATCH = 0

    @classmethod
    def version_string(cls) -> str:
        return f"{cls.MAJOR}.{cls.MINOR}.{cls.PATCH}"

    @classmethod
    def calculation_timestamp(cls) -> str:
        return datetime.now(UTC).isoformat()


class CalculationMetadata(BaseModel):
    """Metadata traceable to every calculation result."""
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    dataset_version: str
    instrument: str
    timeframe: str
    indicator: str
    parameters: Dict[str, Any]
    source_field: str  # Which price field was used (e.g., "close", "high")
    calculation_convention: str  # e.g., "EMA_alpha=2/(period+1)"
    engine_version: str = Field(default_factory=QuantEngineVersion.version_string)
    calculation_timestamp: str = Field(default_factory=QuantEngineVersion.calculation_timestamp)

    @field_validator("parameters")
    @classmethod
    def _freeze_parameters(cls, v: Dict) -> Dict:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    def model_dump_traceable(self) -> Dict:
        """Return a fully traceable dict representation."""
        return self.model_dump()


class QuantResult(BaseModel):
    """Result from a deterministic quant calculation.

    Contains the calculated values plus full provenance metadata.
    """
    model_config = ConfigDict(frozen=True)

    indicator: str
    values: List[Optional[float]]
    metadata: CalculationMetadata
    success: bool = True
    error: Optional[str] = None
    warning_count: int = 0
    warnings: List[str] = Field(
        default_factory=list, validate_default=True
    )

    @field_validator("values", "warnings")
    @classmethod
    def _freeze_series(cls, v: List) -> List:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    @property
    def is_valid(self) -> bool:
        return self.success and self.error is None

    @property
    def has_warnings(self) -> bool:
        return self.warning_count > 0


class IndicatorResult(BaseModel):
    """A single indicator calculation result."""
    model_config = ConfigDict(frozen=True)

    indicator_name: str
    period: int
    values: List[Optional[float]]
    dataset_id: str
    timeframe: str
    instrument: str
    engine_version: str = Field(default_factory=QuantEngineVersion.version_string)

    @field_validator("values")
    @classmethod
    def _freeze_values(cls, v: List) -> List:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    def __len__(self) -> int:
        return len(self.values)

    @property
    def last_value(self) -> Optional[float]:
        """Return the last non-None value."""
        for v in reversed(self.values):
            if v is not None:
                return v
        return None

    @property
    def is_complete(self) -> bool:
        """True if no NaN/None values in the series."""
        return all(v is not None for v in self.values)


class IndicatorSeries(BaseModel):
    """A named series of calculated values with timestamps."""
    model_config = ConfigDict(frozen=True)

    name: str
    timestamps: List[datetime]
    values: List[Optional[float]]
    timeframe: str

    @field_validator("timestamps", "values")
    @classmethod
    def _freeze_series(cls, v: List) -> List:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    def __len__(self) -> int:
        return len(self.values)

    def last_valid(self) -> tuple[Optional[float], Optional[datetime]]:
        """Return (value, timestamp) of the last non-None value."""
        for i in range(len(self.values) - 1, -1, -1):
            if self.values[i] is not None:
                return self.values[i], self.timestamps[i]
        return None, None


class StatisticsResult(BaseModel):
    """Result from statistical calculations."""
    model_config = ConfigDict(frozen=True)

    statistic: str
    value: float
    dataset_id: str
    timeframe: str
    engine_version: str = Field(default_factory=QuantEngineVersion.version_string)