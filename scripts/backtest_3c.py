#!/usr/bin/env python3
"""
3C MASTER — deep loss diagnosis + filter research (v1.8 "CLEAN & PRO")
Exact port of EngineCore.java walk3C/detect3C/manageOpenTrades semantics:
- C1/C2 body >= 70% (|c-o|/(h-l)), C3 opposite + protected close
- BUY: C1 g, C2 g, C3 r, c3.c >= min(c1.l, c2.l); trigger=zoneHigh; SL=zoneLow
- Window 5 candles; close-beyond-boundary invalidates; same-candle break+invalid = skip
- Fill = max(trigger, open) BUY; TP = entry + 3R; BE at +1R (SL->entry, whole pos)
- Conservative same-candle: SL first, TP second
- v1.5 live intrabar trigger == same fill math on the breakout candle
- v1.7 guards: one position/symbol, 15-min cooldown after SL loss, fee 0.05%/side
"""
import urllib.request, json, time, sys

SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
FEE = 0.0005  # per side
TF = 5 * 60 * 1000

def fetch(sym, total=5000):
    out, end = [], None
    while len(out) < total:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=5m&limit=1000"
        if end:
            url += f"&endTime={end}"
        for attempt in range(5):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                if attempt == 4:
                    raise
                time.sleep(12 if "418" in str(e) else 2)
        if not data:
            break
        out = data + out
        end = data[0][0] - 1
        time.sleep(0.15)
    return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in out[-total:]]

def ema(vals, n):
    out, k = [], 2.0 / (n + 1)
    e = vals[0]
    for i, v in enumerate(vals):
        e = v * k + e * (1 - k) if i else v
        out.append(e)
    return out

def atr(k, n=14):
    out, prev = [], None
    trs = []
    for i, c in enumerate(k):
        tr = c[2] - c[3] if prev is None else max(c[2] - c[3], abs(c[2] - prev[4]), abs(c[3] - prev[4]))
        trs.append(tr)
        window = trs[-n:]
        out.append(sum(window) / len(window))
        prev = c
    return out

def body(c):
    rng = c[2] - c[3]
    return abs(c[4] - c[1]) / rng if rng > 0 else 0.0

def detect(k, i):
    c1, c2, c3 = k[i - 2], k[i - 1], k[i]
    if body(c1) < 0.70 or body(c2) < 0.70:
        return None
    zh = max(c1[2], c2[2], c3[2])
    zl = min(c1[3], c2[3], c3[3])
    g1, g2, g3 = c1[4] > c1[1], c2[4] > c2[1], c3[4] > c3[1]
    if g1 and g2 and not g3 and c3[4] >= min(c1[3], c2[3]):
        return {"side": "BUY", "c3ts": c3[0], "zh": zh, "zl": zl, "trig": zh, "sl": zl}
    if (not g1) and (not g2) and g3 and c3[4] <= max(c1[2], c2[2]):
        return {"side": "SELL", "c3ts": c3[0], "zh": zh, "zl": zl, "trig": zl, "sl": zh}
    return None

def backtest(k, ema_f=None, vol_f=False, atr_floor=0.0, tp_r=3.0, cooldown_min=15):
    """ema_f: list of EMA200 values (or None). vol_f: volume>1.2*SMA20 on breakout candle.
    atr_floor: min ATR%/price at setup. Returns trade list."""
    e200 = ema([c[4] for c in k], 200)
    a14 = atr(k)
    vsma = [sum(c[5] for c in k[max(0, i - 19):i + 1]) / len(k[max(0, i - 19):i + 1]) for i in range(len(k))]
    trades, pending, in_pos = [], None, False
    cool_until = 0
    for i in range(2, len(k)):
        c = k[i]
        ts = c[0]
        if pending is not None:
            win = int((ts - pending["c3ts"]) / TF)
            if win > 5:
                pending = None
            else:
                buy = pending["side"] == "BUY"
                boundary = pending["zl"] if buy else pending["zh"]
                invalid = c[4] < boundary if buy else c[4] > boundary
                broke = c[2] > pending["trig"] if buy else c[3] < pending["trig"]
                if broke and invalid:
                    pending = None
                elif invalid:
                    pending = None
                elif broke and not in_pos and ts >= cool_until:
                    ok = True
                    if ema_f is not None:
                        ok = c[4] > ema_f[i] if buy else c[4] < ema_f[i]
                    if ok and vol_f:
                        ok = c[5] > 1.2 * vsma[i]
                    if ok and atr_floor > 0:
                        ok = (a14[i] / c[4]) * 100 >= atr_floor
                    if not ok:
                        pending = None  # filter rejected -> setup consumed (engine behavior)
                    else:
                        fill = max(pending["trig"], c[1]) if buy else min(pending["trig"], c[1])
                        rd = fill - pending["sl"] if buy else pending["sl"] - fill
                        if rd > 0:
                            tp = fill + tp_r * rd if buy else fill - tp_r * rd
                            t = {"fill": fill, "sl": pending["sl"], "tp": tp, "buy": buy,
                                 "exit": None, "why": None, "ts": ts + TF, "r": 0.0,
                                 "be_ts": 0}
                            trades.append(t)
                            in_pos = True
                            step_trade(t, c, tp_r)  # breakout candle itself can close it (engine: live candle checked)
                            if t["why"] is not None:
                                in_pos = False
                                if t["why"] == "SL":
                                    cool_until = t["ts"] + cooldown_min * 60000
                        pending = None
        if pending is None and not in_pos:
            s = detect(k, i)
            if s:
                pending = s
        # manage open trade on this candle (closed-candle walk sim; entry candle handled above)
        if in_pos:
            t = trades[-1]
            step_trade(t, c, tp_r)
            if t["why"] is not None:
                in_pos = False
                if t["why"] == "SL":
                    cool_until = t["ts"] + cooldown_min * 60000
    return [t for t in trades if t["why"] is not None]

def step_trade(t, c, tp_r):
    buy, fill, sl, tp = t["buy"], t["fill"], t["sl"], t["tp"]
    rdist = abs(tp - fill) / tp_r
    hit_sl = (not buy and c[2] >= sl) or (buy and c[3] <= sl)
    hit_tp = (not buy and c[3] <= tp) or (buy and c[2] >= tp)
    if hit_sl or hit_tp:
        px = sl if hit_sl else tp
        gross = (px - fill) * (1 if buy else -1)
        t["exit"], t["why"] = px, "SL" if hit_sl else "TP"
        t["r"] = gross / rdist - (fill * FEE * 2) / rdist
        return
    be_hit = (buy and c[2] >= fill + rdist) or (not buy and c[3] <= fill - rdist)
    if be_hit and t["sl"] != fill:
        t["sl"] = fill       # BE move (whole position)
        t["be_ts"] = c[0]    # engine: BE close only on LATER candles
        return
    if t["sl"] == fill and t["be_ts"] and c[0] > t["be_ts"]:
        hit_be = (buy and c[3] <= fill) or (not buy and c[2] >= fill)
        if hit_be:
            t["exit"], t["why"] = fill, "BE"
            t["r"] = -(fill * FEE * 2) / rdist

def stats(trs, label):
    n = len(trs)
    if n == 0:
        print(f"{label:34s}  trades=0")
        return
    wins = [t for t in trs if t["r"] > 0]
    losses = [t for t in trs if t["r"] <= 0]
    gw = sum(t["r"] for t in wins)
    gl = abs(sum(t["r"] for t in losses))
    pf = gw / gl if gl > 0 else float("inf")
    tot = sum(t["r"] for t in trs)
    wr = 100.0 * len(wins) / n
    eq, peak, dd = 0.0, 0.0, 0.0
    for t in trs:
        eq += t["r"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    consl, cur = 0, 0
    for t in trs:
        cur = cur + 1 if t["r"] <= 0 else 0
        consl = max(consl, cur)
    print(f"{label:34s}  n={n:4d}  wr={wr:5.1f}%  PF={pf:5.2f}  netR={tot:+8.1f}  avgR={tot/n:+5.2f}  maxDD={dd:7.1f}R  consecL={consl}")

def main():
    allk = {}
    for s in SYMS:
        try:
            allk[s] = fetch(s)
            print(f"fetched {s}: {len(allk[s])} candles ({len(allk[s])*5/60/24:.1f} days)", flush=True)
        except Exception as e:
            print(f"FETCH FAIL {s}: {e}", file=sys.stderr)
    variants = [
        ("BASELINE (current live rules)", dict()),
        ("+EMA200 trend filter", dict(ema_f=True)),
        ("+Volume 1.2x filter", dict(vol_f=True)),
        ("+ATR floor 0.08%", dict(atr_floor=0.08)),
        ("+ATR floor 0.12%", dict(atr_floor=0.12)),
        ("EMA200+Volume", dict(ema_f=True, vol_f=True)),
        ("EMA200+ATR0.08", dict(ema_f=True, atr_floor=0.08)),
        ("EMA200+Volume+ATR0.08", dict(ema_f=True, vol_f=True, atr_floor=0.08)),
        ("EMA200+Volume+ATR0.12", dict(ema_f=True, vol_f=True, atr_floor=0.12)),
    ]
    print("\n=== PER SYMBOL: baseline ===")
    for s, k in allk.items():
        e200 = ema([c[4] for c in k], 200)
        stats(backtest(k), f"{s} baseline")
    print("\n=== COMBINED (all symbols merged) ===")
    for label, kw in variants:
        merged = []
        for s, k in allk.items():
            kw2 = dict(kw)
            if kw2.pop("ema_f", False):
                kw2["ema_f"] = ema([c[4] for c in k], 200)
            merged += backtest(k, **kw2)
        merged.sort(key=lambda t: t["ts"])
        stats(merged, label)

if __name__ == "__main__":
    main()
