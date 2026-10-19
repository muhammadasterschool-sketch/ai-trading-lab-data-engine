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

## Dependencies

- New RUNTIME dependencies: none (stdlib + declared pydantic/numpy/
  pandas/openpyxl only).
- New DEV dependencies: none beyond the declared pytest (Stage B
  added ruff config per its changelog entry).
