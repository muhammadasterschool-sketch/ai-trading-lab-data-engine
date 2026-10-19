"""One-way outbound health heartbeat sender (Stage F, Part 9 F6).

Owner mandate (ADMIN REGISTRY EXCEPTION): the ONLY cross-server
communication allowed is a ONE-WAY, OUTBOUND, minimal HEALTH
HEARTBEAT from each user server to the OWNER's admin registry.

Payload discipline — TEST-ENFORCED (tests/test_monitoring_api.py):
the payload contains ONLY identity + health/status fields:

    schema, user_label, server_id, engine_mode, engine_version,
    uptime_seconds, feed_health, risk_state, kill_switch, timestamp

NEVER: positions, PnL, orders, broker details, keys, credentials.

Operational contract:

- **Graceful degradation**: the registry is BEST-EFFORT. Sending
  failures are counted and logged (redacted); the engine NEVER
  blocks, halts, or retries aggressively because of them. User-server
  operation does NOT depend on registry reachability.
- **Configurable interval**: default 45 seconds (30-60s band per the
  mandate); a single in-flight request at a time; bounded timeout
  (default 5s) so a slow registry can never stall the sender thread.
- **One-way only**: the sender performs exactly one HTTP POST per
  beat; it NEVER polls, downloads, or accepts instructions.
- **Token**: the registry ingest token authenticates the heartbeat
  (Bearer). It is passed at construction and never logged.

LIVE TRADING REMAINS NOT AUTHORIZED.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.monitoring import (
    HEARTBEAT_ALLOWED_FIELDS,
    redact_text,
)

HEARTBEAT_SCHEMA = "ai-trading-lab/heartbeat/1"


class HeartbeatError(RuntimeContractError):
    """Raised on heartbeat-sender contract violations."""


def build_heartbeat_payload(
    *,
    user_label: str,
    server_id: str,
    engine_mode: str,
    engine_version: str,
    uptime_seconds: Optional[float],
    feed_health: str,
    risk_state: str,
    kill_switch: str,
    now: Optional[float] = None,
) -> dict:
    """Build the minimal heartbeat payload.

    Data minimization is ENFORCED here: the payload is constructed
    from EXACTLY the allowed fields — anything else raises (fail
    closed), and the field set is pinned by tests.
    """
    if not user_label or not isinstance(user_label, str):
        raise HeartbeatError("user_label is required (non-empty string)")
    if not server_id or not isinstance(server_id, str):
        raise HeartbeatError("server_id is required (non-empty string)")
    moment = time.time() if now is None else now
    payload = {
        "schema": HEARTBEAT_SCHEMA,
        "user_label": redact_text(str(user_label)),
        "server_id": redact_text(str(server_id)),
        "engine_mode": str(engine_mode),
        "engine_version": str(engine_version),
        "uptime_seconds": uptime_seconds,
        "feed_health": str(feed_health),
        "risk_state": str(risk_state),
        "kill_switch": str(kill_switch),
        "timestamp": moment,
    }
    extra = set(payload) - set(HEARTBEAT_ALLOWED_FIELDS)
    if extra:
        raise HeartbeatError(
            f"data minimization violated: extra fields {sorted(extra)}"
        )
    return payload


class HeartbeatSender:
    """One-way outbound heartbeat sender (graceful degradation)."""

    def __init__(
        self,
        *,
        registry_url: str,
        ingest_token: str,
        payload_builder: Callable[[], dict],
        interval_seconds: float = 45.0,
        timeout_seconds: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not registry_url.startswith("https://"):
            raise HeartbeatError(
                "registry_url must be https:// (TLS-only heartbeat channel)"
            )
        if not ingest_token or not isinstance(ingest_token, str):
            raise HeartbeatError("registry ingest token is required")
        if interval_seconds < 5.0:
            raise HeartbeatError(
                "heartbeat interval must be >= 5 seconds"
            )
        self._registry_url = registry_url
        self._token = ingest_token
        self._payload_builder = payload_builder
        self._interval = float(interval_seconds)
        self._timeout = float(timeout_seconds)
        self._clock = clock
        self._sleeper = sleeper
        self._sent = 0
        self._failed = 0
        self._last_error: Optional[str] = None
        self._last_success_monotonic: Optional[float] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._transport: Optional[Callable[..., Any]] = None  # test seam

    # -- statistics (for monitoring/health endpoints) ---------------------

    @property
    def sent(self) -> int:
        return self._sent

    @property
    def failed(self) -> int:
        return self._failed

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def last_success_age_seconds(self) -> Optional[float]:
        if self._last_success_monotonic is None:
            return None
        return self._clock() - self._last_success_monotonic

    # -- sending -----------------------------------------------------------

    def beat_once(self) -> bool:
        """Send exactly one heartbeat. Returns True on HTTP 2xx.

        NEVER raises: registry unreachability is logged-and-counted,
        not propagated (graceful degradation mandate).
        """
        try:
            payload = self._payload_builder()
        except Exception as exc:  # builder failure must not raise either
            self._failed += 1
            self._last_error = f"payload-builder failure: {type(exc).__name__}"
            return False
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._registry_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
            method="POST",
        )
        try:
            if self._transport is not None:
                response = self._transport(request, timeout=self._timeout)
            else:
                with urllib.request.urlopen(
                    request, timeout=self._timeout
                ) as response:
                    response.read()
            self._sent += 1
            self._last_success_monotonic = self._clock()
            self._last_error = None
            return True
        except (urllib.error.URLError, OSError, ValueError) as exc:
            self._failed += 1
            # redacted: never log URLs-with-token or bodies
            self._last_error = f"send failure: {type(exc).__name__}"
            return False

    def run_forever(self) -> None:
        """Beat on the configured interval until stop() is set.

        Graceful degradation: one in-flight request at a time, bounded
        timeout, stop-responsive sleeps. This method never raises.
        """
        while not self._stop.is_set():
            self.beat_once()
            # responsive sleep in small slices
            remaining = self._interval
            while remaining > 0 and not self._stop.is_set():
                slice_ = min(remaining, 0.5)
                self._sleeper(slice_)
                remaining -= slice_

    def start(self) -> None:
        if self._thread is not None:
            raise HeartbeatError("heartbeat sender already started")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self.run_forever,
            name="heartbeat-sender",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 6.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)
            self._thread = None


__all__ = [
    "HeartbeatSender",
    "HeartbeatError",
    "build_heartbeat_payload",
    "HEARTBEAT_SCHEMA",
]
