"""Stage G / G3 — multi-asset instrument registry tests (Part 9B G3).

Per-asset-class rules (stocks / crypto / metals / forex) enforced
fail-closed; provenance REQUIRED on every registration; class drift
refused; unknown class rules BLOCKED.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from data_engine.brokers.instrument_registry import (
    InstrumentRegistrationError,
    MultiAssetInstrumentRegistry,
    Provenance,
    default_multi_asset_registry,
)
from data_engine.brokers.models import InstrumentSpec
from data_engine.schemas import AssetClass

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def _prov(source="MANUAL_ENTRY", recorder="test"):
    return Provenance(
        source=source, recorded_at=NOW, recorder=recorder
    )


def _spec(symbol="BTCUSDT", base="BTC", quote="USDT",
          tick="0.01", lot="0.0001", minq="0.0001", maxq="100",
          broker="paper-mock", ref="50000"):
    return InstrumentSpec(
        broker_id=broker,
        symbol=symbol,
        broker_symbol=symbol,
        base_asset=base,
        quote_asset=quote,
        tick_size=Decimal(tick),
        lot_step=Decimal(lot),
        min_quantity=Decimal(minq),
        max_quantity=Decimal(maxq),
        min_notional=Decimal("0"),
        reference_price=Decimal(ref),
    )


class TestPerClassRules:
    def test_crypto_requires_base_and_quote(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(base=None, quote=None),
                asset_class=AssetClass.CRYPTO,
                provenance=_prov(),
            )
        assert "base_asset and quote_asset" in str(excinfo.value)

    def test_crypto_lot_step_power_of_ten(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(lot="0.0003"),
                asset_class=AssetClass.CRYPTO,
                provenance=_prov(),
            )
        assert "power-of-ten" in str(excinfo.value)

    def test_forex_currency_code_lengths(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="EURUSD", base="EURO", quote="USD",
                      lot="0.01", tick="0.00001", ref="1.10"),
                asset_class=AssetClass.FX,
                provenance=_prov(),
            )
        assert "3 letters" in str(excinfo.value)

    def test_forex_lot_step_band(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="EURUSD", base="EUR", quote="USD",
                      lot="0.5", tick="0.00001", ref="1.10"),
                asset_class=AssetClass.FX,
                provenance=_prov(),
            )
        assert "micro..standard" in str(excinfo.value)

    def test_forex_tick_pip_scale(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="EURUSD", base="EUR", quote="USD",
                      lot="0.01", tick="0.05", ref="1.10"),
                asset_class=AssetClass.FX,
                provenance=_prov(),
            )
        assert "pip-scale" in str(excinfo.value)

    def test_metal_base_vocabulary(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="XYZUSD", base="XYZ", quote="USD",
                      lot="0.01", tick="0.01", ref="10"),
                asset_class=AssetClass.METAL,
                provenance=_prov(),
            )
        assert "troy-ounce" in str(excinfo.value)

    def test_metal_quote_must_be_usd(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="XAUUSDT", base="XAU", quote="USDT",
                      lot="0.01", tick="0.01", ref="2650"),
                asset_class=AssetClass.METAL,
                provenance=_prov(),
            )
        assert "USD" in str(excinfo.value)

    def test_metal_lot_step_floor(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="XAUUSD", base="XAU", quote="USD",
                      lot="0.0001", tick="0.01", ref="2650"),
                asset_class=AssetClass.METAL,
                provenance=_prov(),
            )
        assert "ounce fractions" in str(excinfo.value)

    def test_equity_requires_quote(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError):
            registry.register(
                _spec(symbol="AAPL", base="AAPL", quote=None,
                      lot="1", tick="0.01", ref="230"),
                asset_class=AssetClass.EQUITY,
                provenance=_prov(),
            )

    def test_equity_sub_sub_penny_tick_refused(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="AAPL", base="AAPL", quote="USD",
                      lot="1", tick="0.00001", ref="230"),
                asset_class=AssetClass.EQUITY,
                provenance=_prov(),
            )
        assert "sub-sub-penny" in str(excinfo.value)

    def test_common_precision_rules(self):
        registry = MultiAssetInstrumentRegistry()
        # tick_size <= 0 is refused by the SPEC model itself (pydantic
        # ValidationError is a ValueError — defense in depth)
        with pytest.raises(ValueError):
            registry.register(
                _spec(tick="0"),
                asset_class=AssetClass.CRYPTO,
                provenance=_prov(),
            )
        with pytest.raises(InstrumentRegistrationError):
            registry.register(
                _spec(minq="5", maxq="2"),
                asset_class=AssetClass.CRYPTO,
                provenance=_prov(),
            )


class TestProvenanceAndDrift:
    def test_registration_requires_provenance(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError):
            registry.register(
                _spec(), asset_class=AssetClass.CRYPTO, provenance=None
            )

    def test_provenance_source_vocabulary(self):
        with pytest.raises(InstrumentRegistrationError):
            Provenance.validate_source("MAGIC")
        assert Provenance.validate_source("DISCOVERY") == "DISCOVERY"

    def test_class_drift_refused(self):
        registry = MultiAssetInstrumentRegistry()
        registry.register(
            _spec(), asset_class=AssetClass.CRYPTO, provenance=_prov()
        )
        # same symbol, equity-VALID spec, different class -> drift
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(base="BTC", quote="USD", lot="1", tick="0.01"),
                asset_class=AssetClass.EQUITY,
                provenance=_prov(),
            )
        assert "class drift" in str(excinfo.value)

    def test_idempotent_same_class_registration(self):
        registry = MultiAssetInstrumentRegistry()
        first = registry.register(
            _spec(), asset_class=AssetClass.CRYPTO, provenance=_prov()
        )
        second = registry.register(
            _spec(), asset_class=AssetClass.CRYPTO, provenance=_prov()
        )
        assert first is second

    def test_unknown_symbol_lookup_fails_closed(self):
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError):
            registry.get("GHOST")

    def test_unknown_class_rules_blocked(self):
        """G5 discipline applies here too: a class without a
        registered rule set is UNKNOWN and therefore BLOCKED."""
        registry = MultiAssetInstrumentRegistry()
        with pytest.raises(InstrumentRegistrationError) as excinfo:
            registry.register(
                _spec(symbol="SPX", base="SPX", quote="USD",
                      lot="1", tick="0.01", ref="5000"),
                asset_class=AssetClass.INDEX,
                provenance=_prov(),
            )
        assert "BLOCKED" in str(excinfo.value)


class TestDefaultRegistry:
    def test_all_four_mandated_classes_present(self):
        registry = default_multi_asset_registry()
        classes = {
            registry.asset_class_for(s) for s in registry.symbols()
        }
        assert AssetClass.CRYPTO in classes
        assert AssetClass.FX in classes
        assert AssetClass.METAL in classes
        assert AssetClass.EQUITY in classes
        assert len(registry) == 4

    def test_every_entry_carries_provenance(self):
        registry = default_multi_asset_registry()
        for symbol in registry.symbols():
            entry = registry.get(symbol)
            assert entry.provenance.source == "CATALOG_IMPORT"
            assert entry.provenance.recorder == (
                "default_multi_asset_registry"
            )
            assert entry.provenance.recorded_at is not None
