# run-monitor.ps1 — start the LOCAL MONITOR (v4.0, PART 5 B3 / P5).
#
# Monitor-ONLY entrypoint: it starts the authenticated monitoring API
# (with invitation pairing enabled) and NOTHING else. It runs WITHOUT a
# trading session: no orders, no tick loop composition, no broker —
# and the kill-switch endpoint honestly reports 503 until a separately
# composed operational session is running (fail-closed, unchanged).
#
# What it does (first run):
#   1. creates .\local-monitor.json from the packaged template
#      (invitation code stored ONLY as salted SHA-256 — the plaintext
#      default was issued to you out-of-band and is NEVER in files);
#   2. generates .\monitor-token.txt (the APK obtains this token via
#      pairing; delete the file to invalidate the paired phone);
#   3. starts `data-engine serve` with the monitor on 127.0.0.1.
#
# Phone on the SAME device (Android emulator): use 127.0.0.1:8018.
# Phone on your Wi-Fi: re-run with -AllowLan (reads the LAN IP,
# warns that LAN traffic is UNENCRYPTED outside this PC, enables the
# mDNS announcement so the APK can auto-discover, and prints the
# manual address as the always-works fallback).
#
# Change the invitation code: see LOCAL-MONITOR-RUNBOOK.md.
#
# LIVE TRADING IS NOT AUTHORIZED. PAPER_READY stays FALSE.

param(
    [switch]$AllowLan,
    [int]$MonitorPort = 8018
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message) {
    Write-Host "[RUN-MONITOR-FAILED] $message" -ForegroundColor Red
    exit 1
}

Write-Host "== AI Trading Lab - local monitor (invitation pairing) =="

# -- 0. the engine venv must exist (install.ps1 ran first) ----------------
$vpython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $vpython)) {
    Fail "engine venv not found at .\.venv - run .\install.ps1 first."
}

# -- 1. first-run local config (salted-hash invitation template) ---------
$cfg = ".\local-monitor.json"
if (-not (Test-Path $cfg)) {
    if (-not (Test-Path ".\local-monitor-config.template.json")) {
        Fail "local-monitor-config.template.json is missing from the package (tampered package?)"
    }
    Copy-Item ".\local-monitor-config.template.json" $cfg
    Write-Host "[run-monitor] created .\local-monitor.json (invitation hash pre-set from the template)."
    Write-Host "[run-monitor] to change the invitation code later: see LOCAL-MONITOR-RUNBOOK.md (rotate section)."
}

# -- 2. first-run monitor token -------------------------------------------
$tok = ".\monitor-token.txt"
if (-not (Test-Path $tok)) {
    $token = (& $vpython -c "import secrets; print(secrets.token_hex(32))").Trim()
    if ($token.Length -lt 32) {
        Fail "monitor token generation failed."
    }
    Set-Content -Path $tok -Value $token -NoNewline -Encoding Ascii
    Write-Host "[run-monitor] generated .\monitor-token.txt - keep it private;"
    Write-Host "[run-monitor] delete it to invalidate the paired phone at any time."
}

# -- 3. bind decision: loopback by default (fail-closed) -------------------
$bind = "127.0.0.1"
$extraArgs = @()
if ($AllowLan) {
    $bind = "0.0.0.0"
    $lan = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254*" } |
        Select-Object -First 1
    Write-Host ""
    Write-Host "[run-monitor] WARNING: LAN binding - traffic on your Wi-Fi to this" -ForegroundColor Yellow
    Write-Host "[run-monitor] monitor is UNENCRYPTED outside this PC (honest posture;" -ForegroundColor Yellow
    Write-Host "[run-monitor] cloud mode stays end-to-end TLS). Use only on a network" -ForegroundColor Yellow
    Write-Host "[run-monitor] you trust, and stop the monitor when not pairing." -ForegroundColor Yellow
    Write-Host ""
    if ($null -ne $lan) {
        Write-Host "[run-monitor] manual connect address for the APK: http://$($lan.IPAddress):$MonitorPort"
        Write-Host "[run-monitor] same-device (emulator) address:          http://127.0.0.1:$MonitorPort"
    } else {
        Write-Host "[run-monitor] could not detect a LAN IPv4 address - the APK will need 127.0.0.1 or the manual address."
    }
    Write-Host "[run-monitor] if your phone cannot connect, allow the port once:"
    Write-Host "    netsh advfirewall firewall add rule name=`"AI Trading Lab monitor`" dir=in action=allow protocol=TCP localport=$MonitorPort"
    Write-Host "[run-monitor] mDNS announcement is ON (the APK auto-discovers this PC;"
    Write-Host "[run-monitor] manual address entry always works as the fallback)."
    $extraArgs += "--mdns-announce"
} else {
    Write-Host "[run-monitor] loopback binding (default). Phone on the SAME device:"
    Write-Host "[run-monitor]   APK PC address = 127.0.0.1:$MonitorPort"
    Write-Host "[run-monitor] to connect a phone on your Wi-Fi, re-run with: .\run-monitor.ps1 -AllowLan"
}

# -- 4. go (monitor-only; no trading session is composed) ------------------
Write-Host "[run-monitor] starting data-engine serve (Ctrl+C to stop) ..."
& $vpython -m data_engine.cli serve `
    --no-dashboard `
    --monitor-bind $bind `
    --monitor-port $MonitorPort `
    --monitor-token-file $tok `
    --pairing-config $cfg `
    @extraArgs
exit $LASTEXITCODE
