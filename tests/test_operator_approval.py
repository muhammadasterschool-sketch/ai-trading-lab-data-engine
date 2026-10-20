"""FIX-9 (B-P0-03) — trusted operator-approval evidence: adversarial
security tests.

The P0-P3 master audit hypothesis: "Caller-supplied ``passed=True``,
arbitrary free-text evidence, or operator evidence may satisfy
trust-dependent gates." CONFIRMED at audit time (the old
``test_composition_root.py::_operator_evidence`` helper fabricated
``passed=True`` free-text for all 32 gates — including the three
human gates — and ``compose_operational_session(started=True)``
accepted it). These tests pin the CLOSED state:

- plain ``GateEvidence`` for a human gate is REFUSED
  (``E_EVIDENCE_UNTRUSTED``) — the headline regression test;
- a forged/expired/wrong-scope/wrong-digest/REJECT approval record
  fails with a stable reason code;
- an HMAC signature made WITHOUT the operator key cannot verify;
- ``TrustedGateEvidence`` re-verification happens INSIDE the
  composition root against the operator key — hand-crafting the
  subclass does not shortcut the boundary;
- no environment variable can flip the readiness verdict;
- the human-gate set cannot drift between the two modules.

All venues/fixtures are paper/mock. No network, no real credentials,
no live trading. PAPER_READY stays FALSE until the operator's REAL
signed dependencies close.
"""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from data_engine.runtime import GATE_NAMES, GateEvidence, PaperReadinessGate
from data_engine.runtime.composition import (
    HUMAN_EVIDENCE_GATES,
    CompositionError,
)
from data_engine.runtime.operator_approval import (
    APPROVAL_KINDS,
    HUMAN_GATES,
    MIN_APPROVAL_KEY_BYTES,
    OPERATOR_APPROVAL_ENV_KEY,
    OPERATOR_APPROVAL_ENV_KEY_FILE,
    OperatorApprovalError,
    OperatorApprovalKey,
    OperatorApprovalRecord,
    TrustedGateEvidence,
    build_trusted_evidence,
    sign_approval,
    verify_approval,
    verify_human_gate_evidence,
)

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(days=30)


def _key() -> OperatorApprovalKey:
    return OperatorApprovalKey(secrets.token_bytes(32))


def _record(
    *,
    gate: str = "GOVERNANCE_READY",
    decision: str = "APPROVE",
    scope: str = "*",
    issued_at: datetime = NOW - timedelta(hours=1),
    expires_at: datetime = LATER,
    digest: str = "",
    kind: str = "RECORDED_EVIDENCE",
    principal: str = "operator-test",
    reason: str = "recorded operator decision",
    record_id: str = "approval-1",
) -> OperatorApprovalRecord:
    return OperatorApprovalRecord(
        record_id=record_id,
        approval_kind=kind,
        principal=principal,
        decision=decision,
        gate=gate,
        scope=scope,
        issued_at=issued_at,
        expires_at=expires_at,
        artifact_digest=digest,
        reason=reason,
    )


def _signed(gate: str = "GOVERNANCE_READY", **kwargs):
    key = _key()
    record = _record(gate=gate, **kwargs)
    signature = sign_approval(record, key)
    return key, record, signature


# ---------------------------------------------------------------------------
# 1. the headline regression: caller-supplied free-text evidence is
#    refused for human gates (B-P0-03)
# ---------------------------------------------------------------------------

class TestUntrustedEvidenceRefused:

    def test_plain_passed_true_free_text_refused(self):
        """THE B-P0-03 proof: a plain GateEvidence with passed=True
        and arbitrary free text CANNOT satisfy a human gate."""
        key = _key()
        for gate in sorted(HUMAN_EVIDENCE_GATES):
            fabricated = GateEvidence(
                gate=gate,
                component="operator-recorded:whatever",
                check="operator_evidence_bundle",
                evidence="operator-recorded evidence on file",
                passed=True,
            )
            with pytest.raises(OperatorApprovalError) as excinfo:
                verify_human_gate_evidence(fabricated, key=key, as_of=NOW)
            assert excinfo.value.reason_code == "E_EVIDENCE_UNTRUSTED"

    def test_plain_evidence_refused_even_without_any_key(self):
        """No key provisioned at all: still refused (fail closed,
        never a silent fallback)."""
        fabricated = GateEvidence(
            gate="REAL_DATA_READY",
            component="x",
            check="y",
            evidence="definitely real data, trust me",
            passed=True,
        )
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_human_gate_evidence(fabricated, key=None, as_of=NOW)
        assert excinfo.value.reason_code == "E_EVIDENCE_UNTRUSTED"

    def test_composition_root_refuses_fabricated_bundle(self, tmp_path,
                                                         monkeypatch):
        """End-to-end through compose_operational_session: the old
        attack (free-text bundle for all 32 gates) now fails closed
        with the stable reason code surfaced in the CompositionError."""
        from data_engine.brokers.redaction import BrokerCredential
        from data_engine.runtime.composition import (
            compose_operational_session,
        )
        from tests.test_composition_root import (
            _fit_world,
            _op_config,
            _session_config,
            _specs,
        )
        from tests.test_runtime_authoritative_venue import _clock

        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        ens, cal = _fit_world()
        # The test provisions the approval key explicitly (it acts as
        # the operator WITH a key) — so composition reaches the trust
        # boundary check itself, where the fabricated free-text bundle
        # is refused.
        honest_key = _key()
        bundle = tuple(
            GateEvidence(
                gate=name,
                component=f"operator-recorded:{name.lower()}",
                check="operator_evidence_bundle",
                evidence="operator-recorded evidence on file",
                passed=True,
            )
            for name in GATE_NAMES
        )
        with pytest.raises(CompositionError) as excinfo:
            compose_operational_session(
                config=_op_config(_session_config("b-p0-03-attack")),
                ensemble=ens,
                calibrator=cal,
                state_dir=Path(tmp_path) / "state",
                ledger_path=Path(tmp_path) / "ledger.json",
                venue_journal_path=Path(tmp_path) / "venue.json",
                venue_account_id="acct-attack",
                venue_credential=BrokerCredential("acct-attack", "s"),
                instruments=_specs(),
                venue_clock=_clock(),
                operator_evidence=bundle,
                operator_approval_key=honest_key,
                venue_sleeper=lambda s: None,
            )
        assert "E_EVIDENCE_UNTRUSTED" in str(excinfo.value)

    def test_handcrafted_trusted_subclass_still_needs_valid_signature(
        self,
    ):
        """Constructing the TrustedGateEvidence subclass directly with
        a garbage signature cannot shortcut verification — the model
        rejects malformed signatures at construction and the root
        re-verifies regardless."""
        key, record, _sig = _signed()
        with pytest.raises(Exception, match="E_APPROVAL_SIGNATURE_INVALID"):
            TrustedGateEvidence(
                gate=record.gate,
                component="operator-approval",
                check="verify_operator_approval",
                evidence="hand-crafted",
                passed=True,
                approval_record=record,
                approval_signature="zz" * 31,  # wrong SHAPE (62 chars)
                verification=None,
            )

    def test_valid_shape_wrong_signature_fails_verification(self):
        """A 64-hex-char signature computed by a DIFFERENT key fails
        HMAC verification (the caller cannot forge without the key)."""
        key, record, _sig = _signed()
        attacker_key = _key()
        forged = attacker_key.sign(
            __import__("data_engine.runtime.operator_approval", fromlist=[
                "approval_signature_payload"
            ]).approval_signature_payload(record)
        )
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, forged, key, as_of=NOW,
                expected_gate=record.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_SIGNATURE_INVALID"


# ---------------------------------------------------------------------------
# 2. typed record validation (fail closed, stable codes)
# ---------------------------------------------------------------------------

class TestRecordValidation:

    def test_unknown_gate_refused(self):
        with pytest.raises(Exception, match="E_APPROVAL_UNKNOWN_GATE"):
            _record(gate="NOT_A_GATE")

    def test_readiness_approval_for_non_human_gate_refused(self):
        """An approval cannot substitute for first-hand code evidence
        on a component gate."""
        with pytest.raises(Exception, match="E_APPROVAL_NOT_HUMAN_GATE"):
            _record(gate="OMS_READY")

    def test_control_kinds_may_reference_any_gate(self):
        """Risk-limit/kill-switch/soak control records are audited
        actions and may reference any gate they affect."""
        rec = _record(gate="RISK_READY", kind="RISK_LIMIT_CHANGE")
        assert rec.approval_kind == "RISK_LIMIT_CHANGE"

    def test_bad_decision_refused_at_verify(self):
        key, record, signature = _signed(decision="REJECT")
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_BAD_DECISION"

    def test_naive_datetimes_refused(self):
        with pytest.raises(Exception, match="E_APPROVAL_MALFORMED"):
            OperatorApprovalRecord(
                record_id="x1",
                approval_kind="RECORDED_EVIDENCE",
                principal="p",
                decision="APPROVE",
                gate="GOVERNANCE_READY",
                issued_at=datetime(2026, 1, 1),       # naive — ambiguous
                expires_at=datetime(2026, 2, 1),
                reason="r",
            )

    def test_expires_before_issued_refused(self):
        with pytest.raises(Exception, match="E_APPROVAL_MALFORMED"):
            _record(
                issued_at=NOW,
                expires_at=NOW - timedelta(seconds=1),
            )

    def test_unknown_approval_kind_refused(self):
        with pytest.raises(Exception, match="E_APPROVAL_MALFORMED"):
            _record(kind="MADE_UP_KIND")

    def test_extra_fields_refused(self):
        with pytest.raises(Exception):
            OperatorApprovalRecord(
                record_id="x2",
                approval_kind="RECORDED_EVIDENCE",
                principal="p",
                decision="APPROVE",
                gate="GOVERNANCE_READY",
                issued_at=NOW - timedelta(hours=1),
                expires_at=LATER,
                reason="r",
                smuggled_field="not allowed",
            )

    def test_approval_kinds_are_the_audited_set(self):
        """Task 7: source approval, paper-env authorization, risk-limit
        change, kill-switch reset, soak start/stop + recorded
        evidence."""
        for kind in (
            "SOURCE_APPROVAL",
            "PAPER_ENVIRONMENT_AUTHORIZATION",
            "RISK_LIMIT_CHANGE",
            "KILLSWITCH_RESET",
            "SOAK_START",
            "SOAK_STOP",
            "RECORDED_EVIDENCE",
        ):
            assert kind in APPROVAL_KINDS


# ---------------------------------------------------------------------------
# 3. validity window, scope, digest
# ---------------------------------------------------------------------------

class TestVerifyApprovalSemantics:

    def test_expired_refused(self):
        key, record, signature = _signed(
            issued_at=NOW - timedelta(days=40),
            expires_at=NOW - timedelta(days=10),
        )
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_EXPIRED"

    def test_not_yet_valid_refused(self):
        key, record, signature = _signed(
            issued_at=NOW + timedelta(hours=1),
            expires_at=NOW + timedelta(days=30),
        )
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_NOT_YET_VALID"

    def test_gate_scope_mismatch_refused(self):
        key, record, signature = _signed(gate="GOVERNANCE_READY")
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate="REAL_DATA_READY",
            )
        assert excinfo.value.reason_code == "E_APPROVAL_SCOPE_MISMATCH"

    def test_instrument_scope_pin_refused_for_other_scope(self):
        key, record, signature = _signed(scope="session-alpha")
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
                expected_scope="session-beta",
            )
        assert excinfo.value.reason_code == "E_APPROVAL_SCOPE_MISMATCH"

    def test_wildcard_scope_covers_any_session(self):
        key, record, signature = _signed(scope="*")
        receipt = verify_approval(
            record, signature, key, as_of=NOW,
            expected_gate=record.gate,
            expected_scope="session-beta",
        )
        assert receipt.gate == record.gate

    def test_digest_pin_mismatch_refused(self):
        key, record, signature = _signed(digest="a" * 64)
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
                expected_digest="b" * 64,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_DIGEST_MISMATCH"

    def test_unpinned_record_accepted_with_expected_digest(self):
        """artifact_digest='' means 'unpinned' — the operator chose not
        to pin the approval to one config artifact."""
        key, record, signature = _signed(digest="")
        receipt = verify_approval(
            record, signature, key, as_of=NOW,
            expected_gate=record.gate,
            expected_digest="b" * 64,
        )
        assert receipt.record_id == record.record_id

    def test_boundary_expiry_is_exclusive(self):
        key, record, signature = _signed(expires_at=NOW)
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                record, signature, key, as_of=NOW,
                expected_gate=record.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_EXPIRED"

    def test_tampered_record_field_breaks_signature(self):
        key, record, signature = _signed()
        tampered = record.model_copy(update={"reason": "something else"})
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_approval(
                tampered, signature, key, as_of=NOW,
                expected_gate=tampered.gate,
            )
        assert excinfo.value.reason_code == "E_APPROVAL_SIGNATURE_INVALID"


# ---------------------------------------------------------------------------
# 4. key custody discipline
# ---------------------------------------------------------------------------

class TestKeyCustody:

    def test_strength_floor(self):
        with pytest.raises(OperatorApprovalError):
            OperatorApprovalKey(b"too-short")

    def test_env_channel_direct(self, monkeypatch):
        key_hex = secrets.token_hex(32)
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY, key_hex)
        key = OperatorApprovalKey.from_environment()
        assert key.key_id.startswith("appkey-")

    def test_env_channel_raw_bytes(self, monkeypatch):
        monkeypatch.setenv(
            OPERATOR_APPROVAL_ENV_KEY, "x" * MIN_APPROVAL_KEY_BYTES,
        )
        OperatorApprovalKey.from_environment()  # raw (non-hex) accepted

    def test_env_channel_file(self, monkeypatch, tmp_path):
        key_file = tmp_path / "approval.key"
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY_FILE,
                           str(key_file))
        key = OperatorApprovalKey.from_environment()
        assert key.key_id.startswith("appkey-")

    def test_env_channel_file_must_be_absolute(self, monkeypatch):
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY_FILE, "relative.key")
        with pytest.raises(OperatorApprovalError) as excinfo:
            OperatorApprovalKey.from_environment()
        assert excinfo.value.reason_code == "E_APPROVAL_KEY_UNAVAILABLE"

    def test_missing_key_fails_closed(self, monkeypatch):
        monkeypatch.delenv(OPERATOR_APPROVAL_ENV_KEY, raising=False)
        monkeypatch.delenv(OPERATOR_APPROVAL_ENV_KEY_FILE, raising=False)
        with pytest.raises(OperatorApprovalError) as excinfo:
            OperatorApprovalKey.from_environment()
        assert excinfo.value.reason_code == "E_APPROVAL_KEY_UNAVAILABLE"

    def test_weak_env_key_refused(self, monkeypatch):
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY, "short")
        with pytest.raises(OperatorApprovalError) as excinfo:
            OperatorApprovalKey.from_environment()
        assert excinfo.value.reason_code == "E_APPROVAL_MALFORMED"

    def test_repr_and_str_never_leak_material(self):
        key = _key()
        material = key._material.hex()
        for text in (repr(key), str(key)):
            assert material not in text
            assert "MASKED" in text

    def test_error_messages_never_contain_key_material(self, monkeypatch):
        key_hex = secrets.token_hex(32)
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY, key_hex)
        key = OperatorApprovalKey.from_environment()
        key, record, signature = _signed()
        forged = "0" * 64
        try:
            verify_approval(
                record, forged, key, as_of=NOW,
                expected_gate=record.gate,
            )
        except OperatorApprovalError as exc:
            assert key._material.hex() not in str(exc)
            assert key._material.hex() not in exc.detail

    def test_module_reads_env_only_in_from_environment(self):
        """Structural pin: the ONLY environment access in this module
        is inside OperatorApprovalKey.from_environment (readiness gates
        stay environment-free — same discipline as mac_custody)."""
        import inspect
        import data_engine.runtime.operator_approval as mod

        source = inspect.getsource(mod)
        lines = source.splitlines()
        env_lines = [
            (i, ln) for i, ln in enumerate(lines, start=1)
            if "os.environ" in ln
        ]
        assert env_lines, "expected at least one os.environ read"
        from_environment_src = inspect.getsource(
            OperatorApprovalKey.from_environment
        )
        for _lineno, ln in env_lines:
            assert "os.environ" in ln
            assert "os.environ" in from_environment_src or True
        # every os.environ read must sit inside from_environment's span
        tree = __import__("ast").parse(source)
        env_nodes = []
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").Attribute) and \
                    getattr(node.value, "id", None) == "os" and \
                    node.attr == "environ":
                env_nodes.append(node.lineno)
        fe_start = source.index(
            "def from_environment"
        )
        fe_line = source[:fe_start].count("\n") + 1
        fe_end = fe_line + len(
            __import__("inspect").getsource(
                OperatorApprovalKey.from_environment
            ).splitlines()
        )
        for lineno in env_nodes:
            assert fe_line <= lineno <= fe_end, (
                f"os.environ access at line {lineno} outside "
                "from_environment — environment-free discipline violated"
            )


# ---------------------------------------------------------------------------
# 5. trusted path + composition integration
# ---------------------------------------------------------------------------

class TestTrustedPath:

    def test_sign_verify_build_round_trip(self):
        key, record, signature = _signed()
        evidence = build_trusted_evidence(record, signature, key, as_of=NOW)
        assert evidence.passed is True
        assert isinstance(evidence, TrustedGateEvidence)
        assert evidence.verification.key_id == key.key_id
        # re-verification via the root entry point
        out = verify_human_gate_evidence(evidence, key=key, as_of=NOW)
        assert out is evidence

    def test_trusted_evidence_without_key_fails_closed(self):
        key, record, signature = _signed()
        evidence = build_trusted_evidence(record, signature, key, as_of=NOW)
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_human_gate_evidence(evidence, key=None, as_of=NOW)
        assert excinfo.value.reason_code == "E_APPROVAL_KEY_UNAVAILABLE"

    def test_trusted_evidence_expired_at_reverification(self):
        """Evidence built while valid FAILS re-verification once the
        approval window has passed (as_of advances)."""
        key, record, signature = _signed(expires_at=NOW + timedelta(days=5))
        evidence = build_trusted_evidence(record, signature, key, as_of=NOW)
        with pytest.raises(OperatorApprovalError) as excinfo:
            verify_human_gate_evidence(
                evidence, key=key,
                as_of=NOW + timedelta(days=6),
            )
        assert excinfo.value.reason_code == "E_APPROVAL_EXPIRED"

    def test_signed_bundle_flows_through_composition(self, tmp_path,
                                                     monkeypatch):
        """The legitimate operator path: SIGNED approvals for the three
        human gates + plain recorded evidence for the rest compose and
        start successfully (paper/mock venue, no network)."""
        from tests.test_composition_root import _compose
        composed = _compose(tmp_path, monkeypatch, started=True)
        report = composed.start_report
        assert report is not None and report.post_start_verified
        ev = {e.gate: e for e in composed.evidence}
        for gate in HUMAN_EVIDENCE_GATES:
            assert isinstance(ev[gate], TrustedGateEvidence)
            assert ev[gate].passed

    def test_wrong_key_on_reverification_fails_closed(self, tmp_path,
                                                      monkeypatch):
        """The composition root re-verifies with ITS key: evidence
        signed by a different (attacker) key is refused."""
        from data_engine.brokers.redaction import BrokerCredential
        from data_engine.runtime.composition import (
            compose_operational_session,
        )
        from tests.test_composition_root import (
            _fit_world,
            _op_config,
            _session_config,
            _specs,
        )
        from tests.test_runtime_authoritative_venue import _clock

        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        attacker_key = _key()
        honest_key = _key()
        bundle = []
        for gate in sorted(HUMAN_EVIDENCE_GATES):
            record = _record(gate=gate)
            signature = sign_approval(record, attacker_key)
            bundle.append(build_trusted_evidence(
                record, signature, attacker_key, as_of=datetime.now(UTC),
            ))
        ens, cal = _fit_world()
        with pytest.raises(CompositionError) as excinfo:
            compose_operational_session(
                config=_op_config(_session_config("wrong-key")),
                ensemble=ens,
                calibrator=cal,
                state_dir=Path(tmp_path) / "state",
                ledger_path=Path(tmp_path) / "ledger.json",
                venue_journal_path=Path(tmp_path) / "venue.json",
                venue_account_id="acct-wrong-key",
                venue_credential=BrokerCredential("acct-wrong-key", "s"),
                instruments=_specs(),
                venue_clock=_clock(),
                operator_evidence=tuple(bundle),
                operator_approval_key=honest_key,
                venue_sleeper=lambda s: None,
            )
        assert "E_APPROVAL_SIGNATURE_INVALID" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 6. no environment bypass of the readiness verdict
# ---------------------------------------------------------------------------

class TestNoEnvironmentBypass:

    def test_env_cannot_flip_gate_verdict(self, monkeypatch):
        """FORCE_PAPER_READY and friends are structurally ignored:
        the gate reads no environment at all (§53)."""
        monkeypatch.setenv("FORCE_PAPER_READY", "1")
        monkeypatch.setenv("PAPER_READY", "true")
        monkeypatch.setenv("GOVERNANCE_READY", "1")
        monkeypatch.setenv("OPERATIONAL_FEED_READY", "yes")
        gate = PaperReadinessGate()
        report = gate.evaluate()
        assert report.paper_ready is False
        assert set(report.failed_gates) == set(GATE_NAMES)

    def test_env_cannot_satisfy_human_gates_in_compose(self, tmp_path,
                                                       monkeypatch):
        """Env vars claiming approvals do nothing without the SIGNED
        bundle — the composed session's human gates stay FALSE and
        start() refuses."""
        from tests.test_composition_root import _compose
        monkeypatch.setenv("OPERATOR_APPROVALS_JSON", '{"all": true}')
        monkeypatch.setenv("GOVERNANCE_APPROVED", "1")
        composed = _compose(tmp_path, monkeypatch,
                            operator_evidence="no-human")
        from data_engine.runtime.composition import (
            CompositionStartRefused,
        )
        with pytest.raises(CompositionStartRefused) as excinfo:
            composed.start()
        assert set(HUMAN_EVIDENCE_GATES) <= set(excinfo.value.failed_gates)


# ---------------------------------------------------------------------------
# 7. drift pins
# ---------------------------------------------------------------------------

class TestDriftPins:

    def test_human_gate_sets_agree(self):
        """operator_approval.HUMAN_GATES and
        composition.HUMAN_EVIDENCE_GATES must stay identical (the two
        modules re-declare the set to avoid a circular import)."""
        assert HUMAN_GATES == HUMAN_EVIDENCE_GATES

    def test_human_gates_are_subset_of_gate_names(self):
        assert HUMAN_GATES <= set(GATE_NAMES)

    def test_reason_codes_are_the_documented_set(self):
        """The stable reason-code vocabulary (documented in the module
        docstring) — governance/observability depends on these strings
        being stable."""
        import data_engine.runtime.operator_approval as mod
        source = mod.__doc__
        for code in (
            "E_APPROVAL_MISSING",
            "E_APPROVAL_MALFORMED",
            "E_APPROVAL_UNKNOWN_GATE",
            "E_APPROVAL_NOT_HUMAN_GATE",
            "E_APPROVAL_BAD_DECISION",
            "E_APPROVAL_SCOPE_MISMATCH",
            "E_APPROVAL_DIGEST_MISMATCH",
            "E_APPROVAL_NOT_YET_VALID",
            "E_APPROVAL_EXPIRED",
            "E_APPROVAL_SIGNATURE_INVALID",
            "E_APPROVAL_KEY_UNAVAILABLE",
            "E_EVIDENCE_UNTRUSTED",
        ):
            assert code in source
