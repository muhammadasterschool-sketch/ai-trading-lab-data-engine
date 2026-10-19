# ADMIN PANEL GUIDE (Stage F, Part 9 F6)

The admin registry + panel is deployed ONLY on the OWNER's VPS. It
is a READ-ONLY monitoring console over the one-way health
heartbeats sent by every (opting-in) user server.

**The panel can NEVER control user servers.** There is no command
channel — by construction the registry exposes no endpoint that
sends anything to any user server, and user-server operation NEVER
depends on registry reachability (graceful degradation both sides).

## 1. Deploy (one command, owner VPS, Ubuntu/Debian)

```
ssh root@<owner-vps>
git clone https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git
cd ai-trading-lab-data-engine
./deploy/admin/admin-install.sh --domain registry.<owner-domain>
```

Installs: registry service (systemd, hardened) + nginx HTTPS
(Let's Encrypt) + generated tokens + daily state backup cron.

Outputs:
- Panel: `https://registry.<owner-domain>/` — login with the admin
  token (`/etc/ai-trading-lab-admin/admin.token`).
- Heartbeat endpoint: `https://registry.<owner-domain>/heartbeat`
- Ingest token for user servers:
  `/etc/ai-trading-lab-admin/ingest.token` — hand a COPY to each
  user who opts into heartbeat (it authenticates their POSTs).

## 2. Add / remove users

- **Add**: the user runs `deploy/server-install.sh` on their VPS with
  `--registry-url https://registry.<owner-domain>/heartbeat
  --registry-token-file <copy-of-ingest-token>
  --user-label "<label>"`. Their server appears in the roster on the
  first heartbeat.
- **Remove / offboard**: user teardown (MULTI-USER-DEPLOYMENT-GUIDE
  §7). The entry turns OFFLINE; delete the entry by removing its
  record from `/var/lib/ai-trading-lab-admin/registry.json` (stop
  the service first, edit, start) — the registry stores ONLY
  identity + health, so removal loses nothing else.

## 3. Rotate the admin token

```
openssl rand -hex 32 > /etc/ai-trading-lab-admin/admin.token.new
mv /etc/ai-trading-lab-admin/admin.token.new /etc/ai-trading-lab-admin/admin.token
chown root:aitladmin /etc/ai-trading-lab-admin/admin.token && chmod 0640 /etc/ai-trading-lab-admin/admin.token
systemctl restart ai-trading-lab-admin
```
Existing browser sessions fail at next fetch (panel token is
per-request Bearer auth; nothing server-side persists sessions).

Rotating the INGEST token: same steps for `ingest.token`, then
re-distribute to user servers and restart each of their services.

## 4. Reading the panel

Each roster card shows:
- **NAME/LABEL** — the heartbeat `user_label`;
- **ONLINE / OFFLINE** — missed-heartbeat detection (no heartbeat
  within 3× the 45s interval ⇒ OFFLINE);
- **last seen** — UTC timestamp of the last accepted heartbeat;
- **engine mode / version** — PAPER_SUPERVISOR + engine version;
- **feed health / risk state / kill switch** — the honest values the
  user server reported (`NOT_WIRED` until a composed operational
  session reports real ones);
- **active alerts** — badges: OFFLINE, KILL_SWITCH_ACTIVE,
  RISK_STATE_ALARM, FEED_NOT_HEALTHY.

Filter/sort by label/server; export the roster as CSV (button) or
fetch `GET /api/roster.csv` with the admin Bearer token.

## 5. Offline alerting

The panel badge flips OFFLINE when heartbeats stop. For push-style
alerting (email/Telegram), poll the roster API from any small cron:

```
curl -sS -H "Authorization: Bearer $(cat /etc/ai-trading-lab-admin/admin.token)" \
     https://registry.<owner-domain>/api/roster \
  | jq -r '.[] | select(.online==false) | .user_label'
```
and notify on non-empty output (that surface is deliberately NOT
built into the registry — keep the registry minimal).

## 6. Data minimization (owner mandate — enforced)

The heartbeat payload contains ONLY: schema, user_label, server_id,
engine_mode, engine_version, uptime_seconds, feed_health, risk_state,
kill_switch, timestamp. NEVER positions, PnL, orders, broker
details, keys, or credentials. This is enforced in THREE places:
1. engine-side builder (`runtime/heartbeat.py`) — extra fields raise;
2. tests (`tests/test_monitoring_api.py`) — payload field set is
   pinned exactly;
3. registry-side validation (`deploy/admin/admin_registry.py`) —
   payloads with unknown/forbidden fields are rejected 400 and never
   stored (tests: `tests/test_admin_registry.py`).

The stored roster file contains exactly the accepted fields plus
arrival bookkeeping — nothing else ever reaches the owner's VPS.

## 7. Backup

`admin-install.sh` installs a daily cron: tars
`/var/lib/ai-trading-lab-admin` to `/var/backups/` (14-day
retention). The registry state is one JSON file; restoring = stop
service, replace file, start service.

## 8. Health fields glossary

| Field | Meaning | Alarm when |
| --- | --- | --- |
| `engine_mode` | what the server reports it is running | anything but PAPER* ⇒ investigate |
| `engine_version` | engine version string | version skew across fleet |
| `uptime_seconds` | engine uptime (restarts visible as resets) | frequent resets ⇒ crash loop |
| `feed_health` | feed freshness verdict | STALE/ERROR/FAIL |
| `risk_state` | risk gate disposition | VIOLATION/HALT/BREACH |
| `kill_switch` | kill-switch state | ACTIVE (trading halted) |
