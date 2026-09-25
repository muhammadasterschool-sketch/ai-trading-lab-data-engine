"""Declarative condition evaluation and signal generation for Phase 3.

Implements a condition evaluator that processes declarative entry/exit
conditions without using eval/exec/lambda. Conditions are structured as
typed dictionaries or dataclasses representing comparison trees.

Supported condition types (from the design spec):
- INDICATOR: Check an indicator value against a threshold
- THRESHOLD: Compare a numeric value against a threshold
- COMPARISON: Compare two values with an operator
- LOGICAL_AND: All sub-conditions must be true
- LOGICAL_OR: At least one sub-condition must be true
- LOGICAL_NOT: Negate a sub-condition
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Condition data structures ---

class Condition(BaseModel):
    """Declarative condition for entry/exit signals.

    A condition is a structured tree that is evaluated recursively.
    No eval/exec/lambda are used — all evaluation is explicit.
    """

    model_config = ConfigDict(frozen=True)

    type: str  # "INDICATOR", "THRESHOLD", "COMPARISON", "LOGICAL_AND", "LOGICAL_OR", "LOGICAL_NOT"
    operator: Optional[str] = None  # ">", "<", ">=", "<=", "==", "!="
    indicator: Optional[str] = None  # e.g., "RSI", "SMA_20"
    threshold: Optional[float] = None
    left_operand: Optional["Condition"] = None  # recursive
    right_operand: Optional["Condition"] = None  # recursive
    NOT_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation for serialization."""
        result: Dict[str, Any] = {"type": self.type}
        if self.operator is not None:
            result["operator"] = self.operator
        if self.indicator is not None:
            result["indicator"] = self.indicator
        if self.threshold is not None:
            result["threshold"] = self.threshold
        if self.left_operand is not None:
            result["left_operand"] = self.left_operand.to_dict()
        if self.right_operand is not None:
            result["right_operand"] = self.right_operand.to_dict()
        if self.NOT_applied:
            result["NOT_applied"] = True
        return result


class Signal(BaseModel):
    """Generated trading signal."""

    model_config = ConfigDict(frozen=True)

    timestamp: float
    signal_type: str  # "ENTRY" or "EXIT"
    side: Optional[str] = None  # "LONG" or "SHORT" for entry
    conditions_met: List[str] = Field(default_factory=list)


# --- ConditionEvaluator ---

class ConditionEvaluator:
    """Evaluates declarative conditions against current and previous values.

    No eval/exec/lambda are used. All condition types are handled
    through explicit type checking and recursive evaluation.
    """

    def evaluate_condition(
        self,
        condition: Condition,
        current_value: Optional[float] = None,
        previous_value: Optional[float] = None,
    ) -> bool:
        """Evaluate a condition against current and previous values.

        Args:
            condition: The Condition to evaluate.
            current_value: The current indicator/bar value.
            previous_value: The previous bar's indicator value.

        Returns:
            True if the condition is satisfied, False otherwise.
        """
        result = self._evaluate(condition, current_value, previous_value)
        if condition.NOT_applied:
            return not result
        return result

    def _evaluate(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Internal recursive evaluation."""
        cond_type = condition.type

        if cond_type == "INDICATOR":
            return self._eval_indicator(condition, current_value, previous_value)
        elif cond_type == "THRESHOLD":
            return self._eval_threshold(condition, current_value)
        elif cond_type == "COMPARISON":
            return self._eval_comparison(condition, current_value, previous_value)
        elif cond_type == "LOGICAL_AND":
            return self._eval_and(condition, current_value, previous_value)
        elif cond_type == "LOGICAL_OR":
            return self._eval_or(condition, current_value, previous_value)
        elif cond_type == "LOGICAL_NOT":
            return self._eval_not(condition, current_value, previous_value)
        else:
            raise ValueError(f"Unknown condition type: {cond_type}")

    def _eval_indicator(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Evaluate an INDICATOR condition."""
        value = previous_value if condition.indicator and condition.type == "INDICATOR" and previous_value is not None else current_value
        if value is None:
            return False
        return self._compare(value, condition.operator, condition.threshold)

    def _eval_threshold(
        self,
        condition: Condition,
        current_value: Optional[float],
    ) -> bool:
        """Evaluate a THRESHOLD condition."""
        if current_value is None:
            return False
        return self._compare(current_value, condition.operator, condition.threshold)

    def _eval_comparison(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Evaluate a COMPARISON condition comparing left and right operands."""
        left = self._resolve_operand(condition.left_operand, current_value, previous_value)
        right = self._resolve_operand(condition.right_operand, current_value, previous_value)
        if left is None or right is None:
            return False
        return self._compare(left, condition.operator, right)

    def _eval_and(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Evaluate LOGICAL_AND — all sub-conditions must be true."""
        if condition.left_operand is None or condition.right_operand is None:
            return False
        return (
            self._evaluate(condition.left_operand, current_value, previous_value)
            and self._evaluate(condition.right_operand, current_value, previous_value)
        )

    def _eval_or(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Evaluate LOGICAL_OR — at least one sub-condition must be true."""
        if condition.left_operand is None or condition.right_operand is None:
            return False
        return (
            self._evaluate(condition.left_operand, current_value, previous_value)
            or self._evaluate(condition.right_operand, current_value, previous_value)
        )

    def _eval_not(
        self,
        condition: Condition,
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> bool:
        """Evaluate LOGICAL_NOT — negate the sub-condition."""
        if condition.left_operand is None:
            return False
        return not self._evaluate(condition.left_operand, current_value, previous_value)

    def _resolve_operand(
        self,
        operand: Optional[Condition],
        current_value: Optional[float],
        previous_value: Optional[float],
    ) -> Optional[float]:
        """Resolve an operand to a numeric value."""
        if operand is None:
            return None
        if operand.type == "THRESHOLD" and operand.threshold is not None:
            return operand.threshold
        if operand.type == "INDICATOR" and current_value is not None:
            return current_value
        if operand.type == "COMPARISON":
            # Recursively resolve
            left = self._resolve_operand(operand.left_operand, current_value, previous_value)
            right = self._resolve_operand(operand.right_operand, current_value, previous_value)
            if left is not None and right is not None:
                # For a nested comparison, we need a value — this is a simplification
                # where the comparison resolves to the left value for further comparison
                return left
        return None

    def _compare(
        self,
        value: float,
        operator: Optional[str],
        threshold: Optional[float],
    ) -> bool:
        """Compare a value against a threshold using the given operator."""
        if threshold is None or operator is None:
            return False
        op = operator
        if op == ">":
            return value > threshold
        elif op == "<":
            return value < threshold
        elif op == ">=":
            return value >= threshold
        elif op == "<=":
            return value <= threshold
        elif op == "==":
            return abs(value - threshold) < 1e-10
        elif op == "!=":
            return abs(value - threshold) >= 1e-10
        else:
            raise ValueError(f"Unknown operator: {op}")


# --- SignalGenerator ---

class SignalGenerator:
    """Generates trading signals from declarative conditions.

    Uses ConditionEvaluator to check entry and exit conditions
    against indicator values and produces Signal objects.
    """

    def __init__(self) -> None:
        self._evaluator = ConditionEvaluator()

    def generate_signals(
        self,
        conditions: List[Condition],
        current_value: Optional[float] = None,
        previous_value: Optional[float] = None,
        timestamp: float = 0.0,
    ) -> List[Signal]:
        """Generate signals from a list of conditions.

        Evaluates each condition and returns a list of Signal objects
        for conditions that are satisfied.
        """
        signals: List[Signal] = []
        for condition in conditions:
            result = self._evaluator.evaluate_condition(
                condition, current_value, previous_value
            )
            if result:
                signals.append(Signal(
                    timestamp=timestamp,
                    signal_type="ENTRY",
                    conditions_met=[condition.indicator or condition.type],
                ))
        return signals
