"""Deterministic identity primitives for prediction intelligence (§15, §45).

Identity rules (inheriting the Phase 4 identity discipline,
``data_engine.pit.hashing``):

- Every identity is ``<domain-prefix>`` + SHA-256 hex over a canonical
  payload that ALWAYS includes ``PREDICTION_CONTRACT_VERSION``.
- Identity is a pure function of declared values: no wall-clock, no RNG,
  no PID, no path/locale (ID-WC-03 discipline).
- Prediction identity NEVER depends on the frozen Phase 3 ``Candle``
  hash method or any other frozen hash method (H-1 independence,
  mandate §53; FRZ-01..03 discipline). Hashes are computed over
  caller-extracted values via ``deterministic_hash``.

Floats are rounded to 12 decimal places before hashing (same convention
as ``quant/features.py`` ``_freeze``) so identical computations yield
identical identities across processes.

Prefix map (prediction identity family):
- ``pred.``   prediction identity (prediction_id)
- ``predl.``  crash label definition identity
- ``predm.``  model / calibrator artifact identity
- ``predf.``  feature-set / feature-data identity
- ``predv.``  provenance record identity
- ``predo.``  prediction output identity
- ``prede.``  evidence assessment identity
- ``predd.``  drift report identity
- ``predr.``  registry record identity
- ``predg.``  outcome-ledger entry identity
- ``preds.``  dataset manifest / dataset content identity
- ``predq.``  data-quality report identity
- ``predx.``  external artifact verification identity
- ``predw.``  crash-event evaluation identity
- ``predb.``  benchmark artifact identity
- ``preda.``  red-team attack record identity
- ``predc.``  data-source catalog record identity
- ``predn.``  regime transition event identity (ARCH-F7)
"""

import platform
import sys
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash

from data_engine.prediction.contracts import (
    PREDICTION_CONTRACT_VERSION,
    PredictionContractError,
)

PREDICTION_PREFIX = "pred."
LABEL_DEFINITION_PREFIX = "predl."
MODEL_PREFIX = "predm."
FEATURE_PREFIX = "predf."
PROVENANCE_PREFIX = "predv."
OUTPUT_PREFIX = "predo."
EVIDENCE_PREFIX = "prede."
DRIFT_PREFIX = "predd."
REGISTRY_PREFIX = "predr."
LEDGER_PREFIX = "predg."
DATASET_PREFIX = "preds."
QUALITY_PREFIX = "predq."
VERIFICATION_PREFIX = "predx."
EVENT_PREFIX = "predw."
BENCHMARK_PREFIX = "predb."
ATTACK_PREFIX = "preda."
SOURCE_CATALOG_PREFIX = "predc."
#: ARCH-F7: dedicated prefix for regime transition events
#: (previously reused the provenance ``predv.`` prefix — identity
#: namespaces must not be shared across record kinds).
REGIME_EVENT_PREFIX = "predn."


def freeze_number(value: Optional[float]) -> Optional[float]:
    """Freeze a float for hashing: round to 12 decimals; NaN -> None.

    ``None`` marks a missing value so it can never be silently hashed as
    a number (fail-closed: callers decide how to treat missing values).
    Non-finite values (``inf``/``-inf``) are REJECTED — a non-finite
    number is a data-quality failure, never a hashable identity input
    (red-team hardening, RT-PRED-I-007).
    """
    if value is None:
        return None
    if value != value:  # NaN check — never hash NaN
        return None
    if value in (float("inf"), float("-inf")):
        raise PredictionContractError(
            "non-finite float rejected from identity payloads (inf)"
        )
    return round(float(value), 12)


def _freezed(payload: Mapping[str, Any]) -> dict:
    """Recursively freeze numeric leaves of a payload for hashing."""
    out: dict = {}
    for key in sorted(payload):
        value = payload[key]
        if isinstance(value, float):
            out[key] = freeze_number(value)
        elif isinstance(value, Mapping):
            out[key] = _freezed(value)
        elif isinstance(value, (list, tuple)):
            out[key] = [
                freeze_number(v) if isinstance(v, float) else v for v in value
            ]
        else:
            out[key] = value
    return out


def prefixed_hash(prefix: str, payload: Mapping[str, Any]) -> str:
    """Deterministic domain-prefixed identity over a payload.

    The contract version is ALWAYS injected — two artifacts that differ
    only by contract version are different artifacts.
    """
    if not isinstance(prefix, str) or not prefix.endswith("."):
        raise PredictionContractError(
            "identity prefixes must be '<name>.' strings"
        )
    body = dict(payload)
    body["contract_version"] = PREDICTION_CONTRACT_VERSION
    return prefix + deterministic_hash(_freezed(body))


def prediction_identity(
    *,
    model_id: str,
    model_version: str,
    feature_hash: str,
    pit_cutoff_iso: str,
    horizon_bars: int,
    label_definition_id: str,
) -> str:
    """Prediction identity (§15). Pure function of declared inputs.

    Deliberately EXCLUDES the environment fingerprint: the same logical
    prediction carries the same identity on any machine. The environment
    is recorded inside the provenance record instead.
    """
    if horizon_bars < 1:
        raise PredictionContractError("horizon_bars must be >= 1")
    return prefixed_hash(
        PREDICTION_PREFIX,
        {
            "model_id": model_id,
            "model_version": model_version,
            "feature_hash": feature_hash,
            "pit_cutoff": pit_cutoff_iso,
            "horizon_bars": horizon_bars,
            "label_definition_id": label_definition_id,
        },
    )


class EnvironmentFingerprint(BaseModel):
    """Environment fingerprint (§45) — recorded, never guessed.

    Fields: Python version, implementation, OS, architecture, platform
    summary, declared random seeds, and the git commit under which the
    prediction was produced. The git commit is CALLER-SUPPLIED (the
    prediction layer never shells out to git at prediction time).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    python_version: str
    python_implementation: str
    os_name: str
    machine_architecture: str
    platform_summary: str
    seeds: Tuple[int, ...]
    git_commit: str
    notes: Tuple[str, ...] = ()

    @field_validator("python_version", "python_implementation", "os_name",
                     "machine_architecture", "platform_summary", "git_commit")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PredictionContractError(
                "environment fingerprint fields must be non-empty strings"
            )
        return v

    @property
    def fingerprint_hash(self) -> str:
        return prefixed_hash(
            PROVENANCE_PREFIX,
            {
                "kind": "environment_fingerprint",
                "python_version": self.python_version,
                "python_implementation": self.python_implementation,
                "os_name": self.os_name,
                "machine_architecture": self.machine_architecture,
                "platform_summary": self.platform_summary,
                "seeds": list(self.seeds),
                "git_commit": self.git_commit,
            },
        )


def capture_environment(
    *,
    git_commit: str,
    seeds: Sequence[int] = (),
    notes: Sequence[str] = (),
) -> EnvironmentFingerprint:
    """Capture the current interpreter environment (§45).

    The git commit is REQUIRED and caller-supplied — predictions must
    declare the code version they ran under rather than discovering it
    (no process spawning, no ambient repository state).
    """
    return EnvironmentFingerprint(
        python_version=sys.version.split()[0],
        python_implementation=platform.python_implementation(),
        os_name=platform.system(),
        machine_architecture=platform.machine(),
        platform_summary=platform.platform(),
        seeds=tuple(int(s) for s in seeds),
        git_commit=git_commit,
        notes=tuple(notes),
    )


__all__ = [
    "PREDICTION_PREFIX",
    "LABEL_DEFINITION_PREFIX",
    "MODEL_PREFIX",
    "FEATURE_PREFIX",
    "PROVENANCE_PREFIX",
    "OUTPUT_PREFIX",
    "EVIDENCE_PREFIX",
    "DRIFT_PREFIX",
    "REGISTRY_PREFIX",
    "LEDGER_PREFIX",
    "DATASET_PREFIX",
    "QUALITY_PREFIX",
    "VERIFICATION_PREFIX",
    "EVENT_PREFIX",
    "BENCHMARK_PREFIX",
    "ATTACK_PREFIX",
    "SOURCE_CATALOG_PREFIX",
    "REGIME_EVENT_PREFIX",
    "freeze_number",
    "prefixed_hash",
    "prediction_identity",
    "EnvironmentFingerprint",
    "capture_environment",
]
