"""v1.5.0 accounts + mandatory TOTP 2FA tests (deterministic, offline).

Pins the owner mandate: "email kobi bhi login two factors verification
ke baghair na ho" — password alone NEVER yields a session; enrollment
is an explicit handshake; lockout is fail-closed; admin ops require
the admin role.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine.runtime import totp
from data_engine.runtime.accounts import (
    AccountError,
    AccountService,
    AccountStore,
    SessionManager,
)

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # RFC test vector secret


class TestTotp:
    def test_rfc6238_vectors(self):
        # RFC 6238 appendix B (8-digit, SHA1) test vectors
        vectors = [
            (59, "94287082"),
            (1111111109, "07081804"),
            (1111111111, "14050471"),
            (1234567890, "89005924"),
            (2000000000, "69279037"),
            (20000000000, "65353130"),
        ]
        for unix_ts, expected in vectors:
            counter = unix_ts // 30
            assert totp.hotp_at(RFC_SECRET, counter, digits=8) == expected

    def test_generate_secret_shape(self):
        secret = totp.generate_secret()
        assert len(secret) == 32
        assert secret.isalnum()
        with pytest.raises(ValueError):
            totp.generate_secret(8)

    def test_verify_window(self):
        secret = totp.generate_secret()
        code = totp.totp_at(secret, NOW)
        assert totp.verify(secret, code, NOW)
        assert totp.verify(secret, code, NOW - timedelta(seconds=30))
        assert totp.verify(secret, code, NOW + timedelta(seconds=30))
        assert not totp.verify(secret, code, NOW + timedelta(seconds=95))
        assert not totp.verify(secret, "12345", NOW)  # wrong length
        assert not totp.verify(secret, "0000000", NOW)

    def test_provisioning_uri(self):
        secret = totp.generate_secret()
        uri = totp.provisioning_uri("owner@lab.io", secret)
        assert uri.startswith("otpauth://totp/AI-Trading-Lab:owner@lab.io?")
        assert f"secret={secret}" in uri
        assert "digits=6" in uri and "period=30" in uri


@pytest.fixture()
def service(tmp_path):
    svc = AccountService(tmp_path)
    svc.store.create_account(
        "admin@lab.io", "Owner", "SuperSecret123", "admin", now=NOW
    )
    svc.store.create_account(
        "trader@lab.io", "Trader", "TraderPass1234", "trader", now=NOW
    )
    return svc


class TestAccountStore:
    def test_passwords_are_hashed_not_stored(self, tmp_path):
        store = AccountStore(tmp_path)
        store.create_account(
            "a@b.io", "A", "Password12345", "trader", now=NOW
        )
        raw = (tmp_path / "accounts.json").read_text()
        assert "Password12345" not in raw
        assert "pbkdf2_sha256$" in raw

    def test_duplicate_email_refused(self, service):
        with pytest.raises(AccountError):
            service.store.create_account(
                "admin@lab.io", "X", "Password12345", "trader", now=NOW
            )

    def test_weak_password_refused(self, service):
        with pytest.raises(AccountError):
            service.store.create_account(
                "new@lab.io", "N", "short", "trader", now=NOW
            )

    def test_invalid_role_refused(self, service):
        with pytest.raises(AccountError):
            service.store.create_account(
                "new@lab.io", "N", "Password12345", "root", now=NOW
            )

    def test_sanitize_never_leaks_secrets(self, service):
        for account in service.store.list_accounts():
            assert "password_pbkdf2" not in account
            assert "totp_secret" not in account


class TestLoginTwoFactor:
    def test_password_alone_never_yields_session(self, service):
        result = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "E_TOTP_ENROLLMENT_REQUIRED"
        assert "token" not in result

    def test_bad_password_refused_before_2fa(self, service):
        result = service.login(
            "admin@lab.io", "WRONG", "", ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "E_BAD_CREDENTIALS"

    def test_unknown_account_is_bad_credentials(self, service):
        result = service.login(
            "ghost@lab.io", "whatever123", "123456", ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "E_BAD_CREDENTIALS"

    def test_enrollment_handshake_sticky_secret(self, service):
        first = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        secret = first["totp_secret"]
        second = service.login(
            "admin@lab.io", "SuperSecret123", "000009", ip="1.1.1.1", now=NOW
        )
        assert second["outcome"] == "E_TOTP_ENROLLMENT_REQUIRED"
        assert second["totp_secret"] == secret  # sticky, not rotated

    def test_enrollment_confirms_with_valid_code(self, service):
        first = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        code = totp.totp_at(first["totp_secret"], NOW)
        result = service.login(
            "admin@lab.io", "SuperSecret123", code, ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "SESSION"
        assert result["user"]["role"] == "admin"

    def test_enrolled_login_requires_valid_code(self, service):
        # enroll admin
        first = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        code = totp.totp_at(first["totp_secret"], NOW)
        service.login(
            "admin@lab.io", "SuperSecret123", code, ip="1.1.1.1", now=NOW
        )
        # enrolled: valid code works, wrong code refused
        good = service.login(
            "admin@lab.io", "SuperSecret123",
            totp.totp_at(first["totp_secret"], NOW + timedelta(seconds=30)),
            ip="1.1.1.1", now=NOW,
        )
        assert good["outcome"] == "SESSION"
        bad = service.login(
            "admin@lab.io", "SuperSecret123", "999999",
            ip="1.1.1.1", now=NOW,
        )
        assert bad["outcome"] == "E_TOTP_INVALID"

    def test_lockout_after_five_failures(self, service):
        first = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        code = totp.totp_at(first["totp_secret"], NOW)
        service.login(
            "admin@lab.io", "SuperSecret123", code, ip="1.1.1.1", now=NOW
        )
        outcome = None
        moment = NOW
        for _ in range(5):
            outcome = service.login(
                "admin@lab.io", "SuperSecret123", "999998",
                ip="1.1.1.1", now=moment,
            )
        # the 5th wrong code TRIPS the lock; the NEXT attempt is refused
        assert outcome["outcome"] == "E_TOTP_INVALID"
        locked = service.login(
            "admin@lab.io", "SuperSecret123", "999998",
            ip="1.1.1.1", now=moment,
        )
        assert locked["outcome"] == "E_ACCOUNT_LOCKED"
        # even the CORRECT code is refused while locked
        correct = service.login(
            "admin@lab.io", "SuperSecret123",
            totp.totp_at(first["totp_secret"], NOW),
            ip="1.1.1.1", now=moment,
        )
        assert correct["outcome"] == "E_ACCOUNT_LOCKED"

    def test_login_history_recorded(self, service):
        service.login(
            "admin@lab.io", "SuperSecret123", "", ip="7.7.7.7", now=NOW
        )
        history = service.store.login_history("admin@lab.io")
        assert history
        assert history[-1]["ip"] == "7.7.7.7"
        assert history[-1]["ok"] is False
        assert history[-1]["reason"] == "enroll-bad-totp"


class TestSessions:
    def test_session_ttl_and_revocation(self):
        manager = SessionManager(ttl_seconds=3600)
        issued = manager.issue("a@b.io", "trader", now=NOW)
        assert manager.validate(issued["token"], now=NOW)["role"] == "trader"
        assert manager.validate(
            issued["token"], now=NOW + timedelta(seconds=3601)
        ) is None
        issued2 = manager.issue("a@b.io", "trader", now=NOW)
        assert manager.revoke(issued2["token"]) is True
        assert manager.validate(issued2["token"], now=NOW) is None

    def test_revoke_all_for_email(self):
        manager = SessionManager()
        manager.issue("a@b.io", "trader", now=NOW)
        manager.issue("a@b.io", "trader", now=NOW)
        manager.issue("c@d.io", "admin", now=NOW)
        assert manager.revoke_all_for("a@b.io") == 2


class TestAdminOperations:
    def test_trader_cannot_use_admin_ops(self, service):
        with pytest.raises(AccountError):
            service.accounts(actor_role="trader")
        with pytest.raises(AccountError):
            service.create_user(
                actor_role="trader", email="x@y.io", name="X",
                password="Password12345", role="trader",
            )
        with pytest.raises(AccountError):
            service.reset_2fa(actor_role="trader", email="admin@lab.io")

    def test_admin_creates_and_lists_users(self, service):
        service.create_user(
            actor_role="admin", email="new@lab.io", name="New",
            password="Password12345", role="trader", now=NOW,
        )
        accounts = service.accounts(actor_role="admin")
        assert accounts["count"] == 3
        emails = {a["email"] for a in accounts["accounts"]}
        assert "new@lab.io" in emails

    def test_admin_reset_2fa_revokes_sessions(self, service):
        first = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        code = totp.totp_at(first["totp_secret"], NOW)
        session = service.login(
            "admin@lab.io", "SuperSecret123", code, ip="1.1.1.1", now=NOW
        )
        token = session["token"]
        assert service.sessions.validate(token, now=NOW) is not None
        service.reset_2fa(actor_role="admin", email="admin@lab.io")
        assert service.sessions.validate(token, now=NOW) is None
        # next login re-enrolls
        again = service.login(
            "admin@lab.io", "SuperSecret123", "", ip="1.1.1.1", now=NOW
        )
        assert again["outcome"] == "E_TOTP_ENROLLMENT_REQUIRED"

    def test_admin_lock_unlock(self, service):
        service.set_lock(
            actor_role="admin", email="trader@lab.io", locked=True, now=NOW
        )
        result = service.login(
            "trader@lab.io", "TraderPass1234", "", ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "E_ACCOUNT_LOCKED"
        service.set_lock(
            actor_role="admin", email="trader@lab.io", locked=False, now=NOW
        )
        result = service.login(
            "trader@lab.io", "TraderPass1234", "", ip="1.1.1.1", now=NOW
        )
        assert result["outcome"] == "E_TOTP_ENROLLMENT_REQUIRED"
