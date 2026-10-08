"""TradePlan builder (pre-paper mandate §23).

Translates a BUY/SELL decision + prediction artifact + current
position into a canonical :class:`TradePlan` with:

- risk-budget-derived position sizing (quantity from the stop
  distance, capped by the configured max position units);
- volatility-derived SL/TP geometry (SL = entry ∓ k·σ, TP = entry ±
  rr·k·σ — §38/§31 deterministic placement);
- entry constraints (order type / TTL);
- expected return, risk/reward, uncertainty, crash risk, model
  context, correlation id.

REDUCE/CLOSE decisions do not create risk-ADDING plans: they are
netted to closing quantities (the OMS submits them as orders that
reduce exposure; the risk gate's signed netting guarantees they
never breach). HOLD/NO_TRADE produce no plan at all.
"""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import (
    Decision,
    DecisionAction,
    EntryConstraints,
    PredictionArtifact,
    RuntimeContractError,
    TradePlan,
)
from data_engine.runtime.identity import TRADE_PLAN_PREFIX, prefixed_hash


class PlanError(RuntimeContractError):
    """Raised on trade-plan contract violations."""


class SizingConfig(BaseModel):
    """Governed sizing/geometry configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_fraction: Decimal = Decimal("0.01")  # of equity, per trade
    stop_volatility_multiple: Decimal = Decimal("2.0")  # SL = k·σ
    reward_risk_multiple: Decimal = Decimal("2.0")  # TP = rr·k·σ
    max_position_units: Decimal = Decimal("100")
    default_ttl_bars: int = 3

    @field_validator("risk_fraction")
    @classmethod
    def _validate_risk(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or not 0 < v <= 0.05:
            raise PlanError(
                "risk_fraction must be in (0, 0.05] — a single trade may "
                "never risk more than 5% of equity"
            )
        return v

    @field_validator("stop_volatility_multiple", "reward_risk_multiple")
    @classmethod
    def _validate_multiples(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise PlanError("volatility multiples must be positive")
        return v

    @field_validator("max_position_units")
    @classmethod
    def _validate_units(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise PlanError("max_position_units must be positive")
        return v

    @field_validator("default_ttl_bars")
    @classmethod
    def _validate_ttl(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise PlanError("default_ttl_bars must be >= 1")
        return v


class TradePlanBuilder:
    """Builds canonical trade plans from decisions (mandate §23)."""

    def __init__(self, config: Optional[SizingConfig] = None) -> None:
        self._config = config or SizingConfig()

    @property
    def config(self) -> SizingConfig:
        return self._config

    # ------------------------------------------------------------------
    def build(
        self,
        decision: Decision,
        artifact: PredictionArtifact,
        reference_price: Decimal,
        equity: Decimal,
        position_quantity: Decimal = Decimal("0"),
    ) -> Optional[TradePlan]:
        """Build the plan for a decision; None for HOLD/NO_TRADE.

        BUY/SELL create risk-adding entries; CLOSE creates a
        full-closing plan; REDUCE halves the current exposure.
        """
        if decision is None or artifact is None:
            raise PlanError("plan building requires decision + artifact")
        if reference_price is None or not reference_price.is_finite() or reference_price <= 0:
            raise PlanError("reference price must be positive finite")
        if equity is None or not equity.is_finite() or equity <= 0:
            raise PlanError("equity must be positive finite")
        if decision.action in (DecisionAction.HOLD, DecisionAction.NO_TRADE):
            return None

        cfg = self._config
        vol = Decimal(str(max(artifact.volatility, 1e-6)))
        stop_distance = cfg.stop_volatility_multiple * vol * reference_price
        take_distance = cfg.reward_risk_multiple * stop_distance

        if decision.action in (DecisionAction.BUY, DecisionAction.SELL):
            side = decision.action
            risk_budget = equity * cfg.risk_fraction
            if stop_distance <= 0:
                raise PlanError("stop distance collapsed — plan refused")
            quantity = risk_budget / stop_distance
            quantity = min(quantity, cfg.max_position_units)
            if quantity <= 0:
                raise PlanError("sizing produced zero quantity")
            if side is DecisionAction.BUY:
                stop_loss = reference_price - stop_distance
                take_profit = reference_price + take_distance
            else:
                stop_loss = reference_price + stop_distance
                take_profit = reference_price - take_distance
            notional = quantity * reference_price
        elif decision.action is DecisionAction.CLOSE:
            if position_quantity == 0:
                raise PlanError(
                    "CLOSE decision with a flat position — nothing to close"
                )
            side = DecisionAction.SELL if position_quantity > 0 else DecisionAction.BUY
            quantity = abs(position_quantity)
            notional = quantity * reference_price
            # Closing plans are pure exposure reductions: protective
            # levels are inherited from the position (no new geometry).
            stop_loss = None
            take_profit = None
            stop_distance = Decimal("0")
        else:  # REDUCE
            if position_quantity == 0:
                raise PlanError(
                    "REDUCE decision with a flat position — nothing to reduce"
                )
            side = DecisionAction.SELL if position_quantity > 0 else DecisionAction.BUY
            quantity = abs(position_quantity) / Decimal("2")
            notional = quantity * reference_price
            stop_loss = None
            take_profit = None
            stop_distance = Decimal("0")

        risk_budget = (
            equity * cfg.risk_fraction
            if stop_distance > 0
            else Decimal("0")
        )
        if decision.action in (DecisionAction.BUY, DecisionAction.SELL):
            risk = abs(reference_price - stop_loss)
            reward = abs(take_profit - reference_price)
            risk_reward = float(reward / risk) if risk > 0 else 0.0
        else:
            risk_reward = 0.0  # exits: no new risk taken

        trade_plan_id = prefixed_hash(
            TRADE_PLAN_PREFIX,
            {
                "kind": "trade_plan",
                "decision_id": decision.decision_id,
                "symbol": decision.symbol,
                "side": side.value,
                "quantity": str(quantity),
                "reference_price": str(reference_price),
                "correlation_id": decision.correlation_id,
            },
        )
        plan = TradePlan(
            trade_plan_id=trade_plan_id,
            decision_id=decision.decision_id,
            symbol=decision.symbol,
            side=side,
            quantity=Decimal(round(quantity, 8)),
            notional=Decimal(round(notional, 2)),
            entry=EntryConstraints(
                order_type="MARKET",
                time_in_force="TTL",
                ttl_bars=cfg.default_ttl_bars,
            ),
            stop_loss=Decimal(round(stop_loss, 6))
            if stop_loss is not None
            else None,
            take_profit=Decimal(round(take_profit, 6))
            if take_profit is not None
            else None,
            risk_budget=Decimal(round(risk_budget, 2)),
            expected_return=artifact.expected_return,
            risk_reward_ratio=risk_reward,
            uncertainty=artifact.uncertainty,
            crash_risk=dict(artifact.crash_risk),
            model_context={
                "model_versions": ",".join(artifact.model_versions),
                "feature_version": artifact.feature_version,
                "dataset_version": artifact.dataset_version,
                "regime": artifact.regime,
            },
            correlation_id=decision.correlation_id,
        )
        return plan


__all__ = [
    "PlanError",
    "SizingConfig",
    "TradePlanBuilder",
]
