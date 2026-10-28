# README — WINDOWS PACKAGE (AI Trading Lab Data Engine)

Stage E deliverable (Part 8, E1-E3). Package version: see
`source/pyproject.toml` (engine 0.3.0 series).

**LIVE TRADING IS NOT AUTHORIZED — permanently out of scope. The
packaged application is structurally paper-only (enforced at four
layers; smoke-tested). PAPER_READY stays FALSE.**

## 1. What is in this package

```
<package-root>\
├── install.ps1               fail-closed installer (venv + locked deps + wheel + smoke test)
├── run-tests.ps1             runs the FULL test suite through the venv
├── run-paper.ps1             starts the paper-mode supervisor (fail-closed, -Confirm + MAC key required)
├── requirements-windows.txt  LOCKED runtime dependencies (hash-pinned, uv-exported from uv.lock)
├── README-WINDOWS-PACKAGE.md this file
├── dist\
│   └── ai_trading_lab_data_engine-<version>-py3-none-any.whl
├── source\                   the FULL repository source tree (git archive — auditability)
│   ├── src\data_engine\...
│   ├── tests\...
│   ├── deploy\...
│   ├── docs\...
│   └── pyproject.toml, uv.lock, ...
└── SHA256SUMS.txt            SHA256 of every file above (verify BEFORE installing)
```

Verify integrity FIRST:

```powershell
Get-Content .\SHA256SUMS.txt | ForEach-Object {
    $hash, $rel = $_ -split '  ', 2
    $actual = (Get-FileHash -Algorithm SHA256 $rel.Trim()).Hash.ToLower()
    if ($actual -ne $hash) { Write-Host "MISMATCH: $rel" -ForegroundColor Red }
}
```

## 2. Requirements

- Windows 10/11 (64-bit), PowerShell 5.1+ (built-in).
- **Python 3.11 or newer** (repo `requires-python >=3.11`; declared
  runtime 3.14; 3.12+ recommended). From python.org — tick "Add
  python.exe to PATH" during setup.
- Internet access ONCE for the locked dependency install
  (`--require-hashes` enforces exact integrity).
- ~1 GB disk for venv + source.

## 3. Install / test / run (documented commands, in order)

```powershell
cd <package-root>
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
# paper supervisor — ONLY when you deliberately choose to start it:
$env:RUNTIME_LEDGER_MAC_KEY = "<key from YOUR secret store>"
powershell -ExecutionPolicy Bypass -File .\run-paper.ps1 -Confirm
```

## 3a. v1.5.0 — monitor, 2FA login, real data, paper trading start

The monitor is the single app (the old separate ADMIN APK is retired;
admin features live inside the monitor app for admin-role users).

```powershell
# 1) start the local monitor (preset auto-bootstrap is ON by default)
powershell -ExecutionPolicy Bypass -File .\run-monitor.ps1
#    phone on your Wi-Fi instead of loopback:
powershell -ExecutionPolicy Bypass -File .\run-monitor.ps1 -AllowLan

# 2) create the FIRST ADMIN account (hidden password prompt, min 10
#    chars; the user enrolls their authenticator app on first login)
powershell -ExecutionPolicy Bypass -File .\create-admin.ps1 -Email you@example.com -Name "Owner"

# 3) import VERIFIED REAL 1-minute history into the lab (offline:
#    bundled repo datasets, sha256-checked against the source's
#    official checksum; website fallback = data.binance.vision)
.\.venv\Scripts\python.exe -m data_engine.cli hist-datasets
.\.venv\Scripts\python.exe -m data_engine.cli hist-import --symbol BTCUSDT --monitor-state-dir .\monitor-state
```

Then IN THE APP (everything also exists as HTTP routes):

- **EMAIL LOGIN (2FA)** — email + password + the 6-digit
  authenticator code. NO session is issued without a valid TOTP code
  (RFC 6238; Google Authenticator / Authy / Microsoft Authenticator
  all work; enrollment happens on first login).
- **Users (admin only)** — who is connected right now, all accounts
  with login history, create user, reset 2FA, lock/unlock.
- **AI Lab -> Strategies -> START PAPER TRADING** — imports verified
  1m data, creates the TOP-5 YouTuber presets (EMA 9/21 scalp, RSI +
  Bollinger, VWAP reversion, Supertrend + ADX, opening-range
  breakout) and opens their 30-day paper windows. AUTO-SCAN scans 27
  parameter combinations (70/30 IS/OOS, net of costs) and creates
  ordinary submissions.
- **>=60% confirmed calls** journal a PAPER-ONLY one-fill-per-second
  burst (60 hypothetical fills after the confirmation candle, exit
  marked at the next closed candle, cooldown + loss cap + kill-switch
  pause). These are JOURNAL entries — no orders are sent anywhere.

## 4. State / log directory layout

The engine NEVER writes state inside the package. Runtime artifacts
live under the configured state root (default
`%LOCALAPPDATA%\ai-trading-lab\state`, overridable per the engine's
config contract):

```
%LOCALAPPDATA%\ai-trading-lab\
├── state\            execution state store (flock single-writer, atomic writes)
│   └── <store-dir>\  journals + snapshots + recovery records
├── logs\             redacted logs (secrets NEVER logged — enforced by redaction layer)
└── paper\            paper-mode session artifacts (submission ledger, venue journal)
```

Per-user containment (FS-01..06) is enforced by the engine: fail-closed
containment checks refuse writes outside the configured roots.

## 5. Secret handling (environment variables ONLY)

- `RUNTIME_LEDGER_MAC_KEY` or `RUNTIME_LEDGER_MAC_KEY_FILE` — keyed-MAC
  ledger custody (F-25). Set per-session (`$env:...`) or via the
  Windows user environment (SystemPropertiesAdvanced → Environment
  Variables). NEVER put key material in a file inside the package, in
  config files, or in command history you share.
- The paper venue needs NO broker credentials (structural isolation —
  no credential field exists in the paper execution path).
- Redaction is enforced engine-side; logs are safe by construction.

## 6. Backup / restore

- BACKUP the state root (`%LOCALAPPDATA%\ai-trading-lab\`) with the
  supervisor STOPPED (clean shutdown — see §7). Copy the whole
  directory tree; all files are plain (MAC-protected) JSON.
- RESTORE: stop supervisor → replace directory → restart. The engine
  runs conservative recovery + reconciliation on start (never silently
  optimistic); a tampered chain fails closed.
- The submission ledger hash chain verifies under MAC custody — a
  restored chain that does not verify is refused.

## 7. Safe shutdown

- Preferred: Ctrl+C in the supervisor window (SIGINT trap → clean
  shutdown: journals flushed, dashboard stopped).
- Alternative: `Stop-Process` on the venv's python (crash-consistent:
  journal recovery handles it conservatively on next start — but
  prefer clean shutdown).

## 8. Firewall / antivirus notes

- The engine's dashboard binds **loopback ONLY (127.0.0.1)** — Windows
  Firewall will NOT prompt for inbound access; no inbound rule is
  needed or wanted.
- One-time OUTBOUND HTTPS (443) to PyPI during `install.ps1` — allow
  it, or pre-stage a wheelhouse and adjust the install command.
- Antivirus: the venv python + pytest are ordinary signed binaries;
  real-time scanning may slow the suite but requires no exclusions. Do
  NOT disable security software for this package.

## 9. Verification status (honest markers)

| Item | Status |
| --- | --- |
| Locked deps resolve + install (hash-pinned) | VERIFIED on Linux (fresh venv, `--require-hashes`) |
| Wheel builds from the packaged source | VERIFIED (uv build) |
| Full suite green from the packaged source | VERIFIED on Linux (Python 3.12.15) |
| PowerShell scripts execute on Windows | **NOT VERIFIED on a Windows host in this run** (no Windows VM available in the build environment) — run `install.ps1` on your Windows machine and record the output as the final packaging evidence |
| Paper-mode supervisor (serve) | Engine command verified on Linux; Windows-host run awaits operator evidence |

Record your Windows-host evidence in the operator runbook (source
`docs/` + this README constitute the procedure).

## 10. Upgrade / rollback

- UPGRADE: extract a NEW package beside the old one; point it at the
  SAME state root (config) — recovery + reconciliation run on start.
- ROLLBACK: reinstall the previous package (keep its zip); state
  written by a newer engine may be refused conservatively by an older
  one — that refusal is the fail-closed contract working.
