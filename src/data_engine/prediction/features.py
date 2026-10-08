"""Prediction risk features — slice-then-compute PIT discipline (§2, §14).

Peer of ``data_engine.quant.features`` (feat6.): the SAME hard as-of
discipline, specialized for regime/crash intelligence. Features are
computed ONLY over the PIT-visible candle prefix (callers pass output of
``prediction.data_access.pit_candle_view``); each feature row records the
exact source index range it was computed from so the label/feature
boundary is structurally provable (§14: no feature may depend on
T+1..T+H).

Feature schema (fixed, versioned — no hidden definitions, §5 discipline
applied to features):

- ``ret_1``        last simple return
- ``mom_20``       20-bar momentum (c_t / c_{t-20} - 1)
- ``vol_20``       20-bar return standard deviation (population)
- ``vol_ratio_5_20`` short/long volatility ratio (None when long vol
  is zero — never fabricated)
- ``dd_depth_20``  drawdown depth within the trailing 20-bar window
- ``range_20``     high/low range of the trailing 20-bar window

Warm-up: the first ``long_window`` bars produce NO row (features never
fabricate warm-up values).
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.identity import (
    FEATURE_PREFIX,
    freeze_number,
    prefixed_hash,
)
from data_engine.prediction.contracts import PredictionContractError

FEATURE_SET_VERSION = "1.0.0"
LONG_WINDOW = 20
SHORT_WINDOW = 5

FEATURE_SCHEMA: Tuple[str, ...] = (
    "ret_1",
    "mom_20",
    "vol_20",
    "vol_ratio_5_20",
    "dd_depth_20",
    "range_20",
)


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _population_std(values: Sequence[float]) -> float:
    mean = _mean(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / len(values))


def feature_set_id() -> str:
    """Identity of the feature schema itself (``predf.``)."""
    return prefixed_hash(
        FEATURE_PREFIX,
        {
            "kind": "feature_set",
            "feature_set_version": FEATURE_SET_VERSION,
            "schema": list(FEATURE_SCHEMA),
            "long_window": LONG_WINDOW,
            "short_window": SHORT_WINDOW,
        },
    )


class FeatureRow(BaseModel):
    """One PIT-computed feature row with its exact source range.

    ``source_start``/``source_end`` are INCLUSIVE indices into the close
    series the row was computed from. ``source_end == row_index`` — the
    row structurally cannot reference bars beyond its own timestamp.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_index: int
    timestamp: Optional[str]
    source_start: int
    source_end: int
    values: Tuple[Optional[float], ...]

    @property
    def feature_vector(self) -> Tuple[Optional[float], ...]:
        return self.values


def build_feature_rows(
    closes: Sequence[float],
    *,
    timestamps: Optional[Sequence[object]] = None,
) -> Tuple[FeatureRow, ...]:
    """Compute prediction features over a PIT-visible close series.

    Raises :class:`PredictionContractError` when fewer than
    ``LONG_WINDOW + 1`` bars are available (insufficient history is a
    refusal, not a fabricated row) or when any close is non-positive
    (data-quality failure — fail closed).
    """
    if len(closes) < LONG_WINDOW + 1:
        raise PredictionContractError(
            f"insufficient bars for feature window: {len(closes)} < "
            f"{LONG_WINDOW + 1} (refusing to fabricate warm-up features)"
        )
    if timestamps is not None and len(timestamps) != len(closes):
        raise PredictionContractError(
            "timestamps must align 1:1 with closes"
        )
    for i, close in enumerate(closes):
        if not (close > 0) or close != close:  # noqa: PLR0124 (NaN check)
            raise PredictionContractError(
                f"non-positive/NaN close at index {i} — data quality "
                "failure (fail closed)"
            )

    rows: list[FeatureRow] = []
    for t in range(LONG_WINDOW, len(closes)):
        window = closes[t - LONG_WINDOW: t + 1]
        returns = [
            window[i] / window[i - 1] - 1.0
            for i in range(1, len(window))
        ]
        long_vol = _population_std(returns)
        short_returns = returns[-SHORT_WINDOW:]
        short_vol = _population_std(short_returns)
        if long_vol == 0.0:
            vol_ratio: Optional[float] = None if short_vol > 0 else 1.0
        else:
            vol_ratio = short_vol / long_vol
        peak = max(window)
        trough = min(window)
        dd_depth = 1.0 - closes[t] / peak
        range_ = (peak - trough) / peak
        ts = None
        if timestamps is not None:
            ts_obj = timestamps[t]
            ts = (
                ts_obj.isoformat()
                if hasattr(ts_obj, "isoformat")
                else str(ts_obj)
            )
        rows.append(
            FeatureRow(
                row_index=t,
                timestamp=ts,
                source_start=t - LONG_WINDOW,
                source_end=t,
                values=(
                    closes[t] / closes[t - 1] - 1.0,
                    closes[t] / closes[t - LONG_WINDOW] - 1.0,
                    long_vol,
                    vol_ratio,
                    dd_depth,
                    range_,
                ),
            )
        )
    return tuple(rows)


def feature_data_hash(rows: Sequence[FeatureRow]) -> str:
    """Deterministic hash of the computed feature data (``predf.``).

    Identical visible history -> identical hash, any process (T-PRED-008).
    """
    payload_rows = [
        {
            "row_index": row.row_index,
            "timestamp": row.timestamp,
            "values": [
                freeze_number(v) if v is not None else None
                for v in row.values
            ],
        }
        for row in rows
    ]
    return prefixed_hash(
        FEATURE_PREFIX,
        {
            "kind": "feature_data",
            "feature_set_id": feature_set_id(),
            "rows": payload_rows,
        },
    )


__all__ = [
    "FEATURE_SET_VERSION",
    "FEATURE_SCHEMA",
    "LONG_WINDOW",
    "SHORT_WINDOW",
    "feature_set_id",
    "FeatureRow",
    "build_feature_rows",
    "feature_data_hash",
]
