# AI Trading Lab - v5 UPGRADE PLAN (All-World + Phone + News)

Status: v4 live (paper trading running). v5 phases below.

## Phase 1 - Phone-First (SHIPPED)
- termux-setup-atl.sh: full system on the phone itself (no PC)
- App Local mode -> 127.0.0.1, or browser http://127.0.0.1:81
- Background running via termux wake lock

## Phase 2 - All-World Instruments Ledger
- New DB table: Instrument (symbol, exchange, assetClass, status, autoRegistered, discoveredAt)
- Auto-discovery: Binance exchangeInfo poller -> new symbol = auto-register
  -> data ingest starts -> auto-scan picks strategies -> paper trades begin
- Coverage: all crypto pairs (Binance/OKX) first, then Gold/Forex/US stocks
- Instrument Ledger UI tab: searchable table of every instrument + data status

## Phase 3 - System Ledger (Logs + History)
- New DB table: SystemLog (timestamp, level, component, event, details JSON)
- Every engine action logged: discovery, signals, orders, risk, errors
- Immutable history ledger + export (CSV/JSON) + retention policy

## Phase 4 - News Engine
- RSS/economic calendar ingest (free sources) -> z-ai-web-dev-sdk sentiment
- Event filter: high-impact news pauses burst executor near release
- Optional news-momentum strategy added to the 5 existing strategies

## Phase 5 - Cloud + Live
- Rent VPS ($5-10/mo), attach domain (free subdomain or cheap .com)
- Same setup-atl.ps1 / termux script points at the cloud server
- Broker APIs (paper first, then live): Binance (crypto), OANDA (gold/forex),
  Interactive Brokers (stocks/all-world), Alpaca (US stocks)
- Live mode stays behind 2FA + kill switch + daily 5% circuit breaker

## What the owner must arrange (requirements)
1. Paper trading now: NOTHING - all free (preview URL = temporary domain)
2. Phone install: Termux app (F-Droid) + ~2 GB storage + charger
3. v5 cloud later: VPS rental + (optional) domain name
4. Live later: broker account + API keys (Binance/OANDA first)
5. Keep the Android keystore (REDACTED-ROTATE-KEYSTORE) for app updates
