# PHASE 4A.1 IMPLEMENTATION SPECIFICATION

**Version:** 1.0.0
**Date:** 2026-09-29
**Mode:** DESIGN/SPECIFICATION PASS ONLY
**Authorization:** NOT_AUTHORIZED FOR IMPLEMENTATION
**Branch:** `phase-4a/4a1-temporal-foundation`
**HEAD Commit:** `13fdc7ee55a022a9be36ad910e524dcfa429954c`

---

## 1. EXECUTIVE SUMMARY

This specification defines the exact implementation scope for Phase 4A.1 — Point-in-Time Research Foundation. It is derived from the verified forensic reconciliation and architecture documents.

**Scope Boundary:**
- **REQUIRED for 4A.1:** 13 minimal foundation primitives
- **DEFERRED full domain functionality:** Full multi-asset systems (corporate actions, futures, FX, calendar computation, etc.) remain deferred to later phases
- **OUT OF SCOPE:** Live execution, broker integration, real-money trading, production market-data connectivity

**Identity Architecture:**
- Phase 4 identity uses explicit field allowlists + canonical_serialize() + deterministic_hash()
- NO to_deterministic_hash() methods added to Phase 3 models
- Phase 3 hashes remain frozen

**The 13 Required Primitives:**
1. InstrumentIdentity (minimal identity reference)
2. InstrumentSpecification (minimal specification reference)
3. Venue (minimal venue reference)
4. DataSource (minimal source reference)
5. CalendarRef (minimal calendar reference)
6. PitSidecar (temporal metadata snapshot)
7. RevisionChain (revision history)
8. TieBreakerPolicy (deterministic ordering)
9. PitView (PIT-filtered view)
10. PitViewBuilder (view construction)
11. PitViewValidator (view validation)
12. ExperimentIdentity (experiment hash)
13. PitExperimentConfig (experiment configuration)

**Implementation Order:** Dependency-ordered, 9 steps from foundation to acceptance gate.

---

## 2. PHASE 4A.1 BOUNDARY

### 2.1 REQUIRED FOR PHASE 4A.1 — 13 MINIMAL FOUNDATION PRIMITIVES

Phase 4A.1 requires 13 minimal immutable contracts for deterministic identity, reproducibility, PIT view construction, provenance representation, and experiment identity.

These are minimal identity/reference primitives. They do NOT imply implementation of the full multi-asset domain systems.

#### Asset / Reference Identity Primitives (5)

| Component | Responsibility | Authority |
|-----------|----------------|-----------|
| **InstrumentIdentity** | Minimal immutable instrument identity reference | BLOCKER_RESOLUTION_SPEC.md §3.4.9, §9.1 |
| **InstrumentSpecification** | Minimal instrument specification reference for reproducibility | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-12 |
| **Venue** | Minimal immutable venue reference | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-09 |
| **DataSource** | Minimal immutable data source reference | BLOCKER_RESOLUTION_SPEC.md §9.1 |
| **CalendarRef** | Minimal immutable calendar reference | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-01, UQ-05 |

#### PIT / Temporal Primitives (3)

| Component | Responsibility | Authority |
|-----------|----------------|-----------|
| **PitSidecar** | Immutable temporal metadata snapshot for a dataset version | BLOCKER_RESOLUTION_SPEC.md §3.4.6, §9.1 |
| **RevisionChain** | Append-only revision history tracking | BLOCKER_RESOLUTION_SPEC.md §3.4, §9.1 |
| **TieBreakerPolicy** | Deterministic ordering for equal-time observations | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-12 |

#### PIT View Layer (3)

| Component | Responsibility | Authority |
|-----------|----------------|-----------|
| **PitView** | Immutable PIT-filtered dataset representation | BLOCKER_RESOLUTION_SPEC.md §9.1 |
| **PitViewBuilder** | Constructs PitView from Dataset + cutoff | BLOCKER_RESOLUTION_SPEC.md §9.1 |
| **PitViewValidator** | Validates PitView correctness | BLOCKER_RESOLUTION_SPEC.md §9.1 |

#### Experiment Identity/Configuration (2)

| Component | Responsibility | Authority |
|-----------|----------------|-----------|
| **ExperimentIdentity** | Deterministic experiment identity hash | BLOCKER_RESOLUTION_SPEC.md §3.4.8, §9.1 |
| **PitExperimentConfig** | Configuration for PIT-aware experiments | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 2.2 MINIMAL PRIMITIVE VS FULL DOMAIN SYSTEM DISTINCTION

**CRITICAL DISTINCTION:**

Each of the 13 primitives above is a MINIMAL IMMUTABLE CONTRACT required for deterministic identity and reproducibility. This is NOT the same as implementing the full domain functionality.

#### InstrumentIdentity

**Required in 4A.1 (Minimal Primitive):**
- Immutable instrument identity reference
- Identity fields: `stable_identifier`, `asset_class`, `contract_type`
- Schema version: Phase 4A.1 v4.0.0
- Hash algorithm: SHA-256
- Hash version: v4.0.0

**Deferred to Later Phases:**
- Universe management
- Instrument discovery
- Corporate-action modeling
- Futures lifecycle
- Continuous contracts
- Advanced asset-class behavior
- Symbol history tracking
- Venue history tracking

**Authority:** BLOCKER_RESOLUTION_SPEC.md §3.4.9

#### InstrumentSpecification

**Required in 4A.1 (Minimal Primitive):**
- Immutable instrument specification reference
- Required for: deterministic instrument identity, PIT reproducibility, experiment/view identity, schema/version tracking
- Included in view_hash per UQ-12

**Deferred to Later Phases:**
- Futures contract lifecycle
- Rollover logic
- Corporate actions
- Continuous futures
- FX financing
- Advanced contract semantics
- Exchange-specific contract parameters
- Lot size/contract multiplier

**Authority:** BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-12

#### Venue

**Required in 4A.1 (Minimal Primitive):**
- Immutable venue reference
- Required for: stable venue identity, deterministic serialization, reproducibility/provenance reference
- Identity fields: `venue_id`, `venue_name`, `timezone`

**Deferred to Later Phases:**
- Broker integration
- Order routing
- Execution
- Live market connectivity
- Venue session engine
- is_trading_day() calculation
- get_session_hours()
- Holiday calendar integration
- Exchange session generation

**Authority:** BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-09

#### DataSource

**Required in 4A.1 (Minimal Primitive):**
- Immutable data source reference
- Required for: source identity, source/version reference, deterministic provenance representation

**Deferred to Later Phases:**
- Production market-data connectivity
- Live streaming
- Vendor APIs
- Automated ingestion infrastructure
- Endpoint configuration
- API key management
- Rate limiting

**Authority:** BLOCKER_RESOLUTION_SPEC.md §9.1

#### CalendarRef

**Required in 4A.1 (Minimal Primitive):**
- Immutable calendar reference
- Required for: immutable calendar identity, calendar version, deterministic reproducibility reference
- Included in view_hash per UQ-12
- Identity fields: `calendar_id`, `calendar_version`, `calendar_source`

**Deferred to Later Phases:**
- Holiday calculation
- is_trading_day()
- Session generation
- Exchange-hours engine
- Calendar registry
- Full timezone/session infrastructure

**Authority:** BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-01, UQ-05

### 2.3 EXPLICITLY DEFERRED (Not in Any Phase 4A Scope)

| Feature | Target | Rationale |
|---------|--------|-----------|
| CorporateAction | 4A.2+ | Equity-specific, requires multi-asset infrastructure |
| Full equity corporate-action engine | 4A.2+ | Out of scope |
| FuturesContract | 4A.3 | Futures-specific |
| ContinuousSeries | 4A.3 | Futures rollover requires futures contracts first |
| Futures rollover engine | 4A.3 | Requires FuturesContract |
| FX financing/swap model | 4A.2+ | FX-specific |
| Full calendar registry | 4A.2+ | Calendar infrastructure deferred (minimal CalendarRef is in 4A.1) |
| Holiday calendar engine | 4A.2+ | Requires CalendarRef minimal primitive (in 4A.1) + full calendar infrastructure |
| ResearchContract | 4A.2+ | UQ-04 resolved as later-phase research governance |
| ApprovalMetadata | 4A.2+ | Research governance deferred |
| Live execution | OUT OF SCOPE | Phase 4A is research-only |
| Broker integration | OUT OF SCOPE | Phase 4A is research-only |
| Real-money trading | OUT OF SCOPE | Phase 4A is research-only |
| Production market-data connectivity | OUT OF SCOPE | Phase 4A uses existing datasets |
| Autonomous live trading | OUT OF SCOPE | Phase 4A is research-only |
| Automated strategy optimization | OUT OF SCOPE | Phase 4A is research-only |

### 2.4 SUMMARY

- **REQUIRED for 4A.1:** 13 minimal foundation primitives
- **DEFERRED full domain functionality:** The full multi-asset systems (corporate actions, futures, FX, calendar computation, etc.) remain deferred
- **OUT OF SCOPE:** Live execution, broker integration, real-money trading, production connectivity

---

## 3. EXISTING FOUNDATION — KEEP

### 3.1 Modules Retained Unchanged

| Module | Status | Responsibility |
|--------|--------|----------------|
| `pit/temporal.py` | KEEP | TemporalSemantics, TemporalDataType — complete |
| `pit/availability.py` | KEEP | AvailabilityPolicy, PublicationControlledAvailability, RevisionAwareAvailability — complete |
| `pit/contract.py` | KEEP | TemporalContract, MissingFieldPolicy — complete |
| `pit/hashing.py` | KEEP | deterministic_hash(), deterministic_hash_bytes(), verify_hash_determinism(), verify_cross_process_hash() — complete |
| `pit/serialization.py` | KEEP | canonical_serialize(), SerializationError — complete |
| `pit/__init__.py` | KEEP | Package exports, version 4.1.0 |

### 3.2 What Remains Unchanged

- All temporal field definitions
- All availability policy logic
- All contract validation logic
- All hashing primitives
- All serialization logic
- All test functions in tests/test_pit.py (97 tests)

### 3.3 What May Be Extended

- `TemporalSemantics` may receive additional helper methods for sidecar construction
- `TemporalContract` may receive predefined contract instances for each TemporalDataType
- `AvailabilityPolicy` may be used by PitViewBuilder for filtering decisions

### 3.4 Dependency Relationships

```
New Phase 4A.1 Components
        ↓
Existing PIT Foundation
        ↓
Phase 3 Schemas (Dataset, Candle, ProvenanceRecord, etc.)
        ↓
Phase 3 Strategy (BacktestEngine, StrategySpec, BacktestConfig, etc.)
```

---

## 4. AUTHORITATIVE IDENTITY CONTRACT

### 4.1 Phase 4 Identity Architecture

```text
PHASE 4 IDENTITY CONTRACT
        ↓
explicit POSITIVE field allowlist (defined per entity type)
        ↓
canonical_serialize(allowlist_dict)
        ↓
deterministic_hash(serialized_bytes)
        ↓
PHASE 4 IDENTITY HASH (64-char hex)
```

### 4.2 Design Principles

1. **Positive allowlists only:** Identity is defined by what IS included, not by what is excluded
2. **No Phase 3 modification:** Candle.to_hash(), ProvenanceRecord.to_hash(), etc. remain unchanged
3. **No to_deterministic_hash() methods:** Composition over modification
4. **Version visibility:** Identity changes must be intentional and version-visible
5. **Deterministic:** Same inputs → same identity hash across processes and machines

### 4.3 Identity Field Classification

For every field in every entity, classify as exactly one of:

| Classification | Meaning |
|----------------|---------|
| **IDENTITY** | Participates in identity hash |
| **ELIGIBILITY_ONLY** | Used for PIT eligibility, not identity |
| **AUDIT_ONLY** | Metadata only, excluded from identity and eligibility |
| **DISPLAY_ONLY** | Human-readable, excluded from all computations |

---

## 5. IDENTITY FIELD ALLOWLISTS

### 5.1 Dataset Identity (Phase 3, frozen)

**Source:** BacktestEngine._compute_dataset_hash()

| Field | Classification |
|-------|----------------|
| dataset_id | IDENTITY |
| version.version | IDENTITY |
| version.instrument.symbol | IDENTITY |
| version.timeframe | IDENTITY |
| len(candles) | IDENTITY |
| candle data (timestamp, OHLCV) | IDENTITY |
| evidence_provenance | IDENTITY |
| provenance.retrieval_timestamp | ELIGIBILITY_ONLY (NOT identity) |

**Excluded from identity:**
- provider_timestamp (Candle) — AUDIT_ONLY for identity purposes
- transformation_history timestamps — AUDIT_ONLY

### 5.2 PIT Sidecar Identity

**Source:** PitSidecar model (new)

| Field | Classification |
|-------|----------------|
| dataset_id | IDENTITY |
| dataset_version | IDENTITY |
| schema_version | IDENTITY |
| event_time | IDENTITY |
| observation_time | IDENTITY |
| publication_time | IDENTITY |
| effective_time | IDENTITY |
| revision_time | IDENTITY |
| missing_field_policy | IDENTITY |
| temporal_contract_hash | IDENTITY |
| created_at | AUDIT_ONLY |

**Excluded from identity:**
- ingestion_time — AUDIT_ONLY

### 5.3 PIT View Identity

**Source:** PitView model (new)

| Field | Classification |
|-------|----------------|
| dataset_id | IDENTITY |
| dataset_version | IDENTITY |
| pit_cutoff | IDENTITY |
| sidecar_schema_version | IDENTITY |
| view_hash | IDENTITY |
| filtered_row_count | IDENTITY |
| filtering_timestamp | AUDIT_ONLY |

**Excluded from identity:**
- All runtime timestamps except pit_cutoff (which is an input parameter, not wall-clock)

### 5.4 Revision Identity

**Source:** RevisionChain element (new)

| Field | Classification |
|-------|----------------|
| revision_id | IDENTITY |
| parent_revision_id | IDENTITY |
| revision_time | IDENTITY |
| dataset_id | IDENTITY |
| dataset_version | IDENTITY |
| revision_data_hash | IDENTITY |

**Excluded from identity:**
- ingestion_time — AUDIT_ONLY

### 5.5 Feature Identity

**Source:** QuantEngine feature output (existing, unchanged)

| Field | Classification |
|-------|----------------|
| feature_name | IDENTITY |
| dataset_id | IDENTITY |
| dataset_version | IDENTITY |
| calculation_version | IDENTITY |
| values | IDENTITY |

### 5.6 Experiment Identity

**Source:** ExperimentIdentity (new)

| Field | Classification |
|-------|----------------|
| strategy_id | IDENTITY |
| strategy_version | IDENTITY |
| strategy_hash | IDENTITY |
| dataset_id | IDENTITY |
| dataset_version | IDENTITY |
| dataset_hash | IDENTITY |
| pit_view_hash | IDENTITY |
| config_hash | IDENTITY |
| tie_breaker_name | IDENTITY |
| tie_breaker_version | IDENTITY |
| code_version | IDENTITY |
| quant_engine_version | IDENTITY |
| backtest_engine_version | IDENTITY |

**Excluded from identity:**
- run_timestamp — AUDIT_ONLY
- approval_timestamp — AUDIT_ONLY
- ingestion_time — AUDIT_ONLY

### 5.7 Instrument Identity (Deferred to 4A.2)

For reference only — not implemented in 4A.1:

| Field | Classification |
|-------|----------------|
| symbol | IDENTITY |
| asset_class | IDENTITY |
| base_asset | IDENTITY |
| quote_asset | IDENTITY |
| venue | IDENTITY (when implemented) |
| contract_type | IDENTITY |

### 5.8 Configuration Identity

**Source:** BacktestConfig._compute_config_hash() (existing, frozen)

| Field | Classification |
|-------|----------------|
| initial_capital | IDENTITY |
| cost_parameters_serialized | IDENTITY |
| slippage_parameters_serialized | IDENTITY |
| allow_short | IDENTITY |
| execution_semantics | IDENTITY |
| max_position_size | IDENTITY |
| seed | IDENTITY |
| execution_delay | IDENTITY |
| max_exposure_pct | IDENTITY |

---

## 6. HASH VERSIONING

### 6.1 Version Components

| Component | Value | Meaning |
|-----------|-------|---------|
| Algorithm | SHA-256 | Fixed — never changes |
| Serialization Version | 1 | canonical_serialize() format version |
| Schema Version | Per-model | PitSidecar.schema_version, PitView.schema_version, etc. |
| Identity Contract Version | 1 | Allowlist contract version |

### 6.2 Version Change Behavior

| Change Type | Action Required |
|-------------|-----------------|
| Field added to allowlist | Increment schema_version; identity hash changes intentionally |
| Field removed from allowlist | Increment schema_version; identity hash changes intentionally |
| Serialization format changes | Increment serialization_version; all identities invalidated |
| Schema structure changes | Increment schema_version; old versions remain valid for their data |
| Policy changes (e.g., tie-breaker) | New identity; old experiments retain old identity |

### 6.3 Identity Immutability

Once computed, an identity hash MUST NOT change. If the underlying data or allowlist changes, a new identity is created — the old identity remains valid for its original context.

---

## 7. TEMPORAL MODEL

### 7.1 Field Semantics

| Field | Meaning | Identity Role | Eligibility Role | Ordering Role | Audit Role |
|-------|---------|---------------|------------------|---------------|------------|
| **event_time** | Time the event actually occurred | IDENTITY (if present) | PRIMARY eligibility criterion | SECONDARY ordering key | NO |
| **observation_time** | Time the observation was recorded | IDENTITY (if present) | Eligibility criterion | SECONDARY ordering key | NO |
| **publication_time** | Time data was published/made available | IDENTITY (if present) | PRIMARY availability criterion | PRIMARY cutoff criterion | NO |
| **effective_time** | Time data becomes effective/applicable | IDENTITY (if present) | Eligibility criterion | SECONDARY cutoff criterion | NO |
| **revision_time** | Time this specific version was revised | IDENTITY (if present) | Revision availability criterion | PRIMARY revision ordering | NO |
| **ingestion_time** | Metadata-only ingestion timestamp | NEVER | NEVER | NEVER | YES — audit only |

### 7.2 Ingestion Time Prohibition

**ingestion_time = AUDIT ONLY**

It MUST NOT control:
- PIT eligibility — excluded from temporal_hash_input()
- Identity — excluded from all identity allowlists
- Revision ordering — not used in tie-breaking or sequencing

### 7.3 Temporal Field Requirements by DataType

| DataType | Required Fields | Optional Fields |
|----------|-----------------|-----------------|
| OHLCV | event_time, observation_time | publication_time, effective_time, revision_time |
| ECONOMIC | event_time, publication_time | effective_time, revision_time |
| NEWS | event_time, publication_time | revision_time |
| DERIVED | (none required) | event_time, observation_time, publication_time, effective_time, revision_time |

---

## 8. LEGACY FALLBACK

### 8.1 Precedence Rule

```text
EXPLICIT PIT METADATA
        >
LEGACY FALLBACK
```

Explicit metadata MUST NEVER be silently overwritten by fallback values.

### 8.2 Legacy Fallback Source

For legacy datasets lacking explicit PIT metadata:

| Field | Fallback Source |
|-------|-----------------|
| event_time | dataset.provenance.retrieval_timestamp |
| observation_time | dataset.provenance.retrieval_timestamp |
| publication_time | dataset.provenance.retrieval_timestamp |
| effective_time | dataset.provenance.retrieval_timestamp |
| revision_time | dataset.provenance.retrieval_timestamp |
| ingestion_time | datetime.now(UTC) — metadata only |

### 8.3 Fallback Application

- Fallback applies ONLY when no explicit PIT sidecar exists for the dataset
- Default sidecar is generated by PitViewBuilder on first access
- Default sidecar is cached for subsequent accesses
- Fallback fields are marked with missing_field_policy = REJECT for event_time

---

## 9. PIT CUTOFF SEMANTICS

### 9.1 Publication Time

| Condition | Behavior |
|-----------|----------|
| publication_time < pit_cutoff | INCLUDED |
| publication_time == pit_cutoff | INCLUDED |
| publication_time > pit_cutoff | EXCLUDED — no error |

### 9.2 Effective Time

| Condition | Behavior |
|-----------|----------|
| effective_time <= pit_cutoff | INCLUDED |
| effective_time > pit_cutoff | EXCLUDED — no error |

### 9.3 Revision Time

| Condition | Behavior |
|-----------|----------|
| revision_time <= pit_cutoff | INCLUDED (visible) |
| revision_time > pit_cutoff | EXCLUDED (not visible) — use latest revision at or before cutoff |

### 9.4 Event Time

| Condition | Behavior |
|-----------|----------|
| event_time <= pit_cutoff | INCLUDED |
| event_time > pit_cutoff | EXCLUDED — no error |

### 9.5 Observation Time

| Condition | Behavior |
|-----------|----------|
| observation_time <= pit_cutoff | INCLUDED |
| observation_time > pit_cutoff | EXCLUDED — no error |

### 9.6 Cutoff Equality Convention

For ALL temporal fields, **equality (==) is INCLUDED**. The cutoff represents the latest time included, not the first time excluded.

---

## 10. REVISION CHAIN

### 10.1 RevisionChain Structure

```
RevisionChain
    ↓
revision_id (UUID-like deterministic identifier)
    ↓
parent_revision_id (None for first revision)
    ↓
revision_time (UTC-aware datetime)
    ↓
revision_data_hash (identity hash of revision content)
    ↓
dataset_id
    ↓
dataset_version
```

### 10.2 Revision Sequence

- Revisions are append-only: new revisions append, never modify existing
- Each revision references its parent (None for the first)
- Revision order is determined by revision_time, then by insertion sequence for equal times
- Revisions form a directed acyclic graph (DAG) with single-parent default

### 10.3 Revision Identity

Each revision has a deterministic identity hash computed from:
- revision_time
- revision content hash
- parent revision identity (if any)
- dataset_id + dataset_version

### 10.4 Latest Eligible Revision

At PIT cutoff T:
- Find all revisions with revision_time <= T
- Return the revision with the latest revision_time
- If multiple revisions have the same latest revision_time, apply TieBreakerPolicy

### 10.5 Missing Revision History

- If no revisions exist: treat as single revision with revision_time = observation_time
- If revision history is incomplete: use available revisions, document gap

### 10.6 Latest-Value-Only Rejection

When multiple revisions exist at the same timestamp:
- Apply TieBreakerPolicy to select one
- Reject all others as "superseded"
- Rejection is silent (no error) — T-X07 compliant

### 10.7 Immutability

- Once created, a revision entry MUST NOT change
- Revisions are frozen Pydantic models
- Append-only: no deletion, no modification

---

## 11. EQUAL-TIME ORDERING

### 11.1 TieBreakerPolicy

```text
TieBreakerPolicy
    ↓
deterministic ordering for observations with identical timestamps
```

### 11.2 Complete Ordering Tuple

When multiple observations share the same primary timestamp:

```text
1. primary temporal key (e.g., publication_time, revision_time)
2. revision key (revision_time, then revision sequence)
3. source key (data source identifier)
4. instrument key (instrument symbol)
5. sequence key (deterministic sequence number)
6. canonical identity hash (tie-break of last resort)
```

### 11.3 Deterministic Guarantees

- Ordering MUST be identical across processes and machines
- Ordering MUST NOT depend on wall-clock time
- Ordering MUST NOT depend on random values
- Ordering MUST be reproducible from the data alone

### 11.4 TieBreakerPolicy Configuration

| Policy Type | Ordering Criteria |
|-------------|-------------------|
| VENUE_FIRST | venue, then instrument, then sequence |
| SOURCE_FIRST | data_source, then venue, then instrument |
| INSTRUMENT_FIRST | instrument, then venue, then source |
| IDENTITY_LAST | All above + canonical identity hash as final tie-break |

---

## 12. PIT VIEW

### 12.1 PitView Structure

```text
PitView
    ↓
dataset_id
    ↓
dataset_version
    ↓
pit_cutoff (the cutoff time used for filtering)
    ↓
sidecar (PitSidecar reference)
    ↓
filtered_candles (list of candles passing all filters)
    ↓
filtered_row_count
    ↓
view_hash (deterministic identity of this view)
    ↓
tie_breaker_policy (reference)
    ↓
revision_policy (reference)
    ↓
temporal_contract (reference)
    ↓
provenance (preserved from original dataset)
    ↓
evidence_provenance (preserved — SYNTHETIC stays SYNTHETIC)
```

### 12.2 Immutability

- PitView is a frozen Pydantic model
- Once constructed, filtered_candles cannot change
- view_hash is computed at construction time and never changes

### 12.3 Equivalent PIT Views

Two PitViews are equivalent if and only if:
- Same dataset_id
- Same dataset_version
- Same pit_cutoff
- Same sidecar
- Same tie_breaker_policy
- Same revision_policy
- Same view_hash

---

## 13. PIT VIEW BUILDER

### 13.1 Responsibilities

1. **Validate inputs:** dataset, pit_cutoff, sidecar, policies
2. **Apply temporal cutoff:** filter by publication_time, effective_time, event_time, observation_time
3. **Apply revision policy:** select latest eligible revision per RevisionChain
4. **Apply deterministic ordering:** use TieBreakerPolicy for equal-time observations
5. **Preserve provenance:** evidence_provenance flows through unchanged
6. **Preserve data-quality classification:** SYNTHETIC → SYNTHETIC, REAL → REAL
7. **Reject invalid/future data:** per AvailabilityPolicy rules, silent rejection
8. **Construct immutable PitView:** frozen model with computed view_hash
9. **Calculate deterministic view identity:** view_hash from allowlist

### 13.2 What Does NOT Belong Here

- No simulation logic
- No backtest execution
- No strategy evaluation
- No trade generation

### 13.3 Integration Pipeline

```text
Dataset
    ↓
PitViewBuilder.filter(dataset, pit_cutoff, sidecar, policies)
    ↓
PitView (immutable, with view_hash)
    ↓
PitView.filtered_candles → Dataset (for backtest)
    ↓
BacktestEngine.run(strategy, filtered_dataset)
```

---

## 14. PIT VIEW VALIDATOR

### 14.1 Validation Checks

| Check | Severity | Condition |
|-------|----------|-----------|
| Future information present | ERROR | Any candle with publication_time > pit_cutoff in filtered view |
| Missing required timestamps | ERROR | Required temporal field is None when contract requires it |
| Naive datetime | ERROR | Any timestamp without tzinfo |
| Invalid timezone | ERROR | Timezone is not UTC |
| Revision conflict | ERROR | Multiple revisions claim same revision_time without tie-breaker resolution |
| Equal-time ambiguity | WARNING | Multiple observations share timestamp without deterministic ordering |
| Nondeterministic ordering | ERROR | Ordering is not reproducible (should never occur if TieBreakerPolicy applied) |
| Provenance loss | ERROR | evidence_provenance changed during filtering |
| Synthetic data misclassification | ERROR | SYNTHETIC data marked as REAL or PRODUCTION |
| Identity mismatch | ERROR | view_hash does not match recomputed hash from allowlist |

### 14.2 Validation Output

- Pass/Fail status
- List of violations with severity and description
- Verification that view_hash is consistent

---

## 15. PROVENANCE

### 15.1 Provenance Preservation Through PIT Transformations

| Transformation | Provenance Behavior |
|----------------|---------------------|
| PitViewBuilder filtering | evidence_provenance copied from source dataset unchanged |
| PitView construction | provenance reference preserved |
| Filtered Dataset creation | evidence_provenance from original dataset |

### 15.2 Prohibited Transformations

- SYNTHETIC → REAL: PROHIBITED
- SYNTHETIC → PRODUCTION: PROHIBITED
- REAL → SYNTHETIC: PROHIBITED (would weaken provenance)
- Any reclassification without explicit approval: PROHIBITED

### 15.3 DataQualityGate Interaction

- DataQualityGate.check() runs on input dataset BEFORE PitViewBuilder
- If dataset is blocked, PitViewBuilder is not invoked
- Blocked datasets (SYNTHETIC without approval) never reach PIT filtering

---

## 16. MULTI-ASSET MODEL

### 16.1 Asset-Neutral Guarantee

Phase 4A.1 PIT components are asset-neutral:
- No equity-specific logic
- No futures-specific logic
- No FX-specific logic
- No crypto-specific logic
- No single-asset assumptions

### 16.2 Asset-Class Handling

| Aspect | 4A.1 Behavior |
|--------|---------------|
| Instrument identity | Uses existing Instrument.symbol (string) |
| Asset class | Uses existing Instrument.asset_class (enum) — stored, not processed |
| Venue | Not used in 4A.1 (deferred) |
| DataSource | Not used in 4A.1 (deferred) |
| Calendar | Not used in 4A.1 (deferred) |

### 16.3 Future Extension Points

- InstrumentIdentity can be added later without changing PitSidecar
- Venue can be added to TieBreakerPolicy ordering without changing core logic
- CalendarRef can be referenced by PitExperimentConfig without changing PIT filtering

---

## 17. CALENDAR REFERENCE (Minimal 4A.1 Definition)

### 17.1 CalendarRef (Deferred — Reference Only)

For 4A.1, CalendarRef is NOT implemented. It is documented here for completeness:

| Field | Classification |
|-------|----------------|
| calendar_id | IDENTITY (when implemented) |
| calendar_version | IDENTITY |
| calendar_source | DISPLAY_ONLY |
| periods_per_year | DEFERRED (UQ-01) |

**4A.1 Status:** Deferred to 4A.2. No calendar logic in 4A.1.

---

## 18. EXPERIMENT IDENTITY

### 18.1 ExperimentIdentity Structure

```text
ExperimentIdentity
    ↓
strategy_id + strategy_version → strategy_hash (from StrategySpec.to_hash())
    ↓
dataset_id + dataset_version → dataset_hash (from BacktestEngine._compute_dataset_hash())
    ↓
pit_view_hash (from PitView.view_hash)
    ↓
config_hash (from BacktestConfig._compute_config_hash())
    ↓
tie_breaker_name + tie_breaker_version
    ↓
code_version (Phase 4A.1 version)
    ↓
quant_engine_version (from QuantEngine)
    ↓
backtest_engine_version (from BacktestEngine)
    ↓
EXPERIMENT_IDENTITY_HASH = deterministic_hash({all above})
```

### 18.2 Deterministic Guarantees

Experiment identity MUST NOT depend on:
- run_timestamp
- approval_timestamp
- ingestion_time
- random UUIDs
- wall-clock time

### 18.3 Identity Inputs Summary

| Input | Source |
|-------|--------|
| strategy identity | StrategySpec.to_hash() — frozen |
| dataset identity | BacktestEngine._compute_dataset_hash() — frozen |
| PIT view identity | PitView.view_hash — new |
| configuration identity | BacktestConfig._compute_config_hash() — frozen |
| tie-breaker identity | TieBreakerPolicy.name + version — new |
| code version | Phase 4A.1 implementation version — fixed per release |
| quant engine version | QuantEngine version — existing |
| backtest engine version | BacktestEngine version — existing |

---

## 19. PHASE 3 COMPATIBILITY

### 19.1 Guaranteed Unchanged

| Component | Guarantee |
|-----------|-----------|
| BacktestEngine.run(strategy, dataset) | Signature unchanged — receives Dataset, returns BacktestResult |
| BacktestProvenance.compute_result_hash() | Implementation unchanged — same inputs → same output |
| Candle.to_hash() | Unchanged — uses model_dump_json() |
| ProvenanceRecord.to_hash() | Unchanged — uses model_dump_json() |
| StrategySpec.to_hash() | Unchanged — uses canonical_serialize() |
| BacktestProvenance.to_hash() | Unchanged — excludes run_timestamp, result_hash, backtest_id |
| BacktestEngine._compute_dataset_hash() | Unchanged — content-based |
| BacktestConfig._compute_config_hash() | Unchanged — config-based |

### 19.2 Integration Model

```text
Dataset (original)
    ↓
PitViewBuilder.filter(dataset, pit_cutoff)
    ↓
PitView (filtered view)
    ↓
Extract filtered_candles as new Dataset
    ↓
BacktestEngine.run(strategy, filtered_dataset)  # Same signature, same behavior
    ↓
BacktestResult (with result_hash computed from filtered data)
```

### 19.3 What Changes

- The Dataset passed to BacktestEngine.run() may be a filtered subset
- result_hash reflects the filtered dataset (EXPECTED — different data → different hash)
- config_hash, strategy_hash remain unchanged (same config, same strategy)

### 19.4 What Does NOT Change

- BacktestEngine.run() signature
- BacktestConfig serialization
- StrategySpec serialization
- Any Phase 3 hash method implementation

---

## 20. TEST ARCHITECTURE

### 20.1 Existing Tests (Preserved)

| Test Suite | Count | Status |
|------------|-------|--------|
| test_data_engine.py | 62 | KEEP — regression |
| test_pit.py | 97 | KEEP — PIT foundation |
| test_quant.py | 134 | KEEP — regression |
| test_redteam.py | 50 | KEEP — regression |
| test_strategy.py | 82 | KEEP — regression |
| test_strategy_independent.py | 39 | KEEP — regression |
| **Total** | **464** | **Must continue to pass** |

### 20.2 New Test File

**tests/test_pit_view.py** — New file for PIT view tests

### 20.3 Seven Independent P0 Acceptance Tests

| P0 ID | Test Behavior | Test Location |
|-------|---------------|--------------|
| T-H04 | Verify BacktestConfig._compute_config_hash() produces identical hash before and after Phase 4A.1 additions | test_pit_view.py |
| T-H05 | Verify deterministic_hash() produces identical output across process boundaries (or document SHA-256 guarantee) | test_pit_view.py |
| T-P02 | Verify data with publication_time = pit_cutoff + 1 second is excluded | test_pit_view.py |
| T-R03 | Verify RevisionChain maintains append-only integrity | test_pit_view.py |
| T-R04 | Verify latest-value-only rejection — only latest revision at cutoff visible | test_pit_view.py |
| T-X02 | Verify future revision is excluded (indirect coverage exists — verify explicitly) | test_pit_view.py |
| T-X07 | Verify future data silently excluded — no error raised | test_pit_view.py |

### 20.4 Remaining P0 Tests (12 of 19)

| P0 ID | Verification Method |
|-------|---------------------|
| T-H01 | T-PIT-08, T-PIT-21: view_hash differs from dataset_hash; compute_result_hash unchanged |
| T-H02 | T-PIT-09, T-PIT-10: same cutoff different data → different view_hash; different cutoff same data → different view_hash |
| T-H03 | T-PIT-20: BacktestEngine interface unchanged (TestBackwardCompatibility already covers) |
| T-P01 | T-PIT-03: publication_time == pit_cutoff → included |
| T-P03 | T-PIT-05: revision_time > pit_cutoff → latest revision at cutoff used |
| T-P04 | T-PIT-04: effective_time > pit_cutoff → excluded, no error |
| T-R01 | T-PIT-14: single revision → one visible entry |
| T-R02 | T-PIT-15: multiple revisions → only revision_time <= T visible |
| T-M01 | T-PIT-17: missing event_time rejected (TestTemporalContract covers) |
| T-M06 | T-PIT-18: naive datetime rejected (TestTemporalSemantics covers) |
| T-O01 | T-PIT-12, T-PIT-13: tie-breaker deterministic ordering |
| T-X01 | T-PIT-06: future publication excluded (test_publication_availability_logic covers) |

### 20.5 T-PIT to Implementation Test Map

| T-PIT ID | Implementation Test |
|----------|---------------------|
| T-PIT-01 | test_default_sidecar_for_legacy_dataset |
| T-PIT-02 | test_sidecar_immutability |
| T-PIT-03 | test_pit_filtering_by_publication_time |
| T-PIT-04 | test_pit_filtering_by_effective_time |
| T-PIT-05 | test_pit_filtering_by_revision_time |
| T-PIT-06 | test_future_data_excluded_silently (existing coverage) |
| T-PIT-07 | test_temporal_eligibility_validation |
| T-PIT-08 | test_view_hash_differs_from_dataset_hash |
| T-PIT-09 | test_same_cutoff_different_data_different_view_hash |
| T-PIT-10 | test_different_cutoff_same_data_different_view_hash |
| T-PIT-11 | test_experiment_id_includes_all_components |
| T-PIT-12 | test_changing_tie_breaker_changes_experiment_id |
| T-PIT-13 | test_deterministic_equal_time_ordering |
| T-PIT-14 | test_revision_chain_append_only |
| T-PIT-15 | test_revision_reconstruction_at_pit_cutoff |
| T-PIT-16 | DEFERRED — not tested in 4A.1 |
| T-PIT-17 | test_missing_event_time_rejected (existing coverage) |
| T-PIT-18 | test_naive_datetime_rejected (existing coverage) |
| T-PIT-19 | test_legacy_dataset_default_sidecar |
| T-PIT-20 | test_backtest_engine_interface_unchanged (existing coverage) |
| T-PIT-21 | test_compute_result_hash_unchanged |
| T-PIT-22 | test_new_pit_fields_have_defaults |

---

## 21. IMPLEMENTATION ORDER

### Step 0 — Freeze Baseline

| Action | Details |
|--------|---------|
| Files | None (baseline measurement) |
| Dependencies | None |
| Outputs | Record 464-test baseline, record Phase 3 hash values |
| Tests | Run full regression — 464 must pass |
| Acceptance | Baseline recorded; Phase 3 hashes documented |

### Step 1 — Phase 4 Identity Contract

| Action | Details |
|--------|---------|
| Files | pit/identity.py (NEW) |
| Dependencies | pit/hashing.py, pit/serialization.py |
| Components | identity_allowlist(), compute_identity_hash() helper functions |
| Tests | test_identity_foundation.py (NEW) |
| Acceptance | Identity hash computed from allowlist matches expected; no Phase 3 modification |

### Step 2 — Minimal Asset/Reference Identity Primitives

**These 5 primitives are REQUIRED for 4A.1 as minimal immutable contracts. Their full domain functionality remains deferred.**

#### Step 2.1 — InstrumentIdentity

| Action | Details |
|--------|---------|
| Files | pit/instrument.py (NEW) |
| Dependencies | pit/identity.py |
| Components | InstrumentIdentity (frozen Pydantic model) |
| Identity fields | stable_identifier, asset_class, contract_type |
| Tests | test_pit_view.py: test_instrument_identity_creation, test_instrument_identity_hash |
| Acceptance | InstrumentIdentity creates correctly; immutable; deterministic hash |

#### Step 2.2 — InstrumentSpecification

| Action | Details |
|--------|---------|
| Files | pit/instrument.py (extend) |
| Dependencies | pit/instrument.py (InstrumentIdentity), pit/identity.py |
| Components | InstrumentSpecification (frozen Pydantic model) |
| Tests | test_pit_view.py: test_instrument_specification_creation |
| Acceptance | InstrumentSpecification creates correctly; includes instrument identity reference |

#### Step 2.3 — Venue

| Action | Details |
|--------|---------|
| Files | pit/venue.py (NEW) |
| Dependencies | pit/identity.py |
| Components | Venue (frozen Pydantic model) |
| Identity fields | venue_id, venue_name, timezone |
| Tests | test_pit_view.py: test_venue_creation, test_venue_hash |
| Acceptance | Venue creates correctly; immutable; deterministic hash |

#### Step 2.4 — DataSource

| Action | Details |
|--------|---------|
| Files | pit/source.py (NEW) |
| Dependencies | pit/identity.py |
| Components | DataSource (frozen Pydantic model) |
| Identity fields | source_id, provider_name, source_type |
| Tests | test_pit_view.py: test_data_source_creation, test_data_source_hash |
| Acceptance | DataSource creates correctly; immutable; deterministic hash |

#### Step 2.5 — CalendarRef

| Action | Details |
|--------|---------|
| Files | pit/calendar.py (NEW) |
| Dependencies | pit/identity.py |
| Components | CalendarRef (frozen Pydantic model) |
| Identity fields | calendar_id, calendar_version, calendar_source |
| Tests | test_pit_view.py: test_calendar_ref_creation, test_calendar_ref_hash |
| Acceptance | CalendarRef creates correctly; immutable; deterministic hash; NO holiday/session logic |

### Step 3 — PIT Temporal Primitives

#### Step 3.1 — PitSidecar

| Action | Details |
|--------|---------|
| Files | pit/sidecar.py (NEW) |
| Dependencies | pit/temporal.py, pit/contract.py, Step 1 identity, Step 2.1-2.5 primitives |
| Components | PitSidecar (frozen Pydantic model) |
| Tests | test_pit_view.py: test_sidecar_creation, test_sidecar_immutability, test_default_sidecar |
| Acceptance | PitSidecar creates correctly; immutable; default sidecar for legacy datasets |

#### Step 3.2 — RevisionChain

| Action | Details |
|--------|---------|
| Files | pit/revision.py (NEW) |
| Dependencies | pit/temporal.py, Step 1 identity |
| Components | RevisionChain, RevisionEntry (frozen) |
| Tests | test_pit_view.py: test_revision_chain_append_only, test_revision_reconstruction |
| Acceptance | Revisions append-only; chain integrity maintained; cutoff filtering works |

#### Step 3.3 — TieBreakerPolicy

| Action | Details |
|--------|---------|
| Files | pit/tiebreaker.py (NEW) |
| Dependencies | None (standalone) |
| Components | TieBreakerPolicy (frozen), ordering tuple |
| Tests | test_pit_view.py: test_deterministic_equal_time_ordering, test_tie_breaker_deterministic |
| Acceptance | Same timestamps → deterministic order; order identical across processes |

### Step 4 — PIT View Layer

#### Step 4.1 — PitView

| Action | Details |
|--------|---------|
| Files | pit/view.py (NEW) |
| Dependencies | pit/sidecar.py, Step 3.2 revision, Step 3.3 tie-breaker, Step 2.2 InstrumentSpecification, Step 2.5 CalendarRef, Step 1 identity |
| Components | PitView (frozen Pydantic model) |
| Tests | test_pit_view.py: test_view_creation, test_view_hash_differs_from_dataset_hash |
| Acceptance | PitView immutable; view_hash computed correctly; includes instrument_spec_version and calendar_version per UQ-12 |

#### Step 4.2 — PitViewBuilder

| Action | Details |
|--------|---------|
| Files | pit/builder.py (NEW) |
| Dependencies | pit/sidecar.py, pit/view.py, pit/revision.py, pit/tiebreaker.py, pit/availability.py, pit/instrument.py, pit/calendar.py |
| Components | PitViewBuilder with filter() method |
| Tests | test_pit_view.py: test_publication_time_filtering, test_effective_time_filtering, test_revision_time_filtering, test_future_data_excluded |
| Acceptance | Filtering correct at boundaries; future data excluded silently; provenance preserved |

#### Step 4.3 — PitViewValidator

| Action | Details |
|--------|---------|
| Files | pit/validator.py (NEW) |
| Dependencies | pit/view.py, pit/contract.py |
| Components | PitViewValidator with validate() method |
| Tests | test_pit_view.py: test_future_information_rejected, test_missing_timestamps_rejected, test_naive_datetime_rejected |
| Acceptance | All validation checks pass; errors and warnings correctly classified |

### Step 5 — Experiment Layer

#### Step 5.1 — ExperimentIdentity

| Action | Details |
|--------|---------|
| Files | pit/experiment.py (NEW) |
| Dependencies | pit/view.py, strategy/schemas.py, strategy/backtest.py, pit/tiebreaker.py, pit/instrument.py, Step 1 identity |
| Components | ExperimentIdentity (frozen), compute_experiment_identity() |
| Tests | test_pit_view.py: test_experiment_id_includes_all_components, test_changing_tie_breaker_changes_experiment_id |
| Acceptance | Experiment identity deterministic; includes all required inputs; tie-breaker change produces different identity |

#### Step 5.2 — PitExperimentConfig

| Action | Details |
|--------|---------|
| Files | pit/experiment.py (extend) or pit/config.py (NEW) |
| Dependencies | ExperimentIdentity, BacktestConfig |
| Components | PitExperimentConfig (frozen) |
| Tests | test_pit_view.py: test_new_pit_fields_have_defaults |
| Acceptance | Configuration includes all PIT-specific fields; defaults correct |

### Step 6 — Behavioral Acceptance Tests

| Action | Details |
|--------|---------|
| Files | test_pit_view.py (extend) |
| Dependencies | All previous steps |
| Components | All 19 P0 tests, all 22 T-PIT tests, 7 independent P0 tests |
| Tests | Run full acceptance suite |
| Acceptance | All P0 requirements behaviorally verified; all T-PIT tests resolved |

### Step 7 — Full Regression

| Action | Details |
|--------|---------|
| Files | All existing test files |
| Dependencies | All previous steps |
| Outputs | 464 + new PIT view tests must pass |
| Tests | Full regression: pytest tests/ --tb=no -q |
| Acceptance | 464 existing tests pass; new tests pass; no regressions |

### Step 8 — Final Implementation Gate

| Action | Details |
|--------|---------|
| Files | All implementation files |
| Dependencies | Step 7 regression pass |
| Outputs | Implementation complete |
| Tests | All acceptance criteria met |
| Acceptance | All 19 P0 verified; all T-PIT resolved; Phase 3 hashes unchanged; BacktestEngine signature unchanged; no deferred features leaked |
| Acceptance | Configuration includes all PIT-specific fields; defaults correct |

### Step 10 — Acceptance Tests

| Action | Details |
|--------|---------|
| Files | test_pit_view.py (extend) |
| Dependencies | All previous steps |
| Components | All 19 P0 tests, all 22 T-PIT tests |
| Tests | Run full acceptance suite |
| Acceptance | All P0 requirements behaviorally verified; all T-PIT tests resolved |

### Step 11 — Full Regression

| Action | Details |
|--------|---------|
| Files | All existing test files |
| Dependencies | All previous steps |
| Outputs | 464 + new PIT view tests must pass |
| Tests | Full regression: pytest tests/ --tb=no -q |
| Acceptance | 464 existing tests pass; new tests pass; no regressions |

### Step 12 — Final Implementation Gate

| Action | Details |
|--------|---------|
| Files | All implementation files |
| Dependencies | Step 11 regression pass |
| Outputs | Implementation complete |
| Tests | All acceptance criteria met |
| Acceptance | All 19 P0 verified; all T-PIT resolved; Phase 3 hashes unchanged; BacktestEngine signature unchanged; no deferred features leaked |

---

## 22. FILE-BY-FILE IMPLEMENTATION MAP

| File | Action | Components | Dependencies | Tests |
|------|--------|------------|--------------|-------|
| pit/__init__.py | EXTEND | Export all 13 new components | New modules | — |
| pit/temporal.py | KEEP | Unchanged | — | KEEP existing |
| pit/availability.py | KEEP | Unchanged | — | KEEP existing |
| pit/contract.py | KEEP | Unchanged (may add predefined contracts) | — | KEEP existing |
| pit/hashing.py | KEEP | Unchanged | — | KEEP existing |
| pit/serialization.py | KEEP | Unchanged | — | KEEP existing |
| pit/identity.py | CREATE | identity_allowlist(), compute_identity_hash() | hashing.py, serialization.py | test_identity_foundation.py |
| pit/instrument.py | CREATE | InstrumentIdentity, InstrumentSpecification | identity.py | test_pit_view.py |
| pit/venue.py | CREATE | Venue | identity.py | test_pit_view.py |
| pit/source.py | CREATE | DataSource | identity.py | test_pit_view.py |
| pit/calendar.py | CREATE | CalendarRef | identity.py | test_pit_view.py |
| pit/sidecar.py | CREATE | PitSidecar | temporal.py, contract.py, identity.py, instrument.py, venue.py, source.py, calendar.py |
| pit/revision.py | CREATE | RevisionChain, RevisionEntry | temporal.py, identity.py | test_pit_view.py |
| pit/tiebreaker.py | CREATE | TieBreakerPolicy | None | test_pit_view.py |
| pit/view.py | CREATE | PitView | sidecar.py, revision.py, tiebreaker.py, instrument.py, calendar.py, identity.py | test_pit_view.py |
| pit/builder.py | CREATE | PitViewBuilder | sidecar.py, view.py, revision.py, tiebreaker.py, availability.py, instrument.py, calendar.py | test_pit_view.py |
| pit/validator.py | CREATE | PitViewValidator | view.py, contract.py | test_pit_view.py |
| pit/experiment.py | CREATE | ExperimentIdentity, PitExperimentConfig | view.py, strategy/schemas.py, strategy/backtest.py, tiebreaker.py, instrument.py, identity.py | test_pit_view.py |
| tests/test_pit.py | KEEP | Unchanged — 97 tests | — | KEEP existing |
| tests/test_pit_view.py | CREATE | All PIT view tests (P0, T-PIT, component tests) | All new modules | New tests |
| tests/test_identity_foundation.py | CREATE | Identity foundation tests | identity.py | New tests |
| src/data_engine/schemas.py | DO NOT TOUCH | Phase 3 frozen | — | KEEP existing |
| src/data_engine/strategy/backtest.py | DO NOT TOUCH | Phase 3 frozen | — | KEEP existing |
| src/data_engine/strategy/schemas.py | DO NOT TOUCH | Phase 3 frozen | — | KEEP existing |
| src/data_engine/strategy/provenance.py | DO NOT TOUCH | Phase 3 frozen | — | KEEP existing |

**NOTE:** This is a specification only. Do NOT create these files now. The implementation agent must follow the final approved specification.

---

## 23. SECURITY GATES

### 23.1 Implementation-Time Security Tests

| Security Gate | Test | Severity if Violated |
|---------------|------|---------------------|
| Future leakage | Verify no candle with publication_time > pit_cutoff in filtered view | CRITICAL |
| Revision leakage | Verify no revision with revision_time > pit_cutoff visible | CRITICAL |
| Wall-clock contamination | Verify identity hash does not include run_timestamp, ingestion_time, datetime.now() | CRITICAL |
| Equal-time nondeterminism | Verify same timestamps produce identical order across 100 runs | CRITICAL |
| Provenance loss | Verify evidence_provenance unchanged after filtering | HIGH |
| Synthetic data misclassification | Verify SYNTHETIC data not reclassified as REAL | HIGH |
| Identity collision | Verify different inputs produce different identity hashes (test with varied inputs) | MEDIUM |
| Cross-process determinism | Verify identity hash identical when computed in separate process (or document SHA-256 guarantee) | MEDIUM |
| Immutability | Verify frozen models cannot be modified after creation | HIGH |
| Phase 3 compatibility | Verify Candle.to_hash(), ProvenanceRecord.to_hash(), StrategySpec.to_hash() unchanged | CRITICAL |

---

## 24. ACCEPTANCE GATE

Implementation is complete when ALL of the following are true:

| ## 24.1 Component Completion
|- [ ] InstrumentIdentity implemented and tested (minimal identity reference)
|- [ ] InstrumentSpecification implemented and tested (minimal specification reference)
|- [ ] Venue implemented and tested (minimal venue reference)
|- [ ] DataSource implemented and tested (minimal source reference)
|- [ ] CalendarRef implemented and tested (minimal calendar reference)
|- [ ] PitSidecar implemented and tested
|- [ ] RevisionChain implemented and tested
|- [ ] TieBreakerPolicy implemented and tested
|- [ ] PitView implemented and tested
|- [ ] PitViewBuilder implemented and tested
|- [ ] PitViewValidator implemented and tested
|- [ ] ExperimentIdentity implemented and tested
|- [ ] PitExperimentConfig implemented and tested

**Full Domain Functionality Deferred:**
|- [ ] No full calendar computation implemented (holidays, is_trading_day)
|- [ ] No venue session engine implemented
|- [ ] No instrument lifecycle management implemented
|- [ ] No futures/corporate action/FX functionality implemented

### 24.2 P0 Verification (19 of 19)
- [ ] T-H01: Result hash unchanged — verified
- [ ] T-H02: Dataset hash unchanged — verified
- [ ] T-H03: Strategy hash unchanged — verified
- [ ] T-H04: Config hash unchanged — verified
- [ ] T-H05: Cross-process determinism — verified
- [ ] T-P01: publication_time == cutoff → included — verified
- [ ] T-P02: publication_time = cutoff + 1s → excluded — verified
- [ ] T-P03: revision selection at cutoff — verified
- [ ] T-P04: effective_time > cutoff → excluded, no error — verified
- [ ] T-R01: Single revision → one entry — verified
- [ ] T-R02: Multiple revisions → only <= T visible — verified
- [ ] T-R03: Revision chain integrity — verified
- [ ] T-R04: Latest-value-only rejection — verified
- [ ] T-M01: Missing event_time rejected — verified
- [ ] T-M06: Naive datetime rejected — verified
- [ ] T-O01: Tie-breaker ordering — verified
- [ ] T-X01: Future publication excluded — verified
- [ ] T-X02: Future revision excluded — verified
- [ ] T-X07: Future data silently excluded — verified

### 24.3 T-PIT Resolution (22 of 22)
- [ ] All MAPPED_TO_P0 tests resolved
- [ ] All NEW_4A1_ACCEPTANCE tests resolved
- [ ] T-PIT-16 DEFERRED (not required for 4A.1)

### 24.4 Regression Preservation
- [ ] 464 existing tests pass
- [ ] Phase 3 hashes unchanged (Candle.to_hash, ProvenanceRecord.to_hash, StrategySpec.to_hash, BacktestProvenance.compute_result_hash, BacktestProvenance.to_hash, _compute_dataset_hash, _compute_config_hash)
- [ ] BacktestEngine.run() signature unchanged
- [ ] BacktestProvenance.compute_result_hash() unchanged

### 24.5 Security Gates
- [ ] No future leakage
- [ ] No revision leakage
- [ ] No wall-clock contamination in identity
- [ ] Equal-time ordering deterministic
- [ ] Provenance preserved
- [ ] Synthetic data not misclassified
- [ ] All models immutable

### 24.6 Deferred Feature Containment
- [ ] No equity-specific logic in 4A.1
- [ ] No futures-specific logic in 4A.1
- [ ] No FX-specific logic in 4A.1
- [ ] No calendar logic in 4A.1
- [ ] No live execution in 4A.1
- [ ] No broker integration in 4A.1

---

## 25. FINAL SPECIFICATION STATUS

```text
IMPLEMENTATION SPECIFICATION: CORRECTED
ARCHITECTURE STATUS: 13_PRIMITIVE_FOUNDATION
IMPLEMENTATION READINESS: READY_FOR_EXPLICIT_IMPLEMENTATION_COMMAND
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

This document authorizes NOTHING. A separate explicit implementation command will be required later.

---

*End of PHASE 4A.1 IMPLEMENTATION SPECIFICATION*
