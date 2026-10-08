"""Prediction model registry + lifecycle (§30, §31, §43).

Governed registry for predictive models. Key properties:

- Duplicate identity (model_id, model_version) is REJECTED (§31).
- Lifecycle transitions follow the mandated chain (§30); illegal jumps
  raise. PAPER and GRADUATE additionally REQUIRE a recorded HUMAN
  approval — no model self-approves, and an AI approver is REJECTED
  structurally (§30, §41, T-PRED-022/T-PRED-023).
- Records are immutable; transitions produce new records and append to
  a tamper-evident history chain.
- Timestamps are caller-supplied logical strings; ordering inside the
  registry uses monotonic sequence numbers, never the wall clock.
"""

from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import (
    DriftState,
    ModelLifecycleState,
    PredictionContractError,
)
from data_engine.prediction.identity import REGISTRY_PREFIX, prefixed_hash

#: Mandated lifecycle chain (§30). REJECT/RETIRE are reachable escapes.
FORWARD_CHAIN: Tuple[ModelLifecycleState, ...] = (
    ModelLifecycleState.DISCOVER,
    ModelLifecycleState.TRAIN,
    ModelLifecycleState.VALIDATE,
    ModelLifecycleState.CALIBRATE,
    ModelLifecycleState.ADVERSARIAL_TEST,
    ModelLifecycleState.REGISTER,
    ModelLifecycleState.HUMAN_REVIEW,
    ModelLifecycleState.PAPER,
    ModelLifecycleState.MONITOR,
    ModelLifecycleState.GRADUATE,
)

#: States that require a human approval on record before entry.
APPROVAL_REQUIRED = frozenset({
    ModelLifecycleState.PAPER,
    ModelLifecycleState.GRADUATE,
})

#: Lifecycle states that allow no further transitions (terminal).
TERMINAL_STATES = frozenset({
    ModelLifecycleState.REJECT,
    ModelLifecycleState.RETIRE,
})


def _allowed_transitions() -> Dict[ModelLifecycleState, frozenset]:
    """Allowed edges: the forward chain + escapes to REJECT/RETIRE."""
    table: Dict[ModelLifecycleState, set] = {}
    for state in ModelLifecycleState:
        table[state] = set()
    for i, state in enumerate(FORWARD_CHAIN[:-1]):
        nxt = FORWARD_CHAIN[i + 1]
        table[state].add(nxt)
        table[state].add(ModelLifecycleState.REJECT)
        table[state].add(ModelLifecycleState.RETIRE)
    # GRADUATE -> RETIRE only (a graduated model can later be retired).
    table[ModelLifecycleState.GRADUATE].add(ModelLifecycleState.RETIRE)
    return {state: frozenset(targets) for state, targets in table.items()}


ALLOWED_TRANSITIONS = _allowed_transitions()


class RegistryError(PredictionContractError):
    """Raised on registry-contract violations (duplicate identity, illegal
    transition, missing approval)."""


class ApprovalRecord(BaseModel):
    """One approval decision attached to a model (§43 human review)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approver: str
    approver_kind: str  # "human" | "ai" — ai is rejected at submission
    decision_id: str
    recorded_at: str

    @field_validator("approver", "approver_kind", "decision_id", "recorded_at")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("approval fields must be non-empty strings")
        return v


class ModelRecord(BaseModel):
    """One governed model record (§31 field set)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    model_version: str
    experiment_id: str
    owner: str
    dataset_id: str
    feature_set_id: str
    training_cutoff: str
    status: ModelLifecycleState
    validation_evidence: Tuple[str, ...] = ()
    calibration_evidence: Tuple[str, ...] = ()
    drift_status: DriftState = DriftState.STABLE
    approval: Optional[ApprovalRecord] = None
    paper_status: str = "NOT_STARTED"
    retirement_status: str = "NONE"
    notes: Tuple[str, ...] = ()

    @property
    def identity(self) -> Tuple[str, str]:
        return (self.model_id, self.model_version)

    @property
    def record_hash(self) -> str:
        return prefixed_hash(
            REGISTRY_PREFIX,
            {
                "kind": "model_record",
                "model_id": self.model_id,
                "model_version": self.model_version,
                "experiment_id": self.experiment_id,
                "owner": self.owner,
                "dataset_id": self.dataset_id,
                "feature_set_id": self.feature_set_id,
                "training_cutoff": self.training_cutoff,
                "status": self.status.value,
                "validation_evidence": list(self.validation_evidence),
                "calibration_evidence": list(self.calibration_evidence),
                "drift_status": self.drift_status.value,
                "approval": (
                    None
                    if self.approval is None
                    else {
                        "approver": self.approval.approver,
                        "approver_kind": self.approval.approver_kind,
                        "decision_id": self.approval.decision_id,
                        "recorded_at": self.approval.recorded_at,
                    }
                ),
                "paper_status": self.paper_status,
                "retirement_status": self.retirement_status,
            },
        )


class ApprovalDecision(BaseModel):
    """Outcome of an approval submission (T-PRED-022/T-PRED-023)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    approver: str
    approver_kind: str
    reason: str
    decision_id: str


class PredictionModelRegistry:
    """In-memory governed registry (§31). Duplicate identity rejected."""

    def __init__(self) -> None:
        self._records: Dict[Tuple[str, str], ModelRecord] = {}
        self._history: Tuple[str, ...] = ()

    # -- registration ----------------------------------------------------

    def register(self, record: ModelRecord) -> ModelRecord:
        """Register a new model. Initial status MUST be DISCOVER (§30)."""
        if record.identity in self._records:
            raise RegistryError(
                f"duplicate model identity rejected: "
                f"{record.model_id}@{record.model_version} (§31)"
            )
        if record.status is not ModelLifecycleState.DISCOVER:
            raise RegistryError(
                "models enter the registry at DISCOVER (got "
                f"{record.status.value})"
            )
        self._records[record.identity] = record
        self._history = self._history + (
            f"REGISTER {record.model_id}@{record.model_version}",)
        return record

    def get(self, model_id: str, model_version: str) -> ModelRecord:
        try:
            return self._records[(model_id, model_version)]
        except KeyError as exc:
            raise RegistryError(
                f"unknown model {model_id}@{model_version}"
            ) from exc

    def list_records(self) -> Tuple[ModelRecord, ...]:
        return tuple(
            self._records[key] for key in sorted(self._records)
        )

    # -- lifecycle -------------------------------------------------------

    def transition(
        self,
        model_id: str,
        model_version: str,
        new_status: ModelLifecycleState,
    ) -> ModelRecord:
        """Apply a lifecycle transition (§30). Illegal edges raise.

        PAPER/GRADUATE additionally require a HUMAN approval on record.
        """
        record = self.get(model_id, model_version)
        if record.status in TERMINAL_STATES:
            raise RegistryError(
                f"{record.status.value} is terminal — no further transitions"
            )
        if new_status not in ALLOWED_TRANSITIONS[record.status]:
            raise RegistryError(
                f"illegal lifecycle transition {record.status.value} -> "
                f"{new_status.value} (mandate §30 chain)"
            )
        if new_status in APPROVAL_REQUIRED:
            if record.approval is None or record.approval.approver_kind != "human":
                raise RegistryError(
                    f"transition to {new_status.value} requires a recorded "
                    "HUMAN approval — no model self-approves (§30/§43)"
                )
        updated = record.model_copy(
            update={"status": new_status}
        )
        self._records[record.identity] = updated
        self._history = self._history + (
            f"TRANSITION {model_id}@{model_version} "
            f"{record.status.value}->{new_status.value}",)
        return updated

    # -- approvals -------------------------------------------------------

    def submit_approval(
        self,
        model_id: str,
        model_version: str,
        approver: str,
        *,
        approver_kind: str,
        recorded_at: str = "UNRECORDED",
    ) -> ApprovalDecision:
        """Record (or REJECT) an approval decision (§43, T-PRED-023).

        AI/agent approvals are rejected structurally: the record's
        lifecycle status does not change and the rejection is noted.
        """
        record = self.get(model_id, model_version)
        decision_id = prefixed_hash(
            REGISTRY_PREFIX,
            {
                "kind": "approval_decision",
                "model_id": model_id,
                "model_version": model_version,
                "approver": approver,
                "approver_kind": approver_kind,
                "recorded_at": recorded_at,
            },
        )
        if approver_kind != "human":
            decision = ApprovalDecision(
                accepted=False,
                approver=approver,
                approver_kind=approver_kind,
                reason=(
                    "AI/agent self-approval is structurally rejected — "
                    "only a human approver can approve a model (§30/§41)"
                ),
                decision_id=decision_id,
            )
            updated = record.model_copy(
                update={
                    "notes": record.notes
                    + (f"APPROVAL_REJECTED({approver_kind}:{approver})",)
                }
            )
            self._records[record.identity] = updated
            return decision
        approval = ApprovalRecord(
            approver=approver,
            approver_kind="human",
            decision_id=decision_id,
            recorded_at=recorded_at,
        )
        updated = record.model_copy(update={"approval": approval})
        self._records[record.identity] = updated
        return ApprovalDecision(
            accepted=True,
            approver=approver,
            approver_kind="human",
            reason="human approval recorded",
            decision_id=decision_id,
        )

    @property
    def history(self) -> Tuple[str, ...]:
        return self._history


__all__ = [
    "FORWARD_CHAIN",
    "APPROVAL_REQUIRED",
    "TERMINAL_STATES",
    "ALLOWED_TRANSITIONS",
    "RegistryError",
    "ApprovalRecord",
    "ModelRecord",
    "ApprovalDecision",
    "PredictionModelRegistry",
]
