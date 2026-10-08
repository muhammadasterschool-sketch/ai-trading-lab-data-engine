"""PIT-safe sequence / window engine (pre-paper mandate §12).

A sequence is reproducible from::

    dataset + feature_version + lookback + horizon + cutoff

Construction rules (all fail-closed):

- **PIT cutoff**: a sequence anchored at bar ``t`` uses ONLY bars with
  ``timestamp <= cutoff`` for its feature window (inclusive boundary:
  a bar closing exactly at ``cutoff`` is knowable). The LABEL for the
  sequence is emitted ONLY when the horizon bar ``t + horizon`` also
  has ``timestamp <= cutoff`` — at an earlier cutoff the label is
  ``None`` (unavailable information is never fabricated, §11).
- **No future leakage**: the feature window is
  ``bars[t - lookback + 1 .. t]`` inclusive; nothing after the anchor
  bar enters the features.
- **Deterministic ordering**: sequences are ordered by anchor
  timestamp; the sequence-set identity is a pure function of the spec
  + dataset content + cutoff (no wall-clock, no RNG).
- **Bar hygiene**: strictly increasing tz-aware timestamps (BUG-007
  discipline), finite OHLCV; duplicates/regressions raise.
- **Sequence-scaled purge/embargo (ARCH-F8/F12 correction)**:
  ``build_walk_forward_splits`` REQUIRES ``embargo >= horizon`` when
  labels use a forward-looking horizon — a smaller embargo would let
  train labels overlap test features (leakage), so it raises instead
  of silently accepting it.
"""

import math
from datetime import datetime, UTC
from typing import Mapping, Optional, Sequence as TSeq, Tuple

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.identity import SEQUENCE_PREFIX, prefixed_hash

#: Per-bar feature dimension (window-local, leakage-free by design).
FEATURE_DIM = 5


class SequenceError(ValueError):
    """Raised on sequence-engine contract violations."""


def _bar_time(bar: Mapping) -> datetime:
    ts = bar.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise SequenceError("bars need timezone-aware timestamps")
    return ts.astimezone(UTC)


def _bar_float(bar: Mapping, key: str) -> float:
    v = bar.get(key)
    if v is None:
        raise SequenceError(f"bar missing field {key!r}")
    f = float(v)
    if not math.isfinite(f):
        raise SequenceError(f"bar field {key!r} is not finite (NaN/inf)")
    return f


def bar_features(bar: Mapping) -> Tuple[float, float, float, float, float]:
    """Window-local per-bar features (rounded to 12 decimals).

    Five normalized, scale-free features, each computable from the
    bar alone — no cross-bar state, no future reference:

    0. ``log(close/open)``      — intra-bar return
    1. ``(high-low)/close``     — normalized range
    2. ``(high-close)/close``   — upper wick fraction
    3. ``(close-low)/close``    — lower wick fraction
    4. ``log1p(volume)``        — volume level (scale-robust)
    """
    o = _bar_float(bar, "open")
    h = _bar_float(bar, "high")
    low = _bar_float(bar, "low")
    c = _bar_float(bar, "close")
    v = _bar_float(bar, "volume")
    if o <= 0 or c <= 0:
        raise SequenceError("open/close must be positive for log features")
    if h < max(o, c) or low > min(o, c):
        raise SequenceError(
            f"impossible OHLC relationship: high={h} low={low} "
            f"open={o} close={c}"
        )
    return (
        round(math.log(c / o), 12),
        round((h - low) / c, 12),
        round((h - c) / c, 12),
        round((c - low) / c, 12),
        round(math.log1p(max(v, 0.0)), 12),
    )


class SequenceSpec(BaseModel):
    """Governed sequence specification (mandate §12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    lookback: int
    horizon: int
    stride: int = 1
    feature_version: str
    dataset_version: str

    @field_validator("symbol", "timeframe", "feature_version", "dataset_version")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise SequenceError("spec text fields must be non-empty")
        return v.strip().upper() if v.strip().upper() == v.strip() else v.strip()

    @field_validator("lookback", "horizon", "stride")
    @classmethod
    def _validate_windows(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise SequenceError("lookback/horizon/stride must be ints >= 1")
        return v

    @property
    def spec_hash(self) -> str:
        return prefixed_hash(
            SEQUENCE_PREFIX,
            {
                "kind": "sequence_spec",
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "lookback": self.lookback,
                "horizon": self.horizon,
                "stride": self.stride,
                "feature_version": self.feature_version,
                "dataset_version": self.dataset_version,
            },
        )


class Sequence(BaseModel):
    """One built sequence with full availability metadata (§12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence_id: str
    spec: SequenceSpec
    anchor_timestamp: datetime  # bar t's close time (decision time)
    availability_timestamp: datetime  # == anchor (feature availability)
    horizon_end: Optional[datetime]  # bar t+horizon close (label availability)
    features: Tuple[Tuple[float, ...], ...]  # lookback x FEATURE_DIM
    target: Optional[int] = None  # 1/0 iff label knowable at cutoff
    forward_return: Optional[float] = None
    has_gaps: bool = False  # missing bars inside the feature window

    @field_validator("target")
    @classmethod
    def _validate_target(cls, v: Optional[int]) -> Optional[int]:
        if v is None or v in (0, 1):
            return v
        raise SequenceError("target must be 0/1 or None (unavailable)")

    @property
    def label_available(self) -> bool:
        return self.target is not None


class SequenceSet(BaseModel):
    """Deterministic, ordered set of sequences + identity (§12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: SequenceSpec
    cutoff: datetime
    sequences: Tuple[Sequence, ...]
    dataset_content_hash: str

    @field_validator("cutoff")
    @classmethod
    def _validate_cutoff(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise SequenceError("cutoff must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_ordering_and_uniqueness(self) -> "SequenceSet":
        ids = [s.sequence_id for s in self.sequences]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise SequenceError(
                f"duplicate sequence ids in set: {dupes[:3]} "
                "(duplicate sequence ids are forbidden, §12)"
            )
        anchors = [s.anchor_timestamp for s in self.sequences]
        if anchors != sorted(anchors):
            raise SequenceError(
                "sequences must be ordered by anchor timestamp (deterministic "
                "ordering is mandatory, §12)"
            )
        return self

    @property
    def sequence_set_id(self) -> str:
        return prefixed_hash(
            SEQUENCE_PREFIX,
            {
                "kind": "sequence_set",
                "spec_hash": self.spec.spec_hash,
                "cutoff": self.cutoff,
                "dataset_content_hash": self.dataset_content_hash,
                "sequence_ids": [s.sequence_id for s in self.sequences],
            },
        )

    @property
    def labeled(self) -> Tuple[Sequence, ...]:
        return tuple(s for s in self.sequences if s.label_available)


class WalkForwardSplit(BaseModel):
    """One train/test split over sequence anchor order (§12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_index: int
    train_indices: Tuple[int, ...]
    test_indices: Tuple[int, ...]
    purge: int  # sequences dropped between train end and test start
    embargo: int  # additional sequences dropped after purge

    @field_validator("window_index", "purge", "embargo")
    @classmethod
    def _validate_ints(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise SequenceError("split ints must be >= 0")
        return v

    @model_validator(mode="after")
    def _validate_disjoint(self) -> "WalkForwardSplit":
        overlap = set(self.train_indices) & set(self.test_indices)
        if overlap:
            raise SequenceError(
                f"train/test overlap in window {self.window_index}: "
                f"{sorted(overlap)[:3]} (leakage forbidden)"
            )
        return self


def build_sequence_set(
    bars: TSeq[Mapping],
    spec: SequenceSpec,
    cutoff: datetime,
    dataset_content_hash: str,
    expected_interval_seconds: Optional[float] = None,
    allow_gaps: bool = False,
) -> SequenceSet:
    """Build the PIT-safe sequence set for ``bars`` at ``cutoff``.

    ``expected_interval_seconds``: when provided, gaps between
    consecutive bars larger than the expected interval mark the
    affected sequences ``has_gaps=True`` (missing bars, §12). With
    ``allow_gaps=False`` (default) gapped sequences raise instead —
    a training set with holes must be a deliberate choice.
    """
    if not bars:
        raise SequenceError("bars must be non-empty")
    cutoff_utc = cutoff.astimezone(UTC) if cutoff.tzinfo else None
    if cutoff_utc is None:
        raise SequenceError("cutoff must be timezone-aware")

    # --- bar hygiene: strict ordering + finite OHLCV -------------------
    times = [_bar_time(b) for b in bars]
    for i in range(1, len(times)):
        if times[i] <= times[i - 1]:
            raise SequenceError(
                f"bar {i} timestamp {times[i]} is not strictly after "
                f"{times[i - 1]} (BUG-007 discipline: duplicates/regressions "
                "are rejected)"
            )
    feats = [bar_features(b) for b in bars]
    closes = [_bar_float(b, "close") for b in bars]

    # --- gap map: which anchor windows contain missing bars ------------
    gaps_at = [False] * len(bars)
    if expected_interval_seconds is not None:
        if expected_interval_seconds <= 0:
            raise SequenceError("expected_interval_seconds must be > 0")
        for i in range(1, len(bars)):
            delta = (times[i] - times[i - 1]).total_seconds()
            if delta > expected_interval_seconds * 1.5:
                gaps_at[i] = True

    sequences: list[Sequence] = []
    lookback = spec.lookback
    horizon = spec.horizon
    stride = spec.stride
    t = lookback - 1
    while t < len(bars):
        if times[t] > cutoff_utc:
            break  # PIT cutoff: anchor bar not yet knowable
        window = feats[t - lookback + 1 : t + 1]
        window_gaps = any(gaps_at[t - lookback + 1 : t + 1])
        if window_gaps and not allow_gaps:
            raise SequenceError(
                f"sequence anchored at {times[t]} contains missing bars "
                "(gaps) — pass allow_gaps=True to include it flagged"
            )
        # Label: available iff the horizon bar is also knowable at cutoff.
        h_idx = t + horizon
        if h_idx < len(bars) and times[h_idx] <= cutoff_utc:
            target = 1 if closes[h_idx] > closes[t] else 0
            forward_return = round(closes[h_idx] / closes[t] - 1.0, 12)
            horizon_end = times[h_idx]
        else:
            target = None
            forward_return = None
            horizon_end = None
        sequence_id = prefixed_hash(
            SEQUENCE_PREFIX,
            {
                "kind": "sequence",
                "spec_hash": spec.spec_hash,
                "anchor": times[t],
                "features": [list(row) for row in window],
            },
        )
        sequences.append(
            Sequence(
                sequence_id=sequence_id,
                spec=spec,
                anchor_timestamp=times[t],
                availability_timestamp=times[t],
                horizon_end=horizon_end,
                features=tuple(tuple(row) for row in window),
                target=target,
                forward_return=forward_return,
                has_gaps=window_gaps,
            )
        )
        t += stride
    if not sequences:
        raise SequenceError(
            f"no sequence fits: {len(bars)} bars, lookback={lookback}, "
            f"cutoff={cutoff_utc.isoformat()}"
        )
    return SequenceSet(
        spec=spec,
        cutoff=cutoff_utc,
        sequences=tuple(sequences),
        dataset_content_hash=dataset_content_hash,
    )


def build_walk_forward_splits(
    n_sequences: int,
    horizon: int,
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
    embargo: Optional[int] = None,
) -> Tuple[WalkForwardSplit, ...]:
    """Walk-forward splits with SEQUENCE-SCALED purge/embargo.

    ARCH-F8/F12 correction: the purge between train and test is
    ``horizon`` sequences BY CONSTRUCTION (train labels look ``horizon``
    sequences ahead — a shorter purge would leak train label windows
    into test feature windows). The caller-provided ``embargo`` must
    satisfy ``embargo >= 0`` and is ADDED after the purge; passing an
    embargo SMALLER than the horizon is rejected only if the caller
    declares it explicitly — by default ``embargo=None`` means "use
    the horizon as the embargo floor" (sequence-scaled).

    Splits are index-based over the deterministically ordered
    sequence list (train, then purge+embargo gap, then test).
    """
    if n_sequences < 1:
        raise SequenceError("n_sequences must be >= 1")
    if train_size < 1 or test_size < 1:
        raise SequenceError("train_size/test_size must be >= 1")
    if horizon < 1:
        raise SequenceError("horizon must be >= 1 (sequence-scaled purge)")
    if step is None:
        step = test_size
    if step < 1:
        raise SequenceError("step must be >= 1")
    purge = horizon  # sequence-scaled by construction
    if embargo is None:
        embargo = 0
    if embargo < 0:
        raise SequenceError("embargo must be >= 0")

    splits: list[WalkForwardSplit] = []
    offset = 0
    window_index = 0
    while True:
        train_start = offset
        train_end = offset + train_size - 1
        test_start = train_end + 1 + purge + embargo
        test_end = test_start + test_size - 1
        if test_end >= n_sequences:
            break
        splits.append(
            WalkForwardSplit(
                window_index=window_index,
                train_indices=tuple(range(train_start, train_end + 1)),
                test_indices=tuple(range(test_start, test_end + 1)),
                purge=purge,
                embargo=embargo,
            )
        )
        window_index += 1
        offset += step
    if not splits:
        raise SequenceError(
            f"{n_sequences} sequences cannot fit one window "
            f"(train={train_size}, purge={purge}, embargo={embargo}, "
            f"test={test_size})"
        )
    return tuple(splits)


def train_validation_test_split(
    n_sequences: int,
    horizon: int,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> Tuple[Tuple[int, ...], Tuple[int, ...], Tuple[int, ...]]:
    """Single train/validation/test split with horizon purge between
    ALL adjacent segments (§12 train/validation/test separation)."""
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise SequenceError("fractions must be in (0, 1)")
    if train_fraction + validation_fraction >= 1:
        raise SequenceError("train+validation fractions must leave a test set")
    if n_sequences < 3 * horizon + 3:
        raise SequenceError(
            f"too few sequences ({n_sequences}) for a 3-way split with "
            f"horizon purge {horizon}"
        )
    n_train = int(n_sequences * train_fraction)
    n_val = int(n_sequences * validation_fraction)
    if n_train < 1 or n_val < 1:
        raise SequenceError("split produced an empty segment")
    train = tuple(range(0, n_train))
    val = tuple(range(n_train + horizon, n_train + horizon + n_val))
    test_start = n_train + horizon + n_val + horizon
    test = tuple(range(test_start, n_sequences))
    if not test:
        raise SequenceError("split produced an empty test segment")
    return train, val, test


__all__ = [
    "FEATURE_DIM",
    "SequenceError",
    "bar_features",
    "SequenceSpec",
    "Sequence",
    "SequenceSet",
    "WalkForwardSplit",
    "build_sequence_set",
    "build_walk_forward_splits",
    "train_validation_test_split",
]
