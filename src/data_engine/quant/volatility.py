"""Volatility indicator calculations for the Quant Engine.

Implements:
- ATR (Average True Range)
- Rolling standard deviation
- Realized volatility
- ATR/Close ratio

ATR Convention:
- Default period: 14
- True Range: TR_t = max(H_t - L_t, |H_t - C_(t-1)|, |L_t - C_(t-1)|)
- ATR initialization: SMA of first `period` TR values
- Subsequent: Wilder's smoothing (α = 1/period)
  - ATR_t = (ATR_(t-1) * (period-1) + TR_t) / period
- Insufficient observations: returns None
- All values are non-negative (ATR >= 0)

Rolling Standard Deviation:
- Uses population standard deviation (ddof=0)
- Explicit window size
- Returns None for windows with insufficient data or NaN/Inf

Realized Volatility:
- Annualized standard deviation of log returns
- Annualization depends on timeframe-specific bars per year
"""

from typing import List, Optional
from datetime import datetime
from data_engine.timeframes import get_bars_per_year
import math


def true_range(
    highs: List[float],
    lows: List[float],
    closes: List[float],
) -> List[Optional[float]]:
    """Calculate True Range for each candle.

    TR_t = max(
        High_t - Low_t,
        |High_t - Close_(t-1)|,
        |Low_t - Close_(t-1)|
    )

    For the first observation, returns None (no previous close).

    Args:
        highs: List of high prices.
        lows: List of low prices.
        closes: List of close prices.

    Returns:
        List of True Range values (first is None).
    """
    n = len(highs)
    if n == 0:
        return []

    result: List[Optional[float]] = [None]  # First observation has no TR

    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        prev_c = closes[i - 1]

        if (math.isnan(h) or math.isinf(h) or
            math.isnan(l) or math.isinf(l) or
            math.isnan(prev_c) or math.isinf(prev_c)):
            result.append(None)
            continue

        tr = max(
            h - l,
            abs(h - prev_c),
            abs(l - prev_c)
        )
        result.append(tr)

    return result


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
    timestamps: Optional[List[datetime]] = None,
) -> List[Optional[float]]:
    """Calculate Average True Range (ATR).

    Uses Wilder's smoothing with SMA initialization.
    ATR >= 0 always.

    Args:
        highs: List of high prices.
        lows: List of low prices.
        closes: List of close prices.
        period: ATR period. Default 14.
        timestamps: Optional timestamps (for API consistency).

    Returns:
        List of ATR values. First `period` values are None
        (need `period` TR values for initialization).
    """
    n = len(highs)
    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")
    if n == 0:
        return []

    # Calculate True Range
    tr_values = true_range(highs, lows, closes)

    # Need at least `period` valid TR values (index 0 is always None)
    valid_tr = [v for v in tr_values if v is not None]
    if len(valid_tr) < period:
        return [None] * n

    result: List[Optional[float]] = [None] * n

    # Initialize with SMA of first `period` TR values
    atr_val = sum(valid_tr[:period]) / period

    # Find the index in the original array where the period-th TR value is
    # TR values start at index 1 (index 0 is None)
    # The period-th valid TR is at position period-1 in valid_tr
    # Map back to original array index
    tr_seen = 0
    for i in range(1, n):
        if tr_values[i] is None:
            result[i] = None
            continue

        tr_seen += 1
        if tr_seen < period:
            result[i] = None
        elif tr_seen == period:
            result[i] = atr_val
        else:
            # Wilder's smoothing
            atr_val = (atr_val * (period - 1) + tr_values[i]) / period
            result[i] = atr_val

    return result


def atr_last(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Optional[float]:
    """Calculate only the last ATR value."""
    values = atr(highs, lows, closes, period)
    if not values:
        return None
    for v in reversed(values):
        if v is not None:
            return v
    return None


def rolling_std(
    prices: List[float],
    window: int,
    ddof: int = 0,
) -> List[Optional[float]]:
    """Calculate rolling standard deviation.

    Uses population standard deviation by default (ddof=0).
    Set ddof=1 for sample standard deviation.

    Args:
        prices: List of price values.
        window: Rolling window size.
        ddof: Delta degrees of freedom. Default 0 (population).

    Returns:
        List of rolling std values. First `window-1` values are None.
    """
    n = len(prices)
    if window <= 0:
        raise ValueError(f"Window must be positive, got {window}")
    if n == 0:
        return []

    result: List[Optional[float]] = [None] * n

    for i in range(window - 1, n):
        window_vals = prices[i - window + 1 : i + 1]
        if len(window_vals) != window:
            continue
        if any(math.isnan(v) or math.isinf(v) for v in window_vals):
            result[i] = None
            continue

        mean = sum(window_vals) / window
        variance = sum((v - mean) ** 2 for v in window_vals) / (window - ddof)
        if variance < 0:
            variance = 0.0  # Numerical precision guard
        result[i] = math.sqrt(variance)

    return result


def realized_volatility(
    prices: List[float],
    timeframe,
    window: Optional[int] = None,
) -> Optional[float]:
    """Calculate annualized realized volatility from log returns.

    Formula:
    1. Calculate log returns: r_t = ln(P_t / P_(t-1))
    2. Compute standard deviation of returns
    3. Annualize: σ_annual = σ * sqrt(bars_per_year)

    Args:
        prices: List of price values.
        timeframe: Timeframe enum (for bars_per_year).
        window: Optional rolling window. If None, uses all data.

    Returns:
        Annualized realized volatility, or None if insufficient data.
    """
    from data_engine.timeframes import get_bars_per_year

    n = len(prices)
    if n < 2:
        return None

    # Calculate log returns
    log_rets = []
    for i in range(1, n):
        prev = prices[i - 1]
        curr = prices[i]
        if prev <= 0 or curr <= 0 or math.isnan(prev) or math.isinf(prev) or math.isnan(curr) or math.isinf(curr):
            continue
        log_rets.append(math.log(curr / prev))

    if len(log_rets) < 2:
        return None

    if window is not None and len(log_rets) >= window:
        log_rets = log_rets[-window:]

    mean = sum(log_rets) / len(log_rets)
    variance = sum((r - mean) ** 2 for r in log_rets) / (len(log_rets) - 1)

    if variance < 0:
        variance = 0.0

    daily_vol = math.sqrt(variance)
    bars_per_year = get_bars_per_year(timeframe)
    annualized_vol = daily_vol * math.sqrt(bars_per_year)

    return annualized_vol


def atr_ratio(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    """Calculate ATR/Close ratio.

    Measures normalized volatility (ATR as percentage of price).

    Returns:
        List of ATR/Close ratios. First values may be None.
    """
    atr_values = atr(highs, lows, closes, period)
    result: List[Optional[float]] = []

    for i in range(len(closes)):
        if atr_values[i] is None or closes[i] is None:
            result.append(None)
            continue
        if math.isnan(closes[i]) or math.isinf(closes[i]) or closes[i] <= 0:
            result.append(None)
            continue
        result.append(atr_values[i] / closes[i])

    return result