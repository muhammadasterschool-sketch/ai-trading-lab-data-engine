"""Phase 4A.1 — Canonical Serialization Utilities.

Deterministic serialization for canonical types. Produces bytes
suitable for SHA-256 hashing.

Rules:
- lists preserve order
- dictionary keys are sorted
- UTC datetime serialization is canonical
- float normalization follows project rules (-0.0 → 0.0)
- NaN is rejected
- positive/negative Infinity are rejected
- unsupported types are rejected
- tuple is rejected
- set is rejected
- custom objects are rejected
- no implicit semantic conversion
- no implicit sorting of list values

Every serialization produces deterministic bytes.
"""

import json
import math
from decimal import Decimal
from datetime import datetime, UTC
from typing import Any


class SerializationError(ValueError):
    """Raised when a value cannot be canonical-serialized."""
    pass


def canonical_serialize(value: Any) -> bytes:
    """Serialize a value to deterministic bytes for SHA-256 hashing.

    Args:
        value: Must be one of: str, int, float, bool, None, list, dict,
               datetime, Decimal.

    Returns:
        Deterministic bytes representation.

    Raises:
        SerializationError: If value is unsupported or invalid.
    """
    serialized = _canonical_value(value)
    return json.dumps(serialized, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _canonical_value(value: Any) -> Any:
    """Convert a value to its canonical JSON-serializable form.

    This function does the actual conversion. It does not serialize
    directly — it returns a structure that json.dumps can handle.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerializationError(
                f"Naive datetime cannot be serialized. "
                f"All PIT timestamps must be timezone-aware."
            )
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key in sorted(value.keys()):
            result[key] = _canonical_value(value[key])
        return result
    if isinstance(value, tuple):
        raise SerializationError("tuple is not a supported canonical type")
    if isinstance(value, set):
        raise SerializationError("set is not a supported canonical type")
    raise SerializationError(
        f"Unsupported canonical type: {type(value).__name__}. "
        f"Supported: str, int, float, bool, None, list, dict, datetime, Decimal"
    )


def _canonical_float(value: float) -> float:
    """Normalize a float to canonical form.

    Rules:
    - -0.0 → 0.0
    - NaN → SerializationError
    - +Infinity → SerializationError
    - -Infinity → SerializationError
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
