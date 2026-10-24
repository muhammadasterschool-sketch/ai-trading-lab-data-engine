"""Shared fake MetaTrader5 module + fixture builders for the genuine
Exness MT5 DEMO feed tests.

This file is a TEST HELPER (not collected as a test module). The fake
mimics the real package's shapes the adapter consumes:

- module-level constants (ACCOUNT_TRADE_MODE_*, TIMEFRAME_*, COPY_TICKS_*)
- namedtuples for account_info / terminal_info / symbol_info / symbols_get
  (exactly the real package's payload style)
- list-of-dicts for copy_rates_* / copy_ticks_* (numpy structured arrays
  are covered by the conversion layer's numpy path in production; the
  dict path is shape-identical after coerce_rows)

Every order function (order_send / order_check / order_close / …) is
instrumented: any call is RECORDED and raises AssertionError — the
paper-only negative tests assert zero attempts across full workflows.
"""

from __future__ import annotations

from collections import namedtuple
from typing import Any, Optional

# ---- payload shapes (namedtuples, mirroring the real module) ------------

TerminalInfo = namedtuple(
    "TerminalInfo", "connected name build trade_allowed company"
)
AccountInfo = namedtuple(
    "AccountInfo", "login trade_mode server company currency leverage balance equity"
)
SymbolInfo = namedtuple(
    "SymbolInfo",
    "name digits point trade_contract_size currency_profit path description visible",
)

# deterministic "prices" per canonical family (5-digit FX, 2-digit metal)
_PRICE = {
    "EURUSD": 1.10432,
    "EURUSDm": 1.10432,
    "GBPUSD": 1.27210,
    "GBPUSDm": 1.27210,
    "XAUUSD": 2654.50,
    "US30": 42150.0,
}


def _tick_volume(base: int) -> int:
    return base


def make_rates(
    symbol: str,
    timeframe_seconds: int,
    count: int,
    newest_open_epoch: int,
    *,
    include_forming: bool = True,
) -> list[dict[str, Any]]:
    """Synthetic CLOSED M1-style bars, oldest first.

    ``newest_open_epoch`` is the OPEN time of the newest bar to emit.
    With ``include_forming`` the newest emitted bar is the forming one
    (its close lies in the future relative to any ``now`` before
    ``newest_open_epoch + timeframe_seconds``).
    """
    rows: list[dict[str, Any]] = []
    base = _PRICE.get(symbol.split("m")[0], 1.10000)
    for k in range(count):
        open_epoch = newest_open_epoch - k * timeframe_seconds
        drift = 0.00010 * ((k % 5) - 2) * (1.0 if "USD" in symbol else 50.0)
        o = base + drift
        c = o + 0.00005 * (1.0 if "USD" in symbol else 25.0)
        h = max(o, c) + 0.00020 * (1.0 if "USD" in symbol else 100.0)
        low = min(o, c) - 0.00020 * (1.0 if "USD" in symbol else 100.0)
        rows.append(
            {
                "time": open_epoch,
                "open": o,
                "high": h,
                "low": low,
                "close": c,
                "tick_volume": 100 + k,
                "spread": 7,
                "real_volume": 0,
            }
        )
    rows.reverse()  # oldest first (documented MT5 ordering)
    return rows


def make_ticks(
    symbol: str, count: int, newest_epoch: int, step_seconds: int = 1
) -> list[dict[str, Any]]:
    base = _PRICE.get(symbol.split("m")[0], 1.10000)
    rows = []
    for k in range(count):
        epoch = newest_epoch - (count - 1 - k) * step_seconds
        rows.append(
            {
                "time": epoch,
                "time_msc": epoch * 1000 + 123,
                "bid": base - 0.00007,
                "ask": base + 0.00007,
                "last": 0.0,
                "volume": 0,
                "flags": 0,
            }
        )
    return rows


def make_catalogue() -> dict[str, dict[str, Any]]:
    """Observed catalogue — note the Exness-style suffix on majors and
    the UNSUFFIXED metals symbol; the map must follow observation, not
    any hardcoded convention."""
    return {
        "EURUSDm": dict(
            name="EURUSDm",
            digits=5,
            point=0.00001,
            trade_contract_size=100000.0,
            currency_profit="USD",
            path="Forex\\Majors",
            description="Euro vs US Dollar",
            visible=True,
        ),
        "GBPUSDm": dict(
            name="GBPUSDm",
            digits=5,
            point=0.00001,
            trade_contract_size=100000.0,
            currency_profit="USD",
            path="Forex\\Majors",
            description="Great Britain Pound vs US Dollar",
            visible=True,
        ),
        "XAUUSD": dict(
            name="XAUUSD",
            digits=2,
            point=0.01,
            trade_contract_size=100.0,
            currency_profit="USD",
            path="Metals\\Spot",
            description="Gold vs US Dollar",
            visible=True,
        ),
        "US30": dict(
            name="US30",
            digits=1,
            point=0.1,
            trade_contract_size=1.0,
            currency_profit="USD",
            path="Indices\\US",
            description="Dow Jones Industrial Average CFD",
            visible=True,
        ),
    }


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


class FakeMT5Module:
    """Fake of the real ``MetaTrader5`` module surface (read methods +
    instrumented order functions)."""

    # constants — value-for-value what the real package declares
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408
    TIMEFRAME_W1 = 32769
    TIMEFRAME_MN1 = 49153
    COPY_TICKS_ALL = 0

    def __init__(
        self,
        *,
        trade_mode: int = 0,
        server: str = "Exness-MT5Trial8",
        company: str = "Exness",
        terminal_connected: bool = True,
        catalogue: Optional[dict[str, dict[str, Any]]] = None,
        rates: Optional[dict[tuple[str, int], list[dict[str, Any]]]] = None,
        ticks: Optional[dict[str, list[dict[str, Any]]]] = None,
        initialize_ok: bool = True,
        account_returns_none: bool = False,
        empty_catalogue: bool = False,
        corrupt_rates: bool = False,
    ) -> None:
        self._trade_mode = trade_mode
        self._server = server
        self._company = company
        self._terminal_connected = terminal_connected
        self._catalogue = catalogue if catalogue is not None else make_catalogue()
        self._rates = rates or {}
        self._ticks = ticks or {}
        self._initialize_ok = initialize_ok
        self._account_returns_none = account_returns_none
        self._empty_catalogue = empty_catalogue
        self._corrupt_rates = corrupt_rates
        self.calls: list[tuple[str, tuple, dict]] = []
        self.order_attempts: list[tuple[str, tuple, dict]] = []
        self.initialized = False
        self.initialize_kwargs: Optional[dict[str, Any]] = None
        self.shutdown_count = 0

    # -- instrumentation ---------------------------------------------------
    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    # -- order functions: RECORD + REFUSE (structural paper-only proof) -----
    def _refuse_order(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.order_attempts.append((name, args, kwargs))
        raise AssertionError(
            f"PAPER-ONLY VIOLATION: {name}() must NEVER be called by the "
            f"read-only market-data feed"
        )

    def order_send(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("order_send", *args, **kwargs)

    def order_check(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("order_check", *args, **kwargs)

    def order_close(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("order_close", *args, **kwargs)

    def positions_get(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("positions_get", *args, **kwargs)

    def history_orders_get(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("history_orders_get", *args, **kwargs)

    def history_deals_get(self, *args: Any, **kwargs: Any) -> None:
        self._refuse_order("history_deals_get", *args, **kwargs)

    # -- lifecycle -----------------------------------------------------------
    def initialize(self, **kwargs: Any) -> bool:
        self._record("initialize", **kwargs)
        self.initialize_kwargs = dict(kwargs)
        self.initialized = bool(self._initialize_ok)
        return self._initialize_ok

    def shutdown(self) -> None:
        self._record("shutdown")
        self.shutdown_count += 1
        self.initialized = False

    def last_error(self) -> tuple[int, str]:
        self._record("last_error")
        return (10009, "request completed") if self.initialized else (
            10004, "no connection"
        )

    def version(self) -> tuple[int, str, str]:
        self._record("version")
        return (4120, "20 Oct 2026", "MetaTrader 5")

    # -- account / terminal -----------------------------------------------------
    def terminal_info(self) -> TerminalInfo:
        self._record("terminal_info")
        return TerminalInfo(
            connected=self._terminal_connected,
            name="MetaTrader 5",
            build=4120,
            trade_allowed=False,
            company=self._company,
        )

    def account_info(self) -> Optional[AccountInfo]:
        self._record("account_info")
        if self._account_returns_none:
            return None
        return AccountInfo(
            login=88012345,
            trade_mode=self._trade_mode,
            server=self._server,
            company=self._company,
            currency="USD",
            leverage=100,
            balance=10000.0,
            equity=10000.0,
        )

    def set_trade_mode(self, mode: int) -> None:
        self._trade_mode = mode

    def drop_connection(self) -> None:
        self._terminal_connected = False

    def restore_connection(self) -> None:
        self._terminal_connected = True

    # -- symbols -----------------------------------------------------------------
    def symbols_total(self) -> int:
        self._record("symbols_total")
        return 0 if self._empty_catalogue else len(self._catalogue)

    def symbols_get(self) -> tuple[SymbolInfo, ...]:
        self._record("symbols_get")
        if self._empty_catalogue:
            return ()
        return tuple(
            SymbolInfo(**spec) for spec in self._catalogue.values()
        )

    def symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        self._record("symbol_info", symbol)
        spec = self._catalogue.get(symbol)
        if spec is None:
            return None
        try:
            return SymbolInfo(**spec)
        except TypeError:
            # malformed payload shape (missing namedtuple fields) —
            # surfaced raw so the adapter's own guard refuses it
            return dict(spec)

    # -- rates / ticks ------------------------------------------------------------
    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start: int, count: int
    ) -> list[dict[str, Any]]:
        self._record("copy_rates_from_pos", symbol, timeframe, start, count)
        rows = self._rates.get((symbol, timeframe), [])
        end = max(len(rows) - start, 0)
        out = rows[max(end - count, 0) : end] if rows else []
        if self._corrupt_rates and out:
            idx = len(out) // 2  # corrupt a CLOSED middle row, not the forming one
            bad = dict(out[idx])
            bad["high"] = bad["low"] - 1.0  # impossible OHLC
            out = out[:idx] + [bad] + out[idx + 1 :]
        return out

    def copy_rates_range(
        self, symbol: str, timeframe: int, date_from: Any, date_to: Any
    ) -> list[dict[str, Any]]:
        self._record("copy_rates_range", symbol, timeframe, date_from, date_to)
        rows = self._rates.get((symbol, timeframe), [])
        from_epoch = int(date_from.timestamp())
        to_epoch = int(date_to.timestamp())
        return [
            r for r in rows if from_epoch <= int(r["time"]) <= to_epoch
        ]

    def copy_ticks_from(
        self, symbol: str, date_from: Any, count: int, flags: int
    ) -> list[dict[str, Any]]:
        self._record("copy_ticks_from", symbol, date_from, count, flags)
        rows = self._ticks.get(symbol, [])
        from_epoch = int(date_from.timestamp())
        return [r for r in rows if int(r["time"]) >= from_epoch][-count:]

    def copy_ticks_range(
        self, symbol: str, date_from: Any, date_to: Any, flags: int
    ) -> list[dict[str, Any]]:
        self._record("copy_ticks_range", symbol, date_from, date_to, flags)
        rows = self._ticks.get(symbol, [])
        from_epoch = int(date_from.timestamp())
        to_epoch = int(date_to.timestamp())
        return [
            r for r in rows if from_epoch <= int(r["time"]) <= to_epoch
        ]
