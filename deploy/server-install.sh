#!/usr/bin/env bash
# server-install.sh — ONE-COMMAND per-user VPS deployment (Stage F, Part 9 F5).
#
# Provisions ONE user's dedicated server: engine + authenticated
# monitoring API + systemd service + nginx HTTPS reverse proxy with
# automatic Let's Encrypt certificates + generated secrets.
#
# Per the owner's multi-user model: ONE USER = ONE DEDICATED SERVER.
# This server holds EXACTLY ONE user's config, state, logs, and
# credentials. The ONLY cross-server traffic is the optional one-way
# outbound health heartbeat to the owner's admin registry.
#
# Usage (Ubuntu/Debian, as root):
#   ./server-install.sh --domain engine.example.com \
#       [--repo-url https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git] \
#       [--repo-ref main] \
#       [--registry-url https://registry.example.com/heartbeat] \
#       [--registry-token-file /path/to/ingest-token] \
#       [--user-label "alice-primary"]
#
# Secrets are GENERATED on this host (openssl rand) and stored ONLY in
# /etc/ai-trading-lab/ with root:aitl 0640. Nothing secret is embedded
# in this script, the repo, or any artifact.
#
# LIVE TRADING REMAINS NOT AUTHORIZED (the engine is structurally
# paper-only). PAPER_READY stays FALSE until the owner's separate
# soak authorization.

set -euo pipefail

DOMAIN=""
REPO_URL="https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git"
REPO_REF="main"
REGISTRY_URL=""
REGISTRY_TOKEN_FILE=""
USER_LABEL=""
ENGINE_USER="aitl"
INSTALL_ROOT="/opt/ai-trading-lab"
ETC_DIR="/etc/ai-trading-lab"
STATE_DIR="/var/lib/ai-trading-lab"
LOG_DIR="/var/log/ai-trading-lab"
MONITOR_PORT=8018

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --repo-ref) REPO_REF="$2"; shift 2 ;;
    --registry-url) REGISTRY_URL="$2"; shift 2 ;;
    --registry-token-file) REGISTRY_TOKEN_FILE="$2"; shift 2 ;;
    --user-label) USER_LABEL="$2"; shift 2 ;;
    --engine-user) ENGINE_USER="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

[[ -n "$DOMAIN" ]] || { echo "ERROR: --domain is required (TLS certificate name)" >&2; exit 1; }
if [[ -n "$REGISTRY_URL" ]]; then
  [[ -n "$REGISTRY_TOKEN_FILE" ]] || { echo "ERROR: --registry-token-file is required with --registry-url" >&2; exit 1; }
  [[ -n "$USER_LABEL" ]] || {
    read -r -p "Heartbeat user label for this server (e.g. \"alice-primary\"): " USER_LABEL
  }
  [[ -n "$USER_LABEL" ]] || { echo "ERROR: a non-empty --user-label is required for heartbeat identity" >&2; exit 1; }
fi

echo "== AI Trading Lab — per-user server install =="
echo "   domain:            $DOMAIN"
echo "   engine user:       $ENGINE_USER"
echo "   registry heartbeat: ${REGISTRY_URL:-DISABLED (pass --registry-url to enable)}"
echo "   user label:        ${USER_LABEL:-n/a}"

# -- 1. system packages ----------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx \
  certbot python3-certbot-nginx ufw curl openssl >/dev/null
echo "[ok] system packages installed"

# -- 2. dedicated engine user ----------------------------------------------
if ! id -u "$ENGINE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$INSTALL_ROOT" --shell /usr/sbin/nologin "$ENGINE_USER"
fi
echo "[ok] engine user $ENGINE_USER"

# -- 3. engine source + venv -------------------------------------------------
mkdir -p "$INSTALL_ROOT"
if [[ -d "$INSTALL_ROOT/engine/.git" ]]; then
  git -C "$INSTALL_ROOT/engine" fetch --tags --quiet
  git -C "$INSTALL_ROOT/engine" checkout --quiet "$REPO_REF"
  git -C "$INSTALL_ROOT/engine" reset --hard "origin/$REPO_REF" --quiet 2>/dev/null \
    || git -C "$INSTALL_ROOT/engine" reset --hard "$REPO_REF" --quiet
else
  git clone --quiet "$REPO_URL" "$INSTALL_ROOT/engine"
  git -C "$INSTALL_ROOT/engine" checkout --quiet "$REPO_REF"
fi
python3 -m venv "$INSTALL_ROOT/venv"
"$INSTALL_ROOT/venv/bin/python" -m pip install --quiet --upgrade pip
"$INSTALL_ROOT/venv/bin/python" -m pip install --quiet -e "$INSTALL_ROOT/engine"
echo "[ok] engine installed at $INSTALL_ROOT (ref $REPO_REF)"

# -- 4. generated secrets (root:engine 0640) ---------------------------------
mkdir -p "$ETC_DIR"
install -m 0640 -o root -g "$ENGINE_USER" /dev/null "$ETC_DIR/monitor.token"
if [[ ! -s "$ETC_DIR/monitor.token" ]]; then
  openssl rand -hex 32 | tr -d '\n' > "$ETC_DIR/monitor.token"
fi
install -m 0640 -o root -g "$ENGINE_USER" /dev/null "$ETC_DIR/mac.key"
if [[ ! -s "$ETC_DIR/mac.key" ]]; then
  openssl rand -hex 32 | tr -d '\n' > "$ETC_DIR/mac.key"
fi
if [[ -n "$REGISTRY_URL" ]]; then
  install -m 0640 -o root -g "$ENGINE_USER" "$REGISTRY_TOKEN_FILE" "$ETC_DIR/registry.token"
fi
echo "[ok] secrets generated in $ETC_DIR (root:$ENGINE_USER 0640; never logged, never committed)"

# -- 5. state + log dirs -------------------------------------------------------
mkdir -p "$STATE_DIR" "$LOG_DIR"
chown -R "$ENGINE_USER":"$ENGINE_USER" "$STATE_DIR" "$LOG_DIR"
chmod 0750 "$STATE_DIR" "$LOG_DIR"

# -- 6. systemd service ---------------------------------------------------------
REGISTRY_ARGS=""
if [[ -n "$REGISTRY_URL" ]]; then
  REGISTRY_ARGS="--registry-url $REGISTRY_URL --registry-token-file $ETC_DIR/registry.token --user-label $(printf '%q' "$USER_LABEL")"
fi
cat > "/etc/systemd/system/ai-trading-lab.service" <<UNIT
[Unit]
Description=AI Trading Lab Data Engine (paper-only; monitoring API on loopback)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ENGINE_USER
Group=$ENGINE_USER
Environment=RUNTIME_LEDGER_MAC_KEY_FILE=$ETC_DIR/mac.key
ExecStart=$INSTALL_ROOT/venv/bin/python -m data_engine.cli serve \\
    --monitor-bind 127.0.0.1 --monitor-port $MONITOR_PORT \\
    --monitor-token-file $ETC_DIR/monitor.token $REGISTRY_ARGS
Restart=on-failure
RestartSec=10

# hardening (matches deploy/systemd/ restrictions)
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
ReadWritePaths=$STATE_DIR $LOG_DIR
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now ai-trading-lab.service
echo "[ok] systemd service ai-trading-lab enabled + started"

# -- 7. nginx HTTPS reverse proxy (public TLS -> loopback monitoring API) -------
cat > "/etc/nginx/sites-available/ai-trading-lab" <<NGINX
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$MONITOR_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        # the engine-side API enforces token auth + rate limits itself;
        # nginx adds TLS termination + modest connection caps
        limit_conn perip 20;
    }
}
NGINX
ln -sf /etc/nginx/sites-available/ai-trading-lab /etc/nginx/sites-enabled/ai-trading-lab
rm -f /etc/nginx/sites-enabled/default
# per-IP connection zone (used above)
grep -q 'limit_conn_zone' /etc/nginx/nginx.conf || \
  sed -i 's|http {|http {\n    limit_conn_zone $binary_remote_addr zone=perip:10m;|' /etc/nginx/nginx.conf
nginx -t
systemctl reload nginx
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || {
  echo "WARNING: certbot could not issue a certificate (DNS not pointing here yet?)." >&2
  echo "         Re-run: certbot --nginx -d $DOMAIN" >&2
}
echo "[ok] nginx + TLS for $DOMAIN"

# -- 8. firewall ------------------------------------------------------------------
ufw allow 22/tcp >/dev/null 2>&1 || true
ufw allow 80/tcp >/dev/null 2>&1 || true
ufw allow 443/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
echo "[ok] ufw: 22/80/443 open"

# -- 9. health check ----------------------------------------------------------------
sleep 2
TOKEN=$(cat "$ETC_DIR/monitor.token")
if curl -fsS -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:$MONITOR_PORT/api/health" >/dev/null; then
  echo "[ok] monitoring API healthy on loopback:$MONITOR_PORT"
else
  echo "ERROR: monitoring API health check FAILED — inspect: journalctl -u ai-trading-lab -n 50" >&2
  exit 1
fi

echo ""
echo "== INSTALL COMPLETE =="
echo "   monitoring endpoint:   https://$DOMAIN/api/health"
echo "   APK connection:        server URL https://$DOMAIN  +  token file $ETC_DIR/monitor.token"
echo "   logs:                  journalctl -u ai-trading-lab -f"
echo "   state:                 $STATE_DIR (back this up)"
echo "   heartbeat:             ${REGISTRY_URL:-not configured}"
echo ""
echo "NEXT: give the token file contents to your APK login (server URL + token)."
echo "      The token never leaves this host except into your app's secure storage."
