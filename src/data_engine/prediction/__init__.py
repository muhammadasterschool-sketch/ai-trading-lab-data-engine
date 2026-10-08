"""AI Trading Lab — Prediction & Crash Intelligence layer.

Governed prediction architecture implementing the "Prediction & Crash
Intelligence Master Architecture + Implementation Mandate" (58 sections):

- probabilistic crash-risk estimates — NEVER deterministic crash claims
- PIT-correct features, labels, regimes (no look-ahead, no revision or
  survivorship leakage — structural, tested)
- baseline-first models with justification gates (MODEL_NOT_JUSTIFIED)
- calibration, uncertainty, drift monitoring, evidence scoring
- model registry with human-only approvals and full lifecycle
- append-only, hash-chained prediction outcome ledger
- no-prediction states with machine-readable reasons
- scenario engine (scenarios are NOT forecasts), systemic-risk measures
- advisory-only risk integration (risk engine stays authoritative)

Layer map:
- ``contracts``      status vocabulary, control states, block reasons
- ``identity``       deterministic pred*-prefixed identities (H-1 safe)
- ``provenance``     full §15 provenance records
- ``data_access``    PIT candle views, revision defense, universe, policy
- ``features``       slice-then-compute risk features
- ``labels``         configurable crash labels + boundary proofs
- ``regimes``        deterministic regime engine + transition events
- ``stress``         market-stress classification
- ``models``         baselines, logistic model, justification gate
- ``calibration``    Brier/log-loss/reliability/ECE, Platt scaling
- ``uncertainty``    probability bands, empirical/ensemble intervals
- ``drift``          PSI drift states + mandated actions
- ``evidence_score`` explicit 11-dimension evidence composite
- ``registry``       model lifecycle registry (human-only approval)
- ``ledger``         append-only outcome ledger (hash-chained)
- ``gates``          no-prediction gate evaluation (fail closed)
- ``evaluation``     chronological splits, walk-forward, warning quality
- ``crash``          crash-risk assessment contract
- ``estimator``      governed end-to-end orchestrator
- ``scenarios``      scenario engine (not forecasts)
- ``systemic``       cross-asset correlation / contagion measures
- ``risk_integration`` advisory prediction -> risk interface
- ``microstructure`` explicit availability declaration

Governance: prediction NEVER executes trades, NEVER bypasses hard risk
limits or the kill switch, and NEVER modifies frozen Phase 3 contracts.
LIVE TRADING AUTHORIZATION: NOT GRANTED.
"""

from data_engine.prediction.contracts import (
    BlockReason,
    CalibrationStatus,
    DriftState,
    InsufficiencyState,
    ModelLifecycleState,
    PREDICTION_CONTRACT_VERSION,
    PredictionContractError,
    PredictionControlState,
    RegimeState,
    RiskLevel,
    StressState,
)
from data_engine.prediction.identity import (
    EnvironmentFingerprint,
    capture_environment,
    prediction_identity,
    prefixed_hash,
)
from data_engine.prediction.provenance import PredictionProvenance
from data_engine.prediction.data_access import (
    HistoryPolicyReading,
    PitCandleView,
    PredictionDataError,
    evaluate_history_policy,
    pit_candle_view,
    universe_at,
)
from data_engine.prediction.features import (
    FEATURE_SCHEMA,
    FeatureRow,
    build_feature_rows,
    feature_data_hash,
    feature_set_id,
)
from data_engine.prediction.labels import (
    CrashLabelDefinition,
    CrisisSampleReading,
    LabeledPoint,
    assert_label_feature_boundary,
    compute_crash_labels,
    crisis_sample_status,
    forward_max_drawdown,
)
from data_engine.prediction.regimes import (
    RegimeEngine,
    RegimeFeatures,
    RegimeTransitionEvent,
)
from data_engine.prediction.stress import (
    MarketStressReading,
    classify_market_stress,
)
from data_engine.prediction.models import (
    BaseRateBaseline,
    LogisticCrashModel,
    ModelArtifact,
    ModelJustification,
    NaivePersistenceBaseline,
    PredictionModelError,
    RandomClassifierBaseline,
    RegimeConditionalBaseline,
    RollingBaseRateBaseline,
    bootstrap_improvement_ci,
    justify_model,
)
from data_engine.prediction.calibration import (
    CalibrationReport,
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
    log_loss,
    reliability_curve,
)
from data_engine.prediction.uncertainty import (
    UncertaintyBand,
    ensemble_band,
    empirical_interval,
    is_uncertain,
    probability_band,
)
from data_engine.prediction.drift import (
    DRIFT_ACTIONS,
    DriftReport,
    classify_drift,
    data_source_drift,
    drift_action,
    drift_report,
    population_stability_index,
)
from data_engine.prediction.evidence_score import (
    EvidenceAssessment,
    evidence_assessment,
)
from data_engine.prediction.registry import (
    ApprovalDecision,
    ApprovalRecord,
    ModelRecord,
    PredictionModelRegistry,
    RegistryError,
)
from data_engine.prediction.ledger import (
    LedgerEntry,
    LedgerSummary,
    OutcomeRecord,
    PredictionOutcomeLedger,
)
from data_engine.prediction.gates import (
    GateCheck,
    PredictionGateInput,
    PredictionGateResult,
    evaluate_prediction_gates,
)
from data_engine.prediction.evaluation import (
    ChronologicalSplit,
    CrashWarningQuality,
    PredictionOutcomePair,
    chronological_partitions,
    crash_warning_quality,
    evaluate_walk_forward,
)
from data_engine.prediction.crash import (
    DEFAULT_RISK_THRESHOLDS,
    CrashRiskAssessment,
    RiskThresholds,
    blocked_assessment,
    classify_risk_level,
    uncertain_assessment,
)
from data_engine.prediction.estimator import (
    CrashRiskEstimator,
    EstimatorConfig,
)
from data_engine.prediction.scenarios import (
    SCENARIO_KINDS,
    ScenarioDefinition,
    ScenarioEngine,
    ScenarioResult,
)
from data_engine.prediction.systemic import (
    SystemicRiskReading,
    average_correlation,
    correlation_matrix,
    systemic_risk_reading,
)
from data_engine.prediction.risk_integration import (
    LEVEL_SIZING,
    PredictionRiskDecision,
    prediction_risk_decision,
)
from data_engine.prediction.microstructure import (
    MICROSTRUCTURE_UNAVAILABLE,
    MicrostructureAvailability,
    microstructure_availability,
)
from data_engine.prediction.datasets import (
    DatasetManifest,
    DatasetState,
    DatasetVerificationReport,
    IngestionManifest,
    dataset_content_hash,
    synthetic_dataset_manifest,
    verify_dataset_manifest,
)
from data_engine.prediction.quality_gates import (
    DataQualityReport,
    QualityGateFinding,
    QualityGateID,
    validate_ohlcv,
)
from data_engine.prediction.source_registry import (
    DataSourceRecord,
    DataSourceRegistry,
    SourceApprovalDecision,
    SourceVerificationStatus,
    candidate_source_matrix,
)
from data_engine.prediction.artifact_verification import (
    ArtifactVerificationReport,
    verify_input_snapshot,
    verify_model_artifact,
)
from data_engine.prediction.event_evaluation import (
    CrashEventEpisode,
    CrashEventEvaluation,
    EventEvaluationConfig,
    RegimeConditionedMetrics,
    evaluate_by_split,
    evaluate_crash_events,
    extract_crash_events,
)
from data_engine.prediction.benchmark import (
    BenchmarkProtocol,
    BenchmarkResult,
    ModelEvaluationEntry,
    SplitManifest,
    blocked_benchmark,
    run_prediction_benchmark,
)
from data_engine.prediction.crash import (
    RISK_STATE_VOCABULARY_MAP,
    crash_warning_state,
)
from data_engine.prediction.redteam import (
    AttackVerdict,
    RedTeamAttack,
    RedTeamMatrix,
    run_redteam_matrix,
)

__all__ = [
    # contracts
    "BlockReason", "CalibrationStatus", "DriftState", "InsufficiencyState",
    "ModelLifecycleState", "PREDICTION_CONTRACT_VERSION",
    "PredictionContractError", "PredictionControlState", "RegimeState",
    "RiskLevel", "StressState",
    # identity / provenance
    "EnvironmentFingerprint", "capture_environment",
    "prediction_identity", "prefixed_hash", "PredictionProvenance",
    # data access
    "HistoryPolicyReading", "PitCandleView", "PredictionDataError",
    "evaluate_history_policy", "pit_candle_view", "universe_at",
    # features / labels
    "FEATURE_SCHEMA", "FeatureRow", "build_feature_rows",
    "feature_data_hash", "feature_set_id",
    "CrashLabelDefinition", "CrisisSampleReading", "LabeledPoint",
    "assert_label_feature_boundary", "compute_crash_labels",
    "crisis_sample_status", "forward_max_drawdown",
    # regimes / stress
    "RegimeEngine", "RegimeFeatures", "RegimeTransitionEvent",
    "MarketStressReading", "classify_market_stress",
    # models
    "BaseRateBaseline", "LogisticCrashModel", "ModelArtifact",
    "ModelJustification", "NaivePersistenceBaseline",
    "PredictionModelError", "RandomClassifierBaseline",
    "RegimeConditionalBaseline", "RollingBaseRateBaseline",
    "bootstrap_improvement_ci", "justify_model",
    # calibration / uncertainty
    "CalibrationReport", "PlattCalibrator", "brier_score",
    "expected_calibration_error", "log_loss", "reliability_curve",
    "UncertaintyBand", "ensemble_band", "empirical_interval",
    "is_uncertain", "probability_band",
    # drift / evidence
    "DRIFT_ACTIONS", "DriftReport", "classify_drift", "data_source_drift",
    "drift_action", "drift_report", "population_stability_index",
    "EvidenceAssessment", "evidence_assessment",
    # registry / ledger / gates
    "ApprovalDecision", "ApprovalRecord", "ModelRecord",
    "PredictionModelRegistry", "RegistryError",
    "LedgerEntry", "LedgerSummary", "OutcomeRecord",
    "PredictionOutcomeLedger",
    "GateCheck", "PredictionGateInput", "PredictionGateResult",
    "evaluate_prediction_gates",
    # evaluation / crash / estimator
    "ChronologicalSplit", "CrashWarningQuality",
    "PredictionOutcomePair", "chronological_partitions",
    "crash_warning_quality", "evaluate_walk_forward",
    "DEFAULT_RISK_THRESHOLDS", "CrashRiskAssessment", "RiskThresholds",
    "blocked_assessment", "classify_risk_level", "uncertain_assessment",
    "CrashRiskEstimator", "EstimatorConfig",
    # scenarios / systemic / risk / microstructure
    "SCENARIO_KINDS", "ScenarioDefinition", "ScenarioEngine",
    "ScenarioResult",
    "SystemicRiskReading", "average_correlation", "correlation_matrix",
    "systemic_risk_reading",
    "LEVEL_SIZING", "PredictionRiskDecision", "prediction_risk_decision",
    "MICROSTRUCTURE_UNAVAILABLE", "MicrostructureAvailability",
    "microstructure_availability",
    # datasets / quality gates / source registry (closure mandate)
    "DatasetManifest", "DatasetState", "DatasetVerificationReport",
    "IngestionManifest", "dataset_content_hash",
    "synthetic_dataset_manifest", "verify_dataset_manifest",
    "DataQualityReport", "QualityGateFinding", "QualityGateID",
    "validate_ohlcv",
    "DataSourceRecord", "DataSourceRegistry",
    "SourceApprovalDecision", "SourceVerificationStatus",
    "candidate_source_matrix",
    # artifact verification (PRED-F3)
    "ArtifactVerificationReport", "verify_input_snapshot",
    "verify_model_artifact",
    # crash-event evaluation (§8)
    "CrashEventEpisode", "CrashEventEvaluation",
    "EventEvaluationConfig", "RegimeConditionedMetrics",
    "evaluate_by_split", "evaluate_crash_events",
    "extract_crash_events",
    # benchmark harness (PRED-F1)
    "BenchmarkProtocol", "BenchmarkResult", "ModelEvaluationEntry",
    "SplitManifest", "blocked_benchmark", "run_prediction_benchmark",
    # crash completion (§7)
    "RISK_STATE_VOCABULARY_MAP", "crash_warning_state",
    # red-team matrix (PRED-F2)
    "AttackVerdict", "RedTeamAttack", "RedTeamMatrix",
    "run_redteam_matrix",
]
