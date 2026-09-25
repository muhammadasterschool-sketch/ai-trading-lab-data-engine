"""Indicator registry for the Quant Engine.

Provides a centralized registry of all available indicators
with their metadata, parameter requirements, and calculation functions.
"""

from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
from datetime import datetime


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
            simple_returns, log_returns, cumulative_return, calculate_all_returns
        )
        from data_engine.quant.moving_averages import (
            sma, ema, sma_with_timestamps, ema_with_timestamps
        )
        from data_engine.quant.momentum import rsi
        from data_engine.quant.volatility import (
            atr, rolling_std, realized_volatility, atr_ratio
        )
        from data_engine.quant.trend import (
            ema20, ema50, ema200, sma20, sma50, sma200
        )
        from data_engine.quant.statistics import (
            mean, median, variance, std, covariance, correlation, z_score, percentile
        )
        from data_engine.quant.drawdown import (
            drawdown, max_drawdown, identify_drawdown_events
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