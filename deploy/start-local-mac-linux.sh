#!/usr/bin/env bash
# ============================================================
#  AI Trading Lab — Data Engine v4 · LOCAL MODE START
#  Runs the engine on YOUR computer. Phone/other devices on the
#  same Wi-Fi connect to:  http://<COMPUTER-IP>:81
# ============================================================
set -e
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
OS="$(uname -s)"
PORT_WEB=3000        # Next.js app + API
PORT_ENGINE=3003     # realtime trading engine (socket.io)
PORT_GATEWAY=81      # single public door (Caddy)

echo "======================================================"
echo "  AI Trading LAB — DATA ENGINE v4 · LOCAL MODE"
echo "======================================================"

# ---------- 0. runtime check ----------
if command -v bun >/dev/null 2>&1; then
  RUNTIME=bun
elif command -v node >/dev/null 2>&1 && [ "$(node -v | cut -d. -f1 | tr -d v)" -ge 20 ]; then
  RUNTIME=node
else
  echo "ERROR: Install Node.js 20+ (https://nodejs.org) or Bun (https://bun.sh) first."
  exit 1
fi
echo "[runtime] $RUNTIME ($($RUNTIME --version 2>/dev/null || node -v))"

# ---------- 1. deps ----------
if [ ! -d node_modules ]; then
  echo "[deps] installing…"
  [ "$RUNTIME" = bun ] && bun install || npm install
fi

# ---------- 1b. portable .env (absolute DB path for THIS machine) ----------
echo "DATABASE_URL=file://$ROOT/db/custom.db" > .env
echo "DATABASE_URL=file://$ROOT/db/custom.db" > mini-services/trading-engine/.env

# ---------- 2. build web app ----------
if [ ! -f .next/standalone/server.js ]; then
  echo "[build] building Next.js app (first run only)…"
  if [ "$RUNTIME" = bun ]; then
    bun run build
  else
    npm run build
  fi
fi

# ---------- 3. gateway (Caddy, single binary) ----------
if [ ! -x deploy/caddy ]; then
  echo "[gateway] downloading Caddy…"
  CADDY_URL="https://caddyserver.com/api/download?os=$(uname -s | tr 'A-Z' 'a-z')&arch=amd64"
  [ "$(uname -m)" = "arm64" ] || [ "$(uname -m)" = "aarch64" ] && CADDY_URL="https://caddyserver.com/api/download?os=$(uname -s | tr 'A-Z' 'a-z')&arch=arm64"
  curl -sL --retry 3 -o deploy/caddy "$CADDY_URL" && chmod +x deploy/caddy || echo "[gateway] Caddy download failed — app will still run on :$PORT_WEB"
fi

# ---------- 4. start engine + web ----------
cleanup() {
  [ -n "$ENGINE_PID" ] && kill "$ENGINE_PID" 2>/dev/null
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null
  [ -n "$GATEWAY_PID" ] && kill "$GATEWAY_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

echo "[engine] starting trading engine on :$PORT_ENGINE"
(cd mini-services/trading-engine && exec ../../node_modules/.bin/bun run dev) &
ENGINE_PID=$!

echo "[web] starting app on :$PORT_WEB"
if [ "$RUNTIME" = bun ]; then
  (cd .next/standalone && exec bun server.js) &
else
  (cd .next/standalone && exec node server.js) &
fi
WEB_PID=$!

# ---------- 5. gateway ----------
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "192.168.1.10")
if [ -x deploy/caddy ]; then
  echo "[gateway] starting gateway on :$PORT_GATEWAY"
  (cd deploy && exec ./caddy run --config Caddyfile.local) &
  GATEWAY_PID=$!
  sleep 1
fi

echo ""
echo "======================================================"
echo "  READY — connect your devices:"
echo ""
echo "  This computer:     http://localhost:81"
if [ -x deploy/caddy ]; then
  echo "  Phone (same WiFi): http://$LAN_IP:81"
  echo "                     → type into the Android/iOS app: $LAN_IP"
else
  echo "  Phone (same WiFi): http://$LAN_IP:$PORT_WEB"
  echo "                     → type into the app: http://$LAN_IP:$PORT_WEB"
fi
echo ""
echo "  USB cable (Android): adb reverse tcp:81 tcp:81"
echo "     then in the app:  http://127.0.0.1:81"
echo ""
echo "  Login: admin  muhammadasterschool@gmail.com"
echo "  New users: app → Register → invitation code"
echo "  (Stop: Ctrl+C)"
echo "======================================================"

wait
