# PHASE 1 — DISCOVERY & AUDIT REPORT (Full-Platform Mandate)

> **Document ID:** P1-DA-001 · **Version:** 1.0.0 · **Date:** 2026-10-12
> **Authority:** A — AUTHORITATIVE for this audit cycle
> **Scope:** Repository-wide discovery audit + the first fail-closed
> implementation batch (ING/VAL defect family), executed on branch
> `fix/ingestion-classification-fail-closed` from `d945833`.

**Mandate:** full review and progressive improvement of
`muhammadasterschool-sketch/ai-trading-lab-data-engine` toward a
privately distributed, secure, multi-user trading platform (owner +
20+ approved users, per-user VPS, isolated credentials/licenses,
Windows/Android/iOS private distribution, read-only mobile initially,
extensible broker-adapter architecture, fail-safe trading ledger).
Everything below was verified first-hand this session or cites the
recorded evidence of record; nothing is assumed from prior summaries.

---

## 0. VERDICT SUMMARY

- **Repository access: CONFIRMED.** Anonymous `git ls-remote` works
  (read access to all refs); local clone verified clean at
  `d945833` on `feat/broker-neutral-execution-architecture`.
  Write access (push/PR) is **NOT available** this session — no
  credential exists in the environment (verified: no token file,
  prior one-time-use PATs not reusable per protocol) — so this batch
  is committed locally with exact operator push commands recorded
  (§9).
- **Baseline re-verified first-hand:** full suite at `d945833` =
  **2,005 passed + 1 skipped** (56.51 s) before any edit — matching
  the §0F record exactly.
- **Six confirmed ingestion/validation classification defects**
  (ING-NAT-1, ING-VOL-1, ING-COL-1, VAL-ORDER-1, ING-STALE-1,
  ING-NVIEW-1) — each reproduced with an executable probe BEFORE any
  fix — are **CLOSED in this batch** with 20 new RED-first regression
  tests. Suite: **2,025 passed + 1 skipped × 3 consecutive**
  (55.04/56.23/55.75 s). Frozen Phase 3 blobs 11/11 byte-identical;
  secret scan 0 hits across all history; committed dataset
  classifications verified UNCHANGED under the hardened audit
  (read-only check).
- **The full-platform product goal is NOT met and is NOT claimed:**
  no multi-user surface, no authentication/authorization, no tenant
  isolation, no control plane, no per-user VPS provisioning, no
  Windows installer, no Android/iOS clients, no production broker
  order path (mocks only, by design), and Bitget has no adapter at
  all. §5 maps every gap honestly; §7 gives the phased roadmap.
- **PAPER_READY = FALSE (unchanged); LIVE NOT AUTHORIZED.**

---

## 1. REPOSITORY ACCESS + BRANCH/PR/CI STATE (first-hand, 2026-10-12)

Access method: unauthenticated `git ls-remote origin` (the repository
is publicly readable; no credential used or needed for inspection).
The GitHub REST API is rate-limited from this environment
(unauthenticated), so live PR/CI re-query is a **recorded blocker**;
CI state below is the evidence of record from the push session.

| Ref | SHA (ls-remote, this session) | Meaning |
|---|---|---|
| `refs/heads/main` | `d49b822` | default branch — unchanged |
| `refs/heads/feat/master-market-data-import` | `4e6dfc5` | PR #1 head (open) |
| `refs/heads/feat/broker-neutral-execution-architecture` | `d945833` | PR #2 head (open) |
| `refs/heads/fix/paper-runtime-pnl-correctness` | `efd92c1` | stacked under PR #2 |
| `refs/heads/fix/paper-runtime-killswitch-fill-enforcement` | `1c286d2` | stacked under PR #2 |
| `refs/pull/1/head` / `refs/pull/1/merge` | `4e6dfc5` / `0ec022f` | PR #1 exists, open |
| `refs/pull/2/head` / `refs/pull/2/merge` | `d945833` / `6873028` | PR #2 exists, open |

- **PR #1** (master market-data import): open, mergeable TRUE/clean,
  3 commits, 22 files, +559,875/−25. CI evidence of record: runs
  `38147316090` (head `b9c4361`) and `38147771879` (head `4e6dfc5`)
  — both SUCCESS, 3.11+3.12 legs, all gates green.
- **PR #2** (broker-neutral execution Phase M1 + stacked fixes):
  open, mergeable TRUE/clean. CI evidence of record: run
  `38242367378` (pull_request, head `d945833`) — SUCCESS, full suite
  + determinism ×3 + frozen-blob + secret scan + prediction
  acceptance, both Python legs green.
- Both merges are left to the operator (standing rule: no
  unauthorized merges). Local branch state matches remote exactly
  (`git status` clean, no unpushed commits on any remote-tracked
  branch before this batch).

---

## 2. VERIFIED STACK + ARCHITECTURE (first-hand)

**Stack** (`pyproject.toml`): Python ≥3.11; runtime deps
pydantic ≥2, numpy, pandas, openpyxl; dev dep pytest ≥9.1.1
(actual: pytest 9.1.1, Python 3.12.15 in the locked uv env);
build backend `uv_build` (module `data_engine`); console script
`data-engine` → `data_engine.cli:main`. No web framework, no server,
no database driver — the repository is a **library + evidence
scripts + pytest suite**, not a deployed service.

**CI** (`.github/workflows/ci.yml`, least-privilege
`permissions: contents: read`): 3.11+3.12 matrix; steps = locked env
install → full suite (must be 100% green) → determinism (three
consecutive runs) → frozen Phase 3 verification (11 strategy blobs
byte-identical to `13fdc7e`) → secret scan over **all history**
(0-hit gate) → prediction acceptance tests. Triggers:
`push` to main/`phase-4a/**` and `pull_request` to main.

**Layered architecture** (verified by direct source reads):

```
Raw CSVs / providers  →  ingestion audit + classification
      │                     (platform/datasets.py, master_datasets.py,
      │                      validation.py, ingestion.py, quarantine.py)
      ▼
Canonical datasets + manifests + provenance
      │                     (schemas, provenance, storage, pit/*)
      ▼
Research layer          (quant/*, strategy/* [FROZEN], research_validation/*,
      │                  experiment_registry, discovery/*)
      ▼
Prediction layer        (prediction/* — 28 modules: PIT datasets, labels,
      │                  calibration, drift, red-team matrix, ledger)
      ▼
Paper trading runtime   (runtime/* — feed_gate → data_gate → decision →
      │                  trade_plan → risk_gate [21 checks] → kill_switch
      │                  [7 scopes, fill-time] → oms [14-state] →
      │                  execution → exits → pnl → reconciliation [§32
      │                  three-way] → state [schema 1.1.0, hash-chained,
      │                  atomic] → recovery → ledgers → metrics → rl)
      ▼
Platform projection     (platform/* — registry, workbook, dashboard,
      │                  read-only MT5 surface, TradingView, news, feeds)
      ▼
Broker-neutral layer    (brokers/* — Phase M1: interface, capabilities,
                         redaction, guarded session, 4 deterministic mocks)
```

---

## 3. TRADING SAFETY CHAIN — VERIFIED STATUS

The mandated chain
**market data → strategy/decision → TradePlan → risk gate → kill
switch → order management → broker gateway → acknowledgement → fills
→ positions → reconciliation → ledger → P&L/reporting** exists and is
integration-tested **within the paper runtime** (verified §0D/§0E/§0F
cycles; re-confirmed present at this HEAD by source inspection):
21-check `RiskGate` on every order path; `KillSwitchManager` enforced
at order-submit AND fill-time (in-flight cancel, exit-order
carve-out, persisted terminal HALT restored on restart);
`OrderManagementSystem` with fingerprint-bound risk approval
(RT-F1), 14-state lifecycle incl. PARTIALLY_FILLED → EXPIRED;
§32 three-way reconciliation gates resumption; hash-chained
`EXECUTION_STATE_SCHEMA 1.1.0` persistence with atomic writes,
identity binding, and cross-process deterministic replay; full
restart recovery (LOAD → VERIFY → RESTORE → RECONCILE → RESUME).

**Broker gateway boundary:** the runtime's execution venue is the
paper simulator (`runtime/execution.py` / `paper/gateway.py`).
The new `brokers/` layer (Phase M1) is a **parallel, not-yet-wired
interface**: `BrokerSession` wraps any `BrokerAdapter` with
isolation → health → reconciliation → kill-switch → risk gates,
journal-backed idempotency (survives restart), bounded deterministic
retry, UNKNOWN-status degradation, and per-record-digested
journals. Verified: **no `runtime/*` module imports `brokers/*`**
(grep-verified) — venue wiring is Phase M2 and NOT STARTED.

**Live trading:** no live execution surface exists anywhere. The MT5
platform surface (`platform/mt5.py`) is read-only and fail-closed
(order path always refused); `LiveAuthorizationGate` denies; the
capability registry REFUSES real execution modes at registration.
Zero real credentials and zero real orders have ever been used (all
adapters are deterministic mocks; providers are public read-only
market-data with allowlists).

---

## 4. CONFIRMED DEFECTS — EVIDENCE, FIX, TEST (this batch)

All six were reproduced by an executable probe
(`probe_ingestion_classification.py` pattern, pre-fix output
recorded in the worklog) BEFORE any fix; every fix landed with
RED-first acceptance tests in
`tests/test_ingestion_classification_fail_closed.py` (15 defect
tests RED pre-fix; 5 behaviour pins GREEN throughout).

| ID | Severity | Location (pre-fix) | Defect | Fix |
|---|---|---|---|---|
| ING-NAT-1 | HIGH | `platform/datasets.py` `audit_csv_file` | Unparseable dates coerced to NaT with **no counter, no finding, no classification impact**; NaT-dated rows still counted in `valid_ohlc_rows`; coverage silently shrank via `dropna` | `invalid_timestamp_rows` counter + integrity finding → INVALID; NaT rows excluded from valid-OHLC counts |
| ING-VOL-1 | MED-HIGH | same | `volume_col` discovered but never consulted — negative volume invisible (master path already counted it; platform path did not) | `negative_volume_rows` counter + integrity finding → INVALID |
| ING-COL-1 | MED-HIGH | same | `expected_columns_match=False` never consulted by classification (extra/reordered columns still classified REAL_UNVERIFIED); missing critical columns crashed with raw `KeyError` | Schema mismatch → integrity finding → INVALID; missing critical columns raise explicit contract `ValueError` |
| VAL-ORDER-1 | MED-HIGH | `validation.py` `_check_timestamp_order` | Out-of-order timestamps rated WARNING → `DataIngester.ingest` (blocks only on INVALID) admitted non-chronological datasets into the canonical store | WARNING → INVALID (consistent with the platform CSV path); the one incidental non-chronological test fixture corrected (documented, detection assertion unchanged) |
| ING-STALE-1 | HIGH | `scripts/platform_csv_ingest.py` + `scripts/master_data_ingest.py` | When `data/raw/<file>` already existed, a newly supplied source file was **silently ignored** and the stale destination ingested (no warning, exit 0) | Loud refusal: platform script exit 1, master script exit 2 (checksum-pinned bundle: explicit manifest-update instruction); raw store still never overwritten |
| ING-NVIEW-1 | HIGH | `scripts/master_data_ingest.py` | Normalized-view generation failures swallowed by bare `except Exception` + print, script still returned **exit code 0** (partial lineage.json left behind) | Stage extracted into `_write_normalized_views` (failures propagate); `main` converts to FATAL + exit 3; nothing partial written on failure |

**Companion hardening (ING-COL-2, cosmetic → fixed):** the audit's
recorded `columns` field captured the working frame AFTER helper
columns (`_date`, `_sym`, `_Open`…) were added — the committed
manifests record a self-contradictory `columns` list next to
`expected_columns_match: true`. The audit now records the file's
original columns. Committed manifests are historical evidence and
were NOT regenerated; a read-only stability check proved all four
committed platform datasets keep their recorded SYNTHETIC
classification under the hardened audit (invalid_ts=0, neg_vol=0,
cols_match=true for all four).

**Exit-code contract now enforced by tests:**
`platform_csv_ingest.py` — stale divergence → 1; nothing ingested →
1; success → 0. `master_data_ingest.py` — stale divergence → 2;
checksum failure → 2; normalized-view failure → 3; success → 0.

---

## 5. PRODUCT-GOAL GAP ANALYSIS (verified, honest)

The mandate's product goal is a **privately distributed, secure,
multi-user platform**. First-hand verification of what exists:

| Product requirement | Verified repository state | Status |
|---|---|---|
| Multi-user (owner + 20+ approved users) | Single-user engine; no user/account model anywhere in `src/` (grep: no authn/tenant/session-user surface) | **MISSING — not started** |
| Per-user VPS, isolated DB/keys/credentials/logs/ledger/backups/license | No deployment artifacts, no IaC, no provisioning code | **MISSING — not started** |
| Control plane (approvals, licensing, health) | Nothing; `platform/dashboard.py` is an in-process read-only JSON snapshot builder, not a service | **MISSING — not started** |
| AuthN/AuthZ, short-lived tokens, rate limits, TLS, server-side authorization | No HTTP server, no API surface exposed to networks (library only) — therefore also no auth to review | **MISSING — by absence (no network attack surface today, which is the only honest security claim)** |
| Windows signed installer + private download portal | None | **MISSING — not started** |
| Android APK private distribution | None | **MISSING — not started** |
| iOS private/unlisted distribution | None (research + limitations documented in §7 roadmap) | **MISSING — not started** |
| Mobile read-only app (P&L/equity/drawdown/positions/history/health/alerts) | No mobile client; `dashboard_snapshot.json` projection is the closest seed | **MISSING — not started** |
| Cloud engine running on each user's VPS while their PC is off | Runtime is an in-process library; no daemon/service/deployment story yet | **MISSING — not started** |
| Broker adapters: MT5, Exness, Binance, Bitget, XM, extensible | See §6 matrix — M1 interface + 4 deterministic mocks only | **PARTIAL (interface + mocks only)** |
| Trading-safety chain with risk/kill-switch on every order path | Complete + integration-tested within paper runtime (§3) | **PRESENT (paper-only)** |
| Paper-first, live disabled by default, audited enablement | PAPER_READY=FALSE; LIVE NOT AUTHORIZED; no live surface exists; LiveAuthorizationGate denies | **PRESENT (by design)** |
| Market-data quality classification fail-closed | This batch closed the 6 confirmed defects; master + platform paths now consistent | **PRESENT (this batch)** |

**Residual security notes (verified):** no secrets in git history
(0-hit scan gate); secrets never in tests/fixtures; frozen Phase 3
blobs enforced by CI; least-privilege CI permissions. The PAT
rotation advisory from prior cycles **remains OPEN** (operator
action).

---

## 6. BROKER INTEGRATION SUPPORT MATRIX (verified routes + status)

Distinguishing broker **brands** from **APIs/platforms** (verified
against each provider's documented integration route):

| Provider | Official route (verified) | Implemented in repo | Test evidence | Remaining limitations |
|---|---|---|---|---|
| **Paper/simulated** | n/a (internal) | `brokers/adapters/paper.py` (reference venue) + `paper/simulator.py` runtime | 236 broker tests + full runtime suite | n/a |
| **MT5 (MetaQuotes platform)** | MT5 Python API requires a **local Windows MT5 terminal** running + logged-in account; bridge or VPS-side terminal for headless | `platform/mt5.py` = **read-only, fail-closed** surface (order path always refused); `brokers/adapters/mt5_mock.py` = deterministic MT5-style mock (hedging tickets, volume lots, attached SL/TP, comment idempotency) | unit + contract tests (mock) | No live MT5 connection; requires operator-provisioned Windows terminal; REAL modes refused at registration |
| **Exness / XM** | Retail MT5 **brands** (brokers), not separate public trading APIs — integration is via the MT5 terminal route above | Covered by the MT5 mock surface only; **no Exness/XM-specific integration exists or is claimed** | mock contract tests | Account-support verification + operator credentials required before any real adapter (mandate rule) |
| **Binance** | Public REST (market data, no key) + authenticated REST/WS (trading, keys) | `providers/binance_public.py` = public spot klines market-data adapter (closed-candle enforcement, UTC grid, fail-closed rejections, allowlist=[BTCUSDT], API-key config refused); `brokers/adapters/binance_mock.py` = spot-style execution mock (filters, newClientOrderId, separate SL/TP, request-weight 429) | 41 adapter tests + contract tests | Market data is public/read-only; NO authenticated trading adapter exists; allowlist must be widened per operator approval |
| **Bybit** | v5 REST/WS APIs | `brokers/adapters/bybit_mock.py` = v5-style mock (orderLinkId, attached SL/TP, one-way netting, lotSizeFilter) only | contract tests | NO real Bybit adapter exists |
| **Bitget** | Public + authenticated REST APIs | **NOTHING — no adapter, no mock, no market-data provider** | none | Entirely unimplemented (mandate lists it; scheduled in roadmap Phase M4) |

**No production-ready adapter is claimed for any venue.** All
execution adapters are deterministic mocks; the only network-touching
code is read-only public market data (Binance klines) with strict
fail-closed behaviour. The capability registry structurally refuses
REAL execution modes at registration until per-venue approval exists.

---

## 7. PHASED ROADMAP (mapped to the mandate's Phases 2–7)

Each phase has acceptance criteria that must be demonstrated with
tests/evidence before status changes. Nothing below is claimed done.

- **P2 (correctness — IN PROGRESS, this batch):** ingestion/validation
  fail-closed hardening. ✅ DONE this cycle (§4). NEXT: RUN-DD-1
  account-equity drawdown limit (highest-ranked remaining paper-runtime
  blocker), RUN-ST-1 staleness watchdog, RUN-CA-1 operator
  cancel/manual-close. AC: RED-first acceptance tests, full suite ×3,
  frozen intact, zero regressions.
- **P3 (execution + user isolation):** wire `BrokerSession` into the
  runtime as the execution venue behind the paper gateway (Phase M2);
  tenant identity model (per-user ledger/state namespaces, server-side
  authorization primitives, isolation tests BEFORE any user-facing
  API). AC: paper runtime executes through the broker-neutral session
  against the paper adapter with zero behaviour change (suite green);
  tenant-isolation property tests.
- **P4 (VPS provisioning + operations):** idempotent IaC for per-user
  VPS (no paid resources provisioned without explicit authorization);
  TLS, health checks, monitoring, encrypted backups + restore
  validation, upgrade/rollback, deprovisioning. AC: dry-run
  provisioning plan reviewable in-repo; restore drill documented.
- **P5 (API + read-only mobile dashboard):** authenticated API
  (short-lived tokens, per-user routing to their own VPS/data,
  server-side authorization on every route, rate limits) + read-only
  mobile clients (P&L/equity/drawdown/positions/history/health/
  alerts; NO order placement). AC: authorization/isolation test
  matrix green; read-only enforcement tested (order routes absent).
- **P6 (Windows packaging + private distribution):** signed Windows
  installer via authenticated expiring links (no embedded secrets);
  Android private APK channel; iOS: unlisted App Store / TestFlight /
  Ad Hoc options with Apple-review constraints documented (no
  promise of link-installable iOS apps); license
  creation/expiry/suspension/revocation workflows with signing keys
  outside repo/binaries. AC: packaging pipelines + license lifecycle
  tests; distribution plans documented.
- **P7 (security acceptance + staged release):** automated
  security/tenant-isolation suites; paper pilots; live-trading
  enablement ONLY via explicit owner approval + verified connectivity
  + risk checks + auditable enablement event; deployment/incident/
  recovery/offboarding runbooks. AC: runbooks reviewed; readiness
  verdicts unchanged until evidence supports them.

---

## 8. FIRST IMPLEMENTATION BATCH — EXACT RECORD

**Branch:** `fix/ingestion-classification-fail-closed` (from `d945833`).

**Changed files (6 + 1 new test file):**
1. `src/data_engine/platform/datasets.py` — ING-NAT-1/ING-VOL-1/
   ING-COL-1/ING-COL-2 fixes (new counters, findings, contract
   error, original-columns capture, NaT exclusion from valid rows)
2. `src/data_engine/validation.py` — VAL-ORDER-1 (timestamp_ordering
   WARNING → INVALID, documented)
3. `scripts/platform_csv_ingest.py` — ING-STALE-1 loud refusal (exit 1)
4. `scripts/master_data_ingest.py` — ING-STALE-1 (exit 2) +
   ING-NVIEW-1 (`_write_normalized_views` extraction, FATAL exit 3)
5. `tests/test_data_engine.py` — one incidental non-chronological
   fixture corrected (documented; detection assertion unchanged)
6. `tests/test_ingestion_classification_fail_closed.py` — **NEW**,
   20 tests (15 RED-first defect tests + 5 behaviour pins)
7. This report + index/readiness/§0G registration (docs)

**Commands and actual results:**
```
uv run pytest -q -p no:cacheprovider        # baseline pre-fix @ d945833:
                                            #   2005 passed, 1 skipped (56.51s)
uv run pytest tests/test_ingestion_classification_fail_closed.py -q
                                            # pre-fix: 15 failed, 5 passed (RED confirmed)
                                            # post-fix: 20 passed
uv run pytest -q -p no:cacheprovider        # ×3 post-fix:
                                            #   2025 passed, 1 skipped (55.04s)
                                            #   2025 passed, 1 skipped (56.23s)
                                            #   2025 passed, 1 skipped (55.75s)
frozen check vs 13fdc7e                     # 11/11 INTACT
git grep secret scan over all history       # 0 hits
committed-data stability check (read-only)  # 4/4 classifications UNCHANGED
```

**Test-delta accounting:** +20 new tests, 1 existing test corrected
(fixture order only, documented in-line), 0 tests deleted, 0 tests
weakened — the single behavioural contract change (out-of-order →
INVALID) is itself regression-tested and was impact-assessed by a
full-suite scratch run BEFORE adoption (exactly one incidental
fixture affected).

---

## 9. REMAINING BLOCKERS + OPERATOR ACTIONS

1. **Push credential (immediate):** no credential exists in this
   environment; the prior one-time-use PATs are consumed and flagged
   for rotation. Operator push commands for this branch:
   ```
   git push -u origin fix/ingestion-classification-fail-closed
   # then open a PR targeting feat/broker-neutral-execution-architecture
   # (stacked on PR #2) or main per operator preference
   ```
   With a rotated credential supplied in-session, the push + PR can
   be executed and CI observed to conclusion.
2. **GitHub API rate limit:** live PR/CI re-query blocked
   unauthenticated from this IP; CI evidence of record cited in §1.
3. **Standing human blockers (unchanged):** PAT rotation confirmation;
   SRC-APPROVAL for binance-public-spot + operational feed
   provisioning; keyed-MAC custody key; REAL_DATA_READY nine-stage
   chain with REAL_VERIFIED data (currently 0); H-1 ratification
   recorded, PAT rotation open.
4. **Ranked paper-runtime engineering blockers (next batches):**
   RUN-DD-1 (account-equity drawdown limit) > RUN-ST-1 (staleness
   watchdog) > RUN-CA-1 (operator cancel/manual-close).

---

## 10. WORKING-RULES COMPLIANCE

- Repository treated as source of truth; every state above re-verified
  this session (ls-remote, suite runs, source reads) — nothing taken
  from prior summaries without verification.
- No repository instruction files exist (no AGENTS.md/CONTRIBUTING.md;
  README + MASTER_DOCUMENTATION_INDEX.md are the documented entry
  points) — followed.
- Clean descriptive feature branch; no direct commits to main; no
  force-push, branch deletion, merges, or deployments; frozen
  contracts untouched (11/11 verified); no user data/market data
  modified (read-only stability check); no credentials printed,
  stored, or committed (secret scan 0 hits all history).
- Failures made visible to CI through correct exit codes (ING-STALE-1/
  ING-NVIEW-1); no tests weakened or removed; exact commands and
  counts reported; nothing claimed beyond evidence.

**PAPER_READY = FALSE. LIVE NOT AUTHORIZED.** Both unchanged by this
cycle, by design: the fixes harden data-quality classification; they
do not alter the readiness verdicts or their human/data dependencies.
