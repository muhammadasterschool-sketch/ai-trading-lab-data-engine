# ADMIN PANEL + FULL CONTROL — Owner Runbook (v1.0.0)

Two APKs, one engine, all under your control:

| APK | Purpose | Version |
|-----|---------|---------|
| **AI Trading Lab** (monitor) | Everyday dashboard: health, risk, feed, PnL, positions, trades chart, STOP button | 1.0.0 |
| **AI Trading Lab Admin** (admin panel) | Ownership console: who is logged in, registration ledger, trade ledger, STOP button | 1.0.0 |

Both connect to the SAME engine URL + token on your PC. LIVE TRADING
IS NOT AUTHORIZED. PAPER_READY stays FALSE.

## What the engine gained in v1.0.0

When you start the monitor (`run-monitor.ps1`), the engine now keeps
a `monitor-state\` folder next to it with three honest files:

- `kill_switch_state.json` — the durable STOP flag (see below)
- `registrations.json` — first-contact ledger of every client that
  ever connected (name, email, kind, device, IP, when)
- `trade_ledger.jsonl` — one line per recorded trade (symbol, side,
  quantity, price, PnL, strategy)

New read-only API routes (token-authenticated like everything else):
`/api/users`, `/api/registrations`, `/api/ledger/trades`,
`/api/ledger/stats`.

## Who is "logged in"?

Every APK request carries SELF-REPORTED identity headers
(X-Client-Name / X-Client-Email / X-Client-Kind). The admin panel's
**Users** tab shows who is connected RIGHT NOW (online = the engine
saw them in the last 90 seconds); **Registrations** shows everyone
who EVER connected. This is a lab trust domain: identity is as honest
as the client sending it — the bearer token remains the only real
authentication.

## STOP trading (kill switch) — real and durable

- **From either APK**: the STOP TRADING button asks for a reason and
  sets the durable flag — the engine answers `kill_switch: ACTIVE`
  and the flag SURVIVES restarts.
- **What it honestly is**: monitor-only mode runs NO trading session,
  so there is nothing to interrupt mid-flight. The flag is the
  standing STOP decision for this install — any composed trading
  session must honor it before executing.
- **Resume is PC-gated ON PURPOSE** (fail-safe direction):

  ```powershell
  cd C:\AITradingLab\ai-trading-lab-data-engine-windows-v1.0.0
  .\.venv\Scripts\python.exe -m data_engine.cli control-reset
  ```

  The API has NO reset route — only you, at the machine, can resume.

## Trade ledger honesty

"kis pe trade li, kitna profit hua" — the ledger fills when a
trading session actually records fills. In monitor-only mode the
honest answer is an empty ledger (`total_trades: 0`); both APKs show
that empty state instead of fabricating history. When a paper session
runs on this install, its records land in `trade_ledger.jsonl` and
flow straight to both phones.

## Troubleshooting

- **Admin panel says "connection error"**: engine not running, wrong
  URL, or `-AllowLan` missing for a Wi-Fi phone (loopback binds
  127.0.0.1 only).
- **"invalid or expired token"**: token file changed — re-enter the
  token in both APKs (or re-pair the monitor).
- **`/api/users` shows (anonymous)**: an authenticated client that
  sends no identity headers (e.g. a curl probe). That is honest.
