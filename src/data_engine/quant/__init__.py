"""Phase 2 — Deterministic Quant Engine for the AI Trading Lab Data Engine.

The Quant Engine provides deterministic mathematical calculations
for validated market data. It sits between the Data Engine and
future research/backtesting components.

Architecture:
    Validated Market Data
        ↓
    Data Quality Gate
        ↓
    Deterministic Quant Engine
        ↓
    Quant Features / Indicators
        ↓
    Future Research Agents
    Future Strategy Engine

Every calculation is:
- Deterministic (identical input → identical output)
- Provenance-tracked
- Timeframe-aware
- NaN/Infinity-safe
- Independent of LLM reasoning

The LLM may request calculations and interpret results,
but must NEVER perform numerical market calculations.
"""

__version__ = "2.0.0"

from data_engine.quant.core import QuantEngine
from data_engine.quant.schemas import (
    QuantResult,
    IndicatorResult,
    CalculationMetadata,
)
from data_engine.quant.validation import QuantDataValidator, QuantBoundaryError
from data_engine.quant.registry import IndicatorRegistry, get_registry

__all__ = [
    "QuantEngine",
    "QuantResult",
    "IndicatorResult",
    "CalculationMetadata",
    "QuantDataValidator",
    "QuantBoundaryError",
    "IndicatorRegistry",
    "get_registry",
    "__version__",
]