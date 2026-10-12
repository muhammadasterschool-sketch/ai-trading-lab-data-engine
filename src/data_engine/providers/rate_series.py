"""Forex USD-base RATE-SERIES adapter — deliberately NOT a candle feed.

WHY THIS MODULE EXISTS (paper-readiness mandate, Phase B/Forex):

The operator's Forex master dataset is a USD-base DAILY RATE SERIES
(one exchange rate per currency-pair per day — see
``data/manifests/master/forex_rates_master_manifest.json``). A rate
series is NOT OHLC market data, and converting it into pseudo-candles
would FABRICATE high/low/volume values that no market ever quoted.
That fabrication is forbidden by rule ("Never fabricate candles,
volumes, prices") and by the master-import record ("Forex REAL_
UNVERIFIED (USD-base RATE SERIES — OHLC fabrication forbidden)").

This adapter therefore provides the honest alternative: a clearly
separate rate-series reader that is STRUCTURALLY INCOMPATIBLE with
the candle-feed machinery:

- it does NOT subclass :class:`data_engine.provider.MarketDataProvider`
  (so it can never be plugged anywhere a candle provider is
  expected — no ``fetch_candles`` exists to override or abuse);
- it exposes ``PROVIDES_CANDLES = False`` and a
  :func:`assert_not_a_candle_feed` guard for composition-time checks;
- it returns :class:`RateObservation` records (pair, date, rate) —
  a different schema with different semantics;
- it can serve RESEARCH rate analytics only. It must NEVER back a
  paper-session bar feed, an execution simulator, or anything that
  consumes OHLC.

Instrument semantics documented honestly (operator mandate,
Phase B/Forex): the source carries one mid-style USD-base rate per
pair per day; no bid/ask, no spread, no intraday session structure,
no weekend quoting, no 15-minute bars. Genuine 15-minute forex OHLC
requires a HUMAN-APPROVED genuine forex feed source that does not
exist in this repository yet — the forex market therefore remains
BLOCKED for paper execution (recorded in the source-candidates
module and the readiness report; nothing here un-blocks it).

Provenance is carried verbatim from the governed master-import
manifest: the file is USER_SUPPLIED_NOT_INDEPENDENTLY_SOURCE_VERIFIED
(status REAL_UNVERIFIED, provider/licence UNKNOWN) and this adapter
propagates that honesty — it never upgrades the epistemic state.
"""

from __future__ import annotations

import csv
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "RATE_SERIES_SOURCE_NAME",
    "PROVIDES_CANDLES",
    "RateSeriesError",
    "RateObservation",
    "ForexRateSeriesAdapter",
    "assert_not_a_candle_feed",
]

#: Registry/source name under which the rate series is declared
#: (UNVETTED — research-scope only; never production-ingestion).
RATE_SERIES_SOURCE_NAME = "forex-master-rate-series"

#: Structural marker: this adapter CANNOT produce candles.
PROVIDES_CANDLES = False


class RateSeriesError(RuntimeError):
    """Raised on rate-series contract violations (fail closed)."""


class RateObservation(BaseModel):
    """One dated USD-base exchange-rate observation (NOT a candle).

    Schema deliberately distinct from :class:`~data_engine.schemas.Candle`:
    no open/high/low/volume, no timeframe, no bid/ask. A positive,
    finite rate for a currency pair on a calendar date.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    currency_pair: str
    observation_date: date
    rate: float
    source: str = RATE_SERIES_SOURCE_NAME
    epistemic_state: str = "REAL_UNVERIFIED"

    @field_validator("currency_pair")
    @classmethod
    def _validate_pair(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RateSeriesError("currency_pair must be non-empty")
        return v.strip().upper()

    @field_validator("rate")
    @classmethod
    def _validate_rate(cls, v: float) -> float:
        if not isinstance(v, float):
            raise RateSeriesError("rate must be a float")
        if v != v or v in (float("inf"), float("-inf")) or v <= 0:
            raise RateSeriesError(
                f"rate {v!r} must be finite and positive"
            )
        return v


class _RateReader(Protocol):
    """Minimal file-reading seam for deterministic tests."""

    def read_text(self) -> str: ...


class ForexRateSeriesAdapter:
    """Reader for the operator's USD-base daily forex rate series.

    Parameters
    ----------
    csv_path:
        Path to ``Forex_Master.csv`` (columns: Currency_Pair, Date,
        Exchange_Rate — the exact shape audited by the master-import
        pipeline).
    reader:
        Injectable text reader (tests substitute an in-memory
        string). Production callers pass nothing and the adapter
        reads the file from disk.

    Fail-closed behaviour: malformed rows, non-positive or
    non-finite rates, unparseable dates, duplicate (pair, date)
    keys and header violations raise :class:`RateSeriesError` —
    nothing is dropped silently and nothing is repaired.
    """

    def __init__(
        self,
        csv_path: Optional[Path] = None,
        *,
        reader: Optional[_RateReader] = None,
    ) -> None:
        if reader is None and csv_path is None:
            raise RateSeriesError(
                "ForexRateSeriesAdapter requires either a csv_path or "
                "an injected reader (fail closed — no default data)"
            )
        self._csv_path = csv_path
        self._reader = reader
        self._cache: Optional[Dict[str, List[RateObservation]]] = None

    # -- structural markers ------------------------------------------------
    @property
    def provides_candles(self) -> bool:
        """Always False — a rate series is not an executable feed."""
        return PROVIDES_CANDLES

    @property
    def source_name(self) -> str:
        return RATE_SERIES_SOURCE_NAME

    @property
    def epistemic_state(self) -> str:
        """Honest inherited state from the governed master import."""
        return "REAL_UNVERIFIED"

    # -- rate access (NO candle access exists) ----------------------------
    def pairs(self) -> tuple:
        """Distinct currency pairs available in the series."""
        self._ensure_loaded()
        return tuple(sorted(self._cache.keys()))

    def fetch_rates(
        self,
        currency_pair: str,
        *,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[RateObservation]:
        """Rate observations for one pair, ascending by date.

        This is a RESEARCH data accessor. There is intentionally NO
        method that returns candles, bars, or anything time-framed —
        see the module docstring for why.
        """
        self._ensure_loaded()
        key = currency_pair.strip().upper()
        if key not in self._cache:
            raise RateSeriesError(
                f"currency pair {key!r} not present in the rate series "
                f"(available: {self.pairs()})"
            )
        observations = self._cache[key]
        if start is not None:
            observations = [
                o for o in observations if o.observation_date >= start
            ]
        if end is not None:
            observations = [
                o for o in observations if o.observation_date <= end
            ]
        return list(observations)

    def fetch_candles(self, *args: Any, **kwargs: Any) -> None:
        """NEVER callable — structural refusal.

        Overriding the provider-ABC method name with an unconditional
        refusal documents at the type level that this adapter cannot
        become a candle feed by duck-typing either.
        """
        raise RateSeriesError(
            "ForexRateSeriesAdapter is a USD-base DAILY RATE SERIES — "
            "it has no OHLC data and fabricating candles from rates is "
            "FORBIDDEN (paper-readiness mandate, non-negotiable rule 4). "
            "A paper forex session requires a HUMAN-APPROVED genuine "
            "15-minute OHLC feed source, which does not exist in this "
            "repository."
        )

    # -- loading / validation ----------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._cache is not None:
            return
        if self._reader is not None:
            text = self._reader.read_text()
        else:
            try:
                text = Path(self._csv_path).read_text(encoding="utf-8")
            except OSError as exc:
                raise RateSeriesError(
                    f"cannot read rate series at {self._csv_path}: {exc}"
                ) from exc
        self._cache = self._parse(text)

    def _parse(self, text: str) -> Dict[str, List[RateObservation]]:
        """Pure parse + validation (no I/O) — deterministic."""
        rows = csv.DictReader(text.splitlines())
        header = rows.fieldnames
        expected = ["Currency_Pair", "Date", "Exchange_Rate"]
        if header != expected:
            raise RateSeriesError(
                f"unexpected rate-series header {header!r} — expected "
                f"{expected!r} (the audited master-import shape)"
            )
        cache: Dict[str, List[RateObservation]] = {}
        seen: set = set()
        line_no = 1
        for row in rows:
            line_no += 1
            pair = (row.get("Currency_Pair") or "").strip().upper()
            date_text = (row.get("Date") or "").strip()
            rate_text = (row.get("Exchange_Rate") or "").strip()
            if not pair or not date_text or not rate_text:
                raise RateSeriesError(
                    f"row {line_no}: incomplete rate row {row!r}"
                )
            try:
                observation_date = date.fromisoformat(date_text)
            except ValueError as exc:
                raise RateSeriesError(
                    f"row {line_no}: unparseable date {date_text!r} ({exc})"
                ) from exc
            try:
                rate = float(rate_text)
            except ValueError as exc:
                raise RateSeriesError(
                    f"row {line_no}: unparseable rate {rate_text!r} ({exc})"
                ) from exc
            key = (pair, observation_date)
            if key in seen:
                raise RateSeriesError(
                    f"row {line_no}: duplicate (pair, date) {key} — "
                    "rate series must have one rate per pair per day"
                )
            seen.add(key)
            try:
                observation = RateObservation(
                    currency_pair=pair,
                    observation_date=observation_date,
                    rate=rate,
                )
            except ValueError as exc:
                raise RateSeriesError(
                    f"row {line_no}: invalid rate observation ({exc})"
                ) from exc
            cache.setdefault(pair, []).append(observation)

        if not cache:
            raise RateSeriesError(
                "rate series contains no observations (refusing to "
                "serve an empty feed silently)"
            )
        for pair in cache:
            cache[pair].sort(key=lambda o: o.observation_date)
        return cache


def assert_not_a_candle_feed(provider: Any) -> None:
    """Composition-time guard: the object must NOT be a candle feed.

    Used by the operational-feed composition (and its tests) to prove
    a rate-series adapter can never be mistaken for an executable
    candle feed: it must carry ``PROVIDES_CANDLES = False`` and must
    not be a ``MarketDataProvider`` subclass.
    """
    from data_engine.provider import MarketDataProvider

    if isinstance(provider, MarketDataProvider):
        raise RateSeriesError(
            f"{type(provider).__name__} is a MarketDataProvider — "
            "rate-series adapters must stay structurally separate from "
            "the candle provider hierarchy"
        )
    if getattr(provider, "provides_candles", None) is not False:
        raise RateSeriesError(
            f"{type(provider).__name__} does not declare "
            "PROVIDES_CANDLES = False — refusing ambiguous feed role"
        )
