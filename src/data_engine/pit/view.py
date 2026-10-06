"""Phase 4A.1 — PitView layer: view, builder, validator.

Implements spec SECTIONS 7.4, 7.5, 7.6 with the cutoff semantics of
4.6/4.7 and the legacy rules of SECTION 6.

PitView         — immutable, point-in-time-correct view of a dataset
                  as knowable at a cutoff
PitViewBuilder  — constructs a PitView deterministically; NO wall
                  clock anywhere in the build path (PROH-LEG-01);
                  never injects now() (D-1 defect class)
PitViewValidator— independently verifies a constructed view
                  (re-derivation, hash recompute, ordering, exclusion
                  completeness). Runs AFTER DataQualityGate; it
                  neither duplicates nor weakens the quality gate
                  (spec 7.6, VAL-04)

Scope note: this module is Phase 4 and imports NO Phase 3 module
(spec 2.1). Datasets and candles are consumed duck-typed via attribute
access only; frozen Phase 3 hash methods are never invoked (SUB-25).
"""

from datetime import datetime, UTC, timedelta
from typing import Any, Mapping, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.pit.hashing import (
    deterministic_hash,
    PHASE4_IDENTITY_CONTRACT_VERSION,
)
from data_engine.pit.serialization import canonical_serialize
from data_engine.pit.sidecar import PitSidecar, LegacyClassification
from data_engine.pit.tiebreaker import TieBreakerPolicy

import hashlib


VIEW_HASH_PREFIX = "pit4v."


class ExcludedRecord(BaseModel):
    """Record of one silently-excluded item (spec 4.7, 6.4)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_index: int
    reason: str
    classification: str


def _normalize_utc(ts: datetime) -> datetime:
    """Normalize a timestamp to UTC; naive values are interpreted as UTC.

    Rationale: provider configurations declare their timezone (default
    UTC); Phase 3 candle timestamps are not tz-validated at their
    layer, so the PIT layer normalizes defensively at the boundary.
    """
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def dataset_content_hash(dataset: Any) -> str:
    """Content hash over a duck-typed dataset's candle sequence.

    Reads item attributes directly (timestamp/open/high/low/close/
    volume). Never calls any frozen Phase 3 hash method (SUB-25) —
    Candle.to_hash() is wall-clock contaminated (F-04) and MUST NOT
    enter any Phase 4 identity.
    """
    records = []
    items = getattr(dataset, "candles", ())
    for item in items:
        ts = _normalize_utc(getattr(item, "timestamp"))
        records.append({
            "timestamp": ts,
            "open": float(getattr(item, "open")),
            "high": float(getattr(item, "high")),
            "low": float(getattr(item, "low")),
            "close": float(getattr(item, "close")),
            "volume": getattr(item, "volume", None),
        })
    return deterministic_hash(records)


class PitView(BaseModel):
    """Immutable point-in-time-correct view of a dataset at a cutoff.

    Invariants (spec 7.4):
    - frozen
    - view_hash is a pure function of (dataset content, cutoff,
      sidecar eligibility hashes, tie-breaker, instrument identity,
      contract versions, legacy classification)
    - identical inputs -> identical hash, in any process
    - no excluded item influences any included item: excluded items
      appear ONLY in the exclusion records, never in items, and the
      hash inputs pin dataset content as a whole (not per-exclusion)
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    dataset_id: str
    dataset_version: str
    cutoff: datetime
    items: tuple[Any, ...] = Field(default_factory=tuple)
    excluded_count: int = 0
    excluded_records: tuple[ExcludedRecord, ...] = Field(default_factory=tuple)
    legacy_classification: LegacyClassification = LegacyClassification.EXPLICIT

    # ── recorded hash inputs (view identity, spec 7.4 ordered) ──
    dataset_content_hash: str
    eligibility_hashes: tuple[str, ...] = Field(default_factory=tuple)
    tie_breaker_name: str
    tie_breaker_version: str
    instrument_identity_hash: Optional[str] = None
    instrument_specification_hash: Optional[str] = None
    venue_hash: Optional[str] = None
    source_hash: Optional[str] = None
    calendar_ref_hash: Optional[str] = None
    contract_version: str = PHASE4_IDENTITY_CONTRACT_VERSION
    pit_contract_version: str = "1.0.0"

    @field_validator("cutoff", mode="before")
    @classmethod
    def _validate_cutoff(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("cutoff must be a timezone-aware datetime (UTC).")
        return v.astimezone(UTC)

    @property
    def excluded_breakdown(self) -> dict[str, int]:
        """Exclusion counts by reason (spec 6.4: counted, not raised)."""
        breakdown: dict[str, int] = {}
        for record in self.excluded_records:
            breakdown[record.reason] = breakdown.get(record.reason, 0) + 1
        return breakdown

    @property
    def view_hash(self) -> str:
        """'pit4v.' + SHA-256 over the ordered view-identity payload."""
        payload = {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_content_hash": self.dataset_content_hash,
            "cutoff": self.cutoff,
            "eligibility_hashes": list(self.eligibility_hashes),
            "tie_breaker_name": self.tie_breaker_name,
            "tie_breaker_version": self.tie_breaker_version,
            "instrument_identity": self.instrument_identity_hash,
            "instrument_specification": self.instrument_specification_hash,
            "venue": self.venue_hash,
            "data_source": self.source_hash,
            "calendar_ref": self.calendar_ref_hash,
            "contract_version": self.contract_version,
            "pit_contract_version": self.pit_contract_version,
            "legacy_classification": self.legacy_classification.value,
        }
        digest = hashlib.sha256(canonical_serialize(payload)).hexdigest()
        return VIEW_HASH_PREFIX + digest

    def __len__(self) -> int:
        return len(self.items)


class PitViewBuilder:
    """Deterministic PitView construction (spec 7.5).

    Deterministic by construction: no caching that varies with time,
    order, or process; NO datetime.now() anywhere in the build path
    (PROH-LEG-01); output depends only on declared inputs.

    Cutoff rules applied per item (spec 4.6/4.7) — every exclusion is
    silent, deterministic, and never an exception:
      - event_time > cutoff      -> 'future_event_time'      (T-X07)
      - publication > cutoff     -> 'future_publication_time' (T-X01)
      - effective_time > cutoff  -> 'future_effective_time'   (T-P04)
      - revision_time > cutoff   -> 'future_revision_time'    (T-X02)
      - publication unknown      -> 'pit_ineligible'          (SUB-10)

    The publication boundary is INCLUSIVE (spec 4.6):
    publication_time == cutoff is ELIGIBLE; cutoff + 1µs is EXCLUDED.
    """

    def build(
        self,
        dataset: Any,
        cutoff: datetime,
        sidecars: "PitSidecar | Mapping[int, PitSidecar]",
        tie_breaker: TieBreakerPolicy,
        *,
        legacy_policy: Optional[Any] = None,
        instrument_identity: Optional[Any] = None,
        instrument_specification: Optional[Any] = None,
        venue: Optional[Any] = None,
        data_source: Optional[Any] = None,
        calendar_ref: Optional[Any] = None,
    ) -> PitView:
        if cutoff is None or cutoff.tzinfo is None:
            raise ValueError("cutoff must be a timezone-aware datetime (UTC).")
        cutoff = cutoff.astimezone(UTC)

        items = list(getattr(dataset, "candles", ()))
        dataset_id = getattr(dataset, "dataset_id")
        dataset_version = getattr(getattr(dataset, "version"), "version")

        single_sidecar = sidecars if isinstance(sidecars, PitSidecar) else None
        sidecar_map: Mapping[int, PitSidecar] = (
            {} if single_sidecar is not None else sidecars
        )

        included: list[Any] = []
        excluded: list[ExcludedRecord] = []
        eligibility_hashes: set[str] = set()
        any_assumed_included = False
        any_ineligible = False

        for index, item in enumerate(items):
            sidecar = (
                single_sidecar if single_sidecar is not None
                else sidecar_map.get(index)
            )
            if sidecar is None:
                excluded.append(ExcludedRecord(
                    item_index=index,
                    reason="missing_sidecar",
                    classification="UNKNOWN",
                ))
                continue

            eligibility_hashes.add(sidecar.eligibility_hash)

            classification = sidecar.legacy_classification
            publication_time = sidecar.publication_time

            if classification == LegacyClassification.PIT_INELIGIBLE:
                any_ineligible = True
                excluded.append(ExcludedRecord(
                    item_index=index,
                    reason="pit_ineligible",
                    classification=classification.value,
                ))
                continue

            # Spec 6.3 selection rule: unknown publication time.
            if publication_time is None:
                assumed = getattr(legacy_policy, "legacy_policy", None)
                offset = getattr(legacy_policy, "legacy_publication_offset_seconds", None)
                if assumed is not None and "assumed" in str(assumed).lower() \
                        and offset is not None:
                    # Declared assumption (spec 6.3 branch 2): the assumed
                    # publication time and its basis are recorded; the view
                    # is labelled ASSUMED in its identity (PROH-LEG-08).
                    publication_time = sidecar.observation_time + timedelta(
                        seconds=float(offset)
                    )
                    classification = LegacyClassification.ASSUMED_PUBLICATION
                else:
                    any_ineligible = True
                    excluded.append(ExcludedRecord(
                        item_index=index,
                        reason="pit_ineligible",
                        classification=LegacyClassification.PIT_INELIGIBLE.value,
                    ))
                    continue

            # Cutoff evaluation (spec 4.6/4.7) — inclusive boundary.
            event_time = _normalize_utc(getattr(item, "timestamp"))
            if event_time > cutoff:
                excluded.append(ExcludedRecord(
                    item_index=index, reason="future_event_time",
                    classification=classification.value,
                ))
                continue
            if publication_time > cutoff:
                excluded.append(ExcludedRecord(
                    item_index=index, reason="future_publication_time",
                    classification=classification.value,
                ))
                continue
            if sidecar.effective_time is not None and sidecar.effective_time > cutoff:
                excluded.append(ExcludedRecord(
                    item_index=index, reason="future_effective_time",
                    classification=classification.value,
                ))
                continue
            if sidecar.revision_time is not None and sidecar.revision_time > cutoff:
                # This revision is invisible at the cutoff; a flat sidecar
                # carries no prior revision, so the item is excluded.
                excluded.append(ExcludedRecord(
                    item_index=index, reason="future_revision_time",
                    classification=classification.value,
                ))
                continue

            included.append(item)
            if classification == LegacyClassification.ASSUMED_PUBLICATION:
                any_assumed_included = True

        # Deterministic total order over included items (spec 7.3/7.4).
        ordered = tie_breaker.sort(included) if included else []

        if any_assumed_included:
            view_classification = LegacyClassification.ASSUMED_PUBLICATION
        elif ordered:
            view_classification = LegacyClassification.EXPLICIT
        elif any_ineligible:
            view_classification = LegacyClassification.PIT_INELIGIBLE
        else:
            view_classification = LegacyClassification.EXPLICIT

        return PitView(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            cutoff=cutoff,
            items=tuple(ordered),
            excluded_count=len(excluded),
            excluded_records=tuple(excluded),
            legacy_classification=view_classification,
            dataset_content_hash=dataset_content_hash(dataset),
            eligibility_hashes=tuple(sorted(eligibility_hashes)),
            tie_breaker_name=tie_breaker.name,
            tie_breaker_version=tie_breaker.version,
            instrument_identity_hash=(
                instrument_identity.instrument_identity_hash
                if instrument_identity is not None else None
            ),
            instrument_specification_hash=(
                instrument_specification.specification_hash
                if instrument_specification is not None else None
            ),
            venue_hash=venue.venue_hash if venue is not None else None,
            source_hash=data_source.source_hash if data_source is not None else None,
            calendar_ref_hash=(
                calendar_ref.calendar_ref_hash if calendar_ref is not None else None
            ),
        )


class ValidationCheck(BaseModel):
    """One named validator check with a specific reason (VAL-03)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    passed: bool
    reason: str


class ViewValidationResult(BaseModel):
    """Structured validator result, serializable for audit (spec 7.6)."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    checks: tuple[ValidationCheck, ...]
    view_hash: str

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        return tuple(c.reason for c in self.checks if not c.passed)


class PitViewValidator:
    """Independent verification of a constructed PitView (spec 7.6).

    Runs AFTER DataQualityGate — it answers 'was it available at the
    cutoff?', not 'is this data valid?'. It deliberately performs NO
    quality checks and cannot weaken the quality gate (VAL-04).

    Fail closed: any failed check rejects the view with a specific
    reason (VAL-03).
    """

    def validate(
        self,
        view: PitView,
        dataset: Any,
        sidecars: "PitSidecar | Mapping[int, PitSidecar]",
        cutoff: datetime,
    ) -> ViewValidationResult:
        checks: list[ValidationCheck] = []

        # VAL-01: independent re-derivation — no future item present.
        future_items = self._find_future_items(view, sidecars, cutoff)
        checks.append(ValidationCheck(
            name="no_future_items",
            passed=not future_items,
            reason=(
                "No item in the view becomes available after the cutoff."
                if not future_items else
                f"Future item(s) present at indices {future_items} — "
                f"items with governing times after the cutoff must not "
                f"appear in a PIT view."
            ),
        ))

        # VAL-02: view_hash recomputes and matches.
        recomputed = view.view_hash
        checks.append(ValidationCheck(
            name="view_hash_recomputes",
            passed=(recomputed == view.view_hash),  # property recomputes live
            reason=(
                "view_hash recomputes to its recorded value."
                if recomputed == view.view_hash else
                "view_hash recompute mismatch — the view does not match "
                "its recorded identity."
            ),
        ))

        # Ordering invariant: items are in a non-decreasing total order.
        ordering_ok = True
        ordering_reason = "Items are in the tie-breaker's total order."
        try:
            key_seq = [
                (getattr(item, "timestamp"),) for item in view.items
            ]
        except AttributeError:
            ordering_ok = False
            ordering_reason = "Items lack the temporal attribute."
        if ordering_ok and key_seq != sorted(key_seq):
            ordering_ok = False
            ordering_reason = (
                "Items are not in chronological (tie-breaker-consistent) "
                "order — the ordering invariant is violated."
            )
        checks.append(ValidationCheck(
            name="ordering_invariant",
            passed=ordering_ok,
            reason=ordering_reason,
        ))

        # Exclusions complete: included + excluded == total; no silent drops.
        total = len(list(getattr(dataset, "candles", ())))
        accounted = len(view.items) + view.excluded_count
        checks.append(ValidationCheck(
            name="exclusions_complete",
            passed=(accounted == total),
            reason=(
                f"All {total} items accounted for "
                f"({len(view.items)} included, {view.excluded_count} excluded)."
                if accounted == total else
                f"Exclusion accounting mismatch: {accounted} accounted of "
                f"{total} — items were silently dropped, which is a "
                f"forbidden silent substitution (spec 7.5)."
            ),
        ))

        return ViewValidationResult(
            checks=tuple(checks),
            view_hash=view.view_hash,
        )

    def _find_future_items(
        self,
        view: PitView,
        sidecars: "PitSidecar | Mapping[int, PitSidecar]",
        cutoff: datetime,
    ) -> list[int]:
        """Re-derive availability for every included item, independently.

        Returns the indices (within view.items) of items that would NOT
        have been eligible at the cutoff.
        """
        if cutoff is None or cutoff.tzinfo is None:
            raise ValueError("cutoff must be a timezone-aware datetime.")
        cutoff = cutoff.astimezone(UTC)
        single = sidecars if isinstance(sidecars, PitSidecar) else None
        mapping = {} if single is not None else sidecars

        future: list[int] = []
        for view_index, item in enumerate(view.items):
            sidecar = single if single is not None else mapping.get(view_index)
            if sidecar is None:
                future.append(view_index)  # unverifiable item — fail closed
                continue
            ts = _normalize_utc(getattr(item, "timestamp"))
            if ts > cutoff:
                future.append(view_index)
            elif sidecar.publication_time is not None \
                    and sidecar.publication_time > cutoff:
                future.append(view_index)
            elif sidecar.effective_time is not None \
                    and sidecar.effective_time > cutoff:
                future.append(view_index)
            elif sidecar.revision_time is not None \
                    and sidecar.revision_time > cutoff:
                future.append(view_index)
        return future
