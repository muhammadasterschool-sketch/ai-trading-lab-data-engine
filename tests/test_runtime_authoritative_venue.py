"""Batch 5 acceptance tests — broker-neutral execution FULLY
integrated into the AUTHORITATIVE paper runtime order path (Phase M2
completion, multi-broker architecture mandate).

The integration being proven (``runtime/broker_execution.py`` — the
authoritative venue seam):

1. SINGLE authoritative submission path: when a venue session is
   attached, every runtime order (entries AND protective exits)
   flows gate -> OMS (fingerprint-bound approval) -> BrokerSession
   (isolation > health > reconciliation-gate > kill-switch > risk
   binding verification > journal idempotency > capability +
   precision pre-checks > venue adapter). There is NO hidden
   direct-execution fallback once a venue is attached.
2. The fill model is UNCHANGED: the venue hosts the runtime's own
   ``PaperExecutionAdapter`` — venue-mode fills are bit-identical to
   the internal path (same fill ids, quantities, prices, costs).
3. Fills are applied EXACTLY ONCE (OMS -> position -> P&L -> ledger).
4. UNKNOWN ambiguity blocks ALL new submissions until reconciliation
   resolves it from venue truth — a lost ack NEVER infers failure.
5. Restart idempotency: the same ``client_order_id`` (= OMS order id)
   never executes twice across restarts; key reuse with different
   details is refused; a split run is identical to a whole run.
6. Capability/precision enforcement distinguishes ``price`` (limit
   misalignment) from quantity (lot misalignment) — no silent
   rounding, the venue never sees a bad shape.
7. Account isolation: no credential material reaches the runtime
   ledgers, the state snapshot, the OMS records or the session journal.
8. Fail-closed defaults: degraded session / unhealthy adapter /
   unresolvable ambiguity / live non-venue orders all refuse.

All venues in these tests are paper fixtures (MOCK_DETERMINISTIC);
no real broker, no network, no real credentials. LIVE TRADING
REMAINS NOT AUTHORIZED; PAPER_READY stays FALSE.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers.capabilities import ExecutionMode
from data_engine.brokers.errors import (
    BrokerErrorCategory,
    BrokerExecutionError,
    OrderRefusedError,
    UnknownOrderStateError,
)
from data_engine.brokers.models import (
    InstrumentSpec,
    OrderKind,
    OrderRequest,
    Side,
    TimeInForce,
    VenueOrderStatus,
)
from data_engine.brokers.redaction import BrokerCredential, find_secret_leak
from data_engine.paper.simulator import ExecutionRealism
from data_engine.runtime import (
    BridgeContractError,
    ExecutionStateStore,
    KillSwitchScope,
    RuntimeConfig,
    RuntimePaperExecutionAdapter,
    RuntimeState,
    TradingRuntime,
    attach_runtime_paper_session,
)
from data_engine.runtime.broker_execution import (
    RUNTIME_PAPER_VENUE_ID,
    _VenueOrder,
    attach_authoritative_paper_venue,
)
from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    TradePlan,
    UncertaintyReport,
)
from data_engine.runtime.pnl import PositionState

from test_runtime_e2e import T0, _bars, _fit_world
from test_runtime_recovery_integration import (
    _partial_realism,
    _ready_gate,
)

SYMBOL = "TEST/USD"
ACCOUNT = "paper-acct-1"
SECRET = "b5-opaque-play-money-secret"
CLOCK_BASE = T0 + timedelta(hours=6)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def _clock():
    """Stepping deterministic clock (journal + submission times)."""
    state = {"t": CLOCK_BASE}

    def clock():
        state["t"] = state["t"] + timedelta(seconds=1)
        return state["t"]

    return clock


def _specs(lot=Decimal("0.0001"), tick=Decimal("0.01"),
           max_qty=Decimal("100000")):
    return {
        SYMBOL: InstrumentSpec(
            broker_id=RUNTIME_PAPER_VENUE_ID,
            symbol=SYMBOL,
            broker_symbol=SYMBOL,
            base_asset="TEST",
            quote_asset="USD",
            tick_size=tick,
            lot_step=lot,
            min_quantity=Decimal("0.0001"),
            max_quantity=max_qty,
            min_notional=Decimal("0"),
        ),
    }


def _mk_runtime(session, store_dir, ens_cal=None, realism=None,
                started=True, notrade=True):
    """Operational (fully-gated, persistent) paper runtime.

    ``notrade=True`` (default): the decision engine never opens
    organic positions (crash threshold 0.0 — the RUN-DD-1 fixture
    discipline), so hand-built plans drive the order path in a
    controlled position state. ``notrade=False``: the organic
    decision -> plan -> order chain fires (the e2e world)."""
    if ens_cal is None:
        ens_cal = _fit_world()
    ens, cal = ens_cal
    cfg = RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        max_crash_probability=0.0 if notrade else 0.20,
    )
    rt = TradingRuntime(
        cfg, ens, calibrator=cal,
        state_store=ExecutionStateStore(Path(store_dir)),
        readiness_gate=_ready_gate(), realism=realism,
    )
    if started:
        rt.start()
    return rt


def _attach(rt, tmp_path, *, name="venue.json", instruments=None,
            adapter_factory=None, account=ACCOUNT, secret=SECRET,
            clock=None):
    return attach_authoritative_paper_venue(
        rt,
        account_id=account,
        journal_path=Path(tmp_path) / name,
        clock=_clock() if clock is None else clock,
        instruments=_specs() if instruments is None else instruments,
        credential=BrokerCredential(account, secret),
        adapter_factory=adapter_factory,
        sleeper=lambda s: None,
    )


def _plan(corr, side, qty, ref, order_type="MARKET", limit=None,
          sl=None, tp=None, ttl=3):
    """Hand-built risk-clean plan driven through the REAL
    ``TradingRuntime._execute_plan`` order path (the same precedent
    as the RUN-DD-1 acceptance tests)."""
    return TradePlan(
        trade_plan_id=f"tp-{corr}", decision_id=f"dec-{corr}",
        symbol=SYMBOL, side=side, quantity=qty, notional=qty * ref,
        entry=EntryConstraints(order_type=order_type, limit_price=limit,
                               ttl_bars=ttl),
        stop_loss=sl, take_profit=tp,
        risk_budget=Decimal("100"), expected_return=0.01,
        risk_reward_ratio=2.0,
        uncertainty=UncertaintyReport(
            confidence=0.9, entropy=0.3, ensemble_disagreement=0.1,
        ),
        crash_risk={"probability": 0.0},
        model_context={"model": "batch5-authoritative-venue"},
        correlation_id=corr,
    )


def _entry_plan(corr, bar, qty=Decimal("10")):
    """A risk-clean BUY plan anchored to ``bar``'s close with WIDE
    protective levels (no SL/TP breach inside the test windows — the
    carve-out test builds its own tight-SL plan inline)."""
    ref = Decimal(str(bar["close"]))
    return _plan(corr, DecisionAction.BUY, qty, ref,
                 sl=ref - Decimal("20"), tp=ref + Decimal("20"))


def _submit_plan(rt, plan, bar, idx):
    """Drive ONE plan through the REAL runtime order path."""
    ref = Decimal(str(bar["close"]))
    return rt._execute_plan(plan, bar, idx, plan.correlation_id, ref,
                            rt._current_equity(ref))


def _submit_entry(rt, corr, bar, idx, qty=Decimal("10")):
    return _submit_plan(rt, _entry_plan(corr, bar, qty), bar, idx)


def _seeded(rt, count=25):
    """Admit ``count`` bars (no-trade world: crash floor blocks)."""
    bars = _bars(60)
    for b in bars[:count]:
        rt.process_bar(b)
    return bars


def _declining_bars(start_price, n, t_offset, drop=Decimal("3")):
    """Strictly declining bars (forces SL breaches)."""
    from datetime import datetime, UTC
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


def _venue_orders(venue):
    """Venue-book view (adapter-private, runtime-package seam)."""
    return dict(venue.adapter._orders)


def _journal_acks(venue):
    return [r for r in venue.session.journal_records()
            if r.entry_type == "ORDER_ACK"]


def _journal_refusals(venue):
    return [r for r in venue.session.journal_records()
            if r.entry_type == "ORDER_REFUSED"]


# ----------------------------------------------------------------------
# 1. The single authoritative submission path
# ----------------------------------------------------------------------
class TestAuthoritativeSubmissionPath:

    def test_approved_order_reaches_broker_session_and_fills(self, tmp_path):
        """An approved runtime order lands at the BrokerSession under
        its OMS identity, fills through the hosted venue model, and
        the OMS/position chain is updated — the FULL path."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-authoritative", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        created, failed = _submit_entry(rt, "corr-b5-1", bars[24], 24)
        assert created, f"order must be created (failed={failed})"
        order = created[0]
        # The session journaled an ORDER_ACK under the OMS identity.
        acks = _journal_acks(venue)
        assert [a.client_order_id for a in acks] == [order.order_id]
        # The venue holds exactly this order.
        assert list(_venue_orders(venue)) == [order.order_id]
        # Fill on subsequent bars (latency: submitted at bar 24).
        for b in bars[25:28]:
            rt.process_bar(b)
        order = rt.oms.order(order.order_id)
        assert order.status.value == "FILLED"
        assert order.fills, "venue fills must reach the OMS"
        pos = rt._positions[SYMBOL]
        assert pos.quantity == Decimal("10")
        # The venue book and the OMS agree exactly (fills once).
        vorder = _venue_orders(venue)[order.order_id]
        assert vorder.filled_quantity == order.filled_quantity
        assert [f.fill_id for f in vorder.fills] == \
            [f.fill_id for f in order.fills]

    def test_venue_fills_bit_identical_to_internal_path(self, tmp_path):
        """The SAME deterministic world produces BIT-IDENTICAL orders
        and fills with and without the venue attached — the fill model
        is provably unchanged (no invented semantics)."""
        ens_cal = _fit_world()
        bars = _bars(40)
        runs = {}
        for mode in ("internal", "venue"):
            rt = _mk_runtime("b5-twin", tmp_path / f"state-{mode}",
                             ens_cal=ens_cal)
            for b in bars[:25]:
                rt.process_bar(b)
            if mode == "venue":
                _attach(rt, tmp_path / f"twin-{mode}")
            _submit_entry(rt, "corr-twin-24", bars[24], 24)
            for i in (25, 26):
                rt.process_bar(bars[i])
                _submit_entry(rt, f"corr-twin-{i}", bars[i], i)
            for b in bars[27:40]:
                rt.process_bar(b)
            runs[mode] = rt

        def _signature(rt):
            return [
                (o.order_id, o.status.value,
                 [(f.fill_id, str(f.quantity), str(f.price),
                   str(f.commission + f.slippage_cost + f.spread_cost),
                   f.bar_index) for f in o.fills])
                for o in rt.oms.orders()
            ]

        assert _signature(runs["internal"]) == _signature(runs["venue"])
        internal_pnl = str(runs["internal"]._positions.get(
            SYMBOL, PositionState(symbol=SYMBOL)).realized_pnl)
        venue_pnl = str(runs["venue"]._positions.get(
            SYMBOL, PositionState(symbol=SYMBOL)).realized_pnl)
        assert venue_pnl == internal_pnl

    def test_risk_refusal_never_reaches_the_venue(self, tmp_path):
        """A risk-gate refusal happens BEFORE any venue submission:
        no OMS order, no journal records, no venue state."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-risk-refusal", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        # A plan without protective levels fails the mandatory SL/TP
        # geometry check for entries.
        ref = Decimal(str(bars[24]["close"]))
        naked = _plan("corr-b5-nosl", DecisionAction.BUY, Decimal("10"),
                      ref, sl=None, tp=None)
        created, failed = _submit_plan(rt, naked, bars[24], 24)
        assert not created
        assert failed, "the gate must name its failed checks"
        assert not _journal_acks(venue)
        assert not _journal_refusals(venue)
        assert not _venue_orders(venue)
        assert not rt.oms.orders()

    def test_organic_full_chain_through_the_venue(self, tmp_path):
        """The organic decision -> plan -> order chain flows through
        the venue: every created order is venue-acked under its OMS
        id, fills/exits fire, and the end state matches the internal
        control run exactly.

        Venue clock steps 61s per call: the owner-ratified venue
        order budget (F-06 backstop — max 5 per 60s) never binds for
        the organic chain, which legitimately spaces submissions far
        beyond it on 5-minute bars (the 1s default clock would pack
        every submission into one artificial 60s window)."""
        ens_cal = _fit_world()
        control = _mk_runtime("b5-organic", tmp_path / "ctl",
                              ens_cal=ens_cal, notrade=False)
        for b in _bars(60):
            control.process_bar(b)

        rt = _mk_runtime("b5-organic", tmp_path / "state",
                         ens_cal=ens_cal, notrade=False)
        fast = {"t": CLOCK_BASE}

        def fast_clock():
            fast["t"] = fast["t"] + timedelta(seconds=61)
            return fast["t"]

        venue = _attach(rt, tmp_path, clock=fast_clock)
        outcomes = [rt.process_bar(b) for b in _bars(60)]
        assert any(o.orders_created for o in outcomes)
        assert any(o.fills for o in outcomes)

        live_ids = {o.order_id for o in rt.oms.orders()}
        acked = {a.client_order_id for a in _journal_acks(venue)}
        assert live_ids <= acked, "every OMS order must be venue-acked"
        # Identical end-state to the internal control run.
        assert len(rt.oms.orders()) == len(control.oms.orders())
        assert [o.order_id for o in rt.oms.orders()] == \
            [o.order_id for o in control.oms.orders()]
        assert str(rt._positions[SYMBOL].realized_pnl) == \
            str(control._positions[SYMBOL].realized_pnl)
        assert rt.state is RuntimeState.RUNNING

    def test_side_band_factory_still_functions(self, tmp_path):
        """The Batch-3 side-band surface is preserved untouched."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-sideband", tmp_path / "state",
                         ens_cal=ens_cal)
        _seeded(rt, 25)
        session = attach_runtime_paper_session(
            rt, account_id=ACCOUNT,
            journal_path=Path(tmp_path) / "sideband.json",
            clock=_clock(), instruments=_specs(),
        )
        session.connect(BrokerCredential(ACCOUNT, SECRET))
        bars = _bars(60)
        ref = Decimal(str(bars[24]["close"]))
        request = OrderRequest(
            client_order_id="coi-sideband-1", account_id=ACCOUNT,
            symbol=SYMBOL, side=Side.BUY, order_kind=OrderKind.MARKET,
            quantity=Decimal("10"), price=None, stop_price=None,
            time_in_force=TimeInForce.GTC, stop_loss=ref - Decimal("2"),
            take_profit=ref + Decimal("4"), reduce_only=False,
        )
        ack = session.submit_order(request)
        assert ack.status in (VenueOrderStatus.OPEN,
                              VenueOrderStatus.PARTIALLY_FILLED)


# ----------------------------------------------------------------------
# 2. Fail-closed boundaries
# ----------------------------------------------------------------------
class TestFailClosedBoundaries:

    def test_kill_switch_blocks_new_venue_orders(self, tmp_path):
        """An active governing kill switch refuses new exposure at the
        runtime gate (before the venue is ever consulted)."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-ks", tmp_path / "state", ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "batch5 test trip", SYMBOL)

        created, failed = _submit_entry(rt, "corr-b5-ks", bars[24], 24)
        assert not created
        assert "kill_switch" in failed
        assert not _journal_acks(venue)
        assert not _venue_orders(venue)
        assert not rt.oms.orders()

    def test_inflight_order_cancelled_at_fill_time_via_venue(self, tmp_path):
        """In-flight orders remain governed at FILL time: an active
        kill switch cancels the unfilled remainder at BOTH the OMS and
        the venue (one cancellation, consistent state)."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-ks-fill", tmp_path / "state",
                         ens_cal=ens_cal, realism=_partial_realism())
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        created, _ = _submit_entry(rt, "corr-b5-ksf", bars[24], 24)
        assert created
        oid = created[0].order_id
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "batch5 fill-time trip", SYMBOL)
        rt.process_bar(bars[25])

        order = rt.oms.order(oid)
        assert order.status.value == "CANCELLED"
        vorder = _venue_orders(venue)[oid]
        assert vorder.status is VenueOrderStatus.CANCELLED
        # No fills were applied while the switch was active.
        assert not order.fills
        assert SYMBOL not in rt._positions or \
            rt._positions[SYMBOL].is_flat

    def test_exit_orders_respect_the_risk_reduction_carveout(self, tmp_path):
        """Protective exits traverse the SAME venue boundary AND the
        risk-reduction exception: with a SYMBOL kill switch active, an
        organically triggered protective exit is still submitted at
        the venue and fills, closing the position."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-exit", tmp_path / "state", ens_cal=ens_cal)
        bars = _bars(26)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(rt, tmp_path)

        # Entry with a tight SL below the entry close.
        entry_ref = Decimal(str(bars[24]["close"]))
        entry = _plan("corr-b5-exit-e", DecisionAction.BUY, Decimal("10"),
                      entry_ref, sl=entry_ref - Decimal("2"),
                      tp=entry_ref + Decimal("4"))
        created, _ = _submit_plan(rt, entry, bars[24], 24)
        assert created
        rt.process_bar(bars[25])  # entry fills; SL attaches to position
        pos = rt._positions[SYMBOL]
        assert pos.quantity == Decimal("10")
        assert pos.stop_loss is not None

        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "batch5 exit carve-out trip", SYMBOL)

        # Declining bars breach the SL while the switch is ACTIVE: the
        # protective exit must still traverse the venue (carve-out).
        falling = _declining_bars(float(bars[25]["close"]), 6,
                                  t_offset=26)
        exit_ids = []
        for b in falling:
            outcome = rt.process_bar(b)
            exit_ids.extend(outcome.orders_created)
        assert exit_ids, "the protective exit must fire under the switch"
        exit_id = exit_ids[0]
        acked = {a.client_order_id for a in _journal_acks(venue)}
        assert exit_id in acked, "exit must be venue-acked (carve-out)"

        for b in _declining_bars(
                float(falling[-1]["close"]), 4, t_offset=32):
            rt.process_bar(b)
        assert rt.oms.order(exit_id).status.value == "FILLED"
        assert rt._positions[SYMBOL].is_flat

    def test_precision_refusals_distinguish_price_and_quantity(
            self, tmp_path):
        """Lot-misaligned quantities and tick-misaligned limit prices
        are both REFUSED pre-venue (never silently rounded), and the
        refusal messages distinguish the two dimensions."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-prec", tmp_path / "state", ens_cal=ens_cal)
        bars = _seeded(rt, 25)

        # lot step 1: a fractional quantity is misaligned.
        venue = _attach(rt, tmp_path, instruments=_specs(
            lot=Decimal("1"), tick=Decimal("0.01")))
        created, _ = _submit_entry(rt, "corr-b5-pq", bars[24], 24,
                                   qty=Decimal("10.5"))
        assert not created
        refused = _journal_refusals(venue)
        assert [r.reason_code for r in refused] == ["PRECISION_INVALID"]
        # The refused order is REJECTED in the OMS, never executed; the
        # ledgered rejection reason names the QUANTITY dimension
        # verbatim (lot step misalignment — never silently rounded).
        orders = list(rt.oms.orders())
        assert orders and orders[0].status.value == "REJECTED"
        rejects = [e for e in rt.ledgers.events(ledger="order")
                   if e.event_type == "ORDER_REJECTED"
                   and e.payload.get("order_id") == orders[0].order_id]
        assert rejects and "lot step" in rejects[0].payload.get(
            "reason", "")
        assert not orders[0].fills
        assert not _venue_orders(venue)

    def test_tick_misaligned_limit_price_refused(self, tmp_path):
        """A LIMIT order whose limit price is off-tick is refused with
        the PRICE dimension named (price vs stop_price distinction)."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-prec-lim", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path, instruments=_specs(
            lot=Decimal("0.0001"), tick=Decimal("0.01")))

        ref = Decimal(str(bars[24]["close"]))
        # An off-tick limit price (half a tick above the reference).
        limit = ref + Decimal("0.005")
        plan_l = _plan("corr-b5-pl", DecisionAction.BUY, Decimal("10"),
                       ref, order_type="LIMIT", limit=limit,
                       sl=ref - Decimal("2"), tp=ref + Decimal("4"))
        created, _ = _submit_plan(rt, plan_l, bars[24], 24)
        assert not created
        refused = _journal_refusals(venue)
        assert [r.reason_code for r in refused] == ["PRECISION_INVALID"]
        # The rejection reason names the PRICE dimension verbatim
        # (price vs stop_price distinction: the LIMIT price is the
        # misaligned field, never silently rounded).
        orders = list(rt.oms.orders())
        assert orders and orders[0].status.value == "REJECTED"
        rejects = [e for e in rt.ledgers.events(ledger="order")
                   if e.event_type == "ORDER_REJECTED"
                   and e.payload.get("order_id") == orders[0].order_id]
        assert rejects and "tick" in rejects[0].payload.get(
            "reason", "")
        assert not _venue_orders(venue)

    def test_missing_instrument_spec_refuses_attach(self, tmp_path):
        """Attaching a venue without a spec for the runtime's own
        symbol is refused — precision cannot be enforced on guesses."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-nospec", tmp_path / "state", ens_cal=ens_cal)
        _seeded(rt, 25)
        with pytest.raises(BridgeContractError):
            _attach(rt, tmp_path, instruments={})

    def test_degraded_session_blocks_all_new_submissions(self, tmp_path):
        """A reconciliation mismatch (phantom venue order) degrades
        the session and blocks every NEW submission — entries AND
        protective exits — until reconciliation is clean."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-degraded", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        # A phantom: the venue holds an order the journal never tracked
        # (injected directly into the venue book — the session pipeline
        # itself cannot produce this state: every governed submission
        # journals, and the adapter refuses ungoverned submissions).
        phantom = OrderRequest(
            client_order_id="coi-phantom-b5", account_id=ACCOUNT,
            symbol=SYMBOL, side=Side.BUY, order_kind=OrderKind.MARKET,
            quantity=Decimal("5"), price=None, stop_price=None,
            time_in_force=TimeInForce.GTC, stop_loss=None,
            take_profit=None, reduce_only=False,
        )
        venue.adapter._orders["coi-phantom-b5"] = _VenueOrder(
            request=phantom, venue_order_id="rtpv-phantom-b5",
            submitted_at=bars[24]["timestamp"],
            execution_anchor=bars[24]["timestamp"],
        )
        report = venue.reconcile()
        assert not report.ok
        assert any(
            m.kind.value == "PHANTOM_ORDER_AT_VENUE"
            for m in report.mismatches
        )
        assert venue.session.degraded

        created, failed = _submit_entry(rt, "corr-b5-deg", bars[24], 24)
        assert not created
        assert "venue_reconciliation_required" in failed
        # The blocked order is auditable in the OMS as REJECTED — the
        # venue never saw it and no fills exist.
        orders = list(rt.oms.orders())
        assert orders and orders[0].status.value == "REJECTED"
        assert not orders[0].fills

    def test_unhealthy_adapter_refuses_submissions(self, tmp_path):
        """A disconnected venue refuses new submissions fail-closed
        and recovers after an explicit reconnect."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-health", tmp_path / "state", ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)
        venue.session.disconnect()

        created, failed = _submit_entry(rt, "corr-b5-h", bars[24], 24)
        assert not created
        assert "venue_not_connected" in failed
        blocked = list(rt.oms.orders())
        assert blocked and blocked[0].status.value == "REJECTED"

        venue.session.reconnect()
        created, _ = _submit_entry(rt, "corr-b5-h2", bars[24], 24)
        assert created


# ----------------------------------------------------------------------
# 3. UNKNOWN ambiguity handling
# ----------------------------------------------------------------------
class _UnknownOnce(RuntimePaperExecutionAdapter):
    """Paper fixture: the venue ACCEPTS the order but the ack is lost
    exactly once (accepted-but-unacknowledged)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._fired = False

    def submit_order(self, request):
        ack = super().submit_order(request)
        if not self._fired:
            self._fired = True
            raise UnknownOrderStateError(
                "injected unknown-ack (paper fixture)",
                broker_id=self.broker_id,
                client_order_id=request.client_order_id,
            )
        return ack


class _AlwaysTimeout(RuntimePaperExecutionAdapter):
    """Paper fixture: the venue ACCEPTS the order but the ack channel
    is permanently broken (TIMEOUT on every attempt — retries
    exhaust; the outcome stays ambiguous and unresolvable)."""

    def submit_order(self, request):
        super().submit_order(request)
        raise BrokerExecutionError(
            "injected ack timeout (paper fixture)",
            category=BrokerErrorCategory.TIMEOUT,
            broker_id=self.broker_id,
        )


class _TimesOutUntilAdopted(RuntimePaperExecutionAdapter):
    """Paper fixture: the venue ACCEPTS the order but the ack is lost
    for the ORIGINAL submission (every retry attempt of the first
    session submission times out while the OMS order is still
    RISK_APPROVED). A LATER submission of the same order (the
    reconciliation-driven re-adoption, OMS order already resolved to
    SUBMITTED) succeeds — a transient ack loss that recovery can
    heal."""

    def submit_order(self, request):
        ack = super().submit_order(request)
        from data_engine.runtime.contracts import OrderLifecycle
        try:
            oms_order = self._runtime._oms.order(request.client_order_id)
        except Exception:
            return ack
        if oms_order.status is OrderLifecycle.RISK_APPROVED:
            raise BrokerExecutionError(
                "injected ack timeout (paper fixture)",
                category=BrokerErrorCategory.TIMEOUT,
                broker_id=self.broker_id,
            )
        return ack


def _adapter_wrapper(cls):
    def factory(rt, instruments, account_id, clock):
        return cls(rt, instruments=instruments, account_id=account_id,
                   clock=clock, authoritative=True)
    return factory


class TestUnknownAmbiguity:

    def test_unknown_ack_blocks_until_reconciled(self, tmp_path):
        """An ambiguous submission marks the OMS order UNKNOWN,
        degrades the session, HALTS bar processing, and NEVER infers
        failure from the lost ack: reconciliation adopts venue truth
        (the order WAS accepted), the runtime resumes, and the venue
        fills apply exactly once."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-unknown", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path,
                        adapter_factory=_adapter_wrapper(_UnknownOnce))

        created, _ = _submit_entry(rt, "corr-b5-u", bars[24], 24)
        assert not created, "ambiguous submission creates no live order"
        unknown_orders = [o for o in rt.oms.orders()
                          if o.status.value in ("UNKNOWN", "RECONCILING")]
        assert unknown_orders
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        assert venue.session.degraded

        # New submissions are blocked while the outcome is ambiguous
        # (fail-closed: the runtime state refuses even direct
        # submissions, never just the next bar).
        blocked, blocked_failed = _submit_entry(
            rt, "corr-b5-u2", bars[24], 24)
        assert not blocked
        # The most specific block reason first: the session is degraded
        # (UNKNOWN on record) AND the runtime is EXECUTION_UNCERTAIN.
        assert blocked_failed == ("venue_reconciliation_required",)
        # Only the REJECTED blocked order exists besides the ambiguous
        # one — nothing reached the venue.
        assert len(rt.oms.orders()) == 2
        assert rt.oms.orders()[1].status.value == "REJECTED"

        # Reconciliation resolves from venue truth — never an inferred
        # failure — and the OMS order resumes its lifecycle.
        report = venue.resolve_ambiguity("corr-b5-u-resolve")
        assert report.ok
        order = rt.oms.order(unknown_orders[0].order_id)
        venue_order = _venue_orders(venue)[order.order_id]
        assert order.status.value in ("SUBMITTED", "ACKNOWLEDGED",
                                      "PARTIALLY_FILLED")
        assert [f.fill_id for f in order.fills] == \
            [f.fill_id for f in venue_order.fills]
        assert rt.state is RuntimeState.RUNNING
        assert not venue.session.degraded

        # Fills continue on subsequent bars; no double application.
        fills_before = len(order.fills)
        for b in bars[25:32]:
            rt.process_bar(b)
        order = rt.oms.order(order.order_id)
        venue_order = _venue_orders(venue)[order.order_id]
        assert order.status.value == "FILLED"
        assert len(order.fills) > fills_before
        assert len(order.fills) == len(venue_order.fills)
        assert order.filled_quantity == order.quantity

    def test_timeout_exhaustion_adopts_venue_truth(self, tmp_path):
        """Retry exhaustion on a TIMEOUT is ambiguous: the OMS order
        goes UNKNOWN + RECONCILING, bars stop, and recovery adopts the
        venue's truth explicitly (cross-checked against the OMS order
        parameters, re-adopted through the guarded pipeline — never a
        blind failure inference) before the runtime resumes."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-timeout", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(
            rt, tmp_path,
            adapter_factory=_adapter_wrapper(_TimesOutUntilAdopted))

        created, _ = _submit_entry(rt, "corr-b5-t", bars[24], 24)
        assert not created
        assert any(o.status.value in ("UNKNOWN", "RECONCILING")
                   for o in rt.oms.orders())
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN

        report = venue.resolve_ambiguity("corr-b5-t-resolve")
        assert report.ok
        # The venue DID hold the order: its truth was adopted (ledgered
        # VENUE_SYNC), the OMS order resolved, the runtime resumed.
        resolved = list(rt.oms.orders())
        assert all(o.status.value not in ("UNKNOWN", "RECONCILING")
                   for o in resolved)
        assert resolved[0].status.value == "SUBMITTED"
        assert rt.state is RuntimeState.RUNNING
        syncs = [r for r in venue.session.journal_records()
                 if r.entry_type == "VENUE_SYNC"
                 and r.client_order_id == resolved[0].order_id]
        assert syncs, "accept-venue-truth must be ledgered"
        adoptions = [e for e in rt.ledgers.events(ledger="incident")
                     if e.event_type == "VENUE_PHANTOM_ADOPTED"]
        assert adoptions, "the lost-ack adoption must be ledgered"

    def test_unexplainable_phantom_stays_blocked(self, tmp_path):
        """A phantom the runtime CANNOT explain (no OMS order, foreign
        parameters) is never adopted: reconciliation stays failed, the
        runtime is flagged EXECUTION_UNCERTAIN, new submissions are
        blocked — operator attention is the only exit (fail closed)."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-foreign-phantom", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        foreign = OrderRequest(
            client_order_id="coi-foreign-b5", account_id=ACCOUNT,
            symbol=SYMBOL, side=Side.BUY, order_kind=OrderKind.MARKET,
            quantity=Decimal("5"), price=None, stop_price=None,
            time_in_force=TimeInForce.GTC, stop_loss=None,
            take_profit=None, reduce_only=False,
        )
        venue.adapter._orders["coi-foreign-b5"] = _VenueOrder(
            request=foreign, venue_order_id="rtpv-foreign-b5",
            submitted_at=bars[24]["timestamp"],
            execution_anchor=bars[24]["timestamp"],
        )
        report = venue.resolve_ambiguity("corr-b5-fp-resolve")
        assert not report.ok
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        assert "coi-foreign-b5" not in {
            a.client_order_id for a in _journal_acks(venue)}
        blocked, failed = _submit_entry(rt, "corr-b5-fp", bars[24], 24)
        assert not blocked
        assert failed


# ----------------------------------------------------------------------
# 4. Restart recovery + idempotency
# ----------------------------------------------------------------------
class TestRestartRecovery:

    def _venue_session(self, session, root, ens_cal, bars_n=40):
        """Run a venue-attached session with two organic submissions,
        split across ``bars_n`` bars."""
        rt = _mk_runtime(session, root / "state", ens_cal=ens_cal)
        bars = _bars(60)
        for b in bars[:25]:
            rt.process_bar(b)
        venue = _attach(rt, root)
        _submit_entry(rt, f"corr-{session}-24", bars[24], 24)
        for b in bars[25:30]:
            rt.process_bar(b)
        _submit_entry(rt, f"corr-{session}-29", bars[29], 29)
        for b in bars[30:bars_n]:
            rt.process_bar(b)
        return rt, venue, bars

    def test_restart_is_idempotent_and_deterministic(self, tmp_path):
        """Split run == whole run: a restart mid-session rebuilds the
        venue book deterministically, never re-submits an existing
        client_order_id, and the final OMS/position/fill state is
        IDENTICAL to the internal-mode control run."""
        ens_cal = _fit_world()
        bars = _bars(60)

        # Control: internal path, identical session id + plan ids.
        ctl = _mk_runtime("b5-rst", tmp_path / "ctl", ens_cal=ens_cal)
        for b in bars[:25]:
            ctl.process_bar(b)
        _submit_entry(ctl, "corr-b5-rst-24", bars[24], 24)
        for b in bars[25:30]:
            ctl.process_bar(b)
        _submit_entry(ctl, "corr-b5-rst-29", bars[29], 29)
        for b in bars[30:60]:
            ctl.process_bar(b)

        # Venue run split by a restart at bar 40.
        rt1, venue1, _ = self._venue_session(
            "b5-rst", tmp_path / "run", ens_cal, bars_n=40)
        pre_orders = [o.order_id for o in rt1.oms.orders()]
        pre_ack_count = len(_journal_acks(venue1))

        # Restart: same state store, same journal path.
        rt2 = _mk_runtime("b5-rst", tmp_path / "run" / "state",
                          ens_cal=ens_cal)
        assert rt2.restarted
        venue2 = _attach(rt2, tmp_path / "run")
        # No duplicate submissions: the ack set is unchanged.
        assert len(_journal_acks(venue2)) == pre_ack_count
        # The venue book was rebuilt with the SAME fills.
        for cid in pre_orders:
            restored = rt2.oms.order(cid)
            assert [f.fill_id for f in restored.fills] == \
                [f.fill_id for f in rt1.oms.order(cid).fills]
            vorder = _venue_orders(venue2).get(cid)
            assert vorder is not None
            assert [f.fill_id for f in vorder.fills] == \
                [f.fill_id for f in restored.fills]

        # Continue to bar 60 — the split run equals the whole run.
        for b in bars[40:60]:
            rt2.process_bar(b)

        def _signature(rt):
            return [
                (o.order_id, o.status.value,
                 [(f.fill_id, str(f.quantity), str(f.price))
                  for f in o.fills])
                for o in rt.oms.orders()
            ], str(rt._positions.get(SYMBOL, PositionState(
                symbol=SYMBOL)).realized_pnl)

        assert _signature(rt2) == _signature(ctl)
        # A re-submission of the SAME intent is idempotent (no new
        # venue submission, no new order).
        ack_count = len(_journal_acks(venue2))
        created, _ = _submit_entry(rt2, "corr-b5-rst-24", bars[59], 59)
        assert not created
        assert len(_journal_acks(venue2)) == ack_count

    def test_key_reuse_with_different_details_refused(self, tmp_path):
        """Reusing an existing client_order_id is ALWAYS refused —
        never silently replaced. For an authoritative-tracked order the
        identity-bound risk gate refuses first (a diverging request
        fails the fingerprint binding; an identical request fails the
        state binding because the order is past RISK_APPROVED) — a
        TIGHTER refusal point than the journal's
        IDEMPOTENCY_KEY_REUSE, which remains the backstop."""
        ens_cal = _fit_world()
        rt, venue, bars = self._venue_session(
            "b5-reuse", tmp_path / "run", ens_cal, bars_n=28)
        live = list(rt.oms.orders())
        assert live
        cid = live[0].order_id
        original = rt.oms.order(cid)

        # Different details (quantity): the fingerprint binding refuses.
        diverging = OrderRequest(
            client_order_id=cid, account_id=ACCOUNT,
            symbol=original.symbol,
            side=Side.BUY if original.side == "BUY" else Side.SELL,
            order_kind=(
                OrderKind.MARKET if original.order_type == "MARKET"
                else OrderKind.LIMIT),
            quantity=original.quantity / Decimal("2"),
            price=original.limit_price,
            stop_price=None, time_in_force=TimeInForce.GTC,
            stop_loss=None, take_profit=None, reduce_only=False,
        )
        with pytest.raises(OrderRefusedError) as excinfo:
            venue.session.submit_order(diverging)
        assert excinfo.value.reason_code == "RISK_REFUSED"

        # Identical details: the state binding still refuses (the order
        # is past RISK_APPROVED; only governed transitions may touch
        # it — never a re-submission).
        identical = diverging.model_copy(
            update={"quantity": original.quantity})
        with pytest.raises(OrderRefusedError) as excinfo2:
            venue.session.submit_order(identical)
        assert excinfo2.value.reason_code == "RISK_REFUSED"
        # The journal never grew a second ack for the reused identity.
        acks = [a for a in _journal_acks(venue)
                if a.client_order_id == cid]
        assert len(acks) == 1

    def test_restart_inside_unknown_stays_blocked(self, tmp_path):
        """A restart while a submission is ambiguous stays FAIL-CLOSED:
        the journal's UNKNOWN record degrades the session, the runtime
        refuses bars, and nothing infers an outcome."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-rst-unk", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path,
                        adapter_factory=_adapter_wrapper(_UnknownOnce))
        _submit_entry(rt, "corr-b5-ru", bars[24], 24)
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        unknown = [o for o in rt.oms.orders()
                   if o.status.value in ("UNKNOWN", "RECONCILING")]
        assert unknown
        # The ambiguous submission is part of the persisted session
        # state (inside a real bar this happens at the bar's own
        # persistence step; the direct-path harness persists here).
        rt._persist_safe("corr-b5-ru")

        rt2 = _mk_runtime("b5-rst-unk", tmp_path / "state",
                          ens_cal=ens_cal)
        venue2 = _attach(rt2, tmp_path,
                         adapter_factory=_adapter_wrapper(_UnknownOnce))
        assert venue2.session.degraded
        assert rt2.state is RuntimeState.EXECUTION_UNCERTAIN
        outcome = rt2.process_bar(bars[25])
        assert not outcome.accepted
        # The ambiguous order was NOT fabricated into the venue book.
        assert unknown[0].order_id not in _venue_orders(venue2)

    def test_recovered_halt_is_not_silently_running(self, tmp_path):
        """A terminally HALTED runtime stays HALTED through venue
        recovery — attaching a venue NEVER resurrects trading."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-rst-halt", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        _attach(rt, tmp_path)
        rt.halt("batch5 terminal halt fixture")
        assert rt.state is RuntimeState.HALTED

        rt2 = _mk_runtime("b5-rst-halt", tmp_path / "state",
                          ens_cal=ens_cal)
        assert rt2.state is RuntimeState.HALTED
        _attach(rt2, tmp_path)
        assert rt2.state is RuntimeState.HALTED
        outcome = rt2.process_bar(bars[25])
        assert not outcome.accepted
        created, _ = _submit_entry(rt2, "corr-b5-rh2", bars[24], 24)
        assert not created

    def test_live_non_venue_orders_refuse_attach(self, tmp_path):
        """A runtime with LIVE orders that never went through the
        venue (pre-venue submissions) refuses venue attachment — there
        is no hidden direct-execution fallback and no silent
        migration of in-flight internal orders."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-pre-venue", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        created, _ = _submit_entry(rt, "corr-b5-pv", bars[24], 24)
        assert created
        with pytest.raises(BridgeContractError):
            _attach(rt, tmp_path)


# ----------------------------------------------------------------------
# 5. Accounting + isolation
# ----------------------------------------------------------------------
class TestAccountingAndIsolation:

    def test_partial_fills_accounted_exactly_once(self, tmp_path):
        """Genuine multi-bar partial fills: venue fill count == OMS
        fill count == metrics, positions/ledgers single-applied, and a
        redundant poll is a no-op (structural exactly-once)."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-partial", tmp_path / "state",
                         ens_cal=ens_cal, realism=_partial_realism())
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)

        # qty 100 vs the participation cap (0.01 * 5000 = 50/bar):
        # a genuine MULTI-BAR partial-fill sequence.
        created, _ = _submit_entry(rt, "corr-b5-p", bars[24], 24,
                                   qty=Decimal("100"))
        oid = created[0].order_id
        for b in bars[25:40]:
            rt.process_bar(b)
        order = rt.oms.order(oid)
        assert order.status.value == "FILLED"
        n_fills = len(order.fills)
        assert n_fills >= 2, "fixture must produce multi-bar partials"

        vorder = _venue_orders(venue)[oid]
        assert len(vorder.fills) == n_fills
        assert rt._metrics._counters["fills"] == n_fills
        fill_events = [e for e in rt.ledgers.events(ledger="fill")
                       if e.payload.get("order_id") == oid]
        assert len(fill_events) == n_fills
        # Redundant poll: no new fills, no double application.
        assert venue.poll_order(rt.oms.order(oid), "corr-b5-p2") == []
        assert len(rt.oms.order(oid).fills) == n_fills

    def test_no_credential_material_anywhere(self, tmp_path):
        """The credential secret never reaches the runtime ledgers,
        the persisted execution state, the OMS records or the venue
        journal."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-secret", tmp_path / "state",
                         ens_cal=ens_cal)
        bars = _seeded(rt, 25)
        venue = _attach(rt, tmp_path)
        _submit_entry(rt, "corr-b5-s", bars[24], 24)
        for b in bars[25:30]:
            rt.process_bar(b)

        candidates = []
        for name in ("prediction", "decision", "trade_plan", "order",
                     "fill", "position", "trade", "pnl", "incident"):
            for event in rt.ledgers.events(ledger=name):
                candidates.append(str(event.payload))
        for order in rt.oms.orders():
            candidates.append(str(order.model_dump(mode="json")))
        for record in venue.session.journal_records():
            candidates.append(str(record.model_dump(mode="json")))
        for path in (tmp_path / "state").rglob("*"):
            if path.is_file():
                candidates.append(path.read_text())
        candidates.append(Path(tmp_path / "venue.json").read_text())
        assert find_secret_leak(candidates, [SECRET]) == []

    def test_drawdown_enforcement_through_the_venue(self, tmp_path):
        """RUN-DD-1 semantics are unchanged through the venue: an
        account drawdown breach trips the ACCOUNT kill switch and
        HALTS the session terminally (no new venue exposure)."""
        from test_runtime_account_drawdown import (
            _dd_config,
            _seed_round_trip_loss,
        )
        ens_cal = _fit_world()
        rt = TradingRuntime(
            _dd_config("b5-dd", 0.0005), ens_cal[0], calibrator=ens_cal[1],
        )
        rt.start()
        bars = _seeded(rt, 25)
        _attach(rt, tmp_path)
        _seed_round_trip_loss(rt, bars)
        rt.process_bar(bars[25])
        assert rt.state is RuntimeState.HALTED
        assert rt.kill_switch.is_active(KillSwitchScope.ACCOUNT)
        # No new orders can be submitted through the venue.
        created, _ = _submit_entry(rt, "corr-b5-dd2", bars[25], 25)
        assert not created


# ----------------------------------------------------------------------
# 6. Preservation pins
# ----------------------------------------------------------------------
class TestPreservationPins:

    def test_runtime_without_venue_is_untouched(self, tmp_path):
        """The default runtime has no venue seam active — the entire
        pre-existing suite is that proof; this pins the default."""
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-novenue", tmp_path / "state",
                         ens_cal=ens_cal)
        assert rt.venue is None

    def test_venue_execution_mode_is_paper_mock_only(self, tmp_path):
        ens_cal = _fit_world()
        rt = _mk_runtime("b5-mode", tmp_path / "state", ens_cal=ens_cal)
        _seeded(rt, 25)
        venue = _attach(rt, tmp_path)
        assert venue.session.capabilities.execution_mode is \
            ExecutionMode.MOCK_DETERMINISTIC
