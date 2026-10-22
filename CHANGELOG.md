# CHANGELOG — AI Trading Lab Data Engine

All notable changes under the FULL PROJECT PROMPT v3.0 run
(2026-10-19 → 2026-10-20). History preserved throughout (no reset,
no rebase, no force-push; feature branches merged to main only on
green full suites).

## Stage C — runtime integration (merged 3750dab)

- runtime/composition.py: explicit composition root (documented,
  test-pinned order: config → mac_custody → state_store →
  submission_ledger → governor → runtime → paper_session_boundary →
  reconciliation_driver → readiness_evidence → lifecycle); 32-gate
  readiness evidence chain; ComposedSession.start fail-closed (lists
  exact failed gates); cli status --gates honest per-gate
  dispositions. F-05/F-13/F-14/F-25 closed.
- C3 ReservationReconciler (duplicate signal, ambiguous preservation,
  confirmed absence, timeout ≠ release).

## Stage D — paper-ready evidence (merged b764e35)

- tests/test_paper_mode_selection_proof.py: D1 four-layer
  paper-only selection proof (capabilities registration, venue
  construction, guarded session, vocabulary audit) + paper/live
  unambiguity.
- artifacts/stage-d/: PAPER-SIMULATION-ASSUMPTIONS.md (D2),
  PAPER-SOAK-PROCEDURE.md (D4, NOT STARTED),
  PAPER-TRADING-READINESS-REPORT.md (D5: 32-gate matrix, 30
  VERIFIED_IN_CODE, 2 PENDING_OPERATIONAL_EVIDENCE, PAPER_READY
  FALSE).

## Stage E — Windows package (merged 3e57704 + 7546477)

- deploy/windows/: install.ps1 (fail-closed installer; Python ≥3.11
  gate; isolated venv; --require-hashes locked deps; wheel; smoke
  test), run-tests.ps1, run-paper.ps1 (-Confirm + MAC-key
  enforcement; loopback dashboard), README-WINDOWS-PACKAGE.md
  (layout, secrets env-only, backup/restore, safe shutdown,
  firewall/AV, honest NOT-VERIFIED-on-Windows markers).
- scripts/build_windows_package.py: deterministic zip builder
  (git-archive source, uv-exported hash-pinned lock, wheel,
  SHA256SUMS, normalized mtimes, dirty-tree refusal).
- tests/test_windows_package.py (13 contract tests).
- Forensic git tests skip explicitly in packaged-source (no-.git)
  context (2 were previously vacuous passes — honesty fix).

## Stage F — monitoring + mobile + admin (merged ddb4a2b)

- runtime/monitoring.py: token-authenticated read-only monitoring
  API + kill-switch POST (explicit confirmation + wired activator;
  503 fail-closed otherwise); rate limiting; redacted logging;
  honest provider errors.
- runtime/heartbeat.py: one-way outbound health heartbeat; data
  minimization ENFORCED in builder; https-only; graceful
  degradation.
- CLI serve flags: --monitor-{port,bind,token-file},
  --registry-{url,token-file}, --user-label, --heartbeat-interval;
  tokens via 600-perm files only.
- deploy/admin/: admin_registry.py (server-side minimized ingest,
  read-only panel, offline detection, CSV export, atomic state) +
  admin-install.sh.
- deploy/server-install.sh: one-command per-user VPS deployment.
- mobile/: Flutter monitoring client (TLS-only, secure storage,
  multi-profile, dashboard/alerts/events, kill-switch double
  confirmation) + README-APK.md (release signing + iOS TestFlight
  path).
- .github/workflows/build-apk.yml: reproducible CI APK build
  (verified action SHAs), artifact + GitHub Release attach.
- deploy/MULTI-USER-DEPLOYMENT-GUIDE.md, deploy/ADMIN-PANEL-GUIDE.md.

## Stage G — product feature layer (merged 07514ac)

- submission_ledger.py: G1 confirmed-trade spacing
  (record_fill_confirmation; reserve() reference = later of last
  submission / last confirmed trade).
- runtime/reporting.py: G2 journal-verified trade report.
- brokers/instrument_registry.py: G3 multi-asset per-class rules +
  provenance.
- brokers/allocation.py: G4 capability-aware allocation engine.
- docs/CUSTOM-BROKER-ADAPTER.md: G5 plugin interface.
- runtime/strategy_activation.py + monitoring API strategy routes:
  G6 fail-closed strategy activation gate.
- G7 prediction status exposure (API endpoint + heartbeat field +
  panel row); prediction module audited spec-compliant.
- artifacts/stage-g/FEATURE-VERIFICATION-REPORT.md.

## Post-final hardening supplement (merged 0906279 + 0dcccc2, PR #10)

- U-23 fault battery (tests/test_paper_fault_battery.py, 393 lines):
  restart-with-outstanding-orders, duplicate signals/acks, timeout
  and reconciliation fault injection.
- Simulation behavioral pinning
  (tests/test_simulation_assumptions_doc.py, 278 lines): D2
  assumptions pinned to executable behavior.
- Tamper-proof Windows package validator
  (scripts/validate_windows_package.py, 347 lines +
  tests/test_windows_package_validation.py, 29 tests): structure,
  SHA256SUMS tamper-evidence, forbidden members, unsafe paths,
  version agreement, fail-closed posture pins.
- F-18b secret-scan baseline (FIX-7): named PATTERN + two exact
  synthetic markers (github_pat_11AAAA, github_pat_11REAL) +
  fail-closed git-grep error handling; FIX-5's embedded literal
  filter REMOVED (the literal itself was credential-shaped);
  tests/test_secret_scan_allowlist.py re-pinned (5 tests).
- FIX-8: validator parses the builder's real sha256sum format
  (digest-first) + TestBuilderValidatorFormatAgreement cross-pin;
  the real package validates 8/8 (534 files).
- Suite after supplement: 2735 passed + 1 skipped; CI green on all
  6 jobs (Python 3.11/3.12/3.13/3.14 + lint-sast-coverage +
  audit-dependencies).

## Dependencies

- New RUNTIME dependencies: none (stdlib + declared pydantic/numpy/
  pandas/openpyxl only).
- New DEV dependencies: none beyond the declared pytest (Stage B
  added ruff config per its changelog entry).


## P0-P3 Master Read+Write Audit (2026-10-20, this task)

- FIX-9: runtime/operator_approval.py — TRUSTED operator-approval
  evidence for the three human gates (typed records: principal,
  decision, scope, validity window, artifact digest, reason;
  HMAC-SHA256 signing; composition-root re-verification; stable
  reason codes E_APPROVAL_*/E_EVIDENCE_UNTRUSTED). Plain
  passed=True free-text evidence for human gates is refused
  end-to-end (B-P0-03 closed). 43 adversarial tests.
- FIX-10: runtime/session_launch.py + `cli serve --session-launch` —
  the REAL session wiring (typed launch plan, deterministic replay /
  provider bar sources, SessionTick driven by the supervisor loop,
  exit-code-4 refusals). 24 integration tests prove loop
  advancement, determinism, paper-venue-only routing and
  kill-switch no-new-orders (B-P0-01 closed).
- FIX-11: reports reconciled to the code's own gate classification —
  29 VERIFIED_IN_CODE + 3 PENDING_OPERATIONAL_EVIDENCE
  (REAL_DATA/OPERATIONAL_FEED/GOVERNANCE); 9 executable drift-pin
  tests (B-P0-02 closed).
- FIX-12: submission_ledger.py conditional fcntl import — module
  imports on Windows; constructor refuses with the documented
  fail-closed message (B-P1-09 closed). 4 simulated-absence tests.
- FIX-13: run-paper.ps1 hardening — -SessionPlan passthrough, status
  tool-failure abort, verbatim exit-code propagation (B-P1-10
  closed). +2 contract tests.
- FIX-14: runtime/soak_preflight.py + `cli soak-preflight` —
  executable fail-closed soak preflight (CI-irrelevant by
  structure); 17 tests incl. the MOCK DRY RUN; PAPER-SOAK-PROCEDURE
  updated (B-P2-16 closed). NO soak started.
- artifacts/p0-p3/: the 12-task deliverable set (master audit
  report, bug register, remediation plan, canonical gate matrix,
  market support matrix, secrets/governance checklist, Windows
  platform report, soak dry-run report, owner action checklist).
- PAPER_READY stays FALSE (3 human gates open, owner-side);
  LIVE_TRADING remains NOT AUTHORIZED; historical/backtest data work
  remained excluded throughout.

---

# v4.0 — LOCAL-FIRST ONBOARDING, DUAL-MODE APK + WINDOWS MONITOR (2026-10-23)

Owner-ratified pre-decisions P1–P10 (AI_TRADING_LAB_LOCAL_FIRST_UPGRADE_PROMPT_v4.0.md).
P8 plan approved in-session before implementation. History preserved
throughout (no reset, no rebase, no force-push).

## v4-Stage B — engine pairing + mDNS + CLI

- runtime/pairing.py (NEW): salted-SHA-256 invitation verification
  (constant-time, per-config random salt, committed template carries
  hash ONLY — never a plaintext code), per-IP pairing rate limiter
  (5/min default), stable reason codes (E_PAIRING_DISABLED /
  E_PAIRING_CODE_INVALID / E_PAIRING_RATE_LIMITED), email redaction
  (***@domain), audit lines that NEVER carry code or token.
- runtime/monitoring.py: POST /api/pair — the ONE onboarding endpoint
  handled BEFORE token auth, wired only when a PairingService is
  injected; absent = 503 fail-closed (cloud default). Every other
  route unchanged (token-first; kill-switch 503 honesty preserved).
- runtime/announce.py (NEW): `_aitl-monitor._tcp.local.` mDNS
  announcement via zeroconf; graceful no-mDNS fallback; never fatal.
- cli.py: serve `--pairing-config` / `--mdns-announce` /
  `--mdns-instance`; new `pair-status` subcommand (B4 — prints
  enabled/disabled + attempt cap, never the code); malformed pairing
  config at an explicitly-given path REFUSES startup (token-file
  posture).
- deploy/server-install.sh: `--invitation-code <code>` → salted hash
  at /etc/ai-trading-lab/invitation.hash (0640 root:engine; never
  plaintext, never logged); no flag = pairing disabled; systemd unit
  wired when present.
- Version 0.4.0; NEW runtime dependency `zeroconf` (+`ifaddr` transitively)
  — the only engine-side dependency additions in this release.

## v4-Stage C — APK dual-mode onboarding

- mobile/lib/pairing.dart (NEW): pairWithEngine() client + mDNS
  discovery with graceful manual fallback.
- mobile/lib/main.dart: first-run mode choice (exactly TWO options,
  P2), cloud form (name/https-URL/code, TLS-only), local form
  (name/email/code/PC-address, one-time unencrypted-LAN warning),
  per-profile isLocal transport flag (cloud TLS-only posture
  UNCHANGED), profile mode badges, dashboard Switch action (P6 —
  never deletes profiles/tokens), v0.3.x profile backward compat.
- mobile/pubspec.yaml: version 0.4.0+1; + multicast_dns (only new
  mobile dependency).
- mobile/test/pairing_test.dart (NEW): transport-policy matrix, model
  round-trip, form validation, mDNS prefill seam, pairing client
  contract (MockClient). CI runs `flutter test`; NOT RUN locally (no
  Flutter toolchain — honest).
- .github/workflows/build-apk.yml: idempotent release-manifest patch
  (INTERNET + CHANGE_WIFI_MULTICAST_STATE).

## v4-Stage D — Windows local monitor + packaging pins

- deploy/windows/run-monitor.ps1 (NEW): monitor-only entrypoint; first
  run creates local-monitor.json (salted-hash template) +
  monitor-token.txt; loopback default; -AllowLan = explicit bind +
  UNENCRYPTED-LAN warning + LAN IP + firewall hint + mDNS on.
- deploy/windows/install.ps1: +step 6 component presence check +
  beginner what-next (local-first path documented first).
- build/validate scripts: new required components (run-monitor.ps1,
  local-monitor-config.template.json, source pairing.py + announce.py),
  run-monitor posture pin, strict template shape check, and the
  AITL_INVITE_PROBE owner-side whole-package plaintext scan (structural
  when unset — honest CI posture). Local validation: BUILD-OK +
  VALIDATION OK 10/10 with the probe set (562 packaged files, zero
  plaintext).
- Windows-host execution remains operator evidence (unchanged).

## v4-Stage E — docs replacement

- mobile/README-APK.md: rewritten two-mode onboarding (E1).
- deploy/MULTI-USER-DEPLOYMENT-GUIDE.md: §0 "CLOUD IS OPTIONAL" +
  invitation issuance/rotation/status (E2).
- deploy/windows/LOCAL-MONITOR-RUNBOOK.md (NEW): beginner runbook
  (E3) incl. the code-rotation command.
- Readiness statuses UNTOUCHED: PAPER_READY = FALSE; the 3 human
  gates open; LIVE_TRADING = NOT AUTHORIZED (this task changed
  ONBOARDING, not trading readiness).
