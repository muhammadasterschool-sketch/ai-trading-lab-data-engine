"""Phase C evidence probe: equity cost double-count + loss-limit input.

Diagnostic evidence script for PAPER-RUN-PNL-1 (readiness report
§0D). NOT a pytest test (never collected); no network; read-only.

What this documents: the PRE-FIX arithmetic of
- runtime.py `_apply_fill_to_position` (equity_realized accumulation)
- runtime.py `_current_equity` (the removed `- _equity_realized` term)
- runtime.py `_daily_realized_return` (the costs-only ratio)
replicated literally on top of the authoritative PositionState core,
to demonstrate WHY they were defects (RUN-EQ-1 / RUN-RL-1).

The POST-FIX behavior is proven by the acceptance tests in
tests/test_runtime_pnl_correctness.py (verified red pre-fix, green
post-fix).
"""
from decimal import Decimal

from data_engine.runtime.pnl import PositionState

# ---- one BUY fill of 1 unit @ 100 with 0.2 total costs -------------
pos = PositionState(symbol="BTCUSDT")
pos = pos.apply_fill(
    fill_quantity=Decimal("1"),
    fill_price=Decimal("100"),
    side="BUY",
    commission=Decimal("0.1"),
    slippage_cost=Decimal("0.05"),
    spread_cost=Decimal("0.05"),
    filled_at=None,
)
# PRE-FIX runtime _apply_fill_to_position equivalent:
equity_realized = Decimal("0.1") + Decimal("0.05") + Decimal("0.05")  # = 0.2

initial_equity = Decimal("10000")


def pre_fix_current_equity(mark):
    """The DEFECTIVE formula (RUN-EQ-1): costs subtracted twice."""
    unrealized = (mark - pos.average_cost) * pos.quantity
    return initial_equity + pos.realized_pnl - equity_realized + unrealized


def true_current_equity(mark):
    """The accepted formula (post-fix): costs embedded exactly once."""
    unrealized = (mark - pos.average_cost) * pos.quantity
    return initial_equity + pos.realized_pnl + unrealized


mark = Decimal("100")  # market unchanged
print("average_cost (costs embedded in basis):", pos.average_cost)   # 100.2
print("PRE-FIX  equity @ mark=100           :", pre_fix_current_equity(mark))
print("TRUE     equity @ mark=100            :", true_current_equity(mark))

# ---- PRE-FIX daily loss limit input (RUN-RL-1) ----------------------
daily = float(equity_realized / initial_equity)
print("PRE-FIX  daily_realized_return        :", daily,
      "(>= 0 always; costs only)")
print("PRE-FIX  loss_limit check passes?     :", daily >= -0.03)

# ---- trading-loss scenario -------------------------------------------
# Close the position at 50 (a -50% price move) then re-check inputs
pos2 = pos.apply_fill(Decimal("1"), Decimal("50"), "SELL",
                      Decimal("0"), Decimal("0"), Decimal("0"), None)
equity_realized2 = equity_realized  # no new costs on this fill
daily2 = float(equity_realized2 / initial_equity)
print("after a -50% trade: realized_pnl      :", pos2.realized_pnl)
print("PRE-FIX  daily_realized_return        :", daily2,
      "(blind to the loss)")
print("PRE-FIX  loss_limit check passes?     :", daily2 >= -0.03)
print("TRUE account return                   :",
      float(pos2.realized_pnl / initial_equity))
print("POST-FIX loss_limit check passes?     :",
      float(pos2.realized_pnl / initial_equity) >= -0.03)
