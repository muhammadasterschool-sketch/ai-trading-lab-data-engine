# ZAI DEFECT REGISTER

**Report ID:** ZAI_DEFECT_REGISTER
**Task:** Master Mandate v1.0 — Phase 32 (bug discovery / external review prep)
**Date:** 2026-10-07 (PKT)
**Repository HEAD:** `281dfdc` (`phase-4a/4a1-architecture-correction`)
**Status:** CONSTRUCTION STOPPED at this register per the mandate. NO finding
below was fixed, closed, or concealed. Independent external review (GPT) and
the authorized Claude fix window are the required next steps; the human
operator dispatches both.

Register fields per finding: ID · SEVERITY · COMPONENT · DESCRIPTION ·
REPRODUCTION · EXPECTED · ACTUAL · IMPACT · ROOT CAUSE · RECOMMENDED FIX ·
TEST REQUIRED · GOVERNANCE IMPACT.

---

## F-04 / H-1 — CRITICAL-CLASS CONTAMINATION, ADJUDICATED HIGH, CONTAINED

- **ID:** H-1 (spec finding F-04)
- **SEVERITY:** HIGH (adjudicated; contained; human-reviewed recommendation)
- **COMPONENT:** frozen Phase 3 `src/data_engine/schemas.py` — `Candle.to_hash()`
- **DESCRIPTION:** `provider_timestamp` has `default_factory=_now_utc` and
  enters `model_dump_json()` inside `to_hash()`, so identical OHLCV candles
  hashed with the field unset produce different digests on every call
  (wall-clock contamination of a frozen identity contract).
- **REPRODUCTION:** construct two `Candle`s without `provider_timestamp`,
  hash both — digests differ (`fec31014…` vs `d1556110…` in the original
  audit; re-reproduced at every session since, including this one). With the
  field explicit, the digest is stable (`884e2ce9…`, 3/3 subprocesses).
- **EXPECTED:** identical inputs → identical identity hash, always.
- **ACTUAL:** unset path diverges per call; explicit path is stable.
- **IMPACT:** any future consumer that hashes default-constructed candles
  inherits non-deterministic identity. Current reachability: wired-but-dormant
  (`provider.py:270-281` → `ingestion.py:167`), with ZERO active callers of
  `ingest_from_file` in src/tests/CLI (F-9 precision finding).
- **ROOT CAUSE:** wall-clock default factory included in the serialized hash
  payload of a frozen-era contract.
- **RECOMMENDED FIX:** Option A (standing recommendation, awaiting human
  ratification): CONTAINMENT — keep the frozen contract unchanged; the
  prohibition (`pit/view.py:65`), SUB-25 bomb test, and MUT-13/MUT-05 mutation
  coverage hold. Option B (requires explicit Phase 3 amendment authorization,
  new manifest, full re-freeze ceremony): remove the wall-clock default from
  the identity payload.
- **TEST REQUIRED:** existing — SUB-25 (no Phase 3 hash in Phase 4 identity),
  MUT-13/MUT-05 (mutation detection). If Option B: fresh frozen-contract
  amendment evidence chain.
- **GOVERNANCE IMPACT:** H-1 = OPEN / CONTAINED. Blocks nothing currently
  (zero active callers); Phase 3 amendment NOT AUTHORIZED; WP-5 (amendment
  process) NOT AUTHORIZED pending human decision.

## F-11 — SILENT ALL-NONE FEATURES FOR GENERIC INDICICATOR NAMES (NEW)

- **ID:** F-11
- **SEVERITY:** MEDIUM
- **COMPONENT:** frozen-era `src/data_engine/quant/core.py`
  (`QuantEngine.calculate`) + `quant/registry.py` (IndicatorSpec defaults) +
  `strategy/backtest.py` (`_generate_features` parameterless call path)
- **DESCRIPTION:** `calculate()` invokes `spec.function(prices,
  timestamps=..., **params)` with ONLY caller-supplied params — the
  `IndicatorSpec.parameters` defaults (e.g. `{"period": 20}` for `sma`) are
  never merged into the call. For generic indicator names whose functions
  declare required positional parameters (bare `sma`, `ema`), the call raises
  `TypeError`, which is caught and converted to `QuantResult(success=False,
  values=[None]*n)` — silently.
- **REPRODUCTION:** `QuantEngine().calculate('sma', dataset)` → 0 non-None
  values over 80 bars; `calculate('sma', dataset, period=20)` → 61 non-None;
  `calculate('sma20', dataset)` (pre-parameterized wrapper) → 61 non-None.
  Consequently `BacktestEngine._generate_features` (parameterless) feeds
  all-None series for `required_indicators=["sma"]` and the strategy never
  trades.
- **EXPECTED:** default parameters declared in the registry are applied;
  either the call succeeds with defaults or the failure is loud.
- **ACTUAL:** silent all-None feature series; dependent strategies silently
  never trade.
- **IMPACT:** silent degradation adjacent to false assurance; any strategy
  spec naming a generic indicator appears valid but is inert through the
  frozen engine path. Discovered during lifecycle construction (this cycle);
  no production strategy currently names generic indicators (generated
  candidates use pre-parameterized names).
- **ROOT CAUSE:** registry declares per-indicator defaults but the dispatch
  path never merges them; the broad `except Exception` converts the
  programmer error into empty output instead of a raised boundary error.
- **RECOMMENDED FIX (fix window, NOT now):** merge `spec.parameters` with
  caller params before dispatch, and/or raise `QuantBoundaryError` on
  indicator-function `TypeError` instead of returning success=False
  all-None. Frozen-era code: requires the authorized Claude fix window with
  regression tests; SUB-18 manifest impact must be assessed (quant/core.py
  pinning status) before touching.
- **TEST REQUIRED:** regression test `calculate('sma', ds)` yields non-None
  values after bar `period-1`, or raises loudly if defaults are removed
  instead; plus a backtest test that a `required_indicators=["sma"]` spec
  actually trades.
- **GOVERNANCE IMPACT:** none to authorization chains; register-and-defer
  per the bug-handling model. Mirrors the F-04 lesson: broad exception
  swallowing in frozen-era code converts defects into silence.

## F-9 — DORMANT DEFECTIVE WIRING (PRECISION FINDING)

- **ID:** F-9
- **SEVERITY:** LOW (informational precision; superseding a week-end report
  scope nuance)
- **COMPONENT:** `provider.py:270-281` → `ingestion.py:165-195`
- **DESCRIPTION:** the F-04-defective unset-timestamp path IS wired into the
  dormant Phase 3 ingestion API (`ingest_from_file`), whose only candle
  constructor path omits `provider_timestamp`.
- **REPRODUCTION:** call-graph + code reading (verified again this session:
  zero callers of `ingest_from_file` anywhere).
- **EXPECTED/ACTUAL:** documented precision — "zero call sites" claims are
  accurate only for Phase 4+ modules; the dormant Phase 3 wiring exists.
- **IMPACT:** residual risk only if the dormant API is ever called without
  explicit timestamps.
- **ROOT CAUSE:** frozen-era default design.
- **RECOMMENDED FIX:** containment stands (H-1). Optional hygiene in a fix
  window: an explicit `provider_timestamp` requirement at the dormant entry
  point, or deprecation notice.
- **TEST REQUIRED:** existing H-1 coverage suffices while dormant.
- **GOVERNANCE IMPACT:** recorded in the reconciliation; no change.

## M-1 — UNUSED DEPENDENCY SURFACE

- **ID:** M-1 · **SEVERITY:** MEDIUM · **COMPONENT:** `pyproject.toml`
- **DESCRIPTION:** `numpy>=1.0` declared but never imported in src/tests;
  `pytest` duplicated as runtime + dev dependency.
- **REPRODUCTION:** `rg -c "import numpy" src/ tests/` → 0.
- **EXPECTED:** dependency set = actual import surface.
- **ACTUAL:** numpy is pure supply-chain surface.
- **IMPACT:** dependency-audit noise; inflated supply-chain trust boundary.
- **ROOT CAUSE:** scaffold-era dependency list never pruned.
- **RECOMMENDED FIX:** authorized dependency commit: drop numpy, move pytest
  to dev extras, regenerate `uv.lock` in the same commit.
- **TEST REQUIRED:** suite green after the change (no behavioral delta).
- **GOVERNANCE IMPACT:** none; requires an authorized change window (WP-2).

## M-2 — LOCAL MAIN REF STALENESS

- **ID:** M-2 · **SEVERITY:** MEDIUM (local-only) · **COMPONENT:** local git refs
- **DESCRIPTION:** local `main` = `13fdc7e`, 22+5 behind `origin/main`/branch
  heads because the fast-forward push updated only remote refs.
- **REPRODUCTION:** `git branch -vv`.
- **EXPECTED:** local ref mirrors the authoritative remote.
- **ACTUAL:** 22 behind (remote is correct).
- **IMPACT:** confusion risk for local tooling that assumes main is current.
- **ROOT CAUSE:** push updates remotes only.
- **RECOMMENDED FIX (local, no commit):** `git fetch origin && git branch -f
  main origin/main` — operator action.
- **TEST REQUIRED:** none.
- **GOVERNANCE IMPACT:** none (remote is authoritative).

## M-3 — STALE MANIFEST BLOCK IN THE REMEDIATION SPEC

- **ID:** M-3 · **SEVERITY:** MEDIUM · **COMPONENT:**
  `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` §10.2
- **DESCRIPTION:** the spec's original §10.2 manifest (recorded against a
  CRLF working tree) retains 7/13 stale hashes; superseded by the re-recorded
  13/13 committed-state manifest (PHASE_4A1_IMPLEMENTATION_RECORD §3), with
  the divergence disclosed — but automated audits parsing the spec
  false-alarm.
- **REPRODUCTION:** run `reaudit_ground_truth.py` against the spec block.
- **EXPECTED:** single authoritative manifest source.
- **ACTUAL:** two manifest blocks, one stale, one authoritative.
- **IMPACT:** audit-script false alarms; operator confusion.
- **ROOT CAUSE:** historical recording conditions (CRLF-era), preserved per
  the no-history-rewrite rule.
- **RECOMMENDED FIX:** one-line "SUPERSEDED — see
  PHASE_4A1_IMPLEMENTATION_RECORD §3" marker above the stale block in the
  next authorized docs commit (additive, not a rewrite).
- **TEST REQUIRED:** none.
- **GOVERNANCE IMPACT:** none (disclosed divergence; additive marker only).

## M-4 — FEATURE-PIPELINE TEST DEPTH

- **ID:** M-4 · **SEVERITY:** MEDIUM · **COMPONENT:** `quant/features.py`
- **DESCRIPTION:** 6 tests cover the pipeline's themes exactly (as-of
  cutoff, no-future-in-hash, determinism, spec validation, warmup-None,
  empty-window fail-closed) but numeric breadth (more feature families,
  edge windows) is thin.
- **REPRODUCTION:** test inventory.
- **EXPECTED:** per-family numeric coverage.
- **ACTUAL:** theme-level coverage.
- **IMPACT:** undetected numeric regressions in untested feature families.
- **ROOT CAUSE:** construction-cycle scope discipline.
- **RECOMMENDED FIX:** test-hardening window (WP-3): parameterized feature
  families + edge windows.
- **TEST REQUIRED:** the hardening tests themselves.
- **GOVERNANCE IMPACT:** none.

## L-1 — TRACKED TEST ARTIFACT `src/audit.log`

- **ID:** L-1 · **SEVERITY:** LOW · **COMPONENT:** repo hygiene
- **DESCRIPTION:** 89-byte test artifact tracked since `8f1570f`.
- **RECOMMENDED FIX:** hygiene commit removes it from tracking.
- **GOVERNANCE IMPACT:** none.

## L-2 — RESOURCE-WARNING FILE HANDLES IN FROZEN-ERA SELF-SCAN TESTS

- **ID:** L-2 · **SEVERITY:** LOW · **COMPONENT:** frozen-era tests
- **DESCRIPTION:** `open().read()` patterns leak handles; 14 tests fail
  only under `-W error` (green under default config).
- **RECOMMENDED FIX:** context-manager rewrite in an authorized test commit
  (do not hotfix frozen-era files casually).
- **GOVERNANCE IMPACT:** none.

## L-3 — ZERO-TEST FROZEN CORRUPTION EVIDENCE FILE

- **ID:** L-3 · **SEVERITY:** LOW · **COMPONENT:**
  `tests/test_strategy_corrupted_pre_rebuild.py`
- **DESCRIPTION:** intentionally contains zero tests (frozen corruption
  evidence); generates pytest collection noise.
- **RECOMMENDED FIX:** rename to `.py.frozen` or relocate under `docs/` in
  an authorized commit.
- **GOVERNANCE IMPACT:** none (evidence preservation is the point).

## L-4 — ACCEPTANCE-ID COUNTING IMPRECISION

- **ID:** L-4 · **SEVERITY:** LOW · **COMPONENT:** B6 commit message
- **DESCRIPTION:** "95 IDs" vs 87 distinct docstring-tagged IDs measured
  (families complete: SUB 25/25, T-series 19/19; 23 name-encoded extras).
- **RECOMMENDED FIX:** documentation note only.
- **GOVERNANCE IMPACT:** none (no coverage claim is false).

## L-5 — FS RULES COVERED TRANSITIVELY

- **ID:** L-5 · **SEVERITY:** LOW · **COMPONENT:** test hardening
- **DESCRIPTION:** filesystem rules without dedicated docstring IDs are
  covered transitively; explicit per-rule tests would strengthen the matrix.
- **RECOMMENDED FIX:** WP-3 test-hardening window.
- **GOVERNANCE IMPACT:** none.

## L-6 / L-7 — EXTERNAL AUDIT-SCRIPT COSMETICS

- **IDs:** L-6, L-7 · **SEVERITY:** LOW · **COMPONENT:** external scripts
- **DESCRIPTION:** hardcoded stage label; narrow grep probe — no repo
  impact.
- **RECOMMENDED FIX:** optional script polish.
- **GOVERNANCE IMPACT:** none.

---

## REGISTER SUMMARY

| Severity | Count | IDs |
|---|---|---|
| HIGH (adjudicated, contained) | 1 | H-1/F-04 |
| MEDIUM | 5 | F-11 (new), M-1, M-2, M-3, M-4 |
| LOW | 8 | F-9, L-1, L-2, L-3, L-4, L-5, L-6, L-7 |

**CRITICAL unresolved: 0. HIGH unresolved without governance decision: 1
(H-1 — decision rendered: containment, pending human ratification).**

Per the mandate's Critical Finding Policy, nothing in this register matches
the STOP classes (no frozen mismatch, no security defect, no live bypass, no
authorization bypass, no PIT leakage, no identity failure, no secret
exposure, no network escape, no risk bypass). Construction is stopped at
this register as ordered; every finding now requires, in order: independent
external review (GPT) → authorized fix assignments (Claude window for
F-11/M-items; human decision for H-1) → post-fix Z.ai read-only verification
→ closure with evidence. No finding may be closed by its discoverer without
independent verification.
