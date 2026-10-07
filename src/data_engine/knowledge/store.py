"""Knowledge and memory stores (blueprint 5.42).

``KnowledgeStore``:

- Append-only (append returns a NEW store — no mutation in place).
- Duplicate record_hash rejected (same evidence cannot enter twice).
- Hash chain over record digests (identity + version + type):
  ``verify_integrity`` re-derives it; tamper fails closed.
- ``authoritative()`` view: FACT + HUMAN_DECISION + validated
  MODEL_OUTPUT only — model-generated content is never authoritative
  without validation (mandate Phase 18, structural).
- HUMAN_DECISION records require a HUMAN principal (machine principals
  refused at append — no AI may forge a human decision).

``MemoryStore``:

- Append-only with strictly increasing sequence numbers.
- Bounded capacity (fail-closed when exceeded — memory is not an
  unbounded ledger).
- Hash-chained; tamper detection on read.
"""

import hashlib
from typing import Iterable, Optional

from pydantic import BaseModel, ConfigDict

from data_engine.knowledge.models import (
    KnowledgeRecord,
    MemoryRecord,
    RecordType,
)
from data_engine.research.governance import PrincipalKind


class KnowledgeStoreError(ValueError):
    """Raised on duplicate append, illegal principal, or tamper."""


class MemoryStoreError(ValueError):
    """Raised on sequence/limit violations or tamper."""


class _KnowledgeState(BaseModel):
    model_config = ConfigDict(frozen=True)

    records: tuple[KnowledgeRecord, ...] = ()
    chain_hash: str = "genesis"


class _MemoryState(BaseModel):
    model_config = ConfigDict(frozen=True)

    records: tuple[MemoryRecord, ...] = ()
    chain_hash: str = "genesis"


class KnowledgeStore:
    """Append-only, hash-verified, governance-aware knowledge base."""

    def __init__(self, state: Optional[_KnowledgeState] = None) -> None:
        self._state = state or _KnowledgeState()

    # -- reads --------------------------------------------------------------

    @property
    def records(self) -> tuple[KnowledgeRecord, ...]:
        return self._state.records

    @property
    def chain_hash(self) -> str:
        return self._state.chain_hash

    def authoritative(self) -> tuple[KnowledgeRecord, ...]:
        """The authoritative-evidence view (see KnowledgeRecord rule)."""
        return tuple(r for r in self._state.records if r.is_authoritative)

    def by_type(self, record_type: RecordType) -> tuple[KnowledgeRecord, ...]:
        return tuple(
            r for r in self._state.records if r.record_type is record_type
        )

    def get(self, record_id: str) -> KnowledgeRecord:
        for record in self._state.records:
            if record.record_id == record_id:
                return record
        raise KnowledgeStoreError(f"unknown record {record_id!r}")

    def latest_version(self, record_id: str) -> KnowledgeRecord:
        """The highest-version record for a base id (history kept)."""
        versions = [
            r for r in self._state.records
            if r.record_id == record_id or r.record_id.startswith(
                f"{record_id}#"
            )
        ]
        if not versions:
            raise KnowledgeStoreError(f"unknown record {record_id!r}")
        return max(versions, key=lambda r: r.version)

    # -- writes -------------------------------------------------------------

    def append(self, record: KnowledgeRecord) -> "KnowledgeStore":
        """Return a new store with ``record`` appended (append-only).

        Raises:
            KnowledgeStoreError: duplicate record_hash; HUMAN_DECISION
                attributed to a machine principal; a supersession that
                skips versions.
        """
        if record.record_type is RecordType.HUMAN_DECISION:
            if record.principal.kind is not PrincipalKind.HUMAN:
                raise KnowledgeStoreError(
                    "HUMAN_DECISION records require a HUMAN principal — "
                    "machine/self-issued decisions are refused"
                )
        existing_hashes = {r.record_hash for r in self._state.records}
        if record.record_hash in existing_hashes:
            raise KnowledgeStoreError(
                f"duplicate record (hash already present) — evidence "
                "cannot enter the knowledge base twice"
            )
        # Version continuity for the same base id.
        prior = [
            r for r in self._state.records
            if r.record_id == record.record_id
        ]
        if prior:
            expected = max(r.version for r in prior) + 1
            if record.version != expected:
                raise KnowledgeStoreError(
                    f"version discontinuity for {record.record_id!r}: "
                    f"expected {expected}, got {record.version}"
                )

        chain = self._extend(self._state.chain_hash, record)
        new_state = _KnowledgeState(
            records=self._state.records + (record,),
            chain_hash=chain,
        )
        return KnowledgeStore(new_state)

    def append_all(
        self, records: Iterable[KnowledgeRecord]
    ) -> "KnowledgeStore":
        store = self
        for record in records:
            store = store.append(record)
        return store

    # -- integrity ----------------------------------------------------------

    def verify_integrity(self) -> None:
        chain = "genesis"
        seen: set[str] = set()
        for record in self._state.records:
            if record.record_hash in seen:
                raise KnowledgeStoreError(
                    "integrity failure: duplicate record hash in chain"
                )
            seen.add(record.record_hash)
            chain = self._extend(chain, record)
        if chain != self._state.chain_hash:
            raise KnowledgeStoreError(
                "integrity failure: chain hash mismatch — knowledge base "
                "tampered"
            )

    @staticmethod
    def _extend(prev: str, record: KnowledgeRecord) -> str:
        digest = hashlib.sha256(
            (prev + "|" + record.record_hash).encode("utf-8")
        ).hexdigest()
        return "kchain42." + digest


class MemoryStore:
    """Append-only, bounded, tamper-evident session memory."""

    #: Capacity bound — memory is not an unbounded ledger.
    MAX_RECORDS = 256

    def __init__(self, state: Optional[_MemoryState] = None) -> None:
        self._state = state or _MemoryState()

    @property
    def records(self) -> tuple[MemoryRecord, ...]:
        return self._state.records

    @property
    def chain_hash(self) -> str:
        return self._state.chain_hash

    def append(self, record: MemoryRecord) -> "MemoryStore":
        """Return a new store with ``record`` appended.

        Raises:
            MemoryStoreError: sequence regression/repeat, capacity
                exceeded, or duplicate hash.
        """
        if self._state.records:
            last = self._state.records[-1]
            if record.session_id != last.session_id:
                raise MemoryStoreError(
                    "memory is session-scoped: cannot interleave sessions"
                )
            if record.sequence <= last.sequence:
                raise MemoryStoreError(
                    f"sequence must strictly increase "
                    f"({record.sequence} <= {last.sequence})"
                )
        if len(self._state.records) >= self.MAX_RECORDS:
            raise MemoryStoreError(
                f"memory capacity exceeded ({self.MAX_RECORDS}) — "
                "fail-closed, not silently truncated"
            )
        if any(r.record_hash == record.record_hash for r in self._state.records):
            raise MemoryStoreError("duplicate memory record hash")
        chain = self._extend(self._state.chain_hash, record)
        new_state = _MemoryState(
            records=self._state.records + (record,),
            chain_hash=chain,
        )
        return MemoryStore(new_state)

    def verify_integrity(self) -> None:
        chain = "genesis"
        for record in self._state.records:
            chain = self._extend(chain, record)
        if chain != self._state.chain_hash:
            raise MemoryStoreError(
                "integrity failure: chain hash mismatch — memory tampered"
            )

    @staticmethod
    def _extend(prev: str, record: MemoryRecord) -> str:
        digest = hashlib.sha256(
            (prev + "|" + record.record_hash).encode("utf-8")
        ).hexdigest()
        return "mchain42." + digest
