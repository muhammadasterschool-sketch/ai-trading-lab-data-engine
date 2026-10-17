"""Reconstruction D-1/D-2 — data provenance inventory + fail-closed pins.

Covers the verified G-01 gap (derived exports missing from any
manifest/DatasetState inventory) and pins the fail-closed data
provenance posture against silent regression:

- every file under ``data/exports/`` MUST be covered by
  ``data/manifests/exports/export_inventory.json`` with a matching
  live SHA-256/size, classification DERIVED and honest generator
  attribution (D-1);
- the master/raw import summaries MUST stay internally consistent
  (contradictory manifests are a fail-closed defect, D-2);
- NO dataset anywhere under ``data/manifests/`` may claim
  ``REAL_VERIFIED`` — promotion requires documented source approval
  that does not exist (fail-closed promotion guard, D-1/D-2);
- the Metals_Master.csv dataset MUST remain INVALID and the
  provenance-status statement MUST keep declaring source approval
  UNKNOWN (classification drift guard).
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS = REPO_ROOT / "data" / "exports"
INVENTORY = REPO_ROOT / "data" / "manifests" / "exports" / "export_inventory.json"
MANIFESTS = REPO_ROOT / "data" / "manifests"

ALLOWED_STATES = {
    "SYNTHETIC",
    "REAL_UNVERIFIED",
    "REAL_VERIFIED",
    "INSUFFICIENT",
    "INVALID",
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _live_export_files() -> set[str]:
    return {
        p.relative_to(EXPORTS).as_posix()
        for p in EXPORTS.rglob("*")
        if p.is_file()
    }


# ---------------------------------------------------------------------------
# D-1 — derived-export inventory coverage
# ---------------------------------------------------------------------------


class TestExportInventoryCoverage:
    @pytest.fixture(scope="class")
    def inventory(self) -> dict:
        assert INVENTORY.is_file(), (
            "export inventory manifest missing — run "
            "scripts/generate_export_inventory.py"
        )
        return _load(INVENTORY)

    def test_every_export_file_is_inventoried(self, inventory):
        listed = {e["path"] for e in inventory["exports"]}
        assert listed == _live_export_files(), (
            "data/exports/ and the inventory disagree — a derived export "
            "would silently escape manifest coverage (G-01 regression)"
        )

    def test_no_phantom_inventory_entries(self, inventory):
        listed = {e["path"] for e in inventory["exports"]}
        assert not (listed - _live_export_files())

    def test_each_entry_sha256_and_size_match_live_files(self, inventory):
        for entry in inventory["exports"]:
            p = EXPORTS / entry["path"]
            assert p.is_file()
            import hashlib

            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            assert entry["sha256"] == h.hexdigest(), entry["path"]
            assert entry["bytes"] == p.stat().st_size, entry["path"]

    def test_every_entry_is_derived_with_null_dataset_state(
        self, inventory
    ):
        for entry in inventory["exports"]:
            assert entry["classification"] == "DERIVED", entry["path"]
            assert entry["dataset_state"] is None, entry["path"]
            assert entry["generator"], entry["path"]

    def test_generators_are_attributed_not_invented(self, inventory):
        """Generator attribution must be honest: known projections name
        the committed generator; anything else must say so explicitly."""
        for entry in inventory["exports"]:
            gen = entry["generator"]
            assert (
                "platform_csv_ingest.py" in gen
                or "UNIDENTIFIED GENERATOR" in gen
            ), entry["path"]

    def test_provenance_status_keeps_real_verified_unreachable(
        self, inventory
    ):
        status = inventory["provenance_status"]
        assert "DERIVED" in status
        assert "REAL_VERIFIED" in status and "unreachable" in status


# ---------------------------------------------------------------------------
# D-2 — manifest consistency + fail-closed classification pins
# ---------------------------------------------------------------------------


class TestManifestConsistencyFailClosed:
    @pytest.fixture(scope="class")
    def master_summary(self) -> dict:
        return _load(MANIFESTS / "master" / "master_import_summary.json")

    @pytest.fixture(scope="class")
    def raw_summary(self) -> dict:
        return _load(MANIFESTS / "import_summary.json")

    def test_master_totals_match_dataset_rows(self, master_summary):
        ds = master_summary["datasets"]
        totals = master_summary["totals"]
        assert totals["files"] == len(ds)
        assert totals["rows"] == sum(d["row_count"] for d in ds)
        assert totals["real_unverified"] == sum(
            1 for d in ds if d["data_state"] == "REAL_UNVERIFIED"
        )
        assert totals["invalid"] == sum(
            1 for d in ds if d["data_state"] == "INVALID"
        )
        assert totals["real_verified"] == sum(
            1 for d in ds if d["data_state"] == "REAL_VERIFIED"
        )
        assert totals["synthetic"] == sum(
            1 for d in ds if d["data_state"] == "SYNTHETIC"
        )

    def test_master_states_are_from_the_closed_vocabulary(
        self, master_summary
    ):
        for d in master_summary["datasets"]:
            assert d["data_state"] in ALLOWED_STATES, d["file_name"]

    def test_metals_master_stays_invalid(self, master_summary):
        metals = [
            d for d in master_summary["datasets"]
            if d["file_name"] == "Metals_Master.csv"
        ]
        assert len(metals) == 1
        assert metals[0]["data_state"] == "INVALID"

    def test_source_approval_stays_unknown(self, master_summary):
        """Fail-closed approval pin: provenance must keep declaring that
        source approval is UNKNOWN — silently implying approval would be
        a fabrication."""
        status = master_summary["provenance_status"]
        assert "UNKNOWN" in status
        assert "REAL_VERIFIED is unreachable" in status

    def test_raw_dailies_summary_consistent(self, raw_summary):
        files = raw_summary["files"]
        assert len(files) == 4
        for f in files:
            assert f["data_state"] == "SYNTHETIC", f["file_name"]
        assert raw_summary["total_rows"] == sum(
            f["row_count"] for f in files
        )
        assert raw_summary["total_instruments"] == sum(
            f["instrument_count"] for f in files
        )

    def test_no_dataset_anywhere_claims_real_verified(self):
        """Recursive promotion guard over EVERY manifest JSON under
        data/manifests/ — a single REAL_VERIFIED claim without the
        approval chain is a fail-closed violation."""
        offenders: list[str] = []

        def walk(node, where: str) -> None:
            if isinstance(node, dict):
                for k, v in node.items():
                    if k in ("data_state", "classification") and isinstance(
                        v, str
                    ):
                        if v == "REAL_VERIFIED" and k == "data_state":
                            offenders.append(f"{where}::{k}={v}")
                    walk(v, where)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    walk(item, where)

        for p in sorted(MANIFESTS.rglob("*.json")):
            walk(_load(p), p.relative_to(REPO_ROOT).as_posix())
        assert not offenders, (
            f"REAL_VERIFIED claimed without approval chain: {offenders}"
        )
