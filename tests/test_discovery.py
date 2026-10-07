"""Strategy discovery + execution eligibility (mandate phases 11/15).

Governance tests: deterministic generation, full candidate metadata,
allowed-to-fail rejection with reasons, NO TRADE default, registry
duplicate protection + tamper evidence, validated-only governance view,
and the fail-closed eligibility chain.
"""

import json

import pytest

from data_engine.discovery import (
    CANDIDATE_HASH_PREFIX,
    CandidateStatus,
    DataDependencies,
    DiscoveryProvenance,
    ExecutionAssumptions,
    ExecutionEligibility,
    ParameterField,
    ParameterSchema,
    RiskAssumptions,
    RuleBasedGenerator,
    RuleTemplate,
    CandidateEvaluator,
    CandidateValidator,
    SignalAction,
    StrategyCandidate,
    ValidationRequirements,
    DiscoveryRegistry,
    DiscoveryRegistryError,
)
from data_engine.strategy.schemas import StrategySpec

HYP = "h" * 64
DATA = "d" * 64


def _template(**overrides) -> RuleTemplate:
    base = dict(
        template_id="ma-cross",
        description="momentum entry above threshold",
        indicator="momentum_14",
        entry_operator=">",
        entry_thresholds=(0.0, 0.25, 0.5),
        exit_indicator="momentum_14",
        exit_operator="<",
        exit_thresholds=(0.0,),
        stop_loss_pcts=(2.0, 4.0),
        take_profit_pcts=(4.0, 8.0),
        min_history_bars=20,
    )
    base.update(overrides)
    return RuleTemplate(**base)


def _generate(template=None, seed=0):
    generator = RuleBasedGenerator([template or _template()])
    return generator.generate(
        hypothesis_hash=HYP,
        dataset_hash=DATA,
        instrument="XAU/USD",
        timeframe="D1",
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Generation determinism and metadata completeness
# ---------------------------------------------------------------------------

class TestDeterministicGeneration:
    def test_generation_is_deterministic_same_seed(self):
        a = _generate(seed=7)
        b = _generate(seed=7)
        assert [c.candidate_hash for c in a] == [c.candidate_hash for c in b]

    def test_generation_is_cross_call_stable(self):
        a = _generate()
        b = _generate()
        assert [c.candidate_id for c in a] == [c.candidate_id for c in b]

    def test_different_seed_different_first_point(self):
        a = _generate(seed=0)
        b = _generate(seed=1)
        assert a[0].candidate_id != b[0].candidate_id
        # Same grid → same spec set; the seed orders and identifies them.
        assert {c.spec_hash for c in a} == {c.spec_hash for c in b}
        assert {c.candidate_hash for c in a} != {c.candidate_hash for c in b}

    def test_grid_size_matches_candidate_count(self):
        template = _template()
        candidates = _generate(template)
        assert len(candidates) == template.grid_size()
        assert len(candidates) == 3 * 1 * 2 * 2

    def test_candidate_hash_format(self):
        candidates = _generate()
        for candidate in candidates:
            assert candidate.candidate_hash.startswith(CANDIDATE_HASH_PREFIX)
            assert len(candidate.candidate_hash) == 7 + 64  # 'disc20.' + hex

    def test_no_wall_clock_in_identity(self):
        # Identity payload contains only the declared allowlist keys.
        candidates = _generate()
        payload = candidates[0].identity_payload
        assert set(payload) == {
            "contract_version",
            "template_id",
            "hypothesis_hash",
            "dataset_hash",
            "seed",
            "spec_hash",
        }

    def test_grid_bound_is_fail_closed(self):
        huge = _template(
            entry_thresholds=tuple(float(i) for i in range(10)),
            stop_loss_pcts=tuple(float(i) for i in range(1, 10)),
            take_profit_pcts=tuple(float(i) for i in range(10, 20)),
        )
        with pytest.raises(Exception, match="exceeds the bound"):
            _generate(huge)  # 10*1*9*10 = 900 > 64


class TestCandidateMetadata:
    def test_every_candidate_carries_full_metadata(self):
        candidates = _generate()
        for candidate in candidates:
            assert isinstance(candidate.spec, StrategySpec)
            assert candidate.spec.required_indicators == ["momentum_14"]
            assert candidate.parameter_schema.names
            assert candidate.data_dependencies.instrument == "XAU/USD"
            assert candidate.data_dependencies.timeframe == "D1"
            assert candidate.risk_assumptions.max_position_units > 0
            assert candidate.execution_assumptions.execution_semantics
            assert candidate.validation_requirements.min_history_bars == 20
            assert candidate.provenance.generator_id == "rule-based-v1"

    def test_spec_conditions_parse_via_frozen_phase3(self):
        candidates = _generate()
        for candidate in candidates:
            entries = candidate.spec.entry_conditions
            assert len(entries) == 1
            assert entries[0].indicator == "momentum_14"
            assert entries[0].operator == ">"

    def test_exit_conditions_present_when_declared(self):
        candidates = _generate()
        with_exit = [c for c in candidates if c.spec.exit_conditions_serialized]
        assert with_exit  # exit indicator declared → serialized exits exist
        for candidate in with_exit:
            assert candidate.spec.exit_conditions[0].operator == "<"


# ---------------------------------------------------------------------------
# Validation: strategies are allowed to fail
# ---------------------------------------------------------------------------

class TestCandidateValidator:
    def test_valid_candidate_passes(self):
        candidate = _generate()[0]
        validator = CandidateValidator()
        validated = validator.validate(
            candidate,
            available_history_bars=30,
            available_feature_outputs=["momentum_14"],
        )
        assert validated.status is CandidateStatus.VALIDATED
        assert validated.rejection_reason is None

    def test_insufficient_history_rejects_with_reason(self):
        candidate = _generate()[0]
        validator = CandidateValidator()
        rejected = validator.validate(
            candidate,
            available_history_bars=5,
            available_feature_outputs=["momentum_14"],
        )
        assert rejected.status is CandidateStatus.REJECTED
        assert "insufficient history" in rejected.rejection_reason

    def test_missing_feature_dependency_rejects(self):
        candidate = _generate()[0]
        validator = CandidateValidator()
        rejected = validator.validate(
            candidate,
            available_history_bars=30,
            available_feature_outputs=["something_else"],
        )
        assert rejected.status is CandidateStatus.REJECTED
        assert "feature dependencies unavailable" in rejected.rejection_reason

    def test_take_profit_below_stop_rejects(self):
        candidate = _generate(
            _template(stop_loss_pcts=(8.0,), take_profit_pcts=(4.0,))
        )[0]
        validator = CandidateValidator()
        rejected = validator.validate(
            candidate,
            available_history_bars=30,
            available_feature_outputs=["momentum_14"],
        )
        assert rejected.status is CandidateStatus.REJECTED
        assert "take-profit must exceed stop-loss" in rejected.rejection_reason

    def test_only_draft_candidates_enter_validation(self):
        candidate = _generate()[0].with_status(CandidateStatus.VALIDATED)
        with pytest.raises(Exception, match="only DRAFT"):
            CandidateValidator().validate(candidate, available_history_bars=30)


# ---------------------------------------------------------------------------
# Signal evaluation: NO TRADE is the default
# ---------------------------------------------------------------------------

class TestCandidateEvaluator:
    def _validated(self):
        candidate = _generate()[0]
        return CandidateValidator().validate(
            candidate,
            available_history_bars=30,
            available_feature_outputs=["momentum_14"],
        )

    def test_no_trade_is_the_default_outcome(self):
        evaluator = CandidateEvaluator()
        decision = evaluator.evaluate(self._validated(), {"momentum_14": None})
        assert decision.action is SignalAction.NO_TRADE

    def test_unsatisfied_conditions_yield_no_trade(self):
        evaluator = CandidateEvaluator()
        decision = evaluator.evaluate(self._validated(), {"momentum_14": -0.5})
        assert decision.action is SignalAction.NO_TRADE
        assert decision.conditions_missed

    def test_satisfied_conditions_yield_entry(self):
        evaluator = CandidateEvaluator()
        decision = evaluator.evaluate(self._validated(), {"momentum_14": 1.5})
        assert decision.action is SignalAction.ENTRY_LONG
        assert decision.conditions_met
        assert not decision.conditions_missed

    def test_missing_value_yields_no_trade_not_crash(self):
        evaluator = CandidateEvaluator()
        decision = evaluator.evaluate(self._validated(), {})
        assert decision.action is SignalAction.NO_TRADE

    def test_only_validated_candidates_may_evaluate(self):
        evaluator = CandidateEvaluator()
        with pytest.raises(Exception, match="only VALIDATED"):
            evaluator.evaluate(_generate()[0], {"momentum_14": 1.5})


# ---------------------------------------------------------------------------
# Registry governance
# ---------------------------------------------------------------------------

class TestDiscoveryRegistry:
    def _registry_with(self, count=2):
        candidates = _generate()[:count]
        registry = DiscoveryRegistry()
        return registry.register_all(candidates), candidates

    def test_register_returns_new_registry_immutably(self):
        registry, candidates = self._registry_with()
        assert len(registry.records) == 2
        assert registry.get(candidates[0].candidate_id) is not None

    def test_duplicate_candidate_id_rejected(self):
        registry, candidates = self._registry_with(1)
        with pytest.raises(DiscoveryRegistryError, match="duplicate"):
            registry.register(candidates[0])

    def test_same_identity_new_id_also_rejected(self):
        registry, candidates = self._registry_with(1)
        clone = candidates[0].model_copy(
            update={"candidate_id": "different-id"}, deep=True
        )
        with pytest.raises(DiscoveryRegistryError, match="identity"):
            registry.register(clone)

    def test_validated_only_view(self):
        candidates = _generate()[:2]
        validator = CandidateValidator()
        good = validator.validate(
            candidates[0],
            available_history_bars=30,
            available_feature_outputs=["momentum_14"],
        )
        bad = validator.validate(
            candidates[1],
            available_history_bars=1,  # insufficient history
            available_feature_outputs=["momentum_14"],
        )
        registry = DiscoveryRegistry().register_all([good, bad])
        assert len(registry.validated_only()) == 1
        assert len(registry.rejected()) == 1
        assert "insufficient history" in registry.rejected()[0].rejection_reason

    def test_integrity_verification_passes(self):
        registry, _ = self._registry_with()
        registry.verify_integrity()

    def test_integrity_fails_on_tampered_records(self):
        registry, candidates = self._registry_with(1)
        # Rebuild state with a mutated record (simulated tamper).
        from data_engine.discovery.registry import _RegistryState
        tampered_record = candidates[0].with_status(
            CandidateStatus.VALIDATED
        )
        tampered = DiscoveryRegistry(
            _RegistryState(
                records=(tampered_record,),
                chain_hash=registry.chain_hash,
            )
        )
        with pytest.raises(DiscoveryRegistryError, match="chain hash mismatch"):
            tampered.verify_integrity()


# ---------------------------------------------------------------------------
# Execution eligibility chain (mandate Phase 15)
# ---------------------------------------------------------------------------

class TestExecutionEligibility:
    def test_no_evidence_is_pure_no_trade(self):
        decision = ExecutionEligibility().default_decision()
        assert decision.decision == "NO_TRADE"
        assert any("not evaluated" in r for r in decision.reasons)

    def test_full_chain_passes_to_eligible(self):
        decision = ExecutionEligibility().evaluate(
            data_valid=True,
            pit_valid=True,
            strategy_valid=True,
            signal_is_no_trade=False,
            risk_valid=True,
            portfolio_valid=True,
        )
        assert decision.decision == "EXECUTION_ELIGIBLE"
        assert not decision.reasons

    def test_any_single_failure_is_no_trade(self):
        cases = [
            dict(data_valid=False, pit_valid=True, strategy_valid=True,
                 signal_is_no_trade=False, risk_valid=True, portfolio_valid=True),
            dict(data_valid=True, pit_valid=False, strategy_valid=True,
                 signal_is_no_trade=False, risk_valid=True, portfolio_valid=True),
            dict(data_valid=True, pit_valid=True, strategy_valid=False,
                 signal_is_no_trade=False, risk_valid=True, portfolio_valid=True),
            dict(data_valid=True, pit_valid=True, strategy_valid=True,
                 signal_is_no_trade=False, risk_valid=False, portfolio_valid=True),
            dict(data_valid=True, pit_valid=True, strategy_valid=True,
                 signal_is_no_trade=False, risk_valid=True, portfolio_valid=False),
        ]
        for case in cases:
            decision = ExecutionEligibility().evaluate(**case)
            assert decision.decision == "NO_TRADE", case
            assert decision.reasons

    def test_missing_stage_evidence_fails_closed(self):
        decision = ExecutionEligibility().evaluate(
            data_valid=True,
            # pit_valid omitted → None → fail-closed
            strategy_valid=True,
            signal_is_no_trade=False,
            risk_valid=True,
            portfolio_valid=True,
        )
        assert decision.decision == "NO_TRADE"
        assert any("not evaluated" in r for r in decision.reasons)

    def test_no_trade_signal_denies_execution_even_when_valid(self):
        decision = ExecutionEligibility().evaluate(
            data_valid=True,
            pit_valid=True,
            strategy_valid=True,
            signal_is_no_trade=True,  # signal generation says NO TRADE
            risk_valid=True,
            portfolio_valid=True,
        )
        assert decision.decision == "NO_TRADE"
        assert any("signal" in r for r in decision.reasons)

    def test_authorization_stage_is_always_recorded_not_granted(self):
        decision = ExecutionEligibility().evaluate(
            data_valid=True,
            pit_valid=True,
            strategy_valid=True,
            signal_is_no_trade=False,
            risk_valid=True,
            portfolio_valid=True,
        )
        auth = [s for s in decision.stages if s.stage.value == "execution_authorized"]
        assert auth and auth[0].passed is False
        assert "5.59" in auth[0].detail

    def test_decision_hash_is_deterministic(self):
        args = dict(
            data_valid=True, pit_valid=True, strategy_valid=True,
            signal_is_no_trade=False, risk_valid=True, portfolio_valid=True,
        )
        a = ExecutionEligibility().evaluate(**args)
        b = ExecutionEligibility().evaluate(**args)
        assert a.decision_hash == b.decision_hash
        assert a.decision_hash.startswith("elig20.")

    def test_live_authorization_status_constant(self):
        assert (
            ExecutionEligibility.LIVE_AUTHORIZATION_STATUS
            == "NOT_AUTHORIZED"
        )


# ---------------------------------------------------------------------------
# Model contracts
# ---------------------------------------------------------------------------

class TestModelContracts:
    def test_rejected_requires_reason(self):
        candidate = _generate()[0]
        with pytest.raises(Exception, match="reason"):
            candidate.with_status(CandidateStatus.REJECTED, None)

    def test_non_rejected_forbids_reason(self):
        candidate = _generate()[0]
        with pytest.raises(Exception):
            candidate.with_status(
                CandidateStatus.VALIDATED, "some reason"
            )

    def test_empty_candidate_id_rejected(self):
        candidate = _generate()[0]
        with pytest.raises(Exception, match="non-empty"):
            type(candidate).model_validate(
                {**candidate.model_dump(), "candidate_id": "  "}
            )

    def test_grid_must_be_sorted_and_distinct(self):
        with pytest.raises(Exception):
            ParameterField(name="x", type="number", grid=(2.0, 1.0))

    def test_threshold_grids_must_be_sorted(self):
        with pytest.raises(Exception):
            _template(entry_thresholds=(0.5, 0.0))

    def test_generator_requires_hashes(self):
        generator = RuleBasedGenerator([_template()])
        with pytest.raises(Exception, match="verifiable"):
            generator.generate(
                hypothesis_hash="short",
                dataset_hash=DATA,
                instrument="XAU/USD",
                timeframe="D1",
            )

    def test_generator_requires_templates(self):
        with pytest.raises(Exception):
            RuleBasedGenerator([])

    def test_duplicate_template_ids_rejected(self):
        with pytest.raises(Exception, match="unique"):
            RuleBasedGenerator([_template(), _template()])
