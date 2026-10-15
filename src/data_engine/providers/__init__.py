"""Real market-data provider package (paper-readiness mandate Phase B).

Adapters here conform to the EXISTING framework —
:class:`data_engine.provider.MarketDataProvider`,
:class:`data_engine.provider.ProviderFactory`,
:class:`data_engine.schemas.Candle` — no second ingestion framework
exists or is created.

Members:

- :mod:`data_engine.providers.transport` — stdlib-only single-attempt
  HTTP GET with typed failures (network layer, injectable for tests).
- :mod:`data_engine.providers.binance_public` — crypto pilot:
  Binance public spot klines (BTCUSDT), closed-candle enforcement,
  bounded pagination/retries, raw-response provenance.
- :mod:`data_engine.providers.rate_series` — the forex USD-base rate
  series as a STRUCTURALLY SEPARATE research reader (never candles).

Source governance: none of these adapters is a source approval. They
enter the governed prediction source registry as UNVETTED candidates
(see :mod:`data_engine.platform.feed_source_candidates`) and stay
UNVETTED until the operator records the human SRC-APPROVAL decision.
"""

from datetime import timedelta

from data_engine.providers.binance_public import (
    BINANCE_PUBLIC_PROVIDER_NAME,
    INTERVAL_SECONDS,
    BinanceDataError,
    BinanceHTTPError,
    BinancePublicError,
    BinancePublicKlinesProvider,
    BinanceRateLimitedError,
    BinanceResponseError,
    BinanceTransportError,
)
from data_engine.providers.rate_series import (
    PROVIDES_CANDLES,
    ForexRateSeriesAdapter,
    RateObservation,
    RateSeriesError,
    assert_not_a_candle_feed,
)
from data_engine.providers.transport import (
    HttpGetTransport,
    TransportConnectError,
    TransportHTTPError,
    TransportProtocolError,
    TransportTimeoutError,
)

def interval_for_timeframe(timeframe) -> timedelta:
    """Explicit timeframe → timedelta mapping (companion to the
    runtime feed composition, which stays decoupled from the frozen
    schemas domain and receives a plain timedelta)."""
    from data_engine.schemas import Timeframe

    seconds = INTERVAL_SECONDS.get(timeframe)
    if seconds is None:
        raise ValueError(
            f"no explicit interval mapping for timeframe {timeframe!r}"
        )
    return timedelta(seconds=seconds)


__all__ = [
    "BINANCE_PUBLIC_PROVIDER_NAME",
    "INTERVAL_SECONDS",
    "interval_for_timeframe",
    "BinanceDataError",
    "BinanceHTTPError",
    "BinancePublicError",
    "BinancePublicKlinesProvider",
    "BinanceRateLimitedError",
    "BinanceResponseError",
    "BinanceTransportError",
    "PROVIDES_CANDLES",
    "ForexRateSeriesAdapter",
    "RateObservation",
    "RateSeriesError",
    "assert_not_a_candle_feed",
    "HttpGetTransport",
    "TransportConnectError",
    "TransportHTTPError",
    "TransportProtocolError",
    "TransportTimeoutError",
]
