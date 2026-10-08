"""Market regime engine (§7) — deterministic, PIT-correct, versioned.

The engine is a PURE function of PIT-computed features: same features ->
same regime, any process. Unknown/missing inputs classify as UNKNOWN —
never guessed. Regime transitions are themselves recorded as events
(§7), each stamped with the engine version so historical classifications
remain auditable and backtestable.

Threshold semantics (daily-bar calibration, documented constants — no
hidden tuning):
- VOL_HIGH / VOL_LOW   absolute 20-bar return-volatility bands
- RATIO_HIGH/LOW       short/long volatility-ratio bands (regime shift)
- DD_CRISIS/DD_STRESSED trailing drawdown depth bands
- MOM_TREND            20-bar momentum magnitude for trend regimes
- BREADTH_*            optional cross-sectional breadth gates for
                       RISK_ON / RISK_OFF
"""

from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import (  # ARCH-F7: dedicated prefix
    prefixed_hash,
    REGIME_EVENT_PREFIX,
)

REGIME_ENGINE_VERSION = "1.0.0"


class RegimeFeatures(BaseModel):
    """Inputs to the regime classifier (all PIT-computed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vol_20: Optional[float] = None
    vol_ratio: Optional[float] = None
    dd_depth: Optional[float] = None
    mom_20: Optional[float] = None
    breadth: Optional[float] = None

    @field_validator("vol_20", "vol_ratio", "dd_depth", "mom_20", "breadth")
    @classmethod
    def _validate_finite(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return v
        if v != v or v in (float("inf"), float("-inf")):
            raise PredictionContractError(
                "regime features must be finite or None (missing)"
            )
        return v


class RegimeTransitionEvent(BaseModel):
    """One recorded regime transition (§7 — transitions are events)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    from_state: str
    to_state: str
    engine_version: str
    timestamp: Optional[str] = None

    @property
    def event_id(self) -> str:
        return prefixed_hash(
            REGIME_EVENT_PREFIX,
            {
                "kind": "regime_transition_event",
                "index": self.index,
                "from_state": self.from_state,
                "to_state": self.to_state,
                "engine_version": self.engine_version,
                "timestamp": self.timestamp,
            },
        )


class RegimeEngine:
    """Deterministic regime classifier (§7).

    Classification order is FIXED and documented: CRISIS -> STRESSED ->
    HIGH_VOLATILITY -> LOW_VOLATILITY -> TRANSITION -> trend/breadth
    states -> RANGE -> NORMAL. Missing core inputs -> UNKNOWN.
    """

    engine_version: str = REGIME_ENGINE_VERSION

    VOL_HIGH: float = 0.030
    VOL_LOW: float = 0.005
    RATIO_HIGH: float = 2.0
    RATIO_LOW: float = 0.5
    DD_CRISIS: float = 0.20
    DD_STRESSED: float = 0.10
    MOM_TREND: float = 0.10
    MOM_RANGE: float = 0.02
    BREADTH_RISK_ON: float = 0.60
    BREADTH_RISK_OFF: float = 0.35

    def classify(self, features: RegimeFeatures) -> str:
        """Classify one feature snapshot. Returns a RegimeState value."""
        from data_engine.prediction.contracts import RegimeState

        vol = features.vol_20
        ratio = features.vol_ratio
        dd = features.dd_depth
        mom = features.mom_20

        if vol is None or dd is None or mom is None:
            return RegimeState.UNKNOWN.value

        if dd >= self.DD_CRISIS and vol >= self.VOL_HIGH:
            return RegimeState.CRISIS.value
        if dd >= self.DD_STRESSED and (
            vol >= self.VOL_HIGH or (ratio is not None and ratio >= self.RATIO_HIGH)
        ):
            return RegimeState.STRESSED.value
        if ratio is not None and ratio >= self.RATIO_HIGH and vol >= self.VOL_HIGH:
            return RegimeState.HIGH_VOLATILITY.value
        if vol <= self.VOL_LOW:
            return RegimeState.LOW_VOLATILITY.value
        if ratio is not None and (
            ratio >= self.RATIO_HIGH or ratio <= self.RATIO_LOW
        ):
            return RegimeState.TRANSITION.value
        if mom >= self.MOM_TREND:
            if features.breadth is not None and features.breadth >= self.BREADTH_RISK_ON:
                return RegimeState.RISK_ON.value
            return RegimeState.TRENDING.value
        if mom <= -self.MOM_TREND:
            if features.breadth is not None and features.breadth <= self.BREADTH_RISK_OFF:
                return RegimeState.RISK_OFF.value
            return RegimeState.TRENDING.value
        if abs(mom) <= self.MOM_RANGE:
            return RegimeState.RANGE.value
        return RegimeState.NORMAL.value

    def classify_series(
        self,
        features_seq: Sequence[RegimeFeatures],
    ) -> Tuple[str, ...]:
        """Classify a PIT-ordered feature sequence."""
        return tuple(self.classify(f) for f in features_seq)

    @staticmethod
    def regime_transitions(
        states: Sequence[str],
        *,
        timestamps: Optional[Sequence[object]] = None,
        engine_version: str = REGIME_ENGINE_VERSION,
    ) -> Tuple[RegimeTransitionEvent, ...]:
        """Record every regime change as an event (§7, T-PRED-014)."""
        if timestamps is not None and len(timestamps) != len(states):
            raise PredictionContractError(
                "timestamps must align 1:1 with states"
            )
        events: list[RegimeTransitionEvent] = []
        previous: Optional[str] = None
        for i, state in enumerate(states):
            if previous is not None and state != previous:
                ts = None
                if timestamps is not None:
                    ts_obj = timestamps[i]
                    ts = (
                        ts_obj.isoformat()
                        if hasattr(ts_obj, "isoformat")
                        else str(ts_obj)
                    )
                events.append(
                    RegimeTransitionEvent(
                        index=i,
                        from_state=previous,
                        to_state=state,
                        engine_version=engine_version,
                        timestamp=ts,
                    )
                )
            previous = state
        return tuple(events)


__all__ = [
    "REGIME_ENGINE_VERSION",
    "RegimeFeatures",
    "RegimeTransitionEvent",
    "RegimeEngine",
]
