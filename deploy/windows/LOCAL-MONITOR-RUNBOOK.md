# LOCAL MONITOR RUNBOOK — Windows PC + Android phone, zero rentals (v4.0)

Audience: a beginner. You will install the engine on your own Windows
PC, start the LOCAL MONITOR, and pair your phone to it with an
invitation code. **You rent NOTHING.** There is no VPS, no DNS, no
certificate in this path.

If you later want remote access over the internet, the CLOUD path
remains available (`deploy/MULTI-USER-DEPLOYMENT-GUIDE.md`) — and you
can keep BOTH profiles on the phone, switching any time.

**LIVE TRADING IS NOT AUTHORIZED. This monitor runs the engine's
paper-only mode. PAPER_READY stays FALSE.**

---

## What you need (5 minutes of prerequisites)

1. A Windows 10/11 PC with **Python 3.11+** installed
   (python.org — during install, tick "Add python.exe to PATH").
2. The Windows package zip
   (`ai-trading-lab-data-engine-windows-v0.4.0.zip` from the
   repository's Releases page).
3. The Android APK (`ai-trading-lab-monitor.apk`) on your phone.
4. Your **invitation code** — issued to you out-of-band by the owner
   (it is NEVER written in these files; the engine holds only a salted
   hash of it).

## Step 1 — install the engine on the PC

Extract the zip, open PowerShell **inside the extracted folder**, and:

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer creates an isolated `.venv`, installs the locked
(hash-pinned) dependencies + the engine wheel, and runs a fail-closed
smoke test. Any error stops everything — nothing half-installs.

## Step 2 — start the local monitor

```powershell
.\run-monitor.ps1
```

First run, it creates two files NEXT TO the scripts (both yours,
never committed anywhere):

- `local-monitor.json` — copied from the package's salted-hash
  template (the invitation code inside it is a HASH, not the code);
- `monitor-token.txt` — the monitoring token your phone will receive
  via pairing (delete this file to invalidate the paired phone).

By default the monitor binds `127.0.0.1` (loopback). To pair a real
phone over your Wi-Fi:

```powershell
.\run-monitor.ps1 -AllowLan
```

`-AllowLan` prints your PC's Wi-Fi address (e.g.
`http://192.168.1.5:8018`), announces the PC on the network via mDNS
so the APK can auto-discover it, and shows the honest warning:

> **LAN traffic is UNENCRYPTED outside this PC.** Use only on a
> network you trust, and stop the monitor when you are not using it.

If your phone cannot connect, allow the port once (printed by the
script):

```powershell
netsh advfirewall firewall add rule name="AI Trading Lab monitor" dir=in action=allow protocol=TCP localport=8018
```

Android emulator on the SAME machine? Leave the default loopback
binding and use `127.0.0.1:8018` as the PC address in the app.

## Step 3 — pair the phone

1. Install the APK, open it.
2. Choose **LOCAL COMPUTER**.
3. Fill in: a name, your Gmail/email (identity only — no sign-in, no
   OAuth happens; the engine redacts it to `***@domain` in its audit
   log), your invitation code, and the PC address (usually
   auto-filled via mDNS; type it manually if the search finds
   nothing).
4. Acknowledge the one-time unencrypted-LAN warning.
5. **Pair.** The engine verifies the code and hands the app the
   monitoring token, which is stored in Android secure storage only.

Wrong code? The app shows the engine's refusal
(`E_PAIRING_CODE_INVALID`). Five wrong tries in a minute from the same
phone rate-limit the attempt for a short while. Nothing is ever
fabricated.

## Step 4 — use it

The dashboard shows engine health, positions, PnL, risk, feed, and
audit events; the kill switch requires an explicit typed reason.
While `run-monitor.ps1` runs, the kill-switch endpoint honestly
reports 503 — a monitor-only process has NO trading session to halt
(fail-closed by design). The `Switch` action in the app bar takes you
back to the profile list WITHOUT deleting anything.

## Changing the invitation code (rotate)

```powershell
# 1. make a NEW code up, and give yourself its salted hash:
.\.venv\Scripts\python.exe -c "import secrets, hashlib, sys; salt=secrets.token_hex(16); code=input('new code: '); print('{\"version\": 1, \"enabled\": true, \"salt_hex\": \"%s\", \"code_sha256_hex\": \"%s\", \"max_attempts_per_minute\": 5}' % (salt, hashlib.sha256((salt+code).encode()).hexdigest()))"
# 2. paste the printed JSON into .\local-monitor.json (replacing it)
# 3. check it, then restart the monitor:
.\.venv\Scripts\python.exe -m data_engine.cli pair-status --config .\local-monitor.json
.\run-monitor.ps1 [-AllowLan]
```

## Honest limitations of this path

- LAN-only: the phone must be on the same network as the PC (that is
  the point of the local path). Remote access = the cloud path.
- Unencrypted: outside the PC itself, traffic is plain http on your
  LAN. Cloud profiles stay TLS end-to-end. Keep both facts in mind.
- mDNS is a convenience: some Android devices silently block
  multicast; manual address entry always works.
- The monitor is read-only + kill-switch; it never trades. The
  separate paper supervisor (`run-paper.ps1`) needs its own explicit
  confirmation and MAC key — see `README-WINDOWS-PACKAGE.md`.
