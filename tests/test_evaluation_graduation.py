"""Governance-boundary acceptance tests — evaluation, graduation, live gate.

Blueprint 5.56-5.59 invariants:

- EV-01  30-day rule: 29-day window -> INCOMPLETE even with all
          criteria passing; 30-day -> COMPLETE
- EV-02  criteria failures and missing NO-TRADE verification ->
          INCOMPLETE (fail closed)
- GV-01  no self-graduation: passing evaluation WITHOUT a human
          token -> not graduated
- GV-02  machine principals cannot issue tokens (registry gate)
- GV-03  graduation with a valid human token succeeds; decision
          hashes deterministic
- RV-01  retirement requires evidence AND human authorization
- LB-01  the live boundary DENIES by default (no evidence)
- LB-02  even with evaluation + graduation + attestation, missing
          the human live-boundary token -> DENIED
- LB-03  the full chain (token + evaluation + graduation + attest)
          grants — proving the gate is a functioning gate, not a
          brick; the security lies in the token being human-only
"""

from datetime import datetime, timedelta, UTC

import pytest

from data_engine.paper.evaluation import (
    EvaluationStatus,
    ReadinessCriterion,
    EvaluationFramework,
    ReadinessChecker,
    HumanAuthorizationRegistry,
    GraduationEvaluator,
    RetirementEvaluator,
    LiveAuthorizationGate,
    EvaluationError,
    GraduationError,
)


def utc(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


PASSING = (
    ReadinessCriterion(
        criterion_id="max_drawdown", description="drawdown ok",
        passed=True, measured_value="0.12 <= 0.2",
    ),
    ReadinessCriterion(
        criterion_id="reconciliation", description="reconciled",
        passed=True, measured_value="True",
    ),
)


def evaluate_window(days, criteria=PASSING, no_trade=True):
    framework = EvaluationFramework()
    start = utc(2026, 8, 1)
    return framework.evaluate(
        strategy_id="strat-A",
        window_start=start,
        window_end=start + timedelta(days=days),
        criteria=criteria,
        no_trade_verified=no_trade,
    )


class TestEvaluation:

    def test_ev_01_thirty_day_rule(self):
        short = evaluate_window(29)
        assert short.status is EvaluationStatus.INCOMPLETE
        full = evaluate_window(30)
        assert full.status is EvaluationStatus.COMPLETE
        assert full.evaluation_hash.startswith("eval11.")

    def test_ev_02_fail_closed(self):
        failing = (
            ReadinessCriterion(
                criterion_id="max_drawdown", description="drawdown",
                passed=False, measured_value="0.45 > 0.2",
            ),
        )
        assert evaluate_window(30, criteria=failing).status \
            is EvaluationStatus.INCOMPLETE
        assert evaluate_window(30, no_trade=False).status \
            is EvaluationStatus.INCOMPLETE
        with pytest.raises(EvaluationError, match="without criteria"):
            evaluate_window(30, criteria=())

    def test_ev_02b_readiness_checker(self):
        criterion = ReadinessChecker.max_drawdown_criterion(0.12)
        assert criterion.passed
        assert not ReadinessChecker.max_drawdown_criterion(0.45).passed
        assert ReadinessChecker.reconciliation_criterion(True).passed
        assert not ReadinessChecker.reproducibility_criterion(False).passed


class TestGraduation:

    def _registry(self):
        return HumanAuthorizationRegistry(human_principals={"operator-1"})

    def test_gv_01_no_self_graduation(self):
        registry = self._registry()
        evaluator = GraduationEvaluator(registry)
        # A token issued for a DIFFERENT purpose cannot graduate
        wrong_purpose = registry.issue(
            "operator-1", purpose="retirement", statement="retire strat-B"
        )
        evaluation = evaluate_window(30)
        decision = evaluator.evaluate(evaluation, wrong_purpose)
        assert not decision.graduated
        assert "human authorization" in decision.rationale

    def test_gv_02_machine_principals_refused(self):
        registry = self._registry()
        with pytest.raises(GraduationError, match="not a registered HUMAN"):
            registry.issue(
                "zai-agent", purpose="graduation", statement="self approve"
            )
        # Empty registry authorizes NOTHING
        empty = HumanAuthorizationRegistry()
        with pytest.raises(GraduationError):
            empty.issue("operator-1", purpose="graduation", statement="x")

    def test_gv_03_graduation_with_token(self):
        registry = self._registry()
        evaluator = GraduationEvaluator(registry)
        token = registry.issue(
            "operator-1", purpose="graduation",
            statement="approve strat-A graduation after review",
        )
        evaluation = evaluate_window(30)
        decision = evaluator.evaluate(evaluation, token)
        assert decision.graduated
        assert decision.decision_hash.startswith("grad11.")
        twin = evaluator.evaluate(evaluation, token)
        assert decision.decision_hash == twin.decision_hash
        # Incomplete evaluation never graduates even WITH a token
        short_decision = evaluator.evaluate(evaluate_window(20), token)
        assert not short_decision.graduated


class TestRetirement:

    def test_rv_01_retirement_rules(self):
        registry = HumanAuthorizationRegistry(human_principals={"operator-1"})
        evaluator = RetirementEvaluator(registry)
        with pytest.raises(GraduationError, match="without documented evidence"):
            evaluator.evaluate("strat-B", [], None)
        token = registry.issue(
            "operator-1", purpose="retirement", statement="retire strat-B"
        )
        decision = evaluator.evaluate(
            "strat-B", ["sharpe collapse -2.1 over 30d"], token
        )
        assert decision.retired
        assert decision.decision_hash.startswith("ret11.")


class TestLiveBoundary:

    def _full_chain(self):
        registry = HumanAuthorizationRegistry(
            human_principals={"operator-1"}
        )
        graduation_token = registry.issue(
            "operator-1", purpose="graduation", statement="approve strat-A"
        )
        evaluator = GraduationEvaluator(registry)
        evaluation = evaluate_window(30)
        graduation = evaluator.evaluate(evaluation, graduation_token)
        live_token = registry.issue(
            "operator-1", purpose="live_boundary",
            statement="authorize live execution for strat-A",
        )
        return registry, evaluation, graduation, live_token

    def test_lb_01_default_denial(self):
        gate = LiveAuthorizationGate(HumanAuthorizationRegistry())
        decision = gate.default_decision()
        assert not decision.granted
        assert decision.decision == "DENIED"
        assert decision.decision_hash.startswith("live11.")
        assert any("blueprint" in r for r in decision.reasons)

    def test_lb_02_missing_token_still_denied(self):
        """LB-02: evaluation + graduation + attestation but NO token."""
        registry, evaluation, graduation, _ = self._full_chain()
        gate = LiveAuthorizationGate(registry)
        decision = gate.evaluate_request(
            authorization=None,
            evaluation=evaluation,
            graduation=graduation,
            production_infra_attested=True,
        )
        assert not decision.granted
        assert any("human authorization" in r for r in decision.reasons)

    def test_lb_03_full_chain_grants(self):
        """LB-03: the gate is functional — human token is the key."""
        registry, evaluation, graduation, live_token = self._full_chain()
        gate = LiveAuthorizationGate(registry)
        decision = gate.evaluate_request(
            authorization=live_token,
            evaluation=evaluation,
            graduation=graduation,
            production_infra_attested=True,
        )
        assert decision.granted
        assert decision.reasons == ()

    def test_lb_03b_wrong_purpose_token_denied(self):
        registry, evaluation, graduation, _ = self._full_chain()
        graduation_token = registry.issue(
            "operator-1", purpose="graduation",
            statement="another approval",
        )
        gate = LiveAuthorizationGate(registry)
        decision = gate.evaluate_request(
            authorization=graduation_token,  # wrong purpose
            evaluation=evaluation,
            graduation=graduation,
            production_infra_attested=True,
        )
        assert not decision.granted
