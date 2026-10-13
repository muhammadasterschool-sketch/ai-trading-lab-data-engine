"""Read-only mobile-friendly dashboard view tests (Batch 20).

The mandate's §9 requires a mobile-friendly read-only view where
supported by the architecture. The dashboard is a server-rendered
plain-HTML projection (no JS, no user input) — Batch 20 closes two
VERIFIED rendering gaps, RED-first:

1. MOBILE VIEWPORT — the page had no `<meta name="viewport">` and no
   responsive CSS, so wide tables overflow phone screens.
2. UNRENDERED SNAPSHOT SECTIONS — `PlatformSnapshot` CARRIES
   `open_positions`, `trade_history` and `strategy_performance`
   (exposed via `/api/snapshot`) but `render_html` never rendered
   them; the mandate's positions/orders visibility was therefore
   JSON-only.

Security posture is UNCHANGED and re-pinned here: GET-only surface,
no scripting, all values HTML-escaped, unmistakable simulation-status
labelling (mode column + banner), no trading or administrative
commands, loopback default.

This is a RESPONSIVE WEB INTERFACE, not a mobile application — no
such claim is made or tested.
"""

from datetime import UTC, datetime
from decimal import Decimal  # noqa: F401  (parity with sibling suites)

from data_engine.platform.dashboard import (
    PlatformSnapshot,
    SystemHealthView,
    build_snapshot,
    render_html,
)
from data_engine.platform.workbook import (
    OpenPositionRecord,
    StrategyPerformanceRecord,
    TradeRecord,
)

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
SYNC = T0.isoformat()


def _health() -> SystemHealthView:
    return SystemHealthView(
        paper_ready=False,
        live_authorized=False,
        blocked_gates=("REAL_DATA_READY", "OPERATIONAL_FEED_READY"),
        passing_gates=("PERSISTENCE_MANDATORY",),
        notes=("VERIFIED_YEARS=0 — no verified real data yet",),
    )


def _position() -> OpenPositionRecord:
    return OpenPositionRecord(
        position_id="pos-1",
        mode="paper",
        instrument_id="XAU/USD",
        strategy_id="strat-1",
        direction="long",
        entry_price=2350.0,
        current_price=2351.5,
        position_size=0.1,
        unrealized_pl=0.15,
        stop_loss=2340.0,
        take_profit=2380.0,
        exposure=235.15,
        last_update=T0,
    )


def _trade() -> TradeRecord:
    return TradeRecord(
        trade_id="tr-1",
        timestamp=T0,
        instrument_id="XAU/USD",
        strategy_id="strat-1",
        strategy_version="v1",
        broker="paper-mock",
        account_mode="paper",
        trade_mode="paper",
        direction="long",
        order_type="MARKET",
        entry_price=2350.0,
        exit_price=2355.0,
        position_size=0.1,
        fees=0.047,
        spread_cost=0.002,
        slippage_cost=0.0,
        realized_pl=0.45,
        status="CLOSED",
    )


def _performance() -> StrategyPerformanceRecord:
    return StrategyPerformanceRecord(
        strategy_id="strat-1",
        strategy_version="v1",
        instrument_id="XAU/USD",
        trade_count=1,
        net_pl=0.45,
        win_rate=1.0,
        profit_factor=None,
        max_drawdown=0.0,
        current_mode="paper",
        paper_status="running",
    )


def _page(**overrides) -> str:
    kwargs = dict(
        health=_health(),
        open_positions=(_position(),),
        trades=(_trade(),),
        performance=(_performance(),),
    )
    kwargs.update(overrides)
    snapshot = build_snapshot(SYNC, **kwargs)
    return render_html(snapshot)


class TestMobileViewport:

    def test_viewport_meta_present(self):
        page = _page()
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in page

    def test_responsive_css_present(self):
        page = _page()
        assert "@media" in page
        assert "tablewrap" in page  # horizontal scroll container for wide tables

    def test_no_javascript_ever(self):
        page = _page()
        assert "<script" not in page.lower()
        assert "onerror=" not in page.lower()


class TestRenderedSections:

    def test_open_positions_rendered_with_mode_label(self):
        page = _page()
        assert "Open Positions" in page
        assert "pos-1" in page
        assert "paper" in page  # unmistakable simulation-status label

    def test_trade_history_rendered(self):
        page = _page()
        assert "Trade History" in page
        assert "tr-1" in page
        assert "paper-mock" in page

    def test_strategy_performance_rendered(self):
        page = _page()
        assert "Strategy Performance" in page
        assert "strat-1" in page

    def test_sections_render_safely_escaped(self):
        evil = OpenPositionRecord(
            position_id="<script>alert(1)</script>",
            mode="paper",
            instrument_id="XAU/USD",
            strategy_id="strat-<b>evil</b>",
            direction="long",
            entry_price=1.0,
            current_price=1.0,
            position_size=1.0,
            unrealized_pl=0.0,
            exposure=1.0,
            last_update=T0,
        )
        page = _page(open_positions=(evil,))
        assert "<script>alert(1)</script>" not in page
        assert "&lt;script&gt;" in page

    def test_empty_sections_render_honestly(self):
        snapshot = build_snapshot(SYNC, health=_health())
        page = render_html(snapshot)
        assert "no records" in page  # never fabricated rows


class TestSimulationStatusUnmistakable:

    def test_banner_and_mode_labels(self):
        page = _page()
        assert "LIVE TRADING: NOT AUTHORIZED" in page
        assert "paper" in page  # every position/trade row carries its mode

    def test_snapshot_contract_unchanged(self):
        # The JSON surface (/api/snapshot) is untouched by the rendering
        # change: same fields, same contract version.
        snapshot = build_snapshot(
            SYNC,
            health=_health(),
            open_positions=(_position(),),
            trades=(_trade(),),
            performance=(_performance(),),
        )
        assert isinstance(snapshot, PlatformSnapshot)
        assert snapshot.open_positions[0]["mode"] == "paper"
        assert snapshot.trade_history[0]["trade_mode"] == "paper"
        assert snapshot.strategy_performance[0]["current_mode"] == "paper"
