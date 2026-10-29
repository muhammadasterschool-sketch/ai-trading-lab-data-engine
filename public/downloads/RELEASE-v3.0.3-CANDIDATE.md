# AI Trading Lab v3.0.3 — CANDIDATE BUILD (NOT PUBLISHED — awaiting owner approval)

**Status**: CANDIDATE. v3.0.1 remains the published APK; the v3.0.2 candidate
remains intact and unmodified. This v3.0.3 candidate EXTENDS the v3.0.2 P0 work
with P1 governance hardening. It is merged/published only after owner review.

## What this build is

Mobile-only, paper-only research build. The full engine (data feed → 3C strategy →
risk gates → paper fills → SQLite ledger → dashboard) runs inside the Android app.
No PC, no Python backend, no cloud dependency in the normal operating path.

## Security hardening (P1) — on top of the v3.0.2 P0 loopback fix

1. **ALL settings mutations are now OWNER(ADMIN)-only** (`Api.saveSettings`).
   Until v3.0.2, ANY authenticated TRADER could change `engine_on` (start/stop the
   engine), `risk_pct` (position size), every `threec_*` strategy filter,
   `cooldown_min` / `consec_loss` guards, **`daily_kill_pct` — the daily
   kill-switch threshold**, slippage/heat caps, safe-mode bars and the MT5 bridge
   trio. Non-admin attempts now get 403 + audit entry (`SETTINGS_ADMIN_BLOCKED`).
   The read-only GET view is unchanged so every operator can still SEE state.
2. **Strategy governance actions are OWNER(ADMIN)-only**
   (`Api.strategyAction`): `approve` (the human-approval gate that flips an
   AI/YouTube strategy to ACTIVE as its own signal source), `reject`, `delete`,
   `restore`, `trash`, `set_symbol`. Research actions (add / yt_add / backtest /
   paper) stay open — paper-only, cannot move risk gates. Non-admin attempts:
   403 + audit entry (`STRATEGY_ADMIN_BLOCKED`).
3. **Backup hardening**: `android:allowBackup="false"` +
   `android:dataExtractionRules` + `android:fullBackupContent` — the engine DB
   (PBKDF2 password hashes, TOTP seeds, session tokens, owner-optional broker
   records) can no longer leave the device via Auto Backup, adb backup, or
   device-to-device transfer.
4. **Request-size cap** (`HttpServer.MAX_BODY_BYTES = 1 MB`): a malformed or
   oversized `Content-Length` previously caused either a giant buffer allocation
   (OOM → engine process death) or an unanswered drop. Now: bounded drain +
   HTTP 413. Regression-tested.
5. **Build hygiene**: machine-specific `android-app/local.properties` untracked
   (`.gitignore` already listed it — the file was grandfathered as tracked).

## Known issues NOT changed (owner decisions — documented, not hidden)

- **WebView `onReceivedSslError → proceed()`** (cloud mode): deliberate owner
  workflow — the private cloud server uses a self-signed certificate. Cancelling
  would break owner's cloud access; proper fix is a real cert or cert pinning.
  Requires an owner decision. (Lint flags it: `WebViewClientOnReceivedSslError`.)
- **`usesCleartextTraffic="true"`**: still required for the loopback dashboard
  (`http://127.0.0.1:8788`) and the legacy PC mode (`http://<pc-ip>:81`).
- **Old keystore + passwords remain in git history / v3.0.1 source zip** (public).
  Forward-only hygiene was applied in v3.0.2; rotation is an owner decision.
- **Broker records stored plaintext in SQLite** (device-local, unused by the
  engine); `testBroker` performs NO network calls (verified — paper-only message).
- Optional MT5 bridge (`mt5-bridge.py`) stays OFF by default, owner-gated, and
  still binds 0.0.0.0:8899 on the Windows PC with no auth when used — Windows-side
  risk, out of APK scope.

## Governance invariants — UNTOUCHED

- 3C MASTER rules verbatim (C1/C2 body ≥70%, C3 protected close, 5-candle window,
  SL = extreme ± buffer, BE @ +1R, TP @ +3R, 1 position per symbol).
- Daily P/L UNLIMITED by default; kill/heat/bucket/event/session all opt-in, default OFF.
- Paper-only fills; no broker connectivity in the APK; `LIVE_AUTHORIZATION = NOT_AUTHORIZED`.
- `PAPER_READY = FALSE`; 30-day paper-soak requirement intact — not started, not shortened.
- Entry pipeline fail-closed order verified in source: freshness (SAFE MODE) →
  entry guards (cooldown/daily-kill) → owner trading gate → CME halt → event gate →
  one-position-per-symbol → duplicate-setup dedup → Signal Council minimum.

## Build provenance

| Field | Value |
|---|---|
| Source | branch `feat/v3.0.2-p0-loopback-security` (extends the v3.0.2 candidate) |
| versionCode / versionName | 32 / 3.0.3 |
| Package | com.aitradinglab.monitor (minSdk 24, targetSdk 34) |
| Toolchain | Temurin JDK 17.0.21+9 · Gradle 8.9 · AGP 8.5.2 · SDK 34 / build-tools 34.0.0 |
| Signed with | existing CN=AI Trading Lab identity — installs over v3.0.1 (⚠ identity is the historically exposed one; rotation pending owner decision) |
| SHA-256 | `2dc42931c7ad347c33e21d7f222164d8a980de619a833849cb3bef40136184c4` |
| Size | 229,752 bytes |
| Checks | `gradle test` 7 tests × 2 variants = 14/14 PASS · `gradle lint` 0 errors / 42 warnings (all pre-existing) · `assembleDebug` + `assembleRelease` (lintVital included) BUILD SUCCESSFUL |
| Marker scan | `127.0.0.1` ×2 and `3.0.3` ×1 present in classes.dex (supplementary) |

## Install / verify / rollback

1. Install over v3.0.1 or v3.0.2 (same signing identity, higher versionCode).
2. Verify dashboard loads on `http://127.0.0.1:8788` and shows **v3.0.3**.
3. From a PC on the same Wi-Fi: `http://<phone-ip>:8788` must FAIL to connect (loopback-only).
4. Sign in as a TRADER (non-owner) account and try to save a setting or approve a
   strategy → must get 403 "…sirf owner (ADMIN)…" and the attempt appears in the audit log.
5. Rollback: uninstall → install the previous APK (v3.0.1 published / v3.0.2
   candidate). NOTE: allowBackup is now false — app data does NOT migrate via
   Android backup; use the owner's manual backup procedure if needed.
