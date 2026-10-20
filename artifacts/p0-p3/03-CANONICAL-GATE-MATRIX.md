# P0-P3 CANONICAL READINESS-GATE MATRIX

**Authoritative evaluator** (single source of truth):
`src/data_engine/runtime/readiness.py` (`GATE_NAMES`, 32 gates;
`PaperReadinessGate.evaluate()`) + the composition root's evidence
suppliers (`src/data_engine/runtime/composition.py`). Reports
reconcile to THIS output (FIX-11; pinned by
`tests/test_report_gate_consistency.py`). `cli status --gates` prints
the same classification.

Legend:
- **Current result** — the honest verdict for the repository as of
  this task's final commits, under the gate's real acceptance
  criteria (not what a dev run can self-assert).
- **Mechanism** — is the gate's contract implemented and test-pinned?
- **Evidence supplier** — `SUPPLIED_BY_COMPOSITION_ROOT` (6),
  `HUMAN_ACTION_REQUIRED` (3), `OPERATOR_RECORDED_EVIDENCE_REQUIRED`
  (23).
- **Next action** — who must do what for the gate to pass.

| # | Gate | Mechanism | Evidence supplier | Current result | Evidence / expiry | Next action |
|---|---|---|---|---|---|---|
| 1 | DATA_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | code contract passing (ingestion fail-closed, pinned suites) | suite runs; no expiry | operator records evidence at launch (or signed soak bundle) |
| 2 | REAL_DATA_READY | machinery only | **HUMAN** | **FALSE** | 0 REAL_VERIFIED datasets; out of this task's scope | owner: real-data chain (RDR-01..03) — separate task |
| 3 | OPERATIONAL_FEED_READY | VERIFIED_IN_CODE | **HUMAN** | **FALSE** | no approved genuine feed provisioned | owner: provision feed + source approval (checklist §2) |
| 4 | PIT_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records at launch |
| 5 | SEQUENCE_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records at launch |
| 6 | BASELINE_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records at launch |
| 7 | MODEL_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (pins enforced at start) | suites | operator records at launch (with pinned hashes) |
| 8 | PREDICTION_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 9 | CALIBRATION_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 10 | UNCERTAINTY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 11 | REGIME_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 12 | CRASH_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 13 | RL_GOV_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (advisor-only/ vetoable or disabled) | suites | operator records |
| 14 | DECISION_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 15 | TRADE_PLAN_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 16 | RISK_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose | first-hand at launch | automatic at launch |
| 17 | KILLSWITCH_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose | first-hand at launch | automatic at launch |
| 18 | OMS_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose | first-hand at launch | automatic at launch |
| 19 | EXECUTION_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (paper gateway §D2) | suites | operator records |
| 20 | PERSISTENCE_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose (F-03 flock) | first-hand at launch | automatic at launch |
| 21 | RECOVERY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (conservative recovery) | suites | operator records |
| 22 | PARTIAL_FILL_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 23 | SLTP_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 24 | RECONCILIATION_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose (C3) | first-hand at launch | automatic at launch |
| 25 | LEDGER_READY | VERIFIED_IN_CODE | **COMPOSITION_ROOT** | verified first-hand at compose (B1/B2 + F-25 custody when keyed) | first-hand at launch | automatic at launch; MAC key owner-provisioned |
| 26 | MEMORY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 27 | AUDIT_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (locked append trail) | suites | operator records |
| 28 | REPLAY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 29 | OBSERVABILITY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing | suites | operator records |
| 30 | SECURITY_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | contract passing (redteam/tenancy) | suites | operator records |
| 31 | TESTS_READY | VERIFIED_IN_CODE | OPERATOR_RECORDED | full suite green this run | this task's runs | operator records the suite evidence |
| 32 | GOVERNANCE_READY | machinery VERIFIED; substance human | **HUMAN** | **FALSE** | GOV-03/04/05 open | owner: record decisions + SIGN them (FIX-9 key); checklist §1 |

**Summary (reconciled, FIX-11):** 29 gates have code mechanisms
verified and pinned; their operational verdicts materialize at launch
through the composition root (6 first-hand) and the operator's
recorded bundle (23). **3 gates are human-dependency gates and are
FALSE: REAL_DATA_READY, OPERATIONAL_FEED_READY, GOVERNANCE_READY.**
`PAPER_READY = FALSE` until all three close with verified evidence —
human gates now additionally require SIGNED operator approvals
(FIX-9), so a passing chain can no longer be fabricated by code.

**Verdict logic (unchanged, test-pinned):** ALL 32 must be TRUE;
absent evidence is FALSE; no env-var override exists
(`test_no_environment_bypass` + `PaperReadinessGate` env-freedom
structural tests).

**Expiry model:** signed approvals carry `issued_at`/`expires_at`
and are re-verified at compose/soak-preflight time; the 30-day soak
requires approvals whose window covers the entire soak
(`E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END`).
