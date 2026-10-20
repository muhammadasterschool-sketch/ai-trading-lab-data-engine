# PAPER-SOAK-PROCEDURE (Stage D / D4 — Part 7 mandate)

Status: DOCUMENTED, **NOT STARTED**. This file defines the procedure
the owner's separate "start paper trading" authorization will trigger.
Nothing in the current run executes it. PAPER_READY stays FALSE.

> **FIX-14 update (2026-10-20):** the preflight below is now
> EXECUTABLE (and test-pinned): run
> `data-engine soak-preflight <launch-plan.json> --soak-days 30`
> (module `runtime/soak_preflight.py`; tests
> `tests/test_soak_preflight.py`, including a deterministic MOCK DRY
> RUN of this procedure — no soak was started). The preflight REFUSES
> (exit 6, stable reason codes) unless every non-component gate
> carries passing evidence, the three human gates carry SIGNED
> operator approvals (FIX-9 trust boundary), and every approval's
> validity window covers the FULL soak duration. It reads NO CI
> status: a green CI run alone can never admit a soak.

---

## 1. Preconditions (all must be TRUE before the clock starts)

1. Owner has issued the explicit, separate "start paper trading"
   authorization (Part 2 Rule 3). Recorded in the decision log with
   date, scope, and the exact engine version tag.
2. `PAPER-TRADING-READINESS-REPORT.md` gate matrix reviewed by the
   owner; every gate either VERIFIED or explicitly accepted-as-risk
   by the owner in writing.
3. **Executable soak preflight PASSES**: `data-engine
   soak-preflight <launch-plan.json> --soak-days 30` exits 0 with the
   verdict record (FIX-14). Refusal reasons are stable codes:
   `E_SOAK_PLAN_INVALID`, `E_SOAK_EVIDENCE_MISSING`,
   `E_SOAK_GATES_FALSE`, `E_SOAK_EVIDENCE_UNTRUSTED`,
   `E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END`,
   `E_SOAK_APPROVAL_KEY_UNAVAILABLE`.
4. Engine deployed via the per-user server install
   (`deploy/server-install.sh`, Stage F) on the operator's own VPS;
   monitoring API reachable; APK connected and showing live health.
5. MAC custody key provisioned through the operator channel
   (`RUNTIME_LEDGER_MAC_KEY[_FILE]`); `LEDGER_READY` evidence cites
   the key id. The OPERATOR APPROVAL signing key
   (`OPERATOR_APPROVAL_MAC_KEY[_FILE]`, FIX-9) is provisioned the
   same way — the signed approvals must cover the full soak window.
6. A validated configuration snapshot (hash recorded) is committed to
   the operator runbook BEFORE the soak begins; any config change
   during the soak requires a recorded decision and restarts the
   clock for the affected window.

## 2. Duration

- **Minimum continuous soak: 30 calendar days** (aligned with the
  owner's strategy-activation gate: a strategy needs a 30-day paper
  validation cycle before activation).
- Clock starts at the first successful post-start verification
   (composition root `ComposedSession.start` post-start check
   passes) and stops only on: clean operator shutdown, abort
   condition (§5), or window end.
- Any unplanned engine downtime > 60 minutes during a window
   invalidates that window's continuity credit; the window restarts
   (conservative accounting, fail-closed).

## 3. Success criteria (ALL must hold at window end)

1. **Uptime**: ≥ 99% of the window with the runtime in RUNNING state
   and the feed passing freshness checks (staleness ≤
   `max_feed_staleness_seconds`, default 900s).
2. **Zero unexplained order-state divergences**: every reconciliation
   pass (startup + periodic) closes with zero divergence flags, or
   each flag is explained and closed by a recorded operator decision.
3. **Zero risk-control weakenings**: no kill-switch activation left
   untriaged; every halt has an incident record with root cause.
4. **Ledger integrity**: submission ledger hash chain verifies
   end-to-end under MAC custody; journal tail recovery never needed
   OR needed only for documented clean-shutdown windows.
5. **Spacing compliance**: ≥ 100% of submissions respected the
   owner-ratified spacing (min 1 s between submissions, ≤ 5 per 60 s,
   ≤ 10 open orders); every refusal is logged and none trace to a
   governor bug.
6. **PnL accounting**: every fill's cost decomposition reconciles
   against the PnL ledger to the cent (Decimal-exact).
7. **Monitoring evidence**: heartbeat history complete (registry
   shows no silent offline gap > 5 minutes unexplained).

## 4. Monitoring during the soak

- Engine health heartbeat every 30-60 s to the admin registry
   (one-way, outbound, identity+health fields only).
- Daily automated check: `data-engine status --gates` snapshot
   archived to the state directory (32-gate disposition history).
- Weekly reconciliation audit: `ReservationReconciler` report exported
   and archived; divergence flags must be zero or triaged.
- Alert channels: APK dashboard alerts + admin panel offline
   detection (missed-heartbeat threshold: 3 intervals).

## 5. Abort conditions (any one ABORTS the soak immediately)

1. Kill switch trips without an explainable market cause.
2. Any UNKNOWN order outcome that reconciliation cannot resolve
   within 24 h.
3. Any submission that bypassed the governor/ledger boundary
   (contract violation — this is a code defect, not a market event).
4. Any secret/credential exposure indication.
5. State-store or journal corruption detected (fsck/verification
   failure).
6. Feed provenance failure (data outside the approved PIT /
   research-history window).
7. Operator decision (recorded reason).

Abort handling: clean shutdown → preserve state → incident record →
root-cause analysis → fix → NEW 30-day window (the aborted window
earns no credit).

## 6. End-of-soak deliverables

1. SOAK-REPORT.md: window bounds, uptime, criteria scorecard,
   incidents, divergences, spacing statistics, PnL reconciliation.
2. Updated readiness report with operational-evidence gates flipped
   from REQUIRES_OPERATIONAL_EVIDENCE to VERIFIED.
3. Owner decision record: continue paper / extend soak / stop.
   PAPER_READY remains FALSE until the owner flips it explicitly.
