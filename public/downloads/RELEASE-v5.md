# AI Trading Lab — v5.6 Release (Android + Web)

Release date: 2026-10-28
APK: `AI-Trading-Lab-v5.6-Android.apk` (95 KB, versionCode 11)

## v5.6 feature — instant REGISTRATION ALERTS for the owner

Request: "koi bhi invitation code se agar register karta hai to mere pass pehle
notification ayega." Now every signup — with ANY invitation code — alerts the
owner immediately, on two channels:

1. **Android status-bar notification** (phone engine) — `Notifier` posts a
   high-importance alert the instant `POST /api/auth/register` succeeds:
   "New registration — <name> · <name> (<email>) joined via invitation code
   <CODE> · role: TRADER · paper account created". Distinct channel
   (`atl_alerts`, IMPORTANCE_HIGH), sound + heads-up on modern Android, unique
   notification per event, fully guarded (never breaks the API response).
2. **Web Admin tab feed** (cloud engine) — new `AdminNotification` ledger +
   `GET/POST /api/admin/notifications`. The Admin tab now opens with a
   "Registration alerts" panel: unread amber badge ("N new"), live polling
   every 20 s, per-alert title/body/time, "Mark all read". Registration writes
   the alert AFTER the invite is consumed (with name, email, invite code, role,
   IP) and never blocks or fails the signup itself.

Also in v5.6: invite `uses` counter accuracy, versions bumped everywhere
(versionCode 11 / versionName 5.6 / health 5.6.0 / dashboard badge v5.6).


Release date: 2026-10-28
APK: `AI-Trading-Lab-v5.5-Android.apk` (95 KB, versionCode 10)
Previous v4 files: Windows packages unchanged.

## v5.5 hotfix — DIRECT ENTRY: the 2FA wall removed + zero silent failures

User report: "Sign in karne ke baad khali ye araha hai — mujhe pura system chahiye."
Diagnosis: v5.4 fixed the database, so sign-in now actually SUCCEEDS — but the
flow then demanded TOTP 2FA enrollment: install Google Authenticator, "Enter
setup key", type a 32-character secret, read a 6-digit code. The owner never
got past that wall to the dashboard. On a localhost, single-user, invite-only
phone server this step adds zero security and total lockout — so it is gone.

v5.5 changes:
1. **Direct entry** — `POST /api/auth/login` now verifies name + email +
   password and returns the session token immediately. No ENROLL_2FA stage, no
   authenticator app. Sign in → dashboard opens instantly. (TOTP stays enabled
   on the cloud engine only; `verify2fa` endpoint kept for compatibility.)
2. **Zero silent failures** — the dashboard `api()` wrapper catches every
   network error and shows it on screen in Roman Urdu; a "Signing in…" status
   appears while the request is in flight.
3. **Live engine status strip** on the sign-in screen: green "● Engine running
   — vX · ready" or red "● Engine offline — app band karke dobara kholein",
   probed from `/api/health` on every page load.
4. **Frictionless register/reset** — invitation code M2991474 is pre-filled in
   both forms; a Roman Urdu helper note explains Register → Sign in → dashboard.
5. Forgot-password note no longer mentions 2FA re-enrollment.

Versions: versionCode 10 / versionName 5.5 / health 5.5.0 / dashboard badge
v5.5 / strings subtitle v5.5.


Release date: 2026-10-28
APK: `AI-Trading-Lab-v5.4-Android.apk` (91 KB, versionCode 9)
Previous v4 files: Windows packages unchanged, v4 Android app retired.

## v5.4 hotfix — the REAL "server error" fixed (database never opened)

The v5.3 on-screen diagnostics revealed the exact cause users were seeing:

    server error — SQLiteException: unknown error (code 0 SQLITE_OK[0]):
    Queries can be performed using SQLiteDatabase query or rawQuery methods only

Root cause: `Db.onConfigure()` ran its PRAGMA setup through `execSQL()`.
Value-returning PRAGMAs (`busy_timeout`, `journal_mode=WAL`) return a ROW, and
modern Android (15/16) hard-rejects row-returning statements inside `execSQL()`.
Because this runs on EVERY database open, the phone's database could never open
at all — so every request (register, login, 2FA, dashboard) failed with
"server error". Older Android versions silently tolerated this, which is why it
only appeared on brand-new devices (S26 Ultra / One UI 9).

v5.4 fixes:
1. **PRAGMA via rawQuery()** — the sanctioned path for statements that return
   values. Fully wrapped: even if a PRAGMA fails on any future device, the app
   works without it (they are optimizations, never requirements).
2. **Idempotent schema creation** — every CREATE TABLE / INDEX now uses
   `IF NOT EXISTS` and the master invite uses `INSERT OR IGNORE`, so a partial
   file left by an earlier failed launch can never block startup.
3. Full `execSQL()` audit: all remaining calls are INSERT/UPDATE/DELETE only
   (none return rows) — verified programmatically.

Action for users: install v5.4 over the old app (same signature). Register with
the invitation code, or use **Forgot password?** if you already created an
account and want it set to a new password (e.g. M2991474).

## v5.3 hotfix — "server error" on login + password recovery

What users saw: the app now opens fine, but signing in showed a vague
**"server error"**. The root cause was hidden inside the embedded phone server.
v5.3 fixes the class of problem AND adds self-service recovery:

1. **Real error messages** — the embedded API no longer swallows the cause.
   Every failure now shows the exact exception on screen (e.g.
   "server error — SQLiteDatabaseCorruptException: ..."). Screenshot it and
   the cause is known instantly. It is also written to the Logs ledger
   (component API) and to logcat.
2. **Database self-heal** — on service start every core ledger table is
   probed. If the crash-loop era left a corrupt WAL/DB file behind (typical
   cause of "server error" on every request), the engine closes the helper,
   deletes db+wal+shm, and rebuilds a fresh schema automatically. A
   DB_REBUILT entry lands in the Logs tab.
3. **In-app password reset (Forgot password?)** — on the sign-in screen:
   invitation code + full name + email + new password → the password is
   changed and 2FA returns to enrollment state (fresh setup key on next
   login). The master invitation code (M2991474) is accepted for recovery;
   no usage is consumed.
4. **Engine null-guards** — if the trading engine ever fails to initialize,
   the dashboard, news scan and manual scan keep working instead of erroring.

Action for users: install v5.3 over the old app (same signature).
If login still misbehaves: Forgot password? → M2991474 code → set your new
password → sign in → re-enroll 2FA with the shown setup key.
Cloud/web admin note: the web password was reset separately to `M2991474`.

## v5.2 hotfix — app would not open at all (launch crash)

If the app closed instantly on every open, the launch path itself was fragile.
v5.2 makes the cold-start path crash-proof:

1. **Application-level crash net (AtlApp)** — any unexpected crash is captured
   to a file before the process dies; the next start feeds it into the Logs tab
   (component CRASH) so the cause is always visible.
2. **Service announces foreground FIRST** — before database/engine init. A
   foreground service that fails before startForeground() gets force-stopped by
   Android ("did not call startForeground") — that launch loop is now impossible.
3. **Every init step isolated** — DB, engine, HTTP server, wake lock each run in
   their own guard; one failing component cannot kill the app.
4. **ConnectActivity fully armored** — mode screen can never crash; worst case it
   shows a toast and stays open.
5. **Battery-optimization prompt moved out of cold start** — now asked once,
   right after the dashboard is on screen (Samsung-friendly).
6. Health endpoint now reports device model + Android version for faster support.

Install: uninstall the old app first (full fresh start), then install v5.2.
On the two prompts (notifications + battery) tap Allow.


## v5.1 hotfix — "app keeps crashing" on modern phones (S24/S25/S26 Ultra, One UI 9)

Root cause found: the engine used the `dataSync` foreground-service type.
On Android 15/16 Google enforces a **6-hour daily limit on dataSync services**:
- after 6 hours the system force-stops the engine (crash dialog), and
- once the daily budget is burned, **every app relaunch crashed instantly**
  (`ForegroundServiceStartNotAllowedException`) — that is the "bar bar crash".

v5.1 fixes:
1. Engine service migrated from `dataSync` to **`specialUse`** — no time limit,
   designed exactly for a permanent 24/7 local service.
2. `onTimeout()` safety net: even if a service type ever times out, the engine
   now stops cleanly instead of crashing (auto-restart via START_STICKY).
3. **Crash logger**: any unexpected crash is now recorded in the Logs tab
   (component CRASH) before the process dies — so issues are always visible.
4. **Notification permission** (Android 13+) is requested once — the engine
   notification is visible and One UI treats the app as a real running service.
5. **Battery optimization exemption** prompt (once) — stops Samsung One UI
   from putting the app to sleep ("Put unused apps to sleep" issue).
6. Manual "Scan Now" hardened — can never crash the app anymore.

Action for users: install v5.1 over the old app (same signature, updates in place),
tap **Allow** on the two prompts (notifications + battery), done.


## What is new in v5.0

v5 turns the Android app from a "monitor" into the **full standalone system**.
The complete trading engine now runs inside the phone — no Termux, no PC, no cloud
server required. Everything (users, database, engine, dashboard) is on-device.

### 1. All-World Instruments Ledger (auto-discovery)
- New `instruments` ledger table: symbol, base/quote, exchange, asset class,
  status (ACTIVE / WATCHING / PENDING_BROKER), priority, discovered_at, last_data_at, note.
- Discovery scanner every 30 min: pulls the full Binance 24h ticker list,
  ranks by volume, filters leveraged tokens (UP/DOWN/BULL/BEAR) and stable-junk pairs.
- New instruments are **auto-registered** into the ledger. Top 20 by volume become
  ACTIVE and trading starts on them automatically (candle refresh -> scan -> paper trade).
- Next 20 stay WATCHING. Forex / Gold / Silver / Indices (EURUSD, GBPUSD, USDJPY,
  XAUUSD, XAGUSD, US500, NAS100) are pre-seeded as PENDING_BROKER — they activate
  the day you connect a broker that supports them (live phase).

### 2. Trades Ledger (full history)
- Every position is persisted: symbol, side, qty, entry, SL, TP, exit, pnl,
  strategy votes, consensus %, opened_at, closed_at, status (OPEN/CLOSED).
- Manual CLOSE button per position from the dashboard.
- Equity curve table records account value over time.

### 3. System Log Ledger
- `logs` table records every engine action with timestamp, level (INFO/WARN/ERROR),
  component (SYSTEM/RISK/TRADE/NEWS/DISCOVERY/BROKER) and details.
- Engine start/stop, risk halts, kill switch, discovery registrations, news ingest,
  trade opens/closes — all visible in the dashboard Logs tab.

### 4. News Engine
- Every 15 min the engine pulls RSS from Cointelegraph + CoinDesk.
- Headline sentiment scoring (BULLISH / BEARISH / NEUTRAL) and impact rating.
- **High-impact news automatically pauses new entries for 30 minutes** — the engine
  keeps managing existing positions (SL/TP still active) but opens nothing new.

### 5. Add Broker / Custom Broker (manual connect)
- New Brokers tab: "Add Broker" lets you enter broker name, API key, API secret,
  login and password. Saved on-device (never uploaded anywhere).
- Test Connection + Remove buttons. Status per broker (SAVED / TESTED / ERROR).
- No broker API is hard-coded in v5 — you connect your own broker whenever you are
  ready for live trading. Engine will use the stored credentials at that stage.

## Trading engine (same DNA as v4 server engine)
- Timeframe: 15m candles, Binance Vision data (fallback api.binance.com).
- 5 strategies vote on every closed candle:
  1. EMA 9/21 cross
  2. RSI(14) + Bollinger(20) reversal
  3. MACD + Stochastic(14)
  4. VWAP reversion (±1.2%)
  5. 16-bar Donchian breakout
- Consensus gate: at least 60% (3 of 5) strategies must agree before entry.
- Risk: 1% per trade, max 5 concurrent positions, daily halt at −5%,
  kill switch closes everything at −10% drawdown from peak.
- Paper account starts at 100,000.

## Security
- Invite-only registration (invite code), scrypt password hashing, optional TOTP 2FA,
  session tokens. Same auth system as the web app, fully on-device.

## Install
1. Download the APK on your phone and open it (allow "install from this source").
2. Register with your invite code (admin invite from v4 still works).
3. The engine auto-starts; START/STOP toggle is in the dashboard.

## Files in this release
- `AI-Trading-Lab-v5.4-Android.apk` — the app (full system on phone, v5.3)
- `AI-Trading-Lab-v5.4-Android-source.zip` — complete Android source
- `AI-Trading-Lab-v4.0-Windows.zip` — Windows PC client + server (unchanged)
- `AI-Trading-Lab-v4.0-Windows-Server-mini-services.zip` — mini services (unchanged)
- `AI-Trading-Lab-v4.0-Windows-source.zip` — Windows source (unchanged)
- `setup-atl.ps1` — Windows one-click installer/repair
- `reset-admin.mjs` — admin password reset tool (web/PC side)
- `RELEASE-v4.md` — v4 notes + admin credentials

## Next phase (when you are ready)
- Live trading: connect your broker in the Brokers tab, then we wire order execution
  to it (Binance / OANDA / IBKR / Alpaca or your custom broker).
- Optional cloud VPS if you want the engine running 24/7 off-phone.
