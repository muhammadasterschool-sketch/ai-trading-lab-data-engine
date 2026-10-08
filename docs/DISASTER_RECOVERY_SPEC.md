# DISASTER RECOVERY SPEC

**Document ID:** TRA-DRS-001 · **Version:** 2.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/recovery.py`, `runtime/state.py`
**Mandate:** §48 (restart/recovery)

---

## 1. Recovery Flow (deterministic, fail-closed)

**Re-audit BLOCKER 4: recovery is INTEGRATED INTO
`TradingRuntime.start()` itself** (`_recover_existing_state`) — a
standalone RecoveryManager test is not recovery. The authoritative
runtime path:

    START
      → LOAD SNAPSHOT (state.json; absent = COLD_START, ledgered)
      → VERIFY SNAPSHOT (EXECUTION_STATE_SCHEMA v1.1.0 + journal chain
        + identity binding: config digest + ensemble member hashes)
      → VERIFY hash/ledger integrity (full chain re-derivation;
        restored heads MUST equal persisted heads)
      → RESTORE OMS / ORDERS / FILLS / POSITIONS (incl. SL/TP) /
        KILL SWITCH / LEDGER STATE / MEMORY / PENDING EXECUTION STATE
        (fill cursors, pending protection, pending exits) / bar
        history + cursor + bad-bar counter + realized equity
      → RECONCILE (fills replay vs stated positions, exactly)
      → ONLY THEN RESUME (RUNNING) — else RECONCILIATION_REQUIRED /
        RECOVERY_REQUIRED / HALTED, and start() is REFUSED

**NEVER resume normal trading after restart without the required
reconciliation.** A restart that cannot prove its state clean
degrades to a refusal, not to amnesia. A restart from a DEGRADED
snapshot resumes DEGRADED. Kill-switch trips and halts persist
IMMEDIATELY — a restart NEVER clears a kill switch (BLOCKER 12).

The standalone `RecoveryManager` remains as a verifier for
out-of-band recovery audits and now restores the persisted ledger
chains too (BLOCKER 6 consistency).

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
