"""Deterministic returns calculations for the Quant Engine.

Supports:
- Simple returns: P_t / P_(t-1) - 1
- Logarithmic returns: ln(P_t / P_(t-1))
- Cumulative returns: product(1 + r_i) - 1

All returns are deterministic, NaN-safe, and preserve timestamps.
No silent division by zero. No hidden imputation.
"""

from typing import List, Optional
from datetime import datetime
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ReturnsResult:
    """Container for returns calculation results."""
    timestamps: List[datetime]
    simple_returns: List[Optional[float]]
    log_returns: List[Optional[float]]
    cumulative_returns: List[Optional[float]]

    def __len__(self) -> int:
        return len(self.simple_returns)


def simple_returns(
    prices: List[float],
    timestamps: Optional[List[datetime]] = None,
) -> ReturnsResult:
    """Calculate simple returns.

    Formula: r_t = P_t / P_(t-1) - 1

    For the first observation, returns None (insufficient data).
    If P_(t-1) is 0, returns None for that observation (division by zero).

    Args:
        prices: List of price values (must be positive).
        timestamps: Optional list of timestamps for each price.

    Returns:
        ReturnsResult with simple returns (first value is None).
    """
    n = len(prices)
    if n == 0:
        return ReturnsResult(
            timestamps=[], simple_returns=[], log_returns=[], cumulative_returns=[]
        )

    if timestamps is None:
        timestamps = [datetime.now()] * n

    simple: List[Optional[float]] = [None]  # First observation has no prior
    for i in range(1, n):
        prev = prices[i - 1]
        curr = prices[i]
        if prev == 0 or math.isnan(prev) or math.isinf(prev) or math.isnan(curr) or math.isinf(curr):
            simple.append(None)
        else:
            simple.append(curr / prev - 1.0)

    cumulative: List[Optional[float]] = [None]
    cum_product = 1.0
    for i in range(1, n):
        if simple[i] is not None:
            cum_product *= (1.0 + simple[i])
            cumulative.append(cum_product - 1.0)
        else:
            cumulative.append(None)

    return ReturnsResult(
        timestamps=timestamps,
        simple_returns=simple,
        log_returns=[None] * n,  # Filled below
        cumulative_returns=cumulative,
    )


def log_returns(
    prices: List[float],
    timestamps: Optional[List[datetime]] = None,
) -> ReturnsResult:
    """Calculate logarithmic returns.

    Formula: r_t = ln(P_t / P_(t-1))

    For the first observation, returns None (insufficient data).
    If P_(t-1) <= 0 or P_t <= 0, returns None.

    Args:
        prices: List of price values.
        timestamps: Optional list of timestamps.

    Returns:
        ReturnsResult with log returns (first value is None).
    """
    n = len(prices)
    if n == 0:
        return ReturnsResult(
            timestamps=[], simple_returns=[], log_returns=[], cumulative_returns=[]
        )

    if timestamps is None:
        timestamps = [datetime.now()] * n

    log_r: List[Optional[float]] = [None]
    for i in range(1, n):
        prev = prices[i - 1]
        curr = prices[i]
        if prev <= 0 or curr <= 0 or math.isnan(prev) or math.isinf(prev) or math.isnan(curr) or math.isinf(curr):
            log_r.append(None)
        else:
            log_r.append(math.log(curr / prev))

    return ReturnsResult(
        timestamps=timestamps,
        simple_returns=[None] * n,  # Filled below
        log_returns=log_r,
        cumulative_returns=[None] * n,
    )


def cumulative_return(returns: List[Optional[float]]) -> Optional[float]:
    """Calculate cumulative return from a series of returns.

    Formula: cumulative = product(1 + r_i) - 1

    Returns None if the series is empty or if any return causes overflow.
    """
    if not returns:
        return None

    product = 1.0
    for r in returns:
        if r is None:
            continue
        if math.isnan(r) or math.isinf(r):
            return None
        product *= (1.0 + r)
        if math.isinf(product) or math.isnan(product):
            return None

    return product - 1.0


def calculate_all_returns(
    prices: List[float],
    timestamps: Optional[List[datetime]] = None,
) -> ReturnsResult:
    """Calculate all return types at once.

    Returns a ReturnsResult with simple_returns, log_returns, and cumulative_returns
    all computed from the same price series.
    """
    n = len(prices)
    if n == 0:
        return ReturnsResult(
            timestamps=[], simple_returns=[], log_returns=[], cumulative_returns=[]
        )

    if timestamps is None:
        timestamps = [datetime.now()] * n

    # Simple returns
    simple: List[Optional[float]] = [None]
    for i in range(1, n):
        prev = prices[i - 1]
        curr = prices[i]
        if prev == 0 or math.isnan(prev) or math.isinf(prev) or math.isnan(curr) or math.isinf(curr):
            simple.append(None)
        else:
            simple.append(curr / prev - 1.0)

    # Log returns
    log_r: List[Optional[float]] = [None]
    for i in range(1, n):
        prev = prices[i - 1]
        curr = prices[i]
        if prev <= 0 or curr <= 0 or math.isnan(prev) or math.isinf(prev) or math.isnan(curr) or math.isinf(curr):
            log_r.append(None)
        else:
            log_r.append(math.log(curr / prev))

    # Cumulative returns
    cumulative: List[Optional[float]] = [None]
    cum_product = 1.0
    for i in range(1, n):
        r_i = simple[i]
        if r_i is not None:
            cum_product *= (1.0 + r_i)
            cumulative.append(cum_product - 1.0)
        else:
            cumulative.append(None)

    return ReturnsResult(
        timestamps=timestamps,
        simple_returns=simple,
        log_returns=log_r,
        cumulative_returns=cumulative,
    )