# PHASE 4A.1 MULTI-AI ARCHITECTURE BLUEPRINT

**Version:** 1.0.0
**Date:** 2026-10-06
**Status:** DESIGN ONLY — NO IMPLEMENTATION AUTHORIZED
**Repository:** C:\Users\muham\ai-trading-lab-data-engine
**Governance:** Phase 4A.1 blockers OPEN: 8 / CLOSED: 0 | Implementation NOT AUTHORIZED | Design Lock FAILED | Phase 4.2 NOT AUTHORIZED
**Frozen Phase 3:** PROTECTED — all contracts immutable
**Created by:** Principal Architect analysis (read-only)

---

## 1. Executive Summary

This document is the authoritative architecture and construction blueprint for the AI Trading Lab data-engine repository. It is produced in ANALYSIS/DESIGN mode only. It must NOT be used to authorize implementation. The single authorized output file is this document.

**Current state:**
- Phase 1 (Core Market Data): IMPLEMENTED, 105 tests passing
- Phase 2 (Data Quality, Provenance & Validation): IMPLEMENTED, 239 tests passing
- Phase 3 (Strategy/Backtest Foundation): IMPLEMENTED with frozen contracts
- Phase 4A.1 (Temporal + PIT Foundation): BLOCKED — 8 OPEN blockers, 0 CLOSED, Design Lock FAILED
- Phase 4A.2+: NOT REACHED

**Governance constraints:**
- 8 Phase 4A.1 blockers remain OPEN
- 0 blockers CLOSED
- Implementation NOT AUTHORIZED
- Phase 4.2 NOT AUTHORIZED
- Frozen Phase 3 contracts are immutable
- Design Lock FAILED — no implementation may proceed until resolved

**Blueprint purpose:** Provide a complete architecture reference for a future implementation AI, with explicit dependency ordering, security threat models, testing architecture, and autonomy boundaries. This document does not authorize any implementation action.

---

## 2. Repository Architecture Inventory

### 2.1 Source Tree

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

### 2.2 Tests

```
tests/
  test_data_engine.py      — 62 tests (Phase 1/2 core)
  test_pit.py              — 97 tests (Phase 4A.1 PIT temporal, 15 classes)
  test_quant.py            — 134 tests (Phase 2 quant, 21 classes)
  test_redteam.py          — 50 tests (red-team/security, 10 classes)
  test_strategy.py         — 82 tests (Phase 3 strategy)
  test_strategy_independent.py — 39 tests (10 classes, 6 pre-existing failures documented)
```

**Total: 464 passing tests** (verified in PHASE_4A_FINAL_ARCHITECTURE_SPEC.md)

### 2.3 Configuration

- pyproject.toml — dependencies, project metadata
- All Pydantic models frozen=True
- No external API keys in repository (credentials are [REDACTED] in docs)

### 2.4 Documentation

- docs/strategy_engine_design.md (92KB) — Master design document
- docs/strategy_engine.md — Strategy engine reference
- docs/quant_engine.md — Quant engine reference
- MASTER_PHASE_STATUS_REPORT.md — Phase status
- PHASE_4A_FINAL_ARCHITECTURE_SPEC.md — Phase 4A finalization (1044 lines)
- PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md — Remediation specification
- PHASE_4A1_MULTI_AI_CONSTRUCTION_BASELINE.md — Construction baseline
- PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md — Blocker resolution
- PHASE_4A1_DESIGN_LOCK_RECORD.md — Design lock record
- 30+ Phase 4A.1 audit/review/forensic documents

### 2.5 Key Models

**Phase 3 Frozen Contracts (immutable):**
- Candle.to_hash()
- ProvenanceRecord.to_hash()
- StrategySpec.to_hash()
- BacktestProvenance.compute_result_hash()
- BacktestProvenance.to_hash()
- BacktestConfig._compute_config_hash()
- BacktestEngine._compute_dataset_hash()

**Phase 4A.1 PIT Models (implemented, not frozen):**
- TemporalContract (contract.py)
- TemporalSemantics (temporal.py)
- AvailabilityPolicy (availability.py)
- InstrumentIdentity (schemas.py — needs enhancement)
- InstrumentSpecification (schemas.py — needs enhancement)
- Venue (schemas.py — needs timezone field)
- DataSource (schemas.py — exists)
- CalendarRef (needs creation)
- PitSidecar (needs creation)
- RevisionChain (needs creation)
- TieBreakerPolicy (needs creation)
- PitView (needs creation)
- PitViewBuilder (needs creation)
- PitViewValidator (needs creation)
- ExperimentIdentity (needs creation)
- PitExperimentConfig (needs creation)

---

## 3. Roadmap Traceability

| Phase | Status | Test Count | Key Components | Classification |
|-------|--------|-----------|----------------|----------------|
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

---

## 5. Phase 4A.1 Architecture Assessment

### 5.1 Implemented Components

| Component | File | Status | Notes |
|-----------|------|--------|-------|
| TemporalSemantics | pit/temporal.py | IMPLEMENTED | UTC normalization, naive rejection, temporal_hash_input |
| TemporalContract | pit/contract.py | IMPLEMENTED | required/eligible/non-eligible fields, MissingFieldPolicy |
| AvailabilityPolicy | pit/availability.py | IMPLEMENTED | PublicationControlledAvailability, RevisionAwareAvailability |
| canonical_serialize() | pit/serialization.py | IMPLEMENTED | Deterministic JSON serialization |
| deterministic_hash() | pit/hashing.py | IMPLEMENTED | SHA-256 of canonical bytes |
| PIT tests | tests/test_pit.py | 97 tests | 15 test classes, all passing |

### 5.2 Missing Components (per PHASE_4A_FINAL_ARCHITECTURE_SPEC)

| Component | Required By | Status |
|-----------|-------------|--------|
| PitSidecar | PIT metadata per dataset | MISSING |
| RevisionChain | Immutable revision history | MISSING |
| TieBreakerPolicy | Deterministic equal-time ordering | MISSING |
| PitView | Time-sliced view at PIT cutoff | MISSING |
| PitViewBuilder | Construct PIT-filtered datasets | MISSING |
| PitViewValidator | Validate temporal eligibility | MISSING |
| ExperimentIdentity | Deterministic experiment identity | MISSING |
| PitExperimentConfig | PIT experiment configuration | MISSING |
| CalendarRef | Trading calendar reference | MISSING |
| Venue (enhanced) | Timezone field | PARTIAL |
| InstrumentIdentity (enhanced) | Stable immutable identifier | PARTIAL |
| InstrumentSpecification (enhanced) | Effective-dated specification | PARTIAL |

### 5.3 Design Decisions (from PHASE_4A_FINAL_ARCHITECTURE_SPEC)

DD-01: PIT metadata in sidecar records, NOT in Phase 3 models
DD-02: New PIT experiment identity requires new schema/version (backward compatible)
DD-03: Future publication excluded silently, not an error
DD-04: Calendar version in experiment identity
DD-05: Revision history append-only
DD-06: Deterministic tie-breakers per experiment
DD-07: Single latest-value NOT sufficient for PIT reconstruction
DD-08: ingestion_time metadata-only, excluded from hashes
DD-09: All PIT timestamps UTC-normalized
DD-10: Corporate actions create new instrument identity events
DD-11: Futures contracts and continuous series distinct
DD-12: Calendar data versioned in experiment identity
DD-13: No wall-clock defaults in new schemas
DD-14: BacktestProvenance.compute_result_hash() NEVER modified
DD-15: Approval as auditable external metadata
DD-16: Synthetic data explicitly labeled in PIT views

### 5.4 Governance State

- 8 blockers OPEN, 0 CLOSED
- Design Lock FAILED
- Implementation NOT AUTHORIZED
- Blocker 1 implemented but NOT closed
- Phase 4.2 NOT AUTHORIZED

---

## 6. Multi-Agent Architecture

**DESIGN ONLY — No agent implementation exists yet.**

### 6.1 Agent Roles

| Agent | Authority | Inputs | Outputs | Tools | Evidence |
|-------|-----------|--------|---------|-------|----------|
| Hermes/Orchestrator | Coordination, not execution | Agent results, roadmap state | Task assignments, final integration | All agents | Audit log |
| Market/Data Agent | Data ingestion only | Provider configs, venue metadata | Raw datasets with provenance | Data ingestion, storage | DataQualityGate report |
| News/Research Agent | Analysis only, no trading | News feeds, research documents | Research findings with citations | Web search, extraction | Cited sources |
| Macro Agent | Macro analysis only | Economic indicators, calendar | Macro assessment | Data access | Provenance record |
| Universe Agent | Universe selection only | Instrument lists, filters | Qualified universe | Data access | Universe snapshot hash |
| Strategy Research Agent | Strategy specification only | Market data, research findings | StrategySpec with conditions | ConditionEvaluator | StrategySpec.to_hash() |
| Quant Validation Agent | Statistical validation only | Backtest results, market data | Validation report | Quant engine (deterministic) | Statistical test outputs |
| Backtesting Agent | Backtest execution only | StrategySpec, Dataset | BacktestProvenance | BacktestEngine | result_hash, config_hash |
| Risk Agent | Risk assessment only | Positions, P&L, market data | Risk report | Risk calculations | Risk metrics |
| Execution Agent | Paper execution only | Orders, market data | Fills, positions | Execution simulator | Execution audit trail |
| Monitoring Agent | Monitoring only | System metrics, data feeds | Health reports | Health checks | Monitoring log |
| Security/Audit Agent | Audit only | All agent outputs, filesystem | Audit report | File inspection | Hash-verified audit |
| Knowledge/Registry Agent | Registry management only | Research outputs | Research registry entries | Registry API | Registry hash |

### 6.2 Failure Behavior

- Any agent producing unverified output → quarantine + escalation
- Any agent requesting live execution → immediate rejection + audit
- Any agent modifying frozen contracts → rejection + security alert
- Any agent bypassing governance → immediate shutdown + human review

### 6.3 Escalation Behavior

- P0/P1 gaps → human authorization required
- Security incidents → emergency shutdown
- Governance violations → all agents paused pending review

### 6.4 Prohibited Actions (All Agents)

- Modify frozen Phase 3 contracts
- Authorize live trading
- Close blockers without human authorization
- Bypass PIT correctness checks
- Modify tests or design docs without explicit approval
- Commit/push without review
- Access credentials/secrets directly
- Override risk limits

---

## 7. Skill Architecture

**DESIGN ONLY — Skills do not yet exist for these capabilities.**

### 7.1 Required Skills

| Skill | Purpose | Dependencies | Contract |
|-------|---------|-------------|----------|
| Market Analysis | OHLCV analysis, regime detection | Data ingestion, temporal semantics | Citable evidence, no future data |
| News Analysis | Event extraction, sentiment | News feeds, source verification | Cited sources, timestamps |
| Macro Analysis | Economic indicator analysis | Calendar, macro data | Provenance, UTC timestamps |
| Fundamentals | Financial statement analysis | Data quality gates | Evidence labeling |
| Technical Analysis | Indicator computation | Quant engine | Deterministic, reproducible |
| Data Engineering | Pipeline construction | All data modules | Provenance, SYNTHETIC blocking |
| PIT/Temporal | Point-in-time correctness | pit module | No future-data leakage |
| Temporal Reasoning | Time-series logic | TemporalSemantics | UTC normalization |
| Provenance | Data lineage tracking | ProvenanceTracker | Hash-verified chain |
| Deterministic Identity | Hash computation | hashing.py | SHA-256 canonical |
| Strategy Generation | Condition trees | ConditionEvaluator | Frozen StrategySpec |
| Backtesting | Engine execution | BacktestEngine | Frozen provenance |
| Walk-Forward Testing | Rolling window validation | Backtesting, Quant | No look-ahead |
| OOS Validation | Out-of-sample testing | Backtesting | Separate data partitions |
| Statistical Validation | Hypothesis testing | Quant statistics | p-values, confidence intervals |
| Robustness | Sensitivity analysis | Quant engine | Multiple parameter checks |
| Stress Testing | Extreme scenario analysis | Risk engine | Scenario definitions |
| Overfitting Detection | Model complexity control | Quant validation | Train/test separation |
| Risk | Risk metrics computation | Position, P&L | Limit enforcement |
| Portfolio Construction | Allocation algorithms | Risk engine | Constraint satisfaction |
| Paper Execution | Simulated trading | Execution simulator | No real money |
| MT5 | Broker interface | MT5 terminal | Read-only initial |
| Monitoring | System health | All agents | Alert thresholds |
| Anomaly Detection | Unusual pattern identification | Data quality | Provenance verification |
| Security | Threat modeling, audit | All components | Zero-trust |
| Source Verification | Data origin validation | Provenance | Citation chain |
| Research Registry | Experiment tracking | All research outputs | Hash-verified |
| Reproducibility | Deterministic re-run | All components | Identical hash on re-run |
| Delegation/Orchestration | Multi-agent coordination | All agents | Governance compliance |

### 7.2 Acceptance Criteria (per skill)

1. Deterministic output for identical inputs
2. Citable evidence for all claims
3. No future-data leakage
4. No modification of frozen contracts
5. Explicit failure conditions documented
6. Adversarial tests defined and passing

### 7.3 Adversarial Tests

- Future-data injection: attempt to use data published after cutoff
- Timezone manipulation: naive datetime rejection
- Hash collision: verify deterministic_hash stability
- Synthetic data misrepresentation: ensure SYNTHETIC labeled
- Look-ahead bias: verify PIT boundary enforcement
- Duplicate order detection: paper execution duplicate prevention
- Credential exposure: verify no secrets in output
- Prompt injection: validate agent input sanitization

---

## 8. Quant Research Architecture

### 8.1 Current State (Phase 2 — Implemented)

The quant engine (v2.0.0) provides deterministic calculations:
- returns.py — return computation
- moving_averages.py — SMA/EMA
- momentum.py — momentum indicators
- volatility.py — volatility measures
- trend.py — trend analysis
- statistics.py — statistical tests
- drawdown.py — drawdown computation
- validation.py — parameter validation
- registry.py — indicator registry

**All quant calculations are deterministic, no LLM calls, no network, no live trading.**

### 8.2 Required Extensions (Future Phases)

| Capability | Phase | PIT Concern |
|-----------|-------|-------------|
| Hypothesis generation | 4A.4+ | ResearchContract approval |
| Parameter search | 6 | Multiple-testing control |
| Walk-forward validation | 7 | No future-data contamination |
| OOS validation | 7 | Separate time partitions |
| Bootstrap | 7 | Resampling within PIT boundaries |
| Monte Carlo | 7 | Synthetic data labeling |
| Sensitivity analysis | 7 | Parameter stability across regimes |
| Stability analysis | 7 | Out-of-time validation |
| Multiple-testing control | 7 | Bonferroni/Holm correction |
| Overfitting detection | 7 | Train/test separation |
| Robustness | 7 | Stress scenario coverage |
| Stress testing | 7 | Extreme regime behavior |
| Regime analysis | 7 | Regime detection PIT-correct |
| Strategy rejection | 7 | NO TRADE decision support |

### 8.3 Bias Prevention

- **Look-ahead bias:** PIT cutoff enforced in PitViewBuilder
- **Survivorship bias:** Universe tracking per date (Phase 4A.2)
- **Leakage:** Temporal隔离 between training/validation/test
- **Future-data contamination:** Publication time checks
- **PIT violations:** PitViewValidator
- **Data snooping:** Independent test partitions
- **Multiple comparisons:** Correction procedures
- **Overfitting:** Complexity penalties, cross-validation

### 8.4 NO TRADE / REJECT

The system must produce explicit NO TRADE or REJECT decisions when:
- Statistical significance not met
- Risk limits exceeded
- Data quality insufficient
- PIT correctness cannot be verified
- Model stability fails
- Overfitting detected

---

## 9. Paper Trading Architecture

### 9.1 Pipeline

Market Data → Signal → Risk Engine → Paper Order Gateway → Execution Simulator → Position → P&L → Analytics → Audit

### 9.2 Required Components (ALL MISSING)

| Component | Purpose | Status |
|-----------|---------|--------|
| Signal Processor | Convert conditions to orders | MISSING |
| Risk Engine | Pre-trade risk checks | MISSING |
| Paper Order Gateway | Accept paper orders | MISSING |
| Execution Simulator | Simulate fills with market realism | MISSING |
| Position Manager | Track positions | MISSING |
| P&L Calculator | Realized/unrealized P&L | MISSING |
| Analytics Engine | Performance analytics | MISSING |
| Audit Logger | Complete trade audit | MISSING |

### 9.3 Market Realism

- Spread: explicit bid-ask model
- Fees: per-trade cost model
- Slippage: latency-based slippage model
- Latency: configurable execution delay
- Partial fills: proportionate fill handling
- Rejected orders: rejection reason logging
- Market gaps: session boundary handling
- Sessions: trading session awareness
- Liquidity: volume-limited fills
- TP/SL: stop-loss and take-profit execution

### 9.4 Reconciliation

- Order → Fill reconciliation
- Position → P&L reconciliation
- Data failure handling
- Execution failure handling
- Risk violation handling
- Emergency shutdown procedure

---

## 10. MT5 / Execution Boundary

### 10.1 Future Architecture (DESIGN ONLY)

| Component | Purpose | Security Requirement |
|-----------|---------|---------------------|
| Broker Validator | Verify broker credentials | Credential isolation |
| Credential Store | Secure credential storage | Never in code/docs |
| Order Limiter | Max order size enforcement | Hard limit |
| Exposure Limiter | Max exposure enforcement | Hard limit |
| Kill Switch | Emergency stop | Immediate execution |
| Execution Audit | All order logging | Immutable log |
| Reconciliation | Order/fill matching | Periodic verification |
| Emergency Shutdown | Stop all execution | Manual confirmation |
| Connection Handler | MT5 connection management | Auto-reconnect with limits |
| Duplicate Protection | Prevent duplicate orders | Order ID tracking |
| Live Authorization Gate | Explicit live authorization | Human approval required |

### 10.2 Authorization Boundary

**LIVE TRADING IS NEVER AUTHORIZED by this blueprint.** Any future live execution requires:
1. Explicit human authorization
2. Completed Phase 4A.1/4A.2/4A.3/4A.4
3. Passing 30-day paper evaluation
4. Strategy graduation approval
5. Production data infrastructure (Phase 10)
6. Security audit clearance

### 10.3 Current MT5 State

No MT5 integration exists in the repository. The quant engine is purely computational with no broker connectivity.

---

## 11. Security and Red-Team Architecture

### 11.1 Threat Model

| Threat | Impact | Mitigation | Required Test |
|--------|--------|-----------|---------------|
| Filesystem traversal | Arbitrary file access | Path validation, sandbox | Path traversal test |
| Arbitrary paths | Data exfiltration | Path normalization, allowlist | Path allowlist test |
| Symlinks | Escape sandbox | Symlink resolution check | Symlink traversal test |
| Subprocess execution | Code execution | Restrict subprocess | Subprocess restriction test |
| Network access | Data exfiltration | Firewall rules, no network | Network isolation test |
| Credentials | Broker access | Credential isolation | Credential leak test |
| API keys | Service abuse | Key rotation, scope limit | Key exposure test |
| Broker credentials | Live trading | Never stored, runtime only | Credential storage test |
| Dependencies | Supply chain | Pin versions, audit | Dependency audit test |
| Tool permissions | Unauthorized actions | Least privilege | Permission audit test |
| Prompt injection | Agent manipulation | Input sanitization | Injection test |
| Malicious market data | Data poisoning | Source verification | Data poisoning test |
| Malicious news data | Misinformation | Source verification | Source verification test |
| Agent trust | Unauthorized actions | No agent has live authority | Agent authority test |
| Unauthorized code changes | Contract violation | Immutable contracts + audit | Change detection test |
| Data poisoning | Future-data leakage | Provenance verification | Poisoning detection test |
| Future-data leakage | PIT violation | PIT cutoff enforcement | Future data test |

### 11.2 Red-Team Results

Existing red-team tests: tests/test_redteam.py (50 tests, 10 classes) — all passing.

### 11.3 Security Principles

- Zero trust: no component trusted by default
- Least privilege: minimum necessary permissions
- Defense in depth: multiple security layers
- Auditability: all actions logged with hashes
- No credentials in code/docs
- Deterministic verification: hash-verified evidence

---

## 12. Testing Architecture

### 12.1 Current Test Suite

| File | Tests | Classes | Status |
|------|-------|---------|--------|
| test_data_engine.py | 62 | — | PASSING |
| test_pit.py | 97 | 15 | PASSING |
| test_quant.py | 134 | 21 | PASSING |
| test_redteam.py | 50 | 10 | PASSING |
| test_strategy.py | 82 | — | PASSING |
| test_strategy_independent.py | 39 | 10 | 6 pre-existing failures |

**Total: 464 passing, 6 pre-existing failures (documented separately)**

### 12.2 Required Test Categories (Future)

| Category | Purpose | Count |
|----------|---------|-------|
| Hash Stability | Deterministic hash verification | 5+ |
| PIT Cutoff Boundary | Cutoff enforcement | 4+ |
| Revision History | Append-only verification | 4+ |
| Missing Temporal Metadata | Handling of incomplete data | 2+ |
| Deterministic Equal-Time Ordering | Tie-breaker verification | 1+ |
| Equity Corporate Actions | Corporate action handling | 3+ |
| Futures Expiry/Rollover | Futures contract handling | 4+ |
| Calendar Version Changes | Calendar versioning | 1+ |
| Invalid/Future Information | Future data rejection | 3+ |
| PIT View Construction | PitViewBuilder verification | 10+ |
| PitViewValidator | PIT validation | 8+ |
| Experiment Identity | Experiment hash uniqueness | 5+ |
| Paper Execution | Simulated execution | 15+ |
| Risk Limits | Risk enforcement | 10+ |
| Reconciliation | Order/fill matching | 8+ |
| Recovery | System recovery | 5+ |
| Security | Threat mitigation | 20+ |
| Adversarial | Adversarial inputs | 15+ |
| Reproducibility | Deterministic re-run | 5+ |

### 12.3 Evidence Requirements

- All tests must produce verifiable evidence
- Hash values must be independently reproducible
- No test may rely on wall-clock time (use frozen timestamps)
- No test may use network access
- No test may use live credentials
- All tests must pass deterministically

---

## 13. External AI Construction Protocol

### 13.1 AI Roles

| Role | Purpose | Permission Level |
|------|---------|-----------------|
| Architecture/Review AI | Review designs, verify compliance | Read + review |
| Primary Implementation AI | Implement work packages | Write (authorized modules only) |
| Independent Code Reviewer | Review implementation quality | Read + review |
| Quantitative Specialist | Validate quant calculations | Read + verify |
| Security Specialist | Audit security controls | Read + audit |
| MT5/Execution Specialist | Review execution safety | Read + review |
| QA/Reproducibility Specialist | Verify tests and reproducibility | Read + verify |
| Hermes Final Integrator | Integrate completed work | Integrate only |

### 13.2 Protocol

**Input:** Authorized work package + design blueprint + frozen contracts
**Role:** Assigned AI role with specific permissions
**Permitted actions:** Write to authorized modules only, run tests, generate evidence
**Forbidden actions:** Modify frozen contracts, close blockers, authorize phases, commit
**Expected output:** Implementation + tests + evidence + hash verification
**Acceptance criteria:** All tests pass, hashes verified, evidence cited, no governance violations
**Handoff:** To next AI role or Hermes integrator
**Rollback:** Revert to last verified checkpoint via git

### 13.3 Controls

- Single AI writes at a time (no parallel uncontrolled edits)
- Branch/worktree per work package
- Patch-based reconciliation
- No simultaneous multi-AI editing
- All changes reviewed before merge
- Free/local tools only (no paid AI services required)

---

## 14. Dependency-Aware Construction Order

### 14.1 Work Package Ordering

**BLOCKED — Cannot begin until Phase 4A.1 blockers resolved:**

| Dependency Chain | Order | Reason |
|-----------------|-------|--------|
| Temporal contracts | 1 | Foundation for all PIT work |
| PitSidecar/RevisionChain | 2 | Depends on temporal contracts |
| PitViewBuilder/Validator | 3 | Depends on sidecar/chain |
| ExperimentIdentity | 4 | Depends on view computation |
| CalendarRef | 5 | Independent but needed for multi-asset |
| Venue enhancement | 6 | Independent timezone field |
| InstrumentIdentity enhancement | 7 | Depends on contract stability |
| PIT integration with backtest | 8 | Depends on all above |
| Corporate actions (4A.2) | 9 | Depends on InstrumentSpecification |
| Futures (4A.3) | 10 | Depends on venue/calendar |
| Research governance (4A.4) | 11 | Depends on experiment identity |
| Paper trading | 12 | Depends on PIT correctness |
| MT5/execution | NEVER | Requires all above + authorization |

### 14.2 Foundation-First Principle

Higher-level autonomous capabilities MUST NOT be implemented while foundational PIT/temporal/identity/provenance contracts remain unresolved. The construction order must respect:

1. Temporal correctness
2. PIT correctness
3. Deterministic identity
4. Provenance integrity
5. Statistical validity
6. Risk controls
7. Security
8. Auditability
9. Execution boundaries

---

## 15. Hermes Repository Ingestion / Skill Adaptation Protocol

### 15.1 Ingestion Steps

When Hermes ingests a completed external construction:

1. **Inventory repository** — catalog all modules, tests, configs
2. **Inventory agents** — identify agent definitions and roles
3. **Inventory skills** — identify skill capabilities
4. **Inventory contracts** — identify all domain contracts
5. **Inventory tests** — catalog test coverage
6. **Map against roadmap** — trace against Master Development Roadmap
7. **Detect conflicts** — identify any contract conflicts
8. **Identify gaps** — classify missing capabilities
9. **Adapt compatible capabilities** — integrate compatible components
10. **Reject incompatible capabilities** — reject violations of governance
11. **Run functional tests** — execute full test suite
12. **Run adversarial tests** — execute red-team suite
13. **Verify reproducibility** — confirm deterministic re-run
14. **Produce final capability matrix** — classify all capabilities

### 15.2 Capability Classifications

- **ADAPTED** — Compatible, integrated with minor adaptation
- **PARTIALLY_ADAPTED** — Partially compatible, requires modification
- **NOT_ADAPTED** — Incompatible, rejected
- **CONFLICTING** — Conflicts with existing contracts
- **NOT_NEEDED** — Redundant with existing capability
- **UNKNOWN** — Insufficient evidence to classify

### 15.3 Ingestion Rules

- Frozen contracts cannot be adapted
- Blocked components cannot be ingested as complete
- Implementation without authorization is rejected
- Missing governance documentation is rejected
- Unverified evidence is rejected

---

## 16. Autonomy Boundaries

### 16.1 What Autonomous Systems May Do

- Compute deterministic quant metrics
- Generate condition trees
- Execute backtests on provided data
- Produce statistical validation reports
- Monitor system health
- Generate research findings with citations
- Validate data quality
- Construct PIT views (when implemented)
- Simulate paper execution

### 16.2 What Autonomous Systems May NOT Do

- Modify frozen Phase 3 contracts
- Close blockers
- Authorize implementation phases
- Execute live trades
- Access broker credentials
- Bypass PIT correctness checks
- Override risk limits
- Bypass governance gates
- Modify tests or design docs
- Commit without review
- Access network without authorization
- Run subprocesses without restriction

### 16.3 Human Authorization Gates

| Decision | Required Authorization |
|----------|----------------------|
| Close Phase 4A.1 blocker | Human authorization |
| Authorize Phase 4A.2 | Human authorization |
| Authorize Phase 4.2 | Human authorization |
| Live trading | Explicit human authorization |
| Modify frozen contract | Human authorization + new contract |
| Design lock resolution | Human authorization |
| Production deployment | Human authorization + security audit |
| MT5 connection | Human authorization + credential verification |

---

## 17. 30-Day Paper Trading Readiness

### 17.1 Readiness Criteria

| Category | Criteria | Measurement |
|----------|----------|-------------|
| Functional correctness | All tests pass | 464 + new tests |
| PIT correctness | No future-data leakage | PitViewValidator |
| Deterministic identity | Hash stability | Hash regression tests |
| Provenance | Complete audit trail | Provenance verification |
| Temporal correctness | UTC normalization | Temporal tests |
| Statistical validity | Valid p-values | Statistical tests |
| Risk | Limits enforced | Risk tests |
| Execution simulation | Realistic fills | Execution tests |
| Monitoring | Health checks pass | Monitoring tests |
| Audit | Complete logging | Audit tests |
| Reproducibility | Deterministic re-run | Reproducibility tests |
| Recovery | System recovery | Recovery tests |
| Security | Threat mitigation | Security tests |
| Strategy lifecycle | Full lifecycle | Lifecycle tests |
| NO TRADE behavior | Reject when criteria unmet | NO TRADE tests |

### 17.2 Performance Measurements

| Metric | Target | Measurement |
|--------|--------|-------------|
| Return | Strategy-dependent | Daily/weekly/monthly |
| Drawdown | Within risk limits | Max drawdown |
| Volatility | Within risk limits | Annualized |
| Trade count | Sufficient sample | Total trades |
| Turnover | Reasonable | Turnover ratio |
| Spread cost | Modeled accurately | Spread impact |
| Slippage | Modeled accurately | Slippage impact |
| Fees | Modeled accurately | Fee impact |
| Failed orders | Minimal | Failure rate |
| Data failures | Minimal | Failure rate |
| Risk violations | Zero | Violation count |
| System failures | Zero | Failure count |
| Abnormal behavior | None | Anomaly detection |
| Regime behavior | Consistent | Regime analysis |
| Reproducibility | 100% | Hash match on re-run |

---

## 18. Critical Gaps

### 18.1 P0 — Blocking

| ID | Gap | Evidence |
|----|-----|----------|
| G-P0-1 | Phase 4A.1 blockers unresolved (8 OPEN) | governance state |
| G-P0-2 | Design Lock FAILED | PHASE_4A1_DESIGN_LOCK_RECORD.md |
| G-P0-3 | PitSidecar not implemented | Phase 4A spec Part 4 |
| G-P0-4 | RevisionChain not implemented | Phase 4A spec Part 4 |
| G-P0-5 | PitViewBuilder not implemented | Phase 4A spec Part 4 |
| G-P0-6 | PitViewValidator not implemented | Phase 4A spec Part 4 |
| G-P0-7 | ExperimentIdentity not implemented | Phase 4A spec Part 4 |
| G-P0-8 | TieBreakerPolicy not implemented | Phase 4A spec Part 4 |

### 18.2 P1 — High Priority

| ID | Gap | Evidence |
|----|-----|----------|
| G-P1-1 | CalendarRef not created | Phase 4A spec Part 4 |
| G-P1-2 | Venue timezone field missing | Phase 4A spec UQ-09 |
| G-P1-3 | InstrumentIdentity enhancement needed | Phase 4A spec Part 5 |
| G-P1-4 | InstrumentSpecification enhancement needed | Phase 4A spec Part 5 |
| G-P1-5 | Corporate actions engine (4A.2) | Roadmap traceability |
| G-P1-6 | Futures rollover engine (4A.3) | Roadmap traceability |
| G-P1-7 | Paper trading architecture | Roadmap traceability |
| G-P1-8 | Risk engine | Roadmap traceability |

### 18.3 P2 — Medium Priority

| ID | Gap | Evidence |
|----|-----|----------|
| G-P2-1 | Research governance (4A.4) | Roadmap traceability |
| G-P2-2 | Experiment registry (Phase 5) | Roadmap traceability |
| G-P2-3 | Advanced backtesting (Phase 7) | Roadmap traceability |
| G-P2-4 | Walk-forward validation | Quant research architecture |
| G-P2-5 | Overfitting detection | Quant research architecture |
| G-P2-6 | Multiple-testing control | Quant research architecture |
| G-P2-7 | Stress testing framework | Quant research architecture |
| G-P2-8 | Regime analysis | Quant research architecture |

### 18.4 P3 — Lower Priority

| ID | Gap | Evidence |
|----|-----|----------|
| G-P3-1 | Strategy graduation criteria | Roadmap traceability |
| G-P3-2 | Production data infrastructure | Roadmap traceability |
| G-P3-3 | MT5 integration | Roadmap traceability |
| G-P3-4 | Monitoring automation | Roadmap traceability |
| G-P3-5 | Anomaly detection | Roadmap traceability |
| G-P3-6 | Source verification system | Roadmap traceability |

### 18.5 UNKNOWN

| ID | Gap | Reason |
|----|-----|--------|
| G-U-1 | Exact blocker closure criteria | Not documented in accessible files |
| G-U-2 | Design lock resolution path | Design Lock FAILED, path unclear |
| G-U-3 | Quant engine integration with PIT | No evidence of PIT-aware quant |
| G-U-4 | Multi-asset adapter completeness | Partial evidence only |
| G-U-5 | Recovery procedure specifics | Not documented |

---

## 19. Detailed Implementation Work Packages

**ALL WORK PACKAGES ARE BLOCKED pending Phase 4A.1 blocker resolution and human authorization.**

### WP-4A1-01: PitSidecar Implementation

- **ID:** WP-4A1-01
- **Purpose:** Record temporal metadata snapshot per dataset version
- **Prerequisites:** TemporalContract (implemented), DD-01 compliance
- **Affected modules:** src/data_engine/pit/, src/data_engine/schemas.py
- **Implementation requirements:** Frozen model, immutable once created, dataset_id + dataset_version reference
- **Tests:** PIT tests (existing 97 + new for sidecar)
- **Security requirements:** No wall-clock defaults, no future-data leakage
- **Acceptance evidence:** Hash-verified sidecar, 97+ tests passing
- **Rollback:** Remove module, revert to pre-implementation state

### WP-4A1-02: RevisionChain Implementation

- **ID:** WP-4A1-02
- **Purpose:** Immutable append-only revision history
- **Prerequisites:** WP-4A1-01, DD-05 compliance
- **Affected modules:** src/data_engine/pit/
- **Implementation requirements:** Append-only, hash-linked entries, no modification/deletion
- **Tests:** Revision history tests (T-R01 through T-R04)
- **Security requirements:** Integrity verification, tamper detection
- **Acceptance evidence:** Hash chain verified, append-only enforced
- **Rollback:** Remove module, revert to pre-implementation state

### WP-4A1-03: TieBreakerPolicy Implementation

- **ID:** WP-4A1-03
- **Purpose:** Deterministic equal-time ordering
- **Prerequisites:** TemporalSemantics (implemented), DD-06 compliance
- **Affected modules:** src/data_engine/pit/
- **Implementation requirements:** Declarative policy, included in view_hash, deterministic
- **Tests:** Ordering tests (T-O01)
- **Security requirements:** No insertion-order dependency
- **Acceptance evidence:** Deterministic ordering for identical timestamps
- **Rollback:** Remove module, revert to pre-implementation state

### WP-4A1-04: PitViewBuilder Implementation

- **ID:** WP-4A1-04
- **Purpose:** Construct PIT-filtered datasets from raw datasets + PitSidecar
- **Prerequisites:** WP-4A1-01, WP-4A1-02, WP-4A1-03, DD-03 compliance
- **Affected modules:** src/data_engine/pit/, src/data_engine/strategy/backtest.py (no signature change)
- **Implementation requirements:** Exclude future data silently, cache default sidecar
- **Tests:** PIT cutoff boundary tests (T-P01 through T-P04)
- **Security requirements:** No future-data leakage, no look-ahead
- **Acceptance evidence:** PIT-filtered dataset verified, BacktestConfig unchanged
- **Rollback:** Remove module, ensure backtest.py signature unchanged

### WP-4A1-05: PitViewValidator Implementation

- **ID:** WP-4A1-05
- **Purpose:** Validate temporal eligibility against PIT cutoff
- **Prerequisites:** WP-4A1-04, DD-14 compliance
- **Affected modules:** src/data_engine/pit/
- **Implementation requirements:** Separate from DataQualityGate, runs after data quality check
- **Tests:** Validation tests (T-X01, T-X02, T-X07)
- **Security requirements:** No bypass of data quality checks
- **Acceptance evidence:** Valid PIT views verified, invalid rejected
- **Rollback:** Remove module, ensure DataQualityGate unchanged

### WP-4A1-06: ExperimentIdentity Implementation

- **ID:** WP-4A1-06
- **Purpose:** Deterministic experiment identity computation
- **Prerequisites:** WP-4A1-04, DD-02, DD-04 compliance
- **Affected modules:** src/data_engine/pit/, src/data_engine/strategy/provenance.py
- **Implementation requirements:** view_hash + experiment_id computation, new method names
- **Tests:** Hash stability tests (T-H01 through T-H05)
- **Security requirements:** result_hash formula unchanged
- **Acceptance evidence:** Unique experiment IDs, hash stability verified
- **Rollback:** Remove module, ensure compute_result_hash() unchanged

### WP-4A1-07: CalendarRef Implementation

- **ID:** WP-4A1-07
- **Purpose:** Trading calendar reference with versioning
- **Prerequisites:** None (independent), DD-12 compliance
- **Affected modules:** src/data_engine/schemas.py (new), src/data_engine/pit/
- **Implementation requirements:** calendar_id + calendar_version, periods_per_year property
- **Tests:** Calendar version tests (T-C01)
- **Security requirements:** No wall-clock defaults
- **Acceptance evidence:** Calendar versioning verified, periods_per_year correct
- **Rollback:** Remove model, revert metrics.py periods_per_year dict

### WP-4A1-08: Venue/Instrument Enhancement

- **ID:** WP-4A1-08
- **Purpose:** Add timezone to Venue, enhance InstrumentIdentity/Specification
- **Prerequisites:** WP-4A1-07, DD-09 compliance
- **Affected modules:** src/data_engine/schemas.py
- **Implementation requirements:** Venue.timezone field, InstrumentIdentity stable identifier
- **Tests:** Timezone tests, identity tests
- **Security requirements:** UTC normalization, naive rejection
- **Acceptance evidence:** Timezone handling verified, identity stable
- **Rollback:** Remove fields, revert to pre-enhancement state

### WP-4A2-01: Corporate Actions Engine

- **ID:** WP-4A2-01
- **Purpose:** Equity corporate action handling
- **Prerequisites:** WP-4A1-08, InstrumentSpecification enhancement
- **Affected modules:** src/data_engine/strategy/equity.py, new corporate action models
- **Implementation requirements:** Split, Dividend, SymbolChange, Delisting models
- **Tests:** Equity corporate action tests (T-EQ01, T-EQ04, T-EQ05)
- **Security requirements:** Historical data preservation, adjusted price separation
- **Acceptance evidence:** Corporate actions create new specification versions
- **Rollback:** Remove corporate action models, revert equity.py

### WP-4A3-01: Futures/Rollover Engine

- **ID:** WP-4A3-01
- **Purpose:** Futures contract and continuous series handling
- **Prerequisites:** WP-4A1-07, CalendarRef
- **Affected modules:** New futures models, continuous series models
- **Implementation requirements:** FuturesContract, ContinuousSeries, RolloverPolicy
- **Tests:** Futures expiry/rollover tests (T-FU01 through T-FU05)
- **Security requirements:** Roll leakage detection, PIT-correct roll decisions
- **Acceptance evidence:** Futures contracts and continuous series distinct
- **Rollback:** Remove futures models, revert to pre-implementation state

### WP-7-01: Walk-Forward Validation

- **ID:** WP-7-01
- **Purpose:** Rolling window backtest validation
- **Prerequisites:** WP-4A1-04 (PIT-filtered datasets), all Phase 4A.1 work
- **Affected modules:** New walk-forward module, quant/registry.py
- **Implementation requirements:** Rolling window, no look-ahead, PIT-correct
- **Tests:** Walk-forward specific tests
- **Security requirements:** No future-data contamination
- **Acceptance evidence:** Walk-forward results reproducible, no look-ahead
- **Rollback:** Remove walk-forward module

### WP-8-01: Risk Engine

- **ID:** WP-8-01
- **Purpose:** Risk metrics and limit enforcement
- **Prerequisites:** Position management (existing), P&L (existing)
- **Affected modules:** New risk module, strategy/position.py, strategy/equity.py
- **Implementation requirements:** Risk metrics, limit checks, exposure tracking
- **Tests:** Risk limit tests, exposure tests
- **Security requirements:** Hard limits, no override
- **Acceptance evidence:** Risk limits enforced, violations detected
- **Rollback:** Remove risk module

### WP-11-01: Paper Trading System

- **ID:** WP-11-01
- **Purpose:** Full paper trading pipeline
- **Prerequisites:** All Phase 4A work, WP-8-01 (risk), WP-7-01 (walk-forward)
- **Affected modules:** New paper trading modules, execution simulator
- **Implementation requirements:** Market Data → Signal → Risk → Gateway → Simulator → Position → P&L → Analytics → Audit
- **Tests:** Paper execution tests, reconciliation tests
- **Security requirements:** No real money, no broker credentials
- **Acceptance evidence:** Full pipeline functional, 30-day paper evaluation passing
- **Rollback:** Remove paper trading modules

---

## 20. Acceptance and Evidence Model

### 20.1 Evidence Types

| Evidence Type | Format | Verification |
|---------------|--------|-------------|
| Test results | pytest output | Independent re-run |
| Hash values | SHA-256 hex | Independent computation |
| Audit logs | Structured records | Hash-verified chain |
| Provenance records | Structured metadata | to_hash() verification |
| Performance metrics | JSON/CSV | Deterministic re-computation |
| Security findings | Structured report | Independent review |

### 20.2 Acceptance Criteria per Work Package

1. All new tests pass
2. Existing tests still pass (464 baseline)
3. Hash values independently reproducible
4. No modification of frozen contracts
5. No governance violations
6. Evidence cited for all claims
7. Security requirements met
8. Rollback procedure tested

### 20.3 Evidence Hierarchy

1. **Independent verification** — Third-party re-run of tests/hashes
2. **Test execution** — pytest output with pass/fail
3. **Hash computation** — Deterministic hash of artifacts
4. **Audit trail** — Structured log of all actions
5. **Code review** — Human review of implementation

---

## 21. Rollback / Recovery Model

### 21.1 Checkpoint Model

- Each work package creates a verifiable checkpoint
- Checkpoint = git state + test results + hash values
- Checkpoints are independent and restorable
- Failed work package rolls back to last verified checkpoint

### 21.2 Rollback Procedures

| Scenario | Action | Evidence |
|----------|--------|----------|
| Work package failure | Revert to pre-work-package checkpoint | Git diff + test results |
| Frozen contract modification | Immediate rollback + security alert | Hash comparison |
| Governance violation | All work paused + human review | Audit log |
| Security incident | Emergency shutdown + forensic audit | Security findings |
| Data corruption | Restore from last verified state | Hash verification |
| Test regression | Revert work package + investigate | Test comparison |

### 21.3 Recovery Requirements

- Full repository state restorable from git
- Test suite re-runnable for verification
- Hash values re-computable for verification
- Audit trail complete for post-incident review
- No data loss in rollback
- No credential exposure in rollback

### 21.4 Pre-Existing Failures

6 pre-existing failures in test_strategy_independent.py are documented as separate defects (not Phase 4A.1 blockers). These are NOT addressed by this blueprint and require separate human authorization for remediation.

---

## 22. Final Construction Sequence

**THIS SEQUENCE IS A PLAN, NOT AUTHORIZATION.**

### Phase A: Prerequisites (Blocked)

1. Resolve 8 Phase 4A.1 blockers (human authorization required)
2. Fix Design Lock FAILED (human authorization required)
3. Close Blocker 1 (currently implemented but NOT closed)

### Phase B: Foundation (Sequential)

4. WP-4A1-01: PitSidecar
5. WP-4A1-02: RevisionChain
6. WP-4A1-03: TieBreakerPolicy
7. WP-4A1-04: PitViewBuilder
8. WP-4A1-05: PitViewValidator
9. WP-4A1-06: ExperimentIdentity
10. WP-4A1-07: CalendarRef
11. WP-4A1-08: Venue/Instrument enhancement

### Phase C: Asset Classes (Parallel possible after foundation)

12. WP-4A2-01: Corporate Actions Engine
13. WP-4A3-01: Futures/Rollover Engine

### Phase D: Research & Validation

14. WP-7-01: Walk-Forward Validation
15. WP-8-01: Risk Engine

### Phase E: Paper Trading

16. WP-11-01: Paper Trading System

### Phase F: Evaluation & Graduation

17. 30-Day Paper Evaluation
18. Strategy Graduation Criteria

### Phase G: Execution Boundary (NEVER AUTHORIZED without explicit human authorization)

19. MT5 Integration (read-only initial)
20. Live Execution Gate (requires explicit human authorization)

---

## Document Control

**This blueprint is DESIGN ONLY. It does not authorize implementation.**

**Governance state at time of creation:**
- Phase 4A.1 blockers: 8 OPEN / 0 CLOSED
- Implementation: NOT AUTHORIZED
- Design Lock: FAILED
- Phase 4.2: NOT AUTHORIZED
- Frozen Phase 3: PROTECTED

**Pre-existing repository state vs. this task:**
- All files analyzed were pre-existing
- This task created exactly ONE file: PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md
- No source, test, configuration, or existing documentation files were modified
- No git commits, stages, resets, restores, checkouts, renames, deletions, reformatting, or line-ending normalization performed

---

*End of blueprint. Awaiting human authorization for next steps.*
