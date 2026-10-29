# AI Trading Lab v3.0.2 — CANDIDATE BUILD (NOT PUBLISHED — awaiting owner approval)

**Status**: CANDIDATE. v3.0.1 remains the published APK. This artifact is merged only after owner review.

## What this build is

Mobile-only, paper-only research build. The full engine (data feed → 3C strategy →
risk gates → paper fills → SQLite ledger → dashboard) runs inside the Android app.
No PC, no Python backend, no cloud dependency in the normal operating path.

## Security fixes

1. **P0 — Loopback-only dashboard server.** `HttpServer` previously bound the
   wildcard address (`new ServerSocket(PORT)`), exposing the dashboard + JSON API
   to every device on the phone's network. Now explicitly bound to `127.0.0.1:8788`
   (IPv4-only socket, no separate IPv6 listener), with SO_REUSEADDR + bounded
   retry (5×300ms) so watchdog/START_STICKY quick restarts cannot fail on
   lingering TIME_WAIT sockets.
2. **CORS wildcard removed.** `Access-Control-Allow-Origin: *` was removed — the
   dashboard is same-origin; the wildcard let any website in the phone's browser
   pass CORS preflight against the local API.
3. **Live-mirror settings owner-only.** `mt5Bridge` / `bridgeLive` / `bridgeLots`
   (the ONLY real-order surface in the app: `bridgeOrder`/`bridgeClose` POST to
   the optional Windows MT5 bridge when `bridge_live=1`) can now be changed ONLY
   by the ADMIN/owner account. Non-admin attempts get 403 + audit-ledger entry
   (`SETTINGS_ADMIN_BLOCKED`). Default state unchanged: bridge mirror OFF.
4. **API 26 guards** for `startForegroundService` in BootReceiver + ConnectActivity
   (crash on Android 7.x devices fixed; full `gradle lint` now 0 errors).
5. **Secret hygiene (forward-only):** keystore untracked from git, signing
   passwords removed from Gradle (read from local untracked
   `android-app/keystore.properties`), password strings redacted from 3 tracked
   public docs. ⚠️ The old keystore + passwords remain in git HISTORY and in the
   v3.0.1 source zip (public). Rotation requires an owner decision — history
   rewrite was forbidden for this task.

## Governance invariants — UNTOUCHED

- 3C MASTER rules verbatim (C1/C2 body ≥70%, C3 protected close, 5-candle window,
  SL = extreme ± buffer, BE @ +1R, TP @ +3R, 1 position per symbol).
- Daily P/L UNLIMITED by default; kill/heat/bucket/event/session all opt-in, default OFF.
- Owner gates preserved: registration `approved` + per-user `trade_ok` + invite codes.
- Paper-only fills; no broker connectivity in the app; live trading remains UNAUTHORIZED.
- `PAPER_READY = FALSE` — unchanged. 30-day paper-soak requirement intact, not started.

## Version identity

| Field | Value |
|---|---|
| versionName | 3.0.2 |
| versionCode | 31 |
| applicationId | com.aitradinglab.monitor |
| minSdk / targetSdk / compileSdk | 24 / 34 / 34 |
| Branch | feat/v3.0.2-p0-loopback-security (from main f3b8bda) |

## Build environment

| Tool | Version |
|---|---|
| JDK | Temurin 17.0.21+9 |
| Gradle (wrapper, now committed) | 8.9 |
| Android Gradle Plugin | 8.5.2 |
| Android SDK | platform 34, build-tools 34.0.0 |
| Build command | `./gradlew test assembleRelease` (lint included, NOT skipped) |

## Verification performed (host JVM + build chain)

- `gradle test` — 4/4 P0 regression tests pass (debug + release variants):
  loopback bind asserted, wildcard bind asserted ABSENT, request→accept→close
  pipeline, stop() releases listener.
- `gradle lint` — 0 errors (42 pre-existing warnings, none introduced by this patch).
- `gradle assembleRelease` with `lintVitalRelease` executed (not skipped) — pass.
- `gradle assembleDebug` — pass.
- Live Yahoo feed retest during audit: last closed bar age 10.10 min during open
  market → confirms closed-bar feed behavior and the v3.0.1 `safe_mode_bars=3` fix.

## NOT verified in this sandbox (owner should verify on a real phone)

- On-device runtime behavior (install, foreground service, dashboard over
  loopback, LAN isolation check from another device, reboot recovery, battery
  optimization). Marked **NOT RUN** — no emulator/device in the build sandbox.
- Long-duration endurance (no claim of 24/7 operation is made — Android OEM
  battery managers can and do kill background processes).

## Install / rollback

- Install: sideload APK over v3.0.1 (same signing identity — no uninstall needed).
- Rollback: reinstall the v3.0.1 APK from the downloads page (same identity).
- Owner rotation follow-up: generate a NEW keystore before the next published
  release; after rotation, updates require uninstall/reinstall.

## Known limitations (documented, not fixed here)

- Android loopback is device-global: other on-device apps could still connect to
  127.0.0.1:8788. Session-token auth remains the second gate; every
  state-changing endpoint requires a valid session.
- `allowBackup="true"` and WebView `onReceivedSslError → proceed()` (cloud mode
  convenience) are pre-existing design choices, reported for owner review.
- Error responses include exception class+message (operator-debug UX); bounded,
  no stack frames; loopback + auth limit exposure.
