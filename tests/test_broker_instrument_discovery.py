"""Batch 7 acceptance tests — broker instrument discovery, catalog,
Bitget mock venue, and platform-registry sync (RED-first: these FAIL
on the pre-fix code).

Scope being delivered (the three-batch continuation mandate's Batch 7;
the Phase-1 discovery audit's broker matrix records Bitget as
"NOTHING — no adapter, no mock, no market-data provider"):

1. **Bitget mock venue** — the FIFTH deterministic mock adapter
   (``bitget-mock``), encoding Bitget spot semantics: MARKET/LIMIT
   only, SL/TP as separate trigger/plan orders (no attached stops on
   spot), ``clientOrderId`` native idempotency, balances-only
   account (no position object), trade filters (tick/lot/minimum
   notional). It joins the SHARED adapter contract suite (the
   contract test module's factory map), so the whole normalized
   surface is proven against it like every other venue.

2. **Instrument discovery + catalog** (``brokers/instruments.py``) —
   ``discover_instruments(adapter)`` walks a CONNECTED adapter's
   ``list_symbols``/``instrument_spec`` surface into an immutable,
   fail-closed ``InstrumentCatalog``:

   - discovery from a DISCONNECTED adapter is refused (fabricated
     catalogs are worse than none);
   - every spec's broker_id must match the adapter (foreign specs
     refuse);
   - duplicate venue symbols refuse;
   - the catalog snapshots the venue's capability descriptor AT
     DISCOVERY TIME and cross-checks it against the capability
     registry (drift between the adapter and its registered
     descriptor refuses — capability changes are explicit versioned
     events, never silent);
   - lookups are fail-closed on unknown symbols.

3. **Platform-registry sync** — ``sync_catalog_to_platform_registry``
   registers every discovered instrument into the CENTRAL
   ``InstrumentRegistry`` as canonical identities with
   ``broker:<id>`` provider-symbol mappings:

   - registration ≠ eligibility: a synced instrument lands
     DISCOVERED (the registry's own contract — nothing is tradable
     until explicitly verified);
   - the SAME canonical instrument discovered at a SECOND venue is a
     flagged duplicate whose provider mapping is MERGED (one
     canonical identity, many venue symbols — never two records);
   - the sync reports what it registered/merged;
   - the broker provider mappings are queryable through the
   registry's own ``find_by_provider_symbol``.

PAPER/TEST ONLY: the Bitget adapter is a deterministic MOCK
(MOCK_DETERMINISTIC enforced; REAL execution modes structurally
refused at descriptor registration). No network, no credentials
beyond opaque play-money holders, no real orders. LIVE TRADING
REMAINS NOT AUTHORIZED.

These tests FAIL on the pre-fix code and must pass after it.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from data_engine.brokers import (
    BrokerAdapter,
    BrokerCredential,
    BrokerErrorCategory,
    BrokerExecutionError,
    CapabilityRegistry,
    OrderKind,
    OrderRequest,
    Side,
    default_registry,
)
from data_engine.brokers.capabilities import (
    BITGET_MOCK_CAPABILITIES,
    ExecutionMode,
)
from data_engine.brokers.instruments import (
    InstrumentCatalog,
    discover_instruments,
    sync_catalog_to_platform_registry,
)
from data_engine.brokers.models import (
    AccountMode,
    VenueOrderStatus,
)
from data_engine.platform.registry import (
    Capability,
    InstrumentRegistry,
)

from test_broker_adapter_contract import fixed_clock

ACCOUNT = "acct-1"
SECRET = "mock-secret-material-DO-NOT-PRINT"
FIXED_TS = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)


def _bitget():
    from data_engine.brokers import BitgetSpotMockAdapter

    adapter = BitgetSpotMockAdapter(fixed_clock)
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter


def _binance():
    from data_engine.brokers import BinanceSpotMockAdapter

    adapter = BinanceSpotMockAdapter(fixed_clock)
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter


# ════════════════════════════════════════════════════════════════════
# 1. Bitget mock venue
# ════════════════════════════════════════════════════════════════════

class TestBitgetMockVenue:
    def test_descriptor_is_registered_and_mock_only(self):
        registry = default_registry()
        assert registry.has("bitget-mock")
        cap = registry.get("bitget-mock")
        assert cap.execution_mode is ExecutionMode.MOCK_DETERMINISTIC
        assert cap.order_kinds == (OrderKind.MARKET, OrderKind.LIMIT)
        assert cap.supports_reduce_only is False  # spot: futures-only concept
        # spot semantics: no attached SL/TP, balances-only account
        from data_engine.brokers.capabilities import (
            IdempotencyKeyMechanism,
            PositionMode,
            SlTpSemantics,
        )

        assert cap.sl_tp is SlTpSemantics.SEPARATE_ORDERS
        assert cap.position_mode is PositionMode.BALANCES_ONLY
        assert cap.idempotency_key is IdempotencyKeyMechanism.NATIVE_CLIENT_ID
        assert AccountMode.REAL not in cap.account_modes

    def test_serves_btc_and_eth_instruments(self):
        venue = _bitget()
        assert venue.broker_id == "bitget-mock"
        symbols = venue.list_symbols()
        assert "BTCUSDT" in symbols and "ETHUSDT" in symbols
        spec = venue.instrument_spec("BTCUSDT")
        assert spec.broker_id == "bitget-mock"
        assert spec.base_asset == "BTC" and spec.quote_asset == "USDT"
        assert spec.tick_size > 0 and spec.lot_step > 0
        assert spec.min_notional > 0

    def test_unknown_symbol_fails_closed(self):
        venue = _bitget()
        with pytest.raises(BrokerExecutionError) as exc:
            venue.instrument_spec("NOTASYMBOL")
        assert exc.value.category is BrokerErrorCategory.INVALID_ORDER
        assert exc.value.venue_code == "40001"

    def test_market_order_round_trip(self):
        venue = _bitget()
        request = OrderRequest(
            client_order_id="bg-1",
            account_id=ACCOUNT,
            symbol="BTCUSDT",
            side=Side.BUY,
            order_kind=OrderKind.MARKET,
            quantity=Decimal("0.02"),
        )
        ack = venue.submit_order(request)
        assert ack.client_order_id == "bg-1"
        fills = venue.order_fills("bg-1")
        assert fills and fills[0].quantity == Decimal("0.02")

    def test_attached_sl_tp_refused_with_native_alternative(self):
        venue = _bitget()
        request = OrderRequest(
            client_order_id="bg-2",
            account_id=ACCOUNT,
            symbol="BTCUSDT",
            side=Side.BUY,
            order_kind=OrderKind.LIMIT,
            quantity=Decimal("0.02"),
            price=Decimal("49000.00"),
            stop_loss=Decimal("48000.00"),
        )
        ack = venue.submit_order(request)
        # spot: stops are separate trigger/plan orders at this venue
        assert ack.status is VenueOrderStatus.REJECTED
        assert "separate" in (ack.reject_reason or "").lower()

    def test_lot_step_violation_refused(self):
        venue = _bitget()
        request = OrderRequest(
            client_order_id="bg-3",
            account_id=ACCOUNT,
            symbol="BTCUSDT",
            side=Side.BUY,
            order_kind=OrderKind.MARKET,
            quantity=Decimal("0.020001"),  # off the lot step
        )
        ack = venue.submit_order(request)
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "43007"

    def test_min_notional_refused(self):
        venue = _bitget()
        request = OrderRequest(
            client_order_id="bg-4",
            account_id=ACCOUNT,
            symbol="BTCUSDT",
            side=Side.BUY,
            order_kind=OrderKind.LIMIT,
            quantity=Decimal("0.0001"),   # 0.0001 * 49000 = 4.9 USDT
            price=Decimal("49000.00"),
        )
        ack = venue.submit_order(request)
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "43007"

    def test_capability_drift_refused_by_registry(self):
        registry = default_registry()
        drifted = BITGET_MOCK_CAPABILITIES.model_copy(
            update={"supports_reduce_only": True}
        )
        with pytest.raises(Exception):
            registry.register(drifted)


# ════════════════════════════════════════════════════════════════════
# 2. Instrument discovery + catalog
# ════════════════════════════════════════════════════════════════════

class TestInstrumentDiscovery:
    def test_discovery_from_connected_adapter(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        assert isinstance(catalog, InstrumentCatalog)
        assert catalog.broker_id == "bitget-mock"
        assert set(catalog.symbols()) == {"BTCUSDT", "ETHUSDT"}
        entry = catalog.entry("BTCUSDT")
        assert entry.spec.base_asset == "BTC"
        assert entry.capabilities == venue.capabilities
        assert entry.discovered_at == FIXED_TS
        assert entry.discovery_broker_id == "bitget-mock"

    def test_disconnected_adapter_refused(self):
        venue = _bitget()
        venue.disconnect()
        with pytest.raises(BrokerExecutionError):
            discover_instruments(venue, at=FIXED_TS)

    def test_foreign_broker_id_in_spec_refused(self):
        class ForeignSpecAdapter(_bitget().__class__):
            def instrument_spec(self, symbol):
                spec = super().instrument_spec(symbol)
                return spec.model_copy(update={"broker_id": "other-broker"})

        venue = ForeignSpecAdapter(fixed_clock)
        venue.connect(BrokerCredential(ACCOUNT, SECRET))
        with pytest.raises(BrokerExecutionError):
            discover_instruments(venue, at=FIXED_TS)

    def test_duplicate_venue_symbols_refused(self):
        class DuplicateAdapter(_bitget().__class__):
            def list_symbols(self):
                return ("BTCUSDT", "BTCUSDT", "ETHUSDT")

        venue = DuplicateAdapter(fixed_clock)
        venue.connect(BrokerCredential(ACCOUNT, SECRET))
        with pytest.raises(BrokerExecutionError):
            discover_instruments(venue, at=FIXED_TS)

    def test_capability_drift_against_registry_refused(self):
        # a registry holding a DIFFERENT descriptor for this broker
        # than the adapter serves = drift; discovery refuses
        venue = _bitget()
        drifted_registry = CapabilityRegistry()
        drifted_registry.register(
            BITGET_MOCK_CAPABILITIES.model_copy(
                update={"supports_reduce_only": True}
            )
        )
        with pytest.raises(BrokerExecutionError):
            discover_instruments(
                venue, at=FIXED_TS, registry=drifted_registry
            )

    def test_consistent_registry_accepted(self):
        venue = _bitget()
        catalog = discover_instruments(
            venue, at=FIXED_TS, registry=default_registry()
        )
        assert len(catalog) == 2

    def test_catalog_lookup_fails_closed(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        with pytest.raises(BrokerExecutionError):
            catalog.entry("NOTASYMBOL")

    def test_catalog_is_immutable(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        with pytest.raises(Exception):
            catalog.entries.append(object())  # type: ignore[attr-defined]


# ════════════════════════════════════════════════════════════════════
# 3. Platform-registry sync
# ════════════════════════════════════════════════════════════════════

class TestRegistrySync:
    def test_sync_registers_canonical_instruments(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        registry = InstrumentRegistry()
        report = sync_catalog_to_platform_registry(
            catalog, registry, at=FIXED_TS
        )
        assert report.registered == 2
        assert report.duplicates == 0
        assert len(registry) == 2
        record = registry.find_by_provider_symbol(
            "broker:bitget-mock", "BTCUSDT"
        )
        assert record
        record = record[0]
        assert record.instrument.symbol == "BTC/USDT"
        assert record.instrument.base_asset == "BTC"
        assert record.instrument.quote_asset == "USDT"
        assert record.discovery_source == "broker:bitget-mock"

    def test_registration_is_not_eligibility(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        registry = InstrumentRegistry()
        sync_catalog_to_platform_registry(catalog, registry, at=FIXED_TS)
        records = registry.find_by_provider_symbol(
            "broker:bitget-mock", "BTCUSDT"
        )
        record = records[0]
        # the registry's own honest contract: a fresh registration is
        # DISCOVERED — nothing is tradable until explicitly verified
        assert record.eligibility(
            Capability.PAPER_TRADING
        ).value in ("Discovered", "Blocked")
        assert record.data_state is None
        assert record.strategy_eligible is False

    def test_resync_is_a_flagged_duplicate_with_merged_mapping(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        registry = InstrumentRegistry()
        sync_catalog_to_platform_registry(catalog, registry, at=FIXED_TS)
        report2 = sync_catalog_to_platform_registry(
            catalog, registry, at=FIXED_TS
        )
        assert report2.registered == 0
        assert report2.duplicates == 2
        assert len(registry) == 2  # never duplicated

    def test_second_venue_merges_into_the_same_canonical_identity(self):
        bitget = discover_instruments(_bitget(), at=FIXED_TS)
        binance = discover_instruments(_binance(), at=FIXED_TS)
        registry = InstrumentRegistry()
        sync_catalog_to_platform_registry(bitget, registry, at=FIXED_TS)
        report = sync_catalog_to_platform_registry(
            binance, registry, at=FIXED_TS
        )
        # BTC/USDT already exists — the Binance mapping is MERGED into
        # the SAME canonical record (one identity, many venue symbols)
        assert report.duplicates >= 1
        record = registry.find_by_symbol("BTC/USDT")
        assert len(record) == 1
        providers = {
            (m.provider, m.provider_symbol)
            for m in record[0].provider_symbols
        }
        assert ("broker:bitget-mock", "BTCUSDT") in providers
        assert ("broker:binance-mock", "BTCUSDT") in providers

    def test_provider_mappings_are_unverified_by_default(self):
        venue = _bitget()
        catalog = discover_instruments(venue, at=FIXED_TS)
        registry = InstrumentRegistry()
        sync_catalog_to_platform_registry(catalog, registry, at=FIXED_TS)
        record = registry.find_by_provider_symbol(
            "broker:bitget-mock", "BTCUSDT"
        )[0]
        for mapping in record.provider_symbols:
            if mapping.provider == "broker:bitget-mock":
                assert mapping.verified is False
