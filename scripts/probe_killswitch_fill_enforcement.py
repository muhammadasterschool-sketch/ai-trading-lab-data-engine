#!/usr/bin/env python3
"""Evidence probe — paper-order enforcement audit (session 2026-10-12).

Probe A (RUN-KS-1 candidate): a live order is in flight when a
SYMBOL-scope kill switch trips. Does the order still FILL on the next
bar? (_process_pending_orders never consults the kill switch.)

Probe B (RUN-KS-2 candidate): an ORDER-scope switch is tripped for a
specific live order id. Does that order still fill?

Probe C (RUN-HALT-1 candidate): an operational runtime is HALTED by
the operator (no critical kill switch), then restarted with the same
store/config/ensemble. Does start() resume RUNNING (contradicting the
"terminal safe stop" contract) or refuse?

Read-only diagnostics against the repo's deterministic test world.
"""
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

REPO = Path("/home/z/my-project/workspace/repo")
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from test_runtime_e2e import _bars, _fit_world  # noqa: E402

from data_engine.runtime import (  # noqa: E402
    ExecutionStateStore,
    GATE_NAMES,
    GateEvidence,
    KillSwitchScope,
    PaperReadinessGate,
    RuntimeConfig,
    RuntimeState,
    TradingRuntime,
)

SYMBOL = "TEST/USD"


def _ephemeral(session):
    ens, cal = _fit_world()
    cfg = RuntimeConfig(
        symbol=SYMBOL, timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        ephemeral_test_fixture=True,
    )
    return TradingRuntime(cfg, ens, calibrator=cal)


def _operational(session, store_dir, ens_cal):
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


def _first_live_unfilled(rt, bars):
    """Process bars until a live order with ZERO fills exists; return
    (index_of_next_bar, order_id) or (None, None)."""
    for i, b in enumerate(bars):
        rt.process_bar(b)
        live = [
            o for o in rt.oms.orders()
            if not o.is_terminal and o.filled_quantity == 0
        ]
        if live:
            return i + 1, live[0].order_id
    return None, None


def probe_kill_switch(scope_factory, label):
    print(f"\n=== {label} ===")
    rt = _ephemeral(f"probe-{label}")
    rt.start()
    bars = _bars(120)
    next_i, order_id = _first_live_unfilled(rt, bars)
    if order_id is None:
        print("NO live unfilled order appeared in 120 bars — probe "
              "inconclusive (world too quiet)")
        return
    before = rt.oms.order(order_id)
    print(f"live order {order_id[:20]}… status={before.status.value} "
          f"qty={before.quantity} fills={len(before.fills)}")
    scope_factory(rt, order_id)
    out = rt.process_bar(bars[next_i])
    after = rt.oms.order(order_id)
    print(f"bar {next_i} after trip: outcome fills={len(out.fills)} "
          f"orders_created={len(out.orders_created)} "
          f"runtime_state={out.runtime_state}")
    print(f"order now: status={after.status.value} "
          f"filled_quantity={after.filled_quantity}")
    if after.filled_quantity > 0:
        print(f"RESULT [{label}]: BYPASS CONFIRMED — the order acquired "
              f"fills AFTER the kill switch was active")
    else:
        print(f"RESULT [{label}]: no fill after trip (enforced)")


def probe_restart_after_halt():
    print("\n=== RUN-HALT-1: restart after operator HALT ===")
    with tempfile.TemporaryDirectory() as td:
        ens_cal = _fit_world()
        rt = _operational("probe-halt", Path(td) / "st", ens_cal)
        rt.start()
        for b in _bars(30)[:12]:
            rt.process_bar(b)
        rt.halt("operator stop (probe)")
        print(f"pre-restart state: {rt.state.value}; persisted "
              f"runtime_state=HALTED")
        rt2 = _operational("probe-halt", Path(td) / "st", ens_cal)
        try:
            rt2.start()
            print(f"post-restart state: {rt2.state.value} "
                  f"(restarted={rt2.restarted})")
            if rt2.state is RuntimeState.RUNNING:
                print("RESULT [RUN-HALT-1]: BYPASS CONFIRMED — an "
                      "operator-halted session resumed RUNNING on "
                      "restart (terminal-safe-stop contract violated)")
            else:
                print("RESULT [RUN-HALT-1]: restart did not resume "
                      f"RUNNING (state={rt2.state.value})")
        except Exception as exc:
            print(f"RESULT [RUN-HALT-1]: start() REFUSED ({type(exc).__name__}: "
                  f"{str(exc)[:120]})")


if __name__ == "__main__":
    probe_kill_switch(
        lambda rt, oid: rt.trip_kill_switch(
            KillSwitchScope.SYMBOL, "probe: symbol stress",
            target=SYMBOL),
        "RUN-KS-1: SYMBOL-scope trip vs in-flight order",
    )
    probe_kill_switch(
        lambda rt, oid: rt.trip_kill_switch(
            KillSwitchScope.ORDER, "probe: order-level block",
            target=oid),
        "RUN-KS-2: ORDER-scope trip vs its target order",
    )
    probe_restart_after_halt()
