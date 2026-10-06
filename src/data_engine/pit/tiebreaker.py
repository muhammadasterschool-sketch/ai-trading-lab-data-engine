"""Phase 4A.1 — TieBreakerPolicy: deterministic total order for ties.

Implements spec SECTION 7.3.

Purpose: a total, deterministic ordering for observations sharing an
identical temporal key.

Invariants:
- Total order — any two distinct observations compare deterministically
- The key tuple MUST be sufficient to break every tie
- Ordering MUST NOT depend on input order, dict iteration order, wall
  clock, RNG, or memory address
- A tie that the key tuple cannot break RAISES — never an arbitrary
  fallback (TIE-05)

Identity fields: name, version, ordered key tuple. Participates in
experiment_id so that changing the tie-breaker changes identity
(TIE-06, EXP-02).
"""

from typing import Any, Sequence
from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.pit.hashing import identity_hash, PHASE4_IDENTITY_CONTRACT_VERSION


#: Sort keys that smuggle in wall-clock or audit semantics (TIE-04,
#: PROH-LEG-01 class). A policy naming one of these raises at construction.
WALL_CLOCK_SORT_KEYS: frozenset[str] = frozenset({
    "now", "wall_clock", "wallclock", "current_time", "datetime_now",
    "ingestion_time", "retrieval_timestamp", "provider_timestamp",
    "created_at", "run_timestamp", "approval_timestamp", "process_time",
})


class AmbiguousTieError(ValueError):
    """Raised when two distinct observations share identical sort keys.

    The key tuple MUST be sufficient to break every tie (spec 7.3);
    an unbreakable tie is an error, never an arbitrary fallback.
    """
    pass


class TieBreakerPolicy(BaseModel):
    """Deterministic total-order policy for equal temporal keys."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    name: str
    version: str
    keys: tuple[str, ...]
    schema_version: str = Field(default="1.0.0")

    #: Ordered identity-field allowlist (spec 2.3, 7.3).
    IDENTITY_FIELDS: tuple[str, ...] = ("name", "version", "keys")

    @field_validator("name", "version", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("name/version/schema_version must be non-empty strings")
        return v

    @field_validator("keys")
    @classmethod
    def _validate_keys(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError(
                "TieBreakerPolicy.keys must be a non-empty ordered tuple "
                "(spec 7.3: an empty key tuple cannot define a total order)."
            )
        seen: set = set()
        for key in v:
            if not isinstance(key, str) or not key:
                raise ValueError("sort keys must be non-empty strings")
            if key in seen:
                raise ValueError(
                    f"duplicate sort key '{key}' — no duplicate keys (spec 7.3)."
                )
            seen.add(key)
            if key in WALL_CLOCK_SORT_KEYS:
                raise ValueError(
                    f"Wall-clock sort key '{key}' is PROHIBITED (TIE-04, "
                    f"spec 7.3): ordering must never depend on ambient time."
                )
        return tuple(v)

    # ── ordering surface ─────────────────────────────────────────────

    def key_of(self, observation: Any) -> tuple:
        """Extract the ordered sort-key tuple from an observation.

        Attribute access only (duck-typed); no clock, RNG, or address.
        A missing attribute raises AttributeError — fail closed.
        """
        return tuple(getattr(observation, key) for key in self.keys)

    def compare(self, a: Any, b: Any) -> int:
        """Total-order comparator (spec 7.3).

        Returns -1/0/+1. Two distinct observations with identical key
        tuples raise AmbiguousTieError — the tie is unbreakable and an
        arbitrary fallback is prohibited.
        """
        ka, kb = self.key_of(a), self.key_of(b)
        if ka < kb:
            return -1
        if ka > kb:
            return 1
        # Keys equal: identical observations are interchangeable (0);
        # distinct observations are an unbreakable tie (raise).
        if a == b:
            return 0
        raise AmbiguousTieError(
            f"Unbreakable tie (spec 7.3, TIE-05): observations {a!r} and "
            f"{b!r} share identical sort keys {ka!r} but are distinct. The "
            f"key tuple MUST be sufficient to break every tie; refusing to "
            f"apply an arbitrary order."
        )

    def sort(self, observations: Sequence[Any]) -> list:
        """Return a new list in the policy's total order.

        Input-order independent: the comparator defines a total order,
        so the result is a function of the SET (with duplicates) of
        observations, not of the input sequence order (TIE-02).
        """
        import functools
        return sorted(observations, key=functools.cmp_to_key(self.compare))

    # ── identity ─────────────────────────────────────────────────────

    @property
    def tie_breaker_hash(self) -> str:
        """Phase 4 identity hash over (name, version, ordered keys)."""
        return identity_hash(
            entity_type="TieBreakerPolicy",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "name": self.name,
                "version": self.version,
                "keys": list(self.keys),
            },
        )

    def identity_payload(self) -> dict:
        """Canonical payload fragment used by experiment identity (7.12)."""
        return {
            "name": self.name,
            "version": self.version,
            "keys": list(self.keys),
        }
