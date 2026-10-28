"""Authenticated monitoring API (Stage F, Part 9 F1 — owner mandate).

A server-side, TOKEN-AUTHENTICATED, read-only HTTP surface for the
Android monitoring client (and any future control clients). It runs
on the user's OWN dedicated server, behind their TLS reverse proxy
(``deploy/server-install.sh`` wires nginx + certificates).

Contract (fail-closed at every boundary):

- **Token auth**: ``Authorization: Bearer <token>``;
  ``hmac.compare_digest`` comparison; absent/invalid token → 401.
  The token is INJECTED (never constructed from a default) and is
  never logged, echoed, or embedded in responses.
- **Read-only surface**: GET /api/{health,status,positions,orders,
  pnl,feed,risk,events}. Every non-GET on those routes → 405. The
  ONE deliberately-mutating endpoint is the kill switch:
  ``POST /api/killswitch/activate`` — requires an explicit JSON
  confirmation body ({"confirm": true, "reason": "..."}) and an
  injected activator; a missing/false confirmation → 409 refusal.
  The monitoring API can NEVER submit, modify, or cancel orders.
- **Owner surfaces (v1.0.0)**: GET /api/users (who is connected
  RIGHT NOW), GET /api/registrations (durable first-contact
  ledger), GET /api/ledger/trades + GET /api/ledger/stats
  (per-trade ledger + aggregates for the dashboard mini chart).
  All four are 503 fail-closed unless the corresponding
  registry/ledger is INJECTED by the serve path; identity comes
  from SELF-REPORTED X-Client-* headers read on every
  authenticated request (lab trust domain — the bearer token stays
  the only authentication factor; reset stays PC-gated via the
  ``control-reset`` CLI, never reachable from this API).
- **Rate limiting**: fixed-window per-client cap (default 300
  requests/minute, injectable); exceeded → 429. Applies to
  authenticated AND unauthenticated requests (brute-force friction).
- **Pairing (v4.0)**: ``POST /api/pair`` is the ONE onboarding
  endpoint reachable BEFORE token auth (invitation code → token),
  gated by an injected :class:`~data_engine.runtime.pairing.PairingService`
  with its own stricter per-IP limiter; not wired → 503 fail-closed.
  Every other route is unchanged and stays token-first.
- **Loopback default**: binds 127.0.0.1 unless an EXPLICIT bind
  address is injected (the documented per-user deployment binds the
  engine-side API on loopback and lets nginx terminate TLS on the
  public side; remote exposure without TLS+auth is never implicit).
- **Honest state**: every endpoint reflects its provider's ACTUAL
  state; a provider that is not wired reports ABSENT — never a
  fabricated healthy value.
- **Redacted logs**: the request logger emits method, path, status,
  and client address ONLY (no headers, no bodies, no tokens).

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.pairing import E_PAIRING_DISABLED
from data_engine.runtime.strategy_activation import ActivationDecision

#: Fields a heartbeat payload may contain (Stage F / F6 data
#: minimization — TEST-ENFORCED; see tests/test_monitoring_api.py).
HEARTBEAT_ALLOWED_FIELDS = frozenset(
    {
        "schema",
        "user_label",
        "server_id",
        "engine_mode",
        "engine_version",
        "uptime_seconds",
        "feed_health",
        "risk_state",
        "kill_switch",
        # G7 (owner requirement): prediction status is a HEALTH field
        # exposed through the heartbeat; still NO positions, NO PnL,
        # NO orders, NO broker details, NO credentials.
        "prediction_status",
        "timestamp",
    }
)

_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+"),
)


def redact_text(text: str) -> str:
    """Defensive redaction for any text crossing the monitoring API."""
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


class MonitoringAPIError(RuntimeContractError):
    """Raised on monitoring-API contract violations."""


class _RateLimiter:
    """Fixed-window per-key rate limiter (thread-safe, in-memory)."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        if max_requests < 1:
            raise MonitoringAPIError("max_requests must be >= 1")
        if window_seconds <= 0:
            raise MonitoringAPIError("window_seconds must be positive")
        self._max = int(max_requests)
        self._window = float(window_seconds)
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[float, int]] = {}

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        moment = time.monotonic() if now is None else now
        with self._lock:
            window_start, count = self._counts.get(key, (moment, 0))
            if moment - window_start >= self._window:
                window_start, count = moment, 0
            count += 1
            self._counts[key] = (window_start, count)
            return count <= self._max


def _absent(component: str) -> dict:
    return {"component": component, "state": "ABSENT"}


def default_health_provider() -> dict:
    return {
        "engine_mode": "ABSENT",
        "engine_state": "NOT_CONSTRUCTED",
        "engine_version": "unknown",
        "uptime_seconds": None,
        "detail": "no runtime wired to the monitoring API (honest)",
    }


class MonitoringAPI:
    """Token-authenticated read-only monitoring surface + kill switch.

    Parameters mirror the F1 mandate; every provider is INJECTED —
    there is no hidden global state and no default fabrication.
    """

    def __init__(
        self,
        *,
        auth_token: str,
        host: str = "127.0.0.1",
        port: int = 8018,
        health_provider: Callable[[], dict] = default_health_provider,
        positions_provider: Callable[[], Any] = lambda: [],
        orders_provider: Callable[[], Any] = lambda: [],
        # v4.0.2 correction: the defaults must be zero-arg callables.
        # Binding _absent DIRECTLY (which requires a `component` argument)
        # made every default provider invocation raise TypeError once the
        # monitor-only surface became reachable -> the dashboard showed
        # "provider failure (redacted): TypeError" for Risk/PnL/Feed even
        # though nothing was actually wrong. Mirror the (already correct)
        # prediction_provider pattern: lambda-wrapped with the component.
        pnl_provider: Callable[[], Any] = lambda: _absent("pnl"),
        feed_provider: Callable[[], Any] = lambda: _absent("feed"),
        risk_provider: Callable[[], Any] = lambda: _absent("risk"),
        events_provider: Callable[[], Any] = lambda: [],
        killswitch_state_provider: Callable[[], Any] = lambda: _absent(
            "killswitch"
        ),
        killswitch_activator: Optional[
            Callable[[str, str], dict]
        ] = None,
        prediction_provider: Callable[[], Any] = lambda: _absent("prediction"),
        strategy_gate: Optional[Any] = None,
        # v4.0.2 correction: 60/min starved the real dashboard client,
        # which polls 5 endpoints every cycle (30/min baseline) and tips
        # over the window with the events page or a manual refresh
        # (observed 429 bursts on the owner's phone). 300/min keeps the
        # brute-force friction while leaving normal polling headroom.
        rate_limit_max: int = 300,
        rate_limit_window: float = 60.0,
        pairing_service: Optional[Any] = None,
        # v1.0.0 (owner mandate): client identity registry (who is
        # connected / who ever registered) and the durable trade
        # ledger (which trades, what profit). Both are OPTIONAL and
        # duck-typed; absent -> the matching routes answer 503
        # fail-closed (same posture as the pairing service).
        client_registry: Optional[Any] = None,
        trade_ledger: Optional[Any] = None,
        # v1.1.0 (owner AI lab): the LabManager (strategies + assistant
        # + bars + prediction + broker catalog). Optional and
        # duck-typed; absent -> lab routes answer 503 fail-closed.
        lab: Optional[Any] = None,
        # v1.5.0 (owner mandate): account service with MANDATORY TOTP
        # 2FA login (email+password+code -> 12h session token). Absent
        # -> auth routes answer 503 fail-closed and only the pairing
        # bearer token authorizes (v1.1.0 behavior preserved).
        accounts: Optional[Any] = None,
        # v1.5.0: auto-bootstrap the TOP-5 YouTuber presets when bars
        # first land for a symbol that has no strategies yet (opt-in;
        # tests construct without it).
        bootstrap_presets: bool = False,
        # v1.5.0: historical data service (bundled verified datasets +
        # Binance Vision fallback). Absent -> hist routes 503.
        hist_service: Optional[Any] = None,
    ) -> None:
        if not auth_token or not isinstance(auth_token, str):
            raise MonitoringAPIError(
                "an auth token is MANDATORY (inject the operator-generated "
                "token; the monitoring API never invents one)"
            )
        if len(auth_token) < 16:
            raise MonitoringAPIError(
                "auth token too weak (>= 16 chars; use the installer's "
                "generated 32-hex token)"
            )
        self._token = auth_token
        self._host = host
        self._port = int(port)
        self._providers = {
            "health": health_provider,
            "positions": positions_provider,
            "orders": orders_provider,
            "pnl": pnl_provider,
            "feed": feed_provider,
            "risk": risk_provider,
            "events": events_provider,
            "killswitch": killswitch_state_provider,
        }
        self._killswitch_activator = killswitch_activator
        self._prediction_provider = prediction_provider
        self._strategy_gate = strategy_gate  # StrategyActivationGate (G6)
        self._pairing_service = pairing_service  # PairingService (v4.0 B1)
        self._client_registry = client_registry  # ClientRegistry (v1.0.0)
        self._trade_ledger = trade_ledger  # TradeLedger (v1.0.0)
        self._lab = lab  # LabManager + assistant + bars + predict (v1.1.0)
        self._accounts = accounts  # AccountService (v1.5.0)
        self._bootstrap_presets = bool(bootstrap_presets)
        self._hist_service = hist_service  # HistoricalDataService (v1.5.0)
        self._login_limiter = _RateLimiter(10, 60.0)  # 10 logins/min/IP
        self._limiter = _RateLimiter(rate_limit_max, rate_limit_window)
        self._server: Optional[ThreadingHTTPServer] = None
        self._started_at: Optional[float] = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def bind_host(self) -> str:
        return self._host

    @property
    def bind_port(self) -> int:
        return self._port

    def start(self) -> None:
        if self._server is not None:
            raise MonitoringAPIError("monitoring API already started")
        api = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                # redacted logging: method/path/status/client only
                print(
                    f"[monitoring] {self.command} {self.path} "
                    f"-> {args[1] if len(args) > 1 else '?'} "
                    f"from {self.client_address[0]}"
                )

            def _json(self, code: HTTPStatus, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(int(code))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _identity(self) -> Optional[dict]:
                """v1.5.0: pairing bearer OR a valid 2FA session token.

                Returns ``{"kind": "pairing", "role": "owner"}`` for
                the operator token file, ``{"kind": "session", "email",
                "role": ...}`` for a logged-in account, or None.
                """
                header = self.headers.get("Authorization", "")
                if not header.startswith("Bearer "):
                    return None
                supplied = header[len("Bearer "):].strip()
                if not supplied:
                    return None
                if hmac.compare_digest(
                    supplied.encode("utf-8"), api._token.encode("utf-8")
                ):
                    return {"kind": "pairing", "role": "owner"}
                if api._accounts is not None:
                    session = api._accounts.sessions.validate(supplied)
                    if session:
                        return {
                            "kind": "session",
                            "email": session["email"],
                            "role": session["role"],
                        }
                return None

            def _authorized(self) -> bool:
                return self._identity() is not None

            def _admin(self) -> bool:
                identity = self._identity()
                if not identity:
                    return False
                return identity["kind"] == "pairing" or identity.get(
                    "role"
                ) == "admin"

            def do_GET(self) -> None:  # noqa: N802
                client = self.client_address[0]
                if not api._limiter.allow(client):
                    self._json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {"error": "rate limited"},
                    )
                    return
                if not self._authorized():
                    self._json(
                        HTTPStatus.UNAUTHORIZED,
                        {"error": "invalid or missing bearer token"},
                    )
                    return
                self._observe()
                route = self.path.split("?", 1)[0].rstrip("/") or "/"
                if route == "/api/health":
                    self._json(HTTPStatus.OK, api._provider("health"))
                elif route == "/api/positions":
                    self._json(HTTPStatus.OK, api._provider("positions"))
                elif route == "/api/orders":
                    self._json(HTTPStatus.OK, api._provider("orders"))
                elif route == "/api/pnl":
                    self._json(HTTPStatus.OK, api._provider("pnl"))
                elif route == "/api/feed":
                    self._json(HTTPStatus.OK, api._provider("feed"))
                elif route == "/api/risk":
                    self._json(HTTPStatus.OK, api._provider("risk"))
                elif route == "/api/events":
                    self._json(HTTPStatus.OK, api._provider("events"))
                elif route == "/api/killswitch":
                    self._json(
                        HTTPStatus.OK, api._provider("killswitch")
                    )
                elif route == "/api/prediction":
                    self._json(
                        HTTPStatus.OK, api._prediction_provider()
                    )
                elif route == "/api/users":
                    # v1.0.0: who is connected RIGHT NOW (owner surface)
                    # v1.5.0: admin-gated (pairing owner OR admin-role
                    # session); trader sessions answer 403.
                    if not self._admin():
                        self._json(
                            HTTPStatus.FORBIDDEN,
                            {"error": "admin role required"},
                        )
                        return
                    if api._client_registry is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "client registry not wired "
                                     "(fail closed)"},
                        )
                        return
                    clients = api._client_registry.users()
                    self._json(
                        HTTPStatus.OK,
                        {"clients": clients, "count": len(clients)},
                    )
                elif route == "/api/registrations":
                    # v1.0.0: durable first-contact registration ledger
                    # v1.5.0: admin-gated (see /api/users).
                    if not self._admin():
                        self._json(
                            HTTPStatus.FORBIDDEN,
                            {"error": "admin role required"},
                        )
                        return
                    if api._client_registry is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "client registry not wired "
                                     "(fail closed)"},
                        )
                        return
                    rows = api._client_registry.registrations()
                    self._json(
                        HTTPStatus.OK,
                        {"registrations": rows, "count": len(rows)},
                    )
                elif route == "/api/ledger/trades":
                    # v1.0.0: per-trade ledger (which trades, what PnL)
                    if api._trade_ledger is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "trade ledger not wired "
                                     "(fail closed)"},
                        )
                        return
                    trades = api._trade_ledger.entries(limit=200)
                    self._json(
                        HTTPStatus.OK,
                        {"trades": trades, "count": len(trades)},
                    )
                elif route == "/api/ledger/stats":
                    # v1.0.0: aggregates — trades per symbol (the
                    # dashboard mini chart), total PnL, wins/losses
                    if api._trade_ledger is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "trade ledger not wired "
                                     "(fail closed)"},
                        )
                        return
                    self._json(
                        HTTPStatus.OK, api._trade_ledger.stats()
                    )
                elif route == "/api/lab/strategies":
                    # v1.1.0: owner AI lab — strategy pipeline list
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    rows = api._lab.list()
                    self._json(
                        HTTPStatus.OK,
                        {"strategies": rows, "count": len(rows)},
                    )
                elif route.startswith("/api/lab/bars/"):
                    # v1.1.0: stored bar history summary for one symbol
                    # (symbol may contain '/', e.g. XAU/USD)
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    symbol = route[len("/api/lab/bars/"):]
                    from data_engine.runtime.lab import LabError as _LabError

                    try:
                        self._json(
                            HTTPStatus.OK,
                            api._lab._bars.summary(symbol),
                        )
                    except _LabError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                elif route.startswith("/api/lab/predict/"):
                    # v1.1.0: statistical next-move baseline for a symbol
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    symbol = route[len("/api/lab/predict/"):]
                    from data_engine.runtime.lab import (
                        LabError as _LabError,
                        PredictBaseline as _Predict,
                    )

                    bars = api._lab._bars.bars(symbol)
                    try:
                        self._json(
                            HTTPStatus.OK,
                            _Predict().predict(bars),
                        )
                    except _LabError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                elif route == "/api/lab/brokers":
                    # v1.1.0: honest broker catalog + add-broker contract
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    from data_engine.runtime.lab import (
                        BrokerCatalog as _Catalog,
                    )

                    self._json(HTTPStatus.OK, _Catalog().catalog())
                elif route == "/api/lab/presets":
                    # v1.5.0: the TOP-5 YouTuber strategy presets
                    from data_engine.runtime.presets import (
                        presets_for_api as _presets,
                    )

                    rows = _presets()
                    self._json(
                        HTTPStatus.OK,
                        {"presets": rows, "count": len(rows)},
                    )
                elif route.startswith("/api/lab/predict-ensemble/"):
                    # v1.5.0: multi-component next-move ensemble
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    symbol = route[len("/api/lab/predict-ensemble/"):]
                    from data_engine.runtime.crash_lab import (
                        NextMoveEnsemble as _Ensemble,
                    )
                    from data_engine.runtime.lab import (
                        LabError as _LabError,
                    )

                    bars = api._lab._bars.bars(symbol)
                    try:
                        self._json(
                            HTTPStatus.OK, _Ensemble().predict(bars)
                        )
                    except _LabError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                elif route.startswith("/api/lab/crash/"):
                    # v1.5.0: heuristic crash-risk gauge
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    symbol = route[len("/api/lab/crash/"):]
                    from data_engine.runtime.crash_lab import (
                        LabCrashPredictor as _Crash,
                    )
                    from data_engine.runtime.lab import (
                        LabError as _LabError,
                    )

                    bars = api._lab._bars.bars(symbol)
                    try:
                        self._json(
                            HTTPStatus.OK, _Crash().predict(bars)
                        )
                    except _LabError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                elif route == "/api/hist/datasets":
                    # v1.5.0: bundled verified historical datasets
                    from data_engine.platform.historical_data import (
                        list_bundled_datasets as _list_ds,
                    )

                    rows = _list_ds()
                    self._json(
                        HTTPStatus.OK,
                        {
                            "datasets": rows,
                            "count": len(rows),
                            "note": (
                                "verified real data (sha256 vs official "
                                "source checksum); RESEARCH_BACKTEST_ONLY "
                                "- operational feed gates unchanged"
                            ),
                        },
                    )
                elif route == "/api/auth/me":
                    # v1.5.0: who am I (session or pairing)?
                    identity = self._identity()
                    if identity and identity["kind"] == "session":
                        record = api._accounts.store.get(
                            identity["email"]
                        ) or {}
                        self._json(
                            HTTPStatus.OK,
                            {
                                "auth": "session",
                                "email": identity["email"],
                                "name": record.get("name"),
                                "role": identity["role"],
                            },
                        )
                    else:
                        self._json(
                            HTTPStatus.OK,
                            {
                                "auth": "pairing",
                                "email": None,
                                "role": "owner",
                            },
                        )
                elif route == "/api/admin/accounts":
                    # v1.5.0: admin-only account roster + login history
                    if api._accounts is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "accounts not wired (fail closed)"},
                        )
                        return
                    if not self._admin():
                        self._json(
                            HTTPStatus.FORBIDDEN,
                            {"error": "admin role required"},
                        )
                        return
                    self._json(
                        HTTPStatus.OK,
                        api._accounts.accounts(
                            actor_role=self._identity()["role"]
                            if self._identity()["kind"] == "session"
                            else "admin"
                        ),
                    )
                elif route.startswith("/api/strategy/"):
                    # GET /api/strategy/{id} -> gate status (G6)
                    if api._strategy_gate is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "strategy gate not wired "
                                     "(fail closed)"},
                        )
                        return
                    submission_id = route[len("/api/strategy/"):]
                    try:
                        self._json(
                            HTTPStatus.OK,
                            api._strategy_gate.status(submission_id),
                        )
                    except Exception as exc:
                        self._json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown strategy: "
                                     f"{type(exc).__name__}"},
                        )
                elif route == "/":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "service": "ai-trading-lab-monitoring-api",
                            "routes": [
                                "/api/health", "/api/positions",
                                "/api/orders", "/api/pnl", "/api/feed",
                                "/api/risk", "/api/events",
                                "/api/killswitch", "/api/prediction",
                                "/api/users", "/api/registrations",
                                "/api/ledger/trades", "/api/ledger/stats",
                                "/api/lab/strategies",
                                "/api/lab/bars/{symbol}",
                                "/api/lab/predict/{symbol}",
                                "/api/lab/predict-ensemble/{symbol}",
                                "/api/lab/crash/{symbol}",
                                "/api/lab/presets",
                                "/api/lab/brokers",
                                "/api/hist/datasets",
                                "/api/auth/me",
                                "/api/admin/accounts (admin)",
                                "POST /api/pair (onboarding; invitation code)",
                                "POST /api/auth/login (email+password+TOTP)",
                                "POST /api/auth/logout",
                                "POST /api/killswitch/activate",
                                "POST /api/strategy/submit",
                                "GET /api/strategy/{id}",
                                "POST /api/strategy/{id}/activate",
                                "POST /api/lab/strategies (create)",
                                "POST /api/lab/strategies/{id}/backtest",
                                "POST /api/lab/strategies/{id}/paper/start",
                                "POST /api/lab/strategies/{id}/paper/finish",
                                "POST /api/lab/strategies/{id}/confirm",
                                "POST /api/lab/assistant (ask)",
                                "POST /api/lab/bars (upload history)",
                                "POST /api/lab/bootstrap {symbol}",
                                "POST /api/lab/auto-scan {symbol}",
                                "POST /api/hist/import {symbol, timeframe}",
                                "POST /api/admin/accounts (create user)",
                                "POST /api/admin/accounts/reset-2fa",
                                "POST /api/admin/accounts/set-lock",
                            ],
                            "live_trading": "NOT_AUTHORIZED",
                        },
                    )
                else:
                    self._json(
                        HTTPStatus.NOT_FOUND, {"error": "not found"}
                    )

            def do_POST(self) -> None:  # noqa: N802
                client = self.client_address[0]
                route = self.path.split("?", 1)[0].rstrip("/")

                # -- v4.0 B1: POST /api/pair — the ONE onboarding
                # endpoint handled BEFORE token auth (invitation code
                # is the onboarding secret; the service enforces its own
                # STRICTER per-IP pairing rate limit internally).
                # Everything else below is unchanged and token-first.
                if route == "/api/pair":
                    if api._pairing_service is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": E_PAIRING_DISABLED},
                        )
                        return
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if length <= 0 or length > 8192:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 8 KiB)"},
                        )
                        return
                    try:
                        pair_body = json.loads(
                            self.rfile.read(length).decode("utf-8")
                        )
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(pair_body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    status, payload = api._pairing_service.attempt(
                        client_ip=client,
                        payload=pair_body,
                        token=api._token,
                        health_provider=api._provider("health"),
                    )
                    self._json(
                        HTTPStatus(status) if status in (
                            HTTPStatus.OK.value,
                            HTTPStatus.BAD_REQUEST.value,
                            HTTPStatus.FORBIDDEN.value,
                            HTTPStatus.TOO_MANY_REQUESTS.value,
                            HTTPStatus.SERVICE_UNAVAILABLE.value,
                        ) else HTTPStatus.INTERNAL_SERVER_ERROR,
                        payload,
                    )
                    return

                # -- v1.5.0: POST /api/auth/login — the SECOND pre-auth
                # route (email + password + TOTP; the account service
                # enforces its own lockout policy and this handler adds
                # a dedicated 10/min/IP login rate limit).
                if route == "/api/auth/login":
                    if api._accounts is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "accounts not wired (fail closed)"},
                        )
                        return
                    if not api._login_limiter.allow(client):
                        self._json(
                            HTTPStatus.TOO_MANY_REQUESTS,
                            {"error": "E_LOGIN_RATE_LIMITED"},
                        )
                        return
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if length <= 0 or length > 4096:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 4096 bytes)"},
                        )
                        return
                    try:
                        login_body = json.loads(
                            self.rfile.read(length).decode("utf-8")
                        )
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(login_body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    from data_engine.runtime.accounts import (
                        AccountError as _AccountError,
                    )

                    try:
                        outcome = api._accounts.login(
                            str(login_body.get("email", "")),
                            str(login_body.get("password", "")),
                            str(login_body.get("totp_code", "")),
                            ip=client,
                        )
                    except _AccountError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                        return
                    kind = outcome.get("outcome")
                    if kind == "SESSION":
                        self._json(
                            HTTPStatus.OK,
                            {
                                "token": outcome["token"],
                                "expires_at": outcome["expires_at"],
                                "user": outcome["user"],
                                "auth": "session",
                            },
                        )
                    elif kind == "E_TOTP_ENROLLMENT_REQUIRED":
                        self._json(
                            HTTPStatus.CONFLICT,
                            {
                                "error": kind,
                                "totp_secret": outcome["totp_secret"],
                                "otpauth_uri": outcome["otpauth_uri"],
                                "note": (
                                    "add the secret to your "
                                    "authenticator app, then login again "
                                    "with the 6-digit code to finish "
                                    "enrollment"
                                ),
                            },
                        )
                    elif kind == "E_ACCOUNT_LOCKED":
                        self._json(
                            HTTPStatus.LOCKED,
                            {
                                "error": kind,
                                "locked_until": outcome.get(
                                    "locked_until"
                                ),
                            },
                        )
                    else:  # E_BAD_CREDENTIALS / E_TOTP_INVALID
                        self._json(
                            HTTPStatus.UNAUTHORIZED,
                            {"error": kind},
                        )
                    return

                if not api._limiter.allow(client):
                    self._json(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        {"error": "rate limited"},
                    )
                    return
                if not self._authorized():
                    self._json(
                        HTTPStatus.UNAUTHORIZED,
                        {"error": "invalid or missing bearer token"},
                    )
                    return
                self._observe()
                if route == "/api/strategy/submit":
                    """G6 chat-form submission: structured spec + free
                    text (LLM assist allowed for PARSING ONLY, never
                    decisions). Creates an INACTIVE submission."""
                    if api._strategy_gate is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "strategy gate not wired (fail closed)"},
                        )
                        return
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if not 0 < length <= 16384:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 16 KiB)"},
                        )
                        return
                    try:
                        body = json.loads(self.rfile.read(length).decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    try:
                        submission = api._strategy_gate.submit(
                            submitted_by=str(body.get("submitted_by", "monitoring-client")),
                            label=str(body.get("label", "")),
                            structured_spec=body.get("structured_spec") or {},
                            free_text=str(body.get("free_text", "")),
                            parse_source=str(body.get("parse_source", "USER")),
                        )
                    except Exception as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": f"submission refused: {type(exc).__name__}"},
                        )
                        return
                    self._json(
                        HTTPStatus.OK,
                        {
                            "submission_id": submission.submission_id,
                            "state": "SUBMITTED",
                            "disposition": "INACTIVE",
                            "pipeline": [
                                "automated backtest",
                                "validation cycle",
                                "explicit user YES",
                            ],
                        },
                    )
                    return
                if route.startswith("/api/strategy/") and route.endswith("/activate"):
                    """G6 activation: the gate itself enforces backtest
                    + validation evidence + explicit YES; this endpoint
                    can NEVER bypass the gate (fail closed by design)."""
                    if api._strategy_gate is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "strategy gate not wired (fail closed)"},
                        )
                        return
                    submission_id = route[len("/api/strategy/"):-len("/activate")]
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if not 0 < length <= 4096:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 4096 bytes)"},
                        )
                        return
                    try:
                        body = json.loads(self.rfile.read(length).decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    answer = (body or {}).get("confirm")
                    if answer != "YES":
                        self._json(
                            HTTPStatus.CONFLICT,
                            {
                                "error": "explicit YES required: re-send "
                                         "with {\"confirm\": \"YES\"} — "
                                         "no answer or ambiguity keeps "
                                         "the strategy INACTIVE",
                            },
                        )
                        return
                    try:
                        record = api._strategy_gate.activate(
                            submission_id,
                            ActivationDecision.yes(
                                decided_by=str(
                                    (body or {}).get(
                                        "decided_by", "monitoring-client"
                                    )
                                ),
                                note=str((body or {}).get("note", "")),
                            ),
                        )
                    except Exception as exc:
                        self._json(
                            HTTPStatus.NOT_FOUND,
                            {"error": f"unknown strategy: {type(exc).__name__}"},
                        )
                        return
                    self._json(
                        HTTPStatus.OK,
                        {
                            "submission_id": submission_id,
                            "state": record.state.value,
                            "disposition": record.disposition,
                            "note": "activation requires the full evidence "
                                    "chain; INACTIVE means the gate held",
                        },
                    )
                    return
                # -- v1.5.0: auth/logout + admin account ops + hist
                # import (session or pairing auth; admin ops are
                # admin-gated; nothing here can authorize live
                # trading).
                if route == "/api/auth/logout":
                    if api._accounts is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "accounts not wired (fail closed)"},
                        )
                        return
                    header = self.headers.get("Authorization", "")
                    token = (
                        header[len("Bearer "):].strip()
                        if header.startswith("Bearer ")
                        else ""
                    )
                    revoked = api._accounts.sessions.revoke(token)
                    self._json(
                        HTTPStatus.OK,
                        {"revoked": bool(revoked)},
                    )
                    return
                if route in (
                    "/api/admin/accounts",
                    "/api/admin/accounts/reset-2fa",
                    "/api/admin/accounts/set-lock",
                ):
                    if api._accounts is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "accounts not wired (fail closed)"},
                        )
                        return
                    identity = self._identity()
                    if identity is None:
                        self._json(
                            HTTPStatus.UNAUTHORIZED,
                            {"error": "invalid or missing bearer token"},
                        )
                        return
                    actor_role = (
                        identity.get("role")
                        if identity.get("kind") == "session"
                        else "admin"
                    )
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if length <= 0 or length > 4096:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 4096 bytes)"},
                        )
                        return
                    try:
                        admin_body = json.loads(
                            self.rfile.read(length).decode("utf-8")
                        )
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(admin_body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    from data_engine.runtime.accounts import (
                        AccountError as _AccountError,
                    )

                    try:
                        if route == "/api/admin/accounts":
                            result = api._accounts.create_user(
                                actor_role=actor_role,
                                email=str(admin_body.get("email", "")),
                                name=str(admin_body.get("name", "")),
                                password=str(admin_body.get("password", "")),
                                role=str(admin_body.get("role", "trader")),
                            )
                        elif route == "/api/admin/accounts/reset-2fa":
                            result = api._accounts.reset_2fa(
                                actor_role=actor_role,
                                email=str(admin_body.get("email", "")),
                            )
                        else:
                            raw_locked = admin_body.get("locked")
                            if not isinstance(raw_locked, bool):
                                raise _AccountError(
                                    "locked must be true or false"
                                )
                            result = api._accounts.set_lock(
                                actor_role=actor_role,
                                email=str(admin_body.get("email", "")),
                                locked=raw_locked,
                            )
                    except _AccountError as exc:
                        status = (
                            HTTPStatus.FORBIDDEN
                            if "admin role required" in str(exc)
                            else HTTPStatus.BAD_REQUEST
                        )
                        self._json(status, {"error": str(exc)})
                        return
                    self._json(HTTPStatus.OK, result)
                    return
                if route == "/api/hist/import":
                    # v1.5.0: import VERIFIED REAL history into the lab
                    # BarStore (bundled repo data first, then the
                    # Binance Vision website fallback).
                    if api._hist_service is None or api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "historical data service not wired "
                                     "(fail closed)"},
                        )
                        return
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if length <= 0 or length > 4096:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max 4096 bytes)"},
                        )
                        return
                    try:
                        hist_body = json.loads(
                            self.rfile.read(length).decode("utf-8")
                        )
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(hist_body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    from data_engine.platform.historical_data import (
                        HistoricalDataError as _HistError,
                    )
                    from data_engine.runtime.lab import (
                        LabError as _LabError,
                    )

                    symbol = str(hist_body.get("symbol", ""))
                    timeframe = str(hist_body.get("timeframe", "1m"))
                    source = str(hist_body.get("source", "auto"))
                    raw_months = hist_body.get("months", 1)
                    if isinstance(raw_months, bool) or not isinstance(
                        raw_months, int
                    ):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "months must be an integer"},
                        )
                        return
                    try:
                        fetched = api._hist_service.fetch(
                            symbol,
                            timeframe,
                            months=raw_months,
                            source=source,
                        )
                        imported = api._hist_service.import_into_barstore(
                            api._lab._bars, symbol, fetched["bars"]
                        )
                        imported["source_used"] = fetched["source_used"]
                        imported["provenance"] = fetched["provenance"]
                        imported["paper"] = api._lab.observe_symbol_update(
                            symbol
                        )
                        self._json(HTTPStatus.OK, imported)
                    except (_HistError, _LabError) as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                        return
                if route.startswith("/api/lab/"):
                    # v1.1.0 OWNER AI LAB POST surfaces (fail-closed on
                    # unwired lab; LabError -> 400; nothing here can
                    # ever authorize live trading).
                    if api._lab is None:
                        self._json(
                            HTTPStatus.SERVICE_UNAVAILABLE,
                            {"error": "lab not wired (fail closed)"},
                        )
                        return
                    if route == "/api/lab/bars":
                        max_body = 2_097_152  # 2 MiB (bounded bar upload)
                    elif route == "/api/lab/assistant":
                        max_body = 4096
                    elif route == "/api/lab/strategies":
                        max_body = 8192
                    else:
                        max_body = 4096
                    length = int(
                        self.headers.get("Content-Length", "0") or 0
                    )
                    if not 0 < length <= max_body:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON body required (max "
                                      f"{max_body} bytes for this route)"},
                        )
                        return
                    try:
                        body = json.loads(
                            self.rfile.read(length).decode("utf-8")
                        )
                    except (ValueError, UnicodeDecodeError):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "invalid JSON body"},
                        )
                        return
                    if not isinstance(body, dict):
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": "JSON object required"},
                        )
                        return
                    from data_engine.runtime.lab import (
                        LabError as _LabError,
                    )

                    try:
                        if route == "/api/lab/bars":
                            result = api._lab._bars.append(
                                str(body.get("symbol", "")),
                                body.get("bars"),
                            )
                            # forward paper evaluation on fresh bars
                            result["paper"] = (
                                api._lab.observe_symbol_update(
                                    str(body.get("symbol", ""))
                                )
                            )
                            # v1.5.0: opt-in preset auto-bootstrap —
                            # when the FIRST bars land for a symbol that
                            # has no strategies yet, create the TOP-5
                            # YouTuber presets and open their paper
                            # windows (activation still needs owner YES)
                            if api._bootstrap_presets and int(
                                result.get("total", 0) or 0
                            ) > 0:
                                try:
                                    symbol_now = str(
                                        body.get("symbol", "")
                                    )
                                    rows = api._lab.list()
                                    if not any(
                                        r.get("symbol") == symbol_now
                                        for r in rows
                                    ):
                                        result["bootstrap"] = (
                                            api._lab
                                            .bootstrap_default_strategies(
                                                symbol_now
                                            )
                                        )
                                except _LabError:
                                    pass  # honest skip (fail closed)
                            self._json(HTTPStatus.OK, result)
                            return
                        if route == "/api/lab/bootstrap":
                            self._json(
                                HTTPStatus.OK,
                                api._lab.bootstrap_default_strategies(
                                    str(body.get("symbol", ""))
                                ),
                            )
                            return
                        if route == "/api/lab/auto-scan":
                            raw_top = body.get("top_n", 3)
                            if isinstance(raw_top, bool) or not isinstance(
                                raw_top, int
                            ):
                                raise _LabError("top_n must be an integer")
                            self._json(
                                HTTPStatus.OK,
                                api._lab.auto_scan(
                                    str(body.get("symbol", "")),
                                    top_n=raw_top,
                                ),
                            )
                            return
                        if route == "/api/lab/assistant":
                            if api._lab.assistant is None:
                                self._json(
                                    HTTPStatus.SERVICE_UNAVAILABLE,
                                    {"error": "assistant not wired "
                                              "(fail closed)"},
                                )
                                return
                            self._json(
                                HTTPStatus.OK,
                                api._lab.assistant.ask(
                                    str(body.get("question", ""))
                                ),
                            )
                            return
                        if route == "/api/lab/strategies":
                            self._json(
                                HTTPStatus.OK,
                                api._lab.create(
                                    label=str(body.get("label", "")),
                                    symbol=str(body.get("symbol", "")),
                                    kind=str(body.get("kind", "")),
                                    params=body.get("params") or {},
                                    submitted_by=str(
                                        body.get("submitted_by",
                                                 "owner-lab")
                                    ),
                                ),
                            )
                            return
                        prefix = "/api/lab/strategies/"
                        if route.startswith(prefix) and route.endswith(
                            "/backtest"
                        ):
                            self._json(
                                HTTPStatus.OK,
                                api._lab.run_backtest(
                                    route[len(prefix):-len("/backtest")]
                                ),
                            )
                            return
                        if route.startswith(prefix) and route.endswith(
                            "/paper/start"
                        ):
                            raw_days = body.get("cycle_days", 30)
                            if isinstance(raw_days, bool) or not (
                                isinstance(raw_days, int)
                            ):
                                raise _LabError(
                                    "cycle_days must be an integer"
                                )
                            self._json(
                                HTTPStatus.OK,
                                api._lab.paper_start(
                                    route[len(prefix):-len("/paper/start")],
                                    cycle_days=raw_days,
                                ),
                            )
                            return
                        if route.startswith(prefix) and route.endswith(
                            "/paper/finish"
                        ):
                            self._json(
                                HTTPStatus.OK,
                                api._lab.paper_finish(
                                    route[len(prefix):-len(
                                        "/paper/finish"
                                    )],
                                ),
                            )
                            return
                        if route.startswith(prefix) and route.endswith(
                            "/confirm"
                        ):
                            self._json(
                                HTTPStatus.OK,
                                api._lab.confirm(
                                    route[len(prefix):-len("/confirm")],
                                    confirm=str(body.get("confirm", "")),
                                    decided_by=str(
                                        body.get("decided_by", "owner")
                                    ),
                                    note=str(body.get("note", "")),
                                ),
                            )
                            return
                        self._json(
                            HTTPStatus.NOT_FOUND,
                            {"error": "unknown lab route"},
                        )
                        return
                    except _LabError as exc:
                        self._json(
                            HTTPStatus.BAD_REQUEST,
                            {"error": str(exc)},
                        )
                        return
                if route != "/api/killswitch/activate":
                    self._json(
                        HTTPStatus.METHOD_NOT_ALLOWED,
                        {"error": "read-only surface; POST exists only "
                                  "for the kill switch, the strategy "
                                  "gate, the owner lab, accounts and "
                                  "the historical import (no order "
                                  "submission route exists)"},
                    )
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 4096:
                    self._json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "JSON body required (max 4096 bytes)"},
                    )
                    return
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "invalid JSON body"},
                    )
                    return
                if not isinstance(body, dict):
                    self._json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "JSON object required"},
                    )
                    return
                if body.get("confirm") is not True:
                    self._json(
                        HTTPStatus.CONFLICT,
                        {
                            "error": "explicit confirmation required: "
                                     "re-send with "
                                     '{"confirm": true, "reason": "..."}',
                        },
                    )
                    return
                reason = str(body.get("reason", "")).strip()
                if not reason:
                    self._json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "a non-empty 'reason' is required"},
                    )
                    return
                if api._killswitch_activator is None:
                    self._json(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {
                            "error": "kill-switch activator not wired "
                                     "(fail closed — no implicit action)"
                        },
                    )
                    return
                actor = f"monitoring-client@{client}"
                result = api._killswitch_activator(actor, redact_text(reason))
                self._json(HTTPStatus.OK, result)

            def _method_not_allowed(self) -> None:
                self._json(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    {"error": "read-only monitoring surface"},
                )

            def _observe(self) -> None:
                """v1.0.0: best-effort client observation AFTER auth.

                Identity is SELF-REPORTED via X-Client-* headers (lab
                trust domain — the bearer token is the only
                authentication factor). Observation must NEVER break
                serving, so any registry failure is swallowed here.
                """
                if api._client_registry is None:
                    return
                try:
                    api._client_registry.observe(
                        client_ip=self.client_address[0],
                        name=self.headers.get("X-Client-Name", ""),
                        email=self.headers.get("X-Client-Email", ""),
                        kind=self.headers.get("X-Client-Kind", ""),
                        device=self.headers.get("X-Client-Device", ""),
                    )
                except Exception:  # noqa: BLE001 — never break serving
                    pass

            do_PUT = do_PATCH = do_DELETE = _method_not_allowed

        self._server = ThreadingHTTPServer((self._host, self._port), _Handler)
        self._started_at = time.monotonic()
        thread = threading.Thread(
            target=self._server.serve_forever,
            name="monitoring-api",
            daemon=True,
        )
        thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def url(self) -> str:
        port = self._server.server_address[1] if self._server else self._port
        return f"http://{self._host}:{port}"

    # -- provider access (fail-closed honesty) ----------------------------

    def _provider(self, name: str) -> Any:
        provider = self._providers[name]
        try:
            return provider()
        except Exception as exc:  # never leak internals to the client
            return {
                "component": name,
                "state": "ERROR",
                "detail": f"provider failure (redacted): {type(exc).__name__}",
            }

    def token_digest(self) -> str:
        """Non-reversible digest for install-time verification UX."""
        return hashlib.sha256(self._token.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "MonitoringAPI",
    "MonitoringAPIError",
    "HEARTBEAT_ALLOWED_FIELDS",
    "redact_text",
    "default_health_provider",
]
