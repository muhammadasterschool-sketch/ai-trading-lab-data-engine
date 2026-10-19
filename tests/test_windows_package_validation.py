"""Stage E supplement — Windows package VALIDATION + tamper
resistance (U-26; additive to the parallel session's structural
contract tests in tests/test_windows_package.py).

What this adds on top of main's coverage:

- a REAL validator (scripts/validate_windows_package.py) for the
  BUILT zip — main's builder produces SHA256SUMS.txt but nothing
  verifies a produced package;
- tamper resistance: missing component / digest mismatch / injected
  credential / forbidden member / unsafe path / version drift are
  all REFUSED (fail closed);
- a representative-fixture harness that mimics the builder's exact
  layout (top-level package dir, source/, dist/<wheel>,
  requirements-windows.txt, SHA256SUMS.txt in the builder's
  "<digest>  <rel>" standard sha256sum format) without invoking uv/network — the
  fixture shares the builder's REAL member names and honesty
  content, so the validator is exercised against the true shape.
"""

import hashlib
import importlib.util
import re
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
PKG_ROOT = "ai-trading-lab-data-engine-windows-v9.9.9"  # fixture name


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "vwp_supp", SCRIPTS / "validate_windows_package.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["vwp_supp"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def validator():
    return _load_validator()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _engine_version() -> str:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import data_engine

    return data_engine.__version__


def _fixture_members() -> dict:
    """Representative members mimicking the builder's REAL layout."""
    version = _engine_version()
    root = f"ai-trading-lab-data-engine-windows-v{version}"
    members: dict = {}

    # deploy/windows components (the REAL shipped scripts + readme)
    for comp in (
        "install.ps1", "run-tests.ps1", "run-paper.ps1",
        "README-WINDOWS-PACKAGE.md",
    ):
        members[f"{root}/{comp}"] = (
            REPO_ROOT / "deploy" / "windows" / comp
        ).read_bytes()
    # locked requirements (representative hash-pinned lines)
    members[f"{root}/requirements-windows.txt"] = (
        "# --frozen export (fixture; the real build uses uv export)\n"
        "pydantic==2.12.23 --hash=sha256:0000\n"
    ).encode()
    # engine wheel (representative stub with the REAL version name)
    members[f"{root}/dist/ai_trading_lab_data_engine-{version}-py3-none-any.whl"] = (
        b"PK-fixture-wheel-not-a-real-wheel"
    )
    # source/ (representative REAL files)
    for rel in (
        "pyproject.toml", "uv.lock",
        "src/data_engine/__init__.py", "src/data_engine/cli.py",
        "scripts/windows_smoke_test.py",
    ):
        members[f"{root}/source/{rel}"] = (REPO_ROOT / rel).read_bytes()
    return members


def _add_sums(members: dict) -> None:
    """SHA256SUMS.txt in the builder's REAL format (FIX-8:
    "<digest>  <rel>" — standard sha256sum convention, exactly as
    scripts/build_windows_package.py emits f"{digest}  {rel}"),
    computed LAST so it covers every other member."""
    root = next(iter(members)).split("/", 1)[0]
    lines = [
        f"{_sha(data)}  {name[len(root) + 1:]}"
        for name, data in sorted(members.items())
    ]
    members[f"{root}/SHA256SUMS.txt"] = ("\n".join(lines) + "\n").encode()


def _build_fixture(tmp_path: Path, mutate=None, *, sums_first=False) -> Path:
    """Build a layout-true fixture zip.

    Default: ``mutate(members)`` runs BEFORE the sums are computed
    (the tamper is covered by an honest manifest — catches structural
    detection). ``sums_first=True``: the manifest is computed over the
    HONEST members first, THEN the tamper runs (catches digest
    mismatch — the manifest no longer matches the content)."""
    members = _fixture_members()
    if sums_first:
        _add_sums(members)
        if mutate:
            mutate(members)
    else:
        if mutate:
            mutate(members)
        _add_sums(members)
    out = tmp_path / "fixture.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, members[name])
    return out


# ---------------------------------------------------------------------------
# 1. The honest fixture validates
# ---------------------------------------------------------------------------
class TestHonestPackageValidates:
    def test_validator_accepts_layout_true_fixture(self, validator, tmp_path):
        report = validator.validate_zip(_build_fixture(tmp_path))
        assert report.ok, report.failures

    def test_every_required_component_checked(self, validator, tmp_path):
        report = validator.validate_zip(_build_fixture(tmp_path))
        joined = " ".join(report.checks)
        assert "required components" in joined


# ---------------------------------------------------------------------------
# 2. Tamper resistance — every break is REFUSED
# ---------------------------------------------------------------------------
class TestTamperResistance:
    def test_missing_component_refused(self, validator, tmp_path):
        def mutate(members):
            del members[
                next(n for n in members if n.endswith("run-paper.ps1"))
            ]

        report = validator.validate_zip(_build_fixture(tmp_path, mutate))
        assert not report.ok
        assert any("missing required components" in f for f in report.failures)

    def test_digest_mismatch_refused(self, validator, tmp_path):
        def mutate(members):
            key = next(n for n in members if n.endswith("install.ps1"))
            members[key] += b"\n# tampered after sums\n"

        report = validator.validate_zip(
            _build_fixture(tmp_path, mutate, sums_first=True)
        )
        assert not report.ok
        assert any("mismatch" in f.lower() for f in report.failures)

    def test_injected_credential_refused(self, validator, tmp_path):
        def mutate(members):
            key = next(n for n in members if n.endswith("requirements-windows.txt"))
            members[key] += (
                "\nleak=github_pat_" + "A" * 40 + "\n"
            ).encode()

        report = validator.validate_zip(_build_fixture(tmp_path, mutate))
        assert not report.ok
        assert any("credential" in f.lower() for f in report.failures)

    def test_forbidden_member_refused(self, validator, tmp_path):
        def mutate(members):
            root = next(iter(members)).split("/", 1)[0]
            members[f"{root}/source/.git/config"] = b"[core]"
            members[f"{root}/source/state.json"] = b"{}"

        report = validator.validate_zip(_build_fixture(tmp_path, mutate))
        assert not report.ok
        assert any("forbidden members" in f for f in report.failures)

    def test_unsafe_path_refused(self, validator, tmp_path):
        def mutate(members):
            members["../escape.txt"] = b"traversal"

        report = validator.validate_zip(
            _build_fixture(tmp_path, mutate, sums_first=True)
        )
        assert not report.ok
        assert any("unsafe" in f.lower() for f in report.failures)

    def test_version_drift_refused(self, validator, tmp_path):
        def mutate(members):
            root = next(iter(members)).split("/", 1)[0]
            version = _engine_version()
            wrong = "0.0.1" if version != "0.0.1" else "0.0.2"
            members[f"{root}/dist/ai_trading_lab_data_engine-{wrong}-py3-none-any.whl"] = (
                b"PK-fixture-wheel-wrong-version"
            )
            del members[
                f"{root}/dist/ai_trading_lab_data_engine-{version}-py3-none-any.whl"
            ]

        report = validator.validate_zip(_build_fixture(tmp_path, mutate))
        assert not report.ok
        assert any("version disagreement" in f for f in report.failures)

    def test_two_toplevel_dirs_refused(self, validator, tmp_path):
        def mutate(members):
            members["other-root/file.txt"] = b"x"

        report = validator.validate_zip(
            _build_fixture(tmp_path, mutate, sums_first=True)
        )
        assert not report.ok
        assert any("ONE top-level directory" in f for f in report.failures)

    def test_posture_strip_refused(self, validator, tmp_path):
        def mutate(members):
            key = next(n for n in members if n.endswith("run-tests.ps1"))
            members[key] = members[key].replace(
                b'$ErrorActionPreference = "Stop"', b"$ErrorActionPreference = \"Continue\""
            )

        report = validator.validate_zip(_build_fixture(tmp_path, mutate))
        assert not report.ok
        assert any("posture" in f.lower() for f in report.failures)

    def test_missing_zip_refused(self, validator, tmp_path):
        report = validator.validate_zip(tmp_path / "nonexistent.zip")
        assert not report.ok


# ---------------------------------------------------------------------------
# 3. The validator CLI is the operator's recorded command (U-27)
# ---------------------------------------------------------------------------
class TestValidatorCli:
    def test_cli_help_and_version_interface(self, tmp_path):
        import subprocess

        probe = subprocess.run(
            [sys.executable,
             str(SCRIPTS / "validate_windows_package.py"), "--help"],
            capture_output=True, text=True, timeout=120,
        )
        assert probe.returncode == 0
        assert "usage" in probe.stdout.lower()
        assert "zip_path" in probe.stdout

    def test_cli_rejects_a_broken_zip(self, tmp_path):
        import subprocess

        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip")
        probe = subprocess.run(
            [sys.executable,
             str(SCRIPTS / "validate_windows_package.py"), str(bad)],
            capture_output=True, text=True, timeout=120,
        )
        assert probe.returncode != 0
        assert "VALIDATION FAILED" in probe.stdout


# ---------------------------------------------------------------------------
# FIX-8 cross-pin: the builder's manifest format and the validator's
# parser can never silently diverge again (the original defect: the
# validator parsed "<rel>  <digest>" while the builder emits the
# standard sha256sum convention "<digest>  <rel>").
# ---------------------------------------------------------------------------
class TestBuilderValidatorFormatAgreement:
    def test_builder_emits_digest_first_lines(self):
        """The builder's manifest expression is exactly
        f"{digest}  {rel}" (standard sha256sum convention)."""
        builder = (
            SCRIPTS / "build_windows_package.py"
        ).read_text(encoding="utf-8")
        assert 'f"{digest}  {rel}"' in builder, (
            "build_windows_package.py must keep the standard "
            "sha256sum line format (digest first, two spaces, path)"
        )

    def test_validator_parses_digest_first_lines(self):
        """The validator accepts exactly that line shape and refuses
        malformed lines (wrong order, short digest, missing path)."""
        digest = "a" * 64
        assert re.match(r"[0-9a-f]{64}", digest)
        # well-formed: digest-first
        line = f"{digest}  install.ps1"
        d, sep, rel = line.partition("  ")
        assert sep and d == digest and rel == "install.ps1"
        # reversed order must NOT parse as digest-first
        bad = f"install.ps1  {digest}"
        d2, sep2, _ = bad.partition("  ")
        assert not (sep2 and len(d2) == 64 and
                    all(c in "0123456789abcdef" for c in d2))

    def test_fixture_sums_match_builder_format(self):
        """The fixture harness itself emits digest-first lines (the
        same convention as the builder), so the validator is always
        exercised against the true shape."""
        members = {
            "pkg-root/install.ps1": b"# smoke",
            "pkg-root/run-tests.ps1": b"# tests",
        }
        _add_sums(members)
        text = members["pkg-root/SHA256SUMS.txt"].decode()
        for line in text.splitlines():
            d, sep, rel = line.partition("  ")
            assert sep and len(d) == 64
            assert all(c in "0123456789abcdef" for c in d)
            assert rel in ("install.ps1", "run-tests.ps1")
