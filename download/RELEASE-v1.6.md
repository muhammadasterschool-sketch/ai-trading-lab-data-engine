# AI Trading Lab — v1.6 (versionCode 23)

## Headline: LIVE MONEY — Real-time floating P/L (owner request)

Owner: "real time money show ho ke kitna plus mai abhi trades ja rahi hai ya phir loss,
taake zyada loss avoid kar pao."

## Kya add hua

1. **Har OPEN trade par live P/L** (Trades tab):
   - `abhi <price>` — current market price (engine 10s refresh; live candle included)
   - Unrealized P/L $ mein — GREEN (plus) / RED (minus)
   - **R multiple** (3C trades) — trade kitne R par chal rahi hai (+1.5R = breakeven ke baad aadha R profit)
2. **LIVE P/L banner** — sab open trades ka combined unrealized plus/minus, green/red
3. **Home tab** — "Open Positions" card ab live floating P/L dikhata hai (15s auto-refresh)
4. **Trades tab 5s auto-refresh** — tab khula rahe to P/L khud update hota rahega

## P/L math (honest)

- pnlLive = (BUY: abhi − entry | SELL: entry − abhi) × qty — live candle close par
- Yehi formula close par realized pnl banta hai — paper fills ke beech sirf price movement
  ka farq hota hai (spread/fee model abhi nahi — v1.5 roadmap item #1)
- R multiple 3C trades ke liye: rDist = |TP − entry| / 3 (TP kabhi move nahi hota, isliye
  original 1R hamesha calculate ho sakta hai — BE move ke baad bhi)

## Guards unchanged

- Manual CLOSE button har open trade par (loss dekhte hi band kar sakte hain)
- SL ab bhi live candle par track hota hai — app band ho to bhi SL hit hone par trade close
- versionCode 22 → 23, versionName "1.6"; same keystore (in-place install)
