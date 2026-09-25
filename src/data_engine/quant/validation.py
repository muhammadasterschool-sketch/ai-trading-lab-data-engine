"""Data validation at the Quant Engine boundary.

Before calculating any indicator, the input dataset must be validated
against all integrity requirements. This module enforces:
- Non-empty dataset
- Sorted timestamps
- No duplicate timestamps
- Finite prices
- Positive prices
- Valid OHLC relationships
- Timeframe consistency
- Sufficient observations
- Valid provenance
- Valid DataQualityGate status
"""

from typing import Optional, List
from datetime import datetime, UTC
from pydantic import BaseModel, Field
from data_engine.schemas import Dataset, Candle, Timeframe, ValidationStatus, EvidenceProvenance
from data_engine.data_blocked import DataQualityGate, DATA_QUALITY_BLOCKED, DataQualityBlockedError
from data_engine.timeframes import validate_timeframe_integrity, get_bars_per_day
import math


class QuantBoundaryError(Exception):
    """Raised when a dataset fails quant boundary validation."""
    pass


class QuantValidationResult(BaseModel):
    """Result of quant boundary validation."""
    valid: bool
    errors: List[str]
    warnings: List[str]


class QuantDataValidator:
    """Validates datasets before quant calculations.

    Every indicator calculation must pass through this validator.
    """

    def __init__(self, require_gate_pass: bool = True):
        self.require_gate_pass = require_gate_pass
        self._errors: List[str] = []
        self._warnings: List[str] = []

    def validate(
        self,
        dataset: Dataset,
        min_observations: int = 1,
        require_known_provenance: bool = True,
    ) -> QuantValidationResult:
        """Validate a dataset for quant calculation.

        Returns QuantValidationResult. Raises QuantBoundaryError
        if validation fails critically.
        """
        self._errors = []
        self._warnings = []

        # 1. Non-empty dataset
        if len(dataset.candles) == 0:
            self._errors.append("Dataset contains 0 candles. Cannot calculate indicators.")
            return self._result()

        # 2. Sufficient observations
        if len(dataset.candles) < min_observations:
            self._errors.append(
                f"Insufficient observations: {len(dataset.candles)} < {min_observations}. "
                f"Cannot calculate indicators requiring {min_observations} bars."
            )
            return self._result()

        # 3. Timeframe consistency
        timeframe = dataset.provenance.timeframe
        issues = validate_timeframe_integrity(dataset.candles, timeframe)
        if issues:
            for issue in issues:
                self._errors.append(f"Timeframe integrity violation: {issue}")

        # 4. Sorted timestamps
        self._check_sorted_timestamps(dataset)

        # 5. Duplicate timestamps
        self._check_duplicate_timestamps(dataset)

        # 6. Finite and positive prices
        self._check_price_integrity(dataset)

        # 7. Valid OHLC relationships
        self._check_ohlc_relationships(dataset)

        # 8. Provenance validation
        if require_known_provenance:
            self._check_provenance(dataset)

        # 9. DataQualityGate check
        if self.require_gate_pass:
            self._check_quality_gate(dataset)

        return self._result()

    def _check_sorted_timestamps(self, dataset: Dataset):
        """Verify timestamps are sorted ascending."""
        for i in range(1, len(dataset.candles)):
            if dataset.candles[i].timestamp < dataset.candles[i-1].timestamp:
                self._warnings.append(
                    f"Candle {i}: timestamp out of order. "
                    f"{dataset.candles[i].timestamp} < {dataset.candles[i-1].timestamp}"
                )

    def _check_duplicate_timestamps(self, dataset: Dataset):
        """Verify no duplicate timestamps exist."""
        seen = set()
        for i, candle in enumerate(dataset.candles):
            key = (candle.timestamp.isoformat(), candle.timeframe.value)
            if key in seen:
                self._errors.append(f"Duplicate timestamp at candle {i}: {key}")
            seen.add(key)

    def _check_price_integrity(self, dataset: Dataset):
        """Verify all prices are finite and positive."""
        for i, candle in enumerate(dataset.candles):
            for field in ["open", "high", "low", "close"]:
                val = getattr(candle, field)
                if math.isnan(val) or math.isinf(val):
                    self._errors.append(
                        f"Candle {i}: {field} = {val} (NaN/Inf detected)"
                    )
                elif val <= 0:
                    self._errors.append(
                        f"Candle {i}: {field} = {val} (must be positive)"
                    )
            if candle.volume is not None and (math.isnan(candle.volume) or math.isinf(candle.volume)):
                self._errors.append(f"Candle {i}: volume is NaN/Inf")

    def _check_ohlc_relationships(self, dataset: Dataset):
        """Verify OHLC relationships are valid."""
        for i, candle in enumerate(dataset.candles):
            if candle.high < candle.low:
                self._errors.append(f"Candle {i}: high < low")
            if candle.high < max(candle.open, candle.close):
                self._errors.append(f"Candle {i}: high < max(open, close)")
            if candle.low > min(candle.open, candle.close):
                self._errors.append(f"Candle {i}: low > min(open, close)")

    def _check_provenance(self, dataset: Dataset):
        """Verify dataset provenance is valid for quant use."""
        prov = dataset.provenance
        if prov.evidence_provenance == EvidenceProvenance.UNKNOWN:
            self._warnings.append(
                f"Dataset {dataset.dataset_id}: UNKNOWN provenance. "
                f"Cannot be treated as strong research evidence."
            )
        if prov.evidence_provenance == EvidenceProvenance.SYNTHETIC:
            self._errors.append(
                f"Dataset {dataset.dataset_id}: SYNTHETIC provenance. "
                f"Blocked from quant calculations."
            )
        if prov.evidence_provenance == EvidenceProvenance.SIMULATED:
            self._errors.append(
                f"Dataset {dataset.dataset_id}: SIMULATED provenance. "
                f"Blocked from quant calculations."
            )

    def _check_quality_gate(self, dataset: Dataset):
        """Verify dataset passes DataQualityGate."""
        gate = DataQualityGate()
        passed, error = gate.check(
            dataset,
            require_known_provenance=True,
            require_valid_validation=True,
        )
        if not passed and error:
            self._errors.append(
                f"DataQualityGate blocked dataset {dataset.dataset_id}: {error.failure_reason}"
            )

    def _result(self) -> QuantValidationResult:
        return QuantValidationResult(
            valid=len(self._errors) == 0,
            errors=self._errors.copy(),
            warnings=self._warnings.copy(),
        )

    def assert_valid(self, dataset: Dataset, min_observations: int = 1):
        """Assert dataset is valid, raising QuantBoundaryError if not."""
        validation = self.validate(dataset, min_observations=min_observations)
        if not validation.valid:
            error_msg = "; ".join(validation.errors)
            raise QuantBoundaryError(f"Quant boundary validation failed: {error_msg}")
        return validation