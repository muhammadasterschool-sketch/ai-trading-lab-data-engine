# install.ps1 — AI Trading Lab Data Engine, Windows package installer
# Stage E (Part 8, E1). Fail-closed: ANY error stops the script with a
# non-zero exit. No secrets are read, written, or embedded here.
#
# Usage (from the extracted package root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#
# What it does (documented order):
#   1. verifies Python 3.11+ is available on PATH
#   2. creates an ISOLATED project venv at .\.venv
#   3. installs the LOCKED runtime dependencies (hash-pinned)
#   4. installs the engine wheel from .\dist\
#   5. runs the fail-closed packaging smoke test
#
# LIVE TRADING IS NOT AUTHORIZED. PAPER_READY stays FALSE.
# Secrets are handled ONLY via environment variables at runtime.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$minimumPython = "3.11"

function Fail([string]$message) {
    Write-Host "[INSTALL-FAILED] $message" -ForegroundColor Red
    exit 1
}

Write-Host "== AI Trading Lab Data Engine — Windows installer =="

# -- 1. Python version gate -------------------------------------------------
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Fail "Python not found on PATH. Install Python 3.11+ (3.12 recommended) from python.org, tick 'Add python.exe to PATH', then re-run."
    }
}

$versionRaw = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Host "Detected Python: $versionRaw"
$parts = $versionRaw.Split('.')
$major = [int]$parts[0]; $minor = [int]$parts[1]
if (($major -lt 3) -or (($major -eq 3) -and ($minor -lt 11))) {
    Fail "Python $minimumPython or newer is required (repo requires-python >=3.11; declared runtime is 3.14). Detected: $versionRaw"
}

# -- 2. Isolated project venv ------------------------------------------------
if (Test-Path ".\.venv") {
    Write-Host "[SKIP] .\.venv already exists — remove it first for a CLEAN install."
} else {
    Write-Host "Creating project virtual environment at .\.venv ..."
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "venv creation failed (exit $LASTEXITCODE)." }
}

$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) { Fail "venv python not found at $vpython" }

# -- 3. Locked runtime dependencies (hash-pinned) ----------------------------
Write-Host "Upgrading pip inside the venv ..."
& $vpython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed." }

Write-Host "Installing LOCKED runtime dependencies (hash-pinned) ..."
& $vpython -m pip install --require-hashes -r .\requirements-windows.txt
if ($LASTEXITCODE -ne 0) {
    Fail "locked dependency install failed. Common causes: no internet access; pip too old to honor --require-hashes; corporate TLS interception (see README-WINDOWS-PACKAGE.md, 'Firewall / antivirus notes')."
}

# -- 4. Engine wheel ----------------------------------------------------------
$wheel = Get-ChildItem -Path .\dist -Filter "*.whl" | Select-Object -First 1
if (-not $wheel) { Fail "no engine wheel found in .\dist" }
Write-Host "Installing engine wheel: $($wheel.Name) ..."
& $vpython -m pip install $wheel.FullName
if ($LASTEXITCODE -ne 0) { Fail "engine wheel install failed." }

# -- 5. Fail-closed smoke test ------------------------------------------------
Write-Host "Running fail-closed packaging smoke test ..."
& $vpython .\source\scripts\windows_smoke_test.py
if ($LASTEXITCODE -ne 0) {
    Fail "SMOKE TEST FAILED — the packaged application is NOT fit. Do not proceed; report the output above."
}

Write-Host ""
Write-Host "[INSTALL-OK] Engine installed into .\.venv"
Write-Host "Next steps:"
Write-Host "  .\run-tests.ps1      - run the full test suite"
Write-Host "  .\run-paper.ps1      - start the paper-mode supervisor (fail-closed; see README)"
Write-Host "Secrets: ONLY environment variables (see README-WINDOWS-PACKAGE.md). Never files in the package."
exit 0
