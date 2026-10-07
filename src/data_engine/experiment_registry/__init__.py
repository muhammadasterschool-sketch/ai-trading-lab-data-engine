"""Phase 5 — Experiment registry package (blueprint 5.16)."""

__version__ = "5.0.0"

from data_engine.experiment_registry.registry import (
    VerificationStatus,
    ExperimentRegistryEntry,
    ReproducibilityRun,
    ReproducibilityLog,
    ExperimentRegistry,
    ExperimentRegistryError,
    EXPERIMENT_REGISTRY_PREFIX,
    REPRODUCIBILITY_PREFIX,
    PHASE_5_CONTRACT_VERSION,
)

__all__ = [
    "__version__",
    "VerificationStatus",
    "ExperimentRegistryEntry",
    "ReproducibilityRun",
    "ReproducibilityLog",
    "ExperimentRegistry",
    "ExperimentRegistryError",
    "EXPERIMENT_REGISTRY_PREFIX",
    "REPRODUCIBILITY_PREFIX",
    "PHASE_5_CONTRACT_VERSION",
]
