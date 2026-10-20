"""Milestone A Stage C — composition root + readiness evidence
suppliers + conservative reservation-reconciliation driver
(patch plan P5; findings F-05, F-13, F-14, F-25; mandates C1-C3).

Regression tests written FIRST (Part 5 discipline). The defects being
closed are STRUCTURAL ABSENCES verified in Stage A
(artifacts/stage-a/02-FINDINGS-REGISTER.md):

- F-05 (HIGH): no production composition root — ``TradingRuntime(``
  was constructed only in tests; nothing assembled a validated
  operating runtime and no production path supplied readiness
  evidence (the supervisor could only exit 2).
- F-13 (MED): the feed-staleness watchdog defaulted to DISABLED; an
  operational session could be composed with no staleness budget.
- F-14 (MED): gate context (market_open/model_valid) and risk
  ceilings (max_volatility=0.10, max_spread_fraction=0.01,
  portfolio RiskLimits) were HARDCODED in runtime wiring.
- F-25 (INFO): keyed-MAC custody implemented but never provisioned
  by any production path.

C3 mandate (U-19): a conservative reconciliation driver over
journalled reservations vs OMS records — confirmed-absence vs
timeout; ambiguous PRESERVED (never released); duplicate-signal
idempotent; every decision durably recorded; the driver itself has
NO submission capability.

All venues in these tests are paper/mock fixtures. No real broker,
no network, no real credentials. LIVE TRADING REMAINS NOT AUTHORIZED.
PAPER_READY stays FALSE until the recorded human dependencies close.
"""

import io
import secrets as _secrets
from datetime import UTC as _UTC
from datetime import datetime as _dt
from datetime import timedelta
from datetime import timedelta as _td
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_engine.brokers.redaction import BrokerCredential
from data_engine.runtime import (
    GATE_NAMES,
    GateEvidence,
    PaperReadinessGate,
    RuntimeConfig,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    CONSTRUCTION_ORDER,
    HUMAN_EVIDENCE_GATES,
    OPERATOR_RECORDED_EVIDENCE,
    CompositionError,
    CompositionStartRefused,
    OperationalSessionConfig,
    ReservationReconciler,
    compose_operational_session,
)
from data_engine.runtime.operator_approval import (
    OperatorApprovalKey,
    OperatorApprovalRecord,
    TrustedGateEvidence,
    build_trusted_evidence,
    sign_approval,
)
from data_engine.runtime.contracts import OrderLifecycle
from data_engine.runtime.risk_gate import (
    GateCeilings,
    GateContextDefaults,
    RuntimeRiskLimits,
)
from data_engine.runtime.submission_ledger import (
    PRE_VENUE_OUTCOME,
    ReservationState,
    SubmissionLedger,
    SubmissionPolicy,
)
from data_engine.runtime.service import PaperRuntimeService

from test_runtime_authoritative_venue import ACCOUNT, SECRET, SYMBOL
from test_runtime_e2e import _fit_world
from test_submission_ledger import T0, _clock, _policy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _pins(ens):
    """Operator model pins: every ensemble member's model hash."""
    return tuple(m.artifact().model_hash for m in ens.members)


def _session_config(session="stage-c", **over):
    """Operational base config: watchdog SET (F-13), model pins
    present (F-14 model_valid provenance), ephemeral fixture off."""
    ens, _ = _fit_world()
    cfg = dict(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        max_crash_probability=0.0,
        max_position_units=Decimal("1000"),
        max_feed_staleness_seconds=900,
        pinned_model_hashes=_pins(ens),
    )
    cfg.update(over)
    return RuntimeConfig(**cfg)


def _op_config(session_cfg):
    return OperationalSessionConfig(session=session_cfg)


def _mac_env(monkeypatch):
    key = _secrets.token_hex(32)
    monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", key)
    return key


def _approval_key():
    """FIX-9: the operator approval signing key (test fixture — the
    composition root still re-verifies signatures against it)."""
    return OperatorApprovalKey(_secrets.token_bytes(32))


def _signed_human_evidence(key, *, gates, as_of=None):
    """FIX-9: build SIGNED, trusted evidence for human gates (the
    operator records the decision and signs it; the old free-text
    ``passed=True`` bundle is refused — see
    ``test_operator_approval.py`` for the adversarial proof)."""
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    as_of = as_of if as_of is not None else _dt.now(_UTC)
    out = []
    for name in gates:
        if name not in HUMAN_EVIDENCE_GATES:
            continue
        record = OperatorApprovalRecord(
            record_id=f"approval-{name.lower()}-1",
            approval_kind="RECORDED_EVIDENCE",
            principal="operator-test",
            decision="APPROVE",
            gate=name,
            scope="*",
            issued_at=as_of - _td(hours=1),
            expires_at=as_of + _td(days=30),
            artifact_digest="",
            reason=f"recorded operator evidence for {name}",
        )
        signature = sign_approval(record, key)
        out.append(build_trusted_evidence(
            record, signature, key, as_of=as_of,
        ))
    return tuple(out)


def _operator_evidence(passed=True, gates=None, key=None):
    """The operator's recorded-evidence bundle (the ONLY legitimate
    source for recorded/human gates — tests act as the operator and
    SIGN the records, FIX-9). Non-human gates still carry plain
    recorded evidence (the composition root's first-hand component
    evidence overrides those where applicable)."""
    names = gates if gates is not None else GATE_NAMES
    as_of = _dt.now(_UTC)
    human = tuple(
        g for g in names if g in HUMAN_EVIDENCE_GATES
    )
    non_human = tuple(
        g for g in names if g not in HUMAN_EVIDENCE_GATES
    )
    bundle = _signed_human_evidence(
        key if key is not None else _approval_key(),
        gates=human,
        as_of=as_of,
    )
    bundle += tuple(
        GateEvidence(
            gate=name,
            component=f"operator-recorded:{name.lower()}",
            check="operator_evidence_bundle",
            evidence=(
                "operator-recorded evidence on file"
                if passed else
                "operator evidence FAILS for this gate"
            ),
            passed=passed,
        )
        for name in non_human
    )
    return bundle


def _specs():
    from test_runtime_authoritative_venue import _specs as _s
    return _s()


def _compose(tmp_path, monkeypatch, *, session="stage-c",
             operator_evidence="full", started=False, config=None,
             set_mac_env=True):
    ens, cal = _fit_world()
    if set_mac_env:
        _mac_env(monkeypatch)
    approval_key = _approval_key()
    cfg = config if config is not None else _op_config(
        _session_config(session),
    )
    if operator_evidence == "full":
        bundle = _operator_evidence(key=approval_key)
    elif operator_evidence == "no-human":
        bundle = _operator_evidence(
            gates=tuple(g for g in GATE_NAMES
                        if g not in HUMAN_EVIDENCE_GATES),
            key=approval_key,
        )
    elif operator_evidence == "drop-data-ready":
        bundle = _operator_evidence(
            gates=tuple(g for g in GATE_NAMES if g != "DATA_READY"),
            key=approval_key,
        )
    else:
        bundle = ()
    return compose_operational_session(
        config=cfg,
        ensemble=ens,
        calibrator=cal,
        state_dir=Path(tmp_path) / "state",
        ledger_path=Path(tmp_path) / "ledger.json",
        venue_journal_path=Path(tmp_path) / "venue.json",
        venue_account_id=ACCOUNT,
        venue_credential=BrokerCredential(ACCOUNT, SECRET),
        instruments=_specs(),
        venue_clock=_clock(),
        operator_evidence=bundle,
        operator_approval_key=approval_key,
        venue_sleeper=lambda s: None,
        started=started,
    )


# ---------------------------------------------------------------------------
# F-13 / F-14 / mandate: operational config validation
# ---------------------------------------------------------------------------

class TestOperationalConfigValidation:

    def test_f13_watchdog_unset_refuses(self):
        """F-13: an operational session with the feed watchdog unset
        (None) is REFUSED at config validation — the composition
        root never assembles an unwatched live-clock session."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="max_feed_staleness"):
            _op_config(_session_config(
                "f13", max_feed_staleness_seconds=None,
            ))

    def test_ephemeral_fixture_refused(self):
        """Operational sessions are NEVER test fixtures (BLOCKER 1)."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="ephemeral"):
            _op_config(_session_config(
                "eph", ephemeral_test_fixture=True,
            ))

    def test_f14_pinned_model_hashes_required(self):
        """F-14 (model_valid provenance): operational sessions pin
        the ensemble identity — an unpinned model cannot back an
        honest model_valid=True context value."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="pinned_model_hashes"):
            _op_config(_session_config(
                "nopin", pinned_model_hashes=(),
            ))

    def test_defaults_carry_ratified_provenance(self):
        """Part 3 owner-ratified paper defaults: 5/60s + 10 open
        orders + 1s spacing; ceilings 0.10/0.01; leverage 1.0."""
        cfg = _op_config(_session_config("prov"))
        assert cfg.risk_limits == RuntimeRiskLimits(
            max_orders_per_window=5, window_seconds=60.0,
            max_open_orders=10,
        )
        assert cfg.submission_policy == SubmissionPolicy()
        assert cfg.gate_ceilings == GateCeilings()
        assert float(cfg.gate_ceilings.max_volatility) == 0.10
        assert cfg.gate_ceilings.max_spread_fraction == Decimal("0.01")
        assert cfg.gate_context == GateContextDefaults()
        assert cfg.portfolio_limits.max_leverage == Decimal("1.0")
        assert cfg.portfolio_limits.max_position_units == Decimal("1000")


# ---------------------------------------------------------------------------
# C1: the composition root
# ---------------------------------------------------------------------------

class TestCompositionRoot:

    def test_construction_order_pinned(self, tmp_path, monkeypatch):
        """The documented construction order is code + test pinned
        (F-05: explicit root, no hidden globals, reviewable order)."""
        composed = _compose(tmp_path, monkeypatch)
        assert composed.construction_order == CONSTRUCTION_ORDER
        assert CONSTRUCTION_ORDER.index("config") < \
            CONSTRUCTION_ORDER.index("state_store") < \
            CONSTRUCTION_ORDER.index("submission_ledger") < \
            CONSTRUCTION_ORDER.index("runtime") < \
            CONSTRUCTION_ORDER.index("reconciliation_driver") < \
            CONSTRUCTION_ORDER.index("readiness_evidence") < \
            CONSTRUCTION_ORDER.index("lifecycle")

    def test_type_state(self, tmp_path, monkeypatch):
        composed = _compose(tmp_path, monkeypatch)
        assert isinstance(composed.runtime, TradingRuntime)
        assert isinstance(composed.ledger, SubmissionLedger)
        assert composed.readiness_gate is not None
        # not started yet — lifecycle is the operator's explicit call
        assert composed.runtime.state is RuntimeState.INIT

    def test_ledger_mandatory_for_operational_sessions(
        self, tmp_path, monkeypatch,
    ):
        """C1 mandate: the durable ledger is NOT optional in the
        composed operational runtime (Stage B made it opt-in per
        seam; composition makes it mandatory)."""
        composed = _compose(tmp_path, monkeypatch)
        assert composed.runtime._submission_ledger is composed.ledger

    def test_f14_no_hardcoded_gate_context(self, tmp_path, monkeypatch):
        """F-14: the composed runtime's gate ceilings / context /
        portfolio limits are the CONFIG objects (identity), and the
        runtime source contains no hardcoded gate-context literals."""
        cfg = _op_config(_session_config("f14", **{
            # custom ceilings prove injection end-to-end
        }))
        from data_engine.runtime.composition import OperationalSessionConfig
        cfg = OperationalSessionConfig(
            session=cfg.session,
            gate_ceilings=GateCeilings(
                max_volatility=0.05, max_spread_fraction=Decimal("0.02"),
            ),
        )
        composed = _compose(tmp_path, monkeypatch, config=cfg)
        assert composed.runtime.gate_ceilings is cfg.gate_ceilings
        assert composed.runtime.gate_context is cfg.gate_context
        assert composed.runtime.portfolio_limits is cfg.portfolio_limits
        assert float(cfg.gate_ceilings.max_volatility) == 0.05
        assert cfg.gate_ceilings.max_spread_fraction == Decimal("0.02")
        # structural: the runtime wiring no longer hardcodes the
        # audited literals (they live in GateCeilings defaults now).
        src = Path(
            TradingRuntime.__module__.replace(".", "/") + ".py",
        )
        # src package dir: src/data_engine/runtime/runtime.py
        root = Path(__file__).resolve().parent.parent / "src" / \
            "data_engine" / "runtime" / "runtime.py"
        text = (src if src.exists() else root).read_text(encoding="utf-8")
        assert "max_volatility=0.10" not in text
        assert 'max_spread_fraction=Decimal("0.01")' not in text
        assert "market_open=True" not in text
        assert "model_valid=True" not in text

    def test_f25_mac_custody_required_refuses_without_key(
        self, tmp_path, monkeypatch,
    ):
        """F-25: operational composition REQUIRES a provisioned MAC
        key — absent key fails closed with the operator runbook
        pointer (never silently unkeyed)."""
        monkeypatch.delenv("RUNTIME_LEDGER_MAC_KEY", raising=False)
        monkeypatch.delenv("RUNTIME_LEDGER_MAC_KEY_FILE", raising=False)
        with pytest.raises(CompositionError, match="RUNTIME_LEDGER_MAC_KEY"):
            _compose(tmp_path, monkeypatch, set_mac_env=False)

    def test_f25_mac_custody_provisioned_from_environment(
        self, tmp_path, monkeypatch,
    ):
        """F-25: the documented env channel provisions keyed custody;
        the key_id reaches the LEDGER_READY evidence."""
        _mac_env(monkeypatch)
        composed = _compose(tmp_path, monkeypatch)
        assert composed.mac_custody is not None
        assert composed.mac_custody.status == "OPERATIONAL"
        ledger_ev = [
            e for e in composed.evidence if e.gate == "LEDGER_READY"
        ]
        # last-wins: the composition root's FIRST-HAND component
        # evidence supersedes any operator-recorded duplicate
        assert ledger_ev and ledger_ev[-1].passed
        assert "operator-recorded" not in ledger_ev[-1].component
        assert composed.mac_custody.current_key_id \
            in ledger_ev[-1].evidence

    def test_start_refused_lists_human_gates(self, tmp_path, monkeypatch):
        """Honest fail-closed posture: without the human evidence the
        start refusal lists EXACTLY the human-dependent gates."""
        composed = _compose(
            tmp_path, monkeypatch, operator_evidence="no-human",
        )
        with pytest.raises(CompositionStartRefused) as exc:
            composed.start()
        assert set(exc.value.failed_gates) == set(HUMAN_EVIDENCE_GATES)

    def test_start_succeeds_and_verifies_with_complete_evidence(
        self, tmp_path, monkeypatch,
    ):
        """End-to-end wiring: complete operator bundle (the test
        acts as the operator) → start() runs recovery, attaches the
        paper venue, runs the reconciliation driver and verifies the
        post-start facts."""
        composed = _compose(tmp_path, monkeypatch, started=False)
        report = composed.start()
        assert composed.runtime.state is RuntimeState.RUNNING
        assert report.venue is not None
        assert report.venue.session.broker_id  # real guarded session
        assert report.reconciliation is not None
        assert report.post_start_verified


# ---------------------------------------------------------------------------
# C2: readiness evidence suppliers + flip matrix
# ---------------------------------------------------------------------------

class TestReadinessEvidenceSuppliers:

    def test_component_gates_supplied_first_hand(
        self, tmp_path, monkeypatch,
    ):
        composed = _compose(tmp_path, monkeypatch, operator_evidence=())
        supplied = {e.gate for e in composed.evidence}
        assert COMPONENT_EVIDENCE_GATES <= supplied
        for e in composed.evidence:
            if e.gate in COMPONENT_EVIDENCE_GATES:
                assert e.passed
                assert e.component != "missing"
                assert "operator-recorded" not in e.component

    def test_human_gates_blocked_honestly_when_operator_silent(
        self, tmp_path, monkeypatch,
    ):
        composed = _compose(tmp_path, monkeypatch, operator_evidence=())
        ev = {e.gate: e for e in composed.evidence}
        for gate in HUMAN_EVIDENCE_GATES:
            assert gate in ev and not ev[gate].passed
            assert ev[gate].component == "human-dependency"
            assert ev[gate].check == "operator_action_required"

    def test_operator_human_evidence_never_stomped(
        self, tmp_path, monkeypatch,
    ):
        """The composition root NEVER overrides operator-supplied
        human-gate evidence — code cannot fabricate or veto recorded
        human decisions. FIX-9: the operator's human-gate evidence is
        the SIGNED, re-verified approval bundle (component
        ``operator-approval``), and it survives composition untouched."""
        composed = _compose(tmp_path, monkeypatch,
                            operator_evidence="full")
        ev = {e.gate: e for e in composed.evidence}
        for gate in HUMAN_EVIDENCE_GATES:
            assert ev[gate].passed
            # FIX-9: human-gate evidence is the trusted approval
            # bundle (never plain recorded text, never stomped).
            assert isinstance(ev[gate], TrustedGateEvidence)
            assert ev[gate].component == "operator-approval"
            assert ev[gate].approval_record.decision == "APPROVE"

    def test_flip_matrix_every_gate_decides_the_verdict(self):
        """Over ALL 32 gates: one FALSE gate ⇒ PAPER_READY = FALSE
        naming exactly that gate (fail-closed conjunction §53/§66)."""
        for failing in GATE_NAMES:
            gate = PaperReadinessGate()
            for name in GATE_NAMES:
                gate.submit(GateEvidence(
                    gate=name, component="flip-matrix",
                    check="evidence_submitted",
                    evidence=f"matrix evidence for {name}",
                    passed=(name != failing),
                ))
            report = gate.evaluate()
            assert not report.paper_ready
            assert report.failed_gates == (failing,)

    def test_operator_bundle_gap_refuses_start(
        self, tmp_path, monkeypatch,
    ):
        """A missing piece of recorded evidence (DATA_READY) reaches
        the start refusal — the operator bundle is genuinely wired
        into the readiness decision."""
        composed = _compose(
            tmp_path, monkeypatch, operator_evidence="drop-data-ready",
        )
        with pytest.raises(CompositionStartRefused) as exc:
            composed.start()
        assert "DATA_READY" in exc.value.failed_gates

    def test_gate_disposition_catalog_covers_all_32(self):
        from data_engine.runtime.composition import (
            GATE_SUPPLIER_DISPOSITION,
        )
        assert set(GATE_SUPPLIER_DISPOSITION) == set(GATE_NAMES)
        allowed = {OPERATOR_RECORDED_EVIDENCE,
                   "SUPPLIED_BY_COMPOSITION_ROOT",
                   "HUMAN_ACTION_REQUIRED"}
        assert set(GATE_SUPPLIER_DISPOSITION.values()) <= allowed


# ---------------------------------------------------------------------------
# F-05: supervisor exits 2 until the readiness chain is complete
# ---------------------------------------------------------------------------

class TestSupervisorWiring:

    def _service(self, readiness_fn, max_seconds=0.05):
        return PaperRuntimeService(
            readiness_fn=readiness_fn,
            enable_dashboard=False,
            heartbeat_seconds=60.0,
            tick_seconds=0.01,
            max_seconds=max_seconds,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

    def test_exit_2_until_evidence_complete(self, tmp_path, monkeypatch):
        """F-05 acceptance: the supervisor NEVER reports active unless
        constructed+validated+operating. With the human gates open
        (today's honest state) it exits 2 — and with a complete
        evidence chain it runs to completion."""
        composed = _compose(tmp_path, monkeypatch,
                            operator_evidence="no-human")
        svc = self._service(
            lambda: composed.readiness_gate.evaluate().paper_ready,
        )
        assert svc.run() == 2  # EXIT_NOT_READY — evidence incomplete

        complete = _compose(tmp_path / "x2", monkeypatch,
                            operator_evidence="full", session="svc2")
        svc2 = self._service(
            lambda: complete.readiness_gate.evaluate().paper_ready,
        )
        assert svc2.run() == 0  # evidence chain complete → runs


# ---------------------------------------------------------------------------
# C3: conservative reservation-reconciliation driver
# ---------------------------------------------------------------------------

class _IncidentSink:
    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)


class _SpyLedger:
    """Wraps a real ledger; FAILS the test if the driver ever tries
    to reserve or submit (the driver is reconciliation-only)."""

    def __init__(self, ledger):
        self._ledger = ledger
        self.reserve_calls = 0

    def __getattr__(self, name):
        return getattr(self._ledger, name)

    def reserve(self, *a, **k):  # pragma: no cover - must never run
        self.reserve_calls += 1
        raise AssertionError(
            "the reconciliation driver must NEVER reserve (no "
            "submission capability — C3 mandate)"
        )


class TestReservationReconciler:

    def _ledger(self, tmp_path, n=1):
        return SubmissionLedger(
            Path(tmp_path) / f"led-{n}.json",
            policy=_policy(), wall_clock=_clock(),
        )

    def _reserve(self, ledger, cid, at_seconds):
        return ledger.reserve(
            cid, governed_ts=T0 + timedelta(seconds=at_seconds),
            now=T0 + timedelta(seconds=at_seconds),
        )

    def _oms(self, cid, status):
        return SimpleNamespace(order_id=cid, status=status)

    def _journal(self, cid, entry_type):
        return SimpleNamespace(
            client_order_id=cid, entry_type=entry_type,
        )

    def test_venue_acked_reserved_becomes_submitted(self, tmp_path):
        led = self._ledger(tmp_path, 1)
        self._reserve(led, "o-1", 10)
        sink = _IncidentSink()
        driver = ReservationReconciler(led, incident_sink=sink)
        report = driver.reconcile(
            oms_orders=[self._oms("o-1", OrderLifecycle.ACKNOWLEDGED)],
            venue_records=[self._journal("o-1", "ORDER_ACK")],
        )
        rec = {r.client_order_id: r for r in led.records()}["o-1"]
        assert rec.state is ReservationState.SUBMITTED
        assert report.decision_for("o-1") == "RECONCILED_SUBMITTED"
        # venue truth ⇒ the slot stays consumed
        assert led.count_in_window(
            now=T0 + timedelta(seconds=30),
        ) == 1
        assert any(
            r["event_type"] == "SUBMISSION_RESERVATION_RECONCILED"
            for r in sink.records
        )

    def test_venue_refused_finalized_consumed(self, tmp_path):
        led = self._ledger(tmp_path, 2)
        self._reserve(led, "o-2", 10)
        driver = ReservationReconciler(led, incident_sink=_IncidentSink())
        report = driver.reconcile(
            oms_orders=[self._oms("o-2", OrderLifecycle.REJECTED)],
            venue_records=[self._journal("o-2", "ORDER_REFUSED")],
        )
        rec = {r.client_order_id: r for r in led.records()}["o-2"]
        assert rec.state is ReservationState.FINALIZED
        assert rec.outcome == "VENUE_REFUSED"
        assert report.decision_for("o-2") == "RECONCILED_FINALIZED"
        # consumed: the venue SAW and refused the request
        assert led.count_in_window(
            now=T0 + timedelta(seconds=30),
        ) == 1

    def test_confirmed_absence_released(self, tmp_path):
        """The ONLY release path: venue journal authoritative-ABSENT
        (the venue pipeline never saw the order) AND the OMS holds
        the authoritative pre-venue terminal state REJECTED."""
        led = self._ledger(tmp_path, 3)
        self._reserve(led, "o-3", 10)
        driver = ReservationReconciler(led, incident_sink=_IncidentSink())
        report = driver.reconcile(
            oms_orders=[self._oms("o-3", OrderLifecycle.REJECTED)],
            venue_records=[],
        )
        rec = {r.client_order_id: r for r in led.records()}["o-3"]
        assert rec.state is ReservationState.ABANDONED
        assert rec.outcome == PRE_VENUE_OUTCOME
        assert report.decision_for("o-3") == "RELEASED_CONFIRMED_PRE_VENUE"
        assert led.count_in_window(
            now=T0 + timedelta(seconds=30),
        ) == 0

    def test_ambiguous_preserved_never_released(self, tmp_path):
        """Timeout/unknown ≠ release: no venue truth + OMS pre-submit
        or no OMS record at all ⇒ capacity stays consumed."""
        led = self._ledger(tmp_path, 4)
        self._reserve(led, "o-4a", 10)
        self._reserve(led, "o-4b", 12)
        driver = ReservationReconciler(led, incident_sink=_IncidentSink())
        report = driver.reconcile(
            oms_orders=[
                self._oms("o-4a", OrderLifecycle.RISK_APPROVED),
            ],
            venue_records=[],
        )
        assert report.decision_for("o-4a") == "PRESERVED_AMBIGUOUS"
        assert report.decision_for("o-4b") == "PRESERVED_AMBIGUOUS"
        assert led.count_in_window(
            now=T0 + timedelta(seconds=30),
        ) == 2

    def test_post_venue_terminal_without_journal_flags_divergence(
        self, tmp_path,
    ):
        """OMS says FILLED but the venue journal never saw the order:
        truth divergence — PRESERVED + divergence flag + incident
        (never optimism, never release)."""
        led = self._ledger(tmp_path, 5)
        self._reserve(led, "o-5", 10)
        sink = _IncidentSink()
        driver = ReservationReconciler(led, incident_sink=sink)
        report = driver.reconcile(
            oms_orders=[self._oms("o-5", OrderLifecycle.FILLED)],
            venue_records=[],
        )
        assert report.decision_for("o-5") == "PRESERVED_AMBIGUOUS"
        assert "o-5" in report.divergence_flags
        assert led.count_in_window(
            now=T0 + timedelta(seconds=30),
        ) == 1
        assert any(
            r.get("payload", {}).get("divergence")
            for r in sink.records
        )

    def test_duplicate_signal_idempotent(self, tmp_path):
        """C3: re-running the driver (duplicate signal) performs NO
        additional durable writes — the second pass is a no-op report
        over already-reconciled records."""
        led = self._ledger(tmp_path, 6)
        self._reserve(led, "o-6", 10)
        sink = _IncidentSink()
        driver = ReservationReconciler(led, incident_sink=sink)
        driver.reconcile(
            oms_orders=[self._oms("o-6", OrderLifecycle.REJECTED)],
            venue_records=[],
        )
        ledger_text_before = (Path(tmp_path) / "led-6.json").read_text()
        sink_calls_before = len(sink.records)
        report2 = driver.reconcile(
            oms_orders=[self._oms("o-6", OrderLifecycle.REJECTED)],
            venue_records=[],
        )
        assert report2.decision_for("o-6") == "ALREADY_RESOLVED"
        assert (Path(tmp_path) / "led-6.json").read_text() \
            == ledger_text_before
        assert len(sink.records) == sink_calls_before

    def test_driver_has_no_submission_capability(self, tmp_path):
        """C3: reconciliation NEVER reserves — structurally
        incapable of causing a duplicate submission."""
        led = self._ledger(tmp_path, 7)
        self._reserve(led, "o-7", 10)
        spy = _SpyLedger(led)
        driver = ReservationReconciler(spy, incident_sink=_IncidentSink())
        driver.reconcile(
            oms_orders=[self._oms("o-7", OrderLifecycle.RISK_APPROVED)],
            venue_records=[],
        )
        assert spy.reserve_calls == 0

    def test_reconcile_runtime_extracts_live_truths(self, tmp_path):
        """The driver's runtime adapter pulls OMS orders + venue
        journal records from the REAL composed objects."""
        led = self._ledger(tmp_path, 8)
        self._reserve(led, "o-8", 10)
        driver = ReservationReconciler(led, incident_sink=_IncidentSink())
        report = driver.reconcile_runtime(
            runtime=SimpleNamespace(
                oms=SimpleNamespace(orders=lambda: (
                    self._oms("o-8", OrderLifecycle.RISK_APPROVED),),
                ),
            ),
            venue=SimpleNamespace(session=SimpleNamespace(
                journal_records=lambda: (
                    self._journal("o-8", "ORDER_ACK"),),
            )),
        )
        assert report.decision_for("o-8") == "RECONCILED_SUBMITTED"
        rec = {r.client_order_id: r for r in led.records()}["o-8"]
        assert rec.state is ReservationState.SUBMITTED


# ---------------------------------------------------------------------------
# CLI: per-gate supplier disposition (F-05 acceptance)
# ---------------------------------------------------------------------------

class TestCliGateDisposition:

    def test_status_gates_lists_all_32(self, capsys):
        from data_engine.cli import main
        main(["status", "--gates"])
        out = capsys.readouterr().out
        from data_engine.runtime.composition import (
            GATE_SUPPLIER_DISPOSITION,
        )
        for gate in GATE_NAMES:
            assert gate in out
            assert GATE_SUPPLIER_DISPOSITION[gate] in out

    def test_status_dimensions_honest(self):
        from data_engine.cli import STATUS_DIMENSIONS
        assert STATUS_DIMENSIONS["COMPOSITION_ROOT"] == "AVAILABLE"
        assert STATUS_DIMENSIONS["RUNTIME_HEALTH"] == "ABSENT"
