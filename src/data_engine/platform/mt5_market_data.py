"""Genuine Exness MT5 DEMO market-data feed — READ-ONLY, paper-only.

The genuine counterpart of the crypto pilot
(:mod:`data_engine.providers.binance_public`): real market data from a
REAL MetaTrader 5 terminal through the official ``MetaTrader5`` Python
package (Windows-only), against a POSITIVELY VERIFIED DEMO account.

Structural guarantees (mirror of the binance pilot's guarantees, plus
the MT5-specific ones):

- **Framework conformance, not a second framework** — subclasses
  :class:`data_engine.provider.MarketDataProvider`, returns
  schema-validated :class:`data_engine.schemas.Candle` objects and
  registers with :class:`data_engine.provider.ProviderFactory` under
  ``"exness-mt5-demo"``.
- **Injectable terminal boundary** — all terminal behaviour lives in
  :mod:`data_engine.platform.mt5_terminal`; every method below that
  boundary is pure parsing/validation. Unit tests inject a fake
  module — no terminal, no network, no broker in CI.
- **Positive DEMO verification (fail closed)** — a connection is only
  established when the terminal reports connected AND the observed
  ``account_info().trade_mode`` EQUALS the installed module's
  ``ACCOUNT_TRADE_MODE_DEMO`` constant. REAL, CONTEST, unknown and
  unverifiable accounts are refused. Every reconnect re-verifies.
- **No order path. Nothing to bypass.** The feed exposes market data
  only. Its ``submit_order``/``modify_order``/``cancel_order`` methods
  exist ONLY to raise :class:`MT5OrderRefusedError` (the exact pattern
  of :mod:`data_engine.platform.mt5.py`); the terminal boundary's read
  allowlist makes every other trade function unreachable. Strategy
  output keeps flowing exclusively to the governed internal paper
  broker/simulator; this feed can never route anywhere else because it
  has no routing surface at all.
- **No fabrication, no assumption** — empty terminal answers surface
  structured errors; broker symbols and contract specifications enter
  the feed ONLY through :mod:`data_engine.platform.mt5_symbol_map`
  (observed + digest-stamped + re-verified at every connect).
- **Freshness is explicit** — latest-data reads carry a
  configurable staleness threshold (raise or flag); historical range
  queries are explicitly historical and never freshness-claimed.
- **Provenance per batch** — venue server, terminal build, company,
  verified environment, row counts, first/last timestamps, staleness
  age and a payload SHA-256 travel with every batch.
- **Credentials stay outside the repository** — env-only
  (:class:`~data_engine.platform.mt5_terminal.MT5TerminalConfig`),
  ``SecretStr`` password, never rendered, never logged, never written.

Governance: this module changes NO readiness gate. The feed starts
UNAPPROVED; operator source approval, model registration, real-data
verification and operational-feed evidence remain exactly where they
were. ``PAPER_READY`` stays FALSE; ``LIVE_AUTHORIZATION`` stays
NOT_AUTHORIZED; the 30-day soak and its preflight are untouched.
"""

from __future__ import annotations

import hashlib
import json
import time as _time
from datetime import datetime, UTC, timedelta
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from data_engine.provider import MarketDataProvider, ProviderFactory
from data_engine.platform.mt5 import MT5OrderRefusedError
from data_engine.platform.mt5_symbol_map import (
    MT5SymbolMap,
    SymbolMapEntry,
    ValidatedSymbolEntry,
)
from data_engine.platform.mt5_terminal import (
    MT5TerminalConfig,
    MT5TerminalError,
    RealMT5Terminal,
    to_utc_datetime,
)
from data_engine.schemas import Candle, Instrument, ProviderConfig, Timeframe

__all__ = [
    "EXNESS_MT5_DEMO_PROVIDER_NAME",
    "MT5MarketDataError",
    "MT5ModuleUnavailableError",
    "MT5ConnectError",
    "MT5DemoVerificationError",
    "MT5ServerMismatchError",
    "MT5SymbolNotFoundError",
    "MT5NoDataError",
    "MT5StaleDataError",
    "MT5DisconnectedError",
    "MT5ConfigError",
    "MT5Bar",
    "MT5Tick",
    "MT5BarBatch",
    "MT5TickBatch",
    "MT5FeedProvenance",
    "MT5HealthReport",
    "ExnessMT5DemoFeed",
]

EXNESS_MT5_DEMO_PROVIDER_NAME = "exness-mt5-demo"

#: Framework Timeframe value → MT5 timeframe name.
_TIMEFRAME_TO_MT5 = {
    Timeframe.M1.value: "M1",
    Timeframe.M5.value: "M5",
    Timeframe.M15.value: "M15",
    Timeframe.H1.value: "H1",
    Timeframe.H4.value: "H4",
    Timeframe.D1.value: "D1",
}

#: Nominal bar duration per MT5 timeframe NAME (our own constant — used
#: ONLY for closed-bar detection and freshness thresholds; the
#: module's timeframe INTEGERS are always resolved from the installed
#: package itself, never copied here). MN1 is approximated at 30 days
#: and documented as such.
_TF_NOMINAL_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
    "W1": 604800,
    "MN1": 2_592_000,  # ~30 days, approximation for freshness only
}

DEFAULT_MAX_STALENESS_SECONDS = 300
DEFAULT_TICK_LOOKBACK_SECONDS = 3600
DEFAULT_RECONNECT_ATTEMPTS = 3
DEFAULT_RECONNECT_BACKOFF_SECONDS = 1.0
_MAX_BACKOFF_SECONDS = 8.0


# ════════════════════════════════════════════════════════════════════
# Structured errors (stable codes; never leak credential values)
# ════════════════════════════════════════════════════════════════════

class MT5MarketDataError(RuntimeError):
    """Base class for genuine-feed failures (fail closed)."""

    code = "MT5_E_FEED"


class MT5ModuleUnavailableError(MT5MarketDataError):
    """MetaTrader5 package/terminal absent (Windows-only runtime)."""

    code = "MT5_E_MODULE_UNAVAILABLE"


class MT5ConnectError(MT5MarketDataError):
    """Terminal not connected / connect refused."""

    code = "MT5_E_CONNECT"


class MT5DemoVerificationError(MT5MarketDataError):
    """Connection refused: account could not be POSITIVELY verified DEMO."""

    code = "MT5_E_NOT_DEMO_VERIFIED"


class MT5ServerMismatchError(MT5MarketDataError):
    """Observed server does not match the operator-expected server."""

    code = "MT5_E_SERVER_MISMATCH"


class MT5SymbolNotFoundError(MT5MarketDataError):
    """Requested symbol is not observed on the connected terminal."""

    code = "MT5_E_SYMBOL_NOT_FOUND"


class MT5NoDataError(MT5MarketDataError):
    """Terminal answered with no data (market closed / history gap)."""

    code = "MT5_E_NO_DATA"


class MT5StaleDataError(MT5MarketDataError):
    """Latest data older than the configured staleness threshold."""

    code = "MT5_E_STALE_DATA"

    def __init__(
        self,
        detail: str,
        *,
        age_seconds: float,
        threshold_seconds: int,
        last_close_epoch: int,
    ) -> None:
        super().__init__(
            f"{self.code}: {detail} (age={age_seconds:.0f}s > "
            f"threshold={threshold_seconds}s; last close epoch "
            f"{last_close_epoch}) — markets may be closed; raise or "
            f"flag via stale_policy, never silently accept"
        )
        self.age_seconds = age_seconds
        self.threshold_seconds = threshold_seconds
        self.last_close_epoch = last_close_epoch


class MT5DisconnectedError(MT5MarketDataError):
    """Operation attempted while the feed is not connected/verified."""

    code = "MT5_E_DISCONNECTED"


class MT5ConfigError(MT5MarketDataError):
    """Invalid feed configuration (timeframe name, thresholds…)."""

    code = "MT5_E_CONFIG"


# ════════════════════════════════════════════════════════════════════
# Frozen models: bars, ticks, provenance, health
# ════════════════════════════════════════════════════════════════════

class MT5Bar(BaseModel):
    """One OBSERVED OHLC bar straight from the terminal (never invented)."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    broker_symbol: str
    #: Bar OPEN time, aware UTC (coerced from the terminal's epoch).
    timestamp: datetime
    raw_time_epoch: int = Field(..., description="terminal epoch seconds, verbatim")
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0
    real_volume: float = 0.0
    spread: int = 0

    @property
    def close_epoch(self) -> int:
        return self.raw_time_epoch


class MT5Tick(BaseModel):
    """One OBSERVED tick straight from the terminal."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    broker_symbol: str
    timestamp: datetime
    raw_time_epoch: int
    time_msc: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[float] = None


def _batch_sha(rows: tuple[BaseModel, ...]) -> str:
    payload = json.dumps(
        [r.model_dump(mode="json") for r in rows],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MT5FeedProvenance(BaseModel):
    """Per-batch provenance — the feed never returns data without it."""

    model_config = ConfigDict(frozen=True)

    source_name: str = EXNESS_MT5_DEMO_PROVIDER_NAME
    environment: str = Field(
        ..., description="positively verified account environment (DEMO)"
    )
    demo_verified_at: datetime
    venue_server: str
    terminal_name: str
    terminal_build: str
    broker_company: str
    canonical: str
    broker_symbol: str
    timeframe: str
    row_count: int
    first_epoch: Optional[int] = None
    last_epoch: Optional[int] = None
    staleness_seconds: Optional[float] = None
    staleness_flagged: bool = False
    closed_only: bool = True
    payload_sha256: str
    retrieved_at_utc: datetime
    note: str = (
        "MT5 bar/tick times are broker-server epoch values carried "
        "verbatim; freshness thresholds are operator-configured"
    )


class MT5BarBatch(BaseModel):
    """Bars + mandatory provenance (atomic pair)."""

    model_config = ConfigDict(frozen=True)

    bars: tuple[MT5Bar, ...]
    provenance: MT5FeedProvenance

    @classmethod
    def build(cls, bars: tuple[MT5Bar, ...], **prov: Any) -> "MT5BarBatch":
        return cls(
            bars=bars,
            provenance=MT5FeedProvenance(
                payload_sha256=_batch_sha(bars), **prov
            ),
        )


class MT5TickBatch(BaseModel):
    """Ticks + mandatory provenance (atomic pair)."""

    model_config = ConfigDict(frozen=True)

    ticks: tuple[MT5Tick, ...]
    provenance: MT5FeedProvenance

    @classmethod
    def build(cls, ticks: tuple[MT5Tick, ...], **prov: Any) -> "MT5TickBatch":
        return cls(
            ticks=ticks,
            provenance=MT5FeedProvenance(
                payload_sha256=_batch_sha(ticks), **prov
            ),
        )


class MT5HealthReport(BaseModel):
    """Credential-free health snapshot of the genuine feed."""

    model_config = ConfigDict(frozen=True)

    state: str
    module_available: bool
    terminal_connected: Optional[bool] = None
    terminal_name: str = ""
    terminal_build: str = ""
    venue_server: str = ""
    broker_company: str = ""
    account_currency: str = ""
    leverage: Optional[int] = None
    trade_mode_observed: Optional[str] = None
    demo_verified: bool = False
    demo_verified_at: Optional[datetime] = None
    symbol_map_size: int = 0
    reconnect_count: int = 0
    module_last_error: Optional[str] = None


class _AuditLike(Protocol):
    def record(self, at: datetime, actor: str, event: str, detail: str) -> None: ...


class _TerminalForFeed(Protocol):
    """Narrow terminal surface the feed consumes (read-only)."""

    def initialize(self) -> None: ...
    def shutdown(self) -> None: ...
    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def symbols_get(self) -> list[dict[str, Any]]: ...
    def symbol_info(self, symbol: str) -> Optional[dict[str, Any]]: ...
    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start: int, count: int
    ) -> list[dict[str, Any]]: ...
    def copy_rates_range(
        self, symbol: str, timeframe: int, date_from: datetime, date_to: datetime
    ) -> list[dict[str, Any]]: ...
    def copy_ticks_from(
        self, symbol: str, date_from: datetime, count: int, flags: int
    ) -> list[dict[str, Any]]: ...
    def last_error(self) -> tuple[int, str]: ...
    def version(self) -> str: ...
    def timeframe_constant(self, timeframe_name: str) -> int: ...
    def tick_flag_constant(self, flag_name: str) -> int: ...
    def account_trade_mode_constant(self, mode_name: str) -> int: ...


# ════════════════════════════════════════════════════════════════════
# The genuine feed
# ════════════════════════════════════════════════════════════════════

class ExnessMT5DemoFeed(MarketDataProvider):
    """Genuine read-only Exness MT5 DEMO market-data feed.

    Construct with ``terminal=None`` for the real runtime path (the
    terminal is built lazily at ``connect()`` from the env-backed
    config). Tests inject a fake module-backed terminal instead —
    identical code path, no Windows requirement.
    """

    def __init__(
        self,
        config: ProviderConfig,
        registry: Optional[Any] = None,
        terminal: Optional[_TerminalForFeed] = None,
        terminal_config: Optional[MT5TerminalConfig] = None,
        validated_symbol_map: Optional[MT5SymbolMap] = None,
        symbol_map_proposals: Optional[tuple[SymbolMapEntry, ...]] = None,
        symbol_map_path: Optional[str] = None,
        closed_only: bool = True,
        max_staleness_seconds: int = DEFAULT_MAX_STALENESS_SECONDS,
        reconnect_attempts: int = DEFAULT_RECONNECT_ATTEMPTS,
        reconnect_backoff_seconds: float = DEFAULT_RECONNECT_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = _time.sleep,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        audit_log: Optional[_AuditLike] = None,
        instrument_factory: Optional[
            Callable[[str, ValidatedSymbolEntry], Optional[Instrument]]
        ] = None,
    ) -> None:
        super().__init__(config, registry)
        if max_staleness_seconds < 0:
            raise MT5ConfigError(
                "MT5_E_CONFIG: max_staleness_seconds must be >= 0 "
                "(0 disables freshness enforcement — explicit, honest)"
            )
        if reconnect_attempts < 1:
            raise MT5ConfigError(
                "MT5_E_CONFIG: reconnect_attempts must be >= 1"
            )
        self._terminal = terminal
        self._terminal_config = terminal_config
        self._validated_map = validated_symbol_map
        self._proposals = symbol_map_proposals
        self._map_path = symbol_map_path
        self._closed_only = closed_only
        self._max_staleness = max_staleness_seconds
        self._reconnect_attempts = reconnect_attempts
        self._backoff = reconnect_backoff_seconds
        self._sleep = sleep
        self._clock = clock
        self._audit = audit_log
        self._instrument_factory = instrument_factory
        # connection state
        self._connected = False
        self._demo_verified_at: Optional[datetime] = None
        self._account: dict[str, Any] = {}
        self._terminal_meta: dict[str, Any] = {}
        self._symbol_map: Optional[MT5SymbolMap] = None
        self._reconnect_count = 0

    # -- state -----------------------------------------------------------
    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def demo_verified_at(self) -> Optional[datetime]:
        return self._demo_verified_at

    @property
    def symbol_map(self) -> Optional[MT5SymbolMap]:
        return self._symbol_map

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    def _now(self) -> datetime:
        return self._clock()

    def _audit_event(self, event: str, detail: str) -> None:
        if self._audit is not None:
            self._audit.record(self._now(), EXNESS_MT5_DEMO_PROVIDER_NAME, event, detail)

    def _require_connected(self) -> None:
        if not self._connected or self._symbol_map is None:
            raise MT5DisconnectedError(
                "MT5_E_DISCONNECTED: feed is not connected/verified — "
                "call connect() first; fail-closed"
            )
        # live liveness check: a mid-session terminal drop must surface
        # as a structured disconnect, never as silent empty data
        tinfo = self._terminal.terminal_info()
        if getattr(tinfo, "connected", None) is not True:
            self._connected = False
            raise MT5DisconnectedError(
                "MT5_E_DISCONNECTED: terminal reports disconnected "
                "mid-session — refusing the read (reconnect via "
                "ensure_connected(), which re-verifies DEMO)"
            )

    def _get_terminal(self) -> _TerminalForFeed:
        if self._terminal is None:
            cfg = self._terminal_config
            if cfg is None:
                cfg = MT5TerminalConfig.from_env()
            self._terminal = RealMT5Terminal(cfg)
        return self._terminal

    # -- connection / verification ------------------------------------------
    def connect(self, at: Optional[datetime] = None) -> MT5HealthReport:
        """Connect, POSITIVELY verify DEMO, validate the symbol map.

        Refuses (structured error, state unchanged→disconnected) unless
        EVERY step passes: terminal initialize → terminal_info().connected
        → account_info() readable → trade_mode == module's DEMO constant
        → optional expected-server match → symbol map observed/digest-
        re-verified.
        """
        when = at or self._now()
        terminal = self._get_terminal()
        if not terminal.module_available:
            raise MT5ModuleUnavailableError(
                "MT5_E_MODULE_UNAVAILABLE: the MetaTrader5 package is "
                "not importable here (Windows-only) — the genuine feed "
                "fails closed; it is NEVER substituted with mock data"
            )
        try:
            terminal.initialize()
        except MT5TerminalError:
            self._connected = False
            raise
        tinfo = terminal.terminal_info()
        if getattr(tinfo, "connected", None) is not True:
            code, description = terminal.last_error()
            raise MT5ConnectError(
                f"MT5_E_CONNECT: terminal reports connected="
                f"{getattr(tinfo, 'connected', None)!r} "
                f"(module last_error {code}: {description})"
            )
        account = self._verify_demo(terminal, when)
        self._verify_server(account)
        symbol_map = self._resolve_symbol_map(terminal, when)
        # commit state
        self._connected = True
        self._demo_verified_at = when
        self._account = account
        self._symbol_map = symbol_map
        self._terminal_meta = self._collect_terminal_meta(terminal)
        self._audit_event(
            "connected",
            f"environment=DEMO server={self._account.get('server', '')!r} "
            f"build={self._terminal_meta.get('build', '')!r} "
            f"symbols_mapped={len(symbol_map)}",
        )
        return self.health_check()

    def _verify_demo(self, terminal: _TerminalForFeed, when: datetime) -> dict[str, Any]:
        """POSITIVE DEMO verification against the module's own constant."""
        account_obj = terminal.account_info()
        if account_obj is None:
            code, description = terminal.last_error()
            raise MT5DemoVerificationError(
                f"MT5_E_NOT_DEMO_VERIFIED: account_info() returned None — "
                f"the account environment cannot be positively verified "
                f"(module last_error {code}: {description}); refusing "
                f"the connection"
            )
        trade_mode = getattr(account_obj, "trade_mode", None)
        if trade_mode is None:
            raise MT5DemoVerificationError(
                "MT5_E_NOT_DEMO_VERIFIED: observed account carries no "
                "trade_mode — the environment cannot be positively "
                "verified; refusing (fail-closed)"
            )
        demo_const = terminal.account_trade_mode_constant(
            "ACCOUNT_TRADE_MODE_DEMO"
        )
        real_const = terminal.account_trade_mode_constant(
            "ACCOUNT_TRADE_MODE_REAL"
        )
        contest_const = terminal.account_trade_mode_constant(
            "ACCOUNT_TRADE_MODE_CONTEST"
        )
        observed = int(trade_mode)
        if observed == real_const:
            raise MT5DemoVerificationError(
                "MT5_E_NOT_DEMO_VERIFIED: observed account is a REAL "
                "account — REFUSED. This repository is paper-only; "
                "live trading is NOT AUTHORIZED"
            )
        if observed == contest_const:
            raise MT5DemoVerificationError(
                "MT5_E_NOT_DEMO_VERIFIED: observed account is a CONTEST "
                "account — not a verified DEMO environment; refusing"
            )
        if observed != demo_const:
            raise MT5DemoVerificationError(
                f"MT5_E_NOT_DEMO_VERIFIED: observed trade_mode={observed} "
                f"does not equal the module's DEMO constant "
                f"({demo_const}) — environment unverifiable; refusing"
            )
        return {
            "login": getattr(account_obj, "login", None),
            "server": str(getattr(account_obj, "server", "") or ""),
            "company": str(getattr(account_obj, "company", "") or ""),
            "currency": str(getattr(account_obj, "currency", "") or ""),
            "leverage": getattr(account_obj, "leverage", None),
            "balance": getattr(account_obj, "balance", None),
            "trade_mode": "DEMO",
        }

    def _verify_server(self, account: dict[str, Any]) -> None:
        expected: Optional[str] = None
        if self._terminal_config is not None:
            expected = self._terminal_config.expected_server_substring
        elif self._terminal is not None:
            cfg = getattr(self._terminal, "config", None)
            expected = getattr(cfg, "expected_server_substring", None)
        if expected:
            observed_server = account.get("server", "")
            if expected.strip().lower() not in observed_server.lower():
                raise MT5ServerMismatchError(
                    f"MT5_E_SERVER_MISMATCH: observed server "
                    f"{observed_server!r} does not match the operator "
                    f"expectation — refusing (never trade/connect on an "
                    f"unexpected server)"
                )

    def _resolve_symbol_map(
        self, terminal: _TerminalForFeed, when: datetime
    ) -> MT5SymbolMap:
        if self._validated_map is not None:
            self._validated_map.recheck(terminal)
            return self._validated_map
        if self._proposals:
            return MT5SymbolMap.validate(self._proposals, terminal, when)
        if self._map_path:
            from pathlib import Path

            text = Path(self._map_path).read_text(encoding="utf-8")
            loaded = MT5SymbolMap.load_json(text)
            loaded.recheck(terminal)
            return loaded
        raise MT5ConfigError(
            "MT5_E_CONFIG: no symbol map provided — the genuine feed "
            "never assumes broker symbol names. Author a proposal after "
            "'data-engine mt5-probe --dump-catalogue', then validate it "
            "against the live terminal (see the operator runbook)"
        )

    def _collect_terminal_meta(self, terminal: _TerminalForFeed) -> dict[str, Any]:
        tinfo = terminal.terminal_info()
        return {
            "name": str(getattr(tinfo, "name", "") or ""),
            "build": str(getattr(tinfo, "build", "") or ""),
            "company": str(getattr(tinfo, "company", "") or ""),
            "version": terminal.version(),
        }

    # -- health ---------------------------------------------------------------
    def health_check(self, at: Optional[datetime] = None) -> MT5HealthReport:
        """Credential-free health snapshot (never raises for state)."""
        when = at or self._now()
        module_available = True
        terminal_connected: Optional[bool] = None
        module_last_error: Optional[str] = None
        trade_mode_observed: Optional[str] = None
        if self._connected and self._terminal is not None:
            try:
                tinfo = self._terminal.terminal_info()
                terminal_connected = getattr(tinfo, "connected", None) is True
                account = self._terminal.account_info()
                mode = getattr(account, "trade_mode", None)
                if mode is not None and self._terminal.module_available:
                    demo_const = self._terminal.account_trade_mode_constant(
                        "ACCOUNT_TRADE_MODE_DEMO"
                    )
                    trade_mode_observed = (
                        "DEMO" if int(mode) == demo_const else str(int(mode))
                    )
            except MT5TerminalError as exc:
                terminal_connected = False
                module_last_error = str(exc)
        elif self._terminal is not None:
            module_available = self._terminal.module_available
        else:
            module_available = False
        return MT5HealthReport(
            state="CONNECTED" if self._connected else "DISCONNECTED",
            module_available=module_available,
            terminal_connected=terminal_connected,
            terminal_name=str(self._terminal_meta.get("name", "")),
            terminal_build=str(self._terminal_meta.get("build", "")),
            venue_server=str(self._account.get("server", "")),
            broker_company=str(self._account.get("company", "")),
            account_currency=str(self._account.get("currency", "")),
            leverage=self._account.get("leverage"),
            trade_mode_observed=trade_mode_observed,
            demo_verified=self._connected and self._demo_verified_at is not None,
            demo_verified_at=self._demo_verified_at,
            symbol_map_size=len(self._symbol_map) if self._symbol_map else 0,
            reconnect_count=self._reconnect_count,
            module_last_error=module_last_error,
        )

    # -- symbol catalogue ---------------------------------------------------------
    def symbol_catalogue(self) -> tuple[dict[str, Any], ...]:
        """The OBSERVED symbol catalogue (verbatim dict rows)."""
        self._require_connected()
        rows = self._terminal.symbols_get()
        if not rows:
            raise MT5NoDataError(
                "MT5_E_NO_DATA: the terminal returned an empty symbol "
                "catalogue — refusing to pretend otherwise"
            )
        return tuple(rows)

    def symbol_specification(self, canonical: str) -> ValidatedSymbolEntry:
        """Validated mapping + observed spec for one canonical symbol."""
        self._require_connected()
        return self._symbol_map.resolve(canonical)

    # -- bars -------------------------------------------------------------------
    def latest_bars(
        self,
        canonical: str,
        timeframe: str,
        count: int,
        *,
        closed_only: Optional[bool] = None,
        max_staleness_seconds: Optional[int] = None,
        stale_policy: str = "raise",
        at: Optional[datetime] = None,
    ) -> MT5BarBatch:
        """Latest OBSERVED bars with closed-bar filtering + freshness.

        ``stale_policy="raise"`` (default) raises
        :class:`MT5StaleDataError` when the newest CLOSED bar is older
        than the threshold (e.g. market closed over a weekend);
        ``"flag"`` returns the batch with the staleness recorded in
        provenance — never a silent acceptance.
        """
        self._require_connected()
        if count < 1:
            raise MT5ConfigError("MT5_E_CONFIG: count must be >= 1")
        if stale_policy not in ("raise", "flag"):
            raise MT5ConfigError(
                "MT5_E_CONFIG: stale_policy must be 'raise' or 'flag'"
            )
        tf_name = (timeframe or "").strip().upper()
        tf_seconds = _TF_NOMINAL_SECONDS.get(tf_name)
        if tf_seconds is None:
            raise MT5ConfigError(
                f"MT5_E_CONFIG: unknown timeframe {timeframe!r} — "
                f"supported: {sorted(_TF_NOMINAL_SECONDS)}"
            )
        entry = self._symbol_map.resolve(canonical)
        tf_const = self._terminal.timeframe_constant(tf_name)
        # fetch one extra row so the forming bar can be identified and
        # excluded without reducing the requested count
        rows = self._terminal.copy_rates_from_pos(
            entry.broker_symbol, tf_const, 0, count + 1
        )
        if not rows:
            raise MT5NoDataError(
                f"MT5_E_NO_DATA: no rates returned for broker symbol "
                f"{entry.broker_symbol!r} — market closed or history "
                f"unavailable; never fabricated"
            )
        rows = sorted(rows, key=lambda r: int(r["time"]))
        now = at or self._now()
        now_epoch = int(now.timestamp())
        closed = closed_only if closed_only is not None else self._closed_only
        if closed:
            rows = [
                r
                for r in rows
                if int(r["time"]) + tf_seconds <= now_epoch
            ]
            rows = rows[-count:]
        else:
            rows = rows[-count:]
        if not rows:
            raise MT5NoDataError(
                f"MT5_E_NO_DATA: no CLOSED {tf_name} bar available for "
                f"{canonical!r} within the requested window — refusing "
                f"to hand over a forming bar as if it were closed"
            )
        bars = tuple(
            MT5Bar(
                canonical=canonical,
                broker_symbol=entry.broker_symbol,
                timestamp=to_utc_datetime(r["time"]),
                raw_time_epoch=int(r["time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                tick_volume=int(r.get("tick_volume", 0) or 0),
                real_volume=float(r.get("real_volume", 0) or 0.0),
                spread=int(r.get("spread", 0) or 0),
            )
            for r in rows
        )
        self._validate_bars(bars, canonical, entry.broker_symbol)
        last = bars[-1]
        last_close_epoch = int(last.raw_time_epoch) + tf_seconds
        age = float(now_epoch - last_close_epoch)
        threshold = (
            self._max_staleness
            if max_staleness_seconds is None
            else max_staleness_seconds
        )
        staleness_flagged = False
        if threshold and age > threshold:
            if stale_policy == "raise":
                raise MT5StaleDataError(
                    f"latest closed {tf_name} bar for {canonical!r} is "
                    f"stale",
                    age_seconds=age,
                    threshold_seconds=threshold,
                    last_close_epoch=last_close_epoch,
                )
            staleness_flagged = True
        prov_kwargs = dict(
            environment="DEMO",
            demo_verified_at=self._demo_verified_at or now,
            venue_server=str(self._account.get("server", "")),
            terminal_name=str(self._terminal_meta.get("name", "")),
            terminal_build=str(self._terminal_meta.get("build", "")),
            broker_company=str(self._account.get("company", "")),
            canonical=canonical,
            broker_symbol=entry.broker_symbol,
            timeframe=tf_name,
            row_count=len(bars),
            first_epoch=int(bars[0].raw_time_epoch),
            last_epoch=int(last.raw_time_epoch),
            staleness_seconds=age,
            staleness_flagged=staleness_flagged,
            closed_only=closed,
            retrieved_at_utc=now,
        )
        return MT5BarBatch.build(bars, **prov_kwargs)

    @staticmethod
    def _validate_bars(
        bars: tuple[MT5Bar, ...], canonical: str, broker_symbol: str
    ) -> None:
        for bar in bars:
            if bar.high < bar.low:
                raise MT5MarketDataError(
                    f"MT5_E_TERMINAL: observed bar for {canonical!r} "
                    f"({broker_symbol!r}) at epoch {bar.raw_time_epoch} "
                    f"has high < low — invalid terminal data; refusing"
                )
            if bar.high < max(bar.open, bar.close) or bar.low > min(
                bar.open, bar.close
            ):
                raise MT5MarketDataError(
                    f"MT5_E_TERMINAL: observed bar for {canonical!r} at "
                    f"epoch {bar.raw_time_epoch} violates OHLC relations "
                    f"— refusing"
                )

    def fetch_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[Candle]:
        """Framework historical-range query (explicitly NOT freshness-claimed).

        Returns schema-validated candles for fully-closed bars whose
        open time lies in ``[start, end)``. Empty range → ``[]``
        (honest). Requires a connected, DEMO-verified feed and a
        validated symbol map entry for ``instrument``.
        """
        self._require_connected()
        if start.tzinfo is None or end.tzinfo is None:
            raise MT5ConfigError(
                "MT5_E_CONFIG: fetch_candles requires timezone-aware "
                "start/end datetimes"
            )
        tf_name = _TIMEFRAME_TO_MT5.get(timeframe.value)
        if tf_name is None:
            raise MT5ConfigError(
                f"MT5_E_CONFIG: framework timeframe {timeframe.value!r} "
                f"has no MT5 mapping — supported: "
                f"{sorted(_TIMEFRAME_TO_MT5)}"
            )
        entry = self._symbol_map.resolve(instrument)
        tf_const = self._terminal.timeframe_constant(tf_name)
        tf_seconds = _TF_NOMINAL_SECONDS[tf_name]
        rows = self._terminal.copy_rates_range(
            entry.broker_symbol, tf_const, start, end
        )
        if not rows:
            return []
        rows = sorted(rows, key=lambda r: int(r["time"]))
        start_epoch = int(start.timestamp())
        end_epoch = int(end.timestamp())
        candles: list[Candle] = []
        for r in rows:
            open_epoch = int(r["time"])
            close_epoch = open_epoch + tf_seconds
            if open_epoch < start_epoch or close_epoch > end_epoch:
                continue  # partially outside the window or still open
            volume = int(r.get("tick_volume", 0) or 0)
            candles.append(
                Candle(
                    timestamp=to_utc_datetime(open_epoch),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(volume) if volume > 0 else None,
                    timeframe=timeframe,
                    currency=str(
                        getattr(entry.observed, "currency_profit", "") or "USD"
                    ),
                )
            )
        return candles

    def fetch_instrument_info(self, symbol: str) -> Optional[Instrument]:
        """Honest None by default: asset classification is NOT derivable
        from MT5 ``symbol_info`` without an operator decision. An
        ``instrument_factory`` may be injected (runbook §setup) to build
        :class:`data_engine.schemas.Instrument` from the OBSERVED spec —
        never fabricated here.
        """
        if self._instrument_factory is None:
            return None
        self._require_connected()
        entry = self._symbol_map.resolve(symbol)
        return self._instrument_factory(symbol, entry)

    def check_connectivity(self) -> bool:
        """True ONLY while connected AND the terminal still reports connected."""
        if not self._connected:
            return False
        try:
            tinfo = self._terminal.terminal_info()
        except MT5TerminalError:
            return False
        return getattr(tinfo, "connected", None) is True

    # -- ticks ---------------------------------------------------------------------
    def latest_ticks(
        self,
        canonical: str,
        count: int,
        *,
        max_staleness_seconds: Optional[int] = None,
        stale_policy: str = "raise",
        lookback_seconds: int = DEFAULT_TICK_LOOKBACK_SECONDS,
        at: Optional[datetime] = None,
    ) -> MT5TickBatch:
        """Latest OBSERVED ticks (``copy_ticks_from``) with freshness."""
        self._require_connected()
        if count < 1:
            raise MT5ConfigError("MT5_E_CONFIG: count must be >= 1")
        entry = self._symbol_map.resolve(canonical)
        flags = self._terminal.tick_flag_constant("COPY_TICKS_ALL")
        now = at or self._now()
        lookback = max(int(lookback_seconds), 1)
        rows = self._terminal.copy_ticks_from(
            entry.broker_symbol, now - timedelta(seconds=lookback), count, flags
        )
        if not rows:
            raise MT5NoDataError(
                f"MT5_E_NO_DATA: no ticks returned for "
                f"{entry.broker_symbol!r} within the {lookback}s lookback "
                f"— market closed or feed unavailable; never fabricated"
            )
        rows = sorted(rows, key=lambda r: int(r["time"]))
        ticks = tuple(
            MT5Tick(
                canonical=canonical,
                broker_symbol=entry.broker_symbol,
                timestamp=to_utc_datetime(r["time"]),
                raw_time_epoch=int(r["time"]),
                time_msc=(
                    int(r["time_msc"]) if r.get("time_msc") is not None else None
                ),
                bid=(
                    float(r["bid"])
                    if r.get("bid") is not None
                    else None
                ),
                ask=(
                    float(r["ask"])
                    if r.get("ask") is not None
                    else None
                ),
                last=(
                    float(r["last"]) if r.get("last") is not None else None
                ),
                volume=(
                    float(r["volume"])
                    if r.get("volume") is not None
                    else None
                ),
            )
            for r in rows
        )
        newest = ticks[-1]
        now_epoch = int(now.timestamp())
        newest_epoch = int(newest.raw_time_epoch)
        age = float(now_epoch - newest_epoch)
        threshold = (
            self._max_staleness
            if max_staleness_seconds is None
            else max_staleness_seconds
        )
        staleness_flagged = False
        if threshold and age > threshold:
            if stale_policy == "raise":
                raise MT5StaleDataError(
                    f"newest observed tick for {canonical!r} is stale",
                    age_seconds=age,
                    threshold_seconds=threshold,
                    last_close_epoch=newest_epoch,
                )
            staleness_flagged = True
        prov_kwargs = dict(
            environment="DEMO",
            demo_verified_at=self._demo_verified_at or now,
            venue_server=str(self._account.get("server", "")),
            terminal_name=str(self._terminal_meta.get("name", "")),
            terminal_build=str(self._terminal_meta.get("build", "")),
            broker_company=str(self._account.get("company", "")),
            canonical=canonical,
            broker_symbol=entry.broker_symbol,
            timeframe="TICK",
            row_count=len(ticks),
            first_epoch=int(ticks[0].raw_time_epoch),
            last_epoch=newest_epoch,
            staleness_seconds=age,
            staleness_flagged=staleness_flagged,
            closed_only=False,
            retrieved_at_utc=now,
        )
        return MT5TickBatch.build(ticks, **prov_kwargs)

    # -- disconnect / reconnect ------------------------------------------------------
    def disconnect(self) -> None:
        """Clean disconnect — idempotent, never raises."""
        if self._terminal is not None:
            self._terminal.shutdown()
        was_connected = self._connected
        self._connected = False
        self._demo_verified_at = None
        if was_connected:
            self._audit_event("disconnected", "clean disconnect (idempotent)")

    def ensure_connected(self, at: Optional[datetime] = None) -> MT5HealthReport:
        """Safe (re)connect with bounded backoff + FULL re-verification.

        Reconnection repeats the COMPLETE verification chain (terminal
        connected → positive DEMO → server match → symbol-map digest
        re-check); a drop can never silently degrade into an unverified
        session.
        """
        when = at or self._now()
        if self._connected and self.check_connectivity():
            return self.health_check()
        self._audit_event("reconnect_started", "feed not connected — reconnecting")
        last_error: Optional[BaseException] = None
        for attempt in range(1, self._reconnect_attempts + 1):
            self.disconnect()
            delay = min(
                self._backoff * (2 ** (attempt - 1)), _MAX_BACKOFF_SECONDS
            )
            if attempt > 1:
                self._sleep(delay)
            try:
                report = self.connect(at=when)
                self._reconnect_count += 1
                self._audit_event(
                    "reconnected",
                    f"attempt={attempt} reconnect_count={self._reconnect_count}",
                )
                return report
            except (MT5TerminalError, MT5MarketDataError) as exc:
                last_error = exc
                continue
        raise MT5ConnectError(
            f"MT5_E_CONNECT: reconnect failed after "
            f"{self._reconnect_attempts} attempts — last error: "
            f"{last_error!r}; failing closed"
        )

    # -- the ONLY order surface: refusal ----------------------------------------------
    def submit_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: the genuine MT5 feed is a READ-ONLY market-data "
            "surface — order submission would require the live "
            "execution surface which is NOT AUTHORIZED in this "
            "repository; strategy output belongs to the governed "
            "internal paper broker/simulator only"
        )

    def modify_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: order modification belongs to the live execution "
            "surface which is NOT AUTHORIZED in this repository"
        )

    def cancel_order(self, *args: Any, **kwargs: Any) -> None:
        raise MT5OrderRefusedError(
            "REFUSED: order cancellation belongs to the live execution "
            "surface which is NOT AUTHORIZED in this repository"
        )


ProviderFactory.register(EXNESS_MT5_DEMO_PROVIDER_NAME, ExnessMT5DemoFeed)
