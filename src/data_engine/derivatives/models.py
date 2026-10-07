"""Phase 4A.3 — FuturesContract models (blueprint 5.14).

Single-venue futures contract specifications with deterministic
identity. Invariants:

- Contracts and continuous series are DISTINCT entities (a continuous
  series references contracts by hash; it is never a contract itself).
- Contract specifications are immutable and complete: symbol, expiry,
  tick size, multiplier, delivery month — every field validated.
- Deterministic identity: ``fut43.`` prefix over the typed payload.
- No roll logic here (rollover.py owns it — separation of concerns
  mirrors the 4A.1 component discipline).
"""

from datetime import date, datetime, UTC
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Identity prefix for futures contract hashes.
FUTURES_PREFIX = "fut43."

#: Phase 4A.3 component contract version.
PHASE_4A3_CONTRACT_VERSION = "1.0.0"


def _require_positive(v: Decimal) -> Decimal:
    if v is None or not v.is_finite() or v <= 0:
        raise ValueError("value must be a positive finite Decimal")
    return v


class FuturesContract(BaseModel):
    """One deliverable futures contract specification.

    ``first_notice`` and ``last_trading`` dates govern roll timing
    (rollover.py): positions must roll before first notice for
    physically-settled contracts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_id: str
    root_symbol: str
    expiry: date
    tick_size: Decimal
    multiplier: Decimal
    delivery_month: int  # 1..12
    delivery_year: int
    first_notice: Optional[date] = None
    last_trading: Optional[date] = None
    venue: Optional[str] = None
    currency: str = Field(default="USD")

    @field_validator("contract_id", "root_symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("contract identifiers must be non-empty strings")
        normalized = v.strip().upper()
        if any(ch.isspace() for ch in normalized):
            raise ValueError("identifiers must not contain whitespace")
        return normalized

    @field_validator("expiry")
    @classmethod
    def _validate_expiry(cls, v: date) -> date:
        if v is None:
            raise ValueError("expiry is required (a futures contract always expires)")
        return v

    @field_validator("tick_size", "multiplier")
    @classmethod
    def _validate_positive_decimals(cls, v: Decimal) -> Decimal:
        return _require_positive(v)

    @field_validator("delivery_month")
    @classmethod
    def _validate_month(cls, v: int) -> int:
        if not isinstance(v, int) or not 1 <= v <= 12:
            raise ValueError("delivery_month must be an int in 1..12")
        return v

    @field_validator("delivery_year")
    @classmethod
    def _validate_year(cls, v: int) -> int:
        if not isinstance(v, int) or not 1970 <= v <= 2200:
            raise ValueError("delivery_year must be a sane int in 1970..2200")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("currency must be a non-empty string")
        return v.strip().upper()

    @model_validator(mode="after")
    def _validate_dates(self) -> "FuturesContract":
        if self.delivery_month != self.expiry.month:
            raise ValueError(
                "delivery_month must match expiry month "
                f"(got {self.delivery_month} vs expiry {self.expiry.isoformat()})"
            )
        if self.delivery_year != self.expiry.year:
            raise ValueError(
                "delivery_year must match expiry year "
                f"(got {self.delivery_year} vs expiry {self.expiry.isoformat()})"
            )
        if self.first_notice is not None and self.first_notice > self.expiry:
            raise ValueError("first_notice must be on or before expiry")
        if self.last_trading is not None and self.last_trading > self.expiry:
            raise ValueError("last_trading must be on or before expiry")
        if (
            self.first_notice is not None
            and self.last_trading is not None
            and self.first_notice > self.last_trading
        ):
            raise ValueError("first_notice must be <= last_trading")
        return self

    @property
    def contract_hash(self) -> str:
        """Deterministic identity: ``fut43.`` + SHA-256 hex (69 chars)."""
        payload = {
            "contract_version": PHASE_4A3_CONTRACT_VERSION,
            "contract_id": self.contract_id,
            "root_symbol": self.root_symbol,
            "expiry": self.expiry.isoformat(),
            "tick_size": str(self.tick_size),
            "multiplier": str(self.multiplier),
            "delivery_month": self.delivery_month,
            "delivery_year": self.delivery_year,
            "first_notice": self.first_notice.isoformat() if self.first_notice else None,
            "last_trading": self.last_trading.isoformat() if self.last_trading else None,
            "venue": self.venue,
            "currency": self.currency,
        }
        return FUTURES_PREFIX + deterministic_hash(payload)


__all__ = [
    "FuturesContract",
    "FUTURES_PREFIX",
    "PHASE_4A3_CONTRACT_VERSION",
]
