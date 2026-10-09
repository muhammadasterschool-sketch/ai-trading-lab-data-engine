"""Platform package tests — MT5 fail-closed adapter (Phase F).

The real ``MetaTrader5`` package is Windows-only and no terminal exists
in this environment: these tests verify the ADAPTER CONTRACT with an
injected mock terminal session, exactly the mocked-external-service
discipline the mandate requires. No real broker is contacted, ever.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from data_engine.platform import (
    AccountMode,
    AuditLog,
    MT5AccountInfo,
    MT5Adapter,
    MT5ConnectionState,
    MT5Candle,
    MT5OrderRefusedError,
    MT5SymbolSpec,
    MT5UnavailableError,
)

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


class MockTerminal:
    """Mock of the MetaTrader5 module surface the adapter consumes."""

    def __init__(
        self,
        account: Any = None,
        symbols: dict[str, Any] | None = None,
        rates: dict[str, list[MT5Candle]] | None = None,
        fail_account: bool = False,
    ) -> None:
        self._account = account or {
            "login": 12345,
            "server": "BrokerX-Demo",
            "broker": "BrokerX",
            "mode": "demo",
            "currency": "USD",
            "leverage": 100,
            "balance": 10000.0,
            "equity": 10010.0,
        }
        self._symbols = symbols or {}
        self._rates = rates or {}
        self._fail_account = fail_account

    def account_info(self) -> Any:
        if self._fail_account:
            raise RuntimeError("terminal not running")
        return self._account

    def symbols(self) -> Any:
        return tuple(self._symbols)

    def symbol_info(self, symbol: str) -> Any:
        return self._symbols.get(symbol)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> Any:
        rows = self._rates.get(symbol, ())
        window = rows[start : start + count]
        return window or None

    def positions(self) -> Any:
        return ()

    def orders(self) -> Any:
        return ()


def _candle(ts_min: int, o: float, h: float, low: float, c: float) -> MT5Candle:
    return MT5Candle(
        broker_symbol="XAUUSD",
        timestamp=T0 + timedelta(minutes=ts_min),
        open=o, high=h, low=low, close=c,
    )


class TestConnectionStates:
    def test_no_terminal_is_unavailable(self):
        adapter = MT5Adapter()
        assert adapter.state is MT5ConnectionState.UNAVAILABLE
        assert "BLOCKED_ON_OPERATOR_ENV" in adapter.unavailability_reason

    def test_connect_without_terminal_fails_closed(self):
        adapter = MT5Adapter()
        log = AuditLog()
        state = adapter.connect(at=T0, audit_log=log)
        assert state is MT5ConnectionState.UNAVAILABLE
        assert log.events()[0].event == "connection_unavailable"

    def test_connect_with_mock_terminal_succeeds(self):
        adapter = MT5Adapter(terminal=MockTerminal())
        state = adapter.connect(at=T0)
        assert state is MT5ConnectionState.CONNECTED

    def test_account_failure_transitions_to_error(self):
        adapter = MT5Adapter(terminal=MockTerminal(fail_account=True))
        state = adapter.connect(at=T0)
        assert state is MT5ConnectionState.ERROR


class TestAccountModeDiscipline:
    def test_demo_account_detected(self):
        adapter = MT5Adapter(terminal=MockTerminal())
        adapter.connect(at=T0)
        info = adapter.account_info()
        assert info.mode is AccountMode.DEMO

    def test_real_account_detected(self):
        real = {"login": 1, "server": "BrokerX-Live", "mode": "real", "leverage": 100}
        adapter = MT5Adapter(terminal=MockTerminal(account=real))
        adapter.connect(at=T0)
        assert adapter.account_info().mode is AccountMode.REAL

    def test_unreadable_mode_is_unknown_never_assumed(self):
        odd = {"login": 1, "server": "s", "mode": "contestsomething", "leverage": 100}
        adapter = MT5Adapter(terminal=MockTerminal(account=odd))
        adapter.connect(at=T0)
        assert adapter.account_info().mode is AccountMode.UNKNOWN

    def test_direct_account_info_object_passes_through(self):
        info = MT5AccountInfo(
            login=9, server="s", broker="b", mode=AccountMode.DEMO,
            currency="USD", leverage=100,
        )
        adapter = MT5Adapter(terminal=MockTerminal(account=info))
        adapter.connect(at=T0)
        assert adapter.account_info() == info


class TestReadsFailClosed:
    def test_all_reads_refused_before_connect(self):
        adapter = MT5Adapter(terminal=MockTerminal())
        with pytest.raises(MT5UnavailableError, match="fail-closed"):
            adapter.account_info()
        with pytest.raises(MT5UnavailableError, match="fail-closed"):
            adapter.symbol_spec("XAUUSD")
        with pytest.raises(MT5UnavailableError, match="fail-closed"):
            adapter.candles("XAUUSD", timeframe=1440, count=10)
        with pytest.raises(MT5UnavailableError, match="fail-closed"):
            adapter.positions()
        with pytest.raises(MT5UnavailableError, match="fail-closed"):
            adapter.pending_orders()

    def test_unknown_symbol_refused(self):
        adapter = MT5Adapter(terminal=MockTerminal())
        adapter.connect(at=T0)
        with pytest.raises(MT5UnavailableError, match="not available at this broker"):
            adapter.symbol_spec("NOPE")

    def test_symbol_spec_roundtrip(self):
        spec = MT5SymbolSpec(
            broker_symbol="XAUUSD", contract_size=100.0, tick_size=0.01,
            tick_value=1.0, volume_min=0.01, volume_step=0.01, volume_max=20.0,
        )
        adapter = MT5Adapter(terminal=MockTerminal(symbols={"XAUUSD": spec}))
        adapter.connect(at=T0)
        assert adapter.symbol_spec("XAUUSD") == spec

    def test_candles_roundtrip_in_order(self):
        candles = [_candle(0, 2350.0, 2360.0, 2345.0, 2355.0), _candle(1, 2355.0, 2370.0, 2351.0, 2365.0)]
        adapter = MT5Adapter(terminal=MockTerminal(rates={"XAUUSD": candles}))
        adapter.connect(at=T0)
        out = adapter.candles("XAUUSD", timeframe=1440, count=2)
        assert out == tuple(candles)

    def test_no_history_refused(self):
        adapter = MT5Adapter(terminal=MockTerminal(rates={"XAUUSD": []}))
        adapter.connect(at=T0)
        with pytest.raises(MT5UnavailableError, match="no rates returned"):
            adapter.candles("XAUUSD", timeframe=1440, count=5)


class TestExecutionBoundary:
    @pytest.mark.parametrize(
        "method",
        ["submit_order", "modify_order", "cancel_order"],
    )
    def test_order_surface_refused_always(self, method):
        adapter = MT5Adapter(terminal=MockTerminal())
        adapter.connect(at=T0)
        with pytest.raises(MT5OrderRefusedError, match="NOT AUTHORIZED"):
            getattr(adapter, method)(symbol="XAUUSD", volume=0.1)

    def test_refusal_survives_connected_real_account(self):
        real = {"login": 1, "server": "BrokerX-Live", "mode": "real", "leverage": 100}
        adapter = MT5Adapter(terminal=MockTerminal(account=real))
        adapter.connect(at=T0)
        with pytest.raises(MT5OrderRefusedError, match="NOT AUTHORIZED"):
            adapter.submit_order(symbol="XAUUSD", volume=0.1)
