"""Oscillator / momentum indicator family (v1.5.0 top-50 pack).

Convention (identical to the rest of ``data_engine.quant``):

- Pure functions; ``List[float]`` in -> ``List[Optional[float]]`` out
  (``None`` = insufficient observations or non-finite input). Multi-
  output indicators return a dict of aligned series AND ship single-
  series accessors (``*_line``) so the IndicatorRegistry contract
  (one series per name) stays intact.
- Deterministic: no RNG, no wall clock, no network. The LLM never
  computes these (deterministic quant boundary).
- Wilder-style smoothing is used where the classic definition demands
  it (RSI already lives in ``momentum``); everything else follows the
  textbook formulas cited in each docstring.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence


def _finite(value: float) -> Optional[float]:
    if value is None or not math.isfinite(value):
        return None
    return value


def _ema_kernel(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Classic EMA kernel (alpha = 2/(period+1), SMA seed)."""
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
    """Wilder smoothing kernel (alpha = 1/period, SMA seed)."""
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
# MACD
# ---------------------------------------------------------------------------

def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, List[Optional[float]]]:
    """MACD (Appel): EMA(fast) - EMA(slow), signal = EMA(signal) of that.

    Returns dict with aligned series ``macd``, ``signal``, ``histogram``.
    First valid index = ``slow + signal - 2`` for the histogram.
    """
    if fast < 1 or slow < 2 or fast >= slow or signal < 1:
        raise ValueError("macd requires 1 <= fast < slow and signal >= 1")
    ema_fast = _ema_kernel(closes, fast)
    ema_slow = _ema_kernel(closes, slow)
    macd_line: List[Optional[float]] = []
    raw_for_signal: List[float] = []
    for f, s in zip(ema_fast, ema_slow):
        if f is None or s is None:
            macd_line.append(None)
        else:
            value = f - s
            macd_line.append(value)
            raw_for_signal.append(value)
    sig = _ema_kernel(raw_for_signal, signal)
    sig_aligned: List[Optional[float]] = [None] * len(closes)
    if sig:
        offset = len(closes) - len(raw_for_signal)
        for i, v in enumerate(sig):
            sig_aligned[offset + i] = v
    histogram: List[Optional[float]] = [
        None if (m is None or s is None) else m - s
        for m, s in zip(macd_line, sig_aligned)
    ]
    return {"macd": macd_line, "signal": sig_aligned, "histogram": histogram}


def macd_line(
    closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> List[Optional[float]]:
    """MACD line accessor (registry-friendly single series)."""
    return macd(closes, fast, slow, signal)["macd"]


# ---------------------------------------------------------------------------
# Stochastic (%K/%D)
# ---------------------------------------------------------------------------

def stochastic(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    k_period: int = 14,
    d_period: int = 3,
) -> Dict[str, List[Optional[float]]]:
    """Lane's Stochastic: %K = 100*(C-LL)/(HH-LL); %D = SMA(%K, d).

    Raw %K (no slowing) is computed here; smooth by passing a larger
    ``k_period`` or averaging downstream. Flat windows (HH == LL)
    produce ``None`` (division by zero refused, not fabricated).
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if k_period < 1 or d_period < 1:
        raise ValueError("k_period/d_period must be >= 1")
    raw_k: List[Optional[float]] = [None] * n
    for i in range(k_period - 1, n):
        hh = max(highs[i - k_period + 1: i + 1])
        ll = min(lows[i - k_period + 1: i + 1])
        if hh > ll:
            raw_k[i] = 100.0 * (closes[i] - ll) / (hh - ll)
    k_series: List[Optional[float]] = [None] * n
    d_series: List[Optional[float]] = [None] * n
    for i in range(n):
        window = [raw_k[j] for j in range(i - d_period + 1, i + 1)
                  if j >= 0 and raw_k[j] is not None]
        if len(window) == d_period:
            k_series[i] = sum(window) / d_period
    for i in range(n):
        window = [k_series[j] for j in range(i - d_period + 1, i + 1)
                  if j >= 0 and k_series[j] is not None]
        if len(window) == d_period:
            d_series[i] = sum(window) / d_period
    return {"k": k_series, "d": d_series}


def stochastic_k(
    highs: List[float], lows: List[float], closes: List[float],
    k_period: int = 14, d_period: int = 3,
) -> List[Optional[float]]:
    """Slow %K accessor."""
    return stochastic(highs, lows, closes, k_period, d_period)["k"]


# ---------------------------------------------------------------------------
# Stochastic RSI
# ---------------------------------------------------------------------------

def stoch_rsi(
    closes: List[float],
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
) -> List[Optional[float]]:
    """Stochastic-of-RSI (Chande): RSI rescaled to its own range.

    None until ``rsi_period + stoch_period`` observations; flat RSI
    windows yield None (never fabricated).
    """
    from data_engine.quant.momentum import rsi as _rsi

    rsi_series = _rsi(closes, rsi_period)
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        window = [rsi_series[j] for j in range(i - stoch_period + 1, i + 1)
                  if j >= 0 and rsi_series[j] is not None]
        if len(window) < stoch_period:
            continue
        hi = max(window)
        lo = min(window)
        current = rsi_series[i]
        if current is None or hi <= lo:
            continue
        out[i] = 100.0 * (current - lo) / (hi - lo)
    if k_period > 1:
        smoothed: List[Optional[float]] = [None] * n
        for i in range(n):
            window = [out[j] for j in range(i - k_period + 1, i + 1)
                      if j >= 0 and out[j] is not None]
            if len(window) == k_period:
                smoothed[i] = sum(window) / k_period
        return smoothed
    return out


# ---------------------------------------------------------------------------
# Commodity Channel Index
# ---------------------------------------------------------------------------

def cci(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 20,
) -> List[Optional[float]]:
    """CCI (Lambert): (TP - SMA(TP)) / (0.015 * mean absolute deviation)."""
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 2:
        raise ValueError("cci period must be >= 2")
    tp = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(n)]
    out: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        window = tp[i - period + 1: i + 1]
        sma = sum(window) / period
        mad = sum(abs(x - sma) for x in window) / period
        if mad > 0:
            out[i] = (tp[i] - sma) / (0.015 * mad)
    return out


# ---------------------------------------------------------------------------
# Williams %R
# ---------------------------------------------------------------------------

def williams_r(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> List[Optional[float]]:
    """Williams %R: -100*(HH-C)/(HH-LL) (range [-100, 0])."""
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if period < 1:
        raise ValueError("williams_r period must be >= 1")
    out: List[Optional[float]] = [None] * n
    for i in range(period - 1, n):
        hh = max(highs[i - period + 1: i + 1])
        ll = min(lows[i - period + 1: i + 1])
        if hh > ll:
            out[i] = -100.0 * (hh - closes[i]) / (hh - ll)
    return out


# ---------------------------------------------------------------------------
# Rate of Change / Momentum / TRIX
# ---------------------------------------------------------------------------

def rate_of_change(
    closes: List[float], period: int = 12
) -> List[Optional[float]]:
    """ROC: 100 * (P_t / P_(t-period) - 1)."""
    if period < 1:
        raise ValueError("roc period must be >= 1")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        base = closes[i - period]
        if base != 0:
            out[i] = 100.0 * (closes[i] / base - 1.0)
    return out


def momentum(
    closes: List[float], period: int = 10
) -> List[Optional[float]]:
    """Momentum: P_t - P_(t-period)."""
    if period < 1:
        raise ValueError("momentum period must be >= 1")
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(period, n):
        out[i] = closes[i] - closes[i - period]
    return out


def trix(
    closes: List[float], period: int = 15
) -> List[Optional[float]]:
    """TRIX (Hutson): 1-period ROC of a triple-smoothed EMA.

    None until ~``3*period`` observations.
    """
    if period < 1:
        raise ValueError("trix period must be >= 1")
    first = _ema_kernel(closes, period)
    filled1 = [v for v in first if v is not None]
    second = _ema_kernel(filled1, period)
    filled2 = [v for v in second if v is not None]
    third = _ema_kernel(filled2, period)
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    valid = [v for v in third if v is not None]
    # offset: first valid triple-EMA index
    lead = n - len(valid)
    for i in range(1, len(valid)):
        if valid[i - 1] != 0:
            out[lead + i] = 100.0 * (valid[i] / valid[i - 1] - 1.0)
    return out


# ---------------------------------------------------------------------------
# Ultimate Oscillator
# ---------------------------------------------------------------------------

def ultimate_oscillator(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period1: int = 7,
    period2: int = 14,
    period3: int = 28,
) -> List[Optional[float]]:
    """Ultimate Oscillator (Williams): weighted buying-pressure average.

    BP = C - min(L, C_prev); TR = max(H, C_prev) - min(L, C_prev);
    UO = 100*(4*avg7 + 2*avg14 + avg28) / 7.
    """
    n = len(closes)
    if len(highs) != n or len(lows) != n:
        raise ValueError("highs/lows/closes must be aligned")
    if min(period1, period2, period3) < 1:
        raise ValueError("ultimate_oscillator periods must be >= 1")
    bp: List[float] = [0.0] * n
    tr: List[float] = [0.0] * n
    for i in range(1, n):
        true_low = min(lows[i], closes[i - 1])
        true_high = max(highs[i], closes[i - 1])
        bp[i] = closes[i] - true_low
        tr[i] = true_high - true_low
    out: List[Optional[float]] = [None] * n
    for i in range(period3, n):
        def _avg(p: int) -> Optional[float]:
            window_bp = bp[i - p + 1: i + 1]
            window_tr = tr[i - p + 1: i + 1]
            denom = sum(window_tr)
            if denom <= 0:
                return None
            return sum(window_bp) / denom

        a1, a2, a3 = _avg(period1), _avg(period2), _avg(period3)
        if a1 is None or a2 is None or a3 is None:
            continue
        out[i] = 100.0 * (4.0 * a1 + 2.0 * a2 + a3) / 7.0
    return out


# ---------------------------------------------------------------------------
# Awesome Oscillator
# ---------------------------------------------------------------------------

def awesome_oscillator(
    highs: List[float],
    lows: List[float],
    fast: int = 5,
    slow: int = 34,
) -> List[Optional[float]]:
    """Awesome Oscillator (Williams): SMA(median,5) - SMA(median,34)."""
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs/lows must be aligned")
    if fast < 1 or slow < 2 or fast >= slow:
        raise ValueError("awesome_oscillator requires 1 <= fast < slow")
    median = [(highs[i] + lows[i]) / 2.0 for i in range(n)]
    out: List[Optional[float]] = [None] * n
    for i in range(slow - 1, n):
        fast_sma = sum(median[i - fast + 1: i + 1]) / fast
        slow_sma = sum(median[i - slow + 1: i + 1]) / slow
        out[i] = fast_sma - slow_sma
    return out


__all__ = [
    "macd",
    "macd_line",
    "stochastic",
    "stochastic_k",
    "stoch_rsi",
    "cci",
    "williams_r",
    "rate_of_change",
    "momentum",
    "trix",
    "ultimate_oscillator",
    "awesome_oscillator",
]
