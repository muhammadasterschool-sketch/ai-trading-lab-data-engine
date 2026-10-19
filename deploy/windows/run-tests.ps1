# run-tests.ps1 — run the FULL test suite through the package's venv
# Stage E (Part 8, E1/E2). Fail-closed: non-zero exit on any failure.
#
# Usage (from the package root, after install.ps1):
#   powershell -ExecutionPolicy Bypass -File .\run-tests.ps1
#
# The suite runs from the PACKAGED SOURCE tree with SYNTHETIC data and
# mock venues only. No network trading, no real orders, no secrets.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message) {
    Write-Host "[TESTS-FAILED] $message" -ForegroundColor Red
    exit 1
}

$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) { Fail "venv not found — run .\install.ps1 first." }

if (-not (Test-Path ".\source")) { Fail "packaged source tree not found at .\source" }

# dev dependency (the repo's declared dev extra): pytest 9.1.1
Write-Host "Ensuring pytest (declared dev dependency) ..."
& $vpython -m pip install "pytest==9.1.1"
if ($LASTEXITCODE -ne 0) { Fail "pytest install failed." }

Write-Host "Running the FULL suite (this takes ~2 minutes) ..."
Push-Location .\source
try {
    & $vpython -m pytest -q
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($code -ne 0) { Fail "test suite exited $code — the package is NOT verified." }

Write-Host "[TESTS-OK] full suite green through the documented Windows commands."
exit 0
