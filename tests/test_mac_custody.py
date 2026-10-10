"""Keyed-MAC ledger custody tests (operator mandate 2026-10-10 §1.5).

Covers the P2 KEYED-MAC closure requirement — "human decision record +
keyed-chain implementation + tests":

- custody construction channels (env var, env key file, explicit test
  key) with fail-closed provisioning and entropy floor;
- secret hygiene: key material NEVER in repr/str/exported state;
- keyed chain signing/verification (rtledm. prefix + mac_key_id);
- the P2-demonstrated FULL-HISTORY REWRITE attack now DEFENDED in
  keyed mode (and still detected in unkeyed mode for partial edits);
- downgrade attacks (keyed session + unkeyed event; unkeyed session +
  keyed event) fail verification;
- rotation: retired keys keep verifying old events; new events sign
  under the new current key;
- persistence round-trip: restore verifies under the SAME custody and
  REFUSES under a DIFFERENT custody (fail closed => recovery required);
- runtime integration: an operational runtime wired with custody signs
  every ledger event and recovers cleanly after restart.

Test keys are EXPLICIT test fixtures (status TEST_FIXTURE) — nothing
here claims genuine custody is operational (operator §1.5).
"""

import json
from pathlib import Path

import pytest

from data_engine.runtime import (
    GATE_NAMES,
    KEYED_EVENT_HASH_PREFIX,
    UNKEYED_EVENT_HASH_PREFIX,
    LedgerEvent,
    LedgerFamily,
    LedgerError,
    MacCustody,
    MacCustodyError,
    ENV_KEY_FILE_VAR,
    ENV_KEY_VAR,
)
from data_engine.runtime.ledgers import _event_hash

TEST_KEY_A = b"A" * 32 + b"keyed-mac-test-fixture-a"
TEST_KEY_B = b"B" * 32 + b"keyed-mac-test-fixture-b"


def _custody_a():
    return MacCustody.from_test_key(TEST_KEY_A)


# ════════════════════════════════════════════════════════════════════
# 1. Custody construction channels
# ════════════════════════════════════════════════════════════════════

class TestCustodyConstruction:
    def test_test_fixture_status_is_not_operational(self):
        custody = _custody_a()
        assert custody.status == "TEST_FIXTURE"

    def test_env_channel_provisioning(self, monkeypatch):
        monkeypatch.setenv(ENV_KEY_VAR, (b"C" * 40).hex())
        custody = MacCustody.from_environment()
        assert custody.status == "OPERATIONAL"
        assert custody.current_key_id.startswith("mackey-")

    def test_env_key_file_channel(self, monkeypatch, tmp_path):
        key_file = tmp_path / "ledger_mac.key"
        key_file.write_text((b"D" * 48).hex() + "\n", encoding="utf-8")
        monkeypatch.setenv(ENV_KEY_FILE_VAR, str(key_file))
        custody = MacCustody.from_environment()
        assert custody.status == "OPERATIONAL"

    def test_env_key_file_must_be_absolute(self, monkeypatch):
        monkeypatch.setenv(ENV_KEY_VAR, "")  # force the file channel
        monkeypatch.setenv(ENV_KEY_FILE_VAR, "relative/key.file")
        with pytest.raises(MacCustodyError, match="ABSOLUTE"):
            MacCustody.from_environment()

    def test_missing_provisioning_fails_closed(self, monkeypatch):
        monkeypatch.delenv(ENV_KEY_VAR, raising=False)
        monkeypatch.delenv(ENV_KEY_FILE_VAR, raising=False)
        with pytest.raises(MacCustodyError, match="no key provisioned"):
            MacCustody.from_environment()

    def test_entropy_floor_rejects_short_keys(self):
        with pytest.raises(MacCustodyError, match="at least"):
            MacCustody.from_test_key(b"too-short")

    def test_key_id_is_a_fingerprint_not_material(self):
        custody = _custody_a()
        key_id = custody.current_key_id
        assert key_id.startswith("mackey-")
        assert len(key_id) == len("mackey-") + 16
        # The raw key bytes never appear in the fingerprint.
        assert TEST_KEY_A.hex() not in key_id

    def test_repr_never_leaks_material(self):
        custody = _custody_a()
        rendered = repr(custody) + str(custody)
        assert TEST_KEY_A.hex() not in rendered
        assert repr(TEST_KEY_A) not in rendered
        # The custody repr carries only the key-id fingerprint.
        assert custody.current_key_id in rendered
        assert "material" not in rendered.lower()


# ════════════════════════════════════════════════════════════════════
# 2. Keyed chains: signing + verification
# ════════════════════════════════════════════════════════════════════

class TestKeyedChains:
    def test_events_signed_with_keyed_prefix_and_key_id(self):
        family = LedgerFamily(mac_custody=_custody_a())
        event = family.record(
            "incident", "TEST_EVENT", "corr-1", "tester", {"a": 1}
        )
        assert event.event_hash.startswith(KEYED_EVENT_HASH_PREFIX)
        assert event.mac_key_id == _custody_a().current_key_id
        assert family.verify()
        assert family.verify_ledger("incident")

    def test_unkeyed_family_unchanged_legacy_behavior(self):
        family = LedgerFamily()
        event = family.record(
            "incident", "TEST_EVENT", "corr-1", "tester", {"a": 1}
        )
        assert event.event_hash.startswith(UNKEYED_EVENT_HASH_PREFIX)
        assert event.mac_key_id is None
        assert family.verify()
        assert not family.keyed

    def test_tampered_payload_detected_in_keyed_mode(self):
        family = LedgerFamily(mac_custody=_custody_a())
        family.record("incident", "E1", "c1", "t", {"a": 1})
        family.record("incident", "E2", "c2", "t", {"a": 2})
        # Tamper: mutate an event's payload without recomputing MACs.
        events = list(family.events("incident"))
        tampered = events[0].model_validate(
            {**events[0].model_dump(mode="json"), "payload": {"a": 999}}
        )
        family._chains["incident"]._events[0] = tampered
        assert not family.verify()

    def test_full_history_rewrite_defense_keyed_mode(self):
        """The P2-demonstrated attack: rewrite EVERY event and recompute
        every hash link (possible without the key on unkeyed chains).
        In keyed mode the rewrite cannot forge valid HMACs."""
        family = LedgerFamily(mac_custody=_custody_a())
        for i in range(5):
            family.record("order", f"ORDER_CREATED", f"c{i}", "oms",
                          {"order": i})
        attacker_view = [e.model_dump(mode="json")
                         for e in family.events("order")]
        # Attacker rewrites the whole history with the UNKEYED algorithm
        # (they do not hold the key) and strips mac metadata.
        rewritten = []
        prev = "0" * 64
        for i, ev in enumerate(attacker_view):
            ev = dict(ev)
            ev["sequence"] = i
            ev["prev_hash"] = prev
            ev["mac_key_id"] = None
            ev["event_hash"] = _event_hash({
                "ledger": ev["ledger"], "event_type": ev["event_type"],
                "sequence": ev["sequence"],
                "correlation_id": ev["correlation_id"],
                "parent_id": ev["parent_id"], "actor": ev["actor"],
                "payload_hash": ev["payload_hash"],
                "prev_hash": ev["prev_hash"],
            })
            prev = ev["event_hash"]
            rewritten.append(LedgerEvent.model_validate(ev))
        family._chains["order"]._events = rewritten
        # Under the SAME custody the downgrade is REFUSED.
        assert not family.verify()

    def test_full_history_rewrite_defense_unkeyed_mode_still_detected_for_payload_edits(self):
        """Honesty about the residual: without custody, an attacker who
        rewrites everything CAN re-forge the chain (documented accepted
        threat model) — but payload edits WITHOUT recomputation are
        still detected (tamper-evidence for partial edits holds)."""
        family = LedgerFamily()
        family.record("order", "ORDER_CREATED", "c0", "oms", {"x": 1})
        events = list(family.events("order"))
        tampered = events[0].model_validate(
            {**events[0].model_dump(mode="json"), "payload": {"x": 999}}
        )
        family._chains["order"]._events[0] = tampered
        assert not family.verify()

    def test_keyed_events_without_custody_fail_verification(self):
        """A keyed chain restored where NO custody is wired must fail —
        unverifiable is not verifiable (fail closed)."""
        keyed_family = LedgerFamily(mac_custody=_custody_a())
        keyed_family.record("incident", "E", "c", "t", {"a": 1})
        export = keyed_family.export_state()
        plain_family = LedgerFamily()  # no custody wired
        # The restore itself must raise (chains fail verification).
        with pytest.raises(LedgerError, match="FAILED hash verification"):
            plain_family.restore_state(export)

    def test_wrong_custody_refuses_restore(self):
        """Chains signed under key A cannot be restored under key B."""
        family_a = LedgerFamily(mac_custody=_custody_a())
        family_a.record("incident", "E", "c", "t", {"a": 1})
        export = family_a.export_state()
        family_b = LedgerFamily(
            mac_custody=MacCustody.from_test_key(TEST_KEY_B)
        )
        with pytest.raises(LedgerError, match="FAILED hash verification"):
            family_b.restore_state(export)

    def test_same_custody_restore_round_trip(self):
        family = LedgerFamily(mac_custody=_custody_a())
        for i in range(4):
            family.record("decision", f"D{i}", f"c{i}", "rt", {"i": i})
        export = json.loads(json.dumps(family.export_state()))
        restored = LedgerFamily(mac_custody=_custody_a())
        count = restored.restore_state(export)
        assert count == 4
        assert restored.verify()
        assert restored.head_hashes() == family.head_hashes()


# ════════════════════════════════════════════════════════════════════
# 3. Rotation
# ════════════════════════════════════════════════════════════════════

class TestRotation:
    def test_rotation_keeps_old_events_verifiable(self):
        custody = _custody_a()
        family = LedgerFamily(mac_custody=custody)
        family.record("incident", "UNDER_KEY_A", "c1", "t", {"k": "a"})
        old_key_id = custody.current_key_id
        new_key_id = custody.rotate(TEST_KEY_B)
        assert new_key_id != old_key_id
        family.record("incident", "UNDER_KEY_B", "c2", "t", {"k": "b"})
        events = family.events("incident")
        assert events[0].mac_key_id == old_key_id
        assert events[1].mac_key_id == new_key_id
        # Mixed-key history verifies: retired key still registered.
        assert family.verify()

    def test_rotation_to_same_key_refused(self):
        custody = _custody_a()
        with pytest.raises(MacCustodyError, match="no-op"):
            custody.rotate(TEST_KEY_A)

    def test_unregistered_key_id_fails(self):
        custody = _custody_a()
        family = LedgerFamily(mac_custody=custody)
        family.record("incident", "E", "c", "t", {"a": 1})
        # Foreign key id smuggled into an event -> verification fails.
        events = list(family.events("incident"))
        smuggled = events[0].model_validate({
            **events[0].model_dump(mode="json"),
            "mac_key_id": "mackey-0000000000000000",
        })
        family._chains["incident"]._events[0] = smuggled
        assert not family.verify()

    def test_key_ids_property_lists_fingerprints_only(self):
        custody = _custody_a()
        custody.rotate(TEST_KEY_B)
        ids = custody.key_ids
        assert ids[0] == custody.current_key_id
        assert len(ids) == 2
        assert all(i.startswith("mackey-") for i in ids)


# ════════════════════════════════════════════════════════════════════
# 4. Secret hygiene
# ════════════════════════════════════════════════════════════════════

class TestSecretHygiene:
    def test_exported_state_never_contains_key_material(self):
        family = LedgerFamily(mac_custody=_custody_a())
        family.record("incident", "E", "c", "t", {"a": 1})
        dumped = json.dumps(family.export_state())
        assert TEST_KEY_A.hex() not in dumped
        assert repr(TEST_KEY_A) not in dumped
        assert "mac_key_id" in dumped  # only the fingerprint rides along

    def test_ledgers_module_reads_no_environment(self):
        """The ledgers contract stays environment-free — only the
        explicit MacCustody.from_environment channel may read env."""
        source = (Path(__file__).resolve().parents[1]
                  / "src/data_engine/runtime/ledgers.py").read_text()
        assert "os.environ" not in source
        assert "getenv" not in source

    def test_mac_custody_env_reads_confined_to_provisioning(self):
        source = (Path(__file__).resolve().parents[1]
                  / "src/data_engine/runtime/mac_custody.py").read_text()
        # Both env reads (direct + key-file channels) live inside the
        # single from_environment provisioning method — nowhere else.
        assert source.count("os.environ") == 2
        start = source.index("def from_environment")
        end = source.index("def ", start + 10)
        provisioning_body = source[start:end]
        assert provisioning_body.count("os.environ") == 2

    def test_runtime_rejects_non_custody_object(self):
        from data_engine.runtime.contracts import RuntimeContractError
        from data_engine.runtime import TradingRuntime
        from test_runtime_recovery_integration import _op_config
        from test_runtime_e2e import _fit_world

        ens, cal = _fit_world()
        cfg = _op_config("mac-bogus-custody")
        with pytest.raises(RuntimeContractError, match="MacCustody"):
            TradingRuntime(cfg, ens, calibrator=cal, mac_custody="bogus")
        # LedgerFamily enforces the same type contract:
        with pytest.raises(LedgerError, match="MacCustody"):
            LedgerFamily(mac_custody="not-a-custody")


# ════════════════════════════════════════════════════════════════════
# 5. Runtime integration (operational runtime WITH custody)
# ════════════════════════════════════════════════════════════════════

class TestRuntimeWithCustody:
    def test_operational_runtime_signs_and_recovers(self, tmp_path):
        from test_runtime_recovery_integration import (
            _op_config,
            _ready_gate,
        )
        from test_runtime_e2e import _bars, _fit_world
        from data_engine.runtime import (
            ExecutionStateStore,
            TradingRuntime,
        )

        ens, cal = _fit_world()
        cfg = _op_config("mac-custody-e2e")
        store = ExecutionStateStore(tmp_path / "store")
        rt = TradingRuntime(
            cfg, ens, calibrator=cal, state_store=store,
            readiness_gate=_ready_gate(), mac_custody=_custody_a(),
        )
        rt.start()
        for bar in _bars(20):
            rt.process_bar(bar)
        assert rt.ledgers.keyed
        assert rt.ledgers.verify()
        heads = rt.ledgers.head_hashes()
        assert any(h.startswith(KEYED_EVENT_HASH_PREFIX)
                   for h in heads.values())
        # Restart with the SAME custody -> recovery verifies keyed chains.
        store2 = ExecutionStateStore(tmp_path / "store")
        rt3 = TradingRuntime(
            _op_config("mac-custody-e2e"), ens, calibrator=cal,
            state_store=store2, readiness_gate=_ready_gate(),
            mac_custody=_custody_a(),
        )
        rt3.start()
        assert rt3.ledgers.verify()
        # Recovery legitimately APPENDS incident events on resume — the
        # restored chains must extend (not contradict) the pre-restart
        # state, and every non-incident ledger head must match exactly.
        heads3 = rt3.ledgers.head_hashes()
        for name, head in heads.items():
            if name == "incident":
                assert len(rt3.ledgers.events("incident")) >= len(
                    rt.ledgers.events("incident"))
            else:
                assert heads3[name] == head

    def test_runtime_mac_custody_property(self, tmp_path):
        from test_runtime_recovery_integration import _operational
        rt = _operational("mac-prop", tmp_path / "store")
        assert rt.ledgers.mac_custody is None  # legacy default
        assert not rt.ledgers.keyed


# ════════════════════════════════════════════════════════════════════
# 6. Honest custody-status reporting
# ════════════════════════════════════════════════════════════════════

class TestCustodyStatusHonesty:
    def test_env_var_names_are_documented_constants(self):
        assert ENV_KEY_VAR == "RUNTIME_LEDGER_MAC_KEY"
        assert ENV_KEY_FILE_VAR == "RUNTIME_LEDGER_MAC_KEY_FILE"

    def test_gate_set_unchanged_by_custody(self):
        """Custody is NOT a new readiness gate — it feeds the documented
        GOVERNANCE_READY evidence discipline (see the custody decision
        record). The gate count stays 32 (this cycle's extension)."""
        assert len(GATE_NAMES) == 32
        assert "MAC_CUSTODY_READY" not in GATE_NAMES
