# PREDICTION RED-TEAM / ADVERSARIAL REPORT

```text
Document Type:  Adversarial validation report (executed matrix)
Phase:          PRED (Prediction & Crash Intelligence) — closure cycle
Authority:      B — CURRENT SUPPORTING (evidence companion to the
                validation/evaluation report)
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-08
Matrix Source:  src/data_engine/prediction/redteam.py (EXECUTED, not
                described)
Matrix Hash:    preda.8366c03c0e055f6b574422dbf60149bbec6343b11211fe7dc144ac0cf87dd628
Coverage:       PRED-F2 closure — mandate §13 six categories, 45 attacks
```

---

## 1. Method

Every attack below was EXECUTED against the live prediction layer
(PIT views, features, labels, estimator, gates, ledger, datasets,
quality gates, artifact verification, event evaluation, scenarios,
systemic measures, microstructure declarations). Each attack record
carries the mandated fields: ATTACK_ID, PRECONDITION, INPUT,
EXPECTED_BEHAVIOR, ACTUAL_BEHAVIOR, PASS/FAIL, EVIDENCE. A PASS
verdict means the system defended exactly as designed (fail-closed);
a FAIL would be a real defect. The matrix is deterministic — repeated
execution yields the identical matrix hash.

Hardening applied as a direct result of building this matrix:

- `close=True` (bool) candles REJECTED (RT-PRED-I-001)
- `close=inf` candles REJECTED; `freeze_number` raises on inf
  (RT-PRED-I-007)
- `close=NaN` candles REJECTED at data access (RT-PRED-I-008)
- estimator artifact flags re-verified internally (RT-PRED-P-005/006,
  RT-PRED-M-001/004/007 — PRED-F3)

## 2. Execution Summary

```text
attacks: 45  PASS: 45  FAIL: 0
  crash-intelligence PASS  7  FAIL  0
  data             PASS  8  FAIL  0
  identity         PASS  8  FAIL  0
  model            PASS  7  FAIL  0
  provenance       PASS  7  FAIL  0
  temporal         PASS  8  FAIL  0
```

Harness guarantees (tested in
`tests/test_prediction_redteam_matrix.py`): attack ids unique; every
record carries all mandated fields; category counts exact; determinism
across runs; the harness counts synthetic FAILs (self-test).

## 3. Full Attack Matrix

| ATTACK_ID | Category | Precondition | Input | Expected | Actual | Verdict | Evidence |
|---|---|---|---|---|---|---|---|
| `RT-PRED-T-001` | temporal | PIT candle view at a declared cutoff | candle dated 30 days after the cutoff injected into the input series | future bar INVISIBLE at the cutoff; dropped_future_bars incremented | visible=60 bars, dropped_future_bars=1 | **PASS** | max visible ts 2024-02-29T00:00:00+00:00 <= cutoff 2024-02-29T00:00:00+00:00 |
| `RT-PRED-T-002` | temporal | feature construction over a PIT-visible prefix | features recomputed over the FULL series (including post-cutoff bars) and compared to the PIT-sliced computation | feature hashes DIFFER — using non-PIT data is detectable, and the estimator only ever computes over the sliced view | pit feature hash != full-series hash: True; rows 21 vs 40 | **PASS** | pit=predf.52fe11a115b36c2da8.. full=predf.7eaee744e82e5e0d7a.. — the estimator builds features from view.bars only (§2 slice-then-compute) |
| `RT-PRED-T-003` | temporal | label/feature boundary proof over aligned rows | a crafted feature row whose source range overlaps the label window [t+1, t+H] | assert_label_feature_boundary RAISES — leakage is a defect, not a warning | clean rows: boundary assertion PASSED (features end at or before label window start); crafted overlap: overlapping feature row REJECTED (fail closed) | **PASS** | label windows use closes[t+1..t+W]; feature rows are structurally limited to source_end <= t |
| `RT-PRED-T-004` | temporal | first-arrival-wins revision policy | late-arriving duplicate timestamp carrying a halved close price (a revision) | revision DROPPED — the prediction's view of history cannot be rewritten | dropped_revision_bars=1; visible closes identical to clean view: True | **PASS** | revision policy 'first-arrival-wins' (§34 no revised data leakage) |
| `RT-PRED-T-005` | temporal | full estimator pipeline at a fixed cutoff | same candle history with a revised duplicate appended after the fact | prediction_id, probability, and status UNCHANGED — revised history cannot leak into a past prediction; the provenance record honestly documents the dropped revision (audit trail, not leakage) | ids equal: True; probabilities equal: True; statuses equal: True | **PASS** | id=pred.8eb525750ca009a5b9a..; original view 51 bars, extended view 51 bars, 1 revision dropped (provenance_hash differs BY DESIGN — it records that a revision arrived and was refused) |
| `RT-PRED-T-006` | temporal | PIT view sorted-by-timestamp invariant | input rows fully reversed (delayed arrival ordering) | view CONTENT AND ORDER unchanged — arrival order cannot alter the PIT view | visible=51; bars identical to ordered input: True | **PASS** | view is built from a timestamp-sorted dict — order independent by construction |
| `RT-PRED-T-007` | temporal | cutoff visibility rule timestamp <= as_of | cutoff moved by ±1 microsecond around an existing bar timestamp | bar AT the cutoff is VISIBLE; bar 1µs beyond is INVISIBLE — the boundary is exact | visible at cutoff: 41; at +1µs: 41; at -1µs: 40 | **PASS** | boundary comparison is <= on UTC-normalized timestamps (no tz shift can flip it) |
| `RT-PRED-T-008` | temporal | UTC-normalized cutoff comparison | the same cutoff instant expressed as UTC vs UTC+05:00 | IDENTICAL visibility decision — timezone representation cannot move the boundary | visible counts equal: True (41) | **PASS** | as_of and every timestamp are normalized to UTC before comparison |
| `RT-PRED-I-001` | identity | duck-typed candle close validation | close=True (Python bool — an int subclass that float() would silently coerce to 1.0) | REJECTED — type collisions cannot enter the PIT view | bool close REJECTED (PredictionDataError) | **PASS** | bool check precedes float coercion in _candle_close (RT hardening) |
| `RT-PRED-I-002` | identity | 12-decimal identity freeze semantics (documented) | close differing by 1e-13 — below the freeze resolution | deterministic DOCUMENTED equivalence: sub-resolution differences hash identically (resolution limit recorded, not hidden) | hash equal after 12-decimal freeze: True | **PASS** | freeze resolution is 1e-12 (round(x, 12)) — the documented identity resolution floor |
| `RT-PRED-I-003` | identity | close validation + empty-input estimator path | close=None mid-series; and an EMPTY candle list passed to the estimator | None REJECTED; empty series produces a PREDICTION_BLOCKED assessment — never a fabricated number | None close REJECTED; empty view bars=0; empty-assess status=PREDICTION_BLOCKED/DATA_QUALITY_FAILED | **PASS** | 'no candles visible at the PIT cutoff' refusal path |
| `RT-PRED-I-004` | identity | canonical key-sorted serialization | identity payload with dict keys in two different insertion orders | IDENTICAL identity — field order cannot reorder identity | hashes equal: True | **PASS** | predv.a53f31a6277488c0ab.. == predv.a53f31a6277488c0ab.. |
| `RT-PRED-I-005` | identity | ModelArtifact JSON round-trip + tuple/list canonicalization | artifact serialized to JSON and rebuilt; parameters expressed as tuples vs lists | hash STABLE through the round-trip; tuples and lists canonicalize identically | round-trip stable: True; tuple/list identical: True | **PASS** | serialization ambiguity cannot fork an identity |
| `RT-PRED-I-006` | identity | byte-exact canonical serialization (no silent Unicode normalization) | symbol 'café' in NFC vs NFD normalization forms | DIFFERENT identities — two visibly-equal strings never silently merge into one asset; callers must normalize deliberately | hashes distinct: True | **PASS** | predv.ac70f8e8862ce83795.. != predv.966a9d768d76795dd2.. — byte-level distinction preserved (fail-visible, not fail-silent) |
| `RT-PRED-I-007` | identity | finite-float validation at data access AND identity freeze | close=+inf in a candle; inf in a hashed payload | BOTH rejected — non-finite numbers are data failures, never identity inputs | inf close REJECTED; inf REJECTED from identity payloads | **PASS** | freeze_number raises on inf (RT hardening); _candle_close rejects non-finite closes |
| `RT-PRED-I-008` | identity | NaN rejection at data access; NaN->None at identity freeze | close=NaN in a candle; NaN as a hashed numeric leaf | NaN close REJECTED; freeze_number maps NaN to None — NaN is never hashed as a number | NaN close REJECTED; freeze_number(NaN) -> None | **PASS** | None marks missing values so they can never silently pass as numeric identity |
| `RT-PRED-P-001` | provenance | append-only outcome ledger with hash chain | entry 2's forecast mutated after the fact | chain verification FAILS on the mutated ledger; clean ledger verifies | clean verify=True, tampered verify=False | **PASS** | record_hash covers the full record payload + index + prev hash |
| `RT-PRED-P-002` | provenance | ledger chain links entries via prev_record_hash | entry 2's parent hash replaced with the genesis hash (forged chain origin) | verification FAILS — parent link integrity is checked per-entry | tampered verify=False | **PASS** | prev_record_hash must equal the previous entry's record_hash exactly |
| `RT-PRED-P-003` | provenance | provenance identity covers dataset_id | dataset identifier swapped inside a provenance record body | provenance content hash CHANGES — the swap is tamper-evident, not silent | hash changed: True | **PASS** | dataset_id participates in every derived provenance hash; a changed id is a different record |
| `RT-PRED-P-004` | provenance | assessment output_hash covers model identity | model_id field swapped on a produced assessment | output_hash CHANGES — a swapped model identity cannot inherit the original assessment's tamper-evidence | hash changed: True | **PASS** | model_id is inside output_payload; any mutation forks the hash |
| `RT-PRED-P-005` | provenance | independent artifact re-verification (PRED-F3) | caller asserts a fabricated expected model hash (the 'verified=True' pattern) | verification RECOMPUTES the artifact hash and REJECTS the forged expectation — caller claims are never trusted | verified=False; expected_hash_match=False | **PASS** | failures: ["expected model hash 'predm.FORGED0000' does not match the artifact ('predm.1fb90069a6840dc8be938fe0cb4079642ab82c53ee334dbc1da0885801ade9ba') — stale or substituted artifact"] |
| `RT-PRED-P-006` | provenance | estimator-bound expected model hash (PRED-F3) | registry-supplied expected hash that does not match the live model artifact | assessment BLOCKED with MODEL_ARTIFACT_MISMATCH — stale/substituted artifacts never predict | status=PREDICTION_BLOCKED; reason=MODEL_ARTIFACT_MISMATCH | **PASS** | verify_model_artifact runs inside assess() and feeds the gate machine |
| `RT-PRED-P-007` | provenance | dataset content checksum gate (QG-15) | dataset rows mutated after the manifest checksum was recorded (stale provenance) | quality report INVALID — checksum mismatch is an explicit refusal | passed=False; refusal=INVALID; QG-15 passed=False | **PASS** | content checksum mismatch: manifest declares 'preds.65bb42220a18415cbcb4a5dbd0e0 |
| `RT-PRED-D-001` | data | quality gate QG-02 | an exact duplicate row inserted mid-series | duplicate gate FAILS; report refuses (explicit refusal state) | QG-02 passed=False; refusal=INVALID | **PASS** | 1 duplicate-timestamp rows (first at row 31) |
| `RT-PRED-D-002` | data | quality gate QG-01 | two adjacent rows swapped (ordering broken) | ordering gate FAILS — dataset ingestion refuses unordered rows | QG-01 passed=False | **PASS** | 1 ordering violations (first at row 31) |
| `RT-PRED-D-003` | data | quality gate QG-03 (daily tolerance 7 days) | a 15-day block of bars removed mid-series | missing-interval gate FAILS — gaps are listed, never silently interpolated | QG-03 passed=False | **PASS** | 1 gaps exceed 7 days, 0:00:00 (first after row 29) |
| `RT-PRED-D-004` | data | quality gate QG-05 | close replaced with a negative price | price gate FAILS; report INVALID — negative prices are never repaired in place | QG-05 passed=False; refusal=INVALID | **PASS** | 1 rows with non-positive/NaN prices (first at row 30) |
| `RT-PRED-D-005` | data | quality gate QG-04 (OHLC relationships) | row with high < open (impossible candle) | OHLC gate FAILS — impossible bars are refused, not clipped | QG-04 passed=False | **PASS** | 1 rows with impossible OHLC (first at row 30) |
| `RT-PRED-D-006` | data | quality gate QG-12 (corporate-action consistency) | a 3x single-bar price jump under a declared split-adjusted policy | corporate-action gate FLAGS the jump — an unadjusted split is suspected and refused | QG-12 passed=False | **PASS** | 2 split-like jumps under declared treatment 'split-adjusted' — possible unadjusted corporate action (first at row 31) |
| `RT-PRED-D-007` | data | quality gate QG-10 (symbol identity) | half the rows carry a foreign symbol mid-series | symbol gate FAILS — cross-symbol contamination is refused | QG-10 passed=False | **PASS** | 30 rows carry a foreign symbol (expected 'TEST'; first at row 30) |
| `RT-PRED-D-008` | data | quality gate QG-11 (manifest coverage match) | only 40 of 60 declared bars delivered | coverage gate FAILS — a partial dataset cannot pose as the declared one | QG-11 passed=False | **PASS** | actual last bar 2024-02-09 != declared coverage_end 2024-02-29; declared row_count 60 != inspected 40 |
| `RT-PRED-M-001` | model | registry-bound model hash + live refit model | model refit on different data after registration (hash changed) | assessment BLOCKED — the stale registration does not cover the new artifact | status=PREDICTION_BLOCKED; reason=MODEL_ARTIFACT_MISMATCH | **PASS** | expected-hash comparison inside assess() (PRED-F3) |
| `RT-PRED-M-002` | model | no-prediction gate drift checks (§37) | drift state DRIFTED and INVALID | BOTH states BLOCK predictions — drifted/ invalid models never silently continue as production states | DRIFTED allowed=False; INVALID allowed=False | **PASS** | §37: DRIFTED -> block or require review; INVALID -> retire |
| `RT-PRED-M-003` | model | no-prediction gate calibration check | calibration_valid=False with everything else green | prediction BLOCKED — an invalid calibrator never emits a risk level | allowed=False; reason=CALIBRATION_INVALID | **PASS** | §18 calibration validity is a hard gate |
| `RT-PRED-M-004` | model | independent artifact verification (PRED-F3) | model object exposing model_id/version/hash but NO artifact() method | verification FAILS CLOSED — a hash that cannot be recomputed is not trusted; the estimator blocks | verified=False; estimator status=PREDICTION_BLOCKED/MODEL_ARTIFACT_MISMATCH | **PASS** | documented boundary: without artifact() the strongest possible verification is identity-field validation, which does not establish content integrity |
| `RT-PRED-M-005` | model | artifact schema verification + feature gate | 3-feature model fed to a 6-feature estimator | schema incompatibility DETECTED at verification; estimator blocks with FEATURE_SCHEMA_MISMATCH | schema_compatible=False; estimator=PREDICTION_BLOCKED/FEATURE_SCHEMA_MISMATCH | **PASS** | artifact consumes 3 features, estimator will supply 6 |
| `RT-PRED-M-006` | model | model predict-time arity check | predict_proba called with 3 values on a 2-feature model | RAISES PredictionModelError — the estimator maps this to a blocked assessment | PredictionModelError raised: model not fitted | **PASS** | fail-closed model contract (§27 root cause) |
| `RT-PRED-M-007` | model | dataset-compatibility verification (PRED-F3) | estimator bound to dataset DS-OLD but assessed against expected DS-NEW | BLOCKED — model/data version mismatch is recorded in the refusal notes | status=PREDICTION_BLOCKED; reason=MODEL_ARTIFACT_MISMATCH | **PASS** | dataset_compatible=False in the verification report |
| `RT-PRED-C-001` | crash-intelligence | label/feature boundary proof (§14) | crisis labels computed over a window that overlaps the feature source range | boundary proof RAISES — label contamination is structural, not reviewable | contaminated feature row REJECTED | **PASS** | labels use closes[t+1..t+W]; features are capped at source_end <= t |
| `RT-PRED-C-002` | crash-intelligence | warning lookback clamped to available history | warning_lookback_bars=100 on an 8-bar series | lookback CLAMPS to the series start; detection only counts warnings strictly BEFORE the event | events=1; detected=1; lead=4.0 | **PASS** | window_start = max(0, t - lookback) — warnings are never sought in the future |
| `RT-PRED-C-003` | crash-intelligence | crisis-sample sufficiency gate (§12) | 1 crisis event against a minimum of 5 | CRISIS_SAMPLE_INSUFFICIENT recorded — statistical robustness is NOT claimed | crisis_events=1; status=CRISIS_SAMPLE_INSUFFICIENT | **PASS** | the state is carried on every evaluation report, never hidden |
| `RT-PRED-C-004` | crash-intelligence | uncertainty band refusal (§19) | p=0.5 with n_effective=3 (a coin flip dressed as a forecast) | band width >= 0.5 triggers MODEL_UNCERTAIN/refusal — wide-uncertainty probabilities never become risk levels | band width=0.7399; uncertain=True; refused assessment carries probability=None | **PASS** | MAX_PROBABILITY_BAND_WIDTH=0.5 refusal discipline |
| `RT-PRED-C-005` | crash-intelligence | systemic layer vocabulary audit (§16) | systemic risk reading generated and its schema/notes scanned for causal claims | reading carries CORRELATION vocabulary only and an explicit not-causation note — correlation is never described as causation | label='LOW_RISK'; epistemic_note carries not-causation: True | **PASS** | SystemicRiskReading fields are correlation-only; epistemic_note is hardcoded to the §25 disclaimer |
| `RT-PRED-C-006` | crash-intelligence | microstructure availability declaration (§15) | request for order-book features with no order-book data in the repository | explicit UNAVAILABLE — microstructure is never synthesized from OHLCV | available=False; status=MICROSTRUCTURE_UNAVAILABLE | **PASS** | no spread/depth/queue module exists anywhere in the prediction package (structural absence) |
| `RT-PRED-C-007` | crash-intelligence | scenario contract (§16: ESTIMATE never FORECAST) | scenario result generated; then an attempt to flip is_forecast=True on the record | is_forecast is structurally False; the validator REJECTS the flip; the disclaimer labels outputs as estimates | is_forecast=False; flip rejected: True; disclaimer present: True | **PASS** | ScenarioResult validator raises on is_forecast=True (§24 contract) |
---

## 4. Reading the Matrix

No attack "succeeded" — every row shows the layer refusing, blocking,
detecting, or staying deterministic. Where behavior is a documented
equivalence rather than a rejection (RT-PRED-I-002 freeze resolution,
RT-PRED-I-006 Unicode distinction), the record states the exact
semantic and why it is fail-visible rather than fail-silent.
