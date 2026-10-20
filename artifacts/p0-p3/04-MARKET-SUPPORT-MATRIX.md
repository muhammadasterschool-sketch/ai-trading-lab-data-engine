# P0-P3 MARKET ADAPTER / RUNTIME SUPPORT MATRIX (Task 13)

**Principle:** support is claimed ONLY where a proven adapter +
tests + docs exist. Generic schema enums (`AssetClass`,
`ContractType`) are DATA VOCABULARY, not support claims. A cash
index, ETF, CFD and futures contract are NEVER silently equated
(per-class canonical rules in `brokers/instrument_registry.py`
enforce this at registration time).

## 1. Operational market-data adapters (the honest inventory)

| Market / venue | Feed adapter | Status | Native symbols proven | Evidence |
|---|---|---|---|---|
| Crypto spot — Binance public REST (`https://api.binance.com/api/v3`) | `providers/binance_public.py` (`BinancePublicKlinesProvider`) | **PILOT — implemented + contract-tested (mocked transport); live connectivity NOT exercised in this task** | `BTCUSDT` (narrow pilot allowlist default; operators extend only after mapping + quality validation) | `test_provider_binance_public.py`; FIX-10 launcher `_construct_known_provider` refuses every other name |
| Everything else (forex, equities, ETFs, indices, metals, futures feeds) | **NONE** | **UNSUPPORTED — no adapter exists** | — | the launcher's known-provider inventory; no schema-enum inference anywhere |

Execution is **paper-only for every row**: the session-launch wiring
(FIX-10) feeds `TradingRuntime.process_bar` from a bar source and all
orders route to the `MOCK_DETERMINISTIC` paper venue (L1-L4 proofs;
FIX-10 routing test).

## 2. Per-instrument runtime coverage (as implemented)

| Instrument identity | Asset class / product | Feed adapter | Paper venue | Config/approval required | Sessions / freshness | Risk controls / order types | Fee / spread / contract semantics | Tests | Known limitations |
|---|---|---|---|---|---|---|---|---|---|
| `TEST/USD` (canonical fixture) | synthetic spot pair | replay file (deterministic) | runtime paper venue | launch plan + signed approvals | replay timestamps; watchdog configurable | full runtime risk stack (§26 chain: exposure, drawdown, kill switch, spacing 1s, 5/60s, 10 open) | documented in `PAPER-SIMULATION-ASSUMPTIONS.md` (tick/lot/multiplier validated per InstrumentSpec) | `test_session_launch.py` (24), `test_composition_root.py` (29), recovery/oms suites | fixture world — not a real market |
| `BTCUSDT` Binance spot | crypto / SPOT | Binance public klines (pilot) | runtime paper venue | source approval in prediction registry + operator launch plan | 24/7 crypto; per-feed staleness budget configurable (default 900s gate) | same runtime risk stack | tick/lot from `InstrumentSpec` (per-class rules); spread/slippage per §D2 assumptions | `test_provider_binance_public.py` (adapter contract), `test_feed_gate.py`/`test_feed_composition.py` (gate) | live-path connectivity not run this task; narrow allowlist by design |
| Mock broker venues (Binance/Bybit/Bitget/Exness/XM/MT5 mocks) | mixed (mock adapters) | n/a (paper/mock only) | mock paper venues | n/a (test/deployment fixtures) | n/a | capability-gated per adapter contract | per-mock documented | `test_broker_*` suites | MOCK ONLY — never live; execution adapters refuse REAL mode structurally |

## 3. Explicitly unsupported (no silent fallback)

- **Forex (e.g. EURUSD):** no feed adapter; any launch plan naming a
  forex provider is refused (`not a proven adapter`). Forex
  instrument SPECS exist in the registry vocabulary with per-class
  rules, but no market-data path exists — claiming forex support
  would be false.
- **Equities / ETFs / indices / metals / futures:** same — schema
  enums exist; adapters do not. Futures expiry/roll semantics are
  implemented only in the derivatives research modules
  (`derivatives/`), NOT in any operational feed path.
- **CFDs:** not represented anywhere as a supported product; no
  conflation with futures/ETFs is possible through the canonical
  identity rules.
- **Volume semantics:** exchange volume vs provider tick volume vs
  unavailable are kept distinct in the provider/bar contracts
  (`supports_volume` flags; validation marks unavailable rather than
  fabricating).

## 4. Canonical instrument identity (enforced at registration)

`brokers/instrument_registry.py` requires, per instrument:
`broker_id`, canonical `symbol`, venue-native `broker_symbol`,
base/quote assets, `tick_size`, `lot_step`, min/max quantity,
min_notional — with PER-CLASS rules (e.g. FOREX pip-scale tick,
EQUITY cent-scale tick, CRYPTO fraction rules) and drift refusal
(registration that changes an existing identity is rejected).
Ambiguous aliases are refused rather than silently mapped
(`test_g3_instrument_registry.py`, 19 tests).
