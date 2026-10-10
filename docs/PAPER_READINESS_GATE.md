# PAPER READINESS GATE

**Document ID:** TRA-PRG-001 · **Version:** 2.2.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/readiness.py`
**Mandate:** §52/§53/§66 + paper-readiness re-audit BLOCKER 2/3/24 + RL-governance cycle + operator approval mandate 2026-10-10 §2 (OPERATIONAL_FEED_READY — the research-history vs operational-feed distinction)

---

## 1. The Mandatory Component Gates (32 — re-audit + RL-governance + operational-feed extensions)

DATA_READY · REAL_DATA_READY · **OPERATIONAL_FEED_READY** · PIT_READY ·
SEQUENCE_READY · BASELINE_READY · MODEL_READY · PREDICTION_READY ·
CALIBRATION_READY · UNCERTAINTY_READY · REGIME_READY · CRASH_READY ·
RL_GOV_READY · DECISION_READY · TRADE_PLAN_READY · RISK_READY ·
KILLSWITCH_READY · OMS_READY · EXECUTION_READY · PERSISTENCE_READY ·
RECOVERY_READY · PARTIAL_FILL_READY · SLTP_READY · RECONCILIATION_READY ·
LEDGER_READY · MEMORY_READY · AUDIT_READY · REPLAY_READY ·
OBSERVABILITY_READY · SECURITY_READY · TESTS_READY · GOVERNANCE_READY

Version 1.0.0 listed 23 gates. The 2026-10-09 independent re-audit
(BLOCKER 24) identified seven gates the paper-readiness logic
REQUIRES but the first implementation omitted; they are now
mandatory and fail-closed exactly like the original 23:

- **REAL_DATA_READY** — TRUE only from a REAL_VERIFIED dataset that
  passed the complete nine-stage chain (BLOCKER 3):
  DATA_SOURCE_APPROVED → ACQUIRED → VALIDATED → QUALITY_GATE →
  PIT_VERIFIED → PROVENANCE_VERIFIED → COVERAGE_VERIFIED →
  REPLAYABLE → REAL_VERIFIED. Synthetic data is never promoted
  (structurally refused by `DatasetReadinessRecord`).
- **TRADE_PLAN_READY** — plan construction + risk-budget sizing.
- **PARTIAL_FILL_READY** — multi-bar partial-fill accounting and
  recovery.
- **SLTP_READY** — protective levels survive restart (BLOCKER 9).
- **AUDIT_READY** — the full audit chain is reconstructable.
- **REPLAY_READY** — deterministic replay proven (cross-process).
- **BASELINE_READY** — the deterministic baseline exists and is
  evaluated against (walk-forward).

The 2026-10-09 RL-governance cycle added the thirty-first gate:

- **RL_GOV_READY** — TRUE only with objective evidence that the RL
  layer is EITHER governed-and-integrated (advisor-only, bounded,
  versioned, veto-able — see `docs/RL_RUNTIME_GOVERNANCE_SPEC.md`)
  OR explicitly DISABLED / NON-AUTHORITATIVE — and in BOTH cases
  structurally incapable of bypassing Risk / KillSwitch / OMS
  (verified by import-surface and method-surface tests). An
  ungoverned, failed or silently-absent RL layer blocks operational
  startup exactly like any other failing gate.

The 2026-10-10 operator approval mandate added the thirty-second
(SECTION 2 of that mandate — the research-history vs operational-feed
distinction, decision GOV-HDD-001):

- **OPERATIONAL_FEED_READY** — TRUE only from a genuine, validated,
  FRESH, correctly-mapped current market feed for the traded
  symbol/timeframe from a HUMAN-APPROVED source (APPROVED_FOR_PRODUCTION
  with production-ingestion scope — recorded through the prediction
  source registry's human-only approval mechanism; never fabricated),
  with enough bars for the strategy's indicator warm-up window
  (`src/data_engine/runtime/feed_gate.py`, fail-closed). The DEFERRED
  long-term research-history corpus (GOV-HDD-001) is tracked SEPARATELY
  (RealDataReadiness / VERIFIED_YEARS / the deferral record) and is
  NOT this gate's concern: research history and the operational feed
  are never conflated, and neither is ever claimed satisfied without
  evidence.

## 2. Fail-Closed Rules (§53)

- EVERY gate requires an explicit `GateEvidence` object (component +
  check + evidence + passed). Absent evidence defaults to FALSE —
  never neutral.
- ALL 32 must be TRUE; one FALSE ⇒ `PAPER_READY = FALSE`.
- There is NO manual override, NO environment-variable bypass (the
  gate reads no environment — structurally tested), NO hidden
  default-true.
- `ReadinessReport` validates its own consistency: a TRUE verdict with
  failing gates is IMPOSSIBLE (constructor raises).
- **Runtime enforcement (re-audit BLOCKER 2)**:
  `TradingRuntime.start()` in OPERATIONAL mode evaluates the gate and
  REFUSES startup when the verdict is FALSE (or when no gate is
  wired). The runtime cannot convert missing evidence into
  readiness — the gate is authoritative, the runtime is its subject.

## 3. Evidence Classes

- **Component evidence** — the component is wired AND exercised
  (E2E-tested).
- **Test evidence** — executed suite results (counts, not claims).
- **Governance evidence** — human decisions. NO CODE CAN FABRICATE
  THESE: H-1 ratification (RECORDED 2026-10-10 — GOV-H1-002-RATIFY,
  Option A containment), real-data source approval (OPEN), CI/WP-12
  authorization (RECORDED 2026-10-10 — WP-12-CI-ENABLE, workflow
  installed; platform execution pending first push), credential
  rotation (OPEN — exposed PAT unrevoked), keyed-MAC custody
  operational status (DECIDED + mechanism implemented — GOV-KMC-001;
  NOT operational until a genuine key is provisioned through the
  secure channel). Their open components keep GOVERNANCE_READY /
  REAL_DATA_READY / OPERATIONAL_FEED_READY FALSE, and therefore
  PAPER_READY = FALSE — honestly.

## 4. Ephemeral Test Fixtures (BLOCKER 1 governance)

Unit tests may exercise runtime machinery without persistence ONLY
via the explicit `RuntimeConfig.ephemeral_test_fixture=True`
marking. Such runtimes are ledgered as
`EPHEMERAL_TEST_FIXTURE_STARTED`, are non-operational
(`rt.operational is False`), and never constitute paper sessions.
An operational paper session (`ephemeral_test_fixture=False`, the
fail-closed default) REQUIRES the persistent state store AND a
passing 32-gate readiness verdict — structurally, at startup.

## 5. Current Verdict (2026-10-10, operator-approval cycle)

**PAPER_READY = FALSE.** Engineering gates remain closed and green
(this cycle: keyed-MAC custody mechanism + tests, operational-feed
gate machinery + tests, BUG-008 residual closure with boundary
regression force, suite 1,570 → 1,621 + 1 skipped ×2 deterministic).
Governance/data gates decide the verdict, now with PRECISE remaining
components: **OPERATIONAL_FEED_READY = FALSE** (no human-approved
genuine feed source exists — the operator must record an SRC-APPROVAL
and provision a genuine current feed), **REAL_DATA_READY = FALSE**
(0 REAL_VERIFIED datasets; VERIFIED_YEARS = 0; the long-term research
corpus is DEFERRED by GOV-HDD-001 and honestly reported), and
**GOVERNANCE_READY = FALSE** (H-1 RATIFIED ✓ and CI/WP-12 AUTHORIZED ✓
this cycle — but real-data source approval, exposed-PAT rotation
confirmation, and keyed-MAC custody operationalization remain open
operator actions). See PAPER_TRADING_READINESS_FINAL_REPORT.md v2.2.0
for the full evidence matrix and the exact activation path.
