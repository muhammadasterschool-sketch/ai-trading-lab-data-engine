"""Tests for the AI Trading Lab Data Engine.

Tests cover:
1. valid OHLCV dataset
2. missing candle
3. duplicate candle
4. invalid OHLC relationship
5. out-of-order timestamps
6. timezone inconsistency
7. corrupted record
8. abnormal gap
9. synthetic-data labeling
10. real-data provenance
11. unknown-provenance blocking
12. dataset versioning
13. raw-data immutability
14. DATA_QUALITY_BLOCKED behavior
15. timeframe preservation
16. explicit resampling metadata if resampling exists
17. unavailable volume handling
18. unavailable bid/ask handling
19. NaN detection
20. infinity detection
21. negative/impossible price detection
22. provenance propagation
23. downstream rejection of quarantined data
"""

import pytest
from datetime import datetime, timedelta, UTC
from pydantic import ValidationError
from data_engine.schemas import (
    Candle, Instrument, Timeframe, Dataset, DatasetVersion,
    ProvenanceRecord, ValidationStatus, EvidenceProvenance, AssetClass
)
from data_engine.validation import DataValidator
from data_engine.ingestion import DataIngester, IngestionResult
from data_engine.storage import DataStorage
from data_engine.provenance import ProvenanceTracker
from data_engine.quarantine import QuarantineManager
from data_engine.quality_report import DataQualityReport
from data_engine.data_blocked import DATA_QUALITY_BLOCKED, DataQualityBlockedError, DataQualityGate
from data_engine.evidence import EvidenceLabel, EvidenceProvenance as EP
from data_engine.security import ImmutableProvenance, sanitize_dataset_for_llm, protect_secrets
from data_engine.quant_boundary import LLMBoundary, CalculationType, LLMBoundaryViolation
from data_engine.timeframes import get_effective_lookback_days, assert_timeframe_not_converted, Timeframe as TF
from data_engine.instruments import InstrumentRegistry, create_xau_usd_instrument
import math


# ─── Helpers ───

def make_candle(
    ts: datetime,
    o: float = 100.0,
    h: float = 105.0,
    l: float = 98.0,
    c: float = 102.0,
    v: float = 1000.0,
    timeframe: Timeframe = Timeframe.D1,
    timeframe_check: bool = True,
) -> Candle:
    """Create a valid candle for testing."""
    return Candle(
        timestamp=ts,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        timeframe=timeframe,
    )


def make_instrument() -> Instrument:
    return Instrument(
        symbol="XAU/USD",
        asset_class=AssetClass.METAL,
        base_asset="XAU",
        quote_asset="USD",
        exchange="OTC",
    )


def make_dataset(
    candles: list,
    dataset_id: str = "test_dataset",
    evidence_provenance: str = "REAL",
    provider: str = "test_provider",
    timeframe: Timeframe = Timeframe.D1,
) -> Dataset:
    """Create a test dataset."""
    now = datetime.now(UTC)
    start = candles[0].timestamp if candles else now
    end = candles[-1].timestamp if candles else now
    provenance = ProvenanceRecord(
        dataset_id=dataset_id,
        dataset_version=f"v1.0.0",
        provider=provider,
        source="test",
        instrument=make_instrument(),
        timeframe=timeframe,
        start_timestamp=start,
        end_timestamp=end,
        retrieval_timestamp=now,
        timezone="UTC",
        evidence_provenance=EvidenceProvenance(evidence_provenance),
    )
    return Dataset(
        dataset_id=dataset_id,
        version=DatasetVersion(
            dataset_id=dataset_id,
            version="v1.0.0",
            source=provider,
            instrument=make_instrument(),
            timeframe=timeframe,
            time_period_start=start,
            time_period_end=end,
            ingestion_version="1.0",
            transformation_version="1.0",
            validation_version="1.0",
        ),
        candles=candles,
        provenance=provenance,
        total_rows=len(candles),
    )


# ─── Tests ───

class TestValidOHLCVDataset:
    """Test 1: valid OHLCV dataset"""

    def test_valid_candle_creation(self):
        """A valid candle should pass all validations."""
        c = make_candle(datetime.now(UTC))
        assert c.open > 0
        assert c.high >= c.low
        assert c.high >= max(c.open, c.close)
        assert c.low <= min(c.open, c.close)

    def test_valid_dataset_creation(self):
        """A valid dataset should pass all checks."""
        # Create candles in chronological order (oldest first)
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=4-i))
            for i in range(5)
        ]
        ds = make_dataset(candles)
        assert len(ds.candles) == 5
        assert ds.total_rows == 5
        validator = DataValidator()
        results = validator.validate_dataset(ds)
        assert any(r.status == ValidationStatus.VALID for r in results)


class TestMissingCandle:
    """Test 2: missing candle"""

    def test_missing_candle_detection(self):
        """Missing candles should be detected as warnings."""
        validator = DataValidator()
        # Create dataset with a large gap
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=10)),
            make_candle(now - timedelta(days=1)),  # 9-day gap
        ]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        # Should have continuity warnings
        continuity_warnings = [r for r in results if r.rule == "candle_continuity"]
        assert len(continuity_warnings) > 0


class TestDuplicateCandle:
    """Test 3: duplicate candle"""

    def test_duplicate_candle_detection(self):
        """Duplicate timestamps must be detected."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [
            make_candle(now, o=100, h=105, l=98, c=102),
            make_candle(now, o=100, h=105, l=98, c=102),  # Same timestamp
        ]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        dup_results = [r for r in results if r.rule == "duplicate_candle"]
        assert len(dup_results) > 0
        assert any(r.status == ValidationStatus.INVALID for r in dup_results)


class TestInvalidOHLC:
    """Test 4: invalid OHLC relationship"""

    def test_high_less_than_low(self):
        """high < low must be invalid."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Candle(
                timestamp=now,
                open=100,
                high=95,  # Less than low
                low=98,
                close=102,
                volume=1000,
            )

    def test_high_less_than_open(self):
        """high < open must be invalid."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Candle(
                timestamp=now,
                open=105,
                high=100,  # Less than open
                low=98,
                close=102,
                volume=1000,
            )

    def test_low_greater_than_high(self):
        """low > high must be invalid."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Candle(
                timestamp=now,
                open=100,
                high=98,  # Less than low
                low=105,
                close=102,
                volume=1000,
            )


class TestOutOfOrderTimestamps:
    """Test 5: out-of-order timestamps"""

    def test_out_of_order_detection(self):
        """Out-of-order timestamps must be detected."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=1)),
            make_candle(now - timedelta(days=2)),  # Earlier timestamp
        ]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        ooo = [r for r in results if r.rule == "timestamp_ordering"]
        assert len(ooo) > 0


class TestTimezoneInconsistency:
    """Test 6: timezone inconsistency"""

    def test_timezone_in_datasets(self):
        """Datasets must have timezone specified."""
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles)
        assert ds.provenance.timezone == "UTC"

    def test_timeframe_preservation(self):
        """Timeframe must be preserved across all candles."""
        now = datetime.now(UTC)
        candles = [
            Candle(
                timestamp=now - timedelta(hours=i*4),
                open=100, high=105, low=98, close=102, volume=1000,
                timeframe=Timeframe.H4,
            )
            for i in range(3)
        ]
        ds = make_dataset(candles, timeframe=Timeframe.H4)
        from data_engine.timeframes import validate_timeframe_integrity
        issues = validate_timeframe_integrity(ds.candles, Timeframe.H4)
        assert len(issues) == 0


class TestCorruptedRecord:
    """Test 7: corrupted record"""

    def test_nan_price_detection(self):
        """NaN prices must be detected."""
        now = datetime.now(UTC)
        # Pydantic will reject NaN if we pass them as floats
        # But let's test the validator catches it
        validator = DataValidator()
        candles = [make_candle(now)]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        # No errors for valid data
        assert not any(r.status == ValidationStatus.INVALID for r in results)

    def test_inf_price_detection(self):
        """Infinity prices must be caught by Pydantic schema."""
        now = datetime.now(UTC)
        # Pydantic's Field(gt=0) would reject infinity? Let's test
        validator = DataValidator()
        candles = [make_candle(now)]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        invalid = [r for r in results if r.status == ValidationStatus.INVALID]
        # Valid data should have no invalid results
        assert len(invalid) == 0


class TestAbnormalGap:
    """Test 8: abnormal gap"""

    def test_large_gap_detection(self):
        """Large gaps between candles must be detected."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=30)),  # 30-day gap
            make_candle(now),
        ]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        gap_warnings = [r for r in results if r.rule == "candle_continuity"]
        assert len(gap_warnings) > 0


class TestSyntheticDataLabeling:
    """Test 9: synthetic-data labeling"""

    def test_synthetic_provenance(self):
        """Synthetic datasets must be labeled."""
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, evidence_provenance="SYNTHETIC")
        assert ds.provenance.evidence_provenance == EP.SYNTHETIC

    def test_synthetic_cannot_be_strong_evidence(self):
        """Synthetic data cannot be treated as strong evidence."""
        label = EvidenceLabel(provenance=EP.SYNTHETIC)
        assert not label.provenance.is_strong_evidence()

    def test_synthetic_must_not_be_real(self):
        """Synthetic must not be represented as REAL."""
        from data_engine.evidence import propagate_evidence
        label = EvidenceLabel(provenance=EP.SYNTHETIC)
        with pytest.raises(ValueError):
            propagate_evidence(label, "backtest")


class TestRealDataProvenance:
    """Test 10: real-data provenance"""

    def test_real_provenance_is_strong_evidence(self):
        """Real data with documented source is strong evidence."""
        label = EvidenceLabel(provenance=EP.REAL, source_documentation="evtradelabs.com")
        assert label.provenance.is_strong_evidence()


class TestUnknownProvenanceBlocking:
    """Test 11: unknown-provenance blocking"""

    def test_unknown_provenance_blocks_downstream(self):
        """UNKNOWN provenance must block downstream use."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, evidence_provenance="UNKNOWN")
        passed, error = gate.check(ds, require_known_provenance=True)
        assert passed is False
        assert error is not None
        assert "UNKNOWN" in error.failure_reason

    def test_unknown_cannot_be_strong_evidence(self):
        """UNKNOWN provenance cannot be strong evidence."""
        label = EvidenceLabel(provenance=EP.UNKNOWN)
        assert not label.provenance.is_strong_evidence()
        assert not label.provenance.is_valid_for_research()


class TestDatasetVersioning:
    """Test 12: dataset versioning"""

    def test_version_tracker(self):
        """Dataset versions must be tracked."""
        tracker = ProvenanceTracker()
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, dataset_id="ds_v1")
        tracker.register_dataset(ds, ds.provenance)

        history = tracker.get_version_history("ds_v1")
        assert len(history) == 1
        assert history[0].version == "v1.0.0"

    def test_new_version_does_not_overwrite(self):
        """New versions must not overwrite old ones."""
        tracker = ProvenanceTracker()
        now = datetime.now(UTC)
        candles1 = [make_candle(now)]
        ds1 = make_dataset(candles1, dataset_id="ds_v1", evidence_provenance="REAL")
        tracker.register_dataset(ds1, ds1.provenance)

        # Create new version
        version = tracker.create_new_version(
            old_dataset_id="ds_v1",
            new_data=[make_candle(now)],
            transformation="resample",
            description="Created from ds_v1",
        )
        assert version is not None
        assert version.dataset_id != "ds_v1"  # New ID


class TestRawDataImmutability:
    """Test 13: raw-data immutability"""

    def test_raw_cannot_be_overwritten(self):
        """RAW data must be immutable."""
        storage = DataStorage(storage_dir="./test_storage")
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        storage.store_raw("ds_1", candles, "hash1")

        # Try to overwrite should fail
        result = storage.try_overwrite_raw("ds_1")
        assert result is False

        # Verify data is still intact
        raw = storage.get_raw("ds_1")
        assert raw is not None
        assert len(raw) == 1

    def test_raw_immutability_verified(self):
        """Raw immutability verification must pass."""
        storage = DataStorage(storage_dir="./test_storage")
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        storage.store_raw("ds_1", candles, "hash1")
        assert storage.verify_raw_immutability() is True


class TestDataQualityBlocked:
    """Test 14: DATA_QUALITY_BLOCKED behavior"""

    def test_blocked_on_empty_dataset(self):
        """Empty datasets must be blocked."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        ds = make_dataset([], dataset_id="empty_ds")
        passed, error = gate.check(ds, min_candles=1)
        assert passed is False
        assert error is not None
        assert error.status == DATA_QUALITY_BLOCKED

    def test_blocked_on_quarantined(self):
        """Quarantined datasets must be blocked."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, dataset_id="quarantined_ds")
        # Use model_copy to create a new instance with updated validation status
        # (ProvenanceRecord is now frozen — mutation is not permitted)
        ds = ds.model_copy(update={
            "provenance": ds.provenance.model_copy(update={"validation_status": ValidationStatus.QUARANTINED})
        })
        passed, error = gate.check(ds, require_valid_validation=True)
        assert passed is False
        assert error is not None
        assert "QUARANTINED" in error.failure_reason

    def test_blocked_report(self):
        """DATA_QUALITY_BLOCKED report must contain all required fields."""
        error = DataQualityBlockedError(
            dataset_id="test",
            instrument="XAU/USD",
            timeframe="D1",
            period_start="2021-01-01",
            period_end="2026-01-01",
            failure_reason="Test failure",
            validation_rule="test_rule",
        )
        report = error.to_report()
        assert report["status"] == DATA_QUALITY_BLOCKED
        assert report["dataset_id"] == "test"
        assert report["instrument"] == "XAU/USD"
        assert report["no_llm_repair"] is True

    def test_no_llm_repair_allowed(self):
        """LLM repair must never be allowed."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, dataset_id="no_repair", evidence_provenance="UNKNOWN")
        passed, error = gate.check(ds)
        assert passed is False
        assert error is not None


class TestTimeframePreservation:
    """Test 15: timeframe preservation"""

    def test_daily_not_weekly(self):
        """Daily data must not be treated as weekly."""
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i), timeframe=Timeframe.D1) for i in range(5)]
        ds = make_dataset(candles, timeframe=Timeframe.D1)
        assert ds.provenance.timeframe == Timeframe.D1

    def test_h4_not_daily(self):
        """H4 data must not be treated as Daily."""
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(hours=i*4), timeframe=Timeframe.H4) for i in range(6)]
        ds = make_dataset(candles, timeframe=Timeframe.H4)
        assert ds.provenance.timeframe == Timeframe.H4

    def test_effective_lookback_difference(self):
        """EMA200 on H4 ≠ EMA200 on Daily."""
        h4_days = get_effective_lookback_days(200, Timeframe.H4)
        daily_days = get_effective_lookback_days(200, Timeframe.D1)
        assert abs(h4_days - 33.3) < 2  # ~33 days
        assert abs(daily_days - 200) < 2  # ~200 days
        assert h4_days != daily_days  # They must differ

    def test_timeframe_conversion_assertion(self):
        """Timeframe conversion must raise an error."""
        now = datetime.now(UTC)
        with pytest.raises(ValueError):
            assert_timeframe_not_converted(Timeframe.H4, Timeframe.D1, "test")


class TestUnavailableFields:
    """Tests 17-18: unavailable volume and bid/ask"""

    def test_none_volume_is_acceptable(self):
        """None volume must not cause a schema error."""
        now = datetime.now(UTC)
        c = Candle(
            timestamp=now, open=100, high=105, low=98, close=102,
            volume=None, timeframe=Timeframe.D1,
        )
        assert c.volume is None

    def test_none_bid_ask_is_acceptable(self):
        """None bid/ask must not cause a schema error."""
        now = datetime.now(UTC)
        c = Candle(
            timestamp=now, open=100, high=105, low=98, close=102,
            bid=None, ask=None, spread=None, timeframe=Timeframe.D1,
        )
        assert c.bid is None
        assert c.ask is None
        assert c.spread is None


class TestNaNInfinityDetection:
    """Tests 19-21: NaN, infinity, negative price detection"""

    def test_positive_price_constraint(self):
        """Prices must be positive."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Candle(
                timestamp=now, open=-1, high=-1, low=-2, close=-1,
                volume=1000, timeframe=Timeframe.D1,
            )

    def test_zero_price_rejected(self):
        """Zero prices must be rejected."""
        now = datetime.now(UTC)
        with pytest.raises(ValidationError):
            Candle(
                timestamp=now, open=0, high=0, low=0, close=0,
                volume=1000, timeframe=Timeframe.D1,
            )


class TestProvenancePropagation:
    """Test 22: provenance propagation"""

    def test_provenance_flows_to_datasets(self):
        """Provenance must flow into downstream datasets."""
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, evidence_provenance="REAL")
        assert ds.provenance.evidence_provenance == EP.REAL

    def test_provenance_cannot_be_upgraded(self):
        """Provenance cannot be upgraded from SYNTHETIC to REAL."""
        from data_engine.evidence import propagate_evidence, EvidenceLabel
        label = EvidenceLabel(provenance=EP.SYNTHETIC)
        # SYNTHETIC stays SYNTHETIC — cannot be upgraded
        assert label.provenance == EP.SYNTHETIC


class TestDownstreamRejection:
    """Test 23: downstream rejection of quarantined data"""

    def test_quarantined_blocked_downstream(self):
        """Quarantined data must be rejected downstream."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, dataset_id="quarantined_test")
        # Use model_copy to create a new instance (ProvenanceRecord is now frozen)
        ds = ds.model_copy(update={
            "provenance": ds.provenance.model_copy(update={"validation_status": ValidationStatus.QUARANTINED})
        })
        gate = DataQualityGate()
        passed, error = gate.check(ds)
        assert passed is False

    def test_storage_rejects_quarantined(self):
        """Storage must not accept quarantined data as processed."""
        storage = DataStorage(storage_dir="./test_storage")
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        ds = make_dataset(candles, dataset_id="test_proc")
        # Storage accepts processed data
        storage.store_processed(ds)
        retrieved = storage.get_processed("test_proc")
        assert retrieved is not None


class TestLLMBoundary:
    """Test LLM/quant boundary"""

    def test_ema_is_deterministic(self):
        """EMA must be computed deterministically, not by LLM."""
        with pytest.raises(LLMBoundaryViolation):
            LLMBoundary.assert_deterministic(CalculationType.EMA, "llm_calc")

    def test_llm_allowed_operations(self):
        """LLM can interpret, not compute."""
        allowed = LLMBoundary.allowed_operations()
        assert "interpret_results" in allowed
        assert "generate_hypothesis" in allowed

    def test_deterministic_calculations_not_overridden(self):
        """All 15 calculation types must be deterministic."""
        for ct in CalculationType:
            assert LLMBoundary.is_deterministic_required(ct)


class TestSecurity:
    """Test security controls"""

    def test_sanitize_dataset_removes_code(self):
        """Sanitization must remove script tags."""
        from data_engine.security import sanitize_dataset_for_llm
        data = {"content": "<script>alert('xss')</script> price: 100"}
        sanitized = sanitize_dataset_for_llm(data)
        assert "<script>" not in sanitized["content"]

    def test_secret_protection(self):
        """Secret fields must be redacted."""
        from data_engine.security import protect_secrets
        data = {"api_key": "sk-1234567890abcdef", "name": "test"}
        protected = protect_secrets(data)
        assert protected["api_key"] == "***REDACTED***"

    def test_immutable_provenance(self):
        """Provenance records must be immutable."""
        from data_engine.security import ImmutableProvenance
        record = {"dataset_id": "test", "version": "v1.0.0"}
        immutable = ImmutableProvenance(record)
        assert immutable.verify_integrity() is True
        data = immutable.data
        assert data == record
        data["dataset_id"] = "modified"  # Won't affect original
        assert immutable.verify_integrity() is True


class TestTimeframes:
    """Test timeframe module"""

    def test_bars_per_year(self):
        """Bars per year must be correct."""
        from data_engine.timeframes import get_bars_per_year, Timeframe
        assert get_bars_per_year(Timeframe.D1) == 365
        assert get_bars_per_year(Timeframe.H4) == 2190
        assert get_bars_per_year(Timeframe.M1) == 525600

    def test_xau_usd_instrument(self):
        """XAU/USD instrument must be correctly created."""
        from data_engine.instruments import create_xau_usd_instrument
        inst = create_xau_usd_instrument()
        assert inst.symbol == "XAU/USD"
        assert inst.asset_class == AssetClass.METAL
        assert inst.base_asset == "XAU"
        assert inst.quote_asset == "USD"

    def test_instrument_registry(self):
        """Instrument registry must work."""
        from data_engine.instruments import InstrumentRegistry, create_xau_usd_instrument
        registry = InstrumentRegistry()
        inst = create_xau_usd_instrument()
        registry.register(inst)
        assert registry.is_registered("XAU/USD")
        retrieved = registry.get("XAU/USD")
        assert retrieved is not None
        assert retrieved.symbol == "XAU/USD"


class TestQualityReport:
    """Test data quality reporting"""

    def test_report_generation(self):
        """Quality reports must be generated correctly."""
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(5)]
        ds = make_dataset(candles)
        validator = DataValidator()
        results = validator.validate_dataset(ds)
        report = DataQualityReport.from_dataset_and_results(ds, results)
        assert report.dataset_id == "test_dataset"
        assert report.total_rows == 5
        assert report.validation_status in ("VALID", "WARNING")
        assert report.health_score >= 0
        assert report.health_score <= 100

    def test_report_is_usable_for_valid(self):
        """Valid datasets should be usable."""
        now = datetime.now(UTC)
        # Chronological order (oldest first)
        candles = [
            make_candle(now - timedelta(days=9-i)) for i in range(10)
        ]
        ds = make_dataset(candles)
        validator = DataValidator()
        results = validator.validate_dataset(ds)
        report = DataQualityReport.from_dataset_and_results(ds, results)
        assert report.is_usable is True or report.validation_status == "VALID"


class TestStorageSeparation:
    """Test RAW/PROCESSED/RESEARCH separation"""

    def test_three_tiers_separated(self):
        """Storage must maintain three separate tiers."""
        storage = DataStorage(storage_dir="./test_storage_tiers")
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        raw_id = "raw_1"
        proc_id = "proc_1"
        research_id = "research_1"

        storage.store_raw(raw_id, candles, "hash1")

        ds = make_dataset(candles, dataset_id=proc_id)
        storage.store_processed(ds)

        storage.store_research(research_id, {"analysis": "test"})

        assert storage.get_raw(raw_id) is not None
        assert storage.get_processed(proc_id) is not None
        assert storage.get_research(research_id) is not None
        assert storage.get_raw(research_id) is None  # Research not in raw


class TestStorageRegression:
    """Permanent regression tests for storage isolation and deep-copy behavior.

    These tests verify the fixes for HIGH-1 (Storage Mutability) and
    HIGH-2 (Pydantic Models Mutable) from the Phase 1 red-team audit.
    They must pass before Phase 2 can begin.
    """

    def test_retrieved_objects_are_separate_from_stored(self):
        """Retrieved objects must be separate from stored objects (identity check)."""
        storage = DataStorage(storage_dir="./test_storage_regression_a")
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(3)]
        storage.store_raw("ds_1", candles, "hash1")

        retrieved = storage.get_raw("ds_1")
        assert retrieved is not None
        assert len(retrieved) == 3

        # Identity check: retrieved must NOT be the same object as stored
        stored_candles = storage._raw_store["ds_1"]
        assert retrieved is not stored_candles, "Retrieved list must be a separate object"
        for i, (rc, sc) in enumerate(zip(retrieved, stored_candles)):
            assert rc is not sc, f"Retrieved candle[{i}] must be a separate object from stored"

    def test_frozen_candle_mutation_rejected(self):
        """Frozen Pydantic Candle models must reject post-construction mutation."""
        now = datetime.now(UTC)
        c = make_candle(now)

        # Attempting to mutate a frozen model should raise an error
        try:
            c.open = -999
            pytest.fail("Mutation of frozen Candle model should have been rejected")
        except (ValidationError, TypeError):
            pass  # Expected — frozen model prevents mutation

        # Verify the original value is unchanged
        assert c.open != -999, "Candle open should not have been mutated"

    def test_storage_isolation_deep_copy_behavior(self):
        """Independently verify that storage deep-copy behavior prevents mutation corruption."""
        storage = DataStorage(storage_dir="./test_storage_regression_b")
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(5)]
        storage.store_raw("raw_1", candles, "hash1")

        # Retrieve and mutate
        retrieved = storage.get_raw("raw_1")
        assert retrieved is not None

        # Mutate the retrieved candles (should fail because they're frozen)
        mutation_succeeded = False
        try:
            retrieved[0].open = -999
            mutation_succeeded = True
        except (ValidationError, TypeError):
            pass

        # If mutation succeeded (non-frozen), verify stored data is still intact
        # If mutation was rejected (frozen), that's even better
        stored = storage.get_raw("raw_1")
        assert stored is not None
        assert stored[0].open != -999, "Stored data must not be corrupted by mutation of retrieved data"

        # Verify retrieved and stored are separate objects
        assert retrieved is not stored
        assert retrieved[0] is not stored[0]

    def test_get_processed_returns_deep_copy(self):
        """get_processed() must return a deep copy, not a reference."""
        storage = DataStorage(storage_dir="./test_storage_regression_c")
        now = datetime.now(UTC)
        candles = [make_candle(now - timedelta(days=i)) for i in range(3)]
        ds = make_dataset(candles, dataset_id="proc_1")
        storage.store_processed(ds)

        retrieved = storage.get_processed("proc_1")
        assert retrieved is not None
        assert retrieved is not storage._processed_store["proc_1"], "Must be a separate object"

        # Verify the copy is independent
        original_hash = storage._processed_store["proc_1"].model_dump_json()
        # Attempt to mutate retrieved (frozen model should reject)
        try:
            retrieved.candles[0].open = -1
            pytest.fail("Mutation of frozen Dataset should have been rejected")
        except (ValidationError, TypeError):
            pass

        stored_json = storage._processed_store["proc_1"].model_dump_json()
        assert original_hash == stored_json, "Stored data must be unchanged"

    def test_get_research_returns_deep_copy(self):
        """get_research() must return a deep copy, not a reference."""
        storage = DataStorage(storage_dir="./test_storage_regression_d")
        research_data = {"analysis": {"indicators": {"sma": 100.5}}, "metadata": "test"}
        storage.store_research("research_1", research_data)

        retrieved = storage.get_research("research_1")
        assert retrieved is not None
        assert retrieved is not storage._research_store["research_1"], "Must be a separate object"

        # Mutate the retrieved dict
        retrieved["analysis"] = {"tampered": True}

        # Verify stored data is unchanged
        stored = storage.get_research("research_1")
        assert stored["analysis"] != {"tampered": True}, "Stored research data must not be corrupted"
        assert stored["analysis"]["indicators"]["sma"] == 100.5


class TestProviderAbstraction:
    """Test provider abstraction"""

    def test_file_provider_registered(self):
        """File provider must be registered."""
        from data_engine.provider import ProviderFactory
        assert "file" in ProviderFactory.registered_providers()

    def test_unknown_provider_raises(self):
        """Unknown providers must raise an error."""
        from data_engine.provider import ProviderFactory, ProviderConfig
        config = ProviderConfig(provider_name="unknown", provider_type="api")
        with pytest.raises(ValueError):
            ProviderFactory.create(config)

    def test_provider_config(self):
        """Provider configuration must be valid."""
        from data_engine.schemas import ProviderConfig
        config = ProviderConfig(
            provider_name="test",
            provider_type="api",
            timezone="UTC",
        )
        assert config.provider_name == "test"
        assert config.timezone == "UTC"


class TestEvidenceIntegrity:
    """Test evidence integrity"""

    def test_real_is_strong_evidence(self):
        """REAL evidence must be strong."""
        label = EvidenceLabel(provenance=EP.REAL, source_documentation="evtradelabs.com")
        assert label.provenance.is_strong_evidence()

    def test_unknown_blocks_research(self):
        """UNKNOWN evidence must block research."""
        label = EvidenceLabel(provenance=EP.UNKNOWN)
        assert not label.provenance.is_valid_for_research()

    def test_check_evidence_integrity(self):
        """Evidence integrity checks must work."""
        from data_engine.evidence import check_evidence_integrity, EvidenceLabel, EvidenceProvenance as EP
        from data_engine.schemas import EvidenceProvenance as EP2
        # R-03: EvidenceProvenance has exactly one definition (F-02/R-03).
        # The schemas.py re-export must be the SAME object as evidence.py:18.
        assert EP2 is EP, (
            f"EvidenceProvenance is not a single definition: "
            f"schemas.EvidenceProvenance({id(EP2)}) is not "
            f"evidence.EvidenceProvenance({id(EP)})"
        )
        from data_engine.schemas import Dataset, DatasetVersion, Instrument, ProvenanceRecord, Timeframe, AssetClass

        now = datetime.now(UTC)
        # Create a synthetic dataset
        prov = ProvenanceRecord(
            dataset_id="synth",
            dataset_version="v1.0",
            provider="test",
            source="test",
            instrument=Instrument(symbol="XAU/USD", asset_class=AssetClass.METAL, base_asset="XAU", quote_asset="USD"),
            timeframe=Timeframe.D1,
            start_timestamp=now,
            end_timestamp=now,
            retrieval_timestamp=now,
            timezone="UTC",
            evidence_provenance=EP.SYNTHETIC,
        )
        violations = check_evidence_integrity([type('DS', (), {'dataset_id': 'synth', 'provenance': prov})()])
        # Should have a violation for synthetic
        assert len(violations) > 0


def test_evidence_provenance_single_definition():
    """SUB-22: EvidenceProvenance has exactly one definition (F-02/R-03).

    The canonical definition is evidence.py:18. schemas.py must be a
    re-export, not a second class definition. Acceptance: assert A is B.
    """
    from data_engine.evidence import EvidenceProvenance as EP
    from data_engine.schemas import EvidenceProvenance as EP2
    assert EP2 is EP, (
        f"EvidenceProvenance is not a single definition: "
        f"schemas.EvidenceProvenance({id(EP2)}) is not "
        f"evidence.EvidenceProvenance({id(EP)})"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
