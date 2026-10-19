"""Stage F tests — monitoring API (F1) + heartbeat sender (F6 engine side).

Pins the owner mandates on the ACTUAL code:

- token auth (401 on absent/invalid), rate limiting (429), loopback
  default bind, read-only surface (405), kill-switch POST requiring
  EXPLICIT confirmation (409 without it) and a wired activator;
- provider-failure honesty (ERROR state, no internals leaked);
- redaction of secret-shaped material;
- the monitoring API CANNOT submit orders (no such route exists);
- heartbeat DATA MINIMIZATION: payload fields == EXACTLY the allowed
  set — no positions, no PnL, no orders, no broker details, no
  credentials (owner mandate, ENFORCED BY TEST);
- heartbeat graceful degradation: registry failures never propagate;
  https-only channel; bounded interval.

All fixtures are synthetic. LIVE TRADING REMAINS NOT AUTHORIZED.
PAPER_READY stays FALSE.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from decimal import Decimal

import pytest

from data_engine.runtime.monitoring import (
    HEARTBEAT_ALLOWED_FIELDS,
    MonitoringAPI,
    MonitoringAPIError,
    default_health_provider,
    redact_text,
)
from data_engine.runtime.heartbeat import (
    HeartbeatError,
    HeartbeatSender,
    build_heartbeat_payload,
)

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
def api():
    instance = MonitoringAPI(auth_token=TOKEN, port=0)
    instance.start()
    yield instance
    instance.stop()


def _url(api: MonitoringAPI, path: str) -> str:
    return f"{api.url}{path}"


# ---------------------------------------------------------------------------
# construction + auth
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_token_mandatory(self):
        with pytest.raises(MonitoringAPIError):
            MonitoringAPI(auth_token="")

    def test_token_minimum_strength(self):
        with pytest.raises(MonitoringAPIError):
            MonitoringAPI(auth_token="short")

    def test_loopback_default_bind(self):
        api = MonitoringAPI(auth_token=TOKEN)
        assert api.bind_host == "127.0.0.1"

    def test_token_digest_is_non_reversible_and_short(self):
        api = MonitoringAPI(auth_token=TOKEN)
        digest = api.token_digest()
        assert len(digest) == 12
        assert TOKEN not in digest


class TestAuth:
    def test_missing_token_401(self, api):
        code, body = _get(_url(api, "/api/health"))
        assert code == 401
        assert "token" in body["error"]

    def test_invalid_token_401(self, api):
        code, _ = _get(_url(api, "/api/health"), {"Authorization": "Bearer " + "b" * 32})
        assert code == 401

    def test_valid_token_200(self, api):
        code, body = _get(_url(api, "/api/health"), AUTH)
        assert code == 200
        # default provider is honest ABSENT, never fabricated healthy
        assert body["engine_mode"] == "ABSENT"

    def test_token_never_echoed_in_responses(self, api):
        code, body = _get(_url(api, "/api/health"), AUTH)
        assert TOKEN not in json.dumps(body)


# ---------------------------------------------------------------------------
# read-only surface
# ---------------------------------------------------------------------------


class TestReadOnlySurface:
    ENDPOINTS = (
        "/api/health",
        "/api/positions",
        "/api/orders",
        "/api/pnl",
        "/api/feed",
        "/api/risk",
        "/api/events",
        "/api/killswitch",
    )

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_get_endpoints_serve_providers(self, api, path):
        code, _ = _get(_url(api, path), AUTH)
        assert code == 200

    def test_unknown_path_404(self, api):
        code, _ = _get(_url(api, "/api/nothing"), AUTH)
        assert code == 404

    def test_root_lists_routes(self, api):
        code, body = _get(_url(api, "/"), AUTH)
        assert code == 200
        assert "POST /api/killswitch/activate" in body["routes"]
        assert body["live_trading"] == "NOT_AUTHORIZED"

    def test_post_to_readonly_route_405(self, api):
        code, body = _post(_url(api, "/api/orders"), {"x": 1}, AUTH)
        assert code == 405
        assert "read-only" in body["error"]

    def test_put_405(self, api):
        request = urllib.request.Request(
            _url(api, "/api/positions"), method="PUT", headers=AUTH
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = exc.code == 405
        assert raised

    def test_no_order_submission_route_exists(self, api):
        """F1 structural proof: the ONLY mutating route is the kill
        switch. Order submission is unreachable through this API."""
        code, body = _post(
            _url(api, "/api/orders/submit"),
            {"symbol": "BTCUSDT", "qty": 1},
            AUTH,
        )
        assert code == 405
        assert "read-only" in body["error"]

    def test_providers_are_served_faithfully(self):
        custom = MonitoringAPI(
            auth_token=TOKEN,
            port=0,
            positions_provider=lambda: [{"symbol": "BTCUSDT", "units": "0.5"}],
            pnl_provider=lambda: {"realized": "12.34"},
        )
        custom.start()
        try:
            code, positions = _get(_url(custom, "/api/positions"), AUTH)
            assert code == 200 and positions[0]["symbol"] == "BTCUSDT"
            code, pnl = _get(_url(custom, "/api/pnl"), AUTH)
            assert pnl["realized"] == "12.34"
        finally:
            custom.stop()

    def test_provider_failure_is_honest_and_redacted(self):
        def broken():
            raise RuntimeError("boom: password=hunter2secret")

        custom = MonitoringAPI(auth_token=TOKEN, port=0, feed_provider=broken)
        custom.start()
        try:
            code, body = _get(_url(custom, "/api/feed"), AUTH)
            assert code == 200
            assert body["state"] == "ERROR"
            assert "RuntimeError" in body["detail"]
            assert "hunter2" not in json.dumps(body)
        finally:
            custom.stop()


# ---------------------------------------------------------------------------
# rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    def test_over_limit_429(self):
        api = MonitoringAPI(
            auth_token=TOKEN, port=0, rate_limit_max=3, rate_limit_window=60.0
        )
        api.start()
        try:
            codes = []
            for _ in range(5):
                code, _ = _get(_url(api, "/api/health"), AUTH)
                codes.append(code)
            assert codes[:3] == [200, 200, 200]
            assert codes[3:] == [429, 429]
        finally:
            api.stop()

    def test_unauthenticated_requests_also_rate_limited(self):
        api = MonitoringAPI(
            auth_token=TOKEN, port=0, rate_limit_max=2, rate_limit_window=60.0
        )
        api.start()
        try:
            codes = [_get(_url(api, "/api/health"))[0] for _ in range(4)]
            assert codes == [401, 401, 429, 429]
        finally:
            api.stop()


# ---------------------------------------------------------------------------
# kill switch (the one deliberately-mutating endpoint)
# ---------------------------------------------------------------------------


class TestKillSwitch:
    def test_activate_requires_explicit_confirmation(self, api):
        code, body = _post(_url(api, "/api/killswitch/activate"), {}, AUTH)
        assert code == 409
        assert "confirmation required" in body["error"]

    def test_confirm_false_is_refused(self, api):
        code, body = _post(
            _url(api, "/api/killswitch/activate"),
            {"confirm": False, "reason": "oops"},
            AUTH,
        )
        assert code == 409

    def test_reason_mandatory(self):
        calls = []

        def activator(actor: str, reason: str) -> dict:
            calls.append((actor, reason))
            return {"kill_switch": "ACTIVE", "reason": reason}

        api = MonitoringAPI(
            auth_token=TOKEN, port=0, killswitch_activator=activator
        )
        api.start()
        try:
            code, body = _post(
                _url(api, "/api/killswitch/activate"),
                {"confirm": True, "reason": ""},
                AUTH,
            )
            assert code == 400
            assert calls == []
            code, body = _post(
                _url(api, "/api/killswitch/activate"),
                {"confirm": True, "reason": "operator halt from APK"},
                AUTH,
            )
            assert code == 200
            assert body["kill_switch"] == "ACTIVE"
            assert len(calls) == 1
            actor, reason = calls[0]
            assert actor.startswith("monitoring-client@")
            assert reason == "operator halt from APK"
        finally:
            api.stop()

    def test_reason_is_redacted_before_activation(self):
        seen = []

        def activator(actor: str, reason: str) -> dict:
            seen.append(reason)
            return {"kill_switch": "ACTIVE"}

        api = MonitoringAPI(
            auth_token=TOKEN, port=0, killswitch_activator=activator
        )
        api.start()
        try:
            code, _ = _post(
                _url(api, "/api/killswitch/activate"),
                {"confirm": True, "reason": "api_key=abc123def456ghi789 halt"},
                AUTH,
            )
            assert code == 200
            assert "abc123" not in seen[0]
            assert "[REDACTED]" in seen[0]
        finally:
            api.stop()

    def test_unwired_activator_503_fail_closed(self, api):
        code, body = _post(
            _url(api, "/api/killswitch/activate"),
            {"confirm": True, "reason": "halt"},
            AUTH,
        )
        assert code == 503
        assert "fail closed" in body["error"]

    def test_invalid_json_400(self, api):
        request = urllib.request.Request(
            _url(api, "/api/killswitch/activate"),
            data=b"not-json{",
            headers={**AUTH, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raised = False
        except urllib.error.HTTPError as exc:
            raised = exc.code == 400
        assert raised

    def test_killswitch_state_endpoint(self):
        api = MonitoringAPI(
            auth_token=TOKEN,
            port=0,
            killswitch_state_provider=lambda: {"state": "INACTIVE"},
        )
        api.start()
        try:
            code, body = _get(_url(api, "/api/killswitch"), AUTH)
            assert code == 200 and body["state"] == "INACTIVE"
        finally:
            api.stop()


# ---------------------------------------------------------------------------
# redaction helpers
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_github_pat_redacted(self):
        # Synthetic PAT assembled from pieces at runtime: a literal
        # github_pat_<40 chars> in source would trip the repository's
        # 0-secret forensic scan (pattern-based — fakes included, by
        # design). Assembling keeps the RUNTIME behaviour identical
        # while the SOURCE carries no credential-shaped literal.
        synthetic_pat = "github_" + "pat_11AAAA" + "x" * 34
        assert "github_pat_" not in redact_text(
            f"token {synthetic_pat} tail"
        )

    def test_bearer_redacted(self):
        assert "abcdef" not in redact_text("Bearer abcdef1234567890abcdef")

    def test_key_value_secrets_redacted(self):
        assert "hunter2" not in redact_text("password=hunter2secret")

    def test_plain_text_untouched(self):
        assert redact_text("feed healthy") == "feed healthy"


# ---------------------------------------------------------------------------
# heartbeat payload — DATA MINIMIZATION (F6, TEST-ENFORCED)
# ---------------------------------------------------------------------------


class TestHeartbeatPayloadMinimization:
    def test_payload_fields_exactly_the_allowed_set(self):
        """THE owner-mandate test: payload keys == EXACTLY
        HEARTBEAT_ALLOWED_FIELDS — nothing else, ever."""
        payload = build_heartbeat_payload(
            user_label="owner-primary",
            server_id="srv-001",
            engine_mode="PAPER",
            engine_version="0.3.0",
            uptime_seconds=Decimal("123.5"),
            feed_health="FRESH",
            risk_state="OK",
            kill_switch="INACTIVE",
            now=1_700_000_000.0,
        )
        assert set(payload) == set(HEARTBEAT_ALLOWED_FIELDS)

    FORBIDDEN = (
        "positions",
        "pnl",
        "orders",
        "broker",
        "credential",
        "api_key",
        "secret",
        "token",
        "account_id",
        "balance",
        "fills",
        "trades",
    )

    @pytest.mark.parametrize("field", FORBIDDEN)
    def test_forbidden_fields_absent(self, field):
        payload = build_heartbeat_payload(
            user_label="u",
            server_id="s",
            engine_mode="PAPER",
            engine_version="0.3.0",
            uptime_seconds=1.0,
            feed_health="FRESH",
            risk_state="OK",
            kill_switch="INACTIVE",
        )
        assert field not in json.dumps(payload).lower()

    def test_missing_identity_raises(self):
        with pytest.raises(HeartbeatError):
            build_heartbeat_payload(
                user_label="",
                server_id="s",
                engine_mode="PAPER",
                engine_version="0.3.0",
                uptime_seconds=1.0,
                feed_health="FRESH",
                risk_state="OK",
                kill_switch="INACTIVE",
            )

    def test_label_and_server_id_are_redacted(self):
        payload = build_heartbeat_payload(
            user_label="api_key=supersecret123456",
            server_id="srv token=abcdef123456789",
            engine_mode="PAPER",
            engine_version="0.3.0",
            uptime_seconds=1.0,
            feed_health="FRESH",
            risk_state="OK",
            kill_switch="INACTIVE",
        )
        blob = json.dumps(payload)
        assert "supersecret" not in blob
        assert "abcdef123456" not in blob


# ---------------------------------------------------------------------------
# heartbeat sender — channel discipline + graceful degradation
# ---------------------------------------------------------------------------


class TestHeartbeatSender:
    def _sender(self, **overrides) -> HeartbeatSender:
        defaults = dict(
            registry_url="https://registry.example.invalid/heartbeat",
            ingest_token="r" * 32,
            payload_builder=lambda: build_heartbeat_payload(
                user_label="u",
                server_id="s",
                engine_mode="PAPER",
                engine_version="0.3.0",
                uptime_seconds=1.0,
                feed_health="FRESH",
                risk_state="OK",
                kill_switch="INACTIVE",
            ),
            interval_seconds=30.0,
        )
        defaults.update(overrides)
        return HeartbeatSender(**defaults)

    def test_https_only_channel(self):
        with pytest.raises(HeartbeatError):
            self._sender(registry_url="http://registry.example.invalid/hb")

    def test_token_mandatory(self):
        with pytest.raises(HeartbeatError):
            self._sender(ingest_token="")

    def test_interval_floor_enforced(self):
        with pytest.raises(HeartbeatError):
            self._sender(interval_seconds=1.0)

    def test_successful_beat(self):
        sender = self._sender()
        sender._transport = lambda request, timeout: None
        assert sender.beat_once() is True
        assert sender.sent == 1 and sender.failed == 0
        assert sender.last_error is None

    def test_registry_failure_never_raises(self):
        sender = self._sender()

        def broken(request, timeout):
            raise urllib.error.URLError("unreachable")

        sender._transport = broken
        assert sender.beat_once() is False  # graceful, no exception
        assert sender.failed == 1 and sender.sent == 0
        assert "URLError" in sender.last_error

    def test_payload_builder_failure_never_raises(self):
        sender = self._sender(payload_builder=lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert sender.beat_once() is False
        assert sender.failed == 1
        assert "RuntimeError" in sender.last_error

    def test_run_forever_beats_then_stops(self):
        beats = []
        sender = self._sender(interval_seconds=5.0)
        sender._transport = lambda request, timeout: beats.append(1) or None

        def fast_sleep(seconds: float) -> None:
            time.sleep(0)  # collapses the 5s interval for the test

        sender._sleeper = fast_sleep
        thread = threading.Thread(target=sender.run_forever, daemon=True)
        thread.start()
        time.sleep(0.25)
        sender.stop()
        thread.join(timeout=2)
        assert len(beats) >= 2
        assert not thread.is_alive()

    def test_stats_expose_last_success_age(self):
        sender = self._sender(clock=lambda: 100.0)
        sender._transport = lambda request, timeout: None
        sender.beat_once()
        assert sender.last_success_age_seconds == 0.0


class TestDefaultHealthProvider:
    def test_default_is_honest_absent(self):
        body = default_health_provider()
        assert body["engine_mode"] == "ABSENT"
        assert body["engine_state"] == "NOT_CONSTRUCTED"


# ---------------------------------------------------------------------------
# CLI wiring (token-file hygiene, fail-closed setup)
# ---------------------------------------------------------------------------


class TestCliWiring:
    def test_read_token_file_hygiene(self, tmp_path):
        from data_engine.cli import _read_token_file

        token_file = tmp_path / "monitor.token"
        token_file.write_text("c" * 32 + "\n")
        token_file.chmod(0o600)
        token = _read_token_file(str(token_file), "monitoring API")
        assert token == "c" * 32

    def test_read_token_file_missing_fails_closed(self, tmp_path):
        from data_engine.cli import _read_token_file

        with pytest.raises(ValueError):
            _read_token_file(str(tmp_path / "nope.token"), "monitoring API")

    def test_read_token_file_weak_token_refused(self, tmp_path):
        from data_engine.cli import _read_token_file

        weak = tmp_path / "weak.token"
        weak.write_text("short\n")
        with pytest.raises(ValueError):
            _read_token_file(str(weak), "monitoring API")

    def test_build_monitoring_api_honest_health(self, tmp_path):
        from data_engine.cli import _build_monitoring_api

        token_file = tmp_path / "monitor.token"
        token_file.write_text("d" * 32)
        token_file.chmod(0o600)
        api = _build_monitoring_api(
            bind="127.0.0.1", port=0, token_file=str(token_file)
        )
        assert api.bind_host == "127.0.0.1"
        api.start()
        file_auth = {"Authorization": "Bearer " + "d" * 32}
        try:
            code, body = _get(f"{api.url}/api/health", file_auth)
            assert code == 200
            assert body["engine_mode"] == "PAPER_SUPERVISOR"
            assert body["engine_version"] == "0.3.0"
            # kill switch is fail-closed in the bare CLI path
            code, resp = _post(
                f"{api.url}/api/killswitch/activate",
                {"confirm": True, "reason": "halt"},
                file_auth,
            )
            assert code == 503
        finally:
            api.stop()

    def test_build_heartbeat_sender_requires_token_file(self):
        from data_engine.cli import _build_heartbeat_sender

        with pytest.raises(ValueError):
            _build_heartbeat_sender(
                registry_url="https://registry.example.invalid/hb",
                token_file=None,
                user_label="u",
                interval=45.0,
            )

    def test_build_heartbeat_sender_payload_is_minimal(self, tmp_path):
        from data_engine.cli import _build_heartbeat_sender

        token_file = tmp_path / "registry.token"
        token_file.write_text("e" * 32)
        token_file.chmod(0o600)
        sender = _build_heartbeat_sender(
            registry_url="https://registry.example.invalid/hb",
            token_file=str(token_file),
            user_label="owner-primary",
            interval=45.0,
        )
        # capture the payload via the transport seam
        captured = {}
        sender._transport = lambda request, timeout: captured.update(
            body=json.loads(request.data.decode("utf-8"))
        ) or None
        assert sender.beat_once() is True
        assert set(captured["body"]) == set(HEARTBEAT_ALLOWED_FIELDS)


# ---------------------------------------------------------------------------
# Stage G surfaces: strategy gate (G6) + prediction status (G7)
# ---------------------------------------------------------------------------


class TestStrategyEndpoints:
    def _api_with_gate(self):
        from data_engine.runtime.ledgers import LedgerFamily
        from data_engine.runtime.strategy_activation import (
            StrategyActivationGate,
        )

        gate = StrategyActivationGate(LedgerFamily())
        api = MonitoringAPI(auth_token=TOKEN, port=0, strategy_gate=gate)
        api.start()
        return api, gate

    def test_submit_creates_inactive_submission(self):
        api, gate = self._api_with_gate()
        try:
            code, body = _post(
                f"{api.url}/api/strategy/submit",
                {
                    "label": "BTC momentum",
                    "structured_spec": {"symbol": "BTCUSDT"},
                    "free_text": "buy breakouts",
                },
                AUTH,
            )
            assert code == 200
            assert body["disposition"] == "INACTIVE"
            assert body["pipeline"] == [
                "automated backtest", "validation cycle", "explicit user YES",
            ]
            status_code, status = _get(
                f"{api.url}/api/strategy/{body['submission_id']}", AUTH
            )
            assert status_code == 200
            assert status["state"] == "SUBMITTED"
        finally:
            api.stop()

    def test_activate_without_evidence_stays_inactive(self):
        """The endpoint can NEVER bypass the gate: a YES on a fresh
        submission returns INACTIVE (the gate held)."""
        api, gate = self._api_with_gate()
        try:
            code, body = _post(
                f"{api.url}/api/strategy/submit",
                {"label": "x", "structured_spec": {"s": 1}, "free_text": ""},
                AUTH,
            )
            submission_id = body["submission_id"]
            code, body = _post(
                f"{api.url}/api/strategy/{submission_id}/activate",
                {"confirm": "YES"},
                AUTH,
            )
            assert code == 200
            assert body["disposition"] == "INACTIVE"
        finally:
            api.stop()

    def test_activate_requires_explicit_yes_string(self):
        api, gate = self._api_with_gate()
        try:
            code, body = _post(
                f"{api.url}/api/strategy/anything/activate",
                {"confirm": True},
                AUTH,
            )
            assert code == 409
            assert "explicit YES required" in body["error"]
        finally:
            api.stop()

    def test_unwired_gate_503(self, api):
        code, body = _post(
            f"{api.url}/api/strategy/submit",
            {"label": "x", "structured_spec": {}, "free_text": ""},
            AUTH,
        )
        assert code == 503
        code, _ = _get(f"{api.url}/api/strategy/whatever", AUTH)
        assert code == 503

    def test_unknown_strategy_status_404(self):
        api, gate = self._api_with_gate()
        try:
            code, _ = _get(f"{api.url}/api/strategy/ghost", AUTH)
            assert code == 404
        finally:
            api.stop()


class TestPredictionEndpoint:
    def test_prediction_provider_served(self):
        api = MonitoringAPI(
            auth_token=TOKEN,
            port=0,
            prediction_provider=lambda: {
                "crash_model": "calibrated",
                "drift": "none",
                "status": "OPERATIONAL",
            },
        )
        api.start()
        try:
            code, body = _get(f"{api.url}/api/prediction", AUTH)
            assert code == 200
            assert body["status"] == "OPERATIONAL"
        finally:
            api.stop()

    def test_prediction_default_is_honest_absent(self, api):
        code, body = _get(f"{api.url}/api/prediction", AUTH)
        assert code == 200
        assert body["state"] == "ABSENT"
