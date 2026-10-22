"""v4.0 tests — invitation pairing service (B1) + POST /api/pair + mDNS.

Pins the owner mandates (PART 3 P3/P4/P5, PART 5 B1-B4, PART 9 Stage F)
on the ACTUAL code:

- pairing fail-closed at every boundary: wrong/missing code, disabled
  config, malformed config (startup refusal), rate limiting;
- salted-hash protocol: constant-time verification, salt uniqueness;
- redaction: email ``***@domain`` in audit lines; the invitation code
  and the returned token are NEVER logged;
- ``POST /api/pair`` reachable BEFORE token auth ONLY when a pairing
  service is wired; absent = 503 E_PAIRING_DISABLED (cloud default);
- every OTHER monitoring route unchanged (token-first, 401, kill-switch
  503 honesty preserved);
- mDNS announcement graceful degradation (never blocks serving);
- the local template carries a VALID salt+hash and the invitation
  plaintext appears NOWHERE in the repo when the owner-side probe env
  is set (CI runs the structural subset — recorded honestly).

All fixtures are synthetic. LIVE TRADING REMAINS NOT AUTHORIZED.
PAPER_READY stays FALSE.
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from data_engine.runtime.announce import (
    DEFAULT_INSTANCE,
    SERVICE_TYPE,
    try_announce_mdns,
)
from data_engine.runtime.monitoring import MonitoringAPI
from data_engine.runtime.pairing import (
    E_PAIRING_CODE_INVALID,
    E_PAIRING_DISABLED,
    E_PAIRING_RATE_LIMITED,
    PAIRING_MODES,
    PairingConfigError,
    PairingRateLimiter,
    PairingService,
    format_pairing_status,
    hash_invitation_code,
    load_pairing_config,
    redact_email,
    verify_invitation_code,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = REPO_ROOT / "deploy" / "windows" / "local-monitor-config.template.json"

TOKEN = "t" * 32  # test token (never a real secret)
CODE = "test-invitation-code-1234"  # synthetic test code (never the owner default)
SALT = "0123456789abcdef0123456789abcdef"


def _config(tmp_path, code=CODE, salt=SALT, enabled=True, cap=5):
    path = tmp_path / "pairing.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "enabled": enabled,
                "salt_hex": salt,
                "code_sha256_hex": hash_invitation_code(salt, code),
                "max_attempts_per_minute": cap,
            }
        ),
        encoding="utf-8",
    )
    return path


def _post(url, body, headers=None):
    data = json.dumps(body).encode("utf-8") if not isinstance(body, (bytes, str)) else (
        body if isinstance(body, bytes) else body.encode("utf-8")
    )
    request = urllib.request.Request(
        url, data=data, headers=headers or {}, method="POST"
    )
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# ---------------------------------------------------------------------------
# config loading (fail-closed)
# ---------------------------------------------------------------------------


class TestPairingConfig:
    def test_valid_config_loads(self, tmp_path):
        cfg = load_pairing_config(_config(tmp_path))
        assert cfg["enabled"] is True
        assert cfg["salt_hex"] == SALT
        assert cfg["max_attempts_per_minute"] == 5

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(PairingConfigError):
            load_pairing_config(tmp_path / "does-not-exist.json")

    def test_malformed_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(PairingConfigError):
            load_pairing_config(path)

    def test_non_object_json_raises(self, tmp_path):
        path = tmp_path / "arr.json"
        path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(PairingConfigError):
            load_pairing_config(path)

    def test_wrong_version_refused(self, tmp_path):
        path = tmp_path / "pairing.json"
        payload = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
        payload["version"] = 2
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PairingConfigError):
            load_pairing_config(path)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("enabled", "yes"),
            ("salt_hex", "tooshort"),
            ("salt_hex", "ZZZZ456789abcdef0123456789abcdef"),
            ("code_sha256_hex", "abc"),
            ("code_sha256_hex", 12345),
            ("max_attempts_per_minute", 0),
            ("max_attempts_per_minute", "five"),
            ("max_attempts_per_minute", True),
        ],
    )
    def test_malformed_fields_refused(self, tmp_path, field, value):
        path = tmp_path / "pairing.json"
        payload = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
        payload[field] = value
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(PairingConfigError):
            load_pairing_config(path)

    def test_unknown_keys_ignored(self, tmp_path):
        path = tmp_path / "pairing.json"
        payload = json.loads(_config(tmp_path).read_text(encoding="utf-8"))
        payload["future_field"] = {"anything": True}
        path.write_text(json.dumps(payload), encoding="utf-8")
        cfg = load_pairing_config(path)
        assert cfg["enabled"] is True

    def test_committed_template_is_valid(self):
        cfg = load_pairing_config(TEMPLATE_PATH)
        assert cfg["enabled"] is True
        assert cfg["max_attempts_per_minute"] == 5
        assert cfg["salt_hex"] == "60b67c81d07813d2b9a9f2d99b629a0b"


# ---------------------------------------------------------------------------
# hash protocol (constant-time, salt uniqueness)
# ---------------------------------------------------------------------------


class TestHashProtocol:
    def test_correct_code_verifies(self, tmp_path):
        cfg = load_pairing_config(_config(tmp_path))
        assert verify_invitation_code(cfg, CODE) is True

    def test_wrong_code_refused(self, tmp_path):
        cfg = load_pairing_config(_config(tmp_path))
        assert verify_invitation_code(cfg, "wrong-code") is False

    @pytest.mark.parametrize("bad", ["", None, 123, [], {}, "   "])
    def test_malformed_supplied_refused(self, tmp_path, bad):
        cfg = load_pairing_config(_config(tmp_path))
        assert verify_invitation_code(cfg, bad) is False

    def test_salt_uniqueness_same_code_different_hashes(self):
        hash_a = hash_invitation_code("a" * 32, CODE)
        hash_b = hash_invitation_code("b" * 32, CODE)
        assert hash_a != hash_b
        assert hash_invitation_code("a" * 32, CODE) == hash_a  # deterministic

    def test_committed_template_hash_matches_owner_default_when_probe_set(self):
        """Strong owner-side pin: with AITL_INVITE_PROBE set to the real
        default code, the committed template hash must verify. CI runs
        WITHOUT the probe (structural checks only) — honest skip."""
        probe = os.environ.get("AITL_INVITE_PROBE")
        if not probe:
            pytest.skip("AITL_INVITE_PROBE not set (structural CI run)")
        cfg = load_pairing_config(TEMPLATE_PATH)
        assert verify_invitation_code(cfg, probe) is True

    def test_no_plaintext_probe_in_repo_when_probe_set(self):
        """Owner-side pin: the invitation plaintext appears in NO tracked
        file (repo-wide, incl. mobile/) when AITL_INVITE_PROBE is set."""
        probe = os.environ.get("AITL_INVITE_PROBE")
        if not probe:
            pytest.skip("AITL_INVITE_PROBE not set (structural CI run)")
        offenders = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith((".git/", ".venv/", "build/")) or rel.startswith(
                "artifacts/v4/00-"
            ) and "PLAN" in rel:
                continue
            if path.suffix.lower() in {".pyc", ".zip", ".whl"}:
                continue
            try:
                if probe in path.read_text(encoding="utf-8", errors="ignore"):
                    offenders.append(rel)
            except OSError:
                continue
        assert offenders == []


# ---------------------------------------------------------------------------
# redaction (P7)
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_email_redacted_to_domain_form(self):
        assert redact_email("alice@example.com") == "***@example.com"

    def test_missing_or_malformed_email_redacts_fully(self):
        assert redact_email("") == "***"
        assert redact_email(None) == "***"
        assert redact_email("not-an-email") == "***"
        assert redact_email("alice@") == "***"


# ---------------------------------------------------------------------------
# rate limiter (per-IP, fixed window)
# ---------------------------------------------------------------------------


class TestPairingRateLimiter:
    def test_allows_cap_then_blocks(self):
        limiter = PairingRateLimiter(5, window_seconds=60.0)
        now = 1000.0
        for i in range(5):
            assert limiter.allow("1.2.3.4", now + i * 0.1) is True
        assert limiter.allow("1.2.3.4", now + 4.9) is False

    def test_window_reset(self):
        limiter = PairingRateLimiter(5, window_seconds=60.0)
        now = 1000.0
        for i in range(5):
            assert limiter.allow("1.2.3.4", now + i * 0.1) is True
        assert limiter.allow("1.2.3.4", now + 5) is False
        assert limiter.allow("1.2.3.4", now + 60.5) is True

    def test_independent_ips(self):
        limiter = PairingRateLimiter(5, window_seconds=60.0)
        now = 1000.0
        for i in range(5):
            assert limiter.allow("1.1.1.1", now + i * 0.1) is True
        assert limiter.allow("2.2.2.2", now) is True

    def test_retry_after_positive(self):
        limiter = PairingRateLimiter(5, window_seconds=60.0)
        now = 1000.0
        for i in range(6):
            limiter.allow("1.2.3.4", now + i * 0.1)
        assert limiter.retry_after_seconds("1.2.3.4", now + 1.0) >= 1

    def test_invalid_cap_refused(self):
        with pytest.raises(PairingConfigError):
            PairingRateLimiter(0)


# ---------------------------------------------------------------------------
# PairingService.attempt (unit level, injected audit sink)
# ---------------------------------------------------------------------------


def _service(config_path, cap=5, sink=None, fixed_now=None):
    cfg = load_pairing_config(config_path)
    limiter = PairingRateLimiter(cap, window_seconds=60.0)
    if fixed_now is None:
        return PairingService(cfg, rate_limiter=limiter, audit_sink=sink or (lambda line: None)), None
    clock = [fixed_now]

    def tick():
        return clock[0]

    return PairingService(cfg, rate_limiter=limiter, audit_sink=sink or (lambda line: None), clock=tick), clock


class TestPairingServiceAttempt:
    def _body(self, **overrides):
        body = {
            "name": "alice-laptop",
            "email": "alice@example.com",
            "invitation_code": CODE,
            "mode": "local",
        }
        body.update(overrides)
        return body

    def test_happy_path_returns_token_and_health(self, tmp_path):
        service, _ = _service(_config(tmp_path))
        status, payload = service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(),
            token=TOKEN,
            health_provider=lambda: {"engine_state": "RUNNING"},
        )
        assert status == 200
        assert payload["status"] == "paired"
        assert payload["token"] == TOKEN
        assert payload["health"] == {"engine_state": "RUNNING"}
        assert payload["pairing"] == {
            "email_redacted": "***@example.com",
            "mode": "local",
        }

    def test_disabled_config_503(self, tmp_path):
        service, _ = _service(_config(tmp_path, enabled=False))
        status, payload = service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(),
            token=TOKEN,
            health_provider=lambda: {},
        )
        assert status == 503
        assert payload == {"error": E_PAIRING_DISABLED}

    def test_wrong_code_403_no_token(self, tmp_path):
        service, _ = _service(_config(tmp_path))
        status, payload = service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(invitation_code="nope"),
            token=TOKEN,
            health_provider=lambda: {},
        )
        assert status == 403
        assert payload == {"error": E_PAIRING_CODE_INVALID}
        assert "token" not in payload

    @pytest.mark.parametrize(
        "overrides",
        [
            {"name": ""},
            {"name": None},
            {"invitation_code": ""},
            {"invitation_code": None},
            {"mode": "space"},
            {"mode": None},
            {"email": 42},
        ],
    )
    def test_invalid_requests_400(self, tmp_path, overrides):
        service, _ = _service(_config(tmp_path))
        status, payload = service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(**overrides),
            token=TOKEN,
            health_provider=lambda: {},
        )
        assert status == 400
        assert payload == {"error": "invalid_request"}

    def test_rate_limit_429_with_retry_after(self, tmp_path):
        service, clock = _service(_config(tmp_path), fixed_now=1000.0)
        body = self._body(invitation_code="wrong")  # attempts burn the cap
        for i in range(5):
            clock[0] = 1000.0 + i * 0.5
            status, _ = service.attempt(
                client_ip="9.9.9.9", payload=body, token=TOKEN, health_provider=lambda: {}
            )
            assert status == 403
        clock[0] = 1002.5
        status, payload = service.attempt(
            client_ip="9.9.9.9", payload=body, token=TOKEN, health_provider=lambda: {}
        )
        assert status == 429
        assert payload["error"] == E_PAIRING_RATE_LIMITED
        assert payload["retry_after_seconds"] >= 1

    def test_audit_redacts_email_never_code_or_token(self, tmp_path):
        lines = []
        service, _ = _service(_config(tmp_path), sink=lines.append)
        service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(),
            token=TOKEN,
            health_provider=lambda: {},
        )
        service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(invitation_code="wrong-one"),
            token=TOKEN,
            health_provider=lambda: {},
        )
        joined = "\n".join(lines)
        assert "***@example.com" in joined
        assert "alice@example.com" not in joined
        assert CODE not in joined
        assert TOKEN not in joined

    def test_health_provider_failure_is_honest(self, tmp_path):
        service, _ = _service(_config(tmp_path))

        def boom():
            raise RuntimeError("provider exploded")

        status, payload = service.attempt(
            client_ip="1.2.3.4",
            payload=self._body(),
            token=TOKEN,
            health_provider=boom,
        )
        assert status == 200
        assert payload["health"]["engine_state"] == "ERROR"


# ---------------------------------------------------------------------------
# endpoint integration (MonitoringAPI + POST /api/pair)
# ---------------------------------------------------------------------------


@pytest.fixture()
def pair_api(tmp_path):
    service = PairingService(load_pairing_config(_config(tmp_path)))
    instance = MonitoringAPI(auth_token=TOKEN, port=0, pairing_service=service)
    instance.start()
    yield instance
    instance.stop()


class TestPairEndpoint:
    def _body(self, **overrides):
        body = {
            "name": "alice-laptop",
            "email": "alice@example.com",
            "invitation_code": CODE,
            "mode": "cloud",
        }
        body.update(overrides)
        return body

    def test_pair_works_before_token_auth(self, pair_api):
        # NO Authorization header at all — pairing is the onboarding path
        code, body = _post(f"{pair_api.url}/api/pair", self._body())
        assert code == 200
        assert body["status"] == "paired"
        assert body["token"] == TOKEN

    def test_pair_disabled_when_service_not_wired(self):
        instance = MonitoringAPI(auth_token=TOKEN, port=0)
        instance.start()
        try:
            code, body = _post(f"{instance.url}/api/pair", self._body())
            assert code == 503
            assert body == {"error": E_PAIRING_DISABLED}
        finally:
            instance.stop()

    def test_pair_wrong_code_403(self, pair_api):
        code, body = _post(
            f"{pair_api.url}/api/pair", self._body(invitation_code="bad")
        )
        assert code == 403
        assert body == {"error": E_PAIRING_CODE_INVALID}

    def test_pair_malformed_json_400(self, pair_api):
        code, body = _post(
            f"{pair_api.url}/api/pair", b"{broken", headers={}
        )
        assert code == 400

    def test_pair_non_object_400(self, pair_api):
        code, _ = _post(f"{pair_api.url}/api/pair", [1, 2, 3])
        assert code == 400

    def test_pair_rate_limited_429(self, pair_api):
        for _ in range(5):
            code, body = _post(
                f"{pair_api.url}/api/pair", self._body(invitation_code="x")
            )
            assert code == 403
        code, body = _post(
            f"{pair_api.url}/api/pair", self._body(invitation_code="x")
        )
        assert code == 429
        assert body["error"] == E_PAIRING_RATE_LIMITED
        assert body["retry_after_seconds"] >= 1

    def test_pairing_attempts_do_not_exhaust_general_rate_budget(self, pair_api):
        # 5 pairing attempts (their own limiter) then a normal GET with
        # a valid token still works on the general 60/min budget.
        for _ in range(5):
            _post(f"{pair_api.url}/api/pair", self._body())
        request = urllib.request.Request(
            f"{pair_api.url}/api/health",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200

    def test_other_routes_still_token_first(self, pair_api):
        # the pairing surface did NOT open anything else
        code, body = _post(
            f"{pair_api.url}/api/killswitch/activate",
            {"confirm": True, "reason": "test"},
        )
        assert code == 401  # unauthenticated kill-switch still refused

    def test_killswitch_503_honesty_preserved(self, pair_api):
        code, body = _post(
            f"{pair_api.url}/api/killswitch/activate",
            {"confirm": True, "reason": "test"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert code == 503  # no activator wired in the bare path (kept)
        assert "fail closed" in body["error"]

    def test_root_listing_mentions_pair(self, pair_api):
        request = urllib.request.Request(
            pair_api.url + "/",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            listing = json.loads(response.read())
        assert "POST /api/pair (onboarding; invitation code)" in listing["routes"]
        assert listing["live_trading"] == "NOT_AUTHORIZED"

    def test_pair_modes_are_audited_only(self, pair_api):
        # both modes pair identically at the engine level (transport
        # posture is the APK's per-profile flag, not a server downgrade)
        for mode in ("cloud", "local"):
            code, body = _post(
                f"{pair_api.url}/api/pair", self._body(mode=mode)
            )
            assert code == 200
            assert body["pairing"]["mode"] == mode


class TestPairingModes:
    def test_modes_frozenset(self):
        assert PAIRING_MODES == frozenset({"cloud", "local"})


# ---------------------------------------------------------------------------
# mDNS announcement (graceful, never fatal, injectable)
# ---------------------------------------------------------------------------


class _FakeServiceInfo:
    def __init__(self, type_=None, name=None, addresses=None, port=None, properties=None, **kwargs):
        self.type_ = type_
        self.name = name
        self.addresses = addresses
        self.port = port
        self.properties = properties


class _FakeZeroconf:
    registered = []
    unregistered = []
    closed = False

    def __init__(self):
        self._services = []

    def register_service(self, info):
        self._services.append(info)
        _FakeZeroconf.registered.append(info)

    def unregister_service(self, info):
        _FakeZeroconf.unregistered.append(info)

    def close(self):
        _FakeZeroconf.closed = True


class TestMdnsAnnounce:
    def test_announce_registers_correct_service(self):
        announcement = try_announce_mdns(
            instance="unit-test",
            host="127.0.0.1",
            port=8018,
            zeroconf_factory=lambda: (_FakeZeroconf, _FakeServiceInfo),
        )
        assert announcement.announced
        assert SERVICE_TYPE in announcement.status
        (zc, info) = announcement.handle
        assert info.type_ == SERVICE_TYPE
        assert info.name == f"unit-test.{SERVICE_TYPE}"
        assert info.port == 8018
        announcement.stop()
        assert _FakeZeroconf.unregistered and _FakeZeroconf.closed

    def test_missing_package_is_graceful(self):
        def raising_factory():
            raise ImportError("no zeroconf")

        announcement = try_announce_mdns(zeroconf_factory=raising_factory)
        assert not announcement.announced
        assert "manual PC address" in announcement.status

    def test_registration_failure_is_graceful(self):
        class _BoomZeroconf(_FakeZeroconf):
            def register_service(self, info):
                raise RuntimeError("multicast blocked")

        announcement = try_announce_mdns(
            zeroconf_factory=lambda: (_BoomZeroconf, _FakeServiceInfo)
        )
        assert not announcement.announced
        assert "manual PC address" in announcement.status

    def test_default_instance_and_real_import_shape(self):
        from data_engine.runtime.announce import DEFAULT_INSTANCE as _inst

        assert _inst == "aitl-monitor"

    def test_real_zeroconf_importable_or_graceful(self):
        # zeroconf is a locked runtime dep — import must succeed in the
        # dev environment; the probe ONLY checks importability, never a
        # real network registration (CI determinism).
        try:
            import zeroconf  # noqa: F401
        except ImportError:
            pytest.skip("zeroconf not importable in this environment")


# ---------------------------------------------------------------------------
# CLI pair-status (B4) — enabled/disabled, never the code
# ---------------------------------------------------------------------------


class TestPairStatusCli:
    def test_enabled_status_never_shows_code(self, tmp_path, capsys):
        from data_engine.cli import main

        path = _config(tmp_path)
        with pytest.raises(SystemExit) as exc:
            main(["pair-status", "--config", str(path)])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "ENABLED" in out
        assert CODE not in out
        assert str(path) in out

    def test_disabled_status_on_missing_file(self, tmp_path, capsys):
        from data_engine.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["pair-status", "--config", str(tmp_path / "nope.json")])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "DISABLED" in out

    def test_malformed_config_is_loud(self, tmp_path, capsys):
        from data_engine.cli import main

        path = tmp_path / "broken.json"
        path.write_text("{oops", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            main(["pair-status", "--config", str(path)])
        assert exc.value.code == 1
        assert "CONFIG ERROR" in capsys.readouterr().err

    def test_format_pairing_status_shape(self, tmp_path):
        cfg = load_pairing_config(_config(tmp_path))
        text = format_pairing_status(cfg)
        assert "ENABLED" in text
        assert "never displayed" in text
        assert CODE not in text


# ---------------------------------------------------------------------------
# committed template posture (structural, CI-safe)
# ---------------------------------------------------------------------------


class TestCommittedTemplate:
    def test_template_hash_is_not_the_plaintext(self):
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        # the hash must be a 64-hex digest, never a quoted code literal
        payload = json.loads(text)
        assert len(payload["salt_hex"]) == 32
        assert len(payload["code_sha256_hex"]) == 64

    def test_template_json_is_flat_and_small(self):
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        assert len(text) < 400  # no hidden extras
        payload = json.loads(text)
        assert set(payload) == {
            "version",
            "enabled",
            "salt_hex",
            "code_sha256_hex",
            "max_attempts_per_minute",
        }
