# TRADING LEDGER SPEC

**Document ID:** TRA-TLS-001 · **Version:** 2.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/ledgers.py`
**Mandate:** §34/§35 (ledger family + NO_TRADE ledgering)

---

## 1. The Nine Ledgers

Prediction · Decision · TradePlan · Order · Fill · Position · Trade ·
P&L · Incident — each append-only and hash-chained PER LEDGER.

## 2. Event Schema (§34)

Every event carries: `event_id, ledger, event_type, timestamp,
sequence (per-ledger monotonic), correlation_id, parent_id,
actor/component, payload, payload_hash, prev_hash, event_hash`.

- `event_hash` covers ledger/type/sequence/correlation/parent/actor/
  payload_hash/prev_hash — the chain is tamper-EVIDENT: any edit,
  deletion, or reorder breaks `verify()` (recomputes every link AND
  every payload hash).
- Timestamps are audit wall-clock (FS-21 convention) and never
  participate in identity hashes.

## 3. NO_TRADE Ledgering (§35)

A NO_TRADE decision is recorded in the Decision Ledger as
`DECISION_NO_TRADE` with: prediction ids, reason, risk status,
uncertainty, crash risk, regime, blocked condition, model versions.
The system can always answer **"why did the system NOT trade?"** —
pinned by the positive E2E test.

## 4. Coverage

The RT-F3 closure test requires ALL NINE ledgers non-empty after a
full trading run: predictions, decisions (incl. NO_TRADE), plans,
order transitions, fills, position updates, exits, P&L snapshots, and
incidents (start/halt/data rejections/kill-switch lifecycle/
reconciliation verdicts).

## 4a. Full-Chain Persistence + Recovery (re-audit BLOCKER 6)

v1.0.0 persisted only ledger HEAD hashes — the immutable lineage
(Prediction → Decision → TradePlan → Order → Fill → Position →
Exit → Trade → P&L → Incident) was NOT reconstructable after
restart. v2.0.0 persists the COMPLETE event set of every chain
(`LedgerFamily.export_state()`), and recovery restores + re-verifies
them (`restore_state()`): every event is re-validated, the full hash
chain is recomputed, and the restored heads MUST equal the persisted
heads (chain reconstruction to the same head). Tampering with any
persisted event (edit/delete/reorder) breaks re-derivation ⇒
RECOVERY_REQUIRED refusal (pinned by
`test_ledger_corruption_refuses_restart`). The restart path appends
new events (RUNTIME_STATE_RESTORED, RECONCILIATION_PASS,
RUNTIME_STARTED) onto the restored chains — the audit chain is
CONTINUOUS across restarts, never reset.

## 5. Relationship to Prior Ledgers

The Phase 4A.1 Prediction Outcome Ledger (`predg.` family) remains
the research-layer outcome record. This runtime family (`rtled.`) is
the execution-domain authority. The strategy-domain ledger
(`strategy/ledger.py`, frozen) is historical backtest record and is
never written by the runtime.
