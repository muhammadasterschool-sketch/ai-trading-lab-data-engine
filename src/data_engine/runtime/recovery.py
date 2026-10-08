"""Restart / recovery manager (pre-paper mandate §48; RT-F4/BLK-2).

Recovery flow (deterministic, fail-closed):

    runtime running (open orders / open positions / kill-switch state)
    → restart
    → restore persistent state (orders, fills, positions, switches)
    → verify ledger + journal integrity
    → reconcile orders ↔ fills ↔ positions
    → resume (only if EVERYTHING verifies) or HALT /
      RECONCILIATION_REQUIRED

NEVER resume normal trading after restart without the required
reconciliation — a restart that cannot prove its state clean
degrades to HALT, not to amnesia (mandate §48).
"""

from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict

from data_engine.runtime.contracts import RuntimeState
from data_engine.runtime.kill_switch import KillSwitchManager
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.oms import OMS
from data_engine.runtime.reconciliation import RuntimeReconciliation
from data_engine.runtime.state import ExecutionStateStore, StateStoreError


class RecoveryError(ValueError):
    """Raised when recovery cannot prove a safe state."""


class RecoveryReport(BaseModel):
    """One recovery attempt's verdict + evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    restored_orders: int
    restored_switches: int
    ledger_intact: bool
    journal_intact: bool
    reconciliation_ok: bool
    verdict: str  # RESUME / HALT / RECONCILIATION_REQUIRED
    reasons: tuple


class RecoveryManager:
    """Orchestrates restart recovery (mandate §48)."""

    def __init__(
        self,
        state_store: ExecutionStateStore,
        ledgers: LedgerFamily,
        oms: OMS,
        kill_switch: KillSwitchManager,
        reconciliation: RuntimeReconciliation,
    ) -> None:
        if state_store is None or ledgers is None or oms is None \
                or kill_switch is None or reconciliation is None:
            raise RecoveryError(
                "recovery requires ALL components wired (state store, "
                "ledgers, OMS, kill switch, reconciliation)"
            )
        self._store = state_store
        self._ledgers = ledgers
        self._oms = oms
        self._kill_switch = kill_switch
        self._reconciliation = reconciliation

    def recover(
        self,
        positions: Mapping,
    ) -> RecoveryReport:
        """Restore + verify + reconcile; returns the verdict.

        ``positions`` is the persisted position state (restored by the
        caller from the snapshot); reconciliation compares it against
        the restored OMS fills.
        """
        reasons: list = []
        try:
            state = self._store.restore()
        except StateStoreError as exc:
            return RecoveryReport(
                restored_orders=0,
                restored_switches=0,
                ledger_intact=False,
                journal_intact=False,
                reconciliation_ok=False,
                verdict="HALT",
                reasons=(
                    f"persistent state unverifiable: {exc} — recovery "
                    "refuses to resume on unprovable state (mandate §48)",
                ),
            )
        restored_orders = self._oms.restore_state(
            state.get("orders", [])
        )
        restored_switches = self._kill_switch.restore_state(
            state.get("kill_switch", [])
        )
        ledger_intact = self._ledgers.verify()
        if not ledger_intact:
            reasons.append(
                "ledger chain verification FAILED — tampered or corrupted"
            )
        journal_intact = self._store.verify_journal()
        if not journal_intact:
            reasons.append(
                "state journal chain verification FAILED — tampered or "
                "corrupted"
            )
        report = self._reconciliation.reconcile(self._oms, positions)
        reconciliation_ok = report.ok
        if not reconciliation_ok:
            reasons.extend(report.mismatches)

        if self._kill_switch.any_critical_active():
            verdict = "HALT"
            reasons.append(
                "critical kill switch (ACCOUNT/GLOBAL) active across "
                "restart — runtime stays HALTED"
            )
        elif not (ledger_intact and journal_intact):
            verdict = "HALT"
        elif not reconciliation_ok:
            verdict = "RECONCILIATION_REQUIRED"
        else:
            verdict = "RESUME"
        return RecoveryReport(
            restored_orders=restored_orders,
            restored_switches=restored_switches,
            ledger_intact=ledger_intact,
            journal_intact=journal_intact,
            reconciliation_ok=reconciliation_ok,
            verdict=verdict,
            reasons=tuple(reasons),
        )

    @staticmethod
    def state_for(verdict: str):
        """Map a recovery verdict to the runtime operating state."""
        if verdict == "RESUME":
            return RuntimeState.RUNNING
        if verdict == "RECONCILIATION_REQUIRED":
            return RuntimeState.RECONCILIATION_REQUIRED
        return RuntimeState.HALTED


__all__ = [
    "RecoveryError",
    "RecoveryReport",
    "RecoveryManager",
]
