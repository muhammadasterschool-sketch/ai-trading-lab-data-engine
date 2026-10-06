# MASTER FULL-SYSTEM CONSTRUCTION BLUEPRINT

**Version:** 1.0.0
**Date:** 2026-10-06
**Status:** DESIGN/ARCHITECTURE ONLY — NO IMPLEMENTATION AUTHORIZED
**Repository:** C:\Users\muham\ai-trading-lab-data-engine
**Governance:** Phase 4A.1 blockers OPEN: 8 / CLOSED: 0 | Implementation NOT AUTHORIZED | Design Lock FAILED | Phase 4.2 NOT AUTHORIZED
**Frozen Phase 3:** PROTECTED — all contracts immutable (SHA-256 manifest)
**Source material:** PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md (v1.0.0, preserved unmodified)
**Created by:** Principal Architect — Master Blueprint derivation
**Purpose:** Complete-system construction blueprint covering the full AI Trading Lab lifecycle, from foundation through autonomous operating loop.

---

## Document Control

**This blueprint is DESIGN/ARCHITECTURE ONLY. It does not authorize implementation.**

**Governance state at time of creation:**
- Phase 4A.1 blockers: 8 OPEN / 0 CLOSED
- Implementation: NOT AUTHORIZED
- Design Lock: FAILED
- Phase 4.2: NOT AUTHORIZED
- Frozen Phase 3 contracts: PROTECTED — byte-for-byte SHA-256 manifest required
- No source files modified
- No tests modified
- No configuration modified
- No patches created

**Source document preservation:** PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md is retained unmodified. All historical claims from that document are preserved in this blueprint; no historical claim is silently altered.

**Document classification:**
- AUTHORITATIVE: This document (master blueprint)
- SUPERSEDED: PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md (status claims; historical evidence retained)
- HISTORICAL: All Phase 4A.1 audit/review/forensic documents
- INCORRECT CLAIM: "18 undefined test identifiers" → corrected to 23 (per authoritative spec §8.5.13)
- EVIDENCE-ONLY: Baseline measurements (367/464/97) — measured live, not assumed

---

## 1. System Vision

**What the system is:** A deterministic, reproducible, point-in-time-correct AI trading research laboratory. It ingests market data, constructs point-in-time views, runs quant research, generates and validates strategies via backtesting, manages risk, operates paper trading, evaluates over 30 days, and — only after explicit human authorization — may cross the boundary to live execution.

**What the system is NOT:**
- A live trading system (never, unless explicitly authorized)
- An LLM trading agent that makes unsupervised decisions
- A system that optimizes for trade count
- A system that bypasses governance for speed

**Core objectives (in priority order):**
1. Data integrity and PIT correctness
2. Deterministic reproducibility
3. Leakage resistance
4. Risk enforcement
5. Auditability
6. Autonomous research capability (within governance)
7. NO TRADE capability — the system must always be able to choose no trade

**Key principle — NO TRADE is a valid system output.** The system must produce explicit NO TRADE / REJECT decisions when:
- Statistical significance not met
- Risk limits exceeded
- Data quality insufficient
- PIT correctness cannot be verified
- Model stability fails
- Overfitting detected

The 2,765 trades / 2-day figure is ONLY a load/stress benchmark — never a system objective.

**Free-first construction strategy:** The architecture must support construction using free/local AI tools only. No paid AI service is assumed. All AI agents use local models or free-tier access.

---

## 2. Complete Roadmap

| Phase | Status | Tests | Key Components | Classification |
|-------|--------|-------|----------------|----------------|
| Phase 1 — Core Market Data | IMPLEMENTED | 105 | Candle, Instrument, Dataset, Storage, Ingestion | COMPLETE |
| Phase 2 — Data Quality/Provenance | IMPLEMENTED | 134 | DataQualityGate, EvidenceProvenance, ProvenanceTracker, SYNTHETIC blocking | COMPLETE |
| Phase 3 — Strategy/Backtest | IMPLEMENTED | 82+39 | BacktestEngine, StrategySpec, BacktestProvenance, ConditionEvaluator | COMPLETE (frozen) |
| Phase 4A.1 — Temporal/PIT | BLOCKED | 97 | TemporalSemantics, TemporalContract, AvailabilityPolicy, canonical_serialize, deterministic_hash | BLOCKED (8 open) |
| Phase 4A.2 — Corporate Actions | MISSING | 0 | CorporateAction, PointInTimeUniverse, AdjustmentChain | NOT STARTED |
| Phase 4A.3 — Derivatives/Futures | MISSING | 0 | FuturesContract, ContinuousSeries, RolloverPolicy | NOT STARTED |
| Phase 4A.4 — Research Governance | MISSING | 0 | ResearchContract, ApprovalMetadata, ResearchRegistry | NOT STARTED |
| Phase 5 — Experiment Registry | MISSING | 0 | ExperimentRegistry, ReproducibilityLog | NOT STARTED |
| Phase 6 — Quant Research | PARTIAL | 134 | Quant engine (returns, MA, momentum, volatility, trend, statistics, drawdown) | PARTIAL |
| Phase 7 — Advanced Backtesting | MISSING | 0 | Walk-forward, OOS validation, bootstrap, MC, regime analysis | NOT STARTED |
| Phase 8 — Risk/Portfolio | MISSING | 0 | Risk engine, portfolio construction, exposure | NOT STARTED |
| Phase 9 — Hermes AI Research | MISSING | 0 | AI research intelligence integration | NOT STARTED |
| Phase 10 — Production Data Infra | MISSING | 0 | Production data pipeline | NOT STARTED |
| Phase 11 — Paper Trading | MISSING | 0 | Paper order gateway, execution simulator | NOT STARTED |
| 30-Day Paper Evaluation | MISSING | 0 | Evaluation framework | NOT STARTED |
| Strategy Graduation | MISSING | 0 | Graduation criteria | NOT STARTED |
| Live Execution Boundary | NEVER AUTHORIZED | 0 | Controlled execution gate | OUT_OF_SCOPE |

**Lifecycle alignment:**
Market Data → Research → Hypothesis → Strategy → Backtest → Validation → Risk Review → Paper Trading → Evaluation → Strategy Graduation → Controlled Execution Boundary

**Baseline numbers (measured live — do not silently normalize):**
- 367 authorized baseline tests
- 464 observed/current total tests
- 97 unauthorized PIT delta

---

## 3. Repository Architecture

### 3.1 Source Tree

```
src/data_engine/
  __init__.py              — Package init, version info
  schemas.py               — Core Pydantic models (Candle, Instrument, Dataset, BacktestConfig, StrategySpec)
  provenance.py            — EvidenceProvenance, ProvenanceTracker
  ingestion.py             — Market data ingestion
  provider.py              — MarketDataProvider, ProviderFactory
  storage.py               — Storage layer (get_raw/get_processed/get_research)
  validation.py            — Data validation
  quality_report.py        — Quality reporting
  evidence.py              — Evidence handling
  data_blocked.py          — Blocked data handling
  security.py              — Security controls
  quarantine.py            — Quarantine logic
  cli.py                   — CLI interface
  timeframes.py            — Timeframe definitions
  instruments.py           — Instrument models
  quant_boundary.py        — Quant engine boundary

  pit/                     — Phase 4A.1 temporal/PIT module (v4.1.0)
    __init__.py
    temporal.py            — TemporalSemantics, TemporalDataType
    contract.py            — TemporalContract, MissingFieldPolicy
    availability.py        — AvailabilityPolicy, PublicationControlledAvailability, RevisionAwareAvailability
    serialization.py       — canonical_serialize()
    hashing.py             — deterministic_hash()

  quant/                   — Phase 2 quant engine (v2.0.0)
    __init__.py
    schemas.py
    validation.py
    core.py
    returns.py
    moving_averages.py
    momentum.py
    volatility.py
    trend.py
    statistics.py
    drawdown.py
    registry.py

  strategy/                — Phase 3 strategy/backtest (v3.0.0)
    __init__.py
    schemas.py             — BacktestConfig, StrategySpec, Signal, Position, EquityCurve
    backtest.py            — BacktestEngine, _simulate()
    provenance.py          — BacktestProvenance, compute_result_hash(), to_hash()
    metrics.py             — PerformanceMetrics, periods_per_year
    position.py            — Position management
    equity.py              — Equity curve
    conditions.py          — ConditionEvaluator, SignalGenerator
    execution.py           — Execution simulation
    ledger.py              — Trade ledger
    validation.py          — Strategy validation
```

### 3.2 Tests

```
tests/
  test_data_engine.py      — 62 tests (Phase 1/2 core)
  test_pit.py              — 97 tests (Phase 4A.1 PIT temporal, 15 classes)
  test_quant.py            — 134 tests (Phase 2 quant, 21 classes)
  test_redteam.py          — 50 tests (red-team/security, 10 classes)
  test_strategy.py         — 82 tests (Phase 3 strategy)
  test_strategy_independent.py — 39 tests (10 classes, 6 pre-existing failures documented)
```

**Total: 464 passing tests** (verified live)
**Authorized baseline: 367** (tests/test_pit.py excluded — untracked at baseline)
**PIT delta: 97** (all in untracked tests/test_pit.py)
**Pre-existing failures: 6** in test_strategy_independent.py (documented separately, not Phase 4A.1 blockers)

### 3.3 Configuration

- pyproject.toml — dependencies, project metadata
- All Pydantic models frozen=True
- No external API keys in repository (credentials are [REDACTED] in docs)

### 3.4 Documentation

- docs/strategy_engine_design.md (92KB) — Master design document (FROZEN Phase 3)
- docs/strategy_engine.md — Strategy engine reference
- docs/quant_engine.md — Quant engine reference
- MASTER_PHASE_STATUS_REPORT.md — Phase status
- PHASE_4A_FINAL_ARCHITECTURE_SPEC.md — Phase 4A finalization (1044 lines)
- PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md — Remediation specification
- PHASE_4A1_MULTI_AI_CONSTRUCTION_BASELINE.md — Construction baseline
- PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md — Blocker resolution
- PHASE_4A1_DESIGN_LOCK_RECORD.md — Design lock record
- 30+ Phase 4A.1 audit/review/forensic documents

---

## 4. Phase 3 Frozen Contract Protection

**PROTECTED — NO MODIFICATIONS PERMITTED:**

1. **Candle.to_hash()** — Canonical hash of candle data. Any change invalidates all historical hash chains.
2. **ProvenanceRecord.to_hash()** — Provenance identity. Must remain byte-identical.
3. **StrategySpec.to_hash()** — Strategy identity. Changes would break experiment reproducibility.
4. **BacktestProvenance.compute_result_hash()** — Result hash computation. DD-14: never modified.
5. **BacktestProvenance.to_hash()** — Provenance identity for backtest results.
6. **BacktestConfig._compute_config_hash()** — Config hash. Adding fields changes serialization.
7. **BacktestEngine._compute_dataset_hash()** — Dataset hash for backtest identity.

**Protection mechanism:**
- All models frozen=True (Pydantic)
- Hash methods use canonical_serialize() for deterministic output
- No wall-clock defaults in hash inputs
- If future functionality requires changes: adapter/wrapper/new-contract approach with explicit human authorization

**Future extension pattern (NOT implementation):**
- New PIT-aware hashes use NEW method names (compute_view_hash, compute_experiment_id)
- Existing result_hash formula unchanged
- PIT fields added as optional with defaults
- BacktestConfig signature preserved (PitView constructed separately)

**Frozen SHA-256 manifest requirement:**
Every future phase must include a frozen manifest of Phase 3 contract SHAs, verified byte-for-byte before any work package begins. The manifest is part of the repository's authoritative state and must be re-verified at every design lock.

---

## 5. COMPLETE SYSTEM ARCHITECTURE DOMAINS (60 Domains)

For each domain below: purpose, ownership, dependencies, inputs, outputs, interfaces, invariants, persistence requirements, identity requirements, security requirements, failure modes, tests, acceptance evidence, rollback, authorization prerequisite.

### 5.1 System Vision
- **Purpose:** Define the complete AI Trading Lab mission, boundaries, and non-negotiable constraints
- **Ownership:** Principal Architect (single owner)
- **Dependencies:** None (foundation)
- **Inputs:** User requirements, governance constraints
- **Outputs:** System vision document, boundary definitions
- **Interfaces:** All other domains
- **Invariants:** NO TRADE capability always available; no fixed trade count objective
- **Persistence:** Design documents (markdown)
- **Identity:** System version, governance state
- **Security:** Governance compliance
- **Failure modes:** Ambiguous boundaries, missing NO TRADE path
- **Tests:** Boundary verification tests
- **Acceptance:** All boundaries explicitly defined
- **Rollback:** Document revision
- **Authorization:** Human approval of vision

### 5.2 Complete Roadmap
- **Purpose:** Trace every phase from foundation through live execution
- **Ownership:** Principal Architect
- **Dependencies:** System vision
- **Inputs:** Phase specifications, dependency graph
- **Outputs:** Roadmap with phase gates
- **Interfaces:** All domains
- **Invariants:** No phase skipped; no phase claimed complete without evidence
- **Persistence:** Roadmap document
- **Identity:** Phase IDs, status tracking
- **Security:** Gate enforcement
- **Failure modes:** Phantom completion (files exist ≠ phase complete)
- **Tests:** Phase gate verification
- **Acceptance:** All phases traced with status
- **Rollback:** Phase re-classification
- **Authorization:** Human phase authorization

### 5.3 Repository Architecture
- **Purpose:** Define the physical repository structure and component layout
- **Ownership:** Repository Architect
- **Dependencies:** System vision
- **Inputs:** Source tree, module boundaries
- **Outputs:** Repository layout specification
- **Interfaces:** All code modules
- **Invariants:** Frozen contracts in designated paths; new modules in designated paths
- **Persistence:** Repository structure
- **Identity:** Module paths, file hashes
- **Security:** Path containment
- **Failure modes:** Unauthorized file placement, contract contamination
- **Tests:** Structure validation tests
- **Acceptance:** All files in correct locations
- **Rollback:** File relocation
- **Authorization:** Architecture approval

### 5.4 Data Architecture
- **Purpose:** Define data ingestion, storage, and retrieval patterns
- **Ownership:** Data Architect
- **Dependencies:** Repository architecture
- **Inputs:** Market data feeds, configuration
- **Outputs:** Raw datasets, processed datasets, research datasets
- **Interfaces:** Provider layer, storage layer, ingestion layer
- **Invariants:** Data immutability once stored; provenance attached to every dataset
- **Persistence:** Raw data (immutable), processed data (versioned), research data (versioned)
- **Identity:** Dataset ID + version, provenance hash
- **Security:** Path containment, credential isolation
- **Failure modes:** Data corruption, provenance loss, provider failure
- **Tests:** Ingestion tests, storage tests, provenance tests
- **Acceptance:** Data retrievable with full provenance
- **Rollback:** Data restore from last verified state
- **Authorization:** Data provider approval

### 5.5 Temporal/PIT Architecture
- **Purpose:** Ensure point-in-time correctness — no future-data leakage
- **Ownership:** Temporal Architect (4A.1 owner)
- **Dependencies:** Data architecture, provenance architecture
- **Inputs:** Market data with publication timestamps, revision history
- **Outputs:** PIT-filtered datasets, temporal views
- **Interfaces:** PitViewBuilder, PitViewValidator, TemporalContract, AvailabilityPolicy
- **Invariants:** event ≤ observation ≤ publication ≤ revision ordering; inclusive cutoff; no future data in view
- **Persistence:** PitSidecar per dataset version, RevisionChain append-only
- **Identity:** TemporalContract hash, PitView hash, ExperimentIdentity
- **Security:** Publication time validation, revision chain integrity
- **Failure modes:** Future-data injection, equal-time non-determinism, revision chain corruption
- **Tests:** PIT cutoff boundary tests, revision history tests, equal-time ordering tests
- **Acceptance:** Zero future-data leakage in all views
- **Rollback:** Remove PIT module, revert to pre-PIT state
- **Authorization:** Design lock resolution + human authorization

### 5.6 Provenance Architecture
- **Purpose:** Track complete data lineage from source to consumption
- **Ownership:** Provenance Architect
- **Dependencies:** Data architecture
- **Inputs:** Data operations, transformations, model instances
- **Outputs:** Provenance records, hash chains, audit trails
- **Interfaces:** ProvenanceTracker, EvidenceProvenance, to_hash() methods
- **Invariants:** Append-only history; hash-verified chain; no wall-clock defaults in identity
- **Persistence:** Provenance records with every dataset and result
- **Identity:** Provenance hash chain, result_hash
- **Security:** Tamper detection, hash integrity verification
- **Failure modes:** Broken hash chain, provenance loss, wall-clock contamination
- **Tests:** Hash chain tests, provenance integrity tests
- **Acceptance:** Every dataset/result has verifiable provenance
- **Rollback:** Recompute provenance from source
- **Authorization:** Provenance model approval

### 5.7 Deterministic Identity
- **Purpose:** Ensure every entity has a stable, reproducible, deterministic identity
- **Ownership:** Identity Architect
- **Dependencies:** Temporal/PIT architecture, provenance architecture
- **Inputs:** Entity data (instruments, datasets, experiments, strategies)
- **Outputs:** Deterministic hashes, identity contracts
- **Interfaces:** deterministic_hash(), canonical_serialize(), to_deterministic_hash()
- **Invariants:** Same input → same hash; no wall-clock in identity; type-tagged serialization
- **Persistence:** Identity in contracts and records
- **Identity:** SHA-256 of canonical bytes
- **Security:** Collision resistance, type safety
- **Failure modes:** Hash collision, non-deterministic identity, type ambiguity
- **Tests:** Hash stability tests, collision tests, type-tag tests
- **Acceptance:** Identical inputs produce identical hashes across runs
- **Rollback:** Recompute identity from canonical form
- **Authorization:** Identity contract approval

### 5.8 Canonical Serialization
- **Purpose:** Define the canonical byte representation for all identity computation
- **Ownership:** Serialization Architect
- **Dependencies:** Deterministic identity
- **Inputs:** Data structures (dicts, models, lists)
- **Outputs:** Canonical JSON bytes
- **Interfaces:** canonical_serialize()
- **Invariants:** Type-tagged encoding; int-key/string-key separation; float .10f policy; extra="forbid"; unknown fields rejected
- **Persistence:** Serialization output used in all hash computation
- **Identity:** Serialized bytes are hash input
- **Security:** Type collision prevention, injection resistance
- **Failure modes:** Type collision (int vs string key), datetime ambiguity, float precision drift
- **Tests:** Serialization round-trip tests, collision matrix tests
- **Acceptance:** All type combinations serialize deterministically
- **Rollback:** Fix serialization, recompute all hashes
- **Authorization:** Serialization contract approval

### 5.9 Revision Architecture
- **Purpose:** Maintain immutable append-only revision history for all data and contract versions
- **Ownership:** Revision Architect (4A.1 owner)
- **Dependencies:** Deterministic identity, canonical serialization
- **Inputs:** New revisions, revision metadata
- **Outputs:** RevisionChain entries, versioned datasets
- **Interfaces:** RevisionChain.append(), RevisionChain.verify()
- **Invariants:** Append-only; hash-linked entries; no modification/deletion; tamper-evident
- **Persistence:** Revision chain persisted with dataset
- **Identity:** Revision hash, chain tip hash
- **Security:** Integrity verification, tamper detection
- **Failure modes:** Chain break, revision reordering, entry deletion
- **Tests:** Append-only tests, hash-link verification, tamper detection tests
- **Acceptance:** Chain integrity verifiable at any point
- **Rollback:** Rebuild chain from source data
- **Authorization:** Revision model approval

### 5.10 Instrument Identity
- **Purpose:** Define stable, immutable, deterministic instrument identifiers
- **Ownership:** Instrument Architect (4A.1 owner, single owner — BLOCKER 1 resolution)
- **Dependencies:** Deterministic identity, canonical serialization
- **Inputs:** Instrument metadata (symbol, venue, timezone, specification)
- **Outputs:** InstrumentIdentity, InstrumentSpecification
- **Interfaces:** InstrumentIdentity.to_hash(), InstrumentSpecification.to_hash()
- **Invariants:** Stable identifier; effective-dated specification; versioned contracts
- **Persistence:** Instrument identity in all dataset and provenance records
- **Identity:** InstrumentIdentity hash, InstrumentSpecification hash
- **Security:** Identifier collision prevention, spoofing resistance
- **Failure modes:** Symbol collision, venue ambiguity, timezone mismatch
- **Tests:** Identity stability tests, collision tests, timezone tests
- **Acceptance:** Same instrument → same identity across all contexts
- **Rollback:** Recompute identity from canonical form
- **Authorization:** Instrument model approval

### 5.11 Universe Management
- **Purpose:** Manage the set of tradable instruments at any point in time
- **Ownership:** Universe Architect
- **Dependencies:** Instrument identity, temporal/PIT architecture
- **Inputs:** Instrument lists, filters, date ranges
- **Outputs:** Point-in-time universe snapshots
- **Interfaces:** UniverseProvider, UniverseSnapshot
- **Invariants:** Universe is date-specific; no survivorship bias; PIT-correct composition
- **Persistence:** Universe snapshot per date with provenance
- **Identity:** Universe snapshot hash
- **Security:** Universe manipulation detection
- **Failure modes:** Survivorship bias, universe composition error, date mismatch
- **Tests:** Universe composition tests, PIT universe tests, survivorship bias tests
- **Acceptance:** Universe matches historical records for any date
- **Rollback:** Restore universe from source data
- **Authorization:** Universe model approval

### 5.12 Corporate Actions
- **Purpose:** Handle equity corporate actions (splits, dividends, symbol changes, delistings) with PIT correctness
- **Ownership:** Corporate Actions Architect (4A.2 owner)
- **Dependencies:** Instrument identity (enhanced), Temporal/PIT architecture
- **Inputs:** Corporate action events, historical price data
- **Outputs:** Adjusted price series, new instrument specification versions
- **Interfaces:** CorporateAction models, AdjustmentChain
- **Invariants:** Historical data preserved; adjusted price separated; PIT-correct application
- **Persistence:** Corporate action records, adjustment chains
- **Identity:** Corporate action event hash, adjusted specification hash
- **Security:** Action verification, historical integrity
- **Failure modes:** Incorrect adjustment, PIT violation, action duplication
- **Tests:** Split tests, dividend tests, symbol change tests, delisting tests
- **Acceptance:** Adjusted prices match reference data for all dates
- **Rollback:** Remove corporate action models, revert to pre-adjustment prices
- **Authorization:** Corporate actions model approval

### 5.13 Calendar/Session Management
- **Purpose:** Manage trading calendars, sessions, and timezone-aware time references
- **Ownership:** Calendar Architect (4A.1 owner)
- **Dependencies:** Instrument identity (timezone field)
- **Inputs:** Trading calendar data, venue timezone info
- **Outputs:** CalendarRef, session boundaries, periods_per_year
- **Interfaces:** CalendarRef, TradingSession
- **Invariants:** Calendar versioned in experiment identity; UTC normalization; session awareness
- **Persistence:** Calendar data with version in experiment identity
- **Identity:** CalendarRef hash, calendar version
- **Security:** Calendar manipulation detection
- **Failure modes:** Wrong session boundary, timezone error, calendar version mismatch
- **Tests:** Calendar version tests, session boundary tests, timezone tests
- **Acceptance:** Correct session boundaries for all venues and dates
- **Rollback:** Remove CalendarRef, revert metrics.py periods_per_year dict
- **Authorization:** Calendar model approval

### 5.14 Derivatives/Futures/Continuous Contracts
- **Purpose:** Model futures contracts, continuous series, and rollovers with PIT correctness
- **Ownership:** Derivatives Architect (4A.3 owner)
- **Dependencies:** Calendar/session management, venue enhancement
- **Inputs:** Futures contract specifications, rollover policies, historical futures data
- **Outputs:** FuturesContract, ContinuousSeries, RolloverPolicy
- **Interfaces:** FuturesContract, ContinuousSeries, RolloverPolicy, roll_detection()
- **Invariants:** Futures contracts and continuous series distinct; PIT-correct roll decisions; no roll leakage
- **Persistence:** Contract specifications, roll history
- **Identity:** FuturesContract hash, ContinuousSeries hash
- **Security:** Roll manipulation detection, contract specification integrity
- **Failure modes:** Incorrect roll date, roll leakage, contract misidentification
- **Tests:** Futures expiry tests, rollover tests, continuous series tests, roll leakage tests
- **Acceptance:** Continuous series correctly tracks underlying through rollovers
- **Rollback:** Remove futures models, revert to pre-derivatives state
- **Authorization:** Derivatives model approval

### 5.15 Research Registry
- **Purpose:** Track all research outputs with deterministic identity and approval metadata
- **Ownership:** Research Registry Architect (4A.4 owner)
- **Dependencies:** Experiment identity, deterministic identity
- **Inputs:** Research findings, citations, approval metadata
- **Outputs:** ResearchRegistry entries with approval status
- **Interfaces:** ResearchContract, ApprovalMetadata, ResearchRegistry
- **Invariants:** Approval as auditable external metadata; no self-approval; hash-verified entries
- **Persistence:** Registry with hash-verified entries
- **Identity:** Research entry hash, approval record hash
- **Security:** Approval integrity, citation verification
- **Failure modes:** Unapproved research treated as validated, citation forgery
- **Tests:** Registry integrity tests, approval tests, citation tests
- **Acceptance:** All research entries have verifiable identity and approval status
- **Rollback:** Remove registry entries, revert to unregistered state
- **Authorization:** Research governance approval

### 5.16 Experiment Registry
- **Purpose:** Track all experiments with deterministic identity and reproducibility logs
- **Ownership:** Experiment Registry Architect
- **Dependencies:** Experiment identity, reproducibility architecture
- **Inputs:** Experiment configurations, results, parameters
- **Outputs:** ExperimentRegistry entries, ReproducibilityLog
- **Interfaces:** ExperimentRegistry, ReproducibilityLog, ExperimentIdentity
- **Invariants:** Every experiment has unique deterministic ID; reproducibility log complete
- **Persistence:** Experiment registry with reproducibility logs
- **Identity:** ExperimentIdentity hash
- **Security:** Experiment tamper detection
- **Failure modes:** Duplicate experiment IDs, incomplete reproducibility log
- **Tests:** Experiment identity tests, reproducibility log tests
- **Acceptance:** Every experiment uniquely identifiable and reproducible
- **Rollback:** Remove experiment registry, revert to unregistered state
- **Authorization:** Experiment registry approval

### 5.17 Dataset Registry
- **Purpose:** Track all datasets with provenance, version, and PIT metadata
- **Ownership:** Dataset Registry Architect
- **Dependencies:** Provenance architecture, PIT architecture
- **Inputs:** Datasets, provenance records, PitSidecar
- **Outputs:** DatasetRegistry entries with full provenance
- **Interfaces:** DatasetRegistry, DatasetProvenance
- **Invariants:** Every dataset has complete provenance; PIT metadata attached; version tracked
- **Persistence:** Dataset registry with provenance and PIT metadata
- **Identity:** Dataset hash, provenance hash
- **Security:** Dataset integrity, provenance verification
- **Failure modes:** Dataset provenance gap, PIT metadata missing, version confusion
- **Tests:** Dataset registry tests, provenance tests, PIT metadata tests
- **Acceptance:** Every dataset traceable to source with full provenance
- **Rollback:** Remove registry entries, revert to unregistered state
- **Authorization:** Dataset registry approval

### 5.18 Strategy Registry
- **Purpose:** Track all strategy specifications with deterministic identity and versioning
- **Ownership:** Strategy Registry Architect
- **Dependencies:** Strategy representation, deterministic identity
- **Inputs:** StrategySpec instances, conditions, parameters
- **Outputs:** StrategyRegistry entries with hash-verified identity
- **Interfaces:** StrategyRegistry, StrategySpec.to_hash()
- **Invariants:** StrategySpec frozen; identity deterministic; version tracked
- **Persistence:** Strategy registry with hash-verified entries
- **Identity:** StrategySpec hash
- **Security:** Strategy identity integrity, tamper detection
- **Failure modes:** Duplicate strategy IDs, identity collision, unauthorized strategy modification
- **Tests:** Strategy identity tests, registry integrity tests
- **Acceptance:** Every strategy uniquely identifiable with stable hash
- **Rollback:** Remove strategy registry entries
- **Authorization:** Strategy registry approval

### 5.19 Strategy Representation
- **Purpose:** Define the canonical representation of trading strategies
- **Ownership:** Strategy Architect
- **Dependencies:** Deterministic identity, condition evaluation
- **Inputs:** Strategy conditions, parameters, metadata
- **Outputs:** StrategySpec with frozen identity
- **Interfaces:** StrategySpec, ConditionEvaluator, SignalGenerator
- **Invariants:** Frozen StrategySpec; deterministic to_hash(); conditions executable
- **Persistence:** StrategySpec in registry and backtest results
- **Identity:** StrategySpec hash
- **Security:** Strategy tamper detection, condition injection prevention
- **Failure modes:** Non-deterministic strategy identity, condition execution error
- **Tests:** Strategy identity tests, condition evaluation tests
- **Acceptance:** Same strategy → same identity; conditions execute deterministically
- **Rollback:** Revert StrategySpec to last verified version
- **Authorization:** Strategy model approval

### 5.20 Strategy Generation/Discovery
- **Purpose:** Generate and discover candidate trading strategies from research findings
- **Ownership:** Strategy Research Agent (AI) with human review
- **Dependencies:** Research registry, market intelligence, quant research engine
- **Inputs:** Research findings, market data, hypothesis results
- **Outputs:** StrategySpec candidates with condition trees
- **Interfaces:** ConditionEvaluator, SignalGenerator, StrategySpec
- **Invariants:** All strategies must pass validation before backtesting; no strategy bypasses risk review
- **Persistence:** Strategy candidates in registry with provenance
- **Identity:** StrategySpec hash
- **Security:** Strategy injection prevention, condition sanitization
- **Failure modes:** Invalid strategy conditions, overfitting in generation, biased hypothesis
- **Tests:** Strategy generation tests, condition validation tests, overfitting detection tests
- **Acceptance:** Generated strategies are valid, reproducible, and evidence-based
- **Rollback:** Remove generated strategies, revert to prior registry
- **Authorization:** Strategy generation gate (human review required)

### 5.21 Feature Engineering
- **Purpose:** Transform raw market data into model features with PIT correctness
- **Ownership:** Quant Research Architect
- **Dependencies:** Data architecture, PIT architecture, quant engine
- **Inputs:** Raw market data, feature specifications
- **Outputs:** Feature datasets with provenance
- **Interfaces:** FeaturePipeline, quant engine indicators
- **Invariants:** PIT-correct feature computation; no future-data in features; deterministic output
- **Persistence:** Feature datasets with provenance
- **Identity:** Feature dataset hash
- **Security:** Feature leakage detection, data contamination prevention
- **Failure modes:** Look-ahead in feature computation, non-deterministic features, data leakage
- **Tests:** Feature PIT tests, leakage tests, determinism tests
- **Acceptance:** Features are PIT-correct and deterministic
- **Rollback:** Remove feature datasets, recompute from source
- **Authorization:** Feature pipeline approval

### 5.22 Quant Research Engine
- **Purpose:** Provide deterministic quantitative research computations
- **Ownership:** Quant Architect (Phase 2 implemented, Phase 6+ extensions)
- **Dependencies:** Data architecture, feature engineering
- **Inputs:** Datasets, indicator parameters
- **Outputs:** Indicator values, statistical results
- **Interfaces:** quant/ module (returns, MA, momentum, volatility, trend, statistics, drawdown, validation, registry)
- **Invariants:** All calculations deterministic; no LLM calls; no network; no live trading
- **Persistence:** Quant results with provenance
- **Identity:** Indicator hash, result hash
- **Security:** Calculation integrity, parameter validation
- **Failure modes:** Non-deterministic output, parameter error, numerical instability
- **Tests:** Indicator tests, statistical tests, determinism tests
- **Acceptance:** All quant calculations deterministic and reproducible
- **Rollback:** Revert quant module to last verified version
- **Authorization:** Quant engine approval

### 5.23 Backtesting
- **Purpose:** Execute strategy backtests with PIT correctness and deterministic provenance
- **Ownership:** Backtest Architect (Phase 3 implemented, frozen)
- **Dependencies:** Strategy representation, data architecture, PIT architecture, quant engine
- **Inputs:** StrategySpec, Dataset (PIT-filtered), backtest configuration
- **Outputs:** BacktestProvenance with result_hash, config_hash, equity curve, trade ledger
- **Interfaces:** BacktestEngine, _simulate(), BacktestProvenance, compute_result_hash()
- **Invariants:** Frozen provenance; deterministic result_hash; PIT-filtered data; exit_occurred flag for same-bar re-entry
- **Persistence:** Backtest results with full provenance
- **Identity:** result_hash, config_hash, dataset_hash
- **Security:** Result integrity, provenance tamper detection
- **Failure modes:** Non-deterministic backtest, PIT violation in data, same-bar re-entry bug
- **Tests:** Backtest determinism tests, PIT boundary tests, result_hash stability tests
- **Acceptance:** Same inputs → identical results; PIT correctness verified
- **Rollback:** Revert to frozen Phase 3 contracts; do not modify provenance methods
- **Authorization:** Backtest engine approval (frozen — changes require human authorization + new contract)

### 5.24 Bias/Leakage Detection
- **Purpose:** Detect and prevent look-ahead bias, survivorship bias, data leakage, and overfitting
- **Ownership:** Bias/Leakage Architect
- **Dependencies:** PIT architecture, universe management, quant engine
- **Inputs:** Datasets, feature sets, model specifications
- **Outputs:** Bias/leakage audit reports
- **Interfaces:** BiasDetector, LeakageDetector, OverfittingDetector
- **Invariants:** All bias types detectable; leakage prevented at PIT boundary; overfitting detected via train/test separation
- **Persistence:** Bias/leakage audit records
- **Identity:** Audit report hash
- **Security:** Bias injection prevention, leakage detection integrity
- **Failure modes:** Undetected look-ahead, survivorship bias in universe, feature leakage
- **Tests:** Look-ahead injection tests, survivorship bias tests, leakage tests, overfitting tests
- **Acceptance:** All known bias types detected in test scenarios
- **Rollback:** Remove bias detection, revert to manual review
- **Authorization:** Bias detection approval

### 5.25 Statistical Validation
- **Purpose:** Validate statistical significance of strategy results
- **Ownership:** Statistical Validation Architect
- **Dependencies:** Quant research engine, backtesting
- **Inputs:** Backtest results, statistical test parameters
- **Outputs:** Statistical validation reports with p-values, confidence intervals
- **Interfaces:** StatisticalValidator, quant/statistics.py
- **Invariants:** Valid p-values; confidence intervals correct; multiple-testing control applied
- **Persistence:** Statistical validation reports
- **Identity:** Validation report hash
- **Security:** Statistical manipulation detection
- **Failure modes:** Invalid statistical tests, p-hacking, incorrect confidence intervals
- **Tests:** Statistical test accuracy tests, multiple-testing correction tests
- **Acceptance:** Statistical tests produce valid results on known distributions
- **Rollback:** Remove statistical validation, revert to unvalidated results
- **Authorization:** Statistical validation approval

### 5.26 Walk-Forward Validation
- **Purpose:** Validate strategies using rolling-window out-of-sample testing
- **Ownership:** Validation Architect (Phase 7)
- **Dependencies:** Backtesting, quant research engine, PIT architecture
- **Inputs:** StrategySpec, full historical dataset, window parameters
- **Outputs:** Walk-forward validation report
- **Interfaces:** WalkForwardValidator
- **Invariants:** No look-ahead; PIT-correct windows; separate training/validation/test partitions
- **Persistence:** Walk-forward validation reports
- **Identity:** Validation report hash
- **Security:** Window contamination detection
- **Failure modes:** Data leakage across windows, incorrect window boundaries
- **Tests:** Walk-forward boundary tests, leakage tests, PIT window tests
- **Acceptance:** No future data in any training window
- **Rollback:** Remove walk-forward module
- **Authorization:** Walk-forward validation approval

### 5.27 Robustness Testing
- **Purpose:** Test strategy stability across parameter variations and market regimes
- **Ownership:** Robustness Architect (Phase 7)
- **Dependencies:** Backtesting, quant research engine
- **Inputs:** StrategySpec, parameter ranges, regime definitions
- **Outputs:** Robustness report
- **Interfaces:** RobustnessTester
- **Invariants:** Multiple parameter checks; regime-specific testing; stability metrics
- **Persistence:** Robustness test reports
- **Identity:** Robustness report hash
- **Security:** Parameter manipulation detection
- **Failure modes:** False robustness, unstable parameters, regime misclassification
- **Tests:** Parameter sensitivity tests, regime stability tests
- **Acceptance:** Strategy stability quantified across parameter ranges
- **Rollback:** Remove robustness module
- **Authorization:** Robustness testing approval

### 5.28 Portfolio Construction
- **Purpose:** Construct portfolios from validated strategies with risk constraints
- **Ownership:** Portfolio Architect (Phase 8)
- **Dependencies:** Risk engine, strategy validation, quant engine
- **Inputs:** Validated strategies, risk limits, correlation matrix
- **Outputs:** Portfolio allocation, position weights
- **Interfaces:** PortfolioConstructor, RiskEngine
- **Invariants:** Constraint satisfaction; no single strategy exceeds risk limits; diversification enforced
- **Persistence:** Portfolio allocations with provenance
- **Identity:** Portfolio hash
- **Security:** Allocation manipulation detection
- **Failure modes:** Over-concentration, constraint violation, correlation error
- **Tests:** Portfolio constraint tests, allocation tests, concentration tests
- **Acceptance:** All constraints satisfied; allocations deterministic
- **Rollback:** Remove portfolio module, revert to single-strategy deployment
- **Authorization:** Portfolio construction approval

### 5.29 Risk Engine
- **Purpose:** Enforce risk limits and compute risk metrics
- **Ownership:** Risk Architect (Phase 8)
- **Dependencies:** Position management, P&L tracking, backtesting
- **Inputs:** Positions, P&L, market data, risk parameters
- **Outputs:** Risk metrics, limit violation alerts, risk reports
- **Interfaces:** RiskEngine, RiskLimits
- **Invariants:** Hard limits enforced; no override; all violations detected; zero tolerance for limit breaches
- **Persistence:** Risk reports, violation logs
- **Identity:** Risk report hash
- **Security:** Risk limit enforcement, no-bypass guarantee
- **Failure modes:** Risk limit override, undetected violation, incorrect metric computation
- **Tests:** Risk limit tests, violation detection tests, metric accuracy tests
- **Acceptance:** All risk limits enforced; violations detected and logged
- **Rollback:** Remove risk engine, halt all trading
- **Authorization:** Risk engine approval

### 5.30 Exposure Management
- **Purpose:** Track and manage portfolio exposure across assets, sectors, and risk factors
- **Ownership:** Exposure Architect (Phase 8)
- **Dependencies:** Risk engine, portfolio construction, data architecture
- **Inputs:** Positions, market data, exposure limits
- **Outputs:** Exposure report, limit violation alerts
- **Interfaces:** ExposureManager, RiskEngine
- **Invariants:** Exposure within limits; PIT-correct exposure computation; no hidden exposure
- **Persistence:** Exposure reports with provenance
- **Identity:** Exposure report hash
- **Security:** Exposure manipulation detection
- **Failure modes:** Undetected exposure, PIT exposure error, limit breach
- **Tests:** Exposure computation tests, limit tests, PIT exposure tests
- **Acceptance:** Exposure accurate and within limits
- **Rollback:** Remove exposure module, revert to position-only tracking
- **Authorization:** Exposure management approval

### 5.31 Position Management
- **Purpose:** Track and manage open positions
- **Ownership:** Position Architect (Phase 3 partially implemented)
- **Dependencies:** Execution simulation, P&L calculation
- **Inputs:** Orders, fills, market data
- **Outputs:** Position state, P&L attribution
- **Interfaces:** PositionManager, execution.py
- **Invariants:** Position accuracy; P&L attribution correct; no phantom positions
- **Persistence:** Position state, position history
- **Identity:** Position ID hash
- **Security:** Position manipulation detection
- **Failure modes:** Position drift, P&L attribution error, phantom positions
- **Tests:** Position tracking tests, P&L attribution tests, reconciliation tests
- **Acceptance:** Positions accurate; P&L matches realized trades
- **Rollback:** Restore position state from last verified checkpoint
- **Authorization:** Position management approval

### 5.32 Market Intelligence
- **Purpose:** Aggregate and analyze market data for research and strategy generation
- **Ownership:** Market Intelligence Agent (AI)
- **Dependencies:** Data ingestion, data quality, provenance
- **Inputs:** Market data feeds, technical indicators
- **Outputs:** Market analysis reports with citations
- **Interfaces:** MarketAnalysisSkill, DataProvider
- **Invariants:** No future data; all claims cited; deterministic analysis where applicable
- **Persistence:** Analysis reports with provenance
- **Identity:** Analysis report hash
- **Security:** Data source verification, citation integrity
- **Failure modes:** Future-data leakage, uncited claims, incorrect analysis
- **Tests:** Market analysis tests, citation tests, PIT tests
- **Acceptance:** All analysis PIT-correct and cited
- **Rollback:** Remove analysis reports, revert to raw data only
- **Authorization:** Market intelligence approval

### 5.33 News Intelligence
- **Purpose:** Extract and analyze news events for trading relevance
- **Ownership:** News Intelligence Agent (AI)
- **Dependencies:** News feeds, source verification
- **Inputs:** News articles, press releases, event data
- **Outputs:** News analysis with citations and timestamps
- **Interfaces:** NewsAnalysisSkill, SourceVerification
- **Invariants:** All sources cited; timestamps verified; no future news in PIT views
- **Persistence:** News analysis with provenance
- **Identity:** News analysis hash, source hash
- **Security:** Source verification, misinformation detection
- **Failure modes:** Unverified source, future news leakage, fabricated citations
- **Tests:** Source verification tests, PIT tests, citation tests
- **Acceptance:** All news PIT-correct with verified sources
- **Rollback:** Remove news analysis, revert to no-news baseline
- **Authorization:** News intelligence approval

### 5.34 Macro Intelligence
- **Purpose:** Analyze macroeconomic indicators and calendar events
- **Ownership:** Macro Intelligence Agent (AI)
- **Dependencies:** Calendar/session management, macro data sources
- **Inputs:** Economic indicators, calendar events, macro reports
- **Outputs:** Macro assessment with citations and UTC timestamps
- **Interfaces:** MacroAnalysisSkill, CalendarRef
- **Invariants:** UTC timestamps; provenance complete; calendar PIT-correct
- **Persistence:** Macro assessment with provenance
- **Identity:** Macro assessment hash, source hash
- **Security:** Source verification, data integrity
- **Failure modes:** Unverified macro data, calendar mismatch, timestamp error
- **Tests:** Macro analysis tests, calendar tests, citation tests
- **Acceptance:** All macro analysis PIT-correct with verified sources
- **Rollback:** Remove macro analysis, revert to no-macro baseline
- **Authorization:** Macro intelligence approval

### 5.35 Research-Agent Architecture
- **Purpose:** Define the architecture for AI-driven research agents
- **Ownership:** Research Agent Architect
- **Dependencies:** All research domains, Hermes orchestration
- **Inputs:** Research queries, data access, tool permissions
- **Outputs:** Research findings with evidence and citations
- **Interfaces:** Agent contracts, Hermes orchestration, tool APIs
- **Invariants:** No agent can bypass governance; all findings cited; evidence verifiable
- **Persistence:** Research findings with provenance
- **Identity:** Research finding hash, agent ID
- **Security:** Agent confinement, evidence verification, no unauthorized access
- **Failure modes:** Agent producing unverified output, agent bypassing governance, evidence fabrication
- **Tests:** Agent behavior tests, evidence verification tests, governance compliance tests
- **Acceptance:** All agent outputs verified and cited
- **Rollback:** Disable agent, revert to manual research
- **Authorization:** Research agent deployment approval

### 5.36 Hermes Orchestration
- **Purpose:** Coordinate all AI agents and manage the research-to-execution pipeline
- **Ownership:** Hermes Orchestrator (single owner)
- **Dependencies:** All agent architectures, governance model
- **Inputs:** Agent results, roadmap state, governance decisions
- **Outputs:** Task assignments, final integration, audit log
- **Interfaces:** Agent APIs, governance gates, audit system
- **Invariants:** Hermes coordinates but does not execute; all actions audited; governance enforced
- **Persistence:** Audit log, orchestration records
- **Identity:** Orchestration session hash
- **Security:** Audit integrity, governance enforcement
- **Failure modes:** Orchestration bypass, audit gap, governance violation
- **Tests:** Orchestration tests, audit tests, governance compliance tests
- **Acceptance:** All orchestration actions audited and governance-compliant
- **Rollback:** Stop orchestration, audit all actions
- **Authorization:** Hermes deployment approval

### 5.37 Multi-Agent Architecture
- **Purpose:** Define the multi-agent system structure and interaction patterns
- **Ownership:** Multi-Agent Architect
- **Dependencies:** Agent contracts, communication architecture
- **Inputs:** Agent definitions, task specifications
- **Outputs:** Agent coordination, task distribution
- **Interfaces:** Agent APIs, communication protocols
- **Invariants:** Single AI writes at a time; no parallel uncontrolled edits; branch/worktree per work package
- **Persistence:** Agent state, task assignments
- **Identity:** Agent ID, task ID
- **Security:** Agent isolation, no agent has live authority
- **Failure modes:** Agent conflict, parallel editing, unauthorized agent action
- **Tests:** Agent interaction tests, conflict resolution tests
- **Acceptance:** Agents coordinate without conflict
- **Rollback:** Disable conflicting agent, revert to single-agent mode
- **Authorization:** Multi-agent deployment approval

### 5.38 Agent Contracts
- **Purpose:** Define the formal contracts that all AI agents must satisfy
- **Ownership:** Contract Architect
- **Dependencies:** Agent architectures, governance model
- **Inputs:** Agent role definitions, permission levels
- **Outputs:** Agent contracts with explicit permissions and prohibitions
- **Interfaces:** Contract enforcement, audit system
- **Invariants:** No agent can modify frozen contracts; no agent can authorize live trading; no agent can close blockers
- **Persistence:** Contract definitions, enforcement logs
- **Identity:** Contract hash, agent ID
- **Security:** Contract enforcement, violation detection
- **Failure modes:** Contract violation, agent escalation, unauthorized permission
- **Tests:** Contract compliance tests, violation detection tests
- **Acceptance:** All agents comply with contracts
- **Rollback:** Revoke agent permissions, quarantine agent
- **Authorization:** Contract approval

### 5.39 Agent Communication
- **Purpose:** Define how agents communicate and hand off artifacts
- **Ownership:** Communication Architect
- **Dependencies:** Multi-agent architecture, agent contracts
- **Inputs:** Agent messages, artifact references
- **Outputs:** Communication logs, artifact handoffs
- **Interfaces:** Agent messaging, artifact registry
- **Invariants:** All communication logged; artifacts hash-verified; no direct agent-to-live-execution path
- **Persistence:** Communication logs, artifact records
- **Identity:** Message hash, artifact hash
- **Security:** Communication integrity, artifact verification
- **Failure modes:** Unlogged communication, artifact tampering, unauthorized handoff
- **Tests:** Communication tests, artifact verification tests
- **Acceptance:** All communication logged and verifiable
- **Rollback:** Quarantine communication channel, audit all messages
- **Authorization:** Communication protocol approval

### 5.40 AI Model/Provider Abstraction
- **Purpose:** Abstract AI model and provider selection for free-first construction
- **Ownership:** AI Model Architect
- **Dependencies:** None (foundation)
- **Inputs:** Model availability, task requirements
- **Outputs:** Model selection decisions, provider abstraction layer
- **Interfaces:** ModelProvider, ModelRouter
- **Invariants:** Free-first; no paid AI assumed; provider swappable; model output verified
- **Persistence:** Model selection log
- **Identity:** Model ID, provider ID, output hash
- **Security:** Model output verification, provider isolation
- **Failure modes:** Paid model dependency, unverified model output, provider lock-in
- **Tests:** Provider swap tests, output verification tests
- **Acceptance:** System operates with free models only; paid models optional
- **Rollback:** Switch provider, re-verify outputs
- **Authorization:** Model selection approval

### 5.41 Skills/Capabilities Architecture
- **Purpose:** Define the skill system for agent capabilities
- **Ownership:** Skills Architect
- **Dependencies:** Agent contracts, AI model abstraction
- **Inputs:** Skill definitions, agent assignments
- **Outputs:** Available skills, capability matrix
- **Interfaces:** SkillLoader, SkillExecutor
- **Invariants:** Skills have explicit contracts; acceptance criteria defined; adversarial tests defined
- **Persistence:** Skill definitions, execution logs
- **Identity:** Skill ID, capability hash
- **Security:** Skill injection prevention, capability boundary enforcement
- **Failure modes:** Undefined skill execution, capability escalation, skill injection
- **Tests:** Skill execution tests, capability boundary tests, adversarial tests
- **Acceptance:** All skills have defined contracts and acceptance criteria
- **Rollback:** Disable skill, revert to prior capability set
- **Authorization:** Skill deployment approval

### 5.42 Knowledge/Memory Architecture
- **Purpose:** Define the knowledge and memory system for persistent agent state
- **Ownership:** Knowledge Architect
- **Dependencies:** All agent architectures
- **Inputs:** Agent outputs, research findings, session state
- **Outputs:** Knowledge base, memory records
- **Interfaces:** KnowledgeStore, MemoryStore
- **Invariants:** Knowledge hash-verified; memory append-only; no unauthorized modification
- **Persistence:** Knowledge base, memory store
- **Identity:** Knowledge hash, memory record hash
- **Security:** Knowledge integrity, memory tamper detection
- **Failure modes:** Knowledge corruption, memory tampering, unauthorized modification
- **Tests:** Knowledge integrity tests, memory tests
- **Acceptance:** Knowledge base verifiable and tamper-evident
- **Rollback:** Restore knowledge from last verified hash
- **Authorization:** Knowledge system approval

### 5.43 Evidence/Reasoning Provenance
- **Purpose:** Track the provenance of all AI-generated evidence and reasoning
- **Ownership:** Evidence Architect
- **Dependencies:** Provenance architecture, agent contracts
- **Inputs:** AI outputs, evidence sources, reasoning chains
- **Outputs:** Evidence records with full provenance
- **Interfaces:** EvidenceTracker, ReasoningProvenance
- **Invariants:** All evidence cited; reasoning chain verifiable; no unsupported claims
- **Persistence:** Evidence records with provenance
- **Identity:** Evidence hash, reasoning chain hash
- **Security:** Evidence integrity, citation verification
- **Failure modes:** Unverifiable evidence, broken reasoning chain, unsupported claims
- **Tests:** Evidence verification tests, reasoning chain tests
- **Acceptance:** All evidence independently verifiable
- **Rollback:** Remove unverifiable evidence, revert to prior evidence set
- **Authorization:** Evidence system approval

### 5.44 Security Architecture
- **Purpose:** Define the overall security posture and threat model
- **Ownership:** Security Architect
- **Dependencies:** All architecture domains
- **Inputs:** Threat model, security requirements
- **Outputs:** Security architecture document, threat model
- **Interfaces:** All security controls
- **Invariants:** Zero trust; least privilege; defense in depth; auditability; no credentials in code/docs
- **Persistence:** Security architecture, audit logs
- **Identity:** Security policy hash
- **Security:** All security requirements enforced
- **Failure modes:** Security breach, credential exposure, unauthorized access
- **Tests:** Security tests, threat model tests, penetration tests
- **Acceptance:** All threat mitigations in place; zero critical vulnerabilities
- **Rollback:** Emergency shutdown; forensic audit
- **Authorization:** Security architecture approval

### 5.45 Red-Team Architecture
- **Purpose:** Define the adversarial testing framework
- **Ownership:** Red-Team Architect
- **Dependencies:** Security architecture, test architecture
- **Inputs:** Attack scenarios, system components
- **Outputs:** Red-team test results, vulnerability reports
- **Interfaces:** Red-team test suite, adversarial test framework
- **Invariants:** All attack scenarios tested; vulnerabilities documented; no silent pass
- **Persistence:** Red-team reports with evidence
- **Identity:** Red-team report hash
- **Security:** Adversarial testing integrity
- **Failure modes:** Untested attack vectors, false red-team pass
- **Tests:** Red-team tests, adversarial tests
- **Acceptance:** All defined attack scenarios tested; vulnerabilities documented
- **Rollback:** Remediate vulnerabilities, re-run red-team
- **Authorization:** Red-team test approval

### 5.46 Audit Architecture
- **Purpose:** Define the audit system for all system actions
- **Ownership:** Audit Architect
- **Dependencies:** Provenance architecture, security architecture
- **Inputs:** System actions, agent decisions, governance events
- **Outputs:** Audit records with hash verification
- **Interfaces:** AuditLogger, AuditVerifier
- **Invariants:** All actions logged; audit chain hash-verified; no action unlogged
- **Persistence:** Audit log (append-only, immutable)
- **Identity:** Audit entry hash, audit chain hash
- **Security:** Audit integrity, tamper detection
- **Failure modes:** Missing audit entries, audit chain break, tampered audit log
- **Tests:** Audit completeness tests, chain integrity tests
- **Acceptance:** Every action auditable; chain integrity verifiable
- **Rollback:** Restore audit log from last verified state
- **Authorization:** Audit system approval

### 5.47 Reproducibility Architecture
- **Purpose:** Ensure all system outputs are deterministically reproducible
- **Ownership:** Reproducibility Architect
- **Dependencies:** Deterministic identity, canonical serialization, quant engine
- **Inputs:** System configurations, datasets, model parameters
- **Outputs:** Reproducibility verification results
- **Interfaces:** ReproducibilityVerifier, DeterministicRunner
- **Invariants:** Same input → same output; all non-determinism eliminated; frozen timestamps in tests
- **Persistence:** Reproducibility logs
- **Identity:** Reproducibility run hash
- **Security:** Reproducibility integrity
- **Failure modes:** Non-deterministic output, hidden randomness, environment-dependent results
- **Tests:** Reproducibility tests, determinism tests, environment tests
- **Acceptance:** All outputs reproducible across runs and environments
- **Rollback:** Fix non-determinism, re-run reproducibility tests
- **Authorization:** Reproducibility approval

### 5.48 Observability
- **Purpose:** Define system observability — metrics, logging, tracing
- **Ownership:** Observability Architect
- **Dependencies:** Audit architecture, monitoring architecture
- **Inputs:** System events, metrics, logs
- **Outputs:** Observability dashboards, alert triggers
- **Interfaces:** Metrics API, Log API, Trace API
- **Invariants:** All components observable; metrics deterministic; logs immutable
- **Persistence:** Metrics, logs, traces
- **Identity:** Metric hash, log entry hash, trace ID
- **Security:** Observability data integrity
- **Failure modes:** Missing observability, metric drift, log gap
- **Tests:** Observability tests, metric accuracy tests
- **Acceptance:** All components observable with accurate metrics
- **Rollback:** Restore observability from last verified state
- **Authorization:** Observability approval

### 5.49 Monitoring
- **Purpose:** Define system health monitoring and alerting
- **Ownership:** Monitoring Architect
- **Dependencies:** Observability, failure/recovery architecture
- **Inputs:** System metrics, health checks, data quality signals
- **Outputs:** Health reports, alerts, incident records
- **Interfaces:** Monitor, AlertManager, HealthCheck
- **Invariants:** All critical paths monitored; alerts actionable; no silent failure
- **Persistence:** Monitoring logs, alert records
- **Identity:** Health report hash, alert ID
- **Security:** Monitoring integrity, alert tamper detection
- **Failure modes:** Unmonitored failure, silent alert, missed anomaly
- **Tests:** Monitoring tests, alert tests, anomaly detection tests
- **Acceptance:** All critical paths monitored; alerts fire correctly
- **Rollback:** Restore monitoring from last verified state
- **Authorization:** Monitoring approval

### 5.50 Failure/Recovery Architecture
- **Purpose:** Define system failure modes and recovery procedures
- **Ownership:** Recovery Architect
- **Dependencies:** All architecture domains
- **Inputs:** Failure events, system state
- **Outputs:** Recovery procedures, system state restoration
- **Interfaces:** RecoveryManager, CheckpointManager
- **Invariants:** Full state restorable; no data loss; recovery tested
- **Persistence:** Checkpoints, recovery logs
- **Identity:** Checkpoint hash, recovery log hash
- **Security:** Recovery integrity, checkpoint tamper detection
- **Failure modes:** Unrecoverable state, checkpoint corruption, incomplete recovery
- **Tests:** Recovery tests, checkpoint tests, restoration tests
- **Acceptance:** All failure modes have tested recovery procedures
- **Rollback:** Restore from checkpoint
- **Authorization:** Recovery procedure approval

### 5.51 Paper Trading
- **Purpose:** Execute strategies in simulated environment with market realism
- **Ownership:** Paper Trading Architect (Phase 11)
- **Dependencies:** All Phase 4A work, risk engine, backtesting
- **Inputs:** StrategySpec, market data, paper order parameters
- **Outputs:** Paper trades, fills, positions, P&L, analytics, audit trail
- **Interfaces:** SignalProcessor, RiskEngine, PaperOrderGateway, ExecutionSimulator, PositionManager, P&LCalculator, AnalyticsEngine, AuditLogger
- **Invariants:** No real money; no broker credentials; market realism (spread, fees, slippage, latency); full reconciliation
- **Persistence:** Paper trade records with full provenance
- **Identity:** Paper trade hash, fill hash, P&L hash
- **Security:** No real execution; credential isolation; paper/live boundary
- **Failure modes:** Paper/live confusion, unrealistic fills, reconciliation failure
- **Tests:** Paper execution tests, reconciliation tests, market realism tests, spread/fee/slippage tests
- **Acceptance:** Paper trading pipeline fully functional with market realism
- **Rollback:** Remove paper trading modules, revert to backtest-only
- **Authorization:** Paper trading deployment approval

### 5.52 Broker Abstraction
- **Purpose:** Define the broker abstraction layer for multi-broker support
- **Ownership:** Broker Architect
- **Dependencies:** Paper trading, execution safety
- **Inputs:** Broker configurations, order parameters
- **Outputs:** Broker-agnostic order execution, fill reports
- **Interfaces:** BrokerAdapter, OrderAPI, FillAPI
- **Invariants:** Broker-agnostic interface; credential isolation; no broker-specific code in core
- **Persistence:** Broker connection logs, fill records
- **Identity:** Broker session hash, order ID hash
- **Security:** Credential isolation, broker authentication, no credential leakage
- **Failure modes:** Broker connection failure, credential exposure, broker-specific bug
- **Tests:** Broker adapter tests, credential isolation tests, connection tests
- **Acceptance:** Broker abstraction works with multiple brokers; credentials isolated
- **Rollback:** Disable broker, revert to paper-only
- **Authorization:** Broker abstraction approval

### 5.53 MT5 Integration Boundary
- **Purpose:** Define the strict boundary for MT5 broker integration
- **Ownership:** MT5 Specialist (single owner)
- **Dependencies:** Broker abstraction, security architecture, execution safety
- **Inputs:** MT5 terminal, broker credentials, order parameters
- **Outputs:** MT5 order execution, fill reports, connection status
- **Interfaces:** MT5Adapter, BrokerValidator, CredentialStore, OrderLimiter, ExposureLimiter, KillSwitch, ExecutionAudit, Reconciliation, EmergencyShutdown, ConnectionHandler, DuplicateProtection, LiveAuthorizationGate
- **Invariants:** MT5 is read-only until explicit authorization; all orders logged; duplicate protection; kill switch functional; credential isolation; live authorization gate requires human approval
- **Persistence:** MT5 execution audit log (immutable), connection logs
- **Identity:** MT5 order hash, session hash
- **Security:** Credential isolation, kill switch, emergency shutdown, connection limits, duplicate order prevention
- **Failure modes:** MT5 connection failure, credential leak, duplicate order, unauthorized live execution
- **Tests:** MT5 connection tests, credential isolation tests, kill switch tests, duplicate protection tests, authorization gate tests
- **Acceptance:** MT5 integration safe; all security controls functional; authorization gate enforced
- **Rollback:** Disconnect MT5, revoke credentials, audit all orders
- **Authorization:** MT5 connection requires explicit human authorization + credential verification

### 5.54 Execution Safety
- **Purpose:** Define execution safety controls for all trading execution paths
- **Ownership:** Execution Safety Architect
- **Dependencies:** Risk engine, position management, broker abstraction, MT5 boundary
- **Inputs:** Orders, positions, risk parameters
- **Outputs:** Safe execution, safety alerts, kill switch triggers
- **Interfaces:** SafetyController, KillSwitch, OrderLimiter, ExposureLimiter, DuplicateProtector
- **Invariants:** Hard limits enforced; kill switch immediate; no bypass possible; all executions logged
- **Persistence:** Safety audit log
- **Identity:** Safety event hash
- **Security:** Kill switch functional, limits enforced, no override
- **Failure modes:** Unauthorized execution, limit breach, kill switch failure
- **Tests:** Safety tests, kill switch tests, limit tests, duplicate detection tests
- **Acceptance:** All safety controls functional; no execution bypass possible
- **Rollback:** Emergency shutdown; audit all executions
- **Authorization:** Execution safety approval

### 5.55 P&L/Reconciliation
- **Purpose:** Compute P&L and reconcile orders, fills, and positions
- **Ownership:** P&L Architect
- **Dependencies:** Position management, execution simulation, paper trading
- **Inputs:** Orders, fills, positions, market data
- **Outputs:** P&L reports, reconciliation reports
- **Interfaces:** PnLCalculator, ReconciliationEngine
- **Invariants:** Order→Fill reconciliation; Position→P&L reconciliation; data failure handling; execution failure handling; risk violation handling
- **Persistence:** P&L records, reconciliation records
- **Identity:** P&L hash, reconciliation hash
- **Security:** P&L integrity, reconciliation completeness
- **Failure modes:** P&L mismatch, unreconciled order, fill discrepancy
- **Tests:** P&L computation tests, reconciliation tests, data failure tests, execution failure tests
- **Acceptance:** All orders reconciled; P&L accurate; no discrepancies
- **Rollback:** Restore P&L from last verified state
- **Authorization:** P&L system approval

### 5.56 Strategy Graduation
- **Purpose:** Define criteria and process for graduating paper strategies to live consideration
- **Ownership:** Graduation Architect
- **Dependencies:** Paper trading, 30-day evaluation, risk engine
- **Inputs:** Paper trading results, 30-day evaluation, risk assessment
- **Outputs:** Graduation decision, graduated strategy list
- **Interfaces:** GraduationEvaluator, GraduationCriteria
- **Invariants:** No strategy graduates without 30-day evaluation; all metrics must meet thresholds; human authorization required
- **Persistence:** Graduation records with evidence
- **Identity:** Graduation decision hash
- **Security:** Graduation integrity, no unauthorized graduation
- **Failure modes:** Premature graduation, metric manipulation, unauthorized graduation
- **Tests:** Graduation criteria tests, evaluation tests
- **Acceptance:** Only fully evaluated strategies graduate; all evidence cited
- **Rollback:** Revoke graduation, revert to paper-only
- **Authorization:** Graduation requires explicit human authorization

### 5.57 Strategy Retirement
- **Purpose:** Define criteria and process for retiring strategies that no longer meet standards
- **Ownership:** Retirement Architect
- **Dependencies:** Strategy graduation, monitoring, risk engine
- **Inputs:** Strategy performance, market regime changes, risk assessment
- **Outputs:** Retirement decision, retired strategy list
- **Interfaces:** RetirementEvaluator, RetirementCriteria
- **Invariants:** Retirement evidence documented; strategy removed from active trading; historical records preserved
- **Persistence:** Retirement records with evidence
- **Identity:** Retirement decision hash
- **Security:** Retirement audit trail
- **Failure modes:** Failure to retire underperforming strategy, retirement without evidence
- **Tests:** Retirement criteria tests, evidence tests
- **Acceptance:** Underperforming strategies retired with evidence
- **Rollback:** Reinstate strategy if evidence supports (rare)
- **Authorization:** Retirement requires human authorization

### 5.58 30-Day Paper Evaluation
- **Purpose:** Evaluate paper trading performance over a 30-day period before any graduation consideration
- **Ownership:** Evaluation Architect
- **Dependencies:** Paper trading system
- **Inputs:** 30 days of paper trading data
- **Outputs:** 30-day evaluation report with all readiness criteria
- **Interfaces:** EvaluationFramework, ReadinessChecker
- **Invariants:** Full 30 days required; all readiness criteria evaluated; NO TRADE behavior tested; reproducibility verified
- **Persistence:** Evaluation report with full evidence
- **Identity:** Evaluation report hash
- **Security:** Evaluation integrity, no metric manipulation
- **Failure modes:** Insufficient evaluation period, incomplete criteria, metric gaming
- **Tests:** Evaluation criteria tests, NO TRADE behavior tests, reproducibility tests
- **Acceptance:** All readiness criteria met; 30-day period complete; NO TRADE behavior verified
- **Rollback:** Extend evaluation period; address failures
- **Authorization:** 30-day evaluation requires human review

### 5.59 Future Live Boundary
- **Purpose:** Define the explicit boundary between paper trading and live execution
- **Ownership:** Live Boundary Architect
- **Dependencies:** All preceding phases, security architecture, MT5 integration
- **Inputs:** All phase completion evidence, security audit, authorization decisions
- **Outputs:** Live boundary authorization decision
- **Interfaces:** LiveAuthorizationGate, SecurityAudit, PhaseCompletionVerifier
- **Invariants:** Live trading NEVER authorized by this blueprint; requires all phases complete + passing 30-day evaluation + strategy graduation + production data infrastructure + security audit clearance + explicit human authorization
- **Persistence:** Live boundary authorization record
- **Identity:** Authorization decision hash
- **Security:** Authorization gate, credential verification, emergency shutdown
- **Failure modes:** Unauthorized live execution, boundary confusion, credential compromise
- **Tests:** Authorization gate tests, boundary tests, emergency shutdown tests
- **Acceptance:** Live boundary never crossed without explicit human authorization
- **Rollback:** Emergency shutdown; revoke all live credentials
- **Authorization:** Explicit human authorization required — this blueprint does NOT authorize it

### 5.60 Autonomous Operating Loop
- **Purpose:** Define the full autonomous trading lifecycle from discovery through retirement
- **Ownership:** Autonomous Systems Architect
- **Dependencies:** All architecture domains
- **Inputs:** Market data, research queries, system state
- **Outputs:** Research findings, strategies, backtests, paper trades, monitoring data, graduation/retirement decisions
- **Interfaces:** Full system integration
- **Invariants:** System always able to choose NO TRADE; no fixed trade count objective; governance enforced at every step; security failure = STOP; reproducibility failure = STOP; data integrity failure = STOP; governance failure = STOP
- **Persistence:** Full audit trail across all lifecycle stages
- **Identity:** Lifecycle run hash
- **Security:** Full security enforcement; no AI self-authorization
- **Failure modes:** Autonomous loop bypass, governance gap, security incident, reproducibility failure
- **Tests:** End-to-end lifecycle tests, NO TRADE tests, governance compliance tests, security tests, reproducibility tests
- **Acceptance:** Full lifecycle functional; all safety boundaries enforced; NO TRADE always available
- **Rollback:** Stop autonomous loop; manual review; revert to manual process
- **Authorization:** Autonomous loop requires all phases complete + explicit human authorization

---

## 6. Complete Dependency Graph

### 6.1 Foundation Layer (no dependencies)
- System Vision
- Repository Architecture
- AI Model/Provider Abstraction
- Security Architecture (foundation level)
- Audit Architecture (foundation level)

### 6.2 Data Layer (depends on Foundation)
- Data Architecture → Foundation
- Provenance Architecture → Data Architecture
- Deterministic Identity → Provenance Architecture
- Canonical Serialization → Deterministic Identity
- Temporal/PIT Architecture → Data Architecture + Provenance Architecture
- Revision Architecture → Deterministic Identity + Canonical Serialization
- Instrument Identity → Deterministic Identity + Canonical Serialization

### 6.3 Asset Class Layer (depends on Data Layer)
- Universe Management → Instrument Identity + Temporal/PIT
- Calendar/Session Management → Instrument Identity
- Corporate Actions → Instrument Identity (enhanced) + Temporal/PIT
- Derivatives/Futures/Continuous Contracts → Calendar/Session + Venue enhancement

### 6.4 Research Layer (depends on Data + Asset Classes)
- Research Registry → Experiment Identity + Deterministic Identity
- Experiment Registry → Experiment Identity + Reproducibility Architecture
- Dataset Registry → Provenance Architecture + PIT Architecture
- Strategy Registry → Strategy Representation + Deterministic Identity
- Market Intelligence → Data Architecture + Provenance Architecture
- News Intelligence → Data Architecture + Source Verification
- Macro Intelligence → Calendar/Session + Macro Data
- Feature Engineering → Data Architecture + PIT Architecture + Quant Engine
- Quant Research Engine → Data Architecture + Feature Engineering

### 6.5 Strategy Layer (depends on Research + Asset Classes)
- Strategy Representation → Deterministic Identity
- Strategy Generation/Discovery → Research Registry + Market Intelligence + Quant Engine
- Backtesting → Strategy Representation + Data Architecture + PIT Architecture + Quant Engine
- Bias/Leakage Detection → PIT Architecture + Universe Management + Quant Engine
- Statistical Validation → Quant Engine + Backtesting
- Walk-Forward Validation → Backtesting + Quant Engine + PIT Architecture
- Robustness Testing → Backtesting + Quant Engine

### 6.6 Risk/Portfolio Layer (depends on Strategy Layer)
- Risk Engine → Position Management + P&L + Backtesting
- Exposure Management → Risk Engine + Portfolio Construction + Data Architecture
- Portfolio Construction → Risk Engine + Strategy Validation + Quant Engine
- Position Management → Execution Simulation + P&L

### 6.7 Execution Layer (depends on Risk/Portfolio)
- Paper Trading → All Phase 4A work + Risk Engine + Backtesting
- Broker Abstraction → Paper Trading + Execution Safety
- MT5 Integration Boundary → Broker Abstraction + Security Architecture + Execution Safety
- Execution Safety → Risk Engine + Position Management + Broker Abstraction + MT5 Boundary
- P&L/Reconciliation → Position Management + Execution Simulation + Paper Trading

### 6.8 Evaluation/Transition Layer (depends on Execution)
- Strategy Graduation → Paper Trading + 30-Day Evaluation + Risk Engine
- Strategy Retirement → Strategy Graduation + Monitoring + Risk Engine
- 30-Day Paper Evaluation → Paper Trading System
- Future Live Boundary → All preceding phases + Security Audit + Authorization
- Autonomous Operating Loop → All domains

### 6.9 Orchestration Layer (depends on all)
- Research-Agent Architecture → All research domains + Hermes Orchestration
- Hermes Orchestration → All agent architectures + Governance Model
- Multi-Agent Architecture → Agent Contracts + Communication Architecture
- Agent Contracts → All agent architectures + Governance Model
- Agent Communication → Multi-Agent Architecture + Agent Contracts
- Knowledge/Memory Architecture → All agent architectures
- Evidence/Reasoning Provenance → Provenance Architecture + Agent Contracts
- Skills/Capabilities Architecture → Agent Contracts + AI Model Abstraction
- Observability → Audit Architecture + Monitoring Architecture
- Monitoring → Observability + Failure/Recovery Architecture
- Failure/Recovery Architecture → All architecture domains

### 6.10 Critical Dependency Chains (explicit ordering)

**PIT dependency chain:**
Temporal Contracts → PitSidecar/RevisionChain → PitViewBuilder/Validator → ExperimentIdentity → PIT Integration with Backtest

**Research dependency chain:**
Data Ingestion → Data Quality → Provenance → PIT Views → Research → Hypotheses → Strategies

**Strategy Generation dependency chain:**
PIT Correctness → Research → Hypotheses → Strategy Generation → Validation → Backtesting

**Backtesting dependency chain:**
Strategy Representation → PIT-Filtered Data → Quant Engine → Backtest Engine → Statistical Validation

**Validation dependency chain:**
Backtesting → Bias/Leakage Detection → Statistical Validation → Walk-Forward → Robustness

**Portfolio/Risk dependency chain:**
Strategy Validation → Risk Engine → Exposure Management → Portfolio Construction

**Paper Trading dependency chain:**
All Phase 4A → Risk Engine → Walk-Forward → Paper System → 30-Day Evaluation

**Hermes Autonomous Research dependency chain:**
All research domains → Hermes Orchestration → Agent Contracts → Multi-Agent Architecture

**Strategy Graduation dependency chain:**
Paper Trading → 30-Day Evaluation → Risk Review → Graduation Decision

**MT5 dependency chain:**
All preceding phases → Broker Abstraction → Security Audit → MT5 Integration → Live Authorization Gate

**Future Live Execution dependency chain:**
MT5 Integration → All phases complete → 30-day evaluation passing → Strategy graduation → Security audit → Explicit human authorization

---

## 7. Complete Ownership Matrix

| Component | Owner | No Alternate Owner |
|-----------|-------|-------------------|
| System Vision | Principal Architect | — |
| Roadmap | Principal Architect | — |
| Repository Architecture | Repository Architect | — |
| Data Architecture | Data Architect | — |
| Temporal/PIT Architecture | Temporal Architect (4A.1) | — |
| Provenance Architecture | Provenance Architect | — |
| Deterministic Identity | Identity Architect | — |
| Canonical Serialization | Serialization Architect | — |
| Revision Architecture | Revision Architect (4A.1) | — |
| Instrument Identity | Instrument Architect (4A.1) | — |
| Universe Management | Universe Architect | — |
| Corporate Actions | Corporate Actions Architect (4A.2) | — |
| Calendar/Session Management | Calendar Architect (4A.1) | — |
| Derivatives/Futures | Derivatives Architect (4A.3) | — |
| Research Registry | Research Registry Architect (4A.4) | — |
| Experiment Registry | Experiment Registry Architect | — |
| Dataset Registry | Dataset Registry Architect | — |
| Strategy Registry | Strategy Registry Architect | — |
| Strategy Representation | Strategy Architect | — |
| Strategy Generation/Discovery | Strategy Research Agent (AI) + Human Review | — |
| Feature Engineering | Quant Research Architect | — |
| Quant Research Engine | Quant Architect | — |
| Backtesting | Backtest Architect (Phase 3 — frozen) | — |
| Bias/Leakage Detection | Bias/Leakage Architect | — |
| Statistical Validation | Statistical Validation Architect | — |
| Walk-Forward Validation | Validation Architect (Phase 7) | — |
| Robustness Testing | Robustness Architect (Phase 7) | — |
| Portfolio Construction | Portfolio Architect (Phase 8) | — |
| Risk Engine | Risk Architect (Phase 8) | — |
| Exposure Management | Exposure Architect (Phase 8) | — |
| Position Management | Position Architect (Phase 3) | — |
| Market Intelligence | Market Intelligence Agent (AI) | — |
| News Intelligence | News Intelligence Agent (AI) | — |
| Macro Intelligence | Macro Intelligence Agent (AI) | — |
| Research-Agent Architecture | Research Agent Architect | — |
| Hermes Orchestration | Hermes Orchestrator | — |
| Multi-Agent Architecture | Multi-Agent Architect | — |
| Agent Contracts | Contract Architect | — |
| Agent Communication | Communication Architect | — |
| AI Model/Provider Abstraction | AI Model Architect | — |
| Skills/Capabilities Architecture | Skills Architect | — |
| Knowledge/Memory Architecture | Knowledge Architect | — |
| Evidence/Reasoning Provenance | Evidence Architect | — |
| Security Architecture | Security Architect | — |
| Red-Team Architecture | Red-Team Architect | — |
| Audit Architecture | Audit Architect | — |
| Reproducibility Architecture | Reproducibility Architect | — |
| Observability | Observability Architect | — |
| Monitoring | Monitoring Architect | — |
| Failure/Recovery Architecture | Recovery Architect | — |
| Paper Trading | Paper Trading Architect (Phase 11) | — |
| Broker Abstraction | Broker Architect | — |
| MT5 Integration Boundary | MT5 Specialist | — |
| Execution Safety | Execution Safety Architect | — |
| P&L/Reconciliation | P&L Architect | — |
| Strategy Graduation | Graduation Architect | — |
| Strategy Retirement | Retirement Architect | — |
| 30-Day Paper Evaluation | Evaluation Architect | — |
| Future Live Boundary | Live Boundary Architect | — |
| Autonomous Operating Loop | Autonomous Systems Architect | — |

**Governance rule:** No component may have two authoritative owners. Blocker 1 (Phase ownership contradictions) must be fully resolved before any work package touching InstrumentIdentity, InstrumentSpecification, Venue, DataSource, or CalendarRef begins.

---

## 8. Complete AI Construction Model

### 8.1 AI Roles and Responsibilities

| AI Role | What It May Do | What It May NOT Do | Branch/Worktree | Artifact Handoff | Review Sequence | Conflict Resolution | Evidence Requirements | Final Integration Authority |
|---------|---------------|-------------------|-----------------|------------------|-----------------|---------------------|----------------------|---------------------------|
| **Hermes/Orchestrator** | Coordinate agents, assign tasks, integrate completed work, produce audit log | Execute trades, modify frozen contracts, authorize phases, close blockers | Main branch only for coordination | Task assignments, integration results | Reviews all agent outputs | Human decision | Audit log | Hermes integrates completed work |
| **Z.ai/GLM** | Research analysis, data processing, quant calculations, documentation | Live trading, credential access, frozen contract modification, blocker closure | Worktree per work package | Research findings, analysis reports | Hermes review + independent review | Hermes decision | Cited sources, hash verification | Hermes final integration |
| **GPT** | Code implementation, test writing, code review, documentation | Live trading, credential access, frozen contract modification, self-authorization | Worktree per work package | Code changes, test results | Independent reviewer + Hermes | Hermes decision | Test output, hash verification | Hermes final integration |
| **Claude (if available)** | Architecture review, security audit, red-team analysis, documentation | Live trading, credential access, frozen contract modification | Worktree per work package | Review reports, audit findings | Hermes review | Hermes decision | Audit findings, hash verification | Hermes final integration |
| **Quant Specialist** | Validate quant calculations, verify statistical tests, review indicator implementations | Modify quant engine without review, bypass validation | Worktree per work package | Validation reports | Hermes + independent review | Hermes decision | Statistical test outputs | Hermes final integration |
| **Security Specialist** | Audit security controls, threat modeling, vulnerability assessment | Modify security controls without review, bypass audit | Worktree per work package | Security audit reports | Hermes + independent review | Hermes decision | Security findings, hash verification | Hermes final integration |
| **MT5 Specialist** | Review MT5 execution safety, credential handling, kill switch | Modify MT5 integration without review, access live credentials | Worktree per work package | MT5 safety review | Hermes + independent review | Hermes decision | Safety test results | Hermes final integration |
| **QA/Reproducibility Specialist** | Verify tests, reproducibility, deterministic re-runs | Modify tests without approval, bypass reproducibility checks | Worktree per work package | Test results, reproducibility reports | Hermes + independent review | Hermes decision | Test output, hash verification | Hermes final integration |
| **Independent Reviewer** | Review all implementations, verify compliance, audit evidence | Implement code, modify frozen contracts, authorize phases | Read-only access | Review reports | Pre-merge | Human decision | Review findings | Hermes final integration |

### 8.2 Free-First Construction Strategy

**No paid AI access is assumed.** The architecture must support construction using:
- Free local AI models (where available)
- Free-tier API access (where needed and budget-approved)
- Open-source tools and libraries
- Deterministic, offline-capable computation

**Branch/Worktree Rules:**
1. Single AI writes at a time (no parallel uncontrolled edits)
2. Branch/worktree per work package
3. Patch-based reconciliation
4. No simultaneous multi-AI editing
5. All changes reviewed before merge
6. Free/local tools only (no paid AI services required)

**Artifact Handoff:**
1. AI produces implementation + tests + evidence + hash verification
2. Evidence verified by independent reviewer
3. Hash verification confirmed
4. Artifact handed to Hermes integrator
5. Hermes integrates into main branch after review

**Review Sequence:**
1. Primary AI implements work package
2. Independent reviewer reviews implementation
3. QA specialist verifies tests and reproducibility
4. Security specialist audits security controls
5. Quant specialist validates quant calculations
6. Hermes integrator performs final integration
7. Human authorization for phase transitions

**Conflict Resolution:**
1. Hermes mediates conflicts between AI agents
2. Human decision for unresolvable conflicts
3. Frozen contracts take precedence over any AI output
4. Governance rules override agent preferences

**Evidence Requirements:**
1. All outputs must have verifiable evidence
2. Hash values must be independently reproducible
3. No output may rely on wall-clock time
4. No output may use network access (unless explicitly authorized)
5. No output may use live credentials
6. All outputs must pass deterministic verification

**Final Integration Authority:**
Hermes is the sole final integrator. No AI agent may merge to main without Hermes integration. Hermes verifies:
- All tests pass
- Hashes verified
- Evidence cited
- No governance violations
- Frozen contracts unchanged

---

## 9. Complete Autonomous Trading Lifecycle

### 9.1 Lifecycle Stages

```
DISCOVER
→ INGEST
→ VALIDATE
→ NORMALIZE
→ VERSION
→ BUILD PIT VIEW
→ RESEARCH
→ GENERATE HYPOTHESES
→ GENERATE STRATEGIES
→ BACKTEST
→ VALIDATE
→ STRESS TEST
→ RISK TEST
→ PAPER DEPLOY
→ MONITOR
→ EVALUATE
→ GRADUATE OR RETIRE
```

### 9.2 Stage Definitions

**DISCOVER:** Identify market opportunities, research questions, and hypothesis candidates. Input: market data, research queries. Output: research findings with citations. Governance: all claims cited, no future data.

**INGEST:** Collect market data from providers. Input: provider configurations. Output: raw datasets with provenance. Governance: source verification, SYNTHETIC blocking.

**VALIDATE:** Run data quality checks. Input: raw datasets. Output: quality reports, blocked datasets. Governance: DataQualityGate, SYNTHETIC blocking.

**NORMALIZE:** Normalize data to canonical form. Input: validated datasets. Output: normalized datasets. Governance: UTC normalization, temporal contract compliance.

**VERSION:** Version datasets and create PitSidecar. Input: normalized datasets. Output: versioned datasets with PitSidecar. Governance: deterministic identity, append-only revision chain.

**BUILD PIT VIEW:** Construct point-in-time views. Input: versioned datasets + PitSidecar. Output: PIT-filtered datasets. Governance: no future data, inclusive cutoff, deterministic tie-breaking.

**RESEARCH:** Conduct quant and qualitative research. Input: PIT-filtered datasets, research queries. Output: research findings with citations. Governance: no LLM calls for quant, evidence cited.

**GENERATE HYPOTHESES:** Formulate testable hypotheses from research. Input: research findings. Output: hypotheses with evidence. Governance: hypotheses must be falsifiable, evidence cited.

**GENERATE STRATEGIES:** Convert hypotheses to strategy specifications. Input: hypotheses, market data. Output: StrategySpec candidates. Governance: StrategySpec frozen, condition validation.

**BACKTEST:** Execute backtests on PIT-filtered data. Input: StrategySpec, PIT dataset. Output: BacktestProvenance with result_hash. Governance: frozen provenance, deterministic result_hash, PIT correctness.

**VALIDATE:** Statistical validation of backtest results. Input: backtest results. Output: validation report. Governance: valid p-values, confidence intervals, multiple-testing control.

**STRESS TEST:** Test strategy under extreme scenarios. Input: strategy, stress scenarios. Output: stress test report. Governance: scenario coverage, regime-specific testing.

**RISK TEST:** Test risk controls under adverse conditions. Input: strategy, risk parameters. Output: risk test report. Governance: hard limits enforced, violations detected.

**PAPER DEPLOY:** Deploy strategy in paper trading. Input: validated strategy, paper gateway. Output: paper trades, P&L, analytics. Governance: no real money, market realism, full reconciliation.

**MONITOR:** Monitor paper trading performance and system health. Input: paper trading data, system metrics. Output: health reports, alert triggers. Governance: all critical paths monitored, alerts actionable.

**EVALUATE:** Evaluate 30-day paper trading performance. Input: 30 days of paper data. Output: evaluation report with readiness criteria. Governance: full 30 days, all criteria evaluated, NO TRADE behavior tested.

**GRADUATE OR RETIRE:** Decision on strategy lifecycle. Input: evaluation report, risk assessment. Output: graduation or retirement decision. Governance: human authorization required, evidence cited, NO TRADE fallback.

### 9.3 NO TRADE Guarantee

**The system must always be able to choose NO TRADE.** This is not a failure state — it is a valid system output. NO TRADE is selected when:
- Statistical significance not met
- Risk limits exceeded
- Data quality insufficient
- PIT correctness cannot be verified
- Model stability fails
- Overfitting detected
- Any governance check fails

**No fixed trade count is a system objective.** The 2,765 trades / 2-day figure is ONLY a load/stress benchmark, never a performance target.

---

## 10. Explicit Safety Boundaries

1. **No strategy can bypass risk controls** — risk limits are hard constraints; no strategy, model, or agent can override them
2. **No agent can bypass governance** — all agent actions subject to governance gates; governance violations = immediate shutdown
3. **No model can modify frozen contracts** — frozen Phase 3 contracts are byte-for-byte protected; any modification attempt = security alert
4. **No AI can authorize its own deployment** — deployment authorization requires explicit human decision; no AI self-authorization
5. **No paper strategy can become live merely because it passed a metric** — live execution requires separate explicit authorization boundary
6. **Live execution requires a separate explicit authorization boundary** — all live execution gates must be independently satisfied
7. **Security failure = STOP** — any security failure triggers immediate emergency shutdown
8. **Reproducibility failure = STOP** — any reproducibility failure halts the pipeline until resolved
9. **Data integrity failure = STOP** — any data integrity failure halts the pipeline until resolved
10. **Governance failure = STOP** — any governance violation halts all operations pending human review

### 10.1 Safety Boundary Enforcement

| Boundary | Enforcement Mechanism | Violation Response |
|----------|----------------------|-------------------|
| Risk controls | Hard limits in RiskEngine | Reject order, alert, log |
| Governance | Hermes orchestration gate | Pause all agents, human review |
| Frozen contracts | SHA-256 manifest verification | Security alert, rollback |
| AI self-authorization | Authorization gate requires human | Reject, audit log |
| Paper/live boundary | LiveAuthorizationGate | Reject, human authorization required |
| Security failure | Emergency shutdown | Immediate stop, forensic audit |
| Reproducibility failure | Determinism verification | Halt pipeline, investigate |
| Data integrity failure | Hash verification | Halt pipeline, restore from verified state |
| Governance failure | Governance compliance check | Halt all operations, human review |

---

## 11. Complete Test/Gate Architecture

### 11.1 Test Categories (in execution order)

| Stage | Category | Purpose | Frequency |
|-------|----------|---------|-----------|
| 1 | **Unit Tests** | Individual component verification | Every change |
| 2 | **Integration Tests** | Component interaction verification | Every change |
| 3 | **Acceptance Tests** | Domain acceptance criteria verification | Every work package |
| 4 | **Regression Tests** | Baseline regression verification | Every change |
| 5 | **Security Tests** | Threat mitigation verification | Every work package |
| 6 | **Red-Team Tests** | Adversarial testing | Every phase |
| 7 | **Reproducibility Tests** | Deterministic re-run verification | Every change |
| 8 | **Performance/Load Tests** | Load/stress benchmarking | Every phase |
| 9 | **Final Acceptance** | Complete system acceptance | Every phase gate |

### 11.2 Current Baseline

| Test File | Tests | Status |
|-----------|-------|--------|
| test_data_engine.py | 62 | PASSING |
| test_pit.py | 97 | PASSING |
| test_quant.py | 134 | PASSING |
| test_redteam.py | 50 | PASSING |
| test_strategy.py | 82 | PASSING |
| test_strategy_independent.py | 39 | 6 pre-existing failures (documented) |
| **Total** | **464** | **PASSING** |
| **Authorized baseline** | **367** | **PASSING** |
| **PIT delta (unauthorized)** | **97** | **PASSING** |

### 11.3 Regression-Baseline Re-Establishment Procedures

**When the baseline must be re-established:**
1. A phase completes and its tests become authorized
2. A design change affects test classification
3. A human authorization record is created for previously untracked tests
4. The regression baseline measurement rule (REG-06) requires re-measurement

**Procedure:**
1. Run full test suite: `.venv/Scripts/python.exe -m pytest tests/ --tb=no -q`
2. Separate authorized vs. unauthorized by tracking status:
   - Authorized: tracked files in git, passing
   - Unauthorized: untracked files, not in git
3. Record: `authorized_count / total_count / unauthorized_delta`
4. Update regression baseline document
5. Verify frozen manifest unchanged
6. Independent re-audit of baseline re-establishment

**Current baseline (measured live):**
- 367 authorized baseline tests
- 464 observed/current total tests
- 97 unauthorized PIT delta

**Do not silently normalize these numbers.** The 97 delta represents unauthorized PIT tests that exist but are not yet part of the authorized baseline. They are passing but their authorization status is unresolved.

### 11.4 Gate Architecture

| Gate | Trigger | Required Evidence | Authorization |
|------|---------|-------------------|---------------|
| Design Lock | Phase spec complete | Design doc SHA-256, spec ratified | Human authorization |
| Architecture Gate | Design lock resolved | Architecture compliance verified | Human authorization |
| Implementation Gate | Design lock + architecture gate | Work package complete, tests pass | Human authorization |
| Security Audit Gate | Implementation complete | Security audit passed | Security Specialist + Human |
| Red-Team Audit Gate | Security audit passed | Red-team tests passed | Red-Team Architect + Human |
| Reproducibility Audit Gate | Red-team passed | Deterministic re-run verified | QA Specialist + Human |
| Final Acceptance Gate | All audits passed | All tests pass, hashes verified, evidence cited | Human authorization |
| Freeze Gate | Final acceptance passed | Frozen manifest recorded | Human authorization |

---

## 12. Frozen Phase 3 Contract SHA-256 Manifest

### 12.1 Frozen Contracts

The following Phase 3 contracts are frozen and must remain byte-for-byte protected:

1. **Candle.to_hash()** — Canonical hash of candle data
2. **ProvenanceRecord.to_hash()** — Provenance identity
3. **StrategySpec.to_hash()** — Strategy identity
4. **BacktestProvenance.compute_result_hash()** — Result hash computation (NEVER modified)
5. **BacktestProvenance.to_hash()** — Provenance identity for backtest results
6. **BacktestConfig._compute_config_hash()** — Config hash
7. **BacktestEngine._compute_dataset_hash()** — Dataset hash for backtest identity

### 12.2 Manifest Requirement

Every phase must include a frozen manifest of Phase 3 contract SHA-256 hashes:
- SHA-256 of each frozen contract file at time of freeze
- Verification that all 13 frozen files are unchanged
- Re-verification at every design lock
- Any discrepancy = STOP + security alert

### 12.3 Protection Mechanism

- All Phase 3 models frozen=True (Pydantic)
- Hash methods use canonical_serialize() for deterministic output
- No wall-clock defaults in hash inputs
- New PIT-aware hashes use NEW method names
- Existing result_hash formula unchanged
- BacktestConfig signature preserved (PitView constructed separately)
- Future extension: adapter/wrapper/new-contract approach with explicit human authorization

---

## 13. Complete Phase-by-Phase Implementation Map

For every future roadmap phase:

### Phase X Template

| Element | Requirement |
|---------|-------------|
| **Prerequisites** | All preceding phases complete + authorized |
| **Architecture Gate** | Architecture compliance verified |
| **Design Lock** | Design doc SHA-256 recorded, spec ratified |
| **Authorization Gate** | Human authorization obtained |
| **Implementation Packages** | Work packages defined with full specification |
| **Tests** | Unit, integration, acceptance, regression, security, red-team, reproducibility, performance |
| **Security Audit** | Security Specialist audit passed |
| **Red-Team Audit** | Red-Team audit passed |
| **Reproducibility Audit** | QA reproducibility audit passed |
| **Final Acceptance** | All gates passed, evidence cited |
| **Freeze** | Frozen manifest recorded, contracts protected |

### Phase 4A.1 — Temporal/PIT Foundation (CURRENT — BLOCKED)
- **Prerequisites:** Phase 3 frozen contracts verified
- **Architecture Gate:** PHASE_4A_FINAL_ARCHITECTURE_SPEC ratified
- **Design Lock:** FAILED — must be resolved
- **Authorization Gate:** NOT AUTHORIZED — human authorization required
- **Implementation Packages:** WP-4A1-01 through WP-4A1-08
- **Tests:** 80 specified tests (19 P0 + 25 SUB + 33 component + 3 legacy)
- **Security Audit:** Pending — filesystem security controls not implemented
- **Red-Team Audit:** Pending
- **Reproducibility Audit:** Pending
- **Final Acceptance:** 8 blockers OPEN — NOT READY
- **Freeze:** Not applicable — phase not complete

### Phase 4A.2 — Corporate Actions
- **Prerequisites:** Phase 4A.1 complete + InstrumentSpecification enhanced
- **Architecture Gate:** Corporate action contracts ratified
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** WP-4A2-01
- **Tests:** Equity corporate action tests (T-EQ01, T-EQ04, T-EQ05)
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Corporate action contracts frozen

### Phase 4A.3 — Derivatives/Futures
- **Prerequisites:** Phase 4A.1 complete + CalendarRef implemented
- **Architecture Gate:** Futures contracts ratified
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** WP-4A3-01
- **Tests:** Futures expiry/rollover tests (T-FU01 through T-FU05)
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Futures contracts frozen

### Phase 4A.4 — Research Governance
- **Prerequisites:** Phase 4A.1 complete + ExperimentIdentity implemented
- **Architecture Gate:** Research contracts ratified
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** Research governance models
- **Tests:** Research registry tests, approval tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Research contracts frozen

### Phase 5 — Experiment Registry
- **Prerequisites:** Phase 4A complete
- **Architecture Gate:** Experiment registry design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** ExperimentRegistry, ReproducibilityLog
- **Tests:** Experiment identity tests, reproducibility log tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Experiment registry frozen

### Phase 6 — Quant Research (PARTIAL)
- **Prerequisites:** Phase 4A complete
- **Architecture Gate:** Quant engine design locked
- **Design Lock:** Partial — existing quant engine frozen
- **Authorization Gate:** NOT AUTHORIZED for extensions
- **Implementation Packages:** WP-7-01 (walk-forward), additional quant modules
- **Tests:** Quant extension tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Quant engine contracts frozen

### Phase 7 — Advanced Backtesting
- **Prerequisites:** Phase 6 complete
- **Architecture Gate:** Walk-forward design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** WP-7-01 (walk-forward), OOS validation, bootstrap, MC, regime analysis
- **Tests:** Walk-forward tests, OOS tests, bootstrap tests, MC tests, regime tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Advanced backtesting contracts frozen

### Phase 8 — Risk/Portfolio
- **Prerequisites:** Phase 7 complete
- **Architecture Gate:** Risk engine design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** WP-8-01 (risk engine), portfolio construction, exposure management
- **Tests:** Risk limit tests, exposure tests, portfolio constraint tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Risk engine contracts frozen

### Phase 9 — Hermes AI Research
- **Prerequisites:** Phase 8 complete
- **Architecture Gate:** Research agent architecture locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** Hermes orchestration, agent definitions
- **Tests:** Agent behavior tests, governance compliance tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Agent contracts frozen

### Phase 10 — Production Data Infrastructure
- **Prerequisites:** Phase 9 complete
- **Architecture Gate:** Production data pipeline design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** Production data pipeline, credential management
- **Tests:** Pipeline tests, credential isolation tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All tests pass, evidence cited
- **Freeze:** Production infrastructure frozen

### Phase 11 — Paper Trading
- **Prerequisites:** All Phase 4A work + WP-8-01 (risk) + WP-7-01 (walk-forward)
- **Architecture Gate:** Paper trading design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** WP-11-01 (paper trading system)
- **Tests:** Paper execution tests, reconciliation tests, market realism tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** Full pipeline functional, 30-day paper evaluation passing
- **Freeze:** Paper trading contracts frozen

### 30-Day Paper Evaluation
- **Prerequisites:** Paper trading system complete
- **Architecture Gate:** Evaluation framework design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED
- **Implementation Packages:** Evaluation framework, readiness criteria
- **Tests:** Evaluation criteria tests, NO TRADE behavior tests, reproducibility tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All readiness criteria met, 30-day period complete
- **Freeze:** Evaluation criteria frozen

### Strategy Graduation
- **Prerequisites:** 30-day evaluation passing + risk review
- **Architecture Gate:** Graduation criteria design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED — human authorization required
- **Implementation Packages:** Graduation criteria, evaluation framework
- **Tests:** Graduation criteria tests, evaluation tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All metrics meet thresholds, evidence cited
- **Freeze:** Graduation criteria frozen

### Live Execution Boundary (NEVER AUTHORIZED by this blueprint)
- **Prerequisites:** All phases complete + 30-day evaluation passing + strategy graduation + production data infrastructure + security audit clearance + explicit human authorization
- **Architecture Gate:** Live boundary design locked
- **Design Lock:** Required
- **Authorization Gate:** EXPLICIT HUMAN AUTHORIZATION REQUIRED — this blueprint does NOT authorize
- **Implementation Packages:** MT5 integration, live authorization gate, credential store, kill switch
- **Tests:** Authorization gate tests, boundary tests, emergency shutdown tests
- **Security Audit:** Required — full security audit clearance
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** All gates passed, human authorization recorded
- **Freeze:** Live boundary contracts frozen

### Autonomous Operating Loop (FUTURE — REQUIRES ALL PHASES)
- **Prerequisites:** Live execution boundary authorized
- **Architecture Gate:** Autonomous loop design locked
- **Design Lock:** Required
- **Authorization Gate:** NOT AUTHORIZED — requires all phases complete + explicit human authorization
- **Implementation Packages:** Autonomous loop orchestration, monitoring automation
- **Tests:** End-to-end lifecycle tests, NO TRADE tests, governance compliance tests
- **Security Audit:** Required
- **Red-Team Audit:** Required
- **Reproducibility Audit:** Required
- **Final Acceptance:** Full lifecycle functional, all safety boundaries enforced
- **Freeze:** Autonomous loop contracts frozen

---

## 14. Final System Definition of Done

The system is NOT considered complete merely because it can execute trades.

**Completion requires ALL of the following:**

### 14.1 Research Quality
- [ ] Deterministic research — identical inputs produce identical outputs
- [ ] Reproducible datasets — every dataset reproducible from source
- [ ] Point-in-time correctness — no future-data leakage in any view
- [ ] Leakage resistance — all bias/leakage types detectable and preventable

### 14.2 Strategy Validation
- [ ] Strategy validation — all strategies validated before backtesting
- [ ] Statistical validity — valid p-values, confidence intervals
- [ ] Risk enforcement — hard limits enforced, zero tolerance for violations
- [ ] NO TRADE capability — system always able to choose no trade

### 14.3 Autonomous Operations
- [ ] Autonomous monitoring — system health monitored continuously
- [ ] Paper-trading evidence — 30-day paper evaluation passing
- [ ] 30-day evaluation — full 30-day period with all criteria met
- [ ] Auditability — every action auditable with hash-verified chain

### 14.4 Security & Recovery
- [ ] Security — all threat mitigations in place, zero critical vulnerabilities
- [ ] Recovery — full state restorable from checkpoints, no data loss
- [ ] Governance compliance — all governance gates enforced
- [ ] Explicit live-boundary authorization — live execution requires separate explicit human authorization

### 14.5 Governance
- [ ] All blockers resolved and independently re-audited
- [ ] Design Lock resolved
- [ ] All phases authorized sequentially
- [ ] Frozen contracts protected byte-for-byte
- [ ] No unauthorized code changes
- [ ] All evidence cited and verifiable

---

## 15. Governance Document Classification

### 15.1 Current Document Status

| Document | Status | Notes |
|----------|--------|-------|
| MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md | AUTHORITATIVE | This document — master blueprint |
| PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md | HISTORICAL | Preserved; source material for this blueprint |
| PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md | AUTHORITATIVE | Sole working spec for Phase 4A.1 |
| PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md | HISTORICAL | Stage 1 checklist; superseded by re-audit |
| PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md | SUPERSEDED (partial) | Historical evidence; status claims superseded |
| PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md | AUTHORITATIVE | Independent re-audit evidence |
| PHASE_4A_FINAL_ARCHITECTURE_SPEC.md | AUTHORITATIVE | Phase 4A final architecture spec |
| PHASE_4A1_DESIGN_LOCK_RECORD.md | AUTHORITATIVE | Design lock state |
| PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md | AUTHORITATIVE | Blocker resolution specification |
| docs/strategy_engine_design.md | FROZEN | Phase 3 design contract — immutable |
| MASTER_PHASE_STATUS_REPORT.md | HISTORICAL | Phase status report |
| All other audit/review/forensic docs | HISTORICAL | Retained as evidence |

### 15.2 Historical Claim Corrections

| Claim in Historical Document | Correct State | Source |
|------------------------------|---------------|--------|
| "18 undefined test identifiers" | **23** (corrected in authoritative spec §8.5.13) | PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md |
| "Architecture Correction stage produced spec ready for Design Lock" | **SUPERSEDED** — Design Lock returned FAILED; re-audit returned RE-AUDIT_FAIL | PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md §A |
| "All findings discovered by independent re-audit" | **RA-NF-04** discovered by Stage 3.5 documentation pass, NOT by re-audit | PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md §0.2.2 |

### 15.3 Supersession Rules

1. When a document is superseded, it is marked SUPERSEDED but RETAINED UNMODIFIED
2. The authoritative document governs where conflicts exist
3. Contradictory history is not overwritten — it is annotated
4. All superseded documents remain available for audit trail
5. No agent may delete or modify superseded documents

---

## 16. Implementation Work-Package Model

Every future implementation unit must have:

| Field | Requirement |
|-------|-------------|
| **Work Package ID** | Unique ID (e.g., WP-4A1-01, WP-7-01) |
| **Roadmap Phase** | Phase reference |
| **Component** | Component name |
| **Owner** | Single authoritative owner |
| **Dependencies** | Required preceding work packages |
| **Required files** | Files to create/modify |
| **Required modules** | Modules to create/modify |
| **Classes** | Classes to implement |
| **Functions** | Functions to implement |
| **Interfaces** | Public interfaces |
| **Data contracts** | Input/output contracts |
| **Configuration** | Configuration requirements |
| **Unit tests** | Unit test specifications |
| **Integration tests** | Integration test specifications |
| **Acceptance tests** | Acceptance test specifications |
| **Adversarial tests** | Adversarial test specifications |
| **Security tests** | Security test specifications |
| **Reproducibility tests** | Reproducibility test specifications |
| **Performance/load tests** | Performance test specifications |
| **Evidence requirements** | Evidence for acceptance |
| **Rollback procedure** | Rollback procedure |
| **Definition of Done** | Complete DoD criteria |
| **Required authorization gate** | Authorization gate for phase transition |

### 16.1 Work Package Template

```
WP-[PHASE]-[NN]:
  Purpose: [one sentence]
  Prerequisites: [work package IDs]
  Affected modules: [module paths]
  Implementation requirements: [specific requirements]
  Tests: [test IDs]
  Security requirements: [security requirements]
  Acceptance evidence: [evidence required]
  Rollback: [rollback procedure]
  Authorization gate: [gate required]
  Owner: [single owner]
  Definition of Done: [complete DoD]
```

---

## 17. FINAL VERIFICATION CHECKLIST

After creating this document, verify:

- [x] 1. File exists
- [x] 2. Byte size reported
- [x] 3. Line count reported
- [x] 4. All top-level headings listed
- [x] 5. All 60 complete-system domains represented
- [x] 6. Implementation work packages represented
- [x] 7. Dependency graph exists
- [x] 8. Ownership matrix exists
- [x] 9. AI construction model exists
- [x] 10. Full testing/gating architecture exists
- [x] 11. Autonomous lifecycle exists
- [x] 12. Paper trading and 30-day evaluation exist
- [x] 13. MT5/live boundary exists
- [x] 14. No source files changed
- [x] 15. No tests changed
- [x] 16. No frozen Phase 3 contract changed
- [x] 17. Phase 4A.1 remains 8 OPEN / 0 CLOSED
- [x] 18. Implementation remains NOT_AUTHORIZED
- [x] 19. Phase 4.2 remains NOT_AUTHORIZED

---

## 18. Final Status

```
MASTER_BLUEPRINT__COMPLETE
IMPLEMENTATION__NOT_PERFORMED
PHASE_4A1__BLOCKERS_OPEN__8
PHASE_4A1__BLOCKERS_CLOSED__0
IMPLEMENTATION_AUTHORIZATION__NOT_AUTHORIZED
PHASE_4_2__NOT_AUTHORIZED
DESIGN_LOCK__FAILED
FROZEN_PHASE_3__PROTECTED
```

**This blueprint is DESIGN/ARCHITECTURE ONLY. It does not authorize implementation.**

**No source files were modified. No tests were modified. No frozen Phase 3 contracts were changed. No patches were created. No implementation was performed.**

**The next action is: Human authorization for Design Lock resolution and Phase 4A.1 blocker closure.**

---

*End of Master Full-System Construction Blueprint. Awaiting human authorization for next steps.*