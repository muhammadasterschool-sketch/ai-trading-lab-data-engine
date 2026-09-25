# PHASE 3 — BLOCKER #2
# DESIGN AMENDMENT DRAFT

## 1. Current Locked Design

* **Current design SHA:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`
* **Design status:** The locked design document `docs/strategy_engine_design.md` remains completely unchanged. This draft proposes normative additions for future human approval.
* **Current blocker:** TP/SL floating-point boundary semantics and percentage-unit ambiguity.
  * `entry_fill_price=100.0, take_profit_pct=10.0` computes threshold as `110.00000000000001` in IEEE-754, causing `110.0 >= 110.00000000000001` to evaluate `False`.
  * `ExitCondition.pct_of_entry` uses fractional units (`0.1 = 10%`) while `StrategySpec.take_profit_pct` uses percentage points (`10.0 = 10%`). The design does not define which unit is canonical.
  * The locked design has NO section defining exit threshold computation formulas, comparison operators, boundary equality semantics, or floating-point policies for price comparisons.

---

## 2. Approved Human Decisions

### D1 — Canonical Percentage Unit
Use **percentage points** consistently: `10.0 = 10%`, `0.10 = 0.1%`.
Applies to: `StrategySpec.stop_loss_pct`, `StrategySpec.take_profit_pct`, `ExitCondition.pct_of_entry`.

### D2 — Normative TP/SL Formula
Percentages are of the **actual entry fill price**.
* LONG TP: `entry_fill_price * (1 + take_profit_pct / 100)`
* LONG SL: `entry_fill_price * (1 - stop_loss_pct / 100)`
* SHORT TP: `entry_fill_price * (1 - take_profit_pct / 100)`
* SHORT SL: `entry_fill_price * (1 + stop_loss_pct / 100)`
`entry_fill_price` means the actual executed entry fill price, including applicable execution slippage.

### D3 — Boundary Semantics
Exact mathematical threshold equality MUST trigger the corresponding exit.
* LONG TP: `price >= TP_threshold` (inclusive)
* LONG SL: `price <= SL_threshold` (inclusive)
* SHORT TP: `price <= TP_threshold` (inclusive)
* SHORT SL: `price >= SL_threshold` (inclusive)
LONG/SHORT symmetry is mandatory. All four directions tested independently.

### D4 — Floating-Point Policy
Must define a deterministic numerical policy guaranteeing:
1. Mathematically exact boundary equality triggers.
2. Immediately-below values do not trigger.
3. Immediately-above values trigger.
4. LONG/SHORT symmetric.
5. Repeated runs produce identical results.
6. Explicitly testable.
7. No arbitrary tolerance introduced solely to make existing tests pass.
If more than one mechanism is viable, it is marked **HUMAN APPROVAL REQUIRED**.

### D5 — Tick / Price Precision
Do NOT introduce tick_size, price_precision, pip size, or instrument precision metadata into Phase 3. The chosen numerical policy must operate using the existing Phase 3 data model. If the policy genuinely requires new metadata, report `DESIGN EXPANSION REQUIRED — HUMAN APPROVAL REQUIRED`.

### D6 — Cross-Path Consistency
`StrategySpec.stop_loss_pct`/`take_profit_pct` and `ExitCondition.pct_of_entry` must use the same canonical percentage-point convention (`10.0 = 10%`). Percentage/fraction ambiguity is prohibited.

### D7 — Determinism
Same dataset + same strategy + same configuration + same implementation version must produce identical exit decisions, trades, equity curve, metrics, and `result_hash`.

---

## 3. Proposed Normative Amendments

### Amendment 3.1 — Percentage Unit Definition

* **Existing design location:** Section containing `StrategySpec` definition and config_hash field ordering (line 681).
* **Current wording:** `stop_loss_pct|take_profit_pct` listed as fields in `config_hash` ordering with no unit specification.
* **Proposed replacement/addition:**

```
All percentage fields in the design use percentage points as the canonical unit.
10.0 means ten percent (10%). 0.10 means one-tenth of one percent (0.1%).

The following fields MUST use percentage points:
- StrategySpec.stop_loss_pct
- StrategySpec.take_profit_pct
- ExitCondition.pct_of_entry

Implementations MUST NOT interpret pct_of_entry as a fractional ratio
(where 0.1 = 10%). The unit must be explicitly percentage points throughout
all validation, serialization, hashing, and runtime computation paths.
```

* **Rationale:** The current implementation uses `10.0` for StrategySpec and `0.1` for ExitCondition, creating ambiguity that propagates to test fixtures, validation rules, and serialization. A single canonical unit eliminates this class of errors.
* **Affected implementation components:** `StrategySpec` schema, `ExitCondition` schema, `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, validation rules, test fixtures, `config_hash` computation.
* **Affected tests:** All test fixtures using percentage exit parameters must use percentage-point convention.

### Amendment 3.2 — Normative Formula Definition

* **Existing design location:** No formula section exists. The design lists `stop_loss_pct` and `take_profit_pct` as fields without computational semantics.
* **Current wording:** (Absent — no formula defined)
* **Proposed addition:**

```
**Take-Profit and Stop-Loss Threshold Calculation**

Percentage-based exit thresholds are computed from the actual entry fill price
as a percentage of that fill price.

For a LONG position with entry fill price E, take-profit percentage TP, and
stop-loss percentage SL:
  take_profit_threshold = E × (1 + TP / 100)
  stop_loss_threshold    = E × (1 - SL / 100)

For a SHORT position with entry fill price E, take-profit percentage TP, and
stop-loss percentage SL:
  take_profit_threshold = E × (1 - TP / 100)
  stop_loss_threshold    = E × (1 + SL / 100)

entry_fill_price is the actual executed fill price, including applicable
execution slippage as computed by the ExecutionModel. It MUST NOT be
substituted with signal price, requested execution price, candle close,
or any theoretical price when an actual fill exists.

These computations use Python's native float type (IEEE-754 binary64).
The numerical boundary policy defined in Section [Floating-Point Policy]
governs how thresholds are compared against close prices.
```

* **Rationale:** The formula is currently implemented only in `_check_exit_conditions()` and `ExitCondition.evaluate()` without design authorization. Both code paths must follow the same formula. The `entry_fill_price` requirement prevents silent substitution with signal or close prices.
* **Affected implementation components:** `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, `StrategySpec` schema, `ExecutionModel`, all exit-related test fixtures.
* **Affected tests:** Boundary test vectors must use `entry_fill_price` semantics.

### Amendment 3.3 — Boundary Inclusion Requirement

* **Existing design location:** EDGE CASES section (lines 392-401) covers execution timing only.
* **Current wording:** (Absent — no boundary equality specification)
* **Proposed addition:**

```
**Exit Boundary Semantics**

At the mathematically exact boundary (i.e., when the close price equals the
threshold computed in exact real arithmetic), the corresponding exit condition
MUST trigger.

For all four exit directions, boundary equality is INCLUSIVE:
- LONG take-profit:  close_price >= take_profit_threshold  (equality triggers)
- LONG stop-loss:    close_price <= stop_loss_threshold    (equality triggers)
- SHORT take-profit: close_price <= take_profit_threshold  (equality triggers)
- SHORT stop-loss:   close_price >= stop_loss_threshold    (equality triggers)

LONG and SHORT semantics MUST be symmetric. If LONG TP uses inclusive comparison,
SHORT SL MUST also use inclusive comparison, and vice versa.

The numerical boundary policy (Section [Floating-Point Policy]) must guarantee
that IEEE-754 representation does not prevent boundary-triggering.
```

* **Rationale:** The current implementation uses `>=` and `<=` operators (inclusive by syntax), but IEEE-754 representation causes `100.0 * 1.1 = 110.00000000000001`, making `110.0 >= 110.00000000000001` evaluate `False`. The design must explicitly require inclusive semantics and mandate a numerical policy that ensures they hold in practice.
* **Affected implementation components:** `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, all exit comparison logic, regression test boundary vectors.
* **Affected tests:** Four independent boundary tests (LONG TP, LONG SL, SHORT TP, SHORT SL).

### Amendment 3.4 — Floating-Point Policy

* **Existing design location:** No floating-point policy for exit comparisons exists. The design has `equity == cash + position_market_value (within floating-point tolerance)` (line 99) and `BREAKEVEN_TOLERANCE = 1e-10` (line 1453), both scoped to non-exit contexts.
* **Current wording:** (Absent — no policy defined)
* **Proposed addition:**

```
**Floating-Point Policy for Exit Evaluation**

All take-profit and stop-loss threshold calculations and comparisons use
Python's native float type (IEEE-754 binary64).

The design must specify exactly ONE of the following numerical policies.
The policy MUST guarantee that mathematically exact boundary equality triggers,
immediately-below values do not trigger, immediately-above values trigger,
and LONG/SHORT symmetry holds.

POLICY OPTION A — Additive Threshold Reformulation

Compute the threshold using additive arithmetic instead of multiplicative:

LONG TP:   threshold = entry_fill_price + entry_fill_price * take_profit_pct / 100
LONG SL:   threshold = entry_fill_price - entry_fill_price * stop_loss_pct / 100
SHORT TP:  threshold = entry_fill_price - entry_fill_price * take_profit_pct / 100
SHORT SL:  threshold = entry_fill_price + entry_fill_price * stop_loss_pct / 100

Comparison uses raw >= and <= operators on the computed threshold and close_price.

HUMAN APPROVAL REQUIRED: This policy must be verified to produce exact boundary
triggering for all entry prices and percentages within the supported range,
or the design must specify a bounded verification scope.

POLICY OPTION B — Canonical Float Normalization

Compute the threshold using any deterministic formula, then normalize it by
rounding to the canonical float representation defined by the existing
condition_serialization convention (.10f formatting from line 751):

threshold_normalized = float(f"{threshold:.10f}")

Comparison uses raw >= and <= operators on threshold_normalized and close_price.

HUMAN APPROVAL REQUIRED: This policy extends an existing design convention
(.10f serialization) to runtime comparison. The design must explicitly state
that .10f normalization is the canonical float representation for both
serialization and comparison purposes.

POLICY OPTION C — Explicit Deterministic Mechanism

[If the human reviewer identifies a third mechanism, it must be specified here
with the same guarantee requirements and HUMAN APPROVAL REQUIRED marker.]

The design MUST NOT:
- Use an arbitrary tolerance value to force boundary-triggering.
- Use math.isclose() unless the tolerance is explicitly defined by the design.
- Use Decimal arithmetic unless explicitly required by the chosen policy.
- Use instrument tick-size normalization (see D5).
- Silently choose between Policy Options A and B without explicit human approval.
```

* **Rationale:** The current implementation uses multiplicative threshold computation (`entry * (1 + pct/100)`) which produces `110.00000000000001` instead of `110.0` for `entry=100.0, pct=10.0`. Both the additive reformulation and the `.10f` normalization (which the design already mandates for serialization, line 637) resolve this for tested cases, but neither has been proven to cover all possible inputs. The design must require explicit human choice between viable mechanisms.
* **Affected implementation components:** `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, potentially all threshold computation in the strategy module.
* **Affected tests:** All boundary test vectors must verify the chosen policy produces correct triggering.

### Amendment 3.5 — Cross-Path Unit Consistency Contract

* **Existing design location:** `config_hash` field ordering (line 680-690) lists both `stop_loss_pct|take_profit_pct` and `exit_conditions_serialized` as separate fields.
* **Current wording:** No relationship defined between the two paths.
* **Proposed addition:**

```
**StrategySpec / ExitCondition Cross-Path Contract**

StrategySpec.stop_loss_pct, StrategySpec.take_profit_pct, and
ExitCondition.pct_of_entry MUST represent the same semantic concept using
the same canonical unit: percentage points (10.0 = 10%).

The following MUST be true:
- StrategySpec.take_profit_pct = 10.0 means 10%.
- ExitCondition.pct_of_entry = 10.0 means 10%.
- Both paths compute the same threshold value for the same input.
- Both paths follow the same floating-point policy defined in Amendment 3.4.

The implementation MUST NOT maintain two different unit conventions for the
same percentage concept. If ExitCondition.pct_of_entry was previously stored
as a fraction (0.1 = 10%), this MUST be corrected to percentage points (10.0 = 10%).

All serialization, validation, hashing, and runtime paths MUST use the
canonical percentage-point convention:
- condition_serialization must serialize pct_of_entry as percentage points
- config_hash must compute identically regardless of which path is used
- result_hash must be unaffected by which exit path was triggered
```

* **Rationale:** The current implementation uses `10.0` for StrategySpec and `0.1` for ExitCondition — a 100× discrepancy that could produce different thresholds for the same percentage specification. The design must mandate consistency.
* **Affected implementation components:** `StrategySpec` schema, `ExitCondition` schema, `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, `ConditionValidator`, `validation.py`, `config_hash` computation, `condition_serialization`.
* **Affected tests:** All test fixtures that create `ExitCondition` objects with `pct_of_entry` must use percentage-point values.

---

## 4. Canonical TP/SL Semantics

The following normative language defines the exact semantics after design approval.

```
**Canonical Take-Profit and Stop-Loss Semantics**

All percentage-based exit thresholds are computed as a percentage of the
actual entry fill price using the canonical percentage-point unit.

10.0 = 10%. 0.10 = 0.1%.

For a LONG position with entry fill price E, take-profit percentage TP,
and stop-loss percentage SL:

  take_profit_threshold = E × (1 + TP / 100)
  stop_loss_threshold    = E × (1 - SL / 100)

For a SHORT position with entry fill price E, take-profit percentage TP,
and stop-loss percentage SL:

  take_profit_threshold = E × (1 - TP / 100)
  stop_loss_threshold    = E × (1 + SL / 100)

Boundary semantics are inclusive. Equality triggers:

  LONG TP: close_price >= take_profit_threshold
  LONG SL: close_price <= stop_loss_threshold
  SHORT TP: close_price <= take_profit_threshold
  SHORT SL: close_price >= stop_loss_threshold

The numerical boundary policy (Amendment 3.4) guarantees that IEEE-754
representation does not prevent boundary-triggering.

LONG and SHORT semantics are symmetric: the mathematical relationship between
entry, threshold, and close price is identical up to direction.
```

---

## 5. Numerical Boundary Specification

This section is mandatory. It must define precisely how the engine distinguishes
immediately below threshold, exact mathematical threshold, and immediately above threshold.

### Current Problem

For `entry=100.0, take_profit_pct=10.0`:
- Mathematical threshold: `110.0`
- IEEE-754 computed threshold: `110.00000000000001`
- `110.0 >= 110.00000000000001` evaluates `False`
- The mathematically exact boundary does NOT trigger.

### Candidate Mechanisms (HUMAN APPROVAL REQUIRED)

**Mechanism A — Additive Reformulation:**

Compute threshold as: `entry + entry * pct / 100` (for TP LONG) instead of `entry * (1 + pct / 100)`.

This changes the arithmetic path: `entry * pct` is computed first (exact for round numbers), then divided by 100, then added to `entry`. This avoids the `1 + pct/100` intermediate multiplication that introduces the boundary error.

For `entry=100.0, pct=10.0`: `100.0 + 100.0 * 10.0 / 100.0 = 100.0 + 10.0 = 110.0` (exact).
For `entry=100.5, pct=10.0`: `100.5 + 100.5 * 10.0 / 100.0 = 100.5 + 10.05 = 110.55` (threshold is 110.54999999999999716, slightly below mathematical 110.55, so 110.55 triggers).

**HUMAN APPROVAL REQUIRED:** Must be verified for all supported entry prices and percentages.

**Mechanism B — Canonical `.10f` Normalization:**

After computing the threshold, normalize it by converting to the canonical `.10f` representation defined by the existing condition serialization convention (line 751):

`threshold_normalized = float(f"{threshold:.10f}")`

For `entry=100.0, pct=10.0`: `threshold = 110.00000000000001`, `f"{110.00000000000001:.10f}" = "110.0000000000"`, `float("110.0000000000") = 110.0`.

This extends the design's existing `.10f` canonical serialization convention (line 637: "Two floats that are mathematically equal but differ in their binary IEEE-754 representation must serialize to the same `.10f` string") to runtime comparison.

**HUMAN APPROVAL REQUIRED:** Must be verified that `.10f` normalization does not alter behavior for non-boundary cases and that it provides sufficient precision for all supported instruments.

**Mechanism C — Other:**

If the human reviewer identifies a third deterministic mechanism, it must be specified here with the same guarantee requirements and `HUMAN APPROVAL REQUIRED` marker.

### Decision Points

The following must be explicitly resolved by the human:

1. Which mechanism (A, B, or other) is the normative policy?
2. Is Mechanism A guaranteed to produce boundary-triggering for ALL supported entry prices and percentages? If not, what is the bounded verification scope?
3. Is Mechanism B's `.10f` normalization sufficient precision for all instruments? Does `.10f` (10 decimal places) provide enough precision for the smallest supported price increment?
4. If both A and B produce identical results for all cases, which one is the canonical formula?
5. Does the chosen mechanism interact correctly with `ExitCondition.pct_of_entry` when used as a fraction (before D6 correction)?

### STOP CONDITION

If the architecture cannot support an unambiguous boundary rule without introducing new infrastructure (tolerance, Decimal, tick-size), report:
`DESIGN EXPANSION REQUIRED — HUMAN APPROVAL REQUIRED`
Do not modify the architecture.

---

## 6. Cross-Path Contract

The following contract defines the relationship between the two percentage exit paths.

```
**StrategySpec / ExitCondition Cross-Path Contract**

StrategySpec.stop_loss_pct, StrategySpec.take_profit_pct, and
ExitCondition.pct_of_entry are ONE canonical semantic concept.

Canonical unit: percentage points (10.0 = 10%, NOT 0.1 = 10%).
Canonical formula: threshold = entry_fill_price × (1 ± pct / 100).
Canonical floating-point policy: Amendment 3.4.

Implementation requirements:
- StrategySpec.take_profit_pct = 10.0 and ExitCondition.pct_of_entry = 10.0
  MUST produce the same threshold for the same entry_fill_price.
- Both paths MUST use the same comparison operators:
  LONG TP: >=, LONG SL: <=, SHORT TP: <=, SHORT SL: >=
- Both paths MUST follow the same boundary inclusion rules (Amendment 3.3).

Affected serialization paths:
- condition_serialization must serialize pct_of_entry as percentage points
  using .10f formatting
- config_hash must compute identically regardless of which path is used
- The serialization format for ExitCondition.pct_of_entry must use the same
  precision and unit convention as StrategySpec.take_profit_pct

Affected validation paths:
- ConditionValidator must validate pct_of_entry is in percentage points
- StrategyValidator must validate take_profit_pct/stop_loss_pct is in percentage points
- Both validators MUST reject the old fractional interpretation (0.1 = 10%)
```

---

## 7. Hash / Serialization Impact

### strategy_hash
**Potential impact:** If `take_profit_pct`/`stop_loss_pct` serialization changes (e.g., from fractional to percentage-point convention), the strategy hash may change for existing strategies. The design must define migration rules or confirm that existing serialized strategies use the canonical unit.

### config_hash
**Potential impact:** The `config_hash` field ordering already includes `stop_loss_pct|take_profit_pct` and `exit_conditions_serialized` (line 680-690). If `ExitCondition.pct_of_entry` values change from fractional to percentage-point representation, the `condition_serialization` string changes, which changes `config_hash`. The design must define whether this is a breaking change or a correction.

### result_hash
**Potential impact:** If boundary behavior changes (i.e., exits that previously did not trigger at the boundary now trigger), the trade count, P&L, equity curve, and therefore `result_hash` may change for affected strategies. The design must define whether this is expected behavior correction or a breaking change.

### canonical serialization
**Potential impact:** If `ExitCondition.pct_of_entry` serialization changes to percentage points, the `condition_serialization` format (line 743) must remain compatible. The `.10f` formatting convention already exists and can accommodate the change.

### condition_serialization
**Potential impact:** The `threshold_value` field in condition serialization (line 751) uses `.10f` formatting. If the threshold computation formula changes (additive vs. multiplicative) or if `.10f` normalization is applied to the threshold before serialization, the serialized threshold value may differ for the same percentage specification. The design must specify whether serialization uses the raw computed threshold or the normalized threshold.

---

## 8. Regression Test Specification

After design approval, the following tests must be implemented. They are NOT added now.

### 8.1 LONG TAKE PROFIT

| Test | Entry | TP | Close | Expected |
|------|-------|----|-------|----------|
| Below boundary | 100.0 | 10.0% | 109.99 | No trigger |
| Exact boundary | 100.0 | 10.0% | 110.0 | Trigger |
| Above boundary | 100.0 | 10.0% | 111.0 | Trigger |

### 8.2 LONG STOP LOSS

| Test | Entry | SL | Close | Expected |
|------|-------|----|-------|----------|
| Below boundary | 100.0 | 10.0% | 89.0 | Trigger |
| Exact boundary | 100.0 | 10.0% | 90.0 | Trigger |
| Above boundary | 100.0 | 10.0% | 91.0 | No trigger |

### 8.3 SHORT TAKE PROFIT

| Test | Entry | TP | Close | Expected |
|------|-------|----|-------|----------|
| Below boundary | 100.0 | 10.0% | 89.0 | Trigger |
| Exact boundary | 100.0 | 10.0% | 90.0 | Trigger |
| Above boundary | 100.0 | 10.0% | 91.0 | No trigger |

### 8.4 SHORT STOP LOSS

| Test | Entry | SL | Close | Expected |
|------|-------|----|-------|----------|
| Below boundary | 100.0 | 10.0% | 109.0 | No trigger |
| Exact boundary | 100.0 | 10.0% | 110.0 | Trigger |
| Above boundary | 100.0 | 10.0% | 111.0 | Trigger |

### 8.5 Non-Round Entry Price

| Test | Entry | TP | Close | Expected |
|------|-------|----|-------|----------|
| Boundary at 100.5 | 100.5 | 10.0% | 110.55 | Trigger |
| Below at 100.5 | 100.5 | 10.0% | 110.54 | No trigger |
| Above at 100.5 | 100.5 | 10.0% | 110.56 | Trigger |

### 8.6 Floating-Point-Sensitive Threshold

| Test | Entry | TP | Close | Expected |
|------|-------|----|-------|----------|
| 333.33, TP=33.3 | 333.33 | 33.3% | 444.44 | Trigger or no-trigger per policy |
| 0.01, TP=100% | 0.01 | 100.0% | 0.02 | Trigger |

### 8.7 StrategySpec Path

| Test | Description | Expected |
|------|-------------|----------|
| StrategySpec take_profit_pct | All boundary tests above using StrategySpec field | As specified per test |
| StrategySpec stop_loss_pct | All boundary tests above using StrategySpec field | As specified per test |

### 8.8 ExitCondition Path

| Test | Description | Expected |
|------|-------------|----------|
| ExitCondition.pct_of_entry | All boundary tests above using ExitCondition object | As specified per test |
| Unit consistency | pct_of_entry=10.0 means 10%, NOT 0.1=10% | Confirmed |

### 8.9 Percentage-Unit Consistency

| Test | Description | Expected |
|------|-------------|----------|
| StrategySpec vs ExitCondition | Same entry, close, and percentage value via both paths | Same trigger decision |
| Serialization round-trip | Create ExitCondition with pct_of_entry=10.0, serialize, deserialize | pct_of_entry still 10.0 |
| Hash consistency | Same config via StrategySpec vs ExitCondition | Same config_hash |

### 8.10 LONG/SHORT Symmetry

| Test | Description | Expected |
|------|-------------|----------|
| Symmetric boundary | LONG TP at boundary triggers iff SHORT SL at boundary triggers | Confirmed |
| Symmetric below | LONG TP below boundary does not trigger iff SHORT SL below boundary does not trigger | Confirmed |
| Symmetric above | LONG TP above boundary triggers iff SHORT SL above boundary triggers | Confirmed |

### 8.11 Deterministic Execution

| Test | Description | Expected |
|------|-------------|----------|
| Repeated runs | Run identical backtest 100 times | Identical exit decisions, trades, equity curve, metrics, result_hash |
| Same dataset | Same dataset, same strategy, same config | Identical results |

---

## 9. Conflict Check

### 9.1 Direct Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.1 | Current `ExitCondition.evaluate()` | Uses `pct_of_entry` as fraction (0.1 = 10%). Amendment requires percentage points (10.0 = 10%). |
| 3.2 | No existing formula in design | The design has NO formula section for exit thresholds. This is a new addition, not a conflict. |
| 3.4 | Current `_check_exit_conditions()` | Uses multiplicative threshold (`entry * (1 + pct/100)`). Additive reformulation (Option A) changes the formula. `.10f` normalization (Option B) adds a post-processing step. |
| 3.5 | Current `config_hash` ordering | If `pct_of_entry` serialization changes from fractional to percentage-point, the `condition_serialization` string changes, altering `config_hash`. |

### 9.2 Implied Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.1 | Test fixtures | Existing tests that create `ExitCondition(type='take_profit', pct_of_entry=0.1)` with the meaning of 10% must be updated to `pct_of_entry=10.0`. |
| 3.5 | `ResultHash` | If boundary behavior changes, trade count and P&L may change, altering `result_hash` for affected strategies. The design must define whether this is a correction or breaking change. |
| 3.4 | `condition_serialization` | If `.10f` normalization is applied to threshold before serialization, the `threshold_value` field may differ from the raw computed value. |

### 9.3 Terminology Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.1 | `pct_of_entry` naming | The field name `pct_of_entry` suggests "percentage of entry" which is consistent with percentage points. The current fractional interpretation (0.1 = 10%) is inconsistent with the field name. |
| 3.2 | `entry_fill_price` | The design does not currently define `entry_fill_price` as a concept. The `PositionTracker` uses `entry_fill_price` but the design does not explicitly define it in the exit context. |

### 9.4 Hash/Serialization Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.5 | `config_hash` | Changing `ExitCondition.pct_of_entry` from fractional to percentage-point changes the serialized `condition_serialization` string, which changes `config_hash`. The design must define migration rules. |
| 3.5 | `strategy_hash` | If `take_profit_pct`/`stop_loss_pct` values are unchanged, `strategy_hash` should not change. If test fixtures change these values, `strategy_hash` changes. |

### 9.5 Schema Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.1 | `ExitCondition.pct_of_entry: Optional[float]` | The schema type is `float`, which accommodates both 0.1 and 10.0. The unit convention must be specified in documentation, not in the schema type. |
| 3.2 | `StrategySpec.take_profit_pct: Optional[float]` | Same as above — schema type does not enforce unit convention. |

### 9.6 Architecture Conflicts

| Amendment | Conflict | Description |
|-----------|----------|-------------|
| 3.4 | No existing float infrastructure | The design has no shared comparison utility, no Decimal infrastructure, no tick-size metadata. Any policy must operate within these constraints. |
| 3.4 | `BREAKEVEN_TOLERANCE` | The existing `BREAKEVEN_TOLERANCE = 1e-10` is scoped to breakeven counting. It must NOT be extended to exit comparisons unless the design explicitly authorizes it. |

---

## 10. Human Approval Gate

```
STATUS: DESIGN AMENDMENT DRAFT — AWAITING FINAL HUMAN APPROVAL

The design file docs/strategy_engine_design.md remains unchanged.
The source files in src/ remain unchanged.
The test files in tests/ remain unchanged.
No implementation has been performed.
No tolerance has been introduced.
No Decimal conversion has been introduced.
No tick-size logic has been introduced.
No design option has been selected by this agent.

Phase 3 remains NO-GO.
Blocker #1 (same-bar re-entry) is RESOLVED.
Blocker #2 (TP/SL floating-point boundary semantics) is BLOCKED —
awaiting explicit human approval of the design amendments above.

The human reviewer must approve or reject each of the following:
- Amendment 3.1 (Percentage Unit Definition)
- Amendment 3.2 (Normative Formula Definition)
- Amendment 3.3 (Boundary Inclusion Requirement)
- Amendment 3.4 (Floating-Point Policy) — including choice between Option A, Option B, or other
- Amendment 3.5 (Cross-Path Unit Consistency Contract)
- Section 5 (Numerical Boundary Specification) — including Mechanism A, B, or other
- All conflict resolutions in Section 9
- All regression test specifications in Section 8
```

---
END OF DESIGN AMENDMENT DRAFT
---
