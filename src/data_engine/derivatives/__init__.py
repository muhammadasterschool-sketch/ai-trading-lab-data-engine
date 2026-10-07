"""Phase 4A.3 — Derivatives/Futures package (blueprint 5.14).

FuturesContract, RolloverPolicy, roll_detection(), and
ContinuousSeries — PIT-correct roll decisions with structural
leakage prevention.
"""

__version__ = "4.3.0"

from data_engine.derivatives.models import (
    FuturesContract,
    FUTURES_PREFIX,
    PHASE_4A3_CONTRACT_VERSION,
)
from data_engine.derivatives.rollover import (
    RolloverPolicyType,
    RolloverPolicy,
    RollDecision,
    RollLeakageError,
    roll_detection,
)
from data_engine.derivatives.continuous import (
    ContinuousSeries,
    ContinuousSeriesError,
    AdjustmentMethod,
)

__all__ = [
    "__version__",
    "FuturesContract",
    "FUTURES_PREFIX",
    "PHASE_4A3_CONTRACT_VERSION",
    "RolloverPolicyType",
    "RolloverPolicy",
    "RollDecision",
    "RollLeakageError",
    "roll_detection",
    "ContinuousSeries",
    "ContinuousSeriesError",
    "AdjustmentMethod",
]
