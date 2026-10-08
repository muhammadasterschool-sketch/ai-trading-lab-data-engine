# ZAI ENHANCEMENT MANDATE REGISTRATION & GAP ANALYSIS

```text
Document Type:  Mandate registration record
Phase:          Cross-phase (enhancement era)
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT — execution NOT started
Version:        1.0.0
Last Updated:   2026-10-08 (doc-control header added during documentation
                normalization; content unchanged)
Supersedes:     none
Superseded By:  —
Source Evidence: registration-time verification recorded in §3
```

**Document type:** Mandate registration record (evidence-backed)
**Registered:** 2026-10-08 (PKT), channel zai-web
**Mandate:** MASTER_ENHANCEMENT_HARDENING_MANDATE.md (v2.0, 50 sections,
17 mandatory work packages) — filed verbatim in this commit
**Registration-time HEAD:** `3084dcb` (pre-registration) · both branches synced
**Execution status:** **REGISTERED — NOT EXECUTED**

---

## 1. Purpose and scope of this document

This document registers the Enhancement, Hardening & Construction Mandate
(v2.0) as a governing authority in the repository, records its relationship to
existing governance documents, and produces the **grounded gap analysis**
between the mandate's 17 mandatory work packages and the verified current
implementation. It deliberately does NOT claim any of the 17 packages as
implemented, per the mandate's own §0.5 (No Fake Completion) and §46
(evidence-backed status model).

The mandate's §1 (Initial Repository Discovery) has been satisfied at
registration time by direct verification (not assumption from prior reports):
git ground truth, package structure, module-level inspection of quality/
evidence/risk/hermes/infra modules, and re-execution of the forensic gate and
full test suite (results in §3). The existing
`ZAI_CURRENT_REPOSITORY_STATE.md` (STEP 0 of the prior mandate) remains the
baseline current-state evidence report; the mandate's execution cycle will
re-run full discovery before modifying anything.

## 2. Governance affirmations (binding, restated from mandate §0)

The following are affirmed at registration and bind all future execution:

1. **Frozen Phase 3 (§0.1).** The seven frozen methods
   (`Candle.to_hash()`, `ProvenanceRecord.to_hash()`, `StrategySpec.to_hash()`,
   `BacktestProvenance.compute_result_hash()`, `BacktestProvenance.to_hash()`,
   `BacktestConfig._compute_config_hash()`, `BacktestEngine._compute_dataset_hash()`)
   remain byte-for-byte frozen. Any new identity model goes behind a Phase 4+
   boundary. Registration-time verification: 11/11 strategy blobs
   byte-identical to `13fdc7e` (forensic gate re-run, §3).
2. **H-1 / F-04 containment (§0.2).** H-1 remains **OPEN / HUMAN-REVIEWED /
   CONTAINED** (see `H1_FORMAL_DECISION_ANALYSIS.md`, Option A
   recommendation, awaiting human ratification). The dormant path
   `ingestion.py` → `provider.py` is unchanged. No Phase 3 amendment is
   granted by this mandate.
3. **Live trading prohibition (§0.3).** `LIVE TRADING AUTHORIZATION:
   NOT GRANTED`. `LiveAuthorizationGate` remains deny-by-default with
   humans-only token registry (starts empty). No broker/MT5/network code may
   be introduced. Paper trading and simulation only.
4. **No governance bypass (§0.4).** Tests/code/reports/AI output are never
   authorization. Blockers close only through governance gates.
5. **No fake completion (§0.5).** Every package requires architecture →
   contract → implementation → tests → adversarial tests → integration →
   reproducibility → documentation → evidence → regression → audit before
   any COMPLETE claim.

## 3. Registration-time ground truth (directly verified)

| Check | Result |
|---|---|
| HEAD / branch | `3084dcb` on `phase-4a/4a1-architecture-correction` |
| Remote | github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine |
| GitHub branch state | `main` = phase branch = `3084dcb` (ls-remote verified) |
| Working tree | 0 content delta (mode-only environment artifacts only, reverted before commit) |
| Untracked files | 0 at registration commit |
| Test suite | 789 passed (re-run in registration cycle) |
| Forensic gate | 5/5 PASS — frozen 11/11, SUB-18 manifest 13/13, secrets 0 hits, untracked empty, tree clean |
| Frozen Phase 3 | 11/11 strategy blobs byte-identical to `main@13fdc7e` |
| Live boundary | deny-by-default verified (prior cycles; no live code introduced since) |
| Package layout | `src/data_engine/` — 15 packages + core modules (§4 anchors) |
| CI | `.github/` ABSENT — no CI gates exist (WP-12 gap confirmed) |

## 4. Gap analysis — 17 mandatory work packages vs verified current state

Status vocabulary: **ABSENT** (no meaningful implementation) ·
**PARTIAL** (real anchored implementation exists but does not satisfy the
mandate's full contract) · **SATISFIED** (meets mandate contract with
evidence). No package is SATISFIED today.

| # | Work package | Status | Current anchors (verified) | Principal gaps vs mandate |
|---|---|---|---|---|
| 1 | Market Data Realism & Quality Engine | PARTIAL | `quality_report.py` (missing/duplicate/out-of-order/timezone counts), `quarantine.py` (isolated records), `validation.py` + `data_blocked.py` (DATA_QUALITY_BLOCKED fail-stop), `actions/` (corporate-action discontinuities) | Full classifier taxonomy (VALID/DEGRADED/SUSPICIOUS/INVALID/UNKNOWN), 21-detector coverage (spreads, stale prices, session/holiday, provider disagreement, source corruption, revisions), per-decision evidence |
| 2 | Strategy Novelty & Anti-Overfitting Engine | PARTIAL | `research_validation/` (bias/leakage/overfitting detectors, walk-forward, robustness plateau/regimes, BH multiple-testing), `experiment_registry/` duplicate-identity rejection | Dedicated novelty layer: duplicate-strategy detection, parameter/feature/signal similarity, family clustering, data-snooping, identity tracking fields |
| 3 | Experiment Lineage Graph | PARTIAL | `experiment_registry/` (`ExperimentIdentity pit4x.`, reproducibility verdicts), `provenance.py` + frozen `strategy/provenance.py`, PIT identity chain | Full Dataset→…→Decision graph, immutable-after-completion semantics, versioned corrections, lineage query API |
| 4 | AI Agent Provenance | PARTIAL | `hermes/` (hash-chained agent audit, deterministic provider, dispatch-time refusal), `knowledge/` MODEL_OUTPUT source class with authoritative() exclusion | agent_id/version, model_provider/name/version, prompt/template identity, input/output artifact hashes, confidence, human-authorization state |
| 5 | AI Model Drift / Model Regression | **ABSENT** | — | Entire framework: drift detectors, baseline suites, promotion gates |
| 6 | Market Regime Engine | PARTIAL | `research_validation/robustness.py` (regime-conditioned validation) | Versioned regime identities, recorded methodology, historical reconstruction, no-future-leakage guarantees, confidence exposure |
| 7 | Market Microstructure / Execution Realism | PARTIAL | `paper/simulator.py` (latency/spread/impact/participation realism), `paper/gateway.py` | Backtest-side execution realism separation; degraded-mode marking when data absent; fill/queue/financing models |
| 8 | Portfolio Intelligence | PARTIAL | `risk/portfolio.py` (exposure, inverse-vol allocation with preconditions), `risk/engine.py` hard limits | Correlation/concentration/factor/sector/regime exposure, drawdown interaction, strategy correlation, portfolio-level NO-TRADE |
| 9 | Multi-Level Kill Switch | PARTIAL | `risk/engine.py` single kill switch (trip/active, `KillSwitchActiveError`, hash-chained violations) | 7-level hierarchy (strategy/portfolio/system/data-integrity/execution/security/AI), per-level independence, authorized recovery procedures |
| 10 | Disaster Recovery | PARTIAL | `infra/observability.py` (tamper-fail-closed checkpoints, hash chains) | Backup/restore TESTED (not just created), RPO/RTO, registry/evidence restoration, rollback, safe startup/shutdown, degraded mode |
| 11 | Reproducible Environment Fingerprint | PARTIAL | `infra/` reproducibility verifier (RNG detection), `uv.lock`, deterministic identity hashes throughout | Composed deterministic fingerprint (Python/OS/packages/lock/revision/config/schemas), cross-environment equivalence API |
| 12 | GitHub CI Quality Gates | **ABSENT** | — (`.github/` does not exist) | Full fail-closed CI: tests, frozen-phase3 protection, secret scan, determinism, subprocess reproducibility, mutation, docs consistency |
| 13 | NO-TRADE First-Class Decision Model | PARTIAL | `discovery/` ExecutionEligibility fail-closed chain (authorization always NOT granted → NO TRADE), `data_blocked.py`, lifecycle test NO TRADE at 10 boundaries | Reason-coded NO_TRADE decision records (15 reasons), decision evidence/timestamp/identity/risk/governance state capture |
| 14 | Evidence Score | PARTIAL | `evidence.py` EvidenceProvenance (REAL/SYNTHETIC/SIMULATED/UNKNOWN, `is_strong_evidence()`) | Multi-dimension evidence scoring framework (15 factors), profiles per conclusion, no single-metric dominance |
| 15 | Strategy Lifecycle / Retirement | PARTIAL | `paper/evaluation.py` (graduation/retirement, 30-day rule), `discovery/` candidate states, lifecycle test REJECTION ending | Formal 9-state machine (DISCOVERED→…→RETIRED) with deterministic transition rules and evidence per transition |
| 16 | System Truth / Evidence Layer | PARTIAL | `knowledge/` (5 record classes, source typing, humans-only HUMAN_DECISION, versioned conclusions) | Unified assertion classification (OBSERVED/VERIFIED/DERIVED/ASSUMED/UNKNOWN/CONTRADICTED/BLOCKED), doc-vs-code contradiction surfacing, Hermes anti-hallucination queries |
| 17 | Operator Control Plane | **ABSENT** | — | Authorization-aware operator API: health/quality/regime/exposure/risk/kill-switch/evidence/audit views, auditable controls |

**Summary: 3 ABSENT (WP-5, WP-12, WP-17) · 14 PARTIAL · 0 SATISFIED.**

Adjacent mandate areas with substantial existing implementation (to be
verified/hardened, not built from zero): §3 PIT hardening (Phase 4A.1 closed,
8/8 blockers, mutation gate 15/15), §21 security (`security.py` containment,
audit trail), §22 knowledge (`knowledge/`), §23 Hermes (`hermes/`), §25 paper
trading (`paper/`), §26 30-day evaluation (`paper/evaluation.py` structural
rule), §29 adversarial testing (`tests/test_redteam.py`, mutation gate,
subprocess tests), §31 performance (`benchmarks/`).

## 5. Relationship to existing governance documents

- `MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` — superseded as
  current-status authority by the reconciliation (see
  `PHASE_GOVERNANCE_RECONCILIATION.md`); its construction sequence is COMPLETE.
- `PHASE_GOVERNANCE_RECONCILIATION.md` — remains the authoritative
  reconciliation for the construction era; this mandate opens the
  **enhancement era** on top of it without altering any of its conclusions.
- `H1_FORMAL_DECISION_ANALYSIS.md` — unchanged; H-1 ratification remains a
  pending human decision. This mandate's §0.2 reaffirms containment.
- `ZAI_DEFECT_REGISTER.md` — remains open (1 HIGH contained, 5 MEDIUM,
  8 LOW). Enhancement-era fixes (e.g., F-11) will be registered there and in
  the mandate-era register required by §36.
- Prior implementation records (`PHASE_4A1_…`, `PHASES_4A2_TO_…`,
  `PHASES_DISCOVERY_TO_…`) — historical evidence, not superseded.

## 6. Execution protocol (when authorized)

1. Full §1 discovery re-run (fresh, not from reports) → update
   `ZAI_CURRENT_REPOSITORY_STATE.md`.
2. §2 governance reconciliation delta for the enhancement era.
3. Work packages in dependency order — recommended: WP-12 (CI gates first,
   protects everything after) → WP-13 (NO-TRADE decision model, the system's
   spine) → WP-1 (data quality) → WP-16 (truth layer) → WP-14 (evidence
   score) → WP-3 (lineage) → WP-4/WP-5 (AI provenance, drift) → WP-6
   (regime) → WP-7 (microstructure) → WP-8 (portfolio) → WP-9 (kill-switch
   hierarchy) → WP-10 (DR) → WP-11 (fingerprint) → WP-15 (lifecycle) →
   WP-17 (operator plane) → integration: §40 autonomous lifecycle test →
   §41–§45 audits and final acceptance.
4. Per package: Inspect → Design → Implement → Test → Adversarial Test →
   Integrate → Document → Verify (§50); frozen Phase 3 verification after
   every commit batch (§32); STOP conditions honored (§47).
5. Final deliverable of execution: `FINAL_ENHANCEMENT_VERIFICATION_REPORT.md`
   (§45). **Not produced at registration** — producing it now would be fake
   completion.

## 7. Status block

```text
MANDATE:            MASTER_ENHANCEMENT_HARDENING_MANDATE.md (v2.0)
REGISTRATION:       COMPLETE (this document, filed with the verbatim mandate)
EXECUTION:          NOT STARTED
WORK PACKAGES:      0/17 SATISFIED (3 ABSENT, 14 PARTIAL)
FROZEN PHASE 3:     VERIFIED BYTE-IDENTICAL AT REGISTRATION (11/11)
H-1:                OPEN / CONTAINED (unchanged, awaiting human ratification)
LIVE AUTHORIZATION: NOT GRANTED
STOP CONDITIONS:    ACTIVE (§47)
```
