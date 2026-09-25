"""Momentum indicator calculations for the Quant Engine.

Implements:
- RSI (Relative Strength Index)

RSI Convention:
- Default period: 14
- Formula: RSI = 100 - (100 / (1 + RS))
- RS = Average Gain / Average Loss over `period` observations
- Initial averages: Simple average of gains/losses over first `period` observations
- Subsequent: Wilder's Smoothing (exponential with α = 1/period)
  - avg_gain_t = (avg_gain_(t-1) * (period-1) + current_gain) / period
  - avg_loss_t = (avg_loss_(t-1) * (period-1) + current_loss) / period
- If avg_loss = 0: RSI = 100 (all gains, no losses)
- If avg_gain = 0 and avg_loss > 0: RSI = 0 (all losses, no gains)
- Insufficient observations: returns None
- Flat prices (no gains or losses): RSI = 50 (neutral)
- Zero-loss condition: RSI = 100

All calculations are deterministic.
"""

from typing import List, Optional
from datetime import datetime
import math


def rsi(
    closes: List[float],
    period: int = 14,
    timestamps: Optional[List[datetime]] = None,
) -> List[Optional[float]]:
    """Calculate Relative Strength Index (RSI).

    Wilder's RSI convention with simple initial averages
    and Wilder's smoothing for subsequent values.

    Args:
        closes: List of closing prices (must be positive).
        period: RSI period. Default 14.
        timestamps: Optional timestamps for traceability.

    Returns:
        List of RSI values. First `period` values are None
        (need `period` changes to calculate first RSI).
        RSI is always in [0, 100] when defined.
    """
    n = len(closes)
    if period <= 0:
        raise ValueError(f"Period must be positive, got {period}")
    if n < 2:
        return [None] * n

    # Calculate price changes
    changes: List[Optional[float]] = [None]  # First observation has no change
    for i in range(1, n):
        prev = closes[i - 1]
        curr = closes[i]
        if (math.isnan(prev) or math.isinf(prev) or
            math.isnan(curr) or math.isinf(curr) or
            prev <= 0):
            changes.append(None)
        else:
            changes.append(curr - prev)

    # Need `period` changes to calculate first RSI
    # So result[0..period] are None
    result: List[Optional[float]] = [None] * n

    # Find the first `period` valid changes
    valid_changes = [c for c in changes[1:] if c is not None]
    if len(valid_changes) < period:
        return result  # Not enough valid data

    # Calculate initial average gain and loss
    gains = [max(c, 0) for c in valid_changes[:period]]
    losses = [max(-c, 0) for c in valid_changes[:period]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    # First RSI value at index = period (0-indexed, so period-th element)
    # We need to find the right index in the original list
    # The first RSI is calculated after `period` changes, which is at index `period`
    # But we need to be careful about None values in changes

    # Build result using Wilder's smoothing
    # Track position in changes list
    change_idx = 0
    valid_count = 0
    current_avg_gain = 0.0
    current_avg_loss = 0.0
    initialized = False

    for i in range(1, n):
        ch = changes[i]
        if ch is None:
            result[i] = None
            continue

        change_idx += 1
        gain = max(ch, 0.0)
        loss = max(-ch, 0.0)

        if not initialized:
            valid_count += 1
            if valid_count == period:
                # Initialize
                current_avg_gain = sum(max(c, 0) for c in valid_changes[:period]) / period
                current_avg_loss = sum(max(-c, 0) for c in valid_changes[:period]) / period
                initialized = True
                # Calculate first RSI
                if current_avg_loss == 0:
                    result[i] = 100.0 if current_avg_gain > 0 else 50.0
                elif current_avg_gain == 0:
                    result[i] = 0.0
                else:
                    rs = current_avg_gain / current_avg_loss
                    result[i] = 100.0 - (100.0 / (1.0 + rs))
            else:
                result[i] = None  # Still initializing
        else:
            # Wilder's smoothing
            current_avg_gain = (current_avg_gain * (period - 1) + gain) / period
            current_avg_loss = (current_avg_loss * (period - 1) + loss) / period

            if current_avg_loss == 0:
                result[i] = 100.0 if current_avg_gain > 0 else 50.0
            elif current_avg_gain == 0 and current_avg_loss > 0:
                result[i] = 0.0
            else:
                rs = current_avg_gain / current_avg_loss
                result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def rsi_last(closes: List[float], period: int = 14) -> Optional[float]:
    """Calculate only the last RSI value efficiently.

    Returns the most recent RSI value, or None if insufficient data.
    """
    values = rsi(closes, period)
    if not values:
        return None
    for v in reversed(values):
        if v is not None:
            return v
    return None