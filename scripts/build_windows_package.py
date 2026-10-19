#!/usr/bin/env python3
"""Deterministic Windows package builder (Stage E, Part 8 E1/E3).

Builds the Windows zip package from the CURRENT commit of the working
tree's branch:

    <package>/                          (ai-trading-lab-data-engine-windows-v<version>/)
    ├── install.ps1 / run-tests.ps1 / run-paper.ps1   (from deploy/windows/)
    ├── README-WINDOWS-PACKAGE.md                     (from deploy/windows/)
    ├── requirements-windows.txt                      (uv export --frozen --no-dev --no-emit-project, hash-pinned)
    ├── dist/<engine wheel>                           (uv build)
    ├── source/                                       (git archive of HEAD — full repo)
    └── SHA256SUMS.txt                                (sha256 of every packaged file)

Determinism: file mtimes are normalized to the commit timestamp and
zip entries are written in sorted order, so two builds from the same
commit produce byte-identical zips (given identical wheel builds).

Fail-closed: refuses to run on a dirty tree, missing uv, failed
export/build, or a package that misses any expected component.

Usage:
    python scripts/build_windows_package.py [--out DIR]

Output: <out>/ai-trading-lab-data-engine-windows-v<version>.zip
(default out: build/ inside the repo, which is gitignored).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_COMPONENTS = (
    "install.ps1",
    "run-tests.ps1",
    "run-paper.ps1",
    "README-WINDOWS-PACKAGE.md",
)


def sh(cmd: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        raise SystemExit(f"[BUILD-FAILED] command failed: {' '.join(cmd)}")
    return proc.stdout


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default=str(REPO_ROOT / "build"), help="output directory"
    )
    args = parser.parse_args()

    # -- fail-closed preconditions -----------------------------------------
    if sh(["git", "status", "--porcelain"], cwd=REPO_ROOT).strip():
        raise SystemExit(
            "[BUILD-FAILED] working tree is dirty — commit first "
            "(packages are built from exact commits for provenance)."
        )
    head = sh(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).strip()
    commit_ts = int(
        sh(
            ["git", "log", "-1", "--format=%ct", "HEAD"],
            cwd=REPO_ROOT,
        ).strip()
    )
    commit_dt = datetime.fromtimestamp(commit_ts, tz=timezone.utc)

    for tool in ("uv",):
        if shutil.which(tool) is None:
            raise SystemExit(f"[BUILD-FAILED] {tool} not found on PATH")

    for comp in EXPECTED_COMPONENTS:
        if not (REPO_ROOT / "deploy" / "windows" / comp).is_file():
            raise SystemExit(f"[BUILD-FAILED] missing deploy/windows/{comp}")

    version = sh(
        ["uv", "run", "python", "-c",
         "import tomllib,sys;"
         "print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"],
        cwd=REPO_ROOT,
    ).strip()
    pkg_name = f"ai-trading-lab-data-engine-windows-v{version}"

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{pkg_name}.zip"

    with tempfile.TemporaryDirectory(prefix="winpkg-") as tmp:
        stage = Path(tmp) / pkg_name
        stage.mkdir()

        # 1. source tree (git archive of HEAD — exact commit provenance)
        source = stage / "source"
        source.mkdir()
        archive = Path(tmp) / "repo.tar"
        with open(archive, "wb") as fh:
            proc = subprocess.run(
                ["git", "archive", "--format=tar", "HEAD"],
                cwd=REPO_ROOT, stdout=fh, check=True,
            )  # noqa: F841 (check raises on failure)
        sh(["tar", "-xf", str(archive), "-C", str(source)])

        # 2. locked requirements (hash-pinned, frozen to uv.lock)
        sh(
            [
                "uv", "export", "--frozen", "--no-dev", "--no-emit-project",
                "--format", "requirements-txt",
                "-o", str(stage / "requirements-windows.txt"),
            ],
            cwd=REPO_ROOT,
        )

        # 3. engine wheel (fresh build from the same commit)
        sh(["uv", "build", "--wheel"], cwd=REPO_ROOT)
        dist_src = REPO_ROOT / "dist"
        wheels = sorted(dist_src.glob("*.whl"))
        if not wheels:
            raise SystemExit("[BUILD-FAILED] uv build produced no wheel")
        (stage / "dist").mkdir()
        for whl in wheels:
            shutil.copy2(whl, stage / "dist" / whl.name)

        # 4. deploy/windows components
        for comp in EXPECTED_COMPONENTS:
            shutil.copy2(
                REPO_ROOT / "deploy" / "windows" / comp,
                stage / comp,
            )

        # 5. SHA256SUMS.txt over every packaged file (sorted, relative)
        entries: list[tuple[str, str]] = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                rel = path.relative_to(stage).as_posix()
                entries.append((rel, sha256_file(path)))
        sums = "\n".join(f"{digest}  {rel}" for rel, digest in entries) + "\n"
        (stage / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")

        # 6. deterministic zip: sorted entries, normalized mtimes
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(stage).as_posix()
                    info = zipfile.ZipInfo(
                        f"{pkg_name}/{rel}",
                        date_time=commit_dt.timetuple()[:6],
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o644 << 16
                    with open(path, "rb") as fh:
                        zf.writestr(info, fh.read())

    digest = sha256_file(zip_path)
    print(f"[BUILD-OK] {zip_path}")
    print(f"[BUILD-OK] commit={head} version={version}")
    print(f"[BUILD-OK] package sha256={digest}")
    print(f"[BUILD-OK] package size={zip_path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
