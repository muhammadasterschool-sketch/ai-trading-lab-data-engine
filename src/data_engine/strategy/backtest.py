"""Deterministic historical backtesting engine for Phase 3.

Data flow:
    DATA → FEATURES → SIGNAL → ORDER → EXECUTION → POSITION → TRADE → EQUITY → METRICS → PROVENANCE

Properties:
- Chronological processing only
- No look-ahead bias
- No future-bar access
- Explicit signal timing
- Explicit execution timing
- Deterministic results
- Position state machine enforced
- Cash constraints enforced (no negative cash, no leverage)
- Maximum exposure enforced
- Execution delay handling (0 and 1)
- Missing OHLC handling
- Same-bar entry/exit impossibility
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, UTC
from pydantic import BaseModel, Field, ConfigDict, field_validator
from decimal import Decimal
import json
from data_engine.schemas import Dataset, Candle
from data_engine.strategy.schemas import (
    StrategySpec, OrderSide, ExitReason, OrderStatus,
    CostParameters, SlippageParameters, PositionSizingParameters,
    ExecutionConfig,
)
from data_engine.strategy.execution import ExecutionModel
from data_engine.strategy.ledger import Trade, TradeLedger
from data_engine.strategy.equity import EquityTracker, EquityPoint
from data_engine.strategy.position import PositionTracker
from data_engine.strategy.metrics import BacktestMetrics, periods_per_year as METRICS_PERIODS_PER_YEAR
from data_engine.strategy.provenance import BacktestProvenance, BacktestProvenanceTracker
from data_engine.quant.core import QuantEngine
from data_engine.data_blocked import DataQualityGate
import hashlib
import math


class BacktestConfig(BaseModel):
    """Configuration for a backtest run per Section K and design spec."""
    model_config = ConfigDict(frozen=True)

    initial_capital: float = Field(default=10000.0, gt=0)
    cost_parameters_serialized: str = ""
    slippage_parameters_serialized: str = ""
    allow_short: bool = Field(default=False)
    execution_semantics: str = "signal_at_t_close_execute_at_t_close"
    max_position_size: float = Field(default=1.0, ge=0)
    seed: Optional[int] = Field(None)
    execution_delay: int = Field(default=0, ge=0, le=1)
    max_exposure_pct: float = Field(default=100.0, ge=0, le=100)

    @field_validator("execution_delay")
    @classmethod
    def validate_execution_delay(cls, v: int) -> int:
        if v not in (0, 1):
            raise ValueError("execution_delay must be 0 or 1")
        return v

    def get_cost_parameters(self) -> CostParameters:
            try:
                data = json.loads(self.cost_parameters_serialized) if self.cost_parameters_serialized else {}
                if isinstance(data, dict):
                    return CostParameters(**data)
            except Exception:
                pass
            return CostParameters()

    def get_slippage_parameters(self) -> SlippageParameters:
        try:
            data = json.loads(self.slippage_parameters_serialized) if self.slippage_parameters_serialized else {}
            if isinstance(data, dict):
                return SlippageParameters(**data)
        except Exception:
            pass
        return SlippageParameters()


class BacktestResult(BaseModel):
    """Complete result of a backtest run per Section I and design spec."""

    backtest_id: str
    strategy_id: str
    strategy_version: str
    dataset_id: str
    dataset_version: str
    instrument: str
    timeframe: str
    initial_capital: float
    final_equity: float
    total_return: float
    trades: TradeLedger
    equity_curve: EquityTracker
    metrics: Optional[BacktestMetrics]
    config: Dict[str, Any]
    engine_version: str = "3.0.0"
    quant_engine_version: str = "2.0.0"
    spec_hash: str = ""
    result_hash: str = ""
    provenance: Optional[BacktestProvenance] = None

    @property
    def num_trades(self) -> int:
        return self.trades.total_trades()

    @property
    def num_closed_trades(self) -> int:
        return self.trades.total_closed()

    @property
    def total_net_pnl(self) -> float:
        return self.trades.total_net_pnl()

    @property
    def total_commissions(self) -> float:
        return self.trades.total_commissions()

    @property
    def total_slippage(self) -> float:
        return self.trades.total_slippage()


class BacktestEngine:
    """Deterministic historical backtesting engine.

    Processes data chronologically with no look-ahead.
    Every signal uses only current and past data.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()
        self.execution_model = ExecutionModel(
            cost_params=self.config.get_cost_parameters(),
            slippage_params=self.config.get_slippage_parameters(),
            execution_config=ExecutionConfig(execution_delay=self.config.execution_delay),
        )
        self.quant_engine = QuantEngine()
        self.data_quality_gate = DataQualityGate()
        self.provenance_tracker = BacktestProvenanceTracker()

    def run(
        self,
        strategy: StrategySpec,
        dataset: Dataset,
    ) -> BacktestResult:
        """Run a deterministic backtest.

        Args:
            strategy: The strategy specification
            dataset: Validated market dataset

        Returns:
            BacktestResult with all metrics, trades, equity, and provenance

        Raises:
            ValueError: If dataset fails quality gate
        """
        passed, error = self.data_quality_gate.check(dataset)
        if not passed:
            raise ValueError(f"Dataset blocked by quality gate: {error.failure_reason}")

        features = self._generate_features(strategy, dataset)
        trades, equity_points, equity_tracker = self._simulate(strategy, dataset, features)
        trade_ledger = TradeLedger(trades=trades)

        if equity_tracker is None:
            equity_tracker = EquityTracker(
                initial_capital=self.config.initial_capital,
                equity_curve=equity_points,
            )

        bt_id = self._generate_backtest_id(strategy, dataset)

        periods = METRICS_PERIODS_PER_YEAR.get(strategy.timeframe)
        metrics_from_trades = BacktestMetrics.from_trades(
            trades=trade_ledger,
            initial_capital=self.config.initial_capital,
            risk_free_rate=0.0,
            periods_per_year=periods,
        )
        metrics_from_equity = BacktestMetrics.from_equity_curve(
            equity_curve=equity_tracker.equity_curve,
            risk_free_rate=0.0,
            periods_per_year=periods,
        )
        all_metrics = self._merge_metrics(metrics_from_trades, metrics_from_equity)

        strategy_hash = strategy.to_hash()
        dataset_hash = self._compute_dataset_hash(dataset)
        config_hash = self._compute_config_hash()

        canonical_trades = self._canonical_trades_serialization(trade_ledger)
        canonical_equity = self._canonical_equity_serialization(equity_tracker.equity_curve)
        canonical_metrics = self._canonical_metrics_serialization(all_metrics)
        result_hash = self._compute_result_hash(
            strategy_hash=strategy_hash,
            dataset_hash=dataset_hash,
            canonical_trades=canonical_trades,
            canonical_equity=canonical_equity,
            canonical_metrics=canonical_metrics,
            config_hash=config_hash,
        )

        provenance = self.provenance_tracker.record(
            backtest_id=bt_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            strategy_hash=strategy_hash,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version.version,
            dataset_hash=dataset_hash,
            instrument=strategy.instrument,
            timeframe=strategy.timeframe,
            initial_capital=self.config.initial_capital,
            num_candles=len(dataset.candles),
            start_timestamp=dataset.candles[0].timestamp if dataset.candles else datetime.now(UTC),
            end_timestamp=dataset.candles[-1].timestamp if dataset.candles else datetime.now(UTC),
            cost_parameters=strategy.cost_parameters.model_dump(),
            slippage_parameters=strategy.slippage_parameters.model_dump(),
            position_sizing_parameters=strategy.position_sizing.model_dump(),
            execution_semantics="signal_at_t_close_execute_at_t_close" if self.config.execution_delay == 0
                else "signal_at_t_close_execute_at_t_plus_1_close",
            run_timestamp=datetime.now(UTC),
            result_hash=result_hash,
        )

        return BacktestResult(
            backtest_id=bt_id,
            strategy_id=strategy.strategy_id,
            strategy_version=strategy.strategy_version,
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.version.version,
            instrument=strategy.instrument,
            timeframe=strategy.timeframe,
            initial_capital=self.config.initial_capital,
            final_equity=equity_tracker.get_current_equity(),
            total_return=all_metrics.total_return or 0.0,
            trades=trade_ledger,
            equity_curve=equity_tracker,
            metrics=all_metrics,
            config=self.config.model_dump(),
            spec_hash=strategy_hash,
            result_hash=result_hash,
            provenance=provenance,
        )

    def _simulate(
        self,
        strategy: StrategySpec,
        dataset: Dataset,
        features: Dict[str, List[Optional[float]]],
    ) -> Tuple[List[Trade], List[EquityPoint], EquityTracker]:
        """Chronological simulation with full pipeline enforcement.

        Exit is processed BEFORE entry on each bar to enforce
        same-bar entry/exit impossibility.

        Returns:
            (trades, equity_points, equity_tracker)
        """
        trades: List[Trade] = []
        equity_points: List[EquityPoint] = []
        position = PositionTracker()
        cash = self.config.initial_capital
        candles = dataset.candles
        n = len(candles)
        delay = self.config.execution_delay

        for i in range(n):
            candle = candles[i]

            # Skip bars with missing OHLC data
            if candle.open is None or candle.high is None or candle.low is None or candle.close is None:
                current_equity = self._compute_equity(cash, position, candle.close if candle.close is not None else 0.0)
                pmv = 0.0
                if position.is_open:
                    if position.side == "LONG":
                        pmv = position.quantity * (candle.close if candle.close is not None else 0.0)
                    elif position.side == "SHORT":
                        pmv = -(position.quantity * (candle.close if candle.close is not None else 0.0))
                point = EquityPoint(
                    timestamp=candle.timestamp,
                    cash=cash,
                    position_market_value=pmv,
                    total_equity=current_equity,
                    position=position.quantity,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    cumulative_fees=sum(t.entry_commission + t.exit_commission for t in trades),
                    drawdown=0.0,
                    cumulative_return=current_equity / self.config.initial_capital - 1,
                    daily_return=None,
                )
                equity_points.append(point)
                continue

            close_price = candle.close
            timestamp = candle.timestamp

            # === EXIT phase: check exit conditions for open positions ===
            exit_occurred = False
            if position.is_open:
                exit_reason = self._check_exit_conditions(
                    strategy, features, i, position, close_price,
                )
                if exit_reason is not None:
                    exit_fill = close_price
                    exit_commission = self._compute_commission(exit_fill, position.quantity, position.side)
                    if trades:
                        trades[-1] = trades[-1].close(
                            exit_timestamp=timestamp,
                            exit_fill_price=exit_fill,
                            exit_reason=exit_reason,
                            exit_commission=exit_commission,
                        )
                    if position.side == "LONG":
                        cash = cash + (exit_fill * position.quantity) - exit_commission
                    else:
                        cash = cash - (exit_fill * position.quantity) - exit_commission
                    position = position.close_position(exit_fill, timestamp)
                    exit_occurred = True

            # === ENTRY phase: check entry conditions for flat accounts ===
            # A bar that executed an exit MUST NOT execute a new entry on the same bar.
            if not position.is_open and not exit_occurred:
                entry_signal = self._check_entry_conditions(strategy, features, i)
                if entry_signal:
                    exec_bar_idx = i + delay
                    if exec_bar_idx >= n:
                        continue
                    exec_candle = candles[exec_bar_idx]
                    if exec_candle.open is None or exec_candle.close is None:
                        continue

                    quantity = self._calculate_position_size(strategy, cash, close_price)
                    if quantity < 1:
                        continue

                    side_str = "LONG"
                    if strategy.allow_short and self._is_short_signal(strategy, features, i):
                        side_str = "SHORT"

                    requested_price = exec_candle.close
                    fill_price = self.execution_model.calculate_fill_price(
                        requested_price, side_str, self._get_atr(features, i)
                    )

                    entry_commission = self._compute_commission(fill_price, quantity, side_str)

                    if side_str == "LONG":
                        required_cash = fill_price * quantity + entry_commission
                        if required_cash > cash:
                            continue

                    # Maximum exposure enforcement
                    current_equity = self._compute_equity(cash, position, close_price)
                    exposure_limit = (self.config.max_exposure_pct / 100) * current_equity
                    new_gross_exposure = abs(fill_price * quantity)
                    if new_gross_exposure > exposure_limit:
                        continue

                    # Execute
                    if side_str == "LONG":
                        cash = cash - (fill_price * quantity) - entry_commission
                    else:
                        cash = cash + (fill_price * quantity) - entry_commission

                    position = position.open_position(
                        side=side_str,
                        quantity=quantity,
                        fill_price=fill_price,
                        timestamp=timestamp,
                    )

                    trade = Trade(
                        trade_id="",
                        side=OrderSide.LONG if side_str == "LONG" else OrderSide.SHORT,
                        entry_fill_price=fill_price,
                        quantity=quantity,
                        entry_commission=entry_commission,
                        exit_commission=0.0,
                        gross_pnl=0.0,
                        net_pnl=0.0,
                        entry_timestamp=timestamp,
                        slippage=abs(fill_price - requested_price) * quantity,
                    )
                    trades.append(trade)

            # Create equity point for this bar
            current_equity = self._compute_equity(cash, position, close_price)
            pmv = 0.0
            if position.is_open:
                if position.side == "LONG":
                    pmv = position.quantity * close_price
                elif position.side == "SHORT":
                    pmv = -(position.quantity * close_price)

            point = EquityPoint(
                timestamp=timestamp,
                cash=cash,
                position_market_value=pmv,
                total_equity=current_equity,
                position=position.quantity,
                unrealized_pnl=position.unrealized_pnl,
                realized_pnl=position.cumulative_pnl,
                cumulative_fees=sum(t.entry_commission + t.exit_commission for t in trades),
                drawdown=0.0,
                cumulative_return=current_equity / self.config.initial_capital - 1,
                daily_return=None,
            )
            equity_points.append(point)

        equity_tracker = EquityTracker(
            initial_capital=self.config.initial_capital,
            equity_curve=equity_points,
        )

        return trades, equity_points, equity_tracker

    def _check_entry_conditions(self, strategy: StrategySpec, features: Dict, i: int) -> bool:
        """Check if all entry conditions are met using only past/current data."""
        for condition in strategy.entry_conditions:
            values = features.get(condition.indicator, [])
            if i >= len(values):
                return False
            current_val = values[i]
            prev_val = values[i - 1] if i > 0 and condition.requires_previous else None
            if not condition.evaluate(current_val, prev_val):
                return False
        return True

    def _check_exit_conditions(
        self,
        strategy: StrategySpec,
        features: Dict,
        i: int,
        position: PositionTracker,
        close_price: float,
    ) -> Optional[ExitReason]:
        """Check exit conditions for an open position."""
        exit_reason = None

        if strategy.stop_loss_pct is not None and 0 < strategy.stop_loss_pct <= 100:
            if position.entry_fill_price is not None:
                # D4.1/D4.2/D4.4: Compute threshold directly in Decimal arithmetic
                # T = Decimal(str(entry)) × (Decimal('1') ± Decimal(str(pct)) / Decimal('100'))
                entry_decimal = Decimal(str(position.entry_fill_price))
                pct_decimal = Decimal(str(strategy.stop_loss_pct))
                pct_div_100 = pct_decimal / Decimal('100')
                threshold_decimal = (
                    entry_decimal * (Decimal('1') - pct_div_100)
                    if position.side == "LONG"
                    else entry_decimal * (Decimal('1') + pct_div_100)
                )
                # D4.6: Bridge actual price through Decimal.from_float
                price_decimal = Decimal.from_float(close_price)
                # D4.7: Inclusive boundaries
                if (position.side == "LONG" and price_decimal <= threshold_decimal) or \
                   (position.side == "SHORT" and price_decimal >= threshold_decimal):
                    exit_reason = ExitReason.STOP_LOSS

        if exit_reason is None and strategy.take_profit_pct is not None and 0 < strategy.take_profit_pct <= 100:
            if position.entry_fill_price is not None:
                # D4.1/D4.2/D4.4: Compute threshold directly in Decimal arithmetic
                # T = Decimal(str(entry)) × (Decimal('1') ± Decimal(str(pct)) / Decimal('100'))
                entry_decimal = Decimal(str(position.entry_fill_price))
                pct_decimal = Decimal(str(strategy.take_profit_pct))
                pct_div_100 = pct_decimal / Decimal('100')
                threshold_decimal = (
                    entry_decimal * (Decimal('1') + pct_div_100)
                    if position.side == "LONG"
                    else entry_decimal * (Decimal('1') - pct_div_100)
                )
                # D4.6: Bridge actual price through Decimal.from_float
                price_decimal = Decimal.from_float(close_price)
                # D4.7: Inclusive boundaries
                if (position.side == "LONG" and price_decimal >= threshold_decimal) or \
                   (position.side == "SHORT" and price_decimal <= threshold_decimal):
                    exit_reason = ExitReason.TAKE_PROFIT

        if exit_reason is None:
            for condition in strategy.exit_conditions:
                if condition.type == "signal":
                    values = features.get(condition.indicator, [])
                    if i < len(values) and values[i] is not None:
                        exit_reason = ExitReason.SIGNAL_EXIT
                        break

        return exit_reason

    def _calculate_position_size(self, strategy: StrategySpec, cash: float, price: float) -> float:
        """Calculate position size based on position sizing parameters."""
        sizing = strategy.position_sizing
        if sizing.method == "fixed":
            if sizing.fixed_quantity is None:
                raise ValueError("fixed method requires fixed_quantity")
            quantity = min(sizing.fixed_quantity, sizing.max_position_size)
        elif sizing.method == "percent":
            if sizing.percent_of_capital is None:
                raise ValueError("percent method requires percent_of_capital")
            target_notional = (sizing.percent_of_capital / 100) * cash
            if price <= 0:
                raise ValueError("sizing_price must be > 0")
            quantity = math.floor(target_notional / price)
            quantity = min(quantity, sizing.max_position_size)
        else:
            raise ValueError(f"Unknown position sizing method: {sizing.method}")

        if quantity < 1:
            return 0.0
        return quantity

    def _compute_equity(self, cash: float, position: PositionTracker, price: float) -> float:
        """Compute equity = cash + position_market_value."""
        if position.is_open:
            if position.side == "LONG":
                pmv = position.quantity * price
            elif position.side == "SHORT":
                pmv = -(position.quantity * price)
            else:
                pmv = 0.0
        else:
            pmv = 0.0
        return cash + pmv

    def _compute_commission(self, fill_price: float, quantity: float, side: str = "LONG") -> float:
        """Compute entry/exit commission via ExecutionModel."""
        return self.execution_model.calculate_commission(fill_price, quantity, side)

    def _generate_features(self, strategy: StrategySpec, dataset: Dataset) -> Dict[str, List[Optional[float]]]:
        """Generate all required indicator features using QuantEngine."""
        features = {}
        for indicator_name in strategy.required_indicators:
            try:
                result = self.quant_engine.calculate(indicator_name, dataset)
                features[indicator_name] = result.values
            except Exception:
                features[indicator_name] = [None] * len(dataset.candles)
        return features

    def _get_atr(self, features: Dict, i: int) -> Optional[float]:
        """Get ATR value for slippage calculation."""
        if "atr" in features and features["atr"][i] is not None:
            return features["atr"][i]
        return None

    def _is_short_signal(self, strategy: StrategySpec, features: Dict, i: int) -> bool:
        """Check if the current signal indicates a short position."""
        if not strategy.allow_short:
            return False
        # When allow_short=True, a short signal is permitted
        # Check if any entry condition indicates a short signal
        has_entry_conditions = len(strategy.entry_conditions) > 0
        if has_entry_conditions:
            for condition in strategy.entry_conditions:
                if condition.indicator is not None:
                    values = features.get(condition.indicator, [])
                    if i < len(values) and values[i] is not None:
                        if condition.evaluate(values[i], values[i-1] if i > 0 else None):
                            return True
            return False
        # No entry conditions: allow_short=True permits short position
        return True

    def _merge_metrics(self, t_metrics: BacktestMetrics, e_metrics: BacktestMetrics) -> BacktestMetrics:
        """Merge trade-based and equity-based metrics into a single BacktestMetrics."""
        result = e_metrics
        update_data = {}
        if t_metrics.total_return is not None:
            update_data["total_return"] = t_metrics.total_return
        if t_metrics.cumulative_return is not None:
            update_data["cumulative_return"] = t_metrics.cumulative_return
        if t_metrics.win_rate is not None:
            update_data["win_rate"] = t_metrics.win_rate
        if t_metrics.loss_rate is not None:
            update_data["loss_rate"] = t_metrics.loss_rate
        if t_metrics.breakeven_trades is not None:
            update_data["breakeven_trades"] = t_metrics.breakeven_trades
        if t_metrics.profit_factor is not None:
            update_data["profit_factor"] = t_metrics.profit_factor
        if t_metrics.expectancy is not None:
            update_data["expectancy"] = t_metrics.expectancy
        if t_metrics.average_trade is not None:
            update_data["average_trade"] = t_metrics.average_trade
        if t_metrics.median_trade is not None:
            update_data["median_trade"] = t_metrics.median_trade
        if t_metrics.average_win is not None:
            update_data["average_win"] = t_metrics.average_win
        if t_metrics.average_loss is not None:
            update_data["average_loss"] = t_metrics.average_loss
        if t_metrics.total_net_pnl != 0:
            update_data["total_net_pnl"] = t_metrics.total_net_pnl
        if t_metrics.total_commissions != 0:
            update_data["total_commissions"] = t_metrics.total_commissions
        if t_metrics.total_slippage != 0:
            update_data["total_slippage"] = t_metrics.total_slippage
        if t_metrics.total_trades > 0:
            update_data["total_trades"] = t_metrics.total_trades
            update_data["num_trades"] = t_metrics.num_trades

        return result.model_copy(update=update_data)

    def _compute_dataset_hash(self, dataset: Dataset) -> str:
        """Compute a content-based hash of the dataset per Section H canonical serialization."""
        from data_engine.strategy.schemas import _format_float, _escape
        records = []
        for candle in dataset.candles:
            record = (
                f"{_escape(str(candle.timestamp.isoformat()))}|"
                f"{_format_float(candle.open)}|{_format_float(candle.high)}|"
                f"{_format_float(candle.low)}|{_format_float(candle.close)}|"
                f"{_format_float(candle.volume) if candle.volume is not None else ''}"
            )
            records.append(record)
        candle_data = "\n".join(records) + ("\n" if records else "")
        data = (
            f"{_escape(dataset.dataset_id)}|{_escape(dataset.version.version)}|"
            f"{_escape(str(dataset.version.instrument.symbol))}|{_escape(str(dataset.version.timeframe))}|"
            f"{len(dataset.candles)}|{candle_data}"
            f"evidence_provenance={_escape(str(dataset.provenance.evidence_provenance.value))}"
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _compute_config_hash(self) -> str:
        """Compute config_hash per Section I config_hash specification.

        Field order: initial_capital|cost_parameters_serialized|slippage_parameters_serialized|
        allow_short|execution_semantics|max_position_size|seed|execution_delay
        """
        cost_str = self.config.cost_parameters_serialized
        slippage_str = self.config.slippage_parameters_serialized
        seed_str = f"{self.config.seed:.10f}" if self.config.seed is not None else "<NULL>"
        exec_semantics = self.config.execution_semantics
        data = (
            f"{self.config.initial_capital:.10f}|"
            f"{cost_str}|"
            f"{slippage_str}|"
            f"{int(self.config.allow_short)}|{exec_semantics}|"
            f"{self.config.max_position_size:.10f}|"
            f"{seed_str}|"
            f"{self.config.execution_delay}|"
            f"{self.config.max_exposure_pct:.10f}"
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _canonical_trades_serialization(self, trade_ledger: TradeLedger) -> str:
        """Serialize all trades in canonical format for result_hash."""
        from data_engine.strategy.provenance import canonical_trade_serialization
        records = [canonical_trade_serialization(t) for t in trade_ledger.trades]
        return "\n".join(records) + ("\n" if records else "")

    def _canonical_equity_serialization(self, equity_curve: List[EquityPoint]) -> str:
        """Serialize equity curve in canonical format per Section I."""
        records = []
        for p in equity_curve:
            record = (
                f"{p.timestamp.isoformat()}|"
                f"{p.total_equity:.10f}|"
                f"{p.cash:.10f}|"
                f"{p.position_market_value:.10f}"
            )
            records.append(record)
        return "\n".join(records) + ("\n" if records else "")

    def _canonical_metrics_serialization(self, metrics: BacktestMetrics) -> str:
        """Serialize metrics in canonical format per Section I."""
        records = []
        field_names = [
            "total_return", "cumulative_return", "annualized_return",
            "volatility", "sharpe_ratio", "sortino_ratio",
            "max_drawdown", "max_drawdown_duration", "recovery_duration",
            "win_rate", "loss_rate", "breakeven_trades",
            "profit_factor", "expectancy", "average_trade", "median_trade",
            "average_win", "average_loss", "turnover", "exposure",
        ]
        for name in field_names:
            value = getattr(metrics, name)
            if value is None:
                records.append(f"{name}|<NULL>")
            elif isinstance(value, float):
                if value == float('inf') or value == float('-inf'):
                    records.append(f"{name}|<NULL>")
                else:
                    records.append(f"{name}|{value:.10f}")
            elif isinstance(value, int):
                records.append(f"{name}|{value}")
            else:
                records.append(f"{name}|{value}")
        return "\n".join(records) + "\n"

    def _compute_result_hash(
        self,
        strategy_hash: str,
        dataset_hash: str,
        canonical_trades: str,
        canonical_equity: str,
        canonical_metrics: str,
        config_hash: str,
    ) -> str:
        """Compute SHA-256 of canonical_result_serialization per Section I."""
        canonical_result = (
            f"{strategy_hash}|{dataset_hash}|{canonical_trades}|"
            f"{canonical_equity}|{canonical_metrics}|{config_hash}"
        )
        return hashlib.sha256(canonical_result.encode("utf-8")).hexdigest()

    def _generate_backtest_id(self, strategy: StrategySpec, dataset: Dataset) -> str:
        """Generate a deterministic backtest ID."""
        data = f"{strategy.strategy_id}:{strategy.strategy_version}:{dataset.dataset_id}:{dataset.version.version}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
