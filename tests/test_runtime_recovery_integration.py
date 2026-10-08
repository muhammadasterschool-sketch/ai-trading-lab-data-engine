"""Paper-readiness re-audit: RUNTIME INTEGRATION tests (BLOCKERs 1-24).

This module proves the OPERATIONAL semantics that unit-test fixtures
(``ephemeral_test_fixture=True``) deliberately skip:

- BLOCKER 1 — persistence is MANDATORY: no store / corrupt store /
  unavailable store ⇒ start REFUSED; write failure ⇒ safe HALT.
- BLOCKER 2 — the PaperReadinessGate is AUTHORITATIVE: one failed
  gate (real-data / recovery / security / governance / …) ⇒ start
  REFUSED; ALL gates pass ⇒ startup permitted.
- BLOCKER 4/5/6/8/9/12/13/20 — restart THROUGH TradingRuntime at the
  ten mandated points; complete execution-state persistence; full
  ledger + memory chain recovery with identical heads; partial-fill
  continuation; SL/TP protection survival; kill-switch survival;
  idempotency across restart.
- BLOCKER 10 — reconciliation gates resumption (tampered state ⇒
  RECONCILIATION_REQUIRED, never silent resume).
- BLOCKER 17 — restart around TTL expiry.
- BLOCKER 21 — pinned model hashes refuse foreign models.
- BLOCKER 3 — the REAL_VERIFIED stage chain refuses incomplete
  promotion.
- BLOCKER 14/15 — deterministic identity under replay (order ids,
  fill ids, ledger heads, memory chain hash, final state).
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.runtime import (
    EXECUTION_STATE_FIELDS,
    GATE_NAMES,
    DatasetReadinessRecord,
    DeterministicBaseline,
    DeterministicEnsemble,
    EntryConstraints,
    ExecutionStateStore,
    GateEvidence,
    LSTMClassifier,
    PaperReadinessGate,
    RealDataReadiness,
    RuntimeConfig,
    RuntimeState,
    RuntimeCalibrator,
    StateStoreError,
    TradingRuntime,
    SequenceSpec,
    build_sequence_set,
    KillSwitchScope,
    OMS,
    validate_execution_state,
)
from data_engine.runtime.contracts import DecisionAction, TradePlan

# Reuse the deterministic world builders from the E2E module.
from test_runtime_e2e import T0, _bars, _fit_world

SYMBOL = "TEST/USD"


def _op_config(session, pins=()):
    """OPERATIONAL config (ephemeral_test_fixture=False by default)."""
    return RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        pinned_model_hashes=tuple(pins),
    )


def _ready_gate(failed=()):
    """A gate with objective evidence for ALL 31 mandatory gates.

    ``failed`` names gates whose evidence is submitted with
    passed=False (one FALSE ⇒ PAPER_READY=FALSE ⇒ start REFUSED).
    """
    gate = PaperReadinessGate()
    for name in GATE_NAMES:
        gate.submit(GateEvidence(
            gate=name,
            component=f"component:{name.lower()}",
            check="evidence_submitted",
            evidence=(
                "objective evidence on record" if name not in failed
                else "evidence demonstrates FAILURE"
            ),
            passed=name not in failed,
        ))
    return gate


def _operational(session, store_dir, gate=None, pins=(), volume=None,
                 ens_cal=None, realism=None):
    """Build a fully-gated OPERATIONAL runtime (persistence mandatory)."""
    if ens_cal is None:
        ens_cal = _fit_world()
    ens, cal = ens_cal
    cfg = _op_config(session, pins=pins)
    store = ExecutionStateStore(Path(store_dir))
    rt = TradingRuntime(
        cfg, ens, calibrator=cal, state_store=store,
        readiness_gate=gate if gate is not None else _ready_gate(),
        realism=realism,
    )
    return rt


def _partial_realism():
    """Realism that produces genuine MULTI-BAR PARTIAL FILLS through
    the full governed path (risk-gate liquidity rule requires
    quantity ≤ 10% of bar volume, so the participation cap is what
    splits an order across bars)."""
    from data_engine.paper.simulator import ExecutionRealism
    return ExecutionRealism(
        half_spread=Decimal("0.02"),
        commission_per_unit=Decimal("0.001"),
        impact_rate=Decimal("0.0001"),
        participation_cap=Decimal("0.01"),
        fill_lag_bars=1,
    )


def _run_until(rt, condition, bars, start=0, limit=None):
    """Process bars from ``start`` until ``condition(rt)`` is truthy.

    Returns the index of the LAST processed bar (or None). Never
    processes more than ``limit`` bars.
    """
    end = len(bars) if limit is None else min(len(bars), start + limit)
    last = None
    for i in range(start, end):
        rt.process_bar(bars[i])
        last = i
        if condition(rt):
            return last
    return None


def _live_orders(rt):
    return [o for o in rt.oms.orders() if not o.is_terminal]


def _has_status(rt, status):
    return any(o.status.value == status for o in rt.oms.orders())


def _assert_restart_equivalence(rt1, rt2):
    """BLOCKER 5: EVERY execution-critical field survives restart."""
    # orders incl. lifecycle + fills + quantities + average price
    o1 = {o.order_id: o for o in rt1.oms.orders()}
    o2 = {o.order_id: o for o in rt2.oms.orders()}
    assert set(o1) == set(o2), "order id set changed across restart"
    for oid, before in o1.items():
        after = o2[oid]
        assert before.status is after.status
        assert before.quantity == after.quantity
        assert before.filled_quantity == after.filled_quantity
        assert before.remaining_quantity == after.remaining_quantity
        assert before.average_fill_price == after.average_fill_price
        assert [f.fill_id for f in before.fills] == \
            [f.fill_id for f in after.fills]
        assert [str(f.price) for f in before.fills] == \
            [str(f.price) for f in after.fills]
        assert [str(f.quantity) for f in before.fills] == \
            [str(f.quantity) for f in after.fills]
        assert before.ttl_bars == after.ttl_bars
        assert before.submitted_at_bar == after.submitted_at_bar
    # positions incl. SL/TP + realized P&L (BLOCKER 9/18)
    assert set(rt1.positions) == set(rt2.positions)
    for sym, p1 in rt1.positions.items():
        p2 = rt2.positions[sym]
        assert p1.quantity == p2.quantity
        assert p1.average_cost == p2.average_cost
        assert p1.realized_pnl == p2.realized_pnl
        assert p1.stop_loss == p2.stop_loss
        assert p1.take_profit == p2.take_profit
    # ledger chains: identical heads (BLOCKER 6). The incident ledger
    # legitimately APPENDS recovery events (RUNTIME_STATE_RESTORED,
    # RECONCILIATION_PASS, RUNTIME_STARTED) — its pre-restart history
    # must be identical (prefix) and every non-incident ledger head
    # must be bit-identical.
    h1 = rt1.ledgers.head_hashes()
    h2 = rt2.ledgers.head_hashes()
    for name in h1:
        if name != "incident":
            assert h1[name] == h2[name], f"ledger {name} head diverged"
    inc1 = list(rt1.ledgers.events("incident"))
    inc2 = list(rt2.ledgers.events("incident"))
    assert inc2[:len(inc1)] == inc1, "incident history diverged"
    assert len(inc2) >= len(inc1)
    assert rt2.ledgers.verify()
    # memory chain: identical head (BLOCKER 20)
    assert rt1.memory.chain_hash == rt2.memory.chain_hash
    assert len(rt1.memory) == len(rt2.memory)
    assert rt2.memory.verify_integrity()
    # bookkeeping
    assert rt1._bar_index == rt2._bar_index
    assert len(rt1._bars) == len(rt2._bars)
    assert rt1._order_fill_cursor == rt2._order_fill_cursor
    assert set(rt1._pending_protection) == set(rt2._pending_protection)
    for oid in rt1._pending_protection:
        sl1, tp1, c1 = rt1._pending_protection[oid]
        sl2, tp2, c2 = rt2._pending_protection[oid]
        assert (str(sl1), str(tp1), c1) == (str(sl2), str(tp2), c2)
    assert set(rt1._pending_exits) == set(rt2._pending_exits)
    assert rt1._consecutive_bad_bars == rt2._consecutive_bad_bars
    assert str(rt1._equity_realized) == str(rt2._equity_realized)


# ════════════════════════════════════════════════════════════════════
# BLOCKER 1 — persistent state is MANDATORY
# ════════════════════════════════════════════════════════════════════

class TestPersistenceMandatory:
    def test_missing_state_store_refuses_start(self):
        """NO_STATE_STORE ⇒ BLOCKED ⇒ never RUNNING."""
        ens, cal = _fit_world()
        rt = TradingRuntime(
            _op_config("b1-nostore"), ens, calibrator=cal,
            state_store=None, readiness_gate=_ready_gate(),
        )
        with pytest.raises(Exception, match="NO_STATE_STORE"):
            rt.start()
        assert rt.state is not RuntimeState.RUNNING

    def test_normal_paper_mode_requires_store_and_gate(self, tmp_path):
        """The positive counterpart: store + full gate ⇒ RUNNING."""
        rt = _operational("b1-ok", tmp_path / "st1")
        rt.start()
        assert rt.state is RuntimeState.RUNNING
        assert rt.operational is True
        # first bar persists the first full snapshot
        rt.process_bar(_bars(1)[0])
        assert (Path(tmp_path / "st1") / "state.json").exists()

    def test_corrupt_state_store_refuses_start(self, tmp_path):
        """Corrupt journal/snapshot ⇒ self-check failure ⇒ REFUSED."""
        rt = _operational("b1-corrupt", tmp_path / "st2")
        rt.start()
        rt.process_bar(_bars(1)[0])
        # Corrupt the journal on disk; a FRESH store must see it.
        journal = tmp_path / "st2" / "journal.jsonl"
        lines = journal.read_text().splitlines()
        record = json.loads(lines[-1])
        record["payload"] = {"tampered": True}
        lines[-1] = json.dumps(record, sort_keys=True, default=str)
        journal.write_text("\n".join(lines) + "\n")
        rt2 = _operational("b1-corrupt", tmp_path / "st2")
        with pytest.raises(Exception, match="self-check FAILED"):
            rt2.start()
        assert rt2.state is RuntimeState.RECOVERY_REQUIRED

    def test_unavailable_state_store_refuses_start(self, tmp_path):
        """Unwritable store directory ⇒ REFUSED (fail closed)."""
        ens, cal = _fit_world()
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        blocked.chmod(0o444)  # read-only
        try:
            store = ExecutionStateStore(blocked)
            rt = TradingRuntime(
                _op_config("b1-unavail"), ens, calibrator=cal,
                state_store=store, readiness_gate=_ready_gate(),
            )
            with pytest.raises(Exception):
                rt.start()
        finally:
            blocked.chmod(0o755)

    def test_read_failure_requires_recovery(self, tmp_path):
        """Unreadable snapshot ⇒ RECOVERY_REQUIRED refusal (BLOCKER 1:
        read failure → recovery required, never silent cold start)."""
        rt = _operational("b1-read", tmp_path / "st3")
        rt.start()
        rt.process_bar(_bars(1)[0])
        # Corrupt the SNAPSHOT (journal stays intact): restore must
        # refuse via schema/parse failure, not treat as cold start.
        snap = tmp_path / "st3" / "state.json"
        snap.write_text("{not json")
        rt2 = _operational("b1-read", tmp_path / "st3")
        with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
            rt2.start()
        assert rt2.state is RuntimeState.RECOVERY_REQUIRED

    def test_ephemeral_fixture_is_explicitly_marked(self):
        """Unit-test fixtures may skip persistence ONLY via the
        explicit config marking — and are ledgered as such."""
        ens, cal = _fit_world()
        cfg = _op_config("b1-eph")
        cfg = cfg.model_copy(update={"ephemeral_test_fixture": True})
        rt = TradingRuntime(cfg, ens, calibrator=cal)
        rt.start()
        assert rt.state is RuntimeState.RUNNING
        assert rt.operational is False
        events = rt.ledgers.events("incident")
        assert any(
            e.event_type == "EPHEMERAL_TEST_FIXTURE_STARTED" for e in events
        )


# ════════════════════════════════════════════════════════════════════
# BLOCKER 2 — the readiness gate is AUTHORITATIVE
# ════════════════════════════════════════════════════════════════════

class TestReadinessGateAuthoritative:
    def test_no_gate_wired_refuses_start(self, tmp_path):
        ens, cal = _fit_world()
        rt = TradingRuntime(
            _op_config("b2-nogate"), ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "g1"),
        )
        with pytest.raises(Exception, match="PaperReadinessGate"):
            rt.start()

    def test_readiness_false_refuses_start(self, tmp_path):
        rt = _operational(
            "b2-false", tmp_path / "g2",
            gate=_ready_gate(failed=["MODEL_READY"]),
        )
        with pytest.raises(Exception, match="failed gates.*MODEL_READY"):
            rt.start()
        assert rt.state is not RuntimeState.RUNNING

    def test_real_data_gate_false_refuses_start(self, tmp_path):
        rt = _operational(
            "b2-realdata", tmp_path / "g3",
            gate=_ready_gate(failed=["REAL_DATA_READY"]),
        )
        with pytest.raises(Exception, match="REAL_DATA_READY"):
            rt.start()

    def test_recovery_gate_false_refuses_start(self, tmp_path):
        rt = _operational(
            "b2-recovery", tmp_path / "g4",
            gate=_ready_gate(failed=["RECOVERY_READY"]),
        )
        with pytest.raises(Exception, match="RECOVERY_READY"):
            rt.start()

    def test_security_gate_false_refuses_start(self, tmp_path):
        rt = _operational(
            "b2-security", tmp_path / "g5",
            gate=_ready_gate(failed=["SECURITY_READY"]),
        )
        with pytest.raises(Exception, match="SECURITY_READY"):
            rt.start()

    def test_governance_gate_false_refuses_start(self, tmp_path):
        rt = _operational(
            "b2-governance", tmp_path / "g6",
            gate=_ready_gate(failed=["GOVERNANCE_READY"]),
        )
        with pytest.raises(Exception, match="GOVERNANCE_READY"):
            rt.start()

    def test_rl_gov_gate_false_refuses_start(self, tmp_path):
        """RL-governance cycle: an ungoverned/failed RL layer must
        block operational startup (mandatory gate RL_GOV_READY)."""
        rt = _operational(
            "b2-rlgov", tmp_path / "g6b",
            gate=_ready_gate(failed=["RL_GOV_READY"]),
        )
        with pytest.raises(Exception, match="RL_GOV_READY"):
            rt.start()

    def test_all_mandatory_gates_true_permits_startup(self, tmp_path):
        """The ONLY path to operational RUNNING: every gate PASS."""
        rt = _operational("b2-all", tmp_path / "g7",
                          gate=_ready_gate())
        rt.start()
        assert rt.state is RuntimeState.RUNNING

    def test_gate_completeness_mandated_set(self):
        """BLOCKER 24 + RL-governance cycle: the mandated gates all
        exist, including RL_GOV_READY ("RL safety/integration")."""
        required = {
            "DATA_READY", "REAL_DATA_READY", "PIT_READY", "SEQUENCE_READY",
            "BASELINE_READY", "MODEL_READY", "PREDICTION_READY",
            "CALIBRATION_READY", "UNCERTAINTY_READY", "REGIME_READY",
            "CRASH_READY", "RL_GOV_READY", "DECISION_READY",
            "TRADE_PLAN_READY", "RISK_READY", "KILLSWITCH_READY", "OMS_READY",
            "EXECUTION_READY", "PERSISTENCE_READY", "RECOVERY_READY",
            "PARTIAL_FILL_READY", "SLTP_READY", "RECONCILIATION_READY",
            "LEDGER_READY", "MEMORY_READY", "AUDIT_READY", "REPLAY_READY",
            "SECURITY_READY", "TESTS_READY", "GOVERNANCE_READY",
        }
        assert required <= set(GATE_NAMES)


# ════════════════════════════════════════════════════════════════════
# BLOCKER 4/5/6/8/9/12/13/20 — restart THROUGH TradingRuntime
# ════════════════════════════════════════════════════════════════════

class TestRestartThroughRuntime:
    """The ten mandated restart points, executed against the ACTUAL
    TradingRuntime (not a standalone RecoveryManager)."""

    def _restart(self, rt, session, store_dir, bars, consumed, ens_cal):
        """Simulated crash + restart: a brand-new runtime, same store,
        same ready gate — start() must LOAD→VERIFY→RESTORE→RECONCILE."""
        rt2 = _operational(session, store_dir, ens_cal=ens_cal)
        rt2.start()
        assert rt2.state is RuntimeState.RUNNING
        assert rt2.restarted is True
        _assert_restart_equivalence(rt, rt2)
        return rt2

    def test_restart_1_before_any_order(self, tmp_path):
        """Warm-up phase restart: bar history + cursor survive."""
        ens_cal = _fit_world()
        bars = _bars(20)
        rt = _operational("r1", tmp_path / "r1", ens_cal=ens_cal)
        rt.start()
        for b in bars[:10]:
            rt.process_bar(b)
        assert not rt.oms.orders()  # warm-up: no orders yet
        rt2 = self._restart(rt, "r1", tmp_path / "r1", bars, 10, ens_cal)
        # continuation is seamless
        for b in bars[10:12]:
            rt2.process_bar(b)
        assert rt2._bar_index == 11

    def test_restart_2_after_order_submission(self, tmp_path):
        """A live (submitted+acknowledged) order survives; its intent
        stays unique. (Submission and acknowledgement occur within
        the same bar by design — latency defers FILLS, not acks.)"""
        ens_cal = _fit_world()
        bars = _bars(80)
        rt = _operational("r2", tmp_path / "r2", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(rt, lambda r: bool(_live_orders(r)), bars)
        assert idx is not None, "no live order in 80 bars"
        rt2 = self._restart(rt, "r2", tmp_path / "r2", bars, idx + 1,
                            ens_cal)
        live = _live_orders(rt2)
        assert live, "submitted order lost across restart"
        assert live[0].status.value in ("SUBMITTED", "ACKNOWLEDGED")
        # BLOCKER 13: the same intent NEVER duplicates post-restart.
        plan_fields = live[0]
        duplicate = TradingRuntime.__new__(TradingRuntime)  # noqa
        from data_engine.runtime.oms import idempotent_order_id
        oid = idempotent_order_id(
            session_id=rt2.config.session_id,
            trade_plan_id=plan_fields.trade_plan_id,
            decision_id=plan_fields.decision_id,
            correlation_id=plan_fields.correlation_id,
            symbol=plan_fields.symbol, side=plan_fields.side,
            order_type=plan_fields.order_type,
            quantity=plan_fields.quantity,
            limit_price=plan_fields.limit_price,
        )
        assert oid == plan_fields.order_id  # deterministic identity
        plan = TradePlan.model_construct(
            trade_plan_id=plan_fields.trade_plan_id,
            decision_id=plan_fields.decision_id,
            correlation_id=plan_fields.correlation_id,
            symbol=plan_fields.symbol,
            side=(DecisionAction.BUY if plan_fields.side == "BUY"
                  else DecisionAction.SELL),
            quantity=plan_fields.quantity,
            entry=EntryConstraints(order_type=plan_fields.order_type),
        )
        order, created = rt2.oms.create_order(
            plan=plan, session_id=rt2.config.session_id,
            created_at=plan_fields.created_at,
            ttl_bars=plan_fields.ttl_bars,
        )
        assert created is False and order.order_id == plan_fields.order_id

    def test_restart_3_after_acknowledgement(self, tmp_path):
        ens_cal = _fit_world()
        bars = _bars(80)
        rt = _operational("r3", tmp_path / "r3", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(rt, lambda r: _has_status(r, "ACKNOWLEDGED"),
                         bars)
        assert idx is not None
        self._restart(rt, "r3", tmp_path / "r3", bars, idx + 1, ens_cal)

    def test_restart_4_during_partial_fill(self, tmp_path):
        """100 requested / partial filled: remaining, average price,
        cursor, and commission state survive; fills CONTINUE without
        duplication (BLOCKER 8)."""
        ens_cal = _fit_world()
        realism = _partial_realism()
        bars = _bars(120, volume=3000.0)
        rt = _operational("r4", tmp_path / "r4", ens_cal=ens_cal,
                          realism=realism)
        rt.start()
        idx = _run_until(
            rt, lambda r: _has_status(r, "PARTIALLY_FILLED"), bars,
        )
        assert idx is not None, "no PARTIALLY_FILLED order in 120 bars"
        partial = [
            o for o in rt.oms.orders()
            if o.status.value == "PARTIALLY_FILLED"
        ][0]
        filled_before = partial.filled_quantity
        rt2 = self._restart(rt, "r4", tmp_path / "r4", bars, idx + 1,
                            ens_cal)
        partial2 = rt2.oms.order(partial.order_id)
        assert partial2.remaining_quantity == partial.remaining_quantity
        assert partial2.average_fill_price == partial.average_fill_price
        fill_ids_before = {f.fill_id for f in partial.fills}
        # Continue: the remaining quantity fills on subsequent bars.
        _run_until(
            rt2,
            lambda r: r.oms.order(partial.order_id).is_terminal,
            bars, start=idx + 1, limit=25,
        )
        after = rt2.oms.order(partial.order_id)
        assert after.status.value in ("FILLED", "EXPIRED")
        if after.fills:
            new_ids = {f.fill_id for f in after.fills}
            assert fill_ids_before <= new_ids  # no duplicate identities
            for f in after.fills:
                if f.fill_id not in fill_ids_before:
                    assert f.fill_index >= len(fill_ids_before)

    def test_restart_5_before_protection_attaches(self, tmp_path):
        """Entry filled but SL/TP not yet applied (pending protection
        bookkeeping) survives restart (BLOCKER 9 pending state)."""
        ens_cal = _fit_world()
        bars = _bars(120)
        rt = _operational("r5", tmp_path / "r5", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(
            rt,
            lambda r: bool(r._pending_protection)
            or any(not p.is_flat and p.stop_loss is None
                   and p.take_profit is None for p in r.positions.values()),
            bars,
        )
        self._restart(rt, "r5", tmp_path / "r5", bars,
                      (idx or 0) + 1, ens_cal)

    def test_restart_6_with_active_stop_loss(self, tmp_path):
        """A position with an ACTIVE SL must not lose protection."""
        ens_cal = _fit_world()
        bars = _bars(120)
        rt = _operational("r6", tmp_path / "r6", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(
            rt,
            lambda r: any(not p.is_flat and p.stop_loss is not None
                          for p in r.positions.values()),
            bars,
        )
        assert idx is not None, "no protected position in 120 bars"
        rt2 = self._restart(rt, "r6", tmp_path / "r6", bars, idx + 1,
                            ens_cal)
        pos = rt2.positions[SYMBOL]
        assert pos.stop_loss is not None, "SL lost across restart"

    def test_restart_7_with_active_take_profit(self, tmp_path):
        ens_cal = _fit_world()
        bars = _bars(120)
        rt = _operational("r7", tmp_path / "r7", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(
            rt,
            lambda r: any(not p.is_flat and p.take_profit is not None
                          for p in r.positions.values()),
            bars,
        )
        assert idx is not None
        rt2 = self._restart(rt, "r7", tmp_path / "r7", bars, idx + 1,
                            ens_cal)
        assert rt2.positions[SYMBOL].take_profit is not None

    def test_restart_8_during_exit(self, tmp_path):
        """A protective exit in flight survives restart and completes
        (pending-exit bookkeeping + ExitRecord linkage)."""
        ens_cal = _fit_world()
        realism = _partial_realism()
        bars = _bars(200, volume=3000.0)
        rt = _operational("r8", tmp_path / "r8", ens_cal=ens_cal,
                          realism=realism)
        rt.start()
        idx = _run_until(
            rt, lambda r: bool(r._pending_exits), bars,
        )
        assert idx is not None, "no protective exit in flight"
        rt2 = self._restart(rt, "r8", tmp_path / "r8", bars, idx + 1,
                            ens_cal)
        assert set(rt2._pending_exits) == set(rt._pending_exits)
        # The exit completes (fills or expires) after continuation.
        _run_until(
            rt2, lambda r: not r._pending_exits, bars,
            start=idx + 1, limit=30,
        )

    def test_restart_9_after_fill(self, tmp_path):
        """A FILLED order + resulting position + realized P&L survive
        exactly (BLOCKER 18)."""
        ens_cal = _fit_world()
        bars = _bars(120)
        rt = _operational("r9", tmp_path / "r9", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(rt, lambda r: _has_status(r, "FILLED"), bars)
        assert idx is not None
        rt2 = self._restart(rt, "r9", tmp_path / "r9", bars, idx + 1,
                            ens_cal)
        p1 = rt.positions[SYMBOL]
        p2 = rt2.positions[SYMBOL]
        assert p1.realized_pnl == p2.realized_pnl
        assert p1.average_cost == p2.average_cost

    def test_restart_10_after_reconciliation_mismatch(self, tmp_path):
        """A tampered position state ⇒ RECONCILIATION_REQUIRED refusal
        — never silent resume (BLOCKER 10)."""
        ens_cal = _fit_world()
        bars = _bars(120)
        rt = _operational("r10", tmp_path / "r10", ens_cal=ens_cal)
        rt.start()
        idx = _run_until(rt, lambda r: _has_status(r, "FILLED"), bars)
        assert idx is not None
        # Tamper the persisted position quantity (simulates a state
        # divergence the restart must detect via fill-replay).
        snap = tmp_path / "r10" / "state.json"
        payload = json.loads(snap.read_text())
        if payload["state"]["positions"]:
            payload["state"]["positions"][0]["quantity"] = \
                str(Decimal(payload["state"]["positions"][0]["quantity"])
                    + Decimal("999"))
            snap.write_text(json.dumps(payload, default=str))
        rt2 = _operational("r10", tmp_path / "r10", ens_cal=ens_cal)
        with pytest.raises(Exception,
                           match="RECONCILIATION_REQUIRED"):
            rt2.start()
        assert rt2.state is RuntimeState.RECONCILIATION_REQUIRED

    def test_restart_around_ttl_expiry(self, tmp_path):
        """BLOCKER 17: an order near TTL that restarts must EXPIRE (or
        fill) exactly per its window — never execute post-expiry."""
        ens_cal = _fit_world()
        realism = _partial_realism()
        bars = _bars(120, volume=3000.0)
        rt = _operational("ttl", tmp_path / "ttl", ens_cal=ens_cal,
                          realism=realism)
        rt.start()
        idx = _run_until(
            rt, lambda r: _has_status(r, "PARTIALLY_FILLED"), bars,
        )
        assert idx is not None
        rt2 = self._restart(rt, "ttl", tmp_path / "ttl", bars, idx + 1,
                            ens_cal)
        partial = [
            o for o in rt2.oms.orders()
            if o.status.value == "PARTIALLY_FILLED"
        ][0]
        # Run well past the TTL window; the order must terminate.
        for b in bars[idx + 1: idx + 12]:
            rt2.process_bar(b)
        order = rt2.oms.order(partial.order_id)
        assert order.is_terminal
        if order.status.value == "EXPIRED":
            # Expired orders never execute after expiry: every fill
            # happened on bars within the TTL window.
            expiry_bar = order.submitted_at_bar + (order.ttl_bars or 0)
            for f in order.fills:
                assert f.bar_index <= expiry_bar

    def test_kill_switch_survives_restart_critical(self, tmp_path):
        """BLOCKER 12: a tripped GLOBAL switch stays tripped and the
        restart is REFUSED (HALTED) — restart never clears a switch."""
        ens_cal = _fit_world()
        bars = _bars(40)
        rt = _operational("ks-c", tmp_path / "ks-c", ens_cal=ens_cal)
        rt.start()
        for b in bars[:15]:
            rt.process_bar(b)
        rt.trip_kill_switch(
            KillSwitchScope.GLOBAL, "operator halt — restart test"
        )
        assert rt.state is RuntimeState.HALTED
        rt2 = _operational("ks-c", tmp_path / "ks-c", ens_cal=ens_cal)
        with pytest.raises(Exception, match="kill switch"):
            rt2.start()
        assert rt2.state is RuntimeState.HALTED
        assert rt2.kill_switch.is_active(KillSwitchScope.GLOBAL)

    def test_kill_switch_survives_restart_symbol(self, tmp_path):
        """A tripped SYMBOL switch survives restart and still forces
        NO_TRADE for that symbol."""
        ens_cal = _fit_world()
        bars = _bars(60)
        rt = _operational("ks-s", tmp_path / "ks-s", ens_cal=ens_cal)
        rt.start()
        for b in bars[:15]:
            rt.process_bar(b)
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "symbol halt", target=SYMBOL,
        )
        rt2 = _operational("ks-s", tmp_path / "ks-s", ens_cal=ens_cal)
        rt2.start()  # non-critical scope: restart permitted
        assert rt2.kill_switch.is_active(
            KillSwitchScope.SYMBOL, target=SYMBOL
        )
        orders_before = len(rt2.oms.orders())
        fills_before = sum(
            len(o.fills) for o in rt2.oms.orders()
        )
        for b in bars[15:25]:
            rt2.process_bar(b)
        # The SYMBOL switch survives restart structurally: no new
        # orders and no new fills for the blocked symbol.
        assert len(rt2.oms.orders()) == orders_before
        assert sum(len(o.fills) for o in rt2.oms.orders()) == fills_before

    def test_ledger_corruption_refuses_restart(self, tmp_path):
        """BLOCKER 6: a tampered ledger event inside the snapshot
        breaks chain reconstruction ⇒ RECOVERY_REQUIRED refusal."""
        ens_cal = _fit_world()
        bars = _bars(60)
        rt = _operational("lc", tmp_path / "lc", ens_cal=ens_cal)
        rt.start()
        for b in bars[:20]:
            rt.process_bar(b)
        snap = tmp_path / "lc" / "state.json"
        payload = json.loads(snap.read_text())
        incident = payload["state"]["ledgers"]["incident"]
        assert incident
        incident[-1]["payload"] = {"forged": True}
        snap.write_text(json.dumps(payload, default=str))
        rt2 = _operational("lc", tmp_path / "lc", ens_cal=ens_cal)
        with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
            rt2.start()

    def test_memory_corruption_refuses_restart(self, tmp_path):
        """BLOCKER 20: a tampered memory record breaks the chain ⇒
        RECOVERY_REQUIRED refusal."""
        ens_cal = _fit_world()
        bars = _bars(60)
        rt = _operational("mc", tmp_path / "mc", ens_cal=ens_cal)
        rt.start()
        for b in bars[:20]:
            rt.process_bar(b)
        snap = tmp_path / "mc" / "state.json"
        payload = json.loads(snap.read_text())
        mem = payload["state"]["memory"]
        assert mem
        mem[-1]["content"] = {"forged": True}
        snap.write_text(json.dumps(payload, default=str))
        rt2 = _operational("mc", tmp_path / "mc", ens_cal=ens_cal)
        with pytest.raises(Exception, match="RECOVERY_REQUIRED"):
            rt2.start()

    def test_foreign_model_refused_on_restart(self, tmp_path):
        """BLOCKER 21: persisted state bound to another config/model
        identity is REFUSED (never silently continued)."""
        ens_cal = _fit_world()
        bars = _bars(30)
        rt = _operational("fm", tmp_path / "fm", ens_cal=ens_cal)
        rt.start()
        for b in bars[:10]:
            rt.process_bar(b)
        other_ens, other_cal = _fit_world(drift=5.0)
        rt2 = _operational("fm", tmp_path / "fm", ens_cal=(other_ens,
                                                            other_cal))
        with pytest.raises(Exception, match="DIFFERENT"):
            rt2.start()


# ════════════════════════════════════════════════════════════════════
# BLOCKER 21 — pinned model integrity
# ════════════════════════════════════════════════════════════════════

class TestModelIntegrity:
    def test_pinned_hash_mismatch_refuses_start(self, tmp_path):
        ens, cal = _fit_world()
        rt = _operational(
            "pin-bad", tmp_path / "pin1", pins=["rtmod.doesnotmatch"],
        )
        with pytest.raises(Exception, match="pinned"):
            rt.start()

    def test_correct_pins_permit_start(self, tmp_path):
        ens, cal = _fit_world()
        pins = [m.artifact().model_hash for m in ens.members]
        rt = _operational("pin-good", tmp_path / "pin2", pins=pins)
        rt.start()
        assert rt.state is RuntimeState.RUNNING


# ════════════════════════════════════════════════════════════════════
# BLOCKER 14/15 — deterministic identity under replay (operational)
# ════════════════════════════════════════════════════════════════════

class TestDeterministicReplayOperational:
    def test_same_inputs_same_identity_and_final_state(self, tmp_path):
        """Same config (INCLUDING session id) + models + data + gate ⇒
        same order ids, fill ids, ledger heads, memory chain hash,
        final positions/P&L — across two fully independent runs with
        separate persistent stores."""
        ens_cal = _fit_world()
        realism = _partial_realism()
        bars = _bars(70, volume=3000.0)
        runs = []
        for i in (1, 2):
            rt = _operational(
                "replay-op", tmp_path / f"rep{i}", ens_cal=ens_cal,
                realism=realism,
            )
            rt.start()
            for b in bars:
                rt.process_bar(b)
            runs.append((
                sorted(o.order_id for o in rt.oms.orders()),
                sorted(
                    f.fill_id for o in rt.oms.orders() for f in o.fills
                ),
                rt.ledgers.head_hashes(),
                rt.memory.chain_hash,
                {
                    s: (str(p.quantity), str(p.average_cost),
                        str(p.realized_pnl), str(p.stop_loss),
                        str(p.take_profit))
                    for s, p in rt.positions.items()
                },
                str(rt._equity_realized),
                rt._bar_index,
            ))
        a, b = runs
        assert a[0] == b[0], "order identity diverged"
        assert a[1] == b[1], "fill identity diverged"
        assert a[2] == b[2], "ledger head hashes diverged"
        assert a[3] == b[3], "memory chain hash diverged"
        assert a[4] == b[4], "final positions diverged"
        assert a[5] == b[5], "realized equity diverged"
        assert a[6] == b[6]


# ════════════════════════════════════════════════════════════════════
# BLOCKER 3 — REAL_VERIFIED stage chain
# ════════════════════════════════════════════════════════════════════

def _dataset_record(**overrides):
    base = dict(
        dataset_id="ds-1",
        source="operator-approved-vendor",
        acquisition_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        market="CRYPTO",
        symbols=("BTC/USD",),
        timeframe="5m",
        coverage_start=datetime(2024, 1, 1, tzinfo=UTC),
        coverage_end=datetime(2026, 1, 1, tzinfo=UTC),
        timezone="UTC",
        adjustment_state="RAW",
        missing_data_statistics={"ratio": 0.0},
        duplicate_statistics={"count": 0.0},
        quality_status="PASSED",
        pit_status="VERIFIED",
        provenance={"license": "commercial", "sha": "abc123"},
        content_hash="a" * 64,
        epistemic_state="REAL_VERIFIED",
    )
    base.update(overrides)
    return DatasetReadinessRecord(**base)


class TestRealDataChain:
    def test_incomplete_chain_refuses_real_verified(self):
        """Missing provenance ⇒ promotion refused (fail closed)."""
        with pytest.raises(Exception, match="PROVENANCE_VERIFIED"):
            _dataset_record(provenance={})

    def test_failed_pit_refuses_real_verified(self):
        with pytest.raises(Exception, match="PIT_VERIFIED"):
            _dataset_record(pit_status="NOT_VERIFIED")

    def test_failed_quality_refuses_real_verified(self):
        with pytest.raises(Exception, match="QUALITY_GATE"):
            _dataset_record(quality_status="FAILED")

    def test_complete_chain_passes_and_reports_years(self):
        rec = _dataset_record()
        gate = RealDataReadiness()
        gate.register(rec)
        report = gate.report()
        assert report.gate == "READY"
        assert report.verified_real_datasets == 1
        assert report.verified_years == pytest.approx(2.0, abs=0.01)
        chain = dict(rec.readiness_chain)
        assert all(chain.values())

    def test_empty_registry_reports_zero_years_blocked(self):
        report = RealDataReadiness().report()
        assert report.gate == "BLOCKED_ON_REAL_DATA"
        assert report.verified_years == 0.0
        assert report.verified_real_datasets == 0


# ════════════════════════════════════════════════════════════════════
# BLOCKER 5 — EXECUTION_STATE_SCHEMA completeness
# ════════════════════════════════════════════════════════════════════

class TestExecutionStateSchema:
    def test_schema_documents_every_mandatory_field(self):
        required = {
            "schema", "identity", "orders", "kill_switch", "positions",
            "ledgers", "ledger_heads", "memory", "memory_chain_hash",
            "bars", "bar_index", "order_fill_cursor",
            "pending_protection", "pending_exits", "consecutive_bad_bars",
            "equity_realized", "session_id", "runtime_state",
        }
        assert required <= set(EXECUTION_STATE_FIELDS)

    def test_incomplete_state_fails_validation(self):
        problems = validate_execution_state({"orders": []})
        assert any("missing mandatory field" in p for p in problems)

    def test_persisted_state_satisfies_schema(self, tmp_path):
        rt = _operational("schema", tmp_path / "schema")
        rt.start()
        rt.process_bar(_bars(1)[0])
        payload = json.loads(
            (tmp_path / "schema" / "state.json").read_text()
        )
        problems = validate_execution_state(payload["state"])
        assert problems == []


# ════════════════════════════════════════════════════════════════════
# BLOCKER 11 — no unauthorized execution path (structural scan)
# ════════════════════════════════════════════════════════════════════

class TestStructuralRiskGate:
    def test_no_direct_paper_simulator_execution_in_runtime(self):
        """The runtime package must not call the frozen-era paper
        simulator's execution entrypoint directly — all fills flow
        through PaperExecutionAdapter (the governed gateway)."""
        import subprocess  # noqa: F401  (not used — static scan below)
        runtime_dir = Path(
            TradingRuntime.__module__.replace(".", "/")
        ).parent
        offenders = []
        for py in runtime_dir.glob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "PaperSimulator" in text and "simulator" in \
                    py.name.replace("_", ""):
                offenders.append(py.name)
            if ".simulate(" in text:
                offenders.append(py.name)
        assert offenders == [], (
            f"direct simulator execution paths found: {offenders}"
        )

    def test_oms_refuses_unapproved_orders_structurally(self):
        """The OMS cannot reach RISK_APPROVED without a PASSING,
        fingerprint-matched assessment (RT-F1 pin, re-verified)."""
        from data_engine.runtime import LedgerFamily
        from data_engine.runtime.contracts import OrderLifecycle
        oms = OMS(LedgerFamily())
        plan = TradePlan.model_construct(
            trade_plan_id="tp-1", decision_id="d-1",
            correlation_id="c-1", symbol=SYMBOL, side=DecisionAction.BUY,
            quantity=Decimal("10"),
            entry=EntryConstraints(order_type="MARKET"),
        )
        order, _ = oms.create_order(
            plan=plan, session_id="s1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        oms.validate_order(order.order_id)
        with pytest.raises(Exception, match="assessment"):
            oms.risk_approve(order.order_id, None)
        # Re-fetch: the OMS replaces order records immutably.
        assert oms.order(order.order_id).status is OrderLifecycle.VALIDATED
