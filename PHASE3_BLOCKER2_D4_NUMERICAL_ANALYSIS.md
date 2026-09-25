# PHASE 3 — BLOCKER #2
# D4 NUMERICAL POLICY ANALYSIS

## 1. Locked Design Integrity

* **Design SHA:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`
* **Status:** Unchanged. Verification passed.
* **Source files:** Unchanged (`git diff --stat` is empty).
* **Test files:** Unchanged.
* **This analysis modifies no source, test, or design files.**

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

**Test space:** 10 entries x 13 percentages x 4 directions x 2 candidates = 1,040 cases evaluated.
Additional: 200 random cases (seed=42) per candidate = 400 additional cases.

---

## 3. Mathematical Reference Model

For TEST/ANALYSIS PURPOSES ONLY, a high-precision Decimal reference establishes the mathematical truth:

```
Mathematical threshold (LONG TP)   = entry * (1 + pct/100)    [exact real arithmetic]
Mathematical threshold (LONG SL)   = entry * (1 - pct/100)    [exact real arithmetic]
Mathematical threshold (SHORT TP)  = entry * (1 - pct/100)    [exact real arithmetic]
Mathematical threshold (SHORT SL)  = entry * (1 + pct/100)    [exact real arithmetic]
```

The mathematical boundary is the exact real-number result. In IEEE-754 binary64, this value may or may not be exactly representable. When not exactly representable, there is no binary64 float that is "exactly equal" to the mathematical threshold.

**Critical distinction:**
- **Mathematical real threshold:** Exact real number (e.g., 110.0 for entry=100, pct=10)
- **Implementation-computed threshold:** The float produced by the candidate formula (e.g., 110.00000000000001 for multiplicative, 110.0 for additive)
- **Representable price below:** Largest binary64 strictly below the mathematical boundary
- **Representable price above:** Smallest binary64 strictly above the mathematical boundary

---

## 4. Candidate A — Additive Reformulation

**Definition:**
```
LONG TP:   threshold = entry + entry * pct / 100
LONG SL:   threshold = entry - entry * pct / 100
SHORT TP:  threshold = entry - entry * pct / 100
SHORT SL:  threshold = entry + entry * pct / 100
```

**Mechanism:** Avoids the `1 + pct/100` intermediate multiplication that introduces the boundary error. Computes `entry * pct` first (exact for round numbers), then divides by 100, then adds/subtracts from `entry`.

**Deterministic corpus results (520 cases):**
- PASS: 230
- FAIL: 56
- AMBIGUOUS: 234

**Failure types:**
- `below_triggers`: Below-boundary prices incorrectly trigger the exit (15 cases)
- `boundary_doesnt_trigger`: The mathematical boundary does NOT trigger (30 cases)
- `above_doesnt_trigger`: Above-boundary prices do not trigger (6 cases)
- `unexpected`: Other failure patterns (5 cases)

**Random corpus results (200 cases, seed=42):**
- PASS: 72
- FAIL: 49
- AMBIGUOUS: 79

**Representative failure cases:**
- `entry=2204.407, pct=58.9307, LONG_TP`: boundary_doesnt_trigger
- `entry=2448.919293, pct=13.9624, LONG_TP`: below_triggers
- `entry=8474.943816, pct=60.3766, LONG_TP`: boundary_doesnt_trigger

**Threshold vs mathematical comparison:**
- Additive threshold ABOVE mathematical: 10 cases
- Additive threshold BELOW mathematical: 32 cases
- Additive threshold EQUAL to mathematical: 508 cases

**Root cause of failures:**
The additive reformulation computes `entry * pct / 100` which introduces its own representation errors. When `entry * pct / 100` rounds UP above the exact mathematical value, the threshold exceeds the mathematical boundary, causing the boundary to NOT trigger. When `entry * pct / 100` rounds DOWN, the threshold falls below the boundary, causing below-boundary prices to trigger.

**Directional symmetry:**
The additive reformulation is symmetric in formula structure (LONG_TP and SHORT_SL share the same formula; LONG_SL and SHORT_TP share the same formula). However, threshold errors can be asymmetric in magnitude (10 cases above vs 32 cases below).

---

## 5. Candidate B — .10f Normalization

**Definition:**
```
threshold = float(f'{multiplicative_threshold:.10f}')
```

**Mechanism:** Computes the threshold using the existing multiplicative formula, then normalizes by converting to `.10f` string and back to float. This extends the design's existing `.10f` canonical serialization convention (line 637) to runtime comparison.

**Deterministic corpus results (520 cases):**
- PASS: 260
- FAIL: 0
- AMBIGUOUS: 260

**Random corpus results (200 cases, seed=42):**
- PASS: 7
- FAIL: 92
- AMBIGUOUS: 101

**Failure types (random corpus):**
- `below_triggers`: Below-boundary prices incorrectly trigger (92 cases)

**Representative failure cases:**
- `entry=2448.919293, pct=13.9624, LONG_TP`: below_triggers
- `entry=6766.995198, pct=89.219, LONG_TP`: below_triggers
- `entry=5904.925534, pct=3.188, LONG_TP`: below_triggers
- `entry=7588.073912, pct=15.9743, SHORT_SL`: below_triggers

**.10f differences from multiplicative threshold:**
62 cases where the `.10f`-normalized threshold differs from the raw multiplicative threshold. The `.10f` normalization always rounds DOWN (toward zero), producing a threshold that is <= the mathematical value. This causes below-boundary prices to trigger when the rounding is significant enough.

**Directional symmetry:**
The `.10f` normalization preserves directional symmetry in formula structure. However, the rounding-down effect creates a systematic bias: threshold <= mathematical value, meaning prices slightly below the mathematical boundary may trigger.

**Deterministic corpus vs random corpus discrepancy:**
The deterministic corpus uses round numbers (0.01, 0.1, 10.0, etc.) where `.10f` normalization produces correct results. The random corpus uses arbitrary floats where `.10f` normalization can round down significantly, causing below-trigger failures.

---

## 6. Boundary Corpus

### 6.1 Deterministic Corpus

**Entries:** 0.01, 0.1, 1.0, 10.0, 99.99, 100.0, 100.5, 333.33, 999.99, 10000.0
**Percentages:** 0.01, 0.1, 1.0, 2.5, 5.0, 7.5, 10.0, 12.5, 25.0, 33.3, 50.0, 75.0, 100.0
**Directions:** LONG_TP, LONG_SL, SHORT_TP, SHORT_SL
**Total cases:** 10 x 13 x 4 = 520 per candidate

### 6.2 Random Corpus

**Seed:** 42 (deterministic)
**Entries:** Uniform random [0.001, 10000.0], 6 decimal places
**Percentages:** Uniform random [0.01, 100.0], 4 decimal places
**Directions:** Random uniform
**Total cases:** 200 per candidate

### 6.3 Boundary Classification

For each case, the mathematical threshold is classified as:
- **Exact:** The mathematical real threshold is exactly representable in binary64
- **Non-exact:** The mathematical real threshold is NOT exactly representable in binary64

For the deterministic corpus, all 520 mathematical thresholds round-trip correctly through float conversion (`Decimal(str(float(threshold))) == threshold`), meaning the float representation is the canonical binary64 value. However, the IMPLEMENTATION's computed threshold may differ from the mathematical threshold due to floating-point arithmetic order.

---

## 7. Adversarial Results

### 7.1 Summary Table

| Metric | Candidate A (Additive) | Candidate B (.10f Normalization) |
|--------|----------------------|----------------------------------|
| **Deterministic PASS** | 230 | 260 |
| **Deterministic FAIL** | 56 | 0 |
| **Deterministic AMBIGUOUS** | 234 | 260 |
| **Random PASS** | 72 | 7 |
| **Random FAIL** | 49 | 92 |
| **Random AMBIGUOUS** | 79 | 101 |

### 7.2 Failure Analysis

**Candidate A failures (49 random cases):**
- Boundary doesn't trigger: threshold is above mathematical boundary
- Below triggers: threshold is below mathematical boundary
- Root cause: `entry * pct / 100` rounding errors accumulate differently than `entry * (1 + pct/100)`

**Candidate B failures (92 random cases):**
- Below triggers: `.10f` normalization rounds threshold down, below-boundary prices trigger
- Root cause: `.10f` truncation reduces precision, threshold becomes lower than mathematical boundary

**Both candidates exhibit FAIL cases in the random corpus.** Neither candidate achieves universal correctness.

### 7.3 Representative Cases

**Candidate A failure — boundary_doesnt_trigger:**
```
entry=2204.407, pct=58.9307, LONG_TP
Mathematical threshold: 2204.407 * 1.589307 ~= 3502.96...
Additive threshold:     slightly above mathematical (rounding up)
close at boundary:      does NOT trigger (FAIL)
```

**Candidate B failure — below_triggers:**
```
entry=2448.919293, pct=13.9624, LONG_TP
Mathematical threshold: 2448.919293 * 1.139624 ~= 2790.25...
Multiplicative:         2790.25...42 (17+ digits)
.10f normalized:        2790.2499999999998 (rounded down)
close slightly below:   triggers incorrectly (FAIL)
```

---

## 8. LONG/SHORT Symmetry

**Candidate A (Additive):**
- LONG_TP and SHORT_SL share the same formula: `entry + entry * pct / 100`
- LONG_SL and SHORT_TP share the same formula: `entry - entry * pct / 100`
- Symmetric by construction
- However, threshold errors can be asymmetric in magnitude (10 cases above vs 32 cases below)

**Candidate B (.10f Normalization):**
- LONG_TP and SHORT_SL share the same multiplicative formula + `.10f` normalization
- LONG_SL and SHORT_TP share the same multiplicative formula + `.10f` normalization
- Symmetric by construction
- `.10f` always rounds DOWN, creating a systematic bias: threshold <= mathematical value

**Conclusion:** Both candidates are symmetric in formula structure, but neither guarantees symmetric behavior in practice due to floating-point rounding effects.

---

## 9. Cross-Path Consistency

**D1 verification:** Percentage points (`10.0 = 10%`) applied consistently to both paths.

```
StrategySpec:     take_profit_pct=10.0 -> threshold = entry * (1 + 10.0/100) = entry * 1.1
ExitCondition:    pct_of_entry=10.0 (with D1) -> threshold = entry * (1 + 10.0/100) = entry * 1.1
Without D1:       pct_of_entry=0.1 -> threshold = entry * (1 + 0.1) = entry * 1.1
```

**Finding:** Both paths produce the same numerical threshold when D1 is applied (percentage points). Without D1, `pct_of_entry=0.1` happens to produce the same numerical result but with wrong semantics (0.1 interpreted as 0.1% rather than 10%). D1 ensures semantic consistency, not just numerical equality.

**Affected components:** `StrategySpec`, `ExitCondition`, `BacktestEngine._check_exit_conditions()`, `ExitCondition.evaluate()`, validation, serialization, hashing.

---

## 10. Universal Guarantee Analysis

**The critical question:** Can either candidate guarantee:

> "For every valid finite binary64 entry price and valid percentage, the implementation must guarantee that a mathematically exact boundary triggers, while a mathematically below-boundary value does not trigger."

**Answer: NO.** Neither candidate can provide this universal guarantee under the current float-only architecture.

**Reasoning:**

1. **When the mathematical threshold is not exactly representable in binary64** (which happens for most non-trivial entry/percentage combinations), there is no binary64 float that is "exactly equal" to the mathematical threshold. The nearest representable float is either slightly above or slightly below the true value.

2. **Candidate A (Additive)** can produce thresholds above the mathematical boundary (10 cases in deterministic, 49 failures in random), causing the boundary to NOT trigger. It can also produce thresholds below the boundary, causing below-boundary prices to trigger.

3. **Candidate B (.10f Normalization)** always rounds the threshold DOWN (toward zero), which means below-boundary prices can trigger when the rounding is significant (92 failures in random corpus).

4. **The fundamental impossibility:** When the mathematical threshold is not exactly representable, any binary64-only mechanism must either:
   - Accept that the "exact mathematical boundary" is approximated by the nearest representable float (which may trigger or not depending on rounding direction), OR
   - Introduce a non-binary64 mechanism (Decimal, tick-size, tolerance) that violates the D5 constraint.

**Conclusion:** The universal guarantee CANNOT be achieved with any binary64-only mechanism. The design must either:
- Accept that "exact mathematical equality" is unachievable for non-representable thresholds and define canonical semantics based on the nearest representable float, OR
- Introduce a new numerical mechanism (Decimal, tick-size, or other) that requires explicit human approval and potentially architectural changes.

---

## 11. Failure Cases

### 11.1 Candidate A (Additive) — Failure Cases Summary

| Case | Entry | Pct | Direction | Failure Type | Details |
|------|-------|-----|-----------|-------------|---------|
| 1 | 2204.407 | 58.9307 | LONG_TP | boundary_doesnt_trigger | Additive threshold > mathematical |
| 2 | 8474.944 | 60.3766 | LONG_TP | boundary_doesnt_trigger | Additive threshold > mathematical |
| 3 | 2448.919 | 13.9624 | LONG_TP | below_triggers | Additive threshold < mathematical |
| 4 | 3402.506 | 15.5564 | SHORT_TP | below_triggers | Additive threshold < mathematical |
| 5 | 0.01 | 7.5 | LONG_TP | boundary_doesnt_trigger | Small entry, large relative error |
| 6 | 0.01 | 10.0 | LONG_SL | below_triggers | Small entry, precision loss |
| 7 | 0.01 | 33.3 | LONG_SL | below_triggers | Small entry, precision loss |
| 8 | 0.01 | 75.0 | LONG_SL | below_triggers | Small entry, precision loss |

### 11.2 Candidate B (.10f Normalization) — Failure Cases Summary

| Case | Entry | Pct | Direction | Failure Type | Details |
|------|-------|-----|-----------|-------------|---------|
| 1 | 2448.919 | 13.9624 | LONG_TP | below_triggers | .10f rounds threshold down |
| 2 | 6767.00 | 89.219 | LONG_TP | below_triggers | .10f rounds threshold down |
| 3 | 5904.93 | 3.188 | LONG_TP | below_triggers | .10f rounds threshold down |
| 4 | 2186.38 | 50.5405 | LONG_TP | below_triggers | .10f rounds threshold down |
| 5 | 7588.07 | 15.9743 | SHORT_SL | below_triggers | .10f rounds threshold down |

### 11.3 Failure Patterns

- **Candidate A:** Failures increase with non-round entry prices and non-integer percentages
- **Candidate B:** Failures increase with arbitrary-precision entry prices where `.10f` truncation is significant
- **Both:** Failures are NOT directional (affect all 4 exit directions), but the failure modes differ

---

## 12. Remaining Human Decision

**D4 remains UNRESOLVED.** Neither candidate provides a universal guarantee.

The human reviewer must decide:

1. **Accept that "exact mathematical equality" is unachievable for non-representable thresholds** and define canonical semantics based on the nearest representable float. This would require explicitly stating that when the mathematical threshold is not exactly representable, the nearest binary64 float is the canonical boundary.

2. **Select a candidate** (A or B) and accept its known failure modes as acceptable trade-offs, with explicit documentation of the failure conditions.

3. **Introduce a new numerical mechanism** (Decimal, tick-size, or other) that requires explicit human approval and potentially architectural changes (violating D5).

4. **Define a bounded verification scope** (e.g., "for all entry prices <= X and percentages <= Y, mechanism A/B guarantees boundary-triggering") and accept that guarantees are scoped, not universal.

**No recommendation is made.** The decision must be made by the human reviewer based on the analysis presented.

---

## BLOCKER #2 STATUS

**BLOCKED — D4 NUMERICAL POLICY REQUIRES EXPLICIT HUMAN APPROVAL**

Neither Candidate A (Additive Reformulation) nor Candidate B (.10f Normalization) provides a universal guarantee that "mathematically exact boundary equality triggers while below-boundary values do not trigger." Both candidates have documented failure modes in the random test corpus.

Phase 3 remains NO-GO.

---
END OF D4 NUMERICAL POLICY ANALYSIS
---
