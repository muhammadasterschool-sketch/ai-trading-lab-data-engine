"""BrokerSession — the guarded, account-isolated execution session
(multi-broker mandate, Phase M1).

ONE session binds ONE (adapter, account). Every submission walks the
SAME fail-closed pipeline, regardless of venue:

1. **Account isolation** — the request must name THIS session's
   account (triple binding: session ↔ credential ↔ adapter).
2. **Health gate** — the adapter must be CONNECTED.
3. **Reconciliation gate** — an unresolved UNKNOWN outcome degrades
   the session; ALL submissions are refused until reconcile() is clean.
4. **Kill-switch gate** — an active switch refuses the order BEFORE
   the venue is reached (central risk controls stay broker-agnostic).
5. **Risk gate** — a non-approved RiskDecision refuses the order.
   Both gates are INJECTABLE callables: the runtime's
   ``KillSwitchManager``/``RiskGate`` wire in at integration time
   (Phase M2); a session constructed WITHOUT them refuses everything
   (fail-closed default — no gate, no trading).
6. **Idempotency** — a journaled client_order_id returns the stored
   outcome (the ack is replayed EXACTLY); the SAME key with a
   DIFFERENT request is refused (key reuse is an integrity signal,
   never a silent replacement).
7. **Capability + precision pre-checks** — unsupported kinds/TIFs/
   SL-TP shapes/unaligned lot sizes never reach the venue.
8. **Bounded retry** — only CONNECTIVITY/TIMEOUT/RATE_LIMIT are
   retried (deterministic backoff via injectable sleeper); after the
   last attempt the typed error propagates and nothing is journaled
   as submitted.
9. **UNKNOWN journaling** — an ambiguous outcome is journaled UNKNOWN
   and degrades the session (reconcile before ANY new submission).

Persistence: an append-only JSON journal (atomic tmp+rename writes,
per-record digests verified on load) carries order outcomes across
restarts — duplicate protection and recovery state survive process
boundaries. The journal stores NO credential material (account id
only) and its integrity is verified before any order is accepted from
it (tamper-evident, fail-closed — mirrors the runtime state-store
discipline).
"""

import hashlib
import itertools
import json
import os
import time as _time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.brokers.capabilities import (
    BrokerCapabilities,
    ExecutionMode,
    SlTpSemantics,
)
from data_engine.brokers.errors import (
    BrokerErrorCategory,
    BrokerExecutionError,
    OrderRefusedError,
    RETRYABLE_CATEGORIES,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import (
    ExpectedOrderState,
    OrderAck,
    OrderRequest,
    VenueFill,
    VenueOrderStatus,
    VenueReconciliationReport,
)
from data_engine.brokers.redaction import BrokerCredential, CredentialError

#: Journal schema stamp (bump on incompatible journal format changes).
BROKER_SESSION_JOURNAL_SCHEMA = "broker-session-journal/1.0.0"

#: Unique-tmp counter (F-03): journal writes target process-unique
#: temporary names — two writers can never share a tmp inode.
_JOURNAL_TMP_COUNTER = itertools.count(1)


def _fsync_dir(path: Path) -> None:
    """Directory fsync (F-08): after ``os.replace`` the new journal
    NAME is not durable on all filesystems until the parent directory
    entry is synced (mirrors the runtime state-store discipline)."""
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)



class SessionJournalError(RuntimeError):
    """Raised on journal integrity/persistence failures (fail closed)."""


class RiskDecision(BaseModel):
    """The risk gate's verdict for ONE order (injectable gate result)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    reason: str = ""
    failed_checks: Tuple[str, ...] = ()

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        return v if isinstance(v, str) else ""


class KillSwitchState(BaseModel):
    """The kill-switch gate's current state (injectable gate result)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    active: bool
    reason: str = ""
    scope: str = ""


class RetryPolicy(BaseModel):
    """Bounded deterministic backoff for retryable venue errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    backoff_factor: float = 2.0

    @field_validator("max_attempts")
    @classmethod
    def _validate_attempts(cls, v: int) -> int:
        if v is None or v < 1:
            raise ValueError("max_attempts must be >= 1")
        return v

    @field_validator("base_delay_seconds")
    @classmethod
    def _validate_base(cls, v: float) -> float:
        if v is None or v < 0:
            raise ValueError("base_delay_seconds must be >= 0")
        return float(v)

    @field_validator("backoff_factor")
    @classmethod
    def _validate_factor(cls, v: float) -> float:
        if v is None or v < 1.0:
            raise ValueError("backoff_factor must be >= 1")
        return float(v)

    def delay_for(self, attempt: int) -> float:
        """Delay BEFORE retry ``attempt`` (0-based): base * factor^attempt."""
        return self.base_delay_seconds * (self.backoff_factor ** attempt)


class JournalRecord(BaseModel):
    """One journal entry (append-only; latest non-refused record per
    order is the session's authoritative last-known state)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_type: str                 # ORDER_ACK | ORDER_REFUSED | VENUE_SYNC
    broker_id: str
    account_id: str
    client_order_id: str
    request_digest: str
    status: Optional[VenueOrderStatus] = None
    venue_order_id: Optional[str] = None
    reason_code: Optional[str] = None
    filled_quantity: Decimal = Decimal("0")
    recorded_at: datetime
    record_digest: str
    ack_payload: Optional[Dict[str, Any]] = None  # exact replayable ack

    @field_validator("entry_type")
    @classmethod
    def _validate_entry_type(cls, v: str) -> str:
        if v not in ("ORDER_ACK", "ORDER_REFUSED", "VENUE_SYNC"):
            raise ValueError(f"unknown journal entry_type {v!r}")
        return v

    @field_validator("broker_id", "account_id", "client_order_id", "request_digest",
                     "record_digest")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("journal identifiers must be non-empty strings")
        return v

    def replay_ack(self) -> OrderAck:
        """Reconstruct the EXACT ack this record captured."""
        if self.ack_payload is None:
            raise SessionJournalError(
                f"journal record {self.client_order_id!r} carries no ack "
                "payload to replay"
            )
        return OrderAck.model_validate(self.ack_payload)


def _canonical_digest(payload: Mapping[str, object]) -> str:
    """Stable sha256 over a JSON-canonicalized mapping."""
    serialized = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _request_digest(request: OrderRequest) -> str:
    return _canonical_digest(dict(request.request_digest_fields()))


def _record_digest(
    *,
    entry_type: str,
    broker_id: str,
    account_id: str,
    client_order_id: str,
    request_digest: str,
    status: Optional[str],
    venue_order_id: Optional[str],
    reason_code: Optional[str],
    filled_quantity: Decimal,
    recorded_at: datetime,
    ack_payload: Optional[Dict[str, Any]],
) -> str:
    return _canonical_digest(
        {
            "entry_type": entry_type,
            "broker_id": broker_id,
            "account_id": account_id,
            "client_order_id": client_order_id,
            "request_digest": request_digest,
            "status": status,
            "venue_order_id": venue_order_id,
            "reason_code": reason_code,
            "filled_quantity": str(filled_quantity),
            "recorded_at": recorded_at.isoformat(),
            "ack_payload": ack_payload,
        }
    )


def _make_record(
    *,
    entry_type: str,
    broker_id: str,
    account_id: str,
    client_order_id: str,
    request_digest: str,
    recorded_at: datetime,
    status: Optional[VenueOrderStatus] = None,
    venue_order_id: Optional[str] = None,
    reason_code: Optional[str] = None,
    filled_quantity: Decimal = Decimal("0"),
    ack_payload: Optional[Dict[str, Any]] = None,
) -> JournalRecord:
    """Construct ONE journal record with its digest (single timestamp
    use — a stepping clock must never desynchronize the digest)."""
    digest = _record_digest(
        entry_type=entry_type,
        broker_id=broker_id,
        account_id=account_id,
        client_order_id=client_order_id,
        request_digest=request_digest,
        status=status.value if status is not None else None,
        venue_order_id=venue_order_id,
        reason_code=reason_code,
        filled_quantity=filled_quantity,
        recorded_at=recorded_at,
        ack_payload=ack_payload,
    )
    return JournalRecord(
        entry_type=entry_type,
        broker_id=broker_id,
        account_id=account_id,
        client_order_id=client_order_id,
        request_digest=request_digest,
        status=status,
        venue_order_id=venue_order_id,
        reason_code=reason_code,
        filled_quantity=filled_quantity,
        recorded_at=recorded_at,
        record_digest=digest,
        ack_payload=ack_payload,
    )


class BrokerSession:
    """The guarded per-(broker, account) execution session.

    Parameters
    ----------
    adapter:
        A :class:`BrokerAdapter` (mock in this phase; REAL execution-mode
        adapters are refused — live trading is NOT AUTHORIZED).
    account_id:
        The ONE account this session serves (isolation key).
    journal_path:
        JSON journal file (created atomically; loaded and verified at
        construction — restart recovery).
    risk_decision_fn / kill_switch_fn:
        The injectable central gates. Absent gates REFUSE all orders
        (fail-closed default — no gate, no trading).
    clock:
        REQUIRED injectable clock (journal timestamps — determinism).
    """

    def __init__(
        self,
        adapter: BrokerAdapter,
        *,
        account_id: str,
        journal_path: Path,
        risk_decision_fn: Optional[Callable[[OrderRequest], RiskDecision]] = None,
        kill_switch_fn: Optional[Callable[[], KillSwitchState]] = None,
        retry_policy: Optional[RetryPolicy] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(adapter, BrokerAdapter):
            raise SessionJournalError("session requires a BrokerAdapter instance")
        caps = adapter.capabilities
        if caps.execution_mode is not ExecutionMode.MOCK_DETERMINISTIC:
            raise SessionJournalError(
                "REAL execution-mode adapters are not constructible against a "
                "session in this phase — live trading is NOT AUTHORIZED "
                "(operator authorization protocol required first)"
            )
        if not isinstance(account_id, str) or not account_id.strip():
            raise SessionJournalError("account_id must be a non-empty string")
        if not callable(clock):
            raise SessionJournalError(
                "an injectable clock callable is MANDATORY (determinism)"
            )
        self._adapter = adapter
        self._account_id = account_id.strip()
        self._journal_path = Path(journal_path)
        self._risk_fn = risk_decision_fn
        self._kill_switch_fn = kill_switch_fn
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper if sleeper is not None else _time.sleep
        self._clock = clock
        self._credential: Optional[BrokerCredential] = None
        self._degraded = False
        self._records: List[JournalRecord] = []
        self._sleep_log: List[float] = []
        self._load_journal()

    # ------------------------------------------------------------------
    # Identity + observability
    # ------------------------------------------------------------------
    @property
    def broker_id(self) -> str:
        return self._adapter.broker_id

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._adapter.capabilities

    @property
    def degraded(self) -> bool:
        """True while an UNKNOWN outcome awaits reconciliation."""
        return self._degraded

    @property
    def sleep_log(self) -> Tuple[float, ...]:
        """Deterministic-backoff evidence (injected sleeper recordings)."""
        return tuple(self._sleep_log)

    @property
    def adapter(self) -> BrokerAdapter:
        """The bound adapter (mock surface for failure injection in tests)."""
        return self._adapter

    def journal_records(self) -> Tuple[JournalRecord, ...]:
        return tuple(self._records)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self, credential: BrokerCredential) -> None:
        if not isinstance(credential, BrokerCredential):
            raise CredentialError("connect requires a BrokerCredential holder")
        if not credential.matches_account(self._account_id):
            raise CredentialError(
                f"credential is for account {credential.account_id!r} but this "
                f"session serves {self._account_id!r} (isolation refusal)"
            )
        self._adapter.connect(credential)
        self._credential = credential

    def disconnect(self) -> None:
        self._adapter.disconnect()

    def health(self):
        return self._adapter.health()

    def reconnect(self) -> None:
        """Re-connect with the SAME credential (fail-closed if absent)."""
        if self._credential is None:
            raise OrderRefusedError(
                "reconnect refused: this session was never connected "
                "(no credential handle held)",
                broker_id=self.broker_id,
                reason_code="NEVER_CONNECTED",
            )
        self._adapter.connect(self._credential)

    # ------------------------------------------------------------------
    # Submission pipeline (fail-closed gates in fixed order)
    # ------------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> OrderAck:
        # 1. account isolation
        if request.account_id != self._account_id:
            self._journal_refusal(request, "ACCOUNT_ISOLATION")
            raise OrderRefusedError(
                f"request names account {request.account_id!r} but this "
                f"session serves {self._account_id!r}",
                broker_id=self.broker_id,
                reason_code="ACCOUNT_ISOLATION",
            )
        # 2. health gate
        if self.health().value != "CONNECTED":
            self._journal_refusal(request, "ADAPTER_NOT_CONNECTED")
            raise OrderRefusedError(
                f"adapter is {self.health().value} — submissions refused "
                "(reconnect first)",
                broker_id=self.broker_id,
                reason_code="ADAPTER_NOT_CONNECTED",
            )
        # 3. reconciliation gate
        if self._degraded:
            self._journal_refusal(request, "RECONCILIATION_REQUIRED")
            raise OrderRefusedError(
                "session is DEGRADED (UNKNOWN order outcome on record) — "
                "reconcile() must succeed before ANY new submission",
                broker_id=self.broker_id,
                reason_code="RECONCILIATION_REQUIRED",
            )
        # 4. kill-switch gate (central, broker-agnostic)
        if self._kill_switch_fn is None:
            self._journal_refusal(request, "GATE_MISSING_KILL_SWITCH")
            raise OrderRefusedError(
                "no kill-switch gate is wired into this session — fail-closed "
                "default: no gate, no trading",
                broker_id=self.broker_id,
                reason_code="GATE_MISSING_KILL_SWITCH",
            )
        switch = self._kill_switch_fn()
        if switch.active:
            self._journal_refusal(request, "KILL_SWITCH_ACTIVE")
            raise OrderRefusedError(
                f"kill switch ACTIVE (scope={switch.scope or 'n/a'}): "
                f"{switch.reason or 'no reason recorded'}",
                broker_id=self.broker_id,
                reason_code="KILL_SWITCH_ACTIVE",
            )
        # 5. risk gate (central, broker-agnostic)
        if self._risk_fn is None:
            self._journal_refusal(request, "GATE_MISSING_RISK")
            raise OrderRefusedError(
                "no risk gate is wired into this session — fail-closed "
                "default: no gate, no trading",
                broker_id=self.broker_id,
                reason_code="GATE_MISSING_RISK",
            )
        decision = self._risk_fn(request)
        if not decision.approved:
            self._journal_refusal(request, "RISK_REFUSED")
            raise OrderRefusedError(
                f"risk gate REFUSED: {decision.reason or 'no reason recorded'}"
                + (f" (failed: {', '.join(decision.failed_checks)})"
                   if decision.failed_checks else ""),
                broker_id=self.broker_id,
                reason_code="RISK_REFUSED",
            )
        # 6. idempotency (journal is the authority)
        request_digest = _request_digest(request)
        prior = self._latest_tracked(request.client_order_id)
        if prior is not None:
            if prior.request_digest != request_digest:
                self._journal_refusal(request, "IDEMPOTENCY_KEY_REUSE")
                raise OrderRefusedError(
                    f"client_order_id {request.client_order_id!r} was already "
                    "used for a DIFFERENT request — key reuse is refused, "
                    "never silently replaced",
                    broker_id=self.broker_id,
                    reason_code="IDEMPOTENCY_KEY_REUSE",
                )
            return prior.replay_ack()
        # 7. capability + precision pre-checks (venue never sees bad shapes)
        self._pre_venue_checks(request)
        # 8. bounded retry against the venue
        ack = self._submit_with_retry(request)
        # 9. journal the outcome
        self._journal_ack(request, ack)
        return ack

    def _pre_venue_checks(self, request: OrderRequest) -> None:
        caps = self._adapter.capabilities
        if not caps.supports_order_kind(request.order_kind):
            self._journal_refusal(request, "UNSUPPORTED_ORDER_KIND")
            raise OrderRefusedError(
                f"order kind {request.order_kind.value} is not supported by "
                f"{self.broker_id} (supported: "
                f"{[k.value for k in caps.order_kinds]}) — {caps.venue_notes}",
                broker_id=self.broker_id,
                reason_code="UNSUPPORTED_ORDER_KIND",
            )
        if not caps.supports_time_in_force(request.time_in_force):
            self._journal_refusal(request, "UNSUPPORTED_TIME_IN_FORCE")
            raise OrderRefusedError(
                f"time-in-force {request.time_in_force.value} is not "
                f"supported by {self.broker_id} "
                f"(supported: {[t.value for t in caps.time_in_force]})",
                broker_id=self.broker_id,
                reason_code="UNSUPPORTED_TIME_IN_FORCE",
            )
        if (request.stop_loss is not None or request.take_profit is not None) and \
                caps.sl_tp is not SlTpSemantics.ATTACHED:
            self._journal_refusal(request, "SLTP_SEMANTICS_MISMATCH")
            raise OrderRefusedError(
                f"{self.broker_id} does not support ATTACHED stop-loss/"
                f"take-profit (semantics: {caps.sl_tp.value}) — submit stops "
                "as separate orders per the venue's native mechanism",
                broker_id=self.broker_id,
                reason_code="SLTP_SEMANTICS_MISMATCH",
            )
        if request.reduce_only and not caps.supports_reduce_only:
            self._journal_refusal(request, "REDUCE_ONLY_UNSUPPORTED")
            raise OrderRefusedError(
                f"{self.broker_id} does not support reduce-only orders",
                broker_id=self.broker_id,
                reason_code="REDUCE_ONLY_UNSUPPORTED",
            )
        try:
            spec = self._adapter.instrument_spec(request.symbol)
        except BrokerExecutionError as exc:
            self._journal_refusal(request, "UNKNOWN_SYMBOL")
            raise OrderRefusedError(
                f"symbol {request.symbol!r} is not served by {self.broker_id} — "
                "never assume a symbol exists at a venue",
                broker_id=self.broker_id,
                reason_code="UNKNOWN_SYMBOL",
            ) from exc
        problems = spec.order_problems(request.quantity, request.price)
        if problems:
            self._journal_refusal(request, "PRECISION_INVALID")
            raise OrderRefusedError(
                f"order violates {self.broker_id} instrument rules for "
                f"{request.symbol}: " + "; ".join(problems),
                broker_id=self.broker_id,
                reason_code="PRECISION_INVALID",
            )

    def _submit_with_retry(self, request: OrderRequest) -> OrderAck:
        policy = self._retry_policy
        last_error: Optional[BrokerExecutionError] = None
        for attempt in range(policy.max_attempts):
            if attempt > 0:
                delay = policy.delay_for(attempt - 1)
                self._sleep_log.append(delay)
                self._sleeper(delay)
            try:
                return self._adapter.submit_order(request)
            except BrokerExecutionError as exc:
                if exc.category is BrokerErrorCategory.UNKNOWN_STATE:
                    # Ambiguous: the venue MAY hold a live order. Journal
                    # UNKNOWN, degrade, re-raise — never retry blindly.
                    self._journal_unknown(request)
                    self._degraded = True
                    raise
                if exc.category not in RETRYABLE_CATEGORIES:
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------
    # Order queries + explicit venue-truth sync
    # ------------------------------------------------------------------
    def order_status(self, client_order_id: str) -> OrderAck:
        ack = self._adapter.order_status(client_order_id)
        self._journal_sync(ack)
        return ack

    def order_fills(self, client_order_id: str) -> Tuple[VenueFill, ...]:
        fills = self._adapter.order_fills(client_order_id)
        ack = self._adapter.order_status(client_order_id)
        self._journal_sync(
            ack, filled_quantity=sum(
                (f.quantity for f in fills), Decimal("0")
            )
        )
        return fills

    def cancel_order(self, client_order_id: str) -> OrderAck:
        ack = self._adapter.cancel_order(client_order_id)
        self._journal_sync(ack)
        return ack

    def sync_order_state(self, client_order_id: str) -> OrderAck:
        """EXPLICIT accept-venue-truth action after investigating a
        mismatch (ledgered as VENUE_SYNC — never a silent repair).

        Pulls BOTH the venue status and the venue fills so the journal's
        last-known state matches the execution authority exactly."""
        fills = self._adapter.order_fills(client_order_id)
        ack = self._adapter.order_status(client_order_id)
        self._journal_sync(
            ack,
            filled_quantity=sum((f.quantity for f in fills), Decimal("0")),
        )
        return ack

    def adopt_venue_order(self, request: OrderRequest) -> OrderAck:
        """EXPLICIT lost-ack re-adoption (reconciliation recovery).

        The journal adopts an order the venue verifiably holds after
        the CALLER cross-checked it against its own authoritative
        books (the runtime venue seam cross-checks the OMS order
        parameters before calling this). Ledgered as ORDER_ACK — the
        auditable accept-venue-truth action for a submission whose ack
        was lost.

        This is NOT a trading action: the order already exists at the
        venue (the adapter's idempotent truth is read, never
        re-submitted), no gate is bypassed (the original submission
        passed them; the runtime's fill-time enforcement continues to
        govern the order), and the account-isolation check applies.
        The session itself never fabricates adoption."""
        if request.account_id != self._account_id:
            self._journal_refusal(request, "ACCOUNT_ISOLATION")
            raise OrderRefusedError(
                f"request names account {request.account_id!r} but this "
                f"session serves {self._account_id!r}",
                broker_id=self.broker_id,
                reason_code="ACCOUNT_ISOLATION",
            )
        ack = self._adapter.order_status(request.client_order_id)
        if ack.status is VenueOrderStatus.UNKNOWN:
            self._journal_refusal(request, "ADOPTION_VENUE_TRUTH_UNKNOWN")
            raise OrderRefusedError(
                f"venue truth for {request.client_order_id!r} is UNKNOWN — "
                "adoption refuses ambiguous truth (fail closed)",
                broker_id=self.broker_id,
                reason_code="ADOPTION_VENUE_TRUTH_UNKNOWN",
            )
        self._journal_ack(request, ack)
        # Adopt the venue's fill truth as well (status + quantities).
        return self.sync_order_state(request.client_order_id)

    def positions(self):
        return self._adapter.positions()

    def balances(self):
        return self._adapter.balances()

    def account_info(self):
        return self._adapter.account_info()

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    def reconcile(self) -> VenueReconciliationReport:
        """Journal expectations vs venue truth; a clean report clears
        the degraded state (and applies UNKNOWN resolutions)."""
        expected: List[ExpectedOrderState] = []
        for record in self._tracked_records():
            expected.append(ExpectedOrderState(
                client_order_id=record.client_order_id,
                status=record.status or VenueOrderStatus.UNKNOWN,
                filled_quantity=record.filled_quantity,
            ))
        report = self._adapter.reconcile(expected)
        if report.ok:
            for resolution in report.resolved:
                prior = self._latest_tracked(resolution.client_order_id)
                if prior is None or prior.status is not VenueOrderStatus.UNKNOWN:
                    continue
                resolved_ack = prior.replay_ack().model_copy(
                    update={
                        "status": resolution.status,
                        "venue_order_id": prior.venue_order_id
                        or prior.replay_ack().venue_order_id,
                    }
                )
                self._journal_sync(
                    resolved_ack, filled_quantity=resolution.filled_quantity
                )
            self._degraded = False
        else:
            # Mandate §32 discipline: ANY mismatch stops new orders until
            # resolved (sync_order_state + a clean re-reconciliation).
            self._degraded = True
        return report

    # ------------------------------------------------------------------
    # Journal internals
    # ------------------------------------------------------------------
    def _tracked_records(self) -> List[JournalRecord]:
        """Latest non-refused record per order (venue-submitted only)."""
        latest: Dict[str, JournalRecord] = {}
        for record in self._records:
            if record.entry_type != "ORDER_REFUSED":
                latest[record.client_order_id] = record
        return [latest[cid] for cid in sorted(latest)]

    def _latest_tracked(self, client_order_id: str) -> Optional[JournalRecord]:
        for record in reversed(self._records):
            if record.client_order_id == client_order_id and \
                    record.entry_type != "ORDER_REFUSED":
                return record
        return None

    def _append_record(self, record: JournalRecord) -> None:
        self._records.append(record)
        self._write_journal()

    def _journal_ack(self, request: OrderRequest, ack: OrderAck) -> None:
        self._append_record(_make_record(
            entry_type="ORDER_ACK",
            broker_id=self.broker_id,
            account_id=self._account_id,
            client_order_id=request.client_order_id,
            request_digest=_request_digest(request),
            recorded_at=self._clock(),
            status=ack.status,
            venue_order_id=ack.venue_order_id,
            reason_code=ack.venue_code,
            filled_quantity=Decimal("0"),
            ack_payload=ack.model_dump(mode="json"),
        ))

    def _journal_unknown(self, request: OrderRequest) -> None:
        """Journal an UNKNOWN outcome with a replayable placeholder ack
        (status UNKNOWN; reconciled later from venue truth)."""
        now = self._clock()
        unknown_ack = OrderAck(
            client_order_id=request.client_order_id,
            venue_order_id="unknown",
            account_id=request.account_id,
            broker_id=self.broker_id,
            symbol=request.symbol,
            side=request.side,
            order_kind=request.order_kind,
            quantity=request.quantity,
            status=VenueOrderStatus.UNKNOWN,
            submitted_at=now,
        )
        self._append_record(_make_record(
            entry_type="ORDER_ACK",
            broker_id=self.broker_id,
            account_id=self._account_id,
            client_order_id=request.client_order_id,
            request_digest=_request_digest(request),
            recorded_at=now,
            status=VenueOrderStatus.UNKNOWN,
            venue_order_id=None,
            reason_code="UNKNOWN_STATE",
            filled_quantity=Decimal("0"),
            ack_payload=unknown_ack.model_dump(mode="json"),
        ))

    def _journal_refusal(self, request: OrderRequest, reason_code: str) -> None:
        self._append_record(_make_record(
            entry_type="ORDER_REFUSED",
            broker_id=self.broker_id,
            account_id=self._account_id,
            client_order_id=request.client_order_id,
            request_digest=_request_digest(request),
            recorded_at=self._clock(),
            status=None,
            venue_order_id=None,
            reason_code=reason_code,
            filled_quantity=Decimal("0"),
            ack_payload=None,
        ))

    def _journal_sync(
        self, ack: OrderAck, filled_quantity: Optional[Decimal] = None
    ) -> None:
        prior = self._latest_tracked(ack.client_order_id)
        if prior is None:
            return  # nothing tracked to sync (venue state we never owned)
        filled = (
            filled_quantity if filled_quantity is not None
            else prior.filled_quantity
        )
        self._append_record(_make_record(
            entry_type="VENUE_SYNC",
            broker_id=self.broker_id,
            account_id=self._account_id,
            client_order_id=ack.client_order_id,
            request_digest=prior.request_digest,
            recorded_at=self._clock(),
            status=ack.status,
            venue_order_id=ack.venue_order_id,
            reason_code=None,
            filled_quantity=filled,
            ack_payload=ack.model_dump(mode="json"),
        ))

    # ------------------------------------------------------------------
    # Persistence (atomic writes, verified loads)
    # ------------------------------------------------------------------
    def _journal_document(self) -> dict:
        return {
            "schema": BROKER_SESSION_JOURNAL_SCHEMA,
            "broker_id": self.broker_id,
            "account_id": self._account_id,
            "records": [r.model_dump(mode="json") for r in self._records],
        }

    def _write_journal(self) -> None:
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        # F-03: UNIQUE tmp name (pid + counter) — two writers can
        # never interleave on the same tmp inode.
        tmp = self._journal_path.parent / (
            f".{self._journal_path.name}.{os.getpid()}."
            f"{next(_JOURNAL_TMP_COUNTER)}.tmp"
        )
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._journal_document(), fh, indent=1,
                          sort_keys=True)
                # F-08: fsync the FILE before replace — power loss
                # can no longer lose the rename (the venue journal is
                # the durable venue-truth record).
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._journal_path)
            _fsync_dir(self._journal_path.parent)
        except OSError as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise SessionJournalError(
                f"journal write failed ({self._journal_path}): {exc!r} — "
                "fail closed (no best-effort persistence)"
            ) from exc

    def _load_journal(self) -> None:
        if not self._journal_path.exists():
            return
        try:
            with open(self._journal_path, "r", encoding="utf-8") as fh:
                document = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise SessionJournalError(
                f"journal unreadable ({self._journal_path}): {exc!r} — "
                "fail closed"
            ) from exc
        if document.get("schema") != BROKER_SESSION_JOURNAL_SCHEMA:
            raise SessionJournalError(
                f"journal schema {document.get('schema')!r} != "
                f"{BROKER_SESSION_JOURNAL_SCHEMA!r} — refusing"
            )
        if document.get("broker_id") != self.broker_id or \
                document.get("account_id") != self._account_id:
            raise SessionJournalError(
                "journal belongs to a DIFFERENT (broker, account) session — "
                "refusing to adopt it (isolation)"
            )
        records: List[JournalRecord] = []
        for raw in document.get("records", []):
            record = JournalRecord.model_validate(raw)
            expected = _record_digest(
                entry_type=record.entry_type,
                broker_id=record.broker_id,
                account_id=record.account_id,
                client_order_id=record.client_order_id,
                request_digest=record.request_digest,
                status=record.status.value if record.status else None,
                venue_order_id=record.venue_order_id,
                reason_code=record.reason_code,
                filled_quantity=record.filled_quantity,
                recorded_at=record.recorded_at,
                ack_payload=record.ack_payload,
            )
            if expected != record.record_digest:
                raise SessionJournalError(
                    f"journal record digest mismatch for order "
                    f"{record.client_order_id!r} — tamper-evident journal "
                    "refuses to load (fail closed)"
                )
            records.append(record)
        self._records = records
        if any(
            r.entry_type == "ORDER_ACK" and r.status is VenueOrderStatus.UNKNOWN
            for r in self._records
        ):
            # Restart inside a degraded state: an unresolved UNKNOWN
            # persists across the process boundary (fail-closed recovery).
            self._degraded = True


__all__ = [
    "BROKER_SESSION_JOURNAL_SCHEMA",
    "SessionJournalError",
    "RiskDecision",
    "KillSwitchState",
    "RetryPolicy",
    "JournalRecord",
    "BrokerSession",
]
