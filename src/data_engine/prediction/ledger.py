"""Prediction outcome ledger (§36) — append-only, hash-chained.

Every forecast is stored with its eventual outcome: forecast, actual,
error, horizon, regime, model version, confidence, evidence score,
calibration, outcome timestamp. The chain hash makes tampering evident:
each entry's hash covers its content AND the previous entry's hash.

The ledger answers one question honestly: is the system actually
improving? (§36). There is NO mutation or deletion API — the only way
to change history is to tamper, and tampering breaks verification.
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import LEDGER_PREFIX, prefixed_hash

GENESIS_HASH = "0" * 64


class OutcomeRecord(BaseModel):
    """One forecast/actual pair with full context (§36)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: str
    model_id: str
    model_version: str
    forecast: float
    actual: Optional[bool]
    horizon_bars: int
    regime: str
    confidence: str
    evidence_score: Optional[float]
    calibration_version: str
    outcome_timestamp: str

    @field_validator("forecast")
    @classmethod
    def _validate_forecast(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("forecast probability must be in [0, 1]")
        return v

    @field_validator("horizon_bars")
    @classmethod
    def _validate_horizon(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("horizon_bars must be a positive int")
        return v

    @property
    def outcome_known(self) -> bool:
        return self.actual is not None

    @property
    def error(self) -> Optional[float]:
        """Signed forecast error; None while the outcome is unknown."""
        if self.actual is None:
            return None
        return self.forecast - (1.0 if self.actual else 0.0)


class LedgerEntry(BaseModel):
    """One immutable ledger entry: record + chain position + hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record: OutcomeRecord
    index: int
    prev_record_hash: str
    record_hash: str

    @field_validator("index")
    @classmethod
    def _validate_index(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("ledger index must be a non-negative int")
        return v


class LedgerSummary(BaseModel):
    """Aggregate learning verdict over known outcomes (§36)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_records: int
    n_known_outcomes: int
    brier: Optional[float]
    mean_error: Optional[float]
    hit_rate: Optional[float]


def _entry_hash(record: OutcomeRecord, index: int, prev_hash: str) -> str:
    return prefixed_hash(
        LEDGER_PREFIX,
        {
            "kind": "outcome_ledger_entry",
            "index": index,
            "prev_record_hash": prev_hash,
            "prediction_id": record.prediction_id,
            "model_id": record.model_id,
            "model_version": record.model_version,
            "forecast": record.forecast,
            "actual": record.actual,
            "horizon_bars": record.horizon_bars,
            "regime": record.regime,
            "confidence": record.confidence,
            "evidence_score": record.evidence_score,
            "calibration_version": record.calibration_version,
            "outcome_timestamp": record.outcome_timestamp,
        },
    )


class PredictionOutcomeLedger:
    """Append-only outcome ledger with a tamper-evident hash chain."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._chain: list[str] = [GENESIS_HASH]

    def append(self, record: OutcomeRecord) -> int:
        """Append one outcome record; returns its ledger index."""
        prev_hash = self._chain[-1]
        index = len(self._entries)
        entry_hash = _entry_hash(record, index, prev_hash)
        entry = LedgerEntry(
            record=record,
            index=index,
            prev_record_hash=prev_hash,
            record_hash=entry_hash,
        )
        self._entries.append(entry)
        self._chain.append(entry_hash)
        return index

    @property
    def entries(self) -> Tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    def verify(self) -> bool:
        """Recompute the full chain; False on ANY tamper (T-PRED-019)."""
        prev = GENESIS_HASH
        for position, entry in enumerate(self._entries):
            if entry.index != position:
                return False
            if entry.prev_record_hash != prev:
                return False
            if entry.record_hash != _entry_hash(entry.record, position, prev):
                return False
            prev = entry.record_hash
        return True

    def summary(self) -> LedgerSummary:
        """Brier / mean error / hit rate over known outcomes (§36)."""
        known = [
            e.record for e in self._entries if e.record.outcome_known
        ]
        n_known = len(known)
        if n_known == 0:
            return LedgerSummary(
                n_records=len(self._entries),
                n_known_outcomes=0,
                brier=None,
                mean_error=None,
                hit_rate=None,
            )
        brier = math.fsum(
            (r.forecast - (1.0 if r.actual else 0.0)) ** 2 for r in known
        ) / n_known
        mean_error = math.fsum(r.error or 0.0 for r in known) / n_known
        hits = sum(
            1
            for r in known
            if (r.forecast >= 0.5) == bool(r.actual)
        )
        return LedgerSummary(
            n_records=len(self._entries),
            n_known_outcomes=n_known,
            brier=brier,
            mean_error=mean_error,
            hit_rate=hits / n_known,
        )


__all__ = [
    "GENESIS_HASH",
    "OutcomeRecord",
    "LedgerEntry",
    "LedgerSummary",
    "PredictionOutcomeLedger",
]
