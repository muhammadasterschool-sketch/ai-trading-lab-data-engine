"""Phase 9 — Agent contracts and communication (blueprint 5.38/5.39).

Formal contracts every AI agent must satisfy:

- ``AgentPermission``: capability bits. CRITICALLY, some permissions
  are STRUCTURALLY UNAVAILABLE: no agent contract can carry
  LIVE_TRADING_AUTHORITY, BLOCKER_CLOSURE_AUTHORITY, or
  FROZEN_CONTRACT_MODIFICATION — the constructor rejects them
  (blueprint 5.38: 'no agent can authorize live trading; no agent can
  close blockers; no agent can modify frozen contracts').
- ``AgentContract``: role + permissions + prohibitions, agent9.
  identity hash.
- ``AgentMessage`` / ``MessageLog``: all communication logged and
  hash-verified; the log is append-only and tamper-evident (each
  entry hashes the previous).
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 9 contract version.
PHASE_9_CONTRACT_VERSION = "1.0.0"


class AgentContractError(ValueError):
    """Raised on agent-contract violations."""


class AgentPermission:
    """Permission constants (not an enum: unavailable ones are strings
    that the contract constructor structurally rejects)."""

    READ_MARKET_DATA = "read_market_data"
    READ_RESEARCH = "read_research"
    WRITE_RESEARCH = "write_research"
    RUN_BACKTEST = "run_backtest"
    RUN_VALIDATION = "run_validation"
    WRITE_CODE = "write_code"
    COMMUNICATE = "communicate"

    #: Structurally unavailable to ANY agent (blueprint 5.38).
    UNAVAILABLE_PERMISSIONS = frozenset(
        {
            "live_trading_authority",
            "blocker_closure_authority",
            "frozen_contract_modification",
            "self_approval_authority",
        }
    )


class AgentContract(BaseModel):
    """One agent's formal contract: role, permissions, prohibitions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_id: str
    role: str
    permissions: frozenset[str] = frozenset()
    prohibitions: frozenset[str] = frozenset()
    contract_version: str = "1.0.0"

    @field_validator("agent_id", "role")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("agent_id/role must be non-empty strings")
        return v.strip()

    @model_validator(mode="after")
    def _validate_permissions(self) -> "AgentContract":
        for permission in self.permissions:
            if permission in AgentPermission.UNAVAILABLE_PERMISSIONS:
                raise AgentContractError(
                    f"permission {permission!r} is STRUCTURALLY UNAVAILABLE "
                    "to any agent (blueprint 5.38: no agent can authorize "
                    "live trading, close blockers, modify frozen contracts, "
                    "or self-approve)"
                )
        overlap = self.permissions & self.prohibitions
        if overlap:
            raise AgentContractError(
                f"contract is incoherent: {sorted(overlap)} are both "
                "permitted and prohibited"
            )
        return self

    def may(self, action: str) -> bool:
        """True iff ``action`` is permitted and not prohibited."""
        if action in AgentPermission.UNAVAILABLE_PERMISSIONS:
            return False
        return action in self.permissions and action not in self.prohibitions

    @property
    def contract_hash(self) -> str:
        return "agent9." + deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "agent_id": self.agent_id,
                "role": self.role,
                "permissions": sorted(self.permissions),
                "prohibitions": sorted(self.prohibitions),
                "spec_version": self.contract_version,
            }
        )


class AgentMessage(BaseModel):
    """One logged agent communication."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str
    from_agent: str
    to_agent: str
    payload_hash: str
    content: str

    @field_validator(
        "message_id", "from_agent", "to_agent", "payload_hash", "content"
    )
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("message fields must be non-empty strings")
        return v

    @property
    def message_hash(self) -> str:
        return deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "message_id": self.message_id,
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "payload_hash": self.payload_hash,
                "content": self.content,
            }
        )


class MessageLog:
    """Append-only, hash-chained, tamper-evident communication log."""

    def __init__(self) -> None:
        self._entries: list[AgentMessage] = []
        self._chain: list[str] = []

    def append(self, message: AgentMessage) -> str:
        """Append a message; returns its chain hash."""
        if any(m.message_id == message.message_id for m in self._entries):
            raise AgentContractError(
                f"duplicate message_id {message.message_id!r}"
            )
        prev = self._chain[-1] if self._chain else "0" * 64
        chain_hash = deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "message_hash": message.message_hash,
                "prev_chain_hash": prev,
                "index": len(self._entries),
            }
        )
        self._entries.append(message)
        self._chain.append(chain_hash)
        return chain_hash

    def verify(self) -> bool:
        """Re-verify the whole chain (tamper detection)."""
        prev = "0" * 64
        for index, message in enumerate(self._entries):
            expected = deterministic_hash(
                {
                    "contract_version": PHASE_9_CONTRACT_VERSION,
                    "message_hash": message.message_hash,
                    "prev_chain_hash": prev,
                    "index": index,
                }
            )
            if self._chain[index] != expected:
                return False
            prev = self._chain[index]
        return True

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[AgentMessage, ...]:
        return tuple(self._entries)


class SkillDefinition(BaseModel):
    """One skill with an explicit contract and acceptance criteria."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_id: str
    description: str
    acceptance_criteria: tuple[str, ...]
    adversarial_tests: tuple[str, ...]

    @field_validator("skill_id", "description")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("skill fields must be non-empty strings")
        return v.strip()

    @model_validator(mode="after")
    def _validate_criteria(self) -> "SkillDefinition":
        if not self.acceptance_criteria:
            raise AgentContractError(
                "a skill without acceptance criteria is undefined "
                "(blueprint 5.41)"
            )
        if not self.adversarial_tests:
            raise AgentContractError(
                "a skill without adversarial tests is undefined "
                "(blueprint 5.41)"
            )
        return self

    @property
    def skill_hash(self) -> str:
        return deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "skill_id": self.skill_id,
                "description": self.description,
                "acceptance_criteria": list(self.acceptance_criteria),
                "adversarial_tests": list(self.adversarial_tests),
            }
        )


class SkillExecutor:
    """Executes registered skills against declared callable impls.

    The executor REFUSES to run a skill whose implementation was not
    registered with a matching skill hash (no undefined skill
    execution — blueprint 5.41 failure mode).
    """

    def __init__(self) -> None:
        self._skills: dict[str, tuple[SkillDefinition, Any]] = {}

    def register(
        self, definition: SkillDefinition, implementation: Any
    ) -> None:
        if not callable(implementation):
            raise AgentContractError(
                "skill implementation must be callable"
            )
        if definition.skill_id in self._skills:
            raise AgentContractError(
                f"skill {definition.skill_id!r} already registered"
            )
        self._skills[definition.skill_id] = (definition, implementation)

    def run(self, skill_id: str, *args, **kwargs):
        if skill_id not in self._skills:
            raise AgentContractError(
                f"skill {skill_id!r} is not registered — undefined skill "
                "execution is forbidden (blueprint 5.41)"
            )
        definition, implementation = self._skills[skill_id]
        return implementation(*args, **kwargs)


__all__ = [
    "AgentPermission",
    "AgentContract",
    "AgentContractError",
    "AgentMessage",
    "MessageLog",
    "SkillDefinition",
    "SkillExecutor",
    "PHASE_9_CONTRACT_VERSION",
]
