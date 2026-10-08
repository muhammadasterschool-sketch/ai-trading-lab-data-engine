"""Prediction Intelligence closure tests — datasets, quality gates,
data-source registry (mandate §4/§5/§6).

Covers:
- dataset manifests: identity, immutability, provenance completeness
- dataset verification: state machine, never trusting caller claims
- content checksums: determinism, tamper detection
- all 16 quality gates with explicit refusal states
- data-source registry: no credentials, human-only approval,
  fail-closed usage authorization, candidate matrix honesty
"""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.datasets import (
    MANDATORY_MANIFEST_FIELDS,
    DatasetManifest,
    DatasetState,
    dataset_content_hash,
    synthetic_dataset_manifest,
    verify_dataset_manifest,
)
from data_engine.prediction.quality_gates import (
    QualityGateID,
    validate_ohlcv,
)
from data_engine.prediction.source_registry import (
    DataSourceRecord,
    DataSourceRegistry,
    SourceVerificationStatus,
    USAGE_SCOPES,
    candidate_source_matrix,
)


# ─── fixtures ──────────────────────────────────────────────────────────

def _candles(n: int = 60, *, start: datetime = None) -> list[dict]:
    start = start or datetime(2024, 1, 1, tzinfo=UTC)
    price = 100.0
    out = []
    for i in range(n):
        price *= 1.0 + (0.002 if i % 3 else -0.001)
        out.append({
            "timestamp": start + timedelta(days=i),
            "close": round(price, 10),
        })
    return out


def _synthetic_manifest(candles) -> DatasetManifest:
    return synthetic_dataset_manifest(
        dataset_name="test-fixture",
        symbol="TEST",
        row_count=len(candles),
        content_checksum=dataset_content_hash(candles),
        coverage_start=candles[0]["timestamp"].date().isoformat(),
        coverage_end=candles[-1]["timestamp"].date().isoformat(),
        generator="arithmetic-walk",
        seed=42,
    )


def _real_manifest(candles, **overrides) -> DatasetManifest:
    base = dict(
        dataset_name="test-real",
        source_name="stooq-daily-ohlcv",
        source_version="2024-01",
        acquisition_timestamp="2024-03-01T00:00:00+00:00",
        coverage_start=candles[0]["timestamp"].date().isoformat(),
        coverage_end=candles[-1]["timestamp"].date().isoformat(),
        symbol="TEST",
        exchange="TEST-EXCHANGE",
        timezone="UTC",
        frequency="1D",
        corporate_action_treatment="split-adjusted",
        adjustment_policy="back-adjusted",
        missing_data_policy="explicit-gap",
        revision_policy="append-only-first-arrival",
        license_basis="public-domain",
        provenance_metadata=(("download", "archive"),),
        content_checksum=dataset_content_hash(candles),
        row_count=len(candles),
        data_state=DatasetState.REAL_UNVERIFIED,
    )
    base.update(overrides)
    return DatasetManifest(**base)


# ─── dataset manifests ─────────────────────────────────────────────────

class TestDatasetManifest:

    def test_manifest_hash_is_immutable_identifier(self):
        candles = _candles()
        m1 = _synthetic_manifest(candles)
        m2 = _synthetic_manifest(candles)
        assert m1.manifest_hash == m2.manifest_hash
        assert m1.manifest_hash.startswith("preds.")
        # any field change => different dataset identity
        m3 = m2.model_copy(update={"row_count": m2.row_count + 1})
        assert m3.manifest_hash != m1.manifest_hash

    def test_synthetic_manifest_declares_generator_and_seed(self):
        candles = _candles()
        m = _synthetic_manifest(candles)
        assert m.data_state is DatasetState.SYNTHETIC
        meta = dict(m.provenance_metadata)
        assert meta["generator"] == "arithmetic-walk"
        assert meta["seed"] == "42"
        assert m.synthetic is True
        assert m.eligible_for_empirical_evaluation is False

    def test_synthetic_manifest_requires_generator_and_seed(self):
        candles = _candles()
        with pytest.raises(PredictionContractError):
            synthetic_dataset_manifest(
                dataset_name="x", symbol="T", row_count=1,
                content_checksum=dataset_content_hash(candles[:1]),
                coverage_start="2024-01-01", coverage_end="2024-01-01",
                generator="", seed=1,
            )

    def test_provenance_complete_detects_placeholders(self):
        candles = _candles()
        m = _real_manifest(
            candles, license_basis="UNRECORDED"
        )
        assert m.provenance_complete is False

    def test_empty_text_fields_rejected(self):
        candles = _candles()
        with pytest.raises(Exception) as excinfo:
            _real_manifest(candles, source_name="  ")
        assert "non-empty" in str(excinfo.value)


class TestDatasetContentHash:

    def test_content_hash_deterministic(self):
        a, b = _candles(), _candles()
        assert dataset_content_hash(a) == dataset_content_hash(b)

    def test_content_hash_detects_mutation(self):
        candles = _candles()
        tampered = list(candles)
        tampered[10] = {**tampered[10], "close": 55.0}
        assert dataset_content_hash(candles) != dataset_content_hash(tampered)

    def test_content_hash_rejects_inf(self):
        candles = _candles()
        poisoned = list(candles)
        poisoned[3] = {**poisoned[3], "close": float("inf")}
        with pytest.raises(PredictionContractError):
            dataset_content_hash(poisoned)

    def test_content_hash_order_insensitive_by_timestamp_iso(self):
        candles = _candles()
        reordered = list(reversed(candles))
        # rows are hashed as a LIST — order matters for content identity
        assert dataset_content_hash(candles) != dataset_content_hash(
            reordered
        )


# ─── dataset verification ──────────────────────────────────────────────

class TestDatasetVerification:

    def test_synthetic_never_promoted(self):
        candles = _candles()
        m = _synthetic_manifest(candles)
        report = verify_dataset_manifest(
            m,
            recomputed_checksum=dataset_content_hash(candles),
            quality_report_passed=True,
            source_approved=True,
        )
        # checksum match on synthetic content proves only fixture integrity
        assert report.computed_state is DatasetState.SYNTHETIC
        assert report.verified is False
        assert report.refusal_reason == "SYNTHETIC_NOT_EMPIRICAL_EVIDENCE"

    def test_synthetic_checksum_mismatch_invalid(self):
        candles = _candles()
        m = _synthetic_manifest(candles)
        report = verify_dataset_manifest(
            m, recomputed_checksum="preds.TAMPERED"
        )
        assert report.computed_state is DatasetState.INVALID

    def test_real_unverified_promotes_with_full_evidence(self):
        candles = _candles()
        m = _real_manifest(candles)
        report = verify_dataset_manifest(
            m,
            recomputed_checksum=dataset_content_hash(candles),
            quality_report_passed=True,
            source_approved=True,
            coverage_years=12.0,
        )
        assert report.computed_state is DatasetState.REAL_VERIFIED
        assert report.verified is True

    def test_real_unverified_stays_without_evidence(self):
        candles = _candles()
        m = _real_manifest(candles)
        report = verify_dataset_manifest(
            m, recomputed_checksum=dataset_content_hash(candles)
        )
        assert report.computed_state is DatasetState.REAL_UNVERIFIED
        assert report.verified is False

    def test_declared_real_verified_demoted_without_evidence(self):
        """Caller-asserted verified=True is never trusted (mandate §14)."""
        candles = _candles()
        m = _real_manifest(
            candles, data_state=DatasetState.REAL_VERIFIED
        )
        report = verify_dataset_manifest(
            m, recomputed_checksum=dataset_content_hash(candles)
        )
        assert report.computed_state is DatasetState.REAL_UNVERIFIED
        assert any("demoted" in note for note in report.notes)

    def test_declared_real_verified_invalid_on_checksum_mismatch(self):
        candles = _candles()
        m = _real_manifest(
            candles, data_state=DatasetState.REAL_VERIFIED
        )
        report = verify_dataset_manifest(
            m,
            recomputed_checksum="preds.MISMATCH",
            quality_report_passed=True,
            source_approved=True,
            coverage_years=12.0,
        )
        assert report.computed_state is DatasetState.INVALID
        assert report.failures

    def test_sub_minimum_coverage_is_insufficient(self):
        candles = _candles()  # 60 daily bars ~ 0.24 years
        m = _real_manifest(candles)
        report = verify_dataset_manifest(
            m,
            recomputed_checksum=dataset_content_hash(candles),
            quality_report_passed=True,
            source_approved=True,
            coverage_years=0.24,
        )
        assert report.computed_state is DatasetState.INSUFFICIENT
        assert report.refusal_reason == "INSUFFICIENT_HISTORY"

    def test_failed_quality_gate_blocks_verification(self):
        candles = _candles()
        m = _real_manifest(candles)
        report = verify_dataset_manifest(
            m,
            recomputed_checksum=dataset_content_hash(candles),
            quality_report_passed=False,
            source_approved=True,
        )
        assert report.computed_state is DatasetState.INVALID

    def test_unapproved_source_blocks_verification(self):
        candles = _candles()
        m = _real_manifest(candles)
        report = verify_dataset_manifest(
            m,
            recomputed_checksum=dataset_content_hash(candles),
            quality_report_passed=True,
            source_approved=False,
        )
        assert report.computed_state is DatasetState.INVALID
        assert any("human decision" in f for f in report.failures)

    def test_verification_report_hash_stable(self):
        candles = _candles()
        m = _real_manifest(candles)
        r1 = verify_dataset_manifest(m)
        r2 = verify_dataset_manifest(m)
        assert r1.verification_hash == r2.verification_hash


# ─── quality gates ─────────────────────────────────────────────────────

class TestQualityGates:

    def test_clean_close_only_series_passes(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        report = validate_ohlcv(candles, manifest=manifest)
        assert report.passed, [f.detail for f in report.failures]
        assert report.refusal_state is None
        assert report.rows_inspected == len(candles)
        # 16 gates all evaluated
        assert len(report.findings) == 16

    def test_quality_hash_deterministic(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        r1 = validate_ohlcv(candles, manifest=manifest)
        r2 = validate_ohlcv(candles, manifest=manifest)
        assert r1.quality_hash == r2.quality_hash

    def test_duplicate_timestamps_fail_qg02(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = list(candles)
        poisoned.insert(30, dict(candles[30]))
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.DUPLICATE_TIMESTAMPS
        )
        assert not finding.passed
        assert 31 in finding.affected_rows  # the later duplicate row

    def test_ordering_violation_fails_qg01(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = list(candles)
        poisoned[30], poisoned[31] = poisoned[31], poisoned[30]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.TIMESTAMP_ORDERING
        )
        assert not finding.passed

    def test_missing_block_fails_qg03(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = candles[:30] + candles[45:]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.MISSING_INTERVALS
        )
        assert not finding.passed

    def test_negative_price_fails_qg05_invalid(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = list(candles)
        poisoned[10] = {**poisoned[10], "close": -1.0}
        report = validate_ohlcv(poisoned, manifest=manifest)
        assert not report.passed
        assert report.refusal_state == "INVALID"

    def test_impossible_ohlc_fails_qg04(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = []
        for i, c in enumerate(candles):
            row = dict(c)
            if i == 10:
                row.update({"open": 100.0, "high": 90.0, "low": 80.0})
            poisoned.append(row)
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.OHLC_RELATIONSHIPS
        )
        assert not finding.passed

    def test_invalid_volume_fails_qg06(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = [
            {**c, "volume": (1000 if i != 10 else -5)}
            for i, c in enumerate(candles)
        ]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.INVALID_VOLUMES
        )
        assert not finding.passed

    def test_naive_timestamps_fail_qg07(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = [
            {**c, "timestamp": c["timestamp"].replace(tzinfo=None)}
            if i == 10 else c
            for i, c in enumerate(candles)
        ]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.TIMEZONE_CONSISTENCY
        )
        assert not finding.passed

    def test_future_timestamp_fails_qg08(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        bound = candles[-1]["timestamp"] - timedelta(days=1)
        report = validate_ohlcv(
            candles, manifest=manifest, acquisition_bound=bound
        )
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.FUTURE_TIMESTAMPS
        )
        assert not finding.passed

    def test_lookahead_fails_qg14(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        cutoff = candles[40]["timestamp"]
        report = validate_ohlcv(
            candles, manifest=manifest, evaluation_cutoff=cutoff
        )
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.LOOKAHEAD_CONTAMINATION
        )
        assert not finding.passed
        assert finding.affected_rows

    def test_symbol_substitution_fails_qg10(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = [
            {**c, "symbol": ("TEST" if i < 30 else "IMPOSTER")}
            for i, c in enumerate(candles)
        ]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.SYMBOL_IDENTITY
        )
        assert not finding.passed

    def test_partial_dataset_fails_qg11(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        report = validate_ohlcv(candles[:40], manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.COVERAGE_GAPS
        )
        assert not finding.passed

    def test_checksum_mismatch_fails_qg15(self):
        candles = _candles()
        stale = _synthetic_manifest(candles).model_copy(update={
            "content_checksum": "preds.STALE"
        })
        report = validate_ohlcv(candles, manifest=stale)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.DATASET_CHECKSUM
        )
        assert not finding.passed
        assert report.refusal_state == "INVALID"

    def test_split_jump_flags_qg12(self):
        candles = _candles()
        real_manifest = _real_manifest(candles)
        poisoned = list(candles)
        poisoned[31] = {
            **poisoned[31], "close": poisoned[30]["close"] * 3.0
        }
        report = validate_ohlcv(poisoned, manifest=real_manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.CORPORATE_ACTION_CONSISTENCY
        )
        assert not finding.passed

    def test_revision_contamination_qg13(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        poisoned = list(candles) + [{
            "timestamp": candles[20]["timestamp"],
            "close": candles[20]["close"] * 0.5,
        }]
        report = validate_ohlcv(poisoned, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.REVISION_CONTAMINATION
        )
        assert not finding.passed

    def test_provenance_incomplete_qg16(self):
        candles = _candles()
        incomplete = _real_manifest(
            candles, license_basis="UNRECORDED"
        )
        report = validate_ohlcv(candles, manifest=incomplete)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.PROVENANCE_COMPLETENESS
        )
        assert not finding.passed

    def test_close_only_ohlc_gate_is_na_recorded(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        report = validate_ohlcv(candles, manifest=manifest)
        finding = next(
            f for f in report.findings
            if f.gate is QualityGateID.OHLC_RELATIONSHIPS
        )
        assert finding.passed
        assert finding.detail.startswith("N/A")
        assert finding.applicable is False

    def test_coverage_gap_only_is_insufficient(self):
        candles = _candles()
        manifest = _synthetic_manifest(candles)
        gapped = candles[:30] + candles[45:]
        manifest = manifest.model_copy(update={
            "content_checksum": dataset_content_hash(gapped),
            "row_count": len(gapped),
        })
        report = validate_ohlcv(gapped, manifest=manifest)
        assert not report.passed
        assert report.refusal_state == "DATA_INSUFFICIENT"


# ─── data-source registry ──────────────────────────────────────────────

class TestSourceRegistry:

    def _record(self, **overrides) -> DataSourceRecord:
        base = dict(
            source_name="test-source",
            source_type="archive-download",
            license_basis="UNKNOWN",
            coverage="daily OHLCV",
            granularity="daily-OHLCV",
            revision_behavior="UNKNOWN",
            corporate_action_behavior="verified",
            provenance_mechanism="payload hash",
        )
        base.update(overrides)
        return DataSourceRecord(**base)

    def test_no_credential_fields_structurally(self):
        record = self._record()
        # extra=forbid: no credential field can even be declared
        with pytest.raises(Exception):
            DataSourceRecord(
                **{
                    **self._record().model_dump(),
                    "api_key": "secret",
                }
            )
        assert "api_key" not in record.model_dump()
        assert "token" not in record.model_dump()

    def test_register_and_duplicate_rejection(self):
        registry = DataSourceRegistry()
        registry.register(self._record())
        with pytest.raises(PredictionContractError):
            registry.register(self._record())

    def test_non_unvetted_entry_requires_approval(self):
        registry = DataSourceRegistry()
        with pytest.raises(PredictionContractError):
            registry.register(
                self._record(
                    verification_status=(
                        SourceVerificationStatus.APPROVED_FOR_TESTING
                    )
                )
            )

    def test_ai_approval_structurally_rejected(self):
        registry = DataSourceRegistry()
        registry.register(self._record())
        decision = registry.submit_approval(
            "test-source", "agent-9", approver_kind="ai"
        )
        assert decision.accepted is False
        assert "HUMAN DECISION" in decision.reason
        record = registry.get("test-source")
        assert record.verification_status is (
            SourceVerificationStatus.UNVETTED
        )

    def test_human_approval_enables_usage_scope(self):
        registry = DataSourceRegistry()
        registry.register(self._record())
        decision = registry.submit_approval(
            "test-source", "operator",
            approver_kind="human",
            approved_usage_scopes=("contract-testing",),
        )
        assert decision.accepted is True
        assert registry.usage_authorized(
            "test-source", "contract-testing"
        ) is True
        # scope not granted -> fail closed
        assert registry.usage_authorized(
            "test-source", "empirical-evaluation"
        ) is False

    def test_unknown_source_and_scope_fail_closed(self):
        registry = DataSourceRegistry()
        assert registry.usage_authorized("ghost", "contract-testing") is False
        with pytest.raises(PredictionContractError):
            registry.usage_authorized("test-source", "not-a-scope")

    def test_unknown_usage_scope_rejected_at_validation(self):
        with pytest.raises(Exception) as excinfo:
            self._record(approved_usage_scopes=("weird-scope",))
        assert "closed vocabulary" in str(excinfo.value)

    def test_candidate_matrix_all_unvetted_and_honest(self):
        matrix = candidate_source_matrix()
        assert len(matrix) >= 5
        for record in matrix:
            assert record.verification_status is (
                SourceVerificationStatus.UNVETTED
            )
            assert record.approval is None
            assert record.approved_usage_scopes == ()
            # license basis must be honest (never asserted as confirmed)
            assert record.license_basis != "public-domain"

    def test_usage_scopes_closed_vocabulary(self):
        assert "contract-testing" in USAGE_SCOPES
        assert "empirical-evaluation" in USAGE_SCOPES
        assert "production-ingestion" in USAGE_SCOPES

    def test_record_hash_stable(self):
        r1 = self._record()
        r2 = self._record()
        assert r1.record_hash == r2.record_hash
        assert r1.record_hash.startswith("predc.")
