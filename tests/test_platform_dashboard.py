"""Platform package tests — read-only API + dashboard (Phase J).

Verifies the honest-by-construction contracts: live = NOT AUTHORIZED
everywhere, no fabricated prices, snapshot determinism, and the HTTP
surface (GET-only, 405 on writes, 404 on unknown paths) against a real
loopback server on an ephemeral port.
"""

import http.client
import json
import socket
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from data_engine.platform import (
    AuditLog,
    InstrumentRegistry,
    NewsCategory,
    NewsIntelligenceService,
    ProviderSymbolMapping,
    Sentiment,
    StrategyLab,
    StrategyType,
)
from data_engine.platform.dashboard import (
    DashboardServer,
    PlatformSnapshot,
    SystemHealthView,
    build_snapshot,
    render_html,
)
from data_engine.schemas import AssetClass, Instrument

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
SYNC = T0.isoformat()


@pytest.fixture()
def components():
    log = AuditLog()
    reg = InstrumentRegistry(audit_log=log)
    gold = Instrument(
        symbol="XAU/USD", asset_class=AssetClass.METAL, base_asset="XAU", quote_asset="USD"
    )
    reg.register(
        gold,
        "csv:metals_daily",
        T0,
        provider_symbols=(
            ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),
        ),
    )
    lab = StrategyLab(audit_log=log)
    lab.create(
        name="sma-trend",
        strategy_type=StrategyType.RULES,
        spec={"entry": "sma_cross_up"},
        config={"fast": 20, "slow": 50},
        source=None,
        at=T0,
        created_by="operator",
    )
    news = NewsIntelligenceService(audit_log=log)
    news.register(
        headline="Fed holds rates",
        source="reuters",
        url="https://e.com/1",
        published_at=T0 - timedelta(hours=1),
        retrieved_at=T0,
        category=NewsCategory.MONETARY_POLICY,
        sentiment=Sentiment.NEUTRAL,
    )
    return log, reg, lab, news


def _health() -> SystemHealthView:
    return SystemHealthView(
        paper_ready=False,
        live_authorized=False,
        blocked_gates=("REAL_DATA_READY", "GOVERNANCE_READY"),
        passing_gates=("PERSISTENCE_MANDATORY", "READINESS_GATE_ENFORCED"),
        notes=("VERIFIED_YEARS=0 — no verified real data yet",),
    )


class TestSnapshotHonesty:
    def test_live_shows_not_authorized_everywhere(self, components):
        _, reg, lab, news = components
        snap = build_snapshot(
            SYNC, registry=reg, strategy_lab=lab, news=news, health=_health()
        )
        assert all(i.live_trading == "Not Authorized" for i in snap.instruments)
        assert snap.system_health.live_authorized is False

    def test_paper_readiness_rendered_verbatim(self, components):
        _, reg, lab, news = components
        snap = build_snapshot(
            SYNC, registry=reg, strategy_lab=lab, news=news, health=_health()
        )
        assert snap.system_health.paper_ready is False
        assert "REAL_DATA_READY" in snap.system_health.blocked_gates

    def test_no_fabricated_prices(self, components):
        _, reg, _, _ = components
        from data_engine.platform.workbook import MarketWatchEntry

        watch = (
            MarketWatchEntry(instrument_id="iid-gold", monitoring=True, last_price=None),
            MarketWatchEntry(
                instrument_id="iid-gold2", monitoring=True, last_price=2355.0,
                last_price_time=T0, timeframe="1d",
            ),
        )
        snap = build_snapshot(SYNC, registry=reg, market_watch=watch)
        assert snap.market_watch[0].price_rendered == "no_data"
        assert snap.market_watch[0].last_price is None
        assert snap.market_watch[1].price_rendered == "2355.0"

    def test_snapshot_deterministic_for_same_inputs(self, components):
        _, reg, lab, news = components
        s1 = build_snapshot(SYNC, registry=reg, strategy_lab=lab, news=news, health=_health())
        s2 = build_snapshot(SYNC, registry=reg, strategy_lab=lab, news=news, health=_health())
        assert s1.to_json() == s2.to_json()

    def test_html_renders_banner_and_states(self, components):
        _, reg, lab, news = components
        snap = build_snapshot(
            SYNC, registry=reg, strategy_lab=lab, news=news, health=_health()
        )
        page = render_html(snap)
        assert "LIVE TRADING: NOT AUTHORIZED" in page
        assert "XAU/USD" in page
        assert "sma-trend" in page
        assert "Fed holds rates" in page
        assert "REAL_DATA_READY" in page
        # untrusted content must be escaped
        evil = NewsIntelligenceService()
        evil.register(
            headline="<script>alert(1)</script>",
            source="x",
            url="https://e.com/2",
            published_at=T0,
            retrieved_at=T0,
        )
        page2 = render_html(build_snapshot(SYNC, news=evil))
        assert "<script>" not in page2
        assert "&lt;script&gt;" in page2


class _EphemeralServer:
    """Binds an ephemeral loopback port and serves in a daemon thread."""

    def __init__(self, snapshot: PlatformSnapshot) -> None:
        self._server = DashboardServer(lambda: snapshot, host="127.0.0.1", port=0)
        self._server.start()
        self.port = self._server.bound_port
        assert self.port is not None and self.port > 0
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    def request(self, method: str, path: str):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(method, path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def close(self) -> None:
        self._server.shutdown()
        self._thread.join(timeout=5)


class TestHttpSurface:
    @pytest.fixture()
    def snap(self, components):
        _, reg, lab, news = components
        return build_snapshot(
            SYNC, registry=reg, strategy_lab=lab, news=news, health=_health()
        )

    def test_get_root_returns_html(self, snap):
        server = _EphemeralServer(snap)
        try:
            status, body = server.request("GET", "/")
            assert status == 200
            assert b"LIVE TRADING: NOT AUTHORIZED" in body
        finally:
            server.close()

    def test_get_api_returns_json(self, snap):
        server = _EphemeralServer(snap)
        try:
            status, body = server.request("GET", "/api/snapshot")
            assert status == 200
            data = json.loads(body)
            assert data["system_health"]["paper_ready"] is False
            assert data["contract_version"].startswith("1.")
            assert any(
                i["live_trading"] == "Not Authorized" for i in data["instruments"]
            )
        finally:
            server.close()

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
    def test_write_methods_refused_405(self, snap, method):
        server = _EphemeralServer(snap)
        try:
            status, _ = server.request(method, "/api/snapshot")
            assert status == 405
        finally:
            server.close()

    def test_unknown_path_404(self, snap):
        server = _EphemeralServer(snap)
        try:
            status, _ = server.request("GET", "/admin/secret")
            assert status == 404
        finally:
            server.close()

    def test_server_runs_in_thread_and_stops(self, snap):
        server = _EphemeralServer(snap)
        try:
            status, _ = server.request("GET", "/api/snapshot")
            assert status == 200
        finally:
            server.close()
        # after shutdown the port is closed (connection refused)
        with pytest.raises((ConnectionError, socket.error, OSError)):
            server.request("GET", "/api/snapshot")
