#!/usr/bin/env python3
"""ADMIN REGISTRY + PANEL (Stage F, Part 9 F6 — owner mandate).

Deployed ONLY on the owner's VPS (deploy/admin/admin-install.sh).
Receives the ONE-WAY outbound health heartbeats from every user
server; serves a mobile-friendly READ-ONLY admin panel.

Contract:

- **Ingestion**: POST /heartbeat, Bearer INGEST token. The payload
  is validated against EXACTLY the documented heartbeat fields
  (data minimization enforced SERVER-SIDE TOO: a payload carrying
  positions/PnL/orders/broker/credential fields is REJECTED 400 and
  NEVER stored).
- **Panel**: GET / — mobile-friendly HTML (admin-token login);
  GET /api/roster (admin token) — user list with NAME/LABEL,
  ONLINE/OFFLINE (missed-heartbeat detection), last seen, engine
  mode, version, feed health, risk state, kill switch;
  GET /api/roster.csv — exportable roster.
- **READ-ONLY**: the registry can NEVER control user servers (no
  command channel exists — by construction there is no endpoint that
  sends anything to a user server).
- **Storage**: one JSON file, atomic writes; the ONLY stored data is
  the allowed heartbeat fields + arrival bookkeeping.
- **Offline detection**: a server is OFFLINE when no heartbeat
  arrived within 3x the default interval (45s -> 135s).

stdlib-only; no framework, no new engine dependencies. The registry
never holds user positions, PnL, orders, broker details, or any
credential material — it structurally cannot: those fields are
rejected before storage.

Usage:
    python3 admin_registry.py --state-dir DIR --ingest-token-file F \
        --admin-token-file F [--bind 127.0.0.1] [--port 8019]
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# EXACTLY the documented heartbeat vocabulary (mirrors
# data_engine.runtime.monitoring.HEARTBEAT_ALLOWED_FIELDS — kept
# literal here so the registry stays a standalone deployable).
ALLOWED_FIELDS = {
    "schema",
    "user_label",
    "server_id",
    "engine_mode",
    "engine_version",
    "uptime_seconds",
    "kill_switch",
    "feed_health",
    "risk_state",
    "timestamp",
}

# defensive: field NAMES that must never appear (belt + braces — the
# allow-list above already rejects anything unknown).
FORBIDDEN_SUBSTRINGS = (
    "position", "pnl", "order", "broker", "credential", "secret",
    "token", "api_key", "password", "balance", "fill", "trade",
)

OFFLINE_MULTIPLIER = 3
DEFAULT_INTERVAL_SECONDS = 45.0

_RISK_ALARM = re.compile(r"VIOLATION|HALT|BREACH", re.IGNORECASE)
_FEED_ALARM = re.compile(r"STALE|ERROR|FAIL", re.IGNORECASE)

PANEL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Trading Lab — Admin Panel</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background:#10141c;
         color:#e6e9ef; padding: 1rem; max-width: 860px; margin: 0 auto; }
  h1 { font-size: 1.15rem; margin-bottom: .25rem; }
  .sub { color:#8b93a7; font-size:.8rem; margin-bottom: 1rem; }
  #login { display:flex; gap:.5rem; margin-bottom:1rem; }
  input { flex:1; padding:.6rem; border-radius:8px; border:1px solid #2a3140;
          background:#171c26; color:#e6e9ef; font-size:1rem; }
  button { padding:.6rem 1rem; border-radius:8px; border:0; background:#3b6ef5;
           color:#fff; font-size:1rem; cursor:pointer; }
  .card { background:#171c26; border:1px solid #262d3b; border-radius:12px;
          padding:.9rem 1rem; margin-bottom:.7rem; }
  .row { display:flex; justify-content:space-between; align-items:center;
         gap:.5rem; flex-wrap:wrap; }
  .label { font-weight:600; font-size:1rem; }
  .muted { color:#8b93a7; font-size:.78rem; }
  .online { color:#3ecf8e; font-weight:700; }
  .offline { color:#f6685e; font-weight:700; }
  .badge { display:inline-block; padding:.1rem .5rem; border-radius:999px;
           font-size:.72rem; background:#232a38; margin-left:.4rem; }
  .bad { background:#4a1f24; color:#f6685e; }
  table.meta { width:100%; font-size:.82rem; margin-top:.5rem; border-collapse:collapse; }
  table.meta td { padding:.15rem .3rem; color:#aeb6c8; }
  table.meta td:first-child { color:#8b93a7; width:9.5rem; }
  .toolbar { display:flex; gap:.5rem; margin-bottom:1rem; }
  .toolbar input { max-width: 14rem; }
  #toast { position:fixed; bottom:1rem; left:50%; transform:translateX(-50%);
           background:#232a38; padding:.5rem 1rem; border-radius:8px; font-size:.85rem;
           display:none; }
</style>
</head>
<body>
<h1>AI Trading Lab — Admin Registry</h1>
<div class="sub">READ-ONLY monitoring · one-way heartbeats · no control channel ·
data-minimized (identity + health only)</div>
<div id="login">
  <input id="token" type="password" placeholder="Admin token" autocomplete="off">
  <button id="go">Sign in</button>
</div>
<div class="toolbar" id="tools" style="display:none">
  <input id="filter" placeholder="Filter by label/server">
  <button id="export">Export CSV</button>
  <button id="refresh">Refresh</button>
</div>
<div id="roster"></div>
<div id="toast"></div>
<script>
let ADMIN_TOKEN = sessionStorage.getItem('atl_admin_token') || '';
let DATA = [];
const $ = (id) => document.getElementById(id);

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 2500);
}

async function load() {
  if (!ADMIN_TOKEN) return;
  const res = await fetch('/api/roster', {headers: {'Authorization': 'Bearer ' + ADMIN_TOKEN}});
  if (res.status === 401) { toast('Invalid admin token'); return; }
  DATA = await res.json();
  render();
}

function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function render() {
  const q = $('filter').value.trim().toLowerCase();
  const rows = DATA.filter(r => !q ||
    (r.user_label + ' ' + r.server_id).toLowerCase().includes(q));
  $('roster').innerHTML = rows.map(r => {
    const state = r.online ? '<span class="online">ONLINE</span>'
                           : '<span class="offline">OFFLINE</span>';
    const seen = r.last_seen_iso ? new Date(r.last_seen_iso).toLocaleString() : 'never';
    const alert = r.active_alerts.length ? '<span class="badge bad">ALERT</span>' : '';
    const ks = (r.kill_switch || '').toUpperCase();
    const ksBadge = ks.indexOf('ACTIVE') >= 0 ? '<span class="badge bad">KILL&nbsp;SWITCH&nbsp;ACTIVE</span>' : '';
    const riskBad = /VIOLATION|HALT|BREACH/i.test(r.risk_state || '');
    const riskBadge = riskBad ? '<span class="badge bad">RISK</span>' : '';
    return '<div class="card">' +
      '<div class="row"><span class="label">' + esc(r.user_label) + '</span>' +
      '<span>' + state + alert + ksBadge + riskBadge + '</span></div>' +
      '<div class="muted">' + esc(r.server_id) + ' · last seen ' + esc(seen) + '</div>' +
      '<table class="meta">' +
      '<tr><td>engine mode</td><td>' + esc(r.engine_mode) + '</td></tr>' +
      '<tr><td>version</td><td>' + esc(r.engine_version) + '</td></tr>' +
      '<tr><td>feed health</td><td>' + esc(r.feed_health) + '</td></tr>' +
      '<tr><td>risk state</td><td>' + esc(r.risk_state) + '</td></tr>' +
      '<tr><td>kill switch</td><td>' + esc(r.kill_switch) + '</td></tr>' +
      '<tr><td>uptime</td><td>' + (r.uptime_seconds == null ? '?' : Math.round(r.uptime_seconds/60) + ' min') + '</td></tr>' +
      '</table></div>';
  }).join('') || '<div class="card muted">No user servers registered yet.</div>';
}

$('go').onclick = async () => {
  ADMIN_TOKEN = $('token').value.trim();
  sessionStorage.setItem('atl_admin_token', ADMIN_TOKEN);
  await load();
  if (ADMIN_TOKEN) { $('tools').style.display = 'flex'; $('login').style.display = 'none'; }
};
$('token').addEventListener('keydown', e => { if (e.key === 'Enter') $('go').click(); });
$('filter').oninput = render;
$('refresh').onclick = load;
$('export').onclick = () => {
  const lines = ['user_label,server_id,online,last_seen,engine_mode,engine_version,feed_health,risk_state,kill_switch,uptime_seconds'];
  for (const r of DATA) lines.push([r.user_label, r.server_id, r.online, r.last_seen_iso || '',
    r.engine_mode, r.engine_version, r.feed_health, r.risk_state, r.kill_switch, r.uptime_seconds == null ? '' : r.uptime_seconds]
    .map(v => '"' + String(v).replace(/"/g, '""') + '"').join(','));
  const blob = new Blob([lines.join('\\n')], {type: 'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'ai-trading-lab-roster.csv'; a.click();
};
setInterval(load, 30000);
if (ADMIN_TOKEN) { $('tools').style.display = 'flex'; $('login').style.display = 'none'; load(); }
</script>
</body>
</html>
"""


class RegistryState:
    """Roster persistence: one JSON file, atomic writes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._servers: dict = {}
        if path.is_file():
            try:
                self._servers = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                # torn write: keep empty + back up the damaged file
                backup = path.with_suffix(".damaged")
                path.replace(backup)

    def record(self, payload: dict, interval_seconds: float) -> None:
        now = time.time()
        entry = {
            "user_label": str(payload["user_label"]),
            "server_id": str(payload["server_id"]),
            "engine_mode": str(payload.get("engine_mode", "UNKNOWN")),
            "engine_version": str(payload.get("engine_version", "UNKNOWN")),
            "uptime_seconds": payload.get("uptime_seconds"),
            "feed_health": str(payload.get("feed_health", "UNKNOWN")),
            "risk_state": str(payload.get("risk_state", "UNKNOWN")),
            "kill_switch": str(payload.get("kill_switch", "UNKNOWN")),
            "heartbeat_timestamp": payload.get("timestamp"),
            "last_seen_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)
            ),
            "last_seen_epoch": now,
            "declared_interval_seconds": interval_seconds,
        }
        self._servers[entry["server_id"]] = entry
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".registry-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._servers, fh, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def roster(self, now: float) -> list:
        out = []
        for server_id, entry in sorted(self._servers.items()):
            last = entry.get("last_seen_epoch")
            interval = (
                entry.get("declared_interval_seconds")
                or DEFAULT_INTERVAL_SECONDS
            )
            online = (
                last is not None
                and (now - last) <= interval * OFFLINE_MULTIPLIER
            )
            alerts = []
            if not online:
                alerts.append("OFFLINE (missed heartbeats)")
            if "ACTIVE" in str(entry.get("kill_switch", "")).upper():
                alerts.append("KILL_SWITCH_ACTIVE")
            if _RISK_ALARM.search(str(entry.get("risk_state", ""))):
                alerts.append("RISK_STATE_ALARM")
            if _FEED_ALARM.search(str(entry.get("feed_health", ""))):
                alerts.append("FEED_NOT_HEALTHY")
            out.append(
                {
                    "user_label": entry["user_label"],
                    "server_id": server_id,
                    "online": online,
                    "last_seen_iso": entry.get("last_seen_iso"),
                    "engine_mode": entry["engine_mode"],
                    "engine_version": entry["engine_version"],
                    "feed_health": entry["feed_health"],
                    "risk_state": entry["risk_state"],
                    "kill_switch": entry["kill_switch"],
                    "uptime_seconds": entry.get("uptime_seconds"),
                    "active_alerts": alerts,
                }
            )
        return out


def validate_heartbeat(payload) -> None:
    """Server-side DATA MINIMIZATION: allow-list enforcement."""
    if not isinstance(payload, dict):
        raise ValueError("heartbeat payload must be a JSON object")
    extra = set(payload) - ALLOWED_FIELDS
    if extra:
        raise ValueError(
            f"data minimization violated: unexpected fields {sorted(extra)} "
            "(rejected; nothing stored)"
        )
    missing = {"user_label", "server_id", "timestamp"} - set(payload)
    if missing:
        raise ValueError(f"missing required fields {sorted(missing)}")
    field_blob = json.dumps(sorted(payload))
    for field in FORBIDDEN_SUBSTRINGS:
        if field in field_blob:
            raise ValueError(f"forbidden field vocabulary: {field}")


class AdminRegistry:
    def __init__(
        self,
        *,
        ingest_token: str,
        admin_token: str,
        state_dir: Path,
        bind: str = "127.0.0.1",
        port: int = 8019,
    ) -> None:
        self._ingest_token = ingest_token
        self._admin_token = admin_token
        self._state = RegistryState(state_dir / "registry.json")
        self._bind = bind
        self._port = port
        self._server = None
        registry = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args) -> None:
                print(f"[admin-registry] {self.command} {self.path} "
                      f"from {self.client_address[0]}")

            def _json(self, code, payload) -> None:
                body = (
                    payload.encode("utf-8")
                    if isinstance(payload, str)
                    else json.dumps(payload).encode("utf-8")
                )
                self.send_response(int(code))
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _bearer(self) -> str:
                header = self.headers.get("Authorization", "")
                return header[7:].strip() if header.startswith("Bearer ") else ""

            def do_GET(self) -> None:  # noqa: N802
                route = self.path.split("?", 1)[0]
                if route == "/":
                    body = PANEL_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if not hmac.compare_digest(
                    self._bearer().encode(), registry._admin_token.encode()
                ):
                    self._json(HTTPStatus.UNAUTHORIZED,
                               {"error": "admin token required"})
                    return
                if route == "/api/roster":
                    self._json(HTTPStatus.OK,
                               registry._state.roster(time.time()))
                elif route == "/api/roster.csv":
                    rows = registry._state.roster(time.time())
                    lines = [
                        "user_label,server_id,online,last_seen,engine_mode,"
                        "engine_version,feed_health,risk_state,kill_switch,"
                        "uptime_seconds,active_alerts"
                    ]
                    for r in rows:
                        up = r["uptime_seconds"]
                        cells = [
                            r["user_label"], r["server_id"], str(r["online"]),
                            r["last_seen_iso"] or "", r["engine_mode"],
                            r["engine_version"], r["feed_health"],
                            r["risk_state"], r["kill_switch"],
                            "" if up is None else str(up),
                            ";".join(r["active_alerts"]),
                        ]
                        lines.append(
                            ",".join(
                                '"' + c.replace('"', '""') + '"' for c in cells
                            )
                        )
                    self._json(HTTPStatus.OK, "\n".join(lines) + "\n")
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                route = self.path.split("?", 1)[0]
                if route != "/heartbeat":
                    self._json(
                        HTTPStatus.NOT_FOUND,
                        {"error": "only POST /heartbeat exists "
                                  "(read-only registry)"},
                    )
                    return
                if not hmac.compare_digest(
                    self._bearer().encode(), registry._ingest_token.encode()
                ):
                    self._json(HTTPStatus.UNAUTHORIZED,
                               {"error": "invalid ingest token"})
                    return
                length = int(self.headers.get("Content-Length", "0") or 0)
                if not 0 < length <= 4096:
                    self._json(HTTPStatus.BAD_REQUEST,
                               {"error": "body required (max 4096 bytes)"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    validate_heartbeat(payload)
                except (ValueError, UnicodeDecodeError) as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                registry._state.record(payload, DEFAULT_INTERVAL_SECONDS)
                self._json(HTTPStatus.OK, {"status": "recorded"})

            def _method_not_allowed(self) -> None:
                self._json(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    {"error": "registry is read-only + ingest only"},
                )

            do_PUT = do_PATCH = do_DELETE = _method_not_allowed

        self._handler_cls = _Handler

    def start(self) -> None:
        self._server = ThreadingHTTPServer(
            (self._bind, self._port), self._handler_cls
        )
        threading.Thread(
            target=self._server.serve_forever,
            name="admin-registry",
            daemon=True,
        ).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def url(self) -> str:
        port = self._server.server_address[1] if self._server else self._port
        return f"http://{self._bind}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Trading Lab admin registry")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--ingest-token-file", required=True)
    parser.add_argument("--admin-token-file", required=True)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8019)
    args = parser.parse_args()

    ingest = Path(args.ingest_token_file).read_text(encoding="utf-8").strip()
    admin = Path(args.admin_token_file).read_text(encoding="utf-8").strip()
    if len(ingest) < 16 or len(admin) < 16:
        raise SystemExit("tokens must be >= 16 chars (use the installer)")

    registry = AdminRegistry(
        ingest_token=ingest,
        admin_token=admin,
        state_dir=Path(args.state_dir),
        bind=args.bind,
        port=args.port,
    )
    registry.start()
    print(
        f"[admin-registry] serving on {registry.url} "
        f"(panel at /, ingest POST /heartbeat) — READ-ONLY monitoring"
    )
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        registry.stop()
        print("[admin-registry] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
