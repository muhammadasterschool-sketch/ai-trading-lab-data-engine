"""Read-only platform API + dashboard (platform mandate Phase J).

The smallest compatible surface: NO web framework dependency — a
stdlib ``http.server`` view layer over a frozen ``PlatformSnapshot``
projection. Contracts:

- READ-ONLY: GET /api/snapshot and GET / (HTML) are the only routes;
  every non-GET method is 405, every unknown path 404. There is no
  write surface, no parameterized file access, no template engine, no
  user code execution.
- HONEST BY CONSTRUCTION: the snapshot renders exactly what the
  authoritative services hold. Live trading shows NOT AUTHORIZED
  everywhere; market watch rows without a supplied price render
  ``no_data`` — never a fabricated price; providers that are not
  connected render ``disconnected``/``unavailable``.
- The snapshot is built from a caller-supplied LOGICAL timestamp (INV-01:
  no wall-clock inside identity payloads; the header renders the
  caller's synchronization timestamp).
- Paper/demo/live states are distinguished per record; paper readiness
  and blocked gates are reported verbatim from the supplied health view.
"""

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from data_engine.platform.events import AuditLog
from data_engine.platform.news import NewsIntelligenceService
from data_engine.platform.registry import (
    Capability,
    EligibilityStatus,
    InstrumentRegistry,
)
from data_engine.platform.strategy_lab import StrategyLab
from data_engine.platform.workbook import (
    MarketWatchEntry,
    OpenPositionRecord,
    StrategyPerformanceRecord,
    TradeRecord,
)

DASHBOARD_CONTRACT_VERSION = "1.0.0"


class SystemHealthView(BaseModel):
    """Honest system status — rendered verbatim, never inferred."""

    model_config = ConfigDict(frozen=True)

    paper_ready: bool = False
    live_authorized: bool = False  # frozen honest default
    blocked_gates: tuple[str, ...] = ()
    passing_gates: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class InstrumentView(BaseModel):
    model_config = ConfigDict(frozen=True)

    internal_id: str
    symbol: str
    asset_class: str
    monitoring: str  # Registered | Monitoring
    data_state: str  # NOT_ASSESSED | SYNTHETIC | REAL_UNVERIFIED | ...
    research: str
    backtesting: str
    paper_trading: str
    live_trading: str
    provider_symbols: tuple[str, ...] = ()
    discovery_source: str = ""


class StrategyView(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    name: str
    current_version: int
    state: str
    enabled: bool
    instruments: tuple[str, ...] = ()
    evidence_count: int = 0


class NewsView(BaseModel):
    model_config = ConfigDict(frozen=True)

    news_id: str
    headline: str
    source: str
    published_at: str
    verification: str
    affected_instruments: tuple[str, ...] = ()


class DatasetView(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_id: str
    file_name: str
    kind: str
    row_count: int
    instrument_count: int
    data_state: str
    verification_notes: tuple[str, ...] = ()


class MarketWatchView(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: str
    monitoring: bool
    last_price: Optional[float] = None
    price_rendered: str  # number | no_data (NEVER fabricated)
    data_fresh: bool = True


class PlatformSnapshot(BaseModel):
    """Complete read-only dashboard projection."""

    model_config = ConfigDict(frozen=True)

    contract_version: str = DASHBOARD_CONTRACT_VERSION
    synchronized_at: str  # logical, caller-supplied
    system_health: SystemHealthView = Field(default_factory=SystemHealthView)
    instruments: tuple[InstrumentView, ...] = ()
    strategies: tuple[StrategyView, ...] = ()
    news: tuple[NewsView, ...] = ()
    datasets: tuple[DatasetView, ...] = ()
    market_watch: tuple[MarketWatchView, ...] = ()
    audit_events: tuple[tuple[str, str, str, str], ...] = ()
    open_positions: tuple[dict[str, Any], ...] = ()
    trade_history: tuple[dict[str, Any], ...] = ()
    strategy_performance: tuple[dict[str, Any], ...] = ()
    risk_alerts: tuple[str, ...] = ()

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=False)


def build_snapshot(
    synchronized_at: str,
    registry: Optional[InstrumentRegistry] = None,
    strategy_lab: Optional[StrategyLab] = None,
    news: Optional[NewsIntelligenceService] = None,
    audit_log: Optional[AuditLog] = None,
    datasets: tuple[Any, ...] = (),
    health: Optional[SystemHealthView] = None,
    market_watch: tuple[MarketWatchEntry, ...] = (),
    open_positions: tuple[OpenPositionRecord, ...] = (),
    trades: tuple[TradeRecord, ...] = (),
    performance: tuple[StrategyPerformanceRecord, ...] = (),
    risk_alerts: tuple[str, ...] = (),
) -> PlatformSnapshot:
    """Project the authoritative services into the dashboard view."""
    instruments: tuple[InstrumentView, ...] = ()
    if registry is not None:
        instruments = tuple(
            InstrumentView(
                internal_id=r.internal_id,
                symbol=r.instrument.symbol,
                asset_class=r.instrument.asset_class.value,
                monitoring=(
                    "Monitoring" if r.monitoring else "Registered"
                ),
                data_state=(
                    r.data_state.value if r.data_state is not None else "NOT_ASSESSED"
                ),
                research=r.eligibility(Capability.RESEARCH).value,
                backtesting=r.eligibility(Capability.BACKTESTING).value,
                paper_trading=r.eligibility(Capability.PAPER_TRADING).value,
                live_trading=r.eligibility(Capability.LIVE_TRADING).value,
                provider_symbols=tuple(
                    f"{m.provider}={m.provider_symbol}" for m in r.provider_symbols
                ),
                discovery_source=r.discovery_source,
            )
            for r in registry.all_records()
        )

    strategies: tuple[StrategyView, ...] = ()
    if strategy_lab is not None:
        strategies = tuple(
            StrategyView(
                strategy_id=s.strategy_id,
                name=s.name,
                current_version=s.current_version,
                state=s.state.value,
                enabled=s.enabled,
                instruments=s.instruments,
                evidence_count=len(s.evidence),
            )
            for s in strategy_lab.all_strategies()
        )

    news_views: tuple[NewsView, ...] = ()
    if news is not None:
        news_views = tuple(
            NewsView(
                news_id=n.news_id,
                headline=n.headline,
                source=n.source,
                published_at=n.published_at.isoformat(),
                verification=n.verification.value,
                affected_instruments=n.affected_instruments,
            )
            for n in news.all_items()
        )

    dataset_views = tuple(
        DatasetView(
            dataset_id=d.dataset_id,
            file_name=d.file_name,
            kind=d.kind.value,
            row_count=d.row_count,
            instrument_count=d.instrument_count,
            data_state=d.data_state.value,
            verification_notes=d.verification_notes,
        )
        for d in datasets
    )

    watch_views = tuple(
        MarketWatchView(
            instrument_id=w.instrument_id,
            monitoring=w.monitoring,
            last_price=w.last_price,
            price_rendered=(
                repr(w.last_price) if w.last_price is not None else "no_data"
            ),
            data_fresh=w.data_fresh,
        )
        for w in market_watch
    )

    audit_rows = (
        tuple(
            (e.timestamp.isoformat(), e.component, e.event, e.detail or "")
            for e in audit_log.events()
        )
        if audit_log is not None
        else ()
    )

    return PlatformSnapshot(
        synchronized_at=synchronized_at,
        system_health=health or SystemHealthView(),
        instruments=instruments,
        strategies=strategies,
        news=news_views,
        datasets=dataset_views,
        market_watch=watch_views,
        audit_events=audit_rows,
        open_positions=tuple(p.model_dump() for p in open_positions),
        trade_history=tuple(t.model_dump() for t in trades),
        strategy_performance=tuple(p.model_dump() for p in performance),
        risk_alerts=risk_alerts,
    )


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "<p class='empty'>no records</p>"
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(snapshot: PlatformSnapshot) -> str:
    """Server-side rendered overview page (plain HTML, no JS, no user input)."""
    h = snapshot.system_health
    health_rows = [
        ["Paper trading ready", "YES" if h.paper_ready else "NO"],
        ["Live trading", "NOT AUTHORIZED" if not h.live_authorized else "AUTHORIZED"],
        ["Blocked gates", "; ".join(h.blocked_gates) or "none reported"],
        ["Passing gates (count)", str(len(h.passing_gates))],
    ]
    for note in h.notes:
        health_rows.append(["Note", note])

    inst_rows = [
        [
            i.symbol,
            i.asset_class,
            i.monitoring,
            i.data_state,
            i.research,
            i.backtesting,
            i.paper_trading,
            i.live_trading,
        ]
        for i in snapshot.instruments
    ]
    strat_rows = [
        [s.strategy_id, s.name, f"v{s.current_version}", s.state, "on" if s.enabled else "off"]
        for s in snapshot.strategies
    ]
    news_rows = [[n.published_at, n.source, n.headline, n.verification] for n in snapshot.news]
    dataset_rows = [
        [d.file_name, d.kind, str(d.row_count), str(d.instrument_count), d.data_state]
        for d in snapshot.datasets
    ]
    watch_rows = [
        [w.instrument_id, "yes" if w.monitoring else "no", w.price_rendered,
         "fresh" if w.data_fresh else "stale"]
        for w in snapshot.market_watch
    ]
    audit_rows = [list(r) for r in snapshot.audit_events[-50:]]

    alerts = (
        "".join(f"<li>{html.escape(a)}</li>" for a in snapshot.risk_alerts)
        or "<li class='empty'>no active risk alerts</li>"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Trading Lab — Platform Dashboard (READ-ONLY)</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a2e; background: #f7f8fa; }}
  h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.05rem; margin-top: 2rem; border-bottom: 2px solid #1f4e78; padding-bottom: .2rem; }}
  table {{ border-collapse: collapse; width: 100%; background: white; font-size: .85rem; }}
  th {{ background: #1f4e78; color: white; text-align: left; padding: .35rem .5rem; }}
  td {{ border-bottom: 1px solid #e3e6ea; padding: .3rem .5rem; }}
  .empty {{ color: #7a7f87; font-style: italic; }}
  .banner {{ background: #fff3cd; border: 1px solid #d4a017; padding: .6rem 1rem; border-radius: 4px; }}
  .sync {{ color: #555; font-size: .8rem; }}
</style>
</head>
<body>
<h1>AI Trading Lab — Platform Dashboard</h1>
<p class="sync">Synchronized at {html.escape(snapshot.synchronized_at)} &middot; read-only projection &middot; contract v{snapshot.contract_version}</p>
<div class="banner"><strong>LIVE TRADING: NOT AUTHORIZED.</strong> This dashboard is a reporting projection; it holds no execution surface. Market-watch rows without provider data render <em>no_data</em> — never a fabricated price.</div>
<h2>System Health</h2>
{_html_table(["Property", "Value"], health_rows)}
<h2>Historical Datasets</h2>
{_html_table(["File", "Kind", "Rows", "Instruments", "Data State"], dataset_rows)}
<h2>Instrument Registry ({len(snapshot.instruments)})</h2>
{_html_table(
    ["Symbol", "Asset Class", "Monitoring", "Data State", "Research", "Backtesting", "Paper", "Live"],
    inst_rows,
)}
<h2>Strategies ({len(snapshot.strategies)})</h2>
{_html_table(["ID", "Name", "Version", "Lifecycle State", "Enabled"], strat_rows)}
<h2>Market Watch</h2>
{_html_table(["Instrument", "Monitoring", "Latest Price", "Freshness"], watch_rows)}
<h2>News Intelligence ({len(snapshot.news)})</h2>
{_html_table(["Published", "Source", "Headline", "Verification"], news_rows)}
<h2>Risk Alerts</h2>
<ul>{alerts}</ul>
<h2>Audit Log (latest 50)</h2>
{_html_table(["Timestamp", "Component", "Event", "Detail"], audit_rows)}
</body>
</html>"""


class _SnapshotHandler(BaseHTTPRequestHandler):
    """Read-only HTTP handler: GET-only, two routes, no inputs honored."""

    server_version = "AITradingLabDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:  # silence stdout noise
        return

    def _respond(self, code: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        snapshot = self.server.snapshot_provider()  # type: ignore[attr-defined]
        if self.path == "/api/snapshot":
            body = snapshot.to_json().encode("utf-8")
            self._respond(HTTPStatus.OK, body, "application/json; charset=utf-8")
        elif self.path in ("/", "/index.html"):
            body = render_html(snapshot).encode("utf-8")
            self._respond(HTTPStatus.OK, body, "text/html; charset=utf-8")
        else:
            self._respond(
                HTTPStatus.NOT_FOUND,
                b'{"error": "not found", "routes": ["/", "/api/snapshot"]}',
                "application/json",
            )

    def _method_not_allowed(self) -> None:
        self._respond(
            HTTPStatus.METHOD_NOT_ALLOWED,
            b'{"error": "read-only dashboard: only GET is supported"}',
            "application/json",
        )

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_PATCH = _method_not_allowed


class DashboardServer:
    """Serves the read-only dashboard (default bind: loopback only)."""

    def __init__(
        self,
        snapshot_provider: Callable[[], PlatformSnapshot],
        host: str = "127.0.0.1",
        port: int = 8017,
    ) -> None:
        self._provider = snapshot_provider
        self._host = host
        self._port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._serving = False

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}/"

    @property
    def bound_port(self) -> Optional[int]:
        if self._httpd is None:
            return None
        return int(self._httpd.server_address[1])

    def start(self) -> None:
        """Bind (port 0 = ephemeral) WITHOUT serving — test-friendly."""
        self._httpd = ThreadingHTTPServer((self._host, self._port), _SnapshotHandler)
        self._httpd.snapshot_provider = self._provider  # type: ignore[attr-defined]
        if self._port == 0:
            self._port = self.bound_port or self._port

    def serve_forever(self) -> None:
        if self._httpd is None:
            self.start()
        assert self._httpd is not None
        self._serving = True
        try:
            self._httpd.serve_forever()
        finally:
            self._serving = False

    def shutdown(self) -> None:
        """Stop the server. Safe whether or not serve_forever is running."""
        if self._httpd is not None:
            if self._serving:
                self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
