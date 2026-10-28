# AI Trading Lab — Data Engine · Architecture (v4.0)

> Single source of truth for how the whole system fits together.
> Companion documents: [`README.md`](./README.md) (quick start) · [`deploy/`](./deploy/) (local & cloud runbooks) · [`RELEASE-v4.md`](./download/RELEASE-v4.md) (app builds + links)

---

## 1. System Overview

```
                        ┌──────────────────────────────────────────────────────┐
                        │                    DEVICES (clients)                 │
                        │  Android APK · Windows exe · iOS (PWA/source) · Web  │
                        │  ── all are shells that point at ONE engine URL ──   │
                        └───────────────────────┬──────────────────────────────┘
                                                │  http(s) + WebSocket
                                                ▼
                        ┌──────────────────────────────────────────────────────┐
                        │              GATEWAY (Caddy, port 81 / 443)          │
                        │  • /            → localhost:3000  (Next.js app+API)  │
                        │  • ?XTransformPort=3003 → engine (socket.io)         │
                        └──────────┬───────────────────────────┬───────────────┘
                                   │                           │
                     ┌─────────────▼────────────┐  ┌───────────▼────────────────┐
                     │  WEB APP (Next.js :3000) │  │  TRADING ENGINE (:3003)   │
                     │  • 8-tab monitor UI      │  │  • socket.io realtime     │
                     │  • REST APIs /api/*      │  │  • 1s ticks · 1m candles  │
                     │  • Auth: 2FA + invites   │  │  • strategies + consensus │
                     │  • Backtest / Auto-Scan  │  │  • burst executor + risk  │
                     └─────────────┬────────────┘  └───────────┬────────────────┘
                                   │        Prisma ORM          │
                                   └────────────┬───────────────┘
                                                ▼
                        ┌──────────────────────────────────────────────────────┐
                        │        SQLite (db/custom.db) — 20 models             │
                        │  users · sessions · invites · bars · strategies      │
                        │  scans · backtests · paper accounts/orders/trades    │
                        │  consensus · predictions · crash alerts · risk       │
                        └──────────────────────────────────────────────────────┘
                                                ▲
                        ┌───────────────────────┴──────────────────────────────┐
                        │                   DATA SOURCES (real)                │
                        │  • OKX public API — live PAXG-USDT (gold), BTC-USDT  │
                        │  • Binance Vision repo — checksummed 1m kline dumps  │
                        └──────────────────────────────────────────────────────┘
```

**Design principle (research → live parity):** one set of strategy/risk/cost modules is used by the backtester, the auto-scanner AND the live paper engine. What you backtest is what trades. Fills always model spread + fee + latency slippage + square-root market impact.

---

## 2. Deployment Modes (v4)

| Mode | Who runs the engine | Client connects to | Notes |
|------|--------------------|--------------------|-------|
| **LOCAL** | Your own computer (`deploy/start-local-mac-linux.sh` or `start-local-windows.bat`) | `http://<computer-LAN-IP>:81` (same Wi-Fi) or `http://127.0.0.1:81` via `adb reverse` (USB) | Engine runs while the computer is on |
| **CLOUD** | A VPS (`deploy/deploy-cloud.sh your-domain.com`) | `https://your-domain.com` from anywhere | systemd auto-start, Caddy auto-HTTPS |

Both modes are the SAME code and the SAME database. Switching a client between local and cloud is just entering a different URL in the connect screen.

---

## 3. Component Map (repository)

```
ai-trading-lab-data-engine/
├── src/app/                       # Next.js 16 App Router
│   ├── page.tsx                   # single-page monitor (8 tabs)
│   └── api/                       # REST endpoints
│       ├── auth/                  #   login · verify-2fa · logout · register(invite code)
│       ├── admin/                 #   users · invites (admin only)
│       ├── strategies/            #   list/update 5 YouTuber strategies
│       ├── engine/                #   start/stop/autopilot/kill/close-all control
│       ├── data/                  #   bundles list + Binance Vision fetch
│       ├── backtest/ autoscan/    #   run backtests & grid scans (DSR noise bar)
│       ├── paper/                 #   account, trades, TCA, risk events
│       ├── predictions/ approvals/#   forecasts, crash alerts, governance inbox
│       └── dashboard/             #   aggregated snapshot
├── src/components/trading/        # UI: dashboard, strategies, autoscan, backtest,
│                                  #     paper, predictions, data, admin, login
├── src/hooks/use-engine-socket.ts # socket.io client (dual-mode URL logic)
├── src/lib/
│   ├── auth/                      # scrypt passwords · RFC-6238 TOTP · sessions
│   ├── data/                      # okx.ts (live) · binanceVision.ts (repo dumps)
│   │                              # ingest.ts (SHA-256 provenance + quality gates)
│   └── engine/                    # THE CORE (shared by backtest + live)
│       ├── indicators.ts          #   20 indicators, O(n) prepare + O(1) signalAt
│       ├── strategies/index.ts    #   5 YouTuber M1 strategies + param grids
│       ├── consensus.ts           #   weighted votes → 60% threshold → confirmation
│       │                          #   candle state machine → burst mode
│       ├── crash.ts               #   crash radar + next-move forecast (5m)
│       ├── risk.ts                #   prop-firm rulebook, pre-trade check, TCA
│       ├── backtest.ts            #   costs, walk-forward folds, exit stats
│       ├── autoscan.ts            #   grid sweep + IS/OOS re-test
│       └── dsr.ts                 #   Deflated Sharpe noise bar (Bailey & de Prado)
├── mini-services/trading-engine/  # socket.io service (:3003) — live pipeline
├── prisma/schema.prisma           # 20 models (see §5)
├── android-app/                   # native Android WebView shell (APK source)
├── windows-app/                   # Electron shell (portable exe source)
├── ios-app/                       # Capacitor iOS shell (Xcode source)
├── deploy/                        # start-local / deploy-cloud scripts + Caddyfile
├── scripts/                       # seed · invites · data backfill · engine tests
└── db/custom.db                   # SQLite database (all state)
```

---

## 4. Live Trading Pipeline (engine :3003)

```
OKX tick (1s) ──► price store ──► UI "price" events
      │
      └─ minute roll ──► closed 1m bar ──► indicators (20) refresh
                                 │
                                 ▼
              5 strategies vote (direction + confidence + reason)
                                 │
                                 ▼
              CONSENSUS: weighted bullish% vs bearish%
                                 │
              ┌──────────────────┼──────────────────────┐
              │ < 60%            │ ≥ 60% (≥2 voters)    │
              ▼                  ▼                      │
           neutral        wait CONFIRMATION candle      │
                                 │ next 1m bar closes   │
                                 ▼                      │
                          BURST MODE ── 1 trade/second ─┘
                                 │
                                 ▼
                    RISK ENGINE (pre-trade, EVERY order)
                    daily-loss 5% · trailing DD 10% · per-trade 1%
                    burst 0.1% · cooldown · kill switch · crash pause
                                 │
                                 ▼
                    PAPER FILL (costs: spread + slippage + √impact)
                                 │
                    ├─ 60s time-exit (burst trades)
                    ├─ TCA ledger (arrival-price shortfall)
                    └─ UI events: account · consensus · feed
```

**Crash radar** runs on every closed bar: volatility z-score + ATR regime + velocity + streak analysis → probability & severity; HIGH/CRITICAL alerts pause new entries and log to `CrashAlert`. **Next-move forecast** (momentum + reversion + trend ensemble) predicts direction/confidence 5 minutes ahead, logged to `Prediction` and scored when resolved (real accuracy, no cherry-picking).

---

## 5. Data Model (SQLite, 20 models)

| Group | Models | Purpose |
|-------|--------|---------|
| Auth | `User` `Session` `InvitationCode` | 2FA mandatory; invite-only registration; admin/user roles |
| Market data | `DataBundle` `Bar` | provenance (URL, SHA-256), quality gates (gaps/dups/outliers) |
| Strategies | `Strategy` | 5 seeded YouTuber strategies + JSON params + scan grids |
| Research | `ScanRun` `ScanResult` `BacktestRun` | grid scans with DSR noise bar; walk-forward backtests |
| Paper trading | `PaperAccount` `PaperPosition` `PaperOrder` `PaperTrade` | per-user isolated accounts, full fill records with costs |
| Signals | `ConsensusLog` `Prediction` `CrashAlert` | consensus history, forecast log + accuracy, crash alerts |
| Risk | `RiskEvent` | every breach & action, immutable |
| Governance | `ApprovalRequest` | scan winners → approval inbox (human in the loop) |
| Engine | `EngineState` | singleton: running, autopilot, kill switch, burst snapshot |

---

## 6. Security Model (v4)

1. **Invite-only** — registration requires a valid `InvitationCode` (admin creates/disables codes; single-use codes supported). No code → no account.
2. **Mandatory 2FA** — every login (admin AND users) requires a TOTP code (Google Authenticator / Authy). First login enrolls via QR. Sessions are staged: `PASSWORD_OK` → `FULL` only after the 6-digit code.
3. **Roles** — `ADMIN` (muhammad) sees the Admin tab: all users, invite codes, approvals, kill switch. `TRADER` sees only their own paper account.
4. **Session hygiene** — DB-backed sessions, deactivation kills sessions instantly, password reset also resets 2FA.
5. **Paper only** — no exchange keys exist in the system; no live orders can ever be sent.

---

## 7. Ports & Processes

| Port | Process | What it serves |
|------|---------|----------------|
| 81 (or 443 cloud) | Caddy gateway | the single public door; static + API + WebSocket routing |
| 3000 | Next.js standalone | app UI + all REST APIs |
| 3003 | trading-engine (bun) | socket.io realtime feed + paper execution loop |

The client never talks to 3000/3003 directly in gateway mode; it only knows the gateway URL. In bare local mode (no Caddy), the app auto-detects `:3000` pages and connects the socket directly to `:3003` (dual-mode logic in `use-engine-socket.ts`).

---

## 8. Honest Limitations (carried from research report)

- All 5 strategies were net-negative on the most recent 30-day window after real costs — the DSR noise bar exists precisely so we don't fool ourselves.
- Predictions run ~57% accuracy — logged transparently, never deleted.
- The engine trades **paper** only. Live trading requires: owner attestation, hard risk limits, exchange integration — deliberately not implemented.
