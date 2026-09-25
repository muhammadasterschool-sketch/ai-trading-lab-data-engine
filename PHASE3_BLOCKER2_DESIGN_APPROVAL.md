PHASE 3 — BLOCKER #2
DESIGN AMENDMENT DECISION EXTRACTION

==================================================
A. CURRENT BLOCKER SUMMARY
==================================================

Blocker: TAKE-PROFIT / STOP-LOSS FLOATING-POINT BOUNDARY SEMANTICS
Status: BLOCKED — AWAITING EXPLICIT HUMAN DESIGN APPROVAL
Phase 3 Status: NO-GO

The bug: With `entry_fill_price=100.0, take_profit_pct=10.0`, the threshold computes as
`100.0 * 1.1 = 110.00000000000001` in IEEE-754 binary64. The comparison `110.0 >= 110.00000000000001`
evaluates `False`, meaning a take-profit at exactly the mathematical boundary never triggers.

This affects LONG take-profit and SHORT stop-loss. LONG stop-loss and SHORT take-profit are
unaffected because `100.0 * 0.9 = 90.0` is exact in IEEE-754.

The design does not specify how floating-point boundary equality must be interpreted for exit
threshold comparisons. Implementation exists but is unauthorized by the locked design.

==================================================
B. VERIFIED FACTS
==================================================

FACT 1 — Design SHA Integrity
* Initial SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
* Final SHA:   88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
* Unchanged: YES
* git diff --stat: empty (no tracked files modified)

FACT 2 — Formula for StrategySpec Percentage Exits
* Implementation: `threshold = entry_fill_price * (1 + take_profit_pct / 100)`
* `take_profit_pct=10.0` means 10%, formula divides by 100
* `stop_loss_pct=10.0` means 10%, formula divides by 100
* Source: `src/data_engine/strategy/backtest.py`, `_check_exit_conditions()`, lines 443-456
* Design status: NOT explicitly stated in the locked design doc. The formula exists only in implementation.

FACT 3 — Formula for ExitCondition Percentage Exits
* Implementation: `entry_price * (1.0 + self.pct_of_entry)` for take_profit
* Implementation: `entry_price * (1.0 - self.pct_of_entry)` for stop_loss
* `pct_of_entry=0.1` means 10% (FRACTION, not percentage)
* Source: `src/data_engine/strategy/schemas.py`, `ExitCondition.evaluate()`, lines 165-170
* Design status: NOT explicitly stated in the locked design doc. The formula exists only in implementation.

FACT 4 — Inconsistency Between Paths
* `StrategySpec.take_profit_pct` uses PERCENTAGE units (10.0 = 10%, divided by 100)
* `ExitCondition.pct_of_entry` uses FRACTION units (0.1 = 10%, no division)
* The design doc does NOT define the unit of either field
* The design doc does NOT state that these two paths must or must not be consistent
* This is an implementation-only convention, not a locked design requirement

FACT 5 — IEEE-754 Boundary Reproduction
* entry=100.0, TP=10%: threshold=110.00000000000001421, close=110.0 does NOT trigger LONG TP
* entry=100.0, SL=10%: threshold=90.0 (EXACT), close=90.0 DOES trigger LONG SL
* entry=100.0, TP=10%: threshold=90.0 (EXACT), close=90.0 DOES trigger SHORT TP
* entry=100.0, SL=10%: threshold=110.00000000000001421, close=110.0 does NOT trigger SHORT SL
* Non-round entries (e.g., 100.5, TP=10%): threshold=110.55000000000001, boundary also fails

FACT 6 — No Floating-Point Policy for Exit Comparisons Exists in Design
* Line 99: `equity == cash + position_market_value (within floating-point tolerance)` — equity invariant only
* Line 1453: `BREAKEVEN_TOLERANCE = 1e-10` — breakeven counting only
* Line 637: IEEE-754 representation acknowledged for serialization/hashing only
* No tolerance, rounding, quantization, or Decimal policy exists for exit threshold comparisons
* The EDGE CASES section (lines 392-401) covers execution timing, NOT floating-point boundaries

FACT 7 — No Instrument/Tick Metadata Exists in Architecture
* `Instrument` model has: symbol, asset_class, base_asset, quote_asset, contract_type, currency, exchange, venue, provider_symbol
* `Instrument` has NO tick_size, price_precision, pip, or lot_size fields
* `Candle` model has NO tick-size or precision metadata
* No shared comparison utility exists anywhere in the codebase
* No decimal representation infrastructure exists

FACT 8 — Both Exit Paths Are Implementation Behavior
* `_check_exit_conditions()` in `backtest.py` uses StrategySpec percentage fields with `/100` division
* `ExitCondition.evaluate()` in `schemas.py` uses `pct_of_entry` as fraction
* Neither path is referenced or authorized by the locked design doc's formula sections
* The design doc lists these as fields (config_hash ordering, line 681) but never defines computation

FACT 9 — Comparison Operators in Design
* The design doc defines `operator` values: `>`, `<`, `>=`, `<=`, `==`, `!=`, `AND`, `OR`, `NOT` (line 748)
* These are for the condition serialization tree format, not for take_profit/stop_loss evaluation
* The design does NOT mandate which operator applies to which exit type

==================================================
C. DESIGN GAPS
==================================================

GAP 1 — Threshold Formula Not Defined
The locked design does not specify the formula for computing take_profit/stop_loss thresholds
from `take_profit_pct`/`stop_loss_pct`. It only lists these as fields in `StrategySpec`.

GAP 2 — pct_of_entry Unit Not Defined
The design does not specify whether `ExitCondition.pct_of_entry` is a percentage (10.0) or
fraction (0.1). The implementation uses fraction, but this is not authorized by the design.

GAP 3 — Boundary Equality Semantics Not Defined
The design does not specify whether a price exactly equal to the mathematically-computed
threshold must trigger an exit. The existing behavior is IEEE-754-dependent and may fail at
the boundary.

GAP 4 — Floating-Point Policy for Exit Comparisons Not Defined
The design acknowledges floating-point imprecision for equity invariants and serialization,
but never extends this to exit threshold comparisons. No tolerance, rounding, Decimal, or
quantization policy is specified for exit evaluation.

GAP 5 — LONG/SHORT Symmetry Not Addressed
The design does not state whether LONG and SHORT exit semantics must be symmetric with
respect to floating-point boundary behavior.

GAP 6 — Cross-Path Consistency Not Defined
The design does not state whether `StrategySpec.take_profit_pct`/`stop_loss_pct` and
`ExitCondition.pct_of_entry` must share identical mathematical semantics. The current
implementation uses different units (percentage vs fraction).

GAP 7 — Determinism Requirements Not Explicit
The design does not explicitly state what determinism requirements apply to exit evaluation
across Python versions, operating systems, or CPU architectures.

==================================================
D. REQUIRED HUMAN DECISIONS
==================================================

DECISION 1 — Threshold Formula
What is the exact formula for computing take_profit/stop_loss thresholds from StrategySpec
percentage fields?

CURRENT IMPLEMENTATION:
  take_profit_threshold = entry_fill_price * (1 + take_profit_pct / 100)
  stop_loss_threshold    = entry_fill_price * (1 - stop_loss_pct / 100)

DESIGN GAP:
  The formula is not stated in the locked design doc.

REQUIRED APPROVAL:
  Must explicitly authorize the formula (or a different one).

DECISION 2 — pct_of_entry Unit
What unit does `ExitCondition.pct_of_entry` represent?

CURRENT IMPLEMENTATION:
  Fraction (0.1 = 10%). Formula: entry_price * (1.0 + pct_of_entry)

CURRENT INCONSISTENCY:
  StrategySpec uses percentage (10.0 = 10%, /100 in formula).
  ExitCondition uses fraction (0.1 = 10%, no /100 in formula).

DESIGN GAP:
  Neither unit is defined in the locked design doc.

REQUIRED APPROVAL:
  Must explicitly define the unit for pct_of_entry and reconcile with StrategySpec.

DECISION 3 — Boundary Equality
At the mathematically exact boundary, should the exit trigger?

CURRENT BEHAVIOR:
  LONG TP: close=110.0 does NOT trigger (threshold=110.00000000000001)
  LONG SL: close=90.0 DOES trigger (threshold=90.0 exactly)
  SHORT TP: close=90.0 DOES trigger (threshold=90.0 exactly)
  SHORT SL: close=110.0 does NOT trigger (threshold=110.00000000000001)

DESIGN GAP:
  The design does not specify boundary equality semantics.

REQUIRED APPROVAL:
  Must explicitly state whether each of the four exit types triggers at mathematical equality.

DECISION 4 — Floating-Point Policy
What semantic model governs exit threshold comparisons?

CANDIDATES (not ranked, not selected):
  A. Exact IEEE-754 float comparison (current behavior, no change)
  B. Explicit decimal arithmetic (Decimal)
  C. Explicit fixed precision / quantization
  D. Explicit tolerance (absolute, relative, or scale-dependent)
  E. Mathematical comparison reformulation
  F. Tick-aware price semantics

DESIGN GAP:
  No policy is specified. The design is silent on exit comparison semantics.

REQUIRED APPROVAL:
  Must explicitly select a policy (or define a new one).

DECISION 5 — LONG/SHORT Symmetry
Must LONG and SHORT take-profit/stop-loss use symmetric floating-point semantics?

CURRENT STATE:
  No symmetry requirement exists in the design.
  The current behavior is NOT symmetric in practice (LONG TP and SHORT SL are affected,
  LONG SL and SHORT TP are not, due to IEEE-754 properties of 0.9 vs 1.1).

DESIGN GAP:
  No symmetry requirement is defined.

REQUIRED APPROVAL:
  Must explicitly state whether symmetry is required and what it means.

DECISION 6 — StrategySpec / ExitCondition Consistency
Must StrategySpec.take_profit_pct/stop_loss_pct and ExitCondition.pct_of_entry use the
same mathematical semantics?

CURRENT STATE:
  They use different units (percentage vs fraction) and different formula conventions.
  The design does not address this.

DESIGN GAP:
  No consistency requirement is defined.

REQUIRED APPROVAL:
  Must explicitly state whether the two paths must be consistent and how.

DECISION 7 — Determinism
What determinism requirements must apply to exit evaluation?

CANDIDATES (not ranked, not selected):
  A. Identical results across repeated runs with same seed
  B. Identical results across Python versions in supported range
  C. Identical results across operating systems
  D. Identical results across CPU architectures
  E. All of the above

DESIGN GAP:
  The design does not explicitly state determinism requirements for exit evaluation.

REQUIRED APPROVAL:
  Must explicitly define the determinism scope.

==================================================
E. HUMAN-APPROVAL CHECKLIST
==================================================

Each decision below requires explicit human approval. Do not fill choices — leave blank for
human reviewer.

─────────────────────────────────────────────────────────────────────
DECISION 1 — Threshold Formula
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. entry × (1 + pct/100) for TP, entry × (1 - pct/100) for SL (current implementation)
  B. Alternative formula (specify: _____________________________)
  C. Other (specify: _____________________________)
Approved rule: ________________________________________________

─────────────────────────────────────────────────────────────────────
DECISION 2 — pct_of_entry Unit
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. Percentage points (10.0 = 10%, formula divides by 100)
  B. Fractional ratio (0.1 = 10%, formula does not divide by 100)
  C. Other (specify: _____________________________)
Approved rule: ________________________________________________
Reconciliation with StrategySpec: _________________________________

─────────────────────────────────────────────────────────────────────
DECISION 3 — Boundary Equality
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
LONG TP at mathematical boundary: [TRIGGERS / DOES NOT TRIGGER / UNDEFINED]
LONG SL at mathematical boundary: [TRIGGERS / DOES NOT TRIGGER / UNDEFINED]
SHORT TP at mathematical boundary: [TRIGGERS / DOES NOT TRIGGER / UNDEFINED]
SHORT SL at mathematical boundary: [TRIGGERS / DOES NOT TRIGGER / UNDEFINED]
Rationale: ____________________________________________________

─────────────────────────────────────────────────────────────────────
DECISION 4 — Floating-Point Policy
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. Exact IEEE-754 float comparison (no change to current behavior)
  B. Explicit decimal arithmetic (Decimal)
  C. Explicit fixed precision / quantization (precision: ____________)
  D. Explicit tolerance (type: ____________, value: ____________)
  E. Mathematical comparison reformulation
  F. Tick-aware price semantics
  G. Other (specify: _____________________________)
Approved rule: ________________________________________________

─────────────────────────────────────────────────────────────────────
DECISION 5 — LONG/SHORT Symmetry
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. LONG and SHORT must use symmetric semantics
  B. LONG and SHORT may differ (each exit type handled independently)
  C. Symmetry required only when IEEE-754 representation is exact
  D. Other (specify: _____________________________)
Approved rule: ________________________________________________

─────────────────────────────────────────────────────────────────────
DECISION 6 — StrategySpec / ExitCondition Consistency
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. Must use identical mathematical semantics (and units)
  B. May differ, but both must follow the same floating-point policy
  C. No consistency requirement
  D. Other (specify: _____________________________)
Approved rule: ________________________________________________

─────────────────────────────────────────────────────────────────────
DECISION 7 — Determinism
─────────────────────────────────────────────────────────────────────
Status: REQUIRES APPROVAL
Choice: [  ]
  A. Identical across repeated runs only
  B. Identical across Python versions in supported range
  C. Identical across operating systems
  D. Identical across CPU architectures
  E. All of the above (B, C, D)
  F. Other (specify: _____________________________)
Approved rule: ________________________________________________

─────────────────────────────────────────────────────────────────────

ALL SEVEN DECISIONS MUST BE APPROVED BEFORE IMPLEMENTATION BEGINS.

==================================================
F. PROPOSED DESIGN AMENDMENT — NOT YET APPROVED
==================================================

The following normative text is a PROPOSAL for human approval. Do not modify the design document.
Multiple alternative versions are provided where necessary. The design reviewer may choose
any option or define a new one.

--------------------------------------------------
F.1 THRESHOLD CALCULATION SECTION
--------------------------------------------------

AMENDMENT OPTION A (current formula preserved)

"**Take-Profit and Stop-Loss Threshold Calculation**

Percentage-based take-profit and stop-loss thresholds are computed from StrategySpec fields
`take_profit_pct` and `stop_loss_pct` (expressed as percentage points, e.g. 10.0 = 10%):

For a LONG position with entry price E:
  take_profit_threshold = E × (1 + take_profit_pct / 100)
  stop_loss_threshold    = E × (1 - stop_loss_pct / 100)

For a SHORT position with entry price E:
  take_profit_threshold = E × (1 - take_profit_pct / 100)
  stop_loss_threshold    = E × (1 + stop_loss_pct / 100)

These computations use Python's native `float` type (IEEE-754 binary64)."

AMENDMENT OPTION B (alternative formula)

"**Take-Profit and Stop-Loss Threshold Calculation**

Percentage-based take-profit and stop-loss thresholds are computed as:

For a LONG position with entry price E, take-profit percentage TP, and stop-loss percentage SL:
  take_profit_threshold = E × (1 + TP / 100)
  stop_loss_threshold    = E × (1 - SL / 100)

For a SHORT position with entry price E, take-profit percentage TP, and stop-loss percentage SL:
  take_profit_threshold = E × (1 - TP / 100)
  stop_loss_threshold    = E × (1 + SL / 100)

Where `take_profit_pct` and `stop_loss_pct` are expressed as percentage points.

[Alternative: thresholds may be computed using decimal arithmetic if the floating-point policy
requires it. See the Floating-Point Policy section.]"

--------------------------------------------------
F.2 pct_of_entry UNIT SECTION
--------------------------------------------------

AMENDMENT OPTION A (fraction-based, matching current ExitCondition)

"**ExitCondition Percentage Fields**

`ExitCondition.pct_of_entry` represents a fractional ratio (0.1 = 10%, not 10.0 = 10%).

The `evaluate()` method computes thresholds as:
  take_profit: entry_price × (1.0 + pct_of_entry)
  stop_loss:   entry_price × (1.0 - pct_of_entry)

`StrategySpec.take_profit_pct` and `StrategySpec.stop_loss_pct` represent percentage points
(10.0 = 10%).

Implementations MUST clearly document which unit each field uses. The two paths may use
different units provided they follow the same floating-point policy."

AMENDMENT OPTION B (unified units)

"**ExitCondition Percentage Fields**

All percentage-based exit fields in the design use a single canonical unit.

[If percentage points:]
`StrategySpec.take_profit_pct`, `StrategySpec.stop_loss_pct`, and `ExitCondition.pct_of_entry`
are all expressed as percentage points (10.0 = 10%). Formulas divide by 100 where appropriate.

[If fractional:]
`StrategySpec.take_profit_pct`, `StrategySpec.stop_loss_pct`, and `ExitCondition.pct_of_entry`
are all expressed as fractional ratios (0.1 = 10%). Formulas do not divide by 100."

--------------------------------------------------
F.3 BOUNDARY EQUALITY SECTION
--------------------------------------------------

AMENDMENT OPTION A (boundary inclusive)

"**Boundary Equality Semantics**

At the mathematically exact boundary (e.g., close_price equals entry × (1 + take_profit_pct/100)
in exact arithmetic), the exit condition MUST trigger for all four exit types:
- LONG take-profit: TRIGGERS at equality
- LONG stop-loss: TRIGGERS at equality
- SHORT take-profit: TRIGGERS at equality
- SHORT stop-loss: TRIGGERS at equality

Implementations must ensure boundary-triggering even when IEEE-754 representation differs
from the mathematical value."

AMENDMENT OPTION B (boundary follows IEEE-754)

"**Boundary Equality Semantics**

Exit comparisons use raw IEEE-754 `float` values without tolerance, rounding, or quantization.
At the mathematically exact boundary, the comparison result depends on IEEE-754 representation.
A price exactly equal to the mathematical boundary MAY OR MAY NOT trigger depending on the
IEEE-754 representation of the computed threshold.

This behavior is documented and tested, but is not considered a defect."

AMENDMENT OPTION C (per-exit-type specification)

"**Boundary Equality Semantics**

Boundary behavior is specified per exit type:

| Exit Type | Boundary Equality |
|-----------|-------------------|
| LONG take-profit | [TRIGGERS / DOES NOT TRIGGER] |
| LONG stop-loss   | [TRIGGERS / DOES NOT TRIGGER] |
| SHORT take-profit | [TRIGGERS / DOES NOT TRIGGER] |
| SHORT stop-loss   | [TRIGGERS / DOES NOT TRIGGER] |

[Justification: _____________________________]"

--------------------------------------------------
F.4 FLOATING-POINT POLICY SECTION
--------------------------------------------------

AMENDMENT OPTION A (exact IEEE-754)

"**Floating-Point Policy for Exit Evaluation**

All take-profit and stop-loss threshold calculations and comparisons use Python's native `float`
type (IEEE-754 binary64). Thresholds are computed using `float` multiplication. Comparisons use
raw `>=` and `<=` operators on `float` values without tolerance, rounding, quantization, or
Decimal arithmetic. Boundary behavior follows IEEE-754 representation exactly."

AMENDMENT OPTION B (explicit tolerance)

"**Floating-Point Policy for Exit Evaluation**

All take-profit and stop-loss threshold calculations use Python's native `float` type (IEEE-754
binary64). Comparisons use a tolerance of [TBD by human reviewer] applied as:

A price P is considered to satisfy a comparison against threshold T when:
  P >= T - tolerance (for take-profit LONG)
  P <= T + tolerance (for stop-loss LONG)
[and symmetrically for SHORT and other exit types]

The tolerance value, scope, and definition location are specified in the Determinism section."

AMENDMENT OPTION C (explicit Decimal)

"**Floating-Point Policy for Exit Evaluation**

All take-profit and stop-loss threshold calculations use `decimal.Decimal` arithmetic with
precision [TBD]. Thresholds are computed and compared using `Decimal` values. The `decimal`
context precision and rounding mode are specified in the Determinism section."

AMENDMENT OPTION D (tick-aware)

"**Floating-Point Policy for Exit Evaluation**

Exit threshold comparisons are evaluated at the instrument's tick granularity. A price P
satisfies a comparison against threshold T if P and T are on the same tick grid and the
mathematical comparison holds. Tick-size metadata originates from the [TBD] source."

--------------------------------------------------
F.5 LONG/SHORT SYMMETRY SECTION
--------------------------------------------------

AMENDMENT OPTION A (symmetric required)

"**LONG/SHORT Symmetry**

Take-profit and stop-loss exit evaluation MUST be symmetric between LONG and SHORT positions
with respect to floating-point boundary behavior. For any entry price E, percentage P, and
close price C:
  LONG take-profit(E, P) triggers at C   iff   SHORT stop-loss(E, P) triggers at (E - C + E)
  LONG stop-loss(E, P) triggers at C    iff   SHORT take-profit(E, P) triggers at (E + C - E)

[Precise symmetric mapping to be defined by human reviewer.]"

AMENDMENT OPTION B (symmetry not required)

"**LONG/SHORT Symmetry**

LONG and SHORT exit evaluation may differ in floating-point boundary behavior. Each exit type
is evaluated independently according to its own threshold calculation and comparison operator.
No symmetry requirement is imposed."

--------------------------------------------------
F.6 CONSISTENCY SECTION
--------------------------------------------------

AMENDMENT OPTION A (must be consistent)

"**StrategySpec / ExitCondition Consistency**

`StrategySpec.take_profit_pct`/`stop_loss_pct` and `ExitCondition.pct_of_entry` MUST use the
same mathematical semantics. Both paths compute the same threshold using the same formula and
follow the same floating-point policy. Any difference in units between the two paths must be
explicitly documented and reconciled at the API boundary."

AMENDMENT OPTION B (policy-only consistency)

"**StrategySpec / ExitCondition Consistency**

`StrategySpec.take_profit_pct`/`stop_loss_pct` and `ExitCondition.pct_of_entry` MAY use
different units or formula conventions, provided both follow the same floating-point policy
and produce equivalent threshold values for equivalent percentage specifications."

--------------------------------------------------
F.7 DETERMINISM SECTION
--------------------------------------------------

AMENDMENT OPTION A (full determinism)

"**Determinism**

All exit evaluation must produce identical results across:
- Repeated executions with identical inputs
- All Python versions within the supported range
- All supported operating systems
- All supported CPU architectures

Exit evaluation must be free of platform-dependent floating-point non-determinism. Where
IEEE-754 implementation differences exist, the design must specify a canonical result."

AMENDMENT OPTION B (repeated-execution determinism only)

"**Determinism**

All exit evaluation must produce identical results across repeated executions with identical
inputs within a single Python process. Cross-platform determinism is not required but is
recommended."

--------------------------------------------------
F.8 ACCEPTANCE TEST REQUIREMENTS
--------------------------------------------------

"**Take-Profit / Stop-Loss Boundary Tests**

All percentage-based exit paths must be tested with the following boundary matrix:

For each exit type (LONG TP, LONG SL, SHORT TP, SHORT SL):
  - Exactly at the mathematical boundary
  - One IEEE-754 representable value below the boundary
  - One IEEE-754 representable value above the boundary

Additionally, test with:
  - Non-round entry prices (e.g., 100.5, 99.99) where boundary representation differs
  - Non-integer percentages
  - Values susceptible to binary representation error
  - Deterministic repeated execution (same inputs produce same outputs)
  - Both StrategySpec percentage exit path and ExitCondition.pct_of_entry path

Test suites must document the IEEE-754 behavior at each boundary and must not assume
mathematical boundary equality unless explicitly authorized by the floating-point policy."

==================================================
G. POST-APPROVAL IMPLEMENTATION SCOPE
==================================================

The following files/functions would need modification after human design approval.
These modifications are NOT performed now — they are listed for planning purposes only.

G.1 IF DESIGN APPROVES TOLERANCE:
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — add tolerance to comparison
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — add tolerance to comparison
- `tests/test_strategy_independent.py`: add boundary tests expecting tolerance-based triggering

G.2 IF DESIGN APPROVES ROUNDING/QUANTIZATION:
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — quantize threshold
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — quantize threshold
- `tests/test_strategy_independent.py`: add boundary tests expecting quantized triggering

G.3 IF DESIGN APPROVES EXACT IEEE-754 (NO CHANGE):
- No source code changes needed
- Only tests would need updating to document existing IEEE-754 behavior
- Design doc must be amended to explicitly state this policy

G.4 IF DESIGN APPROVES DECIMAL:
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — convert to Decimal
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — convert to Decimal
- Potentially entire data flow (Instrument, Candle, Position, Trade, EquityPoint)
- Major architectural amendment required

G.5 IF DESIGN APPROVES TICK-AWARE:
- `src/data_engine/schemas.py`: `Instrument` — add tick_size field
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — use tick_size
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — use tick_size
- Major architectural amendment required

G.6 IF DESIGN RECONCILES pct_of_entry UNITS:
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — may need unit conversion
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — may need unit conversion
- Test fixtures may need updating

==================================================
H. REGRESSION-TEST SCOPE (POST-APPROVAL)
==================================================

The following tests would be implemented after design approval. They are NOT added now.

H.1 LONG TAKE PROFIT BOUNDARY MATRIX
- entry=100.0, TP=10.0%, close=110.0 (exact boundary) → Documented IEEE-754 behavior
- entry=100.0, TP=10.0%, close=110.00000000000001 → Above threshold (should trigger)
- entry=100.0, TP=10.0%, close=109.99 → Below threshold (should not trigger)
- entry=100.0, TP=10.0%, close=111.0 → Above threshold (should trigger)

H.2 LONG STOP LOSS BOUNDARY MATRIX
- entry=100.0, SL=10.0%, close=90.0 (exact boundary) → Triggers (exact in IEEE-754)
- entry=100.0, SL=10.0%, close=90.00000000000001 → Above threshold (should not trigger)
- entry=100.0, SL=10.0%, close=89.99 → Below threshold (should trigger)
- entry=100.0, SL=10.0%, close=91.0 → Above threshold (should not trigger)

H.3 SHORT TAKE PROFIT BOUNDARY MATRIX
- entry=100.0, TP=10.0%, close=90.0 (exact boundary) → Triggers (exact in IEEE-754)
- entry=100.0, TP=10.0%, close=89.99 → Below boundary (should trigger)
- entry=100.0, TP=10.0%, close=90.00000000000001 → Above boundary (should not trigger)
- entry=100.0, TP=10.0%, close=91.0 → Above boundary (should not trigger)

H.4 SHORT STOP LOSS BOUNDARY MATRIX
- entry=100.0, SL=10.0%, close=110.0 (exact boundary) → Documented IEEE-754 behavior
- entry=100.0, SL=10.0%, close=110.00000000000001 → Above threshold (should trigger)
- entry=100.0, SL=10.0%, close=109.99 → Below threshold (should not trigger)
- entry=100.0, SL=10.0%, close=111.0 → Above threshold (should trigger)

H.5 NON-ROUND ENTRY TESTS
- entry=100.5, TP=10.0%, close=110.55 (mathematical boundary) → Documented behavior
- entry=99.99, TP=10.0%, close=109.989 → Documented behavior
- entry=1000.0, TP=10.0%, close=1100.0 → Documented behavior (exact in IEEE-754)

H.6 ExitCondition.evaluate() TESTS
- ExitCondition(type='take_profit', pct_of_entry=0.1).evaluate(entry_price=100.0, current_price=110.0)
- ExitCondition(type='stop_loss', pct_of_entry=0.1).evaluate(entry_price=100.0, current_price=90.0)
- Both paths tested with documented pct_of_entry unit convention

H.7 DETERMINISM TESTS
- Run identical backtest 100 times with same seed → identical results
- Same backtest with different Python versions → same exit triggers
- Cross-platform verification (if design requires)

H.8 CROSS-PATH CONSISTENCY TESTS
- StrategySpec take_profit_pct=10.0 path vs ExitCondition(type='take_profit', pct_of_entry=0.1)
- Both paths tested with identical entry/close/percentage values
- Both must produce identical trigger behavior per design decision

==================================================
I. INTEGRITY VERIFICATION
==================================================

* No source modifications: CONFIRMED (git diff --stat is empty)
* No test modifications: CONFIRMED
* No design modifications: CONFIRMED (git diff docs/strategy_engine_design.md is empty)
* Design SHA unchanged: CONFIRMED (88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d)
* No tolerance/rounding/Decimal/tick logic introduced: CONFIRMED
* No comparison operators modified: CONFIRMED
* No implementation behavior changed: CONFIRMED
* The only new artifact is this approval checkpoint document

==================================================
J. FINAL STATUS
==================================================

BLOCKED — AWAITING EXPLICIT HUMAN DESIGN APPROVAL

All seven decisions (D1–D7) in Section E must be explicitly approved by a human reviewer
before any implementation work on Blocker #2 can begin. The proposed normative text in
Section F is a proposal only and must not be inserted into the locked design document
without explicit human approval.

Phase 3 remains NO-GO. Blocker #1 (same-bar re-entry) is RESOLVED. Blocker #2 is BLOCKED
by design ambiguity. No further implementation progress on Blocker #2 is permitted
until the human approval checklist is completed.

==================================================
END OF DESIGN APPROVAL CHECKPOINT
==================================================
