"""Phase 10 — Production infrastructure package (blueprint 5.47-5.50).

Reproducibility verification, observability (metrics/logs), monitoring
(alerts/health checks), and failure/recovery (checkpoints).
"""

__version__ = "10.0.0"

from data_engine.infra.observability import (
    ReproducibilityError,
    ReproducibilityResult,
    DeterministicRunner,
    ReproducibilityVerifier,
    MetricsRegistry,
    LogEntry,
    StructuredLog,
    HealthStatus,
    HealthCheck,
    Alert,
    AlertManager,
    Monitor,
    Checkpoint,
    CheckpointManager,
    RecoveryManager,
    PHASE_10_CONTRACT_VERSION,
)

__all__ = [
    "__version__",
    "ReproducibilityError",
    "ReproducibilityResult",
    "DeterministicRunner",
    "ReproducibilityVerifier",
    "MetricsRegistry",
    "LogEntry",
    "StructuredLog",
    "HealthStatus",
    "HealthCheck",
    "Alert",
    "AlertManager",
    "Monitor",
    "Checkpoint",
    "CheckpointManager",
    "RecoveryManager",
    "PHASE_10_CONTRACT_VERSION",
]
