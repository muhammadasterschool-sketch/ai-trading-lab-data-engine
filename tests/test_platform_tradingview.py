"""Platform package tests — TradingView webhook validation (Phase G).

Webhook security discipline with a mocked transport: schema strictness,
HMAC authentication, replay/staleness windows, nonce dedup and
unknown-instrument fail-closed refusals. A validated signal is ADVISORY
ONLY — no order authority exists anywhere in this contract.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from data_engine.platform import (
    TVEventCategory,
    TVSignalPayload,
    TVSignalValidator,
    expected_digest,
)
from data_engine.platform.tradingview import TVRefusalReason

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
SECRET = "unit-test-shared-secret"


def _payload(**overrides: Any) -> dict[str, Any]:
    base = dict(
        strategy_id="STR-1",
        instrument="OANDA:XAUUSD",
        event_type="entry_long",
        event_timestamp=T0,
        timeframe="1d",
        signal={"price": 2350.0},
        nonce="nonce-1",
    )
    base.update(overrides)
    return base


def _signed(raw: dict[str, Any], secret: str = SECRET) -> dict[str, Any]:
    payload = TVSignalPayload(**{**raw, "auth_digest": "0" * 32})
    digest = expected_digest(secret, payload)
    return {**raw, "auth_digest": digest}


def _validator(**kwargs: Any) -> TVSignalValidator:
    kwargs.setdefault("secret_provider", lambda: SECRET)
    return TVSignalValidator(**kwargs)


class TestSchemaStrictness:
    def test_valid_payload_passes(self):
        validator = _validator()
        signal, refusal = validator.validate(_signed(_payload()), received_at=T0)
        assert refusal is None and signal is not None
        assert signal.advisory_only is True

    def test_unknown_field_refused(self):
        raw = _signed(_payload())
        raw["exec_order_now"] = True  # injection attempt
        validator = _validator()
        _, refusal = validator.validate(raw, received_at=T0)
        assert refusal is not None
        assert refusal.reason is TVRefusalReason.INVALID_SCHEMA

    def test_missing_nonce_refused(self):
        raw = _signed(_payload())
        del raw["nonce"]
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal is not None

    def test_short_auth_digest_refused(self):
        raw = _payload(auth_digest="short")
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal.reason is TVRefusalReason.INVALID_SCHEMA


class TestAuthentication:
    def test_wrong_secret_refused(self):
        raw = _signed(_payload(), secret="attacker-secret")
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal.reason is TVRefusalReason.AUTH_FAILED

    def test_tampered_payload_refused(self):
        raw = _signed(_payload())
        raw["signal"] = {"price": 999999.0}  # mutate after signing
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal.reason is TVRefusalReason.AUTH_FAILED

    def test_digest_is_deterministic_contract(self):
        p1 = TVSignalPayload(**_payload(), auth_digest="0" * 32)
        p2 = TVSignalPayload(**_payload(), auth_digest="0" * 32)
        assert expected_digest(SECRET, p1) == expected_digest(SECRET, p2)


class TestReplayProtection:
    def test_stale_timestamp_refused(self):
        raw = _signed(_payload(event_timestamp=T0 - timedelta(hours=1)))
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal.reason is TVRefusalReason.STALE_TIMESTAMP

    def test_far_future_timestamp_refused(self):
        raw = _signed(_payload(event_timestamp=T0 + timedelta(hours=1)))
        _, refusal = _validator().validate(raw, received_at=T0)
        assert refusal.reason is TVRefusalReason.STALE_TIMESTAMP

    def test_duplicate_nonce_refused(self):
        validator = _validator()
        raw = _signed(_payload())
        first, _ = validator.validate(raw, received_at=T0)
        assert first is not None
        _, refusal = validator.validate(raw, received_at=T0 + timedelta(seconds=1))
        assert refusal.reason is TVRefusalReason.DUPLICATE_NONCE

    def test_same_content_different_nonce_accepted(self):
        validator = _validator()
        one = _signed(_payload(nonce="a"))
        two = _signed(_payload(nonce="b"))
        s1, r1 = validator.validate(one, received_at=T0)
        s2, r2 = validator.validate(two, received_at=T0)
        assert (s1, s2) is not None and r1 is None and r2 is None


class TestRouting:
    def test_unknown_instrument_fails_closed(self):
        validator = _validator(instrument_resolver=lambda sym: None)
        _, refusal = validator.route(_signed(_payload()), received_at=T0)
        assert refusal.reason is TVRefusalReason.UNKNOWN_INSTRUMENT
        assert "not proof" in refusal.detail or "not a verified" in refusal.detail

    def test_no_resolver_configured_fails_closed(self):
        validator = _validator(instrument_resolver=None)
        _, refusal = validator.route(_signed(_payload()), received_at=T0)
        assert refusal.reason is TVRefusalReason.ROUTER_REJECTED

    def test_valid_route_produces_advisory_intent(self):
        validator = _validator(instrument_resolver=lambda sym: "iid-gold")
        intent, refusal = validator.route(_signed(_payload()), received_at=T0)
        assert refusal is None
        assert intent.internal_instrument_id == "iid-gold"
        assert intent.strategy_id == "STR-1"
        assert intent.event_type is TVEventCategory.ENTRY_LONG

    def test_validation_failure_short_circuits_routing(self):
        validator = _validator(instrument_resolver=lambda sym: "iid-gold")
        bad = _signed(_payload(), secret="wrong")
        _, refusal = validator.route(bad, received_at=T0)
        assert refusal.reason is TVRefusalReason.AUTH_FAILED
