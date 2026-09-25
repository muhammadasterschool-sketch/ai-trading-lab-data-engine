"""Core Quant Engine for the AI Trading Lab Data Engine.

The QuantEngine is the main entry point for deterministic calculations.
It validates input data, dispatches to calculation modules, and
returns provenance-tracked results.

Usage:
    from data_engine.quant.core import QuantEngine
    from data_engine.schemas import Dataset

    engine = QuantEngine()
    result = engine.calculate("ema200", dataset, period=200)
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, UTC
from pydantic import BaseModel, Field, ConfigDict
from data_engine.schemas import Dataset, Candle, Timeframe, Instrument
from data_engine.quant.validation import QuantDataValidator, QuantBoundaryError
from data_engine.quant.moving_averages import sma, ema
from data_engine.quant.momentum import rsi
from data_engine.quant.volatility import atr, rolling_std, realized_volatility
from data_engine.quant.trend import (
    ema20, ema50, ema200, sma20, sma50, sma200, TrendState
)
from data_engine.quant.statistics import (
    mean, median, variance, std, covariance, correlation, z_score, percentile
)
from data_engine.quant.drawdown import drawdown, max_drawdown, identify_drawdown_events
from data_engine.quant.registry import IndicatorRegistry, get_registry
from data_engine.quant.schemas import QuantResult, IndicatorResult, CalculationMetadata
from data_engine.quant.returns import calculate_all_returns
import math


class QuantEngine:
    """Deterministic quantitative calculation engine.

    Validates datasets at the quant boundary, then dispatches
    to the appropriate calculation module. Every result is
    provenance-tracked and deterministic.

    The LLM may request calculations through this engine,
    but must NEVER perform calculations directly.
    """

    def __init__(self):
        self.validator = QuantDataValidator()
        self.registry = get_registry()
        self._calculation_history: List[Dict] = []

    def calculate(
        self,
        indicator: str,
        dataset: Dataset,
        **params,
    ) -> QuantResult:
        """Calculate a quant indicator on a validated dataset.

        Args:
            indicator: Name of the indicator (e.g., "ema200", "rsi", "atr").
            dataset: A validated Dataset that passed DataQualityGate.
            **params: Indicator-specific parameters (e.g., period=14).

        Returns:
            QuantResult with calculated values and full provenance.

        Raises:
            QuantBoundaryError: If dataset fails validation.
            ValueError: If indicator is unknown.
        """
        # Validate dataset at quant boundary
        min_obs = params.get("period", params.get("window", 1))
        if not isinstance(min_obs, int):
            min_obs = 1

        validation = self.validator.validate(dataset, min_observations=min_obs)
        if not validation.valid:
            error_msg = "; ".join(validation.errors)
            raise QuantBoundaryError(f"Quant boundary validation failed: {error_msg}")

        # Warn if there are validation warnings
        warnings = validation.warnings

        # Get the calculation function
        spec = self.registry.get(indicator)
        if spec is None:
            raise ValueError(
                f"Unknown indicator: '{indicator}'. "
                f"Available indicators: {', '.join(self.registry.list_indicators())}"
            )

        # Extract the price series and timestamps
        prices = [float(close) for close in [c.close for c in dataset.candles]]
        timestamps = [c.timestamp for c in dataset.candles]

        # Calculate
        try:
            if spec.requires_ohlc:
                highs = [float(c.high) for c in dataset.candles]
                lows = [float(c.low) for c in dataset.candles]
                closes = [float(c.close) for c in dataset.candles]
                values = spec.function(highs, lows, closes, **params)
            else:
                values = spec.function(prices, timestamps=timestamps, **params)
        except Exception as e:
            return QuantResult(
                indicator=indicator,
                values=[None] * len(prices),
                metadata=self._metadata(indicator, dataset, params),
                success=False,
                error=str(e),
                warning_count=len(warnings),
                warnings=warnings,
            )

        # Build result
        result_values = list(values) if values else [None] * len(prices)

        return QuantResult(
            indicator=indicator,
            values=result_values,
            metadata=self._metadata(indicator, dataset, params),
            success=True,
            warning_count=len(warnings),
            warnings=warnings,
        )

    def calculate_multiple(
        self,
        indicators: List[str],
        dataset: Dataset,
        **params,
    ) -> Dict[str, QuantResult]:
        """Calculate multiple indicators at once."""
        results = {}
        for indicator in indicators:
            try:
                results[indicator] = self.calculate(indicator, dataset, **params)
            except QuantBoundaryError as e:
                results[indicator] = QuantResult(
                    indicator=indicator,
                    values=[],
                    metadata=CalculationMetadata(
                        dataset_id=dataset.dataset_id,
                        dataset_version=dataset.version.version,
                        instrument=dataset.provenance.instrument.symbol,
                        timeframe=dataset.provenance.timeframe.value,
                        indicator=indicator,
                        parameters=params,
                        source_field="close",
                        calculation_convention="N/A",
                    ),
                    success=False,
                    error=str(e),
                )
        return results

    def calculate_all_trends(self, dataset: Dataset) -> Dict[str, Any]:
        """Calculate all trend indicators (EMA20, EMA50, EMA200, SMA20, SMA50, SMA200)."""
        from data_engine.quant.trend import calculate_all_trend_indicators
        return calculate_all_trend_indicators(
            closes=[float(c.close) for c in dataset.candles],
            timeframe=dataset.provenance.timeframe,
            instrument=dataset.provenance.instrument.symbol,
            dataset_id=dataset.dataset_id,
        )

    def calculate_returns(self, dataset: Dataset) -> QuantResult:
        """Calculate all return types."""
        prices = [float(c.close) for c in dataset.candles]
        timestamps = [c.timestamp for c in dataset.candles]
        returns_result = calculate_all_returns(prices, timestamps)

        return QuantResult(
            indicator="returns",
            values=returns_result.simple_returns,
            metadata=self._metadata("returns", dataset, {}),
            success=True,
        )

    def calculate_statistics(self, dataset: Dataset) -> Dict[str, float]:
        """Calculate basic statistics on close prices."""
        prices = [float(c.close) for c in dataset.candles]
        return {
            "mean": mean(prices) or 0.0,
            "median": median(prices) or 0.0,
            "std": std(prices) or 0.0,
            "variance": variance(prices) or 0.0,
            "min": min(prices) if prices else 0.0,
            "max": max(prices) if prices else 0.0,
            "count": len(prices),
        }

    def calculate_drawdown(self, equity_curve: List[float]) -> Dict[str, Any]:
        """Calculate drawdown metrics from an equity curve."""
        dd_result = drawdown(equity_curve)
        events = identify_drawdown_events(equity_curve)
        return {
            "drawdowns": dd_result.drawdowns,
            "max_drawdown": dd_result.max_drawdown,
            "max_drawdown_index": dd_result.max_drawdown_index,
            "max_drawdown_duration": dd_result.max_drawdown_duration,
            "recovery_duration": dd_result.recovery_duration,
            "events": events,
        }

    def _metadata(
        self,
        indicator: str,
        dataset: Dataset,
        params: Dict,
    ) -> CalculationMetadata:
        """Build calculation metadata for provenance."""
        return CalculationMetadata(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version.version,
            instrument=dataset.provenance.instrument.symbol,
            timeframe=dataset.provenance.timeframe.value,
            indicator=indicator,
            parameters=params,
            source_field="close",
            calculation_convention="deterministic",
            engine_version="2.0.0",
        )

    def validate_dataset(self, dataset: Dataset) -> bool:
        """Quick validation check for a dataset."""
        try:
            self.validator.assert_valid(dataset)
            return True
        except QuantBoundaryError:
            return False


# Backward compatibility: expose key functions at module level
def ema200(prices: List[float], period: int = 200) -> List[Optional[float]]:
    """Calculate EMA200 - convenience function."""
    return ema(prices, period)


def rsi14(closes: List[float]) -> List[Optional[float]]:
    """Calculate RSI(14) - convenience function."""
    return rsi(closes, period=14)


def atr14(highs: List[float], lows: List[float], closes: List[float]) -> List[Optional[float]]:
    """Calculate ATR(14) - convenience function."""
    return atr(highs, lows, closes, period=14)