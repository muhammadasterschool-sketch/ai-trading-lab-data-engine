"""Phase 4A.2 — AdjustmentChain: PIT-correct price adjustment (blueprint 5.12).

Applies corporate actions to OHLCV candles with two hard invariants:

1. **Historical data preserved.** ``adjust()`` NEVER mutates or returns
   a reference to the input candles: the result is a new list, and the
   ``AdjustedSeries`` records the hash of the ORIGINAL series, so the
   unadjusted history remains verifiable and separate.

2. **PIT correctness (no future knowledge).** Only actions with
   ``announcement_time <= as_of`` may be applied. Attempting to apply
   an action that was not yet announced at ``as_of`` raises
   ``FutureActionError`` — look-ahead via corporate actions is a
   blocker-grade defect, not a warning.

Split adjustment: candles strictly before ``effective_time`` divide
OHLC by the ratio and multiply volume by the ratio. Dividend
adjustment: candles strictly before ``effective_time`` subtract the
cash amount from OHLC. Symbol changes relabel candles strictly after
``effective_time`` to the new symbol (history keeps the old label).
Delistings mark candles strictly after ``effective_time`` as
post-delist (excluded from adjusted output).

Deterministic identity: ``adj42.`` prefix over the ordered action
hashes plus the original series hash.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.actions.models import (
    AnyCorporateAction,
    CorporateAction,
    DelistingAction,
    DividendAction,
    SplitAction,
    SymbolChangeAction,
    PHASE_4A2_CONTRACT_VERSION,
)

#: Identity prefix for adjustment-chain hashes.
ADJUSTMENT_CHAIN_PREFIX = "adj42."

#: Candle field names adjusted for price-level actions.
_PRICE_FIELDS = ("open", "high", "low", "close")


class CorporateActionError(ValueError):
    """Raised on any corporate-action contract violation."""


class FutureActionError(CorporateActionError):
    """Raised when an action not yet announced is applied (PIT violation)."""


def _candle_timestamp(candle: Mapping[str, Any]) -> datetime:
    """Extract a timezone-aware timestamp from a duck-typed candle."""
    ts = candle.get("timestamp")
    if ts is None:
        raise CorporateActionError(
            "candle is missing 'timestamp' (duck-typed OHLCV contract)"
        )
    if not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise CorporateActionError(
            "candle timestamp must be timezone-aware (UTC)"
        )
    return ts.astimezone(UTC)


def _adjust_price(value: Any, operation: str, operand: Decimal) -> Any:
    """Apply a price adjustment preserving the input numeric type.

    Decimals stay Decimal (exact); floats stay float (research mode).
    Any other numeric type is rejected — silent coercion is forbidden.
    """
    if isinstance(value, Decimal):
        if operation == "div":
            return value / operand
        if operation == "sub":
            return value - operand
    elif isinstance(value, float):
        if operation == "div":
            return value / float(operand)
        if operation == "sub":
            return value - float(operand)
    else:
        raise CorporateActionError(
            f"price field must be Decimal or float, got {type(value).__name__}"
        )
    raise CorporateActionError(f"unknown operation {operation!r}")


def _adjust_volume(value: Any, ratio: Decimal) -> Any:
    """Multiply volume by the split ratio, preserving numeric type."""
    if isinstance(value, Decimal):
        return value * ratio
    if isinstance(value, float):
        return value * float(ratio)
    if isinstance(value, int):
        return int(value * ratio) if ratio == int(ratio) else value * float(ratio)
    raise CorporateActionError(
        f"volume field must be Decimal/float/int, got {type(value).__name__}"
    )


class AdjustmentChain(BaseModel):
    """Ordered chain of corporate actions for ONE instrument symbol."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    actions: tuple[AnyCorporateAction, ...] = ()

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("chain symbol must be a non-empty string")
        return v.strip().upper()

    @model_validator(mode="after")
    def _validate_chain(self) -> "AdjustmentChain":
        seen_ids: set[str] = set()
        seen_keys: set[tuple[str, datetime]] = set()
        last_effective: Optional[datetime] = None
        for action in self.actions:
            if action.symbol != self.symbol:
                raise ValueError(
                    f"action {action.action_id} belongs to symbol "
                    f"{action.symbol}, not chain symbol {self.symbol}"
                )
            if action.action_id in seen_ids:
                raise ValueError(
                    f"duplicate action_id {action.action_id!r} in chain "
                    "(blueprint 5.12 failure mode: action duplication)"
                )
            seen_ids.add(action.action_id)
            key = (action.action_type.value, action.effective_time)
            if key in seen_keys:
                raise ValueError(
                    f"duplicate {action.action_type.value} action at "
                    f"{action.effective_time} for {self.symbol}"
                )
            seen_keys.add(key)
            if last_effective is not None and action.effective_time < last_effective:
                raise ValueError(
                    "actions must be ordered by non-decreasing effective_time "
                    f"(got {action.effective_time} after {last_effective})"
                )
            last_effective = action.effective_time
        return self

    # ------------------------------------------------------------------
    # PIT queries
    # ------------------------------------------------------------------
    def known_at(self, as_of: datetime) -> tuple[AnyCorporateAction, ...]:
        """Actions publicly known at ``as_of`` (announcement <= as_of)."""
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        return tuple(a for a in self.actions if a.announcement_time <= cutoff)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    @property
    def chain_hash(self) -> str:
        """Deterministic chain identity over ordered action hashes."""
        payload = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "symbol": self.symbol,
            "action_hashes": [a.action_hash for a in self.actions],
        }
        return ADJUSTMENT_CHAIN_PREFIX + deterministic_hash(payload)

    # ------------------------------------------------------------------
    # Adjustment engine
    # ------------------------------------------------------------------
    def adjust(
        self,
        candles: Sequence[Mapping[str, Any]],
        as_of: datetime,
    ) -> "AdjustedSeries":
        """Adjust ``candles`` using only actions known at ``as_of``.

        The input sequence is never mutated. Every applied action must
        satisfy ``announcement_time <= as_of`` or the call fails closed
        with :class:`FutureActionError` (no silent look-ahead).

        Delisted candles (timestamp strictly after a delisting's
        effective_time) are EXCLUDED from the adjusted output and
        recorded in ``excluded_indices`` — a delisted instrument has no
        post-delist price history by definition.
        """
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)

        # Fail closed BEFORE any computation if the chain itself
        # contains an action not yet known at as_of (PIT guard).
        applicable: list[CorporateAction] = []
        for action in self.actions:
            if action.announcement_time > cutoff:
                raise FutureActionError(
                    f"action {action.action_id} ({action.action_type.value}) "
                    f"was announced {action.announcement_time}, after the "
                    f"as_of cutoff {cutoff}; applying it would be look-ahead "
                    "(blueprint 5.12 PIT violation)"
                )
            applicable.append(action)

        original = [dict(c) for c in candles]
        original_hash = deterministic_hash(
            [
                {
                    "timestamp": _candle_timestamp(c).isoformat(),
                    "open": str(c.get("open")),
                    "high": str(c.get("high")),
                    "low": str(c.get("low")),
                    "close": str(c.get("close")),
                    "volume": str(c.get("volume")),
                }
                for c in original
            ]
        )

        working = [dict(c) for c in original]
        excluded: list[int] = []
        applied: list[str] = []

        for action in applicable:
            applied.append(action.action_hash)
            if isinstance(action, SplitAction):
                ratio = action.ratio
                for candle in working:
                    if _candle_timestamp(candle) < action.effective_time:
                        for field in _PRICE_FIELDS:
                            if candle.get(field) is not None:
                                candle[field] = _adjust_price(
                                    candle[field], "div", ratio
                                )
                        if candle.get("volume") is not None:
                            candle["volume"] = _adjust_volume(
                                candle["volume"], ratio
                            )
            elif isinstance(action, DividendAction):
                for candle in working:
                    if _candle_timestamp(candle) < action.effective_time:
                        for field in _PRICE_FIELDS:
                            if candle.get(field) is not None:
                                candle[field] = _adjust_price(
                                    candle[field], "sub", action.amount
                                )
            elif isinstance(action, SymbolChangeAction):
                for candle in working:
                    if _candle_timestamp(candle) > action.effective_time:
                        candle["symbol"] = action.new_symbol
            elif isinstance(action, DelistingAction):
                for idx, candle in enumerate(working):
                    if (
                        idx not in excluded
                        and _candle_timestamp(candle) > action.effective_time
                    ):
                        excluded.append(idx)

        kept = [c for i, c in enumerate(working) if i not in excluded]

        return AdjustedSeries(
            symbol=self.symbol,
            as_of=cutoff,
            original_series_hash=original_hash,
            applied_action_hashes=tuple(applied),
            candles=tuple(kept),
            excluded_indices=tuple(excluded),
        )


class AdjustedSeries(BaseModel):
    """Result of an adjustment pass — adjusted data SEPARATED from history.

    ``original_series_hash`` pins the unadjusted series (invariant:
    historical data preserved). ``applied_action_hashes`` records the
    exact action set used (invariant: PIT-correct application, auditable).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    as_of: datetime
    original_series_hash: str
    applied_action_hashes: tuple[str, ...]
    candles: tuple[Mapping[str, Any], ...]
    excluded_indices: tuple[int, ...] = ()

    @property
    def adjusted_series_hash(self) -> str:
        """Deterministic identity of the adjusted output (adj42. prefix)."""
        payload = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "symbol": self.symbol,
            "as_of": self.as_of,
            "original_series_hash": self.original_series_hash,
            "applied_action_hashes": list(self.applied_action_hashes),
            "candles": [
                {
                    "timestamp": _candle_timestamp(c).isoformat(),
                    "open": str(c.get("open")),
                    "high": str(c.get("high")),
                    "low": str(c.get("low")),
                    "close": str(c.get("close")),
                    "volume": str(c.get("volume")),
                    "symbol": c.get("symbol"),
                }
                for c in self.candles
            ],
        }
        return ADJUSTMENT_CHAIN_PREFIX + deterministic_hash(payload)


__all__ = [
    "AdjustmentChain",
    "AdjustedSeries",
    "CorporateActionError",
    "FutureActionError",
    "ADJUSTMENT_CHAIN_PREFIX",
]
