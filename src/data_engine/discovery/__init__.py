"""Phase 12 — Strategy Discovery and Execution Eligibility.

Blueprint 5.20 (Strategy Generation/Discovery) + master-mandate Phase 11
(strategy discovery) and Phase 15 (execution eligibility), built on the
FROZEN Phase 3 strategy representation.

Governance model:

- Candidates are GENERATED deterministically from bounded declarative
  grids (no RNG without a structural seed input, no wall clock, no
  network, no code execution).
- Every candidate carries the mandate's full metadata set:
  StrategyIdentity, specification, parameter schema, feature/data
  dependencies, risk assumptions, execution assumptions, and
  validation requirements.
- No generated strategy may bypass governance: the registry exposes
  only VALIDATED candidates, REJECTED candidates are preserved as
  evidence, and promotion to backtesting requires the validation
  requirements to pass.
- A strategy is allowed to fail: invalid conditions produce a REJECTED
  candidate (recorded with reason), never a crash and never a silent
  drop.
- NO TRADE is a first-class outcome of signal evaluation, and the
  execution-eligibility chain returns NO TRADE on any failed stage.
- This layer NEVER authorizes execution. It terminates at
  EXECUTION_ELIGIBLE; live authorization belongs exclusively to
  ``data_engine.paper.evaluation.LiveAuthorizationGate`` which DENIES
  by default (blueprint 5.59 — NEVER authorized by this codebase).
"""

from data_engine.discovery.models import (
    CANDIDATE_HASH_PREFIX,
    DISCOVERY_CONTRACT_VERSION,
    CandidateStatus,
    DataDependencies,
    DiscoveryProvenance,
    ExecutionAssumptions,
    ParameterField,
    ParameterSchema,
    RiskAssumptions,
    StrategyCandidate,
    ValidationRequirements,
)
from data_engine.discovery.generators import (
    RuleTemplate,
    RuleBasedGenerator,
)
from data_engine.discovery.evaluation import (
    CandidateEvaluator,
    CandidateValidator,
    SignalAction,
    SignalDecision,
)
from data_engine.discovery.registry import (
    DiscoveryRegistry,
    DiscoveryRegistryError,
)
from data_engine.discovery.eligibility import (
    ELIGIBILITY_HASH_PREFIX,
    EligibilityDecision,
    EligibilityStage,
    EligibilityStageResult,
    ExecutionEligibility,
)

__all__ = [
    "CANDIDATE_HASH_PREFIX",
    "DISCOVERY_CONTRACT_VERSION",
    "CandidateStatus",
    "DataDependencies",
    "DiscoveryProvenance",
    "ExecutionAssumptions",
    "ParameterField",
    "ParameterSchema",
    "RiskAssumptions",
    "StrategyCandidate",
    "ValidationRequirements",
    "RuleTemplate",
    "RuleBasedGenerator",
    "CandidateEvaluator",
    "CandidateValidator",
    "SignalAction",
    "SignalDecision",
    "DiscoveryRegistry",
    "DiscoveryRegistryError",
    "ELIGIBILITY_HASH_PREFIX",
    "EligibilityDecision",
    "EligibilityStage",
    "EligibilityStageResult",
    "ExecutionEligibility",
]
