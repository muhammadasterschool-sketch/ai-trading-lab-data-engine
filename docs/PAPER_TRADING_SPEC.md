# PAPER TRADING SPEC

**Document ID:** TRA-PTS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/` (whole package)
**Mandate:** §29/§36/§38/§49/§50/§51/§58/§59/§60

---

## 1. Paper Mode Isolation (§59 — structural, not conventional)

The paper execution path is isolated BY CONSTRUCTION:

- no broker credentials exist anywhere in the runtime (there is no
  credential field to leak);
- no production endpoints (no network import, no URL field);
- no real capital (notional is play money);
- no real account mutation (fills exist only inside the simulator);
- the RiskGate carries a mandatory `paper_mode` check — a non-paper
  runtime refuses EVERY order.

## 2. Persistent Execution State (§29 — RT-F4 closure)

`runtime/state.py` persists per bar (when configured):

- orders, fills, positions, portfolio state
- idempotency keys (duplicate protection across restart)
- reconciliation state
- kill-switch state/audit
- incidents
- ledger sequence heads
- correlation IDs (via ledger events)
- runtime checkpoints (bar cursor, realized equity)

Mechanics: atomic full-state snapshots (`state.json`, tmp + rename)
plus an append-only hash-chained journal (`journal.jsonl`, fsync on
append). ANY I/O failure raises `StateStoreError` — the runtime halts;
there is no best-effort write path. Journal tampering breaks chain
verification → recovery HALTs (tested).

## 3. P&L Accounting (§36)

`runtime/pnl.py` reuses the BUG-002-corrected average-cost engine as
its accounting core; adds exposure, SL/TP levels, source-event
linkage. Realized/unrealized/fees are computed with full
order/fill chain linkage (`PnlRecord`: entry fills, exit fills,
orders, mark price, correlation). Position flips leave the residual
opening at the flip fill's all-in price (pinned by test).

## 4. Deterministic Replay (§49)

Given identical dataset + configuration + model versions + seed +
runtime version, the resulting predictions/decisions/orders/fills/
positions/P&L are bit-identical (tested: two fresh runtimes, same
config INCLUDING session id, same bars ⇒ identical BarOutcome tuples).
Seeds and stochastic configuration are recorded in every model
artifact (`seed` field; 0 for the seed-free deterministic baseline).

## 5. Paper E2E (§50)

The positive E2E (tests/test_runtime_e2e.py) walks the complete
DATA→PIT→FEATURES→SEQUENCE→MODEL→PREDICTION→ENSEMBLE→CALIBRATION→
UNCERTAINTY→REGIME→CRASH→DECISION→TRADE PLAN→RISK→KILL SWITCH→OMS→
PAPER FILL→POSITION→RECONCILIATION→EXIT→P&L→LEDGER→MEMORY chain and
verifies correlation-ID integrity + zero orphan events.

## 6. Negative Paper E2E (§51)

The system refuses trading (NO_TRADE / refusal / HALT — never partial
execution) when: data is stale, data is missing, PIT fails, model is
unavailable/invalid, uncertainty is too high, crash risk is too high,
risk limits are exceeded, a kill switch is active, reconciliation has
mismatched, or the runtime is halted. Each refusal is ledgered with
its reason (§35).

## 7. Scope Protection (§58/§60/§61)

No live broker integration, production credentials, real-money
execution, autonomous capital allocation, leverage escalation, live
deployment, self-promotion, or self-authorized model deployment is
implemented or reachable. Configuration separation
(PAPER/SHADOW/SANDBOX/LIVE) is fail-closed: an invalid/missing
execution mode halts; a PAPER process detecting LIVE
credentials/endpoints halts (`paper_mode` gate check + structural
isolation). The AI cannot change PAPER→LIVE, raise limits, disable
kill switches, or alter governance — those actions require
human-principal authority (tested: machine kill-switch reset refused).

## 8. PAPER_START Prerequisite

Declaring paper operation additionally requires the
`PaperReadinessGate` verdict (see PAPER_READINESS_GATE.md) — which is
currently **FALSE** (real data absent; governance decisions pending).
This spec describes the IMPLEMENTED machinery, not an authorization to
begin live paper operation.
