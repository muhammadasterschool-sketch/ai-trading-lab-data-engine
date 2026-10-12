"""Readiness evidence inventory — integrity pinning tests
(Batch 9 release-readiness mandate, 2026-10-13).

The documentation-only evidence inventory
(``docs/READINESS_EVIDENCE_INVENTORY.md``, GOV-REI-001) tracks the
THREE unresolved readiness gates (REAL_DATA_READY,
OPERATIONAL_FEED_READY, GOVERNANCE_READY) at the per-evidence-item
level. Because that inventory is the operator's release-readiness
tracking artifact, its INTEGRITY is a safety property, not a style
preference: a silently weakened inventory (a missing evidence item
converted to PASS, an operator assertion re-labelled as verified
evidence, a mock broker described as a real integration) would
misrepresent PAPER readiness exactly like a fabricated test result.

These tests pin the fail-closed properties the Batch 9 mandate
requires, with regression force:

- structure: the inventory exists, covers exactly the three
  unresolved gates, and every item row carries ALL mandatory fields
  (status, evidence class, evidence reference, owner/approver role,
  verification timestamp where available, expiry/revalidation where
  applicable, explicit unresolved reason, next operator action);
- vocabulary: item status is ONLY "PASS" / "FAIL" / "UNVERIFIED",
  and evidence class is ONLY one of the four honest classes;
- no-fabrication: PASS is allowed ONLY for machine-verified evidence
  or RECORDED operator decisions cited by decision ID — an
  OPERATOR_ACTION_REQUIRED or UNVERIFIED_EXTERNAL item can never be
  PASS (missing evidence never converts to PASS);
- consistency: the three gates are members of the authoritative
  GATE_NAMES tuple (readiness.py), all three gate verdicts in the
  inventory are FAIL, and both the inventory and the authoritative
  final report still state PAPER_READY = FALSE (cross-document
  agreement — diverging edits break this pin);
- hygiene: the inventory contains no credential-shaped strings
  (it must never store secrets, tokens, keys, or account material).

The tests parse the Markdown tables structurally (column count and
cell vocabulary), never the prose — so wording may evolve freely
while the safety shape cannot.
"""

import re
from pathlib import Path

from data_engine.runtime.readiness import GATE_NAMES

REPO = Path(__file__).resolve().parents[1]
INVENTORY_PATH = REPO / "docs" / "READINESS_EVIDENCE_INVENTORY.md"
FINAL_REPORT_PATH = REPO / "PAPER_TRADING_READINESS_FINAL_REPORT.md"

#: The three gates the inventory tracks (the only unresolved ones —
#: the 29 PASS gates are recorded in the final report, not here).
UNRESOLVED_GATES = ("REAL_DATA_READY", "OPERATIONAL_FEED_READY",
                    "GOVERNANCE_READY")

#: Closed status vocabulary (mandate: PASS, FAIL, or UNVERIFIED —
#: nothing else, so no soft status can hide a missing verdict).
STATUS_VOCAB = {"PASS", "FAIL", "UNVERIFIED"}

#: Closed evidence-class vocabulary. The class column is what
#: structurally distinguishes VERIFIED evidence from OPERATOR
#: ASSERTIONS:
#:   VERIFIED_EVIDENCE       — machine-checked / executed first-hand
#:   RECORDED_DECISION       — a human decision recorded in-repo,
#:                             cited by its decision ID
#:   OPERATOR_ACTION_REQUIRED— an open human action (assertion NOT
#:                             yet made — can never be PASS)
#:   UNVERIFIED_EXTERNAL     — requires an external check that has
#:                             not been performed (never PASS)
CLASS_VOCAB = {
    "VERIFIED_EVIDENCE",
    "RECORDED_DECISION",
    "OPERATOR_ACTION_REQUIRED",
    "UNVERIFIED_EXTERNAL",
}

#: Classes that may legitimately carry a PASS status. Anything else
#: is missing evidence and must stay FAIL/UNVERIFIED (fail closed).
PASSABLE_CLASSES = {"VERIFIED_EVIDENCE", "RECORDED_DECISION"}

#: Decision-ID shape (GOV-KMC-001, WP-12-CI-ENABLE,
#: GOV-H1-002-RATIFY, SRC-APPROVAL-<name>-<date>, ...).
DECISION_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")

#: Credential shapes scanned by the CI secret scan (match count only
#: — never the content).
SECRET_SHAPES_RE = re.compile(
    r"github_pat_[A-Za-z0-9_]{20,}"
    r"|ghp_[A-Za-z0-9]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|sk-[A-Za-z0-9]{20,}"
)

#: Inventory item-ID prefixes, one per tracked gate.
ITEM_ID_RE = re.compile(r"^(RDR|OFR|GOV)-\d{2}$")


def _inventory_text() -> str:
    assert INVENTORY_PATH.exists(), (
        f"the readiness evidence inventory must exist at "
        f"{INVENTORY_PATH.relative_to(REPO)} (GOV-REI-001)"
    )
    return INVENTORY_PATH.read_text(encoding="utf-8")


def _parse_item_rows(text: str) -> list:
    """Structurally parse every inventory item row.

    An item row is a Markdown table row whose first cell is an item
    ID matching ``ITEM_ID_RE``. Returns ``[(item_id, cells), ...]``
    with cells stripped; header and separator rows are ignored.
    """
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and ITEM_ID_RE.match(cells[0]):
            rows.append((cells[0], cells))
    return rows


# ══════════════════════════════════════════════════════════════════
# 1. Structure — the inventory exists, is complete, well-formed
# ══════════════════════════════════════════════════════════════════

class TestInventoryStructure:

    def test_inventory_document_exists(self):
        assert INVENTORY_PATH.exists(), (
            "docs/READINESS_EVIDENCE_INVENTORY.md (GOV-REI-001) is "
            "missing — the Batch 9 evidence inventory deliverable"
        )

    def test_inventory_covers_exactly_the_three_unresolved_gates(self):
        text = _inventory_text()
        for gate in UNRESOLVED_GATES:
            assert re.search(rf"###\s+Gate\s+{gate}\b", text), (
                f"inventory must track gate {gate}"
            )

    def test_every_item_row_has_all_ten_columns(self):
        rows = _parse_item_rows(_inventory_text())
        assert rows, "inventory contains no evidence-item rows"
        for item_id, cells in rows:
            assert len(cells) == 10, (
                f"item {item_id} has {len(cells)} columns (needs 10: "
                "item, evidence required, status, evidence class, "
                "evidence reference, owner/approver role, verified at, "
                "expiry/revalidation, unresolved reason, next operator "
                "action)"
            )

    def test_item_ids_unique_and_stably_ordered(self):
        rows = _parse_item_rows(_inventory_text())
        ids = [item_id for item_id, _ in rows]
        assert len(ids) == len(set(ids)), "duplicate inventory item ids"
        # Stable ordering: ascending within each prefix group, and the
        # groups appear in gate order (RDR → OFR → GOV).
        for prefix in ("RDR", "OFR", "GOV"):
            group = [i for i in ids if i.startswith(prefix)]
            assert group == sorted(group), (
                f"{prefix}-* items must be listed in ascending, "
                f"deterministic order (got {group})"
            )
        order = [i.split("-")[0] for i in ids]
        assert order == sorted(order, key=["RDR", "OFR", "GOV"].index), (
            "gate sections must appear in canonical order "
            "(REAL_DATA_READY, OPERATIONAL_FEED_READY, GOVERNANCE_READY)"
        )

    def test_mandatory_text_fields_present_everywhere(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            (item, evidence_required, status, evidence_class,
             reference, owner, verified_at, expiry, reason,
             next_action) = cells
            assert evidence_required and evidence_required != "—", (
                f"{item_id}: the evidence requirement must be stated"
            )
            assert reference and reference != "—", (
                f"{item_id}: an evidence location/reference is mandatory"
            )
            assert owner and owner != "—", (
                f"{item_id}: an evidence owner / approver role is "
                "mandatory"
            )
            assert next_action and next_action != "—", (
                f"{item_id}: a next operator action is mandatory"
            )


# ══════════════════════════════════════════════════════════════════
# 2. Integrity rules — fail-closed semantics, no fabrication
# ══════════════════════════════════════════════════════════════════

class TestInventoryIntegrityRules:

    def test_status_vocabulary_is_closed(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            assert cells[2] in STATUS_VOCAB, (
                f"{item_id}: status {cells[2]!r} is outside the closed "
                "vocabulary {PASS, FAIL, UNVERIFIED}"
            )

    def test_evidence_class_vocabulary_is_closed(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            assert cells[3] in CLASS_VOCAB, (
                f"{item_id}: evidence class {cells[3]!r} is outside "
                "the closed vocabulary (verified evidence / recorded "
                "decision / operator action required / unverified "
                "external)"
            )

    def test_missing_evidence_never_converts_to_pass(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            if cells[2] == "PASS":
                assert cells[3] in PASSABLE_CLASSES, (
                    f"{item_id}: PASS is only legitimate for "
                    "VERIFIED_EVIDENCE or RECORDED_DECISION rows — "
                    "missing evidence must never convert to PASS"
                )

    def test_unresolved_items_carry_explicit_reasons(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            if cells[2] != "PASS":
                assert cells[8] and cells[8] != "—", (
                    f"{item_id}: every unresolved item requires an "
                    "explicit reason for its unresolved status"
                )

    def test_verified_evidence_carries_verification_timestamp(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            if cells[3] == "VERIFIED_EVIDENCE":
                assert cells[6] and cells[6] != "—", (
                    f"{item_id}: VERIFIED_EVIDENCE items must record "
                    "their verification timestamp"
                )

    def test_recorded_decisions_are_cited_by_decision_id(self):
        rows = _parse_item_rows(_inventory_text())
        for item_id, cells in rows:
            if cells[3] == "RECORDED_DECISION":
                row_text = " ".join(cells)
                assert DECISION_ID_RE.search(row_text), (
                    f"{item_id}: RECORDED_DECISION items must cite the "
                    "human decision by its decision ID (operator "
                    "assertions become evidence only when recorded and "
                    "citable)"
                )

    def test_integrity_rules_section_states_mandated_distinctions(self):
        text = _inventory_text()
        lowered = text.lower()
        for phrase in (
            "registration is not trading eligibility",
            "real_unverified",
            "real_verified",
            "mock",
            "real broker",
            "operator assertion",
            "missing evidence",
            "pass",
        ):
            assert phrase in lowered, (
                f"the inventory's integrity-rules section must state "
                f"the mandated distinction containing {phrase!r}"
            )

    def test_inventory_contains_no_credential_shaped_strings(self):
        text = _inventory_text()
        matches = SECRET_SHAPES_RE.findall(text)
        assert not matches, (
            f"{len(matches)} credential-shaped string(s) found in the "
            "inventory — it must never store secrets, tokens, keys, "
            "or account material (shapes counted, content not printed)"
        )


# ══════════════════════════════════════════════════════════════════
# 3. Gate consistency — agreement with the authoritative machinery
# ══════════════════════════════════════════════════════════════════

class TestGateConsistency:

    def test_tracked_gates_are_authoritative_gate_names(self):
        assert set(UNRESOLVED_GATES) <= set(GATE_NAMES), (
            "the tracked gates must be members of the authoritative "
            "GATE_NAMES tuple (readiness.py)"
        )

    def test_all_three_gate_verdicts_are_fail(self):
        text = _inventory_text()
        for gate in UNRESOLVED_GATES:
            block = re.search(
                rf"###\s+Gate\s+{gate}\b.*?(?=\n###\s+Gate\s+|\Z)",
                text, re.DOTALL,
            )
            assert block, f"gate section {gate} not found"
            assert re.search(
                r"\*\*Gate verdict:\s+FAIL\*\*", block.group(0)
            ), (
                f"{gate}: the inventory verdict must be FAIL (no "
                "evidence may claim otherwise without recorded "
                "decisions and verified data)"
            )

    def test_paper_ready_false_stated_in_inventory(self):
        text = _inventory_text()
        assert "PAPER_READY = FALSE" in text, (
            "the inventory must state PAPER_READY = FALSE"
        )
        assert "PAPER_READY = TRUE" not in text, (
            "the inventory must never state PAPER_READY = TRUE: the "
            "three tracked gates are FAIL, so the verdict is FALSE by "
            "the fail-closed conjunction over ALL gates (readiness.py "
            "§66) — a TRUE statement anywhere in the inventory is a "
            "fabrication signal"
        )

    def test_live_not_authorized_stated_in_inventory(self):
        assert re.search(r"LIVE\s+(?:TRADING\s+)?NOT\s+AUTHORIZED",
                         _inventory_text()), (
            "the inventory must state LIVE NOT AUTHORIZED"
        )

    def test_inventory_agrees_with_authoritative_final_report(self):
        """Cross-document consistency guard: the authoritative final
        report and the inventory must not diverge on the verdict —
        flipping either document alone breaks this pin."""
        final_report = FINAL_REPORT_PATH.read_text(encoding="utf-8")
        assert "**PAPER_READY = FALSE.**" in final_report, (
            "the authoritative final report no longer states "
            "PAPER_READY = FALSE — the inventory agrees with it, so "
            "this divergence is a fabrication signal"
        )
