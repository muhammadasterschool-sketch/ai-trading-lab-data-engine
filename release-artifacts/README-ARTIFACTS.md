# Release Artifacts — MT5 Windows Package v0.4.0 (py315, v4.0.2 field-fix set)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-v402-8c8529a.zip` | Windows installer package built from merge commit `8c8529a` — the complete v4.0.2 field-fix set (monitor-serve gate + mobile array parsing + default-provider ERROR fix + rate-limit headroom), with the fixed app source included under `source/mobile/` |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the Android APK pointer) |
| `README-ARTIFACTS.md` | This file |

Superseded artifacts (recoverable from git history, never rewritten):

- allfixes package from `160d61b`
  (sha256 `b19b13672ee5aa9cf3c6e2bcf670091eb7a65424998213c5ecaa04568396e375`)
  -> `git checkout 24aa382 -- release-artifacts/`
- monitorfix package from `336eca8`
  (sha256 `820fa5c32577a23050954d66c9fb12f117389538b1423fe0f110724b8aa90aaa`)
  -> `git checkout 9156269 -- release-artifacts/`
- py315 package from `6cef076`
  (sha256 `473a6114a8d65d6fb04bb226de8bdec378b8b8e8d0d4efa9e16822beef62fe36`)
  -> `git checkout f6fa9ef -- release-artifacts/`

## The four field fixes included (details in CHANGELOG.md)

1. **Monitor-serve gate fix** (`service.py`, `336eca8`): monitor-only
   `serve` starts without paper-readiness evidence; trading-ABLE
   surfaces still require it (gate NOT weakened).
2. **Mobile array parsing fix** (`mobile/lib/main.dart`, `897ec56`):
   collection endpoints (positions/orders) accept JSON arrays — no more
   "connection error (_TypeError)" after successful pairing.
3. **Default-provider ERROR fix** (`monitoring.py`, `e6379a7`): the
   pnl/feed/risk/killswitch defaults are now zero-arg lambdas; the
   dashboard shows honest `ABSENT` instead of
   "provider failure (redacted): TypeError" for not-wired components
   (owner screen recording reproduced the symptom).
4. **Rate-limit headroom** (`monitoring.py` default 60 -> 300/min +
   mobile poll 10 s -> 15 s, `35cec82`): the dashboard's normal polling
   pattern no longer trips 429 bursts; brute-force friction retained.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-v402-8c8529a.zip -Algorithm SHA256
```

Expected:

```
7318cbc9681dbbb5b6790c1c884d5e3903f3e318875cfb2d2e393e2e470f4018
```

If the hash does not match, do NOT extract or run anything — re-download.

## Python version guidance (evidence-based, 2026-10-27)

- **Python 3.15.x**: SUPPORTED by the engine. Locked deps ship cp315
  wheels (pydantic 2.14.1 / pydantic-core 2.50.1, numpy 2.5.3,
  pandas 3.0.6, zeroconf 0.151.5). Full test suite executed on
  CPython 3.15.0 and 3.12 in this session: 3003 passed / 8 skipped /
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
- Source commit: `8c8529a00d165ed9d8360a58b3abc8118754e2d6`
  (merge of `e6379a7` engine v4.0.2 fix into this branch, then
  `builds/mobile-apk-v0.4.4` = `35cec82`). Full chain back:
  `24aa382` allfixes artifacts -> `160d61b` merge -> `897ec56` mobile
  v0.4.3 fix -> `9156269` monitorfix artifacts -> `336eca8` monitor-
  serve fix -> `f6fa9ef` py315 artifacts -> `6cef076` export-ignore ->
  `1f5d218` py315 deps -> `0763507` PS 5.1 fix -> `cf88433` artifacts
  -> `0b1e5e2` verified MT5 feature tip.
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS on
  this exact ZIP.
- Fix markers verified INSIDE the package: `lambda: _absent` (5 hits in
  monitoring.py) and `_statusException` (4 hits in mobile/lib/main.dart).
- `.gitattributes` export-ignore keeps `release-artifacts/` out of the
  packaged source tree (no nested zip).
- Contents include all 3 genuine MT5 modules (`mt5_terminal.py`,
  `mt5_symbol_map.py`, `mt5_market_data.py`), 4 MT5 test files,
  `fake_mt5_lab`, MT5 integration artifacts 03/05/06, and
  `exness_mock.py` (simulation-labeled).
- PS 5.1-safe installers included (pure-ASCII + UTF-8 BOM deploy scripts).

## Android APK (not stored in this branch)

The Android monitoring client APK **v0.4.4** is published as a GitHub
Release asset (tag `apk-35cec826d5cc`, built by CI run 40530057392 from
`builds/mobile-apk-v0.4.4` = commit
`35cec826d5ccaec1808f4a89630107ee9ad4840a` = the 429-handling fix +
15 s poll + app version bump `0.4.4+5`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-35cec826d5cc/ai-trading-lab-monitor.apk
sha256: 185f45f1028bd9330856ae46b6ae0d04eb516ddd89e4ee3247d2cf0606458f36
size:   21402642 bytes (versionName 0.4.4 / versionCode 5, verified in the binary manifest;
        fix symbol _statusException confirmed inside libapp.so)
```

Verify its hash the same way after download.

**Install caveat (applies to every apk-* release):** CI uses a fresh
debug keystore per run, so the signature differs from any previously
installed build — UNINSTALL the old app before installing, then re-pair
(invitation code from `run-monitor.ps1`).

**Honest scope note:** v0.4.4 contains TWO Dart changes over v0.4.2
(defensive JSON parsing for collection endpoints in v0.4.3; honest 429
mapping + 15 s poll in v0.4.4) on top of the v4.0 dual-mode onboarding
(CLOUD SERVER + LOCAL COMPUTER pairing). The Windows package in this
directory and the APK above are the aligned pair to use together.
