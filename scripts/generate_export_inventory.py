#!/usr/bin/env python3
"""Derived-export inventory manifest generator (reconstruction D-1).

Closes the verified G-01 gap: every file under ``data/exports/`` is a
DERIVED artifact (a projection of ingested platform state rendered by
``scripts/platform_csv_ingest.py``), yet none of them appeared in any
manifest or DatasetState inventory.

This script builds and maintains the missing inventory:

    uv run python scripts/generate_export_inventory.py          # write/refresh
    uv run python scripts/generate_export_inventory.py --check  # verify only

``--check`` recomputes the inventory and exits 1 on ANY drift (missing
entry, stale SHA-256, wrong size) — deterministic, offline, fail-closed.

Honest classification rules (D-1):
  - every export entry is ``classification: "DERIVED"``;
  - ``dataset_state`` is intentionally ``null``: the DatasetState enum
    (``data_engine.prediction.datasets``) has no DERIVED member because
    exports are projections, not independently classified datasets;
  - exports INHERIT the provenance of their source datasets (currently
    SYNTHETIC dailies + REAL_UNVERIFIED/INVALID masters) — they never
    upgrade it: REAL_VERIFIED remains unreachable by construction;
  - the source data files themselves are never touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXPORTS = REPO / "data" / "exports"
OUT = REPO / "data" / "manifests" / "exports" / "export_inventory.json"

WORKBOOK_NAME = "ai_trading_lab_workbook.xlsx"
SNAPSHOT_NAME = "dashboard_snapshot.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _generator_for(rel: str) -> str:
    """Attribution of the generating code path (fail-closed: unknown
    generators are labelled honestly instead of guessed)."""
    if rel.startswith("csv/") and rel.endswith(".csv"):
        return (
            "scripts/platform_csv_ingest.py "
            "(data_engine.platform.WorkbookExporter.export_csv)"
        )
    if rel == WORKBOOK_NAME:
        return (
            "scripts/platform_csv_ingest.py "
            "(data_engine.platform.WorkbookExporter.export_xlsx)"
        )
    if rel == SNAPSHOT_NAME:
        return (
            "scripts/platform_csv_ingest.py "
            "(data_engine.platform.dashboard build_snapshot)"
        )
    return "UNIDENTIFIED GENERATOR — provenance of this file's creation process is not documented in the repository"


def build_inventory() -> dict:
    if not EXPORTS.is_dir():
        raise SystemExit(f"FATAL: {EXPORTS} does not exist")
    files = sorted(
        p for p in EXPORTS.rglob("*") if p.is_file()
    )
    if not files:
        raise SystemExit(f"FATAL: {EXPORTS} contains no files")
    exports = []
    for p in files:
        rel = p.relative_to(EXPORTS).as_posix()
        exports.append(
            {
                "path": rel,
                "sha256": _sha256_file(p),
                "bytes": p.stat().st_size,
                "classification": "DERIVED",
                "dataset_state": None,
                "generator": _generator_for(rel),
            }
        )
    return {
        "kind": "export_inventory",
        "generated_by": "scripts/generate_export_inventory.py",
        "classification": "DERIVED",
        "provenance_status": (
            "DERIVED exports inherit the unverified provenance of their "
            "source datasets; no independent classification is claimed; "
            "REAL_VERIFIED is unreachable by construction"
        ),
        "derived_from": {
            "raw_dailies_summary": "data/manifests/import_summary.json",
            "master_import_summary": (
                "data/manifests/master/master_import_summary.json"
            ),
            "generator_script": "scripts/platform_csv_ingest.py",
        },
        "note": (
            "DatasetState (data_engine.prediction.datasets) has no DERIVED "
            "member: exports are projections of ingested state, not "
            "independently classified datasets — dataset_state is "
            "intentionally null per entry"
        ),
        "totals": {"files": len(exports)},
        "exports": exports,
    }


def main(argv: list[str] | None = None) -> int:
    check_only = "--check" in (argv or sys.argv[1:])
    fresh = build_inventory()
    if check_only:
        if not OUT.is_file():
            print(f"CHECK FAIL: {OUT} missing")
            return 1
        current = json.loads(OUT.read_text(encoding="utf-8"))
        if current != fresh:
            print("CHECK FAIL: export inventory drifted from reality "
                  "(re-run without --check to refresh)")
            return 1
        print(f"CHECK PASS: {len(fresh['exports'])} exports verified")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(fresh, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"export inventory -> {OUT} ({len(fresh['exports'])} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
