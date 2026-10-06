"""Phase 4A.1 — Deterministic Hashing and the Phase 4 Identity Contract.

Provides the deterministic hashing abstraction and the mandated
identity free function for the Phase 4 identity contract
(PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md SECTION 2).

Contract highlights:
- IDENTITY_HASH = "pit4." + SHA256_HEX(canonical_bytes(identity_payload))
  (spec 2.5). Output is 70 characters: 6-char prefix + 64 lowercase hex.
- PHASE4_IDENTITY_CONTRACT_VERSION = "1.0.0" is included in every
  identity payload (spec 2.6).
- The allowlist is positively declared, ordered, frozen; order is part
  of the contract — reordering produces a different hash (spec 2.3, 2.6).
- Prohibited wall-clock/audit fields (spec 2.4) NEVER participate:
    ID-WC-01  no prohibited field may appear in any allowlist,
              directly or transitively
    ID-WC-02  an allowlist containing a prohibited field MUST raise
    ID-WC-03  identity is a pure function of the allowlisted values —
              no ambient clock, RNG, PID, path, locale, or environment
- The identity function is a FREE function (spec 2.8, F-09): it MUST
  NOT be added to Candle, ProvenanceRecord, or any frozen Phase 3
  class, and it never imports, calls, or reflects on any Phase 3 hash
  method (FRZ-01..03, SUB-25).
- Eligibility hash (spec 2.7):
    ELIGIBILITY_HASH = "pit4e." + SHA256_HEX(canonical_bytes({
        event_time, observation_time, publication_time,
        effective_time, revision_time}))          # ingestion_time EXCLUDED

Requirements:
- SHA-256, deterministic, no runtime timestamps, no random UUIDs,
  stable across processes.
"""

import hashlib
from typing import Any, Mapping, Sequence
from data_engine.pit.serialization import canonical_serialize, SerializationError


# ---------------------------------------------------------------------------
# Phase 4 identity contract constants (spec 2.4, 2.6)
# ---------------------------------------------------------------------------

PHASE4_IDENTITY_CONTRACT_VERSION = "1.0.0"

IDENTITY_HASH_PREFIX = "pit4."
ELIGIBILITY_HASH_PREFIX = "pit4e."

# Audit-class fields that are PROHIBITED in any Phase 4 identity
# allowlist, directly or transitively (spec 2.4, ID-WC-01/02).
PROHIBITED_IDENTITY_FIELDS: frozenset[str] = frozenset({
    "provider_timestamp",    # Candle — CONTAMINATED (F-04)
    "retrieval_timestamp",   # ProvenanceRecord — CONTAMINATED (F-05)
    "ingestion_time",        # TemporalSemantics — AUDIT class
    "created_at",            # DatasetVersion — POTENTIAL (default_factory now)
    "run_timestamp",         # BacktestProvenance — audit
    "approval_timestamp",    # ApprovalMetadata (4A.4) — audit
})


class IdentityContractError(ValueError):
    """Raised when an identity-contract rule is violated (ID-WC-01..03)."""
    pass


# ---------------------------------------------------------------------------
# Deterministic hash primitives (unchanged public API)
# ---------------------------------------------------------------------------

def deterministic_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hex digest for a canonical value.

    Args:
        value: Any value supported by canonical_serialize.

    Returns:
        SHA-256 hex digest string (64 lowercase hex characters).

    Raises:
        SerializationError: If value cannot be canonicalized.
    """
    canonical_bytes = canonical_serialize(value)
    return hashlib.sha256(canonical_bytes).hexdigest()


def deterministic_hash_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest for raw bytes.

    Args:
        data: Raw bytes to hash.

    Returns:
        SHA-256 hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


def verify_hash_determinism(value: Any, iterations: int = 3) -> bool:
    """Verify that the same value always produces the same hash.

    Args:
        value: Value to hash repeatedly.
        iterations: Number of times to hash and compare.

    Returns:
        True if all iterations produce identical hashes.
    """
    hashes = set()
    for _ in range(iterations):
        h = deterministic_hash(value)
        hashes.add(h)
        if len(hashes) > 1:
            return False
    return len(hashes) == 1


def verify_cross_process_hash(value: Any) -> bool:
    """Verify hash stability across process boundaries.

    This is effectively tested by calling deterministic_hash twice
    in the same process, since SHA-256 is deterministic by definition.
    For true cross-process verification, the same value hashed
    in a separate process should produce identical output.

    Returns:
        True if the hash is well-formed (64 hex chars).
    """
    h = deterministic_hash(value)
    assert len(h) == 64, f"Hash length is {len(h)}, expected 64"
    assert all(c in '0123456789abcdef' for c in h), "Hash contains non-hex characters"
    return True


# ---------------------------------------------------------------------------
# Phase 4 identity contract (spec SECTION 2)
# ---------------------------------------------------------------------------

def _assert_no_prohibited_fields(identity_fields: Sequence[str],
                                 values: Mapping[str, Any]) -> None:
    """Enforce ID-WC-01/02: no wall-clock/audit field, directly or transitively.

    Direct: a prohibited field name appears in the allowlist.
    Transitive: a prohibited field name appears as a key anywhere inside
    a provided dict value (recursively) — such a value would smuggle an
    audit timestamp into the identity payload.
    """
    for field in identity_fields:
        if field in PROHIBITED_IDENTITY_FIELDS:
            raise IdentityContractError(
                f"ID-WC-02 violation: prohibited audit/wall-clock field "
                f"'{field}' MUST NOT appear in a Phase 4 identity allowlist "
                f"(spec 2.4, ID-WC-01)."
            )

    def _scan(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key in value:
                if key in PROHIBITED_IDENTITY_FIELDS:
                    raise IdentityContractError(
                        f"ID-WC-01 violation (transitive): prohibited field "
                        f"'{key}' found at {path} inside an identity value; "
                        f"audit fields must never enter identity payloads."
                    )
                _scan(value[key], f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                _scan(item, f"{path}[{i}]")

    for field in identity_fields:
        _scan(values[field], field)


def identity_hash(entity_type: str,
                  schema_version: str,
                  identity_fields: Sequence[str],
                  values: Mapping[str, Any]) -> str:
    """Compute a Phase 4 identity hash (spec 2.5, 2.8 — F-09 resolution).

    This is the mandated FREE function. It MUST NOT be added to any
    frozen Phase 3 class, and it never imports, calls, or reflects on
    any Phase 3 hash method (FRZ-01..03). It reads only the named
    fields (ID-WC-03): no ambient clock, RNG, PID, path, locale, or
    environment variable is read.

    Args:
        entity_type: Non-empty stable entity type identifier.
        schema_version: Non-empty entity schema version (spec 2.6).
        identity_fields: Ordered, duplicate-free allowlist of field
            names. Order is part of the contract: reordering the tuple
            produces a different hash (spec 2.3, 2.6).
        values: Mapping of field name -> value. MUST contain exactly
            the allowlisted fields — a missing key or an extra key
            raises (fail closed, ID-COL-07).

    Returns:
        "pit4." + 64 lowercase hex characters (70 characters total).

    Raises:
        IdentityContractError: On any ID-WC-01/02/03 violation, an
            invalid allowlist, or a values/allowlist mismatch.
        SerializationError: If any allowlisted value cannot be
            canonical-serialized (fail closed, ID-COL-06).
    """
    if not isinstance(entity_type, str) or not entity_type:
        raise IdentityContractError(
            "entity_type must be a non-empty string"
        )
    if not isinstance(schema_version, str) or not schema_version:
        raise IdentityContractError(
            "schema_version must be a non-empty string"
        )
    if isinstance(identity_fields, (str, bytes)):
        raise IdentityContractError(
            "identity_fields must be a sequence of field names, not a string"
        )
    fields = tuple(identity_fields)
    if not fields:
        raise IdentityContractError(
            "identity_fields allowlist must not be empty (spec 2.3: "
            "positively declared, exhaustive)"
        )
    seen: set = set()
    for field in fields:
        if not isinstance(field, str) or not field:
            raise IdentityContractError(
                f"identity field names must be non-empty strings, got {field!r}"
            )
        if field in seen:
            raise IdentityContractError(
                f"duplicate identity field '{field}' — allowlist order is a "
                f"contract and duplicates are ambiguous (ID-COL-07)"
            )
        seen.add(field)

    value_keys = set(values.keys())
    missing = seen - value_keys
    extra = value_keys - seen
    if missing:
        raise IdentityContractError(
            f"values is missing allowlisted field(s): {sorted(missing)} — "
            f"identity reads exactly the declared allowlist"
        )
    if extra:
        raise IdentityContractError(
            f"values contains non-allowlisted field(s): {sorted(extra)} — "
            f"an identity payload must be built ONLY from identity_fields "
            f"(spec 2.5); fail closed (ID-COL-07)"
        )

    # ID-WC-01/02: wall-clock and audit fields are prohibited, directly
    # or transitively.
    _assert_no_prohibited_fields(fields, values)

    # The payload carries the contract version, the entity type, the
    # entity schema version, and the allowlisted values as an ORDERED
    # list of [name, value] pairs so that allowlist order is part of
    # the hash (spec 2.3/2.6: reordering is a breaking change).
    payload = {
        "contract_version": PHASE4_IDENTITY_CONTRACT_VERSION,
        "entity_type": entity_type,
        "schema_version": schema_version,
        "fields": [[name, values[name]] for name in fields],
    }
    digest = hashlib.sha256(canonical_serialize(payload)).hexdigest()
    return IDENTITY_HASH_PREFIX + digest


# ---------------------------------------------------------------------------
# Eligibility hash (spec 2.7)
# ---------------------------------------------------------------------------

#: Fields hashed into an eligibility hash. ingestion_time is EXCLUDED
#: by mandate (it is AUDIT class and never affects PIT availability).
ELIGIBILITY_FIELDS: tuple[str, ...] = (
    "event_time",
    "observation_time",
    "publication_time",
    "effective_time",
    "revision_time",
)


def eligibility_hash(values: Mapping[str, Any]) -> str:
    """Compute the Phase 4 eligibility hash (spec 2.7).

    Hashes exactly: event_time, observation_time, publication_time,
    effective_time, revision_time. ingestion_time is EXCLUDED — it is
    AUDIT class and never participates in PIT availability.

    This is the TemporalSemantics.temporal_hash_input() principle,
    retained and formally specified.

    Args:
        values: Mapping containing all five eligibility fields. Values
            may be None (optional fields); the five keys themselves
            MUST be present (fail closed).

    Returns:
        "pit4e." + 64 lowercase hex characters.

    Raises:
        IdentityContractError: If any of the five fields is absent.
        SerializationError: If a value cannot be canonical-serialized.
    """
    missing = [f for f in ELIGIBILITY_FIELDS if f not in values]
    if missing:
        raise IdentityContractError(
            f"eligibility values is missing field(s): {missing} "
            f"(ingestion_time is excluded by mandate and is NOT required)"
        )
    if "ingestion_time" in values and values["ingestion_time"] is not None:
        # Not an error (audit metadata may ride along on the object),
        # but it MUST NOT be hashed — and it is not, below.
        pass
    payload = {f: values[f] for f in ELIGIBILITY_FIELDS}
    digest = hashlib.sha256(canonical_serialize(payload)).hexdigest()
    return ELIGIBILITY_HASH_PREFIX + digest
