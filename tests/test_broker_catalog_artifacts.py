"""Broker catalog + capability-matrix artifact tests (Batch 15).

Pins the two GENERATED artifacts (items C-2/C-3) that Batch 11 §9
recorded as missing:

- ``docs/reports/BROKER_CAPABILITY_MATRIX.md``
- ``docs/reports/INSTRUMENT_CATALOG_REPORT.md``

Proves, deterministically:
- the builders render BYTE-IDENTICAL output on every regeneration
  (fixed discovery timestamp, sorted ordering, no wall-clock/RNG);
- the COMMITTED artifacts match a fresh regeneration exactly (the
  files cannot silently drift from the governed registry);
- the honest invariants hold in the rendered state: every venue is
  MOCK_DETERMINISTIC, all venue mappings are UNVERIFIED, eligibility
  is NEVER granted, LIVE TRADING is NOT AUTHORIZED — and the report
  models REFUSE a fabricated authorized/eligible state;
- the cross-venue canonical merge: the same canonical identity
  discovered at multiple venues is ONE record with MANY mappings.

No network, no credentials, no real orders, no real connectivity.
"""

from datetime import datetime, UTC
from pathlib import Path

import pytest

from data_engine.brokers import (
    BinanceSpotMockAdapter,
    BitgetSpotMockAdapter,
    BrokerCredential,
    BybitV5MockAdapter,
    ExnessMT5MockAdapter,
    MT5StyleMockAdapter,
    PaperBrokerAdapter,
    XMMT5MockAdapter,
    default_registry,
    discover_instruments,
    sync_catalog_to_platform_registry,
)
from data_engine.brokers.catalog_report import (
    build_capability_matrix,
    build_catalog_report,
    render_capability_matrix_markdown,
    render_catalog_report_markdown,
)
from data_engine.platform.registry import InstrumentRegistry

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "reports" / "BROKER_CAPABILITY_MATRIX.md"
CATALOG_PATH = REPO / "docs" / "reports" / "INSTRUMENT_CATALOG_REPORT.md"

#: MUST equal scripts/generate_broker_catalog_artifacts.py FIXED_AT —
#: the fixed discovery timestamp that makes regeneration byte-stable.
FIXED_AT = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)

ACCOUNT = "artifact-test"
SECRET = "mock-secret-material-DO-NOT-PRINT"

FACTORIES = {
    "binance-mock": BinanceSpotMockAdapter,
    "bitget-mock": BitgetSpotMockAdapter,
    "bybit-mock": BybitV5MockAdapter,
    "exness-mock": ExnessMT5MockAdapter,
    "mt5-mock": MT5StyleMockAdapter,
    "paper-mock": PaperBrokerAdapter,
    "xm-mock": XMMT5MockAdapter,
}


def fixed_clock() -> datetime:
    return FIXED_AT


def _discover_all():
    """Discover + sync all SEVEN venues exactly like the generator."""
    registry = default_registry()
    platform = InstrumentRegistry()
    catalogs = []
    for broker_id in sorted(FACTORIES):
        adapter = FACTORIES[broker_id](fixed_clock)
        adapter.connect(BrokerCredential(ACCOUNT, SECRET))
        catalog = discover_instruments(adapter, at=FIXED_AT, registry=registry)
        sync_catalog_to_platform_registry(catalog, platform, at=FIXED_AT)
        catalogs.append(catalog)
    return catalogs, platform


# ════════════════════════════════════════════════════════════════════
# 1. Capability matrix (item C-3)
# ════════════════════════════════════════════════════════════════════

class TestCapabilityMatrixArtifact:

    def test_seven_venues_with_mt5_class_rows(self):
        report = build_capability_matrix(default_registry())
        assert report.venue_count == 7
        rows = {row.broker_id: row for row in report.rows}
        assert set(rows) == set(FACTORIES)
        for broker_id in ("exness-mock", "xm-mock"):
            row = rows[broker_id]
            assert row.execution_mode == "MOCK_DETERMINISTIC"
            assert row.order_kinds == ("MARKET", "LIMIT", "STOP", "STOP_LIMIT")
            assert row.position_mode == "HEDGING"
            assert row.idempotency_key == "COMMENT_FIELD"
            assert row.sl_tp == "ATTACHED"
            assert row.account_modes == ("DEMO",)

    def test_every_venue_is_mock_deterministic(self):
        report = build_capability_matrix(default_registry())
        assert all(r.execution_mode == "MOCK_DETERMINISTIC" for r in report.rows)
        assert report.live_trading_authorized is False

    def test_fabricated_authorized_state_is_refused(self):
        report = build_capability_matrix(default_registry())
        with pytest.raises(Exception):
            report.model_copy(update={"live_trading_authorized": True}) \
                .validate_semantics()

    def test_render_contains_every_broker_and_honesty_banner(self):
        markdown = render_capability_matrix_markdown(
            build_capability_matrix(default_registry())
        )
        for broker_id in FACTORIES:
            assert f"`{broker_id}`" in markdown
        assert "LIVE TRADING IS NOT AUTHORIZED" in markdown
        assert "MOCK_DETERMINISTIC" in markdown
        assert "no real broker connectivity" in markdown.lower()

    def test_rendering_is_deterministic(self):
        first = render_capability_matrix_markdown(
            build_capability_matrix(default_registry())
        )
        second = render_capability_matrix_markdown(
            build_capability_matrix(default_registry())
        )
        assert first == second

    def test_committed_artifact_matches_regeneration(self):
        regenerated = render_capability_matrix_markdown(
            build_capability_matrix(default_registry())
        )
        committed = MATRIX_PATH.read_text(encoding="utf-8")
        assert committed == regenerated


# ════════════════════════════════════════════════════════════════════
# 2. Instrument catalog report (item C-2)
# ════════════════════════════════════════════════════════════════════

class TestCatalogReportArtifact:

    def test_seven_venue_sections_sorted(self):
        catalogs, platform = _discover_all()
        report = build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
        assert report.venue_count == 7
        assert [s.broker_id for s in report.venues] == sorted(FACTORIES)

    def test_five_canonical_identities_with_merged_venue_mappings(self):
        catalogs, platform = _discover_all()
        report = build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
        records = {r.canonical_symbol: r for r in report.canonical_records}
        assert report.canonical_count == 5
        assert set(records) == {"BTC/USDT", "BTC/USD", "ETH/USDT", "EUR/USD", "XAU/USD"}
        # The SAME canonical identity from many venues = ONE record with
        # MANY mappings (duplicate-merge, never forked identity).
        expected_mappings = {
            "BTC/USDT": {"broker:binance-mock", "broker:bitget-mock",
                         "broker:bybit-mock", "broker:paper-mock"},
            "BTC/USD": {"broker:exness-mock", "broker:mt5-mock", "broker:xm-mock"},
            "ETH/USDT": {"broker:binance-mock", "broker:bitget-mock",
                         "broker:bybit-mock"},
            "EUR/USD": {"broker:exness-mock", "broker:mt5-mock",
                        "broker:paper-mock", "broker:xm-mock"},
            "XAU/USD": {"broker:exness-mock", "broker:mt5-mock", "broker:xm-mock"},
        }
        for symbol, expected in expected_mappings.items():
            record = records[symbol]
            actual = {m.provider for m in record.provider_mappings}
            assert actual == expected, symbol
        # All venue mappings start UNVERIFIED; eligibility never granted.
        assert all(
            m.verified is False
            for r in report.canonical_records
            for m in r.provider_mappings
        )
        assert report.eligibility_granted is False

    def test_honest_eligibility_statuses_in_rendered_state(self):
        catalogs, platform = _discover_all()
        report = build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
        for record in report.canonical_records:
            assert record.data_state is None
            assert record.live_trading == "Not Authorized"
            assert record.paper_trading == "Discovered"

    def test_fabricated_eligibility_is_refused(self):
        catalogs, platform = _discover_all()
        report = build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
        with pytest.raises(Exception):
            report.model_copy(update={"eligibility_granted": True}) \
                .validate_semantics()

    def test_render_contains_venues_canonicals_and_fail_closed_section(self):
        catalogs, platform = _discover_all()
        markdown = render_catalog_report_markdown(
            build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
        )
        for broker_id in FACTORIES:
            assert f"`{broker_id}`" in markdown
        for symbol in ("BTC/USDT", "BTC/USD", "ETH/USDT", "EUR/USD", "XAU/USD"):
            assert f"`{symbol}`" in markdown
        assert "Fail-closed discovery behaviors" in markdown
        assert "LIVE TRADING IS NOT AUTHORIZED" in markdown
        assert "Known limitations" in markdown

    def test_rendering_is_deterministic(self):
        first = render_catalog_report_markdown(
            build_catalog_report(*_discover_all(), at=FIXED_AT)
        )
        second = render_catalog_report_markdown(
            build_catalog_report(*_discover_all(), at=FIXED_AT)
        )
        assert first == second

    def test_committed_artifact_matches_regeneration(self):
        regenerated = render_catalog_report_markdown(
            build_catalog_report(*_discover_all(), at=FIXED_AT)
        )
        committed = CATALOG_PATH.read_text(encoding="utf-8")
        assert committed == regenerated
