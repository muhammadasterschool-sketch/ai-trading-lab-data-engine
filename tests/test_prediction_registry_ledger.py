"""Prediction Intelligence acceptance tests — registry & ledger.

Mandate test-matrix coverage (§47):

- T-PRED-019  prediction outcome ledger (append-only, tamper-evident)
- T-PRED-022  model approval (human approval enables graduation)
- T-PRED-023  self-approval rejection (AI approver refused)
- T-PRED-024  artifact tampering detection (hash mismatch)
"""

import pytest

from data_engine.prediction.ledger import (
    OutcomeRecord,
    PredictionOutcomeLedger,
)
from data_engine.prediction.models import BaseRateBaseline, LogisticCrashModel
from data_engine.prediction.registry import (
    ModelLifecycleState,
    ModelRecord,
    PredictionModelRegistry,
    RegistryError,
)
from data_engine.prediction.gates import (
    BlockReason,
    PredictionGateInput,
    evaluate_prediction_gates,
)


def make_record(model_id="LOGISTIC-CRASH", version="1") -> ModelRecord:
    return ModelRecord(
        model_id=model_id,
        model_version=version,
        experiment_id="EXP-1",
        owner="research-operator",
        dataset_id="DS-1",
        feature_set_id="predf." + "1" * 64,
        training_cutoff="2019-12-31",
        status=ModelLifecycleState.DISCOVER,
        validation_evidence=("brier=0.18@oos",),
        calibration_evidence=("platt ece=0.03",),
    )


def walk_to(registry, model_id, version, target):
    """Advance the mandated chain DISCOVER -> ... -> target."""
    chain = [
        ModelLifecycleState.TRAIN,
        ModelLifecycleState.VALIDATE,
        ModelLifecycleState.CALIBRATE,
        ModelLifecycleState.ADVERSARIAL_TEST,
        ModelLifecycleState.REGISTER,
        ModelLifecycleState.HUMAN_REVIEW,
    ]
    for state in chain:
        registry.transition(model_id, version, state)
        if state is target:
            return
    registry.transition(model_id, version, target)


# ─── T-PRED-022: model approval & graduation ───


def test_t_pred_022_full_lifecycle_with_human_approval():
    registry = PredictionModelRegistry()
    record = make_record()
    registry.register(record)
    walk_to(registry, record.model_id, record.model_version,
            ModelLifecycleState.HUMAN_REVIEW)
    decision = registry.submit_approval(
        record.model_id, record.model_version, "human-operator-1",
        approver_kind="human", recorded_at="2026-10-08T00:00:00+00:00",
    )
    assert decision.accepted
    registry.transition(record.model_id, record.model_version,
                        ModelLifecycleState.PAPER)
    registry.transition(record.model_id, record.model_version,
                        ModelLifecycleState.MONITOR)
    graduated = registry.transition(
        record.model_id, record.model_version, ModelLifecycleState.GRADUATE
    )
    assert graduated.status is ModelLifecycleState.GRADUATE
    assert graduated.approval is not None
    assert graduated.approval.approver_kind == "human"


def test_t_pred_022_paper_requires_human_approval():
    registry = PredictionModelRegistry()
    record = make_record()
    registry.register(record)
    walk_to(registry, record.model_id, record.model_version,
            ModelLifecycleState.HUMAN_REVIEW)
    with pytest.raises(RegistryError, match="HUMAN approval"):
        registry.transition(record.model_id, record.model_version,
                            ModelLifecycleState.PAPER)


def test_t_pred_022_duplicate_identity_rejected():
    registry = PredictionModelRegistry()
    registry.register(make_record())
    with pytest.raises(RegistryError, match="duplicate"):
        registry.register(make_record())


def test_t_pred_022_illegal_transition_rejected():
    registry = PredictionModelRegistry()
    record = make_record()
    registry.register(record)
    with pytest.raises(RegistryError, match="illegal lifecycle"):
        registry.transition(record.model_id, record.model_version,
                            ModelLifecycleState.PAPER)


def test_t_pred_022_initial_state_must_be_discover():
    record = make_record()
    premature = record.model_copy(
        update={"status": ModelLifecycleState.TRAIN}
    )
    with pytest.raises(RegistryError, match="DISCOVER"):
        PredictionModelRegistry().register(premature)


# ─── T-PRED-023: self-approval rejection ───


def test_t_pred_023_ai_approver_is_structurally_rejected():
    registry = PredictionModelRegistry()
    record = make_record()
    registry.register(record)
    walk_to(registry, record.model_id, record.model_version,
            ModelLifecycleState.HUMAN_REVIEW)
    before = registry.get(record.model_id, record.model_version)
    decision = registry.submit_approval(
        record.model_id, record.model_version, "agent://hermes",
        approver_kind="ai",
    )
    assert decision.accepted is False
    assert "self-approval" in decision.reason
    after = registry.get(record.model_id, record.model_version)
    assert after.status is ModelLifecycleState.HUMAN_REVIEW  # unchanged
    assert any("APPROVAL_REJECTED" in n for n in after.notes)
    # and PAPER still cannot be entered
    with pytest.raises(RegistryError, match="HUMAN approval"):
        registry.transition(record.model_id, record.model_version,
                            ModelLifecycleState.PAPER)


# ─── T-PRED-024: artifact tampering ───


def test_t_pred_024_model_hash_detects_parameter_tampering():
    X = [(float(i), 1.0) for i in range(-10, 10)]
    y = [0] * 10 + [1] * 10
    model = LogisticCrashModel(["x0", "x1"]).fit(X, y)
    trusted_hash = model.model_hash
    # Train on different data -> different parameters -> different hash
    tampered = LogisticCrashModel(["x0", "x1"]).fit(
        X, list(reversed(y))
    )
    assert tampered.model_hash != trusted_hash
    # Same data again -> the trusted hash is reproducible
    refit = LogisticCrashModel(["x0", "x1"]).fit(X, y)
    assert refit.model_hash == trusted_hash


def test_t_pred_024_gate_blocks_on_artifact_hash_mismatch():
    result = evaluate_prediction_gates(
        PredictionGateInput(
            model_artifact_hash_match=False,
            training_samples=100,
            history_bars=1300,
            horizon_bars=20,
        )
    )
    assert result.allowed is False
    assert result.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH


def test_t_pred_024_baseline_artifacts_are_hashed():
    model = BaseRateBaseline().fit([[0.0]] * 10, [0] * 9 + [1])
    assert model.model_hash.startswith("predm.")


# ─── T-PRED-019: outcome ledger ───


def make_outcome(forecast=0.3, actual=True, prediction_id="pred.0" * 8):
    return OutcomeRecord(
        prediction_id=prediction_id,
        model_id="LOGISTIC-CRASH",
        model_version="1",
        forecast=forecast,
        actual=actual,
        horizon_bars=20,
        regime="NORMAL",
        confidence="calibrated",
        evidence_score=0.7,
        calibration_version="platt-v1",
        outcome_timestamp="2021-01-01T00:00:00+00:00",
    )


def test_t_pred_019_ledger_appends_and_verifies():
    ledger = PredictionOutcomeLedger()
    ledger.append(make_outcome(0.3, True, "pred." + "1" * 64))
    ledger.append(make_outcome(0.8, False, "pred." + "2" * 64))
    ledger.append(make_outcome(0.6, True, "pred." + "3" * 64))
    assert len(ledger.entries) == 3
    assert ledger.verify() is True
    assert ledger.entries[0].record_hash != ledger.entries[1].record_hash
    assert ledger.entries[1].prev_record_hash == ledger.entries[0].record_hash


def test_t_pred_019_tampering_breaks_verification():
    ledger = PredictionOutcomeLedger()
    ledger.append(make_outcome(0.3, True, "pred." + "1" * 64))
    ledger.append(make_outcome(0.8, False, "pred." + "2" * 64))
    # Deep tamper: rewrite the first record's forecast behind the frozen
    # model's back (bypassing the public API the only way possible).
    entries = list(ledger.entries)
    entries[0] = entries[0].model_copy(
        update={"record": entries[0].record.model_copy(update={"forecast": 0.99})}
    )
    object.__setattr__(ledger, "_entries", entries)
    assert ledger.verify() is False


def test_t_pred_019_records_are_immutable():
    record = make_outcome()
    with pytest.raises(ValueError):
        record.forecast = 0.5  # type: ignore[misc]


def test_t_pred_019_summary_computes_learning_metrics():
    ledger = PredictionOutcomeLedger()
    ledger.append(make_outcome(0.9, True, "pred." + "1" * 64))
    ledger.append(make_outcome(0.1, False, "pred." + "2" * 64))
    ledger.append(make_outcome(0.5, None, "pred." + "3" * 64))  # unknown yet
    summary = ledger.summary()
    assert summary.n_records == 3
    assert summary.n_known_outcomes == 2
    assert summary.brier == pytest.approx((0.01 + 0.01) / 2)
    assert summary.hit_rate == pytest.approx(1.0)
    unknown = PredictionOutcomeLedger().summary()
    assert unknown.brier is None


def test_t_pred_019_out_of_range_forecast_rejected():
    with pytest.raises(ValueError):
        make_outcome(forecast=1.5)
