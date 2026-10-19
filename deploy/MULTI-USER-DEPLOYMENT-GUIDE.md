# MULTI-USER DEPLOYMENT GUIDE (Stage F, Part 9 F5)

Owner model (ratified): **ONE USER = ONE DEDICATED CLOUD SERVER.**
There is NO shared central backend. Every user (owner included) runs
their own server instance holding EXACTLY their own config, state,
logs, and credentials. The ONLY cross-server communication is the
optional one-way outbound health heartbeat to the owner's admin
registry (see ADMIN-PANEL-GUIDE.md).

LIVE TRADING REMAINS NOT AUTHORIZED. Every deployed server is
structurally paper-only (four enforcement layers + tests). PAPER_READY
stays FALSE until each owner separately authorizes the paper soak.

---

## 1. User onboarding flow (rent → install → connect → verify)

```
rent VPS (Ubuntu 22.04/24.04 or Debian 12, 1 vCPU/1GB is enough)
  │
  ▼
point DNS:  engine.<user-domain>  →  VPS IPv4
  │
  ▼
ssh root@<vps>
git clone https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git
cd ai-trading-lab-data-engine
./deploy/server-install.sh --domain engine.<user-domain> \
    [--registry-url https://registry.<owner-domain>/heartbeat \
     --registry-token-file <ingest-token-file> \
     --user-label "<user>-primary"]
  │        (script: deps → dedicated user → engine+venv → generated
  │         secrets → systemd hardened service → nginx+TLS → ufw →
  │         health check; fully automated, one command)
  ▼
copy the monitoring token:  cat /etc/ai-trading-lab/monitor.token
  │
  ▼
install the APK on the phone → "Add server":
    server URL  = https://engine.<user-domain>
    token       = <the monitoring token>
  │
  ▼
verify: dashboard shows Engine health (mode/version/uptime);
        https://engine.<user-domain>/api/health with the token
        returns JSON health.
```

## 2. What each user server holds (strict per-user isolation)

| Path | Contents |
| --- | --- |
| `/opt/ai-trading-lab/` | engine code + venv (read-only for the service user) |
| `/etc/ai-trading-lab/monitor.token` | THIS user's monitoring token (root:aitl 0640) |
| `/etc/ai-trading-lab/mac.key` | THIS user's ledger MAC custody key (generated on-host) |
| `/etc/ai-trading-lab/registry.token` | heartbeat ingest token (optional; owner-issued) |
| `/var/lib/ai-trading-lab/` | THIS user's execution state (journals, snapshots) |
| `/var/log/ai-trading-lab/` | THIS user's redacted logs |

No user's server ever receives another user's data. The APK talks
ONLY to its configured server. There is no shared account, no shared
database, no cross-user API.

## 3. Token generation, rotation, revocation

- **Generation**: `server-install.sh` generates a fresh 32-hex
  monitoring token per server (never reused, never transmitted
  except by the user reading it into their own app).
- **Rotation** (recommended periodically):
  1. `openssl rand -hex 32 > /etc/ai-trading-lab/monitor.token.new && \
     mv /etc/ai-trading-lab/monitor.token.new /etc/ai-trading-lab/monitor.token && \
     chown root:aitl /etc/ai-trading-lab/monitor.token && chmod 0640 /etc/ai-trading-lab/monitor.token`
  2. `systemctl restart ai-trading-lab`
  3. Update the token in the APK profile (edit profile → new token).
  4. Old token is dead the moment the service restarts.
- **Revocation** (phone lost): rotate the token (same steps). If the
  user server must be locked down entirely: `systemctl stop
  ai-trading-lab` — the monitoring API and the engine stop together.
- **MAC custody key rotation** follows the keyed-custody runbook
  (`RUNTIME_LEDGER_MAC_KEY_FILE`; re-keying is an audited engine
  operation — see the engine docs).

## 4. Heartbeat (optional, per user choice)

With `--registry-url/--registry-token-file/--user-label` the engine
sends the one-way health heartbeat every 45s (configurable via
`--heartbeat-interval`, 30-60s band):
- payload = identity + health ONLY (user label, server id, engine
  mode/version, uptime, feed health, risk state, kill switch,
  timestamp) — data minimization TEST-ENFORCED engine-side AND
  server-side;
- graceful degradation: registry unreachable ⇒ logged + counted,
  NEVER blocks or halts the engine;
- the registry can NEVER send anything back (no control channel).

Users who prefer zero cross-server traffic simply omit the flags.

## 5. Updates

```
ssh root@<vps>
cd /opt/ai-trading-lab/engine
git fetch --tags && git checkout main && git reset --hard origin/main
/opt/ai-trading-lab/venv/bin/python -m pip install -e .
systemctl restart ai-trading-lab
```
On restart the engine runs its conservative recovery +
reconciliation pass (fail-closed: divergence ⇒ halt + incident, never
silent optimism). State survives updates (`/var/lib/ai-trading-lab`).

## 6. Backup / restore

- BACK UP: `/var/lib/ai-trading-lab/` (state) + `/etc/ai-trading-lab/`
  (secrets — store in the user's password manager, not beside the
  VPS). Everything is plain (MAC-protected) JSON; a nightly tar cron
  is sufficient:
  `30 3 * * * tar -czf /var/backups/aitl-$(date +\%F).tgz /var/lib/ai-trading-lab`
- RESTORE: stop service → restore directories → start service →
  the engine verifies the MAC chains; a chain that does not verify
  fails closed with a runbook pointer.

## 7. User offboarding (server teardown)

```
ssh root@<vps>
systemctl disable --now ai-trading-lab
rm -rf /opt/ai-trading-lab /etc/ai-trading-lab \
       /var/lib/ai-trading-lab /var/log/ai-trading-lab
rm /etc/nginx/sites-enabled/ai-trading-lab && nginx -t && systemctl reload nginx
certbot delete --cert-name engine.<user-domain>
deluser --remove-home aitl    # if the account is no longer needed
```
Then destroy/return the VPS. If the user heartbeated the owner
registry, their entry goes OFFLINE and can be removed from the
roster (ADMIN-PANEL-GUIDE.md §housekeeping).

## 8. Troubleshooting

| Symptom | Check |
| --- | --- |
| install fails at certbot | DNS not pointing at the VPS yet; re-run `certbot --nginx -d <domain>` after DNS propagates |
| health check fails post-install | `journalctl -u ai-trading-lab -n 50` |
| APK "invalid or expired token" | token mismatch → re-copy `/etc/ai-trading-lab/monitor.token`; rotate if the phone was lost |
| APK "timeout" | nginx down / domain TLS expired / server offline → `systemctl status nginx ai-trading-lab` |
| kill switch returns 503 | activator not wired in the bare supervisor path — expected until a composed operational session is running; the refusal is fail-closed by design |
