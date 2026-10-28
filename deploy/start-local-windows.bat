@echo off
REM ============================================================
REM  AI Trading Lab — Data Engine v4 · LOCAL MODE START (Windows)
REM  Phone/other devices on same Wi-Fi connect to:
REM  http://^<COMPUTER-IP^>:81
REM ============================================================
title AI Trading Lab — Data Engine v4 (Local)
cd /d "%~dp0.."

echo ======================================================
echo   AI TRADING LAB — DATA ENGINE v4 . LOCAL MODE
echo ======================================================

where bun >nul 2>nul
if %errorlevel%==0 (
  set RUNTIME=bun
) else (
  where node >nul 2>nul
  if not %errorlevel%==0 (
    echo ERROR: Install Node.js 20+ from https://nodejs.org first.
    pause
    exit /b 1
  )
  set RUNTIME=node
)

if not exist node_modules (
  echo [deps] installing...
  if "%RUNTIME%"=="bun" ( call bun install ) else ( call npm install )
)

REM ---------- 1b. portable .env (absolute DB path for THIS machine) ----------
echo DATABASE_URL=file:%cd%\db\custom.db > .env
echo DATABASE_URL=file:%cd%\db\custom.db > mini-services\trading-engine\.env

if not exist .next\standalone\server.js (
  echo [build] building app, first run only...
  if "%RUNTIME%"=="bun" ( call bun run build ) else ( call npm run build )
)

if not exist deploy\caddy.exe (
  echo [gateway] downloading Caddy...
  curl -sL -o deploy\caddy.exe "https://caddyserver.com/api/download?os=windows&arch=amd64"
)

echo [engine] starting trading engine on :3003
start "ATL-Engine" cmd /c "cd /d %cd%\mini-services\trading-engine && ..\..\node_modules\.bin\bun run dev"

echo [web] starting app on :3000
start "ATL-Web" cmd /c "cd /d %cd%\.next\standalone && node server.js"

if exist deploy\caddy.exe (
  echo [gateway] starting gateway on :81
  start "ATL-Gateway" cmd /c "cd /d %cd%\deploy && caddy.exe run --config Caddyfile.local"
)

echo.
echo ======================================================
echo   READY
echo.
echo   This computer:      http://localhost:81
echo   Phone (same WiFi):  http://YOUR-IP:81
echo     (find YOUR-IP: run  ipconfig  and use IPv4 Address)
echo.
echo   USB (Android):  adb reverse tcp:81 tcp:81
echo     then app URL: http://127.0.0.1:81
echo.
echo   Login admin: muhammadasterschool@gmail.com
echo   New users: app - Register - invitation code
echo ======================================================
echo.
echo Close the three ATL-* windows to stop the engine.
pause
