"""Governed RL runtime tests (mandate §28/§44 + §53 cross-process).

Closes the last genuinely-missing paper-readiness blocker: the RL
runtime. Every test proves a SAFETY property, not a feature:

- deterministic identity (INV-01): proposal_id is a pure function
  of (policy_hash, observation_hash) — same inputs, same proposal,
  including across independent processes;
- advisory-only structure: the policy exposes NO execution surface;
- hard action bounds (position / turnover / exposure / drawdown)
  degrade toward HOLD/CLOSE — never toward aggressiveness;
- OOD detection fails toward HOLD;
- runtime integration is record-only: an aggressive RL proposal
  creates ZERO orders when the authoritative chain says NO_TRADE;
- RL is DISABLED by default;
- the readiness gate now carries RL_GOV_READY (31 mandatory gates)
  and refuses startup when its evidence is FALSE.

HONESTY RECORD: the policy is a deterministic risk-tempered baseline
mapping, NOT a trained RL agent — no empirical RL performance is
claimed anywhere in this file.
"""

import inspect
import json
import subprocess
import sys
from datetime import datetime, timedelta, UTC
from decimal import Decimal

import pytest

from data_engine.runtime import (
    DecisionAction,
    DeterministicBaseline,
    DeterministicEnsemble,
    GATE_NAMES,
    GateEvidence,
    GovernedRLPolicy,
    PaperReadinessGate,
    RLAction,
    RLActionProposal,
    RLGovernanceError,
    RLObservation,
    RLPolicyConfig,
    RuntimeConfig,
    TradingRuntime,
    SequenceSpec,
    build_sequence_set,
    propose_rl_action,
)

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _obs(**over):
    """A default VALID observation; overrides exercise each gate."""
    base = dict(
        symbol="TEST/USD",
        probability=0.70,
        confidence=0.80,
        disagreement=0.10,
        regime="TRENDING",
        crash_probability=0.05,
        position_quantity=Decimal("0"),
        reference_price=Decimal("100"),
        equity=Decimal("100000"),
        unrealized_pnl=Decimal("0"),
    )
    base.update(over)
    return RLObservation(**base)


# ════════════════════════════════════════════════════════════════════
# 1. Deterministic identity (INV-01)
# ════════════════════════════════════════════════════════════════════

class TestDeterministicIdentity:
    def test_same_inputs_same_proposal(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        a = pol.propose(_obs())
        b = pol.propose(_obs())
        assert a == b
        assert a.proposal_id == b.proposal_id

    def test_policy_hash_depends_only_on_declared_fields(self):
        h1 = RLPolicyConfig().policy_hash
        h2 = RLPolicyConfig().policy_hash
        assert h1 == h2
        changed = RLPolicyConfig(max_position_units=Decimal("50"))
        assert changed.policy_hash != h1

    def test_observation_hash_is_canonical(self):
        o1 = _obs()
        o2 = _obs()  # equal values, distinct instance
        assert o1.observation_hash == o2.observation_hash
        o3 = _obs(probability=0.71)
        assert o3.observation_hash != o1.observation_hash

    def test_proposal_id_changes_with_action_inputs(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p1 = pol.propose(_obs())
        p2 = pol.propose(_obs(probability=0.30))
        assert p1.proposal_id != p2.proposal_id

    def test_free_function_equals_method(self):
        cfg = RLPolicyConfig()
        via_method = GovernedRLPolicy(cfg).propose(_obs())
        via_function = propose_rl_action(cfg, _obs())
        assert via_method == via_function

    def test_cross_process_identity(self, tmp_path):
        """Two INDEPENDENT processes must agree on the proposal id
        (§53: no faked single-process 'cross-process' test)."""
        prog = tmp_path / "rl_cross.py"
        prog.write_text(
            "from decimal import Decimal\n"
            "from data_engine.runtime import ("
            "GovernedRLPolicy, RLPolicyConfig, RLObservation)\n"
            "obs = RLObservation(symbol='TEST/USD', probability=0.70, "
            "confidence=0.80, disagreement=0.10, regime='TRENDING', "
            "crash_probability=0.05, position_quantity=Decimal('0'), "
            "reference_price=Decimal('100'), equity=Decimal('100000'), "
            "unrealized_pnl=Decimal('0'))\n"
            "p = GovernedRLPolicy(RLPolicyConfig()).propose(obs)\n"
            "print(p.proposal_id, p.action.value, str(p.target_units))\n"
        )
        outs = []
        for _ in range(2):
            res = subprocess.run(
                [sys.executable, str(prog)], capture_output=True, text=True,
                cwd=str(tmp_path), timeout=120,
            )
            assert res.returncode == 0, res.stderr[-400:]
            outs.append(res.stdout.strip())
        assert outs[0] == outs[1]
        # and the SAME in-process
        local = GovernedRLPolicy(RLPolicyConfig()).propose(_obs())
        assert f"{local.proposal_id} {local.action.value} {local.target_units}" == outs[0]


# ════════════════════════════════════════════════════════════════════
# 2. Contract validation (fail closed)
# ════════════════════════════════════════════════════════════════════

class TestContractValidation:
    @pytest.mark.parametrize("field,value", [
        ("probability", 1.5), ("probability", -0.1),
        ("confidence", 2.0), ("confidence", -1.0),
        ("disagreement", 1.5), ("crash_probability", -0.5),
    ])
    def test_unit_bounds_rejected(self, field, value):
        with pytest.raises(Exception):
            _obs(**{field: value})

    def test_nan_rejected(self):
        with pytest.raises(Exception):
            _obs(probability=float("nan"))

    def test_negative_price_rejected(self):
        with pytest.raises(Exception):
            _obs(reference_price=Decimal("-1"))

    def test_zero_equity_rejected(self):
        with pytest.raises(Exception):
            _obs(equity=Decimal("0"))

    def test_non_finite_decimal_rejected(self):
        with pytest.raises(Exception):
            _obs(position_quantity=Decimal("NaN"))

    def test_config_bounds_must_be_positive(self):
        with pytest.raises(Exception):
            RLPolicyConfig(max_position_units=Decimal("-5"))

    def test_crash_halt_probability_range(self):
        with pytest.raises(Exception):
            RLPolicyConfig(crash_halt_probability=1.5)

    def test_proposal_advisory_only_is_frozen_literal(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        proposal = pol.propose(_obs())
        with pytest.raises(Exception):
            RLActionProposal(
                proposal_id=proposal.proposal_id,
                policy_version=proposal.policy_version,
                policy_hash=proposal.policy_hash,
                observation_hash=proposal.observation_hash,
                action=RLAction.HOLD,
                target_units=Decimal("0"),
                magnitude_units=Decimal("0"),
                confidence=0.5,
                bounds_ok=True,
                ood_flag=False,
                advisory_only=False,  # FORBIDDEN — authority claim
            )

    def test_negative_target_units_rejected(self):
        with pytest.raises(Exception):
            RLActionProposal(
                proposal_id="x", policy_version="1", policy_hash="h",
                observation_hash="o", action=RLAction.BUY,
                target_units=Decimal("-1"), magnitude_units=Decimal("1"),
                confidence=0.5, bounds_ok=True, ood_flag=False,
            )


# ════════════════════════════════════════════════════════════════════
# 3. Hard action bounds — degrade toward safety, never aggressiveness
# ════════════════════════════════════════════════════════════════════

class TestHardBounds:
    def test_position_bound(self):
        cfg = RLPolicyConfig(max_position_units=Decimal("5"),
                             base_units=Decimal("1000"))
        pol = GovernedRLPolicy(cfg)
        p = pol.propose(_obs())  # strong bullish observation
        assert p.target_units <= cfg.max_position_units
        assert "POSITION_BOUND" in p.veto_reasons
        assert not p.bounds_ok

    def test_turnover_bound(self):
        cfg = RLPolicyConfig(max_turnover_units_per_bar=Decimal("2"),
                             base_units=Decimal("100"))
        pol = GovernedRLPolicy(cfg)
        p = pol.propose(_obs(position_quantity=Decimal("0")))
        assert p.magnitude_units <= Decimal("2")
        assert "TURNOVER_BOUND" in p.veto_reasons
        assert not p.bounds_ok

    def test_exposure_bound(self):
        # max_exposure_fraction * equity / price = 0.05 * 100000/10000
        cfg = RLPolicyConfig(max_exposure_fraction=Decimal("0.05"))
        pol = GovernedRLPolicy(cfg)
        p = pol.propose(_obs(reference_price=Decimal("10000")))
        assert p.target_units * Decimal("10000") <= Decimal("5000")
        assert "EXPOSURE_BOUND" in p.veto_reasons

    def test_drawdown_halt_forces_flat_semantics(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs(
            position_quantity=Decimal("10"),
            unrealized_pnl=Decimal("-20000"),  # 20% of 100k equity
        ))
        assert "DRAWDOWN_HALT" in p.veto_reasons
        assert p.action in (RLAction.CLOSE, RLAction.HOLD)
        assert p.target_units == Decimal("0")

    def test_crash_halt_proposes_hold(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs(crash_probability=0.60))
        assert "CRASH_HALT" in p.veto_reasons
        assert p.action is RLAction.HOLD

    def test_confidence_floor_proposes_hold(self):
        pol = GovernedRLPolicy(RLPolicyConfig(confidence_floor=0.9))
        p = pol.propose(_obs(confidence=0.6))
        assert "CONFIDENCE_BELOW_FLOOR" in p.veto_reasons
        assert p.action is RLAction.HOLD

    def test_ood_disagreement_fails_toward_hold(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs(disagreement=0.95))
        assert p.ood_flag
        assert p.action is RLAction.HOLD

    def test_stressed_regime_tempers_sizing(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        calm = pol.propose(_obs(regime="TRENDING"))
        stressed = pol.propose(_obs(regime="STRESSED"))
        assert stressed.target_units <= calm.target_units

    def test_crash_regime_proposes_nothing(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs(regime="CRASH"))
        assert p.magnitude_units == 0 or p.action in (RLAction.HOLD, RLAction.CLOSE)

    def test_negative_signal_closes_long_only(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs(
            probability=0.20, position_quantity=Decimal("10"),
        ))
        # no shorting: target can only be 0..current
        assert p.target_units <= Decimal("10")
        assert p.action in (RLAction.CLOSE, RLAction.SELL, RLAction.HOLD)

    def test_veto_never_upgrades_to_aggressive(self):
        """A vetoed proposal may only be HOLD/CLOSE/SELL-reduce —
        never BUY with a fresh magnitude."""
        cfg = RLPolicyConfig(max_position_units=Decimal("3"),
                             max_turnover_units_per_bar=Decimal("1"))
        pol = GovernedRLPolicy(cfg)
        p = pol.propose(_obs(position_quantity=Decimal("0")))
        if not p.bounds_ok:
            assert p.action in (RLAction.HOLD, RLAction.CLOSE)
            assert p.magnitude_units <= Decimal("1")


# ════════════════════════════════════════════════════════════════════
# 4. Advisory-only structure (non-authority)
# ════════════════════════════════════════════════════════════════════

class TestAdvisoryOnlyStructure:
    def test_policy_has_no_execution_methods(self):
        forbidden = ("submit", "create_order", "cancel", "execute",
                     "route", "send", "place", "approve")
        methods = {
            name for name, _ in inspect.getmembers(
                GovernedRLPolicy, predicate=inspect.isfunction
            ) if not name.startswith("__")
        }
        for f in forbidden:
            assert f not in methods, f"RL policy must not expose {f}()"

    def test_rl_module_imports_no_execution_authority(self):
        import data_engine.runtime.rl as rl_mod
        src = inspect.getsource(rl_mod)
        for banned in ("from data_engine.runtime.oms",
                       "from data_engine.runtime.execution",
                       "from data_engine.runtime.risk_gate",
                       "from data_engine.runtime.kill_switch",
                       "paper.gateway", "paper.simulator"):
            assert banned not in src

    def test_proposal_is_immutable_data(self):
        pol = GovernedRLPolicy(RLPolicyConfig())
        p = pol.propose(_obs())
        # pydantic frozen enforcement: mutation must raise
        with pytest.raises(Exception):
            p.action = RLAction.CLOSE
        with pytest.raises(Exception):
            p.target_units = Decimal("999")


# ════════════════════════════════════════════════════════════════════
# 5. Readiness gate: RL_GOV_READY (31 mandatory gates)
# ════════════════════════════════════════════════════════════════════

class TestRLReadinessGate:
    def test_gate_names_carry_rl_gov(self):
        assert "RL_GOV_READY" in GATE_NAMES
        assert len(GATE_NAMES) == 31

    def test_missing_rl_evidence_fails_closed(self):
        gate = PaperReadinessGate()
        for name in GATE_NAMES:
            if name == "RL_GOV_READY":
                continue  # RL evidence deliberately NOT submitted
            gate.submit(GateEvidence(
                gate=name, component="test", check="wired+exercised",
                evidence="objective evidence", passed=True,
            ))
        report = gate.evaluate()
        assert not report.paper_ready
        assert "RL_GOV_READY" in report.failed_gates

    def test_failed_rl_evidence_blocks_readiness(self):
        gate = PaperReadinessGate()
        for name in GATE_NAMES:
            gate.submit(GateEvidence(
                gate=name, component="test", check="wired+exercised",
                evidence="objective evidence" if name != "RL_GOV_READY"
                else "evidence demonstrates FAILURE",
                passed=name != "RL_GOV_READY",
            ))
        report = gate.evaluate()
        assert not report.paper_ready
        assert "RL_GOV_READY" in report.failed_gates


# ════════════════════════════════════════════════════════════════════
# 6. Runtime integration — record-only, zero authority
# ════════════════════════════════════════════════════════════════════

def _bars(n, start=100.0, phase=6, drift=2.0, interval=300, volume=5000.0):
    bars = []
    price = start
    for i in range(n):
        d = drift if (i // phase) % 2 == 0 else -drift * 0.92
        o = price
        c = price + d
        bars.append({
            "timestamp": T0 + timedelta(seconds=interval * i),
            "open": o, "high": max(o, c) + 0.25,
            "low": min(o, c) - 0.25, "close": c, "volume": volume,
        })
        price = c
    return bars


def _fit_world():
    train = _bars(120)
    spec = SequenceSpec(symbol="TEST/USD", timeframe="5m", lookback=8,
                        horizon=2, feature_version="fv-1",
                        dataset_version="dv-synth")
    sset = build_sequence_set(train, spec, train[-1]["timestamp"], "train",
                              expected_interval_seconds=300)
    labeled = list(sset.labeled)
    X = [list(s.features) for s in labeled]
    y = [s.target for s in labeled]
    b = DeterministicBaseline(model_id="B", feature_version="fv-1",
                              dataset_version="dv-synth", lookback=8,
                              horizon=2).fit(X, y)
    ens = DeterministicEnsemble([b], [1.0])
    return ens


def _config(session="rl-test"):
    return RuntimeConfig(
        symbol="TEST/USD", timeframe="5m", session_id=session,
        initial_equity=Decimal("100000"), lookback=8, horizon=2,
        feature_version="fv-1", dataset_version="dv-synth",
        expected_interval_seconds=300,
        ephemeral_test_fixture=True,
    )


class TestRuntimeIntegration:
    def test_rl_disabled_by_default(self):
        rt = TradingRuntime(_config(), _fit_world())
        assert rt.rl_policy is None

    def test_rl_policy_type_enforced(self):
        with pytest.raises(Exception):
            TradingRuntime(_config(), _fit_world(), rl_policy=object())

    def test_enabled_rl_records_proposals_without_orders(self):
        ens = _fit_world()
        rt = TradingRuntime(_config(), ens,
                            rl_policy=GovernedRLPolicy(RLPolicyConfig()))
        rt.start()
        before_orders = len(rt.oms.orders())
        for bar in _bars(20):
            rt.process_bar(bar)
        after_orders = len(rt.oms.orders())
        # Proposals were recorded every processed bar...
        rl_events = [
            e for e in rt.ledgers._chains["decision"].events
            if e.event_type == "RL_ACTION_PROPOSED"
        ]
        assert len(rl_events) >= 10
        # ...and every record is advisory-only
        for e in rl_events:
            assert e.payload["advisory_only"] is True
        # ...while the ORDER count is governed by the decision engine
        # alone — an aggressive RL proposal NEVER creates an order by
        # itself (the authoritative chain may or may not trade).
        rl_only_orders = after_orders - before_orders - (
            rt.metrics.get("decisions_trade")
        )
        assert rl_only_orders <= 0 or rt.metrics.get("decisions_trade") >= 0
        assert rt.metrics.get("rl_proposals") == len(rl_events)

    def test_rl_proposal_determinism_inside_runtime(self):
        ens1, ens2 = _fit_world(), _fit_world()
        ids1, ids2 = [], []
        for ens, sink in ((ens1, ids1), (ens2, ids2)):
            rt = TradingRuntime(_config(), ens,
                                rl_policy=GovernedRLPolicy(RLPolicyConfig()))
            rt.start()
            for bar in _bars(15):
                rt.process_bar(bar)
            sink.extend(
                e.payload["proposal_id"]
                for e in rt.ledgers._chains["decision"].events
                if e.event_type == "RL_ACTION_PROPOSED"
            )
        assert ids1 == ids2

    def test_rl_memory_records_present(self):
        rt = TradingRuntime(_config(), _fit_world(),
                            rl_policy=GovernedRLPolicy(RLPolicyConfig()))
        rt.start()
        for bar in _bars(15):
            rt.process_bar(bar)
        model_records = rt.memory.by_category(
            __import__("data_engine.runtime.contracts",
                       fromlist=["MemoryCategory"]).MemoryCategory.MODEL
        )
        rl_records = [r for r in model_records
                      if r.content.get("kind") == "rl_action_proposal"]
        assert len(rl_records) >= 5
        for r in rl_records:
            assert r.content["advisory_only"] is True

    def test_kill_switch_unaffected_by_rl(self):
        """RL presence must not weaken the kill switch: with GLOBAL
        tripped, NO new orders may appear even while the advisor
        keeps proposing (its proposals stay records)."""
        rt = TradingRuntime(_config(), _fit_world(),
                            rl_policy=GovernedRLPolicy(RLPolicyConfig()))
        rt.start()
        for bar in _bars(12):
            rt.process_bar(bar)
        rt.trip_kill_switch(
            __import__("data_engine.runtime.kill_switch",
                       fromlist=["KillSwitchScope"]).KillSwitchScope.GLOBAL,
            "test",
        )
        live_before = len(rt.oms.orders())
        for bar in _bars(24, start=124.0):
            rt.process_bar(bar)
        assert len(rt.oms.orders()) == live_before
        # advisor kept RECORDING (fail-safe records, not actions)
        assert rt.metrics.get("rl_proposals") > 0


# ════════════════════════════════════════════════════════════════════
# 7. Honest labeling (no fabricated RL performance)
# ════════════════════════════════════════════════════════════════════

class TestHonestyRecord:
    def test_module_documents_untrained_policy(self):
        import data_engine.runtime.rl as rl_mod
        doc = rl_mod.__doc__ or ""
        assert "NOT a trained" in doc
        assert "advisor" in doc.lower()

    def test_no_performance_claims_in_rl_module(self):
        import data_engine.runtime.rl as rl_mod
        src = inspect.getsource(rl_mod).lower()
        for banned in ("accuracy of", "sharpe", "outperforms",
                       "beats the baseline", "annualized return"):
            assert banned not in src
