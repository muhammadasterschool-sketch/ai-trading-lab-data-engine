"""v1.5.0 monitoring API tests — 2FA login routes, admin gating,
lab v1.5.0 surfaces (presets / ensemble / crash / auto-scan /
bootstrap / hist import) end-to-end over real HTTP.

Deterministic, offline (bundled datasets; no network). Governance
invariant: nothing here can authorize live trading.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from data_engine.runtime import totp
from data_engine.runtime.accounts import AccountService
from data_engine.runtime.lab import BarStore, LabManager
from data_engine.runtime.monitoring import MonitoringAPI
from data_engine.runtime.registry import ClientRegistry
from data_engine.platform.historical_data import HistoricalDataService

TOKEN = "t" * 32
NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


def _get(url, headers=None):
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _post(url, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _login(service, email, password, code=""):
    return service.login(email, password, code, ip="127.0.0.1", now=NOW)


@pytest.fixture()
def wired(tmp_path):
    store = BarStore(tmp_path / "bars")
    lab = LabManager(tmp_path, store)
    accounts = AccountService(tmp_path)
    accounts.store.create_account(
        "admin@x.io", "Admin", "AdminPass1234", "admin", now=NOW
    )
    accounts.store.create_account(
        "trader@x.io", "Trader", "TraderPass1234", "trader", now=NOW
    )
    hist = HistoricalDataService(cache_dir=tmp_path / "hc")
    registry = ClientRegistry(tmp_path)
    api = MonitoringAPI(
        auth_token=TOKEN,
        port=0,
        accounts=accounts,
        hist_service=hist,
        lab=lab,
        client_registry=registry,
        bootstrap_presets=True,
    )
    api.start()
    yield api
    api.stop()


def _url(api, path):
    return f"{api.url}{path}"


class TestAuthRoutes:
    def test_login_requires_accounts_wiring(self):
        api = MonitoringAPI(auth_token=TOKEN, port=0)
        api.start()
        try:
            status, payload = _post(
                api.url + "/api/auth/login",
                {"email": "a@b.io", "password": "x", "totp_code": "1"},
            )
            assert status == 503
        finally:
            api.stop()

    def test_full_enrollment_then_session(self, wired):
        accounts = wired._accounts
        # 1) password ok, not enrolled -> 409 with the enrollment secret
        status, payload = _post(
            _url(wired, "/api/auth/login"),
            {"email": "admin@x.io", "password": "AdminPass1234"},
        )
        assert status == 409
        assert payload["error"] == "E_TOTP_ENROLLMENT_REQUIRED"
        secret = payload["totp_secret"]
        assert payload["otpauth_uri"].startswith("otpauth://totp/")
        # 2) valid code -> session (HTTP handler uses the wall clock)
        status, payload = _post(
            _url(wired, "/api/auth/login"),
            {
                "email": "admin@x.io",
                "password": "AdminPass1234",
                "totp_code": totp.totp_at(secret, totp.utc_now()),
            },
        )
        assert status == 200
        assert payload["auth"] == "session"
        token = payload["token"]
        # 3) session authorizes /api/auth/me with the account identity
        status, me = _get(
            _url(wired, "/api/auth/me"),
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 200 and me["role"] == "admin"
        assert me["email"] == "admin@x.io"
        # 4) logout kills the session
        status, _ = _post(
            _url(wired, "/api/auth/logout"), {},
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 200
        status, _ = _get(
            _url(wired, "/api/auth/me"), {"Authorization": f"Bearer {token}"}
        )
        assert status == 401

    def test_bad_credentials_401(self, wired):
        status, payload = _post(
            _url(wired, "/api/auth/login"),
            {"email": "admin@x.io", "password": "wrong", "totp_code": "1"},
        )
        assert status == 401
        assert payload["error"] == "E_BAD_CREDENTIALS"

    def test_session_token_authorizes_general_routes(self, wired):
        accounts = wired._accounts
        result = _login(accounts, "trader@x.io", "TraderPass1234")
        secret = result["totp_secret"]
        result = _login(
            accounts, "trader@x.io", "TraderPass1234",
            totp.totp_at(secret, NOW),
        )
        token = result["token"]
        status, _ = _get(
            _url(wired, "/api/health"), {"Authorization": f"Bearer {token}"}
        )
        assert status == 200


class TestAdminGating:
    def _session(self, wired, email, password):
        accounts = wired._accounts
        first = _login(accounts, email, password)
        return _login(
            accounts, email, password, totp.totp_at(first["totp_secret"], NOW)
        )["token"]

    def test_trader_denied_admin_surfaces(self, wired):
        token = self._session(wired, "trader@x.io", "TraderPass1234")
        for path in ("/api/users", "/api/registrations", "/api/admin/accounts"):
            status, payload = _get(
                _url(wired, path), {"Authorization": f"Bearer {token}"}
            )
            assert status == 403, path
        status, _ = _post(
            _url(wired, "/api/admin/accounts"),
            {"email": "n@x.io", "name": "N", "password": "Password12345",
             "role": "trader"},
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 403

    def test_admin_session_allowed(self, wired):
        token = self._session(wired, "admin@x.io", "AdminPass1234")
        status, payload = _get(
            _url(wired, "/api/admin/accounts"),
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 200 and payload["count"] == 2

    def test_pairing_owner_still_admin(self, wired):
        status, _ = _get(
            _url(wired, "/api/users"), {"Authorization": f"Bearer {TOKEN}"}
        )
        assert status == 200

    def test_admin_creates_user_via_http(self, wired):
        token = self._session(wired, "admin@x.io", "AdminPass1234")
        status, payload = _post(
            _url(wired, "/api/admin/accounts"),
            {
                "email": "new@x.io", "name": "New",
                "password": "Password12345", "role": "trader",
            },
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 200
        # the new user can enroll + login
        first = _login(wired._accounts, "new@x.io", "Password12345")
        result = _login(
            wired._accounts, "new@x.io", "Password12345",
            totp.totp_at(first["totp_secret"], NOW),
        )
        assert result["outcome"] == "SESSION"

    def test_admin_resets_2fa_via_http(self, wired):
        token = self._session(wired, "admin@x.io", "AdminPass1234")
        status, payload = _post(
            _url(wired, "/api/admin/accounts/reset-2fa"),
            {"email": "trader@x.io"},
            {"Authorization": f"Bearer {token}"},
        )
        assert status == 200
        assert payload["totp_enrolled"] is False


class TestLabV150Routes:
    def test_presets_route(self, wired):
        status, payload = _get(
            _url(wired, "/api/lab/presets"), {"Authorization": f"Bearer {TOKEN}"}
        )
        assert status == 200
        assert payload["count"] == 5
        labels = {p["kind"] for p in payload["presets"]}
        assert "ema_scalp" in labels and "orb_breakout" in labels

    def test_crash_and_ensemble_need_bars(self, wired):
        for path in ("/api/lab/crash/BTCUSDT",
                     "/api/lab/predict-ensemble/BTCUSDT"):
            status, payload = _get(
                _url(wired, path), {"Authorization": f"Bearer {TOKEN}"}
            )
            assert status == 400, path  # no bars yet -> honest refusal

    def test_hist_datasets_route(self, wired):
        status, payload = _get(
            _url(wired, "/api/hist/datasets"),
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert payload["count"] == 2
        assert "RESEARCH_BACKTEST_ONLY" in payload["note"]

    def test_hist_import_then_bootstrap_and_predict(self, wired):
        # import verified real bars
        status, payload = _post(
            _url(wired, "/api/hist/import"),
            {"symbol": "BTCUSDT", "timeframe": "1m"},
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert payload["imported"] == 43200
        assert payload["source_used"] == "bundled-repo"
        assert payload["provenance"]["checksum_verified"] is True
        # bootstrap the presets explicitly
        status, payload = _post(
            _url(wired, "/api/lab/bootstrap"),
            {"symbol": "BTCUSDT"},
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert len(payload["created"]) == 5
        assert len(payload["paper_started"]) == 5
        # predict + crash now work on real bars
        status, crash = _get(
            _url(wired, "/api/lab/crash/BTCUSDT"),
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert 0 <= crash["crash_probability"] <= 1
        assert crash["risk_level"] in ("LOW", "MODERATE", "ELEVATED", "SEVERE")
        status, ensemble = _get(
            _url(wired, "/api/lab/predict-ensemble/BTCUSDT"),
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert 0 <= ensemble["probability_up"] <= 1
        # auto-scan runs end-to-end on real bars
        status, scan = _post(
            _url(wired, "/api/lab/auto-scan"),
            {"symbol": "BTCUSDT", "top_n": 2},
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert scan["combinations_tested"] == 27

    def test_bar_upload_triggers_auto_bootstrap_when_enabled(self, wired):
        status, payload = _post(
            _url(wired, "/api/lab/bars"),
            {"symbol": "ETHUSDT", "bars": _synthetic_bars(60)},
            {"Authorization": f"Bearer {TOKEN}"},
        )
        assert status == 200
        assert "bootstrap" in payload
        assert len(payload["bootstrap"]["created"]) == 5


def _synthetic_bars(n=60):
    from datetime import timedelta

    bars = []
    t0 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    price = 100.0
    for i in range(n):
        price *= 1.001
        bars.append(
            {
                "ts": (t0 + timedelta(minutes=i)).isoformat(),
                "open": price,
                "high": price * 1.001,
                "low": price * 0.999,
                "close": price,
                "volume": 10.0,
            }
        )
    return bars
