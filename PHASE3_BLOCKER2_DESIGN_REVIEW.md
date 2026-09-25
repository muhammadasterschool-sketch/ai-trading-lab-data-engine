PHASE 3 — BLOCKER #2: DESIGN CLARIFICATION / AMENDMENT REVIEW
TAKE-PROFIT / STOP-LOSS FLOATING-POINT BOUNDARY SEMANTICS

==================================================
A. DESIGN INTEGRITY
==================================================

* Initial SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
* Final SHA:   88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d
* Unchanged:   YES
* Source modifications: NONE (git diff --stat is empty)
* Test modifications: NONE
* Design modifications: NONE

==================================================
B. EXISTING LOCKED SEMANTICS
==================================================

B.1 EXPLICIT REQUIREMENTS (directly stated in design doc)
---------------------------------------------------------

1. The design doc defines `StrategySpec` as having `stop_loss_pct` and `take_profit_pct` fields (line 681, config_hash ordering). Their presence is explicit; their computational semantics are NOT defined.

2. `ExitCondition` is a defined model class with `type`, `operator`, `threshold`, `pct_of_entry` fields (line 45, module structure; line 680, config_hash). The `operator` field values are `>`, `<`, `>=`, `<=`, `==`, `!=`, `AND`, `OR`, `NOT` (line 748).

3. Condition serialization uses `.10f` float formatting for `threshold_value` and all float values (line 751, 766, 773, 779).

4. The equity invariant: `equity == cash + position_market_value (within floating-point tolerance)` (line 99). This establishes a precedent that floating-point imprecision is acknowledged in the design.

5. `BREAKEVEN_TOLERANCE = 1e-10` is defined (line 1453) exclusively for breakeven trade counting.

6. IEEE-754 representation discrepancy is explicitly acknowledged: "Two floats that are mathematically equal but differ in their binary IEEE-754 representation (e.g., `1.0` vs `1.0000000000000002`) must serialize to the same `.10f` string and therefore hash identically" (line 637). This is about hashing/serialization only.

7. The EDGE CASES section (lines 392-401) covers execution timing (same-bar, delay, missing OHLC) but NOT floating-point boundary comparison semantics.

8. The design doc states: "Every major design rule is structured as: DESIGN DECISION, RATIONALE, FORMULA/RULE, EDGE CASES, ACCEPTANCE TESTS" (lines 11-15).

B.2 STRONG IMPLICATIONS (strongly suggested but not explicitly mandated)
---------------------------------------------------------------------------

1. The existence of `take_profit_pct` and `stop_loss_pct` as percentage fields on `StrategySpec` implies they are applied as percentage deviations from entry price. The exact formula is NOT specified in the design doc but is clearly `entry * (1 ± pct/100)` based on the `ExitCondition` model's `pct_of_entry` field.

2. The `operator` field in `ExitCondition` and the condition serialization format strongly imply directional comparison semantics (LONG TP uses `>=`, LONG SL uses `<=`, SHORT TP uses `<=`, SHORT SL uses `>=`). The design doc does NOT mandate which operator applies to which exit type.

3. The `_check_exit_conditions` method in `backtest.py` and `ExitCondition.evaluate()` in `schemas.py` both independently implement the same conceptual model: percentage threshold + directional comparison. This is implementation behavior, not a locked design requirement.

4. The `.10f` serialization format implies awareness of float imprecision but is scoped to serialization/hashing, not to runtime comparison.

B.3 IMPLEMENTATION-ONLY BEHAVIOR (NOT locked by design)
---------------------------------------------------------

1. `_check_exit_conditions()` computes: `threshold = entry_fill_price * (1 + strategy.take_profit_pct / 100)` with `close_price >= threshold`. This exact formula and comparison operator exist ONLY in the implementation, not in the design doc.

2. `ExitCondition.evaluate()` computes: `current_price >= entry_price * (1.0 + self.pct_of_entry)` for take_profit and `current_price <= entry_price * (1.0 - self.pct_of_entry)` for stop_loss. This exact logic exists ONLY in the implementation.

3. Both paths use Python's native `float` (IEEE-754 binary64) for all arithmetic and comparison.

4. `BREAKEVEN_TOLERANCE = 1e-10` is defined at module scope in `backtest.py` but is used ONLY for breakeven counting, not for exit comparisons.

5. The `PositionTracker`, `TradeLedger`, `EquityTracker`, and `ExecutionModel` all operate on `float` values without any decimal or quantization abstraction.

B.4 UNDEFINED BEHAVIOR (not specified anywhere)
---------------------------------------------------------

1. **The exact formula for computing take_profit/stop_loss thresholds from `take_profit_pct`/`stop_loss_pct` is NOT defined in the design doc.** The design lists these as fields but never specifies `entry * (1 + pct/100)`.

2. **The comparison operator for take_profit/stop_loss evaluation is NOT defined in the design doc.** The design doc defines `operator` values in condition serialization but never states that take_profit uses `>=` or stop_loss uses `<=`.

3. **Floating-point boundary behavior for price comparisons is NOT defined.** The design acknowledges float imprecision for equity invariants and serialization, but never for exit threshold comparisons.

4. **Whether `pct_of_entry` in `ExitCondition` is a percentage (10.0) or a fraction (0.1) is NOT defined in the design doc.** The `evaluate()` method uses `1.0 + self.pct_of_entry` which implies fraction, but no design section specifies this.

5. **No tolerance, rounding, quantization, or Decimal policy exists anywhere in the locked design for runtime price comparisons.**

6. **LONG/SHORT symmetry for floating-point boundary behavior is NOT addressed in the design.**

7. **The interaction between `StrategySpec take_profit_pct` path and `ExitCondition.evaluate()` path is NOT addressed in the design.** They are separate code paths with separate formula conventions.

==================================================
C. REPRODUCTION
==================================================

All cases tested using Python's native `float` (IEEE-754 binary64):

C.1 LONG TAKE PROFIT — ENTRY=100.0, TP=10%
----------------------------------------------
  Mathematical threshold: 110.0
  IEEE-754 threshold:     110.00000000000001421
  close=110.0 >= threshold: FALSE (BUG)
  Affected code paths: _check_exit_conditions, ExitCondition.evaluate

C.2 LONG STOP LOSS — ENTRY=100.0, SL=10%
-------------------------------------------
  Mathematical threshold: 90.0
  IEEE-754 threshold:     90.00000000000000000 (EXACT)
  close=90.0 <= threshold: TRUE (works)
  Reason: 100.0 * 0.9 = 90.0 exactly in IEEE-754

C.3 SHORT TAKE PROFIT — ENTRY=100.0, TP=10%
----------------------------------------------
  Mathematical threshold: 90.0
  IEEE-754 threshold:     90.00000000000000000 (EXACT)
  close=90.0 <= threshold: TRUE (works)
  Reason: 100.0 * 0.9 = 90.0 exactly in IEEE-754

C.4 SHORT STOP LOSS — ENTRY=100.0, SL=10%
-------------------------------------------
  Mathematical threshold: 110.0
  IEEE-754 threshold:     110.00000000000001421
  close=110.0 >= threshold: FALSE (BUG)
  Affected code paths: _check_exit_conditions, ExitCondition.evaluate

C.5 NON-ROUND ENTRY — ENTRY=100.5, TP=10%
-------------------------------------------
  Mathematical threshold: 110.55
  IEEE-754 threshold:     110.55000000000001137
  close=110.55 >= threshold: FALSE (BUG)
  LONG TP affected

C.6 BOUNDARY WITH ADJACENT REPRESENTABLE FLOATS
-------------------------------------------------
  For entry=100.0, TP=10%:
    threshold = 110.00000000000001
    next_up = 110.00000000000003 (diff: 1.4210854715202004e-14)
    close=110.0 != threshold (representation mismatch)
    close=110.0 < next_up (110.0 is below the computed threshold)

  For entry=100.0, SL=10%:
    threshold = 90.0 (exact)
    next_up = 90.00000000000001 (diff: 1.4210854715202004e-17)
    close=90.0 == threshold (exact match)

CONCLUSION: The bug affects exactly 2 of 4 exit types at the exact mathematical boundary: LONG take-profit and SHORT stop-loss. LONG stop-loss and SHORT take-profit are unaffected because multiplication by 0.9 produces exact results for round entry prices.

==================================================
D. SCOPE
==================================================

D.1 AFFECTED CODE PATHS
-------------------------

Path 1: StrategySpec take_profit_pct (via _check_exit_conditions in backtest.py)
  Formula: threshold = entry_fill_price * (1 + take_profit_pct / 100)
  Comparison: close_price >= threshold (LONG TP), close_price <= threshold (LONG SL)
  Impact: LONG TP boundary, SHORT SL boundary

Path 2: StrategySpec stop_loss_pct (via _check_exit_conditions in backtest.py)
  Formula: threshold = entry_fill_price * (1 - stop_loss_pct / 100)
  Comparison: close_price <= threshold (LONG SL), close_price >= threshold (SHORT SL)
  Impact: LONG SL boundary (unaffected for round numbers), SHORT SL boundary

Path 3: ExitCondition.evaluate() (via schemas.py)
  Formula: entry_price * (1.0 + pct_of_entry) for take_profit
           entry_price * (1.0 - pct_of_entry) for stop_loss
  Comparison: current_price >= threshold (take_profit), current_price <= threshold (stop_loss)
  Impact: Same as Path 1/2 for percentage-based ExitCondition objects

Path 4: ExitCondition with explicit threshold field
  Formula: threshold = explicit float value
  Comparison: uses `operator` field value
  Impact: If threshold is pre-computed as a float literal, the same IEEE-754 issue applies to the stored value. However, this path is less susceptible because the threshold is supplied externally rather than computed.

D.2 UNAFFECTED CODE PATHS
---------------------------

1. Signal-based exits (ExitCondition.type == "signal") — no threshold computation involved
2. LONG stop-loss at round entry prices (0.9 is exact in binary64 for 100, 1000, etc.)
3. SHORT take-profit at round entry prices (same reason)
4. Any exit path where the threshold is not computed via percentage multiplication

D.3 NON-ROUND ENTRIES
-----------------------

For entries like 100.5, 99.99, etc., the boundary issue can affect BOTH TP and SL because the product may not be exactly representable. For example:
  entry=100.5, TP=10% → threshold = 110.55000000000001 (not 110.55 exactly)
  entry=99.99, TP=10% → threshold = 109.98900000000000 (approximately exact but not guaranteed)

==================================================
E. CORE AMBIGUITY
==================================================

The exact unresolved design question is:

"DOES THE LOCKED DESIGN SPECIFY HOW NUMERIC BOUNDARY EQUALITY MUST BE INTERPRETED WHEN IEEE-754 REPRESENTATION DIFFERS FROM THE MATHEMATICAL VALUE FOR TAKE-PROFIT AND STOP-LOSS THRESHOLD COMPARISONS?"

More precisely, the design does NOT specify:

1. Whether take-profit at the mathematical boundary (e.g., close_price == entry * (1 + pct/100)) must trigger, regardless of IEEE-754 representation error.
2. Whether stop-loss at the mathematical boundary must trigger, regardless of IEEE-754 representation error.
3. What numeric representation governs threshold calculation (raw float, rounded, Decimal, etc.).
4. What numeric representation governs price comparison (raw float, canonicalized, etc.).
5. Whether the `operator` field values (`>=`, `<=`, `>`, `<`) are to be interpreted as strict IEEE-754 comparisons or as mathematically-intended comparisons with boundary tolerance.
6. Whether LONG/SHORT semantics must be symmetric in their floating-point boundary behavior.
7. Whether StrategySpec percentage exits and ExitCondition percentage exits must share identical boundary semantics.

The design doc establishes that:
- Floating-point tolerance EXISTS for the equity invariant (line 99)
- Float normalization EXISTS for serialization/hashing (line 637)
- A tolerance constant EXISTS for breakeven counting (line 1453)
- BUT no tolerance, rounding, or canonicalization rule EXISTS for exit threshold comparisons.

This is a genuine gap: the design acknowledges floating-point imprecision in some contexts but is silent in others where it matters most (exit triggers that directly affect trade P&L).

==================================================
F. DESIGN OPTIONS
==================================================

OPTION A — Exact IEEE-754 comparison
--------------------------------------
DEFINITION: Use raw binary64 threshold and direct comparison. Boundary behavior follows IEEE-754 representation exactly. If threshold computes to 110.00000000000001, then 110.0 does NOT trigger take_profit.

ADVANTAGES:
- Fully deterministic across all Python/platform environments (IEEE-754 is standardized)
- Matches current implementation exactly (zero code change)
- Simple to specify: "comparison is `>=` on raw float values"
- Reproducible: same inputs always produce same results
- No hidden behavior or magic numbers

DISADVANTAGES:
- Mathematically unintuitive: a price exactly at the intended 10% threshold does NOT trigger
- Reproducibility across platforms depends on IEEE-754 compliance (generally safe but not guaranteed for all edge cases)
- Financial backtest implications: strategies with exact-boundary take-profits may systematically fail to trigger, producing different results than a mathematical model would predict
- Cross-platform behavior: while IEEE-754 is standardized, some platforms (GPU, embedded) may have different rounding modes
- Creates a silent failure mode: the trade never triggers, and the user may not know why

ARCHITECTURAL CONSEQUENCES:
- No new infrastructure required
- Existing code is already correct under this policy
- Design must explicitly state that boundary equality does NOT trigger exit
- Tests must account for the possibility that mathematically-exact boundaries never trigger
- Strategy designers must avoid exact-boundary thresholds or understand they will not trigger

ASSUMPTIONS:
- Platform IEEE-754 compliance is guaranteed
- Users understand and accept that binary float representation differs from mathematical value
- The design's existing acknowledgment of float imprecision (line 637) covers this context

--------------------------------------------------

OPTION B — Explicit decimal arithmetic
---------------------------------------
DEFINITION: Evaluate take_profit/stop_loss using Decimal or equivalent decimal semantics. e.g., `Decimal('100.0') * (Decimal('1') + Decimal('10')/Decimal('100')) = Decimal('110.0')` exactly.

DO NOT IMPLEMENT THIS. Analysis only.

ADVANTAGES:
- Exact decimal percentage interpretation: 10% of 100.0 = 110.0 exactly
- Mathematically intuitive boundary behavior
- Deterministic across all platforms (Decimal arithmetic is platform-independent)
- Matches human mathematical expectations for percentage calculations
- Eliminates the entire class of boundary failures

DISADVANTAGES:
- Performance overhead: Decimal arithmetic is significantly slower than float (10-100x for complex operations)
- Compatibility with existing float-based schemas: all price data, Candle fields, PositionTracker, and EquityTracker use `float`. Mixing Decimal with float requires explicit conversion at every boundary
- Hashing/serialization implications: `condition_serialization` uses `.10f` formatting of floats. Decimal values would need separate serialization rules
- Migration complexity: every backtest component (features, signals, positions, trades, equity) operates on float. Introducing Decimal would require architectural changes to the entire data flow
- Precision management: Decimal requires explicit precision context management (precision, rounding mode), which introduces new design decisions
- JSON serialization: JSON does not natively support Decimal; would need custom encoders

ARCHITECTURAL CONSEQUENCES:
- Requires converting the entire data flow from float to Decimal
- `Instrument`, `Candle`, `Position`, `Trade`, `EquityPoint` all use `float` — these would need to become `Decimal` or a new `DecimalPrice` type
- `QuantEngine` calculations currently use float — would need Decimal equivalents
- `condition_serialization` would need Decimal-aware formatting
- Performance regression for all backtest operations
- The design's `.10f` serialization convention assumes float; Decimal needs new conventions

ASSUMPTIONS:
- Users expect exact decimal percentage interpretation
- Performance overhead is acceptable for backtesting (not real-time)
- The design can accommodate Decimal without breaking float-based components

--------------------------------------------------

OPTION C — Explicit fixed precision / quantization
---------------------------------------------------
DEFINITION: Define a canonical precision for threshold computation and comparison. e.g., round threshold to N decimal places before comparison, or quantize prices to a canonical grid.

DO NOT select a precision arbitrarily. Analysis only.

ADVANTAGES:
- Exact boundary behavior at the chosen precision level
- Deterministic if precision is fixed
- Can be scoped to exit comparisons only (minimal architectural impact)
- Compatible with existing float-based storage (only comparison changes)
- Simple to specify: "threshold is quantized to N decimal places before comparison"

DISADVANTAGES:
- Precision choice is instrument-dependent: XAU/USD at 2 decimals vs JPY pairs at 3 decimals vs crypto at 8 decimals
- Arbitrary precision selection: if the design specifies N=2, a 3-decimal instrument would still have boundary issues
- Quantization is a form of rounding, which the user explicitly said not to impose arbitrarily
- Price tick sizes vary by instrument and venue; canonical precision may not align with actual market tick sizes
- The design currently has NO instrument metadata for tick size or price precision
- Quantization introduces edge cases: prices near the quantization boundary may behave differently than expected
- Cross-instrument applicability is questionable: a single precision value does not serve all instruments
- The design's `.10f` serialization uses 10 decimal places; should exit threshold precision match?

ARCHITECTURAL CONSEQUENCES:
- Requires defining what the canonical precision is and where it comes from
- Instrument model would need price precision metadata (currently absent)
- Exit comparison code would need to quantize before comparing
- The design's `.10f` serialization and exit threshold quantization must be coordinated
- May create inconsistency: serialized thresholds use `.10f` but comparison uses a different precision

ASSUMPTIONS:
- A single canonical precision applies to all instruments
- Precision can be determined from the design without instrument-specific metadata
- The `.10f` serialization convention provides sufficient precision for comparison purposes

--------------------------------------------------

OPTION D — Explicit tolerance
-----------------------------
DEFINITION: Define a tolerance such that `abs(price - threshold) <= tolerance` is treated as equality. This could be absolute, relative, or scale-dependent.

DO NOT choose a tolerance. Analysis only.

ADVANTAGES:
- Addresses the exact boundary issue directly
- Mathematically well-defined if tolerance is specified
- Can be scoped to exit comparisons only
- Compatible with the design's existing precedent of `within floating-point tolerance` for equity (line 99) and `BREAKEVEN_TOLERANCE = 1e-10` (line 1453)
- The design already acknowledges that floating-point tolerance is sometimes needed

DISADVANTAGES:
- Tolerance magnitude is scale-dependent: 1e-10 is appropriate for prices near 100 but may be too small for prices near 100000 or too large for prices near 0.01
- Absolute tolerance: same value for all price levels; fails for very high or very low prices
- Relative tolerance: `abs(price - threshold) <= rel_tol * max(abs(price), abs(threshold))` introduces complexity and another parameter to define
- Instrument dependence: tolerance appropriate for XAU/USD may not be appropriate for crypto or JPY pairs
- Risk of incorrectly triggering exits: any non-zero tolerance means prices slightly below the threshold could trigger take_profit, which may not be intended
- Reproducibility: tolerance-based comparison may produce different results on different platforms if floating-point evaluation order differs
- The design explicitly says "DO NOT invent a tolerance" — suggesting the user is wary of this approach
- Where is tolerance defined? Module-level constant? Per-instrument? Per-strategy? The design has no precedent for tolerance in exit comparisons

ARCHITECTURAL CONSEQUENCES:
- Requires defining tolerance scope, magnitude, and definition location
- Must coordinate with existing `BREAKEVEN_TOLERANCE` and the equity "within floating-point tolerance" precedent
- Exit comparison code becomes more complex: `close_price >= threshold - tolerance`
- The design must specify whether tolerance is absolute, relative, or instrument-specific
- Test design becomes harder: tolerance creates a "gray zone" around boundaries

ASSUMPTIONS:
- A single tolerance value can serve all price scales
- The design's existing tolerance precedent (equity, breakeven) extends to exit comparisons
- Tolerance does not create unacceptable risk of false triggers

--------------------------------------------------

OPTION E — Mathematical comparison reformulation
--------------------------------------------------
DEFINITION: Reformulate the percentage comparison to avoid constructing the threshold in a way that introduces the multiplication boundary artifact.

Example: Instead of `close_price >= entry * (1 + pct/100)`, compute `close_price / entry - 1 >= pct/100` or `(close_price - entry) / entry * 100 >= pct`.

DO NOT implement this. Analysis only.

ADVANTAGES:
- May avoid the specific `100.0 * 1.1 = 110.00000000000001` artifact
- Keeps the mathematical intent intact
- No new infrastructure required (just a different formula)
- Compatible with existing float-based architecture
- The comparison operates on the ratio directly rather than on a computed threshold

DISADVANTAGES:
- Does NOT genuinely solve the problem: `close_price / entry` also produces float representation errors. For example, `110.0 / 100.0 = 1.1` exactly, but `110.00000000000001 / 100.0 = 1.1000000000000002` which may NOT equal `1.1` in comparison
- The boundary artifact merely moves: instead of threshold computation error, it's now in the division or subtraction
- Different reformulations have different error characteristics depending on which values are exact in IEEE-754
- For `entry=100.5, pct=10`: `110.55 / 100.5 = 1.10004975...` which has its own representation issues
- The design would need to specify which reformulation is canonical
- Changes existing implementation behavior without design authorization
- May break existing backtest results if the reformulation produces different exit triggers

ARCHITECTURAL CONSEQUENCES:
- Changes the formula in `_check_exit_conditions` and `ExitCondition.evaluate`
- Must verify that all existing backtest results remain consistent (or document the difference)
- The design must specify which reformulation is canonical
- Does not eliminate floating-point issues, only moves them
- May interact differently with the `.10f` serialization convention

ASSUMPTIONS:
- Division/subtraction produces fewer representation errors than multiplication
- The reformulated comparison is mathematically equivalent to the original for all practical purposes
- Users do not depend on the exact threshold value for anything other than comparison

--------------------------------------------------

OPTION F — Tick-aware price semantics
--------------------------------------
DEFINITION: Define boundary behavior according to instrument price increments/tick size. A price at the tick-level equivalent of the mathematical boundary should trigger.

DO NOT implement. Analysis only.

ADVANTUES:
- Aligns with actual market microstructure: prices move in discrete ticks
- The most financially realistic approach: if the price would be exactly at the boundary in a tick-based market, the exit should trigger
- Resolves the floating-point issue by working at the tick level rather than the float level
- The design already has an `Instrument` model that could potentially be extended

DISADVANTAGES:
- The current architecture has NO tick size metadata anywhere. `Instrument` has `symbol`, `asset_class`, `base_asset`, `quote_asset`, `contract_type`, `currency` — but NO `tick_size`, `price_precision`, `pip`, or `lot_size`.
- Adding tick size metadata would be an architectural change, not a simple fix
- Different instruments have different tick sizes; the comparison logic would need to be instrument-aware
- The `_check_exit_conditions` method currently operates on `close_price` (a float from a `Candle`) without instrument context
- The design's `Candle` model has no tick size field
- Would require passing instrument context to the backtest engine
- The design doc does not mention tick-aware comparison anywhere
- XAU/USD implications: gold trades at 2 decimals typically, but tick size varies by venue
- Cross-instrument applicability requires tick metadata for every instrument in the dataset

ARCHITECTURAL CONSEQUENCES:
- `Instrument` model needs `tick_size` or `price_precision` field
- `Candle` model may need instrument context or tick size
- `BacktestEngine._check_exit_conditions` needs access to instrument metadata
- Exit comparison logic becomes instrument-dependent
- The `.10f` serialization convention would need coordination with tick precision
- The design would need to specify where tick metadata originates and how it propagates through the data flow
- Dataset loading and validation would need to ensure tick metadata is present

ASSUMPTIONS:
- Tick size metadata can be obtained for all instruments
- The design can accommodate instrument-specific comparison without breaking float-based components
- The current `Candle`/`Instrument` architecture can be extended without redesign

==================================================
G. RECOMMENDED DESIGN AMENDMENT CONTENT
==================================================

DO NOT MODIFY THE DESIGN DOCUMENT. The following normative text is proposed for human approval and subsequent insertion into the design.

G.1 PROPOSED TEXT — THRESHOLD CALCULATION
---------------------------------------------

Add to the section covering StrategySpec exit parameters:

"**Take-Profit and Stop-Loss Threshold Calculation**

Percentage-based take-profit and stop-loss thresholds are computed as follows:

For a LONG position with entry price E, take-profit percentage TP, and stop-loss percentage SL:
  take_profit_threshold = E × (1 + TP / 100)
  stop_loss_threshold    = E × (1 - SL / 100)

For a SHORT position with entry price E, take-profit percentage TP, and stop-loss percentage SL:
  take_profit_threshold = E × (1 - TP / 100)
  stop_loss_threshold    = E × (1 + SL / 100)

These computations use Python's native `float` type (IEEE-754 binary64). The resulting threshold may differ from the mathematically exact value due to floating-point representation. The comparison semantics for these thresholds are defined in the Floating-Point Policy section."

G.2 PROPOSED TEXT — COMPARISON SEMANTICS
-------------------------------------------

Add to the section covering exit evaluation:

"**Exit Comparison Semantics**

Exit conditions are evaluated using the following comparison operators based on position side and exit type:

| Position | Exit Type  | Comparison     |
|----------|-----------|----------------|
| LONG     | Take-Profit| close >= threshold |
| LONG     | Stop-Loss | close <= threshold |
| SHORT    | Take-Profit| close <= threshold |
| SHORT    | Stop-Loss | close >= threshold |

These comparisons use the raw `float` values as produced by the threshold calculation above, without any additional normalization, rounding, or quantization. The comparison semantics are defined by the active Floating-Point Policy."

G.3 PROPOSED TEXT — FLOATING-POINT POLICY
-------------------------------------------

Add a new section to the design, following the EDGE CASES section:

"#### FLOATING-POINT POLICY FOR EXIT EVALUATION

All take-profit and stop-loss threshold calculations and comparisons use Python's native `float` type, which conforms to IEEE-754 binary64 arithmetic.

**Threshold Computation**: Threshold values are computed using `float` multiplication. The result may differ from the mathematically exact value due to IEEE-754 representation error. For example, `100.0 * (1 + 10/100)` evaluates to `110.00000000000001`, not `110.0`.

**Comparison Semantics**: The `>=` and `<=` comparisons are performed using raw IEEE-754 `float` values. No tolerance, rounding, quantization, or Decimal arithmetic is applied. A price exactly equal to the mathematical boundary may or may not trigger an exit depending on the IEEE-754 representation of the computed threshold.

**Boundary Behavior**: At the exact mathematical boundary, the comparison result depends on IEEE-754 representation. The design does NOT guarantee boundary-triggering at the mathematically-intended value. Implementations must document this behavior and test suites must cover both boundary-matching and boundary-missing cases.

**Symmetry**: LONG and SHORT semantics use the same floating-point policy. The same representation artifacts apply to all four exit types (LONG TP, LONG SL, SHORT TP, SHORT SL), though the specific boundary behavior depends on whether the threshold multiplication produces an exact IEEE-754 result.

**Scope**: This policy applies to:
- `StrategySpec.take_profit_pct` and `StrategySpec.stop_loss_pct` (via `_check_exit_conditions`)
- `ExitCondition.pct_of_entry` (via `ExitCondition.evaluate()`)
- Any other percentage-based exit threshold computation

**Exclusions**: This policy does NOT apply to:
- Signal-based exits (no threshold computation)
- The equity invariant `equity == cash + position_market_value` (which uses its own floating-point tolerance as specified elsewhere in this document)
- Breakeven trade counting (which uses `BREAKEVEN_TOLERANCE` as specified elsewhere in this document)
- `condition_serialization` float formatting (which uses `.10f` as specified in Section I)

**Determinism**: All exit evaluation is deterministic across Python platforms that conform to IEEE-754 binary64. Results are reproducible given identical inputs and platform compliance."

G.4 PROPOSED TEXT — CONSISTENCY REQUIREMENTS
----------------------------------------------

Add to the section covering StrategySpec and ExitCondition:

"**StrategySpec vs ExitCondition Consistency**

The `StrategySpec.take_profit_pct` / `stop_loss_pct` percentage exits and `ExitCondition` percentage exits (`pct_of_entry`) MUST follow the same floating-point policy and comparison semantics defined in the FLOATING-POINT POLICY FOR EXIT EVALUATION section. Both paths compute thresholds using `float` multiplication and compare using raw `>=` / `<=` without tolerance.

Note: The `StrategySpec` path divides the percentage by 100 in the threshold formula (`entry * (1 + pct/100)`), while the `ExitCondition` path uses `entry * (1.0 + pct_of_entry)`. Implementations MUST ensure `pct_of_entry` is expressed as a fraction (0.1 for 10%) when using the `ExitCondition` path, and as a percentage (10.0 for 10%) when using the `StrategySpec` path. The design must explicitly define the unit of `pct_of_entry`."

G.5 PROPOSED TEXT — ACCEPTANCE TEST REQUIREMENTS
--------------------------------------------------

Add to the section covering acceptance tests:

"**Take-Profit / Stop-Loss Boundary Tests**

All percentage-based exit paths must be tested with the following boundary matrix:

For each exit type (LONG TP, LONG SL, SHORT TP, SHORT SL):
  - Exactly at the mathematical boundary
  - One IEEE-754 representable value below the boundary
  - One IEEE-754 representable value above the boundary

Additionally, test with:
  - Non-round entry prices (e.g., 100.5, 99.99) where boundary representation differs from mathematical intent
  - Non-integer percentages
  - Values susceptible to binary representation error (where `entry * (1 ± pct/100)` does not produce an exact float)
  - Deterministic repeated execution (same inputs produce same outputs across multiple runs)
  - Both `StrategySpec` percentage exit path and `ExitCondition.pct_of_entry` path

Test suites must document the IEEE-754 behavior at each boundary, including whether the boundary triggers or does not trigger, and must not assume mathematical boundary equality."

==================================================
H. REGRESSION TEST PLAN
==================================================

After design approval, the following tests should be implemented (NOT yet added):

H.1 LONG TAKE PROFIT TESTS
-----------------------------
Test: entry=100.0, take_profit_pct=10.0, close=110.0
Expected: Document IEEE-754 behavior (currently: does NOT trigger because 110.00000000000001 > 110.0)

Test: entry=100.0, take_profit_pct=10.0, close=111.0
Expected: Triggers take_profit (111.0 >= 110.00000000000001)

Test: entry=100.0, take_profit_pct=10.0, close=109.99
Expected: Does NOT trigger take_profit

Test: entry=100.5, take_profit_pct=10.0, close=110.55
Expected: Document IEEE-754 behavior (currently: does NOT trigger)

H.2 LONG STOP LOSS TESTS
--------------------------
Test: entry=100.0, stop_loss_pct=10.0, close=90.0
Expected: Triggers stop_loss (90.0 <= 90.0 exactly)

Test: entry=100.0, stop_loss_pct=10.0, close=91.0
Expected: Does NOT trigger

Test: entry=100.0, stop_loss_pct=10.0, close=89.0
Expected: Triggers stop_loss

H.3 SHORT TAKE PROFIT TESTS
----------------------------
Test: entry=100.0, take_profit_pct=10.0, close=90.0
Expected: Triggers take_profit (90.0 <= 90.0 exactly)

Test: entry=100.0, take_profit_pct=10.0, close=89.0
Expected: Triggers take_profit

Test: entry=100.0, take_profit_pct=10.0, close=91.0
Expected: Does NOT trigger

H.4 SHORT STOP LOSS TESTS
---------------------------
Test: entry=100.0, stop_loss_pct=10.0, close=110.0
Expected: Document IEEE-754 behavior (currently: does NOT trigger)

Test: entry=100.0, stop_loss_pct=10.0, close=111.0
Expected: Triggers stop_loss

Test: entry=100.0, stop_loss_pct=10.0, close=109.0
Expected: Does NOT trigger

H.5 EXITCondition EVALUATE TESTS
---------------------------------
Test: ExitCondition(type='take_profit', pct_of_entry=0.1).evaluate(entry_price=100.0, current_price=110.0)
Expected: Document IEEE-754 behavior

Test: ExitCondition(type='stop_loss', pct_of_entry=0.1).evaluate(entry_price=100.0, current_price=90.0)
Expected: Triggers (90.0 <= 90.0 exactly)

H.6 DETERMINISM TESTS
----------------------
Test: Run identical backtest 100 times with same seed
Expected: Identical results every time (no floating-point non-determinism)

H.7 STRATEGYSPEC vs EXITCONDITION CONSISTENCY
----------------------------------------------
Test: Compare results of StrategySpec take_profit_pct=10.0 path vs ExitCondition(type='take_profit', pct_of_entry=0.1) path for identical entry/close/percentage values
Expected: Identical trigger behavior (both follow the same floating-point policy)

==================================================
I. IMPLEMENTATION IMPACT
==================================================

After design approval, the following files/functions would need modification:

I.1 IF DESIGN SPECIFIES TOLERANCE:
------------------------------------
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — add tolerance to comparison
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — add tolerance to comparison
- Design doc: Add tolerance definition section
- Tests: Update boundary tests to expect tolerance-based triggering

I.2 IF DESIGN SPECIFIES ROUNDING/QUANTIZATION:
-------------------------------------------------
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — quantize threshold before comparison
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — quantize threshold before comparison
- Design doc: Add quantization precision specification
- Tests: Update boundary tests to expect quantized triggering

I.3 IF DESIGN SPECIFIES EXACT IEEE-754 (NO CHANGE):
------------------------------------------------------
- No source changes needed
- Only tests would need updating to document and assert the existing IEEE-754 behavior
- Design doc must be amended to explicitly state this policy

I.4 IF DESIGN SPECIFIES DECIMAL ARITHMETIC:
---------------------------------------------
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — convert to Decimal
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — convert to Decimal
- Potentially: entire data flow from `Instrument` through `Candle` to `Position` to `Trade` to `EquityPoint`
- Design doc: Major architectural amendment
- Tests: Comprehensive rewrite

I.5 IF DESIGN SPECIFIES TICK-AWARE COMPARISON:
-------------------------------------------------
- `src/data_engine/schemas.py`: `Instrument` model — add tick_size field
- `src/data_engine/strategy/backtest.py`: `_check_exit_conditions()` — use tick_size for comparison
- `src/data_engine/strategy/schemas.py`: `ExitCondition.evaluate()` — use tick_size for comparison
- Design doc: Major architectural amendment
- Tests: Comprehensive rewrite with tick-size metadata

==================================================
J. VALIDATION
==================================================

* No source modifications: CONFIRMED (git diff --stat is empty)
* No test modifications: CONFIRMED (no test files changed)
* No design modifications: CONFIRMED (git diff docs/strategy_engine_design.md is empty)
* Design SHA unchanged: CONFIRMED (88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d)
* Phase 3 status: NO-GO (Blocker #2 remains BLOCKED — DESIGN AMBIGUITY)

==================================================
K. BLOCKER #2 STATUS
==================================================

BLOCKED — DESIGN AMBIGUITY

The locked design does not specify how floating-point boundary comparisons must behave for take-profit and stop-loss thresholds. The design acknowledges floating-point imprecision for equity invariants and serialization but is silent on exit threshold comparison semantics. This design clarification proposal provides the analysis and proposed normative text needed for explicit human approval before any implementation fix can be attempted.

==================================================
END OF DESIGN REVIEW REPORT
==================================================
