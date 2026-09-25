# PHASE 3 — BLOCKER #2
# D4 HUMAN APPROVAL RECORD

## Scope

This document formalizes the **HUMAN DESIGN APPROVAL** for D4 (Deterministic Numerical Policy for TP/SL Threshold Comparisons) in the AI Trading Lab Data Engine project.

**Project:** AI Trading Lab — Data Engine  
**Phase:** Phase 3 — Strategy & Backtest Engine  
**Blocker:** Blocker #2 — D4 Numerical Policy  
**Task Type:** Governance and Design-Approval  
**Implementation Status:** NOT AUTHORIZED

This task is **analysis and approval-governance only**. No source code, tests, schemas, design documents, or configuration files have been modified by this task.

---

## 1. Locked-Design SHA Verification

### 1.1 Expected SHA-256

```text
88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
```

### 1.2 Actual SHA-256

```text
bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166
```

### 1.3 Verification Result

```text
D4 HUMAN APPROVAL: BLOCKED — LOCKED DESIGN SHA MISMATCH
```

**Expected:** `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`  
**Computed:** `bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166`  
**Match:** FALSE

### 1.4 Design File Status

| Attribute | Expected | Actual |
|-----------|----------|--------|
| Lines | 2,044 | 2,238 |
| Bytes | 89,231 | 95,358 |
| SHA-256 | `88198b17...` | `bd1c606c...` |
| Match | — | **MISMATCH** |

### 1.5 Source Integrity Findings

- `src/data_engine/strategy/backtest.py`: **MODIFIED** — now uses Decimal arithmetic for threshold computation (Phase 1 fix: D4.1/D4.2/D4.4 comments present; `Decimal(str(...))` used for threshold construction)
- `src/data_engine/strategy/schemas.py`: **MODIFIED** — `ExitCondition` now uses `Decimal(str(self.pct_of_entry))` for threshold computation
- `docs/strategy_engine_design.md`: **MODIFIED** — SHA mismatch confirmed; file size and line count differ from expected locked design
- Test files: Not inspected for modification status in this task
- No existing D4 artifacts were overwritten

### 1.6 SHA Mismatch Impact

Per the task rules, a SHA mismatch is a hard STOP condition. The locked design document no longer matches the SHA that all previous analysis artifacts reference. This means:

1. The design document may have been amended between previous analysis sessions and the current task
2. All analysis artifacts referencing SHA `88198b17...` may be based on a different version of the design than what currently exists on disk
3. The approval record must reflect this discrepancy
4. No implementation may proceed until the design SHA is reconciled and re-verified

---

## 2. Source Integrity Assessment

### 2.1 Current Implementation State

The current implementation (as verified during this task) shows that **Phase 1 fixes have been applied**:

**`src/data_engine/strategy/backtest.py`** (lines 440-476):
- Uses `Decimal(str(position.entry_fill_price))` for entry price
- Uses `Decimal(str(strategy.stop_loss_pct))` and `Decimal(str(strategy.take_profit_pct))` for percentages
- Computes threshold as `entry_decimal * (Decimal('1') ± pct_decimal / Decimal('100'))`
- Converts close price via `Decimal.from_float(close_price)`
- Uses inclusive boundary comparisons via `Decimal` comparison operators

**`src/data_engine/strategy/schemas.py`** (lines 165-170):
- `ExitCondition.evaluate()` uses `Decimal(str(self.pct_of_entry))` for percentage conversion
- Threshold computation uses Decimal arithmetic

These modifications were applied as Phase 1 work and are NOT part of this task's scope. However, they represent a substantive departure from the original implementation described in the locked design artifacts, which used raw float arithmetic throughout.

### 2.2 Implications for D4 Approval

The Phase 1 Decimal arithmetic changes in `backtest.py` and `schemas.py` effectively implement a **Policy G (Decimal Production Arithmetic)** approach for threshold computation. However:

1. The comparison is still performed via `Decimal.from_float(close_price)` against a Decimal threshold, which introduces a conversion bridge that is itself a design decision
2. The boundary semantics (inclusive `<=` and `>=`) are preserved
3. The percentage conversion (`pct / 100`) is applied consistently in both paths
4. However, the D1 semantic consistency question (whether `pct_of_entry` should use percentage points or fractional ratio) may have been addressed by these changes

**Important:** These source modifications were NOT made by this task. They represent prior work that must be reconciled with the locked design SHA.

---

## 3. Current D4 State

### 3.1 D4 Requirement

D4 requires a **deterministic numerical policy** for TP/SL threshold comparisons. The locked design references this requirement but does not specify the policy.

### 3.2 Verified D1–D7 Status

| Requirement | Status | Notes |
|-------------|--------|-------|
| **D1** — Percentage points | PARTIALLY ADDRESSED | Phase 1 Decimal changes apply `/100` conversion consistently, but D1 convention (percentage points vs fractional ratio) may still need explicit human decision |
| **D2** — Threshold formula | PARTIALLY ADDRESSED | Decimal arithmetic used in backtest.py; formula matches `entry × (1 ± pct/100)` |
| **D3** — Boundary inclusivity | ADDRESSED | Inclusive comparisons (`>=`/`<=`) used in Decimal arithmetic |
| **D4** — Numerical policy | **BLOCKED** | SHA mismatch prevents definitive verification of design intent |
| **D5** — No tick-size metadata | MAINTAINED | No tick-size metadata in current code |
| **D6** — Cross-path consistency | PARTIALLY ADDRESSED | Both paths now use Decimal with `/100` conversion |
| **D7** — Determinism | ADDRESSED | Decimal arithmetic is deterministic |

### 3.3 D4 Gap Analysis

The D4 numerical policy gap exists in the design document. While Phase 1 source modifications have applied Decimal arithmetic to the implementation, the **locked design document** does not explicitly specify this as the normative policy. The approval process must decide whether:

1. The Phase 1 Decimal changes constitute the D4 policy implementation (requiring design amendment to formalize)
2. A different numerical policy is needed (requiring explicit human selection)
3. The design must be reconciled with the current source state

---

## 4. Verified Numerical Evidence

All numerical evidence is drawn from the retained analysis artifacts and verified against the current implementation.

### 4.1 Mathematical Threshold

For intended decimal inputs:
```
LONG TP:   T = entry × (1 + pct/100)
LONG SL:   T = entry × (1 - pct/100)
SHORT TP:  T = entry × (1 - pct/100)
SHORT SL:  T = entry × (1 + pct/100)
```

Computed using `Decimal(str(entry)) × (1 ± Decimal(str(pct))/100)`.

### 4.2 Mathematical-Threshold Binary64 Representability

| Classification | Count | Percentage |
|----------------|-------|------------|
| **EXACTLY REPRESENTABLE** | 180 | 34.6% |
| **BINARY64 ABOVE T** | 164 | 31.5% |
| **BINARY64 BELOW T** | 176 | 33.8% |
| **Total** | **520** | **100%** |

Test: `float(T)` → `Decimal.from_float(float(T))` == T

### 4.3 Candidate-Computation Results

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **PASS** (exact) | 180 | 180 |
| **BELOW T** | 168 | 176 |
| **ABOVE T** | 172 | 164 |
| **Total** | 520 | 520 |

### 4.4 `.10f` Direction (Deterministic Corpus)

| Direction | Count |
|-----------|-------|
| **UP** | 52 |
| **DOWN** | 42 |
| **EQUAL** | 426 |

### 4.5 Random Corpus (Seed=42)

| Metric | Candidate A | Candidate B |
|--------|-------------|-------------|
| **PASS** | 0 | 0 |
| **FAIL** (below T) | 5,065 | 4,951 |
| **AMBIGUOUS** (above T) | 4,935 | 5,049 |
| **Total** | 10,000 | 10,000 |

### 4.6 Finite Evidence vs. Universal Proof

The deterministic and random corpora demonstrate observed behavior. They do NOT constitute universal mathematical proofs. No policy claims universal correctness.

---

## 5. D1 Semantic Mismatch

### 5.1 Original Mismatch

The original implementation had a D1 semantic inconsistency:

- **StrategySpec path**: `strategy.take_profit_pct / 100` → percentage points (10.0 = 10%)
- **ExitCondition path**: `entry_price * (1.0 ± self.pct_of_entry)` → fractional ratio (0.1 = 10%)

### 5.2 Current State

Phase 1 source modifications have applied `Decimal(str(...))` with `/100` conversion to both paths. However, the D1 semantic question remains whether the canonical unit is percentage points (`10.0 = 10%`) or fractional ratio (`0.1 = 10%`). This is a **design decision**, not an implementation task.

### 5.3 Required Human Decision

> Should Phase 3 canonical exit-condition percentage semantics be percentage points (`10.0 = 10%`) or fractional ratio (`0.1 = 10%`)?

This decision must be explicitly made by the human before implementation proceeds.

---

## 6. Policy-Family Definitions

The following policy families must be preserved exactly as analyzed. The human must select one, or define a new one.

### A — Direct Binary64 Comparison

Use the computed binary64 threshold directly. Comparisons use raw `>=`/`<=` on float values. Boundary behavior follows IEEE-754 representation exactly. No changes to current behavior.

**Assumptions:** `>=` on floats captures intended boundary semantics.  
**Consequences:** Non-representable T produces ambiguous boundary behavior.

### B — Additive Threshold Construction

Construct the threshold using additive arithmetic rather than the multiplicative expression.

```
LONG TP:   threshold = entry + entry * pct / 100
LONG SL:   threshold = entry - entry * pct / 100
SHORT TP:  threshold = entry - entry * pct / 100
SHORT SL:  threshold = entry + entry * pct / 100
```

**Assumptions:** Algebraic equivalence implies numerical equivalence (FALSE in float arithmetic, though observable differences are limited).  
**Consequences:** Different computation path from multiplicative; may avoid specific rounding artifacts.

### C — `.10f` Normalization

Normalize the calculated threshold using the documented `.10f` serialization/rounding mechanism.

```
threshold_normalized = float(f"{threshold:.10f}")
```

**Assumptions:** `.10f` is a valid threshold normalization.  
**Consequences:** `.10f` can move thresholds UP (52 cases), DOWN (42 cases), or leave unchanged (426 cases) in the deterministic corpus. Not universally downward-truncating.

### D — Exact Decimal Threshold + Float Price

Calculate the mathematical threshold in exact decimal arithmetic while comparing against a binary64 market price.

**Assumptions:** A deterministic bridge between Decimal T and binary64 price can be defined.  
**Consequences:** Requires Decimal-to-float conversion rules; architectural impact HIGH.

### E — Tick-Size / Price-Precision Normalization

Normalize prices/thresholds according to an explicitly defined market precision or tick size.

**Assumptions:** Tick-size metadata is available and consistent.  
**Consequences:** CONFLICTS with D5 (no tick-size metadata). Requires design amendment to D5.

### F — Explicit Tolerance / Epsilon

Define a deterministic comparison tolerance around the mathematical threshold.

**Assumptions:** A single epsilon value works across all price levels and instruments.  
**Consequences:** Epsilon is a design parameter, not a mathematical fact. Scale-dependent, instrument-dependent, percentage-dependent.

### G — Decimal Production Arithmetic

Use Decimal arithmetic for production threshold construction/comparison.

**Assumptions:** Decimal arithmetic alone resolves the boundary problem.  
**Consequences:** Decimal solves arithmetic precision but not the boundary-definition problem when T is non-representable. HIGH architectural impact.

---

## 7. Policy Specification Requirements

For each candidate policy, the following template must be satisfied before implementation:

| Field | Required Definition |
|-------|---------------------|
| Input representation | Exact |
| Percentage unit | Exact |
| Threshold mathematical formula | Exact |
| Computation representation | Exact |
| Comparison representation | Exact |
| Equality rule | Exact |
| Rounding | Exact |
| Tolerance | Exact or NONE |
| Tick size | Exact or NONE |
| Decimal arithmetic | Exact or NONE |
| Missing/invalid values | Exact |
| LONG behavior | Exact |
| SHORT behavior | Exact |
| Determinism | Exact |
| Cross-platform behavior | Exact |
| Serialization/hash behavior | Exact |
| Historical-data behavior | Exact |

This is a requirements template, not a recommendation.

---

## 8. Human-Only Decision Boundary

The following MUST NOT be done by this agent:

- Select policy A, B, C, D, E, F, G, or any hybrid
- Recommend, rank, or prefer any policy
- Claim any policy is "best," "optimal," "superior," or "recommended"
- Silently resolve an unresolved D4 decision
- Interpret Hermes analysis, numerical evidence, or previous conclusions as human approval
- Treat an existing draft amendment as human approval

The following are documented for human review only:
- What each policy means
- What assumptions it requires
- What architectural consequences it creates
- What numerical behavior the existing evidence demonstrates
- What unresolved questions remain

**The actual design choice belongs to the human.**

---

## 9. Human D4 Approval Record

## HUMAN D4 APPROVAL RECORD

Approval Status: **PENDING HUMAN APPROVAL**

Selected Policy Family: **PENDING HUMAN INPUT**

Selected Numerical Rule: **PENDING HUMAN INPUT**

Percentage Unit: **PENDING HUMAN INPUT**

Threshold Formula: **PENDING HUMAN INPUT**

Boundary Inclusivity: **PENDING HUMAN INPUT**

Binary64 Handling: **PENDING HUMAN INPUT**

Non-Representable Threshold Handling: **PENDING HUMAN INPUT**

Rounding Rule: **PENDING HUMAN INPUT**

Tolerance Rule: **PENDING HUMAN INPUT**

Tick-Size Rule: **PENDING HUMAN INPUT**

Decimal Arithmetic Rule: **PENDING HUMAN INPUT**

Canonical Semantic Representation: **PENDING HUMAN INPUT**

StrategySpec / ExitCondition Consistency Rule: **PENDING HUMAN INPUT**

Historical Data Compatibility Rule: **PENDING HUMAN INPUT**

Hashing / Serialization Impact: **PENDING HUMAN INPUT**

Determinism Requirement: **PENDING HUMAN INPUT**

Human Approver: **PENDING HUMAN INPUT**

Approval Date: **PENDING HUMAN INPUT**

Approval Notes: **PENDING HUMAN INPUT**

---

## 10. Unresolved Human Decisions

The following decisions must be made by the human reviewer:

### 10.1 Core Numerical Policy

1. **Policy family selection:** Which policy family (A–G) or new mechanism becomes the normative D4 rule?
2. **Exact numerical semantics:** What is the complete mathematical and computational specification of the selected policy?
3. **Percentage unit:** Should `take_profit_pct=10.0` mean 10% (percentage points) or should `pct_of_entry=0.1` mean 10% (fractional ratio)?
4. **Threshold formula:** Which formula path is canonical — multiplicative `entry * (1 + pct/100)` or additive `entry + entry * pct / 100`?
5. **Binary64 comparison semantics:** When T is not exactly representable, what binary64 float is "at" the boundary?
6. **Boundary inclusivity:** Does D3's inclusive boundary apply to the representable float or the mathematical T? How are non-representable T cases handled?
7. **Non-representable threshold behavior:** When T is not representable, does the boundary trigger based on the nearest float or some other rule?
8. **Rounding permitted:** Is `.10f` normalization or any other rounding allowed for threshold construction?
9. **Tolerance permitted:** Is an epsilon or tolerance band allowed for boundary comparisons?
10. **Tick-size semantics:** Despite D5, should tick-size normalization be considered as a design amendment?
11. **Decimal in production:** Should Decimal arithmetic be used in the production backtest path or only for numerical analysis?
12. **Same policy for both paths:** Must StrategySpec and ExitCondition use the same numerical convention and threshold formula?
13. **Historical data precision:** If a policy changes threshold computation, must historical OHLC data be re-normalized?
14. **Result hash invariance:** If a mathematically-equivalent implementation change is made, should `result_hash` remain the same?

### 10.2 D1 Semantic Consistency

15. **ExitCondition percentage convention:** Should `pct_of_entry` use percentage points (10.0 = 10%, divide by 100) or fractional ratio (0.1 = 10%, no division)?

### 10.3 Design Amendment

16. **D5 tick-size prohibition:** If tick-size normalization is desired, must D5 be amended?

### 10.4 SHA Mismatch

17. **Design SHA reconciliation:** The locked design SHA has changed from `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d` to `bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166`. The human must determine:
    - Whether the design document was legitimately amended
    - Whether the previous analysis artifacts (referencing SHA `88198b17...`) remain valid references
    - Whether a new design review is required based on the current design content
    - Whether the Phase 1 source modifications (Decimal arithmetic in backtest.py and schemas.py) are consistent with the current design

---

## 11. Design Amendment Gate

No implementation may begin until all of the following are complete:

1. Human selects a policy family.
2. Human defines its exact numerical semantics.
3. Human resolves the D1 percentage semantic.
4. Human resolves StrategySpec/ExitCondition semantic consistency.
5. Human resolves boundary behavior.
6. Human resolves binary64/non-representable threshold behavior.
7. Human resolves rounding/tolerance/tick-size/Decimal behavior where applicable.
8. Human approves the complete rule.
9. A formal design amendment is created.
10. The amended design receives a new SHA-256.
11. The amendment is separately reviewed.
12. Only then may implementation begin.

**Current status:** Steps 1–8 are PENDING HUMAN INPUT. Steps 9–12 have NOT been reached.

**SHA Mismatch Complication:** Step 10 (new SHA-256) is complicated by the fact that the current design file already has a different SHA than the expected locked value. The human must first reconcile this before any new amendment can be properly tracked.

---

## 12. Implementation Gate

**D4 approval does NOT authorize source-code implementation unless the human has explicitly approved the design amendment and a separate implementation task has been issued.**

No implementation may proceed based on this approval record alone. The approval record documents the design-governance boundary between analysis, human design approval, design amendment, and implementation.

Current implementation state (Phase 1 Decimal arithmetic in backtest.py and schemas.py) was applied as separate prior work and is NOT authorized by this D4 approval record.

---

## 13. Future Acceptance-Test Requirements

The subsequent implementation phase must create deterministic tests covering at minimum:

### Percentage Semantics

```text
0.01%
0.1%
1%
2.5%
5%
7.5%
10%
12.5%
25%
33.3%
50%
75%
100%
```

### Entry Prices

```text
0.01
0.1
1
10
99.99
100
100.5
333.33
999.99
10000
```

### Directions

```text
LONG TP
LONG SL
SHORT TP
SHORT SL
```

### Boundary Cases

```text
price exactly at threshold
price immediately below threshold
price immediately above threshold
```

### Numerical Representation Cases

Include:
- Exactly representable thresholds
- Thresholds represented above mathematical T
- Thresholds represented below mathematical T
- Cases where raw arithmetic differs from `float(T)`
- Previously identified D4 counterexamples

### Determinism

Repeated identical inputs must produce identical:
```text
exit decision
trade sequence
metrics
canonical serialization
result_hash
```

---

## 14. Hashing Impact

### 14.1 Affected Hash Systems

The selected numerical policy may change:

| Hash/Serialization | Potential Impact |
|--------------------|------------------|
| `strategy_hash` | If `take_profit_pct`/`stop_loss_pct` serialization changes |
| `config_hash` | If `ExitCondition.pct_of_entry` values change representation |
| `result_hash` | If boundary behavior changes, trade count and P&L may change |
| Trade serialization | If threshold computation changes fill prices |
| Metrics serialization | If equity curve and metrics change |
| Provenance | If canonical serialization format changes |

### 14.2 Behavioral vs. Serialization Impact

The approval document must explicitly distinguish:

- **Behavioral impact:** Changes to exit decisions, trade sequences, and metrics
- **Serialization/hash impact:** Changes to canonical string representations and hash values

A policy must not silently change canonical serialization. The `.10f` canonical serialization convention (design document, Section H) must remain invariant under implementation refactoring that preserves mathematical semantics.

### 14.3 Current State

The Phase 1 Decimal arithmetic changes in `backtest.py` use `Decimal.from_float(close_price)` for price comparison. This changes the comparison mechanism from raw float to Decimal-to-float bridge. The impact on `result_hash` and `config_hash` depends on how the Decimal comparison results serialize.

---

## 15. Execution-Semantics Impact

### 15.1 Interaction with Execution Paths

The eventual D4 policy must interact correctly with:

| Component | Interaction |
|-----------|-------------|
| Same-bar execution | Signal at bar t close → fill at bar t close |
| `execution_delay=0` | Same as same-bar |
| `execution_delay=1` | Signal at bar t close → fill at bar t+1 close |
| TP | Boundary comparison at fill price |
| SL | Boundary comparison at fill price |
| LONG | `price >= threshold` (TP), `price <= threshold` (SL) |
| SHORT | `price <= threshold` (TP), `price >= threshold` (SL) |
| Final-bar behavior | Exit on last bar if condition met |

### 15.2 Same-Bar Re-Entry Blocker

The same-bar re-entry blocker (Blocker #1) is RESOLVED and must remain resolved. The D4 policy must not re-introduce same-bar re-entry behavior.

### 15.3 Phase 1 Current State

The Phase 1 Decimal arithmetic in `backtest.py` already implements inclusive boundary comparisons (`<=` and `>=`) via Decimal operators. This preserves the D3 inclusive boundary semantics.

---

## 16. Security Impact

### 16.1 Per-Policy Risk Analysis

| Policy | Nondeterminism | Platform-Dependent FP | Hidden Implicit Rounding | Uncontrolled External Precision | User-Controlled Tolerance | Inconsistent Percentage Units | Serialization Ambiguity | Inconsistent StrategySpec/ExitCondition Semantics | Fail-Open Numerical Behavior |
|--------|---------------|----------------------|-------------------------|-------------------------------|-------------------------|------------------------------|------------------------|------------------------------------------------|----------------------------|
| A | No | No | REQUIRES DEFINITION | No | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |
| B | No | No | No | No | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |
| C | No | No | Yes (`.10f` precision) | No | No | REQUIRES DEFINITION | Yes (threshold changes) | REQUIRES DEFINITION | REQUIRES DEFINITION |
| D | REQUIRES DEFINITION | No | REQUIRES DEFINITION | No | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |
| E | REQUIRES DEFINITION | No | No | Yes (tick data) | No | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |
| F | No | No | Yes (epsilon) | No | Yes (epsilon value) | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |
| G | No | No | REQUIRES DEFINITION | No | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION | REQUIRES DEFINITION |

### 16.2 Key Security Concerns

- **Policy E** introduces mutable external metadata (tick-size data) — prohibited by D5
- **Policy F** introduces a hidden configuration parameter (epsilon) that could affect financial accounting silently
- **Policy C's** `.10f` precision creates ambiguity about whether 10 decimal places is sufficient for all instruments
- **Policy D and G** introduce architectural complexity that could create silent fallbacks
- **Any policy** must not introduce fail-open numerical behavior where boundary conditions silently pass

---

## 17. Evidence Limitations

### 17.1 Finite Empirical Evidence

The following are established by finite evidence:

- Deterministic corpus: 520 cases per candidate (10 entries × 13 percentages × 4 directions)
- Random corpus: 10,000 cases per candidate (seed=42)
- Candidate A: PASS=180, BELOW=168, ABOVE=172 (deterministic); PASS=0, FAIL=5065, AMBIGUOUS=4935 (random)
- Candidate B: PASS=180, BELOW=176, ABOVE=164 (deterministic); PASS=0, FAIL=4951, AMBIGUOUS=5049 (random)
- `.10f` direction: UP=52, DOWN=42, EQUAL=426 (deterministic)
- True representability: 180 EXACT, 164 ABOVE, 176 BELOW

### 17.2 NOT Established

The corpora do NOT mathematically prove:

- That any candidate can never be universally correct
- That no policy can achieve universal correctness
- That any specific failure rate applies to all possible inputs
- That any policy is universally safe, correct, exact, or proven

### 17.3 Mathematical Reasoning

A separate mathematical argument establishes that when T is not exactly representable in binary64, no binary64-only mechanism can produce a value exactly equal to T. This is a property of IEEE-754 representability, not a consequence of finite testing.

### 17.4 Required Distinction

```text
FINITE-CORPUS COUNTEREXAMPLE ≠ UNIVERSAL IMPOSSIBILITY PROOF
```

---

## 18. Final Status

```text
D4 HUMAN APPROVAL RECORD: COMPLETE
HUMAN POLICY SELECTION: PENDING
BLOCKER #2 D4: BLOCKED — HUMAN DESIGN APPROVAL REQUIRED

ADDITIONAL BLOCKER: LOCKED DESIGN SHA MISMATCH
Expected SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
Computed SHA: bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166
The locked design document has been modified since the analysis artifacts were created.
This SHA mismatch must be reconciled before any design amendment or implementation can proceed.

PHASE 3: NO-GO
```

---

## 19. Artifact Inventory

### 19.1 Existing Artifacts (Untouched)

| File | Status |
|------|--------|
| `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` | Untouched |
| `PHASE3_BLOCKER2_D4_CORRECTED_ARTIFACT_AUDIT.md` | Untouched |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS_CORRECTED.md` | Untouched |
| `PHASE3_BLOCKER2_DESIGN_REVIEW.md` | Untouched |
| `PHASE3_BLOCKER2_DESIGN_AMENDMENT_DRAFT.md` | Untouched |
| `PHASE3_BLOCKER2_FINAL_DECISION_MATRIX.md` | Untouched |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md` | Untouched |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md` | Untouched |
| `PHASE3_BLOCKER2_DESIGN_APPROVAL.md` | Untouched |
| `PHASE3_BLOCKER2_D4_ANALYSIS_AUDIT.md` | Untouched |

### 19.2 New Artifact

| File | Status |
|------|--------|
| `PHASE3_BLOCKER2_D4_HUMAN_APPROVAL_RECORD.md` | **NEW — This document** |

### 19.3 No Overwrites

No existing artifact was overwritten. The only new file created is this approval record.

---

## 20. Source Code Verification (Read-Only)

### 20.1 `src/data_engine/strategy/backtest.py`

Verified via read-only inspection:
- Lines 440-476: Exit condition checking uses Decimal arithmetic
- `Decimal(str(position.entry_fill_price))` for entry price
- `Decimal(str(strategy.stop_loss_pct))` / `Decimal(str(strategy.take_profit_pct))` for percentages
- `Decimal.from_float(close_price)` for price bridge
- Inclusive boundary comparisons via `<=` and `>=` on Decimal objects
- Comments reference "D4.1/D4.2/D4.4" and "D4.6/D4.7"

### 20.2 `src/data_engine/strategy/schemas.py`

Verified via read-only inspection:
- `ExitCondition` model uses `Decimal(str(self.pct_of_entry))` for threshold computation
- `pct_of_entry` field exists as `Optional[float]`
- `canonical_serialize()` method uses `_format_float()` for serialization
- StrategySpec uses `_format_float()` for `stop_loss_pct` and `take_profit_pct` serialization

### 20.3 Design Document

Verified via read-only inspection:
- File size: 2,238 lines, 95,358 bytes
- SHA-256: `bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166`
- Content differs from the expected locked design (2,044 lines, 89,231 bytes)

---

## 21. Unresolved Questions

The following questions remain open for human resolution:

1. Why did the design document SHA change from `88198b17...` to `bd1c606c...`?
2. Was the design legitimately amended, and if so, what content changed?
3. Are the Phase 1 Decimal arithmetic changes in `backtest.py` and `schemas.py` consistent with the current design?
4. Does the current design document still reference D1–D7 requirements?
5. Do the previous analysis artifacts (referencing SHA `88198b17...`) remain valid as evidence?
6. Should the design SHA be re-verified and a new analysis baseline established?
7. What is the current status of Blocker #2 (D4) relative to the current design?

---

*This document establishes the auditable boundary between analysis, human design approval, design amendment, and implementation. No source code, tests, or design documents were modified by this task.*

*All numerical claims are drawn from verified analysis artifacts and read-only source inspection.*

*SHA mismatch must be resolved before any further design or implementation work.*
