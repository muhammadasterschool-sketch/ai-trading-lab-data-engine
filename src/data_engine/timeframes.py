"""Timeframe handling module for the AI Trading Lab Data Engine.

Timeframes are never silently converted. Every dataset retains its
original timeframe, and any resampling must be an explicit, versioned
transformation.
"""

from data_engine.schemas import Timeframe
from datetime import timedelta
from typing import Optional


# Expected number of bars per calendar year per timeframe
_BARS_PER_YEAR = {
    Timeframe.M1: 525600,     # 365 * 24 * 60
    Timeframe.M5: 105120,     # 365 * 24 * 12
    Timeframe.M15: 35040,     # 365 * 24 * 4
    Timeframe.H1: 8760,       # 365 * 24
    Timeframe.H4: 2190,       # 365 * 6
    Timeframe.D1: 365,        # 365
}

# Expected number of bars per trading day (forex-style, 24h)
_BARS_PER_DAY = {
    Timeframe.M1: 1440,
    Timeframe.M5: 288,
    Timeframe.M15: 96,
    Timeframe.H1: 24,
    Timeframe.H4: 6,
    Timeframe.D1: 1,
}


def get_bars_per_year(timeframe: Timeframe) -> int:
    """Return expected bars per calendar year for the given timeframe."""
    return _BARS_PER_YEAR[timeframe]


def get_bars_per_day(timeframe: Timeframe) -> int:
    """Return expected bars per trading day for the given timeframe."""
    return _BARS_PER_DAY[timeframe]


def get_expected_bars(
    timeframe: Timeframe,
    start: "datetime",
    end: "datetime",
    bars_per_day: Optional[dict] = None,
) -> int:
    """Estimate expected number of bars between two timestamps."""
    if bars_per_day is None:
        bars_per_day = _BARS_PER_DAY
    days = (end - start).days
    if days < 1:
        return 0
    return days * bars_per_day[timeframe]


def validate_timeframe_integrity(candles: list, timeframe: Timeframe) -> list:
    """Validate that all candles in a dataset belong to the declared timeframe.

    Returns a list of validation messages for any candles that don't match.
    """
    from data_engine.schemas import Candle
    issues = []
    for i, candle in enumerate(candles):
        if isinstance(candle, Candle) and candle.timeframe != timeframe:
            issues.append(
                f"Candle {i}: timeframe {candle.timeframe.value} != declared {timeframe.value}"
            )
    return issues


def get_effective_lookback_days(
    period_count: int,
    timeframe: Timeframe,
) -> float:
    """Calculate approximate calendar-day lookback for a given period count.

    This is critical for understanding indicator semantics across timeframes.
    EMA200 on H4 ≠ EMA200 on Daily.

    Example:
        EMA200 on H4 → 200 bars × ~4 hours = 800 hours ≈ 33.3 days
        EMA200 on D1 → 200 bars × ~24 hours = 4800 hours ≈ 200 days
    """
    hours_per_bar = {
        Timeframe.M1: 1/60,
        Timeframe.M5: 5/60,
        Timeframe.M15: 15/60,
        Timeframe.H1: 1,
        Timeframe.H4: 4,
        Timeframe.D1: 24,
    }
    total_hours = period_count * hours_per_bar[timeframe]
    return total_hours / 24.0


def assert_timeframe_not_converted(
    original_timeframe: Timeframe,
    claimed_timeframe: Timeframe,
    operation: str = "data handling",
):
    """Assert that a timeframe has not been silently converted.

    Raises ValueError if timeframes differ.
    """
    if original_timeframe != claimed_timeframe:
        raise ValueError(
            f"Timeframe conversion detected during {operation}: "
            f"original={original_timeframe.value}, claimed={claimed_timeframe.value}. "
            f"Timeframe conversion must be explicit and versioned."
        )


# Indicator effective lookback reference table
INDICATOR_LOOKBACK = {
    "EMA200": {
        Timeframe.D1: "≈200 trading days (~10 months)",
        Timeframe.H4: "≈33 calendar days",
        Timeframe.H1: "≈8.3 calendar days",
        Timeframe.M15: "≈5.2 calendar days",
        Timeframe.M5: "≈2.0 calendar days",
        Timeframe.M1: "≈10 hours",
    },
    "SMA200": {
        Timeframe.D1: "≈200 trading days (~10 months)",
        Timeframe.H4: "≈33 calendar days",
    },
    "RSI14": {
        Timeframe.D1: "≈14 trading days",
        Timeframe.H4: "≈56 hours (~2.3 days)",
    },
    "ATR14": {
        Timeframe.D1: "≈14 trading days",
        Timeframe.H4: "≈56 hours (~2.3 days)",
    },
}
