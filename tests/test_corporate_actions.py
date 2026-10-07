"""Phase 4A.2 acceptance tests — corporate actions, universe, calendar.

Blueprint 5.11 / 5.12 / 5.13 invariants, each pinned to a named test:

Models (5.12):
- CA-M01  discriminated union of four action types
- CA-M02  announcement > effective raises (PIT chronology)
- CA-M03  deterministic action hashes (ca42.), cross-process stable
- CA-M04  split ratio validation (positive, non-degenerate)
- CA-M05  symbol change must map to a different symbol
- CA-M06  delisting requires a reason

Adjustment chain (5.12):
- CA-C01  2:1 split divides pre-split prices, multiplies volume
- CA-C02  dividend subtracts from pre-ex-date prices
- CA-C03  original candles never mutated; original hash pinned
- CA-C04  future-announced action raises FutureActionError (no look-ahead)
- CA-C05  duplicate action_id rejected
- CA-C06  cross-symbol action rejected
- CA-C07  delisting excludes post-delist candles with audit records
- CA-C08  adjusted hash deterministic (same inputs -> same hash)
- CA-C09  symbol change relabels only post-change candles

Universe (5.11):
- CA-U01  PIT constituents: delisted-in-2020 stock visible at 2019
          (survivorship-bias freedom)
- CA-U02  late announcement invisible in the past (no retrospective
          knowledge)
- CA-U03  snapshot hash deterministic and process-stable (uni42.)
- CA-U04  duplicate event keys rejected
- CA-U05  add+remove+re-add lifecycle correct

Calendar (5.13):
- CA-L01  holidays and weekends excluded from trading days
- CA-L02  next/previous trading day skip holidays
- CA-L03  session phase classification (UTC normalization)
- CA-L04  session_utc_bounds raise on non-trading day (fail closed)
- CA-L05  calendar hash deterministic (cal42.); CalendarRef round-trip
- CA-L06  periods_per_year = trading_days_per_year * bars_per_day
- CA-L07  invalid IANA timezone rejected
"""

import subprocess
import sys
from datetime import date, datetime, time, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.actions import (
    CorporateActionType,
    SplitAction,
    DividendAction,
    SymbolChangeAction,
    DelistingAction,
    AdjustmentChain,
    AdjustedSeries,
    CorporateActionError,
    FutureActionError,
    MembershipEventType,
    UniverseMembershipEvent,
    PointInTimeUniverse,
    TradingCalendar,
    SessionPhase,
    CORPORATE_ACTION_PREFIX,
    ADJUSTMENT_CHAIN_PREFIX,
    UNIVERSE_PREFIX,
    CALENDAR_PREFIX,
)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def make_split(action_id="split-1", announced=None, effective=None, n="2", d="1"):
    return SplitAction(
        action_id=action_id,
        symbol="AAPL",
        announcement_time=announced or utc(2020, 8, 25),
        effective_time=effective or utc(2020, 8, 31),
        ratio_numerator=Decimal(n),
        ratio_denominator=Decimal(d),
    )


def make_candle(ts, o, h, l, c, v, symbol="AAPL"):
    return {
        "timestamp": ts,
        "open": Decimal(o),
        "high": Decimal(h),
        "low": Decimal(l),
        "close": Decimal(c),
        "volume": Decimal(v),
        "symbol": symbol,
    }


# ======================================================================
# Models (5.12)
# ======================================================================

class TestCorporateActionModels:

    def test_ca_m01_discriminated_union(self):
        """CA-M01: all four action types instantiate with distinct tags."""
        split = make_split()
        div = DividendAction(
            action_id="div-1", symbol="AAPL",
            announcement_time=utc(2020, 9, 1), effective_time=utc(2020, 9, 10),
            amount=Decimal("0.22"), currency="USD",
        )
        rename = SymbolChangeAction(
            action_id="sym-1", symbol="OLD",
            announcement_time=utc(2020, 1, 1), effective_time=utc(2020, 2, 1),
            new_symbol="NEW",
        )
        delist = DelistingAction(
            action_id="dl-1", symbol="OLD",
            announcement_time=utc(2020, 5, 1), effective_time=utc(2020, 6, 1),
            reason="merger",
        )
        assert split.action_type is CorporateActionType.SPLIT
        assert div.action_type is CorporateActionType.DIVIDEND
        assert rename.action_type is CorporateActionType.SYMBOL_CHANGE
        assert delist.action_type is CorporateActionType.DELISTING

    def test_ca_m02_announcement_after_effective_raises(self):
        """CA-M02: PIT chronology violation fails closed."""
        with pytest.raises(ValueError, match="PIT violation"):
            SplitAction(
                action_id="bad", symbol="AAPL",
                announcement_time=utc(2020, 9, 5),
                effective_time=utc(2020, 8, 31),
                ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1"),
            )

    def test_ca_m03_hash_deterministic_and_prefixed(self):
        """CA-M03: ca42. prefix, 70 chars, stable across instances."""
        a, b = make_split(), make_split()
        assert a.action_hash == b.action_hash
        assert a.action_hash.startswith(CORPORATE_ACTION_PREFIX)
        assert len(a.action_hash) == 69  # 5-char prefix + 64 hex (SPEC-DEF-01 convention)
        # Different announced time -> different hash
        c = make_split(announced=utc(2020, 8, 26))
        assert a.action_hash != c.action_hash

    def test_ca_m03b_cross_process_hash_stability(self):
        """CA-M03b: hash stable across OS processes (no ambient state)."""
        code = (
            "from datetime import datetime, UTC; from decimal import Decimal;"
            "from data_engine.actions import SplitAction;"
            "a = SplitAction(action_id='split-1', symbol='AAPL',"
            "announcement_time=datetime(2020,8,25,tzinfo=UTC),"
            "effective_time=datetime(2020,8,31,tzinfo=UTC),"
            "ratio_numerator=Decimal('2'), ratio_denominator=Decimal('1'));"
            "print(a.action_hash)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            cwd=".", timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == make_split().action_hash

    def test_ca_m04_split_ratio_validation(self):
        """CA-M04: zero/negative/equal ratio parts rejected."""
        with pytest.raises(ValueError):
            make_split(n="0")
        with pytest.raises(ValueError):
            make_split(n="-2")
        with pytest.raises(ValueError):
            make_split(n="3", d="3")

    def test_ca_m05_symbol_change_distinct(self):
        with pytest.raises(ValueError, match="different symbol"):
            SymbolChangeAction(
                action_id="x", symbol="SAME",
                announcement_time=utc(2020, 1, 1),
                effective_time=utc(2020, 2, 1),
                new_symbol="SAME",
            )

    def test_ca_m06_delisting_requires_reason(self):
        with pytest.raises(ValueError):
            DelistingAction(
                action_id="x", symbol="OLD",
                announcement_time=utc(2020, 5, 1),
                effective_time=utc(2020, 6, 1),
                reason="  ",
            )


# ======================================================================
# AdjustmentChain (5.12)
# ======================================================================

class TestAdjustmentChain:

    def _candles(self):
        return [
            make_candle(utc(2020, 8, 28), "100", "102", "99", "101", "1000"),
            make_candle(utc(2020, 8, 31), "100", "102", "99", "101", "1000"),
            make_candle(utc(2020, 9, 1), "51", "52", "50", "51", "2000"),
        ]

    def test_ca_c01_split_adjustment(self):
        """CA-C01: pre-split prices /2, volumes x2; post-split untouched."""
        chain = AdjustmentChain(symbol="AAPL", actions=(make_split(),))
        out = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        c0, c1, c2 = out.candles
        assert c0["close"] == Decimal("101") / Decimal("2")
        assert c0["volume"] == Decimal("1000") * Decimal("2")
        # Candle ON the effective timestamp is NOT adjusted (strictly
        # before rule: the effective bar is the post-split bar).
        assert c1["close"] == Decimal("101")
        assert c1["volume"] == Decimal("1000")
        assert c2["close"] == Decimal("51")
        assert out.excluded_indices == ()

    def test_ca_c02_dividend_adjustment(self):
        div = DividendAction(
            action_id="div-1", symbol="AAPL",
            announcement_time=utc(2020, 8, 30),
            effective_time=utc(2020, 9, 1),
            amount=Decimal("0.5"),
        )
        chain = AdjustmentChain(symbol="AAPL", actions=(div,))
        out = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        c0 = out.candles[0]
        assert c0["close"] == Decimal("101") - Decimal("0.5")
        assert out.candles[2]["close"] == Decimal("51")  # at/after ex-date

    def test_ca_c03_original_preserved(self):
        """CA-C03: input candles never mutated; original hash recorded."""
        candles = self._candles()
        original_close = candles[0]["close"]
        chain = AdjustmentChain(symbol="AAPL", actions=(make_split(),))
        out = chain.adjust(candles, as_of=utc(2020, 9, 5))
        assert candles[0]["close"] == original_close  # untouched
        assert out.original_series_hash != out.adjusted_series_hash
        # Same original -> same original hash across runs
        out2 = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        assert out.original_series_hash == out2.original_series_hash

    def test_ca_c04_future_action_raises(self):
        """CA-C04: applying an action announced after as_of fails closed."""
        split = make_split()  # announced 2020-08-25
        chain = AdjustmentChain(symbol="AAPL", actions=(split,))
        with pytest.raises(FutureActionError, match="look-ahead"):
            chain.adjust(self._candles(), as_of=utc(2020, 8, 20))

    def test_ca_c05_duplicate_action_rejected(self):
        with pytest.raises(ValueError, match="duplicate action_id"):
            AdjustmentChain(
                symbol="AAPL",
                actions=(make_split(), make_split()),
            )

    def test_ca_c06_cross_symbol_rejected(self):
        other = SplitAction(
            action_id="s-msft", symbol="MSFT",
            announcement_time=utc(2020, 8, 25),
            effective_time=utc(2020, 8, 31),
            ratio_numerator=Decimal("2"), ratio_denominator=Decimal("1"),
        )
        with pytest.raises(ValueError, match="not chain symbol"):
            AdjustmentChain(symbol="AAPL", actions=(other,))

    def test_ca_c07_delisting_excludes_post_delist(self):
        delist = DelistingAction(
            action_id="dl-1", symbol="AAPL",
            announcement_time=utc(2020, 8, 31),
            effective_time=utc(2020, 8, 31, 12),
            reason="delisted voluntarily",
        )
        chain = AdjustmentChain(symbol="AAPL", actions=(delist,))
        out = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        # Only candles strictly after 2020-08-31T12:00 excluded
        assert out.excluded_indices == (2,)
        assert len(out.candles) == 2

    def test_ca_c08_adjusted_hash_deterministic(self):
        chain = AdjustmentChain(symbol="AAPL", actions=(make_split(),))
        out1 = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        out2 = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        assert out1.adjusted_series_hash == out2.adjusted_series_hash
        assert out1.adjusted_series_hash.startswith(ADJUSTMENT_CHAIN_PREFIX)
        # Different as_of -> different hash (as_of is part of identity)
        out3 = chain.adjust(self._candles(), as_of=utc(2020, 10, 5))
        assert out1.adjusted_series_hash != out3.adjusted_series_hash

    def test_ca_c09_symbol_change_relabels_future_only(self):
        rename = SymbolChangeAction(
            action_id="sym-1", symbol="AAPL",
            announcement_time=utc(2020, 8, 30),
            effective_time=utc(2020, 8, 31),
            new_symbol="XLPE",
        )
        chain = AdjustmentChain(symbol="AAPL", actions=(rename,))
        out = chain.adjust(self._candles(), as_of=utc(2020, 9, 5))
        # Candles strictly after effective get the new symbol
        assert out.candles[0].get("symbol") == "AAPL"
        assert out.candles[2].get("symbol") == "XLPE"


# ======================================================================
# PointInTimeUniverse (5.11)
# ======================================================================

class TestPointInTimeUniverse:

    def _events(self):
        return (
            UniverseMembershipEvent(
                event_id="e1", event_type=MembershipEventType.ADD,
                symbol="AAA", announcement_time=utc(2015, 1, 1),
                effective_time=utc(2015, 1, 5),
            ),
            UniverseMembershipEvent(
                event_id="e2", event_type=MembershipEventType.ADD,
                symbol="BBB", announcement_time=utc(2016, 1, 1),
                effective_time=utc(2016, 1, 5),
            ),
            UniverseMembershipEvent(
                event_id="e3", event_type=MembershipEventType.REMOVE,
                symbol="BBB", announcement_time=utc(2020, 6, 25),
                effective_time=utc(2020, 6, 30), reason="delisted",
            ),
        )

    def test_ca_u01_no_survivorship_bias(self):
        """CA-U01: BBB (delisted 2020) is a 2019 constituent."""
        universe = PointInTimeUniverse(universe_id="eq-us", events=self._events())
        assert universe.constituents(utc(2019, 1, 1)) == frozenset({"AAA", "BBB"})
        assert universe.constituents(utc(2021, 1, 1)) == frozenset({"AAA"})

    def test_ca_u02_late_announcement_invisible_in_past(self):
        """CA-U02: a membership change announced in 2020 must not alter
        the universe computed for 2019 (no retrospective knowledge)."""
        late_add = UniverseMembershipEvent(
            event_id="e4", event_type=MembershipEventType.ADD,
            symbol="CCC", announcement_time=utc(2020, 1, 1),
            effective_time=utc(2016, 1, 5),  # retro-effective
        )
        universe = PointInTimeUniverse(
            universe_id="eq-us", events=self._events() + (late_add,)
        )
        assert "CCC" not in universe.constituents(utc(2019, 1, 1))
        assert "CCC" in universe.constituents(utc(2020, 6, 1))

    def test_ca_u03_snapshot_hash_deterministic(self):
        universe = PointInTimeUniverse(universe_id="eq-us", events=self._events())
        s1 = universe.snapshot(utc(2019, 1, 1))
        s2 = universe.snapshot(utc(2019, 1, 1))
        assert s1.universe_hash == s2.universe_hash
        assert s1.universe_hash.startswith(UNIVERSE_PREFIX)
        assert len(s1.universe_hash) == 70  # 6-char prefix + 64 hex
        assert s1.symbols == ("AAA", "BBB")
        assert s1.contains("AAA") and not s1.contains("ZZZ")
        # Different as_of -> different snapshot hash
        s3 = universe.snapshot(utc(2021, 1, 1))
        assert s1.universe_hash != s3.universe_hash

    def test_ca_u04_duplicate_events_rejected(self):
        dup = UniverseMembershipEvent(
            event_id="e1", event_type=MembershipEventType.ADD,
            symbol="AAA", announcement_time=utc(2015, 1, 1),
            effective_time=utc(2015, 1, 5),
        )
        with pytest.raises(ValueError, match="duplicate"):
            PointInTimeUniverse(
                universe_id="eq-us",
                events=self._events() + (dup,),
            )

    def test_ca_u05_readd_lifecycle(self):
        events = (
            UniverseMembershipEvent(
                event_id="a1", event_type=MembershipEventType.ADD,
                symbol="XYZ", announcement_time=utc(2010, 1, 1),
                effective_time=utc(2010, 1, 4),
            ),
            UniverseMembershipEvent(
                event_id="r1", event_type=MembershipEventType.REMOVE,
                symbol="XYZ", announcement_time=utc(2012, 1, 1),
                effective_time=utc(2012, 1, 4),
            ),
            UniverseMembershipEvent(
                event_id="a2", event_type=MembershipEventType.ADD,
                symbol="XYZ", announcement_time=utc(2014, 1, 1),
                effective_time=utc(2014, 1, 4),
            ),
        )
        universe = PointInTimeUniverse(universe_id="u", events=events)
        assert "XYZ" in universe.constituents(utc(2011, 1, 1))
        assert "XYZ" not in universe.constituents(utc(2013, 1, 1))
        assert "XYZ" in universe.constituents(utc(2015, 1, 1))


# ======================================================================
# TradingCalendar (5.13)
# ======================================================================

NYSE_LIKE = TradingCalendar(
    calendar_id="nyse-like",
    calendar_version="2020.1",
    timezone="America/New_York",
    session_weekdays=frozenset({1, 2, 3, 4, 5}),
    holidays=frozenset({
        date(2020, 1, 1), date(2020, 12, 25), date(2020, 11, 26),
    }),
    session_open=time(9, 30),
    session_close=time(16, 0),
    trading_days_per_year=252,
)


class TestTradingCalendar:

    def test_ca_l01_trading_day_logic(self):
        """CA-L01: weekends and holidays are not trading days."""
        assert NYSE_LIKE.is_trading_day(date(2020, 11, 25))  # Wed
        assert not NYSE_LIKE.is_trading_day(date(2020, 11, 26))  # holiday
        assert not NYSE_LIKE.is_trading_day(date(2020, 11, 28))  # Saturday
        assert not NYSE_LIKE.is_trading_day(date(2020, 11, 29))  # Sunday

    def test_ca_l02_next_previous_skip_holidays(self):
        """CA-L02: next trading day after Dec 24 skips Dec 25 holiday."""
        assert NYSE_LIKE.next_trading_day(date(2020, 12, 24)) == date(2020, 12, 28)
        # Friday Nov 27 -> previous is Wed Nov 25 (Thu 26 is holiday)
        assert NYSE_LIKE.previous_trading_day(date(2020, 11, 27)) == date(2020, 11, 25)
        # trading_days_between inclusive
        assert NYSE_LIKE.trading_days_between(date(2020, 11, 23), date(2020, 11, 27)) == 4
        # (Mon 23, Tue 24, Wed 25 trade; Thu 26 holiday; Fri 27 trades)

    def test_ca_l03_session_phase_utc_normalization(self):
        """CA-L03: 10:00 New York == 15:00 UTC is in session; 15:05 UTC
        (10:05 local) too; 22:00 UTC (17:00 local) is after session."""
        in1 = datetime(2020, 11, 25, 15, 0, tzinfo=UTC)
        in2 = datetime(2020, 11, 25, 10, 5, tzinfo=UTC)  # 05:05 local — before
        after = datetime(2020, 11, 25, 22, 0, tzinfo=UTC)
        weekend = datetime(2020, 11, 28, 15, 0, tzinfo=UTC)
        assert NYSE_LIKE.session_phase(in1) is SessionPhase.IN_SESSION
        assert NYSE_LIKE.session_phase(in2) is SessionPhase.BEFORE_SESSION
        assert NYSE_LIKE.session_phase(after) is SessionPhase.AFTER_SESSION
        assert NYSE_LIKE.session_phase(weekend) is SessionPhase.NON_TRADING_DAY
        assert NYSE_LIKE.is_session_open_at(in1)

    def test_ca_l04_session_bounds_fail_closed(self):
        open_utc, close_utc = NYSE_LIKE.session_utc_bounds(date(2020, 11, 25))
        assert open_utc == datetime(2020, 11, 25, 14, 30, tzinfo=UTC)
        assert close_utc == datetime(2020, 11, 25, 21, 0, tzinfo=UTC)
        with pytest.raises(ValueError, match="not a trading day"):
            NYSE_LIKE.session_utc_bounds(date(2020, 11, 26))

    def test_ca_l05_calendar_hash_and_ref(self):
        """CA-L05: cal42. hash deterministic; CalendarRef round-trips."""
        twin = TradingCalendar(
            calendar_id="nyse-like", calendar_version="2020.1",
            timezone="America/New_York",
            session_weekdays=frozenset({1, 2, 3, 4, 5}),
            holidays=frozenset({
                date(2020, 1, 1), date(2020, 12, 25), date(2020, 11, 26),
            }),
            session_open=time(9, 30), session_close=time(16, 0),
            trading_days_per_year=252,
        )
        assert NYSE_LIKE.calendar_hash == twin.calendar_hash
        assert NYSE_LIKE.calendar_hash.startswith(CALENDAR_PREFIX)
        ref = NYSE_LIKE.to_calendar_ref()
        assert ref.calendar_id == "nyse-like"
        assert ref.calendar_version == "2020.1"

    def test_ca_l06_periods_per_year(self):
        assert NYSE_LIKE.periods_per_year(1) == 252
        assert NYSE_LIKE.periods_per_year(24) == 252 * 24
        with pytest.raises(ValueError):
            NYSE_LIKE.periods_per_year(0)

    def test_ca_l07_invalid_timezone_rejected(self):
        with pytest.raises(ValueError, match="IANA"):
            TradingCalendar(
                calendar_id="x", calendar_version="1",
                timezone="Not/AZone",
            )

    def test_ca_l08_degenerate_session_rejected(self):
        with pytest.raises(ValueError):
            TradingCalendar(
                calendar_id="x", calendar_version="1",
                session_open=time(16, 0), session_close=time(9, 30),
            )
