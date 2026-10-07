"""Phase 9 acceptance tests — Hermes orchestration.

Blueprint 5.35-5.41 invariants:

- HM-01  unavailable permissions structurally rejected in contracts
          (live trading, blocker closure, frozen modification,
          self-approval)
- HM-02  contract coherence (permission/prohibition overlap rejected);
          may() semantics
- HM-03  deterministic provider: identical prompt -> identical
          response, cross-process; free-first routing
- HM-04  message log: append-only, duplicate rejection, hash-chain
          verification
- HM-05  skills: acceptance criteria AND adversarial tests mandatory;
          undefined skill execution refused
- HM-06  orchestrator: dispatch permitted tasks, audit rejections of
          unknown/underprivileged agents; audit chain tamper-evident
- HM-07  task demanding an unavailable permission refused at
          construction
"""

import subprocess
import sys

import pytest

from data_engine.hermes import (
    ModelAbstractionError,
    ModelRouter,
    DeterministicTestProvider,
    AgentPermission,
    AgentContract,
    AgentContractError,
    AgentMessage,
    MessageLog,
    SkillDefinition,
    SkillExecutor,
    TaskAssignment,
    HermesOrchestrator,
)


class TestAgentContracts:

    def test_hm_01_unavailable_permissions(self):
        """HM-01: no agent can ever hold execution-grade authority."""
        for forbidden in (
            "live_trading_authority",
            "blocker_closure_authority",
            "frozen_contract_modification",
            "self_approval_authority",
        ):
            with pytest.raises(ValueError, match="STRUCTURALLY UNAVAILABLE"):
                AgentContract(
                    agent_id="a-1",
                    role="researcher",
                    permissions=frozenset({forbidden}),
                )
        # may() also refuses unavailable actions even if smuggled in
        contract = AgentContract(
            agent_id="a-1", role="researcher",
            permissions=frozenset({"read_market_data"}),
        )
        assert contract.may("live_trading_authority") is False

    def test_hm_02_coherence_and_may(self):
        with pytest.raises(ValueError, match="incoherent"):
            AgentContract(
                agent_id="a-1", role="r",
                permissions=frozenset({"run_backtest"}),
                prohibitions=frozenset({"run_backtest"}),
            )
        contract = AgentContract(
            agent_id="a-1", role="researcher",
            permissions=frozenset({"run_backtest", "write_research"}),
            prohibitions=frozenset({"write_code"}),
        )
        assert contract.may("run_backtest")
        assert not contract.may("write_code")
        assert not contract.may("read_market_data")  # unlisted
        assert contract.contract_hash.startswith("agent9.")
        twin = AgentContract(
            agent_id="a-1", role="researcher",
            permissions=frozenset({"run_backtest", "write_research"}),
            prohibitions=frozenset({"write_code"}),
        )
        assert contract.contract_hash == twin.contract_hash


class TestModelRouting:

    def test_hm_03_deterministic_provider(self):
        router = ModelRouter(
            (DeterministicTestProvider("free-a"), DeterministicTestProvider("paid-b"))
        )
        r1 = router.complete("analyze momentum")
        r2 = router.complete("analyze momentum")
        assert r1.response_text == r2.response_text
        assert r1.provider_id == "free-a"  # free-first: first registered
        assert r1.response_hash.startswith("her9.")
        explicit = router.complete("analyze momentum", provider_id="paid-b")
        assert explicit.provider_id == "paid-b"
        assert explicit.response_text != r1.response_text
        with pytest.raises(ModelAbstractionError, match="not registered"):
            router.complete("x", provider_id="nope")

    def test_hm_03b_cross_process_determinism(self):
        code = (
            "from data_engine.hermes import DeterministicTestProvider;"
            "p = DeterministicTestProvider('free-a');"
            "print(p.complete('analyze momentum'))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        local = DeterministicTestProvider("free-a").complete("analyze momentum")
        assert proc.stdout.strip() == local

    def test_hm_03c_router_fail_closed(self):
        with pytest.raises(ModelAbstractionError, match="at least one"):
            ModelRouter(())


class TestCommunication:

    def test_hm_04_message_log(self):
        log = MessageLog()
        m1 = AgentMessage(
            message_id="m-1", from_agent="a", to_agent="b",
            payload_hash="1" * 64, content="task update",
        )
        m2 = AgentMessage(
            message_id="m-2", from_agent="b", to_agent="a",
            payload_hash="2" * 64, content="ack",
        )
        log.append(m1)
        log.append(m2)
        assert len(log) == 2
        assert log.verify()
        with pytest.raises(AgentContractError, match="duplicate"):
            log.append(m1)


class TestSkills:

    def test_hm_05_skill_contracts(self):
        with pytest.raises(ValueError, match="acceptance criteria"):
            SkillDefinition(
                skill_id="s", description="d",
                acceptance_criteria=(), adversarial_tests=("t",),
            )
        with pytest.raises(ValueError, match="adversarial tests"):
            SkillDefinition(
                skill_id="s", description="d",
                acceptance_criteria=("c",), adversarial_tests=(),
            )
        executor = SkillExecutor()
        good = SkillDefinition(
            skill_id="add", description="adds two numbers",
            acceptance_criteria=("returns a+b",),
            adversarial_tests=("non-numeric inputs raise",),
        )
        executor.register(good, lambda a, b: a + b)
        assert executor.run("add", 2, 3) == 5
        with pytest.raises(AgentContractError, match="not registered"):
            executor.run("multiply", 2, 3)


class TestOrchestrator:

    def _setup(self):
        orch = HermesOrchestrator()
        orch.register_agent(AgentContract(
            agent_id="researcher-1", role="researcher",
            permissions=frozenset({AgentPermission.READ_MARKET_DATA, AgentPermission.RUN_BACKTEST}),
        ))
        return orch

    def test_hm_06_dispatch_and_rejection(self):
        orch = self._setup()
        ok = TaskAssignment(
            task_id="t-1", agent_id="researcher-1", task_kind="backtest",
            required_permission=AgentPermission.RUN_BACKTEST,
            description="run baseline",
        )
        entry = orch.dispatch(ok)
        assert entry.action == "dispatch"
        underprivileged = TaskAssignment(
            task_id="t-2", agent_id="researcher-1", task_kind="code-change",
            required_permission=AgentPermission.WRITE_CODE,
            description="modify code",
        )
        entry2 = orch.dispatch(underprivileged)
        assert entry2.action == "reject"
        assert "lacks permission" in entry2.detail
        unknown = TaskAssignment(
            task_id="t-3", agent_id="ghost", task_kind="x",
            required_permission=AgentPermission.COMMUNICATE,
            description="haunt",
        )
        entry3 = orch.dispatch(unknown)
        assert entry3.action == "reject"
        assert "unknown agent" in entry3.detail
        assert orch.verify_audit_chain()
        assert ok.assignment_hash.startswith("hermes9.")

    def test_hm_07_unavailable_task_permission_rejected(self):
        with pytest.raises(ValueError, match="unavailable permission"):
            TaskAssignment(
                task_id="t-x", agent_id="researcher-1", task_kind="trade",
                required_permission="live_trading_authority",
                description="trade live",
            )
