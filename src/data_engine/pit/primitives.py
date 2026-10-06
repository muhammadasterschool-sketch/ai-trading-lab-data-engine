"""Phase 4A.1 — Identity primitives: instrument, specification, venue,
data source, calendar reference.

Implements spec SECTIONS 7.7 — 7.11.

Components:
- InstrumentIdentity      (7.7)  stable instrument identity, independent
                                  of provider naming; no free-form symbol
                                  is an identity field (INST-03)
- InstrumentSpecification (7.8)  effective-dated trading specification;
                                  effective_to EXCLUDED from identity
                                  (SPEC-03); intervals never overlap
- Venue                   (7.9)  immutable exchange identity with an
                                  IANA timezone
- DataSource              (7.10) immutable provider identity with
                                  versioned symbol mappings — a rename
                                  creates a new mapping version, never a
                                  silent overwrite (SRC-01)
- CalendarRef             (7.11) identity REFERENCE to a calendar
                                  version. No calendar computation in
                                  4A.1 — no holiday logic, no session
                                  determination, no trading-day
                                  arithmetic (INV-06, CAL-02)

NOTE on enum handling: asset_class and contract_type use string
Literal types whose values mirror the Phase 3 enums. No Phase 3 class
is imported, wrapped, or duplicated here (spec 2.1: Phase 4 identity
is a separate contract; single-definition principle of F-02/R-03).
"""

from datetime import date
from typing import Literal, Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import identity_hash, PHASE4_IDENTITY_CONTRACT_VERSION


AssetClassLiteral = Literal[
    "cryptocurrency", "forex", "equity", "index", "commodity", "metal",
]
ContractTypeLiteral = Literal["spot", "futures", "cfd", "option", "unknown"]


# ---------------------------------------------------------------------------
# InstrumentIdentity (spec 7.7)
# ---------------------------------------------------------------------------

class InstrumentIdentity(BaseModel):
    """Stable instrument identity across its whole lifecycle.

    Stable across provider symbol renames and venue re-listings where
    the economic instrument is unchanged. A free-form symbol is NOT an
    identity field (INST-03): provider_symbol is carried as
    non-identity metadata so renames never change the hash.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stable_identifier: str
    asset_class: AssetClassLiteral
    contract_type: ContractTypeLiteral
    schema_version: str = Field(default="1.0.0")

    # Non-identity metadata (INST-03): never hashed.
    provider_symbol: Optional[str] = None

    IDENTITY_FIELDS: tuple[str, ...] = (
        "stable_identifier", "asset_class", "contract_type", "schema_version",
    )

    @field_validator("stable_identifier", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError(
                "stable_identifier/schema_version must be non-empty strings "
                "(spec 7.7: empty identifier raises)"
            )
        return v

    @property
    def instrument_identity_hash(self) -> str:
        """Phase 4 identity hash ('pit4.'-prefixed)."""
        return identity_hash(
            entity_type="InstrumentIdentity",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "stable_identifier": self.stable_identifier,
                "asset_class": self.asset_class,
                "contract_type": self.contract_type,
                "schema_version": self.schema_version,
            },
        )

    def with_provider_symbol(self, provider_symbol: Optional[str]) -> "InstrumentIdentity":
        """Return a copy carrying a different provider symbol.

        The identity hash is UNCHANGED — provider naming is not
        identity (INST-02 / SUB-23).
        """
        return self.model_copy(update={"provider_symbol": provider_symbol})


# ---------------------------------------------------------------------------
# Venue (spec 7.9)
# ---------------------------------------------------------------------------

class Venue(BaseModel):
    """Immutable exchange/market identifier with its timezone."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    venue_name: str
    timezone: str
    mic: Optional[str] = None
    schema_version: str = Field(default="1.0.0")

    IDENTITY_FIELDS: tuple[str, ...] = ("venue_id", "timezone", "schema_version")

    @field_validator("venue_id", "venue_name", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("venue_id/venue_name/schema_version must be non-empty")
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_iana_timezone(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("timezone must be a non-empty IANA identifier")
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            raise ValueError(
                f"Invalid IANA timezone identifier: {v!r} (spec 7.9, VEN-01: "
                f"invalid timezone raises)."
            )
        return v

    @property
    def venue_hash(self) -> str:
        """Phase 4 identity hash ('pit4.'-prefixed)."""
        return identity_hash(
            entity_type="Venue",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "venue_id": self.venue_id,
                "timezone": self.timezone,
                "schema_version": self.schema_version,
            },
        )


# ---------------------------------------------------------------------------
# DataSource (spec 7.10)
# ---------------------------------------------------------------------------

class SymbolMapping(BaseModel):
    """One versioned mapping of a stable instrument to a provider symbol.

    A provider renaming an instrument produces a NEW mapping version —
    never a silent overwrite (spec 7.10).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mapping_version: int = Field(..., ge=1)
    stable_identifier: str
    provider_symbol: str

    @field_validator("stable_identifier", "provider_symbol")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("stable_identifier/provider_symbol must be non-empty")
        return v


class DataSource(BaseModel):
    """Immutable provider identity with versioned symbol mappings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    provider_name: str
    source_version: str
    symbol_mappings: tuple[SymbolMapping, ...] = Field(default_factory=tuple)
    schema_version: str = Field(default="1.0.0")

    # Identity fields (spec 7.10): symbol mappings are NOT identity —
    # the mapping table is versioned data, not provider identity.
    IDENTITY_FIELDS: tuple[str, ...] = (
        "source_id", "source_version", "provider_name", "schema_version",
    )

    @field_validator("source_id", "provider_name", "source_version", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("source_id/provider_name/source_version must be non-empty")
        return v

    @field_validator("symbol_mappings")
    @classmethod
    def _validate_mappings(cls, v: tuple[SymbolMapping, ...]) -> tuple[SymbolMapping, ...]:
        versions = [m.mapping_version for m in v]
        if len(set(versions)) != len(versions):
            raise ValueError(
                f"Duplicate mapping version(s) detected (SRC-02, spec 7.10): "
                f"{versions}. Mapping versions are unique and monotonic; a "
                f"duplicate version is a silent-overwrite attempt."
            )
        if versions != sorted(versions):
            raise ValueError(
                f"Mapping versions must be strictly increasing (SRC-03, "
                f"spec 7.10): got {versions}."
            )
        return tuple(v)

    @classmethod
    def with_renamed_symbol(cls, source: "DataSource", stable_identifier: str,
                            new_provider_symbol: str) -> "DataSource":
        """Append a NEW mapping version for a renamed symbol (SRC-01).

        The existing mappings are preserved verbatim — a rename never
        silently overwrites; it appends the next mapping version.
        """
        next_version = (max((m.mapping_version for m in source.symbol_mappings),
                            default=0) + 1)
        new_mapping = SymbolMapping(
            mapping_version=next_version,
            stable_identifier=stable_identifier,
            provider_symbol=new_provider_symbol,
        )
        return source.model_copy(
            update={"symbol_mappings": source.symbol_mappings + (new_mapping,)}
        )

    @property
    def source_hash(self) -> str:
        """Phase 4 identity hash ('pit4.'-prefixed)."""
        return identity_hash(
            entity_type="DataSource",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "source_id": self.source_id,
                "source_version": self.source_version,
                "provider_name": self.provider_name,
                "schema_version": self.schema_version,
            },
        )


# ---------------------------------------------------------------------------
# InstrumentSpecification (spec 7.8)
# ---------------------------------------------------------------------------

class InstrumentSpecification(BaseModel):
    """Effective-dated trading specification for one instrument.

    Invariants (spec 7.8):
    - effective-dated: effective_from < effective_to; the interval is
      bounded (an unbounded interval raises)
    - intervals for one instrument MUST NOT overlap (enforced by
      validate_specification_intervals)
    - effective_to is EXCLUDED from identity (SPEC-03): it is a
      consequence of the successor's start, not an independent fact
    - tick_size and contract_size are positive
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument_identity: InstrumentIdentity
    effective_from: date
    effective_to: date
    tick_size: float = Field(..., gt=0)
    contract_size: float = Field(..., gt=0)
    currency: str
    venue: Venue
    schema_version: str = Field(default="1.0.0")

    # effective_to deliberately EXCLUDED (SPEC-03).
    IDENTITY_FIELDS: tuple[str, ...] = (
        "instrument_identity", "effective_from", "tick_size",
        "contract_size", "currency", "venue", "schema_version",
    )

    @field_validator("currency", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("currency/schema_version must be non-empty")
        return v

    @model_validator(mode="after")
    def _validate_interval(self) -> "InstrumentSpecification":
        if self.effective_from >= self.effective_to:
            raise ValueError(
                f"Invalid validity interval (spec 7.8, SPEC-02): "
                f"effective_from ({self.effective_from.isoformat()}) >= "
                f"effective_to ({self.effective_to.isoformat()})."
            )
        return self

    @property
    def specification_hash(self) -> str:
        """Phase 4 identity hash ('pit4.'-prefixed); effective_to EXCLUDED."""
        return identity_hash(
            entity_type="InstrumentSpecification",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                # Nested identities are consumed as OPAQUE hash strings
                # (spec 2.8 / FRZ-02 principle: compose, never re-derive).
                "instrument_identity": self.instrument_identity.instrument_identity_hash,
                "effective_from": self.effective_from,
                "tick_size": self.tick_size,
                "contract_size": self.contract_size,
                "currency": self.currency,
                "venue": self.venue.venue_hash,
                "schema_version": self.schema_version,
            },
        )


def validate_specification_intervals(
    specifications: Sequence[InstrumentSpecification],
) -> None:
    """Reject overlapping validity intervals for one instrument (SPEC-01).

    Intervals for the same instrument identity MUST NOT overlap. This
    is a cross-instance constraint, so it is a module-level check over
    a collection of specifications.
    """
    by_instrument: dict[str, list[InstrumentSpecification]] = {}
    for spec in specifications:
        key = spec.instrument_identity.instrument_identity_hash
        by_instrument.setdefault(key, []).append(spec)
    for key, specs in by_instrument.items():
        ordered = sorted(specs, key=lambda s: s.effective_from)
        for i in range(1, len(ordered)):
            if ordered[i].effective_from < ordered[i - 1].effective_to:
                raise ValueError(
                    f"Overlapping validity intervals for instrument "
                    f"{ordered[i].instrument_identity.stable_identifier} "
                    f"(SPEC-01, spec 7.8): "
                    f"[{ordered[i - 1].effective_from.isoformat()}, "
                    f"{ordered[i - 1].effective_to.isoformat()}) overlaps "
                    f"[{ordered[i].effective_from.isoformat()}, "
                    f"{ordered[i].effective_to.isoformat()})."
                )


# ---------------------------------------------------------------------------
# CalendarRef (spec 7.11 — MINIMAL, reference only)
# ---------------------------------------------------------------------------

class CalendarRef(BaseModel):
    """Identity REFERENCE to a calendar version. Reference only.

    SCOPE GUARD (INV-06, CAL-02): NO calendar computation exists in
    4A.1. This class deliberately exposes no holiday logic, no session
    determination, and no trading-day arithmetic. Any 4A.1 component
    requiring those is a scope violation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    calendar_id: str
    calendar_version: str
    schema_version: str = Field(default="1.0.0")

    IDENTITY_FIELDS: tuple[str, ...] = (
        "calendar_id", "calendar_version", "schema_version",
    )

    @field_validator("calendar_id", "calendar_version", "schema_version")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError(
                "calendar_id/calendar_version must be non-empty strings "
                "(spec 7.11, CAL-01)"
            )
        return v

    @property
    def calendar_ref_hash(self) -> str:
        """Phase 4 identity hash ('pit4.'-prefixed)."""
        return identity_hash(
            entity_type="CalendarRef",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values={
                "calendar_id": self.calendar_id,
                "calendar_version": self.calendar_version,
                "schema_version": self.schema_version,
            },
        )
