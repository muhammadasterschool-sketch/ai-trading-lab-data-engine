"""Reconstruction — package-version consistency pin (mission section 6).

Batch 18 recorded the pyproject/uv-lock 0.1.0 vs
``data_engine.__version__`` 0.3.0 build-provenance mismatch as an
honest LOW finding, deferred to operator review. This reconstruction
aligns the package version to 0.3.0 (the code's own self-reported
version) and pins the three-way consistency so the mismatch cannot
silently return.

Category note (documented, NOT treated as a defect):
``MASTER_DOCUMENTATION_INDEX.md`` carries its own documentation-series
version (v2.28.0 at the reconstruction base) — a deliberately separate
version line for the document corpus, unrelated to the package
version. The three numbers were never one version domain.
"""

import tomllib
from pathlib import Path

from data_engine import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    data = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return data["project"]["version"]


def _uvlock_root_version() -> str:
    data = tomllib.loads(
        (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    )
    for package in data.get("package", []):
        if package.get("name") == "ai-trading-lab-data-engine":
            return package["version"]
    raise AssertionError("root package not found in uv.lock")


def test_package_version_is_single_sourced():
    assert _pyproject_version() == __version__


def test_lockfile_root_version_matches_package_version():
    assert _uvlock_root_version() == __version__


def test_documentation_index_remains_a_separate_series():
    idx = REPO_ROOT / "MASTER_DOCUMENTATION_INDEX.md"
    assert idx.is_file(), (
        "the documentation SSOT index must stay present at the repo root"
    )
    head = idx.read_text(encoding="utf-8")[:4000]
    assert "version" in head.lower()
