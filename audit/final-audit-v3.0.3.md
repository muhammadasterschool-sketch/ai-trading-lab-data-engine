# AI TRADING LAB — v3.0.3 CONTINUATION AUDIT (master engineering prompt, stages A–H)

Date: 2026-10-30 (UTC+8) · Mode: verification-first continuation — prior v3.0.2 evidence
was re-verified against the live repository BEFORE any new change. Nothing was repeated,
nothing was assumed.

## 0. BASELINE RE-VERIFICATION (Stage A) — all prior claims re-checked live

| Claim from v3.0.2 audit | Re-verified result |
|---|---|
| origin/main = f3b8bda2 (v3.0.1) | CONFIRMED via `git ls-remote` — unchanged, untouched |
| feature branch tip 9b55ee8d pushed | CONFIRMED — remote == local, 5 P0 commits intact |
| v3.0.2 candidate APK SHA 04b3317d… | CONFIRMED — checksum matches byte-for-byte |
| Toolchain in .tools/ | CONFIRMED — JDK 17.0.21+9, Gradle 8.9, SDK 34 + build-tools 34.0.0 |
| Local main extra commits 62ec4eb / d471d293 | INSPECTED — only `.next` dev-cache + db/custom.db auto-commits; NO Android source changes; preserved, not pushed |

## 1. ARCHITECTURE (unchanged from v3.0.2 audit — re-spot-checked)

Type A: engine executes ENTIRELY inside Android (`ConnectActivity` → `ServerService`
FGS specialUse + START_STICKY → `EngineCore` 10s loop + `HttpServer` 127.0.0.1:8788 +
SQLite WAL v7 + WebView dashboard same-origin; watchdog 9-min exact alarm; BootReceiver).
Zero runtime Python, zero external server. Yahoo public feed = the only market-data
provider in the runtime path (closed bars, unofficial). Optional Windows MT5 bridge:
OFF by default, owner-gated (now ADMIN-only end-to-end), NOT in the APK.

## 2. P1 SECURITY PATCH (this run) — diff scope (7 files + 2 new resources + 1 untrack)

| File | Change |
|---|---|
| `Api.java` | `saveSettings`: wholesale ADMIN gate (was bridge-only). `strategyAction`: ADMIN gate on approve/reject/delete/restore/trash/set_symbol; uid param threaded through call site. Version fallback 3.0.3. |
| `HttpServer.java` | `MAX_BODY_BYTES=1MB` cap + malformed Content-Length guard → bounded drain + 413 (was: 2GB Content-Length = 2GB char[] allocation = OOM engine death; non-numeric = silent drop). |
| `AndroidManifest.xml` | `allowBackup="false"` + `dataExtractionRules` + `fullBackupContent`. |
| `res/xml/data_extraction_rules.xml` (new) | cloud-backup + device-transfer: all domains excluded. |
| `res/xml/full_backup_content.xml` (new) | API 24–30 parity exclusions. |
| `EngineCore.java` / `dashboard.html` | version fallback/display 3.0.3 (single-source identity preserved). |
| `app/build.gradle` | versionCode 32 / versionName 3.0.3. |
| `android-app/local.properties` | UNTRACKED (machine-specific SDK path; was grandfathered as tracked). |

NOT changed (owner decisions, documented in RELEASE-v3.0.3-CANDIDATE.md):
WebView `onReceivedSslError → proceed()` (owner's self-signed private cloud workflow —
cancelling breaks owner cloud access; needs owner decision), `usesCleartextTraffic`
(required for loopback + legacy PC mode), keystore rotation (history rewrite forbidden),
plaintext broker records in SQLite (device-local, unused by engine).

## 3. TESTS EXECUTED (exact commands, this run)

| Run | Command | Result |
|---|---|---|
| Unit tests | `gradle test` (JAVA_HOME=.tools/jdk-17.0.21+9) | 7 tests × 2 variants = **14/14 PASS** (4 P0 loopback + 3 NEW: oversized-CL 413, malformed-CL 413, small-body pass-through) |
| Lint | `gradle lint` | **0 errors / 42 warnings** — all pre-existing; P1 patch adds ZERO new warnings (the DataExtractionRules warning was resolved by adding the rules files, not suppressed) |
| Debug build | `gradle assembleDebug` | BUILD SUCCESSFUL |
| Release build | `gradle assembleRelease` (lintVital included) | BUILD SUCCESSFUL |
| `git diff --check` | — | CLEAN |
| Yahoo live retest | `scripts/yahoo_retest_v303.py` (curl-equivalent + parse) | HTTP 200 · GC=F · 1109 bars · 36 null-bar gaps · 0 non-monotonic · 0 invalid OHLC (last 50) · last-bar age 10.10 min — reconfirms the ~10-min closed-bar lag profile; feed is NOT real-time and is treated as such by SAFE MODE |
| On-device install / LAN isolation / reboot / FGS / battery | — | **NOT RUN** (no device/emulator in sandbox) — owner checklist in release notes |
| Instrumentation tests (settings/strategy 403 paths) | — | **NOT RUN** (requires device; code path source-verified + audit-logged) |

## 4. RISK / VIRTUAL-EXECUTION / GOVERNANCE EVIDENCE (Stage D — source-traced)

- Entry pipeline (`EngineCore.openTrade3C`): fail-closed ORDER verified —
  `freshData()` (SAFE MODE: stale feed → NO entry) → `entryBlocked()` (cooldown +
  daily kill) → `tradingAllowed()` (v2.1 OWNER TRADING GATE) → CME halt → event
  gate → one-position-per-symbol → duplicate-setup dedup → Signal Council minimum.
- `dailyKillPct()`: opt-in (default 0 = OFF — owner's UNLIMITED requirement),
  clamped 0–90; enforcement logs `DAILY_KILL_SWITCH`; setting now owner-only.
- `testBroker`: ZERO network calls (verbatim: "this build runs paper trading only").
- `bridgeOrder/bridgeClose`: first line `if (!bridgeLive()) return;`; bridge_live
  settable ONLY by owner (v3.0.2) — now within the wholesale settings gate too.
- Engine follows only strategies with `status IN ('PAPER','ACTIVE')` (EngineCore:2232);
  `approve` → ACTIVE is now owner-only — AI strategies cannot be activated by a
  non-owner account, and the AI cannot self-approve (API-level gate + audit log).
- Idempotency: "one trade per setup per account, one open position per symbol" (code + dedup query).
- Audit ledger tags verified: ENGINE_START/STOP, SAFE_MODE_ON, DAILY_KILL_SWITCH,
  COOLDOWN, CONSEC_LOSS_PAUSE, STRATEGY_PAUSED/DEGRADED, ML_DRIFT, SETTINGS_ADMIN_BLOCKED (new), STRATEGY_ADMIN_BLOCKED (new).
- No live-order path enabled; no broker credentials used by the engine.

## 5. READINESS MATRIX (Stage F) — authoritative states

| Gate | Status | Evidence | Remaining blocker |
|---|---|---|---|
| Repository integrity | PASS | baseline + branch verified live; diff --check clean | — |
| P0 loopback binding | PASS (host) | 4 regression tests + bind assertions | on-device LAN-isolation NOT RUN |
| P1 settings/strategy governance | PASS (source) | code + audit-log calls; lint/test suite green | on-device 403-path check NOT RUN |
| Local API request hardening | PASS (host) | 3 new tests (413 ×2, pass-through ×1) | — |
| Backup hardening | PASS (source) | manifest + both rules files; lint 0 errors | adb-backup probe on device NOT RUN |
| Secret hygiene (forward-only) | PASS | keystore/keystore.properties untracked; no secrets in diff | ⚠ old keystore in git HISTORY — rotation needs owner |
| Android build | PASS | assembleDebug/Release BUILD SUCCESSFUL (v3.0.3, vc 32) | — |
| APK provenance | PASS | SHA-256 2dc42931…6184c4 · 229,752 B · badging verified | reproducible-builds equivalence claim NOT made |
| Device install + FGS + reboot recovery | NOT RUN | — | physical device required |
| Data provider verification | PARTIAL | live Yahoo retest PASS (provenance fields + SAFE MODE staleness gate in code) | provider is unofficial/closed-bar; latency ~10 min reconfirmed |
| Stale-data rejection | PASS (source) | freshData() → SAFE MODE blocks entries (v3.0.1 behavior preserved) | live stale-injection test NOT RUN |
| Risk controls preserved | PASS (source) | entry pipeline trace (§4); UNLIMITED default intact | instrumented race/concurrency tests NOT RUN |
| Kill switch | PASS (source) | daily_kill_pct enforcement + persistence (SQLite setting) + now owner-only | device-level kill test NOT RUN |
| Paper-only governance | PASS | paper fills only; testBroker no network; no broker path | — |
| PAPER_READY | **FALSE** (preserved) | — | requires owner-approved evidence chain incl. on-device checks |
| LIVE_AUTHORIZATION | **NOT_AUTHORIZED** (preserved) | bridge mirror OFF + owner-gated | — |
| 30-day paper-soak | **INTACT — NOT STARTED** | no timestamps touched; no soak code paths altered | readiness review + owner authorization required |
| CI | N/A | no GitHub Actions workflows exist in the branch (none claimed) | — |

## 6. VERDICT (per the master prompt's decision ladder)

**PARTIALLY COMPLETE — BLOCKERS REMAIN** (honest status; the P1 hardening is
implemented and host-verified, but on-device verification and the governance
evidence chain for PAPER_READY remain outstanding, and two security items are
deliberately left for owner decision).

- PAPER_READY = **FALSE** · LIVE_AUTHORIZATION = **NOT_AUTHORIZED**
- 30-day paper-soak: **preserved, NOT authorized, NOT started, NOT completed**
- Next action for owner: run the 10-minute on-device checklist in
  RELEASE-v3.0.3-CANDIDATE.md, then decide: (a) merge/publish policy for the
  v3.0.2+v3.0.3 candidates, (b) keystore rotation, (c) WebView self-signed-cloud
  policy (keep / real cert / pin), (d) schedule the paper-soak readiness review.
