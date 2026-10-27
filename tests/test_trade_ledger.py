"""v1.0.0 owner-mandate tests — TradeLedger ("kis pe trade li,
kitna profit hua").

Pins:
- record() validates symbol/side/quantity/price strictly (a bad fill
  can never be silently rewritten into a good-looking one);
- stats() aggregates trades-per-symbol (the dashboard mini chart
  data), total PnL, wins/losses honestly;
- the JSONL file is DURABLE: a fresh instance reloads full history;
- corrupted lines are SKIPPED (counted) — one bad line never erases
  the whole ledger;
- entries() is bounded and most-recent-first;
- a failed append (unwritable path) leaves in-memory state matching
  the durable file (fail-closed, no phantom trades).
"""

import pytest

from data_engine.runtime.trade_ledger import (
    TradeLedger,
    TradeLedgerError,
)


def _record(ledger: TradeLedger, **overrides):
    kwargs = {
        "symbol": "EURUSD",
        "side": "BUY",
        "quantity": 0.1,
        "price": 1.0850,
        "pnl": 10.0,
        "strategy": "ma-cross",
        "note": "",
    }
    kwargs.update(overrides)
    return ledger.record(**kwargs)


class TestRecordValidation:
    def test_valid_record_round_trip(self, tmp_path):
        ledger = TradeLedger(tmp_path / "ledger.jsonl")
        record = _record(ledger)
        assert record["symbol"] == "EURUSD"
        assert record["side"] == "BUY"
        assert record["pnl"] == 10.0
        assert record["ts"]

    def test_empty_symbol_refused(self, tmp_path):
        with pytest.raises(TradeLedgerError):
            _record(TradeLedger(tmp_path / "l.jsonl"), symbol="  ")

    def test_bad_side_refused(self, tmp_path):
        ledger = TradeLedger(tmp_path / "l.jsonl")
        with pytest.raises(TradeLedgerError):
            _record(ledger, side="long")
        with pytest.raises(TradeLedgerError):
            _record(ledger, side="")
        # canonical sides are case/whitespace NORMALIZED (not fabricated)
        assert _record(ledger, side="sell")["side"] == "SELL"
        assert _record(ledger, side=" buy ")["side"] == "BUY"

    def test_non_positive_quantity_refused(self, tmp_path):
        ledger = TradeLedger(tmp_path / "l.jsonl")
        for bad in (0, -1, "x", None, True, float("nan"), float("inf")):
            with pytest.raises(TradeLedgerError):
                _record(ledger, quantity=bad)

    def test_non_finite_price_refused(self, tmp_path):
        ledger = TradeLedger(tmp_path / "l.jsonl")
        with pytest.raises(TradeLedgerError):
            _record(ledger, price=float("inf"))

    def test_open_position_carries_no_pnl(self, tmp_path):
        ledger = TradeLedger(tmp_path / "l.jsonl")
        record = _record(ledger, pnl=None)
        assert record["pnl"] is None
        stats = ledger.stats()
        assert stats["wins"] == 0 and stats["losses"] == 0


class TestStats:
    def test_aggregates_match_owner_questions(self, tmp_path):
        ledger = TradeLedger(tmp_path / "ledger.jsonl")
        _record(ledger, symbol="EURUSD", pnl=25.5)
        _record(ledger, symbol="EURUSD", pnl=-10.0)
        _record(ledger, symbol="XAUUSD", pnl=100.0)
        _record(ledger, symbol="BTCUSD", pnl=0.0)
        stats = ledger.stats()
        assert stats["total_trades"] == 4
        assert stats["per_symbol"] == {
            "EURUSD": 2,
            "XAUUSD": 1,
            "BTCUSD": 1,
        }
        assert stats["total_pnl"] == 115.5
        assert stats["wins"] == 3  # zero-pnl counts as not-a-loss
        assert stats["losses"] == 1
        assert stats["last_trade_at"] is not None

    def test_empty_ledger_is_honest_zero(self, tmp_path):
        stats = TradeLedger(tmp_path / "ledger.jsonl").stats()
        assert stats == {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "per_symbol": {},
            "skipped_lines": 0,
            "last_trade_at": None,
        }


class TestDurability:
    def test_history_survives_reload(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        ledger = TradeLedger(path)
        _record(ledger, symbol="EURUSD", pnl=5.0)
        _record(ledger, symbol="XAUUSD", pnl=7.0)
        revived = TradeLedger(path)
        assert revived.stats()["total_trades"] == 2
        assert revived.entries()[0]["symbol"] == "XAUUSD"

    def test_corrupt_lines_skipped_not_fatal(self, tmp_path):
        path = tmp_path / "ledger.jsonl"
        path.write_text(
            '{"symbol": "AAA", "side": "BUY", "quantity": 1.0,'
            ' "price": 1.0, "pnl": 1.0, "ts": "t"}\n'
            "THIS IS NOT JSON\n"
            "[1, 2, 3]\n",
            encoding="utf-8",
        )
        ledger = TradeLedger(path)
        assert ledger.stats()["total_trades"] == 1
        assert ledger.skipped_lines == 2

    def test_failed_append_keeps_memory_consistent(self, tmp_path):
        # a DIRECTORY occupying the LEDGER FILE path makes every
        # append fail closed (IsADirectoryError -> TradeLedgerError)
        blocker = tmp_path / "ledger.jsonl"
        blocker.mkdir()
        ledger = TradeLedger(blocker)
        with pytest.raises(TradeLedgerError):
            _record(ledger)
        assert ledger.stats()["total_trades"] == 0


class TestBoundedReads:
    def test_entries_bounded_and_newest_first(self, tmp_path):
        ledger = TradeLedger(tmp_path / "ledger.jsonl")
        for index in range(50):
            _record(ledger, symbol=f"S{index:02d}", pnl=float(index))
        page = ledger.entries(limit=10)
        assert len(page) == 10
        assert page[0]["symbol"] == "S49"
        assert page[-1]["symbol"] == "S40"
        assert len(ledger.entries(limit=10**6)) == 50
