# Release Artifacts — MT5 Windows Package v0.4.0 (py315 + monitor-serve fix)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-monitorfix-336eca8.zip` | Windows installer package built from commit `336eca8` — everything in the py315 package PLUS the monitor-serve fix (below) |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the Android APK pointer) |
| `README-ARTIFACTS.md` | This file |

Superseded artifact: the py315 package built from `6cef076`
(sha256 `473a6114a8d65d6fb04bb226de8bdec378b8b8e8d0d4efa9e16822beef62fe36`)
was removed from this branch tip and remains recoverable from git
history: `git checkout f6fa9ef -- release-artifacts/`.

## What changed vs the py315-6cef076 package (exactly one fix)

`src/data_engine/runtime/service.py`: a **monitor-only** `serve`
(no `--session-launch`, no dashboard, no tick source) now STARTS without
paper-readiness evidence. Previously it was unconditionally refused
(`REFUSING TO START: PAPER_READY = FALSE ... Exit 2`), which blocked the
v4.0 beginner path `run-monitor.ps1` + phone pairing even though that
surface can neither trade nor show a trading dashboard. Trading-ABLE
surfaces (tick source present OR dashboard enabled) still require
passing readiness evidence exactly as before — the fail-closed gate is
NOT weakened for anything that can trade. See `CHANGELOG.md` at the
source commit and the refusal-pin tests in
`tests/test_runtime_service_lifecycle.py`.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-monitorfix-336eca8.zip -Algorithm SHA256
```

Expected:

```
820fa5c32577a23050954d66c9fb12f117389538b1423fe0f110724b8aa90aaa
```

If the hash does not match, do NOT extract or run anything — re-download.

## Python version guidance (evidence-based, 2026-10-27)

- **Python 3.15.x**: SUPPORTED by the engine. Locked deps ship cp315
  wheels (pydantic 2.14.1 / pydantic-core 2.50.1, numpy 2.5.3,
  pandas 3.0.6, zeroconf 0.151.5). Full test suite executed on
  CPython 3.15.0 at this source commit: 2997 passed / 8 skipped /
  0 failed.
  **Exception:** the vendor `MetaTrader5` pip package (operator step,
  NOT part of the locked requirements) ships cp310–cp314 wheels only.
  On 3.15 the MT5 demo probe is blocked until the vendor publishes a
  cp315 wheel. For the MT5 probe specifically, create the venv with
  Python 3.14: `py -3.14 -m venv .venv` (install.ps1 skips creating a
  venv that already exists and uses it).
- **Python 3.14.x**: declared runtime; everything works including MT5.
- **Python 3.11–3.13**: supported (CI matrix).
- **Python <3.11**: not supported (requires-python >=3.11).

## Provenance (exactly how this ZIP was produced)

- Built by the repo's own fail-closed deterministic builder
  `scripts/build_windows_package.py` — refuses dirty trees, packages
  `git archive HEAD` content only, embeds SHA256SUMS for all 581 files.
- Source commit: `336eca8ccde6be9ffe2c4c85b5374c5a8c9c74ed`
  (= this branch; parent chain: `0b1e5e2` verified MT5 feature tip ->
  `cf88433` artifacts -> `0763507` PS 5.1 fix -> `1f5d218` py315 deps ->
  `6cef076` export-ignore packaging hygiene -> `f6fa9ef` py315 artifacts
  -> `336eca8` monitor-serve fix).
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS on
  this exact ZIP.
- `.gitattributes` export-ignore keeps `release-artifacts/` out of the
  packaged source tree (no nested zip).
- Contents include all 3 genuine MT5 modules (`mt5_terminal.py`,
  `mt5_symbol_map.py`, `mt5_market_data.py`), 4 MT5 test files,
  `fake_mt5_lab`, MT5 integration artifacts 03/05/06, and
  `exness_mock.py` (simulation-labeled).
- PS 5.1-safe installers included (pure-ASCII + UTF-8 BOM deploy scripts).

## Android APK (not stored in this branch)

The Android monitoring client APK v0.4.2 is published as a GitHub
Release asset (tag `apk-f023425b5539`, built from mobile branch
`builds/mobile-apk-v0.4.2` = commit `f023425b55390ca91a0e99ba4aeb807ff54f1bcc`
= the monitor-fix commit `336eca8` + app version bump `0.4.2+3`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-f023425b5539/ai-trading-lab-monitor.apk
sha256: 63f681b0602c03b784458c760522f72606c4f425226aadd3e8a420ca374f7d9c
size:   21401296 bytes (versionName 0.4.2 / versionCode 3, verified in the binary manifest)
```

Verify its hash the same way after download.

**Install caveat (applies to every apk-* release):** CI uses a fresh
debug keystore per run, so the signature differs from any previously
installed build — UNINSTALL the old app before installing, then re-pair
(invitation code from `run-monitor.ps1`).

**Honest scope note:** the Dart app code is UNCHANGED since v0.4.0
(dual-mode onboarding: CLOUD SERVER + LOCAL COMPUTER pairing). v0.4.2 is
a version-aligned rebuild whose provenance includes the monitor-serve
fix commit; the fix itself is engine-side (Python), so the phone needs
this APK only for a clean versionCode-ordered install — the behavior
change lands on the PC with the new ZIP above.

## Honest testing status

- Automated suite at source commit, on CPython 3.15.0 (sandbox,
  first-hand): 2997 passed / 8 skipped / 0 failed; the 8 skips are the
  terminal-integration tests, BLOCKED_ON_OPERATOR_ENV by design.
- New refusal-pin tests: monitor-only serve starts WITHOUT evidence;
  tick-source or dashboard surfaces still refuse without evidence.
- Builds-branch pushes are branch-filtered (no CI on push by design) —
  workflow_dispatch results are recorded in the commit message / chat.
- **Real Windows + Exness MT5 DEMO terminal connection: NOT RUN.**
  It requires an actual Windows PC with the MetaTrader 5 terminal
  installed and DEMO account credentials. Run
  `mt5-probe --self-test` after installing (exit 0 = DEMO verified).

## Safety state — UNCHANGED

- `PAPER_READY=FALSE`
- `LIVE_AUTHORIZATION=NOT_AUTHORIZED`
- 30-day soak requirement: in force
- No order-submission path exists in this build (read-only market data
  only; 15+ negative tests cover the adapter).
