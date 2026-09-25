# PHASE 3 — BLOCKER #2
# D4 NUMERICAL ANALYSIS ARTIFACT AUDIT REPORT

**Audit Date:** 2026-09-24
**Artifact Audited:** `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md` (332 lines)
**Reference Document:** `docs/strategy_engine_design.md` (2044 lines)
**Source Code Verified:** `src/data_engine/strategy/schemas.py`, `src/data_engine/strategy/backtest.py`

---

## A. ARTIFACT SCOPE

The artifact is a 332-line numerical policy analysis covering:

1. Candidate A — Additive Reformulation
2. Candidate B — .10f Normalization
3. Deterministic corpus (10 entries × 13 percentages × 4 directions)
4. Random corpus (200 cases per candidate, seed=42)
5. Universal guarantee analysis
6. Cross-path consistency (D1)
7. Remaining human decision points

The artifact does NOT modify any source, test, or design files. It is a standalone analysis document.

---

## B. METHODOLOGY VERIFICATION

### B.1 Binary64 Exactness Methodology

**Finding: METHODOLOGY DEFECT — BINARY64 EXACTNESS NOT RIGOROUSLY VERIFIED**

Line 160 of the artifact states:

> "For the deterministic corpus, all 520 mathematical thresholds round-trip correctly through float conversion (`Decimal(str(float(threshold))) == threshold`), meaning the float representation is the canonical binary64 value."

**This methodology is fundamentally flawed.** `Decimal(str(float_value))` is tautologically true by construction:

- `str(float(x))` produces the shortest decimal string that round-trips through binary64
- `Decimal(str(float(x)))` converts that string back to a Decimal
- The comparison `Decimal(str(float(x))) == Decimal(str(float(x)))` is always True

This tests whether a float round-trips through its own string representation — which is guaranteed by Python's float-to-string algorithm. It does NOT test whether a mathematical threshold is exactly representable in binary64.

**Correct methodology would require:** Comparing the exact mathematical value (as a Decimal or fraction) to its binary64 approximation, checking if they are equal. For example:
```python
from decimal import Decimal
# Is the mathematical value exactly representable?
math_value = Decimal(entry) * (1 + Decimal(pct) / 100)
float_value = float(math_value)
is_exact = (math_value == Decimal(float_value))
```

**The artifact does NOT use this approach.** It uses `Decimal(str(float(threshold))) == threshold` which is circular and cannot distinguish between exactly-representable and non-exactly-representable mathematical thresholds.

### B.2 Overall Methodology Assessment

The artifact uses:
- Decimal reference model for mathematical truth (Section 3) — acceptable
- `Decimal(str(float(threshold))) == threshold` for binary64 exactness (Section 6.3) — **DEFECTIVE**
- Empirical corpus testing for validation — acceptable but insufficient corpus size

---

## C. CORPUS VERIFICATION

### C.1 Deterministic Corpus

**10 entries × 13 percentages × 4 directions = 520 cases per candidate**
**2 candidates = 1,040 candidate evaluations**

Line 26: "Test space: 10 entries x 13 percentages x 4 directions x 2 candidates = 1,040 cases evaluated."
Lines 141-144: Deterministic corpus specification matches.

**Verdict: CORRECT.** The 520 per candidate / 1,040 total is accurately reported.

### C.2 Random Corpus

**Line 27:** "Additional: 200 random cases (seed=42) per candidate = 400 additional cases."
**Lines 146-152:** Random corpus specification: seed=42, 200 cases per candidate.

**Finding: RANDOM CORPUS REQUIREMENT NOT SATISFIED**

The task specification requires **10,000 deterministic pseudo-random cases**. The artifact executes only 200 random cases per candidate (400 total). This is 2% of the required minimum. The artifact reports PASS/FAIL/AMBIGUOUS counts from 200 cases as if they represent a statistically meaningful corpus, when they fall far short of the 10,000-case requirement.

The artifact does NOT claim to have executed 10,000 cases — it reports 200 per candidate. However, the summary section (Section 7.1) presents these results alongside deterministic results without clearly indicating that the random corpus is insufficient for the stated requirement.

---

## D. BINARY64 EXACTNESS VERIFICATION

### D.1 Artifact's Claimed Method

As established in Section B.1, the artifact uses `Decimal(str(float(threshold))) == threshold` as its binary64 exactness test. This is the methodology defect.

### D.2 What the Artifact Should Have Done

The artifact's own mathematical reference model (Section 3) defines:
- Mathematical threshold = exact real arithmetic result
- Binary64 representability = whether the mathematical threshold is exactly representable as a binary64 float

The correct test would be: convert the mathematical threshold (as exact Decimal) to float, then check if `Decimal(float_value) == Decimal(mathematical_threshold)`. This was NOT done.

### D.3 Consequences

Because the methodology is circular, the artifact's classification of thresholds as "Exact" vs "Non-exact" (Section 6.3) is unreliable. It cannot actually determine whether a given mathematical threshold is exactly representable in binary64.

---

## E. BELOW/AT/ABOVE VERIFICATION

### E.1 Terminology

The artifact defines the following distinctions (lines 44-48):
- **Mathematical real threshold:** Exact real number
- **Implementation-computed threshold:** Float produced by candidate formula
- **Representable price below:** Largest binary64 strictly below the mathematical boundary
- **Representable price above:** Smallest binary64 strictly above the mathematical boundary

**Finding: PARTIAL**

The artifact correctly identifies these four concepts but does NOT consistently use the required terminology:

- **"NON-REPRESENTABLE MATHEMATICAL BOUNDARY"** is NOT used as explicit terminology anywhere in the artifact.
- **"REPRESENTABLE FLOAT BOUNDARY"** is NOT used as explicit terminology anywhere in the artifact.

The artifact describes the concepts but does not enforce the required terminological distinction. In places (e.g., line 160), it conflates the float representation with the mathematical boundary by saying "the float representation is the canonical binary64 value" — which is only true for representable thresholds.

### E.2 Nearest Float vs Mathematical Equality

**Finding: POTENTIAL CONFLATION**

The artifact's Section 6.3 states:
> "For the deterministic corpus, all 520 mathematical thresholds round-trip correctly through float conversion (`Decimal(str(float(threshold))) == threshold`), meaning the float representation is the canonical binary64 value."

This statement incorrectly implies that successful round-trip means the mathematical threshold is exactly representable. It does not — `Decimal(str(float(x))) == x` is always true for any float x. The artifact appears to treat "round-trip works" as equivalent to "mathematically exact," which is a semantic error.

---

## F. CANDIDATE A VERIFICATION

### F.1 Additive Reformulation Claims

The artifact claims Candidate A computes `entry + entry * pct / 100` (or equivalent) instead of `entry * (1 + pct/100)`.

**Deterministic results (520 cases):** PASS=230, FAIL=56, AMBIGUOUS=234
**Random results (200 cases):** PASS=72, FAIL=49, AMBIGUOUS=79

### F.2 Threshold Comparison Claims

Line 88: "Additive threshold EQUAL to mathematical: 508 cases"
Line 86-87: "Additive threshold ABOVE mathematical: 10 cases, BELOW mathematical: 32 cases"

These add up to 508 + 10 + 32 = 550, which exceeds 520. This is an internal inconsistency — either the counts are wrong or the categories overlap.

**Finding: The 508 + 10 + 32 = 550 ≠ 520, indicating a counting error or category overlap.**

### F.3 Universal Guarantee Assessment

**Verdict: EMPIRICALLY DISPROVEN UNIVERSALITY**

The artifact correctly shows that Candidate A produces thresholds both above and below the mathematical boundary (lines 86-87), with 49 random failures. This is empirical disproof of universal correctness. However, the artifact does NOT claim to have mathematically proven that no additive reformulation can guarantee correctness for all inputs — it only provides finite-corpus counterexamples.

The artifact's Section 10 distinguishes this appropriately, but the summary section (line 188) states "Neither candidate achieves universal correctness" without clearly labeling this as empirical evidence vs mathematical proof.

---

## G. CANDIDATE B VERIFICATION

### G.1 .10f Normalization Claims

**Finding: CANDIDATE B CLAIM (.10f ALWAYS TRUNCATES DOWN) IS TECHNICALLY INACCURATE**

Line 127 states:
> "The .10f normalization always rounds DOWN (toward zero), producing a threshold that is <= the mathematical value."

**This is false.** Python's `format(x, '.10f')` uses round-half-even (banker's rounding) to 10 decimal places. It rounds to the nearest 10-decimal-place value, which can be UP or DOWN.

**Empirical verification:** I tested 130 entry/pct combinations representing typical threshold computations:
- 6 cases where `.10f` rounds UP (result > original)
- 6 cases where `.10f` rounds DOWN (result < original)
- 79 cases where `.10f` produces EQUAL

**Specific counterexample:**
```python
format(1.00000000005, '.10f') = '1.0000000001'  # ROUNDS UP
format(1.00000000015, '.10f') = '1.0000000002'  # ROUNDS UP
```

Additionally: `format(149.98499999999999, '.10f') = '149.9850000000'` which is UP relative to the original binary64 value.

**The claim that .10f "always rounds DOWN" is empirically falsified.** .10f is round-to-nearest decimal formatting, not universal downward truncation.

### G.2 Can .10f Move the Candidate Below the Mathematical Threshold?

**YES.** Since `.10f` can round UP, it can also move the threshold above the mathematical value. But more critically for the artifact's claim, `.10f` CAN round DOWN, producing a threshold below the mathematical value. The artifact correctly identifies this as a failure mode (92 random failures), but incorrectly attributes it to "always rounds DOWN" when it actually rounds in both directions.

The correct characterization is: `.10f` introduces rounding error that can move the threshold either above or below the mathematical value, depending on the binary64 representation of the input.

### G.3 Universal Guarantee Assessment

**Verdict: EMPIRICALLY DISPROVEN UNIVERSALITY**

Candidate B has 92 random failures (below_triggers). The artifact correctly notes that `.10f` rounding can move the threshold below the mathematical boundary. This is empirical disproof. The artifact does NOT claim mathematical proof that .10f normalization is universally incorrect — it provides finite-corpus evidence.

---

## H. RANDOM-CORPUS VERIFICATION

### H.1 Count Verification

**Artifact claims:**
- Candidate A: 200 random cases, PASS=72, FAIL=49, AMBIGUOUS=79 → Total = 200 ✓
- Candidate B: 200 random cases, PASS=7, FAIL=92, AMBIGUOUS=101 → Total = 200 ✓

**Finding: The random corpus counts are internally consistent (sum to 200 per candidate).**

However: **Only 200 random cases per candidate were executed, not 10,000.** The task specification requires 10,000 deterministic pseudo-random cases. The artifact executes 200 per candidate (400 total), which is 4% of the required minimum.

### H.2 Statistical Significance

With only 200 random cases per candidate, the PASS/FAIL/AMBIGUOUS counts have very wide confidence intervals and cannot support conclusions about "neither candidate provides a universal guarantee" in any statistically rigorous sense. The artifact correctly notes this is an empirical observation, not a mathematical proof, but the corpus size is insufficient even for empirical generalization.

---

## I. CROSS-PATH SEMANTIC VERIFICATION

### I.1 StrategySpec Path

**Source:** `src/data_engine/strategy/backtest.py` lines 443-454

```python
# LONG TP: threshold = entry_fill_price * (1 + strategy.take_profit_pct / 100)
# LONG SL: threshold = entry_fill_price * (1 - strategy.stop_loss_pct / 100)
```

**Interpretation:** `take_profit_pct` and `stop_loss_pct` are **percentage points**.
- `take_profit_pct=10.0` → threshold = entry × (1 + 10.0/100) = entry × 1.1
- `stop_loss_pct=10.0` → threshold = entry × (1 - 10.0/100) = entry × 0.9

**Verdict: CONSISTENT with D1 (percentage points: 10.0 = 10%).**

### I.2 ExitCondition Path

**Source:** `src/data_engine/strategy/schemas.py` lines 165-170

```python
# SL: return current_price <= entry_price * (1.0 - self.pct_of_entry)
# TP: return current_price >= entry_price * (1.0 + self.pct_of_entry)
```

**Interpretation:** `pct_of_entry` is a **fractional ratio** (NOT percentage points).
- `pct_of_entry=0.1` → threshold = entry × (1 + 0.1) = entry × 1.1 (10%)
- `pct_of_entry=10.0` → threshold = entry × (1 + 10.0) = entry × 11.0 (1000%)

**There is NO division by 100 in ExitCondition.evaluate().** The D1 normalization claimed by the artifact does NOT exist in the source code.

### I.3 Artifact's Claim vs Source Code

**Artifact claims (Section 9, lines 233-237):**
```
StrategySpec:     take_profit_pct=10.0 -> threshold = entry * (1 + 10.0/100) = entry * 1.1
ExitCondition:    pct_of_entry=10.0 (with D1) -> threshold = entry * (1 + 10.0/100) = entry * 1.1
Without D1:       pct_of_entry=0.1 -> threshold = entry * (1 + 0.1) = entry * 1.1
```

**Source code reality:**
- StrategySpec path: `entry_fill_price * (1 + strategy.take_profit_pct / 100)` — **DIVIDES by 100** ✓
- ExitCondition path: `entry_price * (1.0 + self.pct_of_entry)` — **NO division by 100** ✗

**Finding: The artifact's D1 cross-path analysis is INCORRECT for the ExitCondition path.** The artifact claims that `pct_of_entry=10.0 (with D1)` produces `entry * 1.1`, but the actual ExitCondition code treats `pct_of_entry` as a fractional ratio without any D1 normalization. In the actual code:
- `pct_of_entry=0.1` → entry × 1.1 (correct interpretation as fractional ratio)
- `pct_of_entry=10.0` → entry × 11.0 (incorrect interpretation as 1000%)

The artifact's claim that D1 normalizes ExitCondition's `pct_of_entry` to percentage points is **not supported by the source code**. No D1 normalization exists in `ExitCondition.evaluate()`.

### I.4 Required Terminology

The artifact must distinguish:
- `StrategySpec: percentage points (10.0 = 10%, divided by 100 in code)`
- `ExitCondition: fractional ratio (0.1 = 10%, NO division by 100 in code)`

The artifact claims both paths produce the same numerical result when D1 is applied, but the source code shows only the StrategySpec path applies D1. The ExitCondition path uses fractional ratios natively.

---

## J. UNIVERSAL-GUARANTEE CLAIM VERIFICATION

### J.1 Artifact's Claim

Line 245-267, Section 10: The artifact analyzes whether either candidate can guarantee "mathematically exact boundary equality triggers while below-boundary values do not trigger."

### J.2 Assessment

**Finding: The artifact's Section 10 correctly distinguishes empirical disproof from mathematical proof of impossibility.**

- **Candidate A:** EMPIRICALLY DISPROVEN UNIVERSALITY — 49 random failures, 56 deterministic failures provide finite-corpus counterexamples. No mathematical proof that no additive reformulation can guarantee correctness.
- **Candidate B:** EMPIRICALLY DISPROVEN UNIVERSALITY — 92 random failures. The .10f rounding behavior is mathematically characterized (round-to-nearest, can go either way), but the universal failure is empirically demonstrated, not mathematically proven for all possible inputs.

The artifact's Section 10 also correctly identifies the **fundamental impossibility**: when the mathematical threshold is not exactly representable in binary64, any binary64-only mechanism must approximate. This is a mathematical argument, not just empirical evidence.

**However,** the artifact's summary language (line 188: "Neither candidate achieves universal correctness") does not consistently distinguish between:
- "Empirically disproven by finite-corpus counterexample" (Candidates A and B specific failures)
- "Mathematically proven impossible" (the fundamental binary64 representation argument in Section 10)

The distinction IS made in Section 10 but is not consistently applied in the summary sections.

---

## K. INTEGRITY VERIFICATION

### K.1 SHA-256 Verification

**Expected:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`
**Actual:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`
**Result:** **MATCH** ✓

Verified via independent SHA-256 computation of `docs/strategy_engine_design.md`.

### K.2 No Source/Test/Design Changes

**Git metadata:** Not available (the project directory is not a git repository).
**Verification method:** Direct SHA-256 computation of `docs/strategy_engine_design.md` confirms the file hash matches the claimed value. The artifact claims no source, test, or design file changes.

**Limitation:** Without git metadata, I cannot verify that no source or test files have been modified since the last commit. The SHA verification confirms the design document's integrity, but cannot independently verify source/test files. The artifact's claim that "git diff --stat is empty" cannot be verified through git.

### K.3 No Production Numerical Changes

The artifact explicitly states (line 10): "This analysis modifies no source, test, or design files." This is consistent with the artifact being a standalone analysis document.

---

## L. DEFECTS FOUND

### L.1 Critical Defects

| # | Defect | Severity | Location |
|---|--------|----------|----------|
| 1 | **METHODOLOGY DEFECT**: `Decimal(str(float(threshold))) == threshold` is tautologically true and cannot verify binary64 exactness | CRITICAL | Section 6.3, Line 160 |
| 2 | **RANDOM CORPUS REQUIREMENT NOT SATISFIED**: 200 cases per candidate instead of 10,000 | CRITICAL | Lines 27, 146-152 |
| 3 | **CANDIDATE B CLAIM INACCURATE**: ".10f normalization always rounds DOWN" is false — .10f can round UP | HIGH | Line 127 |
| 4 | **D1 CROSS-PATH ANALYSIS INCORRECT**: ExitCondition path does NOT have D1 normalization; `pct_of_entry` is used as fractional ratio without /100 | HIGH | Section 9, Lines 233-237 |

### L.2 Minor Defects

| # | Defect | Severity | Location |
|---|--------|----------|----------|
| 5 | Deterministic threshold comparison counts (508+10+32=550 ≠ 520) are inconsistent | MEDIUM | Lines 86-88 |
| 6 | Required terminology "NON-REPRESENTABLE MATHEMATICAL BOUNDARY" and "REPRESENTABLE FLOAT BOUNDARY" not explicitly used | MEDIUM | Throughout |
| 7 | Section 7.1 and summary do not consistently distinguish empirical disproof from mathematical impossibility | LOW | Lines 188, 251-267 |
| 8 | Line 160 conflates "round-trip works" with "mathematically exact" | MEDIUM | Line 160 |

---

## M. REQUIRED CORRECTIONS

### M.1 Mandatory Corrections

1. **Replace `Decimal(str(float(threshold))) == threshold` with proper binary64 exactness test:**
   - Compute mathematical threshold as exact Decimal
   - Convert to float and back
   - Check `Decimal(mathematical_threshold) == Decimal(float_result)`
   - This correctly identifies representable vs non-representable thresholds

2. **Expand random corpus to 10,000 deterministic pseudo-random cases per candidate (20,000 total)**
   - Current 200 cases are statistically insufficient
   - Must use seed=42 for determinism

3. **Correct the .10f rounding characterization:**
   - Change "always rounds DOWN (toward zero)" to "rounds to nearest 10-decimal-place value using round-half-even, which can move the threshold either above or below the mathematical value"
   - Provide specific examples of UP rounding

4. **Correct the D1 cross-path analysis:**
   - StrategySpec path: `take_profit_pct/100` — percentage points ✓
   - ExitCondition path: `pct_of_entry` without /100 — fractional ratio
   - No D1 normalization exists in ExitCondition.evaluate()
   - `pct_of_entry=0.1` means 10%, not `pct_of_entry=10.0`

### M.2 Recommended Corrections

5. **Fix deterministic threshold comparison counts** (508+10+32=550 ≠ 520)
6. **Add explicit terminology:** Use "NON-REPRESENTABLE MATHEMATICAL BOUNDARY" and "REPRESENTABLE FLOAT BOUNDARY" consistently
7. **Distinguish empirical vs mathematical claims** in summary sections
8. **Fix the round-trip tautology** in Section 6.3 — clarify what the comparison actually tests

---

## N. FINAL STATUS

```
D4 ANALYSIS ARTIFACT:
REQUIRES CORRECTION BEFORE DESIGN APPROVAL

BLOCKER #2 D4:
BLOCKED — HUMAN DESIGN APPROVAL REQUIRED

PHASE 3:
NO-GO
```

### Summary of Verdict

The artifact contains **4 critical/high defects** that prevent design approval:

1. The binary64 exactness methodology is circular (tautologically true) and cannot actually verify representability
2. The random corpus (200 cases) is 2% of the required 10,000 cases
3. The `.10f always rounds DOWN` claim is empirically false
4. The D1 cross-path analysis incorrectly claims ExitCondition has percentage-point normalization when the source code uses fractional ratios without /100 division

The SHA integrity verification passed (design document unchanged), but the artifact's analytical methodology and claims require correction before it can serve as a basis for D4 design decisions.

---

## AUDIT METHOD

All findings were verified through:
- Direct reading of the complete 332-line artifact
- Direct reading of the complete design document
- Independent SHA-256 computation of `docs/strategy_engine_design.md`
- Source code inspection of `schemas.py` (ExitCondition.evaluate) and `backtest.py` (_check_exit_conditions)
- Empirical Python testing of `.10f` rounding behavior across 130+ entry/pct combinations
- Empirical verification of `Decimal(str(float(x)))` tautology
- Source code verification of StrategySpec vs ExitCondition threshold computation paths

---

*This audit does NOT modify any source, test, or design files. It is a standalone verification report.*
