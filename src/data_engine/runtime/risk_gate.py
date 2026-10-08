"""Structural risk gate (pre-paper mandate §25 — CRITICAL).

The RiskGate is invoked by the authoritative TradingRuntime before
EVERY paper order. Checks (mandate §25 list, each fail-closed):

exposure · leverage · concentration · liquidity · spread ·
volatility · drawdown · loss limits · crash risk · stale data ·
model health · uncertainty · market status · order bounds ·
duplicate order · kill switch · SL · TP · risk/reward · paper mode

Guarantees:

- ANY mandatory check failure ⇒ ``passed=False`` ⇒ the order MUST
  NOT be sent. There is no override parameter, no warn-and-continue
  path, and no caller may bypass the gate: the OMS structurally
  refuses ``RISK_APPROVED`` without a PASSING assessment bound to
  the SAME order fingerprint (see :mod:`data_engine.runtime.oms`).
- Position-size limits delegate to the authoritative (BUG-003
  signed-netting corrected) ``RiskEngine.check_order``; the kill
  switch is consulted via the hierarchical manager AND the engine.
- Every assessment is identity-hashed and ledgered — the risk
  decision trail answers "what risk checks passed/failed?" forever.
"""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.risk.engine import (
    KillSwitchActiveError,
    RiskEngine,
    RiskViolationError,
)
from data_engine.runtime.contracts import (
    RuntimeContractError,
    TradePlan,
    UncertaintyReport,
)
from data_engine.runtime.identity import RISK_PREFIX, prefixed_hash
from data_engine.runtime.kill_switch import KillSwitchManager


class RiskGateError(RuntimeContractError):
    """Raised on risk-gate contract violations."""


class RiskCheckResult(BaseModel):
    """One check outcome with its explainable reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    passed: bool
    reason: str

    @field_validator("check", "reason")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RiskGateError("check fields must be non-empty")
        return v.strip()


MANDATORY_CHECKS = (
    "paper_mode",
    "kill_switch",
    "market_status",
    "data_staleness",
    "model_health",
    "uncertainty",
    "crash_risk",
    "order_bounds",
    "duplicate_order",
    "position_limit",
    "exposure",
    "leverage",
    "concentration",
    "liquidity",
    "spread",
    "volatility",
    "drawdown",
    "loss_limit",
    "stop_loss_presence",
    "take_profit_validity",
    "risk_reward",
)


class RiskContext(BaseModel):
    """Inputs the gate needs beyond the plan itself (fail-closed
    defaults: everything unknown is a FAILURE, never neutral)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equity: Decimal
    current_units: Decimal = Decimal("0")
    reference_price: Optional[Decimal] = None
    bar_volume: Optional[Decimal] = None
    last_bar_age_bars: Optional[int] = None
    market_open: bool = False
    paper_mode: bool = False
    model_valid: bool = False
    uncertainty: Optional[UncertaintyReport] = None
    crash_probability: Optional[float] = None
    max_acceptable_crash_probability: float = 0.20
    max_drawdown_fraction: Optional[float] = None
    drawdown_limit_fraction: float = 0.15
    daily_loss_limit_fraction: float = 0.03
    daily_realized_return: Optional[float] = None
    realized_pnl_today: Optional[Decimal] = None
    max_single_asset_weight: Decimal = Decimal("0.25")
    max_gross_leverage: Decimal = Decimal("1.0")
    min_risk_reward: float = 1.0
    max_spread_fraction: Optional[Decimal] = None
    half_spread: Optional[Decimal] = None
    volatility: Optional[float] = None
    max_volatility: Optional[float] = None
    min_volatility: Optional[float] = None
    duplicate_order_id: Optional[str] = None
    stale_data_max_age_bars: int = 2

    @field_validator("equity")
    @classmethod
    def _validate_equity(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise RiskGateError("equity must be positive finite")
        return v


class RiskAssessment(BaseModel):
    """Immutable full-gate verdict for one order intent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assessment_id: str
    trade_plan_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    limit_price: Optional[Decimal] = None
    passed: bool
    checks: tuple
    assessed_at: datetime
    correlation_id: str

    @field_validator("checks")
    @classmethod
    def _validate_checks(cls, v) -> tuple:
        if not v:
            raise RiskGateError("assessment requires >= 1 check")
        return tuple(v)

    @property
    def order_fingerprint(self) -> dict:
        return {
            "trade_plan_id": self.trade_plan_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": str(self.quantity),
            "order_type": self.order_type,
            "limit_price": str(self.limit_price)
            if self.limit_price is not None
            else None,
        }

    @property
    def failed_checks(self) -> tuple:
        return tuple(c for c in self.checks if not c.passed)


class RiskGate:
    """The authoritative pre-order risk gate (mandate §25)."""

    def __init__(
        self,
        engine: RiskEngine,
        kill_switch: KillSwitchManager,
    ) -> None:
        if engine is None or kill_switch is None:
            raise RiskGateError(
                "RiskGate requires BOTH the RiskEngine and the "
                "KillSwitchManager (wired, never optional — RT-F1)"
            )
        self._engine = engine
        self._kill_switch = kill_switch

    # ------------------------------------------------------------------
    def evaluate(
        self,
        plan: TradePlan,
        context: RiskContext,
        correlation_id: str,
        assessed_at: Optional[datetime] = None,
        ledger=None,
    ) -> RiskAssessment:
        """Evaluate every mandatory check; ledger the verdict."""
        checks: list = []

        def record(check: str, passed: bool, reason: str) -> None:
            checks.append(
                RiskCheckResult(check=check, passed=passed, reason=reason)
            )

        # Closing/reducing orders (netting that never increases
        # |position|) are the fail-safe direction: geometry checks
        # (SL/TP/R:R) do not apply to them, and they remain permitted
        # under an active kill switch — the switch blocks NEW
        # exposure, not risk reduction (mirrors the BUG-003 netting
        # discipline: reductions/closes never trip).
        signed_units = (
            plan.quantity if plan.side.value == "BUY" else -plan.quantity
        )
        current = context.current_units
        is_closing = (
            current != 0
            and (current > 0) != (signed_units > 0)
            and abs(signed_units) <= abs(current)
        )

        # 1. paper mode — never trade outside PAPER isolation (§59)
        record(
            "paper_mode",
            context.paper_mode,
            "runtime is in PAPER mode"
            if context.paper_mode
            else "runtime is NOT in paper mode — execution forbidden (§59)",
        )

        # 2. kill switch — hierarchical manager consult (§26)
        if is_closing:
            record(
                "kill_switch",
                True,
                "risk-reducing order: switch-aware close permitted "
                "(fail-safe direction; new exposure stays blocked)",
            )
        else:
            try:
                self._kill_switch.check(symbol=plan.symbol)
                record("kill_switch", True, "no governing kill switch active")
            except Exception as exc:
                record("kill_switch", False, str(exc))

        # 3. market status
        record(
            "market_status",
            context.market_open,
            "market open"
            if context.market_open
            else "market closed/halted — no execution",
        )

        # 4. data staleness (§10/§51 negative paths)
        if context.last_bar_age_bars is None:
            record("data_staleness", False,
                   "data freshness unknown — fail closed")
        else:
            fresh = context.last_bar_age_bars <= context.stale_data_max_age_bars
            record(
                "data_staleness",
                fresh,
                f"last bar age {context.last_bar_age_bars} bars "
                f"(max {context.stale_data_max_age_bars})"
                if fresh
                else f"STALE DATA: last bar age {context.last_bar_age_bars} "
                     f"bars exceeds max {context.stale_data_max_age_bars}",
            )

        # 5. model health
        record(
            "model_health",
            context.model_valid,
            "prediction model valid"
            if context.model_valid
            else "model invalid/unavailable — NO_TRADE (mandate §51)",
        )

        # 6. uncertainty thresholds (§18 hard NO_TRADE)
        unc = context.uncertainty or plan.uncertainty
        if unc.entropy is None or unc.ensemble_disagreement is None:
            record("uncertainty", False,
                   "uncertainty metadata incomplete — fail closed")
        else:
            ok = unc.confidence >= 0.55 and unc.entropy <= 0.95
            record(
                "uncertainty",
                ok,
                f"confidence={unc.confidence}, entropy={unc.entropy}, "
                f"disagreement={unc.ensemble_disagreement}"
                if ok
                else f"uncertainty too high: confidence={unc.confidence}, "
                     f"entropy={unc.entropy}, "
                     f"disagreement={unc.ensemble_disagreement}",
            )

        # 7. crash risk (§20 — strategy cannot override)
        if context.crash_probability is None:
            record("crash_risk", False,
                   "crash risk unknown — fail closed (never neutral)")
        else:
            ok = context.crash_probability <= context.max_acceptable_crash_probability
            record(
                "crash_risk",
                ok,
                f"crash probability {context.crash_probability} <= "
                f"{context.max_acceptable_crash_probability}"
                if ok
                else f"CRASH BLOCK: probability {context.crash_probability} "
                     f"> {context.max_acceptable_crash_probability}",
            )

        # 8. order bounds
        bounds_ok = plan.quantity > 0 and plan.notional > 0
        if context.reference_price is not None:
            bounds_ok = bounds_ok and (
                plan.quantity * context.reference_price
                <= plan.notional * Decimal("1.05")
            )
        record(
            "order_bounds",
            bounds_ok,
            "quantity/notional positive and consistent with reference price"
            if bounds_ok
            else "order bounds invalid (quantity/notional/price mismatch)",
        )

        # 9. duplicate order (idempotency-key duplicate)
        record(
            "duplicate_order",
            context.duplicate_order_id is None,
            "no duplicate order intent"
            if context.duplicate_order_id is None
            else f"duplicate order intent detected: {context.duplicate_order_id}",
        )

        # 10. position limit — authoritative engine (BUG-003 netting)
        try:
            self._engine.check_order(
                symbol=plan.symbol,
                units=signed_units,
                current_units=context.current_units,
            )
            record("position_limit", True,
                   "projected position within max_position_units")
        except KillSwitchActiveError as exc:
            record("position_limit", False, f"engine kill switch: {exc}")
        except RiskViolationError as exc:
            record("position_limit", False, str(exc))

        # 11. exposure (notional / equity)
        exposure = plan.notional / context.equity
        exposure_ok = exposure <= context.max_gross_leverage
        record(
            "exposure",
            exposure_ok,
            f"order exposure {exposure} of equity (max "
            f"{context.max_gross_leverage})"
            if exposure_ok
            else f"exposure {exposure} exceeds max {context.max_gross_leverage}",
        )

        # 12. leverage (projected gross incl. current exposure)
        current_notional = (
            abs(context.current_units) * context.reference_price
            if context.reference_price is not None
            else Decimal("0")
        )
        projected_gross = current_notional + plan.notional
        leverage = projected_gross / context.equity
        record(
            "leverage",
            leverage <= context.max_gross_leverage,
            f"projected gross leverage {leverage} (max "
            f"{context.max_gross_leverage})",
        )

        # 13. concentration (symbol weight)
        if context.reference_price is not None:
            symbol_exposure = projected_gross / context.equity
            conc_ok = symbol_exposure <= context.max_single_asset_weight
            record(
                "concentration",
                conc_ok,
                f"symbol exposure {symbol_exposure} (max "
                f"{context.max_single_asset_weight})"
                if conc_ok
                else f"concentration {symbol_exposure} exceeds "
                     f"{context.max_single_asset_weight}",
            )
        else:
            record("concentration", False,
                   "no reference price — concentration unverifiable")

        # 14. liquidity (order vs bar volume participation)
        if context.bar_volume is None or context.bar_volume <= 0:
            record("liquidity", False,
                   "bar volume unknown — liquidity unverifiable")
        else:
            liq_ok = plan.quantity <= Decimal("0.1") * context.bar_volume
            record(
                "liquidity",
                liq_ok,
                f"order is {plan.quantity / context.bar_volume} of bar volume"
                if liq_ok
                else f"order {plan.quantity} exceeds 10% of bar volume "
                     f"{context.bar_volume}",
            )

        # 15. spread
        if context.half_spread is None or context.reference_price is None:
            record("spread", False, "spread unknown — fail closed")
        else:
            spread_frac = (
                context.half_spread * 2 / context.reference_price
            )
            max_frac = context.max_spread_fraction or Decimal("0.005")
            record(
                "spread",
                spread_frac <= max_frac,
                f"round-trip spread {spread_frac} (max {max_frac})"
                if spread_frac <= max_frac
                else f"spread too wide: {spread_frac} > {max_frac}",
            )

        # 16. volatility sanity
        if context.volatility is None:
            record("volatility", False, "volatility unknown — fail closed")
        else:
            vol_ok = (
                context.volatility > 0
                and (context.max_volatility is None
                     or context.volatility <= context.max_volatility)
                and (context.min_volatility is None
                     or context.volatility >= context.min_volatility)
            )
            record(
                "volatility",
                vol_ok,
                f"volatility {context.volatility} within band"
                if vol_ok
                else f"volatility {context.volatility} outside band "
                     f"[{context.min_volatility}, {context.max_volatility}]",
            )

        # 17. drawdown
        if context.max_drawdown_fraction is None:
            record("drawdown", False, "drawdown unknown — fail closed")
        else:
            dd_ok = context.max_drawdown_fraction <= context.drawdown_limit_fraction
            record(
                "drawdown",
                dd_ok,
                f"drawdown {context.max_drawdown_fraction} <= limit "
                f"{context.drawdown_limit_fraction}"
                if dd_ok
                else f"drawdown {context.max_drawdown_fraction} exceeds "
                     f"limit {context.drawdown_limit_fraction}",
            )

        # 18. daily loss limit
        if context.daily_realized_return is None:
            record("loss_limit", False,
                   "daily P&L unknown — loss limit unverifiable")
        else:
            loss_ok = context.daily_realized_return >= -context.daily_loss_limit_fraction
            record(
                "loss_limit",
                loss_ok,
                f"daily return {context.daily_realized_return} within "
                f"limit -{context.daily_loss_limit_fraction}"
                if loss_ok
                else f"DAILY LOSS LIMIT HIT: {context.daily_realized_return} "
                     f"< -{context.daily_loss_limit_fraction}",
            )

        # 19/20. SL/TP — entry orders need protective geometry; closing
        # orders ARE the exit (no new risk is taken).
        if is_closing:
            record(
                "stop_loss_presence",
                True,
                "closing order — no new risk taken; protective levels "
                "inherited from the position being closed",
            )
            record(
                "take_profit_validity",
                True,
                "closing order — TP geometry not applicable",
            )
        else:
            record(
                "stop_loss_presence",
                plan.stop_loss is not None,
                "stop-loss attached to plan"
                if plan.stop_loss is not None
                else "NO STOP-LOSS — an unbounded-risk order is refused (§23/§25)",
            )
            if plan.take_profit is None:
                record("take_profit_validity", False,
                       "no take-profit attached — asymmetric plan refused")
            else:
                entry_ref = plan.entry.limit_price or context.reference_price
                if entry_ref is None:
                    record("take_profit_validity", False,
                           "no entry reference — TP geometry unverifiable")
                elif plan.side.value == "BUY":
                    tp_ok = plan.take_profit > entry_ref and (
                        plan.stop_loss is not None and plan.stop_loss < entry_ref
                    )
                    record("take_profit_validity", tp_ok,
                           "TP above entry, SL below entry (long geometry)"
                           if tp_ok else "invalid long TP/SL geometry")
                else:
                    tp_ok = plan.take_profit < entry_ref and (
                        plan.stop_loss is not None and plan.stop_loss > entry_ref
                    )
                    record("take_profit_validity", tp_ok,
                           "TP below entry, SL above entry (short geometry)"
                           if tp_ok else "invalid short TP/SL geometry")

        # 21. risk/reward — entry orders only
        if is_closing:
            record("risk_reward", True,
                   "closing order — risk/reward not applicable (risk removed)")
        else:
            entry_ref = plan.entry.limit_price or context.reference_price
            if entry_ref is None or plan.stop_loss is None or plan.take_profit is None:
                record("risk_reward", False,
                       "risk/reward unverifiable (missing entry/SL/TP)")
            else:
                risk = abs(entry_ref - plan.stop_loss)
                reward = abs(plan.take_profit - entry_ref)
                if risk <= 0:
                    record("risk_reward", False, "zero risk distance")
                else:
                    rr = float(reward / risk)
                    rr_ok = rr >= context.min_risk_reward
                    record(
                        "risk_reward",
                        rr_ok,
                        f"R/R {rr:.3f} >= {context.min_risk_reward}"
                        if rr_ok
                        else f"risk/reward {rr:.3f} below min "
                             f"{context.min_risk_reward}",
                    )

        passed = all(c.passed for c in checks)
        assessment = RiskAssessment(
            assessment_id="pending",
            trade_plan_id=plan.trade_plan_id,
            symbol=plan.symbol,
            side=plan.side.value,
            quantity=plan.quantity,
            order_type=plan.entry.order_type,
            limit_price=plan.entry.limit_price,
            passed=passed,
            checks=tuple(checks),
            assessed_at=assessed_at or datetime.now(UTC),
            correlation_id=correlation_id,
        )
        assessment = assessment.model_copy(
            update={
                "assessment_id": prefixed_hash(
                    RISK_PREFIX,
                    {
                        "kind": "risk_assessment",
                        "fingerprint": assessment.order_fingerprint,
                        "passed": passed,
                        "checks": [
                            {"check": c.check, "passed": c.passed,
                             "reason": c.reason}
                            for c in checks
                        ],
                        # BLOCKER 14: identity is a pure function of
                        # DECLARED fields — assessed_at is audit
                        # metadata (FS-21) and must never enter the
                        # identity hash (wall-clock contamination broke
                        # deterministic replay).
                        "correlation_id": correlation_id,
                    },
                )
            }
        )
        if ledger is not None:
            ledger.record(
                ledger="trade_plan",
                event_type="RISK_ASSESSMENT_" + ("PASS" if passed else "FAIL"),
                correlation_id=correlation_id,
                actor="runtime.risk_gate",
                payload={
                    "assessment_id": assessment.assessment_id,
                    "trade_plan_id": plan.trade_plan_id,
                    "passed": passed,
                    "failed_checks": [c.check for c in assessment.failed_checks],
                    "checks": [
                        {"check": c.check, "passed": c.passed}
                        for c in checks
                    ],
                },
                parent_id=plan.trade_plan_id,
            )
        return assessment


__all__ = [
    "RiskGateError",
    "RiskCheckResult",
    "MANDATORY_CHECKS",
    "RiskContext",
    "RiskAssessment",
    "RiskGate",
]
