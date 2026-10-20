"""30-day paper-soak preflight (P0-P3 master audit FIX-14 / B-P2-16
+ Task 12).

WHY THIS MODULE EXISTS. The soak PROCEDURE existed as a document
(artifacts/stage-d/PAPER-SOAK-PROCEDURE.md) but had NO executable
preflight: nothing refused a soak start when mandatory gates were
false or evidence was stale, and no mock dry run existed. The prompt
requires: "Add an explicit preflight that refuses to start if any
mandatory gate is false or evidence is stale. Ensure a soak cannot
begin from a green CI run alone."

WHAT THIS MODULE ADDS:

- :func:`run_soak_preflight` — an EXECUTABLE, fail-closed preflight
  over the session launch plan's evidence bundle:
  1. the plan itself must load and validate (FIX-10 plan model);
  2. every NON-component gate must carry PASSING evidence in the
     operator's bundle (approvals + recorded entries) — one missing
     or failing gate refuses the soak with that gate named;
  3. every HUMAN gate must be satisfied by a SIGNED, verified
     operator approval (FIX-9 trust boundary — free-text recorded
     evidence is refused);
  4. every approval must still be valid at the soak START and must
     not expire BEFORE the soak's planned END (a 30-day soak needs
     approvals valid for the whole window — stale/short evidence
     refuses the soak);
  5. CI status is STRUCTURALLY IRRELEVANT: the preflight reads no CI
     input whatsoever (a green CI run alone can never start a soak).

HONEST SCOPE:

- The six COMPONENT gates (PERSISTENCE/LEDGER/OMS/RISK/KILLSWITCH/
  RECONCILIATION) are verified FIRST-HAND by the composition root at
  launch time (C2) — the preflight reports them as pending-launch
  verification rather than fabricating a first-hand verdict here.
- This module PERFORMS NO SOAK: it is the preflight that must run
  BEFORE any separately authorized soak start. The dry run in the
  tests uses deterministic mocks only.

Exit code from the CLI: 6 (dedicated soak-preflight refusal code).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict

from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    HUMAN_EVIDENCE_GATES,
)
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.operator_approval import (
    OperatorApprovalKey,
    OperatorApprovalRecord,
    build_trusted_evidence,
)
from data_engine.runtime.readiness import GATE_NAMES, PaperReadinessGate
from data_engine.runtime.session_launch import (
    SessionLaunchError,
    SessionLaunchPlan,
    load_launch_plan,
)

__all__ = [
    "SOAK_PREFLIGHT_EXIT_CODE",
    "DEFAULT_SOAK_DURATION_DAYS",
    "SoakPreflightError",
    "SoakPreflightReport",
    "run_soak_preflight",
    "preflight_report_from_plan",
]

#: Dedicated CLI exit code for a refused soak preflight.
SOAK_PREFLIGHT_EXIT_CODE = 6

#: The documented 30-day paper soak window (PAPER-SOAK-PROCEDURE.md).
DEFAULT_SOAK_DURATION_DAYS = 30


class SoakPreflightError(RuntimeContractError):
    """Refused soak preflight (fail closed). ``reason_code`` is a
    stable code from the module docstring's vocabulary."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"[{reason_code}] {detail}")
        self.reason_code = reason_code
        self.detail = detail


class SoakPreflightReport(BaseModel):
    """The preflight verdict record (attributable, timestamped, no
    secrets — approval references carry only ids/key fingerprints)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    as_of: datetime
    soak_end: datetime
    gates_covered: tuple
    human_gates_verified: tuple
    pending_launch_verification: tuple
    reasons: tuple
    approval_ids: tuple
    plan_session_id: str


def _load_bundle_evidence(
    plan: SessionLaunchPlan,
    *,
    approval_key: Optional[OperatorApprovalKey],
    as_of: datetime,
) -> tuple:
    """Load + verify the plan's evidence bundle (recorded entries +
    signed approvals). Raises SoakPreflightError with a stable code
    on any trust failure (reuses the FIX-9 boundary)."""
    from data_engine.runtime.session_launch import _load_approvals

    evidence = []
    for entry in plan.recorded_evidence:
        evidence.append(entry.to_gate_evidence())
    if plan.approvals_file:
        if approval_key is None:
            try:
                approval_key = OperatorApprovalKey.from_environment()
            except Exception as exc:
                raise SoakPreflightError(
                    "E_SOAK_APPROVAL_KEY_UNAVAILABLE",
                    f"no operator approval key provisioned: {exc}",
                ) from exc
        try:
            evidence.extend(_load_approvals(
                plan.approvals_file, approval_key, as_of=as_of,
            ))
        except SessionLaunchError as exc:
            raise SoakPreflightError(
                "E_SOAK_EVIDENCE_UNTRUSTED",
                f"approval bundle refused: {exc}",
            ) from exc
    return tuple(evidence)


def run_soak_preflight(
    plan_path,
    *,
    approval_key: Optional[OperatorApprovalKey] = None,
    as_of: Optional[datetime] = None,
    soak_duration_days: int = DEFAULT_SOAK_DURATION_DAYS,
) -> SoakPreflightReport:
    """Run the fail-closed soak preflight over a launch plan.

    Raises :class:`SoakPreflightError` (stable reason code) on any
    refusal; returns the passing report otherwise. NEVER reads CI
    status — a green CI run is structurally insufficient to start a
    soak (the evidence bundle is the only admissible basis)."""
    start = as_of or datetime.now(UTC)
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    soak_end = start + timedelta(days=soak_duration_days)

    # -- 1. the plan itself ---------------------------------------------------
    try:
        plan = (
            plan_path
            if isinstance(plan_path, SessionLaunchPlan)
            else load_launch_plan(plan_path)
        )
    except SessionLaunchError as exc:
        raise SoakPreflightError(
            "E_SOAK_PLAN_INVALID", f"launch plan refused: {exc}",
        ) from exc

    # -- 2. the evidence bundle (FIX-9 trust boundary) ------------------------
    try:
        evidence = _load_bundle_evidence(
            plan, approval_key=approval_key, as_of=start,
        )
    except SoakPreflightError:
        raise

    # approvals freshness for the WHOLE soak window
    from data_engine.runtime.operator_approval import TrustedGateEvidence

    approval_ids = []
    for ev in evidence:
        if isinstance(ev, TrustedGateEvidence):
            record: OperatorApprovalRecord = ev.approval_record
            approval_ids.append(record.record_id)
            if record.expires_at <= soak_end:
                raise SoakPreflightError(
                    "E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END",
                    f"approval {record.record_id!r} (gate "
                    f"{record.gate}) expires {record.expires_at}"
                    f" which is at/before the soak end "
                    f"{soak_end} — re-record the approval with a "
                    "validity window covering the full soak",
                )

    # -- 3. evaluate every gate the bundle claims ------------------------------
    gate = PaperReadinessGate()
    for ev in evidence:
        gate.submit(ev)
    report = gate.evaluate()

    # Which gates did the BUNDLE cover (submitted evidence, passing
    # or not)? Anything not covered by the bundle is either a missing
    # mandatory gate or a component gate (verified at launch).
    covered_by_bundle = {ev.gate for ev in evidence}
    failed_in_bundle = {
        g for g in report.failed_gates if g in covered_by_bundle
    }
    if failed_in_bundle:
        raise SoakPreflightError(
            "E_SOAK_GATES_FALSE",
            f"bundle evidence marks these mandatory gates FALSE: "
            f"{sorted(failed_in_bundle)} — a soak cannot start on a "
            "failing gate",
        )

    missing = set(GATE_NAMES) - covered_by_bundle - set(
        COMPONENT_EVIDENCE_GATES
    )
    if missing:
        raise SoakPreflightError(
            "E_SOAK_EVIDENCE_MISSING",
            f"the bundle carries NO evidence for mandatory gates: "
            f"{sorted(missing)} — every non-component gate requires "
            "operator evidence before a soak may start",
        )

    # Human gates must be TRUSTED (signed approvals), not recorded
    # free text — re-assert here even though _load_approvals built
    # them (defense in depth: the bundle could carry plain recorded
    # entries for human gates from the plan's recorded_evidence).
    human_verified = []
    for ev in evidence:
        if ev.gate in HUMAN_EVIDENCE_GATES:
            if not isinstance(ev, TrustedGateEvidence):
                raise SoakPreflightError(
                    "E_SOAK_EVIDENCE_UNTRUSTED",
                    f"human gate {ev.gate} is carried by plain "
                    "recorded evidence — human gates require SIGNED "
                    "approvals (FIX-9)",
                )
            human_verified.append(ev.gate)

    return SoakPreflightReport(
        passed=True,
        as_of=start,
        soak_end=soak_end,
        gates_covered=tuple(sorted(covered_by_bundle)),
        human_gates_verified=tuple(sorted(human_verified)),
        pending_launch_verification=tuple(
            sorted(COMPONENT_EVIDENCE_GATES),
        ),
        reasons=(),
        approval_ids=tuple(approval_ids),
        plan_session_id=plan.runtime_config().session_id,
    )


def preflight_report_from_plan(plan) -> SoakPreflightReport:
    """Convenience: run the preflight over an ALREADY-LOADED plan
    (used by the CLI path and the dry-run tests)."""
    return run_soak_preflight(plan)
