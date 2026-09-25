"""Explicit execution model for Phase 3 backtests.

Implements deterministic transaction cost and slippage calculations.
All assumptions are explicit and recorded in backtest results.

Slippage Contract:
    calculate_slippage() -> returns the slippage AMOUNT (price displacement)
    calculate_fill_price() -> returns the final FILL PRICE (requested +- slippage)
    compute_fill() -> returns FillResult with fill_price and costs

The slippage_amount formula:
    slippage_amount = fixed_slippage + (pct_slippage/100)*requested_price + atr_multiplier*atr

Fill price:
    LONG:  fill_price = requested_price + slippage_amount
    SHORT: fill_price = requested_price - slippage_amount
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from data_engine.strategy.schemas import CostParameters, SlippageParameters, ExecutionConfig


class FillResult(BaseModel):
    """Result of a single order fill with full cost attribution."""
    model_config = ConfigDict(frozen=True)

    order_id: str
    filled: bool
    fill_price: float
    slippage_price: float
    entry_commission: float
    exit_commission: float
    quantity: float
    side: str
    timestamp: Optional[float] = None
    reject_reason: Optional[str] = None


class ExecutionModel:
    """Deterministic execution model with explicit costs.

    Never silently assumes zero transaction costs.
    All cost assumptions are recorded in the backtest result.

    Slippage Contract:
        calculate_slippage(requested_price, side, atr) returns the slippage AMOUNT.
        calculate_fill_price(requested_price, side, atr) returns the final FILL PRICE.
        compute_fill() returns a FillResult with fill_price, costs, and commission.
    """

    def __init__(
        self,
        cost_params: CostParameters,
        slippage_params: SlippageParameters,
        execution_config: ExecutionConfig,
    ):
        self.cost_params = cost_params
        self.slippage_params = slippage_params
        self.execution_config = execution_config

    def calculate_slippage(self, requested_price: float, side: str, atr: Optional[float] = None) -> float:
        """Calculate the slippage AMOUNT for a given requested price and side.

        Formula:
            slippage_amount = fixed_slippage + (pct_slippage/100)*requested_price + atr_multiplier*atr

        Returns:
            The slippage amount (price displacement), NOT the fill price.

        Fill price is then:
            LONG:  fill_price = requested_price + slippage_amount
            SHORT: fill_price = requested_price - slippage_amount
        """
        atr_value = atr if atr is not None else 0.0
        slippage_amount = (
            self.slippage_params.fixed_slippage
            + (self.slippage_params.pct_slippage / 100.0) * requested_price
            + self.slippage_params.atr_multiplier * atr_value
        )
        return slippage_amount

    def calculate_fill_price(self, requested_price: float, side: str, atr: Optional[float] = None) -> float:
        """Calculate the final fill price for a given requested price and side.

        Fill price = requested_price +- slippage_amount.

        LONG:  fill_price = requested_price + slippage_amount
        SHORT: fill_price = requested_price - slippage_amount
        """
        slippage_amount = self.calculate_slippage(requested_price, side, atr)
        if side == "LONG":
            return requested_price + slippage_amount
        elif side == "SHORT":
            return requested_price - slippage_amount
        return requested_price

    def calculate_commission(self, fill_price: float, quantity: float, side: str) -> float:
        """Calculate commission for a fill.

        Formula:
            commission = commission_per_share * quantity + (commission_pct/100) * (fill_price * quantity)
        """
        commission = (
            self.cost_params.commission_per_share * quantity
            + (self.cost_params.commission_pct / 100.0) * (fill_price * quantity)
        )
        return commission

    def compute_fill(self, **order) -> FillResult:
        """Compute the fill result for an order.

        Uses requested_price from the order (bar[t].close or bar[t+1].close
        depending on execution_delay, resolved by the caller).

        Computes fill_price (including slippage), entry_commission, and
        returns a FillResult with all fields.
        """
        order_id = order.get("order_id", "")
        side = order.get("side", "LONG")
        quantity = order.get("quantity", 0.0)
        requested_price = order.get("requested_price", 0.0)
        atr = order.get("atr", None)
        timestamp = order.get("timestamp", None)

        fill_price = self.calculate_fill_price(requested_price, side, atr)
        slippage_price = abs(fill_price - requested_price)
        entry_commission = self.calculate_commission(fill_price, quantity, side)

        return FillResult(
            order_id=order_id,
            filled=True,
            fill_price=fill_price,
            slippage_price=slippage_price,
            entry_commission=entry_commission,
            exit_commission=0.0,
            quantity=quantity,
            side=side,
            timestamp=timestamp,
        )

    def execute(self, **order) -> FillResult:
        """Execute an order with full cost and slippage computation.

        Validates the order parameters, computes fill price including slippage,
        calculates commissions, and returns a FillResult.

        If the order cannot be executed (e.g., insufficient cash), returns
        a FillResult with filled=False and reject_reason set.
        """
        side = order.get("side", "LONG")
        quantity = order.get("quantity", 0.0)
        requested_price = order.get("requested_price", 0.0)
        current_cash = order.get("current_cash", 0.0)
        atr = order.get("atr", None)
        timestamp = order.get("timestamp", None)
        order_id = order.get("order_id", "")

        # Calculate fill price and slippage
        fill_price = self.calculate_fill_price(requested_price, side, atr)
        slippage_price = abs(fill_price - requested_price)

        if side not in ("LONG", "SHORT"):
            fill_price = requested_price
            slippage_price = 0.0

        # Calculate commission
        commission = self.calculate_commission(fill_price, quantity, side)

        # Check cash constraint
        required_cash = (fill_price * quantity) + commission
        if required_cash > current_cash:
            return FillResult(
                order_id=order_id,
                filled=False,
                fill_price=0.0,
                slippage_price=slippage_price,
                entry_commission=0.0,
                exit_commission=0.0,
                quantity=quantity,
                side=side,
                timestamp=timestamp,
                reject_reason="INSUFFICIENT_CASH",
            )

        return FillResult(
            order_id=order_id,
            filled=True,
            fill_price=fill_price,
            slippage_price=slippage_price,
            entry_commission=commission,
            exit_commission=0.0,
            quantity=quantity,
            side=side,
            timestamp=timestamp,
        )

    def execute_order(self, **order) -> FillResult:
        """Execute a complete order through the execution model.

        This is the primary entry point for order execution in the backtest engine.
        It validates, computes fill, and returns the result.
        """
        return self.execute(**order)
