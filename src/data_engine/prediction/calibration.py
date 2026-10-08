"""Calibration (§18): Brier, log loss, reliability, ECE, Platt scaling.

A probability is never presented as reliable unless it is calibrated.
Both ``raw_probability`` and ``calibrated_probability`` travel with the
prediction; the calibration method/version/dataset are recorded.
"""

import math
from typing import Optional, Sequence, Tuple  # ARCH-F5: Optional was used but unimported (latent NameError in annotation scope)

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import (
    CalibrationStatus,
    PredictionContractError,
)
from data_engine.prediction.identity import MODEL_PREFIX, prefixed_hash
from data_engine.prediction.models import PredictionModelError, _sigmoid, _logit


def _validated_pair(probabilities: Sequence[float], outcomes: Sequence[int]) -> None:
    if len(probabilities) != len(outcomes) or not probabilities:
        raise PredictionContractError(
            "probabilities and outcomes must be aligned and non-empty"
        )
    for p in probabilities:
        if not (0.0 <= p <= 1.0):
            raise PredictionContractError(
                f"probability out of range: {p!r}"
            )
    for o in outcomes:
        if o not in (0, 1, True, False):
            raise PredictionContractError(
                f"outcome must be binary, got {o!r}"
            )


def brier_score(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of probabilities (lower is better)."""
    _validated_pair(probabilities, outcomes)
    return math.fsum(
        (p - (1.0 if o else 0.0)) ** 2
        for p, o in zip(probabilities, outcomes)
    ) / len(probabilities)


def log_loss(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """Cross-entropy loss with epsilon clipping (lower is better)."""
    _validated_pair(probabilities, outcomes)
    eps = 1e-12
    total = 0.0
    for p, o in zip(probabilities, outcomes):
        pc = min(max(p, eps), 1.0 - eps)
        oc = 1.0 if o else 0.0
        total -= oc * math.log(pc) + (1.0 - oc) * math.log(1.0 - pc)
    return total / len(probabilities)


class ReliabilityBin(BaseModel):
    """One reliability-curve bin (§18 reliability)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bin_index: int
    count: int
    mean_predicted: float
    empirical_rate: float


def reliability_curve(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> Tuple[ReliabilityBin, ...]:
    """Equal-width reliability bins over [0, 1]; empty bins skipped."""
    _validated_pair(probabilities, outcomes)
    if n_bins < 1:
        raise PredictionContractError("n_bins must be >= 1")
    sums = [0.0] * n_bins
    counts = [0] * n_bins
    positives = [0] * n_bins
    for p, o in zip(probabilities, outcomes):
        idx = min(int(p * n_bins), n_bins - 1)
        counts[idx] += 1
        sums[idx] += p
        if o:
            positives[idx] += 1
    bins = []
    for idx in range(n_bins):
        if counts[idx] == 0:
            continue
        bins.append(
            ReliabilityBin(
                bin_index=idx,
                count=counts[idx],
                mean_predicted=sums[idx] / counts[idx],
                empirical_rate=positives[idx] / counts[idx],
            )
        )
    return tuple(bins)


def expected_calibration_error(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> float:
    """Expected calibration error: count-weighted |predicted - empirical|."""
    bins = reliability_curve(probabilities, outcomes, n_bins=n_bins)
    total = sum(b.count for b in bins)
    if total == 0:
        raise PredictionContractError("no populated reliability bins")
    return math.fsum(
        b.count * abs(b.mean_predicted - b.empirical_rate) for b in bins
    ) / total


class CalibrationReport(BaseModel):
    """Full calibration evidence for one calibrator/dataset pair (§18)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str
    version: str
    dataset_id: str
    n_samples: int
    brier: float
    log_loss: float
    ece: float
    reliability: Tuple[ReliabilityBin, ...]

    @property
    def status(self) -> str:
        if self.n_samples < 30 or self.ece > 0.05:
            return CalibrationStatus.CALIBRATION_INVALID.value
        return CalibrationStatus.CALIBRATION_VALID.value


class PlattCalibrator:
    """Two-parameter Platt scaling fitted by deterministic GD (§18).

    Maps a raw probability through sigmoid(a + b * logit(p)). Fitted on
    a CALIBRATION dataset only — never on the evaluation set (§13).
    """

    version = "platt-v1"
    method = "platt"

    def __init__(self, *, learning_rate: float = 0.5, iterations: int = 200) -> None:
        if learning_rate <= 0 or iterations < 1:
            raise PredictionModelError("invalid calibrator hyperparameters")
        self.learning_rate = learning_rate
        self.iterations = iterations
        self._a: Optional[float] = None
        self._b: Optional[float] = None

    def fit(
        self,
        probabilities: Sequence[float],
        outcomes: Sequence[int],
    ) -> "PlattCalibrator":
        _validated_pair(probabilities, outcomes)
        eps = 1e-6
        logits = [
            _logit(min(max(float(p), eps), 1.0 - eps)) for p in probabilities
        ]
        ys = [1.0 if o else 0.0 for o in outcomes]
        a, b = 0.0, 1.0
        n = len(logits)
        for _ in range(self.iterations):
            grad_a = 0.0
            grad_b = 0.0
            for z, y in zip(logits, ys):
                p = _sigmoid(a + b * z)
                err = p - y
                grad_a += err
                grad_b += err * z
            a -= self.learning_rate * grad_a / n
            b -= self.learning_rate * grad_b / n
        self._a = a
        self._b = b
        return self

    @property
    def fitted(self) -> bool:
        return self._a is not None and self._b is not None

    def calibrate(self, probability: float) -> float:
        """Map one raw probability to its calibrated value."""
        if not self.fitted:
            raise PredictionModelError("calibrator not fitted")
        if not (0.0 <= probability <= 1.0):
            raise PredictionContractError(
                f"probability out of range: {probability!r}"
            )
        eps = 1e-6
        z = _logit(min(max(float(probability), eps), 1.0 - eps))
        return _sigmoid(self._a + self._b * z)  # type: ignore[operator]

    def calibration_hash(self) -> str:
        return prefixed_hash(
            MODEL_PREFIX,
            {
                "kind": "calibrator_artifact",
                "method": self.method,
                "version": self.version,
                "a": float(self._a or 0.0),
                "b": float(self._b or 0.0),
                "learning_rate": self.learning_rate,
                "iterations": float(self.iterations),
            },
        )

    def report(
        self,
        probabilities: Sequence[float],
        outcomes: Sequence[int],
        *,
        dataset_id: str,
    ) -> CalibrationReport:
        """Calibration evidence over a labeled dataset (§18)."""
        if not self.fitted:
            raise PredictionModelError("calibrator not fitted")
        calibrated = [self.calibrate(p) for p in probabilities]
        return CalibrationReport(
            method=self.method,
            version=self.version,
            dataset_id=dataset_id,
            n_samples=len(calibrated),
            brier=brier_score(calibrated, outcomes),
            log_loss=log_loss(calibrated, outcomes),
            ece=expected_calibration_error(calibrated, outcomes),
            reliability=reliability_curve(calibrated, outcomes),
        )


__all__ = [
    "brier_score",
    "log_loss",
    "ReliabilityBin",
    "reliability_curve",
    "expected_calibration_error",
    "CalibrationReport",
    "PlattCalibrator",
]
