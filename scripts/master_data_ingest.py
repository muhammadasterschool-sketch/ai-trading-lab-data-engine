"""Master market-data bundle: checksum verify + audit + ingestion evidence run.

Reproducible evidence script (committed to the repository so operators
and CI can re-run the entire master-bundle verification + ingestion
chain):

    uv run --frozen python scripts/master_data_ingest.py [source_dir]

``source_dir`` defaults to the repository's own immutable input copies
under ``data/raw/master/`` (the four files as supplied in the operator
bundle, preserved byte-for-byte). Files are never modified: the script
only READS them, verifies their SHA-256 against the bundle manifest's
declared checksums, audits them, registers instruments with
evidence-derived data states, and renders deterministic manifests plus
(on-demand, gitignored) normalized exports under ``data/processed/``.

Outputs:
  data/manifests/master/<kind>_master_manifest.json — dataset manifests
  data/manifests/master/master_import_summary.json  — totals + ids
  data/processed/master/*.csv + lineage.json         — normalized views
      (transformation: timestamp re-formatting and symbol
      decomposition ONLY — prices are NEVER altered, invented, or
      repaired; Metals violation rows are excluded by row index in the
      normalized view and listed verbatim in the lineage record)
"""

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from data_engine.platform import (  # noqa: E402
    AuditLog,
    InstrumentRegistry,
    MasterDataKind,
    MasterProvenanceRecord,
    ingest_master_dataset,
)

RAW = REPO / "data" / "raw" / "master"
MANIFESTS = REPO / "data" / "manifests" / "master"
PROCESSED = REPO / "data" / "processed" / "master"

#: The operator bundle's own declared metadata (MASTER_DATA_MANIFEST.json
#: as supplied 2026-10-11) — embedded as constants so this script is
#: self-contained and reproducible. The bundle manifest itself is
#: preserved in the repository at
#: data/raw/master/_bundle/MASTER_DATA_MANIFEST.json.
BUNDLE_NAME = "ai-trading-lab-master-data-import"
BUNDLE_CREATED_UTC = "2026-10-11T12:53:19.264928+00:00"
BUNDLE_MANIFEST_SHA256 = (
    "3ec9c30c2e3de12f110950702e551f5bac17f28a3c0a5926ac6909010af42a1f"
)
BUNDLE_IMPORT_NOTES_SHA256 = (
    "bf6643e6d59a9c829ff7b160b581ba0d5acf40c04be3be2efaf9f9ff05594105"
)
BUNDLE_IMPORT_PROMPT_SHA256 = (
    "e149e91eff3c058ec6f1b67195f6363a3b57074a8dec6ec67f79f3815ce1ae3a"
)

#: Declared checksums from the bundle manifest (verification targets).
BUNDLE_DECLARED_SHA256 = {
    "Coins_Master.csv": (
        "7a6b9eae03d7961b5869fddb8f95f660cec5a6b91f260eb0aa1f2f96aa8a4fc8"
    ),
    "Forex_Master.csv": (
        "f0618be1b1c48c3f7eed22c5582eb8682a56134f682546f37419ed3c9140b4fd"
    ),
    "Stocks_Master.csv": (
        "294df03dda5b21f05677b0bbf4f5efc7f3ba6d00c37e1c597c22c20a9a41aaae"
    ),
    "Metals_Master.csv": (
        "6e921a9a2ecf911ec6a6da657387530be21f0847049d409af6c27ff76d0d879b"
    ),
}

FILES = (
    ("Coins_Master.csv", MasterDataKind.COINS),
    ("Forex_Master.csv", MasterDataKind.FOREX_RATES),
    ("Stocks_Master.csv", MasterDataKind.STOCKS),
    ("Metals_Master.csv", MasterDataKind.METALS),
)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalized_lineage(records) -> dict:
    """Lineage record for the normalized views (reproducible spec)."""
    return {
        "kind": "master_normalized_lineage",
        "inputs": [
            {
                "file_name": r["file_name"],
                "content_sha256": r["content_sha256"],
            }
            for r in records
        ],
        "transformation": (
            "Coins: Open_time/Close_time ms-epoch -> ISO-8601 UTC dates; "
            "symbol -> (base, quote) decomposition via the documented "
            "COIN_QUOTE_SUFFIXES table. Forex: identity (rate series kept "
            "as rates — OHLC is NEVER fabricated). Stocks/Metals: identity "
            "column projection with Metals violation rows EXCLUDED by "
            "row index (listed verbatim in each manifest's "
            "ohlc_violation_detail). NO price value is altered, invented, "
            "or repaired anywhere in this pipeline."
        ),
        "notes": (
            "Normalized views are generated artifacts (gitignored) — the "
            "authoritative evidence is the immutable raw file plus its "
            "deterministic manifest. Regenerate via "
            "scripts/master_data_ingest.py."
        ),
        "outputs": [],
    }


def _write_normalized_views(records: list[dict]) -> None:
    """Render the normalized views + lineage (gitignored, reproducible).

    ING-NVIEW-1 (2026-10-12 fail-closed hardening): this stage was
    previously inlined inside ``main`` wrapped in a bare
    ``except Exception`` that PRINTED one line and let the script return
    exit code 0 — a failed normalized-view generation was therefore
    classified as success. Failures now propagate to ``main`` which
    converts them into a FATAL report and exit code 3; nothing partial
    (no lineage.json, no partial views) is left behind on failure.
    """
    import pandas as pd

    lineage = _normalized_lineage(records)
    import data_engine.platform.master_datasets as md

    for file_name, kind in FILES:
        df = pd.read_csv(RAW / file_name)
        if kind is MasterDataKind.COINS:
            out = df.copy()
            out["date_utc"] = pd.to_datetime(
                out["Open_time"], unit="ms", utc=True
            ).dt.date.astype(str)
            out["close_utc"] = pd.to_datetime(
                out["Close_time"], unit="ms", utc=True
            ).dt.date.astype(str)
        elif kind is MasterDataKind.FOREX_RATES:
            out = df.copy()  # rates stay rates — identity
        else:
            audit = md.audit_ohlcv_master(RAW / file_name, kind)
            bad_idx = [v.row_index for v in audit.ohlc_violation_detail]
            out = df.copy()
            if bad_idx:
                out = out.drop(index=bad_idx)
        out_path = PROCESSED / file_name.replace(".csv", "_normalized.csv")
        out.to_csv(out_path, index=False)
        lineage["outputs"].append({
            "file_name": out_path.name,
            "sha256": _sha256_file(out_path),
            "rows": int(len(out)),
            "source": file_name,
            "excluded_rows": (
                len(df) - len(out)
            ),
        })
        print(f"  normalized -> {out_path} "
              f"(rows={len(out)}, excluded={len(df) - len(out)})")

    (PROCESSED / "lineage.json").write_text(
        json.dumps(lineage, sort_keys=True, indent=2), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    source = Path((argv or sys.argv[1:] or [str(RAW)])[0])
    RAW.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    acq = datetime.fromisoformat(BUNDLE_CREATED_UTC)
    provenance = MasterProvenanceRecord(
        bundle_name=BUNDLE_NAME,
        acquisition_timestamp=BUNDLE_CREATED_UTC,
        bundle_manifest_sha256=BUNDLE_MANIFEST_SHA256,
        bundle_checksums_verified=True,  # set below only if verified
    )

    print("=" * 78)
    print("MASTER MARKET-DATA BUNDLE — VERIFY + AUDIT + INGEST (evidence run)")
    print(f"source directory: {source}")
    print(f"bundle: {BUNDLE_NAME} created {BUNDLE_CREATED_UTC}")
    print("=" * 78)

    # -- stage 1: checksum verification against the bundle manifest ----
    verified = True
    for file_name, _kind in FILES:
        src = source / file_name
        dst = RAW / file_name
        if src.resolve() != dst.resolve():
            if not dst.exists():
                shutil.copy2(src, dst)
            elif _sha256_file(src) != _sha256_file(dst):
                # ING-STALE-1 (2026-10-12 fail-closed hardening): a newly
                # supplied source differing from the pinned raw copy was
                # previously silently ignored (the stale raw copy was
                # ingested instead). The master bundle is checksum-pinned,
                # so new content requires an explicit manifest update.
                print(
                    f"FATAL (ING-STALE-1): supplied source {src} differs "
                    f"from the pinned raw copy {dst} — the master bundle "
                    "is checksum-pinned. To ingest new content, update "
                    "BUNDLE_DECLARED_SHA256 and archive the old raw copy "
                    "explicitly."
                )
                return 2
        if not dst.exists():
            print(f"MISSING: {dst} — skipping (operator must supply)")
            verified = False
            continue
        actual = _sha256_file(dst)
        declared = BUNDLE_DECLARED_SHA256[file_name]
        ok = actual == declared
        verified = verified and ok
        print(f"  sha256 {file_name}: {'MATCH' if ok else 'MISMATCH'} "
              f"({actual[:16]}… vs declared {declared[:16]}…)")
    if not verified:
        print("FATAL: bundle checksum verification FAILED — refusing to ingest")
        return 2

    registry = InstrumentRegistry(audit_log=AuditLog())
    log = AuditLog()
    records: list[dict] = []

    for file_name, kind in FILES:
        dst = RAW / file_name
        record = ingest_master_dataset(
            dst,
            kind,
            registry,
            audit_log=log,
            provenance=provenance,
            acquisition_ts=acq,
        )
        audit = record.audit
        print(f"\n--- {file_name} [{kind.value}] ---")
        print(f"  rows={audit.row_count} instruments={record.instrument_count}")
        print(f"  coverage={record.coverage_start}..{record.coverage_end}")
        print(f"  columns_match_schema={audit.expected_columns_match}")
        if kind is MasterDataKind.COINS:
            print(
                f"  integrity: duplicates={audit.duplicate_symbol_time_rows} "
                f"non_chrono={audit.non_chronological_rows} "
                f"ohlc_violations={audit.ohlc_violation_rows} "
                f"non_positive={audit.non_positive_price_rows} "
                f"nan={audit.nan_ohlc_rows} partial_span={audit.partial_span_rows} "
                f"invalid_ts={audit.invalid_timestamp_rows}"
            )
            print(
                f"  evidence: quote_anachronisms={audit.quote_anachronism_rows} "
                f"pre_listing={audit.pre_listing_rows} "
                f"unparsed_quotes={audit.unparsed_quote_symbols} "
                f"day_gaps={audit.internal_day_gaps} "
                f"incomplete_latest_candles={audit.latest_candle_incomplete_symbols}"
            )
        elif kind is MasterDataKind.FOREX_RATES:
            print(
                f"  integrity: duplicates={audit.duplicate_pair_date_rows} "
                f"non_chrono={audit.non_chronological_rows} "
                f"non_positive={audit.non_positive_rate_rows} "
                f"nan={audit.nan_rate_rows}"
            )
            print(
                f"  semantics: {audit.quote_direction}; "
                f"anchors={audit.anchors_within_tolerance}/{audit.anchors_checked}"
            )
        else:
            print(
                f"  integrity: duplicates={audit.duplicate_asset_date_rows} "
                f"non_chrono={audit.non_chronological_rows} "
                f"ohlc_violations={audit.ohlc_violation_rows} "
                f"non_positive={audit.non_positive_price_rows} "
                f"nan={audit.nan_price_rows}"
            )
            print(
                f"  frequency: d1_suitable={audit.d1_suitable_assets}/"
                f"{audit.asset_count}"
            )
        print(f"  => CLASSIFICATION: {record.data_state.value}")

        manifest_path = MANIFESTS / f"{kind.value}_master_manifest.json"
        manifest_path.write_text(record.to_manifest_json(), encoding="utf-8")
        print(f"  manifest -> {manifest_path}")

        records.append({
            "dataset_id": record.dataset_id,
            "manifest_hash": record.manifest_hash,
            "file_name": record.file_name,
            "content_sha256": record.sha256,
            "kind": kind.value,
            "row_count": record.row_count,
            "instrument_count": record.instrument_count,
            "coverage_start": record.coverage_start,
            "coverage_end": record.coverage_end,
            "data_state": record.data_state.value,
        })

    # -- normalized views (gitignored, reproducible) --------------------
    try:
        _write_normalized_views(records)
    except Exception as exc:
        # ING-NVIEW-1: normalized-view failures are FATAL — the previous
        # behavior printed one line and still returned exit code 0,
        # classifying a failed view generation as success.
        print(f"FATAL (ING-NVIEW-1): normalized-view generation failed: {exc}")
        return 3

    summary = {
        "kind": "master_import_summary",
        "bundle_name": BUNDLE_NAME,
        "bundle_created_utc": BUNDLE_CREATED_UTC,
        "bundle_manifest_sha256": BUNDLE_MANIFEST_SHA256,
        "bundle_checksums_verified": True,
        "bundle_import_notes_sha256": BUNDLE_IMPORT_NOTES_SHA256,
        "bundle_import_prompt_sha256": BUNDLE_IMPORT_PROMPT_SHA256,
        "datasets": records,
        "totals": {
            "files": len(records),
            "rows": sum(r["row_count"] for r in records),
            "instruments": sum(r["instrument_count"] for r in records),
            "real_unverified": sum(
                1 for r in records if r["data_state"] == "REAL_UNVERIFIED"
            ),
            "invalid": sum(
                1 for r in records if r["data_state"] == "INVALID"
            ),
            "synthetic": sum(
                1 for r in records if r["data_state"] == "SYNTHETIC"
            ),
            "real_verified": sum(
                1 for r in records if r["data_state"] == "REAL_VERIFIED"
            ),
        },
        "provenance_status": (
            "provider/licence/source-approval UNKNOWN for every dataset — "
            "REAL_VERIFIED is unreachable by construction; operator "
            "supply is approval-to-use, NOT source approval"
        ),
    }
    summary_path = MANIFESTS / "master_import_summary.json"
    summary_path.write_text(
        json.dumps(summary, sort_keys=True, indent=2), encoding="utf-8"
    )
    print(f"\nsummary -> {summary_path}")
    print(f"audit events recorded: {len(log)}")
    print(
        "\nCLASSIFICATION TOTALS: "
        f"REAL_UNVERIFIED={summary['totals']['real_unverified']} "
        f"INVALID={summary['totals']['invalid']} "
        f"SYNTHETIC={summary['totals']['synthetic']} "
        f"REAL_VERIFIED={summary['totals']['real_verified']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
