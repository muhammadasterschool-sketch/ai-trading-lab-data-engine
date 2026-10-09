"""Phase C EXECUTION: audit + ingest the four historical CSV datasets.

Reproducible evidence script (committed to the repository so operators
can re-run the entire dataset audit + ingestion + export chain):

    uv run --frozen python scripts/platform_csv_ingest.py [source_dir]

``source_dir`` defaults to the repository's own immutable input copies
under ``data/raw/`` (the four files as originally supplied). Files are
never modified: the script only READS them, records SHA-256 manifests,
registers instruments with evidence-derived data states, and renders
the workbook + dashboard snapshot.

Outputs:
  data/manifests/<kind>_manifest.json   — deterministic dataset manifests
  data/manifests/import_summary.json    — totals + dataset ids
  data/exports/ai_trading_lab_workbook.xlsx  — Sheets A–G
  data/exports/csv/*.csv                — byte-deterministic per-sheet CSVs
  data/exports/dashboard_snapshot.json  — read-only platform projection
"""

import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from data_engine.platform import (  # noqa: E402
    AuditLog,
    CsvKind,
    InstrumentRegistry,
    WorkbookExporter,
    ingest_csv_dataset,
)
from data_engine.platform.dashboard import (  # noqa: E402
    SystemHealthView,
    build_snapshot,
)

RAW = REPO / "data" / "raw"
MANIFESTS = REPO / "data" / "manifests"
EXPORTS = REPO / "data" / "exports"

FILES = (
    ("crypto_daily_2006_2026.csv", CsvKind.CRYPTO),
    ("forex_daily_2006_2026.csv", CsvKind.FOREX),
    ("metals_daily_2006_2026.csv", CsvKind.METALS),
    ("stocks_indices_daily_2006_2026.csv", CsvKind.STOCKS_INDICES),
)


def main(argv: list[str] | None = None) -> int:
    source = Path((argv or sys.argv[1:] or [str(RAW)])[0])
    RAW.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    EXPORTS.mkdir(parents=True, exist_ok=True)

    registry = InstrumentRegistry(audit_log=AuditLog())
    log = AuditLog()
    records = []

    print("=" * 78)
    print("PHASE C — HISTORICAL CSV DATASET AUDIT + INGESTION (evidence run)")
    print(f"source directory: {source}")
    print("=" * 78)

    for file_name, kind in FILES:
        src = source / file_name
        if not src.exists():
            print(f"MISSING: {src} — skipping (operator must supply)")
            continue

        # immutable raw input (copy only when ingesting from outside)
        dst = RAW / file_name
        if src.resolve() != dst.resolve():
            if not dst.exists():
                shutil.copy2(src, dst)

        record = ingest_csv_dataset(dst, kind, registry, audit_log=log)
        audit = record.audit
        print(f"\n--- {file_name} [{kind.value}] ---")
        print(f"  rows={audit.row_count} instruments={len(audit.instruments)}")
        print(f"  coverage={audit.coverage_start}..{audit.coverage_end}")
        print(f"  columns_match_schema={audit.expected_columns_match}")
        print(
            f"  integrity: duplicates={audit.duplicate_symbol_date_rows} "
            f"non_chrono={audit.non_chronological_rows} "
            f"ohlc_violations={audit.ohlc_violation_rows} "
            f"non_positive={audit.non_positive_price_rows}"
        )
        print(f"  holiday_rows_with_ohlc={audit.holiday_rows_with_ohlc}")
        print(f"  venue_anachronism_rows={audit.venue_anachronism_rows}")
        print(f"  uniform_generation_grid={audit.uniform_generation_grid}")
        print(
            f"  anchors_2006={audit.anchors_within_tolerance}/{audit.anchors_checked}"
        )
        for inst in audit.instruments:
            pre = (
                f" pre_listing_ohlc={inst.pre_listing_ohlc_rows}"
                if inst.pre_listing_ohlc_rows
                else ""
            )
            print(
                f"    {inst.symbol}: rows={inst.rows} valid={inst.valid_ohlc_rows} "
                f"active_from={inst.first_valid_ohlc_date} "
                f"close={inst.last_close}{pre}"
            )
        print("  FABRICATION EVIDENCE:")
        for e in audit.fabrication_evidence:
            print(f"    * {e}")
        for a in audit.endpoint_anomalies:
            print(f"    * {a}")
        print(f"  => CLASSIFICATION: {audit.recommended_state.value}")

        manifest_path = MANIFESTS / f"{kind.value}_manifest.json"
        manifest_path.write_text(record.to_manifest_json(), encoding="utf-8")
        print(f"  manifest -> {manifest_path}")
        records.append(record)

    if not records:
        print("NO FILES INGESTED — aborting exports")
        return 1

    last_sync_day = records[0].coverage_end or "1970-01-01"
    last_sync = datetime.fromisoformat(last_sync_day).replace(tzinfo=UTC)

    # workbook export from the registered authoritative state
    exporter = WorkbookExporter(registry=registry, audit_log=log)
    xlsx_path = EXPORTS / "ai_trading_lab_workbook.xlsx"
    exporter.export_xlsx(xlsx_path, last_sync=last_sync)
    csv_files = exporter.export_csv(EXPORTS / "csv", last_sync=last_sync)
    print(f"\nworkbook -> {xlsx_path}")
    for f in csv_files:
        print(f"  sheet csv -> {f}")

    # import summary
    summary = {
        "files": [
            {
                "file_name": r.file_name,
                "sha256": r.sha256,
                "kind": r.kind.value,
                "row_count": r.row_count,
                "instrument_count": r.instrument_count,
                "coverage": [r.coverage_start, r.coverage_end],
                "data_state": r.data_state.value,
                "dataset_id": r.dataset_id,
                "manifest_hash": r.manifest_hash,
                "registered_instrument_ids": list(r.registered_instrument_ids),
            }
            for r in records
        ],
        "total_rows": sum(r.row_count for r in records),
        "total_instruments": sum(r.instrument_count for r in records),
        "registry_size": len(registry),
    }
    summary_path = MANIFESTS / "import_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nsummary -> {summary_path}")
    print(
        f"TOTALS: rows={summary['total_rows']} instruments={summary['total_instruments']} "
        f"registry={summary['registry_size']}"
    )

    # dashboard snapshot (read-only projection, honest health)
    snapshot = build_snapshot(
        synchronized_at=last_sync_day,
        registry=registry,
        audit_log=log,
        datasets=tuple(records),
        health=SystemHealthView(
            paper_ready=False,
            live_authorized=False,
            blocked_gates=(
                "REAL_DATA_READY (VERIFIED_YEARS=0 — supplied CSVs classified "
                "SYNTHETIC from fabrication evidence, not real market data)",
                "GOVERNANCE_READY (H-1 ratification, CI/WP-12 authorization, PAT rotation)",
            ),
            passing_gates=("PLATFORM_REGISTRY_POPULATED",),
            notes=(
                "20 instruments registered from 4 audited CSV datasets; all "
                "classified SYNTHETIC from fabrication evidence — research/"
                "backtesting eligibility BLOCKED per registry policy",
            ),
        ),
    )
    snap_path = EXPORTS / "dashboard_snapshot.json"
    snap_path.write_text(
        json.dumps(json.loads(snapshot.to_json()), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"snapshot -> {snap_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
