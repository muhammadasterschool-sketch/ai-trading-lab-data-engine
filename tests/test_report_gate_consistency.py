"""FIX-11 (B-P0-02) — canonical readiness-gate consistency pins.

The audit found the reports disagreed on the pending-gate count: the
Stage-D readiness report and PROJECT-STATE-REPORT said TWO pending
operational gates (counting GOVERNANCE_READY as VERIFIED_IN_CODE)
while docs/READINESS_EVIDENCE_INVENTORY.md and the composition root's
own ``HUMAN_EVIDENCE_GATES`` say THREE unresolved human-evidence
gates. Truth: the CODE constants are the single authoritative
evaluator; every report must agree with them.

These tests make the reconciliation EXECUTABLE and permanent: any
future doc edit that drifts from the code's gate classification fails
the suite (a report cannot claim a human gate is code-verified, and
cannot miscount the pending set).
"""

import re
from pathlib import Path

from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    GATE_SUPPLIER_DISPOSITION,
    HUMAN_EVIDENCE_GATES,
    HUMAN_ACTION_REQUIRED,
)
from data_engine.runtime.readiness import GATE_NAMES

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The reports whose pending-gate claims must agree with the code.
REPORTS = (
    "artifacts/stage-d/PAPER-TRADING-READINESS-REPORT.md",
    "PROJECT-STATE-REPORT.md",
    "PAPER_TRADING_READINESS_FINAL_REPORT.md",
)

#: The evidence inventory (the per-item tracker of the three open
#: human gates — GOV-03/GOV-04/GOV-05 etc.).
INVENTORY = "docs/READINESS_EVIDENCE_INVENTORY.md"


class TestGateCountConsistency:

    def test_gate_names_are_the_canonical_32(self):
        assert len(GATE_NAMES) == 32
        assert len(set(GATE_NAMES)) == 32

    def test_human_gates_are_exactly_three_named_gates(self):
        """The code's authoritative classification: exactly
        REAL_DATA_READY, OPERATIONAL_FEED_READY, GOVERNANCE_READY are
        human-dependency gates (only recorded human decisions can
        satisfy them — FIX-9 requires SIGNED approvals for these)."""
        assert HUMAN_EVIDENCE_GATES == frozenset({
            "REAL_DATA_READY",
            "OPERATIONAL_FEED_READY",
            "GOVERNANCE_READY",
        })

    def test_supplier_disposition_marks_human_gates(self):
        for gate in HUMAN_EVIDENCE_GATES:
            assert GATE_SUPPLIER_DISPOSITION[gate] == HUMAN_ACTION_REQUIRED

    def test_stage_d_report_counts_three_pending(self):
        """The Stage-D matrix must count 3 PENDING_OPERATIONAL_EVIDENCE
        (the human gates) and must NOT classify GOVERNANCE_READY as
        VERIFIED_IN_CODE (B-P0-02 regression pin)."""
        text = (
            REPO_ROOT / "artifacts/stage-d/PAPER-TRADING-READINESS-REPORT.md"
        ).read_text(encoding="utf-8")
        assert "3 PENDING_OPERATIONAL_EVIDENCE" in text, (
            "Stage-D report must count THREE pending operational "
            "evidence gates (the HUMAN_EVIDENCE_GATES) — the "
            "2-pending claim was the B-P0-02 inconsistency"
        )
        assert "2 PENDING_OPERATIONAL_EVIDENCE" not in text, (
            "the old two-pending claim must not survive anywhere in "
            "the Stage-D report"
        )
        # GOVERNANCE_READY row must be PENDING, not code-verified
        gov_rows = [
            ln for ln in text.splitlines()
            if ln.strip().startswith("| 32 | GOVERNANCE_READY")
        ]
        assert gov_rows, "GOVERNANCE_READY matrix row must exist"
        assert "PENDING_OPERATIONAL_EVIDENCE" in gov_rows[0]
        assert "VERIFIED_IN_CODE" not in gov_rows[0]

    def test_project_state_report_counts_three_pending(self):
        text = (REPO_ROOT / "PROJECT-STATE-REPORT.md").read_text(
            encoding="utf-8"
        )
        assert "3 PENDING_OPERATIONAL_EVIDENCE" in text
        assert "30 VERIFIED_IN_CODE, 2 PENDING_OPERATIONAL_EVIDENCE" \
            not in text

    def test_evidence_inventory_tracks_three_unresolved_gates(self):
        """The per-evidence-item inventory tracks all THREE human
        gates as unresolved (FAIL) — the third source of the same
        truth."""
        text = (REPO_ROOT / INVENTORY).read_text(encoding="utf-8")
        for gate in sorted(HUMAN_EVIDENCE_GATES):
            assert gate in text, (
                f"{INVENTORY} must track {gate} evidence items"
            )
        # the inventory's own changelog records the three-gate posture
        assert "all three gates remain FAIL" in text or \
            "three unresolved readiness gates" in text

    def test_reports_agree_with_code_gate_classification(self):
        """Cross-check: no report may claim a HUMAN gate is satisfied
        by code alone (the exact B-P0-02 error class)."""
        for report in REPORTS:
            path = REPO_ROOT / report
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for gate in HUMAN_EVIDENCE_GATES:
                # any matrix row naming a human gate must not pair it
                # with a code-verified disposition
                rows = [
                    ln for ln in text.splitlines()
                    if gate in ln and "VERIFIED_IN_CODE" in ln
                    and ln.strip().startswith("|")
                ]
                assert not rows, (
                    f"{report} classifies human gate {gate} as "
                    "VERIFIED_IN_CODE — human gates require recorded "
                    "human decisions (see composition.HUMAN_EVIDENCE_"
                    "GATES); this is the B-P0-02 drift"
                )

    def test_component_gates_are_six(self):
        """The composition root verifies exactly these six first-hand."""
        assert COMPONENT_EVIDENCE_GATES == frozenset({
            "PERSISTENCE_READY",
            "LEDGER_READY",
            "OMS_READY",
            "RISK_READY",
            "KILLSWITCH_READY",
            "RECONCILIATION_READY",
        })

    def test_cli_status_gates_output_matches_classification(self):
        """The CLI gate listing (GATE_SUPPLIER_DISPOSITION) must cover
        every gate and classify exactly the three human gates as
        HUMAN_ACTION_REQUIRED (the executable canonical output)."""
        assert set(GATE_SUPPLIER_DISPOSITION) == set(GATE_NAMES)
        human = {
            g for g, d in GATE_SUPPLIER_DISPOSITION.items()
            if d == HUMAN_ACTION_REQUIRED
        }
        assert human == set(HUMAN_EVIDENCE_GATES)
