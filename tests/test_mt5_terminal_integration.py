"""Genuine-terminal INTEGRATION checks — RUN ONLY on a Windows host with
the MetaTrader5 package + a running Exness DEMO terminal.

Discipline (non-negotiable):

- These checks are auto-SKIPPED with an explicit
  BLOCKED_ON_OPERATOR_ENV reason whenever the real ``MetaTrader5``
  package is not importable. They are NEVER replaced with mock results
  and NEVER reported as passed from a machine without a terminal.
- Credentials come from the environment (MT5_LOGIN / MT5_PASSWORD /
  MT5_SERVER / optional MT5_TERMINAL_PATH). They are never printed.
- A missing-credentials run is also an honest skip (NOT RUN), not a
  pass and not a failure of code under test.
- Run on the operator's Windows host:
      pytest tests/test_mt5_terminal_integration.py -v
  and archive the output under artifacts/mt5-integration/ as evidence.
"""

from __future__ import annotations

import os

import pytest

from data_engine.platform.mt5_market_data import (
    EXNESS_MT5_DEMO_PROVIDER_NAME,
    ExnessMT5DemoFeed,
)
from data_engine.platform.mt5_symbol_map import SymbolMapEntry
from data_engine.platform.mt5_terminal import (
    MT5TerminalConfig,
    load_mt5_module,
)
from data_engine.schemas import ProviderConfig

BLOCKED_REASON = (
    "BLOCKED_ON_OPERATOR_ENV: the MetaTrader5 package is not importable "
    "on this host (Windows + running terminal required) — integration "
    "checks are NOT RUN and are never mock-substituted"
)

real_module = load_mt5_module()

pytestmark = [
    pytest.mark.skipif(
        real_module is None,
        reason=BLOCKED_REASON,
    ),
]


def _credentials_available() -> bool:
    return all(
        os.environ.get(name, "").strip()
        for name in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
    )


def _make_feed() -> ExnessMT5DemoFeed:
    config = MT5TerminalConfig.from_env()
    cfg = ProviderConfig(
        provider_name=EXNESS_MT5_DEMO_PROVIDER_NAME,
        provider_type="broker-terminal",
    )
    probe_symbol = os.environ.get("MT5_PROBE_SYMBOL", "EURUSD")
    return ExnessMT5DemoFeed(
        cfg,
        terminal_config=config,
        symbol_map_proposals=(
            SymbolMapEntry(
                canonical=probe_symbol, broker_symbol=probe_symbol
            ),
        ),
    )


@pytest.fixture(scope="module")
def connected_feed():
    if not _credentials_available():
        pytest.skip(
            "BLOCKED_ON_OPERATOR_ENV: MT5_LOGIN/MT5_PASSWORD/MT5_SERVER "
            "not exported — probe NOT RUN (never a mock substitution)"
        )
    feed = _make_feed()
    feed.connect()
    yield feed
    feed.disconnect()


def test_real_connect_positively_verifies_demo(connected_feed):
    health = connected_feed.health_check()
    assert health.demo_verified is True
    assert health.trade_mode_observed == "DEMO"
    assert health.terminal_connected is True


def test_real_symbol_catalogue_observed(connected_feed):
    rows = connected_feed.symbol_catalogue()
    assert len(rows) > 0
    assert all("name" in r for r in rows)


def test_real_latest_bars_observed(connected_feed):
    symbol = os.environ.get("MT5_PROBE_SYMBOL", "EURUSD")
    batch = connected_feed.latest_bars(
        symbol, "M1", 5, stale_policy="flag"
    )
    assert len(batch.bars) >= 1
    prov = batch.provenance
    assert prov.environment == "DEMO"
    assert prov.row_count == len(batch.bars)
    assert len(prov.payload_sha256) == 64


def test_real_latest_ticks_observed(connected_feed):
    symbol = os.environ.get("MT5_PROBE_SYMBOL", "EURUSD")
    batch = connected_feed.latest_ticks(
        symbol, 5, stale_policy="flag"
    )
    assert len(batch.ticks) >= 1


def test_real_disconnect_is_clean(connected_feed):
    assert connected_feed.connected is True
    connected_feed.disconnect()
    assert connected_feed.connected is False
