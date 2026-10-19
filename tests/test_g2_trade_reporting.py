"""Stage G / G2 — trade-ledger reporting API tests (Part 9B G2).

Every number in the report must reconcile against the journal:
- the builder VERIFIES the hash chains first and REFUSES on failure;
- totals / win rate / per-trade / per-strategy / per-broker / session
  summaries are derived ONLY from ledger events;
- attribution falls back honestly (payload field -> session context
  -> UNATTRIBUTED), never guessed.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.reporting import (
    ReportRefused,
    UNATTRIBUTED,
    build_trade_report,
)

T0 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)


def _family_with_trades(trades: list) -> LedgerFamily:
    """Record EXIT trades (and matching fill/pnl events) into a
    fresh keyed ledger family; return it ready for reporting."""
    family = LedgerFamily()
    stamp = T0
    for i, spec in enumerate(trades):
        stamp = stamp + timedelta(minutes=5)
        payload = {
            "exit_id": spec.get("exit_id", f"exit-{i}"),
            "symbol": spec["symbol"],
            "realized_pnl": spec["realized_pnl"],
            "reason": spec.get("reason", "TAKE_PROFIT"),
        }
        if "strategy_id" in spec:
            payload["strategy_id"] = spec["strategy_id"]
        if "broker_id" in spec:
            payload["broker_id"] = spec["broker_id"]
        family.record(
            ledger="trade",
            event_type=f"EXIT_{spec.get('reason', 'TAKE_PROFIT')}",
            correlation_id=f"corr-{i}",
            actor="runtime.exit_manager",
            payload=payload,
        )
        family.record(
            ledger="fill",
            event_type="ORDER_FILLED",
            correlation_id=f"corr-{i}",
            actor="runtime.oms",
            payload={"order_id": f"o-{i}", "fill_id": f"f-{i}"},
        )
        family.record(
            ledger="pnl",
            event_type="PNL_SNAPSHOT",
            correlation_id=f"corr-{i}",
            actor="runtime.pnl",
            payload={"pnl_id": f"p-{i}", "realized": spec["realized_pnl"]},
        )
    return family


TRADES = [
    {"symbol": "BTCUSDT", "realized_pnl": "12.50", "strategy_id": "alpha",
     "broker_id": "paper-mock"},
    {"symbol": "EURUSD", "realized_pnl": "-4.25", "strategy_id": "alpha",
     "broker_id": "paper-mock"},
    {"symbol": "BTCUSDT", "realized_pnl": "7.00", "strategy_id": "beta",
     "broker_id": "paper-mock"},
    {"symbol": "XAUUSD", "realized_pnl": "-1.00"},  # unattributed
]


class TestReportBasics:
    def test_totals_and_win_rate(self):
        report = build_trade_report(_family_with_trades(TRADES))
        assert report.total_trades == 4
        assert report.wins == 2
        assert report.losses == 2
        assert report.win_rate == Decimal("0.5000")
        assert report.gross_profit == Decimal("19.50")
        assert report.gross_loss == Decimal("5.25")
        assert report.net_pnl == Decimal("14.25")
        assert report.reconciliation.chains_verified is True
        assert report.reconciliation.reconciled is True
        assert report.reconciliation.trade_events_scanned == 4
        assert report.reconciliation.fill_events_scanned == 4
        assert report.reconciliation.pnl_events_scanned == 4

    def test_per_trade_records(self):
        report = build_trade_report(_family_with_trades(TRADES))
        by_id = {t.trade_id: t for t in report.per_trade}
        assert by_id["exit-0"].realized_pnl == Decimal("12.50")
        assert by_id["exit-0"].symbol == "BTCUSDT"
        assert by_id["exit-3"].strategy_id == UNATTRIBUTED
        assert by_id["exit-3"].broker_id == UNATTRIBUTED

    def test_per_strategy_breakdown(self):
        report = build_trade_report(_family_with_trades(TRADES))
        by_key = {g.key: g for g in report.per_strategy}
        assert by_key["alpha"].trades == 2
        assert by_key["alpha"].wins == 1
        assert by_key["alpha"].net_pnl == Decimal("8.25")
        assert by_key["beta"].trades == 1
        assert by_key[UNATTRIBUTED].trades == 1

    def test_per_broker_breakdown(self):
        report = build_trade_report(_family_with_trades(TRADES))
        by_key = {g.key: g for g in report.per_broker}
        assert by_key["paper-mock"].trades == 3
        assert by_key[UNATTRIBUTED].trades == 1

    def test_session_day_summary(self):
        report = build_trade_report(_family_with_trades(TRADES))
        # all events recorded within one real-time instant batch ->
        # one calendar day (derive the expectation from the journal
        # itself, not a hardcoded wall-clock date)
        expected_day = report.per_trade[0].closed_at.strftime("%Y-%m-%d")
        assert len(report.per_session) == 1
        session = report.per_session[0]
        assert session.day == expected_day
        assert session.trades == 4
        assert session.net_pnl == Decimal("14.25")

    def test_default_context_attribution(self):
        report = build_trade_report(
            _family_with_trades(TRADES[:1]),
            default_strategy_id="ensemble-42",
            default_broker_id="venue-9",
        )
        trade = report.per_trade[0]
        # payload has explicit fields — they win over the context
        assert trade.strategy_id == "alpha"
        unattributed = build_trade_report(
            _family_with_trades([TRADES[3]]),
            default_strategy_id="ensemble-42",
            default_broker_id="venue-9",
        )
        # payload has NO fields — session context applies
        assert unattributed.per_trade[0].strategy_id == "ensemble-42"
        assert unattributed.per_trade[0].broker_id == "venue-9"

    def test_session_id_fallback(self):
        report = build_trade_report(
            _family_with_trades([TRADES[3]]), session_id="session-7"
        )
        assert report.per_trade[0].strategy_id == "session-7"

    def test_to_dict_is_json_projectable(self):
        report = build_trade_report(_family_with_trades(TRADES))
        as_dict = report.to_dict()
        assert as_dict["total_trades"] == 4
        assert as_dict["win_rate"] == "0.5000"
        assert as_dict["net_pnl"] == "14.25"
        assert as_dict["reconciliation"]["reconciled"] is True
        import json

        json.dumps(as_dict)  # must serialize cleanly


class TestReportFailClosed:
    def test_non_ledger_family_refused(self):
        with pytest.raises(ReportRefused):
            build_trade_report(object())

    def test_unparseable_realized_pnl_refuses(self):
        family = _family_with_trades(TRADES)
        family.record(
            ledger="trade",
            event_type="EXIT_TAKE_PROFIT",
            correlation_id="corr-bad",
            actor="runtime.exit_manager",
            payload={"exit_id": "exit-bad", "symbol": "X",
                     "realized_pnl": "not-a-number"},
        )
        with pytest.raises(ReportRefused) as excinfo:
            build_trade_report(family)
        assert "realized_pnl" in str(excinfo.value)

    def test_empty_journal_reports_zeroes_honestly(self):
        report = build_trade_report(LedgerFamily())
        assert report.total_trades == 0
        assert report.win_rate is None
        assert report.net_pnl == Decimal("0")
        assert report.reconciliation.chains_verified is True


class TestGroupSummary:
    def test_win_rate_none_when_no_trades(self):
        from data_engine.runtime.reporting import GroupSummary

        empty = GroupSummary(
            key="k", trades=0, wins=0, losses=0,
            gross_profit=Decimal("0"), gross_loss=Decimal("0"),
            net_pnl=Decimal("0"),
        )
        assert empty.win_rate is None
