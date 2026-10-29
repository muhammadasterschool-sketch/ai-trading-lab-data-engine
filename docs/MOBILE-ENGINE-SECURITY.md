# MOBILE ENGINE SECURITY — v3.1 state

## Implemented and verified (host-side)

| Control | Where | Verification |
|---|---|---|
| Dashboard binds `127.0.0.1:8788` ONLY (was 0.0.0.0 wildcard) | `HttpServer.java` | `HttpServerLoopbackTest` 4/4 — bind asserted loopback, wildcard asserted ABSENT (fails against old impl) |
| CORS `Access-Control-Allow-Origin: *` removed | `HttpServer.java` | source + tests |
| 1 MB request cap + malformed/oversized Content-Length → 413 | `HttpServer.java` | 3 host tests (413 ×2, pass-through ×1) — was a 2 GB OOM engine-kill vector |
| Settings mutations ADMIN-only (wholesale gate incl. engine_on, risk, kill-switch, bridge trio) | `Api.saveSettings` | 403 + `SETTINGS_ADMIN_BLOCKED` audit; source-verified |
| Strategy approve/reject/delete ADMIN-only | `Api.strategyAction` | 403 + `STRATEGY_ADMIN_BLOCKED` audit; AI cannot self-approve |
| Binance watchlist ADMIN-only (new v3.1) | `Api.binanceWatchlistSet` | 403 + audit; same gate as settings |
| Session auth (PBKDF2 120k + TOTP + invitation codes) | `Auth.java`, `Db` | source-verified; on-device 2FA flow NOT RUN |
| `allowBackup=false` + dataExtractionRules + fullBackupContent | manifest + res/xml | lint 0 errors; adb-backup probe NOT RUN (needs device) |
| Binance host fails closed to official HTTPS | `BinanceMarketData.host()` | unit test: cleartext host setting is refused |
| No secrets in source | `git ls-files` + greps | keystore/keystore.properties/local.properties untracked + gitignored |
| Broker credentials | entered at runtime, SQLite `brokers` table, device-local | NOT used by the engine; plaintext storage documented as design limitation |

## Outstanding (honest)

1. **CRITICAL — owner action**: keystore + passwords were historically committed to the
   public repo (pre-v3.0.2). Forward-only hygiene done; real fix = NEW keystore (history
   rewrite forbidden by governance rules).
2. On-device verification of the checklist below is **NOT RUN** (no device/emulator):
   LAN isolation (`http://<phone-ip>:8788` from another device must FAIL), reboot
   recovery, process-kill recovery, battery-optimization behavior, FGS persistence.
3. WebView `onReceivedSslError → proceed()` retained (owner's self-signed cloud
   workflow) — documented MITM exposure in cloud mode; needs owner decision.
4. `usesCleartextTraffic=true` retained (loopback http://127.0.0.1 + legacy PC mode).
5. Android Keystore migration for any future device secrets: not yet needed (no secrets
   stored on device besides app-managed auth data) — revisit before any feature that
   stores credentials.

## New in v3.1 (Binance surface security review)

- Binance module is READ-ONLY by construction: only `GET` requests to
  `/api/v3/{time,exchangeInfo,klines}`; no auth headers; no request bodies; no other
  paths reachable (host + path are concatenated from fixed literals).
- Cleartext (`http://`) host settings are refused by code (`host()` fallback to the
  official default host) — tested.
- No API key is requested, stored, or transmitted. If a future Binance feature ever
  needs a key, it must go through Android Keystore + owner consent first.
- Binance responses are size-bounded by the 1 MB server request cap on the way in and
  by `limit` clamps (klines ≤ 1000, universe pages ≤ 100) on the way out.
