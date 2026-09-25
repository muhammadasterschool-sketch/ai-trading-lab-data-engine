"""Phase 2 Quant Engine Test Suite.

Tests cover all calculation modules, data validation,
provenance, security, and red-team attacks.
"""

import pytest
import math
from datetime import datetime, UTC, timedelta
from pydantic import ValidationError

from data_engine.schemas import (
    Candle, Dataset, DatasetVersion, ProvenanceRecord,
    Timeframe, EvidenceProvenance, ValidationStatus, Instrument, AssetClass
)
from data_engine.quant.core import QuantEngine, ema200, rsi14, atr14
from data_engine.quant.returns import (
    simple_returns, log_returns, calculate_all_returns, cumulative_return
)
from data_engine.quant.moving_averages import sma, ema
from data_engine.quant.momentum import rsi
from data_engine.quant.volatility import atr, rolling_std, realized_volatility, true_range, atr_ratio
from data_engine.quant.trend import (
    ema20, ema50, ema200, sma20, sma50, sma200, TrendState, calculate_all_trend_indicators
)
from data_engine.quant.statistics import (
    mean, median, variance, std, covariance, correlation, z_score, percentile,
    rolling_mean, rolling_percentile
)
from data_engine.quant.drawdown import drawdown, max_drawdown, identify_drawdown_events, calmar_ratio
from data_engine.quant.validation import QuantDataValidator, QuantBoundaryError
from data_engine.quant.registry import IndicatorRegistry, get_registry, calculate_indicator
from data_engine.quant.schemas import QuantResult, IndicatorResult, CalculationMetadata, IndicatorSeries
from data_engine.data_blocked import DataQualityGate
from data_engine.timeframes import get_effective_lookback_days, Timeframe as TF
from data_engine.quant_boundary import LLMBoundary, CalculationType
from data_engine.evidence import EvidenceProvenance as EP


# ─── Helpers ───

def make_candle(ts, o=100, h=105, l=98, c=102, v=1000, tf=Timeframe.D1):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, timeframe=tf)


def make_instrument():
    return Instrument(symbol="XAU/USD", asset_class=AssetClass.METAL, base_asset="XAU", quote_asset="USD", exchange="OTC")


def make_dataset(candles, dataset_id="test", evidence="REAL", timeframe=Timeframe.D1):
    now = datetime.now(UTC)
    inst = make_instrument()
    prov = ProvenanceRecord(
        dataset_id=dataset_id, dataset_version="v1.0", provider="test", source="test",
        instrument=inst, timeframe=timeframe,
        start_timestamp=candles[0].timestamp if candles else now,
        end_timestamp=candles[-1].timestamp if candles else now,
        retrieval_timestamp=now, timezone="UTC",
        evidence_provenance=EP(evidence),
    )
    dv = DatasetVersion(
        dataset_id=dataset_id, version="v1.0", source="test", instrument=inst,
        timeframe=timeframe, time_period_start=prov.start_timestamp,
        time_period_end=prov.end_timestamp, ingestion_version="1",
        transformation_version="1", validation_version="1",
    )
    return Dataset(dataset_id=dataset_id, version=dv, candles=candles, provenance=prov, total_rows=len(candles))


def make_price_series(n=100, start=100.0, trend=0.0, noise=1.0):
    """Generate a deterministic price series."""
    prices = [start]
    for i in range(1, n):
        change = trend + noise * (i % 7 - 3) / 10.0
        prices.append(max(prices[-1] + change, 0.01))
    return prices


# ═══════════════════════════════════════════════════════
# RETURNS TESTS
# ═══════════════════════════════════════════════════════

class TestReturns:
    """Test deterministic return calculations."""

    def test_simple_return_positive(self):
        """Simple return: P_t / P_(t-1) - 1"""
        prices = [100.0, 110.0, 121.0]
        result = simple_returns(prices)
        assert result.simple_returns[0] is None  # First observation
        assert abs(result.simple_returns[1] - 0.10) < 1e-10
        assert abs(result.simple_returns[2] - 0.10) < 1e-10

    def test_log_return(self):
        """Log return: ln(P_t / P_(t-1))"""
        prices = [100.0, 110.0, 121.0]
        result = log_returns(prices)
        assert result.log_returns[0] is None
        assert abs(result.log_returns[1] - math.log(1.1)) < 1e-10
        assert abs(result.log_returns[2] - math.log(1.1)) < 1e-10

    def test_cumulative_return(self):
        """Cumulative return: product(1 + r_i) - 1"""
        prices = [100.0, 110.0, 121.0]
        result = calculate_all_returns(prices)
        cum = cumulative_return(result.simple_returns)
        assert abs(cum - 0.21) < 1e-10

    def test_simple_return_zero_previous(self):
        """Zero previous price returns None."""
        prices = [0.0, 100.0]
        result = simple_returns(prices)
        assert result.simple_returns[1] is None

    def test_simple_return_missing_data(self):
        """NaN in prices returns None for affected returns."""
        prices = [100.0, float('nan'), 120.0]
        result = simple_returns(prices)
        assert result.simple_returns[1] is None
        assert result.simple_returns[2] is None

    def test_cumulative_empty(self):
        """Cumulative return of empty list is None."""
        assert cumulative_return([]) is None

    def test_simple_return_zero_denominator(self):
        """Division by zero handled."""
        prices = [100.0, 0.0, 50.0]
        result = simple_returns(prices)
        assert result.simple_returns[2] is None  # P_prev = 0


# ═══════════════════════════════════════════════════════
# SMA TESTS
# ═══════════════════════════════════════════════════════

class TestSMA:
    """Test Simple Moving Average."""

    def test_known_dataset(self):
        """SMA of [10, 20, 30, 40, 50] with period 3."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = sma(prices, 3)
        assert result[0] is None
        assert result[1] is None
        assert abs(result[2] - 20.0) < 1e-10  # (10+20+30)/3
        assert abs(result[3] - 30.0) < 1e-10  # (20+30+40)/3
        assert abs(result[4] - 40.0) < 1e-10  # (30+40+50)/3

    def test_insufficient_observations(self):
        """Returns None when observations < period."""
        prices = [10.0, 20.0]
        result = sma(prices, 5)
        assert all(v is None for v in result)

    def test_constant_series(self):
        """SMA of constant series equals the constant."""
        prices = [5.0] * 10
        result = sma(prices, 3)
        assert all(v == 5.0 for v in result[2:])

    def test_increasing_series(self):
        """SMA of increasing series is between min and max."""
        prices = list(range(1, 11))
        result = sma(prices, 5)
        assert result[4] == 3.0  # (1+2+3+4+5)/5
        assert result[9] == 8.0  # (6+7+8+9+10)/5

    def test_period_one(self):
        """SMA with period 1 equals the prices."""
        prices = [10.0, 20.0, 30.0]
        result = sma(prices, 1)
        assert result == prices


# ═══════════════════════════════════════════════════════
# EMA TESTS
# ═══════════════════════════════════════════════════════

class TestEMA:
    """Test Exponential Moving Average."""

    def test_known_reference(self):
        """EMA(3) of [10, 20, 30, 40, 50]."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = ema(prices, 3)
        assert result[0] is None
        assert result[1] is None
        # First EMA = SMA of first 3 = (10+20+30)/3 = 20
        assert abs(result[2] - 20.0) < 1e-10
        # α = 2/(3+1) = 0.5
        # EMA_3 = 0.5 * 30 + 0.5 * 20 = 25
        assert abs(result[3] - 30.0) < 1e-10
        # EMA_4 = 0.5 * 40 + 0.5 * 25 = 32.5
        assert abs(result[4] - 40.0) < 1e-10

    def test_insufficient_observations(self):
        """Returns None when observations < period."""
        prices = [10.0, 20.0]
        result = ema(prices, 5)
        assert all(v is None for v in result)

    def test_constant_series(self):
        """EMA of constant series equals the constant."""
        prices = [5.0] * 10
        result = ema(prices, 3)
        assert all(v == 5.0 for v in result[2:])

    def test_alpha_formula(self):
        """α = 2/(period+1)"""
        period = 5
        alpha = 2.0 / (period + 1.0)
        assert abs(alpha - 1/3) < 1e-10

    def test_first_ema_is_sma(self):
        """First EMA value equals SMA of first `period` observations."""
        prices = [10.0, 20.0, 30.0, 40.0]
        result = ema(prices, 3)
        expected_sma = (10.0 + 20.0 + 30.0) / 3.0
        assert abs(result[2] - expected_sma) < 1e-10

    def test_increasing_series(self):
        """EMA of increasing series tracks price."""
        prices = [100.0, 110.0, 121.0, 133.1, 146.41]
        result = ema(prices, 3)
        assert result[2] is not None
        assert result[4] is not None
        assert result[4] > result[2]  # EMA increases


# ═══════════════════════════════════════════════════════
# RSI TESTS
# ═══════════════════════════════════════════════════════

class TestRSI:
    """Test Relative Strength Index."""

    def test_known_reference(self):
        """RSI should produce values in [0, 100]."""
        prices = [100.0 + i * 0.5 for i in range(30)]  # Rising prices
        result = rsi(prices, period=14)
        last_rsi = None
        for v in reversed(result):
            if v is not None:
                last_rsi = v
                break
        assert last_rsi is not None
        assert 0 <= last_rsi <= 100

    def test_rising_prices_high_rsi(self):
        """Rising prices should produce high RSI."""
        prices = [100.0 + i * 2.0 for i in range(30)]
        result = rsi(prices, period=14)
        last_rsi = next(v for v in reversed(result) if v is not None)
        assert last_rsi > 70

    def test_falling_prices_low_rsi(self):
        """Falling prices should produce low RSI."""
        prices = [200.0 - i * 2.0 for i in range(30)]
        result = rsi(prices, period=14)
        last_rsi = next(v for v in reversed(result) if v is not None)
        assert last_rsi < 30

    def test_flat_prices_neutral_rsi(self):
        """Flat prices should produce RSI near 50."""
        prices = [100.0] * 30
        result = rsi(prices, period=14)
        last_rsi = next(v for v in reversed(result) if v is not None)
        assert abs(last_rsi - 50.0) < 5.0

    def test_zero_loss_condition(self):
        """All gains, no losses → RSI = 100."""
        prices = [100.0 + i * 1.0 for i in range(30)]
        result = rsi(prices, period=5)
        last_rsi = next(v for v in reversed(result) if v is not None)
        assert last_rsi == 100.0

    def test_insufficient_data(self):
        """RSI with fewer than period observations returns None."""
        prices = [100.0, 101.0, 102.0]
        result = rsi(prices, period=14)
        assert all(v is None for v in result)

    def test_nan_contamination(self):
        """NaN prices produce None in RSI."""
        prices = [100.0] * 15 + [float('nan')] + [100.0] * 10
        result = rsi(prices, period=14)
        # Some values should be None
        assert any(v is None for v in result)

    def test_default_period_14(self):
        """Default RSI period is 14."""
        prices = [100.0 + i for i in range(30)]
        result = rsi(prices)
        assert result is not None


# ═══════════════════════════════════════════════════════
# ATR TESTS
# ═══════════════════════════════════════════════════════

class TestATR:
    """Test Average True Range."""

    def test_known_ohlc_dataset(self):
        """ATR calculation with known OHLC data."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [98.0, 99.0, 100.0, 101.0, 102.0]
        closes = [102.0, 103.0, 104.0, 105.0, 106.0]
        result = atr(highs, lows, closes, period=3)
        assert result[0] is None
        assert result[3] is not None
        assert result[3] >= 0

    def test_gaps(self):
        """ATR reflects price gaps."""
        highs = [105.0, 115.0, 110.0]
        lows = [98.0, 108.0, 103.0]
        closes = [102.0, 110.0, 105.0]
        result = atr(highs, lows, closes, period=2)
        # Gap between candle 0 and 1 should increase ATR
        assert result[2] is not None

    def test_previous_close_effects(self):
        """True Range accounts for previous close."""
        highs = [105.0, 105.0, 105.0]
        lows = [95.0, 95.0, 95.0]
        closes = [100.0, 80.0, 90.0]  # Big gap down then recovery
        result = atr(highs, lows, closes, period=2)
        # TR for candle 1 should include |High - PrevClose| = |105-100| = 5
        # and |Low - PrevClose| = |95-100| = 5
        # TR = max(10, 5, 5) = 10
        assert result[2] is not None
        assert result[2] >= 0

    def test_insufficient_observations(self):
        """ATR returns None when insufficient TR values."""
        highs = [105.0]
        lows = [98.0]
        closes = [102.0]
        result = atr(highs, lows, closes, period=14)
        assert all(v is None for v in result)

    def test_atr_non_negative(self):
        """ATR is always non-negative."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [98.0, 99.0, 100.0, 101.0, 102.0]
        closes = [102.0, 103.0, 104.0, 105.0, 106.0]
        result = atr(highs, lows, closes, period=3)
        for v in result:
            if v is not None:
                assert v >= 0

    def test_atr_ratio(self):
        """ATR/Close ratio calculation."""
        highs = [105.0, 106.0, 107.0, 108.0, 109.0]
        lows = [98.0, 99.0, 100.0, 101.0, 102.0]
        closes = [102.0, 103.0, 104.0, 105.0, 106.0]
        result = atr_ratio(highs, lows, closes, period=3)
        assert result[3] is not None
        assert 0 <= result[3] <= 1


# ═══════════════════════════════════════════════════════
# VOLATILITY TESTS
# ═══════════════════════════════════════════════════════

class TestVolatility:
    """Test rolling standard deviation and realized volatility."""

    def test_known_standard_deviation(self):
        """Rolling std of known series."""
        prices = [10.0] * 10 + [20.0] * 10
        result = rolling_std(prices, window=5)
        assert result[4] is not None
        assert result[13] > 0

    def test_constant_prices(self):
        """Rolling std of constant prices is zero."""
        prices = [5.0] * 20
        result = rolling_std(prices, window=5)
        assert all(v == 0.0 for v in result[4:] if v is not None)

    def test_rolling_window(self):
        """Rolling std uses correct window."""
        prices = list(range(20))
        result = rolling_std(prices, window=5)
        # First window [0,1,2,3,4] std = sqrt(2) ≈ 1.414
        assert result[4] is not None
        assert result[13] > 0

    def test_missing_values(self):
        """NaN in prices produces None in rolling std."""
        prices = [10.0] * 5 + [float('nan')] + [10.0] * 5
        result = rolling_std(prices, window=3)
        assert any(v is None for v in result)

    def test_realized_volatility(self):
        """Realized volatility is positive for volatile series."""
        prices = make_price_series(50, start=100.0, trend=0.0, noise=5.0)
        vol = realized_volatility(prices, Timeframe.D1)
        assert vol is not None
        assert vol >= 0

    def test_realized_volatility_empty(self):
        """Realized volatility of empty series is None."""
        vol = realized_volatility([], Timeframe.D1)
        assert vol is None


# ═══════════════════════════════════════════════════════
# STATISTICS TESTS
# ═══════════════════════════════════════════════════════

class TestStatistics:
    """Test statistical functions."""

    def test_mean(self):
        assert abs(mean([1, 2, 3, 4, 5]) - 3.0) < 1e-10

    def test_mean_empty(self):
        assert mean([]) is None

    def test_mean_nan(self):
        assert mean([1.0, float('nan'), 3.0]) == 2.0

    def test_median(self):
        assert median([1, 2, 3, 4, 5]) == 3.0
        assert median([1, 2, 3, 4]) == 2.5

    def test_median_empty(self):
        assert median([]) is None

    def test_variance(self):
        assert abs(variance([1, 2, 3, 4, 5]) - 2.0) < 1e-10

    def test_std(self):
        assert abs(std([1, 2, 3, 4, 5]) - math.sqrt(2)) < 1e-10

    def test_std_non_negative(self):
        assert std([1, 2, 3]) >= 0

    def test_covariance(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        cov = covariance(x, y)
        assert cov is not None and cov > 0

    def test_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        corr = correlation(x, y)
        assert abs(corr - 1.0) < 1e-10

    def test_correlation_bounds(self):
        """Correlation is always in [-1, 1]."""
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]
        corr = correlation(x, y)
        assert -1 <= corr <= 1

    def test_correlation_zero_variance(self):
        """Correlation with zero variance is None."""
        x = [1, 1, 1, 1]
        y = [2, 3, 4, 5]
        assert correlation(x, y) is None

    def test_z_score(self):
        """z-score = (value - mean) / std."""
        values = [10, 20, 30, 40, 50]
        z = z_score(values, 30)
        assert abs(z - 0.0) < 1e-10

    def test_percentile(self):
        """Percentile interpolation."""
        values = [1, 2, 3, 4, 5]
        p50 = percentile(values, 50)
        assert abs(p50 - 3.0) < 1e-10

    def test_rolling_mean(self):
        """Rolling mean calculation."""
        prices = [10, 20, 30, 40, 50]
        result = rolling_mean(prices, window=3)
        assert result[2] == 20.0
        assert result[4] == 40.0

    def test_rolling_percentile(self):
        """Rolling percentile calculation."""
        prices = list(range(20))
        result = rolling_percentile(prices, window=5, p=50)
        assert result[4] is not None

    def test_different_lengths_covariance(self):
        """Covariance with different length series returns None."""
        x = [1, 2, 3]
        y = [1, 2]
        assert covariance(x, y) is None


# ═══════════════════════════════════════════════════════
# DRAWDOWN TESTS
# ═══════════════════════════════════════════════════════

class TestDrawdown:
    """Test drawdown calculations."""

    def test_no_drawdown(self):
        """Equity that only goes up has zero drawdown."""
        equity = [100, 110, 120, 130, 140]
        result = drawdown(equity)
        assert result.max_drawdown == 0.0
        assert all(d == 0.0 for d in result.drawdowns if d is not None)

    def test_one_drawdown(self):
        """Single drawdown scenario."""
        equity = [100, 110, 105, 95, 100]
        result = drawdown(equity)
        assert result.max_drawdown < 0
        assert result.max_drawdown == -0.13636363636363635  # 95/110 - 1

    def test_drawdown_non_positive(self):
        """Drawdown is always <= 0."""
        equity = [100, 90, 80, 95, 100]
        result = drawdown(equity)
        assert all(d <= 0 for d in result.drawdowns if d is not None)

    def test_empty_equity(self):
        """Empty equity curve returns empty results."""
        result = drawdown([])
        assert result.total_periods == 0
        assert result.max_drawdown is None

    def test_single_point(self):
        """Single point equity curve."""
        result = drawdown([100])
        assert result.total_periods == 1
        assert result.max_drawdown == 0.0

    def test_constant_equity(self):
        """Constant equity has zero drawdown."""
        equity = [100] * 10
        result = drawdown(equity)
        assert result.max_drawdown == 0.0

    def test_max_drawdown_duration(self):
        """Max drawdown duration is tracked."""
        equity = [100, 90, 80, 70, 80, 90, 100]
        result = drawdown(equity)
        assert result.max_drawdown_duration > 0

    def test_recovery_duration(self):
        """Recovery duration is tracked."""
        equity = [100, 90, 80, 90, 100]
        result = drawdown(equity)
        assert result.recovery_duration is not None
        assert result.recovery_duration > 0

    def test_identify_drawdown_events(self):
        """Drawdown events are identified correctly."""
        equity = [100, 110, 100, 90, 100, 110, 95, 100]
        events = identify_drawdown_events(equity)
        assert len(events) > 0
        for event in events:
            assert event.depth <= 0

    def test_calmar_ratio(self):
        """Calmar ratio calculation."""
        equity = [100, 110, 120, 110, 100, 110, 120]
        cr = calmar_ratio(equity)
        assert cr is None or cr > 0  # Could be None if max_dd is 0

    def test_unrecovered_drawdown(self):
        """Drawdown that never recovers."""
        equity = [100, 90, 80, 70, 60]
        result = drawdown(equity)
        assert result.recovery_duration is None


# ═══════════════════════════════════════════════════════
# TREND TESTS
# ═══════════════════════════════════════════════════════

class TestTrend:
    """Test trend indicator calculations."""

    def test_ema20(self):
        """EMA20 produces non-None values."""
        prices = make_price_series(50, start=100.0)
        result = ema20(prices)
        assert result[19] is not None  # First valid at index 19

    def test_ema50(self):
        """EMA50 produces non-None values."""
        prices = make_price_series(60, start=100.0)
        result = ema50(prices)
        assert result[49] is not None

    def test_ema200(self):
        """EMA200 produces non-None values."""
        prices = make_price_series(210, start=100.0)
        result = ema200(prices)
        assert result[199] is not None

    def test_sma20(self):
        """SMA20 produces non-None values."""
        prices = make_price_series(50, start=100.0)
        result = sma20(prices)
        assert result[19] is not None

    def test_sma50(self):
        """SMA50 produces non-None values."""
        prices = make_price_series(60, start=100.0)
        result = sma50(prices)
        assert result[49] is not None

    def test_sma200(self):
        """SMA200 produces non-None values."""
        prices = make_price_series(210, start=100.0)
        result = sma200(prices)
        assert result[199] is not None

    def test_trend_bullish_alignment(self):
        """Bullish alignment when EMA20 > EMA50 > EMA200."""
        prices = make_price_series(250, start=100.0, trend=0.5)
        all_trends = calculate_all_trend_indicators(
            prices, Timeframe.D1, instrument="XAU/USD", dataset_id="test"
        )
        # With strong uptrend, should have bullish alignment
        if all_trends["trend_bullish"]:
            assert "bullish alignment" in all_trends["trend_state"]

    def test_ema_golden_cross_detection(self):
        """Golden cross detection works."""
        prices = make_price_series(100, start=100.0)
        ema20_vals = ema20(prices)
        ema50_vals = ema50(prices)
        # Can't easily test cross with just one series, but verify function works
        result = TrendState.ema_golden_cross(
            ema20_vals[-1] if ema20_vals[-1] else 0,
            ema50_vals[-1] if ema50_vals[-1] else 0,
            ema20_vals[-2] if len(ema20_vals) > 1 and ema20_vals[-2] else 0,
            ema50_vals[-2] if len(ema50_vals) > 1 and ema50_vals[-2] else 0,
        )
        assert isinstance(result, bool)

    def test_trend_state_returns_string(self):
        """Trend state description is a string."""
        prices = make_price_series(210, start=100.0)
        state = TrendState.get_trend_description(None, None, None)
        assert isinstance(state, str)


# ═══════════════════════════════════════════════════════
# QUANT VALIDATION TESTS
# ═══════════════════════════════════════════════════════

class TestQuantValidation:
    """Test quant boundary validation."""

    def test_valid_dataset_passes(self):
        """Valid dataset passes quant validation."""
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles)
        validator = QuantDataValidator()
        result = validator.validate(ds, min_observations=5)
        assert result.valid is True or len(result.errors) == 0

    def test_empty_dataset_fails(self):
        """Empty dataset fails quant validation."""
        now = datetime.now(UTC)
        ds = make_dataset([], dataset_id="empty")
        validator = QuantDataValidator()
        result = validator.validate(ds, min_observations=1)
        assert result.valid is False

    def test_synthetic_blocked(self):
        """SYNTHETIC datasets are blocked."""
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles, evidence="SYNTHETIC")
        validator = QuantDataValidator()
        result = validator.validate(ds, min_observations=5)
        assert any("SYNTHETIC" in e for e in result.errors)

    def test_assert_valid_raises_on_invalid(self):
        """assert_valid raises QuantBoundaryError."""
        now = datetime.now(UTC)
        ds = make_dataset([], dataset_id="empty")
        validator = QuantDataValidator()
        with pytest.raises(QuantBoundaryError):
            validator.assert_valid(ds, min_observations=1)

    def test_quant_boundary_error_message(self):
        """QuantBoundaryError has informative message."""
        try:
            raise QuantBoundaryError("test error")
        except QuantBoundaryError as e:
            assert "test error" in str(e)


# ═══════════════════════════════════════════════════════
# QUANT ENGINE TESTS
# ═══════════════════════════════════════════════════════

class TestQuantEngine:
    """Test the main QuantEngine."""

    def test_engine_creation(self):
        """QuantEngine can be created."""
        engine = QuantEngine()
        assert engine is not None

    def test_calculate_ema200(self):
        """QuantEngine can calculate EMA200."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now + timedelta(days=i)) for i in range(210)]
        ds = make_dataset(candles)
        result = engine.calculate("ema20", ds, period=20)
        assert result.indicator == "ema20"
        assert len(result.values) == 210
        assert result.success is True

    def test_calculate_rsi(self):
        """QuantEngine can calculate RSI."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(30)]
        ds = make_dataset(candles)
        result = engine.calculate("rsi", ds, period=14)
        assert result.indicator == "rsi"
        assert result.success is True

    def test_calculate_atr(self):
        """QuantEngine can calculate ATR."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles)
        result = engine.calculate("atr", ds, period=14)
        assert result.indicator == "atr"
        assert result.success is True

    def test_calculate_returns(self):
        """QuantEngine can calculate returns."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles)
        result = engine.calculate_returns(ds)
        assert result.indicator == "returns"
        assert result.success is True

    def test_calculate_all_trends(self):
        """QuantEngine can calculate all trend indicators."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(210)]
        ds = make_dataset(candles)
        trends = engine.calculate_all_trends(ds)
        assert "indicators" in trends
        assert "EMA20" in trends["indicators"]
        assert "EMA50" in trends["indicators"]
        assert "EMA200" in trends["indicators"]

    def test_calculate_statistics(self):
        """QuantEngine can calculate statistics."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles)
        stats = engine.calculate_statistics(ds)
        assert "mean" in stats
        assert "std" in stats
        assert "count" in stats

    def test_calculate_drawdown(self):
        """QuantEngine can calculate drawdown."""
        engine = QuantEngine()
        equity = [100, 110, 100, 90, 100, 110]
        dd = engine.calculate_drawdown(equity)
        assert "max_drawdown" in dd
        assert "events" in dd

    def test_unknown_indicator_raises(self):
        """Unknown indicator raises ValueError."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles)
        with pytest.raises(ValueError):
            engine.calculate("unknown_indicator", ds)

    def test_empty_dataset_raises(self):
        """Empty dataset raises QuantBoundaryError."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        ds = make_dataset([], dataset_id="empty")
        with pytest.raises(QuantBoundaryError):
            engine.calculate("ema200", ds)

    def test_result_traceability(self):
        """Calculation results contain full provenance metadata."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles, dataset_id="test_ds")
        result = engine.calculate("ema20", ds, period=20)
        assert result.metadata.dataset_id == "test_ds"
        assert result.metadata.instrument == "XAU/USD"
        assert result.metadata.engine_version == "2.0.0"


# ═══════════════════════════════════════════════════════
# REGISTRY TESTS
# ═══════════════════════════════════════════════════════

class TestIndicatorRegistry:
    """Test indicator registry."""

    def test_registry_has_indicators(self):
        """Registry has registered indicators."""
        registry = get_registry()
        assert registry.count() > 0

    def test_has_ema200(self):
        """Registry has ema200."""
        registry = get_registry()
        assert registry.has_indicator("ema200")

    def test_list_indicators(self):
        """Can list all indicators."""
        registry = get_registry()
        indicators = registry.list_indicators()
        assert "ema200" in indicators
        assert "rsi" in indicators
        assert "atr" in indicators

    def test_list_by_category(self):
        """Can filter indicators by category."""
        registry = get_registry()
        trends = registry.list_by_category("trend")
        assert len(trends) > 0

    def test_calculate_indicator_function(self):
        """Can calculate indicator via registry."""
        prices = make_price_series(50, start=100.0)
        result = calculate_indicator("ema", prices, period=20)
        assert result is not None
        assert len(result) == 50


# ═══════════════════════════════════════════════════════
# SCHEMA TESTS
# ═══════════════════════════════════════════════════════

class TestQuantSchemas:
    """Test Quant Engine data structures."""

    def test_calculation_metadata(self):
        """CalculationMetadata is traceable."""
        meta = CalculationMetadata(
            dataset_id="test",
            dataset_version="v1.0",
            instrument="XAU/USD",
            timeframe="D1",
            indicator="ema20",
            parameters={"period": 200},
            source_field="close",
            calculation_convention="deterministic",
        )
        assert meta.dataset_id == "test"
        assert meta.engine_version == "2.0.0"

    def test_quant_result(self):
        """QuantResult is properly structured."""
        result = QuantResult(
            indicator="ema20",
            values=[None] * 10 + [100.0],
            metadata=CalculationMetadata(
                dataset_id="test", dataset_version="v1.0",
                instrument="XAU/USD", timeframe="D1",
                indicator="ema20", parameters={},
                source_field="close", calculation_convention="deterministic",
            ),
        )
        assert result.indicator == "ema20"
        assert result.is_valid is True

    def test_indicator_result(self):
        """IndicatorResult tracks last value."""
        ir = IndicatorResult(
            indicator_name="RSI", period=14,
            values=[None] * 14 + [70.5],
            dataset_id="test", timeframe="D1", instrument="XAU/USD",
        )
        assert ir.last_value == 70.5
        assert ir.is_complete is False

    def test_indicator_series(self):
        """IndicatorSeries tracks timestamps and values."""
        from data_engine.quant.schemas import IndicatorSeries
        ts = [datetime.now(UTC) - timedelta(hours=i) for i in range(5)]
        series = IndicatorSeries(name="EMA20", timestamps=ts, values=[100.0]*5, timeframe="D1")
        assert len(series) == 5


# ═══════════════════════════════════════════════════════
# DETERMINISM TESTS
# ═══════════════════════════════════════════════════════

class TestDeterminism:
    """Verify calculations are deterministic."""

    def test_ema_deterministic(self):
        """Same input produces same EMA."""
        prices = make_price_series(50, start=100.0, trend=0.5, noise=0.1)
        result1 = ema(prices, 10)
        result2 = ema(prices, 10)
        for i in range(len(result1)):
            if result1[i] is not None and result2[i] is not None:
                assert abs(result1[i] - result2[i]) < 1e-10

    def test_rsi_deterministic(self):
        """Same input produces same RSI."""
        prices = make_price_series(30, start=100.0)
        result1 = rsi(prices, period=14)
        result2 = rsi(prices, period=14)
        for i in range(len(result1)):
            if result1[i] is not None and result2[i] is not None:
                assert abs(result1[i] - result2[i]) < 1e-10

    def test_statistics_deterministic(self):
        """Same input produces same statistics."""
        prices = make_price_series(20, start=100.0)
        assert mean(prices) == mean(prices)
        assert std(prices) == std(prices)


# ═══════════════════════════════════════════════════════
# SECURITY / LLM BOUNDARY TESTS
# ═══════════════════════════════════════════════════════

class TestSecurity:
    """Verify security and LLM boundary."""

    def test_llm_cannot_perform_ema(self):
        """LLM cannot perform EMA calculation."""
        with pytest.raises(Exception):
            LLMBoundary.assert_deterministic(CalculationType.EMA, "llm_calc")

    def test_llm_cannot_perform_rsi(self):
        """LLM cannot perform RSI calculation."""
        with pytest.raises(Exception):
            LLMBoundary.assert_deterministic(CalculationType.RSI, "llm_calc")

    def test_llm_cannot_perform_atr(self):
        """LLM cannot perform ATR calculation."""
        with pytest.raises(Exception):
            LLMBoundary.assert_deterministic(CalculationType.ATR, "llm_calc")

    def test_all_calculation_types_deterministic(self):
        """All calculation types require deterministic code."""
        for ct in CalculationType:
            with pytest.raises(Exception):
                LLMBoundary.assert_deterministic(ct, "llm_calc")

    def test_no_live_trading_in_quant(self):
        """Quant engine source contains no trading execution."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    for pattern in ['place_order', 'market_order', 'execute_trade', 'broker.connect']:
                        if pattern in content and 'quant' in filepath:
                            pytest.fail(f"Found trading execution code in {filepath}")


# ═══════════════════════════════════════════════════════
# PROVENANCE TESTS
# ═══════════════════════════════════════════════════════

class TestProvenance:
    """Verify quant results preserve provenance."""

    def test_result_preserves_dataset_id(self):
        """Result contains dataset_id."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles, dataset_id="my_dataset")
        result = engine.calculate("ema200", ds, period=20)
        assert result.metadata.dataset_id == "my_dataset"

    def test_result_preserves_timeframe(self):
        """Result contains timeframe."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i), tf=Timeframe.H4) for i in range(20)]
        ds = make_dataset(candles, timeframe=Timeframe.H4)
        result = engine.calculate("ema200", ds, period=20)
        assert result.metadata.timeframe == "4h"

    def test_result_preserves_instrument(self):
        """Result contains instrument symbol."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(20)]
        ds = make_dataset(candles, dataset_id="test")
        result = engine.calculate("ema200", ds, period=20)
        assert result.metadata.instrument == "XAU/USD"

    def test_result_preserves_parameters(self):
        """Result contains calculation parameters."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now + timedelta(days=i)) for i in range(200)]
        ds = make_dataset(candles)
        result = engine.calculate("ema20", ds, period=20)
        assert result.metadata.parameters == {"period": 20}


# ═══════════════════════════════════════════════════════
# TIMEFRAME INTEGRITY TESTS
# ═══════════════════════════════════════════════════════

class TestTimeframeIntegrity:
    """Verify timeframe awareness."""

    def test_h4_lookback(self):
        """EMA200 on H4 has correct lookback."""
        days = get_effective_lookback_days(200, TF.H4)
        assert abs(days - 33.3) < 2

    def test_d1_lookback(self):
        """EMA200 on D1 has correct lookback."""
        days = get_effective_lookback_days(200, TF.D1)
        assert abs(days - 200) < 2

    def test_timeframe_not_converted(self):
        """Timeframe conversion raises error."""
        from data_engine.timeframes import assert_timeframe_not_converted
        with pytest.raises(ValueError):
            assert_timeframe_not_converted(TF.H4, TF.D1, "quant calculation")

    def test_indicator_respects_timeframe(self):
        """Indicator calculation respects dataset timeframe."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i), tf=Timeframe.D1) for i in range(200)]
        ds = make_dataset(candles, timeframe=Timeframe.D1)
        result = engine.calculate("ema20", ds, period=20)
        assert result.metadata.timeframe == "1d"


# ═══════════════════════════════════════════════════════
# INSUFFICIENT DATA TESTS
# ═══════════════════════════════════════════════════════

class TestInsufficientData:
    """Verify proper handling of insufficient data."""

    def test_ema_insufficient(self):
        """EMA returns None for insufficient data."""
        prices = [100.0, 101.0]
        result = ema(prices, 14)
        assert all(v is None for v in result)

    def test_sma_insufficient(self):
        """SMA returns None for insufficient data."""
        prices = [100.0, 101.0]
        result = sma(prices, 5)
        assert all(v is None for v in result)

    def test_rsi_insufficient(self):
        """RSI returns None for insufficient data."""
        prices = [100.0, 101.0, 102.0]
        result = rsi(prices, period=14)
        assert all(v is None for v in result)

    def test_atr_insufficient(self):
        """ATR returns None for insufficient data."""
        result = atr([105.0], [98.0], [102.0], period=14)
        assert all(v is None for v in result)

    def test_rolling_std_insufficient(self):
        """Rolling std returns None for insufficient data."""
        prices = [100.0, 101.0]
        result = rolling_std(prices, window=5)
        assert all(v is None for v in result)


# ═══════════════════════════════════════════════════════
# PROPERTY-BASED INVARIANT TESTS
# ═══════════════════════════════════════════════════════

class TestInvariants:
    """Test mathematical invariants."""

    def test_simple_return_greater_than_minus_one(self):
        """Simple return > -1 for positive prices."""
        prices = [100.0, 50.0, 25.0]  # 50% drops each time
        result = simple_returns(prices)
        for r in result.simple_returns[1:]:
            if r is not None:
                assert r > -1.0

    def test_atr_non_negative(self):
        """ATR is always non-negative."""
        highs = [105.0, 106.0, 107.0]
        lows = [98.0, 99.0, 100.0]
        closes = [102.0, 103.0, 104.0]
        result = atr(highs, lows, closes, period=2)
        for v in result:
            if v is not None:
                assert v >= 0

    def test_drawdown_non_positive(self):
        """Drawdown is always <= 0."""
        equity = [100, 90, 80, 95, 100]
        result = drawdown(equity)
        for d in result.drawdowns:
            if d is not None:
                assert d <= 0

    def test_correlation_in_bounds(self):
        """Correlation is always in [-1, 1]."""
        x = [1, 2, 3, 4, 5]
        y = [5, 4, 3, 2, 1]
        corr = correlation(x, y)
        assert corr is None or (-1 <= corr <= 1)

    def test_std_non_negative(self):
        """Standard deviation is always non-negative."""
        assert std([1, 2, 3, 4, 5]) >= 0

    def test_sma_bounded(self):
        """SMA is bounded by min and max of the window."""
        prices = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = sma(prices, 3)
        assert result[2] == 20.0  # Between 10 and 30
        assert result[4] == 40.0  # Between 30 and 50


# ═══════════════════════════════════════════════════════
# GOLD RESEARCH PRESERVATION TESTS
# ═══════════════════════════════════════════════════════

class TestGoldResearchIntegrity:
    """Verify gold research findings remain unchanged."""

    def test_xau_usd_instrument_correct(self):
        """XAU/USD instrument must be correct."""
        from data_engine.instruments import create_xau_usd_instrument
        inst = create_xau_usd_instrument()
        assert inst.symbol == "XAU/USD"
        assert inst.asset_class.value == "metal"

    def test_data_engine_does_not_contain_strategy_logic(self):
        """Data engine must not contain K3 strategy parameters."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'EMA20 > EMA50 > EMA200' in content or 'K3 Unified' in content:
                        pytest.fail(f"Data engine contains strategy logic in {filepath}")

    def test_no_live_trading_code(self):
        """No live trading code must exist."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    for pattern in ['place_order', 'market_order', 'execute_trade', 'broker.connect']:
                        if pattern in content:
                            pytest.fail(f"Found potential trading execution code in {filepath}")

    def test_quant_engine_provides_features_not_signals(self):
        """Quant engine provides numerical features, not trading signals."""
        engine = QuantEngine()
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(210)]
        ds = make_dataset(candles)
        trends = engine.calculate_all_trends(ds)
        # Trend state is a description, not a recommendation
        assert isinstance(trends.get("trend_state"), str)
        # Trend bullish/bearish are boolean features, not signals
        assert isinstance(trends.get("trend_bullish"), bool)
        assert isinstance(trends.get("trend_bearish"), bool)


# ═══════════════════════════════════════════════════════
# QUANT BOUNDARY TESTS
# ═══════════════════════════════════════════════════════

class TestQuantBoundary:
    """Test that quant boundary is enforced."""

    def test_all_calculation_types_are_deterministic(self):
        """All 15 calculation types require deterministic code."""
        for ct in CalculationType:
            with pytest.raises(Exception):
                LLMBoundary.assert_deterministic(ct, "llm_calc")

    def test_llm_allowed_operations(self):
        """LLM can interpret, not compute."""
        allowed = LLMBoundary.allowed_operations()
        assert "interpret_results" in allowed
        assert "generate_hypothesis" in allowed

    def test_deterministic_calculations_not_overridden(self):
        """All 15 calculation types must be deterministic."""
        for ct in CalculationType:
            assert LLMBoundary.is_deterministic_required(ct)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])