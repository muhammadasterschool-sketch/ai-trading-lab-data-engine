# AI Trading Lab — v2.1 "HALAL MT5" (versionCode 28)

**Release date:** Oct 29 · **APK:** `AI-Trading-Lab-v2.1-Android.apk` · **Source:** `AI-Trading-Lab-v2.1-Android-source.zip`

## 1 · Binance → MT5 (HALAL MODE)

Owner request: *"binance ke bajaye mt5 ki api se connect kardo aur ismai sare halal commodities ko add karke baki delete kardo"*

- **Binance feed retired** — engine ab **27 halal commodities** ka MT5-style universe use karta hai (sirf physical commodities):
  - **Metals (6):** XAUUSD Gold, XAGUSD Silver, XPTUSD Platinum, XPDUSD Palladium, XCUUSD Copper, ALUUSD Aluminium
  - **Energy (5):** USOIL WTI, UKOIL Brent, NGAS Natural Gas, GASOLINE, HEATOIL
  - **Agriculture (16):** WHEAT, CORN, SOYBEAN, SOYMEAL, SOYOIL, RICE, OATS, COFFEE, COCOA, SUGAR, COTTON, ORANGEJ, CATTLE, FEEDER, HOGS, LUMBER
- **Crypto, forex, indices, stocks, bonds, ETFs — sab removed** (upgrade par DB se purge: instruments + candles; removed symbols par khuli paper trades CANCEL exit=entry pnl=0)
- **Data source (2 modes):**
  1. **Built-in (default, zero setup):** real commodity futures candles (CME/CBOT 5m, Yahoo chart API) — MT5 symbols ke liye public feed. Kuch configure nahi karna.
  2. **MT5 Bridge (optional, real MT5 terminal):** PC par `mt5-bridge.py` chalayen (MetaTrader5 terminal + `pip install MetaTrader5`), phir app me **Settings > MT5 DATA FEED** me bridge URL dalein — candles seedha aapke MT5 broker ke prices se aayengi.
- Rate-limit guard: per-symbol 60s refresh (`feed_interval_sec` setting se tune ho sakta hai) · 4-din rolling candle window · session-gap null bars skip
- News engine ab commodities sources par (Investing.com commodities + OilPrice RSS); high-impact keywords me OPEC/sanctions/drought waghaira
- Strategy Lab backtest default symbol: XAUUSD

## 2 · Registration + Trading se pehle owner se pooch (double gate)

Owner request: *"registration aur trading karne se pehle mujhse pooch"*

- **Gate 1 — Registration (v1.9, barkarar):** register → owner ko notification → owner APPROVE → tabhi login.
- **Gate 2 — TRADING (naya v2.1):** approval ke baad bhi naya user **trade nahi kar sakta** jab tak owner **Control > Users me ▶ ENABLE TRADING** na dabaye.
  - Trading-blocked user ka signal aye to engine trade skip karta hai aur owner ko foran batata hai: status-bar notification + Control feed (TRADE_REQUEST) + ledger
  - Per-user throttle 30 min (spam nahi) · owner apna trading kabhi band nahi kar sakta
  - Users list me ab har user ka **TRADING ON/OFF** pill + **▶ ENABLE TRADING / ⛔ STOP TRADING** button
- Pre-written master invite code (M2991474) ab **fresh installs me bhi seed nahi hota** aur purane installs par deactivate — codes sirf owner Control se generate hote hain

## 3 · 3C MASTER — koi tabdeeli nahi

3C rules (M5, body≥70%, C3 protected, 5-candle window, SL/BE@+1R/TP@+3R), PRO FILTER PACK (zone 0.25% + EMA200 + ATR floor + volume), risk 2% (0.1–20%), fees 0.05%/side, UNLIMITED daily (kill switch opt-in OFF) — **sab waise ke waise**. Sirf market (symbols) aur data source badla gaya hai.

## Technical notes

- `Db.java` VERSION 5→6: `users.trade_ok` (ADMIN=1), `brokers.server`, halal universe purge migration
- `EngineCore.java`: MT5_FEED map (27 symbols→futures tickers), fetchFromBridge/fetchFromYahoo, tradingAllowed() gate openTrade3C/openTradeLab dono me, discover() → universe maintenance (6h stale→WATCHING)
- `Api.java`: POST /api/admin/users action `trade` {id, value}, settings mt5_bridge, brokers server field + MT5 validation (login+password required, API key optional), /api/candles regex 4–20 chars (CORN/RICE/OATS/HOGS ke liye)
- Same keystore — v2.0 ke upar seedha install hoga, data rahega
- Broker vault (side drawer > Broker) ab MT5-first: type MT5/MT4 default, server field, MT5 ke liye login+password kaafi
