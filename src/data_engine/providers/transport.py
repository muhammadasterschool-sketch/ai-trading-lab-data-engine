"""HTTP transport primitives for real market-data adapters.

PAPER-ONLY machinery. This module provides a SINGLE-ATTEMPT HTTP GET
transport (stdlib :mod:`urllib` only — no new dependencies) with:

- a hard request timeout (no default-forever sockets);
- an explicit response-size cap (memory safety against oversized
  responses);
- typed transport failures (connect / timeout / HTTP status /
  protocol) so adapter retry policy can discriminate WITHOUT
  swallowing anything;
- an injectable ``sleeper`` for deterministic backoff tests.

The transport NEVER parses market-data semantics and NEVER retries on
its own — bounded retry/backoff policy belongs to the adapter
(:mod:`data_engine.providers.binance_public`), keeping network I/O
and pure validation strictly separated (paper-readiness mandate
Phase B: "clear separation of network retrieval from pure validation
logic").

No credentials are ever attached by this transport: it issues plain
anonymous GETs to public endpoints only.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Mapping

__all__ = [
    "MAX_RESPONSE_BYTES",
    "TransportConnectError",
    "TransportHTTPError",
    "TransportProtocolError",
    "TransportTimeoutError",
    "HttpGetTransport",
]

#: Hard cap on one response body (16 MiB) — klines pages are ~100 KB;
#: anything larger is a protocol anomaly, not market data.
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class TransportConnectError(RuntimeError):
    """Could not establish a connection (retryable by policy)."""

    def __init__(self, url: str, cause: BaseException) -> None:
        super().__init__(
            f"transport connect failure for {url}: {cause!r}"
        )
        self.url = url
        self.cause = cause


class TransportTimeoutError(RuntimeError):
    """Request exceeded the configured timeout (retryable by policy)."""

    def __init__(self, url: str, timeout: float) -> None:
        super().__init__(
            f"transport timeout after {timeout}s for {url}"
        )
        self.url = url
        self.timeout = timeout


class TransportHTTPError(RuntimeError):
    """Non-2xx HTTP status (NOT auto-retried — surfaced to policy)."""

    def __init__(self, url: str, status: int, body: str) -> None:
        super().__init__(
            f"HTTP {status} for {url}: {body[:200]}"
        )
        self.url = url
        self.status = status
        self.body = body


class TransportProtocolError(RuntimeError):
    """2xx but the response violates transport-level expectations
    (oversized, undecodable). Never silently truncated."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"transport protocol violation for {url}: {reason}"
        )
        self.url = url
        self.reason = reason


class HttpGetTransport:
    """Single-attempt anonymous HTTP GET returning the raw text body.

    Parameters
    ----------
    timeout:
        Per-request socket timeout in seconds (hard requirement —
        there is no default-forever path).
    sleeper:
        Injectable sleep function (default :func:`time.sleep`) so
        bounded backoff behaviour is deterministically testable.
    """

    def __init__(self, timeout: float, sleeper: Callable[[float], None] | None = None) -> None:
        if timeout is None or timeout <= 0:
            raise ValueError(
                f"transport timeout must be a positive number of seconds "
                f"(got {timeout!r}) — no default-forever sockets"
            )
        import time

        self._timeout = float(timeout)
        self._sleeper = sleeper if sleeper is not None else time.sleep

    @property
    def timeout(self) -> float:
        return self._timeout

    def backoff_sleep(self, seconds: float) -> None:
        """Policy hook: sleep (injectable) between bounded retries."""
        if seconds > 0:
            self._sleeper(seconds)

    def get(self, base_url: str, params: Mapping[str, str]) -> str:
        """Perform ONE anonymous GET and return the raw response text.

        Raises the typed transport errors above — never swallows a
        failure into an empty/short response.
        """
        query = urllib.parse.urlencode(
            {k: str(v) for k, v in sorted(params.items())}
        )
        url = f"{base_url}?{query}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                # Identify the project honestly; no browser spoofing.
                "User-Agent": "ai-trading-lab-data-engine/0.1 (paper-only)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout
            ) as response:
                status = response.status
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # HTTPError IS a response — read its (bounded) body for
            # diagnostics, then surface the typed failure.
            try:
                detail = exc.read(4096).decode("utf-8", "replace")
            except Exception:  # pragma: no cover - diagnostic only
                detail = ""
            raise TransportHTTPError(url, exc.code, detail) from exc
        except socket.timeout as exc:
            raise TransportTimeoutError(url, self._timeout) from exc
        except TimeoutError as exc:
            raise TransportTimeoutError(url, self._timeout) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.timeout):
                raise TransportTimeoutError(url, self._timeout) from exc
            raise TransportConnectError(url, exc) from exc
        except OSError as exc:
            raise TransportConnectError(url, exc) from exc

        if status < 200 or status >= 300:
            raise TransportProtocolError(
                url, f"unexpected success-status band {status}"
            )
        if len(body) > MAX_RESPONSE_BYTES:
            raise TransportProtocolError(
                url,
                f"response exceeds the {MAX_RESPONSE_BYTES}-byte cap — "
                "refusing to buffer or truncate (fail closed)",
            )
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransportProtocolError(
                url, f"response is not valid UTF-8: {exc}"
            ) from exc
        return text
