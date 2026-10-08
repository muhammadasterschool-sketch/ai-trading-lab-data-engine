# AI Trading Lab — Pre-Paper Bug Forensic and Closure Report

```text
Document Type:  Authoritative consolidated bug register (mandated deliverable
                of the FINAL PRE-PAPER BUG FORENSIC AND CLOSURE Master Prompt
                §26 — the single bug-register authority for the pre-paper phase)
Phase:          Pre-paper closure era (bug forensic mandate)
Authority:      A — CURRENT AUTHORITATIVE (consolidates — and does not
                duplicate — the RT-F/MC registers of
                TRADING_RUNTIME_ARCHITECTURE_AUDIT.md and the ARCH-F register
                of the architecture readiness audit; where those registers
                are re-verified here, this document is the verification
                record of record)
Status:         CURRENT
Version:        1.0.0 (initial forensic baseline)
Last Updated:   2026-10-08
Supersedes:     none (first pre-paper forensic register; prior audit
                documents remain their own authorities by reference)
Superseded By:  —
Source Evidence: git @ e060690 (main = phase-4a/4a1-architecture-correction,
                remote synced, 0 unpushed, tree clean); fresh full-suite run
                1059/1059 (17.72 s); final_gate_verify.py 5/5 PASS
                (11/11 frozen blobs, 13/13 SUB-18 manifest, secrets 0/260,
                untracked empty, tree clean); 11/11 executable reproductions
                (scripts/pp_bug_repro.py — BEFORE evidence); AST §9 sweep
                (scripts/pp_frozen_mutable_sweep.py); first-hand reads of
                paper/, risk/, infra/, knowledge/, cli, quant_boundary
```

---

## 0. Mandate registration, method and ground truth

The operative mandate is the operator-issued **“HERMES / Z.AI — AI Trading
Lab — FINAL PRE-PAPER BUG FORENSIC AND CLOSURE MASTER PROMPT”** (32 sections):
find → reproduce → classify → fix → test → re-audit → close every defect that
could invalidate the upcoming PAPER TRADING runtime, **without starting paper
trading** (§29). Per its own §2 governance rule and the repository's standing
authorization state (`RUNTIME_IMPLEMENTATION_AUTHORIZATION:
PHASE_A_COMPLETE__NEXT_PHASES_GATED`; STAGE 0 fix window = pending HUMAN
decision), this cycle is a **read-only forensic on source**: every defect is
reproduced with executable evidence, its exact fix is prepared, and its
application is registered as an authorization request — **no protected source
was modified** (§2 rule 5).

**Audit method.** (1) Fresh ground truth (git, tests, gates). (2) First-hand
re-verification of every carried finding cited by the mandate (RT-F1..RT-F15,
MC-1..MC-12, ARCH-F1/F2/F3/F4) by source read + grep + execution. (3) Adversarial
deep-dives on the mandate's target areas: limit-order safety (§6), partial
fills (§7), audit-logger mutability (§9), memory persistence (§10), ledger
inventory (§11), traceability (§12), SL/TP (§13), position accounting (§14),
reconciliation coverage (§15), idempotency (§16), state machine (§17), bypass
search (§18), CLI truthfulness (§21), observability (§22). (4) An AST sweep
for mutable containers inside frozen pydantic models. (5) Eleven executable
reproductions persisted outside the repository
(`/home/z/my-project/scripts/pp_bug_repro.py`).

**Ground truth (verified this cycle):**

| Check | Result |
|---|---|
| Repository HEAD | `e060690` — `main` = `phase-4a/4a1-architecture-correction` = both remote refs (`git fetch` + rev-parse; **0 unpushed commits**) |
| Working tree | Clean; zero uncommitted changes |
| Test suite | **1059 / 1059 passed** (fresh run, 17.72 s) |
| Frozen gates | `final_gate_verify.py` **5/5 PASS** (11/11 frozen Phase-3 blobs vs `main@13fdc7e`; SUB-18 manifest 13/13; secret scan 0 hits / 260 files; untracked empty; tree clean). Known cosmetic defect: the script prints a stale cycle label (`e7505d3`) — registered in the runtime audit; the checks themselves execute against the current tree |
| Secret scans | 0 hits (260 tracked files). The operator-exposed GitHub PAT was **never used, echoed, stored, or tested** this cycle (§1 below) |
| Runtime existence | Confirmed ABSENT: no composition root, no event bus, no scheduler, no daemon, no persistence layer in `src/` (re-verified by grep) |
| Governance states | PRED-F1/F2/F3 CLOSED · ADVANCED_ML DEFERRED · REAL_DATA_VALIDATION BLOCKED · VERIFIED_YEARS = 0 · H-1 OPEN/CONTAINED · LIVE TRADING NOT AUTHORIZED — **all preserved; none weakened** |

---

## 1. Security verification (mandate §1)

- The GitHub Personal Access Token repeatedly pasted into the operator
  conversation is treated as **COMPROMISED**. This cycle it was **not** printed,
  stored, copied into any file/`.env`/git-config/source/log/doc, committed,
  tested, or reused. **No push was performed with it.** The operator must
  revoke/rotate it outside this task (standing advisory, re-issued).
- Repository scans: `final_gate_verify.py` secret scan 0/260 files; targeted
  PAT-pattern grep over every file changed this cycle (docs only) = 0 hits.
- No broker credentials, API keys, private keys, or secrets exist in source,
  docs, tests, or this phase's git history (this cycle adds documentation
  only; frozen-blob verification unchanged).
- No credential repair was attempted by inventing replacements.

---

## 2. Prior audit verification (mandate §4)

Classification vocabulary: CONFIRMED / PARTIALLY CONFIRMED / FALSE POSITIVE /
ALREADY FIXED / NEW DEFECT. Every row below was re-verified **first-hand this
cycle** (source read, grep, and/or execution — evidence column names the
method).

### 2.1 RT-F register (from TRADING_RUNTIME_ARCHITECTURE_AUDIT.md v1.0.0)

| ID | Verdict | This-cycle evidence |
|---|---|---|
| RT-F1 risk gate + kill switch unwired from paper order path | **CONFIRMED** | `paper/gateway.py` full read: imports = models + simulator only; `submit()` performs no `check_order`/kill-switch consult |
| RT-F2 `ReconciliationEngine` zero src callers | **CONFIRMED** | grep: definitions + facade re-exports only |
| RT-F3 `AuditLogger` never invoked by gateway | **CONFIRMED** | grep: class def + `__init__` re-export only |
| RT-F4 no persistence in execution domain (kill switch, duplicate protection, audit chains all volatile) | **CONFIRMED** | `gateway.py:62` in-memory `dict`; `engine.py:158-159` volatile flag/records; no disk I/O in `paper/`/`risk/` |
| RT-F5 kill-switch trip/reset emit no audit record | **CONFIRMED** | `engine.py:170-176` read: no `_record()` call on trip/reset |
| RT-F6 two disjoint order/position vocabularies (paper vs frozen strategy), no bridge | **CONFIRMED** | `paper/models.py:41-55` (lowercase, buy/sell, Decimal) vs `strategy/schemas.py` (uppercase, LONG/SHORT, float); no bridging module exists |
| RT-F7 CLI `check-boundary` inverted (always exit 1) | **CONFIRMED + REPRODUCED** | REPRO-G: `check-boundary ema` → exit 1 (`assert_deterministic` raises exactly for deterministic-required types) |
| RT-F8 `ingest_from_file` dead path (FS-06 fail-closed before read; ARCH-F3 later) | **CONFIRMED** | `ingestion.py:195-216` read; `ProviderConfig` built without `approved_data_root` |
| RT-F9 kill switch does not guard `ExposureManager.build_report`; report lists breaches without raising | **CONFIRMED** | `engine.py:299-347` read: no `_guard()`, no raise on breach |
| RT-F10 no SUBMITTED-order expiry/TTL; limit fills checked only on the single lag bar | **CONFIRMED** | `simulator.py:138-163` read: only `bars[submit_idx + fill_lag_bars]` is checked; an order fillable one bar later returns None (silently never fills) |
| RT-F11 docstring drift (`PnLCalculator` advertised, does not exist) | **CONFIRMED** | `gateway.py:6` docstring vs `__all__` |
| RT-F12 benchmarks bypass `PaperOrderGateway` (simulator direct) | **CONFIRMED** | `benchmarks/runner.py:479-495` read |
| RT-F13 hygiene: pytest a runtime dependency; tracked `src/audit.log`; `.gitignore` gaps | **CONFIRMED** | `pyproject.toml` read: `pytest>=9.1.1` inside `dependencies` (and duplicated in dev extras) |
| RT-F14 no model-loading/reconstruction path | **CONFIRMED** | no `from_artifact`/loader; models are code + in-process fit state |
| RT-F15 `QuantBoundary.request_calculation` functional stub (`result=None`) | **CONFIRMED** | `quant_boundary.py:153-162` read |

**All 15 RT-F findings: CONFIRMED. Zero false positives. None already fixed.**

### 2.2 MC register (missing connections)

| ID | Verdict | This-cycle evidence |
|---|---|---|
| MC-1 RiskEngine/kill-switch → gateway | **CONFIRMED** | zero `risk`⇄`paper` imports (re-grepped) |
| MC-2 ReconciliationEngine → order path | **CONFIRM** | zero src callers (re-grepped) |
| MC-3 AuditLogger → gateway/runtime | **CONFIRMED** | never invoked (re-grepped) |
| MC-4 paper/evaluation.py gates → anything | **CONFIRMED** | imported by nothing inside `paper/` |
| MC-5 ExecutionEligibility booleans → risk/portfolio engines | **CONFIRMED** | caller-supplied `risk_valid`/`portfolio_valid` only |
| MC-6 `DataIngester.ingest()` → callers | **CONFIRMED** | grep: own module + print-only CLI import + facade only |
| MC-7 `DataStorage.store_*` → callers | **CONFIRMED** | grep: own module + print-only CLI import + facade only |
| MC-8 prediction layer → ingestion/PIT-view chain | **CONFIRMED** | estimator consumes duck-typed candles via its own slice |
| MC-9 PredictionOutcomeLedger.append() → runtime driver | **CONFIRMED** | caller-driven only |
| MC-10 6 orphan packages → composition root | **CONFIRMED** | no non-facade, non-test consumer |
| MC-11 CLI → real operations | **CONFIRMED** | 4 print-only no-ops + 1 inverted (REPRO-G) |
| MC-12 paper order vocabulary ⇄ frozen strategy vocabulary | **CONFIRMED** | RT-F6 evidence |

**All 12 MC findings: CONFIRMED.**

### 2.3 ARCH-F spot-verifications mandated by §4

| ID | Verdict | This-cycle evidence |
|---|---|---|
| ARCH-F1 kill-switch reset unauthenticated | **CONFIRMED** | `risk/engine.py:174-176` read: `reset_kill_switch()` is a bare flag clear — no principal, no authorization, no audit record |
| ARCH-F2 risk violation chain lacks `verify()` | **CONFIRMED** | `engine.py` has no verify method; `violation_log` returns records only |
| ARCH-F3 latent NameError `ingestion.py:191` (`EvidenceProvenance` never imported) | **CONFIRMED** | import list (lines 7-15) read: `evidence.py` absent; usage at line 191 |
| ARCH-F4 latent NameError `quant_boundary.py:118/:175` (`datetime`/`UTC` never imported) | **CONFIRMED + REPRODUCED** | REPRO-F: `DeterministicResult(...)` with default timestamp → `NameError: name 'datetime' is not defined` |

---

## 3. NEW bug register (mandate §26 table)

New defects discovered by this cycle's adversarial audit. Reproduction column
references the executable BEFORE-evidence in
`/home/z/my-project/scripts/pp_bug_repro.py` (11/11 reproduced at `e060690`).
Severity follows the mandate's own rules (§6: limit-violation = CRITICAL).

| ID | Severity | Component | File | Symbol | Finding | Reproduction | Expected | Actual | Fix | Test | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| BUG-001 | **CRITICAL** | paper execution | `src/data_engine/paper/simulator.py` | `ExecutionSimulator.simulate` / `_fill_at_reference` | Limit-order fill price violates the submitted limit: BUY fills ABOVE the limit, SELL fills BELOW it, because half-spread + market-impact are added adversely **on top of the limit reference** (§6) | REPRO-A/A2: BUY limit 101.5 fills at 101.551015 (+0.051015); SELL limit 102.5 fills at 102.448975 (−0.051025) | BUY ≤ limit; SELL ≥ limit, with defined all-in cost accounting | Fill price outside the limit by exactly spread+impact; **pinned by `tests/test_paper_trading.py:123`** (`assert fill.price > D("101.5")`) and contradicted by the simulator's own docstring (“at the limit price”) | Prepared (§5.1); application BLOCKED_BY_AUTHORIZATION | Prepared (§5.1): property test over randomized realism params | CONFIRMED_OPEN |
| BUG-002 | **CRITICAL** | position accounting | `src/data_engine/paper/models.py` | `PaperPosition.apply_fill` | Position **flip** carries the closed side's average cost into the new opposite position; the new side's cost basis is never established (§14: “Do not carry the old side's average cost into the new side”) | REPRO-B: +100@100 → sell 140@110 → short −40 with `average_cost=100` (expected 110); REPRO-B2: closing that short at 120 realizes −800 instead of −400 | Flip residual position basis = flip fill price (all-in) | Old side's basis inherited; downstream realized P&L **doubled in error** | Prepared (§5.2) | Prepared (§5.2): flip/short-flip/partial-reduction/full-close matrix | CONFIRMED_OPEN |
| BUG-003 | **CRITICAL** | pre-trade risk | `src/data_engine/risk/engine.py` | `RiskEngine.check_order` | Exposure computed as `abs(order) + abs(current_position)` — the exact formula §5 forbids. The engine cannot distinguish increase/reduction/close/flip; **risk-REDUCING orders are rejected and TRIP the kill switch** | REPRO-C: current +100, max 100, full-close sell 100 → projected 200 → `RiskViolationError` + kill switch tripped; REPRO-C2: reduction +100→+60 also rejected (projected 140) | Signed netting: projected = current + signed(order); check abs(projected) and abs(order) | Additive absolute sum; **pinned by `tests/test_risk_portfolio.py:80`** (comment “ok: 100”) | Prepared (§5.3); contract amendment of a non-frozen module — BLOCKED_BY_AUTHORIZATION | Prepared (§5.3): the three §5 netting cases + increase/flip rejection + no-trip-on-reduction | CONFIRMED_OPEN |
| BUG-004 | HIGH | reconciliation | `src/data_engine/paper/gateway.py` | `ReconciliationEngine.reconcile` | Docstring check (2) “every filled order has its fill” is **not implemented**; the signature receives no order statuses, so a FILLED order whose fill record went missing reconciles CLEAN when position state is consistent-with-the-loss | REPRO-D: gateway says FILLED, fills=[], empty positions → returns `status="reconciled"` | Missing-fill detection for filled orders (needs status-aware input) | Blind to missing fills of filled orders | Prepared (§5.4) | Prepared (§5.4): missing-fill / orphan-fill / clean-pass | CONFIRMED_OPEN |
| BUG-005 | MEDIUM | audit trail | `src/data_engine/paper/gateway.py` | `AuditLogger.log` / `.entries` / `.verify` | Not deeply immutable (§9): payload dict stored **by caller reference**; `entries` returns a shallow tuple over live mutable dicts; and the hash chain is **unkeyed**, so an attacker can rewrite history and re-forge a consistent chain that `verify()` accepts | REPRO-E: post-`log()` mutation of the caller dict changes the historical entry; REPRO-E2: FILLED→CANCELLED rewrite + chain recompute → `verify()` True | Deep-copied (or model-frozen) entries; documented keyed-MAC decision; mutation attempts leave history intact and verification valid | Historical entries mutable in place; chain re-forgeable | Prepared (§5.5) | Prepared (§5.5): external-mutation attempt → history protected, verify True | CONFIRMED_OPEN |
| BUG-006 | MEDIUM | CLI truthfulness | `src/data_engine/cli.py` | `main` (status branch) | `status` reports “OPERATIONAL” while no integrated runtime exists (§21: one boolean must not stand for 7 distinct health dimensions) | Read + ground truth: no runtime, no wired order path; CLI prints `Status: OPERATIONAL` | Distinct LIBRARY_HEALTH / RUNTIME_HEALTH / PAPER_READINESS / LIVE_AUTHORIZATION / DATA_READINESS / MODEL_READINESS / RECONCILIATION_HEALTH | Single OPERATIONAL claim over a library-only state | Prepared (§5.6) | Prepared (§5.6): status output assertion on all 7 fields | CONFIRMED_OPEN |
| BUG-007 | LOW | execution robustness | `src/data_engine/paper/simulator.py` | `ExecutionSimulator.simulate` | Bar ordering is never validated: the submission-bar scan assumes ascending timestamps; unsorted or duplicate-timestamp bars yield a silently wrong `submit_idx` | Read: lines 129-136 (scan takes last index with time ≤ submitted_at; no monotonicity check) | Reject non-monotonic / duplicate-timestamp bar series | Undefined submit bar on malformed input | Prepared (§5.7) | Prepared (§5.7): unsorted/duplicate bars raise | CONFIRMED_OPEN |
| BUG-008 | LOW | deep immutability (systematic §9 sweep) | 30 files / 43 fields (register in §4.9) | frozen pydantic models incl. `LogEntry.fields`, `Checkpoint.state`, `ExposureReport.by_asset/by_sector`, `KnowledgeRecord.content`, `MemoryRecord.content`, `RevisionEntry.payload`, `Dataset.candles`, `FeatureSpec.parameters` | **43 mutable dict/list fields inside frozen=True models** — frozen ≠ deeply immutable; external mutation of returned records is possible without integrity alarms (none of these fields carries a stored hash checked on read) | AST sweep `pp_frozen_mutable_sweep.py`: 43 frozen-model hits / 54 total | Immutable (tuple/frozen) or defensively-copied containers in record models | Mutable containers shared with callers | Prepared (§5.8): field-by-field migration list, prioritized for ledger-bearing models | Prepared: mutation-attempt tests per migrated model | CONFIRMED_OPEN |
| BUG-009 | LOW | analytics robustness | `src/data_engine/paper/gateway.py` | `AnalyticsEngine.total_pnl` / `max_drawdown` | NaN/inf equity-curve points are **silently skipped** (plausible-but-wrong metrics; no finite guard) | Executed: `max_drawdown([100, nan, 90]) → 0.1`, `total_pnl → -10.0` (NaN point ignored, no error) | Fail closed on non-finite inputs | Silent skip | Prepared (§5.9) | Prepared: NaN/inf raise | CONFIRMED_OPEN |

**No FALSE POSITIVE and no ALREADY FIXED row exists in the new register.**
No cosmetic closure was performed (§27): every row above is
CONFIRMED_OPEN — the repository's standing authorization state gates the fix
window on a human decision, so fixes are **prepared and blocked**, not
silently applied.

---

## 4. Section-by-section forensic results (mandate §5–§25)

### 4.1 Correctness sweep (§5-A)
Decimal discipline is otherwise strong in `paper/` (Decimal end-to-end, no
float mixing in fills/positions; UTC enforced at model validators). The
mandate's arithmetic failure modes concentrate in BUG-001 (limit price),
BUG-002 (flip basis), BUG-003 (netting), plus NaN skipping (BUG-009) and
unvalidated bar ordering (BUG-007). Empty bars raise (`SimulationError`).
Duplicate client ids raise (duplicate protection). Invalid states raise at
model validators.

### 4.2 Execution semantics (§5-B)
Only MARKET and LIMIT exist; no stop orders (acceptable pre-runtime, but a
capability gap for the final runtime). Partial fills: **structurally
impossible** — see §4.3. Cancellation: SUBMITTED-only, correct. Rejected
orders: recorded + raised (fail-closed), correct. Expiry/TTL: absent
(RT-F10). Retry/timeout/ambiguous-execution semantics: absent (runtime-era
scope, MC-2/MC-9). Fill ordering is deterministic `(filled_at, fill_id)` in
reconciliation replay.

### 4.3 Partial-fill audit (§7)
The **one-order = one-fill assumption is structural**: `simulate() -> Optional[Fill]`;
`GatewayRecord.fill: Optional[Fill]` (single field, not a sequence);
`OrderStatus` has **no PARTIALLY_FILLED**; fill ids are
`{client_order_id}-F{fill_idx}` (one per bar by construction);
`ReconciliationEngine` **raises** on multiple fills per order (“single-fill
model violated”) — i.e., today's reconciliation would REJECT a legitimate
partial-fill history (§7 violation at runtime-integration time, consistent
today only because the simulator cannot produce partial fills). **Verdict:**
the final runtime's partial-fill mandate requires redesign of the simulator
contract, the gateway record, the status enum, and the reconciliation
invariant together — registered as PAPER-BLK-3 (below), not patchable
piecemeal.

### 4.4 Paper gateway audit (§8)
Risk gate invocation: ABSENT (RT-F1). Kill switch: ABSENT (RT-F1). Audit
logging: ABSENT (RT-F3). Order ledger / fill ledger / position ledger /
P&L ledger: ABSENT (§11 below; only the in-memory `records` dict exists).
Reconciliation: unwired (RT-F2). Duplicate protection: present but
**in-memory only** (RT-F4 — restart wipes it, §16 idempotency fails across
restarts by construction). Idempotency of the same decision/TradePlan intent
is not derivable anywhere (no decision layer exists — §12). Lifecycle
transitions: implicit, no guard table (§4.10). Recovery: ABSENT.

### 4.5 Audit-logger mutability (§9)
BUG-005 (REPRO-E/E2) + the systematic sweep (BUG-008, §4.9). The §9
acceptance test (“external mutation attempt → historical record remains
protected → verification remains valid”) **fails today**: mutation is possible
in place; verification validity after mutation depends on someone calling
`verify()` (nothing in src does — RT-F3).

### 4.6 Memory audit (§10)
`KnowledgeStore` / `MemoryStore` are **IN-MEMORY** (frozen pydantic state
tuples; zero disk I/O in `knowledge/`; restart = total loss; sequence
continuity is intra-process only; capacity 256 fail-closed). Classification
per §10 vocabulary: **IN-MEMORY — not PROCESS-PERSISTENT, not FILE-PERSISTENT,
not DATABASE-PERSISTENT, not DURABLE.** No repository document falsely claims
persistence for them (the runtime audit already classified them honestly);
the final architecture's persistent-memory requirement is therefore an open
integration gap (PAPER-BLK-5). Memory cannot override risk structurally
(memory stores carry no execution authority — verified).

### 4.7 Ledger audit (§11)
Existing ledgers/chains (11, all in-memory except the optional security
trail JSONL): frozen Phase-3 backtest `TradeLedger` (frozen domain — must NOT
be reused as the runtime ledger), prediction outcome ledger, risk violation
chain, knowledge chain, memory chain, discovery registry chain, hermes
message logs, infra structured log, security audit trail, paper `AuditLogger`
(never invoked), PIT revision chain. **None of the nine mandated runtime
ledgers exists** (grep: OrderLedger/FillLedger/PositionLedger/TradePlanLedger/
DecisionLedger/IncidentLedger/PnLLedger/PredictionLedger → 0 hits).
**PAPER-BLK-4.**

### 4.8 Traceability audit (§12)
The full chain MarketData→…→Memory is **broken at the Decision stage**: no
decision engine, no TradePlan type, no prediction→decision→order linkage
(MC-8/MC-9/MC-12). Registration: MISSING_LINK at Decision/TradePlan;
NON-PERSISTENT_STATE across the entire execution domain (RT-F4);
UNVERIFIED_STATE (reconciliation unwired, RT-F2); BYPASS_PATH = the benchmark
simulator call (RT-F12; the only non-test execution caller in src).

### 4.9 SL/TP audit (§13)
SL/TP exists **only** in the frozen backtest domain (`strategy/schemas.py`
STOP_LOSS/TAKE_PROFIT exit types; `strategy/validation.py` pct bounds) and as
discovery-candidate risk assumptions. The **paper execution path has no SL/TP
whatsoever**: `PaperOrder` carries no SL/TP fields; nothing monitors price
against stops; no exit-reason vocabulary exists. The final trade record
**cannot answer** any of the mandate's SL/TP questions. **PAPER-BLK-6**
(integration gap, not a defect of existing components).

### 4.10 State machine audit (§17)
Paper vocabulary: SUBMITTED/FILLED/CANCELLED/REJECTED (4 states; frozen
strategy: PENDING/FILLED/REJECTED/CANCELLED — RT-F6). No
CREATED/VALIDATING/APPROVED/ACKNOWLEDGED/PARTIALLY_FILLED/EXPIRED/UNKNOWN;
no legal-transition table; transitions are implicit in gateway code paths
(submit→FILLED|SUBMITTED|REJECTED; cancel: SUBMITTED→CANCELLED enforced —
the only guarded transition). Illegal transitions are not representable
today only because the machine is minimal; the mandated machine requires an
explicit guard (runtime era).

### 4.11 Bypass search (§18)
Exhaustive grep of direct simulator/gateway/order/fill/position/P&L/risk/
kill-switch usage in `src/` (excluding tests): the **only** execution-path
caller is `benchmarks/runner.py:479-495` (simulator direct — RT-F12,
benchmark-only). No hidden globals/singletons/loops/retries/undocumented
fallbacks were found in the execution domain; the runtime-adjacent latent
paths are ARCH-F3/F4/RT-F8 (documented dormant defects). **No undocumented
order-submission mechanism exists.**

### 4.12 Prediction integration (§19)
Re-verified per the runtime audit: the prediction layer is reachable only
from tests/benchmarks (estimator/registry/ledger are caller-driven;
MC-8/MC-9). Prediction-to-decision integration does not exist anywhere —
hence NOT RUNTIME-INTEGRATED (component status honestly registered; the
existence of models.py/calibration.py/… proves library readiness, not runtime
wiring).

### 4.13 LSTM / Transformer / Ensemble / RL (§20)
Unchanged from the architecture readiness audit: all five families
**NOT READY**; `IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED`. No fake
readiness was created this cycle (zero source changes; the classification
IMPLEMENTED/WIRED/TESTED/RUNTIME-REACHABLE/DATA-VALIDATED/PAPER-VALIDATED
remains: components exist for baselines only; no NN infra, no artifact
loaders, no ensemble/RL runtime).

### 4.14 CLI truthfulness (§21) — BUG-006 (above).

### 4.15 Observability (§22)
`AuditLogger` entries carry **no timestamp, no component, no
event_id/correlation_id/causation_id** (only event/payload/index/hashes);
`infra/` MetricsRegistry/StructuredLog exist but are test-only. None of the
mandated metric families (data/prediction/decision/risk/order/fill/recon
latency, slippage, rejection/fill rates, P&L, drawdown, exposure, leverage,
drift, crash warnings, kill switches, runtime failures) is emitted anywhere
in a production path. **PAPER-BLK-7.**

### 4.16 Failure-injection audit (§23)
No runtime exists to inject failures into; the required
failure-injection test classes (data disconnect … clock anomaly) are absent
from the suite (the runtime audit's test-pyramid gap, re-confirmed). The
fail-closed default posture is verified at component level (kill switch
raises; reconciliation raises; quality gates refuse), but “failure ⇒ STOP
NEW ORDERS ⇒ SAFE STATE ⇒ INCIDENT ⇒ ALERT ⇒ RECONCILE ⇒ RECOVER IF
VERIFIED” is **unenforceable without the runtime loop** (RT-F1/F2/F4).

### 4.17 Idempotency (§16)
Within one process, duplicate `client_order_id` raises (verified). Across a
restart: duplicate protection memory is gone (RT-F4) ⇒ the same order intent
resubmits and executes twice. Timeout ≠ failure semantics, unknown-state
reconciliation-before-retry: absent (runtime era). **PAPER-BLK-2 (restart
recovery unsafe).**

### 4.18 Frozen-contract protection (§25)
Frozen Phase-3 blobs: 11/11 byte-identical; SUB-18 manifest 13/13; frozen
tests pass (1059/1059 includes them). **No frozen source was modified, and
no proposed fix touches a frozen module** (BUG-001/002/003/004/005/006/007/
009 all target non-frozen Phase-8/10/11 modules or root CLI). No
frozen-contract conflict was found inside the new bug register.

---

## 5. Prepared corrections (NOT applied — authorization-blocked)

Per mandate §2: reproduce → document → prepare exact fix → prepare tests →
**do not modify protected source** → report the authorization blocker. Each
item below is implementation-ready and scoped to non-frozen modules.

### 5.1 BUG-001 — limit-order price protection + cost accounting semantics
**Semantics decision (not a naive clamp).** A resting limit order's price
protection is definitional: the executable price for a BUY limit is
`min(limit, market_all_in_ask)` where `market_all_in_ask = bar_open +
half_spread + impact` (adverse stack retained for MARKET orders unchanged).
For the LIMIT fill the recorded cost decomposition must equal the actually
charged components: `spread_cost = max(0, fill_price − bar_open − impact)`
and `slippage_cost = impact * qty * (fill_price < limit ? … : 0)` — i.e.
costs are charged only up to the limit; a price-improving passive fill
records the improvement in the price, not as a negative “cost”.
**Code change:** `simulator.py` LIMIT branch: `reference =
min(limit, open+spread+impact)` (BUY) / `max(limit, open−spread−impact)`
(SELL); `_fill_at_reference` computes component costs from the actually
charged price. **Tests:** amend `test_pt_04` (which pins the violation) to
assert `fill.price <= limit` (BUY) / `>= limit` (SELL); add a property test
over randomized realism parameters and random bar sets asserting the
invariant; add an accounting-identity test `price*qty ± costs == expected
notional`. **Contract note:** `test_pt_04`'s current assertion is the pinned
defect — the test amendment is part of the fix, subject to the fix window.

### 5.2 BUG-002 — flip basis
**Code change:** `PaperPosition.apply_fill` reducing/flipping branch: when
`new_qty != 0` **and** sign(new_qty) differs from sign(self.quantity), set
`average_cost = price_incl` (the residual opposite side opens at the flip
fill's all-in price). Same-sign reduction keeps `average_cost`; full close
resets to 0 (unchanged). **Tests:** +100→−40 flip (basis = sell price);
−100→+50 flip (basis = buy price); partial reduction (basis preserved);
full close (basis 0); downstream realized-P&L equality vs hand-computed
economics (REPRO-B2's −400 case).

### 5.3 BUG-003 — signed position netting
**Contract amendment (non-frozen Phase-8 module):** `check_order` gains the
order side (or signed units): `projected = current_units + signed_units`;
breach iff `abs(projected) > max_position_units` **or** `abs(signed_units) >
max_position_units` (order itself oversized). Reductions/closes never trip;
flips breach only on the residual. **Tests:** the three §5 cases
(+100/−100→0 pass; +100/−40→+60 pass; +100/−140→−40 pass with max ≥ 40);
increase rejected; flip rejected when abs(residual) > max; **kill switch NOT
tripped by any reduction/close**; amend `test_risk_portfolio.py:79-82`
(pins additive semantics — “ok: 100” becomes the new netting assertions).

### 5.4 BUG-004 — status-aware reconciliation
**Code change:** `reconcile(orders_with_status, fills, positions)` (or a
records-overload): every FILLED order must have ≥ 1 fill; every CANCELLED/
SUBMITTED order must have 0 fills; orphan fills still raise; replay check
unchanged. **Tests:** missing-fill-of-filled-order raises; fill-on-cancelled
raises; clean pass; orphan fill (existing) still raises.

### 5.5 BUG-005 — audit-trail hardening
**Code change:** `log()` deep-copies the payload; `entries` returns
deep-copied (or frozen-model) entries; entry schema gains `timestamp`,
`component`, `event_id` (runtime-era correlation/causation ids per §22).
**Keyed-MAC decision:** an unkeyed chain is evidence against accidental
corruption only; adding an HMAC key requires a key-custody policy —
**registered as a human decision**, not silently chosen. **Tests:**
post-log payload mutation leaves history unchanged and `verify()` True;
entries-tuple mutation attempt fails or is detected; REPRO-E2 re-forgery
documented as the accepted threat model until the keyed-chain decision.

### 5.6 BUG-006 — truthful status command
**Code change:** `status` prints the seven distinct dimensions with
truthful values (LIBRARY_HEALTH: OK · RUNTIME_HEALTH: ABSENT ·
PAPER_READINESS: BLOCKED · LIVE_AUTHORIZATION: NOT_AUTHORIZED ·
DATA_READINESS: SYNTHETIC_ONLY/REAL_BLOCKED · MODEL_READINESS: 0 approved ·
RECONCILIATION_HEALTH: NOT_WIRED). **Tests:** output contains all seven
keys with those values at the current repo state.

### 5.7 BUG-007 — bar-series validation
**Code change:** `simulate` validates strictly increasing bar timestamps
(duplicates and regressions raise `SimulationError`). **Tests:** unsorted
bars raise; duplicate timestamps raise; valid series unchanged.

### 5.8 BUG-008 — deep-immutability migration (43 fields)
Prioritized migration to immutable containers (tuple / frozen mapping) or
defensive copy-on-return, ledger-bearing first: `LogEntry.fields`,
`Checkpoint.state`, `ExposureReport.by_asset/by_sector`, `Allocation.weights`,
`KnowledgeRecord.content`, `MemoryRecord.content`, `RevisionEntry.payload`,
then the quant/pit/strategy-adjacent record fields (frozen-strategy fields
are **excluded — frozen contract**; adapters will wrap them at the runtime
boundary). **Tests:** per migrated model, external-mutation attempt leaves
the record intact and any hash/verify check valid.

### 5.9 BUG-009 — finite-input guard
**Code change:** `AnalyticsEngine` rejects non-finite curve points
(`ValueError`). **Tests:** NaN/inf inputs raise; finite behavior unchanged.

---

## 6. Test-requirements position (mandate §24)

Existing: 1059 tests — strong unit/contract/state coverage of library
components (mutation gate 15/15, red-team 45/45, cross-process identity
probes). Missing for the pre-paper runtime (all registered as part of
PAPER-BLK-1..7): integration tests of the authoritative order path, event
tests, risk-path end-to-end tests, execution/ledger/memory/accounting/
reconciliation integration tests, restart/idempotency tests,
failure-injection tests, property tests (netting, limit-price invariant),
end-to-end paper-path tests. Every confirmed bug above has a prepared
regression test (§5); none can be landed before the fix window opens
(they would fail against the pinned defective contracts — BEFORE/AFTER
evidence is preserved in `pp_bug_repro.py` instead).

---

## 7. Final verification evidence (mandate §28)

| Check | Executed evidence |
|---|---|
| Full test suite | `1059 passed in 17.72s` (fresh run this cycle) |
| Targeted bug tests | `pp_bug_repro.py`: **11/11 REPRODUCED** (read-only; asserts failures, not fixes) |
| Frozen-contract verification | `final_gate_verify.py`: 5/5 PASS (11/11 blobs, 13/13 manifest) |
| Secret scan | 0 hits / 260 tracked files + 0 hits in all files changed this cycle |
| Repository cleanliness | working tree clean pre-commit; untracked-artifacts empty |
| Determinism | suite deterministic (3× verified in the prior cycle; unchanged tree this cycle) |

---

## 8. Paper-readiness verdict (mandate §29–§30)

**PAPER STATUS = BLOCKED.** Triggered blockers (§30 checklist):

| Blocker | Ground |
|---|---|
| PAPER-BLK-1 risk gate bypass exists | RT-F1: the only order path (gateway) invokes no risk check |
| PAPER-BLK-2 restart recovery unsafe | RT-F4: duplicate protection, kill switch, audit chains all volatile |
| PAPER-BLK-3 partial-fill accounting incorrect-for-runtime | one-fill structural assumption + reconciliation rejects multi-fill histories (§4.3) |
| PAPER-BLK-4 decision/order/fill lineage broken | no decision layer, no runtime ledgers, MC-8/9/12 (§4.7/§4.8) |
| PAPER-BLK-5 critical state non-persistent | memory IN-MEMORY; no state store (§4.6, RT-F4) |
| PAPER-BLK-6 SL/TP + exit reasons absent from paper path | §4.9 |
| PAPER-BLK-7 limit-order semantics incorrect | **BUG-001 (CRITICAL)** |
| PAPER-BLK-8 position accounting incorrect (flip) | **BUG-002 (CRITICAL)** |
| PAPER-BLK-9 risk netting incorrect (rejects reductions, trips kill switch) | **BUG-003 (CRITICAL)** |
| PAPER-BLK-10 reconciliation blind to missing fills | **BUG-004 (HIGH)** |

No daemon, scheduler, live order, broker connection, credential, or
autonomous activation was performed or claimed (§29). Tests being green does
NOT imply paper readiness — three of the green tests actively pin CRITICAL
defects (§3).

---

## 9. Authorization request (fix window)

The following single human decision unlocks all ten blockers' first stage:
**an authorized fix window over non-frozen modules** (`paper/simulator.py`,
`paper/models.py`, `paper/gateway.py`, `risk/engine.py`, `cli.py`) for
BUG-001..BUG-009 + carried ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 hygiene, each with
the prepared positive/negative/regression tests of §5. Frozen Phase-3
contracts are untouched by every prepared fix. Second required decision:
keyed-MAC custody policy for audit chains (§5.5).

---

## 10. Final report (mandate §31)

**A. Repository state** — HEAD `e060690`; branch `phase-4a/4a1-architecture-correction` = `main` (remote synced, 0 unpushed); working tree clean; tests 1059/1059 (17.72 s).

**B. Existing audit verification** — RT-F1..RT-F15: **all CONFIRMED** (RT-F7 additionally reproduced by execution). MC-1..MC-12: **all CONFIRMED**. ARCH-F1/F2/F3/F4: **all CONFIRMED** (F4 reproduced).

**C. New bugs** — BUG-001 (CRITICAL, limit-order price violation, test-pinned), BUG-002 (CRITICAL, flip basis corruption), BUG-003 (CRITICAL, additive risk netting trips kill switch on reductions, test-pinned), BUG-004 (HIGH, reconciliation missing-fill blindness), BUG-005 (MEDIUM, audit mutability + unkeyed re-forgeable chain), BUG-006 (MEDIUM, CLI “OPERATIONAL” untruthfulness), BUG-007 (LOW, unvalidated bar ordering), BUG-008 (LOW, 43 frozen-model mutable fields), BUG-009 (LOW, NaN silently skipped in analytics). All reproduced or line-verified; 11/11 executable reproductions.

**D. Closed bugs** — **NONE.** No cosmetic closure (§27): the fix window is a pending human decision; all fixes are prepared (§5) and blocked. Evidence of the defect state (BEFORE) is executable at `scripts/pp_bug_repro.py`.

**E. Remaining blockers** — PAPER-BLK-1..PAPER-BLK-10 (§8) + standing STAGE-0 human decisions (real data source approval, WP-12 CI enable, H-1 ratification, approval-owner assignments, PAT rotation).

**F. Paper readiness** — **PAPER_READY = NO (BLOCKED).**

**G. Live authorization** — **LIVE_AUTHORIZATION = NOT_AUTHORIZED** (no explicit independent human authorization record exists; this cycle created none).

**H. Frozen contracts** — **FROZEN_CONTRACTS = INTACT** (11/11 blobs byte-identical; 13/13 manifest; no frozen module modified or targeted by any prepared fix).

---

## 11. Governance preservation statement

REAL_DATA_VALIDATION = BLOCKED · ADVANCED_ML = DEFERRED · LIVE_TRADING =
NOT_AUTHORIZED · LIVE_CAPITAL = INACCESSIBLE · PAPER = SAFE DEFAULT ·
FROZEN PHASE-3 CONTRACTS = IMMUTABLE · VERIFIED_YEARS = 0 · H-1 =
OPEN/CONTAINED. No risk limit was raised, no kill switch weakened, no
reconciliation or risk path bypassed, no audit evidence deleted, no
self-approval performed, no hidden execution path created. Zero source files
modified this cycle; the only repository changes are this document, the
documentation index registration, and the progress-brief update.
