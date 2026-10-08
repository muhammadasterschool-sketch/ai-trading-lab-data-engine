"""Governed historical-dataset framework (closure mandate §4).

Real market data NEVER enters evaluation silently. Every dataset must
carry an immutable manifest declaring its full provenance:

- explicit source identity + source version + acquisition timestamp
- coverage (start/end), symbol/instrument identity, exchange/venue
- timezone, frequency
- corporate-action treatment, adjustment policy
- missing-data policy, revision policy
- licensing/provenance metadata
- content checksum + immutable dataset identifier (``preds.`` hash)
- ingestion manifest + validation report linkage

Dataset epistemic states (mandate §4.1 — the project's dataset
semantic model; ``InsufficiencyState`` covers the refusal vocabulary):

    SYNTHETIC          deterministic fixture — NEVER empirical evidence
    REAL_UNVERIFIED    real acquisition claim without verification evidence
    REAL_VERIFIED      real acquisition with complete verification chain
    INSUFFICIENT       real but below the coverage minimum (§17)
    INVALID            failed verification — refused, never repaired

Invariants:
- A SYNTHETIC dataset can NEVER be promoted to REAL_* by verification —
  epistemic class is declared at construction and only a NEW manifest
  (new dataset identity) can change it.
- ``acquisition_timestamp`` is a caller-supplied LOGICAL string — dataset
  identity never depends on the wall clock.
- No dataset content is ever "repaired" in place: failures produce
  explicit INVALID/INSUFFICIENT states (§5 refusal discipline).
"""

from enum import Enum

from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import (
    DATASET_PREFIX,
    prefixed_hash,
)

#: Placeholder sentinel for genuinely-unrecorded fields (never fabricated).
UNRECORDED = "UNRECORDED"

#: Mandatory manifest fields checked by provenance-completeness gates.
MANDATORY_MANIFEST_FIELDS: Tuple[str, ...] = (
    "dataset_name",
    "source_name",
    "source_version",
    "acquisition_timestamp",
    "coverage_start",
    "coverage_end",
    "symbol",
    "timezone",
    "frequency",
    "corporate_action_treatment",
    "adjustment_policy",
    "missing_data_policy",
    "revision_policy",
    "license_basis",
)


class DatasetState(str, Enum):
    """Dataset epistemic states (mandate §4.1).

    SYNTHETIC and REAL_* are DECLARED epistemic classes; INSUFFICIENT
    and INVALID are VERDICTS that verification can force.
    """

    SYNTHETIC = "SYNTHETIC"
    REAL_UNVERIFIED = "REAL_UNVERIFIED"
    REAL_VERIFIED = "REAL_VERIFIED"
    INSUFFICIENT = "INSUFFICIENT"
    INVALID = "INVALID"


class DatasetManifest(BaseModel):
    """Immutable dataset manifest — the dataset's identity + provenance.

    The ``manifest_hash`` (``preds.``) IS the immutable dataset
    identifier: two manifests differing in ANY declared field are two
    different datasets (no hidden definition drift).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_name: str
    source_name: str
    source_version: str
    acquisition_timestamp: str  # logical, caller-supplied
    coverage_start: str  # ISO date, inclusive
    coverage_end: str  # ISO date, inclusive
    symbol: str
    exchange: Optional[str] = None
    timezone: str
    frequency: str  # e.g. "1D", "1h"
    corporate_action_treatment: str  # e.g. "split-adjusted", "none-declared"
    adjustment_policy: str  # e.g. "back-adjusted", "unadjusted"
    missing_data_policy: str  # e.g. "explicit-gap", "forward-fill-forbidden"
    revision_policy: str  # e.g. "append-only-first-arrival"
    license_basis: str  # e.g. "public-domain", "vendor-license-xyz"
    provenance_metadata: Tuple[Tuple[str, str], ...] = ()
    content_checksum: str
    row_count: int
    data_state: DatasetState
    verification_notes: Tuple[str, ...] = ()

    @field_validator(
        "dataset_name", "source_name", "source_version",
        "acquisition_timestamp", "coverage_start", "coverage_end",
        "symbol", "timezone", "frequency", "corporate_action_treatment",
        "adjustment_policy", "missing_data_policy", "revision_policy",
        "license_basis", "content_checksum",
    )
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PredictionContractError(
                "manifest fields must be non-empty strings (use explicit "
                "'UNRECORDED' when a value is genuinely unavailable)"
            )
        return v

    @field_validator("row_count")
    @classmethod
    def _validate_rows(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise PredictionContractError("row_count must be >= 0")
        return v

    @property
    def manifest_hash(self) -> str:
        """Immutable dataset identifier (``preds.``)."""
        return prefixed_hash(
            DATASET_PREFIX,
            {
                "kind": "dataset_manifest",
                "dataset_name": self.dataset_name,
                "source_name": self.source_name,
                "source_version": self.source_version,
                "acquisition_timestamp": self.acquisition_timestamp,
                "coverage_start": self.coverage_start,
                "coverage_end": self.coverage_end,
                "symbol": self.symbol,
                "exchange": self.exchange,
                "timezone": self.timezone,
                "frequency": self.frequency,
                "corporate_action_treatment": (
                    self.corporate_action_treatment
                ),
                "adjustment_policy": self.adjustment_policy,
                "missing_data_policy": self.missing_data_policy,
                "revision_policy": self.revision_policy,
                "license_basis": self.license_basis,
                "provenance_metadata": [
                    [k, v] for k, v in self.provenance_metadata
                ],
                "content_checksum": self.content_checksum,
                "row_count": self.row_count,
                "data_state": self.data_state.value,
            },
        )

    @property
    def dataset_id(self) -> str:
        """Human-referenceable dataset id (manifest hash)."""
        return self.manifest_hash

    @property
    def provenance_complete(self) -> bool:
        """True when every mandatory field carries a real value."""
        for field in MANDATORY_MANIFEST_FIELDS:
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                return False
            if value == UNRECORDED:
                return False
        return True

    @property
    def synthetic(self) -> bool:
        return self.data_state is DatasetState.SYNTHETIC

    @property
    def eligible_for_empirical_evaluation(self) -> bool:
        """Only REAL_VERIFIED datasets can back empirical claims (§1.3)."""
        return self.data_state is DatasetState.REAL_VERIFIED


def dataset_content_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    """Deterministic content checksum over dataset rows (``preds.``).

    Rows are normalized: timestamps to ISO-8601 UTC, floats to 12
    decimals, keys sorted. Two row sequences that differ in any value
    or timestamp produce different checksums.
    """
    normalized: list[dict] = []
    for row in rows:
        item: dict = {}
        for key in sorted(row):
            value = row[key]
            if hasattr(value, "isoformat"):
                item[key] = value.isoformat()
            elif isinstance(value, float):
                if value != value:
                    item[key] = None  # NaN -> explicit null, never hashed
                elif value in (float("inf"), float("-inf")):
                    raise PredictionContractError(
                        "non-finite value in dataset rows — content hash "
                        "refused (RT-PRED-I-007)"
                    )
                else:
                    item[key] = round(value, 12)
            else:
                item[key] = value
        normalized.append(item)
    return prefixed_hash(
        DATASET_PREFIX,
        {"kind": "dataset_content", "rows": normalized},
    )


def synthetic_dataset_manifest(
    *,
    dataset_name: str,
    symbol: str,
    row_count: int,
    content_checksum: str,
    coverage_start: str,
    coverage_end: str,
    generator: str,
    seed: int,
    frequency: str = "1D",
    timezone: str = "UTC",
    provenance_metadata: Sequence[Tuple[str, str]] = (),
    verification_notes: Sequence[str] = (),
) -> DatasetManifest:
    """Construct a clearly-SYNTHETIC manifest for deterministic fixtures.

    The generator and seed are MANDATORY provenance metadata — a
    synthetic dataset without reproducibility metadata is refused.
    """
    if not generator.strip() or not str(seed).strip():
        raise PredictionContractError(
            "synthetic datasets must declare generator + seed "
            "(reproducibility is mandatory)"
        )
    return DatasetManifest(
        dataset_name=dataset_name,
        source_name=f"synthetic:{generator}",
        source_version="1",
        acquisition_timestamp="SYNTHETIC-NO-ACQUISITION",
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        symbol=symbol,
        exchange=None,
        timezone=timezone,
        frequency=frequency,
        corporate_action_treatment="not-applicable-synthetic",
        adjustment_policy="not-applicable-synthetic",
        missing_data_policy="not-applicable-synthetic",
        revision_policy="append-only-first-arrival",
        license_basis="synthetic-fixture",
        provenance_metadata=(
            ("generator", generator),
            ("seed", str(seed)),
            *provenance_metadata,
        ),
        content_checksum=content_checksum,
        row_count=row_count,
        data_state=DatasetState.SYNTHETIC,
        verification_notes=tuple(verification_notes) + (
            "SYNTHETIC — deterministic contract fixture; NEVER empirical "
            "evidence (mandate §1.3)",
        ),
    )


class DatasetVerificationReport(BaseModel):
    """Outcome of verifying a dataset manifest + content (mandate §4.1).

    Caller-asserted states are NEVER trusted: every check below is
    recomputed by :func:`verify_dataset_manifest`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_hash: str
    declared_state: DatasetState
    computed_state: DatasetState
    provenance_complete: bool
    license_declared: bool
    checksum_match: Optional[bool]  # None when no content was supplied
    quality_report_passed: Optional[bool]  # None when not supplied
    source_approved: Optional[bool]  # None when no registry verdict given
    coverage_years: Optional[float] = None
    failures: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return (
            self.computed_state is DatasetState.REAL_VERIFIED
            and not self.failures
        )

    @property
    def verification_hash(self) -> str:
        return prefixed_hash(
            DATASET_PREFIX,
            {
                "kind": "dataset_verification",
                "manifest_hash": self.manifest_hash,
                "declared_state": self.declared_state.value,
                "computed_state": self.computed_state.value,
                "provenance_complete": self.provenance_complete,
                "license_declared": self.license_declared,
                "checksum_match": self.checksum_match,
                "quality_report_passed": self.quality_report_passed,
                "source_approved": self.source_approved,
                "coverage_years": self.coverage_years,
                "failures": list(self.failures),
            },
        )

    @property
    def refusal_reason(self) -> Optional[str]:
        """Machine-readable refusal reason when verification fails."""
        if self.verified:
            return None
        if self.computed_state is DatasetState.INVALID:
            return "DATASET_INVALID"
        if self.computed_state is DatasetState.INSUFFICIENT:
            return "INSUFFICIENT_HISTORY"
        if self.computed_state is DatasetState.SYNTHETIC:
            return "SYNTHETIC_NOT_EMPIRICAL_EVIDENCE"
        if self.computed_state is DatasetState.REAL_UNVERIFIED:
            return "DATASET_UNVERIFIED"
        return "DATASET_UNVERIFIED"


def verify_dataset_manifest(
    manifest: DatasetManifest,
    *,
    recomputed_checksum: Optional[str] = None,
    quality_report_passed: Optional[bool] = None,
    source_approved: Optional[bool] = None,
    coverage_years: Optional[float] = None,
    minimum_years: float = 5.0,
) -> DatasetVerificationReport:
    """Re-verify a dataset manifest from evidence — never from claims.

    Rules (fail-closed, mandate §4.1/§5):
    - SYNTHETIC manifests stay SYNTHETIC — verification NEVER promotes
      them; a checksum match on synthetic content proves only that the
      fixture is the fixture.
    - A declared REAL_VERIFIED manifest is DEMOTED to INVALID when any
      recomputed check fails (checksum mismatch, incomplete provenance,
      failed quality gates, unapproved source, sub-minimum coverage).
    - A declared REAL_UNVERIFIED manifest becomes REAL_VERIFIED only
      when ALL evidence is present and green: complete provenance,
      declared license, matching checksum, passed quality report, and
      an approved source. Otherwise it stays REAL_UNVERIFIED.
    - Real datasets below the coverage minimum read INSUFFICIENT.
    """
    failures: list[str] = []
    notes: list[str] = []

    provenance_complete = manifest.provenance_complete
    license_declared = (
        manifest.license_basis.strip() != ""
        and manifest.license_basis != UNRECORDED
        and manifest.license_basis != "UNKNOWN"
    )

    checksum_match: Optional[bool] = None
    if recomputed_checksum is not None:
        checksum_match = (
            recomputed_checksum == manifest.content_checksum
        )
        if not checksum_match:
            failures.append(
                "content checksum mismatch: manifest declares "
                f"{manifest.content_checksum!r}, content hashes to "
                f"{recomputed_checksum!r}"
            )

    if not provenance_complete:
        missing = [
            f for f in MANDATORY_MANIFEST_FIELDS
            if getattr(manifest, f) in ("", UNRECORDED)
        ]
        failures.append(
            f"provenance incomplete — placeholder fields: {missing}"
        )
    if not license_declared:
        failures.append(
            f"license basis not declared (got {manifest.license_basis!r})"
        )
    if quality_report_passed is False:
        failures.append("data-quality report FAILED (§5 gates)")
    if source_approved is False:
        failures.append(
            "data source not approved by a human decision (mandate §18.1)"
        )

    declared = manifest.data_state
    if declared is DatasetState.SYNTHETIC:
        # Synthetic stays synthetic — checksum only proves fixture integrity
        if checksum_match is False:
            computed = DatasetState.INVALID
        else:
            computed = DatasetState.SYNTHETIC
            notes.append(
                "synthetic fixture integrity "
                + ("confirmed" if checksum_match else "not checked")
            )
    elif declared is DatasetState.REAL_VERIFIED:
        if failures:
            computed = DatasetState.INVALID
        elif (
            quality_report_passed is not True
            or source_approved is not True
            or checksum_match is not True
        ):
            # A REAL_VERIFIED claim without complete verification evidence
            # is exactly the "caller-asserted verified=True" the mandate
            # forbids trusting — demote.
            computed = DatasetState.REAL_UNVERIFIED
            notes.append(
                "declared REAL_VERIFIED without complete verification "
                "evidence (checksum/quality/source) — demoted to "
                "REAL_UNVERIFIED"
            )
        elif coverage_years is not None and coverage_years < minimum_years:
            computed = DatasetState.INSUFFICIENT
            notes.append(
                f"coverage {round(coverage_years, 3)}y < minimum "
                f"{minimum_years}y (mandate §17)"
            )
        else:
            computed = DatasetState.REAL_VERIFIED
    else:  # REAL_UNVERIFIED / INSUFFICIENT / INVALID declared
        if failures:
            computed = DatasetState.INVALID
        elif coverage_years is not None and coverage_years < minimum_years:
            computed = DatasetState.INSUFFICIENT
        elif (
            declared is DatasetState.REAL_UNVERIFIED
            and checksum_match is True
            and quality_report_passed is True
            and source_approved is True
        ):
            computed = DatasetState.REAL_VERIFIED
        else:
            computed = declared

    return DatasetVerificationReport(
        manifest_hash=manifest.manifest_hash,
        declared_state=declared,
        computed_state=computed,
        provenance_complete=provenance_complete,
        license_declared=license_declared,
        checksum_match=checksum_match,
        quality_report_passed=quality_report_passed,
        source_approved=source_approved,
        coverage_years=coverage_years,
        failures=tuple(failures),
        notes=tuple(notes),
    )


class IngestionManifest(BaseModel):
    """Record of one governed dataset ingestion (mandate §4.1).

    ``accepted`` is False whenever the quality report failed or the
    dataset verified INVALID — ingestion refuses, it never repairs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_hash: str
    rows_inspected: int
    rows_rejected: int
    quality_report_hash: str
    verification_hash: str
    policy: str = "reject-on-any-failure"
    accepted: bool
    refusal_reason: Optional[str] = None

    @property
    def ingestion_hash(self) -> str:
        return prefixed_hash(
            DATASET_PREFIX,
            {
                "kind": "ingestion_manifest",
                "manifest_hash": self.manifest_hash,
                "rows_inspected": self.rows_inspected,
                "rows_rejected": self.rows_rejected,
                "quality_report_hash": self.quality_report_hash,
                "verification_hash": self.verification_hash,
                "policy": self.policy,
                "accepted": self.accepted,
                "refusal_reason": self.refusal_reason,
            },
        )


__all__ = [
    "DatasetState",
    "DatasetManifest",
    "MANDATORY_MANIFEST_FIELDS",
    "UNRECORDED",
    "dataset_content_hash",
    "synthetic_dataset_manifest",
    "DatasetVerificationReport",
    "verify_dataset_manifest",
    "IngestionManifest",
]
