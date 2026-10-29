# AI Trading Lab — v1.7 "PRO GUARD" (versionCode 24)

**Date:** 2026-10-29 · **Base:** v1.6 LIVE MONEY · v1.5 SPEED · v1.4 3C MASTER

## Naya kya hai (aap ki request: "professional level par le jao — repos dekh kar")

### 🗑 Strategy UNDO (aap ki request)
- Galti se strategy delete ho jaye to **7 din tak wapas** la sakte ho
- Delete dabao → **UNDO button** 8 second toast mein dikhta hai (Gmail-style)
- Lab tab mein **🗑 Trash section** — saari deleted strategies + kitne din baaki + RESTORE button
- 7 din baad auto-purge (database saaf rehta hai)

### 🛡️ PRO GUARD — freqtrade-inspired protections (Settings tab se control)
1. **Loss cooldown (default 15 min):** SL loss ke baad us symbol par naya entry band — revenge trading se bachao (freqtrade CooldownPeriod)
2. **Consecutive-loss pause (default 3):** ek symbol par lagatar 3 SL losses = 1 ghanta pause (freqtrade StoplossGuard)
3. **Daily kill switch (default OFF):** aaj ka total loss X% cross kare to aaj ke naye entries band — aap ne UNLIMITED manga tha isliye OFF hai, chaaho to Settings mein % daal kar ON karo (freqtrade MaxDrawdown protection)

Protections sirf NAYE entries par hain — khuli trades ka SL/TP/breakeven normal chalta rehta hai.

### 💸 REALISTIC FEES
- Ab har trade par **Binance futures taker fee 0.05% per side** lagti hai (entry + exit dono)
- Paper P/L ab real trading jaisa — backtest aur live numbers mein farak nahi rahega
- Trade close log mein fees dikhti hai

## 3C MASTER rules — UNCHANGED (owner approval ke baghair kabhi change nahi)
C1+C2 body ≥ 70% · C3 protected close · 5-candle breakout window · SL opposite extreme ·
BE @ +1R · TP @ +3R (whole position) · close-based invalidation · daily P/L UNLIMITED ·
risk % aap ka (Settings)

## v1.6 yaad dila do (base)
Har open trade par **real-time floating P/L** (price + unrealized $ + R multiple) ·
Trades tab 5s auto-refresh · LIVE P/L banner · manual CLOSE button har open trade par

## v1.5 yaad dila do (base)
10s scan loop · LIVE-candle stop-order entry (breakout ke ~10s andar fill) · live SL/TP/breakeven tracking

## Technical notes
- DB VERSION 3 → 4: `strategies.deleted_at` column (idempotent migration, purana data safe)
- UNDO is soft-delete: row delete nahi hoti, `deleted_at` timestamp lagta hai
- Guard state in-memory (restart par cooldown reset — engine restart hi cooldown clears)
- Fee model: `pnl = (raw price diff) × qty − (entry+exit notional × 0.0005)`
- Same signature — purane version ke upar seedha install ho jata hai
