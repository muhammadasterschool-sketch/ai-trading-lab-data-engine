"""Strategy-discovery data model (blueprint 5.20, mandate Phase 11).

Every candidate embeds the FROZEN Phase 3 ``StrategySpec`` as its
specification (reused, never modified) plus the mandate's required
metadata: parameter schema, feature dependencies, data dependencies,
risk assumptions, execution assumptions, and validation requirements.

Identity contract (ID-WC discipline inherited from 4A.1):

- ``candidate_hash = "disc20." + SHA-256(canonical(payload))`` — 70 chars.
- Identity is a pure function of the allowlisted values: generator
  contract version, template id, hypothesis hash, dataset hash, seed,
  and the candidate's spec hash. No wall clock, no RNG, no PID, no path.
- Wall-clock/audit fields (PROHIBITED_IDENTITY_FIELDS) never enter the
  identity payload — enforced structurally by construction, and the
  registry re-checks the payload keys.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.pit.hashing import (
    PROHIBITED_IDENTITY_FIELDS,
    deterministic_hash,
)
from data_engine.strategy.schemas import StrategySpec

#: Discovery-layer contract version (blueprint 5.20).
DISCOVERY_CONTRACT_VERSION = "1.0.0"

#: Identity prefix for strategy candidates.
CANDIDATE_HASH_PREFIX = "disc20."

#: Fields allowed in the candidate identity payload (positively declared).
_IDENTITY_ALLOWLIST: tuple[str, ...] = (
    "contract_version",
    "template_id",
    "hypothesis_hash",
    "dataset_hash",
    "seed",
    "spec_hash",
)


class CandidateStatus(str, Enum):
    """Lifecycle status of a generated strategy candidate."""

    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ParameterField(BaseModel):
    """One declared parameter: name, type, bounds, and grid values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    type: str = Field(pattern="^(number|boolean|string)$")
    low: Optional[float] = None
    high: Optional[float] = None
    grid: tuple[float, ...] = ()

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("parameter name must be a non-empty string")
        return v.strip()

    @field_validator("grid")
    @classmethod
    def _validate_grid(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if any(x is None for x in v):
            raise ValueError("grid values must be concrete numbers")
        if len(set(v)) != len(v):
            raise ValueError("grid values must be distinct")
        if list(v) != sorted(v):
            raise ValueError("grid values must be sorted ascending")
        return tuple(float(x) for x in v)


class ParameterSchema(BaseModel):
    """Declarative parameter schema for a candidate family."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fields: tuple[ParameterField, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


class DataDependencies(BaseModel):
    """What data a candidate requires (instrument, timeframe, features)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instrument: str
    timeframe: str
    feature_outputs: tuple[str, ...] = ()

    @field_validator("instrument", "timeframe")
    @classmethod
    def _validate_nonempty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("data dependencies must be non-empty strings")
        return v.strip()


class RiskAssumptions(BaseModel):
    """Declared risk assumptions (advisory metadata; enforcement stays
    with the Phase 8 risk engine, which candidates cannot override)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_position_units: float = Field(gt=0)
    stop_loss_pct: Optional[float] = Field(default=None, gt=0, le=100)
    take_profit_pct: Optional[float] = Field(default=None, gt=0, le=100)


class ExecutionAssumptions(BaseModel):
    """Declared execution assumptions (semantics/costs the spec encodes)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_semantics: str
    cost_included: bool = True
    slippage_included: bool = True

    @field_validator("execution_semantics")
    @classmethod
    def _validate_semantics(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("execution_semantics must be non-empty")
        return v.strip()


class ValidationRequirements(BaseModel):
    """Objective gates a candidate must pass before backtest eligibility."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_history_bars: int = Field(gt=0)
    require_walk_forward: bool = True
    require_out_of_sample: bool = True
    require_robustness_plateau: bool = False


class DiscoveryProvenance(BaseModel):
    """Where a candidate came from (deterministic, attributable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generator_id: str
    template_id: str
    hypothesis_hash: str = Field(min_length=16)
    dataset_hash: str = Field(min_length=16)
    seed: int = 0

    @field_validator("generator_id", "template_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("provenance ids must be non-empty strings")
        return v.strip()


class StrategyCandidate(BaseModel):
    """A generated strategy candidate with full governance metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    status: CandidateStatus = CandidateStatus.DRAFT
    spec: StrategySpec
    parameter_schema: ParameterSchema
    data_dependencies: DataDependencies
    risk_assumptions: RiskAssumptions
    execution_assumptions: ExecutionAssumptions
    validation_requirements: ValidationRequirements
    provenance: DiscoveryProvenance
    rejection_reason: Optional[str] = None

    @field_validator("candidate_id")
    @classmethod
    def _validate_candidate_id(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("candidate_id must be a non-empty string")
        return v.strip()

    @field_validator("rejection_reason")
    @classmethod
    def _validate_rejection(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("rejection_reason must be non-empty when set")
        return v

    @model_validator(mode="after")
    def _validate_status_reason(self) -> "StrategyCandidate":
        if self.status is CandidateStatus.REJECTED and not self.rejection_reason:
            raise ValueError("a REJECTED candidate must record its reason")
        if self.status is not CandidateStatus.REJECTED and self.rejection_reason:
            raise ValueError("only REJECTED candidates carry a reason")
        return self

    @property
    def spec_hash(self) -> str:
        """The frozen Phase 3 StrategySpec identity (deterministic)."""
        return self.spec.to_hash()

    @property
    def identity_payload(self) -> dict[str, Any]:
        """Positively-declared identity payload (allowlist only)."""
        payload = {
            "contract_version": DISCOVERY_CONTRACT_VERSION,
            "template_id": self.provenance.template_id,
            "hypothesis_hash": self.provenance.hypothesis_hash,
            "dataset_hash": self.provenance.dataset_hash,
            "seed": self.provenance.seed,
            "spec_hash": self.spec_hash,
        }
        illegal = PROHIBITED_IDENTITY_FIELDS & set(payload)
        if illegal:
            raise ValueError(
                f"prohibited identity fields present: {sorted(illegal)}"
            )
        return payload

    @property
    def candidate_hash(self) -> str:
        """Deterministic candidate identity: ``disc20.`` + SHA-256 hex."""
        return CANDIDATE_HASH_PREFIX + deterministic_hash(self.identity_payload)

    @property
    def record_digest(self) -> str:
        """Tamper-evidence digest over identity + lifecycle outcome.

        Covers the candidate identity AND its recorded status/reason so
        that registry chains detect outcome tampering (e.g., a REJECTED
        record silently flipped to VALIDATED).
        """
        return deterministic_hash(
            {
                "candidate_hash": self.candidate_hash,
                "status": self.status.value,
                "rejection_reason": self.rejection_reason,
            }
        )

    def with_status(
        self,
        status: CandidateStatus,
        rejection_reason: Optional[str] = None,
    ) -> "StrategyCandidate":
        """Return a copy with a new lifecycle status (immutability).

        Guards the status/reason pairing (a REJECTED candidate must
        carry a reason; only REJECTED candidates carry one).
        """
        if status is CandidateStatus.REJECTED and (
            rejection_reason is None or not rejection_reason.strip()
        ):
            raise ValueError(
                "a REJECTED candidate must record its reason"
            )
        if status is not CandidateStatus.REJECTED and rejection_reason:
            raise ValueError("only REJECTED candidates carry a reason")
        return self.model_copy(
            update={"status": status, "rejection_reason": rejection_reason},
            deep=True,
        )
