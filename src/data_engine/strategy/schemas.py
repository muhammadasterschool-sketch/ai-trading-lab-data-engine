"""Immutable, declarative strategy specifications for Phase 3.

A strategy specification is a frozen Pydantic model that defines
a complete trading strategy without allowing arbitrary Python code.

All strategies must explicitly define:
- entry conditions
- exit conditions
- position sizing rules
- risk management rules
- required indicators/features
- assumptions

The strategy spec is declarative — it describes WHAT the strategy does,
not HOW to execute it. Execution is handled by BacktestEngine.

Canonical Serialization Rules (per Section H/I of the design spec):
- UTF-8 encoding
- Pipe | as field separator
- LF (\n) as record separator
- Float values formatted as .10f
- None/null serializes as <NULL>
- -0.0 normalized to 0.0
- Every canonical serialization ends with exactly one \n
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, field_validator
from decimal import Decimal
import hashlib
import json
import math


def _format_float(v: Optional[float]) -> str:
    """Format a float as .10f, normalizing -0.0 to 0.0, or <NULL> if None."""
    if v is None:
        return "<NULL>"
    if math.isnan(v) or math.isinf(v):
        return "<NULL>"
    v = 0.0 if v == 0.0 else v  # normalize -0.0 to 0.0
    return f"{v:.10f}"


def _escape(s: str) -> str:
    """Escape special characters for canonical serialization: \\ -> \\\\, | -> \\|."""
    s = s.replace("\\", "\\\\")
    s = s.replace("|", "\\|")
    s = s.replace("\n", "\\n")
    return s


class OrderSide(str, Enum):
    """Direction of a trade order."""
    LONG = "LONG"
    SHORT = "SHORT"


class OrderStatus(str, Enum):
    """Status of an order in the backtest."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExitReason(str, Enum):
    """Reason for closing a position."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    SIGNAL_EXIT = "SIGNAL_EXIT"
    TIME_EXPIRED = "TIME_EXPIRED"
    MAX_EXPOSURE = "MAX_EXPOSURE"
    MANUAL = "MANUAL"


class EntryCondition(BaseModel):
    """A single entry condition for a strategy.

    Conditions are declarative: they reference indicator names
    and comparison operators. No arbitrary Python code.
    """
    model_config = ConfigDict(frozen=True)

    indicator: str
    operator: str
    threshold: float
    timeframe: Optional[str] = None
    requires_previous: bool = False

    def canonical_serialize(self) -> str:
        """Serialize per Section I condition serialization format:
        condition_type|operator|indicator_name|parameter_order|threshold_value|left_operand|right_operand|NOT_applied
        """
        param_order = self.timeframe if self.timeframe else ""
        threshold_str = _format_float(self.threshold)
        return (
            f"INDICATOR|{_escape(self.operator)}|{_escape(self.indicator)}|"
            f"{_escape(param_order)}|{threshold_str}|<NULL>|<NULL>|false"
        )

    def evaluate(self, current_value: Optional[float], previous_value: Optional[float] = None) -> bool:
        """Evaluate this condition against a value."""
        value = previous_value if self.requires_previous and previous_value is not None else current_value
        if value is None:
            return False
        op = self.operator
        if op == ">":
            return value > self.threshold
        elif op == "<":
            return value < self.threshold
        elif op == ">=":
            return value >= self.threshold
        elif op == "<=":
            return value <= self.threshold
        elif op == "==":
            return abs(value - self.threshold) < 1e-10
        else:
            raise ValueError(f"Unknown operator: {self.operator}")

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return {
            "indicator": self.indicator,
            "operator": self.operator,
            "threshold": self.threshold,
            "timeframe": self.timeframe,
            "requires_previous": self.requires_previous,
        }


class ExitCondition(BaseModel):
    """A single exit condition for a strategy."""
    model_config = ConfigDict(frozen=True)

    type: str
    indicator: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    pct_of_entry: Optional[float] = None

    def canonical_serialize(self) -> str:
        """Serialize per Section I condition serialization format."""
        condition_type = self.type
        indicator_name = _escape(self.indicator) if self.indicator else "<NULL>"
        param_order = ""
        threshold_str = _format_float(self.threshold)
        # For pct_of_entry, include as threshold if threshold is None
        effective_threshold = self.threshold if self.threshold is not None else (self.pct_of_entry if self.pct_of_entry is not None else None)
        threshold_str = _format_float(effective_threshold)
        not_applied = "false"
        return (
            f"{_escape(condition_type)}|{_escape(self.operator) if self.operator else '<NULL>'}|"
            f"{indicator_name}|{_escape(param_order)}|{threshold_str}|<NULL>|<NULL>|{not_applied}"
        )

    def evaluate(
        self,
        entry_price: float,
        current_price: float,
        current_value: Optional[float] = None,
    ) -> bool:
        """Evaluate this exit condition using D4 approved semantics:
        Decimal reference threshold + Decimal.from_float price bridge.
        """
        if self.pct_of_entry is not None:
            # D4.1/D4.2: Percentage-point semantics — pct / 100
            pct_decimal = Decimal(str(self.pct_of_entry))
            pct_div_100 = pct_decimal / Decimal('100')

            # D4.3/D4.4: Compute exact Decimal threshold
            entry_decimal = Decimal(str(entry_price))
            if self.type == "stop_loss":
                threshold = entry_decimal * (Decimal('1') - pct_div_100)
            elif self.type == "take_profit":
                threshold = entry_decimal * (Decimal('1') + pct_div_100)
            else:
                threshold = None

            # D4.6: Bridge actual price through Decimal.from_float
            price_decimal = Decimal.from_float(current_price)

            if threshold is not None:
                # D4.7: Inclusive boundaries (D3 preserved)
                if self.type == "stop_loss":
                    return price_decimal <= threshold
                elif self.type == "take_profit":
                    return price_decimal >= threshold

        # Fallback to threshold-based evaluation
        if self.type == "stop_loss":
            return current_price <= (self.threshold if self.threshold is not None else 0.0)
        elif self.type == "take_profit":
            return current_price >= (self.threshold if self.threshold is not None else 0.0)
        elif self.type == "signal":
            return self.indicator is not None and current_value is not None
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation."""
        return {
            "type": self.type,
            "indicator": self.indicator,
            "threshold": self.threshold,
            "pct_of_entry": self.pct_of_entry,
        }


class PositionSizingParameters(BaseModel):
    """Parameters for position sizing."""
    model_config = ConfigDict(frozen=True)

    method: str = Field(default="fixed", description="fixed or percent")
    fixed_quantity: Optional[float] = None
    percent_of_capital: Optional[float] = None
    max_position_size: float = Field(default=1.0, ge=0)
    max_exposure_pct: float = Field(default=100.0, ge=0, le=100)

    def _validate_method(self) -> None:
        if self.method == "fixed" and self.fixed_quantity is None:
            raise ValueError("fixed method requires fixed_quantity")
        if self.method == "percent" and self.percent_of_capital is None:
            raise ValueError("percent method requires percent_of_capital")

    def canonical_serialize(self) -> str:
        """Serialize per Section I: method|parameters_serialized
        - For fixed: fixed|fixed_quantity=.10f|max_position_size=.10f
        - For percent: percent|percent_of_capital=.10f|max_position_size=.10f
        """
        self._validate_method()
        max_pos_str = _format_float(self.max_position_size)
        if self.method == "fixed":
            fq_str = _format_float(self.fixed_quantity)
            return f"fixed|{fq_str}|{max_pos_str}"
        elif self.method == "percent":
            poc_str = _format_float(self.percent_of_capital)
            return f"percent|{poc_str}|{max_pos_str}"
        else:
            raise ValueError(f"Unknown method: {self.method}")

    def check(self) -> bool:
        """Validate the sizing parameters."""
        self._validate_method()
        return True


class CostParameters(BaseModel):
    """Explicit transaction cost parameters."""
    model_config = ConfigDict(frozen=True)

    commission_per_share: float = Field(default=0.0, ge=0.0)
    commission_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    def canonical_serialize(self) -> str:
        """Serialize per Section I: commission_per_share=.10f|commission_pct=.10f"""
        return f"{_format_float(self.commission_per_share)}|{_format_float(self.commission_pct)}"

    def total_cost(self, trade_value: float, quantity: float) -> float:
        """Calculate total transaction cost for a trade."""
        commission = self.commission_per_share * quantity + self.commission_pct / 100.0 * trade_value
        return commission


class SlippageParameters(BaseModel):
    """Explicit slippage model parameters."""
    model_config = ConfigDict(frozen=True)

    fixed_slippage: float = Field(default=0.0, ge=0.0)
    pct_slippage: float = Field(default=0.0, ge=0.0, le=100.0)
    atr_multiplier: float = Field(default=0.0, ge=0.0)
    atr_period: int = Field(default=14, ge=1)

    def canonical_serialize(self) -> str:
        """Serialize per Section I: fixed_slippage=.10f|pct_slippage=.10f|atr_multiplier=.10f|atr_period=integer"""
        return (
            f"{_format_float(self.fixed_slippage)}|"
            f"{_format_float(self.pct_slippage)}|"
            f"{_format_float(self.atr_multiplier)}|"
            f"{self.atr_period}"
        )

    def calculate_slippage(self, price: float, atr: Optional[float] = None) -> float:
        """Calculate slippage for a given price."""
        slippage = self.fixed_slippage + self.pct_slippage / 100.0 * price
        if atr is not None:
            slippage += self.atr_multiplier * atr
        return slippage


class ExecutionConfig(BaseModel):
    """Execution timing configuration."""
    model_config = ConfigDict(frozen=True)

    execution_delay: int = Field(default=0, ge=0, le=1)

    @field_validator("execution_delay")
    @classmethod
    def validate_execution_delay(cls, v: int) -> int:
        """Validate execution_delay is 0 or 1."""
        if v not in (0, 1):
            raise ValueError("execution_delay must be 0 or 1")
        return v


class StrategySpec(BaseModel):
    """Declarative, immutable strategy specification for Phase 3.

    All strategy logic is defined declaratively. No arbitrary
    Python code can be injected as a strategy.

    Canonical serialization field order (Section I):
    strategy_id|strategy_version|strategy_name|instrument|timeframe|
    entry_conditions_serialized|exit_conditions_serialized|
    position_sizing_serialized|stop_loss_pct|take_profit_pct|
    max_position_size|max_exposure_pct|required_indicators|
    allow_short|cost_parameters_serialized|slippage_parameters_serialized|
    execution_semantics|description|author|assumptions_serialized
    """
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_version: str = "3.0.0"
    strategy_name: str = ""
    instrument: str = "XAU/USD"
    timeframe: str = "D1"
    entry_conditions_serialized: str = ""
    exit_conditions_serialized: str = ""
    position_sizing_serialized: str = ""
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_position_size: float = Field(default=1.0, ge=0)
    max_exposure_pct: float = Field(default=100.0, ge=0, le=100)
    required_indicators: List[str] = Field(default_factory=list)
    allow_short: bool = Field(default=False)
    cost_parameters_serialized: str = ""
    slippage_parameters_serialized: str = ""
    execution_semantics: str = "signal_at_t_close_execute_at_t_close"
    description: str = ""
    author: str = ""
    assumptions_serialized: str = ""

    @property
    def entry_conditions(self) -> List[EntryCondition]:
        """Parse entry_conditions_serialized into a list of EntryCondition."""
        try:
            data = json.loads(self.entry_conditions_serialized) if self.entry_conditions_serialized else []
            if isinstance(data, list):
                return [EntryCondition(**item) if isinstance(item, dict) else item for item in data]
            return []
        except Exception as e:
            raise ValueError(f"Failed to parse entry_conditions_serialized: {e}") from e

    @property
    def exit_conditions(self) -> List[ExitCondition]:
        """Parse exit_conditions_serialized into a list of ExitCondition."""
        try:
            data = json.loads(self.exit_conditions_serialized) if self.exit_conditions_serialized else []
            if isinstance(data, list):
                return [ExitCondition(**item) if isinstance(item, dict) else item for item in data]
            return []
        except Exception as e:
            raise ValueError(f"Failed to parse exit_conditions_serialized: {e}") from e

    @property
    def position_sizing(self) -> PositionSizingParameters:
        """Parse position_sizing_serialized into PositionSizingParameters."""
        try:
            data = json.loads(self.position_sizing_serialized) if self.position_sizing_serialized else {}
            if isinstance(data, dict):
                return PositionSizingParameters(**data)
            return PositionSizingParameters(method="fixed", fixed_quantity=1.0)
        except Exception:
            return PositionSizingParameters(method="fixed", fixed_quantity=1.0)

    @property
    def cost_parameters(self) -> CostParameters:
        """Parse cost_parameters_serialized into CostParameters."""
        try:
            data = json.loads(self.cost_parameters_serialized) if self.cost_parameters_serialized else {}
            if isinstance(data, dict):
                return CostParameters(**data)
            return CostParameters()
        except Exception:
            return CostParameters()

    @property
    def slippage_parameters(self) -> SlippageParameters:
        """Parse slippage_parameters_serialized into SlippageParameters."""
        try:
            data = json.loads(self.slippage_parameters_serialized) if self.slippage_parameters_serialized else {}
            if isinstance(data, dict):
                return SlippageParameters(**data)
            return SlippageParameters()
        except Exception:
            return SlippageParameters()

    @field_validator("strategy_version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate version is 3.0.0."""
        if v != "3.0.0":
            raise ValueError("strategy_version must be 3.0.0")
        return v

    def _serialize_required_indicators(self) -> str:
        """Serialize required_indicators list as comma-separated values."""
        if not self.required_indicators:
            return ""
        return ",".join(self.required_indicators)

    def _serialize_stop_loss_pct(self) -> str:
        """Serialize stop_loss_pct, None as <NULL>."""
        if self.stop_loss_pct is None:
            return "<NULL>"
        return _format_float(self.stop_loss_pct)

    def _serialize_take_profit_pct(self) -> str:
        """Serialize take_profit_pct, None as <NULL>."""
        if self.take_profit_pct is None:
            return "<NULL>"
        return _format_float(self.take_profit_pct)

    def _serialize_assumptions(self) -> str:
        """Return assumptions_serialized string, escaping pipes."""
        return _escape(self.assumptions_serialized)

    def canonical_serialize(self) -> str:
        """Produce the exact canonical string per Section H/I rules.

        Format: UTF-8, pipe | field separator, LF newlines, .10f floats,
        None as <NULL>, trailing newline.
        """
        fields = [
            _escape(self.strategy_id),
            _escape(self.strategy_version),
            _escape(self.strategy_name),
            _escape(self.instrument),
            _escape(self.timeframe),
            _escape(self.entry_conditions_serialized),
            _escape(self.exit_conditions_serialized),
            self.position_sizing.canonical_serialize(),
            self._serialize_stop_loss_pct(),
            self._serialize_take_profit_pct(),
            _format_float(self.max_position_size),
            _format_float(self.max_exposure_pct),
            _escape(self._serialize_required_indicators()),
            "true" if self.allow_short else "false",
            self.cost_parameters.canonical_serialize(),
            self.slippage_parameters.canonical_serialize(),
            _escape(self.execution_semantics),
            _escape(self.description),
            _escape(self.author),
            self._serialize_assumptions(),
        ]
        return "|".join(fields) + "\n"

    def to_hash(self) -> str:
        """Compute SHA-256 of the canonical serialization."""
        canonical = self.canonical_serialize()
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def model_dump_traceable(self) -> Dict[str, Any]:
        """Return fully traceable dict with hash."""
        data = self.model_dump()
        data["spec_hash"] = self.to_hash()
        return data

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation of this strategy."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_name": self.strategy_name,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "entry_conditions_serialized": self.entry_conditions_serialized,
            "exit_conditions_serialized": self.exit_conditions_serialized,
            "position_sizing_serialized": self.position_sizing_serialized,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_position_size": self.max_position_size,
            "max_exposure_pct": self.max_exposure_pct,
            "required_indicators": self.required_indicators,
            "allow_short": self.allow_short,
            "cost_parameters_serialized": self.cost_parameters_serialized,
            "slippage_parameters_serialized": self.slippage_parameters_serialized,
            "execution_semantics": self.execution_semantics,
            "description": self.description,
            "author": self.author,
            "assumptions_serialized": self.assumptions_serialized,
        }
