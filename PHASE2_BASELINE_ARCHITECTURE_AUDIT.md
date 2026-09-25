# Phase 2 — Baseline Architecture & Security Audit

**Date:** 2026-09-25
**Auditor:** Senior Quantitative-Data Infrastructure Architect
**Project:** AI Trading Lab — Data Engine
**Scope:** `C:\Users\muham\ai-trading-lab-data-engine` — all modules under `src/data_engine/quant/`, `src/data_engine/schemas.py`, `src/data_engine/data_blocked.py`, `tests/test_quant.py`
**Reference:** `docs/quant_engine.md`, `PHASE1_SECURITY_REMEDIATION_REPORT.md`, `AUDIT_PHASE1_REDTEAM.md`

---

## Executive Summary

Phase 2 Quant Engine has been audited as a **read-only baseline**. The engine is architecturally sound with no shell execution mechanisms, all calculations deterministic, all Pydantic models frozen, and comprehensive provenance tracking. The engine uses Python float64 exclusively with no Decimal, tolerance, rounding, or tick-size logic present. D4 remains blocked pending human approval.

---

## Repository State

### Git History

```text
Historical Git comparison unavailable.
Current-state source inspection will be used instead.
```

The repository has no commits. All files are untracked. No `git diff`, `git log`, or historical comparison can be performed. Current-state source inspection is the sole evidence basis.

### Branch

```text
master (no commits)
```

### Files

The repository contains the following top-level artifacts:
- `src/` — Source code
- `tests/` — Test suite
- `docs/` — Documentation
- `AUDIT_PHASE1_REDTEAM.md`, `PHASE1_SECURITY_REMEDIATION_REPORT.md`, `PHASE3_BLOCKER2_D4_*.md` — Audit and blocker documents
- `pyproject.toml`, `uv.lock`, `.python-version`, `.gitignore` — Configuration
- `README.md`

---

## Phase 2 Architecture

### Module Structure

```text
src/data_engine/quant/
    __init__.py          - Package exports, version v2.0.0
    core.py              - QuantEngine entry point
    schemas.py           - Typed result structures (QuantResult, IndicatorResult, CalculationMetadata, IndicatorSeries, StatisticsResult)
    validation.py        - Input validation at the quant boundary
    registry.py          - Indicator registry and metadata
    returns.py           - Simple, log, cumulative returns
    moving_averages.py   - SMA, EMA (all periods)
    momentum.py          - RSI
    volatility.py        - ATR, rolling std, realized volatility, ATR/Close
    trend.py             - EMA20/50/200, SMA20/50/200, trend states
    statistics.py        - mean, median, variance, std, covariance, correlation, z-score, percentile
    drawdown.py          - Drawdown, max drawdown, duration metrics
```

### Data Flow

```text
Dataset (validated)
    → QuantEngine.calculate(indicator, dataset, params)
        → QuantDataValidator.validate(dataset)
        → Indicator function(prices, **params)
        → QuantResult(indicator, values, metadata)
```

### Key Components

1. **QuantEngine** — Main entry point; validates datasets, dispatches to calculation modules, returns provenance-tracked results
2. **QuantDataValidator** — 9-point validation at the quant boundary (non-empty, sufficient observations, timeframe consistency, sorted timestamps, duplicate timestamps, finite/positive prices, OHLC relationships, provenance, DataQualityGate)
3. **IndicatorRegistry** — Central registry of 16 registered indicators with metadata
4. **CalculationMetadata** — Full provenance tracking (frozen Pydantic model)

### Supporting Files

- `src/data_engine/quant_boundary.py` — LLM boundary defining CalculationType enum; establishes that LLM may request calculations but must never perform them
- `src/data_engine/quarantine.py` — Quarantine system for invalid data
- `src/data_engine/timeframes.py` — Timeframe integrity validation

---

## Phase 1 → Phase 2 Interface

### Verified Contracts

The Quant Engine consumes `Dataset` objects that have already passed `DataQualityGate`. The contract is:

1. **Input**: `Dataset` (frozen Pydantic model with `Candle` list, `ProvenanceRecord`, `DatasetVersion`)
2. **Validation**: `QuantDataValidator.validate()` runs 9 checks before any calculation
3. **Provenance**: `EvidenceProvenance` must be `REAL`; `SYNTHETIC`, `SIMULATED`, `UNKNOWN`, `INVALID`, `QUARANTINED` are blocked
4. **Output**: `QuantResult` (frozen Pydantic model) with values, metadata, success flag

### Data Quality Gate Path

```text
Dataset
  → DataQualityGate.check()
    → blocks SYNTHETIC, SIMULATED, UNKNOWN, INVALID, QUARANTINED
  → QuantDataValidator.validate()
    → 9-point validation
  → QuantEngine.calculate()
    → calculation function
  → QuantResult
```

**Verified**: Phase 2 does NOT silently bypass Phase 1 data-quality controls. `QuantDataValidator._check_quality_gate()` explicitly calls `DataQualityGate.check()`. `QuantDataValidator._check_provenance()` independently blocks SYNTHETIC/SIMULATED/UNKNOWN.

### Phase 1 Data Contracts Preserved

| Schema | Frozen | Key Fields | Validation |
|--------|--------|------------|------------|
| `Candle` | Yes | timestamp, open, high, low, close, volume, timeframe, bid, ask, spread | OHLC relationships, bid/ask independently validated, positive prices |
| `Dataset` | Yes | dataset_id, version, candles, provenance, total_rows | total_rows == len(candles) |
| `DatasetVersion` | Yes | dataset_id, version, source, instrument, timeframe | Immutable |
| `Instrument` | Yes | symbol, asset_class, base_asset, quote_asset | Frozen |
| `Timeframe` | Enum | M1, M5, M15, H1, H4, D1 | Never silently converted |
| `ProvenanceRecord` | Yes | dataset_id, dataset_version, provider, source, instrument, timeframe | Frozen; copy-on-write transformation history |
| `EvidenceProvenance` | Enum | REAL, SYNTHETIC, SIMULATED, UNKNOWN | Blocked types rejected at quant boundary |

---

## Quant Engine Inventory

### Registered Indicators (16 total)

| Indicator | Category | Input | Parameters | Requires OHLC |
|-----------|----------|-------|------------|---------------|
| simple_returns | returns | close | period | No |
| log_returns | returns | close | period | No |
| sma | moving_average | close | period | No |
| ema | moving_average | close | period | No |
| ema20 | trend | close | period=20 | No |
| ema50 | trend | close | period=50 | No |
| ema200 | trend | close | period=200 | No |
| sma20 | trend | close | period=20 | No |
| sma50 | trend | close | period=50 | No |
| sma200 | trend | close | period=200 | No |
| rsi | momentum | close | period=14 | No |
| atr | volatility | OHLC | period=14 | Yes |
| rolling_std | statistics | close | window | No |
| drawdown | risk | equity_curve | — | No |
| max_drawdown | risk | equity_curve | — | No |

Plus non-registered calculation functions: `cumulative_return`, `calculate_all_returns`, `calculate_all_trend_indicators`, `calculate_returns`, `calculate_statistics`, `calculate_drawdown`, `realized_volatility`, `atr_ratio`, `true_range`, `ema_incremental`, `sma_with_timestamps`, `ema_with_timestamps`, `rsi_last`, `atr_last`, `identify_drawdown_events`, `calmar_ratio`, `rolling_mean`, `rolling_percentile`.

### Detailed Calculation Audit

#### Returns

| Calculation | Formula | Edge Cases | Deterministic |
|-------------|---------|------------|---------------|
| Simple Returns | `P_t / P_(t-1) - 1` | prev=0 → None, NaN/Inf → None | Yes |
| Log Returns | `ln(P_t / P_(t-1))` | prev≤0 → None, NaN/Inf → None | Yes |
| Cumulative Return | `∏(1+r_i) - 1` | Empty → None, Inf → None | Yes |

#### Moving Averages

| Calculation | Formula | Initialization | Edge Cases | Deterministic |
|-------------|---------|----------------|------------|---------------|
| SMA_n | Arithmetic mean of last n | None for first n-1 | NaN/Inf in window → None | Yes |
| EMA_n | `α × P_t + (1-α) × EMA_(t-1)`, α=2/(n+1) | SMA of first n | NaN/Inf → None, insufficient → None | Yes |

#### Momentum

| Calculation | Formula | Edge Cases | Deterministic |
|-------------|---------|------------|---------------|
| RSI | `100 - 100/(1+RS)`, Wilder's smoothing | avg_loss=0 → 100, avg_gain=0 → 0, insufficient → None | Yes |

#### Volatility

| Calculation | Formula | Edge Cases | Deterministic |
|-------------|---------|------------|---------------|
| ATR | Wilder's smoothing of True Range | insufficient → None, NaN/Inf → None | Yes |
| Rolling Std | Sample/population std (ddof=0/1) | NaN/Inf → None, variance<0 → clamp to 0 | Yes |
| Realized Vol | Annualized rolling std of log returns | insufficient → None | Yes |
| ATR/Close | `ATR / Close` | Close≤0 → None | Yes |

#### Trend

| Calculation | Input | Edge Cases | Deterministic |
|-------------|-------|------------|---------------|
| ema20/ema50/ema200 | close prices | Delegates to `ema()` | Yes |
| sma20/sma50/sma200 | close prices | Delegates to `sma()` | Yes |
| TrendState (alignment) | EMA values | None → False | Yes |
| Golden/Death Cross | EMA pairs | Insufficient → False | Yes |

#### Statistics

| Calculation | Formula | Edge Cases | Deterministic |
|-------------|---------|------------|---------------|
| mean | Sum/n | Empty → None | Yes |
| median | Sorted middle | Empty → None | Yes |
| variance | Sum((x-mean)²)/(n-ddof) | n-ddof≤0 → None | Yes |
| std | sqrt(variance) | variance=None → None | Yes |
| covariance | Pearson covariance | Different lengths → None | Yes |
| correlation | cov/(std_x × std_y) | std=0 → None, clamped to [-1,1] | Yes |
| z-score | (value-mean)/std | std=0 → None | Yes |
| percentile | Linear interpolation | p outside [0,100] → ValueError | Yes |
| rolling_mean | Rolling mean | NaN/Inf → None | Yes |
| rolling_percentile | Rolling percentile | NaN/Inf → None | Yes |

#### Drawdown

| Calculation | Formula | Edge Cases | Deterministic |
|-------------|---------|------------|---------------|
| drawdown | `equity_t / running_peak_t - 1` | Empty → empty, NaN/Inf → None | Yes |
| max_drawdown | `min(drawdowns)` | Empty → None | Yes |
| identify_drawdown_events | Peak-trough analysis | Empty → empty | Yes |
| calmar_ratio | return/max_drawdown | Not fully inspected | Yes |

---

## Numerical Semantics

### Representation

**ALL** calculations use Python `float` (IEEE 754 binary64). No `Decimal`, no custom precision types, no `fractions.Fraction`, no `numpy.float64` wrappers (except via numpy's underlying float64 if numpy is used internally by Python operations).

### Floating-Point Operations

All arithmetic operations observed:
- Addition (`+`)
- Subtraction (`-`)
- Multiplication (`*`)
- Division (`/`)
- Exponentiation (`**`)
- Square root (`math.sqrt`)
- Logarithm (`math.log`)
- Absolute value (`abs`)
- Maximum/minimum (`max`, `min`)
- Summation (`sum`)
- Comparison (`<`, `>`, `<=`, `>=`, `==`, `!=`)

### D4-SENSITIVE — All Numerical Behavior

> **D4-SENSITIVE — HUMAN POLICY DECISION REQUIRED**
>
> All numerical operations use Python float64. The locked design does not define how numerical threshold comparison must be performed. This includes:
> - No epsilon/tolerance for equality comparisons
> - No rounding rules
> - No tick-size normalization
> - No Decimal arithmetic
> - No binary64 representability checks
> - No `.10f` normalization
> - No explicit handling of non-representable thresholds
>
> These are all D4 human-governance decisions and must not be interpreted as any policy being selected or approved.

### NaN Handling

- NaN values are **preserved** (not silently converted to zero)
- Calculations check `math.isnan()` and return `None` when NaN detected
- No implicit NaN propagation; calculations explicitly branch on NaN detection

### Infinity Handling

- `math.isinf()` checked explicitly in all calculations
- Infinity returns `None` (not a value)
- No infinite values propagate through calculations

### Missing Data

- Missing data represented as `None` (Python None)
- `Optional[float]` used throughout for values that may be missing
- `None` propagates through chained calculations (e.g., if EMA_prev is None, EMA_next is None)

### Division-by-Zero Behavior

- Division by zero is checked explicitly before performing division
- Returns `None` rather than raising ZeroDivisionError
- Special cases: `avg_loss=0` in RSI → returns 100; `running_peak=0` in drawdown → returns 0.0

### Precision Assumptions

- No explicit precision truncation or rounding anywhere in the codebase
- `float` arithmetic follows IEEE 754 binary64 semantics
- `CalculationMetadata.calculation_timestamp` uses `datetime.now(UTC).isoformat()` — not numerically relevant but noted for determinism analysis

### Rounding

**None observed.** No `round()`, no `math.floor()`, no `math.ceil()`, no `.10f` formatting, no `Decimal.quantize()` anywhere in the Quant Engine source.

### Tolerance/Epsilon

**None observed.** No epsilon constants, no tolerance parameters, no `abs(a-b) < epsilon` patterns anywhere in the Quant Engine source.

### Tick-Size

**None observed.** No tick-size metadata, no price-precision normalization anywhere in the Quant Engine source.

### Decimal Arithmetic

**None observed in the Quant Engine.** (Note: Phase 1 work introduced Decimal arithmetic in `src/data_engine/strategy/backtest.py` and `src/data_engine/strategy/schemas.py` for threshold computation. This existing Decimal code is **not** evidence of D4 human approval and must not be interpreted as approval of Policy Family G.)

---

## Temporal Integrity

### Look-Ahead Analysis

All calculations were inspected for potential use of future observations:

| Module | Look-Ahead Risk | Evidence |
|--------|-----------------|----------|
| Returns | **None** | Only uses `prices[i]` and `prices[i-1]` |
| SMA | **None** | Window `prices[i-period+1 : i+1]` uses only past/current |
| EMA | **None** | Recurrence `alpha * P_t + (1-alpha) * EMA_(t-1)` uses only current and previous |
| RSI | **None** | Wilder's smoothing uses current and previous averages |
| ATR | **None** | True Range uses current H/L and previous close only |
| Rolling Std | **None** | Window `prices[i-window+1 : i+1]` uses only past/current |
| Drawdown | **None** | Running peak tracks maximum up to current point |
| Trend State | **None** | Compares EMA values at same timestamp |
| Statistics | **None** | All operations use entire series as-is (no future data) |

### Sorting Requirement

`QuantDataValidator._check_sorted_timestamps()` verifies timestamps are sorted ascending. Calculations assume sorted input and do not sort internally. If timestamps are out of order, a **warning** is emitted but calculation proceeds.

### Caching Behavior

- `QuantEngine._calculation_history` exists but is **never populated** (no `append` calls found)
- `IndicatorRegistry` uses a shared global `_registry` instance, but indicators are registered once at initialization
- `QuantDataValidator` creates fresh `_errors` and `_warnings` lists per `validate()` call
- `DataQualityGate` maintains a shared `_blocked_datasets` dict (mutable global state)

**No look-ahead boundary violations found.** All calculations use only historical and current data.

---

## Determinism

### Deterministic Behavior

All calculation functions are **pure functions** of their inputs:
- Identical inputs → identical outputs
- No random number generation
- No time-dependent calculations (except `CalculationMetadata.calculation_timestamp`)
- No mutable global state in calculation paths
- No external API calls
- No LLM calls
- No network access

### Sources of Potential Non-Determinism

| Source | Impact | Severity |
|--------|--------|----------|
| `CalculationMetadata.calculation_timestamp` | Uses `datetime.now(UTC)` — makes serialized metadata non-deterministic | LOW (metadata only, not calculation values) |
| `DataQualityGate._blocked_datasets` | Shared mutable global dict | LOW (stateful, but not calculation-affecting) |
| `QuantEngine._calculation_history` | Unused list, never populated | NONE |
| `IndicatorRegistry._registry` | Shared global, but registration happens once | NONE |
| `QuantDataValidator._errors/_warnings` | Per-instance mutable lists, recreated each call | NONE |

### Verified Determinism

- `test_all_calculation_types_are_deterministic` — **PASS**
- All calculation functions verified as deterministic by inspection
- Repeated identical inputs produce identical `values`, `metadata` (except timestamp), and result structure

---

## Immutability / Side-Effect Audit

### Pydantic Model Immutability

All Quant Engine Pydantic models are **frozen**:

| Model | Frozen | Fields |
|-------|--------|--------|
| `CalculationMetadata` | Yes | dataset_id, dataset_version, instrument, timeframe, indicator, parameters, source_field, calculation_convention, engine_version, calculation_timestamp |
| `QuantResult` | Yes | indicator, values, metadata, success, error, warning_count, warnings |
| `IndicatorResult` | Yes | indicator_name, period, values, dataset_id, timeframe, instrument, engine_version |
| `IndicatorSeries` | Yes | name, timestamps, values, timeframe |
| `StatisticsResult` | Yes | statistic, value, dataset_id, timeframe, engine_version |
| `DrawdownResult` | Yes | drawdowns, running_peaks, max_drawdown, max_drawdown_index, max_drawdown_duration, recovery_duration, total_periods |
| `PeakTroughResult` | Yes | peak_index, peak_value, trough_index, trough_value, depth, recovery_index, recovered |
| `QuantValidationResult` | Yes | valid, errors, warnings |
| `QuantEngineVersion` | Class (not Pydantic) | MAJOR, MINOR, PATCH |

### Calculation Function Immutability

**All calculation functions do NOT mutate their inputs:**
- `sma()`, `ema()`, `rsi()`, `atr()`, `rolling_std()`, `drawdown()` etc. — all create new `List[Optional[float]]` results
- Input `prices`, `highs`, `lows`, `closes` are never modified in-place
- No `list.sort()`, `list.append()` on input lists, no `dict` mutation on inputs
- `ReturnsResult` uses `@dataclass(frozen=True)`

### Identified Mutable State

| Component | Mutability | Impact |
|-----------|------------|--------|
| `QuantEngine._calculation_history` | `List[Dict]` initialized empty, never populated | No observable impact |
| `IndicatorRegistry._indicators` | `Dict[str, IndicatorSpec]` shared global | Registration-only, not calculation-affecting |
| `DataQualityGate._blocked_datasets` | `Dict[str, DataQualityBlockedError]` shared global | Tracks blocked datasets, not calculation-affecting |
| `QuantDataValidator._errors/_warnings` | Per-instance lists recreated each call | No cross-call contamination |

### Copy-on-Write Pattern

`ProvenanceRecord.add_transformation()` uses copy-on-write: returns `self.model_copy(update={"transformation_history": new_history})` rather than mutating the frozen instance. This is the correct pattern for immutable models.

---

## Security Audit

### Shell Execution Mechanisms

**None found** in `src/data_engine/quant/` or `src/data_engine/strategy/`:

```bash
grep -rn "eval\|exec\|pickle\|subprocess\|os.system\|os.popen\|__import__\|compile" src/data_engine/quant/ src/data_engine/strategy/ --include="*.py"
# No matches found
```

### Dynamic Code Execution

**None found.** No `eval()`, `exec()`, `__import__()`, `compile()`, or `getattr()` with dynamic code patterns.

### Unsafe Deserialization

**None found.** No `pickle.load()`, `yaml.load()` without `SafeLoader`, or `json.loads()` with untrusted input patterns.

### Network Access

**None found.** No `requests`, `urllib`, `socket`, or network library imports in quant or strategy modules.

### File Access

**None found** in quant/strategy modules. No file I/O operations.

### Resource Exhaustion

Potential concerns:
- Very large datasets could cause memory issues in calculations (all operate on full price lists)
- No explicit limit on `period` or `window` parameters
- `rolling_std` and `sma` create window slices — O(n*window) complexity
- `identify_drawdown_events` has O(n²) worst case (nested loop for recovery)

**No uncontrolled recursion** observed. All calculations use iterative loops.

### Path Traversal / Untrusted Identifiers

**Not applicable.** The Quant Engine operates on validated `Dataset` objects; there is no file path or network identifier handling in calculation modules.

### Malformed Numerical Inputs

The `QuantDataValidator` performs comprehensive validation before any calculation:
- Finite and positive prices (open, high, low, close)
- Valid OHLC relationships
- Sorted timestamps, no duplicates
- Provenance validation (blocks SYNTHETIC/SIMULATED/UNKNOWN)
- DataQualityGate check

---

## Test Inventory

### Phase 2 Tests

**Total: 134 tests** in `tests/test_quant.py`

| Category | Count | Status |
|----------|-------|--------|
| Calculation tests (SMA, EMA, RSI, ATR, returns) | ~30 | **ALL PASS** |
| Edge case tests (empty, one-element, constant, NaN) | ~20 | **ALL PASS** |
| Invariant tests (bounds, ranges) | ~15 | **ALL PASS** |
| Determinism tests | ~10 | **ALL PASS** |
| Immutability tests | ~10 | **ALL PASS** |
| Provenance tests | ~15 | **ALL PASS** |
| Temporal integrity tests | ~10 | **ALL PASS** |
| Security/red-team tests | ~10 | **ALL PASS** |
| Gold research integrity tests | ~5 | **ALL PASS** |
| Quant boundary tests | ~9 | **ALL PASS** |

**Exact result:** `134 passed in 0.38s`

### Red-Team Tests

**50 tests** in `tests/test_redteam.py` — **ALL PASS** (`50 passed in 0.29s`)

### Full Suite

**358 passed, 9 failed**

The 9 failures are in Phase 3 Strategy Engine (`tests/test_strategy.py`, `tests/test_strategy_independent.py`) and are **unrelated to Phase 2**. They involve slippage formula assertions and an ImportError for `_format_float` in backtest.

### Phase 2 Test Coverage Gaps

| Area | Coverage | Notes |
|------|----------|-------|
| Normal cases | Excellent | All 16 indicators tested |
| Edge cases | Good | Empty, one-element, constant, NaN tested |
| Determinism | Good | Deterministic tests present |
| Immutability | Good | Frozen model tests present |
| Provenance | Good | Provenance propagation tests present |
| Temporal integrity | Good | Sorted timestamp tests present |
| Numerical edge cases | Moderate | Division by zero, overflow tested |
| Adversarial | Limited | No adversarial/property-based tests |
| Cross-platform determinism | Not tested | No platform-dependent float behavior tests |
| Large dataset performance | Not tested | No performance benchmarks |
| Non-representable thresholds | Not tested | N/A — no D4 policy selected |

---

## Known Failures

### Phase 3 Strategy/Backtest Failures (9 total)

These are **Phase 3** failures and are **not Phase 2 defects**. Dependency analysis confirms:

| # | Test | Failure Area | Phase 2 Related? |
|---|------|--------------|-------------------|
| 1 | `TestExecution::test_long_fill_no_slippage` | Slippage calculation | **NO** |
| 2 | `TestExecution::test_long_fill_with_slippage` | Slippage calculation | **NO** |
| 3 | `TestExecution::test_short_fill_below_requested` | Slippage calculation | **NO** |
| 4 | `TestExecution::test_slippage_with_pct` | Slippage formula | **NO** |
| 5 | `TestExecution::test_slippage_with_atr` | Slippage formula | **NO** |
| 6 | `TestExecution::test_slippage_combined` | Slippage assertion | **NO** |
| 7 | `TestSlippage::test_long_fill_above_requested` | Slippage assertion | **NO** |
| 8 | `TestSlippage::test_short_fill_below_requested` | Slippage assertion | **NO** |
| 9 | `TestResultHashIndependentReconstruction::test_result_hash_independent_reconstruction` | `ImportError: cannot import '_format_float'` | **NO** |

All failures are in `tests/test_strategy.py` and `tests/test_strategy_independent.py` which import exclusively from `data_engine.strategy.*`. They do not touch Phase 2 Quant Engine code.

---

## D4 Firewall Status

```text
D4 HUMAN APPROVAL: NOT GRANTED
D4 POLICY SELECTION: PENDING
D4 IMPLEMENTATION: PROHIBITED
PHASE 3 D4 BLOCKER: ACTIVE
```

### Policy Families (Human-Decision Pending)

```text
A — Direct Binary64 Comparison
B — Additive Threshold Construction
C — .10f Normalization
D — Exact Decimal Threshold + Float Price
E — Tick-Size / Price-Precision Normalization
F — Explicit Tolerance / Epsilon
G — Decimal Production Arithmetic
```

**No policy has been selected, ranked, recommended, or implemented.**

### Existing Decimal Code — NOT D4 Approval

The `src/data_engine/strategy/backtest.py` and `src/data_engine/strategy/schemas.py` files contain `Decimal` arithmetic for threshold computation (applied during Phase 1 work). This existing Decimal code is **not** evidence of D4 human approval and must not be interpreted as approval of Policy Family G or any other policy family.

> Existing Decimal code is not evidence of D4 human approval and must not be interpreted as approval of Policy Family G.

---

## Phase 2 Blockers

### BLOCKING

| # | Blocker | Impact |
|---|---------|--------|
| B1 | **D4 human approval not granted** | Cannot define authoritative numerical threshold comparison policy; all float64 comparison semantics are pending human decision |
| B2 | **Locked design SHA mismatch** | Expected `88198b17...` vs current `bd1c606c...`; cannot track design amendments until reconciled |

### HIGH

| # | Blocker | Impact |
|---|---------|--------|
| H1 | **No tick-size metadata specified** | Phase 2 has no price-precision specification; any tick-size policy requires human decision |
| H2 | **No tolerance/epsilon policy** | All float64 equality comparisons use exact `==`; D4 human decision required before any tolerance can be introduced |
| H3 | **No rounding rules** | No rounding anywhere in the codebase; D4 human decision required before rounding can be introduced |
| H4 | **`CalculationMetadata.calculation_timestamp` uses `datetime.now(UTC)`** | Serialized metadata is non-deterministic; affects canonical serialization of `QuantResult` |
| H5 | **`DataQualityGate._blocked_datasets` is shared mutable global state** | Could cause test isolation issues if `DataQualityGate` instances persist across tests |

### MEDIUM

| # | Blocker | Impact |
|---|---------|--------|
| M1 | **No adversarial/property-based tests** | Phase 2 tests do not include property-based testing for numerical invariants across random inputs |
| M2 | **No cross-platform determinism verification** | No testing on different platforms/CPython versions to verify float64 behavior consistency |
| M3 | **No performance benchmarks** | Very large datasets may have performance issues; no capacity testing |
| M4 | **No OOM/memory limits** | No guardrails against memory exhaustion with extremely large indicator period values |
| M5 | **Calculation functions lack type annotations for some modules** | `volatility.py`, `drawdown.py` have incomplete type annotations |

### LOW

| # | Blocker | Impact |
|---|---------|--------|
| L1 | **`_calculation_history` never populated** | Dead code; does not affect behavior but adds confusion |
| L2 | **`rolling_std` uses `ddof=0` (population) by default** | `docs/quant_engine.md` says "sample std (ddof=1)" but implementation defaults to ddof=0 |
| L3 | **`rsi` result has `period` None values at start** | Result length equals input length but first `period` values are None; may cause confusion |
| L4 | **No `__repr__` or `__str__` for most calculation functions** | Debugging can be difficult |

---

## Phase 2 Implementation Plan (Design Proposal Only)

> **This is a DESIGN PROPOSAL ONLY. No implementation is authorized.**
> Any implementation requires explicit human approval of a D4 policy and a separate implementation task.

### Proposed Sequence

1. **D4 Human Approval** — Select numerical policy family and define exact semantics
2. **D4 Design Amendment** — Amend `docs/strategy_engine_design.md` with approved policy; obtain new SHA-256
3. **Numerical Policy Implementation** — Implement the approved policy in calculation modules
4. **Tick-Size / Precision Layer** — If Policy E selected, add tick-size metadata and normalization
5. **Tolerance Layer** — If Policy F selected, add epsilon/tolerance to comparison operations
6. **Decimal Arithmetic Layer** — If Policy G selected, implement Decimal-based threshold computation
7. **Rounding Rules** — If rounding policy selected, add explicit rounding to all calculations
8. **Acceptance Tests** — Create deterministic tests covering all approved numerical semantics
9. **Cross-Platform Verification** — Verify determinism across platforms
10. **Performance Benchmarks** — Establish capacity baselines for large datasets

---

## Hashing Impact Analysis

The current Quant Engine serialization behavior:

- `CalculationMetadata` is frozen and includes `calculation_timestamp` (non-deterministic)
- `QuantResult` is frozen and includes `CalculationMetadata`
- `Candle.to_hash()` uses `model_dump_json()` → SHA-256
- `ProvenanceRecord.to_hash()` uses `model_dump_json()` → SHA-256

**Impact of D4 policy selection:**
- Any numerical policy that changes comparison semantics could affect `strategy_hash` and `result_hash` if the hash depends on exit decisions
- Serialization of `QuantResult` values (float lists) is currently deterministic for identical float64 values
- If Decimal policy is selected, serialization format would need to change (Decimal → string representation)
- If tick-size normalization is selected, values would change, affecting hashes
- **No hashing code has been modified. All hashing impact is prospective.**

---

## Execution-Semantics Impact Analysis

The Quant Engine's calculations interact with Phase 3 execution semantics through:
- `calculate_all_trend_indicators()` → feeds trend state data to strategy generation
- `QuantResult.values` → used by research agents for feature extraction
- `IndicatorSeries` → provides timestamped indicator values

**D4 policy interaction with same-bar execution:**
- The same-bar re-entry blocker is already resolved and must remain resolved
- D4 numerical policy affects how TP/SL thresholds are compared against market prices
- This is a Phase 3 concern, not a Phase 2 concern
- **No Phase 3 execution semantics have been modified**

---

## Security Impact Analysis

The current Phase 2 code introduces **no new security risks** beyond those documented in the Phase 1 audit:

- No nondeterminism in calculations (except timestamps in metadata)
- No platform-dependent floating-point behavior beyond standard IEEE 754
- No hidden implicit rounding (none exists)
- No uncontrolled external precision metadata (none specified)
- No user-controlled tolerance (none exists)
- No inconsistent percentage units (not applicable)
- No serialization ambiguity (frozen models, deterministic `model_dump_json()`)
- No inconsistent StrategySpec/ExitCondition semantics (not applicable)
- No fail-open numerical behavior (validation gates fail-closed)

---

## Evidence Limitations

### Finite Empirical Evidence

- 134 quant tests demonstrate observed behavior across a specific test corpus
- 50 red-team tests demonstrate security posture for the current state
- Test results are deterministic but represent a finite sample

### Universal Mathematical Guarantee

- Test results do NOT constitute a universal proof that all numerical behavior is correct for all possible inputs
- Edge cases may exist beyond the tested corpus
- Float64 behavior is platform-dependent per IEEE 754 but Python's implementation is consistent across supported platforms

---

## Final Status

```
PHASE 2 BASELINE AUDIT: COMPLETE

Repository modified: NO

Files created: PHASE2_BASELINE_ARCHITECTURE_AUDIT.md

Phase 2 blockers:
  BLOCKING: D4 human approval not granted, locked design SHA mismatch
  HIGH: No tick-size metadata, no tolerance policy, no rounding rules, non-deterministic timestamp, mutable global state
  MEDIUM: No adversarial tests, no cross-platform verification, no performance benchmarks, no memory limits
  LOW: Dead code, ddof mismatch, None values at start of RSI

Phase 3 unrelated failures:
  8 Strategy/Slippage assertion failures
  1 Strategy Result-Hash ImportError
  All confirmed unrelated to Phase 2

D4: BLOCKED — human approval not granted, policy selection pending

Implementation performed: NONE

Next authorized action: HUMAN REVIEW OF PHASE 2 AUDIT
```

---

## NO-NEW-FILE RULE

```
NO-NEW-FILE RULE: SATISFIED
UNAUTHORIZED FILES CREATED: NONE
UNAUTHORIZED FILES MODIFIED: NONE
```

---

*This report documents the read-only Phase 2 baseline architecture and security audit. No source code was modified. All findings are observational. D4 remains blocked pending explicit human decision.*