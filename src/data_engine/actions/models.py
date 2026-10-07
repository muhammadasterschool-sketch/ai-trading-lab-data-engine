"""Phase 4A.2 — Corporate Action models (blueprint 5.12).

Discriminated union of equity corporate actions with PIT correctness:

- SplitAction            (ratio_numerator : ratio_denominator)
- DividendAction         (cash amount per share)
- SymbolChangeAction     (old_symbol -> new_symbol)
- DelistingAction        (instrument leaves the venue)

Invariants (blueprint 5.12):
- Historical data preserved; adjusted price separated (chain.py)
- PIT-correct application: an action is only *known* after its
  announcement_time; applying it before that is a scope violation
- Action duplication rejected (duplicate action_id / same symbol+time)
- Deterministic action identity hash, prefix ``ca42.``

Phase boundary (spec 12.1/12.5): 4A.1 owns the identity primitives;
this module owns the equity action engine. No calendar computation and
no universe membership logic live here (calendar.py / universe.py).
"""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Identity prefix for corporate action hashes (Phase 4A.2).
CORPORATE_ACTION_PREFIX = "ca42."

#: Phase 4A.2 component contract version.
PHASE_4A2_CONTRACT_VERSION = "1.0.0"


class CorporateActionType(str, Enum):
    """Enumeration of supported corporate action types."""

    SPLIT = "split"
    DIVIDEND = "dividend"
    SYMBOL_CHANGE = "symbol_change"
    DELISTING = "delisting"


def _require_utc(v: datetime, field_name: str) -> datetime:
    """Validate that a datetime is timezone-aware; normalize to UTC."""
    if v is None or v.tzinfo is None:
        raise ValueError(
            f"{field_name} must be a timezone-aware datetime (blueprint "
            "5.12 PIT correctness; UTC normalization)"
        )
    return v.astimezone(UTC)


def _require_symbol(v: str) -> str:
    """Validate an instrument symbol: non-empty, uppercase-able, sane."""
    if not isinstance(v, str) or not v.strip():
        raise ValueError("symbol must be a non-empty string")
    normalized = v.strip().upper()
    if any(ch.isspace() for ch in normalized):
        raise ValueError("symbol must not contain whitespace")
    return normalized


class CorporateAction(BaseModel):
    """Common base for all corporate actions (discriminated union).

    ``announcement_time`` is when the world learned of the action;
    ``effective_time`` is when it takes effect. PIT correctness demands
    ``announcement_time <= effective_time`` — a future-dated
    announcement for an already-effective action is a data corruption.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str
    action_type: CorporateActionType
    symbol: str
    announcement_time: datetime
    effective_time: datetime
    venue: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("action_id")
    @classmethod
    def _validate_action_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("action_id must be a non-empty string")
        return v.strip()

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        return _require_symbol(v)

    @field_validator("announcement_time")
    @classmethod
    def _validate_announcement(cls, v: datetime) -> datetime:
        return _require_utc(v, "announcement_time")

    @field_validator("effective_time")
    @classmethod
    def _validate_effective(cls, v: datetime) -> datetime:
        return _require_utc(v, "effective_time")

    @model_validator(mode="after")
    def _validate_chronology(self) -> "CorporateAction":
        if self.announcement_time > self.effective_time:
            raise ValueError(
                "PIT violation: announcement_time must be <= "
                f"effective_time (got announcement={self.announcement_time}, "
                f"effective={self.effective_time})"
            )
        return self

    def is_known_at(self, as_of: datetime) -> bool:
        """True if this action was publicly known at ``as_of`` (UTC)."""
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return self.announcement_time <= as_of.astimezone(UTC)

    def is_effective_at(self, as_of: datetime) -> bool:
        """True if this action had taken effect by ``as_of`` (UTC)."""
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return self.effective_time <= as_of.astimezone(UTC)

    def identity_payload(self) -> dict[str, Any]:
        """Canonical identity payload for hashing (ordered by contract)."""
        payload: dict[str, Any] = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "symbol": self.symbol,
            "announcement_time": self.announcement_time,
            "effective_time": self.effective_time,
            "venue": self.venue,
        }
        return payload

    @property
    def action_hash(self) -> str:
        """Deterministic identity: ``ca42.`` + SHA-256 hex (70 chars)."""
        return CORPORATE_ACTION_PREFIX + deterministic_hash(
            self.identity_payload()
        )


class SplitAction(CorporateAction):
    """Stock split (or reverse split). Ratio 2/1 = two-for-one.

    Adjustment rule (chain.py): candles *before* effective_time are
    divided by ``ratio``; volume is multiplied by ``ratio``.
    """

    action_type: CorporateActionType = CorporateActionType.SPLIT
    ratio_numerator: Decimal
    ratio_denominator: Decimal

    @field_validator("ratio_numerator", "ratio_denominator")
    @classmethod
    def _validate_ratio_parts(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise ValueError("split ratio part must be a positive Decimal")
        return v

    @model_validator(mode="after")
    def _validate_ratio_sane(self) -> "SplitAction":
        if self.ratio_numerator == self.ratio_denominator:
            raise ValueError("split ratio must differ from 1 (no-op split)")
        return self

    @property
    def ratio(self) -> Decimal:
        """Split ratio as a Decimal (e.g. 2.0 for a 2:1 split)."""
        return self.ratio_numerator / self.ratio_denominator

    def identity_payload(self) -> dict[str, Any]:
        payload = super().identity_payload()
        payload["ratio_numerator"] = str(self.ratio_numerator)
        payload["ratio_denominator"] = str(self.ratio_denominator)
        return payload


class DividendAction(CorporateAction):
    """Cash dividend per share.

    Adjustment rule (chain.py): candles *before* effective_time have
    the dividend amount subtracted from OHLC (cash-dividend basis).
    """

    action_type: CorporateActionType = CorporateActionType.DIVIDEND
    amount: Decimal
    currency: str = Field(default="USD")

    @field_validator("amount")
    @classmethod
    def _validate_amount(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v < 0:
            raise ValueError("dividend amount must be a non-negative Decimal")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("currency must be a non-empty string")
        return v.strip().upper()

    def identity_payload(self) -> dict[str, Any]:
        payload = super().identity_payload()
        payload["amount"] = str(self.amount)
        payload["currency"] = self.currency
        return payload


class SymbolChangeAction(CorporateAction):
    """Ticker symbol change: old_symbol -> new_symbol.

    The action's ``symbol`` field carries the OLD symbol (the identity
    whose history is being relabelled); ``new_symbol`` is the target.
    """

    action_type: CorporateActionType = CorporateActionType.SYMBOL_CHANGE
    new_symbol: str

    @field_validator("new_symbol")
    @classmethod
    def _validate_new_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("new_symbol must be a non-empty string")
        normalized = v.strip().upper()
        if any(ch.isspace() for ch in normalized):
            raise ValueError("new_symbol must not contain whitespace")
        return normalized

    @model_validator(mode="after")
    def _validate_distinct(self) -> "SymbolChangeAction":
        if self.symbol == self.new_symbol:
            raise ValueError("symbol change must map to a different symbol")
        return self

    def identity_payload(self) -> dict[str, Any]:
        payload = super().identity_payload()
        payload["new_symbol"] = self.new_symbol
        return payload


class DelistingAction(CorporateAction):
    """Instrument delisting: the symbol leaves its venue."""

    action_type: CorporateActionType = CorporateActionType.DELISTING
    reason: str

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("delisting reason must be a non-empty string")
        return v.strip()

    def identity_payload(self) -> dict[str, Any]:
        payload = super().identity_payload()
        payload["reason"] = self.reason
        return payload


#: Discriminated union of all corporate actions.
AnyCorporateAction = (
    SplitAction
    | DividendAction
    | SymbolChangeAction
    | DelistingAction
)

__all__ = [
    "CorporateActionType",
    "CorporateAction",
    "SplitAction",
    "DividendAction",
    "SymbolChangeAction",
    "DelistingAction",
    "AnyCorporateAction",
    "CORPORATE_ACTION_PREFIX",
    "PHASE_4A2_CONTRACT_VERSION",
]
