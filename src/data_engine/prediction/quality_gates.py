"""Deterministic data-quality gates for real datasets (closure mandate §5).

Every real dataset must pass these gates before it can participate in
evaluation. Gate coverage (mandate §5, exhaustive):

    QG-01 timestamp ordering           QG-09 discontinuities
    QG-02 duplicate timestamps         QG-10 symbol identity mismatch
    QG-03 missing intervals            QG-11 dataset coverage gaps
    QG-04 impossible OHLC relations    QG-12 corporate-action inconsistency
    QG-05 negative/invalid prices      QG-13 revision contamination
    QG-06 invalid volumes              QG-14 accidental look-ahead
    QG-07 timezone inconsistency       QG-15 dataset checksum mismatch
    QG-08 future timestamps            QG-16 provenance incompleteness

Discipline:
- every failure produces an EXPLICIT refusal state (INVALID, or
  DATA_INSUFFICIENT for coverage-class findings) — data is never
  silently repaired in a way that changes its epistemic status;
- gates are deterministic pure functions of (rows, manifest, bounds);
- findings carry affected-row indices so refusals are inspectable.
"""

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.datasets import (
    DatasetManifest,
    dataset_content_hash,
)
from data_engine.prediction.identity import QUALITY_PREFIX, prefixed_hash

#: Refusal states a failed report can carry (machine-readable).
QUALITY_REFUSAL_INVALID = "INVALID"
QUALITY_REFUSAL_INSUFFICIENT = "DATA_INSUFFICIENT"


class QualityGateID(str, Enum):
    """The 16 mandated gate identifiers (QG-01..QG-16)."""

    TIMESTAMP_ORDERING = "QG-01-timestamp-ordering"
    DUPLICATE_TIMESTAMPS = "QG-02-duplicate-timestamps"
    MISSING_INTERVALS = "QG-03-missing-intervals"
    OHLC_RELATIONSHIPS = "QG-04-impossible-ohlc"
    NEGATIVE_PRICES = "QG-05-negative-invalid-prices"
    INVALID_VOLUMES = "QG-06-invalid-volumes"
    TIMEZONE_CONSISTENCY = "QG-07-timezone-consistency"
    FUTURE_TIMESTAMPS = "QG-08-future-timestamps"
    DISCONTINUITIES = "QG-09-discontinuities"
    SYMBOL_IDENTITY = "QG-10-symbol-identity"
    COVERAGE_GAPS = "QG-11-coverage-gaps"
    CORPORATE_ACTION_CONSISTENCY = "QG-12-corporate-action-consistency"
    REVISION_CONTAMINATION = "QG-13-revision-contamination"
    LOOKAHEAD_CONTAMINATION = "QG-14-lookahead"
    DATASET_CHECKSUM = "QG-15-checksum-mismatch"
    PROVENANCE_COMPLETENESS = "QG-16-provenance-incompleteness"


#: Gates whose failure demotes coverage rather than validity outright.
_COVERAGE_GATES = frozenset({
    QualityGateID.MISSING_INTERVALS,
    QualityGateID.DISCONTINUITIES,
    QualityGateID.COVERAGE_GAPS,
})


class QualityGateFinding(BaseModel):
    """One gate verdict with inspectable evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: QualityGateID
    passed: bool
    detail: str
    affected_rows: Tuple[int, ...] = ()

    @property
    def applicable(self) -> bool:
        """False when the gate is N/A for this dataset shape (e.g. no
        OHLC fields on a close-only series) — recorded, never hidden."""
        return not self.detail.startswith("N/A")


class DataQualityReport(BaseModel):
    """Full deterministic quality verdict over one dataset (§5).

    ``refusal_state`` is the machine-readable refusal: INVALID for hard
    gate failures, DATA_INSUFFICIENT for coverage-class failures, None
    when every applicable gate passed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_manifest_hash: str
    findings: Tuple[QualityGateFinding, ...]
    rows_inspected: int

    @property
    def failures(self) -> Tuple[QualityGateFinding, ...]:
        return tuple(f for f in self.findings if not f.passed and f.applicable)

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def refusal_state(self) -> Optional[str]:
        if self.passed:
            return None
        if any(f.gate in _COVERAGE_GATES for f in self.failures):
            # coverage-class failures are insufficient-data refusals when
            # no validity gate also failed
            if all(f.gate in _COVERAGE_GATES for f in self.failures):
                return QUALITY_REFUSAL_INSUFFICIENT
            return QUALITY_REFUSAL_INVALID
        return QUALITY_REFUSAL_INVALID

    @property
    def quality_hash(self) -> str:
        return prefixed_hash(
            QUALITY_PREFIX,
            {
                "kind": "data_quality_report",
                "dataset_manifest_hash": self.dataset_manifest_hash,
                "rows_inspected": self.rows_inspected,
                "findings": [
                    {
                        "gate": f.gate.value,
                        "passed": f.passed,
                        "detail": f.detail,
                        "affected_rows": list(f.affected_rows),
                    }
                    for f in self.findings
                ],
            },
        )


def _row_timestamp(row: Mapping[str, Any]) -> Optional[datetime]:
    ts = row.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        return None
    return ts


def _finite(value: Any) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return v == v and v not in (float("inf"), float("-inf"))


_FREQUENCY_MAX_GAP: dict[str, timedelta] = {
    "1D": timedelta(days=7),      # trading-day series: week + holiday slack
    "1d": timedelta(days=7),
    "1W": timedelta(days=21),
    "1w": timedelta(days=21),
    "1h": timedelta(hours=36),
    "4h": timedelta(days=4),
}
_DEFAULT_MAX_GAP = timedelta(days=31)


def validate_ohlcv(
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest: DatasetManifest,
    acquisition_bound: Optional[datetime] = None,
    evaluation_cutoff: Optional[datetime] = None,
    max_gap: Optional[timedelta] = None,
    split_symbol: Optional[str] = None,
) -> DataQualityReport:
    """Run all 16 gates deterministically over ``rows`` (mandate §5).

    - ``acquisition_bound``: the acquisition timestamp bound — bars
      dated after it mean the "acquisition" could not have seen them
      (QG-08 future timestamps).
    - ``evaluation_cutoff``: the PIT evaluation cutoff — bars beyond it
      in an evaluation extract are accidental look-ahead (QG-14).
    - ``max_gap``: tolerated calendar gap for QG-03; defaults from the
      manifest frequency (7 days for daily series).
    """
    findings: list[QualityGateFinding] = []
    n = len(rows)

    timestamps: list[Optional[datetime]] = []
    bad_tz_rows: list[int] = []
    for i, row in enumerate(rows):
        ts = _row_timestamp(row)
        timestamps.append(ts)
        if ts is None:
            bad_tz_rows.append(i)

    # QG-07 timezone consistency -----------------------------------------
    if n == 0:
        findings.append(QualityGateFinding(
            gate=QualityGateID.TIMEZONE_CONSISTENCY,
            passed=False,
            detail="empty dataset — no rows to validate",
        ))
    elif bad_tz_rows:
        findings.append(QualityGateFinding(
            gate=QualityGateID.TIMEZONE_CONSISTENCY,
            passed=False,
            detail=(
                f"{len(bad_tz_rows)} rows carry naive/missing timestamps"
            ),
            affected_rows=tuple(bad_tz_rows[:50]),
        ))
    else:
        offsets = {ts.utcoffset() for ts in timestamps if ts is not None}
        findings.append(QualityGateFinding(
            gate=QualityGateID.TIMEZONE_CONSISTENCY,
            passed=True,
            detail=(
                f"all {n} timestamps tz-aware; "
                f"{len(offsets)} distinct UTC offsets (DST-legal)"
            ),
        ))

    valid_ts = [ts for ts in timestamps if ts is not None]

    # QG-01 timestamp ordering -------------------------------------------
    order_violations = [
        i for i in range(1, n)
        if timestamps[i] is not None and timestamps[i - 1] is not None
        and timestamps[i] < timestamps[i - 1]
    ]
    findings.append(QualityGateFinding(
        gate=QualityGateID.TIMESTAMP_ORDERING,
        passed=not order_violations,
        detail=(
            "timestamps non-decreasing"
            if not order_violations
            else f"{len(order_violations)} ordering violations "
                 f"(first at row {order_violations[0]})"
        ),
        affected_rows=tuple(order_violations[:50]),
    ))

    # QG-02 duplicate timestamps -----------------------------------------
    seen: dict[datetime, int] = {}
    duplicates: list[int] = []
    for i, ts in enumerate(timestamps):
        if ts is None:
            continue
        if ts in seen:
            duplicates.append(i)
        else:
            seen[ts] = i
    findings.append(QualityGateFinding(
        gate=QualityGateID.DUPLICATE_TIMESTAMPS,
        passed=not duplicates,
        detail=(
            "no duplicate timestamps"
            if not duplicates
            else f"{len(duplicates)} duplicate-timestamp rows "
                 f"(first at row {duplicates[0]})"
        ),
        affected_rows=tuple(duplicates[:50]),
    ))

    # QG-13 revision contamination (duplicates with DIFFERENT values) ----
    revisions: list[int] = []
    for i in duplicates:
        first = seen.get(timestamps[i])  # type: ignore[arg-type]
        if first is None:
            continue
        if rows[i].get("close") != rows[first].get("close"):
            revisions.append(i)
    findings.append(QualityGateFinding(
        gate=QualityGateID.REVISION_CONTAMINATION,
        passed=not revisions,
        detail=(
            "no value-changing revisions in a clean extract"
            if not revisions
            else f"{len(revisions)} duplicate rows carry different values "
                 f"— revision contamination (first at row {revisions[0]})"
        ),
        affected_rows=tuple(revisions[:50]),
    ))

    # QG-03 missing intervals ---------------------------------------------
    tolerance = max_gap or _FREQUENCY_MAX_GAP.get(
        manifest.frequency, _DEFAULT_MAX_GAP
    )
    gap_rows: list[int] = []
    for i in range(1, n):
        a, b = timestamps[i - 1], timestamps[i]
        if a is None or b is None:
            continue
        if b - a > tolerance:
            gap_rows.append(i)
    findings.append(QualityGateFinding(
        gate=QualityGateID.MISSING_INTERVALS,
        passed=not gap_rows,
        detail=(
            f"no interval exceeds the {tolerance} tolerance "
            f"for frequency {manifest.frequency!r}"
            if not gap_rows
            else f"{len(gap_rows)} gaps exceed {tolerance} "
                 f"(first after row {gap_rows[0] - 1})"
        ),
        affected_rows=tuple(gap_rows[:50]),
    ))

    # QG-04 impossible OHLC relationships ---------------------------------
    has_ohlc = any(
        row.get("high") is not None or row.get("low") is not None
        for row in rows
    )
    if not has_ohlc:
        findings.append(QualityGateFinding(
            gate=QualityGateID.OHLC_RELATIONSHIPS,
            passed=True,
            detail=(
                "N/A — close-only dataset: OHLC gate not applicable "
                "(recorded, never assumed)"
            ),
        ))
    else:
        bad_ohlc: list[int] = []
        for i, row in enumerate(rows):
            o, h = row.get("open"), row.get("high")
            l, c = row.get("low"), row.get("close")
            vals = [v for v in (o, h, l, c) if v is not None]
            if not all(_finite(v) for v in vals):
                bad_ohlc.append(i)
                continue
            if h is not None and l is not None and float(h) < float(l):
                bad_ohlc.append(i)
                continue
            if o is not None and h is not None and l is not None:
                if not (float(l) <= float(o) <= float(h)):
                    bad_ohlc.append(i)
                    continue
            if c is not None and h is not None and l is not None:
                if not (float(l) <= float(c) <= float(h)):
                    bad_ohlc.append(i)
        findings.append(QualityGateFinding(
            gate=QualityGateID.OHLC_RELATIONSHIPS,
            passed=not bad_ohlc,
            detail=(
                "all OHLC relationships consistent"
                if not bad_ohlc
                else f"{len(bad_ohlc)} rows with impossible OHLC "
                     f"(first at row {bad_ohlc[0]})"
            ),
            affected_rows=tuple(bad_ohlc[:50]),
        ))

    # QG-05 negative/invalid prices ---------------------------------------
    bad_prices: list[int] = []
    for i, row in enumerate(rows):
        for field in ("open", "high", "low", "close"):
            v = row.get(field)
            if v is None:
                continue
            if not _finite(v) or float(v) <= 0.0:
                bad_prices.append(i)
                break
    findings.append(QualityGateFinding(
        gate=QualityGateID.NEGATIVE_PRICES,
        passed=not bad_prices,
        detail=(
            "all prices finite and positive"
            if not bad_prices
            else f"{len(bad_prices)} rows with non-positive/NaN prices "
                 f"(first at row {bad_prices[0]})"
        ),
        affected_rows=tuple(bad_prices[:50]),
    ))

    # QG-06 invalid volumes ------------------------------------------------
    has_volume = any(row.get("volume") is not None for row in rows)
    if not has_volume:
        findings.append(QualityGateFinding(
            gate=QualityGateID.INVALID_VOLUMES,
            passed=True,
            detail="N/A — volume-free dataset (recorded, never assumed)",
        ))
    else:
        bad_volume: list[int] = []
        for i, row in enumerate(rows):
            v = row.get("volume")
            if v is None or not _finite(v) or float(v) < 0.0:
                bad_volume.append(i)
        findings.append(QualityGateFinding(
            gate=QualityGateID.INVALID_VOLUMES,
            passed=not bad_volume,
            detail=(
                "all volumes finite and non-negative"
                if not bad_volume
                else f"{len(bad_volume)} rows with invalid volume "
                     f"(first at row {bad_volume[0]})"
            ),
            affected_rows=tuple(bad_volume[:50]),
        ))

    # QG-08 future timestamps (acquisition bound) --------------------------
    if acquisition_bound is None:
        findings.append(QualityGateFinding(
            gate=QualityGateID.FUTURE_TIMESTAMPS,
            passed=True,
            detail="N/A — no acquisition bound declared",
        ))
    else:
        future_rows = [
            i for i, ts in enumerate(timestamps)
            if ts is not None and ts > acquisition_bound
        ]
        findings.append(QualityGateFinding(
            gate=QualityGateID.FUTURE_TIMESTAMPS,
            passed=not future_rows,
            detail=(
                f"no bar dated after the acquisition bound "
                f"{acquisition_bound.isoformat()}"
                if not future_rows
                else f"{len(future_rows)} bars post-date the acquisition "
                     f"bound — acquisition could not have seen them "
                     f"(first at row {future_rows[0]})"
            ),
            affected_rows=tuple(future_rows[:50]),
        ))

    # QG-14 accidental look-ahead (evaluation cutoff) ----------------------
    if evaluation_cutoff is None:
        findings.append(QualityGateFinding(
            gate=QualityGateID.LOOKAHEAD_CONTAMINATION,
            passed=True,
            detail="N/A — no evaluation cutoff declared",
        ))
    else:
        lookahead_rows = [
            i for i, ts in enumerate(timestamps)
            if ts is not None and ts > evaluation_cutoff
        ]
        findings.append(QualityGateFinding(
            gate=QualityGateID.LOOKAHEAD_CONTAMINATION,
            passed=not lookahead_rows,
            detail=(
                f"no bar beyond the evaluation cutoff "
                f"{evaluation_cutoff.isoformat()}"
                if not lookahead_rows
                else f"{len(lookahead_rows)} bars beyond the evaluation "
                     f"cutoff — accidental look-ahead (first at row "
                     f"{lookahead_rows[0]})"
            ),
            affected_rows=tuple(lookahead_rows[:50]),
        ))

    # QG-09 discontinuities (hard coverage breaks) -------------------------
    hard_gap = max(tolerance * 3, timedelta(days=90))
    discontinuity_rows = [
        i for i in range(1, n)
        if timestamps[i] is not None and timestamps[i - 1] is not None
        and timestamps[i] - timestamps[i - 1] > hard_gap
    ]
    findings.append(QualityGateFinding(
        gate=QualityGateID.DISCONTINUITIES,
        passed=not discontinuity_rows,
        detail=(
            f"no discontinuity exceeds {hard_gap}"
            if not discontinuity_rows
            else f"{len(discontinuity_rows)} hard discontinuities > "
                 f"{hard_gap} (first after row "
                 f"{discontinuity_rows[0] - 1})"
        ),
        affected_rows=tuple(discontinuity_rows[:50]),
    ))

    # QG-10 symbol identity mismatch ----------------------------------------
    expected_symbol = split_symbol or manifest.symbol
    rows_with_symbol = [
        i for i, row in enumerate(rows) if row.get("symbol") is not None
    ]
    if not rows_with_symbol:
        findings.append(QualityGateFinding(
            gate=QualityGateID.SYMBOL_IDENTITY,
            passed=True,
            detail=(
                f"N/A — rows carry no symbol field; manifest symbol "
                f"{expected_symbol!r} governs the dataset"
            ),
        ))
    else:
        mismatches = [
            i for i in rows_with_symbol
            if rows[i].get("symbol") != expected_symbol
        ]
        findings.append(QualityGateFinding(
            gate=QualityGateID.SYMBOL_IDENTITY,
            passed=not mismatches,
            detail=(
                f"all {len(rows_with_symbol)} row symbols match "
                f"{expected_symbol!r}"
                if not mismatches
                else f"{len(mismatches)} rows carry a foreign symbol "
                     f"(expected {expected_symbol!r}; first at row "
                     f"{mismatches[0]})"
            ),
            affected_rows=tuple(mismatches[:50]),
        ))

    # QG-11 dataset coverage gaps -------------------------------------------
    if not valid_ts:
        findings.append(QualityGateFinding(
            gate=QualityGateID.COVERAGE_GAPS,
            passed=False,
            detail="no valid timestamps — coverage unmeasurable",
        ))
    else:
        problems: list[str] = []
        actual_start = valid_ts[0].date().isoformat()
        actual_end = valid_ts[-1].date().isoformat()
        if actual_start != manifest.coverage_start:
            problems.append(
                f"actual first bar {actual_start} != declared "
                f"coverage_start {manifest.coverage_start}"
            )
        if actual_end != manifest.coverage_end:
            problems.append(
                f"actual last bar {actual_end} != declared "
                f"coverage_end {manifest.coverage_end}"
            )
        if manifest.row_count != n:
            problems.append(
                f"declared row_count {manifest.row_count} != inspected "
                f"{n}"
            )
        findings.append(QualityGateFinding(
            gate=QualityGateID.COVERAGE_GAPS,
            passed=not problems,
            detail=(
                f"coverage {actual_start}..{actual_end}, {n} rows — "
                "matches the manifest"
                if not problems
                else "; ".join(problems)
            ),
        ))

    # QG-12 corporate-action consistency -------------------------------------
    if manifest.corporate_action_treatment == "not-applicable-synthetic":
        findings.append(QualityGateFinding(
            gate=QualityGateID.CORPORATE_ACTION_CONSISTENCY,
            passed=True,
            detail="N/A — synthetic fixture (no corporate actions)",
        ))
    else:
        jump_rows: list[int] = []
        closes = [
            float(rows[i]["close"])
            for i in range(n)
            if rows[i].get("close") is not None and _finite(rows[i]["close"])
        ]
        idx_map = [
            i for i in range(n)
            if rows[i].get("close") is not None and _finite(rows[i]["close"])
        ]
        for j in range(1, len(closes)):
            if closes[j - 1] > 0:
                ratio = closes[j] / closes[j - 1]
                if ratio >= 2.0 or ratio <= 0.5:
                    jump_rows.append(idx_map[j])
        findings.append(QualityGateFinding(
            gate=QualityGateID.CORPORATE_ACTION_CONSISTENCY,
            passed=not jump_rows,
            detail=(
                f"adjustment policy {manifest.adjustment_policy!r}: no "
                "unadjusted split-like price jumps (>=2x / <=0.5x)"
                if not jump_rows
                else f"{len(jump_rows)} split-like jumps under declared "
                     f"treatment {manifest.corporate_action_treatment!r} "
                     f"— possible unadjusted corporate action (first at "
                     f"row {jump_rows[0]})"
            ),
            affected_rows=tuple(jump_rows[:50]),
        ))

    # QG-15 dataset checksum mismatch ----------------------------------------
    recomputed = dataset_content_hash(
        [dict(row) for row in rows]
    )
    checksum_ok = recomputed == manifest.content_checksum
    findings.append(QualityGateFinding(
        gate=QualityGateID.DATASET_CHECKSUM,
        passed=checksum_ok,
        detail=(
            "content checksum matches the manifest"
            if checksum_ok
            else f"content checksum mismatch: manifest declares "
                 f"{manifest.content_checksum!r}, rows hash to "
                 f"{recomputed!r}"
        ),
    ))

    # QG-16 provenance incompleteness ----------------------------------------
    provenance_ok = manifest.provenance_complete
    findings.append(QualityGateFinding(
        gate=QualityGateID.PROVENANCE_COMPLETENESS,
        passed=provenance_ok,
        detail=(
            "all mandatory provenance fields present"
            if provenance_ok
            else "manifest carries placeholder/empty provenance fields"
        ),
    ))

    return DataQualityReport(
        dataset_manifest_hash=manifest.manifest_hash,
        findings=tuple(findings),
        rows_inspected=n,
    )


__all__ = [
    "QualityGateID",
    "QualityGateFinding",
    "DataQualityReport",
    "validate_ohlcv",
    "QUALITY_REFUSAL_INVALID",
    "QUALITY_REFUSAL_INSUFFICIENT",
]
