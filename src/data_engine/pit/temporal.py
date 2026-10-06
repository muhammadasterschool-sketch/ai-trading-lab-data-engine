"""Phase 4A.1 — Temporal Semantic Model for Point-in-Time data.

Defines the temporal semantic categories used in PIT data handling.

All timestamps must be timezone-aware and normalized to UTC.
Naive datetimes raise ValidationError.

ingestion_time is metadata only. It MUST NOT participate in:
- PIT eligibility
- availability calculations
- research identity hashes
- PIT hashes
"""

from datetime import datetime, UTC
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional
import hashlib


class TemporalDataType(str, Enum):
    """Canonical data-type categories for PIT data.

    Determines which temporal fields are required and how
    availability policies are applied.
    """
    OHLCV = "OHLCV"
    ECONOMIC = "ECONOMIC"
    NEWS = "NEWS"
    DERIVED = "DERIVED"

    def __str__(self) -> str:
        return self.value


class TemporalSemantics(BaseModel):
    """Immutable temporal semantic model for a single PIT observation.

    Every timestamp is timezone-aware and normalized to UTC.
    Naive datetimes are rejected at validation time.

    Fields:
        event_time: The time the event actually occurred.
        observation_time: The time the observation was recorded.
        publication_time: The time the data was published/made available.
        effective_time: The time the data becomes effective/applicable.
        revision_time: The time this specific version was revised.
        ingestion_time: Metadata-only timestamp of ingestion.
            MUST NOT participate in PIT eligibility, availability,
            or any hash computation.
    """
    model_config = ConfigDict(frozen=True)

    event_time: datetime = Field(..., description="Time the event occurred")
    observation_time: datetime = Field(..., description="Time observation was recorded")
    publication_time: Optional[datetime] = Field(None, description="Time data was published")
    effective_time: Optional[datetime] = Field(None, description="Time data becomes effective")
    revision_time: Optional[datetime] = Field(None, description="Time this version was revised")
    ingestion_time: Optional[datetime] = Field(None, description="Metadata-only ingestion timestamp")

    @field_validator("event_time", "observation_time", "publication_time",
                     "effective_time", "revision_time", "ingestion_time", mode="before")
    @classmethod
    def _validate_timezone_aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Reject naive datetimes and normalize to UTC."""
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError(
                f"Naive datetime is not allowed. "
                f"All PIT timestamps must be timezone-aware and UTC-normalized."
            )
        # Normalize to UTC
        return v.astimezone(UTC)

    def _temporal_fields(self) -> dict[str, Optional[datetime]]:
        """Return all temporal fields except ingestion_time (metadata-only)."""
        return {
            "event_time": self.event_time,
            "observation_time": self.observation_time,
            "publication_time": self.publication_time,
            "effective_time": self.effective_time,
            "revision_time": self.revision_time,
        }

    def temporal_hash_input(self) -> str:
        """Return deterministic serialization of temporal fields for hashing.

        Does NOT include ingestion_time per Phase 4A.1 rules.
        """
        parts = []
        for key in ["event_time", "observation_time", "publication_time",
                     "effective_time", "revision_time"]:
            val = getattr(self, key)
            if val is not None:
                parts.append(f"{key}={val.isoformat()}")
            else:
                parts.append(f"{key}=<NULL>")
        return "|".join(parts)

    def __str__(self) -> str:
        return (
            f"TemporalSemantics(event={self.event_time.isoformat()}, "
            f"obs={self.observation_time.isoformat()}, "
            f"pub={self.publication_time.isoformat() if self.publication_time else '<NULL>'}, "
            f"eff={self.effective_time.isoformat() if self.effective_time else '<NULL>'}, "
            f"rev={self.revision_time.isoformat() if self.revision_time else '<NULL>'})"
        )
