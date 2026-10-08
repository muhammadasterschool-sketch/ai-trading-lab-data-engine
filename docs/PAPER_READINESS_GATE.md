# PAPER READINESS GATE

**Document ID:** TRA-PRG-001 · **Version:** 2.1.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/readiness.py`
**Mandate:** §52/§53/§66 + paper-readiness re-audit BLOCKER 2/3/24 + RL-governance cycle ("RL safety/integration" mandatory gate)

---

## 1. The Mandatory Component Gates (31 — re-audit + RL-governance extensions)

DATA_READY · REAL_DATA_READY · PIT_READY · SEQUENCE_READY ·
BASELINE_READY · MODEL_READY · PREDICTION_READY ·
CALIBRATION_READY · UNCERTAINTY_READY · REGIME_READY ·
CRASH_READY · RL_GOV_READY · DECISION_READY · TRADE_PLAN_READY ·
RISK_READY · KILLSWITCH_READY · OMS_READY · EXECUTION_READY ·
PERSISTENCE_READY · RECOVERY_READY · PARTIAL_FILL_READY · SLTP_READY ·
RECONCILIATION_READY · LEDGER_READY · MEMORY_READY · AUDIT_READY ·
REPLAY_READY · OBSERVABILITY_READY · SECURITY_READY · TESTS_READY ·
GOVERNANCE_READY

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

## 2. Fail-Closed Rules (§53)

- EVERY gate requires an explicit `GateEvidence` object (component +
  check + evidence + passed). Absent evidence defaults to FALSE —
  never neutral.
- ALL 31 must be TRUE; one FALSE ⇒ `PAPER_READY = FALSE`.
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
  THESE: H-1 ratification, real-data source approval, CI
  authorization, credential rotation. Their absence keeps
  GOVERNANCE_READY / REAL_DATA_READY FALSE, and therefore
  PAPER_READY = FALSE — honestly.

## 4. Ephemeral Test Fixtures (BLOCKER 1 governance)

Unit tests may exercise runtime machinery without persistence ONLY
via the explicit `RuntimeConfig.ephemeral_test_fixture=True`
marking. Such runtimes are ledgered as
`EPHEMERAL_TEST_FIXTURE_STARTED`, are non-operational
(`rt.operational is False`), and never constitute paper sessions.
An operational paper session (`ephemeral_test_fixture=False`, the
fail-closed default) REQUIRES the persistent state store AND a
passing 31-gate readiness verdict — structurally, at startup.

## 5. Current Verdict (2026-10-09, re-audit cycle)

**PAPER_READY = FALSE** — engineering gates closed this cycle
(persistence mandatory, readiness-gated startup, runtime-integrated
recovery, complete execution-state persistence, full ledger/memory
chain recovery, partial-fill + SL/TP + kill-switch recovery,
deterministic identity); governance/data gates remain open: no
REAL_VERIFIED dataset exists in the repository
(BLOCKED_ON_REAL_DATA, VERIFIED_YEARS = 0), H-1 ratification is
HUMAN_DECISION_REQUIRED, CI/WP-12 authorization is
HUMAN_DECISION_REQUIRED, and the exposed GitHub PAT rotation is an
open operator action. See PAPER_TRADING_READINESS_FINAL_REPORT.md
(v2.0.0) for the full evidence matrix.
