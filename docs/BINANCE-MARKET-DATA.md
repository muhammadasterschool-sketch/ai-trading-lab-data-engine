# BINANCE MARKET DATA — v3.1 (first genuine non-Yahoo provider)

Status: **IMPLEMENTED + HOST-VERIFIED + LIVE SMOKE PASS (2026-10-29, read-only)**.
This phase does NOT authorize execution of anything. Evidence: `audit/BINANCE-LIVE-SMOKE.md`.

## Endpoints used (official, public, no API key)

| Endpoint | Weight | Use |
|---|---|---|
| `GET /api/v3/time` | 1 | clock-skew check before discovery |
| `GET /api/v3/exchangeInfo?permissions=SPOT` | 20 | dynamic instrument universe |
| `GET /api/v3/klines?symbol=&interval=5m&limit=` | 2 | OHLCV candles |

Host: default `https://data-api.binance.vision` (Binance's official market-data-only
domain, same REST contract) — configurable to `https://api.binance.com` via
`binance_host`. Cleartext hosts are refused (fail closed). Category: **SPOT only**.

## Module map (all in `engine/BinanceMarketData.java`, pure Java, no android imports)

- `parseExchangeInfo` — eligibility rules: `status=TRADING` + `isSpotTradingAllowed`
  + symbol format `[A-Z0-9]{5,20}` + quote whitelist (`binance_quotes`, default
  `USDT`; `*` = all). Rejected instruments are STORED with reasons
  (`STATUS_BREAK`, `NOT_SPOT_TRADABLE`, `QUOTE_FILTER_USDC`, `BAD_SYMBOL_FORMAT`)
  — nothing silently dropped. Metadata kept: tickSize, stepSize, minQty, minNotional,
  first_seen, last_verified, SHA-256 metadata digest. Native symbol preserved verbatim.
- `parseKlines` — OHLC sanity (positive prices, `h≥max(o,c)`, `l≤min(o,c)`, `v≥0`),
  duplicate + out-of-order rejection, malformed-row counting, and **explicit
  closed/unfinished marking** (`closed = closeTime < nowMs`).
- `call()` — fail-closed HTTP: tracks `X-MBX-USED-WEIGHT-1M`, enforces a local weight
  budget (`binance_weight_budget`, default 1800 of the exchange's 6000/min), honors
  `Retry-After` and parses real 418 bodies (`"IP banned until <epoch-ms>"`), backs off
  exponentially (60s → 15 min cap) on 429/418/5xx/network errors. While in backoff,
  ALL tiers stop and no request leaves the device.
- Operations: `discoverUniverse` (delisting/suspension sweep with a two-run watermark —
  one failed request can never mass-reject the registry), `syncWatchlist` (hard cap 200
  symbols/tick), `backfillBatch` (rotating window over eligible symbols, default 4,
  cursor persisted in `binance_state`), `coverage` (truthful counters).
- Retention: `binance_candles` purged beyond `binance_candle_days` (default 7).

## Storage (DB v8 — deliberately separate from strategy tables)

```
binance_symbols(symbol PK, base, quote, status, tick_size, step_size, min_qty,
                min_notional, spot_allowed, rejected, reject_reason,
                first_seen, last_verified, digest)
binance_candles(symbol, tf, ts, o, h, l, c, v, closed, src_ts, recv_ts, src,
                PRIMARY KEY(symbol, tf, ts))
binance_state(key PK, value)   -- rot_cursor, prev_discovery_at, last_discovery_at …
```

**Governance invariant:** Binance rows never enter `instruments`/`candles`/`MT5_FEED`;
the 3C MASTER strategy keeps its existing feed. No silent substitution.

## Live smoke evidence (production code path, 2026-10-29 19:36 UTC)

| Step | Result |
|---|---|
| `/api/v3/time` | HTTP 200, server skew −40 ms |
| `/api/v3/exchangeInfo?permissions=SPOT` | HTTP 200 — 3702 symbols parsed → **517 eligible** (USDT whitelist) + **3185 rejected with recorded reasons** |
| klines BTCUSDT + ETHUSDT (5m × 50) | HTTP 200 — 100 stored, closed=98, unfinished=2 (explicitly marked), **0 OHLC violations, monotonic, 0 gaps** |
| Weight header | tracked: 1424 (budget 1800) |

Environment note: the sandbox IP was weight-banned (HTTP 418) earlier the same day —
that REAL response body is committed as a fixture and drives the backoff tests.

## Known limits (stated plainly)

- SPOT category only; other Binance categories need separate implementation + review.
- Data collection frequency is tiered; the full 517-symbol universe is NOT monitored at
  high frequency (watchlist 60s + rotation batch 30s → full sweep ≈ hours). Coverage
  counters state exactly what was fetched — never "all coins at 5m".
- Public endpoints; Binance can rate-limit or ban IPs (handled: fail closed + backoff).
- Unfinished candles exist and are marked; nothing treats them as final.
