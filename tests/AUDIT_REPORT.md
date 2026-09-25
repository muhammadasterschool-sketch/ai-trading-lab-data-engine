# Phase 3 Strategy Engine — Comprehensive Audit Report

## STEP 1 — FREEZE STATUS
- ✅ No live subagents
- ✅ Corrupted test file preserved as `tests/test_strategy_corrupted_pre_rebuild.py`

## STEP 4 — API RECONCILIATION: DESIGN vs IMPLEMENTATION

### A. Public Models

| Design | Implementation | Status |
|--------|---------------|--------|
| `StrategySpec` (schemas.py) | `StrategySpec` in schemas.py | MATCH |
| `OrderSide` (schemas.py) | `OrderSide` in schemas.py | MATCH |
| `OrderStatus` (schemas.py) | `OrderStatus` in schemas.py | MATCH |
| `ExitReason` (schemas.py) | `ExitReason` in schemas.py | MATCH |
| `EntryCondition` (schemas.py) | `EntryCondition` in schemas.py | MATCH |
| `ExitCondition` (schemas.py) | `ExitCondition` in schemas.py | MATCH |
| `PositionSizingParameters` (schemas.py) | `PositionSizingParameters` in schemas.py | MATCH |
| `CostParameters` (schemas.py) | `CostParameters` in schemas.py | MATCH |
| `SlippageParameters` (schemas.py) | `SlippageParameters` in schemas.py | MATCH |
| `ExecutionConfig` (schemas.py) | `ExecutionConfig` in BOTH schemas.py and execution.py | DUPLICATE |
| `PositionTracker` (position.py) | `PositionTracker` in position.py AND positions.py | STALE COPY |
| `Trade` (ledger.py) | `Trade` in ledger.py AND trades.py | STALE COPY |
| `TradeLedger` (ledger.py) | `TradeLedger` in ledger.py AND trades.py | STALE COPY |
| `EquityPoint` (equity.py) | `EquityPoint` in equity.py AND positions.py | STALE COPY |
| `EquityTracker` (equity.py) | `EquityTracker` in equity.py AND positions.py | STALE COPY |
| `BacktestResult` (backtest.py) | `BacktestResult` in backtest.py | MATCH |
| `BacktestProvenance` (provenance.py) | `BacktestProvenance` in provenance.py | MATCH |
| `BacktestConfig` (backtest.py) | `BacktestConfig` in backtest.py | MATCH |
| `ExecutionModel` (execution.py) | `ExecutionModel` in execution.py | MATCH |
| `FillResult` (execution.py) | `FillResult` in execution.py | MATCH |
| `BacktestMetrics` (metrics.py) | `BacktestMetrics` in metrics.py | MATCH |
| `Condition` (conditions.py) | `Condition` in conditions.py | MATCH |
| `Signal` (conditions.py) | `Signal` in conditions.py | MATCH |

### B. Stale/Corrupt Artifacts

| Artifact | File | Issue |
|----------|------|-------|
| `positions.py` | src/data_engine/strategy/positions.py | DEAD FILE — contains stale PositionTracker, EquityPoint, EquityTracker |
| `trades.py` | src/data_engine/strategy/trades.py | DEAD FILE — contains stale Trade, TradeLedger, TradeSide, TradeStatus |
| `ExecutionResult` | __init__.py + execution.py | NOT IN DESIGN — alias `ExecutionResult = FillResult` |
| `TradeSide` | trades.py | NOT IN DESIGN — stale enum |
| `TradeStatus` | trades.py | NOT IN DESIGN — stale enum |
| `OrderStatus` has PENDING, CANCELLED | schemas.py | Design only lists REJECTED in OrderStatus context |

### C. Critical Implementation Deviations

| # | Area | Design | Implementation | Severity |
|---|------|--------|---------------|----------|
| 1 | **`PositionTracker.open_position()`** | `entry_fill_price` parameter; raises ValueError if side != "NONE" | `entry_price` parameter; broken: `if self.is_open: pass` then `if quantity <= 0:` raises but `raise ValueError("Cannot open...")` is unreachable after `pass` | CRITICAL |
| 2 | **`PositionTracker.close_position()`** | `exit_fill_price` parameter; clears side/quantity/entry fields | `exit_price` parameter; missing `side="NONE"` and `quantity=0.0` update in close | CRITICAL |
| 3 | **`PositionTracker` field name** | `entry_fill_price` | Stale positions.py uses `entry_price` | CRITICAL |
| 4 | **`EquityPoint` field name** | `position_market_value` | Stale positions.py uses `position_value`; equity.py uses `position_market_value` (correct) | HIGH |
| 5 | **`EquityPoint` fields** | Only `timestamp, total_equity, cash, position_market_value` | Stale positions.py adds `position, unrealized_pnl, realized_pnl, cumulative_fees, drawdown, cumulative_return, daily_return` — NOT in design | HIGH |
| 6 | **`backtest.py` imports** | Should import from equity.py/position.py | `from data_engine.strategy.positions import EquityTracker, EquityPoint, PositionTracker` — imports STALE dead file | CRITICAL |
| 7 | **`Trade.close()`** | `exit_fill_price`, `exit_timestamp`, `exit_reason`, `exit_commission` parameters | Stale trades.py `close()` uses `exit_price`, `exit_fill_price=None`, `exit_reason="SIGNAL_EXIT"` | HIGH |
| 8 | **`Trade` fields** | `entry_fill_price`, `exit_fill_price`, `entry_commission`, `exit_commission`, `gross_pnl`, `net_pnl`, `side` (OrderSide) | Stale trades.py adds `strategy_id`, `strategy_version`, `entry_price`, `exit_price`, `commissions`, `trade_return`, `entry_signal_value`, `exit_signal_value`, `status`, `TradeSide`, `TradeStatus` | HIGH |
| 9 | **`net_pnl` formula** | `net_pnl = gross_pnl - entry_commission - exit_commission` (slippage NOT subtracted) | Stale trades.py: `net_pnl = gross_pnl - commissions - slippage` (WRONG — subtracts slippage) | CRITICAL |
| 10 | **`TradeLedger.total_closed()`** | Not in design; `BacktestResult.num_closed_trades` calls it | Exists only in stale trades.py, NOT in ledger.py | HIGH |
| 11 | **`TradeLedger.total_commissions()`** | Sum of entry+exit per trade | Stale trades.py uses `t.commissions` (single field) — ledger.py correctly sums `entry_commission + exit_commission` | MEDIUM |
| 12 | **`_compute_config_hash()`** | Field order: `initial_capital|cost_parameters_serialized|slippage_parameters_serialized|allow_short|execution_semantics|max_position_size|seed|execution_delay` | Uses `spread_bps` (not in design), `signal_at_t_close_execute_at_t_close` hardcoded (not from config), wrong field ordering | HIGH |
| 13 | **`_compute_dataset_hash()`** | Content-based canonical serialization per Section H | Simple `f"{dataset_id}:{len(candles)}:{version}"` — NOT content-based | CRITICAL |
| 14 | **`_simulate()` commission** | Should go through ExecutionModel | `_compute_commission()` uses `self.config.commission_*` directly — bypasses ExecutionModel | HIGH |
| 15 | **`_simulate()` slippage** | Should use `ExecutionModel.calculate_slippage()` then `compute_fill()` | Manual calculation in `_simulate()` — bypasses ExecutionModel | HIGH |
| 16 | **`_simulate()` `PositionTracker`** | Uses `position.fill_price` | Uses `position.entry_price` from stale positions.py | CRITICAL |
| 17 | **`_check_exit_conditions()`** | Uses `position.entry_fill_price` | Uses `position.entry_price` | CRITICAL |
| 18 | **`EquityPoint` construction** | `timestamp, total_equity, cash, position_market_value` only | `_simulate()` creates EquityPoint with `position_value`, `position`, `unrealized_pnl`, `realized_pnl`, `cumulative_fees`, `drawdown`, `cumulative_return`, `daily_return` — but equity.py EquityPoint only has 4 fields | CRITICAL |
| 19 | **`BacktestConfig`** | Design says `BacktestConfig` has `execution_delay`, `cost_parameters`, `slippage_parameters` | BacktestConfig has flat fields (`commission_per_share`, `commission_pct`, `fixed_slippage`, etc.) — no nested `CostParameters`/`SlippageParameters` | HIGH |
| 20 | **`ExecutionConfig` duplication** | Only in schemas.py per design | Exists in BOTH schemas.py and execution.py | MEDIUM |
| 21 | **`_check_exit_conditions()`** | Checks `position.entry_fill_price` | References `position.entry_price` which doesn't exist in position.py's PositionTracker | HIGH |
| 22 | **`open_position()` missing validation** | Raises ValueError if side != "NONE" | Stale positions.py: `if self.is_open: pass` — does NOT raise ValueError | CRITICAL |
| 23 | **`open_position()` missing side clearing** | Sets side to "NONE" on close | Stale positions.py close_position() does NOT set `side="NONE"` or `quantity=0.0` | CRITICAL |

### D. Missing Implementation

| Design Requirement | Status |
|-------------------|--------|
| `ExecutionModel.compute_fill()` | EXISTS but not called by backtest engine |
| `ExecutionModel.execute()`/`execute_order()` | NOT IMPLEMENTED — design says `execute()`/`execute_order()` should exist |
| `BacktestProvenanceTracker.record()` | EXISTS but `run_timestamp` is NOT defined in provenance.py `record()` method signature |
| Anti-lookahead test | NOT IN TEST SUITE |
| Determinism double-run | NOT IN TEST SUITE |
| Canonical dataset hash | NOT IMPLEMENTED correctly |
| `result_hash` stability | NOT VERIFIED |
| State machine enforcement | BROKEN in stale positions.py |
| `ORDER_STATUS.REJECTED` for rejected orders | `_simulate()` uses `continue` — no OrderStatus tracking |
| `TIME_EXPIRED` rejection | `_simulate()` uses `continue` — no rejection recorded |
| `MAX_EXPOSURE_EXCEEDED` rejection | `_simulate()` uses `continue` — no rejection recorded |
| `INSUFFICIENT_CASH` rejection | `_simulate()` uses `continue` — no rejection recorded |

### E. Security Issues

| Issue | Location | Severity |
|-------|----------|----------|
| `positions.py` `open_position()` has broken validation allowing `OPEN→OPEN` | `positions.py:72-75` | CRITICAL |
| `trades.py` `Trade` has `status` property checking `TradeStatus.CLOSED` but `TradeStatus` not properly defined | `trades.py:63-67` | HIGH |
| `_simulate()` uses `continue` for rejections — no rejection record | `backtest.py` | HIGH |
| `_generate_features()` swallows all exceptions | `backtest.py:522-523` | MEDIUM |
| No `eval/exec/lambda` in strategy source | conditions.py OK | PASS |
| No pickle/socket/urllib in strategy module | — | PASS |

## STEP 5 — FINANCIAL CORE AUDIT

### Cash Accounting (LONG)

**Design:**
```
cash_after_entry = cash_before - fill_price × quantity - entry_commission
cash_after_exit = cash_before + fill_price × quantity - exit_commission
```

**Implementation (`_simulate`):**
```python
# Entry:
cash = cash - (fill_price * quantity) - entry_commission  # ✓ CORRECT
# Exit:
cash = cash + (exit_fill * position.quantity) - exit_commission  # ✓ CORRECT
```
**Status: MATCH** — but uses stale `position.quantity` and wrong `position` object.

### Cash Accounting (SHORT)

**Design:**
```
cash_after_entry = cash_before + fill_price × quantity - entry_commission
cash_after_exit = cash_before - fill_price × quantity - exit_commission
```

**Implementation:**
```python
# Entry SHORT:
cash = cash + (fill_price * quantity) - entry_commission  # ✓ CORRECT
# Exit SHORT:
cash = cash - (exit_fill * position.quantity) - exit_commission  # ✓ CORRECT
```
**Status: MATCH**

### Equity Invariant

**Design:** `equity = cash + position_market_value`
**Implementation:** `_compute_equity()` correctly computes `cash + pmv` where LONG pmv = qty×price, SHORT pmv = -(qty×price).
**Status: MATCH** — but `_simulate()` creates EquityPoint with wrong field names and from wrong class.

### Commission Model

**Design:** `commission = commission_per_share × quantity + commission_pct/100 × (fill_price × quantity)`
**Implementation:** `_compute_commission()` matches formula. `ExecutionModel.calculate_commission()` matches formula.
**Status: MATCH** — but `_simulate()` bypasses `ExecutionModel`.

### Slippage Model

**Design:** `slippage_price = fixed_slippage + (pct_slippage/100)*requested_price + atr_multiplier*atr`
**LONG:** `fill = requested + slippage_price`
**SHORT:** `fill = requested - slippage_price`
**Implementation:** `ExecutionModel.calculate_slippage()` matches. `_simulate()` matches manually.
**Status: MATCH** — but bypasses `ExecutionModel`.

### CRITICAL: `_simulate()` creates EquityPoint from wrong class

The `_simulate()` method creates `EquityPoint` with fields like `position_value`, `position`, `unrealized_pnl`, `realized_pnl`, `cumulative_fees`, `drawdown`, `cumulative_return`, `daily_return` — but the `equity.py` `EquityPoint` only has `timestamp, total_equity, cash, position_market_value`. This will cause a Pydantic ValidationError at runtime.

## STEP 6 — COST AUDIT

### Commission flow

**Design path:** `Execution → Position → Trade → Ledger → P&L → Equity → Metrics → Result hash`
**Implementation:** `_simulate()` computes commission directly, stores in Trade, but does NOT go through `ExecutionModel.compute_fill()`. The commission IS captured in Trade and used in net_pnl calculation. However, it bypasses the execution model.
**Status: PARTIAL** — commissions reach all layers but bypass ExecutionModel.

### Slippage flow

**Design:** Slippage embedded in fill price, informational `slippage_cost` NOT subtracted from gross_pnl.
**Implementation:** `_simulate()` computes `slippage = abs(fill_price - requested_price) * quantity` and stores in `trade.slippage`. The `net_pnl = gross_pnl - entry_commission - exit_commission` is correct (slippage not subtracted).
**Status: MATCH** — but manual calculation, bypasses ExecutionModel.

## STEP 7 — STATE MACHINE

**Design:** Only FLAT→OPEN and OPEN→FLAT valid. OPEN→OPEN raises ValueError. FLAT→CLOSE raises ValueError.
**Implementation in position.py:** `open_position()` correctly raises ValueError if `self.side != "NONE"`. `close_position()` raises if not open.
**Implementation in positions.py (STALE):** `open_position()` has `if self.is_open: pass` — does NOT raise. `close_position()` does NOT set `side="NONE"`.
**Status: BROKEN** — backtest.py imports from stale positions.py.

## STEP 8 — EXECUTION DELAY

**Design:** delay=0: signal at t → execution at t close. delay=1: signal at t → execution at t+1 close. TIME_EXPIRED if t+1 doesn't exist.
**Implementation:** `_simulate()` handles delay by computing `exec_bar_idx = i + delay` and checking `if exec_bar_idx >= n: continue`. However, it silently skips (no OrderStatus.REJECTED, no TIME_EXPIRED record).
**Status: PARTIAL** — logic exists but rejection semantics missing.

## STEP 9 — ANTI-LOOKAHEAD

**Design:** Modify data after bar t; decisions at bar t must remain identical.
**Implementation:** `_simulate()` processes chronologically, uses `features[i]` for current bar. However, `_generate_features()` pre-computes all features including future bars. This means the feature computation itself could leak if QuantEngine uses future data.
**Status: UNVERIFIED** — depends on QuantEngine implementation.

## STEP 10 — CANONICAL HASHING

**Design:** Four hash types with exact canonical serialization per Section H.
**Implementation:**
- `StrategySpec.canonical_serialize()` — matches design field ordering ✓
- `BacktestEngine._compute_config_hash()` — WRONG field ordering, includes `spread_bps`
- `BacktestEngine._compute_dataset_hash()` — NOT content-based
- `_compute_result_hash()` — correct structure but uses potentially wrong inputs
**Status: PARTIAL** — strategy_hash is correct; config_hash and dataset_hash are broken.

## STEP 11 — REBUILD PLAN

The current implementation is too corrupted to fix incrementally. A complete rebuild is required:

1. **Remove stale files**: `positions.py`, `trades.py`
2. **Fix `position.py`**: `PositionTracker` uses correct field names (`entry_fill_price`, `exit_fill_price`), proper state machine
3. **Fix `equity.py`**: `EquityPoint` has only design fields; `EquityTracker` uses correct `EquityPoint`
4. **Fix `ledger.py`**: `Trade` uses correct fields; `TradeLedger` has `total_closed()` if needed
5. **Fix `backtest.py`**: Import from correct modules; use `ExecutionModel.compute_fill()`; proper rejection semantics; correct config/dataset hash
6. **Fix `__init__.py`**: Remove `ExecutionResult`, `ExecutionConfig` duplicate; remove stale imports
7. **Fix `execution.py`**: Add `execute()`/`execute_order()` methods; remove `ExecutionResult` alias or keep as intentional
8. **Fix `schemas.py`**: Remove duplicate `ExecutionConfig` or consolidate

## REQUIRED FINAL REPORT

### IMPLEMENTATION STATUS
BLOCKED — Multiple critical failures in state machine, imports, and accounting

### API STATUS
BLOCKED — Stale files (`positions.py`, `trades.py`) shadow correct implementations

### FINANCIAL ACCOUNTING STATUS
BLOCKED — `_simulate()` creates EquityPoint from wrong class with wrong fields

### EXECUTION STATUS
BLOCKED — `execute()`/`execute_order()` not implemented; rejection semantics incomplete

### ANTI-LOOKAHEAD STATUS
UNVERIFIED — Depends on QuantEngine; `_generate_features()` pre-computes all features

### HASHING STATUS
BLOCKED — `_compute_dataset_hash()` and `_compute_config_hash()` do not match design

### DETERMINISM STATUS
BLOCKED — Cannot verify due to broken state machine and wrong imports

### PROVENANCE STATUS
PARTIAL — `BacktestProvenanceTracker.record()` missing `run_timestamp` in signature

### SECURITY STATUS
BLOCKED — Broken state machine allows OPEN→OPEN; `_generate_features()` swallows exceptions

### TEST-INTEGRITY STATUS
BLOCKED — Test file is corrupted; must be rebuilt from design

### FULL-SUITE STATUS
BLOCKED — Cannot run tests due to import errors from stale files and broken classes

### REMAINING BLOCKERS
1. Stale `positions.py` and `trades.py` shadow correct implementations
2. `backtest.py` imports from stale `positions.py`
3. `EquityPoint` construction in `_simulate()` uses wrong class/fields
4. `PositionTracker.open_position()` in stale `positions.py` has broken validation
5. `_compute_dataset_hash()` not content-based
6. `_compute_config_hash()` wrong field ordering
7. `ExecutionModel.execute()`/`execute_order()` not implemented
8. Rejection semantics (`continue` instead of proper rejection)
9. `_check_exit_conditions()` references `position.entry_price` (stale field)
10. `Trade.close()` in stale `trades.py` has wrong parameters
11. `TradeLedger.total_closed()` missing from ledger.py
12. `ExecutionConfig` duplicated in schemas.py and execution.py
13. `ExecutionResult` alias not in design
14. `net_pnl` formula in stale `trades.py` subtracts slippage (wrong)
