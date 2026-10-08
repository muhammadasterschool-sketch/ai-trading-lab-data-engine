# AI Trading Lab — Trading Runtime Architecture Audit

```text
Document Type:  Repository audit (runtime-integration lens; mandated deliverable
                of the FINAL INTEGRATED RUNTIME Master Prompt §2 FIRST TASK)
Phase:          Runtime integration era (FINAL INTEGRATED RUNTIME mandate)
Authority:      B — CURRENT SUPPORTING (audit baseline of record for the
                runtime-integration mandate; complements — does not supersede —
                the construction, expansion and readiness authorities)
Status:         CURRENT
Version:        1.0.0 (initial baseline — §2 repository audit)
Last Updated:   2026-10-08
Supersedes:     none (first runtime-integration audit; the autonomy-status
                authority remains ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md; the
                5-family readiness authority remains the external
                AI_TRADING_LAB_ARCHITECTURE_READINESS_AUDIT.md)
Superseded By:  —
Source Evidence: git @ 3567c69 (main = phase-4a/4a1-architecture-correction,
                remote synced); fresh test run 1059/1059 (17.54 s);
                final_gate_verify.py 5/5 PASS; three parallel read-only source
                surveys (execution domain; data/intelligence domain;
                governance/infra + connectivity); first-hand re-verification of
                every defect claim (ARCH-F1/F3 line-verified; ARCH-F4 and the
                CLI check-boundary inversion reproduced by execution)
```

---

## 0. Mandate registration + audit method

The operative mandate is the operator-issued **“HERMES / Z.AI — AI Trading Lab — FINAL INTEGRATED RUNTIME + MEMORY + LEDGER + PAPER/LIVE EXECUTION — MASTER IMPLEMENTATION PROMPT”** (64 sections, §0–§63): transform the existing platform from a collection of individually implemented components into a **single integrated, event-driven, stateful, auditable, memory-aware, testable and governed autonomous trading runtime**, implemented in the exact order PHASE A–AF (§60), with PAPER as the only default execution mode and LIVE capital permanently behind an explicit human authorization boundary (§1: the AI must never enable live trading, create broker credentials, increase risk limits, bypass risk gates or reconciliation, approve its own promotion, or modify frozen Phase 3 contracts).

Per **§2 FIRST TASK — REPOSITORY AUDIT**, before modifying any code the entire repository was inspected against the 29 mandated points — components, public interfaces, dependencies, duplicate implementations, unconnected components, test-only components, missing runtime orchestration, model loading, persistence/state, configuration, logging/observability, execution simulator, OMS, reconciliation, kill switches, broker adapters, paper/live separation, event/message mechanisms, TODO/STUB/NOT_IMPLEMENTED paths, memory/state systems, trade/order/fill ledgers, experiment tracking, model-performance attribution, audit/event stores, databases/persistence layers, dashboards/reporting, replay systems, incident/recovery systems — and this document was produced with the 19 mandated content items plus the exact implementation order (§16). Per §2’s own rule: **no component was assumed operational merely because a file/class exists.**

**Audit method.** Three parallel read-only source surveys covered (a) the **execution domain** (`paper/`, `risk/`, `discovery/`, frozen-strategy public surfaces, CLI exposure), (b) the **data/intelligence domain** (16 root modules, `pit/`, `prediction/`, `quant/`), and (c) the **governance/infra domain plus the AST-level src-internal import graph** (`hermes/`, `infra/`, `research/`, `research_validation/`, `experiment_registry/`, `knowledge/`, `benchmarks/`, `derivatives/`, `actions/`, repo-level facts, runtime entry points). Every claimed defect was then re-verified first-hand by the auditing agent: ARCH-F1 at `risk/engine.py:174-176`, ARCH-F3 at `ingestion.py:191` (import list confirmed absent), ARCH-F4 reproduced by execution (`NameError: name 'datetime' is not defined`), and the CLI `check-boundary` inversion reproduced by execution (exit code 1 on a valid deterministic calculation type).

**Ground truth (verified this cycle):**

| Check | Result |
|---|---|
| Repository HEAD | `3567c69` — `main` = `phase-4a/4a1-architecture-correction`, remote synced (`git ls-remote`) |
| Working tree | Clean; zero uncommitted changes |
| Test suite | **1059 / 1059 passed** (fresh run this cycle, 17.54 s) |
| Frozen gates | `final_gate_verify.py` **5/5 PASS** (11/11 frozen Phase-3 blobs vs `main@13fdc7e`; SUB-18 manifest 13/13; secret scan 0/259 files; untracked empty; tree clean). Cosmetic: the script prints a stale cycle label (`e7505d3`) — registered defect; the checks themselves pass against the current tree |
| CI | `.github/` ABSENT — WP-12 spec ready, HUMAN_DECISION_REQUIRED (unchanged) |
| Governance states | PRED-F1/F2/F3 CLOSED · ADVANCED_ML DEFERRED · REAL_DATA_VALIDATION BLOCKED · VERIFIED_YEARS = 0 · H-1 OPEN/CONTAINED · LIVE TRADING NOT AUTHORIZED — **all preserved, none weakened by this audit** |
| New-machinery absence | Event bus, scheduler, TradingRuntime, OMS/execution-adapter layer, broker adapters, persistence layer, dashboards, incident store: all verified ABSENT in `src/` (greps + full module reads) |

**Implementation status of the runtime mandate: NOT STARTED.** This cycle modified zero source files. This document completes **PHASE A** of §60. Coding begins only after this audit, in PHASE B+ order.

**No duplicate specifications (§61 compliance).** Only the §2-mandated `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` (this document) was created. The remaining 23 §61 spec documents are deliberately NOT created now: each belongs to its implementing phase, and creating them ahead of their phase would produce competing paper specifications — exactly what §61 forbids. Existing authorities remain authoritative (see §18).

---

## 1. Executive summary — what the repository IS today

The repository is a **point-in-time (PIT) multi-asset market-data engine and governed quantitative research platform**, implemented as a Python src-layout library (126 `.py` files: 16 root modules + 16 subpackages, ≈31,940 LOC; dependencies deliberately limited to `pydantic`/`numpy`/`pandas`/`pytest`; no NN framework, no network stack, no database). It covers, as **tested library components**: file-CSV ingestion → validation/quarantine → PIT views → deterministic quant features → frozen Phase-3 strategy backtests → research validation (bias/leakage/walk-forward/robustness) → a governed prediction laboratory (PIT features → labels → regimes → deterministic models → calibration → uncertainty → drift → gates → crash-risk estimation, all fail-closed with machine-readable refusals) → a risk engine (5 hard limits, kill switch, hash-chained violations) → paper-trading components (gateway, deterministic simulator, three-way reconciliation, 30-day evaluation, human-token graduation, deny-by-default live gate) → Hermes agent governance → observability + hash-chained audit chains. **1059 tests pin all of it.**

What does **not** exist anywhere in `src/` is the **runtime**. There is no composition root, no event bus, no scheduler, no daemon, no service loop, no background thread, no persistent state store, and — most consequentially — the **hard risk gate, the reconciliation engine, and the execution audit logger are not wired into the paper order path**. The only entry points are an informational 5-subcommand CLI (four subcommands are print-only no-ops; the fifth is inverted and always exits 1), the test suite (the de-facto runtime that constructs and exercises every subsystem), and direct library import. The repository is precisely the “collection of individually implemented components” that the mandate’s §0 MISSION requires to become “a SINGLE INTEGRATED, EVENT-DRIVEN, STATEFUL, AUDITABLE, MEMORY-AWARE, TESTABLE AND GOVERNED AUTONOMOUS TRADING RUNTIME.” This audit is the verified map from here to there.

**The wiring truth (headline table):**

| Mandate pipeline stage | Component exists? | Wired into any runtime path in `src/`? |
|---|---|---|
| Market data (provider/ingestion) | YES | **NO** — zero callers of `DataIngester.ingest()` in `src/` or `tests/` |
| Data validation / quarantine | YES | only inside `ingest()` (itself uncalled) |
| Storage (3 tiers) | YES (in-memory) | **NO** — `DataStorage.store_*` never called by any src module |
| PIT views (`pit/view.py`) | YES | only via benchmarks (themselves test-only) |
| Quant features (`quant/features.py`) | YES | only via benchmarks |
| Prediction features/labels/models | YES | via `CrashRiskEstimator.assess()` (test/benchmark only) |
| Model registry / artifact verification | YES | registry in-memory; no loader (see §7.1) |
| Calibration / uncertainty / regime / crash | YES | via estimator |
| **Decision engine** | **NO** | — |
| Position sizing (inverse-vol) | YES | only via benchmarks |
| **HARD RISK GATE** | YES (`RiskEngine`) | **NOT in the paper order path** — `paper/gateway.py` imports no risk module |
| Kill switch | YES | not consulted by gateway; state volatile (in-memory) |
| OMS (paper gateway) | YES | test/benchmark only |
| Execution simulator | YES | test/benchmark only |
| **Reconciliation** | YES (3-way) | **zero src callers** |
| Execution audit logger | YES (`AuditLogger`) | **never invoked by the gateway** |
| Runtime ledgers (order/fill/position/trade/P&L) | **NO** (only prediction outcome ledger + per-domain chains) | caller-driven |
| Memory subsystem | knowledge/memory stores | test-only; in-memory |
| Monitoring / health / alerts | YES (`infra/`) | test-only; pull-based `Monitor.poll()` |
| Recovery / checkpoints | YES (in-memory) | test-only |
| `TradingRuntime` / supervisor | **NO** | — |

**Bottom line:** every safety-critical component the mandate requires for PHASE L–T (risk gate, OMS, ledgers, reconciliation, kill switch) already exists as a tested component — the integration work is wiring, event model, persistence, and orchestration, not re-implementation. Conversely, the safety posture is currently **structural but not operational**: the risk gate and reconciliation cannot protect a runtime they are not wired into.

---

## 2. Component inventory (§2 items 1–2 — components and public interfaces)

126 `.py` files: 16 root modules + 16 subpackages, ≈31,940 LOC. All classes are
pydantic models or plain classes with explicit frozen/config discipline; all
deterministic identities are SHA-256 over canonical serialization via the
shared substrate `pit/hashing.py::deterministic_hash` (prefixed per domain).

| Package (modules) | Domain | Key public surface (verified) |
|---|---|---|
| root (16) | data foundation | `MarketDataProvider`/`ProviderFactory`/`FileDataProvider` (provider.py; FS-01..24 containment, instrument allowlist); `DataIngester.ingest()` (ingestion.py); `DataStorage` 3-tier (storage.py, in-memory); `DataValidator` (validation.py); `QuarantineManager` (quarantine.py); `DataQualityGate`/`DATA_QUALITY_BLOCKED` (data_blocked.py, fail-closed); `Candle`/`Dataset`/`ProviderConfig`/`ProvenanceRecord` (schemas.py); `InstrumentRegistry` (instruments.py); timeframe tables (timeframes.py); `EvidenceProvenance`/evidence labels (evidence.py); `ProvenanceTracker` (provenance.py); `SecurityConfig`/`SecurityAuditTrail`/FS containment (security.py); `DataQualityReport` (quality_report.py); `LLMBoundary`/`QuantBoundary` (quant_boundary.py); `cli.main` (cli.py) |
| `pit/` (12) | temporal foundation 4.1.0 | `TemporalSemantics` (6-timestamp model); `PublicationControlledAvailability`/`RevisionAwareAvailability`/`AvailabilityPolicy`; `TemporalContract`; `canonical_serialize`; `deterministic_hash`/`identity_hash`/`eligibility_hash` (+ `PROHIBITED_IDENTITY_FIELDS`); `PitSidecar`; `RevisionChain` (append-only, `pit4c.`); `TieBreakerPolicy`; instrument/venue primitives; **`PitViewBuilder.build()`/`PitViewValidator`** (view.py, `pit4v.`); `ExperimentIdentity` (`pit4x.`) |
| `quant/` (13) | indicator engine 2.0.0 | `QuantEngine.calculate()`; `IndicatorRegistry` (15 built-in indicators, module singleton); **`FeaturePipeline.compute()`** (features.py, `feat6.`, slice-then-compute at `as_of`); `QuantDataValidator` (invokes `DataQualityGate`); pure indicator functions (sma/ema/rsi/atr/returns/statistics/drawdown/trend) |
| `strategy/` (11) | **FROZEN Phase 3** | declarative backtest engine: `TradeLedger` (`trade-000001` deterministic ids), `PositionTracker` (FLAT/OPEN), `OrderStatus` PENDING/FILLED/REJECTED/CANCELLED, conditions/schemas/validation/provenance — 11 blobs byte-pinned |
| `research/` (2) | research governance 4.4.0 | `ResearchContract`/`ResearchRegistry` — structural no-self-approval (approver must be HUMAN ≠ submitter), tamper-check-on-read, `res44.`/`appr44.` |
| `research_validation/` (5) | validation 7.0.0 | `BiasDetector`/`LeakageDetector`/`OverfittingDetector`; `StatisticalValidator` (Student-t via Lentz, no scipy); `build_walk_forward_plan`/`WalkForwardValidator` (`wf7.`, overlap unrepresentable); `sweep`/`plateau_analysis`/`robustness_report` (grid cap 10,000) |
| `experiment_registry/` (2) | experiment tracking 5.0.0 | `ExperimentRegistry` — duplicate deterministic identity refused, tamper-check-on-read, `ReproducibilityRun` verdicts (MATCH/UNVERIFIED) |
| `risk/` (3) | hard risk 8.0.0 | `RiskLimits` (5 limits, `risk8.`); `RiskEngine.check_order()`/`check_weights()` (zero-override, breach ⇒ raise + chained violation record + kill-switch trip by default); `trip/reset_kill_switch()`; `ExposureManager.build_report()`; `PortfolioConstructor.allocate()` (inverse-vol, precondition gauntlet) |
| `paper/` (5) | paper trading 11.0.0 | `PaperOrder`/`Fill`/`PaperPosition` (`paper11.`/`fill11.`); `ExecutionRealism`/`ExecutionSimulator` (lag-1, no same-bar fills, participation raise); **`PaperOrderGateway.submit()/cancel()`** (duplicate protection); `ReconciliationEngine.reconcile()` (3-way); `AuditLogger` (chained); `AnalyticsEngine` (P&L/drawdown/Sharpe); `EvaluationFramework` (30-day); `HumanAuthorizationToken`/`HumanAuthorizationRegistry` (human-principal only); `GraduationEvaluator`/`RetirementEvaluator`; **`LiveAuthorizationGate`** (4-condition conjunctive, deny-by-default) |
| `discovery/` (6) | candidate chain 12/15 | `StrategyCandidate` (`disc20.`, embeds frozen `StrategySpec`); `RuleBasedGenerator` (bounded grid ≤64); `CandidateValidator`/`CandidateEvaluator` (NO-TRADE default); `DiscoveryRegistry` (append-only chain); **`ExecutionEligibility`** (7-stage fail-closed chain, `elig20.`, `LIVE_AUTHORIZATION_STATUS="NOT_AUTHORIZED"` hard-coded) |
| `prediction/` (31) | prediction lab PRED | contracts (closed vocabularies: `BlockReason` 14, `RegimeState` 11+UNKNOWN, `ModelLifecycleState` 12, `DriftState` 5, `DatasetState` 5); `prediction_identity` (17 `pred*.` prefixes); provenance (18-field, wall-clock-free); PIT candle views (revision first-arrival-wins); datasets (`preds.`, epistemic states); QG-01..16; source registry (human-only approvals, 5 UNVETTED candidates); labels (boundary proofs); features (6-feature versioned schema); regimes (+transition events `predv.`); 5 baselines + `LogisticCrashModel` + justification gate; calibration (Platt + Brier/log-loss/ECE); uncertainty bands; PSI drift (5-state + §37 actions); evidence score (11-dim); `PredictionModelRegistry` (12-state, AI self-approval structurally rejected); `PredictionOutcomeLedger` (append-only hash chain); gates (fixed-order fail-closed); walk-forward reuse; event evaluation; benchmark protocol (3-mode, PRED-F1); red-team matrix 45/45 (PRED-F2); `CrashRiskEstimator.assess()` (13-stage governed orchestrator); scenarios (never forecasts); systemic (correlation-only); risk_integration (advisory-only, clamped); microstructure (explicit `MICROSTRUCTURE_UNAVAILABLE`) |
| `hermes/` (4) | agent governance 9.0.0 | `AgentContract`/`AgentPermission` (4 structurally-unavailable permissions incl. `live_trading_authority`); `ModelRouter` (**LLM-provider** routing, free-first; naming collision flag for the future `PredictionModelRouter`); `HermesOrchestrator.dispatch()` (audit records only — never executes); `MessageLog`/`SkillDefinition`/`SkillExecutor` |
| `infra/` (2) | observability 10.0.0 | `DeterministicRunner`/`ReproducibilityVerifier` (raise on non-determinism); `MetricsRegistry` (phantom-forbidden, `obs10.` snapshot hash); `StructuredLog` (chained); `HealthCheck`/`AlertManager`/`Monitor.poll()` (pull-based); `CheckpointManager`/`RecoveryManager` (hash-verified restore) |
| `knowledge/` (3) | knowledge/memory | `KnowledgeRecord`/`MemoryRecord` (`know42.`/`mem42.`); `KnowledgeStore` (append-only chain, authoritative-view filtering, HUMAN_DECISION machine-principal refusal); `MemoryStore` (bounded 256, fail-closed overflow) |
| `benchmarks/` (2) | perf benchmarks | `BenchmarkSuite` — 10 real production surfaces incl. `run_paper_trading` (**bypasses `PaperOrderGateway`, calls simulator directly**) and `run_no_trade_capability`; timing-excluded hashes; invoked only by tests |
| `actions/` (5) | corporate actions 4.2.0 | splits/dividends/symbol-change/delisting; `AdjustmentChain`; PIT universes; `TradingCalendar` |
| `derivatives/` (4) | futures 4.3.0 | `FuturesContract`; rollover detection (decision ≤ effective); `ContinuousSeries` (roll-leakage protection) |

**Interface style.** No dependency-injection framework; components are constructed explicitly by callers (tests/benchmarks) with frozen pydantic config objects. Duck-typed bar/candle mappings at the simulator and prediction boundaries. There is no service interface, no abstract OMS/execution-adapter protocol (§18 of the mandate will introduce one), and no typed event model (§5 of the mandate).

---

## 3. Dependency graph (§2 items 3–4 — interfaces and dependencies)

**AST-verified src-internal cross-package imports:**

| Package | Imports (cross-package, beyond root facade) |
|---|---|
| `actions` | pit |
| `benchmarks` | validation, schemas, pit, quant, strategy, risk, paper, hermes, discovery (lazy, in-method) |
| `derivatives` | pit |
| `discovery` | pit, strategy (frozen schemas) |
| `experiment_registry` | pit |
| `hermes` | pit |
| `infra` | pit |
| `knowledge` | pit, research |
| `paper` | pit |
| `prediction` | pit, research_validation, risk (`risk_integration` only) |
| `quant` | data_blocked, pit, schemas, timeframes |
| `research` | pit |
| `research_validation` | pit |
| `risk` | pit |
| `strategy` | data_blocked, quant, schemas |
| root `ingestion.py` | validation, data_blocked, schemas, provider, provenance, quarantine |
| root `cli.py` | quant_boundary (+ facade) |
| root `provider.py` | instruments, schemas, security |
| root `storage.py` | provenance, schemas, security |
| root `quality_report.py` | schemas, validation (lazy) |
| root `schemas.py` | evidence; quality_report + validation lazily inside methods (runtime-mediated cycle) |

**Shared substrate:** `pit.hashing.deterministic_hash` is imported by effectively every package — the identity backbone of the whole platform.

**Critical structural facts:**

1. **`risk` ⇔ `paper`: zero imports in either direction.** The paper order path has no risk-gate or kill-switch wiring (see §10, RT-F1).
2. **`discovery` ⇔ `paper`/`risk`: zero runtime imports** — `ExecutionEligibility.evaluate()` consumes caller-supplied booleans (`risk_valid`, `portfolio_valid`, …) that only tests ever supply.
3. **Six packages are never imported by any other src module** (facade re-export + tests only): `actions`, `derivatives`, `experiment_registry`, `infra`, `knowledge`, `prediction`. Nuance: `hermes`, `paper`, `risk`, `discovery` are cross-imported only by `benchmarks/runner.py`, which is itself invoked only by tests. **There is no production composition root other than the `data_engine/__init__.py` facade re-export and the informational CLI.**
4. **The prediction layer is not downstream of the ingestion chain.** `CrashRiskEstimator.assess()` builds its own PIT view via `prediction/data_access.pit_candle_view()` (timestamp/revision-drop semantics) over duck-typed candles — a deliberate second PIT implementation parallel to `pit/view.py` (sidecar/publication semantics).
5. Two parallel feature pipelines exist: `quant/features.py` (registry-driven, `feat6.`) and `prediction/features.py` (fixed 6-feature schema, `predf.`) — duck-typed peers by design (see §11).

---

## 4. Runtime graph (§2 items 6–8 — unconnected components, test-only components, missing runtime orchestration)

**Every way the system can be started:**

| # | Entry point | Evidence | What it does |
|---|---|---|---|
| 1 | Console script `data-engine` | `pyproject.toml:17-18` → `data_engine.cli:main` | 5 subcommands: `validate`, `report`, `storage-report`, `status` (all print-only informational no-ops) and `check-boundary` (inverted — raises `LLMBoundaryViolation` for every valid deterministic calculation type and exits 1; success branch unreachable; verified by execution this cycle) |
| 2 | `python src/data_engine/cli.py` | `cli.py:82-83` | same as above |
| 3 | `python -m data_engine` | **NOT POSSIBLE** — no `__main__.py` in the repo | — |
| 4 | **pytest (the de-facto runtime)** | 35 test files / 1059 tests | The only mechanism that constructs and exercises every subsystem end-to-end |
| 5 | Library import `import data_engine` | `__init__.py` facade | eagerly re-exports all 30 packages (no behavior) |
| 6 | External gate scripts | `/home/z/my-project/scripts/*.py` (outside the repo) | `final_gate_verify.py`, `security_scan.py`, `mutation_gate.py`, … — operator-side verification, not system startup |

**Runtime-loop scan of all of `src/` (exhaustive):** `while True` → 1 hit, a bounded plan-builder loop with `break` (`research_validation/walk_forward.py:110`); `while <cond>` → 1 bounded day-counting loop (`actions/calendar.py:199`); `threading` → 1 mutex around the in-memory store (`storage.py:76`), **no thread ever started**; `asyncio`/`sched`/`Timer`/`cron`/`APScheduler`/`time.sleep`/`subprocess`/`multiprocessing` → **0 hits**. There is **no continuously-running component, scheduler, daemon, event loop, or background thread anywhere in `src/`.**

**Missing runtime orchestration (the mandate’s core gap):** no `TradingRuntime` (§3 of the mandate: initialize/start/stop/recover/health), no dependency-injection composition root (§4), no typed event model / event bus (§5), no market-data loop (§6), no autonomous supervisor or loop (§42), no scheduling (§45), no persistent state / restart recovery (§46/§47). The word “orchestrator” in the repo (`HermesOrchestrator`) denotes a dispatch-record data structure: `dispatch()` checks permissions, appends an audit entry, executes nothing.

---

## 5. Execution graph (paper trading as-is)

**The only execution path that exists (library/tests):**

```text
PaperOrder(models.py)                        # construction-validated, order_hash "paper11."
  → PaperOrderGateway(ExecutionSimulator(realism)).submit(order, bars)
      ├─ duplicate client_order_id → GatewayError (in-memory dict)   [idempotency: process-lifetime only]
      ├─ ExecutionSimulator.simulate(order, bars)                    [simulator.py:108-163]
      │    ├─ fill_lag_bars ≥ 1 enforced — NO same-bar fills
      │    ├─ MARKET fills at open of lag bar; LIMIT only on the lag bar, at the limit price
      │    ├─ costs: half-spread (adverse) + linear impact (qty/volume) + commission per unit
      │    ├─ participation breach (qty > cap × volume) → SimulationError (raise, not partial fill)
      │    └─ window past data end → None (order stays SUBMITTED, forever — no TTL/expiry sweep)
      ├─ SimulationError → record stored REJECTED, then GatewayError raised
      └─ Fill → GatewayRecord (status FILLED; fill_id = "{client_order_id}-F{idx}" deterministic)
  → cancel(): only SUBMITTED → CANCELLED
Post-hoc, standalone, NEVER invoked by the gateway or any src module:
  ├─ ReconciliationEngine.reconcile(orders, fills, positions)   [3-way, replay-from-zero, fail-closed raise]
  ├─ AuditLogger.log(event, payload)                            [hash-chained, arbitrary event vocabulary]
  └─ AnalyticsEngine.summarize(...)                             [P&L / max-drawdown / Sharpe]
```

**Order-status vocabulary (exact):** `OrderStatus = {SUBMITTED, FILLED, CANCELLED, REJECTED}` (`paper/models.py:51-55`); side `buy|sell`; type `market|limit`; single-fill model (multiple fills per order = reconciliation violation). **No PARTIAL status, no amend/modify, no expiry.**

**Divergence with frozen Phase 3:** `strategy/schemas.py:60-65` uses uppercase `{PENDING, FILLED, REJECTED, CANCELLED}` with `PENDING` (not `SUBMITTED`); `OrderSide` is `LONG/SHORT` (not `buy/sell`); quantities are `float` (paper uses `Decimal`). No bridge exists between the two order/position representations (RT-F6).

**What is NOT in the execution path (all verified by import analysis):** the `RiskEngine` (no risk-gate check before submit — RT-F1), the kill switch (not consulted — RT-F1), the `AuditLogger` (never invoked — RT-F3), the `ReconciliationEngine` (zero src callers — RT-F2), the evaluation/graduation machinery (`paper/evaluation.py` is imported by nothing inside `paper/`), and any persistence (all state in-memory — RT-F4). The benchmarks' `run_paper_trading` additionally **bypasses the gateway entirely** and calls `simulator.simulate()` directly (RT-F12).

**Broker adapters / live execution (§2 items 17–18):** verified absent. Repo-wide grep for broker/MT5/ccxt/alpaca/oanda/FIX/order-router/websocket/requests/urllib/httpx/aiohttp/api_key patterns in `src/` matches only docstring denials (“NO REAL MONEY. NO BROKER CREDENTIALS”). There is no network I/O anywhere in `src`. **Paper/live separation today = PAPER-only by total absence of live machinery** + the deny-by-default `LiveAuthorizationGate` (4 conjunctive conditions: verified human token purpose `live_boundary` AND complete 30-day evaluation AND `graduated=True` AND `production_infra_attested=True`; `default_decision()` = pure DENIAL; registry starts empty so machine/self-issued authorization is structurally impossible). **SHADOW and CANARY modes do not exist anywhere in `src/`** (grep-verified) — they must be built (PHASE AC/AE).

---

## 6. Ownership tables (§2 content items 5–11)

| Ownership domain | Authoritative owner today | Notes / gaps for the runtime |
|---|---|---|
| **State** | No single owner. Per-component in-memory state: gateway records dict (`gateway.py:62`), risk violation log + kill-switch flag (`engine.py:158-159`), quarantine store, provenance versions, blocked-datasets registry, registries (prediction model / discovery / research / experiment / data-source), knowledge/memory stores, metrics/log/checkpoint stores | **No persistent state; no state owner.** A restart wipes everything, including a tripped kill switch (RT-F4). Mandate §43/§46 (persistent storage, restart recovery) will introduce the authoritative state store |
| **Data** | `DataStorage` (3 in-memory tiers, `storage.py`) + `DataIngester._raw_store` + PIT view objects; content identity via `dataset_content_hash`/`preds.` manifests | `DataStorage.store_*` are never called by any src module; the dir `./data_engine_storage` is created but **no file is ever written**; the prediction layer holds its own duck-typed candles |
| **Model** | `PredictionModelRegistry` (in-memory records, 12-state lifecycle, human-only approvals) + `ModelArtifact` hashes recomputed by `artifact_verification.py` | **No model loader/reconstruction:** models are code + in-process fitted state; a fresh process must re-run `fit()`; there is no artifact→model path (RT-F14). 0 approved models registered |
| **Memory** | `knowledge/` (`KnowledgeStore` + bounded `MemoryStore`), both in-memory | No episodic/market/model/experiment/failure/incident memory split (mandate §29–§36); no persistence |
| **Ledger** | `PredictionOutcomeLedger` (append-only hash chain) + 10 further domain chains (see §9.3) | **No runtime order/fill/position/trade/P&L ledgers** — the 5 execution ledgers of mandate §22/§23/§24/§25/§26 do not exist as persistent ledgers; today's order/fill records live in the volatile gateway dict |
| **Order** | `PaperOrderGateway` (submit/cancel/record; duplicate protection; 4-state lifecycle) | Process-lifetime only; not risk-gated; no OMS state machine beyond 4 states; no idempotency-key framework across restarts |
| **Portfolio** | `PaperPosition.apply_fill` (average-cost, cost-adjusted basis) for paper; frozen Phase 3 `PositionTracker` (backtest domain); `PortfolioConstructor` (inverse-vol weights) | Two disjoint position representations (paper vs frozen strategy) with no bridge (RT-F6); no portfolio state service, no exposure monitoring loop |

---

## 7. Current mechanisms (§2 items 9–19)

### 7.1 Model loading (§2 item 9)
There is **no runtime model-loading service and no deserialization loader**. Loading = registry (metadata) + artifact (hash verification) only. Models are plain Python classes with the duck-typed `fit`/`predict_proba`/`model_hash` contract; training is deterministic GD; standardization stats are train-only and enter the artifact hash. `verify_model_artifact` recomputes hashes from the live artifact (never trusts declared values), checks JSON round-trip integrity, schema/feature-arity, expected-hash, and dataset-id compatibility; models without `artifact()` fail closed. The estimator invokes both artifact and input-snapshot verification inside `assess()`. **Re-instantiating a model in a fresh process requires re-running `fit()`** — no `from_artifact`/reconstruction path exists (RT-F14). Grep-verified: no pickle/joblib/torch.load/sklearn anywhere.

### 7.2 Persistence / state (§2 item 10)
**Everything is in-memory; there are no databases** (grep for sqlite/duckdb/sqlalchemy/postgres/redis → 0 real hits). The only two disk writers in `src/`: (1) `SecurityConfig.audit_log` → appends unchained JSONL to `src/audit.log` (a git-tracked file — ARCH-F11; the method has no current caller); (2) `SecurityAuditTrail` → append-only hash-chained JSONL to a caller-configured path (only when `ProviderConfig.audit_trail_path` is set; wired in `provider.py`). `DataStorage` creates `./data_engine_storage` but never writes files. **Consequence: no state survives a process restart — order state, duplicate-protection memory, audit chains, violation logs, human tokens, and the tripped kill switch are all volatile** (RT-F4).

### 7.3 Configuration (§2 item 11)
No `pydantic-settings`/BaseSettings, no YAML/TOML config files, no env-var app configuration (env vars are used **only for secrets**, `$ENV:`-placeholder-enforced). Three patterns: (1) frozen pydantic config models passed explicitly (`ProviderConfig` FS-04/06/14/17/18; `EstimatorConfig`; `RiskThresholds`; `PitExperimentConfig`; `TemporalContract`; `AvailabilityPolicy`; `ExecutionRealism`); (2) frozen dataclass specs (`IndicatorSpec`); (3) hardcoded documented module constants (regime thresholds, §39 history policy, timeframe tables, gate defaults). A runtime will need a single authoritative configuration composition (mandate §21 paper/live configuration isolation).

### 7.4 Logging / observability (§2 item 12)
The `logging` module is used **nowhere** in `src/`; output is `print()` confined to the CLI (plus one red-team summary print). The observability idiom is **hash-chained audit records instead of logs**: `SecurityAuditTrail`, `PredictionOutcomeLedger`, `RevisionChain`, `infra.StructuredLog`, `KnowledgeStore` chain, gateway `AuditLogger`, risk violation chain, discovery registry chain, hermes audit chain, experiment registry hash-checks — 11 chained stores in total (§9.3). `infra/` adds `MetricsRegistry` (phantom-forbidden, snapshot hash), `HealthCheck`/`AlertManager`/`Monitor.poll()` (pull-based, on-demand), `CheckpointManager`/`RecoveryManager` (in-memory, hash-verified restore). **No structured application logging, no log levels, no log files beyond the stray `src/audit.log`.**

### 7.5 Execution simulator (§2 item 13)
Deterministic, single-fill, lag-1 (no same-bar fills by validator-enforced construction), duck-typed bars; costs = adverse half-spread + linear market impact + per-unit commission, full decomposition recorded per fill; participation breach **raises** rather than partially filling (“a paper fill that real markets could not execute is a realism failure”); no RNG, no clock, no environment reads; `realism_hash` pins the parameter set. Realism defaults exist only in benchmarks. **No partial fills, no regime-conditioned dynamics, no multi-venue behavior** (BLK-10).

### 7.6 OMS (§2 item 14)
`PaperOrderGateway` is a minimal in-memory OMS: duplicate `client_order_id` protection, submit/cancel/record surface, 4-state lifecycle, single-fill invariant, rejection paths (construction validation; realism gate; gateway contract). **No amend, no order expiry/TTL sweep, no persistent order store, no idempotency across restarts, no 19-state order lifecycle** (mandate §15/§16 will define the real OMS). Live OMS is absent by design.

### 7.7 Reconciliation (§2 item 15)
`ReconciliationEngine.reconcile(orders, fills, positions)`: three authorities = order records, fill records, stated position state. Checks: orphan fills; single-fill invariant; **replay-from-zero** — fills sorted by `(filled_at, fill_id)` re-applied through `PaperPosition.apply_fill` must reproduce stated positions exactly (quantity + realized P&L). Any mismatch raises `ReconciliationError` (fail-closed, “never papered over”). **Zero src callers** — it is a standalone engine; “reconciliation failure blocks new orders” (mandate §28) is caller-enforced only, and no production caller exists (RT-F2).

### 7.8 Kill switches (§2 item 16)
`RiskEngine` kill switch: `_guard()` raises `KillSwitchActiveError` at the top of `check_order`/`check_weights` — all order-size/weight/leverage/heat evaluation refuses while tripped; indirectly blocks `PortfolioConstructor.allocate()`. Breaches raise (zero-override), record hash-chained violations, and trip the switch by default (`trip_on_breach=True`). **Gaps:** `reset_kill_switch()` is unauthenticated (ARCH-F1, verified at `risk/engine.py:174-176`) and emits **no audit record on trip or reset** (RT-F5); the switch is volatile (RT-F4); it does not guard `ExposureManager.build_report` (RT-F9); and it is **not consulted by the paper gateway at all** (RT-F1); the only in-repo caller of the reset is a test.

### 7.9 Broker adapters (§2 item 17)
**Absent — verified.** No network code, no credentials surface, no account model, no order routing anywhere in `src/` (grep across broker/MT5/ccxt/alpaca/oanda/FIX/websocket/requests/api_key patterns → docstring denials only). The execution-adapter interface (mandate §18) does not exist yet.

### 7.10 Paper/live separation (§2 item 18)
PAPER exists (simulator + gateway). SHADOW: absent. CANARY: absent. LIVE: structurally denied — `LiveAuthorizationGate` deny-by-default with 4 conjunctive conditions; discovery layer hard-codes `LIVE_AUTHORIZATION_STATUS="NOT_AUTHORIZED"`; Hermes structurally rejects `live_trading_authority` permission; prediction registry requires human tokens for PAPER/GRADUATE. Mode separation as a first-class runtime concept (mandate §1, §21) does not exist — today separation is by total absence of non-paper machinery.

### 7.11 Event/message mechanisms (§2 item 19)
**None.** No event bus, pub-sub, message queue, broker, observer pattern, queue, asyncio, or dispatch mechanism anywhere in `src/` (grep-verified; the only threading primitive is a storage mutex; the only `publish`/`subscribe` hits are docstring prose). “Events” in this codebase are **hash-addressed immutable records**, not messages: `RegimeTransitionEvent` (`predv.`) is produced (returned as a tuple) — nothing subscribes to it; audit-chain entries are appended and later re-derived by explicit polling (`ledger.verify()`, `SecurityAuditTrail.decisions()`), never pushed. The mandate's typed event model (§5: `MarketDataReceived` → … → `KILL_SWITCH_TRIGGERED`) must be built from scratch (PHASE C).

---

## 8. TODO / STUB / NOT_IMPLEMENTED register (§2 item 20)

**Zero keyword markers** (`TODO`/`FIXME`/`XXX`/`STUB`/`NOT_IMPLEMENTED`/`raise NotImplementedError`) across all of `src/` — every method has a real body. The functional stubs and dead paths that DO exist, by behavior:

| # | Location | Nature |
|---|---|---|
| S-1 | `quant_boundary.py:153-158` | `QuantBoundary.request_calculation` returns `DeterministicResult(result=None)` — “In a full implementation, this would call the actual deterministic calculation module. For Phase 1, we validate the boundary is respected.” A functional stub |
| S-2 | `cli.py:47-78` | All 5 CLI subcommands are informational shells; `check-boundary` is inverted (RT-F7 — verified exit 1) |
| S-3 | `ingestion.py:195-216` | `ingest_from_file` is a dead path: builds `ProviderConfig` without `approved_data_root` → FS-06 fail-closed before any read; ARCH-F3 NameError would fire later (RT-F8) |
| S-4 | `storage.py:215-216` | `verify_raw_immutability` comment: “In a production system, this would check file checksums” — in-memory contract only |
| S-5 | `storage.py:183` | `try_overwrite_raw()` always returns False (immutability by refusal) |
| S-6 | `paper/gateway.py:6` | Docstring advertises a `PnLCalculator` class that does not exist (functionality lives in `AnalyticsEngine`) — RT-F11 |

Deliberate sentinel values (NOT stubs — they are adversarially *detected* failure conditions): `placeholder_id="pred.PENDING"` in the estimator's refused-assessment path; `_DATASET_PLACEHOLDERS={"", "DS-UNRECORDED", "UNRECORDED"}` in artifact verification; `MICROSTRUCTURE_UNAVAILABLE`.

---

## 9. Memory, ledgers, tracking, attribution, audit stores, databases, dashboards, replay, incident/recovery (§2 items 21–29)

### 9.1 Memory / state systems (§2 item 21)
`knowledge/`: five record types (FACT/OBSERVATION/HYPOTHESIS/MODEL_OUTPUT/HUMAN_DECISION); structural authoritative-source filtering (FACT + HUMAN_DECISION authoritative; MODEL_OUTPUT only with validation ref; machine principals cannot author HUMAN_DECISION); content-addressed `know42.`/`mem42.` identities (wall-clock-free by `PROHIBITED_IDENTITY_FIELDS` scan); `KnowledgeStore` append-only chained; `MemoryStore` bounded at 256 records — overflow fails closed rather than silently truncating. **Both in-memory**; no episodic/market/model/experiment/failure/incident memory split (mandate §29–§36); no linkage to autonomous research. `infra.CheckpointManager` provides hash-verified in-run state snapshots only.

### 9.2 Trade/order/fill ledgers (§2 item 22)
What exists: `PredictionOutcomeLedger` (append-only, hash-chained, `GENESIS_HASH="0"*64`, no mutation/deletion API, `verify()` recomputes the full chain, `summary()` Brier/hit-rate over known outcomes — in-memory); frozen Phase-3 `TradeLedger` (backtest domain, deterministic `trade-000001` ids); paper `GatewayRecord`s + `Fill` records (volatile gateway dict); risk `ViolationRecord` chain. **What does not exist:** the runtime order ledger, fill ledger, position ledger, trade ledger, and P&L ledger as persistent append-only stores (mandate §16/§22–§26) — none of today's execution records survive a restart or carry cross-subsystem lineage.

### 9.3 Audit / event stores (§2 item 25) — the 11 hash-chained stores
(1) hermes orchestration audit; (2) hermes message log; (3) infra structured log; (4) knowledge chain (`kchain42.`); (5) memory chain (`mchain42.`); (6) discovery registry chain (genesis `"genesis"`); (7) security audit trail (genesis `"GENESIS"`, optional JSONL file); (8) paper `AuditLogger` (never invoked — RT-F3); (9) prediction outcome ledger; (10) risk violation chain; (11) PIT revision chain (`pit4c.`). Plus hash-verified-on-read (not chained): research registry, experiment registry. **All in-memory except the optional security trail file. No unified cross-subsystem lineage DAG exists** (status-doc §17; mandate §49).

### 9.4 Experiment tracking (§2 item 23)
`experiment_registry/`: entries keyed by `pit4x.` experiment identity; duplicate deterministic identity refused; **tamper-check-on-read** (`get()` recomputes `entry_hash` and raises on mismatch); `ReproducibilityRun` verdicts (MATCH iff observed==expected hash; default UNVERIFIED, never assumed); immutable reproducibility logs. Complemented by `infra.DeterministicRunner`/`ReproducibilityVerifier` (re-executes callables N times, raises on non-determinism).

### 9.5 Model-performance attribution (§2 item 24)
Prediction-side attribution exists and is governed: benchmark protocol (3-mode: empirical REAL_VERIFIED-only / contract-verification stamped SYNTHETIC / blocked), calibration metrics (Brier/log-loss/ECE/reliability), drift summaries, refusal analysis, event evaluation (detection/lead-time/FPR, regime-conditioned). Benchmarks suite measures component throughput (timing-excluded hashes) + NO-TRADE capability. **No prediction→decision→order→fill→P&L attribution linking exists** (mandate §37/§38) — the decision and execution legs do not exist yet.

### 9.6 Databases / persistence layers (§2 item 26)
**None.** No sqlite/duckdb/sqlalchemy/redis anywhere; the entire persistence surface is: one empty storage directory, one stray unchained `src/audit.log`, and one optional hash-chained security JSONL. Mandate §43 (persistent storage) starts from zero.

### 9.7 Dashboards / reporting (§2 item 27)
**None.** No matplotlib/jinja/plotly/HTML generation anywhere in `src/`; all “reports” are pydantic model objects consumed programmatically (or the ~90 hand/machine-authored root-level governance `.md` documents).

### 9.8 Replay systems (§2 item 28)
(1) `ReconciliationEngine` — genuine event replay: fills replayed from zero must reproduce positions exactly; (2) `DeterministicRunner` — re-execution with hash comparison; (3) artifact/input-snapshot verification — independent recomputation; (4) PIT view validation — availability re-derivation; (5) recorded reproducibility verdicts. **No market-data replay service, no end-to-end digital-twin replay, no deterministic-replay-of-history machinery** (mandate §56/§57).

### 9.9 Incident / recovery systems (§2 item 29)
`infra.CheckpointManager` (immutable snapshots, verify-before-restore) + `RecoveryManager` (hash-verified restore wrapper) — **in-memory only**. `AlertManager`/`Monitor` (pull-based). **No incident record schema, no incident-response pipeline (DEGRADE → STOP ORDERS → RECONCILE → ALERT → PRESERVE → WAIT), no restart/crash recovery logic** (grep for restart → 0 real hits). Mandate §47/§54 + incident memory (§35) start from zero.

---

## 10. Missing connections (the integration gap register)

Ordered by safety consequence:

| # | Missing connection | Consequence for the mandate |
|---|---|---|
| MC-1 | **`RiskEngine`/kill switch → `PaperOrderGateway`** (zero imports either direction) | The HARD RISK GATE stage (§13) has no insertion point today; paper orders execute with zero risk enforcement. The runtime must inject `check_order` before submit and consult the kill switch in the decision loop |
| MC-2 | **`ReconciliationEngine` → order path** (zero src callers) | §28's “failed reconciliation stops new orders” is unenforced; the runtime must wire reconcile-after-execution with a blocking verdict |
| MC-3 | **`AuditLogger` → gateway/runtime** (never invoked) | No execution audit trail is produced; the runtime must emit the typed event stream (§5) into a chained store |
| MC-4 | **`paper/evaluation.py` gates → anything** (imported by nothing in `paper/`) | Graduation/live-boundary gates are dormant; supervisor must consult them at the PAPER_TRADING_READINESS gate (§50) |
| MC-5 | **`discovery.ExecutionEligibility` booleans → risk/portfolio engines** | The 7-stage fail-closed chain consumes caller-supplied `risk_valid`/`portfolio_valid` that only tests supply |
| MC-6 | **`DataIngester.ingest()` → callers** (zero in src or tests) | The entire ingestion chain (provider→validate→quarantine→dataset) is never executed outside its own unit tests; the market-data service (§6) must drive it |
| MC-7 | **`DataStorage.store_*` → callers** | Storage tiers are never used; the persistence layer (§43) must become the authoritative state owner |
| MC-8 | **prediction layer → ingestion/PIT-view chain** | The estimator consumes duck-typed candles via its own PIT slice — the runtime must route governed datasets into it (via adapter, not by modifying frozen/PIT modules) |
| MC-9 | **`PredictionOutcomeLedger.append()` → runtime driver** | Outcome records are caller-driven only; no evaluation loop appends real outcomes |
| MC-10 | **6 orphan packages (`actions`, `derivatives`, `experiment_registry`, `infra`, `knowledge`, `prediction`) → composition root** | No non-facade, non-test consumer exists; the `TradingRuntime` (§3) is their first production consumer |
| MC-11 | **CLI → real operations** | 4 no-op subcommands + 1 inverted; no runtime control surface (start/stop/health per §3) |
| MC-12 | **paper order vocabulary ⇄ frozen strategy vocabulary** | Two disjoint order/position representations with no bridge (RT-F6); the TradePlan/decision stages must define the authoritative translation |

---

## 11. Duplicate systems + parallel implementations (§2 item 5)

**Zero true duplicate systems** — re-verified this cycle by enumerating every registry/engine/store/ledger/router/orchestrator class (8 registries, 7 engines, all domain-distinct; full table in `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` §10). The runtime mandate must preserve this: **new runtime components EXTEND existing ones; no parallel OMS, no parallel risk gate, no parallel ledger concept** (RL policies enter the SAME 12-state `PredictionModelRegistry`).

**Parallel implementations (deliberate peers, unification flags for the runtime):**

| # | Pair | Nature | Runtime decision required |
|---|---|---|---|
| P-1 | `pit/view.py` (sidecar/publication semantics) vs `prediction/data_access.py` (timestamp/revision-drop semantics) | Two PIT slicing implementations | The market-data service (§6) should own ONE governed view path; prediction keeps its internal slice only behind an adapter, or consumes the runtime view |
| P-2 | `quant/features.py` (`feat6.`, registry-driven) vs `prediction/features.py` (`predf.`, fixed 6-feature schema) | Two feature pipelines | Feature store unification (already registered in the expansion mandate) |
| P-3 | paper `OrderStatus`/`OrderSide`/Decimal vs frozen strategy `OrderStatus`/`OrderSide`/float | Two order/position vocabularies | The runtime's ORDER_LIFECYCLE_SPEC must define the authoritative vocabulary + an explicit bridge to the frozen engine (adapter, zero frozen-file contact) |
| P-4 | Hermes `ModelRouter` (LLM-provider routing) vs the future prediction-model router | Naming collision only | New component named `PredictionModelRouter` (registered decision) |

---

## 12. Runtime finding register (new this cycle) + carried findings

**New runtime findings (RT-F), all verified first-hand this cycle:**

| ID | Finding | Severity | Evidence |
|---|---|---|---|
| RT-F1 | **Hard risk gate + kill switch are NOT wired into the paper order path** — `paper/gateway.py` imports no risk module; `submit()` performs no `check_order`/kill-switch consult | HIGH (safety wiring) | gateway imports `gateway.py:15-29`; zero `risk` ⇄ `paper` imports |
| RT-F2 | **`ReconciliationEngine` has zero src callers** — reconciliation never runs in any production path; “failure blocks new orders” unenforced | HIGH (safety wiring) | grep: definitions + facade re-exports only |
| RT-F3 | **`AuditLogger` never invoked by the gateway** — the advertised immutable execution audit trail is dead wiring | HIGH (auditability) | grep: class def + `__init__` re-export only |
| RT-F4 | **No persistence in the execution domain** — order state, duplicate protection, audit chains, violation logs, human tokens, and the tripped kill switch are all volatile; kill switch does not survive restart | HIGH (runtime) | exhaustive write-grep over `paper/`,`risk/`,`discovery/` → 0 hits |
| RT-F5 | **Kill-switch trip/reset emit no audit record** (extends ARCH-F1: reset unauthenticated) | MEDIUM | `engine.py:170-176` (no `_record` call) |
| RT-F6 | **Two disjoint order/position vocabularies** (paper lowercase/`buy|sell`/Decimal vs frozen strategy uppercase/`LONG|SHORT`/float) with no bridge | MEDIUM (integration) | `paper/models.py:41-55` vs `strategy/schemas.py:54-65` |
| RT-F7 | **CLI `check-boundary` is inverted** — raises for every valid deterministic calculation type; always exits 1; success branch unreachable | LOW (verified by execution) | `cli.py:67-79`; empirical exit=1 |
| RT-F8 | **`ingest_from_file` is a dead path** — no `approved_data_root` ⇒ FS-06 fail-closed before any read; ARCH-F3 NameError would fire later; plus double validation per ingest | MEDIUM | `ingestion.py:195-216`, `provider.py:192-199`, `validation.py:255-257` |
| RT-F9 | Kill switch does not guard `ExposureManager.build_report`; report lists breaches without raising | LOW | `engine.py:299-347` (no `_guard()`) |
| RT-F10 | **No SUBMITTED-order expiry/TTL sweep; limit fills checked only on the single lag bar** — runtime semantics to redefine | MEDIUM (spec) | `gateway.py:85`, `simulator.py:156-163` |
| RT-F11 | Docstring drift: `PnLCalculator` advertised, does not exist | LOW | `gateway.py:6` |
| RT-F12 | Benchmarks' paper-trading workload bypasses `PaperOrderGateway` (simulator only) | LOW | `benchmarks/runner.py:479-498` |
| RT-F13 | Hygiene: `pytest` is a runtime dependency (not dev-only); stray tracked `src/audit.log`; `.gitignore` misses `.pytest_cache`/`test_storage*` | LOW | `pyproject.toml:7-12`, `.gitignore` |
| RT-F14 | **No model-loading/reconstruction path** — models are code + in-process fit state; fresh process must re-`fit()`; no artifact→model loader | MEDIUM (architecture) | §7.1; grep pickle/joblib/torch.load → 0 |
| RT-F15 | `QuantBoundary.request_calculation` functional stub (returns `result=None`) | LOW (known, Phase-1 scope) | `quant_boundary.py:153-158` |

**Carried findings — statuses re-verified this cycle:** ARCH-F1 (kill-switch reset unauthenticated — CONFIRMED at `risk/engine.py:174-176`), ARCH-F2 (violation chain lacks `verify()`), ARCH-F3 (`ingestion.py:191` `EvidenceProvenance` never imported — CONFIRMED), ARCH-F4 (`quant_boundary.py:118/:175` `datetime`/`UTC` never imported — CONFIRMED **by execution**: `NameError: name 'datetime' is not defined`), ARCH-F5 (calibration Optional import lint), ARCH-F6 (dormant `_compute_raw_hash` uses wall-clock-contaminated `Candle.to_hash()`, F-04/H-1), ARCH-F7 (regime events reuse `predv.` prefix), ARCH-F8/F12 (purge/embargo not sequence-scaled), ARCH-F9 (dormant `OrderStatus` enum), ARCH-F10 (provider silently skips malformed CSV rows), ARCH-F11 (`src/audit.log` tracked). All remain in the **authorized-fix-window** state (source changes require the operator's fix-window authorization; see §16).

---

## 13. Blockers (runtime-integration lens)

The standing blocker register **BLK-1..BLK-15 + FROZEN-GUARD** (real data / sequence layer / NN infra / CI / H-1 / ADVANCED_ML / refusal states / unsafe findings / purge scaling / simulator realism / competition arena / supervisor machinery / autonomous infrastructure / learning loop / approval owners) remains authoritative in `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` §12 — unchanged by this audit. For the runtime mandate specifically, the operative blockers are:

| ID | Runtime blocker | Type |
|---|---|---|
| RT-BLK-1 | No event model / event bus (PHASE C prerequisite for everything event-driven) | architecture |
| RT-BLK-2 | No `TradingRuntime` composition root / DI wiring (PHASE D) | architecture |
| RT-BLK-3 | No persistent state store — all ledgers/registries/kill-switch state volatile (PHASE W prerequisite for restart recovery, idempotency, ledger durability) | architecture |
| RT-BLK-4 | Safety wiring gaps MC-1..MC-4 (risk gate, reconciliation, audit logger, evaluation gates not in the order path) | architecture (fixes via PHASE L/T wiring + fix window) |
| RT-BLK-5 | WP-12 CI absent — no per-commit determinism/frozen/secret gate | human decision |
| RT-BLK-6 | Authorized fix window pending for ARCH-F1/F3/F4/F6 + RT-F7/F8 (runtime phases must not build on known-defective dormant paths) | human decision |
| RT-BLK-7 | Real data source approval (BLK-1) — a paper runtime can run on synthetic contract data, but any performance claim cannot | human decision |
| FROZEN-GUARD | Any plan touching frozen Phase 3 / PIT identity semantics / H-1 boundary / NO-TRADE semantics / risk controls / provenance / PRED evidence = BLOCKER | governance (standing) |

---

## 14. Tests (§2 content item: tests)

**1059 / 1059 passed** — fresh run this cycle (17.54 s), deterministic, cache-disabled. 35 test files; largest suites: `test_quant.py` 134, `test_pit_view.py` 103, `test_pit.py` 92, `test_strategy.py` 82, `test_data_engine.py` 63, `test_redteam.py` 50, prediction suites 126+144 across 15 files (full per-file inventory: `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` §13). Standing evidence: mutation gate 15/15; cross-process identity probes; prediction red-team matrix 45/45 defended with deterministic hash. **The test pyramid gap for the runtime mandate:** no event-bus tests, no runtime lifecycle tests, no restart/recovery tests, no failure-injection tests (§54), no end-to-end replay tests (§56) — these arrive with their phases. Note: pytest is currently a **runtime** dependency (RT-F13) — the runtime era should move it to dev extras once real entry points exist.

---

## 15. Current execution modes / persistence / memory / ledgers (§2 content items 16–19, summary)

| Dimension | Current state |
|---|---|
| Execution modes | **PAPER only** (simulator + gateway, library-invoked). SHADOW: absent. CANARY: absent. LIVE: structurally denied (`LiveAuthorizationGate` deny-by-default, 4 conjunctive conditions, human-token only; Hermes permission structurally unavailable; discovery hard-codes NOT_AUTHORIZED) |
| Persistence | **Effectively none.** All state in-memory; two disk writers (one dead + one optional); no databases; empty storage directory; restart wipes everything |
| Memory | `KnowledgeStore` + bounded `MemoryStore` (in-memory, chained, provenance-aware); no runtime memory subsystem, no episodic/failure/incident memory |
| Ledgers | `PredictionOutcomeLedger` (append-only chain) + 10 further domain chains — all in-memory; **no persistent order/fill/position/trade/P&L ledgers** |

---

## 16. Exact implementation order (mapped to repository reality)

The mandate's PHASE A–AF (§60) mapped to this audit's findings. Phases proceed strictly in order; no phase starts while its dependency is NO; LIVE is never jumped to.

| Phase | Mandate scope | Repo reality after this audit | Prerequisite |
|---|---|---|---|
| **A** | Repository audit + runtime architecture | **COMPLETE — this document** | — |
| **B** | Dependency graph + interfaces | Design/spec work: runtime interface contracts (execution-adapter protocol, ledger interfaces, event envelope), the P-1..P-4 unification decisions, MC-1..MC-12 wiring plan | A (done) |
| **C** | Event model + event bus | Build typed event model (§5 vocabulary) + in-process auditable bus; every runtime component emits through it | B |
| **D** | `TradingRuntime` | The composition root: DI construction of the full §4 graph; start/stop/recover/health; exactly one authoritative orchestration path | C |
| **E** | Market data service | Drive `DataIngester`/PIT views through the bus (MC-6/MC-7/MC-8); staleness policy; source failover behind the existing source registry | D |
| **F–G** | Prediction orchestration + Prediction Ledger | Route governed datasets into the estimator via adapter; runtime-driven `PredictionOutcomeLedger` appends (MC-9) | D, E |
| **H–I** | Decision engine + Decision Ledger | NEW component (today absent); NO-TRADE-first; every decision + WHY-NOT recorded | F |
| **J–K** | Portfolio + position sizing; TradePlan | Extend `PortfolioConstructor`/`PaperPosition`; sizing clamped by `RiskLimits` (reuse `risk_integration` pattern) | H |
| **L** | Pre-trade risk gate | **Wire `RiskEngine.check_order` + kill switch into the order path (MC-1)** — the existing engine becomes the gate; no new risk engine | J |
| **M–N** | OMS + order state machine; Order Ledger | Extend `PaperOrderGateway` to the mandated lifecycle + persistent order ledger; vocabulary bridge P-3 (RT-F6) | L |
| **O–S** | Paper execution adapter; Fill/Position/Trade/P&L Ledgers | Adapter over `ExecutionSimulator` (§18 interface); five append-only ledgers on the new persistence layer | M, PHASE W persistence design |
| **T** | Reconciliation | Wire `ReconciliationEngine` into the post-execution path with blocking verdict (MC-2) | O–S |
| **U** | Memory subsystem | Extend `knowledge/` stores + persistence; episodic/failure/incident memory schemas | W |
| **V** | Performance attribution | Decision-to-outcome + prediction-to-P&L linking (§37/§38) | I, S |
| **W** | Persistence + restart recovery | The persistent state store (all ledgers/registries/kill-switch state); idempotency keys; restart recovery | C (bus), design from B |
| **X** | Kill switches | Harden: authenticated reset (ARCH-F1), audit on trip/reset (RT-F5), persistence (RT-F4), gateway wiring (already L) | L, W |
| **Y** | Observability + audit | Extend `infra/` + the event stream into the complete audit trail (MC-3) | C, W |
| **Z** | Failure injection | Chaos harness over the runtime (§54) | D+ |
| **AA** | End-to-end replay | Deterministic digital-twin replay (§56) | W, ledgers |
| **AB** | Paper trading activation | PAPER_TRADING_READINESS gate (§50) consulting the evaluation/graduation machinery (MC-4) | A–Y |
| **AC** | Shadow-live infrastructure | NEW (absent today) — orders mirrored, never sent | AB |
| **AD** | Broker sandbox integration | NEW — broker adapter behind the §18 interface; credentials via env-only policy | AC |
| **AE** | Canary infrastructure | NEW | AD |
| **AF** | LIVE adapter behind explicit authorization gate | **NEVER without explicit external human authorization**; existing `LiveAuthorizationGate` semantics carry forward unchanged | AE + human authorization (separate, never system-issued) |

**First implementation milestone (STAGE-0-equivalent, human-gated before source-modifying phases):**

1. **HUMAN**: WP-12 CI enable decision → install the spec'd workflow (per-commit determinism + frozen-contract + secret gates).
2. **AUTHORIZED FIX WINDOW** (non-frozen modules only, each with positive+negative+regression tests): ARCH-F1 (kill-switch reset authentication + audit records — RT-F5), ARCH-F3 (`EvidenceProvenance` import), ARCH-F4 (`datetime`/`UTC` import), ARCH-F6 (dormant raw-hash path), RT-F7 (CLI inversion), RT-F8 (`ingest_from_file` dead path), ARCH-F5/F-11 hygiene.
3. **HUMAN**: H-1 ratification (Option A containment recommended).
4. **HUMAN**: real data source approval → governs whether PHASE E runs on synthetic contract data (paper-runtime bring-up) or verified real data.
5. Then PHASE B (interface specs) → C (event model) → D (TradingRuntime) in order; supervisor/autonomy machinery remains last (expansion-mandate STAGE 8 alignment); live capital stays never-authorized.

---

## 17. Authorization status

```text
RUNTIME_IMPLEMENTATION_AUTHORIZATION: PHASE_A_COMPLETE__NEXT_PHASES_GATED
```

- **PHASE A (this audit) is complete.** Zero source files were modified this cycle; frozen Phase 3 is byte-identical; all governance states are preserved (PRED-F1/F2/F3 CLOSED · ADVANCED_ML DEFERRED · REAL_DATA_VALIDATION BLOCKED · VERIFIED_YEARS = 0 · H-1 OPEN/CONTAINED · LIVE NOT AUTHORIZED).
- **PHASE B (interface/specification documents) may proceed as documentation** — no source changes required.
- **Source-modifying phases (C+) should sequence behind the STAGE-0-equivalent human decisions** (CI enable, authorized fix window, H-1 ratification, real-data approval) per the standing blocker register — consistent with the expansion mandate's dependency-gate rule and this repository's governance history.
- **LIVE execution remains NOT AUTHORIZED and structurally deny-by-default.** Any movement toward PHASE AD/AF is a separate, explicit, recorded human decision — never issued by the system, the agent, or the runtime itself.

---

## 18. Document reconciliation (no competing specifications)

| Existing authority | Role preserved |
|---|---|
| `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` v1.0.0 | Autonomy-status authority (L0–L8, STAGE 0–9, BLK register) — this document's §16 reconciles PHASE A–AF with its stage order; no contradiction: the runtime mandate's PHASE B–AB operationalizes the same components the expansion mandate staged |
| `AI_TRADING_LAB_ARCHITECTURE_READINESS_AUDIT.md` (external) | 5-family readiness authority (LSTM/Transformer/Ensemble/RL/Autonomous) — unchanged; NN/RL families remain NOT READY (BLK-2/3/6) |
| `MASTER_DOCUMENTATION_INDEX.md` | SSOT index — this document registered at v1.2.0 of the index |
| `ZAI_REPOSITORY_PROGRESS_BRIEF.md` v1.7.0 | Operator-facing progress brief — timeline row added for this audit |
| Construction blueprint / enhancement mandate / WP-12 spec / provenance policy | All remain authoritative in their domains; this audit introduces zero new specifications beyond itself |

**This document is the runtime-integration audit authority.** It will be updated at each runtime-era milestone (PHASE A–AF completions), and superseded only by its own later versions.




