# BROKER CAPABILITY MATRIX (GENERATED ARTIFACT)

> GENERATED, DETERMINISTIC artifact — rendered by `data_engine.brokers.catalog_report.build_capability_matrix` over the governed `CapabilityRegistry` (see `scripts/generate_broker_catalog_artifacts.py`; tests byte-compare regeneration). NO real broker connectivity exists or is claimed: every venue below is a MOCK_DETERMINISTIC in-memory adapter; REAL execution-mode descriptors are refused at registration and by the session. **LIVE TRADING IS NOT AUTHORIZED.**

Registered venues: **7**

| Broker ID | Display name | Execution mode | Order kinds | TIF | SL/TP | Position mode | Idempotency key | Reduce-only | Account modes | Rate limit (orders/requests per window s) | Reconciliation | Market data |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `binance-mock` | Binance spot — REST/filter semantics (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT | GTC, IOC, FOK | SEPARATE_ORDERS | BALANCES_ONLY | NATIVE_CLIENT_ID | no | DEMO | 0/10 per 60s | BALANCE_SNAPSHOT | no |
| `bitget-mock` | Bitget spot v2 — clientOrderId semantics (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT | GTC, IOC | SEPARATE_ORDERS | BALANCES_ONLY | NATIVE_CLIENT_ID | no | DEMO | 5/20 per 60s | BALANCE_SNAPSHOT | no |
| `bybit-mock` | Bybit v5 spot/linear — order/link semantics (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT | GTC, IOC, FOK | ATTACHED | NETTING | NATIVE_CLIENT_ID | yes | DEMO | 5/0 per 60s | POSITION_STATEMENT | no |
| `exness-mock` | Exness — MT5 terminal class (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | no | DEMO | 5/0 per 60s | ORDER_FILL_POLL | no |
| `mt5-mock` | MT5-compatible broker — Exness/XM-class semantics (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | no | DEMO | 5/0 per 60s | ORDER_FILL_POLL | no |
| `paper-mock` | Paper simulation venue (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC, FOK, DAY | ATTACHED | NETTING | INTERNAL_JOURNAL | yes | DEMO | 0/0 per 60s | ORDER_FILL_POLL | no |
| `xm-mock` | XM — MT5 terminal class (deterministic mock) | MOCK_DETERMINISTIC | MARKET, LIMIT, STOP, STOP_LIMIT | GTC, IOC | ATTACHED | HEDGING | COMMENT_FIELD | no | DEMO | 5/0 per 60s | ORDER_FILL_POLL | no |

## Venue notes (per-venue audit narrative)

### `binance-mock` — Binance spot — REST/filter semantics (deterministic mock)

No plain STOP kind on spot; no attached SL/TP — stops are SEPARATE order submissions (STOP_LOSS_LIMIT / TAKE_PROFIT_LIMIT / OCO). newClientOrderId is the idempotency key. Filters: tickSize, stepSize, MIN_NOTIONAL. Representative error codes: -1013 filter failure, -2010 insufficient balance, HTTP 429/418 throttling.

### `bitget-mock` — Bitget spot v2 — clientOrderId semantics (deterministic mock)

clientOrderId is the idempotency key. Spot filters: price/quantity precision + minTradeUSDT minimum notional. No attached SL/TP on spot — stops are separate trigger (plan) order submissions. Representative v2 codes (re-verified against the live docs when the real adapter phase is authorized): 40001 param error, 43007 filter/amount violation, 42911 frequency limit.

### `bybit-mock` — Bybit v5 spot/linear — order/link semantics (deterministic mock)

orderLinkId is the idempotency key. Filters: lotSizeFilter (minOrderQty/qtyStep) + minOrderAmt. Attached SL/TP supported on order placement (v5). One-way position mode default. Representative retCodes: 10004 rate-limited, 10010 order not exists, 10014 insufficient available balance.

### `exness-mock` — Exness — MT5 terminal class (deterministic mock)

Exness is an MT5 brokerage (Standard/Pro/Raw Spread/Zero account classes trading FX, metals and crypto CFDs). Terminal semantics are the MT5 class: hedging position tickets, attached SL/TP, volume_min/step lots, order-comment idempotency, MT5 TRADE_RETCODEs. Symbol suffixes and server names are ACCOUNT-TYPE facts verified per-account by the operator BEFORE any real adapter activation — UNVERIFIED brokers are not connectable by design. This mock encodes Standard-account plain symbols (EURUSD, XAUUSD, BTCUSD); NO network, NO credentials, NO real orders. LIVE TRADING IS NOT AUTHORIZED.

### `mt5-mock` — MT5-compatible broker — Exness/XM-class semantics (deterministic mock)

Encodes COMMON MT5 terminal semantics: hedging position tickets, attached SL/TP, volume_min/step lots, order-comment idempotency (MT5 has no native client-order-id). Exness/XM account support is verified per-account by the operator (symbol suffixes, server names, account modes) BEFORE any real adapter activation — UNVERIFIED brokers are not connectable by design.

### `paper-mock` — Paper simulation venue (deterministic mock)

Reference adapter proving the full neutral surface. Play-money only; the operational paper pipeline remains the frozen runtime simulator (integration is Phase M2, separately reviewed).

### `xm-mock` — XM — MT5 terminal class (deterministic mock)

XM is an MT5/MT4 brokerage (Micro/Standard/ULTRA LOW account classes trading FX, metals and crypto CFDs). Terminal semantics are the MT5 class: hedging position tickets, attached SL/TP, volume_min/step lots, order-comment idempotency, MT5 TRADE_RETCODEs. XM account types carry symbol-suffix conventions (e.g. micro accounts quote EURUSDmicro) — suffixes and server names are ACCOUNT-TYPE facts verified per-account by the operator BEFORE any real adapter activation; UNVERIFIED brokers are not connectable by design. This mock encodes Standard-account plain symbols (EURUSD, XAUUSD, BTCUSD); NO network, NO credentials, NO real orders. LIVE TRADING IS NOT AUTHORIZED.

## Unsupported order kinds per venue (session refuses BEFORE the venue)

Unsupported requests fail closed at the session boundary — the venue never sees them (`session.py` pre-venue capability checks; covered by `tests/test_broker_session_guards.py`).

| Broker ID | Unsupported order kinds |
|---|---|
| `binance-mock` | STOP, STOP_LIMIT |
| `bitget-mock` | STOP, STOP_LIMIT |
| `bybit-mock` | STOP, STOP_LIMIT |
| `exness-mock` | (none — all kinds) |
| `mt5-mock` | (none — all kinds) |
| `paper-mock` | (none — all kinds) |
| `xm-mock` | (none — all kinds) |

PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE TRADING NOT AUTHORIZED.
