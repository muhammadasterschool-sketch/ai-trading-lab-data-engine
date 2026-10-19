# run-paper.ps1 — start the paper-mode SUPERVISOR (fail-closed)
# Stage E (Part 8, E1). This script NEVER places orders and NEVER
# contacts a real broker. It starts the engine's long-running
# paper-mode supervisor with a loopback-only dashboard.
#
# MANDATORY preconditions (both enforced below — fail closed):
#   1. RUNTIME_LEDGER_MAC_KEY or RUNTIME_LEDGER_MAC_KEY_FILE is set
#      (keyed-MAC ledger custody, F-25; key material NEVER touches
#      the package, config files, or logs).
#   2. The -Confirm switch is passed (explicit operator intent —
#      paper execution begins only with this explicit confirmation;
#      the engine itself additionally requires its own readiness
#      evidence chain before going active).
#
# Usage:
#   $env:RUNTIME_LEDGER_MAC_KEY = "<key material from your secret store>"
#   powershell -ExecutionPolicy Bypass -File .\run-paper.ps1 -Confirm
#
# SAFE SHUTDOWN: press Ctrl+C in this window (the supervisor traps
# SIGINT and shuts down cleanly), or from another window:
#   Get-Process python | Where-Object {$_.Path -like "*\.venv*"} | Stop-Process
# State and logs persist under the configured state directory (see
# README-WINDOWS-PACKAGE.md for layout + backup/restore).

param(
    [switch]$Confirm,
    [int]$Port = 8017
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message) {
    Write-Host "[RUN-PAPER-REFUSED] $message" -ForegroundColor Red
    exit 1
}

if (-not $Confirm) {
    Fail "explicit confirmation required: re-run with -Confirm (paper-mode supervisor start is an explicit operator action; PAPER_READY stays FALSE until YOU authorize the soak)."
}

$keyPresent = $env:RUNTIME_LEDGER_MAC_KEY -or $env:RUNTIME_LEDGER_MAC_KEY_FILE
if (-not $keyPresent) {
    Fail "RUNTIME_LEDGER_MAC_KEY (or RUNTIME_LEDGER_MAC_KEY_FILE) is not set. Provision the keyed-MAC custody key in your secret store first (see README-WINDOWS-PACKAGE.md, 'Secret handling'). Key material must NEVER be typed into files inside the package."
}

$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) { Fail "venv not found — run .\install.ps1 first." }

Write-Host "== Gate disposition (32 readiness gates, honest supplier status) =="
& $vpython -m data_engine.cli status --gates

Write-Host ""
Write-Host "Starting paper-mode supervisor (loopback dashboard on 127.0.0.1:$Port)."
Write-Host "Safe shutdown: Ctrl+C here, or Stop-Process on this venv's python."
Write-Host "The supervisor REFUSES to go active unless its full readiness"
Write-Host "evidence chain is present (fail-closed startup)."
& $vpython -m data_engine.cli serve --host 127.0.0.1 --port $Port
exit $LASTEXITCODE
