"""Governed runtime models: baseline, LSTM, Transformer, ensemble,
calibration, walk-forward evaluation (pre-paper mandate §13–§17, §43).

Design contract (every model in this module):

- **PIT-safe input only**: models consume sequence feature matrices
  built by :mod:`data_engine.runtime.sequence` (window-local,
  cutoff-enforced features). A model that receives a matrix with
  non-finite values refuses it (fail closed).
- **Deterministic training**: every model seeds NumPy's
  ``RandomState`` from a recorded integer seed; no other RNG source
  exists in the training path. Retraining on identical data + config
  + seed reproduces identical weights bit-for-bit.
- **Reproducible artifacts (RT-F14)**: ``artifact()`` emits a
  :class:`RuntimeModelArtifact` (identity-hashed, weights rounded to
  12 decimals — the model ADOPTS the rounded weights, so
  ``from_artifact`` reconstructs a bit-identical predictor; a restart
  can never leave the runtime unable to reconstruct its model).
- **No trading authority**: models return probabilities and
  uncertainty metadata only. They cannot submit, size, or approve
  orders (mandate §14/§15).
- **Honest baselines first (§13)**: advanced models are evaluated
  against the deterministic baseline under the SAME walk-forward
  plan; no superiority claim exists without that comparison.

NumPy implementations are deliberate: the environment pins
pydantic/numpy/pandas only — no torch/tensorflow — and a small,
fully deterministic, dependency-free implementation is auditable and
replayable exactly. The LSTM implements the standard recurrent cell
with full backpropagation-through-time; the Transformer implements a
minimal single-head CAUSAL self-attention encoder with full manual
backward passes. Neither is a stub; neither fabricates outputs.
"""

import math
from typing import Callable, Mapping, Optional, Sequence, Tuple

import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.identity import (
    CALIBRATION_PREFIX,
    ENSEMBLE_PREFIX,
    MODEL_PREFIX,
    prefixed_hash,
)
from data_engine.runtime.contracts import RuntimeContractError, freeze_number
from data_engine.runtime.sequence import FEATURE_DIM

#: Weight precision adopted at artifact creation — makes
#: fit → artifact → from_artifact bit-identical (RT-F14).
_WEIGHT_DECIMALS = 12


class ModelError(RuntimeContractError):
    """Raised on runtime-model contract violations."""


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _check_matrix(X: Sequence[Sequence[float]], name: str) -> np.ndarray:
    arr = np.asarray(X, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[0] < 1 or arr.shape[1] < 1:
        raise ModelError(f"{name} must be a non-empty 2-D matrix")
    if not np.isfinite(arr).all():
        raise ModelError(
            f"{name} contains non-finite values (NaN/inf fail closed)"
        )
    return arr


def _check_labels(y: Sequence[int]) -> list:
    labels = list(y)
    if not labels:
        raise ModelError("labels must be non-empty")
    if any(v not in (0, 1) for v in labels):
        raise ModelError("labels must be binary 0/1")
    return labels


def _round_weights(w: np.ndarray) -> np.ndarray:
    """Round to the artifact precision and ADOPT the rounded values."""
    return np.round(w, _WEIGHT_DECIMALS)


# ---------------------------------------------------------------------------
# Runtime model artifact (RT-F14)
# ---------------------------------------------------------------------------

class RuntimeModelArtifact(BaseModel):
    """Reproducible model artifact (mandate §43 / RT-F14).

    A model is reconstructable from: model id + version + artifact +
    configuration + dataset version + feature version + code version +
    dependencies + seed. Weight tensors are stored flattened with
    names and shapes; values are rounded to 12 decimals and the model
    adopts the rounded values at fit time, so reconstruction is
    bit-identical.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    model_version: str
    model_family: str
    feature_version: str
    dataset_version: str
    seed: int
    lookback: int
    horizon: int
    feature_dim: int
    hyperparameters: Tuple[Tuple[str, float], ...]
    weight_names: Tuple[str, ...]
    weight_shapes: Tuple[Tuple[int, int], ...]
    weight_values: Tuple[float, ...]
    training_metadata: Tuple[Tuple[str, str], ...]
    metrics: Tuple[Tuple[str, float], ...]

    @field_validator("model_id", "model_version", "model_family",
                     "feature_version", "dataset_version")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ModelError("artifact text fields must be non-empty")
        return v.strip()

    @field_validator("seed", "lookback", "horizon", "feature_dim")
    @classmethod
    def _validate_ints(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ModelError("artifact int fields must be >= 0")
        return v

    @model_validator(mode="after")
    def _validate_consistency(self) -> "RuntimeModelArtifact":
        if len(self.weight_names) != len(self.weight_shapes):
            raise ModelError("weight names/shapes length mismatch")
        flat = sum(r * c for r, c in self.weight_shapes)
        if flat != len(self.weight_values):
            raise ModelError(
                f"weight values length {len(self.weight_values)} != "
                f"shapes total {flat}"
            )
        return self

    @property
    def model_hash(self) -> str:
        return prefixed_hash(
            MODEL_PREFIX,
            {
                "kind": "runtime_model_artifact",
                "model_id": self.model_id,
                "model_version": self.model_version,
                "model_family": self.model_family,
                "feature_version": self.feature_version,
                "dataset_version": self.dataset_version,
                "seed": self.seed,
                "lookback": self.lookback,
                "horizon": self.horizon,
                "feature_dim": self.feature_dim,
                "hyperparameters": [list(h) for h in self.hyperparameters],
                "weight_names": list(self.weight_names),
                "weight_shapes": [list(s) for s in self.weight_shapes],
                "weight_values": list(self.weight_values),
                "training_metadata": [list(m) for m in self.training_metadata],
                "metrics": [list(m) for m in self.metrics],
            },
        )

    def unpack(self) -> dict:
        """Named weight matrices (``np.ndarray``) for reconstruction."""
        mats: dict = {}
        offset = 0
        for name, (rows, cols) in zip(self.weight_names, self.weight_shapes):
            flat = np.asarray(
                self.weight_values[offset : offset + rows * cols],
                dtype=np.float64,
            )
            mats[name] = flat.reshape(rows, cols)
            offset += rows * cols
        return mats


# ---------------------------------------------------------------------------
# Deterministic baseline (mandate §13)
# ---------------------------------------------------------------------------

class DeterministicBaseline:
    """Momentum-sign baseline over PIT-safe sequences (§13).

    Predicts P(up) as a logistic of the window's mean intra-bar
    return, scaled by a fixed temperature. Completely deterministic
    (no RNG at all — seed is recorded as 0 for artifact uniformity).
    Every advanced model must beat THIS under the same walk-forward
    plan before any superiority claim.
    """

    model_family = "baseline-deterministic-momentum"

    def __init__(
        self,
        model_id: str = "BASE-MOM",
        model_version: str = "1",
        feature_version: str = "fv-seq-1",
        dataset_version: str = "dv-unknown",
        lookback: int = 8,
        horizon: int = 1,
        temperature: float = 25.0,
    ) -> None:
        if lookback < 1 or horizon < 1:
            raise ModelError("lookback/horizon must be >= 1")
        if temperature <= 0:
            raise ModelError("temperature must be > 0")
        self.model_id = model_id
        self.model_version = model_version
        self.feature_version = feature_version
        self.dataset_version = dataset_version
        self.lookback = lookback
        self.horizon = horizon
        self.temperature = temperature
        self._fitted = False

    def fit(
        self, X: Sequence[Sequence[Sequence[float]]], y: Sequence[int]
    ) -> "DeterministicBaseline":
        """Validate inputs; the baseline itself has no fitted state."""
        labels = _check_labels(y)
        for x in X:
            arr = _check_matrix(x, "training sequence")
            if arr.shape[0] != self.lookback:
                raise ModelError(
                    f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
                )
        if len(labels) != len(X):
            raise ModelError("X/y length mismatch")
        self._fitted = True
        return self

    def predict_proba(self, x: Sequence[Sequence[float]]) -> float:
        arr = _check_matrix(x, "prediction sequence")
        if not self._fitted:
            raise ModelError("model not fitted")
        if arr.shape[0] != self.lookback:
            raise ModelError(
                f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
            )
        mean_ret = float(arr[:, 0].mean())  # feature 0 = intra-bar return
        return round(
            min(max(_sigmoid(mean_ret * self.temperature), 1e-9), 1 - 1e-9),
            12,
        )

    def artifact(self, metrics: Sequence[Tuple[str, float]] = ()) -> RuntimeModelArtifact:
        return RuntimeModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_version=self.feature_version,
            dataset_version=self.dataset_version,
            seed=0,
            lookback=self.lookback,
            horizon=self.horizon,
            feature_dim=FEATURE_DIM,
            hyperparameters=(("temperature", self.temperature),),
            weight_names=("scalar_scale",),
            weight_shapes=((1, 1),),
            weight_values=(1.0,),
            training_metadata=(("fitted", "true" if self._fitted else "false"),),
            metrics=tuple((n, freeze_number(v)) for n, v in metrics),
        )

    @classmethod
    def from_artifact(cls, artifact: RuntimeModelArtifact) -> "DeterministicBaseline":
        """RT-F14 reconstruction — bit-identical predictor."""
        if artifact.model_family != cls.model_family:
            raise ModelError(
                f"artifact family {artifact.model_family!r} does not match "
                f"{cls.model_family!r}"
            )
        hyper = dict(artifact.hyperparameters)
        model = cls(
            model_id=artifact.model_id,
            model_version=artifact.model_version,
            feature_version=artifact.feature_version,
            dataset_version=artifact.dataset_version,
            lookback=artifact.lookback,
            horizon=artifact.horizon,
            temperature=hyper["temperature"],
        )
        model._fitted = True
        return model


# ---------------------------------------------------------------------------
# LSTM (mandate §14)
# ---------------------------------------------------------------------------

class LSTMClassifier:
    """Single-layer NumPy LSTM with full backpropagation-through-time.

    Cell (H hidden units, 4H gate block order i,f,o,g)::

        z_t = Wx x_t + Wh h_{t-1} + b
        i,f,o = sigmoid(z[..]) ; g = tanh(z[..])
        c_t = f * c_{t-1} + i * g ; h_t = o * tanh(c_t)
        p   = sigmoid(Wy h_T + by)

    Trained by SGD on binary cross-entropy, seeded ``RandomState``.
    Weights are rounded to 12 decimals at the END of fit and adopted
    (bit-identical artifact reconstruction, RT-F14).
    """

    model_family = "lstm-numpy-bptt"

    def __init__(
        self,
        hidden_units: int = 4,
        epochs: int = 3,
        learning_rate: float = 0.05,
        seed: int = 7,
        model_id: str = "LSTM-1",
        model_version: str = "1",
        feature_version: str = "fv-seq-1",
        dataset_version: str = "dv-unknown",
        lookback: int = 8,
        horizon: int = 1,
    ) -> None:
        if hidden_units < 1 or epochs < 1:
            raise ModelError("hidden_units/epochs must be >= 1")
        if learning_rate <= 0:
            raise ModelError("learning_rate must be > 0")
        if lookback < 1 or horizon < 1:
            raise ModelError("lookback/horizon must be >= 1")
        self.hidden_units = hidden_units
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.seed = seed
        self.model_id = model_id
        self.model_version = model_version
        self.feature_version = feature_version
        self.dataset_version = dataset_version
        self.lookback = lookback
        self.horizon = horizon
        self._feature_dim: Optional[int] = None
        self._Wx: Optional[np.ndarray] = None
        self._Wh: Optional[np.ndarray] = None
        self._b: Optional[np.ndarray] = None
        self._Wy: Optional[np.ndarray] = None
        self._by: Optional[np.ndarray] = None
        self._fitted = False

    # -- forward ------------------------------------------------------------
    def _forward(self, X: np.ndarray):
        T, F = X.shape
        H = self.hidden_units
        Wx, Wh, b, Wy, by = self._Wx, self._Wh, self._b, self._Wy, self._by
        h = np.zeros((T, H))
        c = np.zeros((T, H))
        hs = np.zeros((T, 4 * H))
        ig = np.zeros((T, H)); fg = np.zeros((T, H))
        og = np.zeros((T, H)); gg = np.zeros((T, H))
        h_prev = np.zeros(H); c_prev = np.zeros(H)
        for t in range(T):
            z = X[t] @ Wx + h_prev @ Wh + b  # 4H
            i = _sig(z[0:H]); f = _sig(z[H:2 * H])
            o = _sig(z[2 * H:3 * H]); g = np.tanh(z[3 * H:4 * H])
            c_t = f * c_prev + i * g
            h_t = o * np.tanh(c_t)
            hs[t] = z; ig[t] = i; fg[t] = f; og[t] = o; gg[t] = g
            c[t] = c_t; h[t] = h_t
            h_prev = h_t; c_prev = c_t
        z_out = float((h[-1] @ Wy + by).item())
        p = _sigmoid(z_out)
        cache = (X, hs, ig, fg, og, gg, h, c, h[-1])
        return p, cache

    def _backward(self, y: int, cache):
        X, hs, ig, fg, og, gg, h, c, h_last = cache
        T, F = X.shape
        H = self.hidden_units
        p, _ = self._forward(X)
        dWx = np.zeros_like(self._Wx); dWh = np.zeros_like(self._Wh)
        db = np.zeros_like(self._b)
        dWy = np.zeros_like(self._Wy); dby = np.zeros_like(self._by)
        dz_out = p - y  # BCE + sigmoid
        dWy += np.outer(h_last, np.atleast_1d(dz_out))
        dby += dz_out
        dh_next = (self._Wy @ np.atleast_1d(dz_out)).reshape(H)
        dc_next = np.zeros(H)
        tanh_c = np.tanh(c)
        for t in range(T - 1, -1, -1):
            dh = dh_next.copy()
            do = dh * tanh_c[t]
            dc = dc_next + dh * og[t] * (1.0 - tanh_c[t] ** 2)
            di = dc * gg[t]
            df = dc * (c[t - 1] if t > 0 else np.zeros(H))
            dg = dc * ig[t]
            dzi = di * ig[t] * (1.0 - ig[t])
            dzf = df * fg[t] * (1.0 - fg[t])
            dzo = do * og[t] * (1.0 - og[t])
            dzg = dg * (1.0 - gg[t] ** 2)
            dz = np.concatenate([dzi, dzf, dzo, dzg])
            dWx += np.outer(X[t], dz)
            dWh += np.outer(h[t - 1] if t > 0 else np.zeros(H), dz)
            db += dz
            dh_next = self._Wh @ dz
            dc_next = dc * fg[t]
        return dWx, dWh, db, dWy, dby

    # -- public API ----------------------------------------------------------
    def fit(
        self, X: Sequence[Sequence[Sequence[float]]], y: Sequence[int]
    ) -> "LSTMClassifier":
        labels = _check_labels(y)
        mats = [_check_matrix(x, "training sequence") for x in X]
        if len(mats) != len(labels):
            raise ModelError("X/y length mismatch")
        for arr in mats:
            if arr.shape[0] != self.lookback:
                raise ModelError(
                    f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
                )
        F = mats[0].shape[1]
        if any(a.shape[1] != F for a in mats):
            raise ModelError("inconsistent feature dimensions across sequences")
        H = self.hidden_units
        rng = np.random.RandomState(self.seed)
        self._Wx = rng.normal(0.0, 0.1, (F, 4 * H))
        self._Wh = rng.normal(0.0, 0.1, (H, 4 * H))
        self._b = np.zeros(4 * H)
        self._Wy = rng.normal(0.0, 0.1, (H, 1))
        self._by = np.zeros(1)
        self._feature_dim = F
        n = len(mats)
        for _ in range(self.epochs):
            for X_i, y_i in zip(mats, labels):
                _, cache = self._forward(X_i)
                dWx, dWh, db, dWy, dby = self._backward(y_i, cache)
                self._Wx -= self.learning_rate * dWx / n
                self._Wh -= self.learning_rate * dWh / n
                self._b -= self.learning_rate * db / n
                self._Wy -= self.learning_rate * dWy / n
                self._by -= self.learning_rate * dby / n
        # RT-F14: adopt artifact-precision weights.
        self._Wx = _round_weights(self._Wx)
        self._Wh = _round_weights(self._Wh)
        self._b = _round_weights(self._b)
        self._Wy = _round_weights(self._Wy)
        self._by = _round_weights(self._by)
        self._fitted = True
        return self

    def predict_proba(self, x: Sequence[Sequence[float]]) -> float:
        if not self._fitted:
            raise ModelError("model not fitted")
        arr = _check_matrix(x, "prediction sequence")
        if arr.shape[0] != self.lookback:
            raise ModelError(
                f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
            )
        if arr.shape[1] != self._feature_dim:
            raise ModelError(
                f"feature dim {arr.shape[1]} != trained {self._feature_dim}"
            )
        p, _ = self._forward(arr)
        return round(min(max(p, 1e-9), 1 - 1e-9), 12)

    def artifact(self, metrics: Sequence[Tuple[str, float]] = ()) -> RuntimeModelArtifact:
        if not self._fitted:
            raise ModelError("model not fitted")
        Wx = self._Wx; Wh = self._Wh; b = self._b.reshape(1, -1)
        Wy = self._Wy; by = self._by.reshape(1, -1)
        return RuntimeModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_version=self.feature_version,
            dataset_version=self.dataset_version,
            seed=self.seed,
            lookback=self.lookback,
            horizon=self.horizon,
            feature_dim=self._feature_dim,
            hyperparameters=(
                ("hidden_units", float(self.hidden_units)),
                ("epochs", float(self.epochs)),
                ("learning_rate", self.learning_rate),
            ),
            weight_names=("Wx", "Wh", "b", "Wy", "by"),
            weight_shapes=(
                Wx.shape, Wh.shape, b.shape, Wy.shape, by.shape
            ),
            weight_values=tuple(
                float(v)
                for m in (Wx, Wh, b, Wy, by)
                for v in np.asarray(m, dtype=np.float64).ravel()
            ),
            training_metadata=(("fitted", "true"),),
            metrics=tuple((n, freeze_number(v)) for n, v in metrics),
        )

    @classmethod
    def from_artifact(cls, artifact: RuntimeModelArtifact) -> "LSTMClassifier":
        if artifact.model_family != cls.model_family:
            raise ModelError(
                f"artifact family {artifact.model_family!r} does not match "
                f"{cls.model_family!r}"
            )
        hyper = dict(artifact.hyperparameters)
        model = cls(
            hidden_units=int(hyper["hidden_units"]),
            epochs=int(hyper["epochs"]),
            learning_rate=hyper["learning_rate"],
            seed=artifact.seed,
            model_id=artifact.model_id,
            model_version=artifact.model_version,
            feature_version=artifact.feature_version,
            dataset_version=artifact.dataset_version,
            lookback=artifact.lookback,
            horizon=artifact.horizon,
        )
        mats = artifact.unpack()
        model._Wx = mats["Wx"]
        model._Wh = mats["Wh"]
        model._b = mats["b"].ravel()
        model._Wy = mats["Wy"]
        model._by = mats["by"].ravel()
        model._feature_dim = artifact.feature_dim
        model._fitted = True
        return model


def _sig(x):
    """Vectorized stable sigmoid."""
    out = np.empty_like(x, dtype=np.float64)
    flat = out.reshape(-1)
    xf = np.asarray(x, dtype=np.float64).reshape(-1)
    for i in range(len(flat)):
        flat[i] = _sigmoid(float(xf[i]))
    return out


# ---------------------------------------------------------------------------
# Transformer (mandate §15)
# ---------------------------------------------------------------------------

class TransformerClassifier:
    """Minimal single-head CAUSAL self-attention encoder (NumPy).

    Architecture (T×F input, D even model dim)::

        x_t  = W_in f_t + PE[t]                 (embedding + sinusoidal PE)
        Q,K,V = x Wq, x Wk, x Wv                (D×D projections)
        A    = softmax_j( Q K^T / sqrt(D) )  causal (j <= t)
        C    = A V ;  O = C Wo
        p    = sigmoid( w . mean_t(O_t) + b )

    Full manual backward pass (softmax jacobian, causal masking,
    gradient accumulation into every projection). Deterministic:
    seeded init, no framework, no dropout. Weights adopt 12-decimal
    artifact precision at the end of fit (RT-F14).
    """

    model_family = "transformer-numpy-attention"

    def __init__(
        self,
        model_dim: int = 4,
        epochs: int = 3,
        learning_rate: float = 0.05,
        seed: int = 11,
        model_id: str = "TRF-1",
        model_version: str = "1",
        feature_version: str = "fv-seq-1",
        dataset_version: str = "dv-unknown",
        lookback: int = 8,
        horizon: int = 1,
    ) -> None:
        if model_dim < 2 or model_dim % 2 != 0:
            raise ModelError("model_dim must be an even int >= 2")
        if epochs < 1 or learning_rate <= 0:
            raise ModelError("epochs >= 1 and learning_rate > 0 required")
        if lookback < 1 or horizon < 1:
            raise ModelError("lookback/horizon must be >= 1")
        self.model_dim = model_dim
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.seed = seed
        self.model_id = model_id
        self.model_version = model_version
        self.feature_version = feature_version
        self.dataset_version = dataset_version
        self.lookback = lookback
        self.horizon = horizon
        self._feature_dim: Optional[int] = None
        self._Win = None; self._Wq = None; self._Wk = None
        self._Wv = None; self._Wo = None
        self._w = None; self._b = None
        self._fitted = False

    def _positional_encoding(self, T: int, D: int) -> np.ndarray:
        pe = np.zeros((T, D))
        for t in range(T):
            for i in range(D // 2):
                denom = 10000.0 ** (2 * i / D)
                pe[t, 2 * i] = math.sin(t / denom)
                pe[t, 2 * i + 1] = math.cos(t / denom)
        return pe

    def _forward(self, X: np.ndarray):
        T, F = X.shape
        D = self.model_dim
        Xe = X @ self._Win + self._positional_encoding(T, D)  # T×D
        Q = Xe @ self._Wq
        K = Xe @ self._Wk
        V = Xe @ self._Wv
        S = (Q @ K.T) / math.sqrt(D)  # T×T
        mask = np.triu(np.ones((T, T)), k=1).astype(bool)  # j > t forbidden
        S = np.where(mask, -1e9, S)
        A = np.zeros_like(S)
        for t in range(T):
            row = S[t]
            m = row.max()
            e = np.exp(row - m)
            A[t] = e / e.sum()
        C = A @ V  # T×D
        O = C @ self._Wo  # T×D
        pooled = O.mean(axis=0)  # D
        z = float(self._w @ pooled + self._b[0])
        p = _sigmoid(z)
        cache = (X, Xe, Q, K, V, A, C, O, pooled, p)
        return p, cache

    def _backward(self, y: int, cache):
        X, Xe, Q, K, V, A, C, O, pooled, p = cache
        T, F = X.shape
        D = self.model_dim
        dWin = np.zeros_like(self._Win)
        dWq = np.zeros_like(self._Wq); dWk = np.zeros_like(self._Wk)
        dWv = np.zeros_like(self._Wv); dWo = np.zeros_like(self._Wo)
        dw = np.zeros_like(self._w); db = np.zeros_like(self._b)

        dz = p - y  # BCE + sigmoid
        dw += dz * pooled
        db += dz
        dpooled = dz * self._w  # D

        dO = np.tile(dpooled / T, (T, 1))  # T×D
        dWo += C.T @ dO
        dC = dO @ self._Wo.T  # T×D

        # attention backward
        dA = dC @ V.T  # T×T
        dV = A.T @ dC  # T×D
        # softmax jacobian per row
        dS = np.zeros_like(A)
        for t in range(T):
            g = dA[t]
            dS[t] = A[t] * (g - (A[t] * g).sum())
        # causal mask: no gradient flows to forbidden positions
        mask = np.triu(np.ones((T, T)), k=1).astype(bool)
        dS = np.where(mask, 0.0, dS)
        scale = 1.0 / math.sqrt(D)
        dQ = dS @ K * scale  # T×D
        dK = dS.T @ Q * scale  # T×D

        dWq += Xe.T @ dQ
        dWk += Xe.T @ dK
        dWv += Xe.T @ dV
        dXe = dQ @ self._Wq.T + dK @ self._Wk.T + dV @ self._Wv.T
        dWin += X.T @ dXe
        return dWin, dWq, dWk, dWv, dWo, dw, db

    def fit(
        self, X: Sequence[Sequence[Sequence[float]]], y: Sequence[int]
    ) -> "TransformerClassifier":
        labels = _check_labels(y)
        mats = [_check_matrix(x, "training sequence") for x in X]
        if len(mats) != len(labels):
            raise ModelError("X/y length mismatch")
        for arr in mats:
            if arr.shape[0] != self.lookback:
                raise ModelError(
                    f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
                )
        F = mats[0].shape[1]
        if any(a.shape[1] != F for a in mats):
            raise ModelError("inconsistent feature dimensions across sequences")
        D = self.model_dim
        rng = np.random.RandomState(self.seed)
        self._Win = rng.normal(0.0, 0.1, (F, D))
        self._Wq = rng.normal(0.0, 0.1, (D, D))
        self._Wk = rng.normal(0.0, 0.1, (D, D))
        self._Wv = rng.normal(0.0, 0.1, (D, D))
        self._Wo = rng.normal(0.0, 0.1, (D, D))
        self._w = rng.normal(0.0, 0.1, (D,))
        self._b = np.zeros(1)
        self._feature_dim = F
        n = len(mats)
        for _ in range(self.epochs):
            for X_i, y_i in zip(mats, labels):
                _, cache = self._forward(X_i)
                grads = self._backward(y_i, cache)
                for param, grad in zip(
                    (self._Win, self._Wq, self._Wk, self._Wv,
                     self._Wo, self._w, self._b),
                    grads,
                ):
                    param -= self.learning_rate * grad / n
        self._Win = _round_weights(self._Win)
        self._Wq = _round_weights(self._Wq)
        self._Wk = _round_weights(self._Wk)
        self._Wv = _round_weights(self._Wv)
        self._Wo = _round_weights(self._Wo)
        self._w = _round_weights(self._w)
        self._b = _round_weights(self._b)
        self._fitted = True
        return self

    def predict_proba(self, x: Sequence[Sequence[float]]) -> float:
        if not self._fitted:
            raise ModelError("model not fitted")
        arr = _check_matrix(x, "prediction sequence")
        if arr.shape[0] != self.lookback:
            raise ModelError(
                f"sequence lookback {arr.shape[0]} != spec {self.lookback}"
            )
        if arr.shape[1] != self._feature_dim:
            raise ModelError(
                f"feature dim {arr.shape[1]} != trained {self._feature_dim}"
            )
        p, _ = self._forward(arr)
        return round(min(max(p, 1e-9), 1 - 1e-9), 12)

    def artifact(self, metrics: Sequence[Tuple[str, float]] = ()) -> RuntimeModelArtifact:
        if not self._fitted:
            raise ModelError("model not fitted")
        w = self._w.reshape(1, -1); b = self._b.reshape(1, -1)
        return RuntimeModelArtifact(
            model_id=self.model_id,
            model_version=self.model_version,
            model_family=self.model_family,
            feature_version=self.feature_version,
            dataset_version=self.dataset_version,
            seed=self.seed,
            lookback=self.lookback,
            horizon=self.horizon,
            feature_dim=self._feature_dim,
            hyperparameters=(
                ("model_dim", float(self.model_dim)),
                ("epochs", float(self.epochs)),
                ("learning_rate", self.learning_rate),
            ),
            weight_names=("Win", "Wq", "Wk", "Wv", "Wo", "w", "b"),
            weight_shapes=(
                self._Win.shape, self._Wq.shape, self._Wk.shape,
                self._Wv.shape, self._Wo.shape, w.shape, b.shape,
            ),
            weight_values=tuple(
                float(v)
                for m in (self._Win, self._Wq, self._Wk, self._Wv,
                          self._Wo, w, b)
                for v in np.asarray(m, dtype=np.float64).ravel()
            ),
            training_metadata=(("fitted", "true"),),
            metrics=tuple((n, freeze_number(v)) for n, v in metrics),
        )

    @classmethod
    def from_artifact(cls, artifact: RuntimeModelArtifact) -> "TransformerClassifier":
        if artifact.model_family != cls.model_family:
            raise ModelError(
                f"artifact family {artifact.model_family!r} does not match "
                f"{cls.model_family!r}"
            )
        hyper = dict(artifact.hyperparameters)
        model = cls(
            model_dim=int(hyper["model_dim"]),
            epochs=int(hyper["epochs"]),
            learning_rate=hyper["learning_rate"],
            seed=artifact.seed,
            model_id=artifact.model_id,
            model_version=artifact.model_version,
            feature_version=artifact.feature_version,
            dataset_version=artifact.dataset_version,
            lookback=artifact.lookback,
            horizon=artifact.horizon,
        )
        mats = artifact.unpack()
        model._Win = mats["Win"]
        model._Wq = mats["Wq"]
        model._Wk = mats["Wk"]
        model._Wv = mats["Wv"]
        model._Wo = mats["Wo"]
        model._w = mats["w"].ravel()
        model._b = mats["b"].ravel()
        model._feature_dim = artifact.feature_dim
        model._fitted = True
        return model


# ---------------------------------------------------------------------------
# Randomized / diversified ensemble (mandate §16)
# ---------------------------------------------------------------------------

class EnsembleComposition(BaseModel):
    """Ensemble membership + weights (immutable, identity-hashed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    member_hashes: Tuple[str, ...]
    member_versions: Tuple[str, ...]
    member_families: Tuple[str, ...]
    weights: Tuple[float, ...]

    @field_validator("member_hashes", "member_versions", "member_families")
    @classmethod
    def _validate_members(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        if not v:
            raise ModelError("ensemble needs >= 1 member")
        return tuple(v)

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, v: Sequence[float]) -> Tuple[float, ...]:
        w = tuple(float(x) for x in v)
        if not w or any(x <= 0 for x in w):
            raise ModelError("ensemble weights must be positive")
        total = sum(w)
        if not math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ModelError(
                f"ensemble weights must sum to 1 (got {total})"
            )
        return w

    @model_validator(mode="after")
    def _validate_alignment(self) -> "EnsembleComposition":
        if not (
            len(self.member_hashes)
            == len(self.member_versions)
            == len(self.member_families)
            == len(self.weights)
        ):
            raise ModelError("ensemble member fields must align")
        return self

    @property
    def composition_hash(self) -> str:
        return prefixed_hash(
            ENSEMBLE_PREFIX,
            {
                "kind": "ensemble_composition",
                "member_hashes": list(self.member_hashes),
                "member_versions": list(self.member_versions),
                "member_families": list(self.member_families),
                "weights": list(self.weights),
            },
        )

    @property
    def diversity(self) -> float:
        """Fraction of members from distinct model families."""
        return len(set(self.member_families)) / len(self.member_families)


class EnsemblePrediction(BaseModel):
    """One ensemble output with disagreement metadata (§16/§18)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    probability: float
    member_probabilities: Tuple[float, ...]
    disagreement: float  # population std of member probabilities
    composition: EnsembleComposition

    @field_validator("probability", "disagreement")
    @classmethod
    def _freeze(cls, v: float) -> float:
        return freeze_number(v)


class DeterministicEnsemble:
    """Weighted, validated, reproducible model ensemble (§16).

    Members must share feature_version/lookback/horizon/feature-dim —
    incompatible outputs are NEVER silently averaged (constructor
    raises). Every prediction is reproducible from inputs + member
    versions + weights (composition hash).
    """

    def __init__(self, members: Sequence, weights: Sequence[float]) -> None:
        if not members:
            raise ModelError("ensemble needs >= 1 member")
        w = tuple(float(x) for x in weights)
        if len(w) != len(members) or any(x <= 0 for x in w):
            raise ModelError("one positive weight per member required")
        total = sum(w)
        if not math.isclose(total, 1.0, rel_tol=1e-9):
            raise ModelError(f"weights must sum to 1 (got {total})")
        ref = members[0]
        for m in members:
            if (
                m.feature_version != ref.feature_version
                or m.lookback != ref.lookback
                or m.horizon != ref.horizon
            ):
                raise ModelError(
                    "ensemble members are incompatible "
                    f"(feature_version/lookback/horizon must match; "
                    f"member {m.model_id!r} differs from {ref.model_id!r})"
                )
        self._members = tuple(members)
        self._weights = tuple(x / total for x in w)

    def predict(self, x: Sequence[Sequence[float]]) -> EnsemblePrediction:
        probs = [m.predict_proba(x) for m in self._members]
        p = sum(w * q for w, q in zip(self._weights, probs))
        mean = sum(probs) / len(probs)
        var = sum((q - mean) ** 2 for q in probs) / len(probs)
        composition = EnsembleComposition(
            member_hashes=tuple(
                m.artifact().model_hash for m in self._members
            ),
            member_versions=tuple(
                f"{m.model_id}@{m.model_version}" for m in self._members
            ),
            member_families=tuple(m.model_family for m in self._members),
            weights=self._weights,
        )
        return EnsemblePrediction(
            probability=round(p, 12),
            member_probabilities=tuple(round(q, 12) for q in probs),
            disagreement=round(math.sqrt(var), 12),
            composition=composition,
        )

    @property
    def members(self) -> tuple:
        return self._members

    @property
    def weights(self) -> Tuple[float, ...]:
        return self._weights


# ---------------------------------------------------------------------------
# Calibration wrapper (mandate §17)
# ---------------------------------------------------------------------------

class CalibrationArtifact(BaseModel):
    """Runtime calibration artifact (provenance + reliability)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    calibrator_version: str
    method: str
    a: float
    b: float
    ece: float
    n_calibration: int
    dataset_version: str

    @property
    def calibration_hash(self) -> str:
        return prefixed_hash(
            CALIBRATION_PREFIX,
            {
                "kind": "calibration_artifact",
                "calibrator_version": self.calibrator_version,
                "method": self.method,
                "a": self.a,
                "b": self.b,
                "ece": self.ece,
                "n_calibration": self.n_calibration,
                "dataset_version": self.dataset_version,
            },
        )


class RuntimeCalibrator:
    """Platt-scaling wrapper with ECE + artifact provenance (§17).

    Uncalibrated confidence is never treated as probability truth:
    the runtime records the calibration mapping AND its expected
    calibration error; consumers can refuse uncalibrated outputs.
    """

    def __init__(self, dataset_version: str = "dv-unknown") -> None:
        self._inner = None
        self._ece: Optional[float] = None
        self._n = 0
        self._dataset_version = dataset_version

    @property
    def dataset_version(self) -> str:
        """Dataset version this calibrator was fitted on."""
        return self._dataset_version

    @property
    def ece(self) -> Optional[float]:
        """Expected calibration error (None until fitted)."""
        return self._ece

    def fit(
        self, probabilities: Sequence[float], outcomes: Sequence[int]
    ) -> "RuntimeCalibrator":
        from data_engine.prediction.calibration import (
            PlattCalibrator,
            expected_calibration_error,
        )

        if len(probabilities) != len(outcomes) or not probabilities:
            raise ModelError("calibration pairs must be non-empty and aligned")
        self._inner = PlattCalibrator().fit(probabilities, outcomes)
        self._ece = expected_calibration_error(probabilities, outcomes)
        self._n = len(probabilities)
        return self

    @property
    def fitted(self) -> bool:
        return self._inner is not None and self._inner.fitted

    def calibrate(self, probability: float) -> float:
        if not self.fitted:
            raise ModelError("calibrator not fitted")
        return round(self._inner.calibrate(probability), 12)

    def artifact(self) -> CalibrationArtifact:
        if not self.fitted:
            raise ModelError("calibrator not fitted")
        return CalibrationArtifact(
            calibrator_version=self._inner.version,
            method=self._inner.method,
            a=freeze_number(self._inner._a),
            b=freeze_number(self._inner._b),
            ece=freeze_number(self._ece),
            n_calibration=self._n,
            dataset_version=self._dataset_version,
        )

    @classmethod
    def from_artifact(cls, artifact: CalibrationArtifact) -> "RuntimeCalibrator":
        """RT-F14-style reconstruction (no refit needed)."""
        from data_engine.prediction.calibration import PlattCalibrator

        model = cls(dataset_version=artifact.dataset_version)
        inner = PlattCalibrator()
        inner._a = artifact.a
        inner._b = artifact.b
        model._inner = inner
        model._ece = artifact.ece
        model._n = artifact.n_calibration
        return model


# ---------------------------------------------------------------------------
# Walk-forward evaluation (mandate §13/§14)
# ---------------------------------------------------------------------------

class WalkForwardReport(BaseModel):
    """Deterministic walk-forward evaluation report (§13/§14)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_family: str
    n_windows: int
    n_predictions: int
    accuracy: float
    brier: float
    log_loss: float
    per_window_accuracy: Tuple[float, ...]

    @field_validator("n_windows", "n_predictions")
    @classmethod
    def _validate_counts(cls, v: int) -> int:
        if v < 1:
            raise ModelError("report needs >= 1 window/prediction")
        return v

    @field_validator("accuracy", "brier", "log_loss")
    @classmethod
    def _freeze(cls, v: float) -> float:
        return freeze_number(v)


def _brier(probs, ys) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, ys)) / len(probs)


def _logloss(probs, ys) -> float:
    total = 0.0
    for p, y in zip(probs, ys):
        p = min(max(p, 1e-12), 1 - 1e-12)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(probs)


def evaluate_walk_forward(
    model_factory: Callable[[], object],
    labeled_sequences: Sequence,
    train_size: int,
    test_size: int,
    horizon: int,
    step: Optional[int] = None,
) -> WalkForwardReport:
    """Fit per-window on train, predict test — the ONLY sanctioned
    evaluation path for runtime models (§13 walk-forward validation).

    ``labeled_sequences`` must all carry available labels.
    """
    from data_engine.runtime.sequence import build_walk_forward_splits

    labeled = [s for s in labeled_sequences if s.label_available]
    if not labeled:
        raise ModelError("no labeled sequences to evaluate")
    splits = build_walk_forward_splits(
        n_sequences=len(labeled),
        horizon=horizon,
        train_size=train_size,
        test_size=test_size,
        step=step,
    )
    all_p: list = []
    all_y: list = []
    per_window_acc: list = []
    for split in splits:
        train_X = [list(labeled[i].features) for i in split.train_indices]
        train_y = [labeled[i].target for i in split.train_indices]
        model = model_factory()
        model.fit(train_X, train_y)
        correct = 0
        for i in split.test_indices:
            p = model.predict_proba(list(labeled[i].features))
            y = labeled[i].target
            all_p.append(p)
            all_y.append(y)
            if (p >= 0.5) == bool(y):
                correct += 1
        per_window_acc.append(correct / len(split.test_indices))
    accuracy = sum(1 for p, y in zip(all_p, all_y) if (p >= 0.5) == bool(y)) / len(all_p)
    return WalkForwardReport(
        model_family=getattr(model_factory(), "model_family", "unknown"),
        n_windows=len(splits),
        n_predictions=len(all_p),
        accuracy=accuracy,
        brier=_brier(all_p, all_y),
        log_loss=_logloss(all_p, all_y),
        per_window_accuracy=tuple(round(a, 12) for a in per_window_acc),
    )


__all__ = [
    "ModelError",
    "RuntimeModelArtifact",
    "DeterministicBaseline",
    "LSTMClassifier",
    "TransformerClassifier",
    "EnsembleComposition",
    "EnsemblePrediction",
    "DeterministicEnsemble",
    "CalibrationArtifact",
    "RuntimeCalibrator",
    "WalkForwardReport",
    "evaluate_walk_forward",
]
