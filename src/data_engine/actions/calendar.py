"""Phase 4A.2 — TradingCalendar: full calendar infrastructure (blueprint 5.13).

4A.1 deliberately shipped only ``CalendarRef`` — an identity REFERENCE
with zero computation (INV-06 scope guard). This module is the
authorized 4A.2 expansion: the full holiday engine, session
determination, and trading-day arithmetic.

Components:
- ``TradingCalendar``: versioned calendar (session weekdays, holidays,
  session open/close times, IANA timezone). Deterministic answers for
  is_trading_day / next_trading_day / previous_trading_day /
  trading_days_between / session windows. Produces ``cal42.`` identity
  hashes and converts to the 4A.1 ``CalendarRef`` for identity use.
- ``periods_per_year``: calendar-derived annualization factors —
  trading-days-per-year times bars-per-day. This is the calendar-owned
  successor to frozen Phase 3 ``metrics.periods_per_year`` (the frozen
  dict is NOT touched; it remains valid for its 365-day forex case).

Invariants:
- Calendar version participates in identity (hash + CalendarRef).
- UTC normalization for all datetime comparisons.
- No wall clock: every method is a pure function of inputs.
"""

from datetime import date, datetime, time, timedelta, UTC
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.primitives import CalendarRef
from data_engine.actions.models import PHASE_4A2_CONTRACT_VERSION

#: Identity prefix for calendar hashes.
CALENDAR_PREFIX = "cal42."

#: Default trading days per year (252 — the standard equity convention).
DEFAULT_TRADING_DAYS_PER_YEAR = 252


class SessionPhase(str, Enum):
    """Phase of a timestamp relative to a trading session."""

    BEFORE_SESSION = "before_session"
    IN_SESSION = "in_session"
    AFTER_SESSION = "after_session"
    NON_TRADING_DAY = "non_trading_day"


def _validate_weekday(value: int) -> int:
    """Validate an ISO weekday: 1=Monday .. 7=Sunday (date.isoweekday)."""
    if not isinstance(value, int) or not 1 <= value <= 7:
        raise ValueError(
            "session weekday must be an int in 1..7 (ISO: 1=Monday..7=Sunday)"
        )
    return value


class TradingCalendar(BaseModel):
    """Versioned trading calendar with holiday and session engine.

    Weekdays use the ISO convention (``date.isoweekday()``):
    1=Monday, 2=Tuesday, ..., 5=Friday, 6=Saturday, 7=Sunday.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    calendar_id: str
    calendar_version: str
    timezone: str = "UTC"
    session_weekdays: frozenset[int] = frozenset({1, 2, 3, 4, 5})
    holidays: frozenset[date] = frozenset()
    session_open: time = time(0, 0)
    session_close: time = time(23, 59, 59)
    trading_days_per_year: int = DEFAULT_TRADING_DAYS_PER_YEAR

    @field_validator("calendar_id", "calendar_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("calendar_id/version must be non-empty strings")
        return v.strip()

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError(
                f"timezone {v!r} is not a valid IANA timezone"
            )
        return v

    @field_validator("session_weekdays")
    @classmethod
    def _validate_weekdays(cls, v) -> frozenset[int]:
        if not v:
            raise ValueError("session_weekdays must not be empty")
        return frozenset(_validate_weekday(d) for d in v)

    @field_validator("holidays")
    @classmethod
    def _validate_holidays(cls, v) -> frozenset[date]:
        return frozenset(v)

    @field_validator("trading_days_per_year")
    @classmethod
    def _validate_tdays(cls, v: int) -> int:
        if not isinstance(v, int) or not 1 <= v <= 366:
            raise ValueError("trading_days_per_year must be in 1..366")
        return v

    @model_validator(mode="after")
    def _validate_session_window(self) -> "TradingCalendar":
        if self.session_open >= self.session_close:
            raise ValueError(
                "session_open must be strictly before session_close"
            )
        # Cross-midnight sessions are a venue modeling decision this
        # contract intentionally does not support (fail closed).
        if self.session_close <= self.session_open:
            raise ValueError("session window must be non-degenerate")
        return self

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    @property
    def calendar_hash(self) -> str:
        """Deterministic calendar identity: ``cal42.`` + SHA-256 hex."""
        payload = {
            "contract_version": PHASE_4A2_CONTRACT_VERSION,
            "calendar_id": self.calendar_id,
            "calendar_version": self.calendar_version,
            "timezone": self.timezone,
            "session_weekdays": sorted(self.session_weekdays),
            "holidays": [d.isoformat() for d in sorted(self.holidays)],
            "session_open": self.session_open.isoformat(),
            "session_close": self.session_close.isoformat(),
            "trading_days_per_year": self.trading_days_per_year,
        }
        return CALENDAR_PREFIX + deterministic_hash(payload)

    def to_calendar_ref(self) -> CalendarRef:
        """Convert to the 4A.1 identity reference (no computation leaks)."""
        return CalendarRef(
            calendar_id=self.calendar_id,
            calendar_version=self.calendar_version,
        )

    # ------------------------------------------------------------------
    # Trading-day engine
    # ------------------------------------------------------------------
    def is_trading_day(self, day: date) -> bool:
        """True if ``day`` is a session weekday and not a holiday."""
        if day is None:
            raise ValueError("day must be a date")
        if day.isoweekday() not in self.session_weekdays:
            return False
        return day not in self.holidays

    def next_trading_day(self, day: date) -> date:
        """First trading day strictly after ``day`` (bounded scan)."""
        if day is None:
            raise ValueError("day must be a date")
        candidate = day + timedelta(days=1)
        for _ in range(4000):  # > 10 years of calendar scanning bound
            if self.is_trading_day(candidate):
                return candidate
            candidate += timedelta(days=1)
        raise ValueError(
            "no trading day found within scan bound — calendar is "
            "over-constrained (holidays or weekdays exclude everything)"
        )

    def previous_trading_day(self, day: date) -> date:
        """First trading day strictly before ``day`` (bounded scan)."""
        if day is None:
            raise ValueError("day must be a date")
        candidate = day - timedelta(days=1)
        for _ in range(4000):
            if self.is_trading_day(candidate):
                return candidate
            candidate -= timedelta(days=1)
        raise ValueError(
            "no trading day found within scan bound — calendar is "
            "over-constrained"
        )

    def trading_days_between(self, start: date, end: date) -> int:
        """Count trading days in the INCLUSIVE range [start, end]."""
        if start is None or end is None:
            raise ValueError("start/end must be dates")
        if end < start:
            raise ValueError("end must be >= start")
        count = 0
        cursor = start
        while cursor <= end:
            if self.is_trading_day(cursor):
                count += 1
            cursor += timedelta(days=1)
        return count

    # ------------------------------------------------------------------
    # Session engine
    # ------------------------------------------------------------------
    def _tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def session_phase(self, at: datetime) -> SessionPhase:
        """Classify ``at`` relative to the session on its calendar day."""
        if at is None or at.tzinfo is None:
            raise ValueError("at must be a timezone-aware datetime")
        local = at.astimezone(self._tz())
        local_date = local.date()
        if not self.is_trading_day(local_date):
            return SessionPhase.NON_TRADING_DAY
        local_time = local.time()
        if local_time < self.session_open:
            return SessionPhase.BEFORE_SESSION
        if local_time > self.session_close:
            return SessionPhase.AFTER_SESSION
        return SessionPhase.IN_SESSION

    def is_session_open_at(self, at: datetime) -> bool:
        """True iff ``at`` falls inside a trading session."""
        return self.session_phase(at) is SessionPhase.IN_SESSION

    def session_utc_bounds(self, day: date) -> tuple[datetime, datetime]:
        """UTC open/close boundaries of the session on ``day``.

        Raises ValueError if ``day`` is not a trading day (there is no
        session to bound — failing closed beats guessing).
        """
        if not self.is_trading_day(day):
            raise ValueError(f"{day.isoformat()} is not a trading day")
        tz = self._tz()
        open_dt = datetime.combine(day, self.session_open, tzinfo=tz)
        close_dt = datetime.combine(day, self.session_close, tzinfo=tz)
        return open_dt.astimezone(UTC), close_dt.astimezone(UTC)

    # ------------------------------------------------------------------
    # Annualization
    # ------------------------------------------------------------------
    def periods_per_year(self, bars_per_day: int) -> int:
        """Annualization factor: trading_days_per_year * bars_per_day.

        This is the calendar-owned successor of the frozen Phase 3
        ``metrics.periods_per_year`` static dict (which stays untouched
        and remains correct for the 365-day forex case it froze).
        """
        if not isinstance(bars_per_day, int) or bars_per_day <= 0:
            raise ValueError("bars_per_day must be a positive int")
        return self.trading_days_per_year * bars_per_day


__all__ = [
    "TradingCalendar",
    "SessionPhase",
    "CALENDAR_PREFIX",
    "DEFAULT_TRADING_DAYS_PER_YEAR",
]
