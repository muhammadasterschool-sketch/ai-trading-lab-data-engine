# TRADING RUNTIME ARCHITECTURE

**Document ID:** TRA-RTA-001 · **Version:** 2.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/` (package `data_engine.runtime`)
**Mandate:** Pre-Paper Readiness Implementation mandate §24 + paper-readiness re-audit BLOCKERs 1/2/4/5/14
**Frozen Phase 3 relationship:** NONE — this runtime consumes non-frozen surfaces only; frozen strategy contracts are reached (read-only) through the RT-F6 vocabulary bridge.

---

## 1. The One Authoritative Path

```
DataFeed → DataValidator → PITGate → FeatureEngine → SequenceBuilder
    → PredictionEngine(Ensemble) → Calibration → Uncertainty → Regime
    → CrashRisk → PortfolioState → DecisionEngine → PositionSizer
    → TradePlan → RiskEngine(RiskGate) → KillSwitch → OMS
    → PaperExecutionGateway → Fill → PositionState → Reconciliation
    → Ledgers → Memory → Monitoring
```

Every paper order flows through `TradingRuntime._execute_plan`:
create → validate → risk-approve → submit → (latency) → fill → books.
There is **no alternate production path**:

- The OMS structurally refuses `RISK_APPROVED` without a **passing**
  `RiskAssessment` whose order fingerprint matches the order exactly
  (RT-F1 closure — bypass is impossible, not merely discouraged).
- Reconciliation runs after every fill-producing bar (RT-F2 closure).
- Every transition is ledgered (RT-F3 closure).
- **Persistence is MANDATORY** (re-audit BLOCKER 1): an operational
  paper session cannot reach RUNNING without an authoritative
  `ExecutionStateStore` that passes its self-check (journal chain +
  snapshot schema + writability). Write failure mid-session ⇒ safe
  HALT, never best-effort continuation. Only explicitly-marked
  ephemeral test fixtures (`RuntimeConfig.ephemeral_test_fixture=True`,
  ledgered `EPHEMERAL_TEST_FIXTURE_STARTED`, `rt.operational is False`)
  may run without persistence.
- **The paper readiness gate is AUTHORITATIVE** (re-audit BLOCKER 2):
  `start()` evaluates the 30-gate `PaperReadinessGate` and REFUSES
  startup on a FALSE verdict or a missing gate.
- **Recovery is integrated into the runtime itself** (re-audit
  BLOCKER 4): see §4a.
- **Identity is wall-clock-free** (re-audit BLOCKER 14): every
  identity hash (order, fill, prediction, decision, plan, ledger
  event, memory record, risk assessment) is a pure function of
  declared identity fields. The risk-assessment id no longer embeds
  `assessed_at` (audit metadata only); memory records use bar
  timestamps; ledger events never hashed timestamps.

## 2. Component Map

| Stage | Module | Authority |
|---|---|---|
| Data validation | `runtime/data_gate.py` (`validate_bars`) | §10 hard quality gates |
| PIT sequence | `runtime/sequence.py` | cutoff-enforced windows, labels only when knowable |
| Prediction | `runtime/models.py` | baseline + LSTM + Transformer + ensemble + calibration |
| Uncertainty | `runtime/contracts.py` (`UncertaintyReport`) | confidence/entropy/disagreement/epistemic/aleatoric |
| Regime | `prediction/regimes.py` (`RegimeEngine`) | documented mapping into §19 states |
| Crash intelligence | `runtime/runtime.py` (`_assess_crash`) | INDEPENDENT of the directional signal (§20) |
| Decision | `runtime/decision.py` | BUY/SELL/REDUCE/HOLD/CLOSE/NO_TRADE (closed set) |
| Sizing + plan | `runtime/trade_plan.py` | risk-budget sizing, vol-derived SL/TP |
| Risk gate | `runtime/risk_gate.py` | 21 mandatory fail-closed checks (§25) |
| Kill switch | `runtime/kill_switch.py` | 7-scope hierarchy, human-gated reset |
| OMS | `runtime/oms.py` | 14-state machine, idempotency, TTL, partial fills |
| Execution | `runtime/execution.py` | multi-bar partial fills, paper-only isolation |
| Positions/P&L | `runtime/pnl.py` | BUG-002-corrected average-cost core |
| Exits | `runtime/exits.py` | SL/TP lifecycle + all exit reasons (§31) |
| Reconciliation | `runtime/reconciliation.py` | multi-fill-aware three-way reconcile |
| Ledgers | `runtime/ledgers.py` | 9 hash-chained ledgers |
| Memory | `runtime/memory.py` | 12 categories, read-only for safety |
| Persistence | `runtime/state.py` | atomic snapshots + chained journal + EXECUTION_STATE_SCHEMA v1.1.0 + self-check |
| Recovery | `runtime/recovery.py` + `TradingRuntime._recover_existing_state` | restore → verify → reconcile → resume-or-halt |
| Readiness | `runtime/readiness.py` | 30 fail-closed component gates (re-audit BLOCKER 24) |

## 3. Operating States

`INIT → RUNNING` (fail-closed startup chain, §3a) · `DEGRADED`
(persistent data quality failures — and a restart from a DEGRADED
snapshot stays DEGRADED) · `RECONCILIATION_REQUIRED` (mismatch — new
orders STOP) · `RECOVERY_REQUIRED` / restart path ·
`EXECUTION_UNCERTAIN` (ambiguous outcome — reconcile before retry) ·
`HALTED` (terminal safe stop; persistence write failure halts here).
**Trading happens only in RUNNING.**

## 3a. Fail-Closed Startup Chain (re-audit BLOCKER 1/2/4)

```
INIT
  ↓ component self-check (ensemble non-empty, feature/dataset
    versions, pinned model hashes — BLOCKER 21)
  ↓ [ephemeral test fixture? → ledger EPHEMERAL marker, done]
  ↓ persistence check: store present + self_check() clean
      (NO_STATE_STORE ⇒ REFUSED; corrupt/unavailable ⇒ REFUSED)
  ↓ paper readiness gate: 30/30 gates PASS ⇒ else REFUSED
  ↓ recovery (existing state): LOAD → VERIFY (schema + identity
      binding incl. config digest + ensemble member hashes) →
      RESTORE (ledger chains → memory → OMS → kill switch →
      positions incl. SL/TP → bars → cursors → pending
      protection/exits) → RECONCILE ⇒ mismatch ⇒ REFUSED
  ↓ kill-switch check: critical active ⇒ HALTED + REFUSED
  ↓ (persisted DEGRADED ⇒ resume DEGRADED)
RUNNING
```

A restart never jumps INIT → RUNNING without this chain, and never
resumes on unprovable state (BLOCKER 4/10).

## 4. Bar Processing Order (latency-aware)

1. state guard → refuse in non-trading states
2. data quality validation **with previous-bar context** (gap detection)
3. **pending orders fill FIRST** (orders submitted on bar N fill on
   bars N+lag..; no same-bar fill of the bar's own decision)
4. TTL expiry for live orders
5. completed-exit records (§31 linkage)
6. PIT sequence build (cutoff = this bar's close)
7. ensemble → calibration → uncertainty → regime → crash
8. prediction artifact + prediction ledger
9. decision (+ NO_TRADE ledgering §35)
10. trade plan (if actionable) → risk gate → OMS submission
11. protective exits for positions from earlier bars
12. reconciliation after fills → P&L snapshot → memory (bar-timestamp
    identities) → persistence of the COMPLETE execution state
    (BLOCKER 5 — including warm-up and rejected bars, whose state
    transitions are persisted too)

## 4a. Complete Execution-State Persistence (re-audit BLOCKER 5/6/20)

`EXECUTION_STATE_SCHEMA_VERSION = "1.1.0"` enumerates EVERY
execution-critical field (validated on persist AND restore):
orders (lifecycle + fills + quantities + average prices) ·
kill-switch states · positions incl. SL/TP · **full ledger event
chains** (not just heads — the lineage is reconstructable and the
heads must re-derive identically) · structured memory (chain hash
cross-checked) · admitted bar history · bar cursor · fill cursors ·
pending protection · pending exits · bad-bar counter · realized
equity · session/config/model identity block (config digest +
ensemble member hashes + calibrator identity — a restart under a
DIFFERENT identity is refused, BLOCKER 21). Kill-switch trips and
halts persist IMMEDIATELY (a crash right after a trip never loses
the switch — BLOCKER 12).

## 5. Determinism

Bar processing is a pure function of (config, fitted models, bar
history): identical inputs ⇒ identical predictions, decisions, orders,
fills, positions, P&L (tested in `tests/test_runtime_e2e.py::
TestDeterministicReplay`), **and identical identity/audit digests** —
order ids, fill ids, ledger head hashes, and the memory chain hash
are bit-identical across independent OPERATIONAL runs
(`tests/test_runtime_recovery_integration.py::
TestDeterministicReplayOperational`), and across fully independent
PROCESSES (cross-process replay evidence). Wall-clock appears ONLY
in audit metadata (FS-21 convention), never in identities — the
re-audit removed the two contaminants found (risk-assessment id
embedded `assessed_at`; cold-start incident embedded the store
filesystem path).

## 6. Scope Boundaries (mandate §58/§59/§61)

- PAPER mode only; the execution adapter carries no credential,
  endpoint, network, or account surface (structurally isolated).
- No live broker integration, no real capital, no self-promotion, no
  autonomous kill-switch reset, no limit escalation. PAPER→LIVE
  transitions require the gated later stages (P5–P8), all LOCKED.

## 7. Verification Evidence

- `tests/test_runtime_e2e.py` — full-chain E2E, negative E2E, 24
  failure-injection scenarios, restart/recovery, deterministic replay.
- `tests/test_runtime_recovery_integration.py` — **the re-audit
  evidence module (43 tests)**: persistence-mandatory refusals,
  readiness-gated startup (per-gate negative tests), the ten
  mandated restart points THROUGH TradingRuntime, ledger/memory
  corruption refusals, kill-switch survival, idempotency across
  restart, TTL-around-restart, model pinning, REAL_VERIFIED chain,
  EXECUTION_STATE_SCHEMA, structural risk-gate scan, operational
  deterministic replay.
- `tests/test_runtime_oms.py`, `tests/test_runtime_safety.py`,
  `tests/test_runtime_sequence.py`, `tests/test_runtime_models.py`,
  `tests/test_finding_closures.py` — component + closure evidence.
- Full suite: **1378 passed, 1 skipped** (1335 + 43 re-audit tests).
