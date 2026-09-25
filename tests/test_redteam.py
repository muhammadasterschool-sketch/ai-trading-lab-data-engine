"""Phase 1 Source-Level Red-Team Adversarial Tests.

These tests verify that the Data Engine actually behaves correctly
under adversarial conditions, not just that it has the right structure.
"""

import pytest
from datetime import datetime, UTC, timedelta
from pydantic import ValidationError as PydanticVE
from data_engine.schemas import Candle, Timeframe, Dataset, DatasetVersion, Instrument, ProvenanceRecord, ValidationStatus
from data_engine.validation import DataValidator
from data_engine.storage import DataStorage
from data_engine.data_blocked import DataQualityGate, DATA_QUALITY_BLOCKED
from data_engine.quarantine import QuarantineManager
from data_engine.provenance import ProvenanceTracker
from data_engine.evidence import EvidenceLabel, EvidenceProvenance as EP
from data_engine.quant_boundary import LLMBoundary, CalculationType
from data_engine.instruments import create_xau_usd_instrument, InstrumentRegistry
from data_engine.timeframes import get_effective_lookback_days, Timeframe as TF, assert_timeframe_not_converted
from data_engine.security import protect_secrets, sanitize_dataset_for_llm
from data_engine.ingestion import DataIngester
import math
import os

# ─── Helpers ───

def make_candle(ts, o=100, h=105, l=98, c=102, v=1000, tf=Timeframe.D1):
    return Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, timeframe=tf)

def make_instrument():
    return Instrument(symbol="XAU/USD", asset_class=__import__('data_engine.schemas', fromlist=['AssetClass']).AssetClass.METAL, base_asset="XAU", quote_asset="USD", exchange="OTC")

def make_dataset(candles, dataset_id="test", evidence="REAL", provider="test", timeframe=Timeframe.D1):
    now = datetime.now(UTC)
    inst = make_instrument()
    prov = ProvenanceRecord(
        dataset_id=dataset_id, dataset_version="v1.0", provider=provider, source="test",
        instrument=inst, timeframe=timeframe,
        start_timestamp=candles[0].timestamp if candles else now,
        end_timestamp=candles[-1].timestamp if candles else now,
        retrieval_timestamp=now, timezone="UTC",
        evidence_provenance=EP(evidence),
    )
    dv = DatasetVersion(
        dataset_id=dataset_id, version="v1.0", source=provider, instrument=inst,
        timeframe=timeframe, time_period_start=prov.start_timestamp,
        time_period_end=prov.end_timestamp,
        ingestion_version="1.0", transformation_version="1.0", validation_version="1.0",
    )
    return Dataset(dataset_id=dataset_id, version=dv, candles=candles, provenance=prov, total_rows=len(candles))


# ═══════════════════════════════════════════════════════
# SCHEMA ADVERSARIAL TESTS
# ═══════════════════════════════════════════════════════

class TestSchemaAdversarial:
    """Test whether invalid state can enter through constructors."""

    def test_nan_price_rejected(self):
        """NaN must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=float('nan'), high=105, low=98, close=102, timeframe=Timeframe.D1)

    def test_infinity_price_rejected(self):
        """Infinity must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=float('inf'), high=105, low=98, close=102, timeframe=Timeframe.D1)

    def test_negative_price_rejected(self):
        """Negative prices must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=-1, high=105, low=98, close=102, timeframe=Timeframe.D1)

    def test_zero_price_rejected(self):
        """Zero prices must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=0, high=0, low=0, close=0, timeframe=Timeframe.D1)

    def test_high_less_than_low_rejected(self):
        """High < Low must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=100, high=95, low=98, close=102, timeframe=Timeframe.D1)

    def test_high_less_than_open_rejected(self):
        """High < open must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=105, high=102, low=98, close=102, timeframe=Timeframe.D1)

    def test_negative_volume_rejected(self):
        """Negative volume must be rejected."""
        with pytest.raises(PydanticVE):
            Candle(timestamp=datetime.now(UTC), open=100, high=105, low=98, close=102, volume=-100, timeframe=Timeframe.D1)

    def test_missing_required_field_rejected(self):
        """Missing required fields must be rejected."""
        with pytest.raises(PydanticVE):
            Candle.model_validate({'timestamp': datetime.now(UTC), 'open': 100, 'high': 105, 'low': 98, 'timeframe': Timeframe.D1})

    def test_invalid_enum_rejected(self):
        """Invalid enum values must be rejected."""
        with pytest.raises(PydanticVE):
            Candle.model_validate({'timestamp': datetime.now(UTC), 'open': 100, 'high': 105, 'low': 98, 'close': 102, 'timeframe': 'INVALID_TF'})

    def test_bid_greater_than_ask_rejected(self):
        """Bid > Ask must be rejected by validation."""
        from pydantic import ValidationError
        try:
            Candle(timestamp=datetime.now(UTC), open=100, high=105, low=98, close=102, bid=103, ask=101, timeframe=Timeframe.D1)
            pytest.fail('Bid > Ask should have been rejected')
        except ValidationError:
            pass  # Expected — bid > ask is now properly rejected

    def test_post_creation_mutation_rejected(self):
        """Pydantic models are frozen — post-construction mutation is rejected."""
        from pydantic import ValidationError
        c = Candle(timestamp=datetime.now(UTC), open=100, high=105, low=98, close=102, timeframe=Timeframe.D1)
        try:
            c.open = -50  # Should not be allowed — model is frozen
            pytest.fail('Mutation should have been rejected on frozen model')
        except (ValidationError, TypeError):
            pass  # Expected — frozen models reject post-construction mutation


    def test_nan_bid_ask_rejected(self):
        """NaN bid or ask must be rejected by validation."""
        from pydantic import ValidationError
        now = datetime.now(UTC)
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, bid=float('nan'), timeframe=Timeframe.D1)
            pytest.fail('NaN bid should have been rejected')
        except ValidationError:
            pass
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, ask=float('nan'), timeframe=Timeframe.D1)
            pytest.fail('NaN ask should have been rejected')
        except ValidationError:
            pass

    def test_infinity_bid_ask_rejected(self):
        """Infinite bid or ask must be rejected by validation."""
        from pydantic import ValidationError
        now = datetime.now(UTC)
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, bid=float('inf'), timeframe=Timeframe.D1)
            pytest.fail('Infinity bid should have been rejected')
        except ValidationError:
            pass
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, ask=float('inf'), timeframe=Timeframe.D1)
            pytest.fail('Infinity ask should have been rejected')
        except ValidationError:
            pass

    def test_negative_bid_ask_rejected(self):
        """Negative bid or ask must be rejected by validation."""
        from pydantic import ValidationError
        now = datetime.now(UTC)
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, bid=-1.0, timeframe=Timeframe.D1)
            pytest.fail('Negative bid should have been rejected')
        except ValidationError:
            pass
        try:
            Candle(timestamp=now, open=100, high=105, low=98, close=102, volume=1000, ask=-1.0, timeframe=Timeframe.D1)
            pytest.fail('Negative ask should have been rejected')
        except ValidationError:
            pass


# ═══════════════════════════════════════════════════════
# STORAGE IMMUTABILITY TESTS
# ═══════════════════════════════════════════════════════

class TestStorageImmutability:
    """Test whether retrieved objects can mutate stored data."""

    def test_raw_mutation_does_not_corrupt_storage(self):
        """Retrieved raw candles must be deep copies (frozen, immutable)."""
        storage = DataStorage(storage_dir='/tmp/test_storage_audit_c')
        now = datetime.now(UTC)
        inst = make_instrument()
        candles = [make_candle(now - timedelta(days=4-i)) for i in range(5)]
        prov = ProvenanceRecord(
            dataset_id='test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1,
            start_timestamp=now-timedelta(days=4), end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.REAL,
        )
        dv = DatasetVersion(dataset_id='test', version='v1', source='test', instrument=inst,
                           timeframe=Timeframe.D1, time_period_start=now-timedelta(days=4),
                           time_period_end=now, ingestion_version='1', transformation_version='1',
                           validation_version='1')
        ds = Dataset(dataset_id='test', version=dv, candles=candles, provenance=prov, total_rows=5)

        storage.store_raw('raw_1', candles, 'hash1')
        retrieved = storage.get_raw('raw_1')
        assert retrieved is not None
        # Retrieved candles are deep copies and frozen — attempt to mutate
        from pydantic import ValidationError
        try:
            retrieved[0].open = -999
            pytest.fail('Mutation of frozen retrieved candle should have been rejected')
        except (ValidationError, TypeError):
            pass  # Expected — frozen model prevents mutation
        # Verify stored data is unchanged
        stored = storage.get_raw('raw_1')
        assert stored is not None
        assert stored[0].open != -999, 'Stored data was corrupted!'
        # Verify retrieved and stored are different objects
        assert retrieved is not stored, 'Retrieved data must be a separate object from stored'

    def test_raw_overwrite_rejected(self):
        """RAW data must not be overwritten."""
        storage = DataStorage(storage_dir='/tmp/test_storage_audit2')
        now = datetime.now(UTC)
        candles = [make_candle(now)]
        storage.store_raw('ds_1', candles, 'hash1')
        result = storage.try_overwrite_raw('ds_1')
        assert result is False, "RAW data must not be overwriteable"

    def test_storage_deep_copy_identity(self):
        """get_processed and get_research must return distinct objects,
        not references to internal storage."""
        from data_engine.storage import DataStorage
        from data_engine.schemas import Dataset, DatasetVersion, Candle, ProvenanceRecord
        from data_engine.evidence import EvidenceProvenance as EP
        storage = DataStorage(storage_dir='/tmp/test_storage_deep_copy')
        now = datetime.now(UTC)
        inst = make_instrument()
        candles = [make_candle(now - timedelta(days=4-i)) for i in range(5)]
        prov = ProvenanceRecord(
            dataset_id='test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1,
            start_timestamp=now-timedelta(days=4), end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.REAL,
        )
        dv = DatasetVersion(
            dataset_id='test', version='v1', source='test', instrument=inst,
            timeframe=Timeframe.D1, time_period_start=now-timedelta(days=4),
            time_period_end=now, ingestion_version='1',
            transformation_version='1', validation_version='1'
        )
        ds = Dataset(dataset_id='test', version=dv, candles=candles,
                     provenance=prov, total_rows=5)

        # Test get_processed returns a distinct object
        storage.store_processed(ds)
        retrieved = storage.get_processed('test')
        assert retrieved is not None
        assert retrieved is not ds, 'get_processed must return a deep copy'
        assert retrieved.dataset_id == ds.dataset_id

        # Test get_research returns a distinct object
        research_data = {'metrics': {'return': 0.05}, 'trades': 10}
        storage.store_research('test', research_data)
        retrieved_research = storage.get_research('test')
        assert retrieved_research is not None
        assert retrieved_research is not research_data, 'get_research must return a deep copy'
        assert retrieved_research['metrics'] == research_data['metrics']
        # Mutating the retrieved research must not affect stored data
        retrieved_research['metrics']['return'] = -1.0
        stored_research = storage.get_research('test')
        assert stored_research is not None
        assert stored_research['metrics']['return'] != -1.0, \
            'Mutating retrieved research must not mutate internal storage'

    def test_raw_immutability_verified(self):
        """Immutability verification must pass."""
        storage = DataStorage(storage_dir='/tmp/test_storage_audit3')
        now = datetime.now(UTC)
        storage.store_raw('ds_1', [make_candle(now)], 'hash1')
        assert storage.verify_raw_immutability() is True


# ═══════════════════════════════════════════════════════
# DATA QUALITY GATE BYPASS TESTS
# ═══════════════════════════════════════════════════════

class TestDataQualityGate:
    """Test that DATA_QUALITY_BLOCKED cannot be bypassed."""

    def test_unknown_provenance_blocked(self):
        """UNKNOWN provenance must block downstream use."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        inst = make_instrument()
        candles = [make_candle(now)]
        prov = ProvenanceRecord(
            dataset_id='unknown_test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1, start_timestamp=now, end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.UNKNOWN,
        )
        ds = Dataset(dataset_id='unknown_test', version=DatasetVersion(dataset_id='unknown_test', version='v1', source='test', instrument=inst, timeframe=Timeframe.D1, time_period_start=now, time_period_end=now, ingestion_version='1', transformation_version='1', validation_version='1'), candles=candles, provenance=prov, total_rows=1)
        passed, error = gate.check(ds, require_known_provenance=True)
        assert passed is False
        assert error is not None
        assert "UNKNOWN" in error.failure_reason

    def test_invalid_validation_blocked(self):
        """INVALID validation status must block downstream use."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        inst = make_instrument()
        candles = [make_candle(now)]
        prov = ProvenanceRecord(
            dataset_id='invalid_test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1, start_timestamp=now, end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.REAL,
            validation_status=ValidationStatus.INVALID,
        )
        ds = Dataset(dataset_id='invalid_test', version=DatasetVersion(dataset_id='invalid_test', version='v1', source='test', instrument=inst, timeframe=Timeframe.D1, time_period_start=now, time_period_end=now, ingestion_version='1', transformation_version='1', validation_version='1'), candles=candles, provenance=prov, total_rows=1)
        passed, error = gate.check(ds, require_valid_validation=True)
        assert passed is False

    def test_empty_dataset_blocked(self):
        """Empty datasets must be blocked."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        inst = make_instrument()
        prov = ProvenanceRecord(
            dataset_id='empty_test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1, start_timestamp=now, end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.REAL,
        )
        ds = Dataset(dataset_id='empty_test', version=DatasetVersion(dataset_id='empty_test', version='v1', source='test', instrument=inst, timeframe=Timeframe.D1, time_period_start=now, time_period_end=now, ingestion_version='1', transformation_version='1', validation_version='1'), candles=[], provenance=prov, total_rows=0)
        passed, error = gate.check(ds, min_candles=1)
        assert passed is False
        assert error is not None
        assert error.status == DATA_QUALITY_BLOCKED

    def test_quarantined_blocked(self):
        """QUARANTINED datasets must be blocked."""
        gate = DataQualityGate()
        now = datetime.now(UTC)
        inst = make_instrument()
        prov = ProvenanceRecord(
            dataset_id='quarantined_test', dataset_version='v1', provider='test', source='test',
            instrument=inst, timeframe=Timeframe.D1, start_timestamp=now, end_timestamp=now,
            retrieval_timestamp=now, timezone='UTC', evidence_provenance=EP.REAL,
            validation_status=ValidationStatus.QUARANTINED,
        )
        ds = Dataset(dataset_id='quarantined_test', version=DatasetVersion(dataset_id='quarantined_test', version='v1', source='test', instrument=inst, timeframe=Timeframe.D1, time_period_start=now, time_period_end=now, ingestion_version='1', transformation_version='1', validation_version='1'), candles=[make_candle(now)], provenance=prov, total_rows=1)
        passed, error = gate.check(ds, require_valid_validation=True)
        assert passed is False


# ═══════════════════════════════════════════════════════
# QUANT BOUNDARY TESTS
# ═══════════════════════════════════════════════════════

class TestQuantBoundary:
    """Test that LLM cannot perform deterministic calculations."""

    def test_ema_requires_deterministic_code(self):
        """EMA must not be computable by LLM."""
        with pytest.raises(Exception):
            LLMBoundary.assert_deterministic(CalculationType.EMA, 'llm_calc')

    def test_all_calculation_types_deterministic(self):
        """All 15 calculation types must be deterministic."""
        for ct in CalculationType:
            with pytest.raises(Exception):
                LLMBoundary.assert_deterministic(ct, 'llm_calc')


# ═══════════════════════════════════════════════════════
# TIMEFRAME TESTS
# ═══════════════════════════════════════════════════════

class TestTimeframeAudit:
    """Test timeframe calculations and assumptions."""

    def test_h4_lookback_approximately_33_days(self):
        """EMA200 on H4 should be approximately 33 calendar days."""
        h4_days = get_effective_lookback_days(200, TF.H4)
        assert abs(h4_days - 33.3) < 2, f"H4 lookback {h4_days} not ~33.3"

    def test_daily_lookback_approximately_200_days(self):
        """EMA200 on Daily should be approximately 200 calendar days."""
        d1_days = get_effective_lookback_days(200, TF.D1)
        assert abs(d1_days - 200) < 2, f"D1 lookback {d1_days} not ~200"

    def test_h4_and_daily_lookback_differ(self):
        """H4 and Daily lookbacks must differ."""
        h4 = get_effective_lookback_days(200, TF.H4)
        d1 = get_effective_lookback_days(200, TF.D1)
        assert h4 != d1

    def test_timeframe_conversion_raises(self):
        """Timeframe conversion must raise an error."""
        with pytest.raises(ValueError):
            assert_timeframe_not_converted(TF.H4, TF.D1, "test")


# ═══════════════════════════════════════════════════════
# CONTINUITY TESTS
# ═══════════════════════════════════════════════════════

class TestContinuity:
    """Test whether engine distinguishes market closures from missing data."""

    def test_weekend_gap_flagged(self):
        """Engine flags weekend gaps — cannot distinguish from missing data."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=3)),  # Friday
            make_candle(now),  # Monday
        ]
        ds = make_dataset(candles, timeframe=Timeframe.D1)
        results = validator.validate_dataset(ds)
        gap_warnings = [r for r in results if r.rule == "candle_continuity"]
        # BUG: The engine flags legitimate weekend gaps as warnings
        # It CANNOT distinguish VALID MARKET CLOSURE from MISSING DATA
        # This is a documented limitation, not necessarily a bug
        # But it means continuity validation is overly sensitive
        assert len(gap_warnings) > 0, "Engine should flag large gaps"

    def test_missing_candle_detected(self):
        """Missing candles must be detected."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [
            make_candle(now - timedelta(days=10)),
            make_candle(now - timedelta(days=1)),  # 9-day gap
        ]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        gap_warnings = [r for r in results if r.rule == "candle_continuity"]
        assert len(gap_warnings) > 0

    def test_duplicate_candle_detected(self):
        """Duplicate timestamps must be detected."""
        validator = DataValidator()
        now = datetime.now(UTC)
        candles = [make_candle(now), make_candle(now)]
        ds = make_dataset(candles)
        results = validator.validate_dataset(ds)
        dup = [r for r in results if r.rule == "duplicate_candle"]
        assert len(dup) > 0


# ═══════════════════════════════════════════════════════
# EVIDENCE INTEGRITY TESTS
# ═══════════════════════════════════════════════════════

class TestEvidenceIntegrity:
    """Test evidence classification enforcement."""

    def test_real_is_strong_evidence(self):
        label = EvidenceLabel(provenance=EP.REAL, source_documentation="evtradelabs.com")
        assert label.provenance.is_strong_evidence()

    def test_synthetic_not_strong_evidence(self):
        label = EvidenceLabel(provenance=EP.SYNTHETIC)
        assert not label.provenance.is_strong_evidence()

    def test_unknown_not_strong_evidence(self):
        label = EvidenceLabel(provenance=EP.UNKNOWN)
        assert not label.provenance.is_strong_evidence()

    def test_unknown_not_valid_for_research(self):
        label = EvidenceLabel(provenance=EP.UNKNOWN)
        assert not label.provenance.is_valid_for_research()

    def test_synthetic_cannot_be_propagated_to_backtest(self):
        """Synthetic data must not flow to backtest."""
        from data_engine.evidence import propagate_evidence
        label = EvidenceLabel(provenance=EP.SYNTHETIC)
        with pytest.raises(ValueError):
            propagate_evidence(label, "backtest")


# ═══════════════════════════════════════════════════════
# SECURITY TESTS
# ═══════════════════════════════════════════════════════

class TestSecurity:
    """Test security controls."""

    def test_sanitize_removes_script_tags(self):
        """Sanitization must remove script tags."""
        from data_engine.security import sanitize_dataset_for_llm
        data = {"content": "<script>alert('xss')</script> price: 100"}
        sanitized = sanitize_dataset_for_llm(data)
        assert "<script>" not in sanitized["content"]

    def test_secret_protection_redacts_api_keys(self):
        """Secret fields must be redacted."""
        from data_engine.security import protect_secrets
        data = {"api_key": "sk-1234567890abcdef", "name": "test"}
        protected = protect_secrets(data)
        assert protected["api_key"] == "***REDACTED***"

    def test_immutable_provenance_verifies_integrity(self):
        """Provenance integrity must be verifiable."""
        from data_engine.security import ImmutableProvenance
        record = {"dataset_id": "test", "version": "v1.0.0"}
        immutable = ImmutableProvenance(record)
        assert immutable.verify_integrity() is True
        data = immutable.data
        data["dataset_id"] = "modified"  # Won't affect original
        assert immutable.verify_integrity() is True

    def test_no_eval_or_exec_in_source(self):
        """Source must not contain eval() or exec() calls."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    # Check for eval( or exec( as function calls (not in comments/strings)
                    # Simple check: look for 'eval(' or 'exec(' patterns
                    if 'eval(' in content or 'exec(' in content:
                        # Exclude comments and strings
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            stripped = line.strip()
                            if ('eval(' in stripped or 'exec(' in stripped) and not stripped.startswith('#'):
                                if "'eval'" not in stripped and '"eval"' not in stripped:
                                    pytest.fail(f"Found eval/exec in {filepath}:{i}: {stripped}")

    def test_no_subprocess_in_source(self):
        """Source must not use subprocess."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'subprocess' in content:
                        pytest.fail(f"Found subprocess in {filepath}")

    def test_no_pickle_in_source(self):
        """Source must not use pickle."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'pickle' in content:
                        pytest.fail(f"Found pickle in {filepath}")

    def test_os_popen_found_in_security(self):
        """CRITICAL: os.popen() found in security.py - potential shell injection."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'os.popen' in content:
                        pytest.fail(f"CRITICAL: os.popen() found in {filepath} - shell injection vulnerability")

    def test_no_unsafe_patterns_in_source(self):
        """Regression test: source must NOT contain os.popen, subprocess, eval, exec, or pickle."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        dangerous_patterns = ['os.popen', 'subprocess.', 'eval(', 'exec(', 'pickle']
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    for pattern in dangerous_patterns:
                        if pattern in content:
                            pytest.fail(
                                f"CRITICAL: '{pattern}' found in {filepath} — "
                                f"unsafe execution pattern detected"
                            )

    def test_no_utcnow_in_source(self):
        """Regression test: datetime.utcnow() must NOT be used anywhere in source.

        Must use datetime.now(datetime.UTC) for timezone-aware timestamps.
        """
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'utcnow' in content:
                        pytest.fail(
                            f"CRITICAL: datetime.utcnow() found in {filepath} — "
                            f"use datetime.now(datetime.UTC) instead"
                        )

    def test_datetime_utc_now_used(self):
        """Verify datetime.now(datetime.UTC) is used for timezone-aware timestamps."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        found_datetime_utc = False
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    if 'datetime.now(UTC)' in content or 'datetime.now(datetime.UTC)' in content:
                        found_datetime_utc = True
                        break
        assert found_datetime_utc, "datetime.now(datetime.UTC) must be used for timezone-aware timestamps"


# ═══════════════════════════════════════════════════════
# NORMALIZATION AUDIT
# ═══════════════════════════════════════════════════════

class TestNormalizationAudit:
    """Test whether normalization is implemented."""

    def test_normalization_module_does_not_exist(self):
        """NORMALIZATION IS NOT IMPLEMENTED."""
        import os
        norm_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'data_engine', 'normalization.py')
        assert not os.path.exists(norm_path), "normalization.py should not exist (it's not implemented)"


# ═══════════════════════════════════════════════════════
# GOLD RESEARCH INTEGRITY
# ═══════════════════════════════════════════════════════

class TestGoldResearchIntegrity:
    """Verify data engine did not modify gold research."""

    def test_xau_usd_instrument_correct(self):
        """XAU/USD instrument must be correct."""
        inst = create_xau_usd_instrument()
        assert inst.symbol == "XAU/USD"
        assert inst.asset_class.value == "metal"

    def test_data_engine_does_not_contain_strategy_logic(self):
        """Data Engine must not contain K3 strategy parameters."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    # Data engine should not reference K3 strategy parameters
                    if 'EMA20 > EMA50 > EMA200' in content or 'K3 Unified' in content:
                        pytest.fail(f"Data engine contains strategy logic in {filepath}")

    def test_no_live_trading_code(self):
        """No live trading code must exist."""
        import os
        src_dir = os.path.join(os.path.dirname(__file__), '..', 'src')
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                if f.endswith('.py'):
                    filepath = os.path.join(root, f)
                    content = open(filepath).read()
                    # Check for common trading execution patterns
                    for pattern in ['place_order', 'market_order', 'execute_trade', 'broker.connect']:
                        if pattern in content:
                            pytest.fail(f"Found potential trading execution code in {filepath}")
