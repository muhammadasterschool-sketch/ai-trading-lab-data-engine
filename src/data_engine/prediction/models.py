"""Model layer — baseline-first (§8, §9), deterministic training.

Every prediction target must first have a simple deterministic baseline
(§9). Advanced models must DEMONSTRATE improvement over their baseline
under a predefined protocol, otherwise the verdict is
MODEL_NOT_JUSTIFIED (§9) — no model is useful merely because it is
sophisticated, and none is added for complexity's own sake (§8).

Implemented families:
- Baselines: global base rate, rolling base rate, naive persistence,
  regime-conditional base rate, random (no-skill floor).
- LogisticCrashModel: deterministic gradient-descent logistic model with
  train-set-only standardization (§13: learned transformations are
  fitted ONLY on permitted historical data).

All training is order-stable and uses ``math.fsum`` accumulations so
results are bit-reproducible across processes (T-PREV-006/007).
"""

import math
from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import (
    InsufficiencyState,
    PredictionContractError,
)
from data_engine.prediction.identity import MODEL_PREFIX, prefixed_hash


class PredictionModelError(ValueError):
    """Raised on model-contract violations (fail closed)."""


def _sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _logit(p: float) -> float:
    if not (0.0 < p < 1.0):
        raise PredictionModelError(
            "logit requires p strictly inside (0, 1) — degenerate "
            "probabilities must be clipped by the caller, never silently"
        )
    return math.log(p / (1.0 - p))


class ModelArtifact(BaseModel):
    """Identity-relevant facts about a fitted model (§16 AI provenance)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    model_version: str
    model_family: str
    feature_names: Tuple[str, ...]
    parameters: Tuple[Tuple[str, float], ...]

    @property
    def model_hash(self) -> str:
        """Artifact hash (``predm.``) — integrity-checked before use (§44)."""
        return prefixed_hash(
            MODEL_PREFIX,
            {
                "kind": "model_artifact",
                "model_id": self.model_id,
                "model_version": self.model_version,
                "model_family": self.model_family,
                "feature_names": list(self.feature_names),
                "parameters": [list(pair) for pair in self.parameters],
            },
        )


class BaseRateBaseline:
    """Unconditional historical base rate with Laplace smoothing (§9).

    The canonical crash-probability baseline: p = (pos + 1) / (n + 2).
    """

    model_family = "baseline-base-rate"

    def __init__(self, model_id: str = "BASE-RATE", model_version: str = "1") -> None:
        self.model_id = model_id
        self.model_version = model_version
        self._rate: Optional[float] = None
        self._n = 0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "BaseRateBaseline":
        del X  # unconditional — features unused by design
        if not y:
            raise PredictionModelError("training data must be non-empty")
        pos = sum(1 for v in y if v)
        self._n = len(y)
        self._rate = (pos + 1) / (self._n + 2)
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        if self._rate is None:
            raise PredictionModelError("model not fitted")
        return self._rate

    def artifact(self) -> ModelArtifact:
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=(),
            parameters=(("rate", float(self._rate or 0.0)),),
        )

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "BaseRateBaseline":
        """RT-F14: reconstruct a fitted model from its artifact."""
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        params = dict(artifact.parameters)
        model = cls(
            model_id=artifact.model_id,
            model_version=artifact.model_version,
        )
        model._n = 0
        model._rate = float(params["rate"])
        return model

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash


class RollingBaseRateBaseline:
    """Base rate over the trailing ``window`` labels (recent-conditions)."""

    model_family = "baseline-rolling-base-rate"

    def __init__(self, window: int = 60, model_id: str = "ROLL-RATE", model_version: str = "1") -> None:
        if window < 1:
            raise PredictionModelError("window must be >= 1")
        self.window = window
        self.model_id = model_id
        self.model_version = model_version
        self._recent: Tuple[int, ...] = ()

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "RollingBaseRateBaseline":
        del X
        if not y:
            raise PredictionModelError("training data must be non-empty")
        self._recent = tuple(1 if v else 0 for v in y[-self.window:])
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        if not self._recent:
            raise PredictionModelError("model not fitted")
        pos = sum(self._recent)
        return (pos + 1) / (len(self._recent) + 2)

    def artifact(self) -> ModelArtifact:
        pos = sum(self._recent)
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=(),
            parameters=(
                ("window", float(self.window)),
                ("recent_positives", float(pos)),
                ("recent_n", float(len(self._recent))),
            ),
        )

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "RollingBaseRateBaseline":
        """RT-F14: reconstruct from the artifact (rates rebuilt exactly)."""
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        params = dict(artifact.parameters)
        window = int(params["window"])
        n = int(params["recent_n"])
        pos = int(params["recent_positives"])
        if not 0 <= pos <= n:
            raise PredictionModelError(
                "inconsistent artifact: recent_positives > recent_n"
            )
        model = cls(
            window=window,
            model_id=artifact.model_id,
            model_version=artifact.model_version,
        )
        model._recent = tuple([1] * pos + [0] * (n - pos))
        return model

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash


class NaivePersistenceBaseline:
    """Predicts the last observed outcome (§9 naive persistence)."""

    model_family = "baseline-naive-persistence"

    def __init__(self, model_id: str = "NAIVE-PERSIST", model_version: str = "1") -> None:
        self.model_id = model_id
        self.model_version = model_version
        self._last: Optional[int] = None

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "NaivePersistenceBaseline":
        del X
        if not y:
            raise PredictionModelError("training data must be non-empty")
        self._last = 1 if y[-1] else 0
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        if self._last is None:
            raise PredictionModelError("model not fitted")
        return 0.9 if self._last else 0.1

    def artifact(self) -> ModelArtifact:
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=(),
            parameters=(("last_outcome", float(self._last or 0)),),
        )

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "NaivePersistenceBaseline":
        """RT-F14: reconstruct from the artifact."""
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        params = dict(artifact.parameters)
        model = cls(
            model_id=artifact.model_id,
            model_version=artifact.model_version,
        )
        model._last = 1 if params["last_outcome"] >= 0.5 else 0
        return model

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash


class RandomClassifierBaseline:
    """The no-skill floor: p = 0.5 (§9 'random classifier where appropriate')."""

    model_family = "baseline-random"
    model_id = "RANDOM"
    model_version = "1"

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "RandomClassifierBaseline":
        if not y:
            raise PredictionModelError("training data must be non-empty")
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        return 0.5

    def artifact(self) -> ModelArtifact:
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=(),
            parameters=(("probability", 0.5),),
        )

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "RandomClassifierBaseline":
        """RT-F14: reconstruct (stateless floor model)."""
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        return cls()

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash


class RegimeConditionalBaseline:
    """Per-regime base rates with Laplace smoothing (§9 regime baseline).

    Falls back to the global rate for unseen regimes at prediction time
    — never fabricates a regime-specific number it has not seen.
    """

    model_family = "baseline-regime-conditional"

    def __init__(self, model_id: str = "REGIME-RATE", model_version: str = "1") -> None:
        self.model_id = model_id
        self.model_version = model_version
        self._rates: dict[str, float] = {}
        self._global_rate: Optional[float] = None

    def fit(
        self,
        X: Sequence[Sequence[float]],
        y: Sequence[int],
        regimes: Optional[Sequence[str]] = None,
    ) -> "RegimeConditionalBaseline":
        if not y:
            raise PredictionModelError("training data must be non-empty")
        if regimes is not None and len(regimes) != len(y):
            raise PredictionModelError("regimes must align 1:1 with y")
        pos = sum(1 for v in y if v)
        self._global_rate = (pos + 1) / (len(y) + 2)
        self._rates = {}
        if regimes is not None:
            buckets: dict[str, list[int]] = {}
            for regime, outcome in zip(regimes, y):
                buckets.setdefault(regime, []).append(1 if outcome else 0)
            for regime, values in sorted(buckets.items()):
                r_pos = sum(values)
                self._rates[regime] = (r_pos + 1) / (len(values) + 2)
        return self

    def predict_proba(self, x: Sequence[float], regime: Optional[str] = None) -> float:
        if self._global_rate is None:
            raise PredictionModelError("model not fitted")
        if regime is None:
            return self._global_rate
        return self._rates.get(regime, self._global_rate)

    def artifact(self) -> ModelArtifact:
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=(),
            parameters=tuple(
                (f"rate[{regime}]", rate)
                for regime, rate in sorted(self._rates.items())
            ) + (("global_rate", float(self._global_rate or 0.0)),),
        )

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "RegimeConditionalBaseline":
        """RT-F14: reconstruct per-regime rates from the artifact."""
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        params = dict(artifact.parameters)
        model = cls(
            model_id=artifact.model_id,
            model_version=artifact.model_version,
        )
        model._global_rate = float(params.get("global_rate", 0.5))
        model._rates = {
            key[len("rate["):-1]: float(value)
            for key, value in params.items()
            if key.startswith("rate[") and key.endswith("]")
        }
        return model

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash


class LogisticCrashModel:
    """Deterministic logistic model (GD, fixed iterations, l2 penalty).

    Standardization statistics are computed from the TRAINING data only
    and are part of the artifact hash (§13 — learned transformations
    fitted only on permitted data). Feature-schema mismatches fail
    closed at predict time (§27 FEATURE_SCHEMA_MISMATCH root cause).
    """

    model_family = "logistic-gd"

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        model_id: str = "LOGISTIC-1",
        model_version: str = "1",
        learning_rate: float = 0.5,
        iterations: int = 300,
        l2: float = 0.0,
    ) -> None:
        if not feature_names:
            raise PredictionModelError("feature_names must be non-empty")
        if learning_rate <= 0 or iterations < 1 or l2 < 0:
            raise PredictionModelError("invalid hyperparameters")
        self.feature_names = tuple(feature_names)
        self.model_id = model_id
        self.model_version = model_version
        self.learning_rate = float(learning_rate)
        self.iterations = int(iterations)
        self.l2 = float(l2)
        self._weights: Optional[list[float]] = None
        self._means: Tuple[float, ...] = ()
        self._stds: Tuple[float, ...] = ()

    def _standardize_fit(self, X: Sequence[Sequence[float]]) -> list[list[float]]:
        n_features = len(self.feature_names)
        means: list[float] = []
        stds: list[float] = []
        for j in range(n_features):
            column = [float(row[j]) for row in X]
            mean = math.fsum(column) / len(column)
            var = math.fsum((v - mean) ** 2 for v in column) / len(column)
            means.append(mean)
            stds.append(math.sqrt(var))
        self._means = tuple(means)
        self._stds = tuple(stds)
        return [
            [
                (float(row[j]) - means[j]) / stds[j] if stds[j] > 0 else 0.0
                for j in range(n_features)
            ]
            for row in X
        ]

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "LogisticCrashModel":
        if not X or not y or len(X) != len(y):
            raise PredictionModelError("X and y must be non-empty and aligned")
        n_features = len(self.feature_names)
        for row in X:
            if len(row) != n_features:
                raise PredictionModelError(
                    f"feature schema mismatch: expected {n_features} "
                    f"features, got {len(row)}"
                )
        Xs = self._standardize_fit(X)
        n = len(y)
        d = n_features
        weights = [0.0] * (d + 1)
        for _ in range(self.iterations):
            grad = [0.0] * (d + 1)
            for i in range(n):
                z = weights[0] + math.fsum(
                    weights[k + 1] * Xs[i][k] for k in range(d)
                )
                err = _sigmoid(z) - (1.0 if y[i] else 0.0)
                grad[0] += err
                for k in range(d):
                    grad[k + 1] += err * Xs[i][k]
            weights[0] -= self.learning_rate * grad[0] / n
            for k in range(d):
                weights[k + 1] -= self.learning_rate * (
                    grad[k + 1] / n + self.l2 * weights[k + 1]
                )
        self._weights = weights
        return self

    def predict_proba(self, x: Sequence[float]) -> float:
        if self._weights is None:
            raise PredictionModelError("model not fitted")
        if len(x) != len(self.feature_names):
            raise PredictionModelError(
                f"feature schema mismatch: expected {len(self.feature_names)} "
                f"features, got {len(x)}"
            )
        d = len(self.feature_names)
        z = self._weights[0] + math.fsum(
            self._weights[k + 1]
            * ((float(x[k]) - self._means[k]) / self._stds[k]
               if self._stds[k] > 0 else 0.0)
            for k in range(d)
        )
        return _sigmoid(z)

    def artifact(self) -> ModelArtifact:
        return ModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_names=self.feature_names,
            parameters=(
                ("learning_rate", self.learning_rate),
                ("iterations", float(self.iterations)),
                ("l2", self.l2),
                *(
                    (f"w[{name}]", value)
                    for name, value in zip(self.feature_names, (self._weights or [0.0])[1:])
                ),
                ("w[intercept]", (self._weights or [0.0])[0]),
                *(
                    (f"mean[{name}]", value)
                    for name, value in zip(self.feature_names, self._means)
                ),
                *(
                    (f"std[{name}]", value)
                    for name, value in zip(self.feature_names, self._stds)
                ),
            ),
        )

    @property
    def model_hash(self) -> str:
        return self.artifact().model_hash

    @classmethod
    def from_artifact(cls, artifact: ModelArtifact) -> "LogisticCrashModel":
        """RT-F14: reconstruct the fitted model from its artifact.

        Weights, intercept, and the TRAINING-fitted standardization
        statistics (means/stds) all round-trip through the artifact
        parameters — a restart can never leave the runtime unable to
        reconstruct its approved model.
        """
        if artifact.model_family != cls.model_family:
            raise PredictionModelError(
                f"artifact family {artifact.model_family!r} != {cls.model_family!r}"
            )
        if not artifact.feature_names:
            raise PredictionModelError(
                "logistic artifact requires feature_names"
            )
        params = dict(artifact.parameters)
        names = list(artifact.feature_names)
        model = cls(
            feature_names=names,
            model_id=artifact.model_id,
            model_version=artifact.model_version,
            learning_rate=params.get("learning_rate", 0.5),
            iterations=int(params.get("iterations", 300)),
            l2=params.get("l2", 0.0),
        )
        weights = [params.get("w[intercept]", 0.0)] + [
            params.get(f"w[{name}]", 0.0) for name in names
        ]
        model._weights = weights
        model._means = tuple(
            params.get(f"mean[{name}]", 0.0) for name in names
        )
        model._stds = tuple(
            params.get(f"std[{name}]", 1.0) for name in names
        )
        return model


def reconstruct_model(artifact: ModelArtifact):
    """RT-F14 dispatcher: rebuild ANY known prediction model family
    from its artifact. Raises for unknown families — never guesses."""
    family = artifact.model_family
    dispatch = {
        "baseline-base-rate": BaseRateBaseline,
        "baseline-rolling-base-rate": RollingBaseRateBaseline,
        "baseline-naive-persistence": NaivePersistenceBaseline,
        "baseline-random": RandomClassifierBaseline,
        "baseline-regime-conditional": RegimeConditionalBaseline,
        "logistic-gd": LogisticCrashModel,
    }
    if family not in dispatch:
        raise PredictionModelError(
            f"no reconstruction path registered for model family "
            f"{family!r} (RT-F14: unknown families fail explicitly)"
        )
    return dispatch[family].from_artifact(artifact)


class ModelJustification(BaseModel):
    """Baseline-vs-model justification verdict (§9).

    MODEL_NOT_JUSTIFIED is a recorded verdict, not an exception: the
    model exists but must not be promoted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    baseline_id: str
    metric: str
    baseline_value: float
    model_value: float
    improvement: float
    min_improvement: float
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    status: str

    @property
    def justified(self) -> bool:
        return self.status == "JUSTIFIED"


def bootstrap_improvement_ci(
    model_losses: Sequence[float],
    baseline_losses: Sequence[float],
    *,
    seed: int = 0,
    n_resamples: int = 200,
) -> Tuple[float, float]:
    """Deterministic bootstrap CI on absolute error reduction (§9).

    Resamples paired loss differences with a seeded Mersenne Twister —
    reproducible for a declared seed (T-PREV-029 support).
    """
    if len(model_losses) != len(baseline_losses) or not model_losses:
        raise PredictionModelError("losses must be aligned and non-empty")
    import random

    diffs = [b - m for m, b in zip(model_losses, baseline_losses)]
    rng = random.Random(seed)
    means: list[float] = []
    n = len(diffs)
    for _ in range(n_resamples):
        sample = [diffs[rng.randrange(n)] for _ in range(n)]
        means.append(math.fsum(sample) / n)
    means.sort()
    def _quantile(sorted_values: Sequence[float], q: float) -> float:
        pos = q * (len(sorted_values) - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        frac = pos - lo
        return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac
    return _quantile(means, 0.05), _quantile(means, 0.95)


def justify_model(
    *,
    model_id: str,
    baseline_id: str,
    model_metrics: dict,
    baseline_metrics: dict,
    metric: str = "brier",
    min_improvement: float = 0.05,
    model_losses: Optional[Sequence[float]] = None,
    baseline_losses: Optional[Sequence[float]] = None,
    seed: int = 0,
) -> ModelJustification:
    """Baseline-first justification gate (§9, T-PREV justification).

    ``improvement`` is the RELATIVE error reduction for lower-is-better
    metrics: (baseline - model) / baseline. The model is JUSTIFIED only
    when improvement >= min_improvement AND (when paired losses are
    provided) the bootstrap CI on absolute reduction excludes zero.
    """
    if metric not in model_metrics or metric not in baseline_metrics:
        raise PredictionModelError(
            f"metric {metric!r} missing from one of the metric dicts"
        )
    baseline_value = float(baseline_metrics[metric])
    model_value = float(model_metrics[metric])
    if baseline_value <= 0:
        raise PredictionModelError(
            "baseline metric must be positive to compute relative improvement"
        )
    improvement = (baseline_value - model_value) / baseline_value
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    if model_losses is not None and baseline_losses is not None:
        ci_low, ci_high = bootstrap_improvement_ci(
            model_losses, baseline_losses, seed=seed
        )
    justified = improvement >= min_improvement and (
        ci_low is None or ci_low > 0.0
    )
    return ModelJustification(
        model_id=model_id,
        baseline_id=baseline_id,
        metric=metric,
        baseline_value=baseline_value,
        model_value=model_value,
        improvement=improvement,
        min_improvement=min_improvement,
        ci_low=ci_low,
        ci_high=ci_high,
        status=(
            "JUSTIFIED" if justified
            else InsufficiencyState.MODEL_NOT_JUSTIFIED.value
        ),
    )


__all__ = [
    "PredictionModelError",
    "ModelArtifact",
    "BaseRateBaseline",
    "RollingBaseRateBaseline",
    "NaivePersistenceBaseline",
    "RandomClassifierBaseline",
    "RegimeConditionalBaseline",
    "LogisticCrashModel",
    "ModelJustification",
    "bootstrap_improvement_ci",
    "justify_model",
]
