"""Exness + XM venue disposition tests (Batch 15 — items C-1/C-2/C-3).

Batch 11 §9 finding being closed here: "Exness and XM have NO adapter
of any kind — decide and implement mock-level adapters (following
bitget_mock.py as the pattern) or record interface-only status; never
claim real connectivity."

Disposition chosen: DEDICATED MT5-class mock adapters (Exness and XM are
MT5 brokerages — the existing ``MT5StyleMockAdapter`` encodes their
shared terminal semantics; the new adapters give each venue its own
broker identity, capability descriptor, instrument set and platform
registry mappings). RED-FIRST: this file was written BEFORE the
implementation and must fail on import until the adapters exist.

These tests prove — deterministically, no network, no credentials:
- both descriptors register in the default capability registry
  (SEVEN mock venues after this batch);
- MT5-class semantics per venue (hedging tickets, attached SL/TP,
  comment-field idempotency, volume-step lots, MT5 retcodes);
- REAL account modes / REAL execution modes remain REFUSED;
- the three MT5-class venues (mt5/exness/xm) discover into catalogs and
  SYNC into one platform registry where EUR/USD is ONE canonical
  identity with THREE venue mappings (duplicate-merge, never forked
  identity), all mappings UNVERIFIED, eligibility NEVER granted;
- discovery is deterministic across restart (identical specs, identical
  canonical ids, re-sync duplicates counted).

LIVE TRADING IS NOT AUTHORIZED — nothing here connects to any real
broker, and no real connectivity is claimed.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from data_engine.brokers import (
    BrokerCredential,
    BrokerErrorCategory,
    BrokerExecutionError,
    BrokerCapabilities,
    CapabilityRegistryError,
    MT5StyleMockAdapter,
    OrderKind,
    OrderRequest,
    Side,
    TimeInForce,
    default_registry,
    discover_instruments,
    sync_catalog_to_platform_registry,
)
from data_engine.brokers.capabilities import (
    ExecutionMode,
    IdempotencyKeyMechanism,
    PositionMode,
    SlTpSemantics,
)
from data_engine.brokers.models import AccountMode, VenueOrderStatus
from data_engine.platform.registry import Capability, InstrumentRegistry

ACCOUNT = "acct-1"
SECRET = "mock-secret-material-DO-NOT-PRINT"
FIXED_TS = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)

#: The SEVEN deterministic mock venues after Batch 15.
SEVEN_VENUES = (
    "binance-mock", "bitget-mock", "bybit-mock", "exness-mock",
    "mt5-mock", "paper-mock", "xm-mock",
)


def fixed_clock() -> datetime:
    return FIXED_TS


def _make(broker_id: str):
    from data_engine.brokers import ExnessMT5MockAdapter, XMMT5MockAdapter

    factories = {
        "exness-mock": ExnessMT5MockAdapter,
        "xm-mock": XMMT5MockAdapter,
    }
    adapter = factories[broker_id](fixed_clock)
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter


def _market(broker_id: str, client_order_id: str, qty=Decimal("0.02"), **overrides):
    kwargs = dict(
        client_order_id=client_order_id,
        account_id=ACCOUNT,
        symbol="BTCUSD",
        side=Side.BUY,
        order_kind=OrderKind.MARKET,
        quantity=qty,
    )
    kwargs.update(overrides)
    return OrderRequest(**kwargs)


def _discover_and_sync(broker_ids, registry, at=FIXED_TS):
    """Discover each MT5-class venue and sync into ONE platform registry."""
    from data_engine.brokers import MT5StyleMockAdapter, ExnessMT5MockAdapter, XMMT5MockAdapter

    factories = {
        "mt5-mock": MT5StyleMockAdapter,
        "exness-mock": ExnessMT5MockAdapter,
        "xm-mock": XMMT5MockAdapter,
    }
    reports = []
    for broker_id in broker_ids:
        adapter = factories[broker_id](fixed_clock)
        adapter.connect(BrokerCredential(ACCOUNT, SECRET))
        catalog = discover_instruments(adapter, at=at, registry=default_registry())
        reports.append(sync_catalog_to_platform_registry(catalog, registry, at=at))
    return reports


# ════════════════════════════════════════════════════════════════════
# 1. Capability descriptors
# ════════════════════════════════════════════════════════════════════

class TestExnessXmDescriptors:

    def test_default_registry_has_seven_mock_venues(self):
        registry = default_registry()
        assert registry.broker_ids() == SEVEN_VENUES

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_descriptor_is_registered_and_mt5_class(self, broker_id):
        cap = default_registry().get(broker_id)
        assert cap.execution_mode is ExecutionMode.MOCK_DETERMINISTIC
        assert cap.order_kinds == (
            OrderKind.MARKET, OrderKind.LIMIT, OrderKind.STOP, OrderKind.STOP_LIMIT,
        )
        assert cap.time_in_force == (TimeInForce.GTC, TimeInForce.IOC)
        assert cap.sl_tp is SlTpSemantics.ATTACHED
        assert cap.position_mode is PositionMode.HEDGING
        assert cap.idempotency_key is IdempotencyKeyMechanism.COMMENT_FIELD
        assert cap.supports_reduce_only is False
        assert cap.account_modes == (AccountMode.DEMO,)
        assert cap.rate_limit.max_orders_per_window == 5
        assert cap.provides_market_data is False
        assert broker_id.replace("-mock", "") in cap.display_name.lower()

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_real_execution_mode_descriptor_refused(self, broker_id):
        base = default_registry().get(broker_id)
        with pytest.raises(Exception):
            BrokerCapabilities(
                **{
                    **base.model_dump(),
                    "execution_mode": ExecutionMode.REAL,
                    "account_modes": (AccountMode.REAL,),
                }
            )

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_capability_drift_is_refused(self, broker_id):
        registry = default_registry()
        drifted = registry.get(broker_id).model_copy(
            update={"display_name": "silently different"}
        )
        with pytest.raises(CapabilityRegistryError):
            registry.register(drifted)


# ════════════════════════════════════════════════════════════════════
# 2. Adapter venue semantics (MT5 class, per-venue identity)
# ════════════════════════════════════════════════════════════════════

class TestExnessXmAdapters:

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_real_account_mode_refused_at_construction(self, broker_id):
        from data_engine.brokers import ExnessMT5MockAdapter, XMMT5MockAdapter

        factories = {"exness-mock": ExnessMT5MockAdapter, "xm-mock": XMMT5MockAdapter}
        with pytest.raises(Exception):
            factories[broker_id](fixed_clock, account_mode=AccountMode.REAL)

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_instruments_belong_to_this_broker(self, broker_id):
        venue = _make(broker_id)
        symbols = venue.list_symbols()
        assert symbols == ("BTCUSD", "EURUSD", "XAUUSD")  # sorted, MT5-class naming
        for symbol in symbols:
            spec = venue.instrument_spec(symbol)
            assert spec.broker_id == broker_id
            assert spec.symbol == symbol
            assert spec.lot_step == Decimal("0.01")
            assert spec.min_quantity == Decimal("0.01")

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_eurusd_symbol_normalization(self, broker_id):
        venue = _make(broker_id)
        spec = venue.instrument_spec("EURUSD")
        assert spec.base_asset == "EUR"
        assert spec.quote_asset == "USD"
        assert spec.tick_size == Decimal("0.00001")
        assert spec.reference_price == Decimal("1.10000")

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_unknown_symbol_fails_closed(self, broker_id):
        venue = _make(broker_id)
        with pytest.raises(BrokerExecutionError) as exc:
            venue.instrument_spec("DOGECHF")
        assert exc.value.category is BrokerErrorCategory.INVALID_ORDER

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_hedging_tickets_one_per_order(self, broker_id):
        venue = _make(broker_id)
        venue.submit_order(_market(broker_id, "h-1", qty=Decimal("0.02")))
        venue.submit_order(_market(broker_id, "h-2", qty=Decimal("0.03")))
        positions = venue.positions()
        assert len(positions) == 2  # hedging: per-ticket, not netted
        assert all(p.ticket for p in positions)
        assert all(p.broker_id == broker_id for p in positions)

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_duplicate_client_order_id_never_executes_twice(self, broker_id):
        venue = _make(broker_id)
        first = venue.submit_order(_market(broker_id, "idem-1"))
        second = venue.submit_order(_market(broker_id, "idem-1"))
        assert first == second  # comment-field idempotency: same ack
        assert len(venue.positions()) == 1

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_attached_sltp_accepted_with_commission_only_open(self, broker_id):
        venue = _make(broker_id)
        ack = venue.submit_order(_market(
            broker_id, "sltp-1", qty=Decimal("0.02"),
            stop_loss=Decimal("47000.00"), take_profit=Decimal("55000.00"),
        ))
        assert ack.status is VenueOrderStatus.FILLED
        fills = venue.order_fills("sltp-1")
        assert len(fills) == 1
        assert fills[0].fee > 0  # margin-style: commission only at open

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_fok_time_in_force_not_supported(self, broker_id):
        venue = _make(broker_id)
        ack = venue.submit_order(
            _market(broker_id, "fof-1", time_in_force=TimeInForce.FOK)
        )
        assert ack.status is VenueOrderStatus.REJECTED
        assert "time-in-force" in (ack.reject_reason or "")

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_volume_below_minimum_rejected_with_retcode(self, broker_id):
        venue = _make(broker_id)
        ack = venue.submit_order(_market(broker_id, "small-1", qty=Decimal("0.005")))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "10014"  # TRADE_RETCODE_INVALID_VOLUME

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_order_budget_rate_limit_enforced(self, broker_id):
        venue = _make(broker_id)
        for i in range(5):
            venue.submit_order(_market(broker_id, f"rl-{i}"))
        with pytest.raises(BrokerExecutionError) as exc:
            venue.submit_order(_market(broker_id, "rl-6th"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert exc.value.venue_code == "10027"  # TOO_MANY_REQUESTS

    @pytest.mark.parametrize("broker_id", ["exness-mock", "xm-mock"])
    def test_close_position_settles_pnl_in_account_currency(self, broker_id):
        venue = _make(broker_id)
        venue.submit_order(_market(broker_id, "cp-1", qty=Decimal("0.10")))
        position = venue.positions()[0]
        entry = position.average_entry_price
        close_price = entry + Decimal("100.00")
        pnl = venue.close_position(position.ticket, close_price)
        assert pnl == (close_price - entry) * Decimal("0.10")
        assert venue.positions() == ()
        assert venue.account_realized_pnl() == pnl


# ════════════════════════════════════════════════════════════════════
# 3. Discovery + cross-venue registry sync (C-2 foundation)
# ════════════════════════════════════════════════════════════════════

class TestCrossVenueCatalog:

    def test_all_three_mt5_class_venues_discover(self):
        for broker_id in ("mt5-mock", "exness-mock", "xm-mock"):
            adapter = _make(broker_id) if broker_id != "mt5-mock" else _make_mt5()
            catalog = discover_instruments(
                adapter, at=FIXED_TS, registry=default_registry()
            )
            assert catalog.broker_id == broker_id
            assert catalog.symbols() == ("BTCUSD", "EURUSD", "XAUUSD")

    def test_eurusd_is_one_canonical_identity_with_three_venue_mappings(self):
        registry = InstrumentRegistry()
        reports = _discover_and_sync(
            ("mt5-mock", "exness-mock", "xm-mock"), registry
        )
        # First sync registers 3 canonical identities; the other two
        # syncs are pure duplicate-merges (never forked identity).
        assert [r.registered for r in reports] == [3, 0, 0]
        assert [r.duplicates for r in reports] == [0, 3, 3]
        assert all(r.eligibility_granted is False for r in reports)
        assert len(registry) == 3  # EUR/USD, XAU/USD, BTC/USD only
        eurusd = registry.find_by_symbol("EUR/USD")
        assert len(eurusd) == 1
        record = eurusd[0]
        mappings = {
            (m.provider, m.provider_symbol): m for m in record.provider_symbols
        }
        assert set(mappings) == {
            ("broker:mt5-mock", "EURUSD"),
            ("broker:exness-mock", "EURUSD"),
            ("broker:xm-mock", "EURUSD"),
        }
        assert all(m.verified is False for m in record.provider_symbols)

    def test_synced_instruments_are_discovered_not_eligible(self):
        registry = InstrumentRegistry()
        _discover_and_sync(("mt5-mock", "exness-mock", "xm-mock"), registry)
        for record in registry.all_records():
            assert record.data_state is None
            assert record.strategy_eligible is False
            assert record.monitoring is False
            # Registration is DISTINCT from eligibility (registry
            # contract): with no data state the honest per-capability
            # status is DISCOVERED — never ELIGIBLE.
            assert record.eligibility(Capability.LIVE_TRADING).value == "Not Authorized"
            assert record.eligibility(Capability.PAPER_TRADING).value == "Discovered"
            assert record.eligibility(Capability.RESEARCH).value == "Discovered"

    def test_discovery_is_deterministic_across_restart(self):
        # Two independent discovery+sync cycles produce IDENTICAL
        # canonical records (internal_id is identity-pure, INV-01).
        registry_a = InstrumentRegistry()
        registry_b = InstrumentRegistry()
        _discover_and_sync(("mt5-mock", "exness-mock", "xm-mock"), registry_a)
        _discover_and_sync(("mt5-mock", "exness-mock", "xm-mock"), registry_b)
        ids_a = sorted(r.internal_id for r in registry_a.all_records())
        ids_b = sorted(r.internal_id for r in registry_b.all_records())
        assert ids_a == ids_b
        # Re-syncing the SAME venues into the SAME registry only adds
        # duplicates (idempotent merge, no new records).
        before = len(registry_a)
        reports = _discover_and_sync(
            ("mt5-mock", "exness-mock", "xm-mock"), registry_a,
            at=datetime(2026, 10, 13, 13, 0, 0, tzinfo=UTC),
        )
        assert all(r.registered == 0 for r in reports)
        assert all(r.duplicates == 3 for r in reports)
        assert len(registry_a) == before


def _make_mt5():
    adapter = MT5StyleMockAdapter(fixed_clock)
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter
