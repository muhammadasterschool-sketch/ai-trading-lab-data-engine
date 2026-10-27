# Release Artifacts — v1.1.0 (owner AI lab; Windows package + dual-APK set)

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v1.1.0.zip` | Windows installer package built from commit `bed1600` — the v1.1.0 owner AI lab (assistant, strategy pipeline backtest→paper→confirm, prediction baseline, bars store + push-bars, broker catalog) on top of the complete v1.0.0 owner control plane and the full prior fix chain; engine version line 1.1.0 |
| `...zip.sha256` | SHA-256 checksum companion |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including both Android APK pointers) |
| `README-ARTIFACTS.md` | This file |

Superseded artifacts (recoverable from git history, never rewritten):

- v1.0.0 package from merge `92c86d1`
  (sha256 `e3934c604d9bd75fbdc9bc4faddecfcea5025b748ad14fc3dbe8d6084faff72b`)
  -> `git checkout 856ba48 -- release-artifacts/`
- v402 package from `8c8529a`
  (sha256 `7318cbc9681dbbb5b6790c1c884d5e3903f3e318875cfb2d2e393e2e470f4018`)
  -> `git checkout f3dc44c -- release-artifacts/`
- allfixes package from `160d61b`
  (sha256 `b19b13672ee5aa9cf3c6e2bcf670091eb7a65424998213c5ecaa04568396e375`)
  -> `git checkout 24aa382 -- release-artifacts/`

## The v1.1.0 owner AI-lab mandate set (details in CHANGELOG.md)

1. **AI assistant (offline, ledger-backed)** — ask "total profit",
   "win rate", "best symbol", "XAUUSD pe kitna profit", "who is logged
   in", "is trading stopped?" — every answer is COMPUTED from the
   owner ledgers (trade ledger, client registry, kill-switch state).
   Deterministic, no external LLM, nothing fabricated.
2. **Strategy pipeline** (monitor APK → AI Lab → Strategies):
   create → RUN BACKTEST (deterministic long/flat runner over YOUR
   uploaded bars) → START PAPER (validation window; the fail-closed G6
   gate refuses early-finish evidence) → CONFIRM (explicit YES/NO
   dialog) → ACTIVATED = PAPER-EVALUATION-ONLY. History enters ONLY
   via `push-bars.ps1` (CSV → POST /api/lab/bars); the lab never
   invents market data.
3. **Prediction** (monitor APK → AI Lab → Predict): momentum-vs-
   volatility statistical baseline per symbol with the disclaimer
   shown in the UI — research, not advice, authorizes nothing.
4. **Broker surface** — GET /api/lab/brokers: the 7 in-repo
   SIMULATION/PAPER adapters + the exact BrokerAdapter contract for
   adding a new broker (code, reviewed in git; credentials NEVER via
   the monitoring API).
5. **Admin panel** (v1.1.0+2) gained a read-only Strategies tab: it
   OBSERVES the pipeline; the monitor APK drives it.

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v1.1.0.zip -Algorithm SHA256
```

Expected:

```
04bb9dd54c04bfa273471c1408e51af103365f489409957bf86b6b68659b0e29
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
  `git archive HEAD` content only, embeds SHA256SUMS for all 601
  files, and (new in v1.1.0) ships ONLY the wheel matching this
  commit's engine version.
- Source commit: `bed1600` (`--no-ff` merge `850030e` of
  `feat/v1-ai-lab` tip `61539dc` into this branch + the two packaging
  pins `8ce8a43`/`bed1600`; feat chain: `d04fdd8` v1.1.0 feature
  commit → `61539dc` analyze fixes).
- Engine test suite at the feat tip: sandbox full run 3099 passed /
  8 skipped / 0 failed (3.12); CI runs: 7/7 checks SUCCESS on
  `61539dc` (feat) — pytest matrix 3.11–3.15 + lint/SAST/coverage +
  dependency audit.
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS on
  this exact ZIP (including `version agreement: 1.1.0 everywhere` and
  all 17 required components — `push-bars.ps1` joined the list).
- v1.1.0 markers verified INSIDE the package: `AssistantEngine`,
  `LabManager`, `/api/lab/strategies` in the engine wheel; `LabPage` /
  `AssistantTab` / `StrategiesTab` / `PredictTab` symbols inside the
  monitor APK's libapp.so; `push-bars.ps1` present.
- `.gitattributes` export-ignore keeps `release-artifacts/` out of
  the packaged source tree (no nested zip).
- PS 5.1-safe installers included (pure-ASCII + UTF-8 BOM deploy
  scripts, push-bars.ps1 included).

## Android APKs (not stored in this branch)

Both APKs are published as GitHub Release assets, built by CI from
their build branches (same commit `61539dc` for both — the aligned
v1.1.0 set):

**Monitoring client v1.1.0** (tag `apk-61539dc8ed7c`, run 40558155946,
from `builds/mobile-apk-v1.1.0` = `61539dc`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/apk-61539dc8ed7c/ai-trading-lab-monitor.apk
sha256: 35dcf634d9c6a7a610f0e1e6d251dcb8d974bd3c75c270d3474991067a4a7225
size:   21878515 bytes (versionName 1.1.0 / versionCode 7, verified in the binary manifest;
        symbols LabPage / AssistantTab / StrategiesTab / PredictTab / labStrategies confirmed inside libapp.so)
```

**Admin panel v1.1.0** (tag `admin-apk-61539dc8ed7c`, run 40558161380,
from `builds/admin-apk-v1.1.0` = `61539dc`):

```
https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/admin-apk-61539dc8ed7c/ai-trading-lab-admin.apk
sha256: b794b7670df1f7b5573118f4b06c67c79fd113632cac5135dae782507cad0eab
size:   21323940 bytes (versionName 1.1.0 / versionCode 2, verified in the binary manifest;
        symbols StrategiesTab / labStrategies confirmed inside libapp.so)
```

Verify each hash the same way after download.

**Install caveat (applies to every apk-*/admin-apk-* release):** CI
uses a fresh debug keystore per run, so the signature differs from any
previously installed build — UNINSTALL the old app before installing,
then re-pair (invitation code from `run-monitor.ps1`). The admin
panel does not pair: it takes the engine URL + token directly.

**Honest scope note:** the Windows package in this directory and the
TWO APKs above are the aligned v1.1.0 set. The strategy pipeline's
ACTIVATED state means PAPER-EVALUATION-ONLY — the engine has NO live
path and governance stays untouched (PAPER_READY=FALSE /
LIVE_AUTHORIZATION=NOT_AUTHORIZED). Prediction output is a
statistical research baseline with its disclaimer, not advice.
