"""Phase 9 — Hermes orchestration (blueprint 5.36).

Hermes coordinates but does NOT execute:

- ``TaskAssignment``: a dispatch record — an instruction for an agent
  to perform work under its contract. Dispatch produces assignments
  and audit records ONLY; it never mutates trading state, never
  touches money, never closes blockers.
- ``HermesOrchestrator``: registers agent contracts, dispatches tasks
  (checking the agent's contract permits the task's required
  permission), and maintains a hash-chained orchestration audit log.

Invariants (blueprint 5.36): all orchestration actions audited;
governance enforced (a task requiring an unavailable permission is
refused at dispatch, not discovered later); Hermes has no execution
authority of its own — it returns assignments, side effects belong
to the (test-double) executors downstream.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.hermes.contracts import (
    AgentContract,
    AgentContractError,
    AgentPermission,
    PHASE_9_CONTRACT_VERSION,
)

#: Phase 9 orchestrator prefix.
HERMES_PREFIX = "hermes9."


class TaskAssignment(BaseModel):
    """One dispatch: agent + task kind + required permission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    agent_id: str
    task_kind: str
    required_permission: str
    description: str

    @field_validator("task_id", "agent_id", "task_kind", "description")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("task fields must be non-empty strings")
        return v.strip()

    @field_validator("required_permission")
    @classmethod
    def _validate_permission(cls, v: str) -> str:
        if v in AgentPermission.UNAVAILABLE_PERMISSIONS:
            raise AgentContractError(
                f"task requires unavailable permission {v!r} — no task "
                "may demand an authority structurally denied to agents"
            )
        return v

    @property
    def assignment_hash(self) -> str:
        return HERMES_PREFIX + deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "task_id": self.task_id,
                "agent_id": self.agent_id,
                "task_kind": self.task_kind,
                "required_permission": self.required_permission,
                "description": self.description,
            }
        )


class OrchestrationAuditEntry(BaseModel):
    """One audited orchestration action (hash-chained by the log)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str  # "dispatch" | "reject"
    task_id: str
    agent_id: str
    detail: str
    entry_hash: str

    @field_validator("action", "task_id", "agent_id", "detail", "entry_hash")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("audit fields must be non-empty strings")
        return v


class HermesOrchestrator:
    """Coordinates agents; never executes; audits everything."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentContract] = {}
        self._audit: list[OrchestrationAuditEntry] = []

    def register_agent(self, contract: AgentContract) -> None:
        if contract.agent_id in self._agents:
            raise AgentContractError(
                f"agent {contract.agent_id!r} already registered"
            )
        self._agents[contract.agent_id] = contract

    def dispatch(self, assignment: TaskAssignment) -> OrchestrationAuditEntry:
        """Dispatch a task if the agent's contract permits it.

        Returns the audit entry (action=dispatch) on success; returns
        the audit entry (action=reject) when the agent is unknown or
        lacks the required permission. Rejections are AUDITED, not
        raised — orchestration records the refusal and continues
        (governance is enforced by the record, and by downstream
        executors refusing unaudited work).
        """
        agent = self._agents.get(assignment.agent_id)
        if agent is None:
            entry = self._make_entry(
                "reject", assignment,
                f"unknown agent {assignment.agent_id!r}",
            )
            self._audit.append(entry)
            return entry
        if not agent.may(assignment.required_permission):
            entry = self._make_entry(
                "reject", assignment,
                f"agent {assignment.agent_id!r} lacks permission "
                f"{assignment.required_permission!r}",
            )
            self._audit.append(entry)
            return entry
        entry = self._make_entry(
            "dispatch", assignment,
            f"task {assignment.task_kind!r} dispatched to "
            f"{assignment.agent_id!r} under permission "
            f"{assignment.required_permission!r}",
        )
        self._audit.append(entry)
        return entry

    def _make_entry(
        self, action: str, assignment: TaskAssignment, detail: str
    ) -> OrchestrationAuditEntry:
        prev = self._audit[-1].entry_hash if self._audit else "0" * 64
        entry_hash = deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "action": action,
                "task_id": assignment.task_id,
                "agent_id": assignment.agent_id,
                "detail": detail,
                "prev_entry_hash": prev,
                "index": len(self._audit),
            }
        )
        return OrchestrationAuditEntry(
            action=action,
            task_id=assignment.task_id,
            agent_id=assignment.agent_id,
            detail=detail,
            entry_hash=entry_hash,
        )

    def verify_audit_chain(self) -> bool:
        """Re-verify the audit log chain (tamper detection)."""
        prev = "0" * 64
        for index, entry in enumerate(self._audit):
            expected = deterministic_hash(
                {
                    "contract_version": PHASE_9_CONTRACT_VERSION,
                    "action": entry.action,
                    "task_id": entry.task_id,
                    "agent_id": entry.agent_id,
                    "detail": entry.detail,
                    "prev_entry_hash": prev,
                    "index": index,
                }
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    @property
    def audit_log(self) -> tuple[OrchestrationAuditEntry, ...]:
        return tuple(self._audit)

    @property
    def agents(self) -> tuple[str, ...]:
        return tuple(sorted(self._agents))


__all__ = [
    "TaskAssignment",
    "OrchestrationAuditEntry",
    "HermesOrchestrator",
    "HERMES_PREFIX",
]
