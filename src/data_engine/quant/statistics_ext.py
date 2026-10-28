"""Extended statistical / regime indicator family (v1.5.0 top-50 pack).

Choppiness Index, Vortex Indicator (+/-), approximate Hurst exponent,
Lo-MacKinlay variance ratio, rolling skewness/kurtosis and Kaufman
Efficiency Ratio — the quantitative "regime detectors" used by the
v1.5.0 confidence gate and AUTO-SCAN.

Conventions identical to the rest of ``data_engine.quant``: pure
functions, ``List[Optional[float]]`` outputs, ``None`` for insufficient
data, deterministic, no fabricated values on degenerate windows.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional


def _atr_series(
    highs: List[float], lows: List[float], closes: List[float], period: int
) -> List[Optional[float]]:
    from data_engine.quant.volatility import atr as _atr

    return _atr(highs, lows, closes, period)


# ---------------------------------------------------------------------------
# Choppiness Index
# ---------------------------------------------------------------------------

def choppiness_index(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    """Choppiness Index (Dreiss): 100 * log10(sum TR / range) / log10(period).

    High (> ~61.8) = choppy/consolidating; low (< ~38.2) = trending.
    Range clamped to [0, 100]; degenerate windows (zero range) -> None.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 2:
        raise ValueError("choppiness_index period must be >= 2")
    tr: List[float] = [0.0] * n
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    out: List[Optional[float]] = [None] * n
    denom = math.log10(period)
    for i in range(period, n):
        window = tr[i - period + 1: i + 1]
        sum_tr = sum(window)
        hh = max(highs[i - period + 1: i + 1])
        ll = min(lows[i - period + 1: i + 1])
        price_range = hh - ll
        if sum_tr > 0 and price_range > 0:
            value = 100.0 * math.log10(sum_tr / price_range) / denom
            out[i] = min(100.0, max(0.0, value))
    return out


# ---------------------------------------------------------------------------
# Vortex Indicator
# ---------------------------------------------------------------------------

def vortex(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Dict[str, List[Optional[float]]]:
    """Vortex Indicator (Botes/Siepman): VM+ / TR and VM- / TR sums.

    +VI > -VI suggests bullish trend dominance and vice versa.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 1:
        raise ValueError("vortex period must be >= 1")
    vm_plus: List[float] = [0.0] * n
    vm_minus: List[float] = [0.0] * n
    tr: List[float] = [0.0] * n
    for i in range(1, n):
        vm_plus[i] = abs(highs[i] - lows[i - 1])
        vm_minus[i] = abs(lows[i] - highs[i - 1])
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    plus: List[Optional[float]] = [None] * n
    minus: List[Optional[float]] = [None] * n
    for i in range(period, n):
        tr_sum = sum(tr[i - period + 1: i + 1])
        if tr_sum > 0:
            plus[i] = sum(vm_plus[i - period + 1: i + 1]) / tr_sum
            minus[i] = sum(vm_minus[i - period + 1: i + 1]) / tr_sum
    return {"plus": plus, "minus": minus}


def vortex_plus(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    return vortex(highs, lows, closes, period)["plus"]


def vortex_minus(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    return vortex(highs, lows, closes, period)["minus"]


# ---------------------------------------------------------------------------
# Approximate Hurst exponent (variance-of-differences method)
# ---------------------------------------------------------------------------

def hurst_exponent_approx(
    closes: List[float], max_lag: int = 20
) -> Optional[float]:
    """Single-value approximate Hurst exponent for the whole series.

    Method: variance of lag-d differences scales ~ d^(2H); H is the
    slope of log(std) vs log(d) over d = 2..max_lag. H > 0.5
    persistence, H < 0.5 mean reversion, H = 0.5 random walk.
    Returns None when any lag window is degenerate (zero variance).
    """
    if max_lag < 4 or len(closes) < max_lag * 4:
        return None
    xs: List[float] = []
    ys: List[float] = []
    for d in range(2, max_lag + 1):
        diffs = [closes[i] - closes[i - d] for i in range(d, len(closes))]
        if len(diffs) < 8:
            continue
        mean = sum(diffs) / len(diffs)
        var = sum((x - mean) ** 2 for x in diffs) / len(diffs)
        if var <= 0:
            continue
        xs.append(math.log(d))
        ys.append(0.5 * math.log(var))
    if len(xs) < 3:
        return None
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((xs[k] - x_mean) * (ys[k] - y_mean) for k in range(n))
    return sxy / sxx


# ---------------------------------------------------------------------------
# Lo-MacKinlay variance ratio
# ---------------------------------------------------------------------------

def variance_ratio(
    closes: List[float], period: int = 5
) -> Optional[float]:
    """Single-value Lo-MacKinlay VR(q) for the whole series.

    VR = Var(q-period returns) / (q * Var(1-period returns)) using
    overlapping sums (heteroskedasticity-robust normalization is out of
    scope — research approximation). VR ~ 1 random walk, > 1 trending,
    < 1 mean-reverting. None on degenerate variance.
    """
    if period < 2 or len(closes) < period * 8:
        return None
    one: List[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            one.append(math.log(closes[i] / closes[i - 1]))
    q: List[float] = []
    for i in range(period, len(closes)):
        if closes[i - period] > 0:
            q.append(math.log(closes[i] / closes[i - period]))

    def _var(xs: List[float]) -> Optional[float]:
        if len(xs) < 4:
            return None
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / len(xs)

    var1 = _var(one)
    varq = _var(q)
    if not var1 or not varq or var1 <= 0:
        return None
    return varq / (period * var1)


# ---------------------------------------------------------------------------
# Rolling skewness / kurtosis (population)
# ---------------------------------------------------------------------------

def rolling_skewness(
    closes: List[float], period: int = 30
) -> List[Optional[float]]:
    """Rolling population skewness of simple returns."""
    if period < 3:
        raise ValueError("rolling_skewness period must be >= 3")
    n = len(closes)
    rets = [0.0] * n
    for i in range(1, n):
        rets[i] = closes[i] / closes[i - 1] - 1.0 if closes[i - 1] > 0 else 0.0
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        window = rets[i - period + 1: i + 1]
        m = sum(window) / period
        m2 = sum((x - m) ** 2 for x in window) / period
        if m2 <= 0:
            continue
        m3 = sum((x - m) ** 3 for x in window) / period
        out[i] = m3 / m2 ** 1.5
    return out


def rolling_kurtosis(
    closes: List[float], period: int = 30
) -> List[Optional[float]]:
    """Rolling population kurtosis (normal = 3) of simple returns."""
    if period < 4:
        raise ValueError("rolling_kurtosis period must be >= 4")
    n = len(closes)
    rets = [0.0] * n
    for i in range(1, n):
        rets[i] = closes[i] / closes[i - 1] - 1.0 if closes[i - 1] > 0 else 0.0
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        window = rets[i - period + 1: i + 1]
        m = sum(window) / period
        m2 = sum((x - m) ** 2 for x in window) / period
        if m2 <= 0:
            continue
        m4 = sum((x - m) ** 4 for x in window) / period
        out[i] = m4 / m2 ** 2
    return out


# ---------------------------------------------------------------------------
# Kaufman Efficiency Ratio
# ---------------------------------------------------------------------------

def efficiency_ratio(
    closes: List[float], period: int = 10
) -> List[Optional[float]]:
    """Kaufman Efficiency Ratio: |net change| / sum(|bar changes|).

    ER -> 1 perfectly efficient (trending), -> 0 choppy. Used by KAMA
    and by the v1.5.0 confidence gate as the regime filter.
    """
    if period < 1:
        raise ValueError("efficiency_ratio period must be >= 1")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        net = abs(closes[i] - closes[i - period])
        path = sum(
            abs(closes[j] - closes[j - 1]) for j in range(i - period + 1, i + 1)
        )
        if path > 0:
            out[i] = net / path
    return out


__all__ = [
    "choppiness_index",
    "vortex",
    "vortex_plus",
    "vortex_minus",
    "hurst_exponent_approx",
    "variance_ratio",
    "rolling_skewness",
    "rolling_kurtosis",
    "efficiency_ratio",
]
