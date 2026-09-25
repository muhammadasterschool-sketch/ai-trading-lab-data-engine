# Phase 3 — Strategy & Backtest Engine

## Overview

The Strategy & Backtest Engine provides a deterministic framework for defining, executing, and evaluating trading strategies against historical data.

```
Validated Dataset
        ↓
Feature Calculation (QuantEngine)
        ↓
Signal Generation (StrategySpec)
        ↓
Order Generation
        ↓
Execution Model (costs + slippage)
        ↓
Position Tracking
        ↓
Trade Ledger
        ↓
Equity Curve
        ↓
Backtest Metrics
        ↓
Provenance
```

**No live trading. No broker integration. Research only.**

## Architecture

### Module Structure

```
src/data_engine/strategy/
    __init__.py          - Package exports, version 3.0.0
    schemas.py           - Immutable strategy specs, EntryCondition, ExitCondition, CostParameters
    execution.py         - Deterministic execution model, transaction costs, slippage
    backtest.py          - BacktestEngine, BacktestConfig, BacktestResult
    metrics.py           - BacktestMetrics (Sharpe, Sortino, win rate, etc.)
    validation.py        - StrategyValidator, LeakageDetector
    provenance.py        - BacktestProvenance, BacktestProvenanceTracker
    ledger.py            - Trade, TradeLedger (immutable)
    position.py          - PositionTracker, PositionState
    equity.py            - EquityTracker, EquityPoint
```

### Data Flow

```
DATA → FEATURES → SIGNAL → ORDER → EXECUTION → POSITION → PNL → METRICS → PROVENANCE
```

Each concept is handled by a distinct component. No collapsing.

## Strategy Specification

### Declarative & Immutable

All strategies are defined declaratively using frozen Pydantic models. No arbitrary Python code can be injected as a strategy.

```python
from data_engine.strategy import StrategySpec, EntryCondition, ExitCondition

strategy = StrategySpec(
    strategy_id="mean_reversion",
    instrument="XAU/USD",
    timeframe="D1",
    entry_conditions=[
        EntryCondition(indicator="rsi", operator="<", threshold=30),
    ],
    exit_conditions=[
        ExitCondition(type="signal", indicator="rsi"),
        ExitCondition(type="take_profit", pct_of_entry=0.05),
    ],
    required_indicators=["rsi"],
    initial_capital=10000.0,
)
```

### Strategy Components

| Component | Description |
|-----------|-------------|
| `StrategySpec` | Complete immutable strategy definition |
| `EntryCondition` | Declarative entry rule (indicator + operator + threshold) |
| `ExitCondition` | Declarative exit rule (stop_loss, take_profit, signal) |
| `PositionSizingParameters` | Fixed, percent, or ATR-based sizing |
| `CostParameters` | Explicit commission and spread |
| `SlippageParameters` | Explicit slippage model |

## Execution Model

### Explicit Costs

All transaction costs are explicit and never assumed to be zero:

```python
cost_params = CostParameters(
    commission_per_share=0.01,  # Explicit
    commission_pct=0.1,          # Explicit
    spread_bps=5.0,              # Explicit
)
```

### Slippage Model

```python
slippage_params = SlippageParameters(
    fixed_slippage=0.5,          # Fixed price slippage
    pct_slippage=0.01,           # Percentage of price
    volatility_aware=False,      # Optional ATR-based scaling
)
```

### Fill Price

- **LONG**: `fill_price = price + slippage`
- **SHORT**: `fill_price = price - slippage`

## Backtest Engine

### Chronological Processing

The `BacktestEngine` processes data chronologically with no look-ahead bias:

1. **For each bar in order**:
   - Calculate features using only current and past data
   - Check entry conditions (using current/past indicators)
   - If entry signal and no position → generate order
   - Execute order with costs and slippage
   - Track position and equity
   - Check exit conditions
   - If exit signal → close position

### No Future-Bar Access

The `LeakageDetector` prevents future data from influencing historical decisions:

```python
detector = LeakageDetector()
# Raises ValueError if signal accesses future bar
detector.check_signal_timing(signal_bar_index=5, current_bar_index=2)
```

### Dataset Immutability

The engine never modifies the underlying dataset. Datasets are frozen Pydantic models.

## Trade Ledger

Every completed trade is recorded immutably:

```python
@dataclass
class Trade:
    trade_id: str
    strategy_id: str
    strategy_version: str
    side: OrderSide  # LONG or SHORT
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: Optional[datetime]
    exit_price: Optional[float]
    quantity: float
    gross_pnl: Optional[float]
    commissions: float
    slippage: float
    net_pnl: Optional[float]
    holding_period_bars: Optional[int]
    exit_reason: Optional[str]
```

All trade records are frozen and immutable.

## Equity Curve Tracking

The `EquityTracker` maintains an immutable equity curve:

```python
@dataclass
class EquityPoint:
    timestamp: datetime
    cash: float
    position_value: float
    total_equity: float
    position: float
    unrealized_pnl: float
    realized_pnl: float
    cumulative_fees: float
    drawdown: float  # Equity / running_peak - 1
    cumulative_return: float
```

The `PositionTracker` tracks position state immutably:

```python
@dataclass  
class PositionTracker:
    side: str  # "LONG", "SHORT", "NONE"
    quantity: float
    entry_price: Optional[float]
    entry_timestamp: Optional[datetime]
    cumulative_pnl: float
```

## Backtest Metrics

### Return Metrics

- `total_return`: Net P&L / Initial Capital
- `cumulative_return`: Total return from initial capital
- `annualized_return`: Annualized return (where valid time period exists)

### Risk Metrics

- `volatility`: Standard deviation of returns
- `sharpe_ratio`: (Return - Risk-Free) / Volatility
- `sortino_ratio`: (Return - Risk-Free) / Downside Deviation
- `max_drawdown`: Maximum peak-to-trough decline
- `max_drawdown_duration`: Longest drawdown duration in bars
- `recovery_duration`: Bars to recover from max drawdown

### Trade Metrics

- `total_trades`: Number of closed trades
- `win_rate`: Winning trades / Total trades
- `loss_rate`: Losing trades / Total trades
- `profit_factor`: Gross Wins / Gross Losses
- `expectancy`: Average Net P&L per trade
- `average_trade`: Total Net P&L / Total Trades
- `median_trade`: Median net P&L
- `average_win`: Average winning trade P&L
- `average_loss`: Average losing trade P&L
- `turnover`: Total traded value / Initial Capital
- `exposure`: Average position as fraction of capital

### Edge Cases

- Zero trades → `has_sufficient_data = False`, `insufficient_data_reason` set
- Zero initial capital → Returns handled gracefully
- No closed trades → Metrics return zero values with appropriate warnings

## Data Leakage Protection

The `LeakageDetector` protects against:

1. **Future-bar leakage**: Signal accesses future bar → `ValueError`
2. **Shifted-feature leakage**: Feature uses future data → detected
3. **Signal/execution timing errors**: Execution before signal → `ValueError`
4. **Dataset mutation**: Dataset modified during backtest → detected
5. **Unordered timestamps**: Timestamps not sorted → detected
6. **Duplicate timestamps**: Duplicate timestamps → detected
7. **NaN/Inf contamination**: NaN or Inf in prices → detected
8. **Invalid OHLC**: Impossible OHLC relationships → detected
9. **Invalid position sizing**: Negative quantity → `ValueError`
10. **Impossible trades**: Invalid trade conditions → detected

## Provenance

Every backtest result contains full provenance metadata:

```python
BacktestProvenance(
    backtest_id="bt_abc123",
    strategy_id="mean_reversion",
    strategy_version="1.0.0",
    strategy_hash="sha256_of_strategy_spec",
    dataset_id="xau_usd_daily",
    dataset_version="v1.0",
    instrument="XAU/USD",
    timeframe="D1",
    initial_capital=10000.0,
    num_candles=100,
    cost_parameters={...},
    slippage_parameters={...},
    engine_version="3.0.0",
    quant_engine_version="2.0.0",
)
```

The `BacktestProvenanceTracker` records all provenance for reproducibility.

## Security

- No `eval`, `exec`, `pickle`, or shell execution
- No arbitrary code execution from strategy specs
- No network calls in calculations
- No unsafe deserialization
- Strategies are purely declarative
- Datasets cannot be mutated by the engine

## Usage Example

```python
from data_engine.strategy import (
    StrategySpec, BacktestEngine, BacktestMetrics,
    EntryCondition, ExitCondition, CostParameters,
)

# Define a strategy
strategy = StrategySpec(
    strategy_id="mean_reversion",
    instrument="XAU/USD",
    timeframe="D1",
    entry_conditions=[
        EntryCondition(indicator="rsi", operator="<", threshold=30),
    ],
    exit_conditions=[
        ExitCondition(type="signal", indicator="rsi"),
    ],
    required_indicators=["rsi"],
    initial_capital=10000.0,
    cost_parameters=CostParameters(commission_pct=0.1),
)

# Run backtest
engine = BacktestEngine()
result = engine.run(strategy, validated_dataset)

# Get metrics
metrics = BacktestMetrics.from_trades(result.trades, initial_capital=10000.0)

# Check provenance
print(f"Backtest ID: {result.backtest_id}")
print(f"Total Return: {metrics.total_return}")
print(f"Sharpe Ratio: {metrics.sharpe_ratio}")
```

## Known Limitations

1. Features are calculated via `QuantEngine` which requires pre-computed indicators
2. Backtest engine uses simple position sizing (fixed quantity)
3. No portfolio rebalancing or multi-asset support
4. No transaction queue or partial fills
5. No market impact model (beyond slippage parameters)
6. Annualized return requires valid time period
7. No machine learning-based signal generation (purely declarative)
8. The engine does NOT establish strategy profitability

## Acceptance Gates

- [x] All 315 tests pass
- [x] Zero deprecation warnings
- [x] Backtests are deterministic
- [x] Dataset cannot be mutated by engine
- [x] Future data cannot influence historical decisions
- [x] Costs are explicit
- [x] Slippage is explicit
- [x] Trade ledger is reproducible
- [x] Equity curve is reproducible
- [x] Metrics are deterministic
- [x] Provenance is recorded
- [x] Security tests pass
- [x] Documentation updated

## Phase 2 Compatibility

The Phase 3 Strategy Engine builds on Phase 2 components:

- `QuantEngine` for feature calculation
- `Dataset` for validated market data
- `DataQualityGate` for data quality enforcement
- `CalculationMetadata` for provenance tracking
- `LLMBoundary` for deterministic calculation boundary
- All 12 Phase 2 quant indicators available

**Phase 3 Complete → PHASE 3 READY**