"""Hierarchical kill-switch manager (pre-paper mandate §26/§61).

Seven scopes, checked BEFORE every execution:

ORDER · STRATEGY · SYMBOL · MODEL · PORTFOLIO · ACCOUNT · GLOBAL

Rules (fail-safe direction):

- **Tripping is unprivileged** — any component may trip any scope;
  the safe direction must always be reachable.
- **Reset is HUMAN-principal gated** (ARCH-F1 discipline): machine
  principals are structurally refused. The AI can NEVER disable a
  critical kill switch (mandate §26/§61). ACCOUNT and GLOBAL scopes
  additionally require a pre-recorded reset AUTHORIZATION — a bare
  human identity call is not enough for the account-wide switches.
- Every activation, reset request, and reset emits an audit record
  (RT-F5 discipline) + an Incident-ledger entry, and is persisted
  (RT-F4) — switch state survives restart.
- A tripped GLOBAL or ACCOUNT switch moves the runtime to HALTED;
  PORTFOLIO stops new orders; SYMBOL forces NO_TRADE for that symbol;
  MODEL retires the model from prediction; STRATEGY disables the
  strategy; ORDER blocks one order id.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import KILL_SWITCH_PREFIX, prefixed_hash
from data_engine.runtime.ledgers import LedgerFamily


class KillSwitchError(RuntimeContractError):
    """Raised on kill-switch contract violations."""


class KillSwitchActive(RuntimeContractError):
    """A governing kill switch is active — execution must refuse."""


class KillSwitchScope(str, Enum):
    ORDER = "ORDER"
    STRATEGY = "STRATEGY"
    SYMBOL = "SYMBOL"
    MODEL = "MODEL"
    PORTFOLIO = "PORTFOLIO"
    ACCOUNT = "ACCOUNT"
    GLOBAL = "GLOBAL"


#: Critical scopes: reset requires human principal + recorded
#: authorization (mandate §26 — AI must never clear these alone).
CRITICAL_SCOPES = frozenset({KillSwitchScope.ACCOUNT, KillSwitchScope.GLOBAL})


class SwitchState(BaseModel):
    """Persisted state of one switch (mandate §26 fields)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: KillSwitchScope
    target: Optional[str] = None  # symbol / model id / strategy / order id
    active: bool = False
    activated_at: Optional[datetime] = None
    reason: Optional[str] = None
    source: Optional[str] = None  # tripping component
    reset_requested_at: Optional[datetime] = None
    reset_requested_by: Optional[str] = None
    reset_authorized_at: Optional[datetime] = None
    reset_authorized_by: Optional[str] = None
    reset_at: Optional[datetime] = None

    @field_validator("target")
    @classmethod
    def _validate_target(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (not isinstance(v, str) or not v.strip()):
            raise KillSwitchError("switch target must be non-empty or None")
        return v.strip().upper() if v else v

    def _utc(v):
        return v


class ResetAuthorization(BaseModel):
    """A recorded human authorization to reset a critical switch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: KillSwitchScope
    target: Optional[str] = None
    principal: str
    authorized_at: datetime
    note: str = ""

    @field_validator("principal")
    @classmethod
    def _validate_principal(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise KillSwitchError("authorization principal must be non-empty")
        return v.strip()


class KillSwitchManager:
    """Authoritative hierarchical kill switch (mandate §26)."""

    def __init__(self, ledger: LedgerFamily) -> None:
        if ledger is None:
            raise KillSwitchError(
                "KillSwitchManager requires its ledger family (RT-F5: "
                "every trip/reset must be audited)"
            )
        self._ledger = ledger
        self._switches: dict = {}  # (scope, target) -> SwitchState
        self._authorizations: list = []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _key(self, scope: KillSwitchScope, target: Optional[str]) -> tuple:
        return (scope, (target.strip().upper() if target else None))

    def _get(self, scope: KillSwitchScope, target: Optional[str]) -> SwitchState:
        return self._switches.get(self._key(scope, target), SwitchState(scope=scope, target=target))

    def _put(self, state: SwitchState) -> None:
        self._switches[self._key(state.scope, state.target)] = state

    def _audit(self, event: str, state: SwitchState, extra: Optional[Mapping] = None) -> str:
        """RT-F5 discipline: every trip/reset/request is ledgered."""
        payload = {
            "scope": state.scope.value,
            "target": state.target,
            "active": state.active,
            "reason": state.reason,
            "source": state.source,
            "activated_at": state.activated_at.isoformat()
            if state.activated_at
            else None,
            "reset_at": state.reset_at.isoformat() if state.reset_at else None,
        }
        if extra:
            payload.update(extra)
        return self._ledger.record(
            ledger="incident",
            event_type=f"KILL_SWITCH_{event}",
            correlation_id=f"kill-switch:{state.scope.value}:{state.target or '*'}",
            actor="runtime.kill_switch",
            payload=payload,
        ).event_id

    # ------------------------------------------------------------------
    # Tripping (unprivileged — the fail-safe direction)
    # ------------------------------------------------------------------
    def trip(
        self,
        scope: KillSwitchScope,
        reason: str,
        source: str,
        target: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> SwitchState:
        if not isinstance(reason, str) or not reason.strip():
            raise KillSwitchError("trip reason must be non-empty (auditable)")
        if not isinstance(source, str) or not source.strip():
            raise KillSwitchError("trip source must be non-empty (auditable)")
        if scope in (KillSwitchScope.SYMBOL, KillSwitchScope.MODEL,
                     KillSwitchScope.STRATEGY, KillSwitchScope.ORDER) and not target:
            raise KillSwitchError(
                f"scope {scope.value} requires a target (symbol/model/"
                "strategy/order id)"
            )
        state = self._get(scope, target)
        if state.active:
            return state  # already tripped — idempotent, still audited below
        now = at or datetime.now(UTC)
        state = state.model_copy(
            update={
                "active": True,
                "activated_at": now,
                "reason": reason.strip(),
                "source": source.strip(),
            }
        )
        self._put(state)
        self._audit("TRIPPED", state)
        return state

    # ------------------------------------------------------------------
    # Checking (before every execution — mandate §26)
    # ------------------------------------------------------------------
    def check(
        self,
        symbol: Optional[str] = None,
        model_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> None:
        """Raise :class:`KillSwitchActive` when ANY governing switch
        for this execution context is active. Called before execution."""
        governing: list = []
        sym = symbol.strip().upper() if symbol else None
        for (scope, target), state in self._switches.items():
            if not state.active:
                continue
            if scope is KillSwitchScope.GLOBAL or scope is KillSwitchScope.ACCOUNT \
                    or scope is KillSwitchScope.PORTFOLIO:
                governing.append(state)
            elif scope is KillSwitchScope.SYMBOL and target == sym:
                governing.append(state)
            elif scope is KillSwitchScope.MODEL and model_id and target == model_id.strip().upper():
                governing.append(state)
            elif scope is KillSwitchScope.STRATEGY and strategy_id and target == strategy_id.strip().upper():
                governing.append(state)
            elif scope is KillSwitchScope.ORDER and order_id and target == order_id.strip().upper():
                governing.append(state)
        if governing:
            desc = "; ".join(
                f"{s.scope.value}:{s.target or '*'} ({s.reason})"
                for s in sorted(governing, key=lambda x: x.scope.value)
            )
            raise KillSwitchActive(
                f"kill switch active — execution refused: {desc}"
            )

    def is_active(
        self,
        scope: KillSwitchScope,
        target: Optional[str] = None,
    ) -> bool:
        return self._get(scope, target).active

    def any_critical_active(self) -> bool:
        return any(
            state.active and state.scope in CRITICAL_SCOPES
            for state in self._switches.values()
        )

    # ------------------------------------------------------------------
    # Reset (human-principal gated; critical scopes need authorization)
    # ------------------------------------------------------------------
    def request_reset(
        self,
        scope: KillSwitchScope,
        requested_by: str,
        target: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> SwitchState:
        """Record a reset REQUEST (does not reset — authorization and
        execution are separate, auditable steps)."""
        state = self._get(scope, target)
        if not state.active:
            raise KillSwitchError(
                f"switch {scope.value}:{target or '*'} is not active — "
                "nothing to reset"
            )
        state = state.model_copy(
            update={
                "reset_requested_at": at or datetime.now(UTC),
                "reset_requested_by": requested_by,
            }
        )
        self._put(state)
        self._audit("RESET_REQUESTED", state, {"requested_by": requested_by})
        return state

    def authorize_reset(
        self,
        scope: KillSwitchScope,
        principal: str,
        principal_kind: str = "human",
        target: Optional[str] = None,
        note: str = "",
        at: Optional[datetime] = None,
    ) -> ResetAuthorization:
        """Record the HUMAN authorization required for critical-scope
        resets (ACCOUNT/GLOBAL). Machine principals are refused."""
        if principal_kind != "human" or not isinstance(principal, str) or not principal.strip():
            raise KillSwitchError(
                "kill-switch reset authorization requires an identified "
                "HUMAN principal (mandate §26/§61) — machine principals "
                "are structurally refused"
            )
        if scope not in CRITICAL_SCOPES:
            raise KillSwitchError(
                f"scope {scope.value} is not critical — authorization "
                "records are only required for ACCOUNT/GLOBAL resets"
            )
        auth = ResetAuthorization(
            scope=scope,
            target=target,
            principal=principal.strip(),
            authorized_at=at or datetime.now(UTC),
            note=note,
        )
        self._authorizations.append(auth)
        self._audit(
            "RESET_AUTHORIZED",
            self._get(scope, target),
            {"authorized_by": auth.principal},
        )
        return auth

    def reset(
        self,
        scope: KillSwitchScope,
        principal: str,
        principal_kind: str = "machine",
        target: Optional[str] = None,
        at: Optional[datetime] = None,
    ) -> SwitchState:
        """Reset a switch.

        - ALL scopes require an identified HUMAN principal (ARCH-F1).
        - CRITICAL scopes (ACCOUNT/GLOBAL) additionally require a
          prior recorded authorization from the SAME principal.
        The AI can never perform this successfully (§61).
        """
        if not isinstance(principal, str) or not principal.strip():
            raise KillSwitchError(
                "kill-switch reset requires an identified principal"
            )
        if principal_kind != "human":
            raise KillSwitchError(
                f"kill-switch reset refused for principal_kind="
                f"{principal_kind!r}: only a HUMAN principal may reset "
                "(the AI must never disable a critical kill switch)"
            )
        state = self._get(scope, target)
        if not state.active:
            raise KillSwitchError(
                f"switch {scope.value}:{target or '*'} is not active"
            )
        if scope in CRITICAL_SCOPES:
            authorized = any(
                a.scope is scope
                and a.target == (target.strip().upper() if target else None)
                and a.principal == principal.strip()
                for a in self._authorizations
            )
            if not authorized:
                raise KillSwitchError(
                    f"critical-scope reset ({scope.value}) requires a "
                    f"recorded authorization by principal {principal!r} "
                    "FIRST (request_reset → authorize_reset → reset)"
                )
        now = at or datetime.now(UTC)
        state = state.model_copy(update={"active": False, "reset_at": now})
        self._put(state)
        self._audit("RESET", state, {"reset_by": principal})
        return state

    # ------------------------------------------------------------------
    # Persistence (RT-F4)
    # ------------------------------------------------------------------
    def export_state(self) -> list:
        return [s.model_dump(mode="json") for s in self._switches.values()]

    def restore_state(self, records: Sequence[Mapping[str, Any]]) -> int:
        restored = 0
        for record in records:
            state = SwitchState.model_validate(record)
            self._put(state)
            restored += 1
        return restored

    def states(self) -> Tuple[SwitchState, ...]:
        return tuple(self._switches.values())


__all__ = [
    "KillSwitchError",
    "KillSwitchActive",
    "KillSwitchScope",
    "CRITICAL_SCOPES",
    "SwitchState",
    "ResetAuthorization",
    "KillSwitchManager",
]
