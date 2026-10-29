# AI Trading Lab — v1.8 "CLEAN & PRO" (versionCode 25)

**Date:** 2026-10-29 · **Base:** v1.7 PRO GUARD · v1.6 LIVE MONEY · v1.5 SPEED · v1.4 3C MASTER

## Naya kya hai (owner: "deep research, losses kyu, risk badhao, UI clean, logo change, candlestick chart")

### 🔬 DEEP RESEARCH — losses ka asli sabab (92 din ka real Binance data, 6 symbols, 158k candles)
Python backtest engine banaya jo bilkul engine ke rules par chala (fee-aware 0.05%/side, cooldown, BE/TP sab same):

| Config | Trades | Win Rate | PF | avgR | MaxDD |
|---|---|---|---|---|---|
| PURANE RULES (baseline) | 1336 | 16.3% | **0.07** | −5.22R | −6982R |
| **PRO FILTER PACK (naya)** | 268 | 17.9% | **0.83** | −0.11R | **−40R** |

**3 asli sabab mile:**
1. **FEE BOMB** — jab 3-candle zone chhota hota hai (SL distance 0.02%), to 0.1% round-trip fees = **20R ka nuqsan ek trade par!** Isi liye losses ka pahaad tha.
2. **TREND KE KHILAF** — EMA200 ke neeche BUY aur upar SELL lagata tha.
3. **DEAD CHOP** — bina volatility ke market mein fake breakouts.

### 🎯 PRO FILTER PACK (default ON, Settings se adjustable)
- **Min zone 0.25%** — fee bomb fix
- **EMA200 trend filter** — trend ke saath hi trade
- **ATR floor 0.08%** — dead chop band
- **Volume 1.2×** — weak participation band

### 📈 RISK INCREASE (owner request)
- Default risk **1% → 2%** per trade; range ab **0.1%–20%** (Settings se)

### 🧪 STRATEGY GENERATION CHECK
- Backtest ab **verdict** deta hai: STRONG (PF≥1.15, 30+ trades) / OK / WEAK
- WEAK strategy LIVE approve karo to **warning** message

### 🎨 UI — naya premium clean design
- 10 messy tabs → **5 clean tabs**: Home · Trades · Lab · Insights · Settings
- Premium dark theme (emerald/gold palette), better cards, chips navigation
- Insights tab: Indicators + News + Instruments + Logs ek jagah (chips)
- Settings tab: General + Broker + Control (admin) ek jagah

### 🕯 CANDLESTICK CHART (owner request)
- Home par **real-time M5 candlestick chart** — canvas-based, dependency-free
- Symbol chips: BTC ETH SOL BNB XRP DOGE · last price line + % change · har 15s refresh

### 🖼 NAYA LOGO (owner request)
- App icon: 3 ascending candles + gold trend arrow on premium dark
- Sab densities (48–192px) + dashboard header + login screen

## 3C MASTER rules — UNCHANGED
C1+C2 body ≥ 70% · C3 protected close · 5-candle window · SL opposite extreme ·
BE @ +1R · TP @ +3R · intrabar stop-order entry (v1.5 — backtest mein ye close-confirm se behtar nikla: PF 0.83 vs 0.71)

## Technical notes
- Walk3C ab per-call indicators precompute karta hai (EMA200/ATR14/VolSMA20, O(n) single pass)
- `/api/candles?symbol=&n=` endpoint chart ke liye
- Settings: risk_pct 0.1–20 · threec_rd_min_pct · threec_ema_filter · threec_atr_floor_pct · threec_vol_filter
- Same signature — seedha update
