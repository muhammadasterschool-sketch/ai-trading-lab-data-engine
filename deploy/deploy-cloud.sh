#!/usr/bin/env bash
# ============================================================
#  AI Trading Lab — Data Engine v4 · CLOUD DEPLOY (Ubuntu VPS)
#  Run on a fresh Ubuntu 20.04/22.04/24.04 server as root:
#      bash deploy/deploy-cloud.sh your-domain.com
#  (or without a domain for IP-only HTTP access)
# ============================================================
set -e
DOMAIN="${1:-}"
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

echo "======================================================"
echo "  AI TRADING LAB — CLOUD DEPLOY"
echo "  Domain: ${DOMAIN:-<none — HTTP on server IP>}"
echo "======================================================"

[ "$(id -u)" = 0 ] || { echo "Run as root: sudo bash deploy/deploy-cloud.sh"; exit 1; }

# ---------- runtime ----------
if ! command -v bun >/dev/null 2>&1; then
  echo "[deps] installing bun…"
  curl -fsSL https://bun.sh/install | bash
  export BUN_INSTALL="$HOME/.bun"
  export PATH="$BUN_INSTALL/bin:$PATH"
  ln -sf "$BUN_INSTALL/bin/bun" /usr/local/bin/bun 2>/dev/null || true
fi

# ---------- caddy ----------
if ! command -v caddy >/dev/null 2>&1; then
  echo "[deps] installing Caddy…"
  apt-get update -qq
  apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl >/dev/null
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  apt-get update -qq && apt-get install -y -qq caddy
fi

# ---------- build ----------
echo "[build] installing + building…"
# portable .env (absolute DB path for THIS server)
echo "DATABASE_URL=file://$ROOT/db/custom.db" > .env
echo "DATABASE_URL=file://$ROOT/db/custom.db" > mini-services/trading-engine/.env
bun install
bun run build

# ---------- systemd services ----------
cat > /etc/systemd/system/atl-engine.service <<EOF
[Unit]
Description=AI Trading Lab — realtime trading engine (:3003)
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT/mini-services/trading-engine
ExecStart=$ROOT/node_modules/.bin/bun run dev
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/atl-web.service <<EOF
[Unit]
Description=AI Trading Lab — web app (:3000)
After=network.target atl-engine.service

[Service]
Type=simple
WorkingDirectory=$ROOT/.next/standalone
Environment=NODE_ENV=production
Environment=DATABASE_URL=file://$ROOT/db/custom.db
ExecStart=/usr/local/bin/bun server.js
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now atl-engine atl-web

# ---------- caddy site ----------
if [ -n "$DOMAIN" ]; then
  cat > /etc/caddy/sites/ai-trading-lab.caddy 2>/dev/null || cat > /etc/caddy/Caddyfile.d/ai-trading-lab.caddy 2>/dev/null || true
  CFG=/etc/caddy/ai-trading-lab.caddy
  cat > "$CFG" <<EOF
$DOMAIN {
        @transform_port_query {
                query XTransformPort=*
        }
        handle @transform_port_query {
                reverse_proxy localhost:{query.XTransformPort}
        }
        handle {
                reverse_proxy localhost:3000
        }
}
EOF
  # include the site config if main Caddyfile doesn't import it
  grep -q "ai-trading-lab" /etc/caddy/Caddyfile 2>/dev/null || echo "import /etc/caddy/ai-trading-lab.caddy" >> /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
  echo ""
  echo "  CLOUD URL:  https://$DOMAIN"
else
  CFG=/etc/caddy/ai-trading-lab.caddy
  cat > "$CFG" <<EOF
:80 {
        @transform_port_query {
                query XTransformPort=*
        }
        handle @transform_port_query {
                reverse_proxy localhost:{query.XTransformPort}
        }
        handle {
                reverse_proxy localhost:3000
        }
}
EOF
  grep -q "ai-trading-lab" /etc/caddy/Caddyfile 2>/dev/null || echo "import /etc/caddy/ai-trading-lab.caddy" >> /etc/caddy/Caddyfile
  systemctl reload caddy || systemctl restart caddy
  IP=$(curl -s ifconfig.me || echo SERVER_IP)
  echo ""
  echo "  CLOUD URL:  http://$IP"
fi

# firewall
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true

echo ""
echo "======================================================"
echo "  DONE. In the Android/iOS/Windows app enter the URL"
echo "  above (Cloud mode). Engine auto-starts on boot."
echo ""
echo "  Logs:   journalctl -u atl-engine -f"
echo "         journalctl -u atl-web -f"
echo "  Restart: systemctl restart atl-engine atl-web"
echo "======================================================"
