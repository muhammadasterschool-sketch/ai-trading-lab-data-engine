#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  AI TRADING LAB v4.0 - PHONE SERVER (Termux one-shot setup)
#  Installs the FULL system ON THIS PHONE - no PC needed.
#  Engine + Web + Gateway run inside Ubuntu (proot) on the phone.
#  Paper trading keeps running in background (wake lock).
#
#  Run inside Termux app:   bash termux-setup-atl.sh
# ============================================================
set -e

BASE_URL="https://preview-chat-6708bda6-7b6e-4a6f-a30c-eb65caff80bf.space-z.ai"
ATL="$HOME/AI-Trading-Lab-Phone"

echo ""
echo "=============================================="
echo "  AI TRADING LAB v4.0 - PHONE SERVER SETUP"
echo "=============================================="

echo "[1/6] Termux packages (proot-distro, curl, unzip)..."
pkg update -y >/dev/null 2>&1 || true
pkg install -y proot-distro curl tar unzip >/dev/null 2>&1
termux-wake-lock 2>/dev/null || true

echo "[2/6] Ubuntu container (one time, ~300 MB download)..."
if [ ! -d "$PREFIX/var/lib/proot-distro/installed-rootfs/ubuntu" ]; then
  proot-distro install ubuntu
else
  echo "      Ubuntu already installed"
fi

echo "[3/6] Downloading AI Trading Lab system (11 MB)..."
mkdir -p "$ATL"
if [ ! -f "$ATL/system/db/custom.db" ]; then
  curl -L "$BASE_URL/downloads/AI-Trading-Lab-v4.0-Windows-Server-mini-services.zip" -o "$ATL/atl.zip"
  rm -rf "$ATL/extract"
  mkdir -p "$ATL/extract"
  unzip -q "$ATL/atl.zip" -d "$ATL/extract"
  mv "$ATL/extract/AI-Trading-Lab-v4.0-Windows-Server" "$ATL/system"
  rm -f "$ATL/atl.zip"
  rm -rf "$ATL/extract"
else
  echo "      System already downloaded"
fi

echo "[4/6] Writing installer scripts..."
# ---------- inner setup (runs inside Ubuntu) ----------
cat > "$ATL/inner-setup.sh" <<'EOF'
#!/bin/bash
set -e
S=/atl/system
echo "      Ubuntu packages..."
apt update -y >/dev/null 2>&1 || true
apt install -y curl unzip ca-certificates openssl procps >/dev/null 2>&1 || true

echo "      Configuring database paths..."
echo "DATABASE_URL=file:/atl/system/db/custom.db" > "$S/.env"
echo "DATABASE_URL=file:/atl/system/db/custom.db" > "$S/mini-services/trading-engine/.env"

export PATH="$HOME/.bun/bin:$PATH"
if ! command -v bun >/dev/null 2>&1; then
  echo "      Installing Bun runtime (arm64)..."
  curl -fsSL https://bun.sh/install | bash >/dev/null 2>&1
fi

cd "$S"
if [ ! -d "$S/node_modules" ]; then
  echo "      Installing dependencies (3-6 min, one time)..."
  bun install
fi
if [ ! -d "$S/node_modules/.prisma/client" ]; then
  echo "      Generating Prisma client..."
  bunx prisma generate
fi
if [ ! -f "$S/.next/standalone/server.js" ]; then
  echo "      Building app (10-20 min on phone, ONE TIME ONLY - please wait)..."
  bun run build
fi
cp "$S/.env" "$S/.next/standalone/.env"

echo "      Setting admin password..."
bun scripts/reset-admin.mjs || echo "      (reset skipped - run manually later)"

echo "      Downloading gateway (caddy arm64)..."
if [ ! -f "$S/deploy/caddy" ]; then
  curl -L "https://caddyserver.com/api/download?os=linux&arch=arm64" -o "$S/deploy/caddy" 2>/dev/null || true
  chmod +x "$S/deploy/caddy" 2>/dev/null || true
fi
[ -f "$S/deploy/caddy" ] && echo "      Gateway ready" || echo "      Gateway skipped - app will use port 3000"

cat > "$S/start-inner.sh" <<'EOF2'
#!/bin/bash
S=/atl/system
export PATH="$HOME/.bun/bin:$PATH"
export NODE_ENV=production
pkill -f "index.ts" 2>/dev/null || true
pkill -f "server.js" 2>/dev/null || true
pkill -f caddy 2>/dev/null || true
sleep 1
cd "$S/mini-services/trading-engine" && nohup bun run dev > "$S/engine.log" 2>&1 &
sleep 2
cd "$S/.next/standalone" && nohup bun server.js > "$S/web.log" 2>&1 &
sleep 2
if [ -f "$S/deploy/caddy" ]; then
  printf ':81 {\n  reverse_proxy localhost:3000\n}\n' > "$S/deploy/Caddyfile.phone"
  cd "$S/deploy" && nohup ./caddy run --config Caddyfile.phone > "$S/gateway.log" 2>&1 &
fi
sleep 3
echo "INNER_START_OK"
EOF2
chmod +x "$S/start-inner.sh"

echo "INNER_SETUP_OK"
EOF

# ---------- termux-side start / stop ----------
cat > "$ATL/start-atl.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock 2>/dev/null
proot-distro login ubuntu --fix-low-ports -- bind "$HOME/AI-Trading-Lab-Phone" /atl -- bash /atl/system/start-inner.sh
sleep 5
echo ""
echo "=============================================="
echo "  AI TRADING LAB - PHONE SERVER RUNNING"
echo "=============================================="
for p in 81 3000 3003; do
  (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "  Port $p : ONLINE" || echo "  Port $p : check logs"
done
echo ""
echo "  App (Local mode) : address = 127.0.0.1"
echo "  Browser          : http://127.0.0.1:81"
echo "  Login   : Muhammad / muhammadasterschool@gmail.com"
echo "  Password: AurumLab2026"
echo "  Stop    : bash ~/AI-Trading-Lab-Phone/stop-atl.sh"
echo "  Start   : bash ~/AI-Trading-Lab-Phone/start-atl.sh"
echo ""
echo "  BACKGROUND TIP: keep the Termux notification ON,"
echo "  disable battery optimization for Termux in"
echo "  Android Settings - paper trading keeps running."
echo "=============================================="
EOF

cat > "$ATL/stop-atl.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
proot-distro login ubuntu -- bind "$HOME/AI-Trading-Lab-Phone" /atl -- bash -c 'pkill -f "index.ts" 2>/dev/null; pkill -f "server.js" 2>/dev/null; pkill -f caddy 2>/dev/null; true'
termux-wake-unlock 2>/dev/null
echo "AI Trading Lab phone server stopped."
EOF
chmod +x "$ATL/start-atl.sh" "$ATL/stop-atl.sh"

echo "[5/6] Installing system inside Ubuntu (first time 5-20 min)..."
proot-distro login ubuntu --fix-low-ports -- bind "$ATL" /atl -- bash /atl/inner-setup.sh

echo "[6/6] Starting phone server..."
bash "$ATL/start-atl.sh"

echo ""
echo "SETUP COMPLETE - full system now runs ON THIS PHONE."
echo "Tomorrow onward: just open Termux and run:"
echo "  bash ~/AI-Trading-Lab-Phone/start-atl.sh"
