"""Append-only platform audit events (workbook Sheet F source).

Every platform service (registry, strategy lab, news, MT5, TradingView)
records what it did and why into an AuditLog. Events carry EXPLICIT
timestamps supplied by the caller — never ``datetime.now()`` — so tests
and cross-process replay remain deterministic (INV-01 discipline).

Events are records of operational activity, not trading-decision
identity payloads; they never participate in order identity hashing.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

COMPONENTS = (
    "registry",
    "strategy_lab",
    "news",
    "mt5",
    "tradingview",
    "workbook",
    "operator",
)


class PlatformAuditEvent(BaseModel):
    """One immutable audit event."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    component: str = Field(..., description="Service that emitted the event")
    event: str
    detail: Optional[str] = None
    reference_id: Optional[str] = Field(
        default=None, description="Subject of the event (instrument/strategy/news id)"
    )

    def row(self) -> tuple[str, str, str, str, str]:
        """Projection for workbook Sheet F (System Audit Log)."""
        return (
            self.timestamp.isoformat(),
            self.component,
            self.event,
            self.detail or "",
            self.reference_id or "",
        )


class AuditLog:
    """Append-only audit log (fail-closed on unknown components)."""

    def __init__(self) -> None:
        self._events: list[PlatformAuditEvent] = []

    def append(self, event: PlatformAuditEvent) -> None:
        if event.component not in COMPONENTS:
            raise ValueError(
                f"unknown audit component {event.component!r}; "
                f"allowed: {COMPONENTS}"
            )
        self._events.append(event)

    def record(
        self,
        timestamp: datetime,
        component: str,
        event: str,
        detail: Optional[str] = None,
        reference_id: Optional[str] = None,
    ) -> PlatformAuditEvent:
        evt = PlatformAuditEvent(
            timestamp=timestamp,
            component=component,
            event=event,
            detail=detail,
            reference_id=reference_id,
        )
        self.append(evt)
        return evt

    def events(self) -> tuple[PlatformAuditEvent, ...]:
        return tuple(self._events)

    def rows(self) -> tuple[tuple[str, str, str, str, str], ...]:
        return tuple(e.row() for e in self._events)

    def __len__(self) -> int:
        return len(self._events)
