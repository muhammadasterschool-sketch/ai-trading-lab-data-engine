"""Durable STOP control for the monitor surface (v1.0.0 — owner
mandate: "mai chahu to stop kar pao trading ko").

The monitoring API already carries the ONE deliberately-mutating
endpoint — ``POST /api/killswitch/activate`` — but in the bare CLI
serve path the activator was UNWIRED (503 fail-closed,
"NOT_WIRED_IN_BARE_CLI_PATH"): the phone's kill-switch button could
never actually do anything against the local monitor.

This store makes the STOP control REAL and DURABLE on the user's own
machine while staying honest about what it is:

- **What it is**: a persisted halt flag
  (``monitor-state/kill_switch_state.json``) + the activator/state
  callables the monitoring API contract already expects.
- **What it honestly is NOT**: a live order-flow circuit breaker —
  monitor-only mode composes NO trading session, so there is nothing
  to interrupt mid-flight. The flag is the STANDING STOP decision for
  this install: any composed session must honor it before executing
  (the engine's hierarchical kill-switch checks run BEFORE every
  execution; a GLOBAL-scope ACTIVE state means HALT).
- **STOP from the phone**: POST /api/killswitch/activate with
  {"confirm": true, "reason": "..."} — exact existing contract,
  reason mandatory, redacted in logs.
- **RESUME is PC-gated ON PURPOSE**: the engine's kill-switch
  discipline says reset is a HUMAN-principal action on the machine
  (``data-engine control-reset`` CLI command, v1.0.0). The phone can
  STOP anything; only the owner AT the PC resumes. Fail-safe
  direction, no exceptions.
- **Atomic durability**: state writes go through tmp-file +
  ``os.replace``; a crash mid-write can never produce a torn state
  file that looks INACTIVE.

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from data_engine.runtime.contracts import RuntimeContractError

STATE_ACTIVE = "ACTIVE"
STATE_INACTIVE = "INACTIVE"

_MAX_REASON = 256
_MAX_ACTOR = 128


class KillSwitchStoreError(RuntimeContractError):
    """Raised on kill-switch store contract violations."""


class DurableKillSwitch:
    """Persisted GLOBAL halt flag + monitoring-API callables."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock  # None -> wall-clock ISO timestamps
        self._lock = threading.Lock()
        self._state = self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> dict:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and raw.get("state") in (
                STATE_ACTIVE,
                STATE_INACTIVE,
            ):
                return raw
        except (OSError, ValueError):
            pass
        return self._inactive_state()

    def _now_iso(self) -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _inactive_state(self) -> dict:
        return {
            "state": STATE_INACTIVE,
            "reason": "",
            "activated_by": "",
            "activated_at": "",
            "updated_at": self._now_iso(),
            "detail": (
                "standing halt flag for this install; monitor-only mode "
                "composes no trading session — a composed session must "
                "honor this flag before every execution"
            ),
        }

    def _write(self) -> None:
        payload = json.dumps(self._state, ensure_ascii=False, indent=1)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    # -- monitoring-API contract ----------------------------------------------

    def state(self) -> dict:
        """Kill-switch state provider (GET /api/killswitch)."""
        with self._lock:
            return dict(self._state)

    def activate(self, actor: str, reason: str) -> dict:
        """Kill-switch activator (POST /api/killswitch/activate).

        ``actor``/``reason`` arrive redacted from the monitoring API;
        both are length-capped again here (defense in depth).
        """
        actor_text = str(actor or "").strip()[:_MAX_ACTOR]
        reason_text = str(reason or "").strip()[:_MAX_REASON]
        if not reason_text:
            raise KillSwitchStoreError("a non-empty reason is required")
        with self._lock:
            self._state = {
                "state": STATE_ACTIVE,
                "reason": reason_text,
                "activated_by": actor_text,
                "activated_at": self._now_iso(),
                "updated_at": self._now_iso(),
                "detail": (
                    "STOP requested via the monitoring API; composed "
                    "sessions must treat trading as HALTED"
                ),
            }
            self._write()
            return dict(self._state)

    def reset(self, actor: str) -> dict:
        """HUMAN-principal resume, run ON the PC (``control-reset``).

        This is deliberately NOT reachable from the monitoring API:
        stop-from-anywhere, resume-at-the-machine keeps the fail-safe
        direction (mandate §26 discipline).
        """
        actor_text = str(actor or "").strip()[:_MAX_ACTOR]
        with self._lock:
            self._state = self._inactive_state()
            self._state["activated_by"] = actor_text
            self._state["detail"] = (
                "reset by the owner ON the PC (control-reset); "
                "trading gate restored to its standing state"
            )
            self._write()
            return dict(self._state)


__all__ = [
    "DurableKillSwitch",
    "KillSwitchStoreError",
    "STATE_ACTIVE",
    "STATE_INACTIVE",
]
