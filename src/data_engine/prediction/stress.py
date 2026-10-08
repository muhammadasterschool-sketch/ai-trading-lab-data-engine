"""Market-stress classification (§4E, §6).

A deterministic stress classifier over PIT-computed inputs. Stress is a
STATE observation, not a forecast: it describes current conditions.
Missing inputs -> UNKNOWN (never guessed). Thresholds are documented
constants; the classifier is versioned for auditability.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict

STRESS_ENGINE_VERSION = "1.0.0"


class MarketStressReading(BaseModel):
    """One stress classification with its inspectable inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state: str
    vol_20: Optional[float]
    dd_depth: Optional[float]
    vol_ratio: Optional[float]
    engine_version: str = STRESS_ENGINE_VERSION

    @property
    def inputs(self) -> dict:
        return {
            "vol_20": self.vol_20,
            "dd_depth": self.dd_depth,
            "vol_ratio": self.vol_ratio,
        }


def classify_market_stress(
    *,
    vol_20: Optional[float],
    dd_depth: Optional[float],
    vol_ratio: Optional[float] = None,
) -> MarketStressReading:
    """Classify current market stress (§4E).

    Bands (documented, daily-bar calibration):
    - EXTREME  dd >= 20% with vol >= 4%
    - SEVERE   dd >= 15%, or dd >= 10% with vol >= 3%
    - STRESSED dd >= 10%, or vol >= 3%
    - ELEVATED dd >= 5%, or vol >= 2%
    - NORMAL   otherwise
    - UNKNOWN  required inputs missing
    """
    from data_engine.prediction.contracts import StressState

    state: str
    if vol_20 is None or dd_depth is None:
        state = StressState.UNKNOWN.value
    elif dd_depth >= 0.20 and vol_20 >= 0.040:
        state = StressState.EXTREME.value
    elif dd_depth >= 0.15 or (dd_depth >= 0.10 and vol_20 >= 0.030):
        state = StressState.SEVERE.value
    elif dd_depth >= 0.10 or vol_20 >= 0.030:
        state = StressState.STRESSED.value
    elif dd_depth >= 0.05 or vol_20 >= 0.020:
        state = StressState.ELEVATED.value
    else:
        state = StressState.NORMAL.value

    return MarketStressReading(
        state=state,
        vol_20=vol_20,
        dd_depth=dd_depth,
        vol_ratio=vol_ratio,
    )


__all__ = [
    "STRESS_ENGINE_VERSION",
    "MarketStressReading",
    "classify_market_stress",
]
