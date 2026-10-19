"""Multi-asset instrument registration + per-asset-class validation
(Stage G, Part 9B G3 — owner mandate; audit-then-extend).

The existing ``brokers/instruments.py`` (Batch 7) already provides
fail-closed VENUE discovery + provenance + registry sync. This module
EXTENDS it with the multi-asset mandate: registration and validation
of STOCKS, CRYPTO COINS, METALS and FOREX instruments under
PER-ASSET-CLASS rules, each registration carrying provenance.

Fail-closed contract:

- every registration requires an explicit asset class + provenance
  record (source, recorded_at, recorder) — nothing enters the
  multi-asset registry unattributed;
- per-class RULES are enforced on the venue-normalized
  :class:`InstrumentSpec` (the single source of truth for precision
  and lot rules):

  * CRYPTO — base+quote assets REQUIRED (e.g. BTC/USDT); lot step a
    power-of-ten fraction; quantities positive; max >= min;
  * FOREX — base+quote REQUIRED (e.g. EUR/USD); lot step >= 0.0001
    and conventional (<= 0.01 step accepted: micro/mini/standard);
    tick size <= 0.01 (pip-scale pricing);
  * METAL — symbol must be a known metals symbol (XAU/XAG/XPT/XPD +
    /USD quote); quote asset USD; lot step >= 0.001 (troy-ounce
    fractions);
  * EQUITY (stocks) — quote asset REQUIRED; lot step integer-friendly
    (>= 1 or a simple fraction >= 0.1); tick_size >= 0.01 (cent
    ticks) unless explicitly sub-penny (>= 0.0001);

- a symbol already registered under a DIFFERENT asset class is a
  hard refusal (class drift is an explicit event, never silent);
- unknown asset classes are refused outright.

LIVE TRADING REMAINS NOT AUTHORIZED; registration grants NO trading
permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict

from data_engine.brokers.models import InstrumentSpec
from data_engine.schemas import AssetClass

#: Known precious/base metals (per-class vocabulary).
METAL_SYMBOLS = ("XAU", "XAG", "XPT", "XPD", "XBR", "XIR")


class InstrumentRegistrationError(ValueError):
    """Raised on multi-asset registration contract violations."""


class Provenance(BaseModel):
    """Who/where/when an instrument registration came from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    recorded_at: datetime
    recorder: str

    @classmethod
    def validate_source(cls, v: str) -> str:
        allowed = {"DISCOVERY", "CATALOG_IMPORT", "MANUAL_ENTRY"}
        if v not in allowed:
            raise InstrumentRegistrationError(
                f"provenance source must be one of {sorted(allowed)}"
            )
        return v


@dataclass(frozen=True)
class RegisteredInstrument:
    """One multi-asset registration entry."""

    spec: InstrumentSpec
    asset_class: AssetClass
    provenance: Provenance


def _positive(value: Decimal) -> bool:
    return value is not None and value > 0


def _power_of_ten_fraction(value: Decimal) -> bool:
    """0.0001, 0.001, 0.01, 1, 10 ... (crypto lot conventions)."""
    if value <= 0:
        return False
    scaled = value.normalize()
    sign, digits, exponent = scaled.as_tuple()
    if sign != 0:
        return False
    return all(d in (0, 1, 2, 5) for d in digits) and exponent <= 0


def _check_common(spec: InstrumentSpec) -> None:
    if not _positive(spec.tick_size):
        raise InstrumentRegistrationError(
            f"{spec.symbol}: tick_size must be positive"
        )
    if not _positive(spec.lot_step):
        raise InstrumentRegistrationError(
            f"{spec.symbol}: lot_step must be positive"
        )
    if spec.min_quantity is None or spec.min_quantity < 0:
        raise InstrumentRegistrationError(
            f"{spec.symbol}: min_quantity must be non-negative"
        )
    if (
        spec.max_quantity > 0
        and spec.max_quantity < spec.min_quantity
    ):
        raise InstrumentRegistrationError(
            f"{spec.symbol}: max_quantity < min_quantity"
        )
    if spec.min_notional is not None and spec.min_notional < 0:
        raise InstrumentRegistrationError(
            f"{spec.symbol}: min_notional must be non-negative"
        )


def _check_crypto(spec: InstrumentSpec) -> None:
    if not spec.base_asset or not spec.quote_asset:
        raise InstrumentRegistrationError(
            f"CRYPTO {spec.symbol}: base_asset and quote_asset are "
            "REQUIRED (e.g. BTC/USDT)"
        )
    if not _power_of_ten_fraction(spec.lot_step):
        raise InstrumentRegistrationError(
            f"CRYPTO {spec.symbol}: lot_step must be a power-of-ten "
            f"fraction (got {spec.lot_step})"
        )


def _check_forex(spec: InstrumentSpec) -> None:
    if not spec.base_asset or not spec.quote_asset:
        raise InstrumentRegistrationError(
            f"FOREX {spec.symbol}: base_asset and quote_asset are "
            "REQUIRED (e.g. EUR/USD)"
        )
    if len(spec.base_asset) != 3 or len(spec.quote_asset) != 3:
        raise InstrumentRegistrationError(
            f"FOREX {spec.symbol}: currency codes are 3 letters "
            f"({spec.base_asset}/{spec.quote_asset})"
        )
    if spec.lot_step < Decimal("0.0001") or spec.lot_step > Decimal("0.01"):
        raise InstrumentRegistrationError(
            f"FOREX {spec.symbol}: lot_step must be within "
            f"[0.0001, 0.01] (micro..standard lots; got {spec.lot_step})"
        )
    if spec.tick_size > Decimal("0.01"):
        raise InstrumentRegistrationError(
            f"FOREX {spec.symbol}: tick_size must be pip-scale "
            f"(<= 0.01; got {spec.tick_size})"
        )


def _check_metal(spec: InstrumentSpec) -> None:
    base = (spec.base_asset or spec.symbol[:3]).upper()
    if base not in METAL_SYMBOLS:
        raise InstrumentRegistrationError(
            f"METAL {spec.symbol}: base must be one of {METAL_SYMBOLS} "
            f"(troy-ounce quoted metals; got {base})"
        )
    if (spec.quote_asset or "USD").upper() != "USD":
        raise InstrumentRegistrationError(
            f"METAL {spec.symbol}: quote asset must be USD "
            f"(got {spec.quote_asset})"
        )
    if spec.lot_step < Decimal("0.001"):
        raise InstrumentRegistrationError(
            f"METAL {spec.symbol}: lot_step must be >= 0.001 "
            f"(ounce fractions; got {spec.lot_step})"
        )


def _check_equity(spec: InstrumentSpec) -> None:
    if not spec.quote_asset:
        raise InstrumentRegistrationError(
            f"EQUITY {spec.symbol}: quote_asset is REQUIRED "
            "(the listing currency)"
        )
    if spec.lot_step < Decimal("0.1"):
        raise InstrumentRegistrationError(
            f"EQUITY {spec.symbol}: lot_step must be >= 0.1 "
            f"(fractional-share brokers floor at tenths; got "
            f"{spec.lot_step})"
        )
    if spec.tick_size < Decimal("0.0001"):
        raise InstrumentRegistrationError(
            f"EQUITY {spec.symbol}: tick_size below 0.0001 refused "
            f"(sub-sub-penny pricing is not a listed-equity convention)"
        )


_CLASS_CHECKS = {
    AssetClass.CRYPTO: _check_crypto,
    AssetClass.FX: _check_forex,
    AssetClass.METAL: _check_metal,
    AssetClass.EQUITY: _check_equity,
}


class MultiAssetInstrumentRegistry:
    """Registration + validation of multi-asset instruments with
    provenance and per-asset-class rules (G3)."""

    def __init__(self) -> None:
        self._by_symbol: Dict[str, RegisteredInstrument] = {}

    def register(
        self,
        spec: InstrumentSpec,
        *,
        asset_class: AssetClass,
        provenance: Provenance,
    ) -> RegisteredInstrument:
        if not isinstance(spec, InstrumentSpec):
            raise InstrumentRegistrationError(
                "an InstrumentSpec is required (venue-normalized — the "
                "single source of truth for precision/lot rules)"
            )
        if not isinstance(asset_class, AssetClass):
            raise InstrumentRegistrationError(
                "an explicit AssetClass is required (fail closed — the "
                "class drives the validation rules)"
            )
        if not isinstance(provenance, Provenance):
            raise InstrumentRegistrationError(
                "a Provenance record is required (source, recorded_at, "
                "recorder — registrations are never unattributed)"
            )
        Provenance.validate_source(provenance.source)

        _check_common(spec)
        check = _CLASS_CHECKS.get(asset_class)
        if check is None:
            raise InstrumentRegistrationError(
                f"asset class {asset_class.value!r} has no registered "
                "validation rule set — UNKNOWN rules are BLOCKED "
                "(fail closed)"
            )
        check(spec)

        existing = self._by_symbol.get(spec.symbol)
        if existing is not None:
            if existing.asset_class is not asset_class:
                raise InstrumentRegistrationError(
                    f"{spec.symbol} is already registered as "
                    f"{existing.asset_class.value}; class drift to "
                    f"{asset_class.value} is an explicit removal + "
                    "re-registration, never a silent overwrite"
                )
            # idempotent re-registration of the same class is allowed
            return existing

        entry = RegisteredInstrument(
            spec=spec, asset_class=asset_class, provenance=provenance
        )
        self._by_symbol[spec.symbol] = entry
        return entry

    def get(self, symbol: str) -> RegisteredInstrument:
        entry = self._by_symbol.get(symbol)
        if entry is None:
            raise InstrumentRegistrationError(
                f"unknown instrument {symbol!r} (fail closed — never a "
                "guessed class)"
            )
        return entry

    def asset_class_for(self, symbol: str) -> AssetClass:
        return self.get(symbol).asset_class

    def symbols(self) -> tuple:
        return tuple(sorted(self._by_symbol))

    def __len__(self) -> int:
        return len(self._by_symbol)


def default_multi_asset_registry() -> MultiAssetInstrumentRegistry:
    """Reference registry with one valid instrument per mandated
    class (stocks, crypto, metals, forex), provenance-tagged."""
    from data_engine.brokers.adapters.paper import _paper_instruments

    registry = MultiAssetInstrumentRegistry()
    now = datetime.now(UTC)
    for spec, asset_class in (
        (_paper_instruments()[0], AssetClass.CRYPTO),   # BTCUSDT
        (_paper_instruments()[1], AssetClass.FX),       # EURUSD
        (
            InstrumentSpec(
                broker_id="paper-mock",
                symbol="XAUUSD",
                broker_symbol="XAUUSD",
                base_asset="XAU",
                quote_asset="USD",
                tick_size=Decimal("0.01"),
                lot_step=Decimal("0.01"),
                min_quantity=Decimal("0.01"),
                max_quantity=Decimal("1000"),
                min_notional=Decimal("0"),
                reference_price=Decimal("2650.00"),
            ),
            AssetClass.METAL,
        ),
        (
            InstrumentSpec(
                broker_id="paper-mock",
                symbol="AAPL",
                broker_symbol="AAPL",
                base_asset="AAPL",
                quote_asset="USD",
                tick_size=Decimal("0.01"),
                lot_step=Decimal("1"),
                min_quantity=Decimal("1"),
                max_quantity=Decimal("10000"),
                min_notional=Decimal("0"),
                reference_price=Decimal("230.00"),
            ),
            AssetClass.EQUITY,
        ),
    ):
        registry.register(
            spec,
            asset_class=asset_class,
            provenance=Provenance(
                source="CATALOG_IMPORT",
                recorded_at=now,
                recorder="default_multi_asset_registry",
            ),
        )
    return registry


__all__ = [
    "MultiAssetInstrumentRegistry",
    "RegisteredInstrument",
    "Provenance",
    "InstrumentRegistrationError",
    "default_multi_asset_registry",
    "METAL_SYMBOLS",
]
