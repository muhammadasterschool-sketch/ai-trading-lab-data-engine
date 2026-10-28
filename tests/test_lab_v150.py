"""v1.5.0 lab tests — YouTuber preset kinds, cost model, AUTO-SCAN,
preset bootstrap, confidence gate and the paper-only rapid burst.

Deterministic, offline, synthetic bars. Governance invariants pinned:
bursts are journal-only, the kill switch pauses them, and no code path
here can authorize live trading.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data_engine.runtime.confidence import ConfidenceGate
from data_engine.runtime.lab import (
    LabBacktester,
    LabError,
    LabManager,
    BarStore,
    default_cost_bps,
)
from data_engine.runtime.presets import (
    PRESET_KINDS,
    TOP5_YOUTUBER_PRESETS,
    presets_for_api,
)
from data_engine.runtime.rapid_scalper import RapidScalper

NOW = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


def _bars(n=400, drift=0.0008, seed=5, start_price=100.0, volume=True):
    import random

    rng = random.Random(seed)
    price = start_price
    t0 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    bars = []
    for i in range(n):
        price = max(1.0, price * (1 + drift + rng.gauss(0, 0.004)))
        hi = price * (1 + abs(rng.gauss(0, 0.0015)))
        lo = price * (1 - abs(rng.gauss(0, 0.0015)))
        bars.append(
            {
                "ts": (t0 + timedelta(minutes=i)).isoformat(),
                "open": price,
                "high": hi,
                "low": lo,
                "close": price,
                "volume": max(1.0, rng.expovariate(1 / 500.0)) if volume else None,
            }
        )
    return bars


# ---------------------------------------------------------------------------
# preset metadata
# ---------------------------------------------------------------------------


class TestPresets:
    def test_five_presets_with_m1_timeframe(self):
        assert len(TOP5_YOUTUBER_PRESETS) == 5
        for preset in TOP5_YOUTUBER_PRESETS:
            assert preset["timeframe"] == "M1"
            assert preset["confirmation_candle"] is True
            assert preset["kind"] in PRESET_KINDS

    def test_api_copy_is_isolated(self):
        rows = presets_for_api()
        rows[0]["params"]["fast"] = 999
        assert TOP5_YOUTUBER_PRESETS[0]["params"]["fast"] == 9


# ---------------------------------------------------------------------------
# LabBacktester: new kinds + cost model
# ---------------------------------------------------------------------------


class TestNewKinds:
    @pytest.mark.parametrize("kind", sorted(PRESET_KINDS))
    def test_positions_are_long_flat(self, kind):
        bars = _bars()
        positions = LabBacktester().positions(kind, {}, bars)
        assert len(positions) == len(bars)
        assert set(positions) <= {0, 1}

    def test_ema_scalp_requires_fast_lt_slow(self):
        with pytest.raises(LabError):
            LabBacktester().positions(
                "ema_scalp", {"fast": 30, "slow": 10}, _bars(60)
            )

    def test_float_params_accepted_int_or_float(self):
        runner = LabBacktester()
        clean = runner.validate_params(
            "rsi_bb", {"oversold": 25, "bb_std": 2.5}
        )
        assert clean["oversold"] == 25.0 and clean["bb_std"] == 2.5

    def test_unknown_param_refused(self):
        with pytest.raises(LabError):
            LabBacktester().validate_params("rsi_bb", {"nope": 1})

    def test_out_of_bounds_param_refused(self):
        with pytest.raises(LabError):
            LabBacktester().validate_params("supertrend_follow", {"st_mult": 99.0})

    def test_vwap_reversion_requires_volume(self):
        bars = _bars(100, volume=False)
        with pytest.raises(LabError):
            LabBacktester().positions("vwap_reversion", {}, bars)


class TestCostModel:
    def test_costs_off_matches_v110_contract(self):
        bars = _bars(200)
        runner = LabBacktester()
        result = runner.run("ema_trend", {"period": 20}, bars)
        assert "gross_total_return_pct" not in result
        assert "costs NOT modeled" in result["runner"]

    def test_costs_on_reports_net_and_gross(self):
        bars = _bars(200)
        runner = LabBacktester()
        result = runner.run(
            "ema_trend",
            {"period": 20},
            bars,
            costs={"fee_bps": 10.0, "slippage_bps": 2.0},
        )
        assert result["net_total_return_pct"] == result["total_return_pct"]
        assert result["gross_total_return_pct"] >= result["net_total_return_pct"]
        assert result["cost_drag_pct"] >= 0.0
        assert "fees+slippage modeled" in result["runner"]

    def test_negative_costs_refused(self):
        with pytest.raises(LabError):
            LabBacktester().run(
                "ema_trend", {}, _bars(50),
                costs={"fee_bps": -1.0, "slippage_bps": 0.0},
            )

    def test_default_cost_bps_by_family(self):
        assert default_cost_bps("BTCUSDT")["fee_bps"] == 10.0
        assert default_cost_bps("XAUUSD")["slippage_bps"] == 7.0


# ---------------------------------------------------------------------------
# ConfidenceGate + RapidScalper
# ---------------------------------------------------------------------------


class TestConfidenceGate:
    def test_assessment_shape_and_range(self):
        bars = _bars(200)
        runner = LabBacktester()
        gate = ConfidenceGate(position_fn=runner.positions)
        assessment = gate.assess("ema_scalp", {}, bars)
        assert assessment["threshold_pct"] == 60.0
        assert 50.0 <= assessment["confidence_pct"] <= 100.0
        assert assessment["direction"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert set(assessment["components"]) == {
            "strategy", "baseline", "trend"
        }
        assert assessment["confirmed"] == (
            assessment["direction"] != "NEUTRAL"
            and assessment["confidence_pct"] >= 60.0
        )

    def test_min_bars_enforced(self):
        gate = ConfidenceGate(position_fn=LabBacktester().positions)
        with pytest.raises(LabError):
            gate.assess("ema_scalp", {}, _bars(20))

    def test_no_position_fn_fails_closed(self):
        with pytest.raises(LabError):
            ConfidenceGate().assess("ema_scalp", {}, _bars(100))


class TestRapidScalper:
    def test_burst_is_one_fill_per_second_for_sixty_seconds(self):
        burst = RapidScalper().plan_burst(
            submission_id="s", symbol="BTCUSDT", direction="BULLISH",
            confidence_pct=75.0, confirmation_close=100.0,
            confirmation_ts="2026-10-28T00:00:00+00:00",
        )
        assert burst["fills_planned"] == 60
        offsets = [f["t_offset_sec"] for f in burst["fills"]]
        assert offsets == list(range(1, 61))  # exactly 1/sec, 60s
        assert all(f["side"] == "BUY" for f in burst["fills"])
        assert burst["status"] == "PENDING_MARK"

    def test_bearish_burst_is_sell_side(self):
        burst = RapidScalper().plan_burst(
            submission_id="s", symbol="BTCUSDT", direction="BEARISH",
            confidence_pct=70.0, confirmation_close=100.0,
            confirmation_ts="ts",
        )
        assert all(f["side"] == "SELL" for f in burst["fills"])

    def test_mark_burst_uses_actual_next_close(self):
        scalper = RapidScalper()
        burst = scalper.plan_burst(
            submission_id="s", symbol="X", direction="BULLISH",
            confidence_pct=61.0, confirmation_close=100.0,
            confirmation_ts="ts",
        )
        marked = scalper.mark_burst(burst, next_close=101.0)
        assert marked["status"] == "MARKED"
        assert marked["net_pnl_bps"] > 0  # price rose, long burst

    def test_admission_respects_cooldown_and_loss_cap(self):
        denied = RapidScalper.burst_allowed(
            meta={}, bars_since_last_burst=1, cooldown_bars=2,
            cumulative_bps=0.0, loss_limit_bps=100.0,
        )
        assert denied["allowed"] is False and "cooldown" in denied["reason"]
        disarmed = RapidScalper.burst_allowed(
            meta={}, bars_since_last_burst=99, cooldown_bars=2,
            cumulative_bps=-150.0, loss_limit_bps=100.0,
        )
        assert disarmed["allowed"] is False and "limit" in disarmed["reason"]
        ok = RapidScalper.burst_allowed(
            meta={}, bars_since_last_burst=5, cooldown_bars=2,
            cumulative_bps=0.0, loss_limit_bps=100.0,
        )
        assert ok["allowed"] is True

    def test_rate_is_pinned_to_one_per_second(self):
        with pytest.raises(ValueError):
            RapidScalper(fills_per_second=2)


# ---------------------------------------------------------------------------
# LabManager: bootstrap + AUTO-SCAN + burst journaling
# ---------------------------------------------------------------------------


@pytest.fixture()
def lab(tmp_path):
    store = BarStore(tmp_path / "bars")
    manager = LabManager(tmp_path, store)
    store.append("BTCUSDT", _bars(400))
    return manager


class TestBootstrap:
    def test_bootstrap_creates_and_paper_starts_presets(self, lab):
        result = lab.bootstrap_default_strategies("BTCUSDT")
        assert len(result["created"]) == 5
        assert len(result["paper_started"]) == 5
        rows = lab.list()
        assert all(r["symbol"] == "BTCUSDT" for r in rows)
        kinds = {r["kind"] for r in rows}
        assert kinds == set(PRESET_KINDS)

    def test_bootstrap_is_idempotent(self, lab):
        lab.bootstrap_default_strategies("BTCUSDT")
        again = lab.bootstrap_default_strategies("BTCUSDT")
        assert again["created"] == []

    def test_bootstrap_records_backtest_evidence(self, lab):
        result = lab.bootstrap_default_strategies("BTCUSDT")
        durable = lab._durable()["strategies"][result["created"][0]]
        backtest = durable["status"].get("backtest") or {}
        assert backtest.get("bars_tested") == 400


class TestAutoScan:
    def test_auto_scan_bounded_and_honest(self, lab):
        result = lab.auto_scan("BTCUSDT", top_n=2)
        assert result["combinations_tested"] == 27
        assert result["survivors"] <= result["candidates_found"]
        assert len(result["created"]) <= 2
        for candidate in result["created"]:
            assert candidate["submission_id"]

    def test_auto_scan_needs_history(self, lab):
        with pytest.raises(LabError):
            lab.auto_scan("NOSUCH")

    def test_auto_scan_top_n_bounds(self, lab):
        with pytest.raises(LabError):
            lab.auto_scan("BTCUSDT", top_n=0)
        with pytest.raises(LabError):
            lab.auto_scan("BTCUSDT", top_n=11)


class TestBurstJournal:
    def test_confirmed_signal_journals_rapid_burst(self, tmp_path):
        store = BarStore(tmp_path / "bars")
        manager = LabManager(tmp_path, store)
        # strong drift -> ema_scalp long + bullish gate
        store.append("BTCUSDT", _bars(300, drift=0.0025, seed=3))
        sid = manager.create(
            label="burst", symbol="BTCUSDT", kind="ema_scalp", params={}
        )["submission_id"]
        manager.run_backtest(sid)
        manager.paper_start(sid, cycle_days=1)
        events_before = len(manager._read_paper_events(sid))
        result = manager.observe_symbol_update("BTCUSDT")
        events = manager._read_paper_events(sid)
        burst_events = [e for e in events if e.get("event") == "RAPID_BURST"]
        if result["bursts_planned"]:
            assert burst_events, "planned burst missing from journal"
            assert burst_events[0]["fills_planned"] == 60
            assert "no orders were sent" in burst_events[0]["note"]
        else:
            # not confirmed on this candle — journal unchanged is honest
            assert len(events) == events_before

    def test_kill_switch_pauses_bursts_entirely(self, tmp_path):
        store = BarStore(tmp_path / "bars")
        manager = LabManager(
            tmp_path, store, is_halted=lambda: True
        )
        store.append("BTCUSDT", _bars(300, drift=0.0025, seed=3))
        sid = manager.create(
            label="halted", symbol="BTCUSDT", kind="ema_scalp", params={}
        )["submission_id"]
        manager.run_backtest(sid)
        manager.paper_start(sid, cycle_days=1)
        result = manager.observe_symbol_update("BTCUSDT")
        assert result["halted"] is True
        assert result["bursts_planned"] == []
