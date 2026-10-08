# TRADING RUNTIME ARCHITECTURE

**Document ID:** TRA-RTA-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/` (package `data_engine.runtime`)
**Mandate:** Pre-Paper Readiness Implementation mandate §24 (authoritative orchestration path)
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
- State snapshots persist per bar when a store is configured (RT-F4
  closure).

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
| Persistence | `runtime/state.py` | atomic snapshots + chained journal |
| Recovery | `runtime/recovery.py` | restore → verify → reconcile → resume-or-halt |
| Readiness | `runtime/readiness.py` | 23 fail-closed component gates |

## 3. Operating States

`INIT → RUNNING` (start self-checks) · `DEGRADED` (persistent data
quality failures) · `RECONCILIATION_REQUIRED` (mismatch — new orders
STOP) · `RECOVERY_REQUIRED` / restart path · `EXECUTION_UNCERTAIN`
(ambiguous outcome — reconcile before retry) · `HALTED` (terminal safe
stop). **Trading happens only in RUNNING.**

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
12. reconciliation after fills → P&L snapshot → memory → persistence

## 5. Determinism

Bar processing is a pure function of (config, fitted models, bar
history): identical inputs ⇒ identical predictions, decisions, orders,
fills, positions, P&L (tested in `tests/test_runtime_e2e.py::
TestDeterministicReplay`). Wall-clock appears ONLY in audit metadata
(FS-21 convention), never in identities.

## 6. Scope Boundaries (mandate §58/§59/§61)

- PAPER mode only; the execution adapter carries no credential,
  endpoint, network, or account surface (structurally isolated).
- No live broker integration, no real capital, no self-promotion, no
  autonomous kill-switch reset, no limit escalation. PAPER→LIVE
  transitions require the gated later stages (P5–P8), all LOCKED.

## 7. Verification Evidence

- `tests/test_runtime_e2e.py` — full-chain E2E, negative E2E, 24
  failure-injection scenarios, restart/recovery, deterministic replay.
- `tests/test_runtime_oms.py`, `tests/test_runtime_safety.py`,
  `tests/test_runtime_sequence.py`, `tests/test_runtime_models.py`,
  `tests/test_finding_closures.py` — component + closure evidence.
- Full suite: **1335 passed** (1141 pre-existing + 194 new).
