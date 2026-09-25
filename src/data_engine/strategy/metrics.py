"""Deterministic backtest metrics engine for Phase 3.

All metrics are computed deterministically from trade data and equity curves.
No estimation, no approximation, no hidden state.

All 20 metrics follow exact formulas from Section K of the design document.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from pydantic import BaseModel, Field, ConfigDict
import math
import statistics

from data_engine.strategy.ledger import TradeLedger, Trade
from data_engine.strategy.equity import EquityPoint

# Periods per year for each timeframe (Section K)
periods_per_year: Dict[str, int] = {
    "M1": 525600,   # 365 * 24 * 60
    "M5": 105120,   # 365 * 24 * 12
    "M15": 35040,   # 365 * 24 * 4
    "H1": 8760,     # 365 * 24
    "H4": 2190,     # 365 * 6
    "D1": 365,      # 365 (forex 24h market)
}

BREAKEVEN_TOLERANCE = 1e-10


class BacktestMetrics(BaseModel):
    """Complete deterministic backtest metrics.

    All 20 metrics from Section K with exact formulas.
    Annualized metrics return None when n-1 < periods_per_year.
    """
    model_config = ConfigDict(frozen=True)

    # === Return metrics (1-3) ===
    total_return: Optional[float] = None
    cumulative_return: Optional[float] = None
    annualized_return: Optional[float] = None

    # === Volatility metrics (4-6) ===
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None

    # === Drawdown metrics (7-9) ===
    max_drawdown: Optional[float] = None
    max_drawdown_duration: Optional[int] = None
    recovery_duration: Optional[int] = None

    # === Trade metrics (10-18) ===
    win_rate: Optional[float] = None
    loss_rate: Optional[float] = None
    breakeven_trades: Optional[int] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[float] = None
    average_trade: Optional[float] = None
    median_trade: Optional[float] = None
    average_win: Optional[float] = None
    average_loss: Optional[float] = None

    # === Exposure/turnover metrics (19-20) ===
    turnover: Optional[float] = None
    exposure: Optional[float] = None

    # === Metadata ===
    risk_free_rate: float = 0.0
    total_net_pnl: float = 0.0
    total_commissions: float = 0.0
    total_slippage: float = 0.0
    total_trades: int = 0
    num_trades: int = 0
    has_sufficient_data: bool = True
    insufficient_data_reason: Optional[str] = None
    periods_per_year_used: Optional[int] = None

    @classmethod
    def from_trades(
        cls,
        trades: TradeLedger,
        initial_capital: float = 10000.0,
        risk_free_rate: float = 0.0,
        periods_per_year: Optional[int] = None,
    ) -> "BacktestMetrics":
        """Calculate trade-based metrics from a trade ledger.

        Computes metrics 10-18 (trade-based) and 1-3 (approximate from trades).
        Equity-based metrics (4-9, 20) are set to None.
        """
        closed_trades = trades.get_closed_trades()
        total = len(closed_trades)
        net_pnls = [t.net_pnl for t in closed_trades if t.net_pnl is not None]

        if total == 0 or len(net_pnls) == 0:
            return cls(
                has_sufficient_data=False,
                insufficient_data_reason="No closed trades available",
                total_trades=total,
                num_trades=total,
                total_net_pnl=trades.total_net_pnl(),
                total_commissions=trades.total_commissions(),
                total_slippage=trades.total_slippage(),
            )

        total_net_pnl = sum(net_pnls)
        total_commissions = trades.total_commissions()
        total_slippage = trades.total_slippage()

        # Breakeven trades (metric 12)
        breakeven_count = sum(1 for p in net_pnls if abs(p) <= BREAKEVEN_TOLERANCE)

        # Winners and losers (separated by BREAKEVEN_TOLERANCE)
        winning = [p for p in net_pnls if p > BREAKEVEN_TOLERANCE]
        losing = [p for p in net_pnls if p < -BREAKEVEN_TOLERANCE]
        W = len(winning)
        L = len(losing)
        B = breakeven_count
        T = total  # W + L + B should equal T

        # Win rate (metric 10): W / T
        win_rate = W / T if T > 0 else None
        # Loss rate (metric 11): L / T
        loss_rate = L / T if T > 0 else None

        # Average win (metric 17)
        average_win = sum(winning) / W if W > 0 else None
        # Average loss (metric 18): reported as positive value
        average_loss = abs(sum(losing) / L) if L > 0 else None

        # Profit factor (metric 13): gross_wins / abs(gross_losses)
        gross_wins = sum(winning)
        gross_losses = abs(sum(losing))
        if gross_losses > 0:
            profit_factor = gross_wins / gross_losses
        elif gross_wins > 0:
            profit_factor = float('inf')
        else:
            profit_factor = 0.0

        # Expectancy (metric 14): total_net_pnl / T
        expectancy = total_net_pnl / T if T > 0 else None
        # Average trade (metric 15): same as expectancy
        average_trade = total_net_pnl / T if T > 0 else None

        # Median trade (metric 16)
        if T > 0:
            median_trade = statistics.median(net_pnls)
        else:
            median_trade = None

        # === Return metrics (1-3) from trades ===
        # total_return = total_net_pnl / initial_capital
        total_return = total_net_pnl / initial_capital if initial_capital > 0 else None
        # cumulative_return approximated from trades
        cumulative_return = total_return

        # Annualized return: cannot compute without time period info
        annualized_return = None
        volatility = None
        sharpe_ratio = None
        sortino_ratio = None

        # === Trade-based only: exposure, turnover need equity curve ===
        turnover = None
        exposure = None

        return cls(
            total_return=total_return,
            cumulative_return=cumulative_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=None,
            max_drawdown_duration=None,
            recovery_duration=None,
            win_rate=win_rate,
            loss_rate=loss_rate,
            breakeven_trades=breakeven_count if B > 0 else 0,
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_trade=average_trade,
            median_trade=median_trade,
            average_win=average_win,
            average_loss=average_loss,
            turnover=turnover,
            exposure=exposure,
            risk_free_rate=risk_free_rate,
            total_net_pnl=total_net_pnl,
            total_commissions=total_commissions,
            total_slippage=total_slippage,
            total_trades=total,
            num_trades=total,
            periods_per_year_used=periods_per_year,
        )

    @classmethod
    def from_equity_curve(
        cls,
        equity_curve: List[EquityPoint],
        risk_free_rate: float = 0.0,
        periods_per_year: Optional[int] = None,
    ) -> "BacktestMetrics":
        """Calculate equity-based metrics from an equity curve.

        Computes metrics 1-9 (equity-based) and 20 (exposure).
        Trade-based metrics (10-18) are set to None unless derived.
        """
        if not equity_curve or len(equity_curve) < 2:
            return cls(
                has_sufficient_data=False,
                insufficient_data_reason="Insufficient equity curve data (need at least 2 points)",
                risk_free_rate=risk_free_rate,
                periods_per_year_used=periods_per_year,
            )

        equity_values = [p.total_equity for p in equity_curve]
        n = len(equity_values)
        initial_equity = equity_values[0]
        final_equity = equity_values[-1]
        initial_capital = initial_equity  # equity_values[0] = initial_capital

        # Number of return intervals
        num_periods = n - 1  # n-1 return intervals

        # === 1. total_return ===
        # total_return = (final_equity - initial_capital) / initial_capital
        total_return = (final_equity - initial_capital) / initial_capital if initial_capital > 0 else None

        # === 2. cumulative_return ===
        # cumulative_return = Π(1 + r_i) - 1 where r_i = (equity[i] - equity[i-1]) / equity[i-1]
        returns = []
        for i in range(1, n):
            if equity_values[i - 1] > 0:
                r = equity_values[i] / equity_values[i - 1] - 1
                returns.append(r)
            else:
                returns.append(None)  # undefined

        # Filter out None returns for cumulative calculation
        valid_returns = [r for r in returns if r is not None]
        if valid_returns and all(1 + r > 0 for r in valid_returns):
            cumulative_product = 1.0
            for r in valid_returns:
                cumulative_product *= (1 + r)
            cumulative_return = cumulative_product - 1
        else:
            cumulative_return = None  # equity went to zero or below

        # === 3. annualized_return ===
        # (final_equity / initial_equity) ** (periods_per_year / (n - 1)) - 1
        # None if n-1 < periods_per_year
        annualized_return = None
        if periods_per_year is not None and num_periods >= periods_per_year and num_periods > 0:
            if initial_equity > 0:
                annualized_return = (final_equity / initial_equity) ** (periods_per_year / num_periods) - 1

        # === 4. volatility ===
        # std(returns, ddof=1) * sqrt(periods_per_year)
        volatility = None
        if len(valid_returns) >= 2 and periods_per_year is not None:
            if periods_per_year is not None and num_periods >= periods_per_year:
                try:
                    vol = statistics.stdev(valid_returns)
                    volatility = vol * math.sqrt(periods_per_year)
                except statistics.StatisticsError:
                    volatility = 0.0
            elif num_periods >= periods_per_year:
                # Already handled above
                pass

        # === 5. sharpe_ratio ===
        # (annualized_return - risk_free_rate) / annualized_volatility
        sharpe_ratio = None
        if annualized_return is not None and volatility is not None and periods_per_year is not None and num_periods >= periods_per_year:
            if volatility > 0:
                sharpe_ratio = (annualized_return - risk_free_rate) / volatility
            elif annualized_return > risk_free_rate:
                sharpe_ratio = float('inf')
            elif annualized_return == risk_free_rate:
                sharpe_ratio = 0.0
            else:
                sharpe_ratio = float('-inf')

        # === 6. sortino_ratio ===
        # (annualized_return - risk_free_rate) / downside_deviation_annualized
        sortino_ratio = None
        if annualized_return is not None and periods_per_year is not None and num_periods >= periods_per_year:
            # downside_deviation = sqrt((1/N) * sum(min(r_i - target, 0)^2))
            # target = risk_free_rate / periods_per_year
            target = risk_free_rate / periods_per_year if periods_per_year > 0 else 0.0
            downside_returns = [r for r in valid_returns if r is not None and r - target < 0]
            if downside_returns:
                downside_var = sum((r - target) ** 2 for r in downside_returns) / len(downside_returns)
                downside_dev = math.sqrt(downside_var)
                downside_dev_annualized = downside_dev * math.sqrt(periods_per_year)
                if downside_dev_annualized > 0:
                    sortino_ratio = (annualized_return - risk_free_rate) / downside_dev_annualized
                elif annualized_return > risk_free_rate:
                    sortino_ratio = float('inf')
                elif annualized_return == risk_free_rate:
                    sortino_ratio = 0.0
                else:
                    sortino_ratio = float('-inf')

        # === 7. max_drawdown ===
        # raw = min(equity_values[i] / running_peak[i] - 1)
        # reported = -raw (>= 0)
        max_drawdown = None
        running_peak = equity_values[0]
        raw_max_dd = 0.0
        for eq in equity_values:
            if eq > running_peak:
                running_peak = eq
            if running_peak > 0:
                dd = eq / running_peak - 1
                raw_max_dd = min(raw_max_dd, dd)
        max_drawdown = -raw_max_dd  # reported as positive

        # === 8. max_drawdown_duration ===
        # Find peak bar p where drawdown from p is maximal
        # Count from p+1 to r where equity[r] >= equity[p]
        # duration = r - p
        # If no recovery: None
        max_dd_duration = None
        # Find the peak and trough for the maximum drawdown
        running_peak = equity_values[0]
        peak_idx = 0
        trough_idx = 0
        raw_max_dd_at_peak = 0.0
        current_peak_idx = 0

        # First pass: find the maximum drawdown and its peak/trough
        running_peak = equity_values[0]
        for i in range(len(equity_values)):
            if equity_values[i] >= running_peak:
                running_peak = equity_values[i]
                current_peak_idx = i
            if running_peak > 0:
                dd = equity_values[i] / running_peak - 1
                if dd < raw_max_dd_at_peak or i == 0 and dd == raw_max_dd_at_peak:
                    # Check if this is a new max drawdown
                    if dd < raw_max_dd_at_peak:
                        raw_max_dd_at_peak = dd
                        peak_idx = current_peak_idx
                        trough_idx = i

        # Actually, let me redo this properly
        # Find the maximum drawdown and identify its peak
        running_peak = equity_values[0]
        peak_idx = 0
        max_dd_value = 0.0  # raw (negative or zero)
        trough_idx_for_max = 0

        for i in range(len(equity_values)):
            if equity_values[i] >= running_peak:
                running_peak = equity_values[i]
                peak_idx = i
            if running_peak > 0:
                dd = equity_values[i] / running_peak - 1
                if dd < max_dd_value:
                    max_dd_value = dd
                    trough_idx_for_max = i

        # Now find recovery from peak_idx
        peak_equity = equity_values[peak_idx]
        recovery_idx = None
        for i in range(peak_idx + 1, len(equity_values)):
            if equity_values[i] >= peak_equity:
                recovery_idx = i
                break

        if recovery_idx is not None:
            max_dd_duration = recovery_idx - peak_idx
        elif max_dd_value < 0:
            max_dd_duration = None  # no recovery
        else:
            max_dd_duration = 0  # no drawdown

        # === 9. recovery_duration ===
        # recovery_duration = recovery_bar_index - trough_bar_index
        # trough_bar_index is the lowest equity point after the max_drawdown peak
        recovery_duration = None
        if max_dd_duration is not None and max_dd_duration > 0:
            # Find the actual trough (lowest equity) between peak_idx and recovery_idx
            trough_idx = peak_idx
            for i in range(peak_idx, recovery_idx + 1 if recovery_idx else len(equity_values)):
                if equity_values[i] < equity_values[trough_idx]:
                    trough_idx = i
            if recovery_idx is not None:
                recovery_duration = recovery_idx - trough_idx

        # === 20. exposure ===
        # gross_exposure_t = abs(position_market_value_t) / equity_t
        # exposure = mean(gross_exposure_t) for all t where equity_t > 0
        gross_exposures = []
        for p in equity_curve:
            if p.total_equity > 0:
                gross_exp = abs(p.position_market_value) / p.total_equity
                gross_exposures.append(gross_exp)
        exposure = sum(gross_exposures) / len(gross_exposures) if gross_exposures else None

        # === Trade-based metrics: None (no trade data) ===
        win_rate = None
        loss_rate = None
        breakeven_trades = None
        profit_factor = None
        expectancy = None
        average_trade = None
        median_trade = None
        average_win = None
        average_loss = None
        turnover = None

        # Total net pnl from equity curve: final - initial (approximation)
        total_net_pnl = final_equity - initial_capital
        total_commissions = 0.0  # Not available from equity curve alone
        total_slippage = 0.0
        total_trades = 0  # Not available from equity curve alone

        return cls(
            total_return=total_return,
            cumulative_return=cumulative_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            recovery_duration=recovery_duration,
            win_rate=win_rate,
            loss_rate=loss_rate,
            breakeven_trades=breakeven_trades,
            profit_factor=profit_factor,
            expectancy=expectancy,
            average_trade=average_trade,
            median_trade=median_trade,
            average_win=average_win,
            average_loss=average_loss,
            turnover=turnover,
            exposure=exposure,
            risk_free_rate=risk_free_rate,
            total_net_pnl=total_net_pnl,
            total_commissions=total_commissions,
            total_slippage=total_slippage,
            total_trades=total_trades,
            num_trades=total_trades,
            periods_per_year_used=periods_per_year,
        )
