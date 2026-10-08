"""Phase 5 — Experiment registry and reproducibility logs (blueprint 5.16).

Tracks every experiment by its deterministic identity (the 4A.1
``ExperimentIdentity``) with complete reproducibility provenance:

- ``ExperimentRegistryEntry``: registered experiment (identity hash +
  config hash + registration metadata). Duplicate identity rejection —
  two registrations of the SAME deterministic experiment are the same
  experiment, not two.
- ``ExperimentRegistry``: append-only registry with tamper-evident
  reads (stored identity hash recomputed on every access) and full
  lifecycle status.
- ``ReproducibilityLog``: ordered verification runs — each records the
  environment pin (code/quant/backtest versions), input hashes, output
  hash, and a deterministic verification verdict. Identity: ``rlog5.``.

Invariants (blueprint 5.16):
- Every experiment has a unique deterministic ID.
- The reproducibility log is COMPLETE: a registered experiment without
  a log is flagged ``unverified`` — never silently assumed
  reproducible.
- Experiment tampering breaks the stored hash -> fail closed on read.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.immutable import freeze

#: Identity prefix for experiment-registry entry hashes.
EXPERIMENT_REGISTRY_PREFIX = "expr5."

#: Identity prefix for reproducibility log hashes.
REPRODUCIBILITY_PREFIX = "rlog5."

#: Phase 5 component contract version.
PHASE_5_CONTRACT_VERSION = "1.0.0"


class VerificationStatus(str, Enum):
    """Outcome of one reproducibility verification run."""

    MATCH = "match"          # output hash identical to the registered run
    MISMATCH = "mismatch"    # output hash differs (reproducibility failure)
    UNVERIFIED = "unverified"  # no verification run recorded yet


class ExperimentRegistryEntry(BaseModel):
    """One registered experiment, keyed by its deterministic identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_hash: str  # the 4A.1 pit4x. ExperimentIdentity hash
    experiment_id: str
    config_hash: str
    registered_by: str
    registered_at: datetime
    description: Optional[str] = None

    @field_validator("experiment_hash", "config_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("hashes must be non-empty strings")
        return v

    @field_validator("experiment_id", "registered_by")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("identifiers must be non-empty strings")
        return v.strip()

    @field_validator("registered_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("registered_at must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def entry_hash(self) -> str:
        payload = {
            "contract_version": PHASE_5_CONTRACT_VERSION,
            "experiment_hash": self.experiment_hash,
            "experiment_id": self.experiment_id,
            "config_hash": self.config_hash,
            "registered_by": self.registered_by,
            "registered_at": self.registered_at,
            "description": self.description,
        }
        return EXPERIMENT_REGISTRY_PREFIX + deterministic_hash(payload)


class ReproducibilityRun(BaseModel):
    """One verification run: same inputs -> observed output hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_label: str
    environment_pin: dict  # code/quant/backtest engine versions
    input_hash: str
    observed_output_hash: str
    expected_output_hash: str
    run_at: datetime

    @field_validator("environment_pin")
    @classmethod
    def _freeze_environment_pin(cls, v: dict) -> dict:
        # BUG-008: deep-immutable record containers — the environment
        # pin participates in reproducibility identity.
        return freeze(v) if v is not None else v

    @field_validator("run_label")
    @classmethod
    def _validate_label(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("run_label must be a non-empty string")
        return v.strip()

    @field_validator("run_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("run_at must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def verdict(self) -> VerificationStatus:
        if self.observed_output_hash == self.expected_output_hash:
            return VerificationStatus.MATCH
        return VerificationStatus.MISMATCH


class ReproducibilityLog(BaseModel):
    """Complete reproducibility trail for one experiment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_hash: str
    runs: tuple[ReproducibilityRun, ...] = ()

    @field_validator("experiment_hash")
    @classmethod
    def _validate_hash(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("experiment_hash must be non-empty")
        return v

    @property
    def log_hash(self) -> str:
        """Deterministic log identity: ``rlog5.`` + SHA-256 hex."""
        payload = {
            "contract_version": PHASE_5_CONTRACT_VERSION,
            "experiment_hash": self.experiment_hash,
            "runs": [
                {
                    "run_label": r.run_label,
                    "environment_pin": r.environment_pin,
                    "input_hash": r.input_hash,
                    "observed_output_hash": r.observed_output_hash,
                    "expected_output_hash": r.expected_output_hash,
                    "run_at": r.run_at,
                }
                for r in self.runs
            ],
        }
        return REPRODUCIBILITY_PREFIX + deterministic_hash(payload)

    @property
    def status(self) -> VerificationStatus:
        """Aggregate status: latest run's verdict; UNVERIFIED if empty."""
        if not self.runs:
            return VerificationStatus.UNVERIFIED
        return self.runs[-1].verdict

    def extended(self, run: ReproducibilityRun) -> "ReproducibilityLog":
        """Return a NEW log with ``run`` appended (immutability)."""
        return ReproducibilityLog(
            experiment_hash=self.experiment_hash,
            runs=self.runs + (run,),
        )


class ExperimentRegistryError(ValueError):
    """Raised on registry integrity violations."""


class ExperimentRegistry:
    """Append-only experiment registry with reproducibility logs."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[ExperimentRegistryEntry, str]] = {}
        self._logs: dict[str, ReproducibilityLog] = {}

    def register(self, entry: ExperimentRegistryEntry) -> str:
        if entry.experiment_hash in self._entries:
            raise ExperimentRegistryError(
                "duplicate experiment identity: "
                f"{entry.experiment_hash} is already registered — the same "
                "deterministic experiment cannot register twice"
            )
        if entry.experiment_id in {
            e.experiment_id for e, _ in self._entries.values()
        }:
            raise ExperimentRegistryError(
                f"experiment_id {entry.experiment_id!r} already in use"
            )
        h = entry.entry_hash
        self._entries[entry.experiment_hash] = (entry, h)
        self._logs[entry.experiment_hash] = ReproducibilityLog(
            experiment_hash=entry.experiment_hash
        )
        return h

    def get(self, experiment_hash: str) -> ExperimentRegistryEntry:
        if experiment_hash not in self._entries:
            raise ExperimentRegistryError(
                f"experiment {experiment_hash} not registered"
            )
        entry, stored_hash = self._entries[experiment_hash]
        if entry.entry_hash != stored_hash:
            raise ExperimentRegistryError(
                "experiment tamper detected: stored hash no longer matches "
                f"entry {entry.experiment_id}"
            )
        return entry

    def attach_log(self, log: ReproducibilityLog) -> None:
        if log.experiment_hash not in self._entries:
            raise ExperimentRegistryError(
                "reproducibility log targets an unregistered experiment"
            )
        self._logs[log.experiment_hash] = log

    def reproducibility_status(
        self, experiment_hash: str
    ) -> VerificationStatus:
        self.get(experiment_hash)  # tamper check happens on read
        log = self._logs.get(experiment_hash)
        if log is None:
            return VerificationStatus.UNVERIFIED
        return log.status

    def entries_with_status(
        self, status: VerificationStatus
    ) -> list[str]:
        return [
            h
            for h in self._entries
            if self.reproducibility_status(h) is status
        ]

    def __len__(self) -> int:
        return len(self._entries)


__all__ = [
    "VerificationStatus",
    "ExperimentRegistryEntry",
    "ReproducibilityRun",
    "ReproducibilityLog",
    "ExperimentRegistry",
    "ExperimentRegistryError",
    "EXPERIMENT_REGISTRY_PREFIX",
    "REPRODUCIBILITY_PREFIX",
    "PHASE_5_CONTRACT_VERSION",
]
