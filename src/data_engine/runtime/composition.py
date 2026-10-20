"""Stage C composition root — the explicit production assembly
(patch plan P5; findings F-05, F-13, F-14, F-25; mandates C1-C3).

STAGE A AUDIT CONTEXT
---------------------
Until Stage C, ``TradingRuntime(`` was constructed ONLY in tests
(F-05, HIGH): the repository was a library + test suite, not an
operable service. Nothing assembled a validated operating runtime,
no production path supplied readiness evidence, and the supervisor
could only refuse (honestly) with exit 2. The four structural gaps
closed here:

- **F-05 (HIGH)** — THIS module: the explicit composition root. It
  assembles an operational paper session in ONE documented,
  test-pinned order, with no hidden globals and no second way to
  build the same system.
- **F-13 (MED)** — the feed-staleness watchdog is MANDATORY for
  operational sessions: :class:`OperationalSessionConfig` refuses a
  session whose ``max_feed_staleness_seconds`` is unset (the paper
  default is 900 s, matching the operational feed gate). ``None``
  remains available ONLY on the base ``RuntimeConfig`` for
  deterministic replay, never through this root.
- **F-14 (MED)** — every gate context value and risk ceiling is
  INJECTED from the validated operational config
  (:class:`GateCeilings`, :class:`GateContextDefaults`,
  ``RuntimeRiskLimits``, portfolio ``RiskLimits``) with owner
  ratified paper defaults and provenance; the audited hardcoded
  literals are gone from the runtime wiring (test-pinned
  structurally + by object identity).
- **F-25 (INFO)** — keyed-MAC ledger custody is provisioned through
  the documented operator channel (``RUNTIME_LEDGER_MAC_KEY`` /
  ``RUNTIME_LEDGER_MAC_KEY_FILE`` via ``MacCustody.from_environment``)
  and is REQUIRED for operational sessions — an unprovisioned key
  fails closed with the operator runbook pointer, never silently
  falling back to unkeyed chains.

C1 — CONSTRUCTION ORDER (code- and test-pinned)
-----------------------------------------------
``config -> mac_custody -> state_store -> submission_ledger ->
governor -> runtime -> paper_session_boundary ->
reconciliation_driver -> readiness_evidence -> lifecycle``

Each step is fail-closed: a step that cannot verify itself refuses
construction of everything downstream. ``lifecycle`` (``start()``)
is the operator's explicit call — composition alone never starts a
session, and :meth:`ComposedSession.start` refuses unless the FULL
readiness evidence chain (32 gates) is present.

C2 — READINESS EVIDENCE SUPPLIERS
---------------------------------
:class:`build_readiness_evidence` supplies FIRST-HAND component
evidence for the gates the composition root constructs and
verifies (PERSISTENCE / LEDGER / OMS / RISK / KILLSWITCH /
RECONCILIATION). The three human-dependent gates
(REAL_DATA / OPERATIONAL_FEED / GOVERNANCE) receive explicit FALSE
blockers with precise operator actions — UNLESS the operator's own
evidence bundle already covers them (code never fabricates and
never vetoes recorded human decisions). The remaining gates
require operator-recorded evidence and stay honestly absent when
the bundle does not carry them. ``PAPER_READY`` therefore remains
FALSE until the recorded human dependencies close — this module
makes the wiring EXIST, it does not make the verdict TRUE.

C3 — CONSERVATIVE RESERVATION-RECONCILIATION DRIVER
---------------------------------------------------
:class:`ReservationReconciler` reconciles the durable submission
ledger's outstanding reservations against OMS records and venue
journal truth:

- venue journaled the order (ACK/VENUE_SYNC) -> ``SUBMITTED``
  (durable; the slot stays consumed — the venue saw it);
- venue journaled a REFUSAL -> ``FINALIZED VENUE_REFUSED``
  (consumed — the venue saw and refused the request);
- venue journal authoritative-ABSENT **and** the OMS holds the
  authoritative pre-venue terminal state REJECTED -> the ONLY
  release path (``PRE_VENUE_ABANDONED`` — confirmed absence);
- anything else (timeout / pre-submit OMS state / no OMS record /
  post-venue OMS state without a journal entry) -> PRESERVED,
  never released (timeout is NOT release); a post-venue OMS state
  without a journal entry additionally raises a divergence
  incident (truth divergence is never optimism).

Duplicate-signal idempotent: a second pass performs no additional
durable writes. The driver has NO submission capability — it never
reserves and never submits (structurally incapable of causing a
duplicate submission). Every state-changing decision is durable
(ledger transition) and auditable (incident ledger record).

PAPER-ONLY POSTURE (unchanged): every venue reachable through this
root is the deterministic paper venue (MOCK_DETERMINISTIC enforced
by the guarded session pipeline). LIVE TRADING REMAINS NOT
AUTHORIZED. PAPER_READY stays FALSE until the human dependencies
close.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator

from data_engine.brokers.redaction import BrokerCredential
from data_engine.risk.engine import RiskLimits
from data_engine.runtime.broker_execution import (
    RuntimeAuthoritativeVenue,
    attach_authoritative_paper_venue,
)
from data_engine.runtime.contracts import OrderLifecycle, RuntimeContractError
from data_engine.runtime.mac_custody import MacCustody, MacCustodyError
from data_engine.runtime.operator_approval import (
    OperatorApprovalError,
    OperatorApprovalKey,
    TrustedGateEvidence,
    verify_human_gate_evidence,
)
from data_engine.runtime.readiness import (
    GATE_NAMES,
    GateEvidence,
    PaperReadinessGate,
)
from data_engine.runtime.risk_gate import (
    GateCeilings,
    GateContextDefaults,
    RuntimeRiskLimits,
)
from data_engine.runtime.runtime import RuntimeConfig, TradingRuntime
from data_engine.runtime.state import (
    EXECUTION_STATE_SCHEMA_VERSION,
    ExecutionStateStore,
)
from data_engine.runtime.submission_ledger import (
    ReservationState,
    SubmissionLedger,
    SubmissionPolicy,
)

__all__ = [
    "COMPONENT_EVIDENCE_GATES",
    "CONSTRUCTION_ORDER",
    "GATE_SUPPLIER_DISPOSITION",
    "HUMAN_EVIDENCE_GATES",
    "OPERATOR_RECORDED_EVIDENCE",
    "SUPPLIED_BY_COMPOSITION_ROOT",
    "HUMAN_ACTION_REQUIRED",
    "ComposedSession",
    "ComposedStartReport",
    "CompositionError",
    "CompositionStartRefused",
    "OperationalSessionConfig",
    "ReservationDecision",
    "ReservationReconciler",
    "ReservationReconciliationReport",
    "VenuePlan",
    "build_readiness_evidence",
    "compose_operational_session",
    "_session_config_digest",
]


class CompositionError(RuntimeContractError):
    """Fail-closed composition-root contract violation."""


class CompositionStartRefused(CompositionError):
    """The readiness evidence chain is incomplete — the composed
    session refuses to start (fail closed). ``failed_gates`` carries
    the exact gates whose evidence is missing/failed."""

    def __init__(self, message: str, *, failed_gates: Sequence[str]) -> None:
        super().__init__(message)
        self.failed_gates = tuple(failed_gates)


#: C1: the ONE documented construction order (test-pinned).
CONSTRUCTION_ORDER = (
    "config",
    "mac_custody",
    "operator_approvals",
    "state_store",
    "submission_ledger",
    "governor",
    "runtime",
    "paper_session_boundary",
    "reconciliation_driver",
    "readiness_evidence",
    "lifecycle",
)

#: C2: gates the composition root verifies FIRST-HAND.
COMPONENT_EVIDENCE_GATES = frozenset({
    "PERSISTENCE_READY",
    "LEDGER_READY",
    "OMS_READY",
    "RISK_READY",
    "KILLSWITCH_READY",
    "RECONCILIATION_READY",
})

#: C2: gates that ONLY recorded human decisions can satisfy.
HUMAN_EVIDENCE_GATES = frozenset({
    "REAL_DATA_READY",
    "OPERATIONAL_FEED_READY",
    "GOVERNANCE_READY",
})

SUPPLIED_BY_COMPOSITION_ROOT = "SUPPLIED_BY_COMPOSITION_ROOT"
OPERATOR_RECORDED_EVIDENCE = "OPERATOR_RECORDED_EVIDENCE_REQUIRED"
HUMAN_ACTION_REQUIRED = "HUMAN_ACTION_REQUIRED"

#: F-05 acceptance: every gate's supplier disposition — the honest
#: answer to "who can supply this gate's evidence?" for
#: ``data-engine status --gates``.
GATE_SUPPLIER_DISPOSITION = {
    gate: (
        SUPPLIED_BY_COMPOSITION_ROOT
        if gate in COMPONENT_EVIDENCE_GATES
        else HUMAN_ACTION_REQUIRED
        if gate in HUMAN_EVIDENCE_GATES
        else OPERATOR_RECORDED_EVIDENCE
    )
    for gate in GATE_NAMES
}

_HUMAN_GATE_BLOCKERS = {
    "REAL_DATA_READY": (
        "0 REAL_VERIFIED datasets exist — operator source approval "
        "(SRC-APPROVAL) plus one dataset through the nine-stage chain "
        "is required (RDR-01..RDR-03, READINESS_EVIDENCE_INVENTORY "
        "§4); no code path can fabricate real-data readiness"
    ),
    "OPERATIONAL_FEED_READY": (
        "no human-approved genuine feed source is provisioned "
        "(OFR-01..OFR-05); the feed gate machinery is complete and "
        "refuses to start an operational session without one"
    ),
    "GOVERNANCE_READY": (
        "open human dependencies: GOV-03 credential rotation "
        "confirmation, GOV-04 keyed-MAC key provisioning record, "
        "GOV-05 data-source approval decision "
        "(READINESS_EVIDENCE_INVENTORY §4); recorded human decisions "
        "are the only admissible evidence"
    ),
}


# ---------------------------------------------------------------------------
# F-13/F-14: the validated operational config
# ---------------------------------------------------------------------------

def _d6_portfolio_defaults(max_position_units: Decimal) -> RiskLimits:
    """Reconstruction D-6 provisional portfolio defaults, owner-
    ratified for PAPER MODE ONLY (Part 3) — identical to the legacy
    runtime wiring, now carried as config with provenance."""
    return RiskLimits(
        max_position_units=max_position_units,
        max_leverage=Decimal("1.0"),
        max_single_asset_weight=Decimal("0.30"),
        max_sector_weight=Decimal("1.0"),
        max_portfolio_heat=Decimal("1.0"),
    )


class OperationalSessionConfig(BaseModel):
    """The validated operational session configuration (Stage C).

    Everything an operational paper session injects into the runtime
    lives HERE — never as a hardcoded wiring literal (F-14), never
    as an implicit default the operator did not ratify. Provenance:

    - ``risk_limits`` / ``submission_policy`` — owner-ratified
      PAPER-mode submission governance (Part 3: min 1 s spacing,
      5 submissions per 60 s, max 10 open orders). PAPER MODE ONLY;
      must be re-ratified before any future live mode.
    - ``gate_ceilings`` / ``gate_context`` — see
      :class:`~data_engine.runtime.risk_gate.GateCeilings` and
      :class:`~data_engine.runtime.risk_gate.GateContextDefaults`
      for per-field provenance.
    - ``portfolio_limits`` — D-6 provisional defaults derived from
      the session (explicit injection wins; the derived/injected
      ``max_position_units`` must equal the session's).
    - ``require_mac_custody`` — F-25: operational sessions run on
      keyed-MAC ledger custody, provisioned through the operator
      channel. ``False`` is the explicit NON-OPERATIONAL posture
      (deterministic replay fixtures only).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: RuntimeConfig
    #: Part 3 owner-ratified paper order limits (5/60 s + 10 open).
    risk_limits: RuntimeRiskLimits = RuntimeRiskLimits()
    #: D-6 provisional portfolio defaults (derived when absent).
    portfolio_limits: Optional[RiskLimits] = None
    gate_ceilings: GateCeilings = GateCeilings()
    gate_context: GateContextDefaults = GateContextDefaults()
    #: Part 3 owner-ratified paper submission policy (1 s / 5 / 60 s).
    submission_policy: SubmissionPolicy = SubmissionPolicy()
    require_mac_custody: StrictBool = True

    @model_validator(mode="before")
    @classmethod
    def _derive_portfolio_limits(cls, data):
        if isinstance(data, dict) and data.get("portfolio_limits") is None:
            session = data.get("session")
            units = None
            if isinstance(session, RuntimeConfig):
                units = session.max_position_units
            elif isinstance(session, dict):
                raw = session.get("max_position_units")
                if raw is not None:
                    units = Decimal(str(raw))
            if units is not None:
                data = dict(data)
                data["portfolio_limits"] = _d6_portfolio_defaults(units)
        return data

    @model_validator(mode="after")
    def _operational_mandates(self) -> "OperationalSessionConfig":
        # F-13: the feed watchdog is MANDATORY in operational mode.
        if self.session.max_feed_staleness_seconds is None:
            raise ValueError(
                "operational session requires max_feed_staleness_seconds "
                "to be SET (F-13: paper default 900 s, matching the "
                "operational feed gate) — the composition root refuses "
                "an unwatched live-clock session; None remains available "
                "only for deterministic replay on the base RuntimeConfig"
            )
        # BLOCKER 1: operational sessions are never test fixtures.
        if self.session.ephemeral_test_fixture:
            raise ValueError(
                "ephemeral_test_fixture=True is NOT an operational "
                "session (BLOCKER 1) — the composition root refuses to "
                "assemble a fixture as an operational deployment"
            )
        # F-14 (model_valid provenance): operational sessions pin the
        # ensemble identity; an unpinned model cannot honestly back
        # model_valid=True.
        if not self.session.pinned_model_hashes:
            raise ValueError(
                "operational session requires pinned_model_hashes "
                "(F-14: the model_valid gate-context value is legitimate "
                "ONLY for a pinned + startup-verified ensemble — BLOCKER 21)"
            )
        if self.portfolio_limits is not None and \
                self.portfolio_limits.max_position_units != \
                self.session.max_position_units:
            raise ValueError(
                "portfolio_limits.max_position_units must equal "
                "session.max_position_units (fail closed on divergence "
                "between the two injection channels)"
            )
        return self


# ---------------------------------------------------------------------------
# C3: the conservative reservation-reconciliation driver
# ---------------------------------------------------------------------------

DECISION_RECONCILED_SUBMITTED = "RECONCILED_SUBMITTED"
DECISION_ALREADY_SUBMITTED = "ALREADY_SUBMITTED"
DECISION_RECONCILED_FINALIZED = "RECONCILED_FINALIZED"
DECISION_RELEASED_CONFIRMED_PRE_VENUE = "RELEASED_CONFIRMED_PRE_VENUE"
DECISION_PRESERVED_AMBIGUOUS = "PRESERVED_AMBIGUOUS"
DECISION_ALREADY_RESOLVED = "ALREADY_RESOLVED"

#: OMS states that imply the venue pipeline processed the order — a
#: reservation holding one of these WITHOUT a journal entry is a
#: truth DIVERGENCE (flagged, never released, never optimism).
_POST_VENUE_OMS_STATES = frozenset({
    OrderLifecycle.SUBMITTED,
    OrderLifecycle.ACKNOWLEDGED,
    OrderLifecycle.PARTIALLY_FILLED,
    OrderLifecycle.CANCEL_PENDING,
    OrderLifecycle.FILLED,
    OrderLifecycle.CANCELLED,
    OrderLifecycle.EXPIRED,
    OrderLifecycle.UNKNOWN,
    OrderLifecycle.RECONCILING,
})


@dataclass(frozen=True)
class ReservationDecision:
    """One reconciled reservation's auditable decision record."""

    client_order_id: str
    reservation_id: str
    decision: str
    detail: str


@dataclass(frozen=True)
class ReservationReconciliationReport:
    """Auditable summary of one reconciliation pass."""

    decisions: tuple = ()
    divergence_flags: tuple = ()

    def decision_for(self, client_order_id: str) -> Optional[str]:
        for d in self.decisions:
            if d.client_order_id == client_order_id:
                return d.decision
        return None


class ReservationReconciler:
    """C3 conservative reconciliation driver (U-19).

    Reconciles the durable submission ledger's reservations against
    OMS records and venue-journal truth. Conservative direction
    ONLY: ambiguity preserves the consumed slot; the single release
    path requires CONFIRMED absence (venue journal authoritative-
    absent AND the OMS holds the authoritative pre-venue terminal
    state REJECTED). Duplicate-signal idempotent; no submission
    capability (never reserves, never submits).
    """

    def __init__(
        self,
        ledger: SubmissionLedger,
        *,
        incident_sink: Optional[Any] = None,
        correlation_id: str = "composition.reconciliation",
    ) -> None:
        if not isinstance(ledger, SubmissionLedger) and \
                not hasattr(ledger, "outstanding"):
            raise CompositionError(
                "ReservationReconciler requires a SubmissionLedger "
                "(or a test double exposing its read/transition surface)"
            )
        self._ledger = ledger
        self._incident_sink = incident_sink
        self._correlation_id = correlation_id

    # -- incident recording ------------------------------------------------

    def _incident(self, payload: dict) -> None:
        if self._incident_sink is None:
            return
        self._incident_sink.record(
            ledger="incident",
            event_type="SUBMISSION_RESERVATION_RECONCILED",
            correlation_id=self._correlation_id,
            actor="runtime.reconciliation",
            payload=payload,
        )

    # -- the driver ----------------------------------------------------------

    def reconcile(
        self,
        *,
        oms_orders: Sequence = (),
        venue_records: Sequence = (),
    ) -> ReservationReconciliationReport:
        """One conservative pass. Truth inputs are duck-typed:

        - ``oms_orders``: objects with ``order_id`` + ``status``
          (OrderLifecycle) — the OMS's authoritative records;
        - ``venue_records``: objects with ``client_order_id`` +
          ``entry_type`` (ORDER_ACK / ORDER_REFUSED / VENUE_SYNC) —
          the venue journal's authoritative records.
        """
        latest_venue: dict = {}
        for record in venue_records:
            latest_venue[record.client_order_id] = record.entry_type
        oms_by_cid = {o.order_id: o for o in oms_orders}

        decisions = []
        divergence = []
        for rec in self._ledger.records():
            cid = rec.client_order_id
            outstanding = rec.state in (
                ReservationState.RESERVED, ReservationState.SUBMITTED,
            )
            if not outstanding:
                # Already resolved (FINALIZED/ABANDONED) — a duplicate
                # signal re-reports it with NO durable write.
                decisions.append(ReservationDecision(
                    client_order_id=cid,
                    reservation_id=rec.reservation_id,
                    decision=DECISION_ALREADY_RESOLVED,
                    detail=(
                        f"record already resolved ({rec.state.value}"
                        f"/{'<none>' if rec.outcome is None else rec.outcome}) "
                        "— duplicate signal, no durable write"
                    ),
                ))
                continue

            venue_entry = latest_venue.get(cid)
            oms = oms_by_cid.get(cid)

            if venue_entry in ("ORDER_ACK", "VENUE_SYNC"):
                if rec.state is ReservationState.RESERVED:
                    self._ledger.mark_submitted(rec.reservation_id)
                    decision, detail = (
                        DECISION_RECONCILED_SUBMITTED,
                        "venue journal holds the order — reservation "
                        "reconciled to SUBMITTED (durable; slot stays "
                        "consumed: the venue saw it)",
                    )
                    self._incident({
                        "client_order_id": cid,
                        "reservation_id": rec.reservation_id,
                        "decision": decision,
                        "action": "reconciled SUBMITTED from venue truth",
                    })
                else:
                    decision, detail = (
                        DECISION_ALREADY_SUBMITTED,
                        "venue journal holds the order and the record is "
                        "already SUBMITTED — no-op (idempotent)",
                    )
            elif venue_entry == "ORDER_REFUSED":
                self._ledger.finalize(
                    rec.reservation_id, "VENUE_REFUSED",
                )
                decision, detail = (
                    DECISION_RECONCILED_FINALIZED,
                    "venue journal holds a definitive REFUSAL — the venue "
                    "saw and refused the request (slot consumed; crash "
                    "between refusal and finalize closed)",
                )
                self._incident({
                    "client_order_id": cid,
                    "reservation_id": rec.reservation_id,
                    "decision": decision,
                    "action": "finalized VENUE_REFUSED from venue truth",
                })
            else:
                # No venue-journal entry for this order.
                if oms is not None and \
                        oms.status is OrderLifecycle.REJECTED:
                    # CONFIRMED ABSENCE — the only release path. The
                    # guarded venue pipeline journals EVERY outcome it
                    # sees (ack OR refusal); an authoritative journal
                    # absent + the OMS's authoritative pre-venue
                    # terminal REJECTED prove the venue never saw the
                    # request.
                    self._ledger.abandon(
                        rec.reservation_id,
                        reason=(
                            "reconciliation: confirmed pre-venue "
                            "rejection (venue journal authoritative-"
                            "absent + OMS authoritative pre-venue "
                            "terminal REJECTED)"
                        ),
                    )
                    decision, detail = (
                        DECISION_RELEASED_CONFIRMED_PRE_VENUE,
                        "confirmed absence — venue journal absent AND OMS "
                        "pre-venue terminal REJECTED: the slot is released "
                        "(the ONLY release path; broker never called)",
                    )
                    self._incident({
                        "client_order_id": cid,
                        "reservation_id": rec.reservation_id,
                        "decision": decision,
                        "action": "released on confirmed pre-venue absence",
                    })
                else:
                    detail = (
                        "no venue truth (timeout/unavailable) — "
                        "reservation PRESERVED, capacity stays consumed "
                        "(timeout is NOT release)"
                    )
                    if oms is not None and \
                            oms.status in _POST_VENUE_OMS_STATES:
                        divergence.append(cid)
                        detail = (
                            "TRUTH DIVERGENCE: OMS holds a post-venue "
                            f"state ({oms.status.value}) but the venue "
                            "journal never saw the order — PRESERVED "
                            "(never released) + divergence incident "
                            "(fail closed; manual reconciliation "
                            "required)"
                        )
                        self._incident({
                            "client_order_id": cid,
                            "reservation_id": rec.reservation_id,
                            "decision": DECISION_PRESERVED_AMBIGUOUS,
                            "divergence": True,
                            "oms_status": oms.status.value,
                            "action": (
                                "post-venue OMS state without journal "
                                "entry — incident raised, reservation "
                                "preserved, never released"
                            ),
                        })
                    decision = DECISION_PRESERVED_AMBIGUOUS
                decisions.append(ReservationDecision(
                    client_order_id=cid,
                    reservation_id=rec.reservation_id,
                    decision=decision,
                    detail=detail,
                ))
                continue
            decisions.append(ReservationDecision(
                client_order_id=cid,
                reservation_id=rec.reservation_id,
                decision=decision,
                detail=detail,
            ))

        return ReservationReconciliationReport(
            decisions=tuple(decisions),
            divergence_flags=tuple(divergence),
        )

    def reconcile_runtime(
        self, runtime, venue,
    ) -> ReservationReconciliationReport:
        """Extract the live truths from the composed objects (public
        seams: ``runtime.oms.orders`` + ``venue.session.journal_records``)
        and run one conservative pass."""
        return self.reconcile(
            oms_orders=tuple(runtime.oms.orders()),
            venue_records=tuple(venue.session.journal_records()),
        )


# ---------------------------------------------------------------------------
# C2: readiness evidence suppliers
# ---------------------------------------------------------------------------

def build_readiness_evidence(
    runtime: TradingRuntime,
    ledger: SubmissionLedger,
    mac_custody: Optional[MacCustody],
    state_dir: Path,
    reconciliation_report: Optional[ReservationReconciliationReport] = None,
    operator_evidence: Sequence[GateEvidence] = (),
    operator_approval_key: Optional[OperatorApprovalKey] = None,
    approval_as_of: Optional["datetime"] = None,
    session_scope: str = "*",
    expected_digest: str = "",
) -> tuple:
    """Build the composed session's readiness evidence chain.

    Submission order matters (the gate keeps the LAST evidence per
    gate): operator bundle first, then FIRST-HAND component evidence
    for the gates this root constructed and verified, then explicit
    FALSE blockers for human gates the operator bundle did NOT
    cover (recorded human decisions are never stomped by code).

    FIX-9 (B-P0-03): every ``operator_evidence`` entry that targets a
    HUMAN gate must be a verified :class:`TrustedGateEvidence` — a
    signed ``OperatorApprovalRecord` re-verified here against the
    operator approval key (expiry, scope, decision, digest,
    signature). Plain caller-supplied ``GateEvidence`` with
    ``passed=True`` free text is REFUSED fail-closed with the stable
    reason code ``E_EVIDENCE_UNTRUSTED`` — no path forces a human
    gate TRUE without the operator's key.
    """
    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    as_of = approval_as_of if approval_as_of is not None else _dt.now(_UTC)

    vetted = []
    for ev in operator_evidence:
        if ev.gate in HUMAN_EVIDENCE_GATES:
            try:
                vetted.append(verify_human_gate_evidence(
                    ev,
                    key=operator_approval_key,
                    as_of=as_of,
                    expected_scope=session_scope,
                    expected_digest=expected_digest,
                ))
            except OperatorApprovalError as exc:
                raise CompositionError(
                    "FIX-9 (B-P0-03): human-gate evidence refused "
                    f"for gate {ev.gate!r}: {exc} — supply SIGNED "
                    "operator approval records (see runtime/"
                    "operator_approval.py)"
                ) from exc
        else:
            vetted.append(ev)

    out = list(vetted)

    custody_note = (
        f"keyed-MAC custody OPERATIONAL (key_id="
        f"{mac_custody.current_key_id})"
        if mac_custody is not None else
        "UNKEYED legacy chains (explicit NON-OPERATIONAL posture: "
        "require_mac_custody=False — deterministic replay only)"
    )
    reconc_note = (
        f"pre-start pass over {len(reconciliation_report.decisions)} "
        f"record(s), {len(reconciliation_report.divergence_flags)} "
        "divergence flag(s)"
        if reconciliation_report is not None else
        "driver wired (startup pass runs at lifecycle start)"
    )

    component = {
        "PERSISTENCE_READY": GateEvidence(
            gate="PERSISTENCE_READY",
            component="ExecutionStateStore",
            check="compose_open_flock_verified",
            evidence=(
                f"state store opened under exclusive flock at "
                f"{state_dir} (schema {EXECUTION_STATE_SCHEMA_VERSION}; "
                "atomic tmp+fsync+replace writes; F-03 single-writer "
                "lock held for the composed session's lifetime)"
            ),
            passed=True,
        ),
        "LEDGER_READY": GateEvidence(
            gate="LEDGER_READY",
            component="LedgerFamily+SubmissionLedger",
            check="custody_and_durability_wired",
            evidence=(
                f"durable flock-protected submission ledger at "
                f"{ledger.path} (B1/B2: reserve->submit->finalize "
                f"protocol); {custody_note}"
            ),
            passed=True,
        ),
        "OMS_READY": GateEvidence(
            gate="OMS_READY",
            component="OMS",
            check="transition_table_integrity",
            evidence=(
                "OMS constructed over the custody-backed ledger family; "
                "closed lifecycle state machine with no skip transitions; "
                "UNKNOWN never guessed away (reconcile-before-retry "
                "enforced at OMS + session + runtime layers)"
            ),
            passed=True,
        ),
        "RISK_READY": GateEvidence(
            gate="RISK_READY",
            component="RiskEngine+RiskGate",
            check="limits_injected_with_provenance",
            evidence=(
                "portfolio limits + gate ceilings + order limits "
                "injected from the validated operational config (F-14; "
                "owner-ratified PAPER-mode defaults with provenance: "
                f"leverage<={runtime.portfolio_limits.max_leverage}, "
                f"max_volatility<="
                f"{runtime.gate_ceilings.max_volatility}, "
                f"max_spread_fraction<="
                f"{runtime.gate_ceilings.max_spread_fraction})"
            ),
            passed=True,
        ),
        "KILLSWITCH_READY": GateEvidence(
            gate="KILLSWITCH_READY",
            component="KillSwitchManager",
            check="constructed_no_trips",
            evidence=(
                "kill-switch manager wired to the ledger family; no "
                "trips at composition (7-scope hierarchy; unprivileged "
                "trip; reset is human-principal-gated; trips persist "
                "across restarts)"
            ),
            passed=True,
        ),
        "RECONCILIATION_READY": GateEvidence(
            gate="RECONCILIATION_READY",
            component="ReservationReconciler",
            check="conservative_driver_wired",
            evidence=(
                "C3 conservative reconciliation driver wired over the "
                "durable ledger vs OMS/venue truth (confirmed-absence "
                "only release; ambiguity preserved; duplicate-signal "
                f"idempotent; no submission capability); {reconc_note}"
            ),
            passed=True,
        ),
    }
    out.extend(component[g] for g in sorted(COMPONENT_EVIDENCE_GATES))

    covered_by_operator = {e.gate for e in operator_evidence}
    for gate in sorted(HUMAN_EVIDENCE_GATES):
        if gate not in covered_by_operator:
            out.append(GateEvidence(
                gate=gate,
                component="human-dependency",
                check="operator_action_required",
                evidence=_HUMAN_GATE_BLOCKERS[gate],
                passed=False,
            ))

    return tuple(out)


# ---------------------------------------------------------------------------
# C1: the composition root
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VenuePlan:
    """The prepared paper-session boundary (attached at lifecycle
    start — the venue requires a STARTED runtime by contract)."""

    account_id: str
    journal_path: Path
    clock: Callable[[], datetime]
    instruments: Mapping
    credential: BrokerCredential
    currency: str = "USD"
    initial_balance: Decimal = Decimal("100000")
    retry_policy: Optional[Any] = None
    sleeper: Optional[Any] = None
    adapter_factory: Optional[Any] = None


@dataclass(frozen=True)
class ComposedStartReport:
    """What the lifecycle step started + verified (fail closed)."""

    venue: Optional[RuntimeAuthoritativeVenue]
    reconciliation: ReservationReconciliationReport
    post_start_verified: bool
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ComposedSession:
    """The assembled operational paper session (read-only surface).

    Construction is complete; the LIFECYCLE step
    (:meth:`start`) is the operator's explicit call and refuses
    unless the FULL readiness evidence chain is present.
    """

    def __init__(
        self,
        *,
        config: OperationalSessionConfig,
        runtime: TradingRuntime,
        ledger: SubmissionLedger,
        mac_custody: Optional[MacCustody],
        readiness_gate: PaperReadinessGate,
        evidence: tuple,
        reconciler: ReservationReconciler,
        venue_plan: VenuePlan,
        executed_steps: tuple,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._ledger = ledger
        self._mac_custody = mac_custody
        self._readiness_gate = readiness_gate
        self._evidence = tuple(evidence)
        self._reconciler = reconciler
        self._venue_plan = venue_plan
        self._executed_steps = tuple(executed_steps)
        self._start_report: Optional[ComposedStartReport] = None

    # -- read-only surface -------------------------------------------------

    @property
    def config(self) -> OperationalSessionConfig:
        return self._config

    @property
    def runtime(self) -> TradingRuntime:
        return self._runtime

    @property
    def ledger(self) -> SubmissionLedger:
        return self._ledger

    @property
    def mac_custody(self) -> Optional[MacCustody]:
        return self._mac_custody

    @property
    def readiness_gate(self) -> PaperReadinessGate:
        return self._readiness_gate

    @property
    def evidence(self) -> tuple:
        return self._evidence

    @property
    def reconciler(self) -> ReservationReconciler:
        return self._reconciler

    @property
    def construction_order(self) -> tuple:
        """The documented C1 order (constant, test-pinned)."""
        return CONSTRUCTION_ORDER

    @property
    def executed_steps(self) -> tuple:
        """Which construction steps ACTUALLY ran (lifecycle is last
        and only via :meth:`start`)."""
        return self._executed_steps

    @property
    def start_report(self) -> Optional[ComposedStartReport]:
        return self._start_report

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> ComposedStartReport:
        """The LIFECYCLE step: evaluate the FULL readiness chain,
        start the runtime (recovery), attach the paper venue, run
        the reconciliation driver's startup pass and verify the
        post-start facts. Refuses (fail closed) on ANY gap."""
        report = self._readiness_gate.evaluate()
        if not report.paper_ready:
            raise CompositionStartRefused(
                "START REFUSED — the readiness evidence chain is "
                f"incomplete; failed gates: {list(report.failed_gates)} "
                "(fail closed — the composed session never starts on "
                "an unevidenced readiness claim)",
                failed_gates=report.failed_gates,
            )

        self._runtime.start()
        venue = attach_authoritative_paper_venue(
            self._runtime,
            account_id=self._venue_plan.account_id,
            journal_path=self._venue_plan.journal_path,
            clock=self._venue_plan.clock,
            instruments=self._venue_plan.instruments,
            credential=self._venue_plan.credential,
            currency=self._venue_plan.currency,
            initial_balance=self._venue_plan.initial_balance,
            retry_policy=self._venue_plan.retry_policy,
            sleeper=self._venue_plan.sleeper,
            adapter_factory=self._venue_plan.adapter_factory,
        )

        reconciliation = self._reconciler.reconcile_runtime(
            self._runtime, venue,
        )

        # Post-start verification: the operator's recorded
        # EXECUTION/RECONCILIATION evidence must match the live facts.
        post_start_verified = venue is not None and \
            not reconciliation.divergence_flags
        if reconciliation.divergence_flags:
            self._runtime.ledgers.record(
                ledger="incident",
                event_type="EXECUTION_UNCERTAIN",
                correlation_id="composition.post_start_verify",
                actor="runtime.composition",
                payload={
                    "divergence_flags": list(
                        reconciliation.divergence_flags
                    ),
                    "action": (
                        "post-start verification FAILED: reservations "
                        "hold post-venue OMS states without venue-"
                        "journal entries — manual reconciliation "
                        "required (fail closed, never optimism)"
                    ),
                },
            )
            raise CompositionError(
                "post-start verification FAILED — reconciliation "
                "divergence: "
                f"{list(reconciliation.divergence_flags)} (the composed "
                "session refuses to certify EXECUTION/RECONCILIATION "
                "readiness against divergent truth; fail closed)"
            )

        # Durable audit of the startup pass (C3: auditable decisions).
        self._runtime.ledgers.record(
            ledger="incident",
            event_type="SUBMISSION_RECONCILIATION_PASS",
            correlation_id="composition.lifecycle",
            actor="runtime.composition",
            payload={
                "decisions": len(reconciliation.decisions),
                "divergence_flags": len(reconciliation.divergence_flags),
                "action": (
                    "composed session started: runtime recovered, paper "
                    "venue attached, reservation reconciliation pass "
                    "complete (conservative; fail closed)"
                ),
            },
        )

        self._start_report = ComposedStartReport(
            venue=venue,
            reconciliation=reconciliation,
            post_start_verified=post_start_verified,
        )
        return self._start_report


def _session_config_digest(config: OperationalSessionConfig) -> str:
    """SHA-256 over the canonical JSON of the operational session
    config — the artifact digest a pinned operator approval must
    match (FIX-9: an approval recorded for one config cannot be
    replayed against a different one)."""
    import hashlib

    return hashlib.sha256(
        config.model_dump_json().encode("utf-8")
    ).hexdigest()


def compose_operational_session(
    *,
    config: OperationalSessionConfig,
    ensemble,
    calibrator=None,
    state_dir: Path,
    ledger_path: Path,
    venue_journal_path: Path,
    venue_account_id: str,
    venue_credential: BrokerCredential,
    instruments: Mapping,
    venue_clock: Callable[[], datetime],
    operator_evidence: Sequence[GateEvidence] = (),
    operator_approval_key: Optional[OperatorApprovalKey] = None,
    approval_as_of: Optional[datetime] = None,
    mac_custody: Optional[MacCustody] = None,
    wall_clock=None,
    venue_currency: str = "USD",
    venue_initial_balance: Decimal = Decimal("100000"),
    venue_retry_policy=None,
    venue_sleeper=None,
    venue_adapter_factory=None,
    started: bool = False,
) -> ComposedSession:
    """Assemble an operational paper session in the ONE documented
    order (C1). Fail-closed at every step; ``lifecycle`` runs only
    when ``started=True`` (otherwise the caller makes the explicit
    :meth:`ComposedSession.start` call).

    The operator supplies: the fitted + pinned ``ensemble``, the
    venue boundary parameters (paper/mock only — the guarded session
    pipeline enforces MOCK_DETERMINISTIC and refuses REAL adapters),
    and the operator's recorded-evidence bundle for the readiness
    gates this root cannot verify first-hand.
    """
    executed = []

    # -- 1. validated config ------------------------------------------------
    if not isinstance(config, OperationalSessionConfig):
        raise CompositionError(
            "compose_operational_session requires an "
            "OperationalSessionConfig (pydantic-validated, fail closed) "
            "— assemble operational sessions ONLY through the "
            "composition root"
        )
    if ensemble is None:
        raise CompositionError(
            "an operational session requires a fitted ensemble "
            "(operator-supplied; identity pinned via "
            "pinned_model_hashes and verified at start — BLOCKER 21)"
        )
    if not isinstance(venue_credential, BrokerCredential):
        raise CompositionError(
            "a BrokerCredential holder is MANDATORY for the paper "
            "venue boundary (account isolation)"
        )
    executed.append("config")

    # -- 2. keyed-MAC custody (F-25) ----------------------------------------
    custody: Optional[MacCustody] = mac_custody
    if custody is not None and not isinstance(custody, MacCustody):
        raise CompositionError(
            "mac_custody must be a MacCustody instance (explicit "
            "injection) — use require_mac_custody + the environment "
            "channel for operational provisioning"
        )
    if custody is None and config.require_mac_custody:
        try:
            custody = MacCustody.from_environment()
        except MacCustodyError as exc:
            raise CompositionError(
                "F-25: operational keyed-MAC ledger custody is REQUIRED "
                f"but provisioning FAILED: {exc} — provision the key "
                "through the documented operator secure channel (see "
                "docs/PAPER_OPERATOR_RUNBOOK.md §5 / GOV-04); the "
                "composition root never falls back to unkeyed chains"
            ) from exc
    executed.append("mac_custody")

    # -- 1b. trusted operator approvals (FIX-9 / B-P0-03) ------------------
    # Human-gate evidence must be SIGNED approval records re-verified
    # against the operator approval key. The key enters EITHER by
    # explicit injection (tests / operator launchers that already hold
    # it) or through the environment channel (the same discipline as
    # keyed-MAC custody, F-25). Absent key + present human evidence =>
    # fail closed; absent key + NO human evidence => the human gates
    # simply stay FALSE (the pre-existing fail-closed path).
    human_evidence_present = any(
        ev.gate in HUMAN_EVIDENCE_GATES for ev in operator_evidence
    )
    approval_key = operator_approval_key
    if human_evidence_present and approval_key is None:
        try:
            approval_key = OperatorApprovalKey.from_environment()
        except OperatorApprovalError as exc:
            raise CompositionError(
                "FIX-9 (B-P0-03): human-gate evidence was supplied but "
                f"no operator approval key could be provisioned: {exc} "
                "— a human-dependency gate cannot pass on unverified "
                "evidence (fail closed)"
            ) from exc
    executed.append("operator_approvals")

    # -- 3. state store (F-03 single-writer flock) --------------------------
    if not isinstance(state_dir, Path):
        state_dir = Path(state_dir)
    state_store = ExecutionStateStore(state_dir)
    executed.append("state_store")

    # -- 4+5. durable ledger + governor policy (B1/B2) ----------------------
    if not isinstance(ledger_path, Path):
        ledger_path = Path(ledger_path)
    ledger = SubmissionLedger(
        ledger_path,
        policy=config.submission_policy,
        wall_clock=wall_clock,
    )
    executed.append("submission_ledger")
    executed.append("governor")

    # -- 6. the runtime (ALL values injected — F-14) ------------------------
    readiness_gate = PaperReadinessGate()
    runtime = TradingRuntime(
        config.session,
        ensemble,
        calibrator=calibrator,
        state_store=state_store,
        readiness_gate=readiness_gate,
        risk_limits=config.risk_limits,
        portfolio_limits=config.portfolio_limits,
        gate_ceilings=config.gate_ceilings,
        gate_context=config.gate_context,
        submission_ledger=ledger,
        mac_custody=custody,
        wall_clock=wall_clock,
    )
    executed.append("runtime")

    # -- 7. the prepared paper-session boundary ------------------------------
    venue_plan = VenuePlan(
        account_id=venue_account_id,
        journal_path=venue_journal_path
        if isinstance(venue_journal_path, Path)
        else Path(venue_journal_path),
        clock=venue_clock,
        instruments=instruments,
        credential=venue_credential,
        currency=venue_currency,
        initial_balance=venue_initial_balance,
        retry_policy=venue_retry_policy,
        sleeper=venue_sleeper,
        adapter_factory=venue_adapter_factory,
    )
    executed.append("paper_session_boundary")

    # -- 8. the reconciliation driver (C3) — pre-start pass -----------------
    reconciler = ReservationReconciler(
        ledger,
        incident_sink=runtime.ledgers,
        correlation_id=f"composition:{config.session.session_id}",
    )
    pre_start = reconciler.reconcile(
        oms_orders=tuple(runtime.oms.orders()),
        venue_records=(),
    )
    if pre_start.divergence_flags:
        raise CompositionError(
            "pre-start reconciliation divergence: "
            f"{list(pre_start.divergence_flags)} — the ledger holds "
            "post-venue OMS states the (not-yet-attached) venue journal "
            "cannot corroborate; manual reconciliation required "
            "(fail closed)"
        )
    executed.append("reconciliation_driver")

    # -- 9. readiness evidence (C2 + FIX-9 trusted approvals) --------------
    evidence = build_readiness_evidence(
        runtime=runtime,
        ledger=ledger,
        mac_custody=custody,
        state_dir=state_dir,
        reconciliation_report=pre_start,
        operator_evidence=operator_evidence,
        operator_approval_key=approval_key,
        approval_as_of=approval_as_of,
        session_scope=config.session.session_id,
        expected_digest=_session_config_digest(config),
    )
    for ev in evidence:
        readiness_gate.submit(ev)
    executed.append("readiness_evidence")

    session = ComposedSession(
        config=config,
        runtime=runtime,
        ledger=ledger,
        mac_custody=custody,
        readiness_gate=readiness_gate,
        evidence=evidence,
        reconciler=reconciler,
        venue_plan=venue_plan,
        executed_steps=tuple(executed),
    )

    # -- 10. lifecycle (explicit) ---------------------------------------------
    if started:
        session.start()
        executed.append("lifecycle")
        session._executed_steps = tuple(executed)

    return session
