"""Phase 10 — Reproducibility, observability, monitoring, recovery.

Blueprint domains 5.47-5.50:

- ``DeterministicRunner`` / ``ReproducibilityVerifier`` (5.47): run a
  callable N times, hash outputs, compare — hidden randomness and
  environment dependence surface as mismatches.
- ``MetricsRegistry`` / ``StructuredLog`` (5.48): deterministic
  counters/gauges with labels; append-only hash-chained log entries.
- ``HealthCheck`` / ``AlertManager`` (5.49): registered health checks
  with deterministic alert IDs and duplicate suppression.
- ``CheckpointManager`` / ``RecoveryManager`` (5.50): state snapshots
  with content hashes; restore verifies the hash before applying
  (checkpoint tampering fails closed).
"""

from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 10 contract version.
PHASE_10_CONTRACT_VERSION = "1.0.0"


# ======================================================================
# 5.47 Reproducibility
# ======================================================================

class ReproducibilityError(ValueError):
    """Raised on reproducibility failures (fail closed)."""


class ReproducibilityResult(BaseModel):
    """Outcome of a determinism verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: int
    distinct_output_hashes: int
    output_hashes: tuple[str, ...]
    reproducible: bool

    @field_validator("runs")
    @classmethod
    def _validate_runs(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("runs must be >= 1")
        return v

    @property
    def result_hash(self) -> str:
        return "rep10." + deterministic_hash(
            {
                "contract_version": PHASE_10_CONTRACT_VERSION,
                "runs": self.runs,
                "distinct_output_hashes": self.distinct_output_hashes,
                "output_hashes": list(self.output_hashes),
                "reproducible": self.reproducible,
            }
        )


class DeterministicRunner:
    """Runs a callable N times and hashes each output."""

    def __init__(self, runs: int = 3) -> None:
        if runs < 1:
            raise ReproducibilityError("runs must be >= 1")
        self._runs = runs

    def run(self, fn: Callable[[], Any]) -> ReproducibilityResult:
        """Execute ``fn`` N times; hash outputs deterministically."""
        hashes: list[str] = []
        for _ in range(self._runs):
            output = fn()
            hashes.append(deterministic_hash(_canonical(output)))
        distinct = len(set(hashes))
        return ReproducibilityResult(
            runs=self._runs,
            distinct_output_hashes=distinct,
            output_hashes=tuple(hashes),
            reproducible=distinct == 1,
        )


class ReproducibilityVerifier:
    """Verifies callables are reproducible (raises on failure)."""

    def __init__(self, runner: Optional[DeterministicRunner] = None) -> None:
        self._runner = runner or DeterministicRunner()

    def verify(self, fn: Callable[[], Any]) -> ReproducibilityResult:
        result = self._runner.run(fn)
        if not result.reproducible:
            raise ReproducibilityError(
                f"non-deterministic output across {result.runs} runs "
                f"({result.distinct_output_hashes} distinct hashes) — "
                "hidden randomness or environment dependence"
            )
        return result


def _canonical(value: Any) -> Any:
    """Canonicalize common containers for hashing."""
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float):
        return round(value, 12)
    return value


# ======================================================================
# 5.48 Observability
# ======================================================================

class MetricsRegistry:
    """Deterministic labeled metrics.

    Counters/gauges are pure maps of (name, sorted labels) -> value.
    Unregistered metric updates raise (a typo must never create a
    phantom series).
    """

    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    @staticmethod
    def _key(name: str, labels: Optional[Mapping[str, str]]) -> tuple:
        if not name or not isinstance(name, str):
            raise ValueError("metric name must be a non-empty string")
        label_pairs = tuple(sorted((labels or {}).items()))
        return (name, label_pairs)

    def register_counter(
        self, name: str, labels: Optional[Mapping[str, str]] = None
    ) -> None:
        key = self._key(name, labels)
        self._counters.setdefault(key, 0)

    def register_gauge(
        self, name: str, labels: Optional[Mapping[str, str]] = None
    ) -> None:
        key = self._key(name, labels)
        self._gauges.setdefault(key, 0.0)

    def increment(
        self, name: str, amount: int = 1, labels: Optional[Mapping[str, str]] = None
    ) -> int:
        key = self._key(name, labels)
        if key not in self._counters:
            raise ValueError(
                f"counter {name!r} not registered — phantom metrics are "
                "forbidden (register first)"
            )
        self._counters[key] += amount
        return self._counters[key]

    def set_gauge(
        self, name: str, value: float, labels: Optional[Mapping[str, str]] = None
    ) -> float:
        key = self._key(name, labels)
        if key not in self._gauges:
            raise ValueError(
                f"gauge {name!r} not registered — phantom metrics are "
                "forbidden (register first)"
            )
        self._gauges[key] = value
        return value

    def snapshot(self) -> dict:
        """Deterministic snapshot (sorted) with obs10. identity."""
        return {
            "counters": {
                f"{name}|{dict(labels)}": value
                for (name, labels), value in sorted(self._counters.items())
            },
            "gauges": {
                f"{name}|{dict(labels)}": value
                for (name, labels), value in sorted(self._gauges.items())
            },
        }

    @property
    def snapshot_hash(self) -> str:
        return "obs10." + deterministic_hash(
            {
                "contract_version": PHASE_10_CONTRACT_VERSION,
                "snapshot": self.snapshot(),
            }
        )


class LogEntry(BaseModel):
    """One structured log entry (hash-chained by StructuredLog)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: str
    message: str
    fields: dict
    entry_hash: str

    @field_validator("level", "message", "entry_hash")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("log fields must be non-empty strings")
        return v


class StructuredLog:
    """Append-only, hash-chained, immutable log."""

    def __init__(self) -> None:
        self._entries: list[LogEntry] = []

    def append(self, level: str, message: str, fields: Optional[dict] = None) -> LogEntry:
        prev = self._entries[-1].entry_hash if self._entries else "0" * 64
        entry_hash = deterministic_hash(
            {
                "contract_version": PHASE_10_CONTRACT_VERSION,
                "level": level,
                "message": message,
                "fields": _canonical(fields or {}),
                "prev_entry_hash": prev,
                "index": len(self._entries),
            }
        )
        entry = LogEntry(
            level=level, message=message,
            fields=fields or {}, entry_hash=entry_hash,
        )
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        prev = "0" * 64
        for index, entry in enumerate(self._entries):
            expected = deterministic_hash(
                {
                    "contract_version": PHASE_10_CONTRACT_VERSION,
                    "level": entry.level,
                    "message": entry.message,
                    "fields": _canonical(entry.fields),
                    "prev_entry_hash": prev,
                    "index": index,
                }
            )
            if expected != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[LogEntry, ...]:
        return tuple(self._entries)


# ======================================================================
# 5.49 Monitoring
# ======================================================================

class HealthStatus:
    """Health check outcome constants."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """One registered health check (callable returning a status)."""

    def __init__(self, check_id: str, fn: Callable[[], str]) -> None:
        if not check_id.strip():
            raise ValueError("check_id must be non-empty")
        if not callable(fn):
            raise ValueError("health check must be callable")
        self.check_id = check_id
        self._fn = fn

    def evaluate(self) -> str:
        result = self._fn()
        if result not in (
            HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY
        ):
            raise ValueError(
                f"health check {self.check_id!r} returned invalid status "
                f"{result!r}"
            )
        return result


class Alert:
    """One alert with a deterministic identity (duplicate suppression)."""

    def __init__(self, check_id: str, status: str) -> None:
        self.check_id = check_id
        self.status = status
        self.alert_id = "alert10." + deterministic_hash(
            {"check_id": check_id, "status": status}
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Alert) and other.alert_id == self.alert_id

    def __hash__(self) -> int:
        return hash(self.alert_id)


class AlertManager:
    """Deterministic alerting with duplicate suppression."""

    def __init__(self) -> None:
        self._active: dict[str, Alert] = {}

    def observe(self, check_id: str, status: str) -> Optional[Alert]:
        """Record a status observation; return the alert if it fires.

        An alert fires on UNHEALTHY/DEGRADED; duplicate consecutive
        statuses for the same check are suppressed (one active alert
        per check+status). A return to HEALTHY clears the alert.
        """
        if status == HealthStatus.HEALTHY:
            return self._clear(check_id)
        alert = Alert(check_id, status)
        if alert.alert_id in self._active:
            return None  # duplicate suppressed
        self._active[alert.alert_id] = alert
        return alert

    def _clear(self, check_id: str) -> Optional[Alert]:
        for alert_id, alert in list(self._active.items()):
            if alert.check_id == check_id:
                del self._active[alert_id]
                return alert
        return None

    @property
    def active_alerts(self) -> tuple[Alert, ...]:
        return tuple(self._active.values())

    def __len__(self) -> int:
        return len(self._active)


class Monitor:
    """Runs registered health checks and feeds the alert manager."""

    def __init__(self, alert_manager: Optional[AlertManager] = None) -> None:
        self.alert_manager = alert_manager or AlertManager()
        self._checks: dict[str, HealthCheck] = {}

    def register(self, check: HealthCheck) -> None:
        if check.check_id in self._checks:
            raise ValueError(f"duplicate health check {check.check_id!r}")
        self._checks[check.check_id] = check

    def poll(self) -> dict[str, str]:
        """Evaluate every check; route to alerts; return statuses."""
        statuses: dict[str, str] = {}
        for check_id in sorted(self._checks):
            status = self._checks[check_id].evaluate()
            statuses[check_id] = status
            self.alert_manager.observe(check_id, status)
        return statuses


# ======================================================================
# 5.50 Recovery
# ======================================================================

class Checkpoint(BaseModel):
    """One state snapshot with content hash."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    checkpoint_id: str
    state: dict
    state_hash: str

    @field_validator("checkpoint_id", "state_hash")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("checkpoint fields must be non-empty")
        return v


class CheckpointManager:
    """Snapshot state with content hashes; restore verifies."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    def save(self, checkpoint_id: str, state: Mapping[str, Any]) -> Checkpoint:
        if checkpoint_id in self._checkpoints:
            raise ValueError(
                f"checkpoint {checkpoint_id!r} already exists "
                "(checkpoints are immutable; use a new id)"
            )
        canonical = _canonical(dict(state))
        state_hash = deterministic_hash(canonical)
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            state=canonical,
            state_hash=state_hash,
        )
        self._checkpoints[checkpoint_id] = checkpoint
        return checkpoint

    def restore(self, checkpoint_id: str) -> dict:
        """Restore a checkpoint; verify hash BEFORE applying."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint {checkpoint_id!r} not found")
        recomputed = deterministic_hash(_canonical(checkpoint.state))
        if recomputed != checkpoint.state_hash:
            raise ValueError(
                f"checkpoint {checkpoint_id!r} tamper detected: state hash "
                "mismatch — refusing to restore corrupted state"
            )
        return dict(checkpoint.state)

    def __len__(self) -> int:
        return len(self._checkpoints)


class RecoveryManager:
    """Orchestrates checkpoint-verified recovery plans."""

    def __init__(self, checkpoints: CheckpointManager) -> None:
        self._checkpoints = checkpoints

    def recover(self, checkpoint_id: str) -> dict:
        """Recover to a checkpoint (hash-verified restore)."""
        return self._checkpoints.restore(checkpoint_id)


__all__ = [
    "ReproducibilityError",
    "ReproducibilityResult",
    "DeterministicRunner",
    "ReproducibilityVerifier",
    "MetricsRegistry",
    "LogEntry",
    "StructuredLog",
    "HealthStatus",
    "HealthCheck",
    "Alert",
    "AlertManager",
    "Monitor",
    "Checkpoint",
    "CheckpointManager",
    "RecoveryManager",
    "PHASE_10_CONTRACT_VERSION",
]
