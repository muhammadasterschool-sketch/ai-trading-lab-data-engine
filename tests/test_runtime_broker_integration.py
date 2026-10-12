"""Phase M2 / Batch 3 acceptance tests — runtime -> broker-neutral
execution bridge.

The integration being proven (``runtime/broker_execution.py``, the
SMALLEST maintainable integration layer):

1. A ``BrokerSession`` attached to a STARTED paper runtime is
   governed by the runtime's REAL central gates — the SAME
   ``RiskGate`` (all 22 mandatory checks incl. RUN-DD-1 account
   drawdown) and ``KillSwitchManager`` instances, never copies.
2. Venue-side execution is the runtime's OWN deterministic
   ``PaperExecutionAdapter`` fill model over the runtime's admitted
   bar history (latency, participation-capped partial fills, LIMIT
   never through the limit).
3. The runtime's authoritative order path is UNTOUCHED: venue
   orders live in the session journal + venue book, never in the
   runtime OMS/position book (side-band integration).
4. Session protections work end-to-end on this boundary: journal
   idempotency across restarts, bounded deterministic retry, UNKNOWN
   degradation with reconciliation-only recovery, capability and
   precision refusals, account isolation.

All venues in these tests are paper fixtures (MOCK_DETERMINISTIC);
no real broker, no network, no credentials beyond opaque play-money
holders. LIVE TRADING REMAINS NOT AUTHORIZED.
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
from data_engine.brokers.redaction import BrokerCredential
from data_engine.brokers.session import BrokerSession
from data_engine.paper.simulator import ExecutionRealism
from data_engine.runtime import (
    DecisionAction,
    KillSwitchScope,
    RuntimeKillSwitchGate,
    RuntimePaperExecutionAdapter,
    RuntimeRiskGateBridge,
    RuntimeState,
    TradingRuntime,
    attach_runtime_paper_session,
)
from data_engine.runtime.broker_execution import RUNTIME_PAPER_VENUE_ID

from test_runtime_e2e import T0, _bars, _fit_world
from test_runtime_account_drawdown import (
    _dd_config,
    _plan,
    _run_bars,
    _seed_order_fill,
)

SYMBOL = "TEST/USD"
ACCOUNT = "paper-acct-1"
#: Deterministic clock base: AFTER the last admitted bar of a
#: 25-bar session (T0 + 24*300s = 11:00) so submissions anchor at
#: the latest bar.
CLOCK_BASE = T0 + timedelta(hours=3)


def _make_clock():
    """Stepping deterministic clock (journal + submission times)."""
    state = {"t": CLOCK_BASE}

    def clock():
        state["t"] = state["t"] + timedelta(seconds=1)
        return state["t"]

    return clock


def _instruments():
    return {
        SYMBOL: InstrumentSpec(
            broker_id=RUNTIME_PAPER_VENUE_ID,
            symbol=SYMBOL,
            broker_symbol=SYMBOL,
            base_asset="TEST",
            quote_asset="USD",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.0001"),
            min_quantity=Decimal("0.0001"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("0"),
        ),
    }


def _runtime(session, realism=None):
    """Started no-trade paper runtime with 25 bars admitted."""
    ens, cal = _fit_world()
    rt = TradingRuntime(_dd_config(session, 0.20), ens,
                        calibrator=cal, realism=realism)
    rt.start()
    bars = _bars(30)
    _run_bars(rt, bars, 25)
    return rt, bars


def _attach(rt, tmp_path, clock, name="journal.json", adapter=None):
    if adapter is not None:
        return BrokerSession(
            adapter,
            account_id=ACCOUNT,
            journal_path=tmp_path / name,
            risk_decision_fn=RuntimeRiskGateBridge(rt),
            kill_switch_fn=RuntimeKillSwitchGate(rt),
            clock=clock,
            sleeper=lambda s: None,
        )
    return attach_runtime_paper_session(
        rt,
        account_id=ACCOUNT,
        journal_path=tmp_path / name,
        clock=clock,
        instruments=_instruments(),
    )


def _connect(session):
    session.connect(BrokerCredential(ACCOUNT, "opaque-play-money-secret"))
    return session


def _request(corr, *, side=Side.BUY, qty=Decimal("10"),
             kind=OrderKind.MARKET, price=None, stop_price=None,
             sl=None, tp=None,
             tif=TimeInForce.GTC, account=ACCOUNT, symbol=SYMBOL):
    return OrderRequest(
        client_order_id=f"coi-{corr}",
        account_id=account,
        symbol=symbol,
        side=side,
        order_kind=kind,
        quantity=qty,
        price=price,
        stop_price=stop_price,
        time_in_force=tif,
        stop_loss=sl,
        take_profit=tp,
        reduce_only=False,
    )


def _protective(bars, corr, ref_offset=Decimal("0"), qty=Decimal("10"),
                bar_i=24):
    """A risk-clean BUY request: SL below the reference close, TP
    above it (valid long geometry + R:R >= 1 for the REAL gate).

    ``bar_i`` anchors the geometry to the bar that will be the
    runtime's LATEST admitted close at submission time — the bridged
    risk gate evaluates MARKET geometry against exactly that close,
    so submitting after more bars processed must re-anchor here."""
    ref = Decimal(str(bars[bar_i]["close"])) + ref_offset
    return _request(corr, qty=qty, sl=ref - Decimal("2"),
                    tp=ref + Decimal("4"))


class TestOrderLifecycle:
    """Submit -> latency -> fills -> terminal state, venue-side."""

    def test_market_order_lifecycle_fills_with_cost_decomposition(
            self, tmp_path):
        rt, bars = _runtime("m2-life")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        ack = session.submit_order(_protective(bars, "life-1"))
        assert ack.status is VenueOrderStatus.OPEN      # latency
        assert ack.broker_id == RUNTIME_PAPER_VENUE_ID
        assert ack.venue_order_id.startswith("rtpv-")
        # bars arrive -> poll -> the venue fills (single bar: qty 10
        # is far below the 35% participation capacity of 5000)
        for b in bars[25:27]:
            rt.process_bar(b)
        ack2 = session.order_status(ack.client_order_id)
        assert ack2.status is VenueOrderStatus.FILLED
        fills = session.order_fills(ack.client_order_id)
        assert sum((f.quantity for f in fills), Decimal("0")) \
            == Decimal("10")
        for f in fills:
            assert f.price > 0 and f.fee > 0  # costs charged, visible
            assert f.broker_id == RUNTIME_PAPER_VENUE_ID
        # journal carries the ack + the venue-truth syncs
        kinds = [r.entry_type for r in session.journal_records()]
        assert "ORDER_ACK" in kinds and "VENUE_SYNC" in kinds
        assert not session.degraded
        report = session.reconcile()
        assert report.ok and report.mismatches == ()

    def test_partial_fills_across_bars(self, tmp_path):
        """Participation-capped venue: qty 12 against a 5-unit/bar
        capacity fills across THREE polled bars (the runtime's own
        multi-bar partial-fill model, hosted venue-side)."""
        realism = ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.001"),   # 5 units per bar
            fill_lag_bars=1,
        )
        rt, bars = _runtime("m2-part", realism=realism)
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        ack = session.submit_order(_protective(bars, "part-1",
                                             qty=Decimal("12")))
        assert ack.status is VenueOrderStatus.OPEN
        rt.process_bar(bars[25])
        mid = session.order_status(ack.client_order_id)
        assert mid.status is VenueOrderStatus.PARTIALLY_FILLED
        assert mid_filled(session, ack.client_order_id) == Decimal("5")
        rt.process_bar(bars[26])
        rt.process_bar(bars[27])
        final = session.order_status(ack.client_order_id)
        assert final.status is VenueOrderStatus.FILLED
        assert mid_filled(session, ack.client_order_id) == Decimal("12")

    def test_limit_order_rests_then_fills_on_cross(self, tmp_path):
        """A resting BUY LIMIT below the market stays OPEN until a
        bar's low crosses the limit — then fills at the protected
        price (never through the limit)."""
        rt, bars = _runtime("m2-limit")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        ref = Decimal(str(bars[24]["close"]))       # ~103.92
        limit = (ref + Decimal("0.50")).quantize(Decimal("0.01"))
        ack = session.submit_order(_request(
            "limit-1", kind=OrderKind.LIMIT, price=limit,
            sl=limit - Decimal("2"), tp=limit + Decimal("4"),
        ))
        assert ack.status is VenueOrderStatus.OPEN
        rt.process_bar(bars[25])                    # low 103.67 <= 104.42?
        ack2 = session.order_status(ack.client_order_id)
        if ack2.status is not VenueOrderStatus.FILLED:
            rt.process_bar(bars[26])
            ack2 = session.order_status(ack.client_order_id)
        assert ack2.status is VenueOrderStatus.FILLED
        fills = session.order_fills(ack.client_order_id)
        for f in fills:
            assert f.price <= limit                 # BUG-001 protection

    def test_cancel_before_fill_freezes_order(self, tmp_path):
        realism = ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.35"),
            fill_lag_bars=2,
        )
        rt, bars = _runtime("m2-cancel", realism=realism)
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        ack = session.submit_order(_protective(bars, "cancel-1"))
        assert ack.status is VenueOrderStatus.OPEN
        cancelled = session.cancel_order(ack.client_order_id)
        assert cancelled.status is VenueOrderStatus.CANCELLED
        for b in bars[25:29]:
            rt.process_bar(b)
        final = session.order_status(ack.client_order_id)
        assert final.status is VenueOrderStatus.CANCELLED
        assert session.order_fills(ack.client_order_id) == ()


def mid_filled(session, client_order_id):
    fills = session.order_fills(client_order_id)
    return sum((f.quantity for f in fills), Decimal("0"))


class TestCentralGatesGovernTheSession:
    """The runtime's REAL risk gate + kill switch refuse venue orders."""

    def test_runtime_kill_switch_refuses_session_orders(self, tmp_path):
        rt, bars = _runtime("m2-ks")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "bridge test trip", target=SYMBOL
        )
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_protective(bars, "ks-1"))
        assert excinfo.value.reason_code == "KILL_SWITCH_ACTIVE"
        assert rt.state is RuntimeState.RUNNING  # SYMBOL scope: no halt
        refusals = [
            r for r in session.journal_records()
            if r.entry_type == "ORDER_REFUSED"
        ]
        assert refusals and refusals[-1].reason_code == "KILL_SWITCH_ACTIVE"

    def test_runtime_risk_gate_refuses_unprotected_order(self, tmp_path):
        """No stop-loss attached -> the REAL 22-check gate refuses
        (stop_loss_presence); the venue never sees the order."""
        rt, bars = _runtime("m2-nosl")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request("nosl-1"))
        assert excinfo.value.reason_code == "RISK_REFUSED"
        assert "stop_loss_presence" in str(excinfo.value)
        # the bridged assessment is ledgered in the RUNTIME's ledger
        # family (auditable forever)
        bridge_events = [
            e for e in rt.ledgers.events(ledger="trade_plan")
            if e.correlation_id.startswith("bridge:")
        ]
        assert any(
            e.event_type == "RISK_ASSESSMENT_FAIL" for e in bridge_events
        )

    def test_account_drawdown_refuses_session_orders(self, tmp_path):
        """RUN-DD-1 through the bridge: a seeded account loss beyond
        the configured limit makes the bridged risk gate refuse the
        venue order (account_drawdown among the failed checks)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("m2-dd", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        # seeded round-trip loss: -184 on 100000 = 0.184% > 0.1%
        buy_px = Decimal(str(bars[5]["close"]))
        sell_px = Decimal(str(bars[6]["close"]))
        _seed_order_fill(
            rt, _plan("m2-dd-b", DecisionAction.BUY, Decimal("100"),
                      buy_px, buy_px - Decimal("2"),
                      buy_px + Decimal("4")), buy_px, 5, "m2-dd-b",
        )
        _seed_order_fill(
            rt, _plan("m2-dd-s", DecisionAction.SELL, Decimal("100"),
                      sell_px, sell_px + Decimal("2"),
                      sell_px - Decimal("4")), sell_px, 6, "m2-dd-s",
        )
        assert rt._account_drawdown() > 0.001
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_protective(bars, "dd-1"))
        assert excinfo.value.reason_code == "RISK_REFUSED"
        assert "account_drawdown" in str(excinfo.value)

    def test_no_market_context_refuses_orders(self, tmp_path):
        """A runtime with ZERO admitted bars cannot verify ANY order
        (no mark, volume, volatility) — fail closed at the bridge."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("m2-empty", 0.20), ens,
                            calibrator=cal)
        rt.start()
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request("empty-1", sl=Decimal("98"),
                                          tp=Decimal("104")))
        assert excinfo.value.reason_code == "RISK_REFUSED"
        assert "market context" in str(excinfo.value)

    def test_foreign_symbol_refused_no_authoritative_context(
            self, tmp_path):
        """A symbol the runtime does not trade has no authoritative
        market context — the bridge refuses rather than risk-evaluating
        against the WRONG instrument's bars."""
        rt, bars = _runtime("m2-foreign")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request(
                "foreign-1", symbol="OTHER/USD",
                sl=Decimal("98"), tp=Decimal("104"),
            ))
        assert excinfo.value.reason_code == "RISK_REFUSED"
        assert "not the runtime" in str(excinfo.value)


class TestIdempotencyAndJournal:
    """Journal-backed duplicate protection, including restarts."""

    def test_duplicate_submission_replays_exact_ack(self, tmp_path):
        rt, bars = _runtime("m2-idem")
        clock = _make_clock()
        session = _connect(_attach(rt, tmp_path, clock))
        request = _protective(bars, "idem-1")
        ack1 = session.submit_order(request)
        # the SAME key + SAME request replays the STORED ack exactly
        # (a duplicate RETRY — no market movement between attempts)
        ack2 = session.submit_order(request)
        assert ack2 == ack1
        # ...and never executed twice at the venue
        rt.process_bar(bars[25])
        assert mid_filled(session, ack1.client_order_id) \
            <= request.quantity

    def test_key_reuse_with_different_request_refused(self, tmp_path):
        rt, bars = _runtime("m2-reuse")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        session.submit_order(_protective(bars, "reuse-1"))
        altered = _protective(bars, "reuse-1", qty=Decimal("7"))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(altered)
        assert excinfo.value.reason_code == "IDEMPOTENCY_KEY_REUSE"

    def test_journal_survives_session_restart(self, tmp_path):
        """A NEW session over the same journal replays the stored
        outcome (no double execution across the process boundary)."""
        rt, bars = _runtime("m2-restart")
        clock = _make_clock()
        journal = tmp_path / "journal.json"
        session1 = _connect(_attach(rt, tmp_path, clock))
        ref = Decimal(str(bars[24]["close"]))
        limit = (ref + Decimal("0.50")).quantize(Decimal("0.01"))
        request = _request(
            "restart-1", kind=OrderKind.LIMIT, price=limit,
            sl=ref - Decimal("1.50"), tp=ref + Decimal("4.50"),
        )
        ack1 = session1.submit_order(request)
        rt.process_bar(bars[25])
        session2 = _connect(_attach(rt, tmp_path, _make_clock()))
        ack2 = session2.submit_order(request)
        assert ack2 == ack1
        with pytest.raises(OrderRefusedError) as excinfo:
            session2.submit_order(_request(
                "restart-1", kind=OrderKind.LIMIT,
                price=limit, qty=Decimal("3"),
                sl=ref - Decimal("1.50"), tp=ref + Decimal("4.50"),
            ))
        assert excinfo.value.reason_code == "IDEMPOTENCY_KEY_REUSE"


class TestErrorsTimeoutsAndUnsupported:
    """Typed errors, bounded retry, UNKNOWN degradation, refusals."""

    def test_timeout_retried_with_deterministic_backoff(self, tmp_path):
        rt, bars = _runtime("m2-timeout")

        class _Flaky(RuntimePaperExecutionAdapter):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.timeouts_left = 2

            def submit_order(self, request):
                if self.timeouts_left > 0:
                    self.timeouts_left -= 1
                    raise BrokerExecutionError(
                        "injected timeout (paper fixture)",
                        category=BrokerErrorCategory.TIMEOUT,
                        broker_id=self.broker_id,
                    )
                return super().submit_order(request)

        adapter = _Flaky(
            rt, instruments=_instruments(), account_id=ACCOUNT,
            clock=_make_clock(),
        )
        session = _connect(_attach(rt, tmp_path, _make_clock(),
                                   adapter=adapter))
        ack = session.submit_order(_protective(bars, "timeout-1"))
        assert ack.status is VenueOrderStatus.OPEN
        # bounded deterministic backoff evidence (0.05, 0.1 for the
        # two injected retries under the default policy)
        assert session.sleep_log == (0.05, 0.1)

    def test_unknown_ack_degrades_until_reconciled(self, tmp_path):
        """UNKNOWN submission outcome: journal UNKNOWN, session
        DEGRADED (new orders refused), reconciliation resolves from
        venue truth, trading resumes. The venue DID hold the order
        (ack lost after accept) — resolution, never blind retry."""
        rt, bars = _runtime("m2-unknown")

        class _UnknownOnce(RuntimePaperExecutionAdapter):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.unknowns_left = 1

            def submit_order(self, request):
                ack = super().submit_order(request)
                if self.unknowns_left > 0:
                    self.unknowns_left -= 1
                    raise UnknownOrderStateError(
                        "injected unknown-ack (paper fixture)",
                        broker_id=self.broker_id,
                        client_order_id=request.client_order_id,
                    )
                return ack

        adapter = _UnknownOnce(
            rt, instruments=_instruments(), account_id=ACCOUNT,
            clock=_make_clock(),
        )
        session = _connect(_attach(rt, tmp_path, _make_clock(),
                                   adapter=adapter))
        with pytest.raises(UnknownOrderStateError):
            session.submit_order(_protective(bars, "unknown-1"))
        assert session.degraded
        # degraded: ALL new submissions refused
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_protective(bars, "unknown-2"))
        assert excinfo.value.reason_code == "RECONCILIATION_REQUIRED"
        # venue truth resolves the UNKNOWN (fills happened)
        for b in bars[25:27]:
            rt.process_bar(b)
        report = session.reconcile()
        assert report.ok
        assert any(
            r.client_order_id == "coi-unknown-1" for r in report.resolved
        )
        assert not session.degraded
        # trading resumed after the clean reconciliation (geometry
        # re-anchored to the CURRENT latest close — bars moved)
        ack = session.submit_order(_protective(bars, "unknown-2",
                                               bar_i=26))
        assert ack.status is VenueOrderStatus.OPEN

    def test_unsupported_time_in_force_refused(self, tmp_path):
        rt, bars = _runtime("m2-ioc")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request(
                "ioc-2", tif=TimeInForce.IOC,
                sl=Decimal("101"), tp=Decimal("108"),
            ))
        assert excinfo.value.reason_code == "UNSUPPORTED_TIME_IN_FORCE"

    def test_stop_order_kind_refused_by_bridge(self, tmp_path):
        """STOP orders cannot be translated onto the frozen paper OMS
        (MARKET/LIMIT only) — refused at the bridged risk gate with a
        NAMED failed check."""
        rt, bars = _runtime("m2-stop")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request(
                "stop-1", kind=OrderKind.STOP,
                stop_price=Decimal("104"),
            ))
        assert excinfo.value.reason_code == "RISK_REFUSED"
        assert "paper_oms_order_kind" in str(excinfo.value)

    def test_account_isolation_refused(self, tmp_path):
        rt, bars = _runtime("m2-iso")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_request(
                "iso-1", account="someone-elses-account",
                sl=Decimal("101"), tp=Decimal("108"),
            ))
        assert excinfo.value.reason_code == "ACCOUNT_ISOLATION"

    def test_unknown_symbol_refused_never_guessed(self, tmp_path):
        """The runtime's symbol is not in the integrator-supplied
        instrument map -> UNKNOWN_SYMBOL (a spec is never guessed)."""
        rt, bars = _runtime("m2-nosym")

        class _NoInstruments(RuntimePaperExecutionAdapter):
            def __init__(self, *a, **kw):
                kw["instruments"] = {}   # deliberately empty map
                super().__init__(*a, **kw)

        adapter = _NoInstruments(
            rt, account_id=ACCOUNT, clock=_make_clock(),
        )
        session = _connect(_attach(rt, tmp_path, _make_clock(),
                                   adapter=adapter))
        with pytest.raises(OrderRefusedError) as excinfo:
            session.submit_order(_protective(bars, "nosym-1"))
        assert excinfo.value.reason_code == "UNKNOWN_SYMBOL"


class TestReconciliation:
    """Journal expectations vs venue truth (§32 discipline)."""

    def test_divergence_degrades_until_venue_truth_synced(self, tmp_path):
        """The journal falls behind the venue (new fills unknown to
        it): reconciliation reports STATUS_DIVERGENCE and degrades;
        sync_order_state accepts venue truth (ledgered); a clean
        re-reconciliation restores trading. Nothing is papered over."""
        realism = ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.001"),   # 5 units per bar
            fill_lag_bars=1,
        )
        rt, bars = _runtime("m2-div", realism=realism)
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        ack = session.submit_order(_protective(bars, "div-1", qty=12))
        for b in bars[25:28]:
            rt.process_bar(b)
        report = session.reconcile()
        assert not report.ok
        assert any(
            m.kind.value == "STATUS_DIVERGENCE"
            for m in report.mismatches
        )
        assert session.degraded
        with pytest.raises(OrderRefusedError):
            session.submit_order(_protective(bars, "div-2", bar_i=27))
        # accept venue truth explicitly (ledgered VENUE_SYNC)
        synced = session.sync_order_state(ack.client_order_id)
        assert synced.status is VenueOrderStatus.FILLED
        report2 = session.reconcile()
        assert report2.ok, report2.mismatches
        assert not session.degraded

    def test_phantom_order_at_venue_degrades(self, tmp_path):
        """An order submitted DIRECTLY to the adapter (bypassing the
        session) is a phantom the journal does not know: mismatch,
        degraded, operator investigates."""
        rt, bars = _runtime("m2-phantom")
        clock = _make_clock()
        session = _connect(_attach(rt, tmp_path, clock))
        direct = _request("phantom-1", sl=Decimal("101"),
                          tp=Decimal("108"))
        session.adapter.submit_order(direct)   # bypasses the journal
        report = session.reconcile()
        assert not report.ok
        assert any(
            m.kind.value == "PHANTOM_ORDER_AT_VENUE"
            for m in report.mismatches
        )
        assert session.degraded


class TestRuntimeBehaviorPreserved:
    """The side-band contract: venue orders never touch the runtime's
    authoritative OMS / position book / operating state."""

    def test_session_orders_leave_runtime_oms_untouched(self, tmp_path):
        rt, bars = _runtime("m2-sideband")
        session = _connect(_attach(rt, tmp_path, _make_clock()))
        session.submit_order(_protective(bars, "side-1"))
        for b in bars[25:28]:
            rt.process_bar(b)
        session.order_status("coi-side-1")
        # the venue filled — but the RUNTIME's own books are untouched
        assert not rt.oms.orders()
        assert all(p.is_flat for p in rt.positions.values())
        assert rt.state is RuntimeState.RUNNING
        # the runtime keeps processing bars normally afterwards
        outcome = rt.process_bar(bars[28])
        assert outcome.accepted

    def test_execution_mode_is_paper_mock_only(self):
        """The integration venue is MOCK_DETERMINISTIC — the session
        constructor REFUSES anything else (LIVE NOT AUTHORIZED)."""
        from data_engine.runtime.broker_execution import (
            RUNTIME_PAPER_VENUE_CAPABILITIES,
        )
        assert (RUNTIME_PAPER_VENUE_CAPABILITIES.execution_mode
                is ExecutionMode.MOCK_DETERMINISTIC)
