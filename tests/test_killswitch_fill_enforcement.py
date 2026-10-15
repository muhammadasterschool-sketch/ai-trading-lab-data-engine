"""Kill-switch FILL-time enforcement + terminal-HALT restart semantics.

Findings registered by the 2026-10-12 paper-runtime audit (executable
evidence probe: an in-flight order filled COMPLETELY on the bar after
a governing switch was active):

- RUN-KS-1 — a SYMBOL-scope switch did not stop in-flight orders
  (``_process_pending_orders`` never consulted the kill switch).
- RUN-KS-2 — an ORDER-scope switch had NO enforcement point anywhere
  (``KillSwitchManager.check(order_id=…)`` exists but no caller
  passed an order id).
- RUN-HALT-1 — an operator-halted session resumed RUNNING on restart
  (``start()`` special-cased only persisted DEGRADED).

Contract pinned by this module (fail closed):

- An in-flight order that would ADD exposure is CANCELLED — never
  filled — while ANY governing kill switch is active, with a ledgered
  ``ORDER_CANCELLED_KILL_SWITCH`` incident.
- A partially filled entry order's REMAINDER is cancelled; the
  already-filled part is retained (position unchanged).
- Risk-reducing EXIT orders remain permitted to fill under a switch
  (mirrors the risk gate's documented closing-order carve-out).
- A persisted HALTED runtime is TERMINAL: restart restores HALTED,
  never RUNNING; bars are refused.
- EXECUTION_UNCERTAIN is a non-trading state: bars are refused.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from test_runtime_e2e import _bars, _fit_world

from data_engine.paper.simulator import ExecutionRealism
from data_engine.runtime import (
    ExecutionStateStore,
    GATE_NAMES,
    GateEvidence,
    KillSwitchScope,
    PaperReadinessGate,
    RuntimeConfig,
    RuntimeState,
    TradingRuntime,
)
from data_engine.runtime.contracts import OrderLifecycle
from data_engine.runtime.pnl import PositionState

SYMBOL = "TEST/USD"


def _cfg(session):
    """Ephemeral unit-test fixture (machinery semantics, BLOCKER 1
    governance mark; operational restart semantics use _operational)."""
    return RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        ephemeral_test_fixture=True,
    )


def _operational(session, store_dir, ens_cal):
    """Fully-gated OPERATIONAL runtime (persistence mandatory)."""
    ens, cal = ens_cal
    gate = PaperReadinessGate()
    for name in GATE_NAMES:
        gate.submit(GateEvidence(
            gate=name, component=f"component:{name.lower()}",
            check="evidence_submitted",
            evidence="objective evidence on record", passed=True,
        ))
    cfg = RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
    )
    return TradingRuntime(
        cfg, ens, calibrator=cal,
        state_store=ExecutionStateStore(Path(store_dir)),
        readiness_gate=gate,
    )


def _partial_realism():
    """Realism producing genuine multi-bar partial fills (the risk
    gate's liquidity rule caps at 10% of volume; the participation cap
    then splits the order across bars)."""
    return ExecutionRealism(
        half_spread=Decimal("0.02"),
        commission_per_unit=Decimal("0.001"),
        impact_rate=Decimal("0.0001"),
        participation_cap=Decimal("0.01"),
        fill_lag_bars=1,
    )


def _run_until(rt, condition, bars):
    """Process bars until ``condition(rt)``; returns the last index
    processed (None when the condition never fired)."""
    for i, b in enumerate(bars):
        rt.process_bar(b)
        if condition(rt):
            return i
    return None


def _first_live_unfilled(rt, bars):
    """Index of the next bar after the first live, ZERO-fill order."""
    idx = _run_until(
        rt,
        lambda r: any(
            not o.is_terminal and o.filled_quantity == 0
            for o in r.oms.orders()
        ),
        bars,
    )
    live = [
        o for o in rt.oms.orders()
        if not o.is_terminal and o.filled_quantity == 0
    ]
    return idx, (live[0].order_id if live else None)


def _stage_long_with_stop(rt, bars, quantity=Decimal("50"),
                          entry_price=Decimal("100"),
                          stop=Decimal("95")):
    """Stage a REAL long position with a stop-loss through the
    authoritative PositionState core (deterministic, no RNG)."""
    entry_ts = bars[-1]["timestamp"]
    pos = PositionState(symbol=SYMBOL).apply_fill(
        fill_quantity=quantity, fill_price=entry_price, side="BUY",
        commission=Decimal("0.05"), slippage_cost=Decimal("0.10"),
        spread_cost=Decimal("0.10"), filled_at=entry_ts,
        source_event="staging-fill",
    )
    pos, _ = rt._exit_manager.set_stop_loss(
        pos, stop, "corr-staging", entry_ts
    )
    rt._positions[SYMBOL] = pos
    return pos, entry_ts


# ════════════════════════════════════════════════════════════════════
# RUN-KS-1 / RUN-KS-2 — kill-switch enforcement at FILL time
# ════════════════════════════════════════════════════════════════════

class TestKillSwitchFillEnforcement:

    def test_inflight_entry_cancelled_under_symbol_switch(self):
        """RUN-KS-1: a SYMBOL-scope switch must stop an in-flight
        ENTRY order — cancelled with a ledgered incident, never
        filled."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_cfg("ks-fe-1"), ens, calibrator=cal)
        rt.start()
        bars = _bars(120)
        idx, oid = _first_live_unfilled(rt, bars)
        assert oid, "deterministic world must produce an in-flight order"
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "audit: symbol stress", target=SYMBOL,
        )
        out = rt.process_bar(bars[idx + 1])
        order = rt.oms.order(oid)
        assert order.filled_quantity == 0, (
            "in-flight order acquired exposure AFTER the switch tripped"
        )
        assert order.status is OrderLifecycle.CANCELLED
        assert len(out.fills) == 0
        assert len(out.orders_created) == 0
        incidents = [e.event_type for e in rt.ledgers.events("incident")]
        assert "ORDER_CANCELLED_KILL_SWITCH" in incidents
        assert rt.metrics.counters["orders_killswitch_cancelled"] == 1
        assert rt.state is RuntimeState.RUNNING  # non-critical scope

    def test_inflight_entry_cancelled_under_order_scope_switch(self):
        """RUN-KS-2: an ORDER-scope switch must block its target order
        at fill time (previously no enforcement point existed)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_cfg("ks-fe-2"), ens, calibrator=cal)
        rt.start()
        bars = _bars(120)
        idx, oid = _first_live_unfilled(rt, bars)
        assert oid
        rt.trip_kill_switch(
            KillSwitchScope.ORDER, "audit: block this order", target=oid,
        )
        out = rt.process_bar(bars[idx + 1])
        order = rt.oms.order(oid)
        assert order.filled_quantity == 0
        assert order.status is OrderLifecycle.CANCELLED
        assert len(out.fills) == 0
        incidents = [e.event_type for e in rt.ledgers.events("incident")]
        assert "ORDER_CANCELLED_KILL_SWITCH" in incidents

    def_partially = None

    def test_partially_filled_remainder_cancelled_under_symbol_switch(self):
        """RUN-KS-1 (partial case): the REMAINDER is cancelled, the
        already-filled part is retained, and no further fill occurs."""
        ens, cal = _fit_world()
        rt = TradingRuntime(
            _cfg("ks-fe-4"), ens, calibrator=cal,
            realism=_partial_realism(),
        )
        rt.start()
        bars = _bars(120)
        idx = _run_until(
            rt,
            lambda r: any(
                o.status is OrderLifecycle.PARTIALLY_FILLED
                for o in r.oms.orders()
            ),
            bars,
        )
        assert idx is not None, "partial-fill world must produce one"
        partial = next(
            o for o in rt.oms.orders()
            if o.status is OrderLifecycle.PARTIALLY_FILLED
        )
        filled_before = partial.filled_quantity
        assert filled_before > 0
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "audit: symbol stress", target=SYMBOL,
        )
        out = rt.process_bar(bars[idx + 1])
        order = rt.oms.order(partial.order_id)
        assert order.filled_quantity == filled_before, (
            "remainder acquired additional fills after the switch tripped"
        )
        assert order.status is OrderLifecycle.CANCELLED
        assert len(out.fills) == 0
        order_events = [
            e.event_type for e in rt.ledgers.events("order")
        ]
        assert "ORDER_CANCELLED_AFTER_PARTIAL" in order_events
        incidents = [e.event_type for e in rt.ledgers.events("incident")]
        assert "ORDER_CANCELLED_KILL_SWITCH" in incidents

    def test_inflight_exit_order_fills_under_symbol_switch(self):
        """Carve-out preservation: a risk-reducing EXIT order still
        fills under a SYMBOL-scope switch (mirrors the risk gate's
        closing-order exemption — the switch blocks NEW exposure, not
        risk reduction)."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_cfg("ks-fe-3"), ens, calibrator=cal)
        rt.start()
        bars = _bars(22)
        for b in bars:
            rt.process_bar(b)
        assert not rt.oms.orders(), (
            "staging requires a quiet world (no in-flight orders)"
        )
        pos, entry_ts = _stage_long_with_stop(rt, bars)
        rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "audit: symbol stress", target=SYMBOL,
        )
        # Bar that breaks the stop → protective exit order submitted
        # through the gate's closing-order carve-out. The close
        # recovers so the price-drawdown check (limit 0.15) stays
        # green — only the LOW needs to touch the stop.
        t1 = entry_ts + timedelta(seconds=300)
        sl_bar = {
            "timestamp": t1, "open": 99.0, "high": 99.5,
            "low": 94.8, "close": 98.0, "volume": 5000.0,
        }
        rt.process_bar(sl_bar)
        pending = {oid for oid, _, _ in rt._pending_exits.values()}
        assert pending, "protective exit order must be submitted"
        exit_oid = pending.pop()
        # Next bar: the in-flight EXIT order must still FILL.
        t2 = t1 + timedelta(seconds=300)
        fill_bar = {
            "timestamp": t2, "open": 97.0, "high": 97.6,
            "low": 96.4, "close": 96.8, "volume": 5000.0,
        }
        rt.process_bar(fill_bar)
        exit_order = rt.oms.order(exit_oid)
        assert exit_order.status is OrderLifecycle.FILLED
        assert exit_order.filled_quantity == pos.quantity
        assert rt.positions[SYMBOL].quantity == 0
        assert rt.kill_switch.is_active(
            KillSwitchScope.SYMBOL, target=SYMBOL,
        )


# ════════════════════════════════════════════════════════════════════
# RUN-HALT-1 — persisted HALTED is terminal
# ════════════════════════════════════════════════════════════════════

class TestTerminalHaltRestart:

    def test_restart_after_operator_halt_stays_halted(self, tmp_path):
        """RUN-HALT-1: an operator-halted session restores as HALTED —
        restart never resumes a terminal safe stop."""
        ens_cal = _fit_world()
        rt = _operational("ks-halt", tmp_path / "st", ens_cal)
        rt.start()
        for b in _bars(20)[:12]:
            rt.process_bar(b)
        rt.halt("operator stop (audit)")
        assert rt.state is RuntimeState.HALTED

        rt2 = _operational("ks-halt", tmp_path / "st", ens_cal)
        rt2.start()
        assert rt2.restarted is True
        assert rt2.state is RuntimeState.HALTED, (
            "restart resumed an operator-halted session into RUNNING"
        )
        incidents = [e.event_type for e in rt2.ledgers.events("incident")]
        assert "RUNTIME_RESUMED_HALTED" in incidents
        out = rt2.process_bar(_bars(1, start=100.0, t_offset=12)[0])
        assert out.accepted is False
        assert out.runtime_state == "HALTED"
        assert not out.orders_created and not out.fills

    def test_critical_switch_restart_refusal_still_loud(self, tmp_path):
        """Regression guard: a persisted HALTED + critical switch
        restart still raises the LOUD critical-switch refusal (the
        terminal-HALT restore must not mask the stronger error)."""
        ens_cal = _fit_world()
        rt = _operational("ks-crit", tmp_path / "st", ens_cal)
        rt.start()
        for b in _bars(20)[:12]:
            rt.process_bar(b)
        rt.trip_kill_switch(
            KillSwitchScope.GLOBAL, "operator halt — audit",
        )
        assert rt.state is RuntimeState.HALTED
        rt2 = _operational("ks-crit", tmp_path / "st", ens_cal)
        with pytest.raises(Exception, match="kill switch"):
            rt2.start()
        assert rt2.state is RuntimeState.HALTED


# ════════════════════════════════════════════════════════════════════
# Uncertain execution state — bars refused (pin)
# ════════════════════════════════════════════════════════════════════

class TestUncertainStateRefusal:

    def test_execution_uncertain_refuses_subsequent_bars(self):
        """EXECUTION_UNCERTAIN is non-trading: after an execution
        adapter failure the NEXT bar is refused outright."""
        ens, cal = _fit_world()
        rt = TradingRuntime(_cfg("ks-fe-6"), ens, calibrator=cal)
        rt.start()
        bars = _bars(120)
        idx, oid = _first_live_unfilled(rt, bars)
        assert oid, "a pending order is needed to trigger the failure"

        class ExplodingAdapter:
            realism = rt._execution.realism

            def execute(self, *a, **kw):
                raise TimeoutError("gateway timeout")

        rt._execution = ExplodingAdapter()
        rt.process_bar(bars[idx + 1])
        assert rt.state is RuntimeState.EXECUTION_UNCERTAIN
        out = rt.process_bar(bars[idx + 2])
        assert out.accepted is False
        assert out.runtime_state == "EXECUTION_UNCERTAIN"
        assert not out.orders_created and not out.fills
