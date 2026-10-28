# Release Artifacts — v1.5.0 (paper-ready full upgrade; Windows package + monitor APK)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v1.5.0.zip` | Windows installer package built from merge `a46ac5f` (feature tip `0a566ad`) — the v1.5.0 paper-ready full upgrade: 57-indicator quant pack, TOP-5 YouTuber M1 presets with auto-bootstrap, mandatory TOTP 2FA login, VERIFIED REAL bundled 1m data (BTCUSDT + ETHUSDT, sha256-checked), AUTO-SCAN, crash + next-move ensemble prediction, net-of-cost backtests, paper-only 1-fill/second bursts — on top of the complete v1.1.0 owner AI lab; engine version line 1.5.0 |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the monitor APK pointer) |
| `README-ARTIFACTS.md` | This file |

## The v1.5.0 download set

1. **Windows package (this branch)** —
   `release-artifacts/ai-trading-lab-data-engine-windows-v1.5.0.zip`
   (raw link below). New inside: `create-admin.ps1` (first ADMIN
   account for 2FA login), updated `run-monitor.ps1` (preset
   auto-bootstrap ON by default), bundled `datasets/` (verified real
   1-minute history), README §3a quickstart.
2. **Monitor APK (GitHub Release)** —
   `apk-0a566ad79ae5/ai-trading-lab-monitor.apk` — the SINGLE app
   (v1.5.0+8): EMAIL LOGIN (2FA) with in-app enrollment, admin Users
   screen, START PAPER TRADING card (verified data import + TOP-5
   presets + AUTO-SCAN). The separate ADMIN APK IS RETIRED (source
   removed in this merge; old admin-apk releases remain historical
   artifacts of v1.0.0-v1.1.0 and are obsolete).

## Quickstart (Windows)

```powershell
# after extracting the zip:
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\run-monitor.ps1     # presets auto-bootstrap ON
powershell -ExecutionPolicy Bypass -File .\create-admin.ps1 -Email you@example.com -Name "Owner"
# verify + import REAL data (offline; bundled, checksum-verified):
.\.venv\Scripts\python.exe -m data_engine.cli hist-datasets
.\.venv\Scripts\python.exe -m data_engine.cli hist-import --symbol BTCUSDT --monitor-state-dir .\monitor-state
```

Then in the app: EMAIL LOGIN (2FA) → AI Lab → Strategies → START
PAPER TRADING. LIVE TRADING IS NOT AUTHORIZED; PAPER_READY stays
FALSE; activation of any strategy still requires the owner's
explicit YES.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v1.5.0.zip -Algorithm SHA256
```

Expected: `b6eff2d03b91ca8d6163a035d3592f02e7dd7f925dd60f512e46a06656b887c1`

APK (against the release's own SHA256SUMS.apk.txt):

```powershell
Get-FileHash .\ai-trading-lab-monitor.apk -Algorithm SHA256
```

Expected: `5f38a67f11bc58082160eff952c46425f3a5430cfcc897d244c46edc5df75502`

## Direct links (public, no auth)

- Windows ZIP:
  `https://raw.githubusercontent.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/builds/mt5-windows-v0.4.0/release-artifacts/ai-trading-lab-data-engine-windows-v1.5.0.zip`
- Monitor APK (v1.5.0+8, built by CI from `0a566ad79ae5`):
  `https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-0a566ad79ae5/ai-trading-lab-monitor.apk`

## Install caveats (honest)

- The APK is DEBUG-keystore signed by CI (fresh key each run):
  UNINSTALL the old monitor/admin apps before installing, then
  re-pair or re-login (2FA enrollment repeats if the account was
  reset; existing accounts survive on the PC side).
- Terminal/DEMO MT5 connection remains the documented operator step
  (Python 3.11-3.14 venv); nothing here was live-tested on a Windows
  host (NOT VERIFIED markers in README §9 are the honest posture).
- `PAPER_READY` stays FALSE and `LIVE_AUTHORIZATION` stays
  NOT_AUTHORIZED — by design, unchanged by this release.

## Superseded artifacts (recoverable from git history, never rewritten)

- v1.1.0 package from merge `850030e`+packaging (sha256
  `04bb9dd54c04bfa273471c1408e51af103365f489409957bf86b6b68659b0e29`)
  -> `git checkout 5800aae -- release-artifacts/`
- v1.0.0 package from merge `92c86d1` (sha256 `e3934c604d9bd75f...`)
  -> `git checkout 856ba48 -- release-artifacts/`
- v402 package from `8c8529a` (sha256 `7318cbc9681dbbb5...`)
  -> `git checkout f3dc44c -- release-artifacts/`
- allfixes package from `160d61b` (sha256 `b19b13672ee5aa9c...`)
  -> `git checkout 24aa382 -- release-artifacts/`
