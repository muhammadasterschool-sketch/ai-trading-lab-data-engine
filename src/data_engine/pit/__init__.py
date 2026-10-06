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
    AvailabilityRuleType,
    PublicationControlledAvailability,
    RevisionAwareAvailability,
)
from data_engine.pit.contract import TemporalContract
from data_engine.pit.serialization import canonical_serialize
from data_engine.pit.hashing import (
    deterministic_hash,
    identity_hash,
    eligibility_hash,
    PHASE4_IDENTITY_CONTRACT_VERSION,
)
from data_engine.pit.sidecar import PitSidecar, LegacyClassification
from data_engine.pit.revision import RevisionChain, RevisionEntry
from data_engine.pit.tiebreaker import TieBreakerPolicy, AmbiguousTieError
from data_engine.pit.primitives import (
    InstrumentIdentity,
    InstrumentSpecification,
    Venue,
    DataSource,
    SymbolMapping,
    CalendarRef,
    validate_specification_intervals,
)
from data_engine.pit.view import (
    PitView,
    PitViewBuilder,
    PitViewValidator,
    ViewValidationResult,
    ValidationCheck,
    ExcludedRecord,
    dataset_content_hash,
)
from data_engine.pit.experiment import (
    ExperimentIdentity,
    PitExperimentConfig,
    LegacyPolicy,
)

__all__ = [
    "TemporalDataType",
    "TemporalSemantics",
    "AvailabilityPolicy",
    "AvailabilityRuleType",
    "PublicationControlledAvailability",
    "RevisionAwareAvailability",
    "TemporalContract",
    "canonical_serialize",
    "deterministic_hash",
    "identity_hash",
    "eligibility_hash",
    "PHASE4_IDENTITY_CONTRACT_VERSION",
    "PitSidecar",
    "LegacyClassification",
    "RevisionChain",
    "RevisionEntry",
    "TieBreakerPolicy",
    "AmbiguousTieError",
    "InstrumentIdentity",
    "InstrumentSpecification",
    "Venue",
    "DataSource",
    "SymbolMapping",
    "CalendarRef",
    "validate_specification_intervals",
    "PitView",
    "PitViewBuilder",
    "PitViewValidator",
    "ViewValidationResult",
    "ValidationCheck",
    "ExcludedRecord",
    "dataset_content_hash",
    "ExperimentIdentity",
    "PitExperimentConfig",
    "LegacyPolicy",
    "__version__",
]
