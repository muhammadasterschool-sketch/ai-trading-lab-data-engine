# RL RUNTIME GOVERNANCE SPEC

**Document ID:** TRA-RLG-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/rl.py`, `src/data_engine/runtime/metrics.py`, `TradingRuntime(rl_policy=...)`
**Mandate:** §28 (RL layer), §44 (autonomy levels), Workstream E (RL advisor), §26/Workstream P (observability)

---

## 1. Purpose and honest scope

This specification governs the RL runtime layer of the paper-trading
system. It exists to close the one genuinely-missing paper-readiness
blocker (RL runtime) under the mandate's own safety rules:

- RL is an **advisor / proposal generator** — never the final
  authority (Workstream E);
- RL must never have authority over Risk, Kill Switch, Order Gateway,
  or Live Trading (Phase 6);
- if RL cannot be safely production-integrated it must be explicitly
  DISABLED / NON-AUTHORITATIVE (Workstream E fallback).

### 1.1 What IS implemented

| Capability | Implementation |
|---|---|
| Policy versioning + deterministic identity | `RLPolicyConfig.policy_hash` — pure function of declared fields (INV-01) |
| Observation contract (state schema) | `RLObservation` — frozen, validated, PIT-safe (built only from the current bar's already-computed state) |
| Action schema (bounded vocabulary) | `RLAction`: HOLD / BUY / SELL / CLOSE, long-only target semantics |
| Hard action bounds | max position units · max turnover per bar · max exposure notional fraction · drawdown halt |
| Out-of-distribution detection | disagreement threshold + confidence floor → HOLD (fail toward safety) |
| Deterministic evaluation mode | `propose()` is a pure mapping; `propose_rl_action()` free function cross-process verifiable |
| Risk escalation | crash-probability halt threshold forces HOLD; drawdown halt forces CLOSE/HOLD only |
| Runtime integration | `TradingRuntime(rl_policy=...)` — record-only, one ledger event + one memory record per bar |
| Readiness gate | `RL_GOV_READY` (31st mandatory gate, fail-closed) |
| Observability | `RuntimeMetrics` counters: rl_proposals / rl_proposals_vetoed / rl_proposals_ood |

### 1.2 What is NOT claimed (honesty record)

- The policy is a **deterministic risk-tempered baseline mapping** —
  NOT a trained reinforcement-learning agent. No empirical RL
  performance (accuracy, reward, Sharpe, or superiority) is claimed,
  implied, or fabricated anywhere.
- "RL runtime implemented" ≠ "RL model empirically validated". The
  runtime contract, bounds, veto machinery, and integration are
  validated by tests; the policy mapping itself is a governed
  placeholder baseline until a trained policy is registered through
  the model registry with out-of-sample evidence.
- RL is DISABLED by default (`rl_policy=None`). No production session
  is required to enable it.

## 2. Architecture (advisory-only, structurally enforced)

```
Market State → Features → Prediction (ensemble+calibration)
                                  ↓
                        Regime / Crash Intelligence
                                  ↓
                        RLObservation (frozen contract)
                                  ↓
                        GovernedRLPolicy.propose()
                                  ↓
                        RLActionProposal (immutable DATA)
                                  ↓  record-only
              Decision Ledger (RL_ACTION_PROPOSED) + TradingMemory
                                  ↓
        (the AUTHORITATIVE chain decides independently:
         Decision → Risk → KillSwitch → OMS — the proposal
         influences NOTHING unless a future governed integration
         says so, and even then only through those gates)
```

Structural non-authority guarantees (tested):

1. `GovernedRLPolicy` exposes NO execution methods (method-surface
   test: submit/create_order/cancel/execute/route/send/place/approve
   all absent).
2. `rl.py` imports no OMS / execution adapter / risk gate / kill
   switch / paper gateway / simulator (import-surface test).
3. `RLActionProposal.advisory_only` is a frozen literal `True`; a
   proposal claiming authority is INVALID BY CONTRACT.
4. An aggressive RL proposal creates ZERO orders when the
   authoritative chain says NO_TRADE (integration test).
5. A tripped GLOBAL kill switch blocks all new orders even while the
   advisor keeps recording proposals (integration test).
6. An invalid observation (NaN, out-of-range, non-positive price or
   equity) raises `RLGovernanceError`; the runtime records an
   `RL_ADVISOR_REFUSED` incident and discards the output (fail safe).

## 3. Deterministic mapping (the governed baseline)

```
score          = probability − 0.5
temper         = regime factor (CRASH 0 · STRESSED 0.25 ·
                 HIGH_VOLATILITY 0.5 · RECOVERY 0.75 ·
                 TRENDING 1 · RANGING 0.75 · UNKNOWN 0.5)
crash_temper   = 1 − crash_probability
confidence_temper = 2·(confidence − 0.5) clipped to [0, 1]
desired        = score · temper · crash_temper ·
                confidence_temper · base_units
```

Fences (in priority order, each recorded as a veto reason):

1. OOD (disagreement ≥ threshold) → HOLD
2. confidence < floor → HOLD
3. crash_probability ≥ crash_halt_probability → HOLD
4. drawdown fraction ≥ drawdown_halt_fraction → CLOSE (if long) / HOLD
5. desired > max_position_units → cap at the ceiling + POSITION_BOUND veto
6. exposure (target notional > fraction · equity) → HOLD + EXPOSURE_BOUND veto
7. turnover (|Δtarget| > per-bar cap) → HOLD + TURNOVER_BOUND veto
   (risk-reduction CLOSE is EXEMPT — blocking risk reduction is unsafe)

Bound-violation semantics are STRICT: any turnover/exposure violation
degrades the proposal to HOLD — never a clamped aggressive move.

Identity: `proposal_id = H(policy_hash, observation_hash, action,
target, bounds_ok, ood_flag)` — INV-01 clean (no wall clock, no
randomness, no process state). Cross-process determinism is proven by
a two-subprocess test plus the in-process equality check.

## 4. Runtime integration contract

- Constructor: `TradingRuntime(..., rl_policy=None)` — DISABLED by
  default; a non-`GovernedRLPolicy` object is refused.
- Per processed bar (after the decision, before plan execution):
  build `RLObservation` from the bar's artifact/uncertainty/regime/
  crash/position/equity → `propose()` → one `RL_ACTION_PROPOSED`
  decision-ledger event (parent = decision id) + one MODEL memory
  record (`kind=rl_action_proposal`, `advisory_only=true`).
- The proposal NEVER reaches the OMS, the risk gate, the gateway, or
  the position book from this path.
- Metrics: `rl_proposals`, `rl_proposals_vetoed`, `rl_proposals_ood`
  increment deterministically with the records.

## 5. Runtime metrics (observability, §26)

`RuntimeMetrics` (in `metrics.py`) provides a closed counter
vocabulary (unknown names raise) and two latency gauges:

- counters: bars_processed / bars_refused / bad_bars / warmup_bars /
  decisions_trade / decisions_hold / no_trade_total (+ reason
  histogram) / orders_created / orders_risk_rejected / fills /
  partial_fill_events / kill_switch_trips / halts /
  reconciliation_mismatches / recovery_events / audit_memory_records /
  ledger_events / rl_proposals / rl_proposals_vetoed /
  rl_proposals_ood;
- gauges: cycle_latency_seconds (last + max), measured with
  `time.perf_counter` around the whole bar cycle.

INV-01 boundary rules (tested):

- `snapshot_hash` covers COUNTERS ONLY (sorted canonical JSON);
  latency gauges are EXCLUDED — wall-clock observability is never
  identity, never persisted, never a decision input;
- metrics are NOT part of EXECUTION_STATE_SCHEMA persistence (they
  are re-derivable from ledgers/memory; the persistence schema and
  its replay identity are unchanged);
- metrics content is counts + numbers only — structurally unable to
  carry secrets (banned-string scan test).

## 6. Test evidence

`tests/test_runtime_rl.py` (45 tests) and
`tests/test_runtime_metrics.py` (23 tests) — 68 tests across the two
new files, plus one operational refusal in
`tests/test_runtime_recovery_integration.py`
(`test_rl_gov_gate_false_refuses_start`) — cover:

- deterministic identity: same inputs ⇒ same proposal / hash;
  cross-process (two independent subprocesses) equality;
- contract validation: unit bounds, NaN/inf, negative price/equity,
  frozen advisory_only literal, negative units;
- hard bounds: position / turnover / exposure / drawdown / crash /
  confidence / OOD — each degrading toward safety;
- advisory-only structure: method-surface, import-surface,
  immutability, zero-order-authority, kill-switch independence;
- readiness gate: 31 gates, RL_GOV_READY missing/failed ⇒
  PAPER_READY = FALSE ⇒ startup refused;
- runtime integration: disabled by default; record-only path;
  in-runtime determinism; memory records present;
- honesty record: module documents "NOT a trained" policy; no
  performance-claim vocabulary in source.

`tests/test_runtime_metrics.py` (23 tests) covers the registry
contract, snapshot-hash determinism, gauge exclusion, scripted-session
exact accounting, persistence isolation, and secret-safety.

`tests/test_runtime_recovery_integration.py` adds the
`test_rl_gov_gate_false_refuses_start` operational refusal.

## 7. Limitations and follow-ups

- No trained policy exists; when one is produced it must enter via
  the model registry with out-of-sample evidence and a NEW policy
  version/hash (never a silent swap).
- The observation vocabulary is currently single-symbol (matches the
  runtime's single-symbol scope); portfolio-level RL would require a
  governed contract extension.
- RL proposals are currently pure audit records; any future
  "consultative" integration (e.g. proposal as a decision-engine
  input) requires a spec amendment + fresh gate evidence.
