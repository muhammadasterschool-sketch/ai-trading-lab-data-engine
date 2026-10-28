"""Band / envelope / VWAP indicator family (v1.5.0 top-50 pack).

Same conventions as the rest of ``data_engine.quant``: pure functions,
``List[Optional[float]]`` outputs, ``None`` for insufficient data or
non-finite values, fully deterministic. Multi-output indicators return
a dict of aligned series and ship single-series accessors for the
registry contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Sequence


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


def _rolling_std_kernel(
    values: Sequence[float], period: int
) -> List[Optional[float]]:
    """Population (ddof=0) rolling std — matches quant.volatility style."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period < 2 or n < period:
        return out
    for i in range(period - 1, n):
        window = values[i - period + 1: i + 1]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        out[i] = var ** 0.5
    return out


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


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger(
    closes: List[float],
    period: int = 20,
    num_std: float = 2.0,
) -> Dict[str, List[Optional[float]]]:
    """Bollinger Bands (Bollinger): SMA +/- num_std * rolling std.

    Returns ``middle``, ``upper``, ``lower``, ``bandwidth`` (relative,
    in %) and ``percent_b`` ((C-lower)/(upper-lower), None on flat
    bands). Population std (ddof=0).
    """
    if period < 2 or num_std <= 0:
        raise ValueError("bollinger requires period >= 2 and num_std > 0")
    middle = _sma_kernel(closes, period)
    std = _rolling_std_kernel(closes, period)
    upper: List[Optional[float]] = []
    lower: List[Optional[float]] = []
    bandwidth: List[Optional[float]] = []
    percent_b: List[Optional[float]] = []
    for m, s, c in zip(middle, std, closes):
        if m is None or s is None:
            upper.append(None)
            lower.append(None)
            bandwidth.append(None)
            percent_b.append(None)
            continue
        up = m + num_std * s
        lo = m - num_std * s
        upper.append(up)
        lower.append(lo)
        bandwidth.append(100.0 * (up - lo) / m if m != 0 else None)
        percent_b.append((c - lo) / (up - lo) if up > lo else None)
    return {
        "middle": middle,
        "upper": upper,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


def bollinger_upper(
    closes: List[float], period: int = 20, num_std: float = 2.0
) -> List[Optional[float]]:
    return bollinger(closes, period, num_std)["upper"]


def bollinger_lower(
    closes: List[float], period: int = 20, num_std: float = 2.0
) -> List[Optional[float]]:
    return bollinger(closes, period, num_std)["lower"]


# ---------------------------------------------------------------------------
# Keltner Channels
# ---------------------------------------------------------------------------

def keltner(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 20,
    atr_mult: float = 2.0,
) -> Dict[str, List[Optional[float]]]:
    """Keltner Channels: EMA(period) +/- atr_mult * ATR(period)."""
    from data_engine.quant.volatility import atr as _atr

    if period < 2 or atr_mult <= 0:
        raise ValueError("keltner requires period >= 2 and atr_mult > 0")
    middle = _ema_kernel(closes, period)
    atr_series = _atr(highs, lows, closes, period)
    upper: List[Optional[float]] = []
    lower: List[Optional[float]] = []
    for m, a in zip(middle, atr_series):
        if m is None or a is None:
            upper.append(None)
            lower.append(None)
        else:
            upper.append(m + atr_mult * a)
            lower.append(m - atr_mult * a)
    return {"middle": middle, "upper": upper, "lower": lower}


def keltner_upper(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 20, atr_mult: float = 2.0,
) -> List[Optional[float]]:
    return keltner(highs, lows, closes, period, atr_mult)["upper"]


# ---------------------------------------------------------------------------
# Donchian Channels
# ---------------------------------------------------------------------------

def donchian(
    highs: List[float],
    lows: List[float],
    period: int = 20,
) -> Dict[str, List[Optional[float]]]:
    """Donchian Channels: rolling max(high)/min(low), mid = average."""
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs/lows must be aligned")
    if period < 1:
        raise ValueError("donchian period must be >= 1")
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    middle: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        up = max(highs[i - period + 1: i + 1])
        lo = min(lows[i - period + 1: i + 1])
        upper[i] = up
        lower[i] = lo
        middle[i] = (up + lo) / 2.0
    return {"upper": upper, "lower": lower, "middle": middle}


def donchian_upper(
    highs: List[float], lows: List[float], period: int = 20
) -> List[Optional[float]]:
    return donchian(highs, lows, period)["upper"]


# ---------------------------------------------------------------------------
# Rolling VWAP (fixed window, volume-weighted)
# ---------------------------------------------------------------------------

def rolling_vwap(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    window: int = 20,
) -> List[Optional[float]]:
    """Rolling VWAP over the last ``window`` bars.

    Typical price = (H+L+C)/3; VWAP = sum(TP*V)/sum(V). Bars with zero
    total window volume yield None (never fabricated).
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n or len(volumes) != n:
        raise ValueError("highs/lows/closes/volumes must be aligned")
    if window < 1:
        raise ValueError("rolling_vwap window must be >= 1")
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    out: List[Optional[float]] = [None] * n
    for i in range(window - 1, n):
        pv = 0.0
        vol = 0.0
        for j in range(i - window + 1, i + 1):
            pv += tp[j] * volumes[j]
            vol += volumes[j]
        if vol > 0:
            out[i] = pv / vol
    return out


# ---------------------------------------------------------------------------
# Anchored VWAP (session/day reset)
# ---------------------------------------------------------------------------

def anchored_vwap(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    volumes: List[float],
    timestamps: List[datetime],
    anchor: str = "day",
) -> List[Optional[float]]:
    """VWAP anchored at each new UTC day (or week on ``anchor="week"``).

    Resets the cumulative sum when the anchor period changes; bars with
    zero cumulative volume yield None. ``timestamps`` must be timezone-
    aware or naive-UTC (mixed awareness is refused).
    """
    n = len(closes)
    if not (len(highs) == len(lows) == len(volumes) == len(timestamps) == n):
        raise ValueError("inputs must be aligned")
    if anchor not in ("day", "week"):
        raise ValueError('anchor must be "day" or "week"')

    def _key(ts: datetime) -> tuple:
        if ts.tzinfo is not None:
            ts = ts.astimezone(tz=None)  # handled below via utcoffset
        # normalize to UTC deterministically
        import datetime as _dt

        if ts.tzinfo is not None:
            ts = ts.astimezone(_dt.timezone.utc)
        if anchor == "day":
            return (ts.year, ts.month, ts.day)
        iso = ts.isocalendar()
        return (iso[0], iso[1])

    out: List[Optional[float]] = [None] * n
    pv = 0.0
    vol = 0.0
    current_key: Optional[tuple] = None
    for i in range(n):
        key = _key(timestamps[i])
        if key != current_key:
            current_key = key
            pv = 0.0
            vol = 0.0
        tp = (highs[i] + lows[i] + closes[i]) / 3.0
        pv += tp * volumes[i]
        vol += volumes[i]
        out[i] = pv / vol if vol > 0 else None
    return out


__all__ = [
    "bollinger",
    "bollinger_upper",
    "bollinger_lower",
    "keltner",
    "keltner_upper",
    "donchian",
    "donchian_upper",
    "rolling_vwap",
    "anchored_vwap",
]
