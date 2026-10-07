"""Phase 7 — Bias, leakage, and overfitting detection (blueprint 5.24).

Detection layer for the four classic research defects:

- **Look-ahead**: features computed from data beyond the as-of cutoff.
- **Train/test leakage**: overlapping partitions, mis-ordered windows,
  or missing embargo gaps.
- **Survivorship bias**: universe composition checked against a PIT
  universe (requires the 4A.2 PointInTimeUniverse — duck-typed).
- **Overfitting**: parameter-count vs sample-count ratio and
  in-sample/out-of-sample divergence.

Every check returns a typed finding; nothing is silently tolerated.
"""

from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from data_engine.pit.hashing import deterministic_hash

#: Phase 7 contract version.
PHASE_7_CONTRACT_VERSION = "1.0.0"


class BiasFinding(BaseModel):
    """One bias-detection finding (typed, machine-checkable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    check: str
    passed: bool
    detail: str

    @property
    def finding_hash(self) -> str:
        return deterministic_hash(
            {
                "contract_version": PHASE_7_CONTRACT_VERSION,
                "check": self.check,
                "passed": self.passed,
                "detail": self.detail,
            }
        )


def _ts(value: Any):
    if value is None or not hasattr(value, "tzinfo"):
        raise ValueError("timestamps must be datetime objects")
    return value


class BiasDetector:
    """Look-ahead and survivorship checks over feature datasets."""

    def check_lookahead(
        self,
        feature_rows: Sequence[Mapping[str, Any]],
        candles: Sequence[Mapping[str, Any]],
        as_of: Any,
    ) -> BiasFinding:
        """Verify every feature row timestamp is a visible candle time.

        A feature row whose timestamp does not correspond to a candle
        at or before ``as_of`` is look-ahead contamination.
        """
        cutoff = _ts(as_of)
        visible_times = {
            _ts(c.get("timestamp")) for c in candles
            if _ts(c.get("timestamp")) <= cutoff
        }
        bad = [
            _ts(r.get("timestamp"))
            for r in feature_rows
            if _ts(r.get("timestamp")) not in visible_times
        ]
        if bad:
            return BiasFinding(
                check="lookahead",
                passed=False,
                detail=f"{len(bad)} feature rows beyond the as-of cutoff "
                f"(first offender: {bad[0].isoformat()})",
            )
        return BiasFinding(
            check="lookahead", passed=True,
            detail=f"all {len(feature_rows)} rows within the as-of window",
        )

    def check_survivorship(
        self,
        universe_symbols: Sequence[str],
        pit_universe: Any,
        as_of: Any,
    ) -> BiasFinding:
        """Verify a symbol list matches the PIT universe at ``as_of``.

        ``pit_universe`` is duck-typed: anything with a
        ``constituents(as_of)`` method (the 4A.2 PointInTimeUniverse).
        A symbol list missing instruments that were live at ``as_of``
        (but later delisted) carries survivorship bias.
        """
        if not hasattr(pit_universe, "constituents"):
            raise ValueError(
                "pit_universe must expose constituents(as_of) "
                "(the 4A.2 PointInTimeUniverse contract)"
            )
        expected = set(pit_universe.constituents(as_of))
        provided = {s.strip().upper() for s in universe_symbols}
        missing = expected - provided
        if missing:
            return BiasFinding(
                check="survivorship",
                passed=False,
                detail=f"universe omits {len(missing)} live-at-as_of "
                f"instruments: {sorted(missing)[:5]}",
            )
        return BiasFinding(
            check="survivorship", passed=True,
            detail=f"universe matches PIT composition ({len(expected)} "
            "constituents) at as_of",
        )


class LeakageDetector:
    """Partition hygiene: disjoint, ordered, embargoed windows."""

    def check_partition(
        self,
        train_indices: Sequence[int],
        test_indices: Sequence[int],
        embargo: int = 0,
    ) -> BiasFinding:
        """Train/test index hygiene.

        Rules: (1) disjoint sets; (2) every train index strictly before
        every test index (temporal order); (3) at least ``embargo``
        bars of separation (max train index + 1 + embargo <= min test
        index) so test-window feature warm-ups cannot touch train data.
        """
        train, test = set(train_indices), set(test_indices)
        if not train or not test:
            return BiasFinding(
                check="partition", passed=False,
                detail="train and test partitions must both be non-empty",
            )
        overlap = train & test
        if overlap:
            return BiasFinding(
                check="partition", passed=False,
                detail=f"train/test overlap at indices {sorted(overlap)[:5]}",
            )
        if max(train) >= min(test):
            return BiasFinding(
                check="partition", passed=False,
                detail=(
                    "temporal order violated: train index "
                    f"{max(train)} >= test index {min(test)}"
                ),
            )
        gap = min(test) - max(train) - 1
        if gap < embargo:
            return BiasFinding(
                check="partition", passed=False,
                detail=f"embargo violation: gap {gap} < required {embargo}",
            )
        return BiasFinding(
            check="partition", passed=True,
            detail=(
                f"disjoint, ordered, embargo={gap} (>= {embargo} required)"
            ),
        )


class OverfittingDetector:
    """Parameter-count and IS/OOS divergence checks."""

    def check_parameter_ratio(
        self,
        parameter_count: int,
        sample_count: int,
        max_ratio: float = 0.1,
    ) -> BiasFinding:
        """Flag models whose parameter count exceeds max_ratio of samples."""
        if sample_count <= 0:
            return BiasFinding(
                check="parameter_ratio", passed=False,
                detail="no samples to support any parameter count",
            )
        ratio = parameter_count / sample_count
        if ratio > max_ratio:
            return BiasFinding(
                check="parameter_ratio", passed=False,
                detail=(
                    f"parameter/sample ratio {ratio:.4f} exceeds "
                    f"{max_ratio} ({parameter_count} params / {sample_count} samples)"
                ),
            )
        return BiasFinding(
            check="parameter_ratio", passed=True,
            detail=f"parameter/sample ratio {ratio:.4f} within {max_ratio}",
        )

    def check_is_oos_divergence(
        self,
        in_sample_score: float,
        out_of_sample_score: float,
        max_gap: float = 0.5,
    ) -> BiasFinding:
        """Flag IS performance far above OOS (classic overfit signature)."""
        if out_of_sample_score <= 0 and in_sample_score > 0:
            return BiasFinding(
                check="is_oos_divergence", passed=False,
                detail=(
                    f"in-sample {in_sample_score:.4f} vs out-of-sample "
                    f"{out_of_sample_score:.4f}: OOS collapse"
                ),
            )
        if in_sample_score <= 0:
            return BiasFinding(
                check="is_oos_divergence", passed=True,
                detail="in-sample score non-positive; no overfit signature",
            )
        relative_gap = (in_sample_score - out_of_sample_score) / abs(in_sample_score)
        if relative_gap > max_gap:
            return BiasFinding(
                check="is_oos_divergence", passed=False,
                detail=(
                    f"relative IS-OOS gap {relative_gap:.4f} exceeds "
                    f"{max_gap} (IS={in_sample_score:.4f}, "
                    f"OOS={out_of_sample_score:.4f})"
                ),
            )
        return BiasFinding(
            check="is_oos_divergence", passed=True,
            detail=f"relative IS-OOS gap {relative_gap:.4f} within {max_gap}",
        )


__all__ = [
    "BiasFinding",
    "BiasDetector",
    "LeakageDetector",
    "OverfittingDetector",
    "PHASE_7_CONTRACT_VERSION",
]
