"""v1.1.0 owner AI LAB unit tests — BarStore, AssistantEngine,
LabBacktester, LabManager (the durable G6 driver), PredictBaseline,
BrokerCatalog.

Pins (module-level, no HTTP):

- BarStore: validation (bad bars refused), dedupe by timestamp,
  per-symbol bound, atomic files, symbol rules;
- AssistantEngine: every intent answers from the LEDGERS and honest
  zeros are stated (never fabricated);
- LabBacktester: deterministic metrics on a synthetic series; param
  whitelist + bounds; too-few bars refused;
- LabManager: the FULL fail-closed pipeline — create -> backtest ->
  paper window -> finish BEFORE window refused (the gate holds) ->
  finish AT window end -> explicit YES -> ACTIVATED (paper-only) ->
  durable restore replay; kill switch pauses paper evaluation;
- PredictBaseline: direction + probability shape + honest disclaimer;
- BrokerCatalog: mock/simulation honesty + add-broker contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from data_engine.runtime.lab import (
    MAX_BARS_PER_REQUEST,
    AssistantEngine,
    BarStore,
    BrokerCatalog,
    LabBacktester,
    LabError,
    LabManager,
    PredictBaseline,
    validate_bar,
)
from data_engine.runtime.registry import ClientRegistry
from data_engine.runtime.trade_ledger import TradeLedger

BASE = datetime(2026, 2, 1, tzinfo=timezone.utc)


def _bars(n: int, *, drift: float = 1.004, seed_pattern=None, start=BASE):
    out = []
    price = 100.0
    for i in range(n):
        change = drift if (seed_pattern(i) if seed_pattern else i % 3) else 0.998
        o = price
        c = price * change
        h = max(o, c) * 1.001
        low = min(o, c) * 0.999
        out.append(
            {
                "ts": (start + timedelta(hours=i)).isoformat(),
                "open": round(o, 6),
                "high": round(h, 6),
                "low": round(low, 6),
                "close": round(c, 6),
                "volume": 100.0,
            }
        )
        price = c
    return out


@pytest.fixture()
def state(tmp_path) -> Path:
    return tmp_path / "monitor-state"


@pytest.fixture()
def store(state) -> BarStore:
    return BarStore(state / "bars")


@pytest.fixture()
def lab(state, store) -> LabManager:
    return LabManager(state, store)


# ─── BarStore ───────────────────────────────────────────────────


class TestBarStore:
    def test_append_and_roundtrip(self, store):
        result = store.append("XAU/USD", _bars(50))
        assert result["added"] == 50
        assert result["total"] == 50
        bars = store.bars("XAU/USD")
        assert len(bars) == 50
        assert bars[0]["ts"] < bars[-1]["ts"]
        assert store.summary("XAU/USD")["latest_close"] == bars[-1]["close"]

    def test_dedupe_keeps_newest(self, store):
        first = _bars(10)
        store.append("BTCUSD", first)
        mutated = [dict(first[0], open=555.0, close=555.0, high=556.0,
                        low=554.0)]
        store.append("BTCUSD", mutated)
        bars = store.bars("BTCUSD")
        assert len(bars) == 10
        assert bars[0]["close"] == 555.0

    def test_bad_bar_refused(self, store):
        with pytest.raises(LabError):
            store.append("XAUUSD", [{"ts": "2026-01-01T00:00:00+00:00",
                                     "open": 1, "high": 0.5, "low": 2,
                                     "close": 1, "volume": 1}])
        with pytest.raises(LabError):
            store.append("XAUUSD", [{"ts": "not-a-date", "open": 1,
                                     "high": 2, "low": 0.5, "close": 1}])
        with pytest.raises(LabError):
            store.append("XAUUSD", [{"ts": 1767225600, "open": -1,
                                     "high": 2, "low": 0.5, "close": 1}])

    def test_bad_symbol_refused(self, store):
        with pytest.raises(LabError):
            store.append("../evil", _bars(2))
        with pytest.raises(LabError):
            store.append("A" * 30, _bars(2))
        with pytest.raises(LabError):
            store.append("XAU USD!", _bars(2))

    def test_request_size_bound(self, store):
        with pytest.raises(LabError):
            store.append("XAUUSD", _bars(MAX_BARS_PER_REQUEST + 1))

    def test_validate_bar_epoch_and_iso(self):
        bar = validate_bar({"ts": 1767225600, "open": 10, "high": 11,
                            "low": 9, "close": 10.5})
        assert bar["ts"].startswith("2026-01-01T00:00:00")
        assert bar["volume"] is None

    def test_unstored_symbol_is_empty(self, store):
        assert store.bars("NOPE/USD") == []
        assert store.summary("NOPE/USD")["count"] == 0
        assert store.symbols() == []


# ─── AssistantEngine ────────────────────────────────────────────


@pytest.fixture()
def assistant(state):
    ledger = TradeLedger(state / "trade_ledger.jsonl")
    ledger.record(symbol="XAU/USD", side="buy", quantity=1.0,
                  price=2000.0, pnl=150.5, strategy="t1")
    ledger.record(symbol="BTC/USD", side="sell", quantity=0.5,
                  price=40000.0, pnl=-40.0, strategy="t2")
    registry = ClientRegistry(state)
    return AssistantEngine(
        trade_ledger=ledger,
        client_registry=registry,
        health_provider=lambda: {"kill_switch": "INACTIVE"},
    )


class TestAssistantEngine:
    def test_total_pnl(self, assistant):
        reply = assistant.ask("total profit kitna hua")
        assert "110.5" in reply["answer"]
        assert reply["metrics"]["total_trades"] == 2
        assert reply["engine"] == "rule-based-analytics-offline"

    def test_win_rate(self, assistant):
        reply = assistant.ask("win rate kya hai")
        assert "50.0%" in reply["answer"]

    def test_best_symbol(self, assistant):
        reply = assistant.ask("best symbol")
        assert "XAU/USD" in reply["answer"]

    def test_specific_symbol(self, assistant):
        reply = assistant.ask("BTC/USD pe kitna profit")
        assert "BTC/USD" in reply["answer"]
        assert "-40" in reply["answer"]

    def test_who_is_online(self, assistant):
        reply = assistant.ask("who is logged in")
        assert "0 client(s) online" in reply["answer"]

    def test_stop_state(self, assistant):
        reply = assistant.ask("is trading stopped?")
        assert "INACTIVE" in reply["answer"]

    def test_honest_fallback(self, assistant):
        reply = assistant.ask("meri shaadi kab hogi")
        assert "never invent" in reply["answer"]

    def test_help(self, assistant):
        reply = assistant.ask("help")
        assert "LEDGERS" in reply["answer"]

    def test_empty_question_refused(self, assistant):
        with pytest.raises(LabError):
            assistant.ask("   ")

    def test_honest_zeros_when_no_trades(self, state):
        bare = AssistantEngine(
            trade_ledger=TradeLedger(state / "none.jsonl"),
            client_registry=ClientRegistry(state),
            health_provider=lambda: {"kill_switch": "INACTIVE"},
        )
        reply = bare.ask("total profit")
        assert "NO trades yet" in reply["answer"]


# ─── LabBacktester ──────────────────────────────────────────────


class TestLabBacktester:
    def test_deterministic_metrics(self, store):
        runner = LabBacktester()
        bars = _bars(120, drift=1.01)
        a = runner.run("ema_trend", {"period": 20}, bars)
        b = runner.run("ema_trend", {"period": 20}, bars)
        assert a == b
        assert a["bars_tested"] == 120
        assert a["trades"] >= 1
        assert a["total_return_pct"] > 0  # steady uptrend
        assert "costs NOT modeled" in a["runner"]

    def test_param_whitelist_and_bounds(self):
        runner = LabBacktester()
        assert runner.validate_params("ema_trend", {"period": 50}) == {
            "period": 50
        }
        with pytest.raises(LabError):
            runner.validate_params("ema_trend", {"mystery": 1})
        with pytest.raises(LabError):
            runner.validate_params("ema_trend", {"period": 100000})
        with pytest.raises(LabError):
            runner.validate_params("nope", {})
        with pytest.raises(LabError):
            runner.validate_params("ema_cross", {"fast": 50, "slow": 10})

    def test_too_few_bars_refused(self):
        with pytest.raises(LabError):
            LabBacktester().run("breakout", {"lookback": 5}, _bars(10))

    def test_all_kinds_run(self):
        runner = LabBacktester()
        trending = _bars(300, drift=1.005, seed_pattern=lambda i: i % 5)
        # mean-reverting (symmetric oscillation) so RSI actually
        # crosses the oversold/overbought bands
        oscillating = []
        price = 100.0
        for i in range(300):
            factor = 1.02 if (i // 3) % 2 == 0 else 1.0 / 1.02
            o = price
            c = price * factor
            h = max(o, c) * 1.001
            low = min(o, c) * 0.999
            oscillating.append({
                "ts": (BASE + timedelta(hours=i)).isoformat(),
                "open": o, "high": h, "low": low, "close": c,
                "volume": 100.0,
            })
            price = c
        cases = [
            ("ema_trend", {"period": 20}, trending),
            ("ema_cross", {"fast": 5, "slow": 20}, trending),
            ("rsi_reversal",
             {"period": 14, "oversold": 46, "overbought": 55},
             oscillating),
            ("breakout", {"lookback": 10}, trending),
        ]
        for kind, params, bars in cases:
            metrics = runner.run(kind, params, bars)
            assert metrics["bars_tested"] == 300
            assert metrics["trades"] >= 1, kind


# ─── LabManager (the durable G6 driver) ─────────────────────────


class TestLabManagerPipeline:
    def test_create_requires_label(self, lab):
        with pytest.raises(LabError):
            lab.create(label="  ", symbol="XAU/USD", kind="ema_trend",
                       params={})

    def test_create_validates_kind_and_symbol(self, lab):
        with pytest.raises(LabError):
            lab.create(label="x", symbol="XAU/USD", kind="martingale",
                       params={})
        with pytest.raises(LabError):
            lab.create(label="x", symbol="bad symbol!", kind="ema_trend",
                       params={})

    def test_backtest_needs_bars_first(self, lab):
        created = lab.create(label="T", symbol="XAU/USD",
                             kind="ema_trend", params={"period": 20})
        with pytest.raises(LabError):
            lab.run_backtest(created["submission_id"])

    def test_full_pipeline_fail_closed_gate(self, lab, store):
        store.append("XAU/USD", _bars(300, drift=1.005,
                                      seed_pattern=lambda i: i % 5))
        created = lab.create(label="Gold breakout", symbol="XAU/USD",
                             kind="breakout", params={"lookback": 10})
        sid = created["submission_id"]
        assert created["state"] == "SUBMITTED"

        backtested = lab.run_backtest(sid)
        assert backtested["state"] == "BACKTESTED"
        assert backtested["backtest"]["trades"] >= 1
        assert backtested["backtest_metrics"]["total_return_pct"] != 0

        scheduled = lab.paper_start(sid, cycle_days=1)
        assert scheduled["state"] == "VALIDATION_SCHEDULED"
        assert scheduled["validation_window_end"] is not None

        observed = lab.observe_symbol_update("XAU/USD")
        assert observed["evaluated"] == [sid]
        assert observed["halted"] is False

        # THE GATE HOLDS: evidence before the window elapses is refused
        with pytest.raises(Exception):
            lab.paper_finish(sid)

        meta = lab._paper_meta[sid]
        window_end = datetime.fromisoformat(meta["window_end"])
        finished = lab.paper_finish(sid, now=window_end)
        assert finished["state"] == "VALIDATED"
        assert finished["paper_summary"]["paper_trades"] >= 0

        confirmed = lab.confirm(sid, confirm="YES", decided_by="owner")
        assert confirmed["state"] == "ACTIVATED"
        assert "PAPER_EVALUATION_ONLY" in confirmed["governance"]
        assert "NOT_AUTHORIZED" in confirmed["governance"]

    def test_confirm_without_yes_stays_inactive(self, lab, store):
        store.append("XAU/USD", _bars(60))
        sid = lab.create(label="T", symbol="XAU/USD", kind="ema_trend",
                         params={})["submission_id"]
        result = lab.confirm(sid, confirm="NO")
        assert result["state"] != "ACTIVATED"

    def test_confirm_ambiguity_refused(self, lab, store):
        store.append("XAU/USD", _bars(60))
        sid = lab.create(label="T", symbol="XAU/USD", kind="ema_trend",
                         params={})["submission_id"]
        with pytest.raises(LabError):
            lab.confirm(sid, confirm="maybe")

    def test_unknown_strategy_refused(self, lab):
        with pytest.raises(LabError):
            lab.run_backtest("lab-does-not-exist")

    def test_kill_switch_pauses_paper(self, state, store):
        halted_lab = LabManager(state, store, is_halted=lambda: True)
        store.append("XAU/USD", _bars(60))
        sid = halted_lab.create(label="T", symbol="XAU/USD",
                                kind="ema_trend", params={})["submission_id"]
        halted_lab.run_backtest(sid)
        halted_lab.paper_start(sid, cycle_days=1)
        result = halted_lab.observe_symbol_update("XAU/USD")
        assert result == {"evaluated": [], "halted": True}

    def test_durable_restore_replay(self, lab, store):
        store.append("XAU/USD", _bars(300, drift=1.005,
                                      seed_pattern=lambda i: i % 5))
        sid = lab.create(label="Persist me", symbol="XAU/USD",
                         kind="breakout", params={"lookback": 10})[
            "submission_id"
        ]
        lab.run_backtest(sid)
        lab.paper_start(sid, cycle_days=1)
        meta = lab._paper_meta[sid]
        window_end = datetime.fromisoformat(meta["window_end"])
        lab.paper_finish(sid, now=window_end)
        lab.confirm(sid, confirm="YES", decided_by="owner")

        restored = LabManager(lab._dir, store)
        rows = restored.list()
        match = [r for r in rows if r["submission_id"] == sid]
        assert match, "restored row missing"
        assert match[0]["state"] == "ACTIVATED"
        assert match[0]["symbol"] == "XAU/USD"
        assert match[0]["kind"] == "breakout"

    def test_list_is_newest_first(self, lab, store):
        store.append("XAU/USD", _bars(60))
        first = lab.create(label="one", symbol="XAU/USD",
                           kind="ema_trend", params={})["submission_id"]
        second = lab.create(label="two", symbol="XAU/USD",
                            kind="breakout", params={"lookback": 10})[
            "submission_id"
        ]
        rows = lab.list()
        ids = [r["submission_id"] for r in rows]
        assert ids.index(second) < ids.index(first)


# ─── PredictBaseline ────────────────────────────────────────────


class TestPredictBaseline:
    def test_uptrend_is_up(self):
        predictor = PredictBaseline()
        result = predictor.predict(_bars(120, drift=1.01))
        assert result["direction"] in ("UP", "FLAT", "DOWN")
        assert result["direction"] == "UP"
        assert 0.05 <= result["probability_up"] <= 0.95
        assert "NOT investment advice" in result["disclaimer"]
        assert result["confidence"] == "medium"

    def test_downtrend_is_down(self):
        bars = _bars(120, drift=0.99)
        result = PredictBaseline().predict(bars)
        assert result["direction"] == "DOWN"

    def test_too_few_bars_refused(self):
        with pytest.raises(LabError):
            PredictBaseline().predict(_bars(10))

    def test_confidence_low_on_short_history(self):
        assert PredictBaseline().predict(_bars(30))["confidence"] == "low"


# ─── BrokerCatalog ──────────────────────────────────────────────


class TestBrokerCatalog:
    def test_catalog_honesty(self):
        catalog = BrokerCatalog().catalog()
        assert catalog["count"] == len(catalog["brokers"]) == 7
        modes = {row["mode"] for row in catalog["brokers"]}
        assert modes == {"SIMULATION", "PAPER"}
        assert catalog["add_new_broker"]["live_trading"] == (
            "NOT_AUTHORIZED"
        )
        assert "interface.py" in catalog["add_new_broker"]["interface"]


# ─── paper journal robustness ───────────────────────────────────


class TestPaperJournal:
    def test_corrupt_lines_tolerated(self, lab, store):
        store.append("XAU/USD", _bars(60))
        sid = lab.create(label="T", symbol="XAU/USD", kind="ema_trend",
                         params={})["submission_id"]
        lab.run_backtest(sid)
        lab.paper_start(sid, cycle_days=1)
        path = lab._paper_path(sid)
        path.write_text(
            json.dumps({"event": "ENTER_LONG", "ts": "x", "price": 1,
                        "symbol": "XAU/USD"})
            + "\n{corrupt\n\n",
            encoding="utf-8",
        )
        events = lab._read_paper_events(sid)
        assert len(events) == 1
        assert events[0]["event"] == "ENTER_LONG"
