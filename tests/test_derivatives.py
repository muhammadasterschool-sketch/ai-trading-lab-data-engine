"""Phase 4A.3 acceptance tests — futures, rollover, continuous series.

Blueprint 5.14 invariants:

- FU-M01  contract validation (expiry/delivery consistency, positive
          tick/multiplier) and fut43. deterministic identity
- FU-M02  date sanity guards (first_notice <= last_trading <= expiry)
- FU-R01  calendar policy rolls N days before expiry
- FU-R02  volume-cross policy detects the roll on the cross bar
- FU-R03  RollDecision leakage guard: decision after effect raises
- FU-R04  no roll detected -> None (fail-open only in the absence of
          a signal, never on contract violation)
- FU-C01  backward-ratio stitching adjusts pre-roll history exactly
- FU-C02  stitched series never mutates segment inputs
- FU-C03  series hash deterministic (cont43.), distinct from contract
          hashes (contracts and series are distinct entities)
- FU-C04  roll referencing an unknown contract rejected
- FU-C05  missing observable roll bar pair raises (no future data)
"""

from datetime import date, datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.derivatives import (
    FuturesContract,
    RolloverPolicy,
    RolloverPolicyType,
    RollDecision,
    RollLeakageError,
    roll_detection,
    ContinuousSeries,
    ContinuousSeriesError,
    AdjustmentMethod,
    FUTURES_PREFIX,
)


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def bar(ts, o, h, l, c, v, oi=None):
    out = {
        "timestamp": ts, "open": Decimal(o), "high": Decimal(h),
        "low": Decimal(l), "close": Decimal(c), "volume": Decimal(v),
    }
    if oi is not None:
        out["open_interest"] = Decimal(oi)
    return out


def make_contract(contract_id="CLZ2020", month=12, year=2020):
    return FuturesContract(
        contract_id=contract_id,
        root_symbol="CL",
        expiry=date(year, month, 15),
        tick_size=Decimal("0.01"),
        multiplier=Decimal("1000"),
        delivery_month=month,
        delivery_year=year,
        first_notice=date(year, month, 1),
        last_trading=date(year, month, 14),
    )


# ======================================================================

class TestFuturesContract:

    def test_fu_m01_validation_and_identity(self):
        """FU-M01: model validates; fut43. hash deterministic."""
        c1 = make_contract()
        c2 = make_contract()
        assert c1.contract_hash == c2.contract_hash
        assert c1.contract_hash.startswith(FUTURES_PREFIX)
        assert len(c1.contract_hash) == 70  # 6-char prefix + 64 hex
        c3 = make_contract(contract_id="CLZ2021", year=2021)
        assert c1.contract_hash != c3.contract_hash

    def test_fu_m01b_validation_rejects_bad_specs(self):
        with pytest.raises(ValueError, match="delivery_month"):
            FuturesContract(
                contract_id="X", root_symbol="CL",
                expiry=date(2020, 12, 15),
                tick_size=Decimal("0.01"), multiplier=Decimal("1000"),
                delivery_month=11, delivery_year=2020,
            )
        with pytest.raises(ValueError):
            FuturesContract(
                contract_id="X", root_symbol="CL",
                expiry=date(2020, 12, 15),
                tick_size=Decimal("0"), multiplier=Decimal("1000"),
                delivery_month=12, delivery_year=2020,
            )

    def test_fu_m02_date_sanity(self):
        with pytest.raises(ValueError, match="first_notice"):
            FuturesContract(
                contract_id="X", root_symbol="CL",
                expiry=date(2020, 12, 15),
                tick_size=Decimal("0.01"), multiplier=Decimal("1000"),
                delivery_month=12, delivery_year=2020,
                first_notice=date(2020, 12, 20),
            )


class TestRollover:

    def test_fu_r01_calendar_policy(self):
        """FU-R01: roll decided 5 days before expiry (Dec 15 -> Dec 10)."""
        policy = RolloverPolicy(
            policy_type=RolloverPolicyType.CALENDAR_DAYS, parameter=5
        )
        bars = [bar(utc(2020, 12, d), "50", "51", "49", "50", "100") for d in range(1, 16)]
        decision = roll_detection(
            policy, front_bars=bars, back_bars=[],
            front_expiry=date(2020, 12, 15),
            front_contract_id="CLZ2020", back_contract_id="CLF2021",
        )
        assert decision is not None
        assert decision.decision_time.date() == date(2020, 12, 10)
        assert decision.decision_time <= decision.effective_time
        assert decision.front_contract_id == "CLZ2020"
        assert decision.back_contract_id == "CLF2021"

    def test_fu_r02_volume_cross(self):
        """FU-R02: roll on the bar where back volume exceeds front."""
        policy = RolloverPolicy(policy_type=RolloverPolicyType.VOLUME_CROSS)
        front = [
            bar(utc(2020, 12, 8), "50", "51", "49", "50", "5000"),
            bar(utc(2020, 12, 9), "50", "51", "49", "50", "3000"),
            bar(utc(2020, 12, 10), "50", "51", "49", "50", "1000"),
        ]
        back = [
            bar(utc(2020, 12, 8), "51", "52", "50", "51", "1000"),
            bar(utc(2020, 12, 9), "51", "52", "50", "51", "2500"),
            bar(utc(2020, 12, 10), "51", "52", "50", "51", "4000"),
        ]
        decision = roll_detection(policy, front, back)
        assert decision is not None
        assert decision.decision_time == utc(2020, 12, 10)  # cross bar
        # Decision bar existed in BOTH series (observable when made)
        assert decision.decision_time == decision.effective_time

    def test_fu_r02b_no_cross_no_roll(self):
        policy = RolloverPolicy(policy_type=RolloverPolicyType.VOLUME_CROSS)
        front = [bar(utc(2020, 12, 8), "50", "51", "49", "50", "5000")]
        back = [bar(utc(2020, 12, 8), "51", "52", "50", "51", "1000")]
        assert roll_detection(policy, front, back) is None

    def test_fu_r03_leakage_guard(self):
        """FU-R03: decision after effect is structurally rejected."""
        with pytest.raises(ValueError, match="precedes"):
            RollDecision(
                front_contract_id="A", back_contract_id="B",
                decision_time=utc(2020, 12, 11),
                effective_time=utc(2020, 12, 10),
                reason="test",
            )
        with pytest.raises(ValueError, match="DIFFERENT"):
            RollDecision(
                front_contract_id="A", back_contract_id="A",
                decision_time=utc(2020, 12, 10),
                effective_time=utc(2020, 12, 10),
                reason="test",
            )

    def test_fu_r04_calendar_needs_expiry(self):
        policy = RolloverPolicy(
            policy_type=RolloverPolicyType.CALENDAR_DAYS, parameter=5
        )
        with pytest.raises(ValueError, match="front_expiry"):
            roll_detection(policy, front_bars=[], back_bars=[])


class TestContinuousSeries:

    def _roll(self):
        return RollDecision(
            front_contract_id="CLZ2020", back_contract_id="CLF2021",
            decision_time=utc(2020, 12, 10),
            effective_time=utc(2020, 12, 10),
            reason="volume cross",
        )

    def _segments(self):
        front = [
            bar(utc(2020, 12, 8), "50", "51", "49", "50", "1000"),
            bar(utc(2020, 12, 9), "50", "51", "49", "50", "900"),
        ]
        back = [
            # The roll bar pair: front close 50, back close 55 -> ratio 10/11
            bar(utc(2020, 12, 10), "55", "56", "54", "55", "4000"),
            bar(utc(2020, 12, 11), "56", "57", "55", "56", "4100"),
        ]
        front.append(bar(utc(2020, 12, 10), "50", "51", "49", "50", "800"))
        return {"CLZ2020": front, "CLF2021": back}

    def test_fu_c01_ratio_stitching(self):
        """FU-C01: pre-roll history scaled by front/back close ratio."""
        series = ContinuousSeries(
            series_id="CL-CONT",
            root_symbol="CL",
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(self._roll(),),
        )
        out = series.stitch(self._segments())
        # Roll bar pair: front close 50 @ Dec10, back close 55 @ Dec10
        # ratio = 50/55 = 10/11
        from decimal import Decimal as D
        ratio = D("50") / D("55")
        dec8 = out[0]
        assert dec8["close"] == D("50") * ratio
        assert dec8["volume"] == D("1000") / ratio
        # Post-roll bars untouched
        assert out[-1]["close"] == D("56")
        # Roll bar itself comes from the BACK contract (we roll INTO it)
        assert out[2]["close"] == D("55")

    def test_fu_c02_inputs_never_mutated(self):
        series = ContinuousSeries(
            series_id="CL-CONT", root_symbol="CL",
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(self._roll(),),
        )
        segments = self._segments()
        front_close_before = segments["CLZ2020"][0]["close"]
        series.stitch(segments)
        assert segments["CLZ2020"][0]["close"] == front_close_before

    def test_fu_c03_series_hash_distinct_and_deterministic(self):
        """FU-C03: cont43. hash deterministic; distinct from contracts."""
        s1 = ContinuousSeries(
            series_id="CL-CONT", root_symbol="CL",
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(self._roll(),),
        )
        s2 = ContinuousSeries(
            series_id="CL-CONT", root_symbol="CL",
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(self._roll(),),
        )
        assert s1.series_hash == s2.series_hash
        assert s1.series_hash.startswith("cont43.")
        contract = make_contract("CLZ2020")
        assert s1.series_hash != contract.contract_hash

    def test_fu_c04_unknown_roll_contract_rejected(self):
        roll = RollDecision(
            front_contract_id="CLX2020",  # not in contract set
            back_contract_id="CLF2021",
            decision_time=utc(2020, 12, 10),
            effective_time=utc(2020, 12, 10),
            reason="x",
        )
        with pytest.raises(ValueError, match="not in the series"):
            ContinuousSeries(
                series_id="CL-CONT", root_symbol="CL",
                contract_ids=("CLZ2020", "CLF2021"),
                roll_decisions=(roll,),
            )

    def test_fu_c05_missing_roll_bar_pair_raises(self):
        """FU-C05: no observable bar pair at roll time -> leakage error."""
        series = ContinuousSeries(
            series_id="CL-CONT", root_symbol="CL",
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(self._roll(),),
        )
        # Back segment starts AFTER the roll effective time
        segments = {
            "CLZ2020": [
                bar(utc(2020, 12, 8), "50", "51", "49", "50", "1000"),
                bar(utc(2020, 12, 10), "50", "51", "49", "50", "800"),
            ],
            "CLF2021": [
                bar(utc(2020, 12, 20), "55", "56", "54", "55", "4000"),
            ],
        }
        with pytest.raises(RollLeakageError, match="no observable bar pair"):
            series.stitch(segments)

    def test_fu_c06_difference_method(self):
        roll = self._roll()
        series = ContinuousSeries(
            series_id="CL-CONT", root_symbol="CL",
            adjustment_method=AdjustmentMethod.BACKWARD_DIFFERENCE,
            contract_ids=("CLZ2020", "CLF2021"),
            roll_decisions=(roll,),
        )
        segments = self._segments()
        out = series.stitch(segments)
        # diff = front(50) - back(55) = -5 applied to earlier closes
        from decimal import Decimal as D
        assert out[0]["close"] == D("50") + D("-5")
        assert out[-1]["close"] == D("56")
