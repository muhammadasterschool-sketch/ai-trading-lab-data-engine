# run-paper.ps1 - start the paper-mode SUPERVISOR (fail-closed)
# Stage E (Part 8, E1). This script NEVER places orders and NEVER
# contacts a real broker. It starts the engine's long-running
# paper-mode supervisor with a loopback-only dashboard.
#
# MANDATORY preconditions (both enforced below - fail closed):
#   1. RUNTIME_LEDGER_MAC_KEY or RUNTIME_LEDGER_MAC_KEY_FILE is set
#      (keyed-MAC ledger custody, F-25; key material NEVER touches
#      the package, config files, or logs).
#   2. The -Confirm switch is passed (explicit operator intent -
#      paper execution begins only with this explicit confirmation;
#      the engine itself additionally requires its own readiness
#      evidence chain before going active).
#
# Usage:
#   $env:RUNTIME_LEDGER_MAC_KEY = "<key material from your secret store>"
#   powershell -ExecutionPolicy Bypass -File .\run-paper.ps1 -Confirm
#
#   With an explicit session launch plan (FIX-10/B-P0-01 - the REAL
#   session wiring; the plan carries SIGNED operator approvals,
#   FIX-9, plus the approval key):
#   $env:OPERATOR_APPROVAL_MAC_KEY = "<approval signing key>"
#   powershell -ExecutionPolicy Bypass -File .\run-paper.ps1 -Confirm `
#       -SessionPlan .\launch-plan.json
#
# SAFE SHUTDOWN: press Ctrl+C in this window (the supervisor traps
# SIGINT and shuts down cleanly), or from another window:
#   Get-Process python | Where-Object {$_.Path -like "*\.venv*"} | Stop-Process
# State and logs persist under the configured state directory (see
# README-WINDOWS-PACKAGE.md for layout + backup/restore).

param(
    [switch]$Confirm,
    [int]$Port = 8017,
    [string]$SessionPlan = ""
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message, [int]$Code = 1) {
    Write-Host "[RUN-PAPER-REFUSED] $message" -ForegroundColor Red
    exit $Code
}

if (-not $Confirm) {
    Fail "explicit confirmation required: re-run with -Confirm (paper-mode supervisor start is an explicit operator action; PAPER_READY stays FALSE until YOU authorize the soak)."
}

$keyPresent = $env:RUNTIME_LEDGER_MAC_KEY -or $env:RUNTIME_LEDGER_MAC_KEY_FILE
if (-not $keyPresent) {
    Fail "RUNTIME_LEDGER_MAC_KEY (or RUNTIME_LEDGER_MAC_KEY_FILE) is not set. Provision the keyed-MAC custody key in your secret store first (see README-WINDOWS-PACKAGE.md, 'Secret handling'). Key material must NEVER be typed into files inside the package."
}

$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) { Fail "venv not found - run .\install.ps1 first." }

# FIX-13 (B-P1-10): exit-code hardening. The gate disposition print
# is informational, but if the engine itself FAILS to report (crash,
# import error), the script must NOT continue to a green-looking
# startup. NOTE: `status --gates` reports the honest disposition and
# exits 0 by design - a non-zero exit here means the STATUS TOOL
# failed, not that a gate failed.
Write-Host "== Gate disposition (32 readiness gates, honest supplier status) =="
& $vpython -m data_engine.cli status --gates
if ($LASTEXITCODE -ne 0) {
    Fail "gate disposition command failed (exit $LASTEXITCODE) - the engine status tool itself is broken; refusing to proceed." 5
}

Write-Host ""
Write-Host "Starting paper-mode supervisor (loopback dashboard on 127.0.0.1:$Port)."
Write-Host "Safe shutdown: Ctrl+C here, or Stop-Process on this venv's python."
Write-Host "The supervisor REFUSES to go active unless its full readiness"
Write-Host "evidence chain is present (fail-closed startup)."

# FIX-10/B-P0-01: with -SessionPlan the supervisor composes + starts
# a REAL operational paper session through the composition root and
# drives its tick; a refused launch exits 4 (never a silent
# supervisor-only shell when a session was requested).
if ($SessionPlan -ne "") {
    if (-not (Test-Path $SessionPlan)) {
        Fail "session launch plan not found: $SessionPlan (pass -SessionPlan with an existing launch-plan.json path)" 4
    }
    Write-Host "Session launch plan: $SessionPlan (compose + start via the composition root)"
    & $vpython -m data_engine.cli serve --host 127.0.0.1 --port $Port --session-launch $SessionPlan
}
else {
    & $vpython -m data_engine.cli serve --host 127.0.0.1 --port $Port
}
exit $LASTEXITCODE
