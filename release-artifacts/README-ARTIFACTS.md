# Release Artifacts — v1.0.0 (owner control plane + admin panel; Windows package + dual-APK set)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v1.0.0.zip` | Windows installer package built from merge commit `92c86d1` — the v1.0.0 owner control plane (durable STOP flag + client registry + trade ledger + 4 new owner API routes) with the complete prior fix chain, admin panel source under `source/admin/`, and engine version line 1.0.0 |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including both Android APK pointers) |
| `README-ARTIFACTS.md` | This file |

Superseded artifacts (recoverable from git history, never rewritten):

- v402 package from `8c8529a`
  (sha256 `7318cbc9681dbbb5b6790c1c884d5e3903f3e318875cfb2d2e393e2e470f4018`)
  -> `git checkout f3dc44c -- release-artifacts/`
- allfixes package from `160d61b`
  (sha256 `b19b13672ee5aa9cf3c6e2bcf670091eb7a65424998213c5ecaa04568396e375`)
  -> `git checkout 24aa382 -- release-artifacts/`
- monitorfix package from `336eca8`
  (sha256 `820fa5c32577a23050954d66c9fb12f117389538b1423fe0f110724b8aa90aaa`)
  -> `git checkout 9156269 -- release-artifacts/`
- py315 package from `6cef076`
  (sha256 `473a6114a8d65d6fb04bb226de8bdec378b8b8e8d0d4efa9e16822beef62fe36`)
  -> `git checkout f6fa9ef -- release-artifacts/`

## The v1.0.0 owner mandate set (details in CHANGELOG.md)

1. **Real, durable STOP control** (`runtime/control_state.py` + `cli.py`):
   `POST /api/killswitch/activate` now PERSISTS a stop flag under
   `monitor-state\kill_switch_state.json` (survives restarts; corrupt
   file fails safe to INACTIVE). Resume is PC-gated:
   `python -m data_engine.cli control-reset`. The API has NO reset route.
2. **Who is logged in / who ever registered** (`runtime/registry.py`):
   self-reported `X-Client-*` identity headers observed on every
   authenticated request; `GET /api/users` (online now, 90 s window) +
   `GET /api/registrations` (durable first-contact ledger, bounded).
3. **Trade ledger** (`runtime/trade_ledger.py`): append-only JSONL +
   `GET /api/ledger/trades` + `GET /api/ledger/stats` (per-symbol
   counts, total PnL, wins/losses). Honest zeros in monitor-only mode —
   nothing fabricates history.
4. **Admin panel APK** (new `admin/` app): who-is-logged-in, registration
   ledger, trade ledger, STOP button — connect-once setup, secure
   storage only, TLS default with explicit plain-LAN escape.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v1.0.0.zip -Algorithm SHA256
```

Expected:

```
e3934c604d9bd75fbdc9bc4faddecfcea5025b748ad14fc3dbe8d6084faff72b
```

If the hash does not match, do NOT extract or run anything — re-download.

## Python version guidance (evidence-based, 2026-10-27)

- **Python 3.15.x**: SUPPORTED by the engine. Locked deps ship cp315
  wheels (pydantic 2.14.1 / pydantic-core 2.50.1, numpy 2.5.3,
  pandas 3.0.6, zeroconf 0.151.5).
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
  `git archive HEAD` content only, embeds SHA256SUMS for all 596 files.
- Source commit: `92c86d10ff2e3327aeaed6fdd0ca09346dfe995d`
  (`--no-ff` merge of `feat/v1-control-admin-panel` tip `f3b0493`
  into this branch; feat chain: `932f2a3` v1.0.0 feature commit ->
  `55da28f` mobile chart-test fix -> `f3b0493` admin analyze fixes).
- Engine test suite at the feat tip: sandbox full run 3048 passed /
  8 skipped / 0 failed (3.12); CI run on `f3b0493`: 7/7 checks SUCCESS
  (pytest matrix 3.11–3.15 + lint/SAST/coverage + dependency audit).
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS on
  this exact ZIP.
- v1.0.0 markers verified INSIDE the package: `control-reset` in
  cli.py, `/api/ledger/stats` in monitoring.py, `TradesChartCard` in
  mobile/lib/main.dart, `admin/lib/main.dart` present, wheel 1.0.0.
- `.gitattributes` export-ignore keeps `release-artifacts/` out of the
  packaged source tree (no nested zip).
- Contents include the full prior chain: 3 genuine MT5 modules,
  `exness_mock.py` (simulation-labeled), the v4.0.2 field-fix set, and
  the complete admin panel source + its CI workflow.
- PS 5.1-safe installers included (pure-ASCII + UTF-8 BOM deploy scripts).

## Android APKs (not stored in this branch)

Both APKs are published as GitHub Release assets, built by CI from
their build branches:

**Monitoring client v1.0.0** (tag `apk-55da28fedd9f`, run 40538714448,
from `builds/mobile-apk-v1.0.0` = `55da28f`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-55da28fedd9f/ai-trading-lab-monitor.apk
sha256: 45cebd9538f7bcad4a4cfd13d95d1c6215139ff57e85e4525f9d261bc88d7929
size:   21420947 bytes (versionName 1.0.0 / versionCode 6, verified in the binary manifest;
        symbols TradesChartCard / TradesPage / X-Client-Kind confirmed inside libapp.so)
```

**Admin panel v1.0.0** (tag `admin-apk-2f9d6f80f14d`, run 40538929818,
from `builds/admin-apk-v1.0.0` = `2f9d6f8`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/admin-apk-2f9d6f80f14d/ai-trading-lab-admin.apk
sha256: d46e64b0f9eda833f2fe324955ad7e06e75db2b64006b97ebcf345aecf60ef37
size:   21317139 bytes (versionName 1.0.0 / versionCode 1, verified in the binary manifest;
        symbols AdminApiClient / OverviewTab / formatTimestamp confirmed inside libapp.so)
```

Verify each hash the same way after download.

**Install caveat (applies to every apk-*/admin-apk-* release):** CI uses
a fresh debug keystore per run, so the signature differs from any
previously installed build — UNINSTALL the old app before installing,
then re-pair (invitation code from `run-monitor.ps1`). The admin panel
does not pair: it takes the engine URL + token directly.

**Honest scope note:** the Windows package in this directory and the
TWO APKs above are the aligned v1.0.0 set. In monitor-only mode the
trade ledger is honestly empty (`total_trades: 0`) until a composed
paper session records fills; the STOP flag is real and durable, and
governance stays untouched (PAPER_READY=FALSE /
LIVE_AUTHORIZATION=NOT_AUTHORIZED).
