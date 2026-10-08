# P1 CORRECTION WINDOW REPORT

```text
Document Type:  Correction-window execution report (P1 of the staged
                readiness program P0–P8)
Phase:          P1 — authorized correction window
Authority:      C — AUDIT EVIDENCE (execution record of the operator's
                P1 authorization, issued 2026-10-08)
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-08
Supersedes:     none (first correction-window execution record)
Superseded By:  —
Source Evidence: commit 1277331 (source+tests) + this docs commit;
                BEFORE evidence scripts/pp_bug_repro.py (11 repros at
                e060690) + pp_frozen_mutable_sweep.py (43 findings);
                AFTER evidence scripts/pp_p1_after_evidence.py (0/17
                defective) + pp_bug008_runtime_sweep.py (31/31 blocked);
                full suite 1141/1141 x3 deterministic; final_gate_verify
                5/5 PASS pre- and post-commit
```

> Operator authorization (verbatim scope): READ and WRITE only to
> correct BUG-001..009, ARCH-F1/F3/F4/F6, RT-F7/F8/F13; frozen Phase 3
> untouched; no LSTM/Transformer/Ensemble/RL/autonomous/paper-runtime/
> broker/live implementation; smallest safe changeset; tests proving
> each correction; full suite + security checks; explicit before/after
> evidence; no closure declaration without objective evidence; **no
> push/merge/tag/deploy** (kept — both P1 commits are local only).

---

## 1. Every finding addressed (before/after evidence)

Legend — BEFORE: state at 5079484 (= e060690 + P0 docs), reproduced by
`scripts/pp_bug_repro.py` / line-verified in the pre-paper forensic.
AFTER: state at 1277331, proven by
`tests/test_p1_correction_window.py` (82 tests) and
`scripts/pp_p1_after_evidence.py` (17 probes).

| Finding | BEFORE (defect) | AFTER (corrected) | Evidence |
|---|---|---|---|
| **BUG-001** CRITICAL | BUY limit 101.5 filled at 101.551015 (+spread+impact ON the limit); SELL below limit; pinned by `test_pt_04:123` | BUY fills at `min(limit, all-in ask)`, SELL at `max(limit, all-in bid)` — never through the limit; passive fill AT the limit with zero charged costs; marketable fill takes the all-in price (improvement in the price, never a negative cost); exact accounting identity `price*qty == base*qty ± (spread+slippage)`; MARKET branch byte-identical semantics | probe A/A2 CLOSED; 7 tests incl. 300-case randomized property test; `test_pt_04` amended (pin removal documented in §3) |
| **BUG-002** CRITICAL | Flip +100@100 → sell 140@110 left short −40 with basis 100; downstream P&L +200 instead of +600 | Flip residual opens at the flip fill's all-in price (basis 110); economics exact (+600); same-sign reduction preserves basis; full close resets to 0 | probe B/B2 CLOSED; 5 tests |
| **BUG-003** CRITICAL | `projected = abs(order)+abs(current)` rejected the full CLOSE of a max position and TRIPPED the kill switch on risk-reducing orders; pinned by `test_risk_portfolio.py:80` | Signed netting: `projected = current + signed(units)`; breach iff `abs(projected) > max` or `abs(units) > max` (order itself oversized); reductions/closes/legitimate flips never breach and never trip; hard-limit posture for true breaches unchanged | probe C/C2 CLOSED; 9 tests; `test_rk_01` amended to documented signed semantics (§3) |
| **BUG-004** HIGH | FILLED order + missing fill + consistent positions reconciled CLEAN (docstring check-2 unimplemented, signature status-blind) | `reconcile` accepts `GatewayRecord` sequences: FILLED-without-fill raises, fill-on-CANCELLED/SUBMITTED/REJECTED raises (fills iff FILLED); legacy plain-order path honestly skips check-2 (documented) | probe D CLOSED; 6 tests |
| **BUG-005** MEDIUM | Payload stored by caller reference; `entries` shallow over live dicts; chain unkeyed/re-forgeable | `log()` deep-copies payload; `entries` returns deep copies; entries carry `timestamp`/`component`/`event_id`; internal tamper still detected; **unkeyed re-forge remains the ACCEPTED threat model** (keyed-MAC custody = registered human decision, deliberately not made) | probe E CLOSED (E2 documented-by-test as accepted boundary); 5 tests |
| **BUG-006** MEDIUM | CLI printed `Status: OPERATIONAL` over a library-only state | Seven truthful dimensions: LIBRARY_HEALTH OK · RUNTIME_HEALTH ABSENT · PAPER_READINESS BLOCKED · LIVE_AUTHORIZATION NOT_AUTHORIZED · DATA_READINESS SYNTHETIC_ONLY/REAL_BLOCKED · MODEL_READINESS 0_APPROVED · RECONCILIATION_HEALTH NOT_WIRED | 2 tests (dimensions + printed output, OPERATIONAL absent) |
| **BUG-007** LOW | Bar ordering unvalidated — unsorted/duplicate bars silently mis-locate the submission bar | `simulate` validates strictly-increasing timestamps; duplicates/regressions raise `SimulationError`; valid series unchanged | probe CLOSED; 3 tests |
| **BUG-008** LOW | 43 mutable dict/list fields inside frozen=True models (annotation-level sweep) | 25 in-scope fields migrated to deep-immutable `FrozenDict`/`FrozenList` via new `pit/immutable.py` (read-API, equality, JSON + PIT canonical serialization, and every existing hash byte-compatible — verified); mutable defaults covered via `validate_default=True` | runtime sweep **31/31 in-scope mutations BLOCKED**; 11 tests; exclusions in §7 |
| **BUG-009** LOW | NaN equity points silently skipped → plausible-but-wrong metrics | `total_pnl`/`max_drawdown`/`sharpe` fail closed (`ValueError`) on any non-finite input; finite behavior unchanged | probe CLOSED; 6 tests |
| **ARCH-F1** MEDIUM | `reset_kill_switch()` a bare flag clear — any caller (incl. AI) could clear a tripped switch; `trip_on_breach=False` silently disabled auto-trip | Reset requires an identified HUMAN principal (`principal` + `principal_kind="human"`); machine/AI/unidentified refused with `RiskViolationError` (mirrors research-governance/prediction-registry conventions); trip stays unprivileged (fail-safe direction); opt-out now warns + `trip_on_breach` property | 8 tests; `test_rk_03` amended (§3) |
| **ARCH-F3** MEDIUM | `EvidenceProvenance` used at ingestion.py:191, never imported → NameError on the happy path | Imported from canonical `data_engine.evidence`; provenance builds | probe CLOSED; 1 test |
| **ARCH-F4** MEDIUM | `datetime`/`UTC` never imported in quant_boundary.py → NameError in `DeterministicResult` default factory + `mark_complete` | Import added; both paths execute | probe F CLOSED; 2 tests |
| **ARCH-F6** LOW | Dormant ingestion path hashed via wall-clock-contaminated `Candle.to_hash()` (H-1 family) | `_compute_raw_hash` hashes canonical market fields via PIT `deterministic_hash`, excluding `provider_timestamp`; identical market data → identical hash; H-1 containment posture preserved (frozen Candle model untouched) | 3 tests (incl. provider_timestamp-irrelevance) |
| **RT-F7** LOW/MED | `check-boundary` called `assert_deterministic` — raises exactly for deterministic-required types → always exit 1 | Verifies via `is_deterministic_required` → exit 0 with DETERMINISTIC confirmation; invalid types still exit 1 with the error path | probe G CLOSED; 3 tests (incl. argparse usage semantics) |
| **RT-F8** LOW/MED | `ingest_from_file` hard-coded `endpoint="./data"` with no approved root → FS-06 fail-closed before any read (dead path); `file_path` ignored | Data dir + `approved_data_root` + instrument allowlist derived from the caller's path (FS-04/FS-14 explicit caller approval; FS-06/07/09-16 containment invariants intact — re-tested); explicit `{instrument}_{timeframe}.csv` naming contract (mismatch fails closed); honest classifier-based Instrument fallback replaces the invalid `asset_class=None` fallback (fail-closed for unclassifiable symbols) | probe CLOSED; 4 tests (incl. end-to-end ingest from a temp CSV and the no-root fail-closed guard) |
| **RT-F13** LOW | `pytest>=9.1.1` a RUNTIME dependency; `src/audit.log` tracked; `.gitignore` gaps | pytest dev-only (+ `uv lock` regenerated, `uv sync --frozen --extra dev` verified, WP-12 CI spec install line updated); `src/audit.log` untracked + ignored; zero pytest imports in src (verified) | probe CLOSED; 4 tests |

All 16 authorized findings: **corrected with objective evidence; NOT
declared CLOSED here** — closure verdicts belong to the P2 independent
re-audit (rule 10). The three findings requiring contract-convention
notes are annotated in §6.

## 2. Files changed (commit 1277331 + this docs commit)

**Source (21 files + 1 new):** `paper/simulator.py` (BUG-001/007) ·
`paper/models.py` (BUG-002) · `paper/gateway.py` (BUG-004/005/009) ·
`risk/engine.py` (BUG-003, ARCH-F1, BUG-008) · `risk/portfolio.py` ·
`cli.py` (BUG-006, RT-F7) · `ingestion.py` (ARCH-F3/F6, RT-F8) ·
`quant_boundary.py` (ARCH-F4) · **`pit/immutable.py` (NEW)** ·
`pit/revision.py` · `pit/contract.py` · `infra/observability.py` ·
`knowledge/models.py` · `quant/features.py` · `quant/schemas.py` ·
`quant/drawdown.py` · `quarantine.py` ·
`research_validation/robustness.py` ·
`research_validation/walk_forward.py` · `benchmarks/runner.py` ·
`experiment_registry/registry.py`.

**Packaging/hygiene:** `pyproject.toml` + `uv.lock` (RT-F13) ·
`.gitignore` (RT-F13) · `src/audit.log` (untracked) ·
`WP_12_CI_IMPLEMENTATION_SPEC.md` (install-line consistency: `--extra dev`).

**Tests:** `tests/test_p1_correction_window.py` (NEW, 82 tests) ·
`tests/test_paper_trading.py` (test_pt_04 amended) ·
`tests/test_risk_portfolio.py` (test_rk_01/test_rk_03 amended).

**Zero frozen-module changes:** no `strategy/` file, no
`docs/strategy_engine_design.md`, no `schemas.py` (manifest-pinned —
see §7), no manifest edit.

## 3. Tests added/changed

- **Added: 82** targeted regression tests in
  `tests/test_p1_correction_window.py`, one test class per finding,
  each named for its finding ID; includes the 300-case randomized
  property test (BUG-001 invariant), the flip-economics matrix
  (BUG-002), the signed-netting matrix incl. no-trip-on-reduction
  (BUG-003), the reset-authentication matrix (ARCH-F1), the
  status-aware reconciliation matrix (BUG-004), the deep-immutability
  matrix over every migrated model (BUG-008), and two frozen-contract
  guards mirroring the forensic gates (rule 1).
- **Changed: 3 pinned tests** — each pinned a DEFECTIVE behavior and
  its amendment is part of the authorized fix (per the pre-paper
  prepared fixes §5.1/§5.3):
  - `test_pt_04` (was `assert fill.price > D("101.5")` — the pinned
    BUG-001 violation): now asserts the protected fill (≤ limit,
    equality at the limit, zero charged costs).
  - `test_rk_01` (pinned additive netting "ok: 100"): same-sign calls
    are outcome-identical under signed netting; comment updated to the
    documented semantics.
  - `test_rk_03` (pinned unauthenticated reset): reset now carries a
    human principal.
- Full-suite delta: 1,059 → **1,141** (−0 removed, 3 amended in place,
  82 added).

## 4. Tests passed/failed

| Run | Result |
|---|---|
| Baseline (pre-change, @5079484) | 1,059/1,059 |
| Full suite @1277331 (run 1) | **1,141/1,141** in 16.83s |
| Determinism runs 2 & 3 (`-p no:cacheprovider`) | **1,141/1,141** / **1,141/1,141** |
| Failures | **0** |
| AFTER-evidence probe (`scripts/pp_p1_after_evidence.py`) | **0/17 defective** (exit 0) |
| BUG-008 runtime sweep (`scripts/pp_bug008_runtime_sweep.py`) | **31/31 in-scope mutations BLOCKED** (exit 0) |
| BEFORE-evidence script (`scripts/pp_bug_repro.py`) | 8/11 no longer reproduce; C/C2/D "reproduce" only under the pre-correction calling conventions (unsigned magnitudes / status-blind input) — detailed in §6; the corrected-convention equivalents are probe-closed |

## 5. Frozen-contract integrity + security results

| Check | Result |
|---|---|
| Frozen Phase-3 blobs vs `main@13fdc7e` | **11/11 byte-identical** (pre- and post-commit) |
| SUB-18 manifest (13 sha256 pins incl. `schemas.py`) | **13/13 match** — no pinned file modified |
| `docs/strategy_engine_design.md` | untouched |
| Secret scan (tracked files) | **0 hits / 263 files** (pre- and post-commit) |
| Credential scan of every file changed this window | 0 hits (no PAT/token shapes anywhere in the diff) |
| Untracked artifacts | empty (`.gitignore` covers the untracked audit log) |
| Working tree | clean at each commit |
| Layering guard `test_no_phase3_imports_in_pit` | PASS — the new `pit/immutable.py` lives inside PIT precisely because the guard forbids cross-layer imports from pit modules (verified live during migration) |
| Cross-process identity hashes / red-team matrix | unchanged and passing (suite green; hash compatibility of frozen containers proven by test + canonical-serialization equality) |
| PAT rotation | still owed by the operator (exposure #4, verified STILL ACTIVE in P0) — unchanged disposition |

## 6. Contract-convention notes (for the P2 auditor)

1. **BUG-003 signed-order contract.** `check_order`'s `units` is now
   the order's SIGNED size; `current_units` the signed position. The
   pre-paper §5.3 spec's example "+100/−140→−40 pass with max ≥ 40"
   additionally requires max ≥ 140 under the spec's OWN order-size
   rule (`abs(signed_units) > max` ⇒ breach); with max=100 the −140
   order is rightly rejected by order size. The test matrix uses
   order-size-conformant numbers and documents this reading. All
   existing callers used positive-only units (verified by grep), so no
   caller semantics changed.
2. **BUG-004 input discrimination.** Status-aware checks engage when
   `orders` is a `GatewayRecord` sequence (duck-typed: has `.order` +
   `.status`); plain `PaperOrder` input keeps legacy status-blind
   behavior with the docstring saying exactly that. The BEFORE repro
   passed plain orders, so its "reproduction" of D is a convention
   artifact — the corrected-convention probe (records input) is closed.
3. **BUG-005 accepted residual risk.** The unkeyed chain can still be
   re-forged end-to-end by an attacker with full write access
   (pinned by `test_unreforged_chain_threat_model_documented` as the
   honest boundary). The keyed-MAC custody decision remains a
   registered pending HUMAN decision — P1 deliberately did not make it.
4. **Decimal dust.** The limit-fill cost decomposition is exact by
   construction (`gap := price − base`); under 28-digit Decimal
   division the charged stack may exceed `half_spread + impact` by a
   final-digit rounding dust — documented in the simulator comment; no
   guard is enforced there because it would spuriously reject
   legitimate fills.

## 7. Remaining risks / open items

| Item | Class | Disposition |
|---|---|---|
| `schemas.py` BUG-008 quartet (`Dataset.candles`, `ProvenanceRecord.transformation_history`, `ValidationResult.details`, `ProviderConfig.instrument_allowlist`) | rule-1 exclusion | Untouched: the file is SUB-18 manifest-pinned and rule 1 forbids manifest edits. Requires a manifest-refresh authorization (or runtime-boundary adapters, per the pre-paper §5.8 note) — registered as the follow-up |
| strategy/ BUG-008 fields (9) | frozen contract | Excluded by design; adapters will wrap at the runtime boundary (pre-paper §5.8) |
| Unkeyed audit chain (BUG-005 residual) | accepted threat model | Keyed-MAC custody decision pending (human) |
| PAPER-BLK-1..6 (risk wiring, persistence, partial-fill redesign, ledgers, SL/TP, lineage) | structural | NOT in the P1 window — unchanged; PAPER_READY remains **NO** |
| RT-F1..F6, RT-F9..F12, RT-F14/F15, MC-1..12, ARCH-F2/F5/F7..F12, H-1, F-11 | registered findings | Dispositions UNCHANGED by rule 3 (this window touched none of them; RT-F5 in particular remains OPEN — trip/reset events still emit no audit records; only the construction-time opt-out warning was added under ARCH-F1) |
| CLI status values are current-state truths | maintenance note | The seven dimensions must be updated when underlying reality changes (P4+); they are exported as `STATUS_DIMENSIONS` for that purpose |
| `trip_on_breach=False` warning noise | cosmetic | 25 suite-time warnings by design (non-silent opt-out); no test treats warnings as errors |

**Findings still OPEN (outside the window, unchanged):** every
registered finding not listed in §1 — see the authoritative registers
(`PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` §2,
`TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` §12, the architecture readiness
audit ARCH-F table). PAPER_READY = NO; LIVE = NOT_AUTHORIZED;
ADVANCED_ML = DEFERRED; REAL_DATA_VALIDATION = BLOCKED;
VERIFIED_YEARS = 0; H-1 = OPEN/CONTAINED.

## 8. Exact commit/tree state

| Field | Value |
|---|---|
| Branch | `phase-4a/4a1-architecture-correction` |
| Correction commit | **1277331** — `fix(P1): authorized correction window — BUG-001..009 + ARCH-F1/F3/F4/F6 + RT-F7/F8/F13` (29 files: 21 source + 1 new module + 3 test files + 4 packaging/spec, +~2,950/−~180) |
| Docs commit | this commit (report + index + brief) |
| Remote state | `origin/main` = `origin/phase-4a/4a1-architecture-correction` = **5079484** — the P1 commits are **LOCAL ONLY** (rule 11: no push; push requires separate authorization) |
| Working tree | clean after each commit; untracked empty |
| Push instruction (when separately authorized) | `git push <auth> phase-4a/4a1-architecture-correction` then fast-forward `main` to the same commit and push — same two-ref convention as every prior cycle |

## 9. NO TRADING IMPLEMENTATION PERFORMED

No LSTM, Transformer, Ensemble, RL, autonomous trading, paper-runtime,
broker integration, live trading, daemon, scheduler, event bus,
composition root, or any P4-scope feature was implemented. This window
corrected registered defects in existing non-frozen components only.
The staged program remains: **P2 independent re-audit (READ ONLY) is
the next authorized stage** — it must independently verify every §1
row before any P3/P4 authorization.

## 10. P1 final response block

```text
FINDINGS ADDRESSED:      16/16 authorized (BUG-001..009, ARCH-F1/F3/
                         F4/F6, RT-F7/F8/F13) — all corrected with
                         objective evidence; closure verdicts deferred
                         to P2 per rule 10.
FILES CHANGED:           29 files in commit 1277331 (21 modified
                         source, 1 new module pit/immutable.py, 3
                         test files, 4 packaging/spec) + 3 docs in
                         this commit. Zero frozen/manifest-pinned
                         files touched.
TESTS ADDED/CHANGED:     +82 new (test_p1_correction_window.py);
                         3 pinned tests amended (documented §3).
TESTS PASSED/FAILED:     1141/1141 passed, 0 failed, 3x deterministic.
FROZEN CONTRACT:         INTACT — 11/11 blobs, 13/13 manifest,
                         design doc untouched (pre+post commit).
SECURITY:                secret scan 0/263 tracked files; 0 credential
                         shapes in the diff; PIT layering guard PASS;
                         FS-06 containment re-verified; kill-switch
                         hardening (ARCH-F1) in force.
REMAINING RISKS:         §7 (schemas.py BUG-008 quartet deferred by
                         rule 1; unkeyed chain accepted threat model;
                         structural PAPER-BLK register unchanged).
FINDINGS STILL OPEN:     all non-window registered findings, unchanged
                         dispositions (§7).
COMMIT/TREE STATE:       1277331 + docs commit, branch
                         phase-4a/4a1-architecture-correction, tree
                         clean, remote untouched at 5079484 (NOT
                         pushed — rule 11).
TRADING IMPLEMENTATION:  NONE.
NEXT AUTHORIZED STAGE:   P2 — INDEPENDENT CORRECTION RE-AUDIT
                         (READ ONLY; verify §1 independently; run the
                         full suite, gates, and both AFTER-evidence
                         scripts; do not trust this report's summaries).
```
