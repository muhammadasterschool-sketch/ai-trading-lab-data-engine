# Phase 2 — Deterministic Quant Engine

## Overview

The Quant Engine provides deterministic mathematical calculations for validated market data. It sits between the Data Quality Gate and future research/strategy agents.

```
Validated Market Data
        ↓
Data Quality Gate
        ↓
Deterministic Quant Engine
        ↓
Quant Features / Indicators
        ↓
Future Research Agents
```

## Architecture

### Module Structure

```
src/data_engine/quant/
    __init__.py          - Package exports, version
    schemas.py           - Typed result structures (QuantResult, IndicatorResult, CalculationMetadata)
    validation.py        - Input validation at the quant boundary
    core.py              - Main QuantEngine entry point
    returns.py           - Simple, log, cumulative returns
    moving_averages.py   - SMA, EMA (all periods)
    momentum.py          - RSI
    volatility.py        - ATR, rolling std, realized volatility, ATR/Close
    trend.py             - EMA20/50/200, SMA20/50/200, trend states
    statistics.py        - mean, median, variance, std, covariance, correlation, z-score, percentile
    drawdown.py          - Drawdown, max drawdown, duration metrics
    registry.py          - Indicator registry and metadata
```

### Data Flow

```
Dataset (validated)
    → QuantEngine.calculate(indicator, dataset, params)
        → QuantValidator.validate(dataset)
        → Indicator function(prices, **params)
        → QuantResult(indicator, values, metadata)
```

## Mathematical Conventions

### Returns

- **Simple Return**: `P_t / P_(t-1) - 1`
- **Log Return**: `ln(P_t / P_(t-1))`
- **Cumulative Return**: `∏(1 + r_i) - 1`

### Moving Averages

- **SMA_n**: Arithmetic mean of last n observations
- **EMA_n**: Exponential Moving Average with α = 2/(n+1)
  - Initialization: SMA of first n observations
  - Formula: `EMA_t = α × P_t + (1-α) × EMA_(t-1)`
  - Insufficient data: returns None

### RSI

- Default period: 14
- Formula: `RSI = 100 - (100 / (1 + RS))`
- `RS = Average Gain / Average Loss` (Wilder's smoothing)
- Insufficient data: returns None

### ATR

- Default period: 14
- True Range: `TR = max(High - Low, abs(High - PrevClose), abs(Low - PrevClose))`
- Smoothing: Wilder's method (`ATR_t = (ATR_(t-1) × (period-1) + TR_t) / period`)
- Initialization: SMA of first `period` TR values

### Volatility

- Rolling standard deviation using sample std (ddof=1)
- Realized volatility: rolling std × sqrt(bars_per_year)
- ATR/Close: `ATR / Close`

### Statistics

- Mean, median, variance, standard deviation (sample, ddof=1)
- Covariance, correlation (Pearson)
- Z-score: `(x - mean) / std`
- Percentile (linear interpolation)

### Drawdown

- `drawdown_t = equity_t / running_peak_t - 1`
- Maximum drawdown: `min(drawdowns)`
- Duration: bars from peak to trough, trough to recovery

## Timeframe Handling

All indicators preserve timeframe metadata. Period parameters are always expressed in bars of the dataset's timeframe, never calendar days.

| Timeframe | Bars/Day | Bars/Year |
|-----------|----------|-----------|
| M1        | 1440     | ~525,600  |
| M5        | 288      | ~105,120  |
| M15       | 96       | ~35,040   |
| H1        | 24       | ~8,760    |
| H4        | 6        | ~2,190    |
| D1        | 1        | ~365      |

## Provenance Propagation

Every `QuantResult` includes full provenance metadata:

```python
CalculationMetadata(
    dataset_id="...",
    dataset_version="...",
    instrument="XAU/USD",
    timeframe="H4",
    indicator="EMA",
    parameters={"period": 200},
    source_field="close",
    calculation_convention="deterministic",
    engine_version="2.0.0"
)
```

## NaN / Infinity Policy

- NaN values are preserved (not silently converted to zero)
- Insufficient data returns None (Python None, not NaN)
- Zero denominators return None
- No silent forward-filling unless explicitly requested
- Empty datasets raise `QuantError`

## Security

- No LLM calls in any calculation
- No network calls
- No external API calls
- No arbitrary code execution
- No random numbers
- No time-dependent calculations (except timestamps)
- No mutable global state
- All calculations are pure functions

## Input Validation

Before any calculation, the following are validated:

1. Dataset is non-empty
2. Timestamps are sorted ascending, no duplicates
3. All prices are finite and positive
4. OHLC relationships are valid (High >= max(Open, Close), Low <= min(Open, Close))
5. Timeframe is consistent across the dataset
6. Sufficient observations for the requested indicator
7. Provenance is valid and not blocked

## API Usage

```python
from data_engine.quant import QuantEngine
from data_engine.quant.schemas import CalculationMetadata, Dataset

engine = QuantEngine()

# Calculate EMA
result = engine.calculate("ema", dataset, period=20)
print(result.values)       # List[Optional[float]]
print(result.metadata)     # CalculationMetadata
print(result.success)      # bool

# Calculate RSI
result = engine.calculate("rsi", dataset, period=14)

# Calculate ATR
result = engine.calculate("atr", dataset, period=14)

# Calculate returns
result = engine.calculate("returns", dataset)
```

## Known Limitations

1. All calculations use Python float64 (limited precision)
2. Very large datasets may have performance issues
3. No GPU acceleration
4. No parallel computation
5. Indicator results are not cached across sessions
6. Historical data must be pre-validated through the Data Quality Gate

## Version

- Engine version: 2.0.0
- Python: >= 3.10
- Dependencies: numpy, pandas (optional), pydantic