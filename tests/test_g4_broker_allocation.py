"""Stage G / G4 — multi-broker allocation engine tests (Part 9B G4).

Fail-closed config validation; capability-aware routing; hard
per-broker limits; UNKNOWN broker capabilities BLOCKED; deterministic
selection; auditable config changes; per-broker ledger payloads.
"""

from decimal import Decimal

import pytest

from data_engine.brokers.allocation import (
    AllocationConfig,
    AllocationError,
    AllocationRefused,
    BrokerAllocationEntry,
    BrokerLoad,
    OrderRequestSpec,
    route_order,
    validate_allocation_change,
)
from data_engine.brokers.capabilities import default_registry
from data_engine.brokers.models import OrderKind, TimeInForce


def _entry(broker: str, weight: str, **overrides) -> BrokerAllocationEntry:
    return BrokerAllocationEntry(
        broker_id=broker, weight=Decimal(weight), **overrides
    )


def _config(*entries: BrokerAllocationEntry) -> AllocationConfig:
    return AllocationConfig(entries=entries)


def _request(**overrides) -> OrderRequestSpec:
    defaults = dict(order_kind=OrderKind.MARKET)
    defaults.update(overrides)
    return OrderRequestSpec(**defaults)


REGISTRY = default_registry()  # 7 registered MOCK_DETERMINISTIC venues


class TestConfigValidation:
    def test_empty_config_refused(self):
        with pytest.raises(Exception):
            AllocationConfig(entries=())

    def test_duplicate_brokers_refused(self):
        with pytest.raises(Exception) as excinfo:
            AllocationConfig(
                entries=(
                    _entry("paper-mock", "0.5"),
                    _entry("paper-mock", "0.5"),
                )
            )
        assert "duplicate" in str(excinfo.value).lower()

    def test_weights_must_sum_to_exactly_one(self):
        with pytest.raises(Exception) as excinfo:
            AllocationConfig(
                entries=(
                    _entry("paper-mock", "0.4"),
                    _entry("mt5-mock", "0.4"),
                )
            )
        assert "exactly 1" in str(excinfo.value)

    def test_non_positive_weight_refused(self):
        with pytest.raises(Exception):
            BrokerAllocationEntry(broker_id="paper-mock", weight=Decimal("0"))
        with pytest.raises(Exception):
            BrokerAllocationEntry(broker_id="paper-mock", weight=Decimal("-1"))

    def test_valid_config_accepted(self):
        config = _config(
            _entry("paper-mock", "0.6"), _entry("mt5-mock", "0.4")
        )
        assert config.entry_for("paper-mock").weight == Decimal("0.6")
        with pytest.raises(AllocationError):
            config.entry_for("unknown-broker")

    def test_open_orders_floor(self):
        with pytest.raises(Exception):
            BrokerAllocationEntry(
                broker_id="paper-mock", weight=Decimal("1"),
                max_open_orders=0,
            )


class TestRouting:
    def test_highest_weight_wins(self):
        config = _config(
            _entry("paper-mock", "0.3"), _entry("mt5-mock", "0.7")
        )
        decision = route_order(
            _request(), config=config, registry=REGISTRY
        )
        assert decision.broker_id == "mt5-mock"
        assert decision.weight == Decimal("0.7")
        assert "paper-mock" in decision.eligible_brokers

    def test_capability_aware_kind(self):
        """A broker without STOP support is skipped for STOP orders
        (binance-mock supports only MARKET/LIMIT; paper-mock all)."""
        config = _config(
            _entry("binance-mock", "0.9"), _entry("paper-mock", "0.1")
        )
        decision = route_order(
            _request(order_kind=OrderKind.STOP),
            config=config,
            registry=REGISTRY,
        )
        assert decision.broker_id == "paper-mock"
        skip_reasons = dict(decision.skipped)
        assert "binance-mock" in skip_reasons
        assert "unsupported" in skip_reasons["binance-mock"]

    def test_capability_aware_time_in_force(self):
        """mt5-mock lacks FOK; a FOK order routes to paper-mock."""
        config = _config(
            _entry("mt5-mock", "0.9"), _entry("paper-mock", "0.1")
        )
        decision = route_order(
            _request(time_in_force=TimeInForce.FOK),
            config=config,
            registry=REGISTRY,
        )
        assert decision.broker_id == "paper-mock"
        assert "time-in-force" in dict(decision.skipped)["mt5-mock"]

    def test_capability_aware_reduce_only(self):
        """Only paper-mock and bybit-mock support reduce-only; a
        reduce-only order skips venues without it."""
        config = _config(
            _entry("binance-mock", "0.9"), _entry("bybit-mock", "0.1")
        )
        decision = route_order(
            _request(reduce_only=True), config=config, registry=REGISTRY
        )
        assert decision.broker_id == "bybit-mock"
        assert "reduce-only" in dict(decision.skipped)["binance-mock"]

    def test_open_order_cap_skips_broker(self):
        config = _config(
            _entry("mt5-mock", "0.9", max_open_orders=2),
            _entry("paper-mock", "0.1", max_open_orders=10),
        )
        loads = {
            "mt5-mock": BrokerLoad("mt5-mock", open_orders=2),
            "paper-mock": BrokerLoad("paper-mock", open_orders=0),
        }
        decision = route_order(
            _request(), config=config, registry=REGISTRY, loads=loads
        )
        assert decision.broker_id == "paper-mock"
        assert "cap reached" in dict(decision.skipped)["mt5-mock"]

    def test_notional_cap_skips_broker(self):
        config = _config(
            _entry(
                "mt5-mock", "0.9",
                max_open_notional=Decimal("1000"),
            ),
            _entry("paper-mock", "0.1"),
        )
        loads = {
            "mt5-mock": BrokerLoad(
                "mt5-mock", open_orders=0, open_notional=Decimal("900")
            ),
            "paper-mock": BrokerLoad("paper-mock"),
        }
        decision = route_order(
            _request(notional=Decimal("500")), config=config,
            registry=REGISTRY, loads=loads,
        )
        assert decision.broker_id == "paper-mock"
        assert "notional cap" in dict(decision.skipped)["mt5-mock"]

    def test_no_eligible_broker_refuses(self):
        config = _config(
            _entry("mt5-mock", "1.0", max_open_orders=1),
        )
        loads = {"mt5-mock": BrokerLoad("mt5-mock", open_orders=5)}
        with pytest.raises(AllocationRefused) as excinfo:
            route_order(
                _request(), config=config, registry=REGISTRY, loads=loads
            )
        assert "never falls back" in str(excinfo.value)

    def test_unknown_broker_in_config_is_blocked(self):
        """G5 discipline: UNKNOWN capabilities are BLOCKED."""
        config = _config(
            _entry("ghost-broker", "0.5"), _entry("paper-mock", "0.5")
        )
        with pytest.raises(AllocationRefused) as excinfo:
            route_order(_request(), config=config, registry=REGISTRY)
        assert "ghost-broker" in str(excinfo.value)
        assert "BLOCKED" in str(excinfo.value)

    def test_tie_breaks_deterministically_by_broker_id(self):
        config = _config(
            _entry("paper-mock", "0.5"), _entry("mt5-mock", "0.5")
        )
        decisions = {
            route_order(_request(), config=config, registry=REGISTRY).broker_id
            for _ in range(5)
        }
        assert decisions == {"mt5-mock"}  # ascending id: m < p
        decision = route_order(_request(), config=config, registry=REGISTRY)
        assert "tie" in decision.rationale

    def test_decision_carries_ledger_payload(self):
        config = _config(_entry("paper-mock", "1.0"))
        decision = route_order(_request(), config=config, registry=REGISTRY)
        payload = decision.ledger_payload()
        assert payload["selected_broker"] == "paper-mock"
        assert Decimal(payload["weight"]) == Decimal("1")
        assert payload["eligible"] == ["paper-mock"]
        assert isinstance(payload["skipped"], list)


class TestAllocationChangeAudit:
    def test_change_is_auditable(self):
        old = _config(_entry("paper-mock", "1.0"))
        new = _config(
            _entry("paper-mock", "0.5"), _entry("mt5-mock", "0.5")
        )
        change = validate_allocation_change(old, new)
        payload = change.ledger_payload()
        assert payload["change"] == "allocation-config"
        assert payload["old"][0]["broker_id"] == "paper-mock"
        assert len(payload["new"]) == 2
        assert payload["new"][1]["weight"] == "0.5"

    def test_change_requires_valid_new_config(self):
        with pytest.raises(AllocationError):
            validate_allocation_change(None, "not-a-config")

    def test_initial_config_change_audits_from_empty(self):
        new = _config(_entry("paper-mock", "1.0"))
        change = validate_allocation_change(None, new)
        assert change.ledger_payload()["old"] == []
