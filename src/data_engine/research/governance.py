"""Phase 4A.4 — Research governance (blueprint 5.15).

Research outputs with deterministic identity and auditable approval:

- ``ResearchContract``: a research finding with hypothesis, methodology,
  data references (by hash), and citations. Identity: ``res44.``.
- ``ApprovalMetadata``: EXTERNAL approval record. The no-self-approval
  invariant is structural: submitter and approver are different
  principals, and the approver must be a declared HUMAN principal
  (machine principals can never approve research — blueprint 5.15
  'no self-approval'; 5.60 'no AI self-authorization').
- ``ResearchRegistry``: append-only, hash-verified entries with
  approval status queries. Tampering with a stored entry breaks its
  recorded hash (fail closed on read).

Invariants:
- Approval is auditable EXTERNAL metadata — never a field the
  submitter can set on its own submission.
- Every citation carries a verifiable source hash.
- Unapproved research is queryable but explicitly NOT validated
  (failure mode 'unapproved research treated as validated' is closed
  by status separation, not by hiding entries).
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Identity prefix for research contract hashes.
RESEARCH_PREFIX = "res44."

#: Identity prefix for approval record hashes.
APPROVAL_PREFIX = "appr44."

#: Phase 4A.4 component contract version.
PHASE_4A4_CONTRACT_VERSION = "1.0.0"


class PrincipalKind(str, Enum):
    """Kind of principal (submitter or approver)."""

    HUMAN = "human"
    MACHINE = "machine"


class Principal(BaseModel):
    """Identified principal — human or machine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    kind: PrincipalKind

    @field_validator("principal_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("principal_id must be a non-empty string")
        return v.strip()


class ApprovalStatus(str, Enum):
    """Lifecycle status of a research entry's approval."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Citation(BaseModel):
    """One verifiable citation: source reference + content hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_ref: str
    content_hash: str

    @field_validator("source_ref")
    @classmethod
    def _validate_ref(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("source_ref must be a non-empty string")
        return v.strip()

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) < 16:
            raise ValueError("content_hash must be a verifiable hash (>= 16 chars)")
        return v


class ApprovalMetadata(BaseModel):
    """External approval record for a research entry.

    NO-SELF-APPROVAL (blueprint 5.15): ``approver`` must differ from
    the submitting principal AND must be a HUMAN principal. A machine
    approver raises at construction — fail closed, not at read time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    research_hash: str
    submitter: Principal
    approver: Principal
    decision: ApprovalStatus
    decision_time: datetime
    rationale: Optional[str] = None

    @field_validator("research_hash")
    @classmethod
    def _validate_research_hash(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("research_hash must be a non-empty hash string")
        return v

    @field_validator("decision_time")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("decision_time must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_no_self_approval(self) -> "ApprovalMetadata":
        if self.submitter.principal_id == self.approver.principal_id:
            raise ValueError(
                "NO-SELF-APPROVAL violation: submitter and approver are the "
                "same principal (blueprint 5.15)"
            )
        if self.approver.kind is not PrincipalKind.HUMAN:
            raise ValueError(
                "NO-SELF-APPROVAL violation: approver must be a HUMAN "
                "principal; machine principals can never approve research "
                "(blueprint 5.15 / 5.60 no AI self-authorization)"
            )
        return self

    @property
    def approval_hash(self) -> str:
        payload = {
            "contract_version": PHASE_4A4_CONTRACT_VERSION,
            "research_hash": self.research_hash,
            "submitter": self.submitter.principal_id,
            "submitter_kind": self.submitter.kind.value,
            "approver": self.approver.principal_id,
            "approver_kind": self.approver.kind.value,
            "decision": self.decision.value,
            "decision_time": self.decision_time,
            "rationale": self.rationale,
        }
        return APPROVAL_PREFIX + deterministic_hash(payload)


class ResearchContract(BaseModel):
    """A research finding with deterministic identity and citations.

    The contract does NOT carry an approval field: approval lives ONLY
    in external ApprovalMetadata records (auditable separation).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    research_id: str
    title: str
    hypothesis: str
    methodology: str
    data_references: tuple[str, ...] = ()
    citations: tuple[Citation, ...] = ()
    submitted_by: Principal
    submitted_at: datetime

    @field_validator("research_id", "title", "hypothesis", "methodology")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("research text fields must be non-empty strings")
        return v.strip()

    @field_validator("data_references")
    @classmethod
    def _validate_refs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("data_references must be unique")
        return tuple(v)

    @field_validator("submitted_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("submitted_at must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def research_hash(self) -> str:
        """Deterministic identity: ``res44.`` + SHA-256 hex (70 chars)."""
        payload = {
            "contract_version": PHASE_4A4_CONTRACT_VERSION,
            "research_id": self.research_id,
            "title": self.title,
            "hypothesis": self.hypothesis,
            "methodology": self.methodology,
            "data_references": list(self.data_references),
            "citations": [
                {"source_ref": c.source_ref, "content_hash": c.content_hash}
                for c in self.citations
            ],
            "submitted_by": self.submitted_by.principal_id,
            "submitted_by_kind": self.submitted_by.kind.value,
            "submitted_at": self.submitted_at,
        }
        return RESEARCH_PREFIX + deterministic_hash(payload)


class ResearchRegistryError(ValueError):
    """Raised on registry integrity violations."""


class ResearchRegistry:
    """Append-only, hash-verified research registry.

    Entries are stored with their computed hash; a read that finds the
    stored entry no longer matching its hash fails closed
    (tamper detection, blueprint 5.15 failure mode).
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[ResearchContract, str]] = {}
        self._approvals: dict[str, list[ApprovalMetadata]] = {}

    def register(self, contract: ResearchContract) -> str:
        """Register a research contract; returns its hash.

        Duplicate research_id or duplicate hash raises (registry
        integrity — no silent overwrite).
        """
        if contract.research_id in self._entries:
            raise ResearchRegistryError(
                f"research_id {contract.research_id!r} already registered"
            )
        h = contract.research_hash
        if any(h == stored for _, stored in self._entries.values()):
            raise ResearchRegistryError(
                "identical research contract already registered "
                "(duplicate submission)"
            )
        self._entries[contract.research_id] = (contract, h)
        return h

    def attach_approval(self, approval: ApprovalMetadata) -> None:
        """Attach an external approval record to a registered entry."""
        registered = self._find_by_hash(approval.research_hash)
        if registered is None:
            raise ResearchRegistryError(
                "approval targets an unregistered research hash — "
                "approving ghosts is forbidden"
            )
        for existing in self._approvals.get(registered.research_id, []):
            if existing.approval_hash == approval.approval_hash:
                raise ResearchRegistryError("duplicate approval record")
        self._approvals.setdefault(registered.research_id, []).append(approval)

    def _find_by_hash(self, research_hash: str) -> Optional[ResearchContract]:
        for contract, stored_hash in self._entries.values():
            if stored_hash == research_hash:
                # Tamper check: recompute NOW and compare.
                if contract.research_hash != stored_hash:
                    raise ResearchRegistryError(
                        f"registry tamper detected for {contract.research_id}: "
                        "stored hash no longer matches the entry"
                    )
                return contract
        return None

    def get(self, research_id: str) -> ResearchContract:
        """Fetch a registered entry; verifies hash on read."""
        if research_id not in self._entries:
            raise ResearchRegistryError(
                f"research_id {research_id!r} not registered"
            )
        contract, stored_hash = self._entries[research_id]
        if contract.research_hash != stored_hash:
            raise ResearchRegistryError(
                f"registry tamper detected for {research_id}: "
                "stored hash no longer matches the entry"
            )
        return contract

    def status(self, research_id: str) -> ApprovalStatus:
        """Current approval status of an entry.

        PENDING when no approval records exist. With multiple records
        the LATEST decision_time governs (rejection can be overturned
        only by a later human record — an auditable trail, not a
        silent flip).
        """
        contract = self.get(research_id)
        records = self._approvals.get(research_id, [])
        if not records:
            return ApprovalStatus.PENDING
        latest = max(records, key=lambda r: r.decision_time)
        return latest.decision

    def approved_only(self) -> list[str]:
        """IDs of entries whose latest status is APPROVED."""
        return [
            rid
            for rid in self._entries
            if self.status(rid) is ApprovalStatus.APPROVED
        ]

    def __len__(self) -> int:
        return len(self._entries)


__all__ = [
    "PrincipalKind",
    "Principal",
    "ApprovalStatus",
    "Citation",
    "ApprovalMetadata",
    "ResearchContract",
    "ResearchRegistry",
    "ResearchRegistryError",
    "RESEARCH_PREFIX",
    "APPROVAL_PREFIX",
    "PHASE_4A4_CONTRACT_VERSION",
]
