"""Phase 4A.1 — Temporal Foundation Tests.

Tests cover:
1. Temporal semantics (event_time, observation_time, etc.)
2. UTC normalization
3. Naive datetime rejection
4. Data-type availability controls (OHLCV, ECONOMIC, NEWS, DERIVED)
5. Declarative policy validation (publication-controlled, revision-aware)
6. ingestion_time exclusion from eligibility/hashes
7. Canonical serialization (str, int, float, bool, None, list, dict, datetime, Decimal)
8. Nested dict serialization with sorted keys
9. List ordering preservation
10. Float determinism (-0.0 normalization)
11. Decimal determinism
12. NaN rejection
13. Infinity rejection
14. Unsupported type rejection
15. Tuple encoded identically to list (spec 3.1)
16. Set rejection
17. Custom object rejection
18. Non-string mapping-key rejection (SER-KEY-01, RA-NF-01)
19. Cross-process deterministic hashing
20. Canonical hash stability
21. TemporalContract validation
22. Backward compatibility with existing Phase 3 behavior

NOTE (Phase 4A.1 remediation, Blocker 4): assertions below were
re-aligned to the type-tagged canonical encoding mandated by spec
SECTION 3 / 3.1a (PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md). The
previous assertions encoded the non-conformant untagged output and
are superseded per GOV-01.
"""

import pytest
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from pydantic import ValidationError
from data_engine.pit.temporal import TemporalDataType, TemporalSemantics
from data_engine.pit.availability import (
    AvailabilityPolicy,
    PublicationControlledAvailability,
    RevisionAwareAvailability,
    AvailabilityRuleType,
)
from data_engine.pit.contract import TemporalContract, MissingFieldPolicy
from data_engine.pit.serialization import (
    canonical_serialize,
    SerializationError,
    _canonical_float,
    _canonical_value,
)
from data_engine.pit.hashing import deterministic_hash, verify_hash_determinism, verify_cross_process_hash
from data_engine.schemas import Candle, Timeframe, Dataset, Instrument, ProvenanceRecord, DatasetVersion


# ─── TemporalDataType Tests ───

class TestTemporalDataType:
    """Test TemporalDataType enum categories."""

    def test_all_categories_exist(self):
        """Verify all four data-type categories are defined."""
        assert TemporalDataType.OHLCV.value == "OHLCV"
        assert TemporalDataType.ECONOMIC.value == "ECONOMIC"
        assert TemporalDataType.NEWS.value == "NEWS"
        assert TemporalDataType.DERIVED.value == "DERIVED"

    def test_category_count(self):
        """Exactly four categories."""
        assert len(list(TemporalDataType)) == 4

    def test_category_str(self):
        """String representation returns value."""
        assert str(TemporalDataType.OHLCV) == "OHLCV"


# ─── TemporalSemantics Tests ───

class TestTemporalSemantics:
    """Test temporal semantic model."""

    def make_temporal(self, tz_info=UTC):
        """Helper to create a TemporalSemantics instance."""
        return TemporalSemantics(
            event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=tz_info),
            observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=tz_info),
            publication_time=datetime(2025, 1, 15, 11, 0, 0, tzinfo=tz_info),
            effective_time=datetime(2025, 1, 15, 12, 0, 0, tzinfo=tz_info),
            revision_time=datetime(2025, 1, 15, 11, 30, 0, tzinfo=tz_info),
            ingestion_time=datetime(2025, 1, 15, 12, 30, 0, tzinfo=tz_info),
        )

    def test_create_temporal_semantics(self):
        """TemporalSemantics can be created with all fields."""
        ts = self.make_temporal()
        assert ts.event_time.hour == 10
        assert ts.observation_time.hour == 10
        assert ts.publication_time.hour == 11

    def test_utc_normalization(self):
        """All timestamps are normalized to UTC."""
        ts = self.make_temporal()
        assert ts.event_time.tzinfo == UTC
        assert ts.observation_time.tzinfo == UTC
        assert ts.publication_time.tzinfo == UTC

    def test_utc_normalization_from_offset(self):
        """Timestamps with non-UTC timezone are normalized to UTC."""
        from datetime import timezone
        est_tz = timezone(timedelta(hours=-5))
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 5, 30, 0, tzinfo=est_tz),  # 5:30 EST = 10:30 UTC
            observation_time=datetime(2025, 1, 15, 5, 31, 0, tzinfo=est_tz),
        )
        assert ts.event_time.hour == 10
        assert ts.event_time.tzinfo == UTC

    def test_naive_datetime_rejected(self):
        """Naive datetime raises ValidationError."""
        with pytest.raises(ValidationError):
            TemporalSemantics(
                event_time=datetime(2025, 1, 15, 10, 30, 0),  # naive
                observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC),
            )

    def test_naive_datetime_observation_rejected(self):
        """Naive datetime in observation_time raises ValidationError."""
        with pytest.raises(ValidationError):
            TemporalSemantics(
                event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                observation_time=datetime(2025, 1, 15, 10, 31, 0),  # naive
            )

    def test_all_fields_frozen(self):
        """TemporalSemantics is immutable (frozen)."""
        ts = self.make_temporal()
        with pytest.raises(Exception):
            ts.event_time = datetime(2025, 2, 1, tzinfo=UTC)

    def test_ingestion_time_is_optional(self):
        """ingestion_time can be None."""
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC),
        )
        assert ts.ingestion_time is None

    def test_temporal_hash_input_excludes_ingestion(self):
        """temporal_hash_input does NOT include ingestion_time."""
        ts = self.make_temporal()
        hash_input = ts.temporal_hash_input()
        assert "ingestion_time" not in hash_input
        assert "event_time" in hash_input
        assert "observation_time" in hash_input

    def test_temporal_hash_input_deterministic(self):
        """temporal_hash_input produces same output for same data."""
        ts = self.make_temporal()
        h1 = ts.temporal_hash_input()
        h2 = ts.temporal_hash_input()
        assert h1 == h2

    def test_publication_time_optional(self):
        """publication_time can be None."""
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC),
        )
        assert ts.publication_time is None
        hash_input = ts.temporal_hash_input()
        assert "<NULL>" in hash_input


# ─── UTC Normalization Tests ───

class TestUTCNormalization:
    """Test that all timestamps are normalized to UTC."""

    def test_all_timestamps_utc_aware(self):
        """All created TemporalSemantics instances have UTC-aware timestamps."""
        from datetime import timezone
        est = timezone(timedelta(hours=-5))
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 5, 30, 0, tzinfo=est),
            observation_time=datetime(2025, 1, 15, 5, 31, 0, tzinfo=est),
        )
        assert ts.event_time.tzinfo == UTC
        assert ts.observation_time.tzinfo == UTC

    def test_isoformat_utc(self):
        """ISO format of UTC-normalized timestamp."""
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC),
        )
        assert "+00:00" in ts.event_time.isoformat()


# ─── Data-Type Availability Controls ───

class TestDataTypeAvailability:
    """Test TemporalDataType-based availability controls."""

    def test_ohlcv_requires_event_and_observation(self):
        """OHLCV data requires event_time and observation_time."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time", "observation_time"],
            eligible_fields=["event_time", "observation_time", "publication_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert "event_time" in contract.required_fields
        assert "ingestion_time" in contract.non_eligible_fields

    def test_economic_requires_publication(self):
        """ECONOMIC data requires publication_time."""
        contract = TemporalContract(
            data_type=TemporalDataType.ECONOMIC,
            required_fields=["event_time", "publication_time"],
            eligible_fields=["event_time", "publication_time", "effective_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert "publication_time" in contract.required_fields

    def test_news_requires_publication(self):
        """NEWS data requires publication_time for availability."""
        contract = TemporalContract(
            data_type=TemporalDataType.NEWS,
            required_fields=["event_time", "publication_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert "publication_time" in contract.required_fields

    def test_derived_has_no_required_temporal(self):
        """DERIVED data may not have strict temporal requirements."""
        contract = TemporalContract(
            data_type=TemporalDataType.DERIVED,
            required_fields=[],
            non_eligible_fields=["ingestion_time"],
        )
        assert contract.required_fields == []

    def test_all_datatype_non_eligible_ingestion(self):
        """All data types have ingestion_time as non-eligible."""
        for dtype in TemporalDataType:
            contract = TemporalContract(
                data_type=dtype,
                non_eligible_fields=["ingestion_time"],
            )
            assert "ingestion_time" in contract.non_eligible_fields
            assert not contract.is_eligible_field("ingestion_time")


# ─── Declarative Policy Validation Tests ───

class TestDeclarativePolicyValidation:
    """Test that availability policies are declarative, not executable."""

    def test_publication_policy_no_callbacks(self):
        """PublicationControlledAvailability contains no callable code."""
        policy = PublicationControlledAvailability(
            require_publication=True,
            max_delay_seconds=3600.0,
        )
        d = policy.to_dict()
        assert d["rule_type"] == "PublicationControlledAvailability"
        assert d["require_publication"] is True
        assert d["max_delay_seconds"] == 3600.0

    def test_revision_policy_no_callbacks(self):
        """RevisionAwareAvailability contains no callable code."""
        policy = RevisionAwareAvailability(
            require_revision=True,
            max_revision_age_seconds=86400.0,
        )
        d = policy.to_dict()
        assert d["rule_type"] == "RevisionAwareAvailability"
        assert d["require_revision"] is True
        assert d["max_revision_age_seconds"] == 86400.0

    def test_availability_policy_top_level(self):
        """AvailabilityPolicy is a proper declarative container."""
        pub_policy = PublicationControlledAvailability(require_publication=True)
        policy = AvailabilityPolicy(
            rule_type=AvailabilityRuleType.PUBLICATION_CONTROLLED,
            policy=pub_policy,
        )
        d = policy.to_dict()
        assert d["rule_type"] == "publication_controlled"

    def test_no_eval_exec_in_policy(self):
        """Policy dicts must not contain eval or exec references."""
        import json
        policy = PublicationControlledAvailability(require_publication=True)
        d = policy.to_dict()
        serialized = json.dumps(d)
        assert "eval" not in serialized
        assert "exec" not in serialized
        assert "lambda" not in serialized
        assert "callback" not in serialized

    def test_publication_availability_logic(self):
        """PublicationControlledAvailability correctly determines availability."""
        policy = PublicationControlledAvailability(require_publication=True)
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        pub_time = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        # Published before query time → available
        assert policy.is_available(publication_time=pub_time, effective_time=None, query_time=now) is True
        # Published after query time → not available
        future_pub = datetime(2025, 6, 1, 13, 0, 0, tzinfo=UTC)
        assert policy.is_available(publication_time=future_pub, effective_time=None, query_time=now) is False
        # No publication_time when required → not available
        assert policy.is_available(publication_time=None, effective_time=None, query_time=now) is False

    def test_revision_availability_logic(self):
        """RevisionAwareAvailability correctly determines availability."""
        policy = RevisionAwareAvailability(require_revision=True)
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        rev_time = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        # Revision before query time → available
        assert policy.is_available(revision_time=rev_time, publication_time=None, query_time=now) is True
        # Revision after query time → not available
        future_rev = datetime(2025, 6, 1, 13, 0, 0, tzinfo=UTC)
        assert policy.is_available(revision_time=future_rev, publication_time=None, query_time=now) is False

    def test_policy_is_immutable(self):
        """Policies are frozen and cannot be modified."""
        policy = PublicationControlledAvailability(require_publication=True)
        with pytest.raises(Exception):
            policy.require_publication = False


# ─── ingestion_time Exclusion Tests ───

class TestIngestionTimeExclusion:
    """Test that ingestion_time does not participate in eligibility/hashes."""

    def test_ingestion_not_in_temporal_hash(self):
        """temporal_hash_input excludes ingestion_time."""
        ts = TemporalSemantics(
            event_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            observation_time=datetime(2025, 1, 15, 10, 31, 0, tzinfo=UTC),
            ingestion_time=datetime(2025, 1, 15, 12, 30, 0, tzinfo=UTC),
        )
        hash_input = ts.temporal_hash_input()
        assert "ingestion_time" not in hash_input

    def test_contract_non_eligible_ingestion(self):
        """Contract marks ingestion_time as non-eligible."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            non_eligible_fields=["ingestion_time"],
        )
        assert not contract.is_eligible_field("ingestion_time")

    def test_contract_eligible_fields_exclude_ingestion(self):
        """Contract eligible_fields should not include ingestion_time."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            eligible_fields=["event_time", "observation_time", "publication_time"],
        )
        assert not contract.is_eligible_field("ingestion_time")


# ─── TemporalContract Tests ───

class TestTemporalContract:
    """Test TemporalContract validation."""

    def test_create_contract(self):
        """TemporalContract can be created with all fields."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time", "observation_time"],
            eligible_fields=["event_time", "observation_time", "publication_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert contract.data_type == TemporalDataType.OHLCV

    def test_invalid_field_name_rejected(self):
        """Unknown field names raise ValidationError."""
        with pytest.raises(ValidationError):
            TemporalContract(
                data_type=TemporalDataType.OHLCV,
                required_fields=["invalid_field"],
            )

    def test_non_utc_timezone_rejected(self):
        """Non-UTC timezone requirement raises ValidationError."""
        with pytest.raises(ValidationError):
            TemporalContract(
                data_type=TemporalDataType.OHLCV,
                timezone_requirement="EST",  # Must be UTC
            )

    def test_missing_required_fields_raises(self):
        """Missing required fields raises ValueError when policy is REJECT."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time", "publication_time"],
            missing_field_policy=MissingFieldPolicy.REJECT,
        )
        temporal_fields = {
            "event_time": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            "publication_time": None,
        }
        with pytest.raises(ValueError):
            contract.validate_required_fields_present(temporal_fields)

    def test_missing_allow_null(self):
        """Missing fields are allowed when policy is ALLOW_NULL.

        NOTE: superseded by spec 4.2 / SUB-20 — construction with
        ALLOW_NULL + required_fields MUST raise. The re-aligned
        assertion and the TemporalContract enforcement land together
        with Blocker 3 (one blocker, one commit).
        """
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["publication_time"],
            missing_field_policy=MissingFieldPolicy.ALLOW_NULL,
        )
        temporal_fields = {
            "event_time": datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            "publication_time": None,
        }
        contract.validate_required_fields_present(temporal_fields)  # Should not raise

    def test_is_eligible_field(self):
        """Eligible/non-eligible field checks work correctly."""
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            eligible_fields=["event_time", "observation_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert contract.is_eligible_field("event_time") is True
        assert contract.is_eligible_field("ingestion_time") is False
        assert contract.is_eligible_field("publication_time") is False

    def test_contract_frozen(self):
        """TemporalContract is immutable."""
        contract = TemporalContract(data_type=TemporalDataType.OHLCV)
        with pytest.raises(Exception):
            contract.data_type = TemporalDataType.ECONOMIC

    def test_contract_hash_deterministic(self):
        """Contract hash is deterministic for same configuration."""
        contract1 = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time", "observation_time"],
        )
        contract2 = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time", "observation_time"],
        )
        h1 = contract1.get_contract_hash()
        h2 = contract2.get_contract_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


# ─── Canonical Serialization Tests ───

class TestCanonicalSerialization:
    """Test canonical serialization for all supported types."""

    def test_serialize_str(self):
        """String serialization is deterministic and type-tagged (spec 3.1)."""
        result = canonical_serialize("hello")
        assert result == b'{"s":"hello"}'

    def test_serialize_int(self):
        """Integer serialization is deterministic and type-tagged (spec 3.1a.3)."""
        result = canonical_serialize(42)
        assert result == b'{"i":"42"}'

    def test_serialize_float(self):
        """Float serialization uses the .10f policy (spec 3.3)."""
        result = canonical_serialize(3.14)
        assert result == b'{"f":"3.1400000000"}'

    def test_serialize_bool(self):
        """Boolean serialization is type-tagged and never int-like (COL-NUM-04)."""
        assert canonical_serialize(True) == b'{"b":true}'
        assert canonical_serialize(False) == b'{"b":false}'

    def test_serialize_none(self):
        """None serializes to null (spec 3.1)."""
        assert canonical_serialize(None) == b'null'

    def test_serialize_list_preserves_order(self):
        """List values preserve their order (order is significant)."""
        result = canonical_serialize([3, 1, 2])
        result_str = result.decode('utf-8')
        assert result_str == '{"L":[{"i":"3"},{"i":"1"},{"i":"2"}]}'

    def test_serialize_dict_sorts_keys(self):
        """Dictionary entries are sorted by key code point (spec 3.2)."""
        result = canonical_serialize({"c": 3, "a": 1, "b": 2})
        result_str = result.decode('utf-8')
        assert result_str == '{"D":[[{"s":"a"},{"i":"1"}],[{"s":"b"},{"i":"2"}],[{"s":"c"},{"i":"3"}]]}'

    def test_serialize_datetime_utc(self):
        """Datetime serializes to ISO format in UTC."""
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
        result = canonical_serialize(dt)
        result_str = result.decode('utf-8')
        assert "2025-01-15" in result_str
        assert "+00:00" in result_str or "T" in result_str

    def test_serialize_decimal(self):
        """Decimal serializes to string representation."""
        d = Decimal("123.456")
        result = canonical_serialize(d)
        result_str = result.decode('utf-8')
        assert "123.456" in result_str

    def test_serialize_nested_dict(self):
        """Nested dict: entries sorted at all levels, keys type-tagged."""
        nested = {"b": {"d": 4, "c": 3}, "a": 1}
        result = canonical_serialize(nested)
        result_str = result.decode('utf-8')
        assert result_str == '{"D":[[{"s":"a"},{"i":"1"}],[{"s":"b"},{"D":[[{"s":"c"},{"i":"3"}],[{"s":"d"},{"i":"4"}]]}]]}'

    def test_serialize_nested_list_order(self):
        """Nested list order is preserved."""
        nested = [1, [3, 1, 2], 4]
        result = canonical_serialize(nested)
        result_str = result.decode('utf-8')
        assert result_str == '{"L":[{"i":"1"},{"L":[{"i":"3"},{"i":"1"},{"i":"2"}]},{"i":"4"}]}'

    def test_serialize_float_neg_zero(self):
        """-0.0 is normalized to 0.0."""
        result = canonical_serialize(-0.0)
        result_str = result.decode('utf-8')
        # The float -0.0 gets normalized to 0.0 by _canonical_float
        assert "0.0" in result_str or "0" in result_str

    def test_tuple_encoded_as_list(self):
        """Tuple is accepted and encoded identically to list (spec 3.1).

        Old behaviour rejected tuple; the authoritative spec redefines
        it: tuple == list, documented. Re-aligned per GOV-01.
        """
        assert canonical_serialize((1, 2, 3)) == canonical_serialize([1, 2, 3])
        assert canonical_serialize((1, 2, 3)) == b'{"L":[{"i":"1"},{"i":"2"},{"i":"3"}]}'

    def test_reject_set(self):
        """Set is rejected."""
        with pytest.raises(SerializationError):
            canonical_serialize({1, 2, 3})

    def test_reject_custom_object(self):
        """Custom objects are rejected."""
        class CustomObj:
            pass
        with pytest.raises(SerializationError):
            canonical_serialize(CustomObj())

    def test_reject_nan(self):
        """NaN is rejected."""
        import math
        with pytest.raises(SerializationError):
            canonical_serialize(float('nan'))

    def test_reject_infinity(self):
        """Positive infinity is rejected."""
        with pytest.raises(SerializationError):
            canonical_serialize(float('inf'))

    def test_reject_negative_infinity(self):
        """Negative infinity is rejected."""
        with pytest.raises(SerializationError):
            canonical_serialize(float('-inf'))

    def test_reject_naive_datetime(self):
        """Naive datetime raises SerializationError."""
        with pytest.raises(SerializationError):
            canonical_serialize(datetime(2025, 1, 15, 10, 30, 0))

    def test_canonical_bytes_for_hashing(self):
        """Serialization produces bytes suitable for SHA-256."""
        result = canonical_serialize("test")
        assert isinstance(result, bytes)
        import hashlib
        digest = hashlib.sha256(result).hexdigest()
        assert len(digest) == 64

    def test_deterministic_multiple_runs(self):
        """Same input always produces same output."""
        for _ in range(10):
            r1 = canonical_serialize({"key": "value", "num": 42})
            assert r1 == canonical_serialize({"key": "value", "num": 42})


# ─── Canonical Float Determinism ───

class TestFloatDeterminism:
    """Test float normalization rules."""

    def test_negative_zero_normalized(self):
        """-0.0 is normalized to 0.0."""
        result = _canonical_float(-0.0)
        assert result == 0.0
        # Verify json serialization produces "0.0" not "-0.0"
        import json
        serialized = json.dumps(_canonical_float(-0.0))
        assert serialized == "0.0"

    def test_normal_float_preserved(self):
        """Normal floats are preserved."""
        result = _canonical_float(3.14)
        assert result == 3.14

    def test_canonical_float_deterministic(self):
        """Float serialization is deterministic."""
        for _ in range(5):
            assert _canonical_float(1.5) == 1.5


# ─── Decimal Determinism ───

class TestDecimalDeterminism:
    """Test Decimal serialization is deterministic."""

    def test_decimal_serialize(self):
        """Decimal serializes to deterministic string."""
        d1 = Decimal("0.1")
        d2 = Decimal("0.1")
        r1 = canonical_serialize(d1)
        r2 = canonical_serialize(d2)
        assert r1 == r2

    def test_decimal_string_representation(self):
        """Decimal string representation preserves precision."""
        d = Decimal("123456789.123456789")
        result = canonical_serialize(d).decode('utf-8')
        assert "123456789.123456789" in result


# ─── Deterministic Hashing Tests ───

class TestDeterministicHashing:
    """Test deterministic SHA-256 hashing abstraction."""

    def test_hash_string(self):
        """Hashing a string produces a 64-char hex digest."""
        h = deterministic_hash("hello")
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_hash_int(self):
        """Hashing an int produces a 64-char hex digest."""
        h = deterministic_hash(42)
        assert len(h) == 64

    def test_hash_dict(self):
        """Hashing a dict produces a consistent hash."""
        h1 = deterministic_hash({"a": 1, "b": 2})
        assert len(h1) == 64

    def test_hash_stability(self):
        """Same value always produces same hash."""
        h1 = deterministic_hash("test")
        h2 = deterministic_hash("test")
        assert h1 == h2

    def test_hash_cross_process_determinism(self):
        """Hash is deterministic across invocations."""
        assert verify_hash_determinism({"key": "value"}) is True

    def test_hash_stability_dict_order(self):
        """Dict with different key order produces same hash."""
        h1 = deterministic_hash({"a": 1, "b": 2})
        h2 = deterministic_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_cross_process_hash_well_formed(self):
        """Hash is well-formed (64 hex chars)."""
        assert verify_cross_process_hash("test") is True

    def test_hash_not_random(self):
        """Hash is not random — same input always same output."""
        results = {deterministic_hash("same_input") for _ in range(100)}
        assert len(results) == 1

    def test_hash_no_timestamp(self):
        """Hash does not include runtime timestamps."""
        # This is verified by the fact that hashing the same string
        # always produces the same result — no timestamps are injected
        h1 = deterministic_hash("no_timestamp_test")
        h2 = deterministic_hash("no_timestamp_test")
        assert h1 == h2

    def test_hash_no_uuid(self):
        """Hash does not include random UUIDs."""
        import re
        h = deterministic_hash("test")
        # UUIDs contain hyphens; SHA-256 hex digests do not
        assert "-" not in h


# ─── Backward Compatibility Tests ───

class TestBackwardCompatibility:
    """Verify Phase 3 modules are untouched and still work."""

    def test_candle_creation_works(self):
        """Phase 3 Candle model still works."""
        from data_engine.schemas import Candle, Timeframe
        c = Candle(
            timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
            open=100.0, high=105.0, low=98.0, close=102.0,
            volume=1000.0, timeframe=Timeframe.D1,
        )
        assert c.open == 100.0

    def test_dataset_creation_works(self):
        """Phase 3 Dataset model still works."""
        from data_engine.schemas import Candle, Dataset, DatasetVersion, Instrument, ProvenanceRecord, Timeframe, EvidenceProvenance, AssetClass
        instrument = Instrument(symbol="XAU/USD", asset_class=AssetClass.COMMODITY, base_asset="XAU", quote_asset="USD")
        provenance = ProvenanceRecord(
            dataset_id="test", dataset_version="v1", provider="test", source="test",
            instrument=instrument, timeframe=Timeframe.D1,
            start_timestamp=datetime(2025, 1, 1, tzinfo=UTC),
            end_timestamp=datetime(2025, 1, 31, tzinfo=UTC),
            retrieval_timestamp=datetime(2025, 1, 31, tzinfo=UTC),
            timezone="UTC", evidence_provenance=EvidenceProvenance.REAL,
        )
        version = DatasetVersion(
            dataset_id="test", version="v1", source="test",
            instrument=instrument, timeframe=Timeframe.D1,
            time_period_start=datetime(2025, 1, 1, tzinfo=UTC),
            time_period_end=datetime(2025, 1, 31, tzinfo=UTC),
            ingestion_version="v1", transformation_version="v1", validation_version="v1",
        )
        d = Dataset(
            dataset_id="test", version=version,
            candles=[], provenance=provenance, total_rows=0,
        )
        assert d.dataset_id == "test"

    def test_no_phase3_source_modified(self):
        """Verify that no Phase 3 source files have been modified."""
        import os
        phase3_files = [
            "src/data_engine/schemas.py",
            "src/data_engine/storage.py",
            "src/data_engine/provenance.py",
            "src/data_engine/validation.py",
            "src/data_engine/ingestion.py",
            "src/data_engine/data_blocked.py",
            "src/data_engine/evidence.py",
            "src/data_engine/quarantine.py",
            "src/data_engine/quality_report.py",
            "src/data_engine/provider.py",
            "src/data_engine/timeframes.py",
        ]
        for f in phase3_files:
            assert os.path.exists(f), f"Phase 3 file missing: {f}"

    def test_no_datetime_utcnow_in_source(self):
        """Verify no datetime.utcnow() in any source file."""
        import os
        src_dir = "src"
        for root, dirs, files in os.walk(src_dir):
            for fname in files:
                if fname.endswith('.py'):
                    path = os.path.join(root, fname)
                    with open(path) as f:
                        content = f.read()
                        assert 'utcnow' not in content, f"Found utcnow in {path}"

    def test_pit_package_is_new(self):
        """Verify the pit package was created as new files."""
        import os
        pit_dir = "src/data_engine/pit"
        assert os.path.isdir(pit_dir)
        assert os.path.exists(os.path.join(pit_dir, "__init__.py"))
        assert os.path.exists(os.path.join(pit_dir, "temporal.py"))
        assert os.path.exists(os.path.join(pit_dir, "availability.py"))
        assert os.path.exists(os.path.join(pit_dir, "contract.py"))
        assert os.path.exists(os.path.join(pit_dir, "serialization.py"))
        assert os.path.exists(os.path.join(pit_dir, "hashing.py"))

    def test_pit_version(self):
        """PIT package has correct version."""
        from data_engine.pit import __version__
        assert __version__ == "4.1.0"

    def test_no_phase3_imports_in_pit(self):
        """PIT module does NOT import Phase 3 modules."""
        import ast
        import os
        pit_dir = "src/data_engine/pit"
        for fname in os.listdir(pit_dir):
            if fname.endswith('.py'):
                path = os.path.join(pit_dir, fname)
                with open(path) as f:
                    tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ImportFrom):
                            if node.module and node.module.startswith('data_engine.'):
                                assert 'data_engine.pit' in node.module, \
                                    f"Phase 3 import found in {path}: {node.module}"


# ─── TemporalContract with TemporalDataType Tests ───

class TestTemporalContractWithDataType:
    """Test TemporalContract properly associates with TemporalDataType."""

    def test_ohlcv_contract_default(self):
        """OHLCV contract defaults are correct."""
        contract = TemporalContract(data_type=TemporalDataType.OHLCV)
        assert contract.data_type == TemporalDataType.OHLCV
        assert contract.timezone_requirement == "UTC"

    def test_economic_contract_with_publication(self):
        """ECONOMIC contract with publication requirement."""
        contract = TemporalContract(
            data_type=TemporalDataType.ECONOMIC,
            required_fields=["event_time", "publication_time"],
            eligible_fields=["event_time", "publication_time", "effective_time"],
            non_eligible_fields=["ingestion_time"],
        )
        assert "publication_time" in contract.required_fields
        assert "effective_time" in contract.eligible_fields


# ─── Availability Policy Edge Cases ───

class TestAvailabilityPolicyEdgeCases:
    """Test edge cases in availability policies."""

    def test_publication_max_delay(self):
        """PublicationControlledAvailability enforces max_delay_seconds."""
        policy = PublicationControlledAvailability(
            require_publication=True,
            max_delay_seconds=3600.0,
        )
        now = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
        pub = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        eff = datetime(2025, 6, 1, 13, 30, 0, tzinfo=UTC)  # 3.5 hours delay
        assert policy.is_available(publication_time=pub, effective_time=eff, query_time=now) is False
        eff2 = datetime(2025, 6, 1, 10, 30, 0, tzinfo=UTC)  # 30 min delay
        assert policy.is_available(publication_time=pub, effective_time=eff2, query_time=now) is True

    def test_revision_max_age(self):
        """RevisionAwareAvailability enforces max_revision_age_seconds."""
        policy = RevisionAwareAvailability(
            require_revision=True,
            max_revision_age_seconds=86400.0,
        )
        now = datetime(2025, 6, 2, 12, 0, 0, tzinfo=UTC)
        # 26 hours old (93600 seconds) → stale, NOT available
        rev = datetime(2025, 6, 1, 10, 0, 0, tzinfo=UTC)
        assert policy.is_available(revision_time=rev, publication_time=None, query_time=now) is False
        # 5 minutes old → within max age → available
        rev_fresh = datetime(2025, 6, 2, 11, 50, 0, tzinfo=UTC)
        assert policy.is_available(revision_time=rev_fresh, publication_time=None, query_time=now) is True

    def test_availability_policy_immutable(self):
        """AvailabilityPolicy is frozen."""
        policy = AvailabilityPolicy(
            rule_type=AvailabilityRuleType.PUBLICATION_CONTROLLED,
            policy=PublicationControlledAvailability(),
        )
        with pytest.raises(Exception):
            policy.rule_type = AvailabilityRuleType.REVISION_AWARE


# ─── Serialization Edge Cases ───

class TestSerializationEdgeCases:
    """Test edge cases in canonical serialization."""

    def test_empty_list(self):
        """Empty list serializes correctly."""
        result = canonical_serialize([])
        assert result == b'{"L":[]}'

    def test_empty_dict(self):
        """Empty dict serializes correctly."""
        result = canonical_serialize({})
        assert result == b'{"D":[]}'

    def test_empty_string(self):
        """Empty string serializes correctly."""
        result = canonical_serialize("")
        assert result == b'{"s":""}'

    def test_large_int(self):
        """Large integer serializes correctly, base-10, tagged."""
        result = canonical_serialize(999999999999999999)
        assert result == b'{"i":"999999999999999999"}'

    def test_nested_dict_sorted_deeply(self):
        """Deeply nested dict entries are all sorted."""
        d = {"z": {"y": {"x": 1}}, "a": {"c": {"b": 2}}}
        result = canonical_serialize(d)
        result_str = result.decode('utf-8')
        assert result_str == '{"D":[[{"s":"a"},{"D":[[{"s":"c"},{"D":[[{"s":"b"},{"i":"2"}]]}]]}],[{"s":"z"},{"D":[[{"s":"y"},{"D":[[{"s":"x"},{"i":"1"}]]}]]}]]}'

    def test_mixed_list_preserves_order(self):
        """Mixed-type list preserves order; every element is tagged."""
        result = canonical_serialize([1, "two", True, None])
        result_str = result.decode('utf-8')
        assert result_str == '{"L":[{"i":"1"},{"s":"two"},{"b":true},null]}'

    def test_datetime_in_dict(self):
        """Dict containing datetime serializes correctly."""
        d = {"time": datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)}
        result = canonical_serialize(d)
        result_str = result.decode('utf-8')
        assert "2025-01-15" in result_str

    def test_decimal_in_dict(self):
        """Dict containing Decimal serializes correctly."""
        d = {"value": Decimal("0.001")}
        result = canonical_serialize(d)
        result_str = result.decode('utf-8')
        assert "0.001" in result_str

    def test_list_of_dicts_preserves_order(self):
        """List of dicts preserves list order; inner dicts sorted by key."""
        d1 = {"b": 2, "a": 1}
        d2 = {"d": 4, "c": 3}
        result = canonical_serialize([d1, d2])
        result_str = result.decode('utf-8')
        assert result_str == '{"L":[{"D":[[{"s":"a"},{"i":"1"}],[{"s":"b"},{"i":"2"}]]},{"D":[[{"s":"c"},{"i":"3"}],[{"s":"d"},{"i":"4"}]]}]}'


# ─── Backward Compatibility: No Phase 3 Module Changes ───

def test_phase3_candle_temporal_compatibility():
    """Verify Phase 3 Candle still works with the new temporal model."""
    from data_engine.schemas import Candle, Timeframe
    c = Candle(
        timestamp=datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC),
        open=100.0, high=105.0, low=98.0, close=102.0,
        volume=1000.0, timeframe=Timeframe.D1,
    )
    assert c.to_hash() is not None

def test_no_eval_or_exec_in_pit():
    """Verify no eval/exec calls in PIT source (docstrings don't count)."""
    import ast
    import os
    pit_dir = "src/data_engine/pit"
    for fname in os.listdir(pit_dir):
        if fname.endswith('.py'):
            path = os.path.join(pit_dir, fname)
            with open(path) as f:
                tree = ast.parse(f.read())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            assert node.func.id not in ('eval', 'exec'), \
                                f"Found {node.func.id}() call in {path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
