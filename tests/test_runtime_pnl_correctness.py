"""PAPER-RUN-PNL-1 acceptance tests — account-equity correctness.

Defect being closed (discovered in the 2026-10-12 next-execution
mandate Phase C, first-hand source inspection + executable probes):

- RUN-EQ-1 (HIGH): ``TradingRuntime._current_equity`` subtracted the
  cumulative transaction-cost ledger (``_equity_realized``) although
  those costs are ALREADY embedded in the average-cost basis and the
  realized P&L by the authoritative ``PaperPosition.apply_fill`` core
  (``paper/models.py`` price-inclusive basis). Equity was understated
  by exactly the cumulative transaction costs — corrupting position
  sizing and every equity-denominated risk check.

- RUN-RL-1 (HIGH): ``TradingRuntime._daily_realized_return`` returned
  ``_equity_realized / initial_equity`` — a ratio of NON-NEGATIVE
  cumulative costs. The mandatory ``loss_limit`` risk-gate check
  (``daily_realized_return >= -daily_loss_limit_fraction``) was
  therefore structurally INCAPABLE of failing: a day of catastrophic
  trading losses never stopped new orders, and no day boundary
  existed.

ACCEPTED INTERFACE (implemented in this fix):

1. ``_current_equity(mark)`` == initial_equity + position.realized_pnl
   + unrealized(position, mark) — transaction costs counted EXACTLY
   ONCE (via the cost-embedded basis). The persisted
   ``equity_realized`` field remains a cost-observability accumulator
   only (schema 1.1.0 unchanged — backward compatible).

2. ``_daily_realized_return()`` == the TRUE mark-to-market account
   return between the current UTC day's first admitted bar and the
   latest admitted bar's close:
   (current_equity - day_start_equity) / day_start_equity, where the
   day-start anchor is DETERMINISTICALLY reconstructed by replaying
   every OMS fill with ``bar_index`` before the day's first bar onto
   a fresh position (costs embedded once, consistent with the
   runtime's authoritative accounting) and marking it at the previous
   day's last close. A non-positive/unestablishable anchor yields
   -1.0 so the loss limit FAILS CLOSED (new orders refused).

3. The value is restart-stable: after full state restore it is
   recomputed identically from persisted bars + orders (no new
   persisted field; the in-memory day-anchor cache is pure
   determinism, never state).

Acceptance tests below FAIL on the pre-fix code (verified red before
implementation) and must pass after it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from data_engine.runtime import (
    DecisionAction,
    EntryConstraints,
    ExecutionStateStore,
    RiskContext,
    RuntimeConfig,
    RuntimeFill,
    RuntimeCalibrator,
    TradePlan,
    TradingRuntime,
    UncertaintyReport,
)
from data_engine.runtime.pnl import PositionState

# Reuse the deterministic world builders from the E2E module.
from test_runtime_e2e import T0, _bars, _fit_world

SYMBOL = "TEST/USD"


def _no_trade_config(session):
    """Ephemeral fixture whose decision engine never trades
    (max_crash_probability=0.0 < the crash floor 0.02), so tests can
    seed OMS orders/positions deterministically."""
    return RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        max_crash_probability=0.0,
        ephemeral_test_fixture=True,
    )


def _uncertainty():
    return UncertaintyReport(
        confidence=0.9, entropy=0.3, ensemble_disagreement=0.1,
    )


def _plan(corr, side, qty, ref, sl, tp, ttl=3):
    return TradePlan(
        trade_plan_id=f"tp-{corr}", decision_id=f"dec-{corr}",
        symbol=SYMBOL, side=side, quantity=qty, notional=qty * ref,
        entry=EntryConstraints(order_type="MARKET", ttl_bars=ttl),
        stop_loss=sl, take_profit=tp, risk_budget=Decimal("100"),
        expected_return=0.01, risk_reward_ratio=2.0,
        uncertainty=_uncertainty(), crash_risk={"probability": 0.0},
        model_context={"model": "pnl-correctness"}, correlation_id=corr,
    )


def _fill(order_id, side, qty, price, bar_index, filled_at,
          commission=Decimal("0"), slippage=Decimal("0"),
          spread=Decimal("0")):
    f = RuntimeFill(
        fill_id="pending", order_id=order_id, symbol=SYMBOL, side=side,
        quantity=qty, price=price, commission=commission,
        slippage_cost=slippage, spread_cost=spread,
        filled_at=filled_at, fill_index=0, bar_index=bar_index,
    )
    return f.model_copy(update={"fill_id": f.fill_hash})


def _seed_order_fill(rt, plan, price, bar_index, corr):
    """Seed one FULLY risk-approved, submitted, filled order through
    the REAL OMS path (no bypass) and apply it to the position book
    exactly like the runtime does."""
    position = rt._positions.get(SYMBOL, PositionState(symbol=SYMBOL))
    ctx = RiskContext(
        equity=Decimal("100000"),
        current_units=position.quantity,
        reference_price=price,
        bar_volume=Decimal("5000"),
        last_bar_age_bars=0, market_open=True, paper_mode=True,
        model_valid=True, uncertainty=plan.uncertainty,
        crash_probability=0.0, max_drawdown_fraction=0.0,
        volatility=0.01, daily_realized_return=0.0,
        account_drawdown_fraction=0.0,
        half_spread=Decimal("0.02"), max_spread_fraction=Decimal("0.01"),
        # reconstruction D-6: in-limit order-limit state (the gate's new
        # mandatory checks fail closed when unknown)
        open_order_count=0, max_open_orders=10,
        orders_submitted_in_window=0, max_orders_per_window=5,
        order_rate_window_seconds=60.0,
    )
    assessment = rt._risk_gate.evaluate(plan, ctx, corr)
    assert assessment.passed, [c.reason for c in assessment.failed_checks]
    order, created = rt._oms.create_order(
        plan=plan, session_id=rt.config.session_id,
        created_at=T0 + timedelta(seconds=300 * bar_index),
        ttl_bars=plan.entry.ttl_bars,
    )
    assert created
    rt._oms.validate_order(order.order_id)
    rt._oms.risk_approve(order.order_id, assessment)
    rt._oms.submit(
        order.order_id,
        submitted_at=T0 + timedelta(seconds=300 * bar_index),
        bar_index=bar_index,
    )
    rt._oms.acknowledge(order.order_id)
    fill = _fill(order.order_id, plan.side.value, plan.quantity, price,
                 bar_index, T0 + timedelta(seconds=300 * bar_index))
    rt._oms.apply_fill(order.order_id, fill)
    rt._apply_fill_to_position(fill, corr)
    return order


def _run_bars(rt, bars, count):
    for b in bars[:count]:
        rt.process_bar(b)


class TestEquityCountsCostsExactlyOnce:
    """RUN-EQ-1 acceptance."""

    def test_equity_after_costly_fill_matches_true_equity(self, tmp_path):
        """One BUY fill of 1 unit @100 with 0.2 total costs, market
        unchanged: account equity MUST be initial - 0.2 (costs once,
        embedded in the 100.2 basis). Pre-fix: initial - 0.4."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_no_trade_config("pnl-t1"), ens, calibrator=cal)
        rt.start()
        _run_bars(rt, _bars(10), 10)
        fill = _fill("seed-1", "BUY", Decimal("1"), Decimal("100"), 5,
                     T0 + timedelta(seconds=1500),
                     commission=Decimal("0.1"),
                     slippage=Decimal("0.05"), spread=Decimal("0.05"))
        rt._apply_fill_to_position(fill, "corr-t1")
        pos = rt._positions[SYMBOL]
        assert pos.average_cost == Decimal("100.2")  # costs embedded once
        # TRUE equity: initial(100000) + realized(0) + unrealized(-0.2)
        assert rt._current_equity(Decimal("100")) == Decimal("99999.8")

    def test_full_chain_equity_identity(self):
        """After a REAL governed trading run: account equity equals
        initial + realized + unrealized EXACTLY (no cost double
        count). Pre-fix it is lower by the cumulative costs."""
        ens, cal = _fit_world()
        rt = TradingRuntime(
            RuntimeConfig(
                symbol=SYMBOL, timeframe="5m", session_id="pnl-t6",
                initial_equity=Decimal("100000"), lookback=8, horizon=2,
                feature_version="fv-1", dataset_version="dv-synth",
                expected_interval_seconds=300,
                ephemeral_test_fixture=True,
            ),
            ens, calibrator=cal,
        )
        rt.start()
        bars = _bars(60)
        for b in bars:
            rt.process_bar(b)
        assert rt._equity_realized > 0, "scenario must incur costs"
        assert any(o.fills for o in rt.oms.orders())
        mark = Decimal(str(bars[-1]["close"]))
        pos = rt._positions.get(SYMBOL, PositionState(symbol=SYMBOL))
        expected = (
            Decimal("100000") + pos.realized_pnl
            + rt._pnl_engine.unrealized(pos, mark)
        )
        assert rt._current_equity(mark) == expected


class TestDailyLossLimitMeasuresTrueLosses:
    """RUN-RL-1 acceptance."""

    def test_limit_fails_after_beyond_limit_trading_loss(self):
        """A controlled -3.6% intraday trading loss (seeded through
        the REAL OMS+risk path) MUST make _daily_realized_return()
        < -0.03 AND the runtime's own _execute_plan context MUST fail
        the mandatory loss_limit check (new entry refused).
        Pre-fix: the measure returned ~0.0 and the check passed."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_no_trade_config("pnl-t2"), ens, calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)  # >= 21 bars -> volatility check has data
        # Round trip: BUY 60 @100 (bar 5), SELL 60 @40 (bar 6) -> -3600
        _seed_order_fill(
            rt, _plan("seed-b", DecisionAction.BUY, Decimal("60"),
                      Decimal("100"), Decimal("98"), Decimal("104")),
            Decimal("100"), 5, "corr-seed-b",
        )
        _seed_order_fill(
            rt, _plan("seed-s", DecisionAction.SELL, Decimal("60"),
                      Decimal("40"), Decimal("42"), Decimal("36")),
            Decimal("40"), 6, "corr-seed-s",
        )
        pos = rt._positions[SYMBOL]
        assert pos.is_flat
        assert pos.realized_pnl == Decimal("-3600")
        daily = rt._daily_realized_return()
        assert daily < -0.03, f"true daily return must trip: {daily}"
        # The REAL wiring: _execute_plan builds the RiskContext from
        # _daily_realized_return() itself.
        ref = Decimal(str(bars[24]["close"]))
        entry = _plan("entry-2", DecisionAction.BUY, Decimal("10"),
                      ref, ref - Decimal("2"), ref + Decimal("4"))
        created, failed = rt._execute_plan(
            entry, bars[24], 24, "corr-entry-2", ref,
            rt._current_equity(ref),
        )
        assert failed == ("loss_limit",), (
            f"loss_limit must be the ONLY failing check, got {failed}"
        )
        assert created == []

    def test_limit_does_not_trip_on_moderate_loss(self):
        """-1.5% intraday loss stays within the limit: the loss_limit
        check passes and an entry order is created (no over-tripping
        regression guard for the fix)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_no_trade_config("pnl-t7"), ens, calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_order_fill(
            rt, _plan("seed-b7", DecisionAction.BUY, Decimal("50"),
                      Decimal("100"), Decimal("98"), Decimal("104")),
            Decimal("100"), 5, "corr-seed-b7",
        )
        _seed_order_fill(
            rt, _plan("seed-s7", DecisionAction.SELL, Decimal("50"),
                      Decimal("70"), Decimal("72"), Decimal("66")),
            Decimal("70"), 6, "corr-seed-s7",
        )
        daily = rt._daily_realized_return()
        assert -0.03 < daily < 0, f"moderate loss must not trip: {daily}"
        ref = Decimal(str(bars[24]["close"]))
        entry = _plan("entry-7", DecisionAction.BUY, Decimal("10"),
                      ref, ref - Decimal("2"), ref + Decimal("4"))
        created, failed = rt._execute_plan(
            entry, bars[24], 24, "corr-entry-7", ref,
            rt._current_equity(ref),
        )
        assert failed == ()
        assert created  # order created — the gate did not over-trip


class TestDailyAnchorResetsPerUtcDay:
    """Day-boundary semantics of the accepted interface."""

    def test_anchor_resets_after_utc_midnight(self):
        """Same session: -3.6% on day 1 trips the limit; after UTC
        midnight (no further losses) the daily return resets to ~0.
        Pre-fix both values were ~0.0 (costs only), so the day-1
        trip assertion fails on the old code."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_no_trade_config("pnl-t3"), ens, calibrator=cal)
        rt.start()
        # Start at 22:00 (t_offset=156): bars 0-11 are day 1, bar 12
        # is the first bar of the next UTC day.
        bars = _bars(45, t_offset=156)
        _run_bars(rt, bars, 11)
        _seed_order_fill(
            rt, _plan("seed-b3", DecisionAction.BUY, Decimal("60"),
                      Decimal("100"), Decimal("98"), Decimal("104")),
            Decimal("100"), 5, "corr-seed-b3",
        )
        _seed_order_fill(
            rt, _plan("seed-s3", DecisionAction.SELL, Decimal("60"),
                      Decimal("40"), Decimal("42"), Decimal("36")),
            Decimal("40"), 6, "corr-seed-s3",
        )
        day1 = rt._daily_realized_return()
        assert day1 < -0.03, f"day-1 loss must trip: {day1}"
        for b in bars[11:]:
            rt.process_bar(b)
        day2 = rt._daily_realized_return()
        assert day2 >= -0.03, f"new day must reset the anchor: {day2}"
        assert day2 > day1, "anchor reset must change the measure"


class TestDeterminismAndRestartStability:
    """The accepted measure is deterministic + restart-stable."""

    def test_identical_runs_same_daily_return_and_outcomes(self):
        bars = _bars(60)
        results = []
        # SAME session id: the idempotent order identity is a pure
        # function of governed fields INCLUDING session_id, so
        # determinism is asserted for identical configurations.
        for _ in range(2):
            ens, cal = _fit_world()
            rt = TradingRuntime(
                _no_trade_config("pnl-t4").model_copy(
                    update={"max_crash_probability": 0.20}
                ),
                ens, calibrator=cal,
            )
            rt.start()
            outcomes = [rt.process_bar(b) for b in bars]
            results.append((
                rt._daily_realized_return(),
                rt._current_equity(Decimal(str(bars[-1]["close"]))),
                rt.ledgers.head_hashes(),
                tuple(
                    (o.orders_created, o.fills, o.realized_pnl,
                     o.unrealized_pnl) for o in outcomes
                ),
            ))
        assert results[0] == results[1]

    def test_daily_return_recomputed_identically_after_restart(
            self, tmp_path):
        """Operational runtime + real state store: after full restore
        (LOAD -> VERIFY -> RESTORE -> RECONCILE) the daily return and
        equity are IDENTICAL to the pre-restart values."""
        from test_runtime_recovery_integration import _operational

        ens_cal = _fit_world()
        store_dir = tmp_path / "state"
        rt1 = _operational("pnl-t5", store_dir, ens_cal=ens_cal)
        rt1.start()
        bars = _bars(60)  # 09:00 -> 14:00, one UTC day
        for b in bars:
            rt1.process_bar(b)
        assert any(o.fills for o in rt1.oms.orders()), "needs fills"
        mark = Decimal(str(bars[-1]["close"]))
        pre_daily = rt1._daily_realized_return()
        pre_equity = rt1._current_equity(mark)

        if getattr(rt1, "_store", None) is not None:
            rt1._store.close()  # process death (F-03 single-writer lock)
        rt2 = _operational("pnl-t5", store_dir, ens_cal=ens_cal)
        rt2.start()  # full recovery chain (restore + reconcile)
        assert rt2.restarted
        assert rt2._daily_realized_return() == pre_daily
        assert rt2._current_equity(mark) == pre_equity
