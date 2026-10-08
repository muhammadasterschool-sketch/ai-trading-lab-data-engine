"""SL/TP lifecycle and exit semantics (pre-paper mandate §31).

Complete lifecycle vocabulary, every transition ledgered:

- ``SL_SET`` / ``SL_MODIFIED`` / ``SL_HIT``
- ``TP_SET`` / ``TP_MODIFIED`` / ``TP_HIT``
- ``RISK_EXIT`` / ``CRASH_EXIT`` / ``STRATEGY_EXIT`` /
  ``MANUAL_CLOSE`` / ``SYSTEM_CLOSE`` / ``KILL_SWITCH_CLOSE``

Every exit produces an :class:`ExitRecord` (exit id, reason,
timestamp, position, order/fill linkage, correlation id — §31)
and is recorded in the Position/Trade ledgers.

Deterministic SL/TP evaluation over bars:

- long: SL hit when ``bar.low <= SL``; TP hit when
  ``bar.high >= TP``;
- short: SL hit when ``bar.high >= SL``; TP hit when
  ``bar.low <= TP``;
- a bar that trips BOTH resolves to the STOP (conservative worst-
  case ordering — documented, deterministic, never optimistic).
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import ExitReason, ExitRecord, RuntimeContractError
from data_engine.runtime.identity import EXIT_PREFIX, prefixed_hash
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.pnl import PositionState


class ExitError(RuntimeContractError):
    """Raised on exit-lifecycle contract violations."""


class ProtectionLevels(BaseModel):
    """A position's SL/TP snapshot (immutable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ExitError("symbol must be non-empty")
        return v.strip().upper()

    @field_validator("stop_loss", "take_profit")
    @classmethod
    def _validate_levels(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and (not v.is_finite() or v <= 0):
            raise ExitError("protection levels must be positive finite")
        return v


class ExitManager:
    """Authoritative SL/TP + exit lifecycle (mandate §31)."""

    def __init__(self, ledger: LedgerFamily) -> None:
        if ledger is None:
            raise ExitError("ExitManager requires its ledger family")
        self._ledger = ledger
        self._exits: dict = {}

    # ------------------------------------------------------------------
    # SL/TP lifecycle events
    # ------------------------------------------------------------------
    def set_stop_loss(
        self,
        state: PositionState,
        level: Decimal,
        correlation_id: str,
        at: datetime,
    ) -> Tuple[PositionState, str]:
        """SL_SET (or SL_MODIFIED when a level already exists)."""
        if level is None or not level.is_finite() or level <= 0:
            raise ExitError("stop-loss level must be positive finite")
        self._assert_geometry(state, sl=level)
        event = "SL_MODIFIED" if state.stop_loss is not None else "SL_SET"
        event_id = self._ledger.record(
            ledger="position",
            event_type=event,
            correlation_id=correlation_id,
            actor="runtime.exit_manager",
            payload={
                "symbol": state.symbol,
                "level": str(level),
                "previous": str(state.stop_loss)
                if state.stop_loss is not None
                else None,
                "quantity": str(state.quantity),
            },
            parent_id=state.position_id,
        ).event_id
        new_state = state.with_protection(
            stop_loss=level, source_event=event_id, at=at
        )
        return new_state, event_id

    def set_take_profit(
        self,
        state: PositionState,
        level: Decimal,
        correlation_id: str,
        at: datetime,
    ) -> Tuple[PositionState, str]:
        """TP_SET (or TP_MODIFIED when a level already exists)."""
        if level is None or not level.is_finite() or level <= 0:
            raise ExitError("take-profit level must be positive finite")
        self._assert_geometry(state, tp=level)
        event = "TP_MODIFIED" if state.take_profit is not None else "TP_SET"
        event_id = self._ledger.record(
            ledger="position",
            event_type=event,
            correlation_id=correlation_id,
            actor="runtime.exit_manager",
            payload={
                "symbol": state.symbol,
                "level": str(level),
                "previous": str(state.take_profit)
                if state.take_profit is not None
                else None,
                "quantity": str(state.quantity),
            },
            parent_id=state.position_id,
        ).event_id
        new_state = state.with_protection(
            take_profit=level, source_event=event_id, at=at
        )
        return new_state, event_id

    def _assert_geometry(
        self,
        state: PositionState,
        sl: Optional[Decimal] = None,
        tp: Optional[Decimal] = None,
    ) -> None:
        """SL below / TP above the average entry for longs (mirror for
        shorts) — inverted protection is refused at set time."""
        sl_level = sl if sl is not None else state.stop_loss
        tp_level = tp if tp is not None else state.take_profit
        if state.quantity > 0:
            if sl_level is not None and state.average_cost > 0 and sl_level >= state.average_cost:
                raise ExitError(
                    f"long stop-loss {sl_level} must sit below average "
                    f"entry {state.average_cost}"
                )
            if tp_level is not None and tp_level <= state.average_cost:
                raise ExitError(
                    f"long take-profit {tp_level} must sit above average "
                    f"entry {state.average_cost}"
                )
        elif state.quantity < 0:
            if sl_level is not None and sl_level <= state.average_cost:
                raise ExitError(
                    f"short stop-loss {sl_level} must sit above average "
                    f"entry {state.average_cost}"
                )
            if tp_level is not None and tp_level >= state.average_cost:
                raise ExitError(
                    f"short take-profit {tp_level} must sit below average "
                    f"entry {state.average_cost}"
                )

    # ------------------------------------------------------------------
    # Bar evaluation
    # ------------------------------------------------------------------
    def evaluate_bar(
        self, state: PositionState, bar: Mapping
    ) -> Optional[Tuple[ExitReason, Decimal]]:
        """Deterministic SL/TP evaluation on one bar.

        Returns ``(reason, trigger_level)`` when a protective level is
        hit, else None. A bar tripping both resolves to the STOP
        (conservative worst-case, documented).
        """
        if state.is_flat:
            return None
        low = Decimal(str(bar["low"]))
        high = Decimal(str(bar["high"]))
        if state.quantity > 0:
            sl_hit = state.stop_loss is not None and low <= state.stop_loss
            tp_hit = state.take_profit is not None and high >= state.take_profit
            if sl_hit:
                return ExitReason.SL_HIT, state.stop_loss
            if tp_hit:
                return ExitReason.TP_HIT, state.take_profit
        else:
            sl_hit = state.stop_loss is not None and high >= state.stop_loss
            tp_hit = state.take_profit is not None and low <= state.take_profit
            if sl_hit:
                return ExitReason.SL_HIT, state.stop_loss
            if tp_hit:
                return ExitReason.TP_HIT, state.take_profit
        return None

    # ------------------------------------------------------------------
    # Exit records
    # ------------------------------------------------------------------
    def record_exit(
        self,
        reason: ExitReason,
        state: PositionState,
        timestamp: datetime,
        order_ids: Tuple[str, ...],
        fill_ids: Tuple[str, ...],
        correlation_id: str,
    ) -> ExitRecord:
        """Create + ledger one exit record (mandate §31 linkage)."""
        if state is None or state.is_flat:
            raise ExitError(
                "exits require a non-flat position (flat exits are "
                "accounting summaries, not exit events)"
            )
        exit_id = prefixed_hash(
            EXIT_PREFIX,
            {
                "kind": "exit",
                "reason": reason.value,
                "symbol": state.symbol,
                "timestamp": timestamp,
                "position_quantity": str(state.quantity),
                "order_ids": list(order_ids),
                "fill_ids": list(fill_ids),
                "correlation_id": correlation_id,
            },
        )
        record = ExitRecord(
            exit_id=exit_id,
            reason=reason,
            symbol=state.symbol,
            timestamp=timestamp,
            position_quantity=state.quantity,
            average_cost=state.average_cost,
            order_ids=tuple(order_ids),
            fill_ids=tuple(fill_ids),
            realized_pnl=state.realized_pnl,
            correlation_id=correlation_id,
        )
        self._exits[exit_id] = record
        self._ledger.record(
            ledger="trade",
            event_type=f"EXIT_{reason.value}",
            correlation_id=correlation_id,
            actor="runtime.exit_manager",
            payload={
                "exit_id": exit_id,
                "reason": reason.value,
                "symbol": state.symbol,
                "position_quantity": str(state.quantity),
                "average_cost": str(state.average_cost),
                "realized_pnl": str(state.realized_pnl),
                "order_ids": list(order_ids),
                "fill_ids": list(fill_ids),
            },
            parent_id=state.position_id,
        )
        return record

    @property
    def exits(self) -> Tuple[ExitRecord, ...]:
        return tuple(self._exits.values())


__all__ = [
    "ExitError",
    "ProtectionLevels",
    "ExitManager",
]
