# AI Trading Lab — Data Engine
## Repository Progress Brief

```text
Document Type:  Progress brief (living orientation document)
Phase:          Cross-phase
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT
Version:        1.13.0
Last Updated:   2026-10-09 (PAPER-READINESS RE-AUDIT EXECUTED: blocker closure + runtime-integration forensic re-audit — PAPER_TRADING_READINESS_FINAL_REPORT.md v2.0.0)
Supersedes:     v1.12.0 (PRE-PAPER READINESS IMPLEMENTATION EXECUTED)
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
> **P1 correction window EXECUTED (v1.10.0 — see
> `P1_CORRECTION_WINDOW_REPORT.md`): all 16 authorized findings
> corrected with objective evidence (1,141/1,141 tests ×3; 0/17
> AFTER-probes defective; frozen contracts INTACT; local commits NOT
> pushed).**
> **P2 independent re-audit EXECUTED (v1.11.0 — see
> `P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md`): 15/16 findings
> CLOSED with independently re-verified evidence, BUG-008 PARTIAL
> (rule-compliant deferral); P2 VERDICT: CONDITIONAL PASS; frozen
> contracts INTACT; 1,141/1,141 re-verified; exposed PAT re-verified
> STILL ACTIVE (exposure #5) — rotation still owed.**
> **PRE-PAPER READINESS IMPLEMENTATION EXECUTED (v1.12.0 — see
> `PAPER_TRADING_READINESS_FINAL_REPORT.md`): the authoritative
> paper-trading runtime is BUILT and VERIFIED — PIT-safe sequence
> engine, deterministic baseline + NumPy LSTM + NumPy Transformer +
> validated ensemble + Platt calibration, 21-check structural risk
> gate, 7-scope hierarchical kill switch, 14-state OMS with idempotent
> order identity / partial fills / TTL, persistent execution state
> (atomic snapshots + hash-chained journal), 9 tamper-evident ledgers
> with NO_TRADE ledgering, SL/TP lifecycle, multi-fill-aware
> reconciliation, structured memory, restart/recovery, deterministic
> replay, and the fail-closed 23-gate readiness gate. RT-F1..F6,
> F9..F12, F14, F15 and ARCH-F2/F5/F7/F8/F9/F10/F11 corrected with
> regression evidence; BUG-008 = DEFERRED-BY-FROZEN-CONTRACT with the
> runtime-boundary adapter. 1,335/1,335 tests (1141 + 194 new) ×2
> deterministic; frozen 11/11 + 13/13 INTACT; security scans 0 hits.
> PAPER_READY = FALSE — honestly: 0 REAL_VERIFIED datasets
> (BLOCKED_ON_REAL_DATA), H-1/CI authorization + PAT rotation remain
> human decisions (records created, none fabricated).**
> **PAPER-READINESS RE-AUDIT EXECUTED (v1.13.0 — see
> `PAPER_TRADING_READINESS_FINAL_REPORT.md` v2.0.0): independent
> forensic re-verification of the integrated runtime found and closed
> every technically-authorized blocker — persistence is now MANDATORY
> (NO_STATE_STORE ⇒ start REFUSED; write failure ⇒ safe HALT;
> explicit ephemeral-fixture marking for unit tests), the 30-gate
> readiness gate is AUTHORITATIVE at startup (23 → 30 gates incl.
> REAL_DATA_READY), recovery is INTEGRATED INTO TradingRuntime.start()
> (LOAD → VERIFY → RESTORE → RECONCILE → RESUME; proven at the ten
> mandated restart points with bit-exact state equivalence), the
> execution-state persistence is COMPLETE (EXECUTION_STATE_SCHEMA
> v1.1.0 — full ledger chains + memory + pending SL/TP + bar history
> + identity binding), kill-switch trips persist IMMEDIATELY (a
> restart never clears a switch), a real PARTIALLY_FILLED → EXPIRED
> state-machine defect was fixed, two wall-clock identity contaminants
> were removed (deterministic replay now bit-identical across
> independent processes ×2), and REAL_VERIFIED promotion now requires
> the complete nine-stage chain (VERIFIED_YEARS reported honestly as
> 0). 43 new integration tests; 1,378/1,378 ×2 deterministic; frozen
> 13/13 INTACT before AND after; security scans 0 hits. PAPER_READY
> = FALSE — STATUS = BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY (real data
> + H-1 + CI + PAT rotation + BUG-008 residual + keyed-MAC custody).**
> Documentation map of record: `MASTER_DOCUMENTATION_INDEX.md`.

| | |
|---|---|
| **Remote** | https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine |
| **HEAD** | `main` and `phase-4a/4a1-architecture-correction` in sync (see git log) |
| **Test suite** | **1,378 passed + 1 skipped** (deterministic; 2× re-verified in the re-audit cycle; 1,335 + 43 re-audit integration tests) |
| **Overall status** | Construction era COMPLETE · prediction intelligence layer BUILT, TESTED **and closure-validated** (PRED-F1/F2/F3 closed) · architecture readiness AUDITED (5 families NOT READY) · expansion era REGISTERED + §78 audit baseline COMPLETE (autonomy L0 achieved, L1–L5 components partial, L6 absent, L7/L8 never authorized — see `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md`) · **runtime-integration era REGISTERED + PHASE A audit COMPLETE** (`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md`: no runtime/event bus/persistence yet; risk gate + reconciliation + audit logger UNWIRED from the paper order path — RT-F1..F15 registered; PHASE B–AF gated) · **pre-paper bug forensic COMPLETE** (`PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md`: RT-F1..15 + MC-1..12 + ARCH-F1..4 all re-verified CONFIRMED; NEW BUG-001..009 (3 CRITICAL) reproduced 11/11; fixes prepared and BLOCKED_BY_AUTHORIZATION; PAPER_READY = **NO**) · **P0 security credential cleanup COMPLETE** (`SECURITY_CREDENTIAL_FORENSIC_REPORT.md`: 0 secrets in working tree / full 52-commit history / config; exposed PAT verified STILL ACTIVE via API — rotation advisory standing; staged readiness program P0–P8 registered, P0 done, P1 correction window awaiting human authorization) · **P1 correction window EXECUTED** (`P1_CORRECTION_WINDOW_REPORT.md`: BUG-001..009 + ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 all corrected — limit-price protection, flip basis, signed netting, status-aware reconciliation, audit deep-immutability, truthful CLI status, bar-order validation, deep-immutability migration (25 fields, `pit/immutable.py`), NaN guards, human-gated kill-switch reset, latent NameErrors, deterministic raw hash, CLI boundary fix, live file-ingest path, pytest dev-only; 82 new tests; closure verdicts deferred to P2) · **P2 independent re-audit EXECUTED — CONDITIONAL PASS** (`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md`: every P1 correction re-verified first-hand from diffs + probes — 15/16 findings CLOSED (BUG-001..007/009, ARCH-F1/F3/F4/F6, RT-F7/F8/F13), BUG-008 PARTIAL (25/25 in-scope fields migrated and runtime-blocked 31/31; 13 fields rule-deferred under frozen-contract/manifest immunity); no regressions; frozen 11/11 + 13/13 re-verified blob-level; credential STILL ACTIVE — exposure #5, rotation OPEN) · **PRE-PAPER READINESS IMPLEMENTATION EXECUTED** (`PAPER_TRADING_READINESS_FINAL_REPORT.md`: authoritative runtime BUILT — sequence engine, baseline/LSTM/Transformer/ensemble/calibration, risk gate, kill switches, OMS, persistence, ledgers, SL/TP, reconciliation, memory, recovery, replay, readiness gate; RT-F1..F6/F9..F12/F14/F15 + ARCH-F2/F5/F7/F8/F9/F10/F11 closed with regression evidence; BUG-008 DEFERRED-BY-FROZEN-CONTRACT via runtime-boundary adapter; 194 new tests) · **PAPER-READINESS RE-AUDIT EXECUTED** (`PAPER_TRADING_READINESS_FINAL_REPORT.md` v2.0.0: every re-audit blocker verified first-hand and closed where authorized — persistence MANDATORY + readiness-gated startup + runtime-integrated recovery at 10 restart points + complete EXECUTION_STATE_SCHEMA v1.1.0 + full ledger/memory chain recovery + immediate kill-switch persistence + PARTIAL→EXPIRED state-machine fix + wall-clock-free identity (cross-process replay ×2 deterministic) + 30-gate readiness set + nine-stage REAL_VERIFIED chain with honest VERIFIED_YEARS=0; 43 new integration tests) · empirical validation truthfully BLOCKED on real data · PAPER_READY = FALSE (STATUS = BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY) · READY_WITH_FINDINGS |

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
| P0 security credential cleanup + forensic baseline | **Staged readiness program P0–P8 registered as the program of record** (P0 security cleanup → P1 correction window → P2 independent re-audit → P3 Stage-0 decision gate → P4 paper runtime → P5 paper E2E gate → P6 shadow → P7 canary → P8 final live audit; LIVE never authorizable by stage outcomes alone). P0 EXECUTED: `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` v1.0.0 — full credential sweep (working tree incl. hidden files, 261 tracked files, `.git/config`, docs, scripts, logs, artifacts) + full-history sweeps (string `-S` and real-token-shape `-G` across all 52 commits): **0 credentials anywhere** (only string-family occurrence = the WP-12 CI spec's own scan regex); exposed PAT verified STILL ACTIVE via GitHub API (login = repo owner); push of the pending `24bf426` + this commit executed per explicit operator live instruction (one-off credential use, never stored — `.git/config` grep-verified 0 tokens; rotation advisory standing, exposure #4); 1,059/1,059 tests + final gate 5/5 re-verified; documentation index v1.4.0 | `5079484` (1) | 1,059 |
| P1 correction window (staged program stage 1) | **Operator-authorized fix window EXECUTED over non-frozen modules** (`P1_CORRECTION_WINDOW_REPORT.md` v1.0.0): all 16 authorized findings corrected — 3 CRITICAL (limit-order price protection with exact cost accounting; position-flip basis at the flip fill price; signed risk netting that never trips on reductions/closes) + 1 HIGH (status-aware reconciliation: fills-iff-FILLED) + ARCH-F1 (human-principal-gated kill-switch reset + non-silent opt-out) + ARCH-F3/F4 (latent NameErrors) + ARCH-F6 (deterministic raw hash, H-1 containment preserved) + RT-F7/F8/F13 (CLI boundary exit semantics; live file-ingest path through FS-06 containment; pytest dev-only + audit.log untracked) + the deep-immutability migration (25 non-pinned frozen-model fields via new `pit/immutable.py`; strategy/×9 + schemas.py×4 excluded by frozen-contract/manifest rules) + BUG-005/006/007/009; 82 new regression tests + 3 pinned-test amendments; suite 1,059→1,141 (×3 deterministic); frozen gates 11/11 + 13/13 pre- and post-commit; secret scan 0; AFTER-evidence probe 0/17 defective; BUG-008 runtime sweep 31/31 blocked; commits 1277331 + docs **local only — NOT pushed (rule 11)**; closure verdicts deferred to the P2 independent re-audit | `1277331` + docs (2) | 1,141 |
| P2 independent re-audit (staged program stage 2, READ-ONLY) | **Independent re-audit of every P1 correction, evidence-first** (`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` v1.0.0): first-hand re-derivation of all 16 corrections from the `1277331` diffs + re-execution of the full suite (1,141/1,141 ×2 deterministic) + 8 category subsets (PIT 195 / identity 33 / red-team 61 / risk 11 / paper 10 / governance 21 / infra 8 / P1-window 82) + AFTER-probe 0/17 defective + BUG-008 sweep 31/31 blocked + BEFORE-probe convention artifacts verified first-hand; the 3 pinned-test amendments verified HONEST (defect-pins → corrected assertions); frozen gates re-verified blob-level (11/11 + 13/13); secret/history/config scans 0; **VERDICTS: 15 CLOSED · 1 PARTIAL (BUG-008 — 13 fields deferred under frozen/manifest immunity, registered follow-up) · 0 OPEN · 0 REGRESSED; P2 VERDICT: CONDITIONAL PASS** (conditions operator-side: PAT rotation, BUG-008 residual authorization path, keyed-MAC custody decision); OBS-1 recorded (262-file mode-only worktree sweep, content 0/0 — environment artifact, cosmetic); NO implementation modified by the audit | docs commit | 1,141 |
| Pre-paper readiness implementation (operator-authorized, this cycle) | **THE AUTHORITATIVE PAPER-TRADING RUNTIME IS BUILT AND VERIFIED** (`PAPER_TRADING_READINESS_FINAL_REPORT.md` v1.0.0 + 11 runtime specs + 3 governance decision records): new `src/data_engine/runtime/` package (22 modules) — PIT-safe sequence engine with horizon-scaled purge/embargo; deterministic baseline + NumPy LSTM (full BPTT) + NumPy Transformer (causal self-attention, full backward) + compatibility-validated ensemble + Platt calibration with ECE; DecisionEngine (NO_TRADE first-class); TradePlan builder (risk-budget sizing, vol-derived SL/TP); structural 21-check RiskGate wired into OMS approval (bypass impossible); 7-scope hierarchical kill switch (human-gated reset); 14-state OMS with idempotent order identity, partial fills, TTL, ambiguous-order reconcile-before-retry; multi-bar partial-fill paper executor (latency, liquidity caps, BUG-001 limit protection, structural PAPER isolation); persistent execution state (atomic snapshots + fsync hash-chained journal); 9 tamper-evident ledgers with NO_TRADE ledgering; SL/TP lifecycle + 9 exit reasons; multi-fill-aware three-way reconciliation; 12-category structured memory; restart/recovery (restore→verify→reconcile→resume-or-halt); deterministic replay; fail-closed 23-gate readiness gate. Existing-module corrections: RT-F5/F9 (risk engine), RT-F11 (gateway docstring), RT-F12 (benchmark via gateway), RT-F14 (model reconstruction incl. prediction layer), RT-F15 (explicit failure), ARCH-F2/F5/F7/F8/F9/F10/F11. BUG-008 = DEFERRED-BY-FROZEN-CONTRACT (runtime-boundary adapter; 13 pinned fields untouched). 194 new tests (E2E positive+negative, 24 failure-injection scenarios, recovery, replay, closures); suite 1,141→1,335 ×2 deterministic; frozen 11/11 + 13/13 INTACT; security scans 0; PAPER_READY = FALSE — BLOCKED_ON_REAL_DATA + H-1/CI human decisions + PAT rotation (exposure #6) | implementation + docs | 1,335 |
| Paper-readiness re-audit (operator-authorized, this cycle) | **BLOCKER CLOSURE + RUNTIME-INTEGRATION FORENSIC RE-AUDIT EXECUTED** (`PAPER_TRADING_READINESS_FINAL_REPORT.md` v2.0.0): all 28 re-audit blockers verified first-hand against the code; every technically-authorized one CLOSED — **persistence MANDATORY** (NO_STATE_STORE ⇒ start REFUSED; corrupt/unavailable store ⇒ REFUSED; write failure ⇒ safe HALT; read failure ⇒ RECOVERY_REQUIRED; explicit `ephemeral_test_fixture` marking for unit tests, ledgered non-operational); **readiness gate AUTHORITATIVE at startup** (23→30 gates incl. REAL_DATA_READY/TRADE_PLAN/PARTIAL_FILL/SLTP/AUDIT/REPLAY/BASELINE; one FALSE ⇒ start REFUSED); **recovery INTEGRATED into TradingRuntime.start()** (LOAD→VERIFY→RESTORE→RECONCILE→RESUME; ten mandated restart points with bit-exact state equivalence incl. partial fills, SL/TP, kill switches, idempotency); **EXECUTION_STATE_SCHEMA v1.1.0** (18 fields — full ledger chains + memory + pending protection/exits + bar history + identity binding; validated on persist AND restore); **kill-switch trips/halts persist immediately** (restart never clears a switch); **REAL DEFECT FIXED**: PARTIALLY_FILLED→EXPIRED transition was illegal while expiry accepted partial orders (crash) — now legal + tested; **wall-clock identity contaminants removed** (assessment id embedded `assessed_at`; cold-start incident embedded the store path) — deterministic replay now bit-identical across independent processes ×2; REAL_VERIFIED nine-stage chain + honest VERIFIED_YEARS=0; model pinning + restart identity binding (foreign model refused). 43 new integration tests; suite 1,335→1,378 ×2 deterministic; frozen 13/13 INTACT before AND after; security re-scan 0 hits; PAPER_READY = FALSE — STATUS = BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY (real data + H-1 + CI + PAT rotation #7 + BUG-008 residual + keyed-MAC custody) | implementation + docs | 1,378 |

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

## 4. Current verified state (all gates green at the re-audit-cycle HEAD)

- **1,378 passed + 1 skipped tests** — deterministic across repeated
  runs (×2, cache disabled on the second run), including the 43-test
  runtime-integration module (restart matrix, readiness-gated startup,
  persistence mandates, corruption refusals, operational replay).
- **Frozen Phase 3 intact**: 11/11 strategy blobs byte-identical to `13fdc7e`;
  SUB-18 manifest 13/13 sha256 pins match — re-verified BEFORE and
  AFTER the re-audit cycle by an independent script.
- **Cross-process deterministic replay**: order ids, fill ids, ledger
  head hashes, and the memory chain hash are bit-identical across
  fully independent processes (×2 invocations of the replay script).
- **Secret scan**: 0 hits across 309 tracked files (re-audit cycle
  re-scan; 10 pattern families); **0 real-token-shape
  strings across the full history on all refs** (`-S`/`-G` sweeps —
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
| ARCH-F1..F12 | 5 MEDIUM + 6 LOW + 1 INFO | **F1/F3/F4/F6 CORRECTED (P1) and CLOSED by the P2 re-audit (independently verified)** | Kill-switch reset unauthenticated (ARCH-F1 — human-principal-gated, AI refused, 8-test matrix); latent NameErrors (ARCH-F3/F4 — imports fixed, probes closed); dormant raw-hash contamination (ARCH-F6 — deterministic re-implementation, provider_timestamp excluded, H-1 containment preserved). Remaining OPEN (outside window, unchanged): purge/embargo defaults unsafe for future overlapping sequence windows (F8); walk-forward plan builder lacks a purge parameter (F12); risk violation chain lacks `verify()` (F2); + hygiene items (F5/F7/F9/F10/F11). RT-F5 (trip/reset audit records) remains OPEN — separate finding. |
| RT-F1..F15 | 3 HIGH + 4 MEDIUM + 8 LOW | **F7/F8/F13 CORRECTED (P1) and CLOSED by the P2 re-audit (independently verified)** | Risk gate + kill switch NOT wired into the paper order path (F1); `ReconciliationEngine` zero src callers (F2); `AuditLogger` never invoked (F3); no persistence in the execution domain (F4); order-vocabulary divergence (F6); CLI check-boundary inverted (F7 — verify semantics, exit 0); `ingest_from_file` dead path (F8 — live through FS-04/06/14 containment, honest classifier fallback); no model-loading path (F14); + F5/F9..F12/F15 unchanged (RT-F5 = trip/reset audit records, OPEN). Full register with evidence in `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` §12. Dispositions of the non-window findings UNCHANGED. |
| **BUG-001..009** | 3 CRITICAL + 1 HIGH + 2 MEDIUM + 3 LOW | **P2 VERDICTS: 001–007 & 009 CLOSED (independently re-verified); 008 PARTIAL** | All nine defects corrected in commit 1277331 and re-audited first-hand in P2: limit-order fills never through the limit (300-case property test); flip basis at the flip fill price (economics exact); signed netting (reductions/closes never trip the kill switch; sole production caller positive-only); status-aware reconciliation; AuditLogger deep-immutability (unkeyed re-forge = accepted threat model pending keyed-MAC custody decision); truthful 7-dimension CLI status; bar-order validation; 25-field deep-immutability migration (`pit/immutable.py`; runtime sweep 31/31 blocked; schemas.py quartet + strategy ×9 deferred by manifest/frozen rules — BUG-008 PARTIAL with registered follow-up); NaN fail-closed analytics. Full evidence tables: `P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` §6. |
| REAL-DATA / WP-12 / MODEL-APPROVAL / PAT-ROTATION | — | **HUMAN_DECISION_REQUIRED** | Real data source approval (candidate matrix ready); GitHub Actions CI (workflow spec ready, deliberately not installed); prediction registry approval owner; **rotate the chat-exposed GitHub PAT (5th exposure; re-verified STILL ACTIVE via API on 2026-10-09 during P2 — revoke immediately; one-off push use per operator instruction documented in `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` §6.3 and the P2 report §16)**. |
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
   2026-10-08).** P0 COMPLETE · P1 EXECUTED · **P2 EXECUTED — CONDITIONAL
   PASS** (`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md`: 15/16 findings
   CLOSED with independent verification; BUG-008 PARTIAL with registered
   rule-deferred residual; no regressions; frozen intact; P1+P2 commits
   pushed per the operator's explicit push instruction). The governing
   sequence from here: **P3 Stage-0 decision gate** (real data / WP-12 CI /
   H-1 — the same human decisions as items 1, 2 and 8; NOT AUTHORIZED until
   explicitly granted) → **P4 paper runtime +
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
9. **Rotate the GitHub PAT** (exposed in chat five times; re-verified STILL
   ACTIVE on 2026-10-09 during the P2 audit — see
   `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` §3 and
   `P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` §8) and
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
`P1_CORRECTION_WINDOW_REPORT.md` (P1 correction-window execution record —
16/16 findings corrected, evidence tables, remaining risks) ·
`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` (P2 independent re-audit
record — 15/16 CLOSED, BUG-008 PARTIAL, CONDITIONAL PASS verdict,
open-blocker register) ·
`PAPER_TRADING_READINESS_FINAL_REPORT.md` v2.0.0 (re-audit cycle record —
all 28 re-audit blockers verified + closed where authorized, 10-point
restart matrix, EXECUTION_STATE_SCHEMA, final verdict
BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY; v1.0.0 archived under `docs/`) ·
`docs/` runtime spec family (TRADING_RUNTIME_ARCHITECTURE /
TRADING_EVENT_CONTRACT / ORDER_LIFECYCLE_SPEC / PAPER_TRADING_SPEC /
RECONCILIATION_SPEC / KILL_SWITCH_SPEC / TRADING_LEDGER_SPEC /
PREDICTION_LEDGER_SPEC / DECISION_LEDGER_SPEC / DISASTER_RECOVERY_SPEC /
PAPER_READINESS_GATE — re-audit versions v2.0.0 where amended) ·

Read-only audit deliverable (maintained **outside** the repository, per the
audit's no-modification mandate): `AI_TRADING_LAB_ARCHITECTURE_READINESS_
AUDIT.md` — 12-section forensic report, A–X area survey, per-family
readiness tables (LSTM / Transformer / Ensemble / RL / Autonomous Trading),
and IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED with the sequenced path
that would change it.
