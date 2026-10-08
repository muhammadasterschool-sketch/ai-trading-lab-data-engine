"""Runtime typed event contracts (pre-paper mandate §21/§22/§23/§31/§41).

Every runtime event is an immutable (``frozen=True, extra="forbid"``)
pydantic model with:

- a deterministic identity property (``*_id`` / ``*_hash``) computed
  from declared values ONLY — never from wall-clock (audit timestamps
  are a deliberate exception, mirroring the security-audit FS-21
  convention; they never participate in any identity);
- a ``correlation_id`` threading the whole
  data → prediction → decision → plan → risk → order → fill →
  position → exit → P&L → ledger chain (mandate §50: no orphan
  events);
- no order/execution authority — contracts are records, not actors.

The decision vocabulary is exactly the mandate §22 set:
BUY / SELL / REDUCE / HOLD / CLOSE / NO_TRADE — with NO_TRADE
mandatory and first-class.
"""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_engine.runtime.identity import (
    DECISION_PREFIX,
    EXIT_PREFIX,
    PREDICTION_PREFIX,
    RUNTIME_CONTRACT_VERSION,
    TRADE_PLAN_PREFIX,
    prefixed_hash,
)

#: Floats are rounded to 12 decimals before identity (prediction-layer
#: convention) so identical computations yield identical identities.
_IDENTITY_DECIMALS = 12


class RuntimeContractError(ValueError):
    """Raised on runtime contract violations."""


def _require_utc(v: datetime, name: str) -> datetime:
    if v is None or v.tzinfo is None:
        raise RuntimeContractError(f"{name} must be timezone-aware")
    return v.astimezone(UTC)


def freeze_number(value: Optional[float]) -> Optional[float]:
    """Round to the identity precision; reject non-finite values."""
    if value is None:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        raise RuntimeContractError(
            "non-finite float in runtime contract (NaN/inf fail closed)"
        )
    return round(float(value), _IDENTITY_DECIMALS)


def _freeze_mapping(values: Optional[Mapping[str, float]]) -> Optional[dict]:
    if values is None:
        return None
    return {k: freeze_number(v) for k, v in sorted(values.items())}


# ---------------------------------------------------------------------------
# State vocabularies
# ---------------------------------------------------------------------------

class RuntimeState(str, Enum):
    """Authoritative runtime operating states (mandate §32/§48/§60)."""

    INIT = "INIT"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"  # partial capability, trading still refused
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"  # mismatch: no new orders
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"  # restart: reconcile before resume
    EXECUTION_UNCERTAIN = "EXECUTION_UNCERTAIN"  # ambiguous outcome: reconcile
    HALTED = "HALTED"  # terminal safe stop (kill switch GLOBAL / operator)


#: Fail-closed trading states — no new order may be submitted in these.
NON_TRADING_STATES = frozenset(
    {
        RuntimeState.INIT,
        RuntimeState.DEGRADED,
        RuntimeState.RECONCILIATION_REQUIRED,
        RuntimeState.RECOVERY_REQUIRED,
        RuntimeState.EXECUTION_UNCERTAIN,
        RuntimeState.HALTED,
    }
)


class DecisionAction(str, Enum):
    """DecisionEngine output vocabulary (mandate §22) — CLOSED set."""

    BUY = "BUY"
    SELL = "SELL"
    REDUCE = "REDUCE"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    NO_TRADE = "NO_TRADE"


#: Actions that (if approved by risk) create a NEW or increased position.
ENTRY_ACTIONS = frozenset({DecisionAction.BUY, DecisionAction.SELL})
#: Actions that only reduce/close exposure.
EXIT_ACTIONS = frozenset({DecisionAction.REDUCE, DecisionAction.CLOSE})


class OrderLifecycle(str, Enum):
    """Authoritative OMS state machine (mandate §27).

    No order may jump directly from decision to FILLED — every
    transition follows this machine (see oms.py TRANSITIONS).
    """

    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    RISK_APPROVED = "RISK_APPROVED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    FAILED = "FAILED"


class ExitReason(str, Enum):
    """Complete exit vocabulary (mandate §31)."""

    SL_HIT = "SL_HIT"
    TP_HIT = "TP_HIT"
    SL_MODIFIED = "SL_MODIFIED"  # lifecycle event, not a fill exit
    TP_MODIFIED = "TP_MODIFIED"  # lifecycle event, not a fill exit
    RISK_EXIT = "RISK_EXIT"
    CRASH_EXIT = "CRASH_EXIT"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    SYSTEM_CLOSE = "SYSTEM_CLOSE"
    KILL_SWITCH_CLOSE = "KILL_SWITCH_CLOSE"


class MemoryCategory(str, Enum):
    """Structured trading-memory categories (mandate §41)."""

    MARKET = "MARKET"
    MODEL = "MODEL"
    PREDICTION = "PREDICTION"
    DECISION = "DECISION"
    TRADE = "TRADE"
    EXECUTION = "EXECUTION"
    RISK = "RISK"
    INCIDENT = "INCIDENT"
    PERFORMANCE = "PERFORMANCE"
    REGIME = "REGIME"
    CRASH = "CRASH"
    OPERATIONS = "OPERATIONS"


class UncertaintyReport(BaseModel):
    """Per-prediction uncertainty bundle (mandate §18)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence: float = Field(..., ge=0.0, le=1.0)
    entropy: Optional[float] = Field(None, ge=0.0)
    ensemble_disagreement: Optional[float] = Field(None, ge=0.0)
    epistemic_uncertainty: Optional[float] = Field(None, ge=0.0)
    aleatoric_uncertainty: Optional[float] = Field(None, ge=0.0)

    @property
    def is_high(self) -> bool:
        """True when ANY tracked uncertainty dimension is missing or
        high — missing evidence is uncertainty, not neutrality."""
        if self.entropy is None or self.ensemble_disagreement is None:
            return True
        return self.confidence < 0.5 or self.entropy > 0.9


# ---------------------------------------------------------------------------
# PredictionArtifact (mandate §21)
# ---------------------------------------------------------------------------

class PredictionArtifact(BaseModel):
    """Canonical immutable prediction artifact (mandate §21).

    Immutable after creation; every field the mandate lists is
    present. ``crash_risk`` carries the independent crash
    intelligence assessment (probability/severity/state summary);
    ``regime`` carries the timestamped regime state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction_id: str
    symbol: str
    horizon: int
    timestamp: datetime
    prediction: str  # UP / DOWN / FLAT (governed vocabulary)
    probability: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    volatility: float = Field(..., ge=0.0)
    uncertainty: UncertaintyReport
    model_versions: Tuple[str, ...]
    ensemble_composition: Optional[Mapping[str, float]] = None
    feature_version: str
    dataset_version: str
    regime: str
    crash_risk: Mapping[str, object]
    provenance: Mapping[str, str]
    correlation_id: str

    @field_validator("prediction_id", "symbol", "prediction",
                     "feature_version", "dataset_version", "correlation_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError(
                "prediction artifact text fields must be non-empty"
            )
        return v.strip()

    @field_validator("symbol", "prediction")
    @classmethod
    def _validate_vocab(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("horizon")
    @classmethod
    def _validate_horizon(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise RuntimeContractError("horizon must be an int >= 1")
        return v

    @field_validator("timestamp")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "timestamp")

    @field_validator("probability", "expected_return", "volatility")
    @classmethod
    def _freeze_floats(cls, v: float) -> float:
        return freeze_number(v)

    @field_validator("model_versions")
    @classmethod
    def _validate_models(cls, v: Sequence[str]) -> Tuple[str, ...]:
        if not v:
            raise RuntimeContractError(
                "model_versions must be non-empty (no anonymous predictions)"
            )
        return tuple(v)

    @model_validator(mode="after")
    def _validate_crash_governance(self) -> "PredictionArtifact":
        if "probability" not in self.crash_risk:
            raise RuntimeContractError(
                "crash_risk must carry 'probability' (crash intelligence "
                "is mandatory, never optional)"
            )
        return self

    @property
    def artifact_hash(self) -> str:
        return prefixed_hash(
            PREDICTION_PREFIX,
            {
                "kind": "prediction_artifact",
                "prediction_id": self.prediction_id,
                "symbol": self.symbol,
                "horizon": self.horizon,
                "timestamp": self.timestamp,
                "prediction": self.prediction,
                "probability": self.probability,
                "expected_return": self.expected_return,
                "volatility": self.volatility,
                "uncertainty": {
                    "confidence": self.uncertainty.confidence,
                    "entropy": self.uncertainty.entropy,
                    "ensemble_disagreement": self.uncertainty.ensemble_disagreement,
                    "epistemic_uncertainty": self.uncertainty.epistemic_uncertainty,
                    "aleatoric_uncertainty": self.uncertainty.aleatoric_uncertainty,
                },
                "model_versions": list(self.model_versions),
                "ensemble_composition": _freeze_mapping(self.ensemble_composition),
                "feature_version": self.feature_version,
                "dataset_version": self.dataset_version,
                "regime": self.regime,
                "crash_risk": dict(self.crash_risk),
                "provenance": dict(self.provenance),
                "correlation_id": self.correlation_id,
            },
        )


# ---------------------------------------------------------------------------
# Decision (mandate §22)
# ---------------------------------------------------------------------------

class RejectedAlternative(BaseModel):
    """One considered-and-rejected decision alternative (§22)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action: DecisionAction
    reason: str

    @field_validator("reason")
    @classmethod
    def _validate_reason(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("rejection reason must be non-empty")
        return v


class Decision(BaseModel):
    """One DecisionEngine output (mandate §22).

    The DecisionEngine has NO order authority — it records intent,
    context and rejected alternatives; the TradePlan/RiskGate/OMS
    chain decides execution.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    action: DecisionAction
    symbol: str
    timestamp: datetime
    prediction_ids: Tuple[str, ...]
    model_versions: Tuple[str, ...]
    uncertainty: UncertaintyReport
    regime: str
    crash_risk: Mapping[str, object]
    portfolio_state: Mapping[str, str]
    reason: str
    rejected_alternatives: Tuple[RejectedAlternative, ...] = ()
    correlation_id: str

    @field_validator("decision_id", "symbol", "reason", "correlation_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("decision text fields must be non-empty")
        return v.strip()

    @field_validator("timestamp")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "timestamp")

    @field_validator("prediction_ids", "model_versions")
    @classmethod
    def _validate_tuples(cls, v: Sequence[str]) -> Tuple[str, ...]:
        if not v:
            raise RuntimeContractError(
                "decisions must cite their evidence (prediction ids / "
                "model versions are mandatory)"
            )
        return tuple(v)

    @field_validator("reason")
    @classmethod
    def _validate_reason_depth(cls, v: str) -> str:
        if len(v.strip()) < 8:
            raise RuntimeContractError(
                "decision reason must be a real explanation, not a token"
            )
        return v

    @property
    def decision_hash(self) -> str:
        return prefixed_hash(
            DECISION_PREFIX,
            {
                "kind": "decision",
                "decision_id": self.decision_id,
                "action": self.action.value,
                "symbol": self.symbol,
                "timestamp": self.timestamp,
                "prediction_ids": list(self.prediction_ids),
                "model_versions": list(self.model_versions),
                "uncertainty": {
                    "confidence": self.uncertainty.confidence,
                    "entropy": self.uncertainty.entropy,
                    "ensemble_disagreement": self.uncertainty.ensemble_disagreement,
                },
                "regime": self.regime,
                "crash_risk": dict(self.crash_risk),
                "portfolio_state": dict(self.portfolio_state),
                "reason": self.reason,
                "rejected_alternatives": [
                    {"action": alt.action.value, "reason": alt.reason}
                    for alt in self.rejected_alternatives
                ],
                "correlation_id": self.correlation_id,
            },
        )


# ---------------------------------------------------------------------------
# TradePlan (mandate §23)
# ---------------------------------------------------------------------------

class EntryConstraints(BaseModel):
    """Entry constraints for a trade plan (mandate §23)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_type: str  # MARKET / LIMIT
    limit_price: Optional[Decimal] = None
    time_in_force: str = "GTC"  # GTC / DAY / TTL
    ttl_bars: Optional[int] = None

    @field_validator("order_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("MARKET", "LIMIT"):
            raise RuntimeContractError("order_type must be MARKET or LIMIT")
        return v

    @field_validator("time_in_force")
    @classmethod
    def _validate_tif(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("GTC", "DAY", "TTL"):
            raise RuntimeContractError("time_in_force must be GTC/DAY/TTL")
        return v

    @model_validator(mode="after")
    def _validate_limit_presence(self) -> "EntryConstraints":
        if self.order_type == "LIMIT" and self.limit_price is None:
            raise RuntimeContractError("LIMIT entries require a limit_price")
        if self.order_type == "MARKET" and self.limit_price is not None:
            raise RuntimeContractError("MARKET entries must not carry a limit")
        if self.time_in_force == "TTL" and (self.ttl_bars is None or self.ttl_bars < 1):
            raise RuntimeContractError("TTL entries require ttl_bars >= 1")
        return self


class TradePlan(BaseModel):
    """Canonical trade plan (mandate §23) — must pass RiskEngine
    before execution; carries the full model/safety context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_plan_id: str
    decision_id: str
    symbol: str
    side: DecisionAction  # BUY or SELL only
    quantity: Decimal
    notional: Decimal
    entry: EntryConstraints
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    risk_budget: Decimal
    expected_return: float
    risk_reward_ratio: float
    uncertainty: UncertaintyReport
    crash_risk: Mapping[str, object]
    model_context: Mapping[str, str]
    correlation_id: str

    @field_validator("trade_plan_id", "decision_id", "symbol", "correlation_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("trade plan text fields must be non-empty")
        return v.strip()

    @field_validator("side")
    @classmethod
    def _validate_side(cls, v: DecisionAction) -> DecisionAction:
        if v not in (DecisionAction.BUY, DecisionAction.SELL):
            raise RuntimeContractError(
                "trade plan side must be BUY or SELL — REDUCE/CLOSE are "
                "translated to netting quantities upstream"
            )
        return v

    @field_validator("quantity", "notional")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise RuntimeContractError(
                "quantity/notional must be positive finite Decimals"
            )
        return v

    @field_validator("risk_budget")
    @classmethod
    def _validate_risk_budget(cls, v: Decimal) -> Decimal:
        # risk_budget >= 0: entries carry a positive budget; closing/
        # reducing plans legitimately carry ZERO (they remove risk).
        if v is None or not v.is_finite() or v < 0:
            raise RuntimeContractError(
                "risk_budget must be a non-negative finite Decimal (zero "
                "only for pure risk-reducing plans)"
            )
        return v

    @field_validator("expected_return", "risk_reward_ratio")
    @classmethod
    def _freeze_floats(cls, v: float) -> float:
        return freeze_number(v)

    @model_validator(mode="after")
    def _validate_sl_tp_geometry(self) -> "TradePlan":
        # Geometric validation only applies to LIMIT entries where the
        # intended entry price is known at plan time; MARKET entries
        # are validated against the actual fill by the risk gate.
        ref = self.entry.limit_price
        if ref is None:
            return self
        if self.side is DecisionAction.BUY:
            if self.stop_loss is not None and self.stop_loss >= ref:
                raise RuntimeContractError(
                    "long stop-loss must sit below the limit entry"
                )
            if self.take_profit is not None and self.take_profit <= ref:
                raise RuntimeContractError(
                    "long take-profit must sit above the limit entry"
                )
        else:
            if self.stop_loss is not None and self.stop_loss <= ref:
                raise RuntimeContractError(
                    "short stop-loss must sit above the limit entry"
                )
            if self.take_profit is not None and self.take_profit >= ref:
                raise RuntimeContractError(
                    "short take-profit must sit below the limit entry"
                )
        return self

    @property
    def plan_hash(self) -> str:
        return prefixed_hash(
            TRADE_PLAN_PREFIX,
            {
                "kind": "trade_plan",
                "trade_plan_id": self.trade_plan_id,
                "decision_id": self.decision_id,
                "symbol": self.symbol,
                "side": self.side.value,
                "quantity": str(self.quantity),
                "notional": str(self.notional),
                "entry": {
                    "order_type": self.entry.order_type,
                    "limit_price": str(self.entry.limit_price)
                    if self.entry.limit_price is not None
                    else None,
                    "time_in_force": self.entry.time_in_force,
                    "ttl_bars": self.entry.ttl_bars,
                },
                "stop_loss": str(self.stop_loss) if self.stop_loss is not None else None,
                "take_profit": str(self.take_profit) if self.take_profit is not None else None,
                "risk_budget": str(self.risk_budget),
                "expected_return": self.expected_return,
                "risk_reward_ratio": self.risk_reward_ratio,
                "uncertainty": {
                    "confidence": self.uncertainty.confidence,
                    "entropy": self.uncertainty.entropy,
                    "ensemble_disagreement": self.uncertainty.ensemble_disagreement,
                },
                "crash_risk": dict(self.crash_risk),
                "model_context": dict(self.model_context),
                "correlation_id": self.correlation_id,
            },
        )


# ---------------------------------------------------------------------------
# ExitRecord (mandate §31)
# ---------------------------------------------------------------------------

class ExitRecord(BaseModel):
    """One position exit with complete linkage (mandate §31)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_id: str
    reason: ExitReason
    symbol: str
    timestamp: datetime
    position_quantity: Decimal  # quantity at exit time (signed)
    average_cost: Decimal
    order_ids: Tuple[str, ...]
    fill_ids: Tuple[str, ...]
    realized_pnl: Decimal
    correlation_id: str

    @field_validator("exit_id", "symbol", "correlation_id")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("exit text fields must be non-empty")
        return v.strip()

    @field_validator("timestamp")
    @classmethod
    def _validate_time(cls, v: datetime) -> datetime:
        return _require_utc(v, "timestamp")

    @property
    def exit_hash(self) -> str:
        return prefixed_hash(
            EXIT_PREFIX,
            {
                "kind": "exit_record",
                "exit_id": self.exit_id,
                "reason": self.reason.value,
                "symbol": self.symbol,
                "timestamp": self.timestamp,
                "position_quantity": str(self.position_quantity),
                "average_cost": str(self.average_cost),
                "order_ids": list(self.order_ids),
                "fill_ids": list(self.fill_ids),
                "realized_pnl": str(self.realized_pnl),
                "correlation_id": self.correlation_id,
            },
        )


__all__ = [
    "RUNTIME_CONTRACT_VERSION",
    "RuntimeContractError",
    "RuntimeState",
    "NON_TRADING_STATES",
    "DecisionAction",
    "ENTRY_ACTIONS",
    "EXIT_ACTIONS",
    "OrderLifecycle",
    "ExitReason",
    "MemoryCategory",
    "UncertaintyReport",
    "PredictionArtifact",
    "RejectedAlternative",
    "Decision",
    "EntryConstraints",
    "TradePlan",
    "ExitRecord",
    "freeze_number",
]
