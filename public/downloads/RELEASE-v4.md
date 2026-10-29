# AI Trading Lab — Data Engine · RELEASE v4.0

**Private build — not published to any app store.** Install directly from the files below.

---

## 1. Downloads

| Platform | File | Size | Install |
|----------|------|------|---------|
| **Android** | `AI-Trading-Lab-v4.0-Android.apk` | 50 KB | Copy to phone → open → allow "install unknown apps" → install |
| **Windows (mini-services SERVER)** | `AI-Trading-Lab-v4.0-Windows-Server-mini-services.zip` | 11 MB | Unzip on the PC that will run the engine → install Node.js LTS (nodejs.org) → double-click `deploy\start-local-windows.bat` — includes trading-engine + web app + database with 253k real bars + invitation code, ready in ~15 min first run |
| **Windows (client app)** | `AI-Trading-Lab-v4.0-Windows.zip` | 110 MB | Unzip anywhere → run `AI Trading Lab.exe` (portable — no installer, no admin rights) — thin monitor shell that connects to a running server |
| **One-click setup (recommended)** | `setup-atl.ps1` | 11 KB | PowerShell one-shot: downloads the server zip, installs everything, creates the desktop shortcut, opens the dashboard |
| **iOS (no Mac needed)** | PWA — no file needed | — | Open the engine URL in **Safari** → Share → **Add to Home Screen** → launches full-screen like a native app |
| **iOS (native, needs Mac)** | `AI-Trading-Lab-v4.0-iOS-source.zip` | 106 KB | Xcode project — build & sign on any Mac (commands below) |
| Android source | `AI-Trading-Lab-v4.0-Android-source.zip` | 46 KB | Rebuild the APK yourself (commands below) |
| Windows source | `AI-Trading-Lab-v4.0-Windows-source.zip` | 4 KB | Electron shell source |

> 🔑 **Keep the keystore safe:** `android-app/ai-trading-lab.keystore` (password `atl-v4-release`) signs the APK. Future APK updates must be signed with the SAME keystore, or users must uninstall first.

Screenshots: `preview-register-v4.png` (invitation-code registration) · `preview-trader-dashboard-v4.png` (live trader dashboard)

### Two Windows packages — which one do you need?

| Package | What it is | Where to run it |
|---------|-----------|-----------------|
| **Windows SERVER (mini-services, 11 MB)** | The actual engine: trading strategies, consensus, burst executor, database, admin. Runs invisible in the background. | The PC that HOSTS the system (usually your main PC). Install once via `setup-atl.ps1`. |
| **Windows client app (110 MB)** | Just the monitor window — connects to a running server and shows the dashboard. Cannot trade by itself. | Any other Windows PC/laptop that wants to WATCH the system. |

Setup (server PC) now creates a **desktop shortcut "AI Trading Lab"** — one click starts the engine + opens the dashboard.

### What changed in this build (still v4.0)
- Connect screen (Android + Windows apps): pick **LOCAL** or **CLOUD** first — each mode remembers its own last address
- Sign-in now asks **Name + Email + Password** (name must match registration); registration stays Name + Gmail + Password + invitation code

All files are in this `download/` folder. The apps are thin secure shells — the whole trading system runs from YOUR server (local computer or cloud), so every device sees the same live data and you control access.

---

## 2. Connection modes — the engine must be running somewhere

### Mode A · LOCAL — phone ↔ your computer (same Wi-Fi, or USB)

Start the engine on YOUR computer:

```bash
# macOS / Linux — from the repo root:
bash deploy/start-local-mac-linux.sh

# Windows:
deploy\start-local-windows.bat
```

The script prints your computer's IP. Then connect:

| Device | URL to enter in the app |
|--------|------------------------|
| Same computer (browser) | `http://localhost:81` |
| Android/iOS app (same Wi-Fi) | `http://192.168.x.x:81` (the IP the script printed — in the app you can type just `192.168.x.x`) |
| Android via **USB cable** (more reliable than Wi-Fi) | `adb reverse tcp:81 tcp:81` then in the app: `http://127.0.0.1:81` |

### Mode B · CLOUD — connect from anywhere

Deploy the engine once on a VPS (Ubuntu, ~$5/mo):

```bash
# copy the repo to the server, then:
sudo bash deploy/deploy-cloud.sh your-domain.com
# (no domain yet? run without argument — you get an http://<server-ip> URL)
```

Every device then enters just `https://your-domain.com` — works on mobile data, from any city. Engine auto-restarts on reboot (systemd), HTTPS is automatic (Caddy).

**Switching modes:** tap "Change server" (Android/Windows) or "Forget this server" in the connect screen and enter the other URL. Your 2FA enrollment stays valid per-server.

---

## 3. First-time setup (2 minutes)

1. Start the engine (Mode A or B above).
2. Open the app → enter the server URL → CONNECT.
3. **Admin login:** `muhammadasterschool@gmail.com` / password `AurumLab2026` (forgot it? run `bun scripts/reset-admin.mjs` in the install folder) → scan QR with Google Authenticator → enter 6-digit code.
4. **Invite a user:** Admin tab → Invitation codes → the master code `M•••••••(REDACTED)` is pre-seeded (unlimited uses), or create a fresh single-use code.
5. **User joins:** they open the app → same server URL → **Register** → enter the invitation code + their name + Gmail + password → sign in → scan their own 2FA QR. Their paper account is created automatically, fully isolated from yours.
6. Autopilot: Paper tab → switch ON → the engine now fires **1 trade/sec bursts** whenever ≥2 strategies reach ≥60% consensus and the confirmation candle closes.

---

## 4. iOS native build (optional, needs a Mac)

```bash
unzip AI-Trading-Lab-v4.0-iOS-source.zip && cd ios-app
bun install            # or npm install
npx cap sync ios
open ios/App/App.xcworkspace     # Xcode → select your iPhone → Run
# For your own device: Xcode → Signing & Capabilities → your Apple ID (free works)
```

The App Store is NOT required — a free Apple ID can sideload to your own iPhone (re-sign every 7 days) or a $99/yr developer account installs via TestFlight-free ad-hoc for 1 year.

---

## 4b. Rebuild the Android APK yourself

```bash
unzip AI-Trading-Lab-v4.0-Android-source.zip && cd android-app
# needs: JDK 17, Android SDK (platform 34, build-tools 34.0.0), Gradle 8.9
echo "sdk.dir=/path/to/android-sdk" > local.properties
gradle assembleRelease
# output: app/build/outputs/apk/release/app-release.apk
# (signed with the included keystore — same key = updates install over the old app)
```

---

## 5. What's inside v4

- ✅ Invite-only registration (invitation code + name + Gmail) — no code, no account
- ✅ Mandatory 2FA on every login (admin and users)
- ✅ Admin (muhammad) inside the monitor app: all users, invitation codes, approvals, kill switch — old separate admin APK retired
- ✅ Local (Wi-Fi/USB) and Cloud connection modes with in-app server switcher
- ✅ 5 YouTuber M1 strategies, 60% consensus, confirmation candle, burst mode 1 trade/sec
- ✅ Crash radar + next-move prediction (logged accuracy, no cherry-picking)
- ✅ Auto-scan with DSR noise bar, walk-forward backtests with real costs
- ✅ Real verified data: OKX live feed (PAXG gold, BTC) + Binance Vision checksummed dumps (253k+ bars)
- ✅ Prop-firm risk engine checked before every fill; paper only — no live orders possible

**Verify build integrity:** the APK is signed (CN=AI Trading Lab, O=Muhammad); Windows zip contains the signed folder `AI-Trading-Lab-v4.0-Windows/`.

---

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| App says "Cannot reach the engine" | Engine script still running? Same Wi-Fi? Correct IP (`ipconfig` / `ifconfig`)? Try USB mode |
| Registered but can't login | After registering you must sign in — then enroll 2FA (QR) — then enter the 6-digit code |
| Lost 2FA device | Admin → Users → your account → Reset password (resets 2FA; you scan a new QR on next login) |
| Gateway port 81 busy | Edit `deploy/Caddyfile.local` first line to another port; enter URL with that port |
| Cloud domain not HTTPS yet | DNS A-record must point at the VPS before running deploy-cloud.sh |
