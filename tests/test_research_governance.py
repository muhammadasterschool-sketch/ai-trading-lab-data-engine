"""Phase 4A.4 acceptance tests — research governance.

Blueprint 5.15 invariants:

- RG-A01  no self-approval: submitter == approver raises
- RG-A02  machine approvers rejected (human-only approval)
- RG-A03  deterministic research hash (res44.) and approval hash
          (appr44.); cross-instance stable
- RG-A04  registry: register / duplicate rejection / ghost approval
          rejection
- RG-A05  status lifecycle: PENDING -> APPROVED; later rejection
          overrides; later approval overrides rejection (auditable
          trail, latest human decision governs)
- RG-A06  unapproved research visible but NOT in approved_only()
          (never treated as validated by hiding)
- RG-A07  citations require verifiable content hashes
"""

from datetime import datetime, UTC

import pytest

from data_engine.research import (
    PrincipalKind,
    Principal,
    ApprovalStatus,
    Citation,
    ApprovalMetadata,
    ResearchContract,
    ResearchRegistry,
    ResearchRegistryError,
    RESEARCH_PREFIX,
    APPROVAL_PREFIX,
)


def utc(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


HUMAN = Principal(principal_id="operator-1", kind=PrincipalKind.HUMAN)
AGENT = Principal(principal_id="zai-agent", kind=PrincipalKind.MACHINE)


def make_contract(research_id="r-001", title="Momentum persistence in FX"):
    return ResearchContract(
        research_id=research_id,
        title=title,
        hypothesis="12h momentum persists 4 bars at 55% frequency",
        methodology="PIT view over 2019-2021; walk-forward validation",
        data_references=("pit4v." + "a" * 64,),
        citations=(
            Citation(source_ref="dataset:fx-majors-v3", content_hash="b" * 64),
        ),
        submitted_by=AGENT,
        submitted_at=utc(2026, 10, 1),
    )


class TestNoSelfApproval:

    def test_rg_a01_same_principal_rejected(self):
        """RG-A01: submitter == approver fails closed."""
        with pytest.raises(ValueError, match="same principal"):
            ApprovalMetadata(
                research_hash="x" * 64,
                submitter=HUMAN,
                approver=HUMAN,
                decision=ApprovalStatus.APPROVED,
                decision_time=utc(2026, 10, 2),
            )

    def test_rg_a02_machine_approver_rejected(self):
        """RG-A02: machine principals can never approve."""
        with pytest.raises(ValueError, match="HUMAN"):
            ApprovalMetadata(
                research_hash="x" * 64,
                submitter=AGENT,
                approver=Principal(principal_id="other-agent", kind=PrincipalKind.MACHINE),
                decision=ApprovalStatus.APPROVED,
                decision_time=utc(2026, 10, 2),
            )


class TestIdentity:

    def test_rg_a03_hashes_deterministic(self):
        c1, c2 = make_contract(), make_contract()
        assert c1.research_hash == c2.research_hash
        assert c1.research_hash.startswith(RESEARCH_PREFIX)
        assert len(c1.research_hash) == 70  # 6 + 64
        a1 = ApprovalMetadata(
            research_hash=c1.research_hash,
            submitter=AGENT, approver=HUMAN,
            decision=ApprovalStatus.APPROVED,
            decision_time=utc(2026, 10, 2),
        )
        a2 = ApprovalMetadata(
            research_hash=c1.research_hash,
            submitter=AGENT, approver=HUMAN,
            decision=ApprovalStatus.APPROVED,
            decision_time=utc(2026, 10, 2),
        )
        assert a1.approval_hash == a2.approval_hash
        assert a1.approval_hash.startswith(APPROVAL_PREFIX)
        # Content change -> hash change
        c3 = make_contract(title="Different title")
        assert c1.research_hash != c3.research_hash


class TestRegistry:

    def test_rg_a04_register_and_duplicates(self):
        registry = ResearchRegistry()
        h = registry.register(make_contract())
        assert h == make_contract().research_hash
        with pytest.raises(ResearchRegistryError, match="already registered"):
            registry.register(make_contract())
        with pytest.raises(ResearchRegistryError, match="unregistered"):
            ApprovalMetadata(
                research_hash="c" * 64,
                submitter=AGENT, approver=HUMAN,
                decision=ApprovalStatus.APPROVED,
                decision_time=utc(2026, 10, 2),
            ) and registry.attach_approval(ApprovalMetadata(
                research_hash="c" * 64,
                submitter=AGENT, approver=HUMAN,
                decision=ApprovalStatus.APPROVED,
                decision_time=utc(2026, 10, 2),
            ))

    def test_rg_a05_status_lifecycle(self):
        """RG-A05: latest human decision governs."""
        registry = ResearchRegistry()
        contract = make_contract()
        registry.register(contract)

        assert registry.status("r-001") is ApprovalStatus.PENDING

        approve = ApprovalMetadata(
            research_hash=contract.research_hash,
            submitter=AGENT, approver=HUMAN,
            decision=ApprovalStatus.APPROVED,
            decision_time=utc(2026, 10, 2),
        )
        registry.attach_approval(approve)
        assert registry.status("r-001") is ApprovalStatus.APPROVED

        reject = ApprovalMetadata(
            research_hash=contract.research_hash,
            submitter=AGENT,
            approver=Principal(principal_id="operator-2", kind=PrincipalKind.HUMAN),
            decision=ApprovalStatus.REJECTED,
            decision_time=utc(2026, 10, 5),
            rationale="methodology gap",
        )
        registry.attach_approval(reject)
        assert registry.status("r-001") is ApprovalStatus.REJECTED

        reapprove = ApprovalMetadata(
            research_hash=contract.research_hash,
            submitter=AGENT, approver=HUMAN,
            decision=ApprovalStatus.APPROVED,
            decision_time=utc(2026, 10, 8),
        )
        registry.attach_approval(reapprove)
        assert registry.status("r-001") is ApprovalStatus.APPROVED

    def test_rg_a06_unapproved_not_validated(self):
        """RG-A06: pending entries visible but excluded from approved."""
        registry = ResearchRegistry()
        pending = make_contract("r-pending")
        registry.register(pending)
        approved = make_contract("r-approved")
        registry.register(approved)
        registry.attach_approval(ApprovalMetadata(
            research_hash=approved.research_hash,
            submitter=AGENT, approver=HUMAN,
            decision=ApprovalStatus.APPROVED,
            decision_time=utc(2026, 10, 3),
        ))
        assert registry.get("r-pending") is not None  # visible
        assert registry.approved_only() == ["r-approved"]

    def test_rg_a07_citation_hash_required(self):
        with pytest.raises(ValueError, match="verifiable hash"):
            Citation(source_ref="src", content_hash="short")
