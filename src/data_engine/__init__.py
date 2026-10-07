"""AI Trading Lab — Data Engine.

Production-grade deterministic market-data engine.
Provides canonical schemas, validation, provenance, and data-quality
safeguards for all downstream research, quant, and backtesting components.

Phase map (post 4A.1 remediation, phases 4A.2 through graduation):
- ``data_engine.pit``          4A.1  temporal/PIT foundation
- ``data_engine.actions``      4A.2  corporate actions, universe, calendar
- ``data_engine.derivatives``  4A.3  futures, rollover, continuous series
- ``data_engine.research``     4A.4  research governance
- ``data_engine.experiment_registry``  5  experiment registry
- ``data_engine.quant``        2/6   quant engine + feature pipeline
- ``data_engine.research_validation``  7  bias/stats/walk-forward/robustness
- ``data_engine.risk``         8     risk engine, exposure, portfolio
- ``data_engine.hermes``       9     AI orchestration (deterministic core)
- ``data_engine.infra``        10    reproducibility, observability, recovery
- ``data_engine.paper``        11    paper trading + evaluation/graduation
                                 and the live-authorization boundary
                                 (NEVER authorized by this codebase)

This module does NOT implement trading strategies and does NOT determine
whether any strategy is profitable.
"""

__version__ = "0.2.0"

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

# Phase 4A.1+ subsystem facade imports (lazy-safe: pure modules, no
# circularity — every package imports only from pit/ and stdlib).
from data_engine.pit import (
    TemporalSemantics,
    TemporalContract,
    canonical_serialize,
    identity_hash,
    PitSidecar,
    RevisionChain,
    PitView,
    PitViewBuilder,
    ExperimentIdentity,
)
from data_engine.actions import (
    CorporateActionType,
    SplitAction,
    DividendAction,
    SymbolChangeAction,
    DelistingAction,
    AdjustmentChain,
    PointInTimeUniverse,
    TradingCalendar,
)
from data_engine.derivatives import (
    FuturesContract,
    RolloverPolicy,
    roll_detection,
    ContinuousSeries,
)
from data_engine.research import (
    ResearchContract,
    ApprovalMetadata,
    ResearchRegistry,
)
from data_engine.experiment_registry import (
    ExperimentRegistry,
    ReproducibilityLog,
)
from data_engine.quant.features import (
    FeatureSpec,
    FeaturePipeline,
)
from data_engine.research_validation import (
    BiasDetector,
    StatisticalValidator,
    WalkForwardValidator,
    build_walk_forward_plan,
    robustness_report,
)
from data_engine.risk import (
    RiskLimits,
    RiskEngine,
    ExposureManager,
    PortfolioConstructor,
)
from data_engine.hermes import (
    AgentContract,
    ModelRouter,
    HermesOrchestrator,
)
from data_engine.infra import (
    ReproducibilityVerifier,
    MetricsRegistry,
    Monitor,
    CheckpointManager,
)
from data_engine.paper import (
    PaperOrder,
    ExecutionSimulator,
    PaperOrderGateway,
    ReconciliationEngine,
)
from data_engine.paper.evaluation import (
    EvaluationFramework,
    HumanAuthorizationRegistry,
    GraduationEvaluator,
    LiveAuthorizationGate,
)

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
