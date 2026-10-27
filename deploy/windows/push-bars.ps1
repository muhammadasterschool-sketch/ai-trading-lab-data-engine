# push-bars.ps1 - upload YOUR OHLCV history into the AI lab (v1.1.0).
#
# The lab NEVER invents market data: strategies backtest and
# paper-evaluate the bars YOU upload. This script reads a CSV with the
# header row:  timestamp,open,high,low,close,volume
# (timestamp = ISO-8601 like 2026-01-01T00:00:00Z, or epoch seconds)
# and POSTs it to the engine's POST /api/lab/bars in bounded chunks.
#
# Usage (from the package directory, after run-monitor.ps1 is running):
#   .\push-bars.ps1 -CsvPath .\xauusd_h1.csv -Symbol XAU/USD
#   .\push-bars.ps1 -CsvPath .\btc.csv -Symbol BTCUSD -BaseUrl http://127.0.0.1:8018
#
# The monitor token is read from .\monitor-token.txt (the same token
# your paired phone uses). Volume is optional per row.
#
# LIVE TRADING IS NOT AUTHORIZED. PAPER_READY stays FALSE.

param(
    [Parameter(Mandatory = $true)][string]$CsvPath,
    [Parameter(Mandatory = $true)][string]$Symbol,
    [string]$BaseUrl = "http://127.0.0.1:8018",
    [int]$ChunkSize = 4000
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Fail([string]$message) {
    Write-Host "[PUSH-BARS-FAILED] $message" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $CsvPath)) {
    Fail "CSV not found: $CsvPath"
}

$tok = ".\monitor-token.txt"
if (-not (Test-Path $tok)) {
    Fail "monitor-token.txt not found - run run-monitor.ps1 first (it creates the token)."
}
$token = (Get-Content $tok -Raw).Trim()
if ($token.Length -lt 16) {
    Fail "monitor-token.txt is too short / corrupt."
}

$headers = @{
    "Authorization" = "Bearer $token"
    "Content-Type"  = "application/json"
    "Accept"        = "application/json"
}

$rows = Import-Csv -Path $CsvPath
if ($rows.Count -eq 0) {
    Fail "CSV has no data rows (expected header: timestamp,open,high,low,close,volume)."
}
Write-Host "[push-bars] $($rows.Count) rows loaded from $CsvPath (symbol $Symbol)"

$bars = New-Object System.Collections.Generic.List[object]
foreach ($row in $rows) {
    $ts = $row.timestamp
    if (-not $ts) { $ts = $row.time }
    if (-not $ts) { $ts = $row.date }
    if (-not $ts) { Fail "CSV row without a timestamp column (need timestamp|time|date)." }
    $open = 0.0; $high = 0.0; $low = 0.0; $close = 0.0
    if (-not [double]::TryParse([string]$row.open, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$open)) { Fail "bad open: $($row.open)" }
    if (-not [double]::TryParse([string]$row.high, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$high)) { Fail "bad high: $($row.high)" }
    if (-not [double]::TryParse([string]$row.low, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$low)) { Fail "bad low: $($row.low)" }
    if (-not [double]::TryParse([string]$row.close, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$close)) { Fail "bad close: $($row.close)" }
    $bar = [ordered]@{
        ts    = "$ts"
        open  = $open
        high  = $high
        low   = $low
        close = $close
    }
    $volRaw = $row.volume
    if ($volRaw) {
        $vol = 0.0
        if ([double]::TryParse([string]$volRaw, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$vol)) {
            $bar.volume = $vol
        }
    }
    $bars.Add([pscustomobject]$bar)
}

$totalAdded = 0
$totalStored = 0
for ($offset = 0; $offset -lt $bars.Count; $offset += $ChunkSize) {
    $end = [Math]::Min($offset + $ChunkSize, $bars.Count)
    $slice = $bars.GetRange($offset, $end - $offset)
    $payload = @{
        symbol = $Symbol
        bars   = $slice
    } | ConvertTo-Json -Depth 5 -Compress
    try {
        $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/lab/bars" -Headers $headers -Body $payload -TimeoutSec 120
    } catch {
        $detail = ""
        try {
            $stream = $_.Exception.Response.GetResponseStream()
            if ($stream) {
                $reader = New-Object System.IO.StreamReader($stream)
                $detail = $reader.ReadToEnd()
            }
        } catch { }
        Fail "upload refused (chunk at offset $offset): $detail $($_.Exception.Message)"
    }
    $totalAdded += [int]$response.added
    $totalStored = [int]$response.total
    Write-Host ("[push-bars] chunk {0}-{1}: +{2} bars (stored total {3})" -f $offset, $end, $response.added, $response.total)
}

Write-Host "[push-bars] DONE: +$totalAdded new bars for $Symbol (stored total $totalStored)."
Write-Host "[push-bars] Next: monitor APK -> AI Lab -> Strategies -> create -> RUN BACKTEST."
