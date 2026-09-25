"""Backtest provenance tracking for Phase 3.

Every backtest result contains enough metadata to reproduce
the exact experiment. Run timestamps are excluded from result_hash.

The result_hash is SHA-256 of the canonical_result_serialization
per Section I of the design document.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
import hashlib
import json

from data_engine.strategy.schemas import (
    CostParameters, SlippageParameters, PositionSizingParameters,
)


def _format_float(value: float) -> str:
    """Format a float as .10f per canonical serialization rules."""
    if value != value or value == float('inf') or value == float('-inf'):
        return "<NULL>"
    # Normalize -0.0 to 0.0
    if value == 0.0:
        value = 0.0
    return f"{value:.10f}"


def canonical_trade_serialization(trade) -> str:
    """Serialize a Trade per Section I trade_serialization format.

    trade_id|side|entry_fill_price=.10f|exit_fill_price=.10f|quantity=.10f|
    entry_commission=.10f|exit_commission=.10f|gross_pnl=.10f|net_pnl=.10f|
    entry_timestamp|exit_timestamp|holding_period_bars|exit_reason
    """
    parts = [
        trade.trade_id,
        trade.side.value if hasattr(trade.side, 'value') else str(trade.side),
        _format_float(trade.entry_fill_price),
        _format_float(trade.exit_fill_price) if trade.exit_fill_price is not None else "<NULL>",
        _format_float(trade.quantity),
        _format_float(trade.entry_commission),
        _format_float(trade.exit_commission),
        _format_float(trade.gross_pnl),
        _format_float(trade.net_pnl),
        trade.entry_timestamp.isoformat() if trade.entry_timestamp else "<NULL>",
        trade.exit_timestamp.isoformat() if trade.exit_timestamp else "<NULL>",
        str(trade.holding_period_bars) if trade.holding_period_bars is not None else "<NULL>",
        trade.exit_reason.value if hasattr(trade.exit_reason, 'value') else (trade.exit_reason if trade.exit_reason else "<NULL>"),
    ]
    return "|".join(parts)


class BacktestProvenance(BaseModel):
    """Complete provenance record for a backtest result per Section H."""
    model_config = ConfigDict(frozen=True)

    backtest_id: str
    strategy_id: str
    strategy_version: str
    strategy_hash: str
    dataset_id: str
    dataset_version: str
    dataset_hash: str
    instrument: str
    timeframe: str
    initial_capital: float
    num_candles: int
    start_timestamp: datetime
    end_timestamp: datetime
    cost_parameters: Dict[str, Any]
    slippage_parameters: Dict[str, Any]
    position_sizing_parameters: Dict[str, Any]
    engine_version: str = "3.0.0"
    quant_engine_version: str = "2.0.0"
    execution_semantics: str = "signal_at_t_close_execute_at_t_close"
    # Runtime metadata (excluded from result_hash):
    run_timestamp: datetime
    # Result hash computed from deterministic data only
    result_hash: str = ""

    def compute_result_hash(
        self,
        canonical_trades: str,
        canonical_equity_curve: str,
        canonical_metrics: str,
        config_hash: str,
        strategy_hash: str,
        dataset_hash: str,
    ) -> str:
        """Compute SHA-256 of canonical_result_serialization per Section I.

        result_hash = sha256(
            strategy_hash|dataset_hash|canonical_trades|
            canonical_equity_curve|canonical_metrics|config_hash
        )

        Run timestamps are EXCLUDED from the hash.
        """
        canonical_result = (
            f"{strategy_hash}|{dataset_hash}|{canonical_trades}|"
            f"{canonical_equity_curve}|{canonical_metrics}|{config_hash}"
        )
        return hashlib.sha256(canonical_result.encode("utf-8")).hexdigest()

    def to_hash(self) -> str:
        """Return SHA-256 hash of the provenance record (deterministic fields only)."""
        data = self.model_dump(exclude_unset=True)
        # Exclude run_timestamp and result_hash from hash
        data.pop("run_timestamp", None)
        data.pop("result_hash", None)
        data.pop("backtest_id", None)  # backtest_id may contain runtime data
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return self.model_dump()


class BacktestProvenanceTracker:
    """Tracks provenance across backtest runs."""

    def __init__(self):
        self._provenance_records: List[BacktestProvenance] = []

    def record(
        self,
        backtest_id: str,
        strategy_id: str,
        strategy_version: str,
        strategy_hash: str,
        dataset_id: str,
        dataset_version: str,
        dataset_hash: str,
        instrument: str,
        timeframe: str,
        initial_capital: float,
        num_candles: int,
        start_timestamp: datetime,
        end_timestamp: datetime,
        cost_parameters: Dict[str, Any],
        slippage_parameters: Dict[str, Any],
        position_sizing_parameters: Dict[str, Any],
        execution_semantics: str,
                run_timestamp: datetime,
                result_hash: str,
    ) -> BacktestProvenance:
        """Record a backtest provenance with the computed result_hash."""
        provenance = BacktestProvenance(
            backtest_id=backtest_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            strategy_hash=strategy_hash,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            dataset_hash=dataset_hash,
            instrument=instrument,
            timeframe=timeframe,
            initial_capital=initial_capital,
            num_candles=num_candles,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            cost_parameters=cost_parameters,
            slippage_parameters=slippage_parameters,
            position_sizing_parameters=position_sizing_parameters,
            execution_semantics=execution_semantics,
            run_timestamp=run_timestamp,
            result_hash=result_hash,
        )
        self._provenance_records.append(provenance)
        return provenance

    def get_all(self) -> List[BacktestProvenance]:
        """Return all recorded provenance."""
        return self._provenance_records.copy()

    def get_by_strategy(self, strategy_id: str) -> List[BacktestProvenance]:
        """Return provenance records for a strategy."""
        return [p for p in self._provenance_records if p.strategy_id == strategy_id]

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return {
            "total_records": len(self._provenance_records),
            "records": [p.to_dict() for p in self._provenance_records],
        }
