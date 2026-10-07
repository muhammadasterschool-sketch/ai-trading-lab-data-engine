"""Phase 8 — Risk and portfolio package (blueprint 5.28–5.31)."""

__version__ = "8.0.0"

from data_engine.risk.engine import (
    RiskLimits,
    RiskViolationError,
    KillSwitchActiveError,
    ViolationRecord,
    ExposureReport,
    RiskEngine,
    ExposureManager,
    PHASE_8_CONTRACT_VERSION,
)
from data_engine.risk.portfolio import (
    PortfolioError,
    Allocation,
    PortfolioConstructor,
)

__all__ = [
    "__version__",
    "RiskLimits",
    "RiskViolationError",
    "KillSwitchActiveError",
    "ViolationRecord",
    "ExposureReport",
    "RiskEngine",
    "ExposureManager",
    "PHASE_8_CONTRACT_VERSION",
    "PortfolioError",
    "Allocation",
    "PortfolioConstructor",
]
