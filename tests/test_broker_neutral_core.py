"""Broker-neutral core contract tests (multi-broker mandate, Phase M1).

Covers the normalized vocabulary, the typed error taxonomy, the
capability registry discipline and the credential-redaction boundary.
Fail-closed everywhere: invalid shapes raise, incoherent descriptors
cannot be registered, REAL execution modes cannot be registered, and
secret material never renders.
"""

from decimal import Decimal

import pytest

from data_engine.brokers import (
    BINANCE_MOCK_CAPABILITIES,
    BROKER_ADAPTER_SURFACE,
    BYBIT_MOCK_CAPABILITIES,
    BrokerCapabilities,
    BrokerCredential,
    BrokerErrorCategory,
    CapabilityRegistry,
    CapabilityRegistryError,
    CredentialError,
    ExecutionMode,
    InstrumentSpec,
    MT5_MOCK_CAPABILITIES,
    OrderKind,
    OrderRequest,
    PAPER_MOCK_CAPABILITIES,
    RateLimitError,
    RETRYABLE_CATEGORIES,
    Side,
    TimeInForce,
    UnknownOrderStateError,
    UnsupportedOrderError,
    VenueOrderStatus,
    assert_no_secret_material,
    default_registry,
    find_secret_leak,
)
from data_engine.brokers.errors import (
    BrokerExecutionError,
    OrderRefusedError,
    redact_mapping,
    scrub_text,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import AccountMode, PositionMode
from data_engine.brokers.capabilities import (
    IdempotencyKeyMechanism,
    RateLimitPolicy,
    SlTpSemantics,
)

SECRET = "mock-secret-material-DO-NOT-PRINT"


# ---------------------------------------------------------------------------
# Normalized order models
# ---------------------------------------------------------------------------

class TestOrderRequestValidation:

    def test_market_order_valid(self):
        req = OrderRequest(
            client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
            side=Side.BUY, order_kind=OrderKind.MARKET, quantity=Decimal("0.5"),
        )
        assert req.time_in_force is TimeInForce.GTC
        assert req.price is None and req.stop_price is None

    def test_limit_requires_price(self):
        with pytest.raises(Exception):
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.BUY, order_kind=OrderKind.LIMIT, quantity=Decimal("0.5"),
            )

    def test_market_must_not_carry_price(self):
        with pytest.raises(Exception):
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.BUY, order_kind=OrderKind.MARKET,
                quantity=Decimal("0.5"), price=Decimal("50000.00"),
            )

    def test_stop_requires_stop_price(self):
        with pytest.raises(Exception):
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.SELL, order_kind=OrderKind.STOP, quantity=Decimal("0.5"),
            )

    def test_market_must_not_carry_stop_price(self):
        with pytest.raises(Exception):
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.SELL, order_kind=OrderKind.MARKET,
                quantity=Decimal("0.5"), stop_price=Decimal("49000.00"),
            )

    @pytest.mark.parametrize("bad_quantity", [
        Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity"),
    ])
    def test_quantity_must_be_positive_finite(self, bad_quantity):
        with pytest.raises(Exception):
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.BUY, order_kind=OrderKind.MARKET, quantity=bad_quantity,
            )

    @pytest.mark.parametrize("field", ["client_order_id", "account_id", "symbol"])
    def test_identifiers_must_be_non_empty(self, field):
        kwargs = dict(
            client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
            side=Side.BUY, order_kind=OrderKind.MARKET, quantity=Decimal("0.5"),
        )
        kwargs[field] = "   "
        with pytest.raises(Exception):
            OrderRequest(**kwargs)

    def test_request_digest_fields_are_stable_and_complete(self):
        req = OrderRequest(
            client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=Decimal("0.5"), price=Decimal("50000.00"),
        )
        fields = req.request_digest_fields()
        assert fields["side"] == "BUY"
        assert fields["order_kind"] == "LIMIT"
        assert fields["quantity"] == "0.5"
        assert fields["stop_price"] == ""  # absent fields serialize as ""
        # Same intent → identical digest payload (idempotency basis).
        assert dict(fields) == dict(
            OrderRequest(
                client_order_id="cid-1", account_id="acct-1", symbol="BTCUSDT",
                side=Side.BUY, order_kind=OrderKind.LIMIT,
                quantity=Decimal("0.5"), price=Decimal("50000.00"),
            ).request_digest_fields()
        )


class TestInstrumentSpec:

    def _spec(self) -> InstrumentSpec:
        return InstrumentSpec(
            broker_id="paper-mock", symbol="BTCUSDT", broker_symbol="BTCUSDT",
            base_asset="BTC", quote_asset="USDT",
            tick_size=Decimal("0.01"), lot_step=Decimal("0.001"),
            min_quantity=Decimal("0.001"), max_quantity=Decimal("10"),
            min_notional=Decimal("10"), reference_price=Decimal("50000.00"),
        )

    def test_quantize_price_rounds_half_up_to_tick(self):
        spec = self._spec()
        assert spec.quantize_price(Decimal("50000.005")) == Decimal("50000.01")
        assert spec.quantize_price(Decimal("50000.004")) == Decimal("50000")

    def test_quantize_quantity_rounds_to_lot_step(self):
        spec = self._spec()
        assert spec.quantize_quantity(Decimal("0.0015")) == Decimal("0.002")

    def test_order_problems_clean_order(self):
        assert self._spec().order_problems(
            Decimal("0.5"), Decimal("50000.00")
        ) == ()

    def test_order_problems_lot_misalignment(self):
        problems = self._spec().order_problems(Decimal("0.5005"))
        assert any("lot step" in p for p in problems)

    def test_order_problems_below_minimum_quantity(self):
        problems = self._spec().order_problems(Decimal("0.0005"))
        assert any("below the venue minimum" in p for p in problems)

    def test_order_problems_above_maximum_quantity(self):
        problems = self._spec().order_problems(Decimal("11"))
        assert any("above the venue maximum" in p for p in problems)

    def test_order_problems_tick_misalignment(self):
        problems = self._spec().order_problems(
            Decimal("0.5"), Decimal("50000.005")
        )
        assert any("tick size" in p for p in problems)

    def test_order_problems_below_min_notional(self):
        problems = self._spec().order_problems(
            Decimal("0.001"), Decimal("5000.00")  # 5 < 10
        )
        assert any("minimum" in p for p in problems)

    def test_unknown_status_is_first_class(self):
        # UNKNOWN must exist as a distinct status (ambiguous outcomes are
        # recorded, never guessed away).
        assert VenueOrderStatus.UNKNOWN.value == "UNKNOWN"


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class TestErrorTaxonomy:

    def test_retryable_categories_are_exactly_transport_three(self):
        assert RETRYABLE_CATEGORIES == frozenset({
            BrokerErrorCategory.CONNECTIVITY,
            BrokerErrorCategory.TIMEOUT,
            BrokerErrorCategory.RATE_LIMIT,
        })

    def test_retryability_derives_from_category_only(self):
        connectivity = BrokerExecutionError(
            "down", category=BrokerErrorCategory.CONNECTIVITY, broker_id="x"
        )
        invalid = BrokerExecutionError(
            "bad shape", category=BrokerErrorCategory.INVALID_ORDER, broker_id="x"
        )
        assert connectivity.retryable is True
        assert invalid.retryable is False

    def test_rate_limit_error_carries_retry_after(self):
        err = RateLimitError(
            "throttled", broker_id="binance-mock",
            venue_code="429", retry_after_seconds=1.5,
        )
        assert err.retry_after_seconds == 1.5
        assert err.category is BrokerErrorCategory.RATE_LIMIT
        assert err.retryable is True

    def test_rate_limit_error_rejects_nonpositive_retry_after(self):
        err = RateLimitError(
            "throttled", broker_id="x", retry_after_seconds=-3
        )
        assert err.retry_after_seconds is None

    def test_unknown_state_error_requires_client_order_id(self):
        with pytest.raises(ValueError):
            UnknownOrderStateError("ambiguous", broker_id="x", client_order_id=" ")

    def test_refused_error_requires_reason_code(self):
        with pytest.raises(ValueError):
            OrderRefusedError("nope", broker_id="x", reason_code="")

    def test_unsupported_error_carries_venue_alternative(self):
        err = UnsupportedOrderError(
            "no STOP on spot", broker_id="binance-mock",
            alternative="submit STOP_LOSS_LIMIT as a separate order",
        )
        assert err.alternative.startswith("submit")

    def test_errors_name_their_broker(self):
        err = BrokerExecutionError(
            "boom", category=BrokerErrorCategory.INTERNAL, broker_id="bybit-mock"
        )
        assert err.broker_id == "bybit-mock"
        assert err.retryable is False

    def test_scrub_text_replaces_secrets(self):
        text = f"credential {SECRET} attached"
        assert SECRET not in scrub_text(text, [SECRET])
        assert "<redacted>" in scrub_text(text, [SECRET])

    def test_redact_mapping_recurses(self):
        obj = {"a": f"token={SECRET}", "nested": {"b": SECRET}}
        red = redact_mapping(obj, [SECRET])
        assert SECRET not in str(red)
        assert red["nested"]["b"] == "<redacted>"


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

class TestCapabilityRegistry:

    def test_default_registry_has_the_four_mocks(self):
        registry = default_registry()
        assert registry.broker_ids() == (
            "binance-mock", "bybit-mock", "mt5-mock", "paper-mock"
        )

    def test_unknown_broker_fails_closed(self):
        with pytest.raises(CapabilityRegistryError):
            default_registry().get("nonexistent-broker")

    def test_duplicate_registration_is_idempotent_for_same_descriptor(self):
        registry = default_registry()
        before = len(registry)
        registry.register(PAPER_MOCK_CAPABILITIES)
        assert len(registry) == before

    def test_descriptor_drift_is_refused(self):
        registry = default_registry()
        drifted = PAPER_MOCK_CAPABILITIES.model_copy(
            update={"display_name": "silently different"}
        )
        with pytest.raises(CapabilityRegistryError):
            registry.register(drifted)

    def test_incoherent_descriptor_cannot_register(self):
        # BALANCES_ONLY venue with ATTACHED SL/TP is semantically impossible.
        with pytest.raises(Exception):
            BrokerCapabilities(
                broker_id="incoherent",
                display_name="Incoherent",
                order_kinds=(OrderKind.MARKET,),
                sl_tp=SlTpSemantics.ATTACHED,
                position_mode=PositionMode.BALANCES_ONLY,
            )

    def test_real_execution_mode_cannot_register(self):
        # REAL modes are refused at registration: live trading is NOT
        # AUTHORIZED in this repository.
        with pytest.raises(Exception):
            BrokerCapabilities(
                broker_id="live-broker",
                display_name="Live",
                execution_mode=ExecutionMode.REAL,
                order_kinds=(OrderKind.MARKET,),
                account_modes=(AccountMode.REAL,),
            )

    def test_empty_order_kinds_cannot_register(self):
        with pytest.raises(Exception):
            BrokerCapabilities(broker_id="empty", display_name="Empty")


class TestCapabilityDescriptors:

    def test_paper_mock_is_the_full_reference_surface(self):
        caps = PAPER_MOCK_CAPABILITIES
        assert set(caps.order_kinds) == {
            OrderKind.MARKET, OrderKind.LIMIT,
            OrderKind.STOP, OrderKind.STOP_LIMIT,
        }
        assert caps.sl_tp is SlTpSemantics.ATTACHED
        assert caps.position_mode is PositionMode.NETTING
        assert caps.supports_reduce_only is True
        assert caps.account_modes == (AccountMode.DEMO,)

    def test_mt5_mock_encodes_exness_xm_class_semantics(self):
        caps = MT5_MOCK_CAPABILITIES
        assert caps.position_mode is PositionMode.HEDGING
        assert caps.sl_tp is SlTpSemantics.ATTACHED
        assert caps.idempotency_key is IdempotencyKeyMechanism.COMMENT_FIELD
        assert caps.supports_reduce_only is False
        assert set(caps.time_in_force) == {TimeInForce.GTC, TimeInForce.IOC}
        assert caps.account_modes == (AccountMode.DEMO,)  # REAL refused

    def test_binance_mock_encodes_spot_filters_semantics(self):
        caps = BINANCE_MOCK_CAPABILITIES
        assert set(caps.order_kinds) == {OrderKind.MARKET, OrderKind.LIMIT}
        assert caps.sl_tp is SlTpSemantics.SEPARATE_ORDERS
        assert caps.position_mode is PositionMode.BALANCES_ONLY
        assert caps.idempotency_key is IdempotencyKeyMechanism.NATIVE_CLIENT_ID
        assert caps.rate_limit.max_requests_per_window == 10

    def test_bybit_mock_encodes_v5_semantics(self):
        caps = BYBIT_MOCK_CAPABILITIES
        assert caps.position_mode is PositionMode.NETTING
        assert caps.sl_tp is SlTpSemantics.ATTACHED
        assert caps.idempotency_key is IdempotencyKeyMechanism.NATIVE_CLIENT_ID
        assert caps.supports_reduce_only is True
        assert caps.rate_limit.max_orders_per_window == 5

    def test_supports_queries(self):
        assert BINANCE_MOCK_CAPABILITIES.supports_order_kind(OrderKind.LIMIT)
        assert not BINANCE_MOCK_CAPABILITIES.supports_order_kind(OrderKind.STOP)
        assert MT5_MOCK_CAPABILITIES.supports_time_in_force(TimeInForce.IOC)
        assert not MT5_MOCK_CAPABILITIES.supports_time_in_force(TimeInForce.FOK)

    def test_rate_limit_policy_rejects_bad_shapes(self):
        with pytest.raises(Exception):
            RateLimitPolicy(window_seconds=0)
        with pytest.raises(Exception):
            RateLimitPolicy(max_orders_per_window=-1)


class TestAdapterSurface:

    def test_surface_matches_the_abstract_interface_exactly(self):
        # Fail closed on accidental interface growth: an unreviewed new
        # method on BrokerAdapter is a contract change, not a patch.
        abstract = {
            name for name in dir(BrokerAdapter)
            if getattr(getattr(BrokerAdapter, name), "__isabstractmethod__", False)
        }
        assert abstract == set(BROKER_ADAPTER_SURFACE)

    def test_surface_covers_the_mandate_requirements(self):
        surface = " ".join(BROKER_ADAPTER_SURFACE)
        for required in (
            "connect", "disconnect", "health",        # lifecycle
            "account_info", "instrument_spec",        # account + instruments
            "submit_order", "cancel_order", "order_status",  # orders
            "positions", "balances", "reconcile",     # state + reconciliation
        ):
            assert required in surface


# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------

class TestCredentialRedaction:

    def test_repr_and_str_never_leak(self):
        cred = BrokerCredential("acct-1", SECRET)
        assert SECRET not in repr(cred)
        assert SECRET not in str(cred)
        assert "<redacted>" in repr(cred)

    def test_credential_requires_non_empty_secret(self):
        with pytest.raises(CredentialError):
            BrokerCredential("acct-1", "")
        with pytest.raises(CredentialError):
            BrokerCredential("", SECRET)

    def test_credential_rejects_nul_bytes(self):
        with pytest.raises(CredentialError):
            BrokerCredential("acct-1", "bad\x00secret")

    def test_equality_compares_account_only(self):
        a = BrokerCredential("acct-1", "secret-one")
        b = BrokerCredential("acct-1", "secret-two")
        assert a == b  # interchangeable handles for the same account
        assert a != BrokerCredential("acct-2", "secret-one")

    def test_matches_account(self):
        cred = BrokerCredential("acct-1", SECRET)
        assert cred.matches_account("acct-1")
        assert not cred.matches_account("acct-2")

    def test_find_secret_leak_reports_leaks(self):
        assert find_secret_leak(["safe", f"leak: {SECRET}"], [SECRET])
        assert find_secret_leak(["safe", "also safe"], [SECRET]) == []

    def test_assert_no_secret_material_raises_on_leak(self):
        with pytest.raises(CredentialError):
            assert_no_secret_material(
                [{"nested": [f"token {SECRET}"]}], [SECRET]
            )

    def test_assert_no_secret_material_passes_clean_outputs(self):
        assert_no_secret_material(
            ["clean", {"k": "v"}, ["x", "y"]], [SECRET]
        )
