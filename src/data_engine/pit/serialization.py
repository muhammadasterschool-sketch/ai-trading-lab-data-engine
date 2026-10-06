"""Phase 4A.1 — Canonical Serialization Utilities (type-tagged).

Deterministic serialization for canonical types. Produces bytes
suitable for SHA-256 hashing.

Implements the authoritative remediation spec SECTION 3 (type-tagged
encoding, F-07 resolution) including the post-re-audit conformance
layer of SECTION 3.1a (RA-NF-01 .. RA-NF-04, SER-KEY-01 .. SER-KEY-05).

Encoding table (every scalar carries an explicit type tag so that no
two semantically distinct values can produce identical canonical bytes):

    None      -> null                              (ID-COL-05)
    bool      -> {"b":true} | {"b":false}          (never {"i":"1"}; True != 1)
    int       -> {"i":"<base-10>"}                 (never a bare JSON number)
    float     -> {"f":"<.10f>"}                    (-0.0 -> 0.0; NaN/Inf rejected)
    Decimal   -> {"d":"<exact str()>"}             (never float-converted)
    str       -> {"s":"<escaped>"}                 (non-ASCII literal UTF-8)
    datetime  -> {"t":"<ISO-8601 UTC>"}            (naive rejected)
    date      -> {"c":"<ISO-8601 YYYY-MM-DD>"}     (tag 'c'; RA-NF-04)
    list      -> {"L":[ ... ]}                     (order preserved, significant)
    tuple     -> {"L":[ ... ]}                     (tuple == list, documented)
    dict      -> {"D":[[{"s":key},value], ...]}    (string keys only, sorted)

Tag-letter registry (mutually distinct; RA-NF-04 resolution):
    b bool, i int, f float, d Decimal, s str, t datetime,
    c date ('c' = calendar date), L list/tuple, D dict (mapping).

The historical spec table reused 'D' for both `date` and `dict`; that
ambiguity is resolved here by assigning `date` the distinct letter 'c'
and by encoding mappings as tagged pair lists (SER-KEY-03).

Mapping-key rules (SER-KEY-01 .. SER-KEY-05, RA-NF-01):
    - Every mapping key MUST be a str. A non-string key raises
      SerializationError BEFORE any coercion (SER-KEY-01).
    - Implicit conversion of 1 -> "1", True -> "True", Decimal -> str,
      date -> ISO string (or any other key coercion) is PROHIBITED
      (SER-KEY-02).
    - Keys are encoded as {"s": <key>} inside the mapping wrapper so a
      key can never be confused with a bare scalar (SER-KEY-03).
    - Unrepresentable keys fail closed, never fall back (SER-KEY-04).
    - These rules apply recursively at every nesting depth (SER-KEY-05).

Other rules:
- list order is preserved and significant ([1,2] != [2,1])
- mapping entries are sorted by key Unicode code point (deterministic
  across platforms and locales); values are never sorted
- float normalization follows the project .10f policy (F-08)
- NaN and +/-Infinity are rejected (float AND Decimal)
- naive datetime is rejected
- a date is never implicitly widened to a datetime (RA-NF-02)
- set, frozenset, bytes, arbitrary objects and non-whitelisted models
  are rejected — fail closed (F-17, ID-COL-06)
- encoding is UTF-8, no BOM; separators ',' and ':' with no whitespace;
  control characters escaped; non-ASCII emitted literally

Every serialization produces deterministic bytes.
"""

import json
import math
from decimal import Decimal
from datetime import datetime, date, UTC
from typing import Any


class SerializationError(ValueError):
    """Raised when a value cannot be canonical-serialized."""
    pass


# Tag letters. Mutually distinct by construction (RA-NF-04 resolution).
_TAG_BOOL = "b"
_TAG_INT = "i"
_TAG_FLOAT = "f"
_TAG_DECIMAL = "d"
_TAG_STR = "s"
_TAG_DATETIME = "t"
_TAG_DATE = "c"          # 'c' = calendar date; distinct from the dict tag 'D'
_TAG_LIST = "L"
_TAG_DICT = "D"


def canonical_serialize(value: Any) -> bytes:
    """Serialize a value to deterministic type-tagged canonical bytes.

    Args:
        value: Must be one of: str, int, float, bool, None, list, tuple,
               dict (string keys only), datetime, date, Decimal.

    Returns:
        Deterministic bytes representation (UTF-8, single-line JSON).

    Raises:
        SerializationError: If value is unsupported or invalid —
            including any non-string mapping key (SER-KEY-01).
    """
    serialized = _canonical_value(value)
    return json.dumps(
        serialized,
        ensure_ascii=False,       # non-ASCII emitted literally as UTF-8
        separators=(",", ":"),    # no whitespace
    ).encode("utf-8")


def _canonical_value(value: Any) -> Any:
    """Convert a value to its type-tagged canonical JSON form.

    This function does the actual conversion. It does not serialize
    directly — it returns a structure that json.dumps can handle.
    """
    # NOTE: bool MUST be tested before int (bool is a subclass of int),
    # and datetime MUST be tested before date (datetime is a subclass
    # of date). Order is load-bearing.
    if value is None:
        return None
    if isinstance(value, bool):
        return {_TAG_BOOL: value}
    if isinstance(value, int):
        return {_TAG_INT: str(value)}
    if isinstance(value, float):
        return {_TAG_FLOAT: _canonical_float_str(value)}
    if isinstance(value, str):
        return {_TAG_STR: value}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerializationError(
                f"Naive datetime cannot be serialized. "
                f"All PIT timestamps must be timezone-aware."
            )
        return {_TAG_DATETIME: value.astimezone(UTC).isoformat()}
    if isinstance(value, date):
        # Bare date (never a datetime here). Never widened to a
        # datetime (RA-NF-02); tagged 'c' (RA-NF-04 resolution).
        return {_TAG_DATE: value.isoformat()}
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SerializationError(
                f"Non-finite Decimal ({value}) is not a supported "
                f"canonical value"
            )
        return {_TAG_DECIMAL: str(value)}
    if isinstance(value, (list, tuple)):
        # tuple is accepted and encoded identically to list (spec 3.1).
        return {_TAG_LIST: [_canonical_value(item) for item in value]}
    if isinstance(value, dict):
        return {_TAG_DICT: _canonical_mapping(value)}
    if isinstance(value, (set, frozenset)):
        raise SerializationError("set is not a supported canonical type")
    if isinstance(value, (bytes, bytearray)):
        raise SerializationError("bytes is not a supported canonical type")
    raise SerializationError(
        f"Unsupported canonical type: {type(value).__name__}. "
        f"Supported: str, int, float, bool, None, list, tuple, dict "
        f"(string keys), datetime, date, Decimal"
    )


def _canonical_mapping(value: dict) -> list:
    """Encode a mapping as a sorted list of tagged [key, value] pairs.

    SER-KEY-01: a non-string key raises BEFORE any coercion.
    SER-KEY-02: no implicit key conversion of any kind.
    SER-KEY-03: keys are encoded as {"s": <key>} so a key can never be
                confused with a bare scalar value.
    SER-KEY-05: recursion applies these rules at every depth.
    """
    pairs = []
    for key in value:
        if not isinstance(key, str):
            raise SerializationError(
                f"Mapping keys MUST be strings (SER-KEY-01). "
                f"Got key {key!r} of type {type(key).__name__}; "
                f"implicit coercion to a string is PROHIBITED (SER-KEY-02)."
            )
    for key in sorted(value.keys()):  # Unicode code-point order
        pairs.append([{_TAG_STR: key}, _canonical_value(value[key])])
    return pairs


def _canonical_float(value: float) -> float:
    """Normalize a float to canonical numeric form (identity-level).

    Rules:
    - -0.0 -> 0.0
    - NaN -> SerializationError
    - +Infinity -> SerializationError
    - -Infinity -> SerializationError

    Retained as a float-returning helper for backward compatibility;
    the tagged encoder uses _canonical_float_str.
    """
    if math.isnan(value):
        raise SerializationError("NaN is not a supported canonical float value")
    if math.isinf(value):
        raise SerializationError(
            f"Infinity ({value}) is not a supported canonical float value"
        )
    if value == 0.0:
        return 0.0  # Normalize -0.0 to 0.0
    return value


def _canonical_float_str(value: float) -> str:
    """Return the .10f canonical string form of a float (F-08 policy).

    Phase 4 adopts the Phase 3 '.10f' float policy: always 10 decimal
    places, -0.0 normalized to 0.0 first, NaN and +/-Inf rejected.
    """
    return f"{_canonical_float(value):.10f}"


def canonical_serialize_deterministic(value: Any) -> str:
    """Serialize a value to a deterministic string.

    Convenience wrapper that returns a string instead of bytes.
    """
    return canonical_serialize(value).decode('utf-8')


def validate_canonical_value(value: Any) -> bool:
    """Validate that a value can be canonical-serialized without raising.

    Returns True if serializable, raises SerializationError if not.
    """
    _canonical_value(value)
    return True
