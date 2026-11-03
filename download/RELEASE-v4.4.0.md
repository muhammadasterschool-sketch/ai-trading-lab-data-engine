# AI Trading Lab — v4.4.0 "ALL-BINANCE + PDF RESTORE + AI TRAINER" (versionCode 36)

**PAPER ONLY — koi real order path nahi. Ye simulation + learning tool hai.**

## Owner requests is release me (sab complete)
1. **Indicators + Strategies dono** — Shaakuni Trap Trader ka poora suite (13 indicators: PDH/PDL/PWH/PWL, EQ premium/discount, Liquidity Sweep, MSS/BOS, Order Block + mitigation, FVG, Killzones, candle setups) **+ uski 5 strategies** (SSM Sniper Bull/Bear, Killzone Sweep, OB Retest, Discount+EMA200) — ab chart par overlay bhi dikhta hai.
2. **Purani PDF strategies WAAPIS** — PDF Strategy Pack S1–S9 restored: S1 EMA Pullback, S2 BB Squeeze, S3 Supertrend+ADX, S4 VWAP Bounce, S5 PDH/PDL, S6 Funding/OI, S7 Candle Patterns, S8 Dow Pullback, S9 Gann 50% — 15m timeframe, sab pairs par. (v4.1.0 me ghalti se gayab thi — owner ne pakra, ab restored.)
3. **Saare Binance coins** — halal/haram filter KHATAM. `exchangeInfo` + 24h volume se **saare spot USDT pairs** auto-sync (300+ coins, 6h refresh): 1–10 MAJOR, 11–60 RETAIL, 61+ ALTCOIN. Chart chips top-14 + "all coins" refresh. Sirf leveraged (UP/DOWN/BULL/BEAR) aur stable-stable pairs exclude.
4. **Trade frequency fix** — pehle sirf 7 pairs × 1m scan hota tha. Ab: ACTIVE_TOP 40 (1m) + naya **15m scan layer** (30 pairs/tick rotation, poora universe ~2 min) + PDF pack S1–S9 × sab pairs har closed 15m candle par → **trades 50×+ zyada**.
5. **AI professional + profitable training** — naya **AI TRAINER**: walk-forward backtest engine (fees+slippage included), Binance 15m deep data + 1d data **2017→2026** tak (2006–2016 kisi exchange ka crypto candle data exist nahi karta — honest note), IS/OOS 70/30 split, Profit-Factor se weights, OOS PF<0.9 → strategy auto-pause. Boot + har 24h auto-train, ya Home par **🤖 TRAIN AI** button. Self-learning: har 25 closed trades par live results se re-weight.
6. **Risk rules (owner)** — har trade **1% risk flat**; min 25 closed trades tak 1%, uske baad consensus win% par scale (50% = 1×, 75% = 1.5×, cap 2×; loss-heavy < 1×).
7. **Loss killer** — **fee-edge guard**: agar TP move fees+slippage (0.14%) se chhota hai to trade skip (FEE_EDGE_SKIP log) — teeno entry paths (3C/Lab/Pack) par.

## Numbers
- versionCode **36**, versionName **4.4.0**, minSdk 24 (Android 7.0+), targetSdk 34
- APK ~254 KB, signed (CN=AI Trading Lab), zipaligned
- Tests: **41/41 host tests** (ShaakuniEngineTest 18 + V44Test 23)

## Download
- **Android APK**: `AI-Trading-Lab-v4.4.0-all-binance-ai.apk` (is folder me + GitHub Release)
- **iOS**: APK iOS par install NAHI hota. Do raste: (1) **Safari PWA** — engine apne computer par chalao (`deploy/start-local-mac-linux.sh`), iPhone Safari me `http://<computer-ip>:81` kholo, Share → Add to Home Screen. (2) **Native Xcode build** — `ios-app/` Capacitor project, Mac + Xcode chahiye. Poori guide: `iOS-Setup-Guide.pdf`.

## SHA256
```
089831c201532fd69de2a39b6dbf3942bc29359d469bd93cbe0adf1a04d75b10  AI-Trading-Lab-v4.4.0-all-binance-ai.apk
```

## Invite code
`M2991474` (pehle se active)

## 3C MASTER rules UNTOUCHED — UNLIMITED daily P/L, owner gates barkarar. PAPER ONLY.
