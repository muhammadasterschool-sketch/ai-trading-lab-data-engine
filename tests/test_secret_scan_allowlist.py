"""FIX-5/F-18b/FIX-7 pin: the secret-scan allowlist is EXACTLY TWO
short synthetic markers, and NO current tree carries a contiguous
credential-shaped literal.

The CI secret scan (all-history, 0 non-baselined hits required)
filters two DOCUMENTED false positives, both obviously-synthetic
fixtures that live in immutable history:

* ``github_pat_11AAAA`` — the Stage F redaction test's synthetic
  token fixture (commits a2a6d2b/ddb4a2b..bab12c7), replaced by
  runtime concatenation from b2e1879 onward.
* ``github_pat_11REAL`` — the 812a5fc version of THIS file's own
  positive-control literal, replaced by concatenation from the
  FIX-7 merge onward.

Both markers are deliberately SHORTER than the scan pattern's own
20-character tail requirement, so neither marker is itself
credential-shaped and writing them in ci.yml keeps the current
tree clean. A real credential never carries either marker, so it
still fails CI. These tests pin that the allowlist cannot silently
grow and that the current tree stays clean.
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_PATTERN = (
    r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,}|"
    r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{20,}|AIza[0-9A-Za-z_-]{35}"
)

MARKERS = ("github_pat_11AAAA", "github_pat_11REAL")


class TestSecretScanAllowlist:
    def test_ci_step_filters_exactly_the_documented_markers(self):
        """The workflow's scan step filters EXACTLY the two documented
        synthetic markers (no silent allowlist growth) via exactly one
        filtering pipeline, and NO literal-substring filter exists (the
        FIX-5 approach embedded a credential-shaped literal and is
        forbidden forever)."""
        text = (
            REPO_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        # both exact marker assignments present
        assert 'BASELINE="github_pat_11AAAA"' in text
        assert 'MARKER2="github_pat_11REAL"' in text
        # exactly ONE filtering pipeline line driving BOTH marker
        # variables
        filter_lines = [
            line
            for line in text.splitlines()
            if "grep -vF" in line
        ]
        assert len(filter_lines) == 1, (
            "the secret-scan filter must stay exactly ONE pipeline "
            f"stage (found {len(filter_lines)})"
        )
        pipeline = filter_lines[0]
        assert '"$BASELINE"' in pipeline and '"$MARKER2"' in pipeline, (
            "the single filter pipeline must apply both NAMED marker "
            "variables, never an embedded literal substring"
        )
        # the forbidden FIX-5 pattern: literal substring filtering
        assert "grep -vF 'token" not in text and 'grep -vF "token' not in text
        # fail-closed tool-error handling (F-18b)
        assert "fail closed" in text

    def test_markers_are_not_themselves_credential_shaped(self):
        """Scanner hygiene: the two allowlist markers are shorter than
        the pattern's 20-char tail requirement, so writing them in
        ci.yml cannot reintroduce a current-tree hit."""
        for marker in MARKERS:
            assert not re.search(SCAN_PATTERN, marker), marker

    def test_current_tree_has_no_contiguous_literal(self):
        """No CURRENT file carries a contiguous scanner-shaped
        literal (both fixtures are replaced by concatenation)."""
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
        assert '"github_" + "pat_11AAAA"' in test_text
        # no contiguous literal in the test source
        assert not re.search(
            r"github_pat_[A-Za-z0-9_]{20,}", test_text
        )

    def test_scan_still_catches_real_shaped_credentials(self):
        """Control: the scan pattern itself matches realistic
        credential-shaped strings (the control is NOT weakened)."""
        assert re.search(
            SCAN_PATTERN, "github_pat_" + "A" * 34
        )
        assert re.search(SCAN_PATTERN, "ghp_" + "a" * 36)
        assert re.search(SCAN_PATTERN, "AKIA" + "ABCDEFGHIJKLMNOP")
        # and does NOT match the assembled-from-pieces source idiom
        assert not re.search(SCAN_PATTERN, '"github_" + "pat_" +')
        # nor the short allowlist markers
        for marker in MARKERS:
            assert not re.search(SCAN_PATTERN, marker)
