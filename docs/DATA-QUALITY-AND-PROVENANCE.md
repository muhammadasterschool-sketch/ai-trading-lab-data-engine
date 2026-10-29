# DATA QUALITY AND PROVENANCE — v3.1

## Validation rules (Binance pipeline, enforced BEFORE storage)

| Check | Rule | On failure |
|---|---|---|
| OHLC sanity | `o,h,l,c > 0`; `h ≥ max(o,c)`; `l ≤ min(o,c)`; `h ≥ l`; `v ≥ 0` | row rejected (`invalid` counter) |
| Timestamps | openTime > 0; closeTime > openTime | row rejected |
| Duplicates | same openTime within one response | row rejected (`duplicates` counter) |
| Ordering | strictly non-decreasing openTime | row rejected (`nonMonotonic` counter) |
| Malformed | non-array element, missing fields, JSON parse errors | counted (`malformed`), never crash |
| Closed vs unfinished | `closed = closeTime < now` (explicit column) | unfinished rows stored with `closed=0` — never mixed silently |
| Gaps | interval deltas computed (`gapCount`), reported per sync | reported in logs + coverage `suspected_gaps` |
| Staleness | `binance_stale_min` (default 30) vs newest stored candle | coverage marks symbol STALE; data is never silently extended |
| Response emptiness | universe/klines parse to 0 valid rows | operation fails closed; registry untouched; error logged |
| Clock skew | `/api/v3/time` vs device clock | recorded in coverage (`server_skew_ms`); closed-marking uses device clock — documented limitation |

## Provenance columns (every candle row)

- `src` — the exact official host that served the observation
- `src_ts` — exchange openTime (source timestamp)
- `recv_ts` — device receipt time
- `closed` — explicit finished/unfinished marking

Yahoo feed (legacy strategy pipeline) keeps its own 4-day rolling store; its
~10-minute closed-bar lag is a documented, measured property (v3.0.1 audit), handled by
SAFE MODE rather than relabeled as real-time.

## Fail-closed behavior (summarized)

Rate-limited (429/418), banned, 5xx, timeout, empty/malformed response → the affected
operation aborts, nothing is written, backoff engages, coverage reflects the failure
(`last_error`, `last_http_status`, `in_backoff`). No retry storm (exponential, capped).
No synthetic candles are ever generated to fill gaps — gaps are reported, not invented.

## Test evidence

20 host-JVM tests (`BinanceMarketDataTest`) cover every row above with labelled
FIXTURES (including the real recorded 418 ban body). Live confirmation:
`audit/BINANCE-LIVE-SMOKE.md` (0 OHLC violations, monotonic, 0 gaps on real data).
