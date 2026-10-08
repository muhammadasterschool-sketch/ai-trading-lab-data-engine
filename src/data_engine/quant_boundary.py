"""Deterministic / LLM boundary for the AI Trading Lab Data Engine.

Establishes a hard boundary between deterministic computation
and LLM reasoning.

The LLM may:
- request calculations
- orchestrate workflows
- interpret results
- explain results
- compare results
- generate research hypotheses

The LLM must NOT replace deterministic computation for numerical
market calculations.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class QuantBoundaryError(ValueError):
    """Raised when the boundary cannot serve a request EXPLICITLY.

    RT-F15: unsupported operations fail loudly instead of returning
    fabricated placeholder results (mandate §44 — no fake success
    implementations).
    """


class CalculationType(str, Enum):
    """Types of calculations that MUST be done deterministically."""
    EMA = "ema"
    SMA = "sma"
    RSI = "rsi"
    ATR = "atr"
    ADX = "adx"
    VOLATILITY = "volatility"
    RETURNS = "returns"
    DRAWDOWN = "drawdown"
    CORRELATION = "correlation"
    SHARPE = "sharpe"
    SORTINO = "sortino"
    EXPECTANCY = "expectancy"
    PROFIT_FACTOR = "profit_factor"
    POSITION_SIZING = "position_sizing"
    BACKTEST_STATISTICS = "backtest_statistics"


class LLMBoundary:
    """Hard boundary between deterministic computation and LLM reasoning.

    The LLM is NOT a calculation engine. It orchestrates, interprets,
    and explains — but does not compute market statistics.
    """

    # Calculations that MUST be done deterministically
    DETERMINISTIC_CALCULATIONS = {
        CalculationType.EMA,
        CalculationType.SMA,
        CalculationType.RSI,
        CalculationType.ATR,
        CalculationType.ADX,
        CalculationType.VOLATILITY,
        CalculationType.RETURNS,
        CalculationType.DRAWDOWN,
        CalculationType.CORRELATION,
        CalculationType.SHARPE,
        CalculationType.SORTINO,
        CalculationType.EXPECTANCY,
        CalculationType.PROFIT_FACTOR,
        CalculationType.POSITION_SIZING,
        CalculationType.BACKTEST_STATISTICS,
    }

    # What the LLM IS allowed to do
    LLM_ALLOWED = {
        "orchestrate_workflow",
        "interpret_results",
        "explain_results",
        "compare_results",
        "generate_hypothesis",
        "generate_report",
        "classify_evidence",
        "validate_logic",
        "summarize_findings",
    }

    @classmethod
    def is_deterministic_required(cls, calculation_type: CalculationType) -> bool:
        """Check if a calculation type requires deterministic code."""
        return calculation_type in cls.DETERMINISTIC_CALCULATIONS

    @classmethod
    def assert_deterministic(cls, calculation_type: CalculationType, func_name: str = "unknown"):
        """Assert that a calculation is done deterministically.

        Raises if an LLM attempts to perform the calculation.
        """
        if cls.is_deterministic_required(calculation_type):
            raise LLMBoundaryViolation(
                f"Calculation type {calculation_type.value} must be computed "
                f"deterministically, not by LLM. Function: {func_name}. "
                f"Use deterministic code in data_engine/quant/ module."
            )

    @classmethod
    def allowed_operations(cls) -> set:
        """Return what the LLM is allowed to do."""
        return cls.LLM_ALLOWED.copy()


class LLMBoundaryViolation(Exception):
    """Raised when an LLM attempts to perform deterministic computation."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class DeterministicResult(BaseModel):
    """Result from a deterministic calculation."""
    calculation_type: str
    result: Any
    parameters: Dict
    input_dataset_id: str
    calculation_timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    is_deterministic: bool = True
    source_code_reference: Optional[str] = None  # Which module computed this

    @property
    def is_valid(self) -> bool:
        return self.is_deterministic and self.result is not None


class QuantBoundary:
    """Interface for requesting deterministic calculations.

    The LLM uses this to request calculations from deterministic code.
    Never uses LLM reasoning for numerical market calculations.
    """

    def __init__(self):
        self._pending_calculations: list = []
        self._completed_calculations: list = []

    def request_calculation(
        self,
        calculation_type: CalculationType,
        parameters: Dict,
        input_dataset_id: str,
    ) -> DeterministicResult:
        """Request a deterministic calculation.

        This delegates to deterministic code, NOT LLM reasoning.

        RT-F15 correction: this method is NO LONGER a functional stub
        returning ``result=None`` with a fabricated success shape.
        There is no wired deterministic execution engine behind this
        boundary yet, so the request is RECORDED (audit trail) and
        the call FAILS EXPLICITLY with :class:`QuantBoundaryError` —
        an unsupported operation must never masquerade as a
        completed calculation (mandate §44: no fake success
        implementations). Callers that need the actual computation
        use the ``data_engine.quant`` modules directly.
        """
        self._pending_calculations.append({
            "type": calculation_type.value,
            "parameters": parameters,
            "dataset_id": input_dataset_id,
        })
        raise QuantBoundaryError(
            f"deterministic calculation {calculation_type.value!r} is not "
            "wired to an execution engine behind this boundary — refusing "
            "to return a fabricated result (RT-F15/§44); use the "
            "data_engine.quant modules directly for this computation"
        )

    def get_pending(self) -> list:
        return self._pending_calculations.copy()

    def get_completed(self) -> list:
        return self._completed_calculations.copy()

    def mark_complete(self, calculation_id: int, result):
        """Mark a calculation as completed by deterministic code."""
        self._completed_calculations.append({
            "id": calculation_id,
            "result": result,
            "completed_at": datetime.now(UTC).isoformat(),
        })

    def verify_no_llm_override(self, result: DeterministicResult) -> bool:
        """Verify that a calculation result came from deterministic code."""
        if not result.is_deterministic:
            raise LLMBoundaryViolation(
                f"Result from non-deterministic source. "
                f"Calculation type: {result.calculation_type}. "
                f"Expected deterministic code reference."
            )
        return True
