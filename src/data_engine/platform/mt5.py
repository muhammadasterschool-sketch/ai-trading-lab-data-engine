"""MetaTrader 5 fail-closed adapter (platform mandate Phase F).

Contract:
- The official ``MetaTrader5`` Python package is Windows-only and
  requires a running terminal + broker account. In this environment the
  adapter is UNAVAILABLE by construction: every market-data or account
  call fails closed with ``MT5UnavailableError`` until a real terminal
  session is injected AND connectable.
- Demo and real accounts are strictly distinguished (``AccountMode``).
- Order submission is REFUSED ALWAYS: repository policy keeps live
  trading NOT AUTHORIZED and paper execution runs on the governed
  runtime simulator — the MT5 adapter is a read/market-data surface
  only. ``MT5OrderRefusedError`` documents the refusal reason.
- Real connection verification is BLOCKED_ON_OPERATOR_ENV and is never
  claimed. Tests use an injected mock terminal session.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


class MT5ConnectionState(str, Enum):
    UNAVAILABLE = "UNAVAILABLE"
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class AccountMode(str, Enum):
    DEMO = "demo"
    REAL = "real"
    UNKNOWN = "unknown"


class MT5UnavailableError(RuntimeError):
    """Raised when the terminal/package is absent or not connected."""


class MT5OrderRefusedError(RuntimeError):
    """Raised for any order submission attempt (policy refusal)."""


class MT5AccountInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    login: int
    server: str
    broker: str
    mode: AccountMode
    currency: str
    leverage: int
    balance: Optional[float] = None
    equity: Optional[float] = None


class MT5SymbolSpec(BaseModel):
    """Broker symbol specification (per-broker names differ)."""

    model_config = ConfigDict(frozen=True)

    broker_symbol: str
    description: str = ""
    contract_size: float = 1.0
    tick_size: float = 0.0
    tick_value: float = 0.0
    volume_min: float = 0.01
    volume_step: float = 0.01
    volume_max: float = 0.0
    currency: str = "USD"
    trading_sessions: tuple[tuple[str, str], ...] = ()
    supported_order_types: tuple[str, ...] = ("market",)


class MT5Candle(BaseModel):
    model_config = ConfigDict(frozen=True)

    broker_symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class MT5TerminalSession(Protocol):
    """Interface a real ``MetaTrader5`` package (or a mock) must provide."""

    def account_info(self) -> Any: ...
    def symbols(self) -> Any: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> Any: ...
    def positions(self) -> Any: ...
    def orders(self) -> Any: ...


def _detect_mt5_package() -> Optional[Any]:
    try:
        import MetaTrader5  # noqa: F401  (Windows-only)
    except Exception:
        return None
    import MetaTrader5 as mt5

    return mt5


class MT5Adapter:
    """Fail-closed MT5 adapter (market-data + reconciliation reads only)."""

    def __init__(self, terminal: Optional[MT5TerminalSession] = None) -> None:
        self._terminal = terminal
        self._state = MT5ConnectionState.DISCONNECTED if terminal else MT5ConnectionState.UNAVAILABLE
        self._account: Optional[MT5AccountInfo] = None
        self._reason = (
            "no terminal session injected and MetaTrader5 package not importable "
            "(Windows-only; BLOCKED_ON_OPERATOR_ENV: Windows terminal + broker account)"
            if terminal is None
            else "terminal session injected but not yet connected"
        )

    # -- connection --------------------------------------------------------
    @property
    def state(self) -> MT5ConnectionState:
        return self._state

    @property
    def unavailability_reason(self) -> str:
        return self._reason

    def connect(self, at: datetime, audit_log: Optional[object] = None) -> MT5ConnectionState:
        """Attempt connection; fail-closed when no injectable session exists."""
        if self._terminal is None:
            pkg = _detect_mt5_package()
            if pkg is None:
                self._state = MT5ConnectionState.UNAVAILABLE
                self._reason = (
                    "MetaTrader5 package unavailable on this platform and no "
                    "terminal session injected — adapter fails closed "
                    "(BLOCKED_ON_OPERATOR_ENV: Windows terminal + broker account)"
                )
                if audit_log is not None:
                    audit_log.record(at, "mt5", "connection_unavailable", self._reason)
                return self._state
        try:
            raw = self._terminal.account_info()
        except Exception as exc:  # noqa: BLE001 — any terminal failure is unavailable
            self._state = MT5ConnectionState.ERROR
            self._reason = f"terminal account_info failed: {exc}"
            return self._state
        self._account = self._coerce_account(raw)
        self._state = MT5ConnectionState.CONNECTED
        self._reason = ""
        if audit_log is not None:
            audit_log.record(
                at, "mt5", "connected",
                f"login={self._account.login} mode={self._account.mode.value}",
            )
        return self._state

    @staticmethod
    def _coerce_account(raw: Any) -> MT5AccountInfo:
        if isinstance(raw, MT5AccountInfo):
            return raw
        if isinstance(raw, dict):
            mode_raw = str(raw.get("mode", "unknown")).lower()
            mode = AccountMode.DEMO if "demo" in mode_raw else (
                AccountMode.REAL if "real" in mode_raw else AccountMode.UNKNOWN
            )
            return MT5AccountInfo(
                login=int(raw["login"]),
                server=str(raw.get("server", "")),
                broker=str(raw.get("broker", "")),
                mode=mode,
                currency=str(raw.get("currency", "USD")),
                leverage=int(raw.get("leverage", 0)),
                balance=raw.get("balance"),
                equity=raw.get("equity"),
            )
        raise MT5UnavailableError(f"unsupported account_info payload {type(raw)!r}")

    def _require_connected(self) -> None:
        if self._state is not MT5ConnectionState.CONNECTED:
            raise MT5UnavailableError(
                f"MT5 adapter state={self._state.value} — {self._reason or 'not connected'}; "
                "fail-closed: refusing the call"
            )

    # -- reads (market data / account / reconciliation) ------------------------
    def account_info(self) -> MT5AccountInfo:
        self._require_connected()
        assert self._account is not None
        return self._account

    def symbol_spec(self, broker_symbol: str) -> MT5SymbolSpec:
        self._require_connected()
        raw = self._terminal.symbol_info(broker_symbol)
        if raw is None:
            raise MT5UnavailableError(
                f"symbol {broker_symbol!r} not available at this broker — "
                "never assume a symbol exists"
            )
        if isinstance(raw, MT5SymbolSpec):
            return raw
        if isinstance(raw, dict):
            return MT5SymbolSpec(
                broker_symbol=str(raw.get("broker_symbol", broker_symbol)),
                description=str(raw.get("description", "")),
                contract_size=float(raw.get("contract_size", 1.0)),
                tick_size=float(raw.get("tick_size", 0.0)),
                tick_value=float(raw.get("tick_value", 0.0)),
                volume_min=float(raw.get("volume_min", 0.01)),
                volume_step=float(raw.get("volume_step", 0.01)),
                volume_max=float(raw.get("volume_max", 0.0)),
                currency=str(raw.get("currency", "USD")),
                trading_sessions=tuple(
                    (str(a), str(b)) for a, b in raw.get("trading_sessions", ())
                ),
                supported_order_types=tuple(
                    str(t) for t in raw.get("supported_order_types", ("market",))
                ),
            )
        raise MT5UnavailableError(f"unsupported symbol_info payload {type(raw)!r}")

    def candles(
        self, broker_symbol: str, timeframe: int, count: int, start: int = 0
    ) -> tuple[MT5Candle, ...]:
        self._require_connected()
        raw = self._terminal.copy_rates_from_pos(broker_symbol, timeframe, start, count)
        if not raw:
            raise MT5UnavailableError(
                f"no rates returned for {broker_symbol!r} — market closed or history "
                "unavailable; never assume availability"
            )
        out = []
        for r in raw:
            if isinstance(r, MT5Candle):
                out.append(r)
            elif isinstance(r, dict):
                out.append(
                    MT5Candle(
                        broker_symbol=broker_symbol,
                        timestamp=r["timestamp"],
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume=float(r.get("volume", 0.0)),
                    )
                )
            else:
                raise MT5UnavailableError(f"unsupported rate payload {type(r)!r}")
        return tuple(out)

    def positions(self) -> tuple[Any, ...]:
        """Read broker positions for reconciliation (permission-dependent)."""
        self._require_connected()
        result = self._terminal.positions()
        return tuple(result or ())

    def pending_orders(self) -> tuple[Any, ...]:
        self._require_connected()
        result = self._terminal.orders()
        return tuple(result or ())

    # -- execution boundary --------------------------------------------------
    def submit_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: repository policy — LIVE TRADING NOT AUTHORIZED; paper "
            "execution runs exclusively on the governed runtime simulator. "
            "The MT5 adapter is a read/market-data surface by design; a real "
            "order path would require a separate, explicitly authorized "
            "implementation and independent review."
        )

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: order modification is part of the live execution surface "
            "which is NOT AUTHORIZED in this repository"
        )

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: order cancellation is part of the live execution surface "
            "which is NOT AUTHORIZED in this repository"
        )
