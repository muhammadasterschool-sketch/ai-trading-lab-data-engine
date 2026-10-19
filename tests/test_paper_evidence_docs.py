"""U-24/U-25 (Stage D, patch plan P6) — structural pinning for the
paper-evidence documentation set:

- docs/PAPER_SOAK_PROCEDURE.md (U-24)
- docs/PAPER-TRADING-READINESS-REPORT.md (U-25)

These are DOCUMENTATION-ONLY pins (the inventory-precedent pattern):
they verify the documents exist, carry every mandated section, agree
with the AUTHORITATIVE code constants (the 32-gate register, the
supplier-disposition model), state PAPER_READY = FALSE, and contain
no credential-shaped strings. Weakening any of these properties
breaks the suite.
"""

import re
from pathlib import Path

import pytest

from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    GATE_SUPPLIER_DISPOSITION,
)
from data_engine.runtime.readiness import GATE_NAMES

DOCS = Path(__file__).resolve().parents[1] / "docs"
SOAK = DOCS / "PAPER_SOAK_PROCEDURE.md"
REPORT = DOCS / "PAPER-TRADING-READINESS-REPORT.md"

CREDENTIAL_PATTERNS = (
    re.compile(p, re.IGNORECASE)
    for p in (
        r"github_pat_[A-Za-z0-9_]+",
        r"gh[pousr]_[A-Za-z0-9]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"xox[baprs]-[A-Za-z0-9-]+",
        r"AIza[0-9A-Za-z_-]{30,}",
    )
)


def _norm(text: str) -> str:
    """Collapse all whitespace so line-wrapped phrases still match."""
    return " ".join(text.split())


def _no_credentials(text: str) -> None:
    for pattern in CREDENTIAL_PATTERNS:
        assert not pattern.search(text), (
            f"credential-shaped string matched {pattern.pattern!r} — "
            "the evidence docs are 0-secret surfaces"
        )


# ----------------------------------------------------------------------
# U-24 — the soak procedure
# ----------------------------------------------------------------------
class TestSoakProcedureDoc:
    def test_document_exists_and_is_honest_about_status(self):
        assert SOAK.is_file()
        text = _norm(SOAK.read_text(encoding="utf-8"))
        assert "NOT STARTED" in text
        assert "PAPER_READY = FALSE" in text
        assert "LIVE TRADING REMAINS NOT AUTHORIZED" in text

    @pytest.mark.parametrize(
        "section",
        [
            "## 1. Preconditions",
            "## 2. Duration",
            "## 3. Monitoring",
            "## 4. Success criteria",
            "## 5. Abort conditions",
            "## 6. Evidence pack",
            "## 7. Honest scope statement",
        ],
    )
    def test_mandated_sections(self, section):
        text = SOAK.read_text(encoding="utf-8")
        assert section in text, f"missing section {section!r}"

    def test_duration_and_thresholds_are_stated(self):
        text = SOAK.read_text(encoding="utf-8")
        assert "30 consecutive calendar days" in text
        assert "20 trading days" in text
        assert "900 s" in text  # the ratified paper feed-staleness default

    def test_ratified_paper_limits_are_stated(self):
        text = SOAK.read_text(encoding="utf-8")
        assert "5-per-60 s" in text
        assert "1 s-spacing" in text
        assert "10-open-orders" in text

    def test_abort_conditions_are_fail_closed(self):
        text = SOAK.read_text(encoding="utf-8")
        assert "the soak STOPS immediately" in text
        assert "NO partial success credit" in text

    def test_no_credentials(self):
        _no_credentials(SOAK.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------
# U-25 — the gate-by-gate readiness report
# ----------------------------------------------------------------------
class TestReadinessReportDoc:
    def test_document_exists_with_verdict(self):
        assert REPORT.is_file()
        text = _norm(REPORT.read_text(encoding="utf-8"))
        assert "PAPER_READY = FALSE" in text
        assert "BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY" in text
        assert "LIVE TRADING REMAINS NOT AUTHORIZED" in text

    def test_all_32_gates_listed_exactly_once(self):
        text = REPORT.read_text(encoding="utf-8")
        for gate in GATE_NAMES:
            count = len(re.findall(rf"\b{gate}\b", text))
            assert count >= 1, f"gate {gate} missing from the report"
        # the table header exists and the count line is honest
        assert "29 of the 32" in text

    def test_gate_set_agrees_with_the_authoritative_register(self):
        """The report must cover EXACTLY the authoritative 32-gate
        register — no invented gates, no missing gates."""
        text = REPORT.read_text(encoding="utf-8")
        listed = {
            g for g in GATE_NAMES if re.search(rf"\|\s*\d+\s*\|\s*{g}\s*\|", text)
        }
        assert listed == set(GATE_NAMES), (
            f"table coverage mismatch: missing={set(GATE_NAMES) - listed}, "
            f"extra={listed - set(GATE_NAMES)}"
        )

    def test_the_three_fail_gates_are_marked_fail(self):
        text = REPORT.read_text(encoding="utf-8")
        for gate in ("REAL_DATA_READY", "OPERATIONAL_FEED_READY",
                     "GOVERNANCE_READY"):
            row = re.search(
                rf"\|\s*\d+\s*\|\s*{gate}\s*\|\s*\*\*FAIL\*\*", text
            )
            assert row, f"{gate} must be marked **FAIL** in the table"

    def test_component_suppliers_agree_with_composition(self):
        """The six first-hand Stage C supplier gates in the report
        must match the composition root's supplier model exactly."""
        text = REPORT.read_text(encoding="utf-8")
        for gate in COMPONENT_EVIDENCE_GATES:
            assert re.search(
                rf"\|\s*\d+\s*\|\s*{gate}\s*\|\s*PASS\s*\|\s*COMPONENT\s*\|",
                text,
            ), f"{gate} must be PASS/COMPONENT (Stage C supplier)"
        # and the disposition registry classifies them identically
        for gate in COMPONENT_EVIDENCE_GATES:
            assert gate in GATE_SUPPLIER_DISPOSITION

    def test_blockers_reference_the_evidence_inventory(self):
        text = REPORT.read_text(encoding="utf-8")
        assert "READINESS_EVIDENCE_INVENTORY" in text or \
            "RDR-01" in text and "OFR-01" in text
        for item in ("RDR-01", "RDR-02", "RDR-03",
                     "OFR-01", "OFR-05",
                     "GOV-03", "GOV-04", "GOV-05"):
            assert item in text, f"blocker item {item} not cited"

    def test_live_query_documented(self):
        text = REPORT.read_text(encoding="utf-8")
        assert "data-engine status --gates" in text

    def test_no_credentials(self):
        _no_credentials(REPORT.read_text(encoding="utf-8"))
