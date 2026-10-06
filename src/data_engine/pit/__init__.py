"""Phase 4A.1 — Temporal Foundation for Point-in-Time (PIT) data.

This module provides the temporal semantic foundation for Point-in-Time
data handling in the AI Trading Lab Data Engine. It defines:

- Temporal semantic model (event_time, observation_time, publication_time,
  effective_time, revision_time, ingestion_time)
- TemporalDataType enum (OHLCV, ECONOMIC, NEWS, DERIVED)
- Declarative availability policy definitions
- TemporalContract for PIT data validation
- Canonical serialization utilities
- Deterministic SHA-256 hashing abstraction

Key invariant: ingestion_time is metadata only and must NOT participate
in PIT eligibility, availability calculations, research identity hashes,
or PIT hashes.

Phase 4A depends on Phase 3, not the reverse. This module does NOT
import any Phase 3 modules.
"""

__version__ = "4.1.0"

from data_engine.pit.temporal import (
    TemporalDataType,
    TemporalSemantics,
)
from data_engine.pit.availability import (
    AvailabilityPolicy,
    PublicationControlledAvailability,
    RevisionAwareAvailability,
)
from data_engine.pit.contract import TemporalContract
from data_engine.pit.serialization import canonical_serialize
from data_engine.pit.hashing import deterministic_hash

__all__ = [
    "TemporalDataType",
    "TemporalSemantics",
    "AvailabilityPolicy",
    "PublicationControlledAvailability",
    "RevisionAwareAvailability",
    "TemporalContract",
    "canonical_serialize",
    "deterministic_hash",
    "__version__",
]
