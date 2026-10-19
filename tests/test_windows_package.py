"""Stage E — Windows packaging contract tests (Part 8, E1).

Pins the packaging MACHINERY committed to the repo (audit-then-extend:
the wheel-based Batch 18 spec remains; Stage E adds the zip-package
layer). Verifies, fail-closed:

  1. every mandated package component exists in deploy/windows/;
  2. the deterministic builder refuses a dirty tree (fail-closed
     provenance: packages are built from exact commits);
  3. NO secret material is embedded in any packaging component
     (env-var-only secret handling is the documented contract);
  4. the README documents the mandated sections (state/log layout,
     secrets, backup/restore, safe shutdown, firewall/AV).

The ACTUAL zip build + fresh-venv validation evidence is produced by
scripts/build_windows_package.py and recorded in the Stage E report —
NEVER fabricated here.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DIR = REPO_ROOT / "deploy" / "windows"

COMPONENTS = (
    "install.ps1",
    "run-tests.ps1",
    "run-paper.ps1",
    "README-WINDOWS-PACKAGE.md",
)

SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)api[_-]?key\s*=\s*['\"][A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)secret\s*=\s*['\"][A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)password\s*=\s*['\"][^\s'\"]{8,}"),
    re.compile(r"(?i)BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY"),
)


class TestWindowsPackageComponents:
    def test_all_mandated_components_exist(self):
        for comp in COMPONENTS:
            path = WINDOWS_DIR / comp
            assert path.is_file(), f"missing deploy/windows/{comp}"

    def test_builder_script_exists_and_is_fail_closed(self):
        builder = REPO_ROOT / "scripts" / "build_windows_package.py"
        assert builder.is_file()
        text = builder.read_text(encoding="utf-8")
        # dirty-tree refusal is part of the provenance contract
        assert "working tree is dirty" in text
        # SHA256SUMS generation is part of the E3 contract
        assert "SHA256SUMS" in text

    def test_run_paper_requires_explicit_confirmation(self):
        """run-paper.ps1 must refuse without -Confirm AND without the
        MAC custody env var (fail-closed paper start, Part 2 Rule 3)."""
        ps1 = (WINDOWS_DIR / "run-paper.ps1").read_text(encoding="utf-8")
        assert "-Confirm" in ps1
        assert "RUNTIME_LEDGER_MAC_KEY" in ps1
        assert "explicit confirmation required" in ps1

    def test_install_ps1_installs_locked_hash_pinned_deps(self):
        ps1 = (WINDOWS_DIR / "install.ps1").read_text(encoding="utf-8")
        assert "--require-hashes" in ps1
        assert "requirements-windows.txt" in ps1

    def test_dashboard_is_loopback_only_in_run_paper(self):
        ps1 = (WINDOWS_DIR / "run-paper.ps1").read_text(encoding="utf-8")
        assert "127.0.0.1" in ps1


class TestNoSecretsInPackaging:
    @pytest.mark.parametrize("comp", COMPONENTS)
    def test_no_secret_material_embedded(self, comp):
        text = (WINDOWS_DIR / comp).read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            match = pattern.search(text)
            assert match is None, (
                f"secret-like material in {comp}: "
                f"{match.group(0)[:12]}... (secrets are env-var only)"
            )

    def test_builder_does_not_embed_secrets(self):
        text = (
            REPO_ROOT / "scripts" / "build_windows_package.py"
        ).read_text(encoding="utf-8")
        for pattern in SECRET_PATTERNS:
            assert pattern.search(text) is None


class TestReadmeDocumentsMandatedSections:
    def test_mandated_sections_present(self):
        readme = (WINDOWS_DIR / "README-WINDOWS-PACKAGE.md").read_text(
            encoding="utf-8"
        )
        for section in (
            "State / log directory layout",
            "Secret handling",
            "Backup / restore",
            "Safe shutdown",
            "Firewall / antivirus",
            "SHA256SUMS",
        ):
            assert section in readme, f"README missing section: {section}"

    def test_honest_windows_host_verification_marker(self):
        """The README must keep the honest marker: Windows-host
        execution of the ps1 scripts is NOT VERIFIED in this run."""
        readme = (WINDOWS_DIR / "README-WINDOWS-PACKAGE.md").read_text(
            encoding="utf-8"
        )
        assert "NOT VERIFIED on a Windows host" in readme

    def test_paper_ready_stays_false_marker(self):
        readme = (WINDOWS_DIR / "README-WINDOWS-PACKAGE.md").read_text(
            encoding="utf-8"
        )
        assert "PAPER_READY stays FALSE" in readme
