# HASH FORENSIC AUDIT
**Date:** 2026-09-30
**Mode:** READ-ONLY

---

## Complete Hashing and Canonical Serialization Inventory

### 1. Candle.to_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `Candle.to_hash()` |
| **OWNER_PHASE** | Phase 1 (Candle is Phase 1 contract) |
| **INPUT_FIELDS** | ALL fields via `model_dump_json()` — timestamp, open, high, low, close, volume, timeframe, bid, ask, spread, currency, provider_timestamp |
| **CANONICALIZATION** | NONE — uses Pydantic `model_dump_json()` which is not canonical |
| **SERIALIZATION** | JSON via `model_dump_json()` |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE — no version declared |
| **WALL_CLOCK_FIELDS** | `provider_timestamp` (default_factory=_now_utc) — enters hash via model_dump_json() |
| **SCHEMA_VERSION** | NONE — no schema_version field |
| **ORDERING_RULE** | Pydantic JSON serialization order (not guaranteed deterministic across versions) |
| **NULL_RULE** | JSON null |
| **FLOAT_RULE** | Pydantic default float serialization (no -0.0 normalization, no NaN rejection) |
| **NESTED_STRUCTURE_RULE** | None (no nested structures in Candle) |
| **STATUS** | **CONTAMINATED** — wall-clock field enters identity; no canonical serialization; no allowlist |

---

### 2. ProvenanceRecord.to_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `ProvenanceRecord.to_hash()` |
| **OWNER_PHASE** | Phase 2 (ProvenanceRecord is Phase 2 contract) |
| **INPUT_FIELDS** | ALL fields via `model_dump_json()` — dataset_id, dataset_version, provider, source, instrument, timeframe, start_timestamp, end_timestamp, retrieval_timestamp, timezone, source_hash, transformation_history, validation_status, evidence_provenance |
| **CANONICALIZATION** | NONE — uses Pydantic `model_dump_json()` |
| **SERIALIZATION** | JSON via `model_dump_json()` |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | `retrieval_timestamp` — enters hash via model_dump_json() |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Pydantic JSON serialization order |
| **NULL_RULE** | JSON null |
| **FLOAT_RULE** | N/A (no floats in ProvenanceRecord) |
| **NESTED_STRUCTURE_RULE** | instrument (nested Instrument), transformation_history (list of dicts) — serialized via model_dump_json() |
| **STATUS** | **CONTAMINATED** — wall-clock field enters identity; no canonical serialization; no allowlist |

---

### 3. BacktestProvenance.compute_result_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `BacktestProvenance.compute_result_hash()` |
| **OWNER_PHASE** | Phase 3 (strategy provenance) |
| **INPUT_FIELDS** | Explicit pipe-separated formula: config_hash, dataset_hash, strategy_spec_json, trades_json, equity_json, metadata_json |
| **CANONICALIZATION** | PARTIAL — pipe-separated string concatenation |
| **SERIALIZATION** | String concatenation with pipe separator |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | EXCLUDED — `run_timestamp` explicitly excluded |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Explicit field order in pipe-separated string |
| **NULL_RULE** | String representation of None |
| **FLOAT_RULE** | Not applicable (no floats in hash input directly) |
| **NESTED_STRUCTURE_RULE** | trades_json, equity_json, metadata_json — serialized as JSON strings |
| **STATUS** | **PASS** — explicit field list; wall-clock excluded; deterministic |

---

### 4. BacktestProvenance.to_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `BacktestProvenance.to_hash()` |
| **OWNER_PHASE** | Phase 3 |
| **INPUT_FIELDS** | `model_dump(exclude_unset=True)` with known audit fields popped |
| **CANONICALIZATION** | PARTIAL — excludes known audit fields but uses Pydantic dump |
| **SERIALIZATION** | JSON via `model_dump()` |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | EXCLUDED — explicitly popped from dict before hashing |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Pydantic dump order |
| **NULL_RULE** | JSON null |
| **FLOAT_RULE** | Pydantic default |
| **NESTED_STRUCTURE_RULE** | Nested objects serialized via model_dump() |
| **STATUS** | **PARTIAL** — explicit audit field exclusion but no positive allowlist |

---

### 5. StrategySpec.to_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `StrategySpec.to_hash()` |
| **OWNER_PHASE** | Phase 3 |
| **INPUT_FIELDS** | Explicit field-by-field canonical serialization |
| **CANONICALIZATION** | YES — uses `canonical_serialize()` |
| **SERIALIZATION** | canonical_serialize() → SHA-256 |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | NONE — no wall-clock fields in StrategySpec |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Explicit field ordering in canonical_serialize() |
| **NULL_RULE** | Canonical null representation |
| **FLOAT_RULE** | Canonical float normalization |
| **NESTED_STRUCTURE_RULE** | Explicit handling via canonical_serialize() |
| **STATUS** | **PASS** — explicit allowlist; canonical serialization; deterministic |

---

### 6. BacktestConfig._compute_config_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `BacktestConfig._compute_config_hash()` |
| **OWNER_PHASE** | Phase 3 |
| **INPUT_FIELDS** | Explicit pipe-separated string: initial_capital, cost_parameters_serialized, slippage_parameters_serialized, allow_short, execution_semantics, max_position_size, seed, execution_delay |
| **CANONICALIZATION** | YES — explicit pipe-separated string |
| **SERIALIZATION** | String concatenation |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | NONE |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Explicit field order |
| **NULL_RULE** | String representation |
| **FLOAT_RULE** | String representation of float |
| **NESTED_STRUCTURE_RULE** | cost_parameters_serialized and slippage_parameters_serialized are JSON strings |
| **STATUS** | **PASS** — explicit field list; deterministic |

---

### 7. BacktestEngine._compute_dataset_hash()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `BacktestEngine._compute_dataset_hash()` |
| **OWNER_PHASE** | Phase 3 |
| **INPUT_FIELDS** | Manual pipe-separated string: dataset_id, len(candles), version |
| **CANONICALIZATION** | YES — explicit pipe-separated string |
| **SERIALIZATION** | String concatenation |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | NONE |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Explicit field order |
| **NULL_RULE** | String representation |
| **FLOAT_RULE** | N/A |
| **NESTED_STRUCTURE_RULE** | N/A |
| **STATUS** | **PASS** — explicit field list; deterministic but NOT content-based (only dataset_id, count, version) |

---

### 8. TemporalSemantics.temporal_hash_input()

| Attribute | Value |
|-----------|-------|
| **METHOD** | `TemporalSemantics.temporal_hash_input()` |
| **OWNER_PHASE** | Phase 4A.1 (pit/temporal.py) |
| **INPUT_FIELDS** | Explicit field list: event_time, observation_time, publication_time, effective_time, revision_time |
| **CANONICALIZATION** | YES — explicit pipe-separated string with ISO format |
| **SERIALIZATION** | String concatenation |
| **HASH_ALGORITHM** | N/A (returns string, not hash) |
| **ALGORITHM_VERSION** | N/A |
| **WALL_CLOCK_FIELDS** | EXCLUDED — ingestion_time explicitly excluded |
| **SCHEMA_VERSION** | N/A |
| **ORDERING_RULE** | Explicit field order |
| **NULL_RULE** | `<NULL>` string |
| **FLOAT_RULE** | N/A |
| **NESTED_STRUCTURE_RULE** | N/A |
| **STATUS** | **PASS** — explicit field list; ingestion_time excluded; deterministic |

---

### 9. deterministic_hash() (pit/hashing.py)

| Attribute | Value |
|-----------|-------|
| **METHOD** | `deterministic_hash()` |
| **OWNER_PHASE** | Phase 4A.1 |
| **INPUT_FIELDS** | Any value supported by canonical_serialize() |
| **CANONICALIZATION** | YES — uses canonical_serialize() |
| **SERIALIZATION** | canonical_serialize() → SHA-256 |
| **HASH_ALGORITHM** | SHA-256 |
| **ALGORITHM_VERSION** | NONE |
| **WALL_CLOCK_FIELDS** | NONE — no wall-clock injection |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | canonical_serialize() handles ordering |
| **NULL_RULE** | Canonical null |
| **FLOAT_RULE** | Canonical float normalization |
| **NESTED_STRUCTURE_RULE** | canonical_serialize() handles nested structures |
| **STATUS** | **PASS** — canonical serialization; deterministic; no wall-clock |

---

### 10. canonical_serialize() (pit/serialization.py)

| Attribute | Value |
|-----------|-------|
| **METHOD** | `canonical_serialize()` |
| **OWNER_PHASE** | Phase 4A.1 |
| **INPUT_FIELDS** | str, int, float, bool, None, list, dict, datetime, Decimal |
| **CANONICALIZATION** | YES — dict keys sorted, floats normalized, datetimes UTC-normalized |
| **SERIALIZATION** | JSON with sorted keys, compact separators |
| **HASH_ALGORITHM** | N/A (returns bytes) |
| **ALGORITHM_VERSION** | N/A |
| **WALL_CLOCK_FIELDS** | NONE |
| **SCHEMA_VERSION** | NONE |
| **ORDERING_RULE** | Dict keys sorted alphabetically |
| **NULL_RULE** | JSON null |
| **FLOAT_RULE** | -0.0 → 0.0; NaN rejected; Infinity rejected |
| **NESTED_STRUCTURE_RULE** | Recursive canonical serialization |
| **STATUS** | **PASS** — canonical; deterministic; well-defined |

---

## CRITICAL FINDING: Pydantic model_dump_json() as Implicit Identity Allowlist

The current architecture accidentally treats Pydantic model serialization as an identity allowlist.

### How the Accident Happens

1. `Candle.to_hash()` calls `self.model_dump_json()` and hashes the result
2. `model_dump_json()` serializes ALL fields — it is "serialize everything," not "serialize these specific fields"
3. The developer may INTEND for only certain fields to be in the identity, but `model_dump_json()` includes ALL fields
4. Fields like `provider_timestamp` (which is a wall-clock audit field) enter the identity hash because they are model fields
5. The developer has no way to exclude fields from `model_dump_json()` without modifying the model or using `exclude` parameter

### Why This Is Wrong

- An identity allowlist is a POSITIVE declaration: "these fields define identity"
- `model_dump_json()` is a NEGATIVE approach: "everything except what we explicitly exclude"
- The negative approach is fragile: adding a new field to the model automatically adds it to the identity hash
- Wall-clock fields (provider_timestamp, retrieval_timestamp) are model fields with default_factory — they automatically enter identity

### Example: Candle.to_hash() Contamination

```python
class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float]
    timeframe: Timeframe
    bid: Optional[float]
    ask: Optional[float]
    spread: Optional[float]
    currency: str = "USD"
    provider_timestamp: Optional[datetime] = Field(default_factory=_now_utc)  # ← WAL-CLOCK FIELD

    def to_hash(self) -> str:
        data = self.model_dump_json()  # ← SERIALIZES ALL FIELDS INCLUDING provider_timestamp
        return hashlib.sha256(data.encode()).hexdigest()
```

Every time a Candle is created, `provider_timestamp` gets a new wall-clock value. If you create two Candles with identical OHLCV data but at different times, they will have DIFFERENT hashes because `provider_timestamp` differs. This violates the principle that identity should be based on data content, not on when the object was created.

---

## SUMMARY TABLE

| Method | Allowlist? | Canonical? | Wall-Clock Safe? | Status |
|--------|------------|------------|------------------|--------|
| Candle.to_hash() | NO (model_dump_json) | NO | NO (provider_timestamp) | FAIL |
| ProvenanceRecord.to_hash() | NO (model_dump_json) | NO | NO (retrieval_timestamp) | FAIL |
| BacktestProvenance.compute_result_hash() | YES (explicit) | PARTIAL (pipe-separated) | YES (run_timestamp excluded) | PASS |
| BacktestProvenance.to_hash() | PARTIAL (exclude unset + pops) | PARTIAL (model_dump) | YES (audit fields popped) | PARTIAL |
| StrategySpec.to_hash() | YES (explicit field-by-field) | YES (canonical_serialize) | YES (no wall-clock fields) | PASS |
| BacktestConfig._compute_config_hash() | YES (explicit) | YES (pipe-separated) | YES | PASS |
| BacktestEngine._compute_dataset_hash() | YES (explicit) | YES (pipe-separated) | YES | PASS (but not content-based) |
| TemporalSemantics.temporal_hash_input() | YES (explicit) | YES (pipe-separated) | YES (ingestion_time excluded) | PASS |
| deterministic_hash() | YES (via canonical_serialize) | YES (canonical_serialize) | YES | PASS |
| canonical_serialize() | N/A (serialization primitive) | YES | YES | PASS |

---

## PHASE 3 HASH COMPATIBILITY

Phase 3 hashes (Candle.to_hash, ProvenanceRecord.to_hash, BacktestProvenance.compute_result_hash, BacktestProvenance.to_hash) remain frozen. No Phase 4A.1 code modifies them. The `pit/` module does not import any Phase 3 modules.

**Phase 3 hashes are frozen but CONTAMINATED.** The contamination (wall-clock fields in identity) exists in the original Phase 3 implementation and is not introduced by Phase 4A.1.

---

## BLOCKER DECLARATION

**IDENTITY_HASH_CONTAMINATION: YES**
- Candle.to_hash() includes provider_timestamp (wall-clock) in identity
- ProvenanceRecord.to_hash() includes retrieval_timestamp (wall-clock) in identity
- No explicit allowlist exists for any Phase 3 entity
- Pydantic model_dump_json() is treated as an implicit allowlist

**ARCHITECTURE_STATUS: REQUIRES_REVISION**
**IMPLEMENTATION_READINESS: NOT_READY**
**IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED**

IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
