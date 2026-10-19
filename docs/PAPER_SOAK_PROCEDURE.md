# PAPER SOAK PROCEDURE (NOT STARTED)

```text
Document ID:     GOV-PSP-001
Version:         1.0.0
Date:            2026-10-19 (Asia/Karachi)
Document Type:   Operational procedure specification (U-24, Stage D,
                 patch plan P6)
Authority:       B — CURRENT SUPPORTING (the procedure a soak must
                 follow; the soak itself is an operator-run activity)
Status:          NOT STARTED — no paper soak has been run, and this
                 document authorizes nothing by existing
Pinning tests:   tests/test_paper_evidence_docs.py
```

**PAPER_READY = FALSE. LIVE TRADING REMAINS NOT AUTHORIZED.** A
soak is an EVIDENCE-GATHERING activity inside paper mode. It does not
activate anything, does not flip any gate, and can never authorize
live trading.

---

## 1. Preconditions (all must hold BEFORE the soak starts)

1. `PAPER-TRADING-READINESS-REPORT.md` reviewed by the operator; the
   soak does NOT require its verdict to be PASS — it requires the
   operator to have READ the blocker list and accepted the soak scope.
2. An operational session composed through
   `compose_operational_session` (Stage C composition root) — the
   soak never runs an ad-hoc hand-wired runtime.
3. A provisioned operational feed from a human-approved source
   (`OPERATIONAL_FEED_READY` evidence recorded), sufficient warm-up
   bars, feed watchdog enabled (`max_feed_staleness_seconds` = the
   paper default 900 s or tighter).
4. Keyed-MAC custody provisioned (`RUNTIME_LEDGER_MAC_KEY[_FILE]`,
   `key_id` recorded in the `LEDGER_READY` evidence — GOV-04).
5. The 5-per-60 s / 1 s-spacing / 10-open-orders ratified paper
   limits ACTIVE (durable submission ledger + governor + venue
   backstop all wired — verified through `status --gates`).
6. Operator on-call rota agreed for the soak window (the soak is
   monitored, never unattended).

## 2. Duration

- **Minimum soak:** 30 consecutive calendar days of session uptime
  (aligned with the strategy-lab 30-day paper cycle), PLUS at least
  20 trading days with a live operational feed.
- **Zero-restart requirement for the CORE evidence:** the first 7
  days must run without any operator-initiated restart (crash
  restarts are evidence, not failure — see §5).
- **Extension trigger:** any EXECUTION_UNCERTAIN incident, kill-switch
  trip, or reconciliation divergence during the window pauses the
  clock until resolved; the 30-day clock resumes only from a clean
  RUNNING state (total wall time therefore exceeds 30 days whenever
  incidents occur).

## 3. Monitoring (what is watched, where it is recorded)

| Signal | Source | Cadence |
|---|---|---|
| Session state (RUNNING / DEGRADED / HALTED / EXECUTION_UNCERTAIN) | runtime state store + `status --gates` | at least hourly (scripted) |
| Feed freshness / staleness watchdog verdicts | feed gate + watchdog incidents | every bar close |
| Submission-rate ledger health (reservations, refusals, spacing) | durable ledger records + incidents | daily review |
| Reconciliation verdicts (venue journal vs OMS vs ledger) | `ReservationReconciler` decisions + incidents | every bar close |
| Drawdown vs ratified limits (3 % daily / 20 % account) | risk gate assessments | every bar close |
| Kill-switch state transitions | kill-switch manager + incidents | event-driven |
| Persistence integrity (journal chain verification, snapshot loads) | recovery protocol on every restart | every restart |

All monitoring records are retained under the session's data
directory; the soak evidence pack references them by path (nothing is
rewritten or summarized destructively).

## 4. Success criteria (ALL must hold at the end of the window)

1. **Zero silent divergences:** every venue-journal/OMS/ledger
   mismatch produced an incident and a fail-closed halt — none was
   auto-repaired, none was missed.
2. **Zero unauthorized submissions:** every executed submission
   carried a durable reservation made BEFORE the venue call; the
   measured window is a superset of the journalled acks at all times.
3. **Rate-limit honesty:** zero submissions that violated the
   ratified spacing/capacity limits (ledger-enforced, not
   honor-system).
4. **Recovery soundness:** every crash/restart inside the window
   followed LOAD → VERIFY → RESTORE → RECONCILE → RESUME-or-HALT with
   identical results to the equivalent unbroken run (deterministic
   replay verification where applicable).
5. **No unplanned exposure:** end-of-window positions reconcile
   exactly against venue truth; no orphan orders, no phantom fills.
6. **Honest incidents:** every incident that occurred is classified,
   recorded and reviewed — an incident-free soak with no explanations
   is NOT more valuable than one with well-understood incidents.

## 5. Abort conditions (the soak STOPS immediately when ANY holds)

1. Any kill-switch trip that was not an explicit test (a real risk
   breach).
2. Any reconciliation divergence that cannot be resolved from venue
   truth within one bar.
3. Any persistence-integrity failure (journal chain verification
   failure, torn snapshot, state-store lock violation).
4. Account drawdown beyond the ratified 20 % limit, or daily loss
   beyond 3 % on two consecutive days.
5. Feed outage longer than the watchdog window with orders open.
6. Any evidence of secret exposure or unexpected network egress.

Abort = halt the session (safe shutdown), preserve ALL state, record
the abort reason in the soak evidence pack, and file the incident.
An aborted soak yields NO partial success credit.

## 6. Evidence pack (what the operator files at the end)

- Session identity (session id, symbol, timeframe, config hash,
  model hashes, runtime version, start/end timestamps).
- The monitoring records of §3 (by reference).
- The incident ledger extract for the full window.
- The final `status --gates` output.
- A signed operator statement: duration actually run, criteria
  met/not met, aborts (if any) with reasons.
- Explicit statement that PAPER_READY remains FALSE regardless of
  the soak outcome (readiness gates evaluate separately; a soak is
  ONE input among many).

## 7. Honest scope statement

No soak has been started. This procedure exists so that WHEN the
operator chooses to run one, the rules, thresholds, and evidence
expectations are agreed BEFORE the first bar — not negotiated
afterwards. Nothing in this document changes any gate verdict, and
the soak itself never authorizes live trading.
