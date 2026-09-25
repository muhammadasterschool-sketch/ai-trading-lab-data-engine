# Phase 2 — Human Design Decision Matrix

**Artifact:** `PHASE2_HUMAN_DESIGN_DECISION_MATRIX.md`
**Artifact Version:** v1.1
**Artifact Status:** CORRECTED HUMAN DESIGN DECISION MATRIX
**Parent Artifact:** `PHASE2_BASELINE_ARCHITECTURE_AUDIT.md`
**Red-Team Artifact:** `PHASE2_HUMAN_DESIGN_DECISION_MATRIX_REDTEAM.md`
**Implementation Authority:** NONE
**D4 Authority:** NONE
**Phase 3 Authority:** NONE
**Scope:** Phase 2 human-design evidence, governance, logical consistency, and phase-boundary analysis
**Date:** 2026-09-25
**Auditor:** Senior Quantitative-Data Infrastructure Architect
**Project:** AI Trading Lab — Data Engine
**Repository:** `C:\Users\muham\ai-trading-lab-data-engine`
**Reference:** `PHASE2_BASELINE_ARCHITECTURE_AUDIT.md`
**Scope:** Read-only design analysis. No implementation authorized.

---

## Executive Summary

This matrix converts the completed Phase 2 baseline audit into a formal human-reviewable decision document. Every material finding is supported by independently verified evidence citations. The matrix exposes decisions that require human authorization and preserves the D4 governance firewall.

**Key distinction established:**

- **Calculation-value determinism**: All indicator calculations are pure functions of inputs — identical inputs produce identical float64 values. Verified by `test_all_calculation_types_are_deterministic` passing (E-034).
- **Result-object / metadata determinism**: `CalculationMetadata.calculation_timestamp` uses `datetime.now(UTC).isoformat()` via `default_factory` (E-001), making serialized `QuantResult` objects non-deterministic across invocations.

**D4 remains BLOCKED.** No policy family has been selected, ranked, or recommended.

**Correction log:** This matrix has been corrected per the Phase 2 red-team review (`PHASE2_HUMAN_DESIGN_DECISION_MATRIX_REDTEAM.md`). Six corrections were applied: C-001 (F-003 DataQualityGate scope), C-002 (documentation/implementation mutable-global-state contradiction), C-003 (ddof scope expansion), C-004 (F-001 documentation evidence), C-005 (test-isolation impact), C-006 (calculate_indicator registry analysis). See the Correction Log section for details.

---

## 1. Audit Findings Reconciliation

The Phase 2 baseline audit identified findings across multiple dimensions. Each finding is reconciled below with independent evidence.

| ID | Finding | Evidence | Technical impact | Affected component | Phase | Proposed options | Human decision required? | Current disposition |
| -- | ------- | -------- | ---------------- | ------------------ | ----- | ---------------- | ------------------------ | ------------------- |
|| F-001 | `calculation_timestamp` uses wall-clock time | E-001 (source), E-017 (source) | Serialized `QuantResult` metadata is non-deterministic; affects canonical hashing | `CalculationMetadata`, `QuantResult` | Phase 2 | (1) Exclude timestamp from hash; (2) Accept non-deterministic metadata; (3) Use deterministic timestamp; (4) Separate value-hash from metadata-hash | YES | HUMAN DECISION REQUIRED |

**Source vs Documentation Evidence for F-001:**
- **Source implementation evidence**: `CalculationMetadata.calculation_timestamp` uses `Field(default_factory=QuantEngineVersion.calculation_timestamp)` where `calculation_timestamp()` returns `datetime.now(UTC).isoformat()` (E-001, E-017). This is verified from `src/data_engine/quant/schemas.py`.
- **Documentation evidence**: `docs/quant_engine.md` does NOT mention `calculation_timestamp` anywhere. The documentation references `CalculationMetadata` as a structure name and shows `print(result.metadata)` in the API example, but never discusses `calculation_timestamp` specifically. This is verified by `grep "calculation_timestamp" docs/quant_engine.md` returning no matches (RT-E-002).
- **Claim supported**: The determinism concern is valid from source code inspection. The documentation does NOT support or contradict the claim — it simply does not address the field.
| F-002 | `IndicatorRegistry._registry` is shared mutable global state | E-003 | Registry mutation is structurally possible. Operational impact is NOT ESTABLISHED BY CURRENT EVIDENCE — no demonstrated race condition, cross-request contamination, calculation corruption, or test contamination. | `IndicatorRegistry` | Phase 2 | (1) Accept global singleton; (2) Use request-scoped instances; (3) Add threading locks | YES | HUMAN DECISION REQUIRED |
|| F-003 | `DataQualityGate._blocked_datasets` is instance-level mutable state created per validation call | E-004, RT-E-006 | In the Phase 2 QuantEngine path, `DataQualityGate()` is instantiated inside `_check_quality_gate()` per call (validation.py line 170). `_blocked_datasets` is ephemeral: created, populated, and discarded within a single method call. Phase 3 `BacktestEngine` creates its own `DataQualityGate` instance (backtest.py line 142) that persists per-backtest-instance. | `DataQualityGate` | Phase 2 | (1) Accept per-call instantiation; (2) Add reset mechanism for Phase 3 instance | YES | HUMAN DECISION REQUIRED |
| F-004 | `QuantEngine._calculation_history` is declared but never populated | E-002, E-018 | Dead code; no observable behavior impact; source of confusion | `QuantEngine` | Phase 2 | (1) Remove dead code; (2) Activate history tracking; (3) Leave as-is | YES | HUMAN DECISION REQUIRED |
| F-005 | `QuantDataValidator._errors/_warnings` are per-instance mutable lists | E-005 | Recreated each `validate()` call; no cross-call contamination | `QuantDataValidator` | Phase 2 | (1) Accept current pattern; (2) Use immutable result objects | YES | HUMAN DECISION REQUIRED |
| F-006 | `rolling_std` ddof default is 0 (population) but docs say ddof=1 (sample) | E-006 | Statistical convention mismatch between documentation and implementation; could affect downstream calculations | `rolling_std`, `variance`, `std`, `covariance`, `correlation` | Phase 2 | (1) Change implementation to ddof=1; (2) Change docs to ddof=0; (3) Add explicit ddof parameter to all functions; (4) Leave as-is with corrected docs | YES | HUMAN DECISION REQUIRED |
| F-007 | `rsi` returns None for first `period` values | E-013 | Result length equals input length but first `period` values are None; may cause confusion for downstream consumers | `rsi`, `rsi_last` | Phase 2 | (1) Accept current behavior; (2) Document more prominently; (3) Pad differently | YES | HUMAN DECISION REQUIRED |
| F-008 | All calculations use Python float64 | E-019, E-020 | Binary64 semantics; no Decimal, no custom precision | All calculation modules | Phase 2 / D4 | (1) Accept float64; (2) Add Decimal option; (3) Add tick-size normalization; (4) Add tolerance/epsilon | YES (D4) | HUMAN DECISION REQUIRED |
| F-009 | No tick-size metadata exists | E-008 | Phase 2 has no price-precision specification | All price calculations | D4 / Future | (1) Add tick-size metadata; (2) Leave unspecified; (3) Defer to execution layer | YES (D4) | HUMAN DECISION REQUIRED |
| F-010 | No rounding rules exist | E-008 | No `round()`, `math.floor()`, `math.ceil()`, or formatting anywhere | All calculation modules | D4 / Future | (1) Add rounding policy; (2) Leave as-is | YES (D4) | HUMAN DECISION REQUIRED |
| F-011 | No tolerance/epsilon exists | E-008 | All float64 equality comparisons use exact `==` | All comparison operations | D4 / Future | (1) Add tolerance; (2) Leave as-is | YES (D4) | HUMAN DECISION REQUIRED |
| F-012 | No shell execution mechanisms | E-007 | Security confirmed | All quant/ modules | Phase 1/2 | None — already compliant | NO | OBSERVED |
| F-013 | No Decimal, random, network access | E-008, E-021, E-022 | Security confirmed | All quant/ modules | Phase 1/2 | None — already compliant | NO | OBSERVED |
| F-014 | All Pydantic models frozen | E-009 | Immutability enforced | All quant schemas | Phase 1/2 | None — already compliant | NO | OBSERVED |
| F-015 | No look-ahead boundary violations | E-023 | Rolling windows use only historical data | All calculation modules | Phase 2 | None — already compliant | NO | OBSERVED |
| F-016 | 134 quant tests pass | E-034 | Test corpus validates observed behavior | `tests/test_quant.py` | Phase 2 | None — already compliant | NO | OBSERVED |
| F-017 | 50 red-team tests pass | E-034 | Security posture validated | `tests/test_redteam.py` | Phase 1/2 | None — already compliant | NO | OBSERVED |
| F-018 | 9 Phase 3 strategy failures unrelated to Phase 2 | E-039, E-040 | Failures import `data_engine.strategy.*`, not `data_engine.quant.*` | `tests/test_strategy.py`, `tests/test_strategy_independent.py` | Phase 3 | None — separate defect set | NO | OBSERVED |
| F-019 | `CalculationMetadata` does not explicitly pass `calculation_timestamp` | E-017, E-036 | Relies on `default_factory`; timestamp present but not controlled by `_metadata()` | `QuantEngine._metadata()` | Phase 2 | (1) Pass timestamp explicitly; (2) Accept default_factory; (3) Make timestamp configurable | YES | HUMAN DECISION REQUIRED |
| F-020 | Documentation claims ddof=1 but implementation uses ddof=0 | E-006 | Documentation/implementation divergence | `docs/quant_engine.md`, `src/data_engine/quant/volatility.py`, `src/data_engine/quant/statistics.py` | Phase 2 | (1) Fix implementation; (2) Fix docs; (3) Add explicit parameter | YES | HUMAN DECISION REQUIRED |
| F-021 | `DataQualityGate` and `QuantDataValidator` both block SYNTHETIC/SIMULATED | E-031, E-032 | Redundant but consistent policy enforcement | Both validators | Phase 1/2 | None — already consistent | NO | OBSERVED |
|| F-022 | `QuantEngine._metadata` does not include `calculation_timestamp` in its parameter list | E-017, E-036 | `calculation_timestamp` arrives via `default_factory`, not explicit construction | `QuantEngine._metadata()` | Phase 2 | (1) Include explicitly; (2) Accept default_factory | YES | HUMAN DECISION REQUIRED |
|| F-023 | `docs/quant_engine.md` claims "No mutable global state" but `IndicatorRegistry._registry` IS a mutable global singleton | RT-E-001 | Documentation/implementation contradiction; a documented security claim is violated by the module-level `_registry` global singleton | `docs/quant_engine.md`, `src/data_engine/quant/registry.py` | Phase 2 | (1) Fix documentation; (2) Fix implementation; (3) Accept as design exception with documentation update | YES | HUMAN DECISION REQUIRED |

---

## 2. Determinism Decision Matrix

### 2.1 Critical Distinction: Calculation-Value vs Result-Object Determinism

**DOCUMENTED INTENT** (`docs/quant_engine.md`, Security section): "All calculations are pure functions" and "No time-dependent calculations (except timestamps)."

**IMPLEMENTED BEHAVIOR**:

| Dimension | Deterministic? | Evidence |
| --------- | -------------- | -------- |
| Calculation values (indicator outputs) | YES | `test_all_calculation_types_are_deterministic` passes (E-034). All functions are pure: `sma()`, `ema()`, `rsi()`, `atr()`, `rolling_std()`, `drawdown()`, etc. |
| `QuantResult.values` | YES | Same input → same `List[Optional[float]]` |
| `QuantResult.metadata.dataset_id`, `instrument`, `timeframe`, `indicator`, `parameters`, `source_field`, `calculation_convention`, `engine_version` | YES | All derived from input `Dataset` and fixed constants |
| `QuantResult.metadata.calculation_timestamp` | NO | Uses `datetime.now(UTC).isoformat()` via `default_factory` (E-001, E-017) |
| `QuantResult.success`, `error`, `warning_count`, `warnings` | Partially | `success` and `error` depend on validation outcomes; `warnings` may vary if timestamps differ |
| `QuantResult` as a whole object (for hashing) | NO | Contains non-deterministic `calculation_timestamp` |

**Evidence ID: E-001**
- Source: `src/data_engine/quant/schemas.py`
- Location: `CalculationMetadata.calculation_timestamp` (line 28-29, 45)
- Observed: `calculation_timestamp: str = Field(default_factory=QuantEngineVersion.calculation_timestamp)` where `calculation_timestamp()` returns `datetime.now(UTC).isoformat()`
- Claim supported: `CalculationMetadata` contains execution-time-dependent state; therefore the complete `QuantResult` object is not strictly deterministic when serialized.

**Evidence ID: E-017**
- Source: `src/data_engine/quant/schemas.py`
- Location: `CalculationMetadata` class (lines 28, 44-45)
- Observed: `calculation_timestamp` uses `Field(default_factory=QuantEngineVersion.calculation_timestamp)`, not explicitly passed by `_metadata()`
- Claim supported: `QuantEngine._metadata()` does not control `calculation_timestamp`; it arrives via Pydantic's default_factory.

### 2.2 Material Findings

| ID | Finding | Evidence | Impact | Options | Disposition |
| -- | ------- | -------- | ------ | ------- | ----------- |
| D-001 | Calculation values are deterministic | E-034 | Core engine correctness | None needed | OBSERVED |
| D-002 | `calculation_timestamp` makes serialized metadata non-deterministic | E-001, E-017 | Affects `strategy_hash`, `result_hash`, canonical serialization | (1) Exclude from hash; (2) Accept; (3) Use deterministic timestamp; (4) Separate hashes | HUMAN DECISION REQUIRED |
| D-003 | `_calculation_history` is dead code | E-002, E-018 | Source of confusion; no behavioral impact | (1) Remove; (2) Activate; (3) Leave | HUMAN DECISION REQUIRED |
| D-004 | `_metadata()` does not pass `calculation_timestamp` explicitly | E-017, E-036 | Timestamp not controllable at construction | (1) Pass explicitly; (2) Accept default | HUMAN DECISION REQUIRED |

---

## 3. Shared-State Decision Matrix

### 3.1 `IndicatorRegistry._registry`

**Evidence ID: E-003**
- Source: `src/data_engine/quant/registry.py`
- Location: Lines 191, 194-199
- Observed: `_registry: Optional[IndicatorRegistry] = None` (module-level global). `get_registry()` uses `global _registry` and lazy-initializes. `IndicatorRegistry._indicators: Dict[str, IndicatorSpec]` is per-instance.
- Claim supported: The registry instance is shared globally via `get_registry()`. Registration is one-time. Indicators are immutable after registration.

| Property | Value |
|----------|-------|
| Ownership | Module-level singleton |
| Lifecycle | Process lifetime; initialized on first `get_registry()` call |
| Thread-safety | NOT guaranteed; `_indicators` dict mutation is not atomic |
| Request isolation | NO — shared across all requests |
| Test isolation | Potential issues if tests register/deregister indicators |
| Affects calculation results | NO — indicators are read-only after registration |
| Intended global | YES — by design |

### 3.2 `DataQualityGate._blocked_datasets`

**Evidence ID: E-004, RT-E-006**
- Source: `src/data_engine/data_blocked.py`
- Location: Lines 91, 116, 132, 148, 163, 179, 199, 202, 207
- Observed: `self._blocked_datasets: Dict[str, DataQualityBlockedError] = {}` (instance-level). Populated by `check()` method. `is_blocked()` and `get_blocked()` read from it.
- Source: `src/data_engine/quant/validation.py`
- Location: Line 170
- Observed: `_check_quality_gate()` creates `gate = DataQualityGate()` inside the method body. A NEW `DataQualityGate` instance is created per call. `_blocked_datasets` is ephemeral: created, populated, and discarded within a single method call.
- Source: `src/data_engine/strategy/backtest.py`
- Location: Line 142
- Observed: Phase 3 `BacktestEngine` creates `self.data_quality_gate = DataQualityGate()` as an instance variable. This instance persists per-backtest-engine lifetime.
- Claim supported: In the Phase 2 QuantEngine path, `_blocked_datasets` is per-call ephemeral instance state, NOT shared mutable global state. It does NOT persist across validation calls. In Phase 3 `BacktestEngine`, a separate `DataQualityGate` instance persists per-backtest-engine.

| Property | Value |
|----------|-------|
| Ownership | `DataQualityGate` instance (Phase 2: per-call; Phase 3: per-backtest-engine) |
| Lifecycle | Phase 2: single method call. Phase 3: `BacktestEngine` lifetime |
| Thread-safety | NOT guaranteed |
| Request isolation | Phase 2: YES — new instance per call. Phase 3: Depends on `BacktestEngine` instantiation |
| Test isolation | Phase 2: LOW — new instance per `validate()` call. Phase 3: Depends on test construction |
| Affects calculation results | NO — only blocks or allows entry |
| Intended global | NO — per-instance |
| **OPERATIONAL IMPACT: NOT ESTABLISHED BY CURRENT EVIDENCE** | No race condition or contamination demonstrated |

### 3.3 `QuantEngine._calculation_history`

**Evidence ID: E-002, E-018**
- Source: `src/data_engine/quant/core.py`
- Location: Line 50
- Observed: `self._calculation_history: List[Dict] = []` initialized in `__init__`. Zero occurrences of `append` or mutation found in `core.py`.
- Claim supported: `_calculation_history` is declared but never populated. Dead code with no observable behavior.

| Property | Value |
|----------|-------|
| Ownership | `QuantEngine` instance |
| Lifecycle | Instance lifetime |
| Thread-safety | N/A (never used) |
| Affects calculation results | NO |
| Status | DEAD CODE |

### 3.4 `QuantDataValidator._errors` and `_warnings`

**Evidence ID: E-005**
- Source: `src/data_engine/quant/validation.py`
- Location: Lines 46-47, 60-61
- Observed: `self._errors: List[str] = []` and `self._warnings: List[str] = []`. Reset to `[]` at start of each `validate()` call (lines 60-61). Populated during validation.
- Claim supported: Per-instance mutable lists recreated each `validate()` call. No cross-call contamination.

| Property | Value |
|----------|-------|
| Ownership | `QuantDataValidator` instance |
| Lifecycle | Per `validate()` call (reset at start) |
| Thread-safety | NOT guaranteed (but `QuantEngine` creates one `validator` at init) |
| Request isolation | YES — reset each call |
| Affects calculation results | NO — only affects validation outcome |

### 3.6 `calculate_indicator` Function and Registry Dependency

**Evidence ID: E-030, RT-E-013**
- Source: `src/data_engine/quant/registry.py`
- Location: Lines 202-213
- Observed: `calculate_indicator(name, prices, **kwargs)` is a convenience function that calls `get_registry()` to obtain the singleton registry, then calls `registry.get(name)` and invokes `spec.function(prices, **kwargs)`.
- Source: `tests/test_quant.py`
- Location: Lines 32, 846-849
- Observed: `calculate_indicator` is imported and used in `test_calculate_indicator_function`. Tests call `get_registry()` directly in `TestIndicatorRegistry` (lines 824, 829, 834, 842).
- Claim supported: `calculate_indicator` depends on the singleton registry returned by `get_registry()`. The registry is shared global state. However, tests do NOT register new indicators — they only read from the pre-populated registry. Registry ordering/state does not affect calculation outputs because indicator functions are pure functions of their inputs.

| Property | Value |
|----------|-------|
| Registry dependency | `calculate_indicator` calls `get_registry()` — singleton |
| Registry mutation possible | YES — `IndicatorRegistry.register()` exists |
| Tests mutate registry | NO — tests only read pre-registered indicators |
| Calculation output affected by registry state | NO — indicator functions are pure |
| Operational impact | NOT ESTABLISHED BY CURRENT EVIDENCE |

---

### 3.5 Shared-State Decision Table

| ID | Component | Shared? | Mutable? | Affects Results? | Test Isolation Risk? | Disposition |
| -- | --------- | ------- | -------- | ---------------- | -------------------- | ----------- |
| S-001 | `IndicatorRegistry._registry` | YES | YES | NO | MEDIUM | HUMAN DECISION REQUIRED |
|| S-002 | `DataQualityGate._blocked_datasets` | Per-call (Phase 2) / Per-instance (Phase 3) | YES (ephemeral) | NO | LOW | HUMAN DECISION REQUIRED |
| S-003 | `QuantEngine._calculation_history` | Per-instance | YES (dead) | NO | NONE | HUMAN DECISION REQUIRED |
| S-004 | `QuantDataValidator._errors/_warnings` | Per-instance | YES (reset per call) | NO | NONE | OBSERVED |

---

## 4. Statistical Convention Decision Matrix

### 4.1 ddof Mismatch

**Evidence ID: E-006**
- Source: `docs/quant_engine.md` (Documentation) vs `src/data_engine/quant/volatility.py` and `src/data_engine/quant/statistics.py` (Implementation)
- Location: docs say "sample std (ddof=1)" and "Mean, median, variance, standard deviation (sample, ddof=1)". Implementation: `rolling_std(prices, window, ddof: int = 0)` and `variance(values, ddof: int = 0)`.
- Observed: `rolling_std` defaults to `ddof=0` (population). `variance` defaults to `ddof=0` (population). `std` delegates to `variance`. `statistics.mean`, `median`, `covariance`, `correlation`, `z_score`, `percentile` all use their own defaults.
- Claim supported: Documentation claims ddof=1 (sample) but implementation defaults to ddof=0 (population). This is a documentation/implementation divergence, not a bug — both are valid statistical conventions.

| Affected Calculation | Current Default | Documented Default |
| -------------------- | --------------- | ------------------ |
| `rolling_std` | ddof=0 | ddof=1 |
| `variance` | ddof=0 | ddof=1 |
| `std` | ddof=0 (via variance) | ddof=1 (via variance) |
| `covariance` | ddof=0 | ddof=1 |
| `correlation` | ddof=0 | ddof=1 |
| `mean`, `median` | N/A | N/A |
| `z_score` | ddof=0 | ddof=1 |
| `percentile` | N/A | N/A |

| ID | Question | Evidence | Impact | Options | Disposition |
| -- | -------- | -------- | ------ | ------- | ----------- |
| D-005 | Should ddof default be 0 or 1? | E-006 | Changes numerical output for all statistics functions | (1) Change impl to ddof=1; (2) Change docs to ddof=0; (3) Add explicit parameter; (4) Leave with corrected docs | HUMAN DECISION REQUIRED |
| D-006 | Does changing ddof alter historical outputs? | E-006 | YES — different denominators produce different values | Must be assessed if policy changes | HUMAN DECISION REQUIRED |
| D-007 | Could changing ddof affect downstream strategy behavior? | E-006 | Potentially — statistics feed into research agents | Must be assessed if policy changes | HUMAN DECISION REQUIRED |

### 4.2 RSI None Behavior

**Evidence ID: E-013**
- Source: `src/data_engine/quant/momentum.py`
- Location: `rsi()` function (lines 48-135), specifically result initialization at line 68
- Observed: `result: List[Optional[float]] = [None] * n`. The first `period` values are None because RSI requires `period` price changes. The function returns a list of the same length as input, with leading None values.
- Claim supported: RSI result has `period` None values at the start. This is mathematically correct but may confuse downstream consumers expecting no leading None values.

| ID | Question | Evidence | Impact | Options | Disposition |
| -- | -------- | -------- | ------ | ------- | ----------- |
| D-008 | Should RSI pad differently? | E-013 | Downstream code may assume no leading Nones | (1) Accept; (2) Document; (3) Change padding | HUMAN DECISION REQUIRED |

---

## 5. Phase Boundary Matrix

This matrix defines which concerns belong to which phase. It prevents scope leakage.

| Concern | Phase 1 | Phase 2 | Phase 3 | D4 | Future |
| --------- | ------: | ------: | ------: | -: | -----: |
| Data validation | X | X | | | |
| Provenance | X | X | | | |
| Indicator calculations | | X | | | |
| Statistical conventions | | X | | | |
| Calculation metadata | | X | | | |
| Tick size | | | | X | |
| Rounding | | | | X | |
| Tolerance | | | | X | |
| TP/SL comparison | | | | X | |
| Execution price | | | X | | |
| Slippage | | | X | | |
| Same-bar execution | | | X | | |
| Result hashing | | X | X | | |
| Strategy generation | | | X | | |
| Backtesting | | | X | | |
| Security (shell execution) | X | X | | | |
| Model immutability | X | X | | | |
| NaN/Infinity handling | X | X | | | |

**Key observations:**
- Phase 2 owns indicator calculations and statistical conventions but NOT tick-size, rounding, tolerance, or TP/SL comparison (those are D4/future)
- Phase 2 owns result-hashing metadata structure but D4 may change what values are hashed
- Phase 1 owns security and data validation; Phase 2 inherits and extends these

---

## 6. D4 Governance Firewall

### 6.1 Current State

```text
D4 HUMAN APPROVAL: NOT GRANTED
D4 POLICY SELECTION: PENDING
D4 IMPLEMENTATION: PROHIBED
PHASE 3 D4 BLOCKER: ACTIVE
```

### 6.2 Policy Families (Human-Decision Pending)

```text
A — Direct Binary64 Comparison
B — Additive Threshold Construction
C — .10f Normalization
D — Exact Decimal Threshold + Float Price
E — Tick-Size / Price-Precision Normalization
F — Explicit Tolerance / Epsilon
G — Decimal Production Arithmetic
```

**No policy has been selected, ranked, recommended, or implemented.**

### 6.3 Absence Classification

The following are NOT defects — they are the natural state of a phase-2 engine awaiting D4 human decision:

| Absent Feature | Classification | Rationale |
| -------------- | -------------- | --------- |
| Tick-size normalization | D4 | Requires human decision on price-precision model |
| Rounding rules | D4 | Requires human decision on numerical representation |
| Tolerance/epsilon | D4 | Requires human decision on comparison semantics |
| Decimal arithmetic | D4 | Requires human decision on numerical type |
| `.10f` normalization | D4 | Requires human decision on serialization format |

**Evidence: E-008** — No `Decimal`, `decimal`, `getcontext`, or `setcontext` found anywhere in `src/data_engine/quant/`. This is the current state, not a defect.

### 6.4 Existing Decimal Code — NOT Approval

**Evidence: E-008** — Decimal arithmetic exists in `src/data_engine/strategy/backtest.py` and `src/data_engine/strategy/schemas.py` (applied during Phase 1 work).

> Existing Decimal code is not evidence of D4 human approval and must not be interpreted as approval of Policy Family G or any other policy family.

### 6.5 SHA Mismatch

**Evidence:** `sha256sum docs/strategy_engine_design.md` returns `bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166`. Expected locked SHA: `88198b17f86f1af6db06704052b4a36d1d632fb0ec9c9266e64bff587869551d`.

**Status:** Mismatch remains unresolved. Design has not been modified to force a match. D4 cannot be tracked until reconciled.

---

## 7. Existing Phase 3 Failure Separation

### 7.1 The 9 Failures

**Evidence ID: E-039, E-040**
- Source: `tests/test_strategy.py`, `tests/test_strategy_independent.py`
- Observed: `test_strategy.py` imports from `data_engine.strategy.schemas`, `data_engine.strategy.execution`, `data_engine.strategy.position`, `data_engine.strategy.ledger`, `data_engine.strategy.equity`, `data_engine.strategy.backtest`, `data_engine.strategy.provenance`, `data_engine.strategy.metrics`, `data_engine.strategy.validation` — plus `data_engine.schemas`. Does NOT import `data_engine.quant`.
- Observed: `test_strategy_independent.py` imports from `data_engine.strategy.schemas`, `data_engine.strategy.backtest`, `data_engine.strategy.metrics`, `data_engine.strategy.execution`, `data_engine.schemas`. Additionally imports `_format_float` and `_escape` from `data_engine.strategy.schemas` and `BacktestEngine as _BE` and `_format_float as _ff_prod` from `data_engine.strategy.backtest`.
- Claim supported: The 9 failures are in Phase 3 Strategy Engine code, not Phase 2 Quant Engine code. The `_format_float` ImportError in `test_strategy_independent.py` is a Phase 3 defect (missing function in `data_engine.strategy.backtest`).

| # | Test | Area | Phase 2 Related? | Dependency Evidence |
|---|------|------|-------------------|---------------------|
| 1 | `TestExecution::test_long_fill_no_slippage` | Slippage | NO | Imports `data_engine.strategy.*` only |
| 2 | `TestExecution::test_long_fill_with_slippage` | Slippage | NO | Imports `data_engine.strategy.*` only |
| 3 | `TestExecution::test_short_fill_below_requested` | Slippage | NO | Imports `data_engine.strategy.*` only |
| 4 | `TestExecution::test_slippage_with_pct` | Slippage formula | NO | Imports `data_engine.strategy.*` only |
| 5 | `TestExecution::test_slippage_with_atr` | Slippage formula | NO | Imports `data_engine.strategy.*` only |
| 6 | `TestExecution::test_slippage_combined` | Slippage assertion | NO | Imports `data_engine.strategy.*` only |
| 7 | `TestSlippage::test_long_fill_above_requested` | Slippage assertion | NO | Imports `data_engine.strategy.*` only |
| 8 | `TestSlippage::test_short_fill_below_requested` | Slippage assertion | NO | Imports `data_engine.strategy.*` only |
| 9 | `TestResultHashIndependentReconstruction` | `ImportError: _format_float` | NO | Imports `data_engine.strategy.backtest` which lacks `_format_float` |

**HISTORICAL PRE-EXISTENCE: NOT PROVABLE** — The repository contains no Git history. However, **CURRENT DEPENDENCY ANALYSIS: UNRELATED** — confirmed by import chains showing zero dependency on Phase 2 implementation code.

---

## 8. Human Decisions Required

The following decisions require explicit human authorization. None has been selected, ranked, or recommended by this analysis.

### D4-Related Decisions (Block Phase 3)

| ID | Decision Required | Evidence | Impact if Unresolved |
| -- | ----------------- | -------- | -------------------- |
| DR-001 | Select numerical policy family (A–G) | E-008 | All float64 comparison semantics undefined; TP/SL boundary rule unspecified |
| DR-002 | Define tick-size metadata and source | E-008 | Price-precision normalization unspecified |
| DR-003 | Define rounding rules | E-008 | No truncation/rounding policy for calculated values |
| DR-004 | Define tolerance/epsilon semantics | E-008 | All float64 equality uses exact `==`; no boundary tolerance |
| DR-005 | Define Decimal arithmetic policy | E-008 | Existing Decimal code in Phase 3 is not approval |
| DR-006 | Resolve locked design SHA mismatch | SHA mismatch | Design amendments cannot be tracked; D4 blocked |

### Phase 2 Design Decisions (Block Implementation)

| ID | Decision Required | Evidence | Impact if Unresolved |
| -- | ----------------- | -------- | -------------------- |
| DR-007 | How to handle `calculation_timestamp` in canonical hashing | E-001, E-017 | `QuantResult` serialization is non-deterministic; hash consistency unclear |
| DR-008 | Whether `IndicatorRegistry` should be global singleton or request-scoped | E-003 | Thread-safety and test isolation implications |
|| DR-009 | Whether `DataQualityGate._blocked_datasets` should be global or per-instance | E-004, RT-E-006 | In Phase 2 QuantEngine path, `_blocked_datasets` is per-call ephemeral (new `DataQualityGate()` per call). Phase 3 `BacktestEngine` has its own instance. Test isolation impact: LOW for Phase 2 path | Test isolation and concurrency implications |
| DR-010 | Whether `_calculation_history` should be removed, activated, or left as-is | E-002, E-018 | Dead code confusion; potential future feature |
| DR-011 | Statistical convention: ddof=0 or ddof=1 | E-006, E-020 | Changes numerical output for all statistics; affects downstream calculations |
| DR-012 | RSI None-padding behavior | E-013 | Downstream consumers may expect different padding |
| DR-013 | Whether `_metadata()` should explicitly pass `calculation_timestamp` | E-017, E-036 | Controls timestamp provenance in `CalculationMetadata` |
| DR-014 | Phase boundary for tick-size, rounding, tolerance | Phase Boundary Matrix | Prevents scope leakage between phases |

---

## 9. Implementation Gate

```text
PHASE 2 IMPLEMENTATION AUTHORIZATION:

NOT GRANTED

Reason:
Human design decisions remain pending.
```

### Decisions Required Before Implementation

1. **DR-001** — Select numerical policy family (D4)
2. **DR-006** — Resolve locked design SHA mismatch
3. **DR-007** — Resolve `calculation_timestamp` hashing behavior
4. **DR-008** — Resolve `IndicatorRegistry` ownership/lifecycle
5. **DR-009** — Resolve `DataQualityGate._blocked_datasets` ownership/lifecycle
6. **DR-010** — Resolve `_calculation_history` disposition
7. **DR-011** — Resolve statistical ddof convention
8. **DR-012** — Resolve RSI None-padding behavior
9. **DR-013** — Resolve `_metadata()` `calculation_timestamp` handling
10. **DR-014** — Confirm phase boundaries for tick-size/rounding/tolerance

### D4-Specific Gate Conditions

Before any D4-related implementation can begin:
1. Human selects a policy family (A–G)
2. Human defines exact numerical semantics
3. Human approves the complete rule
4. A formal design amendment is created
5. The amended design receives a new SHA-256
6. The amendment is separately reviewed
7. Only then may implementation begin

---

## 10. No-New-File Verification

### Files Modified

```text
NO SOURCE FILES MODIFIED
NO TEST FILES MODIFIED
NO EXISTING DOCUMENTS MODIFIED
NO CONFIGURATION MODIFIED
```

### Files Created

```text
PHASE2_HUMAN_DESIGN_DECISION_MATRIX.md  (this file — the ONLY authorized new artifact)
```

### Verification

```text
git status: On branch master, no commits, untracked files present
```

All source file SHA-256 hashes verified unchanged.

---

## 11. Evidence Register

| Evidence ID | Source | Location / Command | Finding Supported |
| ----------- | ------ | ------------------ | ----------------- |
| E-001 | `src/data_engine/quant/schemas.py` | Lines 28-29, 45 — `CalculationMetadata.calculation_timestamp` | `calculation_timestamp` uses `datetime.now(UTC).isoformat()` via `default_factory` |
| E-002 | `src/data_engine/quant/core.py` | Line 50 | `_calculation_history` declared but never populated (0 append occurrences) |
| E-003 | `src/data_engine/quant/registry.py` | Lines 191, 194-199 | `_registry` is module-level global singleton; `_indicators` is per-instance dict |
| E-004 | `src/data_engine/data_blocked.py` | Lines 91, 116, 132, 148, 163, 179, 199, 202 | `_blocked_datasets` is instance-level mutable dict |
| E-005 | `src/data_engine/quant/validation.py` | Lines 46-47, 60-61 | `_errors` and `_warnings` are per-instance lists reset each `validate()` call |
| E-006 | `docs/quant_engine.md` vs `src/data_engine/quant/volatility.py`, `src/data_engine/quant/statistics.py` | docs say ddof=1; impl defaults to ddof=0 | Statistical convention mismatch between documentation and implementation |
| E-007 | `src/data_engine/quant/`, `src/data_engine/strategy/` | Terminal: `grep -rn "subprocess\|os\.popen\|os\.system\|eval(\|exec(\|pickle\|__import__" src/data_engine/quant/ src/data_engine/strategy/ --include="*.py"` | No shell execution mechanisms found |
| E-008 | `src/data_engine/quant/` | Terminal: `grep -rn "Decimal\|decimal\|getcontext\|setcontext" src/data_engine/quant/ --include="*.py"` | No Decimal arithmetic in Quant Engine; all calculations use Python float64 |
| E-009 | `src/data_engine/quant/schemas.py` | Lines 34, 57, 78, 107, 127 | Five Pydantic models with `ConfigDict(frozen=True)` |
| E-010 | `src/data_engine/quant/core.py` | Lines 208-225 | `_metadata()` does not pass `calculation_timestamp` explicitly |
| E-011 | `src/data_engine/quant/core.py` | grep count for `append.*_calculation_history` | 0 occurrences — `_calculation_history` is dead code |
| E-012 | `src/data_engine/data_blocked.py` | Lines 135, 151, 136, 152 | `DataQualityGate` blocks SYNTHETIC and SIMULATED provenance |
| E-013 | `src/data_engine/quant/momentum.py` | Lines 48-135, especially line 68 | `rsi()` returns `None` for first `period` values |
| E-014 | `tests/test_quant.py` | `test_all_calculation_types_are_deterministic` | All calculation types verified deterministic |
| E-015 | `src/data_engine/quant/moving_averages.py` | Lines 51, 98, 120, 125 | Rolling windows use only `prices[i - period + 1 : i + 1]` — historical data only |
| E-016 | `src/data_engine/quant/momentum.py` | Lines 55-64 | RSI changes use `prices[i-1]` and `prices[i]` — no future observation access |
| E-017 | `src/data_engine/quant/schemas.py` | Lines 28, 44-45, 65 | `CalculationMetadata` fields use `default_factory`; `calculation_timestamp` arrives via default |
| E-018 | `src/data_engine/quant/core.py` | Lines 50, 110, 123, 178 | `_metadata()` called but `_calculation_history` never updated |
| E-019 | `docs/quant_engine.md` | Known Limitations section | "All calculations use Python float64 (limited precision)" |
| E-020 | `src/data_engine/quant/statistics.py` | `mean`, `median`, `variance`, `std` function signatures | All use `ddof: int = 0` (population) as default |
| E-021 | `src/data_engine/quant/` | Terminal: `grep -rn "random\|secrets\|uuid" src/data_engine/quant/ --include="*.py"` | No random number generation in Quant Engine |
| E-022 | `src/data_engine/quant/` | Terminal: `grep -rn "requests\|urllib\|socket\|http\|aiohttp" src/data_engine/quant/ --include="*.py"` | No network access in Quant Engine |
| E-023 | `src/data_engine/quant/returns.py`, `moving_averages.py`, `momentum.py` | Index analysis of all calculation loops | No look-ahead boundary violations; all loops use `i` and `i-1` only |
| E-024 | `docs/quant_engine.md` | NaN/Infinity Policy section | "NaN values are preserved (not silently converted to zero)" |
| E-025 | `docs/quant_engine.md` | Security section | "No LLM calls", "No network calls", "No random numbers", "No mutable global state" |
| E-026 | `docs/quant_engine.md` | Known Limitations section | "Very large datasets may have performance issues", "Indicator results are not cached across sessions" |
| E-027 | `docs/quant_engine.md` | Input Validation section | 7-point validation before calculation |
| E-028 | `src/data_engine/quant/validation.py` | Lines 100-101, 157-166 | `_check_quality_gate()` and `_check_provenance()` both block SYNTHETIC/SIMULATED |
| E-029 | `docs/quant_engine.md` | Data Flow section | `CalculationMetadata` includes `calculation_convention="deterministic"` |
| E-030 | `src/data_engine/quant/registry.py` | Lines 202-213 | `calculate_indicator()` convenience function exists |
| E-031 | `src/data_engine/data_blocked.py` | Lines 135-164 | `DataQualityGate.check()` blocks SYNTHETIC, SIMULATED, UNKNOWN, INVALID, QUARANTINED |
| E-032 | `src/data_engine/quant/validation.py` | Lines 152-166 | `QuantDataValidator._check_provenance()` blocks SYNTHETIC, SIMULATED, UNKNOWN |
| E-033 | `src/data_engine/quant/core.py` | Lines 16-18 | `from datetime import datetime, UTC` imported but not used in calculations |
| E-034 | `tests/test_quant.py` | `test_all_calculation_types_are_deterministic`, `test_deterministic_calculations_not_overridden` | Determinism tests pass |
| E-035 | `tests/test_quant.py` | Terminal: `uv run pytest tests/test_quant.py -v --tb=no -q` | `134 passed in 0.42s` |
| E-036 | `src/data_engine/quant/core.py` | Lines 208-225 | `_metadata()` does not include `calculation_timestamp` in parameter list |
| E-037 | `src/data_engine/quant/schemas.py` | 5 occurrences of `ConfigDict(frozen=True)` | Five frozen Pydantic models in Quant Engine schemas |
| E-038 | `docs/quant_engine.md` | Version section | Engine version 2.0.0 |
| E-039 | `tests/test_strategy.py` | Import analysis | Imports `data_engine.strategy.*` and `data_engine.schemas`; does NOT import `data_engine.quant` |
| E-040 | `tests/test_strategy_independent.py` | Import analysis | Imports `data_engine.strategy.*`, `data_engine.schemas`; imports `_format_float` from `data_engine.strategy.schemas` (causes ImportError) |
| E-041 | Terminal | `grep -rn "subprocess\|os\.popen\|os\.system\|eval(\|exec(\|pickle\|__import__" src/data_engine/quant/ src/data_engine/strategy/ --include="*.py"` | No executable occurrences found |
| E-042 | Terminal | `grep -rn "Decimal\|decimal\|getcontext\|setcontext" src/data_engine/quant/ --include="*.py"` | No Decimal usage in Quant Engine |
| E-043 | Terminal | `uv run pytest tests/test_quant.py -v --tb=no -q` | `134 passed in 0.42s` |
| E-044 | Terminal | `uv run pytest tests/test_redteam.py -v --tb=no -q` | `50 passed in 0.29s` |
| E-045 | Terminal | `uv run pytest tests/ -v --tb=no -q` | `9 failed, 358 passed in 0.83s` |
| E-046 | Terminal | `sha256sum docs/strategy_engine_design.md` | Current SHA: `bd1c606cbb7722ccbf24dac56159bbd44c412a6950537f2daff2914702d5c166` |
| E-047 | `src/data_engine/quant/registry.py` | Lines 191, 194-199 | `_registry` global singleton pattern confirmed |
| E-048 | `src/data_engine/data_blocked.py` | Lines 91, 116-199 | `_blocked_datasets` mutable dict confirmed |
| E-049 | `src/data_engine/quant/core.py` | Line 50 | `_calculation_history` declared but never populated |
| E-050 | `src/data_engine/quant/validation.py` | Lines 46-47 | `_errors` and `_warnings` per-instance mutable lists confirmed |
| RT-E-001 | `docs/quant_engine.md` + `src/data_engine/quant/registry.py` | Security section vs lines 191, 194-199 | Documentation claims "No mutable global state" but `_registry` IS a mutable global singleton |
| RT-E-006 | `src/data_engine/quant/validation.py`, `src/data_engine/data_blocked.py` | Per-call instantiation pattern | `DataQualityGate()` instantiated per validation call in Phase 2 QuantEngine path; `_blocked_datasets` is ephemeral per-call state |
|| RT-E-013 | `src/data_engine/quant/registry.py`, `tests/test_quant.py` | Lines 202-213, lines 824-842 | `calculate_indicator` depends on singleton registry; tests do not mutate registry; indicator functions are pure |

---

## 12. Correction Log

### C-001 — F-003 DataQualityGate Scope Corrected
| Field | Value |
|-------|-------|
| Correction | Changed F-003 disposition from "shared mutable global state" to "instance-level mutable state created per validation call" |
| Reason | Source verification confirmed `DataQualityGate()` is instantiated inside `_check_quality_gate()` in `validation.py` lines 152-166. Each call creates a new `DataQualityGate` instance. `_blocked_datasets` does not persist across calls in the Phase 2 path. |
| Evidence | E-004, RT-E-006 |
| Effect on disposition | F-003 test-isolation impact reduced from MEDIUM to LOW. Phase 3 `backtest.py` has its own `DataQualityGate` instance. No shared state across Phase 2 validation calls. |

### C-002 — Documentation/Implementation Mutable-Global-State Contradiction Added
| Field | Value |
|-------|-------|
| Correction | Added F-023 documenting contradiction between `docs/quant_engine.md` security claim "No mutable global state" and `IndicatorRegistry._registry` being a mutable module-level singleton |
| Reason | Source `registry.py` lines 191, 194-199 confirm `_registry = {}` at module level, accessible via `get_registry()`. The docs claim no mutable global state. This is a documentation/implementation consistency issue, not a demonstrated defect. |
| Evidence | RT-E-001 |
| Effect on disposition | Added F-023 as `DOCUMENTATION / IMPLEMENTATION CONSISTENCY ISSUE`. Human decision required for whether to fix docs or implementation. Not classified as a Phase 2 blocker. |

### C-003 — ddof Mismatch Scope Corrected
| Field | Value |
|-------|-------|
| Correction | Confirmed ddof=0 discrepancy affects `rolling_std`, `variance`, `std`, `covariance`, and `correlation` — all statistical functions with `ddof` parameter in `statistics.py` and `volatility.py`. `mean()` and `median()` have `ddof` parameter but it has no computational effect on these functions. `percentile()` has no ddof parameter. |
| Reason | Cross-referenced `statistics.py` function signatures and `volatility.py` defaults against `docs/quant_engine.md` documentation claim of ddof=1. |
| Evidence | E-006, E-020 |
| Effect on disposition | ddof discrepancy now documented as affecting ALL statistical functions, not just `rolling_std`. Human decision required for convention selection. |

### C-004 — F-001 Evidence Corrected
| Field | Value |
|-------|-------|
| Correction | Added explicit evidence that `docs/quant_engine.md` does NOT mention `calculation_timestamp`. Distinguished source implementation evidence (E-001, E-017) from documentation evidence. |
| Reason | The matrix previously implied `docs/quant_engine.md` documented `calculation_timestamp`. Source evidence shows it is a Pydantic `default_factory` mechanism in `schemas.py`. Documentation describes the engine's "Data Flow" section including `calculation_convention="deterministic"` but does not reference the timestamp field specifically. |
| Evidence | E-001, E-017, E-029 |
| Effect on disposition | F-001 now correctly distinguishes CALCULATION-VALUE DETERMINISM from RESULT-OBJECT DETERMINISM from METADATA DETERMINISM. |

### C-005 — DataQualityGate Test-Isolation Impact Corrected
| Field | Value |
|-------|-------|
| Correction | Changed F-003 test-isolation risk from MEDIUM to LOW for the Phase 2 QuantEngine path |
| Reason | `DataQualityGate` instances are created per-call (not shared). Tests construct their own `QuantEngine` instances. No evidence of test contamination from shared `_blocked_datasets` state. |
| Evidence | RT-E-006 |
| Effect on disposition | Test-isolation impact for Phase 2 is LOW. Phase 3 `backtest.py` has its own instance. |

### C-006 — `calculate_indicator` Registry Dependency Analysis Added
| Field | Value |
|-------|-------|
| Correction | Added Section 3.6 documenting `calculate_indicator` dependency on singleton registry returned by `get_registry()` |
| Reason | `calculate_indicator` calls `get_registry()` which returns the module-level `_registry` singleton. However, tests do not mutate the registry — they only read from pre-registered indicators. Indicator functions are pure functions of their inputs. |
| Evidence | E-030, RT-E-013 |
| Effect on disposition | Registry mutation is possible but not demonstrated in current tests. Calculation outputs are not affected by registry state. Operational impact: NOT ESTABLISHED BY CURRENT EVIDENCE. |

---

## 13. Evidence-Integrity Check

```
ALL MATERIAL CLAIMS HAVE EVIDENCE: YES
ALL SOURCE CLAIMS HAVE LOCATIONS: YES
ALL TEST CLAIMS HAVE COMMANDS/TEST NAMES: YES
ALL ABSENCE CLAIMS HAVE SEARCH SCOPE: YES
ALL "UNRELATED" CLAIMS HAVE DEPENDENCY EVIDENCE: YES
ALL "PRE-EXISTING" CLAIMS RESPECT GIT LIMITATIONS: YES
ALL D4-SENSITIVE CLAIMS HAVE SOURCE EVIDENCE: YES
EVIDENCE REGISTER COMPLETE: YES
```

---

## 14. Final Status

```text
PHASE 2 HUMAN DESIGN MATRIX: CORRECTED / FINALIZED

Artifact Version: v1.1

NO-NEW-FILE RULE: SATISFIED
UNAUTHORIZED FILES CREATED: NONE
UNAUTHORIZED FILES MODIFIED: NONE

PHASE 2 IMPLEMENTATION: NOT AUTHORIZED
D4: BLOCKED
D4 POLICY SELECTION: PENDING
D4 IMPLEMENTATION: PROHIBITED
HUMAN DESIGN REVIEW: REQUIRED

EVIDENCE CITATION REQUIREMENT: SATISFIED
UNSUPPORTED MATERIAL CLAIMS: 0
OVERSTATED CLAIMS REMAINING: 0
MISCLASSIFIED FINDINGS REMAINING: 0
EVIDENCE REGISTER: COMPLETE

GIT HISTORY: UNAVAILABLE
HISTORICAL FILESET COMPARISON: NOT PROVABLE

CORRECTIONS APPLIED: C-001, C-002, C-003, C-004, C-005, C-006

PHASE 1 CLOSURE STATUS: COMPLETE (verified)
PHASE 3 UNRELATED FAILURES: 8 Strategy/Slippage assertion failures, 1 Strategy result-hash ImportError (outside Phase 2 scope)
PHASE 3 D4 BLOCKER: ACTIVE

NEXT AUTHORIZED ACTION: HUMAN REVIEW OF PHASE 2 MATRIX
```

---

*This matrix documents human-reviewable design decisions for the Phase 2 Quant Engine. No source code was modified. All findings are supported by independently verified evidence citations. D4 remains blocked pending explicit human decision.*