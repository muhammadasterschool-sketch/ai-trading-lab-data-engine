"""Statistical functions for the Quant Engine.

Implements deterministic:
- mean, median
- variance, standard deviation
- covariance, correlation
- z-score
- percentile
- rolling statistics

All functions are deterministic and explicitly handle:
- NaN and Infinity
- Empty arrays
- Zero denominators
- Missing data (returns None)

Degrees of freedom convention:
- Population stats use ddof=0 (default)
- Sample stats use ddof=1
"""

from typing import List, Optional
from datetime import datetime
import math


def mean(values: List[float], ddof: int = 0) -> Optional[float]:
    """Calculate arithmetic mean.

    Returns None for empty lists or lists with only NaN/Inf values.
    ddof is accepted for API consistency but has no effect on mean.
    """
    valid = [v for v in values if v is not None and not math.isnan(v) and not math.isinf(v)]
    if not valid:
        return None
    return sum(valid) / len(valid)


def median(values: List[float]) -> Optional[float]:
    """Calculate median.

    Returns None for empty lists.
    """
    valid = sorted([v for v in values if v is not None and not math.isnan(v) and not math.isinf(v)])
    if not valid:
        return None
    n = len(valid)
    if n % 2 == 1:
        return valid[n // 2]
    return (valid[n // 2 - 1] + valid[n // 2]) / 2.0


def variance(
    values: List[float],
    ddof: int = 0,
) -> Optional[float]:
    """Calculate variance.

    ddof: Delta degrees of freedom. Default 0 (population variance).
    Returns None for empty lists or insufficient data.
    """
    valid = [v for v in values if v is not None and not math.isnan(v) and not math.isinf(v)]
    n = len(valid)
    if n == 0:
        return None
    if n - ddof <= 0:
        return None

    m = mean(valid)
    if m is None:
        return None

    return sum((v - m) ** 2 for v in valid) / (n - ddof)


def std(
    values: List[float],
    ddof: int = 0,
) -> Optional[float]:
    """Calculate standard deviation.

    ddof: Delta degrees of freedom. Default 0 (population std).
    Returns None for empty lists or insufficient data.
    """
    v = variance(values, ddof)
    if v is None:
        return None
    return math.sqrt(v)


def covariance(
    x: List[float],
    y: List[float],
    ddof: int = 0,
) -> Optional[float]:
    """Calculate covariance between two series.

    Returns None if series have different lengths, are empty, or have insufficient data.
    """
    if len(x) != len(y):
        return None

    valid_pairs = [
        (xi, yi) for xi, yi in zip(x, y)
        if (xi is not None and not math.isnan(xi) and not math.isinf(xi) and
            yi is not None and not math.isnan(yi) and not math.isinf(yi))
    ]

    n = len(valid_pairs)
    if n == 0 or n - ddof <= 0:
        return None

    x_mean = mean([p[0] for p in valid_pairs])
    y_mean = mean([p[1] for p in valid_pairs])
    if x_mean is None or y_mean is None:
        return None

    return sum((xi - x_mean) * (yi - y_mean) for xi, yi in valid_pairs) / (n - ddof)


def correlation(
    x: List[float],
    y: List[float],
    ddof: int = 0,
) -> Optional[float]:
    """Calculate Pearson correlation coefficient.

    Returns None if insufficient data or if either std is zero.
    Result is in [-1, 1] when defined.
    """
    if len(x) != len(y):
        return None

    valid_pairs = [
        (xi, yi) for xi, yi in zip(x, y)
        if (xi is not None and not math.isnan(xi) and not math.isinf(xi) and
            yi is not None and not math.isnan(yi) and not math.isinf(yi))
    ]

    n = len(valid_pairs)
    if n == 0 or n - ddof <= 0:
        return None

    cov = covariance([p[0] for p in valid_pairs], [p[1] for p in valid_pairs], ddof)
    x_std = std([p[0] for p in valid_pairs], ddof)
    y_std = std([p[1] for p in valid_pairs], ddof)

    if cov is None or x_std is None or y_std is None:
        return None

    if x_std == 0 or y_std == 0:
        return None  # Zero variance means correlation is undefined

    corr = cov / (x_std * y_std)

    # Clamp to [-1, 1] due to floating point precision
    if corr < -1.0:
        corr = -1.0
    elif corr > 1.0:
        corr = 1.0

    return corr


def z_score(
    values: List[float],
    value: float,
    ddof: int = 0,
) -> Optional[float]:
    """Calculate z-score of a value relative to a series.

    z = (value - mean) / std

    Returns None if std is zero or insufficient data.
    """
    m = mean(values)
    s = std(values, ddof)
    if m is None or s is None or s == 0:
        return None
    return (value - m) / s


def percentile(
    values: List[float],
    p: float,
) -> Optional[float]:
    """Calculate percentile using linear interpolation.

    p must be in [0, 100].
    Returns None for empty lists.
    """
    if p < 0 or p > 100:
        raise ValueError(f"Percentile must be in [0, 100], got {p}")

    valid = sorted([v for v in values if v is not None and not math.isnan(v) and not math.isinf(v)])
    n = len(valid)
    if n == 0:
        return None

    if n == 1:
        return valid[0]

    # Linear interpolation method
    rank = (p / 100.0) * (n - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))

    if lower == upper:
        return valid[lower]

    frac = rank - lower
    return valid[lower] + frac * (valid[upper] - valid[lower])


def rolling_mean(
    values: List[float],
    window: int,
) -> List[Optional[float]]:
    """Calculate rolling mean."""
    return rolling_stat(values, window, mean)


def rolling_stat(
    values: List[float],
    window: int,
    stat_func,
) -> List[Optional[float]]:
    """Calculate rolling statistics with a given function.

    Generic rolling window calculation.
    """
    n = len(values)
    if window <= 0:
        raise ValueError(f"Window must be positive, got {window}")
    if n == 0:
        return []

    result: List[Optional[float]] = [None] * n
    for i in range(window - 1, n):
        window_vals = values[i - window + 1 : i + 1]
        if len(window_vals) != window:
            continue
        if any(math.isnan(v) or math.isinf(v) for v in window_vals):
            result[i] = None
            continue
        result[i] = stat_func(window_vals)

    return result


def rolling_percentile(
    values: List[float],
    window: int,
    p: float,
) -> List[Optional[float]]:
    """Calculate rolling percentile."""
    n = len(values)
    if window <= 0 or p < 0 or p > 100:
        raise ValueError(f"Invalid parameters: window={window}, p={p}")
    if n == 0:
        return []

    result: List[Optional[float]] = [None] * n
    for i in range(window - 1, n):
        window_vals = values[i - window + 1 : i + 1]
        if len(window_vals) != window:
            continue
        if any(math.isnan(v) or math.isinf(v) for v in window_vals):
            result[i] = None
            continue
        result[i] = percentile(window_vals, p)

    return result