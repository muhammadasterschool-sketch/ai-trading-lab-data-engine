"""Moving average calculations for the Quant Engine.

Implements:
- SMA (Simple Moving Average): arithmetic mean over n observations
- EMA (Exponential Moving Average): weighted mean with exponential decay

EMA convention:
- Initialization: first EMA value = SMA of first `period` observations
- Alpha: α = 2 / (period + 1)
- Recurrence: EMA_t = α * P_t + (1 - α) * EMA_(t-1)
- Insufficient observations: returns None until `period` observations available
- NaN policy: if any input is NaN/Inf, output is None

All calculations are deterministic and reproducible.
"""

from typing import List, Optional
from datetime import datetime
import math


def sma(
    prices: List[float],
    period: int,
    timestamps: Optional[List[datetime]] = None,
) -> List[Optional[float]]:
    """Calculate Simple Moving Average.

    SMA_n = mean(P_(t-n+1), ..., P_t)

    For the first (period-1) observations, returns None.
    If any value in the window is NaN/Inf, returns None for that window.

    Args:
        prices: List of price values.
        period: Number of observations for the moving average.
        timestamps: Optional timestamps for traceability.

    Returns:
        List of SMA values (None for insufficient observations).
    """
    n = len(prices)
    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")
    if n == 0:
        return []

    result: List[Optional[float]] = [None] * n

    for i in range(period - 1, n):
        window = prices[i - period + 1 : i + 1]
        if len(window) != period:
            continue
        # Check for NaN/Inf in window
        if any(math.isnan(v) or math.isinf(v) for v in window):
            result[i] = None
            continue
        result[i] = sum(window) / period

    return result


def ema(
    prices: List[float],
    period: int,
    timestamps: Optional[List[datetime]] = None,
) -> List[Optional[float]]:
    """Calculate Exponential Moving Average.

    Convention:
    - α = 2 / (period + 1)
    - First EMA = SMA of first `period` observations
    - EMA_t = α * P_t + (1 - α) * EMA_(t-1)
    - For t < period: returns None (insufficient observations)
    - If any price is NaN/Inf: returns None for that point

    Args:
        prices: List of price values.
        period: EMA period (number of observations).
        timestamps: Optional timestamps (not used, kept for API consistency).

    Returns:
        List of EMA values. First `period-1` values are None.
    """
    n = len(prices)
    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")
    if n == 0:
        return []

    result: List[Optional[float]] = [None] * n
    alpha = 2.0 / (period + 1.0)

    if n < period:
        return result

    # Initialize with SMA of first `period` observations
    window = prices[:period]
    if any(math.isnan(v) or math.isinf(v) for v in window):
        # Find first valid starting point
        for i in range(period - 1, n):
            if math.isnan(prices[i]) or math.isinf(prices[i]):
                result[i] = None
                continue
            prev_valid = None
            for j in range(i - 1, period - 2, -1):
                if result[j] is not None:
                    prev_valid = result[j]
                    break
            if prev_valid is not None:
                result[i] = alpha * prices[i] + (1 - alpha) * prev_valid
            else:
                result[i] = prices[i] if not math.isnan(prices[i]) else None
        return result

    ema_val = sum(window) / period
    result[period - 1] = ema_val

    for i in range(period, n):
        if math.isnan(prices[i]) or math.isinf(prices[i]):
            result[i] = None
            continue
        prev_ema = result[i - 1]
        if prev_ema is not None:
            result[i] = alpha * prices[i] + (1 - alpha) * prev_ema
        else:
            result[i] = None

    return result


def ema_incremental(
    prices: List[float],
    period: int,
    prev_ema: Optional[float] = None,
) -> Optional[float]:
    """Calculate a single EMA value incrementally.

    Used when processing streaming data where previous EMA is known.

    Args:
        prices: Current price (single value).
        period: EMA period.
        prev_ema: Previous EMA value. If None, initializes with price.

    Returns:
        Single EMA value, or None if price is NaN/Inf.
    """
    if math.isnan(prices) or math.isinf(prices):
        return None

    alpha = 2.0 / (period + 1.0)

    if prev_ema is None:
        return prices  # Initialize with first price

    return alpha * prices + (1 - alpha) * prev_ema


def sma_with_timestamps(
    prices: List[float],
    timestamps: List[datetime],
    period: int,
) -> List[Optional[float]]:
    """Calculate SMA with timestamp preservation."""
    result = sma(prices, period, timestamps)
    return result


def ema_with_timestamps(
    prices: List[float],
    timestamps: List[datetime],
    period: int,
) -> List[Optional[float]]:
    """Calculate EMA with timestamp preservation."""
    result = ema(prices, period, timestamps)
    return result