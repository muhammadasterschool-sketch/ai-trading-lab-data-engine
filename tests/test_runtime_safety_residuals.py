"""Batch 6 acceptance tests — runtime safety residuals + snapshot
compat (RED-first: these FAIL on the pre-fix code).

Defects being closed (readiness report §0D findings register; ranked
RUN-ST-1 > RUN-CA-1 > RUN-PM-1/RUN-OBS-1/RUN-DA-1, plus the §0H
snapshot-compat limitation recorded with Batch 2):

- RUN-ST-1 (MED): in-session data staleness was HARDCODED
  always-fresh (``last_bar_age_bars=0`` at every risk-context
  construction site) and NO wall-clock feed watchdog existed
  (pre-start freshness IS enforced by the operational feed gate, but
  once a session was running a stalled/lagged feed was invisible:
  the runtime kept evaluating decisions as if the newest bar were
  current).

- RUN-CA-1 (MED): NO operator cancel / manual-close API existed —
  an operator could not cancel a pending order or liquidate a
  position directly, and after a terminal HALT every in-flight
  protection exit was frozen with no escape hatch (bars refused ⇒
  exit orders could never fill).

- RUN-PM-1 (LOW): the ``partial_fill_events`` metric counted the
  COMPLETING fill of an order as a partial-fill event (the check
  read the caller's PRE-batch order snapshot, whose remaining
  quantity was still positive).

- RUN-DA-1 (LOW): dead attribute
  ``TradingRuntime._entry_orders_by_symbol`` (written once in
  ``__init__``, never read, never updated).

- RUN-OBS-1 (LOW): exit-path risk rejections were ledgered
  (``RISK_ASSESSMENT_FAIL``) but the failed-checks tuple returned by
  ``_execute_plan`` was DISCARDED by ``_submit_protection_exits`` —
  ``BarOutcome.risk_failed_checks`` never surfaced WHY a protective
  exit was refused.

- Snapshot compat (§0H limitation): the config digest covers the
  FULL ``RuntimeConfig`` dump, so every config-schema evolution
  (e.g. §0H adding ``max_account_drawdown_fraction``) changes the
  digest of an UNCHANGED session — pre-evolution snapshots become
  unloadable with an opaque "config_digest mismatch" refusal.

ACCEPTED INTERFACES (implemented in this batch):

1. RUN-ST-1 — ``RuntimeConfig.max_feed_staleness_seconds``
   (Optional[int], default None = watchdog DISABLED for
   deterministic-replay compatibility; explicit int >= 1 enables an
   in-session wall-clock watchdog) + an injectable ``wall_clock``
   seam on ``TradingRuntime``. On a stale bar (wall-clock age of the
   bar's timestamp strictly beyond the limit) the bar is still
   ADMITTED (fills, TTL, drawdown enforcement, protective exits and
   persistence all continue) but the prediction/decision/entry
   chain is SKIPPED (new exposure refused, fail closed), a
   ``FEED_STALE_BLOCK`` incident is ledgered and the
   ``feed_stale_bars`` counter increments. The broker bridge's
   external-order risk context derives ``last_bar_age_bars`` from
   the SAME wall clock when the watchdog is enabled (stale feed ⇒
   ``data_staleness`` fails closed for external submissions).

2. RUN-CA-1 — ``TradingRuntime.operator_cancel_order(order_id, *,
   reason)`` (live orders only; refused on unknown/terminal orders
   and in EXECUTION_UNCERTAIN/RECOVERY_REQUIRED/
   RECONCILIATION_REQUIRED states per §28; works under HALT) and
   ``TradingRuntime.operator_close_position(symbol=None, *,
   reason)`` (RUNNING: submits a MANUAL_CLOSE order through the
   AUTHORITATIVE gate→OMS path that settles on later bars; HALTED:
   immediate ledgered settlement at the latest admitted bar — the
   operator escape hatch for frozen protection; other non-trading
   states refuse fail-closed).

3. RUN-PM-1 — ``partial_fill_events`` increments only when the
   order STILL has a remainder after the applied fill (the live OMS
   order is re-queried, not the stale pre-batch snapshot).

4. RUN-DA-1 — the dead attribute is removed.

5. RUN-OBS-1 — ``_submit_protection_exits`` returns
   ``(orders, failed_checks)`` and the bar outcome's
   ``risk_failed_checks`` includes EXIT-path rejections.

6. Snapshot compat — ``SNAPSHOT_CONFIG_EVOLUTION`` (ordered
   post-formula config-field additions) +
   ``RuntimeConfig.allow_snapshot_config_evolution`` (default
   False). A digest mismatch that decomposes EXACTLY into known
   schema evolution (legacy digest recomputation / persisted config
   view) refuses by DEFAULT with a precise, actionable message;
   with the explicit operator opt-in the session resumes and the
   evolution is ledgered as ``SNAPSHOT_CONFIG_EVOLVED``. Any
   SHARED-field value change still refuses (never silently
   continues under a different identity). New snapshots persist the
   full config view inside the identity block for exact future
   decomposition.

These tests FAIL on the pre-fix code and must pass after it.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from data_engine.paper.simulator import ExecutionRealism
from data_engine.runtime import (
    ExecutionStateStore,
    RuntimeConfig,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import prefixed_hash
from data_engine.runtime.pnl import PositionState
from data_engine.runtime.decision import DecisionAction

# Reuse the deterministic world builders from the E2E module.
from test_runtime_e2e import T0, _bars, _fit_world
from test_runtime_account_drawdown import (
    INITIAL,
    QTY,
    SYMBOL,
    _dd_config,
    _plan,
    _run_bars,
    _seed_order_fill,
)
from test_runtime_recovery_integration import (
    _op_config,
    _operational,
    _ready_gate,
)

#: The ordered post-formula config additions (must mirror
#: SNAPSHOT_CONFIG_EVOLUTION in the implementation).
EVOLVED_FIELDS = (
    "max_account_drawdown_fraction",
    "max_feed_staleness_seconds",
    "allow_snapshot_config_evolution",
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _stale_config(session, limit, max_units="1000", dd_limit=0.20):
    """No-trade fixture config with the staleness watchdog ON."""
    return _dd_config(session, dd_limit, max_units=max_units).model_copy(
        update={"max_feed_staleness_seconds": limit}
    )


def _holder(t):
    """Mutable injected wall clock."""
    state = {"t": t}

    def clock():
        return state["t"]

    def set_to(new_t):
        state["t"] = new_t

    return clock, set_to


def _runtime(session, config=None, realism=None, wall_clock=None):
    ens, cal = _fit_world()
    rt = TradingRuntime(
        config if config is not None else _dd_config(session, 0.20),
        ens, calibrator=cal, realism=realism, wall_clock=wall_clock,
    )
    rt.start()
    return rt


def _seed_pending_order(rt, plan, bar_index, corr):
    """Seed one FULLY risk-approved, SUBMITTED, ACKNOWLEDGED but
    UNFILLED order through the real OMS path (deterministic)."""
    from data_engine.runtime import RiskContext

    position = rt._positions.get(SYMBOL, PositionState(symbol=SYMBOL))
    ctx = RiskContext(
        equity=INITIAL,
        current_units=position.quantity,
        reference_price=Decimal(str(rt._bars[bar_index]["close"])),
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
    return order


def _seed_position(rt, bars, bar_i=5, qty=QTY):
    """Seed a FILLED long position of ``qty`` at bar ``bar_i``'s
    close (through the real OMS path)."""
    px = Decimal(str(bars[bar_i]["close"]))
    order = _seed_order_fill(
        rt,
        _plan("seed-pos", DecisionAction.BUY, qty, px,
              px - Decimal("2"), px + Decimal("4")),
        px, bar_i, "corr-seed-pos",
    )
    return order, rt._positions[SYMBOL]


def _incident_types(rt):
    return [e.event_type for e in rt.ledgers.events(ledger="incident")]


# ════════════════════════════════════════════════════════════════════
# 1. RUN-ST-1 — in-session staleness watchdog
# ════════════════════════════════════════════════════════════════════

class TestStalenessWatchdogConfig:
    def test_watchdog_disabled_by_default(self):
        """Default None: deterministic replay semantics preserved."""
        cfg = _dd_config("st-default", 0.20)
        assert cfg.max_feed_staleness_seconds is None

    def test_watchdog_limit_validation(self):
        base = _dd_config("st-val", 0.20).model_dump()
        for bad in (0, -5, True):
            with pytest.raises((RuntimeContractError, ValidationError)):
                RuntimeConfig.model_validate(
                    {**base, "max_feed_staleness_seconds": bad}
                )
        cfg = RuntimeConfig.model_validate(
            {**base, "max_feed_staleness_seconds": 1}
        )
        assert cfg.max_feed_staleness_seconds == 1


class TestInSessionStalenessWatchdog:
    def test_stale_bar_blocks_new_exposure_but_is_admitted(self):
        """A bar whose wall-clock age strictly exceeds the limit is
        ADMITTED (accepted=True — fills/accounting continue) but the
        prediction/decision chain is skipped: no prediction artifact,
        NO_TRADE reason names staleness, and the FEED_STALE_BLOCK
        incident + feed_stale_bars counter fire. 16 bars cross the
        warm-up threshold, so without the fix the chain WOULD run."""
        clock, _ = _holder(T0 + timedelta(hours=10))
        rt = _runtime(
            "st-block", config=_stale_config("st-block", 300),
            wall_clock=clock,
        )
        bars = _bars(30)
        outcomes = [rt.process_bar(b) for b in bars[:16]]

        assert len(rt._bars) == 16
        for o in outcomes:
            assert o.accepted is True
            assert o.decision_action == "NO_TRADE"
            assert "stale" in o.decision_reason.lower()
            assert o.orders_created == ()
            assert o.prediction_probability is None
        assert rt._metrics.counters["feed_stale_bars"] == 16
        assert "FEED_STALE_BLOCK" in _incident_types(rt)
        pred_events = rt.ledgers.events(ledger="prediction")
        assert not any(
            e.event_type == "PREDICTION_ARTIFACT" for e in pred_events
        )

    def test_fresh_bars_still_decide_with_watchdog_on(self):
        """Watchdog on + clock near the bar timestamps: the normal
        chain runs (prediction artifacts produced past warm-up)."""
        clock, _ = _holder(T0)
        rt = _runtime(
            "st-fresh", config=_stale_config("st-fresh", 300),
            wall_clock=clock,
        )
        bars = _bars(30)
        outcomes = [rt.process_bar(b) for b in bars[:16]]

        pred_events = rt.ledgers.events(ledger="prediction")
        assert any(
            e.event_type == "PREDICTION_ARTIFACT" for e in pred_events
        )
        assert rt._metrics.counters["feed_stale_bars"] == 0
        assert "FEED_STALE_BLOCK" not in _incident_types(rt)
        assert all(
            "stale" not in o.decision_reason.lower() for o in outcomes
        )

    def test_watchdog_recovers_when_feed_catches_up(self):
        """Stale bars block decisions; when the feed catches up,
        decisions resume on the next admitted bar."""
        clock, set_to = _holder(T0 + timedelta(hours=10))
        rt = _runtime(
            "st-resume", config=_stale_config("st-resume", 300),
            wall_clock=clock,
        )
        bars = _bars(30)
        for b in bars[:14]:
            rt.process_bar(b)
        assert rt._metrics.counters["feed_stale_bars"] == 14

        set_to(T0 + timedelta(seconds=300 * 14))
        rt.process_bar(bars[14])
        assert rt._metrics.counters["feed_stale_bars"] == 14  # no new
        pred_events = rt.ledgers.events(ledger="prediction")
        assert any(
            e.event_type == "PREDICTION_ARTIFACT" for e in pred_events
        )

    def test_stale_bar_still_settles_inflight_orders(self):
        """In-flight orders continue to FILL on stale bars — the
        watchdog blocks NEW exposure, never in-flight settlement."""
        clock, _ = _holder(T0 + timedelta(hours=10))
        rt = _runtime("st-inflight", config=_stale_config("st-inflight", 300))
        bars = _bars(30)
        _run_bars(rt, bars, 6)
        ref = Decimal(str(bars[5]["close"]))
        order = _seed_pending_order(
            rt,
            _plan("st-pend", DecisionAction.BUY, QTY, ref,
                  ref - Decimal("2"), ref + Decimal("4")),
            5, "corr-st-pend",
        )
        rt._wall_clock = clock  # far future: every later bar is stale
        rt.process_bar(bars[6])  # latency bar for the seeded order
        live = rt._oms.order(order.order_id)
        assert live.status.value in ("FILLED", "PARTIALLY_FILLED")
        assert rt._metrics.counters["fills"] >= 1

    def test_stale_bar_still_submits_protective_exits(self):
        """Protection exits are risk-reduction: an SL breach on a
        STALE bar still submits the closing order."""
        clock, _ = _holder(T0 + timedelta(hours=10))
        rt = _runtime("st-exit", config=_stale_config("st-exit", 300))
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_position(rt, bars, 5)
        # SL below entry (geometry) and above the trigger bar's
        # natural low (a real breach, OHLC-consistent)
        sl = Decimal(str(bars[25]["low"])) + Decimal("0.05")
        position = rt._positions[SYMBOL]
        position, _ = rt._exit_manager.set_stop_loss(
            position, sl, "corr-st-sl", bars[5]["timestamp"]
        )
        rt._positions[SYMBOL] = position
        rt._wall_clock = clock

        trigger = dict(bars[25])  # low breaches the stop naturally
        outcome = rt.process_bar(trigger)
        assert outcome.accepted is True
        assert "stale" in outcome.decision_reason.lower()
        assert outcome.orders_created != ()
        exit_ids = {oid for oid, _, _ in rt._pending_exits.values()}
        assert exit_ids == set(outcome.orders_created)

    def test_stale_bar_enforcement_survives_halting_drawdown(self):
        """Price-driven drawdown enforcement still HALTS on a stale
        bar (the watchdog never weakens the account-equity guard).
        Seeded 200-unit long + a 30-point crash on the stale bar =
        6% account loss vs a 5% limit — a strict price-driven
        breach."""
        from data_engine.runtime import KillSwitchScope

        clock, _ = _holder(T0 + timedelta(hours=10))
        rt = _runtime(
            "st-dd", config=_stale_config("st-dd", 300, dd_limit=0.05)
        )
        bars = _bars(30)
        _run_bars(rt, bars, 6)
        _seed_position(rt, bars, 5, qty=Decimal("200"))
        rt._wall_clock = clock
        crash_bar = dict(bars[6])
        crash_close = float(
            Decimal(str(bars[6]["close"])) - Decimal("30")
        )
        crash_bar["close"] = crash_close
        crash_bar["low"] = crash_close - 0.25  # keep OHLC consistent
        rt.process_bar(crash_bar)
        assert rt._state is RuntimeState.HALTED
        assert rt._kill_switch.is_active(KillSwitchScope.ACCOUNT, None)


class TestBridgeStalenessHonesty:
    """External (side-band bridge) orders see the honest wall-clock
    bar age when the watchdog is enabled."""

    def _session(self, tmp_path, clock, limit=300):
        from data_engine.brokers.models import InstrumentSpec
        from data_engine.brokers.redaction import BrokerCredential
        from data_engine.runtime import attach_runtime_paper_session
        from data_engine.runtime.broker_execution import (
            RUNTIME_PAPER_VENUE_ID,
        )

        rt = _runtime(
            "st-bridge", config=_stale_config("st-bridge", limit),
            wall_clock=clock,
        )
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        session = attach_runtime_paper_session(
            rt,
            account_id="paper-acct-1",
            journal_path=tmp_path / "journal.json",
            clock=lambda: T0 + timedelta(hours=6),
            instruments={
                SYMBOL: InstrumentSpec(
                    broker_id=RUNTIME_PAPER_VENUE_ID,
                    symbol=SYMBOL, broker_symbol=SYMBOL,
                    base_asset="TEST", quote_asset="USD",
                    tick_size=Decimal("0.01"),
                    lot_step=Decimal("0.0001"),
                    min_quantity=Decimal("0.0001"),
                    max_quantity=Decimal("100"),
                    min_notional=Decimal("0"),
                ),
            },
        )
        session.connect(
            BrokerCredential("paper-acct-1", "opaque-play-money-secret")
        )
        return rt, session, bars

    def _request(self, corr, bars, bar_i=24):
        from data_engine.brokers.models import (
            OrderKind,
            OrderRequest,
            Side,
            TimeInForce,
        )

        ref = Decimal(str(bars[bar_i]["close"]))
        return OrderRequest(
            client_order_id=f"coi-{corr}",
            account_id="paper-acct-1",
            symbol=SYMBOL,
            side=Side.BUY,
            order_kind=OrderKind.MARKET,
            quantity=Decimal("10"),
            price=None,
            stop_price=None,
            time_in_force=TimeInForce.GTC,
            stop_loss=ref - Decimal("2"),
            take_profit=ref + Decimal("4"),
            reduce_only=False,
        )

    def test_stale_feed_refuses_external_orders(self, tmp_path):
        """Watchdog ON + clock far past the latest admitted bar: the
        bridged risk context reports the honest bar age and the
        ``data_staleness`` mandatory check FAILS CLOSED."""
        from data_engine.brokers.errors import OrderRefusedError

        clock, _ = _holder(T0 + timedelta(hours=10))
        rt, session, bars = self._session(tmp_path, clock)
        with pytest.raises(OrderRefusedError):
            session.submit_order(self._request("stale-ext", bars))

    def test_fresh_feed_admits_external_orders(self, tmp_path):
        """Watchdog ON + clock near the latest bar: external orders
        pass exactly as before (age 0)."""
        clock, _ = _holder(T0 + timedelta(seconds=300 * 25))
        rt, session, bars = self._session(tmp_path, clock)
        ack = session.submit_order(self._request("fresh-ext", bars))
        assert ack.client_order_id == "coi-fresh-ext"


# ════════════════════════════════════════════════════════════════════
# 2. RUN-PM-1 — partial fill metric counts only PARTIAL fills
# ════════════════════════════════════════════════════════════════════

class TestPartialFillMetric:
    def test_completing_fill_not_counted_as_partial(self):
        """Order of 100 units fills 60 then 40 across two bars: the
        metric increments ONCE (the partial fill), not twice (the
        pre-fix code counted the completing fill too)."""
        realism = ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0"),
            impact_rate=Decimal("0"),
            participation_cap=Decimal("0.6"),
        )
        rt = _runtime("pm", realism=realism)
        bars = _bars(30, volume=100.0)
        _run_bars(rt, bars, 6)
        ref = Decimal(str(bars[5]["close"]))
        order = _seed_pending_order(
            rt,
            _plan("pm-fill", DecisionAction.BUY, Decimal("100"), ref,
                  ref - Decimal("2"), ref + Decimal("4")),
            5, "corr-pm",
        )
        rt.process_bar(bars[6])  # fills 60 (capacity = 0.6*100)
        live = rt._oms.order(order.order_id)
        assert live.status.value == "PARTIALLY_FILLED"
        assert rt._metrics.counters["partial_fill_events"] == 1
        rt.process_bar(bars[7])  # fills the remaining 40
        live = rt._oms.order(order.order_id)
        assert live.status.value == "FILLED"
        assert rt._metrics.counters["partial_fill_events"] == 1


# ════════════════════════════════════════════════════════════════════
# 3. RUN-DA-1 — dead attribute removal
# ════════════════════════════════════════════════════════════════════

class TestDeadAttribute:
    def test_dead_entry_orders_map_removed(self):
        rt = _runtime("da")
        assert not hasattr(rt, "_entry_orders_by_symbol")


# ════════════════════════════════════════════════════════════════════
# 4. RUN-OBS-1 — exit-path risk failures surface in the bar outcome
# ════════════════════════════════════════════════════════════════════

class TestExitRiskObservability:
    def test_exit_risk_failure_surfaced_in_outcome(self):
        """A protective exit whose risk gate FAILS (liquidity: the
        closing quantity exceeds 10% of a thin bar) is refused AND
        the failed check appears in BarOutcome.risk_failed_checks
        (pre-fix: silently discarded)."""
        rt = _runtime("obs")
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _seed_position(rt, bars, 5)
        sl = Decimal(str(bars[25]["low"])) + Decimal("0.05")
        position = rt._positions[SYMBOL]
        position, _ = rt._exit_manager.set_stop_loss(
            position, sl, "corr-obs-sl", bars[5]["timestamp"]
        )
        rt._positions[SYMBOL] = position

        trigger = dict(bars[25])
        trigger["volume"] = 1  # closing QTY exceeds 10% of volume
        outcome = rt.process_bar(trigger)
        assert outcome.accepted is True
        assert "liquidity" in outcome.risk_failed_checks
        plan_events = rt.ledgers.events(ledger="trade_plan")
        assert any(
            e.event_type == "RISK_ASSESSMENT_FAIL" for e in plan_events
        )
        assert SYMBOL not in rt._pending_exits


# ════════════════════════════════════════════════════════════════════
# 5. RUN-CA-1 — operator cancel / manual close
# ════════════════════════════════════════════════════════════════════

class TestOperatorCancel:
    def _rt_with_pending(self, session="ca-cancel"):
        rt = _runtime(session)
        bars = _bars(30)
        _run_bars(rt, bars, 6)
        ref = Decimal(str(bars[5]["close"]))
        order = _seed_pending_order(
            rt,
            _plan("ca-p", DecisionAction.BUY, QTY, ref,
                  ref - Decimal("2"), ref + Decimal("4")),
            5, f"corr-{session}",
        )
        return rt, bars, order

    def test_cancel_requires_reason(self):
        rt, _, order = self._rt_with_pending()
        with pytest.raises(RuntimeContractError):
            rt.operator_cancel_order(order.order_id, reason="  ")

    def test_cancel_unknown_order_refused(self):
        rt, _, _ = self._rt_with_pending()
        with pytest.raises(RuntimeContractError, match="unknown order"):
            rt.operator_cancel_order("no-such-order", reason="cleanup")

    def test_cancel_terminal_order_refused(self):
        rt, bars, _ = self._rt_with_pending()
        _seed_position(rt, bars, 5)
        filled = rt._oms.orders()[-1]
        with pytest.raises(RuntimeContractError, match="terminal"):
            rt.operator_cancel_order(filled.order_id, reason="cleanup")

    def test_cancel_live_order(self):
        rt, _, order = self._rt_with_pending()
        rt._pending_protection[order.order_id] = (
            Decimal("98"), Decimal("106"), "corr-prot"
        )
        result = rt.operator_cancel_order(
            order.order_id, reason="operator test cancel"
        )
        assert result["status"] == "CANCELLED"
        assert rt._oms.order(order.order_id).status.value == "CANCELLED"
        assert order.order_id not in rt._pending_protection
        assert rt._metrics.counters["orders_operator_cancelled"] == 1
        assert "ORDER_CANCELLED_OPERATOR" in _incident_types(rt)

    def test_cancel_works_under_halt(self):
        rt, _, order = self._rt_with_pending()
        rt.halt("operator halt test")
        rt.operator_cancel_order(order.order_id, reason="post-halt clean")
        assert rt._oms.order(order.order_id).status.value == "CANCELLED"

    def test_cancel_refused_while_execution_uncertain(self):
        rt, _, order = self._rt_with_pending()
        rt._state = RuntimeState.EXECUTION_UNCERTAIN
        with pytest.raises(RuntimeContractError,
                           match="EXECUTION_UNCERTAIN"):
            rt.operator_cancel_order(order.order_id, reason="cleanup")

    def test_cancel_exit_order_clears_pending_exits(self):
        rt, bars, _ = self._rt_with_pending()
        _, position = _seed_position(rt, bars, 5)
        ref = Decimal(str(bars[5]["close"]))
        exit_order = _seed_pending_order(
            rt,
            _plan("ca-x", DecisionAction.SELL, QTY, ref, None, None),
            5, "corr-ca-x",
        )
        rt._pending_exits[SYMBOL] = (
            exit_order.order_id, "SL_HIT", position,
        )
        rt.operator_cancel_order(
            exit_order.order_id, reason="operator replaces exit"
        )
        assert SYMBOL not in rt._pending_exits
        assert rt._oms.order(exit_order.order_id).status.value == \
            "CANCELLED"


class TestOperatorManualClose:
    def _rt_with_position(self, session="ca-close"):
        rt = _runtime(session)
        bars = _bars(30)
        _run_bars(rt, bars, 25)
        _, position = _seed_position(rt, bars, 5)
        return rt, bars, position

    def test_close_requires_reason(self):
        rt, _, _ = self._rt_with_position()
        with pytest.raises(RuntimeContractError):
            rt.operator_close_position(reason="")

    def test_close_flat_position_refused(self):
        rt, _, _ = self._rt_with_position()
        rt._positions[SYMBOL] = PositionState(symbol=SYMBOL)
        with pytest.raises(RuntimeContractError, match="flat"):
            rt.operator_close_position(reason="liquidate")

    def test_close_running_submits_authoritative_order(self):
        rt, bars, position = self._rt_with_position()
        result = rt.operator_close_position(reason="operator reduces")
        assert result["mode"] == "submitted"
        order = rt._oms.order(result["order_id"])
        assert order.side == "SELL"
        assert order.quantity == QTY
        assert "ORDER_MANUAL_CLOSE_SUBMITTED" in _incident_types(rt)
        # settles through the normal bar path (latency model):
        # continue AFTER the latest admitted bar
        _run_bars(rt, bars[25:30], 5)
        assert rt._positions[SYMBOL].is_flat
        assert rt._oms.order(result["order_id"]).status.value == "FILLED"

    def test_close_running_risk_failure_refused_loudly(self):
        rt, bars, position = self._rt_with_position()
        thin = dict(bars[24])
        thin["volume"] = 1
        rt._bars[-1] = thin
        with pytest.raises(RuntimeContractError, match="liquidity"):
            rt.operator_close_position(reason="cannot close thin book")

    def test_close_halted_settles_immediately(self):
        rt, bars, position = self._rt_with_position()
        rt.halt("operator halt test")
        result = rt.operator_close_position(reason="halted liquidation")
        assert result["mode"] == "settled"
        order = rt._oms.order(result["order_id"])
        assert order.status.value == "FILLED"
        assert len(order.fills) == 1
        fill = order.fills[0]
        # MARKET close of a LONG: latest bar open MINUS half spread
        expected = Decimal(str(bars[24]["open"])) - Decimal("0.02")
        assert fill.price == expected
        assert fill.quantity == QTY
        # position flat NOW with the loss realized (below entry)
        assert rt._positions[SYMBOL].is_flat
        assert rt._positions[SYMBOL].realized_pnl < 0
        assert rt._metrics.counters["orders_operator_closed"] == 1
        assert "OPERATOR_MANUAL_CLOSE" in _incident_types(rt)

    def test_close_halted_cancels_frozen_exit_orders(self):
        rt, bars, position = self._rt_with_position()
        ref = Decimal(str(bars[5]["close"]))
        exit_order = _seed_pending_order(
            rt,
            _plan("ca-fx", DecisionAction.SELL, QTY, ref, None, None),
            5, "corr-ca-fx",
        )
        rt._pending_exits[SYMBOL] = (exit_order.order_id, "SL_HIT",
                                     position)
        rt.halt("operator halt test")
        result = rt.operator_close_position(reason="full liquidation")
        assert result["mode"] == "settled"
        assert rt._positions[SYMBOL].is_flat
        assert rt._oms.order(exit_order.order_id).status.value == \
            "CANCELLED"
        assert SYMBOL not in rt._pending_exits

    def test_close_refused_while_execution_uncertain(self):
        rt, _, _ = self._rt_with_position()
        rt._state = RuntimeState.EXECUTION_UNCERTAIN
        with pytest.raises(RuntimeContractError,
                           match="EXECUTION_UNCERTAIN"):
            rt.operator_close_position(reason="liquidate")

    def test_close_refused_before_start(self):
        ens, cal = _fit_world()
        rt = TradingRuntime(_dd_config("ca-init", 0.20), ens,
                            calibrator=cal)
        with pytest.raises(RuntimeContractError):
            rt.operator_close_position(reason="liquidate")


# ════════════════════════════════════════════════════════════════════
# 6. Snapshot config compatibility (§0H limitation)
# ════════════════════════════════════════════════════════════════════

def _legacy_digest(config_view):
    return prefixed_hash(
        "rtcfg.",
        {"kind": "runtime_config_identity", "config": config_view},
    )


def _legacy_snapshot(tmp_path, session):
    """Run an operational session, then rewrite its persisted
    identity to the PRE-evolution shape: no ``config`` view, digest
    over the old field set (exactly what a pre-§0H snapshot looked
    like). Returns the matching current config."""
    rt = _operational(session, tmp_path / "state")
    rt.start()
    _run_bars(rt, _bars(30), 8)
    cfg = _op_config(session)
    current = cfg.model_dump(mode="json")
    legacy_view = {
        k: v for k, v in current.items() if k not in EVOLVED_FIELDS
    }
    snap_path = tmp_path / "state" / "state.json"
    payload = json.loads(snap_path.read_text(encoding="utf-8"))
    identity = payload["state"]["identity"]
    identity.pop("config", None)
    identity["config_digest"] = _legacy_digest(legacy_view)
    snap_path.write_text(json.dumps(payload), encoding="utf-8")
    return cfg


class TestSnapshotConfigCompat:
    def test_same_config_restart_still_works(self, tmp_path):
        rt = _operational("snap-same", tmp_path / "state")
        rt.start()
        _run_bars(rt, _bars(30), 8)
        ens, cal = _fit_world()
        if getattr(rt, "_store", None) is not None:
            rt._store.close()  # process death (F-03 single-writer lock)
        rt2 = TradingRuntime(
            _op_config("snap-same"), ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "state"),
            readiness_gate=_ready_gate(),
        )
        rt2.start()
        assert rt2.restarted is True
        assert len(rt2._bars) == 8

    def test_shared_field_change_still_refused(self, tmp_path):
        rt = _operational("snap-shared", tmp_path / "state")
        rt.start()
        _run_bars(rt, _bars(30), 8)
        ens, cal = _fit_world()
        changed = _op_config("snap-shared").model_copy(
            update={"ttl_bars": 9}
        )
        if getattr(rt, "_store", None) is not None:
            rt._store.close()  # process death (F-03 single-writer lock)
        rt2 = TradingRuntime(
            changed, ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "state"),
            readiness_gate=_ready_gate(),
        )
        with pytest.raises(RuntimeContractError, match="identity"):
            rt2.start()
        assert rt2._state is RuntimeState.RECOVERY_REQUIRED

    def test_new_snapshots_persist_config_view(self, tmp_path):
        rt = _operational("snap-view", tmp_path / "state")
        rt.start()
        _run_bars(rt, _bars(30), 8)
        payload = json.loads(
            (tmp_path / "state" / "state.json").read_text(encoding="utf-8")
        )
        identity = payload["state"]["identity"]
        assert isinstance(identity.get("config"), dict)
        assert identity["config"]["session_id"] == "snap-view"

    def test_legacy_snapshot_default_refused_precisely(self, tmp_path):
        """A pre-evolution snapshot is refused by DEFAULT with a
        message naming the evolution and the opt-in — never the
        opaque generic digest mismatch."""
        cfg = _legacy_snapshot(tmp_path, "snap-legacy")
        ens, cal = _fit_world()
        rt2 = TradingRuntime(
            cfg, ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "state"),
            readiness_gate=_ready_gate(),
        )
        with pytest.raises(RuntimeContractError,
                            match="config schema evolved"):
            rt2.start()
        assert rt2._state is RuntimeState.RECOVERY_REQUIRED

    def test_legacy_snapshot_opt_in_resumes(self, tmp_path):
        """With the explicit operator opt-in the evolved-config
        snapshot RESUMES and the evolution is ledgered loudly."""
        cfg = _legacy_snapshot(tmp_path, "snap-optin")
        ens, cal = _fit_world()
        rt2 = TradingRuntime(
            cfg.model_copy(
                update={"allow_snapshot_config_evolution": True}
            ),
            ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "state"),
            readiness_gate=_ready_gate(),
        )
        rt2.start()
        assert rt2.restarted is True
        assert len(rt2._bars) == 8
        assert "SNAPSHOT_CONFIG_EVOLVED" in _incident_types(rt2)

    def test_evolution_flag_validation(self):
        base = _dd_config("snap-bool", 0.20).model_dump()
        for bad in ("yes", 1.5, 1):
            with pytest.raises((RuntimeContractError, ValidationError)):
                RuntimeConfig.model_validate(
                    {
                        **base,
                        "allow_snapshot_config_evolution": bad,
                    }
                )
