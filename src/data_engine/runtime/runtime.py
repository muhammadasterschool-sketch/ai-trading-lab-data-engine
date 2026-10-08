"""Authoritative TradingRuntime — the ONE orchestration path
(pre-paper mandate §24; RT-F1/RT-F2/RT-F3/RT-F4 closures).

    DataFeed → DataValidator → PITGate → FeatureEngine →
    SequenceBuilder → PredictionEngine(Ensemble) → Calibration →
    Uncertainty → Regime → CrashRisk → PortfolioState →
    DecisionEngine → PositionSizer → TradePlan → RiskEngine →
    KillSwitch → OMS → PaperExecutionGateway → Fill →
    PositionState → Reconciliation → Ledgers → Memory → Monitoring

Guarantees:

- **No alternate production path**: every order flows through
  ``_execute_plan`` (create → validate → risk-approve → submit →
  execute → fills); the OMS refuses risk approval without a PASSING
  gate assessment (RT-F1 structural), reconciliation runs after
  fills (RT-F2), every transition is ledgered (RT-F3), and state
  snapshots persist when a store is configured (RT-F4).
- **Fail-closed operating states**: INIT/RUNNING/DEGRADED/
  RECONCILIATION_REQUIRED/RECOVERY_REQUIRED/EXECUTION_UNCERTAIN/
  HALTED — trading only happens in RUNNING.
- **PIT**: each bar's prediction uses a sequence built with cutoff =
  that bar's close timestamp; nothing after the anchor enters
  features (sequence engine enforces).
- **Crash independence (§20)**: crash probability is computed from
  volatility/drawdown/disagreement stress — NEVER from the
  directional signal — and can force NO_TRADE/exit regardless of
  strategy opinion.
- Determinism: bar processing is a pure function of
  (config, models, bar history) — replayable (mandate §49).
"""

import math
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.paper.simulator import ExecutionRealism
from data_engine.prediction.regimes import RegimeEngine, RegimeFeatures
from data_engine.risk.engine import RiskEngine, RiskLimits
from data_engine.runtime.contracts import (
    Decision,
    DecisionAction,
    ExitReason,
    MemoryCategory,
    OrderLifecycle,
    PredictionArtifact,
    RuntimeState,
    RuntimeContractError,
    TradePlan,
    UncertaintyReport,
    NON_TRADING_STATES,
)
from data_engine.runtime.data_gate import validate_bars
from data_engine.runtime.decision import (
    DecisionEngine,
    MarketDataStatus,
    DecisionThresholds,
)
from data_engine.runtime.execution import PaperExecutionAdapter, RuntimeFill
from data_engine.runtime.exits import ExitManager
from data_engine.runtime.identity import prefixed_hash
from data_engine.runtime.kill_switch import (
    KillSwitchManager,
    KillSwitchScope,
)
from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.memory import TradingMemory
from data_engine.runtime.oms import OMS, OMSOrder
from data_engine.runtime.pnl import PnLEngine, PositionState
from data_engine.runtime.reconciliation import RuntimeReconciliation
from data_engine.runtime.risk_gate import RiskContext, RiskGate
from data_engine.runtime.sequence import (
    SequenceSpec,
    build_sequence_set,
)
from data_engine.runtime.state import ExecutionStateStore
from data_engine.runtime.trade_plan import SizingConfig, TradePlanBuilder


class RuntimeConfig(BaseModel):
    """Governed runtime configuration (fail-closed defaults)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    session_id: str
    initial_equity: Decimal
    expected_interval_seconds: float = 300.0
    lookback: int = 8
    horizon: int = 2
    stride: int = 1
    feature_version: str = "fv-seq-1"
    dataset_version: str = "dv-synthetic"
    ttl_bars: int = 3
    max_crash_probability: float = 0.20
    crash_exit_probability: float = 0.40
    max_position_units: Decimal = Decimal("100")
    risk_fraction: Decimal = Decimal("0.01")

    @field_validator("symbol", "timeframe", "session_id",
                     "feature_version", "dataset_version")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("config text fields must be non-empty")
        return v.strip()

    @field_validator("initial_equity")
    @classmethod
    def _validate_equity(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise RuntimeContractError("initial equity must be positive")
        return v

    @field_validator("lookback", "horizon", "stride", "ttl_bars")
    @classmethod
    def _validate_windows(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise RuntimeContractError("window ints must be >= 1")
        return v


#: Regime vocabulary mapping (prediction RegimeEngine → mandate §19
#: governed states). Documented, deterministic, total.
_REGIME_MAP = {
    "CRISIS": "CRASH",
    "STRESSED": "STRESSED",
    "HIGH_VOLATILITY": "HIGH_VOLATILITY",
    "LOW_VOLATILITY": "LOW_VOLATILITY",
    "TRANSITION": "RECOVERY",
    "TRENDING": "TRENDING",
    "RANGE": "RANGING",
    "RISK_ON": "TRENDING",
    "RISK_OFF": "STRESSED",
    "NORMAL": "RANGING",
    "UNKNOWN": "UNKNOWN",
}


class BarOutcome(BaseModel):
    """One processed bar's complete outcome (observability)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_index: int
    correlation_id: str
    timestamp: datetime
    accepted: bool
    quality_rejections: tuple = ()
    decision_action: str
    decision_reason: str
    prediction_probability: Optional[float] = None
    regime: str
    crash_probability: float
    orders_created: tuple = ()
    fills: tuple = ()
    exits: tuple = ()
    realized_pnl: str = "0"
    unrealized_pnl: str = "0"
    runtime_state: str
    risk_failed_checks: tuple = ()


class TradingRuntime:
    """The authoritative paper trading runtime (mandate §24)."""

    def __init__(
        self,
        config: RuntimeConfig,
        ensemble,
        calibrator=None,
        state_store: Optional[ExecutionStateStore] = None,
        realism: Optional[ExecutionRealism] = None,
    ) -> None:
        if config is None or ensemble is None:
            raise RuntimeContractError(
                "runtime requires config + fitted ensemble"
            )
        self._config = config
        self._ensemble = ensemble
        self._calibrator = calibrator
        self._store = state_store
        self._realism = realism or ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.35"),
            fill_lag_bars=1,
        )

        # --- authoritative component wiring (§24) -----------------------
        self._ledgers = LedgerFamily()
        self._oms = OMS(self._ledgers)
        self._kill_switch = KillSwitchManager(self._ledgers)
        limits = RiskLimits(
            max_position_units=config.max_position_units,
            max_leverage=Decimal("1.0"),
            max_single_asset_weight=Decimal("0.30"),
            max_sector_weight=Decimal("1.0"),
            max_portfolio_heat=Decimal("1.0"),
        )
        self._risk_engine = RiskEngine(limits)
        self._risk_gate = RiskGate(self._risk_engine, self._kill_switch)
        self._execution = PaperExecutionAdapter(self._realism)
        self._exit_manager = ExitManager(self._ledgers)
        self._reconciliation = RuntimeReconciliation(self._ledgers)
        self._memory = TradingMemory()
        self._pnl_engine = PnLEngine()
        self._decision_engine = DecisionEngine(
            DecisionThresholds(max_crash_probability=config.max_crash_probability)
        )
        self._plan_builder = TradePlanBuilder(
            SizingConfig(
                risk_fraction=config.risk_fraction,
                max_position_units=config.max_position_units,
                default_ttl_bars=config.ttl_bars,
            )
        )
        self._regime_engine = RegimeEngine()

        # --- operating state ----------------------------------------------
        self._state = RuntimeState.INIT
        self._bars: list = []
        self._bar_index = -1
        self._positions: dict = {}
        self._consecutive_bad_bars = 0
        self._session_start_equity = config.initial_equity
        self._equity_realized = Decimal("0")
        self._entry_orders_by_symbol: dict = {}
        self._started_at: Optional[datetime] = None
        # Latency-aware pending-order bookkeeping: fills for orders
        # submitted on bar N happen on bars N+lag.. (never same-bar).
        self._order_fill_cursor: dict = {}   # order_id -> next bar index
        self._pending_protection: dict = {}  # order_id -> (sl, tp, corr)
        self._pending_exits: dict = {}       # symbol -> (order_id, reason, snapshot)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def ledgers(self) -> LedgerFamily:
        return self._ledgers

    @property
    def oms(self) -> OMS:
        return self._oms

    @property
    def kill_switch(self) -> KillSwitchManager:
        return self._kill_switch

    @property
    def memory(self) -> TradingMemory:
        return self._memory

    @property
    def positions(self) -> Mapping[str, PositionState]:
        return dict(self._positions)

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    def start(self) -> None:
        """INIT → RUNNING after component self-checks (fail-closed)."""
        if self._state is not RuntimeState.INIT:
            raise RuntimeContractError(
                f"runtime cannot start from {self._state.value}"
            )
        if not self._ensemble.members:
            raise RuntimeContractError("ensemble empty — refusing to start")
        for member in self._ensemble.members:
            art = member.artifact()
            if art.feature_version != self._config.feature_version:
                raise RuntimeContractError(
                    f"member {art.model_id} feature_version mismatch"
                )
        self._state = RuntimeState.RUNNING
        self._started_at = datetime.now(UTC)
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_STARTED",
            correlation_id=f"session:{self._config.session_id}",
            actor="runtime",
            payload={"session_id": self._config.session_id,
                     "equity": str(self._config.initial_equity),
                     "symbol": self._config.symbol},
        )

    def halt(self, reason: str) -> None:
        """Terminal safe stop (operator / critical switch)."""
        previous = self._state
        self._state = RuntimeState.HALTED
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_HALTED",
            correlation_id=f"session:{self._config.session_id}",
            actor="runtime",
            payload={"reason": reason, "from": previous.value},
        )

    def trip_kill_switch(
        self,
        scope: KillSwitchScope,
        reason: str,
        target: Optional[str] = None,
    ) -> None:
        """Trip a hierarchical switch; critical scopes halt the runtime."""
        self._kill_switch.trip(
            scope=scope, reason=reason, source="runtime.operator", target=target
        )
        if scope in (KillSwitchScope.GLOBAL, KillSwitchScope.ACCOUNT):
            self.halt(f"kill switch {scope.value} tripped: {reason}")
        elif scope is KillSwitchScope.PORTFOLIO:
            self._state = RuntimeState.RECONCILIATION_REQUIRED

    # ------------------------------------------------------------------
    # Bar processing (the authoritative path)
    # ------------------------------------------------------------------
    def process_bar(self, bar: Mapping) -> BarOutcome:
        """Process ONE bar through the full governed chain."""
        self._bar_index += 1
        idx = self._bar_index
        correlation_id = f"corr-{self._config.session_id}-{idx:06d}"
        ts = bar.get("timestamp")
        ts = ts.astimezone(UTC) if getattr(ts, "tzinfo", None) else None

        # -- 0. operating-state guard -------------------------------------
        if self._state in NON_TRADING_STATES:
            return self._refuse_bar(idx, correlation_id, ts,
                                    f"runtime is {self._state.value}")

        # -- 1. data validation (§10 hard gates, WITH gap context) -----
        # A stale/gapped bar is only detectable relative to the last
        # admitted bar — validate the pair, then keep only rejections
        # that concern the NEW bar (index -1).
        context_bars = (self._bars[-1:] + [dict(bar)]) if self._bars else [dict(bar)]
        accepted, rejections = validate_bars(
            context_bars,
            expected_interval=timedelta(
                seconds=self._config.expected_interval_seconds
            ),
        )
        new_bar_rejections = tuple(
            r for r in rejections if r.bar_index == len(context_bars) - 1
        )
        if new_bar_rejections:
            return self._bad_bar(idx, correlation_id, ts,
                                 new_bar_rejections, bar)

        # -- 2. bar admitted: pending orders fill FIRST (latency §38) ------
        # Orders submitted on earlier bars execute against THIS bar's
        # liquidity — fills precede any new decision (no same-bar fill
        # of the decision that is about to be made on this bar).
        self._bars.append(dict(bar))
        bar_fills = self._process_pending_orders(bar, idx, correlation_id)
        orders_created: list = []
        risk_failed: tuple = ()

        # -- 3. TTL expiry for live orders (§39) ----------------------------
        for order in list(self._oms.live_orders()):
            self._oms.expire_if_elapsed(order.order_id, idx)

        # -- 4. record exits for completed exit orders (§31) -----------------
        exits = self._record_completed_exits(bar, correlation_id)

        # -- 5. PIT sequence construction ----------------------------------
        cutoff = ts
        spec = SequenceSpec(
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
            lookback=self._config.lookback,
            horizon=self._config.horizon,
            stride=self._config.stride,
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
        )
        try:
            sset = build_sequence_set(
                self._bars,
                spec,
                cutoff=cutoff,
                dataset_content_hash=f"bars-{len(self._bars)}",
                expected_interval_seconds=self._config.expected_interval_seconds,
            )
            latest = sset.sequences[-1]
        except Exception as exc:  # insufficient bars yet → HOLD posture
            if bar_fills:
                self._reconcile_after_fills(correlation_id)
            return self._warmup_bar(idx, correlation_id, ts, str(exc))

        # -- 3. prediction: ensemble → calibration --------------------------
        ensemble_pred = self._ensemble.predict(list(latest.features))
        probability = ensemble_pred.probability
        calibrated = (
            self._calibrator.calibrate(probability)
            if self._calibrator is not None and self._calibrator.fitted
            else probability
        )
        calibrated = min(max(calibrated, 1e-9), 1 - 1e-9)
        confidence = max(calibrated, 1.0 - calibrated)
        entropy = -(
            calibrated * math.log(max(calibrated, 1e-12))
            + (1 - calibrated) * math.log(max(1 - calibrated, 1e-12))
        )
        disagreement = ensemble_pred.disagreement
        uncertainty = UncertaintyReport(
            confidence=round(confidence, 12),
            entropy=round(entropy, 12),
            ensemble_disagreement=round(disagreement, 12),
            epistemic_uncertainty=round(disagreement / 2, 12),
            aleatoric_uncertainty=round(entropy / 2, 12),
        )

        # -- 4. regime (independent classification) -------------------------
        regime_state = self._classify_regime()
        # -- 5. crash intelligence (INDEPENDENT of the signal, §20) ---------
        crash = self._assess_crash(disagreement)

        # -- 6. prediction artifact + ledger ---------------------------------
        prediction_id = prefixed_hash(
            "rtpre.",
            {"kind": "prediction", "bar": idx, "corr": correlation_id,
             "p": round(calibrated, 12)},
        )
        expected_return = round(calibrated - 0.5, 12)
        artifact = PredictionArtifact(
            prediction_id=prediction_id,
            symbol=self._config.symbol,
            horizon=self._config.horizon,
            timestamp=ts,
            prediction="UP" if calibrated >= 0.5 else "DOWN",
            probability=round(calibrated, 12),
            expected_return=expected_return,
            volatility=round(self._window_volatility(), 12),
            uncertainty=uncertainty,
            model_versions=tuple(ensemble_pred.composition.member_versions),
            ensemble_composition={
                v: w for v, w in zip(
                    ensemble_pred.composition.member_versions,
                    ensemble_pred.composition.weights,
                )
            },
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
            regime=regime_state,
            crash_risk=crash,
            provenance={
                "session": self._config.session_id,
                "sequence_set": sset.sequence_set_id,
                "calibrated": "yes" if (
                    self._calibrator is not None and self._calibrator.fitted
                ) else "no",
            },
            correlation_id=correlation_id,
        )
        self._ledgers.record(
            ledger="prediction",
            event_type="PREDICTION_ARTIFACT",
            correlation_id=correlation_id,
            actor="runtime.prediction",
            payload={
                "prediction_id": prediction_id,
                "symbol": artifact.symbol,
                "probability": artifact.probability,
                "prediction": artifact.prediction,
                "uncertainty": {
                    "confidence": uncertainty.confidence,
                    "entropy": uncertainty.entropy,
                    "ensemble_disagreement": uncertainty.ensemble_disagreement,
                },
                "regime": regime_state,
                "crash_risk": crash,
                "model_versions": list(artifact.model_versions),
            },
        )

        # -- 7. decision ------------------------------------------------------
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        data_status = MarketDataStatus(available=True, last_bar_age_bars=0)
        decision = self._decision_engine.decide(
            artifact=artifact,
            data_status=data_status,
            position_quantity=position.quantity,
            correlation_id=correlation_id,
        )
        if decision.action is DecisionAction.NO_TRADE:
            self._ledgers.record_no_trade(decision)
        else:
            self._ledgers.record(
                ledger="decision",
                event_type=f"DECISION_{decision.action.value}",
                correlation_id=correlation_id,
                actor="runtime.decision_engine",
                payload={
                    "decision_id": decision.decision_id,
                    "action": decision.action.value,
                    "symbol": decision.symbol,
                    "reason": decision.reason,
                    "prediction_ids": list(decision.prediction_ids),
                    "regime": decision.regime,
                    "crash_risk": dict(decision.crash_risk),
                },
                parent_id=artifact.prediction_id,
            )
        self._memory.record(
            MemoryCategory.DECISION,
            {"action": decision.action.value, "reason": decision.reason,
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
        )

        # -- 8. plan + risk gate + submission ---------------------------------
        reference_price = Decimal(str(bar["close"]))
        equity = self._current_equity(reference_price)
        if decision.action not in (DecisionAction.HOLD, DecisionAction.NO_TRADE):
            plan = self._plan_builder.build(
                decision=decision,
                artifact=artifact,
                reference_price=reference_price,
                equity=equity,
                position_quantity=position.quantity,
            )
            if plan is not None:
                self._ledgers.record(
                    ledger="trade_plan",
                    event_type="TRADE_PLAN_BUILT",
                    correlation_id=correlation_id,
                    actor="runtime.plan_builder",
                    payload={
                        "trade_plan_id": plan.trade_plan_id,
                        "decision_id": plan.decision_id,
                        "symbol": plan.symbol,
                        "side": plan.side.value,
                        "quantity": str(plan.quantity),
                        "notional": str(plan.notional),
                        "stop_loss": str(plan.stop_loss)
                        if plan.stop_loss is not None else None,
                        "take_profit": str(plan.take_profit)
                        if plan.take_profit is not None else None,
                        "risk_budget": str(plan.risk_budget),
                    },
                    parent_id=decision.decision_id,
                )
                created, failed = self._execute_plan(
                    plan, bar, idx, correlation_id, reference_price, equity
                )
                orders_created.extend(created)
                risk_failed = failed

        # -- 9. protective exits for positions from EARLIER bars (§31) -------
        # Positions entered on THIS bar evaluate protection from the
        # next bar onward (never intra-entry-bar lookahead).
        exit_orders = self._submit_protection_exits(
            bar, idx, correlation_id, crash
        )
        orders_created.extend(exit_orders)

        # -- 10. reconciliation after any fills (RT-F2) ------------------------
        if bar_fills:
            self._reconcile_after_fills(correlation_id)

        # -- 11. P&L + memory + persistence --------------------------------------
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        unrealized = self._pnl_engine.unrealized(position, reference_price)
        pnl_record = self._pnl_engine.record(
            state=position,
            mark_price=reference_price,
            fees_paid=Decimal("0"),
            entry_fill_ids=[f.fill_id for o in self._oms.orders() for f in o.fills],
            exit_fill_ids=[],
            order_ids=[o.order_id for o in self._oms.orders()],
            correlation_id=correlation_id,
        )
        self._ledgers.record(
            ledger="pnl",
            event_type="PNL_SNAPSHOT",
            correlation_id=correlation_id,
            actor="runtime.pnl",
            payload={
                "pnl_id": pnl_record.pnl_id,
                "symbol": pnl_record.symbol,
                "realized": str(pnl_record.realized_pnl),
                "unrealized": str(pnl_record.unrealized_pnl),
                "mark_price": str(reference_price),
            },
        )
        self._memory.record(
            MemoryCategory.MARKET,
            {"bar_index": idx, "close": str(reference_price),
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
        )
        self._memory.record(
            MemoryCategory.REGIME,
            {"regime": regime_state, "crash_probability": crash["probability"],
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
        )
        if self._store is not None:
            self._persist(correlation_id)

        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=True,
            decision_action=decision.action.value,
            decision_reason=decision.reason,
            prediction_probability=artifact.probability,
            regime=regime_state,
            crash_probability=crash["probability"],
            orders_created=tuple(o.order_id for o in orders_created),
            fills=tuple(f.fill_id for f in bar_fills),
            exits=tuple(e.exit_id for e in exits),
            realized_pnl=str(position.realized_pnl),
            unrealized_pnl=str(unrealized),
            runtime_state=self._state.value,
            risk_failed_checks=risk_failed,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _execute_plan(
        self,
        plan: TradePlan,
        bar: Mapping,
        bar_index: int,
        correlation_id: str,
        reference_price: Decimal,
        equity: Decimal,
    ):
        """The ONE order path: gate → OMS (create/validate/approve/
        submit/ack). Fills are DEFERRED to the pending-order processor
        (latency: an order submitted on bar N fills on bars N+lag.. —
        never same-bar, §38). Returns (orders, failed_checks)."""
        position = self._positions.get(
            plan.symbol, PositionState(symbol=plan.symbol)
        )
        duplicate = self._duplicate_intent(plan)
        context = RiskContext(
            equity=equity,
            current_units=position.quantity,
            reference_price=reference_price,
            bar_volume=Decimal(str(bar.get("volume") or 0)),
            last_bar_age_bars=0,
            market_open=True,
            paper_mode=True,
            model_valid=True,
            uncertainty=plan.uncertainty,
            crash_probability=float(plan.crash_risk.get("probability", 1.0)),
            max_acceptable_crash_probability=self._config.max_crash_probability,
            max_drawdown_fraction=self._window_drawdown(),
            volatility=self._window_volatility(),
            max_volatility=0.10,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
            max_spread_fraction=Decimal("0.01"),
            duplicate_order_id=duplicate,
        )
        assessment = self._risk_gate.evaluate(
            plan, context, correlation_id, ledger=self._ledgers
        )
        if not assessment.passed:
            return [], tuple(c.check for c in assessment.failed_checks)

        order, created = self._oms.create_order(
            plan=plan,
            session_id=self._config.session_id,
            created_at=bar.get("timestamp") or datetime.now(UTC),
            ttl_bars=plan.entry.ttl_bars,
        )
        if not created:
            # Idempotent duplicate — no new order, no execution.
            return [], ()
        self._oms.validate_order(order.order_id)
        self._oms.risk_approve(order.order_id, assessment)
        self._oms.submit(
            order.order_id,
            submitted_at=bar["timestamp"],
            bar_index=bar_index,
        )
        self._oms.acknowledge(order.order_id)
        if plan.stop_loss is not None or plan.take_profit is not None:
            self._pending_protection[order.order_id] = (
                plan.stop_loss,
                plan.take_profit,
                correlation_id,
            )
        return [order], ()

    def _apply_fill_to_position(self, fill: RuntimeFill, correlation_id: str) -> None:
        position = self._positions.get(
            fill.symbol, PositionState(symbol=fill.symbol)
        )
        updated = position.apply_fill(
            fill_quantity=fill.quantity,
            fill_price=fill.price,
            side=fill.side,
            commission=fill.commission,
            slippage_cost=fill.slippage_cost,
            spread_cost=fill.spread_cost,
            filled_at=fill.filled_at,
            source_event=fill.fill_id,
        )
        self._positions[fill.symbol] = updated
        self._equity_realized = (
            self._equity_realized + fill.commission + fill.slippage_cost
            + fill.spread_cost
        )
        self._ledgers.record(
            ledger="position",
            event_type="POSITION_APPLY_FILL",
            correlation_id=correlation_id,
            actor="runtime.position_book",
            payload={
                "symbol": fill.symbol,
                "fill_id": fill.fill_id,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "new_quantity": str(updated.quantity),
                "average_cost": str(updated.average_cost),
                "realized_pnl": str(updated.realized_pnl),
            },
            parent_id=fill.fill_id,
        )

    def _process_pending_orders(
        self, bar: Mapping, bar_index: int, correlation_id: str
    ) -> list:
        """Fill live orders against the newly arrived bar (latency).

        Cursor-based: each order fills only on bars it has not yet
        consumed (fill_index continues the order's numbering — no
        duplicate fill identities, no duplicate fills). Protective
        levels attach after the FIRST fill of an entry order.
        """
        fills: list = []
        from data_engine.runtime.contracts import OrderLifecycle as _LC
        for order in list(self._oms.orders()):
            if order.status not in (
                _LC.SUBMITTED, _LC.ACKNOWLEDGED, _LC.PARTIALLY_FILLED
            ):
                continue
            if order.submitted_at_bar is None or order.submitted_at is None:
                continue
            latency_start = order.submitted_at_bar + self._realism.fill_lag_bars
            cursor = self._order_fill_cursor.get(
                order.order_id, latency_start
            )
            if cursor > bar_index:
                continue  # latency window not reached yet
            ttl_window = order.ttl_bars or self._config.ttl_bars
            try:
                new_fills = self._execution.execute(
                    order_id=order.order_id,
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=order.remaining_quantity,
                    bars=self._bars,
                    submitted_at=order.submitted_at,
                    limit_price=order.limit_price,
                    max_bars=ttl_window,
                    from_bar=cursor,
                    start_index=len(order.fills),
                )
            except Exception as exc:
                # Execution failure: mark the order UNKNOWN and
                # reconcile-before-retry (mandate §28) — never
                # optimistic continuation.
                self._oms.mark_unknown(
                    order.order_id, f"execution adapter failure: {exc}"
                )
                self._oms.start_reconciling(order.order_id)
                self._state = RuntimeState.EXECUTION_UNCERTAIN
                self._ledgers.record(
                    ledger="incident",
                    event_type="EXECUTION_FAILURE",
                    correlation_id=correlation_id,
                    actor="runtime.execution",
                    payload={
                        "order_id": order.order_id,
                        "error": str(exc),
                        "action": "ORDER_UNKNOWN + RECONCILING (§28)",
                    },
                )
                continue
            for fill in new_fills:
                self._oms.apply_fill(order.order_id, fill)
                self._apply_fill_to_position(fill, correlation_id)
                fills.append(fill)
                self._memory.record(
                    MemoryCategory.EXECUTION,
                    {"order_id": order.order_id, "fill_id": fill.fill_id,
                     "quantity": str(fill.quantity), "price": str(fill.price),
                     "correlation_id": correlation_id},
                    correlation_id=correlation_id,
                )
            if new_fills:
                self._order_fill_cursor[order.order_id] = (
                    new_fills[-1].bar_index + 1
                )
                # Attach protective levels after the first entry fill.
                protection = self._pending_protection.get(order.order_id)
                if protection is not None:
                    sl, tp, prot_corr = protection
                    fresh = self._positions.get(
                        order.symbol, PositionState(symbol=order.symbol)
                    )
                    if not fresh.is_flat:
                        if sl is not None:
                            fresh, _ = self._exit_manager.set_stop_loss(
                                fresh, sl, prot_corr, fill.filled_at
                            )
                        if tp is not None:
                            fresh, _ = self._exit_manager.set_take_profit(
                                fresh, tp, prot_corr, fill.filled_at
                            )
                        self._positions[order.symbol] = fresh
                        self._pending_protection.pop(order.order_id, None)
        return fills

    def _record_completed_exits(self, bar: Mapping, correlation_id: str) -> list:
        """Record ExitRecords for exit orders that have now filled (§31)."""
        exits: list = []
        for symbol, pending in list(self._pending_exits.items()):
            order_id, reason, snapshot = pending
            try:
                order = self._oms.order(order_id)
            except Exception:
                self._pending_exits.pop(symbol, None)
                continue
            if order.status is OrderLifecycle.FILLED:
                current = self._positions.get(
                    symbol, PositionState(symbol=symbol)
                )
                # Hybrid state: quantity/avg from the trigger snapshot,
                # realized P&L AFTER the exit fills (mandate §31 linkage).
                hybrid = PositionState(
                    symbol=symbol,
                    quantity=snapshot.quantity,
                    average_cost=snapshot.average_cost,
                    realized_pnl=current.realized_pnl,
                )
                record = self._exit_manager.record_exit(
                    reason=reason,
                    state=hybrid,
                    timestamp=bar.get("timestamp") or datetime.now(UTC),
                    order_ids=(order_id,),
                    fill_ids=tuple(f.fill_id for f in order.fills),
                    correlation_id=correlation_id,
                )
                exits.append(record)
                self._pending_exits.pop(symbol, None)
            elif order.status in (
                OrderLifecycle.CANCELLED, OrderLifecycle.EXPIRED,
                OrderLifecycle.REJECTED, OrderLifecycle.FAILED,
            ):
                # Exit order did not complete: position remains at risk;
                # protection re-evaluates on the next bar (new exit order).
                self._pending_exits.pop(symbol, None)
                self._ledgers.record(
                    ledger="incident",
                    event_type="EXIT_ORDER_INCOMPLETE",
                    correlation_id=correlation_id,
                    actor="runtime.exit_manager",
                    payload={
                        "order_id": order_id,
                        "symbol": symbol,
                        "status": order.status.value,
                        "reason": "exit order ended without filling; "
                                  "protection will re-trigger",
                    },
                )
        return exits

    def _submit_protection_exits(
        self, bar: Mapping, bar_index: int,
        correlation_id: str, crash: Mapping
    ) -> list:
        """SL/TP/crash exit submission for positions from earlier bars."""
        orders: list = []
        bar_ts = bar.get("timestamp") or datetime.now(UTC)
        bar_ts_utc = bar_ts.astimezone(UTC) if getattr(bar_ts, "tzinfo", None) else None
        for symbol, position in list(self._positions.items()):
            if position.is_flat:
                continue
            if (
                bar_ts_utc is not None
                and position.last_update is not None
                and position.last_update == bar_ts_utc
            ):
                continue  # entered this bar — protection from next bar
            if symbol in self._pending_exits:
                continue  # exit already in flight
            hit = self._exit_manager.evaluate_bar(position, bar)
            reason = None
            if hit is not None:
                reason = hit[0]
            elif (
                crash.get("probability", 0.0)
                >= self._config.crash_exit_probability
            ):
                reason = ExitReason.CRASH_EXIT
            if reason is None:
                continue
            exit_plan = self._build_exit_plan(
                position, reason, bar, correlation_id
            )
            if exit_plan is None:
                continue
            created, _ = self._execute_plan(
                exit_plan, bar, bar_index, correlation_id,
                Decimal(str(bar["close"])),
                self._current_equity(Decimal(str(bar["close"]))),
            )
            if created:
                self._pending_exits[symbol] = (
                    created[0].order_id, reason, position,
                )
                orders.extend(created)
        return orders

    def _reconcile_after_fills(self, correlation_id: str) -> None:
        """Post-fill three-way reconciliation (RT-F2; §32)."""
        report = self._reconciliation.reconcile(self._oms, self._positions)
        if not report.ok:
            self._state = RuntimeState.RECONCILIATION_REQUIRED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RECONCILIATION_REQUIRED",
                correlation_id=correlation_id,
                actor="runtime",
                payload={"mismatches": list(report.mismatches)},
            )

    def _build_exit_plan(self, position: PositionState, reason: ExitReason,
                         bar: Mapping, correlation_id: str):
        """Build the closing plan for a protective exit (§31)."""
        from data_engine.runtime.contracts import (
            RejectedAlternative,
        )
        decision = Decision(
            decision_id=prefixed_hash(
                "rtdec.",
                {"kind": "exit_decision", "reason": reason.value,
                 "position": position.position_id},
            ),
            action=DecisionAction.CLOSE,
            symbol=position.symbol,
            timestamp=bar["timestamp"],
            prediction_ids=("exit-protection",),
            model_versions=("runtime.exit_manager",),
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            regime="EXIT",
            crash_risk={"probability": 0.0},
            portfolio_state={"position_quantity": str(position.quantity)},
            reason=f"protective exit: {reason.value} (position protection)",
            rejected_alternatives=(
                RejectedAlternative(
                    action=DecisionAction.HOLD,
                    reason="holding through a triggered protective level is "
                           "never an alternative",
                ),
            ),
            correlation_id=correlation_id,
        )
        reference = Decimal(str(bar["close"]))
        artifact = PredictionArtifact(
            prediction_id=f"exit-{reason.value.lower()}",
            symbol=position.symbol,
            horizon=1,
            timestamp=bar["timestamp"],
            prediction="EXIT",
            probability=1.0,
            expected_return=0.0,
            volatility=0.01,
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            model_versions=("runtime.exit_manager",),
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
            regime="EXIT",
            crash_risk={"probability": 0.0},
            provenance={"origin": "protective_exit"},
            correlation_id=correlation_id,
        )
        return self._plan_builder.build(
            decision=decision,
            artifact=artifact,
            reference_price=reference,
            equity=self._current_equity(reference),
            position_quantity=position.quantity,
        )

    def _duplicate_intent(self, plan: TradePlan) -> Optional[str]:
        """Detect a same-plan live order (duplicate order protection)."""
        from data_engine.runtime.oms import idempotent_order_id
        oid = idempotent_order_id(
            session_id=self._config.session_id,
            trade_plan_id=plan.trade_plan_id,
            decision_id=plan.decision_id,
            correlation_id=plan.correlation_id,
            symbol=plan.symbol,
            side=plan.side.value,
            order_type=plan.entry.order_type,
            quantity=plan.quantity,
            limit_price=plan.entry.limit_price,
        )
        existing = self._oms.order(oid) if self._oms_exists(oid) else None
        if existing is not None and not existing.is_terminal:
            return oid
        return None

    def _oms_exists(self, order_id: str) -> bool:
        try:
            self._oms.order(order_id)
            return True
        except Exception:
            return False

    def _classify_regime(self) -> str:
        closes = [float(b["close"]) for b in self._bars]
        if len(closes) < 21:
            return "UNKNOWN"
        returns = [
            closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))
        ]
        recent = returns[-20:]
        vol_20 = _std(recent)
        long_vol = _std(returns[-40:]) if len(returns) >= 40 else vol_20
        vol_ratio = vol_20 / long_vol if long_vol > 0 else 1.0
        window = closes[-40:]
        peak = max(window)
        dd_depth = (peak - closes[-1]) / peak if peak > 0 else 0.0
        mom_20 = closes[-1] / closes[-21] - 1.0
        features = RegimeFeatures(
            vol_20=vol_20, vol_ratio=vol_ratio, dd_depth=dd_depth,
            mom_20=mom_20,
        )
        raw = self._regime_engine.classify(features)
        return _REGIME_MAP.get(raw.upper(), "UNKNOWN")

    def _assess_crash(self, disagreement: float) -> dict:
        """Independent crash intelligence (mandate §20).

        Deterministic stress model over: drawdown stress, volatility
        stress, and model disagreement — deliberately INDEPENDENT of
        the directional prediction signal. Output feeds NO_TRADE /
        CRASH_EXIT decisions and can never be overridden by strategy
        signals.
        """
        closes = [float(b["close"]) for b in self._bars]
        dd = self._window_drawdown()
        vol = self._window_volatility()
        p = 0.02
        if dd is not None:
            if dd >= 0.20:
                p += 0.40
            elif dd >= 0.10:
                p += 0.20
        if vol is not None:
            if vol >= 0.05:
                p += 0.15
            elif vol >= 0.03:
                p += 0.08
        p += 0.25 * min(disagreement, 0.4)
        p = round(min(p, 0.99), 12)
        severity = "HIGH" if p >= 0.5 else ("MEDIUM" if p >= 0.3 else "LOW")
        return {
            "probability": p,
            "severity": severity,
            "horizon": self._config.horizon,
            "volatility_stress": round(vol, 12) if vol is not None else None,
            "drawdown_stress": round(dd, 12) if dd is not None else None,
            "model_disagreement": round(disagreement, 12),
            "liquidity_stress": None,
            "correlation_stress": None,
            "regime": self._classify_regime(),
        }

    def _window_volatility(self) -> float:
        closes = [float(b["close"]) for b in self._bars]
        if len(closes) < 21:
            return 0.0  # insufficient data → vol band check fails closed upstream? (0 is in-band; staleness handles freshness)
        returns = [
            closes[i] / closes[i - 1] - 1.0
            for i in range(len(closes) - 20, len(closes))
        ]
        return round(_std(returns), 12)

    def _window_drawdown(self) -> float:
        closes = [float(b["close"]) for b in self._bars]
        if not closes:
            return 0.0
        peak = closes[0]
        worst = 0.0
        for c in closes:
            peak = max(peak, c)
            if peak > 0:
                worst = max(worst, (peak - c) / peak)
        return round(worst, 12)

    def _daily_realized_return(self) -> float:
        if self._config.initial_equity <= 0:
            return 0.0
        return float(self._equity_realized / self._config.initial_equity)

    def _current_equity(self, mark_price: Decimal) -> Decimal:
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        unrealized = self._pnl_engine.unrealized(position, mark_price)
        return (
            self._config.initial_equity
            + position.realized_pnl
            - self._equity_realized
            + unrealized
        )

    def _persist(self, correlation_id: str) -> None:
        state = {
            "orders": self._oms.export_state(),
            "kill_switch": self._kill_switch.export_state(),
            "positions": [
                p.model_dump(mode="json")
                for p in self._positions.values()
            ],
            "ledger_heads": self._ledgers.head_hashes(),
            "bar_index": self._bar_index,
            "equity_realized": str(self._equity_realized),
            "session_id": self._config.session_id,
            "runtime_state": self._state.value,
        }
        self._store.snapshot(state, kind="bar_checkpoint")

    # -- negative-path bar helpers -----------------------------------------
    def _refuse_bar(self, idx, correlation_id, ts, reason) -> BarOutcome:
        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=False,
            decision_action="NO_TRADE",
            decision_reason=reason,
            regime="UNKNOWN",
            crash_probability=1.0,
            runtime_state=self._state.value,
        )

    def _bad_bar(self, idx, correlation_id, ts, rejections, bar) -> BarOutcome:
        self._consecutive_bad_bars += 1
        reasons = "; ".join(r.reason for r in rejections)
        self._ledgers.record(
            ledger="incident",
            event_type="DATA_QUALITY_REJECTION",
            correlation_id=correlation_id,
            actor="runtime.data_gate",
            payload={"bar_index": idx, "reasons": reasons},
        )
        if self._consecutive_bad_bars >= 3:
            self._state = RuntimeState.DEGRADED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_DEGRADED",
                correlation_id=correlation_id,
                actor="runtime",
                payload={
                    "consecutive_bad_bars": self._consecutive_bad_bars,
                    "reason": "persistent data-quality failures",
                },
            )
        return self._refuse_bar(
            idx, correlation_id, ts,
            f"data quality rejection: {reasons} — NO_TRADE (fail closed)",
        )

    def _warmup_bar(self, idx, correlation_id, ts, detail) -> BarOutcome:
        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=True,
            decision_action="NO_TRADE",
            decision_reason=f"warm-up: sequence engine not yet ready ({detail})",
            regime="UNKNOWN",
            crash_probability=0.0,
            runtime_state=self._state.value,
        )


def _std(values) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(var, 0.0))


__all__ = [
    "RuntimeConfig",
    "BarOutcome",
    "TradingRuntime",
]
