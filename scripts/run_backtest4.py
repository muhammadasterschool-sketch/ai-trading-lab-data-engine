import json, sys
sys.path.insert(0, "/home/z/my-project/scripts")
import backtest_3c as B
from backtest_3c import ema, stats

def backtest4(k, ema_f=None, vol_f=False, atr_floor=0.0, tp_r=3.0, cooldown_min=15,
              rd_min=0.0, sl_buf=0.0, mode="intrabar"):
    e200 = ema([c[4] for c in k], 200)
    a14 = B.atr(k)
    vsma = [sum(c[5] for c in k[max(0, i - 19):i + 1]) / len(k[max(0, i - 19):i + 1]) for i in range(len(k))]
    trades, pending, in_pos = [], None, False
    cool_until = 0
    for i in range(2, len(k)):
        c = k[i]
        ts = c[0]
        if pending is not None:
            win = int((ts - pending["c3ts"]) / B.TF)
            if win > 5:
                pending = None
            else:
                buy = pending["side"] == "BUY"
                boundary = pending["zl"] if buy else pending["zh"]
                invalid = c[4] < boundary if buy else c[4] > boundary
                if mode == "close":
                    broke = c[4] > pending["trig"] if buy else c[4] < pending["trig"]
                    if broke and invalid: pending = None; continue
                else:
                    broke = c[2] > pending["trig"] if buy else c[3] < pending["trig"]
                if invalid:
                    pending = None
                elif broke and not in_pos and ts >= cool_until:
                    ok = True
                    if ema_f is not None: ok = c[4] > ema_f[i] if buy else c[4] < ema_f[i]
                    if ok and vol_f: ok = c[5] > 1.2 * vsma[i]
                    if ok and atr_floor > 0: ok = (a14[i] / c[4]) * 100 >= atr_floor
                    if not ok:
                        pending = None
                    else:
                        if mode == "close":
                            fill = c[4]
                        else:
                            fill = max(pending["trig"], c[1]) if buy else min(pending["trig"], c[1])
                        sl = pending["sl"] * (1 - sl_buf) if buy else pending["sl"] * (1 + sl_buf)
                        rd = fill - sl if buy else sl - fill
                        if rd > 0 and rd / fill * 100 >= rd_min:
                            tp = fill + tp_r * rd if buy else fill - tp_r * rd
                            t = {"fill": fill, "sl": sl, "tp": tp, "buy": buy, "exit": None,
                                 "why": None, "ts": ts + B.TF, "r": 0.0, "be_ts": 0}
                            trades.append(t); in_pos = True
                            if mode == "close":
                                pass  # candle already closed; manage from next candle
                            else:
                                B.step_trade(t, c, tp_r)
                                if t["why"] is not None:
                                    in_pos = False
                                    if t["why"] == "SL": cool_until = t["ts"] + cooldown_min * 60000
                        pending = None
        if pending is None and not in_pos:
            s = B.detect(k, i)
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
F = dict(rd_min=0.25, ema_f=True, vol_f=True, atr_floor=0.08)
variants = [
    ("INTRABAR (v1.5 live) + pack A", dict(F, mode="intrabar")),
    ("CLOSE-CONFIRM + pack A", dict(F, mode="close")),
    ("CLOSE-CONFIRM + A + slbuf 0.1%", dict(F, mode="close", sl_buf=0.001)),
    ("CLOSE-CONFIRM + A + TP 2.5R", dict(F, mode="close", tp_r=2.5)),
    ("CLOSE-CONFIRM + A + TP 2R", dict(F, mode="close", tp_r=2.0)),
    ("CLOSE-CONFIRM + rd 0.35% + EMA+Vol+ATR", dict(rd_min=0.35, ema_f=True, vol_f=True, atr_floor=0.08, mode="close")),
]
print("=== ENTRY MODE SHOOTOUT (92 din, fee-aware) ===", flush=True)
for label, kw in variants:
    merged = []
    for s, k in allk.items():
        kw2 = dict(kw)
        if kw2.pop("ema_f", False):
            kw2["ema_f"] = ema([c[4] for c in k], 200)
        merged += backtest4(k, **kw2)
    merged.sort(key=lambda t: t["ts"])
    stats(merged, label)
