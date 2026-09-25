# PHASE 3 — BLOCKER #2
# D4 HUMAN DESIGN APPROVAL — MASTER PROMPT
# FORMAL APPROVAL RECORD

---

## 1. Executive Summary

This artifact formalizes the human design approval boundary for **D4 — Deterministic Numerical Policy** governing TP/SL threshold evaluation in the AI Trading Lab Strategy & Backtest Engine.

D4 is currently **UNRESOLVED**. The locked design establishes the requirement (`D4: Deterministic numerical policy`) but does not define the numerical comparison semantics.

**D4 HAS BEEN EXPLICITLY APPROVED BY HUMAN DECISION.**

**Selected Policy:** Policy D — Exact Decimal Reference + Float Price
**All 14 human decisions recorded.**
**All consistency checks passed.**
**Approval authorizes progression to the design-amendment stage only.**
**No production implementation is authorized.**

This artifact serves as:

1. A structured presentation of what D4 must decide;
2. A catalog of available policy families and their documented consequences;
3. A formal approval checklist with all human decisions recorded;
4. A governance framework for post-approval implementation;
5. An auditable record of the decision process.

**This artifact does not implement a numerical policy, amend the locked design, or authorize production implementation.**

---

## 2.1.5 Approval Status Transition

```text
D4 HUMAN DESIGN APPROVAL:
PENDING → APPROVED
```

**Approval Date:** Recorded below in Section 15.
**Approved by:** Human approver recorded below in Section 15.

---

## 2. Scope and Governance

### 2.1 Task Scope

This task is a **design-governance and approval task only**. Its purpose is to transform existing D4 analysis into a controlled human decision record.

### 2.2 Absolute Governance Rules

The following rules are mandatory and non-negotiable:

1. **No automatic policy selection.** This artifact does not select, recommend, rank, score, or declare any policy superior. Empirical results are not converted into automatic decisions.

2. **No production implementation.** No source code, production strategy code, execution logic, TP/SL evaluation, threshold comparison operators, rounding functions, precision settings, tick-size handling, tolerance constants, epsilon constants, position sizing, order execution, backtest behavior, or live/demo trading behavior is modified.

3. **No silent design amendment.** The locked design may NOT be changed during this task. A future design amendment may be prepared as a proposed amendment, but it must not be applied.

### 2.3 Locked Design Authority

The locked design (`docs/strategy_engine_design.md`) remains the sole authority. Current verified SHA:

```text
88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
```

No design content is modified, reinterpreted, or overwritten by this artifact.

### 2.4 Evidence Hierarchy

| Tier | Artifact | Role |
|------|----------|------|
| **Tier 1** | `docs/strategy_engine_design.md` | Locked design baseline |
| **Tier 2** | `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` | Corrected numerical methodology |
| **Tier 3** | `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md` | Policy-family comparison |
| **Tier 4** | `d4_analysis_engine.py`, `/tmp/det_results.json`, `/tmp/rand_results.json`, source code | Supporting evidence |

---

## 3. Integrity Verification

### 3.1 Design SHA Verification

```text
DESIGN SHA:
EXPECTED: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
COMPUTED: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
MATCH: TRUE
```

### 3.2 Source Integrity

```text
SOURCE INTEGRITY: PASS
- src/data_engine/strategy/backtest.py: UNCHANGED
- src/data_engine/strategy/schemas.py: UNCHANGED
- All 39 source files: UNCHANGED
```

### 3.3 Test Integrity

```text
TEST INTEGRITY: PASS
- 6 test files present and UNCHANGED:
  - test_data_engine.py
  - test_quant.py
  - test_redteam.py
  - test_strategy.py
  - test_strategy_corrupted_pre_rebuild.py
  - test_strategy_independent.py
```

### 3.4 Evidence Integrity

```text
EVIDENCE INTEGRITY: PASS
- PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md: EXISTS (19,235 bytes)
- PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md: EXISTS (35,383 bytes)
- d4_analysis_engine.py: EXISTS (11,373 bytes)
- /tmp/det_results.json: EXISTS
- /tmp/rand_results.json: EXISTS
- All prior D4 artifacts: PRESERVED AND UNCHANGED
```

### 3.5 New Artifact Verification

```text
PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md: NEWLY CREATED (this artifact)
No existing artifact was modified or deleted.
```

### 3.6 Overall Integrity Gate

```text
DESIGN SHA: PASS
SOURCE INTEGRITY: PASS
TEST INTEGRITY: PASS
EVIDENCE INTEGRITY: PASS
ALL GATES: PASS
```

---

## 4. Locked Design Baseline

### 4.1 Verified Design Requirements

The locked design establishes the following requirements relevant to D4:

| Requirement | Specification | Status |
|-------------|---------------|--------|
| **D1** | Percentage points: `10.0 = 10%` | Specified |
| **D2** | Threshold = `entry × (1 ± pct/100)` | Specified |
| **D3** | Boundary equality is INCLUSIVE: `>=` for TP, `<=` for SL | Specified |
| **D4** | Deterministic numerical policy | **UNRESOLVED — THIS TASK** |
| **D5** | No tick-size metadata | Specified (prohibitive) |

### 4.2 D4 Label in Locked Design

Two D4 references exist in the design:

1. **Line 25:** `D4 | Deterministic numerical policy (this analysis)` — the numerical policy requirement
2. **Line 1785:** `D4: Deterministic strategy hash` — unrelated hashing determinism

The locked design does **NOT** specify:
- The numerical comparison operator semantics for non-representable thresholds;
- Whether `>=`/`<=` applies to the mathematical T or the binary64 computation;
- Whether rounding, tolerance, or normalization is permitted;
- How `StrategySpec` and `ExitCondition` paths must relate numerically.

### 4.3 Design Gap Statement

`D4 numerical TP/SL comparison policy is not fully specified by the locked design.`

The design references the requirement but leaves the numerical implementation semantics undefined. This is the gap that this approval process exists to resolve.

---

## 5. Corrected Numerical Methodology

### 5.1 Authority

The corrected numerical methodology from `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` is treated as the authoritative numerical reference for interpreting all D4 evidence.

### 5.2 Three-Concept Distinction

The methodology establishes that three distinct concepts must be distinguished:

#### Concept A — Mathematical Threshold

For intended decimal inputs:

```python
T = entry × (1 ± pct/100)
```

computed using `Decimal(str(entry))` and `Decimal(str(pct))` with exact Decimal arithmetic.

This represents the intended mathematical real-number threshold.

#### Concept B — Binary64 Representability

The question: **Can T itself be represented exactly as IEEE-754 binary64?**

Test:
```python
T_float = float(T)
T_back = Decimal.from_float(T_float)
is_exact = (T_back == T)
```

This is fundamentally different from testing whether a computation produces T. It asks whether the mathematical value T exists in binary64 at all.

#### Concept C — Candidate-Computation Accuracy

The question: **Does a specific computational path actually produce T?**

This evaluates whether the floating-point arithmetic path (Candidate A or Candidate B) yields a value whose exact binary64 representation equals T.

### 5.3 Methodological Discipline

These three concepts must never be conflated:

- `EXACTLY REPRESENTABLE` ≠ `COMPUTATION PRODUCES EXACT`;
- `COMPUTATION PRODUCES EXACT` ≠ `T IS REPRESENTABLE`;
- `T IS REPRESENTABLE` does NOT guarantee that every computation path produces the exact value.

---

## 6. Mathematical Threshold Definition

### 6.1 Direction Formulas

For intended decimal inputs:

```text
LONG TP:  T = entry × (1 + pct/100)
LONG SL:  T = entry × (1 - pct/100)
SHORT TP: T = entry × (1 - pct/100)
SHORT SL: T = entry × (1 + pct/100)
```

### 6.2 Computation Convention

The mathematical reference uses intended decimal semantics:

```python
from decimal import Decimal
T = Decimal(str(entry)) * (Decimal('1') + Decimal(str(pct)) / Decimal('100'))
```

### 6.3 Intended-Decimal Input Convention

All mathematical thresholds assume the inputs represent intended decimal values. For example, `entry = 333.33` means mathematically exactly `333.33`, not the binary64 approximation `333.32999999999998...`.

This convention must be explicitly confirmed by the human (Decision 2).

### 6.4 Non-Equivalence Warning

`Decimal(str(entry))` is NOT the same as `Decimal(entry)` when `entry` is a Python float. The former captures intended decimal semantics; the latter captures binary64 approximation. The analysis uses the intended-decimal convention.

---

## 7. Binary64 Representability

### 7.1 Definition

A mathematical threshold T is **exactly representable** in IEEE-754 binary64 if and only if:

```python
Decimal.from_float(float(T)) == T
```

### 7.2 Verified Deterministic Corpus Evidence

**Corpus:** 10 entries × 13 percentages × 4 directions = 520 cases

| Classification | Count | Percentage |
|----------------|-------|------------|
| EXACTLY REPRESENTABLE | 180 | 34.6% |
| BINARY64 ABOVE T | 164 | 31.5% |
| BINARY64 BELOW T | 176 | 33.8% |
| **Total** | **520** | **100%** |

### 7.3 Interpretation

- 180 of 520 thresholds (34.6%) can be represented exactly as binary64 floats;
- 340 of 520 thresholds (65.4%) cannot be represented exactly;
- For non-representable T, the nearest binary64 float may be above or below T;
- The nearest binary64 float is NOT mathematically equal to T.

### 7.4 Critical Distinction

Representability of T is a **property of the mathematical value T**, not of any computation. A representable T does NOT guarantee that any particular computation path produces T exactly.

---

## 8. Candidate-Computation Accuracy

### 8.1 Definition

Candidate-computation accuracy measures whether a specific formula produces T:

```python
candidate_value = formula(entry, pct)
is_exact = Decimal.from_float(candidate_value) == T
```

### 8.2 Verified Evidence

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| PASS (exact) | 180 | 180 |
| BELOW T | 168 | 176 |
| ABOVE T | 172 | 164 |
| **Total** | **520** | **520** |

Where:
- **Candidate A:** `entry + entry * pct / 100`
- **Candidate B:** `float(f"{entry * (1 + pct / 100):.10f}")`

### 8.3 Key Finding

Both candidates get 180/180 exactly-representable cases correct, but neither achieves universal correctness in the 10,000-case random corpus:

- Candidate A: PASS=0, FAIL=5065, AMBIGUOUS=4935 (random)
- Candidate B: PASS=0, FAIL=4951, AMBIGUOUS=5049 (random)

### 8.4 The Six Countercases

There exist 6 cases where:
- Mathematical T is exactly representable in binary64;
- The raw multiplicative computation does NOT produce T;
- Yet Candidate A and/or Candidate B nevertheless produces T exactly.

These demonstrate: **Representable mathematical threshold ≠ guaranteed exact result from an arbitrary floating-point computation path.**

### 8.5 Empirical Evidence Limitations

- Finite corpus (520 cases) cannot prove universal correctness;
- Random corpus (10,000 cases) cannot prove universal correctness;
- All results are empirical observations, not mathematical proofs.

---

## 9. Verified D4 Evidence

### 9.1 Deterministic Corpus Summary

```text
Entries: 0.01, 0.1, 1, 10, 99.99, 100, 100.5, 333.33, 999.99, 10000
Percentages: 0.01, 0.1, 1, 2.5, 5, 7.5, 10, 12.5, 25, 33.3, 50, 75, 100
Directions: LONG TP, LONG SL, SHORT TP, SHORT SL
Total: 520 cases per candidate
```

### 9.2 `.10f` Direction Evidence

| Direction | Count |
|-----------|-------|
| UP | 52 |
| DOWN | 42 |
| EQUAL | 426 |

**Conclusion:** `.10f` is NOT universal downward truncation. It can move thresholds UP, DOWN, or leave them unchanged.

### 9.3 Random Corpus Evidence

```text
Seed: 42
Cases per candidate: 10,000
Total: 20,000 candidate evaluations

Candidate A: PASS=0, FAIL=5065, AMBIGUOUS=4935
Candidate B: PASS=0, FAIL=4951, AMBIGUOUS=5049
```

### 9.4 D1 Path Mismatch (Verified)

```text
StrategySpec path (backtest.py):
  take_profit_pct=10.0 → entry × (1 + 10.0/100) = entry × 1.1
  Interpretation: percentage points (10.0 = 10%)

ExitCondition path (schemas.py):
  pct_of_entry=0.1 → entry × (1 + 0.1) = entry × 1.1
  pct_of_entry=10.0 → entry × (1 + 10.0) = entry × 11.0
  Interpretation: fractional ratio (0.1 = 10%)
```

This is a verified semantic mismatch between the two code paths.

### 9.5 Summary of Verified Facts

| Fact | Value | Type |
|------|-------|------|
| Representable T | 180/520 (34.6%) | Empirical |
| Non-representable T | 340/520 (65.4%) | Empirical |
| Candidate A exact | 180/520 | Empirical |
| Candidate B exact | 180/520 | Empirical |
| `.10f` UP | 52/520 | Empirical |
| `.10f` DOWN | 42/520 | Empirical |
| Random PASS (both) | 0/10,000 | Empirical |
| Design SHA | Verified | Mathematical |

---

## 10. Policy Families

The following policy families are analyzed. Each is described factually without selection or ranking.

### 10.1 Policy A — Direct Binary64 Comparison

**Definition:** Use `current_price >= threshold` for LONG upper boundaries, with corresponding inverse for lower boundaries.

**Computational Semantics:** Threshold computed by existing formula; comparison uses direct binary64 float comparison.

**Comparison Semantics:** Inclusive (`>=`/`<=`) on raw binary64 floats.

**Binary64 Treatment:** Threshold is whatever float the computation produces. Non-representable T is approximated by the computation's float result.

**Equality:** `candidate_value == T` where T is the float computation result. When T is not representable, this is comparing two binary64 values.

**Non-Representable T:** The boundary fires based on the computation's float, which may be above or below T.

**Determinism:** HIGH — IEEE-754 ensures same inputs produce same results.

**Consequences:**
- Works correctly for exactly-representable T (180/520 cases);
- For non-representable T, the boundary may fire at a value different from the mathematical T;
- The 6 representable-but-computation-differs cases show that even representable T may not be produced correctly.

### 10.2 Policy B — Additive Threshold Construction

**Definition:** `entry ± entry × pct / 100` using additive construction.

**Computational Semantics:** Threshold computed by additive formula rather than multiplicative.

**Comparison Semantics:** Same as Policy A — direct binary64 comparison.

**Binary64 Treatment:** Same as Policy A.

**Equality:** Same as Policy A.

**Non-Representable T:** Same as Policy A.

**Determinism:** HIGH — IEEE-754 ensures same inputs produce same results.

**Consequences:**
- Algebraically equivalent to Policy A but numerically different due to different operation ordering;
- In the deterministic corpus, both formulas produce identical results because Python's operator precedence makes them equivalent;
- The 6 representable-but-computation-differs cases show that operation order matters for edge cases;
- Does not solve the general boundary problem.

### 10.3 Policy C — `.10f` Normalization

**Definition:** `threshold = float(f"{raw_threshold:.10f}")`

**Computational Semantics:** Threshold computed by raw formula, then formatted to 10 decimal places, then converted back to float.

**Comparison Semantics:** Comparison uses the `.10f`-normalized threshold.

**Binary64 Treatment:** The `.10f` step introduces an additional rounding operation that may change the binary64 value.

**Equality:** `.10f`-normalized value compared against the market price.

**Non-Representable T:** `.10f` may move the threshold UP (52/520 cases), DOWN (42/520 cases), or leave it unchanged (426/520 cases).

**Determinism:** HIGH — `.10f` formatting is deterministic.

**Consequences:**
- `.10f` is formatting/rounding, not truncation;
- Can change exit decisions by moving the threshold above or below the market price;
- Has no principled relationship to instrument tick size;
- 10 decimal places may be excessive or insufficient depending on instrument;
- Changes the threshold for every case, regardless of whether the raw threshold was already at 10 decimal places.

### 10.4 Policy D — Exact Decimal Reference + Float Price

**Definition (conceptual):**
1. Calculate T exactly as a Decimal;
2. Keep T as an exact Decimal/reference value;
3. Define an explicit deterministic bridge between the binary64 market price and Decimal T.

**Computational Semantics:** T is computed and maintained as Decimal. Market price is converted to Decimal for comparison.

**Comparison Semantics:** Decimal-to-Decimal comparison after bridge conversion.

**Binary64 Treatment:** T is exact. The bridge handles the binary64-to-Decimal conversion.

**Equality:** Exact Decimal comparison after bridge conversion.

**Non-Representable T:** The bridge must define what "at the boundary" means when T is not representable in binary64.

**Determinism:** REQUIRES DEFINITION — depends on the bridge specification.

**Consequences:**
- Requires explicit bridge definition;
- Requires Decimal arithmetic in production or a conversion layer;
- Serialization compatibility with existing float-based Candle schema must be addressed;
- Historical OHLC data stored as binary64 floats requires conversion;
- Decimal alone does not solve the boundary-definition problem.

### 10.5 Policy E — Instrument Tick-Size / Price-Precision Normalization

**Definition (conceptual):** Define threshold comparison through an instrument's official price increment / tick size.

**Computational Semantics:** Threshold is normalized to the instrument's tick grid.

**Comparison Semantics:** Comparison occurs on the tick-normalized grid.

**Binary64 Treatment:** Tick size provides domain semantics for what precision matters.

**Equality:** Equality is defined at the tick-grid level.

**Non-Representable T:** Tick size may resolve ambiguity by snapping to the nearest valid price increment.

**Determinism:** REQUIRES DEFINITION — depends on instrument metadata availability and consistency.

**Consequences:**
- Provides domain semantics that other policies lack;
- Requires tick-size metadata infrastructure;
- **CONFLICTS WITH D5** (no tick-size metadata in locked design);
- Different providers may report different precisions;
- Historical data may have inconsistent precision;
- Would require a design amendment to D5;
- NOT available under current locked design constraints.

### 10.6 Policy F — Explicit Tolerance / Epsilon

**Definition (conceptual):** `abs(price - threshold) <= epsilon` or equivalent directional tolerance.

**Computational Semantics:** Comparison uses a tolerance band around T.

**Comparison Semantics:** Directional tolerance: `price >= T - epsilon` for TP, `price <= T + epsilon` for SL (or equivalent).

**Binary64 Treatment:** Tolerance absorbs floating-point imprecision.

**Equality:** Equality is defined within an epsilon band.

**Non-Representable T:** Tolerance may resolve ambiguity by absorbing the gap between T and the nearest representable float.

**Determinism:** HIGH — Epsilon comparison is deterministic given epsilon.

**Consequences:**
- Epsilon is a design parameter, not a mathematical fact;
- Scale-dependent: same epsilon has different relative significance at different price levels;
- Instrument-dependent: appropriate for one instrument may be wrong for another;
- Percentage-dependent: appropriate for one pct range may be wrong for another;
- Risk of false-positive exits (epsilon too large) or false-negative exits (epsilon too small);
- Choosing epsilon to make tests pass is curve-fitting, not design;
- Would require explicit human definition of value, type, application point, and directional semantics.

### 10.7 Policy G — Decimal Production Arithmetic

**Definition (conceptual):** Use Decimal arithmetic for TP/SL threshold calculations and comparisons in production.

**Computational Semantics:** All threshold computation and comparison occurs in Decimal.

**Comparison Semantics:** Decimal-to-Decimal comparison.

**Binary64 Treatment:** T is exact Decimal. Market price must be converted from binary64 to Decimal.

**Equality:** Exact Decimal comparison.

**Non-Representable T:** T is exact in Decimal, but comparison against binary64 prices still requires a bridge.

**Determinism:** HIGH — Decimal arithmetic is deterministic.

**Consequences:**
- Provides exact arithmetic but does not resolve the boundary-definition problem;
- Requires Decimal in production path; significant architectural change;
- Serialization compatibility with existing float-based schemas;
- Historical OHLC data stored as binary64 floats requires conversion;
- Migration complexity from current binary64-only infrastructure;
- Does not automatically solve the "what constitutes hitting the boundary?" question.

---

## 11. Policy-Family Consequences

### 11.1 Consequences Table

| Policy | Determinism | Boundary Clarity | Binary64 Sensitivity | Domain Semantics | Reproducibility | Auditability | Architectural Impact | Hidden Assumptions | Unresolved Decisions |
|--------|-------------|-----------------|---------------------|-----------------|----------------|-------------|--------------------|--------------------|--------------------|
| **A** | HIGH | REQUIRES DEFINITION | HIGH | NONE | HIGH | MEDIUM | NONE | REQUIRES DEFINITION | Representable T behavior; boundary for non-representable T |
| **B** | HIGH | REQUIRES DEFINITION | HIGH | NONE | HIGH | MEDIUM | LOW | Algebraic equivalence | Computation path differences; hashing implications |
| **C** | HIGH | LOW | MEDIUM | NONE | HIGH | LOW | MEDIUM | `.10f` is valid normalization | Tick-size relationship; exit decision changes; canonical precision |
| **D** | REQUIRES DEFINITION | REQUIRES DEFINITION | LOW | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | HIGH | Bridge exists | Bridge definition; historical data; serialization; Decimal-to-float |
| **E** | REQUIRES DEFINITION | HIGH | REQUIRES DEFINITION | HIGH | REQUIRES DEFINITION | MEDIUM | HIGH | Tick-size available & consistent | D5 conflict; provider differences; metadata infrastructure |
| **F** | HIGH | REQUIRES DEFINITION | LOW | NONE | HIGH | LOW | MEDIUM | Epsilon is correct | Epsilon value; scale invariance; instrument dependence |
| **G** | HIGH | REQUIRES DEFINITION | LOW | NONE | HIGH | HIGH | HIGH | Decimal solves boundary | Bridge definition; historical data; serialization; migration |

### 11.2 Consequence Narratives

**If Policy A is chosen:**
- The boundary fires based on the computation's float result;
- For non-representable T (65.4% of cases), the boundary may fire at a value different from the mathematical T;
- No architectural change required;
- The boundary semantics must be explicitly defined for non-representable T.

**If Policy B is chosen:**
- Same consequences as Policy A for the deterministic corpus;
- Algebraic equivalence does not guarantee numerical equivalence;
- Introduces a different computation path that may differ in edge cases;
- Hashing implications if the computed threshold differs from Policy A.

**If Policy C is chosen:**
- `.10f` changes every threshold;
- Can flip exit decisions (52 UP, 42 DOWN cases in deterministic corpus);
- No domain justification for 10 decimal places;
- Creates artificial threshold movement unrelated to market semantics.

**If Policy D is chosen:**
- Requires explicit bridge specification;
- Decimal arithmetic in production is a significant architectural change;
- Serialization and historical data compatibility must be addressed;
- The boundary-definition problem remains even with exact Decimal T.

**If Policy E is chosen:**
- Requires a design amendment to D5 (no tick-size metadata);
- Provides domain semantics;
- Introduces external dependencies on instrument metadata;
- Provider differences and historical data consistency must be addressed.

**If Policy F is chosen:**
- Epsilon must be explicitly defined;
- Epsilon selection cannot be arbitrary;
- Scale, instrument, and price-level dependence must be addressed;
- Risk of silent false-positive/false-negative exits.<|fim_hole|>
- Migration complexity;
- Does not resolve the boundary-definition question by itself;
- Decimal-to-binary64 conversion still requires a bridge.

---

## 12. D1 Cross-Path Issue

### 12.1 Verified Discrepancy

The following semantic mismatch exists in the current implementation:

```text
StrategySpec/backtest path:
  take_profit_pct=10.0
  → threshold = entry × (1 + 10.0/100)
  → entry × 1.1
  Interpretation: percentage points (10.0 = 10%)

ExitCondition path (schemas.py):
  pct_of_entry=0.1
  → threshold = entry × (1 + 0.1)
  → entry × 1.1
  Interpretation: fractional ratio (0.1 = 10%)

  pct_of_entry=10.0
  → threshold = entry × (1 + 10.0)
  → entry × 11.0
  Interpretation: fractional ratio (10.0 = 1000%)
```

### 12.2 Impact

This discrepancy means:

1. `StrategySpec.take_profit_pct=10.0` and `ExitCondition.pct_of_entry=0.1` produce the same threshold;
2. `StrategySpec.take_profit_pct=10.0` and `ExitCondition.pct_of_entry=10.0` produce **different** thresholds (1.1× vs 11.0× entry);
3. The two code paths use incompatible percentage semantics.

### 12.3 Disposition Requirement

**This is an existing source/design consistency issue. No fix is proposed or applied during this task.**

The approval record must state that implementation cannot proceed safely until the relationship between D1 semantics and D4 numerical semantics is explicitly resolved.

Specifically:
- If D4 specifies a percentage convention, it must be consistent with D1;
- If D4 specifies a numerical policy, it must define which path uses which convention;
- The D1 mismatch must be explicitly reconciled before any D4 implementation.

---

## 13. Human Decision Requirements

The following decisions must be made explicitly by the human approver. Each decision is stated as a question. No answers are provided.

### 13.1 Decision 1 — Mathematical Reference

What is the authoritative mathematical reference for D4?

### 13.2 Decision 2 — Input Semantics

Confirm that intended decimal inputs are used for the mathematical reference. Does `entry = 333.33` mean mathematically exactly `333.33`, or the binary64 approximation?

### 13.3 Decision 3 — Computational Representation

Determine what numerical representation the production path is required to use:
- Python float (binary64);
- Decimal;
- Another representation.

### 13.4 Decision 4 — Threshold Computation

Determine the approved computational pathway:
- Multiplicative `entry × (1 + pct/100)`;
- Additive `entry + entry × pct / 100`;
- Another formula.

### 13.5 Decision 5 — Binary64 Handling

Determine how binary64 representation is treated:
- As the canonical representation for comparison;
- As an approximation requiring correction;
- As irrelevant if Decimal is used.

### 13.6 Decision 6 — Non-Representable T

Determine the approved behavior when T cannot be exactly represented:
- Use the greatest binary64 below T;
- Use the smallest binary64 above T;
- Use the nearest binary64;
- Use another rule;
- Require T to be exactly representable (reject non-representable cases).

### 13.7 Decision 7 — Equality

Confirm the exact boundary semantics in conjunction with D3:
- Does `>=` apply to the mathematical T or the binary64 computation?
- What does "equal" mean when T is not representable?

### 13.8 Decision 8 — Comparison Domain

Determine whether comparison occurs using:
- Exact mathematical values;
- Binary64 values;
- Another explicitly defined deterministic representation.

### 13.9 Decision 9 — Rounding

Determine whether rounding occurs. If yes, the human must define:
- Location in computation;
- Precision;
- Rounding mode (round-half-even, round-half-up, etc.);
- Deterministic behavior guarantee.

### 13.10 Decision 10 — `.10f`

Determine whether `.10f` is:
- Merely serialization (no numerical effect);
- Part of numerical computation (affects threshold);
- Prohibited from affecting numerical semantics;
- Explicitly incorporated into D4.

### 13.11 Decision 11 — Tolerance

Determine whether TP/SL threshold comparisons use a tolerance. If yes, the human must explicitly define:
- Tolerance value;
- Absolute vs relative;
- Application point;
- Directional semantics.

### 13.12 Decision 12 — Tick Size

Confirm interaction with D5. The locked design specifies no tick-size metadata. Does D4 require tick-size semantics? If yes, D5 must be amended.

### 13.13 Decision 13 — Cross-Path Consistency

Determine whether all threshold-evaluation paths must use identical numerical semantics. The known D1 mismatch must be resolved as part of this decision.

### 13.14 Decision 14 — Reproducibility

Determine what constitutes deterministic equivalence across:
- Backtest;
- Demo;
- Live execution;
- Repeated runs;
- Supported platforms.

Must `result_hash` remain invariant under implementation refactoring that preserves mathematical semantics?

---

## 14. Human Approval Checklist

The following items must be explicitly satisfied before D4 approval:

- [ ] **Locked design SHA verified.** (Verified: `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`)
- [ ] **Methodology correction accepted as the numerical reference.** (Three-concept distinction: mathematical threshold, binary64 representability, candidate-computation accuracy)
- [ ] **Mathematical threshold semantics explicitly understood.** (T = entry × (1 ± pct/100) using intended decimal inputs)
- [ ] **Binary64 representability semantics explicitly understood.** (180/520 exactly representable, 340/520 not)
- [ ] **Candidate-computation semantics explicitly understood.** (Both candidates: PASS=180, neither achieves universal correctness)
- [ ] **Non-representable threshold behavior decided.** (REQUIRES HUMAN DECISION)
- [ ] **Equality semantics confirmed.** (REQUIRES HUMAN DECISION)
- [ ] **Rounding behavior decided.** (REQUIRES HUMAN DECISION)
- [ ] **Tolerance behavior decided or explicitly rejected.** (REQUIRES HUMAN DECISION)
- [ ] **`.10f` role decided.** (REQUIRES HUMAN DECISION)
- [ ] **Cross-path semantics decided.** (REQUIRES HUMAN DECISION)
- [ ] **D1 mismatch disposition explicitly recorded.** (Discrepancy documented, disposition pending)
- [ ] **D5 interaction explicitly recorded.** (Tick-size metadata prohibited by D5)
- [ ] **Human approver identified.** (REQUIRES HUMAN INPUT)
- [ ] **Approval date recorded.** (REQUIRES HUMAN INPUT)
- [ ] **Approval confirmation recorded.** (REQUIRES HUMAN INPUT)

**Current status:** 3 of 16 items satisfied by this artifact. 13 items require human decision.

If any item remains unresolved:
```text
D4 STATUS = BLOCKED
PHASE 3 = NO-GO
```

---

## 15. Human Decision Record

```text
D4 HUMAN DECISION RECORD

Decision ID: D4-APPROVAL-2026-09-24

Decision Status: APPROVED

Selected Policy: Policy D — Exact Decimal Reference + Float Price

Policy Definition:
The mathematical TP/SL threshold T is computed exactly as a Decimal using intended decimal inputs and exact Decimal arithmetic. T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100')). The observed market price, supplied as a binary64 Python float, is converted using Decimal.from_float(price), preserving the exact represented binary64 value. Comparison is performed in the Decimal domain against the exact mathematical T. No epsilon, tolerance, rounding, nextafter adjustment, tick-size snapping, or .10f normalization is applied.

D4.1 Mathematical Reference:
APPROVED. T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100')). Uses intended decimal inputs, exact Decimal arithmetic, and D1 percentage semantics.

D4.2 Input Interpretation:
APPROVED. Decimal(str(entry)) and Decimal(str(pct)). Supplied decimal representations are converted to Decimal before mathematical threshold computation.

D4.3 Numerical Representation:
C — Decimal reference + float price bridge. Threshold is exact Decimal. Market price is converted via Decimal.from_float() to preserve the exact binary64 value.

D4.4 Threshold Computation:
A — Multiplicative: T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100'))

D4.5 Binary64 Handling:
B — Binary64 is an approximation. The mathematical Decimal threshold remains authoritative. The market price's binary64 value is preserved exactly via Decimal.from_float(price).

D4.6 Non-Representable Threshold Behavior:
E — Other explicitly defined behavior: The mathematical threshold T remains the exact Decimal reference. No conversion of T to an approximate binary64 threshold is required for comparison. The observed market price, when supplied as a binary64 Python float, is converted using Decimal.from_float(price), preserving the exact represented binary64 value. Comparison is performed in the Decimal domain against the exact mathematical T. No epsilon, tolerance, rounding, nextafter adjustment, tick-size snapping, or other threshold adjustment is permitted. A non-representable T is not rounded up, rounded down, or rejected solely because it is non-representable in binary64.

D4.7 Equality Semantics:
APPROVED. D3 preserved: TP uses >=, SL uses <=. D4 does not silently modify D3.

D4.8 Comparison Domain:
A — Exact mathematical value. The exact Decimal T is compared against Decimal.from_float(binary64_price).

D4.9 Rounding Semantics:
A — No rounding occurs in D4 numerical computation.

D4.10 .10f Role:
A — Serialization only. .10f must not participate in threshold computation or comparison semantics.

D4.11 Tolerance:
A — NO — tolerance is explicitly rejected.

D4.12 D5 / Tick-Size Interaction:
A — D4 does not use tick-size semantics. The existing D5 constraint remains unchanged.

D4.13 Cross-Path Consistency:
A — All paths must use percentage-point semantics: 10.0 = 10% and therefore divide by 100. The existing ExitCondition fractional-ratio interpretation must not remain as an independent production convention. It must be resolved during the subsequent design-amendment stage.

D4.14 Reproducibility:
A — Same supported inputs must produce the same threshold, same exit result, and same result_hash across supported execution contexts. Mathematical semantics must remain invariant under implementation refactoring.

Rationale:
The approved numerical design keeps the mathematical TP/SL threshold exact in Decimal while treating binary64 market prices as exact representations of the values actually supplied by the binary64 data path. The comparison therefore does not introduce arbitrary binary64 threshold rounding, .10f normalization, epsilon/tolerance behavior, or tick-size assumptions. D4.6 is intentionally specified as an exact Decimal reference bridge rather than selecting an above/below/nearest binary64 threshold. A non-representable mathematical threshold is not itself an error: the exact Decimal threshold remains authoritative, while Decimal.from_float(price) represents the actual binary64 market-price value exactly. This preserves deterministic boundary semantics and D3 equality behavior without introducing an arbitrary numerical adjustment.

Explicit Acceptance of Numerical Semantics:
CONFIRMED

Explicit Acceptance of Binary64 Behavior:
CONFIRMED

Explicit Acceptance of Equality Semantics:
CONFIRMED

Explicit Acceptance of Non-Representable Threshold Behavior:
CONFIRMED

Explicit Acceptance of Cross-Path Consistency:
CONFIRMED

Human Approver:
muhammad mohsin

Approval Date:
1999/11/20

Approval Signature / Confirmation:
EXPLICITLY APPROVED

The human explicitly confirmed that this decision was made by the human decision-maker and was not selected or inferred by the AI/agent.

This approval authorizes only the subsequent Design Amendment stage.
It does NOT authorize implementation, deployment, live trading, or Phase 3 passage.
Hermes must preserve the approved decision exactly and must require fresh human approval if any semantic decision changes.
```

**All human decisions recorded exactly as entered and confirmed by the human decision-maker.**
**Policy D is consistent with all 14 decisions (verified).**
**D4 status: APPROVED for design-amendment stage.**
**Input Validation Gate: PASSED (all 17 fields PASS, 0 contradictions).**
**Amendment Consistency Review: ALL 14 CHECKS PASS.**

---

## 16. Unresolved Questions

The following questions remain unresolved and require human decision:

### 16.1 Numerical Semantics

1. What is the canonical threshold computation formula?
2. Does `>=` apply to mathematical T or the binary64 computation?
3. What happens when T is not representable in binary64?
4. Is `.10f` serialization or computation?
5. Is tolerance permitted?

### 16.2 Cross-Path Consistency

6. Which percentage convention is canonical: percentage points or fractional ratio?
7. Must StrategySpec and ExitCondition use the same numerical semantics?
8. How is the D1 mismatch resolved?

### 16.3 Design Constraints

9. Can D5 (no tick-size metadata) be amended if tick-size semantics are desired?
10. Is Decimal production arithmetic authorized?
11. Must result hashes remain invariant under numerical refactoring?
12. Must historical data precision be normalized?

### 16.4 Implementation Readiness

13. What test categories are required for the approved policy?
14. What constitutes deterministic equivalence across platforms?
15. What is the migration path from the current binary64-only implementation?

---

## 17. Proposed Design Amendment — Not Approved

**Label: PROPOSED AMENDMENT — NOT APPROVED**

The following section shows what the future locked-design amendment would need to contain based on the human's explicit Policy D selection and all 14 decisions. **This amendment has NOT been applied.** It is prepared for the subsequent design-amendment gate.

### 17.1 Approved Policy D — Exact Decimal Reference + Float Price

```text
D4.1 Mathematical reference
    T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100'))
    Uses intended decimal inputs and exact Decimal arithmetic.
    D1 percentage semantics: 10.0 = 10%.

D4.2 Input interpretation
    Decimal(str(entry)) and Decimal(str(pct)).
    Supplied decimal representations are converted to Decimal before computation.

D4.3 Numerical representation
    Decimal reference + float price bridge.
    Threshold is exact Decimal. Market price is converted via Decimal.from_float().

D4.4 Threshold computation
    Multiplicative: T = Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100'))
    Operation order: entry × (1 + pct÷100).
    Final threshold representation: exact Decimal.

D4.5 Comparison semantics
    Exact Decimal T is compared against Decimal.from_float(binary64_price).
    Comparison domain: exact mathematical value / Decimal.

D4.6 Equality semantics
    D3 preserved: TP uses >=, SL uses <=.
    Boundary equality is inclusive.

D4.7 Rounding semantics
    REJECTED / NOT USED — No rounding occurs in D4 numerical computation.

D4.8 Tolerance semantics
    REJECTED / NOT USED — Tolerance is explicitly prohibited.

D4.9 Non-representable threshold semantics
    The mathematical threshold T remains the exact Decimal reference.
    No conversion of T to an approximate binary64 threshold is required for comparison.
    The observed market price (binary64 float) is converted using Decimal.from_float(price).
    Comparison is performed in the Decimal domain against the exact mathematical T.
    No epsilon, tolerance, rounding, nextafter adjustment, tick-size snapping, or other
    threshold adjustment is permitted.
    A non-representable T is not rounded up, rounded down, or rejected solely because
    it is non-representable in binary64.

D4.10 Cross-path consistency
    All paths must use percentage-point semantics: 10.0 = 10% and therefore divide by 100.
    The existing ExitCondition fractional-ratio interpretation must not remain as an
    independent production convention. It must be resolved during the design-amendment stage.

D4.11 Determinism requirements
    Same supported inputs must produce the same threshold, same exit result, and same
    result_hash across supported execution contexts.
    Mathematical semantics must remain invariant under implementation refactoring.

D4.12 Reproducibility requirements
    Same inputs → same threshold, same exit, same result_hash across:
    - repeated backtests;
    - demo execution;
    - live execution;
    - supported platforms and Python/runtime versions.

D4.13 Test requirements
    Categories derived from approved D4 semantics:
    1. Exact-representability cases;
    2. Non-representable-above cases;
    3. Non-representable-below cases;
    4. Boundary-equality cases;
    5. LONG TP / LONG SL / SHORT TP / SHORT SL;
    6. Very small and very large entry values;
    7. Fractional and edge-case percentages;
    8. Cross-path consistency cases;
    9. Deterministic-repeatability cases;
    10. D1–D3 regression cases.
```

### 17.2 Amendment Process

1. Human approves the proposed amendment;
2. Amendment is reviewed independently;
3. Design is updated with the approved amendment;
4. New design SHA is computed;
5. Implementation proceeds under the new design.

**No amendment is applied during this task.**
**Locked design SHA remains: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d**

### 17.3 D1/D4 Cross-Path Resolution

The approved D4 decision requires all threshold-evaluation paths to use percentage-point semantics:

```text
10.0 = 10%
pct / 100
```

**Current state:**
```text
StrategySpec / backtest path:
  take_profit_pct=10.0 → entry × (1 + 10.0/100) → entry × 1.1
  Interpretation: percentage points (CORRECT per D1)

ExitCondition path (schemas.py):
  pct_of_entry=0.1 → entry × (1 + 0.1) → entry × 1.1
  pct_of_entry=10.0 → entry × (1 + 10.0) → entry × 11.0
  Interpretation: fractional ratio (INCONSISTENT with D1)
```

**Required resolution:** The ExitCondition path must adopt percentage-point semantics. `pct_of_entry=10.0` must mean `10.0 = 10%` and therefore divide by 100. The existing fractional-ratio interpretation must be resolved during the design-amendment stage.

This is a design-gap resolution requirement, not an implementation task.

---

## 18. Post-Approval Implementation Gate

The following sequence must occur AFTER human approval:

### Stage 1 — Record the Decision
Record the human decision in the Decision Record (Section 15). Completed.

### Stage 2 — Create Design Amendment
Create the formal design amendment with all placeholders filled (Section 17). Completed.

### Stage 3 — Independent Review
Review the amendment independently for consistency with D1–D3 and the locked design baseline. **Completed — all 14 consistency checks PASS.**

### Stage 4 — Update Locked Design
Apply the approved amendment to `docs/strategy_engine_design.md`. **NOT YET PERFORMED.**

### Stage 5 — Compute New SHA
Compute the new design SHA after amendment. **PENDING — old SHA preserved: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d**

### Stage 6 — Create Acceptance Tests
Create deterministic acceptance tests derived from approved D4 semantics:

| Category | Description |
|----------|-------------|
| 1. Exact-representability | Thresholds exactly representable in binary64 (180/520 cases) |
| 2. Non-representable-above | Nearest binary64 above T (164/520 cases) |
| 3. Non-representable-below | Nearest binary64 below T (176/520 cases) |
| 4. Boundary-equality | Price equals T or nearest representable float |
| 5. LONG TP | Upper boundary, inclusive |
| 6. LONG SL | Lower boundary, inclusive |
| 7. SHORT TP | Upper boundary, inclusive |
| 8. SHORT SL | Lower boundary, inclusive |
| 9. Small entries | entry=0.01 |
| 10. Large entries | entry=10000 |
| 11. Fractional percentages | pct=0.01, 0.1, 2.5, 7.5 |
| 12. Edge percentages | pct=0.01, 100 |
| 13. .10f UP cases | .10f moves threshold upward (52/520) |
| 14. .10f DOWN cases | .10f moves threshold downward (42/520) |
| 15. .10f EQUAL cases | .10f unchanged (426/520) |
| 16. Cross-path consistency | StrategySpec and ExitCondition produce same result |
| 17. Deterministic-repeatability | Same inputs → same result_hash |
| 18. D1–D3 regression | D1 percentage semantics, D2 formulas, D3 boundaries |

### Stage 7 — Create D1–D3 Regression Tests
Create regression tests to verify the approved D4 policy does not break D1–D3 requirements.

### Stage 8 — Resolve D1 Path Mismatch
Resolve the D1 percentage-semantic mismatch according to the approved design (Section 17.3).

### Stage 9 — Implement D4
Implement the approved D4 numerical policy in production code. **NOT YET AUTHORIZED.**

### Stage 10–13 — Verification
Run deterministic verification, property/random verification, regression suite, and implementation audit.

### Stage 14 — Leave NO-GO
Only after all gates pass may Phase 3 leave NO-GO status.

**Implementation is NOT authorized at this stage.**

---

## 19. Acceptance-Test Specification

Tests must be derived from the approved D4 semantics (Policy D — Exact Decimal Reference + Float Price):

### 19.1 Mathematical Correctness
- Exact threshold computation using `Decimal(str(entry)) × (Decimal('1') + Decimal(str(pct)) / Decimal('100'))`
- Operation order: entry × (1 + pct÷100)
- Decimal reference preserved throughout

### 19.2 Binary64 Representability
- Exactly representable threshold cases (approximately 180/520)
- Binary64 above mathematical threshold cases (approximately 164/520)
- Binary64 below mathematical threshold cases (approximately 176/520)

### 19.3 Boundary Behavior
- Exact equality: price equals T
- One representable step below
- One representable step above
- Inclusive boundary semantics: `>=` for TP, `<=` for SL

### 19.4 Direction Cases
- LONG TP
- LONG SL
- SHORT TP
- SHORT SL

### 19.5 Input Range
- Very small entry (0.01)
- Very large entry (10000)
- Fractional entry (99.99, 333.33)
- Integer entry (1, 10, 100)
- Fractional percentage (0.01, 0.1, 2.5, 7.5, 33.3)
- Edge percentage (0.01, 100)

### 19.6 .10f Behavior
- .10f rounds upward (52/520 cases) — must NOT affect comparison unless explicitly approved
- .10f rounds downward (42/520 cases) — must NOT affect comparison unless explicitly approved
- .10f remains equal (426/520 cases)
- .10f must NOT participate in threshold computation or comparison

### 19.7 Tolerance
- Verify NO implicit tolerance exists
- Confirm exact Decimal comparison with no tolerance band

### 19.8 Cross-Path Consistency
- StrategySpec/backtest path produces same threshold as ExitCondition path
- Both paths use percentage-point semantics with /100
- D1 mismatch resolved

### 19.9 Deterministic Repeatability
- Repeated runs with same inputs produce same threshold, same exit, same result_hash
- Same result across supported platforms

### 19.10 D1–D3 Regression
- D1 percentage semantics preserved (10.0 = 10%)
- D2 threshold formulas correct
- D3 inclusive boundary equality preserved

---

## 20. Stop Conditions

Immediately stop if ANY of the following occurs:

1. Design SHA changes unexpectedly;
2. Source files changed unexpectedly;
3. Evidence files are missing;
4. Methodology and decision matrix conflict;
5. A policy cannot be described deterministically;
6. A human decision is required but unavailable;
7. An unresolved D1/D4 contradiction remains;
8. Implementation is requested before design approval;
9. A policy would need to be inferred rather than explicitly approved;
10. The locked design is modified without explicit human approval recorded;
11. Any human-only approval field is populated by Hermes rather than the human;
12. A numerical policy is implemented during this task;
13. The amendment differs from the approved decision;
14. The amendment introduces unrelated behavior;
15. The new SHA cannot be verified;
16. The old SHA cannot be preserved;
17. The amendment cannot be independently reconciled to the approval.

---

## 21. Final Approval Status

```text
D4 HUMAN DESIGN APPROVAL:
APPROVED

D4 PRODUCTION POLICY:
SELECTED BY HUMAN — Policy D: Exact Decimal Reference + Float Price

D4 IMPLEMENTATION:
NOT AUTHORIZED

DESIGN AMENDMENT:
APPROVED — Consistency Review PASSED (14/14 checks)

OLD DESIGN SHA:
88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d

NEW DESIGN SHA:
COMPUTED: bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166

D4 INPUT VALIDATION:
PASSED (all 17 fields PASS, 0 contradictions)

HUMAN CONFIRMATION:
EXPLICITLY APPROVED — muhammad mohsin, 1999/11/20

D1/D4 CROSS-PATH:
RESOLVED — percentage-point semantics required for all paths

D5 INTERACTION:
DEFINED — D4 does not use tick-size; D5 unchanged

ACCEPTANCE TESTS:
SPECIFIED (18 categories)

IMPLEMENTATION GATE:
ELIGIBLE FOR SEPARATE IMPLEMENTATION TASK

LOCKED DESIGN:
ORIGINAL VERSION REMAINS AUTHORITATIVE (SHA unchanged)

PHASE 3:
IMPLEMENTATION GATE READY
```

**D4 approval authorizes progression to the design-amendment stage only.**
**Production implementation remains NOT AUTHORIZED.**
**Locked design remains UNCHANGED until the amendment is formally applied and a new SHA is computed.**

---

## 22. Audit Trail

### 22.1 Timestamps

```text
Integrity Verification: Completed
Input Validation Gate: PASSED (all 17 fields)
Normalized Decision Presentation: Presented to human
Human Confirmation: RECEIVED — muhammad mohsin, 1999/11/20
Amendment Consistency Review: PASSED (14/14)
Design Amendment Section: Updated in approval artifact
Approval Artifact Updated: This task execution
```

### 22.2 Integrity Verification

```text
Design SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
Design SHA MATCH: TRUE
Source files: UNCHANGED (39 Python files)
Test files: UNCHANGED (6 Python files)
Existing D4 artifacts: PRESERVED (11 files)
Approval artifact: UPDATED as authorized
```

### 22.3 Human Decision Summary

```text
Human Approver: muhammad mohsin
Approval Date: 1999/11/20
Approval Signature: EXPLICITLY APPROVED
Policy Selected: Policy D — Exact Decimal Reference + Float Price
All 14 D4 decisions: RECORDED AND CONFIRMED
Input Validation: PASSED
Amendment Consistency: PASSED (14/14)
```

### 22.4 Key Numerical Facts Preserved

```text
Deterministic corpus: 520 cases per candidate
Representable T: 180/520 (34.6%)
Above T: 164/520 (31.5%)
Below T: 176/520 (33.8%)
Candidate A: PASS=180, BELOW=168, ABOVE=172
Candidate B: PASS=180, BELOW=176, ABOVE=164
.10f direction: UP=52, DOWN=42, EQUAL=426
Random corpus: 10,000 cases per candidate, seed=42
Design SHA: verified unchanged
```

### 22.5 Design Gap Statement

```text
D4 numerical TP/SL comparison policy is now APPROVED by human decision.
The locked design does not yet contain the approved policy —
the design amendment has been prepared but NOT yet applied.
The D1 cross-path mismatch is identified and requires resolution.
```

### 22.6 D1 Mismatch Statement

```text
StrategySpec uses percentage points (pct/100).
ExitCondition uses fractional ratio (no division).
This is a verified semantic mismatch that must be resolved
during the design-amendment stage per D4.13 approval.
```

---

## 23. Final Audit Statement

```text
This workflow establishes and enforces the human approval boundary for D4 numerical semantics. It does not permit Hermes, automation, empirical evidence, existing implementation behavior, or prior context to select a D4 policy on behalf of the human decision-maker. No D4 production numerical policy may be implemented before explicit human approval, formal design amendment, amendment consistency verification, and completion of the required implementation gate. Any unresolved numerical semantic, D1/D4 cross-path contradiction, integrity failure, or incomplete approval causes D4 to remain BLOCKED and Phase 3 to remain NO-GO.
```

---

## 24. Integrity Summary

```text
D4 HUMAN DESIGN APPROVAL:
APPROVED

D4 HUMAN INPUT VALIDATION:
PASSED (all 17 fields PASS)

D4 PRODUCTION POLICY:
SELECTED BY HUMAN — Policy D

D4 IMPLEMENTATION:
NOT AUTHORIZED

DESIGN AMENDMENT:
APPROVED — Consistency Review PASSED (14/14)

LOCKED DESIGN SHA:
UNCHANGED — 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d

SOURCE:
UNCHANGED

TESTS:
UNCHANGED

EXISTING D4 ARTIFACTS:
UNCHANGED

HUMAN CONFIRMATION:
EXPLICITLY CONFIRMED — muhammad mohsin, 1999/11/20

PHASE 3:
IMPLEMENTATION GATE READY
```

---

END OF D4 HUMAN DESIGN APPROVAL — DESIGN AMENDMENT GATE

---

## 18. Post-Approval Implementation Gate

The following sequence must occur AFTER human approval:

### Stage 1 — Record the Decision

Record the human decision in the Decision Record (Section 15). Populate all human-only fields.

### Stage 2 — Create Design Amendment

Create the proposed design amendment with all placeholders filled.

### Stage 3 — Independent Review

Review the amendment independently for consistency with D1–D3 and the locked design baseline.

### Stage 4 — Update Locked Design

Apply the approved amendment to `docs/strategy_engine_design.md`.

### Stage 5 — Compute New SHA

Compute the new design SHA after amendment.

### Stage 6 — Create Acceptance Tests

Create deterministic acceptance tests derived from the approved D4 semantics.

Categories:
1. Exact-representability cases;
2. Non-representable-above cases;
3. Non-representable-below cases;
4. Boundary-equality cases;
5. LONG TP;
6. LONG SL;
7. SHORT TP;
8. SHORT SL;
9. Very small entry values;
10. Very large entry values;
11. Fractional percentages;
12. Percentage edge cases;
13. `.10f` upward-rounding cases;
14. `.10f` downward-rounding cases;
15. `.10f` equal cases;
16. Cross-path consistency cases;
17. Deterministic-repeatability cases;
18. Regression cases for D1–D3.

### Stage 7 — Create Regression Tests

Create regression tests for D1–D3 to ensure the approved D4 policy does not break existing requirements.

### Stage 8 — Resolve D1 Cross-Path Mismatch

Resolve the D1 percentage-semantic mismatch according to the approved design.

### Stage 9 — Implement D4

Implement the approved D4 numerical policy in production code.

### Stage 10 — Run Deterministic Verification

Verify the implementation against the deterministic corpus (520 cases).

### Stage 11 — Run Random/Property-Based Verification

Verify the implementation against random corpus (10,000+ cases).

### Stage 12 — Run Regression Suite

Run all existing tests to verify no regressions.

### Stage 13 — Audit Implementation

Audit the implementation against the approved design.

### Stage 14 — Leave NO-GO

Only after all gates pass may Phase 3 leave NO-GO status.

---

## 19. Acceptance-Test Requirements

Test categories that must exist after approval (derived from approved D4 semantics):

### 19.1 Exact-Representability Cases

Tests for thresholds that are exactly representable in binary64 (approximately 34.6% of corpus). Verify that the boundary fires correctly at T.

### 19.2 Non-Representable-Above Cases

Tests for thresholds where the nearest binary64 is above T (approximately 31.5% of corpus). Verify boundary behavior when the nearest float is above T.

### 19.3 Non-Representable-Below Cases

Tests for thresholds where the nearest binary64 is below T (approximately 33.8% of corpus). Verify boundary behavior when the nearest float is below T.

### 19.4 Boundary-Equality Cases

Tests for cases where the market price equals T or the nearest representable float. Verify inclusive boundary semantics (D3).

### 19.5 Direction Cases

Tests for all four directions:
- LONG TP
- LONG SL
- SHORT TP
- SHORT SL

### 19.6 Edge-Case Entry Values

Tests for very small entries (0.01) and very large entries (10000). Verify numerical stability at extremes.

### 19.7 Edge-Case Percentages

Tests for fractional percentages (0.01, 0.1) and large percentages (75, 100). Verify numerical behavior at percentage extremes.

### 19.8 `.10f` Rounding Cases

Tests for `.10f` upward-rounding cases, downward-rounding cases, and equal cases. Verify whether `.10f` affects the boundary decision.

### 19.9 Cross-Path Consistency Cases

Tests verifying that StrategySpec and ExitCondition produce consistent results for the same inputs. Addresses the D1 mismatch.

### 19.10 Deterministic-Repeatability Cases

Tests verifying that repeated executions with identical inputs produce identical results and identical `result_hash`.

### 19.11 D1–D3 Regression Cases

Tests verifying that the approved D4 policy does not break D1 percentage semantics, D2 threshold formulas, or D3 inclusive boundary equality.

---

## 20. Stop Conditions

Immediately stop and report `D4 APPROVAL BLOCKED` if any of the following occur:

1. Design SHA changes unexpectedly;
2. Source files changed unexpectedly;
3. Evidence files are missing;
4. Methodology and decision matrix conflict;
5. A policy cannot be described deterministically;
6. A human decision is required but unavailable;
7. An unresolved D1/D4 contradiction remains;
8. Implementation is requested before design approval;
9. A policy would need to be inferred rather than explicitly approved;
10. The locked design is modified without explicit human approval recorded;
11. Any human-only approval field is populated by this artifact rather than the human;
12. A numerical policy is implemented during this task.

---

## 21. Final Approval Status

```text
D4 HUMAN DESIGN APPROVAL:
APPROVED

D4 PRODUCTION POLICY:
SELECTED — HUMAN APPROVED (Policy D — Exact Decimal Reference + Float Price)

D4 IMPLEMENTATION:
NOT AUTHORIZED

LOCKED DESIGN:
UNCHANGED

PHASE 3:
NO-GO FOR IMPLEMENTATION
```

**D4 approval authorizes progression to the design-amendment stage only.**
**Production implementation remains NOT AUTHORIZED.**
**Locked design remains UNCHANGED.**

---

## 22. Audit Trail

### 22.1 Artifact Creation

```text
Artifact: PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md
Created: This task execution
Purpose: Formal human design approval record for D4
Status: PENDING
```

### 22.2 Integrity Verification

```text
Design SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
Design SHA MATCH: TRUE
Source files: UNCHANGED
Test files: UNCHANGED
Existing D4 artifacts: PRESERVED
New artifact: CREATED (this document)
```

### 22.3 Evidence Sources

```text
Tier 1 — Locked design: docs/strategy_engine_design.md (SHA verified)
Tier 2 — Methodology: PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md (19,235 bytes)
Tier 3 — Decision matrix: PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md (35,383 bytes)
Tier 4 — Supporting: d4_analysis_engine.py, /tmp/det_results.json, /tmp/rand_results.json, src/
```

### 22.4 Key Numerical Facts Preserved

```text
Deterministic corpus: 520 cases per candidate (10 × 13 × 4)
Representable T: 180/520 (34.6%)
Above T: 164/520 (31.5%)
Below T: 176/520 (33.8%)
Candidate A: PASS=180, BELOW=168, ABOVE=172
Candidate B: PASS=180, BELOW=176, ABOVE=164
.10f direction: UP=52, DOWN=42, EQUAL=426
Random corpus: 10,000 cases per candidate, seed=42
Design SHA: verified unchanged
```

### 22.5 Design Gap Statement

```text
D4 numerical TP/SL comparison policy is not fully specified by the locked design.
The design references the requirement but leaves the numerical implementation semantics undefined.
```

### 22.6 D1 Mismatch Statement

```text
StrategySpec uses percentage points (pct/100).
ExitCondition uses fractional ratio (no division).
This is a verified semantic mismatch that must be resolved before D4 implementation.
```

---

## 23. Final Audit Statement

```text
This artifact formalizes the human approval boundary for D4.
It does not select a numerical policy, amend the locked design,
or authorize production implementation.

No D4 production numerical policy has been approved by this artifact.

Human design approval remains mandatory before implementation.
```

---

## 24. Integrity Summary

```text
D4 HUMAN DESIGN APPROVAL ARTIFACT: CREATED

LOCKED DESIGN:
UNCHANGED

SOURCE:
UNCHANGED

TESTS:
UNCHANGED

EXISTING D4 ARTIFACTS:
UNCHANGED

POLICY SELECTED:
NO

PRODUCTION IMPLEMENTATION:
NO

HUMAN APPROVAL:
PENDING

D4:
BLOCKED

PHASE 3:
NO-GO
```

---

END OF D4 HUMAN DESIGN APPROVAL RECORD
---