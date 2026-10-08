"""Phase 8 acceptance tests — risk limits, exposure, portfolio.

Blueprint 5.28–5.31 invariants:

- RK-01  hard limits: position breach raises AND records (no override)
- RK-02  weight breaches (single-asset, sector, leverage, heat) raise
- RK-03  kill switch: once tripped everything refuses until external
          reset; breaches trip it in production posture
- RK-04  hash-chained violation log (tamper-evident ordering)
- RK-05  exposure aggregation by asset and sector with breach lists
- RK-06  inverse-volatility allocation deterministic; limit gauntlet
          runs BEFORE allocation returns
- RK-07  zero-volatility strategies fail closed
- RK-08  incoherent limit sets rejected at construction
"""

from decimal import Decimal

import pytest

from data_engine.risk import (
    RiskLimits,
    RiskViolationError,
    KillSwitchActiveError,
    RiskEngine,
    ExposureManager,
    PortfolioConstructor,
    PortfolioError,
    Allocation,
)

D = Decimal

LIMITS = RiskLimits(
    max_position_units=D("100"),
    max_leverage=D("2"),
    max_single_asset_weight=D("0.3"),
    max_sector_weight=D("0.6"),
    max_portfolio_heat=D("1.5"),
)


class TestRiskLimits:

    def test_rk_08_incoherent_limits_rejected(self):
        with pytest.raises(ValueError, match="incoherent"):
            RiskLimits(
                max_position_units=D("100"),
                max_leverage=D("2"),
                max_single_asset_weight=D("0.7"),  # > sector cap
                max_sector_weight=D("0.6"),
                max_portfolio_heat=D("1.5"),
            )
        with pytest.raises(ValueError):
            RiskLimits(
                max_position_units=D("0"),  # non-positive
                max_leverage=D("2"),
                max_single_asset_weight=D("0.3"),
                max_sector_weight=D("0.6"),
                max_portfolio_heat=D("1.5"),
            )

    def test_rk_08b_limits_hash_deterministic(self):
        twin = RiskLimits(
            max_position_units=D("100"),
            max_leverage=D("2"),
            max_single_asset_weight=D("0.3"),
            max_sector_weight=D("0.6"),
            max_portfolio_heat=D("1.5"),
        )
        assert LIMITS.limits_hash == twin.limits_hash
        assert LIMITS.limits_hash.startswith("risk8.")


class TestRiskEngine:

    def test_rk_01_position_breach_raises_and_records(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        engine.check_order("EURUSD", D("60"))  # ok
        engine.check_order("EURUSD", D("40"), current_units=D("60"))  # ok: projected 100 (signed netting, BUG-003)
        with pytest.raises(RiskViolationError, match="exceeds max"):
            engine.check_order("EURUSD", D("50"), current_units=D("60"))
        assert len(engine.violation_log) == 1
        assert engine.violation_log[0].rule == "max_position_units"

    def test_rk_02_weight_breaches(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        ok = {"AAA": D("0.25"), "BBB": D("0.25"), "CCC": D("0.25")}
        engine.check_weights(ok, gross_leverage=D("0.75"))
        with pytest.raises(RiskViolationError, match="single-asset"):
            engine.check_weights({"AAA": D("0.5"), "BBB": D("0.2")})
        sectors = {"AAA": "tech", "AAB": "tech", "BBB": "fin"}
        with pytest.raises(RiskViolationError, match="sector"):
            engine.check_weights(
                {"AAA": D("0.25"), "AAB": D("0.25"), "AAC": D("0.25")},
                sectors={**sectors, "AAC": "tech"},
            )  # tech total 0.75 > 0.6 cap
        with pytest.raises(RiskViolationError, match="leverage"):
            engine.check_weights({"AAA": D("0.2")}, gross_leverage=D("3"))
        with pytest.raises(RiskViolationError, match="heat"):
            engine.check_weights({"AAA": D("0.2")}, gross_leverage=D("1.8"))

    def test_rk_03_kill_switch(self):
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        # A breach trips the switch...
        with pytest.raises(RiskViolationError):
            engine.check_order("X", D("500"))
        assert engine.kill_switch_active
        # ...and everything afterwards refuses
        with pytest.raises(KillSwitchActiveError):
            engine.check_order("X", D("1"))
        # Only an external HUMAN controller may reset (ARCH-F1)
        engine.reset_kill_switch(principal="risk-operator", principal_kind="human")
        engine.check_order("X", D("1"))
        assert not engine.kill_switch_active

    def test_rk_04_hash_chained_log(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        for _ in range(3):
            with pytest.raises(RiskViolationError):
                engine.check_order("X", D("500"))
        log = engine.violation_log
        assert len(log) == 3
        assert log[0].prev_record_hash == "0" * 64  # genesis
        for prev, cur in zip(log, log[1:]):
            assert cur.prev_record_hash == prev.record_hash


class TestExposure:

    def test_rk_05_exposure_report(self):
        manager = ExposureManager(LIMITS)
        report = manager.build_report(
            positions={"AAA": D("10"), "BBB": D("5")},
            prices={"AAA": D("10"), "BBB": D("20")},
            equity=D("1000"),
            sectors={"AAA": "tech", "BBB": "fin"},
        )
        assert report.by_asset["AAA"] == "0.1"
        assert report.by_asset["BBB"] == "0.1"
        assert report.by_sector["tech"] == "0.1"
        assert report.by_sector["fin"] == "0.1"
        assert report.total_exposure == "0.2"
        assert report.single_asset_breaches == ()
        assert report.sector_breaches == ()
        assert report.report_hash.startswith("expo8.")

    def test_rk_05b_exposure_breach_lists(self):
        manager = ExposureManager(LIMITS)
        report = manager.build_report(
            positions={"AAA": D("40")},  # 40*10=400 -> 0.4 > 0.3
            prices={"AAA": D("10")},
            equity=D("1000"),
        )
        assert report.single_asset_breaches == ("AAA",)


class TestPortfolio:

    def test_rk_06_inverse_vol_allocation(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        constructor = PortfolioConstructor(engine)
        allocation = constructor.allocate(
            volatilities={"AAA": D("0.1"), "BBB": D("0.2"), "CCC": D("0.2")},
            target_gross=D("0.5"),
        )
        # Inverse vols: 10, 5, 5 -> total 20 -> weights .5/.25/.25 * 0.5
        assert D(allocation.weights["AAA"]) == D("0.25")
        assert D(allocation.weights["BBB"]) == D("0.125")
        assert D(allocation.weights["CCC"]) == D("0.125")
        assert D(allocation.gross_exposure) == D("0.5")
        assert allocation.allocation_hash.startswith("port8.")
        # Determinism
        twin = constructor.allocate(
            volatilities={"AAA": D("0.1"), "BBB": D("0.2"), "CCC": D("0.2")},
            target_gross=D("0.5"),
        )
        assert allocation.allocation_hash == twin.allocation_hash

    def test_rk_06b_limit_gauntlet_before_return(self):
        """RK-06b: a target that would breach limits raises."""
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        constructor = PortfolioConstructor(engine)
        # Two assets with vols 0.1/0.01: weights 1/11 and 10/11 — the
        # latter exceeds the 0.3 single-asset cap at any gross >= 3.3
        with pytest.raises(RiskViolationError, match="single-asset"):
            constructor.allocate(
                volatilities={"AAA": D("0.1"), "BBB": D("0.01")},
                target_gross=D("1.0"),
            )

    def test_rk_07_zero_volatility_fails_closed(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        constructor = PortfolioConstructor(engine)
        with pytest.raises(PortfolioError, match="positive Decimal"):
            constructor.allocate(
                volatilities={"AAA": D("0")},
                target_gross=D("1.0"),
            )
