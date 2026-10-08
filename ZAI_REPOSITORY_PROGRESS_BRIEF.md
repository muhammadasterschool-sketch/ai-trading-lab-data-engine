# AI Trading Lab — Data Engine
## Repository Progress Brief

```text
Document Type:  Progress brief (living orientation document)
Phase:          Cross-phase
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT
Version:        1.9.0
Last Updated:   2026-10-08 (P0 security credential cleanup + staged readiness program P0–P8 registered: SECURITY_CREDENTIAL_FORENSIC_REPORT.md)
Supersedes:     v1.8.0 (pre-paper bug forensic mandate: PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md)
Superseded By:  —
Source Evidence: git log, MASTER_DOCUMENTATION_INDEX.md, cycle records cited below
```

> One-page orientation: what exists in this repository today, how it got here,
> and what remains. Updated 2026-10-08 after the architecture readiness audit
> (v1.5.0), the Autonomous Intelligence + Full System Expansion mandate
> §78 audit baseline (v1.6.0 — see `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`),
> and the FINAL INTEGRATED RUNTIME mandate §2 repository audit (v1.7.0 — see
> `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`), and the FINAL PRE-PAPER BUG
> FORENSIC AND CLOSURE mandate (v1.8.0 — see
> `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md`: 3 CRITICAL new defects
> reproduced — limit-order price violation, position-flip basis, additive
> risk netting; PAPER_READY = NO), and the P0 security credential cleanup +
> forensic baseline (v1.9.0 — see `SECURITY_CREDENTIAL_FORENSIC_REPORT.md`:
> 0 secrets in tree / history / configuration; credential exposure #4
> contained by policy; staged readiness program P0–P8 registered; P0 COMPLETE).
> Documentation map of record: `MASTER_DOCUMENTATION_INDEX.md`.

| | |
|---|---|
| **Remote** | https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine |
| **HEAD** | `main` and `phase-4a/4a1-architecture-correction` in sync (see git log) |
| **Test suite** | **1,059 passed** (deterministic; verified 4x) |
| **Overall status** | Construction era COMPLETE · prediction intelligence layer BUILT, TESTED **and closure-validated** (PRED-F1/F2/F3 closed) · architecture readiness AUDITED (5 families NOT READY) · expansion era REGISTERED + §78 audit baseline COMPLETE (autonomy L0 achieved, L1–L5 components partial, L6 absent, L7/L8 never authorized — see `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`) · **runtime-integration era REGISTERED + PHASE A audit COMPLETE** (`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`: no runtime/event bus/persistence yet; risk gate + reconciliation + audit logger UNWIRED from the paper order path — RT-F1..F15 registered; PHASE B–AF gated) · **pre-paper bug forensic COMPLETE** (`PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md`: RT-F1..15 + MC-1..12 + ARCH-F1..4 all re-verified CONFIRMED; NEW BUG-001..009 (3 CRITICAL) reproduced 11/11; fixes prepared and BLOCKED_BY_AUTHORIZATION; PAPER_READY = **NO**) · **P0 security credential cleanup COMPLETE** (`SECURITY_CREDENTIAL_FORENSIC_REPORT.md`: 0 secrets in working tree / full 52-commit history / config; exposed PAT verified STILL ACTIVE via API — rotation advisory standing; staged readiness program P0–P8 registered, P0 done, P1 correction window awaiting human authorization) · empirical validation truthfully BLOCKED on real data · enhancement era REGISTERED, NOT STARTED · READY_WITH_FINDINGS |

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
| Runtime-integration §2 audit (PHASE A) | **FINAL INTEGRATED RUNTIME + MEMORY + LEDGER + PAPER/LIVE EXECUTION mandate (64 sections) registered**; §2 FIRST TASK repository audit executed (3 parallel read-only source surveys + first-hand defect re-verification, ARCH-F4 and the CLI check-boundary inversion reproduced by execution): `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` v1.0.0 — 29 inspection points answered, dependency/runtime/execution graphs, ownership tables, missing-connection register MC-1..12 (risk gate / reconciliation / audit logger / evaluation gates UNWIRED from the paper order path), RT-F1..F15 new findings, PHASE A–AF implementation order mapped to repo reality, RUNTIME_IMPLEMENTATION_AUTHORIZATION: PHASE_A_COMPLETE__NEXT_PHASES_GATED; documentation index v1.2.0 | `e060690` (1) | 1,059 |
| Pre-paper bug forensic & closure | **FINAL PRE-PAPER BUG FORENSIC AND CLOSURE mandate (32 sections) registered**; read-only forensic executed (first-hand re-verification of RT-F1..15, MC-1..12, ARCH-F1..4 — all CONFIRMED, zero false positives; adversarial deep-dives on limit-order safety, partial fills, audit mutability, memory persistence, ledgers, SL/TP, position accounting, reconciliation, state machine, bypass, CLI truthfulness; AST frozen-model mutable-field sweep): `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` v1.0.0 — NEW register **BUG-001..009** (3 CRITICAL: BUY limit fills ABOVE the limit / SELL below it, test-pinned; position flip carries the old side's basis into the new side (P&L doubles in error); additive risk netting rejects risk-REDUCING orders and TRIPS the kill switch; + HIGH missing-fill reconciliation blindness; + audit-logger mutability/unkeyed chain; + CLI "OPERATIONAL" untruthfulness; + robustness/deep-immutability items), **11/11 executable reproductions**, all fixes PREPARED and BLOCKED_BY_AUTHORIZATION (fix window = pending human decision), PAPER_READY = NO (PAPER-BLK-1..10); documentation index v1.3.0 | `24bf426` (1) | 1,059 |
| P0 security credential cleanup + forensic baseline | **Staged readiness program P0–P8 registered as the program of record** (P0 security cleanup → P1 correction window → P2 independent re-audit → P3 Stage-0 decision gate → P4 paper runtime → P5 paper E2E gate → P6 shadow → P7 canary → P8 final live audit; LIVE never authorizable by stage outcomes alone). P0 EXECUTED: `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` v1.0.0 — full credential sweep (working tree incl. hidden files, 261 tracked files, `.git/config`, docs, scripts, logs, artifacts) + full-history sweeps (string `-S` and real-token-shape `-G` across all 52 commits): **0 credentials anywhere** (only string-family occurrence = the WP-12 CI spec's own scan regex); exposed PAT verified STILL ACTIVE via GitHub API (login = repo owner); push of the pending `24bf426` + this commit executed per explicit operator live instruction (one-off credential use, never stored — `.git/config` grep-verified 0 tokens; rotation advisory standing, exposure #4); 1,059/1,059 tests + final gate 5/5 re-verified; documentation index v1.4.0 | this commit (1) | 1,059 |

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

- **1,059/1,059 tests pass** — deterministic across repeated runs (4×),
  cache disabled.
- **Frozen Phase 3 intact**: 11/11 strategy blobs byte-identical to `13fdc7e`;
  SUB-18 manifest 13/13 sha256 pins match (re-pinned by T-PRED-028).
- **Secret scan**: 0 hits across 261 tracked files; **0 real-token-shape
  strings across the full 52-commit history on all refs** (`-S`/`-G` sweeps —
  see `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` §5); 0 tokens in `.git/config`
  (verified after every push); 0 tracked symlinks; 0 path-traversal/exec
  patterns; 0 private endpoints (5-family security scan, closure cycle + P0
  credential sweep).
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
| RT-F1..F15 | 3 HIGH + 4 MEDIUM + 8 LOW | **registered (runtime-integration audit; zero source modified)** | Risk gate + kill switch NOT wired into the paper order path; `ReconciliationEngine` zero src callers; `AuditLogger` never invoked; no persistence in the execution domain (kill switch does not survive restart); order-vocabulary divergence paper vs frozen strategy; CLI check-boundary inverted (verified exit 1); `ingest_from_file` dead path; no model-loading/reconstruction path. Full register with evidence in `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` §12. **All 15 re-verified CONFIRMED by the pre-paper forensic.** |
| **BUG-001..009** | 3 CRITICAL + 1 HIGH + 2 MEDIUM + 3 LOW | **CONFIRMED_OPEN (pre-paper forensic; fixes prepared, BLOCKED_BY_AUTHORIZATION)** | BUG-001 limit-order fills violate the limit (BUY above / SELL below — spread+impact stacked on the limit reference; **pinned by test_pt_04:123**); BUG-002 position flip carries the old side's average cost into the new opposite side (downstream realized P&L doubled in error); BUG-003 additive risk netting rejects reductions/closes and TRIPS the kill switch (pinned by test_risk_portfolio.py:80); BUG-004 reconciliation blind to missing fills of FILLED orders; BUG-005 AuditLogger not deeply immutable + unkeyed re-forgeable chain; BUG-006 CLI reports OPERATIONAL with no runtime; BUG-007 unvalidated bar ordering; BUG-008 43 frozen-model mutable fields; BUG-009 NaN silently skipped in analytics. Full 12-column register + prepared fixes + regression-test specs in `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` §3/§5. |
| REAL-DATA / WP-12 / MODEL-APPROVAL / PAT-ROTATION | — | **HUMAN_DECISION_REQUIRED** | Real data source approval (candidate matrix ready); GitHub Actions CI (workflow spec ready, deliberately not installed); prediction registry approval owner; **rotate the chat-exposed GitHub PAT (4th exposure; verified STILL ACTIVE via API on 2026-10-08 — revoke immediately; one-off push use per operator instruction documented in `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` §6.3)**. |
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
3b. **Authorize the pre-paper fix window (FIRST new gating decision).** The
   pre-paper bug forensic (`PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md`)
   reproduced **3 CRITICAL defects** (BUG-001 limit-order price violation,
   BUG-002 position-flip basis corruption, BUG-003 additive risk netting that
   rejects risk-reducing orders and trips the kill switch) plus 1 HIGH and 5
   MEDIUM/LOW — all in **non-frozen** modules, all with prepared fixes and
   regression-test specs (report §5). A single human authorization ("fix
   window over paper/risk/cli non-frozen modules for BUG-001..009 +
   ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 hygiene") unlocks the correction stage of
   PAPER-BLK-7/8/9/10. Paper trading itself stays BLOCKED until the full
   PAPER-BLK-1..10 register closes (risk wiring, persistence, partial fills,
   ledgers, SL/TP, lineage). Also decide the audit-chain keyed-MAC custody
   policy (report §5.5). No daemon/scheduler/live activation may be started
   at any point without the separate paper-activation phase.
3c. **Execute the staged readiness program P0–P8 (program of record, registered
   2026-10-08).** P0 (security credential cleanup + forensic baseline) is
   COMPLETE (`SECURITY_CREDENTIAL_FORENSIC_REPORT.md` — repo-side baseline
   clean; PAT rotation still owed by the operator). The governing sequence
   from here: **P1 correction window** (same authorization request as item 3b:
   BUG-001..009 + ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 hygiene, non-frozen modules
   only) → **P2 independent re-audit** of those closures (READ ONLY, evidence
   over documentation) → **P3 Stage-0 decision gate** (real data / WP-12 CI /
   H-1 — the same human decisions as items 1, 2 and 8) → **P4 paper runtime +
   prediction + memory + ledgers** → **P5 paper E2E forensic gate** → **P6
   shadow mode** → **P7 sandbox/canary** → **P8 final live + autonomous
   readiness audit**. Live activation always requires separate explicit human
   authorization outside the program; the AI never authorizes itself.
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
9. **Rotate the GitHub PAT** (exposed in chat four times; verified STILL ACTIVE
   on 2026-10-08 — see `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` §3) and
   **final human acceptance** → graduation decision. Live execution remains
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
`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` (runtime-integration audit authority) ·
`PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` (authoritative pre-paper bug
register — BUG-001..009, PAPER-BLK-1..10, prepared fixes) ·
`SECURITY_CREDENTIAL_FORENSIC_REPORT.md` (P0 credential forensic baseline +
staged readiness program P0–P8 registration) ·

Read-only audit deliverable (maintained **outside** the repository, per the
audit's no-modification mandate): `AI_TRADING_LAB_ARCHITECTURE_READINESS_
AUDIT.md` — 12-section forensic report, A–X area survey, per-family
readiness tables (LSTM / Transformer / Ensemble / RL / Autonomous Trading),
and IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED with the sequenced path
that would change it.
