"""PIT data access for prediction intelligence (§2, §11, §13, §39, §40).

Peer of ``data_engine.pit.view`` (Phase 4 sidecar views) and
``data_engine.quant.features`` (feat6. pipeline): this module applies the
SAME slice-then-compute discipline to duck-typed market bars for the
prediction layer:

- ``pit_candle_view``: bars with ``timestamp <= as_of`` are visible;
  later-arriving duplicate timestamps are treated as REVISIONS and
  dropped (first arrival wins) — revised values are never allowed to
  rewrite the past a prediction saw (§2, §34).
- ``universe_at``: point-in-time universe membership — symbols not yet
  listed at the cutoff are excluded, newly listed symbols with too
  little history are declared INSUFFICIENT_HISTORY, never silently
  substituted (§39).
- ``evaluate_history_policy``: the 5-year minimum / 10+ year preferred
  data policy as an explicit reading (§39).

Candles are duck-typed mappings with timezone-aware ``timestamp`` and
numeric ``close`` fields (same convention as ``quant/features.py``).
"""

from datetime import UTC, datetime
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import PredictionContractError


class PredictionDataError(PredictionContractError):
    """Raised when candle data violates the PIT data contract."""


def _candle_time(candle: Mapping[str, Any]) -> datetime:
    ts = candle.get("timestamp") if isinstance(candle, Mapping) else getattr(
        candle, "timestamp", None
    )
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise PredictionDataError(
            "candles need timezone-aware 'timestamp' fields"
        )
    return ts.astimezone(UTC)


def _candle_close(candle: Mapping[str, Any]) -> float:
    close = candle.get("close") if isinstance(candle, Mapping) else getattr(
        candle, "close", None
    )
    if close is None:
        raise PredictionDataError("every candle must carry a close price")
    if isinstance(close, bool):
        # bool is an int subclass — True would silently become 1.0
        raise PredictionDataError(
            "close price must be numeric, not bool (RT-PRED-I-001)"
        )
    try:
        value = float(close)
    except (TypeError, ValueError) as exc:
        raise PredictionDataError(
            f"close price must be numeric, got {close!r}"
        ) from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise PredictionDataError(
            "close price must be finite (NaN/inf rejected — RT-PRED-I-007/I-008)"
        )
    return value


class PitCandleView(BaseModel):
    """Result of applying the PIT cutoff to a candle series.

    ``bars`` is the visible, revision-deduplicated, time-ordered prefix.
    Counters make every invisible/dropped bar inspectable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bars: Tuple[dict, ...]
    as_of: datetime
    dropped_future_bars: int
    dropped_revision_bars: int

    @property
    def visible_count(self) -> int:
        return len(self.bars)

    @property
    def cutoff_timestamp(self) -> str:
        return self.as_of.isoformat()


def pit_candle_view(
    candles: Sequence[Any],
    as_of: datetime,
    *,
    revision_policy: str = "first-arrival-wins",
) -> PitCandleView:
    """PIT-visible candle prefix at ``as_of`` (slice FIRST, compute later).

    Rules:
    - bars with ``timestamp > as_of`` are INVISIBLE (dropped_future_bars)
    - a duplicate timestamp is a REVISION: the first arrival wins and
      the later arrival is dropped (dropped_revision_bars). Revised
      history cannot leak into a past prediction (§34: no revised data
      leakage).
    - output is stably sorted by timestamp
    """
    if as_of is None or as_of.tzinfo is None:
        raise PredictionDataError("as_of must be a timezone-aware datetime")
    if revision_policy != "first-arrival-wins":
        raise PredictionDataError(
            f"unknown revision policy {revision_policy!r}"
        )
    cutoff = as_of.astimezone(UTC)

    seen: dict[datetime, dict] = {}
    order: list[datetime] = []
    dropped_future = 0
    dropped_revisions = 0
    for candle in candles:
        ts = _candle_time(candle)
        if ts > cutoff:
            dropped_future += 1
            continue
        if ts in seen:
            dropped_revisions += 1
            continue  # first arrival wins — revision defense
        bar = {
            "timestamp": ts,
            "close": _candle_close(candle),
        }
        seen[ts] = bar
        order.append(ts)

    bars = tuple(seen[ts] for ts in sorted(order))
    return PitCandleView(
        bars=bars,
        as_of=cutoff,
        dropped_future_bars=dropped_future,
        dropped_revision_bars=dropped_revisions,
    )


class UniverseView(BaseModel):
    """Point-in-time universe membership at ``as_of`` (§39).

    Excluded symbols are named with explicit reasons — membership is
    never silently adjusted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    included: Tuple[str, ...]
    excluded_not_listed: Tuple[str, ...]
    excluded_insufficient_history: Tuple[str, ...]
    visible_bar_counts: Tuple[Tuple[str, int], ...]


def universe_at(
    candles_by_symbol: Mapping[str, Sequence[Any]],
    as_of: datetime,
    *,
    min_history_bars: int,
) -> UniverseView:
    """Universe membership as known at ``as_of`` (no survivorship leakage).

    A symbol is INCLUDED only when it was already listed at the cutoff
    AND has at least ``min_history_bars`` visible bars. Symbols listed
    after the cutoff are excluded as not-yet-listed; short-history
    symbols are excluded as INSUFFICIENT_HISTORY (§39).
    """
    if min_history_bars < 1:
        raise PredictionDataError("min_history_bars must be >= 1")
    included: list[str] = []
    not_listed: list[str] = []
    insufficient: list[str] = []
    counts: list[tuple[str, int]] = []
    for symbol in sorted(candles_by_symbol):
        view = pit_candle_view(candles_by_symbol[symbol], as_of)
        if not view.bars:
            not_listed.append(symbol)
            counts.append((symbol, 0))
            continue
        counts.append((symbol, view.visible_count))
        if view.visible_count < min_history_bars:
            insufficient.append(symbol)
        else:
            included.append(symbol)
    return UniverseView(
        as_of=as_of.astimezone(UTC),
        included=tuple(included),
        excluded_not_listed=tuple(not_listed),
        excluded_insufficient_history=tuple(insufficient),
        visible_bar_counts=tuple(counts),
    )


class HistoryPolicyReading(BaseModel):
    """Explicit reading of the historical-data policy (§39).

    MINIMUM: 5 years where available. PREFERRED: 10-15+ years where
    available. Readings never fabricate coverage — years_covered is
    computed from visible bars only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    visible_bars: int
    bars_per_year: int
    minimum_years: float
    preferred_years: float
    meets_minimum: bool
    meets_preferred: bool

    @property
    def years_covered(self) -> float:
        return round(self.visible_bars / self.bars_per_year, 6)

    @property
    def status(self) -> str:
        if self.meets_minimum:
            return "OK"
        return "INSUFFICIENT_HISTORY"


#: Mandate §39 data policy constants.
MINIMUM_HISTORY_YEARS = 5.0
PREFERRED_HISTORY_YEARS = 10.0
DEFAULT_BARS_PER_YEAR = 252


def evaluate_history_policy(
    *,
    visible_bars: int,
    bars_per_year: int = DEFAULT_BARS_PER_YEAR,
    minimum_years: float = MINIMUM_HISTORY_YEARS,
    preferred_years: float = PREFERRED_HISTORY_YEARS,
) -> HistoryPolicyReading:
    """Evaluate the 5-year minimum / 10-year preferred policy (§39)."""
    if bars_per_year < 1:
        raise PredictionDataError("bars_per_year must be >= 1")
    years = visible_bars / bars_per_year
    return HistoryPolicyReading(
        visible_bars=visible_bars,
        bars_per_year=bars_per_year,
        minimum_years=minimum_years,
        preferred_years=preferred_years,
        meets_minimum=years >= minimum_years,
        meets_preferred=years >= preferred_years,
    )


__all__ = [
    "PredictionDataError",
    "PitCandleView",
    "pit_candle_view",
    "UniverseView",
    "universe_at",
    "HistoryPolicyReading",
    "evaluate_history_policy",
    "MINIMUM_HISTORY_YEARS",
    "PREFERRED_HISTORY_YEARS",
    "DEFAULT_BARS_PER_YEAR",
]
