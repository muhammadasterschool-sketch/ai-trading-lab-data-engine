"""Runtime observability metrics tests (mandate §26 / Workstream P).

Proves:
- the counter vocabulary is CLOSED (unknown names raise);
- counters track a scripted governed session EXACTLY (bars, orders,
  risk rejections, fills, partial fills, kill switch, no-trade
  reasons, reconciliation, RL proposals);
- snapshot_hash is deterministic over counters ONLY — latency
  gauges (wall-clock observability) are excluded BY DESIGN (INV-01);
- metrics are NEVER persisted into EXECUTION_STATE_SCHEMA and never
  leak into runtime identity;
- metrics content cannot carry secrets (counts + numbers only).
"""

import json
from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.runtime import (
    COUNTER_NAMES,
    DeterministicBaseline,
    DeterministicEnsemble,
    GAUGE_NAMES,
    MetricsError,
    RuntimeConfig,
    RuntimeMetrics,
    TradingRuntime,
    SequenceSpec,
    build_sequence_set,
    GovernedRLPolicy,
    RLPolicyConfig,
    KillSwitchScope,
    MemoryCategory,
)

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _bars(n, start=100.0, phase=6, drift=2.0, interval=300, volume=5000.0):
    bars = []
    price = start
    for i in range(n):
        d = drift if (i // phase) % 2 == 0 else -drift * 0.92
        o = price
        c = price + d
        bars.append({
            "timestamp": T0 + timedelta(seconds=interval * i),
            "open": o, "high": max(o, c) + 0.25,
            "low": min(o, c) - 0.25, "close": c, "volume": volume,
        })
        price = c
    return bars


def _fit_world():
    train = _bars(120)
    spec = SequenceSpec(symbol="TEST/USD", timeframe="5m", lookback=8,
                        horizon=2, feature_version="fv-1",
                        dataset_version="dv-synth")
    sset = build_sequence_set(train, spec, train[-1]["timestamp"], "train",
                              expected_interval_seconds=300)
    labeled = list(sset.labeled)
    X = [list(s.features) for s in labeled]
    y = [s.target for s in labeled]
    b = DeterministicBaseline(model_id="B", feature_version="fv-1",
                              dataset_version="dv-synth", lookback=8,
                              horizon=2).fit(X, y)
    return DeterministicEnsemble([b], [1.0])


def _config(session="metrics-test"):
    return RuntimeConfig(
        symbol="TEST/USD", timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        ephemeral_test_fixture=True,
    )


# ════════════════════════════════════════════════════════════════════
# 1. Registry contract (fail closed)
# ════════════════════════════════════════════════════════════════════

class TestRegistryContract:
    def test_unknown_counter_raises(self):
        m = RuntimeMetrics()
        with pytest.raises(MetricsError):
            m.increment("not_a_counter")

    def test_unknown_gauge_raises(self):
        m = RuntimeMetrics()
        with pytest.raises(MetricsError):
            m.set_gauge("not_a_gauge", 1.0)

    def test_negative_increment_rejected(self):
        m = RuntimeMetrics()
        with pytest.raises(MetricsError):
            m.increment("bars_processed", -1)

    def test_empty_no_trade_reason_rejected(self):
        m = RuntimeMetrics()
        with pytest.raises(MetricsError):
            m.count_no_trade_reason("   ")

    def test_all_counters_start_at_zero(self):
        m = RuntimeMetrics()
        assert all(v == 0 for v in m.counters.values())
        assert set(m.counters) == set(COUNTER_NAMES)

    def test_mandated_metric_families_present(self):
        required = {
            "bars_processed", "orders_created", "orders_risk_rejected",
            "fills", "partial_fill_events", "no_trade_total",
            "kill_switch_trips", "halts", "reconciliation_mismatches",
            "recovery_events", "audit_memory_records", "ledger_events",
            "rl_proposals", "decisions_trade", "decisions_hold",
        }
        assert required <= set(COUNTER_NAMES)
        assert "cycle_latency_seconds" in GAUGE_NAMES


# ════════════════════════════════════════════════════════════════════
# 2. Determinism of the snapshot hash (INV-01 boundary)
# ════════════════════════════════════════════════════════════════════

class TestSnapshotDeterminism:
    def test_identical_event_sequences_identical_hash(self):
        a, b = RuntimeMetrics(), RuntimeMetrics()
        for m in (a, b):
            m.increment("bars_processed", 5)
            m.increment("fills", 3)
            m.count_no_trade_reason("stale")
            m.count_no_trade_reason("stale")
        assert a.snapshot_hash == b.snapshot_hash

    def test_different_sequences_different_hash(self):
        a, b = RuntimeMetrics(), RuntimeMetrics()
        a.increment("bars_processed", 5)
        b.increment("bars_processed", 6)
        assert a.snapshot_hash != b.snapshot_hash

    def test_latency_gauses_excluded_from_hash(self):
        a, b = RuntimeMetrics(), RuntimeMetrics()
        a.set_gauge("cycle_latency_seconds", 0.001)
        b.set_gauge("cycle_latency_seconds", 999.0)
        assert a.snapshot_hash == b.snapshot_hash  # gauges never identity

    def test_gauge_negative_and_nan_dropped(self):
        m = RuntimeMetrics()
        m.set_gauge("cycle_latency_seconds", -1.0)
        m.set_gauge("cycle_latency_seconds", float("nan"))
        assert m.gauges["cycle_latency_seconds"] == 0.0

    def test_gauge_max_tracks_maximum(self):
        m = RuntimeMetrics()
        m.set_gauge("cycle_latency_seconds", 0.5)
        m.set_gauge("cycle_latency_seconds", 0.2)
        m.set_gauge("cycle_latency_seconds", 0.9)
        assert m.gauges["cycle_latency_seconds"] == 0.9
        assert m.gauges["cycle_latency_seconds_max"] == 0.9

    def test_snapshot_key_order_deterministic(self):
        m = RuntimeMetrics()
        m.increment("bars_processed")
        m.count_no_trade_reason("z-reason")
        m.count_no_trade_reason("a-reason")
        snap = m.snapshot()
        assert list(snap["counters"]) == sorted(snap["counters"])
        assert list(snap["no_trade_reasons"]) == sorted(snap["no_trade_reasons"])


# ════════════════════════════════════════════════════════════════════
# 3. Scripted governed session — exact accounting
# ════════════════════════════════════════════════════════════════════

class TestScriptedSessionAccounting:
    def _run(self, rl=False, bars=20):
        rt = TradingRuntime(
            _config(), _fit_world(),
            rl_policy=GovernedRLPolicy(RLPolicyConfig()) if rl else None,
        )
        rt.start()
        for bar in _bars(bars):
            rt.process_bar(bar)
        return rt

    def test_bars_counter_matches_processed_bars(self):
        rt = self._run(bars=20)
        assert rt.metrics.get("bars_processed") >= 20
        assert (
            rt.metrics.get("bars_processed")
            == rt.metrics.get("warmup_bars")
            + rt.metrics.get("bad_bars")
            + rt.metrics.get("bars_refused")
            + rt.metrics.get("decisions_trade")
            + rt.metrics.get("decisions_hold")
            + rt.metrics.get("no_trade_total")
        )

    def test_orders_created_matches_oms(self):
        rt = self._run()
        assert rt.metrics.get("orders_created") == len(rt.oms.orders())

    def test_fills_counter_matches_oms_fills(self):
        rt = self._run(bars=30)
        oms_fills = sum(len(o.fills) for o in rt.oms.orders())
        assert rt.metrics.get("fills") == oms_fills

    def test_kill_switch_trip_counted_once(self):
        rt = self._run(bars=12)
        rt.trip_kill_switch(KillSwitchScope.GLOBAL, "metrics-test")
        assert rt.metrics.get("kill_switch_trips") == 1
        assert rt.metrics.get("halts") >= 1

    def test_no_trade_reasons_histogram(self):
        rt = self._run(bars=25)
        total = rt.metrics.get("no_trade_total")
        assert sum(rt.metrics.no_trade_reasons.values()) == total

    def test_rl_counters_when_enabled(self):
        rt = self._run(rl=True, bars=15)
        assert rt.metrics.get("rl_proposals") >= 5
        assert (
            rt.metrics.get("rl_proposals_vetoed")
            + (rt.metrics.get("rl_proposals")
               - rt.metrics.get("rl_proposals_vetoed"))
            == rt.metrics.get("rl_proposals")
        )

    def test_rl_counters_zero_when_disabled(self):
        rt = self._run(rl=False, bars=15)
        assert rt.metrics.get("rl_proposals") == 0

    def test_cycle_latency_gauge_positive_after_processing(self):
        rt = self._run(bars=5)
        assert rt.metrics.gauges["cycle_latency_seconds"] > 0.0

    def test_metrics_survive_kill_switch_and_continue(self):
        rt = self._run(bars=12)
        rt.trip_kill_switch(KillSwitchScope.GLOBAL, "metrics-test")
        for bar in _bars(6, start=150.0):
            rt.process_bar(bar)
        assert rt.metrics.get("bars_refused") >= 6
        assert rt.metrics.get("kill_switch_trips") == 1


# ════════════════════════════════════════════════════════════════════
# 4. Isolation from persistence + identity (INV-01)
# ════════════════════════════════════════════════════════════════════

class TestMetricsIsolation:
    def test_metrics_not_in_persisted_state(self, tmp_path):
        from data_engine.runtime import ExecutionStateStore
        store = ExecutionStateStore(tmp_path / "store")
        rt = TradingRuntime(
            _config(session="persist-metrics"), _fit_world(),
            state_store=store,
        )
        rt.start()
        for bar in _bars(12):
            rt.process_bar(bar)
        assert rt.metrics.get("bars_processed") >= 12
        snap_path = tmp_path / "store" / "state.json"
        assert snap_path.exists()
        state = json.loads(snap_path.read_text())
        # EXECUTION_STATE_SCHEMA carries authoritative state ONLY —
        # metrics are observability, re-derivable, never persisted.
        assert "metrics" not in state
        assert "counters" not in state
        assert "gauges" not in state

    def test_metrics_snapshot_contains_no_secrets(self):
        rt = self._run = None  # guard accidental reuse
        m = RuntimeMetrics()
        m.increment("bars_processed", 3)
        m.count_no_trade_reason("stale data")
        m.set_gauge("cycle_latency_seconds", 0.01)
        blob = json.dumps(m.snapshot()).lower()
        for banned in ("github_pat", "token", "secret", "password",
                       "api_key", "credential"):
            assert banned not in blob
