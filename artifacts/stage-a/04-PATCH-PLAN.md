# 04 — PATCH PLAN (ordered implementation groups)

Execution rule per prompt Part 5: for EVERY defect — regression test FIRST (prove it fails on the defective behavior where reproducible; where the historical defective commit is unavailable — it IS unavailable, see 00-REPO-IDENTITY §1 — use documented reproductions or controlled faulty test doubles, labeled with limitations; never fabricate differential results), then the smallest authorized fix, related tests, FULL suite, race/crash-window probes where applicable, full diff review, static + security checks, clean commit on a feature branch.

**Test-first discipline for B1/B2/B3 (historical C1/C2 commit is ABSENT):** each group ships with (a) a reproduction test written against current `main` that demonstrates the defective behavior where one exists (e.g., restart-wipes-budget is directly reproducible; cross-process last-slot race is reproducible with a multiprocessing probe), and (b) controlled faulty doubles where the defect is a crash window (kill -9 / fault-injection seams, labeled as such).

---

## GROUP P1 — Durable submission-rate ledger (B1) — findings F-01, F-02, F-19

- **Scope:** New module `src/data_engine/runtime/submission_ledger.py`: `SubmissionLedger` — flock-protected durable ledger (JSONL append + periodic compacted snapshot) storing reservations `{reservation_id, client_order_id, created_at (governed time + wall clock), state: RESERVED|SUBMITTED|FINALIZED|ABANDONED, outcome}`. Protocol: `reserve()` = lock → capacity + spacing check inside lock → durable append (fsync) → return identity; broker call only with valid reservation; `finalize(outcome)` under lock; crash recovery = scan → all RESERVED-without-outcome treated as CONSUMED (conservative) + reconciliation against session-journal acks (F-19 convergence: both authoritative and bridge paths route through the ledger).
- **Files:** new `runtime/submission_ledger.py`; wire into `runtime/runtime.py` `_execute_plan` (reserve BEFORE venue call; finalize on ack/refusal/UNKNOWN) and `broker_execution.py` bridge; new `tests/test_submission_ledger.py` (+multiprocessing probe `tests/test_submission_ledger_concurrency.py`).
- **Tests (first):** (T1) restart-wipes-budget reproduction on current main (fails now, passes after); (T2) two-process last-slot probe on real filesystem — exactly one winner; (T3) failed reservation leaves no record; (T4) no reservation ⇒ no broker call (instrumented venue double asserts refusal upstream); (T5) kill -9 between reserve and submit → recovery treats as consumed; (T6) ledger-vs-journal reconciliation on restart; (T7) property: measured window ⊇ journalled acks.
- **Acceptance:** all B1 mandate properties hold on the actual filesystem; full suite green; no submission path bypasses the boundary (grep + contract test).
- **Effort:** S-M (new module + wiring + 7 test families). **Risk:** Medium — touches the order path; mitigated by reserve-before-call ordering (refusal happens strictly earlier than today's post-ack accounting) and by keeping the RiskGate check as a second independent layer.

## GROUP P2 — Submission-spacing governor (B2) — mandate + F-06

- **Scope:** `SubmissionGovernor` (in `submission_ledger.py` or sibling `submission_governor.py`): enforces owner-ratified paper defaults — **min 1s between submissions, max 5 per 60s, max 10 open orders** — at the actual submission boundary (the ledger's reserve step); monotonic-protected wall clock (refuse on wall-clock regression ≥ threshold; governed time for determinism, wall clock for spacing); deterministic conservative restart (persisted last-submission timestamps restored as-consumed); venue capability `rate_limit` added to `RUNTIME_PAPER_VENUE_CAPABILITIES` (F-06).
- **Files:** `runtime/submission_ledger.py` (or new governor module), `runtime/broker_execution.py:125-143`, runtime wiring, `tests/test_submission_governor.py`.
- **Tests (first):** (T1) 6th submission in 60s refused at boundary; (T2) <1s spacing refused (injectable clock); (T3) wall-clock regression → conservative refusal + incident ledger entry; (T4) restart preserves last-submission time (reproduction on main fails first); (T5) no alternate path bypasses (muteness test: monkeypatch governor to count calls; every submission route counted); (T6) venue-level refusal independent of runtime gate; (T7) timing model doc test (documented model matches code).
- **Acceptance:** B2 mandate properties; suite green. **Effort:** S. **Risk:** Low-Medium (same seam as P1; landed immediately after P1 on the same branch).

## GROUP P3 — OMS durable outcomes + operator-close paths (B3) — F-07 + mandate transitions

- **Scope:** Recovery/reconciliation rule for journalled-venue-order with OMS order in pre-SUBMITTED state → EXECUTION_UNCERTAIN incident + fail-closed halt + operator report; extend reconciliation driver to distinguish confirmed-absence (venue journal + venue both authoritative) vs timeout/unavailable (preserve ambiguous, never release reservations); operator-close refusal paths tested; any failed durable outcome transition ⇒ incident + halt.
- **Files:** `runtime/broker_execution.py` (recovery), `runtime/reconciliation.py`, `runtime/runtime.py` (incident wiring), `tests/test_oms_durable_outcomes.py`.
- **Tests (first):** controlled faulty doubles (labeled): (T1) venue-ack-recorded/OMS-submit-skipped → recovery halts (fails on main: recovery currently resumes silently); (T2) crash-at-each-transition matrix (accepted / explicit refusal / capacity exhaustion / broker exception pre-ack / ack-then-persistence-failure / UNKNOWN / HALTED liquidation / operator-close refusals / restart / reconciliation failure) — each pinned to expected OMS state; (T3) duplicate ack idempotency; (T4) failed durable transition ⇒ incident + halt (never optimism).
- **Acceptance:** full B3 transition matrix green; suite green. **Effort:** M. **Risk:** Medium (recovery semantics) — conservative direction only; any ambiguity ⇒ halt, never resume.

## GROUP P4 — Locking, fsync, fail-open fixes, deploy/CI hardening (B4) — F-03, F-04, F-08-F-12, F-15, F-16, F-18, F-21, F-22

- **Scope:** (a) store-level flock at `ExecutionStateStore` open + unique tmp names; (b) session journal fsync file+dir; (c) state store dir fsync; (d) SecurityAuditTrail locked append; (e) audit_log fail-closed + operator path; (f) journal tail-recovery subcommand (audited, explicit confirmation); (g) systemd ReadWritePaths + hardening set + validator update; (h) CI matrix 3.13/3.14 + ruff + coverage artifact + bandit; pip-audit on push; secret-scan prefixes; (i) CLI validate arg; (j) test storage tmp_path hygiene.
- **Files:** `runtime/state.py`, `brokers/session.py`, `security.py`, `cli.py`, `deploy/systemd/ai-trading-lab@.service`, `scripts/validate_deployment_templates.py`, `.github/workflows/ci.yml`, `pyproject.toml` (ruff config — new dev dep, changelog-noted), affected tests.
- **Tests (first):** (T1) concurrent store open refused (real flock); (T2) interleave SecurityAuditTrail from 2 processes → linear chain; (T3) unwritable audit path → loud failure; (T4) torn-tail fixture → recovery tool detects/reports/refuses-without-confirmation; (T5) validator rejects strict-without-ReadWritePaths unit; (T6) ruff/bandit clean on changed files; (T7) storage fixtures leave no repo-root dirs.
- **Acceptance:** each finding's criteria in register; suite green ×3 (determinism discipline). **Effort:** M. **Risk:** Low — additive; new dev dep (ruff) noted in changelog per Rule 7.

## GROUP P5 — Stage C composition root + readiness + reconciliation driver (F-05, F-13, F-14, F-25 + C1-C3)

- **Scope:** `src/data_engine/runtime/composition.py`: explicit root constructing in documented order (validated config → state store → durable reservation ledger → governor → OMS → risk/readiness gates → feed services → paper session boundary → audit journal → reconciliation driver → lifecycle); readiness evidence suppliers for the 5 missing gates; feed watchdog mandatory in operational mode; config-injected gate context + risk limits (Part 3 ratified defaults with provenance); MAC key provisioning; reconciliation driver per C3.
- **Tests:** composition test (order-pinned, type-state); readiness flip matrix; supervisor exit-2-until-evidence; reconciliation driver scenarios (duplicate signal, ambiguous preservation, confirmed absence, timeout ≠ release).
- **Acceptance:** C1-C3 mandates; suite green. **Effort:** M-L. **Risk:** Medium — largest additive surface; frozen strategy blobs untouched (CI pins them).

## GROUP P6 — Stage D paper evidence (U-21..U-25)

PAPER-TRADING-READINESS-REPORT.md gate-by-gate; paper-only selection proof; simulation-assumption docs; fault-test battery; soak PROCEDURE (not started); **PAPER_READY = FALSE** at all times.

## GROUP P7 — Stage E Windows package (U-26..U-28)

Zip + install.ps1/run-tests.ps1/run-paper.ps1 + layout/env-secrets/backup docs; fresh-venv validation (Linux-side Wine validation documented as limitation if Windows VM unavailable; validation commands recorded exactly); Release asset + SHA256SUMS + link.

## GROUP P8 — Stage F Android + multi-user + admin (U-29..U-32)

Monitoring API (token auth, loopback default, rate limit, redaction, kill-switch with confirmation); Flutter APK (server URL + token login, multi-profile, secure storage, TLS-only, no embedded secrets, zero default server) via build-apk.yml; deploy/server-install.sh + MULTI-USER-DEPLOYMENT-GUIDE.md; admin registry + panel (one-way outbound heartbeat, data-minization TEST-ENFORCED) + admin-install.sh + ADMIN-PANEL-GUIDE.md; iOS TestFlight path documented only.

## GROUP P9 — Stage G product layer (U-33..U-39, audit-then-extend)

G1 spacing wiring; G2 reporting API (journal-reconciled); G3 multi-asset instruments (remove F-17 hardcode, per-class rules, provenance); G4 allocation engine (greenfield, fail-closed); G5 adapter plugin interface (UNKNOWN = BLOCKED, mock-first); G6 strategy chat + automated backtest + 30-day cycle scheduling + explicit YES gate (compose with existing strategy_lab/evaluation — never weaken; LIVE_ACTIVE stays unreachable); G7 prediction exposure + F-20. Every feature VERIFIED_IMPLEMENTED with tests or explicitly labeled in the readiness matrix.

---

## Sequencing + gates

P1 → P2 → P3 → P4 (Stage B complete: suite green, no unresolved blocker) → P5 (C) → P6 (D) → P7 (E) ∥ P8 (F) → P9 (G) → final deliverables (Part 10).

- Every group: regression tests first → smallest fix → full suite → diff review → static/security checks → commit (feature branch `feat/milestone-a-<group>` series, merged to main only on green suite per Rule 1).
- STOP conditions honored throughout (Part 12). PAPER_READY stays FALSE. No real orders ever — system is structurally paper-only and stays that way.
