import json, sys
sys.path.insert(0, "/home/z/my-project/scripts")
import backtest_3c as B
from backtest_3c import ema, stats

def backtest3(k, ema_f=None, vol_f=False, atr_floor=0.0, atr_ceil=0.0, tp_r=3.0,
              cooldown_min=15, rd_min=0.0, rd_max=0.0, c3_max_body=0.0, win_max=5, regime=False):
    e200 = ema([c[4] for c in k], 200)
    e50 = ema([c[4] for c in k], 50)
    a14 = B.atr(k)
    vsma = [sum(c[5] for c in k[max(0, i - 19):i + 1]) / len(k[max(0, i - 19):i + 1]) for i in range(len(k))]
    trades, pending, in_pos = [], None, False
    cool_until = 0
    for i in range(2, len(k)):
        c = k[i]
        ts = c[0]
        if pending is not None:
            win = int((ts - pending["c3ts"]) / B.TF)
            if win > win_max:
                pending = None
            else:
                buy = pending["side"] == "BUY"
                boundary = pending["zl"] if buy else pending["zh"]
                invalid = c[4] < boundary if buy else c[4] > boundary
                broke = c[2] > pending["trig"] if buy else c[3] < pending["trig"]
                if broke and invalid: pending = None
                elif invalid: pending = None
                elif broke and not in_pos and ts >= cool_until:
                    ok = True
                    if ema_f is not None: ok = c[4] > ema_f[i] if buy else c[4] < ema_f[i]
                    if ok and regime:
                        ok = e50[i] > e200[i] if buy else e50[i] < e200[i]
                    if ok and vol_f: ok = c[5] > 1.2 * vsma[i]
                    if ok and atr_floor > 0: ok = (a14[i] / c[4]) * 100 >= atr_floor
                    if ok and atr_ceil > 0: ok = (a14[i] / c[4]) * 100 <= atr_ceil
                    if not ok:
                        pending = None
                    else:
                        fill = max(pending["trig"], c[1]) if buy else min(pending["trig"], c[1])
                        rd = fill - pending["sl"] if buy else pending["sl"] - fill
                        zhpct = (pending["zh"] - pending["zl"]) / fill * 100
                        if rd > 0 and rd / fill * 100 >= rd_min and (rd_max == 0 or zhpct <= rd_max):
                            tp = fill + tp_r * rd if buy else fill - tp_r * rd
                            t = {"fill": fill, "sl": pending["sl"], "tp": tp, "buy": buy, "exit": None,
                                 "why": None, "ts": ts + B.TF, "r": 0.0, "be_ts": 0}
                            trades.append(t); in_pos = True
                            B.step_trade(t, c, tp_r)
                            if t["why"] is not None:
                                in_pos = False
                                if t["why"] == "SL": cool_until = t["ts"] + cooldown_min * 60000
                        pending = None
        if pending is None and not in_pos:
            s = B.detect(k, i)
            if s and c3_max_body > 0:
                c3 = k[i]
                cb = abs(c3[4] - c3[1]) / (c3[2] - c3[3]) if c3[2] - c3[3] > 0 else 0
                if cb > c3_max_body: s = None
            if s: pending = s
        if in_pos:
            t = trades[-1]
            B.step_trade(t, c, tp_r)
            if t["why"] is not None:
                in_pos = False
                if t["why"] == "SL": cool_until = t["ts"] + cooldown_min * 60000
    return [t for t in trades if t["why"] is not None]

cache = json.load(open("/home/z/my-project/scripts/klines_cache.json"))
allk = {s: [list(x) for x in cache[s]] for s in B.SYMS}

BASE = dict(rd_min=0.25, ema_f=True, vol_f=True, atr_floor=0.08)
variants = [
    ("A: rd.25+EMA+Vol+ATR (best so far)", dict(BASE)),
    ("B: A + C3 body<=60%", dict(BASE, c3_max_body=0.60)),
    ("C: A + window<=3 (fresh only)", dict(BASE, win_max=3)),
    ("D: A + regime EMA50/200", dict(BASE, regime=True)),
    ("E: A + ATR ceiling 0.5%", dict(BASE, atr_ceil=0.5)),
    ("F: A + zone max 1.2% (rd_max)", dict(BASE, rd_max=1.2)),
    ("G: B+C combined", dict(BASE, c3_max_body=0.60, win_max=3)),
    ("H: B+C+D combined", dict(BASE, c3_max_body=0.60, win_max=3, regime=True)),
    ("I: B+C+D+E+F ALL", dict(BASE, c3_max_body=0.60, win_max=3, regime=True, atr_ceil=0.5, rd_max=1.2)),
]
print("=== FINAL TUNING (92 din, fee-aware) ===", flush=True)
for label, kw in variants:
    merged = []
    for s, k in allk.items():
        kw2 = dict(kw)
        if kw2.pop("ema_f", False):
            kw2["ema_f"] = ema([c[4] for c in k], 200)
        merged += backtest3(k, **kw2)
    merged.sort(key=lambda t: t["ts"])
    stats(merged, label)
