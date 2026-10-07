"""Knowledge/Memory layer (blueprint 5.42, mandate Phase 18).

Stores research knowledge — findings, experiments, datasets, strategies,
validation results, failures, lessons, market observations, model
evaluations — as versioned, attributable, tamper-evident records.

Record taxonomy (mandate Phase 18 — the system must distinguish):

- FACT
- OBSERVATION
- HYPOTHESIS
- MODEL_OUTPUT
- HUMAN_DECISION

Governance invariants:

- MODEL_OUTPUT is NEVER authoritative evidence without validation:
  ``KnowledgeStore.authoritative()`` excludes MODEL_OUTPUT records
  that lack a ``validation_ref`` (structural, not procedural).
- HUMAN_DECISION records require a HUMAN principal (machine principals
  are refused at append).
- Knowledge is hash-verified (record hash + chain hash); memory is
  append-only with tamper detection.
- Identity contains NO wall-clock fields (ID-WC discipline).
"""

from data_engine.knowledge.models import (
    KNOWLEDGE_HASH_PREFIX,
    MEMORY_HASH_PREFIX,
    KNOWLEDGE_CONTRACT_VERSION,
    KnowledgeRecord,
    MemoryRecord,
    RecordType,
)
from data_engine.knowledge.store import (
    KnowledgeStore,
    KnowledgeStoreError,
    MemoryStore,
    MemoryStoreError,
)

__all__ = [
    "KNOWLEDGE_HASH_PREFIX",
    "MEMORY_HASH_PREFIX",
    "KNOWLEDGE_CONTRACT_VERSION",
    "KnowledgeRecord",
    "MemoryRecord",
    "RecordType",
    "KnowledgeStore",
    "KnowledgeStoreError",
    "MemoryStore",
    "MemoryStoreError",
]
