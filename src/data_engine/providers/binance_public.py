"""Binance public spot klines adapter — the CRYPTO market-data pilot.

PAPER-ONLY FEED MACHINERY. This adapter is structurally incapable of
trading: it only ever issues anonymous GET requests to two PUBLIC
market-data endpoints (``/api/v3/ping`` and ``/api/v3/klines``). There
is no API key, no account endpoint, no order endpoint, no signed
request, and the adapter REFUSES a configuration that names an API-key
environment variable (a public-data adapter that expects credentials
is a misconfiguration — fail closed at construction).

Scope: narrow pilot — BTCUSDT on Binance spot, interval set
{1m, 5m, 15m, 1h, 4h, 1d}. Additional symbols require explicit
allowlist extension plus mapping/quality validation first (the default
allowlist is exactly ``["BTCUSDT"]``).

Contract conformance (existing framework, NOT a second framework):
subclasses :class:`data_engine.provider.MarketDataProvider`, returns
schema-validated :class:`data_engine.schemas.Candle` objects, and
registers itself with :class:`data_engine.provider.ProviderFactory`
under ``"binance-public-spot"``.

Design guarantees (paper-readiness mandate Phase B):

- **Network/validation separation**: all HTTP behaviour lives in the
  injectable transport; every method below the transport boundary is
  pure parsing/validation. Unit tests inject a fake transport — no
  live network in CI.
- **UTC-aware deterministic timestamps**: kline ``open_time`` (ms
  epoch, UTC by Binance contract) → timezone-aware UTC datetimes.
  Interval alignment is verified (``open_time % interval_ms == 0``).
- **Closed-candle enforcement**: a kline is CLOSED only when its
  ``close_time`` is strictly in the past of the evaluation reference
  time. ``closed_only=True`` (the default) EXCLUDES the still-open
  candle — strategies must never consume a candle before its close.
  Excluded-open-candle counts are reported in fetch metadata, never
  fabricated into a completed candle.
- **OHLC validation**: every row goes through the strict frozen
  :class:`Candle` schema (positive prices, ``low <= open/close <=
  high`` enforced at construction). Violations raise
  :class:`BinanceDataError` naming the row index — fail closed, no
  silent drops.
- **Duplicates / ordering**: duplicate or regressing ``open_time``
  values raise :class:`BinanceDataError` (fail closed).
- **Gap reporting**: missing intervals inside a fetched window are
  REPORTED in fetch metadata (crypto trades ~24/7, so gaps indicate
  listing/venue anomalies the operator must see) — the hard gap gate
  stays with ``runtime.data_gate.validate_bars`` (1.5x interval).
- **Bounded pagination + bounded retries**: at most ``max_pages``
  kline pages per fetch (each <= 1000 rows), at most
  ``max_attempts`` transport attempts with exponential backoff on
  connect/timeout ONLY. HTTP 429/418 map to
  :class:`BinanceRateLimitedError` (caller backs off — no retry
  storm); other HTTP errors raise immediately.
- **Client-side rate-limit guard**: requests are counted in a
  rolling 60s window; exceeding ``rate_limit_per_minute`` raises
  :class:`BinanceRateLimitedError` before the network is touched.
- **Raw-response preservation**: every page's raw JSON text, its
  SHA-256 content hash, the exact request parameters and the
  retrieval timestamp are retained in ``last_fetch_raw`` and surfaced
  through :meth:`retrieve_raw` (idempotent re-derivation of
  provenance).
- **No fabricated fields**: quote-asset volume / trade counts are
  available on the wire but NOT represented in ``Candle`` — nothing
  is invented for unavailable fields (bid/ask stay ``None``).

Source-governance note (honest): this adapter provides ENDPOINT
CONNECTIVITY and DATA MECHANICS only. It does NOT constitute source
approval: ``binance-public-spot`` enters the governed
:class:`~data_engine.prediction.source_registry.DataSourceRegistry`
as UNVETTED and stays UNVETTED until the operator records the human
SRC-APPROVAL decision (see docs/OPERATOR_SOURCE_APPROVAL_PACK.md).
The 32-gate ``OPERATIONAL_FEED_READY`` verdict remains FALSE until
then — by construction, not by policy text.
"""

from __future__ import annotations

import hashlib
import json
import math
import time as _time
from collections import deque
from datetime import datetime, UTC
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from data_engine.provider import MarketDataProvider, ProviderFactory
from data_engine.schemas import (
    AssetClass,
    Candle,
    ContractType,
    Instrument,
    Instrument as InstrumentSchema,
    ProviderConfig,
    Timeframe,
)
from data_engine.providers.transport import (
    HttpGetTransport,
    TransportConnectError,
    TransportHTTPError,
    TransportTimeoutError,
)

__all__ = [
    "BINANCE_PUBLIC_PROVIDER_NAME",
    "DEFAULT_ENDPOINT",
    "BinancePublicError",
    "BinanceTransportError",
    "BinanceRateLimitedError",
    "BinanceHTTPError",
    "BinanceResponseError",
    "BinanceDataError",
    "BinancePublicKlinesProvider",
    "DEFAULT_QUOTE_SUFFIXES",
]

#: Provider name registered in the ProviderFactory.
BINANCE_PUBLIC_PROVIDER_NAME = "binance-public-spot"

#: Public REST base (no credentials, market-data endpoints only).
DEFAULT_ENDPOINT = "https://api.binance.com/api/v3"

KLINES_PATH = "klines"
PING_PATH = "ping"

#: Binance klines page hard limit.
MAX_PAGE_LIMIT = 1000

#: Conservative default client-side request budget (Binance's IP
#: weight budget is larger; a paper poller needs a tiny fraction).
DEFAULT_RATE_LIMIT_PER_MINUTE = 120

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_PAGES = 10
DEFAULT_BACKOFF_BASE_SECONDS = 0.5

#: Supported timeframes — Binance interval strings equal the engine's
#: Timeframe values exactly (identity mapping, no conversion).
BINANCE_INTERVALS: Dict[Timeframe, str] = {
    Timeframe.M1: "1m",
    Timeframe.M5: "5m",
    Timeframe.M15: "15m",
    Timeframe.H1: "1h",
    Timeframe.H4: "4h",
    Timeframe.D1: "1d",
}

INTERVAL_SECONDS: Dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}

#: Quote assets recognised for concatenated-symbol decomposition
#: (longest first so "BTCUSDT" → base "BTC", quote "USDT", never
#: "BTCU"/"SDT"). This is a PARSE of the provider's own symbol
#: convention — the canonical instrument still must exist in the
#: instrument registry for the feed gate to pass (fail closed on
#: unmapped symbols).
DEFAULT_QUOTE_SUFFIXES: tuple = (
    "USDT", "FDUSD", "USDC", "TUSD", "BUSD", "USDS", "USD", "EUR",
    "GBP", "TRY", "BRL", "ARS", "JPY", "RUB", "UAH", "DAI", "BTC",
    "ETH", "BNB", "SOL", "XRP", "DOGE", "TRX", "DOT", "IDRT", "NGN",
    "ZAR", "MXN", "CZK", "PLN", "RON", "HRK", "BIDR", "UAH",
)


class BinancePublicError(RuntimeError):
    """Base class for Binance public-adapter failures (fail closed)."""


class BinanceTransportError(BinancePublicError):
    """Connectivity exhausted after bounded retries (no retry storm)."""


class BinanceRateLimitedError(BinancePublicError):
    """Provider signalled rate limiting (HTTP 429/418) or the
    client-side rolling budget was exhausted."""


class BinanceHTTPError(BinancePublicError):
    """Other non-2xx provider response (surfaced, never swallowed)."""


class BinanceResponseError(BinancePublicError):
    """2xx response whose payload violates the documented klines
    envelope (malformed JSON / wrong shape)."""


class BinanceDataError(BinancePublicError):
    """Payload parsed, but a DATA invariant failed (OHLC violation,
    duplicate/regressing timestamps, misaligned interval, non-finite
    or non-positive values). The offending row index is named."""


class BinancePublicKlinesProvider(MarketDataProvider):
    """Public spot-klines provider for the crypto pilot (BTCUSDT).

    Parameters
    ----------
    config:
        ``ProviderConfig`` with ``provider_name='binance-public-spot'``.
        ``api_key_env_var`` MUST be None (public-only; set values are
        refused at construction). ``endpoint`` defaults to the public
        REST base.
    registry:
        Canonical instrument registry used for symbol mapping.
    transport:
        Injectable single-attempt GET transport
        (:class:`~data_engine.providers.transport.HttpGetTransport`
        by default). Unit tests substitute a fake here — everything
        below this boundary is pure and deterministic.
    as_of:
        Injectable evaluation reference time for closed-candle
        enforcement (deterministic tests). ``None`` (default) means
        "wall clock at fetch time" — legitimate here because
        open/closed is a freshness property of the FEED, not part of
        any deterministic identity.
    closed_only:
        Exclude the still-open candle (default True — strategies
        never consume an unclosed candle).
    max_attempts / backoff_base:
        Bounded retry policy for connect/timeout transport failures.
    max_pages:
        Pagination bound per fetch (<= max_pages kline pages).
    """

    def __init__(
        self,
        config: ProviderConfig,
        registry: Optional[Any] = None,
        *,
        transport: Optional[HttpGetTransport] = None,
        as_of: Optional[datetime] = None,
        closed_only: bool = True,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        backoff_base: float = DEFAULT_BACKOFF_BASE_SECONDS,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        if config.api_key_env_var is not None:
            raise BinancePublicError(
                "binance-public-spot is a PUBLIC market-data adapter: "
                f"api_key_env_var={config.api_key_env_var!r} is refused "
                "(no credentials exist on this path — fail closed on "
                "misconfiguration)"
            )
        if not config.endpoint or not config.endpoint.startswith("https://"):
            raise BinancePublicError(
                "endpoint must be an explicit https:// URL for the "
                "Binance public adapter (got "
                f"{config.endpoint!r})"
            )
        if config.instrument_allowlist is None:
            # Narrow pilot default — NOT an open door. Operators add
            # symbols only after mapping + quality validation.
            config = config.model_copy(
                update={"instrument_allowlist": ["BTCUSDT"]}
            )
        if max_attempts < 1 or max_pages < 1:
            raise BinancePublicError(
                "max_attempts and max_pages must be >= 1 (bounded by "
                "construction)"
            )
        super().__init__(config, registry)
        self._transport = transport if transport is not None else HttpGetTransport(
            timeout=DEFAULT_TIMEOUT_SECONDS
        )
        self._as_of = as_of
        self._closed_only = closed_only
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._max_pages = max_pages
        self._request_times: deque = deque()
        self._rate_limit = (
            config.rate_limit_per_minute
            or DEFAULT_RATE_LIMIT_PER_MINUTE
        )
        #: Metadata for the most recent fetch (raw preservation).
        self.last_fetch_raw: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Public provider surface (framework contract)
    # ------------------------------------------------------------------
    def fetch_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        """Fetch CLOSED klines for [start, end) — fail-closed.

        Raises the typed :class:`BinancePublicError` hierarchy on any
        transport, protocol, envelope or data-quality failure. An
        empty list is returned ONLY for a window with no klines at
        all (e.g. entirely in the future); it is never used to mask a
        failure.
        """
        symbol = self._validate_symbol(instrument)
        interval = self._validate_timeframe(timeframe)
        start_utc = self._require_utc(start, "start")
        end_utc = self._require_utc(end, "end")
        if end_utc <= start_utc:
            raise BinancePublicError(
                f"end ({end_utc.isoformat()}) must be after start "
                f"({start_utc.isoformat()})"
            )

        interval_ms = INTERVAL_SECONDS[timeframe] * 1000
        start_ms = int(start_utc.timestamp() * 1000)
        end_ms = int(end_utc.timestamp() * 1000)
        # Align the first request to the interval grid containing
        # start (Binance klines are grid-aligned; this is a REQUEST
        # param choice, not a data rewrite).
        cursor = (start_ms // interval_ms) * interval_ms

        reference = self._as_of or datetime.now(UTC)
        reference_ms = int(reference.timestamp() * 1000)

        rows: List[list] = []
        pages: List[Dict[str, Any]] = []
        page_index = 0
        while cursor < end_ms and page_index < self._max_pages:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": str(cursor),
                "endTime": str(end_ms),
                "limit": str(MAX_PAGE_LIMIT),
            }
            fetched_at = datetime.now(UTC).isoformat()
            text = self._bounded_get(params)
            page_rows = self._parse_envelope(text)
            pages.append(
                {
                    "params": dict(params),
                    "retrieved_at": fetched_at,
                    "row_count": len(page_rows),
                    "raw_sha256": hashlib.sha256(
                        text.encode("utf-8")
                    ).hexdigest(),
                }
            )
            if not page_rows:
                break
            rows.extend(page_rows)
            last_open = int(page_rows[-1][0])
            cursor = last_open + interval_ms
            page_index += 1

        candles, skipped_open, gaps = self._rows_to_candles(
            rows,
            timeframe=timeframe,
            interval_ms=interval_ms,
            reference_ms=reference_ms,
            end_ms=end_ms,
        )
        self.last_fetch_raw = {
            "endpoint": self.config.endpoint,
            "path": KLINES_PATH,
            "symbol": symbol,
            "interval": interval,
            "window": {
                "start": start_utc.isoformat(),
                "end": end_utc.isoformat(),
            },
            "pages": pages,
            "raw_row_count": len(rows),
            "candle_count": len(candles),
            "open_candles_excluded": skipped_open,
            "gaps_reported": gaps,
            "closed_only": self._closed_only,
            "evaluation_reference": reference.isoformat(),
        }
        return candles

    def fetch_instrument_info(self, symbol: str) -> Optional[Instrument]:
        """Resolve the provider symbol to a canonical instrument.

        Registry-first: an existing canonical record (with its own
        ``provider_symbol`` mapping) WINS — the adapter never invents
        a competing canonical identity. Only when the registry has no
        entry does the adapter return the provider's OWN honest
        decomposition (BTCUSDT → BTC/USDT spot on BINANCE), clearly
        venue-labelled; the feed gate still fails closed on
        unconfirmed mapping unless the operator registers it.
        """
        provider_symbol = self._validate_symbol(symbol)
        canonical = self._canonical_symbol(provider_symbol)
        registered = self.registry.get(canonical)
        if registered is not None:
            return registered
        base, quote = self._split_pair(provider_symbol)
        return InstrumentSchema(
            symbol=canonical,
            asset_class=AssetClass.CRYPTO,
            base_asset=base,
            quote_asset=quote,
            exchange="BINANCE",
            venue="BINANCE-SPOT",
            contract_type=ContractType.SPOT,
            currency=quote,
            provider_symbol=provider_symbol,
        )

    def check_connectivity(self) -> bool:
        """Anonymous ping — True iff the public endpoint responds.

        Connectivity evidence ONLY (never a readiness claim). This
        method never raises: transport failures return False, and the
        failure detail is kept in :attr:`last_fetch_raw` under the
        ``last_connectivity`` key for diagnostics.
        """
        fetched_at = datetime.now(UTC).isoformat()
        try:
            text = self._ping()
        except BinancePublicError as exc:
            self.last_fetch_raw["last_connectivity"] = {
                "checked_at": fetched_at,
                "ok": False,
                "error": str(exc),
            }
            return False
        self.last_fetch_raw["last_connectivity"] = {
            "checked_at": fetched_at,
            "ok": True,
            "raw": text,
        }
        return True

    # ------------------------------------------------------------------
    # Provenance-preserving raw retrieval (framework contract)
    # ------------------------------------------------------------------
    def retrieve_raw(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Dict:
        """Retrieve candles + full raw-response provenance metadata.

        The framework's raw layer: immutable-after-ingestion raw data
        plus the adapter's page-level content hashes, request
        parameters, retrieval timestamps and gap/open-candle reports
        (idempotent provenance — see DataIngester).
        """
        candles = self.fetch_candles(instrument, timeframe, start, end)
        return {
            "raw_data": candles,
            "provider": self.config.provider_name,
            "provider_type": self.config.provider_type,
            "instrument": instrument,
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "retrieval_timestamp": datetime.now(UTC).isoformat(),
            "timezone": "UTC",
            "candle_count": len(candles),
            "api_key_loaded": False,
            "fetch_metadata": dict(self.last_fetch_raw),
        }

    # ------------------------------------------------------------------
    # Internal: bounded transport with typed failure mapping
    # ------------------------------------------------------------------
    def _ping(self) -> str:
        """Single bounded GET to /api/v3/ping (connectivity probe).

        Raw urllib exceptions are normalised to the adapter's typed
        hierarchy (connect/timeout/http) — a probe failure is never
        an unhandled crash.
        """
        import urllib.error

        url = f"{self.config.endpoint}/{PING_PATH}"
        try:
            with _urlopen_bounded(url, self._transport.timeout) as resp:
                body = resp.read(4096)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 418):
                raise BinanceRateLimitedError(
                    f"ping rate-limited (HTTP {exc.code})"
                ) from exc
            raise BinanceHTTPError(
                f"ping failed: HTTP {exc.code}"
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise BinanceTransportError(
                f"ping transport failure: {exc!r}"
            ) from exc
        return body.decode("utf-8", "replace")

    def _bounded_get(self, params: Mapping[str, str]) -> str:
        """Bounded retries on connect/timeout ONLY; typed mapping."""
        self._respect_rate_budget()
        last_error: Optional[BinancePublicError] = None
        for attempt in range(self._max_attempts):
            try:
                return self._transport.get(
                    f"{self.config.endpoint}/{KLINES_PATH}", params
                )
            except TransportHTTPError as exc:
                if exc.status in (429, 418):
                    raise BinanceRateLimitedError(
                        f"Binance signalled rate limiting (HTTP "
                        f"{exc.status}); caller must back off — this "
                        f"adapter does NOT hammer through it: {exc}"
                    ) from exc
                raise BinanceHTTPError(str(exc)) from exc
            except (TransportConnectError, TransportTimeoutError) as exc:
                last_error = BinanceTransportError(
                    f"bounded transport failure (attempt "
                    f"{attempt + 1}/{self._max_attempts}): {exc}"
                )
                if attempt + 1 < self._max_attempts:
                    self._transport.backoff_sleep(
                        self._backoff_base * (2 ** attempt)
                    )
        raise last_error or BinanceTransportError("unreachable")

    def _respect_rate_budget(self) -> None:
        """Client-side rolling 60s request budget (no retry storms)."""
        now = _time.monotonic()
        while self._request_times and now - self._request_times[0] > 60.0:
            self._request_times.popleft()
        if len(self._request_times) >= self._rate_limit:
            raise BinanceRateLimitedError(
                f"client-side rate budget exhausted: "
                f"{self._rate_limit} requests/minute (rolling window) — "
                "refusing to issue another request"
            )
        self._request_times.append(now)

    def _map_transport_error(
        self, url: str, exc: BaseException
    ) -> BinancePublicError:
        from data_engine.providers.transport import (
            TransportProtocolError,
        )

        if isinstance(exc, TransportHTTPError):
            if exc.status in (429, 418):
                return BinanceRateLimitedError(str(exc))
            return BinanceHTTPError(str(exc))
        if isinstance(exc, TransportProtocolError):
            return BinanceResponseError(str(exc))
        return BinanceTransportError(str(exc))

    # ------------------------------------------------------------------
    # Internal: pure parsing + validation (no network below here)
    # ------------------------------------------------------------------
    def _parse_envelope(self, text: str) -> List[list]:
        """Parse one klines page (list of row lists) — strict shape."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BinanceResponseError(
                f"klines payload is not valid JSON: {exc}"
            ) from exc
        if not isinstance(payload, list):
            raise BinanceResponseError(
                "klines payload must be a JSON array of rows (got "
                f"{type(payload).__name__})"
            )
        for i, row in enumerate(payload):
            if not isinstance(row, list) or len(row) < 7:
                raise BinanceResponseError(
                    f"kline row {i} must be an array with >= 7 fields "
                    f"(got {type(row).__name__}, len="
                    f"{len(row) if isinstance(row, list) else 'n/a'})"
                )
        return payload

    def _rows_to_candles(
        self,
        rows: Sequence[list],
        *,
        timeframe: Timeframe,
        interval_ms: int,
        reference_ms: int,
        end_ms: int,
    ) -> tuple:
        """Convert raw rows to validated CLOSED candles.

        Fail-closed on: duplicate open_time, regressing open_time,
        misaligned open_time, non-finite/non-positive numerics,
        impossible OHLC (via the frozen Candle schema), close_time
        before open_time. Open candles are EXCLUDED (counted) when
        ``closed_only``; gaps between consecutive kept candles are
        REPORTED (not fabricated — the hard gap gate lives in the
        runtime data gate).
        """
        candles: List[Candle] = []
        skipped_open = 0
        gaps: List[Dict[str, int]] = []
        seen_open_ms: set = set()
        last_open_ms: Optional[int] = None

        for i, row in enumerate(rows):
            try:
                open_ms = int(row[0])
                close_ms = int(row[6])
                o = float(row[1])
                h = float(row[2])
                low = float(row[3])
                c = float(row[4])
                v = float(row[5])
            except (TypeError, ValueError) as exc:
                raise BinanceDataError(
                    f"kline row {i}: non-numeric field ({exc})"
                ) from exc

            if open_ms in seen_open_ms:
                raise BinanceDataError(
                    f"kline row {i}: duplicate open_time {open_ms} "
                    "(provider must not repeat klines — fail closed)"
                )
            if last_open_ms is not None and open_ms < last_open_ms:
                raise BinanceDataError(
                    f"kline row {i}: open_time {open_ms} regresses "
                    f"before previous {last_open_ms} (out-of-order feed)"
                )
            if open_ms % interval_ms != 0:
                raise BinanceDataError(
                    f"kline row {i}: open_time {open_ms} is not aligned "
                    f"to the {timeframe.value} interval grid"
                )
            if close_ms < open_ms:
                raise BinanceDataError(
                    f"kline row {i}: close_time {close_ms} precedes "
                    f"open_time {open_ms} (impossible row)"
                )
            for name, value in (
                ("open", o), ("high", h), ("low", low), ("close", c),
            ):
                if not math.isfinite(value) or value <= 0:
                    raise BinanceDataError(
                        f"kline row {i}: {name}={value!r} must be a "
                        "finite positive number"
                    )
            if not math.isfinite(v) or v < 0:
                raise BinanceDataError(
                    f"kline row {i}: volume={v!r} must be finite and "
                    "non-negative"
                )

            # -- closed-candle enforcement --------------------------------
            is_closed = close_ms < reference_ms
            if not is_closed:
                skipped_open += 1
                if self._closed_only:
                    continue

            if (
                last_open_ms is not None
                and open_ms - last_open_ms > interval_ms
            ):
                gaps.append(
                    {
                        "after_open_ms": last_open_ms,
                        "next_open_ms": open_ms,
                        "missing_intervals": (
                            (open_ms - last_open_ms) // interval_ms - 1
                        ),
                    }
                )

            try:
                candle = Candle(
                    timestamp=datetime.fromtimestamp(
                        open_ms / 1000.0, tz=UTC
                    ),
                    open=o,
                    high=h,
                    low=low,
                    close=c,
                    volume=v,
                    timeframe=timeframe,
                )
            except ValueError as exc:
                raise BinanceDataError(
                    f"kline row {i}: OHLC schema violation — {exc}"
                ) from exc

            candles.append(candle)
            seen_open_ms.add(open_ms)
            last_open_ms = open_ms

        # Window honesty: bars at/after end are not requested; rows
        # beyond end_ms (inclusive endTime semantics) are dropped ONLY
        # with an explicit boundary note — never silently.
        bounded = [
            candle for candle in candles
            if int(candle.timestamp.timestamp() * 1000) < end_ms
        ]
        if len(bounded) != len(candles):
            gaps.append(
                {
                    "boundary": "end",
                    "dropped_rows": len(candles) - len(bounded),
                    "note": "rows at/after the exclusive end bound",
                }
            )
        return bounded, skipped_open, gaps

    # ------------------------------------------------------------------
    # Internal: symbol / timeframe / timestamp validation
    # ------------------------------------------------------------------
    def _validate_symbol(self, instrument: str) -> str:
        if not isinstance(instrument, str) or not instrument.strip():
            raise BinancePublicError(
                "instrument must be a non-empty provider symbol string"
            )
        symbol = instrument.strip().upper()
        allowlist = self.config.instrument_allowlist or []
        if symbol not in allowlist:
            raise BinancePublicError(
                f"provider symbol {symbol!r} is not in the pilot "
                f"allowlist {allowlist} — extend the allowlist only "
                "after mapping and quality validation (fail closed)"
            )
        return symbol

    def _validate_timeframe(self, timeframe: Timeframe) -> str:
        if timeframe not in BINANCE_INTERVALS:
            raise BinancePublicError(
                f"timeframe {timeframe!r} is not supported by the "
                f"Binance public klines adapter (supported: "
                f"{sorted(t.value for t in BINANCE_INTERVALS)})"
            )
        return BINANCE_INTERVALS[timeframe]

    def _require_utc(self, value: datetime, name: str) -> datetime:
        if value.tzinfo is None:
            raise BinancePublicError(
                f"{name} must be a timezone-aware datetime (naive "
                "timestamps are ambiguous — refused)"
            )
        return value.astimezone(UTC)

    def _canonical_symbol(self, provider_symbol: str) -> str:
        base, quote = self._split_pair(provider_symbol)
        return f"{base}/{quote}"

    def _split_pair(self, provider_symbol: str) -> tuple:
        for quote in DEFAULT_QUOTE_SUFFIXES:
            if provider_symbol.endswith(quote) and len(provider_symbol) > len(quote):
                base = provider_symbol[: -len(quote)]
                if base and base.isalpha():
                    return base, quote
        raise BinancePublicError(
            f"provider symbol {provider_symbol!r} cannot be decomposed "
            "into a known base/quote pair (refusing to guess a mapping)"
        )


# ---------------------------------------------------------------------------
# Ping helper (stdlib, bounded) — kept separate for clarity/testability.
# ---------------------------------------------------------------------------
class _urlopen_bounded:
    """Context manager: one bounded anonymous GET to a full URL."""

    def __init__(self, url: str, timeout: float) -> None:
        import urllib.request

        self._req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": (
                    "ai-trading-lab-data-engine/0.1 (paper-only)"
                ),
                "Accept": "application/json",
            },
        )
        self._timeout = timeout
        self._response = None

    def __enter__(self):
        import urllib.request

        self._response = urllib.request.urlopen(
            self._req, timeout=self._timeout
        )
        return self._response

    def __exit__(self, *exc_info) -> bool:
        if self._response is not None:
            self._response.close()
        return False


# Register with the EXISTING factory (no second framework).
ProviderFactory.register(
    BINANCE_PUBLIC_PROVIDER_NAME, BinancePublicKlinesProvider
)
