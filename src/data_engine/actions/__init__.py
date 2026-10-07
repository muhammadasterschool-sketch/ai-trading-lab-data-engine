"""Phase 4A.2 — Corporate Actions, Universe, Calendar package.

Implements blueprint domains 5.11 (Universe Management), 5.12
(Corporate Actions), and 5.13 (Calendar/Session Management) — the
authorized 4A.2 expansion on top of the 4A.1 identity primitives.

Nothing in this package imports frozen Phase 3 ``strategy/`` modules,
and no 4A.3+ capability (futures, rollovers, continuous series) leaks
in here.
"""

__version__ = "4.2.0"

from data_engine.actions.models import (
    CorporateActionType,
    CorporateAction,
    SplitAction,
    DividendAction,
    SymbolChangeAction,
    DelistingAction,
    AnyCorporateAction,
    CORPORATE_ACTION_PREFIX,
    PHASE_4A2_CONTRACT_VERSION,
)
from data_engine.actions.chain import (
    AdjustmentChain,
    AdjustedSeries,
    CorporateActionError,
    FutureActionError,
    ADJUSTMENT_CHAIN_PREFIX,
)
from data_engine.actions.universe import (
    MembershipEventType,
    UniverseMembershipEvent,
    UniverseSnapshot,
    PointInTimeUniverse,
    UNIVERSE_PREFIX,
)
from data_engine.actions.calendar import (
    TradingCalendar,
    SessionPhase,
    CALENDAR_PREFIX,
    DEFAULT_TRADING_DAYS_PER_YEAR,
)

__all__ = [
    "__version__",
    "CorporateActionType",
    "CorporateAction",
    "SplitAction",
    "DividendAction",
    "SymbolChangeAction",
    "DelistingAction",
    "AnyCorporateAction",
    "CORPORATE_ACTION_PREFIX",
    "PHASE_4A2_CONTRACT_VERSION",
    "AdjustmentChain",
    "AdjustedSeries",
    "CorporateActionError",
    "FutureActionError",
    "ADJUSTMENT_CHAIN_PREFIX",
    "MembershipEventType",
    "UniverseMembershipEvent",
    "UniverseSnapshot",
    "PointInTimeUniverse",
    "UNIVERSE_PREFIX",
    "TradingCalendar",
    "SessionPhase",
    "CALENDAR_PREFIX",
    "DEFAULT_TRADING_DAYS_PER_YEAR",
]
