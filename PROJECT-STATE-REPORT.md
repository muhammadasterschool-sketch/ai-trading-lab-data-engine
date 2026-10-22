# PROJECT-STATE-REPORT — AI TRADING LAB DATA ENGINE
## FULL PROJECT PROMPT v3.0 — full-run state report

Report date: 2026-10-20. Repository:
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine
Final main HEAD at report time: see §7 (verification) — every stage
below lists its merge commit.

---

## 0. Top-line statuses (reported separately, never inferred)

| Status | Value | Basis |
| --- | --- | --- |
| CORE_ENGINE_VERIFIED | **TRUE** | Stage A audit (25 findings, 6H/10M/9L-I) + Stage B P1-P4 fixes + suites |
| INTEGRATION_VERIFIED | **TRUE** | Stage C composition root / readiness suppliers / C3 reconciler + suites |
| PAPER_EVIDENCE_COMPLETE | **TRUE** (dev-run scope) | Stage D D1-D5 (operational/soak evidence intentionally absent) |
| WINDOWS_PACKAGE | **TRUE** (Linux-side validated; Windows-host run = operator evidence) | Stage E E1-E2 + E3 release |
| ANDROID_APK | **TRUE** (CI-built, debug-signed) | Stage F F2-F3 workflow + release |
| MULTI_USER_DEPLOYMENT | **TRUE** | Stage F F5 + guides |
| ADMIN_REGISTRY_PANEL | **TRUE** | Stage F F6 + tests |
| PRODUCT_FEATURE_LAYER | **TRUE** (see FEATURE-VERIFICATION-REPORT for the PARTIAL residuals) | Stage G G1-G7 |
| **PAPER_READY** | **FALSE** | Owner decision + 30-day soak NOT started (per Part 2 Rule 3) |
| LIVE_TRADING | **NOT AUTHORIZED — permanently out of scope** | structural four-layer enforcement + tests |

## 1. Stage A — full analysis + audit (merged 5d700ed)

- Identity re-verified (branch main, HEAD 4e9be35 at the time, clean
  tree, fsck clean, origin verified); historical C1/C2 commit
  confirmed ABSENT — Milestone A treated as fresh implementation.
- Baseline suite ACTUALLY run: **2403 passed + 1 skipped** (the
  historical claim was thereby verified, not assumed).
- Deliverables: artifacts/stage-a/{00-REPO-IDENTITY,
  01-MASTER-AUDIT-REPORT, 02-FINDINGS-REGISTER, 03-UPGRADE-BACKLOG,
  04-PATCH-PLAN}.md — 25 findings (6 HIGH / 10 MEDIUM / 9 LOW-INFO),
  READ+WRITE path map, ordered patch plan P1-P9.

## 2. Stage B — upgrades + Milestone A (merged 09127e6 via PR #7)

- P1 (B1) durable submission-rate ledger: flock-protected durable
  reservations; reserve→submit→finalize; cross-process last-slot
  race proven on the real filesystem; conservative crash recovery.
- P2 (B2) submission-spacing governor: owner-ratified defaults (min
  1s, max 5/60s, max 10 open orders) at the actual submission
  boundary; wall-clock regression fail-closed.
- P3 (B3) OMS durable outcomes: full transition matrix (accepted /
  refusal / capacity / exception pre-ack / ack-then-persistence-
  failure / UNKNOWN / HALTED liquidation / operator-close refusals /
  restart / reconciliation failure); failed durable transition ⇒
  incident + halt.
- Venue-level rate backstop (F-06) + B4 hardening sweep
  (F-03/04/08/09/10/12/15/16/18/21/22): store flock, fsync
  file+dir, locked audit append, fail-closed audit_log, journal
  tail-recovery subcommand with explicit confirmation, systemd
  ReadWritePaths, CI matrix 3.11-3.14 + ruff/bandit/pip-audit.
- Suite at stage end: 2439 passed + 1 skipped; every defect fixed
  test-first.

## 3. Stage C — runtime integration (merged 3750dab)

- Explicit composition root (runtime/composition.py, 1129 lines):
  documented, test-pinned construction order; no hidden globals;
  ComposedSession.start refuses unless the FULL 32-gate evidence
  chain is present (lists exact failed gates).
- Readiness suppliers wired; feed watchdog mandatory in operational
  mode (F-13); gate context + risk limits config-injected (F-14);
  MAC custody via operator channel (F-25).
- C3 conservative reconciliation driver: duplicate-signal, ambiguous
  preservation, confirmed absence, timeout ≠ release.
- Suite: 2491 passed + 1 skipped (107.51s) on the branch before
  merge.

## 4. Stage D — paper-ready evidence (merged b764e35)

- D1: four-layer paper-only selection proof
  (tests/test_paper_mode_selection_proof.py, 10 tests).
- D2: artifacts/stage-d/PAPER-SIMULATION-ASSUMPTIONS.md (fills,
  partial fills, TTL, rejections, slippage/impact, fees, latency —
  file:line evidence for both simulation surfaces).
- D3: fault-battery evidence map (all five mandated scenarios pinned
  by cited Stage B/C suites; zero duplication).
- D4: artifacts/stage-d/PAPER-SOAK-PROCEDURE.md — documented, NOT
  STARTED.
- D5: artifacts/stage-d/PAPER-TRADING-READINESS-REPORT.md — 32-gate
  matrix: 29 VERIFIED_IN_CODE, 3 PENDING_OPERATIONAL_EVIDENCE
  (REAL_DATA_READY, OPERATIONAL_FEED_READY, GOVERNANCE_READY — the
  three HUMAN_EVIDENCE_GATES; reconciled by FIX-11/B-P0-02 on
  2026-10-20 to match the code's own gate classification and
  docs/READINESS_EVIDENCE_INVENTORY.md), zero failed.
  **PAPER_READY = FALSE.**
- Suite: 2501 passed + 1 skipped.

## 5. Stage E — Windows package (merged 3e57704 + 7546477)

- E1: deploy/windows/{install.ps1, run-tests.ps1, run-paper.ps1,
  README-WINDOWS-PACKAGE.md} + deterministic builder
  scripts/build_windows_package.py + 13 contract tests.
- E2 (Linux-side, honest): fresh venv → `pip install
  --require-hashes` locked deps → engine wheel → FULL suite from the
  packaged source: 2508 passed + 7 skipped (93.03s, exit 0);
  SHA256SUMS verified (500 files, 0 mismatches). Windows-host
  execution of the ps1 scripts: NOT VERIFIED in this run (no Windows
  VM) — the operator runs install.ps1/run-tests.ps1 and records the
  output as final packaging evidence (same honest posture as Batch
  18).
- E3: package published as a GitHub Release asset + SHA256SUMS (see
  §8 links). Required Python: >=3.11 (declared runtime 3.14;
  3.12+ recommended).
- Genuine defect found + fixed by the validation: forensic git tests
  in packaged-source context (FIX-1 in FIX-LOG.md).

## 6. Stage F — monitoring + mobile + admin (merged ddb4a2b)

- F1 monitoring API (runtime/monitoring.py): token auth (401
  matrix), rate limit (429), read-only endpoints + kill-switch POST
  requiring explicit confirmation + wired activator (409/503
  fail-closed), redacted logging, honest provider errors, no order-
  submission route (structural proof).
- F2 Flutter client (mobile/): server-URL + personal-token login,
  TLS-only, secure-storage tokens, multi-profile (one active),
  dashboard + alerts + events, kill-switch double confirmation.
- F3 build-apk.yml: reproducible CI build (actions pinned to
  VERIFIED full commit SHAs), debug-keystore signing (release
  signing documented), artifact + GitHub Release attach via built-in
  GITHUB_TOKEN (zero user secrets).
- F4 iOS TestFlight path documented (mobile/README-APK.md) — NOT
  built.
- F5 deploy/server-install.sh: one-command per-user VPS deployment
  (dedicated user, hardened systemd, generated secrets root:aitl
  0640, nginx + Let's Encrypt, ufw, health check) +
  MULTI-USER-DEPLOYMENT-GUIDE.md.
- F6 admin registry + panel (deploy/admin/): server-side data
  minimization (reject-400 + never stored), read-only mobile-friendly
  panel (online/offline, last seen, mode/version/feed/risk/kill-
  switch/prediction, alerts, filter, CSV export), no control channel
  (source-audit test), atomic state, backup cron +
  ADMIN-PANEL-GUIDE.md. Heartbeat: one-way outbound, graceful
  degradation, data minimization TEST-ENFORCED engine-side AND
  server-side.
- Suites: 2602 passed + 1 skipped.

## 7. Stage G — product feature layer (merged 07514ac)

G1-G7 audit-then-extend; per-feature EXISTED/ADDED/PARTIAL matrix in
artifacts/stage-g/FEATURE-VERIFICATION-REPORT.md. Highlights:
confirmed-trade spacing (G1), journal-verified reporting API (G2),
multi-asset instrument rules (G3), allocation engine (G4), plugin
interface docs (G5), fail-closed strategy activation gate + API (G6),
prediction status exposure (G7). Suite: 2685 passed + 1 skipped.

## 7b. Post-final hardening supplement (merged 0906279 + 0dcccc2)

Continuation-session close-out of the parallel-delivery branch
(PR #10, `feat/milestone-a-supplement`) plus two self-caught fixes:

- U-23 fault battery (restart/duplicate/timeout/reconciliation
  faults) + simulation behavioral pinning + tamper-proof Windows
  package validator — see CHANGELOG "Post-final hardening
  supplement".
- FIX-7: the F-18b secret-scan baseline (two exact short synthetic
  markers, fail-closed tool-error handling); CI green on ALL SIX
  jobs at 0906279 — the first fully-green main since Stage F (FIX-5
  had left every test job red: its embedded filter literal was
  itself credential-shaped).
- FIX-8: the package validator now parses the builder's real
  sha256sum format; the REAL rebuilt package validates 8/8 (534
  files, tamper-evident); builder/validator format agreement is
  source-level cross-pinned by tests.
- Final suite: **2735 passed + 1 skipped**; final HEAD recorded in
  the GitHub Release (the release asset SHA256SUMS files are
  authoritative for the published artifacts).

## 8. Final deliverables + links

| Deliverable | Location |
| --- | --- |
| PROJECT-STATE-REPORT.md | this file (repo root + download/reports/) |
| FEATURE-VERIFICATION-REPORT.md | artifacts/stage-g/ |
| CHANGELOG.md / FIX-LOG.md | repo root |
| Stage reports | artifacts/stage-{a,d,g}/ + docs/WINDOWS_INSTALLER_AND_PACKAGING.md (Stage E addendum) |
| Windows package (zip + SHA256SUMS) | GitHub Release asset — see RELEASE-LINKS below |
| Android APK (debug-signed + SHA256) | GitHub Release asset (CI build) — see RELEASE-LINKS below |
| Per-user server install | deploy/server-install.sh (in repo + release) |
| Admin registry + panel install | deploy/admin/admin-install.sh (in repo + release) |
| Deployment guides | deploy/MULTI-USER-DEPLOYMENT-GUIDE.md, deploy/ADMIN-PANEL-GUIDE.md |

RELEASE-LINKS (published at report time — final URLs recorded in the
GitHub Release; see the release attached to the final tag):
- Windows package: `ai-trading-lab-data-engine-windows-v0.3.0.zip`
  (built from the final main commit by
  scripts/build_windows_package.py; SHA256 in SHA256SUMS.txt inside
  the zip and in the release notes).
- Android APK: `ai-trading-lab-monitor.apk` + `SHA256SUMS.apk.txt`
  (built by .github/workflows/build-apk.yml from the same tree).

## 9. Verification protocol (how to re-verify everything)

```
git clone https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git
cd ai-trading-lab-data-engine
uv sync --extra dev
uv run pytest -q        # FULL suite (final tree)
uv run pytest tests/test_paper_mode_selection_proof.py -q   # D1
uv run python scripts/build_windows_package.py             # E1/E3
```
CI: .github/workflows/ci.yml (Python 3.11/3.12/3.13/3.14 matrix,
ruff, bandit, pip-audit, secret-scan) runs on every push.

## 10. Residual risks + honest limitations

1. PAPER_READY = FALSE by mandate: the 30-day soak has NOT started;
   REAL_DATA_READY / OPERATIONAL_FEED_READY need live-feed evidence.
2. Windows-host ps1 execution + APK-on-device behavior are operator
   evidence items (scripts are fail-closed and Linux-side-validated;
   same posture as the repo's Batch 18 honesty markers).
3. APK is debug-keystore signed (release signing documented for
   later); iOS not built (TestFlight path documented).
4. Mobile strategy-chat UI + dedicated prediction card are residual
   polish (engine-side APIs complete + tested) — see the Stage G
   feature verification matrix.
5. Live trading is PERMANENTLY out of scope; no live path exists in
   this repository (four-layer enforcement, test-pinned).


## 11. P0-P3 Master Read+Write Audit (2026-10-20, this task)

Baseline audited: main @ 1e66d5a (clean tree; suite 2735 + 1 skipped
re-executed this run). Every candidate B-P0-01 … B-P3-16 was
investigated against current source; the full register with
dispositions lives in `artifacts/p0-p3/01-BUG-AND-GAP-REGISTER.md`.

Fixed this task (each with regression tests, details in FIX-LOG):

- FIX-9 (B-P0-03, CRITICAL): human-gate evidence trust boundary —
  signed operator approvals (typed records + HMAC + re-verification
  in the composition root); fabricated passed=True free-text
  evidence is refused end-to-end. runtime/operator_approval.py + 43
  adversarial tests.
- FIX-10 (B-P0-01, HIGH): REAL session wiring —
  runtime/session_launch.py + `cli serve --session-launch` (exit 4
  refusals); 24 integration tests prove the supervisor loop drives a
  composed paper session (deterministic advancement, paper-venue-only
  routing, kill-switch no-new-orders).
- FIX-11 (B-P0-02): reports reconciled to the code's gate
  classification — 29 VERIFIED_IN_CODE + 3 PENDING (§4 D5 above);
  pinned by 9 executable consistency tests.
- FIX-12 (B-P1-09): submission_ledger conditional fcntl import —
  documented fail-closed refusal on non-POSIX hosts instead of an
  import crash.
- FIX-13 (B-P1-10): run-paper.ps1 — status-tool failure aborts;
  -SessionPlan passthrough; exit codes propagate verbatim.
- FIX-14 (B-P2-16): executable soak preflight (runtime/soak_preflight
  .py + `cli soak-preflight`, exit 0/6, CI-irrelevant by structure) +
  deterministic MOCK DRY RUN. NO soak started.

Deliverables: artifacts/p0-p3/00…08 (audit report, bug register,
remediation plan, canonical gate matrix, market support matrix,
secrets/governance checklist, Windows platform report, soak dry-run
report, owner action checklist).

Readiness after this task (unchanged verdicts, now machine-guarded):
PAPER_READY = FALSE (REAL_DATA_READY, OPERATIONAL_FEED_READY,
GOVERNANCE_READY — owner-side provisioning; human gates now require
SIGNED approvals); LIVE_TRADING = NOT AUTHORIZED; historical/
backtest data work remained excluded and no data gate was flipped.
Final decision: `BLOCKED — DO NOT START PAPER TRADING` until the
owner-side checklist closes (artifacts/p0-p3/08).

---

# v4.0 SUPPLEMENT — LOCAL-FIRST ONBOARDING, DUAL-MODE APK, WINDOWS MONITOR (2026-10-23)

Scope: AI_TRADING_LAB_LOCAL_FIRST_UPGRADE_PROMPT_v4.0.md (owner-ratified
P1–P10; P8 plan posted in-session and approved BEFORE any
implementation code). This task changed ONBOARDING and MONITORING
packaging only. **It did NOT touch any trading-readiness surface.**

## What v4.0 added (feature branch → main; per-stage commits with green suites)

- Engine: runtime/pairing.py (salted-hash invitation pairing,
  constant-time, per-IP rate limit, fail-closed reason codes, email
  redaction), POST /api/pair (pre-token-auth onboarding endpoint;
  absent config = 503 disabled), runtime/announce.py (mDNS
  `_aitl-monitor._tcp.local.`, graceful fallback), CLI `pair-status`
  + serve flags (`--pairing-config`, `--mdns-announce/--mdns-instance`).
- Cloud: `server-install.sh --invitation-code <code>` →
  /etc/ai-trading-lab/invitation.hash (salted hash only, 0640).
- APK: two-option first-run (CLOUD/LOCAL), compulsory invitation-code
  pairing per mode, per-profile `isLocal` transport flag (CLOUD TLS-only
  posture UNCHANGED; local http explicitly scoped + one-time warning),
  mDNS prefill with manual fallback, profile badges + Switch (nothing
  deleted), v0.3.x profile backward compatibility, mobile tests.
- Windows package: run-monitor.ps1 (monitor-only; loopback default;
  -AllowLan with honest warning), salted-hash template, install.ps1
  component check + beginner flow, builder/validator pins incl.
  owner-side AITL_INVITE_PROBE plaintext scans; package v0.4.0 built +
  validated 10/10 locally (Windows-host run remains operator evidence).
- Docs: README-APK.md (two-mode), MULTI-USER-DEPLOYMENT-GUIDE.md §0
  ("CLOUD IS OPTIONAL" + issuance/rotation), LOCAL-MONITOR-RUNBOOK.md,
  CHANGELOG/FIX-LOG entries, this supplement.

## Secrets posture (v4.0 additions)

- Invitation codes: salted SHA-256 hashes ONLY (committed template +
  cloud install path); plaintext never in git, never in the APK, never
  in logs; repo-wide and whole-package probe scans test-enforced
  (owner-side env AITL_INVITE_PROBE; CI runs the structural subset —
  honest, recorded).
- The owner's GitHub PAT used for push/release was provided in-chat
  (contrary to P9 transport guidance): stored only OUTSIDE the repo
  (workspace credential file, 0600), never committed, remote URL
  sanitized. Rotation recommended post-task.
- The APK binary contains ZERO secrets, ZERO code values, ZERO
  default addresses (unchanged).

## Readiness statuses — UNCHANGED (verified, not assumed)

| Status | Value |
| --- | --- |
| PAPER_READY | **FALSE** (unchanged — the 3 human gates remain open: REAL_DATA_READY, OPERATIONAL_FEED_READY, GOVERNANCE_READY) |
| LIVE_TRADING | **NOT AUTHORIZED — permanently out of scope** (four-layer enforcement untouched) |
| ONBOARDING | local-first + cloud dual-mode shipped (this task) |

## Honest NOT-RUN / limitations record (v4.0)

- Flutter tests + APK build: CI only (no Flutter toolchain locally).
- Windows-host execution of the .ps1 scripts: operator evidence.
- mDNS on Android: graceful degradation assumed; manual entry always
  documented.
- APK remains debug-signed; release signing documented-only. No iOS
  (P10).
