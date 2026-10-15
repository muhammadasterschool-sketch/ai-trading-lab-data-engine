"""Operational-feed composition: adapter → gate → readiness evidence.

This is the Phase-D integration the paper-readiness mandate requires
("Integrate the real adapter into the actual runtime composition
path. A standalone diagnostic script is not sufficient."):

1. ``fetch_feed_window`` retrieves CLOSED bars from a REAL provider
   through the existing provider framework (e.g. the Binance public
   klines adapter) for the strategy's warm-up window;
2. the bars are mapped to a canonical instrument (registry-confirmed
   — unconfirmed mapping fails closed);
3. :func:`~data_engine.runtime.feed_gate.evaluate_operational_feed`
   evaluates the FULL 32nd-gate checklist (approved source +
   production-ingestion scope + validated bars + correct interval +
   warm-up sufficiency + freshness + closed-bar discipline via the
   data gate);
4. :func:`operational_feed_evidence` converts the verdict into an
   honest :class:`~data_engine.runtime.readiness.GateEvidence` object
   for the authoritative :class:`PaperReadinessGate` — ``passed`` is
   the feed verdict, NEVER forced.

FAIL-CLOSED COMPOSITION: every failure mode (unapproved source,
stale data, unknown symbol, insufficient warm-up, open bars, gap
rejections, malformed data, provider outage/timeout/rate-limit,
rate-series abuse) surfaces as either a thrown typed error or a
FALSE verdict with explicit reasons — and a FALSE
``OPERATIONAL_FEED_READY`` evidence makes ``TradingRuntime.start()``
REFUSE (proven by tests in tests/test_feed_composition.py).

The evidence classes stay DISTINCT (mandate Phase C):
endpoint connectivity ≠ basic OHLCV validity ≠ operational feed
readiness ≠ research-dataset verification. Only the third is
evaluated here; connectivity helpers are explicitly labelled as
non-evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any, List, Optional, Sequence, Tuple

from datetime import timedelta
from typing import Any

from data_engine.prediction.source_registry import DataSourceRegistry
from data_engine.provider import MarketDataProvider
from data_engine.runtime.feed_gate import (
    OperationalFeedReport,
    evaluate_operational_feed,
)
from data_engine.runtime.readiness import GateEvidence

__all__ = [
    "OPERATIONAL_FEED_GATE_NAME",
    "FeedCompositionError",
    "fetch_feed_window",
    "resolve_canonical_instrument",
    "evaluate_paper_feed",
    "operational_feed_evidence",
    "build_paper_feed_evidence",
]

#: The readiness gate this composition feeds (the 32nd gate).
OPERATIONAL_FEED_GATE_NAME = "OPERATIONAL_FEED_READY"

class FeedCompositionError(RuntimeError):
    """Raised when the composition itself cannot proceed safely.

    Distinct from a FALSE feed verdict: this error means we could not
    even obtain/shape the inputs to evaluate the gate (provider
    outage, unmapped instrument, invalid configuration). The session
    must NOT start — fail closed at composition time.
    """


def fetch_feed_window(
    provider: MarketDataProvider,
    *,
    instrument: str,
    timeframe: Any,
    interval: timedelta,
    as_of: datetime,
    required_warmup_bars: int,
    extra_bars: int = 0,
) -> List:
    """Fetch the closed-bar warm-up window ending at ``as_of``.

    ``timeframe`` is passed through to the provider OPAQUELY (the
    runtime package stays decoupled from the frozen schema domain —
    see tests/test_bug008_boundary_closure.py); the grid math uses the
    EXPLICIT ``interval`` timedelta (no inference, no enum knowledge).

    The window is ``[as_of - (warmup+extra) * interval, as_of)``.
    The provider's closed-candle enforcement excludes the still-open
    candle; this function additionally verifies every returned bar's
    GRID CLOSE (open + interval) is at/before ``as_of`` — defence in
    depth against both future-dated and still-open bars.
    """
    if interval is None or interval.total_seconds() <= 0:
        raise FeedCompositionError(
            f"interval must be a positive timedelta (got {interval!r}) — "
            "refusing to infer bar spacing"
        )
    if required_warmup_bars < 1:
        raise FeedCompositionError(
            "required_warmup_bars must be >= 1 (fail closed on "
            "nonsensical warm-up)"
        )
    if not isinstance(provider, MarketDataProvider):
        raise FeedCompositionError(
            f"{type(provider).__name__} is not a MarketDataProvider — "
            "the candle composition only accepts genuine candle "
            "providers (rate-series readers are structurally separate "
            "and must NEVER be composed as an executable feed)"
        )
    if extra_bars < 0:
        raise FeedCompositionError("extra_bars must be >= 0")
    if as_of.tzinfo is None:
        raise FeedCompositionError(
            "as_of must be a timezone-aware datetime (logical session "
            "reference time — naive times are ambiguous)"
        )
    as_of = as_of.astimezone(UTC)
    window = (required_warmup_bars + extra_bars) * interval
    bars = provider.fetch_candles(
        instrument, timeframe, start=as_of - window, end=as_of
    )
    for i, bar in enumerate(bars):
        if bar.timestamp.tzinfo is None:
            raise FeedCompositionError(
                f"feed bar {i} has a naive timestamp — ambiguous time "
                "is refused at composition (fail closed)"
            )
        # Defence in depth: a bar is only consumable when its grid
        # close (open + interval) is at/before the session reference
        # time. This catches BOTH future-dated bars (open >= as_of)
        # AND still-open bars (open < as_of but open + interval >
        # as_of) — independent of the provider's own closed-candle
        # enforcement, which remains the first line of defence.
        bar_close = bar.timestamp + interval
        if bar_close > as_of:
            raise FeedCompositionError(
                f"feed bar {i} at {bar.timestamp.isoformat()} is open or "
                f"future-dated (grid close {bar_close.isoformat()} > "
                f"session reference {as_of.isoformat()}) — look-ahead "
                "leakage is refused at composition (no open/future "
                "bars by construction)"
            )
    return list(bars)


def resolve_canonical_instrument(
    provider: MarketDataProvider,
    *,
    instrument: str,
) -> Tuple[str, bool]:
    """Resolve a provider symbol to (canonical_id, registry_confirmed).

    Registry-confirmed means the provider's own resolution returned a
    canonical instrument that ALREADY exists in the instrument
    registry — the adapter never invents a canonical identity that
    the governed registry does not hold. Unconfirmed mapping returns
    ``(canonical_symbol, False)`` and the feed gate FAILS CLOSED on
    it (fail closed on ambiguity).
    """
    info = provider.fetch_instrument_info(instrument)
    if info is None:
        raise FeedCompositionError(
            f"provider {provider.config.provider_name!r} returned no "
            f"instrument info for {instrument!r} — cannot map to a "
            "canonical instrument (fail closed)"
        )
    canonical = info.symbol
    confirmed = provider.registry.is_registered(canonical)
    return canonical, confirmed


def evaluate_paper_feed(
    provider: MarketDataProvider,
    *,
    source_registry: DataSourceRegistry,
    source_name: str,
    instrument: str,
    timeframe: Any,
    interval: timedelta,
    as_of: datetime,
    required_warmup_bars: int,
    extra_bars: int = 0,
    max_staleness_seconds: int = 900,
    future_tolerance_seconds: int = 60,
) -> Tuple[OperationalFeedReport, List, str, bool]:
    """Full Phase-D composition: fetch → map → evaluate the 32nd gate.

    Returns ``(report, bars, canonical_instrument_id,
    registry_confirmed)``. The report is the authoritative
    :class:`OperationalFeedReport` — passed=False carries explicit
    reasons. This function NEVER fabricates a pass: a provider
    outage raises through (fail closed), and every gate component
    failure lands in ``report.reasons``.
    """
    bars = fetch_feed_window(
        provider,
        instrument=instrument,
        timeframe=timeframe,
        interval=interval,
        as_of=as_of,
        required_warmup_bars=required_warmup_bars,
        extra_bars=extra_bars,
    )
    canonical_id, confirmed = resolve_canonical_instrument(
        provider, instrument=instrument
    )
    report = evaluate_operational_feed(
        source_registry=source_registry,
        source_name=source_name,
        session_symbol=instrument,
        bars=[bar.model_dump() for bar in bars],
        required_warmup_bars=required_warmup_bars,
        as_of=as_of,
        canonical_instrument_id=canonical_id,
        registry_confirmed=confirmed,
        expected_interval=interval,
        max_staleness_seconds=max_staleness_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    return report, bars, canonical_id, confirmed


def operational_feed_evidence(
    report: OperationalFeedReport,
    *,
    provider_name: str,
    instrument: str,
    timeframe: Any,
    verified_where: str = "local",
) -> GateEvidence:
    """Convert a feed verdict into HONEST gate evidence.

    ``passed`` mirrors ``report.passed`` exactly — there is no path
    that forces TRUE. The evidence text records the full verdict
    shape (status, scopes, bar count, warm-up, staleness, reasons)
    so the readiness report carries first-class diagnostics.
    """
    summary = {
        "source": report.source_name,
        "source_status": report.source_status,
        "approved_scopes": list(report.approved_scopes),
        "symbol": report.symbol,
        "canonical_instrument_id": report.canonical_instrument_id,
        "bar_count": report.bar_count,
        "warmup_required": report.warmup_required,
        "quality_rejections": len(report.quality_rejections),
        "latest_bar_timestamp": (
            report.latest_bar_timestamp.isoformat()
            if report.latest_bar_timestamp is not None
            else None
        ),
        "as_of": (
            report.as_of.isoformat() if report.as_of is not None else None
        ),
        "reasons": list(report.reasons),
    }
    return GateEvidence(
        gate=OPERATIONAL_FEED_GATE_NAME,
        component=f"runtime.feed_composition:{provider_name}",
        check="evaluate_operational_feed",
        evidence=(
            f"provider={provider_name} instrument={instrument} "
            f"timeframe={getattr(timeframe, 'value', timeframe)} verdict="
            f"{'PASS' if report.passed else 'FAIL'} "
            f"verified={verified_where} summary={summary}"
        ),
        passed=report.passed,
    )


def build_paper_feed_evidence(
    provider: MarketDataProvider,
    *,
    source_registry: DataSourceRegistry,
    source_name: str,
    instrument: str,
    timeframe: Any,
    interval: timedelta,
    as_of: datetime,
    required_warmup_bars: int,
    extra_bars: int = 0,
    max_staleness_seconds: int = 900,
    future_tolerance_seconds: int = 60,
    verified_where: str = "local",
) -> Tuple[GateEvidence, OperationalFeedReport, List]:
    """One-call composition: fetch → evaluate → evidence.

    The returned :class:`GateEvidence` is ready for submission to the
    authoritative :class:`~data_engine.runtime.readiness.PaperReadinessGate`;
    a FALSE verdict (unapproved source, stale feed, insufficient
    warm-up, quality rejections, unconfirmed mapping) produces
    ``passed=False`` evidence and ``TradingRuntime.start()`` will
    REFUSE the session — the fail-closed chain is exercised
    end-to-end in tests/test_feed_composition.py.
    """
    report, bars, _canonical, _confirmed = evaluate_paper_feed(
        provider,
        source_registry=source_registry,
        source_name=source_name,
        instrument=instrument,
        timeframe=timeframe,
        interval=interval,
        as_of=as_of,
        required_warmup_bars=required_warmup_bars,
        extra_bars=extra_bars,
        max_staleness_seconds=max_staleness_seconds,
        future_tolerance_seconds=future_tolerance_seconds,
    )
    evidence = operational_feed_evidence(
        report,
        provider_name=provider.config.provider_name,
        instrument=instrument,
        timeframe=timeframe,
        verified_where=verified_where,
    )
    return evidence, report, bars
