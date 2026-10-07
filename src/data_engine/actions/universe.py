"""Phase 4A.2 — PointInTimeUniverse (blueprint 5.11).

Survivorship-bias-free instrument universe:

- Membership is a sequence of ADD/REMOVE events with announcement and
  effective times (PIT correctness — the world knew about the change
  only after ``announcement_time``).
- ``constituents(as_of)`` returns the instruments active at ``as_of``
  using ONLY events known at that time. A stock delisted in 2020 STILL
  appears in ``constituents(as_of=2019)`` — that is the whole point.
- Universe snapshots are date-specific and hash-stable: the same event
  history and the same ``as_of`` always produce the same ``uni42.`` hash,
  in any process (no wall clock, no RNG, no environment).
- Universe manipulation is detectable: events are frozen, duplicate
  keys are rejected, and the snapshot hash covers every event hash.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.actions.models import PHASE_4A2_CONTRACT_VERSION

#: Identity prefix for universe snapshot hashes.
UNIVERSE_PREFIX = "uni42."


class MembershipEventType(str, Enum):
    """Universe membership change kinds."""

    ADD = "add"
    REMOVE = "remove"


class UniverseMembershipEvent(BaseModel):
    """One membership change, PIT-correct.

    ``announcement_time`` is when the change became public knowledge;
    ``effective_time`` is when membership actually changed. Retro-effective
    events (effective BEFORE announcement — corrections, index
    reconstitutions) are permitted: PIT visibility is governed by
    ``is_known_at``, so a retro-effective event is invisible until its
    announcement. A member is active at ``as_of`` iff some ADD for it is
    BOTH announced and effective <= ``as_of``, and no REMOVE likewise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    event_type: MembershipEventType
    symbol: str
    announcement_time: datetime
    effective_time: datetime
    reason: Optional[str] = None

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("event_id must be a non-empty string")
        return v.strip()

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("symbol must be a non-empty string")
        normalized = v.strip().upper()
        if any(ch.isspace() for ch in normalized):
            raise ValueError("symbol must not contain whitespace")
        return normalized

    @field_validator("announcement_time", "effective_time")
    @classmethod
    def _validate_utc(cls, v: datetime, info) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError(
                f"{info.field_name} must be a timezone-aware datetime"
            )
        return v.astimezone(UTC)

    @property
    def event_hash(self) -> str:
        payload = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "announcement_time": self.announcement_time,
            "effective_time": self.effective_time,
            "reason": self.reason,
        }
        return deterministic_hash(payload)

    def is_known_at(self, as_of: datetime) -> bool:
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return self.announcement_time <= as_of.astimezone(UTC)


class UniverseSnapshot(BaseModel):
    """Immutable date-specific universe composition with identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    symbols: tuple[str, ...]
    universe_hash: str
    event_hashes_covered: tuple[str, ...]

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(v)) != len(v):
            raise ValueError("snapshot symbols must be unique")
        return tuple(sorted(v))

    def contains(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.symbols

    def __len__(self) -> int:
        return len(self.symbols)


class PointInTimeUniverse(BaseModel):
    """Event-sourced universe: membership derived, never stored stale.

    Invariant (blueprint 5.11): "Universe is date-specific; no
    survivorship bias; PIT-correct composition."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_id: str
    events: tuple[UniverseMembershipEvent, ...] = ()

    @field_validator("universe_id")
    @classmethod
    def _validate_universe_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("universe_id must be a non-empty string")
        return v.strip()

    @model_validator(mode="after")
    def _validate_events(self) -> "PointInTimeUniverse":
        seen_ids: set[str] = set()
        seen_keys: set[tuple[str, str, datetime]] = set()
        for event in self.events:
            if event.event_id in seen_ids:
                raise ValueError(
                    f"duplicate universe event_id {event.event_id!r}"
                )
            seen_ids.add(event.event_id)
            key = (event.symbol, event.event_type.value, event.effective_time)
            if key in seen_keys:
                raise ValueError(
                    f"duplicate {event.event_type.value} event for "
                    f"{event.symbol} at {event.effective_time}"
                )
            seen_keys.add(key)
        return self

    def known_at(self, as_of: datetime) -> tuple[UniverseMembershipEvent, ...]:
        """Events publicly known at ``as_of``."""
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        return tuple(e for e in self.events if e.announcement_time <= cutoff)

    def constituents(self, as_of: datetime) -> frozenset[str]:
        """Active symbols at ``as_of`` (PIT-correct, no survivorship bias).

        Uses only events BOTH announced and effective by ``as_of``.
        Events announced later are invisible — asking about the past
        cannot use the future's knowledge (late announcements included).
        """
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        active: dict[str, datetime] = {}
        for event in self.events:
            if event.announcement_time > cutoff or event.effective_time > cutoff:
                continue
            if event.event_type is MembershipEventType.ADD:
                if event.symbol not in active or event.effective_time >= active[event.symbol]:
                    active[event.symbol] = event.effective_time
            else:  # REMOVE
                if event.symbol in active and event.effective_time >= active[event.symbol]:
                    del active[event.symbol]
        return frozenset(active.keys())

    def snapshot(self, as_of: datetime) -> UniverseSnapshot:
        """Deterministic, hash-stable universe snapshot at ``as_of``."""
        if as_of is None or as_of.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        members = self.constituents(cutoff)
        covered = [e.event_hash for e in self.known_at(cutoff)]
        payload = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "universe_id": self.universe_id,
            "as_of": cutoff,
            "symbols": sorted(members),
            "event_hashes_covered": covered,
        }
        return UniverseSnapshot(
            as_of=cutoff,
            symbols=tuple(sorted(members)),
            universe_hash=UNIVERSE_PREFIX + deterministic_hash(payload),
            event_hashes_covered=tuple(covered),
        )


__all__ = [
    "MembershipEventType",
    "UniverseMembershipEvent",
    "UniverseSnapshot",
    "PointInTimeUniverse",
    "UNIVERSE_PREFIX",
]
