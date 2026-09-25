"""Canonical instrument model for the AI Trading Lab Data Engine.

Supports multiple asset classes (XAU/USD, FX, equities, indices, crypto)
without assuming identical data semantics across asset classes.
"""

from data_engine.schemas import (
    Instrument as InstrumentSchema,
    AssetClass,
    ContractType,
)
from typing import Optional, Dict
from pydantic import BaseModel, Field
import re


# Supported instrument patterns
INSTRUMENT_PATTERNS = {
    "FX": r"^[A-Z]{3}/[A-Z]{3}$",           # e.g. EUR/USD
    "METAL": r"^[A-Z]+/[A-Z]{2,3}$",         # e.g. XAU/USD, XAG/USD
    "EQUITY": r"^[A-Z]+\.[A-Z]{2,4}$",       # e.g. AAPL.US
    "CRYPTO": r"^[A-Z]{3,6}/[A-Z]{3,6}$",    # e.g. BTC/USD
    "INDEX": r"^[A-Z]{2,5}\.[A-Z]{2,4}$",    # e.g. SPX.US
}


class InstrumentRegistry(BaseModel):
    """Registry of known instruments with their metadata."""
    instruments: Dict[str, InstrumentSchema] = Field(default_factory=dict)

    def register(self, instrument: InstrumentSchema):
        """Register an instrument in the canonical registry."""
        self.instruments[instrument.symbol] = instrument

    def get(self, symbol: str) -> Optional[InstrumentSchema]:
        """Retrieve an instrument by canonical symbol."""
        return self.instruments.get(symbol)

    def is_registered(self, symbol: str) -> bool:
        return symbol in self.instruments

    def classify_asset_class(self, symbol: str) -> Optional[AssetClass]:
        """Best-effort classification of an instrument's asset class."""
        if symbol.startswith("XAU") or symbol.startswith("XAG"):
            return AssetClass.METAL
        if "/" in symbol:
            parts = symbol.split("/")
            base = parts[0]
            crypto_bases = {"BTC", "ETH", "SOL", "ADA", "DOT", "AVAX", "MATIC"}
            if base in crypto_bases:
                return AssetClass.CRYPTO
            fx_pairs = {"EUR", "GBP", "USD", "JPY", "CHF", "AUD", "CAD", "NZD"}
            if base in fx_pairs and len(parts) == 2:
                return AssetClass.FX
            indices = {"SPX", "NDX", "DJI", "FTSE", "DAX", "NIK"}
            if base in indices:
                return AssetClass.INDEX
        return None

    def validate_symbol_format(self, symbol: str) -> tuple[bool, Optional[str]]:
        """Validate symbol format against known patterns.

        Returns (is_valid, error_message).
        """
        for asset_class, pattern in INSTRUMENT_PATTERNS.items():
            if re.match(pattern, symbol):
                return True, None
        return False, f"Symbol '{symbol}' does not match any known instrument pattern"


def create_xau_usd_instrument(exchange: Optional[str] = None) -> InstrumentSchema:
    """Create the canonical XAU/USD instrument.

    Used by gold-trading-lab integration. XAU/USD is a metal commodity.
    """
    return InstrumentSchema(
        symbol="XAU/USD",
        asset_class=AssetClass.METAL,
        base_asset="XAU",
        quote_asset="USD",
        exchange=exchange or "OTC",
        venue=exchange or "Over-the-Counter",
        contract_type=ContractType.SPOT,
        currency="USD",
        provider_symbol="XAUUSD",
    )


# Asset-class-specific data semantics
ASSET_SEMANTICS = {
    AssetClass.CRYPTO: {
        "trading_hours": "24/7",
        "volume_semantics": "base_asset_volume",
        "supports_bid_ask": True,
        "typical_sessions": None,  # No market hours
    },
    AssetClass.FX: {
        "trading_hours": "24/5 (UTC Sun-Fri)",
        "volume_semantics": "tick_volume",
        "supports_bid_ask": True,
        "typical_sessions": {"Sydney", "Tokyo", "London", "New York"},
    },
    AssetClass.EQUITY: {
        "trading_hours": "exchange-dependent",
        "volume_semantics": "share_volume",
        "supports_bid_ask": True,
        "typical_sessions": {"Exchange hours"},
    },
    AssetClass.INDEX: {
        "trading_hours": "exchange-dependent",
        "volume_semantics": "contract_volume",
        "supports_bid_ask": False,
        "typical_sessions": {"Exchange hours"},
    },
    AssetClass.COMMODITY: {
        "trading_hours": "exchange-dependent",
        "volume_semantics": "contract_volume",
        "supports_bid_ask": True,
        "typical_sessions": {"Exchange hours"},
    },
    AssetClass.METAL: {
        "trading_hours": "24/5 (OTC)",
        "volume_semantics": "troy_oz_volume",
        "supports_bid_ask": True,
        "typical_sessions": {"London, New York, Sydney"},
    },
}


def get_asset_semantics(asset_class: AssetClass) -> dict:
    """Return data semantics for the given asset class."""
    return ASSET_SEMANTICS.get(asset_class, {})


def validate_volume_semantics(asset_class: AssetClass, volume: Optional[float]) -> bool:
    """Validate volume semantics according to asset class.

    Does not reject a dataset merely because volume is unavailable
    when the provider legitimately does not supply it.
    """
    semantics = get_asset_semantics(asset_class)
    if volume is None and semantics.get("supports_bid_ask"):
        return True  # Volume optional for this asset class
    if volume is not None and volume < 0:
        return False
    return True
