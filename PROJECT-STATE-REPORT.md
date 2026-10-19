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
  matrix: 30 VERIFIED_IN_CODE, 2 PENDING_OPERATIONAL_EVIDENCE
  (REAL_DATA_READY, OPERATIONAL_FEED_READY), zero failed.
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
