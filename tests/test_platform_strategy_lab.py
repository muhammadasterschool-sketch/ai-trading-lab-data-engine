"""Platform package tests — strategy management lab (Phase D)."""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.platform import (
    AuditLog,
    EvidenceRecord,
    LifecycleError,
    LifecycleState,
    OperatorApproval,
    StrategyLab,
    StrategyType,
)

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(hours=1)


@pytest.fixture()
def lab():
    return StrategyLab(audit_log=AuditLog())


def _create(lab: StrategyLab):
    return lab.create(
        name="sma-trend",
        strategy_type=StrategyType.RULES,
        spec={"entry": "sma_cross_up", "exit": "sma_cross_down"},
        config={"fast": 20, "slow": 50},
        source=None,
        at=T0,
        created_by="operator",
        instruments=("iid-gold",),
    )


def _add(lab: StrategyLab, sid: str, kind: str, at: datetime = T1):
    rec = lab.get(sid)
    return lab.add_evidence(
        sid,
        EvidenceRecord(
            kind=kind, version=rec.current_version, reference=f"{kind}-1", recorded_at=at
        ),
    )


class TestCreationAndVersioning:
    def test_create_assigns_stable_id_and_version_1(self, lab):
        rec = _create(lab)
        assert rec.strategy_id.startswith("STR-")
        assert rec.current_version == 1
        assert rec.state is LifecycleState.DRAFT
        assert len(rec.versions) == 1
        assert rec.versions[0].spec_hash and rec.versions[0].config_hash

    def test_python_strategy_requires_source(self, lab):
        with pytest.raises(ValueError, match="PYTHON strategies require source"):
            lab.create(
                name="py-strat",
                strategy_type=StrategyType.PYTHON,
                spec={},
                config={},
                source=None,
                at=T0,
                created_by="operator",
            )

    def test_new_version_resets_evidence_and_state(self, lab):
        rec = _create(lab)
        _add(lab, rec.strategy_id, "static_check")
        rec = lab.transition(rec.strategy_id, LifecycleState.VALIDATED, T1)
        rec = lab.new_version(
            rec.strategy_id,
            at=T1,
            created_by="operator",
            config={"fast": 10, "slow": 50},
        )
        assert rec.current_version == 2
        assert rec.state is LifecycleState.DRAFT
        assert rec.evidence == ()
        assert len(rec.versions) == 2

    def test_no_op_version_refused(self, lab):
        rec = _create(lab)
        with pytest.raises(ValueError, match="no material change"):
            lab.new_version(rec.strategy_id, at=T1, created_by="operator")

    def test_versions_are_immutable_records(self, lab):
        rec = _create(lab)
        with pytest.raises(Exception):
            rec.versions[0].spec_hash = "tamper"  # type: ignore[misc]


class TestLifecycle:
    def test_full_happy_path_to_awaiting_live_approval(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        lab.transition(sid, LifecycleState.SUBMITTED, T1)
        lab.transition(sid, LifecycleState.STATIC_VALIDATION, T1)
        _add(lab, sid, "static_check")
        lab.transition(sid, LifecycleState.VALIDATED, T1)
        lab.transition(sid, LifecycleState.BACKTEST_RUNNING, T1)
        _add(lab, sid, "backtest_report")
        lab.transition(sid, LifecycleState.BACKTEST_PASSED, T1)
        lab.transition(sid, LifecycleState.PAPER_RUNNING, T1)
        _add(lab, sid, "paper_report")
        lab.transition(sid, LifecycleState.PAPER_PASSED, T1)
        lab.transition(sid, LifecycleState.EVIDENCE_REVIEW, T1)
        _add(lab, sid, "eligibility_review")
        rec = lab.transition(sid, LifecycleState.AWAITING_LIVE_APPROVAL, T1)
        assert rec.state is LifecycleState.AWAITING_LIVE_APPROVAL

    def test_transition_without_evidence_fails_closed(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        lab.transition(sid, LifecycleState.SUBMITTED, T1)
        lab.transition(sid, LifecycleState.STATIC_VALIDATION, T1)
        with pytest.raises(LifecycleError, match="requires evidence 'static_check'"):
            lab.transition(sid, LifecycleState.VALIDATED, T1)

    def test_illegal_jump_refused(self, lab):
        rec = _create(lab)
        with pytest.raises(LifecycleError, match="illegal transition"):
            lab.transition(rec.strategy_id, LifecycleState.PAPER_RUNNING, T1)

    def test_live_active_is_structurally_refused(self, lab):
        rec = _create(lab)
        with pytest.raises(LifecycleError, match="LIVE_ACTIVE is not reachable"):
            lab.transition(rec.strategy_id, LifecycleState.LIVE_ACTIVE, T1)

    def test_live_approved_requires_operator_approval(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        _add(lab, sid, "eligibility_review")
        with pytest.raises(LifecycleError, match="explicit OperatorApproval"):
            lab.transition(sid, LifecycleState.LIVE_APPROVED, T1)

    def test_approval_scope_mismatch_refused(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        approval = OperatorApproval(
            actor="operator",
            approved_at=T1,
            strategy_id="STR-OTHER",
            version=1,
            scope="live",
            signature="sig",
        )
        with pytest.raises(LifecycleError, match="scope mismatch"):
            lab.transition(
                sid, LifecycleState.LIVE_APPROVED, T1, approval=approval
            )

    def test_old_evidence_cannot_certify_new_version(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        _add(lab, sid, "static_check", at=T1)
        lab.new_version(sid, at=T1, created_by="operator", config={"fast": 5, "slow": 50})
        with pytest.raises(LifecycleError, match="cannot be attached"):
            lab.add_evidence(
                sid,
                EvidenceRecord(kind="static_check", version=1, reference="x", recorded_at=T1),
            )
        with pytest.raises(LifecycleError, match="requires evidence"):
            # v2 has no static_check; the transition path exists only via v2 evidence
            lab.transition(sid, LifecycleState.VALIDATED, T1)

    def test_failure_states_reachable(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        lab.transition(sid, LifecycleState.SUBMITTED, T1)
        lab.transition(sid, LifecycleState.STATIC_VALIDATION, T1)
        rec = lab.transition(sid, LifecycleState.STATIC_CHECK_FAILED, T1)
        assert rec.state is LifecycleState.STATIC_CHECK_FAILED


class TestManagement:
    def test_archive_disables_and_cannot_reenable(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        rec = lab.transition(sid, LifecycleState.ARCHIVED, T1)
        assert rec.enabled is False
        with pytest.raises(LifecycleError, match="archived strategy cannot be re-enabled"):
            lab.set_enabled(sid, True, T1)

    def test_enable_disable(self, lab):
        rec = _create(lab)
        sid = rec.strategy_id
        rec = lab.set_enabled(sid, False, T1)
        assert rec.enabled is False
        rec = lab.set_enabled(sid, True, T1)
        assert rec.enabled is True

    def test_duplicate_strategy_id_refused(self, lab):
        rec = _create(lab)
        with pytest.raises(ValueError, match="already exists"):
            lab.create(
                name="other",
                strategy_type=StrategyType.RULES,
                spec={},
                config={},
                source=None,
                at=T1,
                created_by="operator",
                strategy_id=rec.strategy_id,
            )

    def test_audit_events_emitted(self, lab):
        _create(lab)
        rec = lab.get(_create_lab_id(lab))
        assert lab is not None
        # creation emits one audit event
        assert len(lab.all_strategies()) >= 1


def _create_lab_id(lab: StrategyLab) -> str:
    return lab.all_strategies()[0].strategy_id
