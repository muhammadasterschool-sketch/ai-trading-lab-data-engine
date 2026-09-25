"""Phase 3 — Strategy & Backtest Engine for the AI Trading Lab Data Engine.

The Strategy Engine provides:
1. Declarative, immutable strategy specifications
2. Deterministic historical backtesting engine
3. Explicit transaction-cost and slippage models
4. Complete trade ledger and equity tracking
5. Comprehensive backtest metrics

Architecture:
    Validated Dataset
        → Feature Calculation (QuantEngine)
        → Signal Generation (StrategySpec)
        → Order Generation
        → Execution Model (costs + slippage)
        → Position Tracking
        → Trade Ledger
        → Equity Curve
        → Backtest Metrics
        → Provenance

No live trading. No broker integration. Research only.
"""

from data_engine.strategy.schemas import (
    StrategySpec, OrderSide, OrderStatus, ExitReason,
    EntryCondition, ExitCondition, PositionSizingParameters,
    CostParameters, SlippageParameters, ExecutionConfig,
)
from data_engine.strategy.execution import ExecutionModel, FillResult
from data_engine.strategy.backtest import BacktestEngine, BacktestConfig, BacktestResult
from data_engine.strategy.metrics import BacktestMetrics, periods_per_year, BREAKEVEN_TOLERANCE
from data_engine.strategy.validation import StrategyValidator, LeakageDetector, ValidationIssue
from data_engine.strategy.provenance import BacktestProvenanceTracker, BacktestProvenance
from data_engine.strategy.ledger import Trade, TradeLedger
from data_engine.strategy.position import PositionTracker, PositionState
from data_engine.strategy.equity import EquityTracker, EquityPoint
from data_engine.strategy.conditions import ConditionEvaluator, SignalGenerator, Condition, Signal

__version__ = "3.0.0"

__all__ = [
    "StrategySpec", "OrderSide", "OrderStatus", "ExitReason",
    "EntryCondition", "ExitCondition", "PositionSizingParameters",
    "CostParameters", "SlippageParameters", "ExecutionConfig",
    "BacktestResult", "BacktestConfig", "BacktestProvenance",
    "ExecutionModel", "FillResult",
    "BacktestEngine", "BacktestMetrics", "periods_per_year", "BREAKEVEN_TOLERANCE",
    "StrategyValidator", "LeakageDetector", "ValidationIssue",
    "BacktestProvenanceTracker", "Trade", "TradeLedger",
    "EquityTracker", "EquityPoint", "PositionTracker", "PositionState",
    "ConditionEvaluator", "SignalGenerator", "Condition", "Signal",
    "__version__",
]
