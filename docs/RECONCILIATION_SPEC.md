# RECONCILIATION SPEC

**Document ID:** TRA-RCS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/reconciliation.py`
**Mandate:** §32 (reconciliation is part of the runtime)

---

## 1. Scope

Three-way reconciliation over:

    INTERNAL ORDERS (OMS) ↔ EXECUTION GATEWAY (fills) ↔ POSITIONS ↔ PORTFOLIO

Multi-fill aware (PAPER-BLK-3 closure — extends the BUG-004
fills-iff-FILLED invariant to partial-fill accounting):

1. **every fill's order exists** (no orphan fills);
2. **quantity consistency per lifecycle state**: FILLED ⇒ Σfills ==
   quantity; PARTIALLY_FILLED ⇒ 0 < Σfills < quantity;
   SUBMITTED/ACKNOWLEDGED ⇒ Σfills == 0; CANCELLED ⇒ not fully
   filled;
3. **position replay**: replaying all fills from zero reproduces the
   stated positions EXACTLY (quantity + average cost + realized P&L);
4. **no unstated positions**: every symbol with fills has stated state.

## 2. Failure Behavior (§32)

Any mismatch ⇒ `ReconciliationReport.ok = False` ⇒ the runtime enters
`RECONCILIATION_REQUIRED` and **STOPS NEW ORDERS** until resolved.
`require_ok` raises `ReconciliationFailure` — never papered over.
Every reconciliation (pass or mismatch) is recorded in the Incident
Ledger with the full mismatch list.

## 3. Invocation Points

- after every fill-producing bar (`_reconcile_after_fills` — RT-F2
  closure: the runtime is a production caller);
- during restart recovery (restore → verify → reconcile →
  resume-or-halt; see DISASTER_RECOVERY_SPEC.md).

## 4. Ambiguous Orders (§28)

Orders in UNKNOWN/RECONCILING refuse resubmission; the only legal
resolution path is `resolve_reconciling(order_id, resolved_state)`
after reconciliation determines the safe state.
