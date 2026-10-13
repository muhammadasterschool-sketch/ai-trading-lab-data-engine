#!/usr/bin/env python3
"""Generate the two Batch 15 broker catalog artifacts (deterministic).

Regenerates, BYTE-IDENTICALLY on every run:

- ``docs/reports/BROKER_CAPABILITY_MATRIX.md``   (item C-3)
- ``docs/reports/INSTRUMENT_CATALOG_REPORT.md``  (item C-2)

from the SEVEN deterministic mock venues: every adapter is constructed,
connected with a MOCK credential (never printed), discovered through
the fail-closed discovery path against the default capability
registry, and synced into a FRESH platform InstrumentRegistry. The
discovery timestamp is a FIXED constant (audit provenance only — never
an identity input, INV-01) so regeneration is reproducible.

NO network. NO real credentials. NO real orders. LIVE TRADING IS NOT
AUTHORIZED.

Usage (from the repository root)::

    uv run python scripts/generate_broker_catalog_artifacts.py
"""

from datetime import datetime, UTC
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Fixed discovery timestamp (audit provenance ONLY — INV-01: never an
#: identity input). Deterministic regeneration requires a constant.
FIXED_AT = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)

ACCOUNT = "artifact-generator"
MOCK_SECRET = "mock-credential-material-never-printed"


def fixed_clock() -> datetime:
    return FIXED_AT


def main() -> int:
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

    factories = {
        "binance-mock": BinanceSpotMockAdapter,
        "bitget-mock": BitgetSpotMockAdapter,
        "bybit-mock": BybitV5MockAdapter,
        "exness-mock": ExnessMT5MockAdapter,
        "mt5-mock": MT5StyleMockAdapter,
        "paper-mock": PaperBrokerAdapter,
        "xm-mock": XMMT5MockAdapter,
    }

    registry = default_registry()
    matrix = build_capability_matrix(registry)
    matrix_md = render_capability_matrix_markdown(matrix)
    matrix_path = REPO / "docs" / "reports" / "BROKER_CAPABILITY_MATRIX.md"
    matrix_path.write_text(matrix_md, encoding="utf-8")
    print(f"wrote {matrix_path.relative_to(REPO)} ({matrix.venue_count} venues)")

    platform = InstrumentRegistry()
    catalogs = []
    for broker_id in sorted(factories):
        adapter = factories[broker_id](fixed_clock)
        adapter.connect(BrokerCredential(ACCOUNT, MOCK_SECRET))
        catalog = discover_instruments(adapter, at=FIXED_AT, registry=registry)
        report = sync_catalog_to_platform_registry(catalog, platform, at=FIXED_AT)
        catalogs.append(catalog)
        print(
            f"  {broker_id}: {len(catalog)} instruments, "
            f"{report.registered} registered / {report.duplicates} merged"
        )

    catalog_report = build_catalog_report(tuple(catalogs), platform, at=FIXED_AT)
    catalog_md = render_catalog_report_markdown(catalog_report)
    catalog_path = REPO / "docs" / "reports" / "INSTRUMENT_CATALOG_REPORT.md"
    catalog_path.write_text(catalog_md, encoding="utf-8")
    print(
        f"wrote {catalog_path.relative_to(REPO)} "
        f"({catalog_report.venue_count} venues, "
        f"{catalog_report.canonical_count} canonical identities)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
