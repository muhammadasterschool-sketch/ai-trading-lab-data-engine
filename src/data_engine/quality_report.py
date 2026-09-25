"""Data quality reporting for the AI Trading Lab Data Engine.

Produces automated, reproducible data-quality reports.
"""

from datetime import datetime, UTC
from typing import Optional, List, Dict
from pydantic import BaseModel, Field
from data_engine.schemas import (
    Dataset, Candle, ValidationResult, ValidationStatus, Timeframe,
    EvidenceProvenance
)
from data_engine.validation import DataValidator


class DataQualityReport(BaseModel):
    """Automated data quality report."""
    dataset_id: str
    provider: str
    instrument: str
    timeframe: str
    start_timestamp: str
    end_timestamp: str
    total_rows: int
    expected_rows: Optional[int] = None
    missing_periods: int = 0
    duplicate_count: int = 0
    invalid_candle_count: int = 0
    out_of_order_count: int = 0
    timezone_issues: int = 0
    abnormal_gaps: int = 0
    nan_count: int = 0
    infinity_count: int = 0
    unavailable_fields: Dict[str, int] = Field(default_factory=dict)
    validation_status: str = "UNKNOWN"
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    dataset_version: str = "1.0.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def is_usable(self) -> bool:
        return self.validation_status == "VALID" and self.invalid_candle_count == 0

    @property
    def is_blocked(self) -> bool:
        return self.validation_status in ("INVALID", "QUARANTINED")

    @property
    def health_score(self) -> float:
        """Return a 0-100 health score based on validation results."""
        if self.total_rows == 0:
            return 0.0
        score = 100.0
        score -= self.invalid_candle_count * 10
        score -= self.duplicate_count * 5
        score -= self.out_of_order_count * 3
        score -= self.abnormal_gaps * 2
        score = max(score, 0)
        return score

    @classmethod
    def from_dataset_and_results(
        cls,
        dataset: Dataset,
        validation_results: List[ValidationResult],
    ) -> "DataQualityReport":
        """Build a report from a dataset and its validation results."""
        # Count issues
        invalid = sum(1 for r in validation_results if r.status == ValidationStatus.INVALID)
        warnings = sum(1 for r in validation_results if r.status == ValidationStatus.WARNING)
        quarantined = sum(1 for r in validation_results if r.status == ValidationStatus.QUARANTINED)
        out_of_order = sum(1 for r in validation_results if r.rule == "timestamp_ordering")
        duplicates = sum(1 for r in validation_results if r.rule == "duplicate_candle")

        # Detect NaN/Infinity
        import math
        nan_count = sum(1 for c in dataset.candles if any(
            math.isnan(getattr(c, f)) for f in ["open", "high", "low", "close"] if getattr(c, f) is not None
        ))
        infinity_count = sum(1 for c in dataset.candles if any(
            math.isinf(getattr(c, f)) for f in ["open", "high", "low", "close"] if getattr(c, f) is not None
        ))

        # Detect unavailable fields
        unavailable_fields = {}
        for i, candle in enumerate(dataset.candles[:100]):  # Sample first 100
            if candle.bid is None:
                unavailable_fields["bid"] = unavailable_fields.get("bid", 0) + 1
            if candle.ask is None:
                unavailable_fields["ask"] = unavailable_fields.get("ask", 0) + 1
            if candle.spread is None:
                unavailable_fields["spread"] = unavailable_fields.get("spread", 0) + 1
            if candle.volume is None:
                unavailable_fields["volume"] = unavailable_fields.get("volume", 0) + 1

        # Determine overall status
        if invalid > 0 or quarantined > 0:
            status = "QUARANTINED"
        elif warnings > 0:
            status = "WARNING"
        else:
            status = "VALID"

        # Detect abnormal gaps
        abnormal_gaps = sum(1 for r in validation_results if r.rule == "candle_continuity")

        # Build warning/error lists
        warning_list = [r.message for r in validation_results if r.status == ValidationStatus.WARNING]
        error_list = [r.message for r in validation_results if r.status in (ValidationStatus.INVALID, ValidationStatus.QUARANTINED)]

        return cls(
            dataset_id=dataset.dataset_id,
            provider=dataset.provenance.provider,
            instrument=dataset.provenance.instrument.symbol,
            timeframe=dataset.provenance.timeframe.value,
            start_timestamp=dataset.provenance.start_timestamp.isoformat(),
            end_timestamp=dataset.provenance.end_timestamp.isoformat(),
            total_rows=len(dataset.candles),
            expected_rows=dataset.expected_rows,
            missing_periods=abnormal_gaps,
            duplicate_count=duplicates,
            invalid_candle_count=invalid,
            out_of_order_count=out_of_order,
            timezone_issues=0,  # Would be detected by timezone checks
            abnormal_gaps=abnormal_gaps,
            nan_count=nan_count,
            infinity_count=infinity_count,
            unavailable_fields=unavailable_fields,
            validation_status=status,
            warnings=warning_list[:10],
            errors=error_list[:10],
            dataset_version=dataset.provenance.dataset_version,
        )

    def to_string(self) -> str:
        """Return a human-readable report."""
        lines = [
            f"=== Data Quality Report ===",
            f"Dataset ID: {self.dataset_id}",
            f"Provider: {self.provider}",
            f"Instrument: {self.instrument}",
            f"Timeframe: {self.timeframe}",
            f"Period: {self.start_timestamp} → {self.end_timestamp}",
            f"Total Rows: {self.total_rows}",
            f"Validation Status: {self.validation_status}",
            f"Health Score: {self.health_score:.1f}/100",
            f"",
            f"Issues:",
            f"  Invalid Candles: {self.invalid_candle_count}",
            f"  Duplicates: {self.duplicate_count}",
            f"  Out-of-Order: {self.out_of_order_count}",
            f"  Abnormal Gaps: {self.abnormal_gaps}",
            f"  NaN Count: {self.nan_count}",
            f"  Infinity Count: {self.infinity_count}",
            f"  Unavailable Fields: {self.unavailable_fields}",
        ]
        if self.warnings:
            lines.append(f"\nWarnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        if self.errors:
            lines.append(f"\nErrors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        lines.append(f"\nUsable: {self.is_usable}")
        lines.append(f"Blocked: {self.is_blocked}")
        return "\n".join(lines)
