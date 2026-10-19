#!/usr/bin/env bash
# admin-install.sh — ONE-COMMAND admin registry + panel deployment
# (Stage F, Part 9 F6). Runs ONLY on the OWNER's VPS.
#
# Provisions: admin registry service (one-way heartbeat ingestion,
# READ-ONLY panel) + systemd + nginx HTTPS + generated tokens +
# daily state backup.
#
# Usage (Ubuntu/Debian, as root):
#   ./admin-install.sh --domain registry.example.com \
#       [--repo-url https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git] \
#       [--repo-ref main]
#
# The registry receives ONLY identity + health fields (data
# minimization enforced engine-side AND server-side + tests). It can
# NEVER control user servers; user servers never depend on it.

set -euo pipefail

DOMAIN=""
REPO_URL="https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git"
REPO_REF="main"
ADMIN_USER="aitladmin"
INSTALL_ROOT="/opt/ai-trading-lab-admin"
ETC_DIR="/etc/ai-trading-lab-admin"
STATE_DIR="/var/lib/ai-trading-lab-admin"
PORT=8019

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --repo-ref) REPO_REF="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$DOMAIN" ]] || { echo "ERROR: --domain is required" >&2; exit 1; }

echo "== AI Trading Lab — ADMIN registry + panel install (owner VPS) =="

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 git nginx certbot python3-certbot-nginx \
  ufw curl openssl >/dev/null

if ! id -u "$ADMIN_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_ROOT" --shell /usr/sbin/nologin "$ADMIN_USER"
fi

mkdir -p "$INSTALL_ROOT"
if [[ -d "$INSTALL_ROOT/engine/.git" ]]; then
  git -C "$INSTALL_ROOT/engine" fetch --tags --quiet
  git -C "$INSTALL_ROOT/engine" checkout --quiet "$REPO_REF"
else
  git clone --quiet "$REPO_URL" "$INSTALL_ROOT/engine"
  git -C "$INSTALL_ROOT/engine" checkout --quiet "$REPO_REF"
fi
install -m 0755 -o root -g root \
  "$INSTALL_ROOT/engine/deploy/admin/admin_registry.py" \
  "$INSTALL_ROOT/admin_registry.py"

mkdir -p "$ETC_DIR" "$STATE_DIR"
chown -R "$ADMIN_USER":"$ADMIN_USER" "$STATE_DIR"
chmod 0750 "$STATE_DIR"

install -m 0640 -o root -g "$ADMIN_USER" /dev/null "$ETC_DIR/admin.token"
[[ -s "$ETC_DIR/admin.token" ]] || openssl rand -hex 32 | tr -d '\n' > "$ETC_DIR/admin.token"
install -m 0640 -o root -g "$ADMIN_USER" /dev/null "$ETC_DIR/ingest.token"
[[ -s "$ETC_DIR/ingest.token" ]] || openssl rand -hex 32 | tr -d '\n' > "$ETC_DIR/ingest.token"
echo "[ok] tokens generated: $ETC_DIR/admin.token (panel login), $ETC_DIR/ingest.token (user-server heartbeats)"

cat > /etc/systemd/system/ai-trading-lab-admin.service <<UNIT
[Unit]
Description=AI Trading Lab admin registry + panel (READ-ONLY monitoring)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ADMIN_USER
Group=$ADMIN_USER
ExecStart=/usr/bin/python3 $INSTALL_ROOT/admin_registry.py \\
    --state-dir $STATE_DIR \\
    --ingest-token-file $ETC_DIR/ingest.token \\
    --admin-token-file $ETC_DIR/admin.token \\
    --bind 127.0.0.1 --port $PORT
Restart=on-failure
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=$STATE_DIR
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ai-trading-lab-admin.service
echo "[ok] systemd service ai-trading-lab-admin enabled + started"

cat > "/etc/nginx/sites-available/ai-trading-lab-admin" <<NGINX
server {
    listen 80;
    server_name $DOMAIN;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/ai-trading-lab-admin /etc/nginx/sites-enabled/ai-trading-lab-admin
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || {
  echo "WARNING: certbot could not issue a certificate — re-run: certbot --nginx -d $DOMAIN" >&2
}

ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

# daily state backup (registry roster + history)
cat > /etc/cron.d/ai-trading-lab-admin-backup <<'CRON'
30 3 * * * root tar -czf /var/backups/ai-trading-lab-admin-$(date +\%F).tgz /var/lib/ai-trading-lab-admin 2>/dev/null && find /var/backups -name 'ai-trading-lab-admin-*.tgz' -mtime +14 -delete
CRON
echo "[ok] daily backup cron installed (/var/backups, 14-day retention)"

sleep 2
if curl -fsS "http://127.0.0.1:$PORT/" >/dev/null; then
  echo "[ok] admin registry healthy on loopback:$PORT"
else
  echo "ERROR: admin registry health check FAILED — journalctl -u ai-trading-lab-admin -n 50" >&2
  exit 1
fi

echo ""
echo "== ADMIN INSTALL COMPLETE =="
echo "   panel:              https://$DOMAIN/  (login: $ETC_DIR/admin.token)"
echo "   heartbeat endpoint: https://$DOMAIN/heartbeat"
echo "   ingest token for user servers: $ETC_DIR/ingest.token"
echo "   backups:            /var/backups/ai-trading-lab-admin-*.tgz (daily)"
echo ""
echo "NEXT: for each user server run deploy/server-install.sh with:"
echo "        --registry-url https://$DOMAIN/heartbeat \\"
echo "        --registry-token-file <copy of $ETC_DIR/ingest.token> \\"
echo "        --user-label \"<that user's label>\""
