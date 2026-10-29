# BASELINE AUDIT — Multi-Broker Ecosystem Engineering Run (v3.1 line)

Date: 2026-10-30 (UTC+8) · Mode: verification-first · Written BEFORE any code change on this branch.
Every claim below was re-verified live in this session; nothing was inherited on trust.

## 1. Source-of-truth verification (live checks this run)

| Item | Verified value | Method |
|---|---|---|
| Repository | `github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine` | `git ls-remote origin` |
| Remote `main` | `f3b8bda2b43ab4b7379badbaafcca465b84af344` (v3.0.1, versionCode 30) | `git ls-remote` |
| Remote `feat/v3.0.2-p0-loopback-security` | `98309977eb0746c10f49910ed92f0e82ebbd1a3f` | `git ls-remote` |
| Local branch tip | `98309977eb07` — **identical to remote** (pushed, clean worktree) | `git rev-parse` + `git status` |
| Historical claim "v3.0.3 candidate @ 98309977" | **CONFIRMED** — commit exists on that branch: "v3.0.3 CANDIDATE artifacts + evidence: APK 229752b SHA-256 2dc42931…, PAPER_READY=FALSE" | `git log` |
| Historical claim "baseline f3b8bda" | CONFIRMED — direct ancestor, remote main still at it, never merged over | `git log`/`ls-remote` |
| Commit chain on v3.0.2 branch | `4d04ce5` (P0 loopback) → `ae1cf61` (secret hygiene) → `3f73697` (lint API-26) → `df464f7` (v3.0.2 bump) → `9b55ee8` (v3.0.2 candidate) → `c239eafc` (P1 owner-only settings/strategy + 1MB request cap + backup rules, v3.0.3 bump vc32) → `9830997` (v3.0.3 candidate artifacts) | `git log` |
| Backup branch `backup-v12-local` | exists locally, untouched | `git branch` |
| Local `main` extra commits `62ec4eb`/`d471d293`/`c1dcd539` | auto-commits of `.next` cache + runtime DB + deploy artifacts only; `android-app/` identical to f3b8bda. PRESERVED, never pushed by this workflow | `git diff f3b8bda..62ec4eb -- android-app` (empty) |
| `git diff --check` on new branch | CLEAN | run this session |

## 2. Baseline test evidence (this run)

| Run | Command | Result |
|---|---|---|
| Unit tests (debug variant) | `./gradlew test` (JDK 17.0.21+9, Gradle 8.9 wrapper re-downloaded, SDK 34 in `.tools/`) | **7/7 PASS** (`TEST-com.aitradinglab.engine.HttpServerLoopbackTest.xml`: tests=7 failures=0 errors=0 skipped=0) — matches v3.0.3 claim of 7×2 variants=14 |
| Build sanity | `./gradlew test` → `BUILD SUCCESSFUL` | PASS |
| Live Yahoo feed probe (prior run, re-confirmed in v3.0.3 audit) | curl GC=F 5m/5d | HTTP 200, ~1109 bars, last-bar age ≈10.1 min (closed-bars profile) |
| **Live Binance probe (this run, first attempt)** | `GET https://api.binance.com/api/v3/exchangeInfo` | **HTTP 418 — IP weight-banned by Binance until 2026-10-29 19:35:54 UTC** (sandbox shared-IP, prior tenants exhausted weight). Same on `data-api.binance.vision`. **Environment restriction, recorded honestly. Live smoke test re-attempt scheduled after expiry; failure-injection fixtures built from this REAL 418 response.** |

## 3. Existing implementation inventory (verified by source inspection this run)

**Architecture (Type A — engine runs entirely inside the Android app; verified prior audits, re-spot-checked):**
`ConnectActivity` → `ServerService` (FGS `specialUse`, START_STICKY, wakelock, 30s thread watchdog) → `EngineCore` (10s loop) + `HttpServer` (**127.0.0.1:8788 only** since `4d04ce5`) + `Api` (session auth, PBKDF2+TOTP, admin gates) + SQLite WAL **v7** (14 tables) + `MainActivity` WebView (same-origin dashboard). `WatchdogReceiver` (9-min exact alarm) + `BootReceiver` (reboot recovery). Zero runtime Python. Zero external runtime dependencies (pure platform).

| Capability present at baseline | Location (verified) |
|---|---|
| Market-data feed (27 halal CME commodities) | `EngineCore.java` `MT5_FEED` map (lines 435–463), Yahoo chart 5m/5d, closed-bars (~10 min lag), `feed_interval_sec` throttle, exp backoff |
| Optional MT5 bridge (Windows PC, OFF by default, ADMIN-gated) | `fetchFromBridge`, `bridgeOrder/bridgeClose` first-line `if (!bridgeLive()) return;`; `public/downloads/mt5-bridge.py` v2.0 (NOT in APK) |
| Symbol registry | SQLite `instruments` (symbol PK, base, quote, exchange, status, priority, discovered_at, last_data_at); `seedStaticInstruments()`; `discover()` every 30 min |
| Candles store | SQLite `candles(symbol, tf, ts PK-composite)`, 4-day rolling purge, `INSERT OR REPLACE` upsert |
| Risk controls | entry pipeline fail-closed: `freshData()` SAFE MODE → `entryBlocked()` (cooldown + daily kill) → owner `tradingAllowed()` → CME halt → event gate → one-position-per-symbol → dedup → council; heat/bucket caps; slippage model; TRUE-HWM drawdown; persistent guards |
| Virtual (paper) execution | paper fills only; `orders` table; `trades` journal (r_mult/mfe/mae/tca_bps/council/win_prob); `testBroker` = zero network calls; bridge live-mirror default OFF |
| Strategy governance | `strategies` table, owner-only approve/reject (ADMIN gate since `c239eafc`), AI cannot self-approve (API 403 + `STRATEGY_ADMIN_BLOCKED` audit) |
| Dashboard/API security | loopback bind, ACAO wildcard removed, 1MB body cap + 413, session auth, PBKDF2 120k, TOTP, invites, `allowBackup=false` + dataExtractionRules |
| Tests at baseline | `HttpServerLoopbackTest.java` — 7 host-JVM tests (4 loopback + 3 request-cap), 14/14 across variants |
| CI workflows | **none** (`.github/workflows` absent — no CI claims made) |

**MT5 adapter files from the engineering prompt (`mt5_terminal.py`, `mt5_symbol_map.py`, `mt5_market_data.py`, `platform/mt5.py`):**
NOT present in this branch's Android architecture. They exist only on the historical branch
`origin/feat/exness-mt5-demo-market-data` (older Python lineage, incl. `adapters/exness_mock.py`,
`adapters/mt5_mock.py` — mock-labelled). The current MT5 surface is the optional Windows
bridge (`mt5-bridge.py`) + Yahoo commodity feed. Recorded here to prevent false claims.

## 4. Secret-hygiene state (carried from v3.0.2/v3.0.3, re-checked)

- `android-app/ai-trading-lab.keystore`, `keystore.properties`, `local.properties`: **untracked + gitignored** (verified: `git ls-files` exit 1; `.gitignore` contains all three). Files still exist locally for signing.
- ⚠ KEPT OPEN (owner decision, cannot be fixed forward-only): the keystore + passwords were historically committed (public). Rotation requires owner action; history rewrite is forbidden by governance rules.
- No broker credentials/API keys in Android source; broker records entered at runtime sit in SQLite (device-local, unused by engine).

## 5. Toolchain (re-provisioned, verified)

JDK 17.0.21+9 (`​.tools/jdk-17.0.21+9`), Gradle 8.9 (`.tools/gradle-8.9` + committed wrapper), Android SDK platform 34 / build-tools 34.0.0 (`.tools/android-sdk`), signing via local `keystore.properties` (CN=AI Trading Lab).

## 6. Decision record for THIS run

- Feature branch `feat/v3.1-multi-broker-market-data` created from **`98309977`** (the verified v3.0.3 candidate tip) — NOT from `main`, so the P0/P1 security fixes are the starting point.
- `main` remains at `f3b8bda2`; nothing merges without owner authorization.
- Governance carried forward unchanged: `PAPER_READY = FALSE`, `LIVE_AUTHORIZATION = NOT_AUTHORIZED`, 30-day soak NOT STARTED, bridge mirror OFF, UNLIMITED daily P/L default, 3C MASTER rules untouched.
- No history rewrite, no force-push, no backup-branch modification.

## 7. Implementation plan for this branch (file-level, acceptance criteria)

| # | Change | Files | Acceptance criteria |
|---|---|---|---|
| 1 | Binance market-data module (pure-Java core, host-testable) | NEW `engine/BinanceMarketData.java` | exchangeInfo → validated symbol registry; klines → closed/open-marked candles; OHLC/monotonic/dup/stale checks; weight-budget + 429/418 backoff; no Android imports in core |
| 2 | DB v7→v8 | `engine/Db.java` | idempotent CREATE for `binance_symbols`, `binance_candles` (provenance cols), `binance_state`; old data untouched |
| 3 | Engine integration | `engine/EngineCore.java` | tiered scheduler (discovery 12h / watchlist 60s / backfill rotation batch), truthful coverage stats in `status()`; **Binance must NOT alter the 3C strategy universe** (no silent substitution) |
| 4 | API surface | `engine/Api.java` | `/api/binance/coverage`, `/api/binance/universe` (paginated search), `/api/binance/candles`, `/api/binance/watchlist` (ADMIN-gated POST), `/api/brokers/registry` |
| 5 | Broker-neutral layer | NEW `engine/BrokerAdapter.java`, `engine/BrokerRegistry.java` | capability declarations, unknown capabilities default disabled, honest status labels, zero order paths added |
| 6 | Dashboard | `assets/dashboard.html` | Markets section: source health (READ_ONLY/STALE/BLOCKED…), universe search, coverage counters, watchlist editor; no fake "LIVE/READY" labels |
| 7 | Tests + fixtures | NEW `app/src/test/.../BinanceMarketDataTest.java`, `app/src/test/resources/binance/*.json` | fixtures labelled FIXTURE; cover TRADING/permission filtering, malformed instruments, dup/non-monotonic/OHLC-violation/stale klines, 418/429 backoff (real recorded ban body), rotation fairness, provenance round-trip |
| 8 | Docs | `docs/*.md` (13 files per master prompt, adapted; no duplicate-of-existing docs) | honest, evidence-referencing |
| 9 | Release candidate | `app/build.gradle` (v3.1.0 / versionCode 33), `RELEASE-v3.1.0-CANDIDATE.md`, checksums | signed APK + SHA-256 + badging verification; v3.0.x artifacts preserved |
| 10 | Final readiness report | `audit/FINAL-READINESS-REPORT.md` | gate matrix; PAPER_READY/LIVE_AUTHORIZATION/soak states re-affirmed from code evidence |
