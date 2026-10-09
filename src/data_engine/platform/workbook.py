"""Central Instrument Registry workbook export (platform mandate Phase E).

Sheets A–G per the mandate:
  A. Instrument Registry  B. Trade Log  C. Strategy Performance
  D. Open Positions       E. Market Watch
  F. System Audit Log     G. News Log

The workbook is a REPORTING PROJECTION, never the authoritative store:
the registry / strategy lab / news service / audit log own the records;
the exporter renders rows at a supplied synchronization timestamp
(explicit — deterministic in tests). XLSX via openpyxl (approved
dependency addition 2026-10-10); CSV per sheet for portability.

The XLSX container itself embeds generation timestamps in its zip
metadata, so byte-level XLSX determinism is not claimed; the CSV
exports ARE byte-deterministic for identical inputs.
"""

import csv
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, ConfigDict, Field

from data_engine.platform.events import AuditLog
from data_engine.platform.news import NewsItem
from data_engine.platform.registry import Capability, InstrumentRegistry

SHEET_NAMES = (
    "A Instrument Registry",
    "B Trade Log",
    "C Strategy Performance",
    "D Open Positions",
    "E Market Watch",
    "F System Audit Log",
    "G News Log",
)

TRADE_MODES = ("paper", "demo", "live")


class TradeRecord(BaseModel):
    """Projection row for Sheet B (trade log)."""

    model_config = ConfigDict(frozen=True)

    trade_id: str
    timestamp: datetime
    instrument_id: str
    strategy_id: str
    strategy_version: str
    broker: str
    account_mode: str = Field(pattern="^(paper|demo|live)$")
    trade_mode: str = Field(pattern="^(paper|demo|live)$")
    direction: str = Field(pattern="^(long|short)$")
    order_type: str
    entry_price: float
    exit_price: Optional[float] = None
    position_size: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    fees: float = 0.0
    spread_cost: float = 0.0
    slippage_cost: float = 0.0
    realized_pl: float = 0.0
    unrealized_pl: Optional[float] = None
    status: str
    broker_order_id: Optional[str] = None
    broker_position_id: Optional[str] = None
    exit_reason: Optional[str] = None
    risk_checks: str = "passed"
    audit_reference: Optional[str] = None


class StrategyPerformanceRecord(BaseModel):
    """Projection row for Sheet C."""

    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str
    instrument_id: str
    trade_count: int
    net_pl: float
    win_rate: float
    profit_factor: Optional[float] = None
    max_drawdown: float
    current_mode: str = Field(pattern="^(paper|demo|live|idle)$")
    paper_status: str = "not_started"


class OpenPositionRecord(BaseModel):
    """Projection row for Sheet D (paper/demo/live separated by mode)."""

    model_config = ConfigDict(frozen=True)

    position_id: str
    mode: str = Field(pattern="^(paper|demo|live)$")
    instrument_id: str
    strategy_id: str
    direction: str = Field(pattern="^(long|short)$")
    entry_price: float
    current_price: float
    position_size: float
    unrealized_pl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    exposure: float
    last_update: datetime


class MarketWatchEntry(BaseModel):
    """Projection row for Sheet E."""

    model_config = ConfigDict(frozen=True)

    instrument_id: str
    monitoring: bool
    last_price: Optional[float] = None
    last_price_time: Optional[datetime] = None
    timeframe: Optional[str] = None
    latest_signal: Optional[str] = None
    signal_time: Optional[datetime] = None
    data_fresh: bool = True
    data_error: Optional[str] = None


_HEADERS = {
    "A Instrument Registry": (
        "Internal Instrument ID", "Canonical Name", "Instrument Type", "Exchange/Market",
        "Original MT5 Symbol", "TradingView Symbol", "Broker", "Currency",
        "Contract Specs", "Supported Timeframes", "Market Data Status",
        "Historical Data Status", "Strategy Eligibility", "Paper Trading Enabled",
        "Live Trading Enabled", "Discovery Source", "First Discovered",
        "Last Verified", "Current Monitoring Status", "Notes and Limitations",
    ),
    "B Trade Log": (
        "Trade ID", "Timestamp", "Instrument", "Strategy ID", "Strategy Version",
        "Broker", "Account Mode", "Trade Mode", "Direction", "Order Type",
        "Entry Price", "Exit Price", "Position Size", "Stop-Loss", "Take-Profit",
        "Fees", "Spread Cost", "Slippage Cost", "Realized P/L", "Unrealized P/L",
        "Trade Status", "Broker Order ID", "Broker Position ID", "Exit Reason",
        "Risk Checks", "Audit Reference",
    ),
    "C Strategy Performance": (
        "Strategy ID", "Strategy Version", "Instrument", "Trade Count", "Net P/L",
        "Win Rate", "Profit Factor", "Max Drawdown", "Current Mode", "Paper/Live Status",
    ),
    "D Open Positions": (
        "Position ID", "Mode", "Instrument", "Strategy ID", "Direction", "Entry Price",
        "Current Price", "Position Size", "Unrealized P/L", "Stop-Loss", "Take-Profit",
        "Exposure", "Last Update",
    ),
    "E Market Watch": (
        "Instrument ID", "Monitoring", "Latest Price", "Price Timestamp", "Timeframe",
        "Latest Signal", "Signal Time", "Data Fresh", "Data Error",
    ),
    "F System Audit Log": (
        "Timestamp", "Component", "Event", "Detail", "Reference ID",
    ),
    "G News Log": (
        "News ID", "Headline", "Source", "Original URL", "Published At", "Retrieved At",
        "Affected Instrument IDs", "Sentiment", "Event Category", "Estimated Impact",
        "Confidence", "Verification Status", "Alert Status", "Audit Reference",
    ),
}

_HEADER_FILL = PatternFill(start_color="FF1F4E78", end_color="FF1F4E78", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)


def _instrument_row(rec) -> tuple:
    def mt5_symbols(r):
        return "; ".join(
            m.provider_symbol for m in r.provider_symbols if m.provider.startswith("mt5")
        ) or "—"

    def tv_symbol(r):
        for m in r.provider_symbols:
            if m.provider == "tradingview":
                return m.provider_symbol if m.verified else f"{m.provider_symbol} (unverified)"
        return "—"

    return (
        rec.internal_id,
        rec.instrument.symbol,
        rec.instrument.asset_class.value,
        rec.instrument.exchange or rec.instrument.venue or "—",
        mt5_symbols(rec),
        tv_symbol(rec),
        "; ".join(sorted({m.provider.split(":", 1)[1] for m in rec.provider_symbols if m.provider.startswith("mt5:")})) or "—",
        rec.instrument.currency,
        f"contract_type={rec.instrument.contract_type.value}",
        "; ".join(rec.supported_timeframes) or "—",
        rec.eligibility(Capability.MONITORING).value,
        rec.data_state.value if rec.data_state is not None else "NOT_ASSESSED",
        "yes" if rec.strategy_eligible else "no",
        "yes" if rec.eligibility(Capability.PAPER_TRADING).value == "Eligible" else "no",
        rec.eligibility(Capability.LIVE_TRADING).value,
        rec.discovery_source,
        rec.first_discovered.isoformat(),
        rec.last_verified.isoformat() if rec.last_verified else "—",
        "Monitoring" if rec.monitoring else "Registered",
        "; ".join(rec.notes) or "—",
    )


def _trade_row(t: TradeRecord) -> tuple:
    return (
        t.trade_id, t.timestamp.isoformat(), t.instrument_id, t.strategy_id,
        t.strategy_version, t.broker, t.account_mode, t.trade_mode, t.direction,
        t.order_type, t.entry_price, t.exit_price if t.exit_price is not None else "",
        t.position_size, t.stop_loss if t.stop_loss is not None else "",
        t.take_profit if t.take_profit is not None else "", t.fees, t.spread_cost,
        t.slippage_cost, t.realized_pl,
        t.unrealized_pl if t.unrealized_pl is not None else "", t.status,
        t.broker_order_id or "", t.broker_position_id or "", t.exit_reason or "",
        t.risk_checks, t.audit_reference or "",
    )


def _perf_row(p: StrategyPerformanceRecord) -> tuple:
    return (
        p.strategy_id, p.strategy_version, p.instrument_id, p.trade_count, p.net_pl,
        p.win_rate, p.profit_factor if p.profit_factor is not None else "",
        p.max_drawdown, p.current_mode, p.paper_status,
    )


def _position_row(o: OpenPositionRecord) -> tuple:
    return (
        o.position_id, o.mode, o.instrument_id, o.strategy_id, o.direction,
        o.entry_price, o.current_price, o.position_size, o.unrealized_pl,
        o.stop_loss if o.stop_loss is not None else "",
        o.take_profit if o.take_profit is not None else "", o.exposure,
        o.last_update.isoformat(),
    )


def _watch_row(w: MarketWatchEntry) -> tuple:
    return (
        w.instrument_id, "yes" if w.monitoring else "no",
        w.last_price if w.last_price is not None else "",
        w.last_price_time.isoformat() if w.last_price_time else "",
        w.timeframe or "", w.latest_signal or "",
        w.signal_time.isoformat() if w.signal_time else "",
        "fresh" if w.data_fresh else "stale", w.data_error or "",
    )


def _news_row(n: NewsItem) -> tuple:
    return (
        n.news_id, n.headline, n.source, n.url, n.published_at.isoformat(),
        n.retrieved_at.isoformat(), "; ".join(n.affected_instruments) or "—",
        n.sentiment.value, n.category.value, n.impact_estimate.value,
        n.confidence, n.verification.value, n.alert_status, n.audit_reference or "",
    )


class WorkbookExporter:
    """Renders the synchronized workbook from authoritative services."""

    def __init__(
        self,
        registry: InstrumentRegistry,
        audit_log: Optional[AuditLog] = None,
        trades: Sequence[TradeRecord] = (),
        performance: Sequence[StrategyPerformanceRecord] = (),
        open_positions: Sequence[OpenPositionRecord] = (),
        market_watch: Sequence[MarketWatchEntry] = (),
        news: Sequence[NewsItem] = (),
    ) -> None:
        self._registry = registry
        self._audit = audit_log
        self._trades = list(trades)
        self._performance = list(performance)
        self._positions = list(open_positions)
        self._watch = list(market_watch)
        self._news = list(news)

    def _sheet_rows(self, sheet: str) -> tuple:
        if sheet == SHEET_NAMES[0]:
            return tuple(_instrument_row(r) for r in self._registry.all_records())
        if sheet == SHEET_NAMES[1]:
            return tuple(_trade_row(t) for t in self._trades)
        if sheet == SHEET_NAMES[2]:
            return tuple(_perf_row(p) for p in self._performance)
        if sheet == SHEET_NAMES[3]:
            return tuple(_position_row(o) for o in self._positions)
        if sheet == SHEET_NAMES[4]:
            return tuple(_watch_row(w) for w in self._watch)
        if sheet == SHEET_NAMES[5]:
            return self._audit.rows() if self._audit is not None else ()
        if sheet == SHEET_NAMES[6]:
            return tuple(_news_row(n) for n in self._news)
        raise KeyError(sheet)

    def _validate_unique_ids(self) -> None:
        trade_ids = [t.trade_id for t in self._trades]
        if len(trade_ids) != len(set(trade_ids)):
            raise ValueError("duplicate trade_id in trade log — refusing export")
        for rec in self._registry.all_records():
            pass  # registry already guarantees unique internal ids

    def export_xlsx(self, path: Path, last_sync: datetime) -> Path:
        """Write the workbook; ``last_sync`` is rendered on every sheet header
        (filters + frozen header row; no historical record is overwritten —
        the file is a fresh projection of current authoritative state)."""
        self._validate_unique_ids()
        wb = Workbook()
        wb.remove(wb.active)
        for sheet in SHEET_NAMES:
            ws = wb.create_sheet(title=sheet)
            headers = _HEADERS[sheet]
            ws.append(headers)
            ws.append(("Last successful synchronization:", last_sync.isoformat()))
            for row in self._sheet_rows(sheet):
                ws.append(row)
            for cell in ws[1]:
                cell.fill = _HEADER_FILL
                cell.font = _HEADER_FONT
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 1)}"
        wb.save(path)
        return path

    def export_csv(self, directory: Path, last_sync: datetime) -> tuple[Path, ...]:
        """One deterministic CSV per sheet (byte-stable for same inputs)."""
        self._validate_unique_ids()
        directory.mkdir(parents=True, exist_ok=True)
        written = []
        for sheet in SHEET_NAMES:
            slug = (
                sheet.split(" ", 1)[1].lower().replace(" ", "_")
            )
            target = directory / f"{slug}.csv"
            with open(target, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(_HEADERS[sheet])
                for row in self._sheet_rows(sheet):
                    writer.writerow(row)
            written.append(target)
        return tuple(written)
