"""Indicator registry for the Quant Engine.

Provides a centralized registry of all available indicators
with their metadata, parameter requirements, and calculation functions.
"""

from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass


@dataclass
class IndicatorSpec:
    """Specification for a registered indicator."""
    name: str
    description: str
    function: Callable
    parameters: Dict[str, Any]  # Parameter name -> default value
    requires_prices: bool = True  # Requires close prices
    requires_ohlc: bool = False  # Requires OHLC data
    min_observations: int = 1
    timeframe_aware: bool = True
    category: str = "technical"


class IndicatorRegistry:
    """Registry of all available quant indicators."""

    def __init__(self):
        self._indicators: Dict[str, IndicatorSpec] = {}
        self._register_defaults()

    def _register_defaults(self):
        """Register all built-in indicators."""
        from data_engine.quant.returns import (
            simple_returns, log_returns
        )
        from data_engine.quant.moving_averages import (
            sma, ema
        )
        from data_engine.quant.momentum import rsi
        from data_engine.quant.volatility import (
            atr, rolling_std
        )
        from data_engine.quant.trend import (
            ema20, ema50, ema200, sma20, sma50, sma200
        )
        from data_engine.quant.drawdown import (
            drawdown, max_drawdown
        )

        self.register(IndicatorSpec(
            name="simple_returns",
            description="Simple returns: P_t / P_(t-1) - 1",
            function=simple_returns,
            parameters={"period": 1},
            category="returns",
        ))
        self.register(IndicatorSpec(
            name="log_returns",
            description="Logarithmic returns: ln(P_t / P_(t-1))",
            function=log_returns,
            parameters={"period": 1},
            category="returns",
        ))
        self.register(IndicatorSpec(
            name="sma",
            description="Simple Moving Average",
            function=sma,
            parameters={"period": 20},
            category="moving_average",
        ))
        self.register(IndicatorSpec(
            name="ema",
            description="Exponential Moving Average (α=2/(period+1))",
            function=ema,
            parameters={"period": 20},
            category="moving_average",
        ))
        self.register(IndicatorSpec(
            name="ema20",
            description="EMA with period 20",
            function=ema20,
            parameters={"period": 20},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="ema50",
            description="EMA with period 50",
            function=ema50,
            parameters={"period": 50},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="ema200",
            description="EMA with period 200",
            function=ema200,
            parameters={"period": 200},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="sma20",
            description="SMA with period 20",
            function=sma20,
            parameters={"period": 20},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="sma50",
            description="SMA with period 50",
            function=sma50,
            parameters={"period": 50},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="sma200",
            description="SMA with period 200",
            function=sma200,
            parameters={"period": 200},
            category="trend",
        ))
        self.register(IndicatorSpec(
            name="rsi",
            description="Relative Strength Index (Wilder's smoothing)",
            function=rsi,
            parameters={"period": 14},
            category="momentum",
        ))
        self.register(IndicatorSpec(
            name="atr",
            description="Average True Range (Wilder's smoothing)",
            function=atr,
            parameters={"period": 14},
            requires_ohlc=True,
            category="volatility",
        ))
        self.register(IndicatorSpec(
            name="rolling_std",
            description="Rolling standard deviation",
            function=rolling_std,
            parameters={"window": 20},
            category="statistics",
        ))
        self.register(IndicatorSpec(
            name="drawdown",
            description="Drawdown series from equity curve",
            function=drawdown,
            parameters={},
            category="risk",
        ))
        self.register(IndicatorSpec(
            name="max_drawdown",
            description="Maximum drawdown",
            function=max_drawdown,
            parameters={},
            category="risk",
        ))
        self._register_extended_v150()

    def _register_extended_v150(self):
        """v1.5.0 top-50 pack: 42 additional indicators.

        Registered names are the SINGLE-SERIES accessors; multi-output
        indicators (macd/stochastic/bollinger/adx/supertrend/ichimoku/
        donchian/keltner/vortex) also expose dict-returning parents via
        direct import from their modules. OHLC/volume-needing specs set
        ``requires_ohlc=True`` (same pre-existing convention as atr).
        """
        from data_engine.quant.oscillators import (
            macd_line, stochastic_k, stoch_rsi, cci, williams_r,
            rate_of_change, momentum, trix, ultimate_oscillator,
            awesome_oscillator,
        )
        from data_engine.quant.bands import (
            bollinger_upper, bollinger_lower, keltner_upper,
            donchian_upper, rolling_vwap,
        )
        from data_engine.quant.trend_indicators import (
            adx_value, supertrend_line, parabolic_sar, ichimoku_tenkan,
            aroon_up, wma, hma, dema, tema, zlema, kama,
            linear_regression_slope, r_squared,
        )
        from data_engine.quant.volume_ta import (
            on_balance_volume, money_flow_index, force_index,
            ease_of_movement, chaikin_money_flow, accumulation_distribution,
            chaikin_oscillator, volume_zscore,
        )
        from data_engine.quant.statistics_ext import (
            choppiness_index, vortex_plus, vortex_minus,
            rolling_skewness, rolling_kurtosis, efficiency_ratio,
        )

        price_specs = [
            ("macd", "MACD line (EMA12-EMA26)", macd_line,
             {"fast": 12, "slow": 26, "signal": 9}, "momentum"),
            ("stoch_rsi", "Stochastic RSI (Chande)", stoch_rsi,
             {"rsi_period": 14, "stoch_period": 14, "k_period": 3}, "momentum"),
            ("rate_of_change", "Rate of Change (ROC)", rate_of_change,
             {"period": 12}, "momentum"),
            ("momentum", "Momentum (P_t - P_{t-period})", momentum,
             {"period": 10}, "momentum"),
            ("trix", "TRIX (triple-smoothed ROC)", trix,
             {"period": 15}, "momentum"),
            ("bollinger_upper", "Bollinger upper band", bollinger_upper,
             {"period": 20, "num_std": 2.0}, "volatility"),
            ("bollinger_lower", "Bollinger lower band", bollinger_lower,
             {"period": 20, "num_std": 2.0}, "volatility"),
            ("wma", "Weighted Moving Average", wma,
             {"period": 20}, "moving_average"),
            ("hma", "Hull Moving Average", hma,
             {"period": 16}, "moving_average"),
            ("dema", "Double EMA", dema,
             {"period": 20}, "moving_average"),
            ("tema", "Triple EMA", tema,
             {"period": 20}, "moving_average"),
            ("zlema", "Zero-Lag EMA (Ehlers)", zlema,
             {"period": 20}, "moving_average"),
            ("kama", "Kaufman Adaptive MA", kama,
             {"period": 10, "fast": 2, "slow": 30}, "moving_average"),
            ("linear_regression_slope", "Rolling OLS slope", linear_regression_slope,
             {"period": 20}, "trend"),
            ("r_squared", "Rolling OLS R-squared (trend quality)", r_squared,
             {"period": 20}, "trend"),
            ("rolling_skewness", "Rolling skewness of returns", rolling_skewness,
             {"period": 30}, "statistics"),
            ("rolling_kurtosis", "Rolling kurtosis of returns", rolling_kurtosis,
             {"period": 30}, "statistics"),
            ("efficiency_ratio", "Kaufman Efficiency Ratio (regime)", efficiency_ratio,
             {"period": 10}, "statistics"),
            ("volume_zscore", "Rolling volume z-score (surge)", volume_zscore,
             {"period": 20}, "volume"),
        ]
        ohlc_specs = [
            ("stochastic_k", "Stochastic %K (slow)", stochastic_k,
             {"k_period": 14, "d_period": 3}, "momentum"),
            ("cci", "Commodity Channel Index (Lambert)", cci,
             {"period": 20}, "momentum"),
            ("williams_r", "Williams %R", williams_r,
             {"period": 14}, "momentum"),
            ("ultimate_oscillator", "Ultimate Oscillator (Williams)", ultimate_oscillator,
             {"period1": 7, "period2": 14, "period3": 28}, "momentum"),
            ("awesome_oscillator", "Awesome Oscillator (Williams)", awesome_oscillator,
             {"fast": 5, "slow": 34}, "momentum"),
            ("keltner_upper", "Keltner upper channel", keltner_upper,
             {"period": 20, "atr_mult": 2.0}, "volatility"),
            ("donchian_upper", "Donchian upper channel", donchian_upper,
             {"period": 20}, "volatility"),
            ("rolling_vwap", "Rolling VWAP (typical price, volume)", rolling_vwap,
             {"window": 20}, "volume"),
            ("adx", "ADX trend strength (Wilder)", adx_value,
             {"period": 14}, "trend"),
            ("supertrend", "Supertrend line (ATR bands)", supertrend_line,
             {"period": 10, "multiplier": 3.0}, "trend"),
            ("parabolic_sar", "Parabolic SAR (Wilder)", parabolic_sar,
             {"af_step": 0.02, "af_max": 0.2}, "trend"),
            ("ichimoku_tenkan", "Ichimoku Tenkan-sen", ichimoku_tenkan,
             {"tenkan_period": 9}, "trend"),
            ("aroon_up", "Aroon Up", aroon_up,
             {"period": 25}, "trend"),
            ("on_balance_volume", "On-Balance Volume (needs volumes)", on_balance_volume,
             {}, "volume"),
            ("money_flow_index", "Money Flow Index (needs volumes)", money_flow_index,
             {"period": 14}, "volume"),
            ("force_index", "Force Index (needs volumes)", force_index,
             {"period": 13}, "volume"),
            ("ease_of_movement", "Ease of Movement (needs volumes)", ease_of_movement,
             {"period": 14}, "volume"),
            ("chaikin_money_flow", "Chaikin Money Flow (needs volumes)", chaikin_money_flow,
             {"period": 20}, "volume"),
            ("accumulation_distribution", "A/D line (needs volumes)", accumulation_distribution,
             {}, "volume"),
            ("chaikin_oscillator", "Chaikin Oscillator (needs volumes)", chaikin_oscillator,
             {"fast": 3, "slow": 10}, "volume"),
            ("choppiness_index", "Choppiness Index (regime)", choppiness_index,
             {"period": 14}, "statistics"),
            ("vortex_plus", "Vortex +VI", vortex_plus,
             {"period": 14}, "trend"),
            ("vortex_minus", "Vortex -VI", vortex_minus,
             {"period": 14}, "trend"),
        ]
        for name, desc, fn, params, category in price_specs:
            self.register(IndicatorSpec(
                name=name, description=desc, function=fn,
                parameters=params, category=category,
            ))
        for name, desc, fn, params, category in ohlc_specs:
            self.register(IndicatorSpec(
                name=name, description=desc, function=fn,
                parameters=params, requires_ohlc=True, category=category,
            ))

    def register(self, spec: IndicatorSpec):
        """Register an indicator specification."""
        self._indicators[spec.name] = spec

    def get(self, name: str) -> Optional[IndicatorSpec]:
        """Get an indicator by name."""
        return self._indicators.get(name)

    def list_indicators(self) -> List[str]:
        """List all registered indicator names."""
        return sorted(self._indicators.keys())

    def list_by_category(self, category: str) -> List[str]:
        """List indicators by category."""
        return [
            name for name, spec in self._indicators.items()
            if spec.category == category
        ]

    def has_indicator(self, name: str) -> bool:
        """Check if an indicator is registered."""
        return name in self._indicators

    def count(self) -> int:
        """Return number of registered indicators."""
        return len(self._indicators)


# Global registry instance
_registry: Optional[IndicatorRegistry] = None


def get_registry() -> IndicatorRegistry:
    """Get the global indicator registry."""
    global _registry
    if _registry is None:
        _registry = IndicatorRegistry()
    return _registry


def calculate_indicator(
    name: str,
    prices: List[float],
    **kwargs,
) -> Optional[List[float]]:
    """Calculate a registered indicator by name.

    Convenience function for direct indicator calculation.
    """
    registry = get_registry()
    spec = registry.get(name)
    if spec is None:
        raise ValueError(f"Unknown indicator: {name}")
    return spec.function(prices, **kwargs)