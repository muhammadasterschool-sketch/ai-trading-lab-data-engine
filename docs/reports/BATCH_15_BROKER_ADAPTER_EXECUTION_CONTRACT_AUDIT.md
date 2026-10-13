# BATCH 15 — BROKER ADAPTER & EXECUTION CONTRACT AUDIT + VENUE/CATALOG COMPLETION

> **Batch type:** audit + verified-gap implementation (the mandate's
> §4 scope + the three code-addressable items confirmed by the Batch 11
> audit §9 and carried in the Batch 14 dependency map as C-1/C-2/C-3).
> No push, merge, rebase, reset, or history rewrite was performed.
>
> **Repository:** `muhammadasterschool-sketch/ai-trading-lab-data-engine`
> **Base commit:** `1f2c689` (Batch 14 tip)
> **Dedicated branch:** `feat/batch-15-venue-catalog-completion`
> **Date:** 2026-10-13
>
> **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY.**
> **LIVE TRADING NOT AUTHORIZED.** Nothing in this batch changes either.

## 1. Pre-batch protocol (mandate §14)

| Check | Result |
|---|---|
| `git status --short` at start | CLEAN (Batch 14 committed at `1f2c689`) |
| Test baseline | 2,233 passed + 1 skipped (Batch 14 post-commit, 79.22s) |
| Relevant history inspected | Batches 5–7 (broker layer), Batch 8 §real-vs-mock matrix, Batch 11 §4 items 9–10 + §9 confirmed items |
| Smallest safe change identified | (a) subclass seams on `MT5StyleMockAdapter` (defaults preserve behavior); (b) two new mock adapter modules; (c) two new capability descriptors + registry extension; (d) one new deterministic artifact module + generator; (e) tests: 2 new files + 2 strengthened existing files; (f) 2 generated artifacts. NO existing behavior changed. |

## 2. Per-venue implementation status (mandate §4 — first-hand)

Connection status vocabulary: **MOCK-ONLY** = deterministic in-memory
adapter, no network, structurally refused at REAL execution mode
(`session.py:309` + descriptor registration validator); production /
sandbox connectivity does not exist anywhere in this repository and is
NEVER claimed.

| Venue | Adapter (file) | Status | Asset classes served | Instruments | Order kinds | TIF | SL/TP | Position mode | Idempotency | Native error codes |
|---|---|---|---|---|---|---|---|---|---|---|
| Paper | `adapters/paper.py` | **MOCK-ONLY** (reference surface) | crypto + FX | BTCUSDT, EURUSD | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC, FOK, DAY | ATTACHED | NETTING | INTERNAL_JOURNAL | (normalized) |
| MT5 (generic class) | `adapters/mt5_mock.py` | **MOCK-ONLY** | FX, metals, crypto CFD | EURUSD, XAUUSD, BTCUSD | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | 10014/10019/10036/10027 |
| **Exness** | `adapters/exness_mock.py` — **NEW (C-1)** | **MOCK-ONLY** (MT5 terminal class) | FX, metals, crypto CFD | EURUSD, XAUUSD, BTCUSD | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | MT5 retcodes (inherited) |
| **XM** | `adapters/xm_mock.py` — **NEW (C-1)** | **MOCK-ONLY** (MT5 terminal class) | FX, metals, crypto CFD | EURUSD, XAUUSD, BTCUSD | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | MT5 retcodes (inherited) |
| Binance | `adapters/binance_mock.py` | **MOCK-ONLY** (spot REST/filter semantics) | crypto | BTCUSDT, ETHUSDT | MARKET, LIMIT | GTC, IOC, FOK | SEPARATE_ORDERS | BALANCES_ONLY | NATIVE_CLIENT_ID | -1013/-2010/429/418 |
| Bybit | `adapters/bybit_mock.py` | **MOCK-ONLY** (v5 spot/linear) | crypto | BTCUSDT, ETHUSDT | MARKET, LIMIT | GTC, IOC, FOK | ATTACHED | NETTING (one-way) | NATIVE_CLIENT_ID (orderLinkId) | 10004/10001/10010/10014/110007 |
| Bitget | `adapters/bitget_mock.py` | **MOCK-ONLY** (spot v2) | crypto | BTCUSDT, ETHUSDT | MARKET, LIMIT | GTC, IOC | SEPARATE_ORDERS | BALANCES_ONLY | NATIVE_CLIENT_ID (clientOrderId) | 40001/43007/43025/42911 |

### 2.1 Cross-venue contract facts (identical for all seven, first-hand anchors)

- **Authentication / secret boundary:** `connect(BrokerCredential(account_id,
  secret))` binds ONE account; every subsequent call refuses other
  account ids (cross-account leakage defense, `interface.py` contract).
  No credential material may appear in return values, error messages or
  logs — enforced by `redaction.py` (`scrub_text`, `redact_mapping`,
  `assert_no_secret_material`) and tested in
  `test_broker_neutral_core.py`. Credentials are NEVER stored in
  descriptors/registries (credential-free by schema, `extra="forbid"`).
- **Instrument discovery & symbol normalization:** fail-closed
  `discover_instruments` (`brokers/instruments.py`): disconnected
  adapter refused, foreign specs refused, duplicate symbols refused,
  capability drift refused, unregistered venue refused; canonical
  `symbol` ↔ venue `broker_symbol` normalization per spec; registry
  sync merges the same canonical identity across venues (never forks).
- **Order types / precision / minimum size / capability validation:**
  session consults the frozen descriptor BEFORE any venue call —
  unsupported kinds/TIFs fail closed at the boundary
  (`test_broker_session_guards.py`); `InstrumentSpec` tick/lot/min/
  max/notional validated with venue-native rejection codes
  (definitive REJECTED acks, not exceptions).
- **Order lifecycle:** idempotent submit per `client_order_id`
  (comment-field discipline at MT5-class venues); cancel idempotent
  with terminal orders returned unchanged; `order_status` venue truth;
  partial-fill accounting; UNKNOWN outcomes raise typed errors →
  journal UNKNOWN → reconcile-from-venue-truth before retry.
- **Rate limits / retries / reconnects / reconciliation / error
  mapping:** deterministic `RateLimitPolicy` enforcement per venue
  (venue-native codes, `retry_after`); typed error taxonomy with
  `RETRYABLE_CATEGORIES` (`errors.py`); `BrokerSession.reconnect()`
  re-binds with the SAME credential (fail-closed if absent); per-venue
  reconciliation styles (ORDER_FILL_POLL / BALANCE_SNAPSHOT /
  POSITION_STATEMENT); journal persistence + fail-closed recovery
  across restart (`session.py` `_load_journal`).
- **Venue-native codes preserved as audit data** in normalized errors
  (never parsed as control flow) — representative codes re-verified
  against live venue docs when the REAL adapter phase is separately
  operator-authorized.

### 2.2 Data-plane venues (not execution adapters — no order surface)

- `platform/mt5.py` — READ-ONLY MT5 data adapter (operator Windows
  environment); order surface REFUSED unconditionally, including on a
  connected REAL account (tested).
- `providers/binance_public.py` — public/unauthenticated market-data
  transport (credentials refused at construction; see Batch 14 §4).

These are intentional plane separations (verified distinct in Batch 11
§6); neither is an execution venue and neither claims connectivity
status beyond its documented boundary.

## 3. Implemented work (the three confirmed code-addressable items)

### 3.1 C-1 — Exness + XM venue disposition: dedicated MT5-class mock adapters

- **Design decision:** Exness and XM are MT5/MT4 brokerages — their
  terminal semantics ARE the MT5 class the repository already encodes.
  The honest completion is DEDICATED mock adapters inheriting
  `MT5StyleMockAdapter` verbatim (hedging tickets, attached SL/TP,
  volume-step lots, comment-field idempotency, margin-style
  account-currency accounting, MT5 retcode mapping) with each venue's
  OWN identity: new descriptors `EXNESS_MOCK_CAPABILITIES` /
  `XM_MOCK_CAPABILITIES` (broker_id `exness-mock` / `xm-mock`,
  registered in `default_registry()` — now SEVEN venues), own
  Standard-account instrument sets (EURUSD, XAUUSD, BTCUSD), and
  per-venue audit narratives documenting the operator-side account
  verification boundary (symbol suffixes / server names per account
  type; UNVERIFIED brokers are not connectable by design).
- **Smallest-safe-change seam:** `MT5StyleMockAdapter.__init__` gained
  optional `capabilities` / `instruments` kwargs (defaults preserve the
  original `mt5-mock` behavior exactly — every existing caller and
  test unchanged in expectation).
- **NO real connectivity is claimed or implied.** The venue notes
  state the REAL adapter phase is separately operator-authorized.

### 3.2 C-2 — deterministic instrument-catalog report artifact

- New module `brokers/catalog_report.py`:
  `build_catalog_report(catalogs, platform_registry, at)` +
  `render_catalog_report_markdown` — frozen pydantic report models with
  honest-invariant validators (eligibility NEVER granted; LIVE records
  must render "Not Authorized"; fabrication refused).
- Generated artifact `docs/reports/INSTRUMENT_CATALOG_REPORT.md` (7
  venue sections; 5 canonical platform identities with merged venue
  mappings — BTC/USDT ×4 venues, BTC/USD ×3, ETH/USDT ×3, EUR/USD ×4,
  XAU/USD ×3 — all mappings UNVERIFIED; fail-closed discovery
  behaviors referenced to their existing tests; known limitations
  documented honestly, including the canonical asset-class
  simplification in `brokers/instruments.py::_canonical_instrument`).
- Generator script `scripts/generate_broker_catalog_artifacts.py`
  (fixed discovery timestamp — audit provenance only, INV-01; byte-
  identical regeneration).

### 3.3 C-3 — broker capability matrix artifact

- Same module: `build_capability_matrix(registry)` +
  `render_capability_matrix_markdown` — every descriptor dimension
  rendered (order kinds, TIFs, SL/TP semantics, position mode,
  idempotency mechanism, reduce-only, account modes, rate-limit shape,
  reconciliation style, execution mode) + per-venue notes + the
  unsupported-order-kinds-per-venue table (what the session refuses
  BEFORE the venue).
- Generated artifact `docs/reports/BROKER_CAPABILITY_MATRIX.md`
  (7 venues, all MOCK_DETERMINISTIC, LIVE TRADING NOT AUTHORIZED
  banner; refusal of a fabricated authorized state is TESTED).

## 4. Tests (RED-first where new)

| File | Kind | Tests |
|---|---|---|
| `tests/test_broker_exness_xm_venues.py` | **NEW — RED-first** (import-RED verified first-hand: `ImportError: cannot import name 'ExnessMT5MockAdapter'` before implementation) | 33 — descriptors (7-venue registry, MT5-class semantics, REAL-mode refusal, drift refusal), adapters (hedging, attached SL/TP, FOK refusal, retcode 10014, unknown-symbol fail-closed, rate limit 10027, comment-field idempotency, close-position P&L, per-broker instrument ownership), cross-venue catalog (3 MT5-class venues discover; EUR/USD one canonical identity with 3 mappings; registration ≠ eligibility incl. LIVE "Not Authorized"; restart determinism + idempotent re-sync) |
| `tests/test_broker_catalog_artifacts.py` | **NEW** | 13 — capability matrix (7 rows, MT5-class rows, all MOCK_DETERMINISTIC, fabricated-authorized refusal, render content, determinism, **byte-compare vs committed artifact**) + catalog report (7 sections, 5 canonical identities with exact merged-mapping sets, honest eligibility statuses, fabricated-eligibility refusal, render content, determinism, **byte-compare vs committed artifact**) |
| `tests/test_broker_adapter_contract.py` | **STRENGTHENED** | shared contract suite parametrization 5 → 7 venues (paper/mt5/exness/xm/binance/bybit/bitget) — the SAME normalized-surface contract now proven at Exness/XM; zero assertions weakened |
| `tests/test_broker_neutral_core.py` | **STRENGTHENED** | registry pin updated five → seven mock venues (explicit comment: Batch 7 Bitget, Batch 15 Exness/XM) |

One test-side expectation correction during development (recorded
honestly): `test_synced_instruments_are_discovered_not_eligible`
initially expected PAPER_TRADING eligibility "Blocked"; the platform
registry's actual honest semantics return "Discovered" when no data
state exists (checked BEFORE capability branches) — the test was
corrected to assert the registry's real contract, which demonstrates
registration ≠ eligibility even more strongly. No production code was
changed to satisfy any test.

## 5. Verification results (actual)

| Check | Result |
|---|---|
| RED-first evidence | `ImportError: cannot import name 'ExnessMT5MockAdapter'` captured at `tests/test_broker_exness_xm_venues.py` BEFORE implementation |
| New venue tests | **33 passed** |
| New artifact tests | **13 passed** (including byte-compare of both committed artifacts against fresh regeneration) |
| Focused broker suite (8 files) | **432 passed** (adapter contract ×7 venues, neutral core, session guards, instrument discovery, Exness/XM, catalog artifacts, runtime broker integration, authoritative venue) |
| Full suite | **2,333 passed + 1 skipped, 31 warnings, 79.44s** — baseline 2,233+1 → **+100 tests, ZERO regressions** (single benign skip unchanged) |
| Frozen strategy contracts | **PASS 11/11** byte-identical to `main@13fdc7e` |
| Manifest integrity | **PASS 13/13** |
| Secret scan | **PASS 0** across all 85 commits + working tree |
| Diff review | 14 files, +1,754/−34 — EXACTLY the Batch 15 scope; no unrelated files touched; frozen blobs untouched |

## 6. Honest scope boundaries

- Every venue in the capability matrix is MOCK_DETERMINISTIC; no
  production or sandbox connectivity exists; REAL execution modes are
  refused at descriptor registration AND at session construction.
- Exness/XM venue notes document the operator-side per-account
  verification boundary (symbol suffixes, server names, account
  modes) — required BEFORE any future real adapter activation.
- The two generated artifacts carry GENERATED + honesty banners; the
  report models structurally refuse fabricated
  authorized/eligible states; tests byte-pin the committed artifacts
  to fresh regeneration (no silent drift).
- 29 PASS / 3 FAIL readiness unchanged; no gate verdict touched;
  PAPER_READY = FALSE; LIVE TRADING NOT AUTHORIZED.

## 7. Commands executed (exact)

```bash
git status --short                       # clean at start; reviewed before commit
uv run pytest -q -p no:cacheprovider tests/test_broker_exness_xm_venues.py   # RED (ImportError) → 33 passed
uv run pytest -q -p no:cacheprovider tests/test_broker_catalog_artifacts.py  # 13 passed
uv run pytest -q -p no:cacheprovider <8 broker test files>                   # 432 passed
uv run pytest -q -p no:cacheprovider                                          # 2,333 + 1 skipped
uv run pytest --collect-only -q                                               # 2,334 collected
uv run python scripts/generate_broker_catalog_artifacts.py                    # deterministic artifacts
python3 /home/z/my-project/scripts/batch9_gate_verify.py                      # 11/11, 13/13, 0, 0
git diff --cached --stat                                                      # 14 files, +1,754/−34
```

No `git push`, no merge, no rebase, no history rewrite, no credential
use (none exists in the environment).

## 8. Commit record

- New: `src/data_engine/brokers/adapters/exness_mock.py`,
  `src/data_engine/brokers/adapters/xm_mock.py`,
  `src/data_engine/brokers/catalog_report.py`,
  `scripts/generate_broker_catalog_artifacts.py`,
  `docs/reports/BROKER_CAPABILITY_MATRIX.md`,
  `docs/reports/INSTRUMENT_CATALOG_REPORT.md`,
  `tests/test_broker_exness_xm_venues.py`,
  `tests/test_broker_catalog_artifacts.py`.
- Modified: `brokers/capabilities.py` (+2 descriptors, registry=7),
  `brokers/adapters/mt5_mock.py` (subclass seams, defaults preserved),
  `brokers/adapters/__init__.py`, `brokers/__init__.py` (exports),
  `tests/test_broker_adapter_contract.py` (7-venue parametrization),
  `tests/test_broker_neutral_core.py` (registry pin),
  `MASTER_DOCUMENTATION_INDEX.md` (v2.19.0 → v2.20.0).
- Branch: `feat/batch-15-venue-catalog-completion` from `1f2c689`.
  Post-commit verification: full suite + forensic gates re-run at the
  new HEAD (recorded in the worklog).

## 9. Final verification verdict (per mandate §4)

| Mandate item | Status |
|---|---|
| Per-venue implementation status reported (adapter, asset classes, discovery, auth boundary, order types, precision, lifecycle, rate limits, retries, reconnects, reconciliation, error mapping, connection status) | **PASS** — §2 tables with first-hand anchors |
| "Do not claim that a broker is supported merely because its name appears in a registry" | **PASS** — every registry row maps to a working deterministic adapter + tests; data-plane venues documented as non-execution; Exness/XM now REAL adapters at mock level (previously absent) |
| Implement missing broker-neutral contracts + deterministic tests where gaps are verified | **PASS** — C-1/C-2/C-3 closed: +100 tests, all green; artifacts byte-pinned |
| No real credentials, no real orders, external integration stays blocked | **PASS** — MOCK_DETERMINISTIC enforced; secret scan 0; LIVE NOT AUTHORIZED |
| Frozen contracts / manifest / no unrelated changes | **PASS** — 11/11, 13/13, diff scoped exactly |

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE
TRADING NOT AUTHORIZED.** Batch 15 stops here. Next per the dependency
map: **Batch 16 — paper-execution and risk assurance audit**.
