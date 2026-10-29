# RELEASE — AI Trading Lab v3.1.0 CANDIDATE (versionCode 33)

**STATUS: CANDIDATE — NOT PUBLISHED. The live download page still serves v3.0.1.
Publishing requires owner approval. Prior artifacts (v3.0.1 live, v3.0.2/v3.0.3
candidates) are preserved untouched.**

## Identity

| Field | Value |
|---|---|
| Package | `com.aitradinglab.monitor` |
| versionCode / versionName | 33 / 3.1.0 |
| Branch / commit | `feat/v3.1-multi-broker-market-data` (from verified `9830997` = v3.0.3 candidate) |
| minSdk / targetSdk | 24 / 34 |
| Signing | existing identity `CN=AI Trading Lab, O=Muhammad, L=Lahore, C=PK` (installs over v3.0.1/v3.0.3) — the OLD keystore remains publicly exposed in git history; rotation is an open owner decision |
| SHA-256 | `0d86b18f36c863503b7340255cee755d1bac432d27ac21290af0d11f23a3b025` |
| Size | 250,492 bytes |
| Build | `./gradlew test assembleDebug assembleRelease` — BUILD SUCCESSFUL (lint 0 errors, 42 pre-existing warnings) |
| Marker scan | 210 Binance/BTCUSDT dex markers · 3 × "v3.1.0" in dashboard asset |

## What's new (paper-only; no order paths added)

1. **Binance SPOT market data (read-only, official public endpoints)** — dynamic
   universe discovery (3702 parsed → 517 eligible USDT + 3185 rejected with reasons on
   the live smoke run), validated 5m klines with closed/unfinished marking and full
   provenance, rate-limit aware (weight budget, Retry-After/ban backoff, fail-closed),
   tiered scheduler (discovery 12h / watchlist 60s cap 200 / rotating backfill),
   7-day retention. LIVE SMOKE: PASS (see `audit/BINANCE-LIVE-SMOKE.md`).
2. **Broker-neutral registry** — Yahoo / Binance / MT5-bridge adapters with declared
   capabilities (unknown = disabled), honest status labels, per-source approval state.
3. **Dashboard "🌐 Markets"** — source health (READ_ONLY / RATE_LIMIT_BACKOFF /
   LAST_ERROR; order path: NONE), paginated universe search with rejection reasons,
   admin pipeline settings, registry table.
4. **DB v8** — three new tables (`binance_symbols`, `binance_candles`, `binance_state`);
   idempotent migration; existing data untouched.
5. Docs set under `docs/` + `audit/BASELINE-AUDIT.md` + readiness gates matrix.

**Governance: 3C MASTER rules UNTOUCHED · UNLIMITED daily P/L default preserved ·
Binance data never feeds the strategy (separate tables, no substitution) ·
PAPER_READY = FALSE · LIVE_AUTHORIZATION = NOT_AUTHORIZED · 30-day soak NOT STARTED.**

## Owner on-device verification checklist (~10 min, NOT RUN — required before merge/publish)

1. Install candidate over v3.0.1 → sign in → dashboard loads (127.0.0.1:8788).
2. Insights → 🌐 Markets: Binance card shows READ_ONLY + counters within ~2 min
   (first discovery runs at engine start).
3. From a PC on the same Wi-Fi: `http://<phone-ip>:8788` must FAIL to connect.
4. Airplane mode off/on → feed recovers; backoff banner if Binance was rate-limited.
5. Reboot → engine returns via BootReceiver.
6. Non-owner account: try saving Markets settings → 403 + audit event.

## Rollback

`docs/ROLLBACK.md` — reinstall previous APK; DB v8 adds tables only; branch deletable;
`main` untouched throughout.
