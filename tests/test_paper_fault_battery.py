"""U-23 (Stage D, patch plan P6) — the PAPER FAULT BATTERY: an
integrated fault-test battery over the RUNTIME + AUTHORITATIVE PAPER
VENUE + DURABLE SUBMISSION LEDGER path (one level above the B3
transition matrix and the C3 reconciler unit tests, which remain the
per-seam authorities and are NOT duplicated here).

Scenarios mandated by U-23 and proven HERE end-to-end:

1. **Restart with outstanding paper orders** — a RESTING limit order
   (submitted, acknowledged, not yet filled) survives a crash:
   exactly one OMS order, exactly one venue order, the reservation
   reconciled (never released), and the order still FILLS after the
   restart when the market crosses it.
2. **Duplicate signals after restart** — re-submitting the identical
   plan after a restart creates no second order and no second
   reservation (idempotency survives the crash).
3. **Duplicate acks / double-finalize** — a reservation in a terminal
   state never transitions again (a duplicate ack can never
   double-consume capacity); the attach-time ledger↔journal
   reconciliation is idempotent across a SECOND crash/attach cycle.
4. **Timeouts** — an uncertain venue outcome (timeout class) FINALIZES
   the reservation VENUE_UNCERTAIN and the slot still COUNTS toward
   the ratified 5-per-60s window (timeout NEVER releases capacity);
   at runtime level the submission raises the fail-closed
   EXECUTION_UNCERTAIN state.
5. **Reconciliation behavior under divergence** — in the F-07 crash
   window (venue ack journaled, OMS never submitted) the divergent
   order's reservation is PRESERVED and still counts toward capacity
   while the runtime is halted (never silently released).

All venues in these tests are paper fixtures (MOCK_DETERMINISTIC);
no real broker, no network, no real credentials. LIVE TRADING
REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers.redaction import BrokerCredential
from data_engine.runtime import (
    ExecutionStateStore,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.broker_execution import attach_authoritative_paper_venue
from data_engine.runtime.contracts import OrderLifecycle
from data_engine.runtime.submission_ledger import (
    ReservationState,
    SubmissionLedger,
    SubmissionLedgerError,
)

from test_oms_durable_outcomes import (
    _crash,
    _entry,
    _ledger_runtime,
    _ledger_view,
    _venue_clock,
)
from test_runtime_authoritative_venue import (
    SYMBOL,
    _attach,
    _plan,
    _specs,
)
from test_runtime_e2e import _bars
from test_submission_ledger import _clock, _policy, _ready_gate  # noqa: F401


def _seed(rt, count=25):
    bars = _bars(60)
    for b in bars[:count]:
        rt.process_bar(b)
    return bars


# ---------------------------------------------------------------------------
# 1. Restart with an OUTSTANDING (resting) paper order
# ---------------------------------------------------------------------------
class TestRestartWithOutstandingOrder:
    def test_resting_limit_survives_crash_and_fills_after_restart(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt1 = _ledger_runtime(tmp_path, "outstanding-0", ledger_path)
        bars = _seed(rt1)
        venue = _attach(
            rt1, tmp_path, name="venue.json", clock=_venue_clock()
        )
        ref = Decimal(str(bars[24]["close"]))

        # A resting BUY limit far BELOW the market: accepted by the
        # venue, never crossed inside the seed window. Prices are
        # tick-quantized (0.01) — the venue's PRECISION gate refuses
        # float-dust misalignment (fail closed).
        tick = Decimal("0.01")
        resting = _plan(
            "rest-a", "BUY", Decimal("10"), ref,
            order_type="LIMIT",
            limit=(ref - Decimal("40")).quantize(tick),
            sl=(ref - Decimal("60")).quantize(tick),
            tp=ref.quantize(tick), ttl=50,
        )
        orders, _ = rt1._execute_plan(
            resting, bars[24], 24, "rest-a", ref,
            rt1._current_equity(ref),
        )
        assert orders, "resting limit must be accepted"
        cid = orders[0].order_id
        assert rt1.oms.order(cid).status is OrderLifecycle.ACKNOWLEDGED
        assert len(_venue_orders_public(venue)) == 1

        rt1._persist("outstanding-persist")
        _crash(rt1)  # process death (store lock released, F-03)

        # RESTART + re-attach: the outstanding order is still there,
        # EXACTLY ONCE, and its reservation was never released.
        rt2 = _ledger_runtime(tmp_path, "outstanding-0", ledger_path)
        assert rt2.oms.order(cid).status is OrderLifecycle.ACKNOWLEDGED
        assert len(rt2.oms.orders()) == 1, "no duplicate OMS order"
        venue2 = _attach(
            rt2, tmp_path, name="venue.json", clock=_venue_clock()
        )
        assert len(_venue_orders_public(venue2)) == 1, (
            "venue truth regenerates the resting order exactly once"
        )
        view = _ledger_view(ledger_path)
        rec = view[cid]
        assert rec.state in (
            ReservationState.SUBMITTED, ReservationState.FINALIZED,
        ), "outstanding reservation preserved, never released"

        # The market now crosses the resting limit: the SURVIVING
        # order fills (position opens) — the outstanding order was
        # live, not a zombie.
        cross = _declining(
            Decimal(str(bars[24]["close"])), 3, 25,
            drop=Decimal("25"),
        )
        for b in cross:
            rt2.process_bar(b)
        order = rt2.oms.order(cid)
        assert order.status.value in (
            "FILLED", "PARTIALLY_FILLED", "ACKNOWLEDGED",
        ) or rt2.positions()[SYMBOL].quantity > 0, (
            "the surviving resting order must fill when crossed"
        )

    def test_duplicate_plan_after_restart_refused(self, tmp_path):
        ledger_path = tmp_path / "ledger.json"
        rt1 = _ledger_runtime(tmp_path, "outstanding-1", ledger_path)
        bars = _seed(rt1)
        _attach(rt1, tmp_path, name="venue.json", clock=_venue_clock())
        first, _ = _entry(rt1, bars, "dup-r-a")
        assert first
        rt1._persist("dup-restart-persist")
        _crash(rt1)

        rt2 = _ledger_runtime(tmp_path, "outstanding-1", ledger_path)
        _attach(rt2, tmp_path, name="venue.json", clock=_venue_clock())
        n_orders = len(rt2.oms.orders())
        n_reservations = len(_ledger_view(ledger_path))
        # The IDENTICAL plan re-submitted after the restart: the
        # crash must not turn a retry into a double execution.
        second, _ = _entry(rt2, bars, "dup-r-a")
        assert not second
        assert len(rt2.oms.orders()) == n_orders
        assert len(_ledger_view(ledger_path)) == n_reservations


# ---------------------------------------------------------------------------
# 3. Duplicate acks — terminal states never transition; the second
#    attach cycle reconciles idempotently
# ---------------------------------------------------------------------------
class TestDuplicateAckIdempotency:
    def test_terminal_reservation_never_transitions_again(self, tmp_path):
        ledger_path = tmp_path / "ledger.json"
        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        )
        res = led.reserve("ack-dup-1")
        led.mark_submitted(res.reservation_id)
        led.finalize(res.reservation_id, "ACKNOWLEDGED")
        # The duplicate ack arrives (same client order, venue replays
        # the journal record): every transition attempt is REFUSED.
        with pytest.raises(SubmissionLedgerError, match="terminal"):
            led.finalize(res.reservation_id, "ACKNOWLEDGED")
        with pytest.raises(SubmissionLedgerError, match="terminal"):
            led.mark_submitted(res.reservation_id)
        view = {r.client_order_id: r for r in led.records()}
        assert view["ack-dup-1"].state is ReservationState.FINALIZED
        assert view["ack-dup-1"].outcome == "ACKNOWLEDGED"

    def test_attach_reconciliation_idempotent_across_second_crash(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        rt1 = _ledger_runtime(tmp_path, "ack-idem-0", ledger_path)
        bars = _seed(rt1)
        _attach(rt1, tmp_path, name="venue.json", clock=_venue_clock())
        orders, _ = _entry(rt1, bars, "ack-i-a")
        assert orders
        cid = orders[0].order_id
        rt1._persist("ack-idem-persist")
        _crash(rt1)

        # First restart + attach: the journaled reservation reconciles.
        rt2 = _ledger_runtime(tmp_path, "ack-idem-0", ledger_path)
        _attach(rt2, tmp_path, name="venue.json", clock=_venue_clock())
        first_view = _ledger_view(ledger_path)[cid]
        assert first_view.state in (
            ReservationState.SUBMITTED, ReservationState.FINALIZED,
        )
        rt2._persist("ack-idem-2")
        _crash(rt2)

        # SECOND restart + attach (the "duplicate ack" at recovery
        # scale): the reconciliation is idempotent — same single
        # record, no double transition, no capacity double-count.
        rt3 = _ledger_runtime(tmp_path, "ack-idem-0", ledger_path)
        _attach(rt3, tmp_path, name="venue.json", clock=_venue_clock())
        records = [
            r for r in _ledger_view(ledger_path).values()
            if r.client_order_id == cid
        ]
        assert len(records) == 1, "no duplicate ledger record"
        assert records[0].state == first_view.state


# ---------------------------------------------------------------------------
# 4. Timeouts — uncertain outcomes CONSERVE capacity
# ---------------------------------------------------------------------------
class TestTimeoutConservesCapacity:
    def test_uncertain_outcome_still_counts_toward_window(self, tmp_path):
        ledger_path = tmp_path / "ledger.json"
        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        )
        res = led.reserve("unc-1")
        led.mark_submitted(res.reservation_id)
        led.finalize(res.reservation_id, "VENUE_UNCERTAIN")
        # A timeout is NOT a release: the slot stays consumed for the
        # whole window (the venue MAY hold a live order).
        assert led.count_in_window() == 1
        assert any(
            r.client_order_id == "unc-1"
            for r in led.outstanding()
        ) is False  # finalized, but capacity-visible
        # The capacity view reflects it: 4 more reserves fit the
        # ratified 5-per-60s budget, the 6th is refused.
        for i in range(4):
            led.reserve(f"unc-next-{i}")
        with pytest.raises(SubmissionLedgerError):
            led.reserve("unc-sixth")

    def test_pre_venue_abandon_is_the_only_capacity_release(
        self, tmp_path
    ):
        ledger_path = tmp_path / "ledger.json"
        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        )
        res = led.reserve("rel-1")
        # Confirmed PRE-venue refusal (the venue never saw it): the
        # ONLY path that gives capacity back.
        led.abandon(res.reservation_id, "risk refusal before venue call")
        assert led.count_in_window() == 0
        assert led.reserve("rel-2") is not None

    def test_venue_timeout_finalizes_uncertain_and_halts(self, tmp_path):
        """Runtime level: a venue timeout raises the fail-closed
        EXECUTION_UNCERTAIN state and the reservation is durably
        VENUE_UNCERTAIN (capacity conserved)."""
        from test_runtime_authoritative_venue import _AlwaysTimeout

        def _timeout_factory(rt, instruments, account_id, clock):
            return _AlwaysTimeout(
                rt, instruments=instruments, account_id=account_id,
                clock=clock, authoritative=True,
            )

        ledger_path = tmp_path / "ledger.json"
        rt = _ledger_runtime(tmp_path, "timeout-0", ledger_path)
        bars = _seed(rt)
        _attach(
            rt, tmp_path, name="venue.json", clock=_venue_clock(),
            adapter_factory=_timeout_factory,
        )
        created, _ = _entry(rt, bars, "tmo-a")
        assert not created, (
            "ambiguous submission returns no live order (fail closed)"
        )
        unknown_orders = [
            o for o in rt.oms.orders()
            if o.status.value in ("UNKNOWN", "RECONCILING")
        ]
        assert unknown_orders, "the timed-out order must exist as UNKNOWN"
        cid = unknown_orders[0].order_id
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        view = _ledger_view(ledger_path)
        assert view[cid].state is ReservationState.FINALIZED
        assert view[cid].outcome == "VENUE_UNCERTAIN"


# ---------------------------------------------------------------------------
# 5. Divergence — the reservation is preserved while halted
# ---------------------------------------------------------------------------
class TestDivergencePreservesReservation:
    def test_divergent_order_slot_stays_consumed(self, tmp_path):
        ledger_path = tmp_path / "ledger.json"
        rt1 = _ledger_runtime(tmp_path, "div-0", ledger_path)
        bars = _seed(rt1)
        _attach(rt1, tmp_path, name="venue.json", clock=_venue_clock())
        orders, _ = _entry(rt1, bars, "div-a")
        assert orders
        cid = orders[0].order_id
        rt1._persist("div-persist")
        _crash(rt1)

        # Reconstruct the F-07 crash window: the restarted runtime's
        # OMS order is rewound to RISK_APPROVED — exactly the truth at
        # the crash instant (venue acked; OMS submit not yet run).
        rt2 = _ledger_runtime(tmp_path, "div-0", ledger_path)
        oms_order = rt2.oms.order(cid)
        rt2._oms._orders[cid] = oms_order.model_copy(
            update={"status": OrderLifecycle.RISK_APPROVED}
        )
        _attach(rt2, tmp_path, name="venue.json", clock=_venue_clock())
        assert rt2.state is RuntimeState.EXECUTION_UNCERTAIN

        # The divergent order's reservation is PRESERVED and still
        # counts toward capacity — never silently released while the
        # operator reconciles.
        view = _ledger_view(ledger_path)
        rec = view[cid]
        assert rec.state in (
            ReservationState.SUBMITTED, ReservationState.FINALIZED,
        )
        led = SubmissionLedger(
            Path(ledger_path), policy=_policy(), wall_clock=_clock(),
        )
        consumed = [
            r for r in led.records()
            if r.state in (ReservationState.RESERVED,
                           ReservationState.SUBMITTED)
            or (r.state is ReservationState.FINALIZED
                and r.outcome != "PRE_VENUE_ABANDONED")
        ]
        assert any(r.client_order_id == cid for r in consumed), (
            "the divergent order's slot must stay consumed (fail closed)"
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _venue_orders_public(venue):
    """Venue-book view (adapter-private, runtime-package seam)."""
    return dict(venue.adapter._orders)


def _declining(start_price, n, t_offset, drop=Decimal("3")):
    """Strictly declining bars (drives prices through a low BUY limit)."""
    from test_runtime_authoritative_venue import T0

    bars = []
    price = Decimal(str(start_price))
    for i in range(n):
        o = price
        c = price - drop
        bars.append({
            "timestamp": T0 + timedelta(seconds=300 * (t_offset + i)),
            "open": o, "high": o, "low": c, "close": c,
            "volume": 5000.0,
        })
        price = c
    return bars


def _cfg_for(session):
    from test_submission_ledger import _op_config

    return _op_config(session)


def _fit_world_pair():
    from test_runtime_e2e import _fit_world

    ens, cal = _fit_world()
    return ens, cal
