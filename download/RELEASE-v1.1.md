# AI Trading Lab v1.1 TUNED — X7 REGIME FADE + TURBO (versionCode 2)

**PAPER ONLY simulator** — koi real order kahin nahi jata. Invite-only engine (code: aapke paas hai).

## Naya kya hai (v1.0 → v1.1)

### 1. X7 REGIME FADE — replay-tuned strategy (naya)
11 candidate configs real Binance 5m data (14-din windows, fees+slippage included) par replay-test kiye. Winner:
- **24h VWAP ± 3.5σ deviation fade + RSI confluence (RSI<30 BUY / >70 SELL) + ADX regime gate (ADX(56) < 22 — sirf ranging market)**
- SL = 1.0×ATR, TP = +2.5R, NO breakeven (tuned), 15-min cooldown after SL
- Replay results (1% risk baseline): PF 1.29–1.87, maxDD 1.7–2.7%, win 48–57%
- Purane window (7–28 din pehle) mein bhi test kiya — regime-dependent edge honest report mein note hai

### 2. TURBO — paper speed controls (Settings > TURBO)
- **Paper leverage cap** (lev_cap): 0.95 = spot (default) · 2/3/5/10 = TURBO presets (max 10x)
- **Paper fee** (fee_bps): 5 = Binance VIP 0.05% (default) · 0 = zero-fee sim
- **Risk %**: 0.1–20% per trade (pehle se tha)
- ⚠ PAPER ONLY — ye sirf simulated account ki speed badalte hain

### 3. PDF Pack default OFF (data-backed)
Replay mein PDF pack S1–S9 ne 5m par PF 0.38–0.60 diya (919 trades/7d, $52 fees loss on $100). Default OFF kiya — Settings mein ek toggle se ON kar sakte hain. 3C MASTER + 5M PLAYBOOK + SHAAKUNI + AI TRAINER sab pehle jaise hain.

### 4. Pro filter — NAHI hai (confirm)
v1.0/v1.1 mein PRO FILTER PACK MOJOOD NAHI (v4.4.1 mein aapke order par delete hua tha — trades block ho rahi thin). Sirf 3C core rules + fee-edge skip + SAFE MODE (data-stale guard) hain. Heat/bucket/event/council caps opt-in hain, default OFF.

## Login + Data Guarantee
- Invite code registration → owner approve → trade — poora flow host simulation mein test hua
- **Update par data as-it-is**: same keystore + additive schema — v1.0 ke upar seedha install karein, login/balances/trades/candles sab preserved

## Trajectory (honest expectations)
- Max TURBO replay (risk 20%, lev 10x, real fees): **+18.8% / 14 din** (+1.34%/day), best hour +13.4%, maxDD 16.7%
- $2,000/day absolute (from $100) = ~1500x growth — compounding path months leta hai; TURBO se speed badalti hai, guarantee kahin nahi
- $100→$200 in 1h (doubling) koi bhi strategy reliably nahi kar sakta — sim ka best hour +13% hai
- Ye PAPER simulator hai — results trading advice ya real-money return NAHI hain

## Install
1. Purana app kholna ho to pehle data ka screenshot (optional)
2. APK download → install (unknown sources allow) — v1.0 ke UPAR install hoga, data rahega
3. Login (invite code) → Settings > TURBO se speed set karein

## SHA256
`ec834735fdb75386…` (full: release asset ke saath .sha256 file)

## Tests
131/131 host-JVM guards pass — Shaakuni 18, V4.4 23, V4.4.1 15, V4.4.2 38, V1.0 27, **V1.1 X7+TURBO 10**
