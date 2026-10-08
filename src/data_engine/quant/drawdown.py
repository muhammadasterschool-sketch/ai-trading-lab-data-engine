"""Drawdown calculations for the Quant Engine.

Implements:
- Running equity high
- Drawdown at each point
- Maximum drawdown
- Drawdown duration
- Recovery duration

Drawdown Definition:
    drawdown_t = equity_t / running_peak_t - 1

Maximum Drawdown:
    max_drawdown = min(drawdown_t)  (most negative value)

Properties:
- drawdown_t <= 0 always
- max_drawdown <= 0 always
- If equity never declines, drawdown = 0 everywhere

Edge cases handled:
- Empty equity curve: returns empty results
- Single point: drawdown = 0
- Constant equity: drawdown = 0
- Unrecovered drawdown: duration tracking accounts for this
"""

from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
import math
from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.immutable import freeze


class DrawdownResult(BaseModel):
    """Result from drawdown calculation."""
    model_config = ConfigDict(frozen=True)

    drawdowns: List[Optional[float]]
    running_peaks: List[Optional[float]]
    max_drawdown: Optional[float]
    max_drawdown_index: Optional[int]
    max_drawdown_duration: int  # Number of periods at max drawdown
    recovery_duration: Optional[int]  # Periods to recover from max DD
    total_periods: int

    @field_validator("drawdowns", "running_peaks")
    @classmethod
    def _freeze_series(cls, v: List) -> List:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    def __len__(self) -> int:
        return self.total_periods


class PeakTroughResult(BaseModel):
    """Peak-trough pair for a single drawdown event."""
    model_config = ConfigDict(frozen=True)

    peak_index: int
    peak_value: float
    trough_index: int
    trough_value: float
    depth: float  # Negative value: trough_value / peak_value - 1
    recovery_index: Optional[int] = None
    recovered: bool = False


def drawdown(
    equity_curve: List[float],
    timestamps: Optional[List[datetime]] = None,
) -> DrawdownResult:
    """Calculate drawdown series from an equity curve.

    Args:
        equity_curve: List of equity values (must be non-negative).
        timestamps: Optional timestamps for each equity point.

    Returns:
        DrawdownResult with drawdown series, running peaks, and metrics.
    """
    n = len(equity_curve)
    if n == 0:
        return DrawdownResult(
            drawdowns=[], running_peaks=[],
            max_drawdown=None, max_drawdown_index=None,
            max_drawdown_duration=0, recovery_duration=None,
            total_periods=0,
        )

    drawdowns: List[Optional[float]] = []
    running_peaks: List[Optional[float]] = []
    running_peak = equity_curve[0]
    peak_index = 0

    for i in range(n):
        eq = equity_curve[i]
        if math.isnan(eq) or math.isinf(eq):
            drawdowns.append(None)
            running_peaks.append(None)
            continue

        if eq > running_peak:
            running_peak = eq
            peak_index = i

        running_peaks.append(running_peak)

        if running_peak > 0:
            dd = eq / running_peak - 1.0
        else:
            dd = 0.0
        drawdowns.append(dd)

    # Calculate max drawdown
    valid_drawdowns = [(i, d) for i, d in enumerate(drawdowns) if d is not None]
    if not valid_drawdowns:
        return DrawdownResult(
            drawdowns=drawdowns, running_peaks=running_peaks,
            max_drawdown=None, max_drawdown_index=None,
            max_drawdown_duration=0, recovery_duration=None,
            total_periods=n,
        )

    max_dd = min(d for _, d in valid_drawdowns)
    max_dd_idx = min(valid_drawdowns, key=lambda x: x[1])[0]

    # Calculate max drawdown duration
    max_dd_duration = 0
    current_dd_duration = 0
    in_max_dd = False
    for i, d in enumerate(drawdowns):
        if d is not None and abs(d - max_dd) < 1e-10:
            current_dd_duration += 1
            in_max_dd = True
        elif in_max_dd:
            max_dd_duration = max(max_dd_duration, current_dd_duration)
            current_dd_duration = 0
            in_max_dd = False
    max_dd_duration = max(max_dd_duration, current_dd_duration)

    # Calculate recovery duration
    recovery_duration = None
    peak_at_max = running_peaks[max_dd_idx]
    if peak_at_max is not None:
        trough_val = equity_curve[max_dd_idx]
        for i in range(max_dd_idx + 1, n):
            if equity_curve[i] >= peak_at_max:
                recovery_duration = i - max_dd_idx
                break

    return DrawdownResult(
        drawdowns=drawdowns,
        running_peaks=running_peaks,
        max_drawdown=max_dd,
        max_drawdown_index=max_dd_idx,
        max_drawdown_duration=max_dd_duration,
        recovery_duration=recovery_duration,
        total_periods=n,
    )


def max_drawdown(
    equity_curve: List[float],
) -> Optional[float]:
    """Calculate maximum drawdown from equity curve."""
    result = drawdown(equity_curve)
    return result.max_drawdown


def drawdown_duration(
    equity_curve: List[float],
) -> List[int]:
    """Calculate drawdown duration at each point.

    Returns number of consecutive periods since last peak.
    """
    n = len(equity_curve)
    if n == 0:
        return []

    durations: List[int] = [0]
    for i in range(1, n):
        if equity_curve[i] >= equity_curve[i - 1]:
            durations.append(0)
        else:
            durations.append(durations[i - 1] + 1)

    return durations


def identify_drawdown_events(
    equity_curve: List[float],
) -> List[PeakTroughResult]:
    """Identify all peak-trough drawdown events.

    Returns a list of PeakTroughResult objects describing each drawdown.
    """
    n = len(equity_curve)
    if n < 2:
        return []

    events: List[PeakTroughResult] = []
    peak_idx = 0
    peak_val = equity_curve[0]
    trough_idx = 0
    trough_val = equity_curve[0]
    in_dd = False

    for i in range(1, n):
        eq = equity_curve[i]
        if math.isnan(eq) or math.isinf(eq):
            continue

        if eq > peak_val:
            # New peak
            if in_dd and trough_idx > peak_idx:
                recovered = False
                for j in range(trough_idx + 1, n):
                    if equity_curve[j] >= peak_val:
                        recovered = True
                        break
                events.append(PeakTroughResult(
                    peak_index=peak_idx,
                    peak_value=peak_val,
                    trough_index=trough_idx,
                    trough_value=trough_val,
                    depth=trough_val / peak_val - 1.0,
                    recovery_index=None,
                    recovered=recovered,
                ))
            peak_idx = i
            peak_val = eq
            trough_idx = i
            trough_val = eq
            in_dd = False
        elif eq < trough_val:
            trough_idx = i
            trough_val = eq
            in_dd = True

    # Handle last drawdown
    if in_dd and trough_idx > peak_idx:
        recovered = False
        for j in range(trough_idx + 1, n):
            if equity_curve[j] >= peak_val:
                recovered = True
                break
        events.append(PeakTroughResult(
            peak_index=peak_idx,
            peak_value=peak_val,
            trough_index=trough_idx,
            trough_value=trough_val,
            depth=trough_val / peak_val - 1.0,
            recovery_index=None,
            recovered=recovered,
        ))

    return events


def calmar_ratio(
    equity_curve: List[float],
    annualization_factor: float = 1.0,
) -> Optional[float]:
    """Calculate Calmar Ratio = Annualized Return / Max Drawdown.

    Returns None if max_drawdown is 0 or equity curve is invalid.
    """
    if len(equity_curve) < 2:
        return None

    total_return = equity_curve[-1] / equity_curve[0] - 1.0 if equity_curve[0] != 0 else None
    if total_return is None:
        return None

    max_dd = max_drawdown(equity_curve)
    if max_dd is None or max_dd == 0:
        return None

    annualized_return = total_return * annualization_factor
    return annualized_return / abs(max_dd)


