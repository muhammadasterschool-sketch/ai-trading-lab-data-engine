# AI Trading Lab — v1.5 (versionCode 22)

## Headline: 3C MASTER + SPEED (owner request: "1 trade per sec")

Owner ne kaha: "Ye aik hi baar mai aik trade khol raha hai — isko 1 trade per sec karni chahiye."
Diagnosis: 2 bottlenecks the — (1) 30s scan loop, (2) entry sirf candle CLOSE hone par
(breakout candle ke close ka intezaar = 5 minute tak late).

## Kya badla (3 upgrades)

1. **10s scan loop** (pehle 30s) — setup fire hone ke baad entry ~10 second ke andar
   (pehle 30 second tak wait hota tha).
2. **LIVE candle stop-order trigger** — sab se bada upgrade. Chalti hui (in-progress) M5
   candle jab setup ka trigger price (zone extreme + buffer) cross karti hai, entry FORAN
   hoti hai — candle close ka intezaar nahi. Bilkul real trader ke stop order jaisa:
   BUY trigger cross = instant fill (gap-open par open price par fill). Pehle ye entry
   candle close tak late hoti thi — breakout ke baad 1-5 minute ka nuksan.
3. **LIVE SL/TP/breakeven tracking** — open trades ab closed + live dono candles par
   check hote hain: SL/TP hit aur +1R breakeven move ab seconds mein react karta hai
   (pehle agle closed candle ka intezaar).

## Jo NAHI badla (3C rules intact — MASTER PROMPT verbatim)

- C1+C2 body ≥ 70%, C3 protected close, 5-candle breakout window (live candle bhi window
  ke andar hi trigger kar sakti hai — window khatam = SETUP_EXPIRED, live trigger band).
- Close-based invalidation: closed candle par hi check hoti hai (close final hota hai);
  live candle par close ka intezaar — wick kabhi cancel nahi karta.
- Ek hi candle mein breakout + close-beyond (closed candle) = ambiguous = untraded dead.
- SL = opposite extreme ± buffer · 1R = |entry−SL| · TP = +3R · BE @ +1R · no partial TP.
- 1 open position per symbol (professional guard) — lekin ALAG symbols par unlimited
  positions; jitne symbols par ek saath setup fire ho utne trades back-to-back foran.
- Daily P/L UNLIMITED · no kill switch · risk_pct owner setting (default 1%).

## Speed math (honest)

- "1 trade per sec" ka matlab: jab setups fire hon to execution instantly, bina kisi
  artificial delay ke. Trades sirf valid 3C setups par khulte hain — ye discipline hi
  strategy hai. Speed ab: breakout → ~10s ke andar entry (pehle 30s-5min).
- API weight: 30 symbols × weight 2 × 6 scans/min = 360/min (Binance limit 1200+ — safe).

## Technical notes

- Live trigger gap-open handling: fill = max(trigger, open) for BUY, min(trigger, open)
  for SELL — stop-order semantics.
- manageOpenTrades: closed candle pehle, live candle baad; SL-first conservative order;
  BE move ke baad local `sl` update (double BE move guard).
- versionCode 21 → 22, versionName "1.5"; health 1.5.0; badge v1.5.
- Signed with ORIGINAL keystore (SHA-1 0440b7f9...) — v1.4 ke upar seedha install.
- No migration: v1.4 trades/settings as-is; sirf speed behavior change.
