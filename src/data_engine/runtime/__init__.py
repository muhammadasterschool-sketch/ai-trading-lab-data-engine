"""Authoritative paper-trading runtime package (pre-paper mandate).

The ONE orchestration path (mandate §24):

    DataFeed → DataValidator → PITGate → FeatureEngine →
    SequenceBuilder → PredictionEngine(Ensemble) → Calibration →
    Uncertainty → Regime → CrashRisk → PortfolioState →
    DecisionEngine → PositionSizer → TradePlan → RiskEngine →
    KillSwitch → OMS → PaperExecutionGateway → Fill →
    PositionState → Reconciliation → Ledgers → Memory → Monitoring

PAPER MODE ONLY. No broker integration, no live execution, no
production credentials, no autonomous capital allocation (mandate
§58/§59/§61). This package implements PAPER readiness machinery;
declaring PAPER_READY remains the exclusive verdict of
:class:`PaperReadinessGate` from objective evidence.
"""

from data_engine.runtime.identity import (
    RUNTIME_CONTRACT_VERSION,
    prefixed_hash,
)
from data_engine.runtime.contracts import (
    DecisionAction,
    Decision,
    EntryConstraints,
    ExitReason,
    ExitRecord,
    MemoryCategory,
    OrderLifecycle,
    PredictionArtifact,
    RejectedAlternative,
    RuntimeState,
    TradePlan,
    UncertaintyReport,
    freeze_number,
)
from data_engine.runtime.vocabulary import (
    VocabularyError,
    freeze_strategy_boundary,
    lifecycle_to_paper_status,
    paper_side_to_runtime,
    paper_status_to_lifecycle,
    runtime_side_to_paper,
    runtime_side_to_strategy,
    strategy_quantity_to_decimal,
    strategy_side_to_runtime,
)
from data_engine.runtime.sequence import (
    SequenceSpec,
    SequenceSet,
    Sequence,
    WalkForwardSplit,
    build_sequence_set,
    build_walk_forward_splits,
    train_validation_test_split,
)
from data_engine.runtime.models import (
    CalibrationArtifact,
    DeterministicBaseline,
    DeterministicEnsemble,
    EnsembleComposition,
    EnsemblePrediction,
    LSTMClassifier,
    RuntimeCalibrator,
    RuntimeModelArtifact,
    TransformerClassifier,
    WalkForwardReport,
    evaluate_walk_forward,
)
from data_engine.runtime.state import (
    EXECUTION_STATE_FIELDS,
    EXECUTION_STATE_SCHEMA_VERSION,
    ExecutionStateStore,
    HashChainJournal,
    StateStoreError,
    validate_execution_state,
)
from data_engine.runtime.ledgers import (
    LedgerEvent,
    LedgerFamily,
    LedgerError,
    LEDGER_NAMES,
)
from data_engine.runtime.pnl import (
    PnLEngine,
    PnlRecord,
    PositionState,
)
from data_engine.runtime.execution import (
    PaperExecutionAdapter,
    RuntimeFill,
    PAPER_MODE_STRUCTURAL_ISOLATION,
)
from data_engine.runtime.oms import (
    AMBIGUOUS_STATES,
    LIVE_STATES,
    OMS,
    OMSOrder,
    TRANSITIONS,
    AmbiguousOrderError,
    InvalidTransitionError,
    idempotent_order_id,
)
from data_engine.runtime.exits import ExitManager, ProtectionLevels
from data_engine.runtime.risk_gate import (
    MANDATORY_CHECKS,
    RiskAssessment,
    RiskCheckResult,
    RiskContext,
    RiskGate,
)
from data_engine.runtime.kill_switch import (
    CRITICAL_SCOPES,
    KillSwitchActive,
    KillSwitchManager,
    KillSwitchScope,
    ResetAuthorization,
    SwitchState,
)
from data_engine.runtime.reconciliation import (
    ReconciliationFailure,
    ReconciliationReport,
    RuntimeReconciliation,
)
from data_engine.runtime.memory import (
    TradingMemory,
    TradingMemoryRecord,
)
from data_engine.runtime.decision import (
    DecisionEngine,
    DecisionThresholds,
    MarketDataStatus,
)
from data_engine.runtime.trade_plan import (
    SizingConfig,
    TradePlanBuilder,
)
from data_engine.runtime.data_gate import (
    DataReadinessReport,
    DatasetReadinessRecord,
    QualityRejection,
    RealDataReadiness,
    validate_bars,
)
from data_engine.runtime.recovery import (
    RecoveryManager,
    RecoveryReport,
)
from data_engine.runtime.runtime import (
    BarOutcome,
    RuntimeConfig,
    TradingRuntime,
)
from data_engine.runtime.readiness import (
    GATE_NAMES,
    GateEvidence,
    PaperReadinessGate,
    ReadinessReport,
)
from data_engine.runtime.rl import (
    GovernedRLPolicy,
    RLAction,
    RLActionProposal,
    RLGovernanceError,
    RLObservation,
    RLPolicyConfig,
    propose_rl_action,
)
from data_engine.runtime.metrics import (
    COUNTER_NAMES,
    GAUGE_NAMES,
    MetricsError,
    RuntimeMetrics,
)

__all__ = [
    "RUNTIME_CONTRACT_VERSION",
    # contracts
    "DecisionAction", "Decision", "EntryConstraints", "ExitReason",
    "ExitRecord", "MemoryCategory", "OrderLifecycle",
    "PredictionArtifact", "RejectedAlternative", "RuntimeState",
    "TradePlan", "UncertaintyReport", "freeze_number",
    # vocabulary (RT-F6 bridge)
    "VocabularyError", "freeze_strategy_boundary",
    "lifecycle_to_paper_status", "paper_side_to_runtime",
    "paper_status_to_lifecycle", "runtime_side_to_paper",
    "runtime_side_to_strategy", "strategy_quantity_to_decimal",
    "strategy_side_to_runtime",
    # sequence engine
    "SequenceSpec", "SequenceSet", "Sequence", "WalkForwardSplit",
    "build_sequence_set", "build_walk_forward_splits",
    "train_validation_test_split",
    # models
    "CalibrationArtifact", "DeterministicBaseline", "DeterministicEnsemble",
    "EnsembleComposition", "EnsemblePrediction", "LSTMClassifier",
    "RuntimeCalibrator", "RuntimeModelArtifact", "TransformerClassifier",
    "WalkForwardReport", "evaluate_walk_forward",
    # persistence
    "ExecutionStateStore", "HashChainJournal", "StateStoreError",
    "EXECUTION_STATE_FIELDS", "EXECUTION_STATE_SCHEMA_VERSION",
    "validate_execution_state",
    # ledgers
    "LedgerEvent", "LedgerFamily", "LedgerError", "LEDGER_NAMES",
    # accounting
    "PnLEngine", "PnlRecord", "PositionState",
    # execution
    "PaperExecutionAdapter", "RuntimeFill",
    "PAPER_MODE_STRUCTURAL_ISOLATION",
    # OMS
    "AMBIGUOUS_STATES", "LIVE_STATES", "OMS", "OMSOrder", "TRANSITIONS",
    "AmbiguousOrderError", "InvalidTransitionError", "idempotent_order_id",
    # exits
    "ExitManager", "ProtectionLevels",
    # risk + kill switch
    "MANDATORY_CHECKS", "RiskAssessment", "RiskCheckResult",
    "RiskContext", "RiskGate",
    "CRITICAL_SCOPES", "KillSwitchActive", "KillSwitchManager",
    "KillSwitchScope", "ResetAuthorization", "SwitchState",
    # reconciliation
    "ReconciliationFailure", "ReconciliationReport",
    "RuntimeReconciliation",
    # memory
    "TradingMemory", "TradingMemoryRecord",
    # decision + plans
    "DecisionEngine", "DecisionThresholds", "MarketDataStatus",
    "SizingConfig", "TradePlanBuilder",
    # data gate
    "DataReadinessReport", "DatasetReadinessRecord", "QualityRejection",
    "RealDataReadiness", "validate_bars",
    # recovery + runtime + readiness
    "RecoveryManager", "RecoveryReport",
    "BarOutcome", "RuntimeConfig", "TradingRuntime",
    "GATE_NAMES", "GateEvidence", "PaperReadinessGate", "ReadinessReport",
    # governed RL advisor (mandate §28/§44)
    "GovernedRLPolicy", "RLAction", "RLActionProposal", "RLGovernanceError",
    "RLObservation", "RLPolicyConfig", "propose_rl_action",
    # runtime observability (mandate §26)
    "COUNTER_NAMES", "GAUGE_NAMES", "MetricsError", "RuntimeMetrics",
]
