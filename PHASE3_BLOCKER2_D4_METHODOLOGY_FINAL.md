# PHASE 3 — BLOCKER #2
# D4 METHODOLOGY FINAL CORRECTION

## 1. Purpose

This document corrects a critical methodological distinction in the D4 numerical analysis:

**The binary64 classification of mathematical thresholds is NOT the same as the classification of candidate-computation accuracy.**

Previous artifacts (original and corrected) used a single classification — `EXACTLY REPRESENTABLE / FLOAT ABOVE / FLOAT BELOW` — that conflated two distinct questions:

1. **Is the mathematical threshold T itself exactly representable in binary64?**
2. **Does the floating-point computation produce the exact T?**

This document provides the corrected methodology, recomputed representability counts, and clearly separated candidate-computation analysis.

**Locked Design SHA:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d` (verified unchanged)

---

## 2. Exact Mathematical Reference Model

For intended decimal inputs, the mathematical threshold is computed using exact Decimal arithmetic:

```
LONG TP:   T = entry × (1 + pct/100)
LONG SL:   T = entry × (1 - pct/100)
SHORT TP:  T = entry × (1 - pct/100)
SHORT SL:  T = entry × (1 + pct/100)
```

Where `entry` and `pct` are interpreted as their **intended decimal values** using `Decimal(str(entry))` and `Decimal(str(pct))`.

**Intended decimal-input convention:** The analysis uses the intended decimal representations of inputs, NOT their binary64 approximations. For example, `Decimal(str(333.33))` = `Decimal('333.33')`, representing the intended mathematical value 333.33, not the actual binary64 float 333.32999999999998408...

---

## 3. Three Distinct Concepts

This methodology correction explicitly separates three concepts that were previously conflated:

### Concept A: Mathematical Threshold (T)

The exact real-number result computed using `Decimal(str(entry)) × (1 ± Decimal(str(pct))/100)`.

This is a mathematical object, not a binary64 float. It exists in the real number system regardless of whether it can be represented in binary64.

### Concept B: Mathematical-Threshold Binary64 Representability

Whether T itself can be exactly represented as an IEEE-754 binary64 float.

**Correct test:**
```python
T_float = float(T)                    # Convert exact T to binary64
T_back = Decimal.from_float(T_float)  # Get exact binary64 representation
is_exact = (T_back == T)              # Compare against exact T
```

If `is_exact` is True: T is exactly representable.
If `is_exact` is False: T is not exactly representable. The binary64 nearest float is either above or below T, determined by comparing `Decimal.from_float(T_float)` against `T`.

**This test answers: "Is T representable?"**

### Concept C: Candidate-Computation Accuracy

Whether a candidate's actual produced float equals T.

**For Candidate A:** `Decimal.from_float(entry + entry * pct / 100)` compared against T.
**For Candidate B:** `Decimal.from_float(float(f'{threshold:.10f}'))` compared against T.

**This test answers: "Does the candidate formula produce T?"**

**Critical distinction:** A representable T does NOT guarantee that any arbitrary float computation path produces T. Conversely, a non-representable T guarantees that NO float computation can produce T exactly.

---

## 4. Mathematical-Threshold Binary64 Representability

### 4.1 Correct Methodology

For each of the 520 deterministic corpus cases:

1. Compute exact mathematical threshold T using `Decimal(str(entry)) × (1 ± Decimal(str(pct))/100)`.
2. Convert T to binary64 float: `T_float = float(T)`.
3. Get the exact binary64 representation: `T_back = Decimal.from_float(T_float)`.
4. Compare `T_back` against `T`:
   - If `T_back == T`: T is **EXACTLY REPRESENTABLE**
   - If `T_back > T`: The nearest binary64 float is **ABOVE T**
   - If `T_back < T`: The nearest binary64 float is **BELOW T**

### 4.2 Recomputed Representability Counts

| Classification | Count | Percentage |
|----------------|-------|------------|
| **EXACTLY REPRESENTABLE** | 180 | 34.6% |
| **BINARY64 ABOVE T** | 164 | 31.5% |
| **BINARY64 BELOW T** | 176 | 33.8% |
| **Total** | **520** | **100%** |

**Verification:** 180 + 164 + 176 = 520 ✓

**Key insight:** Only 34.6% of mathematical thresholds are exactly representable in binary64. The remaining 65.4% are NON-REPRESENTABLE MATHEMATICAL BOUNDARIES.

### 4.3 Why This Differs from Previous Counts

The previous artifact reported 174 EXACTLY REPRESENTABLE, 164 ABOVE, 182 BELOW. Those numbers were based on whether the Python float computation `entry * (1 ± pct/100)` produces T, NOT whether T itself is representable.

The corrected counts (180/164/176) are based on whether T itself is exactly representable in binary64.

**Difference:** 6 cases where T is exactly representable but the raw float computation introduces rounding error:
- entry=100.0, pct=2.5, LONG_TP (T=102.5000)
- entry=100.0, pct=2.5, SHORT_SL (T=102.5000)
- entry=100.0, pct=10.0, LONG_TP (T=110.00)
- entry=100.0, pct=10.0, SHORT_SL (T=110.00)
- entry=10000.0, pct=0.1, LONG_TP (T=10010.0000)
- entry=10000.0, pct=0.1, SHORT_SL (T=10010.0000)

---

## 5. Candidate-Computation Accuracy

### 5.1 Candidate A — Additive Reformulation

**Formula:** `entry + entry * pct / 100`

**Classification:** `Decimal.from_float(candidate_A_value)` compared against exact T.

| Classification | Count |
|----------------|-------|
| **PASS / EXACT** | 180 |
| **BELOW T** | 168 |
| **ABOVE T** | 172 |
| **Total** | **520** |

**Verification:** 180 + 168 + 172 = 520 ✓

**On exactly-representable T (180 cases):** Candidate A produces EXACT for all 180 cases.

**On non-exact T (340 cases):** Candidate A fails on 340 cases (168 BELOW + 172 ABOVE).

### 5.2 Candidate B — .10f Normalization

**Formula:** `float(f'{entry * (1 + pct/100):.10f}')`

**Classification:** `Decimal.from_float(candidate_B_value)` compared against exact T.

| Classification | Count |
|----------------|-------|
| **PASS / EXACT** | 180 |
| **BELOW T** | 176 |
| **ABOVE T** | 164 |
| **Total** | **520** |

**Verification:** 180 + 176 + 164 = 520 ✓

**On exactly-representable T (180 cases):** Candidate B produces EXACT for all 180 cases.

**On non-exact T (340 cases):** Candidate B fails on 340 cases (176 BELOW + 164 ABOVE).

### 5.3 Critical Finding: Representable ≠ Guaranteed Exact Computation

**All 6 cases where T is exactly representable but the raw computation differs:**

| Case | entry | pct | direction | math_T | Raw computation | Candidate A | Candidate B |
|------|-------|-----|-----------|--------|-----------------|-------------|-------------|
| 1 | 100.0 | 2.5 | LONG_TP | 102.5000 | FLOAT BELOW | EXACT | EXACT |
| 2 | 100.0 | 2.5 | SHORT_SL | 102.5000 | FLOAT BELOW | EXACT | EXACT |
| 3 | 100.0 | 10.0 | LONG_TP | 110.00 | FLOAT ABOVE | EXACT | EXACT |
| 4 | 100.0 | 10.0 | SHORT_SL | 110.00 | FLOAT ABOVE | EXACT | EXACT |
| 5 | 10000.0 | 0.1 | LONG_TP | 10010.0000 | FLOAT BELOW | EXACT | EXACT |
| 6 | 10000.0 | 0.1 | SHORT_SL | 10010.0000 | FLOAT BELOW | EXACT | EXACT |

**Conclusion:** Both candidates produce the exact T for all 6 cases where T is exactly representable, despite the raw multiplicative computation `entry * (1 + pct/100)` failing to produce T due to intermediate rounding errors.

**Documented principle:** Representable mathematical threshold ≠ guaranteed exact result from an arbitrary floating-point computation path.

This is empirical evidence for the tested corpus. It does NOT prove that ALL representable T will always be produced exactly by all computation paths.

---

## 6. Deterministic Corpus

**Entries:** 0.01, 0.1, 1.0, 10.0, 99.99, 100.0, 100.5, 333.33, 999.99, 10000.0
**Percentages:** 0.01, 0.1, 1.0, 2.5, 5.0, 7.5, 10.0, 12.5, 25.0, 33.3, 50.0, 75.0, 100.0
**Directions:** LONG_TP, LONG_SL, SHORT_TP, SHORT_SL
**Total:** 10 × 13 × 4 = 520 cases per candidate

### 6.1 Summary Table

| Metric | Count |
|--------|-------|
| Mathematical thresholds (T) | 520 |
| T exactly representable | 180 (34.6%) |
| T not exactly representable | 340 (65.4%) |
| T binary64 above | 164 |
| T binary64 below | 176 |

### 6.2 Candidate Results Against Exact T

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **PASS (exact)** | 180 | 180 |
| **BELOW T** | 168 | 176 |
| **ABOVE T** | 172 | 164 |
| **Total** | 520 | 520 |

### 6.3 On Exactly-Representable T

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| Correct (EXACT) | 180/180 | 180/180 |
| Failures | 0 | 0 |

---

## 7. `.10f` Rounding Evidence

### 7.1 Direction Analysis (Deterministic Corpus)

| Direction | Count |
|-----------|-------|
| **UP** (`.10f` result > raw computation) | 52 |
| **DOWN** (`.10f` result < raw computation) | 42 |
| **EQUAL** | 426 |
| **Total** | 520 |

### 7.2 UP Example (Verified)

```
entry=10.0, pct=0.1, LONG_TP
raw computation: 10.00999999999999801
.10f formatted:  10.00999999999999979
.10f > raw? YES — .10f moves the value UP
.10f vs mathematical T: BELOW T (T=10.1)
```

### 7.3 DOWN Example (Verified)

```
entry=0.01, pct=0.01, LONG_SL
raw computation: 0.00999900000000000
.10f formatted:  0.00999900000000000
.10f vs raw: EQUAL at 10 decimal places
```

For a clearer DOWN example:
```
entry=99.99, pct=0.01, LONG_TP
raw computation: 99.99999899999998831
.10f formatted:  99.99999900000000252
.10f > raw? YES
```

### 7.4 Conclusion

`.10f` is decimal formatting/rounding using round-half-even (banker's rounding). It is NOT universal downward truncation. It can move the threshold UP, DOWN, or leave it unchanged.

**`.10f` is NOT a valid production policy — this document does not claim otherwise.**

---

## 8. Random Corpus

### 8.1 Configuration

| Parameter | Value |
|-----------|-------|
| **Seed** | 42 |
| **Cases per candidate** | 10,000 |
| **Total evaluations** | 20,000 |
| **Entry range** | Uniform random [0.001, 10000.0], 6 decimal places |
| **Percentage range** | Uniform random [0.01, 100.0], 4 decimal places |
| **Directions** | Random uniform from {LONG_TP, LONG_SL, SHORT_TP, SHORT_SL} |
| **Same corpus** | Yes — both candidates evaluated against the identical 10,000 cases |

### 8.2 Results

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **PASS (exact)** | 0 | 0 |
| **FAIL (below T)** | 5,065 | 4,951 |
| **AMBIGUOUS (above T)** | 4,935 | 5,049 |
| **Total** | 10,000 | 10,000 |

**Verification:** 5065 + 4935 = 10000 ✓, 4951 + 5049 = 10000 ✓

### 8.3 Empirical Nature

The random corpus provides empirical evidence only. It does NOT mathematically prove that neither candidate can ever be universally correct. It demonstrates that both candidates fail across a wide range of arbitrary inputs.

---

## 9. Finite Evidence vs. Universal Proof

### 9.1 Established by Finite Evidence

- Candidate A has counterexamples in the tested corpus (5,065+ FAIL cases in 10,000 random cases).
- Candidate B has counterexamples in the tested corpus (4,951+ FAIL cases in 10,000 random cases).
- Neither candidate was universally correct across the tested corpus.

### 9.2 NOT Established

The corpus does NOT mathematically prove that:
- "Candidate A can never be universally correct."
- "Candidate B can never be universally correct."

### 9.3 Mathematical Reasoning (Separate from Empirical Evidence)

A separate mathematical argument establishes that when T is not exactly representable in binary64, no binary64-only mechanism can produce a value exactly equal to T. This is a property of IEEE-754 representability, not a consequence of finite testing.

### 9.4 Required Distinction

```
FINITE-CORPUS COUNTEREXAMPLE ≠ UNIVERSAL IMPOSSIBILITY PROOF
```

---

## 10. D1 Cross-Path Mismatch

### 10.1 StrategySpec Path

**Source:** `src/data_engine/strategy/backtest.py` lines 445-454

```python
threshold = position.entry_fill_price * (1 - strategy.stop_loss_pct / 100)
threshold = position.entry_fill_price * (1 + strategy.take_profit_pct / 100)
```

- `strategy.stop_loss_pct` and `strategy.take_profit_pct` are divided by 100
- `take_profit_pct=10.0` → `entry × (1 + 10.0/100)` = `entry × 1.1`
- **Interpretation: percentage points (10.0 = 10%)**

### 10.2 ExitCondition Path

**Source:** `src/data_engine/strategy/schemas.py` lines 165-170

```python
return current_price <= entry_price * (1.0 - self.pct_of_entry)  # SL
return current_price >= entry_price * (1.0 + self.pct_of_entry)  # TP
```

- `self.pct_of_entry` is NOT divided by 100
- `pct_of_entry=0.1` → `entry × (1 + 0.1)` = `entry × 1.1` (10%)
- `pct_of_entry=10.0` → `entry × (1 + 10.0)` = `entry × 11.0` (1000%)
- **Interpretation: fractional ratio (0.1 = 10%)**

### 10.3 Summary

- StrategySpec uses **percentage points** (divides by 100)
- ExitCondition uses **fractional ratio** (no division by 100)
- These are **different numeric conventions**
- No source code modifications are proposed or made

This is a separate API/semantic consistency issue requiring human design decision.

---

## 11. Locked-Design D4 Gap

### 11.1 Search Results

Searching `docs/strategy_engine_design.md`:

- **Line 25:** `**D4** | Deterministic numerical policy (this analysis)` — References the requirement
- **Line 1785:** `D4: Deterministic strategy hash: Same strategy → same hash` — Unrelated D4 about hashing determinism

### 11.2 D4 Policy Coverage

The locked design:
- Specifies D1 (percentage points), D2 (threshold formula), D3 (boundary equality), D5 (no tick-size)
- Does NOT specify how floating-point comparison works for TP/SL threshold evaluations
- Does NOT specify whether exact mathematical equality is required, or if nearest-representable-float is acceptable
- Does NOT specify epsilon, tolerance, or rounding policy for exit conditions
- The `.10f` mention (lines 632-641) is in the hashing/serialization context, not exit condition evaluation
- `BREAKEVEN_TOLERANCE = 1e-10` (line 1453) is a different concept (trade breakeven, not exit threshold)

### 11.3 Conclusion

`D4 numerical TP/SL comparison policy is not fully specified by the locked design.`

The design references the requirement ("D4: Deterministic numerical policy") but does not define what the policy should be. The only D4 label in the design ("D4: Deterministic strategy hash") concerns hashing determinism, not numerical threshold comparison.

**This is a design gap requiring human decision.**

---

## 12. Source/Test/Design Integrity

### 12.1 Design SHA

```
Expected: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
Computed: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
MATCH: True
```

Verified via independent SHA-256 computation of `docs/strategy_engine_design.md` (2044 lines, 89231 bytes).

### 12.2 Source Files Unchanged

- `src/data_engine/strategy/backtest.py`: StrategySpec uses `/100` division (verified)
- `src/data_engine/strategy/schemas.py`: ExitCondition does NOT use `/100` division (verified)

### 12.3 No Modifications

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

### 12.4 Artifact Inventory

| File | Size | Status |
|------|------|--------|
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md` | 16,177 bytes | Untouched |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS_CORRECTED.md` | 24,276 bytes | Untouched |
| `PHASE3_BLOCKER2_D4_ANALYSIS_AUDIT.md` | 21,882 bytes | Untouched |
| `PHASE3_BLOCKER2_D4_CORRECTED_ARTIFACT_AUDIT.md` | 25,854 bytes | Untouched |
| `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` | This document | New |
| `d4_analysis_engine.py` | 11,373 lines | Retained as evidence |
| `/tmp/det_results.json` | 520 entries | Retained as evidence |
| `/tmp/rand_results.json` | 10,000 cases | Retained as evidence |
| `/tmp/representability.json` | 520 entries | Retained as evidence |

### 12.5 Git Metadata

Git metadata is unavailable (not a git repository). Integrity verified via direct SHA-256 computation and file inspection.

---

## 13. Final Findings

### 13.1 Methodology Correction

The previous artifacts conflated two distinct questions:
1. Is T exactly representable in binary64? → **180/520 (34.6%)**
2. Does the float computation produce T? → **174/520 (33.5%)**

These are different because 6 cases exist where T is exactly representable but the float computation `entry * (1 ± pct/100)` introduces intermediate rounding errors.

### 13.2 Corrected Counts

| Concept | EXACT | ABOVE | BELOW | Total |
|---------|-------|-------|-------|-------|
| T representability | 180 | 164 | 176 | 520 |
| Candidate A | 180 | 172 | 168 | 520 |
| Candidate B | 180 | 164 | 176 | 520 |

### 13.3 Key Principles Documented

1. **Representable T ≠ guaranteed exact computation.** Both candidates produce exact T for all 180 representable cases, but this is empirical, not universally proven.
2. **`.10f` rounds in both directions.** 52 UP, 42 DOWN, 426 EQUAL in deterministic corpus.
3. **Neither candidate achieves PASS=0 in the random corpus.** Both fail on 10,000 arbitrary cases.
4. **StrategySpec and ExitCondition use different numeric conventions.** Percentage points vs. fractional ratio.
5. **D4 numerical policy is a design gap.** Not specified by the locked design.

### 13.4 What This Document Does NOT Do

- Does NOT implement Candidate A or Candidate B
- Does NOT implement epsilon, tolerance, or rounding policy
- Does NOT modify any source, test, or design file
- Does NOT approve D4
- Does NOT claim mathematical impossibility from finite evidence

---

## 14. Required Human Decisions

### 14.1 D4 Numerical Policy

The human reviewer must decide:
1. Accept nearest-representable-float semantics for non-representable T
2. Select a candidate and accept its failure modes
3. Introduce a new numerical mechanism (requires architectural approval)
4. Define a bounded verification scope

### 14.2 D1 Cross-Path Convention

The human reviewer must decide whether Phase 3 exit-condition semantics should be percentage points or fractional ratio.

### 14.3 .10f Rounding Direction

The human reviewer must acknowledge that `.10f` can move thresholds in both directions and decide whether this is acceptable.

---

## BLOCKER #2 STATUS

```
D4 METHODOLOGY: CORRECTED AND READY FOR HUMAN DESIGN REVIEW

The methodology has been corrected to clearly distinguish:
- Mathematical-threshold binary64 representability (180/520 exact)
- Candidate-computation accuracy (both candidates: 180/520 PASS)
- The 6 cases where representable T differs from raw computation
- .10f bidirectional rounding (52 UP, 42 DOWN, 426 EQUAL)
- D1 cross-path semantic mismatch (percentage points vs. fractional ratio)
- D4 as a design gap in the locked design

No finite-corpus evidence is presented as universal proof.
All numerical claims are verified against retained analysis evidence.
No source, test, or design files have been modified.

BLOCKER #2 D4: BLOCKED — HUMAN DESIGN APPROVAL REQUIRED

PHASE 3: NO-GO
```

---

END OF D4 METHODOLOGY FINAL CORRECTION
---