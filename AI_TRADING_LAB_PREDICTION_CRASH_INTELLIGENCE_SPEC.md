# AI Trading Lab — Prediction & Crash Intelligence Specification

```text
Document Type:  Canonical prediction architecture specification
Phase:          PRED (Prediction & Crash Intelligence architecture extension)
Authority:      A — AUTHORITATIVE (canonical spec for this layer)
Status:         CURRENT
Version:        1.1.0 (closure-cycle extension §17; v1.0.0 body retained)
Last Updated:   2026-10-08 (closure/completion/validation cycle)
Source Mandate: "AI Trading Lab — Prediction & Crash Intelligence Master
                Architecture + Implementation Mandate" (58 sections,
                operator-issued 2026-10-08); closure extension per the
                Phase 4A.1 Completion/Validation/Closure mandate (34
                sections, operator-issued 2026-10-08)
Implementation: src/data_engine/prediction/ (31 modules)
Acceptance:     tests/test_prediction_*.py (T-PRED-001..030 + red-team
                matrix + closure suites, 270 prediction tests;
                suite total 1,059)
```

---

## 1. Scope

The AI Trading Lab is not only a strategy/backtesting system. This
specification governs its extension into a **prediction & crash
intelligence research laboratory**: return/volatility forecasting,
regime classification, market-stress detection, crash-risk estimation,
anomaly-ready infrastructure, early-warning measurement, and
probability-calibrated predictions with evidence scoring — all PIT
correct, deterministic, auditable, and integrated with the existing
strategy, risk, and paper-trading engines.

**The system NEVER claims deterministic crash prediction.** Every crash
output is a probabilistic forecast or risk estimate, and the system is
required to be able to say NO_SIGNAL, LOW_RISK, ELEVATED_RISK,
HIGH_RISK, EXTREME_RISK, MODEL_UNCERTAIN, DATA_INSUFFICIENT,
REGIME_UNKNOWN, or PREDICTION_BLOCKED instead of forcing a prediction.
The most important prediction this layer can make is "I DON'T KNOW."

## 2. Architecture — What Exists vs. What This Layer Adds

This layer integrates with, and does not duplicate, the established
package conventions:

| Concern | Existing component (reused) | Prediction layer (added) |
|---|---|---|
| Deterministic hashing | `pit.hashing.deterministic_hash` | `pred*.`-prefixed identities |
| Walk-forward plans | `research_validation.walk_forward` (wf7.) | `prediction.evaluation` outcome pairing |
| Hard risk limits / kill switch | `risk.engine.RiskLimits` | `prediction.risk_integration` (advisory only) |
| Indicator features | `quant.features` (feat6.) | `prediction.features` (risk-feature set, same discipline) |
| Evidence integrity | `evidence.EvidenceProvenance` | `prediction.evidence_score` (explicit composite) |
| Experiment identity | `experiment_registry` | `prediction.registry` (model lifecycle) |
| Paper graduation | `paper.evaluation` | prediction model graduation (separate contract) |

Architectural pipeline (no stage may be bypassed):

```text
PIT view -> data quality -> features -> regime -> gates -> model ->
calibration -> uncertainty -> evidence -> risk level -> provenance ->
audit -> paper evaluation
```

## 3. Module Map

| Module | Purpose |
|---|---|
| `contracts.py` | Closed status vocabulary: RiskLevel, PredictionControlState, RegimeState, StressState, DriftState, ModelLifecycleState, BlockReason, CalibrationStatus, InsufficiencyState |
| `identity.py` | `pred.`/`predl.`/`predm.`/`predf.`/`predv.`/`predo.`/`prede.`/`predd.`/`predr.`/`predg.` prefixed identities; environment fingerprint capture |
| `provenance.py` | Full §15 provenance record (all timestamps caller-supplied; never wall-clock sampled) |
| `data_access.py` | `pit_candle_view` (revision first-arrival-wins), `universe_at`, `evaluate_history_policy` |
| `features.py` | Fixed 6-feature risk schema (`ret_1`, `mom_20`, `vol_20`, `vol_ratio_5_20`, `dd_depth_20`, `range_20`) with per-row source-index ranges |
| `labels.py` | `CrashLabelDefinition` (identity covers every field), forward-window labels, `assert_label_feature_boundary`, crisis-sample readings |
| `regimes.py` | Deterministic `RegimeEngine` (11 states, documented thresholds), transitions as events |
| `stress.py` | `classify_market_stress` (NORMAL→EXTREME, UNKNOWN on missing inputs) |
| `models.py` | Baselines (base-rate, rolling, persistence, regime-conditional, random floor) + `LogisticCrashModel` (deterministic GD) + `justify_model` gate |
| `calibration.py` | Brier, log loss, reliability curve, ECE, `PlattCalibrator`, `CalibrationReport` validity |
| `uncertainty.py` | Closed-set z-scores; empirical, Wald-probability, and ensemble bands; `is_uncertain` |
| `drift.py` | PSI (reference-quantile bins), DriftReport, mandated §37 actions, data-source drift |
| `evidence_score.py` | 11 weighted dimensions; zero-component or sub-0.5 composite → EVIDENCE_INSUFFICIENT |
| `registry.py` | §30 lifecycle machine; duplicate identity rejected; PAPER/GRADUATE require human approval |
| `ledger.py` | Append-only outcome ledger, hash-chained (index + prev-hash + content) |
| `gates.py` | Fixed-order §27 gate evaluation; DEGRADED drift restricts, DRIFTED/INVALID blocks |
| `evaluation.py` | `chronological_partitions` (TRAIN→VALIDATION→TEST→FINAL OOS→PAPER with purge/embargo), `evaluate_walk_forward`, `crash_warning_quality` |
| `crash.py` | `CrashRiskAssessment` contract + `RiskThresholds` + refused-assessment constructors |
| `estimator.py` | `CrashRiskEstimator` — the governed orchestrator wiring every stage |
| `scenarios.py` | 10 scenario kinds; pure runs; `is_forecast` cannot be true |
| `systemic.py` | Pairwise correlations, average/dispersion, spike detection; correlation ≠ prediction ≠ causation |
| `risk_integration.py` | Advisory-only decision over the real `RiskLimits`; kill switch suppresses everything |
| `microstructure.py` | Explicit `MICROSTRUCTURE_UNAVAILABLE` — order-book evidence is never synthesized |
| `datasets.py` *(closure)* | `DatasetManifest` (immutable `preds.` identity), `DatasetState` epistemic machine (SYNTHETIC/REAL_UNVERIFIED/REAL_VERIFIED/INSUFFICIENT/INVALID), content checksums, evidence-driven verification |
| `quality_gates.py` *(closure)* | 16 deterministic gates QG-01..QG-16 with INVALID/DATA_INSUFFICIENT refusal states and affected-row evidence |
| `source_registry.py` *(closure)* | Governed source catalog — human-only approvals, closed usage-scope vocabulary, credential-free schema, UNVETTED candidate matrix |
| `artifact_verification.py` *(closure)* | PRED-F3: recomputed verification of external artifacts (existence, hash vs declared vs expected, serialization integrity, schema, dataset, version) — caller `verified=True` never trusted |
| `event_evaluation.py` *(closure)* | Deterministic crash-episode extraction; event-level metrics (detection, lead, precision, FPR, F1, calibration, regime-conditioned); per-split ownership |
| `benchmark.py` *(closure)* | PRED-F1: governed benchmark protocol — split manifests, mode gating (empirical/contract-verification/blocked), complete refusal harness |
| `redteam.py` *(closure)* | PRED-F2: 45 EXECUTED adversarial attacks across six categories with mandated evidence fields |

## 4. Prediction Targets

Supported target families: next-bar/next-day/multi-horizon return
distributions (baselines + logistic demonstrator), direction
(UP/DOWN/FLAT via momentum features), volatility (rolling + persistence
baselines), drawdown probability/severity (label engine + probability
models), market stress (state classification), and crash risk
(probabilistic assessment contract). The crash-risk output carries:
probability, horizon, severity threshold, confidence, evidence score,
regime, uncertainty band, model/model-version, prediction timestamp,
PIT cutoff, and a machine-readable refusal reason when blocked.

## 5. Crash Labels

Labels are configurable (threshold, measurement window, forward
horizon, asset scope, calibration period, creation version). The
`label_definition_id` hash covers every field — hidden definition drift
is impossible. The label/feature boundary is structural: features stop
at t, labels read t+1..t+H, and `assert_label_feature_boundary` fails
closed on any overlap. Crisis-sample sufficiency is a recorded reading
(CRISIS_SAMPLE_INSUFFICIENT when positives are too few); no statistical
robustness is claimed without it.

## 6. Anti-Leakage Invariants

- **PIT correctness**: features computed over the visible prefix only
  (slice-then-compute; verified by T-PRED-001/002).
- **No revision leakage**: later-arriving duplicate timestamps are
  dropped — first arrival wins (T-PRED-005).
- **No survivorship leakage**: `universe_at` excludes not-yet-listed and
  short-history symbols with named reasons (T-PRED-004).
- **No label leakage**: labels use future windows by definition; the
  boundary proof keeps them out of features (T-PRED-003).
- **No random splits**: chronological partitions only, with purge/embargo
  gaps; walk-forward windows come from the Phase 7 plan builder where
  leakage is unrepresentable (T-PRED-017).

## 7. Data Policy

Minimum 5 years of history per sufficiently liquid instrument where
available; 10–15+ years preferred. The estimator enforces the 5-year
minimum BY DEFAULT (HISTORICAL_COVERAGE_INADEQUATE refusal); an
operator override must be explicit and is recorded in the assessment
notes. Newly listed instruments get INSUFFICIENT_HISTORY. **The
repository contains no real market datasets** — the policy engine,
coverage readings, and refusal states exist and are tested; actual data
acquisition (with provenance per `evidence.EvidenceProvenance`) remains
operator-scoped future work. Coverage claims are therefore never made.

## 8. Baseline-First & Justification

Every prediction target has simple deterministic baselines. A model is
JUSTIFIED only when it beats its baseline by the declared minimum
relative improvement under the predefined protocol (optionally with a
seeded bootstrap CI on paired losses); otherwise the recorded verdict is
MODEL_NOT_JUSTIFIED. No algorithm is added for complexity's own sake:
the implemented advanced family is a single deterministic logistic
model; tree ensembles, sequence models, and neural networks are
deliberately deferred until a baseline-beating need is demonstrated.

## 9. Calibration & Uncertainty

Probabilities travel with raw AND calibrated values, calibration
method/version/dataset, and a `CalibrationReport` (Brier, log loss, ECE,
reliability). Uncertainty is mandatory: analytic probability bands
(Wald, closed-set z-scores), empirical quantile intervals, and ensemble
dispersion. Excessive width → MODEL_UNCERTAIN (probability still
recorded, never hidden).

## 10. Drift & Failure Actions

PSI-based monitoring over reference/current distributions maps to
STABLE / WATCH / DEGRADED / DRIFTED / INVALID with the mandated actions
(continue / increase monitoring / restrict usage / block or require
review / retire). A drifted model never silently continues as healthy.

## 11. Model Governance

Lifecycle: DISCOVER → TRAIN → VALIDATE → CALIBRATE → ADVERSARIAL_TEST →
REGISTER → HUMAN_REVIEW → PAPER → MONITOR → GRADUATE (or REJECT/RETIRE).
Duplicate identity is rejected. PAPER and GRADUATE require a recorded
HUMAN approval; AI/agent approvals are structurally rejected and noted.
The outcome ledger records every forecast with its eventual outcome
(hash-chained, tamper-evident) so the system can learn whether it is
actually improving.

## 12. Prediction → Risk Interface

Prediction output may inform sizing/risk budget/exposure limits,
hedging research, NO-TRADE decisions, and scenario analysis. It may
never bypass hard limits, the kill switch, governance, human approval,
or paper-trading requirements. `prediction_risk_decision` clamps every
proposal to the real Phase 8 `RiskLimits`, marks authority=RISK_ENGINE,
and returns zero sizing input for refused/uncertain predictions.

## 13. Frozen Phase 3 & H-1

The prediction layer is additive only. It imports no frozen module
(`data_engine.schemas`, `data_engine.strategy`) and never invokes the
frozen `Candle` hash method — identity is computed over
caller-extracted values via `deterministic_hash` (H-1 independence).
The SUB-18 13-file manifest is re-verified by T-PRED-028 in the normal
test run. Any genuine incompatibility would be recorded as
PREDICTION_PHASE3_COMPATIBILITY_FINDING and would stop only the affected
integration.

## 14. Test Matrix

T-PRED-001..030 are implemented as named tests across seven files
(PIT/leakage, identity/provenance, regimes/labels, models/calibration,
registry/ledger, gates/evaluation, scenarios/risk/frozen). The matrix is
expandable: adversarial cases in §48 beyond the current set (fake
artifacts, changed feature order/types, corrupted provenance) are
covered at contract level via the gates, hash comparisons, and schema
mismatch refusals.

## 15. Limitations (Honest)

- No real historical data in the repository; all quantitative examples
  in tests are synthetic with declared seeds. No coverage claim.
- One advanced model family (deterministic logistic); no ensembles/NNs.
- Microstructure explicitly UNAVAILABLE; never synthesized.
- CI gates executed locally (pytest + frozen verify + secret scan);
  remote GitHub Actions remains deferred (registered gap WP-12).
- Scenario impacts are declared estimates, not forecasts; systemic-risk
  measures record correlation only — no causal claims.
- The 30-day paper evaluation for prediction models requires real
  candidates and calendar time; not yet exercised.

## 16. Governance

LIVE TRADING AUTHORIZATION: NOT GRANTED. Prediction never executes
trades. LLM/agent roles remain research/summarization/explanation only
(governed by `hermes` contracts and `research` human-only approvals);
deterministic code stays authoritative.

---

## 17. Closure Extension (v1.1.0 — 2026-10-08)

The Phase 4A.1 completion/validation/closure mandate added a
validation-and-governance ring around the layer built under v1.0.0:

1. **Dataset epistemics** (§7 reinforcement): every dataset carries an
   immutable `preds.` manifest; epistemic states
   SYNTHETIC/REAL_UNVERIFIED/REAL_VERIFIED/INSUFFICIENT/INVALID are
   declared and evidence-verified; SYNTHETIC can never be promoted to
   REAL_*; empirical evaluation requires REAL_VERIFIED with ≥ 5
   verified years. Detail: `PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md`.
2. **Data quality gates**: QG-01..QG-16 fail closed with
   INVALID/DATA_INSUFFICIENT refusal states; failures list affected
   rows; data is never silently repaired.
3. **Source governance**: human-only source approvals; fail-closed
   usage authorization over a closed scope vocabulary; no credentials
   in the repository (schema-level guarantee).
4. **External artifact verification (PRED-F3)**: `assess()` recomputes
   artifact hashes (vs declared AND registry-expected), serialization
   integrity, schema/dataset compatibility — caller-asserted flags are
   no longer accepted anywhere.
5. **Crash-intelligence completion (§4F)**: assessments carry
   `dataset_version` and PIT evidence windows; derived warning states
   (WARNING_ACTIVE/WARNING_INACTIVE/REFUSED); the closure mandate's
   risk vocabulary maps 1:1 onto this spec's closed states via
   `RISK_STATE_VOCABULARY_MAP` (NORMAL→NO_SIGNAL/LOW_RISK,
   CRISIS→EXTREME_RISK, INSUFFICIENT_EVIDENCE→EVIDENCE_INSUFFICIENT,
   INVALID→PREDICTION_BLOCKED+BlockReason).
6. **Crash-event evaluation**: deterministic episode extraction;
   warning horizon [t-lookback, t-1] strictly separate from the event
   window [t, t+forward]; detection/miss/lead/precision/FPR/F1/
   warning-frequency/Brier/log-loss/regime-conditioned reported
   together (never a single-metric objective); per-split ownership
   prevents train/test pooling; CRISIS_SAMPLE_INSUFFICIENT is carried
   on every report where it stands.
7. **Benchmark protocol (PRED-F1)**: hash-stable protocol + split
   manifests + machine-readable results; three modes — empirical
   (REAL_VERIFIED only), contract-verification (synthetic, stamped
   `SYNTHETIC_CONTRACT_VERIFICATION`, `empirical_valid=False`), and
   the complete blocked refusal harness. Standing state:
   REAL_DATA_VALIDATION = BLOCKED (0 verified years).
8. **Adversarial matrix (PRED-F2)**: 45 executed attacks across
   temporal/identity/provenance/data/model/crash-intelligence
   categories; all defended; matrix hash recorded in
   `PREDICTION_REDTEAM_ADVERSARIAL_REPORT.md`.

Test acceptance grew from 126 prediction tests (T-PRED-001..030) to
270 (matrix + closure suites); the repository suite is 1,059. Frozen
Phase 3 and H-1 are unchanged. No empirical performance claim is made
or implied anywhere in this spec — see
`PREDICTION_VALIDATION_EVALUATION_REPORT.md` §2 for the strictly
separated claim categories.
