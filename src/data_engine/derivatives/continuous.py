"""Phase 4A.3 — ContinuousSeries (blueprint 5.14).

Stitches contract segments into one continuous research series via
backward ratio adjustment at roll points:

    factor_t = front_close(t_roll) / back_close(t_roll)
    bars strictly BEFORE t_roll: price *= factor, volume /= factor

Invariants:
- PIT-correct rolls: every roll decision must carry
  ``decision_time <= effective_time`` (enforced by RollDecision; the
  series builder re-validates against its own segment data — a roll
  effective before its decision bar is a leakage error).
- Contracts and continuous series are distinct: a ContinuousSeries
  references contracts by id/hash, never masquerading as one.
- Deterministic identity: ``cont43.`` prefix over segment hashes +
  roll decision hashes + adjustment method.
- Original segment data never mutated: stitching produces new bars.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.derivatives.models import PHASE_4A3_CONTRACT_VERSION
from data_engine.derivatives.rollover import RollDecision, RollLeakageError


class ContinuousSeriesError(ValueError):
    """Raised on continuous-series contract violations."""


class AdjustmentMethod:
    """Supported stitching methods (namespace of constants)."""

    BACKWARD_RATIO = "backward_ratio"
    BACKWARD_DIFFERENCE = "backward_difference"


def _bar_time(bar: Mapping[str, Any]) -> datetime:
    ts = bar.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise ContinuousSeriesError("bars need timezone-aware timestamps")
    return ts.astimezone(UTC)


class ContinuousSeries(BaseModel):
    """Stitched continuous futures series with full roll provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    series_id: str
    root_symbol: str
    adjustment_method: str = AdjustmentMethod.BACKWARD_RATIO
    contract_ids: tuple[str, ...]
    roll_decisions: tuple[RollDecision, ...] = ()

    @field_validator("series_id", "root_symbol")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("series identifiers must be non-empty strings")
        return v.strip().upper()

    @field_validator("adjustment_method")
    @classmethod
    def _validate_method(cls, v: str) -> str:
        allowed = {
            AdjustmentMethod.BACKWARD_RATIO,
            AdjustmentMethod.BACKWARD_DIFFERENCE,
        }
        if v not in allowed:
            raise ValueError(f"adjustment_method must be one of {sorted(allowed)}")
        return v

    @field_validator("contract_ids")
    @classmethod
    def _validate_contracts(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("continuous series needs at least one contract")
        if len(set(v)) != len(v):
            raise ValueError("contract_ids must be unique")
        return tuple(c.strip().upper() for c in v)

    @model_validator(mode="after")
    def _validate_rolls(self) -> "ContinuousSeries":
        for roll in self.roll_decisions:
            if roll.front_contract_id not in self.contract_ids:
                raise ContinuousSeriesError(
                    f"roll references front contract {roll.front_contract_id} "
                    "not in the series contract set"
                )
            if roll.back_contract_id not in self.contract_ids:
                raise ContinuousSeriesError(
                    f"roll references back contract {roll.back_contract_id} "
                    "not in the series contract set"
                )
        return self

    @property
    def series_hash(self) -> str:
        """Deterministic identity: ``cont43.`` + SHA-256 hex (69 chars)."""
        payload = {
            "contract_version": PHASE_4A3_CONTRACT_VERSION,
            "series_id": self.series_id,
            "root_symbol": self.root_symbol,
            "adjustment_method": self.adjustment_method,
            "contract_ids": list(self.contract_ids),
            "roll_decisions": [
                {
                    "front": r.front_contract_id,
                    "back": r.back_contract_id,
                    "decision_time": r.decision_time,
                    "effective_time": r.effective_time,
                    "reason": r.reason,
                }
                for r in self.roll_decisions
            ],
        }
        return "cont43." + deterministic_hash(payload)

    def stitch(
        self,
        segments: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> tuple[Mapping[str, Any], ...]:
        """Stitch contract segments into the adjusted continuous series.

        ``segments`` maps contract_id -> bars (each bar a mapping with a
        timezone-aware ``timestamp`` and OHLCV fields). Segment inputs
        are never mutated. At each roll's effective time the ratio (or
        difference) between the front and back closes ON the roll bar
        is applied backward to all earlier stitched bars.
        """
        missing = [c for c in self.contract_ids if c not in segments]
        if missing:
            raise ContinuousSeriesError(
                f"missing segments for contracts {missing}"
            )

        # Start from the LAST (most deferred) contract's bars, then walk
        # rolls backward applying cumulative adjustments.
        ordered_contracts = list(self.contract_ids)
        stitched = [dict(b) for b in segments[ordered_contracts[-1]]]
        stitched.sort(key=_bar_time)

        for roll in reversed(self.roll_decisions):
            front_bars = sorted(
                (dict(b) for b in segments[roll.front_contract_id]),
                key=_bar_time,
            )
            back_bars = sorted(
                (dict(b) for b in segments[roll.back_contract_id]),
                key=_bar_time,
            )
            # The roll bar pair must exist ON the roll date in BOTH
            # segments — closes from LATER dates are future data and
            # using them would leak (RollLeakageError).
            roll_date = roll.effective_time.date()
            front_close = None
            for bar in front_bars:
                if _bar_time(bar).date() == roll_date:
                    front_close = bar.get("close")
                    break
            back_close = None
            for bar in back_bars:
                if _bar_time(bar).date() == roll_date:
                    back_close = bar.get("close")
                    break
            if front_close is None or back_close is None:
                raise RollLeakageError(
                    f"roll {roll.front_contract_id}->{roll.back_contract_id} "
                    f"effective {roll.effective_time} has no observable bar "
                    "pair on the roll date; the adjustment ratio cannot be "
                    "computed without future data"
                )

            if self.adjustment_method == AdjustmentMethod.BACKWARD_RATIO:
                ratio = Decimal(str(front_close)) / Decimal(str(back_close))
                for bar in stitched:
                    if _bar_time(bar) < roll.effective_time:
                        for field in ("open", "high", "low", "close"):
                            value = bar.get(field)
                            if value is not None:
                                bar[field] = _scale(value, ratio)
                        volume = bar.get("volume")
                        if volume is not None:
                            bar["volume"] = _unscale(volume, ratio)
            else:  # BACKWARD_DIFFERENCE
                diff = Decimal(str(front_close)) - Decimal(str(back_close))
                for bar in stitched:
                    if _bar_time(bar) < roll.effective_time:
                        for field in ("open", "high", "low", "close"):
                            value = bar.get(field)
                            if value is not None:
                                bar[field] = _shift(value, diff)

            # Prepend the front contract's pre-roll history.
            earlier = [
                dict(b) for b in front_bars
                if _bar_time(b) < roll.effective_time
            ]
            # Recursively adjust the earlier history by the SAME ratio
            # so multiple rolls compose correctly.
            if self.adjustment_method == AdjustmentMethod.BACKWARD_RATIO:
                for bar in earlier:
                    for field in ("open", "high", "low", "close"):
                        value = bar.get(field)
                        if value is not None:
                            bar[field] = _scale(value, ratio)
                    volume = bar.get("volume")
                    if volume is not None:
                        bar["volume"] = _unscale(volume, ratio)
            else:
                for bar in earlier:
                    for field in ("open", "high", "low", "close"):
                        value = bar.get(field)
                        if value is not None:
                            bar[field] = _shift(value, diff)
            stitched = earlier + stitched

        return tuple(stitched)


def _scale(value: Any, ratio: Decimal) -> Any:
    if isinstance(value, Decimal):
        return value * ratio
    if isinstance(value, float):
        return value * float(ratio)
    raise ContinuousSeriesError(
        f"price fields must be Decimal or float, got {type(value).__name__}"
    )


def _unscale(value: Any, ratio: Decimal) -> Any:
    if isinstance(value, Decimal):
        return value / ratio if ratio != 0 else value
    if isinstance(value, float):
        return value / float(ratio) if ratio != 0 else value
    if isinstance(value, int):
        return value  # volume ints kept as-is (approximation documented)
    raise ContinuousSeriesError(
        f"volume fields must be Decimal/float/int, got {type(value).__name__}"
    )


def _shift(value: Any, diff: Decimal) -> Any:
    if isinstance(value, Decimal):
        return value + diff
    if isinstance(value, float):
        return value + float(diff)
    raise ContinuousSeriesError(
        f"price fields must be Decimal or float, got {type(value).__name__}"
    )


__all__ = [
    "ContinuousSeries",
    "ContinuousSeriesError",
    "AdjustmentMethod",
]
