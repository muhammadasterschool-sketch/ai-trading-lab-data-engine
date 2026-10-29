# AI Trading Lab — v3.0.1 "FIXED ENTRIES" (versionCode 30)

## 🔴 Kya masla tha? (v3.0 me trades kyun nahi lag rahi theen)

Owner report: **"Bhai ye to trades hi nahi le raha"** — diagnosis ki aur 3 root causes mile:

### 1. SAFE MODE false-positive (MAIN KILLER)
- v3.0 ka stale-data guard (`freshData`) candle ko 10 min (2×TF) se purani hone par SAFE MODE me dal deta tha = **naye entries band**
- Lekin Yahoo futures feed **sirf CLOSED bars** deta hai (in-progress bar nahi) — live test me newest candle hamesha **5–11 min purani** milti hai (measured: 10.13 min)
- Nateeja: SAFE MODE lagbhag hamesha ON = **koi entry kabhi nahi**
- **Fix**: threshold ab `safe_mode_bars` setting (default 3 bars = 15 min) + market-band awareness (neeche)

### 2. Market band = SAFE MODE alarm (galat state)
- Weekend + CME daily maintenance halt (17:00–18:00 ET) par candles purani ho jati hain — ye feed failure NAHI
- **Fix**: naya `marketClosedET()` — America/New_York timezone me weekend/halt detect karta hai. Band market par SAFE MODE nahi lagta; entries waise bhi live-trigger ki wajah se naturally nahi hoti (live candle hi nahi banti)
- Dashboard par ab **amber "Market BAND hai" banner** aata hai taake confusion na ho

### 3. Volume filter zero-volume setups maar raha tha
- Yahoo futures ke overnight bars par volume aksar **0** hota hai (= unknown, zero participation nahi)
- PRO FILTER PACK ka volume check (`c3.v <= 1.2×SMA20`) aise setups ko "weak volume" reject kar deta tha — overnight setups sab dead
- **Fix**: `c3.v > 0` guard — unknown volume par check SKIP, reject nahi

## ✅ NAYA: "🔍 Why no trades?" card (Home par)
Ab dashboard Home par 24h engine report card hai — saaf nazar aata hai engine kya kar raha hai:
- **3C SETUPS BANE** / **PRO FILTER REJECT** / **BREAKOUT NAHI HUA (expire)** / **INVALIDATED** / **ENTRIES EXECUTED** — sab 24h counts
- Market OPEN/BAND indicator + newest candle age (min) + data-kam symbols count
- Roz 1–4 valid setup **normal** hai — 3C strict pattern hai (C1+C2 70% body + C3 protected close + 5-candle breakout), har candle par trade nahi banti

## 🔒 Jo NAHI badla (hard rules)
- **3C MASTER rules UNTOUCHED** — sirf aas-paas ki guards theek ki gayin
- **Daily P/L UNLIMITED** — koi kill/limit default ON nahi
- Owner approval gates (approved + trade_ok) barkarar
- Halal-only universe (27 commodities) barkarar

## 📦 Install
1. Purani app ke upar hi install karein (same signature — data nahi udega)
2. App kholein → Home par naya "Why no trades?" card dekhein
3. Agar market band ho to amber banner dikhega — market khulte hi (Sun 18:00 ET / weekday) trades apne aap shuru
4. Optional: Settings me `safe_mode_bars` (default 3) — feed late ho to barha sakte hain

## Files
- `AI-Trading-Lab-v3.0.1-Android.apk` — signed release (same keystore)
- `AI-Trading-Lab-v3.0.1-Android-source.zip` — poora source
- `mt5-bridge.py` — Windows MT5 bridge (unchanged)
