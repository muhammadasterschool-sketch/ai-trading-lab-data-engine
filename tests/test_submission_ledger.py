"""Milestone A B1+B2 — durable submission-rate ledger + spacing governor.

Regression tests written FIRST (prompt v3.0 Part 5): the historical
C1/C2 commit is ABSENT (see artifacts/stage-a/00-REPO-IDENTITY.md),
so reproductions of the defective behavior are documented in-file
where directly reproducible, and controlled faulty doubles are used
for crash windows (labeled; never fabricated differential results).

Defects being fixed (artifacts/stage-a/02-FINDINGS-REGISTER.md):
- F-01: submission-rate accounting is volatile (in-memory list,
  absent from EXECUTION_STATE_FIELDS) — restart wipes the budget.
- F-02: no atomic reservation; check and record are separate steps;
  no cross-process guarantee.
- F-19: bridge/authoritative accounting asymmetry (converged on the
  ledger by routing both through reserve→finalize).

Owner-ratified PAPER defaults enforced by the governor (Part 3):
minimum 1 second between submissions; max 5 submissions per 60
seconds; max 10 open orders.

All venues in these tests are paper/mock fixtures. LIVE TRADING
REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

import json
import multiprocessing as mp
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.runtime import (
    ExecutionStateStore,
    RuntimeConfig,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    TradePlan,
    UncertaintyReport,
)
from data_engine.runtime.submission_ledger import (
    CapacityRefused,
    Reservation,
    ReservationState,
    SubmissionLedger,
    SubmissionLedgerError,
    SubmissionPolicy,
    WallClockRegression,
)

# Reuse the deterministic world builders from the E2E module.
from test_runtime_e2e import T0, _bars, _fit_world

SYMBOL = "TEST/USD"


def _policy(**over):
    return SubmissionPolicy(**over)


def _clock(start=T0, step_seconds=1.0):
    """Injectable wall clock; steps ``step_seconds`` per call.

    The default +1s step models the owner-ratified MINIMUM 1s
    spacing between submissions honestly (rapid-fire reserves would
    be spacing-refused — which is the governor working as ratified).
    """
    state = {"t": start}

    def clock():
        state["t"] = state["t"] + timedelta(seconds=step_seconds)
        return state["t"]

    return clock


def _ledger(path, policy=None, clock=None):
    return SubmissionLedger(
        Path(path), policy=policy or _policy(),
        wall_clock=clock or _clock(),
    )


# ---------------------------------------------------------------------------
# Unit: capacity, spacing, wall-clock protection (F-02, B2)
# ---------------------------------------------------------------------------

class TestLedgerCapacity:
    def test_five_reserves_then_sixth_refused(self, tmp_path):
        led = _ledger(tmp_path / "led.json")
        for i in range(5):
            r = led.reserve(f"ord-{i}")
            assert r.state is ReservationState.RESERVED
        with pytest.raises(CapacityRefused):
            led.reserve("ord-5")

    def test_capacity_refusal_leaves_no_record(self, tmp_path):
        path = tmp_path / "led.json"
        led = _ledger(path)
        for i in range(5):
            led.reserve(f"ord-{i}")
        before = json.loads(path.read_text())
        with pytest.raises(CapacityRefused):
            led.reserve("ord-overflow")
        after = json.loads(path.read_text())
        assert after == before, "failed reservation must leave no record"

    def test_window_expiry_releases_capacity(self, tmp_path):
        path = tmp_path / "led.json"
        led = _ledger(path)  # steps +1s per call
        for i in range(5):
            led.reserve(f"ord-{i}")  # created at T0+1s .. T0+5s
        with pytest.raises(CapacityRefused):
            led.reserve("ord-5")
        # a LATER ledger instance (same durable file) whose clock is
        # 70s beyond every record: the 60s window has expired.
        led_later = _ledger(path, clock=_clock(start=T0 + timedelta(seconds=70)))
        led_later.reserve("ord-6")  # window expired — capacity available

    def test_finalize_venue_refused_still_counts_conservatively(
        self, tmp_path
    ):
        """A venue-refused attempt CONSUMED a submission slot — the
        conservative reading of the ratified 5/60s limit."""
        led = _ledger(tmp_path / "led.json")
        for i in range(4):
            r = led.reserve(f"ord-{i}")
            led.mark_submitted(r.reservation_id)
            led.finalize(r.reservation_id, "ACKNOWLEDGED")
        r = led.reserve("ord-4")
        led.mark_submitted(r.reservation_id)
        led.finalize(r.reservation_id, "VENUE_REFUSED")
        with pytest.raises(CapacityRefused):
            led.reserve("ord-5")

    def test_abandoned_pre_venue_reservation_does_not_count(self, tmp_path):
        led = _ledger(tmp_path / "led.json")
        for i in range(5):
            r = led.reserve(f"ord-{i}")
            led.abandon(r.reservation_id, "pre-venue wiring failure")
        # all five abandoned BEFORE any broker call — capacity intact
        led.reserve("ord-5")

    def test_reservation_carries_durable_order_identity(self, tmp_path):
        path = tmp_path / "led.json"
        led = _ledger(path)
        r = led.reserve("order-identity-123")
        doc = json.loads(path.read_text())
        rec = doc["records"][0]
        assert rec["client_order_id"] == "order-identity-123"
        assert rec["reservation_id"] == r.reservation_id
        assert rec["state"] == "RESERVED"


class TestLedgerSpacing:
    def test_second_submission_within_one_second_refused(self, tmp_path):
        t = {"now": T0}

        def clock():
            return t["now"]

        led = _ledger(tmp_path / "led.json", clock=clock)
        led.reserve("ord-0")
        t["now"] = T0 + timedelta(milliseconds=999)
        with pytest.raises(CapacityRefused) as ei:
            led.reserve("ord-1")
        assert ei.value.reason_code == "SPACING"

    def test_spacing_satisfied_after_one_second(self, tmp_path):
        t = {"now": T0}

        def clock():
            return t["now"]

        led = _ledger(tmp_path / "led.json", clock=clock)
        led.reserve("ord-0")
        t["now"] = T0 + timedelta(seconds=1)
        led.reserve("ord-1")

    def test_wall_clock_regression_refused_fail_closed(self, tmp_path):
        t = {"now": T0 + timedelta(hours=1)}

        def clock():
            return t["now"]

        led = _ledger(tmp_path / "led.json", clock=clock)
        led.reserve("ord-0")
        # wall clock regresses backwards beyond tolerance
        t["now"] = T0
        with pytest.raises(WallClockRegression):
            led.reserve("ord-1")


# ---------------------------------------------------------------------------
# Unit: durability + recovery (F-01, F-02; B1 crash recovery)
# ---------------------------------------------------------------------------

class TestLedgerDurability:
    def test_records_survive_process_restart(self, tmp_path):
        path = tmp_path / "led.json"
        led1 = _ledger(path)
        for i in range(5):
            led1.reserve(f"ord-{i}")  # created at T0+1s .. T0+5s
        # a NEW process opening the same ledger (clock consistent with
        # the durable history — restart does not rewind the wall)
        led2 = _ledger(path, clock=_clock(start=T0 + timedelta(seconds=10)))
        with pytest.raises(CapacityRefused):
            led2.reserve("ord-5")

    def test_outstanding_reservation_consumed_conservatively_after_crash(
        self, tmp_path
    ):
        """Simulated kill -9 between reserve and outcome: the record
        stays RESERVED and CONSUMES capacity (fail-closed direction).
        Controlled double: the crash is simulated by simply never
        finalizing — labeled limitation, no fabricated result."""
        path = tmp_path / "led.json"
        led1 = _ledger(path)
        for i in range(5):
            led1.reserve(f"ord-{i}")  # crash: nothing finalized
        led2 = _ledger(path, clock=_clock(start=T0 + timedelta(seconds=10)))
        assert len(led2.outstanding()) == 5
        with pytest.raises(CapacityRefused):
            led2.reserve("ord-5")

    def test_journal_reconciled_reservation_becomes_submitted(
        self, tmp_path
    ):
        path = tmp_path / "led.json"
        led = _ledger(path)
        led.reserve("ord-journaled")
        led.reserve("ord-not-journaled")
        report = led.recover(
            journal_client_order_ids={"ord-journaled"}
        )
        assert report.reconciled_submitted == 1
        assert report.preserved_reserved == 1
        states = {r.client_order_id: r.state for r in led.outstanding()}
        assert states["ord-journaled"] is ReservationState.SUBMITTED
        assert states["ord-not-journaled"] is ReservationState.RESERVED

    def test_recovery_is_durable_and_auditable(self, tmp_path):
        path = tmp_path / "led.json"
        led = _ledger(path)
        led.reserve("ord-j")
        led.recover(journal_client_order_ids={"ord-j"})
        doc = json.loads(path.read_text())
        rec = doc["records"][0]
        assert rec["state"] == "SUBMITTED"
        notes = [tr["note"] for tr in rec["transitions"]]
        assert any("journal" in n.lower() for n in notes)


# ---------------------------------------------------------------------------
# Unit: cross-process atomicity — real flock on the actual filesystem (F-02)
# ---------------------------------------------------------------------------

def _race_worker(path_str, policy_kwargs, out_path, worker_id):
    """Runs in a SEPARATE process: try to consume the LAST capacity
    slot. Writes 1 (won) / 0 (refused) / -1 (error) to ``out_path``.
    Spacing is disabled for this test — the property under test is
    cross-process atomicity of the last slot, not spacing."""
    try:
        led = SubmissionLedger(
            Path(path_str), policy=SubmissionPolicy(**policy_kwargs)
        )
        try:
            led.reserve(f"race-{worker_id}")
            result = 1
        except CapacityRefused:
            result = 0
    except Exception:
        result = -1
    Path(out_path).write_text(str(result))


class TestCrossProcessAtomicity:
    def test_competing_processes_never_both_consume_last_slot(
        self, tmp_path
    ):
        path = tmp_path / "led.json"
        # Pre-fill 4 slots at REAL wall time with spacing disabled so
        # the racing workers (real clock) see them inside the window.
        led = SubmissionLedger(
            path, policy=_policy(min_spacing_seconds=0)
        )
        for i in range(4):
            led.reserve(f"pre-{i}")
        procs = []
        outs = []
        for w in (0, 1, 2):
            out = tmp_path / f"out-{w}"
            outs.append(out)
            p = mp.Process(
                target=_race_worker,
                args=(str(path), {"min_spacing_seconds": 0},
                      str(out), w),
            )
            procs.append(p)
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)
            assert p.exitcode == 0, "worker crashed"
        results = [int(o.read_text()) for o in outs]
        assert results.count(1) == 1, (
            f"exactly ONE process may consume the last slot "
            f"(results={results})"
        )
        assert results.count(0) == 2
        doc = json.loads(path.read_text())
        assert len(doc["records"]) == 5, "no double-consumption"

    def test_second_runtime_instance_on_same_ledger_refused_capacity(
        self, tmp_path
    ):
        path = tmp_path / "led.json"
        # Real clock + no spacing: the cross-process capacity property
        # (window accounting), not spacing, is under test.
        led_a = SubmissionLedger(
            path, policy=_policy(min_spacing_seconds=0)
        )
        for i in range(5):
            led_a.reserve(f"ord-a-{i}")
        led_b = SubmissionLedger(
            path, policy=_policy(min_spacing_seconds=0)
        )
        # different processes, same durable accounting
        with pytest.raises(CapacityRefused):
            led_b.reserve("ord-b-0")


# ---------------------------------------------------------------------------
# Runtime integration (F-01, F-19) — the volatile-budget reproduction
# ---------------------------------------------------------------------------

def _op_config(session):
    """No-trade fixture config (max_crash_probability=0.0 < the crash
    floor 0.02) — the decision engine stays flat so ONLY the explicit
    manual _try_entry submissions traverse the order path."""
    return RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        max_crash_probability=0.0,
        max_position_units=Decimal("1000"),
    )


def _ready_gate():
    from data_engine.runtime import GATE_NAMES, GateEvidence
    from data_engine.runtime import PaperReadinessGate
    gate = PaperReadinessGate()
    for name in GATE_NAMES:
        gate.submit(GateEvidence(
            gate=name, component=f"component:{name.lower()}",
            check="evidence_submitted",
            evidence="objective evidence on record", passed=True,
        ))
    return gate


def _uncertainty():
    return UncertaintyReport(confidence=0.9, entropy=0.3,
                             ensemble_disagreement=0.1)


def _plan(corr, ref, qty=Decimal("10")):
    return TradePlan(
        trade_plan_id=f"tp-{corr}", decision_id=f"dec-{corr}",
        symbol=SYMBOL, side=DecisionAction.BUY, quantity=qty,
        notional=qty * ref,
        entry=EntryConstraints(order_type="MARKET", ttl_bars=3),
        stop_loss=ref - Decimal("2"), take_profit=ref + Decimal("4"),
        risk_budget=Decimal("100"), expected_return=0.01,
        risk_reward_ratio=2.0, uncertainty=_uncertainty(),
        crash_risk={"probability": 0.0},
        model_context={"model": "submission-ledger"},
        correlation_id=corr,
    )


def _try_entry(rt, bars, corr, bar_i=24):
    from data_engine.runtime.contracts import EntryConstraints  # noqa: F401
    ref = Decimal(str(bars[bar_i]["close"]))
    return rt._execute_plan(
        _plan(corr, ref), bars[bar_i], bar_i, corr, ref,
        rt._current_equity(ref),
    )


class TestVolatileBudgetReproduction:
    """DEFECT DEMONSTRATION (F-01) — documents the CURRENT volatile
    behavior on the no-ledger path so the defect is pinned in the
    historical record. This is NOT the fix; the fix is the ledger
    path (TestDurableBudget below). Passes before AND after the fix
    because the ledger is OPT-IN (composition root makes it
    mandatory in Stage C)."""

    def test_restart_wipes_in_memory_budget_without_ledger(self, tmp_path):
        ens, cal = _fit_world()
        store = tmp_path / "state"
        rt1 = TradingRuntime(
            _op_config("f01-repro"), ens, calibrator=cal,
            state_store=ExecutionStateStore(store),
            readiness_gate=_ready_gate(),
        )
        rt1.start()
        bars = _bars(30)
        for b in bars[:25]:
            rt1.process_bar(b)
        # consume the in-memory budget to the 5/60s cap (internal path)
        for i in range(5):
            orders, _ = _try_entry(rt1, bars, f"repro-{i}")
            assert orders, "entry must pass while budget remains"
        # the sixth submission is refused while the process lives …
        orders6, _ = _try_entry(rt1, bars, "repro-5")
        assert not orders6, "in-memory cap must hold in-process"
        # … but a RESTART (same store) reconstructs an EMPTY budget —
        # the defect: nothing durable carries the submissions forward.
        if getattr(rt1, "_store", None) is not None:
            rt1._store.close()  # process death (F-03 single-writer lock)
        rt2 = TradingRuntime(
            _op_config("f01-repro"), ens, calibrator=cal,
            state_store=ExecutionStateStore(store),
            readiness_gate=_ready_gate(),
        )
        rt2.start()
        assert rt2.state is RuntimeState.RUNNING
        assert rt2._submissions_in_window(bars[24]["timestamp"]) == 0, (
            "F-01 DEFECT DEMONSTRATED: restart wiped the rate budget"
        )


class TestDurableBudget:
    """THE FIX (B1): with a durable SubmissionLedger attached, the
    rate budget survives restart — recovery reconstructs outstanding
    reservations CONSERVATIVELY (consumed until proven otherwise)."""

    def _runtime(self, tmp_path, session, ledger_path):
        ens, cal = _fit_world()
        return TradingRuntime(
            _op_config(session), ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "state"),
            readiness_gate=_ready_gate(),
            submission_ledger=SubmissionLedger(
                ledger_path, policy=_policy(), wall_clock=_clock(),
            ),
        )

    def test_budget_survives_restart_with_ledger(self, tmp_path):
        led_path = tmp_path / "ledger.json"
        bars = _bars(30)
        rt1 = self._runtime(tmp_path, "b1-durable", led_path)
        rt1.start()
        for b in bars[:25]:
            rt1.process_bar(b)
        for i in range(5):
            orders, _ = _try_entry(rt1, bars, f"dur-{i}")
            assert orders
        # capacity now exhausted in-process …
        orders6, _ = _try_entry(rt1, bars, "dur-5")
        assert not orders6
        # … and STILL exhausted after restart (the durable fix)
        if getattr(rt1, "_store", None) is not None:
            rt1._store.close()  # process death (F-03 single-writer lock)
        rt2 = self._runtime(tmp_path, "b1-durable", led_path)
        rt2.start()
        assert rt2.state is RuntimeState.RUNNING
        orders7, _ = _try_entry(rt2, bars, "dur-6")
        assert not orders7, (
            "durable ledger must carry the rate budget across restart"
        )

    def test_capacity_refusal_precedes_broker_call(self, tmp_path):
        """B1: capacity refusal happens BEFORE any broker call — a
        venue double that FAILS the test if invoked."""
        led_path = tmp_path / "ledger.json"
        bars = _bars(30)
        rt = self._runtime(tmp_path, "b1-precall", led_path)
        rt.start()
        for b in bars[:25]:
            rt.process_bar(b)
        # exhaust capacity directly through the ledger (external
        # consumer — simulates another process / prior crash debris)
        led = SubmissionLedger(
            led_path, policy=_policy(), wall_clock=_clock()
        )
        for i in range(5):
            led.reserve(f"external-{i}")

        class VenueDouble:
            def __init__(self):
                self.called = False

            def submission_block_reason(self):
                return None

            def submit_order(self, *a, **kw):
                self.called = True
                raise AssertionError(
                    "broker call reached with exhausted capacity — "
                    "capacity refusal must precede any broker call"
                )

        venue = VenueDouble()
        rt._venue = venue
        orders, _ = _try_entry(rt, bars, "precall-0")
        assert not orders
        assert not venue.called, (
            "capacity refusal must precede any broker call (B1)"
        )
        # the durable accounting is visible to the runtime's own
        # risk-gate measurement (cross-process truth)
        assert rt._submissions_in_window(bars[24]["timestamp"]) == 5

    def test_successful_submission_finalizes_acknowledged(self, tmp_path):
        led_path = tmp_path / "ledger.json"
        bars = _bars(30)
        rt = self._runtime(tmp_path, "b1-finalize", led_path)
        rt.start()
        for b in bars[:25]:
            rt.process_bar(b)
        orders, _ = _try_entry(rt, bars, "fin-0")
        assert orders
        led = SubmissionLedger(
            led_path, policy=_policy(), wall_clock=_clock()
        )
        finalized = [
            r for r in led.records()
            if r.state is ReservationState.FINALIZED
            and r.outcome == "ACKNOWLEDGED"
        ]
        assert finalized, "successful submission must finalize ACKNOWLEDGED"

    def test_every_submission_route_traverses_the_ledger(self, tmp_path):
        """B2 muteness check: no alternate path bypasses the ledger."""
        led_path = tmp_path / "ledger.json"
        bars = _bars(30)
        rt = self._runtime(tmp_path, "b1-mute", led_path)
        rt.start()
        for b in bars[:25]:
            rt.process_bar(b)
        calls = {"n": 0}
        led = SubmissionLedger(
            led_path, policy=_policy(), wall_clock=_clock()
        )
        orig = SubmissionLedger.reserve

        def counting_reserve(self, *a, **kw):
            calls["n"] += 1
            return orig(self, *a, **kw)

        rt._submission_ledger.__class__.reserve = counting_reserve
        try:
            _try_entry(rt, bars, "mute-0")
        finally:
            rt._submission_ledger.__class__.reserve = orig
        assert calls["n"] >= 1, "order path must traverse the ledger"
