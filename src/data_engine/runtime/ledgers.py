"""Trading ledger family (pre-paper mandate §34/§35).

Nine ledgers, each append-only and hash-chained per ledger:

- Prediction Ledger, Decision Ledger, TradePlan Ledger,
  Order Ledger, Fill Ledger, Position Ledger, Trade Ledger,
  P&L Ledger, Incident Ledger.

Every event carries (mandate §34): event ID, timestamp, per-ledger
sequence, correlation ID, parent ID, actor/component, payload hash,
previous hash. Chains are tamper-EVIDENT: ``verify`` recomputes every
link; any edit/deletion/reorder breaks it.

**NO_TRADE ledgering (§35)**: a NO_TRADE decision is recorded in the
Decision Ledger with prediction refs, reason, risk status,
uncertainty, crash risk, regime and the blocked condition — the
system can always answer "why did the system NOT trade?".

Ledger timestamps are wall-clock audit metadata (FS-21 convention)
and never participate in identity hashes. The same convention applies
to ``mac_key_id`` (keyed-MAC mode): it is audit metadata identifying
the SIGNING KEY (a fingerprint, never material) and is not hashed.

Keyed-MAC custody mode (operator mandate 2026-10-10 §1.5): when a
:class:`~data_engine.runtime.mac_custody.MacCustody` is wired, every
event hash is an HMAC-SHA256 over the canonical event fields under
the custody's current key (prefix ``rtledm.``), and the event records
the signing key id. STRICT fail-closed verification both ways:

- custody present  + any event lacking ``mac_key_id``/``rtledm.``  =>
  verify FAILS (downgrade-to-unkeyed is tampering);
- custody absent   + any event carrying ``mac_key_id``/``rtledm.``  =>
  verify FAILS (keyed events cannot be verified without custody);
- custody absent   + all events unkeyed                          =>
  legacy unkeyed chains — byte-identical to the pre-keyed behavior
  (backward compatible with every existing persisted state).

The full-history-rewrite attack (P2 KEYED-MAC finding: re-forge every
link of an unkeyed chain) is defeated in keyed mode because valid
MACs cannot be recomputed without the key.
"""

from datetime import datetime, UTC
import hmac as _hmac
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.identity import LEDGER_PREFIX, prefixed_hash
from data_engine.runtime.mac_custody import (
    MacCustody,
    event_fields_mac,
    keyed_event_mac,
)

#: Unkeyed event-hash prefix (legacy + default mode).
UNKEYED_EVENT_HASH_PREFIX = LEDGER_PREFIX  # "rtled."

#: Keyed-MAC event-hash prefix (custody mode) — structurally distinct
#: so a keyed event can never be confused with an unkeyed one.
KEYED_EVENT_HASH_PREFIX = "rtledm."

#: The nine mandated ledgers (mandate §34).
LEDGER_NAMES = (
    "prediction",
    "decision",
    "trade_plan",
    "order",
    "fill",
    "position",
    "trade",
    "pnl",
    "incident",
)

#: Events that terminate or materially alter an order's lifecycle and
#: therefore REQUIRE a ledger entry (checked by tests).
ORDER_LEDGER_EVENTS = (
    "ORDER_CREATED",
    "ORDER_VALIDATED",
    "ORDER_RISK_APPROVED",
    "ORDER_SUBMITTED",
    "ORDER_ACKNOWLEDGED",
    "ORDER_PARTIAL_FILL",
    "ORDER_FILLED",
    "ORDER_CANCEL_REQUESTED",
    "ORDER_CANCELLED",
    "ORDER_CANCELLED_AFTER_PARTIAL",
    "ORDER_REJECTED",
    "ORDER_EXPIRED",
    "ORDER_UNKNOWN",
    "ORDER_RECONCILING",
    "ORDER_FAILED",
)


class LedgerError(ValueError):
    """Raised on ledger contract violations."""


class LedgerEvent(BaseModel):
    """One immutable ledger record (mandate §34)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    ledger: str
    event_type: str
    timestamp: datetime
    sequence: int
    correlation_id: str
    parent_id: Optional[str] = None
    actor: str
    payload: Mapping[str, Any]
    payload_hash: str
    prev_hash: str
    event_hash: str
    #: Keyed-MAC signing-key fingerprint (audit metadata — NEVER key
    #: material; never hashed). None in legacy unkeyed mode.
    mac_key_id: Optional[str] = None

    @field_validator("event_id", "ledger", "event_type", "correlation_id",
                     "actor")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise LedgerError("ledger text fields must be non-empty")
        return v.strip()

    @field_validator("sequence")
    @classmethod
    def _validate_sequence(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise LedgerError("sequence must be >= 0")
        return v

    @field_validator("ledger")
    @classmethod
    def _validate_ledger_name(cls, v: str) -> str:
        if v not in LEDGER_NAMES:
            raise LedgerError(
                f"unknown ledger {v!r} (allowed: {sorted(LEDGER_NAMES)})"
            )
        return v

    @field_validator("timestamp")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise LedgerError("ledger timestamps must be timezone-aware")
        return v.astimezone(UTC)


def _event_payload_hash(payload: Mapping[str, Any]) -> str:
    return prefixed_hash(LEDGER_PREFIX, {"kind": "payload", "payload": dict(payload)})


def _event_hash(event_fields: Mapping[str, Any]) -> str:
    return prefixed_hash(LEDGER_PREFIX, {"kind": "event", **dict(event_fields)})


def _keyed_event_hash(custody: MacCustody, event_fields: Mapping[str, Any]) -> tuple:
    """Keyed event hash: HMAC-SHA256 over the SAME canonical field set
    the unkeyed path hashes (contract version included). Returns
    ``(event_hash, key_id)`` — the hash carries the ``rtledm.`` prefix
    so keyed and unkeyed events are structurally distinguishable."""
    mac_hex, key_id = keyed_event_mac(
        custody, {"kind": "event", **dict(event_fields)}
    )
    return KEYED_EVENT_HASH_PREFIX + mac_hex, key_id


class _LedgerChain:
    """One ledger's append-only chain (in-memory + optional journal)."""

    def __init__(self, name: str, mac_custody: Optional[MacCustody] = None) -> None:
        self._name = name
        self._events: list[LedgerEvent] = []
        self._mac_custody = mac_custody

    @property
    def name(self) -> str:
        return self._name

    @property
    def events(self) -> tuple:
        return tuple(self._events)

    @property
    def head_hash(self) -> str:
        return self._events[-1].event_hash if self._events else "0" * 64

    def append(
        self,
        event_type: str,
        correlation_id: str,
        actor: str,
        payload: Mapping[str, Any],
        parent_id: Optional[str] = None,
    ) -> LedgerEvent:
        sequence = len(self._events)
        timestamp = datetime.now(UTC)
        payload_hash = _event_payload_hash(payload)
        event_id = f"{self._name}-{sequence:06d}-{event_type}"
        prev_hash = self.head_hash
        fields = {
            "ledger": self._name,
            "event_type": event_type,
            "sequence": sequence,
            "correlation_id": correlation_id,
            "parent_id": parent_id,
            "actor": actor,
            "payload_hash": payload_hash,
            "prev_hash": prev_hash,
        }
        mac_key_id: Optional[str] = None
        if self._mac_custody is not None:
            event_hash, mac_key_id = _keyed_event_hash(
                self._mac_custody, fields
            )
        else:
            event_hash = _event_hash(fields)
        event = LedgerEvent(
            event_id=event_id,
            ledger=self._name,
            event_type=event_type,
            timestamp=timestamp,
            sequence=sequence,
            correlation_id=correlation_id,
            parent_id=parent_id,
            actor=actor,
            payload=dict(payload),
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            event_hash=event_hash,
            mac_key_id=mac_key_id,
        )
        self._events.append(event)
        return event

    def verify(self) -> bool:
        """Recompute the full chain — STRICT on keyed/unkeyed mode.

        Keyed session (custody wired): EVERY event must carry a
        ``mac_key_id`` registered in the custody and an ``rtledm.``
        HMAC that recomputes exactly — any unkeyed event inside a keyed
        session is a downgrade attack and fails verification.

        Unkeyed session (no custody): every event must be legacy
        (``rtled.`` hash, no ``mac_key_id``) and recompute exactly — a
        keyed event without custody is unverifiable and fails.
        """
        prev = "0" * 64
        for i, event in enumerate(self._events):
            if event.sequence != i or event.prev_hash != prev:
                return False
            fields = {
                "ledger": event.ledger,
                "event_type": event.event_type,
                "sequence": event.sequence,
                "correlation_id": event.correlation_id,
                "parent_id": event.parent_id,
                "actor": event.actor,
                "payload_hash": event.payload_hash,
                "prev_hash": event.prev_hash,
            }
            if self._mac_custody is not None:
                # STRICT keyed mode: no unkeyed events allowed.
                if event.mac_key_id is None or \
                        not event.event_hash.startswith(KEYED_EVENT_HASH_PREFIX):
                    return False
                # Recompute under the key THIS EVENT was signed with —
                # which may be a RETIRED rotation key (grace verification).
                key = self._mac_custody.key_for(event.mac_key_id)
                if key is None:
                    return False
                expected_hash = KEYED_EVENT_HASH_PREFIX + event_fields_mac(
                    key, {"kind": "event", **fields}
                )
                # Constant-time MAC comparison.
                if not _hmac.compare_digest(expected_hash, event.event_hash):
                    return False
            else:
                # STRICT unkeyed mode: no keyed events without custody.
                if event.mac_key_id is not None or \
                        event.event_hash.startswith(KEYED_EVENT_HASH_PREFIX):
                    return False
                expected = _event_hash(fields)
                if expected != event.event_hash:
                    return False
            if _event_payload_hash(event.payload) != event.payload_hash:
                return False
            prev = event.event_hash
        return True


class LedgerFamily:
    """The nine authoritative ledgers + NO_TRADE ledgering (§34/§35)."""

    def __init__(self, mac_custody: Optional[MacCustody] = None) -> None:
        if mac_custody is not None and not isinstance(mac_custody, MacCustody):
            raise LedgerError(
                "mac_custody must be a MacCustody instance (keyed-MAC "
                "custody contract — operator mandate 2026-10-10 §1.5)"
            )
        self._mac_custody = mac_custody
        self._chains = {
            name: _LedgerChain(name, mac_custody=mac_custody)
            for name in LEDGER_NAMES
        }

    @property
    def mac_custody(self) -> Optional[MacCustody]:
        """The wired keyed-MAC custody (None = legacy unkeyed mode)."""
        return self._mac_custody

    @property
    def keyed(self) -> bool:
        """True when this family signs events with keyed MACs."""
        return self._mac_custody is not None

    # -- recording ------------------------------------------------------------
    def record(
        self,
        ledger: str,
        event_type: str,
        correlation_id: str,
        actor: str,
        payload: Mapping[str, Any],
        parent_id: Optional[str] = None,
    ) -> LedgerEvent:
        """Append one event to one ledger (per-ledger hash chain)."""
        if ledger not in self._chains:
            raise LedgerError(
                f"unknown ledger {ledger!r} (allowed: {sorted(LEDGER_NAMES)})"
            )
        if not isinstance(payload, Mapping):
            raise LedgerError("payload must be a mapping")
        return self._chains[ledger].append(
            event_type=event_type,
            correlation_id=correlation_id,
            actor=actor,
            payload=payload,
            parent_id=parent_id,
        )

    def record_no_trade(
        self,
        decision,
    ) -> LedgerEvent:
        """Ledger a NO_TRADE decision with its full refusal context
        (mandate §35) — the anti-orphan guarantee for non-trades."""
        payload = {
            "action": "NO_TRADE",
            "symbol": decision.symbol,
            "prediction_ids": list(decision.prediction_ids),
            "reason": decision.reason,
            "risk_status": "not_consulted (no plan built)",
            "uncertainty": {
                "confidence": decision.uncertainty.confidence,
                "entropy": decision.uncertainty.entropy,
                "ensemble_disagreement": decision.uncertainty.ensemble_disagreement,
            },
            "crash_risk": dict(decision.crash_risk),
            "regime": decision.regime,
            "blocked_condition": decision.reason,
            "model_versions": list(decision.model_versions),
        }
        return self.record(
            ledger="decision",
            event_type="DECISION_NO_TRADE",
            correlation_id=decision.correlation_id,
            actor="runtime.decision_engine",
            payload=payload,
            parent_id=decision.decision_id,
        )

    # -- verification -----------------------------------------------------------
    def verify(self) -> bool:
        """True iff EVERY ledger chain recomputes cleanly."""
        return all(chain.verify() for chain in self._chains.values())

    def verify_ledger(self, name: str) -> bool:
        if name not in self._chains:
            raise LedgerError(f"unknown ledger {name!r}")
        return self._chains[name].verify()

    # -- access ------------------------------------------------------------------
    def events(self, ledger: str) -> tuple:
        if ledger not in self._chains:
            raise LedgerError(f"unknown ledger {ledger!r}")
        return self._chains[ledger].events

    def head_hashes(self) -> dict:
        return {
            name: chain.head_hash for name, chain in self._chains.items()
        }

    def total_events(self) -> int:
        return sum(len(chain.events) for chain in self._chains.values())

    def __len__(self) -> int:
        return self.total_events()

    # -- persistence (BLOCKER 6: FULL chains, not just heads) -------------------
    def export_state(self) -> dict:
        """Serialize EVERY ledger chain completely (events + heads).

        Persisting only head hashes cannot reconstruct the lineage
        Prediction → Decision → TradePlan → Order → Fill → Position →
        Exit → Trade → P&L → Incident after restart; the full
        immutable event set is the minimum authoritative record.
        """
        return {
            name: [event.model_dump(mode="json") for event in chain.events]
            for name, chain in self._chains.items()
        }

    def restore_state(self, state: Mapping[str, Any]) -> int:
        """Rebuild all chains from a persisted export; VERIFY as loaded.

        Every event is re-validated (model contract) and the full hash
        chain is recomputed — any tampered/edited/reordered record
        raises :class:`LedgerError` (fail closed: corrupted ledgers
        force RECOVERY_REQUIRED, never silent trust). Returns the
        number of restored events.
        """
        if not isinstance(state, Mapping):
            raise LedgerError("ledger export must be a mapping")
        unknown = set(state) - set(LEDGER_NAMES)
        if unknown:
            raise LedgerError(f"unknown ledgers in export: {sorted(unknown)}")
        restored = 0
        for name in LEDGER_NAMES:
            chain = self._chains[name]
            records = state.get(name, [])
            if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
                raise LedgerError(
                    f"ledger {name!r} export must be a sequence of events"
                )
            events = []
            for record in records:
                try:
                    events.append(LedgerEvent.model_validate(record))
                except Exception as exc:
                    raise LedgerError(
                        f"ledger {name!r} contains a malformed event "
                        f"(sequence {record.get('sequence') if isinstance(record, Mapping) else '?'}): "
                        f"{exc} — RECOVERY_REQUIRED"
                    ) from exc
            chain._events = events
            restored += len(events)
        # Full-chain verification AFTER loading — the restored chains
        # must recompute to exactly the same hashes they had before
        # restart (BLOCKER 6: stored ledger → hash verification →
        # chain reconstruction → same head).
        if not self.verify():
            raise LedgerError(
                "restored ledger chains FAILED hash verification — "
                "tampered or corrupted (RECOVERY_REQUIRED)"
            )
        return restored


__all__ = [
    "LEDGER_NAMES",
    "ORDER_LEDGER_EVENTS",
    "UNKEYED_EVENT_HASH_PREFIX",
    "KEYED_EVENT_HASH_PREFIX",
    "LedgerError",
    "LedgerEvent",
    "LedgerFamily",
]
