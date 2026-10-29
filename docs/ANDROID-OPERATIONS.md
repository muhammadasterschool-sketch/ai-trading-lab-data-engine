# ANDROID OPERATIONS — lifecycle, resources, honest ladder

## Service topology (source-verified)

- `ConnectActivity` → "THIS DEVICE" mode (default) → `startForegroundService(ServerService)`.
- `ServerService`: FGS type `specialUse`, `START_STICKY`, `PARTIAL_WAKE_LOCK`, 30s
  engine-thread watchdog (restarts the engine thread if it dies), crash logger,
  DB repair on open.
- `WatchdogReceiver`: 9-minute exact alarm (Doze-resilient) revives the service.
- `BootReceiver`: restarts after reboot (needs "open new apps" permission on some OEMs).
- `MainActivity`: WebView on `http://127.0.0.1:8788` + battery-optimization exemption
  prompt.

## Operator runbook (owner, on-device)

1. Install candidate APK over the previous version (same signing identity).
2. Open app → register/sign in → dashboard loads (loopback only).
3. From a PC on the SAME Wi-Fi: `http://<phone-ip>:8788` MUST FAIL (LAN isolation).
4. Airplane mode off/on → engine recovers on next loop; SAFE MODE banner explains state.
5. Reboot the phone → service must return via BootReceiver within ~1–2 min.
6. Settings → battery → Unrestricted (app already prompts).
7. Insights → 📐 Markets: verify Binance card shows READ_ONLY + counters.

**All of steps 3–7 are NOT RUN in this environment (no device/emulator).** Prior
sessions' APKs were host-built only; every on-device claim in this project stops at
"source-verified".

## Mobile performance — what is measured vs not

| Metric | Status |
|---|---|
| Memory/CPU/battery on device | NOT RUN (no device) |
| SQLite growth | bounded by design: 4-day candle purge (strategy), 7-day binance purge, 4000-log cap — host-side logic only |
| Market-data request frequency | bounded by design: feed_interval_sec ≥ 20s, binance watchlist ≥ 30s, backfill batch ≤ 20/30s, weight budget 1800/min — verified by tests |
| Recovery time after network loss | NOT RUN on device; design: per-symbol backoff + watchdog revival |
| Recovery after process death | START_STICKY + watchdog + boot receiver — source-verified only |
| 24/7 reliability | **NOT CLAIMED.** OEM battery managers can kill background apps; mitigations exist but must be measured on real hardware |

## v3.1 engine loop additions

`binanceTick(now)` runs inside the main loop every ~2s and self-schedules: discovery
(12h), watchlist sync (60s), rotation backfill (30s), hourly retention purge. All
tiers stop during provider backoff. Loop errors are logged (`BINANCE/TICK_FAIL`) and
never kill the engine thread.
