"""Phase 4A.1 — Experiment identity and PIT experiment configuration.

Implements spec SECTIONS 7.12 and 7.13 with the legacy rules of 6.3.

ExperimentIdentity (7.12):
- Deterministic identity for one complete PIT experiment
- A PURE function of its declared inputs: strategy_hash, dataset_hash,
  view_hash, config_hash, tie-breaker name+version, code/quant/
  backtest engine versions, contract version
- MUST NOT depend on run_timestamp, approval_timestamp, ingestion_time,
  random UUIDs, wall clock, filesystem path, or environment (EXP-03)
- Frozen Phase 3 hashes are consumed AS OPAQUE STRINGS (FRZ-02);
  no Phase 3 hash method is ever invoked (EXP-05, SUB-25)

PitExperimentConfig (7.13):
- Configuration for a PIT-aware experiment; frozen; extra='forbid'
- Every legacy assumption is explicit and declared (CFG-01)
- The config alone determines the view (CFG-04)
"""

import re
from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import identity_hash, PHASE4_IDENTITY_CONTRACT_VERSION
from data_engine.pit.tiebreaker import TieBreakerPolicy

#: A component hash is 64 lowercase hex, optionally prefixed with a
#: Phase 4 style dotted prefix (e.g. 'pit4.', 'pit4v.'). Frozen Phase 3
#: hashes arrive bare (64 hex); Phase 4 composite hashes arrive prefixed.
_COMPONENT_HASH_RE = re.compile(r"^(?:pit4[a-z]*\.)?[0-9a-f]{64}$")

EXPERIMENT_ID_PREFIX = "pit4x."


class ExperimentIdentity(BaseModel):
    """Deterministic identity for one complete PIT experiment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_hash: str
    dataset_hash: str
    view_hash: str
    config_hash: str
    tie_breaker_name: str
    tie_breaker_version: str
    code_version: str
    quant_version: str
    backtest_engine_version: str

    IDENTITY_FIELDS: tuple[str, ...] = (
        "strategy_hash", "dataset_hash", "view_hash", "config_hash",
        "tie_breaker_name", "tie_breaker_version",
        "code_version", "quant_version", "backtest_engine_version",
    )

    @field_validator(
        "strategy_hash", "dataset_hash", "view_hash", "config_hash",
    )
    @classmethod
    def _validate_component_hash(cls, v: str) -> str:
        if not isinstance(v, str) or not _COMPONENT_HASH_RE.match(v):
            raise ValueError(
                f"Component hash malformed (spec 7.12: all component hashes "
                f"well-formed — 64 hex, optional pit4-style prefix): {v!r}"
            )
        return v

    @field_validator(
        "tie_breaker_name", "tie_breaker_version", "code_version",
        "quant_version", "backtest_engine_version",
    )
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(
                "Experiment identity components must be non-empty strings "
                "(spec 7.12, EXP-04: a missing or blank component raises)."
            )
        return v

    @property
    def experiment_id(self) -> str:
        """'pit4x.' + SHA-256 over the ordered identity payload.

        Pure function of the declared inputs — no wall clock, no UUID,
        no PID, no path, no environment (EXP-01/EXP-03).
        """
        return EXPERIMENT_ID_PREFIX + identity_hash(
            entity_type="ExperimentIdentity",
            schema_version=PHASE4_IDENTITY_CONTRACT_VERSION,
            identity_fields=self.IDENTITY_FIELDS,
            values={name: getattr(self, name) for name in self.IDENTITY_FIELDS},
        )[len("pit4."):]


class LegacyPolicy(str, Enum):
    """What to do when publication time is unknown (spec 6.3)."""
    PIT_INELIGIBLE = "pit_ineligible"
    ASSUMED_PUBLICATION = "assumed_publication"


class PitExperimentConfig(BaseModel):
    """Configuration for a PIT-aware experiment (spec 7.13).

    Frozen; extra='forbid' (CFG-02). The cutoff is UTC-aware (CFG-03).
    An ASSUMED_PUBLICATION legacy policy REQUIRES explicit assumption
    text and an explicit publication offset (CFG-01) — never a silent
    default (PROH-LEG-04 prohibits defaulting publication to event
    time; the offset here is a DECLARED assumption with recorded
    basis, applied from observation_time).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cutoff: datetime
    tie_breaker: TieBreakerPolicy
    legacy_policy: LegacyPolicy = LegacyPolicy.PIT_INELIGIBLE
    legacy_assumption_text: Optional[str] = None
    legacy_publication_offset_seconds: Optional[float] = Field(
        None, description=(
            "Declared assumption: publication_time = observation_time + "
            "offset. Required when legacy_policy is ASSUMED_PUBLICATION."
        )
    )
    calendar_ref: Optional[Any] = None
    instrument_identity: Optional[Any] = None
    instrument_specification: Optional[Any] = None
    venue: Optional[Any] = None
    data_source: Optional[Any] = None
    schema_version: str = Field(default="1.0.0")

    IDENTITY_FIELDS: tuple[str, ...] = (
        "cutoff", "contract_version", "tie_breaker_name", "tie_breaker_version",
        "legacy_policy", "legacy_assumption_text",
        "legacy_publication_offset_seconds", "calendar_ref",
        "instrument_identity", "instrument_specification", "venue",
        "data_source",
    )

    @field_validator("cutoff", mode="before")
    @classmethod
    def _validate_cutoff(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError(
                "cutoff must be a timezone-aware datetime (spec 7.13, "
                "CFG-03: naive cutoff raises)."
            )
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_legacy_policy(self) -> "PitExperimentConfig":
        if self.legacy_policy == LegacyPolicy.ASSUMED_PUBLICATION:
            if not (self.legacy_assumption_text and self.legacy_assumption_text.strip()):
                raise ValueError(
                    "CFG-01 violation (spec 7.13): ASSUMED_PUBLICATION "
                    "requires explicit, non-empty legacy_assumption_text — "
                    "the assumption and its basis are identity-bearing "
                    "declarations, never silent defaults."
                )
            if self.legacy_publication_offset_seconds is None:
                raise ValueError(
                    "CFG-01 violation (spec 7.13): ASSUMED_PUBLICATION "
                    "requires an explicit legacy_publication_offset_seconds "
                    "declaring the assumed publication schedule."
                )
        return self

    @property
    def config_identity_hash(self) -> str:
        """Phase 4 identity hash of this configuration ('pit4.'-prefixed).

        The config ALONE determines the view (CFG-04): every input that
        affects view construction is an identity field here.
        """
        values = {
            "cutoff": self.cutoff,
            "contract_version": PHASE4_IDENTITY_CONTRACT_VERSION,
            "tie_breaker_name": self.tie_breaker.name,
            "tie_breaker_version": self.tie_breaker.version,
            "legacy_policy": self.legacy_policy.value,
            # Spec 6.3 mandate: the declared assumption TEXT becomes an
            # identity field (two different declared assumptions are two
            # different experiments — PROH-LEG-08 class). The offset is
            # the declared assumed publication schedule; equally
            # identity-bearing.
            "legacy_assumption_text": self.legacy_assumption_text,
            "legacy_publication_offset_seconds": (
                self.legacy_publication_offset_seconds
            ),
            "calendar_ref": (
                self.calendar_ref.calendar_ref_hash if self.calendar_ref else None
            ),
            "instrument_identity": (
                self.instrument_identity.instrument_identity_hash
                if self.instrument_identity else None
            ),
            "instrument_specification": (
                self.instrument_specification.specification_hash
                if self.instrument_specification else None
            ),
            "venue": self.venue.venue_hash if self.venue else None,
            "data_source": self.data_source.source_hash if self.data_source else None,
        }
        return identity_hash(
            entity_type="PitExperimentConfig",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values=values,
        )
