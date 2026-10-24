# 02 — File-by-File Implementation Summary

Base `4cc6782` → plan `169b655` → implementation `79f3f49`
(branch `feat/exness-mt5-demo-market-data`).

## New files

| File | Purpose | Key contracts |
|---|---|---|
| `src/data_engine/platform/mt5_terminal.py` | Terminal boundary (injectable, read-only) | `MT5_READ_METHODS` closed allowlist; `MT5TerminalConfig.from_env()` (SecretStr, missing-var-only errors); `RealMT5Terminal` with `_call` choke point refusing non-read names; `initialize/shutdown` lifecycle; `rates_to_dicts/ticks_to_dicts/coerce_rows` handling numpy structured arrays, namedtuples, mappings; `timeframe_constant/tick_flag_constant/account_trade_mode_constant` resolved from the installed module (never hardcoded ints) |
| `src/data_engine/platform/mt5_symbol_map.py` | Exact symbol mapping | `SymbolMapEntry` (proposal) → `ValidatedSymbolEntry` (observed digits/point/contract size/path/description + `spec_sha256` + verified_at); `MT5SymbolMap.validate()` refuses unobserved symbols, duplicates, ambiguity, incomplete observations; `recheck()` refuses spec drift / removal; JSON load/dump (operator artifacts) |
| `src/data_engine/platform/mt5_market_data.py` | The genuine feed | `ExnessMT5DemoFeed(MarketDataProvider)` registered `exness-mt5-demo`; `connect()` = initialize → terminal connected → POSITIVE DEMO verification (module's own constant) → server match → map resolve/recheck; `latest_bars` (forming-bar exclusion, staleness raise/flag, OHLC validation); `fetch_candles` (aware-dt range, fully-closed bars only, `[]` when empty); `latest_ticks`; `symbol_catalogue` / `symbol_specification`; `health_check` (credential-free `MT5HealthReport`); `ensure_connected` (bounded backoff, injectable sleep, full re-verification); `disconnect` (idempotent); `MT5FeedProvenance` per batch (server/build/company/DEMO/counts/epochs/staleness/payload SHA-256/retrieved_at); `MT5_E_*` error hierarchy; refusal trio |
| `tests/fake_mt5_lab.py` | Test helper | `FakeMT5Module` mirroring the real package's payload shapes (namedtuples + dict rows, real constant values for DEMO=0/CONTEST=1/REAL=2 semantics); order functions RECORD + raise; rate/tick/catalogue builders with a forming bar |
| `tests/test_mt5_market_data_feed.py` | Unit tests (51) | config/credential hygiene, module-unavailable fail-closed, DEMO verification matrix, health, catalogue/spec, bars (forming exclusion, staleness, corruption), framework conformance, ticks, reconnect/restart, `require_demo` hardening |
| `tests/test_mt5_paper_only_negative.py` | Negative suite (15) | refusal trio; full-workflow spy (zero order attempts, calls ⊆ `MT5_READ_METHODS`); choke-point refusal; AST scan (no order calls in the 3 modules; no hardcoded `EURUSDm`-style suffixes); REAL venue descriptor refused at registration; candidate UNVETTED; BLOCKED_MARKETS unchanged |
| `tests/test_mt5_symbol_mapping.py` | Mapping suite (19) | validation matrix, identity-mapping refusal, digest sensitivity/determinism, drift + removal recheck, JSON round-trip, garbage refusal |
| `tests/test_mt5_terminal_integration.py` | Genuine-terminal checks (5) | auto-SKIP `BLOCKED_ON_OPERATOR_ENV` without the Windows package; never mock-passed; run on the operator host with env credentials |

## Edited files (additive, minimal)

| File | Change |
|---|---|
| `src/data_engine/platform/mt5.py` | `MT5Adapter(terminal, require_demo=False)` — when True, `connect()` refuses non-DEMO/unverifiable modes (state=ERROR + reason). Default preserves all historical behaviour. New `MT5DemoRequiredError` documenting the guard. |
| `src/data_engine/platform/__init__.py` | exports for the new feed/map/terminal names |
| `src/data_engine/platform/feed_source_candidates.py` | candidate `exness-mt5-demo` (UNVETTED; credential-word-free text per record-hygiene test); `CANDIDATE_SOURCES` gains the name; `BLOCKED_MARKETS` untouched |
| `src/data_engine/cli.py` | `mt5-probe` command: `--self-test`, `--dump-catalogue PATH`, `--validate-map PATH`, `--symbol S --timeframe TF --bars N [--out PATH] [--stale-flag]`; exits 0 verified / 2 config / 6 fail-closed refusal / 7 environment NOT RUN; credentials env-only, never printed |
| `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` | §8 candidate section: what it is / is NOT, required evidence, unchanged blocked markets |
| `CHANGELOG.md` | Stage MT5 entry |

## Explicitly NOT changed

Runtime composition, the 32-gate chain, soak preflight, MAC custody,
submission ledger, paper broker/simulator, allocation/venue registry,
monitoring API, APK, Windows packaging. No new dependency (MetaTrader5
stays an optional Windows runtime import).
