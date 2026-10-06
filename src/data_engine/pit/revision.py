"""Phase 4A.1 — RevisionChain: append-only revision history.

Implements spec SECTION 7.2 with the composite cutoff semantics of
SECTION 4.6.

A RevisionChain is an append-only, ordered history of all revisions of
one logical datum:

- every entry is immutable once appended
- revision_time is STRICTLY increasing within a chain
- every entry except the first declares supersedes (the entry_hash of
  its predecessor); no gaps, no dangling links
- chain integrity is hash-verifiable (chain_hash recomputation)

Composite cutoff evaluation at cutoff T (spec 4.6):

    eligible(revision) iff  revision.revision_time <= T
                       AND  revision.publication_time <= T
                       AND  revision is not superseded by a revision
                            with revision_time <= T
    selected = max(revision_time) among eligible

A "latest-value-only" dataset (an entry claiming to supersede a prior
revision that is absent from the chain) is REJECTED at construction —
a dangling supersedes link is unverifiable history (T-R04).
"""

from datetime import datetime, UTC
from typing import Any, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import identity_hash, PHASE4_IDENTITY_CONTRACT_VERSION


class RevisionEntry(BaseModel):
    """One immutable revision of a logical datum.

    Identity: revision_time, publication_time, and the payload content
    (spec 7.2: 'Ordered (revision_time, publication_time, entry_hash)
    sequence. Payload content participates').
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_time: datetime
    publication_time: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
    supersedes: Optional[str] = None
    schema_version: str = Field(default="1.0.0")

    #: Ordered identity-field allowlist (spec 2.3).
    IDENTITY_FIELDS: tuple[str, ...] = (
        "revision_time",
        "publication_time",
        "payload",
    )

    @field_validator("revision_time", "publication_time", mode="before")
    @classmethod
    def _validate_timezone_aware(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError(
                "Naive datetime is not allowed. All PIT timestamps must be "
                "timezone-aware and UTC-normalized."
            )
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_entry(self) -> "RevisionEntry":
        # Spec 4.5: a chain entry without revision_time is malformed —
        # enforced by the required field. Publication ordering per 4.3.
        if self.publication_time > self.revision_time:
            raise ValueError(
                f"Temporal ordering violation (spec 4.3): publication_time "
                f"({self.publication_time.isoformat()}) > revision_time "
                f"({self.revision_time.isoformat()})."
            )
        return self

    @property
    def entry_hash(self) -> str:
        """Phase 4 identity hash of this entry (payload participates)."""
        return identity_hash(
            entity_type="RevisionEntry",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "revision_time": self.revision_time,
                "publication_time": self.publication_time,
                "payload": self.payload,
            },
        )


class RevisionChain(BaseModel):
    """Append-only, ordered history of all revisions of one datum."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    entries: tuple[RevisionEntry, ...] = Field(default_factory=tuple)
    schema_version: str = Field(default="1.0.0")

    @field_validator("entries")
    @classmethod
    def _validate_entries(cls, v: tuple[RevisionEntry, ...]) -> tuple[RevisionEntry, ...]:
        if not v:
            raise ValueError("A RevisionChain must contain at least one entry.")
        prior: Optional[RevisionEntry] = None
        for i, entry in enumerate(v):
            if prior is not None:
                # Strict monotonicity (spec 7.2).
                if entry.revision_time <= prior.revision_time:
                    raise ValueError(
                        f"revision_time must be strictly increasing within a "
                        f"chain (spec 7.2): entry {i} "
                        f"({entry.revision_time.isoformat()}) <= entry {i - 1} "
                        f"({prior.revision_time.isoformat()})."
                    )
                # No gaps in supersedes: each entry links to its predecessor.
                if entry.supersedes != prior.entry_hash:
                    raise ValueError(
                        f"Broken supersedes link at entry {i}: declared "
                        f"{entry.supersedes!r}, expected "
                        f"{prior.entry_hash!r} (the predecessor's entry_hash)."
                    )
            else:
                # First entry: a dangling supersedes link is a
                # latest-value-only dataset — unverifiable history (T-R04).
                if entry.supersedes is not None:
                    raise ValueError(
                        f"Latest-value-only dataset rejected (T-R04, spec 7.2): "
                        f"the first entry declares supersedes={entry.supersedes!r} "
                        f"but no such prior revision exists in the chain. A "
                        f"revision history that claims to replace absent "
                        f"history is unverifiable and MUST be rejected."
                    )
            prior = entry
        return v

    @property
    def chain_hash(self) -> str:
        """Integrity hash over the ordered entry sequence ('pit4c.')."""
        from data_engine.pit.serialization import canonical_serialize
        import hashlib
        payload = [entry.entry_hash for entry in self.entries]
        digest = hashlib.sha256(canonical_serialize(payload)).hexdigest()
        return "pit4c." + digest

    def verify_integrity(self, recorded_chain_hash: Optional[str] = None) -> bool:
        """Recompute the chain hash and verify integrity (tamper detection).

        With ``recorded_chain_hash``: recomputes the live chain hash from
        the current entries and compares it to the recorded value. A
        mutated payload in ANY entry changes that entry's entry_hash,
        which changes the recomputed chain hash — the mismatch is the
        tamper evidence (T-R03).

        Without it: verifies the structural invariant that each entry's
        declared supersedes link equals its predecessor's recomputed
        entry_hash (an in-place mutation of any non-final entry breaks
        its successor's link).
        """
        if recorded_chain_hash is not None:
            return self.chain_hash == recorded_chain_hash
        for i in range(1, len(self.entries)):
            if self.entries[i].supersedes != self.entries[i - 1].entry_hash:
                return False
        return True

    def select_at(self, cutoff: datetime) -> Optional[RevisionEntry]:
        """Composite cutoff selection (spec 4.6).

        eligible(revision) iff revision_time <= cutoff AND
        publication_time <= cutoff AND not superseded by a revision
        with revision_time <= cutoff. selected = max revision_time
        among eligible. Returns None when nothing is eligible.
        """
        if cutoff is None or cutoff.tzinfo is None:
            raise ValueError("cutoff must be a timezone-aware datetime.")
        cutoff = cutoff.astimezone(UTC)
        eligible: list[RevisionEntry] = []
        for i, entry in enumerate(self.entries):
            if entry.revision_time > cutoff:
                continue
            if entry.publication_time > cutoff:
                continue
            superseded = any(
                later.revision_time <= cutoff
                for later in self.entries[i + 1:]
            )
            if superseded:
                continue
            eligible.append(entry)
        if not eligible:
            return None
        return max(eligible, key=lambda e: e.revision_time)

    def latest_entry(self) -> RevisionEntry:
        """The most recent revision in the chain (no cutoff applied)."""
        return self.entries[-1]

    def __len__(self) -> int:
        return len(self.entries)
