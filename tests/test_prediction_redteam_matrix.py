"""Prediction Intelligence closure tests — the adversarial red-team
matrix (PRED-F2).

The matrix itself lives in ``data_engine.prediction.redteam`` and is
EXECUTED there against live components. These tests:

- run the full matrix and assert every attack was defended
- assert the mandated field set on every attack record
- assert category coverage (6 categories, 45 attacks)
- assert determinism across repeated runs
- assert a synthetic FAIL is detectable (self-test of the harness)
"""

import pytest

from data_engine.prediction.redteam import (
    AttackVerdict,
    RedTeamAttack,
    RedTeamMatrix,
    run_redteam_matrix,
)


class TestRedTeamMatrix:

    @pytest.fixture(scope="module")
    def matrix(self) -> RedTeamMatrix:
        return run_redteam_matrix()

    def test_every_attack_defended(self, matrix):
        assert matrix.failed == (), (
            f"undefended attacks: "
            f"{[(a.attack_id, a.actual_behavior) for a in matrix.failed]}"
        )

    def test_attack_count_and_categories(self, matrix):
        assert len(matrix.attacks) == 45
        categories = {a.category for a in matrix.attacks}
        assert categories == {
            "temporal", "identity", "provenance",
            "data", "model", "crash-intelligence",
        }

    def test_category_counts(self, matrix):
        counts: dict[str, int] = {}
        for a in matrix.attacks:
            counts[a.category] = counts.get(a.category, 0) + 1
        assert counts == {
            "temporal": 8,
            "identity": 8,
            "provenance": 7,
            "data": 8,
            "model": 7,
            "crash-intelligence": 7,
        }

    def test_every_attack_has_mandated_fields(self, matrix):
        for attack in matrix.attacks:
            assert attack.attack_id.startswith("RT-PRED-")
            assert attack.precondition.strip()
            assert attack.input_description.strip()
            assert attack.expected_behavior.strip()
            assert attack.actual_behavior.strip()
            assert attack.evidence.strip()
            assert attack.verdict in (
                AttackVerdict.PASS, AttackVerdict.FAIL
            )

    def test_attack_ids_unique(self, matrix):
        ids = [a.attack_id for a in matrix.attacks]
        assert len(ids) == len(set(ids))

    def test_matrix_deterministic(self):
        m1 = run_redteam_matrix()
        m2 = run_redteam_matrix()
        assert m1.matrix_hash == m2.matrix_hash
        for a1, a2 in zip(m1.attacks, m2.attacks):
            assert a1.attack_id == a2.attack_id
            assert a1.actual_behavior == a2.actual_behavior

    def test_matrix_hash_identity(self, matrix):
        assert matrix.matrix_hash.startswith("preda.")

    def test_summary_reports_counts(self, matrix):
        summary = matrix.summary()
        assert f"attacks: {len(matrix.attacks)}" in summary
        assert "PASS" in summary
        for category in (
            "temporal", "identity", "provenance",
            "data", "model", "crash-intelligence",
        ):
            assert category in summary

    def test_harness_detects_failures_self_test(self):
        """A FAIL verdict must be countable — the harness is not
        hard-wired to green."""
        failing = RedTeamAttack(
            attack_id="RT-PRED-SELF-001",
            category="self-test",
            precondition="harness self-test",
            input_description="synthetic undefended attack",
            expected_behavior="harness counts FAIL verdicts",
            actual_behavior="attack was not defended",
            verdict=AttackVerdict.FAIL,
            evidence="constructed failure",
        )
        m = RedTeamMatrix(attacks=(failing,))
        assert m.passed_count == 0
        assert len(m.failed) == 1
        assert "FAIL  1" in m.summary()

    def test_key_pit_attacks_present(self, matrix):
        ids = {a.attack_id for a in matrix.attacks}
        for expected in (
            "RT-PRED-T-001",  # future timestamp injection
            "RT-PRED-T-003",  # label leakage
            "RT-PRED-T-005",  # revision leakage
            "RT-PRED-I-006",  # unicode normalization ambiguity
            "RT-PRED-P-005",  # forged verification state
            "RT-PRED-M-001",  # stale model
            "RT-PRED-C-001",  # crisis label contamination
            "RT-PRED-C-007",  # scenario presented as forecast
        ):
            assert expected in ids

    def test_failed_attacks_have_reasons(self, matrix):
        """Contract: any FAIL must carry an inspectable actual_behavior
        (evidence discipline) — vacuously true when all pass, and the
        property is asserted for the record."""
        for attack in matrix.attacks:
            if attack.verdict is AttackVerdict.FAIL:
                assert attack.actual_behavior != attack.expected_behavior
