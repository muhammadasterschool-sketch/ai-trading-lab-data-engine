# MASTER DOCUMENTATION INDEX

> **Single source of truth for repository documentation.**
> Every documentation artifact in this repository is classified here by
> phase ownership, authority, status, and supersession relationship.

```text
Document Type:  Master documentation index (SSOT)
Phase:          Cross-phase (all phases)
Authority:      A — AUTHORITATIVE (this index is the documentation map of record)
Status:         CURRENT
Version:        1.7.0
Last Updated:   2026-10-09 (pre-paper readiness implementation executed: PAPER_TRADING_READINESS_FINAL_REPORT.md + 11 runtime specs + 3 governance decision records)
Supersedes:     none (first canonical index)
Superseded By:  —
Source Evidence: doc_discovery.py inventory (80 pre-existing docs), reference
                 graph (199 referrer files scanned), git log, PHASE_GOVERNANCE_
                 RECONCILIATION.md authority matrix
```

**Authority classification vocabulary** (normalization mandate §7):
- **A** — AUTHORITATIVE (current governing specification)
- **B** — CURRENT SUPPORTING (current, subordinate)
- **C** — AUDIT EVIDENCE (produced by audit/verification activity)
- **D** — HISTORICAL (retained to preserve project history)
- **E** — SUPERSEDED (no longer authoritative, retained for traceability)
- **F** — INCORRECT/CONTRADICTORY HISTORICAL CLAIM (preserved, corrected by
  supersession notices / the contradiction register)

**Naming decision (recorded per mandate §6):** No existing document was
renamed. Rationale: (1) `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md`,
`PHASE_4A1_IMPLEMENTATION_RECORD.md`, `docs/strategy_engine_design.md`, and
`tests/AUDIT_REPORT.md` are referenced by **source code and tests**
(`src/data_engine/pit/hashing.py`, `tests/test_pit.py`, `tests/test_pit_view.py`,
`tests/test_strategy.py`) — renaming them would require modifying runtime
code/tests, which the mandate forbids (§1.1, §15, §25 STOP condition);
(2) every historical document carries 2–27 inbound prose references forming
the forensic evidence chain — renaming would sever traceability cited in
commit messages and audit trails (§6); (3) §6 explicitly authorizes
preserving originals and creating clearly identified canonical/current
documents instead — **this index is that canonical document.** New documents
created from 2026-10-08 onward follow the mandate §4/§5 naming standards.

---

## Phase 0 — Foundation / Evidence

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_0_EVIDENCE_REAUDIT.md` | C | Historical | Phase 0 evidence re-audit (pre-4A.1 baseline verification) | superseded by later cycle audits for status; retained as evidence |

## Phase 1 — Contract / Security Remediation

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_1_CONTRACT_FORENSIC_AUDIT.md` | C | Historical | Phase 1 contract-level forensic audit | evidence of record |
| `AUDIT_PHASE1_REDTEAM.md` | D | Historical | Phase 1 source-level red-team audit | evidence of record |
| `PHASE1_SECURITY_REMEDIATION_REPORT.md` | D | Historical | Phase 1 security remediation record | evidence of record |

## Phase 2 — Baseline Architecture / Design Decisions

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE2_BASELINE_ARCHITECTURE_AUDIT.md` | C | Historical | Baseline architecture & security audit | evidence of record |
| `PHASE2_HUMAN_DESIGN_DECISION_MATRIX.md` | D | Historical | Human design decision matrix (Phase 2 gate) | evidence of record |
| `PHASE2_HUMAN_DESIGN_DECISION_MATRIX_REDTEAM.md` | D | Historical | Red-team review of the Phase 2 decision matrix | evidence of record |
| `PHASE_2_IMPLEMENTATION_AUTHORIZATION_FORENSIC.md` | C | Historical | Phase 2 implementation-authorization chain forensics (A1–A7 chain origin) | still cited by reconciliation §8 |
| `docs/quant_engine.md` | B | Current supporting | Phase 2 deterministic quant engine design documentation | — |

## Phase 3 — Strategy Engine (FROZEN)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `docs/strategy_engine.md` | B | Current supporting | Strategy & backtest engine overview (frozen Phase 3 behavior) | — |
| `docs/strategy_engine_design.md` | B | Current supporting — **FROZEN DESIGN DOCUMENT, bytes must not be reformatted** | Final Phase 3 design document (referenced by tests) | — |
| `tests/AUDIT_REPORT.md` | C | Historical | Phase 3 strategy engine comprehensive audit (audit evidence located under `tests/`, deliberately preserved in place) | evidence of record |
| `PHASE3_BLOCKER2_D4_ANALYSIS_AUDIT.md` | D | Historical | Blocker #2 D4 analysis audit | evidence of record |
| `PHASE3_BLOCKER2_D4_CORRECTED_ARTIFACT_AUDIT.md` | D | Historical | Corrected artifact audit for D4 | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_APPROVAL_RECORD.md` | D | Historical | Human approval record (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md` | D | Historical | Human design approval (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md` | D | Historical | Human design decision matrix (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` | D | Historical | Final D4 methodology | evidence of record |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md` | D | Historical | D4 numerical analysis (original) | superseded by _CORRECTED variant; preserved |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS_CORRECTED.md` | D | Historical | D4 numerical analysis (corrected) | evidence of record |
| `PHASE3_BLOCKER2_DESIGN_AMENDMENT_DRAFT.md` | D | Historical | Blocker #2 design amendment draft | superseded by DESIGN_APPROVAL; preserved |
| `PHASE3_BLOCKER2_DESIGN_APPROVAL.md` | D | Historical | Blocker #2 design approval | evidence of record |
| `PHASE3_BLOCKER2_DESIGN_REVIEW.md` | D | Historical | Blocker #2 design review | evidence of record |
| `PHASE3_BLOCKER2_FINAL_DECISION_MATRIX.md` | D | Historical | Blocker #2 final decision matrix | evidence of record |

## Phase 4A — Multi-Asset PIT Design (pre-correction)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `DESIGN_REVIEW_PHASE_4A_MULTI_ASSET_PIT.md` | E | Superseded | Original 4A multi-asset PIT design review | superseded by 4A.1 architecture correction |
| `DESIGN_GATE_REPORT.md` | E | Superseded | 4A decision-gate report | superseded by 4A.1 cycle |
| `PHASE_4A_FINAL_ARCHITECTURE_SPEC.md` | E | Superseded | 4A final architecture spec (pre-correction) | superseded by 4A.1 spec family |

## Phase 4A.1 — Architecture Correction (remediation cycle)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | E | Superseded (executed); governance practice retained | The 4A.1 remediation spec of record (GOV rules, dispositions). **Name pinned by src/tests references — never rename** | execution mandate discharged; closure evidence = IMPLEMENTATION_RECORD + ZAI_PHASE_4A1_FINAL_STATUS |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md` | E | Superseded | Earlier correction spec | superseded by AUTHORITATIVE_REMEDIATION_SPEC |
| `PHASE_4A1_IMPLEMENTATION_SPEC.md` | E | Superseded (historical) | Implementation specification (spec era) | superseded by closure evidence |
| `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` | E | Superseded (historical) | Blocker resolution specification | superseded by AUTHORITATIVE_REMEDIATION_SPEC + closure |
| `PHASE_4A1_IMPLEMENTATION_RECORD.md` | B | Current supporting — **authoritative 4A.1 closure record; manifest pinned by SUB-18 + final_gate_verify.py; name pinned by tests** | 4A.1 implementation record incl. 13-file sha256 manifest | — |
| `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md` | D | Historical | Final architecture gate decision record | closure evidence governs |
| `PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md` | C | Historical | Implementation forensic audit (spec era) | evidence of record |
| `PHASE_4A1_FORENSIC_RECONCILIATION.md` | D | Historical | Spec-era forensic reconciliation | evidence of record |
| `PHASE_4A1_SPEC_RECONCILIATION.md` | D | Historical | Specification reconciliation | evidence of record |
| `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` | C | Historical | Pre-implementation independent re-audit (RE-AUDIT_FAIL era) | superseded by closure; preserved |
| `PHASE_4A1_POST_REAUDIT_CORRECTION_REPORT.md` | D | Historical | Post-re-audit documentation correction pass | evidence of record |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` | D | Historical | Correction checklist & diff plan | evidence of record |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` | D | Historical | Correction report | evidence of record |
| `PHASE_4A1_MANDATORY_BLOCKER_CLOSURE_EXECUTION_PLAN.md` | D | Historical | PLAN_ONLY closure execution plan (executed under authorization A4) | superseded by execution record |
| `PHASE_4A1_PRE_IMPLEMENTATION_PLAN_INTEGRITY_GATE_REPORT.md` | D | Historical | Pre-implementation plan integrity gate | evidence of record |
| `PHASE_4A1_DESIGN_LOCK_RECORD.md` | D | Historical — FAILED attempt, never rewritten | Design Lock attempt #1 | gate SUPERSEDED by operator authorization (CR-04) |
| `PHASE_4A1_DESIGN_LOCK_REATTEMPT_RECORD.md` | D | Historical — FAILED attempt | Design Lock re-attempt #2 | as above |
| `PHASE_4A1_DESIGN_LOCK_FINAL_REATTEMPT_REPORT.md` | D | Historical — FAILED attempt | Design Lock final re-attempt #3 | as above |
| `PHASE_4A1_DL_D1_AUTHORIZATION_IMPACT_ASSESSMENT.md` | D | Historical | DL-D1 authorization & impact assessment | evidence of record |
| `PHASE_4A1_DL_D1_HUMAN_AUTHORIZATION_GATE_REPORT.md` | D | Historical | DL-D1 human-authorization decision gate report | evidence of record |
| `PHASE_4A1_DL_D1_OPTION_A_DECISION_RECORD.md` | D | Historical — decision still standing | Human decision: CRLF Option A | condition root-caused (CR-07) |
| `PHASE_4A1_DL_D5_RED_TEAM_REPORT.md` | D | Historical | DL-D5 red-team report | evidence of record |
| `PHASE_4A1_DL_D5_TARGETED_CORRECTION_REPORT.md` | D | Historical | DL-D5 targeted correction | evidence of record |
| `PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md` | D | Historical | 4A.1-era multi-AI architecture planning | superseded by construction-era blueprint |
| `PHASE_4A1_MULTI_AI_CONSTRUCTION_BASELINE.md` | D | Historical | 4A.1-era construction baseline / document map | superseded by MASTER_DOCUMENTATION_INDEX (this index) |
| `PHASE_4A1_OPTION_A_CLOSURE_STATE_RECONCILIATION.md` | D | Historical | Option A closure-state reconciliation | superseded by cycle reconciliation |
| `PHASE_4A1_BLOCKER_1_ACCEPTANCE_TEST_REPORT.md` | C | Historical | Blocker 1 acceptance test report | evidence of record |
| `PHASE_4A1_BLOCKER_1_MANIFEST_INTEGRITY_REVIEW.md` | C | Historical | Blocker 1 manifest integrity review | evidence of record |
| `PHASE_4A1_BLOCKER_1_OWNERSHIP_IMPLEMENTATION_REPORT.md` | C | Historical | Blocker 1 ownership implementation report | evidence of record |
| `ZAI_PHASE_4A1_FINAL_STATUS.md` | B | Current supporting | 4A.1 closure status report (8/8 blockers CLOSED, 563 tests, 9 commits) — re-verified post-hoc | — |
| `ZAI_PHASE_4A1_STATE_REAUDIT.md` | C | Audit evidence | Independent re-verification of the 4A.1 final status claims | — |

## Phases 4A.2, 4A.3, 4A.4, 5, 6, 7, 8, 9, 10, 11, 11P, 12

**No phase-owned standalone documents exist for these phases.** Their
authoritative documentation lives in the cross-phase implementation records
(next section). This is intentional: each phase was constructed and closed
within a single cycle whose provenance is recorded cycle-wide, not per-phase.
Any future phase-owned document SHALL follow the naming standard
(`PHASE_04A2_<SUBJECT>.md`, …, `PHASE_12_<SUBJECT>.md`).

## Phase PRED — Prediction & Crash Intelligence

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AI_TRADING_LAB_PREDICTION_CRASH_INTELLIGENCE_SPEC.md` | A | Current — authoritative architecture spec for the prediction layer (v1.1.0: closure extension §17) | Prediction & crash intelligence contracts, invariants, data policy, governance | — |
| `PREDICTION_INTELLIGENCE_IMPLEMENTATION_REPORT.md` | B | Current supporting — construction record (v1.0.0) + closure addendum (v1.1.0, §7) | Implementation record (31 modules, 270 prediction tests, honest coverage assessment) | — |
| `PREDICTION_VALIDATION_EVALUATION_REPORT.md` | B | Current supporting — closure-cycle validation record | §26 claim-category separation, PRED-F1/F2/F3 closure evidence, blocker closure table | — |
| `PREDICTION_REDTEAM_ADVERSARIAL_REPORT.md` | B | Current supporting — executed adversarial matrix evidence | 45 attacks, six categories, matrix hash `preda.8366…`, all defended | — |
| `PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md` | B | Current supporting — governing data policy companion | Dataset epistemic states, quality gates, source governance, approval templates | — |
| `WP_12_CI_IMPLEMENTATION_SPEC.md` | B | Current supporting — PENDING HUMAN AUTHORIZATION | Implementation-ready GitHub Actions workflow spec; WP-12 = HUMAN_DECISION_REQUIRED | — |

## Phase RT — Final Integrated Runtime (runtime-integration era)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` | B | Current — audit baseline of record for the FINAL INTEGRATED RUNTIME mandate (§2 FIRST TASK; v1.0.0) | Runtime-integration audit: component inventory, dependency/runtime/execution graphs, ownership tables, missing connections MC-1..12, RT-F1..15 findings, PHASE A–AF implementation order | — |
| `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` | A | Current — **authoritative consolidated bug register** for the pre-paper phase (bug-forensic mandate §26; v1.0.0) | Pre-paper forensic: RT-F1..15 + MC-1..12 + ARCH-F1..4 re-verification record; NEW register BUG-001..009 (3 CRITICAL: limit-order price violation, position-flip basis, additive risk netting); 11/11 executable reproductions; prepared fixes (§5) BLOCKED_BY_AUTHORIZATION; PAPER_READY = NO (PAPER-BLK-1..10) | — |

The remaining §61 spec documents (`TRADING_RUNTIME_ARCHITECTURE.md`, `TRADING_EVENT_CONTRACT.md`, `ORDER_LIFECYCLE_SPEC.md`, `PAPER_TRADING_SPEC.md`, …) are deliberately NOT created until their implementing phase lands (audit-first discipline; §61 "only where needed").

## Cross-Phase Implementation Records

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md` | B | Current supporting — authoritative for the 4A.2→graduation cycle | Provenance + authorization #2 record (12 commits, 692 tests) | — |
| `PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` | B | Current supporting — authoritative for the discovery/knowledge/benchmarks/lifecycle cycle | Provenance record (5 commits, 789 tests) | — |
| `ZAI_FULL_ROADMAP_COMPLETION_STATUS.md` | B | Current supporting | Roadmap completion status (4A.2→graduation delivery summary) | — |

## Cross-Phase Governance

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_GOVERNANCE_RECONCILIATION.md` | A | Current — authoritative construction-era reconciliation (12 contradictions classified, authorization chain A1–A7, SSOT hierarchy) | Governance reconciliation of the construction era | — |
| `H1_FORMAL_DECISION_ANALYSIS.md` | B | Current — decision-gate artifact; H-1 = OPEN / HUMAN-REVIEWED / CONTAINED; **awaiting human ratification** | H-1/F-04 formal decision analysis | — |
| `ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` | B | Current | Enhancement Mandate v2.0 registration + 17-package gap analysis | — |
| `GOVERNANCE_DOCUMENT_CONTRADICTION_REGISTER.md` | A | Current — the live contradiction register (carries CR-01..CR-12 forward + documentation-era entries) | Contradiction register of record | supersedes the reconciliation's inline CR table for tracking purposes (original preserved) |

## Cross-Phase Audits

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AUDIT_SELF_INTEGRITY_REPORT.md` | D | Historical | Pre-4A.1 self-integrity audit | evidence of record |
| `AUDIT_STATE_SNAPSHOT.md` | D | Historical | Pre-4A.1 state snapshot | evidence of record |
| `REGRESSION_BASELINE_FORENSIC.md` | C | Historical | Baseline regression forensics | evidence of record |
| `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` | C | Audit evidence (25 sections; scope nuance CR-06 recorded) | Week-end full forensic inspection | — |
| `ZAI_CURRENT_REPOSITORY_STATE.md` | C | Audit evidence (point-in-time STEP 0 snapshot) | Mandate v1.0 STEP 0 discovery report | superseded for "current state" by the progress brief; preserved as evidence |
| `FINAL_FULL_REPOSITORY_FORENSIC_AUDIT.md` | C | Audit evidence | Mandate Phase 31 forensic audit | — |
| `ZAI_DEFECT_REGISTER.md` | B | Current supporting — live register (1 HIGH contained, 5 MEDIUM, 8 LOW) | Defect register of record | — |
| `AUDIT_DOCUMENTATION_LINKS.md` | C | Current audit evidence | Documentation link audit (this cycle) | — |
| `AUDIT_DOCUMENTATION_NORMALIZATION.md` | C | Current audit evidence | Documentation normalization final report (this cycle) | — |

## Cross-Phase Security

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` | C | Current audit evidence — P0 deliverable of the staged readiness program (v1.0.0) | Credential exposure forensic (4th chat exposure, value withheld, verified STILL ACTIVE via API); full tree/config/history sweeps (0 credentials); push hygiene record; staged readiness program P0–P8 registration (P0 COMPLETE, P1 correction window AWAITING HUMAN AUTHORIZATION); NO TRADING IMPLEMENTATION PERFORMED | — |
| `P1_CORRECTION_WINDOW_REPORT.md` | C | Current audit evidence — P1 execution record (v1.0.0): 16/16 authorized findings corrected with objective evidence (1141/1141 tests x3, 0/17 AFTER-probes defective, 31/31 BUG-008 mutations blocked, frozen gates 11/11 + 13/13); closure verdicts deferred to the P2 re-audit; local commits 1277331 + docs (NOT pushed per rule 11) | Correction-window execution record for BUG-001..009 + ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 | — |
| `P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` | C | Current audit evidence — P2 independent re-audit record (v1.0.0, READ-ONLY): every P1 correction re-verified first-hand (diffs + probes + 1141/1141 x2 + 8 category subsets); **verdicts 15 CLOSED · 1 PARTIAL (BUG-008 residual rule-deferred) · 0 OPEN · 0 REGRESSED; P2 VERDICT: CONDITIONAL PASS**; frozen integrity re-verified blob-level; security scans 0; exposed PAT re-verified STILL ACTIVE (exposure #5 — rotation OPEN); OBS-1 mode-sweep recorded; open-blocker register (CRED-ROTATION / BUG-008-RESIDUAL / KEYED-MAC / PAPER-BLK-1..6 / P3 Stage-0 / OBS-1); P3 NOT AUTHORIZED | Independent re-audit of the P1 correction window (staged readiness program stage 2) | — |
| `PAPER_TRADING_READINESS_FINAL_REPORT.md` | C | Current cycle evidence — pre-paper readiness implementation final report (v1.0.0): authoritative runtime built+verified (1,335/1,335 tests ×2; frozen 11/11+13/13; security 0); RT-F/ARCH-F closure table; BUG-008 DEFERRED-BY-FROZEN-CONTRACT; **PAPER_READY = FALSE** (BLOCKED_ON_REAL_DATA; H-1/CI human decisions; PAT rotation) | Pre-paper readiness implementation cycle (operator-authorized) | — |
| `CURRENT_REPOSITORY_PAPER_READINESS_BRIEF.md` | B | Current supporting — pre-implementation paper-readiness snapshot at f61e1ee (gap register this cycle closed) | Orientation snapshot (superseded in part by the final report above) | — |
| `H1_RATIFICATION_DECISION_RECORD.md` | A | AUTHORITATIVE governance decision record (v1.0.0): H-1 ratification request with signature block — **HUMAN_DECISION_REQUIRED** (no approval fabricated) | H-1/F-04 containment governance | — |
| `REAL_DATA_READINESS_CONTRACT.md` | A | AUTHORITATIVE data contract (v1.0.0): full §9 pipeline + dataset record schema + §10 quality gates — **BLOCKED_ON_REAL_DATA** (0 verified datasets; never invented) | Real-data readiness gate | — |
| `CI_WP12_GATE_DECISION_RECORD.md` | A | AUTHORITATIVE governance decision record (v1.0.0): WP-12 CI authorization request with signature block — **HUMAN_DECISION_REQUIRED** (.github/ intentionally absent) | CI gate governance | — |
| `docs/TRADING_RUNTIME_ARCHITECTURE.md` | A | AUTHORITATIVE runtime spec (v1.0.0): the one orchestration path, component map, operating states, bar-processing order, determinism | Runtime implementation | — |
| `docs/TRADING_EVENT_CONTRACT.md` | A | AUTHORITATIVE contract spec (v1.0.0): identity rules/prefix map, PredictionArtifact/Decision/TradePlan/ExitRecord schemas, correlation threading | Runtime contracts | — |
| `docs/ORDER_LIFECYCLE_SPEC.md` | A | AUTHORITATIVE OMS spec (v1.0.0): 14-state machine, idempotency, partial fills, TTL, execution realism | OMS implementation | — |
| `docs/PAPER_TRADING_SPEC.md` | A | AUTHORITATIVE paper spec (v1.0.0): structural isolation, persistence, P&L, replay, E2E scope protection | Paper runtime | — |
| `docs/RECONCILIATION_SPEC.md` | A | AUTHORITATIVE reconciliation spec (v1.0.0): multi-fill three-way reconcile, mismatch = STOP_NEW_ORDERS | Runtime reconciliation | — |
| `docs/KILL_SWITCH_SPEC.md` | A | AUTHORITATIVE kill-switch spec (v1.0.0): 7 scopes, human-gated reset, critical-scope authorization | Runtime safety | — |
| `docs/TRADING_LEDGER_SPEC.md` | A | AUTHORITATIVE ledger spec (v1.0.0): 9 hash-chained ledgers, event schema, NO_TRADE ledgering | Runtime ledgers | — |
| `docs/PREDICTION_LEDGER_SPEC.md` | A | AUTHORITATIVE prediction-ledger spec (v1.0.0): operational prediction records + research-layer relationship | Runtime prediction ledger | — |
| `docs/DECISION_LEDGER_SPEC.md` | A | AUTHORITATIVE decision-ledger spec (v1.0.0): decision records incl. NO_TRADE with blocked conditions | Runtime decision ledger | — |
| `docs/DISASTER_RECOVERY_SPEC.md` | A | AUTHORITATIVE recovery spec (v1.0.0): restore→verify→reconcile→resume-or-halt, corruption detection, runbook | Runtime recovery | — |
| `docs/PAPER_READINESS_GATE.md` | A | AUTHORITATIVE readiness spec (v1.0.0): 23 fail-closed gates, evidence classes, current FALSE verdict | Readiness gate | — |
| `FILESYSTEM_SECURITY_FORENSIC_AUDIT.md` | E | Historical audit evidence (pre-B8 remediation findings) | Filesystem security forensic audit | remediation recorded in 4A.1 closure; preserved as evidence |
| `HASH_FORENSIC_AUDIT.md` | E | Historical audit evidence — pre-remediation verdicts (incl. Candle.to_hash CONTAMINATED); current interpretation: H-1 OPEN/CONTAINED | Hash forensic audit | interpretation superseded by `H1_FORMAL_DECISION_ANALYSIS.md`; evidence preserved |
| `PHASE_OWNERSHIP_FORENSIC_AUDIT.md` | E | Historical audit evidence | Phase ownership forensics | superseded by construction records; preserved |

## Reproducibility

No dedicated standalone document. Reproducibility controls are documented
in: `PHASE_4A1_IMPLEMENTATION_RECORD.md` (determinism gates),
`PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` (cross-process
identity probes), and `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` (§ frozen
behavior / determinism). Future dedicated documents SHALL use
`REPRODUCIBILITY_<SUBJECT>.md`.

## Acceptance

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AI_TRADING_LAB_FINAL_ACCEPTANCE_AUDIT.md` | C | Current audit evidence — verdict READY_WITH_FINDINGS (NOT COMPLETE) | Mandate Phase 45 final acceptance audit | — |

## Master / System Documents

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` | A | Current (architecture normative) / **STALE (§2 status table + L1751 status lines — see contradiction register)** | Construction-era full-system blueprint (60 domains) | status superseded by implementation records; architecture retained |
| `MASTER_ENHANCEMENT_HARDENING_MANDATE.md` | A | Current — enhancement-era authority (50 sections, 17 work packages; execution NOT started) | Enhancement/hardening mandate v2.0 (verbatim, operator-issued) | — |
| `MASTER_PHASE_STATUS_REPORT.md` | F | **INCORRECT/CONTRADICTORY HISTORICAL CLAIMS** — 2026-09-30 snapshot ("NO PHASE MAY ADVANCE", NOT_AUTHORIZED statuses) now stale; preserved per mandate §7-F | Audit-era phase/blocker status snapshot | superseded by `PHASE_GOVERNANCE_RECONCILIATION.md` + implementation records |
| `MASTER_DOCUMENTATION_INDEX.md` | A | Current — **THIS DOCUMENT** | Documentation SSOT index | — |
| `README.md` | B | Current supporting | Package orientation, module map, phase map | — |
| `ZAI_REPOSITORY_PROGRESS_BRIEF.md` | B | Current supporting — the repository progress brief ("what has been done so far") | One-page orientation: timeline, current state, open items | — |
| `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` | B | Current — §76-required living status document for the Autonomous Intelligence + Full System Expansion mandate (v1.0.0 baseline: §78 audit) | Autonomy levels L0–L8, capability matrix, duplicate-system audit, dependency graph, blocker table BLK-1..15, test/data/model inventories, authorization state | — |
| `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` | B | Current — runtime-integration audit authority for the FINAL INTEGRATED RUNTIME mandate (see Phase RT section above) | §2 repository audit: the map from component library to governed trading runtime | — |
| `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` | A | Current — authoritative bug register for the pre-paper phase (see Phase RT section above) | Consolidated pre-paper forensic: prior-register verification + BUG-001..009 + paper-readiness blockers PAPER-BLK-1..10 | — |

---

## Ownership rules (mandate §9)

1. Every phase-owned document above has exactly one primary phase owner.
2. Cross-phase documents carry cross-phase classifications only
   (GOVERNANCE_ / AUDIT_ / SECURITY_ / REPRODUCIBILITY_ / ACCEPTANCE_ /
   MASTER_ or pre-existing names preserved under the §6 traceability rule).
3. No document simultaneously claims two phase owners. The pre-normalization
   legacy names (`PHASE_4A1_…`, `PHASE3_…`, `PHASE2_…`, `ZAI_…`) are retained
   as-is per the recorded rename decision; their phase ownership is fixed by
   THIS index, not by their filename prefix.

## How to use this index

- **"What is the current truth about X?"** → start at
  `ZAI_REPOSITORY_PROGRESS_BRIEF.md` (orientation) → this index (authority
  map) → the A/B-classified documents it points to.
- **"Is a historical claim still valid?"** → check
  `GOVERNANCE_DOCUMENT_CONTRADICTION_REGISTER.md`.
- **"Which document governs frozen Phase 3?"** → `docs/strategy_engine_design.md`
  (design, bytes frozen) + `PHASE_4A1_IMPLEMENTATION_RECORD.md` (freeze
  verification manifest).
