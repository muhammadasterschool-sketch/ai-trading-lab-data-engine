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
- **Rate limiting**: fixed-window per-client cap (default 60
  requests/minute, injectable); exceeded → 429. Applies to
  authenticated AND unauthenticated requests (brute-force friction).
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
        pnl_provider: Callable[[], Any] = _absent,
        feed_provider: Callable[[], Any] = _absent,
        risk_provider: Callable[[], Any] = _absent,
        events_provider: Callable[[], Any] = lambda: [],
        killswitch_state_provider: Callable[[], Any] = _absent,
        killswitch_activator: Optional[
            Callable[[str, str], dict]
        ] = None,
        rate_limit_max: int = 60,
        rate_limit_window: float = 60.0,
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

            def _authorized(self) -> bool:
                header = self.headers.get("Authorization", "")
                if not header.startswith("Bearer "):
                    return False
                supplied = header[len("Bearer "):].strip()
                return hmac.compare_digest(
                    supplied.encode("utf-8"), api._token.encode("utf-8")
                )

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
                elif route == "/":
                    self._json(
                        HTTPStatus.OK,
                        {
                            "service": "ai-trading-lab-monitoring-api",
                            "routes": [
                                "/api/health", "/api/positions",
                                "/api/orders", "/api/pnl", "/api/feed",
                                "/api/risk", "/api/events",
                                "/api/killswitch",
                                "POST /api/killswitch/activate",
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
                route = self.path.split("?", 1)[0].rstrip("/")
                if route != "/api/killswitch/activate":
                    self._json(
                        HTTPStatus.METHOD_NOT_ALLOWED,
                        {"error": "read-only surface; only the kill "
                                  "switch accepts POST"},
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
