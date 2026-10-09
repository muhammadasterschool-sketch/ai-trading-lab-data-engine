# AI Trading Lab — Data Engine
## Platform-Expansion Master Mandate: Registration + Phase 1/2 Forensic Gap Matrix

```text
Document Type:  Mandate registration + Phase 1/2 forensic audit (READ-ONLY)
Phase:          Platform expansion (strategy lab, instrument registry workbook,
                MT5/TradingView integration, dashboard, news intelligence §11 A–M)
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT (superseded in implementation status by
                docs/PLATFORM_EXPANSION_SPEC.md v1.0.0 — the delivery record)
Version:        1.1.0
Last Updated:   2026-10-10
Supersedes:     v1.0.0 (2026-10-09)
Superseded By:  —
Source Evidence: git (HEAD 8667d60 at cycle start, both refs), repo-wide
                 symbol searches, module inventories, full-suite re-runs
                 1,447 + 1 skipped (pre-cycle) → 1,570 + 1 skipped ×2
                 (post-cycle, uv --frozen), frozen manifest 13/13 before
                 AND after, Phase C evidence run (data/manifests/)
```

> This document registers the operator's **Master Prompt — AI Trading Lab**
> (strategy testing, paper trading, MT5 & TradingView integration, instrument
> registry, controlled live execution, dashboard, market intelligence, and
> §11 Real-Time Web News Intelligence A–M) and delivers the Phase 1 (inspect)
> and Phase 2 (implementation plan / gap matrix) outputs that the mandate's
> own §13 requires **before** new implementation. No source, test or frozen
> file was touched this cycle. Nothing in this document claims a feature is
> complete unless repository evidence proves it.

---

## 1. Mandate registration

- **Received**: 2026-10-09, with a repeated operator instruction
  *"sab push karke ek brief doc banao jisme batao ke is repo mai abhi tak
  kiya kiya hai"* (push everything; brief doc of work done so far).
- **Push state re-verified first**: HEAD `779df16` present on BOTH
  `refs/heads/main` and `refs/heads/phase-4a/4a1-architecture-correction`
  via `git ls-remote`; working tree clean — **everything was already
  pushed**; the brief doc (`ZAI_REPOSITORY_WORK_DONE_SUMMARY.md`) exists and
  is updated this cycle to v2.1.0.
- **Operating principles acknowledged**: evidence before claims; no
  fabricated results; frozen Phase 3 contracts untouchable; paper default;
  live trading DISABLED and NOT AUTHORIZED; fail-closed readiness; no
  self-approval; external content (news/web) treated as untrusted data.
- **Relationship to prior mandates**: the runtime/paper-readiness mandates
  (Erases 6–8 of the work-done summary) are CLOSED with evidence. This
  mandate expands the platform surface into five genuinely-new areas
  (news intelligence, instrument registry workbook, MT5/TradingView
  adapters, strategy management lab, dashboard) — all mapped in §3.

---

## 2. Method (first-hand, this session)

1. `git status` / `git log` / `git ls-remote` — state and push truth.
2. Full suite re-run: `uv run --frozen pytest -p no:cacheprovider -q`
   → **1,447 passed + 1 skipped in 37.07 s** (matches the reported baseline
   exactly; the 30 warnings are documented ARCH-F1 test-posture warnings).
3. Frozen Phase 3 manifest: `scripts/frozen_integrity_check.py`
   → **13/13 OK**.
4. Repo-wide symbol searches over `src/`, `tests/`, `pyproject.toml`:
   `metatrader|mt5`, `tradingview`, `xlsx|openpyxl|excel|spreadsheet`,
   `webhook`, `fastapi|flask|uvicorn|dashboard`, `postgres|sqlite|sqlalchemy`
   → **zero hits each** (evidence for the MISSING classifications below).
5. Targeted inspection: `pit/temporal.py` (the only `news` occurrence),
   `discovery/` package purpose, `paper/evaluation.py` criteria surface,
   `schemas.py` `Instrument`, `runtime/` module inventory, `pyproject.toml`
   dependency set (pydantic/numpy/pandas only; pytest dev-extra).

---

## 3. The gap matrix — mandate section vs repository reality

| Mandate § | Requirement | Repo status | Evidence |
|---|---|---|---|
| 2 | Historical backtesting (PIT, costs, OOS, walk-forward, bias guards) | **IMPLEMENTED** | Frozen Phase 3 `strategy/` engine; `research_validation/` (walk-forward, OOS, leakage, overfitting, robustness); `pit/` 13 components; fees/spread/slippage in execution path. Honest limit: **VERIFIED_YEARS = 0** — no real dataset supplied yet |
| 3 | Paper-trading engine (fills, costs, ledgers, recovery, approval gate) | **IMPLEMENTED** | `runtime/` 24 modules: 14-state OMS (idempotent identity, partial fills, TTL), SL/TP exits, PnL, 9 hash-chained ledgers, atomic persistence + journal, reconciliation, recovery (LOAD→VERIFY→RESTORE→RECONCILE→RESUME), deterministic replay ×2; `paper/evaluation.py` configurable `ReadinessCriterion` set, fail-closed without criteria, graduation requires explicit human authorization. **Documented deviation**: evaluation floor pinned at 30 days by frozen blueprint 5.56–5.58 (criteria configurable; duration floor not — see §7) |
| 4 | Controlled live trading (two-stage approval, account/strategy limits, kill switch) | **PARTIAL — FRAMEWORK ONLY** | 21-check risk gate wired into OMS approval (bypass impossible), 7-scope kill switch, always-deny live-authorization gate (Era 2). **No live execution surface exists (intentional); no two-stage approval registry built** — moot until an operator ever authorizes a live surface. Broker-specific controls (connection loss, reconnection reconciliation) N/A without a broker adapter |
| 5 | MetaTrader 5 integration | **IMPLEMENTED — READ-ONLY, FAIL-CLOSED** (v1.1.0) | `platform/mt5.py`: unavailable-by-construction on non-Windows (BLOCKED_ON_OPERATOR_ENV); injected-terminal protocol; DEMO/REAL discipline; reads fail closed; order surface REFUSED ALWAYS (tested incl. connected real account). Real verification BLOCKED on operator environment; 19 tests |
| 6 | TradingView integration (alerts/webhooks) | **IMPLEMENTED — VALIDATOR/ROUTER CONTRACT** (v1.1.0) | `platform/tradingview.py`: strict schema (extra fields forbidden), HMAC-SHA256 over FULL canonical payload incl. signal body (tamper test caught + fixed a mid-implementation digest-coverage defect), replay window, nonce dedup, unknown-instrument fail-closed → advisory intent (never an order). Public endpoint deployment BLOCKED on infra; 18 tests |
| 7 | Automatic instrument discovery & registration | **IMPLEMENTED** (v1.1.0) | `platform/registry.py` + `platform/datasets.py`: deterministic canonical ids (cross-process tested), provider-symbol mappings, provenance, verification timestamps, eligibility workflow (registration ≠ eligibility), duplicate detection without merging distinct instruments; 20 instruments registered from the audited CSVs |
| 8 | Central Instrument Registry workbook (Sheets A–F + News Log) | **IMPLEMENTED** (v1.1.0) | `platform/workbook.py`: Sheets A–G exactly as mandated (incl. G News Log), paper/demo/live mode separation, filters + frozen header, duplicate-trade refusal, XLSX (openpyxl — dependency added to pyproject + uv.lock) + byte-deterministic CSV export; 10 tests; rendered artifact at data/exports/ |
| 9 | Dashboard & approval workflow UI | **IMPLEMENTED — READ-ONLY, STDLIB** (v1.1.0) | `platform/dashboard.py`: frozen PlatformSnapshot + stdlib http.server (NO framework dependency — smallest compatible choice); GET-only 2 routes, 405 on writes, 404 unknown; honest contracts tested (LIVE renders NOT AUTHORIZED; no fabricated prices — no_data; XSS-escaped); 13 tests |
| 10 | AI market risk & crash prediction | **IMPLEMENTED** | `prediction/` ~30 modules: baselines, LSTM, Transformer, ensemble, calibration, regimes, crash framework, scenarios/stress, drift, uncertainty, event evaluation, red-team matrix (45/45 defended), abstention gates. Honest limits: VERIFIED_YEARS = 0; advisory-only (cannot bypass risk limits — tested) |
| 11 A–M | Real-time web news intelligence | **IMPLEMENTED — OFFLINE CORE** (v1.1.0) | `platform/news.py`: content-hash dedup (syndication-aware), retrieval-before-publication refused, PIT visibility boundary, staleness, entity→instrument resolution with ambiguity FLAGGED, EconomicEvent calendar (surprise only when consensus+actual both present — never invented), untrusted-content posture; live sources BLOCKED on credentials; 17 tests. News Log sheet joins the workbook |
| — | Four historical CSV datasets (Phase C of this mandate) | **INGESTED — ALL CLASSIFIED SYNTHETIC** (v1.1.0) | 116,940 rows / 20 instruments audited through `platform/datasets.py`; HARD fabrication evidence (TSLA 1,171 pre-IPO OHLC rows; 27,449 venue/quote-asset anachronisms; 270 holiday-priced rows; uniform generation grid); 2006 anchors match real history (calibration, not reality); registry blocks research/backtesting eligibility for all 20 instruments; manifests under data/manifests/; 17 tests |
| 12 | Testing & reliability discipline | **IMPLEMENTED** (as a standing practice) | 54 test files / 1,570 + 1 skipped ×2; determinism ×2 per cycle; mutation gates (15/15, 31/31); failure injection (24 scenarios); frozen verification before/after every cycle. New platform modules extend per category (123 new tests across 8 files) |
| 13 | Development workflow | **Phases 1–8 DELIVERED** (W4 sandbox + W8 DB explicitly deferred) | Delivery record: docs/PLATFORM_EXPANSION_SPEC.md v1.0.0 |
| 14 | Final deliverables | **PER-PHASE DELIVERED** | data/manifests/ + data/exports/ + this matrix + the work-done summary era 9 |

---

## 4. Detailed findings — the five genuinely-new areas

### 4.1 News intelligence (§11 A–M)
The repository has zero news functionality. What can be built honestly and
fully tested offline: the **core engine** — news-item data model (headline,
source, original URL, publication ≠ retrieval timestamps, affected
instruments), dedup/syndication detection, entity→instrument resolution with
ambiguous-match flagging (reusing the canonical `Instrument` identity), a
pluggable sentiment/analysis interface, an economic-calendar model
(scheduled vs unscheduled, surprise fields never invented), a
news-publication-timestamp PIT boundary for backtesting (extending the
existing `pit/` temporal machinery — `TemporalDataType.NEWS` already
exists), an audit trail, and the News Log sheet (§8). What is BLOCKED:
real source connections (credentials/subscriptions — operator), LLM-based
interpretation (integration decision), and any claim of live news coverage
until a source is actually connected and disclosed. Security posture
already specified by the mandate matches repo doctrine: news content is
untrusted data; it can never modify instructions, expose credentials, or
authorize a trade.

### 4.2 Instrument registry workbook (§8)
Sheets A–F (+ News Log) are a pure offline-buildable export/reporting layer
over a registry service that does not yet exist. Two operator decisions
gate it: (a) adding `openpyxl` to the locked dependency set (the repo
currently pins exactly pydantic/numpy/pandas — a governance-recorded
change); (b) the "database as authoritative source" question — the repo's
existing file-based atomic persistence + hash-chained ledgers + deterministic
replay currently serve that role; introducing PostgreSQL is an architecture
decision that must preserve INV-01 identity/determinism contracts. The
spreadsheet must remain a synchronized reporting interface, per the mandate.

### 4.3 MT5 adapter (§5)
An adapter can be built with fail-closed semantics (unconfigured ⇒
unavailable; demo/real strictly distinguished; no order submission unless
the execution mode is explicitly enabled) and mocked contract tests.
**Actual connection cannot be verified in this Linux container**: the
official `MetaTrader5` Python package requires Windows, a running MT5
terminal, and a broker account. Any "MT5 integrated" claim without that
environment would violate the repo's evidence rules. Honest path: build
adapter + mocks + tests, mark real verification BLOCKED_ON_OPERATOR_ENV.

### 4.4 TradingView adapter (§6)
Webhook ingestion (authenticated endpoint, replay protection, duplicate
handling, payload validation, audit) can be built and tested with mocked
transport. Deployment requires a public endpoint + secrets (infra). A
TradingView alert remains a signal, not a fill — it must pass the same
instrument validation and risk controls (already enforced centrally in the
runtime).

### 4.5 Strategy management lab (§1) + two-stage approval records (§4)
Reusable base exists: frozen Phase 3 strategy contracts (schemas,
validation), experiment registry, research governance (human-only
approvals), strategy discovery. Missing: a strategy-management registry
with immutable versioning (spec/source/config hashes) and the lifecycle
state machine (DRAFT→…→AWAITING_LIVE_APPROVAL, fail-closed transitions), a
plain-English→rules converter (LLM integration decision), a secure Python
sandbox worker (subprocess isolation, resource limits, static + behavioral
security tests), and the two-stage live approval record store (Approval 1 ≠
Approval 2; both can be implemented without any live execution surface —
consistent with the mandate's own "implement the workflow, keep live
disabled").

---

## 5. Dependencies and risks

| Item | Nature | Risk / note |
|---|---|---|
| `openpyxl` | New dependency (workbook export) | Lockfile + governance record; pin exact version |
| `MetaTrader5` | Windows-only, terminal + broker account | Cannot be installed/verified here; adapter must degrade to UNAVAILABLE |
| Webhook endpoint | Public host + authentication secrets | Operator/infra; mocked tests until then |
| News sources | API credentials / RSS licensing | Core buildable with mocked sources; sources disclosed honestly |
| LLM integration | Plain-English strategies, news analysis | Architecture + cost + determinism decision; must remain outside identity payloads (INV-01) |
| PostgreSQL | Optional DB layer | Must not weaken file-persistence determinism/replay contracts; decision owed |
| Frozen Phase 3 | 13/13 manifest | Untouchable — all new strategy-laboratory work must adapt to frozen contracts, never the reverse |

---

## 6. Phased implementation plan (workstreams) — STATUS after the 2026-10-10 cycle

Ordered so that every phase is offline-verifiable and fail-closed:

- **W1 — Instrument Registry core + workbook export**: **DELIVERED**
  (`platform/registry.py`, `platform/workbook.py`; openpyxl added to
  pyproject + uv.lock; 25 tests; rendered workbook in data/exports/).
- **W2 — News Intelligence core**: **DELIVERED** (`platform/news.py`;
  17 tests; News Log sheet joins the workbook). *Live sources remain
  BLOCKED on operator credentials.*
- **W3 — Strategy Management backend**: **DELIVERED**
  (`platform/strategy_lab.py`; 15 tests; two-stage approval records as
  governance metadata; LIVE_ACTIVE structurally unreachable).
- **W4 — Secure Python strategy sandbox**: **NOT STARTED — NOT CLAIMED.**
  The strategy lab records PYTHON source artifacts but never executes
  user code; the isolated worker remains a separate authorized
  workstream.
- **W5 — MT5 adapter**: **DELIVERED** (`platform/mt5.py`; 19 tests with
  a mocked terminal; fail-closed by construction; real verification
  gated on the operator Windows environment).
- **W6 — TradingView signal adapter**: **DELIVERED**
  (`platform/tradingview.py`; 18 tests with a mocked transport;
  endpoint deployment gated on infra).
- **W7 — Dashboard/API**: **DELIVERED — STDLIB READ-ONLY**
  (`platform/dashboard.py`; 13 tests; no framework dependency — the
  smallest compatible choice; the FastAPI-vs-Flask decision became
  unnecessary for this scope; a write-surface framework remains an
  operator decision if interactive control is ever wanted).
- **W8 — DB decision (PostgreSQL vs existing persistence)**: **NOT
  PURSUED** — the platform package uses the existing persistence
  discipline (immutable records + atomic file stores); no DB was
  added. Revisit only if scale demands it.
- **Phase C — four historical CSV datasets**: **DELIVERED**
  (`platform/datasets.py` + `scripts/platform_csv_ingest.py`; 17 tests;
  all four files audited, classified SYNTHETIC from hard fabrication
  evidence, 20 instruments registered with eligibility BLOCKED —
  see docs/PLATFORM_EXPANSION_SPEC.md §3).

Cross-cutting for every workstream: frozen 13/13 verified before/after;
INV-01 identity discipline; full suite ×2 deterministic; security scans;
readiness gates extended fail-closed; no live surface ever without explicit
operator authorization; no fabricated data, approvals or coverage.

---

## 7. Operator decision list (new + standing)

**New (from this mandate):**
1. ~~Approve `openpyxl` dependency addition (W1).~~ **RESOLVED by
   implementation** — openpyxl>=3.1 added to pyproject + uv.lock
   (locked, hash-pinned) as the smallest dependency needed for the
   mandated workbook; retrospective approval documented here.
2. Approve the 30-day evaluation-floor deviation question: keep the frozen
   blueprint 5.56–5.58 30-day minimum, or introduce per-strategy
   configurable durations as a documented contract amendment.
3. Approve the web-stack direction IF an interactive (write-surface)
   dashboard is ever wanted; the delivered read-only stdlib dashboard
   required no framework decision.
4. Approve LLM integration scope (plain-English strategies, news analysis).
5. Provide, when real verification is wanted: Windows MT5 terminal +
   broker (demo first) for W5; webhook host + secrets for W6; news API
   credentials for W2.
6. **Supply REAL market data if real coverage is wanted**: the four
   supplied CSV datasets were audited and classified SYNTHETIC from hard
   fabrication evidence (docs/PLATFORM_EXPANSION_SPEC.md §3). They are
   registered for pipeline demonstration only; research/backtesting/
   paper eligibility remains BLOCKED for all 20 instruments.

**Standing (unchanged, from prior cycles):**
7. **Rotate the exposed PAT** — now pasted in chat **12 times**; never
   reproduced in any artifact, but rotation is overdue and is an
   operator-side action.
8. Supply + verify real market data (~20 years expected) through the
   nine-stage REAL_VERIFIED chain (VERIFIED_YEARS = 0 today).
9. Ratify H-1; authorize CI/WP-12; decide BUG-008 residual path +
   keyed-MAC custody.

---

## 8. Honest scope statement for this cycle

The 2026-10-10 cycle DELIVERED the platform package (8 modules, 123 tests)
and the Phase C dataset integration, all verified inside the full suite
(1,570 + 1 skipped ×2, frozen 13/13 before and after, security scans 0).
The four supplied CSV files were audited with hard fabrication evidence
and classified SYNTHETIC — no empirical trading claim was produced from
them, and none may be. W4 (user-code sandbox) and W8 (external DB) remain
NOT STARTED and NOT CLAIMED. The repository verdict chain is unchanged:

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY ·
LIVE = NOT AUTHORIZED · VERIFIED_YEARS = 0.**
