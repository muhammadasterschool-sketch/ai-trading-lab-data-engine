"""Strategy submission pipeline + ACTIVATION GATE (Stage G, Part 9B G6).

Owner mandate (STRATEGY ACTIVATION GATE): NO strategy ever activates
without passing:
  1. an automated BACKTEST (strategy/backtest.py — evidence object),
  2. a 30-day paper validation cycle (the 30-day clock runs in real
     operation AFTER paper trading starts; this dev run builds and
     tests the automation with SHORT-CYCLE simulations), AND
  3. an explicit YES from the user — no answer or ambiguity keeps the
     strategy INACTIVE.
The gate is FAIL-CLOSED: every activation path checks all three
evidences; absent evidence = refusal; ``affirmative`` is a strict
boolean YES; nothing defaults to active.

Surface: users submit strategies through a chat-like structured form
+ free text (monitoring app; optional LLM assist for PARSING ONLY —
never for decisions). This module is the engine-side pipeline the
API surface drives; every transition is journaled to the decision
ledger (auditable).

States: SUBMITTED → BACKTESTED → VALIDATION_SCHEDULED → VALIDATED →
ACTIVATED (only via the gate) | REJECTED. INACTIVE is the honest
report for anything not activated.

LIVE TRADING REMAINS NOT AUTHORIZED. Activating a strategy enables
it for PAPER evaluation only — LIVE_ACTIVE is unreachable by
construction (no live path exists in this repository).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.ledgers import LedgerFamily

#: The ratified real-operation validation window (owner Part 3).
VALIDATION_CYCLE_DAYS = 30


class StrategyActivationError(RuntimeError):
    """Raised on pipeline-contract violations (fail closed)."""


class PipelineState(str, Enum):
    SUBMITTED = "SUBMITTED"
    BACKTESTED = "BACKTESTED"
    VALIDATION_SCHEDULED = "VALIDATION_SCHEDULED"
    VALIDATED = "VALIDATED"
    ACTIVATED = "ACTIVATED"
    REJECTED = "REJECTED"


#: The honest disposition for anything that is not ACTIVATED.
INACTIVE = "INACTIVE"


class BacktestEvidence(BaseModel):
    """Objective backtest evidence (produced by strategy/backtest.py
    or the operator's recorded run of it). Evidence is REQUIRED —
    numbers are never invented here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_id: str
    ran_at: datetime
    bars_tested: int
    trades: int
    total_return: Decimal
    max_drawdown: Decimal
    engine_version: str

    @field_validator("backtest_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise StrategyActivationError("backtest_id is required")
        return v.strip()

    @field_validator("bars_tested", "trades")
    @classmethod
    def _validate_counts(cls, v: int) -> int:
        if v is None or v < 0:
            raise StrategyActivationError("counts must be non-negative")
        return v


class ValidationEvidence(BaseModel):
    """Objective paper-validation evidence for the cycle window."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validation_id: str
    window_start: datetime
    window_end: datetime
    cycles_completed: int
    paper_trades: int
    anomalies: int

    @field_validator("cycles_completed", "paper_trades", "anomalies")
    @classmethod
    def _validate_counts(cls, v: int) -> int:
        if v is None or v < 0:
            raise StrategyActivationError("counts must be non-negative")
        return v


@dataclass(frozen=True)
class ActivationDecision:
    """The user's explicit answer to the activation question."""

    affirmative: bool  # YES (True) / NO (False) — nothing else
    decided_at: datetime
    decided_by: str
    note: str = ""

    @classmethod
    def yes(cls, *, decided_by: str, note: str = "",
            decided_at: Optional[datetime] = None) -> "ActivationDecision":
        return cls(
            affirmative=True,
            decided_at=decided_at or datetime.now(timezone.utc),
            decided_by=decided_by,
            note=note,
        )

    @classmethod
    def no(cls, *, decided_by: str, note: str = "",
           decided_at: Optional[datetime] = None) -> "ActivationDecision":
        return cls(
            affirmative=False,
            decided_at=decided_at or datetime.now(timezone.utc),
            decided_by=decided_by,
            note=note,
        )


class StrategySubmission(BaseModel):
    """A user-submitted strategy (structured form + free text)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    submission_id: str
    submitted_at: datetime
    submitted_by: str
    label: str
    structured_spec: Mapping[str, Any]
    free_text: str
    parse_source: str = "USER"  # USER | LLM_ASSIST_PARSE_ONLY

    @field_validator("label")
    @classmethod
    def _validate_label(cls, v: str) -> str:
        if not v or not v.strip():
            raise StrategyActivationError(
                "a strategy label is required (fail closed)"
            )
        return v.strip()

    @field_validator("structured_spec")
    @classmethod
    def _validate_spec(cls, v) -> Mapping[str, Any]:
        if not isinstance(v, Mapping) or not v:
            raise StrategyActivationError(
                "a structured spec is required (the structured form "
                "backing the free text; empty submissions are refused)"
            )
        return v

    @field_validator("parse_source")
    @classmethod
    def _validate_source(cls, v: str) -> str:
        allowed = {"USER", "LLM_ASSIST_PARSE_ONLY"}
        if v not in allowed:
            raise StrategyActivationError(
                f"parse_source must be one of {sorted(allowed)} — LLM "
                "output is parsing assistance ONLY and never a decision"
            )
        return v


@dataclass(frozen=True)
class StrategyRecord:
    """The full pipeline state for one submission (auditable)."""

    submission: StrategySubmission
    state: PipelineState
    backtest: Optional[BacktestEvidence] = None
    validation_window_end: Optional[datetime] = None
    validation: Optional[ValidationEvidence] = None
    decision: Optional[ActivationDecision] = None

    @property
    def disposition(self) -> str:
        return (
            "ACTIVATED" if self.state is PipelineState.ACTIVATED
            else INACTIVE
        )


class StrategyActivationGate:
    """The fail-closed strategy activation pipeline.

    Every transition is journaled to the ``decision`` ledger of the
    supplied :class:`LedgerFamily` (auditable end-to-end).
    """

    def __init__(self, ledger_family: LedgerFamily) -> None:
        if not isinstance(ledger_family, LedgerFamily):
            raise StrategyActivationError(
                "a LedgerFamily is required — every pipeline transition "
                "is journaled (auditability is part of the mandate)"
            )
        self._ledgers = ledger_family
        self._records: dict = {}

    # -- pipeline steps (each fail-closed) --------------------------------

    def submit(
        self,
        *,
        submitted_by: str,
        label: str,
        structured_spec: Mapping[str, Any],
        free_text: str,
        parse_source: str = "USER",
        submitted_at: Optional[datetime] = None,
        submission_id: Optional[str] = None,
    ) -> StrategySubmission:
        submission = StrategySubmission(
            submission_id=submission_id or f"strat-{id(self)}-{len(self._records)}",
            submitted_at=submitted_at or datetime.now(timezone.utc),
            submitted_by=submitted_by,
            label=label,
            structured_spec=structured_spec,
            free_text=free_text,
            parse_source=parse_source,
        )
        self._records[submission.submission_id] = StrategyRecord(
            submission=submission, state=PipelineState.SUBMITTED
        )
        self._journal(
            submission.submission_id, "STRATEGY_SUBMITTED",
            {"label": label, "parse_source": parse_source,
             "submitted_by": submitted_by},
        )
        return submission

    def record_backtest(
        self, submission_id: str, evidence: BacktestEvidence
    ) -> None:
        record = self._record(submission_id, PipelineState.SUBMITTED)
        if not isinstance(evidence, BacktestEvidence):
            raise StrategyActivationError(
                "objective BacktestEvidence is REQUIRED (evidence, never "
                "claims)"
            )
        self._records[submission_id] = StrategyRecord(
            submission=record.submission,
            state=PipelineState.BACKTESTED,
            backtest=evidence,
        )
        self._journal(
            submission_id, "STRATEGY_BACKTESTED",
            {"backtest_id": evidence.backtest_id,
             "bars_tested": evidence.bars_tested,
             "trades": evidence.trades,
             "total_return": str(evidence.total_return),
             "max_drawdown": str(evidence.max_drawdown)},
        )

    def schedule_validation(
        self,
        submission_id: str,
        *,
        cycle_days: int = VALIDATION_CYCLE_DAYS,
        now: Optional[datetime] = None,
    ) -> datetime:
        """Schedule the paper-validation cycle window.

        Real operation: 30 days (owner-ratified). This dev run may use
        SHORT cycles (``cycle_days`` < 30) to test the automation —
        the deviation is journaled explicitly, never silent.
        """
        record = self._record(submission_id, PipelineState.BACKTESTED)
        if cycle_days < 1:
            raise StrategyActivationError("cycle_days must be >= 1")
        start = now or datetime.now(timezone.utc)
        window_end = start + timedelta(days=cycle_days)
        self._records[submission_id] = StrategyRecord(
            submission=record.submission,
            state=PipelineState.VALIDATION_SCHEDULED,
            backtest=record.backtest,
            validation_window_end=window_end,
        )
        self._journal(
            submission_id, "STRATEGY_VALIDATION_SCHEDULED",
            {"window_start": start.isoformat(),
             "window_end": window_end.isoformat(),
             "cycle_days": cycle_days,
             "short_cycle_deviation": cycle_days < VALIDATION_CYCLE_DAYS,
             "note": (
                 f"owner-ratified real-operation cycle is "
                 f"{VALIDATION_CYCLE_DAYS} days; this window is "
                 f"{cycle_days} days"
                 if cycle_days < VALIDATION_CYCLE_DAYS
                 else "ratified 30-day cycle"
             )},
        )
        return window_end

    def record_validation(
        self, submission_id: str, evidence: ValidationEvidence,
        now: Optional[datetime] = None,
    ) -> None:
        record = self._record(
            submission_id, PipelineState.VALIDATION_SCHEDULED
        )
        if not isinstance(evidence, ValidationEvidence):
            raise StrategyActivationError(
                "objective ValidationEvidence is REQUIRED"
            )
        moment = now or datetime.now(timezone.utc)
        window_end = record.validation_window_end
        if window_end is None or moment < window_end:
            raise StrategyActivationError(
                "the validation window has NOT elapsed — evidence cannot "
                "be recorded before the cycle completes (fail closed; "
                f"window ends {window_end.isoformat() if window_end else '?'})"
            )
        self._records[submission_id] = StrategyRecord(
            submission=record.submission,
            state=PipelineState.VALIDATED,
            backtest=record.backtest,
            validation_window_end=window_end,
            validation=evidence,
        )
        self._journal(
            submission_id, "STRATEGY_VALIDATED",
            {"validation_id": evidence.validation_id,
             "cycles_completed": evidence.cycles_completed,
             "paper_trades": evidence.paper_trades,
             "anomalies": evidence.anomalies},
        )

    def activate(
        self, submission_id: str, decision: ActivationDecision
    ) -> StrategyRecord:
        """THE GATE (owner mandate): activation requires backtest
        evidence + completed validation evidence + an explicit YES.

        No answer / ambiguity / NO ⇒ the strategy stays INACTIVE (the
        record is returned with its honest disposition). Activation is
        PAPER-ONLY (live trading remains not authorized).
        """
        record = self._records.get(submission_id)
        if record is None:
            raise StrategyActivationError(
                f"unknown submission {submission_id!r} (fail closed)"
            )
        if record.state not in (
            PipelineState.VALIDATED, PipelineState.REJECTED
        ):
            # not yet at the decision point: any decision attempt is
            # journaled and the strategy stays INACTIVE (fail closed)
            self._journal(
                submission_id, "STRATEGY_ACTIVATION_REFUSED",
                {"reason": f"state is {record.state.value}, not VALIDATED",
                 "affirmative": bool(decision.affirmative)},
            )
            return record
        if not isinstance(decision, ActivationDecision):
            raise StrategyActivationError(
                "an explicit ActivationDecision is REQUIRED — no answer "
                "or ambiguity means INACTIVE (fail closed)"
            )
        # evidence chain re-checked AT THE GATE (defense in depth)
        if record.backtest is None or record.validation is None:
            self._journal(
                submission_id, "STRATEGY_ACTIVATION_REFUSED",
                {"reason": "evidence chain incomplete at the gate"},
            )
            return record
        if decision.affirmative is not True:
            self._journal(
                submission_id, "STRATEGY_ACTIVATION_DECLINED",
                {"decided_by": decision.decided_by,
                 "note": decision.note or "user answered NO/absent"},
            )
            return record
        activated = StrategyRecord(
            submission=record.submission,
            state=PipelineState.ACTIVATED,
            backtest=record.backtest,
            validation_window_end=record.validation_window_end,
            validation=record.validation,
            decision=decision,
        )
        self._records[submission_id] = activated
        self._journal(
            submission_id, "STRATEGY_ACTIVATED",
            {"decided_by": decision.decided_by,
             "note": decision.note,
             "mode": "PAPER_EVALUATION_ONLY",
             "live_trading": "NOT_AUTHORIZED"},
        )
        return activated

    def status(self, submission_id: str) -> dict:
        record = self._records.get(submission_id)
        if record is None:
            raise StrategyActivationError(
                f"unknown submission {submission_id!r}"
            )
        return {
            "submission_id": submission_id,
            "label": record.submission.label,
            "state": record.state.value,
            "disposition": record.disposition,
            "backtest": (
                {
                    "backtest_id": record.backtest.backtest_id,
                    "bars_tested": record.backtest.bars_tested,
                    "trades": record.backtest.trades,
                    "total_return": str(record.backtest.total_return),
                    "max_drawdown": str(record.backtest.max_drawdown),
                }
                if record.backtest else None
            ),
            "validation": (
                {
                    "validation_id": record.validation.validation_id,
                    "cycles_completed": record.validation.cycles_completed,
                    "paper_trades": record.validation.paper_trades,
                    "anomalies": record.validation.anomalies,
                }
                if record.validation else None
            ),
            "validation_window_end": (
                record.validation_window_end.isoformat()
                if record.validation_window_end else None
            ),
            "decision": (
                {
                    "affirmative": record.decision.affirmative,
                    "decided_by": record.decision.decided_by,
                    "decided_at": record.decision.decided_at.isoformat(),
                }
                if record.decision else None
            ),
        }

    def _record(
        self, submission_id: str, expected: PipelineState
    ) -> StrategyRecord:
        record = self._records.get(submission_id)
        if record is None:
            raise StrategyActivationError(
                f"unknown submission {submission_id!r} (fail closed)"
            )
        if record.state is not expected:
            raise StrategyActivationError(
                f"submission {submission_id!r} is {record.state.value}, "
                f"expected {expected.value} — pipeline order is strict "
                "(fail closed)"
            )
        return record

    def _journal(self, submission_id: str, event: str, payload: dict) -> None:
        self._ledgers.record(
            ledger="decision",
            event_type=event,
            correlation_id=f"strategy:{submission_id}",
            actor="runtime.strategy_activation_gate",
            payload=payload,
        )


__all__ = [
    "StrategyActivationGate",
    "StrategyActivationError",
    "StrategySubmission",
    "StrategyRecord",
    "PipelineState",
    "BacktestEvidence",
    "ValidationEvidence",
    "ActivationDecision",
    "VALIDATION_CYCLE_DAYS",
    "INACTIVE",
]
