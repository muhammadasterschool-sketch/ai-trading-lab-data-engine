"""Volume-based indicator family (v1.5.0 top-50 pack).

OBV, MFI, Force Index, Ease of Movement, Chaikin Money Flow,
Accumulation/Distribution line, Chaikin Oscillator and rolling volume
z-score. Conventions identical to the rest of ``data_engine.quant``:
pure functions, ``List[Optional[float]]`` outputs, ``None`` for
insufficient data, fully deterministic.
"""

from __future__ import annotations

from typing import List, Optional, Sequence


def _ema_kernel(values: Sequence[float], period: int) -> List[Optional[float]]:
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period < 1 or n < period:
        return out
    alpha = 2.0 / (period + 1.0)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = alpha * values[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _sma_kernel(values: Sequence[float], period: int) -> List[Optional[float]]:
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period < 1 or n < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


# ---------------------------------------------------------------------------
# On-Balance Volume
# ---------------------------------------------------------------------------

def on_balance_volume(
    closes: List[float], volumes: List[float]
) -> List[Optional[float]]:
    """OBV (Granville): cumulative volume signed by close direction.

    First bar = its own volume; OBV rises when close rises, falls when
    close falls, unchanged on flat closes.
    """
    n = len(closes)
    if len(volumes) != n:
        raise ValueError("closes/volumes must be aligned")
    if n == 0:
        return []
    out: List[Optional[float]] = [None] * n
    obv = float(volumes[0])
    out[0] = obv
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
        out[i] = obv
    return out


# ---------------------------------------------------------------------------
# Money Flow Index
# ---------------------------------------------------------------------------

def money_flow_index(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    """MFI (Quong/Soudack): volume-weighted RSI over typical price.

    Range [0, 100]; windows with zero negative (or zero positive) flow
    produce 100.0 (0.0) respectively — the standard convention.
    """
    n = len(closes)
    if not (len(highs) == len(lows) == len(volumes) == n):
        raise ValueError("inputs must be aligned")
    if period < 2:
        raise ValueError("mfi period must be >= 2")
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        pos = 0.0
        neg = 0.0
        for j in range(i - period + 1, i + 1):
            flow = tp[j] * volumes[j]
            if tp[j] > tp[j - 1]:
                pos += flow
            elif tp[j] < tp[j - 1]:
                neg += flow
        if neg == 0:
            out[i] = 100.0 if pos > 0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + pos / neg)
    return out


# ---------------------------------------------------------------------------
# Force Index
# ---------------------------------------------------------------------------

def force_index(
    closes: List[float],
    volumes: List[float],
    period: int = 13,
) -> List[Optional[float]]:
    """Force Index (Elder): EMA(period) of (close delta * volume)."""
    n = len(closes)
    if len(volumes) != n:
        raise ValueError("closes/volumes must be aligned")
    if period < 1:
        raise ValueError("force_index period must be >= 1")
    raw: List[float] = [0.0] * n
    for i in range(1, n):
        raw[i] = (closes[i] - closes[i - 1]) * volumes[i]
    ema = _ema_kernel(raw, period)
    out: List[Optional[float]] = [None] * n
    for i in range(1, n):
        out[i] = ema[i] if i > 0 else None
    out[0] = None
    return out


# ---------------------------------------------------------------------------
# Ease of Movement
# ---------------------------------------------------------------------------

def ease_of_movement(
    highs: List[float],
    lows: List[float],
    volumes: List[float],
    period: int = 14,
    divisor: float = 100_000.0,
) -> List[Optional[float]]:
    """EOM ( Arms-style ): SMA of box ratio inverted by volume.

    DM = (H+L)/2 - (H_prev+L_prev)/2; BR = V / divisor / (H - L);
    EOM = DM / BR; smoothed by SMA(period). Flat bars (H == L) yield
    None for that bar and are skipped from the average.
    """
    n = len(highs)
    if len(lows) != n or len(volumes) != n:
        raise ValueError("inputs must be aligned")
    if period < 1 or divisor <= 0:
        raise ValueError("eom requires period >= 1 and divisor > 0")
    raw: List[Optional[float]] = [None] * n
    for i in range(1, n):
        range_ = highs[i] - lows[i]
        if range_ > 0:
            dm = (highs[i] + lows[i]) / 2.0 - (highs[i - 1] + lows[i - 1]) / 2.0
            br = volumes[i] / divisor / range_
            raw[i] = dm / br if br != 0 else None
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        window = [raw[j] for j in range(i - period + 1, i + 1)
                  if raw[j] is not None]
        if len(window) == period:
            out[i] = sum(window) / period
    return out


# ---------------------------------------------------------------------------
# Chaikin Money Flow
# ---------------------------------------------------------------------------

def chaikin_money_flow(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    period: int = 20,
) -> List[Optional[float]]:
    """CMF (Chaikin): sum(MFV, period) / sum(V, period).

    MFV = ((C-L)-(H-C))/(H-L) * V; flat bars contribute zero MFV.
    """
    n = len(closes)
    if not (len(highs) == len(lows) == len(volumes) == n):
        raise ValueError("inputs must be aligned")
    if period < 1:
        raise ValueError("cmf period must be >= 1")
    mfv: List[float] = [0.0] * n
    for i in range(n):
        range_ = highs[i] - lows[i]
        if range_ > 0:
            multiplier = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / range_
            mfv[i] = multiplier * volumes[i]
    out: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        vol = sum(volumes[i - period + 1: i + 1])
        if vol > 0:
            out[i] = sum(mfv[i - period + 1: i + 1]) / vol
    return out


# ---------------------------------------------------------------------------
# Accumulation/Distribution line + Chaikin Oscillator
# ---------------------------------------------------------------------------

def accumulation_distribution(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
) -> List[Optional[float]]:
    """A/D line (Chaikin): cumulative sum of money-flow volume."""
    n = len(closes)
    if not (len(highs) == len(lows) == len(volumes) == n):
        raise ValueError("inputs must be aligned")
    out: List[Optional[float]] = [None] * n
    ad = 0.0
    for i in range(n):
        range_ = highs[i] - lows[i]
        if range_ > 0:
            ad += (
                ((closes[i] - lows[i]) - (highs[i] - closes[i])) / range_
                * volumes[i]
            )
        out[i] = ad
    return out


def chaikin_oscillator(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    fast: int = 3,
    slow: int = 10,
) -> List[Optional[float]]:
    """Chaikin Oscillator: EMA(AD, fast) - EMA(AD, slow)."""
    ad = accumulation_distribution(highs, lows, closes, volumes)
    filled = [v for v in ad if v is not None]
    if not filled or fast < 1 or slow < 2 or fast >= slow:
        return [None] * len(closes)
    ema_fast_full = _ema_kernel(filled, fast)
    ema_slow_full = _ema_kernel(filled, slow)
    start = next((i for i, v in enumerate(ad) if v is not None), len(ad))
    out: List[Optional[float]] = [None] * len(closes)
    for i in range(len(filled)):
        f = ema_fast_full[i]
        s = ema_slow_full[i]
        if f is not None and s is not None:
            out[start + i] = f - s
    return out


# ---------------------------------------------------------------------------
# Rolling volume z-score
# ---------------------------------------------------------------------------

def volume_zscore(
    volumes: List[float], period: int = 20
) -> List[Optional[float]]:
    """Rolling z-score of volume (surge detector, ddof=0)."""
    if period < 2:
        raise ValueError("volume_zscore period must be >= 2")
    n = len(volumes)
    out: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        window = volumes[i - period + 1: i + 1]
        mean = sum(window) / period
        var = sum((v - mean) ** 2 for v in window) / period
        if var > 0:
            out[i] = (volumes[i] - mean) / var ** 0.5
    return out


__all__ = [
    "on_balance_volume",
    "money_flow_index",
    "force_index",
    "ease_of_movement",
    "chaikin_money_flow",
    "accumulation_distribution",
    "chaikin_oscillator",
    "volume_zscore",
]
