"""v1.5.0 ConfidenceGate — the >=60% confirmation assessor.

Owner mandate (2026-10-28): "agar koi strategy confirm kare ke ye
market ab is taraf jaye gi 60 percent sure ho ke market ab Bullish ya
phir bearish ho gi to phir ye 1 trade per sec shuru karde after
confirmation candle".

HONEST design (no theatre):

- The gate is a DETERMINISTIC, inspectable weighted ensemble of three
  components — the strategy's own signal, the statistical PredictBase
  next-move baseline, and a trend-alignment factor. Every component
  and every weight is returned with the assessment so the owner can
  audit WHY a burst was (or was not) armed.
- "60% sure" is a CALIBRATION-FREE research heuristic, NOT a verified
  probability. It gates a PAPER-ONLY rapid burst, never live trading.
- Confirmation-candle semantics: every assessment is computed strictly
  on CLOSED bars (the last element of the supplied bar list is the
  confirmation candle).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class ConfidenceGate:
    """Weighted three-component direction/confidence assessor."""

    THRESHOLD_PCT = 60.0
    MIN_BARS = 40
    WEIGHTS = {"strategy": 0.45, "baseline": 0.35, "trend": 0.20}
    #: |score| needed for a non-NEUTRAL call (exactly the >=60% mapping)
    DIRECTION_BAND = 0.20

    def assess(
        self,
        kind: str,
        params: Dict[str, Any],
        bars: List[dict],
        positions: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Assess direction + confidence on the last CLOSED bar.

        ``positions`` may be supplied by callers that already ran the
        strategy (avoids recomputation); otherwise it is computed via
        the injected ``position_fn`` (set by the lab wiring).
        """
        from data_engine.runtime.lab import LabError

        if len(bars) < self.MIN_BARS:
            raise LabError(
                f"confidence assessment needs at least {self.MIN_BARS} "
                f"bars (have {len(bars)})"
            )
        if positions is None:
            if self._position_fn is None:
                raise LabError("no position function wired (fail closed)")
            positions = self._position_fn(kind, params, bars)
        closes = [float(b["close"]) for b in bars]

        # -- component 1: strategy vote (recent flip = fresh signal) ----
        strategy_score = self._strategy_score(positions, closes)

        # -- component 2: statistical baseline (momentum vs volatility) --
        from data_engine.runtime.lab import PredictBaseline

        baseline = PredictBaseline().predict(bars)
        p_up = float(baseline["probability_up"])
        baseline_score = (p_up - 0.5) * 2.0

        # -- component 3: trend alignment (EMA50 distance, ATR-scaled) --
        trend_score = self._trend_score(closes, bars)

        score = (
            self.WEIGHTS["strategy"] * strategy_score
            + self.WEIGHTS["baseline"] * baseline_score
            + self.WEIGHTS["trend"] * trend_score
        )
        score = max(-1.0, min(1.0, score))
        if score >= self.DIRECTION_BAND:
            direction = "BULLISH"
        elif score <= -self.DIRECTION_BAND:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"
        confidence = 50.0 + 50.0 * abs(score)
        confirmed = direction != "NEUTRAL" and confidence >= self.THRESHOLD_PCT
        return {
            "direction": direction,
            "confidence_pct": round(confidence, 2),
            "threshold_pct": self.THRESHOLD_PCT,
            "confirmed": confirmed,
            "score": round(score, 4),
            "components": {
                "strategy": round(strategy_score, 4),
                "baseline": round(baseline_score, 4),
                "trend": round(trend_score, 4),
            },
            "weights": dict(self.WEIGHTS),
            "confirmation_candle": {
                "ts": bars[-1]["ts"],
                "close": bars[-1]["close"],
            },
            "bars_used": len(bars),
            "note": (
                "deterministic research heuristic (not a calibrated "
                "probability); gates PAPER-ONLY rapid bursts, never "
                "live trading"
            ),
        }

    # ------------------------------------------------------------------

    def __init__(self, position_fn=None) -> None:
        # position_fn(kind, params, bars) -> List[int]; wired by the lab
        # so the gate never duplicates strategy logic.
        self._position_fn = position_fn

    @staticmethod
    def _strategy_score(positions: List[int], closes: List[float]) -> float:
        """+1 (long) / -1 (flat) vote, damped when the signal is stale."""
        if not positions:
            return 0.0
        current = positions[-1]
        raw = 1.0 if current == 1 else -1.0
        # bars since the most recent flip (staleness gauge)
        age = len(positions) - 1  # never flipped -> fully stale
        for i in range(len(positions) - 1, 0, -1):
            if positions[i] != positions[i - 1]:
                age = len(positions) - 1 - i
                break
        damping = 1.0 if age <= 5 else (0.6 if age <= 20 else 0.3)
        return raw * damping

    @staticmethod
    def _trend_score(closes: List[float], bars: List[dict]) -> float:
        """EMA50 distance scaled by ATR14 (bounded by +-3 ATR)."""
        from data_engine.quant.moving_averages import ema as _ema
        from data_engine.quant.volatility import atr as _atr

        period = 50
        ema_series = _ema(closes, period)
        value = ema_series[-1]
        if value is None:
            return 0.0
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]
        atr_series = _atr(highs, lows, closes, 14)
        a = atr_series[-1]
        if not a or a <= 0:
            return 0.0
        distance = closes[-1] - value
        bounded = max(-3.0, min(3.0, distance / a))
        return bounded / 3.0


__all__ = ["ConfidenceGate"]
