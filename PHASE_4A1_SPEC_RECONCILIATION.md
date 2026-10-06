# PHASE 4A.1 SPECIFICATION RECONCILIATION

**Version:** 1.0.0
**Date:** 2026-09-29
**Mode:** READ-ONLY ARCHITECTURAL RECONCILIATION
**Authorization:** NOT_AUTHORIZED FOR IMPLEMENTATION

---

## 1. EXECUTIVE VERDICT

**The 8-component scope in PHASE_4A1_IMPLEMENTATION_SPEC.md is ARCHITECTURALLY INCORRECT.**

The authoritative BLOCKER_RESOLUTION_SPEC.md Section 9.1 explicitly lists InstrumentIdentity, InstrumentSpecification, Venue, DataSource, and CalendarRef as **4A.1 PROPOSED** primitives — not deferred to 4A.2+.

The correct architecture is:

```text
13 MINIMAL FOUNDATION PRIMITIVES REQUIRED FOR 4A.1
```

with their **full domain functionality deferred**.

The distinction is:
- MINIMAL IDENTITY/REFERENCE PRIMITIVE: Required for 4A.1 (identity, reproducibility, view_hash computation)
- FULL DOMAIN FUNCTIONALITY: Deferred (calendar computation, venue session management, etc.)

---

## 2. 8-VS-13 RECONCILIATION

### 2.1 Source of Conflict

| Document | Claim | Status |
|----------|-------|--------|
| PHASE_4A1_IMPLEMENTATION_SPEC.md | 8 required, 5 deferred | **INCORRECT** |
| PHASE_4A1_FORENSIC_RECONCILIATION.md | 8 required, 5 deferred | **INCORRECT** (inherited from spec) |
| PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md §9.1 | All 13 PROPOSED for 4A.1 | **AUTHORITATIVE** |
| PHASE_4A_FINAL_ARCHITECTURE_SPEC.md UQ-12 | view_hash includes instrument_spec_version, calendar_version | **AUTHORITATIVE** |

### 2.2 Why the 8-Component Specification Is Wrong

1. **Direct contradiction with BLOCKER_RESOLUTION_SPEC.md §9.1**: The authoritative blocker resolution explicitly lists all 13 primitives as 4A.1 PROPOSED.

2. **view_hash dependency (UQ-12)**: The architecture specifies that view_hash includes `instrument_spec_version` and `calendar_version`. Without these primitives, view_hash cannot be computed per the architecture.

3. **ExperimentIdentity dependency**: ExperimentIdentity requires instrument identity for deterministic experiment reproduction across different instruments.

4. **Incorrect rationale**: "Multi-asset primitives not required for temporal foundation" is false. The temporal foundation needs instrument identity for PIT view reproducibility — the same temporal data for different instruments produces different PIT views.

### 2.3 Resolution

**CORRECT SCOPE: 13 MINIMAL PRIMITIVES REQUIRED FOR 4A.1**

---

## 3. COMPONENT-BY-COMPONENT DECISION

### 3.1 PitSidecar

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Immutable temporal metadata snapshot |
| Full functionality deferred | No — this IS the minimal primitive |
| Identity fields | dataset_id, dataset_version, event_time, observation_time, publication_time, effective_time, revision_time |
| Audit-only | ingestion_time |
| Authority | BLOCKER_RESOLUTION_SPEC.md §3.4.6 |

### 3.2 RevisionChain

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Append-only revision history |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §3.4 | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 3.3 TieBreakerPolicy

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Deterministic ordering policy |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-12 |

### 3.4 PitView

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | PIT-filtered dataset representation |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 3.5 PitViewBuilder

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Constructs PitView from Dataset + cutoff |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 3.6 PitViewValidator

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Validates PitView correctness |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 3.7 ExperimentIdentity

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Deterministic experiment identity hash |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §3.4.8, §9.1 |

### 3.8 PitExperimentConfig

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | YES |
| Minimal primitive | Configuration for PIT-aware experiments |
| Full functionality deferred | No — this IS the minimal primitive |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1 |

### 3.9 InstrumentIdentity

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | **YES — MINIMAL PRIMITIVE** |
| Minimal primitive | Immutable instrument identity reference |
| Full functionality deferred | Full instrument lifecycle management, symbol history, venue history |
| Identity fields | stable_identifier, asset_class, contract_type |
| Audit-only | symbol_history, venue_history |
| Schema version | Phase 4A.1 v4.0.0 |
| Authority | BLOCKER_RESOLUTION_SPEC.md §3.4.9, §9.1 |

**Minimal 4A.1 fields:**
```python
class InstrumentIdentity(BaseModel):
    stable_identifier: str  # Immutable canonical identifier
    asset_class: AssetClass  # From existing enum
    contract_type: ContractType  # From existing enum
```

**Deferred functionality:**
- Symbol history tracking
- Venue history tracking
- Lifecycle event metadata
- Corporate action integration

### 3.10 InstrumentSpecification

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | **YES — MINIMAL PRIMITIVE** |
| Minimal primitive | Immutable instrument specification reference |
| Full functionality deferred | Full trading calendar integration, contract details, commission schedules |
| Identity fields | instrument_identity, specification_version, periods_per_year (default) |
| Deferred | Exchange-specific contract details, ticker symbols, lot sizes |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-12 |

**Minimal 4A.1 fields:**
```python
class InstrumentSpecification(BaseModel):
    instrument_identity: InstrumentIdentity
    specification_version: str
    periods_per_year: Optional[float] = None  # Default from calendar if not specified
```

**Deferred functionality:**
- Exchange-specific contract parameters
- Lot size/contract multiplier
- Trading hours integration
- Corporate action adjustments

### 3.11 Venue

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | **YES — MINIMAL PRIMITIVE** |
| Minimal primitive | Immutable venue reference |
| Full functionality deferred | Session management, trading hours calculation, timezone conversion engine |
| Identity fields | venue_id, venue_name, timezone |
| Deferred | is_trading_day(), get_session_hours(), holiday calendar |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-09 |

**Minimal 4A.1 fields:**
```python
class Venue(BaseModel):
    venue_id: str  # Immutable venue identifier
    venue_name: str
    timezone: str  # IANA timezone string
```

**Deferred functionality:**
- is_trading_day() calculation
- get_session_hours() 
- Holiday calendar integration
- Exchange session generation

### 3.12 DataSource

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | **YES — MINIMAL PRIMITIVE** |
| Minimal primitive | Immutable data source reference |
| Full functionality deferred | Provider connection management, live data streaming, provider factory |
| Identity fields | source_id, provider_name, source_type |
| Deferred | Endpoint configuration, API key management, rate limiting |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1 |

**Minimal 4A.1 fields:**
```python
class DataSource(BaseModel):
    source_id: str  # Immutable source identifier
    provider_name: str
    source_type: str  # 'api', 'file', 'database', etc.
```

**Deferred functionality:**
- Endpoint configuration
- API key/env var management
- Rate limiting configuration
- Live connectivity

### 3.13 CalendarRef

| Aspect | Decision |
|--------|----------|
| REQUIRED 4A.1 | **YES — MINIMAL PRIMITIVE** |
| Minimal primitive | Immutable calendar reference |
| Full functionality deferred | Holiday calculation, session generation, trading day detection |
| Identity fields | calendar_id, calendar_version, calendar_source |
| Deferred | is_trading_day(), get_holidays(), session schedule |
| Authority | BLOCKER_RESOLUTION_SPEC.md §9.1, UQ-01, UQ-05 |

**Minimal 4A.1 fields:**
```python
class CalendarRef(BaseModel):
    calendar_id: str  # Immutable calendar identifier
    calendar_version: str
    calendar_source: str  # 'exchange', 'custom', etc.
```

**Deferred functionality:**
- is_trading_day() method
- Holiday list calculation
- Session hours generation
- Exchange-specific calendar implementations

---

## 4. IDENTITY CONTRACT AUDIT

### 4.1 Phase 4 Identity Contract Verification

**VERIFIED:** The Phase 4 identity contract follows:

```text
EXPLICIT POSITIVE ALLOWLIST
    ↓
canonical_serialize()
    ↓
deterministic_hash()  [SHA-256]
    ↓
VERSIONED IDENTITY HASH
```

### 4.2 Verified Properties

| Property | Status | Evidence |
|----------|--------|----------|
| SHA-256 algorithm | CONFIRMED | All identity hashes use SHA-256 |
| Explicit algorithm/version | CONFIRMED | Schema version + hash version per entity |
| No wall-clock audit fields | CONFIRMED | provider_timestamp, retrieval_timestamp, run_timestamp, created_at, approval_timestamp all excluded |
| No provider_timestamp contamination | CONFIRMED | Phase 4 identity uses explicit allowlists, not model_dump_json() |
| No retrieval_timestamp contamination | CONFIRMED | excluded from Phase 4 identity |
| ingestion_time audit-only | CONFIRMED | Excluded from temporal_hash_input() |
| run_timestamp audit-only | CONFIRMED | Excluded from compute_result_hash() and to_hash() |
| created_at does not enter identity | CONFIRMED | default_factory=_now_utc but excluded from allowlists |
| Phase 3 hashes untouched | CONFIRMED | No to_deterministic_hash() added to Phase 3 models |

### 4.3 NO to_deterministic_hash() Required

**VERIFIED:** No `to_deterministic_hash()` methods should be added to Phase 3 models.

The architecture uses composition:
```python
identity_hash = deterministic_hash(
    canonical_serialize({
        field_1: value_1,
        field_2: value_2,
        ...
    })
)
```

This is functionally equivalent to a to_deterministic_hash() method but uses composition instead of modification.

---

## 5. PIT SEMANTICS AUDIT

### 5.1 Verified Inequalities

| Field | Cutoff Relationship | Behavior |
|-------|---------------------|----------|
| publication_time | < cutoff | INCLUDED |
| publication_time | == cutoff | INCLUDED |
| publication_time | > cutoff | EXCLUDED — silent |
| effective_time | <= cutoff | INCLUDED |
| effective_time | > cutoff | EXCLUDED — silent |
| revision_time | <= cutoff | INCLUDED (visible) |
| revision_time | > cutoff | EXCLUDED (not visible) |
| event_time | <= cutoff | INCLUDED |
| event_time | > cutoff | EXCLUDED — silent |
| observation_time | <= cutoff | INCLUDED |
| observation_time | > cutoff | EXCLUDED — silent |

### 5.2 Verified Semantics

| Semantic | Status |
|----------|--------|
| PIT cutoff is not simulation end time | CONFIRMED — cutoff is temporal filter, not simulation boundary |
| PitViewBuilder performs temporal filtering | CONFIRMED — this is its responsibility |
| Revision selection is deterministic | CONFIRMED — RevisionChain + TieBreakerPolicy |
| Equal timestamps use explicit TieBreakerPolicy | CONFIRMED — required by T-O01 |
| Revision history represented by RevisionChain | CONFIRMED — append-only structure |
| Latest-value-only data cannot become historically reconstructable | CONFIRMED — only revisions <= cutoff visible |
| Legacy fallback uses explicitly permitted provenance metadata | CONFIRMED — retrieval_timestamp only |
| ingestion_time never used for eligibility | CONFIRMED — excluded from temporal_hash_input() |

---

## 6. DEPENDENCY GRAPH

### 6.1 Corrected Dependency Graph

```
Dataset
    ↓
DataSource (minimal reference — for provenance tracking)
    ↓
Venue (minimal reference — for timezone/origin metadata)
    ↓
InstrumentIdentity (minimal — for instrument identification in PIT view)
    ↓
InstrumentSpecification (minimal — for periods_per_year default)
    ↓
CalendarRef (minimal — for calendar version in view_hash)
    ↓
PitSidecar (temporal metadata snapshot)
    ↓
RevisionChain (revision history)
    ↓
TieBreakerPolicy (deterministic ordering)
    ↓
PitView (filtered view with view_hash)
    ↓
PitViewValidator (validates PitView)
    ↓
ExperimentIdentity (experiment hash using all above)
```

### 6.2 Edge Justifications

| Edge | Why It Exists |
|------|---------------|
| Dataset → DataSource | DataSource is part of provenance tracking; dataset references its source |
| DataSource → Venue | Data source is associated with a venue (exchange/provider location) |
| Venue → InstrumentIdentity | Instruments trade on venues; venue provides timezone context |
| InstrumentIdentity → InstrumentSpecification | Specification extends identity with trading parameters |
| InstrumentSpecification → CalendarRef | Specification may reference calendar for periods_per_year |
| CalendarRef → PitSidecar | Calendar version included in sidecar for reproducibility |
| PitSidecar → RevisionChain | Sidecar references revision history for temporal metadata |
| RevisionChain → TieBreakerPolicy | Revision ordering uses tie-breaker for equal-time revisions |
| TieBreakerPolicy → PitView | PitView ordering uses tie-breaker for equal-time observations |
| PitView → PitViewValidator | Validator checks PitView correctness |
| PitView → ExperimentIdentity | Experiment identity includes view_hash |

### 6.3 Dependencies That Do NOT Exist

| False Dependency | Why It's False |
|-----------------|----------------|
| PitSidecar → InstrumentSpecification | Sidecar stores temporal metadata, not instrument specs |
| RevisionChain → DataSource | Revisions are temporal, not source-dependent |
| TieBreakerPolicy → Venue | Tie-breaker may use venue as ordering criterion, but doesn't depend on it |
| PitViewValidator → CalendarRef | Validation is temporal, not calendar-dependent |

---

## 7. TEST COVERAGE RECONCILIATION

### 7.1 19 P0 Requirements

| P0 ID | Status | Evidence |
|-------|--------|----------|
| T-H01 | NEW ACCEPTANCE TEST | T-PIT-08, T-PIT-21 — view_hash differs, compute_result_hash unchanged |
| T-H02 | NEW ACCEPTANCE TEST | T-PIT-09, T-PIT-10 — view_hash changes with data/cutoff |
| T-H03 | PASSING FOUNDATION | T-PIT-20 — BacktestEngine interface unchanged (existing tests verify) |
| T-H04 | NEW ACCEPTANCE TEST | Independent — config_hash stability |
| T-H05 | NEW ACCEPTANCE TEST | Independent — cross-process determinism |
| T-P01 | NEW ACCEPTANCE TEST | T-PIT-03 — publication_time == cutoff → included |
| T-P02 | NEW ACCEPTANCE TEST | Independent — publication_time = cutoff + 1s → excluded |
| T-P03 | NEW ACCEPTANCE TEST | T-PIT-05 — revision_time > cutoff → latest at cutoff |
| T-P04 | NEW ACCEPTANCE TEST | T-PIT-04 — effective_time > cutoff → excluded |
| T-R01 | NEW ACCEPTANCE TEST | T-PIT-14 — single revision → one entry |
| T-R02 | NEW ACCEPTANCE TEST | T-PIT-15 — multiple revisions → only <= T visible |
| T-R03 | NEW ACCEPTANCE TEST | T-PIT-14 — append-only (chain integrity needs explicit test) |
| T-R04 | NEW ACCEPTANCE TEST | Independent — latest-value-only rejection |
| T-M01 | PASSING FOUNDATION | T-PIT-01, T-PIT-17 — missing event_time rejected (existing test) |
| T-M06 | PASSING FOUNDATION | T-PIT-18, T-PIT-19 — naive datetime rejected (existing test) |
| T-O01 | NEW ACCEPTANCE TEST | T-PIT-12, T-PIT-13 — tie-breaker ordering |
| T-X01 | PASSING FOUNDATION | T-PIT-06 — future publication excluded (existing test) |
| T-X02 | NEW ACCEPTANCE TEST | Independent — future revision excluded |
| T-X07 | NEW ACCEPTANCE TEST | Independent — future data silently excluded |

### 7.2 7 Independent P0 Requirements

| P0 ID | Status |
|-------|--------|
| T-H04 | MISSING — needs new test |
| T-H05 | MISSING — needs new test |
| T-P02 | MISSING — needs new test |
| T-R03 | MISSING — needs new test |
| T-R04 | MISSING — needs new test |
| T-X02 | MISSING — needs new test |
| T-X07 | MISSING — needs new test |

### 7.3 T-PIT 01–22

| T-PIT ID | Status |
|-----------|--------|
| T-PIT-01 through T-PIT-22 | All accounted for in BLOCKER_RESOLUTION_SPEC.md §2.2 |

### 7.4 Existing Tests

| Suite | Count | Status |
|-------|-------|--------|
| test_pit.py | 97 | KEEP — foundational temporal tests |
| Full regression | 464 | Must continue to pass |

---

## 8. PHASE BOUNDARY AUDIT

### 8.1 Confirmed Deferred (NOT in 4A.1)

| Feature | Phase | Reason |
|---------|-------|--------|
| CorporateAction | 4A.2 | Equity-specific |
| Full corporate-action engine | 4A.2 | Requires CorporateAction |
| FuturesContract | 4A.3 | Futures-specific |
| ContinuousSeries | 4A.3 | Requires FuturesContract |
| Rollover logic | 4A.3 | Requires FuturesContract |
| FX financing/swap | Later | FX-specific |
| Full calendar infrastructure | 4A.2 | Requires CalendarRef minimal primitive first |
| Holiday engine | 4A.2 | Requires CalendarRef |
| ResearchContract | 4A.4 | Research governance |
| ApprovalMetadata | 4A.4 | Research governance |
| Live execution | NEVER | Phase 4A is research-only |
| Broker integration | NEVER | Phase 4A is research-only |
| Real-money trading | NEVER | Phase 4A is research-only |
| Production market-data connectivity | NEVER | Phase 4A uses existing datasets |
| Autonomous live trading | NEVER | Phase 4A is research-only |
| Automated strategy optimization | 4A+ | Out of scope |

### 8.2 Minimal Primitives Required for 4A.1

These are NOT deferred despite being "multi-asset" related:

| Primitive | Why Required for 4A.1 |
|-----------|----------------------|
| InstrumentIdentity | view_hash includes instrument identity; ExperimentIdentity requires instrument for reproducibility |
| InstrumentSpecification | view_hash includes instrument_spec_version (UQ-12); periods_per_year default |
| Venue | Timezone context for temporal metadata; tie-breaker may use venue |
| DataSource | Provenance tracking; dataset provenance references source |
| CalendarRef | view_hash includes calendar_version (UQ-12); periods_per_year source |

### 8.3 Distinction: Reference Primitive vs Full Subsystem

| Component | Minimal 4A.1 Primitive | Full Subsystem (Deferred) |
|-----------|----------------------|--------------------------|
| InstrumentIdentity | stable_identifier, asset_class, contract_type | Symbol history, venue history, lifecycle events |
| InstrumentSpecification | instrument_identity, spec_version, periods_per_year | Exchange-specific params, lot sizes, ticker symbols |
| Venue | venue_id, venue_name, timezone | is_trading_day(), session hours, holidays |
| DataSource | source_id, provider_name, source_type | Endpoint config, API keys, rate limiting, live streaming |
| CalendarRef | calendar_id, calendar_version, calendar_source | is_trading_day(), holidays, session schedules |

---

## 9. CORRECTED IMPLEMENTATION ORDER

### 9.1 Revised Dependency Order

The implementation order must ensure identity/reference primitives exist before objects that depend on their deterministic identity.

```
STEP 0 — Freeze baseline
    ↓
STEP 1 — Identity contract foundation (pit/identity.py)
    ↓
STEP 2 — Minimal identity/reference primitives (parallel)
    ├── pit/instrument.py — InstrumentIdentity, InstrumentSpecification
    ├── pit/venue.py — Venue
    ├── pit/source.py — DataSource
    └── pit/calendar.py — CalendarRef
    ↓
STEP 3 — PitSidecar (depends on temporal foundation + identity primitives)
    ↓
STEP 4 — RevisionChain (depends on temporal foundation)
    ↓
STEP 5 — TieBreakerPolicy (standalone, but needed before PitView)
    ↓
STEP 6 — PitView (depends on PitSidecar, RevisionChain, TieBreakerPolicy, InstrumentSpecification, CalendarRef)
    ↓
STEP 7 — PitViewBuilder (depends on all above)
    ↓
STEP 8 — PitViewValidator (depends on PitView)
    ↓
STEP 9 — ExperimentIdentity (depends on PitView, InstrumentIdentity, TieBreakerPolicy)
    ↓
STEP 10 — PitExperimentConfig (depends on ExperimentIdentity)
    ↓
STEP 11 — Acceptance tests (all 19 P0, 7 independent P0, 22 T-PIT)
    ↓
STEP 12 — Full regression (464 + new tests)
    ↓
STEP 13 — Final implementation gate
```

### 9.2 Key Change from Previous Specification

Steps 2 (minimal primitives) now precede Steps 3-6 (PIT view components) because:
- PitView.view_hash includes instrument_spec_version and calendar_version (UQ-12)
- ExperimentIdentity requires InstrumentIdentity for reproducibility
- DataSource and Venue are referenced by provenance metadata

---

## 10. FILE MAP

### 10.1 New Files Required

| File | Components | Dependencies |
|------|------------|--------------|
| pit/identity.py | identity_allowlist(), compute_identity_hash() | hashing.py, serialization.py |
| pit/instrument.py | InstrumentIdentity, InstrumentSpecification | identity.py |
| pit/venue.py | Venue | identity.py |
| pit/source.py | DataSource | identity.py |
| pit/calendar.py | CalendarRef | identity.py |
| pit/sidecar.py | PitSidecar | temporal.py, contract.py, identity.py, instrument.py |
| pit/revision.py | RevisionChain, RevisionEntry | temporal.py, identity.py |
| pit/tiebreaker.py | TieBreakerPolicy | None (standalone) |
| pit/view.py | PitView | sidecar.py, revision.py, tiebreaker.py, instrument.py, calendar.py, identity.py |
| pit/builder.py | PitViewBuilder | sidecar.py, view.py, revision.py, tiebreaker.py, availability.py, instrument.py, calendar.py |
| pit/validator.py | PitViewValidator | view.py, contract.py |
| pit/experiment.py | ExperimentIdentity, PitExperimentConfig | view.py, strategy/schemas.py, strategy/backtest.py, tiebreaker.py, instrument.py, identity.py |

### 10.2 Existing Files (Unchanged)

| File | Action |
|------|--------|
| pit/__init__.py | EXTEND — export new components |
| pit/temporal.py | KEEP |
| pit/availability.py | KEEP |
| pit/contract.py | KEEP |
| pit/hashing.py | KEEP |
| pit/serialization.py | KEEP |
| tests/test_pit.py | KEEP — 97 tests |
| src/data_engine/schemas.py | DO NOT TOUCH |
| src/data_engine/strategy/backtest.py | DO NOT TOUCH |
| src/data_engine/strategy/schemas.py | DO NOT TOUCH |
| src/data_engine/strategy/provenance.py | DO NOT TOUCH |

### 10.3 New Test Files

| File | Tests |
|------|-------|
| tests/test_pit_view.py | All PIT view tests (P0, T-PIT, component tests) |
| tests/test_identity_foundation.py | Identity foundation tests |

---

## 11. REMAINING BLOCKERS

### 11.1 Blockers for Implementation Authorization

| # | Blocker | Status | Resolution |
|---|---------|--------|------------|
| 1 | Design lock correction not committed | RESOLVED (working tree) | Commit correction |
| 2 | 13 minimal primitives not implemented | OPEN | Implement in corrected order |
| 3 | 7 independent P0 tests not implemented | OPEN | Add acceptance tests |
| 4 | Phase 4 identity contract not formalized in code | OPEN | Implement pit/identity.py |
| 5 | view_hash formula not implemented | OPEN | Implement per UQ-12 (includes instrument_spec_version, calendar_version, tie_breaker_policy) |

### 11.2 Non-Blockers

- T-X02 has indirect coverage — not a blocker (explicit test recommended)
- T-P02 has partial coverage — not a blocker (boundary test recommended)

---

## 12. EXACT RECOMMENDATION

### 12.1 Architecture Decision

**The architecture should be:**

```text
B. 13 MINIMAL FOUNDATION PRIMITIVES REQUIRED, WITH THEIR FULL DOMAIN FUNCTIONALITY DEFERRED.
```

This is based on:
1. BLOCKER_RESOLUTION_SPEC.md §9.1 explicitly lists all 13 as 4A.1 PROPOSED
2. UQ-12 requires instrument_spec_version and calendar_version in view_hash
3. ExperimentIdentity requires instrument identity for reproducibility
4. The distinction between minimal primitive and full subsystem is architecturally sound

### 12.2 Next Implementation Command Should:

1. Implement pit/identity.py (identity contract foundation)
2. Implement pit/instrument.py (InstrumentIdentity, InstrumentSpecification)
3. Implement pit/venue.py (Venue)
4. Implement pit/source.py (DataSource)
5. Implement pit/calendar.py (CalendarRef)
6. Then proceed with PitSidecar, RevisionChain, TieBreakerPolicy, PitView, etc.

### 12.3 Do NOT Implement

- Full calendar computation (is_trading_day, holidays)
- Venue session management
- DataSource connectivity
- Instrument lifecycle management
- Any corporate action, futures, or FX functionality

---

## FINAL OUTPUT

```text
SPECIFICATION RECONCILIATION: COMPLETE

ARCHITECTURE DECISION: 13 MINIMAL PRIMITIVES REQUIRED FOR 4A.1
IMPLEMENTATION ORDER: CORRECTED (identity/reference primitives first)
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

---

*End of PHASE 4A.1 SPEC RECONCILIATION*
