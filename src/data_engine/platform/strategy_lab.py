"""Strategy Management Lab (platform mandate Phase D).

Registry + immutable versioning + server-controlled lifecycle for
operator-defined strategies (RULES or PYTHON). Built on the FROZEN Phase 3
strategy contracts via adaptation — frozen files are never modified.

Contracts (fail-closed):
- Every version is immutable: spec/config/source hashes identify it; any
  change creates a NEW version; prior evidence never certifies a new
  version (evidence records are bound to the version that produced them).
- Lifecycle transitions validate prerequisites; unknown/missing/failed
  prerequisites refuse the transition (fail closed).
- ``LIVE_ACTIVE`` is unreachable in this implementation: repository
  policy keeps live trading NOT AUTHORIZED — the transition raises with
  an explicit refusal reason, even if approvals exist.
- No user code is executed here: this module only manages metadata.
  Execution of PYTHON strategies requires the sandbox worker (separate
  workstream — not claimed here).
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrategyType(str, Enum):
    RULES = "RULES"
    PYTHON = "PYTHON"


class LifecycleState(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    STATIC_VALIDATION = "STATIC_VALIDATION"
    VALIDATED = "VALIDATED"
    BACKTEST_RUNNING = "BACKTEST_RUNNING"
    BACKTEST_PASSED = "BACKTEST_PASSED"
    PAPER_RUNNING = "PAPER_RUNNING"
    PAPER_PASSED = "PAPER_PASSED"
    EVIDENCE_REVIEW = "EVIDENCE_REVIEW"
    AWAITING_LIVE_APPROVAL = "AWAITING_LIVE_APPROVAL"
    LIVE_APPROVED = "LIVE_APPROVED"
    AWAITING_FINAL_CONFIRMATION = "AWAITING_FINAL_CONFIRMATION"
    LIVE_ACTIVE = "LIVE_ACTIVE"
    STATIC_CHECK_FAILED = "STATIC_CHECK_FAILED"
    BACKTEST_FAILED = "BACKTEST_FAILED"
    PAPER_FAILED = "PAPER_FAILED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    ARCHIVED = "ARCHIVED"


#: Allowed transitions (legality only). Evidence requirements live in
#: ``_REQUIRED_EVIDENCE_BY_TARGET`` — the single authoritative map — so
#: the missing-evidence refusal fires BEFORE the state-table refusal and
#: is always the most informative failure (fail-closed diagnostics).
_TRANSITIONS: dict[LifecycleState, tuple[LifecycleState, ...]] = {
    LifecycleState.DRAFT: (
        LifecycleState.SUBMITTED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.SUBMITTED: (
        LifecycleState.STATIC_VALIDATION,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.STATIC_VALIDATION: (
        LifecycleState.VALIDATED,
        LifecycleState.STATIC_CHECK_FAILED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.VALIDATED: (
        LifecycleState.BACKTEST_RUNNING,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.BACKTEST_RUNNING: (
        LifecycleState.BACKTEST_PASSED,
        LifecycleState.BACKTEST_FAILED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.BACKTEST_PASSED: (
        LifecycleState.PAPER_RUNNING,
        LifecycleState.BACKTEST_RUNNING,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.PAPER_RUNNING: (
        LifecycleState.PAPER_PASSED,
        LifecycleState.PAPER_FAILED,
        LifecycleState.SUSPENDED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.PAPER_PASSED: (
        LifecycleState.EVIDENCE_REVIEW,
        LifecycleState.PAPER_RUNNING,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.EVIDENCE_REVIEW: (
        LifecycleState.AWAITING_LIVE_APPROVAL,
        LifecycleState.INSUFFICIENT_EVIDENCE,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.AWAITING_LIVE_APPROVAL: (
        LifecycleState.LIVE_APPROVED,
        LifecycleState.REVOKED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.LIVE_APPROVED: (
        LifecycleState.AWAITING_FINAL_CONFIRMATION,
        LifecycleState.REVOKED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.AWAITING_FINAL_CONFIRMATION: (
        # LIVE_ACTIVE intentionally absent: repository policy refuses it.
        LifecycleState.REVOKED,
        LifecycleState.SUSPENDED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.STATIC_CHECK_FAILED: (
        LifecycleState.ARCHIVED, LifecycleState.DRAFT,
    ),
    LifecycleState.BACKTEST_FAILED: (
        LifecycleState.ARCHIVED, LifecycleState.DRAFT,
    ),
    LifecycleState.PAPER_FAILED: (
        LifecycleState.ARCHIVED, LifecycleState.DRAFT,
    ),
    LifecycleState.INSUFFICIENT_EVIDENCE: (
        LifecycleState.ARCHIVED, LifecycleState.EVIDENCE_REVIEW,
    ),
    LifecycleState.SUSPENDED: (
        LifecycleState.PAPER_RUNNING,
        LifecycleState.REVOKED,
        LifecycleState.ARCHIVED,
    ),
    LifecycleState.REVOKED: (LifecycleState.ARCHIVED,),
    LifecycleState.ARCHIVED: (),
    LifecycleState.LIVE_ACTIVE: (),
}

#: Evidence kinds that MUST be attached to the CURRENT version before
#: entering the target state. Checked before the legality table: an
#: evidence-bound-to-old-version refusal is more specific than a generic
#: illegal-transition refusal and must never be masked by it.
_REQUIRED_EVIDENCE_BY_TARGET: dict[LifecycleState, str] = {
    LifecycleState.VALIDATED: "static_check",
    LifecycleState.BACKTEST_PASSED: "backtest_report",
    LifecycleState.PAPER_PASSED: "paper_report",
    LifecycleState.AWAITING_LIVE_APPROVAL: "eligibility_review",
    LifecycleState.LIVE_APPROVED: "operator_approval",
}

#: Analytical targets where the required evidence itself certifies the
#: prerequisite work: an interactive flow holding the evidence may enter
#: the state directly (the SUBMITTED/STATIC_VALIDATION bookkeeping steps
#: may be compressed). Governance targets (AWAITING_LIVE_APPROVAL,
#: LIVE_APPROVED) are deliberately NOT in this set — evidence alone never
#: shortcuts the approval chain — and no evidence can revive a terminal
#: (ARCHIVED/REVOKED) strategy.
_EVIDENCE_GATED_ANALYTICAL = (
    LifecycleState.VALIDATED,
    LifecycleState.BACKTEST_PASSED,
    LifecycleState.PAPER_PASSED,
)

_TERMINAL_STATES = (LifecycleState.ARCHIVED, LifecycleState.REVOKED)


class LifecycleError(RuntimeError):
    """Raised when a transition is illegal, lacks prerequisites, or is
    refused by repository policy."""


def _canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class EvidenceRecord(BaseModel):
    """Evidence bound to ONE strategy version (never inherited)."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(..., description="static_check|backtest_report|paper_report|eligibility_review|operator_approval")
    version: int
    reference: str
    recorded_at: datetime
    recorded_by: str = "system"
    summary: Optional[str] = None


class OperatorApproval(BaseModel):
    """Human approval (Approval 1). Never fabricated by the system."""

    model_config = ConfigDict(frozen=True)

    actor: str
    approved_at: datetime
    strategy_id: str
    version: int
    scope: str
    signature: str = Field(..., min_length=1)


class StrategyVersion(BaseModel):
    """Immutable version identity (hashes over declared fields only)."""

    model_config = ConfigDict(frozen=True)

    version: int
    strategy_type: StrategyType
    spec: dict[str, Any]
    config: dict[str, Any]
    source: Optional[str] = None
    created_at: datetime
    created_by: str
    spec_hash: str
    config_hash: str
    source_hash: Optional[str] = None

    @classmethod
    def create(
        cls,
        version: int,
        strategy_type: StrategyType,
        spec: dict[str, Any],
        config: dict[str, Any],
        source: Optional[str],
        created_at: datetime,
        created_by: str,
    ) -> "StrategyVersion":
        if strategy_type is StrategyType.PYTHON and not (source and source.strip()):
            raise ValueError("PYTHON strategies require source artifact")
        return cls(
            version=version,
            strategy_type=strategy_type,
            spec=dict(spec),
            config=dict(config),
            source=source,
            created_at=created_at,
            created_by=created_by,
            spec_hash=_canonical_hash(spec),
            config_hash=_canonical_hash(config),
            source_hash=_canonical_hash(source) if source else None,
        )


class StrategyRecord(BaseModel):
    """Mutable strategy envelope over immutable versions."""

    strategy_id: str
    name: str
    enabled: bool = True
    state: LifecycleState = LifecycleState.DRAFT
    current_version: int = 0
    versions: tuple[StrategyVersion, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    instruments: tuple[str, ...] = ()

    def version(self, n: int) -> StrategyVersion:
        for v in self.versions:
            if v.version == n:
                return v
        raise KeyError(f"strategy {self.strategy_id} has no version {n}")


class StrategyLab:
    """Server-controlled strategy registry (UI can never jump states)."""

    def __init__(self, audit_log: Optional[object] = None) -> None:
        self._strategies: dict[str, StrategyRecord] = {}
        self._audit = audit_log

    # -- creation / versioning -------------------------------------------
    def create(
        self,
        name: str,
        strategy_type: StrategyType,
        spec: dict[str, Any],
        config: dict[str, Any],
        source: Optional[str],
        at: datetime,
        created_by: str,
        instruments: tuple[str, ...] = (),
        strategy_id: Optional[str] = None,
    ) -> StrategyRecord:
        if not name.strip():
            raise ValueError("strategy name required")
        sid = strategy_id or f"STR-{_canonical_hash((name, strategy_type.value))[:12]}"
        if sid in self._strategies:
            raise ValueError(f"strategy_id {sid} already exists")
        version = StrategyVersion.create(
            1, strategy_type, spec, config, source, at, created_by
        )
        rec = StrategyRecord(
            strategy_id=sid,
            name=name,
            current_version=1,
            versions=(version,),
            instruments=instruments,
        )
        self._strategies[sid] = rec
        self._event(at, "strategy_created", f"{name} v1 ({strategy_type.value})", sid)
        return rec

    def new_version(
        self,
        strategy_id: str,
        at: datetime,
        created_by: str,
        spec: Optional[dict[str, Any]] = None,
        config: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> StrategyRecord:
        """Any change to spec/config/source creates a NEW immutable version.

        The new version starts over at DRAFT with an EMPTY evidence set:
        a prior version's results never certify the modified version.
        """
        rec = self._get(strategy_id)
        current = rec.version(rec.current_version)
        next_spec = current.spec if spec is None else dict(spec)
        next_config = current.config if config is None else dict(config)
        next_source = current.source if source is None else source
        if (
            _canonical_hash(next_spec) == current.spec_hash
            and _canonical_hash(next_config) == current.config_hash
            and _canonical_hash(next_source or "") == (current.source_hash or _canonical_hash(""))
        ):
            raise ValueError(
                "no material change: spec, config and source hashes identical "
                "to the current version — refusing to create a no-op version"
            )
        version_n = rec.current_version + 1
        version = StrategyVersion.create(
            version_n,
            current.strategy_type,
            next_spec,
            next_config,
            next_source,
            at,
            created_by,
        )
        updated = rec.model_copy(
            update={
                "current_version": version_n,
                "versions": rec.versions + (version,),
                "evidence": (),
                "state": LifecycleState.DRAFT,
            }
        )
        self._strategies[strategy_id] = updated
        self._event(at, "strategy_versioned", f"v{rec.current_version} -> v{version_n} (evidence reset)", strategy_id)
        return updated

    # -- lifecycle ----------------------------------------------------------
    def transition(
        self,
        strategy_id: str,
        target: LifecycleState,
        at: datetime,
        evidence: Optional[EvidenceRecord] = None,
        approval: Optional[OperatorApproval] = None,
    ) -> StrategyRecord:
        rec = self._get(strategy_id)
        current = rec.state
        version = rec.current_version

        if target is LifecycleState.LIVE_ACTIVE:
            raise LifecycleError(
                "REFUSED: LIVE_ACTIVE is not reachable — repository policy keeps "
                "live trading NOT AUTHORIZED; no live execution surface exists. "
                "Two-stage approval records exist only as governance metadata."
            )

        approval_evidence: Optional[EvidenceRecord] = None
        if target is LifecycleState.LIVE_APPROVED:
            if approval is None:
                raise LifecycleError(
                    "REFUSED: LIVE_APPROVED requires an explicit OperatorApproval "
                    "(human approval) — fail-closed"
                )
            if approval.strategy_id != strategy_id or approval.version != version:
                raise LifecycleError(
                    "operator approval scope mismatch — approval is bound to "
                    f"{approval.strategy_id} v{approval.version}, current is "
                    f"{strategy_id} v{version}; a prior version's approval never "
                    "certifies a modified version"
                )
            approval_evidence = EvidenceRecord(
                kind="operator_approval",
                version=version,
                reference=f"approval:{approval.signature[:8]}",
                recorded_at=approval.approved_at,
                recorded_by=approval.actor,
                summary=f"Approval 1 scope: {approval.scope}",
            )

        required_kind = _REQUIRED_EVIDENCE_BY_TARGET.get(target)
        if required_kind is not None:
            present = {e.kind for e in rec.evidence if e.version == version}
            if approval_evidence is not None:
                present.add(approval_evidence.kind)
            if evidence is not None and evidence.version == version:
                present.add(evidence.kind)
            if required_kind not in present:
                raise LifecycleError(
                    f"transition to {target.value} requires evidence "
                    f"'{required_kind}' bound to version {version} — missing or "
                    f"bound to another version (fail-closed)"
                )

        legal = _TRANSITIONS.get(current, ())
        if target not in legal:
            evidence_satisfied = (
                required_kind is not None
                and target in _EVIDENCE_GATED_ANALYTICAL
                and current not in _TERMINAL_STATES
            )
            if not evidence_satisfied:
                raise LifecycleError(
                    f"illegal transition {current.value} -> {target.value}; "
                    f"legal targets: {[t.value for t in legal] or 'NONE (terminal)'}"
                )

        appended = list(rec.evidence)
        if evidence is not None:
            if evidence.version != version:
                raise LifecycleError(
                    f"evidence bound to version {evidence.version} cannot affect "
                    f"version {version}"
                )
            appended.append(evidence)
        if approval_evidence is not None:
            appended.append(approval_evidence)

        updates: dict[str, Any] = {"state": target}
        if len(appended) != len(rec.evidence):
            updates["evidence"] = tuple(appended)
        if target is LifecycleState.ARCHIVED:
            updates["enabled"] = False
        updated = rec.model_copy(update=updates)
        self._strategies[strategy_id] = updated
        self._event(at, "lifecycle_transition", f"{current.value} -> {target.value}", strategy_id)
        return updated

    # -- management -----------------------------------------------------------
    def set_enabled(self, strategy_id: str, enabled: bool, at: datetime) -> StrategyRecord:
        rec = self._get(strategy_id)
        if rec.state is LifecycleState.ARCHIVED and enabled:
            raise LifecycleError("an archived strategy cannot be re-enabled; create a new strategy")
        updated = rec.model_copy(update={"enabled": enabled})
        self._strategies[strategy_id] = updated
        self._event(at, "strategy_enabled" if enabled else "strategy_disabled", "", strategy_id)
        return updated

    def add_evidence(self, strategy_id: str, evidence: EvidenceRecord) -> StrategyRecord:
        rec = self._get(strategy_id)
        if evidence.version != rec.current_version:
            raise LifecycleError(
                f"evidence for version {evidence.version} cannot be attached to "
                f"current version {rec.current_version} — prior evidence never "
                "certifies a modified version"
            )
        updated = rec.model_copy(update={"evidence": rec.evidence + (evidence,)})
        self._strategies[strategy_id] = updated
        return updated

    def get(self, strategy_id: str) -> StrategyRecord:
        return self._get(strategy_id)

    def all_strategies(self) -> tuple[StrategyRecord, ...]:
        return tuple(self._strategies.values())

    def __len__(self) -> int:
        return len(self._strategies)

    # -- internals ---------------------------------------------------------
    def _get(self, strategy_id: str) -> StrategyRecord:
        if strategy_id not in self._strategies:
            raise KeyError(f"unknown strategy {strategy_id!r}")
        return self._strategies[strategy_id]

    def _event(self, at: datetime, event: str, detail: str, ref: str) -> None:
        if self._audit is None:
            return
        self._audit.record(at, "strategy_lab", event, detail, ref)
