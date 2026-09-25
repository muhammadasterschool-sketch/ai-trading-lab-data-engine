"""Trend indicator calculations for the Quant Engine.

Implements:
- EMA20, EMA50, EMA200
- SMA20, SMA50, SMA200
- Trend state helpers (K20-K50-K200 alignment, etc.)

All indicators preserve timeframe awareness and provenance.
Trend states are numerical features only — NOT trading signals.

Timeframe Integrity:
- EMA(200) on H4 means 200 H4 bars (≈33 calendar days)
- EMA(200) on D1 means 200 D1 bars (≈200 calendar days)
- Never silently convert between timeframes
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from data_engine.schemas import Timeframe
from data_engine.timeframes import get_effective_lookback_days
from data_engine.quant.moving_averages import sma, ema
import math


def ema20(prices: List[float], period: int = 20, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate EMA with period 20."""
    return ema(prices, 20, timestamps)


def ema50(prices: List[float], period: int = 50, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate EMA with period 50."""
    return ema(prices, 50, timestamps)


def ema200(prices: List[float], period: int = 200, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate EMA with period 200."""
    return ema(prices, 200, timestamps)


def sma20(prices: List[float], period: int = 20, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate SMA with period 20."""
    return sma(prices, 20, timestamps)


def sma50(prices: List[float], period: int = 50, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate SMA with period 50."""
    return sma(prices, 50, timestamps)


def sma200(prices: List[float], period: int = 200, timestamps: Optional[List[datetime]] = None) -> List[Optional[float]]:
    """Calculate SMA with period 200."""
    return sma(prices, 200, timestamps)


class TrendState:
    """Numerical trend state from moving average relationships.

    These are FEATURES, not trading signals.
    """

    @staticmethod
    def ema_bullish_alignment(
        ema20_val: Optional[float],
        ema50_val: Optional[float],
        ema200_val: Optional[float],
    ) -> bool:
        """Check if K20-K50-K200 alignment (bullish alignment).

        Returns False if any value is None or non-finite.
        """
        if any(v is None or math.isnan(v) or math.isinf(v) for v in [ema20_val, ema50_val, ema200_val]):
            return False
        return ema20_val > ema50_val > ema200_val

    @staticmethod
    def ema_bearish_alignment(
        ema20_val: Optional[float],
        ema50_val: Optional[float],
        ema200_val: Optional[float],
    ) -> bool:
        """Check if EMA20 < EMA50 < EMA200 (bearish alignment).

        Returns False if any value is None or non-finite.
        """
        if any(v is None or math.isnan(v) or math.isinf(v) for v in [ema20_val, ema50_val, ema200_val]):
            return False
        return ema20_val < ema50_val < ema200_val

    @staticmethod
    def ema_golden_cross(
        ema_short_val: Optional[float],
        ema_long_val: Optional[float],
        prev_ema_short: Optional[float] = None,
        prev_ema_long: Optional[float] = None,
    ) -> bool:
        """Check if short EMA crossed above long EMA.

        For a cross, we need current and previous values.
        Returns False if insufficient data.
        """
        if (ema_short_val is None or ema_long_val is None or
            prev_ema_short is None or prev_ema_long is None):
            return False
        if math.isnan(ema_short_val) or math.isnan(ema_long_val):
            return False
        return prev_ema_short <= prev_ema_long and ema_short_val > ema_long_val

    @staticmethod
    def ema_death_cross(
        ema_short_val: Optional[float],
        ema_long_val: Optional[float],
        prev_ema_short: Optional[float] = None,
        prev_ema_long: Optional[float] = None,
    ) -> bool:
        """Check if short EMA crossed below long EMA."""
        if (ema_short_val is None or ema_long_val is None or
            prev_ema_short is None or prev_ema_long is None):
            return False
        if math.isnan(ema_short_val) or math.isnan(ema_long_val):
            return False
        return prev_ema_short >= prev_ema_long and ema_short_val < ema_long_val

    @staticmethod
    def get_trend_description(
        ema20_val: Optional[float],
        ema50_val: Optional[float],
        ema200_val: Optional[float],
    ) -> str:
        """Get a textual description of the current trend state.

        This is numerical observation, not a recommendation.
        """
        if TrendState.ema_bullish_alignment(ema20_val, ema50_val, ema200_val):
            return "K20-K50-K200 alignment: bullish alignment"
        elif TrendState.ema_bearish_alignment(ema20_val, ema50_val, ema200_val):
            return "EMA20 < EMA50 < EMA200: bearish alignment"
        elif ema20_val is not None and ema50_val is not None and ema20_val > ema50_val:
            return "EMA20 > EMA50: short-term bullish"
        elif ema20_val is not None and ema50_val is not None and ema20_val < ema50_val:
            return "EMA20 < EMA50: short-term bearish"
        else:
            return "Indeterminate trend state"


def calculate_all_trend_indicators(
    closes: List[float],
    timeframe: Timeframe,
    instrument: str = "",
    dataset_id: str = "",
) -> Dict[str, Any]:
    """Calculate all trend indicators at once.

    Returns a dict with EMA20, EMA50, EMA200, SMA20, SMA50, SMA200
    and trend state information.
    """
    result: Dict[str, Any] = {
        "instrument": instrument,
        "dataset_id": dataset_id,
        "timeframe": timeframe.value,
        "effective_lookback_days": get_effective_lookback_days(200, timeframe),
        "indicators": {},
    }

    result["indicators"]["EMA20"] = ema20(closes)
    result["indicators"]["EMA50"] = ema50(closes)
    result["indicators"]["EMA200"] = ema200(closes)
    result["indicators"]["SMA20"] = sma20(closes)
    result["indicators"]["SMA50"] = sma50(closes)
    result["indicators"]["SMA200"] = sma200(closes)

    # Get last valid values for trend state
    def last_valid(values: List[Optional[float]]) -> Optional[float]:
        if not values:
            return None
        for v in reversed(values):
            if v is not None and not math.isnan(v) and not math.isinf(v):
                return v
        return None

    ema20_last = last_valid(result["indicators"]["EMA20"])
    ema50_last = last_valid(result["indicators"]["EMA50"])
    ema200_last = last_valid(result["indicators"]["EMA200"])

    result["trend_state"] = TrendState.get_trend_description(
        ema20_last, ema50_last, ema200_last
    )
    result["trend_bullish"] = TrendState.ema_bullish_alignment(ema20_last, ema50_last, ema200_last)
    result["trend_bearish"] = TrendState.ema_bearish_alignment(ema20_last, ema50_last, ema200_last)

    return result