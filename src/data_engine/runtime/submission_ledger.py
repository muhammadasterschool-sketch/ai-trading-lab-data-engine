"""Durable submission-rate ledger + submission-spacing governor.

Milestone A B1 + B2 (prompt v3.0 Part 5; findings F-01, F-02, F-19 in
artifacts/stage-a/02-FINDINGS-REGISTER.md).

PROBLEM BEING FIXED
-------------------
The runtime's submission-rate accounting was an in-memory list
(``_submission_times``) that is NOT part of ``EXECUTION_STATE_FIELDS``:
a restart wiped the rate budget (fail-open direction), the capacity
check and the record were separate steps with no atomicity, and
nothing prevented two processes from each consuming a full budget.

PROTOCOL (reserve → submit → finalize)
--------------------------------------
1. ``reserve(client_order_id)`` — the ONLY way to consume submission
   capacity. Under an exclusive ``flock`` on the ACTUAL filesystem:
   reload ledger → wall-clock regression check → spacing check →
   window-capacity check → durable append (atomic tmp+replace, fsync
   file AND directory) → release. A refused reservation writes NO
   record. A successful reservation carries the durable order
   identity (the OMS order id) + reservation id.
2. ``mark_submitted`` — the venue call happened (or is happening);
   the record moves RESERVED → SUBMITTED.
3. ``finalize(outcome)`` — definitive outcome. Outcomes:
   ``ACKNOWLEDGED`` / ``VENUE_REFUSED`` / ``VENUE_UNCERTAIN`` /
   ``EXCEPTION_NO_ACK`` / ``OMS_TRANSITION_FAILED``. Every one of
   these CONSUMED a submission attempt — all count toward the window
   (conservative: the venue may have seen the request).
4. ``abandon(reason)`` — pre-venue wiring failure after reserve (the
   broker was never called). ABANDONED records do NOT count toward
   capacity; they are retained for audit only.

CONSERVATIVE COUNTING RULE
--------------------------
A record counts toward window capacity iff its state is RESERVED or
SUBMITTED, or it is FINALIZED with an outcome other than
``PRE_VENUE_ABANDONED``. A crash anywhere between reserve and outcome
therefore leaves the slot CONSUMED (fail-closed), never released.

CRASH RECOVERY
--------------
``recover(journal_client_order_ids)`` reconciles outstanding
RESERVED records against venue-journal acks: journaled → SUBMITTED
(durable, auditable transition note); not journaled → PRESERVED as
RESERVED (consumed — "never infer failure from absence"). A restart
never silently releases risk capacity.

OWNER-RATIFIED PAPER DEFAULTS (Part 3)
--------------------------------------
minimum 1 second between submissions; max 5 submissions per 60
seconds; max 10 open orders (open-order cap enforced by the runtime
risk gate; carried here for policy documentation). These are PAPER
MODE ONLY and must be re-ratified before any future live mode.

PLATFORM NOTE: locking uses ``fcntl.flock`` (POSIX). On platforms
without ``fcntl`` the ledger REFUSES to construct (fail closed);
the Stage E Windows package documents the platform story.

All venues used with this ledger are paper/mock. LIVE TRADING
REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable, List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

__all__ = [
    "CapacityRefused",
    "LedgerRecord",
    "PRE_VENUE_OUTCOME",
    "RecoveryReport",
    "Reservation",
    "ReservationState",
    "SubmissionLedger",
    "SubmissionLedgerError",
    "SubmissionPolicy",
    "WallClockRegression",
]

#: Ledger document schema stamp (fail-closed on mismatch).
SUBMISSION_LEDGER_SCHEMA = "atl.submission-ledger/1.0.0"

#: Outcome recorded for pre-venue abandons — the ONLY non-counting
#: finalized outcome (the broker was never called).
PRE_VENUE_OUTCOME = "PRE_VENUE_ABANDONED"

#: Legal finalize outcomes (each represents a CONSUMED attempt).
FINALIZE_OUTCOMES = frozenset({
    "ACKNOWLEDGED",
    "VENUE_REFUSED",
    "VENUE_UNCERTAIN",
    "EXCEPTION_NO_ACK",
    "OMS_TRANSITION_FAILED",
})


class SubmissionLedgerError(RuntimeError):
    """Fail-closed base class for every ledger failure."""


class WallClockRegression(SubmissionLedgerError):
    """The wall clock moved BACKWARDS beyond tolerance — the spacing
    model cannot be evaluated safely; refusal is fail-closed."""


class CapacityRefused(SubmissionLedgerError):
    """Submission capacity/spacing refusal (no record is written).

    ``reason_code`` ∈ {"WINDOW_CAPACITY", "SPACING"}.
    """

    def __init__(
        self, message: str, *, reason_code: str,
        retry_after_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.retry_after_seconds = retry_after_seconds


class SubmissionPolicy(BaseModel):
    """Owner-ratified PAPER-mode submission policy (Part 3).

    Defaults: min 1s between submissions, max 5 per 60s, max 10 open
    orders. PAPER MODE ONLY — must be re-ratified before any future
    live mode.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_orders_per_window: int = 5
    window_seconds: float = 60.0
    min_spacing_seconds: float = 1.0
    max_open_orders: int = 10
    #: Wall clock may jitter; a regression beyond this tolerance is a
    #: fail-closed refusal (never a silent reset of the spacing model).
    wall_clock_regression_tolerance_seconds: float = 2.0

    @field_validator(
        "max_orders_per_window", "max_open_orders",
    )
    @classmethod
    def _validate_counts(cls, v: int) -> int:
        if v is None or v < 1:
            raise ValueError("submission counts must be >= 1")
        return v

    @field_validator("window_seconds")
    @classmethod
    def _validate_window(cls, v: float) -> float:
        if v is None or v <= 0:
            raise ValueError("window_seconds must be positive")
        return float(v)

    @field_validator("min_spacing_seconds")
    @classmethod
    def _validate_spacing(cls, v: float) -> float:
        if v is None or v < 0:
            raise ValueError("min_spacing_seconds must be >= 0")
        return float(v)

    @field_validator(
        "wall_clock_regression_tolerance_seconds",
    )
    @classmethod
    def _validate_tolerance(cls, v: float) -> float:
        if v is None or v < 0:
            raise ValueError("regression tolerance must be >= 0")
        return float(v)


class ReservationState(str, Enum):
    RESERVED = "RESERVED"
    SUBMITTED = "SUBMITTED"
    FINALIZED = "FINALIZED"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class Reservation:
    """Handle returned by a successful reservation."""

    reservation_id: str
    client_order_id: str
    created_at_wall: datetime
    state: ReservationState


@dataclass(frozen=True)
class LedgerRecord:
    """Read-only view of one persisted ledger record."""

    reservation_id: str
    client_order_id: str
    created_at_wall: datetime
    created_at_governed: Optional[datetime]
    state: ReservationState
    outcome: Optional[str]
    finalized_at: Optional[datetime]
    transitions: List[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RecoveryReport:
    """Auditable summary of one recovery pass."""

    reconciled_submitted: int
    preserved_reserved: int
    total_records: int


def _require_aware(dt: datetime, what: str) -> datetime:
    if dt.tzinfo is None:
        raise SubmissionLedgerError(
            f"{what} must be timezone-aware (fail closed)"
        )
    return dt


def _parse_ts(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class SubmissionLedger:
    """Durable, flock-protected submission ledger (see module doc)."""

    def __init__(
        self,
        path: Path,
        *,
        policy: Optional[SubmissionPolicy] = None,
        wall_clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not isinstance(path, Path):
            path = Path(path)
        if policy is not None and not isinstance(
            policy, SubmissionPolicy
        ):
            raise SubmissionLedgerError(
                "policy must be a SubmissionPolicy (fail closed)"
            )
        try:
            import fcntl  # noqa: F401  (platform gate)
        except ImportError as exc:  # pragma: no cover - non-POSIX
            raise SubmissionLedgerError(
                "SubmissionLedger requires POSIX flock support "
                "(fail closed on this platform; see Stage E notes)"
            ) from exc
        self._path = path
        self._lock_path = path.with_name(path.name + ".lock")
        self._policy = policy or SubmissionPolicy()
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        if not callable(self._wall_clock):
            raise SubmissionLedgerError(
                "wall_clock must be callable (injectable for determinism)"
            )
        self._tmp_counter = 0
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Initialize / validate the document under the lock (fail
        # closed on corruption — never best-effort).
        with self._locked():
            doc = self._load()
            if not self._path.exists():
                self._save({"schema": SUBMISSION_LEDGER_SCHEMA,
                            "records": []})

    # -- locking ----------------------------------------------------------

    @property
    def path(self) -> Path:
        """The durable ledger location (public: the Stage C
        composition root cites it in readiness evidence)."""
        return self._path

    @property
    def policy(self) -> SubmissionPolicy:
        """The governed submission policy in force (B2)."""
        return self._policy

    @contextmanager
    def _locked(self):
        """Exclusive flock on ``<path>.lock`` — the actual filesystem,
        cross-process (B1: competing processes serialize here)."""
        fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    # -- persistence ------------------------------------------------------

    def _load(self) -> dict:
        """Load + validate. Caller holds the lock (or is __init__)."""
        if not self._path.exists():
            return {"schema": SUBMISSION_LEDGER_SCHEMA, "records": []}
        try:
            doc = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise SubmissionLedgerError(
                f"submission ledger corrupt at {self._path} "
                f"(fail closed): {exc}"
            ) from exc
        if not isinstance(doc, dict) or \
                doc.get("schema") != SUBMISSION_LEDGER_SCHEMA:
            raise SubmissionLedgerError(
                f"submission ledger at {self._path} has an unknown "
                f"schema (fail closed)"
            )
        if not isinstance(doc.get("records"), list):
            raise SubmissionLedgerError(
                "submission ledger records must be a list (fail closed)"
            )
        return doc

    def _save(self, doc: dict) -> None:
        """Atomic durable write: unique tmp + fsync file + replace +
        fsync directory. Caller holds the lock."""
        self._tmp_counter += 1
        tmp = self._path.with_name(
            f"{self._path.name}.tmp.{os.getpid()}.{self._tmp_counter}"
        )
        text = json.dumps(doc, sort_keys=True, indent=1)
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
            dirfd = os.open(self._path.parent, os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except OSError as exc:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise SubmissionLedgerError(
                f"durable submission-ledger write failed at "
                f"{self._path} (fail closed — the reservation is NOT "
                f"granted): {exc}"
            ) from exc

    # -- time -------------------------------------------------------------

    def _now(self, now: Optional[datetime] = None) -> datetime:
        dt = now if now is not None else self._wall_clock()
        return _require_aware(dt, "wall timestamp")

    # -- capacity model ---------------------------------------------------

    def _counts_toward_capacity(self, rec: dict) -> bool:
        """Conservative counting rule (see module docstring)."""
        state = rec.get("state")
        if state == ReservationState.ABANDONED.value:
            return False
        if state == ReservationState.FINALIZED.value:
            return rec.get("outcome") != PRE_VENUE_OUTCOME
        return True  # RESERVED / SUBMITTED

    def _capacity_view(
        self, doc: dict, now: datetime
    ) -> "tuple[int, Optional[datetime]]":
        window = timedelta(seconds=self._policy.window_seconds)
        count = 0
        last: Optional[datetime] = None
        for rec in doc["records"]:
            if not self._counts_toward_capacity(rec):
                continue
            created = _parse_ts(rec["created_at_wall"])
            if (now - created).total_seconds() <= window.total_seconds():
                count += 1
                if last is None or created > last:
                    last = created
        return count, last

    # -- protocol ---------------------------------------------------------

    def reserve(
        self,
        client_order_id: str,
        governed_ts: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> Reservation:
        """Atomically reserve one submission slot (B1).

        Raises CapacityRefused (NO record written) or
        WallClockRegression (fail closed). The broker call may only
        happen with the returned reservation in hand.
        """
        if not isinstance(client_order_id, str) or \
                not client_order_id.strip():
            raise SubmissionLedgerError(
                "client_order_id must be a non-empty string "
                "(durable order identity is mandatory)"
            )
        if governed_ts is not None:
            _require_aware(governed_ts, "governed timestamp")
        now = self._now(now)
        tol = self._policy.wall_clock_regression_tolerance_seconds
        with self._locked():
            doc = self._load()
            _count, last = self._capacity_view(doc, now)
            if last is not None:
                regression = (last - now).total_seconds()
                if regression > tol:
                    raise WallClockRegression(
                        f"wall clock regressed {regression:.1f}s behind "
                        f"the last durable submission at {last.isoformat()}"
                        f" — spacing model unevaluable (fail closed)"
                    )
                spacing = (now - last).total_seconds()
                if spacing < self._policy.min_spacing_seconds:
                    raise CapacityRefused(
                        f"submission spacing refused: last durable "
                        f"submission was {spacing:.3f}s ago "
                        f"(min {self._policy.min_spacing_seconds}s)",
                        reason_code="SPACING",
                        retry_after_seconds=(
                            self._policy.min_spacing_seconds - spacing
                        ),
                    )
            count, _last = self._capacity_view(doc, now)
            if count >= self._policy.max_orders_per_window:
                raise CapacityRefused(
                    f"submission capacity exhausted "
                    f"({self._policy.max_orders_per_window} per "
                    f"{self._policy.window_seconds}s)",
                    reason_code="WINDOW_CAPACITY",
                    retry_after_seconds=self._policy.window_seconds,
                )
            record = {
                "reservation_id": f"res-{uuid.uuid4().hex}",
                "client_order_id": client_order_id,
                "created_at_wall": now.isoformat(),
                "created_at_governed": (
                    governed_ts.isoformat()
                    if governed_ts is not None else None
                ),
                "state": ReservationState.RESERVED.value,
                "outcome": None,
                "finalized_at": None,
                "transitions": [{
                    "state": ReservationState.RESERVED.value,
                    "at": now.isoformat(),
                    "note": "reserved (capacity + spacing verified "
                            "under exclusive lock)",
                }],
            }
            doc["records"].append(record)
            self._save(doc)
        return Reservation(
            reservation_id=record["reservation_id"],
            client_order_id=client_order_id,
            created_at_wall=now,
            state=ReservationState.RESERVED,
        )

    def _transition(
        self,
        reservation_id: str,
        new_state: ReservationState,
        *,
        outcome: Optional[str] = None,
        note: str,
        now: Optional[datetime] = None,
    ) -> dict:
        if not isinstance(reservation_id, str) or \
                not reservation_id.strip():
            raise SubmissionLedgerError(
                "reservation_id must be non-empty (fail closed)"
            )
        now = self._now(now)
        with self._locked():
            doc = self._load()
            rec = None
            for candidate in doc["records"]:
                if candidate.get("reservation_id") == reservation_id:
                    rec = candidate
                    break
            if rec is None:
                raise SubmissionLedgerError(
                    f"reservation {reservation_id!r} not found in the "
                    f"durable ledger (fail closed — no silent release)"
                )
            current = ReservationState(rec["state"])
            if current in (ReservationState.FINALIZED,
                           ReservationState.ABANDONED):
                raise SubmissionLedgerError(
                    f"reservation {reservation_id!r} is already "
                    f"{current.value} — terminal states never "
                    f"transition (fail closed)"
                )
            rec["state"] = new_state.value
            if outcome is not None:
                rec["outcome"] = outcome
            if new_state is ReservationState.FINALIZED:
                rec["finalized_at"] = now.isoformat()
            rec.setdefault("transitions", []).append({
                "state": new_state.value,
                "at": now.isoformat(),
                "note": note,
            })
            self._save(doc)
            return rec

    def mark_submitted(
        self,
        reservation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        """RESERVED → SUBMITTED (the venue call happened)."""
        self._transition(
            reservation_id, ReservationState.SUBMITTED,
            note="venue submission dispatched (durable record)",
            now=now,
        )

    def finalize(
        self,
        reservation_id: str,
        outcome: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Definitive outcome — the attempt CONSUMED a slot (all
        finalize outcomes count toward capacity)."""
        if outcome not in FINALIZE_OUTCOMES:
            raise SubmissionLedgerError(
                f"unknown finalize outcome {outcome!r} (legal: "
                f"{sorted(FINALIZE_OUTCOMES)}; fail closed)"
            )
        self._transition(
            reservation_id, ReservationState.FINALIZED,
            outcome=outcome,
            note=f"finalized: {outcome} (slot consumed — conservative)",
            now=now,
        )

    def abandon(
        self,
        reservation_id: str,
        reason: str,
        now: Optional[datetime] = None,
    ) -> None:
        """Pre-venue wiring failure: the broker was NEVER called —
        the slot is released (ABANDONED, retained for audit only)."""
        if not isinstance(reason, str) or not reason.strip():
            raise SubmissionLedgerError("abandon reason is mandatory")
        self._transition(
            reservation_id, ReservationState.ABANDONED,
            outcome=PRE_VENUE_OUTCOME,
            note=f"abandoned pre-venue: {reason} (broker never called)",
            now=now,
        )

    # -- recovery + introspection ----------------------------------------

    def recover(
        self,
        journal_client_order_ids: Iterable[str] = (),
    ) -> RecoveryReport:
        """Conservative crash recovery (B1).

        Outstanding RESERVED records reconciled against venue-journal
        acks: journaled → SUBMITTED (venue truth); not journaled →
        PRESERVED as RESERVED (consumed — never infer failure from
        absence). Every decision is durable + auditable.
        """
        journaled = set(journal_client_order_ids)
        reconciled = 0
        preserved = 0
        with self._locked():
            doc = self._load()
            changed = False
            for rec in doc["records"]:
                if rec.get("state") != ReservationState.RESERVED.value:
                    continue
                if rec.get("client_order_id") in journaled:
                    rec["state"] = ReservationState.SUBMITTED.value
                    rec.setdefault("transitions", []).append({
                        "state": ReservationState.SUBMITTED.value,
                        "at": self._now().isoformat(),
                        "note": "recovery: venue journal ack found — "
                                "reservation reconciled to SUBMITTED",
                    })
                    reconciled += 1
                    changed = True
                else:
                    rec.setdefault("transitions", []).append({
                        "state": ReservationState.RESERVED.value,
                        "at": self._now().isoformat(),
                        "note": "recovery: no journal ack — reservation "
                                "PRESERVED (conservative: consumed)",
                    })
                    preserved += 1
                    changed = True
            if changed:
                self._save(doc)
        return RecoveryReport(
            reconciled_submitted=reconciled,
            preserved_reserved=preserved,
            total_records=len(doc["records"]),
        )

    @staticmethod
    def _to_record_view(rec: dict) -> LedgerRecord:
        return LedgerRecord(
            reservation_id=rec["reservation_id"],
            client_order_id=rec["client_order_id"],
            created_at_wall=_parse_ts(rec["created_at_wall"]),
            created_at_governed=(
                _parse_ts(rec["created_at_governed"])
                if rec.get("created_at_governed") else None
            ),
            state=ReservationState(rec["state"]),
            outcome=rec.get("outcome"),
            finalized_at=(
                _parse_ts(rec["finalized_at"])
                if rec.get("finalized_at") else None
            ),
            transitions=list(rec.get("transitions", [])),
        )

    def records(self) -> List[LedgerRecord]:
        """All persisted records (read-through, no caching)."""
        with self._locked():
            doc = self._load()
        return [self._to_record_view(r) for r in doc["records"]]

    def outstanding(self) -> List[LedgerRecord]:
        """Records still RESERVED/SUBMITTED (unresolved)."""
        return [
            r for r in self.records()
            if r.state in (ReservationState.RESERVED,
                           ReservationState.SUBMITTED)
        ]

    def count_in_window(self, now: Optional[datetime] = None) -> int:
        """Consumed submission slots inside the policy window."""
        now = self._now(now)
        with self._locked():
            doc = self._load()
        count, _last = self._capacity_view(doc, now)
        return count
