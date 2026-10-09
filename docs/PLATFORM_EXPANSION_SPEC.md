# AI Trading Lab — Platform Expansion Specification

```text
Document Type:  Implementation specification + verification record
Phase:          Platform expansion (Phases C–H + J of the master mandate:
                CSV dataset integration, strategy lab, instrument registry
                + workbook, MT5/TradingView adapters, news intelligence,
                read-only dashboard/API)
Authority:      A — CURRENT AUTHORITATIVE for the platform package
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-10
Supersedes:     —
Superseded By:  —
Source Evidence: src/data_engine/platform/ (8 modules, ~2,900 lines),
                 tests/test_platform_*.py (8 files, 123 tests),
                 data/manifests/ + data/exports/ (Phase C evidence run),
                 full-suite 1,570 passed + 1 skipped x2 (uv --frozen,
                 45.6 s / 44.7 s), frozen manifest 13/13 before AND after,
                 security scans 0 credential values
```

---

## 1. Scope and authority

This specification governs the `data_engine.platform` package delivered
for the platform-expansion master mandate. Every module is **advisory
and read-only with respect to the governed trading runtime**: nothing
in this package can submit, alter or bypass orders, risk gates, kill
switches or readiness gates. The paper-trading runtime
(`data_engine.runtime`) remains the only execution surface; live
trading remains **NOT AUTHORIZED** repository-wide.

`PLATFORM_CONTRACT_VERSION = "1.0.0"` follows the repository
contract-versioning discipline.

---

## 2. Module inventory (all IMPLEMENTED + TESTED)

| Module | Mandate phase | Summary | Tests |
|---|---|---|---|
| `events.py` | E/J | Append-only `AuditLog` + `PlatformAuditEvent`; caller-supplied timestamps only (INV-01); fail-closed on unknown components | via registry/lab tests |
| `registry.py` | E | `InstrumentRegistry` + immutable `InstrumentRecord`; deterministic `canonical_instrument_id` (SHA-256 over canonical identity fields, cross-process stable); provider-symbol mappings; evidence-gated `set_data_state` (REAL_VERIFIED requires verified coverage evidence — unreachable from CSV ingestion by construction); `authorize_live` records the refusal and returns the record unchanged | 15 |
| `workbook.py` | E | `WorkbookExporter` rendering Sheets A–G (Instrument Registry, Trade Log, Strategy Performance, Open Positions, Market Watch, System Audit Log, News Log); paper/demo/live mode separation as first-class columns; duplicate trade-id refusal; XLSX (openpyxl, filters + frozen header) + byte-deterministic CSV export | 10 |
| `strategy_lab.py` | D | `StrategyLab`: immutable versioning (spec/config/source hashes; no-op versions refused; evidence reset on new version); server-controlled lifecycle state machine; evidence-gated analytical transitions; LIVE_APPROVED requires explicit `OperatorApproval` with scope match; LIVE_ACTIVE structurally unreachable; archived strategies never re-enabled | 15 |
| `news.py` | H | `NewsIntelligenceService`: content-hash dedup (source is part of identity — syndicated copies are distinct); retrieval-before-publication refused; PIT `items_visible_at`; staleness marking; entity resolution with ambiguity FLAGGED (never auto-assigned); `EconomicEvent` calendar where surprise exists only when BOTH consensus and actual are present | 17 |
| `mt5.py` | F | `MT5Adapter`: UNAVAILABLE-by-construction on non-Windows environments (BLOCKED_ON_OPERATOR_ENV); injected-terminal-session protocol for tests; DEMO/REAL account-mode discipline; unknown mode is UNKNOWN (never assumed); all reads fail closed before connect; order submit/modify/cancel REFUSED ALWAYS (`MT5OrderRefusedError`) | 19 |
| `tradingview.py` | G | `TVSignalValidator`: strict payload schema (extra fields forbidden); HMAC-SHA256 authentication over the ENTIRE canonical payload including the signal body (constant-time compare); replay window; nonce dedup; unknown-instrument fail-closed routing into `TVAdvisoryIntent` — a signal, never an order | 18 |
| `datasets.py` | C | CSV audit + ingestion (§3 below) | 17 |
| `dashboard.py` | J | Read-only `PlatformSnapshot` + stdlib HTTP server (§5 below) | 13 |

Package tests: 8 files / 123 tests, all passing inside the full suite
(1,570 passed + 1 skipped).

---

## 3. Historical CSV dataset integration (Phase C) — evidence record

The four supplied files were audited and ingested through the platform
pipeline (`scripts/platform_csv_ingest.py`, evidence run 2026-10-10):

| File | Rows | Instruments | Coverage | Integrity | Classification |
|---|---|---|---|---|---|
| crypto_daily_2006_2026.csv | 30,316 | 4 | 2006-01-01..2026-10-01 | duplicates 0, OHLC OK, chronology OK | **SYNTHETIC** |
| forex_daily_2006_2026.csv | 32,484 | 6 | 2006-01-02..2026-10-01 | duplicates 0, OHLC OK, chronology OK | **SYNTHETIC** |
| metals_daily_2006_2026.csv | 21,656 | 4 | 2006-01-02..2026-10-01 | duplicates 0, OHLC OK, chronology OK | **SYNTHETIC** |
| stocks_indices_daily_2006_2026.csv | 32,484 | 6 | 2006-01-02..2026-10-01 | duplicates 0, OHLC OK, chronology OK | **SYNTHETIC** |
| **TOTAL** | **116,940** | **20** | | | |

### 3.1 Fabrication evidence (hard, reproducible)

1. **TSLA prints OHLC on 1,171 rows before its 2010-06-29 IPO**
   (first OHLC 2006-01-02). Tesla was not a public company in 2006;
   pre-IPO candles cannot exist in real data.
2. **27,449 crypto rows attribute trading to venues/quote assets that
   did not exist on the row date** — the Exchange column reads
   "Binance / Kraken" (etc.) from 2006; Binance was founded 2017-07-14
   and USDT launched 2014-10-06.
3. **270 stock rows carry full OHLC on dates the file itself marks
   `Closed_Holiday`** — and at prices wildly off the instruments' own
   paths (e.g. US500 938.52 on 2006-07-04 against a January 2006 level
   of 1242 and a real-world July 2006 level of ~1270). Real closed
   markets print no candle.
4. **Uniform generation grid**: every non-crypto instrument has exactly
   5,414 rows on an identical, gap-free weekday grid (only 1- and
   3-day gaps, zero holiday variation across 20 years) — including
   instruments that provably began trading mid-range. This is a
   construction signature, not a real multi-instrument history.
5. **Implausible endpoints** (recorded as anomalies, not proof):
   USDCHF 4.37, USDJPY 354.21, XAGUSD 3.70, US500 1,393.73 after 20
   years (while US100 multiplies 5x) — consistent with unbounded
   synthetic drift, inconsistent with any remotely comparable
   historical structural break.

### 3.2 What the data is NOT

- The 2006 starting anchors DO match real history (EURUSD 1.1841,
  XAUUSD 524.48, US500 1242.32, AAPL split-adjusted 2.53; anchors
  6/6, 4/4, 5/5 within tolerance). This proves **calibration to real
  history, not reality**: the files are synthetic price paths seeded
  from real 2006 levels.
- The crypto pre-launch markers are themselves accurate (BTC active
  from 2010-07-18 = Mt.Gox launch; ETH 2015-08-07; SOL 2020-04-10) —
  the generator knew real listing dates, which strengthens the
  classification of the family as deliberately constructed.
- **VERIFIED_YEARS remains 0.** No dataset was promoted toward
  REAL_VERIFIED; the audit module cannot assign that state by
  construction (it requires the nine-stage runtime verification chain
  plus human approval).

### 3.3 Registry consequences (fail-closed)

All 20 instruments are registered with their ORIGINAL identifiers
preserved as `csv:<kind>` provider symbol mappings, discovery source
`csv:<kind>:<file>`, and data state **SYNTHETIC**. Per registry
policy:

- `RESEARCH` / `BACKTESTING` eligibility: **BLOCKED** for every
  instrument (synthetic data cannot back valid empirical results).
- `PAPER_TRADING`: **BLOCKED** (requires REAL_VERIFIED).
- `LIVE_TRADING`: **NOT AUTHORIZED** (unchanged, repository-wide).

No backtest, walk-forward evaluation, or performance figure was
produced from these files, and none may be until real verified data
arrives through the governed chain.

### 3.4 Immutable inputs + reproducible manifests

- Original files recorded verbatim under `data/raw/` (SHA-256 in each
  manifest; see §3 table files `data/manifests/<kind>_manifest.json`).
- `data/manifests/import_summary.json` — totals + dataset ids +
  manifest hashes.
- `data/exports/ai_trading_lab_workbook.xlsx` + per-sheet CSVs — the
  central workbook rendered from the registered authoritative state.
- `data/exports/dashboard_snapshot.json` — read-only projection.

Manifests are deterministic functions of file content (INV-01): the
audit contains no wall-clock, no paths, no environment data.

---

## 4. Strategy management lab (Phase D) — governance contract

- **Versioning**: spec/config/source are canonical-JSON hashed; any
  material change creates a new immutable version; a no-op version is
  refused; a new version resets evidence to empty (prior evidence
  never certifies a modified version; evidence records are version-
  bound).
- **Lifecycle**: DRAFT → SUBMITTED → STATIC_VALIDATION → VALIDATED →
  BACKTEST_RUNNING → BACKTEST_PASSED → PAPER_RUNNING → PAPER_PASSED →
  EVIDENCE_REVIEW → AWAITING_LIVE_APPROVAL → LIVE_APPROVED →
  AWAITING_FINAL_CONFIRMATION, with failure/suspension/revocation
  branches. Evidence gates: `static_check`, `backtest_report`,
  `paper_report`, `eligibility_review`, `operator_approval` — checked
  BEFORE the legality table so the missing-evidence refusal is always
  the most informative one.
- **Analytical evidence-gated targets** (VALIDATED, BACKTEST_PASSED,
  PAPER_PASSED) may be entered directly when the current version holds
  the required evidence (interactive flows may compress bookkeeping
  steps). **Governance targets** (AWAITING_LIVE_APPROVAL,
  LIVE_APPROVED) additionally require the full state chain — evidence
  alone never shortcuts the approval chain. Terminal states
  (ARCHIVED, REVOKED) are never revivable by evidence.
- **LIVE_APPROVED** requires an explicit `OperatorApproval` whose
  strategy id AND version match; scope mismatch is refused.
- **LIVE_ACTIVE is structurally unreachable**: the transition raises
  with an explicit policy refusal. No live execution surface exists.
- **No user code execution**: `PYTHON` strategies require a source
  artifact recorded at creation, but this module never executes it.
  The isolated sandbox worker (gap-matrix W4) remains a separate,
  unclaimed workstream. This module manages METADATA only.

---

## 5. Read-only dashboard/API (Phase J)

`dashboard.py` provides the smallest compatible web surface — **no
framework dependency** (stdlib `http.server`):

- `build_snapshot(...)` projects the authoritative services (registry,
  strategy lab, news, audit log, datasets, market watch, positions,
  trades, performance, risk alerts, system health) into a frozen
  `PlatformSnapshot`.
- `DashboardServer` binds loopback by default and serves exactly two
  GET routes: `/api/snapshot` (JSON) and `/` (server-rendered HTML).
  Every non-GET method → 405; every unknown path → 404. There is no
  write surface, no parameterized file access, no template engine, no
  user input evaluated anywhere.
- **Honesty contracts (tested)**: LIVE renders "NOT AUTHORIZED"
  everywhere; market-watch rows without provider data render
  `no_data` — never a fabricated price; paper readiness and blocked
  gates render verbatim from the supplied health view; untrusted
  content (news headlines) is HTML-escaped.
- The snapshot's `synchronized_at` is a caller-supplied logical
  timestamp (INV-01).
- Deployment (binding a real interface, TLS, reverse proxy) is an
  operator infrastructure decision; the module defaults to
  `127.0.0.1`.

---

## 6. Security posture

- External content (news, TradingView payloads) is UNTRUSTED DATA:
  validated and classified only; never executed; never able to alter
  instructions, expose secrets or authorize trading.
- TradingView authentication: HMAC-SHA256 over the full canonical
  payload (INCLUDING the signal body — a mid-implementation defect
  where the digest did not cover `signal` was caught by the tamper
  test and FIXED before commit); constant-time comparison; the shared
  secret is supplied by a caller-provided provider function and never
  stored.
- MT5 order surface: refusal is unconditional, including on a
  connected REAL account (tested).
- The red-team source scan (`test_redteam.py::TestSecurity`) applies
  to the new modules: no `eval(`/`exec(`/`subprocess.`/`os.popen`/
  `pickle` anywhere in `src/` (a method name containing the literal
  substring `eval(` was renamed rather than weakening the scanner).
- Secrets: 0 credential values in the working tree, staged files,
  `.git/config` (verified pre-commit).

---

## 7. Honest limitations and remaining blockers

1. **Real market data remains absent** (VERIFIED_YEARS = 0). The four
   CSV files are SYNTHETIC — usable for pipeline demonstration only,
   BLOCKED for research/backtesting/paper eligibility by registry
   policy. REAL_VERIFIED requires the nine-stage chain + human
   approval.
2. **MT5 real connectivity** — BLOCKED_ON_OPERATOR_ENV (Windows
   terminal + broker account). The adapter fails closed by
   construction; contract verified with a mock terminal.
3. **TradingView webhook endpoint deployment** — requires operator
   infrastructure (HTTPS host, secret distribution). The validation/
   routing contract is implemented and tested with a mocked transport.
4. **News real sources** — the offline core is complete; live
   RSS/API ingestion requires operator credentials and network
   egress. Nothing claims live news coverage.
5. **Python strategy sandbox (W4)** — NOT implemented, NOT claimed.
   The strategy lab manages metadata; user code never executes in the
   trusted process.
6. **Paper trading readiness** — unchanged: PAPER_READY = FALSE —
   BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY (REAL_DATA_READY and
   GOVERNANCE_READY gates). The platform package does not modify the
   31-gate runtime readiness evaluation in any way.
7. **Live trading** — NOT AUTHORIZED. No live execution surface
   exists anywhere in the repository, including the new adapters.

---

## 8. Verification record (this cycle)

- Full suite: **1,570 passed + 1 skipped** — run TWICE (45.64 s /
  44.65 s, cache disabled) — deterministic.
- Frozen Phase 3 manifest: **13/13 PASS** before AND after all
  implementation (independent script, authoritative manifest).
- Security: red-team source scans green; secret scans 0 values in
  tree/staged/`.git/config`.
- Phase C evidence run reproducible:
  `uv run --frozen python scripts/platform_csv_ingest.py` (script
  lives outside the repo with the other evidence scripts; artifacts
  under `data/`).
- All 20 registered instrument ids are cross-process deterministic
  (subprocess test).
