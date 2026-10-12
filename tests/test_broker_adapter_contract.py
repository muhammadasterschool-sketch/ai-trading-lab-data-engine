"""Broker-neutral adapter contract tests (multi-broker mandate,
Phase M1 + Batch 7).

The SAME contract suite runs against ALL five deterministic mock
adapters (paper / MT5-style / Binance-style / Bybit-style /
Bitget-style): whatever the venue, the normalized surface behaves
identically. Venue-specific semantics (hedging tickets, spot
filters, attached-vs-separate stops, native error codes, rate-limit
shapes) get dedicated tests — the capability matrix is executable,
not documentation-only.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from data_engine.brokers import (
    BinanceSpotMockAdapter,
    BitgetSpotMockAdapter,
    BrokerAdapter,
    BrokerCredential,
    BrokerErrorCategory,
    BrokerExecutionError,
    BybitV5MockAdapter,
    ExpectedOrderState,
    MT5StyleMockAdapter,
    OrderKind,
    OrderRequest,
    PaperBrokerAdapter,
    Side,
    TimeInForce,
    VenueOrderStatus,
)
from data_engine.brokers.adapters._mock_core import MockVenueError
from data_engine.brokers.models import AccountMode, ConnectionState

ACCOUNT = "acct-1"
SECRET = "mock-secret-material-DO-NOT-PRINT"

#: Per-venue canonical BTC symbol (MT5-class brokers spell it BTCUSD).
BTC_SYMBOL = {
    "paper-mock": "BTCUSDT",
    "mt5-mock": "BTCUSD",
    "binance-mock": "BTCUSDT",
    "bybit-mock": "BTCUSDT",
    "bitget-mock": "BTCUSDT",
}

#: A MARKET BUY quantity valid at EVERY venue (lot steps, minimums and
#: minimum notionals all satisfied; balances all sufficient).
COMMON_QTY = Decimal("0.02")

FIXED_TS = datetime(2026, 10, 12, 12, 0, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_TS


ADAPTER_FACTORIES = {
    "paper-mock": PaperBrokerAdapter,
    "mt5-mock": MT5StyleMockAdapter,
    "binance-mock": BinanceSpotMockAdapter,
    "bybit-mock": BybitV5MockAdapter,
    "bitget-mock": BitgetSpotMockAdapter,
}


def _make(broker_id: str) -> BrokerAdapter:
    adapter = ADAPTER_FACTORIES[broker_id](fixed_clock)
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter


def _symbol(venue: BrokerAdapter) -> str:
    return BTC_SYMBOL[venue.broker_id]


def _market(venue: BrokerAdapter, client_order_id: str, qty: Decimal = COMMON_QTY,
            **overrides):
    kwargs = dict(
        client_order_id=client_order_id,
        account_id=ACCOUNT,
        symbol=_symbol(venue),
        side=Side.BUY,
        order_kind=OrderKind.MARKET,
        quantity=qty,
    )
    kwargs.update(overrides)
    return OrderRequest(**kwargs)


@pytest.fixture(params=list(ADAPTER_FACTORIES))
def venue(request) -> BrokerAdapter:
    return _make(request.param)


# ---------------------------------------------------------------------------
# Lifecycle, account, instruments
# ---------------------------------------------------------------------------

class TestLifecycleAndAccount:

    def test_connect_binds_the_account(self, venue):
        assert venue.health() is ConnectionState.CONNECTED
        info = venue.account_info()
        assert info.account_id == ACCOUNT
        assert info.broker_id == venue.broker_id
        assert info.account_mode is AccountMode.DEMO  # REAL refused this phase

    def test_disconnect_fails_closed(self, venue):
        venue.disconnect()
        assert venue.health() is ConnectionState.DISCONNECTED
        with pytest.raises(BrokerExecutionError) as exc:
            venue.account_info()
        assert exc.value.category is BrokerErrorCategory.CONNECTIVITY

    def test_instrument_metadata_is_normalized(self, venue):
        spec = venue.instrument_spec(_symbol(venue))
        assert spec.broker_id == venue.broker_id
        assert spec.tick_size > 0 and spec.lot_step > 0
        assert spec.min_quantity > 0

    def test_unknown_symbol_fails_closed(self, venue):
        with pytest.raises(BrokerExecutionError) as exc:
            venue.instrument_spec("NOTASYMBOL")
        assert exc.value.category is BrokerErrorCategory.INVALID_ORDER

    def test_list_symbols_includes_the_btc_instrument(self, venue):
        assert _symbol(venue) in venue.list_symbols()

    def test_connect_requires_credential_holder(self, venue):
        venue.disconnect()
        with pytest.raises(BrokerExecutionError) as exc:
            venue.connect("plain-string-credential")
        assert exc.value.category is BrokerErrorCategory.AUTH

    def test_one_adapter_serves_exactly_one_account(self, venue):
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "iso-1", account_id="OTHER-ACCOUNT"))
        assert exc.value.category is BrokerErrorCategory.AUTH
        assert exc.value.venue_code == "ACCOUNT_ISOLATION_MISMATCH"


# ---------------------------------------------------------------------------
# Order submission, idempotency, fills
# ---------------------------------------------------------------------------

class TestSubmissionContract:

    def test_market_order_fills_immediately(self, venue):
        ack = venue.submit_order(_market(venue, "m-1"))
        assert ack.status is VenueOrderStatus.FILLED
        assert ack.client_order_id == "m-1"
        assert ack.account_id == ACCOUNT
        assert ack.broker_id == venue.broker_id
        fills = venue.order_fills("m-1")
        assert len(fills) == 1
        assert fills[0].quantity == COMMON_QTY
        assert fills[0].price > 0

    def test_limit_order_rests_open(self, venue):
        ack = venue.submit_order(OrderRequest(
            client_order_id="l-1", account_id=ACCOUNT, symbol=_symbol(venue),
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=COMMON_QTY, price=Decimal("48000.00"),
        ))
        assert ack.status is VenueOrderStatus.OPEN
        assert venue.order_fills("l-1") == ()

    def test_duplicate_client_order_id_never_executes_twice(self, venue):
        first = venue.submit_order(_market(venue, "dup-1"))
        balances_after_first = {b.asset: b.free for b in venue.balances()}
        second = venue.submit_order(_market(venue, "dup-1"))
        assert second.venue_order_id == first.venue_order_id
        assert second.status == first.status
        assert venue.executed_orders == 1
        assert venue.submit_attempts == 2
        # Balances moved exactly ONCE (no double execution).
        assert {b.asset: b.free for b in venue.balances()} == balances_after_first

    def test_cancel_open_order_is_idempotent(self, venue):
        venue.submit_order(OrderRequest(
            client_order_id="c-1", account_id=ACCOUNT, symbol=_symbol(venue),
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=COMMON_QTY, price=Decimal("48000.00"),
        ))
        cancelled = venue.cancel_order("c-1")
        assert cancelled.status is VenueOrderStatus.CANCELLED
        again = venue.cancel_order("c-1")
        assert again.status is VenueOrderStatus.CANCELLED  # terminal: no error

    def test_cancel_unknown_order_fails_closed(self, venue):
        with pytest.raises(BrokerExecutionError) as exc:
            venue.cancel_order("never-submitted")
        assert exc.value.category is BrokerErrorCategory.INVALID_ORDER

    def test_order_status_unknown_id_fails_closed(self, venue):
        with pytest.raises(BrokerExecutionError):
            venue.order_status("never-submitted")

    def test_partial_fill_accounting(self, venue):
        venue.configure_market_fill_fraction(Decimal("0.5"))
        ack = venue.submit_order(_market(venue, "pf-1", qty=Decimal("0.04")))
        assert ack.status is VenueOrderStatus.PARTIALLY_FILLED
        assert venue.order_fills("pf-1")[0].quantity == Decimal("0.02")
        venue.fill_remaining("pf-1")
        assert venue.order_status("pf-1").status is VenueOrderStatus.FILLED

    def test_precision_violation_is_a_definitive_rejection(self, venue):
        spec = venue.instrument_spec(_symbol(venue))
        misaligned = spec.quantize_quantity(COMMON_QTY) + spec.lot_step / 2
        ack = venue.submit_order(_market(venue, "pv-1", qty=misaligned))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code  # venue-native code preserved for audit
        assert venue.executed_orders == 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:

    def test_identical_sequences_produce_identical_outcomes(self):
        for broker_id in ADAPTER_FACTORIES:
            run_one = _make(broker_id)
            run_two = _make(broker_id)
            ack_one = run_one.submit_order(_market(run_one, "det-1"))
            ack_two = run_two.submit_order(_market(run_two, "det-1"))
            assert ack_one == ack_two, broker_id
            assert run_one.order_fills("det-1") == run_two.order_fills("det-1")
            assert run_one.balances() == run_two.balances()

    def test_no_wall_clock_no_rng_in_ids(self, venue):
        ack = venue.submit_order(_market(venue, "seq-1"))
        # Sequence-counter ids: stable format, no hash-of-time jitter.
        assert ack.venue_order_id == f"{venue.broker_id}.000001"


# ---------------------------------------------------------------------------
# Failure injection (transport-level)
# ---------------------------------------------------------------------------

class TestFailureInjection:

    def test_injected_disconnect_fails_closed(self, venue):
        venue.inject_disconnect()
        assert venue.health() is ConnectionState.DISCONNECTED
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "dc-1"))
        assert exc.value.category is BrokerErrorCategory.CONNECTIVITY
        assert venue.executed_orders == 0

    def test_reconnect_restores_submissions(self, venue):
        venue.inject_disconnect()
        venue.clear_injections()
        venue.connect(BrokerCredential(ACCOUNT, SECRET))
        ack = venue.submit_order(_market(venue, "rc-1"))
        assert ack.status is VenueOrderStatus.FILLED

    def test_injected_rate_limit_is_unambiguous(self, venue):
        venue.inject_rate_limit(1)
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "rl-1"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert exc.value.retryable is True
        # The venue holds NO order for the throttled attempt.
        with pytest.raises(BrokerExecutionError):
            venue.order_status("rl-1")
        # The next attempt goes through.
        ack = venue.submit_order(_market(venue, "rl-2"))
        assert ack.status is VenueOrderStatus.FILLED

    def test_injected_ack_timeout_is_ambiguous(self, venue):
        venue.inject_ack_timeout()
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "to-1"))
        assert exc.value.category is BrokerErrorCategory.UNKNOWN_STATE
        # The venue DID accept (and fill) — the caller just cannot know.
        assert venue.order_status("to-1").status is VenueOrderStatus.FILLED

    def test_injected_rejection_is_definitive_and_idempotent(self, venue):
        venue.inject_rejection("-9999", "injected venue rejection")
        ack = venue.submit_order(_market(venue, "rj-1"))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "-9999"
        assert ack.reject_reason == "injected venue rejection"
        # A duplicate returns the SAME rejection (never re-attempts).
        assert venue.submit_order(_market(venue, "rj-1")).venue_code == "-9999"
        assert venue.executed_orders == 0

    def test_injected_extra_fill_only_on_unfilled_orders(self, venue):
        venue.submit_order(OrderRequest(
            client_order_id="ef-1", account_id=ACCOUNT, symbol=_symbol(venue),
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=COMMON_QTY, price=Decimal("48000.00"),
        ))
        venue.inject_extra_fill("ef-1", COMMON_QTY, Decimal("48000.00"))
        assert venue.order_status("ef-1").status is VenueOrderStatus.FILLED
        # Overfilling a filled order is refused.
        with pytest.raises(MockVenueError):
            venue.inject_extra_fill("ef-1", COMMON_QTY, Decimal("48000.00"))


# ---------------------------------------------------------------------------
# Reconciliation (venue level)
# ---------------------------------------------------------------------------

class TestVenueReconciliation:

    def test_clean_reconciliation_is_ok(self, venue):
        venue.submit_order(_market(venue, "rec-1"))
        report = venue.reconcile([ExpectedOrderState(
            client_order_id="rec-1",
            status=VenueOrderStatus.FILLED,
            filled_quantity=COMMON_QTY,
        )])
        assert report.ok is True
        assert report.mismatches == ()

    def test_phantom_order_is_a_mismatch(self, venue):
        venue.submit_order(_market(venue, "ph-1"))
        report = venue.reconcile([])  # journal knows nothing
        assert report.ok is False
        assert report.mismatches[0].kind.value == "PHANTOM_ORDER_AT_VENUE"

    def test_fill_divergence_is_a_mismatch(self, venue):
        venue.submit_order(OrderRequest(
            client_order_id="fd-1", account_id=ACCOUNT, symbol=_symbol(venue),
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=COMMON_QTY, price=Decimal("48000.00"),
        ))
        venue.trigger_fill("fd-1", Decimal("48000.00"))  # venue filled it
        report = venue.reconcile([ExpectedOrderState(
            client_order_id="fd-1",
            status=VenueOrderStatus.OPEN,          # journal still believes OPEN
            filled_quantity=Decimal("0"),
        )])
        assert report.ok is False
        kinds = {m.kind.value for m in report.mismatches}
        assert "STATUS_DIVERGENCE" in kinds
        assert "FILL_QUANTITY_DIVERGENCE" in kinds

    def test_unknown_journal_record_resolves_from_venue_truth(self, venue):
        venue.submit_order(_market(venue, "ur-1"))
        report = venue.reconcile([ExpectedOrderState(
            client_order_id="ur-1",
            status=VenueOrderStatus.UNKNOWN,
            filled_quantity=Decimal("0"),
        )])
        assert report.ok is True
        assert report.resolved[0].status is VenueOrderStatus.FILLED

    def test_unknown_journal_record_missing_at_venue_resolves_rejected(self, venue):
        report = venue.reconcile([ExpectedOrderState(
            client_order_id="ghost-1",
            status=VenueOrderStatus.UNKNOWN,
            filled_quantity=Decimal("0"),
        )])
        assert report.ok is True
        assert report.resolved[0].status is VenueOrderStatus.REJECTED


# ---------------------------------------------------------------------------
# Venue-specific semantics (the executable capability matrix)
# ---------------------------------------------------------------------------

class TestPaperVenueSemantics:

    def test_all_order_kinds_and_attached_sltp(self):
        venue = _make("paper-mock")
        for kind, extra in (
            (OrderKind.MARKET, {}),
            (OrderKind.LIMIT, {"price": Decimal("48000.00")}),
            (OrderKind.STOP, {"stop_price": Decimal("52000.00")}),
            (OrderKind.STOP_LIMIT, {
                "price": Decimal("52000.00"), "stop_price": Decimal("51900.00"),
            }),
        ):
            ack = venue.submit_order(_market(venue, f"pk-{kind.value}",
                                             order_kind=kind, **extra))
            assert ack.status in (VenueOrderStatus.FILLED, VenueOrderStatus.OPEN)
        # Attached SL/TP accepted.
        ack = venue.submit_order(_market(
            venue, "pk-sltp",
            stop_loss=Decimal("47000.00"), take_profit=Decimal("55000.00"),
        ))
        assert ack.status is VenueOrderStatus.FILLED

    def test_reduce_only_enforced_against_net_position(self):
        venue = _make("paper-mock")
        venue.submit_order(_market(venue, "ro-base"))
        # Long 0.02: a reduce-only SELL of the exact size is allowed...
        ack = venue.submit_order(_market(venue, "ro-ok", side=Side.SELL,
                                         reduce_only=True))
        assert ack.status is not VenueOrderStatus.REJECTED
        # ...but with no remaining position, another reduce-only is refused.
        ack2 = venue.submit_order(_market(venue, "ro-bad", side=Side.SELL,
                                          reduce_only=True))
        assert ack2.status is VenueOrderStatus.REJECTED
        assert "reduce-only" in (ack2.reject_reason or "")


class TestMT5VenueSemantics:

    def test_real_account_mode_refused_at_construction(self):
        with pytest.raises(MockVenueError):
            MT5StyleMockAdapter(fixed_clock, account_mode=AccountMode.REAL)

    def test_hedging_tickets_one_per_order(self):
        venue = _make("mt5-mock")
        venue.submit_order(_market(venue, "h-1", qty=Decimal("0.02")))
        venue.submit_order(_market(venue, "h-2", qty=Decimal("0.03")))
        positions = venue.positions()
        assert len(positions) == 2  # hedging: per-ticket, not netted
        assert all(p.ticket for p in positions)
        quantities = sorted(str(p.quantity) for p in positions)
        assert quantities == ["0.02", "0.03"]

    def test_close_position_settles_pnl_in_account_currency(self):
        venue = _make("mt5-mock")
        venue.submit_order(_market(venue, "cp-1", qty=Decimal("0.10")))
        ticket = venue.positions()[0].ticket
        entry = venue.positions()[0].average_entry_price
        pnl = venue.close_position(ticket, entry + Decimal("100.00"))
        assert pnl == Decimal("10.00000")  # 0.10 * 100 USD/BTC
        assert venue.positions() == ()
        assert venue.account_realized_pnl() == pnl

    def test_attached_sltp_accepted_with_commission_only_open(self):
        venue = _make("mt5-mock")
        ack = venue.submit_order(_market(
            venue, "mt5-sltp", qty=Decimal("0.02"),
            stop_loss=Decimal("47000.00"), take_profit=Decimal("55000.00"),
        ))
        assert ack.status is VenueOrderStatus.FILLED
        # Margin-style opening deal: commission charged, no base/quote exchange.
        fills = venue.order_fills("mt5-sltp")
        assert len(fills) == 1
        assert fills[0].fee > 0

    def test_fok_time_in_force_not_supported(self):
        venue = _make("mt5-mock")
        ack = venue.submit_order(_market(venue, "mt5-fof",
                                         time_in_force=TimeInForce.FOK))
        assert ack.status is VenueOrderStatus.REJECTED
        assert "time-in-force" in (ack.reject_reason or "")

    def test_order_budget_rate_limit_enforced(self):
        venue = _make("mt5-mock")
        for i in range(5):
            venue.submit_order(_market(venue, f"mt5-rl-{i}"))
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "mt5-rl-6th"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert exc.value.venue_code == "10027"  # TOO_MANY_REQUESTS

    def test_volume_below_minimum_rejected_with_retcode(self):
        venue = _make("mt5-mock")
        ack = venue.submit_order(_market(venue, "mt5-small", qty=Decimal("0.005")))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "10014"  # INVALID_VOLUME


class TestBinanceVenueSemantics:

    def test_stop_kind_is_a_definitive_rejection(self):
        venue = _make("binance-mock")
        ack = venue.submit_order(OrderRequest(
            client_order_id="bn-stop", account_id=ACCOUNT, symbol="BTCUSDT",
            side=Side.SELL, order_kind=OrderKind.STOP,
            quantity=COMMON_QTY, stop_price=Decimal("49000.00"),
        ))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "-1013"  # FILTER_FAILURE

    def test_min_notional_on_market_orders(self):
        venue = _make("binance-mock")
        ack = venue.submit_order(_market(venue, "bn-tiny", qty=Decimal("0.0001")))
        # 0.0001 * 50000 = 5 USDT < 10 minimum notional.
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "-1013"

    def test_insufficient_quote_balance_rejected(self):
        venue = BinanceSpotMockAdapter(
            fixed_clock, initial_balances={"USDT": Decimal("100")}
        )
        venue.connect(BrokerCredential(ACCOUNT, SECRET))
        ack = venue.submit_order(_market(venue, "bn-poor"))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "-2010"  # insufficient balance

    def test_spot_has_no_position_objects(self):
        venue = _make("binance-mock")
        venue.submit_order(_market(venue, "bn-pos"))
        assert venue.positions() == ()  # BALANCES_ONLY

    def test_request_weight_rate_limit_enforced(self):
        venue = _make("binance-mock")
        for _ in range(10):
            venue.account_info()  # 10 API calls fill the budget
        with pytest.raises(BrokerExecutionError) as exc:
            venue.account_info()  # the 11th call is throttled
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert exc.value.venue_code == "429"

    def test_unknown_order_carries_native_code(self):
        venue = _make("binance-mock")
        with pytest.raises(BrokerExecutionError) as exc:
            venue.order_status("bn-never")
        assert exc.value.venue_code == "-2013"  # Order does not exist


class TestBybitVenueSemantics:

    def test_attached_sltp_accepted(self):
        venue = _make("bybit-mock")
        ack = venue.submit_order(_market(
            venue, "by-sltp",
            stop_loss=Decimal("47000.0"), take_profit=Decimal("55000.0"),
        ))
        assert ack.status is VenueOrderStatus.FILLED

    def test_min_order_amt_satisfied(self):
        venue = _make("bybit-mock")
        ack = venue.submit_order(_market(venue, "by-ok", qty=Decimal("0.001")))
        # 0.001 * 50000 = 50 USDT ≥ 5 minimum order amount.
        assert ack.status is VenueOrderStatus.FILLED

    def test_qty_below_minimum_rejected(self):
        venue = _make("bybit-mock")
        ack = venue.submit_order(_market(venue, "by-small", qty=Decimal("0.0005")))
        # below minOrderQty 0.001 AND misaligned to qtyStep 0.001.
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "110007"

    def test_order_rate_limit_code_is_native(self):
        venue = _make("bybit-mock")
        for i in range(5):
            venue.submit_order(_market(venue, f"by-rl-{i}"))
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(venue, "by-rl-6th"))
        assert exc.value.venue_code == "10004"  # rate-limited

    def test_netting_position_after_two_buys(self):
        venue = _make("bybit-mock")
        venue.submit_order(_market(venue, "by-n1", qty=Decimal("0.02")))
        venue.submit_order(_market(venue, "by-n2", qty=Decimal("0.03")))
        positions = venue.positions()
        assert len(positions) == 1  # netted per symbol
        assert positions[0].quantity == Decimal("0.05")
