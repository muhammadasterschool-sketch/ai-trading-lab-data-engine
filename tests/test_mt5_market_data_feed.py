"""Genuine Exness MT5 DEMO feed — unit tests (fake module, no terminal).

Every test drives the REAL feed + REAL terminal-boundary code with an
injected fake MetaTrader5 module (the mocked-external-service
discipline used across this repository). No Windows terminal, no
network, no broker — and no mock is ever labelled as real data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from pydantic import SecretStr

from fake_mt5_lab import (
    FakeMT5Module,
    SymbolInfo,
    make_catalogue,
    make_rates,
    make_ticks,
)
from data_engine.platform.mt5 import (
    MT5Adapter,
    MT5ConnectionState,
    MT5OrderRefusedError,
)
from data_engine.platform.mt5_market_data import (
    EXNESS_MT5_DEMO_PROVIDER_NAME,
    ExnessMT5DemoFeed,
    MT5ConfigError,
    MT5ConnectError,
    MT5DemoVerificationError,
    MT5DisconnectedError,
    MT5ModuleUnavailableError,
    MT5NoDataError,
    MT5ServerMismatchError,
    MT5StaleDataError,
)
from data_engine.platform.mt5_symbol_map import (
    MT5SymbolMapError,
    SymbolMapEntry,
)
from data_engine.platform.mt5_terminal import (
    MT5CredentialsError,
    MT5TerminalConfig,
    MT5TerminalInitializeError,
    RealMT5Terminal,
    rates_to_dicts,
)
from data_engine.schemas import Candle, ProviderConfig, Timeframe

# Friday 2026-10-23 12:00 UTC — a market-open instant for FX.
NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)
NOW_EPOCH = int(NOW.timestamp())
DUMMY_PASSWORD = "dummy-operator-pass-not-a-real-secret"

DEFAULT_PROPOSALS = (
    SymbolMapEntry(canonical="EURUSD", broker_symbol="EURUSDm"),
    SymbolMapEntry(canonical="XAUUSD", broker_symbol="XAUUSD"),
)


def make_terminal(fake: FakeMT5Module | None = None, **kw):
    fake = fake if fake is not None else FakeMT5Module(**kw)
    config = MT5TerminalConfig(
        login=88012345,
        password=SecretStr(DUMMY_PASSWORD),
        server="Exness-MT5Trial8",
    )
    return fake, RealMT5Terminal(config, module=fake), config


def make_rates_fixture(fake: FakeMT5Module) -> None:
    """9 M1 rows: newest = forming (opens NOW-30), 8 older closed."""
    fake._rates[("EURUSDm", FakeMT5Module.TIMEFRAME_M1)] = make_rates(
        "EURUSDm", 60, 9, NOW_EPOCH - 30
    )
    fake._rates[("XAUUSD", FakeMT5Module.TIMEFRAME_M1)] = make_rates(
        "XAUUSD", 60, 9, NOW_EPOCH - 30
    )


def make_feed(terminal, **kw) -> ExnessMT5DemoFeed:
    cfg = ProviderConfig(
        provider_name=EXNESS_MT5_DEMO_PROVIDER_NAME,
        provider_type="broker-terminal",
        supports_bid_ask=True,
    )
    kw.setdefault("symbol_map_proposals", DEFAULT_PROPOSALS)
    kw.setdefault("clock", lambda: NOW)
    kw.setdefault("sleep", lambda _s: None)
    return ExnessMT5DemoFeed(cfg, terminal=terminal, **kw)


def connect_feed(fake: FakeMT5Module, **kw) -> ExnessMT5DemoFeed:
    make_rates_fixture(fake)
    fake._ticks["EURUSDm"] = make_ticks("EURUSDm", 5, NOW_EPOCH - 2)
    fake._ticks["XAUUSD"] = make_ticks("XAUUSD", 5, NOW_EPOCH - 2)
    _fake, terminal, _cfg = make_terminal(fake)
    feed = make_feed(terminal, **kw)
    feed.connect()
    return feed


# ════════════════════════════════════════════════════════════════════
# Terminal configuration & credential hygiene
# ════════════════════════════════════════════════════════════════════

class TestTerminalConfig:
    def test_from_env_missing_variables_named_not_echoed(self):
        with pytest.raises(MT5CredentialsError) as excinfo:
            MT5TerminalConfig.from_env(env={})
        msg = str(excinfo.value)
        assert "MT5_LOGIN" in msg and "MT5_PASSWORD" in msg
        assert "MT5_SERVER" in msg

    def test_from_env_non_numeric_login_refused(self):
        with pytest.raises(MT5CredentialsError):
            MT5TerminalConfig.from_env(
                env={
                    "MT5_LOGIN": "not-a-number",
                    "MT5_PASSWORD": "x",
                    "MT5_SERVER": "Exness-MT5Trial8",
                }
            )

    def test_from_env_round_trip(self):
        cfg = MT5TerminalConfig.from_env(
            env={
                "MT5_LOGIN": "88012345",
                "MT5_PASSWORD": DUMMY_PASSWORD,
                "MT5_SERVER": "Exness-MT5Trial8",
                "MT5_TERMINAL_PATH": "C:/Program Files/MetaTrader 5/terminal64.exe",
            }
        )
        assert cfg.login == 88012345
        assert cfg.password.get_secret_value() == DUMMY_PASSWORD

    def test_password_never_rendered(self):
        cfg = MT5TerminalConfig(
            login=1,
            password=SecretStr(DUMMY_PASSWORD),
            server="Exness-MT5Trial8",
        )
        assert DUMMY_PASSWORD not in repr(cfg)
        assert DUMMY_PASSWORD not in str(cfg)
        assert "**********" in repr(cfg)

    def test_password_not_in_json_dump(self):
        cfg = MT5TerminalConfig(
            login=1,
            password=SecretStr(DUMMY_PASSWORD),
            server="Exness-MT5Trial8",
        )
        assert DUMMY_PASSWORD not in cfg.model_dump_json()


# ════════════════════════════════════════════════════════════════════
# Module unavailability — fail closed, never mock-substituted
# ════════════════════════════════════════════════════════════════════

class TestModuleUnavailable:
    def test_connect_without_module_is_structured_error(self, monkeypatch):
        # no injected terminal → RealMT5Terminal tries the lazy real
        # import; force it to fail regardless of the host platform so
        # the structured (fail-closed) path is exercised deterministically
        import data_engine.platform.mt5_terminal as term_mod

        monkeypatch.setattr(term_mod, "load_mt5_module", lambda: None)
        cfg = ProviderConfig(
            provider_name=EXNESS_MT5_DEMO_PROVIDER_NAME,
            provider_type="broker-terminal",
        )
        feed = ExnessMT5DemoFeed(
            cfg,
            terminal_config=MT5TerminalConfig(
                login=1,
                password=SecretStr(DUMMY_PASSWORD),
                server="Exness-MT5Trial8",
            ),
        )
        with pytest.raises(MT5ModuleUnavailableError):
            feed.connect()
        assert feed.connected is False

    def test_numpy_structured_arrays_normalise(self):
        arr = np.array(
            [
                (NOW_EPOCH - 60, 1.10, 1.11, 1.09, 1.105, 120),
                (NOW_EPOCH - 120, 1.09, 1.12, 1.08, 1.10, 130),
            ],
            dtype=[
                ("time", "<i8"),
                ("open", "<f8"),
                ("high", "<f8"),
                ("low", "<f8"),
                ("close", "<f8"),
                ("tick_volume", "<i8"),
            ],
        )
        rows = rates_to_dicts(arr)
        # conversion preserves the terminal's row order verbatim (the
        # FEED sorts by time; the boundary never reorders silently)
        assert [r["time"] for r in rows] == [NOW_EPOCH - 60, NOW_EPOCH - 120]
        assert rows[0]["tick_volume"] == 120

    def test_namedtuple_symbol_info_normalises(self):
        info = SymbolInfo(
            name="XAUUSD", digits=2, point=0.01,
            trade_contract_size=100.0, currency_profit="USD",
            path="Metals", description="Gold", visible=True,
        )
        from data_engine.platform.mt5_terminal import coerce_rows

        rows = coerce_rows(info, ("name", "digits"))
        assert rows[0]["name"] == "XAUUSD"
        assert rows[0]["digits"] == 2


# ════════════════════════════════════════════════════════════════════
# Connect + POSITIVE DEMO verification
# ════════════════════════════════════════════════════════════════════

class TestConnectAndDemoVerification:
    def test_happy_path_connects_and_verifies_demo(self):
        fake = FakeMT5Module(trade_mode=FakeMT5Module.ACCOUNT_TRADE_MODE_DEMO)
        make_rates_fixture(fake)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        health = feed.connect()
        assert feed.connected is True
        assert health.demo_verified is True
        assert health.venue_server == "Exness-MT5Trial8"
        assert health.trade_mode_observed == "DEMO"
        assert health.symbol_map_size == 2
        assert fake.initialized is True

    def test_real_account_refused(self):
        fake = FakeMT5Module(trade_mode=FakeMT5Module.ACCOUNT_TRADE_MODE_REAL)
        make_rates_fixture(fake)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5DemoVerificationError) as excinfo:
            feed.connect()
        assert "REAL" in str(excinfo.value)
        assert feed.connected is False

    def test_contest_account_refused(self):
        fake = FakeMT5Module(
            trade_mode=FakeMT5Module.ACCOUNT_TRADE_MODE_CONTEST
        )
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5DemoVerificationError):
            feed.connect()

    def test_unknown_trade_mode_refused(self):
        fake = FakeMT5Module(trade_mode=99)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5DemoVerificationError) as excinfo:
            feed.connect()
        assert "unverifiable" in str(excinfo.value)

    def test_unverifiable_account_none_refused(self):
        fake = FakeMT5Module(account_returns_none=True)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5DemoVerificationError) as excinfo:
            feed.connect()
        assert "cannot be positively verified" in str(excinfo.value)

    def test_terminal_not_connected_refused(self):
        fake = FakeMT5Module(terminal_connected=False)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5ConnectError):
            feed.connect()
        assert feed.connected is False

    def test_initialize_failure_is_structured(self):
        fake = FakeMT5Module(initialize_ok=False)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5TerminalInitializeError):
            feed.connect()

    def test_server_mismatch_refused(self):
        fake = FakeMT5Module(server="BrokerX-Real")
        make_rates_fixture(fake)
        _f, terminal, config = make_terminal(fake)
        cfg = MT5TerminalConfig(
            login=88012345,
            password=SecretStr(DUMMY_PASSWORD),
            server="BrokerX-Real",
            expected_server_substring="Exness-MT5Trial",
        )
        terminal = RealMT5Terminal(cfg, module=fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5ServerMismatchError):
            feed.connect()

    def test_connect_without_any_symbol_map_refused(self):
        fake = FakeMT5Module()
        _f, terminal, _c = make_terminal(fake)
        cfg = ProviderConfig(
            provider_name=EXNESS_MT5_DEMO_PROVIDER_NAME,
            provider_type="broker-terminal",
        )
        feed = ExnessMT5DemoFeed(cfg, terminal=terminal)
        with pytest.raises(MT5ConfigError) as excinfo:
            feed.connect()
        assert "never assumes broker symbol names" in str(excinfo.value)

    def test_unobserved_identity_mapping_refused(self):
        # EURUSD (unsuffixed) does NOT exist on this terminal — only
        # EURUSDm does. An identity proposal must be REFUSED: no
        # assumptions about broker naming.
        fake = FakeMT5Module()
        make_rates_fixture(fake)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(
            terminal,
            symbol_map_proposals=(
                SymbolMapEntry(canonical="EURUSD", broker_symbol="EURUSD"),
            ),
        )
        with pytest.raises(MT5SymbolMapError) as excinfo:
            feed.connect()
        assert "NOT observed" in str(excinfo.value)


# ════════════════════════════════════════════════════════════════════
# Health report (credential-free)
# ════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_before_connect(self):
        fake = FakeMT5Module()
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        health = feed.health_check()
        assert health.state == "DISCONNECTED"
        assert health.demo_verified is False
        assert health.module_available is True

    def test_health_never_contains_credentials(self):
        feed = connect_feed(FakeMT5Module())
        blob = feed.health_check().model_dump_json()
        assert DUMMY_PASSWORD not in blob


# ════════════════════════════════════════════════════════════════════
# Catalogue + validated specification
# ════════════════════════════════════════════════════════════════════

class TestCatalogue:
    def test_catalogue_is_observed(self):
        feed = connect_feed(FakeMT5Module())
        rows = feed.symbol_catalogue()
        names = {r["name"] for r in rows}
        assert names == {"EURUSDm", "GBPUSDm", "XAUUSD", "US30"}

    def test_empty_catalogue_refused(self):
        feed = connect_feed(FakeMT5Module(empty_catalogue=True))
        with pytest.raises(MT5NoDataError):
            feed.symbol_catalogue()

    def test_specification_carries_observed_fields(self):
        feed = connect_feed(FakeMT5Module())
        entry = feed.symbol_specification("EURUSD")
        assert entry.broker_symbol == "EURUSDm"
        assert entry.observed.digits == 5
        assert entry.observed.trade_contract_size == 100000.0
        assert entry.observed.path == "Forex\\Majors"
        assert len(entry.spec_sha256) == 64

    def test_unknown_canonical_refused(self):
        feed = connect_feed(FakeMT5Module())
        with pytest.raises(MT5SymbolMapError):
            feed.symbol_specification("US500")


# ════════════════════════════════════════════════════════════════════
# Latest bars: closed-candle enforcement + freshness + provenance
# ════════════════════════════════════════════════════════════════════

class TestLatestBars:
    def test_latest_bars_happy_path(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_bars("EURUSD", "M1", 5)
        assert len(batch.bars) == 5
        prov = batch.provenance
        assert prov.environment == "DEMO"
        assert prov.canonical == "EURUSD"
        assert prov.broker_symbol == "EURUSDm"
        assert prov.row_count == 5
        assert len(prov.payload_sha256) == 64
        assert prov.timeframe == "M1"
        assert prov.staleness_flagged is False

    def test_forming_bar_excluded_by_default(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_bars("EURUSD", "M1", 8)
        # the newest fetched row opens at NOW-30 (closes NOW+30) — a
        # forming bar; closed_only must exclude it
        newest_open = max(b.raw_time_epoch for b in batch.bars)
        assert newest_open + 60 <= NOW_EPOCH
        assert len(batch.bars) == 8

    def test_closed_only_false_includes_forming_bar(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_bars("EURUSD", "M1", 8, closed_only=False)
        newest_open = max(b.raw_time_epoch for b in batch.bars)
        assert newest_open == NOW_EPOCH - 30

    def test_stale_data_raises(self):
        feed = connect_feed(FakeMT5Module())
        with pytest.raises(MT5StaleDataError) as excinfo:
            feed.latest_bars("EURUSD", "M1", 5, max_staleness_seconds=10)
        assert excinfo.value.age_seconds > excinfo.value.threshold_seconds

    def test_stale_data_can_be_flagged_not_accepted_silently(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_bars(
            "EURUSD", "M1", 5,
            max_staleness_seconds=10, stale_policy="flag",
        )
        assert batch.provenance.staleness_flagged is True
        assert batch.provenance.staleness_seconds > 10

    def test_no_rates_is_structured_empty(self):
        fake = FakeMT5Module()
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        feed.connect()
        with pytest.raises(MT5NoDataError):
            feed.latest_bars("EURUSD", "M1", 5)

    def test_count_honoured(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_bars("EURUSD", "M1", 3)
        assert len(batch.bars) == 3

    def test_corrupt_ohlc_refused(self):
        feed = connect_feed(FakeMT5Module(corrupt_rates=True))
        with pytest.raises(Exception) as excinfo:
            feed.latest_bars("EURUSD", "M1", 5)
        assert "high < low" in str(excinfo.value) or "OHLC" in str(
            excinfo.value
        )

    def test_unknown_timeframe_refused(self):
        feed = connect_feed(FakeMT5Module())
        with pytest.raises(MT5ConfigError):
            feed.latest_bars("EURUSD", "M7", 5)

    def test_bars_before_connect_refused(self):
        fake = FakeMT5Module()
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        with pytest.raises(MT5DisconnectedError):
            feed.latest_bars("EURUSD", "M1", 5)

    def test_disconnected_mid_session_refused(self):
        feed = connect_feed(FakeMT5Module())
        fake = feed._terminal._module
        fake.drop_connection()
        with pytest.raises(MT5DisconnectedError):
            feed.latest_bars("EURUSD", "M1", 5)


# ════════════════════════════════════════════════════════════════════
# Framework conformance: fetch_candles / connectivity
# ════════════════════════════════════════════════════════════════════

class TestFrameworkFetchCandles:
    def test_range_query_returns_validated_candles(self):
        feed = connect_feed(FakeMT5Module())
        candles = feed.fetch_candles(
            "EURUSD",
            Timeframe.M1,
            NOW - timedelta(minutes=5),
            NOW,
        )
        assert all(isinstance(c, Candle) for c in candles)
        # fake range filter keeps opens in [NOW-5m, NOW]; generated
        # opens are NOW-30-60k → in-window: NOW-90,-150,-210,-270 (4)
        assert len(candles) == 4
        for c in candles:
            assert c.open > 0 and c.high >= c.low
            assert c.volume is not None and c.volume > 0

    def test_empty_range_is_honest_empty(self):
        feed = connect_feed(FakeMT5Module())
        candles = feed.fetch_candles(
            "EURUSD",
            Timeframe.M1,
            NOW - timedelta(days=365),
            NOW - timedelta(days=364),
        )
        assert candles == []

    def test_naive_datetimes_refused(self):
        feed = connect_feed(FakeMT5Module())
        with pytest.raises(MT5ConfigError):
            feed.fetch_candles(
                "EURUSD",
                Timeframe.M1,
                datetime(2026, 10, 23, 11, 0),
                NOW,
            )

    def test_check_connectivity_follows_terminal(self):
        feed = connect_feed(FakeMT5Module())
        assert feed.check_connectivity() is True
        feed._terminal._module.drop_connection()
        assert feed.check_connectivity() is False

    def test_fetch_instrument_info_honest_none_by_default(self):
        feed = connect_feed(FakeMT5Module())
        # asset classification is NOT derivable from symbol_info —
        # honest None rather than a fabricated Instrument
        assert feed.fetch_instrument_info("EURUSD") is None


# ════════════════════════════════════════════════════════════════════
# Ticks
# ════════════════════════════════════════════════════════════════════

class TestTicks:
    def test_latest_ticks_happy_path(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_ticks("EURUSD", 3)
        assert len(batch.ticks) == 3
        assert batch.ticks[-1].bid is not None
        assert batch.provenance.timeframe == "TICK"
        assert batch.provenance.environment == "DEMO"

    def test_empty_ticks_refused(self):
        fake = FakeMT5Module()
        make_rates_fixture(fake)
        _f, terminal, _c = make_terminal(fake)
        feed = make_feed(terminal)
        feed.connect()
        with pytest.raises(MT5NoDataError):
            feed.latest_ticks("EURUSD", 3)

    def test_stale_ticks_flagged(self):
        feed = connect_feed(FakeMT5Module())
        batch = feed.latest_ticks(
            "EURUSD", 3, max_staleness_seconds=1, stale_policy="flag"
        )
        assert batch.provenance.staleness_flagged is True


# ════════════════════════════════════════════════════════════════════
# Disconnect / reconnect / restart (DEMO re-verified every time)
# ════════════════════════════════════════════════════════════════════

class TestDisconnectReconnect:
    def test_disconnect_idempotent(self):
        feed = connect_feed(FakeMT5Module())
        feed.disconnect()
        assert feed.connected is False
        feed.disconnect()  # second call must not raise
        assert feed.connected is False

    def test_reconnect_after_drop_reverifies_demo(self):
        fake = FakeMT5Module()
        feed = connect_feed(fake)
        fake.drop_connection()
        # terminal comes back after the first post-drop health read
        orig_ti = fake.terminal_info
        reads = {"n": 0}

        def flaky_terminal_info():
            reads["n"] += 1
            if reads["n"] >= 2:
                fake.restore_connection()
            return orig_ti()

        fake.terminal_info = flaky_terminal_info
        report = feed.ensure_connected()
        assert feed.connected is True
        assert feed.reconnect_count == 1
        assert report.demo_verified is True
        # the fake was re-initialized through the full verification chain
        assert fake.initialized is True

    def test_reconnect_refuses_if_environment_changed_to_real(self):
        fake = FakeMT5Module()
        feed = connect_feed(fake)
        fake.drop_connection()
        fake.set_trade_mode(FakeMT5Module.ACCOUNT_TRADE_MODE_REAL)
        with pytest.raises(MT5ConnectError) as excinfo:
            feed.ensure_connected()
        # exhaustion after the configured attempt count, fail-closed
        assert "reconnect failed after" in str(excinfo.value)
        assert feed.connected is False

    def test_reconnect_attempts_bounded(self):
        fake = FakeMT5Module()
        feed = connect_feed(fake)
        fake.drop_connection()  # terminal stays dead → every attempt fails
        sleeps: list[float] = []
        feed._sleep = sleeps.append
        with pytest.raises(MT5ConnectError):
            feed.ensure_connected()
        assert len(sleeps) == feed._reconnect_attempts - 1


# ════════════════════════════════════════════════════════════════════
# Platform MT5Adapter require_demo hardening (defense-in-depth)
# ════════════════════════════════════════════════════════════════════

class _PlatformMockTerminal:
    def __init__(self, account: dict[str, Any]) -> None:
        self._account = account

    def account_info(self):
        return self._account

    def symbols(self):
        return {}

    def symbol_info(self, symbol):
        return None

    def copy_rates_from_pos(self, symbol, timeframe, start, count):
        return []

    def positions(self):
        return ()

    def orders(self):
        return ()


class TestPlatformRequireDemo:
    def test_require_demo_accepts_demo(self):
        terminal = _PlatformMockTerminal(
            {"login": 1, "server": "S", "broker": "B", "mode": "demo"}
        )
        adapter = MT5Adapter(terminal=terminal, require_demo=True)
        assert adapter.connect(NOW) is MT5ConnectionState.CONNECTED

    def test_require_demo_refuses_real(self):
        terminal = _PlatformMockTerminal(
            {"login": 1, "server": "S", "broker": "B", "mode": "real"}
        )
        adapter = MT5Adapter(terminal=terminal, require_demo=True)
        state = adapter.connect(NOW)
        assert state is MT5ConnectionState.ERROR
        assert "DEMO verification failed" in adapter.unavailability_reason

    def test_require_demo_refuses_unknown(self):
        terminal = _PlatformMockTerminal(
            {"login": 1, "server": "S", "broker": "B", "mode": "mystery"}
        )
        adapter = MT5Adapter(terminal=terminal, require_demo=True)
        assert adapter.connect(NOW) is MT5ConnectionState.ERROR

    def test_default_behaviour_unchanged(self):
        terminal = _PlatformMockTerminal(
            {"login": 1, "server": "S", "broker": "B", "mode": "real"}
        )
        adapter = MT5Adapter(terminal=terminal)
        assert adapter.connect(NOW) is MT5ConnectionState.CONNECTED
