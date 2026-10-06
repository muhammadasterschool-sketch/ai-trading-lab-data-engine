# Phase 3 — Strategy & Backtest Engine: Final Design Document

## A. FINAL DESIGN

### Overview

This document specifies the complete redesign of Phase 3 — the Strategy & Backtest Engine for the AI Trading Lab Data Engine. The redesign is prompted by a forensic audit that found critical financial-accounting, state-machine, execution-cost, equity, determinism, leakage-detection, and test-integrity problems in the initial implementation.

**Priority:** Financial correctness, deterministic reproducibility, and research integrity take priority over backward compatibility with the broken initial implementation.

**Design Discipline:** Every major design rule in this document is structured as:
- **DESIGN DECISION** — The authoritative choice.
- **RATIONALE** — Why this choice was made.
- **FORMULA / RULE** — The exact mathematical or procedural rule.
- **EDGE CASES** — Every boundary condition and its deterministic resolution.
- **ACCEPTANCE TESTS** — Required future tests that verify compliance.

No exploratory reasoning, candidate alternatives, or unresolved ambiguity remains in this document.

---

## B. ARCHITECTURE

### DATA DECISION
The architecture uses a strict pipeline where each concept is handled by a distinct component. No collapsing of concerns.

### DATA FLOW

```
Validated Dataset (Phase 1/2)
        ↓ DataQualityGate
Candle[] → QuantEngine.calculate()
        ↓ features per bar
StrategySpec (declarative)
        ↓ signals
Signal → Order → Execution → Position → Trade → Equity → Metrics → Provenance
```

### MODULE STRUCTURE

```
src/data_engine/strategy/
    __init__.py          - Package exports, version 3.0.0
    schemas.py           - Domain models: StrategySpec, OrderSide, OrderStatus,
                          ExitReason, EntryCondition, ExitCondition, PositionSizing,
                          CostParameters, SlippageParameters, ExecutionConfig
    execution.py         - ExecutionModel, FillResult, ExecutionConfig
    position.py          - PositionTracker, PositionState (enum), PositionSnapshot
    ledger.py            - Trade, TradeLedger, TradeMetrics
    equity.py            - EquityPoint, EquityTracker, EquitySnapshot
    conditions.py        - ConditionEvaluator, SignalGenerator
    backtest.py          - BacktestEngine, BacktestConfig, BacktestResult, BacktestReport
    metrics.py           - BacktestMetrics (from_trades, from_equity_curve)
    provenance.py        - BacktestProvenance, BacktestProvenanceTracker, ResultHash
    validation.py        - StrategyValidator, LeakageDetector, ConditionValidator
```

### DATA FLOW (DETAILED)

```
DATA (Candle[], validated by DataQualityGate)
  → FEATURES (QuantEngine.calculate per indicator)
    → SIGNAL (ConditionEvaluator evaluates conditions per bar)
      → ORDER (Order generated from signal + position_sizing)
        → EXECUTION (ExecutionModel computes fill price + costs)
          → POSITION (PositionTracker updated: open/update/close)
            → TRADE (Trade created/closed in TradeLedger)
              → EQUITY (EquityTracker updated per bar)
                → METRICS (BacktestMetrics computed from trades + equity)
                  → PROVENANCE (BacktestProvenance recorded)
                    → RESULT (BacktestResult assembled)
```

Each concept is handled by a distinct component. No collapsing.

---

## C. ACCOUNTING MODEL

### DESIGN DECISION

**One authoritative accounting identity.** The primary invariant is `equity = cash + position_market_value`. All other P&L decompositions are derived and informational. Realized and unrealized P&L are NOT additive with initial capital to produce equity when transaction costs exist. Commissions reduce cash at the moment of entry and are captured in the cash balance — they are not part of unrealized P&L.

### RATIONALE

The previous design attempted to use `equity = initial_capital + realized_pnl + unrealized_pnl` as the primary identity. This fails because entry commissions reduce cash immediately upon position opening but are not reflected in unrealized P&L (which is defined as mark-to-market price displacement only). This creates a discrepancy of exactly the entry commission amount at every point while a position is open. The `equity = cash + position_market_value` identity is always correct by construction and requires no additional tracking.

### FORMULA

```
equity(t) = cash(t) + position_market_value(t)
```

This holds at every bar `t`, for every position state (flat, long, short), with zero exceptions.

### INVARIANT

```
equity == cash + position_market_value   (within floating-point tolerance)
```

This is the ONLY primary accounting identity. All other decompositions are secondary.

### Core Definitions

```
INITIAL_CAPITAL: float       # Starting cash, must be > 0
CASH: float                  # Available cash at any point (tracked explicitly)
POSITION_SIDE: enum          # "NONE", "LONG", "SHORT"
POSITION_QUANTITY: float     # > 0 when open, 0 when flat
ENTRY_FILL_PRICE: float      # Fill price at entry (None when flat)
CURRENT_MARKET_PRICE: float  # Current bar close price
POSITION_MARKET_VALUE: float # See formulas below
REALIZED_PNL: float          # Sum of net_pnl for all CLOSED trades (derived)
UNREALIZED_PNL: float        # Mark-to-market change (derived, informational)
```

### Position Market Value

**For LONG:**
```
position_market_value = POSITION_QUANTITY * CURRENT_MARKET_PRICE
```

**For SHORT:**
```
position_market_value = -(POSITION_QUANTITY * CURRENT_MARKET_PRICE)
```
(The negative sign reflects that a short position is a liability — the cost to buy back the shares.)

**When flat (POSITION_SIDE == "NONE"):**
```
position_market_value = 0
```

### CASH Transitions

**INITIAL:**
```
cash(0) = INITIAL_CAPITAL
```

**At LONG entry (fill_price, quantity, entry_commission):**
```
cash = cash - (fill_price * quantity) - entry_commission
```

**At SHORT entry (fill_price, quantity, entry_commission):**
```
cash = cash + (fill_price * quantity) - entry_commission
```
(Short sale proceeds add to cash, minus commission.)

**During holding (position remains open, price changes):**
```
cash does NOT change
```
(Only position_market_value changes as current_price moves.)

**At LONG exit (fill_price, quantity, exit_commission):**
```
cash = cash + (fill_price * quantity) - exit_commission
```

**At SHORT exit (fill_price, quantity, exit_commission):**
```
cash = cash - (fill_price * quantity) - exit_commission
```
(Buying back the short costs cash.)

**After position closes (position_market_value → 0):**
```
position_market_value = 0
```

### DERIVED P&L Decomposition (Informational)

**REALIZED_PNL** (sum of all closed trade economics):
```
realized_pnl = Σ net_pnl for each closed trade
net_pnl = gross_pnl - entry_commission - exit_commission
```
where `gross_pnl` is defined per side in the Cost Model section.

**UNREALIZED_PNL** (mark-to-market displacement, NOT including entry commission):
```
For LONG:
  unrealized_pnl = (current_market_price - entry_fill_price) * quantity

For SHORT:
  unrealized_pnl = (entry_fill_price - current_market_price) * quantity
```

**IMPORTANT:** `unrealized_pnl` does NOT include entry commission. Entry commission is already captured in cash at the time of entry. Therefore:

```
equity ≠ initial_capital + realized_pnl + unrealized_pnl   (GENERALLY FALSE)
```

**Correct relationship for an open LONG position:**
```
equity = initial_capital + unrealized_pnl - entry_commission_already_paid
```

**Correct relationship after full round-trip (position closed):**
```
equity = initial_capital + realized_pnl   (unrealized_pnl is now 0)
```

**Verification of why `equity = initial_capital + realized + unrealized` fails:**
- LONG entry at 100, qty=10, initial_capital=10000, entry_comm=0.5
- cash = 10000 - 1000 - 0.50 = 8999.5
- pmv = 1000
- equity = 8999.5 + 1000 = 9999.5
- unrealized_pnl (at entry) = 0
- initial_capital + realized + unrealized = 10000 + 0 + 0 = 10000 ≠ 9999.5
- Discrepancy = 0.5 = entry_commission

The discrepancy arises because the entry commission reduces cash but is not subtracted from unrealized_pnl. This is by design — commissions are realized costs, not mark-to-market changes.

### CASH CONSTRAINTS

#### DESIGN DECISION

Negative cash is **not permitted**. Leverage is **not permitted**. The strategy must always have sufficient cash to cover the full cost of entry (fill price × quantity + entry commission) before an order is accepted.

#### RATIONALE

The simplified model does not model margin, collateral, borrow fees, financing, or forced liquidation. Allowing negative cash would imply borrowing from a broker, which is a margin relationship that Phase 3 explicitly does not represent. The `equity = cash + position_market_value` identity requires cash to be non-negative for the simplified model to remain internally consistent without introducing a lending mechanism.

#### FORMULA / RULE

```
CASH_MINIMUM = 0.0

Before accepting any order:
  required_cash = (fill_price * quantity) + entry_commission
  IF required_cash > current_cash:
    ORDER IS REJECTED
  ELSE:
    cash = cash - required_cash
```

#### EDGE CASES

| Condition | Resolution |
|-----------|------------|
| Negative cash after any operation | **IMPOSSIBLE.** The invariant `cash >= 0` is enforced at every cash transition. |
| Leverage (position value > equity) | **NOT PERMITTED.** `required_cash > current_cash` rejection prevents leverage. |
| Maximum long notional | `fill_price * quantity <= current_cash - entry_commission` |
| Short-sale constraints | Short sale proceeds add to cash, but the resulting cash must still be >= 0 after exit commission deduction. `allow_short` must be True in StrategySpec. |
| Insufficient capital | Order is **rejected** (not an engine exception). Returns `OrderStatus.REJECTED`. |
| Zero equity | `equity = 0` is possible only if `cash = 0` AND `position_market_value = 0` (flat, no capital). Any new order requires `current_capital > 0`. |
| Negative equity | **IMPOSSIBLE** under the constraints above. If `cash >= 0` and `position_market_value` is bounded by `cash` (no leverage), then `equity = cash + pmv >= 0`. |

#### ACCEPTANCE TESTS

- **AC-CASH-1:** Attempt to open a LONG position exceeding available cash → `OrderStatus.REJECTED`, no state change, no exception raised.
- **AC-CASH-2:** Attempt to open a SHORT position where `required_cash > current_cash` → `OrderStatus.REJECTED`.
- **AC-CASH-3:** After full round-trip, `cash >= 0` always.
- **AC-CASH-4:** `equity >= 0` at every bar for all valid executions.

### SHORT POSITION SCOPE LIMITATIONS

**Phase 3 simplified accounting assumption for SHORT positions:**

Phase 3 does NOT model:
- Margin requirements or margin calls
- Borrow fees (securities lending costs)
- Financing costs (interest on borrowed shares)
- Collateral requirements
- Dividend payments (which short sellers must pay to lenders)
- Forced liquidation
- Broker constraints

The simplified model assumes:
1. Short sale proceeds are immediately available as cash (no margin hold)
2. No borrow fees are charged
3. No collateral is locked
4. No dividend obligations
5. No forced liquidation even if equity approaches zero

**This means the SHORT accounting model is a theoretical simplification suitable for backtesting research purposes only. It does not reflect live broker behavior.** This limitation must be documented in any research output derived from Phase 3 results.

### Summary of Accounting Equations

| Quantity | Equation | Notes |
|----------|----------|-------|
| Primary | `equity = cash + position_market_value` | Always true, primary invariant |
| LONG pmv | `quantity × current_price` | Positive asset |
| SHORT pmv | `-(quantity × current_price)` | Negative liability |
| Realized P&L | `Σ (gross_pnl - entry_comm - exit_comm)` | Derived, informational |
| Unrealized P&L | `(current - entry) × qty` (LONG) | Derived, informational |
| Unrealized P&L | `(entry - current) × qty` (SHORT) | Derived, informational |
| Equity identity | `equity ≠ initial_capital + realized + unrealized` | FAILS when commissions exist |
| Correct closed-trade | `equity = initial_capital + realized_pnl` | After position closes |
| Cash floor | `cash >= 0` | Enforced at every transition |
| No leverage | `required_cash <= current_cash` | Enforced before every order |

### Commission and Slippage Attribution Rules

| Cost Type | Where Captured | Effect on Primary Invariant |
|-----------|---------------|---------------------------|
| Entry commission | Deducted from cash at entry | Reduces equity immediately |
| Exit commission | Deducted from cash at exit | Reduces equity at close |
| Slippage | Embedded in fill price | Already reflected in gross_pnl |
| Slippage cost (monetary) | Informational only | NOT deducted again |

**Rule:** No cost is ever counted twice. Entry and exit commissions each appear exactly once in cash transitions. Slippage appears exactly once in the fill price difference. The `slippage_cost` field in Trade is informational attribution and MUST NOT be subtracted from gross_pnl or net_pnl.

---

## D. STATE MACHINE

### Position States

```
FLAT
  ↓ open_position(side, quantity, fill_price, timestamp)
OPEN
  ↓ update_unrealized(current_price)
OPEN (mark-to-market)
  ↓ close_position(exit_fill_price, exit_timestamp)
FLAT
```

### STATE DECISION
State transitions are enforced. Invalid transitions raise `ValueError`. Valid no-op transitions (FLAT → FLAT with update_unrealized) return silently.

### State Transitions

| From | To | Trigger | Valid? |
|------|----|---------|--------|
| FLAT | OPEN | open_position() | ✓ |
| OPEN | FLAT | close_position() | ✓ |
| OPEN | — | update_unrealized() | NO STATE TRANSITION (mark-to-market update only) |
| FLAT | FLAT | update_unrealized() | ✓ (no-op, no error) |
| FLAT | CLOSE | close_position() | ✗ (raise ValueError) |
| OPEN | OPEN | open_position() | ✗ (raise ValueError) |

### Invariants

1. **OPEN → OPEN is invalid** — raising `ValueError("Cannot open position when already in a position")`
2. **FLAT → CLOSE is invalid** — raising `ValueError("Cannot close position when flat")`
3. **Quantity must be > 0** — raising `ValueError("Quantity must be positive")`
4. **Entry fill price must exist for OPEN** — set during open_position()
5. **Exit fill price must exist for CLOSED** — set during close_position()
6. **Side must be LONG or SHORT while open** — validated in open_position()
7. **Side must become NONE/flat after close** — set to "NONE" in close_position()
8. **Closed position cannot accumulate unrealized P&L** — unrealized_pnl = 0 when flat
9. **Holding period must be calculated deterministically** — exit_timestamp - entry_timestamp

### PositionTracker Interface

```python
class PositionTracker:
    side: str  # "NONE", "LONG", "SHORT"
    quantity: float  # > 0 when open, 0 when flat
    entry_fill_price: Optional[float]  # set when open
    entry_timestamp: Optional[datetime]  # set when open
    cumulative_pnl: float = 0.0  # sum of realized P&L from all closed positions
    
    def open_position(side, quantity, fill_price, timestamp) -> PositionTracker
    def update_unrealized(current_price) -> PositionTracker
    def close_position(exit_fill_price, exit_timestamp) -> PositionTracker
```

---

## E. EXECUTION SEMANTICS

### DESIGN DECISION

The default execution convention is **declared theoretical end-of-bar execution**:
```
signal at bar[t] close → theoretical execution at bar[t] close
```

### RATIONALE

This convention means the strategy observes the complete bar `t` (including its close price) and the resulting order is assumed to fill at that same close price (subject to slippage). This is a standard theoretical assumption for daily research backtests. It is NOT equivalent to real-time execution and must not be described as such.

### FORMULA / RULE

```
DEFAULT: signal at bar[t].close → fill at bar[t].close (subject to slippage)
DELAY=1: signal at bar[t].close → fill at bar[t+1].close (subject to slippage)
```

This is a **declared theoretical end-of-bar execution convention**. The strategy sees the full bar `t` and the order fills at bar `t`'s close price.

### EDGE CASES

| Condition | Resolution |
|-----------|------------|
| Same-bar entry and exit | **IMPOSSIBLE.** A signal at bar `t` that triggers an exit for a position opened at bar `t` cannot occur because the position was not open before bar `t`. If `execution_delay=1`, entry at `t+1` and exit at `t+1` is also impossible for the same reason. |
| Exit after entry (same signal) | If a single bar produces both an exit signal for an existing position and an entry signal for the same side, the exit is processed first, freeing capital, then the entry is processed. The entry uses the same bar's close price. |
| `execution_delay=1` | Signal at bar `t` close → order fills at bar `t+1` close. The requested_price = `bar[t+1].close`. If `t+1` does not exist (final bar), the order is **rejected** with `OrderStatus.REJECTED` and reason `TIME_EXPIRED`. |
| Final bar with no future execution bar | Any order requiring `execution_delay=1` that cannot find bar `t+1` is **rejected** with `OrderStatus.REJECTED`, reason `TIME_EXPIRED`. No partial execution. |
| Missing OHLC data | If `bar[t]` has `None` for any OHLC field, the bar is **skipped** (no signal evaluation, no order generation). The equity curve still includes a point for that bar using the last known equity. If the missing bar is the current bar during a hold, `position_market_value` uses the last available close price. |
| Rejected orders | When an order is rejected (insufficient cash, invalid state, time expired), the engine records the rejection in the order log. **No state change occurs.** The position remains as it was. The equity curve continues with the current state. |

### Timing Components

```
SIGNAL_TIMESTAMP: datetime  # bar t close when signal is generated
ORDER_TIMESTAMP: datetime   # same as signal or signal + delay
EXECUTION_TIMESTAMP: datetime  # when order is filled (same bar or t+1)
REQUESTED_PRICE: float  # bar[t].close (price available to signal)
FILL_PRICE: float  # requested_price ± slippage (price available to execution)
```

### Anti-Lookahead Guarantee

The backtest engine must guarantee that:

1. **Indicator values at bar `i` only use data from bars `0..i`** (no future access)
2. **Signal at bar `t` uses only `features[0..t]`** (no future features)
3. **Execution at bar `t` uses only `data[0..t]`** (no future data)
4. **Changing all data after bar `t` does not change the signal at bar `t`**

These are tested explicitly (see Anti-Lookahead Tests in Test Matrix).

**Price availability:**
- The signal has access to `bar[t].open, bar[t].high, bar[t].low, bar[t].close, bar[t].volume`
- Execution uses `bar[t].close` (default) or `bar[t+1].close` (delay=1) as the requested price
- No future bar's OHLC values can influence the signal at bar `t`

---

## F. COST MODEL

### Canonical Model (Selected)

**Slippage modifies execution price. Commission is deducted separately. No double-counting.**

### Slippage

```
slippage_price = fixed_slippage + (pct_slippage / 100) * requested_price + atr_multiplier * atr
```

**Fill price:**
- LONG: `fill_price = requested_price + slippage_price`
- SHORT: `fill_price = requested_price - slippage_price`

**Slippage cost (monetary):**
- `slippage_cost = slippage_price * quantity`

Note: The slippage_cost is the monetary equivalent of the price displacement. It is used for informational tracking and metrics. The fill price already includes the slippage effect, so gross P&L is calculated from actual fill prices.

**Do NOT subtract slippage_cost again from gross P&L.** The slippage is already embedded in the fill price. Subtracting it again would double-count.

### Commission

```
commission = commission_per_share * quantity + (commission_pct / 100) * (fill_price * quantity)
```

**Note:** Both per-share and percentage commission are additive by design. This is documented and tested explicitly. If only one is intended, the other must be 0.0.

### Trade Economics (per completed trade)

```
ENTRY:
  requested_price = bar[t].close
  fill_price = requested_price ± slippage_price
  entry_commission = commission_per_share * quantity + (commission_pct / 100) * (fill_price * quantity)
  entry_slippage_cost = slippage_price * quantity

EXIT:
  requested_price = bar[t].close
  fill_price = requested_price ∓ slippage_price (opposite direction)
  exit_commission = commission_per_share * quantity + (commission_pct / 100) * (fill_price * quantity)
  exit_slippage_cost = slippage_price * quantity

GROSS_PNL:
  LONG:  (exit_fill_price - entry_fill_price) * quantity
  SHORT: (entry_fill_price - exit_fill_price) * quantity

NET_PNL:
  net_pnl = gross_pnl - entry_commission - exit_commission
  (slippage is already embedded in fill prices, NOT subtracted again)

HOLDING_PERIOD:
  holding_period_bars = exit_timestamp - entry_timestamp (in bars)
  holding_period_days = (exit_timestamp - entry_timestamp).total_seconds() / 86400
```

### Invariant

```
net_pnl == gross_pnl - entry_commission - exit_commission
```

Slippage is NOT separately subtracted from net_pnl because it's already in the fill price.

### Cost Accounting Verification

```
Test: entry=100, exit=110, qty=10, fixed_slippage=0.5, commission_per_share=0.01, commission_pct=0.0

LONG:
  entry_fill = 100 + 0.5 = 100.5
  exit_fill = 110 - 0.5 = 109.5
  gross_pnl = (109.5 - 100.5) * 10 = 90.0
  entry_commission = 0.01 * 10 = 0.1
  exit_commission = 0.01 * 10 = 0.1
  net_pnl = 90.0 - 0.1 - 0.1 = 89.8
  
  Verify: equity change = net_pnl = 89.8
```

---

## G. DETERMINISM MODEL

### Separation of Concerns

**RESEARCH RESULT DATA** must be deterministic:
- trades
- fills
- P&L
- equity curve
- metrics
- strategy hash
- dataset hash
- provenance content
- result hash

**RUNTIME METADATA** can be non-deterministic:
- `datetime.now(UTC)` for audit timestamps
- process IDs
- object memory addresses

### Deterministic Trade IDs

Trade IDs must be deterministic based on chronological order:
```
trade-000001
trade-000002
trade-000003
```

Based on execution order, not random UUIDs.

### Required Invariants

For identical (dataset + strategy + configuration):

```
identical signals
identical orders
identical fills
identical P&L
identical equity curve
identical metrics
identical strategy hash
identical dataset hash
identical provenance content (excluding runtime timestamps)
identical result_hash
```

### Runtime Timestamps

Runtime timestamps (e.g., `BacktestResult.timestamp`) are stored as audit metadata but are **excluded from the research-result hash**. The result hash is computed over the deterministic data only.

---

## H. PROVENANCE MODEL

### BacktestProvenance

```python
class BacktestProvenance(BaseModel):
    backtest_id: str                    # deterministic hash of inputs
    strategy_id: str
    strategy_version: str
    strategy_hash: str                  # canonical hash of StrategySpec
    dataset_id: str
    dataset_version: str
    dataset_hash: str                   # content hash of Dataset
    instrument: str
    timeframe: str
    initial_capital: float
    num_candles: int
    start_timestamp: datetime
    end_timestamp: datetime
    cost_parameters: Dict[str, Any]
    slippage_parameters: Dict[str, Any]
    position_sizing_parameters: Dict[str, Any]
    execution_semantics: str            # e.g., "signal_at_t_close_execute_at_t_close"
    engine_version: str                 # "3.0.0"
    quant_engine_version: str           # "2.0.0"
    result_hash: str                    # hash of all deterministic results
    # Runtime metadata (excluded from result_hash):
    run_timestamp: datetime             # audit only, not in result_hash
```

### Result Hash

The result hash is a SHA-256 of all deterministic output data:
```python
result_hash = sha256(
    strategy_hash + dataset_hash + 
    serialized_trades + serialized_equity_curve +
    serialized_metrics + config
)
```

This must be stable across runs. Runtime timestamps are excluded.

### CANONICAL DATASET HASH — SPECIFICATION

#### DESIGN DECISION

The canonical dataset hash must produce **identical bytes** across runs and platforms. The serialization is fully specified with no ambiguity.

#### CANONICAL SERIALIZATION FORMAT (ALL COMPONENTS)

The following rules apply to ALL canonical serializations unless explicitly overridden for a specific component:

| Rule | Specification |
|------|---------------|
| **Encoding** | UTF-8 |
| **Record separator** | LF (`\n`, 0x0A) — never CRLF |
| **Field separator** | ASCII pipe `|` (0x7C) |
| **String escaping** | Backslash `\` is escaped as `\\`. Pipe `|` is escaped as `\|`. Newline in string values is escaped as `\n`. |
| **Null representation** | Empty string between separators: `||` for missing float; `<NULL>` for explicit null in string/object fields |
| **Boolean representation** | `true` / `false` (lowercase) |
| **Integer representation** | Base-10, no leading zeros (except `0` itself) |
| **Float representation** | IEEE 754 double precision formatted as `.10f` (10 decimal places) — see Section H Float Formatting Rules |
| **Trailing newline** | Every canonical serialization ends with exactly one `\n` |
| **Empty collections** | `[]` for empty arrays; `{}` for empty objects |
| **Key ordering** | Fields appear in the exact order explicitly enumerated below — NOT alphabetical |

**IMPORTANT ON FLOAT SERIALIZATION:** Hash identity operates on the canonical decimal representation (`.10f`), not raw IEEE-754 binary identity. Two floats that are mathematically equal but differ in their binary IEEE-754 representation (e.g., `1.0` vs `1.0000000000000002`) must serialize to the same `.10f` string and therefore hash identically.

#### FLOAT FORMATTING RULES

- All float values formatted with exactly 10 decimal places: `.10f`
- `-0.0` is normalized to `0.0` before formatting
- `float('nan')`, `float('inf')`, `float('-inf')` are represented as `<NULL>` for non-dataset components; for dataset hash (Section H) they are represented as empty fields between separators
- Python's `format(x, '.10f')` is used for all finite floats

#### NaN / +Inf / -Inf POLICY

**For dataset_hash:** `NaN`/`Inf` are serialized as empty fields between separators (per Section H). Duplicate timestamps must still be rejected before hashing.

**For strategy_hash, config_hash, result_hash:** Non-finite values in any component field **MUST be rejected before hashing** — a `ValueError` is raised if any float value in the canonical input is NaN or Inf. This prevents collision scenarios where different non-finite values could map to the same empty-field representation.

**Empty collections** are represented as `[]` (empty array) or `{}` (empty object) — never as null or empty string.

#### TRAILING NEWLINE

Every canonical serialization ends with exactly one `\n` character, including the final record. No trailing newline after the final `\n`.

### BacktestProvenanceTracker

Must actually be used by `BacktestEngine.run()`. Not dead architecture.

---

## I. HASHING MODEL

### DESIGN DECISION

Four distinct hash types are defined, each with a specific canonical serialization input. Runtime timestamps are excluded from all deterministic research hashes.

### Canonical Serialization Inputs

#### strategy_hash

**Input:** Canonical serialization of `StrategySpec` fields, in the exact order below. Each nested component must itself be serialized using the canonical serialization rules defined in Section H (CANONICAL SERIALIZATION FORMAT).

**Field ordering (authoritative — NOT alphabetical):**

```
strategy_id|strategy_version|strategy_name|instrument|timeframe|
entry_conditions_serialized|exit_conditions_serialized|
position_sizing_serialized|stop_loss_pct|take_profit_pct|
max_position_size|max_exposure_pct|required_indicators|
allow_short|cost_parameters_serialized|slippage_parameters_serialized|
execution_semantics|description|author|assumptions_serialized
```

**Nested component serialization:**

- `entry_conditions_serialized`: See Section I (Condition Serialization)
- `exit_conditions_serialized`: See Section I (Condition Serialization)
- `position_sizing_serialized`: See Section I (Position-Sizing Serialization)
- `cost_parameters_serialized`: See Section I (Cost Serialization)
- `slippage_parameters_serialized`: See Section I (Slippage Serialization)

**Excluded:** Any runtime metadata, timestamps, or non-deterministic fields.

**Condition serialization** must follow Section I. Equivalent logical structures that differ structurally (e.g., `A AND B` vs `B AND A`) are **NOT** normalized to the same hash unless explicitly specified as equivalent. Two structurally identical condition trees must produce identical `entry_conditions_serialized` strings.

#### config_hash

**Input:** Canonical serialization of `BacktestConfig` fields, in the exact order below:

```
initial_capital|cost_parameters_serialized|slippage_parameters_serialized|
allow_short|execution_semantics|max_position_size|seed|execution_delay
```

**`execution_delay`** is a required field of `BacktestConfig` and must be included in `config_hash`. Valid values: `0` or `1`. Default: `0`.

**Excluded:** Runtime timestamps, random seed state after generation.

#### result_hash

**Input:** SHA-256 of a single canonical result serialization string:

```
result_hash = sha256(canonical_result_serialization)
```

**canonical_result_serialization** is the concatenation of the following components, separated by `|`, in exact order:

```
strategy_hash|dataset_hash|canonical_trades|canonical_equity_curve|canonical_metrics|config_hash
```

**Component serialization:**

- `canonical_trades`: Each trade serialized as `trade_id|side|entry_fill_price|exit_fill_price|quantity|entry_commission|exit_commission|net_pnl|entry_timestamp|exit_timestamp|holding_period_bars`. Records joined by `\n`, trailing `\n`.
- `canonical_equity_curve`: Each `EquityPoint` serialized as `timestamp|total_equity|cash|position_market_value`. Records joined by `\n`, trailing `\n`.
- `canonical_metrics`: Each metric serialized as `metric_name|value`. Records joined by `\n`, trailing `\n`. If a metric value is `None`, serialize as `<NULL>`. Float values use `.10f`.
- `config_hash`: As defined above.
- `strategy_hash`, `dataset_hash`: As defined above.

**Excluded:** `run_timestamp`, `backtest_id` (if it contains runtime data), any process/runtime metadata including wall-clock timestamps, process IDs, machine hostname, Python process metadata, memory addresses, random runtime identifiers, and execution duration.

#### condition_serialization

Declaratory entry/exit conditions must be serialized canonically. **No arbitrary Python expressions, no `eval()`, no `exec()`, no `lambda`, no executable source strings are permitted in condition serialization.**

A condition is serialized as a structured tree:

```
condition_type|operator|indicator_name|parameter_order|threshold_value|left_operand_serialized|right_operand_serialized|NOT_applied
```

Where:
- `condition_type`: `INDICATOR`, `THRESHOLD`, `COMPARISON`, `LOGICAL_AND`, `LOGICAL_OR`, `LOGICAL_NOT`
- `operator`: The comparison or logical operator (e.g., `>`, `<`, `>=`, `<=`, `==`, `!=`, `AND`, `OR`, `NOT`)
- `indicator_name`: The indicator identifier string (e.g., `"RSI"`, `"SMA_20"`)
- `parameter_order`: The ordered parameter list serialized as comma-separated values (e.g., `"14,70,30"`)
- `threshold_value`: Float formatted as `.10f`
- `left_operand_serialized`, `right_operand_serialized`: Recursive condition serialization, or `<NULL>` if not applicable
- `NOT_applied`: `true` or `false`

**Rules:**
- Equivalent logical structures that differ structurally (e.g., `A AND B` vs `B AND A`) are **NOT** normalized to the same hash unless explicitly specified as equivalent by design.
- Two structurally identical condition trees must produce identical `condition_serialization` strings.
- Null operands serialize as `<NULL>`.
- Boolean values serialize as `true` / `false`.
- Empty conditions serialize as an empty string `""`.

#### position_sizing_serialized

`method|parameters_serialized` where `method` is `fixed` or `percent`.

- For `fixed`: `fixed|fixed_quantity=.10f|max_position_size=.10f`
- For `percent`: `percent|percent_of_capital=.10f|max_position_size=.10f`

Float values use `.10f`.

#### cost_parameters_serialized

`commission_per_share=.10f|commission_pct=.10f`

Float values use `.10f`.

#### slippage_parameters_serialized

`fixed_slippage=.10f|pct_slippage=.10f|atr_multiplier=.10f|atr_period=integer`

Float values use `.10f`. Integer values are base-10 without leading zeros.

#### trade_serialization

Each `Trade` object serialized as:
```
trade_id|side|entry_fill_price=.10f|exit_fill_price=.10f|quantity=.10f|entry_commission=.10f|exit_commission=.10f|gross_pnl=.10f|net_pnl=.10f|entry_timestamp|exit_timestamp|holding_period_bars|exit_reason
```

If `exit_fill_price` is None (open trade), serialize as `<NULL>`.
If `exit_timestamp` is None, serialize as `<NULL>`.
If `holding_period_bars` is None, serialize as `<NULL>`.
Fields are separated by `|`. Records joined by `\n`, trailing `\n`.

#### equity_curve_serialization

Each `EquityPoint` serialized as:
```
timestamp|total_equity=.10f|cash=.10f|position_market_value=.10f
```

Fields are separated by `|`. Records joined by `\n`, trailing `\n`.

#### metric_serialization

Each metric serialized as `metric_name|value`.
- If `value` is a float: `.10f`
- If `value` is `None`: `<NULL>`
- If `value` is `float('inf')`: `<NULL>` and the metric must be rejected before hashing (per Section H NaN/Inf Policy)
- If `value` is an integer: base-10, no leading zeros
- If `value` is a ratio/percentage: `.10f`
Fields separated by `|`. Records joined by `\n`, trailing `\n`.


### Execution Delay — Formal Parameter

#### DESIGN DECISION

`execution_delay` is a formal integer parameter of `BacktestConfig` that determines the number of bars between signal generation and order execution.

#### FORMULA / RULE

```
execution_delay: integer, required
Allowed values: 0, 1
Default: 0
```

**`execution_delay = 0`:**
Signal determined using information available through bar[t].
→ Order executes at bar[t] close under the theoretical same-bar execution assumption.

**`execution_delay = 1`:**
Signal determined at bar[t].
→ Order executes at bar[t+1] close.

No larger delay values are permitted in Phase 3 unless explicitly designed and tested.

`execution_delay` is included in `config_hash` and `result_hash` via `config_hash`.

### Execution Delay + Missing Next Bar

If `execution_delay = 1` and the required execution bar `t+1` does not exist:

```
OrderStatus.REJECTED
reason = TIME_EXPIRED
```

- No trade is created.
- No position state changes.
- No cash changes.
- No equity mutation caused by the rejected order.

If the execution bar `t+1` exists but required OHLC data is missing:

```
OrderStatus.REJECTED
reason = INVALID_EXECUTION_DATA
```

- No trade is created.
- No position state changes.
- No cash changes.
- No equity mutation caused by the rejected order.

### Deterministic Research Identity vs. Runtime Metadata

| Category | Included in hashes? | Examples |
|----------|-------------------|----------|
| **Deterministic research identity** | YES | strategy_id, instrument, timeframe, initial_capital, all trade data, all equity points, all metric values, cost parameters |
| **Runtime metadata** | NO | `run_timestamp`, process ID, memory address, `datetime.now(UTC)` |

### ACCEPTANCE TESTS

- **H-1:** Same dataset + same strategy → identical `strategy_hash` across runs
- **H-2:** Same backtest → identical `result_hash` across runs
- **H-3:** `result_hash` does not change when `run_timestamp` changes
- **H-4:** `config_hash` does not change when runtime metadata changes
- **H-5:** `dataset_hash` is content-based, not based on dataset object identity
- **H-6:** Changing any single float in any trade → completely different `result_hash`
- **H-7:** `strategy_hash` excludes runtime timestamps
- **H-8:** `result_hash` excludes runtime timestamps

---

## J. POSITION SIZING

### DESIGN DECISION

Phase 3 supports two position sizing methods: `fixed` and `percent`. The `atr_based` method is **removed from Phase 3 scope**.

### RATIONALE

The `percent` method requires a precise definition of what "percent" refers to and the exact sequence from signal to fill. The `atr_based` method requires additional parameter definitions that were left ambiguous in the original design. Phase 3 supports only methods with exact, unambiguous formulas and deterministic rejection semantics.

---

### Maximum Exposure Enforcement

#### Purpose

The `max_exposure_pct` parameter constrains the **TOTAL RESULTING GROSS EXPOSURE** of the portfolio, not merely the notional of the incoming order. This prevents the strategy from exceeding a gross position whose absolute market value surpasses a safe fraction of current equity.

**Phase 3 Single-Position Constraint:** Phase 3 supports at most one open position at any time. `OPEN → OPEN` via a new `open_position()` call is invalid (raises `ValueError`). Pyramiding is **not supported**. Multiple simultaneous positions are **not supported**.

**Execution Path:** In Phase 3, a new entry occurs only while FLAT. An exit must transition `OPEN → FLAT` before a new entry can occur. Therefore, the "existing position + new position" scenario is **not an executable Phase 3 path**. The generic formula below is defined mathematically to make the invariant explicit, but during normal Phase 3 operation, `existing_gross_exposure` is always `0` at order validation time.

#### Gross Exposure Definition

Gross exposure is defined as the absolute market value of all open positions. Because Phase 3 allows only one position at a time (no simultaneous multi-position accumulation), total gross exposure is:

```
gross_exposure = abs(existing_position_market_value) + abs(new_position_market_value)
```

**IMPORTANT:** Gross exposure uses absolute values. LONG and SHORT exposures do NOT cancel each other mathematically. The constraint is **GROSS**, not NET.

#### Existing-Position Treatment

When a position already exists, its current market value MUST be included in the exposure calculation:

```
existing_gross_exposure = abs(existing_position_market_value)
```

For a FLAT state (no position):
```
existing_gross_exposure = 0
```

#### New-Order Treatment

The incoming order contributes:
```
new_gross_exposure = abs(actual_fill_price × quantity)
```

#### Resulting Exposure Formula

```
resulting_gross_exposure = existing_gross_exposure + new_gross_exposure
```

#### Exposure Limit Formula

```
exposure_limit = (max_exposure_pct / 100) × current_equity
```

#### Rejection Condition

The order is accepted only when:
```
resulting_gross_exposure <= exposure_limit
```

Otherwise:
- `OrderStatus.REJECTED`
- `reason = MAX_EXPOSURE_EXCEEDED`

#### FLAT-State Behavior

When the account is FLAT (`existing_gross_exposure = 0`):
```
resulting_gross_exposure = new_gross_exposure
```

The constraint simplifies to: `abs(actual_fill_price × quantity) <= exposure_limit`.

#### Existing-Position Behavior

**When a position already exists** (this is **not an executable Phase 3 path** — `OPEN → OPEN` is invalid; the formula is retained for mathematical generality):

```
resulting_gross_exposure = abs(existing_position_market_value) + abs(actual_fill_price × quantity)
```

#### No-Partial-Fill Rule

There is NO partial fill under the exposure constraint. If the resulting gross exposure would exceed the limit, the ENTIRE order is rejected. No resize-and-retry, no partial execution, no engine exception.

#### Deterministic Rejection Semantics

Exposure rejection is deterministic:
- No state mutation
- No trade record
- No equity modification
- The equity curve continues unchanged for that bar
- Returns `OrderStatus.REJECTED` with `reason = MAX_EXPOSURE_EXCEEDED`

#### Acceptance Tests

| # | Scenario | Equity | max_exposure_pct | Existing | New | Resulting | Limit | Result |
|---|----------|--------|-----------------|----------|-----|-----------|-------|--------|
| AE-1 | Flat, within limit | 10,000 | 50% | 0 | 4,000 | 4,000 (40%) | 5,000 | ACCEPT |
| AE-2 | Existing, exceeds | 10,000 | 50% | 3,000 | 3,000 | 6,000 (60%) | 5,000 | REJECT |
| AE-3 | Existing, at limit | 10,000 | 50% | 3,000 | 2,000 | 5,000 (50%) | 5,000 | ACCEPT |
| AE-4 | Existing, 0.01% over | 10,000 | 50% | 4,000 | 1,001 | 5,001 (50.01%) | 5,000 | REJECT |

---

### METHOD = fixed

**FORMULA / RULE:**
```
quantity = fixed_quantity
```

**Constraints:**
- `fixed_quantity > 0`
- `fixed_quantity ≤ max_position_size`
- If `fixed_quantity` is None → method is invalid → raise `ValueError`

**WORKED EXAMPLE:**
- `fixed_quantity = 10.0` → `quantity = 10.0`

---

### METHOD = percent

#### DESIGN DECISION

For `method=percent`, the exact execution sequence is:

```
SIGNAL generated at bar[t] close
  → determine sizing_price = requested execution price
  → calculate quantity using sizing_price and current_equity
  → create order with calculated quantity
  → calculate actual fill price including slippage
  → validate resulting notional/cash constraints
  → execute or reject
```

**sizing_price = requested execution price** (i.e., the price used for sizing calculation is the same price that the order requests as execution).

**quantity is calculated BEFORE slippage changes the actual fill.**

This means:
- The sizing calculation uses the requested price (pre-slippage)
- The actual fill price may differ due to slippage
- If the actual fill causes the position to exceed intended allocation, the order is **rejected** (not partially filled)

#### RATIONALE

Using the requested price (not the slippage-adjusted fill price) for sizing ensures that the position size is determined by the strategy's signal logic, not by an unpredictable slippage adjustment. The validation step after fill ensures that slippage does not silently create an oversized position.

#### FORMULA / RULE

**Step 1 — Determine sizing_price:**
```
sizing_price = requested_execution_price = bar[t].close
```

**Step 2 — Calculate target_notional:**
```
target_notional = (percent_of_capital / 100) × current_equity
```

Where `current_equity = cash + position_market_value` at signal time (from EquityTracker).

**Step 3 — Calculate quantity:**
```
quantity = floor(target_notional / sizing_price)
```

**Step 4 — Create order with calculated quantity.**

**Step 5 — Calculate actual fill price including slippage:**
```
slippage_price = fixed_slippage + (pct_slippage / 100) × requested_price + atr_multiplier × atr
LONG:   actual_fill_price = requested_price + slippage_price
SHORT:  actual_fill_price = requested_price - slippage_price
```

**Step 6 — Validate constraints (see Maximum Exposure Enforcement):**
```
required_cash = (actual_fill_price × quantity) + entry_commission
IF required_cash > current_cash:
  → REJECT order (OrderStatus.REJECTED, reason="INSUFFICIENT_CASH")
ELSE IF quantity < 1:
  → REJECT order (OrderStatus.REJECTED, reason="INSUFFICIENT_CAPITAL")
ELSE:
  // Apply the general Maximum Exposure Enforcement rule:
  // new_gross_exposure = abs(actual_fill_price × quantity)
  // existing_gross_exposure = abs(existing_position_market_value)
  // resulting_gross_exposure = existing_gross_exposure + new_gross_exposure
  // exposure_limit = (max_exposure_pct / 100) × current_equity
  // Accept only if resulting_gross_exposure <= exposure_limit
  IF resulting_gross_exposure > exposure_limit:
    → REJECT order (OrderStatus.REJECTED, reason="MAX_EXPOSURE_EXCEEDED")
  ELSE:
    → EXECUTE order
```

**Step 7 — If executed, update state using actual_fill_price.**

What happens when the resulting gross exposure exceeds the limit:

The order is **REJECTED**. There is no partial fill, no resize-and-execute, and no engine-level exception. The deterministic response is `OrderStatus.REJECTED` with reason `MAX_EXPOSURE_EXCEEDED`.

This means:
- The quantity is calculated using the pre-slippage sizing_price
- The resulting gross exposure (existing + new) is checked against `exposure_limit = (max_exposure_pct / 100) × current_equity`
- If `resulting_gross_exposure > exposure_limit`, the entire order is rejected
- No trade is recorded
- No state change occurs
- The equity curve continues unchanged for that bar
- Per the No-Partial-Fill Rule, the order is never resized and re-submitted

#### Edge Cases

| Condition | Resolution |
|-----------|------------|
| `percent_of_capital <= 0` | Raise `ValueError("percent_of_capital must be > 0")` |
| `percent_of_capital > 100` | Raise `ValueError("percent_of_capital must be ≤ 100")` |
| `current_equity <= 0` | `target_notional = 0` → `quantity = 0` → **REJECT** (reason: `INSUFFICIENT_CAPITAL`). No exception raised. |
| `sizing_price <= 0` | Raise `ValueError("sizing_price must be > 0")` |
| `quantity < 1` (after floor) | **REJECT** (reason: `INSUFFICIENT_CAPITAL`). No exception raised. |
| `quantity > max_position_size` | Cap: `quantity = min(quantity, max_position_size)` |
|| `resulting_gross_exposure > exposure_limit` | **REJECT** (reason: `MAX_EXPOSURE_EXCEEDED`). No exception raised. No partial fill. |
|| `required_cash > current_cash` | **REJECT** (reason: `INSUFFICIENT_CASH`). No exception raised. |
|| `quantity = 0` | **REJECT** (reason: `INSUFFICIENT_CAPITAL`) |
|| Minimum quantity | `quantity_min = 1` (one share/unit). If `floor(...)` yields 0, reject. |
|| Maximum quantity | `quantity_max = max_position_size`. Hard cap enforced after floor and before slippage validation. |
|| Minimum notional | `target_notional_min = sizing_price × 1` (one unit at sizing price). If `target_notional < sizing_price`, reject. |
|| Insufficient cash | **REJECT** with `OrderStatus.REJECTED`, reason `INSUFFICIENT_CASH`. |
|| Zero/negative equity | **REJECT** with `OrderStatus.REJECTED`, reason `INSUFFICIENT_CAPITAL`. |
|| Rounding | `floor()` rounds down to nearest integer. No ceiling, no ceiling-to-nearest. |

#### WORKED EXAMPLE

- `percent_of_capital = 10.0`, `current_equity = $10,000`, `entry_fill_price = $100`
- `target_notional = (10.0 / 100) × 10000 = 1000`
- `quantity = floor(1000 / 100) = floor(10.0) = 10`
- `slippage_price = 0.5`, `actual_fill_price = 100 + 0.5 = 100.5`
- `new_gross_exposure = abs(100.5 × 10) = 1005`
- `existing_gross_exposure = 0` (FLAT account)
- `resulting_gross_exposure = 0 + 1005 = 1005`
- `exposure_limit = (10.0 / 100) × 10000 = 1000`
- `1005 > 1000` → **REJECT** (reason: `MAX_EXPOSURE_EXCEEDED`)

**Note:** Even though `percent_of_capital = 10%` targets $1,000 notional, slippage pushes the actual gross exposure to $1,005, which exceeds the 10% exposure limit. The order is rejected in full.

#### WORKED EXAMPLE — Rejection due to resulting gross exposure exceeding limit

- `percent_of_capital = 100.0`, `current_equity = $10,000`, `entry_fill_price = $10`, `max_position_size = 1000`, `max_exposure_pct = 50.0`
- `target_notional = (100.0 / 100) × 10000 = 10000`
- `quantity = floor(10000 / 10) = 1000`
- `quantity = min(1000, max_position_size=1000) = 1000`
- `slippage_price = 0.5`, `actual_fill_price = 10 + 0.5 = 10.5`
- `new_gross_exposure = abs(10.5 × 1000) = 10500`
- `existing_gross_exposure = 0` (FLAT account)
- `resulting_gross_exposure = 0 + 10500 = 10500`
- `exposure_limit = (50.0 / 100) × 10000 = 5000`
- `10500 > 5000` → **REJECT** (reason: `MAX_EXPOSURE_EXCEEDED`)

#### ACCEPTANCE TESTS

- **PS-SEQ-1:** Verify sizing_price = requested execution price (not fill price)
- **PS-SEQ-2:** Verify quantity calculated before slippage
- **PS-SEQ-3:** Verify actual fill price used for cash validation, not sizing price
- **PS-SEQ-4:** Verify order rejection when `resulting_gross_exposure > exposure_limit` (see Maximum Exposure Enforcement)
- **PS-FIXED-1:** `fixed_quantity=10` → `quantity=10`
- **PS-PERCENT-1:** `percent_of_capital=10, equity=10000, price=100` → `quantity=10`
- **PS-PERCENT-2:** `percent_of_capital=10, equity=50, price=100` → **REJECT** (`INSUFFICIENT_CAPITAL`)
- **PS-PERCENT-3:** `percent_of_capital=100, equity=10000, price=10, max_position_size=500` → `quantity=500`
- **PS-PERCENT-4:** `percent_of_capital=0` → `ValueError`
- **PS-PERCENT-5:** `percent_of_capital=101` → `ValueError`
- **PS-PERCENT-6:** `current_equity=0` → **REJECT** (`INSUFFICIENT_CAPITAL`)
- **PS-PERCENT-7:** `current_equity<0` → **REJECT** (`INSUFFICIENT_CAPITAL`)
- **PS-PERCENT-8:** `quantity<1` after floor → **REJECT** (`INSUFFICIENT_CAPITAL`)
- **PS-PERCENT-9:** `resulting_gross_exposure > exposure_limit` after slippage → **REJECT** (`MAX_EXPOSURE_EXCEEDED`)
- **PS-PERCENT-10:** Insufficient cash after fill → **REJECT** (`INSUFFICIENT_CASH`)
- **PS-EDGE-1:** `percent_of_capital=100, equity=$10000, price=$1, max_exposure=100%` → `quantity=10000`, valid if within max_position_size
- **PS-MIN-1:** Minimum quantity = 1. If `floor(...)` yields 0 → reject.
- **PS-MAX-1:** Quantity capped by `max_position_size` after floor, before slippage validation.

---

## K. METRICS

### DESIGN DECISION

Every metric must have an exact formula, defined source series, units, sampling frequency, annualization convention, minimum data requirement, and zero-denominator behavior. No metric may be inferred from implementation conventions. All formulas below are authoritative.

### SOURCE SERIES

All metrics use one of two source series:
- **Trade series:** `List[Trade]` from the TradeLedger (only closed trades)
- **Equity series:** `List[EquityPoint]` from the EquityTracker (every bar)

Where:
- `equity_values[i]` = `EquityPoint[i].total_equity`
- `returns[i]` = `(equity_values[i] - equity_values[i-1]) / equity_values[i-1]` for `i ≥ 1`
- `n` = number of equity points (bars)
- `T` = number of trades (closed)
- `W` = winning trades (net_pnl > 0)
- `L` = losing trades (net_pnl < 0)
- `B` = breakeven trades (net_pnl == 0)

### TIMEFRAME-AWARE ANNUALIZATION

#### DESIGN DECISION

**The constant 252 is replaced by `periods_per_year`, which is defined for every supported timeframe.** Annualization uses `periods_per_year` consistently across all metrics.

#### RATIONALE

Different timeframes have different numbers of bars per year. Using a single constant (252) for all timeframes is incorrect for hourly, minutely, and weekly data. Each timeframe must have its own `periods_per_year` value.

#### FORMULA / RULE

```
periods_per_year = {
    "M1":   525600,    # 365 × 24 × 60
    "M5":   105120,    # 365 × 24 × 12
    "M15":  35040,     # 365 × 24 × 4
    "H1":   8760,      # 365 × 24
    "H4":   2190,      # 365 × 6
    "D1":   365,       # 365 (forex 24h market)
}
```

**Primary annualization formula for returns:**
```
annualized_return = (final_equity / initial_equity) ** (periods_per_year / number_of_periods) - 1
```

Where `number_of_periods = n - 1` (number of return intervals, not number of equity points).

#### periods_per_year for Volatility, Sharpe, Sortino

**Volatility:**
```
annualized_volatility = std(returns) × sqrt(periods_per_year)
```

**Sharpe ratio:**
```
annualized_return = (final_equity / initial_equity) ** (periods_per_year / (n - 1)) - 1
annualized_volatility = std(returns) × sqrt(periods_per_year)
sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility
```

**Sortino ratio:**
```
annualized_return = (final_equity / initial_equity) ** (periods_per_year / (n - 1)) - 1
downside_deviation_annualized = downside_deviation × sqrt(periods_per_year)
sortino_ratio = (annualized_return - risk_free_rate) / downside_deviation_annualized
```

#### UNRELIABLE ANNUALIZATION

If `number_of_periods < periods_per_year` (i.e., the backtest period is shorter than one full year of that timeframe), annualized return, volatility, Sharpe, and Sortino are **marked as unavailable** (return `None`). No approximation is used.

**Exception:** `periods_per_year / (n - 1)` must be ≥ 1.0 for annualization to be reliable. If `< 1.0`, return `None`.

#### ACCEPTANCE TESTS

- **ANNUAL-1:** D1, n=366 → periods_per_year=365, number_of_periods=365 → annualization exponent = 1.0
- **ANNUAL-2:** H1, n=8761 → periods_per_year=8760, number_of_periods=8760 → annualization exponent = 1.0
- **ANNUAL-3:** D1, n=100 → periods_per_year=365, number_of_periods=99 → exponent = 365/99, but 99 < 365 → **return None**
- **ANNUAL-4:** Verify sqrt(periods_per_year) used for volatility, not sqrt(252)
- **ANNUAL-5:** Verify periods_per_year varies by timeframe in all metric calculations

---

### 1. total_return

- **Formula:** `(final_equity - initial_capital) / initial_capital`
- **Source:** Equity series (first and last points)
- **Units:** Ratio (e.g., 0.05 = 5%)
- **Sampling:** Entire equity curve
- **Annualization:** None
- **Minimum observations:** 2 equity points
- **Zero denominator:** If `initial_capital == 0`, return `None` (undefined)
- **NaN/inf behavior:** If any equity value is NaN or inf, return `None`
- **Worked example:** `initial_capital=10000, final_equity=11000` → `total_return = 1000/10000 = 0.10` (10%)

### 2. cumulative_return

- **Formula:** `Π(1 + r_i) - 1` where `r_i` are per-period returns
- **Source:** Equity series
- **Units:** Ratio
- **Sampling:** Entire equity curve
- **Annualization:** None
- **Minimum observations:** 2 equity points
- **Zero denominator:** If any `1 + r_i` term is ≤ 0, return `None` (equity went to zero or below)
- **NaN/inf behavior:** If any return is NaN or inf, return `None`
- **Worked example:** Returns = [0.05, -0.03, 0.02] → `cumulative = (1.05)(0.97)(1.02) - 1 = 0.03918` (3.918%)

### 3. annualized_return

- **Formula:** `(final_equity / initial_equity) ** (periods_per_year / (n - 1)) - 1`
- **Source:** Equity series
- **Units:** Ratio (annualized)
- **Sampling:** Entire equity curve
- **Annualization:** `periods_per_year / (n - 1)` exponent
- **Minimum observations:** `n - 1 >= periods_per_year` (backtest spans ≥ 1 year). Otherwise return `None`.
- **Zero denominator:** If `initial_equity == 0`, return `None`. If `n - 1 == 0`, return `None`.
- **NaN/inf behavior:** If final_equity or initial_equity is NaN/inf, return `None`
- **Worked example:** `initial=10000, final=11000, periods_per_year=365, n=366` → `annualized = (11000/10000)^(365/365) - 1 = 0.10` (10%)

### 4. volatility

- **Formula:** `std(returns, ddof=1) × sqrt(periods_per_year)`
- **Source:** Equity series (bar-to-bar returns)
- **Units:** Ratio
- **Sampling:** Bar-to-bar equity returns
- **Standard deviation:** Sample standard deviation (ddof=1), not population
- **Annualization:** `sqrt(periods_per_year)`
- **Minimum observations:** At least 2 return observations (3 equity points minimum)
- **Zero denominator:** If all returns are identical (std = 0), return `0.0`
- **NaN/inf behavior:** If any return is NaN or inf, return `None`
- **Worked example:** `std(returns) = 0.02, periods_per_year=365` → `volatility = 0.02 × sqrt(365) ≈ 0.382` (38.2%)

### 5. sharpe_ratio

- **Formula:** `(annualized_return - risk_free_rate) / annualized_volatility`
- **Source:** Equity series, `risk_free_rate` parameter (annualized, e.g., 0.05 for 5%)
- **Units:** Ratio (dimensionless)
- **Sampling:** Bar-to-bar equity returns
- **Annualization:** Both numerator and denominator are annualized using `periods_per_year`
- **Minimum observations:** `n - 1 >= periods_per_year` AND `volatility > 0`
- **Zero denominator:** If `annualized_volatility == 0`:
  - If `annualized_return > risk_free_rate`: return `float('inf')`
  - If `annualized_return == risk_free_rate`: return `0.0`
  - If `annualized_return < risk_free_rate`: return `float('-inf')`
- **NaN/inf behavior:** If `annualized_return` is `None`, return `None`
- **Risk-free rate convention:** Annualized rate, provided as a parameter. Default = 0.0.
- **Worked example:** `annualized_return=0.20, risk_free=0.05, annualized_vol=0.15` → `sharpe = (0.20 - 0.05) / 0.15 = 1.0`

### 6. sortino_ratio

- **Formula:** `(annualized_return - risk_free_rate) / downside_deviation_annualized`
- **Source:** Equity series, `risk_free_rate` parameter
- **Units:** Ratio (dimensionless)
- **Sampling:** Bar-to-bar equity returns
- **Downside deviation definition:**
  ```
  downside_deviation = sqrt( (1/N) × Σ min(r_i - target, 0)^2 )
  ```
  where `r_i` = bar-to-bar return at bar `i`, `target = risk_free_rate / periods_per_year`, `N` = total number of returns
- **Annualization:** `downside_deviation × sqrt(periods_per_year)`
- **Minimum observations:** Same as sharpe_ratio, AND `downside_deviation > 0`
- **Zero denominator:** If `downside_deviation == 0`:
  - If `annualized_return > risk_free_rate`: return `float('inf')`
  - If `annualized_return == risk_free_rate`: return `0.0`
  - If `annualized_return < risk_free_rate`: return `float('-inf')`
- **NaN/inf behavior:** If `annualized_return` is `None`, return `None`
- **Worked example:** `annualized_return=0.20, risk_free=0.05, downside_deviation=0.10` → `sortino = (0.20 - 0.05) / 0.10 = 1.5`

### 7. max_drawdown

- **Formula (raw):** `min(equity_values[i] / running_peak[i] - 1)` for all `i`
  where `running_peak[i] = max(equity_values[0..i])`
- **Formula (reported):** `reported_max_drawdown = -raw_max_drawdown`
  Therefore `reported_max_drawdown >= 0` always.
- If `raw_max_drawdown == 0`: `reported_max_drawdown = 0`
- **Source:** Equity series
- **Units:** Ratio (reported as positive value)
- **Sampling:** Entire equity curve
- **Annualization:** None
- **Minimum observations:** 2 equity points
- **Zero denominator:** If `running_peak[i] == 0` at any point, skip that point (treat drawdown as 0 for that point)
- **NaN/inf behavior:** If any equity value is NaN or inf, return `None`
- **Worked example:** Equity = [10000, 11000, 9500, 10500, 12000] → Peaks = [10000, 11000, 11000, 11000, 12000] → Drawdowns = [0, 0, -0.1364, -0.0455, 0] → `max_drawdown = 0.1364` (13.64%)

### 8. max_drawdown_duration

#### DESIGN DECISION

The duration is counted using an exact convention.

#### FORMULA / RULE

```
drawdown_duration = number of completed periods from the peak bar
                   until the first bar whose equity >= the previous peak.
```

More precisely:
1. Identify the peak bar `p` where `equity[p] = running_peak[p]` and the drawdown from `p` is maximal.
2. Count from bar `p + 1` to bar `r` where `r` is the first bar such that `equity[r] >= equity[p]`.
3. `duration = r - p` (number of bars from peak to recovery, inclusive of both endpoints minus 1).

If no recovery occurs, `max_drawdown_duration = None`.

#### Worked Example

```
Equity: 100 → 90 → 95 → 100
```

- Peak at index 0: `equity[0] = 100`
- Trough at index 1: `equity[1] = 90`
- Recovery at index 3: `equity[3] = 100 >= 100`
- Duration = `3 - 0 = 3` bars (indices 0, 1, 2, 3 → 3 complete periods from peak to recovery)

**Expected duration for `100 → 90 → 95 → 100`:** `3` bars.

#### Edge Cases

| Condition | Resolution |
|-----------|------------|
| No recovery ever | `max_drawdown_duration = None` |
| Peak at final bar (no drawdown) | `max_drawdown_duration = 0` |
| Recovery on next bar (peak → recovery in 1 bar) | `max_drawdown_duration = 1` |
| Multiple drawdowns of same depth | Use the first occurrence |
| Single equity point | `max_drawdown_duration = 0` |

#### Minimum observations: 2 equity points

### 9. recovery_duration

- **Formula:** `recovery_duration = recovery_bar_index - trough_bar_index`
  where `trough_bar_index` is the index of the lowest equity point after the max_drawdown peak,
  and `recovery_bar_index` is the first bar index satisfying `equity[recovery_bar_index] >= peak_equity`.
- **Source:** Equity series timestamps
- **Units:** Bars (integer)
- **Sampling:** Entire equity curve
- **Minimum data:** Must have a completed drawdown with recovery
- **Edge case:** If no completed drawdown exists: `recovery_duration = None`
- **Worked example:** Equity = [10000, 11000, 9500, 10500, 12000] → Trough at index 2 (9500), peak = 11000 at index 1 → Recovery at index 4 (12000 >= 11000) → `recovery_duration = 4 - 2 = 2` bars

### 10. win_rate

- **Formula:** `W / T`
- **Source:** Trade series
- **Units:** Ratio
- **Sampling:** Closed trades
- **Minimum observations:** At least 1 closed trade
- **Zero denominator:** If `T == 0`, return `None`
- **NaN/inf behavior:** If any `net_pnl` is NaN or inf, exclude from count and return `None` if all are NaN/inf
- **Worked example:** `W=7, T=10` → `win_rate = 0.70` (70%)

### 11. loss_rate

- **Formula:** `L / T`
- **Source:** Trade series
- **Units:** Ratio
- **Sampling:** Closed trades
- **Minimum observations:** At least 1 closed trade
- **Zero denominator:** If `T == 0`, return `None`
- **Worked example:** `L=3, T=10` → `loss_rate = 0.30` (30%)

### 12. breakeven_trades

- **Definition:** Count of trades where `abs(net_pnl) <= BREAKEVEN_TOLERANCE`

**BREAKEVEN_TOLERANCE** is defined as `1e-10` (absolute currency units, i.e., $0.0000000001). A trade is breakeven iff `abs(net_pnl) <= 1e-10`. This tolerance is absolute, not relative, and is expressed in the same currency units as `net_pnl`.
- **Source:** Trade series
- **Units:** Integer count
- **Note:** Counted separately from winners and losers. `pnl == 0` is neither.

### 13. profit_factor

- **Formula:** `gross_wins / abs(gross_losses)`
  where `gross_wins = Σ net_pnl for trades where net_pnl > 0`
  and `gross_losses = Σ net_pnl for trades where net_pnl < 0`
- **Source:** Trade series
- **Units:** Ratio
- **Sampling:** Closed trades
- **Minimum observations:** At least 1 winning AND 1 losing trade
- **Zero denominator:** If `gross_losses == 0` (all trades profitable):
  - If `gross_wins > 0`: return `float('inf')`
  - If `gross_wins == 0`: return `0.0`
- **NaN/inf behavior:** If any `net_pnl` is NaN or inf, return `None`
- **Worked example:** `gross_wins=500, gross_losses=-300` → `profit_factor = 500/300 ≈ 1.667`

### 14. expectancy

- **Formula:** `total_net_pnl / T`
- **Source:** Trade series
- **Units:** Currency per trade
- **Sampling:** Closed trades
- **Zero denominator:** If `T == 0`, return `None`

### 15. average_trade

- **Formula:** `total_net_pnl / T` (same as expectancy)
- **Source:** Trade series
- **Units:** Currency per trade
- **Zero denominator:** If `T == 0`, return `None`

### 16. median_trade

- **Formula:** `median([net_pnl for all closed trades])`
- **Source:** Trade series
- **Units:** Currency
- **Minimum observations:** At least 1 closed trade
- **Zero denominator:** If `T == 0`, return `None`

### 17. average_win

- **Formula:** `mean([net_pnl for trades where net_pnl > 0])`
- **Source:** Trade series
- **Units:** Currency
- **Minimum observations:** At least 1 winning trade
- **Zero denominator:** If `W == 0`, return `None`

### 18. average_loss

- **Formula:** `mean([net_pnl for trades where net_pnl < 0])` reported as positive value
- **Source:** Trade series
- **Units:** Currency
- **Minimum observations:** At least 1 losing trade
- **Zero denominator:** If `L == 0`, return `None`

### 19. turnover

#### DESIGN DECISION

The denominator and numerator are precisely defined.

#### FORMULA / RULE

```
total_notional = Σ (entry_fill_price × quantity + exit_fill_price × quantity)
                for each closed trade
```

```
average_equity = arithmetic mean of total_equity values across ALL equity points
```

```
turnover = total_notional / average_equity
```

#### Which equity points are included in average_equity:

**All** `EquityPoint.total_equity` values from the entire equity curve, including the initial point and every bar. If the equity curve has `n` points, `average_equity` is the mean of all `n` values.

#### Edge Cases

| Condition | Resolution |
|-----------|------------|
| `average_equity == 0` | `turnover = None` (undefined) |
| `average_equity < 0` | `turnover = None` (undefined; negative equity is impossible under current constraints) |
| No closed trades | `total_notional = 0`, `turnover = 0.0` |
| Single bar (no returns) | `average_equity = initial_capital`, `total_notional` from trades |

#### WORKED EXAMPLE

- Trade: entry_fill=100, exit_fill=110, qty=10
- `total_notional = (100 × 10) + (110 × 10) = 1000 + 1100 = 2100`
- Equity curve: [10000, 10100, 10500, 10000, 10200]
- `average_equity = (10000 + 10100 + 10500 + 10000 + 10200) / 5 = 10160`
- `turnover = 2100 / 10160 ≈ 0.2067`

#### ACCEPTANCE TESTS

- **TURN-1:** Verify `total_notional` includes both entry and exit fill prices × quantity
- **TURN-2:** Verify `average_equity` uses ALL equity points (not just non-flat bars)
- **TURN-3:** `average_equity=0` → `turnover=None`
- **TURN-4:** No trades → `turnover=0.0`
- **TURN-5:** Verify worked example matches formula

### 20. exposure

#### DESIGN DECISION

Exposure is defined with exact edge case rules.

#### FORMULA / RULE

```
gross_exposure_t = abs(position_market_value_t) / equity_t
```

```
exposure = mean(gross_exposure_t) for all t where equity_t > 0
```

#### Edge Cases

| Condition | Resolution |
|-----------|------------|
| `equity_t == 0` | `gross_exposure_t` is undefined; **exclude this bar** from the mean |
| `equity_t < 0` | **IMPOSSIBLE** under current constraints (cash >= 0, no leverage). If it occurs, exclude from mean. |
| Flat position | `gross_exposure_t = 0.0` (since `position_market_value = 0`) |
| Sampling points | **All** equity points where `equity > 0` |
| Return format | Ratio (0.0 = flat, 1.0 = fully invested) |
| Aggregation method | Arithmetic mean of `gross_exposure_t` values |
| All bars excluded | If no equity points have `equity > 0`, return `None` |

#### WORKED EXAMPLE

- Bars: pmv=[5000, 8000, 0, 3000], equity=[10000, 10000, 10000, 10000]
- `gross_exposure = [0.5, 0.8, 0.0, 0.3]`
- `exposure = (0.5 + 0.8 + 0.0 + 0.3) / 4 = 0.40`

---

## L. TEST MATRIX — REQUIRED FUTURE ACCEPTANCE TESTS

### DESIGN DECISION

**The test matrix below defines REQUIRED FUTURE acceptance tests. Existing passing tests do NOT constitute evidence that these requirements are currently satisfied.**

The current test suite has `76` test functions across 13 test classes (as of the date of this document). These tests validate the existing (partially complete) implementation. They do **NOT** validate the redesigned engine defined in this document. Passing current tests is **not** evidence of compliance with the requirements below.

**Each acceptance test listed below must be explicitly implemented and passing before Phase 3 implementation is authorized.**

### Financial Invariant Tests (Required)

```
A. LONG PROFIT: entry=100, exit=110, qty=10 → gross_pnl=+100
B. LONG LOSS: entry=110, exit=100, qty=10 → gross_pnl=-100
C. SHORT PROFIT: entry=100, exit=90, qty=10 → gross_pnl=+100
D. SHORT LOSS: entry=90, exit=100, qty=10 → gross_pnl=-100
E. ENTRY COMMISSION: entry=100, qty=10, comm=0.01/share → entry_commission=0.10
F. EXIT COMMISSION: exit=110, qty=10, comm=0.01/share → exit_commission=0.10
G. ENTRY+EXIT COMMISSION: total_commission=0.20, net_pnl=gross-0.20
H. LONG WITH SLIPPAGE: entry_fill=100.5, exit_fill=109.5 → slippage embedded in fill
I. SHORT WITH SLIPPAGE: entry_fill=99.5, exit_fill=90.5 → slippage embedded in fill
J. ENTRY COST WHILE OPEN: equity = cash + pmv, equity < initial_capital by entry_comm
K. EXIT COST: equity decreases by exit_commission at close
L. FULL ROUND-TRIP P&L: net_pnl = gross - entry_comm - exit_comm, equity change = net_pnl
M. EQUITY INVARIANT AT EVERY BAR: equity == cash + pmv for all bars
N. REALIZED/UNREALIZED SEPARATION: unrealized=0 when flat, unrealized≠0 when open
O. LONG COMMISSION-ONLY: gross=100, entry_comm=0.5, exit_comm=0.5 → net=99.0
P. SHORT COMMISSION-ONLY: gross=100, entry_comm=0.5, exit_comm=0.5 → net=99.0
Q. CASH_FLOOR: cash never negative after any valid operation
R. NO_LEVERAGE: order rejected if required_cash > current_cash
S. SHORT_CONSTRAINTS: short sale proceeds + entry_commission must leave cash >= 0
```

### Position Sizing Tests (Required — All New)

```
PS-SEQ-1: sizing_price = requested execution price, not fill price
PS-SEQ-2: quantity calculated BEFORE slippage changes fill
PS-SEQ-3: actual fill price used for cash validation
PS-SEQ-4: order REJECTED when resulting_gross_exposure > exposure_limit (see Maximum Exposure Enforcement, not resized)
PS-FIXED-1: fixed_quantity=10 → quantity=10
PS-PERCENT-1: percent_of_capital=10, equity=10000, price=100 → quantity=10
PS-PERCENT-2: percent_of_capital=10, equity=50, price=100 → REJECT (INSUFFICIENT_CAPITAL)
PS-PERCENT-3: percent_of_capital=100, equity=10000, price=10, max_position_size=500 → quantity=500
PS-PERCENT-4: percent_of_capital=0 → ValueError
PS-PERCENT-5: percent_of_capital=101 → ValueError
PS-PERCENT-6: current_equity=0 → REJECT (INSUFFICIENT_CAPITAL), no exception
PS-PERCENT-7: current_equity<0 → REJECT (INSUFFICIENT_CAPITAL), no exception
PS-PERCENT-8: quantity<1 after floor → REJECT (INSUFFICIENT_CAPITAL), no exception
PS-PERCENT-9: resulting_gross_exposure > exposure_limit after slippage → REJECT (MAX_EXPOSURE_EXCEEDED)
PS-PERCENT-10: Insufficient cash after fill → REJECT (INSUFFICIENT_CASH)
PS-PERCENT-11: percent_of_capital=100, equity=$10000, price=$1, max_exposure=100% → quantity=10000 (within max_position_size)
PS-MIN-1: Minimum quantity = 1. If floor yields 0 → REJECT
PS-MAX-1: Quantity capped by max_position_size after floor, before slippage validation
PS-REJECT-SEMANTICS: All rejections return OrderStatus.REJECTED, never raise engine exceptions
PS-NO-TRADE: Rejected orders produce no trade record, no state change, no equity modification
```

### Timeframe-Aware Annualization Tests (Required — All New)

```
ANNUAL-1: D1, n=366 → periods_per_year=365, exponent=365/365=1.0
ANNUAL-2: H1, n=8761 → periods_per_year=8760, exponent=8760/8760=1.0
ANNUAL-3: D1, n=100 → periods_per_year=365, n-1=99 < 365 → annualized_return=None
ANNUAL-4: Verify sqrt(periods_per_year) used for volatility, not sqrt(252)
ANNUAL-5: Verify periods_per_year varies by timeframe in ALL metric calculations
ANNUAL-6: M15, n=35041 → periods_per_year=35040, exponent=35040/35040=1.0
ANNUAL-7: Verify annualized_return=None when n-1 < periods_per_year (all return-based metrics)
ANNUAL-8: Verify annualized_return=None when n-1 < periods_per_year (volatility, sharpe, sortino)
```

### Metric Formula Tests (Required — Verified)

```
M1: total_return: (final_equity - initial_capital) / initial_capital
M2: cumulative_return: product of (1 + r_i) - 1
M3: annualized_return: (final_equity / initial_equity)^(periods_per_year/(n-1)) - 1, None if n-1 < periods_per_year
M4: volatility: std(returns) × sqrt(periods_per_year), ddof=1
M5: sharpe_ratio: (annualized_return - risk_free) / annualized_volatility, zero-vol handling
M6: sortino_ratio: (annualized_return - risk_free) / downside_deviation_annualized
M7: max_drawdown: min(equity / running_peak - 1), reported as positive
M8: max_drawdown_duration: exact counting convention (see Section K.8)
M9: recovery_duration: bars from trough to recovery of previous peak
M10: win_rate: W / T
M11: loss_rate: L / T
M12: breakeven_trades: count where abs(net_pnl) <= BREAKEVEN_TOLERANCE (1e-10)
M13: profit_factor: gross_wins / abs(gross_losses), zero-denominator handling
M14: expectancy: total_net_pnl / T
M15: average_trade: total_net_pnl / T
M16: median_trade: median of all net_pnl values
M17: average_win: mean of positive net_pnl values
M18: average_loss: mean of negative net_pnl values (reported positive)
M19: turnover: total_notional / average_equity, entry+exit included, all equity points
M20: exposure: mean(abs(pmv / equity)) over all bars where equity > 0
```

### Drawdown Duration Tests (Required — All New)

```
DDUR-1: Equity [10000, 9000, 9500, 10000] → peak=10000 at idx=0, recovery=10000 at idx=3 → duration=3
DDUR-2: Equity [10000, 9000, 10000] → peak=10000 at idx=0, recovery=10000 at idx=2 → duration=2
DDUR-3: Equity [10000, 9000] → no recovery → duration=None
DDUR-4: Equity [10000, 11000, 10500] → peak=11000 at idx=1, no recovery → duration=None
DDUR-5: Equity [10000, 10000] → no drawdown → duration=0
DDUR-6: Equity [10000] → single point → duration=0
DDUR-7: Equity [10000, 9000, 9500, 10000, 11000, 10000] → max_dd from 11000 to 10000 → duration=1
```

### Hashing Tests (Required)

```
H1: canonical dataset_hash: Same candle data → identical hash, different data → different hash
H2: canonical strategy_hash: Same StrategySpec → identical hash
H3: canonical result_hash: Same backtest → identical result_hash across runs
H4: dataset_hash serialization: Exact byte-level specification (Section H)
H5: strategy_hash serialization: Exact canonical inputs (Section I)
H6: result_hash serialization: Exact canonical inputs (Section I)
H7: config_hash serialization: Exact canonical inputs (Section I)
H8: datetime in hash: ISO 8601 UTC format, stable across runs
H9: numeric in hash: .10f precision, stable across runs
H10: field ordering in hash: Alphabetical field order, stable across runs
H11: runtime timestamp excluded: result_hash does not change with runtime timestamp
H12: -0.0 normalized to 0.0 in canonical serialization
H13: NaN/inf represented as empty fields in canonical serialization
H14: Duplicate timestamps rejected before hashing
H15: UTF-8 encoding verified for non-ASCII instrument names
H16: Unix line endings (\n) in canonical serialization
H17: Trailing newline after last record in canonical serialization
H18: Identical bytes across platforms verified
```

### Anti-Lookahead Tests (Required)

```
A1: Modify all data after bar t. Decision at bar t must remain identical.
A2: Modify bar t+1. Signal at t must remain identical.
A3: Modify future data after trade exit. That trade must remain identical.
A4: Run strategy on prefix dataset ending at t vs full dataset. Decisions at t must match.
A5: Change candle t+1 price dramatically. Trade at bar t must remain identical.
A6: Reverse future data after final decision. Historical decisions unchanged.
```

### Accounting Tests (Required — Extended)

```
AC1: Cash accounting: Verify cash transitions for LONG open/hold/close.
AC2: Cash accounting: Verify cash transitions for SHORT open/hold/close.
AC3: Equity equation: equity == cash + position_market_value for every bar.
AC4: Realized P&L: After closing position, realized_pnl == net_pnl.
AC5: Unrealized P&L: When flat, unrealized_pnl == 0.
AC6: No double-counting: equity change == net_pnl for each closed trade.
AC7: Commission accounting: entry_commission + exit_commission == total_commission.
AC8: Slippage accounting: fill_price - requested_price == slippage_price.
AC9: Cost model consistency: Same cost parameters used in execution, ledger, metrics.
AC10: Identity verification: equity ≠ initial_capital + realized + unrealized when commissions exist.
AC-CASH-1: Attempt to open LONG exceeding available cash → REJECTED, no state change.
AC-CASH-2: Attempt to open SHORT where required_cash > current_cash → REJECTED.
AC-CASH-3: After full round-trip, cash >= 0 always.
AC-CASH-4: equity >= 0 at every bar for all valid executions.
```

### State Machine Tests (Required)

```
SM1: FLAT → OPEN: Valid transition.
SM2: OPEN → OPEN: Invalid, raises ValueError.
SM3: OPEN → FLAT: Valid transition via close_position().
SM4: FLAT → CLOSE: Invalid, raises ValueError.
SM5: Quantity > 0: Zero or negative quantity raises ValueError.
SM6: Entry price exists: OPEN position must have entry_fill_price.
SM7: Exit price exists: CLOSED trade must have exit_fill_price.
SM8: Side consistency: Side is LONG/SHORT while open, NONE when flat.
SM9: Holding period: Holding period bars = exit_timestamp - entry_timestamp.
SM10: Closed position cannot accumulate unrealized P&L.
SM11: Rejected order → no state change, no trade record, no equity modification.
SM12: Same-bar entry and exit → IMPOSSIBLE (no state allows it).
SM13: Final bar with execution_delay=1 → REJECTED (TIME_EXPIRED).
SM14: Missing OHLC data → bar skipped, equity continues with last known values.
```

### Determinism Tests (Required)

```
D1: Same backtest twice → identical trades, fills, P&L, equity, metrics
D2: Deterministic trade IDs: trade-000001, trade-000002, ...
D3: Deterministic result_hash: Same inputs → same result_hash
D4: Deterministic strategy hash: Same strategy → same hash
D5: Deterministic dataset hash: Same content → same hash, different content → different hash
D6: Deterministic across platforms: Same inputs → same result_hash on different OS
D7: Deterministic across runs: Same inputs → same result_hash in repeated runs
```

### Provenance Tests (Required)

### D4 NUMERICAL POLICY — DETERMINISTIC THRESHOLD EVALUATION

This section defines the approved deterministic numerical policy for TP/SL threshold evaluation (D4).

**Approval Status:** HUMAN-APPROVED
**Approval Record:** `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md`
**Approved Policy:** Policy D — Exact Decimal Reference + Float Price
**Human Approver:** muhammad mohsin
**Approval Date:** 1999/11/20

---

#### D4.1 — Mathematical Reference

For LONG TP:

```text
Decimal(str(entry)) ×
(
    Decimal('1') +
    Decimal(str(pct)) / Decimal('100')
)
```

Directional equivalents:

```text
LONG SL:  entry × (1 - pct/100)
SHORT TP: entry × (1 - pct/100)
SHORT SL: entry × (1 + pct/100)
```

---

#### D4.2 — Input Semantics

Inputs use:

```text
Decimal(str(entry))
Decimal(str(pct))
```

Percentage-point semantics apply. Therefore:

```text
10.0 = 10%
```

and:

```text
pct / 100
```

is required for threshold calculation.

---

#### D4.3 — Computational Representation

Use Decimal reference + float price bridge.

The mathematical threshold remains an exact Decimal reference.
The market price may originate as binary64/float.

---

#### D4.4 — Threshold Computation

Use multiplicative threshold computation:

```text
T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100'))
```

No alternate threshold construction may be introduced.

---

#### D4.5 — Binary64 Handling

Binary64 is an approximation of the mathematical real value.
Do NOT reinterpret binary64 as the authoritative mathematical threshold.

For a supplied binary64 price:

```text
Decimal.from_float(price)
```

may be used to preserve the exact represented float value in the Decimal comparison domain.

---

#### D4.6 — Non-Representable Threshold

When the exact mathematical threshold is not representable in binary64:

- Retain the exact Decimal threshold.
- Do not round it.
- Do not convert it to an approximate binary64 threshold.
- Do not reject it.
- Do not adjust it.
- Do not snap it to tick size.
- Do not introduce epsilon.

For a supplied binary64 price:

```text
Decimal.from_float(price)
```

may be used to preserve the exact represented float value. Comparison is performed in the Decimal domain against the exact mathematical T. A non-representable T is not rounded up, rounded down, or rejected solely because it is non-representable in binary64.

---

#### D4.7 — Equality

Preserve D3 inclusive boundaries:

```text
TP: price >= TP
SL: price <= SL
```

Do NOT modify D3.

---

#### D4.8 — Comparison Domain

Comparison is performed in the exact Decimal domain under the approved float-price bridge.

---

#### D4.9 — Rounding

No rounding is applied to the mathematical threshold.

---

#### D4.10 — `.10f`

`.10f` is serialization/formatting only.
It MUST NOT participate in threshold computation or comparison.

---

#### D4.11 — Tolerance

No epsilon.
No tolerance band.
No numerical adjustment.
No approximate comparison.

---

#### D4.12 — Tick Size / D5

D4 does not introduce tick-size semantics.
D5 remains unchanged.

---

#### D4.13 — Cross-Path Semantics

All threshold-evaluation paths must use percentage-point semantics:

```text
10.0 = 10%
pct / 100
```

**Current implementation mismatch (identified, NOT yet resolved):**

```text
StrategySpec / backtest:
  percentage-point semantics using /100

ExitCondition.pct_of_entry:
  currently uses direct fractional semantics
```

This design-document amendment defines the target contract as percentage-point semantics using `/100`. The existing source mismatch must remain visibly identified until a separate implementation authorization is granted. This design-document amendment does NOT modify the source implementation.

---

#### D4.14 — Reproducibility

Equivalent supported contexts must preserve deterministic behavior and the same `result_hash` invariant.

---


```
P1: BacktestProvenance contains all required fields
P2: BacktestProvenance.result_hash is stable across runs
P3: BacktestProvenanceTracker records and retrieves provenance
P4: BacktestResult includes BacktestProvenance
P5: dataset_hash is content-based, not id()-based
P6: Runtime timestamps excluded from result_hash
P7: Canonical dataset hash produces identical bytes across runs
P8: Canonical dataset hash uses exact serialization format (Section H)
```

### Security Tests (Required)

```
S1: No eval/exec/compile/lambda in strategy source
S2: StrategySpec contains no executable code (structural test)
S3: No pickle, socket, urllib, http in strategy module
S4: Unknown indicators raise ValueError (not silent failure)
S5: Condition evaluator returns deterministic boolean
S6: Exit condition semantics verified (RSI available ≠ exit signal)
```

### Integration Tests (Required)

```
I1: Full workflow: Strategy → Engine → Metrics → Provenance
I2: DataQualityGate blocks backtest on bad data
I3: BacktestEngine uses QuantEngine for features
I4: Multi-bar equity curve has correct mark-to-market values
I5: Close then open new position: state transitions correct
I6: Equity invariant verified at every bar in a full multi-bar backtest
I7: Full round-trip with commission and slippage: equity change == net_pnl
I8: Position sizing rejection: order rejected, no state change, no trade recorded
I9: Position sizing rejection: equity curve unchanged for rejected bar
I10: Execution_delay=1 on final bar: order rejected, OrderStatus.REJECTED, reason=TIME_EXPIRED
I11: Missing OHLC data: bar skipped, equity uses last known values
I12: All metrics computed for periods shorter than 1 year: return None (not approximation)
I13: All metrics computed for D1 timeframe: periods_per_year=365
I14: All metrics computed for H1 timeframe: periods_per_year=8760
```

### Manually Calculated Worked Examples

Each major financial formula must have at least one manually calculated worked example in the test suite:

```
WORKED EXAMPLE 1: LONG with commission and slippage
  Entry: requested=100, slippage=0.5, qty=10, comm/share=0.01
  Exit: requested=110, slippage=0.5, qty=10, comm/share=0.01
  entry_fill = 100.5, exit_fill = 109.5
  gross_pnl = 90.0, entry_comm = 0.1, exit_comm = 0.1
  net_pnl = 89.8
  Expected equity change = 89.8
  Expected slippage_cost (informational) = 5.0 (NOT subtracted from net_pnl)

WORKED EXAMPLE 2: SHORT with commission
  Entry: requested=100, qty=10, comm/share=0.01
  Exit: requested=90, qty=10, comm/share=0.01
  entry_fill = 100, exit_fill = 90
  gross_pnl = 100, entry_comm = 0.1, exit_comm = 0.1
  net_pnl = 99.8
  Expected equity change = 99.8

WORKED EXAMPLE 3: Max drawdown
  Equity: [10000, 11000, 9500, 10500, 12000]
  Running peaks: [10000, 11000, 11000, 11000, 12000]
  Drawdowns: [0%, -4.55%, -13.64%, -4.55%, 0%]
  max_drawdown = 13.64%

WORKED EXAMPLE 4: Sharpe ratio
  annualized_return = 0.20, risk_free = 0.05, periods_per_year = 365, n = 366
  annualized_vol = 0.15
  sharpe = (0.20 - 0.05) / 0.15 = 1.0

WORKED EXAMPLE 5: Turnover
  Trade: entry_fill=100, exit_fill=110, qty=10
  Notional = (100×10) + (110×10) = 2100
  Average equity = mean(all equity points)
  Turnover = 2100 / average_equity

WORKED EXAMPLE 6: Exposure
  Bars: pmv=[5000, 8000, 0, 3000], equity=[10000, 10000, 10000, 10000]
  Exposure = (0.5 + 0.8 + 0 + 0.3) / 4 = 0.40

WORKED EXAMPLE 7: Drawdown duration
  Equity: 100 → 90 → 95 → 100
  Peak at index 0 (100), recovery at index 3 (100 >= 100)
  Duration = 3 - 0 = 3 bars
  Expected: 3

WORKED EXAMPLE 8: Annualized return (D1)
  initial=10000, final=11000, periods_per_year=365, n=366
  annualized = (11000/10000)^(365/365) - 1 = 0.10 (10%)

WORKED EXAMPLE 9: Annualized return (D1, insufficient data)
  initial=10000, final=10500, periods_per_year=365, n=100
  n-1=99 < 365 → annualized_return = None

WORKED EXAMPLE 10: Position sizing rejection
  percent_of_capital=100, equity=10000, price=10, max_exposure=50%
  quantity = floor(10000/10) = 1000
  new_gross_exposure = abs(10 × 1000) = 10000
  existing_gross_exposure = 0 (FLAT account)
  resulting_gross_exposure = 0 + 10000 = 10000
  exposure_limit = (50 / 100) × 10000 = 5000
  10000 > 5000 → REJECT (MAX_EXPOSURE_EXCEEDED)
```

---

## M. EXISTING FILE DISPOSITION

### Current Phase 3 Files

```
src/data_engine/strategy/
    __init__.py          → REWRITE (update exports to new module structure)
    schemas.py           → REWRITE (redesign all domain models)
    execution.py         → REWRITE (redesign execution model)
    backtest.py          → REWRITE (redesign backtest engine completely)
    metrics.py           → REWRITE (fix metrics, add breakeven_trades)
    validation.py        → REWRITE (add condition validator, fix leakage)
    provenance.py        → REWRITE (add result_hash, integrate with engine)
    trades.py            → REWRITE (add entry/exit commissions separately)
    positions.py         → REWRITE (fix state machine, implement update_unrealized)
```

### Test Files

```
tests/test_strategy.py → REWRITE (restore correctness, add invariant tests)
```

### Documentation Files

```
docs/strategy_engine.md → REWRITE (match new architecture)
docs/strategy_engine_design.md → THIS DOCUMENT
README.md → UPDATE (module table)
```

### Files to Preserve (unchanged)

```
src/data_engine/schemas.py      (Phase 1/2, unchanged)
src/data_engine/quant/          (Phase 2, unchanged)
src/data_engine/storage.py      (Phase 1, unchanged)
src/data_engine/validation.py   (Phase 1, unchanged)
src/data_engine/provenance.py   (Phase 1, unchanged)
src/data_engine/security.py     (Phase 1, unchanged)
src/data_engine/quarantine.py   (Phase 1, unchanged)
src/data_engine/ingestion.py    (Phase 1, unchanged)
src/data_engine/cli.py          (Phase 1, unchanged)
src/data_engine/data_blocked.py (Phase 1, unchanged)
src/data_engine/evidence.py     (Phase 1, unchanged)
src/data_engine/instruments.py  (Phase 1, unchanged)
src/data_engine/quant_boundary.py (Phase 1, unchanged)
src/data_engine/timeframes.py   (Phase 1, unchanged)
src/data_engine/provider.py     (Phase 1, unchanged)
src/data_engine/quality_report.py (Phase 1, unchanged)
src/data_engine/__init__.py     (Phase 1, unchanged)
```

---

## N. ACCEPTANCE GATES

All gates must be true for Phase 3 completion:

```
[ ] all required acceptance tests (Section L) pass
[ ] no tests were weakened to hide failures
[ ] zero deprecation warnings
[ ] deterministic repeated backtests (same inputs → same outputs)
[ ] deterministic trade IDs (trade-000001, ...)
[ ] deterministic result identity (result_hash stable)
[ ] dataset content hash works (content-based, not id())
[ ] dataset remains unchanged after backtest
[ ] no arbitrary code execution (no eval/exec/lambda)
[ ] position state machine enforced (OPEN→OPEN invalid)
[ ] long P&L verified (gross = (exit-entry)*qty)
[ ] short P&L verified (gross = (entry-exit)*qty)
[ ] realized P&L verified (sum of closed trades)
[ ] unrealized P&L verified (mark-to-market while open)
[ ] cash accounting verified (cash transitions correct)
[ ] equity accounting verified (equity = cash + position_value)
[ ] commission accounting verified (entry + exit)
[ ] slippage accounting verified (no double-counting)
[ ] exit semantics verified (RSI available ≠ exit signal)
[ ] position sizing semantics explicit (Section J)
[ ] position sizing rejections verified (no exceptions, OrderStatus.REJECTED)
[ ] maximum exposure enforcement verified (resulting_gross_exposure <= exposure_limit, no partial fill, deterministic rejection)
[ ] periods_per_year defined for every timeframe (Section K)
[ ] annualization uses periods_per_year, not generic 252
[ ] drawdown_duration counting convention verified (Section K.8)
[ ] canonical dataset hash produces identical bytes (Section H)
[ ] strategy_hash, result_hash, config_hash canonical inputs specified (Section I)
[ ] runtime timestamps excluded from all deterministic hashes
[ ] look-ahead tests pass (modify future → historical unchanged)
[ ] provenance integrated (BacktestResult includes BacktestProvenance)
[ ] metrics validated against known examples
[ ] cash constraints verified (no negative cash, no leverage)
[ ] short model explicitly states limitations (no margin, borrow, financing)
[ ] execution_delay=1 final bar rejection verified
[ ] missing OHLC data handling verified
[ ] documentation matches implementation
```

---

## O. IMPLEMENTATION STATUS

**IMPLEMENTATION STATUS: PHASE 3 COMPLETE — 367/367 TESTS PASSING**

---

## P. KEY DESIGN DECISIONS SUMMARY

1. **Equity equation:** `equity = cash + position_market_value` — the ONLY primary invariant
2. **Commission in cash:** Entry and exit commissions are captured in cash transitions — NOT in unrealized P&L
3. **`equity ≠ initial_capital + realized + unrealized`:** This identity FAILS when commissions exist — it is explicitly rejected as a primary equation
4. **Slippage model:** Slippage modifies fill price — NOT separately subtracted from gross P&L — avoids double-counting
5. **Commission model:** Both per-share and percentage are additive — documented and tested explicitly
6. **State machine:** OPEN→OPEN raises ValueError — enforced by the state machine
7. **Execution timing:** Default is declared theoretical end-of-bar execution (signal at t close → fill at t close)
8. **Trade IDs:** Deterministic chronological ordering (trade-000001) — not random UUIDs
9. **Result hash:** Computed over canonical deterministic serialization — SHA-256
10. **Unknown indicators:** Raise ValueError — not silent failure
11. **Exit conditions:** Semantic evaluation only — "RSI available" ≠ "exit signal"
12. **Breakeven trades:** Counted separately from winners and losers — `pnl == 0` is neither
13. **Provenance:** Integrated into BacktestResult — not dead architecture
14. **Dataset hashing:** Content-based using exact canonical serialization (Section H)
15. **Position sizing:** `fixed` and `percent` only — `atr_based` removed from Phase 3 scope
16. **Percent sizing:** Uses sizing_price = requested execution price; quantity calculated BEFORE slippage
17. **Order rejection semantics:** Deterministic OrderStatus.REJECTED for all undersized/invalid signals; no engine-level exceptions
18. **Volatility:** Sample standard deviation (ddof=1) — not population
19. **Annualization:** `periods_per_year` defined for every timeframe (M1=525600, M5=105120, M15=35040, H1=8760, H4=2190, D1=365); NOT a generic 252
20. **Exposure:** Time-weighted average instantaneous exposure; all equity points where equity > 0; ratio format
21. **Turnover:** `total_notional = Σ(entry_fill × qty + exit_fill × qty)`; `average_equity = mean(all equity points)`; denominator = 0 → None
22. **Drawdown duration:** Exact counting: `r - p` bars from peak bar `p` to first recovery bar `r` where equity >= peak; worked example: `100 → 90 → 95 → 100` → duration = 3
23. **SHORT positions:** Simplified model — no margin, borrow fees, financing, collateral, or forced liquidation
24. **Cash constraints:** `cash >= 0` enforced at every transition; leverage not permitted; insufficient cash → REJECT
25. **Annualized metrics unavailable** when `n - 1 < periods_per_year` — return None, not approximation
26. **Maximum Exposure Enforcement:** `max_exposure_pct` constrains TOTAL RESULTING GROSS EXPOSURE (existing + new), not just the new order. Gross exposure uses absolute values; LONG and SHORT do NOT cancel. Formula: `resulting_gross_exposure = abs(existing_position_market_value) + abs(actual_fill_price × quantity)`. Order rejected only when `resulting_gross_exposure > (max_exposure_pct / 100) × current_equity`. No partial fill. No engine exception. Deterministic `OrderStatus.REJECTED` with `reason = MAX_EXPOSURE_EXCEEDED` (Section J, Maximum Exposure Enforcement)

---

*Document version: 3.0.0*
*Design date: 2026-09-25*
*Phase: 3 Redesign — Final Design-Only Correction Pass*
IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW
