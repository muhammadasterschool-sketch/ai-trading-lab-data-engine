# AI TRADING LAB — DATA ENGINE · PROFESSIONAL UPGRADE ROADMAP (v2.2 → v3.0)
Research base: NautilusTrader, freqtrade (+FreqAI+FreqUI), Jesse, hummingbot, QuantConnect LEAN,
Microsoft Qlib, FinRL, TradingAgents (Tauric), virattt/ai-hedge-fund, OpenBB Workspace, seasonality.ai
Audit base: full code audit of EngineCore/StrategyLab/Api/Db + web engine (see worklog Task 29).

## HARD CONSTRAINTS (owner, never violated)
- 3C MASTER rules: UNTOUCHED forever. All upgrades are around the strategy, not inside it.
- Daily P/L UNLIMITED — any kill/limit switch ships default OFF, owner opt-in only.
- Owner gates (register approval + trading approval) unchanged. Halal-only universe unchanged.
- Reply language: Roman Urdu.

## PHASE 1 — v2.2 "PRO RISK" (engine safety — P0 audit items)
Source patterns: LEAN RiskManager models, hummingbot kill switch, freqtrade protections, Nautilus fill models.
1. PORTFOLIO HEAT CAP: total open risk % limit (sum of qty*(entry-sl) per uid / equity); settings heat_max_pct.
   BUCKET CAPS: Energy/Metals/Agri per-bucket open-risk caps (LEAN MaximumSectorExposure pattern) —
   USOIL/UKOIL/NGAS are correlated; 27 syms x 2% = 54% simultaneous risk today.
2. SLIPPAGE/SPREAD MODEL: port web backtest.ts cost model to EngineCore closeTrade/openTrade fills:
   per-symbol spread bps + slippage bps (settings, default realistic for futures e.g. 2-5 bps majors,
   higher for LUMBER/RICE/ORANGEJ thin markets). Fees already exist (0.05%/side).
3. STALE-DATA GUARD: max candle age (2x TF) before ANY entry/SL/TP action; feed older → SAFE MODE:
   block new entries, keep managing, notify owner (Notifier + log + Home banner). Fixes frozen-SL risk.
4. FEED RESILIENCE: Yahoo 429/retry with exponential backoff + jitter; bridge /health poll + status row;
   last error surfaced on dashboard feed card.
5. TRUE DRAWDOWN: accounts.peak ratchets on new equity highs; DD = (peak-equity)/peak displayed;
   optional (default OFF) DD-based pause — owner opt-in.
6. SESSION CALENDAR: CME/CBOT maintenance break (17:00-18:00 ET) + weekend/holiday handling;
   window arithmetic uses bar count (index-based), not raw time diff — fixes setup-window miscounts.
7. PERSISTENT GUARDS: cooldownUntil + consecLoss counters + dedup sets → DB (settings/trades rows);
   survive watchdog revive (ServerService recreates EngineCore today and wipes them).
8. BUG FIXES: rDist=|tp-entry|/THREEC_TP_R kept but guarded (assert TP==3R or store 1R at open);
   live-trigger invalidation symmetry check; HttpServer socket read timeouts; day rollover on wake.

## PHASE 2 — v2.3 "HONEST LAB" (research discipline)
Source patterns: freqtrade walk-forward/hyperopt hygiene, Jesse Monte Carlo + bootstrap, LEAN reality models.
1. DEEPER DATA: Lab backtest window 1000 bars (~3.5d) → up to 60d 5m (Yahoo range=60d or bridge history);
   fees INCLUDED in Lab P&L (currently missing); next-bar-open fill option (parity with web engine).
2. WALK-FORWARD: IS 70% / OOS 30% split mandatory; 5-fold rolling WFO; verdict requires OOS PF>=1.0
   AND IS PF (freqtrade overfitting hygiene). STRONG gate: PF>=1.15 & n>=30 & OOS-positive.
3. METRICS SUITE: + expectancy (R), avgR, Sharpe, Sortino, Calmar, avg duration, exit-reason breakdown
   (SL/TP/BE/time), fee drag %. Jesse-standard results panel.
4. MONTE CARLO (Jesse pattern): trade-order shuffle x1000 → 5th/50th/95th percentile equity paths;
   rule-significance bootstrap (shuffle entry side) → verdict tag: EDGE / MARGINAL / NOISE.
5. EMA200 warmup fix (seed = SMA of first 200 closes or require >=200 bars before filter active).
6. DEGRADATION MONITOR: rolling 20-trade PF + expectancy per ACTIVE strategy; breach → owner alert
   "STRATEGY DEGRADED — <name> rolling PF 0.6" + optional auto-pause (owner toggle).
7. TRADE JOURNAL COLUMNS: R-multiple, MFE, MAE per closed trade (professional journal standard).

## PHASE 3 — v2.4 "EDGE ANALYTICS" (UI extraction — FreqUI + Jesse + prop dashboards)
1. Home chart (FreqUI visuals): entry/SL/TP lines drawn per open trade + entry/exit markers on candles.
2. Daily P&L bar chart (FreqUI Profit page): last 30 days, green/red bars, tap a day → that day's trades.
3. Per-symbol performance table (FreqUI Performance): n trades, winrate, net, avgR, avg duration, PF.
4. Equity curve with HWM line + underwater DD shading (Jesse); monthly returns heatmap (Jesse).
5. R-multiple distribution histogram; exposure-by-bucket pie (Energy/Metals/Agri — LEAN style).
6. Seasonality card (seasonality.ai pattern, perfect for halal commodities): avg % by month per symbol
   heatmap (needs >=2y daily data — fetch weekly range from Yahoo/bridge), seasonal strength tag.
7. Prop-style risk strip: daily loss limit line + "risk remaining" gauge on Home (default UNLIMITED label).

## PHASE 4 — v2.5 "AI QUANT CORE" (Qlib/FreqAI/TradingAgents patterns)
1. SIGNAL COUNCIL (TradingAgents-lite, does NOT touch 3C rules): 4 lightweight analysts score every
   armed setup — Technical (multi-TF trend+momentum), Seasonality (month bias), News (existing RSS
   sentiment), Volatility regime (ATR percentile). Output: confidence 0-100 tag on entry + optional
   min-confidence gate (owner toggle, default OFF).
2. ADAPTIVE ML (FreqAI-lite): rolling retrain of GBM/logistic on candle features (Qlib Alpha158-lite
   subset) predicting 3C setup success; DI-style drift check; prediction stored per trade for analysis.
3. EVENT GATE (FinRL turbulence concept): high-impact keyword/OPEC-CPI-FOMC window → pause NEW entries
   N minutes (owner toggle, default OFF) — stop orders currently rest 24/7 through gap events.
4. LAB v2 FEEDBACK LOOP: auto-evolve LLM prompt now receives walk-forward + degradation stats so new
   strategies are proposed against live weaknesses (Qlib research-loop pattern).

## PHASE 5 — v3.0 "LIVE READY"
1. ORDER LIFECYCLE: PENDING/WORKING/PARTIAL/FILLED/REJECTED + order ids + fill history (Nautilus parity).
2. MT5 BRIDGE ORDER ROUTING: bridge /order endpoints; per-user paper→real switch (owner-only, halal check).
3. TCA on Android (decision vs fill, web /api/paper/tca parity).
4. CLOUD 24/7: engine offload option to bridge PC / mini-server (phone stays dashboard).
5. AUDIT: full audit-trail export, strategy report cards, benchmark comparison (buy&hold per symbol).

## SEQUENCING
v2.2 (1 session) → v2.3 (1 session) → v2.4 (1-2) → v2.5 (2) → v3.0 (when owner ready for real money).
Each release: versionCode+1, build+sign, triple deploy, downloads.html, RELEASE.md, git push, worklog.
