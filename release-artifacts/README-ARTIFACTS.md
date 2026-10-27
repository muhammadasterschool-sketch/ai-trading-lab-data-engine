# Release Artifacts — MT5 Windows Package v0.4.0

This directory contains **verified build artifacts**. Everything here is
read-only deliverable content; it changes NO engine code, NO tests, and
NO governance state.

## What is here

| File | What it is |
|------|------------|
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-0b1e5e2.zip` | Windows installer package built from commit `0b1e5e2` (feat/exness-mt5-demo-market-data tip) — genuine read-only Exness MT5 DEMO market-data integration |
| `ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-0b1e5e2.zip.sha256` | SHA-256 checksum companion for the ZIP |
| `SHA256SUMS.txt` | SHA-256 of every artifact here (including the Android APK pointer) |

## Verification (do this before trusting any download)

PowerShell (Windows):

```powershell
Get-FileHash .\ai-trading-lab-data-engine-windows-v0.4.0-exness-mt5-0b1e5e2.zip -Algorithm SHA256
```

Expected:

```
3a22efab9314005825f82f481a90004d8b95078b0dfb37c0a3ee666c484d9f99
```

If the hash does not match, do NOT extract or run anything — re-download.

## Provenance (exactly how this ZIP was produced)

- Built by the repo's own fail-closed deterministic builder
  `scripts/build_windows_package.py` — refuses dirty trees, packages
  `git archive HEAD` content only, embeds SHA256SUMS for all 580 files.
- Source commit: `0b1e5e27b6a90be57c501e6cf83ec55869ec552a`
  (= tip of `feat/exness-mt5-demo-market-data`, CI 6/6 SUCCESS on that
  exact SHA, run 40217138921).
- Repo validator `scripts/validate_windows_package.py`: 10/10 PASS.
- Contents include all 3 genuine MT5 modules (`mt5_terminal.py`,
  `mt5_symbol_map.py`, `mt5_market_data.py`), 4 MT5 test files,
  `fake_mt5_lab`, MT5 integration artifacts 03/05/06, and
  `exness_mock.py` (simulation-labeled).

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

## Known issue (fixed on this branch): Windows PowerShell 5.1 parse errors

The .ps1 files inside the ZIP published at commit `cf88433` contained
UTF-8 em-dashes and no BOM. Windows PowerShell 5.1 (the default
`powershell.exe`) reads BOM-less files as ANSI/CP1252; the em-dash's
third byte (0x94) decodes to a smart quote that the PS 5.1 tokenizer
treats as a string delimiter, corrupting the parse (errors like
"Unexpected token 'recommended'", "The 'from' keyword is not
supported", "Array index expression is missing or not valid").

Fixed on this branch: `deploy/windows/*.ps1` are now pure ASCII with a
UTF-8 BOM. If your extracted copy still shows parse errors, either
re-download the fixed `install.ps1` from this branch or add the BOM
locally (fixes every script at once):

```powershell
Get-ChildItem "C:\AITradingLab\ai-trading-lab-data-engine-windows-v0.4.0" -Recurse -Filter *.ps1 | ForEach-Object {
  $c = [System.IO.File]::ReadAllText($_.FullName)
  $c = $c.Replace([string][char]0x2014, '-')
  [System.IO.File]::WriteAllText($_.FullName, $c, (New-Object System.Text.UTF8Encoding($true)))
  Write-Host "fixed: $($_.Name)"
}
```

## Honest testing status

- Automated suite at source commit: 2994 passed / 8 skipped / 0 failed;
  MT5 subset 102 passed / 5 skipped (terminal-integration tests are
  BLOCKED_ON_OPERATOR_ENV by design).
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
