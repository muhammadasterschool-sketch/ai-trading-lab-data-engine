"""Regression tests: Binance public spot-klines adapter (crypto pilot).

DETERMINISTIC, OFFLINE. Every network response is a SANITIZED
FIXTURE served by a fake transport that mimics the DOCUMENTED shape
of Binance klines rows:

    [ open_time_ms, "open", "high", "low", "close", "volume",
      close_time_ms, quote_volume, trades, taker_base, taker_quote,
      ignore ]

These fixtures are NOT live data and are NOT evidence of anything
about the real Binance service — they exist to prove the adapter's
parsing, validation, ordering, closed-candle enforcement, pagination,
bounded-retry and provenance mechanics. (The optional live smoke
script lives OUTSIDE the test tree: scripts/
binance_public_smoke.py — never collected by pytest, never a
readiness claim.)

Source governance: ``binance-public-spot`` is an UNVETTED candidate
(see tests/test_feed_composition.py for the gate-level consequences).
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.prediction.source_registry import (
    DataSourceRegistry,
)
from data_engine.provider import ProviderFactory
from data_engine.schemas import (
    Instrument,
    AssetClass,
    ProviderConfig,
    Timeframe,
)
from data_engine.providers.transport import (
    TransportConnectError,
    TransportHTTPError,
    TransportTimeoutError,
)
from data_engine.providers.binance_public import (
    BINANCE_PUBLIC_PROVIDER_NAME,
    BinanceDataError,
    BinanceHTTPError,
    BinancePublicError,
    BinancePublicKlinesProvider,
    BinanceRateLimitedError,
    BinanceResponseError,
    BinanceTransportError,
)

# Reference time for all deterministic fixtures (session-logical).
AS_OF = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
INTERVAL_MS = 900_000  # 15 minutes
WARMUP_BARS = 30


def _kline_row(open_ms: int, o=100.0, h=101.0, low=99.0, c=100.5,
               volume=12.5, close_ms=None):
    """One sanitized kline row in the documented 12-field shape."""
    return [
        open_ms, str(o), str(h), str(low), str(c), str(volume),
        close_ms if close_ms is not None else open_ms + INTERVAL_MS - 1,
        "1234.5", 96, "6.2", "6.1", "0",
    ]


def _closed_rows(n, *, end_ms=None, start_price=100.0):
    """n grid-aligned CLOSED klines ending just before end_ms."""
    if end_ms is None:
        end_ms = int(AS_OF.timestamp() * 1000)
    end_ms = (end_ms // INTERVAL_MS) * INTERVAL_MS
    first_open = end_ms - n * INTERVAL_MS
    rows = []
    price = start_price
    for i in range(n):
        open_ms = first_open + i * INTERVAL_MS
        o = price
        c = round(price + 0.5, 2)
        h = round(max(o, c) + 1.0, 2)
        low = round(min(o, c) - 1.0, 2)
        rows.append(_kline_row(open_ms, o=o, h=h, low=low, c=c))
        price = c
    return rows


class FakeTransport:
    """Deterministic single-attempt transport (offline fixtures)."""

    def __init__(self, pages, *, http_statuses=None, failures=None):
        # pages: list[str] — JSON texts returned in order
        self.pages = list(pages)
        self.http_statuses = list(http_statuses or [])
        self.failures = list(failures or [])
        self.calls = []          # (url, params) per attempt
        self.sleeps = []         # backoff seconds requested
        self.timeout = 10.0

    def backoff_sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def get(self, base_url, params):
        self.calls.append((base_url, dict(params)))
        if self.failures:
            raise self.failures.pop(0)
        if self.http_statuses:
            raise TransportHTTPError("u", self.http_statuses.pop(0), "")
        if not self.pages:
            return "[]"
        return self.pages.pop(0)


def _provider(transport, **overrides):
    kwargs = dict(
        transport=transport,
        as_of=AS_OF,
        closed_only=True,
        max_attempts=3,
        backoff_base=0.5,
    )
    kwargs.update(overrides)
    config = ProviderConfig(
        provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
        provider_type="api",
        endpoint="https://api.binance.com/api/v3",
        rate_limit_per_minute=10_000,  # never the unit-test bottleneck
    )
    return BinancePublicKlinesProvider(config, **kwargs)


def _window():
    return AS_OF - timedelta(minutes=15 * WARMUP_BARS), AS_OF


# ════════════════════════════════════════════════════════════════════
# 1. Construction / configuration guards (fail closed)
# ════════════════════════════════════════════════════════════════════

class TestConstruction:
    def test_registered_with_existing_factory(self):
        names = ProviderFactory.registered_providers()
        assert BINANCE_PUBLIC_PROVIDER_NAME in names
        assert "file" in names  # existing framework untouched

    def test_api_key_env_var_refused(self):
        config = ProviderConfig(
            provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
            provider_type="api",
            endpoint="https://api.binance.com/api/v3",
            api_key_env_var="BINANCE_KEY",
        )
        with pytest.raises(BinancePublicError, match="PUBLIC"):
            BinancePublicKlinesProvider(config)

    def test_non_https_endpoint_refused(self):
        config = ProviderConfig(
            provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
            provider_type="api",
            endpoint="http://api.binance.com/api/v3",
        )
        with pytest.raises(BinancePublicError, match="https"):
            BinancePublicKlinesProvider(config)

    def test_default_allowlist_is_btcusdt_only_pilot(self):
        p = _provider(FakeTransport([]))
        assert p.config.instrument_allowlist == ["BTCUSDT"]

    def test_symbol_outside_allowlist_refused(self):
        p = _provider(FakeTransport([]))
        with pytest.raises(BinancePublicError, match="allowlist"):
            p.fetch_candles("ETHUSDT", Timeframe.M15, *_window())

    def test_bogus_timeframe_value_refused(self):
        # All six Timeframe enum members are supported (identity
        # mapping); a non-member value cannot even be constructed as
        # a Timeframe — the adapter's supported-set check stays as
        # defence in depth.
        with pytest.raises(ValueError):
            Timeframe("8h")

    def test_all_engine_timeframes_supported(self):
        from data_engine.providers.binance_public import BINANCE_INTERVALS

        assert set(BINANCE_INTERVALS) == set(Timeframe)

    def test_naive_datetimes_refused(self):
        p = _provider(FakeTransport([]))
        naive = datetime(2026, 10, 11, 11, 0)
        with pytest.raises(BinancePublicError, match="timezone-aware"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, naive, AS_OF)

    def test_end_before_start_refused(self):
        p = _provider(FakeTransport([]))
        with pytest.raises(BinancePublicError, match="after start"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, AS_OF, AS_OF - timedelta(hours=1))


# ════════════════════════════════════════════════════════════════════
# 2. Happy path: closed klines → validated UTC candles
# ════════════════════════════════════════════════════════════════════

class TestHappyPath:
    def test_closed_klines_parse_to_utc_candles(self):
        import json

        rows = _closed_rows(WARMUP_BARS)
        transport = FakeTransport([json.dumps(rows)])
        p = _provider(transport)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

        assert len(candles) == WARMUP_BARS
        first_open_ms = rows[0][0]
        assert candles[0].timestamp == datetime.fromtimestamp(
            first_open_ms / 1000.0, tz=UTC
        )
        assert candles[0].timeframe == Timeframe.M15
        assert candles[0].open == 100.0
        assert candles[0].volume == 12.5
        # Strictly ascending, grid-aligned, all UTC.
        for a, b in zip(candles, candles[1:]):
            assert b.timestamp - a.timestamp == timedelta(minutes=15)
        # Bid/ask untouched (no fabricated fields).
        assert candles[0].bid is None and candles[0].ask is None

    def test_raw_provenance_preserved(self):
        import json

        rows = _closed_rows(WARMUP_BARS)
        payload = json.dumps(rows)
        transport = FakeTransport([payload])
        p = _provider(transport)
        p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

        meta = p.last_fetch_raw
        assert meta["symbol"] == "BTCUSDT"
        assert meta["interval"] == "15m"
        assert meta["raw_row_count"] == WARMUP_BARS
        assert meta["candle_count"] == WARMUP_BARS
        assert meta["open_candles_excluded"] == 0
        assert len(meta["pages"]) == 1
        import hashlib

        assert meta["pages"][0]["raw_sha256"] == hashlib.sha256(
            payload.encode()
        ).hexdigest()
        assert meta["pages"][0]["params"]["limit"] == "1000"

    def test_retrieve_raw_carries_fetch_metadata(self):
        import json

        transport = FakeTransport([json.dumps(_closed_rows(5))])
        p = _provider(transport)
        raw = p.retrieve_raw("BTCUSDT", Timeframe.M15, *_window())
        assert raw["provider"] == BINANCE_PUBLIC_PROVIDER_NAME
        assert raw["api_key_loaded"] is False
        assert raw["timezone"] == "UTC"
        assert "fetch_metadata" in raw
        assert raw["fetch_metadata"]["symbol"] == "BTCUSDT"

    def test_deterministic_repeat(self):
        import json

        pages = [json.dumps(_closed_rows(WARMUP_BARS))]
        p1 = _provider(FakeTransport(list(pages)))
        p2 = _provider(FakeTransport(list(pages)))
        c1 = p1.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        c2 = p2.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        # Determinism over the market-data identity fields.
        # (provider_timestamp is intentionally wall-clock provenance
        # and is excluded — see schemas.Candle.)
        fields = (
            "timestamp", "open", "high", "low", "close", "volume",
            "timeframe",
        )
        assert [
            tuple(getattr(c, f) for f in fields) for c in c1
        ] == [tuple(getattr(c, f) for f in fields) for c in c2]


# ════════════════════════════════════════════════════════════════════
# 3. Closed-candle enforcement (no open-bar leakage)
# ════════════════════════════════════════════════════════════════════

class TestClosedCandles:
    def test_open_candle_excluded_by_default(self):
        import json

        rows = _closed_rows(5)
        # The LAST in-window kline is still OPEN: its close_time is
        # in the future relative to the reference time.
        rows[-1][6] = int(AS_OF.timestamp() * 1000) + 60_000
        transport = FakeTransport([json.dumps(rows)])
        p = _provider(transport)  # closed_only=True default
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

        assert len(candles) == 4
        assert candles[-1].timestamp < AS_OF
        assert p.last_fetch_raw["open_candles_excluded"] == 1

    def test_open_candle_included_only_when_explicitly_allowed(self):
        import json

        rows = _closed_rows(5)
        rows[-1][6] = int(AS_OF.timestamp() * 1000) + 60_000
        transport = FakeTransport([json.dumps(rows)])
        p = _provider(transport, closed_only=False)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        # The still-open row appears — callers opt in explicitly; the
        # composition layer still refuses bars >= as_of (defence in
        # depth, see tests/test_feed_composition.py).
        assert len(candles) == 5

    def test_window_boundary_rows_are_dropped_with_note(self):
        import json

        # Reference time LATER than the window end: a row between the
        # window end and the reference is CLOSED at reference time but
        # lies at/after the exclusive end bound — dropped with an
        # explicit boundary note (never silently).
        end = AS_OF
        reference = AS_OF + timedelta(hours=2)
        rows = _closed_rows(4)
        beyond = _kline_row(
            int(end.timestamp() * 1000) + INTERVAL_MS
        )
        transport = FakeTransport([json.dumps(list(rows) + [beyond])])
        p = _provider(transport, as_of=reference, closed_only=True)
        start = end - timedelta(minutes=15 * 4)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, start, end)
        assert len(candles) == 4
        boundary_notes = [
            g for g in p.last_fetch_raw["gaps_reported"]
            if g.get("boundary") == "end"
        ]
        assert boundary_notes and boundary_notes[0]["dropped_rows"] == 1


# ════════════════════════════════════════════════════════════════════
# 4. Data-integrity failures (fail closed, row-indexed)
# ════════════════════════════════════════════════════════════════════

class TestDataIntegrity:
    def _fetch(self, rows):
        import json

        transport = FakeTransport([json.dumps(rows)])
        p = _provider(transport)
        return p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

    def test_duplicate_kline_rejected(self):
        rows = _closed_rows(5)
        rows.append(_kline_row(rows[-1][0]))
        with pytest.raises(BinanceDataError, match="duplicate"):
            self._fetch(rows)

    def test_out_of_order_kline_rejected(self):
        rows = _closed_rows(5)
        rows[-1], rows[-2] = rows[-2], rows[-1]
        with pytest.raises(BinanceDataError, match="regresses"):
            self._fetch(rows)

    def test_misaligned_open_time_rejected(self):
        rows = _closed_rows(5)
        rows.append(_kline_row(rows[-1][0] + INTERVAL_MS + 1))
        with pytest.raises(BinanceDataError, match="aligned"):
            self._fetch(rows)

    def test_impossible_ohlc_rejected_by_schema(self):
        rows = _closed_rows(4)
        # Replace the LAST in-window closed row with an impossible
        # OHLC shape at the same grid slot.
        bad = _kline_row(
            rows[3][0], o=100.0, h=98.0, low=99.0, c=100.0
        )
        rows[3] = bad
        with pytest.raises(BinanceDataError, match="OHLC"):
            self._fetch(rows)

    def test_nonpositive_price_rejected(self):
        rows = _closed_rows(3)
        rows.append(_kline_row(rows[-1][0] + INTERVAL_MS, o=0.0))
        with pytest.raises(BinanceDataError, match="finite positive"):
            self._fetch(rows)

    def test_negative_volume_rejected(self):
        rows = _closed_rows(3)
        rows.append(_kline_row(rows[-1][0] + INTERVAL_MS, volume=-1.0))
        with pytest.raises(BinanceDataError, match="volume"):
            self._fetch(rows)

    def test_close_before_open_rejected(self):
        rows = _closed_rows(3)
        bad = _kline_row(rows[-1][0] + INTERVAL_MS)
        bad[6] = bad[0] - 1
        rows.append(bad)
        with pytest.raises(BinanceDataError, match="close_time"):
            self._fetch(rows)

    def test_gap_is_reported_not_fabricated(self):
        import json

        # Seven consecutive grid slots with the 6th row REMOVED: a
        # one-interval gap INSIDE the window, reported (never filled).
        rows = _closed_rows(7)
        del rows[5]
        transport = FakeTransport([json.dumps(rows)])
        p = _provider(transport)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(candles) == 6
        gaps = p.last_fetch_raw["gaps_reported"]
        assert gaps and gaps[0]["missing_intervals"] == 1


# ════════════════════════════════════════════════════════════════════
# 5. Envelope / transport failures (typed, no swallowing)
# ════════════════════════════════════════════════════════════════════

class TestFailures:
    def test_malformed_json_rejected(self):
        transport = FakeTransport(["{not json"])
        p = _provider(transport)
        with pytest.raises(BinanceResponseError, match="JSON"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

    def test_non_array_payload_rejected(self):
        transport = FakeTransport(['{"code": -1121}'])
        p = _provider(transport)
        with pytest.raises(BinanceResponseError, match="array"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

    def test_short_row_rejected(self):
        transport = FakeTransport(["[[123, \"1\", \"2\", \"3\"]]"])
        p = _provider(transport)
        with pytest.raises(BinanceResponseError, match=">= 7"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

    def test_http_429_maps_to_rate_limited_without_retry_storm(self):
        transport = FakeTransport([], http_statuses=[429])
        p = _provider(transport)
        with pytest.raises(BinanceRateLimitedError):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        # Exactly ONE attempt — a rate-limited provider must never be
        # hammered by automatic retries.
        assert len(transport.calls) == 1
        assert transport.sleeps == []

    def test_http_500_maps_to_http_error(self):
        transport = FakeTransport([], http_statuses=[500])
        p = _provider(transport)
        with pytest.raises(BinanceHTTPError):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(transport.calls) == 1

    def test_bounded_retry_on_connect_failure_then_success(self):
        import json

        payload = json.dumps(_closed_rows(WARMUP_BARS))
        transport = FakeTransport(
            [payload],
            failures=[TransportConnectError("u", RuntimeError("dns"))],
        )
        p = _provider(transport)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(candles) == WARMUP_BARS
        assert len(transport.calls) == 2
        assert transport.sleeps == [0.5]

    def test_bounded_retry_exhaustion_raises(self):
        transport = FakeTransport(
            [],
            failures=[
                TransportConnectError("u", RuntimeError("d1")),
                TransportConnectError("u", RuntimeError("d2")),
                TransportConnectError("u", RuntimeError("d3")),
            ],
        )
        p = _provider(transport)
        with pytest.raises(BinanceTransportError, match="attempt 3/3"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(transport.calls) == 3
        assert transport.sleeps == [0.5, 1.0]

    def test_timeout_failure_retried_then_exhausts(self):
        transport = FakeTransport(
            [],
            failures=[
                TransportTimeoutError("u", 10.0),
                TransportTimeoutError("u", 10.0),
                TransportTimeoutError("u", 10.0),
            ],
        )
        p = _provider(transport)
        with pytest.raises(BinanceTransportError):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())

    def test_client_side_rate_budget(self):
        import json

        payload = json.dumps(_closed_rows(2))
        config = ProviderConfig(
            provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
            provider_type="api",
            endpoint="https://api.binance.com/api/v3",
            rate_limit_per_minute=2,
        )
        p = BinancePublicKlinesProvider(
            config, transport=FakeTransport([payload, payload]), as_of=AS_OF
        )
        p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        with pytest.raises(BinanceRateLimitedError, match="budget"):
            p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())


# ════════════════════════════════════════════════════════════════════
# 6. Pagination (bounded, cursor-advancing)
# ════════════════════════════════════════════════════════════════════

class TestPagination:
    def test_two_pages_are_stitched_in_order(self):
        import json

        rows = _closed_rows(20)
        transport = FakeTransport([
            json.dumps(rows[:10]), json.dumps(rows[10:]),
        ])
        p = _provider(transport)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(candles) == 20
        opens = [c.timestamp for c in candles]
        assert opens == sorted(opens)
        assert len(p.last_fetch_raw["pages"]) == 2
        # second page starts after the last row of page one
        second_start = int(rows[10][0])
        assert transport.calls[1][1]["startTime"] == str(second_start)

    def test_empty_page_stops_pagination(self):
        import json

        # Page one returns 3 bars that end well BEFORE the window
        # end (cursor still below end); page two is empty — pagination
        # stops cleanly without fabrication.
        end_ms = (int(AS_OF.timestamp() * 1000) // INTERVAL_MS) * INTERVAL_MS
        first_open = end_ms - 20 * INTERVAL_MS
        rows = [
            _kline_row(first_open + i * INTERVAL_MS) for i in range(3)
        ]
        transport = FakeTransport([json.dumps(rows), "[]"])
        p = _provider(transport)
        candles = p.fetch_candles("BTCUSDT", Timeframe.M15, *_window())
        assert len(candles) == 3
        assert len(transport.calls) == 2  # stopped after the empty page

    def test_max_pages_bound_enforced(self):
        import json

        # A window spanning 50 grid slots served in disjoint pages
        # of 10: with max_pages=3 the fetch stops after 3 pages —
        # bounded pagination, no unbounded loop, no fabrication.
        total_slots = 50
        end_ms = (int(AS_OF.timestamp() * 1000) // INTERVAL_MS) * INTERVAL_MS
        first_open = end_ms - total_slots * INTERVAL_MS
        pages = []
        for chunk in range(0, total_slots, 10):
            page_rows = [
                _kline_row(first_open + (chunk + i) * INTERVAL_MS)
                for i in range(10)
            ]
            pages.append(json.dumps(page_rows))
        transport = FakeTransport(pages)
        p = _provider(transport, max_pages=3)
        start = AS_OF - timedelta(minutes=15 * total_slots)
        p.fetch_candles("BTCUSDT", Timeframe.M15, start, AS_OF)
        assert len(transport.calls) == 3  # hard bound respected


# ════════════════════════════════════════════════════════════════════
# 7. Instrument mapping (registry-first, honest decomposition)
# ════════════════════════════════════════════════════════════════════

class TestInstrumentMapping:
    def test_registered_canonical_instrument_wins(self):
        from data_engine.instruments import InstrumentRegistry

        registry = InstrumentRegistry()
        registry.register(Instrument(
            symbol="BTC/USDT",
            asset_class=AssetClass.CRYPTO,
            base_asset="BTC",
            quote_asset="USDT",
            exchange="BINANCE",
            venue="BINANCE-SPOT",
            provider_symbol="BTCUSDT",
        ))
        p = _provider(FakeTransport([]))
        p.registry = registry
        info = p.fetch_instrument_info("BTCUSDT")
        assert info.symbol == "BTC/USDT"
        assert info.provider_symbol == "BTCUSDT"
        assert registry.is_registered(info.symbol)

    def test_unregistered_symbol_yields_honest_decomposition(self):
        p = _provider(FakeTransport([]))
        info = p.fetch_instrument_info("BTCUSDT")
        assert info.symbol == "BTC/USDT"
        assert info.exchange == "BINANCE"
        assert info.venue == "BINANCE-SPOT"
        assert p.registry.is_registered(info.symbol) is False

    def test_undecomposable_symbol_refused(self):
        p = _provider(FakeTransport([]))
        p.config = p.config.model_copy(
            update={"instrument_allowlist": ["ZZZZZZZZZ"]}
        )
        with pytest.raises(BinancePublicError, match="decomposed"):
            p.fetch_instrument_info("ZZZZZZZZZ")


# ════════════════════════════════════════════════════════════════════
# 8. Connectivity probe (diagnostic only — never readiness evidence)
# ════════════════════════════════════════════════════════════════════

class TestConnectivity:
    def test_ping_success_returns_true(self, monkeypatch):
        p = _provider(FakeTransport([]))
        monkeypatch.setattr(
            p, "_ping", lambda: "{}"
        )
        assert p.check_connectivity() is True
        assert p.last_fetch_raw["last_connectivity"]["ok"] is True

    def test_ping_failure_returns_false_with_diagnostics(self, monkeypatch):
        p = _provider(FakeTransport([]))

        def _fail():
            raise BinanceTransportError("down")

        monkeypatch.setattr(p, "_ping", _fail)
        assert p.check_connectivity() is False
        assert p.last_fetch_raw["last_connectivity"]["ok"] is False
        assert "down" in p.last_fetch_raw["last_connectivity"]["error"]
