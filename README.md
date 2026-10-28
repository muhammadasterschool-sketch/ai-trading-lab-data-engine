# AI Trading Lab — Data Engine

Invite-only **paper trading** monitor & engine: 5 YouTuber M1 strategies, 60% consensus → burst mode (1 trade/sec), crash radar, next-move forecasts, auto-scan with DSR noise bar, walk-forward backtests with real costs, and a prop-firm-grade risk engine. Every login requires 2FA.

> 📐 **Full system design:** see [`ARCHITECTURE.md`](./ARCHITECTURE.md)

## Quick start (local mode)

```bash
# macOS / Linux
bash deploy/start-local-mac-linux.sh

# Windows
deploy\start-local-windows.bat
```

Then open **http://localhost:81** on the computer, or **http://\<computer-LAN-IP\>:81** on a phone (same Wi-Fi). The Android/iOS/Windows apps ask for this URL on first launch.

## Cloud mode

```bash
# on a fresh Ubuntu VPS (with a domain for HTTPS)
sudo bash deploy/deploy-cloud.sh your-domain.com
```

Apps then connect to `https://your-domain.com` from anywhere.

## Accounts

| Who | How |
|-----|-----|
| Admin (muhammad) | muhammadasterschool@gmail.com — seeded, full control: users, invitation codes, approvals, kill switch |
| Everyone else | App → **Register** → invitation code + name + Gmail + password → mandatory 2FA enrollment on first login |

No invitation code = no access. Admin can create limited single-use codes from the Admin tab.

## Platform apps (v4)

See [`download/RELEASE-v4.md`](./download/RELEASE-v4.md) — Android APK, Windows portable exe, iOS (PWA + Xcode source) with links and connect commands.

## Repo layout

- `src/` — Next.js app + APIs + engine core (`src/lib/engine/`)
- `mini-services/trading-engine/` — realtime engine (:3003)
- `android-app/` · `windows-app/` · `ios-app/` — native client shells
- `deploy/` — local & cloud runbooks
- `prisma/` + `db/` — schema & SQLite database
- `scripts/` — seed, invites, data backfill, tests (`bun scripts/test-engine.ts`, `bun scripts/test-burst.ts`)

## Safety

Paper only — no exchange keys, no live orders, ever. Risk engine enforces daily-loss 5%, trailing drawdown 10%, per-trade 1%, burst 0.1%, cooldowns, kill switch — checked before **every** fill.
