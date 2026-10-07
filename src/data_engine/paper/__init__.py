"""Phase 11 — Paper trading package (blueprint 5.51/5.55).

NO REAL MONEY. NO BROKER CREDENTIALS. Simulated execution with market
realism (spread, commission, slippage, latency), full reconciliation,
and an immutable audit trail.
"""

__version__ = "11.0.0"

from data_engine.paper.models import (
    OrderSide,
    OrderType,
    OrderStatus,
    PaperOrder,
    Fill,
    PaperPosition,
    PHASE_11_CONTRACT_VERSION,
)
from data_engine.paper.simulator import (
    SimulationError,
    ExecutionRealism,
    ExecutionSimulator,
)
from data_engine.paper.gateway import (
    GatewayError,
    GatewayRecord,
    PaperOrderGateway,
    ReconciliationError,
    ReconciliationEngine,
    AuditLogger,
    AnalyticsEngine,
)

__all__ = [
    "__version__",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "PaperOrder",
    "Fill",
    "PaperPosition",
    "PHASE_11_CONTRACT_VERSION",
    "SimulationError",
    "ExecutionRealism",
    "ExecutionSimulator",
    "GatewayError",
    "GatewayRecord",
    "PaperOrderGateway",
    "ReconciliationError",
    "ReconciliationEngine",
    "AuditLogger",
    "AnalyticsEngine",
]
