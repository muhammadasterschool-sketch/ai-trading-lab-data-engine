"""RUN-DD-1 acceptance tests — ACCOUNT-equity drawdown limit.

Defect being closed (ranked next blocker in the 2026-10-12
killswitch-audit mandate §0E; implemented as Batch 2 of the
runtime-risk-safety mandate):

- RUN-DD-1 (MED-HIGH): the mandatory ``drawdown`` risk-gate check
  measured ONLY the SYMBOL's price-window drawdown
  (``TradingRuntime._window_drawdown`` over bar closes). The
  ACCOUNT's own mark-to-market equity drawdown — the measure that
  actually protects the user's capital — was NEVER limited: a
  session could lose half its account equity with every mandatory
  gate check passing, and no automatic protective action existed.

ACCEPTED INTERFACE (implemented in this fix):

1. Calculation — ``TradingRuntime._account_drawdown()`` =
   ``(peak - current) / peak`` where BOTH are TRUE mark-to-market
   account equity (PAPER-RUN-PNL-1 accounting: initial + realized +
   unrealized at the latest admitted bar's close, costs exactly
   once) and ``peak`` is the session high-water mark of that same
   equity over every admitted bar close — deterministically replayed
   from the persisted bar history + OMS fills (the identical
   reconstruction discipline as the daily anchor: no new persisted
   field, so the measure is restart-stable by construction).

2. Configuration — ``RuntimeConfig.max_account_drawdown_fraction``
   (default 0.20, validated to be a finite fraction in (0, 1]).

3. Enforcement —
   a. a NEW mandatory risk-gate check ``account_drawdown`` refuses
      NEW entry orders when the fraction is unknown (fail closed,
      never neutral) or strictly above the limit; closing/reducing
      orders stay permitted (the limit blocks NEW exposure, not risk
      reduction — the fail-safe direction);
   b. the runtime evaluates the drawdown after every admitted bar's
      fills (fill-driven AND price-driven breaches); a strict breach
      ledgered as ``ACCOUNT_DRAWDOWN_LIMIT_BREACH``, trips the
      ACCOUNT kill switch (auditable source
      ``runtime.risk.drawdown``) and HALTS the session terminally;
      the trip persists immediately (BLOCKER 12) and a restart
      REFUSES to clear it (critical-switch loud refusal);
   c. a HALT freezes every in-flight order: no bar is processed, so
      no entry remainder can ever fill past the limit.

4. Missing/anomalous equity data — a fresh session measures 0.0
   (peak == current == initial, nothing at risk); an unanchorable
   equity path (a fill whose ``bar_index`` is missing or outside
   the admitted bar history — unreachable through the governed
   execution adapter) yields ``None``: the risk-gate check then
   FAILS CLOSED for new orders and enforcement ledgered
   ``ACCOUNT_DRAWDOWN_UNKNOWN`` without tripping on an unknown
   measure.

Boundary convention (consistent with the existing ``drawdown`` and
``loss_limit`` checks): equality PASSES — only a strict breach
trips.

These tests FAIL on the pre-fix code (the interface does not exist)
and must pass after it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from data_engine.paper.simulator import ExecutionRealism
from data_engine.runtime import (
    DecisionAction,
    EntryConstraints,
    ExecutionStateStore,
    KillSwitchScope,
    RiskContext,
    RuntimeConfig,
    RuntimeFill,
    RuntimeCalibrator,
    RuntimeState,
    TradePlan,
    TradingRuntime,
    UncertaintyReport,
)
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.pnl import PositionState

# Reuse the deterministic world builders from the E2E module.
from test_runtime_e2e import T0, _bars, _fit_world
from test_runtime_recovery_integration import _operational, _ready_gate

SYMBOL = "TEST/USD"
#: Seeded round-trip size (position limit in the test configs is 1000).
QTY = Decimal("100")
INITIAL = Decimal("100000")


def _dd_config(session, limit, max_units="1000"):
    """Ephemeral no-trade fixture config (max_crash_probability=0.0 <
    the crash floor 0.02) with a configurable ACCOUNT drawdown
    limit — tests seed OMS orders/positions deterministically."""
    return RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=INITIAL, lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        max_crash_probability=0.0,
        max_position_units=Decimal(max_units),
        max_account_drawdown_fraction=limit,
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
        model_context={"model": "account-drawdown"}, correlation_id=corr,
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
        equity=INITIAL,
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
        bar_index=min(bar_index, 24),
    )
    rt._oms.acknowledge(order.order_id)
    fill = _fill(order.order_id, plan.side.value, plan.quantity, price,
                 bar_index, T0 + timedelta(seconds=300 * bar_index))
    rt._oms.apply_fill(order.order_id, fill)
    rt._apply_fill_to_position(fill, corr)
    return order


def _seed_round_trip_loss(rt, bars):
    """Seed a controlled round-trip loss THROUGH THE REAL OMS PATH:
    BUY QTY at bar 5's close, SELL QTY at bar 6's close. Fill prices
    equal the bar closes, so the replayed equity path is exact and
    the position ends flat with realized P&L = QTY*(close6-close5)."""
    buy_px = Decimal(str(bars[5]["close"]))
    sell_px = Decimal(str(bars[6]["close"]))
    _seed_order_fill(
        rt,
        _plan("seed-dd-b", DecisionAction.BUY, QTY, buy_px,
              buy_px - Decimal("2"), buy_px + Decimal("4")),
        buy_px, 5, "corr-seed-dd-b",
    )
    _seed_order_fill(
        rt,
        _plan("seed-dd-s", DecisionAction.SELL, QTY, sell_px,
              sell_px + Decimal("2"), sell_px - Decimal("4")),
        sell_px, 6, "corr-seed-dd-s",
    )
    pos = rt._positions[SYMBOL]
    assert pos.is_flat
    return buy_px, sell_px


def _expected_round_trip_drawdown(bars):
    """(peak - current)/peak for the seeded round trip, computed from
    the bar data exactly like the runtime's replay: peak == initial
    (the long position is opened AT bar 5's close, so no unrealized
    bump), current == initial + realized loss."""
    buy_px = Decimal(str(bars[5]["close"]))
    sell_px = Decimal(str(bars[6]["close"]))
    loss = (buy_px - sell_px) * QTY
    assert loss > 0
    return float(loss / INITIAL)


def _run_bars(rt, bars, count):
    for b in bars[:count]:
        rt.process_bar(b)


def _entry_plan(bars, corr, bar_i=24):
    ref = Decimal(str(bars[bar_i]["close"]))
    return _plan(corr, DecisionAction.BUY, Decimal("10"), ref,
                 ref - Decimal("2"), ref + Decimal("4"))


def _try_entry(rt, bars, corr, bar_i=24):
    ref = Decimal(str(bars[bar_i]["close"]))
    return rt._execute_plan(
        _entry_plan(bars, corr, bar_i), bars[bar_i], bar_i, corr,
        ref, rt._current_equity(ref),
    )


def _incident_types(rt):
    return [
        e.event_type for e in rt.ledgers.events(ledger="incident")
    ]


class TestDrawdownMeasurement:
    """The accepted calculation."""

    def test_fresh_session_measures_zero(self):
        """No bars, no fills: peak == current == initial equity and
        the drawdown is exactly 0.0 (nothing is at risk yet)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-fresh", 0.20), ens,
                            calibrator=cal)
        rt.start()
        assert rt._account_drawdown() == 0.0
        assert rt._peak_account_equity() == INITIAL

    def test_measures_true_mark_to_market_drawdown(self):
        """Seeded round trip at bar closes: the measure is exactly
        loss/initial (peak stays at initial — the long position is
        opened AT bar 5's close, so equity never rises above the
        initial level on the replayed path)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-measure", 0.20), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_round_trip_loss(rt, bars)
        expected = _expected_round_trip_drawdown(bars)
        assert rt._peak_account_equity() == INITIAL
        assert rt._account_drawdown() == pytest.approx(expected, rel=1e-12)

    def test_unrealized_loss_is_measured(self):
        """An OPEN position marked below its basis is a drawdown too
        (mark-to-market, not realized-only): BUY at bar 5's close and
        the later bars mark the position DOWN — the open loss must
        register against the true mark-to-market PEAK (which includes
        the position's intra-session appreciation above entry)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-open", 0.20), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        buy_px = Decimal(str(bars[5]["close"]))
        _seed_order_fill(
            rt,
            _plan("seed-open-b", DecisionAction.BUY, QTY, buy_px,
                  buy_px - Decimal("2"), buy_px + Decimal("4")),
            buy_px, 5, "corr-seed-open-b",
        )
        # true MTM path: peak = max(initial, best close since entry)
        # with the long position on the book; current at bar 24's close
        closes = [Decimal(str(b["close"])) for b in bars[5:25]]
        peak = max(
            [INITIAL]
            + [INITIAL + (c - buy_px) * QTY for c in closes]
        )
        mark = Decimal(str(bars[24]["close"]))
        current = INITIAL + (mark - buy_px) * QTY
        expected = float((peak - current) / peak)
        assert expected > 0
        assert rt._account_drawdown() == pytest.approx(expected, rel=1e-9)

    def test_config_rejects_invalid_limits(self):
        """The limit must be a finite fraction in (0, 1] — 0, negative,
        >1 and NaN are refused at construction (fail closed)."""
        def _cfg(limit):
            return RuntimeConfig(
                symbol=SYMBOL, timeframe="5m", session_id="dd-bad",
                initial_equity=INITIAL,
                max_account_drawdown_fraction=limit,
            )
        for bad in (0.0, -0.1, 1.5, float("nan")):
            with pytest.raises(Exception, match="max_account_drawdown"):
                _cfg(bad)
        # boundary values ARE legal
        assert _cfg(1.0).max_account_drawdown_fraction == 1.0
        assert _cfg(0.001).max_account_drawdown_fraction == 0.001


class TestRiskGateAccountDrawdownCheck:
    """The mandatory gate check (new orders)."""

    def test_entry_refused_when_drawdown_exceeds_limit(self):
        """dd 0.184% > limit 0.1%: a NEW entry order is refused by the
        risk gate with ``account_drawdown`` as the ONLY failing
        check; no order is created. Pre-fix: no such check existed."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-refuse", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_round_trip_loss(rt, bars)
        assert rt._account_drawdown() > 0.001
        created, failed = _try_entry(rt, bars, "corr-entry-refuse")
        assert failed == ("account_drawdown",), (
            f"account_drawdown must be the ONLY failing check, got {failed}"
        )
        assert created == []
        assert rt.metrics.get("orders_risk_rejected") >= 1

    def test_entry_permitted_at_exact_limit_boundary(self):
        """Equality PASSES (consistent with drawdown/loss_limit): with
        the limit set to exactly the measured drawdown, the entry is
        created and no check fails."""
        ens, cal = _fit_world()
        bars = _bars(30)
        limit = _expected_round_trip_drawdown(bars)
        rt = TradingRuntime(_dd_config("dd-boundary", limit), ens,
                            calibrator=cal)
        rt.start()
        _run_bars(rt, bars, 25)
        _seed_round_trip_loss(rt, bars)
        assert rt._account_drawdown() == pytest.approx(limit, rel=1e-12)
        created, failed = _try_entry(rt, bars, "corr-entry-boundary")
        assert failed == ()
        assert created

    def test_no_trip_at_exact_limit_boundary(self):
        """The runtime enforcement also treats equality as in-limit:
        processing further bars does NOT trip the switch or halt."""
        ens, cal = _fit_world()
        bars = _bars(30)
        limit = _expected_round_trip_drawdown(bars)
        rt = TradingRuntime(_dd_config("dd-no-trip", limit), ens,
                            calibrator=cal)
        rt.start()
        _run_bars(rt, bars, 25)
        _seed_round_trip_loss(rt, bars)
        rt.process_bar(bars[25])
        assert rt.state is RuntimeState.RUNNING
        assert not rt.kill_switch.is_active(KillSwitchScope.ACCOUNT)
        assert "ACCOUNT_DRAWDOWN_LIMIT_BREACH" not in _incident_types(rt)

    def test_closing_order_permitted_during_breach(self):
        """Directional carve-out: while the drawdown is breached, a
        NEW entry is refused but a CLOSING order (risk reduction)
        is still created — the limit blocks new exposure, not the
        wind-down of an existing position."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-close", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        buy_px = Decimal(str(bars[5]["close"]))
        _seed_order_fill(
            rt,
            _plan("seed-close-b", DecisionAction.BUY, QTY, buy_px,
                  buy_px - Decimal("2"), buy_px + Decimal("4")),
            buy_px, 5, "corr-seed-close-b",
        )
        mark = Decimal(str(bars[24]["close"]))
        assert rt._account_drawdown() > 0.001  # open unrealized loss
        # entry: refused
        created_e, failed_e = _try_entry(rt, bars, "corr-entry-close")
        assert failed_e == ("account_drawdown",)
        assert created_e == []
        # closing order of the FULL position: permitted
        closing = _plan("close-all", DecisionAction.SELL, QTY, mark,
                        mark + Decimal("2"), mark - Decimal("4"))
        created_c, failed_c = rt._execute_plan(
            closing, bars[24], 24, "corr-close-all", mark,
            rt._current_equity(mark),
        )
        assert failed_c == ()
        assert created_c

    def test_unknown_drawdown_fails_closed(self):
        """A fill whose bar anchor is outside the admitted history
        (unreachable through the governed adapter) makes the equity
        path unanchorable: the measure is None, the gate REFUSES new
        entries fail-closed, and enforcement ledgered the anomaly
        WITHOUT tripping on an unknown measure."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-unknown", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        buy_px = Decimal(str(bars[5]["close"]))
        _seed_order_fill(
            rt,
            _plan("seed-oor", DecisionAction.BUY, QTY, buy_px,
                  buy_px - Decimal("2"), buy_px + Decimal("4")),
            buy_px, 999, "corr-seed-oor",  # unanchorable bar index
        )
        assert rt._account_drawdown() is None
        created, failed = _try_entry(rt, bars, "corr-entry-unknown")
        assert failed == ("account_drawdown",)
        assert created == []
        rt.process_bar(bars[25])
        assert "ACCOUNT_DRAWDOWN_UNKNOWN" in _incident_types(rt)
        # unknown != measured breach: no trip, session stays RUNNING
        assert rt.state is RuntimeState.RUNNING
        assert not rt.kill_switch.is_active(KillSwitchScope.ACCOUNT)


class TestBreachTripsAccountKillSwitch:
    """Runtime enforcement: fill-driven and price-driven breaches."""

    def test_breach_trips_account_switch_and_halts(self):
        """dd 0.184% > limit 0.1%: processing the next admitted bar
        trips the ACCOUNT kill switch (auditable source
        runtime.risk.drawdown), ledgered as
        ACCOUNT_DRAWDOWN_LIMIT_BREACH, and HALTS terminally — the
        FOLLOWING bar is refused outright."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-trip", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_round_trip_loss(rt, bars)
        out = rt.process_bar(bars[25])
        assert out.accepted  # this bar itself was admitted...
        assert out.runtime_state == "HALTED"  # ...and halted the session
        assert rt.state is RuntimeState.HALTED
        assert rt.kill_switch.is_active(KillSwitchScope.ACCOUNT)
        assert rt.metrics.get("drawdown_limit_breaches") == 1
        types = _incident_types(rt)
        assert "ACCOUNT_DRAWDOWN_LIMIT_BREACH" in types
        assert "KILL_SWITCH_TRIPPED" in types
        trip = [
            e for e in rt.ledgers.events(ledger="incident")
            if e.event_type == "KILL_SWITCH_TRIPPED"
        ][-1]
        assert trip.payload["scope"] == "ACCOUNT"
        assert trip.payload["source"] == "runtime.risk.drawdown"
        # terminal: the NEXT bar is refused (HALTED bars never trade)
        out2 = rt.process_bar(bars[26])
        assert not out2.accepted
        assert out2.runtime_state == "HALTED"

    def test_price_driven_breach_trips_without_new_fills(self):
        """An OPEN position marked down by later bars breaches the
        limit with NO new fills at all — the enforcement point runs
        on every admitted bar, not only on fill bars."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("dd-price", 0.001), ens,
                            calibrator=cal)
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        buy_px = Decimal(str(bars[5]["close"]))
        _seed_order_fill(
            rt,
            _plan("seed-price-b", DecisionAction.BUY, QTY, buy_px,
                  buy_px - Decimal("2"), buy_px + Decimal("4")),
            buy_px, 5, "corr-seed-price-b",
        )
        # open loss at bar 24: (112 - 103.92) * 100 = 808 -> 0.808%
        assert rt._account_drawdown() > 0.001
        rt.process_bar(bars[25])
        assert rt.state is RuntimeState.HALTED
        assert rt.kill_switch.is_active(KillSwitchScope.ACCOUNT)

    def test_inflight_entry_order_frozen_after_trip(self):
        """FAIL-SAFE FREEZE: an entry order submitted before the
        breach (fill lag 2 — not yet filled) can NEVER fill once the
        trip halts the session: bars are refused, so the pending
        remainder stays at zero fills and the position is unchanged.
        No exposure can be added past the limit."""
        ens, cal = _fit_world()
        rt = TradingRuntime(
            _dd_config("dd-freeze", 0.001), ens, calibrator=cal,
            realism=ExecutionRealism(
                half_spread=Decimal("0.02"),
                commission_per_unit=Decimal("0.001"),
                impact_rate=Decimal("0.0001"),
                participation_cap=Decimal("0.35"),
                fill_lag_bars=2,
            ),
        )
        rt.start()
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        # entry submitted on bar 24, fills from bar 26 (lag 2)
        created, failed = _try_entry(rt, bars, "corr-entry-fz")
        assert failed == ()
        assert created
        order = created[0]
        # the breach arrives AFTER submission (seeded at bar 5/6)
        _seed_round_trip_loss(rt, bars)
        rt.process_bar(bars[25])  # no fill yet (lag), trip happens
        assert rt.state is RuntimeState.HALTED
        rt.process_bar(bars[26])  # REFUSED — never fills
        live = rt.oms.order(order.order_id)  # authoritative live state
        assert not live.fills
        assert live.filled_quantity == Decimal("0")
        assert live.status.value in ("SUBMITTED", "ACKNOWLEDGED")
        pos = rt._positions.get(SYMBOL, PositionState(symbol=SYMBOL))
        assert pos.is_flat  # only the seeded round trip happened


class TestRestartRecovery:
    """Persistence/restart behaviour of the accepted interface."""

    def test_trip_survives_restart_and_refuses_start(self, tmp_path):
        """OPERATIONAL runtime (persistence + readiness gate): the
        breach trip is persisted (BLOCKER 12) — a restart REFUSES to
        start (critical-switch loud refusal), restores HALTED, and
        the reconstructed drawdown measure is identical."""
        ens, cal = _fit_world()
        store = tmp_path / "state"
        rt1 = TradingRuntime(
            _dd_config("dd-restart", 0.001).model_copy(
                update={"ephemeral_test_fixture": False}
            ),
            ens, calibrator=cal,
            state_store=ExecutionStateStore(store),
            readiness_gate=_ready_gate(),
        )
        rt1.start()
        bars = _bars(30)
        _run_bars(rt1, bars, 25)
        _seed_round_trip_loss(rt1, bars)
        rt1.process_bar(bars[25])
        assert rt1.state is RuntimeState.HALTED
        pre_dd = rt1._account_drawdown()
        assert pre_dd > 0.001

        if getattr(rt1, "_store", None) is not None:
            rt1._store.close()  # process death (F-03 single-writer lock)
        rt2 = TradingRuntime(
            _dd_config("dd-restart", 0.001).model_copy(
                update={"ephemeral_test_fixture": False}
            ),
            ens, calibrator=cal,
            state_store=ExecutionStateStore(store),
            readiness_gate=_ready_gate(),
        )
        with pytest.raises(RuntimeContractError,
                           match="critical kill switch"):
            rt2.start()
        assert rt2.state is RuntimeState.HALTED
        assert rt2.kill_switch.is_active(KillSwitchScope.ACCOUNT)
        # the measure is reconstructed identically from persisted
        # bars + OMS fills (no new persisted field)
        assert rt2._account_drawdown() == pre_dd

    def test_drawdown_recomputed_identically_after_restart(self, tmp_path):
        """A REAL governed trading session (organic fills through the
        full chain): after full state restore the peak equity and the
        drawdown fraction are IDENTICAL to the pre-restart values."""
        ens_cal = _fit_world()
        store = tmp_path / "state"
        rt1 = _operational("dd-organic", store, ens_cal=ens_cal)
        rt1.start()
        bars = _bars(60)
        for b in bars:
            rt1.process_bar(b)
        assert any(o.fills for o in rt1.oms.orders()), "needs fills"
        assert rt1.state is RuntimeState.RUNNING  # never breached 0.20
        pre_dd = rt1._account_drawdown()
        pre_peak = rt1._peak_account_equity()
        assert pre_dd is not None and pre_dd >= 0.0

        if getattr(rt1, "_store", None) is not None:
            rt1._store.close()  # process death (F-03 single-writer lock)
        rt2 = _operational("dd-organic", store, ens_cal=ens_cal)
        rt2.start()
        assert rt2.restarted
        assert rt2._peak_account_equity() == pre_peak
        assert rt2._account_drawdown() == pre_dd
