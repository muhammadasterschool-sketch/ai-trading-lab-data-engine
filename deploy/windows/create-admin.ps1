# create-admin.ps1 - v1.5.0: create the FIRST ADMIN account (2FA login).
#
# The monitor app's EMAIL LOGIN requires an account, and NO login is
# possible without a valid TOTP (two-factor) code. This script creates
# the admin account; the user enrolls their authenticator app on
# first login (the app shows the secret once, you enter the 6-digit
# code, enrollment completes).
#
# Password rules: minimum 10 characters. The password is read from a
# HIDDEN PROMPT (never a command-line argument, never echoed).
#
# LIVE TRADING IS NOT AUTHORIZED. PAPER_READY stays FALSE.

param(
    [Parameter(Mandatory = $true)][string]$Email,
    [Parameter(Mandatory = $true)][string]$Name,
    [string]$StateDir = ".\monitor-state"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message) {
    Write-Host "[CREATE-ADMIN-FAILED] $message" -ForegroundColor Red
    exit 1
}

$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) {
    Fail "engine venv not found at .\.venv - run .\install.ps1 first."
}

Write-Host "== AI Trading Lab - create ADMIN account (2FA) =="
Write-Host "[create-admin] email: $Email"
Write-Host "[create-admin] the password prompt is hidden (min 10 chars)."
& $vpython -m data_engine.cli add-admin --email $Email --name $Name --monitor-state-dir $StateDir
exit $LASTEXITCODE
