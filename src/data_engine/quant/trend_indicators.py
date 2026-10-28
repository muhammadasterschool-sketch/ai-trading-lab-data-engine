"""Extended trend indicator family (v1.5.0 top-50 pack).

ADX/DI, Supertrend, Parabolic SAR, Ichimoku, Aroon, WMA/HMA/DEMA/TEMA/
ZLEMA/KAMA moving averages, and rolling linear-regression slope/R2.

Conventions identical to the rest of ``data_engine.quant``: pure
functions, ``List[Optional[float]]`` outputs, ``None`` for insufficient
data, deterministic, Wilder smoothing where the classic definition
requires it.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence


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


def _wilder_kernel(values: Sequence[float], period: int) -> List[Optional[float]]:
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period < 1 or n < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


# ---------------------------------------------------------------------------
# ADX / +DI / -DI (Wilder)
# ---------------------------------------------------------------------------

def adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Dict[str, List[Optional[float]]]:
    """Wilder's ADX system: +DI, -DI and the smoothed DX trend gauge.

    All three series are Wilder-smoothed. First +DI/-DI index =
    ``2*period - 1``; first ADX index = ``3*period - 2``.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 2:
        raise ValueError("adx period must be >= 2")
    plus_dm: List[float] = [0.0] * n
    minus_dm: List[float] = [0.0] * n
    tr: List[float] = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
    tr_s = _wilder_kernel(tr, period)
    pdm_s = _wilder_kernel(plus_dm, period)
    mdm_s = _wilder_kernel(minus_dm, period)
    plus_di: List[Optional[float]] = [None] * n
    minus_di: List[Optional[float]] = [None] * n
    dx: List[float] = []
    dx_index: List[int] = []
    for i in range(n):
        if tr_s[i] is not None and pdm_s[i] is not None and mdm_s[i] is not None:
            t = tr_s[i]
            if t > 0:
                plus_di[i] = 100.0 * pdm_s[i] / t
                minus_di[i] = 100.0 * mdm_s[i] / t
                s = plus_di[i] + minus_di[i]
                if s > 0:
                    dx.append(100.0 * abs(plus_di[i] - minus_di[i]) / s)
                    dx_index.append(i)
    adx_series: List[Optional[float]] = [None] * n
    if len(dx) >= period:
        first = sum(dx[:period]) / period
        adx_series[dx_index[period - 1]] = first
        prev = first
        for k in range(period, len(dx)):
            prev = (prev * (period - 1) + dx[k]) / period
            adx_series[dx_index[k]] = prev
    return {"adx": adx_series, "plus_di": plus_di, "minus_di": minus_di}


def adx_value(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    """ADX line accessor (registry-friendly)."""
    return adx(highs, lows, closes, period)["adx"]


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------

def supertrend(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> Dict[str, List[Optional[float]]]:
    """Supertrend (standard ATR version): band flip trend follower.

    basic_ub = (H+L)/2 + mult*ATR; basic_lb = (H+L)/2 - mult*ATR;
    final bands close in the direction of the trend; direction = +1
    (uptrend, line = lower band) or -1 (downtrend, line = upper band).
    Deterministic tie-breaks; requires 2*period bars to stabilise.
    """
    from data_engine.quant.volatility import atr as _atr

    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 1 or multiplier <= 0:
        raise ValueError("supertrend requires period >= 1, multiplier > 0")
    atr_series = _atr(highs, lows, closes, period)
    line: List[Optional[float]] = [None] * n
    direction: List[Optional[int]] = [None] * n
    final_ub: Optional[float] = None
    final_lb: Optional[float] = None
    prev_dir: Optional[int] = None
    for i in range(n):
        a = atr_series[i]
        if a is None:
            continue
        mid = (highs[i] + lows[i]) / 2.0
        bub = mid + multiplier * a
        blb = mid - multiplier * a
        if final_ub is None or final_lb is None or prev_dir is None:
            final_ub, final_lb = bub, blb
            prev_dir = 1 if closes[i] >= mid else -1
        else:
            # band tightening rules (classic)
            final_ub = (
                bub
                if (bub < final_ub or closes[i - 1] > final_ub)
                else final_ub
            )
            final_lb = (
                blb
                if (blb > final_lb or closes[i - 1] < final_lb)
                else final_lb
            )
            if prev_dir == 1 and closes[i] < final_lb:
                prev_dir = -1
            elif prev_dir == -1 and closes[i] > final_ub:
                prev_dir = 1
        direction[i] = prev_dir
        line[i] = final_lb if prev_dir == 1 else final_ub
    return {"line": line, "direction": direction}


def supertrend_line(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 10, multiplier: float = 3.0,
) -> List[Optional[float]]:
    return supertrend(highs, lows, closes, period, multiplier)["line"]


def supertrend_direction(
    highs: List[float], lows: List[float], closes: List[float],
    period: int = 10, multiplier: float = 3.0,
) -> List[Optional[int]]:
    return supertrend(highs, lows, closes, period, multiplier)["direction"]


# ---------------------------------------------------------------------------
# Parabolic SAR (Wilder)
# ---------------------------------------------------------------------------

def parabolic_sar(
    highs: List[float],
    lows: List[float],
    af_step: float = 0.02,
    af_max: float = 0.2,
) -> List[Optional[float]]:
    """Parabolic SAR (Wilder): accelerating trailing stop.

    Deterministic bootstrap: first two bars assume uptrend if
    highs[1] >= highs[0] else downtrend. Output = SAR level per bar.
    """
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs/lows must be aligned")
    if af_step <= 0 or af_max < af_step:
        raise ValueError("parabolic_sar requires 0 < af_step <= af_max")
    out: List[Optional[float]] = [None] * n
    if n < 3:
        return out
    up = highs[1] >= highs[0]
    af = af_step
    if up:
        ep = max(highs[0], highs[1])
        sar = min(lows[0], lows[1])
    else:
        ep = min(lows[0], lows[1])
        sar = max(highs[0], highs[1])
    out[1] = sar
    for i in range(2, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 3 else lows[i - 1])
            if lows[i] < sar:
                up = False
                sar = ep
                ep = lows[i]
                af = af_step
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_step, af_max)
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 3 else highs[i - 1])
            if highs[i] > sar:
                up = True
                sar = ep
                ep = highs[i]
                af = af_step
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_step, af_max)
        out[i] = sar
    return out


# ---------------------------------------------------------------------------
# Ichimoku Kinko Hyo
# ---------------------------------------------------------------------------

def ichimoku(
    highs: List[float],
    lows: List[float],
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_b_period: int = 52,
) -> Dict[str, List[Optional[float]]]:
    """Ichimoku: Tenkan, Kijun, Senkou A and Senkou B (unshifted).

    NOTE: the classic chart shifts Senkou A/B forward by kijun_period
    and Chikou backward — this function returns the UNSHIFTED series
    (as-of values, PIT-safe); callers shift for display only.
    """
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs/lows must be aligned")
    if min(tenkan_period, kijun_period, senkou_b_period) < 1:
        raise ValueError("ichimoku periods must be >= 1")

    def _mid(period: int) -> List[Optional[float]]:
        series: List[Optional[float]] = [None] * n
        for i in range(period - 1, n):
            hi = max(highs[i - period + 1: i + 1])
            lo = min(lows[i - period + 1: i + 1])
            series[i] = (hi + lo) / 2.0
        return series

    tenkan = _mid(tenkan_period)
    kijun = _mid(kijun_period)
    senkou_b = _mid(senkou_b_period)
    senkou_a: List[Optional[float]] = [
        None if (t is None or k is None) else (t + k) / 2.0
        for t, k in zip(tenkan, kijun)
    ]
    return {
        "tenkan": tenkan,
        "kijun": kijun,
        "senkou_a": senkou_a,
        "senkou_b": senkou_b,
    }


def ichimoku_tenkan(
    highs: List[float], lows: List[float], tenkan_period: int = 9,
    kijun_period: int = 26, senkou_b_period: int = 52,
) -> List[Optional[float]]:
    return ichimoku(highs, lows, tenkan_period, kijun_period, senkou_b_period)["tenkan"]


# ---------------------------------------------------------------------------
# Aroon
# ---------------------------------------------------------------------------

def aroon(
    highs: List[float],
    lows: List[float],
    period: int = 25,
) -> Dict[str, List[Optional[float]]]:
    """Aroon Up/Down: 100 * (period - bars since extreme) / period."""
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs/lows must be aligned")
    if period < 1:
        raise ValueError("aroon period must be >= 1")
    up: List[Optional[float]] = [None] * n
    down: List[Optional[float]] = [None] * n
    for i in range(period, n):
        window_hi = highs[i - period: i + 1]
        window_lo = lows[i - period: i + 1]
        hi_idx = window_hi.index(max(window_hi))
        lo_idx = window_lo.index(min(window_lo))
        up[i] = 100.0 * (period - hi_idx) / period
        down[i] = 100.0 * (period - lo_idx) / period
    return {"up": up, "down": down}


def aroon_up(
    highs: List[float], lows: List[float], period: int = 25
) -> List[Optional[float]]:
    return aroon(highs, lows, period)["up"]


# ---------------------------------------------------------------------------
# Moving-average family: WMA, HMA, DEMA, TEMA, ZLEMA, KAMA
# ---------------------------------------------------------------------------

def wma(closes: List[float], period: int) -> List[Optional[float]]:
    """Weighted Moving Average (linear weights, newest heaviest)."""
    n = len(closes)
    if period < 1:
        raise ValueError("wma period must be >= 1")
    out: List[Optional[float]] = [None] * n
    denom = period * (period + 1) / 2.0
    for i in range(period - 1, n):
        acc = 0.0
        for k in range(period):
            acc += closes[i - period + 1 + k] * (k + 1)
        out[i] = acc / denom
    return out


def hma(closes: List[float], period: int) -> List[Optional[float]]:
    """Hull Moving Average: WMA(2*WMA(p/2) - WMA(p), sqrt(p))."""
    if period < 4:
        raise ValueError("hma period must be >= 4")
    half = max(2, period // 2)
    sqrt_p = max(2, int(math.sqrt(period)))
    wma_full = wma(closes, period)
    wma_half = wma(closes, half)
    raw: List[float] = []
    offset = n_offset = len(closes)
    for i in range(len(closes)):
        if wma_full[i] is not None and wma_half[i] is not None:
            raw.append(2.0 * wma_half[i] - wma_full[i])
        else:
            if len(raw) == 0:
                n_offset = min(n_offset, i)
    # align raw to its start index
    start = next(
        (i for i in range(len(closes))
         if wma_full[i] is not None and wma_half[i] is not None),
        len(closes),
    )
    final = wma(raw, sqrt_p) if raw else []
    out: List[Optional[float]] = [None] * len(closes)
    for i, v in enumerate(final):
        if v is not None:
            out[start + i] = v
    return out


def dema(closes: List[float], period: int) -> List[Optional[float]]:
    """Double EMA: 2*EMA - EMA(EMA)."""
    if period < 1:
        raise ValueError("dema period must be >= 1")
    first = _ema_kernel(closes, period)
    filled = [v for v in first if v is not None]
    second = _ema_kernel(filled, period)
    out: List[Optional[float]] = [None] * len(closes)
    start = next((i for i, v in enumerate(first) if v is not None), len(closes))
    for i, v in enumerate(second):
        if v is not None:
            out[start + i] = 2.0 * filled[i] - v
    return out


def tema(closes: List[float], period: int) -> List[Optional[float]]:
    """Triple EMA: 3*EMA1 - 3*EMA2 + EMA3 (frame-aligned)."""
    if period < 1:
        raise ValueError("tema period must be >= 1")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    e1 = _ema_kernel(closes, period)
    s1 = next((i for i, v in enumerate(e1) if v is not None), None)
    if s1 is None:
        return out
    f1 = [v for v in e1 if v is not None]
    e2 = _ema_kernel(f1, period)
    s2_rel = next((i for i, v in enumerate(e2) if v is not None), None)
    if s2_rel is None:
        return out
    s2 = s1 + s2_rel
    f2 = [v for v in e2 if v is not None]
    e3 = _ema_kernel(f2, period)
    s3_rel = next((i for i, v in enumerate(e3) if v is not None), None)
    if s3_rel is None:
        return out
    s3 = s2 + s3_rel
    for m, v3 in enumerate(e3):
        if v3 is None:
            continue
        j1 = (s3 + m) - s1
        j2 = (s3 + m) - s2
        if j1 < len(f1) and j2 < len(f2):
            out[s3 + m] = 3.0 * f1[j1] - 3.0 * f2[j2] + v3
    return out


def zlema(closes: List[float], period: int) -> List[Optional[float]]:
    """Zero-Lag EMA (Ehlers): EMA of (2*P - P[lag])."""
    if period < 2:
        raise ValueError("zlema period must be >= 2")
    lag = (period - 1) // 2
    n = len(closes)
    de_lagged: List[float] = []
    start = lag
    for i in range(lag, n):
        de_lagged.append(2.0 * closes[i] - closes[i - lag])
    ema = _ema_kernel(de_lagged, period)
    out: List[Optional[float]] = [None] * n
    for i, v in enumerate(ema):
        if v is not None:
            out[start + i] = v
    return out


def kama(
    closes: List[float],
    period: int = 10,
    fast: int = 2,
    slow: int = 30,
) -> List[Optional[float]]:
    """Kaufman Adaptive MA: efficiency-ratio-scaled smoothing.

    fast/slow are SC (smoothing constant) periods, not bounds.
    """
    if period < 2 or fast < 1 or slow < 2 or fast >= slow:
        raise ValueError("kama requires period >= 2 and 1 <= fast < slow")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    fast_sc = 2.0 / (fast + 1.0)
    slow_sc = 2.0 / (slow + 1.0)
    prev = sum(closes[:period]) / period
    out[period] = prev
    for i in range(period + 1, n):
        change = abs(closes[i] - closes[i - period])
        vol_sum = sum(
            abs(closes[j] - closes[j - 1]) for j in range(i - period + 1, i + 1)
        )
        er = change / vol_sum if vol_sum > 0 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        prev = sc * closes[i] + (1.0 - sc) * prev
        out[i] = prev
    return out


# ---------------------------------------------------------------------------
# Rolling linear regression slope / R2
# ---------------------------------------------------------------------------

def linear_regression_slope(
    closes: List[float], period: int
) -> List[Optional[float]]:
    """OLS slope of close against bar index over the rolling window."""
    if period < 2:
        raise ValueError("linear_regression_slope period must be >= 2")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    xs = list(range(period))
    x_mean = (period - 1) / 2.0
    denom = sum((x - x_mean) ** 2 for x in xs)
    for i in range(period - 1, n):
        window = closes[i - period + 1: i + 1]
        y_mean = sum(window) / period
        num = sum((xs[k] - x_mean) * (window[k] - y_mean) for k in range(period))
        out[i] = num / denom if denom > 0 else None
    return out


def r_squared(
    closes: List[float], period: int
) -> List[Optional[float]]:
    """R-squared of the rolling OLS fit (0..1 trend quality)."""
    if period < 2:
        raise ValueError("r_squared period must be >= 2")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    xs = list(range(period))
    x_mean = (period - 1) / 2.0
    sx = sum((x - x_mean) ** 2 for x in xs)
    for i in range(period - 1, n):
        window = closes[i - period + 1: i + 1]
        y_mean = sum(window) / period
        sxy = sum((xs[k] - x_mean) * (window[k] - y_mean) for k in range(period))
        sy = sum((y - y_mean) ** 2 for y in window)
        if sx > 0 and sy > 0:
            r = sxy / math.sqrt(sx * sy)
            out[i] = min(1.0, max(0.0, r * r))
    return out


__all__ = [
    "adx",
    "adx_value",
    "supertrend",
    "supertrend_line",
    "supertrend_direction",
    "parabolic_sar",
    "ichimoku",
    "ichimoku_tenkan",
    "aroon",
    "aroon_up",
    "wma",
    "hma",
    "dema",
    "tema",
    "zlema",
    "kama",
    "linear_regression_slope",
    "r_squared",
]
