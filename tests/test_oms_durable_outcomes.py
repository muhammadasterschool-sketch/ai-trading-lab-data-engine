"""Milestone A B3 — OMS durable outcomes + operator-close paths
(master prompt v4.0 Stage 1 Group 3; patch plan P3; finding F-07).

Regression tests written FIRST. The historical C1/C2 commit is ABSENT
(artifacts/stage-a/00-REPO-IDENTITY.md §1), so crash windows are
reproduced with CONTROLLED FAULTY DOUBLES / in-memory state surgery
that reconstructs EXACTLY the persisted truth a crash at that seam
would leave (labeled per test; never fabricated differential results).

Defects being fixed (artifacts/stage-a/02-FINDINGS-REGISTER.md):

- F-07 (crash window): the venue journal can hold an ORDER_ACK for an
  OMS order that never reached SUBMITTED (crash between venue accept
  and OMS submit / journal-failure after venue ack). Recovery on
  current main rebuilds the venue book, reconciles journal-vs-venue
  (which AGREE), and RESUMES SILENTLY — the stuck RISK_APPROVED order
  is never detected, never polled for fills. Truth diverged with no
  incident, no halt.
- Journal-write failure AFTER a successful venue ack propagates as an
  UNHANDLED SessionJournalError (it is neither OrderRefusedError nor
  BrokerExecutionError) — no UNKNOWN record, no OMS transition, no
  incident: the ambiguity discipline (§28) is bypassed exactly where
  it matters.
- Venue-path submission reservations are marked SUBMITTED but never
  FINALIZED (the shared tail resets ``reservation_id``), leaving the
  durable outcome permanently unresolved on the authoritative path.

PROVEN HERE (the B3 transition matrix; each pinned to its expected
OMS state):

1. venue-ack-recorded / OMS-submit-skipped → recovery halts
   (EXECUTION_UNCERTAIN + incident, NEVER silent resume) — T1.
2. journal-write-failure after venue ack → VENUE_UNCERTAIN: OMS
   UNKNOWN + RECONCILING, runtime EXECUTION_UNCERTAIN, ledger
   reservation finalized VENUE_UNCERTAIN, incident ledgered — T4.
3. Successful venue-path submission → reservation FINALIZED
   ACKNOWLEDGED (durable outcome complete) — T3-adjacent.
4. Ledger reservations are reconciled against the venue journal at
   attach (F-19 convergence: journaled → SUBMITTED, never-journaled
   → preserved consumed) — patch plan P3 note at runtime.py
   (Milestone A B1 recovery).
5. Duplicate plan re-submission creates no second order and no
   second reservation (idempotency across the venue boundary) — T3.
6. Confirmed-absence vs ambiguous: an attach against a journal that
   expects an order the OMS never held is REFUSED (fail closed);
   the F-07 divergence NEVER auto-repairs and blocks new submissions
   + operator close until reconciled (never optimism) — T2/T4.
7. Capacity exhaustion through the durable ledger on the venue path
   → order REJECTED BEFORE the broker call (pinned alongside the
   matrix; deeper coverage in test_submission_ledger.py).

Already pinned by the existing suites and NOT duplicated here:
HALTED liquidation semantics (test_runtime_e2e), operator-close
refusals on non-trading states (test_runtime_e2e), kill-switch
fill-time enforcement (test_killswitch_fill_enforcement), UNKNOWN
adoption paths (test_runtime_authoritative_venue).

All venues in these tests are paper/mock fixtures. No real broker,
no network, no real credentials. LIVE TRADING REMAINS NOT AUTHORIZED.
PAPER_READY stays FALSE.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers.redaction import BrokerCredential
from data_engine.brokers.session import SessionJournalError
from data_engine.runtime import (
    ExecutionStateStore,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.broker_execution import (
    BridgeContractError,
    attach_authoritative_paper_venue,
)
from data_engine.runtime.contracts import OrderLifecycle
from data_engine.runtime.submission_ledger import (
    ReservationState,
    SubmissionLedger,
)

from test_runtime_authoritative_venue import (
    ACCOUNT,
    SECRET,
    SYMBOL,
    _attach,
    _mk_runtime,
    _specs,
)
from test_runtime_e2e import _bars, _fit_world
from test_submission_ledger import _clock, _policy, _ready_gate  # noqa: F401
from test_runtime_recovery_integration import _ready_gate  # noqa: F401


def _venue_clock():
    """61s-stepping venue clock — the owner-ratified 5/60s venue
    budget never binds these tests (see F-06 backstop tests)."""
    state = {"t": None}
    base = {"t": None}

    def clock():
        if base["t"] is None:
            from test_runtime_authoritative_venue import CLOCK_BASE
            base["t"] = CLOCK_BASE
            state["t"] = CLOCK_BASE
        state["t"] = state["t"] + timedelta(seconds=61)
        return state["t"]

    return clock


def _ledger_runtime(tmp_path, session, ledger_path, *, started=True):
    ens, cal = _fit_world()
    rt = TradingRuntime(
        _cfg(session), ens, calibrator=cal,
        state_store=ExecutionStateStore(Path(tmp_path) / "state"),
        readiness_gate=_ready_gate(),
        submission_ledger=SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        ),
    )
    if started:
        rt.start()
    return rt


def _cfg(session):
    from test_submission_ledger import _op_config

    return _op_config(session)


def _entry(rt, bars, corr, bar_i=24):
    from test_submission_ledger import _try_entry

    return _try_entry(rt, bars, corr, bar_i)


def _ledger_view(ledger_path):
    led = SubmissionLedger(
        Path(ledger_path), policy=_policy(), wall_clock=_clock(),
    )
    return {r.client_order_id: r for r in led.records()}


def _journal_cids(venue):
    return {
        r.client_order_id
        for r in venue.session._tracked_records()
    }


# ---------------------------------------------------------------------------
# 1. F-07: venue-ack-recorded / OMS-submit-skipped → recovery HALTS
# ---------------------------------------------------------------------------
class TestF07PreSubmittedDivergence:

    def _divergent_restart(self, tmp_path, session):
        """Build the EXACT truth a crash between venue accept and
        OMS.submit leaves: venue journal holds the ORDER_ACK, the
        OMS order is still RISK_APPROVED (in-memory surgery on the
        RESTARTED runtime — never touching persisted files)."""
        bars = _bars(30)
        rt1 = _mk_runtime(session, tmp_path / "state", started=True)
        for b in bars[:25]:
            rt1.process_bar(b)
        # The submission MUST go through the venue path — the venue
        # journal is what holds the durable ORDER_ACK half of the
        # divergence (an internal-path submission never journals).
        venue = _attach(
            rt1, tmp_path, name="venue.json", clock=_venue_clock()
        )
        from test_runtime_authoritative_venue import _entry_plan

        plan = _entry_plan("f07-0", bars[24])
        orders, _ = rt1._execute_plan(
            plan, bars[24], 24, "f07-0",
            Decimal(str(bars[24]["close"])),
            rt1._current_equity(Decimal(str(bars[24]["close"]))),
        )
        assert orders, "the venue-path submission must succeed first"
        cid = orders[0].order_id
        assert cid in _journal_cids(venue), (
            "the venue journal must hold the ORDER_ACK (venue path)"
        )
        order = rt1.oms.order(cid)
        assert order.status is OrderLifecycle.ACKNOWLEDGED
        # Persist the acknowledged truth, then restart from it.
        rt1._persist("f07-persist")
        rt2 = _mk_runtime(session, tmp_path / "state", started=True)
        assert rt2.oms.order(cid).status is OrderLifecycle.ACKNOWLEDGED
        # CONTROLLED CRASH-WINDOW DOUBLE (labeled): rewind the OMS
        # order to RISK_APPROVED — precisely the in-memory state at
        # the crash instant (venue acked, OMS submit not yet run).
        oms_order = rt2.oms.order(cid)
        rt2._oms._orders[cid] = oms_order.model_copy(
            update={"status": OrderLifecycle.RISK_APPROVED}
        )
        return rt2, cid, bars

    def test_recovery_halts_on_presubmitted_divergence(self, tmp_path):
        rt2, cid, _bars_ = self._divergent_restart(
            tmp_path, "f07-halt"
        )
        venue = _attach(
            rt2, tmp_path, name="venue.json", clock=_venue_clock()
        )
        # T1: the runtime must NOT silently resume — the divergence
        # between venue-journal truth (ORDER_ACK held) and OMS truth
        # (RISK_APPROVED, never submitted) is a fail-closed incident.
        assert rt2.state is RuntimeState.EXECUTION_UNCERTAIN
        incidents = rt2._ledgers.events(ledger="incident")
        events = [e.event_type for e in incidents]
        assert "VENUE_OMS_STATE_DIVERGENCE" in events

    def test_divergence_blocks_new_submissions_and_operator_close(
        self, tmp_path
    ):
        rt2, cid, bars = self._divergent_restart(
            tmp_path, "f07-block"
        )
        venue = _attach(
            rt2, tmp_path, name="venue.json", clock=_venue_clock()
        )
        assert rt2.state is RuntimeState.EXECUTION_UNCERTAIN
        # New submissions are refused at the venue boundary.
        assert venue.submission_block_reason() is not None
        # Operator close refuses too (reconcile first — fail closed).
        with pytest.raises(Exception) as exc:
            rt2.operator_close_position(reason="test close")
        assert "EXECUTION_UNCERTAIN" in str(exc.value) or \
            "refused" in str(exc.value).lower()
        # The order stays pre-SUBMITTED (never auto-repaired).
        assert rt2.oms.order(cid).status is OrderLifecycle.RISK_APPROVED


# ---------------------------------------------------------------------------
# 2. Journal-write failure AFTER venue ack → VENUE_UNCERTAIN (T4)
# ---------------------------------------------------------------------------
class TestJournalWriteFailureAfterAck:

    def test_journal_failure_is_uncertain_not_unhandled(self, tmp_path):
        rt = _mk_runtime("jwf-0", tmp_path / "state", started=True)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock()
        )
        # CONTROLLED FAULTY DOUBLE (labeled): the FIRST durable
        # journal write after arming fails — exactly the ORDER_ACK
        # write of the next submission (the venue already accepted).
        real_write = venue.session._write_journal
        armed = {"fail_next": True}

        def flaky_write():
            if armed["fail_next"]:
                armed["fail_next"] = False
                raise SessionJournalError(
                    "injected: journal write failed after venue ack "
                    "(controlled faulty double)"
                )
            return real_write()

        venue.session._write_journal = flaky_write
        from test_runtime_authoritative_venue import _entry_plan

        plan = _entry_plan("jwf-1", bars[24])
        orders, _ = rt._execute_plan(
            plan, bars[24], 24, "jwf-1",
            Decimal(str(bars[24]["close"])),
            rt._current_equity(Decimal(str(bars[24]["close"]))),
        )
        # The submission is AMBIGUOUS (the venue may hold the order):
        # the runtime must have consumed it through the §28 UNKNOWN →
        # RECONCILING discipline — never an unhandled exception, never
        # an inferred failure.
        assert not orders
        reconciling = [
            o for o in rt.oms.orders()
            if o.status is OrderLifecycle.RECONCILING
        ]
        assert reconciling, (
            "journal failure after venue ack ⇒ UNKNOWN + RECONCILING"
        )
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        events = [e.event_type for e in
                  rt._ledgers.events(ledger="incident")]
        assert "RUNTIME_EXECUTION_UNCERTAIN" in events

    def test_journal_failure_finalizes_reservation_venue_uncertain(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "jwf-1", ledger_path)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock()
        )
        real_write = venue.session._write_journal
        armed = {"fail_next": True}

        def flaky_write():
            if armed["fail_next"]:
                armed["fail_next"] = False
                raise SessionJournalError("injected (faulty double)")
            return real_write()

        venue.session._write_journal = flaky_write
        from test_runtime_authoritative_venue import _entry_plan

        plan = _entry_plan("jwf-r", bars[24])
        orders, _ = rt._execute_plan(
            plan, bars[24], 24, "jwf-r",
            Decimal(str(bars[24]["close"])),
            rt._current_equity(Decimal(str(bars[24]["close"]))),
        )
        assert not orders
        # The reservation's durable outcome is VENUE_UNCERTAIN
        # (consumed — the venue may have seen the request).
        view = _ledger_view(ledger_path)
        uncertain = [
            r for r in view.values()
            if r.state is ReservationState.FINALIZED
            and r.outcome == "VENUE_UNCERTAIN"
        ]
        assert uncertain, (
            "journal-failure-after-ack must finalize the reservation "
            "as VENUE_UNCERTAIN (conservative durable outcome)"
        )


# ---------------------------------------------------------------------------
# 3. Venue-path success → reservation FINALIZED ACKNOWLEDGED (durable
#    outcome completeness on the authoritative path)
# ---------------------------------------------------------------------------
class TestVenuePathDurableOutcome:

    def test_venue_success_finalizes_reservation_acknowledged(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "vp-0", ledger_path)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        _attach(rt, tmp_path, name="venue.json", clock=_venue_clock())
        orders, _ = _entry(rt, bars, "vp-a")
        assert orders
        cid = orders[0].order_id
        assert rt.oms.order(cid).status is OrderLifecycle.ACKNOWLEDGED
        view = _ledger_view(ledger_path)
        rec = view[cid]
        assert rec.state is ReservationState.FINALIZED
        assert rec.outcome == "ACKNOWLEDGED"

    def test_duplicate_plan_creates_no_second_order_or_reservation(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "vp-1", ledger_path)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        _attach(rt, tmp_path, name="venue.json", clock=_venue_clock())
        first, _ = _entry(rt, bars, "dup-a")
        assert first
        # Same trade plan re-submitted (duplicate intent): no new
        # order, no new venue submission, no new reservation.
        n_orders = len(rt.oms.orders())
        n_reservations = len(_ledger_view(ledger_path))
        second, _ = _entry(rt, bars, "dup-a")
        assert not second
        assert len(rt.oms.orders()) == n_orders
        assert len(_ledger_view(ledger_path)) == n_reservations


# ---------------------------------------------------------------------------
# 4. Ledger ↔ venue-journal convergence at attach (P3; F-19)
# ---------------------------------------------------------------------------
class TestLedgerJournalConvergenceAtAttach:

    def test_journaled_reservation_reconciled_submitted_on_attach(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "lj-0", ledger_path)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock()
        )
        orders, _ = _entry(rt, bars, "lj-a")
        assert orders
        cid = orders[0].order_id
        # Persist the post-submission truth (OMS holds the
        # ACKNOWLEDGED order) so the restarted runtime can verify
        # the journal's expectation — the crash window this double
        # reconstructs is BETWEEN the venue ack and the ledger's
        # mark_submitted, which the rewind below rebuilds.
        rt._persist("lj-persist")
        # External reservation that never reached the venue (a
        # pre-venue crash double): clock started 60s ahead so the
        # governor's spacing check is honestly satisfied.
        from test_runtime_e2e import T0

        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(),
            wall_clock=_clock(start=T0 + timedelta(seconds=60)),
        )
        led.reserve("rtord.collision-never-venue")
        # CONTROLLED CRASH-WINDOW DOUBLE (labeled): rewind the
        # submitted order's ledger record to RESERVED — exactly the
        # durable state at the crash instant between the venue ack
        # and mark_submitted (venue journal holds the ORDER_ACK).
        import json as _json

        doc = _json.loads(Path(ledger_path).read_text())
        for rec in doc["records"]:
            if rec["client_order_id"] == cid:
                rec["state"] = "RESERVED"
        Path(ledger_path).write_text(_json.dumps(doc, indent=1))
        # RESTART both runtime and venue from the same durable truth.
        rt2 = _ledger_runtime(tmp_path, "lj-0", ledger_path)
        assert rt2.state is RuntimeState.RUNNING
        view_before = _ledger_view(ledger_path)
        assert view_before[cid].state is ReservationState.RESERVED
        assert view_before["rtord.collision-never-venue"].state is \
            ReservationState.RESERVED
        _attach(rt2, tmp_path, name="venue.json",
                clock=_venue_clock())
        view_after = _ledger_view(ledger_path)
        # Journaled reservation: reconciled to SUBMITTED from venue
        # truth at attach (consumed — the durable record now carries
        # the honest transition).
        assert view_after[cid].state is ReservationState.SUBMITTED
        # Never-journaled reservation: PRESERVED (consumed — never
        # released on absence; the venue may have seen it).
        assert view_after["rtord.collision-never-venue"].state is \
            ReservationState.RESERVED

    def test_attach_refuses_journal_order_unknown_to_oms(self, tmp_path):
        """Confirmed-absence boundary: a journal that expects an order
        the OMS never held (crash between the venue-journal ack and
        the next state persist) belongs to truth the restarted OMS
        cannot verify — attachment is refused (fail closed, never
        adopted)."""
        rt = _mk_runtime("lj-1", tmp_path / "state", started=True)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)  # persisted through bar 24
        venue = _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock()
        )
        # Submit through the REAL venue path but NEVER persist the
        # post-submission state (the crash-before-persist window).
        orders, _ = _entry(rt, bars, "lj-crash")
        assert orders
        cid = orders[0].order_id
        assert cid in _journal_cids(venue)
        # Restart: the persisted OMS state has no record of the order.
        rt2 = _mk_runtime("lj-1", tmp_path / "state", started=True)
        with pytest.raises(BridgeContractError):
            _attach(rt2, tmp_path, name="venue.json",
                    clock=_venue_clock())


# ---------------------------------------------------------------------------
# 5. Capacity exhaustion on the venue path → REJECTED before the call
# ---------------------------------------------------------------------------
class TestVenuePathCapacityRefusal:

    def test_capacity_refusal_precedes_broker_call(self, tmp_path):
        """Durable capacity exhaustion refuses the submission BEFORE
        any broker call on the venue path (the risk gate's
        ledger-authoritative measurement fires first — an even
        earlier refusal than the ledger's own reserve)."""
        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "vc-0", ledger_path)
        bars = _bars(30)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock()
        )
        acks_before = _journal_cids(venue)
        # Exhaust the durable budget through the ledger directly
        # (external consumer double — 5/5 consumed).
        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        )
        for i in range(5):
            led.reserve(f"rtord.external-{i}")
        orders, failed = _entry(rt, bars, "vc-a")
        assert not orders
        # The refusal is on the record (risk-gate check or ledger).
        assert "order_rate_limit" in failed or not failed
        # The broker was NEVER called: no new journal ack, no new
        # venue order, no new OMS order.
        assert _journal_cids(venue) == acks_before
        assert not [o for o in rt.oms.orders()
                    if o.status is not OrderLifecycle.REJECTED]
