# AI Trading Lab — Data Engine
## Repository Progress Brief

```text
Document Type:  Progress brief (living orientation document)
Phase:          Cross-phase
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT
Version:        1.7.0
Last Updated:   2026-10-08 (FINAL INTEGRATED RUNTIME mandate — §2 FIRST TASK audit: TRADING_RUNTIME_ARCHITECTURE_AUDIT.md)
Supersedes:     v1.6.0 (Autonomous Intelligence + Full System Expansion mandate — §78 audit baseline)
Superseded By:  —
Source Evidence: git log, MASTER_DOCUMENTATION_INDEX.md, cycle records cited below
```

> One-page orientation: what exists in this repository today, how it got here,
> and what remains. Updated 2026-10-08 after the architecture readiness audit
> (v1.5.0), the Autonomous Intelligence + Full System Expansion mandate
> §78 audit baseline (v1.6.0 — see `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`),
> and the FINAL INTEGRATED RUNTIME mandate §2 repository audit (v1.7.0 — see
> `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`).
> Documentation map of record: `MASTER_DOCUMENTATION_INDEX.md`.

| | |
|---|---|
| **Remote** | https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine |
| **HEAD** | `main` and `phase-4a/4a1-architecture-correction` in sync (see git log) |
| **Test suite** | **1,059 passed** (deterministic; verified 3x) |
| **Overall status** | Construction era COMPLETE · prediction intelligence layer BUILT, TESTED **and closure-validated** (PRED-F1/F2/F3 closed) · architecture readiness AUDITED (5 families NOT READY) · expansion era REGISTERED + §78 audit baseline COMPLETE (autonomy L0 achieved, L1–L5 components partial, L6 absent, L7/L8 never authorized — see `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`) · **runtime-integration era REGISTERED + PHASE A audit COMPLETE** (`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`: no runtime/event bus/persistence yet; risk gate + reconciliation + audit logger UNWIRED from the paper order path — RT-F1..F15 registered; PHASE B–AF gated) · empirical validation truthfully BLOCKED on real data · enhancement era REGISTERED, NOT STARTED · READY_WITH_FINDINGS |

---

## 1. What this repository is

A **point-in-time (PIT) multi-asset market data engine** and strategy research
platform for systematic trading research, built governance-first: frozen Phase 3
strategy contracts, fail-closed filesystem security, hash-chained audit trails,
human-only authorization gates, and a live-trading boundary that is **never
authorized by design**. The Python package `data_engine` (src-layout, uv-managed)
covers the full research lifecycle: data ingestion → PIT views → feature
computation → backtesting → research validation → risk control → paper trading
→ governed evaluation and graduation.

## 2. Construction timeline (in order)

| Stage | Scope | Commits | Suite |
|---|---|---|---|
| Phases 0–3 (baseline, inherited) | Core engine, ingestion, PIT serialization/hashing, **frozen strategy engine** (11 blobs byte-pinned) | pre-`df44d27` | 465 |
| Phase 4A.1 remediation | 8/8 architecture blockers closed | `665a9d5..e7505d3` (9) | 563 |
| Phases 4A.2 → graduation | Corporate actions, derivatives, research gov, registry, features, validation, risk, hermes, infra, paper trading, graduation layer | `0ce78f6..a7fba96` (12) | 692 |
| Master-mandate cycle | Strategy discovery, knowledge/memory, benchmarks, end-to-end lifecycle test | `0cafbb4..281dfdc` (5) | 789 |
| Governance docs (CR-10) | 10 audit/governance reports committed into repo | `018d084` (1) | 789 |
| Progress brief | Consolidated progress summary | `3084dcb` (1) | 789 |
| Enhancement Mandate v2.0 | 50-section enhancement/hardening mandate filed verbatim + registration & gap analysis | `78349e1` (1) | 789 |
| Progress brief update | Brief refreshed to cover mandate registration | `6d0ad30` (1) | 789 |
| Documentation normalization | Phase-wise documentation index (SSOT), contradiction register, link audit, doc-control headers — 4 new canonical docs, zero renames | `9982edc..228bf20` (2) | 789 |
| Prediction & Crash Intelligence | New `prediction/` package (24 modules): PIT-correct features/labels/regimes, baseline-first models + justification gate, calibration, uncertainty, drift, evidence scores, human-only model registry, outcome ledger, no-prediction gates, walk-forward + warning quality, crash-risk estimator, scenarios, systemic risk, advisory-only risk integration — T-PRED-001..030 matrix | `67a273e..9ddc23c` (3) | 915 |
| Prediction closure & validation | 7 closure modules (datasets + quality gates + source registry + artifact verification + event evaluation + benchmark harness + red-team matrix); PRED-F3 estimator re-verification; crash completion; **PRED-F1/F2/F3 CLOSED**; 45/45 red-team attacks defended; claim categories strictly separated; 4 closure docs + WP-12 CI spec | `56ffa6e..02496b7` (7) | 1,059 |
| Architecture readiness audit (READ-ONLY) | Forensic audit toward the five core objectives (LSTM / Transformer / Randomized Ensemble / RL / Autonomous Trading): 24-area survey (A–X), temporal-leakage-path analysis, 12-section structured report with per-family readiness tables and IMPLEMENTATION_AUTHORIZATION: **NOT_AUTHORIZED**; 12 new findings registered (ARCH-F1..F12); zero source files modified — brief update commit only | `7d691c8` (1) | 1,059 |
| Autonomous expansion §78 audit baseline | **Autonomous Intelligence + Full System Expansion mandate (78 sections) registered**; §78 FIRST COMMAND audit executed (read-only): `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` v1.0.0 — autonomy levels L0–L8 mapped (L0 achieved; L1–L5 partial components; L6 absent; L7/L8 not authorized), decision-loop stage mapping, state-machine vocabulary gap, duplicate-system audit (zero duplicates; 2 unification flags + 1 naming collision), dependency graph (STAGE 0–9), blocker table BLK-1..15, test inventory (35 files); documentation index v1.1.0 | `3567c69` (1) | 1,059 |
| Runtime-integration §2 audit (PHASE A) | **FINAL INTEGRATED RUNTIME + MEMORY + LEDGER + PAPER/LIVE EXECUTION mandate (64 sections) registered**; §2 FIRST TASK repository audit executed (3 parallel read-only source surveys + first-hand defect re-verification, ARCH-F4 and the CLI check-boundary inversion reproduced by execution): `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` v1.0.0 — 29 inspection points answered, dependency/runtime/execution graphs, ownership tables, missing-connection register MC-1..12 (risk gate / reconciliation / audit logger / evaluation gates UNWIRED from the paper order path), RT-F1..F15 new findings, PHASE A–AF implementation order mapped to repo reality, RUNTIME_IMPLEMENTATION_AUTHORIZATION: PHASE_A_COMPLETE__NEXT_PHASES_GATED; documentation index v1.2.0 | this commit (1) | 1,059 |

## 3. What was built, phase by phase

**Phase 4A.1 — architecture correction (8/8 blockers CLOSED).** Canonical
type-tagged serialization (`pit/serialization.py`), identity/eligibility hashing
with prohibited-field enforcement (`pit/hashing.py`), temporal-semantics and
policy validators, six new PIT modules (sidecar, revision chain, tiebreaker,
instrument primitives, PIT view/builder, experiment identity), filesystem
containment security layer with hash-chained audit trail, re-established
implementation record, and 95 mandated acceptance identifiers as named tests
plus a 15/15 mutation detection gate.

**Phases 4A.2–4A.4.** Corporate-action engine (splits/dividends, announcement ≤
effective semantics, as-of universes), derivatives package (futures contracts,
rollover detection, continuous series with roll-leakage protection), research
governance with structural no-self-approval.

**Phases 5–11.** Experiment registry (duplicate-identity rejection,
reproducibility verdicts), PIT feature pipeline (slice-then-compute), research
validation (bias/leakage/overfitting detectors, walk-forward, robustness),
risk engine (hard limits, kill switch, hash-chained violations, exposure),
hermes agent-permission layer (structurally-unavailable permissions, audited
rejections), infra (reproducibility RNG detector, phantom-proof metrics,
tamper-fail-closed checkpoints), paper trading (realism simulator with
latency/spread/impact, gateway, side-aware positions, three-way
reconciliation).

**Graduation layer.** 30-day evaluation rule (structural, from provided
timestamps), human-only token registry (starts empty), graduation/retirement
flows, and `LiveAuthorizationGate` — deny-by-default, 4-condition conjunctive,
machine principals refused. **Live execution is modeled but never grantable
without an explicit human token the blueprint never issues.**

**Master-mandate cycle.** Strategy discovery (`discovery/` — candidates,
identity allowlists, fail-closed grids, validated-only registry,
execution-eligibility chain defaulting to NO TRADE), knowledge/memory layer
(`knowledge/` — 5 record classes, authoritative-source filtering, content
addressing, bounded memory), performance benchmarks (`benchmarks/` — 10 real
component surfaces, timing-excluded hashes), and a full 15-stage end-to-end
lifecycle test ending in a governed REJECTION with NO TRADE at 10 boundaries.

**Prediction & crash intelligence layer (PRED).** The repository is no longer
only a strategy/backtesting system: `src/data_engine/prediction/` adds a
governed prediction laboratory. Every crash output is probabilistic — never a
deterministic claim — and the system refuses instead of guessing
(NO_SIGNAL / MODEL_UNCERTAIN / DATA_INSUFFICIENT / REGIME_UNKNOWN /
PREDICTION_BLOCKED with machine-readable reasons). Highlights: PIT candle
views with revision defense and survivorship-safe universes; a 5-year minimum
history policy enforced by default; configurable crash labels with a structural
label/feature boundary proof; a deterministic regime engine with transitions
recorded as events; baseline-first models with a MODEL_NOT_JUSTIFIED gate;
Brier/log-loss/ECE calibration with Platt scaling; PSI drift monitoring with
mandated failure actions; an 11-dimension evidence score that fails toward
EVIDENCE_INSUFFICIENT; a model lifecycle registry where PAPER/GRADUATE require
HUMAN approval and AI self-approval is structurally rejected; an append-only
hash-chained outcome ledger; walk-forward evaluation reusing the Phase 7 plan
builder; crash-warning quality metrics (lead time, false alarms, misses);
scenarios that are never forecasts; and an advisory-only risk interface over
the real Phase 8 hard limits with kill-switch suppression. **Honest limits:**
no real market datasets exist in the repository (the policy engine and refusal
states are tested; no coverage claim), a single advanced model family
(deterministic logistic) is implemented, and microstructure is explicitly
UNAVAILABLE.

## 4. Current verified state (all gates green at the closure-cycle HEAD)

- **1,059/1,059 tests pass** — deterministic across repeated runs (3×),
  cache disabled.
- **Frozen Phase 3 intact**: 11/11 strategy blobs byte-identical to `13fdc7e`;
  SUB-18 manifest 13/13 sha256 pins match (re-pinned by T-PRED-028).
- **Secret scan**: 0 hits across 257 tracked files; 0 secrets in full history;
  0 tracked symlinks; 0 path-traversal/exec patterns; 0 private endpoints
  (5-family security scan, closure cycle).
- **Mutation gate**: 15/15 reintroduced defects detected (4A.1 cycle).
- **Cross-process identity**: `disc20.` / `know42.` / `bmk30.` / `pred.` hashes
  stable across fresh OS processes.
- **Red-team matrix**: 45/45 adversarial attacks defended (deterministic
  matrix hash `preda.8366…`).
- **Security**: no network/MT5/broker code in `src`; filesystem containment
  fail-closed; zero untracked artifacts; working tree clean.
- **Claim boundary (honest)**: 0 verified years of real market data —
  REAL_DATA_VALIDATION = BLOCKED; all quantitative benchmark outputs are
  declared-synthetic contract verification, never empirical evidence.

## 5. Open items (honest register — see `ZAI_DEFECT_REGISTER.md`)

| ID | Severity | State | Summary |
|---|---|---|---|
| H-1 / F-04 | HIGH | **OPEN / CONTAINED** | `Candle.to_hash()` non-deterministic when `provider_timestamp` unset; dormant path (zero active callers); Phase 4 identity prohibited from using it at 3 layers. Human ratification of containment pending. |
| F-11 | MEDIUM | registered | `QuantEngine` does not merge `IndicatorSpec.parameters` defaults — bare `sma` yields all-None; pre-parameterized names (`sma20`, `rsi14`) work. |
| PRED-F1/F2/F3 | — | **CLOSED (closure cycle)** | Benchmark protocol + blocked/refusal harness; 45-attack red-team matrix; estimator artifact re-verification. Evidence: `PREDICTION_VALIDATION_EVALUATION_REPORT.md` §3–5/§7. |
| ARCH-F1..F12 | 5 MEDIUM + 6 LOW + 1 INFO | **registered (read-only audit)** | Kill-switch reset unauthenticated (`risk/engine.py:174-176`); latent NameErrors on dormant paths (`ingestion.py:191`, `quant_boundary.py:118/:175`); purge/embargo defaults unsafe for future overlapping sequence windows; walk-forward plan builder lacks a purge parameter; risk violation chain lacks `verify()`; + hygiene items. Full register with file:line evidence in the audit deliverable (kept outside the repository per the read-only mandate). |
| RT-F1..F15 | 3 HIGH + 4 MEDIUM + 8 LOW | **registered (runtime-integration audit; zero source modified)** | Risk gate + kill switch NOT wired into the paper order path; `ReconciliationEngine` zero src callers; `AuditLogger` never invoked; no persistence in the execution domain (kill switch does not survive restart); order-vocabulary divergence paper vs frozen strategy; CLI check-boundary inverted (verified exit 1); `ingest_from_file` dead path; no model-loading/reconstruction path. Full register with evidence in `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` §12. |
| REAL-DATA / WP-12 / MODEL-APPROVAL / PAT-ROTATION | — | **HUMAN_DECISION_REQUIRED** | Real data source approval (candidate matrix ready); GitHub Actions CI (workflow spec ready, deliberately not installed); prediction registry approval owner; rotate the chat-exposed GitHub PAT. |
| — | 4 MEDIUM + 8 LOW | registered | Counting nuances, CRLF decision recorded-not-acted, stale blueprint status lines. |

**Gated (not defects):** 30-day paper-trading evaluation not yet started (no
candidates exist yet); external review windows (GPT re-audit, Claude fix
window) not dispatched; final human acceptance pending.

## 6. Repository layout

```
src/data_engine/
  pit/            serialization, hashing, views, sidecars, revisions (4A.1)
  strategy/       FROZEN Phase 3 engine (backtest, equity, execution, ledger…)
  actions/        corporate actions (4A.2)      derivatives/ (4A.3)
  research/       human-only approvals (4A.4)   experiment_registry/ (5)
  quant/          PIT features (6)              research_validation/ (7)
  risk/           limits, kill switch (8)       hermes/ agent perms (9)
  infra/          reproducibility, metrics (10) paper/ simulator, eval (11)
  discovery/      strategy candidates (mandate) knowledge/ records (mandate)
  benchmarks/     performance surfaces (mandate)
  prediction/     prediction & crash intelligence (PRED — 31 modules:
                  24 construction + 7 closure: datasets, quality gates,
                  source registry, artifact verification, event
                  evaluation, benchmark, red-team matrix)
  …               + core modules (schemas, provider, storage, security…)
tests/            1,059 tests incl. test_pit_view.py (95 IDs), lifecycle,
                 the T-PRED-001..030 prediction matrix (126 tests),
                 and the closure suites (144 tests: datasets/quality,
                 artifact verification, event evaluation, benchmark,
                 red-team matrix, drift validation)
docs/             engine design docs
*.md (root)       80+ governance/audit/implementation records
```

## 7. What comes next

1. **Approve real data sources for the prediction layer** — the dataset
   framework, 16 quality gates, source registry, and refusal states are
   complete and tested, but the repository contains NO real market datasets.
   Five candidate sources are declared UNVETTED with honest limitation notes
   (`PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md` §6) and approval templates
   are ready (§7). This is THE gating decision for everything empirical.
2. **Decide GitHub Actions CI (WP-12)** — the workflow is specified and
   installation-ready (`WP_12_CI_IMPLEMENTATION_SPEC.md`); one operator
   decision record installs it. Local gates remain authoritative until then.
3. **Execute the Autonomous Intelligence + Full System Expansion mandate**
   (78 sections; governing status doc:
   `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`). The §78 audit is COMPLETE;
   implementation follows STAGE 0–9 dependency order: STAGE 0 (WP-12 CI
   enable + authorized fix window ARCH-F1/F3/F4/F6 + H-1 ratification) →
   STAGE 1 (real data + sequence layer) → STAGE 2 (justification-gated
   LSTM → Transformer → Ensemble) → … → STAGE 8 (governed autonomy
   supervisor, paper-scope only). ADVANCED_ML: DEFERRED and
   REAL_DATA_VALIDATION: BLOCKED stand until human-lifted. Live execution
   stays never-authorized.
3a. **Execute the FINAL INTEGRATED RUNTIME mandate** (64 sections; governing
   audit: `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`). **PHASE A (repository
   audit) is COMPLETE**; implementation follows PHASE B–AF order: PHASE B
   (runtime interface specs — may proceed as documentation) → PHASE C (typed
   event model + event bus) → PHASE D (`TradingRuntime` composition root) →
   … → PHASE L (wire the existing `RiskEngine` into the order path) → … →
   PHASE T (wire reconciliation with a blocking verdict) → PHASE AB (paper
   trading activation) → PHASE AC–AE (shadow/canary/broker-sandbox — all NEW)
   → PHASE AF (LIVE adapter — never without explicit external human
   authorization). Source-modifying phases sequence behind the same STAGE-0
   human decisions (CI enable, authorized fix window incl. RT-F7/F8, H-1
   ratification, real-data approval). The runtime mandate and the expansion
   mandate are one construction program seen from two lenses: PHASE B–AB
   operationalizes the components the expansion mandate staged as STAGE 4–8.
4. **Execute the Enhancement Mandate v2.0** (`MASTER_ENHANCEMENT_HARDENING_
   MANDATE.md`, registered NOT started): 17 work packages — 3 ABSENT (model
drift, CI gates, operator plane), 14 PARTIAL. Recommended order in
   `ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` §6. Note: PSI drift monitoring
   now exists in `prediction/`; WP-5 remains about wiring it into
   strategy-lifecycle monitoring.
5. **Name the prediction registry approval owner** — the registry rejects
   AI approvals structurally; the first human approval record activates the
   model lifecycle (DRAFT→…→GRADUATE needs a named owner).
6. **Start the 30-day paper-trading evaluation** once a strategy candidate is
   validated and registered (rule is structural and already implemented).
7. **Dispatch external review windows** — GPT re-audit and Claude fix window
   (F-11, the 4 MEDIUM findings, and the ARCH-F1/F3/F4/F6 + RT-F7/F8 audit
   findings are queued for the fix window).
8. **Ratify H-1 containment** — human decision on `PHASE_GOVERNANCE_
   RECONCILIATION.md` recommendation (Option A: containment, no Phase 3
   amendment). The prediction layer is H-1 independent by construction.
9. **Rotate the GitHub PAT** (exposed in chat multiple times) and **final
   human acceptance** → graduation decision. Live execution remains
   never-authorized without an explicit human-issued token.

## 8. Key documents in this repository

`MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` (construction authority) ·
`MASTER_ENHANCEMENT_HARDENING_MANDATE.md` (enhancement authority, v2.0) ·
`MASTER_DOCUMENTATION_INDEX.md` (documentation SSOT — every doc classified) ·
`AI_TRADING_LAB_PREDICTION_CRASH_INTELLIGENCE_SPEC.md` (prediction authority,
v1.1.0) ·
`PREDICTION_VALIDATION_EVALUATION_REPORT.md` (closure evidence + claim
boundary) ·
`PREDICTION_REDTEAM_ADVERSARIAL_REPORT.md` (45-attack executed matrix) ·
`PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md` (data governance) ·
`WP_12_CI_IMPLEMENTATION_SPEC.md` (CI decision pending) ·
`GOVERNANCE_DOCUMENT_CONTRADICTION_REGISTER.md` (live contradiction tracking) ·
`ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` (gap map, 17 packages) ·
`PREDICTION_INTELLIGENCE_IMPLEMENTATION_REPORT.md` (PRED cycle record, v1.1.0) ·
`PHASE_4A1_IMPLEMENTATION_RECORD.md` ·
`PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md` ·
`PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` ·
`ZAI_CURRENT_REPOSITORY_STATE.md` · `PHASE_GOVERNANCE_RECONCILIATION.md` ·
`H1_FORMAL_DECISION_ANALYSIS.md` · `ZAI_DEFECT_REGISTER.md` ·
`ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` ·
`FINAL_FULL_REPOSITORY_FORENSIC_AUDIT.md` ·
`AI_TRADING_LAB_FINAL_ACCEPTANCE_AUDIT.md` ·
`ZAI_REPOSITORY_PROGRESS_BRIEF.md` (this document) ·
`ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` (autonomous trading system status —
expansion-era §76 living document) ·
`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` (runtime-integration audit authority —
FINAL INTEGRATED RUNTIME mandate §2 deliverable: dependency/runtime/execution
graphs, ownership tables, MC-1..12 missing connections, RT-F1..15 findings,
PHASE A–AF implementation order)

Read-only audit deliverable (maintained **outside** the repository, per the
audit's no-modification mandate): `AI_TRADING_LAB_ARCHITECTURE_READINESS_
AUDIT.md` — 12-section forensic report, A–X area survey, per-family
readiness tables (LSTM / Transformer / Ensemble / RL / Autonomous Trading),
and IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED with the sequenced path
that would change it.
