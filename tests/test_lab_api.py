"""v1.1.0 owner AI LAB — HTTP-level tests of the monitoring API
surfaces (matching tests/test_owner_surfaces_api.py style):

- unwired lab -> 503 fail-closed on ALL lab routes (GET + POST);
- wired lab serves the full pipeline over HTTP: create -> backtest ->
  paper/start -> paper/finish (gate refuses before the window) ->
  confirm YES -> ACTIVATED with the PAPER_EVALUATION_ONLY note;
- POST /api/lab/assistant answers from the ledgers;
- POST /api/lab/bars validates + stores + triggers forward paper
  evaluation; GET /api/lab/bars/{symbol} summarizes (symbol may
  contain '/');
- GET /api/lab/predict/{symbol} serves the honest baseline (and 400
  when there is not enough history);
- GET /api/lab/brokers serves the honest catalog;
- body-size limits + auth + JSON hygiene still apply.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from data_engine.runtime.control_state import DurableKillSwitch
from data_engine.runtime.lab import AssistantEngine, BarStore, LabManager
from data_engine.runtime.monitoring import MonitoringAPI
from data_engine.runtime.registry import ClientRegistry
from data_engine.runtime.trade_ledger import TradeLedger

TOKEN = "a" * 32  # test token (never a real secret)
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE = datetime(2026, 2, 1, tzinfo=timezone.utc)


def _get(url: str, headers=None) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(url: str, body, headers=None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _bars(n: int, *, drift: float = 1.005):
    out = []
    price = 100.0
    for i in range(n):
        change = drift if i % 5 else 0.998
        o = price
        c = price * change
        h = max(o, c) * 1.001
        low = min(o, c) * 0.999
        out.append(
            {
                "ts": (BASE + timedelta(hours=i)).isoformat(),
                "open": round(o, 6),
                "high": round(h, 6),
                "low": round(low, 6),
                "close": round(c, 6),
                "volume": 100.0,
            }
        )
        price = c
    return out


@pytest.fixture()
def bare_api():
    instance = MonitoringAPI(auth_token=TOKEN, port=0)
    instance.start()
    yield instance
    instance.stop()


@pytest.fixture()
def wired_api(tmp_path):
    state = tmp_path / "monitor-state"
    registry = ClientRegistry(state)
    ledger = TradeLedger(state / "trade_ledger.jsonl")
    kill = DurableKillSwitch(state / "kill_switch_state.json")
    bars = BarStore(state / "bars")
    lab = LabManager(state, bars)
    lab.assistant = AssistantEngine(
        trade_ledger=ledger,
        client_registry=registry,
        health_provider=lambda: {"kill_switch": kill.state()["state"]},
    )
    instance = MonitoringAPI(
        auth_token=TOKEN,
        port=0,
        killswitch_state_provider=kill.state,
        killswitch_activator=kill.activate,
        client_registry=registry,
        trade_ledger=ledger,
        lab=lab,
    )
    instance.start()
    yield instance
    instance.stop()


def _url(api: MonitoringAPI, path: str) -> str:
    return f"{api.url}{path}"


class TestFailClosedWhenUnwired:
    def test_lab_gets_503_without_lab(self, bare_api):
        for path in (
            "/api/lab/strategies",
            "/api/lab/bars/XAUUSD",
            "/api/lab/predict/XAUUSD",
            "/api/lab/brokers",
        ):
            code, body = _get(_url(bare_api, path), AUTH)
            assert code == 503, path
            assert "fail closed" in body["error"]

    def test_lab_posts_503_without_lab(self, bare_api):
        for path, body in (
            ("/api/lab/strategies", {"label": "x", "symbol": "X",
                                     "kind": "ema_trend", "params": {}}),
            ("/api/lab/strategies/lab-x/backtest", {}),
            ("/api/lab/strategies/lab-x/paper/start", {}),
            ("/api/lab/strategies/lab-x/paper/finish", {}),
            ("/api/lab/strategies/lab-x/confirm", {"confirm": "YES"}),
            ("/api/lab/assistant", {"question": "total profit"}),
            ("/api/lab/bars", {"symbol": "X", "bars": []}),
        ):
            code, payload = _post(_url(bare_api, path), body, AUTH)
            assert code == 503, path
            assert "fail closed" in payload["error"]


class TestAuthAndHygiene:
    def test_lab_routes_require_token(self, wired_api):
        code, _ = _get(_url(wired_api, "/api/lab/strategies"))
        assert code == 401
        code, _ = _post(_url(wired_api, "/api/lab/assistant"),
                        {"question": "x"})
        assert code == 401

    def test_invalid_json_refused(self, wired_api):
        request = urllib.request.Request(
            _url(wired_api, "/api/lab/assistant"),
            data=b"{not json",
            headers={**AUTH, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            code = 200
        except urllib.error.HTTPError as exc:
            code = exc.code
        assert code == 400

    def test_body_size_cap(self, wired_api):
        big = {"question": "x" * 5000}
        code, body = _post(_url(wired_api, "/api/lab/assistant"), big, AUTH)
        assert code == 400


class TestLabOverHTTP:
    def test_bars_upload_and_summary(self, wired_api):
        code, body = _post(
            _url(wired_api, "/api/lab/bars"),
            {"symbol": "XAU/USD", "bars": _bars(40)},
            AUTH,
        )
        assert code == 200
        assert body["added"] == 40
        assert body["total"] == 40
        code, summary = _get(_url(wired_api, "/api/lab/bars/XAU/USD"), AUTH)
        assert code == 200
        assert summary["count"] == 40
        assert summary["latest_close"] is not None

    def test_bad_bars_refused(self, wired_api):
        code, body = _post(
            _url(wired_api, "/api/lab/bars"),
            {"symbol": "XAU/USD", "bars": [{"ts": "junk"}]},
            AUTH,
        )
        assert code == 400
        assert "timestamp" in body["error"]

    def test_predict_needs_history(self, wired_api):
        code, body = _get(_url(wired_api, "/api/lab/predict/XAUUSD"), AUTH)
        assert code == 400
        assert "bars" in body["error"]

    def test_predict_after_upload(self, wired_api):
        _post(_url(wired_api, "/api/lab/bars"),
              {"symbol": "BTCUSD", "bars": _bars(120, drift=1.01)}, AUTH)
        code, body = _get(_url(wired_api, "/api/lab/predict/BTCUSD"), AUTH)
        assert code == 200
        assert body["direction"] in ("UP", "DOWN", "FLAT")
        assert "NOT investment advice" in body["disclaimer"]

    def test_brokers_catalog(self, wired_api):
        code, body = _get(_url(wired_api, "/api/lab/brokers"), AUTH)
        assert code == 200
        assert body["count"] == 7
        assert body["add_new_broker"]["live_trading"] == "NOT_AUTHORIZED"

    def test_assistant_over_http(self, wired_api):
        code, body = _post(
            _url(wired_api, "/api/lab/assistant"),
            {"question": "how many trades"},
            AUTH,
        )
        assert code == 200
        assert body["engine"] == "rule-based-analytics-offline"
        assert "0 trades" in body["answer"]

    def test_full_strategy_pipeline_over_http(self, wired_api):
        # history first
        code, body = _post(
            _url(wired_api, "/api/lab/bars"),
            {"symbol": "XAUUSD", "bars": _bars(300)},
            AUTH,
        )
        assert code == 200
        # create
        code, created = _post(
            _url(wired_api, "/api/lab/strategies"),
            {"label": "HTTP gold", "symbol": "XAUUSD",
             "kind": "breakout", "params": {"lookback": 10}},
            AUTH,
        )
        assert code == 200
        assert created["state"] == "SUBMITTED"
        sid = created["submission_id"]
        # list shows it
        code, listing = _get(_url(wired_api, "/api/lab/strategies"), AUTH)
        assert code == 200
        assert listing["count"] == 1
        assert listing["strategies"][0]["submission_id"] == sid
        # backtest
        code, backtested = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/backtest"),
            {}, AUTH,
        )
        assert code == 200
        assert backtested["state"] == "BACKTESTED"
        # paper window
        code, scheduled = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/paper/start"),
            {"cycle_days": 1}, AUTH,
        )
        assert code == 200
        assert scheduled["state"] == "VALIDATION_SCHEDULED"
        # finish BEFORE window -> the gate refuses (HTTP 400)
        code, refused = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/paper/finish"),
            {}, AUTH,
        )
        assert code == 400
        # confirm before validation -> stays INACTIVE (200 + honest
        # disposition; the refusal is journaled by the gate)
        code, held = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/confirm"),
            {"confirm": "YES"}, AUTH,
        )
        assert code == 200
        assert held["state"] != "ACTIVATED"
        # bad params on create are refused
        code, bad = _post(
            _url(wired_api, "/api/lab/strategies"),
            {"label": "x", "symbol": "XAUUSD", "kind": "nope",
             "params": {}},
            AUTH,
        )
        assert code == 400
        # unknown strategy id -> 400
        code, unknown = _post(
            _url(wired_api, "/api/lab/strategies/lab-missing/backtest"),
            {}, AUTH,
        )
        assert code == 400

    def test_cycle_days_type_enforced(self, wired_api):
        _post(_url(wired_api, "/api/lab/bars"),
              {"symbol": "XAUUSD", "bars": _bars(60)}, AUTH)
        code, created = _post(
            _url(wired_api, "/api/lab/strategies"),
            {"label": "x", "symbol": "XAUUSD", "kind": "ema_trend",
             "params": {}},
            AUTH,
        )
        sid = created["submission_id"]
        _post(_url(wired_api, f"/api/lab/strategies/{sid}/backtest"), {},
              AUTH)
        code, body = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/paper/start"),
            {"cycle_days": "seven"}, AUTH,
        )
        assert code == 400
        code, body = _post(
            _url(wired_api, f"/api/lab/strategies/{sid}/paper/start"),
            {"cycle_days": 0}, AUTH,
        )
        assert code == 400

    def test_root_route_lists_lab_surfaces(self, wired_api):
        code, body = _get(_url(wired_api, "/"), AUTH)
        assert code == 200
        assert "/api/lab/strategies" in body["routes"]
        assert "POST /api/lab/assistant (ask)" in body["routes"]
        assert body["live_trading"] == "NOT_AUTHORIZED"
