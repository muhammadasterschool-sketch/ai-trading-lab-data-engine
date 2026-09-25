# PHASE 3 — BLOCKER #2
# FINAL HUMAN DECISION MATRIX

## Status

BLOCKED — AWAITING EXPLICIT HUMAN DESIGN APPROVAL

Phase 3 remains NO-GO. Blocker #1 (same-bar re-entry) is RESOLVED. Blocker #2 remains BLOCKED by design ambiguity. No implementation may proceed until all seven decisions below are explicitly approved by a human reviewer.

## Locked Design Integrity

Design SHA: 88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d

Verified unchanged at time of this report. `git diff --stat` is empty for all tracked files. No source, test, or design modifications have been made.

---

## D1 — Canonical Percentage Unit

* Current implementation:
  - `StrategySpec.stop_loss_pct` and `StrategySpec.take_profit_pct` use **percentage points**: `10.0 = 10%`. Formula divides by 100: `threshold = entry * (1 + take_profit_pct / 100)`.
  - `ExitCondition.pct_of_entry` uses **fractional ratio**: `0.1 = 10%`. Formula does NOT divide by 100: `threshold = entry * (1.0 + pct_of_entry)`.
  - Same mathematical percentage (10%) is expressed as `10.0` in one path and `0.1` in the other.

* Locked-design status:
  - The design doc lists `stop_loss_pct` and `take_profit_pct` as fields on `StrategySpec` (line 681) and `pct_of_entry` on `ExitCondition` (line 45).
  - The design doc does NOT define the unit of either field.
  - The design doc does NOT state whether these two paths must use the same unit.

* Human decision required:
  - Must the canonical percentage unit be **percentage points** (10.0 = 10%) or **fractional ratio** (0.10 = 10%)?
  - This single decision affects every field, formula, test fixture, validation rule, serialization format, hash computation, and regression vector in the entire system.

* Affected components:
  - `StrategySpec.stop_loss_pct`
  - `StrategySpec.take_profit_pct`
  - `ExitCondition.pct_of_entry`
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - `StrategyValidator` and `ConditionValidator`
  - `condition_serialization` and `config_hash` computation
  - All test fixtures using percentage exit parameters
  - All regression test vectors

---

## D2 — Normative TP/SL Formula

* Current implementation:
  - LONG TP: `threshold = entry_fill_price * (1 + take_profit_pct / 100)`
  - LONG SL: `threshold = entry_fill_price * (1 - stop_loss_pct / 100)`
  - SHORT TP: `threshold = entry_fill_price * (1 - take_profit_pct / 100)`
  - SHORT SL: `threshold = entry_fill_price * (1 + stop_loss_pct / 100)`
  - The formula is implemented in `_check_exit_conditions()` only. It is NOT stated in the locked design doc.
  - `ExitCondition.evaluate()` mirrors this with `pct_of_entry` as fraction instead of percentage.

* Locked-design status:
  - The design doc does NOT specify the threshold computation formula for any exit type.
  - The design doc does NOT specify the directional mapping (which operator applies to which exit type and position side).
  - The design doc defines `operator` values (`>`, `<`, `>=`, `<=`) in the condition serialization format but never assigns them to specific exit types.

* Human decision required:
  - The design must explicitly specify, for each of LONG TP, LONG SL, SHORT TP, SHORT SL:
    - The entry price used (entry_fill_price, entry_price, or another)
    - The percentage-to-rate conversion (division by 100 or not)
    - The threshold calculation formula
    - The directional comparison operator (`>=` or `<=`)
    - The mathematical meaning of the percentage (percentage of entry price, or another interpretation)
  - Must LONG and SHORT formulas be symmetric? (See D3.)

* Affected components:
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - `StrategySpec` schema
  - `ExitCondition` schema
  - All exit-related test fixtures
  - `condition_serialization` (if threshold_value serialization must reflect the formula)
  - `config_hash` computation

---

## D3 — Boundary Inclusion

* Current implementation:
  - LONG TP: `close_price >= threshold` (inclusive at boundary)
  - LONG SL: `close_price <= threshold` (inclusive at boundary)
  - SHORT TP: `close_price <= threshold` (inclusive at boundary)
  - SHORT SL: `close_price >= threshold` (inclusive at boundary)
  - However, due to IEEE-754 representation, `100.0 * 1.1 = 110.00000000000001`, so `close_price=110.0 >= 110.00000000000001` evaluates `False` — the inclusive comparison fails at the exact boundary in practice.

* Locked-design status:
  - The design doc does NOT specify whether boundary equality must trigger exit conditions.
  - The design doc does NOT address floating-point boundary behavior for any exit type.
  - The design doc's EDGE CASES section covers execution timing only, not boundary equality.

* Human decision required:
  - For each exit type, must the boundary be inclusive?
    - LONG TP: `close_price >= threshold` or `close_price > threshold`?
    - LONG SL: `close_price <= threshold` or `close_price < threshold`?
    - SHORT TP: `close_price <= threshold` or `close_price < threshold`?
    - SHORT SL: `close_price >= threshold` or `close_price > threshold`?
  - Must LONG/SHORT symmetry be **mandatory**? That is, if LONG TP uses `>=`, must SHORT SL also use `>=`?
  - If boundary inclusion is required, what mechanism ensures it despite IEEE-754 representation? (See D4.)

* Affected components:
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - All exit condition test fixtures
  - `condition_serialization` (operator field values)
  - Regression test boundary vectors
  - `ResultHash` computation (exit triggers affect trade count and P&L)

---

## D4 — Floating-Point Policy

* Current implementation:
  - All arithmetic uses Python's native `float` (IEEE-754 binary64).
  - All comparisons use raw `>=` and `<=` operators on `float` values.
  - No tolerance, rounding, quantization, Decimal, or tick-aware comparison exists anywhere in the codebase.
  - The design acknowledges floating-point imprecision for equity invariants (line 99) and serialization (line 637), but NEVER for exit threshold comparisons.

* Locked-design status:
  - The design doc does NOT specify a floating-point policy for exit evaluation.
  - `BREAKEVEN_TOLERANCE = 1e-10` exists but is scoped to breakeven counting only.
  - `equity == cash + position_market_value (within floating-point tolerance)` exists but is scoped to the equity equation only.
  - No policy exists that governs take_profit/stop_loss threshold comparisons.

* Human decision required:
  - The design must choose **exactly one** normative numerical policy from the following categories (or define a new one):
    - **A. Direct IEEE-754 comparison**: Raw `>=`/`<=` on `float` values. Boundary behavior follows IEEE-754 representation exactly. No changes to current behavior.
    - **B. Mathematically equivalent reformulation**: Restructure the comparison to avoid the specific multiplication boundary artifact (e.g., `(close_price - entry) / entry * 100 >= pct`). Does not eliminate floating-point error; moves it.
    - **C. Fixed decimal precision**: Quantize threshold or price to N decimal places before comparison. Precision value and scope must be specified.
    - **D. Decimal arithmetic**: Use `decimal.Decimal` for all exit threshold calculations and comparisons. Requires architectural changes.
    - **E. Explicit tolerance**: Define a tolerance value and scope (absolute, relative, or instrument-specific). Tolerance definition and location must be specified.
    - **F. Instrument tick/price precision**: Define boundary behavior according to instrument tick size. Requires tick metadata (see D5).
    - **G. Another explicitly specified deterministic mechanism**: Any other formally defined rule.
  - Must the same policy apply to both `StrategySpec` and `ExitCondition` paths?

* Affected components:
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - `src/data_engine/strategy/backtest.py`
  - `src/data_engine/strategy/schemas.py`
  - All percentage exit test vectors
  - `condition_serialization`
  - `config_hash` and `ResultHash`
  - Potentially entire data flow if Decimal or tick-aware policy is chosen

---

## D5 — Tick / Price Precision

* Current architecture:
  - `Instrument` model fields: `symbol`, `asset_class`, `base_asset`, `quote_asset`, `contract_type`, `currency`, `exchange`, `venue`, `provider_symbol`. **NO tick_size, price_precision, decimal_places, or minimum price increment.**
  - `Candle` model fields: `timestamp`, `open`, `high`, `low`, `close`, `volume`, `timeframe`, `bid`, `ask`, `spread`, `currency`, `provider_timestamp`. **NO tick or precision metadata.**
  - No shared comparison utility exists in the codebase.
  - No decimal representation infrastructure exists.
  - The design doc does NOT mention tick size, price precision, or decimal places anywhere.

* Locked-design status:
  - The design doc does NOT require tick-size or price-precision metadata for exit evaluation.
  - No section of the design defines where instrument metadata originates or how it propagates through the data flow for exit comparisons.

* Human decision required:
  - **Is tick-size / price-precision metadata REQUIRED for Blocker #2 immediately?**
    - If the design chooses a tick-aware policy (D4-F), then yes, it is required.
    - If the design chooses IEEE-754, tolerance, or Decimal, then NO — it is not required for Blocker #2.
  - **Is tick-size / price-precision metadata potentially useful future infrastructure?**
    - Yes, for instrument-specific exit behavior, but this is a separate architectural decision.
  - If required, where does tick metadata originate? Instrument definition? Dataset metadata? Provider configuration?

* Affected components (IF REQUIRED):
  - `Instrument` model (`src/data_engine/schemas.py`)
  - `Candle` model (`src/data_engine/schemas.py`)
  - `BacktestEngine._check_exit_conditions()` — needs instrument context
  - `ExitCondition.evaluate()` — needs instrument context
  - Dataset loading and validation
  - `Instrument` serialization/hashing
  - **IF NOT REQUIRED**: No impact on Blocker #2 implementation.

---

## D6 — Cross-Path Consistency

* Current implementation:
  - `StrategySpec.take_profit_pct`/`stop_loss_pct`: percentage points (10.0 = 10%), formula divides by 100.
  - `ExitCondition.pct_of_entry`: fractional ratio (0.1 = 10%), formula does NOT divide by 100.
  - These are two independent implementations of the same concept with incompatible units.
  - Both are computed in the same backtest session (`_check_exit_conditions` iterates `strategy.exit_conditions` in addition to checking `strategy.take_profit_pct`/`stop_loss_pct` directly), but they are independent paths that could produce different thresholds for the same percentage specification.

* Locked-design status:
  - The design doc does NOT state whether these two paths must use the same units or formulas.
  - The design doc lists both as fields in `config_hash` ordering (line 680-690) but does not define their relationship.
  - The design doc's condition serialization section (line 736-760) defines how `ExitCondition` objects are serialized, but does not reconcile with `StrategySpec` percentage fields.

* Human decision required:
  - Are `StrategySpec.take_profit_pct`/`stop_loss_pct` and `ExitCondition.pct_of_entry` **one canonical semantic concept** that must use the same unit and formula?
  - OR are they **two independent representations** that may differ in units and formula, provided both follow the same floating-point policy?
  - If one canonical concept: which unit governs? What conversion rules exist? How are validation and serialization affected?

* Affected components:
  - `StrategySpec` schema
  - `ExitCondition` schema
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - `StrategyValidator`
  - `ConditionValidator`
  - `validation.py`
  - All test fixtures
  - `config_hash` and `condition_serialization`
  - `ResultHash`

---

## D7 — Determinism

* Current implementation:
  - All calculations use Python `float` (IEEE-754 binary64).
  - Results are deterministic within a single Python process on a single platform for identical inputs.
  - No explicit determinism requirement exists in the design doc for exit evaluation.
  - The design doc's `condition_serialization` section (line 637) acknowledges IEEE-754 representation for hashing, implying some determinism expectation.

* Locked-design status:
  - The design doc does NOT explicitly state determinism requirements for exit evaluation.
  - The design doc defines `BREAKEVEN_TOLERANCE` for breakeven counting but does not extend determinism requirements to exit comparisons.
  - The `ResultHash` and `config_hash` systems imply that deterministic results are expected, but the exact scope is not defined.

* Human decision required:
  - What exact determinism scope must apply to exit evaluation?
    - Identical results across repeated runs with same seed?
    - Identical results across Python versions in the supported range?
    - Identical results across operating systems?
    - Identical results across CPU architectures?
    - All of the above?
  - Must the same determinism apply to both `StrategySpec` and `ExitCondition` paths?
  - Is deterministic cross-platform behavior a hard requirement, or is single-platform determinism sufficient?

* Affected components:
  - `BacktestEngine._check_exit_conditions()`
  - `ExitCondition.evaluate()`
  - `ResultHash` computation
  - `config_hash` computation
  - `condition_serialization`
  - All regression test vectors
  - Cross-platform test infrastructure (if determinism scope requires it)

---

## Explicit Non-Decisions

* No source code was modified.
* No tests were modified.
* The locked design was not modified.
* No tolerance was introduced.
* No rounding was introduced.
* No Decimal conversion was introduced.
* No tick-size logic was introduced.
* No design option was selected by this agent.
* No comparison operators were modified.
* No existing behavior was changed.
* All seven decisions (D1–D7) remain undecided and require explicit human approval.

---

## Final Status

BLOCKED — AWAITING EXPLICIT HUMAN DESIGN APPROVAL

All seven decisions (D1–D7) in this matrix must be explicitly approved by a human reviewer before any implementation work on Blocker #2 can begin. The proposed normative text in `PHASE3_BLOCKER2_DESIGN_APPROVAL.md` provides multiple alternative formulations for each decision point and must not be inserted into the locked design document without explicit human approval.

Phase 3 remains NO-GO. Blocker #1 (same-bar re-entry) is RESOLVED. Blocker #2 (take-profit/stop-loss floating-point boundary semantics) is BLOCKED by design ambiguity.

---
END OF FINAL DECISION MATRIX
---
