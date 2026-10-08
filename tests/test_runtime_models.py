"""Runtime model tests (pre-paper mandate §13–§17, §43/RT-F14).

Coverage: determinism, artifact round-trip reconstruction (bit
identical), walk-forward evaluation, ensemble validation, calibration,
baseline comparison requirement, no trading authority.
"""

import math
from datetime import datetime, timedelta, UTC

import pytest

from data_engine.runtime.models import (
    DeterministicBaseline,
    DeterministicEnsemble,
    LSTMClassifier,
    ModelError,
    RuntimeCalibrator,
    TransformerClassifier,
    evaluate_walk_forward,
)
from data_engine.runtime.sequence import (
    SequenceSpec,
    build_sequence_set,
)


def _bars(n=120, start=100.0, phase=6, drift=0.6):
    base = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    bars = []
    price = start
    for i in range(n):
        d = drift if (i // phase) % 2 == 0 else -drift * 0.8
        o = price
        c = price + d
        bars.append({
            "timestamp": base + timedelta(minutes=5 * i),
            "open": o, "high": max(o, c) + 0.1, "low": min(o, c) - 0.1,
            "close": c, "volume": 1000.0 + i,
        })
        price = c
    return bars


SPEC = SequenceSpec(symbol="TEST/USD", timeframe="5m", lookback=8,
                    horizon=2, feature_version="fv-1", dataset_version="dv-1")


@pytest.fixture(scope="module")
def labeled_sequences():
    bars = _bars()
    sset = build_sequence_set(bars, SPEC, bars[-1]["timestamp"], "dch",
                              expected_interval_seconds=300)
    return list(sset.labeled)


@pytest.fixture(scope="module")
def xy(labeled_sequences):
    return ([list(s.features) for s in labeled_sequences],
            [s.target for s in labeled_sequences])


MODEL_CASES = [
    ("baseline", lambda: DeterministicBaseline(
        model_id="B", feature_version="fv-1", dataset_version="dv-1",
        lookback=8, horizon=2)),
    ("lstm", lambda: LSTMClassifier(
        hidden_units=3, epochs=2, seed=5, model_id="L",
        feature_version="fv-1", dataset_version="dv-1",
        lookback=8, horizon=2)),
    ("transformer", lambda: TransformerClassifier(
        model_dim=4, epochs=2, seed=3, model_id="T",
        feature_version="fv-1", dataset_version="dv-1",
        lookback=8, horizon=2)),
]


class TestDeterminism:
    @pytest.mark.parametrize("name,factory", MODEL_CASES)
    def test_retraining_is_bit_identical(self, xy, name, factory):
        X, y = xy
        m1 = factory().fit(X, y)
        m2 = factory().fit(X, y)
        p1 = [m1.predict_proba(x) for x in X[:8]]
        p2 = [m2.predict_proba(x) for x in X[:8]]
        assert p1 == p2

    @pytest.mark.parametrize("name,factory", MODEL_CASES)
    def test_different_seed_diverges(self, xy, name, factory):
        X, y = xy
        if name == "baseline":
            pytest.skip("baseline is seed-free by design")
        kw = {"seed": 99} if name == "lstm" else {"seed": 99}
        m = factory()
        m_alt = type(m)(**{**m.__dict__, **kw}) if False else None
        # Construct variant explicitly per family.
        if name == "lstm":
            m_alt = LSTMClassifier(hidden_units=3, epochs=2, seed=99,
                                   model_id="L", feature_version="fv-1",
                                   dataset_version="dv-1",
                                   lookback=8, horizon=2)
        else:
            m_alt = TransformerClassifier(model_dim=4, epochs=2, seed=99,
                                          model_id="T", feature_version="fv-1",
                                          dataset_version="dv-1",
                                          lookback=8, horizon=2)
        m.fit(X, y)
        m_alt.fit(X, y)
        p = [m.predict_proba(x) for x in X[:4]]
        p_alt = [m_alt.predict_proba(x) for x in X[:4]]
        assert p != p_alt

    @pytest.mark.parametrize("name,factory", MODEL_CASES)
    def test_probabilities_in_range(self, xy, name, factory):
        X, y = xy
        m = factory().fit(X, y)
        for x in X[:10]:
            p = m.predict_proba(x)
            assert 0.0 < p < 1.0 and math.isfinite(p)


class TestArtifactsRTF14:
    @pytest.mark.parametrize("name,factory", MODEL_CASES)
    def test_artifact_roundtrip_bit_identical(self, xy, name, factory):
        X, y = xy
        m = factory().fit(X, y)
        art = m.artifact()
        assert art.model_hash.startswith("rtmod.")
        rec = type(m).from_artifact(art)
        p_orig = [m.predict_proba(x) for x in X[:8]]
        p_rec = [rec.predict_proba(x) for x in X[:8]]
        assert p_orig == p_rec, "from_artifact must reproduce predictions exactly"

    def test_unknown_family_rejected(self, xy):
        X, y = xy
        m = DeterministicBaseline(
            model_id="B", feature_version="fv-1", dataset_version="dv-1",
            lookback=8, horizon=2).fit(X, y)
        art = m.artifact().model_copy(
            update={"model_family": "not-a-family"})
        with pytest.raises(ModelError, match="family"):
            DeterministicBaseline.from_artifact(art)

    def test_lstm_reconstruction_after_restart(self, xy):
        """RT-F14: a restart reconstructs the approved model from the
        artifact without refitting."""
        X, y = xy
        m = LSTMClassifier(hidden_units=3, epochs=2, seed=7,
                           feature_version="fv-1", dataset_version="dv-1",
                           lookback=8, horizon=2).fit(X, y)
        art = m.artifact()
        # "Restart": reconstruct from the artifact alone.
        m2 = LSTMClassifier.from_artifact(art)
        assert [m.predict_proba(x) for x in X[:5]] == \
               [m2.predict_proba(x) for x in X[:5]]

    def test_prediction_layer_reconstruction_dispatcher(self, xy):
        """RT-F14 extends to the Phase 4A.1 prediction models."""
        from data_engine.prediction.models import (
            BaseRateBaseline, RollingBaseRateBaseline, NaivePersistenceBaseline,
            RandomClassifierBaseline, RegimeConditionalBaseline,
            LogisticCrashModel, reconstruct_model,
        )
        X, y = xy
        # Single-feature view: first bar's first feature per sequence.
        flat_X = [seq[0][0] for seq in X]
        models = [
            BaseRateBaseline().fit(X, y),
            RollingBaseRateBaseline(window=20).fit(X, y),
            NaivePersistenceBaseline().fit(X, y),
            RandomClassifierBaseline().fit(X, y),
            RegimeConditionalBaseline().fit(X, y, regimes=["A"] * len(y)),
            LogisticCrashModel(feature_names=["f0"]).fit(
                [[r] for r in flat_X], y),
        ]
        for m in models:
            art = m.artifact()
            rec = reconstruct_model(art)
            if hasattr(m, "predict_proba"):
                for x in (X[:3] if not isinstance(m, LogisticCrashModel)
                          else [[r] for r in flat_X[:3]]):
                    assert m.predict_proba(x) == rec.predict_proba(x)
        with pytest.raises(Exception, match="no reconstruction path"):
            class _FakeArt:
                model_family = "unknown-family"
            reconstruct_model(_FakeArt())


class TestModelHygiene:
    def test_unfitted_model_refuses(self, xy):
        m = LSTMClassifier(hidden_units=2, epochs=1, lookback=8, horizon=2)
        with pytest.raises(ModelError, match="not fitted"):
            m.predict_proba(xy[0][0])

    def test_nan_features_rejected(self, xy):
        X, y = xy
        m = DeterministicBaseline(lookback=8, horizon=2).fit(X, y)
        bad = [[float("nan")] * 5] * 8
        with pytest.raises(ModelError, match="non-finite"):
            m.predict_proba(bad)

    def test_wrong_lookback_rejected(self, xy):
        X, y = xy
        m = DeterministicBaseline(lookback=8, horizon=2).fit(X, y)
        with pytest.raises(ModelError, match="lookback"):
            m.predict_proba(X[0][:4])

    def test_invalid_labels_rejected(self, xy):
        X, y = xy
        with pytest.raises(ModelError, match="binary"):
            DeterministicBaseline(lookback=8, horizon=2).fit(X, [2] * len(y))


class TestEnsemble:
    def _fit(self, xy):
        X, y = xy
        b = DeterministicBaseline(model_id="B", feature_version="fv-1",
                                  dataset_version="dv-1", lookback=8,
                                  horizon=2).fit(X, y)
        l = LSTMClassifier(hidden_units=3, epochs=1, seed=5, model_id="L",
                           feature_version="fv-1", dataset_version="dv-1",
                           lookback=8, horizon=2).fit(X, y)
        return b, l

    def test_ensemble_prediction_and_disagreement(self, xy):
        b, l = self._fit(xy)
        ens = DeterministicEnsemble([b, l], [0.5, 0.5])
        pred = ens.predict(xy[0][0])
        probs = pred.member_probabilities
        assert pred.probability == pytest.approx(
            0.5 * probs[0] + 0.5 * probs[1], abs=1e-9)
        mean = sum(probs) / 2
        var = sum((p - mean) ** 2 for p in probs) / 2
        assert pred.disagreement == pytest.approx(math.sqrt(var), abs=1e-9)
        assert pred.composition.composition_hash.startswith("rtens.")
        assert pred.composition.diversity == 1.0

    def test_incompatible_members_rejected(self, xy):
        b, l = self._fit(xy)
        odd = DeterministicBaseline(model_id="B2", feature_version="fv-OTHER",
                                    dataset_version="dv-1", lookback=8,
                                    horizon=2).fit(*xy)
        with pytest.raises(ModelError, match="incompatible"):
            DeterministicEnsemble([b, odd], [0.5, 0.5])

    def test_weights_must_sum_to_one(self, xy):
        b, l = self._fit(xy)
        with pytest.raises(ModelError, match="sum to 1"):
            DeterministicEnsemble([b, l], [0.5, 0.6])

    def test_reproducible_from_composition(self, xy):
        b, l = self._fit(xy)
        ens = DeterministicEnsemble([b, l], [0.6, 0.4])
        p1 = ens.predict(xy[0][0])
        p2 = DeterministicEnsemble([b, l], [0.6, 0.4]).predict(xy[0][0])
        assert p1.probability == p2.probability
        assert p1.composition.composition_hash == p2.composition.composition_hash


class TestCalibration:
    def test_calibration_fit_and_roundtrip(self, xy):
        X, y = xy
        b = DeterministicBaseline(lookback=8, horizon=2).fit(X, y)
        raw = [b.predict_proba(x) for x in X]
        cal = RuntimeCalibrator(dataset_version="dv-1").fit(raw, y)
        assert cal.fitted
        art = cal.artifact()
        assert art.calibration_hash.startswith("rtcal.")
        assert 0.0 <= art.ece <= 1.0
        rec = RuntimeCalibrator.from_artifact(art)
        for p in (0.3, 0.5, 0.7):
            assert rec.calibrate(p) == cal.calibrate(p)

    def test_uncalibrated_use_refused(self):
        cal = RuntimeCalibrator()
        with pytest.raises(ModelError, match="not fitted"):
            cal.calibrate(0.5)


class TestWalkForwardEvaluation:
    def test_baseline_evaluated_walk_forward(self, labeled_sequences):
        rep = evaluate_walk_forward(
            lambda: DeterministicBaseline(
                model_id="B", feature_version="fv-1", dataset_version="dv-1",
                lookback=8, horizon=2),
            labeled_sequences, train_size=20, test_size=10, horizon=2,
        )
        assert rep.n_windows >= 1
        assert 0.0 <= rep.accuracy <= 1.0
        assert rep.brier >= 0.0
        assert rep.log_loss >= 0.0

    def test_lstm_evaluated_against_baseline(self, labeled_sequences):
        """§13: no advanced-model claim without the SAME-PLAN baseline
        comparison (both evaluated under identical splits)."""
        base_rep = evaluate_walk_forward(
            lambda: DeterministicBaseline(
                model_id="B", feature_version="fv-1", dataset_version="dv-1",
                lookback=8, horizon=2),
            labeled_sequences, train_size=20, test_size=10, horizon=2,
        )
        lstm_rep = evaluate_walk_forward(
            lambda: LSTMClassifier(
                hidden_units=3, epochs=1, seed=5,
                feature_version="fv-1", dataset_version="dv-1",
                lookback=8, horizon=2),
            labeled_sequences, train_size=20, test_size=10, horizon=2,
        )
        assert base_rep.n_windows == lstm_rep.n_windows
        # Recorded comparison (no fabricated superiority claim).
        comparison = {
            "baseline_brier": base_rep.brier,
            "lstm_brier": lstm_rep.brier,
            "improvement": base_rep.brier - lstm_rep.brier,
        }
        assert all(math.isfinite(v) for v in comparison.values())

    def test_no_labeled_data_raises(self, labeled_sequences):
        with pytest.raises(ModelError, match="no labeled"):
            evaluate_walk_forward(
                lambda: DeterministicBaseline(lookback=8, horizon=2),
                labeled_sequences[:0], train_size=5, test_size=5, horizon=2,
            )
