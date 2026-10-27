# ANDROID MONITORING APK (Stage F, Part 9 F2/F3/F4; v4.0 dual-mode onboarding)

## What this app is

The Android admin panel client for the AI Trading Lab data engine.
**Monitoring + control only — the trading engine NEVER runs on the
phone.**

v4.0 onboarding offers exactly **TWO ways to connect** (owner decision
P1/P2 — **renting a server is OPTIONAL**):

1. **CLOUD SERVER** — your own dedicated VPS over https (the original
   multi-user deployment path; see
   `deploy/MULTI-USER-DEPLOYMENT-GUIDE.md`).
2. **LOCAL COMPUTER** — the engine on your own Windows PC. Install the
   Windows package, run `run-monitor.ps1`, and pair the phone with an
   **invitation code** over your Wi-Fi (or `127.0.0.1` on the same
   device/emulator). No server rental, no DNS, no certificates.

Both modes onboard through the engine's `POST /api/pair` endpoint
using an **owner-issued invitation code** (compulsory in both forms).
On success the engine returns the profile's monitoring **bearer token**,
which is stored ONLY in `flutter_secure_storage` — no manual token
copying. Manual token entry remains available as the "Advanced" path.

Security contract (enforced in `lib/main.dart` + `lib/pairing.dart`):
- **TLS only for CLOUD profiles** — `http://` URLs are refused before
  any request; a bare host is upgraded to `https://` (unchanged
  v0.3.0 posture).
- **LOCAL profiles may use `http://`** — ONLY via an explicit
  PER-PROFILE `isLocal` flag (never a global downgrade). The app shows
  a one-time honest warning: LAN traffic is UNENCRYPTED outside the
  host PC. Use only on a network you trust.
- **The invitation code is typed once, sent once to `/api/pair`, and
  never stored, logged, or embedded** in the APK. NO code value
  (including the local default) appears anywhere in `mobile/` — the
  engine ships only a salted SHA-256 hash of it.
- **Token in secure storage only** — `flutter_secure_storage`
  (Android Keystore-backed); never logged, never rendered. Delete
  `monitor-token.txt` on the PC (or rotate the server token) to
  invalidate a paired phone.
- **mDNS auto-discovery for local mode** — the APK resolves
  `_aitl-monitor._tcp.local.` (announced by `run-monitor.ps1
  -AllowLan`) and prefills the PC address; a manual address entry is
  the always-works fallback (some Android devices restrict multicast).
- **Multi-profile** — several server profiles (mixed cloud + local)
  can be stored, exactly ONE active at a time; the dashboard has a
  Switch action that NEVER deletes profiles, tokens, or state.
- **The only mutating action is the kill switch**, gated by an
  explicit confirmation dialog with a mandatory reason — and
  re-confirmed server-side (the engine requires
  `{"confirm": true, "reason": ...}` and audits the action).

## Onboarding walkthrough (what a user sees)

1. First run: **"How will you run?"** — CLOUD SERVER / LOCAL COMPUTER
   (+ "Advanced: paste token manually").
2. Cloud form: Name + Server URL (https) + Invitation Code → Pair.
3. Local form: Name + Gmail/email (identity only — no OAuth, no
   sign-in; redacted `***@domain` in engine audit logs) + Invitation
   Code + PC address (auto-detected via mDNS or typed manually) →
   one-time unencrypted-LAN warning → Pair.
4. Dashboard: health, positions, PnL, risk, feed, audit events,
   kill switch (confirmation required), and Switch-profile.
5. Wrong code: the engine's stable reason code is shown in-app
   (`E_PAIRING_CODE_INVALID` etc.); nothing is ever fabricated.

## Pairing trust statement (honest, owner-ratified)

Whoever holds the invitation code AND network access to the monitor
endpoint can obtain the monitoring bearer token. The code is the
onboarding secret; rotate it any time (cloud: re-run
`server-install.sh --invitation-code <new>`; local: see
`deploy/windows/LOCAL-MONITOR-RUNBOOK.md`).

## Build (reproducible, GitHub Actions)

`.github/workflows/build-apk.yml` builds the APK on every change
under `mobile/` and on manual dispatch:

- Java 17 (temurin) + Flutter stable 3.24.5, actions pinned to full
  commit SHAs.
- `flutter create .` regenerates the Android platform scaffolding
  around the committed `lib/` + `pubspec.yaml` (generated files are
  deliberately NOT committed); a post-create step additively patches
  the release manifest with `INTERNET` +
  `CHANGE_WIFI_MULTICAST_STATE` (mDNS; graceful without it).
- `flutter analyze` + `flutter test` (widget tests in
  `mobile/test/pairing_test.dart`) run before the release build.
- `flutter build apk --release` → `app-release.apk` (debug-keystore
  signing — see below), renamed `ai-trading-lab-monitor.apk`, with
  SHA256SUMS, uploaded as a workflow artifact AND attached to a
  GitHub Release via the repository's built-in GITHUB_TOKEN (no user
  secrets involved anywhere).

Local build (needs Flutter SDK):
```
cd mobile
flutter create . --platforms android --org com.aitradinglab \
  --project-name ai_trading_lab_monitor
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

## Release signing (documented for LATER — not in this run)

The current build is **debug-keystore signed**: installable for
private distribution, not for public stores. To move to release
signing:

1. Generate a keystore in a SECURE EXTERNAL process (never on a CI
   runner, never in the repo):
   `keytool -genkey -v -keystore aitl-release.keystore -alias aitl \
   -keyalg RSA -keysize 4096 -validity 10000`
2. Store `AITL_KEYSTORE_BASE64`, `AITL_KEYSTORE_PASSWORD`,
   `AITL_KEY_ALIAS`, `AITL_KEY_PASSWORD` as GitHub repository
   SECRETS (Settings → Secrets → Actions).
3. Add a workflow step decoding the keystore and point
   `mobile/android/key.properties` at it (standard Flutter signing
   setup).
4. Keep the keystore backed up — losing it means a new app identity
   for future updates.

## iOS — NOT built in this run (F4/P10: documented path)

iOS requires the Apple Developer Program ($99/year) and macOS
runners. The follow-up path (owner decision, out of scope here):

1. Enroll in the Apple Developer Program.
2. `flutter create . --platforms ios` on a macOS host; open
   `ios/Runner.xcworkspace` in Xcode; set the team + bundle id.
3. Run flutter unit/widget tests as on Android.
4. **TestFlight distribution (recommended first step):**
   `flutter build ipa --export-method ad-hoc` → upload via Xcode
   Organizer or `xcrun altool`/Transporter to App Store Connect →
   add internal testers in TestFlight → external review for public
   TestFlight (beta app review applies).
5. App Store distribution later requires full App Review; the app's
   monitoring-only role must be stated clearly in review notes
   (no trading execution on-device).
6. Same security contract applies: cloud TLS-only, token in Keychain
   (flutter_secure_storage handles this), no embedded endpoints, no
   embedded invitation codes.

## Verification status (honest)

| Item | Status |
| --- | --- |
| Dart source committed (two-mode onboarding, dashboard, alerts, kill-switch, profiles) | YES — this repo, `mobile/` |
| Static analysis (`flutter analyze`) | runs in CI at build time |
| Widget tests (`mobile/test/pairing_test.dart`) | run in CI (`flutter test`); NOT RUN locally (no Flutter toolchain in the dev workspace) |
| APK build executed | via GitHub Actions on push (see run + Release) |
| Debug-keystore signing | YES (release signing documented for later) |
| iOS build | NOT BUILT (path documented above) |
| Invitation-code plaintext anywhere in `mobile/` | NONE — repo-wide probe scan is test-enforced (owner-side `AITL_INVITE_PROBE` runs; CI structural subset) |
