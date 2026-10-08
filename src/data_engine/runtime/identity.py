"""Runtime identity primitives (pre-paper mandate §21/§34/§64).

Identity rules inherit the Phase 4 / prediction identity discipline:

- Every identity is ``<domain-prefix>`` + SHA-256 hex over a canonical
  payload that ALWAYS includes ``RUNTIME_CONTRACT_VERSION``.
- Identity is a pure function of declared values: no wall-clock, no
  RNG, no PID, no path/locale (ID-WC-03 discipline).
- Runtime identity NEVER depends on the frozen Phase 3 ``Candle``
  hash method (H-1 independence; FRZ-01..03 discipline).

Prefix map (runtime identity family):
- ``rtseq.``   sequence / sequence-set identity
- ``rtmod.``   runtime sequence-model artifact identity
- ``rtens.``   ensemble composition identity
- ``rtcal.``   calibration artifact identity (runtime wrapper)
- ``rtpre.``   prediction-artifact identity
- ``rtdec.``   decision identity
- ``rtpln.``   trade-plan identity
- ``rtord.``   runtime order identity (idempotency key)
- ``rtfll.``   runtime fill identity
- ``rtpos.``   position-state identity
- ``rtxit.``   exit record identity
- ``rtled.``   ledger event identity
- ``rtmem.``   trading-memory record identity
- ``rtks.``    kill-switch state/audit identity
- ``rtrg.``    risk assessment identity
- ``rtrec.``   reconciliation report identity
- ``rtsta.``   runtime checkpoint identity
- ``rtdat.``   dataset-readiness record identity
"""

from typing import Any, Mapping

from data_engine.pit.hashing import deterministic_hash

#: Runtime contract version (bumped on any breaking contract change).
#: Lives here — the identity layer is the package root with no
#: runtime-internal imports (avoids the identity↔contracts cycle).
RUNTIME_CONTRACT_VERSION = "1.0.0"

SEQUENCE_PREFIX = "rtseq."
MODEL_PREFIX = "rtmod."
ENSEMBLE_PREFIX = "rtens."
CALIBRATION_PREFIX = "rtcal."
PREDICTION_PREFIX = "rtpre."
DECISION_PREFIX = "rtdec."
TRADE_PLAN_PREFIX = "rtpln."
ORDER_PREFIX = "rtord."
FILL_PREFIX = "rtfll."
POSITION_PREFIX = "rtpos."
EXIT_PREFIX = "rtxit."
LEDGER_PREFIX = "rtled."
MEMORY_PREFIX = "rtmem."
KILL_SWITCH_PREFIX = "rtks."
RISK_PREFIX = "rtrg."
RECONCILIATION_PREFIX = "rtrec."
CHECKPOINT_PREFIX = "rtsta."
DATASET_READINESS_PREFIX = "rtdat."


def prefixed_hash(prefix: str, payload: Mapping[str, Any]) -> str:
    """``prefix`` + SHA-256 over the canonical payload + contract version.

    Floats inside ``payload`` must already be frozen by the caller
    (round to a fixed number of decimals) — the runtime models round
    predictions/probabilities to 12 decimals before identity, matching
    the prediction-layer convention.
    """
    body = dict(payload)
    body["contract_version"] = RUNTIME_CONTRACT_VERSION
    return prefix + deterministic_hash(body)


__all__ = [
    "RUNTIME_CONTRACT_VERSION",
    "SEQUENCE_PREFIX",
    "MODEL_PREFIX",
    "ENSEMBLE_PREFIX",
    "CALIBRATION_PREFIX",
    "PREDICTION_PREFIX",
    "DECISION_PREFIX",
    "TRADE_PLAN_PREFIX",
    "ORDER_PREFIX",
    "FILL_PREFIX",
    "POSITION_PREFIX",
    "EXIT_PREFIX",
    "LEDGER_PREFIX",
    "MEMORY_PREFIX",
    "KILL_SWITCH_PREFIX",
    "RISK_PREFIX",
    "RECONCILIATION_PREFIX",
    "CHECKPOINT_PREFIX",
    "DATASET_READINESS_PREFIX",
    "prefixed_hash",
]
