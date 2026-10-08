"""Authoritative vocabulary bridge (RT-F6) + BUG-008 runtime-boundary
adapters (pre-paper mandate §5/§6/§40).

The repository historically carries TWO disjoint order/position
vocabularies:

- **paper domain** (``paper/models.py``): lowercase ``buy``/``sell``
  sides, ``Decimal`` quantities, 4-state ``OrderStatus``;
- **frozen strategy domain** (``strategy/schemas.py`` — SUB-18
  manifest-pinned, immutable by rule): uppercase ``LONG``/``SHORT``,
  ``float`` quantities, ``PENDING/FILLED/REJECTED/CANCELLED``.

RT-F6 correction: this module is the ONE authoritative bridge. Every
cross-domain translation goes through it — no ad-hoc conversions in
callers, no frozen-file modification (the bridge lives entirely in
the non-frozen runtime package).

BUG-008 runtime-boundary adapter: the 13 deferred mutable fields (9
frozen-strategy + 4 manifest-pinned schemas.py fields) are never
mutated by the runtime — strategy-domain models crossing into the
runtime are DEEP-COPIED and frozen at this boundary, so the residual
deferment is contained without touching the pinned files.
"""

import copy
from decimal import Decimal
from typing import Any, Mapping, Optional

from data_engine.paper.models import OrderSide as PaperOrderSide
from data_engine.runtime.contracts import (
    DecisionAction,
    OrderLifecycle,
    RuntimeContractError,
)

#: Documented float→Decimal conversion precision (strategy domain is
#: float-based; the runtime is Decimal-based). 10 decimal places is
#: far below any float's ~15-17 significant digits and far above any
#: real instrument tick — the conversion is lossless in practice and
#: deterministic by construction.
_STRATEGY_FLOAT_DP = 10


class VocabularyError(RuntimeContractError):
    """Raised on invalid cross-domain translations."""


# ---------------------------------------------------------------------------
# Side vocabulary: strategy LONG/SHORT ⇄ paper buy/sell ⇄ runtime BUY/SELL
# ---------------------------------------------------------------------------

_STRATEGY_TO_RUNTIME = {"LONG": DecisionAction.BUY, "SHORT": DecisionAction.SELL}
_RUNTIME_TO_STRATEGY = {
    DecisionAction.BUY: "LONG",
    DecisionAction.SELL: "SHORT",
}
_RUNTIME_TO_PAPER = {
    DecisionAction.BUY: PaperOrderSide.BUY,
    DecisionAction.SELL: PaperOrderSide.SELL,
}


def strategy_side_to_runtime(side: str) -> DecisionAction:
    """``LONG``/``SHORT`` (frozen strategy vocabulary) → BUY/SELL."""
    if not isinstance(side, str):
        raise VocabularyError("strategy side must be a string")
    key = side.strip().upper()
    if key not in _STRATEGY_TO_RUNTIME:
        raise VocabularyError(
            f"unknown strategy side {side!r} (expected LONG/SHORT)"
        )
    return _STRATEGY_TO_RUNTIME[key]


def runtime_side_to_strategy(action: DecisionAction) -> str:
    """BUY/SELL → ``LONG``/``SHORT`` (frozen strategy vocabulary)."""
    if action not in _RUNTIME_TO_STRATEGY:
        raise VocabularyError(
            f"runtime side must be BUY or SELL (got {action!r}); "
            "REDUCE/CLOSE are netted to quantities upstream"
        )
    return _RUNTIME_TO_STRATEGY[action]


def runtime_side_to_paper(action: DecisionAction) -> PaperOrderSide:
    """BUY/SELL → paper ``buy``/``sell``."""
    if action not in _RUNTIME_TO_PAPER:
        raise VocabularyError(
            f"runtime side must be BUY or SELL (got {action!r})"
        )
    return _RUNTIME_TO_PAPER[action]


def paper_side_to_runtime(side: PaperOrderSide) -> DecisionAction:
    """Paper ``buy``/``sell`` → BUY/SELL."""
    if side is PaperOrderSide.BUY:
        return DecisionAction.BUY
    if side is PaperOrderSide.SELL:
        return DecisionAction.SELL
    raise VocabularyError(f"unknown paper side {side!r}")


# ---------------------------------------------------------------------------
# Quantity vocabulary: strategy float ⇄ runtime Decimal
# ---------------------------------------------------------------------------

def strategy_quantity_to_decimal(quantity: float) -> Decimal:
    """Frozen-strategy float quantity → runtime Decimal (lossless at
    10 dp, deterministic; rejects non-finite/NaN)."""
    if quantity is None or quantity != quantity or quantity in (
        float("inf"),
        float("-inf"),
    ):
        raise VocabularyError(
            f"strategy quantity {quantity!r} is not finite (NaN/inf "
            "fail closed)"
        )
    return Decimal(str(round(float(quantity), _STRATEGY_FLOAT_DP)))


def decimal_quantity_to_strategy(quantity: Decimal) -> float:
    """Runtime Decimal quantity → frozen-strategy float (for
    reporting into the strategy domain only — never for execution)."""
    if quantity is None or not quantity.is_finite():
        raise VocabularyError("decimal quantity must be finite")
    return float(round(quantity, _STRATEGY_FLOAT_DP))


# ---------------------------------------------------------------------------
# Status vocabulary: paper 4-state ⇄ runtime 14-state lifecycle
# ---------------------------------------------------------------------------

_PAPER_TO_LIFECYCLE = {
    "submitted": OrderLifecycle.SUBMITTED,
    "filled": OrderLifecycle.FILLED,
    "cancelled": OrderLifecycle.CANCELLED,
    "rejected": OrderLifecycle.REJECTED,
}

#: Runtime lifecycle states that map DOWN to paper "filled" (the
#: paper gateway vocabulary only records terminal fill state).
_LIFECYCLE_FILLED_STATES = frozenset({OrderLifecycle.FILLED})


def paper_status_to_lifecycle(status: str) -> OrderLifecycle:
    """Paper ``OrderStatus`` value → runtime ``OrderLifecycle``."""
    if not isinstance(status, str):
        raise VocabularyError("paper status must be a string")
    key = status.strip().lower()
    if key not in _PAPER_TO_LIFECYCLE:
        raise VocabularyError(
            f"unknown paper status {status!r} "
            f"(expected {sorted(_PAPER_TO_LIFECYCLE)})"
        )
    return _PAPER_TO_LIFECYCLE[key]


def lifecycle_to_paper_status(state: OrderLifecycle) -> str:
    """Runtime ``OrderLifecycle`` → paper ``OrderStatus`` value.

    The paper vocabulary has no partial-fill state: PARTIALLY_FILLED
    maps to ``submitted`` (the order is still live in the gateway
    sense); EXPIRED/CANCEL_PENDING map to ``cancelled``-family
    states; RECONCILING/UNKNOWN/FAILED map to ``rejected`` (the
    gateway never acknowledges them as fills).
    """
    if state in _LIFECYCLE_FILLED_STATES:
        return "filled"
    if state in (OrderLifecycle.CREATED, OrderLifecycle.VALIDATED,
                 OrderLifecycle.RISK_APPROVED, OrderLifecycle.SUBMITTED,
                 OrderLifecycle.ACKNOWLEDGED, OrderLifecycle.PARTIALLY_FILLED):
        return "submitted"
    if state in (OrderLifecycle.CANCEL_PENDING, OrderLifecycle.CANCELLED,
                 OrderLifecycle.EXPIRED):
        return "cancelled"
    if state in (OrderLifecycle.REJECTED, OrderLifecycle.RECONCILING,
                 OrderLifecycle.UNKNOWN, OrderLifecycle.FAILED):
        return "rejected"
    raise VocabularyError(f"unmapped lifecycle state {state!r}")


# ---------------------------------------------------------------------------
# BUG-008 runtime-boundary adapter
# ---------------------------------------------------------------------------

def freeze_strategy_boundary(model: Any) -> Mapping[str, Any]:
    """BUG-008 runtime-boundary adapter (mandate §5).

    Strategy-domain (and schemas.py) models carry 13 manifest/frozen
    immune mutable fields that CANNOT be migrated without touching
    SUB-18-pinned files. This adapter guarantees the runtime NEVER
    mutates them: any strategy-domain object crossing into the runtime
    is deep-copied and returned as a read-only mapping snapshot.

    The returned mapping is a plain ``dict`` COPY — the runtime treats
    it as immutable by convention enforced at every use site
    (contracts accept it only through frozen pydantic fields). The
    ORIGINAL object is never retained or mutated.
    """
    if model is None:
        raise VocabularyError("boundary snapshot requires a model")
    if hasattr(model, "model_dump"):
        snapshot = copy.deepcopy(model.model_dump())
    elif isinstance(model, Mapping):
        snapshot = copy.deepcopy(dict(model))
    elif hasattr(model, "__dict__"):
        snapshot = copy.deepcopy(vars(model))
    else:
        raise VocabularyError(
            f"cannot snapshot {type(model).__name__} at the strategy "
            "boundary (expected pydantic model / mapping)"
        )
    return snapshot


__all__ = [
    "VocabularyError",
    "strategy_side_to_runtime",
    "runtime_side_to_strategy",
    "runtime_side_to_paper",
    "paper_side_to_runtime",
    "strategy_quantity_to_decimal",
    "decimal_quantity_to_strategy",
    "paper_status_to_lifecycle",
    "lifecycle_to_paper_status",
    "freeze_strategy_boundary",
]
