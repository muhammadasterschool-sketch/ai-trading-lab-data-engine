# AI Trading Lab — v3.0 "QUANT PRO" (versionCode 29)

**Release date:** 29 October 2026
**Build:** 29 / versionName 3.0 · signed with original keystore (SHA-1 0440b7f9…, CN=AI Trading Lab) — purane install par seedha update ho jata hai, data nahi jata.

---

## Kya hai ye release?

Professional research se bana **5-upgrade mega release** — poora roadmap (v2.2 PRO RISK → v3.0 LIVE READY) aik hi version mein. Study base: NautilusTrader, freqtrade (+FreqAI+FreqUI), Jesse, hummingbot, QuantConnect LEAN, Microsoft Qlib, FinRL, TradingAgents, ai-hedge-fund, OpenBB Workspace, seasonality.ai. **3C MASTER strategy rules UNTOUCHED** — ye sab strategy ke aas paas ki professional discipline hai.

---

## P1 — PRO RISK (engine safety)

1. **Portfolio HEAT cap** — total open risk (entry→SL) ÷ equity ka cap. Default OFF (UNLIMITED — owner rule). Home par live heat gauge + METAL/ENERGY/AGRI bucket exposure.
2. **Bucket caps** — correlated group limit (USOIL+UKOIL+NGAS = ek hi macro bet). LEAN sector-exposure pattern.
3. **Slippage/spread model** — default 2 bps per side: entry thoda zyada par, exit thoda kam par. NautilusTrader fill-model parity. Settings me 0–50 bps.
4. **SAFE MODE** — feed outage (candle >10 min stale) par naye entries band + SL/TP freeze (stale prices par false trigger nahi) + owner notification. Auto-resume.
5. **Feed backoff + retry** — Yahoo fail par exponential backoff 60s→15min + cross-fallback retry. Request storm khatam.
6. **TRUE Drawdown** — `accounts.peak` ab har loop equity-highs par ratchet hota hai (balance + floating). Dashboard ka Drawdown ab real HWM drawdown hai.
7. **Session-gap fix** — 3C breakout window ab candle INDEX-based hai (time-diff nahi) — CME maintenance breaks/weekends par mis-count khatam.
8. **Persistent guards** — cooldowns ab DB me save hote hain; watchdog restart par restore (pehle wipe ho jate the).

## P2 — HONEST LAB (Strategy Lab backtest rewrite)

- **Deep data**: 1000 bars (~3.5 din) → ~1 mahina 5m candles (bridge ho to 8000 bars), DB me upsert nahi (in-memory).
- **Fees included** — pehle Lab P&L me fees ZERO thi (jhoota optimism), ab 0.05%/side.
- **Walk-forward**: IS 70% / OOS 30% split — verdict ke liye dono segments ki PF chahiye.
- **Full metrics**: expectancy, avgR, Sharpe, Sortino, Calmar, avg duration, SL/TP/TIME exit breakdown, fee drag.
- **Monte Carlo** (Jesse pattern): 1000x trade-shuffle → DD percentiles (p5/p50/p95) + side-flip bootstrap **p-value** → verdict tag **EDGE / MARGINAL / NOISE**. Ab STRONG = IS PF≥1.15 + OOS PF≥1.0 + n≥30 + NOT-NOISE.
- **EMA200 warmup fix** — ab SMA-200 seed (pehle first-close seed se level galat banta tha), filter index≥200 par.
- **24h time stop** — 288 bars (Jesse parity).

## P3 — EDGE ANALYTICS (UI — FreqUI + Jesse + prop-dashboards)

- **Home chart**: khuli trade ke **ENTRY/SL/TP dashed lines** chart par (FreqUI visuals).
- **Portfolio Heat + Bucket Exposure card** (LEAN-style) Home par.
- **Insights > 📊 Edge Analytics**: Daily P&L bar chart (30d), Monthly Returns Heatmap (Jesse), R-multiple distribution histogram, per-symbol performance table (n/WR/net/PF/avgR), costs honesty card (total fees + avg TCA slippage bps).
- **Insights > 🗓 Seasonality**: 5y monthly seasonal heatmap per commodity (seasonality.ai pattern) — coffee frost, heating season, harvest cycles ka edge.
- **Trades**: har trade par COUNCIL % + ML winProb pill, closed par R-multiple + TCA bps.
- **Drawdown card ab TRUE HWM** (peak-ratcheted).

## P4 — AI QUANT CORE

- **Signal Council** (TradingAgents pattern): har 3C entry par 4 analysts score dete hain — Technical (EMA200 trend + RSI), Volatility regime (ATR), News bias (24h RSS), **Seasonality** (month bias). Score 0-100 trade par tag hota hai. Optional min-gate (default tag-only — kuch block nahi).
- **ML-lite** (FreqAI-inspired): har 20 closed trades par logistic regression retrain (pure Java SGD) — setup DNA features (body%, vol ratio, ATR%, EMA dist, hour, council) se win probability. Drift check. Experimental, honesty-first.
- **Event gate** (FinRL turbulence pattern): OPEC/CPI/FOMC HIGH-impact news ke 60 min tak naye entries pause — opt-in.
- **Degradation monitor**: har 30 min har strategy ki rolling 20-trade PF — PF<0.7 par owner alert (notification + status bar). AI strategies opt-in auto-pause. 3C MASTER sirf alert (kabhi auto-pause nahi).
- **Lab feedback loop**: auto-evolve ab rolling PF data prompt me daalta hai — AI kamzori dekh kar nayi strategy propose karta hai.

## P5 — LIVE READY

- **Order lifecycle**: naya `orders` table — har paper/bridge order ka audit trail (STOP/MARKET, PAPER/BRIDGE source, FILLED/SENT/REJECTED).
- **TCA**: har close par decision-vs-fill slippage (bps) record hoti hai — analytics me aggregate.
- **MT5 Bridge v2.0** (`mt5-bridge.py`): naye endpoints **POST /order, /close, GET /positions** — app ka **BRIDGE LIVE MIRROR** (Settings, owner-only, default OFF, confirm dialog) paper trade ke saath real MT5 orders mirror karta hai. DEMO account par pehle test karein!
- **Audit export**: Insights > Edge Analytics se `/api/audit.csv` — trades + orders full export.

---

## Owner gates unchanged

- Registration approval + per-user TRADING gate (v2.1) barkarar.
- Daily P/L UNLIMITED — kill switch, heat cap, event gate sab **default OFF** (opt-in).
- Halal universe (27 commodities) wahi.

## Settings > 🧠 QUANT PRO (naya section)

Slippage bps · Heat cap % · Bucket cap % · Council min % · Event gate ON/OFF · CME session filter ON/OFF · Auto-pause ON/OFF · Bridge live toggle + lots · Feed interval.

## Upgrade notes

- DB v6→v7: trades par naye journal columns (r_mult, mfe, mae, risk_amt, decision, tca_bps, council, win_prob, features) + orders table — purana data untouched.
- Purani trades par r_mult/tca 0 hongi — nayi trades se bharange.
- ML ko training ke liye ~40 feature-tagged closed trades chahiye (khud ban jayenge).
- Bridge live mirror ke liye PC par naya `mt5-bridge.py v2.0` chahiye (purana v1.0 candles-only hai).

**Downloads:** `AI-Trading-Lab-v3.0-Android.apk` (230 KB) · source zip · ye RELEASE.md
**Paper trading only** — jo bhi bridge mirror use kare, pehle demo par. Allah Hafiz!
