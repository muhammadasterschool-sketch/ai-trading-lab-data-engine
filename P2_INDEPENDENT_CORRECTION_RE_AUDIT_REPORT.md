# P2 INDEPENDENT CORRECTION RE-AUDIT REPORT

```text
Document Type:  Independent re-audit report (P2 of the staged readiness
                program P0–P8) — READ-ONLY audit artifact; no
                implementation, test, or frozen file was modified by
                this audit (only this report + brief/index updates)
Phase:          P2 — INDEPENDENT CORRECTION RE-AUDIT
Authority:      C — AUDIT EVIDENCE (independent verification record;
                produced under the operator's P2 master prompt)
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-09
Supersedes:     none (first independent re-audit record)
Superseded By:  —
Source Evidence: git @ 95e0745 (P1 docs HEAD; correction commit 1277331);
                fresh test runs (2x full suite + 8 category subsets);
                AFTER/BEFORE probe scripts re-executed; first-hand reads
                of every correction diff; security scans re-executed;
                credential status check (HTTP 200, 2026-10-09)
```

> **P2 mode compliance.** This stage was executed READ-ONLY per the P2
> master prompt §5: the audit inspected diffs, source, tests, history,
> and documentation; ran tests, static scans, and reproducibility
> checks; and produced this report as an audit artifact. No finding
> status was changed to satisfy an outcome; no closure was accepted on
> documentation or self-assertion alone. Every verdict below required:
> required condition + objective evidence + independent verification +
> regression safety + governance compliance (§7 forensic principle).

---

## 1. Executive summary

P2 independently re-audited the P1 correction window (commits `1277331`
source + `95e0745` docs, both verified LOCAL-ONLY at audit start) over
the 16 authorized findings: BUG-001..009, ARCH-F1/F3/F4/F6,
RT-F7/F8/F13.

**Outcome: 15/16 findings CLOSED with objective, independently
re-verified evidence; 1/16 PARTIAL (BUG-008 — in-scope migration
complete and runtime-verified; 13 of the original 43 fields remain
mutable under explicit frozen-contract / SUB-18-manifest immunity,
registered as a rule-compliant follow-up).** No REGRESSED finding. No
cosmetic closure. Frozen Phase 3 intact (11/11 blobs, 13/13 manifest,
design doc untouched by P1). Full suite 1,141/1,141 (2 fresh
deterministic runs this audit). No unauthorized trading-runtime
implementation of any kind exists.

Two audit-environment observations are recorded transparently: (a) the
working tree carries a **mode-only sweep** (262 files `644→755`,
content diff `0 insertions / 0 deletions` — byte-identical to HEAD;
introduced between sessions, not by P1; left unrepaired per READ-ONLY
mode); (b) the operator's chat-exposed GitHub PAT was re-exposed in
the P2 prompt itself (**exposure #5**) and was re-verified **STILL
ACTIVE** via API — rotation remains an OPEN operator obligation.

**P2 VERDICT: CONDITIONAL PASS** (§17) — corrections verified; the
conditions are operator-side: credential rotation, the BUG-008 deferred
fields' separate authorization path, and the keyed-MAC custody decision.

## 2. Repository baseline

| Item | Verified value (P2, 2026-10-09) |
|---|---|
| Repository | `github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine` (local `/home/z/my-project/workspace/repo`) |
| Branch | `phase-4a/4a1-architecture-correction` |
| HEAD | `95e07458d7685e20cbc8167527babd84bcfdfd70` |
| Remote refs | `origin/main` = `origin/phase-4a/…` = `5079484` (verified via anonymous `ls-remote`; repo public) |
| Unpushed commits | **2** (`1277331` correction + `95e0745` P1 docs) — consistent with P1 rule 11 (no push) |
| Tracked files | 264 (262 at P0 + P1 report + `tests/test_p1_correction_window.py`) |
| Working tree | 262 files mode-only modified (`644→755`); **content 0/0** vs HEAD; untracked empty; stash empty |
| Tests | **1,141/1,141** (fresh run 1: 14.05s; determinism run 2 `-p no:cacheprovider`: 14.34s) |
| Frozen Phase 3 | 11/11 strategy blobs byte-identical to `main@13fdc7e`; SUB-18 manifest 13/13 sha256 |
| Trading runtime implementation | **NONE** (no LSTM / Transformer / model-Ensemble / RL / autonomous / broker / live code) |
| Commit chain (P1 window) | `5079484` → `1277331` (29 files, +2,073/−98) → `95e0745` (3 docs: P1 report + index v1.5.0 + brief v1.10.0) |

The expected baseline in the P2 prompt ("HEAD 5079484, 1,059 tests,
262 files, tree clean") was **stale** — it described the pre-P1 state.
Actual values are reported above per §4 ("do not blindly trust;
re-verify"). P1 was in fact executed (worklog task
`p1-correction-window-1` + the two local commits are the ground truth).

## 3. Git / commit state

- `git status --porcelain`: 262 ` M ` lines, **zero** staged, **zero**
  untracked, zero stash entries. Every modified file differs from HEAD
  **only in file mode** (`old mode 100644 / new mode 100755`); the
  content diff across all 262 files is `0 insertions(+), 0 deletions(-)`
  (`git diff --shortstat`). This is an environment-level permission
  sweep that occurred between sessions (all files that existed before
  the sweep, including the P1-created report, are affected; the
  content is byte-identical to the committed state). Per READ-ONLY
  mode P2 did **not** repair it; remediation options for the operator:
  `git config core.filemode false` (make git ignore the bits) or a
  one-time `chmod` normalization commit. Recorded as observation
  **OBS-1**; it is cosmetic, content-neutral, and affects no gate
  except the tree-cleanliness check (see §7's gate note).
- `.git/config`: 0 credential-shaped strings (verified again this
  audit); remote URL clean (no embedded token).
- History integrity: no rewrite — the P1 commits sit linearly on
  `5079484`; the full commit chain matches the worklog records.
- `1277331` touches **zero** `strategy/` files, **zero**
  `docs/strategy_engine_design.md`, **zero** `src/data_engine/schemas.py`
  (the manifest-pinned module) — verified from the commit's file list.

## 4. Phase 3 frozen integrity

| Check | Method (independent) | Result |
|---|---|---|
| 11 strategy blobs | `git rev-parse 13fdc7e:<f>` vs `HEAD:<f>` (blob-level, immune to worktree mode bits) | **11/11 identical** |
| SUB-18 manifest (13 pins) | sha256 of working-tree files vs the recorded manifest (content byte-identical to HEAD) | **13/13 match** |
| `docs/strategy_engine_design.md` | `git diff 13fdc7e..HEAD -- <doc>` | **One metadata line**, changed in `df44d27` (the branch's forensic-baseline commit, pre-P0/P1): `IMPLEMENTATION STATUS: COMPLETE…` → `NO-GO…` — the documented Phase-4A.1 baseline governance marker (Blocker-2 record), **not** a P1 change; disclosed for completeness |
| History rewrite | commit chain inspection | none |

**FROZEN CONTRACT INTEGRITY: INTACT.** No HALT condition triggered: the
material frozen artifacts (strategy implementation blobs + manifest)
are byte-identical; the one-line doc-status difference predates the
entire P0–P2 program and is part of the branch's own recorded
governance baseline.

## 5. P1 scope verification

Authorized scope (operator P1 authorization, verbatim from the P1
report): READ+WRITE only over BUG-001..009 + ARCH-F1/F3/F4/F6 +
RT-F7/F8/F13; frozen Phase 3 untouched; no new trading runtime;
smallest safe changeset; tests per correction; full regression +
security; before/after evidence; no closure self-declaration; no push.

Verified against the actual diff of `1277331` (29 files):

- **In-scope corrections only**: every changed source file maps to an
  authorized finding (mapping re-derived independently from the diffs —
  see §6; it matches P1 report §2's map).
- **Zero frozen-file changes** (see §4); `pit/immutable.py` is a NEW
  module inside the PIT package (the layering guard
  `test_no_phase3_imports_in_pit` passes — re-run in the suite).
- **No scope expansion**: no new trading feature, no daemon, no
  scheduler, no event bus, no broker surface, no ML framework
  dependency (runtime deps remain pydantic/numpy/pandas only; pytest is
  now dev-only — RT-F13). The `paper/` package edits are corrections to
  the pre-existing (Phase-11-era) deterministic simulator library, not
  a P4 paper runtime.
- **The 3 pinned-test amendments** (test_pt_04, test_rk_01, test_rk_03)
  were each read first-hand: each previously **pinned the defective
  behavior**; each amendment asserts the corrected behavior (details in
  §6 rows). No unrelated test was weakened.
- **Push discipline**: P1 did not push (remote still at `5079484` at
  P2 start) — rule 11 honored.

## 6. Finding-by-finding re-audit

Legend — **Evidence**: first-hand code-diff read + probe re-execution;
**Tests**: re-run this audit; **IV**: independent verification beyond
the P1 report's own claims. Verdicts per §7: CLOSED only when the
register's closure condition is objectively satisfied.

| Finding | Original condition (register) | Required closure condition | Evidence found (P2, first-hand) | Tests | Independent verification | Verdict |
|---|---|---|---|---|---|---|
| **BUG-001** CRITICAL | BUY limit fills ABOVE the limit (+spread+impact on the limit), SELL below; pinned by `test_pt_04` | Fills never through the limit; costs charged only up to the limit; exact accounting identity; property test; pin amended (§5.1) | `simulator.py::_fill_limit`: BUY `price=min(limit, open+hs+impact)`, SELL `price=max(limit, open−hs−impact)`; `base=min/max(limit,open)`, `gap:=price−base`, `impact_charged=min(impact,gap)`, `spread_charged=gap−impact` — identity exact by construction; MARKET branch unchanged; probe A/A2 closed | 7 tests incl. **300-case randomized property test**; amended `test_pt_04` asserts `price ≤ limit`, passive fill AT limit with zero costs, no-fill for non-crossing | diff read; AFTER-probe re-executed (0/17 defective); BEFORE probe A/A2 no longer reproduces | **CLOSED** |
| **BUG-002** CRITICAL | Flip carries old side's basis into the new opposite side; P&L doubles in error | Residual opens at the flip fill's all-in price; same-sign reduction preserves basis; full close → 0; economics matrix (§5.2) | `models.py::apply_fill`: sign-flip branch sets `average_cost = price_incl`; reduction branch preserves; zero branch resets — exactly the §5.2 spec | 5 tests (long/short flip, economics equality, reduction, full close) | diff read; probes B/B2 no longer reproduce | **CLOSED** |
| **BUG-003** CRITICAL | Additive `abs(order)+abs(current)` rejects risk-REDUCING orders and TRIPS the kill switch; pinned by `test_rk_01` | Signed netting `projected=current+signed(units)`; breach iff `\|projected\|>max` OR `\|units\|>max`; reductions/closes never trip; pin amended (§5.3) | `engine.py::check_order`: `projected = signed_current + units`; both breach rules implemented with record+trip only on true breach; finite-input guards added | 9 tests (netting matrix, no-trip-on-reduction, order-size rule, documented semantics) | diff read; **production call-site audit re-done**: exactly ONE src caller (`benchmarks/runner.py:455`, positive-only units) — signed contract compatible; amended `test_rk_01` is same-sign outcome-identical; BEFORE probe C/C2 "reproduce" only under the pre-correction **unsigned-magnitude** convention (probe passes `+100` for a sell — under the corrected signed contract that is a BUY add-on and rightly breaches) | **CLOSED** |
| **BUG-004** HIGH | Docstring check-2 "every filled order has its fill" unimplemented; status-blind signature | Status-aware reconciliation: FILLED⇒has fill, non-FILLED⇒no fill; legacy path honestly documented (§5.4) | `gateway.py::reconcile`: GatewayRecord duck-typed input builds `status_by_order`; missing-fills and ghost-fills both raise `ReconciliationError`; plain-order path documented status-blind | 6 tests (missing-fill, ghost on CANCELLED/SUBMITTED, clean pass, legacy pass, orphan still raises) | diff read; AFTER probe D closed; BEFORE probe D "reproduces" only via plain-order (status-blind) input convention — verified first-hand | **CLOSED** |
| **BUG-005** MEDIUM | Payload stored by caller reference; `entries` shallow over live dicts; chain unkeyed/re-forgeable | Deep-copied entries; `timestamp`/`component`/`event_id` fields; keyed-MAC decision **registered as a human decision**, not silently chosen (§5.5) | `gateway.py::AuditLogger`: `log()` deep-copies payload; `entries` returns deep copies; new fields chained into the hash; wall-clock timestamps explicitly excluded from Phase-4 identity (FS-21 convention) | 5 tests incl. `test_unreforced_chain_threat_model_documented` — which **demonstrates** the full-rewrite re-forge remains possible (honest boundary) | diff read; probe E closed; residual re-forge = the closure condition's own accepted threat model pending the registered human keyed-MAC decision | **CLOSED** (keyed-MAC custody carried as open human decision — see §13/§15) |
| **BUG-006** MEDIUM | CLI printed blanket `OPERATIONAL` over a library-only state | Seven truthful dimensions (§5.6) | `cli.py`: `STATUS_DIMENSIONS` = LIBRARY_HEALTH OK / RUNTIME_HEALTH ABSENT / PAPER_READINESS BLOCKED / LIVE_AUTHORIZATION NOT_AUTHORIZED / DATA_READINESS SYNTHETIC_ONLY/REAL_BLOCKED / MODEL_READINESS 0_APPROVED / RECONCILIATION_HEALTH NOT_WIRED — each matches the independently verified repository reality | 2 tests (dimensions + printed output) | diff read; values cross-checked against actual governance state (no runtime; 0 approved models; paper blocked) | **CLOSED** |
| **BUG-007** LOW | Bar ordering unvalidated; unsorted/duplicate bars silently mis-locate the submission bar | Strictly-increasing validation; violations raise (§5.7) | `simulator.py::_validate_bar_order` raises `SimulationError` on `ts <= previous`; runs before the scan | 3 tests | diff read; probe closed | **CLOSED** |
| **BUG-008** LOW | 43 mutable dict/list fields inside frozen=True models | Prioritized migration to immutable/defensively-copied containers; strategy fields excluded by design (§5.8) | `pit/immutable.py` (NEW): `FrozenDict`/`FrozenList` dict/list subclasses whose mutators raise `TypeError`; `freeze()` recursive; construction deep-copies; equality/JSON/canonical-serialization preserved → hash stability; 25 in-scope fields migrated across 14 modules; **runtime sweep re-executed by P2: 31/31 in-scope mutations BLOCKED**; exclusions: strategy ×9 (frozen contract, per §5.8's own design), schemas.py ×4 (SUB-18 manifest pin, rule 1), frozenset/enum ×5 (sweep false positives) | 13 tests (per-model mutation matrix, serialization identity, hash-unchanged) | diff read; sweep re-run; **residual: 13 registered fields remain mutable** (9 frozen + 4 manifest-pinned) — deferred under higher-priority immunity rules, follow-up registered (manifest-refresh authorization or runtime-boundary adapters) | **PARTIAL** (in-scope closure complete; residual is rule-blocked, registered, not silent) |
| **BUG-009** LOW | NaN/inf equity points silently skipped | Fail closed on non-finite inputs (§5.9) | `gateway.py::AnalyticsEngine::_require_finite` guards `total_pnl`/`max_drawdown`/`sharpe` | 6 tests (NaN/inf per function + finite behavior unchanged) | diff read; probe closed | **CLOSED** |
| **ARCH-F1** MEDIUM | Kill-switch reset unauthenticated — any caller (incl. AI) could clear a tripped switch | Reset requires identified human principal (authorized window note) | `engine.py::reset_kill_switch(principal, principal_kind)`: non-string/blank principal refused; `principal_kind != "human"` refused with `RiskViolationError`; trip stays unprivileged (fail-safe direction); `trip_on_breach=False` opt-out now warns + introspectable property | 8 tests incl. **AI-principal-refused** matrix | diff read; note: RT-F5 (trip/reset audit **records**) is a distinct registered finding outside the P1 list and remains OPEN — correctly untouched | **CLOSED** (RT-F5 remains a separate OPEN finding) |
| **ARCH-F3** MEDIUM | `EvidenceProvenance` used at ingestion.py:191, never imported → NameError | Import + working provenance build | `from data_engine.evidence import EvidenceProvenance` added; probe confirms resolution | 1 test | diff read; probe closed | **CLOSED** |
| **ARCH-F4** MEDIUM | `datetime`/`UTC` never imported in quant_boundary.py → NameError (reproduced pre-P1) | Imports added; both paths execute | `from datetime import datetime, UTC` at quant_boundary.py; default-factory + `mark_complete` paths tested | 2 tests | diff read; probe F closed | **CLOSED** |
| **ARCH-F6** LOW | Dormant ingestion path hashed via wall-clock-contaminated `Candle.to_hash()` (H-1/F-04 family) | Deterministic raw hash; H-1 containment preserved; frozen Candle untouched | `ingestion.py::_compute_raw_hash`: canonical market fields via PIT `deterministic_hash`, **`provider_timestamp` excluded**; frozen Candle model untouched | 3 tests (identical-data→identical-hash; provider_timestamp-irrelevance; different-data→different-hash) | diff read; H-1 containment posture re-checked (Phase-4 identity still prohibited from `to_hash()` at 3 layers — unchanged) | **CLOSED** |
| **RT-F7** LOW/MED | `check-boundary` called `assert_deterministic` → always exit 1 | Verify semantics; exit 0 on valid types | `cli.py`: `is_deterministic_required` branch prints DETERMINISTIC confirmation (exit 0); non-required types get an honest no-enforcement message; invalid input keeps the error path | 3 tests (exit codes + usage) | diff read; probe G closed | **CLOSED** |
| **RT-F8** LOW/MED | `ingest_from_file` dead path: no `approved_data_root` → FS-06 fail-closed before any read; invalid `asset_class=None` fallback | Live path through FS-04/FS-06/FS-14; honest fallback | `ingestion.py`: data dir derived from caller's `file_path`; `approved_data_root=str(data_dir)` (FS-04); `instrument_allowlist=[instrument]` (FS-14); explicit `{instrument}_{timeframe}.csv` naming contract (mismatch fails closed); `_fallback_instrument` uses the repository classifier and **fails closed for unclassifiable symbols** (replaces invalid `asset_class=None`) | 4 tests incl. end-to-end temp-CSV ingest + no-root fail-closed + security-layers-still-enforced | diff read; probe closed | **CLOSED** |
| **RT-F13** LOW | pytest a RUNTIME dependency; `src/audit.log` tracked; `.gitignore` gaps | pytest dev-only; audit.log untracked+ignored | `pyproject.toml`: pytest removed from runtime deps → dev extras `>=9.1.1`; `uv.lock` relocked; `src/audit.log` untracked (removed from index); `.gitignore` + `src/audit.log`/`*.log`; WP-12 CI spec install line updated to `--extra dev`; zero pytest imports in src (tested) | 4 tests | diff read; gate untracked-check empty; `uv run --frozen` environment functional (all P2 runs used it) | **CLOSED** |

**Verdict tally: 15 CLOSED · 1 PARTIAL (BUG-008) · 0 OPEN · 0 BLOCKED ·
0 REGRESSED · 0 NOT-APPLICABLE.**

## 7. Test evidence

| Run (all fresh, this audit) | Command (form) | Expected | Actual | Result |
|---|---|---|---|---|
| Full suite #1 | `uv run --frozen pytest -q` | 1,141 pass | **1,141 passed** (14.05s, 30 warnings — the ARCH-F1 opt-out warnings, by design) | PASS |
| Full suite #2 (determinism) | `… -p no:cacheprovider` | 1,141 pass | **1,141 passed** (14.34s) | PASS |
| P1 window (targeted) | `pytest tests/test_p1_correction_window.py` | 82 pass | **82 passed** (1.58s) | PASS |
| PIT | `test_pit.py + test_pit_view.py` | pass | **195 passed** | PASS |
| Identity/hash | `test_prediction_identity_provenance.py + test_prediction_artifact_verification.py` | pass | **33 passed** | PASS |
| Red-team | `test_redteam.py + test_prediction_redteam_matrix.py` | pass | **61 passed** | PASS |
| Risk/safety | `test_risk_portfolio.py` | pass | **11 passed** | PASS |
| Paper (incl. amended pins) | `test_paper_trading.py` | pass | **10 passed** | PASS |
| Governance/provenance/ledger | `test_research_governance.py + test_prediction_registry_ledger.py` | pass | **21 passed** | PASS |
| Infra/security surfaces | `test_infra.py` | pass | **8 passed** | PASS |
| AFTER-evidence probe | `uv run --frozen python scripts/pp_p1_after_evidence.py` | 0/17 defective | **ALL PROBES CLOSED** (exit 0) | PASS |
| BUG-008 runtime sweep | `uv run --frozen python scripts/pp_bug008_runtime_sweep.py` | 31/31 blocked | **31/31 BLOCKED** | PASS |
| BEFORE-evidence script (historical) | `uv run --frozen python scripts/pp_bug_repro.py` | 8/11 not reproducing | **8/11 not reproducing**; C/C2/D reproduce **only under pre-correction calling conventions** (unsigned magnitudes / status-blind plain orders — both conventions verified first-hand in the probe source; corrected-convention equivalents are probe-closed) | PASS (as documented) |
| Final gate | `python3 scripts/final_gate_verify.py` | 5/5 | **4/5** — frozen 11/11 PASS · manifest 13/13 PASS · secrets 0/264 PASS · untracked empty PASS · tree-clean **FAIL: OBS-1 mode-only sweep** (262 files, content 0/0) | PASS with documented environment observation |

No failure was hidden: the single gate FAIL is the OBS-1 mode sweep,
which is content-neutral (proven by `git diff --shortstat` =
0 insertions/0 deletions) and is not attributable to P1 (the tree was
clean at P1's commits per its report §8; the sweep affects files that
existed before it, including P1's own new files).

## 8. Security evidence

| Check | Method | Result |
|---|---|---|
| Working-tree credential shapes | ripgrep `github_pat_[A-Za-z0-9_]{20,}` + 6 secret families across all tracked files | **0 hits / 264 files** (gate re-scan) |
| `.git/config` / git config | pattern scan | **0 tokens** |
| Full history — real token shapes | `git log --all -G'github_pat_[A-Za-z0-9_]{20,}'` | **0 commits** |
| Full history — string family | `git log --all -S'github_pat_'` | 2 commits, **both documentation-only**: `02496b7` (WP-12 CI spec's own scan regex) and `5079484` (P0 report describing the token TYPE — value withheld). No credential value anywhere in history |
| Dangerous-op surface | `subprocess|pickle|eval(|exec(|os.system|shell=True` over `src/` | **0 hits** |
| Network/broker surface | vocabulary scan (`broker|mt5|metatrader|websocket|live_trading|lstm|transformer|…`) | **0 implementations** — matches are safety banners ("NO REAL MONEY. NO BROKER CREDENTIALS."), docstrings, and the pre-existing statistical `ensemble_band` (dispersion function over caller-provided probabilities, §19 of the prediction spec) |
| Filesystem traversal / symlinks | standing FS-01..22 suite (`test_infra.py` + containment tests) | PASS (8/8 + suite green); RT-F8's revived path re-tested with FS-04/06/14 invariants |
| **Exposed credential status** | API `GET /user` with the operator-provided PAT (transient env var; value never printed/stored/committed) | **STILL ACTIVE — HTTP 200, login `muhammadasterschool-sketch` (repo owner). Exposure #5 (re-pasted in the P2 prompt). Rotation remains owed by the operator — RISK OPEN** |

## 9. PIT verification

- PIT suites re-run green: 195 tests (`test_pit.py` + `test_pit_view.py`)
  covering serialization canonicality, availability/revision/tiebreaker
  semantics, immutable sidecars, experiment identity.
- PIT layering guard (`test_no_phase3_imports_in_pit`) — PASS with the
  NEW `pit/immutable.py` inside the package (placement is itself
  guard-compliant).
- ARCH-F6 correction re-verified PIT-pure: the raw hash uses
  `deterministic_hash` over canonical fields, excludes the
  wall-clock `provider_timestamp`, and does not touch the frozen
  Candle model.
- No PIT semantic changed by P1: no `pit/` semantic module was modified
  except `contract.py`/`revision.py` container-freeze migration
  (BUG-008) whose serialization/hash byte-compatibility is proven by
  tests (`test_frozen_containers_serialize_identically`,
  `test_knowledge_hash_unchanged_by_freeze` — both re-run green).

## 10. Identity / hash verification

- Frozen Phase 3 identity: 11/11 blobs byte-identical to `13fdc7e`
  (blob-level `git rev-parse` comparison — independent of worktree
  state).
- SUB-18 manifest: 13/13 sha256 pins match.
- Cross-process identity hashes (`disc20.`/`know42.`/`bmk30.`/`pred.`)
  unchanged and passing (suite green; the frozen-container migration
  preserves hash bytes — empirically pinned by the P1 tests re-run
  this audit).
- Determinism: full suite ×2 (cache disabled on run 2) — identical
  1,141/1,141 results.

## 11. Governance verification

| Invariant | State (re-verified) |
|---|---|
| PRED-F1/F2/F3 | CLOSED (tests re-run green) |
| ADVANCED_ML | DEFERRED (no ML framework, no LSTM/Transformer/RL code) |
| REAL_DATA_VALIDATION | BLOCKED (no real datasets; SYNTHETIC-only) |
| VERIFIED_YEARS | 0 |
| H-1 | OPEN / CONTAINED (containment preserved by ARCH-F6 correction design; ratification still a human decision) |
| PAPER_READY | **NO** (PAPER-BLK-1..6 structural blockers unchanged — outside the P1 window by design) |
| LIVE | NOT_AUTHORIZED (never self-authorizable) |
| Stage locks | P2 executed under explicit authorization; **P3 NOT AUTHORIZED**; P4–P8 LOCKED |
| Out-of-window findings | RT-F1..F6, RT-F9..F12, RT-F14/F15, MC-1..12, ARCH-F2/F5/F7..F12, F-11, RT-F5 — dispositions UNCHANGED (verified: no out-of-window source change in `1277331`) |

## 12. Regression assessment

- **No regressions found.** Suite grew 1,059 → 1,141 with zero removals
  (3 amendments in place, each verified as an honest defect-pin
  replacement — §6).
- Same-sign risk callers are outcome-identical under signed netting
  (verified: the only production `check_order` call site passes
  positive-only units).
- MARKET-order fill semantics byte-identical (unchanged branch).
- Frozen-container migration preserves serialization and hashes
  (empirical tests green).
- The only new runtime behaviors are fail-closed additions (bar-order
  validation, finite guards, status-aware reconciliation raises,
  filename contract, classifier fail-closed fallback) — each covered
  by negative tests.

## 13. Open risks

| ID | Risk | Owner |
|---|---|---|
| **CRED-ROTATION** | Chat-exposed GitHub PAT **STILL ACTIVE** (verified HTTP 200 this audit; exposure #5). Repository itself is clean; the risk lives in the credential, not the code | **Operator — immediate rotation/revocation** |
| **BUG-008-RESIDUAL** | 13 frozen/manifest-pinned mutable fields remain (strategy ×9, schemas.py ×4); closure requires a separate manifest-refresh authorization or runtime-boundary adapters | Future authorized window (P4-era) + human decision |
| **KEYED-MAC** | Unkeyed audit chain remains re-forgeable end-to-end by a full-history rewrite (demonstrated by test; accepted threat model) — keyed-MAC custody decision pending | Human |
| **OBS-1** | Worktree mode-only sweep (262 files `644→755`, content 0/0) — environment artifact; breaks the tree-clean gate cosmetically; recommend operator normalization (`core.filemode false` or a chmod commit) | Operator (cosmetic) |
| PAPER-BLK-1..6 | Structural pre-paper blockers (risk wiring, persistence, partial fills, ledgers, SL/TP, lineage) — unchanged, outside window | P4 scope |
| Out-of-window register | RT-F5 (trip/reset audit records) and the other registered findings — unchanged | Future windows |

## 14. Closed findings

Closed by this re-audit (objective closure condition satisfied +
independent verification): **BUG-001, BUG-002, BUG-003, BUG-004,
BUG-005, BUG-006, BUG-007, BUG-009, ARCH-F1, ARCH-F3, ARCH-F4,
ARCH-F6, RT-F7, RT-F8, RT-F13 — 15 findings.**

Not closed: **BUG-008 = PARTIAL** (see §6 row: in-scope complete,
13 fields rule-deferred with registered follow-up).

Pre-existing closures re-confirmed intact: PRED-F1/F2/F3 (tests green).

## 15. Remaining blockers

| ID | Why open | Required evidence |
|---|---|---|
| CRED-ROTATION | Credential active; exposure #5 | Operator rotation + negative API check (401) in a future audit |
| BUG-008-RESIDUAL | 13 fields under frozen/manifest immunity | Separate authorization (manifest refresh or P4 runtime adapters) + migration + runtime sweep green |
| KEYED-MAC | Custody policy undecided | Human decision record + keyed-chain implementation + tests |
| PAPER-BLK-1..6 | Structural (pre-P4) | P4 paper-runtime construction + E2E evidence |
| P3 Stage-0 decisions | Real data source / WP-12 CI / H-1 ratification | Explicit human decision records |
| OBS-1 | Cosmetic environment artifact | Operator normalization (no functional impact) |

## 16. Authorization status

| Stage | Status |
|---|---|
| P1 correction window | EXECUTED (verified); commits local-only at P2 start |
| **P2 (this audit)** | **AUTHORIZED & EXECUTED** (operator master prompt, READ-ONLY) — complete with this report |
| Push of P1+P2 commits | **Explicitly authorized by the operator's appended live instruction** ("push everything + brief doc"), scoped here to documentation/audit artifacts on both remote refs per the standing two-ref convention; implementation was not modified by this audit. Token used one-off (transient shell variable), never stored/echoed/committed; `.git/config` re-verified 0 tokens after push |
| P3 — Stage-0 | **NOT AUTHORIZED** (requires explicit operator grant; the P2 verdict does not authorize it) |
| P4–P8 | LOCKED |

## 17. Exact next gate

**P3 — STAGE-0 GOVERNANCE DECISIONS** (real data source · WP-12 CI
enablement · H-1 ratification · approval-owner assignments) — to be
entered ONLY on explicit operator authorization. Standing operator
obligations ahead of any P3/P4 work: rotate the exposed PAT; decide
keyed-MAC custody; normalize OBS-1 (optional, cosmetic).

---

## P2 final response block

```text
P2 INDEPENDENT RE-AUDIT RESULT

Repository:   github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine
Branch:       phase-4a/4a1-architecture-correction
HEAD:         95e0745 (P2 docs commit supersedes on push; audit ran at 95e0745)
Working Tree: mode-only sweep OBS-1 (262 files 644→755; content 0/0; untracked empty)
Tracked Files: 264
Tests:        1,141/1,141 (x2 deterministic this audit) + 8 category subsets green
Frozen Phase 3: INTACT — 11/11 blobs, 13/13 manifest; design doc untouched by P1
Security:     repo/tree/history/config CLEAN (0 credentials); exposed PAT STILL
              ACTIVE (HTTP 200, exposure #5) — rotation OPEN, operator-owned
PIT:          VERIFIED (195 tests green; layering guard PASS; ARCH-F6 PIT-pure)
Identity/Hash: VERIFIED (blob-level frozen check; cross-process hashes stable)
Governance:   INVARIANTS PRESERVED; PAPER_READY=NO; LIVE NOT_AUTHORIZED

FINDING CLOSURE TABLE (16)

BUG-001|CLOSED|limit protection verified in diff+probes|7 tests incl. 300-case property|none residual
BUG-002|CLOSED|flip basis = flip all-in price|5 tests|none
BUG-003|CLOSED|signed netting; 1 positive-only prod caller|9 tests|contract note documented
BUG-004|CLOSED|fills-iff-FILLED both directions|6 tests|legacy path honestly blind (documented)
BUG-005|CLOSED|deep-copy + observability fields|5 tests|keyed-MAC decision open (human)
BUG-006|CLOSED|7 truthful dimensions match reality|2 tests|maintenance note
BUG-007|CLOSED|strict bar-order validation|3 tests|none
BUG-008|PARTIAL|25/25 in-scope migrated; sweep 31/31 blocked|13 tests|13 fields rule-deferred (frozen/manifest)
BUG-009|CLOSED|NaN/inf fail closed|6 tests|none
ARCH-F1|CLOSED|human-principal-gated reset; AI refused|8 tests|RT-F5 (audit records) separately OPEN
ARCH-F3|CLOSED|import fixed; probe closed|1 test|none
ARCH-F4|CLOSED|imports fixed; both paths tested|2 tests|none
ARCH-F6|CLOSED|deterministic raw hash, provider_timestamp excluded|3 tests|H-1 ratification still human
RT-F7|CLOSED|verify semantics, exit 0|3 tests|none
RT-F8|CLOSED|FS-04/06/14 live path + honest fallback|4 tests|none
RT-F13|CLOSED|pytest dev-only; audit.log ignored|4 tests|none

OPEN BLOCKERS

CRED-ROTATION|PAT active after exposure #5|operator rotation + 401 re-check
BUG-008-RESIDUAL|13 fields under frozen/manifest immunity|separate authorization + migration + sweep
KEYED-MAC|custody undecided|human decision + keyed chain + tests
PAPER-BLK-1..6|structural, pre-P4|P4 construction + E2E evidence
P3 Stage-0 decisions|no human records yet|explicit decision records
OBS-1|mode-sweep cosmetic|operator normalization (optional)

CLOSED FINDINGS

BUG-001..007, BUG-009, ARCH-F1/F3/F4/F6, RT-F7/F8/F13 (15) — each with
objective condition + evidence + independent verification + regression
safety + governance compliance. BUG-008 PARTIAL (not closed).

REGRESSIONS

None found (1,141/1,141 x2; zero removals; 3 honest pin amendments;
frozen hashes byte-stable).

P2 VERDICT

CONDITIONAL PASS — 15/16 CLOSED, 1/16 PARTIAL (rule-compliant deferral);
no regressions; frozen intact; conditions are operator-side (credential
rotation, BUG-008 residual authorization path, keyed-MAC decision).

NEXT AUTHORIZED STAGE

P3 — STAGE-0

AUTHORIZATION STATUS

P3 NOT AUTHORIZED unless explicitly granted.
```
