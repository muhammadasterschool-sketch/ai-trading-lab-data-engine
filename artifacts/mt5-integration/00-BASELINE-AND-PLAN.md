# Exness MT5 DEMO Read-Only Market-Data Integration — Baseline & Implementation Plan

Status: **PLAN (pre-implementation)** — written on the feature branch
`feat/exness-mt5-demo-market-data` BEFORE any source edit.

- Base commit: `4cc6782c9804fd689fe524f0d54b1a01817a35c6` (branch `main`)
- Working tree at plan time: clean (`git status` empty)
- CI at base commit: `ci.yml` success; `build-apk` success ×2 (GitHub Actions, verified 2026-10-24)
- Baseline gate status (executed, not assumed): `data-engine status --gates` →
  `PAPER_READINESS: BLOCKED`, `LIVE_AUTHORIZATION: NOT_AUTHORIZED`,
  `DATA_READINESS: SYNTHETIC_ONLY/REAL_BLOCKED`, `MODEL_READINESS: 0_APPROVED`,
  32 gates (GOVERNANCE_READY = HUMAN_ACTION_REQUIRED).
- Baseline test suite: executed locally (uv, Python 3.12); result recorded in
  `04-TEST-EVIDENCE.md` (counts/exit code filled in after the run).

## 1. What exists today (verified by reading the code, not by prior audit artifacts)

| Area | File | Current reality |
|---|---|---|
| Fail-closed MT5 read surface | `src/data_engine/platform/mt5.py` | `MT5Adapter` consumes an injectable `MT5TerminalSession` (account_info, symbols, symbol_info, copy_rates_from_pos, positions, orders). Without an injected session it is UNAVAILABLE by construction. `submit_order`/`modify_order`/`cancel_order` ALWAYS raise `MT5OrderRefusedError`. No genuine terminal wiring exists yet: no `initialize/shutdown`, no `terminal_info`, no DEMO-positive verification (any coerced account mode connects), no ticks, no freshness, no provenance, no reconnect. |
| Genuine feed pattern (proven) | `src/data_engine/providers/binance_public.py` | The ONLY genuine market-data adapter in the repo. Pattern: subclass `MarketDataProvider`, register in `ProviderFactory` (`binance-public-spot`), injectable transport boundary, structured error hierarchy, closed-candle enforcement, UTC-aware timestamps, raw-response provenance. |
| MT5 broker mocks | `src/data_engine/brokers/adapters/mt5_mock.py`, `exness_mock.py` | Deterministic EXECUTION-venue mocks (paper simulator semantics). Explicitly NOT market data; explicitly NOT a MetaTrader5 connection. |
| Feed-source governance | `src/data_engine/platform/feed_source_candidates.py` + `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` | 4 candidates, ALL `UNVETTED`: `binance-public-spot`, `forex-15m-ohlc`, `stocks-15m`, `metals-15m`. Forex/metals/stocks are honest BLOCKED candidates (missing genuine 15-minute source). No MT5 candidate exists. |
| Provider registry | `src/data_engine/provider.py` | `ProviderFactory` with `file` + `binance-public-spot` registered. |
| Tests | `tests/test_platform_mt5.py` etc. | Adapter-contract tests with injected mock terminal (2,909 passed / 3 skipped at base). |
| CLI | `src/data_engine/cli.py` | `validate/report/status/serve/soak-preflight/recover-state/pair-status/check-boundary`. No MT5 operator probe. |

## 2. Scope of this change (and hard exclusions)

IN: read-only market data from a REAL MetaTrader 5 terminal (official
`MetaTrader5` Python package, Windows-only) against an **Exness DEMO** account:
terminal connect + health, positive DEMO verification (fail-closed), symbol
catalogue + per-symbol specifications observed from the terminal, ticks, OHLC
bars (latest + historical ranges), freshness validation, per-batch provenance,
structured errors, clean disconnect + safe reconnect, and an exact
canonical→broker symbol mapping that is only ever built from OBSERVED terminal
metadata (digest-stamped, re-verified at every connect).

OUT (never implemented here):
- ANY order path. No `order_send`, no order submission, modification or
  cancellation, no live-trading flag. Strategy output keeps flowing ONLY to the
  existing governed internal paper broker/simulator.
- No fabrication of candles from daily exchange rates; no mock relabelled as
  real data; no assumed broker symbol names or contract specs.
- No gate flips: `PAPER_READY` stays FALSE; `LIVE_AUTHORIZATION` stays
  NOT_AUTHORIZED; the 30-day soak and its preflight rules are untouched; no
  source is auto-approved (the new candidate enters `UNVETTED` like every other
  candidate).

## 3. File-level implementation plan

### New files

1. `src/data_engine/platform/mt5_terminal.py` — **terminal boundary** (the
   injectable equivalent of binance's transport):
   - `MT5TerminalConfig` (pydantic): `terminal_path`, `login`, `password`
     (`SecretStr`), `server`, `expected_server_substring`; `from_env()` reads
     `MT5_TERMINAL_PATH`, `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`;
     `repr`/log-safe (password never rendered); missing vars → structured
     `MT5CredentialsError` naming only the missing variable names.
   - `load_mt5_module()` — lazy `import MetaTrader5`; on failure returns None
     (caller fails closed with `MT5ModuleUnavailableError`).
   - `RealMT5Terminal` — thin adapter wrapping the REAL module (or an injected
     fake in tests) to the read surface the platform adapter consumes:
     `initialize/shutdown/version/last_error/terminal_info/account_info/
     symbols_total/symbols_get/symbol_info/symbol_info_tick/
     copy_rates_from_pos/copy_rates_range/copy_ticks_from/copy_ticks_range`
     + timeframe-constant resolution (`TIMEFRAME_*` via `getattr` on the module
     — ints are NEVER hardcoded here) + numpy-structured-array → plain-dict
     conversion (repo already depends on numpy) + UTC datetime coercion.
     Order functions of the wrapped module are NEVER referenced; tests enforce
     a read-allowlist of module functions.
2. `src/data_engine/platform/mt5_symbol_map.py` — **exact symbol mapping**:
   - `SymbolMapEntry` (canonical, broker_symbol) — operator-authored proposal;
   - `ValidatedSymbolEntry` — proposal + OBSERVED spec from the terminal
     (digits, point, trade_contract_size, description, path, currency_profit)
     + SHA-256 spec digest + verified_at;
   - `MT5SymbolMap.validate(proposals, terminal)` — every broker_symbol must be
     positively observed via `symbol_info`; duplicate canonical/broker
     collisions rejected; identity (canonical==broker) allowed ONLY through the
     same positive observation (no assumption);
   - JSON file load/dump (map lives OUTSIDE the repo or in operator artifacts);
   - digest re-check at feed connect: broker-side spec change → refusal until
     re-validated.
3. `src/data_engine/platform/mt5_market_data.py` — **the genuine feed**:
   - `ExnessMT5DemoFeed(MarketDataProvider)` registered in `ProviderFactory`
     as `exness-mt5-demo` (framework conformance: `fetch_candles/
     fetch_instrument_info/check_connectivity`);
   - `connect()`: initialize terminal → `terminal_info().connected` must be
     True → `account_info().trade_mode` must EQUAL the module's
     `ACCOUNT_TRADE_MODE_DEMO` constant (positive verification — REAL,
     CONTEST and UNKNOWN/None all refused) → optional
     `expected_server_substring` match → symbol map validated against the
     live terminal; full DEMO re-verification on every reconnect;
   - `health_check()` → `MT5HealthReport` (frozen model, credential-free);
   - `latest_bars(canonical, timeframe, count, closed_only=True,
     max_staleness_seconds=300, stale_policy="raise")` — forming bar excluded,
     staleness enforced or flagged;
   - `fetch_candles(...)` (framework) = historical range query — never
     freshness-checked (explicitly historical), empty range → `[]` honestly;
   - `latest_ticks(canonical, count, max_staleness_seconds=300)` via
     `copy_ticks_from`;
   - `MT5FeedProvenance` (frozen) attached to every batch: venue server,
     terminal name/build, company, environment="DEMO" (verified), symbol,
     timeframe, row count, first/last timestamps, staleness age,
     payload SHA-256, retrieved_at_utc;
   - structured error hierarchy with stable codes (`MT5_E_*`);
   - `disconnect()` idempotent; `ensure_connected()` bounded-backoff reconnect
     (injectable sleep; reconnect counter in health report);
   - explicit `submit_order/modify_order/cancel_order` refusal methods
     (same pattern as `platform/mt5.py`) — refusal is the ONLY order behavior
     in the entire surface.
4. `src/data_engine/platform/mt5_provenance.py` — kept INSIDE
   `mt5_market_data.py` (single module; no extra file).
5. Tests:
   - `tests/test_mt5_market_data_feed.py` — unit tests with a fake module:
     env config, module-unavailable fail-closed, DEMO-positive verification
     (happy + REAL/CONTEST/None refusal + server mismatch), health report,
     catalogue/specs, ticks (incl. empty → structured error), latest bars
     (forming-bar exclusion, freshness ok/stale, closed_only), history range,
     provenance completeness, credential redaction (repr/str/errors/
     provenance payload), disconnect idempotence, reconnect/restart with
     DEMO re-verification.
   - `tests/test_mt5_paper_only_negative.py` — order-path absence: refusal
     methods raise; spy fake module records every called function name and
     the full workflow stays inside the READ allowlist (`order_send` and
     every other order function NEVER called even when instrumented to
     raise); feed exposes no other order-named API; feed is not usable as an
     execution venue (allocation's non-MOCK venue refusal still applies);
     no live-flag attribute exists.
   - `tests/test_mt5_symbol_mapping.py` — mapping built only from observed
     metadata; unobserved broker symbol refused; digest mismatch refused
     after spec change; duplicate/collision rejection; file round-trip;
     NO hardcoded Exness suffix logic anywhere (asserted).
   - `tests/test_mt5_terminal_integration.py` — real-terminal integration
     checks, auto-SKIPPED with reason `BLOCKED_ON_OPERATOR_ENV` whenever the
     `MetaTrader5` package is not importable (non-Windows): connect, DEMO
     verify, catalogue, ticks, bars, disconnect. Never mocked-passed; either
     genuinely RUN on the operator's Windows host or honestly NOT RUN.
6. `artifacts/mt5-integration/01..08-*.md` — the eight deliverable notes
   (architecture/threat model, file-by-file summary, Windows host setup,
   test evidence, terminal evidence / BLOCKED status, source-approval +
   preflight, runbook + rollback, commit record).

### Edited files (additive, minimal)

1. `src/data_engine/platform/mt5.py` — add optional `require_demo: bool =
   False` to `MT5Adapter.__init__` (backward compatible: existing tests keep
   their semantics); when True, `connect()` refuses any coerced account mode
   that is not `AccountMode.DEMO` (state=ERROR + reason; UNKNOWN refused).
   Defense-in-depth behind the feed's own positive verification.
2. `src/data_engine/platform/__init__.py` — export the new public names.
3. `src/data_engine/platform/feed_source_candidates.py` — add candidate
   `exness-mt5-demo` (UNVETTED; honest license/coverage/limitation text;
   no credential words per existing record-hygiene test) to
   `CANDIDATE_SOURCES`. `BLOCKED_MARKETS` unchanged — forex/metals/stocks
   stay blocked until a human SRC-APPROVAL plus real verification exists.
4. `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` — append the
   `exness-mt5-demo` candidate section (what it is, what it is NOT,
   required evidence, SRC-APPROVAL template pointer).
5. `src/data_engine/cli.py` — add `mt5-probe` operator command:
   `--self-test`, `--dump-catalogue PATH`, `--validate-map PATH`,
   `--symbol S --timeframe TF --bars N [--out PATH]`; exit 0 = verified,
   6 = fail-closed verification failure, 7 = environment blocked
   (no MetaTrader5 module / non-Windows → honest NOT RUN). Reads
   credentials from environment only; never prints them.
6. `CHANGELOG.md` — additive entry.

### Governance invariants explicitly preserved (post-implementation verification)

- `data-engine status --gates` output identical to baseline
  (PAPER_READINESS: BLOCKED; LIVE_AUTHORIZATION: NOT_AUTHORIZED; 32 gates).
- `build_feed_source_registry()`: every record UNVETTED, zero approvals.
- Full pytest suite green (baseline 2909 passed / 3 skipped + new tests).
- No new dependency added (MetaTrader5 stays an OPTIONAL runtime import,
  never a pyproject dependency — it is Windows-only; absence is a structured
  error, not an install failure).

## 4. Risk register (pre-implementation)

| Risk | Mitigation |
|---|---|
| MT5 timestamps are broker-server-time epoch; naive UTC math could misstate freshness | Raw epoch + derived ISO both recorded; freshness threshold is operator-configurable; caveat documented in provenance note + runbook; weekend/market-closed staleness handled via `stale_policy="flag"` |
| Broker symbol drift (Exness suffixes differ per account) | Nothing assumed: mapping validated against observed `symbol_info` and digest-stamped; every connect re-validates |
| numpy structured arrays differ from fake shapes | Conversion layer handles both; repo already depends on numpy |
| Breaking existing 2,909 tests | Additive-only edits; `require_demo` default False; full suite re-run required |
| Credential leakage | SecretStr + redaction tests; candidate record hygiene test already forbids credential words; probe prints no credential values |
