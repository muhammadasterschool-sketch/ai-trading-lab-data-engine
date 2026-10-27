# Release Artifacts — MT5 Windows Package v0.4.0 (py315 + all field fixes)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-allfixes-160d61b.zip` | Windows installer package built from merge commit `160d61b` — the py315 package PLUS both field fixes (monitor-serve gate + mobile dashboard parsing), with the fixed app source included under `source/mobile/` |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the Android APK pointer) |
| `README-ARTIFACTS.md` | This file |

Superseded artifacts (recoverable from git history, never rewritten):

- monitorfix package from `336eca8`
  (sha256 `820fa5c32577a23050954d66c9fb12f117389538b1423fe0f110724b8aa90aaa`)
  -> `git checkout 9156269 -- release-artifacts/`
- py315 package from `6cef076`
  (sha256 `473a6114a8d65d6fb04bb226de8bdec378b8b8e8d0d4efa9e16822beef62fe36`)
  -> `git checkout f6fa9ef -- release-artifacts/`

## What changed vs the monitorfix-336eca8 package

Engine source is UNCHANGED (zero Python diffs). This rebuild aligns the
package with the mobile fix commit so one ZIP contains the whole verified
state:

- `mobile/lib/main.dart`: `positions()`/`orders()` parsed defensively
  (JSON arrays accepted) — fixes the phone dashboard
  "connection error (_TypeError)" that appeared AFTER successful pairing
  because the monitor-only API returns `[]` for collection endpoints
  while the app cast every response to a Map. `pnl()` also normalized.
- `mobile/pubspec.yaml`: app version `0.4.3+4` (APK v0.4.3,
  versionCode 4).
- `CHANGELOG.md`: full entries for both fixes.

The two field fixes included (details in CHANGELOG.md at the source
commit):

1. **Monitor-serve gate fix** (`src/data_engine/runtime/service.py`,
   `336eca8`): a monitor-only `serve` (no `--session-launch`, no
   dashboard, no tick source) STARTS without paper-readiness evidence.
   Previously it was refused unconditionally
   (`REFUSING TO START: PAPER_READY = FALSE ... Exit 2`). Trading-ABLE
   surfaces (tick source OR dashboard) still require passing evidence —
   the fail-closed gate is NOT weakened for anything that can trade.
2. **Mobile dashboard parse fix** (`mobile/lib/main.dart`, `897ec56`):
   collection endpoints accept JSON arrays; no more `_TypeError` after
   successful pairing.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-py315-allfixes-160d61b.zip -Algorithm SHA256
```

Expected:

```
b19b13672ee5aa9cf3c6e2bcf670091eb7a65424998213c5ecaa04568396e375
```

If the hash does not match, do NOT extract or run anything — re-download.

## Python version guidance (evidence-based, 2026-10-27)

- **Python 3.15.x**: SUPPORTED by the engine. Locked deps ship cp315
  wheels (pydantic 2.14.1 / pydantic-core 2.50.1, numpy 2.5.3,
  pandas 3.0.6, zeroconf 0.151.5). Full test suite executed on
  CPython 3.15.0: 2997 passed / 8 skipped / 0 failed.
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
- Source commit: `160d61ba2a69d7464af0a730d74f8b38f0e884b2`
  (merge commit on this branch; parents: `9156269` monitorfix artifacts
  -> `336eca8` monitor-serve fix, and `897ec56` mobile v0.4.3 fix ->
  `f023425` mobile v0.4.2 bump -> `336eca8`). Full parent chain back:
  `0b1e5e2` verified MT5 feature tip -> `cf88433` artifacts ->
  `0763507` PS 5.1 fix -> `1f5d218` py315 deps -> `6cef076`
  export-ignore packaging hygiene -> `f6fa9ef` py315 artifacts.
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

The Android monitoring client APK **v0.4.3** is published as a GitHub
Release asset (tag `apk-897ec56a6032`, built by CI run 40523413756 from
`builds/mobile-apk-v0.4.3` = commit
`897ec56a603237ef98e6125aa9e20ccc501da0bd` = the dashboard parse fix +
app version bump `0.4.3+4`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-897ec56a6032/ai-trading-lab-monitor.apk
sha256: b69918d5c3594021438afe8542d769b4bfa6b2f25e6c03f2adc9eb4a44c34433
size:   21402398 bytes (versionName 0.4.3 / versionCode 4, verified in the binary manifest;
        fix symbol _getDynamic confirmed inside libapp.so)
```

Verify its hash the same way after download.

**Install caveat (applies to every apk-* release):** CI uses a fresh
debug keystore per run, so the signature differs from any previously
installed build — UNINSTALL the old app before installing, then re-pair
(invitation code from `run-monitor.ps1`).

**Honest scope note:** v0.4.3 contains ONE Dart change (defensive JSON
parsing for collection endpoints) on top of the v4.0 dual-mode
onboarding (CLOUD SERVER + LOCAL COMPUTER pairing). Server-side monitor
behavior is unchanged by the mobile fix; the Windows package in this
directory and the APK above are the aligned pair to use together.
