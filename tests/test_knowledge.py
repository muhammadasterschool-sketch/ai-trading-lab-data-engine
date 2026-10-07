"""Knowledge/Memory layer tests (mandate Phase 18, blueprint 5.42)."""

import pytest

from data_engine.knowledge import (
    KNOWLEDGE_HASH_PREFIX,
    MEMORY_HASH_PREFIX,
    KnowledgeRecord,
    KnowledgeStore,
    KnowledgeStoreError,
    MemoryRecord,
    MemoryStore,
    MemoryStoreError,
    RecordType,
)
from data_engine.research.governance import Principal, PrincipalKind

HUMAN = Principal(principal_id="operator-1", kind=PrincipalKind.HUMAN)
AGENT = Principal(principal_id="agent-zai", kind=PrincipalKind.MACHINE)


def _record(
    record_type=RecordType.OBSERVATION,
    principal=AGENT,
    record_id="obs-1",
    version=1,
    content=None,
    validation_ref=None,
) -> KnowledgeRecord:
    return KnowledgeRecord(
        record_id=record_id,
        record_type=record_type,
        principal=principal,
        # Content-addressed identity: distinct records carry distinct
        # content (identical evidence deduplicates — by design).
        content=content or {"note": f"record {record_id}"},
        version=version,
        validation_ref=validation_ref,
    )


# ---------------------------------------------------------------------------
# Record taxonomy and identity
# ---------------------------------------------------------------------------

class TestRecordTaxonomy:
    def test_five_record_types_exist(self):
        assert {t.value for t in RecordType} == {
            "fact",
            "observation",
            "hypothesis",
            "model_output",
            "human_decision",
        }

    def test_record_hash_format(self):
        record = _record()
        assert record.record_hash.startswith(KNOWLEDGE_HASH_PREFIX)
        assert len(record.record_hash) == 7 + 64  # 'know42.' + hex

    def test_record_hash_is_deterministic(self):
        a = _record()
        b = _record()
        assert a.record_hash == b.record_hash

    def test_record_hash_distinguishes_type(self):
        assert _record().record_hash != _record(
            record_type=RecordType.HYPOTHESIS
        ).record_hash

    def test_record_hash_distinguishes_principal(self):
        assert _record().record_hash != _record(principal=HUMAN).record_hash

    def test_record_hash_distinguishes_version(self):
        assert _record().record_hash != _record(version=2).record_hash

    def test_no_wall_clock_in_identity_payload(self):
        payload = _record().identity_payload
        assert set(payload) == {
            "contract_version",
            "record_type",
            "principal",
            "content",
            "subject_refs",
            "version",
            "validation_ref",
        }

    def test_authoritative_type_rules(self):
        assert _record(RecordType.FACT).is_authoritative
        assert _record(RecordType.HUMAN_DECISION, HUMAN).is_authoritative
        assert not _record(RecordType.OBSERVATION).is_authoritative
        assert not _record(RecordType.HYPOTHESIS).is_authoritative
        assert not _record(RecordType.MODEL_OUTPUT).is_authoritative

    def test_model_output_authoritative_only_with_validation(self):
        unvalidated = _record(
            RecordType.MODEL_OUTPUT, validation_ref=None
        )
        validated = _record(
            RecordType.MODEL_OUTPUT, validation_ref="v" * 64
        )
        assert not unvalidated.is_authoritative
        assert validated.is_authoritative

    def test_empty_record_id_rejected(self):
        with pytest.raises(Exception, match="non-empty"):
            _record(record_id="  ")

    def test_subject_refs_require_real_hashes(self):
        from data_engine.knowledge.models import SubjectRefs
        with pytest.raises(Exception, match="verifiable"):
            SubjectRefs(dataset_hashes=("short",))


# ---------------------------------------------------------------------------
# Knowledge store governance
# ---------------------------------------------------------------------------

class TestKnowledgeStore:
    def test_append_returns_new_store(self):
        store = KnowledgeStore()
        store2 = store.append(_record())
        assert len(store.records) == 0
        assert len(store2.records) == 1

    def test_duplicate_record_rejected(self):
        record = _record()
        with pytest.raises(KnowledgeStoreError, match="duplicate"):
            KnowledgeStore().append(record).append(record)

    def test_human_decision_requires_human_principal(self):
        with pytest.raises(KnowledgeStoreError, match="HUMAN"):
            KnowledgeStore().append(
                _record(RecordType.HUMAN_DECISION, principal=AGENT)
            )

    def test_human_decision_with_human_principal_ok(self):
        store = KnowledgeStore().append(
            _record(RecordType.HUMAN_DECISION, principal=HUMAN)
        )
        assert len(store.records) == 1

    def test_authoritative_view_excludes_unvalidated_model_output(self):
        store = (
            KnowledgeStore()
            .append(_record(RecordType.FACT, principal=HUMAN, record_id="f1"))
            .append(_record(RecordType.MODEL_OUTPUT, record_id="m1"))
            .append(
                _record(
                    RecordType.MODEL_OUTPUT,
                    record_id="m2",
                    validation_ref="v" * 64,
                )
            )
            .append(_record(RecordType.OBSERVATION, record_id="o1"))
            .append(_record(RecordType.HYPOTHESIS, record_id="h1"))
        )
        authoritative = store.authoritative()
        ids = {r.record_id for r in authoritative}
        assert ids == {"f1", "m2"}  # unvalidated model output excluded

    def test_by_type_query(self):
        store = (
            KnowledgeStore()
            .append(_record(RecordType.OBSERVATION, record_id="o1"))
            .append(_record(RecordType.OBSERVATION, record_id="o2"))
            .append(_record(RecordType.HYPOTHESIS, record_id="h1"))
        )
        assert len(store.by_type(RecordType.OBSERVATION)) == 2
        assert len(store.by_type(RecordType.HYPOTHESIS)) == 1

    def test_version_continuity_enforced(self):
        store = KnowledgeStore().append(_record(version=1))
        with pytest.raises(KnowledgeStoreError, match="discontinuity"):
            store.append(_record(version=3))  # skips 2

    def test_versioned_supersession_keeps_history(self):
        store = (
            KnowledgeStore()
            .append(_record(version=1))
            .append(_record(version=2, content={"note": "revised"}))
        )
        assert len(store.records) == 2  # history never rewritten
        assert store.latest_version("obs-1").version == 2

    def test_version_continuity_and_dedup_are_distinct(self):
        store = KnowledgeStore().append(_record(version=1))
        # Same content + version bump is a legitimate supersession:
        store2 = store.append(
            _record(version=2, content={"note": "record obs-1"})
        )
        assert len(store2.records) == 2
        # Identical evidence re-appended to a FRESH store still stores once:
        with pytest.raises(KnowledgeStoreError, match="duplicate"):
            store2.append(_record(version=2, content={"note": "record obs-1"}))
        # ...but version 3 with identical content is a new version:
        store3 = store2.append(
            _record(version=3, content={"note": "record obs-1"})
        )
        assert store3.latest_version("obs-1").version == 3

    def test_integrity_verification_passes(self):
        store = KnowledgeStore().append_all(
            [_record(record_id=f"r{i}") for i in range(5)]
        )
        store.verify_integrity()

    def test_integrity_fails_on_tamper(self):
        store = KnowledgeStore().append(_record())
        tampered_record = _record(
            record_type=RecordType.FACT, principal=HUMAN
        )  # same id, different content — simulated silent rewrite
        from data_engine.knowledge.store import _KnowledgeState
        tampered = KnowledgeStore(
            _KnowledgeState(
                records=(tampered_record,),
                chain_hash=store.chain_hash,
            )
        )
        with pytest.raises(KnowledgeStoreError, match="chain hash mismatch"):
            tampered.verify_integrity()

    def test_unknown_record_get_raises(self):
        with pytest.raises(KnowledgeStoreError, match="unknown"):
            KnowledgeStore().get("missing")


# ---------------------------------------------------------------------------
# Memory store
# ---------------------------------------------------------------------------

class TestMemoryStore:
    def _memory(self, sequence=0, content=None) -> MemoryRecord:
        return MemoryRecord(
            session_id="run-1",
            sequence=sequence,
            principal=AGENT,
            content=content or {"state": f"step-{sequence}"},
        )

    def test_memory_hash_format(self):
        record = self._memory()
        assert record.record_hash.startswith(MEMORY_HASH_PREFIX)
        assert len(record.record_hash) == 6 + 64  # 'mem42.' + hex

    def test_append_and_immutability(self):
        store = MemoryStore().append(self._memory(0))
        store2 = store.append(self._memory(1))
        assert len(store.records) == 1
        assert len(store2.records) == 2

    def test_sequence_must_strictly_increase(self):
        store = MemoryStore().append(self._memory(0)).append(self._memory(2))
        with pytest.raises(MemoryStoreError, match="strictly increase"):
            store.append(self._memory(2))
        with pytest.raises(MemoryStoreError, match="strictly increase"):
            store.append(self._memory(1))

    def test_sessions_cannot_interleave(self):
        store = MemoryStore().append(self._memory(0))
        other = MemoryRecord(
            session_id="run-2",
            sequence=1,
            principal=AGENT,
            content={},
        )
        with pytest.raises(MemoryStoreError, match="session-scoped"):
            store.append(other)

    def test_capacity_is_fail_closed(self):
        store = MemoryStore()
        for i in range(MemoryStore.MAX_RECORDS):
            store = store.append(self._memory(i))
        with pytest.raises(MemoryStoreError, match="capacity"):
            store.append(self._memory(MemoryStore.MAX_RECORDS))

    def test_memory_integrity_tamper_detected(self):
        store = MemoryStore().append(self._memory(0))
        from data_engine.knowledge.store import _MemoryState
        tampered = MemoryStore(
            _MemoryState(
                records=(self._memory(0, content={"state": "hacked"}),),
                chain_hash=store.chain_hash,
            )
        )
        with pytest.raises(MemoryStoreError, match="chain hash mismatch"):
            tampered.verify_integrity()

    def test_memory_integrity_passes_when_untouched(self):
        store = MemoryStore().append(self._memory(0)).append(self._memory(1))
        store.verify_integrity()


# ---------------------------------------------------------------------------
# Cross-cutting: model output never silently authoritative
# ---------------------------------------------------------------------------

class TestModelOutputGovernance:
    def test_store_never_promotes_unvalidated_model_output(self):
        """Even after many appends, unvalidated MODEL_OUTPUT stays out."""
        records = [
            _record(RecordType.MODEL_OUTPUT, record_id=f"m{i}")
            for i in range(10)
        ]
        store = KnowledgeStore().append_all(records)
        assert len(store.records) == 10
        assert len(store.authoritative()) == 0

    def test_machine_principals_cannot_forge_decisions(self):
        """A machine principal's 'human decision' is refused at append."""
        forged = _record(RecordType.HUMAN_DECISION, principal=AGENT)
        with pytest.raises(KnowledgeStoreError):
            KnowledgeStore().append(forged)
