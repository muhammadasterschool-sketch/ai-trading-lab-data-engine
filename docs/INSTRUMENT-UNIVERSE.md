# INSTRUMENT UNIVERSE — integrity rules (v3.1)

## Universes in the app (kept separate by design)

| Universe | Source | Storage | Purpose |
|---|---|---|---|
| Halal commodities (27) | static `HALAL_COMMODITIES` + Yahoo/bridge feed | `instruments` + `candles` | 3C MASTER strategy feed (owner-fixed since v2.1; no auto-register) |
| Binance SPOT | DYNAMIC `exchangeInfo` discovery | `binance_symbols` + `binance_candles` | research universe (v3.1); does NOT feed strategies |
| MT5 symbols | terminal metadata via optional PC bridge | not persisted on device | optional mirror only |

The master prompt's "do not hardcode a static list as the definitive coin universe" is
satisfied by the Binance registry (fully dynamic). The 27-symbol halal list remains
static **by explicit owner request** (v2.1: "sare halal commodities add karo, baki
delete kardo") — that is a deliberate owner decision, documented here, not an oversight.

## Binance eligibility rules (explicitly configured)

1. `status == TRADING` (BREAK/HALT/SETTLING → rejected, reason stored)
2. `isSpotTradingAllowed == true`
3. symbol matches `^[A-Z0-9]{5,20}$`
4. quote asset in `binance_quotes` (default `USDT`, `*` = all)

## Lifecycle integrity

- **Discovery cadence:** every `binance_discovery_hours` (default 12h) + once at engine
  start. `/api/v3/time` skew check runs first.
- **Delisting / suspension:** two-run sweep — symbols not re-verified by the current
  successful discovery (compared against the previous watermark) are marked
  `rejected=1, reject_reason=ABSENT_OR_STATUS_CHANGE_<ts>`. A symbol that disappears or
  changes status cannot silently remain eligible. A single failed request can NOT
  trigger a mass-rejection (watermark only advances on success).
- **Metadata changes:** tick/step/min filters are updated on every verified discovery;
  SHA-256 digest of the meaningful fields is recomputed and stored.
- **first_seen preserved** across updates (upsert does not overwrite it).

## Coverage truthfulness

`/api/binance/coverage` (and the dashboard Markets card) report: eligible, rejected,
watchlist size, fresh/stale/no-data within the sampled set, suspected gaps, last
discovery/sync timestamps, used weight, backoff state, clock skew. It NEVER claims
full-coin coverage when only a subset was fetched; the sampled set is labeled as such.
