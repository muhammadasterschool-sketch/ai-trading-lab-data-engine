"""Phase 7 — Walk-forward validation (blueprint 5.26).

Rolling-window out-of-sample validation with structural leakage
prevention:

- ``WalkForwardWindow``: one (train_start, train_end, test_start,
  test_end) tuple — INCLUSIVE integer index ranges over a bar series.
- ``build_walk_forward_plan``: deterministic plan construction; every
  window is disjoint, ordered, and embargoed BY CONSTRUCTION (a plan
  that violates hygiene cannot exist — invalid parameters raise).
- ``WalkForwardValidator``: re-validates any plan against the data
  length (defense in depth) and evaluates a window runner function,
  aggregating per-window and out-of-sample metrics. Report identity:
  ``wf7.`` prefix.

Invariants (blueprint 5.26): no look-ahead; PIT-correct windows;
separate train/test partitions. The plan format makes overlap
unrepresentable.
"""

from typing import Any, Callable, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.immutable import freeze

#: Identity prefix for walk-forward report hashes.
WALK_FORWARD_PREFIX = "wf7."

#: Phase 7 contract version (shared).
PHASE_7_CONTRACT_VERSION = "1.0.0"


class WalkForwardPlanError(ValueError):
    """Raised when walk-forward parameters cannot produce a valid plan."""


class WalkForwardWindow(BaseModel):
    """One walk-forward window: train [a..b], test [c..d], inclusive."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @field_validator(
        "window_index", "train_start", "train_end", "test_start", "test_end"
    )
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("window indices must be non-negative ints")
        return v

    @model_validator(mode="after")
    def _validate_window(self) -> "WalkForwardWindow":
        if self.train_start > self.train_end:
            raise WalkForwardPlanError("train range empty (start > end)")
        if self.test_start > self.test_end:
            raise WalkForwardPlanError("test range empty (start > end)")
        if self.train_end >= self.test_start:
            raise WalkForwardPlanError(
                "leakage: train_end must be strictly before test_start "
                f"(got train_end={self.train_end} >= "
                f"test_start={self.test_start})"
            )
        return self

    def train_indices(self) -> range:
        return range(self.train_start, self.train_end + 1)

    def test_indices(self) -> range:
        return range(self.test_start, self.test_end + 1)


def build_walk_forward_plan(
    data_length: int,
    train_size: int,
    test_size: int,
    step: Optional[int] = None,
    embargo: int = 0,
    label_horizon: Optional[int] = None,
) -> tuple[WalkForwardWindow, ...]:
    """Deterministic rolling-window plan.

    Windows advance by ``step`` (default: test_size — contiguous OOS
    coverage). ``embargo`` bars separate train end from test start.
    The plan is built greedily while a FULL window fits; the final
    partial window is DISCARDED (no short test windows — every OOS
    measurement uses the full test_size).

    ARCH-F8/F12 correction — sequence-scaled purge: when the caller
    declares ``label_horizon`` (the forward-looking span the labels
    were computed over), an ``embargo < label_horizon`` RAISES: train
    labels look ``label_horizon`` bars ahead, so a shorter embargo
    would leak train label windows into test feature windows. The
    check is opt-in only because this legacy planner serves both
    label-free and label-bearing callers; the runtime sequence
    engine enforces the horizon-scaled purge BY CONSTRUCTION.
    """
    if data_length < 1:
        raise WalkForwardPlanError("data_length must be >= 1")
    if train_size < 1:
        raise WalkForwardPlanError("train_size must be >= 1")
    if test_size < 1:
        raise WalkForwardPlanError("test_size must be >= 1")
    if step is None:
        step = test_size
    if step < 1:
        raise WalkForwardPlanError("step must be >= 1")
    if embargo < 0:
        raise WalkForwardPlanError("embargo must be >= 0")
    if label_horizon is not None:
        if label_horizon < 1:
            raise WalkForwardPlanError("label_horizon must be >= 1")
        if embargo < label_horizon:
            raise WalkForwardPlanError(
                f"embargo {embargo} < label_horizon {label_horizon} "
                "(ARCH-F8/F12: train labels look label_horizon bars "
                "ahead — a shorter embargo leaks train label windows "
                "into test features)"
            )

    windows: list[WalkForwardWindow] = []
    offset = 0
    window_index = 0
    while True:
        train_start = offset
        train_end = offset + train_size - 1
        test_start = train_end + 1 + embargo
        test_end = test_start + test_size - 1
        if test_end >= data_length:
            break
        windows.append(
            WalkForwardWindow(
                window_index=window_index,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        window_index += 1
        offset += step
    if not windows:
        raise WalkForwardPlanError(
            f"data_length {data_length} cannot fit even one window "
            f"(train={train_size}, embargo={embargo}, test={test_size})"
        )
    return tuple(windows)


class WalkForwardReport(BaseModel):
    """Aggregate walk-forward evaluation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window_count: int
    per_window_results: tuple[dict, ...]
    oos_aggregate: dict

    @field_validator("oos_aggregate")
    @classmethod
    def _freeze_aggregate(cls, v: dict) -> dict:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    @property
    def report_hash(self) -> str:
        return WALK_FORWARD_PREFIX + deterministic_hash(
            {
                "contract_version": PHASE_7_CONTRACT_VERSION,
                "window_count": self.window_count,
                "per_window_results": list(self.per_window_results),
                "oos_aggregate": self.oos_aggregate,
            }
        )


class WalkForwardValidator:
    """Validate plans and evaluate window runners deterministically."""

    def validate_plan(
        self,
        windows: Sequence[WalkForwardWindow],
        data_length: int,
    ) -> None:
        """Defense-in-depth re-validation against the data length.

        Rules: every window's test range fits the data; test windows
        advance strictly; no window's TRAIN reaches into a LATER
        window's TEST region (future leakage). Rolling plans whose
        train windows overlap PAST test regions are legitimate — past
        data is known at decision time.
        """
        if not windows:
            raise WalkForwardPlanError("empty plan")
        prev_test_start = -1
        for i, window in enumerate(windows):
            if window.test_end >= data_length:
                raise WalkForwardPlanError(
                    f"window {window.window_index} exceeds data length "
                    f"({window.test_end} >= {data_length})"
                )
            if window.test_start <= prev_test_start:
                raise WalkForwardPlanError(
                    f"window {window.window_index} test range does not "
                    "strictly advance (overlaps or retests prior range)"
                )
            if i > 0 and windows[i - 1].train_end >= window.test_start:
                raise WalkForwardPlanError(
                    f"window {windows[i - 1].window_index} train reaches "
                    f"into window {window.window_index}'s test region "
                    "(future leakage)"
                )
            prev_test_start = window.test_start

    def evaluate(
        self,
        windows: Sequence[WalkForwardWindow],
        data_length: int,
        window_runner: Callable[[WalkForwardWindow], dict[str, Any]],
    ) -> WalkForwardReport:
        """Run ``window_runner`` per window; aggregate OOS metrics.

        The runner receives the window and returns a dict of metrics
        (any JSON-safe scalars). OOS aggregation averages every numeric
        key across windows — deterministic by construction.
        """
        self.validate_plan(windows, data_length)
        per_window = []
        for window in windows:
            result = window_runner(window)
            if not isinstance(result, dict):
                raise WalkForwardPlanError(
                    "window_runner must return a dict of metrics"
                )
            per_window.append(
                {
                    "window_index": window.window_index,
                    "train_start": window.train_start,
                    "train_end": window.train_end,
                    "test_start": window.test_start,
                    "test_end": window.test_end,
                    **{k: v for k, v in result.items()},
                }
            )
        numeric_keys = {
            k
            for entry in per_window
            for k, v in entry.items()
            if isinstance(v, (int, float)) and k != "window_index"
        }
        aggregate: dict[str, float] = {}
        for key in sorted(numeric_keys):
            values = [
                e[key] for e in per_window
                if isinstance(e.get(key), (int, float))
            ]
            if values:
                aggregate[key] = sum(values) / len(values)
        return WalkForwardReport(
            window_count=len(windows),
            per_window_results=tuple(per_window),
            oos_aggregate=aggregate,
        )


__all__ = [
    "WalkForwardWindow",
    "WalkForwardPlanError",
    "build_walk_forward_plan",
    "WalkForwardReport",
    "WalkForwardValidator",
    "WALK_FORWARD_PREFIX",
]
