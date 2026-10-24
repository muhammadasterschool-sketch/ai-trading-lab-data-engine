"""Paper-only NEGATIVE tests — proving the genuine MT5 feed cannot trade.

These tests exist to make the boundary EVIDENCE, not a claim:

1. the feed's only order surface is the refusal trio;
2. a call-recording spy across a FULL read workflow shows every module
   function used stays inside the read allowlist and ZERO order
   functions are ever invoked (the spy's order functions raise on any
   attempt);
3. static AST scan: no call to any MT5 order function exists in the
   three genuine-feed modules;
4. the feed cannot be smuggled into the execution venue layer (REAL
   execution-mode descriptors are refused at registration);
5. no live-trading flag exists anywhere on the feed.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from fake_mt5_lab import FakeMT5Module, make_rates, make_ticks

from data_engine.platform.mt5 import MT5OrderRefusedError
from data_engine.platform.mt5_market_data import (
    EXNESS_MT5_DEMO_PROVIDER_NAME,
    ExnessMT5DemoFeed,
)
from data_engine.platform.mt5_symbol_map import SymbolMapEntry
from data_engine.platform.mt5_terminal import (
    MT5_READ_METHODS,
    MT5TerminalConfig,
    RealMT5Terminal,
)
from data_engine.schemas import ProviderConfig, Timeframe

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)
NOW_EPOCH = int(NOW.timestamp())

ORDER_FUNCTION_NAMES = (
    "order_send",
    "order_check",
    "order_close",
    "order_calc_margin",
    "order_calc_profit",
    "positions_get",
    "history_orders_get",
    "history_deals_get",
)

GENUINE_MODULES = (
    "mt5_market_data.py",
    "mt5_terminal.py",
    "mt5_symbol_map.py",
)


def make_connected_feed(**kw) -> tuple[FakeMT5Module, ExnessMT5DemoFeed]:
    fake = FakeMT5Module()
    fake._rates[("EURUSDm", FakeMT5Module.TIMEFRAME_M1)] = make_rates(
        "EURUSDm", 60, 9, NOW_EPOCH - 30
    )
    fake._ticks["EURUSDm"] = make_ticks("EURUSDm", 5, NOW_EPOCH - 2)
    config = MT5TerminalConfig(
        login=88012345,
        password=SecretStr("dummy-pass-not-real"),
        server="Exness-MT5Trial8",
    )
    terminal = RealMT5Terminal(config, module=fake)
    cfg = ProviderConfig(
        provider_name=EXNESS_MT5_DEMO_PROVIDER_NAME,
        provider_type="broker-terminal",
    )
    feed = ExnessMT5DemoFeed(
        cfg,
        terminal=terminal,
        symbol_map_proposals=(
            SymbolMapEntry(canonical="EURUSD", broker_symbol="EURUSDm"),
        ),
        clock=lambda: NOW,
        sleep=lambda _s: None,
        **kw,
    )
    feed.connect()
    return fake, feed


# ════════════════════════════════════════════════════════════════════
# 1. The refusal trio is the ONLY order surface
# ════════════════════════════════════════════════════════════════════

class TestRefusalTrio:
    def test_submit_order_refused(self):
        _f, feed = make_connected_feed()
        with pytest.raises(MT5OrderRefusedError) as excinfo:
            feed.submit_order(symbol="EURUSDm", volume=0.01)
        assert "REFUSED" in str(excinfo.value)
        assert "NOT AUTHORIZED" in str(excinfo.value)

    def test_modify_order_refused(self):
        _f, feed = make_connected_feed()
        with pytest.raises(MT5OrderRefusedError):
            feed.modify_order(ticket=1)

    def test_cancel_order_refused(self):
        _f, feed = make_connected_feed()
        with pytest.raises(MT5OrderRefusedError):
            feed.cancel_order(ticket=1)

    def test_refusals_hold_even_disconnected(self):
        _f, feed = make_connected_feed()
        feed.disconnect()
        with pytest.raises(MT5OrderRefusedError):
            feed.submit_order()
        with pytest.raises(MT5OrderRefusedError):
            feed.modify_order()
        with pytest.raises(MT5OrderRefusedError):
            feed.cancel_order()

    def test_no_other_order_named_api_exists(self):
        _f, feed = make_connected_feed()
        forbidden_prefixes = (
            "place", "execute", "route", "close_position",
            "open_position", "send_order", "trade", "buy", "sell",
        )
        public = [name for name in dir(feed) if not name.startswith("_")]
        for name in public:
            lowered = name.lower()
            if name in ("submit_order", "modify_order", "cancel_order"):
                continue  # the refusal trio itself
            for prefix in forbidden_prefixes:
                assert not lowered.startswith(prefix), (
                    f"unexpected order-surface API on feed: {name}"
                )
        # no live-trading flag of any kind
        for name in public:
            assert "live" not in lowered, f"unexpected live flag: {name}"


# ════════════════════════════════════════════════════════════════════
# 2. Spy: full workflow stays inside the read allowlist
# ════════════════════════════════════════════════════════════════════

class TestReadAllowlistSpy:
    def test_full_workflow_zero_order_attempts(self):
        fake, feed = make_connected_feed()
        # exercise EVERY read surface the feed offers
        feed.symbol_catalogue()
        feed.symbol_specification("EURUSD")
        feed.latest_bars("EURUSD", "M1", 5)
        feed.latest_ticks("EURUSD", 3)
        feed.fetch_candles(
            "EURUSD",
            Timeframe.M1,
            datetime.fromtimestamp(NOW_EPOCH - 600, tz=UTC),
            NOW,
        )
        feed.health_check()
        feed.check_connectivity()
        feed.ensure_connected()
        feed.disconnect()
        # the order functions are instrumented to RECORD + raise — any
        # attempt inside the workflow would have raised long before
        assert fake.order_attempts == [], (
            f"ORDER ATTEMPTS RECORDED: {fake.order_attempts}"
        )

    def test_every_called_function_inside_read_allowlist(self):
        fake, feed = make_connected_feed()
        feed.symbol_catalogue()
        feed.latest_bars("EURUSD", "M1", 3)
        feed.latest_ticks("EURUSD", 2)
        feed.disconnect()
        called = {name for name, _args, _kw in fake.calls}
        assert called <= MT5_READ_METHODS, (
            f"functions outside the read allowlist were called: "
            f"{sorted(called - MT5_READ_METHODS)}"
        )
        # and no order function name appears among the called names
        assert called.isdisjoint(set(ORDER_FUNCTION_NAMES))

    def test_choke_point_refuses_non_read_names(self):
        _f, terminal = None, None
        config = MT5TerminalConfig(
            login=1, password=SecretStr("x"), server="S"
        )
        terminal = RealMT5Terminal(config, module=FakeMT5Module())
        with pytest.raises(Exception) as excinfo:
            terminal._call("order_send", "EURUSDm", 0.01)
        assert "outside the read-only MT5 allowlist" in str(excinfo.value)


# ════════════════════════════════════════════════════════════════════
# 3. Static AST scan — no order call exists in the genuine modules
# ════════════════════════════════════════════════════════════════════

class TestStaticAstScan:
    def test_no_order_function_call_in_genuine_modules(self):
        src_dir = Path(__file__).resolve().parent.parent / (
            "src/data_engine/platform"
        )
        for module_name in GENUINE_MODULES:
            tree = ast.parse(
                (src_dir / module_name).read_text(encoding="utf-8"),
                filename=module_name,
            )
            offenders = []
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in ORDER_FUNCTION_NAMES:
                    offenders.append((module_name, name, node.lineno))
            assert offenders == [], (
                f"order-function calls found in {module_name}: {offenders}"
            )

    def test_no_hardcoded_exness_suffix_in_source(self):
        # "EURUSDm"-style suffixes are per-account facts observed from a
        # terminal — they must NEVER be baked into the implementation
        src_dir = Path(__file__).resolve().parent.parent / (
            "src/data_engine/platform"
        )
        for module_name in GENUINE_MODULES:
            source = (src_dir / module_name).read_text(encoding="utf-8")
            for hardcoded in ("EURUSDm", "GBPUSDm", "XAUUSDm"):
                assert hardcoded not in source, (
                    f"hardcoded broker symbol {hardcoded!r} found in "
                    f"{module_name} — broker naming must stay "
                    f"observation-driven"
                )


# ════════════════════════════════════════════════════════════════════
# 4. The feed cannot become an execution venue
# ════════════════════════════════════════════════════════════════════

class TestNotAnExecutionVenue:
    def test_real_mode_venue_descriptor_refused_at_registration(self):
        from data_engine.brokers.capabilities import (
            AccountMode,
            BrokerCapabilities,
            ExecutionMode,
            OrderKind,
        )

        with pytest.raises(ValueError) as excinfo:
            BrokerCapabilities(
                broker_id="exness-mt5-demo-venue",
                display_name="Exness MT5 (would-be REAL venue)",
                order_kinds=(OrderKind.MARKET,),
                account_modes=(AccountMode.REAL,),
                execution_mode=ExecutionMode.REAL,
            )
        assert "REAL execution-mode descriptors are not registrable" in str(
            excinfo.value
        )

    def test_capability_registry_has_no_mt5_venue(self):
        from data_engine.brokers.capabilities import CapabilityRegistry

        registry = CapabilityRegistry()
        ids = registry.broker_ids()
        assert all("mt5-demo-venue" not in i for i in ids)


# ════════════════════════════════════════════════════════════════════
# 5. Governance markers preserved
# ════════════════════════════════════════════════════════════════════

class TestGovernanceMarkers:
    def test_provider_registered_readonly(self):
        from data_engine.provider import ProviderFactory

        assert EXNESS_MT5_DEMO_PROVIDER_NAME in (
            ProviderFactory.registered_providers()
        )

    def test_candidate_source_unvetted(self):
        from data_engine.platform.feed_source_candidates import (
            build_feed_source_registry,
            candidate_record,
        )
        from data_engine.prediction.source_registry import (
            SourceVerificationStatus,
        )

        record = candidate_record("exness-mt5-demo")
        assert record.verification_status is (
            SourceVerificationStatus.UNVETTED
        )
        assert record.approved_usage_scopes == ()
        registry = build_feed_source_registry()
        assert all(
            r.verification_status is SourceVerificationStatus.UNVETTED
            for r in registry.list_records()
        )

    def test_blocked_markets_unchanged(self):
        from data_engine.platform.feed_source_candidates import (
            BLOCKED_MARKETS,
        )

        assert BLOCKED_MARKETS == (
            "forex-15m-ohlc",
            "stocks-15m",
            "metals-15m",
        )
