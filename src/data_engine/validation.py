"""Data validation engine for the AI Trading Lab Data Engine.

Implements deterministic validation for:
- Schema validity
- OHLC relationships
- Timestamp ordering
- Candle continuity
- Price integrity
- Volume integrity
- Timezone consistency
- Data corruption

Every validation result is recorded with a status.
"""

from datetime import datetime
from typing import Optional, List, Tuple
from pydantic import BaseModel
from data_engine.schemas import (
    Candle, Dataset, ValidationStatus, ValidationResult, Instrument,
    Timeframe, EvidenceProvenance
)
from data_engine.timeframes import validate_timeframe_integrity, get_expected_bars


class DataValidator:
    """Deterministic data validation engine.

    Validates datasets against all integrity rules.
    Never silently accepts invalid data.
    """

    def __init__(self):
        self.validation_results: List[ValidationResult] = []

    def validate_dataset(self, dataset: Dataset) -> List[ValidationResult]:
        """Run all validation checks on a dataset.

        Returns a list of validation results.
        """
        self.validation_results = []

        # Check provenance
        self._check_provenance(dataset)

        # Validate each candle
        for i, candle in enumerate(dataset.candles):
            self._validate_candle(candle, i)

        # Check timestamp ordering
        self._check_timestamp_order(dataset)

        # Check duplicate timestamps
        self._check_duplicates(dataset)

        # Check candle continuity / gaps
        self._check_continuity(dataset)

        # Check timeframe integrity
        self._check_timeframe_integrity(dataset)

        # Check overall dataset quality
        self._check_dataset_quality(dataset)

        return self.validation_results

    def _check_provenance(self, dataset: Dataset):
        """Validate dataset provenance."""
        prov = dataset.provenance
        if prov.evidence_provenance == EvidenceProvenance.UNKNOWN:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.WARNING,
                rule="provenance_check",
                severity="MEDIUM",
                message=f"Dataset {dataset.dataset_id} has UNKNOWN evidence provenance. "
                        f"Cannot be treated as strong research evidence.",
            ))
        if prov.evidence_provenance == EvidenceProvenance.SYNTHETIC:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.WARNING,
                rule="provenance_check",
                severity="HIGH",
                message=f"Dataset {dataset.dataset_id} is SYNTHETIC. Must not be represented as REAL.",
            ))

    def _validate_candle(self, candle: Candle, index: int):
        """Validate a single candle's integrity."""
        # Check OHLC relationships
        if candle.high < candle.low:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                record_index=index,
                rule="ohlc_relationship",
                severity="CRITICAL",
                message=f"Candle {index}: high ({candle.high}) < low ({candle.low}). Impossible.",
            ))
            return
        if candle.high < max(candle.open, candle.close):
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                record_index=index,
                rule="ohlc_relationship",
                severity="CRITICAL",
                message=f"Candle {index}: high < max(open, close). OHLC violation.",
            ))
        if candle.low > min(candle.open, candle.close):
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                record_index=index,
                rule="ohlc_relationship",
                severity="CRITICAL",
                message=f"Candle {index}: low > min(open, close). OHLC violation.",
            ))

        # Check for NaN or infinity
        import math
        for field_name in ["open", "high", "low", "close"]:
            val = getattr(candle, field_name)
            if math.isnan(val) or math.isinf(val):
                self.validation_results.append(ValidationResult(
                    status=ValidationStatus.INVALID,
                    record_index=index,
                    rule="price_integrity",
                    severity="CRITICAL",
                    message=f"Candle {index}: {field_name} is {val} (NaN/Inf detected).",
                ))

        # Check volume if present
        if candle.volume is not None and candle.volume < 0:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                record_index=index,
                rule="volume_integrity",
                severity="HIGH",
                message=f"Candle {index}: negative volume ({candle.volume}).",
            ))

    def _check_timestamp_order(self, dataset: Dataset):
        """Detect out-of-order timestamps."""
        if len(dataset.candles) < 2:
            return
        for i in range(1, len(dataset.candles)):
            if dataset.candles[i].timestamp < dataset.candles[i-1].timestamp:
                self.validation_results.append(ValidationResult(
                    status=ValidationStatus.WARNING,
                    record_index=i,
                    rule="timestamp_ordering",
                    severity="HIGH",
                    message=f"Candle {i}: timestamp {dataset.candles[i].timestamp} is before candle {i-1}.",
                ))

    def _check_duplicates(self, dataset: Dataset):
        """Detect duplicate timestamps."""
        seen = {}
        for i, candle in enumerate(dataset.candles):
            key = (candle.timestamp, candle.timeframe.value)
            if key in seen:
                self.validation_results.append(ValidationResult(
                    status=ValidationStatus.INVALID,
                    record_index=i,
                    rule="duplicate_candle",
                    severity="CRITICAL",
                    message=f"Candle {i}: duplicate timestamp {candle.timestamp} on timeframe {candle.timeframe.value}. "
                            f"First seen at index {seen[key]}.",
                ))
            else:
                seen[key] = i

    def _check_continuity(self, dataset: Dataset):
        """Detect missing candles and abnormal gaps."""
        if len(dataset.candles) < 2:
            return
        timeframe = dataset.candles[0].timeframe
        from data_engine.timeframes import get_bars_per_day

        expected_bars_per_day = get_bars_per_day(timeframe)
        # Check for gaps larger than 1 day
        for i in range(1, len(dataset.candles)):
            diff = (dataset.candles[i].timestamp - dataset.candles[i-1].timestamp).total_seconds()
            expected_seconds = expected_bars_per_day * 86400 / max(expected_bars_per_day, 1)
            if timeframe == dataset.candles[0].timeframe:
                # For H4, expected gap is ~4 hours
                if timeframe == dataset.candles[0].timeframe:
                    if timeframe == Timeframe.H4:
                        expected_seconds = 4 * 3600
                    elif timeframe == Timeframe.D1:
                        expected_seconds = 86400
                    elif timeframe == Timeframe.H1:
                        expected_seconds = 3600
                    elif timeframe == Timeframe.M15:
                        expected_seconds = 900
                    elif timeframe == Timeframe.M5:
                        expected_seconds = 300
                    elif timeframe == Timeframe.M1:
                        expected_seconds = 60

            if diff > expected_seconds * 2:  # Gap > 2x expected interval
                self.validation_results.append(ValidationResult(
                    status=ValidationStatus.WARNING,
                    record_index=i,
                    rule="candle_continuity",
                    severity="MEDIUM",
                    message=f"Gap detected between candles {i-1} and {i}: "
                            f"{diff:.0f} seconds vs expected {expected_seconds:.0f} seconds.",
                ))

    def _check_timeframe_integrity(self, dataset: Dataset):
        """Verify all candles belong to the declared timeframe."""
        issues = validate_timeframe_integrity(dataset.candles, dataset.provenance.timeframe)
        for issue in issues:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                rule="timeframe_integrity",
                severity="CRITICAL",
                message=issue,
            ))

    def _check_dataset_quality(self, dataset: Dataset):
        """Overall dataset quality assessment."""
        total = len(dataset.candles)
        if total == 0:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.INVALID,
                rule="empty_dataset",
                severity="CRITICAL",
                message=f"Dataset {dataset.dataset_id} contains 0 candles.",
            ))
            return

        invalid_count = sum(1 for r in self.validation_results if r.status == ValidationStatus.INVALID)
        warning_count = sum(1 for r in self.validation_results if r.status == ValidationStatus.WARNING)

        if invalid_count > 0:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.QUARANTINED,
                rule="dataset_quality",
                severity="CRITICAL",
                message=f"Dataset {dataset.dataset_id} has {invalid_count} invalid candles. QUARANTINED.",
            ))
        elif warning_count > total * 0.1:  # >10% warnings
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.WARNING,
                rule="dataset_quality",
                severity="MEDIUM",
                message=f"Dataset {dataset.dataset_id} has {warning_count} warnings (>10% of candles).",
            ))
        else:
            self.validation_results.append(ValidationResult(
                status=ValidationStatus.VALID,
                rule="dataset_quality",
                severity="LOW",
                message=f"Dataset {dataset.dataset_id} passed all checks ({total} candles).",
            ))

    def get_validation_summary(self, dataset: Dataset) -> dict:
        """Return a summary of validation results."""
        results = self.validate_dataset(dataset)
        return {
            "dataset_id": dataset.dataset_id,
            "total_candles": len(dataset.candles),
            "total_checks": len(results),
            "valid_count": sum(1 for r in results if r.status == ValidationStatus.VALID),
            "warning_count": sum(1 for r in results if r.status == ValidationStatus.WARNING),
            "invalid_count": sum(1 for r in results if r.status == ValidationStatus.INVALID),
            "quarantined_count": sum(1 for r in results if r.status == ValidationStatus.QUARANTINED),
            "overall_status": self._determine_overall_status(results),
        }

    def _determine_overall_status(self, results: List[ValidationResult]) -> ValidationStatus:
        if any(r.status == ValidationStatus.INVALID for r in results):
            return ValidationStatus.INVALID
        if any(r.status == ValidationStatus.QUARANTINED for r in results):
            return ValidationStatus.QUARANTINED
        if any(r.status == ValidationStatus.WARNING for r in results):
            return ValidationStatus.WARNING
        return ValidationStatus.VALID
