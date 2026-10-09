# AI Trading Lab — Data Engine
## Platform-Expansion Master Mandate: Registration + Phase 1/2 Forensic Gap Matrix

```text
Document Type:  Mandate registration + Phase 1/2 forensic audit (READ-ONLY)
Phase:          Platform expansion (strategy lab, instrument registry workbook,
                MT5/TradingView integration, dashboard, news intelligence §11 A–M)
Authority:      B — CURRENT SUPPORTING
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-09
Supersedes:     —
Superseded By:  —
Source Evidence: git (HEAD 779df16 on BOTH refs, ls-remote verified), repo-wide
                 symbol searches this session, module inventories, full-suite
                 re-run 1,447 + 1 skipped (37.07 s, uv --frozen), frozen
                 manifest 13/13, pyproject/uv.lock dependency review
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
| 5 | MetaTrader 5 integration | **MISSING** | Zero `metatrader`/`mt5` code. `MetaTrader5` Python package is Windows-only + requires a running terminal + broker account → **real verification BLOCKED on operator environment** (see §5) |
| 6 | TradingView integration (alerts/webhooks) | **MISSING** | Zero `tradingview`/`webhook` code. Receiver needs a publicly reachable endpoint + authentication secrets → **deployment BLOCKED on infra/operator** |
| 7 | Automatic instrument discovery & registration | **PARTIAL** | Canonical `Instrument` schema exists (`schemas.py`: symbol/asset_class/base/quote/exchange/venue/contract_type/currency/provider_symbol); CSV ingestion exists (`ingestion.py`, `provider.py` — input side). **No discovery service from MT5/market-data sources; no eligibility workflow**. Note: `discovery/` package is STRATEGY discovery, not instrument discovery |
| 8 | Central Instrument Registry workbook (Sheets A–F + News Log) | **MISSING** | Zero xlsx/openpyxl/excel/spreadsheet code; no CSV export either. Buildable offline — requires an **openpyxl dependency addition** (repo pins exactly pydantic/numpy/pandas) → operator approval logged in §7. DB-as-authoritative-source: repo uses file-based atomic persistence + hash-chained ledgers; PostgreSQL is an architecture decision (§5) |
| 9 | Dashboard & approval workflow UI | **MISSING** | Zero fastapi/flask/uvicorn/dashboard code; the repo is a Python engine + pytest. Web stack choice is an operator architecture decision |
| 10 | AI market risk & crash prediction | **IMPLEMENTED** | `prediction/` ~30 modules: baselines, LSTM, Transformer, ensemble, calibration, regimes, crash framework, scenarios/stress, drift, uncertainty, event evaluation, red-team matrix (45/45 defended), abstention gates. Honest limits: VERIFIED_YEARS = 0; advisory-only (cannot bypass risk limits — tested) |
| 11 A–M | Real-time web news intelligence | **MISSING** | The only `news` occurrence in the entire source tree is `TemporalDataType.NEWS` (`pit/temporal.py:30`) — a PIT temporal classification, **not** a news module. No ingestion, no dedup, no entity→instrument mapping, no sentiment, no economic calendar, no news-PIT backtest boundary, no News Log sheet |
| 12 | Testing & reliability discipline | **IMPLEMENTED** (as a standing practice) | 46 test files / 1,447 + 1 skipped; determinism ×2 per cycle; mutation gates (15/15, 31/31); failure injection (24 scenarios); frozen verification before/after every cycle. New modules must extend per category |
| 13 | Development workflow | **Phase 1 + 2 COMPLETE (this document)** | Phases 3–10 mapped in §6 |
| 14 | Final deliverables | **PER-PHASE, FUTURE** | Produced as each workstream lands; consolidated at program end |

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

## 6. Phased implementation plan (workstreams)

Ordered so that every phase is offline-verifiable and fail-closed:

- **W1 — Instrument Registry core + workbook export**: registry service,
  eligibility model (registration ≠ eligibility), discovery-state fields,
  XLSX/CSV export with Sheets A–F scaffold + sync semantics (append-only,
  unique IDs, last-sync display). *Blocked only on openpyxl approval.*
- **W2 — News Intelligence core**: §4.1 scope with mocked sources + News
  Log sheet (joins W1). *Real sources later, on credentials.*
- **W3 — Strategy Management backend**: registry, immutable versioning,
  lifecycle state machine, two-stage approval records (always-deny live).
- **W4 — Secure Python strategy sandbox**: isolated worker, resource
  limits, security test battery (malicious imports, fs access, subprocess,
  resource exhaustion, order-path bypass).
- **W5 — MT5 adapter**: fail-closed interface + mocked contract tests;
  real verification gated on operator environment.
- **W6 — TradingView signal adapter**: webhook receiver contract + mocked
  tests; deployment gated on infra.
- **W7 — Dashboard/API**: only after the architecture decision (FastAPI or
  compatible choice).
- **W8 — DB decision** (PostgreSQL vs existing persistence), if pursued.

Cross-cutting for every workstream: frozen 13/13 verified before/after;
INV-01 identity discipline; full suite ×2 deterministic; security scans;
readiness gates extended fail-closed; no live surface ever without explicit
operator authorization; no fabricated data, approvals or coverage.

---

## 7. Operator decision list (new + standing)

**New (from this mandate):**
1. Approve `openpyxl` dependency addition (W1).
2. Approve the 30-day evaluation-floor deviation question: keep the frozen
   blueprint 5.56–5.58 30-day minimum, or introduce per-strategy
   configurable durations as a documented contract amendment.
3. Approve web-stack choice for the dashboard (W7) and the DB question (W8).
4. Approve LLM integration scope (plain-English strategies, news analysis).
5. Provide, when real verification is wanted: Windows MT5 terminal +
   broker (demo first) for W5; webhook host + secrets for W6; news API
   credentials for W2.

**Standing (unchanged, from prior cycles):**
6. **Rotate the exposed PAT** — now pasted in chat **11 times**; never
   reproduced in any artifact, but rotation is overdue and is an
   operator-side action.
7. Supply + verify real market data (~20 years expected) through the
   nine-stage REAL_VERIFIED chain (VERIFIED_YEARS = 0 today).
8. Ratify H-1; authorize CI/WP-12; decide BUG-008 residual path +
   keyed-MAC custody.

---

## 8. Honest scope statement for this cycle

This cycle implemented **no new platform features**. It verified the push
state, re-ran the full suite and frozen checks first-hand, registered the
mandate, and published this Phase 1/2 gap matrix so that all future
implementation claims are measured against a fixed, evidence-based
baseline. The repository verdict chain is unchanged:

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY ·
LIVE = NOT AUTHORIZED · VERIFIED_YEARS = 0.**
