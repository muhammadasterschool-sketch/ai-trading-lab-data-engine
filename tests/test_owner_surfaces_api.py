"""v1.0.0 owner-mandate tests — the OWNER SURFACES of the monitoring
API (who is connected, who ever registered, trade ledger + stats)
and the REAL durable kill-switch activator.

Pins (HTTP-level, matching tests/test_monitoring_api.py style):

- unwired registry/ledger -> 503 fail-closed on all four new routes
  (same posture as the pairing service);
- wired routes serve their payloads with honest shapes;
- self-reported X-Client-* identity headers on an AUTHENTICATED
  request are OBSERVED: /api/users then shows the client with an
  online verdict, /api/registrations shows the first contact;
- unauthenticated requests are NEVER observed (401 first);
- the durable activator makes POST /api/killswitch/activate REALLY
  persist the STOP flag (survives a full API restart) and the
  killswitch state provider reflects it;
- the monitoring API still has NO reset route (resume stays
  PC-gated; POST to any reset-shaped path is refused).
"""

import json
import urllib.error
import urllib.request

import pytest

from data_engine.runtime.control_state import DurableKillSwitch
from data_engine.runtime.monitoring import MonitoringAPI
from data_engine.runtime.registry import ClientRegistry
from data_engine.runtime.trade_ledger import TradeLedger

TOKEN = "a" * 32  # test token (never a real secret)
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def _get(url: str, headers=None) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(url: str, body: dict, headers=None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.fixture()
def bare_api():
    instance = MonitoringAPI(auth_token=TOKEN, port=0)
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture()
def wired_api(tmp_path):
    registry = ClientRegistry(tmp_path / "state")
    ledger = TradeLedger(tmp_path / "state" / "trade_ledger.jsonl")
    kill = DurableKillSwitch(tmp_path / "state" / "kill_switch_state.json")
    instance = MonitoringAPI(
        auth_token=TOKEN,
        port=0,
        killswitch_state_provider=kill.state,
        killswitch_activator=kill.activate,
        client_registry=registry,
        trade_ledger=ledger,
    )
    instance.start()
    yield instance
    instance.stop()


def _url(api: MonitoringAPI, path: str) -> str:
    return f"{api.url}{path}"


class TestFailClosedWhenUnwired:
    def test_users_503_without_registry(self, bare_api):
        code, body = _get(_url(bare_api, "/api/users"), AUTH)
        assert code == 503
        assert "not wired" in body["error"]

    def test_registrations_503_without_registry(self, bare_api):
        code, body = _get(_url(bare_api, "/api/registrations"), AUTH)
        assert code == 503
        assert "not wired" in body["error"]

    def test_ledger_trades_503_without_ledger(self, bare_api):
        code, body = _get(_url(bare_api, "/api/ledger/trades"), AUTH)
        assert code == 503
        assert "not wired" in body["error"]

    def test_ledger_stats_503_without_ledger(self, bare_api):
        code, body = _get(_url(bare_api, "/api/ledger/stats"), AUTH)
        assert code == 503
        assert "not wired" in body["error"]

    def test_new_routes_require_auth(self, bare_api):
        for path in (
            "/api/users",
            "/api/registrations",
            "/api/ledger/trades",
            "/api/ledger/stats",
        ):
            code, _ = _get(_url(bare_api, path))
            assert code == 401, path


class TestWiredOwnerSurfaces:
    def test_identity_headers_are_observed(self, wired_api):
        headers = {
            **AUTH,
            "X-Client-Name": "owner-phone",
            "X-Client-Email": "owner@gmail.com",
            "X-Client-Kind": "monitor",
            "X-Client-Device": "Pixel-8",
        }
        code, _ = _get(_url(wired_api, "/api/health"), headers)
        assert code == 200
        code, body = _get(_url(wired_api, "/api/users"), headers)
        assert code == 200
        assert body["count"] == 1
        row = body["clients"][0]
        assert row["name"] == "owner-phone"
        assert row["email"] == "owner@gmail.com"
        assert row["kind"] == "monitor"
        assert row["device"] == "Pixel-8"
        assert row["online"] is True

    def test_registration_ledger_records_first_contact_once(
        self, wired_api
    ):
        headers = {
            **AUTH,
            "X-Client-Name": "admin",
            "X-Client-Email": "admin@lab.test",
            "X-Client-Kind": "admin",
        }
        for _ in range(4):
            _get(_url(wired_api, "/api/health"), headers)
        code, body = _get(_url(wired_api, "/api/registrations"), headers)
        assert code == 200
        assert body["count"] == 1
        row = body["registrations"][0]
        assert row["name"] == "admin"
        assert row["kind"] == "admin"

    def test_unauthenticated_clients_are_not_observed(self, wired_api):
        _get(_url(wired_api, "/api/health"))  # no token -> 401
        # the ONLY row is the anonymous observation of THIS very
        # request (authenticated but identity-less) — a 401 request
        # never created anything
        code, body = _get(_url(wired_api, "/api/users"), AUTH)
        assert code == 200
        assert body["count"] == 1
        row = body["clients"][0]
        assert row["name"] == ""
        assert row["kind"] == "other"
        assert row["requests"] == 1

    def test_trade_ledger_and_stats(self, wired_api):
        registry = wired_api._client_registry
        ledger = wired_api._trade_ledger
        ledger.record(symbol="EURUSD", side="BUY", quantity=0.1,
                      price=1.08, pnl=25.5)
        ledger.record(symbol="EURUSD", side="SELL", quantity=0.1,
                      price=1.09, pnl=-5.0)
        ledger.record(symbol="XAUUSD", side="BUY", quantity=0.01,
                      price=2650.0, pnl=100.0)
        del registry  # silence unused warnings in some lints
        code, body = _get(_url(wired_api, "/api/ledger/trades"), AUTH)
        assert code == 200
        assert body["count"] == 3
        assert body["trades"][0]["symbol"] == "XAUUSD"  # newest first
        code, stats = _get(_url(wired_api, "/api/ledger/stats"), AUTH)
        assert code == 200
        assert stats["total_trades"] == 3
        assert stats["per_symbol"] == {"XAUUSD": 1, "EURUSD": 2}
        assert stats["total_pnl"] == 120.5

    def test_empty_ledger_is_honest(self, wired_api):
        code, stats = _get(_url(wired_api, "/api/ledger/stats"), AUTH)
        assert code == 200
        assert stats["total_trades"] == 0
        assert stats["per_symbol"] == {}


class TestDurableStopControl:
    def test_killswitch_activate_really_persists(self, tmp_path):
        kill = DurableKillSwitch(tmp_path / "state" / "ks.json")
        registry = ClientRegistry(tmp_path / "state")
        instance = MonitoringAPI(
            auth_token=TOKEN,
            port=0,
            killswitch_state_provider=kill.state,
            killswitch_activator=kill.activate,
            client_registry=registry,
        )
        instance.start()
        code, body = _post(
            _url(instance, "/api/killswitch/activate"),
            {"confirm": True, "reason": "owner: stop trading now"},
            AUTH,
        )
        assert code == 200
        assert body["state"] == "ACTIVE"
        code, state = _get(_url(instance, "/api/killswitch"), AUTH)
        assert code == 200
        assert state["state"] == "ACTIVE"
        instance.stop()
        # the WHOLE POINT: the STOP survives a full process restart
        revived = DurableKillSwitch(tmp_path / "state" / "ks.json")
        assert revived.state()["state"] == "ACTIVE"

    def test_no_reset_route_exists(self, wired_api):
        # resume stays PC-gated: no reset-shaped route on the API
        code, body = _post(
            _url(wired_api, "/api/killswitch/reset"),
            {"confirm": True},
            AUTH,
        )
        assert code == 405  # read-only surface refusal, unchanged

    def test_root_route_lists_owner_surfaces(self, wired_api):
        code, body = _get(_url(wired_api, "/"), AUTH)
        assert code == 200
        routes = " ".join(body["routes"])
        for expected in (
            "/api/users",
            "/api/registrations",
            "/api/ledger/trades",
            "/api/ledger/stats",
        ):
            assert expected in routes
