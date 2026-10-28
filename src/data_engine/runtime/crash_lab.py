"""v1.5.0 lab crash-risk + next-move ensemble (research heuristics).

Owner mandate (2026-10-28): "is ke pass crash prediction aur next
market move predict kar pae".

HONEST positioning (same posture as PredictBaseline):

- These are DETERMINISTIC statistical heuristics over owner-supplied
  bars: volatility z-scores, ATR expansion, drawdown speed, momentum
  ensembles. They are NOT the governed ``data_engine.prediction``
  §4F crash contract (CrashRiskEstimator remains the research path
  with calibration/uncertainty/redteam machinery) and they are NOT
  investment advice.
- Crash "probability" is a heuristic severity score mapped through a
  logistic squash — it is a gauge, not a verified probability, and it
  gates nothing by itself.
- Every output carries its trigger breakdown so the owner can audit
  which feature fired.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from data_engine.runtime.lab import LabError


class LabCrashPredictor:
    """Heuristic downside-risk gauge over closed bars."""

    MIN_BARS = 60
    #: logistic weights (documented, deterministic, auditable)
    _W = {"vol_z": 0.55, "atr_expansion": 0.30, "dd_speed": 0.45,
          "consecutive": 0.10}
    _BIAS = -4.2

    def predict(self, bars: List[dict]) -> Dict[str, Any]:
        if len(bars) < self.MIN_BARS:
            raise LabError(
                f"crash prediction needs at least {self.MIN_BARS} bars "
                f"(have {len(bars)}); upload history via POST /api/lab/bars"
            )
        closes = [float(b["close"]) for b in bars]
        highs = [float(b["high"]) for b in bars]
        lows = [float(b["low"]) for b in bars]

        # -- feature 1: realized-vol z-score (20-bar vol vs 200-bar) -----
        def _vol(window: List[float]) -> float:
            rets = [
                math.log(window[i] / window[i - 1])
                for i in range(1, len(window))
                if window[i - 1] > 0
            ]
            mean = sum(rets) / max(1, len(rets))
            var = sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1)
            return math.sqrt(var)

        recent_vol = _vol(closes[-20:])
        vol_history = [
            _vol(closes[i - 20: i]) for i in range(40, len(closes), 10)
        ]
        vol_history = [v for v in vol_history if v > 0]
        if vol_history and recent_vol > 0:
            v_mean = sum(vol_history) / len(vol_history)
            v_std = (
                sum((v - v_mean) ** 2 for v in vol_history) / len(vol_history)
            ) ** 0.5
            vol_z = (recent_vol - v_mean) / v_std if v_std > 0 else 0.0
        else:
            vol_z = 0.0

        # -- feature 2: ATR expansion (last ATR14 vs its 50-bar mean) ----
        from data_engine.quant.volatility import atr as _atr

        atr_series = _atr(highs, lows, closes, 14)
        valid_atr = [a for a in atr_series if a is not None]
        if len(valid_atr) >= 20:
            atr_mean = sum(valid_atr[-50:]) / len(valid_atr[-50:])
            atr_expansion = (
                (valid_atr[-1] / atr_mean - 1.0) if atr_mean > 0 else 0.0
            )
        else:
            atr_expansion = 0.0

        # -- feature 3: drawdown speed over the last 10 bars -------------
        window = closes[-10:]
        peak = max(window)
        trough = min(window)
        dd_speed = (peak - trough) / peak if peak > 0 else 0.0

        # -- feature 4: consecutive adverse closes -----------------------
        consecutive = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] < closes[i - 1]:
                consecutive += 1
            else:
                break

        z = (
            self._W["vol_z"] * max(0.0, vol_z)
            + self._W["atr_expansion"] * max(0.0, atr_expansion) * 10.0
            + self._W["dd_speed"] * dd_speed * 20.0
            + self._W["consecutive"] * consecutive
            + self._BIAS
        )
        probability = 1.0 / (1.0 + math.exp(-z))
        probability = min(0.95, max(0.02, probability))
        if probability >= 0.60:
            level = "SEVERE"
        elif probability >= 0.40:
            level = "ELEVATED"
        elif probability >= 0.20:
            level = "MODERATE"
        else:
            level = "LOW"
        return {
            "crash_probability": round(probability, 4),
            "risk_level": level,
            "horizon_bars": 30,
            "triggers": {
                "volatility_zscore": round(vol_z, 4),
                "atr_expansion_pct": round(atr_expansion * 100.0, 4),
                "drawdown_speed_pct": round(dd_speed * 100.0, 4),
                "consecutive_down_bars": consecutive,
            },
            "weights": dict(self._W),
            "bars_used": len(bars),
            "disclaimer": (
                "heuristic research gauge (NOT the governed §4F crash "
                "contract, NOT a verified probability, NOT investment "
                "advice); live trading stays NOT_AUTHORIZED"
            ),
        }


class NextMoveEnsemble:
    """Multi-component next-move assessment (baseline + trend + ER)."""

    MIN_BARS = 60
    _W = {"baseline": 0.50, "trend": 0.30, "efficiency": 0.20}

    def predict(self, bars: List[dict]) -> Dict[str, Any]:
        if len(bars) < self.MIN_BARS:
            raise LabError(
                f"ensemble prediction needs at least {self.MIN_BARS} bars "
                f"(have {len(bars)})"
            )
        from data_engine.runtime.lab import PredictBaseline
        from data_engine.quant.moving_averages import ema as _ema
        from data_engine.quant.statistics_ext import efficiency_ratio

        baseline = PredictBaseline().predict(bars)
        closes = [float(b["close"]) for b in bars]
        p_up_base = float(baseline["probability_up"])

        ema50 = _ema(closes, 50)[-1]
        if ema50 and ema50 > 0:
            trend_component = max(
                -1.0, min(1.0, (closes[-1] / ema50 - 1.0) * 40.0)
            )
        else:
            trend_component = 0.0

        er_series = efficiency_ratio(closes, 10)
        er = er_series[-1] if er_series and er_series[-1] is not None else 0.0
        momentum_sign = 1.0 if closes[-1] >= closes[-11] else -1.0
        efficiency_component = momentum_sign * er

        score = (
            self._W["baseline"] * (p_up_base - 0.5) * 2.0
            + self._W["trend"] * trend_component
            + self._W["efficiency"] * efficiency_component
        )
        score = max(-1.0, min(1.0, score))
        p_up = 1.0 / (1.0 + math.exp(-3.0 * score))
        if p_up > 0.55:
            direction = "UP"
        elif p_up < 0.45:
            direction = "DOWN"
        else:
            direction = "FLAT"
        return {
            "direction": direction,
            "probability_up": round(p_up, 4),
            "probability_down": round(1.0 - p_up, 4),
            "horizon_bars": 5,
            "components": {
                "baseline_pct": round((p_up_base - 0.5) * 200.0, 2),
                "trend_pct": round(trend_component * 100.0, 2),
                "efficiency_pct": round(efficiency_component * 100.0, 2),
            },
            "weights": dict(self._W),
            "bars_used": len(bars),
            "baseline": baseline,
            "disclaimer": (
                "deterministic research ensemble (not a learned model, "
                "not investment advice); predicts nothing about live "
                "trading (which stays NOT_AUTHORIZED)"
            ),
        }


__all__ = ["LabCrashPredictor", "NextMoveEnsemble"]
