"""Phase 5 acceptance tests — experiment registry, reproducibility.

Blueprint 5.16 invariants:

- ER-01  unique deterministic experiment IDs: duplicate identity
          registration rejected
- ER-02  entry hash deterministic (expr5.), tamper-evident reads
- ER-03  reproducibility log: MATCH / MISMATCH / UNVERIFIED verdicts
- ER-04  log immutability: extended() returns a new log; original runs
          tuple unchanged; rlog5. hash deterministic
- ER-05  unregistered experiment: log attachment and reads fail closed
- ER-06  registry status queries (entries_with_status)
"""

from datetime import datetime, UTC

import pytest

from data_engine.experiment_registry import (
    VerificationStatus,
    ExperimentRegistryEntry,
    ReproducibilityRun,
    ReproducibilityLog,
    ExperimentRegistry,
    ExperimentRegistryError,
    EXPERIMENT_REGISTRY_PREFIX,
    REPRODUCIBILITY_PREFIX,
)


def utc(y, m, d):
    return datetime(y, m, d, tzinfo=UTC)


def make_entry(experiment_hash=None, experiment_id="exp-001"):
    return ExperimentRegistryEntry(
        experiment_hash=experiment_hash or ("pit4x." + "a" * 64),
        experiment_id=experiment_id,
        config_hash="cfg-" + "b" * 61,
        registered_by="operator-1",
        registered_at=utc(2026, 10, 1),
        description="momentum baseline",
    )


def make_run(label="run-1", observed=None, expected=None, label_time=1):
    return ReproducibilityRun(
        run_label=label,
        environment_pin={
            "code_version": "0.1.0",
            "quant_version": "1.0.0",
            "backtest_engine_version": "1.0.0",
        },
        input_hash="inp-" + "c" * 61,
        observed_output_hash=observed or ("d" * 64),
        expected_output_hash=expected or ("d" * 64),
        run_at=utc(2026, 10, label_time),
    )


class TestExperimentRegistry:

    def test_er_01_duplicate_identity_rejected(self):
        registry = ExperimentRegistry()
        registry.register(make_entry())
        with pytest.raises(ExperimentRegistryError, match="cannot register twice"):
            registry.register(make_entry())
        # Same identity, different experiment_id — still duplicate
        with pytest.raises(ExperimentRegistryError):
            registry.register(make_entry(experiment_id="exp-002"))
        # Different identity, same experiment_id — also rejected
        with pytest.raises(ExperimentRegistryError, match="already in use"):
            registry.register(
                make_entry(experiment_hash="pit4x." + "e" * 64)
            )

    def test_er_02_entry_hash_deterministic(self):
        e1, e2 = make_entry(), make_entry()
        assert e1.entry_hash == e2.entry_hash
        assert e1.entry_hash.startswith(EXPERIMENT_REGISTRY_PREFIX)
        assert len(e1.entry_hash) == 70  # 6-char prefix + 64 hex

    def test_er_02b_get_tamper_evident(self):
        """ER-02b: stored-hash mismatch fails closed on read."""
        registry = ExperimentRegistry()
        entry = make_entry()
        registry.register(entry)
        # Tamper: replace the stored tuple with a mutated entry
        h = entry.experiment_hash
        registry._entries[h] = (
            ExperimentRegistryEntry(
                experiment_hash=h,
                experiment_id="exp-001",
                config_hash="TAMPERED-" + "x" * 56,
                registered_by="operator-1",
                registered_at=utc(2026, 10, 1),
            ),
            registry._entries[h][1],
        )
        with pytest.raises(ExperimentRegistryError, match="tamper"):
            registry.get(h)

    def test_er_05_unregistered_fail_closed(self):
        registry = ExperimentRegistry()
        with pytest.raises(ExperimentRegistryError, match="not registered"):
            registry.get("pit4x." + "9" * 64)
        with pytest.raises(ExperimentRegistryError, match="unregistered"):
            registry.attach_log(
                ReproducibilityLog(experiment_hash="pit4x." + "9" * 64)
            )


class TestReproducibility:

    def test_er_03_verdicts(self):
        match = make_run()
        assert match.verdict is VerificationStatus.MATCH
        mismatch = make_run(observed="e" * 64, expected="d" * 64)
        assert mismatch.verdict is VerificationStatus.MISMATCH
        empty = ReproducibilityLog(experiment_hash="pit4x." + "a" * 64)
        assert empty.status is VerificationStatus.UNVERIFIED

    def test_er_04_log_immutable_and_deterministic(self):
        base = ReproducibilityLog(experiment_hash="pit4x." + "a" * 64)
        extended = base.extended(make_run())
        assert base.runs == ()  # original untouched
        assert len(extended.runs) == 1
        assert extended.status is VerificationStatus.MATCH
        # Deterministic hash
        twin = ReproducibilityLog(
            experiment_hash="pit4x." + "a" * 64
        ).extended(make_run())
        assert extended.log_hash == twin.log_hash
        assert extended.log_hash.startswith(REPRODUCIBILITY_PREFIX)
        # Different runs -> different hash
        other = base.extended(make_run(label="run-2"))
        assert extended.log_hash != other.log_hash

    def test_er_06_registry_status_queries(self):
        registry = ExperimentRegistry()
        e_match = make_entry(experiment_hash="pit4x." + "1" * 64, experiment_id="a")
        e_mismatch = make_entry(experiment_hash="pit4x." + "2" * 64, experiment_id="b")
        e_unverified = make_entry(experiment_hash="pit4x." + "3" * 64, experiment_id="c")
        registry.register(e_match)
        registry.register(e_mismatch)
        registry.register(e_unverified)

        registry.attach_log(
            ReproducibilityLog(experiment_hash=e_match.experiment_hash).extended(
                make_run(observed="d" * 64, expected="d" * 64)
            )
        )
        registry.attach_log(
            ReproducibilityLog(experiment_hash=e_mismatch.experiment_hash).extended(
                make_run(observed="f" * 64, expected="d" * 64)
            )
        )

        assert registry.reproducibility_status(e_match.experiment_hash) \
            is VerificationStatus.MATCH
        assert registry.reproducibility_status(e_mismatch.experiment_hash) \
            is VerificationStatus.MISMATCH
        assert registry.reproducibility_status(e_unverified.experiment_hash) \
            is VerificationStatus.UNVERIFIED
        assert registry.entries_with_status(VerificationStatus.MATCH) \
            == [e_match.experiment_hash]
        assert len(registry) == 3
