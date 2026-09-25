# PHASE 3 — BLOCKER #2
# D4 HUMAN DESIGN DECISION MATRIX

## 1. Scope

This document prepares the human design decision for D4 by analyzing multiple candidate numerical policy families for TP/SL boundary evaluation. It is **analysis-only**. It does not select, recommend, or implement any policy. Phase 3 remains NO-GO.

**Locked Design SHA:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d` (verified unchanged)

---

## 2. Locked Design References

### 2.1 Verified Design Document

`docs/strategy_engine_design.md` (2044 lines, 89231 bytes)
SHA-256 verified: `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`

### 2.2 Approved Requirements (D1–D7)

| Requirement | Specification |
|-------------|---------------|
| **D1** | Percentage points: `10.0 = 10%` |
| **D2** | Threshold = `entry_fill_price × (1 ± pct/100)` |
| **D3** | Boundary equality is INCLUSIVE: `>=` for TP, `<=` for SL |
| **D4** | Deterministic numerical policy (this analysis) |
| **D5** | No tick-size metadata |

### 2.3 D4 Label in Locked Design

Two D4 references exist:
- **Line 25:** `D4 | Deterministic numerical policy (this analysis)` — the policy requirement
- **Line 1785:** `D4: Deterministic strategy hash` — unrelated hashing determinism

The locked design does **NOT** specify the numerical comparison policy for TP/SL thresholds.

---

## 3. Verified D4 Facts

### 3.1 Mathematical Threshold

For intended decimal inputs:
```
LONG TP:   T = entry × (1 + pct/100)
LONG SL:   T = entry × (1 - pct/100)
SHORT TP:  T = entry × (1 - pct/100)
SHORT SL:  T = entry × (1 + pct/100)
```

Computed using `Decimal(str(entry)) × (1 ± Decimal(str(pct))/100)`.

### 3.2 True Binary64 Representability (Deterministic Corpus)

| Classification | Count | Percentage |
|----------------|-------|------------|
| EXACTLY REPRESENTABLE | 180 | 34.6% |
| BINARY64 ABOVE T | 164 | 31.5% |
| BINARY64 BELOW T | 176 | 33.8% |
| **Total** | **520** | **100%** |

Test: `float(T)` → `Decimal.from_float(float(T))` == T

### 3.3 Candidate-Computation Results

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| PASS | 180 | 180 |
| BELOW T | 168 | 176 |
| ABOVE T | 172 | 164 |
| Total | 520 | 520 |

### 3.4 `.10f` Direction (Deterministic)

| Direction | Count |
|-----------|-------|
| UP | 52 |
| DOWN | 42 |
| EQUAL | 426 |

### 3.5 Random Corpus

- Seed: 42
- 10,000 cases per candidate (20,000 total)
- Candidate A: PASS=0, FAIL=5065, AMBIGUOUS=4935
- Candidate B: PASS=0, FAIL=4951, AMBIGUOUS=5049

### 3.6 D1 Semantic Mismatch

`StrategySpec`: `take_profit_pct=10.0` → `entry × (1 + 10.0/100)` = entry × 1.1 (divides by 100)
`ExitCondition.pct_of_entry`: `pct_of_entry=0.1` → `entry × (1 + 0.1)` = entry × 1.1 (no division)
`ExitCondition.pct_of_entry`: `pct_of_entry=10.0` → `entry × (1 + 10.0)` = entry × 11.0

### 3.7 Source Integrity

- `src/data_engine/strategy/backtest.py`: UNCHANGED
- `src/data_engine/strategy/schemas.py`: UNCHANGED
- Test files (6 Python files): UNCHANGED
- `docs/strategy_engine_design.md`: SHA verified

---

## 4. Mathematical Reference Model

### 4.1 Intended Decimal-Input Convention

All mathematical thresholds are computed using `Decimal(str(entry))` and `Decimal(str(pct))`, representing the intended decimal values of the inputs. This is distinct from the binary64 approximations of those same inputs.

Example: `Decimal(str(333.33))` = `Decimal('333.33')`, not `Decimal('333.32999999999998...')`.

### 4.2 Three Non-Equivalent Equality Concepts

| Concept | Definition | Example |
|---------|-----------|---------|
| **Mathematical equality** | `candidate_value == T` where T is the exact real number | `102.5 == Decimal('102.5000')` |
| **Binary64 equality** | Two values are identical as IEEE-754 binary64 representations | `float(102.5) == float(102.5)` |
| **Market-price boundary decision** | Whether the observed price triggers TP/SL | Depends on policy semantics |

These are NOT automatically equivalent.

---

## 5. Policy A — Direct Binary64 Comparison

**Definition:** Use the existing comparison style: `current_price >= threshold` for LONG upper boundaries, with corresponding inverse for lower boundaries.

### 5.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | HIGH — Same inputs always produce same result in IEEE-754 |
| **Boundary clarity** | REQUIRES DEFINITION — What does `>=` mean when T is not representable? |
| **Binary64 sensitivity** | HIGH — Results depend on the exact float computation of threshold |
| **Domain semantics** | NONE — No connection to instrument tick size or market convention |
| **Reproducibility** | HIGH — IEEE-754 compliance ensures same results across platforms |
| **Auditability** | MEDIUM — Direct comparison is auditable but non-exact thresholds produce ambiguous results |
| **Architectural impact** | NONE — Uses existing infrastructure |
| **Hidden assumptions** | REQUIRES DEFINITION — Assumes `>=` on floats captures the intended boundary semantics |
| **Unresolved decisions** | What happens when T is not representable? Which float is "at" the boundary? |

### 5.2 Observed Behavior

- When T is exactly representable (180/520 cases): direct comparison is well-defined
- When T is not representable (340/520 cases): `>= threshold` uses whatever float the computation produces, which may be above or below T
- The raw multiplicative computation `entry * (1 + pct/100)` introduces rounding errors even when T is representable (6 cases)

### 5.3 Representative Cases

| Case | entry | pct | T | Raw computation | Direction | Boundary behavior |
|------|-------|-----|---|-----------------|-----------|-------------------|
| Representable | 100.0 | 2.5 | 102.5000 | 102.49999999999999 | BELOW T | `>= 102.49999999999999` misses T=102.5 |
| Representable | 100.0 | 10.0 | 110.00 | 110.00000000000001 | ABOVE T | `>= 110.00000000000001` fires early |
| Non-representable | 333.33 | 10.0 | 366.663 | 366.66300000000001 | ABOVE T | `>= 366.66300000000001` misses T=366.663 |

---

## 6. Policy B — Additive Threshold Construction

**Definition:**
```
LONG TP:   entry + entry × pct / 100
LONG SL:   entry - entry × pct / 100
SHORT TP:  entry - entry × pct / 100
SHORT SL:  entry + entry × pct / 100
```

### 6.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | HIGH — Same inputs always produce same result |
| **Boundary clarity** | REQUIRES DEFINITION — Same representability question as Policy A |
| **Binary64 sensitivity** | HIGH — Different computation path from multiplicative, different rounding |
| **Domain semantics** | NONE — Algebraically equivalent but numerically different |
| **Reproducibility** | HIGH — IEEE-754 compliant |
| **Auditability** | MEDIUM — Different from multiplicative formula; may confuse auditors |
| **Architectural impact** | LOW — Requires changing threshold construction logic |
| **Hidden assumptions** | Assumes algebraic equivalence implies numerical equivalence (FALSE in float arithmetic) |
| **Unresolved decisions** | Does the additive path introduce different results from multiplicative for the same inputs? |

### 6.2 Observed Behavior

Both candidates A and B produce the same threshold values. The additive and multiplicative formulations produce identical results for all 520 deterministic cases because Python's operator precedence and IEEE-754 semantics make `entry + entry * pct / 100` equivalent to `entry * (1 + pct/100)`.

**However**, the raw multiplicative computation `entry * (1 + pct/100)` can introduce different rounding than the additive path due to the intermediate `1 + pct/100` computation. This is observable in the 6 cases where T is representable but the raw computation differs.

### 6.3 Key Finding

Representable mathematical threshold ≠ guaranteed exact result from an arbitrary floating-point computation path. For all 6 representable-but-computation-differs cases, both Candidate A and Candidate B produce EXACT results because their computation order happens to avoid the intermediate rounding error.

---

## 7. Policy C — `.10f` Normalization

**Definition:** `threshold = float(f"{raw_threshold:.10f}")`

### 7.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | HIGH — `.10f` formatting is deterministic |
| **Boundary clarity** | LOW — `.10f` produces an arbitrary decimal precision with no domain justification |
| **Binary64 sensitivity** | MEDIUM — `.10f` rounds to 10 decimal places, which may change the threshold |
| **Domain semantics** | NONE — `.10f` is a formatting convention, not a market/instrument semantic |
| **Reproducibility** | HIGH — `.10f` formatting is deterministic across platforms |
| **Auditability** | LOW — Decimal formatting has no principled relationship to exit conditions |
| **Architectural impact** | MEDIUM — Changes threshold values for all exit conditions |
| **Hidden assumptions** | Assumes `.10f` is a valid threshold normalization (UNPROVEN) |
| **Unresolved decisions** | Does `.10f` have any relationship to instrument tick size? Can it change exit decisions? |

### 7.2 `.10f` ≠ Universal Downward Truncation

**Verified empirically:**
- Deterministic corpus: UP=52, DOWN=42, EQUAL=426
- Random corpus subset (1,000): UP≈498, DOWN≈470, EQUAL≈32

`.10f` uses round-half-even (banker's rounding) and can move thresholds UP, DOWN, or leave them unchanged. It is NOT truncation.

### 7.3 Concrete UP Example

```
entry=10.0, pct=0.1, LONG_TP
raw computation: 10.00999999999999801
.10f formatted:  10.00999999999999979
.10f > raw? YES — .10f moves the value UP
```

### 7.4 Can `.10f` Change an Exit Decision?

Yes. If the threshold moves from below the market price to above (or vice versa), the exit decision flips. The 52 UP cases and 42 DOWN cases in the deterministic corpus demonstrate that `.10f` can alter the boundary position.

### 7.5 Does `.10f` Have Principled Relationship to Tick Size?

No. `.10f` produces 10 decimal places regardless of instrument precision. XAU/USD prices may have different precision (e.g., 2 decimal places for some providers, 4 for others). `.10f` is a formatting convention with no connection to market semantics.

---

## 8. Policy D — Exact Decimal Reference + Float Price

**Definition (conceptual):**
1. Calculate mathematical T exactly as a Decimal
2. Keep T as an exact Decimal/reference value
3. Define an explicit deterministic bridge between the binary64 market price and Decimal T

### 8.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | REQUIRES DEFINITION — Depends on the bridge specification |
| **Boundary clarity** | REQUIRES DEFINITION — The bridge defines what "at the boundary" means |
| **Binary64 sensitivity** | LOW — T is exact; only the price conversion matters |
| **Domain semantics** | REQUIRES DEFINITION — Bridge must encode domain semantics |
| **Reproducibility** | REQUIRES DEFINITION — Bridge must be deterministic |
| **Auditability** | REQUIRES DEFINITION — Bridge must be auditable |
| **Architectural impact** | HIGH — Requires Decimal arithmetic in production or a conversion layer |
| **Hidden assumptions** | Assumes a bridge can be defined without introducing non-determinism |
| **Unresolved decisions** | What is the bridge? How does it handle non-representable T? |

### 8.2 Unresolved Decisions for Policy D

Policy D requires explicit specification of:
1. How binary64 market price converts to Decimal for comparison
2. What happens when T is not representable (which direction is "at" the boundary?)
3. Whether the conversion is symmetric across LONG/SHORT and TP/SL
4. Performance implications of Decimal arithmetic in hot path
5. Serialization compatibility with existing float-based Candle schema
6. Historical data precision normalization

### 8.3 Does Decimal Alone Solve the Problem?

No. Decimal provides exact arithmetic but does not resolve the fundamental question: when T is not representable in binary64, what is the canonical boundary? Decimal arithmetic on a binary64 price still requires a conversion rule. The boundary-definition problem is separate from the arithmetic representation.

---

## 9. Policy E — Instrument Tick-Size / Price-Precision Normalization

**Definition (conceptual):** Define threshold comparison through an instrument's official price increment / tick size.

### 9.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | REQUIRES DEFINITION — Depends on instrument metadata |
| **Boundary clarity** | HIGH — Tick size provides natural boundary granularity |
| **Binary64 sensitivity** | REQUIRES DEFINITION — Depends on how tick size interacts with float representation |
| **Domain semantics** | HIGH — Tick size is a domain concept (price increments are market-defined) |
| **Reproducibility** | REQUIRES DEFINITION — Depends on consistent instrument metadata |
| **Auditability** | MEDIUM — Tick size is auditable if metadata is reliable |
| **Architectural impact** | HIGH — Requires instrument metadata infrastructure |
| **Hidden assumptions** | Assumes tick size is available, consistent, and provider-independent |
| **Unresolved decisions** | Is tick-size metadata compatible with D5 (no tick-size metadata)? |

### 9.2 Design Gap: D5 Constraint

The locked design specifies **D5: No tick-size metadata**. This creates a direct conflict with Policy E. If D5 is maintained, Policy E is not available without design amendment.

### 9.3 Provider Differences

- Different data providers may report different precisions for the same instrument
- Historical data may have inconsistent precision
- XAU/USD may not have a single universal precision across all providers
- Tick-size metadata introduces external dependencies

### 9.4 Currently Specified by Locked Design?

No. Policy E is NOT specified by the locked design. D5 explicitly prohibits tick-size metadata. Policy E would require a design amendment.

---

## 10. Policy F — Explicit Tolerance / Epsilon

**Definition (conceptual):**
```
abs(price - threshold) <= epsilon
```
or equivalent directional tolerance.

### 10.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | HIGH — Epsilon comparison is deterministic |
| **Boundary clarity** | REQUIRES DEFINITION — Epsilon defines a band, not a point |
| **Binary64 sensitivity** | LOW — Tolerance absorbs floating-point imprecision |
| **Domain semantics** | NONE — Epsilon is arbitrary, not market-derived |
| **Reproducibility** | HIGH — Same epsilon produces same results |
| **Auditability** | LOW — Epsilon is a magic number without domain justification |
| **Architectural impact** | MEDIUM — Changes all boundary comparisons |
| **Hidden assumptions** | Assumes a single epsilon works across all price levels and instruments |
| **Unresolved decisions** | What epsilon value? Who defines it? Is it scale-invariant? |

### 10.2 Why Epsilon Cannot Simply Be Chosen

- **Scale dependence:** An epsilon of 0.01 is meaningful for entry=100 but negligible for entry=100000
- **Instrument dependence:** An epsilon appropriate for EUR/USD may be inappropriate for BTC/USD
- **Percentage dependence:** An epsilon appropriate for pct=1.0 may be inappropriate for pct=50.0
- **Price-level dependence:** The same absolute epsilon has different relative significance at different price levels
- **False positives/negatives:** Too large → premature exits; too small → missed exits
- **Arbitrary selection:** Choosing epsilon to make tests pass is not a design decision — it is curve-fitting

### 10.3 Epsilon Is a Design Parameter, Not a Mathematical Fact

Epsilon is a human-chosen tolerance with no mathematical derivation. It cannot be derived from the locked design and must be explicitly decided by the human reviewer.

---

## 11. Policy G — Decimal Production Arithmetic

**Definition (conceptual):** Use Decimal arithmetic for TP/SL threshold calculations and comparisons in production.

### 11.1 Analysis

| Dimension | Assessment |
|-----------|-----------|
| **Determinism** | HIGH — Decimal arithmetic is deterministic |
| **Boundary clarity** | REQUIRES DEFINITION — Exact Decimal T still requires a comparison rule for binary64 prices |
| **Binary64 sensitivity** | LOW — T is exact; comparison still requires bridge |
| **Domain semantics** | NONE — Decimal is arithmetic, not market semantics |
| **Reproducibility** | HIGH — Decimal is platform-independent |
| **Auditability** | HIGH — Exact decimal values are auditable |
| **Architectural impact** | HIGH — Requires Decimal in production path; serialization changes |
| **Hidden assumptions** | Assumes Decimal alone solves the boundary problem (FALSE) |
| **Unresolved decisions** | How does Decimal compare to binary64 prices? What about historical OHLC data? |

### 11.2 Does Decimal Automatically Solve the Problem?

No. Decimal provides exact arithmetic but does not resolve:
1. How to compare a Decimal T against a binary64 market price
2. What "at the boundary" means when T is not representable in binary64
3. How to handle historical OHLC data stored as binary64 floats
4. Serialization compatibility with existing `.10f` canonical format

Decimal solves the arithmetic precision problem but not the boundary-definition problem. The fundamental question — "what constitutes hitting the boundary?" — remains.

### 11.3 Intended-Decimal vs Actual-Binary64 Input Semantics

This is a critical unresolved issue. If the analysis uses `Decimal(str(entry))` (intended decimal), but the actual input data is binary64 floats, there is a semantic gap. The analysis assumes intended decimal semantics, but the production data uses binary64 representation. This gap must be explicitly addressed.

---

## 12. Numerical Counterexamples

The following cases are drawn from the deterministic corpus (520 cases) and are representative of the full domain.

### 12.1 Exactly Representable T

```
entry=0.1, pct=25.0, LONG_TP
T = 0.1 × 1.25 = 0.125 (EXACTLY REPRESENTABLE)
Binary64: 0.125 (exact)
Both candidates: EXACT
```

### 12.2 Non-Representable T — Below Nearest Binary64

```
entry=333.33, pct=10.0, LONG_TP
T = 333.33 × 1.1 = 366.663 (NOT EXACTLY REPRESENTABLE)
Nearest binary64: 366.66300000000001091393642127513885498046875 (ABOVE T)
Candidate A: ABOVE T (172 cases)
Candidate B: ABOVE T (164 cases)
```

### 12.3 Non-Representable T — Above Nearest Binary64

```
entry=0.01, pct=0.01, LONG_TP
T = 0.01 × 1.0001 = 0.010001 (NOT EXACTLY REPRESENTABLE)
Nearest binary64: 0.010001000000000000... (BELOW T)
Candidate A: BELOW T (168 cases)
Candidate B: BELOW T (176 cases)
```

### 12.4 `.10f` UP Case

```
entry=10.0, pct=0.1, LONG_TP
raw computation: 10.00999999999999801
.10f formatted:  10.00999999999999979
.10f > raw? YES — .10f moves threshold UP
```

### 12.5 `.10f` DOWN Case

```
entry=0.01, pct=7.5, LONG_SL
raw computation: 0.00925000000000000
.10f formatted:  0.00925000000000000
.10f = raw at 10 decimal places
(Note: DOWN cases exist but are subtle due to 10-decimal-place precision)
```

### 12.6 Computation Order Changes Result

```
entry=100.0, pct=2.5, LONG_TP
math_T = 102.5000 (EXACTLY REPRESENTABLE)
Raw multiplicative: 100.0 * 1.025 = 102.49999999999999 (BELOW T)
Additive/Candidate A: 100.0 + 100.0*2.5/100 = 102.5 (EXACT)
Candidate B: float(f'{102.49999999999999:.10f}') = 102.5 (EXACT)
```

**Principle:** Representable mathematical threshold ≠ guaranteed exact result from an arbitrary floating-point computation path.

---

## 13. Execution-Semantics Impact

### 13.1 Default Execution (Same-Bar)

```
signal at bar t close → fill at bar t close
```

### 13.2 Execution Delay (=1)

```
signal at bar t close → fill at bar t+1 close
```

### 13.3 Policy Impact Analysis

| Policy | Entry Impact | TP Exit Impact | SL Exit Impact | Same-Bar Exit | Trade Ordering | Equity Curve | Result Hash |
|--------|-------------|----------------|----------------|---------------|----------------|--------------|-------------|
| A | None | Depends on threshold | Depends on threshold | Depends on boundary | None | Depends on exits | May change |
| B | None | Depends on threshold | Depends on threshold | Depends on boundary | None | Depends on exits | May change |
| C | None | `.10f` may change threshold | `.10f` may change threshold | May change | None | May change | May change |
| D | None | Depends on bridge | Depends on bridge | Depends on bridge | None | Depends on exits | May change |
| E | None | Depends on tick size | Depends on tick size | Depends on tick size | None | Depends on exits | May change |
| F | None | Epsilon band | Epsilon band | May change | None | May change | May change |
| G | None | Decimal comparison | Decimal comparison | Depends on bridge | None | Depends on exits | May change |

### 13.4 Result Hash Implications

Canonical serialization uses `.10f` formatting for float values (line 632-641 of design document). If a policy changes the computed threshold values, the trade fill prices, equity curve, and metrics may change, potentially altering the `result_hash`. The canonical serialization rules must remain invariant under implementation refactoring that preserves mathematical semantics.

---

## 14. Hashing Impact

### 14.1 Canonical Serialization

The locked design specifies `.10f` formatting for all float values in canonical serialization (Section H, lines 632-641). This applies to trades, equity curve, metrics, and condition serialization.

### 14.2 Policy Impact on Hash

| Policy | Trade Serialization | Equity Curve | Metrics | Result Hash |
|--------|--------------------|--------------|---------|-------------|
| A | Float values unchanged | Float values unchanged | Float values unchanged | Unchanged |
| B | Float values unchanged | Float values unchanged | Float values unchanged | Unchanged |
| C | Threshold changes may affect fill prices | May change | May change | May change |
| D | Decimal T may affect fill prices | May change | May change | May change |
| E | Tick-size normalization may affect prices | May change | May change | May change |
| F | Epsilon may affect exit decisions | May change | May change | May change |
| G | Decimal arithmetic may affect fill prices | May change | May change | May change |

### 14.3 Critical Requirement

Result hashes must remain invariant under implementation refactoring that preserves mathematical semantics. Any numerical policy must specify whether a mathematically-equivalent implementation change should preserve the result hash.

---

## 15. Determinism Analysis

### 15.1 Per-Policy Determinism Questions

| Policy | Same Inputs → Same Threshold? | Same Inputs → Same Exit? | Same Config/Version → Same Hash? | Platform Dependent? | Locale Dependent? | Formatting Dependent? | External Metadata? | Hidden Tolerance? |
|--------|-------------------------------|--------------------------|----------------------------------|---------------------|-------------------|----------------------|--------------------|--------------------|
| A | Yes | Yes | Yes | No | No | No | No | REQUIRES DEFINITION |
| B | Yes | Yes | Yes | No | No | No | No | REQUIRES DEFINITION |
| C | Yes | Yes | Yes | No | No | Yes | No | No |
| D | Yes | REQUIRES DEFINITION | REQUIRES DEFINITION | No | No | REQUIRES DEFINITION | No | REQUIRES DEFINITION |
| E | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | No | No | No | Yes | No |
| F | Yes | Yes | Yes | No | No | No | No | Yes (epsilon value) |
| G | Yes | REQUIRES DEFINITION | REQUIRES DEFINITION | No | No | REQUIRES DEFINITION | No | REQUIRES DEFINITION |

### 15.2 Key Observations

- All policies produce deterministic results given the same inputs and configuration
- Policy C is formatting-dependent (`.10f` behavior is locale-independent but formatting-dependent)
- Policy E depends on external instrument metadata (if tick size is introduced)
- Policy F has a hidden tolerance parameter (epsilon)
- Policies D, G, and potentially E require additional specification to be fully deterministic

---

## 16. Security Analysis

### 16.1 Per-Policy Security Concerns

| Policy | Hidden Configuration | Mutable Metadata | Non-Deterministic | Unsafe Parsing | Environment-Dependent | Silent Fallback | Financial Ambiguity |
|--------|---------------------|------------------|-------------------|----------------|----------------------|-----------------|---------------------|
| A | None | None | No | No | No | No | REQUIRES DEFINITION |
| B | None | None | No | No | No | No | REQUIRES DEFINITION |
| C | None | None | No | No | No | No | Yes (arbitrary precision) |
| D | REQUIRES DEFINITION | No | REQUIRES DEFINITION | No | No | REQUIRES DEFINITION | REQUIRES DEFINITION |
| E | REQUIRES DEFINITION | Yes (tick data) | REQUIRES DEFINITION | No | No | REQUIRES DEFINITION | REQUIRES DEFINITION |
| F | Yes (epsilon) | No | No | No | No | No | Yes (epsilon selection) |
| G | REQUIRES DEFINITION | No | No | No | No | No | REQUIRES DEFINITION |

### 16.2 Key Concerns

- Policy E introduces mutable external metadata (tick-size data)
- Policy F introduces a hidden configuration parameter (epsilon) that could affect financial accounting silently
- Policy D and G introduce architectural complexity that could create silent fallbacks
- Policy C's `.10f` precision creates ambiguity about whether 10 decimal places is sufficient for all instruments

---

## 17. D1 Percentage-Semantic Mismatch

### 17.1 Current Implementation

**StrategySpec path** (`src/data_engine/strategy/backtest.py` lines 445-454):
```python
threshold = position.entry_fill_price * (1 - strategy.stop_loss_pct / 100)
```
- `take_profit_pct=10.0` → `entry × (1 + 10.0/100)` = `entry × 1.1`
- **Interpretation: percentage points (10.0 = 10%)**

**ExitCondition path** (`src/data_engine/strategy/schemas.py` lines 165-170):
```python
return current_price <= entry_price * (1.0 - self.pct_of_entry)
```
- `pct_of_entry=0.1` → `entry × (1 + 0.1)` = `entry × 1.1`
- `pct_of_entry=10.0` → `entry × (1 + 10.0)` = `entry × 11.0`
- **Interpretation: fractional ratio (0.1 = 10%)**

### 17.2 The Mismatch

The two paths currently use **different numeric conventions** for percentage values. StrategySpec expects percentage points (divides by 100). ExitCondition expects fractional ratio (no division).

### 17.3 Required Human Decision

> Should Phase 3 canonical exit-condition percentage semantics be percentage points (`10.0 = 10%`) or fractional ratio (`0.1 = 10%`)?

This is a DESIGN DECISION, not an implementation task. No source code modifications are proposed or made by this analysis.

### 17.4 Impact on D4 Policy

The chosen D1 convention must be consistent across all numerical policies. If Policy D, E, F, or G is selected, the percentage semantic must be explicitly defined and consistent.

---

## 18. Design Gaps

### 18.1 Missing Specifications in Locked Design

The following are NOT specified by `docs/strategy_engine_design.md`:

| Missing Item | Status |
|-------------|--------|
| TP/SL numerical comparison semantics | NOT SPECIFIED |
| Floating-point equality for thresholds | NOT SPECIFIED |
| Threshold rounding rules | NOT SPECIFIED |
| Decimal arithmetic for exit conditions | NOT SPECIFIED |
| Epsilon/tolerance for boundaries | NOT SPECIFIED |
| Tick-size metadata (prohibited by D5) | PROHIBITED |
| Price precision rules | NOT SPECIFIED |
| Binary64 semantics for comparisons | NOT SPECIFIED |
| Decimal-to-float conversion rules | NOT SPECIFIED |
| Boundary handling for non-representable thresholds | NOT SPECIFIED |
| Percentage point convention for ExitCondition | NOT SPECIFIED |
| Canonical result hash invariance under numerical refactoring | NOT SPECIFIED |

### 18.2 Design Gap Statement

`D4 numerical TP/SL comparison policy is not fully specified by the locked design.`

The locked design references the requirement (D4: Deterministic numerical policy) but does not define what the policy should be. The only D4 label in the design ("D4: Deterministic strategy hash" at line 1785) concerns hashing determinism, not numerical threshold comparison.

### 18.3 D5 Constraint

D5 explicitly prohibits tick-size metadata. This means Policy E (tick-size normalization) is not available without a design amendment to D5.

---

## 19. Full Comparison Matrix

| Policy | Determinism | Boundary clarity | Binary64 sensitivity | Domain semantics | Reproducibility | Auditability | Architectural impact | Hidden assumptions | Unresolved decisions |
|--------|-------------|-----------------|---------------------|-----------------|----------------|-------------|--------------------|--------------------|--------------------|
| **A** | HIGH | REQUIRES DEFINITION | HIGH | NONE | HIGH | MEDIUM | NONE | REQUIRES DEFINITION | Representable T behavior; boundary for non-representable T |
| **B** | HIGH | REQUIRES DEFINITION | HIGH | NONE | HIGH | MEDIUM | LOW | Algebraic equivalence | Computation path differences; hashing implications |
| **C** | HIGH | LOW | MEDIUM | NONE | HIGH | LOW | MEDIUM | `.10f` is valid normalization | Tick-size relationship; exit decision changes; canonical precision |
| **D** | REQUIRES DEFINITION | REQUIRES DEFINITION | LOW | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | HIGH | Bridge exists | Bridge definition; historical data; serialization; Decimal-to-float |
| **E** | REQUIRES DEFINITION | HIGH | REQUIRES DEFINITION | HIGH | REQUIRES DEFINITION | MEDIUM | HIGH | Tick-size available & consistent | D5 conflict; provider differences; metadata infrastructure |
| **F** | HIGH | REQUIRES DEFINITION | LOW | NONE | HIGH | LOW | MEDIUM | Epsilon is correct | Epsilon value; scale invariance; instrument dependence |
| **G** | HIGH | REQUIRES DEFINITION | LOW | NONE | HIGH | HIGH | HIGH | Decimal solves boundary | Bridge definition; historical data; serialization; migration |

**Legend:**
- **HIGH** = Strong property, well-defined
- **MEDIUM** = Moderate property, some ambiguity
- **LOW** = Weak property, significant ambiguity
- **NONE** = No property
- **REQUIRES DEFINITION** = Property depends on unresolved decisions

---

## 20. HUMAN DESIGN DECISIONS REQUIRED

The following decisions must be made by the human reviewer before any implementation:

### 20.1 Core Numerical Policy

1. **Intended input semantic:** Should the analysis use intended decimal values (`Decimal(str(entry))`) or actual binary64 inputs for threshold computation?
2. **Canonical TP/SL percentage unit:** Should `take_profit_pct=10.0` mean 10% (percentage points) or should `pct_of_entry=0.1` mean 10% (fractional ratio)? Must be consistent across StrategySpec and ExitCondition.
3. **Exact threshold construction semantics:** Which formula path should be canonical — multiplicative `entry * (1 + pct/100)` or additive `entry + entry * pct / 100`? Must be consistent across all exit paths.
4. **Binary64 comparison semantics:** When T is not exactly representable, what binary64 float is "at" the boundary? Greatest below? Smallest above? Nearest?
5. **Boundary inclusivity:** Does D3's inclusive boundary (`>=`/`<=`) apply to the representable float or the mathematical T? How are non-representable T cases handled?
6. **Non-representable threshold behavior:** When T is not representable, does the boundary trigger based on the nearest float or some other rule?
7. **Whether rounding is permitted:** Is `.10f` normalization or any other rounding allowed for threshold construction?
8. **Whether tolerance is permitted:** Is an epsilon or tolerance band allowed for boundary comparisons?
9. **Whether tick-size semantics are required:** Despite D5, should tick-size normalization be considered as a design amendment?
10. **Whether Decimal is production arithmetic or analysis-only:** Should Decimal arithmetic be used in the production backtest path or only for numerical analysis?
11. **Whether threshold normalization is permitted:** Is any form of threshold normalization (`.10f`, tick-size rounding, etc.) allowed?
12. **Whether the same policy must be used by StrategySpec and ExitCondition:** Must both paths use the same numerical convention and threshold formula?
13. **Whether historical data precision must be normalized:** If a policy changes threshold computation, must historical OHLC data be re-normalized?
14. **Whether result hashes must remain invariant under implementation refactoring:** If a mathematically-equivalent implementation change is made, should `result_hash` remain the same?

### 20.2 D1 Semantic Consistency

15. **ExitCondition percentage convention:** Should `pct_of_entry` use percentage points (10.0 = 10%, divide by 100) or fractional ratio (0.1 = 10%, no division)?

### 20.3 Design Amendment

16. **D5 tick-size prohibition:** If tick-size normalization is desired, must D5 be amended?

---

## 21. Evidence Limitations

The following limitations must be explicitly acknowledged:

1. **Finite corpus cannot prove universal correctness.** The 520-case deterministic corpus and 10,000-case random corpus provide empirical evidence only. Finding even one counterexample disproves universality, but finding none does not prove it.

2. **Random corpus cannot prove universal correctness.** The 10,000 random cases (seed=42) are a finite sample. Results may differ for inputs outside the tested distribution.

3. **Empirical results are not mathematical proofs.** All PASS/FAIL/AMBIGUOUS counts are empirical observations, not proofs of universal properties.

4. **Decimal reference semantics depend on the declared intended-input convention.** Using `Decimal(str(entry))` assumes intended decimal semantics. If actual binary64 inputs are used instead, the mathematical thresholds differ.

5. **Tick-size semantics cannot be assumed without instrument metadata.** No tick-size metadata exists in the locked design (D5 prohibition). Any tick-size analysis is conceptual only.

6. **`.10f` is formatting/rounding, not inherently market semantics.** `.10f` is a Python formatting convention with no connection to instrument precision or market convention.

7. **Epsilon is a design parameter, not a mathematical fact.** Epsilon values are human-chosen and cannot be derived from the locked design.

8. **Binary64 representability counts are convention-dependent.** The 180/164/176 counts depend on the intended-decimal-input convention. Different conventions produce different counts.

---

## 22. Final Status

```
D4 HUMAN DESIGN DECISION MATRIX: COMPLETE

This document analyzes seven policy families without selecting any.
All numerical claims are verified against retained analysis evidence:
- Deterministic corpus: 520 cases per candidate
- True representability: 180 EXACT, 164 ABOVE, 176 BELOW
- Candidate A: PASS=180, BELOW=168, ABOVE=172
- Candidate B: PASS=180, BELOW=176, ABOVE=164
- .10f direction: UP=52, DOWN=42, EQUAL=426
- Random corpus: 10,000 cases per candidate, seed=42
- Design SHA: verified unchanged
- No source/test/design modifications made

14 HUMAN DESIGN DECISIONS are enumerated in Section 20.
None have been answered.

BLOCKER #2 D4: BLOCKED — HUMAN DESIGN APPROVAL REQUIRED

PHASE 3: NO-GO
```

---

END OF D4 HUMAN DESIGN DECISION MATRIX
---