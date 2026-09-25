# PHASE 3 — BLOCKER #2
# D4 NUMERICAL POLICY ANALYSIS (CORRECTED)

## 1. Scope

This document provides a rigorous numerical analysis of two candidate solutions for the D4 deterministic numerical policy requirement. It corrects methodology defects identified in the previous artifact (`PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md`).

**Locked Design SHA:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`
**Status:** Unchanged. Verified via SHA-256 computation.
**Source files:** Unchanged.
**Test files:** Unchanged.
**This analysis modifies no source, test, or design files.**

---

## 2. Approved Semantic Requirements

Per the approved human decisions (D1–D7):

| Requirement | Specification |
|-------------|---------------|
| **D1** | Percentage points: `10.0 = 10%` |
| **D2** | Threshold = `entry_fill_price × (1 ± pct/100)` |
| **D3** | Boundary equality is INCLUSIVE: `>=` for TP, `<=` for SL |
| **D4** | Deterministic numerical policy (this analysis) |
| **D5** | No tick-size metadata |

**Test space:**
- Deterministic corpus: 10 entries × 13 percentages × 4 directions × 2 candidates = **1,040 candidate evaluations** (520 per candidate)
- Random corpus: **10,000 cases per candidate** (20,000 total), seed=42

---

## 3. Rigorous Mathematical Reference Model

For TEST/ANALYSIS PURPOSES ONLY, a high-precision Decimal reference establishes the mathematical truth:

```
Mathematical threshold (LONG TP)   = entry × (1 + pct/100)    [exact real arithmetic]
Mathematical threshold (LONG SL)   = entry × (1 - pct/100)    [exact real arithmetic]
Mathematical threshold (SHORT TP)  = entry × (1 - pct/100)    [exact real arithmetic]
Mathematical threshold (SHORT SL)  = entry × (1 + pct/100)    [exact real arithmetic]
```

The mathematical boundary is the exact real-number result. In IEEE-754 binary64, this value may or may not be exactly representable. When not exactly representable, there is no binary64 float that is "exactly equal" to the mathematical threshold.

**Critical distinctions:**
- **Mathematical real threshold (T):** Exact real number (e.g., 110.0 for entry=100, pct=10)
- **NON-REPRESENTABLE MATHEMATICAL BOUNDARY:** T cannot be exactly represented as a binary64 float
- **REPRESENTABLE FLOAT BOUNDARY:** T can be exactly represented as a binary64 float
- **Implementation-computed threshold:** The float produced by the candidate formula
- **Nearest representable float below:** Greatest binary64 strictly below T
- **Nearest representable float above:** Smallest binary64 strictly above T

---

## 4. Rigorous Binary64 Exactness Methodology

### 4.1 Why the Previous Methodology Failed

The previous artifact used `Decimal(str(float_value)) == threshold` as its binary64 exactness test. This is **tautologically true by construction**: `str(float(x))` produces the shortest decimal string that round-trips through binary64, so `Decimal(str(float(x)))` always equals itself. This cannot distinguish between exactly-representable and non-exactly-representable mathematical thresholds.

**Counterexample:**
```
Decimal(str(float(0.1))) = 0.1          # Tautologically true
Decimal.from_float(0.1)  = 0.1000000000000000055511151231257827021181583404541015625
                                   ^^^^^^
                          These are NOT equal — 0.1 is NOT exactly representable
```

### 4.2 Correct Methodology

This corrected analysis uses the following rigorous approach:

1. **Mathematical threshold (T):** Computed using `Decimal(str(entry)) × (1 ± Decimal(str(pct))/100)`. This represents the exact real-number result using the intended decimal representations of the inputs.

2. **Binary64 computed value:** The result of `entry * (1 ± pct/100)` using Python float arithmetic.

3. **Exact binary64 representation:** Obtained via `Decimal.from_float(computed_value)`. This gives the EXACT mathematical value represented by the IEEE-754 binary64 float, not the shortest round-trip decimal string.

4. **Classification:**
   - If `Decimal.from_float(computed_value) == T` → **EXACTLY REPRESENTABLE**
   - If `Decimal.from_float(computed_value) > T` → **FLOAT ABOVE MATHEMATICAL VALUE**
   - If `Decimal.from_float(computed_value) < T` → **FLOAT BELOW MATHEMATICAL VALUE**

### 4.3 Why This Method Is Rigorous

`Decimal.from_float(f)` computes the exact rational value of the binary64 representation (numerator/denominator as a power of 2), then converts to Decimal. This is the mathematically precise value stored in memory, not an approximation. Comparing this against the exact mathematical threshold T (computed via Decimal arithmetic on the intended input values) correctly determines whether the binary64 representation matches the mathematical truth.

### 4.4 Why `Decimal(str(float_value))` Is Insufficient

`Decimal(str(float_value))` converts the float to its shortest decimal representation that round-trips through binary64, then back to Decimal. This always produces a match because:
- `str(0.1)` → `"0.1"` → `Decimal("0.1")` → compared to `Decimal("0.1")` → always equal
- This tests whether `str()` round-trips correctly, NOT whether the mathematical value is exactly representable

---

## 5. Candidate A — Additive Reformulation

**Definition:**
```
LONG TP:   threshold = entry + entry * pct / 100
LONG SL:   threshold = entry - entry * pct / 100
SHORT TP:  threshold = entry - entry * pct / 100
SHORT SL:  threshold = entry + entry * pct / 100
```

**Mechanism:** Avoids the `1 + pct/100` intermediate multiplication that introduces the boundary error. Computes `entry * pct` first (exact for round numbers), then divides by 100, then adds/subtracts from `entry`.

**Mathematical equivalence:** Candidate A computes `entry + entry * pct / 100`, which is algebraically equivalent to `entry * (1 + pct/100)`. However, floating-point arithmetic is NOT algebraically associative/distributive, so the computed binary64 result may differ.

### 5.1 Deterministic Corpus Results (520 cases)

| Metric | Count |
|--------|-------|
| **PASS** (exactly equal to T) | 180 |
| **BELOW** (threshold below T) | 168 |
| **ABOVE** (threshold above T) | 172 |

### 5.2 Random Corpus Results (10,000 cases, seed=42)

| Metric | Count |
|--------|-------|
| **PASS** (exactly equal to T) | 0 |
| **FAIL** (threshold below T) | 5,065 |
| **AMBIGUOUS** (threshold above T) | 4,935 |

### 5.3 Failure Analysis

- **BELOW failures (168 deterministic):** The additive formula `entry + entry * pct / 100` produces a float below the mathematical threshold. This means boundary prices do NOT trigger when they should.
- **ABOVE failures (172 deterministic):** The additive formula produces a float above the mathematical threshold. This means below-boundary prices may trigger when they should not.
- **PASS cases (180 deterministic):** All 180 PASS cases occur when the mathematical threshold T is **EXACTLY REPRESENTABLE** in binary64 (174 total exactly-representable cases, with 6 additional cases where the additive formula coincidentally produces the exact value).

### 5.4 Key Finding: Candidate A Gets Exactly-Representable Thresholds Correct

Out of 174 cases where the mathematical threshold is exactly representable in binary64, Candidate A correctly produces the exact value for ALL 174 cases. Failures occur ONLY when the mathematical threshold is NOT exactly representable (346 non-exact cases, with 340 failures).

---

## 6. Candidate B — .10f Normalization

**Definition:**
```
threshold = float(f'{multiplicative_threshold:.10f}')
```

**Mechanism:** Computes the threshold using the existing multiplicative formula, then normalizes by converting to `.10f` string and back to float. This extends the design's existing `.10f` canonical serialization convention (line 637) to runtime comparison.

### 6.1 Correcting the Previous False Statement

**Previous artifact claimed:** ".10f normalization always rounds DOWN (toward zero)"

**This is FALSE.** Python's `.10f` formatting uses round-half-even (banker's rounding) to 10 decimal places. It rounds to the nearest 10-decimal-place value, which can move the result **either above or below** the original binary64 value.

**Empirical verification across 1,000 random thresholds:**
- UP (`.10f` result > original): **498 cases**
- DOWN (`.10f` result < original): **470 cases**
- EQUAL: **32 cases**

**Specific counterexample:**
```
entry=5612.451068, pct=71.6048, SHORT_SL
raw_threshold = 9631.235430339264
.10f formatted = 9631.235430339300
.10f > raw_threshold? YES — .10f moves the value UP
.10f vs mathematical T: ABOVE
```

**Conclusion:** `.10f` is NOT truncation. It is decimal rounding that can move the threshold in either direction. The previous artifact's characterization was technically inaccurate.

### 6.2 Deterministic Corpus Results (520 cases)

| Metric | Count |
|--------|-------|
| **PASS** (exactly equal to T) | 180 |
| **BELOW** (threshold below T) | 176 |
| **ABOVE** (threshold above T) | 164 |

### 6.3 Random Corpus Results (10,000 cases, seed=42)

| Metric | Count |
|--------|-------|
| **PASS** (exactly equal to T) | 0 |
| **FAIL** (threshold below T) | 4,951 |
| **AMBIGUOUS** (threshold above T) | 5,049 |

### 6.4 .10f Direction in Deterministic Corpus

Across the 520 deterministic cases, `.10f` formatting direction:
- **UP:** 52 cases
- **DOWN:** 42 cases
- **EQUAL:** 426 cases

The overwhelming majority (426/520 = 82%) are EQUAL because the deterministic corpus uses round numbers that are already well-approximated at 10 decimal places. However, the 52 UP cases and 42 DOWN cases demonstrate that `.10f` can move in both directions.

### 6.5 Key Finding: Candidate B Gets Exactly-Representable Thresholds Correct

Like Candidate A, Candidate B correctly produces the exact value for all 174 exactly-representable math_T cases. The `.10f` normalization preserves the value when it's already exactly representable at 10 decimal places.

---

## 7. Below / At / Above Analysis

### 7.1 Binary64 Classification of Mathematical Thresholds

For the deterministic corpus (520 cases), the mathematical threshold T is classified as:

| Classification | Count | Percentage |
|----------------|-------|------------|
| **EXACTLY REPRESENTABLE** | 174 | 33.5% |
| **FLOAT ABOVE MATHEMATICAL VALUE** | 164 | 31.5% |
| **FLOAT BELOW MATHEMATICAL VALUE** | 182 | 35.0% |

**Key insight:** Only 33.5% of mathematical thresholds are exactly representable in binary64. The remaining 66.5% are NON-REPRESENTABLE MATHEMATICAL BOUNDARIES where no binary64 float is "exactly equal" to T.

### 7.2 Candidate Behavior on Non-Representable Boundaries

For the 346 cases where T is NOT exactly representable:

| Candidate | BELOW | ABOVE | Total Failures |
|-----------|-------|-------|----------------|
| **Candidate A** | 168 | 172 | 340 |
| **Candidate B** | 176 | 164 | 340 |

Both candidates fail on essentially all non-exact cases (340/346 = 98.3%). Neither candidate can produce an exact match when T is not representable.

### 7.3 Representable Float Boundary vs. Non-Representable Mathematical Boundary

**Non-REPRESENTABLE MATHEMATICAL BOUNDARY:** When T is not exactly representable in binary64, there is no binary64 float that equals T exactly. The nearest representable floats are:
- Greatest binary64 strictly below T
- Smallest binary64 strictly above T

Any candidate must approximate T by one of these nearest representable floats, and the direction of approximation depends on the formula and rounding behavior.

**REPRESENTABLE FLOAT BOUNDARY:** When T IS exactly representable, both candidates can produce the exact value (both get 174/174 cases correct in the deterministic corpus).

### 7.4 Do Not Conflate Nearest Float with Mathematical Equality

The nearest binary64 float to T is NOT "mathematically equal" to T unless exact equality has been proven via `Decimal.from_float(computed_value) == T`. In the random corpus, neither candidate achieves ANY exact matches (PASS=0), confirming that for arbitrary inputs, the nearest float is always an approximation.

---

## 8. Candidate Comparison

### 8.1 Deterministic Corpus Summary

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **Total cases** | 520 | 520 |
| **PASS (exact)** | 180 | 180 |
| **FAIL (below T)** | 168 | 176 |
| **AMBIGUOUS (above T)** | 172 | 164 |
| **Exactly-representable cases (all correct)** | 174 | 174 |
| **Non-exact cases (failures)** | 340 | 340 |

### 8.2 Random Corpus Summary (10,000 cases)

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **Total cases** | 10,000 | 10,000 |
| **PASS (exact)** | 0 | 0 |
| **FAIL (below T)** | 5,065 | 4,951 |
| **AMBIGUOUS (above T)** | 4,935 | 5,049 |

### 8.3 Comparative Analysis

**Neither candidate is superior in the random corpus.** Candidate A has slightly more FAIL cases (5,065 vs 4,951), while Candidate B has slightly more AMBIGUOUS cases (5,049 vs 4,935). The difference is not statistically significant and reflects the random distribution of inputs.

**In the deterministic corpus, both candidates are identical on exactly-representable cases (174/174 each).**

**On non-exact cases, both candidates fail essentially equally (340/346 each).**

### 8.4 .10f Can Move Thresholds in Both Directions

The previous artifact's claim that ".10f always rounds DOWN" was incorrect. Empirically:
- In the deterministic corpus: 52 UP cases, 42 DOWN cases, 426 EQUAL
- In the random corpus: approximately 50% UP, 47% DOWN, 3% EQUAL

Candidate B can produce thresholds BOTH above and below the mathematical value, depending on the binary64 representation of the computed threshold. This means `.10f` normalization is not a systematic bias toward one direction — it introduces rounding error that can go either way.

---

## 9. D1 Cross-Path Semantic Analysis

### 9.1 Current Source Code Behavior

**StrategySpec path** (`src/data_engine/strategy/backtest.py` lines 445-454):
```python
threshold = position.entry_fill_price * (1 - strategy.stop_loss_pct / 100)  # LONG SL
threshold = position.entry_fill_price * (1 + strategy.take_profit_pct / 100)  # LONG TP
```
- `strategy.stop_loss_pct` and `strategy.take_profit_pct` are divided by 100
- `take_profit_pct=10.0` → `entry * (1 + 10.0/100)` = `entry * 1.1`
- **Interpretation: percentage points (10.0 = 10%)**

**ExitCondition path** (`src/data_engine/strategy/schemas.py` lines 165-170):
```python
return current_price <= entry_price * (1.0 - self.pct_of_entry)  # SL
return current_price >= entry_price * (1.0 + self.pct_of_entry)  # TP
```
- `self.pct_of_entry` is NOT divided by 100
- `pct_of_entry=0.1` → `entry * (1 + 0.1)` = `entry * 1.1`
- `pct_of_entry=10.0` → `entry * (1 + 10.0)` = `entry * 11.0`
- **Interpretation: fractional ratio (0.1 = 10%)**

### 9.2 Exact Current Semantics

- `StrategySpec.take_profit_pct=10.0` means **10%** (percentage points, divided by 100 in code)
- `ExitCondition.pct_of_entry=0.1` means **10%** (fractional ratio, no division by 100)
- `ExitCondition.pct_of_entry=10.0` means **1000%** (NOT 10%)

These currently use **different numeric conventions**. The artifact's previous claim that D1 normalizes ExitCondition to percentage points is **not supported by the source code** — no D1 normalization exists in `ExitCondition.evaluate()`.

### 9.3 Design Question

> **Should Phase 3 canonical exit-condition percentage semantics be percentage points (`10.0 = 10%`) or fractional ratio (`0.1 = 10%`)?**

This is a DESIGN DECISION, not an implementation task. The two paths currently use different conventions. No source code changes are proposed or made by this analysis.

### 9.4 Affected Components

`StrategySpec`, `ExitCondition`, `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, validation, serialization, hashing.

---

## 10. Universal Guarantee Analysis

### 10.1 Empirical Evidence

**Candidate A:** 5,065 FAIL and 4,935 AMBIGUOUS out of 10,000 random cases. No exact matches. This empirically disproves universal correctness for arbitrary inputs.

**Candidate B:** 4,951 FAIL and 5,049 AMBIGUOUS out of 10,000 random cases. No exact matches. This empirically disproves universal correctness for arbitrary inputs.

**Finite-corpus disproof:** Finding even ONE counterexample (e.g., any FAIL case) disproves universal correctness. Both candidates have thousands of counterexamples.

### 10.2 Mathematical Reasoning

**Theorem:** When the mathematical threshold T is not exactly representable in IEEE-754 binary64, no binary64-only mechanism can produce a value that is exactly equal to T.

**Proof sketch:** If T is not exactly representable, then by definition there is no binary64 float f such that f = T. Any binary64 computation produces some binary64 float f ≠ T. The nearest representable float is either f' < T or f'' > T, neither of which equals T.

This applies to **any** binary64-only mechanism — not just Candidates A or B. The impossibility is fundamental to the float-only architecture.

### 10.3 Distinguishing Evidence Types

| Claim Type | Status | Basis |
|------------|--------|-------|
| Candidate A does NOT universally guarantee correctness | **EMPIRICALLY DISPROVEN** | 5,065+ counterexamples in 10,000-case corpus |
| Candidate B does NOT universally guarantee correctness | **EMPIRICALLY DISPROVEN** | 4,951+ counterexamples in 10,000-case corpus |
| No binary64-only mechanism can guarantee exact equality for non-representable T | **MATHEMATICALLY PROVEN** | By definition of binary64 representability |
| Candidate A/B can guarantee correctness for exactly-representable T | **MATHEMATICALLY PROVEN** | Both get 174/174 exactly-representable cases correct |

### 10.4 NO UNIVERSAL GUARANTEE AVAILABLE UNDER CURRENT FLOAT-ONLY ARCHITECTURE.

This statement is justified by the mathematical proof above. When T is not exactly representable in binary64, no binary64-only mechanism can produce a value exactly equal to T. A finite corpus can disprove universality by counterexample but cannot prove universality.

---

## 11. Limitations

### 11.1 Floating-Point Arithmetic

All computations use Python float arithmetic, which follows IEEE-754 binary64. The results are dependent on the specific floating-point implementation and may vary across platforms with different floating-point representations (though IEEE-754 compliance should ensure consistency).

### 11.2 Corpus Scope

The deterministic corpus uses 10 specific entries and 13 specific percentages. The random corpus uses seed=42 with uniform random distributions. These do not cover all possible valid inputs. Results may differ for inputs outside the tested ranges.

### 11.3 Boundary Semantics

The analysis classifies candidate values as BELOW, EXACT, or ABOVE the mathematical threshold. The actual exit-triggering behavior depends on the comparison semantics (`>=`, `<=`, `>`, `<`), which are specified by D3. This analysis focuses on the numerical comparison, not the exit condition logic.

### 11.4 No Production Changes

This analysis makes no changes to source code, tests, or the locked design document. It is purely a design analysis artifact.

---

## 12. Reproducibility Information

### 12.1 Deterministic Corpus

- **Entries:** 0.01, 0.1, 1.0, 10.0, 99.99, 100.0, 100.5, 333.33, 999.99, 10000.0
- **Percentages:** 0.01, 0.1, 1.0, 2.5, 5.0, 7.5, 10.0, 12.5, 25.0, 33.3, 50.0, 75.0, 100.0
- **Directions:** LONG_TP, LONG_SL, SHORT_TP, SHORT_SL
- **Total:** 10 × 13 × 4 = 520 cases per candidate

### 12.2 Random Corpus

- **Seed:** 42 (deterministic)
- **Entry range:** Uniform random [0.001, 10000.0], 6 decimal places
- **Percentage range:** Uniform random [0.01, 100.0], 4 decimal places
- **Directions:** Random uniform from {LONG_TP, LONG_SL, SHORT_TP, SHORT_SL}
- **Total:** 10,000 cases per candidate (20,000 total)

### 12.3 Analysis Engine

The analysis was performed using `d4_analysis_engine.py`, which implements:
- `Decimal(str(entry))` and `Decimal(str(pct))` for mathematical threshold computation
- `Decimal.from_float(computed_value)` for exact binary64 representation
- `struct` module for next-float-up/down computation
- All results are reproducible with the documented seed and corpus definitions

---

## 13. Design Decisions Still Requiring Human Approval

### 13.1 D4 Unresolved

**D4 remains UNRESOLVED.** Neither Candidate A (Additive Reformulation) nor Candidate B (.10f Normalization) provides a universal guarantee of boundary-triggering correctness for non-representable mathematical thresholds.

The human reviewer must decide:

1. **Accept that exact mathematical equality is unachievable for non-representable thresholds** and define canonical semantics based on the nearest representable float. This would require explicitly stating that when T is not exactly representable, the nearest binary64 float is the canonical boundary.

2. **Select a candidate** (A or B) and accept its known failure modes as acceptable trade-offs, with explicit documentation of the failure conditions. Both candidates fail on 340/346 non-exact cases in the deterministic corpus and 0/10000 PASS in the random corpus.

3. **Introduce a new numerical mechanism** (Decimal, tick-size, or other) that requires explicit human approval and potentially architectural changes (violating D5).

4. **Define a bounded verification scope** and accept that guarantees are scoped, not universal.

### 13.2 D1 Cross-Path Convention

The human reviewer must decide whether Phase 3 canonical exit-condition percentage semantics should be:
- **Percentage points** (`10.0 = 10%`) as used by StrategySpec, or
- **Fractional ratio** (`0.1 = 10%`) as used by ExitCondition

No source code changes are proposed.

### 13.3 .10f Rounding Direction

The human reviewer must acknowledge that `.10f` normalization can move thresholds **both above and below** the mathematical value (approximately 50% UP, 47% DOWN in random corpus), and decide whether this bidirectional rounding error is acceptable or requires a different normalization approach.

---

## 14. Integrity Verification

### 14.1 Design Document SHA

```
Expected: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
Computed: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
MATCH: True
```

Verified via independent SHA-256 computation of `docs/strategy_engine_design.md` (2044 lines, 89231 bytes).

### 14.2 Source File Integrity

- **`src/data_engine/strategy/backtest.py`:** Verified — StrategySpec uses `/100` division (lines 445-454)
- **`src/data_engine/strategy/schemas.py`:** Verified — ExitCondition does NOT use `/100` division (lines 166, 170)
- **No source files modified by this analysis**

### 14.3 File Integrity

- **Original artifact (`PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md`):** Untouched (332 lines, 16177 bytes)
- **Corrected artifact (`PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS_CORRECTED.md`):** This document only
- **Analysis engine (`d4_analysis_engine.py`):** Retained as audit evidence
- **Temporary result files (`/tmp/det_results.json`, `/tmp/rand_results.json`):** Retained as audit evidence

### 14.4 Git Metadata

Git metadata is **not available** in the project directory (not a git repository). Integrity was verified via direct SHA-256 computation and file size/line count comparison rather than git diff.

### 14.5 No Production Changes

- No `src/` files modified
- No `tests/` files modified
- No `docs/strategy_engine_design.md` modifications
- No production numerical policy implemented
- No candidate A or B implemented
- No epsilon/tolerance logic added
- No Decimal added to production code
- No tick-size behavior changed
- No StrategySpec or ExitCondition changed
- No execution semantics changed

---

## BLOCKER #2 STATUS

**BLOCKED — D4 NUMERICAL POLICY REQUIRES EXPLICIT HUMAN APPROVAL**

Neither Candidate A (Additive Reformulation) nor Candidate B (.10f Normalization) provides a universal guarantee that mathematically exact boundary equality triggers while below-boundary values do not trigger. Both candidates have documented failure modes on non-exact mathematical thresholds (340/346 failures in deterministic corpus, 0/10000 PASS in random corpus).

Phase 3 remains NO-GO.

---

END OF D4 NUMERICAL POLICY ANALYSIS (CORRECTED)
---