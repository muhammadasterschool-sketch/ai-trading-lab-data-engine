# DISASTER RECOVERY SPEC

**Document ID:** TRA-DRS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/recovery.py`, `runtime/state.py`
**Mandate:** §48 (restart/recovery)

---

## 1. Recovery Flow (deterministic, fail-closed)

    runtime running (open orders / open positions / kill-switch state)
      → restart
      → restore persistent state (orders, fills, positions, switches)
      → verify ledger integrity (all 9 chains)
      → verify state-journal chain
      → reconcile orders ↔ fills ↔ positions
      → RESUME (only if EVERYTHING verifies) | RECONCILIATION_REQUIRED
        | HALT

**NEVER resume normal trading after restart without the required
reconciliation.** A restart that cannot prove its state clean
degrades to HALT, not to amnesia.

## 2. Verdicts

- `RESUME` — state restored, all chains verify, reconciliation clean,
  no critical kill switch active.
- `RECONCILIATION_REQUIRED` — integrity intact but positions/fills
  mismatch (or stated state missing): new orders STOP until resolved.
- `HALT` — unverifiable state (corrupted snapshot, broken journal
  chain, broken ledger chain) or a critical kill switch (ACCOUNT/
  GLOBAL) active across restart.

## 3. Corruption Detection

- Snapshot: malformed JSON or missing envelope → `StateStoreError`
  → HALT verdict.
- Journal: any record whose recomputed hash differs, or whose
  index/prev-link is inconsistent → chain verification FAILS → HALT.
- Ledgers: `LedgerFamily.verify()` recomputes every chain and every
  payload hash.
- All three are exercised by failure-injection tests (tampered
  journal → HALT; position mismatch → RECONCILIATION_REQUIRED).

## 4. Persistence Guarantees (RT-F4)

Atomic snapshot writes (tmp + rename, fsync) mean a crash mid-write
can never leave a half-written authoritative state. The append-only
journal (fsync per record) provides the mutation history between
snapshots. I/O failures raise — there is no best-effort mode.

## 5. Operator Runbook (informational)

1. Restart the runtime with the same store directory.
2. Read the RecoveryReport verdict.
3. HALT → inspect journal/ledger corruption, then restart from a
   known-good snapshot (operator decision).
4. RECONCILIATION_REQUIRED → resolve open-order ambiguity
   (`resolve_reconciling`), correct stated positions, re-run
   reconciliation until clean.
5. RESUME → the runtime may continue (it is still subject to the
   readiness gate and governance states).
