"""Stage F tests — ADMIN REGISTRY + PANEL (Part 9 F6).

Loads deploy/admin/admin_registry.py as a standalone module (it is a
deployable, NOT part of the data_engine package — no new engine
dependency) and pins the owner mandates:

- SERVER-SIDE data minimization: heartbeats with positions/PnL/
  orders/broker/credential fields are REJECTED (400) and NEVER
  stored;
- token auth for ingest (401) and panel APIs (401);
- the panel is READ-ONLY: no PUT/PATCH/DELETE, no command channel —
  the registry structurally CANNOT control user servers;
- ONLINE/OFFLINE detection from missed heartbeats;
- roster CSV export;
- atomic JSON persistence (state survives restart).

LIVE TRADING REMAINS NOT AUTHORIZED.
"""

import importlib.util
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "deploy" / "admin" / "admin_registry.py"


def _load_registry_module():
    spec = importlib.util.spec_from_file_location(
        "admin_registry_under_test", REGISTRY_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REG = _load_registry_module()

INGEST = "i" * 32
ADMIN = "m" * 32


def _post(url, body, token):
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _get(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _valid_payload(label="user-1", **overrides):
    payload = {
        "schema": REG.HEARTBEAT_SCHEMA if hasattr(REG, "HEARTBEAT_SCHEMA")
        else "ai-trading-lab/heartbeat/1",
        "user_label": label,
        "server_id": f"srv-{label}",
        "engine_mode": "PAPER_SUPERVISOR",
        "engine_version": "0.3.0",
        "uptime_seconds": 10.0,
        "feed_health": "FRESH",
        "risk_state": "OK",
        "kill_switch": "INACTIVE",
        "prediction_status": "OPERATIONAL",
        "timestamp": time.time(),
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def registry(tmp_path):
    instance = REG.AdminRegistry(
        ingest_token=INGEST,
        admin_token=ADMIN,
        state_dir=tmp_path,
        port=0,
    )
    instance.start()
    yield instance
    instance.stop()


class TestDataMinimizationServerSide:
    """THE F6 mandate: payload contains ONLY documented fields."""

    @pytest.mark.parametrize(
        "field,value",
        [
            ("positions", [{"symbol": "BTCUSDT", "units": 1}]),
            ("pnl", {"realized": "12.34"}),
            ("orders", [{"id": "o-1"}]),
            ("broker", "binance"),
            ("credential", "abc"),
            ("api_key", "xyz"),
            ("balance", {"USD": "100"}),
        ],
    )
    def test_forbidden_fields_rejected_400(self, registry, field, value):
        code, body = _post(
            f"{registry.url}/heartbeat",
            _valid_payload(**{field: value}),
            INGEST,
        )
        assert code == 400
        assert "data minimization" in body["error"]

    def test_valid_payload_accepted(self, registry):
        code, body = _post(
            f"{registry.url}/heartbeat", _valid_payload(), INGEST
        )
        assert code == 200
        assert body["status"] == "recorded"

    def test_missing_identity_rejected(self, registry):
        payload = _valid_payload()
        del payload["user_label"]
        code, body = _post(f"{registry.url}/heartbeat", payload, INGEST)
        assert code == 400
        assert "user_label" in body["error"]

    def test_stored_state_contains_only_allowed_data(self, registry, tmp_path):
        _post(f"{registry.url}/heartbeat", _valid_payload(), INGEST)
        stored = json.loads((tmp_path / "registry.json").read_text())
        assert len(stored) == 1
        entry = list(stored.values())[0]
        forbidden = ("position", "pnl", "order", "broker", "credential",
                     "secret", "token", "balance")
        blob = json.dumps(entry).lower()
        for word in forbidden:
            assert word not in blob, f"stored heartbeat leaks {word!r}"

    def test_validate_heartbeat_unit(self):
        with pytest.raises(ValueError):
            REG.validate_heartbeat({"user_label": "u", "positions": []})
        with pytest.raises(ValueError):
            REG.validate_heartbeat({"user_label": "u"})


class TestRegistryAuth:
    def test_ingest_requires_token(self, registry):
        request = urllib.request.Request(
            f"{registry.url}/heartbeat",
            data=json.dumps(_valid_payload()).encode(),
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = exc.code == 401
        assert raised

    def test_wrong_ingest_token_401(self, registry):
        code, _ = _post(
            f"{registry.url}/heartbeat", _valid_payload(), "x" * 32
        )
        assert code == 401

    def test_roster_requires_admin_token(self, registry):
        code, _ = _get(f"{registry.url}/api/roster")
        assert code == 401
        code, _ = _get(f"{registry.url}/api/roster", "wrong" * 8)
        assert code == 401

    def test_panel_html_is_public_login_page(self, registry):
        code, body = _get(f"{registry.url}/")
        assert code == 200
        text = body.decode("utf-8")
        assert "Admin token" in text
        assert "READ-ONLY" in text


class TestRegistryReadOnly:
    def test_no_mutating_methods(self, registry):
        for method in ("PUT", "PATCH", "DELETE"):
            request = urllib.request.Request(
                f"{registry.url}/api/roster", method=method,
                headers={"Authorization": f"Bearer {ADMIN}"},
            )
            try:
                urllib.request.urlopen(request, timeout=5)
                raised = False
            except urllib.error.HTTPError as exc:
                raised = exc.code == 405
            assert raised, method

    def test_only_heartbeat_post_route(self, registry):
        code, body = _post(
            f"{registry.url}/api/command", {"cmd": "halt"}, ADMIN
        )
        assert code == 404
        assert "read-only" in body["error"].lower()

    def test_no_control_channel_exists(self):
        """Structural: the registry module defines no code that opens
        outbound connections to user servers (one-way heartbeats ONLY
        — enforced by source audit)."""
        source = REGISTRY_PATH.read_text(encoding="utf-8")
        assert "urlopen" not in source  # no outbound HTTP at all
        assert "socket.create_connection" not in source


class TestRosterAndOfflineDetection:
    def test_online_then_offline(self, registry, tmp_path):
        _post(f"{registry.url}/heartbeat", _valid_payload("u1"), INGEST)
        code, body = _get(f"{registry.url}/api/roster", ADMIN)
        assert code == 200
        roster = json.loads(body)
        assert roster[0]["user_label"] == "u1"
        assert roster[0]["online"] is True

        # simulate missed heartbeats: backdate the last-seen record
        state_file = tmp_path / "registry.json"
        stored = json.loads(state_file.read_text())
        key = list(stored)[0]
        stored[key]["last_seen_epoch"] = time.time() - 1000
        state_file.write_text(json.dumps(stored))
        # reload into a fresh registry over the same state dir
        second = REG.AdminRegistry(
            ingest_token=INGEST, admin_token=ADMIN,
            state_dir=tmp_path, port=0,
        )
        second.start()
        try:
            code, body = _get(f"{second.url}/api/roster", ADMIN)
            roster = json.loads(body)
            assert roster[0]["online"] is False
            assert "OFFLINE" in roster[0]["active_alerts"][0]
        finally:
            second.stop()

    def test_killswitch_and_risk_alerts_surface(self, registry):
        _post(
            f"{registry.url}/heartbeat",
            _valid_payload(
                "u2", kill_switch="ACTIVE", risk_state="HALTED"
            ),
            INGEST,
        )
        code, body = _get(f"{registry.url}/api/roster", ADMIN)
        roster = json.loads(body)
        alerts = roster[0]["active_alerts"]
        assert "KILL_SWITCH_ACTIVE" in alerts
        assert "RISK_STATE_ALARM" in alerts

    def test_roster_csv_export(self, registry):
        _post(f"{registry.url}/heartbeat", _valid_payload("u3"), INGEST)
        code, body = _get(f"{registry.url}/api/roster.csv", ADMIN)
        assert code == 200
        text = body.decode("utf-8")
        assert text.startswith("user_label,server_id,online")
        assert "u3" in text

    def test_state_survives_registry_restart(self, tmp_path):
        first = REG.AdminRegistry(
            ingest_token=INGEST, admin_token=ADMIN, state_dir=tmp_path, port=0
        )
        first.start()
        _post(f"{first.url}/heartbeat", _valid_payload("persist"), INGEST)
        first.stop()
        second = REG.AdminRegistry(
            ingest_token=INGEST, admin_token=ADMIN, state_dir=tmp_path, port=0
        )
        second.start()
        try:
            code, body = _get(f"{second.url}/api/roster", ADMIN)
            roster = json.loads(body)
            assert roster[0]["user_label"] == "persist"
        finally:
            second.stop()
