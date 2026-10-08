"""Governed prediction benchmark harness (PRED-F1 closure, mandate §3/§9/§10).

The performance-benchmark protocol. Three hard rules:

1. TEMPORAL SEPARATION IS STRUCTURAL. Chronological partitions with
   purge/embargo gaps (Phase-13 discipline) are the only permitted
   split shape; every artifact records a :class:`SplitManifest`
   carrying training/validation/test intervals, feature cutoff, label
   horizon, dataset version, and model version.

2. EMPIRICAL VALIDATION REQUIRES REAL_VERIFIED DATA. ``run_prediction_benchmark``
   refuses to produce an empirical result unless the dataset manifest
   verifies ``REAL_VERIFIED`` with adequate coverage. With no verified
   real dataset the harness returns the BLOCKED result
   (``REAL_DATA_VALIDATION = BLOCKED``) — a complete, machine-readable
   refusal artifact, never a fabricated GREEN (mandate §1.3).

3. SYNTHETIC DATA IS CONTRACT VERIFICATION, NEVER EVIDENCE. The
   ``mode="contract-verification"`` path runs the identical protocol on
   declared-synthetic fixtures and stamps every artifact with
   ``evidence_class = SYNTHETIC_CONTRACT_VERIFICATION`` and
   ``empirical_valid = False``. These runs prove the machinery works;
   they prove NOTHING about market prediction quality.

Evaluation randomness (seeded bootstrap) is recorded with seed,
algorithm, dataset version, and split manifest — distinct from
identity determinism (no wall clock / RNG / PID ever enters an
artifact identity).
"""

import math
from typing import Callable, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.calibration import (
    CalibrationReport,
    PlattCalibrator,
    brier_score,
    expected_calibration_error,
    log_loss,
)
from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.data_access import HistoryPolicyReading
from data_engine.prediction.datasets import DatasetManifest, DatasetState
from data_engine.prediction.drift import population_stability_index
from data_engine.prediction.evaluation import (
    ChronologicalSplit,
    chronological_partitions,
)
from data_engine.prediction.event_evaluation import (
    CrashEventEvaluation,
    EventEvaluationConfig,
    evaluate_crash_events,
)
from data_engine.prediction.identity import BENCHMARK_PREFIX, prefixed_hash
from data_engine.prediction.labels import (
    CrashLabelDefinition,
    compute_crash_labels,
)
from data_engine.prediction.models import ModelJustification, justify_model

#: Evidence classes (mandate §26 — categories are never combined).
EVIDENCE_CLASS_EMPIRICAL = "REAL_EMPIRICAL"
EVIDENCE_CLASS_SYNTHETIC = "SYNTHETIC_CONTRACT_VERIFICATION"
EVIDENCE_CLASS_BLOCKED = "BLOCKED_NO_REAL_DATA"

#: Randomness declaration for seeded evaluation components (§23).
EVALUATION_RANDOMNESS = {
    "algorithm": "bootstrap-paired-mean",
    "generator": "python random.Random (Mersenne Twister)",
    "resamples": 200,
}


class SplitManifest(BaseModel):
    """Reproducible record of one temporal split (mandate §10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_bars: int
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int
    test_start: int
    test_end: int
    final_oos_start: int
    final_oos_end: int
    paper_start: int
    paper_end: int
    purge: int
    embargo: int
    label_horizon_bars: int
    feature_cutoff: int  # last bar whose FEATURES may enter training
    dataset_id: str
    dataset_state: str
    model_id: str
    model_version: str

    @field_validator("n_bars", "label_horizon_bars")
    @classmethod
    def _validate_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise ValueError("must be a positive int")
        return v

    @property
    def split_hash(self) -> str:
        return prefixed_hash(
            BENCHMARK_PREFIX,
            {
                "kind": "split_manifest",
                "n_bars": self.n_bars,
                "train": [self.train_start, self.train_end],
                "validation": [self.validation_start, self.validation_end],
                "test": [self.test_start, self.test_end],
                "final_oos": [self.final_oos_start, self.final_oos_end],
                "paper": [self.paper_start, self.paper_end],
                "purge": self.purge,
                "embargo": self.embargo,
                "label_horizon_bars": self.label_horizon_bars,
                "feature_cutoff": self.feature_cutoff,
                "dataset_id": self.dataset_id,
                "dataset_state": self.dataset_state,
                "model_id": self.model_id,
                "model_version": self.model_version,
            },
        )

    @classmethod
    def from_split(
        cls,
        split: ChronologicalSplit,
        *,
        dataset: DatasetManifest,
        model_id: str,
        model_version: str,
        label_horizon_bars: int,
    ) -> "SplitManifest":
        return cls(
            n_bars=split.n_bars,
            train_start=split.train_start,
            train_end=split.train_end,
            validation_start=split.validation_start,
            validation_end=split.validation_end,
            test_start=split.test_start,
            test_end=split.test_end,
            final_oos_start=split.final_oos_start,
            final_oos_end=split.final_oos_end,
            paper_start=split.paper_start,
            paper_end=split.paper_end,
            purge=split.purge,
            embargo=split.embargo,
            label_horizon_bars=label_horizon_bars,
            feature_cutoff=split.train_end,
            dataset_id=dataset.manifest_hash,
            dataset_state=dataset.data_state.value,
            model_id=model_id,
            model_version=model_version,
        )


class BenchmarkProtocol(BaseModel):
    """Declared, hash-stable evaluation protocol (mandate §3/§9/§10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    train_fraction: float = 0.60
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    purge: int = 5
    embargo: int = 10
    warning_threshold: float = 0.25
    warning_lookback_bars: int = 10
    forward_event_window_bars: int = 10
    min_improvement: float = 0.05
    bootstrap_seed: int = 0
    bootstrap_resamples: int = 200
    min_crisis_events: int = 5

    @field_validator("train_fraction", "validation_fraction",
                     "test_fraction", "warning_threshold", "min_improvement")
    @classmethod
    def _validate_unit(cls, v: float) -> float:
        if not (0.0 < v < 1.0):
            raise ValueError("fractions/thresholds must be in (0, 1)")
        return v

    @field_validator("purge", "embargo", "bootstrap_seed",
                     "bootstrap_resamples", "warning_lookback_bars",
                     "forward_event_window_bars", "min_crisis_events")
    @classmethod
    def _validate_non_negative(cls, v: int) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("must be a non-negative int")
        return v

    @property
    def protocol_hash(self) -> str:
        return prefixed_hash(
            BENCHMARK_PREFIX,
            {
                "kind": "benchmark_protocol",
                "train_fraction": self.train_fraction,
                "validation_fraction": self.validation_fraction,
                "test_fraction": self.test_fraction,
                "purge": self.purge,
                "embargo": self.embargo,
                "warning_threshold": self.warning_threshold,
                "warning_lookback_bars": self.warning_lookback_bars,
                "forward_event_window_bars": (
                    self.forward_event_window_bars
                ),
                "min_improvement": self.min_improvement,
                "bootstrap_seed": self.bootstrap_seed,
                "bootstrap_resamples": self.bootstrap_resamples,
                "min_crisis_events": self.min_crisis_events,
            },
        )


class ModelEvaluationEntry(BaseModel):
    """One model's evaluation metrics under the protocol (§9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    model_family: str
    segment: str
    n_predictions: int
    brier: float
    log_loss_value: float
    ece: float

    @property
    def entry_hash(self) -> str:
        return prefixed_hash(
            BENCHMARK_PREFIX,
            {
                "kind": "model_evaluation_entry",
                "model_id": self.model_id,
                "model_family": self.model_family,
                "segment": self.segment,
                "n_predictions": self.n_predictions,
                "brier": self.brier,
                "log_loss": self.log_loss_value,
                "ece": self.ece,
            },
        )


class CalibrationEvaluation(BaseModel):
    """Pre/post calibration performance with temporal separation (§11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: str = "platt"
    fitted_on: str  # "validation" — NEVER test (§11 Platt discipline)
    raw_test_brier: float
    calibrated_test_brier: float
    raw_test_ece: float
    calibrated_test_ece: float
    calibration_validity: str

    @property
    def improved(self) -> bool:
        return self.calibrated_test_brier < self.raw_test_brier


class DriftSummary(BaseModel):
    """Per-feature PSI between train and test distributions (§12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_name: str
    psi: float
    state: str


class RefusalAnalysis(BaseModel):
    """Control-state tally over governed test assessments (§0)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_assessments: int
    status_counts: Tuple[Tuple[str, int], ...]

    @property
    def refusal_rate(self) -> float:
        refused = sum(
            count for status, count in self.status_counts
            if status not in (
                "NO_SIGNAL", "LOW_RISK", "ELEVATED_RISK",
                "HIGH_RISK", "EXTREME_RISK",
            )
        )
        if self.n_assessments == 0:
            return 0.0
        return refused / self.n_assessments


class BenchmarkResult(BaseModel):
    """Machine-readable benchmark artifact (mandate §3 outputs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark_id: str
    mode: str  # "empirical" | "contract-verification" | "blocked"
    evidence_class: str
    empirical_valid: bool
    real_data_validation: str  # "PERFORMED" | "BLOCKED"
    block_reason: Optional[str] = None
    protocol_hash: str
    split_manifest: Optional[SplitManifest] = None
    dataset_manifest_hash: str
    dataset_state: str
    dataset_name: str
    coverage_years: Optional[float] = None
    history_policy_status: Optional[str] = None
    baselines: Tuple[ModelEvaluationEntry, ...] = ()
    candidate: Optional[ModelEvaluationEntry] = None
    justification: Optional[ModelJustification] = None
    calibration: Optional[CalibrationEvaluation] = None
    crash_event_evaluation: Optional[CrashEventEvaluation] = None
    drift_summary: Tuple[DriftSummary, ...] = ()
    refusal_analysis: Optional[RefusalAnalysis] = None
    notes: Tuple[str, ...] = ()

    @property
    def benchmark_hash(self) -> str:
        return prefixed_hash(
            BENCHMARK_PREFIX,
            {
                "kind": "benchmark_result",
                "mode": self.mode,
                "evidence_class": self.evidence_class,
                "empirical_valid": self.empirical_valid,
                "real_data_validation": self.real_data_validation,
                "block_reason": self.block_reason,
                "protocol_hash": self.protocol_hash,
                "split_manifest": (
                    None if self.split_manifest is None
                    else self.split_manifest.split_hash
                ),
                "dataset_manifest_hash": self.dataset_manifest_hash,
                "dataset_state": self.dataset_state,
                "baselines": [b.entry_hash for b in self.baselines],
                "candidate": (
                    None if self.candidate is None
                    else self.candidate.entry_hash
                ),
                "justification": (
                    None if self.justification is None
                    else self.justification.status
                ),
                "crash_event_evaluation": (
                    None if self.crash_event_evaluation is None
                    else self.crash_event_evaluation.evaluation_hash
                ),
                "notes": list(self.notes),
            },
        )

    def summary(self) -> str:
        """Human-readable one-screen summary (never an overclaim)."""
        lines = [
            f"benchmark_id: {self.benchmark_id}",
            f"mode: {self.mode}  evidence_class: {self.evidence_class}",
            f"real_data_validation: {self.real_data_validation}",
        ]
        if self.block_reason:
            lines.append(f"BLOCKED: {self.block_reason}")
        if self.coverage_years is not None:
            lines.append(
                f"dataset: {self.dataset_name} "
                f"({self.dataset_state}, {round(self.coverage_years, 3)}y)"
            )
        if self.candidate is not None:
            lines.append(
                f"candidate [{self.candidate.segment}] "
                f"brier={round(self.candidate.brier, 6)} "
                f"logloss={round(self.candidate.log_loss_value, 6)} "
                f"ece={round(self.candidate.ece, 6)}"
            )
        for b in self.baselines:
            lines.append(
                f"baseline {b.model_id} [{b.segment}] "
                f"brier={round(b.brier, 6)}"
            )
        if self.justification is not None:
            lines.append(
                f"justification: {self.justification.status} "
                f"(improvement={round(self.justification.improvement, 6)} "
                f">= {self.justification.min_improvement}?)"
            )
        if self.crash_event_evaluation is not None:
            ev = self.crash_event_evaluation
            lines.append(
                f"crash events [{ev.segment}]: {ev.detected_events}/"
                f"{ev.total_events} detected, "
                f"precision={ev.precision}, fpr={ev.false_positive_rate}, "
                f"f1={ev.f1}, lead={ev.mean_lead_time_bars}, "
                f"crisis={ev.crisis_sample_status}"
            )
        if self.calibration is not None:
            lines.append(
                f"calibration: fitted_on={self.calibration.fitted_on}, "
                f"brier {round(self.calibration.raw_test_brier, 6)} -> "
                f"{round(self.calibration.calibrated_test_brier, 6)}, "
                f"validity={self.calibration.calibration_validity}"
            )
        if self.refusal_analysis is not None:
            lines.append(
                f"refusals: {self.refusal_analysis.refusal_rate:.1%} of "
                f"{self.refusal_analysis.n_assessments} assessments "
                f"({dict(self.refusal_analysis.status_counts)})"
            )
        lines.append(
            "CLAIM BOUNDARY: "
            + (
                "empirical performance on verified real data"
                if self.empirical_valid
                else "NO empirical claim — "
                + (
                    "synthetic contract verification only"
                    if self.evidence_class == EVIDENCE_CLASS_SYNTHETIC
                    else "real-data validation is BLOCKED"
                )
            )
        )
        return "\n".join(lines)


def blocked_benchmark(
    *,
    dataset: Optional[DatasetManifest],
    protocol: BenchmarkProtocol,
    reason: str,
) -> BenchmarkResult:
    """The complete refusal harness (mandate §3: 'otherwise implement a
    complete blocked/refusal benchmark harness').

    Machine-readable, hash-stable, honest: REAL_DATA_VALIDATION=BLOCKED
    with the exact reason. Never a fabricated GREEN.
    """
    return BenchmarkResult(
        benchmark_id="predb.BLOCKED",
        mode="blocked",
        evidence_class=EVIDENCE_CLASS_BLOCKED,
        empirical_valid=False,
        real_data_validation="BLOCKED",
        block_reason=reason,
        protocol_hash=protocol.protocol_hash,
        dataset_manifest_hash=(
            dataset.manifest_hash if dataset is not None else "NO-DATASET"
        ),
        dataset_state=(
            dataset.data_state.value if dataset is not None else "ABSENT"
        ),
        dataset_name=(
            dataset.dataset_name if dataset is not None else "ABSENT"
        ),
        notes=(
            "REAL_DATA_VALIDATION = BLOCKED — the repository holds zero "
            "verified years of real market data; performance claims are "
            "structurally unavailable (mandate §1.3/§26)",
            "the harness, protocol, splits, metrics, and refusal states "
            "are fully implemented and contract-tested — ready to run "
            "the moment a REAL_VERIFIED dataset is approved and ingested",
        ),
    )


def _fit_and_score(
    model_factory: Callable[[], object],
    X, y, eval_X, eval_y,
) -> ModelEvaluationEntry:
    model = model_factory()
    model.fit(X, y)
    preds = [float(model.predict_proba(row)) for row in eval_X]
    outcomes = [1 if v else 0 for v in eval_y]
    return ModelEvaluationEntry(
        model_id=getattr(model, "model_id", "UNKNOWN"),
        model_family=getattr(model, "model_family", "unknown"),
        segment="test",
        n_predictions=len(preds),
        brier=brier_score(preds, outcomes),
        log_loss_value=log_loss(preds, outcomes),
        ece=expected_calibration_error(preds, outcomes),
    )


def run_prediction_benchmark(
    *,
    dataset: DatasetManifest,
    closes: Sequence[float],
    timestamps: Optional[Sequence[object]] = None,
    label_definition: CrashLabelDefinition,
    model_factory: Callable[[], object],
    baseline_factories: Sequence[Callable[[], object]] = (),
    protocol: Optional[BenchmarkProtocol] = None,
    mode: str = "empirical",
    regimes: Optional[Sequence[str]] = None,
    crisis_flags: Optional[Sequence[bool]] = None,
    feature_rows: Optional[Sequence] = None,
) -> BenchmarkResult:
    """Run the governed benchmark protocol over a declared dataset.

    GATE (fail-closed):
    - ``mode="empirical"`` requires ``dataset.data_state`` to be
      REAL_VERIFIED AND the 5-year coverage minimum to pass — anything
      else returns the BLOCKED result with the exact reason.
    - ``mode="contract-verification"`` accepts SYNTHETIC datasets and
      stamps every artifact SYNTHETIC_CONTRACT_VERIFICATION /
      empirical_valid=False — the run exercises machinery, never
      claims performance.

    Calibration discipline (§11): Platt scaling is fitted on the
    VALIDATION segment only and applied to TEST — test information
    never enters the calibrator.
    """
    proto = protocol or BenchmarkProtocol()
    notes: list[str] = []

    # --- hard gates -------------------------------------------------------
    if mode not in ("empirical", "contract-verification"):
        raise PredictionContractError(
            f"unknown benchmark mode {mode!r}"
        )
    if mode == "empirical":
        if dataset.data_state is not DatasetState.REAL_VERIFIED:
            return blocked_benchmark(
                dataset=dataset,
                protocol=proto,
                reason=(
                    f"dataset {dataset.dataset_name!r} is "
                    f"{dataset.data_state.value}, not REAL_VERIFIED — "
                    "empirical evaluation refuses unverified data "
                    "(mandate §1.3)"
                ),
            )
    else:
        if dataset.data_state is not DatasetState.SYNTHETIC:
            return blocked_benchmark(
                dataset=dataset,
                protocol=proto,
                reason=(
                    "contract-verification mode requires a declared "
                    "SYNTHETIC dataset (never mix synthetic and real)"
                ),
            )
        notes.append(
            "SYNTHETIC fixtures — deterministic contract verification "
            "ONLY; results are NEVER empirical evidence (mandate §1.3)"
        )

    n = len(closes)
    labeled = compute_crash_labels(
        closes, label_definition, timestamps=timestamps
    )
    labels: list[Optional[bool]] = [p.label for p in labeled]

    if feature_rows is not None:
        rows = feature_rows
    else:
        from data_engine.prediction.features import build_feature_rows
        rows = build_feature_rows(
            closes, timestamps=timestamps
        )
    warmup = rows[0].row_index if rows else 0
    X: list = [list(r.values) for r in rows]
    y: list = [labels[r.row_index] for r in rows]
    usable = [
        i for i, outcome in enumerate(y)
        if outcome is not None
    ]
    X_u = [X[i] for i in usable]
    y_u = [int(y[i]) for i in usable]

    try:
        split = chronological_partitions(
            len(X_u),
            train_fraction=proto.train_fraction,
            validation_fraction=proto.validation_fraction,
            test_fraction=proto.test_fraction,
            purge=proto.purge,
            embargo=proto.embargo,
        )
    except PredictionContractError as exc:
        return blocked_benchmark(
            dataset=dataset,
            protocol=proto,
            reason=f"temporal partition unavailable: {exc}",
        )

    # history policy snapshot (bars-per-year from frequency)
    bars_per_year = 252 if dataset.frequency.upper() in ("1D", "1W") else 24 * 252
    history = HistoryPolicyReading(
        visible_bars=n,
        bars_per_year=bars_per_year,
        minimum_years=5.0,
        preferred_years=10.0,
        meets_minimum=(n / bars_per_year) >= 5.0,
        meets_preferred=(n / bars_per_year) >= 10.0,
    )
    if mode == "empirical" and not history.meets_minimum:
        return blocked_benchmark(
            dataset=dataset,
            protocol=proto,
            reason=(
                f"coverage {round(history.years_covered, 3)}y < 5y "
                "minimum (mandate §17) — CRISIS_SAMPLE_INSUFFICIENT "
                "remains active"
            ),
        )
    if not history.meets_minimum:
        notes.append(
            f"HISTORY POLICY NOT MET ({round(history.years_covered, 3)}y "
            "< 5y minimum) — recorded, contract-verification only"
        )

    train_idx = list(split.train_indices())
    val_idx = list(split.validation_indices())
    test_idx = list(split.test_indices())

    model = model_factory()
    model.fit(
        [X_u[i] for i in train_idx], [y_u[i] for i in train_idx]
    )
    test_preds = [
        float(model.predict_proba(X_u[i])) for i in test_idx
    ]
    test_out = [y_u[i] for i in test_idx]
    candidate = ModelEvaluationEntry(
        model_id=getattr(model, "model_id", "UNKNOWN"),
        model_family=getattr(model, "model_family", "unknown"),
        segment="test",
        n_predictions=len(test_preds),
        brier=brier_score(test_preds, test_out),
        log_loss_value=log_loss(test_preds, test_out),
        ece=expected_calibration_error(test_preds, test_out),
    )

    baselines: list[ModelEvaluationEntry] = []
    baseline_test_predictions: list[Tuple[str, list[float]]] = []
    paired_model_losses = [
        (p - o) ** 2 for p, o in zip(test_preds, test_out)
    ]
    for factory in baseline_factories:
        baseline = factory()
        baseline.fit(
            [X_u[i] for i in train_idx], [y_u[i] for i in train_idx]
        )
        b_preds = [
            float(baseline.predict_proba(X_u[i])) for i in test_idx
        ]
        baselines.append(ModelEvaluationEntry(
            model_id=getattr(baseline, "model_id", "UNKNOWN"),
            model_family=getattr(baseline, "model_family", "unknown"),
            segment="test",
            n_predictions=len(b_preds),
            brier=brier_score(b_preds, test_out),
            log_loss_value=log_loss(b_preds, test_out),
            ece=expected_calibration_error(b_preds, test_out),
        ))
        baseline_test_predictions.append(
            (getattr(baseline, "model_id", "UNKNOWN"), b_preds)
        )

    justification: Optional[ModelJustification] = None
    if baselines:
        best = min(baselines, key=lambda b: b.brier)
        best_predictions = next(
            preds for model_id, preds in baseline_test_predictions
            if model_id == best.model_id
        )
        baseline_losses = [
            (p - o) ** 2 for p, o in zip(best_predictions, test_out)
        ]
        justification = justify_model(
            model_id=candidate.model_id,
            baseline_id=best.model_id,
            model_metrics={
                "brier": candidate.brier,
                "log_loss": candidate.log_loss_value,
                "ece": candidate.ece,
            },
            baseline_metrics={
                "brier": best.brier,
                "log_loss": best.log_loss_value,
                "ece": best.ece,
            },
            metric="brier",
            min_improvement=proto.min_improvement,
            model_losses=paired_model_losses,
            baseline_losses=baseline_losses,
            seed=proto.bootstrap_seed,
        )

    # --- calibration: fit on VALIDATION only, evaluate on TEST (§11) -----
    calibration: Optional[CalibrationEvaluation] = None
    calibrator = PlattCalibrator()
    val_model = model_factory()
    val_model.fit(
        [X_u[i] for i in train_idx], [y_u[i] for i in train_idx]
    )
    val_preds = [
        float(val_model.predict_proba(X_u[i])) for i in val_idx
    ]
    val_out = [y_u[i] for i in val_idx]
    if val_preds and all(o in (0, 1) for o in val_out):
        calibrator.fit(val_preds, val_out)
        calibrated_test = [
            calibrator.calibrate(p) for p in test_preds
        ]
        raw_report = CalibrationReport(
            method="none",
            version="raw",
            dataset_id=dataset.manifest_hash,
            n_samples=len(test_preds),
            brier=brier_score(test_preds, test_out),
            log_loss=log_loss(test_preds, test_out),
            ece=expected_calibration_error(test_preds, test_out),
            reliability=(),
        )
        calibrated_report = CalibrationReport(
            method="platt",
            version="platt-v1",
            dataset_id=dataset.manifest_hash,
            n_samples=len(calibrated_test),
            brier=brier_score(calibrated_test, test_out),
            log_loss=log_loss(calibrated_test, test_out),
            ece=expected_calibration_error(calibrated_test, test_out),
            reliability=(),
        )
        calibration = CalibrationEvaluation(
            fitted_on="validation",
            raw_test_brier=raw_report.brier,
            calibrated_test_brier=calibrated_report.brier,
            raw_test_ece=raw_report.ece,
            calibrated_test_ece=calibrated_report.ece,
            calibration_validity=(
                calibrated_report.status
                if calibrated_report.n_samples >= 30
                else "CALIBRATION_INVALID"
            ),
        )
        del raw_report

    # --- crash-event evaluation on the TEST segment (§8) ------------------
    event_config = EventEvaluationConfig(
        label_definition_id=label_definition.label_definition_id,
        label_threshold=label_definition.threshold,
        horizon_bars=label_definition.forward_horizon,
        warning_threshold=proto.warning_threshold,
        warning_lookback_bars=proto.warning_lookback_bars,
        forward_event_window_bars=proto.forward_event_window_bars,
        min_crisis_events=proto.min_crisis_events,
    )
    # map test X-indices back to absolute bar indices
    abs_test = [usable[i] for i in test_idx]
    abs_row_idx = [rows[i].row_index for i in abs_test]
    event_eval = evaluate_crash_events(
        probabilities=test_preds,
        labels=[labels[bar] for bar in abs_row_idx],
        config=event_config,
        segment="test",
        regimes=(
            [regimes[bar] for bar in abs_row_idx]
            if regimes is not None else None
        ),
        crisis_flags=(
            [crisis_flags[bar] for bar in abs_row_idx]
            if crisis_flags is not None else None
        ),
        segment_start=abs_row_idx[0] if abs_row_idx else 0,
    )

    # --- uncertainty / refusal analysis over test predictions (§0/§19) ---
    from data_engine.prediction.crash import classify_risk_level
    from data_engine.prediction.uncertainty import (
        is_uncertain,
        probability_band,
    )
    status_tally: dict[str, int] = {}
    n_effective = max(len(train_idx), 1)
    for p in test_preds:
        band = probability_band(p, n_effective=n_effective)
        if is_uncertain(band):
            status = "MODEL_UNCERTAIN"
        else:
            status = classify_risk_level(p)
        status_tally[status] = status_tally.get(status, 0) + 1
    refusal_analysis = RefusalAnalysis(
        n_assessments=len(test_preds),
        status_counts=tuple(sorted(status_tally.items())),
    )

    # --- drift: per-feature PSI train -> test (§12) -------------------------
    drift_summary: list[DriftSummary] = []
    from data_engine.prediction.drift import classify_drift
    if rows:
        n_features = len(rows[0].values)
        feature_names = [
            getattr(r, "names", None) or [f"f{j}" for j in range(n_features)]
            for r in [rows[0]]
        ][0]
        for j in range(n_features):
            train_vals = [X_u[i][j] for i in train_idx]
            test_vals = [X_u[i][j] for i in test_idx]
            try:
                psi = population_stability_index(train_vals, test_vals)
                state = classify_drift(psi).value
            except PredictionContractError:
                psi = float("nan")
                state = "INVALID"
            drift_summary.append(DriftSummary(
                feature_name=str(feature_names[j]),
                psi=float(psi) if psi == psi else 0.0,
                state=state,
            ))

    split_manifest = SplitManifest.from_split(
        split,
        dataset=dataset,
        model_id=getattr(model, "model_id", "UNKNOWN"),
        model_version=getattr(model, "model_version", "1"),
        label_horizon_bars=label_definition.forward_horizon,
    )

    result = BenchmarkResult(
        benchmark_id="predb.RUN",
        mode=mode,
        evidence_class=(
            EVIDENCE_CLASS_EMPIRICAL if mode == "empirical"
            else EVIDENCE_CLASS_SYNTHETIC
        ),
        empirical_valid=(mode == "empirical"),
        real_data_validation=(
            "PERFORMED" if mode == "empirical" else "BLOCKED"
        ),
        protocol_hash=proto.protocol_hash,
        split_manifest=split_manifest,
        dataset_manifest_hash=dataset.manifest_hash,
        dataset_state=dataset.data_state.value,
        dataset_name=dataset.dataset_name,
        coverage_years=history.years_covered,
        history_policy_status=history.status,
        baselines=tuple(baselines),
        candidate=candidate,
        justification=justification,
        calibration=calibration,
        crash_event_evaluation=event_eval,
        drift_summary=tuple(drift_summary),
        refusal_analysis=refusal_analysis,
        notes=tuple(notes) + (
            f"warm-up bars excluded from features: {warmup}",
            f"evaluation randomness: seed={proto.bootstrap_seed}, "
            f"algorithm={EVALUATION_RANDOMNESS['algorithm']} "
            f"({EVALUATION_RANDOMNESS['resamples']} resamples) — "
            "evaluation-only, never identity",
        ),
    )
    return result


__all__ = [
    "SplitManifest",
    "BenchmarkProtocol",
    "ModelEvaluationEntry",
    "CalibrationEvaluation",
    "DriftSummary",
    "RefusalAnalysis",
    "BenchmarkResult",
    "blocked_benchmark",
    "run_prediction_benchmark",
    "EVIDENCE_CLASS_EMPIRICAL",
    "EVIDENCE_CLASS_SYNTHETIC",
    "EVIDENCE_CLASS_BLOCKED",
    "EVALUATION_RANDOMNESS",
]
