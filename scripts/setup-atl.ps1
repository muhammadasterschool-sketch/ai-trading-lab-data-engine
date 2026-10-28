# ============================================================
#  AI TRADING LAB v4.0 - ONE-SHOT WINDOWS SETUP (PowerShell)
#  Download -> Extract -> Install -> Build -> Start -> Dashboard
#  Run:  powershell -ExecutionPolicy Bypass -File setup-atl.ps1
# ============================================================
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$Base    = "$env:USERPROFILE\AI-Trading-Lab"
$ZipUrl  = "https://preview-chat-6708bda6-7b6e-4a6f-a30c-eb65caff80bf.space-z.ai/downloads/AI-Trading-Lab-v4.0-Windows-Server-mini-services.zip"
$ZipFile = "$env:TEMP\ATL-server.zip"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Yellow
Write-Host "  AI TRADING LAB v4.0 - DATA ENGINE SETUP" -ForegroundColor Yellow
Write-Host "==============================================" -ForegroundColor Yellow

# ---------- STEP 1: DOWNLOAD + EXTRACT ----------
if (Test-Path "$Base\db\custom.db") {
    Write-Host "[1/7] Already installed at $Base - skipping download" -ForegroundColor Green
} else {
    Write-Host "[1/7] Downloading system (11 MB)..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipFile -UseBasicParsing
    Write-Host "      Extracting..."
    if (Test-Path "$env:TEMP\ATL-extract") { Remove-Item "$env:TEMP\ATL-extract" -Recurse -Force }
    Expand-Archive -Path $ZipFile -DestinationPath "$env:TEMP\ATL-extract" -Force
    if (Test-Path $Base) { Remove-Item $Base -Recurse -Force }
    Move-Item "$env:TEMP\ATL-extract\AI-Trading-Lab-v4.0-Windows-Server" $Base
    Write-Host "      Installed at $Base" -ForegroundColor Green
}

# ---------- STEP 2: BUN RUNTIME ----------
Write-Host "[2/7] Checking Bun runtime (needed for engine)..." -ForegroundColor Cyan
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
if (Get-Command bun -ErrorAction SilentlyContinue) {
    Write-Host "      Bun already installed: $(bun --version)" -ForegroundColor Green
} else {
    Write-Host "      Installing Bun (30 sec)..."
    Invoke-RestMethod https://bun.sh/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
    if (-not (Get-Command bun -ErrorAction SilentlyContinue)) { throw "Bun install failed - restart PowerShell and run again" }
    Write-Host "      Bun $(bun --version) installed" -ForegroundColor Green
}

# ---------- STEP 3: ENV FILES ----------
Write-Host "[3/7] Writing config (.env)..." -ForegroundColor Cyan
$DbPath = ($Base -replace '\\', '/')
"DATABASE_URL=file:$DbPath/db/custom.db" | Out-File -Encoding ascii "$Base\.env"
"DATABASE_URL=file:$DbPath/db/custom.db" | Out-File -Encoding ascii "$Base\mini-services\trading-engine\.env"
New-Item -ItemType Directory -Force -Path "$Base\logs" | Out-Null
Write-Host "      .env ready (database with 253,000+ real bars included)" -ForegroundColor Green

# ---------- STEP 4: DEPENDENCIES + PRISMA ----------
Push-Location $Base
try {
    if (-not (Test-Path "$Base\node_modules")) {
        Write-Host "[4/7] Installing dependencies (2-4 min, one time only)..." -ForegroundColor Cyan
        & bun install
        if ($LASTEXITCODE -ne 0) { throw "bun install failed" }
    } else {
        Write-Host "[4/7] Dependencies already installed" -ForegroundColor Green
    }
    if (-not (Test-Path "$Base\node_modules\.prisma\client\index.js")) {
        Write-Host "      Generating Prisma client..."
        & bunx prisma generate
        if ($LASTEXITCODE -ne 0) { throw "prisma generate failed" }
    }
    Write-Host "      Dependencies ready" -ForegroundColor Green
} finally { Pop-Location }

# ---------- STEP 5: BUILD APP ----------
Push-Location $Base
try {
    if (-not (Test-Path "$Base\.next\standalone\server.js")) {
        Write-Host "[5/7] Building app (3-5 min, first run only)..." -ForegroundColor Cyan
        & bun run build
        if ($LASTEXITCODE -ne 0) { throw "build failed" }
    } else {
        Write-Host "[5/7] App already built" -ForegroundColor Green
    }
    # Native PowerShell copy - cross-platform, also repairs any partial build
    Write-Host "      Copying static assets into standalone..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path "$Base\.next\standalone\.next" | Out-Null
    if (Test-Path "$Base\.next\static") {
        if (Test-Path "$Base\.next\standalone\.next\static") { Remove-Item "$Base\.next\standalone\.next\static" -Recurse -Force }
        Copy-Item "$Base\.next\static" "$Base\.next\standalone\.next\static" -Recurse -Force
    }
    if (Test-Path "$Base\public") {
        if (Test-Path "$Base\.next\standalone\public") { Remove-Item "$Base\.next\standalone\public" -Recurse -Force }
        Copy-Item "$Base\public" "$Base\.next\standalone\public" -Recurse -Force
    }
    Copy-Item "$Base\.env" "$Base\.next\standalone\.env" -Force
    Write-Host "      Standalone ready" -ForegroundColor Green
} finally { Pop-Location }

# ---------- STEP 5b: ADMIN PASSWORD (known default, one time) ----------
if (-not (Test-Path "$Base\.admin-ready")) {
    Push-Location $Base
    try {
        Write-Host "[5b] Setting admin login password..." -ForegroundColor Cyan
        if (-not (Test-Path "$Base\scripts\reset-admin.mjs")) {
            Invoke-WebRequest "https://preview-chat-6708bda6-7b6e-4a6f-a30c-eb65caff80bf.space-z.ai/downloads/reset-admin.mjs" -OutFile "$Base\scripts\reset-admin.mjs" -UseBasicParsing
        }
        & bun scripts/reset-admin.mjs
        if ($LASTEXITCODE -eq 0) {
            New-Item -ItemType File -Path "$Base\.admin-ready" -Force | Out-Null
            Write-Host "      Admin password set: AurumLab2026" -ForegroundColor Green
        } else { Write-Host "      Reset failed - run: bun scripts/reset-admin.mjs" -ForegroundColor Yellow }
    } finally { Pop-Location }
} else { Write-Host "[5b] Admin password already configured" -ForegroundColor Green }

# ---------- STEP 6: GATEWAY (Caddy) ----------
Write-Host "[6/7] Checking gateway..." -ForegroundColor Cyan
if (-not (Test-Path "$Base\deploy\caddy.exe")) {
    try {
        Invoke-WebRequest "https://caddyserver.com/api/download?os=windows&arch=amd64" -OutFile "$Base\deploy\caddy.exe" -UseBasicParsing
        Write-Host "      Caddy downloaded" -ForegroundColor Green
    } catch { Write-Host "      Caddy download failed - app will run on port 3000 (fine)" -ForegroundColor Yellow }
} else { Write-Host "      Caddy ready" -ForegroundColor Green }

# ---------- STEP 7: START EVERYTHING ----------
Write-Host "[7/7] Starting engine + web + gateway..." -ForegroundColor Cyan

# kill old instances if running
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and ($_.CommandLine -match "AI-Trading-Lab" -or $_.CommandLine -match "Caddyfile.local")
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$env:NODE_ENV = "production"
$engArgs = "/c bun run dev >> `"$Base\logs\engine.log`" 2>&1"
Start-Process -FilePath "cmd.exe" -ArgumentList $engArgs -WorkingDirectory "$Base\mini-services\trading-engine" -WindowStyle Minimized
Start-Sleep 2
$webArgs = "/c bun server.js >> `"$Base\logs\web.log`" 2>&1"
Start-Process -FilePath "cmd.exe" -ArgumentList $webArgs -WorkingDirectory "$Base\.next\standalone" -WindowStyle Minimized
if (Test-Path "$Base\deploy\caddy.exe") {
    $gwArgs = "/c caddy.exe run --config Caddyfile.local >> `"$Base\logs\gateway.log`" 2>&1"
    Start-Process -FilePath "cmd.exe" -ArgumentList $gwArgs -WorkingDirectory "$Base\deploy" -WindowStyle Minimized
}

# ---------- HEALTH CHECK ----------
function Wait-Port {
    param([int]$p, [int]$tries = 45)
    for ($i = 0; $i -lt $tries; $i++) {
        try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $p); $c.Close(); return $true } catch { Start-Sleep 2 }
    }
    return $false
}

Write-Host ""
Write-Host "      Engine (port 3003)... " -NoNewline
if (Wait-Port 3003) { Write-Host "ONLINE" -ForegroundColor Green } else { Write-Host "FAIL (see logs\engine.log)" -ForegroundColor Red }
Write-Host "      Web app (port 3000)... " -NoNewline
if (Wait-Port 3000) { Write-Host "ONLINE" -ForegroundColor Green } else { Write-Host "FAIL (see logs\web.log)" -ForegroundColor Red }

$Dash = "http://localhost:3000"
if (Wait-Port 81 10) {
    $Dash = "http://localhost:81"
    Write-Host "      Gateway (port 81)... ONLINE" -ForegroundColor Green
} else {
    Write-Host "      Gateway skipped - dashboard will open on port 3000" -ForegroundColor Yellow
}

# firewall rule for phone access (UAC prompt may appear - click Yes)
try {
    Start-Process powershell -Verb RunAs -Wait -ArgumentList "-Command", "New-NetFirewallRule -DisplayName 'AI Trading Lab 81' -Direction Inbound -LocalPort 81 -Protocol TCP -Action Allow | Out-Null" -ErrorAction SilentlyContinue
} catch { Write-Host "      Firewall rule skipped - phone connect may need USB mode" -ForegroundColor Yellow }

# ---------- DONE: OPEN DASHBOARD ----------
Write-Host ""
Write-Host "==============================================" -ForegroundColor Yellow
Write-Host "  READY - OPENING DASHBOARD" -ForegroundColor Yellow
Write-Host "==============================================" -ForegroundColor Yellow
Write-Host "  Dashboard   : $Dash"
Write-Host "  Admin login : muhammadasterschool@gmail.com"
Write-Host "  Admin pass  : AurumLab2026   (forgot it? run: bun scripts/reset-admin.mjs)"
Write-Host "  Sign in with: Name = Muhammad  +  Email  +  Password"
Write-Host "  2FA         : first login shows QR - scan with Google Authenticator"
Write-Host "  New users   : Register tab -> invitation code M2991474"
Write-Host "  Phone app   : http://<PC-IP>:81  (run ipconfig to find IPv4)"
Write-Host "  USB mode    : adb reverse tcp:81 tcp:81 -> http://127.0.0.1:81"
Write-Host "  Desktop     : 'AI Trading Lab' shortcut - one click = start + dashboard"
Write-Host "  Restart     : $Base\run-atl.ps1"
Write-Host "  Stop        : $Base\stop-atl.ps1"
Write-Host "==============================================" -ForegroundColor Yellow

# helper scripts for next time (single-quoted here-strings = written as-is)
$runScript = @'
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
$env:NODE_ENV = "production"
$Base = "$env:USERPROFILE\AI-Trading-Lab"
if (-not (Test-Path "$Base\logs")) { New-Item -ItemType Directory -Force -Path "$Base\logs" | Out-Null }
Start-Process cmd.exe -ArgumentList "/c bun run dev >> `"$Base\logs\engine.log`" 2>&1" -WorkingDirectory "$Base\mini-services\trading-engine" -WindowStyle Minimized
Start-Sleep 2
Start-Process cmd.exe -ArgumentList "/c bun server.js >> `"$Base\logs\web.log`" 2>&1" -WorkingDirectory "$Base\.next\standalone" -WindowStyle Minimized
if (Test-Path "$Base\deploy\caddy.exe") {
    Start-Process cmd.exe -ArgumentList "/c caddy.exe run --config Caddyfile.local >> `"$Base\logs\gateway.log`" 2>&1" -WorkingDirectory "$Base\deploy" -WindowStyle Minimized
}
Start-Sleep 5
$dash = "http://localhost:3000"
try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", 81); $c.Close(); $dash = "http://localhost:81" } catch {}
Start-Process $dash
Write-Host "AI Trading Lab started - dashboard opened in browser" -ForegroundColor Green
'@
$runScript | Out-File -Encoding ascii "$Base\run-atl.ps1"

$stopScript = @'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -match "trading-engine" -or
        $_.CommandLine -match "standalone" -or
        $_.CommandLine -match "Caddyfile.local" -or
        $_.CommandLine -match "AI-Trading-Lab"
    )
} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Write-Host "AI Trading Lab stopped" -ForegroundColor Yellow
'@
$stopScript | Out-File -Encoding ascii "$Base\stop-atl.ps1"

# ---------- DESKTOP SHORTCUT (one click = start everything + open dashboard) ----------
try {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $WS = New-Object -ComObject WScript.Shell
    $Lnk = $WS.CreateShortcut("$Desktop\AI Trading Lab.lnk")
    $Lnk.TargetPath = "powershell.exe"
    $Lnk.Arguments = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Base\run-atl.ps1`""
    $Lnk.WorkingDirectory = $Base
    $Lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
    $Lnk.Description = "Start AI Trading Lab engine + dashboard (one click)"
    $Lnk.Save()
    Write-Host "      Desktop shortcut created: 'AI Trading Lab' - double-click = full system start" -ForegroundColor Green
} catch { Write-Host "      Desktop shortcut skipped (permissions) - use run-atl.ps1 instead" -ForegroundColor Yellow }

Start-Sleep 3
Start-Process $Dash
Write-Host ""
