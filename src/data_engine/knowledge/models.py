"""Knowledge/Memory record models (blueprint 5.42).

Identity contract:

- ``know42.`` / ``mem42.`` prefixes + SHA-256 hex (deterministic_hash
  over the allowlisted payload).
- Payload: contract version, record type, subject refs, attribution,
  content, version, validation ref. NO wall-clock, no RNG, no PID.
- Attributable: every record carries a ``Principal`` (human or machine)
  — HUMAN_DECISION records MUST be human-attributed (store enforces).
- Versioned: a ``version`` field orders supersessions; the store keeps
  every version (history is never rewritten).
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.pit.hashing import (
    PROHIBITED_IDENTITY_FIELDS,
    deterministic_hash,
)
from data_engine.research.governance import Principal, PrincipalKind

#: Knowledge-layer contract version (blueprint 5.42).
KNOWLEDGE_CONTRACT_VERSION = "1.0.0"

#: Identity prefix for knowledge records.
KNOWLEDGE_HASH_PREFIX = "know42."

#: Identity prefix for memory records.
MEMORY_HASH_PREFIX = "mem42."


class RecordType(str, Enum):
    """The mandate's five knowledge record classes."""

    FACT = "fact"
    OBSERVATION = "observation"
    HYPOTHESIS = "hypothesis"
    MODEL_OUTPUT = "model_output"
    HUMAN_DECISION = "human_decision"


#: Types that constitute authoritative evidence on their own.
_AUTHORITATIVE_TYPES: frozenset[RecordType] = frozenset(
    {RecordType.FACT, RecordType.HUMAN_DECISION}
)


def is_authoritative_type(record_type: RecordType) -> bool:
    """True when a record type is authoritative without validation."""
    return record_type in _AUTHORITATIVE_TYPES


class SubjectRefs(BaseModel):
    """Structured references to the artifacts a record concerns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_hashes: tuple[str, ...] = ()
    dataset_hashes: tuple[str, ...] = ()
    strategy_hashes: tuple[str, ...] = ()
    validation_hashes: tuple[str, ...] = ()

    @field_validator(
        "experiment_hashes",
        "dataset_hashes",
        "strategy_hashes",
        "validation_hashes",
    )
    @classmethod
    def _validate_hash_lists(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for item in v:
            if not isinstance(item, str) or len(item) < 16:
                raise ValueError(
                    "subject refs must be verifiable hashes (>= 16 chars)"
                )
        return tuple(v)


class KnowledgeRecord(BaseModel):
    """One versioned, attributable knowledge record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    record_type: RecordType
    principal: Principal
    content: dict[str, Any] = Field(default_factory=dict)
    subject_refs: SubjectRefs = Field(default_factory=SubjectRefs)
    version: int = Field(default=1, ge=1)
    validation_ref: Optional[str] = Field(default=None, min_length=16)
    superseded_by: Optional[str] = None

    @field_validator("record_id")
    @classmethod
    def _validate_record_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("record_id must be a non-empty string")
        return v.strip()

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("content must be a structured mapping")
        return v

    @property
    def identity_payload(self) -> dict[str, Any]:
        """Positively-declared identity payload (allowlist only)."""
        payload = {
            "contract_version": KNOWLEDGE_CONTRACT_VERSION,
            "record_type": self.record_type.value,
            "principal": {
                "principal_id": self.principal.principal_id,
                "kind": self.principal.kind.value,
            },
            "content": self.content,
            "subject_refs": {
                "experiment_hashes": list(
                    self.subject_refs.experiment_hashes
                ),
                "dataset_hashes": list(self.subject_refs.dataset_hashes),
                "strategy_hashes": list(self.subject_refs.strategy_hashes),
                "validation_hashes": list(
                    self.subject_refs.validation_hashes
                ),
            },
            "version": self.version,
            "validation_ref": self.validation_ref,
        }
        illegal = PROHIBITED_IDENTITY_FIELDS & set(payload)
        if illegal:
            raise ValueError(
                f"prohibited identity fields present: {sorted(illegal)}"
            )
        return payload

    @property
    def record_hash(self) -> str:
        """Deterministic record identity: ``know42.`` + SHA-256 hex."""
        return (
            KNOWLEDGE_HASH_PREFIX
            + deterministic_hash(self.identity_payload)
        )

    @property
    def is_authoritative(self) -> bool:
        """Authoritative-evidence rule (mandate Phase 18).

        FACT and HUMAN_DECISION are authoritative on their own;
        MODEL_OUTPUT requires a validation_ref; OBSERVATION and
        HYPOTHESIS are never authoritative evidence.
        """
        if self.record_type in _AUTHORITATIVE_TYPES:
            return True
        if self.record_type is RecordType.MODEL_OUTPUT:
            return self.validation_ref is not None
        return False


class MemoryRecord(BaseModel):
    """One append-only memory entry (agent/run state)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    sequence: int = Field(ge=0)
    principal: Principal
    content: dict[str, Any] = Field(default_factory=dict)

    @field_validator("session_id")
    @classmethod
    def _validate_session(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("session_id must be a non-empty string")
        return v.strip()

    @property
    def record_hash(self) -> str:
        """Deterministic memory identity: ``mem42.`` + SHA-256 hex."""
        payload = {
            "contract_version": KNOWLEDGE_CONTRACT_VERSION,
            "session_id": self.session_id,
            "sequence": self.sequence,
            "principal": {
                "principal_id": self.principal.principal_id,
                "kind": self.principal.kind.value,
            },
            "content": self.content,
        }
        illegal = PROHIBITED_IDENTITY_FIELDS & set(payload)
        if illegal:
            raise ValueError(
                f"prohibited identity fields present: {sorted(illegal)}"
            )
        return MEMORY_HASH_PREFIX + deterministic_hash(payload)
