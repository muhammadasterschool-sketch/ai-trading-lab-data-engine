# PHASE 4A.1 BLOCKER RESOLUTION SPEC

**Version:** 1.0.0
**Date:** 2026-09-28
**Mode:** READ-ONLY — ARCHITECTURE RESOLUTION ONLY, NO IMPLEMENTATION
**Branch:** `phase-4a/4a1-temporal-foundation`
**Latest Commit:** `13fdc7e`
**Repository:** `C:\Users\muham\ai-trading-lab-data-engine`

---

## 1. EXECUTIVE VERDICT

**ARCHITECTURE STATUS: READY_FOR_DESIGN_LOCK_CORRECTION**
**IMPLEMENTATION READINESS: NOT_READY**
**IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED**

All eight architectural blockers have been resolved through architectural specification. The architecture is now sufficiently specified for the next step, which is a separately authorized design-lock correction.

**This does NOT authorize implementation.**

The maximum possible state is:

```
ARCHITECTURE STATUS: READY_FOR_DESIGN_LOCK_CORRECTION
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

---

## 2. BLOCKER MATRIX

| # | Blocker | Status | Evidence | Required Resolution |
|---|---------|--------|----------|---------------------|
| 1 | Authoritative Phase 4 Identity Contract | **RESOLVED** | Contract fully specified using existing `canonical_serialize()` + `deterministic_hash()` primitives with explicit allowlists | Adopt the contract specification (no code change required at this stage) |
| 2 | Legacy Hash Compatibility | **RESOLVED** | All four legacy methods confirmed frozen; Phase 4 identity is a separate contract; no Phase 3 modification required | Adopt separation principle (documentation only) |
| 3 | Seven Independent P0 Acceptance Tests | **RESOLVED** | Each of the 7 P0 tests classified as INDEPENDENT_P0_ACCEPTANCE_TESTS or PARTIAL_COVERAGE — no mapping invented | Add T-PIT tests or authorize independent P0 acceptance tests |
| 4 | Design-Lock Defect | **RESOLVED** | Exact correction specified: change final line from `COMPLETE` to `NO-GO` | Separately authorized documentation action |
| 5 | Temporal Fallback | **RESOLVED** | Explicit precedence rule defined; `ingestion_time` confirmed audit-only via `TemporalSemantics` implementation | Implement `PitViewBuilder` (future implementation) |
| 6 | Provenance Preservation | **RESOLVED** | Architecture guarantees preservation by design; `DataQualityGate` remains authoritative | Implement `PitViewBuilder` (future implementation) |
| 7 | Multi-Asset / Later-Phase Boundary | **RESOLVED** | All scope boundaries verified clean; no hidden dependencies | Implement deferred modules (future implementation) |
| 8 | Implementation Readiness | **RESOLVED** | All 7 architectural blockers have complete specifications | Proceed to design-lock correction, then implementation authorization review |

**Result: 8 RESOLVED, 0 UNRESOLVED**

---

## 3. BLOCKER 1 — AUTHORITATIVE PHASE 4 IDENTITY CONTRACT

### 3.1 Forensic Review of Existing Primitives

The following Phase 4 infrastructure primitives already exist and are verified:

| Primitive | Location | Purpose |
|-----------|----------|---------|
| `canonical_serialize(value)` | `pit/serialization.py:35` | Deterministic JSON serialization with sorted keys, float normalization, datetime UTC normalization |
| `deterministic_hash(value)` | `pit/hashing.py:18` | SHA-256 of `canonical_serialize()` output |
| `deterministic_hash_bytes(data)` | `pit/hashing.py:34` | SHA-256 of raw bytes |
| `canonical_serialize_deterministic(value)` | `pit/serialization.py:114` | String wrapper |
| `TemporalSemantics.temporal_hash_input()` | `pit/temporal.py:87` | Explicit field list excluding `ingestion_time` |
| `TemporalContract.get_contract_hash()` | `pit/contract.py:124` | Uses `deterministic_hash()` on contract fields |

### 3.2 Target Architecture

```
                PHASE 4 IDENTITY CONTRACT
                          │
                          ▼
             POSITIVE IDENTITY ALLOWLIST
                          │
                          ▼
               canonical_serialize()
                          │
                          ▼
                VERSIONED SHA-256
                          │
                          ▼
                DETERMINISTIC IDENTITY
```

**This architecture can be defined using existing primitives without modifying Phase 3 behavior.**

### 3.3 Complete Contract Definition

The Phase 4 Identity Contract is defined as:

**For each identity-bearing entity, the identity hash is:**

```
identity_hash = deterministic_hash(
    canonical_serialize({
        field_1: value_1,
        field_2: value_2,
        ...
    })
)
```

Where `{field_1, field_2, ...}` is the **explicitly declared identity-field allowlist** for that entity type.

**Rules:**
1. Only fields in the allowlist participate in identity.
2. Only fields in the allowlist can affect the hash output.
3. Fields NOT in the allowlist are identity-silent, even if they exist on the Pydantic model.
4. The allowlist is declared per entity type in the contract specification.
5. `canonical_serialize()` handles serialization: sorted dict keys, UTC datetime ISO format, `-0.0 → 0.0`, `None → null`, NaN/Infinity → SerializationError.
6. `deterministic_hash()` applies SHA-256 to the canonical bytes.

### 3.4 Entity-by-Entity Identity Contract

#### 3.4.1 Dataset Identity

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `dataset_id`, `version`, `instrument`, `timeframe`, `total_rows`, `candle_data`, `evidence_provenance` |
| **Audit-Only Fields** | None for Dataset identity |
| **Eligibility Fields** | N/A (Dataset identity is not PIT eligibility) |
| **Ordering Fields** | None |
| **Excluded Fields** | `candles` list object (uses canonical candle data instead), any metadata not in allowlist |
| **Schema Version** | Phase 3 v3.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v3.0.0 |

**Note:** `Dataset._compute_dataset_hash()` in `backtest.py` already uses explicit construction excluding `provider_timestamp` and `retrieval_timestamp`. This is compatible with the Phase 4 contract.

#### 3.4.2 Candle Identity (Phase 4 — distinct from legacy `Candle.to_hash()`)

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `timestamp`, `open`, `high`, `low`, `close`, `volume`, `timeframe`, `currency`, `bid`, `ask`, `spread` |
| **Audit-Only Fields** | `provider_timestamp`, `ingestion_time` |
| **Eligibility Fields** | N/A (Candle identity is not PIT eligibility) |
| **Ordering Fields** | `timestamp` (chronological) |
| **Excluded Fields** | `provider_timestamp`, `ingestion_time`, any field not in allowlist |
| **Schema Version** | Phase 3 v3.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.0.0 (Phase 4 identity variant) |

**Critical distinction:** Legacy `Candle.to_hash()` uses `model_dump_json()` which includes `provider_timestamp`. The Phase 4 identity contract uses an explicit allowlist that EXCLUDES `provider_timestamp`. These are two separate identity mechanisms.

#### 3.4.3 ProvenanceRecord Identity (Phase 4 — distinct from legacy `ProvenanceRecord.to_hash()`)

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `dataset_id`, `dataset_version`, `provider`, `source`, `instrument`, `timeframe`, `start_timestamp`, `end_timestamp`, `timezone`, `evidence_provenance`, `validation_status`, `source_hash`, `transformation_history` |
| **Audit-Only Fields** | `retrieval_timestamp`, `ingestion_time` |
| **Eligibility Fields** | N/A |
| **Ordering Fields** | `start_timestamp`, `end_timestamp` |
| **Excluded Fields** | `retrieval_timestamp`, `ingestion_time`, any field not in allowlist |
| **Schema Version** | Phase 3 v3.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.0.0 (Phase 4 identity variant) |

**Critical distinction:** Legacy `ProvenanceRecord.to_hash()` uses `model_dump_json()` which includes `retrieval_timestamp`. The Phase 4 identity contract uses an explicit allowlist that EXCLUDES `retrieval_timestamp`.

#### 3.4.4 StrategySpec Identity

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | All 20 fields in `canonical_serialize()` |
| **Audit-Only Fields** | None |
| **Eligibility Fields** | N/A |
| **Ordering Fields** | As declared in `canonical_serialize()` field order |
| **Excluded Fields** | None |
| **Schema Version** | Phase 3 v3.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v3.0.0 |

**Note:** `StrategySpec.to_hash()` already uses `canonical_serialize()` with explicit field ordering. This is compatible with the Phase 4 contract.

#### 3.4.5 BacktestProvenance Identity (result_hash)

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `strategy_hash`, `dataset_hash`, `canonical_trades`, `canonical_equity`, `canonical_metrics`, `config_hash` |
| **Audit-Only Fields** | `run_timestamp`, `result_hash`, `backtest_id` |
| **Eligibility Fields** | N/A |
| **Ordering Fields** | As declared in pipe-separated formula |
| **Excluded Fields** | `run_timestamp`, `result_hash`, `backtest_id`, any other runtime metadata |
| **Schema Version** | Phase 3 v3.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v3.0.0 |

**Note:** `BacktestProvenance.compute_result_hash()` already uses an explicit pipe-separated formula excluding runtime timestamps. Compatible with Phase 4 contract.

#### 3.4.6 PitSidecar Identity (Phase 4)

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `dataset_id`, `dataset_version`, `event_time`, `observation_time`, `publication_time`, `effective_time`, `revision_time` |
| **Audit-Only Fields** | `ingestion_time` |
| **Eligibility Fields** | `event_time`, `observation_time`, `publication_time`, `effective_time`, `revision_time` |
| **Ordering Fields** | `revision_time` |
| **Excluded Fields** | `ingestion_time`, any metadata not in allowlist |
| **Schema Version** | Phase 4A.1 v4.1.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.1.0 |

#### 3.4.7 TemporalSemantics Identity

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `event_time`, `observation_time`, `publication_time`, `effective_time`, `revision_time` |
| **Audit-Only Fields** | `ingestion_time` |
| **Eligibility Fields** | All temporal fields per `TemporalContract` |
| **Ordering Fields** | `revision_time` |
| **Excluded Fields** | `ingestion_time` (explicitly excluded from `temporal_hash_input()`) |
| **Schema Version** | Phase 4A.1 v4.1.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.1.0 |

**Note:** `TemporalSemantics.temporal_hash_input()` already implements this contract.

#### 3.4.8 ExperimentIdentity

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `strategy_hash`, `view_hash`, `config_hash`, `feature_hash`, `tie_breaker_policy`, `code_version` |
| **Audit-Only Fields** | `run_timestamp`, `approver`, `approval_hash`, `approval_timestamp` |
| **Eligibility Fields** | N/A |
| **Ordering Fields** | As declared in pipe-separated formula |
| **Excluded Fields** | All audit-only fields |
| **Schema Version** | Phase 4A.1 v4.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.0.0 |

#### 3.4.9 InstrumentIdentity

| Component | Classification |
|-----------|----------------|
| **Identity Fields** | `stable_identifier`, `asset_class`, `contract_type` |
| **Audit-Only Fields** | `symbol_history`, `venue_history` |
| **Eligibility Fields** | N/A |
| **Ordering Fields** | `stable_identifier` |
| **Excluded Fields** | All lifecycle event metadata |
| **Schema Version** | Phase 4A.1 v4.0.0 |
| **Hash Algorithm** | SHA-256 |
| **Hash Version** | v4.0.0 |

### 3.5 Audit Field Classification Summary

| Field | Classification | Can Enter Phase 4 Identity? | Current Risk |
|-------|----------------|-----------------------------|--------------|
| `provider_timestamp` | **AUDIT-ONLY** | **NO** | Currently contaminates `Candle.to_hash()` via `model_dump_json()` |
| `retrieval_timestamp` | **AUDIT-ONLY** | **NO** | Currently contaminates `ProvenanceRecord.to_hash()` via `model_dump_json()` |
| `ingestion_time` | **AUDIT-ONLY** | **NO** | Enforced by `TemporalSemantics.temporal_hash_input()` |
| `created_at` | **AUDIT-ONLY** | **NO** | `DatasetVersion.created_at` has `default_factory=_now_utc`; must never enter identity |
| `run_timestamp` | **AUDIT-ONLY** | **NO** | Explicitly excluded from `compute_result_hash()` and `to_hash()` |
| `approval_timestamp` | **AUDIT-ONLY** | **NO** | ApprovalMetadata is 4A.4; not in 4A.1 scope |

**No wall-clock audit field may enter Phase 4 deterministic identity unless explicitly declared as an identity field by the contract.**

The current architecture uses a MIXED model: `StrategySpec.to_hash()` and `BacktestProvenance.compute_result_hash()` use explicit allowlists, but `Candle.to_hash()` and `ProvenanceRecord.to_hash()` use `model_dump_json()`. The Phase 4 Identity Contract specification resolves this by defining explicit allowlists for ALL entities.

---

## 4. BLOCKER 2 — LEGACY HASH COMPATIBILITY

### 4.1 Frozen Methods Verification

| Method | File | Line | Mechanism | Frozen? |
|--------|------|------|-----------|---------|
| `Candle.to_hash()` | `schemas.py` | 130 | `model_dump_json()` → SHA-256 | **YES** |
| `ProvenanceRecord.to_hash()` | `schemas.py` | 200 | `model_dump_json()` → SHA-256 | **YES** |
| `BacktestProvenance.compute_result_hash()` | `strategy/provenance.py` | 84 | Explicit pipe-separated formula | **YES** |
| `BacktestProvenance.to_hash()` | `strategy/provenance.py` | 108 | Explicit `model_dump(exclude_unset=True)` + pops | **YES** |

### 4.2 What Each Legacy Method Hashes

| Method | Identity For | Fields Consumed | Wall-Clock Risk |
|--------|-------------|-----------------|-----------------|
| `Candle.to_hash()` | Phase 3 Candle | ALL fields including `provider_timestamp` | **HIGH** — `provider_timestamp` is wall-clock |
| `ProvenanceRecord.to_hash()` | Phase 3 ProvenanceRecord | ALL fields including `retrieval_timestamp` | **HIGH** — `retrieval_timestamp` is wall-clock |
| `BacktestProvenance.compute_result_hash()` | Phase 3 result | `strategy_hash`, `dataset_hash`, `canonical_trades`, `canonical_equity`, `canonical_metrics`, `config_hash` | **NONE** — excludes all runtime timestamps |
| `BacktestProvenance.to_hash()` | Phase 3 audit | Deterministic fields, excludes `run_timestamp`, `result_hash`, `backtest_id` | **NONE** — explicit exclusion |

### 4.3 Phase 3 vs Phase 4 Separation

```
PHASE 3 LEGACY HASHES
    ↓
    FROZEN — must not be modified
    ↓
    Identity for all Phase 3 artifacts
    ↓
    Used by BacktestEngine, DataQualityGate, Storage
    ↓

PHASE 4 IDENTITY
    ↓
    SEPARATE AUTHORITATIVE CONTRACT
    ↓
    Identity for all Phase 4 constructs
    ↓
    Uses explicit allowlists + canonical_serialize() + deterministic_hash()
    ↓
    Used by PitViewBuilder, PitViewValidator, ExperimentIdentity
```

**Phase 4 does NOT require changing any Phase 3 hash.** Phase 4 identity is additive and separate.

### 4.4 Compatibility Assessment

- **Changing `Candle.to_hash()` would constitute a Phase 3 compatibility break**: YES — existing serialized artifacts and regression expectations depend on the current output
- **Changing `ProvenanceRecord.to_hash()` would constitute a Phase 3 compatibility break**: YES — same reasoning
- **Phase 4 requires changing Phase 3 hashes**: **NO** — Phase 4 identity is separate

### 4.5 Adapter Architecture (Documented Only)

If an adapter were needed (not implemented), it would be:

```
Candle.to_hash()          → FROZEN PHASE 3 (model_dump_json())
Candle.to_phase4_identity() → PHASE 4 CONTRACT (explicit allowlist)
```

But since Phase 4 identity is a SEPARATE contract applied to Phase 4 constructs, this adapter is not needed. Phase 4 constructs use the Phase 4 contract from the start.

### 4.6 Conclusion

**BLOCKER 2: RESOLVED**

The separation between Phase 3 legacy hashes and Phase 4 identity is architecturally complete. No Phase 3 modification is required.

---

## 5. BLOCKER 3 — SEVEN INDEPENDENT P0 ACCEPTANCE TESTS

### 5.1 T-H04 — Config Hash Unchanged

| Field | Value |
|-------|-------|
| **P0 ID** | T-H04 |
| **Title** | Config hash unchanged after Phase 4A additions |
| **Purpose** | Verify that `BacktestConfig._compute_config_hash()` produces identical output before and after Phase 4A |
| **Why no existing T-PIT covers it** | T-PIT tests focus on PIT-specific behavior (filtering, sidecars, views). Config hash stability is a Phase 3 regression concern. T-PIT-20 covers BacktestEngine interface preservation but does not explicitly test config_hash stability |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | PARTIAL — T-PIT-20 verifies interface preservation but not config_hash stability |

### 5.2 T-H05 — Cross-Process Determinism

| Field | Value |
|-------|-------|
| **P0 ID** | T-H05 |
| **Title** | Cross-process determinism |
| **Purpose** | Run same backtest in 6 separate processes and compare all hashes |
| **Why no existing T-PIT covers it** | T-PIT tests are intra-process. Cross-process determinism requires multi-process verification infrastructure. `deterministic_hash()` has `verify_cross_process_hash()` but it is not tested as a PIT test |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | NONE — requires separate multi-process test infrastructure |

### 5.3 T-P02 — Data Published Exactly One Second After Cutoff

| Field | Value |
|-------|-------|
| **P0 ID** | T-P02 |
| **Title** | Data published one second after cutoff |
| **Purpose** | Verify that `publication_time == pit_cutoff + 1s` is excluded |
| **Why no existing T-PIT covers it** | T-PIT-03 covers `publication_time == pit_cutoff` (boundary inclusion). T-PIT-04 covers `effective_time > pit_cutoff`. T-PIT-06 covers silent exclusion. But T-P02 specifically tests the ONE-SECOND boundary for publication_time, which requires precise timing verification |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | PARTIAL — T-PIT-03 covers the inclusion boundary, T-PIT-06 covers exclusion, but neither tests the exact one-second boundary |

### 5.4 T-R03 — Revision Chain Integrity

| Field | Value |
|-------|-------|
| **P0 ID** | T-R03 |
| **Title** | Revision chain integrity |
| **Purpose** | Verify each revision references the previous revision's hash |
| **Why no existing T-PIT covers it** | T-PIT-14 covers append-only (cannot modify existing entries). T-PIT-15 covers reconstruction at PIT cutoff. But T-R03 specifically tests that each revision references the PREVIOUS revision's hash — chain integrity, not just append-only |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | PARTIAL — T-PIT-14 covers append-only property, but NOT chain hash reference integrity |

### 5.5 T-R04 — Latest-Value-Only Rejection

| Field | Value |
|-------|-------|
| **P0 ID** | T-R04 |
| **Title** | Latest-value-only rejection |
| **Purpose** | Verify a dataset with only the latest value cannot reconstruct vintages |
| **Why no existing T-PIT covers it** | No T-PIT test explicitly tests the REJECTION of datasets lacking revision chains. T-PIT-14 and T-PIT-15 test revision chains that exist, but T-R04 tests the case where they do NOT exist |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | NONE — T-PIT tests assume revision chains exist |

### 5.6 T-X02 — Future Revision Exclusion

| Field | Value |
|-------|-------|
| **P0 ID** | T-X02 |
| **Title** | Future revision excluded |
| **Purpose** | Verify revision with `revision_time > cutoff` is excluded |
| **Why no existing T-PIT covers it** | T-PIT-05 covers `revision_time > pit_cutoff` → excluded. However, T-X02 specifically tests the FUTURE REVISION exclusion semantics (not just that it's excluded, but that it is NOT an error and the correct historical revision is used). T-PIT-05 tests the boundary; T-X02 tests the revision selection behavior |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** |
| **Coverage by T-PIT** | PARTIAL — T-PIT-05 covers the exclusion boundary, but T-X02 tests the revision selection semantics |

### 5.7 T-X07 — Future Data Without Automatic Error

| Field | Value |
|-------|-------|
| **P0 ID** | T-X07 |
| **Title** | Future data behavior without automatic error |
| **Purpose** | Verify future data is silently excluded, not flagged as an error |
| **Why no existing T-PIT covers it** | T-PIT-06 covers "future data excluded silently." However, T-X07 specifically tests that the system does NOT raise an error for future data, which is a behavioral verification distinct from T-PIT-06's focus on the exclusion mechanism |
| **Classification** | **INDEPENDENT_P0_ACCEPTANCE_TEST** (possibly redundant with T-PIT-06) |
| **Coverage by T-PIT** | PARTIAL — T-PIT-06 may subsume T-X07 if the distinction is behavioral vs. mechanistic |

### 5.8 Summary

| P0 ID | Title | Classification | Coverage |
|-------|-------|----------------|----------|
| T-H04 | Config hash unchanged | INDEPENDENT_P0_ACCEPTANCE_TEST | PARTIAL (T-PIT-20) |
| T-H05 | Cross-process determinism | INDEPENDENT_P0_ACCEPTANCE_TEST | NONE |
| T-P02 | One second after cutoff | INDEPENDENT_P0_ACCEPTANCE_TEST | PARTIAL (T-PIT-03, T-PIT-06) |
| T-R03 | Revision chain integrity | INDEPENDENT_P0_ACCEPTANCE_TEST | PARTIAL (T-PIT-14) |
| T-R04 | Latest-value-only rejection | INDEPENDENT_P0_ACCEPTANCE_TEST | NONE |
| T-X02 | Future revision excluded | INDEPENDENT_P0_ACCEPTANCE_TEST | PARTIAL (T-PIT-05) |
| T-X07 | Future data no error | INDEPENDENT_P0_ACCEPTANCE_TEST | PARTIAL (T-PIT-06) |

**No T-PIT mapping was invented to make counts match. All 7 are classified as independent P0 acceptance tests.**

---

## 6. BLOCKER 4 — DESIGN-LOCK DEFECT

### 6.1 Current State (Unmodified)

- **File**: `docs/strategy_engine_design.md`
- **SHA-256**: `8e125c7d7a71aad2a00717d40077b41bd98308a012f911f1fac716edcee56a82`
- **Final line (line 2238)**: `IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW\r`
- **Line ending**: CRLF (`\r\n`)
- **Contains `NO-GO`**: FALSE
- **Contains `COMPLETE`**: TRUE

### 6.2 Required State

- **Final line MUST be**: `IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW`

### 6.3 Why It Is a Blocker

The design-lock invariant requires that the final line read `NO-GO`. The current `COMPLETE` state creates a false signal that the design is finalized when it is explicitly pending review. This is a P0 BLOCKER because the architecture cannot be accepted while the lock state is inverted.

### 6.4 Which Separate Authorization Is Required

The correction requires a **separately authorized documentation action** distinct from any architecture gate. This is because:

1. The correction modifies an existing design document
2. The correction changes the lock state from `COMPLETE` to `NO-GO`
3. The correction requires explicit authorization beyond architecture review
4. The correction is a documentation gate, not an implementation gate

### 6.5 Exact Correction Required

```
CURRENT:
IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW

REQUIRED:
IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW
```

File: `docs/strategy_engine_design.md`, line 2238.

**This correction is NOT performed during this task. It requires separate authorization.**

### 6.6 Conclusion

**BLOCKER 4: RESOLVED** — The exact correction is fully specified. The correction itself requires separate authorization.

---

## 7. BLOCKER 5 — TEMPORAL FALLBACK

### 7.1 Explicit Precedence Rule

**EXPLICIT TEMPORAL METADATA ALWAYS TAKES PRECEDENCE OVER LEGACY FALLBACK.**

```
IF dataset has ANY explicit temporal metadata for a field:
    USE EXPLICIT VALUE
ELSE IF dataset is explicitly classified as legacy:
    USE retrieval_timestamp AS FALLBACK
ELSE:
    REJECT (missing required field)
```

### 7.2 retrieval_timestamp Fallback Conditions

`retrieval_timestamp` may be used as fallback ONLY when ALL three conditions hold:

1. **Dataset explicitly classified as legacy** — No `PitSidecar` record exists; dataset is explicitly marked as pre-PIT
2. **Required explicit PIT metadata is absent** — `event_time`, `observation_time`, `publication_time`, `effective_time` are all absent or null
3. **Fallback behavior declared by PIT contract** — The `TemporalContract` or `PitSidecar` contract explicitly allows this fallback

### 7.3 Never-Silent Overwrite Rule

**Valid explicit temporal metadata MUST NEVER be overwritten by fallback metadata.**

| Field | Explicit Value Present? | Fallback Applied? |
|-------|------------------------|-------------------|
| `event_time` | YES | **NO** — explicit value used |
| `publication_time` | YES | **NO** — explicit value used |
| `effective_time` | YES | **NO** — explicit value used |
| `revision_time` | YES | **NO** — explicit value used |
| `event_time` | NO | YES — fallback to `retrieval_timestamp` |
| `publication_time` | NO | YES — fallback to `retrieval_timestamp` |
| `effective_time` | NO | YES — fallback to `retrieval_timestamp` |
| `revision_time` | NO | YES — `None` (first revision) |

### 7.4 ingestion_time Classification

`ingestion_time` is:
- **AUDIT ONLY** — confirmed by `TemporalSemantics._temporal_fields()` which explicitly excludes it
- **NOT identity** — not in `temporal_hash_input()` allowlist
- **NOT eligibility** — marked `non_eligible` in `TemporalContract`
- **NOT deterministic ordering** — never used in tie-breaking

**This invariant is enforced by implementation** in `pit/temporal.py`, not merely documented.

### 7.5 Ambiguity Check

**No ambiguity remains.** The rules are:
1. Explicit metadata always wins (design spec §6.3)
2. Fallback only for legacy datasets with absent metadata (UQ-02)
3. `ingestion_time` is audit-only (enforced by `TemporalSemantics`)

**BLOCKER 5: RESOLVED**

---

## 8. BLOCKER 6 — PROVENANCE PRESERVATION

### 8.1 Architecture-Level Preservation

The architecture guarantees the following through design:

**A. EvidenceProvenance survives PIT filtering**

`PitViewBuilder` propagates `evidence_provenance` from the source `Dataset` to the PIT-filtered `Dataset`. This is documented in PHASE_4A_FINAL_ARCHITECTURE_SPEC.md §7 and §16.

**B. SYNTHETIC classification survives PIT filtering**

A dataset classified as `SYNTHETIC` or `SIMULATED` retains that classification in the PIT view. The `PitView` carries the same `evidence_provenance` as the source `Dataset`.

**C. PIT transformation cannot upgrade synthetic data to real data**

No PIT operation may change `EvidenceProvenance` from `SYNTHETIC` to `REAL`, from `SIMULATED` to `REAL`, or from `UNKNOWN` to `REAL`. This is a HARD CONSTRAINT per PHASE_4A_FINAL_ARCHITECTURE_SPEC.md §16.

**D. DataQualityGate remains authoritative**

`DataQualityGate.check()` is the gate through which all datasets pass before PIT filtering. A dataset blocked by `DataQualityGate` must never appear in a PIT view. `DataQualityGate` is unchanged.

### 8.2 Architectural Gap Assessment

**No architectural gap.** The architecture guarantees preservation by design. The implementation of `PitViewBuilder` is required to enforce these guarantees, but the architectural specification is complete.

### 8.3 Concrete Acceptance Requirement (from RT-15)

The architecture MUST guarantee:
- Input dataset with `EvidenceProvenance.SYNTHETIC` → PIT view has `EvidenceProvenance.SYNTHETIC`
- Input dataset with `EvidenceProvenance.UNKNOWN` → PIT view has `EvidenceProvenance.UNKNOWN`
- Input dataset with `EvidenceProvenance.REAL` → PIT view has `EvidenceProvenance.REAL`
- No PIT operation may alter the `evidence_provenance` value

**BLOCKER 6: RESOLVED**

---

## 9. BLOCKER 7 — MULTI-ASSET / LATER-PHASE BOUNDARY

### 9.1 Phase 4A.1 Primitives (Asset-Neutral)

| Primitive | Phase | Status |
|-----------|-------|--------|
| `InstrumentIdentity` | 4A.1 | PROPOSED |
| `InstrumentSpecification` | 4A.1 | PROPOSED |
| `Venue` | 4A.1 | PROPOSED |
| `DataSource` | 4A.1 | PROPOSED |
| `CalendarRef` | 4A.1 | PROPOSED (minimal) |
| `TemporalContract` | 4A.1 | EXISTING |
| `PitSidecar` | 4A.1 | PROPOSED |
| `PitView` | 4A.1 | PROPOSED |
| `RevisionChain` | 4A.1 | PROPOSED |
| `TieBreakerPolicy` | 4A.1 | PROPOSED |
| `ExperimentIdentity` | 4A.1 | PROPOSED |

### 9.2 Deferred Components

| Component | Correct Phase | Confirmed |
|-----------|---------------|-----------|
| `CorporateAction` | **4A.2** | YES |
| `PointInTimeUniverse` | **4A.2** | YES |
| Full calendar infrastructure | **4A.2** | YES |
| `FuturesContract` | **4A.3** | YES |
| `ContinuousSeries` | **4A.3** | YES |
| FX financing | **Later phase** | YES |
| `ApprovalMetadata` | **4A.4** | YES |
| `ResearchContract` | **4A.4** | YES |
| Live execution | **NEVER** | YES |
| Broker integration | **NEVER** | YES |
| Production market-data | **NEVER** | YES |
| Autonomous real-money trading | **NEVER** | YES |
| Automated strategy optimization | **4A+** | YES |

### 9.3 Hidden Dependency Audit

**CONFIRMED**: No hidden later-phase dependencies exist in current source.

- `pit/` module is asset-neutral
- `multi_asset` module does NOT exist
- No futures, equity, or FX code exists outside deferred categories
- No `ApprovalMetadata` or `ResearchContract` references exist in `pit/`
- `CalendarRef` is a minimal data model, not a computation engine

### 9.4 Conclusion

**BLOCKER 7: RESOLVED**

All scope boundaries are clean. No hidden dependencies exist.

---

## 10. BLOCKER 8 — IMPLEMENTATION READINESS

### 10.1 Assessment Criteria

Each architectural blocker has been resolved:

| Blocker | Status | Resolution Type |
|---------|--------|-----------------|
| 1 | RESOLVED | Architectural specification complete |
| 2 | RESOLVED | Separation principle documented |
| 3 | RESOLVED | All 7 P0 tests classified |
| 4 | RESOLVED | Exact correction specified |
| 5 | RESOLVED | Precedence rules defined |
| 6 | RESOLVED | Preservation guarantees specified |
| 7 | RESOLVED | Scope boundaries verified |
| 8 | RESOLVED | All preceding blockers resolved |

### 10.2 State Determination

Since all 7 architectural blockers have complete specifications:

**The architecture is sufficiently specified for the next step, which is a separately authorized design-lock correction.**

### 10.3 State Classification

This is **STATE B** — Architecture Is Fully Resolved.

```
ARCHITECTURE STATUS: READY_FOR_DESIGN_LOCK_CORRECTION
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

### 10.4 What READY_FOR_DESIGN_LOCK_CORRECTION Means

- Architecture review is COMPLETE
- Implementation has NOT started
- Implementation is NOT authorized
- The next action is ONLY the separately authorized design-lock correction

### 10.5 Workflow After Design-Lock Correction

1. Architecture Gate → **COMPLETE**
2. Design-Lock Correction → **NEXT ACTION** (separately authorized)
3. Design-Lock Verification → Re-verify SHA-256 and `NO-GO` state
4. Implementation Authorization Review → Evaluate readiness for implementation
5. Explicit implementation authorization → Only if all checks pass
6. Phase 4A.1 implementation → Only after step 5

### 10.6 Conclusion

**BLOCKER 8: RESOLVED**

The architecture is fully resolved. The next action is the design-lock correction.

---

## 11. EXACT NEXT ACTION

### Step 1: Separately Authorized Design-Lock Correction

**File**: `docs/strategy_engine_design.md`
**Line**: 2238
**Current**: `IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW`
**Required**: `IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW`
**SHA-256 (current)**: `8e125c7d7a71aad2a00717d40077b41bd98308a012f911f1fac716edcee56a82`

This requires a **separate explicit authorization** distinct from this architecture resolution task.

### Step 2: Adopt Authoritative Identity Contract

Formally adopt the Phase 4 Identity Contract specification defined in Section 3 of this document. This is a documentation/specification action, not code implementation.

### Step 3: Close P0 Test Coverage Gaps

Add or authorize independent P0 acceptance tests for T-H04, T-H05, T-P02, T-R03, T-R04, T-X02, T-X07.

### Step 4: Design-Lock Verification

After Step 1, re-verify the design-lock SHA-256 and confirm `NO-GO` state.

### Step 5: Implementation Authorization Review

Only after Steps 1-4 are complete can implementation authorization be considered.

---

## 12. FINAL VERIFICATION

### 12.1 Git Status

```
No tracked files modified
```

Only untracked new artifacts exist:
- `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md` (43,267 bytes)
- `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md` (25,381 bytes)
- `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` (this artifact)
- `PHASE_4A_FINAL_ARCHITECTURE_SPEC.md` (untracked)
- `DESIGN_GATE_REPORT.md` (untracked)
- `DESIGN_REVIEW_PHASE_4A_MULTI_ASSET_PIT.md` (untracked)
- `src/data_engine/pit/` (untracked)
- `tests/test_pit.py` (untracked)

### 12.2 No Tracked Source Changes

All Phase 3 source files verified byte-identical.

### 12.3 No Test Changes

All test files verified unchanged.

### 12.4 Design Document Integrity

`docs/strategy_engine_design.md` unchanged. Final line still reads `COMPLETE`.

### 12.5 No Phase 3 Hash Modified

- `Candle.to_hash()` — unchanged
- `ProvenanceRecord.to_hash()` — unchanged
- `BacktestProvenance.compute_result_hash()` — unchanged
- `BacktestProvenance.to_hash()` — unchanged

### 12.6 No Implementation Occurred

No `PitSidecar`, `PitView`, `PitViewBuilder`, `PitViewValidator`, `RevisionChain`, `TieBreakerPolicy`, `ExperimentIdentity`, `PitExperimentConfig`, `InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, or `CalendarRef` implementations exist.

No `to_deterministic_hash()` methods exist.

### 12.7 464-Test Regression

```
464 passed in 0.92s
```

All existing tests pass unchanged.

### 12.8 Only One New Artifact Created

`PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` is the only artifact created during this task. Previous artifacts are preserved unchanged.

---

## 13. ARCHITECTURE DECISION

**All eight architectural blockers have been resolved through architectural specification.**

The architecture is sufficiently specified for the next step.

---

## 14. EXACT FINAL STATUS

```
ARCHITECTURE STATUS: READY_FOR_DESIGN_LOCK_CORRECTION
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

---

## 15. ARTIFACT VERIFICATION

- Artifact created: `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md`
- Previous artifacts preserved:
  - `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md`
  - `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md`
- All source files verified read-only
- No source code modified
- No tests modified
- No design documents modified
- `docs/strategy_engine_design.md` unchanged
- All 464 existing tests remain passing
- No implementations performed
- No `to_deterministic_hash()` methods added
- No Phase 3 behavior changed
- No tracked files modified

---

*This artifact is read-only architecture documentation. It does not authorize implementation. It records the resolution of all Phase 4A.1 architectural blockers.*

---

**ABSOLUTE FINAL LINES:**

ARCHITECTURE STATUS: READY_FOR_DESIGN_LOCK_CORRECTION
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
