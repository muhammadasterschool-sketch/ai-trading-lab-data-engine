"""Phase 9 — Hermes AI research orchestration package (blueprint 5.35-5.41).

Agent contracts, deterministic model routing, communication, skills,
and the orchestrator. Zero network capability; zero execution
authority; structurally unavailable permissions.
"""

__version__ = "9.0.0"

from data_engine.hermes.providers import (
    ModelAbstractionError,
    ModelResponse,
    ModelProvider,
    DeterministicTestProvider,
    ModelRouter,
)
from data_engine.hermes.contracts import (
    AgentPermission,
    AgentContract,
    AgentContractError,
    AgentMessage,
    MessageLog,
    SkillDefinition,
    SkillExecutor,
)
from data_engine.hermes.orchestrator import (
    TaskAssignment,
    OrchestrationAuditEntry,
    HermesOrchestrator,
    HERMES_PREFIX,
)

__all__ = [
    "__version__",
    "ModelAbstractionError",
    "ModelResponse",
    "ModelProvider",
    "DeterministicTestProvider",
    "ModelRouter",
    "AgentPermission",
    "AgentContract",
    "AgentContractError",
    "AgentMessage",
    "MessageLog",
    "SkillDefinition",
    "SkillExecutor",
    "TaskAssignment",
    "OrchestrationAuditEntry",
    "HermesOrchestrator",
    "HERMES_PREFIX",
]
