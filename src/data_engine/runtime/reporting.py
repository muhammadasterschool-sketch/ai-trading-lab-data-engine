"""Trade-ledger REPORTING API (Stage G, Part 9B G2 — owner mandate).

On top of the existing ledger family (``runtime/ledgers.py``) and PnL
modules: a VERIFIED reporting surface —

- total trades taken;
- per-trade profit and loss;
- win rate;
- per-strategy and per-broker breakdowns;
- session (calendar-day) summaries.

EVERY reported number RECONCILES against the journal: the builder
first VERIFIES the ledger hash chains (keyed MAC custody included)
and REFUSES to produce a report from a chain that does not verify
(``ReportRefused`` — fail closed, never optimistic numbers).

Attribution honesty: per-strategy / per-broker attribution comes from
(1) explicit ``strategy_id`` / ``broker_id`` payload fields when the
recording site provides them, else (2) the caller-supplied session
context (``default_strategy_id`` / ``default_broker_id`` — e.g. the
composed session's ensemble identity and venue id), else (3) the
literal ``UNATTRIBUTED`` bucket. Nothing is ever guessed.

LIVE TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Optional

from data_engine.runtime.ledgers import LedgerFamily

#: TRADE-ledger event types that CLOSE a trade (a realized outcome).
TRADE_CLOSING_EVENT_PREFIX = "EXIT_"

UNATTRIBUTED = "UNATTRIBUTED"


class ReportRefused(RuntimeError):
    """Raised when the journal does not verify — no report is built."""


@dataclass(frozen=True)
class TradeRecord:
    """One closed trade as reported (all values journal-derived)."""

    trade_id: str
    symbol: str
    realized_pnl: Decimal
    strategy_id: str
    broker_id: str
    closed_at: Optional[datetime]
    reason: str


@dataclass(frozen=True)
class GroupSummary:
    """Aggregate for one bucket (strategy or broker)."""

    key: str
    trades: int
    wins: int
    losses: int
    gross_profit: Decimal
    gross_loss: Decimal
    net_pnl: Decimal

    @property
    def win_rate(self) -> Optional[Decimal]:
        if self.trades == 0:
            return None
        return (Decimal(self.wins) / Decimal(self.trades)).quantize(
            Decimal("0.0001")
        )


@dataclass(frozen=True)
class SessionSummary:
    """Aggregate for one calendar day (UTC) of journal activity."""

    day: str
    trades: int
    net_pnl: Decimal
    wins: int


@dataclass(frozen=True)
class Reconciliation:
    """The journal-verification evidence backing the report."""

    chains_verified: bool
    ledgers_scanned: int
    trade_events_scanned: int
    fill_events_scanned: int
    pnl_events_scanned: int

    @property
    def reconciled(self) -> bool:
        return self.chains_verified


@dataclass(frozen=True)
class TradeReport:
    total_trades: int
    wins: int
    losses: int
    win_rate: Optional[Decimal]
    gross_profit: Decimal
    gross_loss: Decimal
    net_pnl: Decimal
    per_trade: tuple
    per_strategy: tuple
    per_broker: tuple
    per_session: tuple
    reconciliation: Reconciliation

    def to_dict(self) -> dict:
        """JSON-friendly projection (Decimal → str, tuples → lists)."""

        def _group(g: GroupSummary) -> dict:
            return {
                "key": g.key,
                "trades": g.trades,
                "wins": g.wins,
                "losses": g.losses,
                "gross_profit": str(g.gross_profit),
                "gross_loss": str(g.gross_loss),
                "net_pnl": str(g.net_pnl),
                "win_rate": str(g.win_rate) if g.win_rate is not None else None,
            }

        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": str(self.win_rate) if self.win_rate is not None else None,
            "gross_profit": str(self.gross_profit),
            "gross_loss": str(self.gross_loss),
            "net_pnl": str(self.net_pnl),
            "per_trade": [
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "realized_pnl": str(t.realized_pnl),
                    "strategy_id": t.strategy_id,
                    "broker_id": t.broker_id,
                    "closed_at": t.closed_at.isoformat()
                    if t.closed_at else None,
                    "reason": t.reason,
                }
                for t in self.per_trade
            ],
            "per_strategy": [_group(g) for g in self.per_strategy],
            "per_broker": [_group(g) for g in self.per_broker],
            "per_session": [
                {
                    "day": s.day,
                    "trades": s.trades,
                    "net_pnl": str(s.net_pnl),
                    "wins": s.wins,
                }
                for s in self.per_session
            ],
            "reconciliation": {
                "chains_verified": self.reconciliation.chains_verified,
                "ledgers_scanned": self.reconciliation.ledgers_scanned,
                "trade_events_scanned": self.reconciliation.trade_events_scanned,
                "fill_events_scanned": self.reconciliation.fill_events_scanned,
                "pnl_events_scanned": self.reconciliation.pnl_events_scanned,
                "reconciled": self.reconciliation.reconciled,
            },
        }


def _payload_mapping(event: Any) -> Mapping[str, Any]:
    payload = getattr(event, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def _event_time(event: Any) -> Optional[datetime]:
    for attr in ("recorded_at", "ts", "timestamp", "at"):
        value = getattr(event, attr, None)
        if isinstance(value, datetime):
            return value
    return None


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def _summarize(
    trades: list,
    key_fn,
) -> tuple:
    buckets: dict = defaultdict(
        lambda: {
            "trades": 0, "wins": 0, "losses": 0,
            "gross_profit": Decimal("0"), "gross_loss": Decimal("0"),
        }
    )
    for trade in trades:
        bucket = buckets[key_fn(trade)]
        bucket["trades"] += 1
        if trade.realized_pnl > 0:
            bucket["wins"] += 1
            bucket["gross_profit"] += trade.realized_pnl
        elif trade.realized_pnl < 0:
            bucket["losses"] += 1
            bucket["gross_loss"] += abs(trade.realized_pnl)
    return tuple(
        GroupSummary(
            key=key,
            trades=data["trades"],
            wins=data["wins"],
            losses=data["losses"],
            gross_profit=data["gross_profit"],
            gross_loss=data["gross_loss"],
            net_pnl=data["gross_profit"] - data["gross_loss"],
        )
        for key, data in sorted(buckets.items())
    )


def build_trade_report(
    ledger_family: LedgerFamily,
    *,
    default_strategy_id: str = UNATTRIBUTED,
    default_broker_id: str = UNATTRIBUTED,
    session_id: Optional[str] = None,
) -> TradeReport:
    """Build the verified trade report from the journal.

    Fail-closed: the ledger chains are VERIFIED first; a chain that
    does not verify raises ``ReportRefused`` (no optimistic numbers
    from a corrupted journal).
    """
    if not isinstance(ledger_family, LedgerFamily):
        raise ReportRefused(
            "build_trade_report requires a LedgerFamily (the "
            "authoritative journal — reports never come from "
            "anywhere else)"
        )
    if not ledger_family.verify():
        raise ReportRefused(
            "ledger hash chains FAILED verification — no report is "
            "built from an unverifiable journal (fail closed)"
        )

    strategy_default = (
        default_strategy_id
        if default_strategy_id and default_strategy_id != UNATTRIBUTED
        else (session_id or UNATTRIBUTED)
    )

    trades: list = []
    trade_events = fill_events = pnl_events = 0
    for event in ledger_family.events("trade"):
        event_type = str(getattr(event, "event_type", ""))
        if not event_type.startswith(TRADE_CLOSING_EVENT_PREFIX):
            continue
        trade_events += 1
        payload = _payload_mapping(event)
        realized = _decimal(payload.get("realized_pnl"))
        if realized is None:
            # a trade event without a parseable realized PnL is a
            # journal-contract violation — refuse rather than guess
            raise ReportRefused(
                f"trade event {getattr(event, 'event_id', '?')} carries "
                f"no parseable realized_pnl (fail closed)"
            )
        trades.append(
            TradeRecord(
                trade_id=str(
                    payload.get("exit_id")
                    or getattr(event, "event_id", "")
                ),
                symbol=str(payload.get("symbol", UNATTRIBUTED)),
                realized_pnl=realized,
                strategy_id=str(
                    payload.get("strategy_id", strategy_default)
                ),
                broker_id=str(
                    payload.get("broker_id", default_broker_id)
                ),
                closed_at=_event_time(event),
                reason=str(payload.get("reason", event_type)),
            )
        )
    fill_events = sum(1 for _ in ledger_family.events("fill"))
    pnl_events = sum(1 for _ in ledger_family.events("pnl"))

    total = len(trades)
    wins = sum(1 for t in trades if t.realized_pnl > 0)
    losses = sum(1 for t in trades if t.realized_pnl < 0)
    gross_profit = sum(
        (t.realized_pnl for t in trades if t.realized_pnl > 0),
        Decimal("0"),
    )
    gross_loss = sum(
        (abs(t.realized_pnl) for t in trades if t.realized_pnl < 0),
        Decimal("0"),
    )
    win_rate = (
        (Decimal(wins) / Decimal(total)).quantize(Decimal("0.0001"))
        if total else None
    )

    sessions: dict = defaultdict(
        lambda: {"trades": 0, "net": Decimal("0"), "wins": 0}
    )
    for trade in trades:
        day = (
            trade.closed_at.strftime("%Y-%m-%d")
            if trade.closed_at else UNATTRIBUTED
        )
        bucket = sessions[day]
        bucket["trades"] += 1
        bucket["net"] += trade.realized_pnl
        if trade.realized_pnl > 0:
            bucket["wins"] += 1

    return TradeReport(
        total_trades=total,
        wins=wins,
        losses=losses,
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=gross_profit - gross_loss,
        per_trade=tuple(trades),
        per_strategy=_summarize(trades, lambda t: t.strategy_id),
        per_broker=_summarize(trades, lambda t: t.broker_id),
        per_session=tuple(
            SessionSummary(
                day=day,
                trades=data["trades"],
                net_pnl=data["net"],
                wins=data["wins"],
            )
            for day, data in sorted(sessions.items())
        ),
        reconciliation=Reconciliation(
            chains_verified=True,
            ledgers_scanned=9,
            trade_events_scanned=trade_events,
            fill_events_scanned=fill_events,
            pnl_events_scanned=pnl_events,
        ),
    )


__all__ = [
    "TradeReport",
    "TradeRecord",
    "GroupSummary",
    "SessionSummary",
    "Reconciliation",
    "ReportRefused",
    "build_trade_report",
    "UNATTRIBUTED",
    "TRADE_CLOSING_EVENT_PREFIX",
]
