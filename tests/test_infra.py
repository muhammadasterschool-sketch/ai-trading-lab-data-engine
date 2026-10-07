"""Phase 10 acceptance tests — reproducibility, observability, recovery.

Blueprint 5.47-5.50 invariants:

- IN-01  deterministic runner: reproducible function verifies; hidden
          randomness raises (fail closed)
- IN-02  metrics: phantom series forbidden; labeled determinism;
          snapshot hash stable
- IN-03  structured log: append-only hash chain verifies
- IN-04  monitoring: health checks feed alerts; duplicate
          suppression; healthy clears alerts
- IN-05  checkpoints: save/restore round-trip; tamper fails closed
"""

import random

import pytest

from data_engine.infra import (
    ReproducibilityError,
    DeterministicRunner,
    ReproducibilityVerifier,
    MetricsRegistry,
    StructuredLog,
    HealthStatus,
    HealthCheck,
    AlertManager,
    Monitor,
    CheckpointManager,
    RecoveryManager,
)


class TestReproducibility:

    def test_in_01_reproducible_and_not(self):
        runner = DeterministicRunner(runs=4)
        ok = runner.run(lambda: {"a": 1, "b": [1.5, 2.5]})
        assert ok.reproducible
        assert ok.distinct_output_hashes == 1
        assert ok.result_hash.startswith("rep10.")

        verifier = ReproducibilityVerifier(runner)
        assert verifier.verify(lambda: 42).reproducible

        rng = random.Random(1234)
        with pytest.raises(ReproducibilityError, match="non-deterministic"):
            verifier.verify(lambda: rng.random())

    def test_in_01b_runs_validation(self):
        with pytest.raises(ReproducibilityError):
            DeterministicRunner(runs=0)


class TestObservability:

    def test_in_02_metrics_registry(self):
        metrics = MetricsRegistry()
        metrics.register_counter("orders_routed")
        metrics.register_counter("orders_routed", labels={"venue": "sim"})
        metrics.register_gauge("equity")
        metrics.increment("orders_routed", 3)
        metrics.increment("orders_routed", 2, labels={"venue": "sim"})
        with pytest.raises(ValueError, match="not registered"):
            metrics.increment("orders_routed", 1, labels={"venue": "x"})
        with pytest.raises(ValueError, match="phantom"):
            metrics.increment("never_registered")
        metrics.set_gauge("equity", 100000.0)
        snap = metrics.snapshot()
        assert snap["counters"]["orders_routed|{}"] == 3
        assert snap["counters"]["orders_routed|{'venue': 'sim'}"] == 2
        assert metrics.snapshot_hash.startswith("obs10.")
        twin = MetricsRegistry()
        twin.register_counter("orders_routed")
        twin.register_counter("orders_routed", labels={"venue": "sim"})
        twin.register_gauge("equity")
        twin.increment("orders_routed", 3)
        twin.increment("orders_routed", 2, labels={"venue": "sim"})
        twin.set_gauge("equity", 100000.0)
        assert metrics.snapshot_hash == twin.snapshot_hash

    def test_in_03_structured_log_chain(self):
        log = StructuredLog()
        log.append("INFO", "engine started", {"phase": "4A.2"})
        log.append("WARN", "late data", {"source": "x"})
        log.append("ERROR", "gate refused", {})
        assert len(log) == 3
        assert log.verify()
        # Chain is tamper-evident: mutating an entry breaks verification
        log._entries[1] = log._entries[1].model_copy(
            update={"message": "TAMPERED"}
        )
        assert not log.verify()


class TestMonitoring:

    def test_in_04_alerts(self):
        manager = AlertManager()
        first = manager.observe("data-feed", HealthStatus.UNHEALTHY)
        assert first is not None and first.status == HealthStatus.UNHEALTHY
        dup = manager.observe("data-feed", HealthStatus.UNHEALTHY)
        assert dup is None  # suppressed
        assert len(manager) == 1
        other = manager.observe("risk-engine", HealthStatus.DEGRADED)
        assert other is not None
        assert len(manager) == 2
        cleared = manager.observe("data-feed", HealthStatus.HEALTHY)
        assert cleared is not None
        assert len(manager) == 1  # risk-engine still active

    def test_in_04b_monitor_poll(self):
        monitor = Monitor()
        state = {"feed": HealthStatus.HEALTHY}

        monitor.register(HealthCheck("feed", lambda: state["feed"]))
        statuses = monitor.poll()
        assert statuses == {"feed": HealthStatus.HEALTHY}
        assert len(monitor.alert_manager) == 0
        state["feed"] = HealthStatus.UNHEALTHY
        statuses = monitor.poll()
        assert len(monitor.alert_manager) == 1
        with pytest.raises(ValueError, match="duplicate health check"):
            monitor.register(HealthCheck("feed", lambda: "x"))


class TestRecovery:

    def test_in_05_checkpoints(self):
        manager = CheckpointManager()
        manager.save("cp-1", {"positions": {"AAA": 10}, "equity": 1000})
        restored = manager.restore("cp-1")
        assert restored == {"positions": {"AAA": 10}, "equity": 1000}

        recovery = RecoveryManager(manager)
        assert recovery.recover("cp-1")["equity"] == 1000

        with pytest.raises(ValueError, match="already exists"):
            manager.save("cp-1", {"x": 1})
        with pytest.raises(ValueError, match="not found"):
            manager.restore("ghost")

    def test_in_05b_checkpoint_tamper_fails_closed(self):
        manager = CheckpointManager()
        cp = manager.save("cp-1", {"equity": 1000})
        # Tamper with the stored state
        manager._checkpoints["cp-1"] = cp.model_copy(
            update={"state": {"equity": 999999}}
        )
        with pytest.raises(ValueError, match="tamper detected"):
            manager.restore("cp-1")
