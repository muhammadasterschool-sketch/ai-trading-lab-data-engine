"""Real-data readiness contract + hard data-quality gates
(pre-paper mandate §9/§10).

Real-data readiness (mandate §9): the pipeline contract is

    DATA SOURCE → INGESTION → VALIDATION → NORMALIZATION →
    TIMESTAMP VALIDATION → SYMBOL VALIDATION → CORPORATE ACTION
    POLICY → MISSING DATA POLICY → DUPLICATE POLICY → PIT
    VALIDATION → PROVENANCE → DATASET MANIFEST → REPLAYABILITY

Each registered dataset must carry ALL mandated fields. Synthetic
data can NEVER be promoted to REAL_VERIFIED (Phase 4A.1 dataset
governance). With zero verified real datasets in this repository
the gate is BLOCKED — honestly, not invented around (mandate §9:
"do not invent it... mark the gate BLOCKED until real data is
supplied").

Data quality (mandate §10): hard, explainable rejections for
missing/duplicate/non-monotonic timestamps, impossible OHLC
relationships, invalid prices, negative volume, NaN/inf, stale
records, gaps, and timezone inconsistencies.
"""

import math
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import (
    DATASET_READINESS_PREFIX,
    prefixed_hash,
)


class DataGateError(RuntimeContractError):
    """Raised on data-readiness contract violations."""


class DatasetReadinessRecord(BaseModel):
    """One dataset's full readiness record (mandate §9 field list)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_id: str
    source: str
    acquisition_timestamp: datetime
    market: str
    symbols: tuple
    timeframe: str
    coverage_start: datetime
    coverage_end: datetime
    timezone: str
    adjustment_state: str  # RAW / SPLIT_ADJUSTED / TOTAL_RETURN ...
    missing_data_statistics: Mapping[str, float]
    duplicate_statistics: Mapping[str, float]
    quality_status: str  # PENDING / PASSED / FAILED
    pit_status: str  # NOT_VERIFIED / VERIFIED / FAILED
    provenance: Mapping[str, str]
    content_hash: str
    epistemic_state: str  # SYNTHETIC / REAL_UNVERIFIED / REAL_VERIFIED / ...

    @field_validator("dataset_id", "source", "market", "timeframe",
                     "timezone", "adjustment_state", "quality_status",
                     "pit_status", "epistemic_state")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise DataGateError("dataset record text fields must be non-empty")
        return v.strip()

    @field_validator("symbols")
    @classmethod
    def _validate_symbols(cls, v) -> tuple:
        if not v:
            raise DataGateError("dataset must declare its symbols")
        return tuple(v)

    @field_validator("content_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise DataGateError("dataset content hash is mandatory")
        return v.strip()

    @field_validator("acquisition_timestamp", "coverage_start", "coverage_end")
    @classmethod
    def _validate_times(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise DataGateError("dataset timestamps must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_coverage(self) -> "DatasetReadinessRecord":
        if self.coverage_end <= self.coverage_start:
            raise DataGateError("coverage_end must be after coverage_start")
        if self.epistemic_state == "REAL_VERIFIED" and (
            self.quality_status != "PASSED" or self.pit_status != "VERIFIED"
        ):
            raise DataGateError(
                "REAL_VERIFIED requires quality PASSED and PIT VERIFIED — "
                "synthetic/unverified data can never be promoted"
            )
        return self

    @property
    def record_id(self) -> str:
        return prefixed_hash(
            DATASET_READINESS_PREFIX,
            {
                "kind": "dataset_readiness",
                "dataset_id": self.dataset_id,
                "source": self.source,
                "content_hash": self.content_hash,
                "epistemic_state": self.epistemic_state,
            },
        )


class DataReadinessReport(BaseModel):
    """Verdict over all registered datasets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    datasets_registered: int
    verified_real_datasets: int
    synthetic_datasets: int
    unverified_real_datasets: int
    gate: str  # READY / BLOCKED_ON_REAL_DATA
    reasons: tuple


class RealDataReadiness:
    """The real-data gate (mandate §9). Registers datasets, verifies
    states, and reports the honest gate verdict."""

    def __init__(self) -> None:
        self._datasets: dict = {}

    def register(self, record: DatasetReadinessRecord) -> str:
        if record.dataset_id in self._datasets:
            raise DataGateError(
                f"duplicate dataset registration {record.dataset_id!r}"
            )
        self._datasets[record.dataset_id] = record
        return record.record_id

    def report(self) -> DataReadinessReport:
        records = list(self._datasets.values())
        verified = [r for r in records if r.epistemic_state == "REAL_VERIFIED"]
        synthetic = [r for r in records if r.epistemic_state == "SYNTHETIC"]
        unverified = [
            r for r in records if r.epistemic_state == "REAL_UNVERIFIED"
        ]
        reasons = []
        if not verified:
            reasons.append(
                "no REAL_VERIFIED dataset exists in this repository — "
                "the gate is BLOCKED until real data is supplied and "
                "verified (mandate §9: never invented)"
            )
        for r in unverified:
            reasons.append(
                f"dataset {r.dataset_id} is REAL_UNVERIFIED (quality="
                f"{r.quality_status}, pit={r.pit_status})"
            )
        return DataReadinessReport(
            datasets_registered=len(records),
            verified_real_datasets=len(verified),
            synthetic_datasets=len(synthetic),
            unverified_real_datasets=len(unverified),
            gate="READY" if verified else "BLOCKED_ON_REAL_DATA",
            reasons=tuple(reasons),
        )

    @property
    def datasets(self) -> tuple:
        return tuple(self._datasets.values())


# ---------------------------------------------------------------------------
# Hard data-quality gates (mandate §10)
# ---------------------------------------------------------------------------

QUALITY_CHECKS = (
    "timestamp_present",
    "timestamp_timezone",
    "timestamp_monotonic",
    "timestamp_duplicates",
    "ohlc_relationship",
    "price_finite_positive",
    "volume_valid",
    "stale_record",
    "gap_detection",
)


class QualityRejection(BaseModel):
    """One rejected record with its explainable reason (§10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_index: int
    check: str
    reason: str


def validate_bars(
    bars: Sequence[Mapping],
    expected_interval: Optional[timedelta] = None,
    staleness_limit: Optional[timedelta] = None,
    now: Optional[datetime] = None,
) -> tuple:
    """Hard quality gates over a bar series (mandate §10).

    Returns ``(accepted, rejections)`` where every rejection carries
    bar index + check + explainable reason. Fail-closed philosophy:
    an unverifiable property (e.g. staleness without ``now``) is
    simply not asserted, but every asserted property is HARD.
    """
    rejections: list = []
    previous_ts: Optional[datetime] = None
    for i, bar in enumerate(bars):
        ts = bar.get("timestamp")
        if ts is None:
            rejections.append(QualityRejection(
                bar_index=i, check="timestamp_present",
                reason="bar has no timestamp"))
            continue
        if getattr(ts, "tzinfo", None) is None:
            rejections.append(QualityRejection(
                bar_index=i, check="timestamp_timezone",
                reason="timestamp is not timezone-aware (naive datetime)"))
            continue
        ts = ts.astimezone(UTC)
        if previous_ts is not None:
            if ts == previous_ts:
                rejections.append(QualityRejection(
                    bar_index=i, check="timestamp_duplicates",
                    reason=f"timestamp {ts.isoformat()} duplicates bar "
                           f"{i - 1}"))
                continue
            if ts < previous_ts:
                rejections.append(QualityRejection(
                    bar_index=i, check="timestamp_monotonic",
                    reason=f"timestamp {ts.isoformat()} regresses before "
                           f"bar {i - 1}"))
                continue
            if expected_interval is not None:
                gap = ts - previous_ts
                if gap > expected_interval * 1.5:
                    rejections.append(QualityRejection(
                        bar_index=i, check="gap_detection",
                        reason=f"gap of {gap} exceeds expected interval "
                               f"{expected_interval} (missing bars)"))
        if staleness_limit is not None and now is not None:
            age = now - ts
            if age > staleness_limit:
                rejections.append(QualityRejection(
                    bar_index=i, check="stale_record",
                    reason=f"record age {age} exceeds staleness limit "
                           f"{staleness_limit}"))
        previous_ts = ts

        o = bar.get("open"); h = bar.get("high")
        low = bar.get("low"); c = bar.get("close"); v = bar.get("volume")
        numeric = []
        for name, value in (("open", o), ("high", h), ("low", low),
                            ("close", c)):
            if value is None:
                rejections.append(QualityRejection(
                    bar_index=i, check="price_finite_positive",
                    reason=f"missing {name} price"))
                numeric = []
                break
            f = float(value)
            numeric.append(f)
            if not math.isfinite(f):
                rejections.append(QualityRejection(
                    bar_index=i, check="price_finite_positive",
                    reason=f"{name} is not finite (NaN/inf)"))
                numeric = []
                break
            if f <= 0:
                rejections.append(QualityRejection(
                    bar_index=i, check="price_finite_positive",
                    reason=f"{name} price {f} is not positive"))
                numeric = []
                break
        if numeric:
            fo, fh, fl, fc = numeric
            if fh < max(fo, fc) or fl > min(fo, fc):
                rejections.append(QualityRejection(
                    bar_index=i, check="ohlc_relationship",
                    reason=f"impossible OHLC: high={fh} low={fl} for "
                           f"open={fo} close={fc}"))
        if v is not None:
            fv = float(v)
            if not math.isfinite(fv) or fv < 0:
                rejections.append(QualityRejection(
                    bar_index=i, check="volume_valid",
                    reason=f"volume {fv} is negative or non-finite"))
    accepted = len(bars) - len(rejections)
    return accepted, tuple(rejections)


__all__ = [
    "DataGateError",
    "DatasetReadinessRecord",
    "DataReadinessReport",
    "RealDataReadiness",
    "QUALITY_CHECKS",
    "QualityRejection",
    "validate_bars",
]
