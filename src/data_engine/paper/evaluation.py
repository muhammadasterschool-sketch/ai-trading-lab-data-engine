"""Phase 11+ — 30-day paper evaluation, graduation, retirement (5.56-5.58)
and the Live Authorization Boundary (5.59).

Governance-critical module. Three hard rules:

1. **Full 30 days required** (5.58): an evaluation window shorter
   than 30 calendar days (measured from PROVIDED timestamps, never
   the wall clock) cannot produce a passing evaluation. Insufficient
   windows fail closed with INCOMPLETE status.

2. **No self-graduation** (5.56): graduation requires BOTH a passing
   30-day evaluation record AND an explicit human authorization
   token. Tokens are verified against an operator-maintained registry
   that starts EMPTY and can only be extended through
   :meth:`HumanAuthorizationRegistry.issue` — which requires a human
   principal identity and REFUSES machine principals. An agent can
   call the method; it cannot satisfy the human-principal precondition.

3. **The live boundary is NEVER authorized by this codebase**
   (5.59): :class:`LiveAuthorizationGate` ALWAYS denies live trading
   unless presented with a human-issued token from the registry — and
   the registry starts empty. Even WITH a valid token, the gate
   requires every phase-completion precondition to hold; the
   blueprint itself never issues the token, so the boundary cannot be
   crossed from inside the system.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal
from enum import Enum
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase contract version.
EVALUATION_CONTRACT_VERSION = "1.0.0"

#: Minimum paper evaluation window (blueprint 5.58).
MINIMUM_EVALUATION_DAYS = 30


class EvaluationError(ValueError):
    """Raised on evaluation-contract violations."""


class GraduationError(ValueError):
    """Raised on graduation/retirement contract violations."""


class ReadinessCriterion(BaseModel):
    """One named readiness criterion with a measured verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion_id: str
    description: str
    passed: bool
    measured_value: str

    @field_validator("criterion_id", "description", "measured_value")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("criterion fields must be non-empty strings")
        return v


class EvaluationStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class PaperEvaluationRecord(BaseModel):
    """A 30-day paper evaluation record with full evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    window_start: datetime
    window_end: datetime
    criteria: tuple[ReadinessCriterion, ...]
    no_trade_verified: bool

    @field_validator("strategy_id")
    @classmethod
    def _validate_strategy(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("strategy_id must be non-empty")
        return v.strip()

    @field_validator("window_start", "window_end")
    @classmethod
    def _validate_times(cls, v: datetime, info) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError(f"{info.field_name} must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_window(self) -> "PaperEvaluationRecord":
        if self.window_end <= self.window_start:
            raise EvaluationError("window_end must be after window_start")
        return self

    @property
    def window_days(self) -> int:
        return (self.window_end - self.window_start).days

    @property
    def status(self) -> EvaluationStatus:
        """COMPLETE only when the full 30 days AND all criteria AND
        NO-TRADE behavior verification hold."""
        if self.window_days < MINIMUM_EVALUATION_DAYS:
            return EvaluationStatus.INCOMPLETE
        if not self.no_trade_verified:
            return EvaluationStatus.INCOMPLETE
        if not all(c.passed for c in self.criteria):
            return EvaluationStatus.INCOMPLETE
        return EvaluationStatus.COMPLETE

    @property
    def evaluation_hash(self) -> str:
        return "eval11." + deterministic_hash(
            {
                "contract_version": EVALUATION_CONTRACT_VERSION,
                "strategy_id": self.strategy_id,
                "window_start": self.window_start,
                "window_end": self.window_end,
                "criteria": [
                    {
                        "criterion_id": c.criterion_id,
                        "description": c.description,
                        "passed": c.passed,
                        "measured_value": c.measured_value,
                    }
                    for c in self.criteria
                ],
                "no_trade_verified": self.no_trade_verified,
            }
        )


class EvaluationFramework:
    """Builds evaluation records; enforces the 30-day rule."""

    def evaluate(
        self,
        strategy_id: str,
        window_start: datetime,
        window_end: datetime,
        criteria: Sequence[ReadinessCriterion],
        no_trade_verified: bool,
    ) -> PaperEvaluationRecord:
        if not criteria:
            raise EvaluationError(
                "an evaluation without criteria is undefined (blueprint "
                "5.58: all readiness criteria evaluated)"
            )
        return PaperEvaluationRecord(
            strategy_id=strategy_id,
            window_start=window_start,
            window_end=window_end,
            criteria=tuple(criteria),
            no_trade_verified=no_trade_verified,
        )


class ReadinessChecker:
    """Standard readiness criteria (deterministic thresholds)."""

    @staticmethod
    def max_drawdown_criterion(drawdown: float, limit: float = 0.20) -> ReadinessCriterion:
        return ReadinessCriterion(
            criterion_id="max_drawdown",
            description="30-day max drawdown within limit",
            passed=drawdown <= limit,
            measured_value=f"{drawdown:.6f} <= {limit}",
        )

    @staticmethod
    def reconciliation_criterion(reconciled: bool) -> ReadinessCriterion:
        return ReadinessCriterion(
            criterion_id="reconciliation",
            description="All orders/fills/positions reconciled",
            passed=reconciled,
            measured_value=str(reconciled),
        )

    @staticmethod
    def reproducibility_criterion(reproducible: bool) -> ReadinessCriterion:
        return ReadinessCriterion(
            criterion_id="reproducibility",
            description="Strategy outputs reproducible",
            passed=reproducible,
            measured_value=str(reproducible),
        )


# ======================================================================
# Human authorization registry (5.56 / 5.59)
# ======================================================================

class HumanAuthorizationToken(BaseModel):
    """A human-issued authorization token (opaque, hash-verified)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    token_id: str
    human_principal_id: str
    purpose: str  # e.g. "graduation", "live_boundary"
    issued_at: datetime
    statement: str

    @field_validator("token_id", "human_principal_id", "purpose", "statement")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("token fields must be non-empty strings")
        return v.strip()

    @field_validator("issued_at")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("issued_at must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def token_hash(self) -> str:
        return "human11." + deterministic_hash(
            {
                "contract_version": EVALUATION_CONTRACT_VERSION,
                "token_id": self.token_id,
                "human_principal_id": self.human_principal_id,
                "purpose": self.purpose,
                "issued_at": self.issued_at,
                "statement": self.statement,
            }
        )


class HumanAuthorizationRegistry:
    """Operator-maintained registry of human authorization tokens.

    Starts EMPTY. ``issue`` requires a HUMAN principal identity —
    machine principals are refused. The registry is the ONLY path to
    a token, and only humans pass its gate: no agent can mint one.
    """

    #: Principal ids recognized as human operators (operator sets
    #: these explicitly when constructing the registry; the default is
    #: deliberately empty — an unset registry authorizes nothing).
    def __init__(self, human_principals: Optional[set[str]] = None) -> None:
        self._human_principals: set[str] = set(human_principals or ())
        self._tokens: dict[str, HumanAuthorizationToken] = {}

    @property
    def human_principals(self) -> frozenset[str]:
        return frozenset(self._human_principals)

    def issue(
        self,
        human_principal_id: str,
        purpose: str,
        statement: str,
        token_id: Optional[str] = None,
        issued_at: Optional[datetime] = None,
    ) -> HumanAuthorizationToken:
        """Issue a token — HUMAN principals only, fail closed."""
        if human_principal_id not in self._human_principals:
            raise GraduationError(
                f"principal {human_principal_id!r} is not a registered "
                "HUMAN operator — machine/self-issued authorization is "
                "structurally impossible (blueprint 5.56/5.59)"
            )
        token = HumanAuthorizationToken(
            token_id=token_id or f"tok-{len(self._tokens) + 1}",
            human_principal_id=human_principal_id,
            purpose=purpose,
            issued_at=issued_at or datetime.now(UTC),
            statement=statement,
        )
        if token.token_hash in self._tokens:
            raise GraduationError("duplicate token")
        self._tokens[token.token_hash] = token
        return token

    def verify(self, token: HumanAuthorizationToken, purpose: str) -> bool:
        stored = self._tokens.get(token.token_hash)
        if stored is None:
            return False
        if stored.purpose != purpose:
            return False
        return stored == token


# ======================================================================
# Graduation / retirement (5.56 / 5.57)
# ======================================================================

class GraduationDecision(BaseModel):
    """A graduation decision with its evidence chain."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    evaluation_hash: str
    authorization_token_hash: str
    graduated: bool
    rationale: str

    @property
    def decision_hash(self) -> str:
        return "grad11." + deterministic_hash(
            {
                "contract_version": EVALUATION_CONTRACT_VERSION,
                "strategy_id": self.strategy_id,
                "evaluation_hash": self.evaluation_hash,
                "authorization_token_hash": self.authorization_token_hash,
                "graduated": self.graduated,
                "rationale": self.rationale,
            }
        )


class RetirementDecision(BaseModel):
    """A retirement decision with documented evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: str
    evidence: tuple[str, ...]
    retired: bool
    rationale: str

    @property
    def decision_hash(self) -> str:
        return "ret11." + deterministic_hash(
            {
                "contract_version": EVALUATION_CONTRACT_VERSION,
                "strategy_id": self.strategy_id,
                "evidence": list(self.evidence),
                "retired": self.retired,
                "rationale": self.rationale,
            }
        )


class GraduationEvaluator:
    """Evaluates graduation: passing evaluation + human token, BOTH."""

    def __init__(self, registry: HumanAuthorizationRegistry) -> None:
        self._registry = registry

    def evaluate(
        self,
        evaluation: PaperEvaluationRecord,
        authorization: HumanAuthorizationToken,
    ) -> GraduationDecision:
        """Graduate only with a COMPLETE 30-day evaluation AND a
        verified human token for the graduation purpose."""
        evaluation_ok = evaluation.status is EvaluationStatus.COMPLETE
        token_ok = self._registry.verify(authorization, purpose="graduation")
        graduated = evaluation_ok and token_ok
        if not evaluation_ok:
            rationale = (
                f"evaluation {evaluation.evaluation_hash} is "
                f"{evaluation.status.value} — the 30-day rule and every "
                "readiness criterion must hold before graduation"
            )
        elif not token_ok:
            rationale = (
                "no verified human authorization token for graduation — "
                "AI self-graduation is impossible (blueprint 5.56)"
            )
        else:
            rationale = (
                "30-day evaluation complete and human authorization "
                "verified"
            )
        return GraduationDecision(
            strategy_id=evaluation.strategy_id,
            evaluation_hash=evaluation.evaluation_hash,
            authorization_token_hash=authorization.token_hash,
            graduated=graduated,
            rationale=rationale,
        )


class RetirementEvaluator:
    """Evaluates retirement: evidence-documented, human-authorized."""

    def __init__(self, registry: HumanAuthorizationRegistry) -> None:
        self._registry = registry

    def evaluate(
        self,
        strategy_id: str,
        evidence: Sequence[str],
        authorization: HumanAuthorizationToken,
    ) -> RetirementDecision:
        if not evidence:
            raise GraduationError(
                "retirement without documented evidence is forbidden "
                "(blueprint 5.57)"
            )
        token_ok = self._registry.verify(authorization, purpose="retirement")
        return RetirementDecision(
            strategy_id=strategy_id,
            evidence=tuple(evidence),
            retired=token_ok,
            rationale=(
                "human-authorized retirement with documented evidence"
                if token_ok else
                "no verified human authorization — strategy stays active"
            ),
        )


# ======================================================================
# Live authorization boundary (5.59) — NEVER authorized by this code
# ======================================================================

class LiveBoundaryDecision(BaseModel):
    """The live boundary gate's decision record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: str  # "DENIED" | "GRANTED"
    reasons: tuple[str, ...]
    decision_hash: str

    @property
    def granted(self) -> bool:
        return self.decision == "GRANTED"


class LiveAuthorizationGate:
    """The boundary between paper and live trading.

    DENIES by default. A grant requires ALL of:

    1. A verified human token with purpose "live_boundary".
    2. A COMPLETE 30-day evaluation record.
    3. A graduation decision that actually graduated.
    4. Production-infrastructure attestation flag.

    The blueprint itself NEVER issues the token — the registry starts
    empty and only human principals can extend it. Absent explicit
    out-of-band human action, this gate cannot grant anything.
    """

    def __init__(self, registry: HumanAuthorizationRegistry) -> None:
        self._registry = registry

    def evaluate_request(
        self,
        authorization: Optional[HumanAuthorizationToken] = None,
        evaluation: Optional[PaperEvaluationRecord] = None,
        graduation: Optional[GraduationDecision] = None,
        production_infra_attested: bool = False,
    ) -> LiveBoundaryDecision:
        reasons: list[str] = []
        granted = True

        if authorization is None or not self._registry.verify(
            authorization, purpose="live_boundary"
        ):
            granted = False
            reasons.append(
                "no verified human authorization token for the live "
                "boundary (the blueprint NEVER issues one — blueprint 5.59)"
            )
        if evaluation is None or evaluation.status is not EvaluationStatus.COMPLETE:
            granted = False
            reasons.append("30-day evaluation missing or incomplete")
        if graduation is None or not graduation.graduated:
            granted = False
            reasons.append("strategy has not graduated")
        if not production_infra_attested:
            granted = False
            reasons.append("production infrastructure not attested")

        decision = "GRANTED" if granted else "DENIED"
        decision_hash = "live11." + deterministic_hash(
            {
                "contract_version": EVALUATION_CONTRACT_VERSION,
                "decision": decision,
                "reasons": reasons,
                "authorization_token_hash": (
                    authorization.token_hash if authorization else None
                ),
                "evaluation_hash": (
                    evaluation.evaluation_hash if evaluation else None
                ),
                "graduation_decision_hash": (
                    graduation.decision_hash if graduation else None
                ),
                "production_infra_attested": production_infra_attested,
            }
        )
        return LiveBoundaryDecision(
            decision=decision,
            reasons=tuple(reasons),
            decision_hash=decision_hash,
        )

    def default_decision(self) -> LiveBoundaryDecision:
        """The decision with NO evidence supplied: pure DENIAL."""
        return self.evaluate_request()


__all__ = [
    "MINIMUM_EVALUATION_DAYS",
    "EvaluationStatus",
    "ReadinessCriterion",
    "PaperEvaluationRecord",
    "EvaluationFramework",
    "ReadinessChecker",
    "HumanAuthorizationToken",
    "HumanAuthorizationRegistry",
    "GraduationDecision",
    "RetirementDecision",
    "GraduationEvaluator",
    "RetirementEvaluator",
    "LiveBoundaryDecision",
    "LiveAuthorizationGate",
    "EvaluationError",
    "GraduationError",
]
