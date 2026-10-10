"""Operational feed-gate tests (operator mandate 2026-10-10 §2/§5).

The research-history vs operational-feed distinction:

- OPERATIONAL_FEED_READY is the 32nd mandatory readiness gate;
- the verdict requires a HUMAN-APPROVED source (APPROVED_FOR_PRODUCTION
  + production-ingestion scope — recorded through the prediction
  source registry's human-only approval mechanism), validated bars,
  freshness, correct instrument mapping, and warm-up sufficiency;
- the deferred long-term research history (GOV-HDD-001) is reported as
  DEFERRED_BY_OPERATOR — never claimed satisfied, never an activation
  requirement, never conflated with the operational feed;
- the gate reads NO environment and never fabricates an approval
  (unapproved/unregistered sources evaluate FALSE).

The "approved" sources here are TEST FIXTURES driving the registry's
human-only approval API — machinery tests, not real-world approvals.
"""

from datetime import timedelta
from pathlib import Path

import pytest

from data_engine.runtime import (
    GATE_NAMES,
    GateEvidence,
    PaperReadinessGate,
    evaluate_operational_feed,
)
from data_engine.runtime.feed_gate import (
    RESEARCH_HISTORY_DECISION_ID,
    RESEARCH_HISTORY_STATUS,
)
from data_engine.prediction.source_registry import (
    DataSourceRecord,
    DataSourceRegistry,
    SourceVerificationStatus,
)
from test_runtime_e2e import T0, _bars

SYMBOL = "TEST/USD"
CANONICAL = "instr-test-usd-001"


def _record(name="feed-source", status=None):
    return DataSourceRecord(
        source_name=name,
        source_type="exchange-api",
        license_basis="test-fixture-license",
        coverage="test fixture coverage",
        granularity="5m-OHLCV",
        revision_behavior="append-only",
        corporate_action_behavior="none",
        provenance_mechanism="checksums",
        verification_status=(
            status or SourceVerificationStatus.UNVETTED
        ),
    )


def _registry_with(*records):
    registry = DataSourceRegistry()
    for record in records:
        registry.register(record)
    return registry


def _approved_registry(name="feed-source"):
    """Registry whose source carries a HUMAN approval record (fixture)."""
    registry = _registry_with(_record(name))
    registry.submit_approval(
        name,
        approver="test-operator-fixture",
        approver_kind="human",
        target_status=SourceVerificationStatus.APPROVED_FOR_PRODUCTION,
        approved_usage_scopes=("production-ingestion",),
    )
    return registry


def _fresh_bars(n=30, interval=300, as_of=None):
    """Bars whose newest timestamp is one interval before ``as_of``."""
    offset = 0
    if as_of is not None:
        total = (as_of - T0).total_seconds()
        offset = int(total / interval) - n
    return _bars(n, interval=interval, t_offset=max(0, offset))


AS_OF = T0 + timedelta(seconds=300 * 200)  # logical session reference

BARS = _fresh_bars(30, as_of=AS_OF)


def _evaluate(registry, bars=BARS, warmup=30, **overrides):
    kwargs = dict(
        source_registry=registry,
        source_name="feed-source",
        session_symbol=SYMBOL,
        bars=bars,
        required_warmup_bars=warmup,
        as_of=AS_OF,
        canonical_instrument_id=CANONICAL,
        registry_confirmed=True,
    )
    kwargs.update(overrides)
    return evaluate_operational_feed(**kwargs)


# ════════════════════════════════════════════════════════════════════
# 1. Gate-set integration
# ════════════════════════════════════════════════════════════════════

class TestGateSet:
    def test_operational_feed_ready_is_gate_32(self):
        assert "OPERATIONAL_FEED_READY" in GATE_NAMES
        assert len(GATE_NAMES) == 32

    def test_real_data_ready_semantics_unchanged(self):
        """The distinction must not weaken REAL_DATA_READY: it stays a
        mandatory gate with its own dataset-chain evidence path."""
        assert "REAL_DATA_READY" in GATE_NAMES

    def test_runtime_start_refused_when_feed_gate_fails(self, tmp_path):
        """One FALSE gate (OPERATIONAL_FEED_READY) => start REFUSED."""
        from data_engine.runtime import (
            ExecutionStateStore,
            TradingRuntime,
        )
        from data_engine.runtime.contracts import RuntimeContractError
        from test_runtime_recovery_integration import (
            _op_config,
            _ready_gate,
        )
        from test_runtime_e2e import _fit_world

        ens, cal = _fit_world()
        cfg = _op_config("feed-gate-refusal")
        rt = TradingRuntime(
            cfg, ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "store"),
            readiness_gate=_ready_gate(failed=["OPERATIONAL_FEED_READY"]),
        )
        with pytest.raises(RuntimeContractError,
                           match="OPERATIONAL_FEED_READY"):
            rt.start()

    def test_runtime_starts_with_all_32_gates_true(self, tmp_path):
        from data_engine.runtime import ExecutionStateStore, TradingRuntime
        from test_runtime_recovery_integration import (
            _op_config,
            _ready_gate,
        )
        from test_runtime_e2e import _fit_world

        ens, cal = _fit_world()
        rt = TradingRuntime(
            _op_config("feed-gate-all-32"),
            ens, calibrator=cal,
            state_store=ExecutionStateStore(tmp_path / "store"),
            readiness_gate=_ready_gate(),
        )
        rt.start()
        assert rt.ledgers.verify()


# ════════════════════════════════════════════════════════════════════
# 2. Source approval discipline (fail closed)
# ════════════════════════════════════════════════════════════════════

class TestSourceApproval:
    def test_unvetted_source_fails(self):
        report = _evaluate(_registry_with(_record()))
        assert not report.passed
        assert any("APPROVED_FOR_PRODUCTION" in r for r in report.reasons)
        assert report.source_status == "UNVETTED"

    def test_unregistered_source_fails_closed(self):
        report = _evaluate(_registry_with())  # empty registry
        assert not report.passed
        assert any("not registered" in r for r in report.reasons)

    def test_approved_for_testing_insufficient(self):
        registry = _registry_with(_record())
        registry.submit_approval(
            "feed-source",
            approver="test-operator-fixture",
            approver_kind="human",
            target_status=SourceVerificationStatus.APPROVED_FOR_TESTING,
            approved_usage_scopes=("contract-testing",),
        )
        report = _evaluate(registry)
        assert not report.passed
        assert any("APPROVED_FOR_TESTING cannot authorize" in r
                   for r in report.reasons)

    def test_production_without_ingestion_scope_fails(self):
        registry = _registry_with(_record())
        registry.submit_approval(
            "feed-source",
            approver="test-operator-fixture",
            approver_kind="human",
            target_status=SourceVerificationStatus.APPROVED_FOR_PRODUCTION,
            approved_usage_scopes=("contract-testing",),
        )
        report = _evaluate(registry)
        assert not report.passed
        assert any("production-ingestion" in r for r in report.reasons)

    def test_approved_production_source_passes(self):
        report = _evaluate(_approved_registry())
        assert report.passed, report.reasons
        assert report.source_status == "APPROVED_FOR_PRODUCTION"
        assert "production-ingestion" in report.approved_scopes


# ════════════════════════════════════════════════════════════════════
# 3. Feed quality / warm-up / freshness / mapping
# ════════════════════════════════════════════════════════════════════

class TestFeedRequirements:
    def test_insufficient_warmup_fails(self):
        report = _evaluate(_approved_registry(), warmup=50)  # 30 < 50
        assert not report.passed
        assert any("warm-up" in r for r in report.reasons)

    def test_quality_rejection_fails(self):
        bad_bars = [dict(b) for b in BARS]
        bad_bars[3]["high"] = bad_bars[3]["low"] - 5.0  # impossible OHLC
        report = _evaluate(_approved_registry(), bars=bad_bars)
        assert not report.passed
        assert any("ohlc_relationship" in r for r in report.reasons)

    def test_stale_feed_fails(self):
        stale_bars = _fresh_bars(30, as_of=AS_OF - timedelta(hours=24))
        report = _evaluate(_approved_registry(), bars=stale_bars)
        assert not report.passed
        assert any("STALE" in r for r in report.reasons)

    def test_future_dated_feed_fails(self):
        future_bars = _fresh_bars(30, as_of=AS_OF + timedelta(hours=2))
        report = _evaluate(_approved_registry(), bars=future_bars)
        assert not report.passed
        assert any("FUTURE-DATED" in r for r in report.reasons)

    def test_unmapped_instrument_fails(self):
        report = _evaluate(
            _approved_registry(), registry_confirmed=False,
            canonical_instrument_id=None,
        )
        assert not report.passed
        assert any("mapping unconfirmed" in r for r in report.reasons)
        assert any("canonical instrument id missing" in r
                   for r in report.reasons)

    def test_wrong_symbol_fails(self):
        from data_engine.runtime.feed_gate import FeedGateError
        with pytest.raises(FeedGateError):
            evaluate_operational_feed(
                source_registry=_approved_registry(),
                source_name="feed-source",
                session_symbol="  ",
                bars=BARS, required_warmup_bars=30, as_of=AS_OF,
            )

    def test_empty_bar_window_fails_warmup(self):
        report = _evaluate(_approved_registry(), bars=[])
        assert not report.passed
        assert any("warm-up" in r for r in report.reasons)

    def test_invalid_inputs_raise(self):
        from data_engine.runtime.feed_gate import FeedGateError
        with pytest.raises(FeedGateError):
            evaluate_operational_feed(
                source_registry=_approved_registry(),
                source_name="feed-source",
                session_symbol=SYMBOL,
                bars=BARS,
                required_warmup_bars=0,  # invalid
                as_of=AS_OF,
            )


# ════════════════════════════════════════════════════════════════════
# 4. Research-history separation (never conflated, never claimed)
# ════════════════════════════════════════════════════════════════════

class TestResearchHistorySeparation:
    def test_report_carries_deferral_status(self):
        report = _evaluate(_approved_registry())
        assert report.research_history_status == RESEARCH_HISTORY_STATUS
        assert RESEARCH_HISTORY_DECISION_ID == "GOV-HDD-001"

    def test_deferral_status_is_pinned_constant(self):
        from data_engine.runtime.feed_gate import OperationalFeedReport
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            OperationalFeedReport(
                passed=True, source_name="s", source_status="x",
                approved_scopes=(), symbol=SYMBOL, bar_count=1,
                warmup_required=1, quality_rejections=(),
                research_history_status="SATISFIED",  # forbidden lie
            )

    def test_feed_gate_reads_no_environment(self):
        source = (Path(__file__).resolve().parents[1]
                  / "src/data_engine/runtime/feed_gate.py").read_text()
        assert "os.environ" not in source
        assert "getenv" not in source

    def test_real_data_gate_untouched_by_distinction(self):
        """REAL_DATA_READY's own machinery still refuses a REAL_VERIFIED
        claim with INCOMPLETE evidence (fail closed — the distinction
        change must not weaken the nine-stage chain)."""
        from data_engine.runtime import DatasetReadinessRecord
        # pydantic wraps the DataGateError in ValidationError — match
        # the fail-closed message either way.
        with pytest.raises(Exception, match="REAL_VERIFIED refused"):
            DatasetReadinessRecord(
                dataset_id="incomplete-claim-1",
                source="some-real-source",
                acquisition_timestamp=T0,
                market="test",
                symbols=("TEST/USD",),
                timeframe="5m",
                coverage_start=T0,
                coverage_end=T0 + timedelta(days=1),
                timezone="UTC",
                adjustment_state="RAW",
                missing_data_statistics={},
                duplicate_statistics={},
                quality_status="PENDING",   # evidence incomplete...
                pit_status="NOT_VERIFIED",  # ...so REAL_VERIFIED must be
                provenance={"source": "x"},
                content_hash="a" * 64,
                epistemic_state="REAL_VERIFIED",  # REFUSED
            )


# ════════════════════════════════════════════════════════════════════
# 5. Determinism of the verdict
# ════════════════════════════════════════════════════════════════════

class TestVerdictDeterminism:
    def test_same_inputs_same_verdict(self):
        a = _evaluate(_approved_registry())
        b = _evaluate(_approved_registry())
        assert a.passed == b.passed
        assert a.reasons == b.reasons
        assert a.bar_count == b.bar_count
        assert a.research_history_status == b.research_history_status

    def test_as_of_is_caller_supplied_not_wall_clock(self):
        """The gate never reads the ambient clock — the reference time
        is an explicit input (deterministic given inputs)."""
        earlier = AS_OF - timedelta(hours=1)
        r_earlier = _evaluate(_approved_registry(), as_of=earlier)
        assert not r_earlier.passed  # same bars, older reference => stale
        assert r_earlier.as_of == earlier
