"""Structured trading memory (pre-paper mandate §41).

Twelve governed categories:

MARKET · MODEL · PREDICTION · DECISION · TRADE · EXECUTION · RISK ·
INCIDENT · PERFORMANCE · REGIME · CRASH · OPERATIONS

Design constraints:

- append-only, hash-chained, capacity-bounded (fail-closed on
  overflow — memory is not an unbounded ledger);
- **memory NEVER overrides safety controls**: the store is read-only
  context — there is no API through which a memory record could
  alter a risk verdict, kill switch, or order decision (structural
  separation, mandate §41);
- deterministic record identity (``rtmem.`` prefix); wall-clock
  audit timestamps only.
"""

from datetime import datetime, UTC
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import MemoryCategory, RuntimeContractError
from data_engine.runtime.identity import MEMORY_PREFIX, prefixed_hash


class MemoryError(RuntimeContractError):
    """Raised on trading-memory contract violations."""


class TradingMemoryRecord(BaseModel):
    """One structured memory record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    category: MemoryCategory
    timestamp: datetime
    correlation_id: Optional[str] = None
    content: Mapping[str, Any]
    record_hash: str
    prev_hash: str

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v) -> Mapping:
        if not isinstance(v, Mapping) or not v:
            raise MemoryError("memory content must be a non-empty mapping")
        return v

    @field_validator("timestamp")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise MemoryError("memory timestamps must be timezone-aware")
        return v.astimezone(UTC)


class TradingMemory:
    """Append-only structured trading memory (mandate §41)."""

    MAX_RECORDS = 1024

    def __init__(self) -> None:
        self._records: list = []
        self._chain_hash = "genesis"

    # ------------------------------------------------------------------
    def record(
        self,
        category: MemoryCategory,
        content: Mapping[str, Any],
        correlation_id: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> TradingMemoryRecord:
        """Append one memory record (chained, capacity-bounded)."""
        if len(self._records) >= self.MAX_RECORDS:
            raise MemoryError(
                f"memory capacity exceeded ({self.MAX_RECORDS}) — fail "
                "closed, never silently truncated"
            )
        timestamp = at or datetime.now(UTC)
        prev_hash = self._chain_hash
        record_hash = prefixed_hash(
            MEMORY_PREFIX,
            {
                "kind": "trading_memory",
                "category": category.value,
                "timestamp": timestamp,
                "correlation_id": correlation_id,
                "content": dict(content),
                "prev_hash": prev_hash,
            },
        )
        record = TradingMemoryRecord(
            record_id=f"mem-{len(self._records):06d}-{category.value.lower()}",
            category=category,
            timestamp=timestamp,
            correlation_id=correlation_id,
            content=dict(content),
            record_hash=record_hash,
            prev_hash=prev_hash,
        )
        self._records.append(record)
        self._chain_hash = prefixed_hash(
            MEMORY_PREFIX,
            {"kind": "memory_chain", "prev": prev_hash,
             "record": record_hash},
        )
        return record

    # ------------------------------------------------------------------
    @property
    def records(self) -> tuple:
        return tuple(self._records)

    @property
    def chain_hash(self) -> str:
        return self._chain_hash

    def by_category(self, category: MemoryCategory) -> tuple:
        return tuple(r for r in self._records if r.category is category)

    # -- persistence (BLOCKER 20: memory survives restart) ---------------------
    def export_state(self) -> list:
        """Serialize every record (structured memory is authoritative
        trading state — it must not silently disappear on restart)."""
        return [r.model_dump(mode="json") for r in self._records]

    def restore_state(self, records: Sequence[Mapping]) -> int:
        """Rebuild memory from a persisted export; VERIFY the chain.

        Any tampered record (hash/chain mismatch) raises
        :class:`MemoryError` — fail closed. Returns restored count.
        """
        if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            raise MemoryError("memory export must be a sequence of records")
        restored: list = []
        for record in records:
            try:
                restored.append(TradingMemoryRecord.model_validate(record))
            except Exception as exc:
                raise MemoryError(
                    "memory export contains a malformed record — "
                    f"RECOVERY_REQUIRED ({exc})"
                ) from exc
        self._records = restored
        # Re-derive the chain head from the restored records FIRST,
        # then verify the full chain (record hashes + links + head).
        chain = "genesis"
        for record in restored:
            chain = prefixed_hash(
                MEMORY_PREFIX,
                {"kind": "memory_chain", "prev": chain,
                 "record": record.record_hash},
            )
        self._chain_hash = chain
        if not self.verify_integrity():
            raise MemoryError(
                "restored memory chain FAILED hash verification — "
                "tampered or corrupted (RECOVERY_REQUIRED)"
            )
        return len(restored)

    def verify_integrity(self) -> bool:
        """Recompute the full chain (tamper-evidence)."""
        prev = "genesis"
        for i, record in enumerate(self._records):
            if record.prev_hash != prev:
                return False
            expected = prefixed_hash(
                MEMORY_PREFIX,
                {
                    "kind": "trading_memory",
                    "category": record.category.value,
                    "timestamp": record.timestamp,
                    "correlation_id": record.correlation_id,
                    "content": dict(record.content),
                    "prev_hash": prev,
                },
            )
            if expected != record.record_hash:
                return False
            prev = prefixed_hash(
                MEMORY_PREFIX,
                {"kind": "memory_chain", "prev": prev,
                 "record": record.record_hash},
            )
        return prev == self._chain_hash

    def __len__(self) -> int:
        return len(self._records)


__all__ = [
    "MemoryError",
    "TradingMemoryRecord",
    "TradingMemory",
]
