# Release Artifacts — MT5 Windows Package v0.4.0 (Python 3.15 support)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-6cef076.zip` | Windows installer package built from commit `6cef076` — genuine read-only Exness MT5 DEMO market-data integration + Python 3.15 support (pydantic 2.14.1 / pydantic-core 2.50.1) + PS 5.1-safe installers |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the Android APK pointer) |
| `README-ARTIFACTS.md` | This file |

Superseded artifact: the pre-3.15 package built from `0b1e5e2`
(sha256 `3a22efab...d9f99`) was removed from this branch tip and remains
recoverable from git history: `git checkout 0763507 -- release-artifacts/`.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-6cef076.zip -Algorithm SHA256
```

Expected:

```
473a6114a8d65d6fb04bb226de8bdec378b8b8e8d0d4efa9e16822beef62fe36
```

If the hash does not match, do NOT extract or run anything — re-download.

## Python version guidance (evidence-based, 2026-10-27)

- **Python 3.15.x**: SUPPORTED by the engine. Locked deps were bumped
  (pydantic 2.14.1, pydantic-core 2.50.1 — first line with cp315
  wheels; numpy 2.5.3 / pandas 3.0.6 / zeroconf 0.151.5 already ship
  cp315). Full test suite executed on CPython 3.15.0: 2994 passed /
  8 skipped / 0 failed.
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
- Source commit: `6cef076eec440f48e9fa3fa0e8f5ef34380c580d`
  (= this branch; parent chain: `0b1e5e2` verified MT5 feature tip ->
  `cf88433` artifacts -> `0763507` PS 5.1 fix -> `1f5d218` py315 deps ->
  `6cef076` export-ignore packaging hygiene).
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS.
- `.gitattributes` export-ignore keeps `release-artifacts/` out of the
  packaged source tree (no nested zip).
- Contents include all 3 genuine MT5 modules (`mt5_terminal.py`,
  `mt5_symbol_map.py`, `mt5_market_data.py`), 4 MT5 test files,
  `fake_mt5_lab`, MT5 integration artifacts 03/05/06, and
  `exness_mock.py` (simulation-labeled).
- The PS 5.1 encoding fix (pure-ASCII + UTF-8 BOM deploy scripts) is
  INCLUDED in this package — no local BOM one-liner needed.

## Android APK (not stored in this branch)

The Android monitoring client APK is published as a GitHub Release
asset (tag `v0.4.0`, target `4cc6782c9804fd689fe524f0d54b1a01817a35c6`
= `main`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/v0.4.0/ai-trading-lab-monitor.apk
sha256: fbaac5c0a4d4b03bab793bfcf34b0bbea5a0b40d3a4d4ca5c97f34553e56d3bc
```

That APK was built from the `mobile/` Flutter sources at `main`
(v0.4.0 dual-mode onboarding: CLOUD SERVER + LOCAL COMPUTER pairing).
Verify its hash the same way after download.

## Honest testing status

- Automated suite at source commit, on CPython 3.15.0 (sandbox,
  first-hand): 2994 passed / 8 skipped / 0 failed; the 8 skips are the
  terminal-integration tests, BLOCKED_ON_OPERATOR_ENV by design.
- CI matrix now includes 3.15; builds-branch pushes are branch-filtered
  (no CI on push by design) — workflow_dispatch results, if any, are
  recorded in the commit message / chat.
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
