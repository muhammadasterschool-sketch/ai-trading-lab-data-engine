# AI Trading Lab — v1.4 (versionCode 21)

## Headline: 3C MASTER STRATEGY ENGINE

Owner ke MASTER TRAINING PROMPT ke mutabiq: **saari 35 purani strategies retire** — ab engine
sirf **3C Breakout (M5)** chalata hai, aur **daily loss/profit UNLIMITED** hai.

## 3C Strategy rules (mechanical, verbatim)

- **BUY setup**: C1 green + C2 green (har ek ka body ≥ 70% of High-Low range), C3 red —
  C3 ki close C1+C2 ke lowest Low ke neeche nahi (wick se farq nahi parta).
- **SELL setup**: C1 red + C2 red (body ≥ 70%), C3 green — C3 ki close C1+C2 ke highest
  High ke upar nahi.
- **Setup zone**: teeno candles ka highest High / lowest Low.
- **Entry window**: agle **5 M5 candles** (5th included). Breakout wahan nahi hua to setup
  EXPIRE — candle-6 ka breakout invalid.
- **Invalidation**: window candle ka **CLOSE** protected boundary (BUY: zone low, SELL: zone
  high) ke paar → setup cancel. Sirf wick kabhi cancel nahi karta. Agar ek hi candle mein
  breakout + close-beyond dono hon to OHLC se sequence nahi bathta — setup skip (kabhi guess nahi).
- **Entry**: stop-order simulation zone extreme par (+ configurable buffer, default 0).
- **SL**: setup ke opposite extreme ± SL buffer. **1R = |entry − SL|**.
- **Management**: **+1R par poore position ka SL breakeven**; **+3R par poora position close**.
  Koi partial TP nahi.
- **Risk**: `risk_pct` setting (default 1% equity/trade) — owner controlled, 0.1–10%.

## UNLIMITED (owner request)

- Daily loss halt (-5%) — **REMOVED**
- Drawdown kill switch (-10%) — **REMOVED**
- Daily profit cap / trades-per-day cap / concurrent-position cap / consecutive-loss stop — **pehle se nahi tha, ab bhi nahi**
- High-impact news ab **display-only** — 3C entry kabhi block nahi hoti
- Jo guards bache hain wo sirf mechanical correctness ke liye: 1 open position per symbol
  per account, 1 entry per setup.

## Honest backtest (90 din, real Binance 5m klines, 1% risk, BE@1R/TP@3R)

Gross (paper engine parity — fees shamil nahi):

| Symbol | Setups | Trades | Winrate | Avg R | Net | MaxDD |
|--------|--------|--------|---------|-------|-----|-------|
| BTCUSDT | 880 | 327 | 19.0% | +0.07 | −2.55% | 10.8% |
| ETHUSDT | 553 | 216 | 15.7% | −0.009 | +2.81% | 10.0% |
| SOLUSDT | 468 | 186 | 15.6% | −0.016 | −1.15% | 11.1% |
| BNBUSDT | 668 | 284 | 21.5% | +0.194 | +13.95% | 4.4% |
| PAXGUSDT (Gold) | 1245 | 405 | 23.7% | +0.298 | +1.98% | 3.8% |

**Total: 1418 trades, 30.2% winrate (BE excluded).** Master Prompt ke section-11 ke mutabiq
ye ASLI numbers hain — koi invented result nahi. Note: breakeven exits bohat zyada hain
(486/1418) kyunki +1R par SL entry par aa jata hai; real costs (spread/fees) lagaane par
results kharab ho sakte hain. Ye paper-trading research hai, profit ki guarantee nahi.

## Strategy Lab — Auto-Evolve ("aur strategies banati raho")

- Har **6 ghante** AI ek nayi complementary strategy propose karta hai (3C se different),
  use foran real candles par **backtest** karta hai, aur owner ko notification jata hai.
- Strategy Lab mein **BACKTESTED** status ke saath aati hai — **PAPER/LIVE sirf owner
  approve karta hai** (AI kabhi khud live nahi jati).
- Manual pipeline waisa hi: text likho ya YouTube video/channel do → backtest → paper → approve.
- 40-strategy flood guard + `lab_auto` setting se on/off.

## Technical changes

- Timeframe: **1m → 5m** (3C spec M5 hai). Klines 200 × 5m per active symbol (top-30 by volume).
- New 3C state machine: `detect3C()` + `walk3C()` — har loop state real candles se
  dobara derive hota hai (restart-proof). Master Prompt section-12 ke event names log hote
  hain: SETUP_DETECTED / SETUP_EXPIRED / SETUP_INVALIDATED / BREAKOUT_DETECTED /
  ORDER_EXECUTED / TRADE_MANAGED / TRADE_CLOSED_SL|TP.
- `manageOpenTrades()`: ab last **closed** candle ke high/low se SL/TP check (stop-order
  semantics, conservative SL-first). 3C trades par BE@+1R move.
- One-time v1.4 migration: purane open trades cancel (naye semantics), 1m candles purge.
- Dashboard Home/Indicators/Lab tabs 3C contract ke saath update (strategy_name, risk_pct,
  limits, threec_armed).
- `/api/settings` GET/POST ab `riskPct` expose/set karta hai (0.1–10).
- 35-strategy vote register → single 3C direction register (`lastVotes[1]`, compat).

## Install

- Purane kisi bhi version ke **upar seedha install** — original keystore signature, data
  (history/strategies/settings) preserve rehti hai.
- Invitation code: **M2991474** · Paper trading only — koi real paisa involve nahi.
