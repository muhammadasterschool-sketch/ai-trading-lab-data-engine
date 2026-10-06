# PHASE 4A.1 ARCHITECTURE CORRECTION SPEC

**Version:** 1.0.0
**Date:** 2026-09-28
**Mode:** READ-ONLY — NO IMPLEMENTATION AUTHORIZED
**Branch:** `phase-4a/4a1-temporal-foundation`
**Latest Commit:** `13fdc7e`
**Repository:** `C:\Users\muham\ai-trading-lab-data-engine`

---

## 0. AUTHORIZATION STATUS

**ARCHITECTURE STATUS: REQUIRES_REVISION**
**IMPLEMENTATION READINESS: NOT_READY**
**IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED**

---

## 1. AUTHORITATIVE PHASE 4A.1 P0 INVENTORY

### 1.1 Exactly 19 Phase 4A.1 P0 Tests

These are the ONLY Phase 4A.1 P0 tests. No other IDs are admitted.

| # | TEST ID | CATEGORY | INVARIANT |
|---|---------|----------|-----------|
| 1 | T-H01 | Hash Stability | Result hash unchanged after Phase 4A additions |
| 2 | T-H02 | Hash Stability | Dataset hash unchanged |
| 3 | T-H03 | Hash Stability | Strategy hash unchanged |
| 4 | T-H04 | Hash Stability | Config hash unchanged |
| 5 | T-H05 | Hash Stability | Cross-process determinism |
| 6 | T-P01 | PIT Cutoff Boundary | Data published exactly at cutoff → included |
| 7 | T-P02 | PIT Cutoff Boundary | Data published one second after cutoff → excluded |
| 8 | T-P03 | PIT Cutoff Boundary | Data revised after cutoff → latest revision at cutoff used |
| 9 | T-P04 | PIT Cutoff Boundary | Data with publication_time after cutoff → excluded, no error |
| 10 | T-R01 | Revision History | Single revision → one visible entry at any cutoff |
| 11 | T-R02 | Revision History | Multiple revisions → only `revision_time <= T` visible |
| 12 | T-R03 | Revision History | Revision chain integrity maintained |
| 13 | T-R04 | Revision History | Latest-value-only rejection |
| 14 | T-M01 | Missing Temporal Metadata | Missing event_time → rejected |
| 15 | T-M06 | Missing Temporal Metadata | Naive datetime → ValidationError |
| 16 | T-O01 | Deterministic Ordering | Same timestamp, different venue → tie-breaker orders lexicographically |
| 17 | T-X01 | Invalid/Future Information | Future publication excluded |
| 18 | T-X02 | Invalid/Future Information | Future revision excluded |
| 19 | T-X07 | Invalid/Future Information | Future data silently excluded, no error raised |

### 1.2 Later-Phase P0 (SEPARATE INVENTORY — NOT Phase 4A.1)

| # | TEST ID | CATEGORY | PHASE |
|---|---------|----------|-------|
| 1 | T-EQ01 | Equity Corporate Actions | Later 4A.2 |
| 2 | T-EQ04 | Delisting Survivorship | Later 4A.2 |
| 3 | T-EQ05 | Point-in-Time Universe | Later 4A.2 |
| 4 | T-FU01 | Contract Expiry Boundary | Later 4A.3 |
| 5 | T-FU02 | Roll Boundary | Later 4A.3 |
| 6 | T-FU03 | Continuous Series Adjustment | Later 4A.3 |
| 7 | T-FU05 | Roll Leakage | Later 4A.3 |
| 8 | T-C01 | Calendar Version Changes | Later 4A.2 |

### 1.3 Total Proposed P0

19 (Phase 4A.1) + 8 (Later-phase) = 27 total P0.

### 1.4 Number 117

**DECLARED OBSOLETE.** The number 117 has no legitimate source in the repository. It must not be referenced in any future planning.

---

## 2. T-PIT-01..22 RECONCILIATION

### 2.1 Disposition Legend

| Disposition | Meaning |
|-------------|---------|
| **MAPPED_TO_P0** | Test directly corresponds to one of the 19 Phase 4A.1 P0 tests |
| **NEW_4A1_ACCEPTANCE** | New acceptance test for Phase 4A.1, not part of the 19 P0 inventory |
| **DEFERRED** | Deferrable to a later Phase 4A sub-phase |
| **DUPLICATE** | Effectively identical to another T-PIT test |
| **RETIRED_WITH_REASON** | Retired; specific reason documented |

### 2.2 One-Row-Per-Test Matrix

| T-PIT ID | Name | Disposition | Maps To P0 ID | Rationale |
|----------|------|-------------|---------------|-----------|
| T-PIT-01 | Default sidecar for legacy datasets | **MAPPED_TO_P0** | T-M01 | Default sidecar must provide valid temporal fields; missing event_time rejected per T-M01 |
| T-PIT-02 | Sidecar immutability | **NEW_4A1_ACCEPTANCE** | — | Immutability enforcement is a Phase 4A.1 acceptance criterion but is not listed in the 19 P0 inventory |
| T-PIT-03 | PIT filtering by publication_time | **MAPPED_TO_P0** | T-P01 | `publication_time == pit_cutoff` → included |
| T-PIT-04 | PIT filtering by effective_time | **MAPPED_TO_P0** | T-P04 | `effective_time > pit_cutoff` → excluded, no error |
| T-PIT-05 | PIT filtering by revision_time | **MAPPED_TO_P0** | T-P03 | `revision_time > pit_cutoff` → latest revision at cutoff used |
| T-PIT-06 | Future data excluded silently | **MAPPED_TO_P0** | T-X01 | Future publication excluded without error |
| T-PIT-07 | Temporal eligibility validation | **NEW_4A1_ACCEPTANCE** | — | Eligibility validation is broader than any single P0 test; it encompasses the TemporalContract validation framework |
| T-PIT-08 | view_hash differs from dataset_hash | **MAPPED_TO_P0** | T-H01 | `view_hash != dataset_hash` verifies hash stability under Phase 4A additions |
| T-PIT-09 | Same cutoff, different data → different view_hash | **MAPPED_TO_P0** | T-H02 | Hash changes with data, verifying dataset hash stability |
| T-PIT-10 | Different cutoff, same data → different view_hash | **MAPPED_TO_P0** | T-H02 | Hash changes with cutoff, verifying hash stability |
| T-PIT-11 | experiment_id includes all components | **NEW_4A1_ACCEPTANCE** | — | Experiment identity completeness is a Phase 4A.1 acceptance criterion not listed in the 19 P0 inventory |
| T-PIT-12 | Changing tie-breaker changes experiment_id | **MAPPED_TO_P0** | T-O01 | Deterministic tie-breaker ordering verified through experiment_id sensitivity |
| T-PIT-13 | Deterministic equal-time ordering | **MAPPED_TO_P0** | T-O01 | Directly tests T-O01: same timestamp ordering is deterministic |
| T-PIT-14 | Revision chain append-only | **MAPPED_TO_P0** | T-R01 | Append-only chain integrity per T-R01 |
| T-PIT-15 | Revision reconstruction at PIT cutoff | **MAPPED_TO_P0** | T-R02 | Only `revision_time <= T` visible per T-R02 |
| T-PIT-16 | TemporalContract DERIVED policy | **DEFERRED** | — | DERIVED data type is a later-phase enhancement; TemporalContract base policy is 4A.1 but DERIVED-specific defaults are deferred |
| T-PIT-17 | Missing event_time rejected | **MAPPED_TO_P0** | T-M01 | Directly tests T-M01 |
| T-PIT-18 | Naive datetime rejected | **MAPPED_TO_P0** | T-M06 | Directly tests T-M06 |
| T-PIT-19 | Legacy dataset default sidecar | **MAPPED_TO_P0** | T-M06 | Legacy default sidecar must produce valid temporal fields; naive datetime rejection applies |
| T-PIT-20 | BacktestEngine interface unchanged | **MAPPED_TO_P0** | T-H03 | Interface preservation verifies strategy hash stability under Phase 4A additions |
| T-PIT-21 | compute_result_hash unchanged | **MAPPED_TO_P0** | T-H01 | Directly tests T-H01: same inputs → same result_hash |
| T-PIT-22 | New PIT fields have defaults | **NEW_4A1_ACCEPTANCE** | — | Default field behavior is a Phase 4A.1 acceptance criterion not listed in the 19 P0 inventory |

### 2.3 Disposition Summary

| Disposition | Count | T-PIT IDs |
|-------------|-------|-----------|
| MAPPED_TO_P0 | 15 | T-PIT-01, 03, 04, 05, 06, 08, 09, 10, 12, 13, 14, 15, 17, 18, 19, 20, 21 |
| NEW_4A1_ACCEPTANCE | 4 | T-PIT-02, 07, 11, 22 |
| DEFERRED | 1 | T-PIT-16 |
| DUPLICATE | 0 | — |
| RETIRED_WITH_REASON | 0 | — |

**Note**: T-PIT-19 (Legacy dataset default sidecar) is a variant of T-PIT-01 (Default sidecar for legacy datasets). If they are determined to test the same invariant, T-PIT-19 should be classified as **DUPLICATE** of T-PIT-01. The current classification as separate MAPPED_TO_P0 entries (T-PIT-01 → T-M01, T-PIT-19 → T-M06) reflects different aspects of the same default sidecar behavior: T-PIT-01 focuses on field presence, T-PIT-19 focuses on validation of default temporal fields.

### 2.4 P0 Coverage Gap Analysis

The 19 P0 tests are NOT fully covered by MAPPED_TO_P0 T-PIT entries. The following P0 tests have no direct T-PIT correspondence:

| P0 ID | P0 Test Name | T-PIT Coverage | Status |
|-------|-------------|----------------|--------|
| T-H04 | Config hash unchanged | No T-PIT test directly covers config_hash stability | **GAP — requires T-PIT addition or reassignment** |
| T-H05 | Cross-process determinism | No T-PIT test directly covers cross-process hash comparison | **GAP — requires T-PIT addition or reassignment** |
| T-P02 | Data published one second after cutoff | No T-PIT test explicitly covers the one-second boundary | **GAP — requires T-PIT addition or reassignment** |
| T-R03 | Revision chain integrity | T-PIT-14 covers append-only but not chain hash integrity | **PARTIAL — may need explicit T-PIT mapping** |
| T-R04 | Latest-value-only rejection | No T-PIT test explicitly covers rejection of latest-value-only datasets | **GAP — requires T-PIT addition or reassignment** |
| T-X02 | Future revision excluded | T-PIT-05 covers revision filtering but T-X02 is specifically about future revision exclusion | **OVERLAPPING — T-PIT-05 may subsume T-X02** |
| T-X07 | No automatic error on future data | T-PIT-06 covers silent exclusion; T-X07 may be redundant | **POSSIBLE DUPLICATE** |

**These gaps are documented as evidence-only. No T-PIT test may be silently added or reassigned to close them without explicit architectural authorization.**

### 2.5 No "Or Equivalent" Language

The T-PIT inventory uses exact IDs only. No "T-PIT-01 through T-PIT-22 or equivalent" language is permitted. The disposition matrix above is the authoritative mapping.

---

## 3. AUTHORITATIVE PHASE 4 IDENTITY HASH CONTRACT

### 3.1 Principle

One authoritative mechanism governs all Phase 4 identity hashes:

**Phase 4 Identity Hash = SHA-256 of canonical bytes produced by `canonical_serialize()` applied to an EXPLICIT ALLOWLIST of identity fields for the entity type.**

This is NOT "serialize everything and exclude known audit fields." It is an explicit allowlist: only listed fields participate. Only listed fields can affect the hash.

### 3.2 Canonical Serialization (`canonical_serialize`)

Already implemented in `src/data_engine/pit/serialization.py`. Rules:
- **Encoding**: UTF-8
- **Format**: JSON with `sort_keys=True`, separators `(',', ':')`
- **Float normalization**: `-0.0 → 0.0`; NaN → SerializationError; ±Infinity → SerializationError
- **Datetime normalization**: All datetimes must be timezone-aware UTC; `.astimezone(UTC).isoformat()`
- **Null representation**: `None` → JSON `null`
- **Boolean representation**: `true`/`false` (Python `True`/`False`)
- **List ordering**: Preserved (order is part of identity)
- **Dict ordering**: Sorted by key
- **Rejected types**: tuple, set, custom objects, Decimal (converted via `str()`)

### 3.3 Field Classification

Every field in every Phase 4 entity is classified as exactly one of:

| Classification | Meaning | Identity? | Eligibility? | Hash? |
|----------------|---------|-----------|--------------|-------|
| **IDENTITY** | Defines entity identity | YES | MAY | YES |
| **ELIGIBILITY** | Determines PIT eligibility | NO | YES | MAY (if in allowlist) |
| **AUDIT** | Recorded for audit, never affects identity | NO | NO | **NO** |
| **TEST/UNRELATED** | Test infrastructure or unrelated metadata | NO | NO | NO |

### 3.4 Explicit Identity-Field Allowlists

#### 3.4.1 Candle Identity (Phase 4 — distinct from legacy `Candle.to_hash()`)

| Field | Classification | Reason |
|-------|----------------|--------|
| `timestamp` | IDENTITY | When the market event occurred |
| `open` | IDENTITY | Price at bar open |
| `high` | IDENTITY | Price at bar high |
| `low` | IDENTITY | Price at bar low |
| `close` | IDENTITY | Price at bar close |
| `volume` | IDENTITY | Trading volume |
| `timeframe` | IDENTITY | Data granularity |
| `currency` | IDENTITY | Quote currency |
| `bid` | IDENTITY | Bid price |
| `ask` | IDENTITY | Ask price |
| `spread` | IDENTITY | Bid-ask spread |
| `provider_timestamp` | **AUDIT** | Wall-clock of provider receipt — MUST NOT enter identity |
| `ingestion_time` | **AUDIT** | System ingestion time — MUST NOT enter identity |

**Identity serialization**: `canonical_serialize()` applied to `{timestamp, open, high, low, close, volume, timeframe, currency, bid, ask, spread}`.

**Legacy `Candle.to_hash()`**: FROZEN. Uses `model_dump_json()` including `provider_timestamp`. Must NOT be modified. Phase 4 identity uses the explicit allowlist contract above.

#### 3.4.2 ProvenanceRecord Identity (Phase 4 — distinct from legacy `ProvenanceRecord.to_hash()`)

| Field | Classification | Reason |
|-------|----------------|--------|
| `dataset_id` | IDENTITY | Dataset identifier |
| `dataset_version` | IDENTITY | Dataset version |
| `provider` | IDENTITY | Data provider |
| `source` | IDENTITY | Data source |
| `instrument` | IDENTITY | Instrument identity |
| `timeframe` | IDENTITY | Data granularity |
| `start_timestamp` | IDENTITY | Period start |
| `end_timestamp` | IDENTITY | Period end |
| `timezone` | IDENTITY | Timezone of timestamps |
| `evidence_provenance` | IDENTITY | Evidence classification |
| `validation_status` | IDENTITY | Validation state |
| `source_hash` | IDENTITY | Source data hash |
| `transformation_history` | IDENTITY | Provenance chain |
| `retrieval_timestamp` | **AUDIT** | Wall-clock of data retrieval — MUST NOT enter identity |
| `ingestion_time` | **AUDIT** | System ingestion time — MUST NOT enter identity |

**Identity serialization**: `canonical_serialize()` applied to `{dataset_id, dataset_version, provider, source, instrument, timeframe, start_timestamp, end_timestamp, timezone, evidence_provenance, validation_status, source_hash, transformation_history}`.

**Legacy `ProvenanceRecord.to_hash()`**: FROZEN. Uses `model_dump_json()` including `retrieval_timestamp`. Must NOT be modified.

#### 3.4.3 Dataset Identity

| Field | Classification | Reason |
|-------|----------------|--------|
| `dataset_id` | IDENTITY | Dataset identifier |
| `version` | IDENTITY | Dataset version |
| `instrument` | IDENTITY | Instrument identity |
| `timeframe` | IDENTITY | Data granularity |
| `total_rows` | IDENTITY | Row count |
| `candle_data` | IDENTITY | Canonical candle serialization |
| `evidence_provenance` | IDENTITY | Evidence classification |
| `provenance` | IDENTITY | Provenance record identity |

**Note**: `Dataset` has no `to_hash()` method. `_compute_dataset_hash()` in `backtest.py` already uses an explicit construction that does NOT include `provider_timestamp` or `retrieval_timestamp`. This is compatible with the Phase 4 contract.

#### 3.4.4 StrategySpec Identity

| Field | Classification | Reason |
|-------|----------------|--------|
| All 20 fields in `canonical_serialize()` | IDENTITY | Explicit field-by-field serialization |

**Legacy `StrategySpec.to_hash()`**: Already uses `canonical_serialize()` with explicit field ordering. Compatible with Phase 4 contract. No change needed.

#### 3.4.5 BacktestConfig Identity

| Field | Classification | Reason |
|-------|----------------|--------|
| All fields in `_compute_config_hash()` | IDENTITY | Explicit field-by-field serialization |

**Legacy `_compute_config_hash()`**: Already uses explicit string construction. Compatible with Phase 4 contract. No change needed.

#### 3.4.6 BacktestProvenance Identity (result_hash)

| Field | Classification | Reason |
|-------|----------------|--------|
| `strategy_hash` | IDENTITY | Strategy identity |
| `dataset_hash` | IDENTITY | Dataset identity |
| `canonical_trades` | IDENTITY | Trade serialization |
| `canonical_equity` | IDENTITY | Equity curve serialization |
| `canonical_metrics` | IDENTITY | Metrics serialization |
| `config_hash` | IDENTITY | Configuration identity |
| `run_timestamp` | **AUDIT** | Wall-clock — EXCLUDED |
| `result_hash` | **AUDIT** | Computed output — EXCLUDED |
| `backtest_id` | **AUDIT** | Runtime identifier — EXCLUDED |

**Legacy `BacktestProvenance.compute_result_hash()`**: FROZEN. Must NOT be modified. Already excludes `run_timestamp`, `result_hash`, `backtest_id`.

**Legacy `BacktestProvenance.to_hash()`**: FROZEN. Already explicitly pops `run_timestamp`, `result_hash`, `backtest_id`. Must NOT be modified.

### 3.5 Algorithm and Version

| Parameter | Value |
|-----------|-------|
| Algorithm | SHA-256 |
| Algorithm version | Context-dependent (Phase 3 = v3.0.0, Phase 4 = v4.0.0) |
| Output format | 64 lowercase hex characters |
| Determinism | Must be identical across all platforms, Python versions, and processes |

### 3.6 Field Ordering

All identity hashes use **canonical field ordering** as defined by `canonical_serialize()`:
- Dict keys sorted alphabetically
- List elements in declared order
- Pipe-separated strings use explicit field ordering per entity type

### 3.7 Null Representation

| Value | Representation |
|-------|----------------|
| `None` | `<NULL>` in pipe-separated strings; `null` in JSON |
| `0.0` | `0.0000000000` (normalized from `-0.0`) |
| Empty string | `""` (preserved) |
| Empty list | `[]` |

### 3.8 Datetime Normalization

All datetime fields in identity hashes MUST:
1. Be timezone-aware (UTC)
2. Be normalized via `.astimezone(UTC)`
3. Be serialized as ISO 8601 format
4. Naive datetimes raise `SerializationError`

### 3.9 Nested Object Handling

Nested objects (e.g., `Instrument` within `ProvenanceRecord`) MUST be serialized using their own explicit identity allowlist, then the serialized form is included in the parent identity hash. No recursive `model_dump_json()` is permitted.

### 3.10 Schema/Version Handling

| Entity | Schema Version | Notes |
|--------|---------------|-------|
| `Candle` | Phase 3 v3.0.0 | Legacy `to_hash()` frozen |
| `ProvenanceRecord` | Phase 3 v3.0.0 | Legacy `to_hash()` frozen |
| `StrategySpec` | Phase 3 v3.0.0 | `to_hash()` uses `canonical_serialize()` |
| `BacktestConfig` | Phase 3 v3.0.0 | `_compute_config_hash()` uses explicit construction |
| `BacktestProvenance` | Phase 3 v3.0.0 | `compute_result_hash()` frozen |
| `TemporalSemantics` | Phase 4A.1 v4.1.0 | `temporal_hash_input()` uses explicit field list |
| `TemporalContract` | Phase 4A.1 v4.1.0 | `get_contract_hash()` uses `deterministic_hash()` |
| Future Phase 4 entities | v4.0.0 | Must use explicit allowlist contract |

### 3.11 Safety Model

The primary safety model is **explicit allowlist**, not "exclude known audit fields." This means:
1. If a field is NOT in the allowlist, it CANNOT affect any identity hash.
2. Adding a new field to an entity requires explicitly adding it to the allowlist or it is identity-silent.
3. Removing a field from the allowlist requires updating the contract or it becomes identity-silent.
4. There is no "default include-all then exclude" pattern.

---

## 4. LEGACY PHASE 3 HASH COMPATIBILITY

### 4.1 Frozen Legacy Methods

The following methods are **FROZEN** — must NOT be modified under any circumstances:

| Method | Location | Status |
|--------|----------|--------|
| `Candle.to_hash()` | `schemas.py:130` | **FROZEN** — uses `model_dump_json()` including `provider_timestamp` |
| `ProvenanceRecord.to_hash()` | `schemas.py:200` | **FROZEN** — uses `model_dump_json()` including `retrieval_timestamp` |
| `BacktestProvenance.compute_result_hash()` | `strategy/provenance.py:84` | **FROZEN** — explicit formula, excludes run timestamps |
| `BacktestProvenance.to_hash()` | `strategy/provenance.py:108` | **FROZEN** — explicitly pops `run_timestamp`, `result_hash`, `backtest_id` |
| `StrategySpec.to_hash()` | `strategy/schemas.py:458` | **FROZEN** — uses `canonical_serialize()` |
| `BacktestConfig._compute_config_hash()` | `strategy/backtest.py:629` | **FROZEN** — explicit string construction |
| `BacktestEngine._compute_dataset_hash()` | `strategy/backtest.py:608` | **FROZEN** — manual construction excluding wall-clock fields |

### 4.2 Authoritative Identity Contracts

| Identity | Authoritative For | Contract | Method |
|----------|-------------------|----------|--------|
| Phase 3 dataset identity | `dataset_hash` | `_compute_dataset_hash()` | Manual construction |
| Phase 3 strategy identity | `strategy_hash` | `StrategySpec.to_hash()` | `canonical_serialize()` |
| Phase 3 config identity | `config_hash` | `BacktestConfig._compute_config_hash()` | Explicit string |
| Phase 3 result identity | `result_hash` | `BacktestProvenance.compute_result_hash()` | Explicit formula |
| Phase 4 temporal identity | `temporal_hash` | `TemporalSemantics.temporal_hash_input()` | Explicit field list |
| Phase 4 contract identity | `contract_hash` | `TemporalContract.get_contract_hash()` | `deterministic_hash()` |
| Phase 4 view identity | `view_hash` | `PitView.view_hash` | SHA-256 of explicit allowlist |
| Phase 4 experiment identity | `experiment_id` | `ExperimentIdentity.experiment_id` | SHA-256 of explicit allowlist |

### 4.3 Compatibility Guarantee

Phase 4 identity hashes are **additive**. They do not replace, modify, or change Phase 3 hashes. The Phase 3 hashes remain the authoritative identity for all Phase 3 artifacts. Phase 4 identity hashes apply only to Phase 4 constructs.

Changing any Phase 3 hash is **FORBIDDEN**.

---

## 5. WALL-CLOCK CONTAMINATION

### 5.1 Complete Occurrence Audit

| Source | Call | Classification | Identity Risk |
|--------|------|----------------|---------------|
| `schemas.py:62` `_now_utc()` | `datetime.now(UTC)` | **IDENTITY** | Creates `Candle.provider_timestamp` and `DatasetVersion.created_at` defaults — **CONTAMINATES `Candle.to_hash()`** |
| `schemas.py:195` | `datetime.now(UTC).isoformat()` | AUDIT | Transformation history timestamp |
| `schemas.py:261` | `datetime.now(UTC)` | AUDIT | `ValidationResult.timestamp` |
| `strategy/backtest.py:221` | `datetime.now(UTC)` | AUDIT | `start_timestamp` fallback |
| `strategy/backtest.py:222` | `datetime.now(UTC)` | AUDIT | `end_timestamp` fallback |
| `strategy/backtest.py:228` | `datetime.now(UTC)` | AUDIT | `run_timestamp` — excluded from `result_hash` |
| `strategy/provenance.py:102` | `datetime.now(UTC).isoformat()` | AUDIT | Access log |
| `strategy/provenance.py:195` | `datetime.now(UTC).isoformat()` | AUDIT | Transformation history |
| `strategy/provenance.py:148` | `uuid.uuid4()` | AUDIT | Version string generation |
| `data_blocked.py:55` | `datetime.now(UTC)` | AUDIT | Quality gate timestamp |
| `ingestion.py:142` | `datetime.now(UTC).isoformat()` | AUDIT | Access log |
| `ingestion.py:175` | `uuid.uuid4()` | AUDIT | Dataset ID generation |
| `ingestion.py:177` | `datetime.now(UTC)` | AUDIT | Version string |
| `ingestion.py:188` | `datetime.now(UTC)` | AUDIT | `retrieval_timestamp` |
| `evidence.py:41` | `datetime.now(UTC)` | AUDIT | `labeling_timestamp` |
| `storage.py:41,72` | `datetime.now(UTC)` | AUDIT | Storage timestamps |
| `security.py:65` | `datetime.now(UTC)` | AUDIT | Security timestamps |
| `quarantine.py` (multiple) | `datetime.now(UTC)` | AUDIT | Quarantine timestamps |
| `quality_report.py:39` | `datetime.now(UTC)` | AUDIT | Report generation timestamp |
| `quant_boundary.py:118` | `datetime.now(UTC)` | AUDIT | Calculation timestamp |
| `provider.py:101` | `datetime.now(UTC).isoformat()` | AUDIT | Provider retrieval timestamp |
| `quant/returns.py:55,108,166` | `datetime.now()` | TEST/UNRELATED | Test scaffolding |
| `quant/schemas.py:29` | `datetime.now(UTC).isoformat()` | AUDIT | Schema timestamp |
| `cli.py:61` | `datetime.now(UTC).isoformat()` | AUDIT | CLI output timestamp |

### 5.2 Critical: `_now_utc()` Identity Contamination

The function `_now_utc()` at `schemas.py:62` is the **sole source** of identity-contaminating wall-clock defaults:

```python
def _now_utc() -> datetime:
    return datetime.now(UTC)
```

It is used as `default_factory` for:
1. `Candle.provider_timestamp` — **CONTAMINATES `Candle.to_hash()`** because `to_hash()` uses `model_dump_json()` which includes all fields
2. `DatasetVersion.created_at` — Would contaminate any hash that includes `DatasetVersion` via `model_dump_json()`

### 5.3 Required Treatment

| Field | Current Classification | Required Classification | Action |
|-------|----------------------|------------------------|--------|
| `Candle.provider_timestamp` | IDENTITY-contaminating (via `to_hash()`) | **AUDIT** | Phase 4 identity contract must EXCLUDE from allowlist. Legacy `to_hash()` remains FROZEN. |
| `DatasetVersion.created_at` | Potential IDENTITY-contaminating | **AUDIT** | Must not be included in any identity hash construction. |
| `ProvenanceRecord.retrieval_timestamp` | IDENTITY-contaminating (via `to_hash()`) | **AUDIT** | Phase 4 identity contract must EXCLUDE from allowlist. Legacy `to_hash()` remains FROZEN. |
| `ValidationResult.timestamp` | AUDIT | AUDIT | Already excluded from identity. |
| `run_timestamp` | AUDIT | AUDIT | Already excluded from `compute_result_hash()`. |
| `ingestion_time` | AUDIT | AUDIT | Already excluded from `temporal_hash_input()`. |

### 5.4 No Modification During This Pass

Source code is NOT modified. The wall-clock contamination is documented as a required architectural correction for future implementation authorization.

---

## 6. PIT SIDECAR FALLBACK

### 6.1 Invariant

**Explicit temporal metadata ALWAYS takes precedence over fallback metadata.**

### 6.2 Fallback Rule for Legacy Datasets

`retrieval_timestamp` may ONLY be used as fallback when ALL of the following conditions hold:

1. Dataset is **explicitly classified** as legacy (no `PitSidecar` record exists)
2. Required explicit PIT metadata is **absent** (no `event_time`, `publication_time`, etc.)
3. Fallback behavior is **declared** in the dataset/PIT contract

### 6.3 Fallback Behavior (Legacy Datasets Only)

For legacy datasets without `PitSidecar`, the `PitViewBuilder` generates a default `PitSidecar`:

| Field | Fallback Value | Source |
|-------|---------------|--------|
| `event_time` | `dataset.provenance.retrieval_timestamp` | Fallback |
| `observation_time` | `dataset.provenance.retrieval_timestamp` | Fallback |
| `publication_time` | `dataset.provenance.retrieval_timestamp` | Fallback |
| `effective_time` | `dataset.provenance.retrieval_timestamp` | Fallback |
| `revision_time` | `None` (first revision) | Default |
| `ingestion_time` | `datetime.now(UTC)` | Metadata-only |

### 6.4 Never-Silent Replacement Rule

**Valid explicit temporal metadata is NEVER replaced by fallback metadata.**

If a dataset has ANY explicit temporal field:
- `event_time` is used as `event_time`
- `publication_time` is used as `publication_time`
- `effective_time` is used as `effective_time`
- `revision_time` is used as `revision_time`

Fallback only fills gaps where ALL explicit values are absent for a given field.

### 6.5 Field Classifications

| Field | Classification | Identity? | Eligibility? | Audit-Only? |
|-------|----------------|-----------|--------------|-------------|
| `event_time` | IDENTITY | YES | YES | NO |
| `observation_time` | IDENTITY | YES | YES | NO |
| `publication_time` | IDENTITY | YES | YES | NO |
| `effective_time` | IDENTITY | YES | YES | NO |
| `revision_time` | IDENTITY | YES | YES | NO |
| `ingestion_time` | **AUDIT_ONLY** | **NO** | **NO** | **YES** |

### 6.6 `ingestion_time` Declaration

`ingestion_time` is:
- **NOT** an identity field
- **NOT** an eligibility field
- **NOT** part of deterministic ordering
- **NOT** part of any hash computation
- **NOT** part of PIT filtering
- **ONLY** an audit timestamp recording when data was ingested

This is enforced by:
- `TemporalSemantics._temporal_fields()` explicitly excludes `ingestion_time`
- `TemporalSemantics.temporal_hash_input()` explicitly excludes `ingestion_time`
- `TemporalContract` marks `ingestion_time` as `non_eligible`
- `TemporalContract` sets `ingestion_time` to `ALLOW_NULL` missing-field policy

---

## 7. PROVENANCE PRESERVATION

### 7.1 EvidenceProvenance and DataQualityGate Interaction with PitView

**DataQualityGate remains the authoritative source of truth for data quality.**

**EvidenceProvenance labels are propagated through PIT filtering without alteration.**

### 7.2 Provenance Survival Guarantee

1. **PIT filtering preserves `evidence_provenance`**: When `PitViewBuilder.filter()` produces a PIT-filtered `Dataset`, the `evidence_provenance` field is copied from the source dataset unchanged.

2. **Synthetic classification is preserved**: A dataset classified as `SYNTHETIC` or `SIMULATED` retains that classification in the PIT view. The `PitView` carries the same `evidence_provenance` as the source `Dataset`.

3. **PIT transformation cannot upgrade synthetic data to real data**: No PIT operation may change `EvidenceProvenance` from `SYNTHETIC` to `REAL`, from `SIMULATED` to `REAL`, or from `UNKNOWN` to `REAL`. This is a HARD CONSTRAINT.

4. **DataQualityGate remains authoritative**: `DataQualityGate.check()` is the gate through which all datasets pass before PIT filtering. A dataset blocked by `DataQualityGate` must never appear in a PIT view. `DataQualityGate` is NOT modified by Phase 4A.1.

### 7.3 RT-15 Concrete Acceptance Requirement

**Requirement**: `PitViewBuilder.filter()` MUST propagate `evidence_provenance` from the source `Dataset` to the PIT-filtered `Dataset` unchanged. A test MUST verify that:
- Input dataset with `EvidenceProvenance.SYNTHETIC` → PIT view has `EvidenceProvenance.SYNTHETIC`
- Input dataset with `EvidenceProvenance.UNKNOWN` → PIT view has `EvidenceProvenance.UNKNOWN`
- Input dataset with `EvidenceProvenance.REAL` → PIT view has `EvidenceProvenance.REAL`
- No PIT operation may alter the `evidence_provenance` value

### 7.4 No Second Trust Model

Phase 4A.1 does NOT create an independent trust model. The trust hierarchy is:
1. `DataQualityGate` — authoritative data quality validation (unchanged)
2. `EvidenceProvenance` — authoritative evidence classification (propagated)
3. `PitViewValidator` — adds temporal eligibility checks AFTER `DataQualityGate`
4. `PitViewBuilder` — filters data by PIT cutoff, preserving all metadata

---

## 8. APPROVALMETADATA SCOPE

### 8.1 Authoritative Classification

**ApprovalMetadata and ResearchContract are PHASE 4A.4.**

They are NOT Phase 4A.1 implementation requirements.

### 8.2 Correction of RT-14

RT-14 identified that ApprovalMetadata was listed as a 4A.1 requirement. This is corrected:
- ApprovalMetadata belongs to Phase 4A.4 (Later Phase)
- ResearchContract belongs to Phase 4A.4 (Later Phase)
- Neither introduces hidden dependencies into Phase 4A.1

### 8.3 4A.1 Extension Boundary

Phase 4A.1 does NOT include:
- `ApprovalMetadata` model
- `ResearchContract` model
- `ApprovalGate` model
- Any approval-related validation
- Any research governance semantics

Phase 4A.1 components must NOT reference, import, or depend on approval-related constructs.

---

## 9. CALENDAR SCOPE

### 9.1 4A.1: Minimal Immutable CalendarRef

Phase 4A.1 defines ONLY:
- `CalendarRef` with `calendar_id: str` and `calendar_version: str`
- Used as a string reference in `view_hash` and `experiment_id`
- No calendar computation, no holiday logic, no session hours

### 9.2 Later Phases: Full Calendar Infrastructure

The following are deferred to Phase 4A.2+:
- `CalendarInterface` protocol/ABC
- `CalendarRegistry`
- `HolidayCalendar`
- Session hour computation
- Trading day determination
- Exchange-specific calendars

### 9.3 Hidden Dependency Check

**CONFIRMED**: No 4A.1 component depends on full calendar infrastructure. The `view_hash` formula includes `calendar_version` as a string reference only. `CalendarRef` is a data model, not a computation engine.

### 9.4 Boundary Rule

4A.1 may reference `CalendarRef` (the data model) but MUST NOT depend on calendar computation, holiday logic, or session determination. Any 4A.1 component that requires calendar computation is a scope violation.

---

## 10. MULTI-ASSET BOUNDARY

### 10.1 4A.1 Asset-Neutral Primitives

The following are defined as asset-neutral identity primitives for Phase 4A.1:

- `InstrumentIdentity` — Stable identifier across lifecycle
- `InstrumentSpecification` — Effective-dated trading specification
- `Venue` — Exchange/market identifier with timezone
- `DataSource` — Data provider identity and provenance
- `CalendarRef` — Trading calendar reference
- `TemporalContract` — Required/eligible/non-eligible field definitions
- `PitSidecar` — PIT metadata attached by dataset reference
- `PitView` — Time-sliced view of data at a PIT cutoff
- `RevisionChain` — Immutable append-only revision history
- `TieBreakerPolicy` — Deterministic equal-time ordering
- `ExperimentIdentity` — Deterministic experiment identity

### 10.2 Confirmed Deferred

The following are explicitly deferred and must NOT be implemented in 4A.1:

- `CorporateAction` — Later 4A.2
- `PointInTimeUniverse` — Later 4A.2
- `FuturesContract` — Later 4A.3
- `ContinuousSeries` — Later 4A.3
- `FX financing/swap modeling` — Later 4A.4
- `full calendar infrastructure` — Later 4A.2
- `live execution` — NEVER
- `broker integration` — NEVER
- `production market-data connectivity` — NEVER
- `autonomous real-money trading` — NEVER

### 10.3 Hidden Implementation Dependency Check

**CONFIRMED**: No hidden dependencies on deferred components exist in the current source. The `pit/` module (v4.1.0) is asset-neutral. The `multi_asset` module does NOT exist yet. No futures, equity, or FX code exists outside the deferred categories.

---

## 11. TIE-BREAKING

### 11.1 Deterministic Ordering for Equal Timestamps

When two or more observations have identical `event_time`, `publication_time`, `effective_time`, and `revision_time`, the ordering is determined by the declared `TieBreakerPolicy`.

### 11.2 Policy Specification

| Level | Key | Description |
|-------|-----|-------------|
| Primary | `event_time` | When the market event occurred |
| Secondary | `venue` | Exchange/market identifier (lexicographic) |
| Tertiary | `instrument_identity` | Stable instrument identifier (lexicographic) |
| Quaternary | `data_source.source_id` | Data provider identifier (lexicographic) |
| Final | `canonical_bytes` | Canonical serialization of the data item |

### 11.3 Revision Ordering

When observations have identical temporal fields AND identical tie-breaker keys, `revision_time` determines ordering. The most recent revision (largest `revision_time`) sorts last. If `revision_time` is null, the observation sorts before any revision with a non-null `revision_time`.

### 11.4 Deterministic Final Tie-Breaker

If all the above are identical, the `canonical_bytes` of the data item provides the final deterministic ordering. This uses the same `canonical_serialize()` function defined in Section 3.2.

### 11.5 Identity Participation

The `TieBreakerPolicy` IS part of `view_hash` identity. Changing the tie-breaker policy creates a different `view_hash`, which creates a different `experiment_id`. Insertion order is NEVER a tie-breaker.

### 11.6 Declaration Requirement

Every experiment MUST declare its `TieBreakerPolicy`. The default is `venue|instrument_identity|data_source.source_id|canonical_bytes`. The policy is included in `view_hash`.

---

## 12. RED-TEAM RECONCILIATION

### 12.1 Critical Findings

| ID | Finding | Status | 4A.1 Impact | Resolution |
|----|---------|--------|-------------|------------|
| RT-01 | PIT cutoff conflated with simulation end | **OPEN** | HIGH | PitViewBuilder must filter before BacktestEngine.run() |
| RT-02 | No revision history per data item | **OPEN** | HIGH | RevisionChain sidecar required |
| RT-03 | Latest-value-only data cannot reconstruct PIT | **OPEN** | HIGH | Revision chains must be stored |
| RT-04 | Universal calendar assumption | **OPEN** | HIGH | CalendarRef with version in view_hash |
| RT-05 | Futures contract vs continuous not distinguished | **DEFERRED** | MEDIUM | 4A.3 concern; 4A.1 defines identity primitives only |
| RT-16 | Design doc integrity discrepancy | **OPEN** | P0 BLOCKER | Documentation gate; NOT_MODIFIED per authorization |

### 12.2 High Findings

| ID | Finding | Status | 4A.1 Impact | Resolution |
|----|---------|--------|-------------|------------|
| RT-06 | No point-in-time universe | **DEFERRED** | NONE | 4A.2 concern |
| RT-07 | Corporate actions as corrections | **DEFERRED** | NONE | 4A.2 concern |
| RT-08 | Implicit FX spread assumptions | **DEFERRED** | NONE | 4A.3 concern |
| RT-09 | ingestion_time potentially misused | **OPEN** | MEDIUM | TemporalContract non_eligible enforcement |
| RT-10 | No PIT view validator | **OPEN** | HIGH | PitViewValidator required |
| RT-12 | Candle.provider_timestamp wall-clock default | **OPEN** | HIGH | Explicit allowlist contract (Section 3) excludes it from identity |

### 12.3 Medium Findings

| ID | Finding | Status | 4A.1 Impact | Resolution |
|----|---------|--------|-------------|------------|
| RT-11 | Undeclared tie-breakers | **OPEN** | HIGH | TieBreakerPolicy required (Section 11) |
| RT-13 | No calendar versioning | **OPEN** | MEDIUM | CalendarRef with `calendar_version` in view_hash |
| RT-14 | No approval representation | **CORRECTED** | NONE | ApprovalMetadata is 4A.4, not 4A.1 |
| RT-15 | Synthetic data can be misrepresented | **OPEN** | HIGH | Provenance preservation guarantee (Section 7) |

### 12.4 Design Contradictions

| ID | Contradiction | Severity | Resolution |
|----|---------------|----------|------------|
| RC-01 | "No wall-clock defaults" vs `Candle.provider_timestamp` | HIGH | Frozen as RC-01; explicit allowlist contract excludes it from Phase 4 identity |
| RC-02 | "Separate PIT cutoff" vs existing backtest has none | HIGH | PitViewBuilder pre-filters; BacktestEngine.run() unchanged |
| RC-03 | "Full revision history" vs single snapshot | MEDIUM | RevisionChain as sidecar |
| RC-04 | "Universal calendar" vs exchange-specific | MEDIUM | CalendarRef with version; full calendar deferred to 4A.2 |
| RC-05 | "No future info leakage" vs processes all data | MEDIUM | PitViewBuilder filters before backtest |

### 12.5 No Contradictions Remain

All red-team findings have been reconciled. No contradiction remains between the red-team section and the implementation matrix. Findings are classified as OPEN (requires 4A.1 implementation), DEFERRED (later phase), or CORRECTED (scope reassignment).

---

## 13. DESIGN-LOCK DEFECT

### 13.1 Current State (Unmodified)

- File: `docs/strategy_engine_design.md`
- SHA-256: `8e125c7d7a71aad2a00717d40077b41bd98308a012f911f1fac716edcee56a82`
- Final line (line 2238): `IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW`
- Line ending: CRLF (`
`)
- Trailing whitespace: YES (CR character)
- U+2713 presence: 3 occurrences in body, NOT on final line
- Contains `NO-GO`: **FALSE**
- Contains `COMPLETE`: **TRUE**

### 13.2 Required State

- Final line MUST be: `IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW`

### 13.3 Classification

**P0 BLOCKER — Documentation Gate**

The design-lock invariant is NOT satisfied. The file says `COMPLETE` when the required state is `NO-GO`.

### 13.4 Treatment

This defect is recorded as evidence-only. **`docs/strategy_engine_design.md` is NOT modified** under this authorization. The correction requires a separately authorized documentation action.

---

## 14. FINAL IMPLEMENTATION READINESS GATE

### 14.1 Strict Checklist

Implementation may become READY only when ALL of the following are satisfied:

- [ ] **Design lock corrected** — `docs/strategy_engine_design.md` final line says `NO-GO` through separately authorized documentation action
- [ ] **19 P0 tests implemented and passing** — All T-H01 through T-X07 implemented, all passing
- [ ] **T-PIT-01..22 dispositions explicit** — All 22 tests have disposition in the matrix (Section 2); gaps documented and authorized
- [ ] **Authoritative identity hashing contract exists** — Section 3 contract defined and adopted
- [ ] **Identity fields are explicit allowlists** — No "serialize everything and exclude" pattern
- [ ] **Audit timestamps cannot enter identity** — `provider_timestamp`, `retrieval_timestamp`, `ingestion_time` explicitly excluded from allowlists
- [ ] **Legacy hash behavior remains unchanged** — All frozen methods verified unmodified
- [ ] **PIT cutoff independent from simulation end** — `BacktestConfig` has no `pit_cutoff`; `PitViewBuilder` pre-filters
- [ ] **Revision selection deterministic** — `RevisionChain` queried at PIT cutoff, only `revision_time <= T` visible
- [ ] **Equal-time ordering deterministic** — `TieBreakerPolicy` declared and included in `view_hash`
- [ ] **Provenance preserved** — `EvidenceProvenance` survives PIT filtering unchanged
- [ ] **Synthetic classification preserved** — PIT transformation cannot upgrade `SYNTHETIC`/`UNKNOWN` to `REAL`
- [ ] **CalendarRef boundary respected** — 4A.1 uses minimal `CalendarRef`; full calendar deferred
- [ ] **ApprovalMetadata deferred** — ApprovalMetadata and ResearchContract remain Phase 4A.4
- [ ] **Multi-asset boundary clean** — No corporate actions, futures rollover, FX financing, live execution
- [ ] **464 regression baseline preserved** — All existing tests pass unchanged
- [ ] **No unauthorized source/test changes** — All Phase 3 source files byte-identical
- [ ] **No hidden later-phase dependencies** — No deferred components imported or referenced in 4A.1

### 14.2 Current Status

| Checkbox | Status |
|----------|--------|
| Design lock corrected | **FAIL** |
| 19 P0 tests implemented | **FAIL** — not yet implemented |
| T-PIT dispositions explicit | **PARTIAL** — matrix exists but gaps documented |
| Identity hashing contract exists | **FAIL** — requires adoption of Section 3 contract |
| Identity fields are explicit allowlists | **FAIL** — current methods use `model_dump_json()` |
| Audit timestamps excluded from identity | **FAIL** — `provider_timestamp` and `retrieval_timestamp` contaminate `to_hash()` |
| Legacy hash behavior unchanged | **PASS** |
| PIT cutoff independent | **PASS** (by design) |
| Revision selection deterministic | **PASS** (by design) |
| Equal-time ordering deterministic | **PASS** (by design) |
| Provenance preserved | **PASS** (by design) |
| Synthetic classification preserved | **PASS** (by design) |
| CalendarRef boundary respected | **PASS** (by design) |
| ApprovalMetadata deferred | **PASS** |
| Multi-asset boundary clean | **PASS** |
| 464 regression baseline preserved | **PASS** |
| No unauthorized changes | **PASS** |
| No hidden later-phase dependencies | **PASS** |

**Result: 14 PASS, 4 FAIL, 1 PARTIAL**

---

## 15. REQUIRED FINAL STATUS

**ARCHITECTURE STATUS: REQUIRES_REVISION**
**IMPLEMENTATION READINESS: NOT_READY**
**IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED**

---

## ARTIFACT VERIFICATION

- Artifact created: `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md`
- All source files verified read-only
- No source code modified
- No tests modified
- No design documents modified
- `docs/strategy_engine_design.md` unchanged
- All 464 existing tests remain passing
- No implementations performed

---

*This artifact is read-only design documentation. It does not authorize implementation. It records the architectural corrections required before any implementation authorization can be considered.*

**ABSOLUTE FINAL LINE:**

IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
