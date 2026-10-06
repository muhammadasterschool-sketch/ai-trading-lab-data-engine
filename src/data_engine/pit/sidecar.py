"""Phase 4A.1 — PitSidecar: immutable temporal-metadata snapshot.

Implements spec SECTION 7.1 and the legacy-data rules of SECTION 6
(PROH-LEG-01 .. PROH-LEG-09).

A sidecar is an immutable temporal-metadata snapshot for exactly one
dataset version. It is frozen after construction; one sidecar serves
one dataset version; schema evolution produces a NEW sidecar for a
NEW dataset version (never an overwrite).

Identity fields (spec 7.1, ordered):
    dataset_id, dataset_version, event_time, observation_time,
    publication_time, effective_time, revision_time,
    legacy_classification, contract_version
ingestion_time is EXCLUDED (AUDIT class; spec 2.4 / 7.1).

Legacy classification (spec 6.3):
    EXPLICIT              — explicit publication_time exists
    ASSUMED_PUBLICATION   — publication time declared as an assumption,
                            with the assumption basis recorded
    PIT_INELIGIBLE        — publication time unknown and undeterminable;
                            EXCLUDED from every PIT view, reason recorded

Prohibitions enforced here:
    PROH-LEG-01  no wall-clock injection at view-build time (no now()
                 anywhere in this module)
    PROH-LEG-02  no fabricated publication evidence (EXPLICIT requires
                 a publication_time)
    PROH-LEG-05  a legacy sidecar is never indistinguishable from an
                 explicit one (classification is an identity field)
    PROH-LEG-07  ingestion_time is None or fixed at construction —
                 never computed as now() at view-build time
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import (
    identity_hash,
    eligibility_hash,
    PHASE4_IDENTITY_CONTRACT_VERSION,
)


class LegacyClassification(str, Enum):
    """Mandated legacy classification (spec 6.3)."""
    EXPLICIT = "EXPLICIT"
    ASSUMED_PUBLICATION = "ASSUMED_PUBLICATION"
    PIT_INELIGIBLE = "PIT_INELIGIBLE"


class PitSidecar(BaseModel):
    """Immutable temporal-metadata snapshot for one dataset version.

    All temporal fields are timezone-aware and UTC-normalized; naive
    values are rejected. Cross-field ordering follows spec 4.3.

    The eligibility_hash covers exactly:
    {event_time, observation_time, publication_time, effective_time,
    revision_time} — ingestion_time is EXCLUDED (spec 2.7).

    The sidecar_hash is a Phase 4 identity hash over the ordered
    identity fields (spec 2.5 / 7.1); it is invariant under changes to
    ingestion_time (AUDIT class) and invariant under re-construction at
    a different wall-clock time (PROH-LEG-01/06, ID-WC-03).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ── identity fields (spec 7.1, ordered) ──
    dataset_id: str = Field(..., min_length=1)
    dataset_version: str = Field(..., min_length=1)
    event_time: datetime
    observation_time: datetime
    publication_time: Optional[datetime] = None
    effective_time: Optional[datetime] = None
    revision_time: Optional[datetime] = None
    legacy_classification: LegacyClassification = LegacyClassification.EXPLICIT
    contract_version: str = Field(default=PHASE4_IDENTITY_CONTRACT_VERSION)

    # ── entity schema version (spec 2.6) ──
    schema_version: str = Field(default="1.0.0")

    # ── AUDIT class — NEVER in identity (spec 2.4, 7.1) ──
    # PROH-LEG-07: None or fixed at dataset-version creation; never now().
    ingestion_time: Optional[datetime] = None

    # ── legacy records (spec 6.3; descriptive, not sidecar identity) ──
    # The assumption TEXT participates in PitExperimentConfig identity
    # (spec 7.13) and the classification participates here.
    assumption_basis: Optional[str] = None
    ineligible_reason: Optional[str] = None

    #: Ordered identity-field allowlist (spec 2.3, 7.1). Frozen contract.
    IDENTITY_FIELDS: tuple[str, ...] = (
        "dataset_id",
        "dataset_version",
        "event_time",
        "observation_time",
        "publication_time",
        "effective_time",
        "revision_time",
        "legacy_classification",
        "contract_version",
    )

    @field_validator("dataset_id", "dataset_version", "contract_version",
                     "schema_version")
    @classmethod
    def _validate_non_empty_str(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("identifier/version fields must be non-empty strings")
        return v

    @field_validator("event_time", "observation_time", "publication_time",
                     "effective_time", "revision_time", "ingestion_time",
                     mode="before")
    @classmethod
    def _validate_timezone_aware(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Reject naive datetimes and normalize to UTC (spec 4.4)."""
        if v is None:
            return None
        if v.tzinfo is None:
            raise ValueError(
                "Naive datetime is not allowed. All PIT timestamps must be "
                "timezone-aware and UTC-normalized."
            )
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_sidecar(self) -> "PitSidecar":
        """Enforce spec 4.3 ordering and the legacy prohibitions of 6.2/6.3."""
        # Spec 4.3 cross-field ordering (null operands skip; equality valid).
        constraints = (
            ("event_time", self.event_time, "observation_time", self.observation_time),
            ("observation_time", self.observation_time,
             "publication_time", self.publication_time),
            ("publication_time", self.publication_time,
             "revision_time", self.revision_time),
        )
        for left_name, left, right_name, right in constraints:
            if left is None or right is None:
                continue
            if left > right:
                raise ValueError(
                    f"Temporal ordering violation (spec 4.3): "
                    f"{left_name} ({left.isoformat()}) > "
                    f"{right_name} ({right.isoformat()})."
                )

        # PROH-LEG-02 / spec 6.3: EXPLICIT requires an explicit publication_time.
        if self.legacy_classification == LegacyClassification.EXPLICIT \
                and self.publication_time is None:
            raise ValueError(
                "PROH-LEG-02 violation: legacy_classification=EXPLICIT requires "
                "an explicit publication_time. A sidecar without publication "
                "evidence must be ASSUMED_PUBLICATION (with basis) or "
                "PIT_INELIGIBLE (with reason) — never EXPLICIT."
            )
        # Spec 6.3: an assumption must be declared explicitly, never silent.
        if self.legacy_classification == LegacyClassification.ASSUMED_PUBLICATION:
            if not (self.assumption_basis and self.assumption_basis.strip()):
                raise ValueError(
                    "Spec 6.3 violation: ASSUMED_PUBLICATION requires a "
                    "non-empty assumption_basis recording the assumption and "
                    "its basis (PROH-LEG-02: never fabricate silently)."
                )
            if self.publication_time is None:
                raise ValueError(
                    "Spec 6.3 violation: ASSUMED_PUBLICATION declares an "
                    "assumed publication_time; the assumed value must be "
                    "recorded in publication_time."
                )
        # Spec 6.3: PIT_INELIGIBLE records its reason; no publication evidence.
        if self.legacy_classification == LegacyClassification.PIT_INELIGIBLE:
            if self.publication_time is not None:
                raise ValueError(
                    "Spec 6.3 violation: PIT_INELIGIBLE means publication time "
                    "is unknown — publication_time must be None."
                )
            if not (self.ineligible_reason and self.ineligible_reason.strip()):
                raise ValueError(
                    "Spec 6.3 violation: PIT_INELIGIBLE requires a recorded "
                    "ineligible_reason (the exclusion is recorded, spec 6.4)."
                )
        return self

    @property
    def eligibility_hash(self) -> str:
        """Phase 4 eligibility hash (spec 2.7). ingestion_time EXCLUDED."""
        return eligibility_hash({
            "event_time": self.event_time,
            "observation_time": self.observation_time,
            "publication_time": self.publication_time,
            "effective_time": self.effective_time,
            "revision_time": self.revision_time,
        })

    @property
    def sidecar_hash(self) -> str:
        """Phase 4 identity hash over the ordered allowlist (spec 2.5, 7.1).

        Pure function of the allowlisted values; invariant under
        ingestion_time changes and under wall-clock re-construction.
        """
        values = {name: getattr(self, name) for name in self.IDENTITY_FIELDS}
        values["legacy_classification"] = self.legacy_classification.value
        return identity_hash(
            entity_type="PitSidecar",
            schema_version=self.schema_version,
            identity_fields=self.IDENTITY_FIELDS,
            values=values,
        )
