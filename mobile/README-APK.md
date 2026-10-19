# ANDROID MONITORING APK (Stage F, Part 9 F2/F3/F4)

## What this app is

The Android monitoring client for the AI Trading Lab data engine.
**Monitoring + control only — the trading engine NEVER runs on the
phone.** Each user points the app at their OWN dedicated server
(server URL + personal token at login; nothing is embedded in the
APK).

Security contract (enforced in `lib/main.dart`):
- **TLS only** — `http://` URLs are refused before any request.
- **Token in secure storage only** — `flutter_secure_storage`
  (Android Keystore-backed); never logged, never rendered.
- **No default server address, no shared account** — the APK is
  built once and works with ANY user's server.
- **Multi-profile** — several server profiles stored, exactly ONE
  active at a time.
- **The only mutating action is the kill switch**, gated by an
  explicit confirmation dialog with a mandatory reason — and
  re-confirmed server-side (the engine requires
  `{"confirm": true, "reason": ...}` and audits the action).

## Build (reproducible, GitHub Actions)

`.github/workflows/build-apk.yml` builds the APK on every change
under `mobile/` and on manual dispatch:

- Java 17 (temurin) + Flutter stable 3.24.5, actions pinned to full
  commit SHAs.
- `flutter create .` regenerates the Android platform scaffolding
  around the committed `lib/` + `pubspec.yaml` (generated files are
  deliberately NOT committed).
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

## iOS — NOT built in this run (F4: documented path)

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
6. Same security contract applies: TLS-only, token in Keychain
   (flutter_secure_storage handles this), no embedded endpoints.

## Verification status (honest)

| Item | Status |
| --- | --- |
| Dart source committed (login/dashboard/alerts/kill-switch/profiles) | YES — this repo, `mobile/` |
| Static analysis (`flutter analyze`) | runs in CI at build time |
| APK build executed | via GitHub Actions on push (see run + Release) |
| Debug-keystore signing | YES (release signing documented for later) |
| iOS build | NOT BUILT (path documented above) |
