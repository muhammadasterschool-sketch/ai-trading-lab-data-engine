# P0-P3 PAPER-SOAK DRY-RUN REPORT (Task 12 — NO SOAK STARTED)

**Status: the 30-day soak has NOT been started.** What this task did:
make the soak preflight EXECUTABLE, prove it with a deterministic
MOCK dry run, and wire it into the procedure document.

## 1. What was verified about the procedure (against actual code)

`artifacts/stage-d/PAPER-SOAK-PROCEDURE.md` now requires (§1) the
executable preflight as precondition #3 and the FIX-14 update banner
records the command, module, tests, and refusal codes. The
procedure's own start/stop/alert/recovery criteria were checked
against real code paths during the audit:

| Procedure criterion | Code reality (verified) |
|---|---|
| Clock starts at post-start verification | `ComposedSession.start()` refuses without post-start verification (composition root); the FIX-10 launcher inherits this |
| Feed freshness | `feed_gate` staleness thresholds + in-session RUN-ST-1 watchdog (skips new exposure on stale bars; fills/TTL/drawdown continue) |
| No weakening of risk controls | risk limits injected from validated config (F-14); kill-switch trip persists across restarts (tested); one-second spacing governor preserved (9 tests) |
| Ledger integrity | keyed-MAC custody + tamper/history-rewrite tests (28); failed persistence blocks submissions (fail-closed tests) |
| Decimal-exact reconciliation | `ReservationReconciler` conservative driver; post-start divergence refuses certification |
| Bounded monitoring gaps | monitoring API + heartbeat with honest NOT_WIRED dimensions; FIX-10 SessionTick exposes ticks/bars_fed/refusals/feed_errors |
| Daily review | `cli status --gates` snapshot (procedure §); now backed by the canonical classification (FIX-11 pins) |

## 2. The executable preflight (FIX-14)

Command: `data-engine soak-preflight <launch-plan.json> --soak-days 30`
(exit 0 pass / exit 6 refusal; module `runtime/soak_preflight.py`).

Checks performed (all fail-closed, stable reason codes):
1. plan loads and validates (`E_SOAK_PLAN_INVALID`);
2. every NON-component gate carries PASSING bundle evidence
   (`E_SOAK_EVIDENCE_MISSING` / `E_SOAK_GATES_FALSE` — the failing or
   missing gate is named);
3. human gates carry SIGNED approvals only
   (`E_SOAK_EVIDENCE_UNTRUSTED` — the FIX-9 boundary; the plan model
   additionally rejects human-gate free-text entries at load time);
4. every approval's validity window covers the FULL soak duration
   (`E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END`);
5. approval key provisioned (`E_SOAK_APPROVAL_KEY_UNAVAILABLE`).

**CI irrelevance is structural:** the preflight source contains no
CI-input identifiers and no `os.environ` reads outside the
approval-key loader (pinned by test; a green CI run alone can never
admit a soak).

## 3. The mock dry run (deterministic, no network, no live session)

Executed in `tests/test_soak_preflight.py::TestSoakProcedureDryRun`:

1. **preflight passes** on a signed bundle covering all 26
   non-component gates;
2. **(simulated) authorized launch** — `launch_paper_session`
   composes + starts the session through the composition root;
   post-start verification passes;
3. **bounded tick loop** — 80 deterministic replay bars consumed
   (minutes-scale smoke, exactly the documented pre-soak scope — NOT
   a 30-day window);
4. **quiescence** — replay source exhaustion is visible, not fatal.

The dry run also proves procedure ORDER: when the preflight refuses
(missing `AUDIT_READY` evidence), the launch step is never reached —
and the launch itself independently refuses the incomplete chain
(defense in depth).

## 4. Negative paths proven (each refuses the soak)

- one missing recorded gate (`PIT_READY`) → `E_SOAK_EVIDENCE_MISSING`;
- one failing recorded gate (`TESTS_READY`) → `E_SOAK_GATES_FALSE`;
- unsigned human-gate entries → refused (plan model + preflight);
- expired approval → `E_SOAK_EVIDENCE_UNTRUSTED`;
- approval expiring before soak end →
  `E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END`;
- forged signature (different key) → `E_SOAK_EVIDENCE_UNTRUSTED`;
- missing approval key → `E_SOAK_APPROVAL_KEY_UNAVAILABLE`;
- env vars (`SOAK_APPROVED=1`, `CI_GREEN=true`) cannot flip any of
  the above.

## 5. What still gates an ACTUAL soak start

1. the owner's explicit, separate soak-start authorization
   (procedure §1.1 — not given, not assumed);
2. GOVERNANCE_READY / OPERATIONAL_FEED_READY closing with signed
   evidence (owner actions);
3. preflight exit 0 on the owner's real launch plan (the mock dry
   run used fixtures — it is procedure evidence, NOT operational
   evidence).

**No soak was started by this task; no soak is claimed complete.**
