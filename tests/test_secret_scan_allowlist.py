"""FIX-5 pin: the secret-scan allowlist is EXACTLY ONE synthetic
fixture, and NO current tree carries a contiguous literal.

The CI secret scan (all-history, 0 real hits required) filters one
documented false positive: the Stage F redaction test's SYNTHETIC
token fixture (an obviously-fake string used as test data, present
in immutable history commits ddb4a2b..bab12c7 and replaced by
runtime concatenation in b2e1879). These tests pin that the
allowlist cannot silently grow and that the current tree is clean —
a real credential would still fail CI.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_FILE = REPO_ROOT / ".github" / "ci_secret_scan_reference.txt"

SCAN_PATTERN = (
    r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{35}"
)


class TestSecretScanAllowlist:
    def test_ci_step_filters_exactly_one_fixture(self):
        """The workflow's scan step contains EXACTLY ONE grep -vF
        filter line (no silent allowlist growth)."""
        text = (
            REPO_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        filter_lines = [
            line
            for line in text.splitlines()
            if "grep -vF" in line and "REAL=" in line
        ]
        assert len(filter_lines) == 1, (
            "the secret-scan allowlist must stay EXACTLY one filter "
            f"(found {len(filter_lines)})"
        )
        # the filter targets the documented synthetic fixture only
        assert "token github_pat_" in filter_lines[0]
        assert " tail" in filter_lines[0]

    def test_current_tree_has_no_contiguous_literal(self):
        """No CURRENT file carries a contiguous scanner-shaped
        literal (the fixture was replaced by concatenation)."""
        offenders = subprocess.run(
            ["git", "grep", "-lE", SCAN_PATTERN, "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).stdout.strip()
        assert offenders == "", (
            f"contiguous credential-shaped literals in current tree: "
            f"{offenders}"
        )

    def test_redaction_test_uses_concatenation_not_literal(self):
        """The redaction test builds its synthetic input from pieces
        at runtime (scanner hygiene) and still proves redaction."""
        test_text = (
            REPO_ROOT / "tests" / "test_monitoring_api.py"
        ).read_text(encoding="utf-8")
        assert '"github_" + "pat_"' in test_text
        # no contiguous literal in the test source
        assert not re.search(
            r"github_pat_[A-Za-z0-9_]{20,}", test_text
        )

    def test_scan_still_catches_real_shaped_credentials(self):
        """Control: the scan pattern itself matches a realistic
        credential-shaped string (the control is NOT weakened)."""
        assert re.search(
            SCAN_PATTERN, "github_pat_11REALcredentialDATAhere1234567890"
        )
        assert re.search(SCAN_PATTERN, "ghp_" + "a" * 36)
        assert re.search(SCAN_PATTERN, "AKIA" + "ABCDEFGHIJKLMNOP")
        # and does NOT match the assembled-from-pieces source idiom
        assert not re.search(SCAN_PATTERN, '"github_" + "pat_" +')
