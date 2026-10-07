"""Phase 4A.4 — Research governance package (blueprint 5.15)."""

__version__ = "4.4.0"

from data_engine.research.governance import (
    PrincipalKind,
    Principal,
    ApprovalStatus,
    Citation,
    ApprovalMetadata,
    ResearchContract,
    ResearchRegistry,
    ResearchRegistryError,
    RESEARCH_PREFIX,
    APPROVAL_PREFIX,
    PHASE_4A4_CONTRACT_VERSION,
)

__all__ = [
    "__version__",
    "PrincipalKind",
    "Principal",
    "ApprovalStatus",
    "Citation",
    "ApprovalMetadata",
    "ResearchContract",
    "ResearchRegistry",
    "ResearchRegistryError",
    "RESEARCH_PREFIX",
    "APPROVAL_PREFIX",
    "PHASE_4A4_CONTRACT_VERSION",
]
