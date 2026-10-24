"""Genuine MetaTrader 5 terminal boundary (read-only, Windows-bound).

This module is the injectable TERMINAL BOUNDARY of the genuine Exness
MT5 DEMO market-data feed — the exact structural analogue of the
injectable HTTP transport in :mod:`data_engine.providers.binance_public`.

Contract:

- **Read allowlist only.** :data:`MT5_READ_METHODS` is the complete,
  closed set of ``MetaTrader5`` module functions this layer may ever
  call. The module's order functions (``order_send``, ``order_check``,
  ``order_close``, ``positions_get``, ``history_orders_*`` …) are NEVER
  referenced by name and NEVER called — the paper-only boundary is
  structural, not conventional. Negative tests enforce the allowlist
  with a call-recording spy.
- **Credentials stay outside the repository.** ``MT5TerminalConfig``
  is built from operator-provided environment variables
  (``MT5_TERMINAL_PATH``, ``MT5_LOGIN``, ``MT5_PASSWORD``,
  ``MT5_SERVER``); the password is held as a ``SecretStr`` and is
  never rendered by ``repr``, logging or error messages. Nothing here
  writes credentials to disk.
- **Fail closed.** A missing ``MetaTrader5`` package (it is
  Windows-only and intentionally NOT a pyproject dependency) is a
  structured, reported condition — never a silent degradation and
  never a mock substitution.
- **No fabrication.** Empty terminal answers are surfaced as
  structured errors/empty results upstream; nothing here invents
  candles or ticks. Broker symbol names and contract specifications
  are only ever OBSERVED from the terminal (see
  :mod:`data_engine.platform.mt5_symbol_map`).
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, SecretStr

__all__ = [
    "MT5_READ_METHODS",
    "MT5TerminalConfig",
    "MT5TerminalError",
    "MT5CredentialsError",
    "MT5TerminalInitializeError",
    "RealMT5Terminal",
    "load_mt5_module",
    "coerce_rows",
    "rates_to_dicts",
    "ticks_to_dicts",
]

#: The complete closed set of MetaTrader5 module functions the genuine
#: read-only surface may ever call. Every name NOT in this set is
#: forbidden — in particular every order/trade function. Tests spy on
#: the injected module and assert called-name ⊆ this allowlist.
MT5_READ_METHODS = frozenset(
    {
        "initialize",
        "login",
        "shutdown",
        "version",
        "last_error",
        "terminal_info",
        "account_info",
        "symbols_total",
        "symbols_get",
        "symbol_info",
        "symbol_info_tick",
        "copy_rates_from_pos",
        "copy_rates_range",
        "copy_ticks_from",
        "copy_ticks_range",
    }
)

#: Environment variable names (documented contract for the operator).
ENV_TERMINAL_PATH = "MT5_TERMINAL_PATH"
ENV_LOGIN = "MT5_LOGIN"
ENV_PASSWORD = "MT5_PASSWORD"
ENV_SERVER = "MT5_SERVER"


class MT5TerminalError(RuntimeError):
    """Base class for terminal-boundary failures (fail closed)."""

    code = "MT5_E_TERMINAL"


class MT5CredentialsError(MT5TerminalError):
    """Credentials missing/invalid — names only the MISSING VARIABLE."""

    code = "MT5_E_CREDENTIALS"


class MT5TerminalInitializeError(MT5TerminalError):
    """Terminal initialize/login failed (module error code surfaced)."""

    code = "MT5_E_CONNECT"


class MT5TerminalConfig(BaseModel):
    """Operator-provided terminal connection configuration.

    ``password`` is a ``SecretStr``: ``repr``/``str`` of this model
    (and of every downstream error message built from it) never
    contains the secret. Tests assert the redaction.
    """

    model_config = ConfigDict(frozen=True)

    terminal_path: Optional[str] = None
    login: int
    password: SecretStr
    server: str
    #: When set, the OBSERVED ``account_info().server`` must contain
    #: this substring (case-insensitive) or connection is refused —
    #: protects against connecting to an unexpected account/server.
    expected_server_substring: Optional[str] = None

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "MT5TerminalConfig":
        """Build from environment variables; fail closed naming the gap.

        Only the NAMES of missing variables are reported — values are
        never echoed, never logged, never written anywhere.
        """
        source = env if env is not None else os.environ
        missing = [
            name
            for name in (ENV_LOGIN, ENV_PASSWORD, ENV_SERVER)
            if not (source.get(name) or "").strip()
        ]
        if missing:
            raise MT5CredentialsError(
                f"MT5_E_CREDENTIALS: missing environment variable(s) "
                f"{missing} — terminal credentials stay outside the "
                f"repository; set them in the operator shell, never in "
                f"files, logs or reports"
            )
        raw_login = (source.get(ENV_LOGIN) or "").strip()
        try:
            login = int(raw_login)
        except ValueError as exc:
            raise MT5CredentialsError(
                f"MT5_E_CREDENTIALS: {ENV_LOGIN} must be the numeric "
                f"account login — refusing non-numeric value"
            ) from exc
        password_value = source.get(ENV_PASSWORD) or ""
        if len(password_value) < 1:
            raise MT5CredentialsError(
                f"MT5_E_CREDENTIALS: {ENV_PASSWORD} is empty — refusing"
            )
        return cls(
            terminal_path=(source.get(ENV_TERMINAL_PATH) or "").strip() or None,
            login=login,
            password=SecretStr(password_value),
            server=(source.get(ENV_SERVER) or "").strip(),
            expected_server_substring=(
                (source.get("MT5_EXPECTED_SERVER") or "").strip() or None
            ),
        )

    def __repr__(self) -> str:  # pragma: no cover - exercised via str() tests
        return (
            f"MT5TerminalConfig(terminal_path={self.terminal_path!r}, "
            f"login={self.login!r}, password=SecretStr('**********'), "
            f"server={self.server!r})"
        )


def load_mt5_module() -> Optional[Any]:
    """Return the real ``MetaTrader5`` module, or None when absent.

    The package is Windows-only and requires a running terminal; it is
    deliberately NOT a project dependency. Absence is an honest,
    structured condition (``MT5ModuleUnavailableError`` upstream), never
    a mock substitution.
    """
    try:
        import MetaTrader5  # noqa: F401 — Windows-only optional runtime
    except Exception:  # noqa: BLE001 — any import failure = unavailable
        return None
    import MetaTrader5 as mt5

    return mt5


def _py(value: Any) -> Any:
    """Convert numpy scalars to plain Python values (honest, lossless)."""
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (str, bytes, bool, int, float)):
        try:
            return item()
        except Exception:  # noqa: BLE001 — fall through to raw value
            return value
    return value


def _row_to_dict(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    """Convert one terminal row (mapping / namedtuple / numpy void)."""
    if isinstance(row, Mapping):
        source: dict[str, Any] = dict(row)
    elif hasattr(row, "_asdict"):  # real module namedtuples
        source = dict(row._asdict())
    elif hasattr(row, "dtype") and getattr(row.dtype, "names", None):
        source = {name: row[name] for name in row.dtype.names}
    else:
        raise MT5TerminalError(
            f"MT5_E_TERMINAL: unsupported terminal row type "
            f"{type(row)!r} — refusing to guess"
        )
    missing = [f for f in fields if f not in source]
    if missing:
        raise MT5TerminalError(
            f"MT5_E_TERMINAL: terminal payload missing expected "
            f"field(s) {missing} — refusing to guess"
        )
    return {k: _py(v) for k, v in source.items()}


def coerce_rows(raw: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Normalise a terminal answer to a list of plain dicts.

    Handles ALL the real module's payload shapes — numpy structured
    arrays (copy_rates_*/copy_ticks_*), namedtuples (account_info /
    symbol_info / terminal_info / symbol_info_tick) and lists of
    namedtuples (symbols_get) — plus plain mappings/sequences (injected
    fakes). Unknown shapes are REJECTED — never guessed, never
    fabricated.
    """
    if raw is None:
        return []
    if hasattr(raw, "dtype") and getattr(raw.dtype, "names", None):
        field_names = tuple(raw.dtype.names)
        missing = [f for f in fields if f not in field_names]
        if missing:
            raise MT5TerminalError(
                f"MT5_E_TERMINAL: terminal payload missing expected "
                f"field(s) {missing} — refusing to guess"
            )
        return [
            {name: _py(row[name]) for name in field_names}
            for row in raw
        ]
    if isinstance(raw, Mapping) or hasattr(raw, "_asdict"):
        return [_row_to_dict(raw, fields)]
    if isinstance(raw, (list, tuple)):
        return [_row_to_dict(row, fields) for row in raw]
    raise MT5TerminalError(
        f"MT5_E_TERMINAL: unsupported terminal payload type "
        f"{type(raw)!r} — refusing to guess"
    )


_RATES_FIELDS = ("time", "open", "high", "low", "close", "tick_volume")
_TICK_FIELDS = ("time", "bid", "ask")


def rates_to_dicts(raw: Any) -> list[dict[str, Any]]:
    """Normalise copy_rates_* output (extra fields preserved)."""
    return coerce_rows(raw, _RATES_FIELDS)


def ticks_to_dicts(raw: Any) -> list[dict[str, Any]]:
    """Normalise copy_ticks_* output (extra fields preserved)."""
    return coerce_rows(raw, _TICK_FIELDS)


def to_utc_datetime(value: Any) -> datetime:
    """Coerce an epoch-seconds / ms / datetime value to aware UTC.

    MT5 bar/tick ``time`` fields are broker-server epoch seconds
    (``time_msc`` is milliseconds). The raw value is preserved by the
    caller for provenance; this helper only normalises the type.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    number = _py(value)
    if isinstance(number, (int, float)):
        # Heuristic documented in the runbook: >1e11 is treated as
        # milliseconds (tick time_msc), otherwise seconds.
        if number > 100_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(float(number), tz=UTC)
    raise MT5TerminalError(
        f"MT5_E_TERMINAL: cannot coerce timestamp value {value!r}"
    )


class RealMT5Terminal:
    """Thin read-only wrapper around the real ``MetaTrader5`` module.

    Every module call is dispatched BY NAME through
    :meth:`_call`, which refuses any name outside
    :data:`MT5_READ_METHODS` — the paper-only boundary is enforced at
    the single choke point through which the module is reachable.
    Tests inject a fake module object; production passes the module
    from :func:`load_mt5_module` (or None to attempt the real import).
    """

    def __init__(
        self,
        config: MT5TerminalConfig,
        module: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._module = module if module is not None else load_mt5_module()
        self._initialized = False
        self.last_initialize_error: Optional[str] = None

    # -- introspection --------------------------------------------------
    @property
    def module_available(self) -> bool:
        return self._module is not None

    @property
    def config(self) -> MT5TerminalConfig:
        return self._config

    @property
    def initialized(self) -> bool:
        return self._initialized

    # -- the single choke point ------------------------------------------
    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in MT5_READ_METHODS:
            raise MT5TerminalError(
                f"MT5_E_TERMINAL: function {name!r} is outside the "
                f"read-only MT5 allowlist — the genuine feed is a "
                f"market-data surface only and can never trade"
            )
        if self._module is None:
            raise MT5TerminalError(
                "MT5_E_MODULE_UNAVAILABLE: the MetaTrader5 package is "
                "not importable on this platform (Windows-only) — "
                "fail-closed; integration checks stay NOT RUN / "
                "BLOCKED_ON_OPERATOR_ENV until a real Windows terminal "
                "host executes them"
            )
        return getattr(self._module, name)(*args, **kwargs)

    # -- lifecycle ---------------------------------------------------------
    def initialize(self) -> None:
        """Initialize the terminal (optionally launching it) and log in.

        Raises :class:`MT5TerminalInitializeError` with the module's
        own error description when the terminal refuses — the raw
        module error code is surfaced verbatim, never masked.
        """
        kwargs: dict[str, Any] = {
            "login": self._config.login,
            "password": self._config.password.get_secret_value(),
            "server": self._config.server,
        }
        if self._config.terminal_path:
            kwargs["path"] = self._config.terminal_path
        raw = self._call("initialize", **kwargs)
        ok = raw[0] if isinstance(raw, tuple) else raw
        if not ok:
            code, description = self.last_error()
            self._initialized = False
            self.last_initialize_error = f"{code}: {description}"
            raise MT5TerminalInitializeError(
                f"MT5_E_CONNECT: terminal initialize/login failed — "
                f"module last_error={code}: {description} "
                f"(credentials are never echoed)"
            )
        self._initialized = True

    def shutdown(self) -> None:
        """Clean disconnect. Safe to call repeatedly (idempotent)."""
        if self._module is not None and self._initialized:
            try:
                self._call("shutdown")
            except Exception:  # noqa: BLE001 — shutdown must never raise
                pass
        self._initialized = False

    # -- reads (all through the allowlisted choke point) -------------------
    def last_error(self) -> tuple[int, str]:
        raw = self._call("last_error")
        try:
            code, description = raw
        except Exception as exc:  # noqa: BLE001 — shape guard
            raise MT5TerminalError(
                f"MT5_E_TERMINAL: unexpected last_error payload {raw!r}"
            ) from exc
        return int(code), str(description)

    def version(self) -> str:
        raw = self._call("version")
        return " / ".join(str(part) for part in raw) if raw else "unknown"

    def terminal_info(self) -> Any:
        return self._call("terminal_info")

    def account_info(self) -> Any:
        return self._call("account_info")

    def symbols_total(self) -> int:
        return int(self._call("symbols_total") or 0)

    def symbols_get(self) -> list[dict[str, Any]]:
        raw = self._call("symbols_get")
        return coerce_rows(raw, ("name",))

    def symbol_info(self, symbol: str) -> Optional[dict[str, Any]]:
        raw = self._call("symbol_info", symbol)
        rows = coerce_rows(raw, ("name",))
        return rows[0] if rows else None

    def symbol_info_tick(self, symbol: str) -> Optional[dict[str, Any]]:
        raw = self._call("symbol_info_tick", symbol)
        rows = ticks_to_dicts(raw)
        return rows[0] if rows else None

    def copy_rates_from_pos(
        self, symbol: str, timeframe: int, start: int, count: int
    ) -> list[dict[str, Any]]:
        raw = self._call("copy_rates_from_pos", symbol, timeframe, start, count)
        return rates_to_dicts(raw)

    def copy_rates_range(
        self, symbol: str, timeframe: int, date_from: datetime, date_to: datetime
    ) -> list[dict[str, Any]]:
        raw = self._call("copy_rates_range", symbol, timeframe, date_from, date_to)
        return rates_to_dicts(raw)

    def copy_ticks_from(
        self, symbol: str, date_from: datetime, count: int, flags: int
    ) -> list[dict[str, Any]]:
        raw = self._call("copy_ticks_from", symbol, date_from, count, flags)
        return ticks_to_dicts(raw)

    def copy_ticks_range(
        self, symbol: str, date_from: datetime, date_to: datetime, flags: int
    ) -> list[dict[str, Any]]:
        raw = self._call("copy_ticks_range", symbol, date_from, date_to, flags)
        return ticks_to_dicts(raw)

    # -- constant resolution (NEVER hardcoded integers) --------------------
    def timeframe_constant(self, timeframe_name: str) -> int:
        """Resolve ``"M1"``/``"H1"``/… to the module's own constant.

        The integer values live in the installed MetaTrader5 package —
        they are NEVER duplicated in this repository. An unknown or
        module-missing name fails closed with a structured error.
        """
        name = (timeframe_name or "").strip().upper()
        if not name:
            raise MT5TerminalError(
                "MT5_E_CONFIG: empty timeframe name — refusing"
            )
        if self._module is None:
            raise MT5TerminalError(
                "MT5_E_MODULE_UNAVAILABLE: no MetaTrader5 module to "
                "resolve timeframe constant from"
            )
        attr = f"TIMEFRAME_{name}"
        value = getattr(self._module, attr, None)
        if value is None:
            raise MT5TerminalError(
                f"MT5_E_CONFIG: timeframe {timeframe_name!r} not offered "
                f"by the installed MetaTrader5 module ({attr} missing) — "
                f"refusing to substitute"
            )
        return int(value)

    def tick_flag_constant(self, flag_name: str) -> int:
        """Resolve e.g. ``"COPY_TICKS_ALL"`` from the module itself."""
        if self._module is None:
            raise MT5TerminalError(
                "MT5_E_MODULE_UNAVAILABLE: no MetaTrader5 module to "
                "resolve tick flag constant from"
            )
        value = getattr(self._module, flag_name, None)
        if value is None:
            raise MT5TerminalError(
                f"MT5_E_CONFIG: tick flag {flag_name!r} not offered by "
                f"the installed MetaTrader5 module — refusing to substitute"
            )
        return int(value)

    def account_trade_mode_constant(self, mode_name: str) -> int:
        """Resolve e.g. ``"ACCOUNT_TRADE_MODE_DEMO"`` from the module.

        Positive DEMO verification compares the OBSERVED
        ``account_info().trade_mode`` against the DEMO constant the
        installed module itself declares — never against a copied
        integer.
        """
        if self._module is None:
            raise MT5TerminalError(
                "MT5_E_MODULE_UNAVAILABLE: no MetaTrader5 module to "
                "resolve account trade-mode constant from"
            )
        value = getattr(self._module, mode_name, None)
        if value is None:
            raise MT5TerminalError(
                f"MT5_E_CONFIG: account trade-mode constant {mode_name!r} "
                f"not offered by the installed MetaTrader5 module — "
                f"refusing to substitute"
            )
        return int(value)
