# INSTRUMENT CATALOG REPORT (GENERATED ARTIFACT)

> GENERATED, DETERMINISTIC artifact — rendered by `data_engine.brokers.catalog_report.build_catalog_report` from the discovered venue catalogs (fail-closed discovery) and the synced platform `InstrumentRegistry` (see `scripts/generate_broker_catalog_artifacts.py`; tests byte-compare regeneration). Discovery timestamp (audit provenance ONLY — never an identity input, INV-01): `2026-10-13T12:00:00+00:00`. NO real broker connectivity exists or is claimed; every venue is a MOCK_DETERMINISTIC in-memory adapter. **LIVE TRADING IS NOT AUTHORIZED.**

Venues cataloged: **7** · canonical platform identities: **5** · eligibility granted by this report: **NONE** (registration is DISTINCT from eligibility).

## 1. Venue catalogs (served instruments)

### `binance-mock` — Binance spot — REST/filter semantics (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 2 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSDT` | `BTCUSDT` | BTC | USDT | 0.01 | 0.00001 | 0.00001 | 1000 | 10 | 50000.00 |
| `ETHUSDT` | `ETHUSDT` | ETH | USDT | 0.01 | 0.0001 | 0.0001 | 5000 | 10 | 3000.00 |

### `bitget-mock` — Bitget spot v2 — clientOrderId semantics (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 2 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSDT` | `BTCUSDT` | BTC | USDT | 0.01 | 0.00001 | 0.00001 | 1000 | 5 | 50000.00 |
| `ETHUSDT` | `ETHUSDT` | ETH | USDT | 0.01 | 0.0001 | 0.0001 | 5000 | 5 | 3000.00 |

### `bybit-mock` — Bybit v5 spot/linear — order/link semantics (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 2 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSDT` | `BTCUSDT` | BTC | USDT | 0.1 | 0.001 | 0.001 | 1000 | 5 | 50000.0 |
| `ETHUSDT` | `ETHUSDT` | ETH | USDT | 0.01 | 0.01 | 0.01 | 5000 | 1 | 3000.00 |

### `exness-mock` — Exness — MT5 terminal class (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 3 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSD` | `BTCUSD` | BTC | USD | 0.01 | 0.01 | 0.01 | 10 | 0 | 50000.00 |
| `EURUSD` | `EURUSD` | EUR | USD | 0.00001 | 0.01 | 0.01 | 100 | 0 | 1.10000 |
| `XAUUSD` | `XAUUSD` | XAU | USD | 0.01 | 0.01 | 0.01 | 50 | 0 | 2350.00 |

### `mt5-mock` — MT5-compatible broker — Exness/XM-class semantics (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 3 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSD` | `BTCUSD` | BTC | USD | 0.01 | 0.01 | 0.01 | 10 | 0 | 50000.00 |
| `EURUSD` | `EURUSD` | EUR | USD | 0.00001 | 0.01 | 0.01 | 100 | 0 | 1.10000 |
| `XAUUSD` | `XAUUSD` | XAU | USD | 0.01 | 0.01 | 0.01 | 50 | 0 | 2350.00 |

### `paper-mock` — Paper simulation venue (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 2 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSDT` | `BTCUSDT` | BTC | USDT | 0.01 | 0.0001 | 0.0001 | 100 | 0 | 50000.00 |
| `EURUSD` | `EURUSD` | EUR | USD | 0.00001 | 0.01 | 0.01 | 100 | 0 | 1.10000 |

### `xm-mock` — XM — MT5 terminal class (deterministic mock)

Execution mode: MOCK_DETERMINISTIC · instruments: 3 · discovered at `2026-10-13T12:00:00+00:00`

| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | Min qty | Max qty | Min notional | Reference price |
|---|---|---|---|---|---|---|---|---|---|
| `BTCUSD` | `BTCUSD` | BTC | USD | 0.01 | 0.01 | 0.01 | 10 | 0 | 50000.00 |
| `EURUSD` | `EURUSD` | EUR | USD | 0.00001 | 0.01 | 0.01 | 100 | 0 | 1.10000 |
| `XAUUSD` | `XAUUSD` | XAU | USD | 0.01 | 0.01 | 0.01 | 50 | 0 | 2350.00 |

## 2. Platform-registry canonical state (after sync)

The SAME canonical identity discovered at multiple venues is ONE record with MANY venue mappings (duplicate-merge; identity is never forked). All broker mappings start UNVERIFIED.

| Canonical symbol | Asset class | Contract | Currency | Internal ID | First discovered from | Venue mappings | Data state | Monitoring | Paper trading | Live trading |
|---|---|---|---|---|---|---|---|---|---|---|
| `BTC/USD` | cryptocurrency | spot | USD | `959a6f889b0d0798` | `broker:exness-mock` | `broker:exness-mock`→`BTCUSD` (UNVERIFIED); `broker:mt5-mock`→`BTCUSD` (UNVERIFIED); `broker:xm-mock`→`BTCUSD` (UNVERIFIED) | none | Registered | Discovered | Not Authorized |
| `BTC/USDT` | cryptocurrency | spot | USDT | `8f54e7c6d120ba75` | `broker:binance-mock` | `broker:binance-mock`→`BTCUSDT` (UNVERIFIED); `broker:bitget-mock`→`BTCUSDT` (UNVERIFIED); `broker:bybit-mock`→`BTCUSDT` (UNVERIFIED); `broker:paper-mock`→`BTCUSDT` (UNVERIFIED) | none | Registered | Discovered | Not Authorized |
| `ETH/USDT` | cryptocurrency | spot | USDT | `481286e28927c775` | `broker:binance-mock` | `broker:binance-mock`→`ETHUSDT` (UNVERIFIED); `broker:bitget-mock`→`ETHUSDT` (UNVERIFIED); `broker:bybit-mock`→`ETHUSDT` (UNVERIFIED) | none | Registered | Discovered | Not Authorized |
| `EUR/USD` | cryptocurrency | spot | USD | `a7307a41fac04678` | `broker:exness-mock` | `broker:exness-mock`→`EURUSD` (UNVERIFIED); `broker:mt5-mock`→`EURUSD` (UNVERIFIED); `broker:paper-mock`→`EURUSD` (UNVERIFIED); `broker:xm-mock`→`EURUSD` (UNVERIFIED) | none | Registered | Discovered | Not Authorized |
| `XAU/USD` | cryptocurrency | spot | USD | `409a16eaae31afdb` | `broker:exness-mock` | `broker:exness-mock`→`XAUUSD` (UNVERIFIED); `broker:mt5-mock`→`XAUUSD` (UNVERIFIED); `broker:xm-mock`→`XAUUSD` (UNVERIFIED) | none | Registered | Discovered | Not Authorized |

## 3. Fail-closed discovery behaviors (tested, referenced)

- Discovery from a DISCONNECTED adapter is REFUSED (a fabricated catalog is worse than none). — `tests/test_broker_instrument_discovery.py`
- Foreign specs (broker_id mismatch) are REFUSED — a venue's catalog only contains its OWN instruments. — same suite
- Duplicate venue symbols are REFUSED — the venue surface must be consistent. — same suite
- Capability DRIFT (adapter serves a descriptor differing from the registered one) is REFUSED — capability changes are explicit versioned events. — same suite
- Unregistered venues are REFUSED at discovery (fail closed — refusing to assume capabilities). — same suite
- Precision/lot-step/minimum violations are DEFINITIVE rejections carrying venue-native codes (e.g. MT5 retcode 10014) BEFORE any execution. — `tests/test_broker_adapter_contract.py`
- Unknown symbols fail closed on lookup (INVALID_ORDER-category error, never a guessed spec). — same suite

## 4. Known limitations (documented honestly)

- Canonical platform identity is currently modeled uniformly as CRYPTO/SPOT by the broker-catalog sync (brokers/instruments.py _canonical_instrument) — FX and metals canonical records (EUR/USD, XAU/USD, BTC/USD from the MT5-class venues) inherit that simplification. Canonical identity and venue mappings are correct; the asset-class label is a documented modeling simplification, not a connectivity claim.
- All venue mappings are UNVERIFIED by construction — provider verification is the platform registry's explicit evidence-driven action, never granted by discovery or by this report.

PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE TRADING NOT AUTHORIZED.
