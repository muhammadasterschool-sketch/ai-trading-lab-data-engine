import json, sys
sys.path.insert(0, "/home/z/my-project/scripts")
from backtest_3c import backtest, ema, stats, SYMS
cache = json.load(open("/home/z/my-project/scripts/klines_cache.json"))
allk = {s: [list(x) for x in cache[s]] for s in SYMS if s in cache}
print("=== PER SYMBOL: baseline (current live rules, fee 0.05%/side, cooldown 15m) ===", flush=True)
for s, k in allk.items():
    stats(backtest(k), f"{s}")
variants = [
    ("BASELINE (current rules)", dict()),
    ("+EMA200 trend filter", dict(ema_f=True)),
    ("+Volume 1.2x filter", dict(vol_f=True)),
    ("+ATR floor 0.08%", dict(atr_floor=0.08)),
    ("+ATR floor 0.12%", dict(atr_floor=0.12)),
    ("EMA200+Volume", dict(ema_f=True, vol_f=True)),
    ("EMA200+ATR0.08", dict(ema_f=True, atr_floor=0.08)),
    ("EMA200+Volume+ATR0.08", dict(ema_f=True, vol_f=True, atr_floor=0.08)),
    ("EMA200+Volume+ATR0.12", dict(ema_f=True, vol_f=True, atr_floor=0.12)),
]
print("\n=== COMBINED (all symbols merged, chronological) ===", flush=True)
for label, kw in variants:
    merged = []
    for s, k in allk.items():
        kw2 = dict(kw)
        if kw2.pop("ema_f", False):
            kw2["ema_f"] = ema([c[4] for c in k], 200)
        merged += backtest(k, **kw2)
    merged.sort(key=lambda t: t["ts"])
    stats(merged, label)
print("\n=== TRADE EXIT MIX (baseline) ===", flush=True)
b = []
for s, k in allk.items():
    b += backtest(k)
from collections import Counter
c = Counter(t["why"] for t in b)
n = len(b)
print(f"total={n}  SL={c.get('SL',0)} ({100*c.get('SL',0)/n:.0f}%)  TP={c.get('TP',0)} ({100*c.get('TP',0)/n:.0f}%)  BE={c.get('BE',0)} ({100*c.get('BE',0)/n:.0f}%)")
sls = [t for t in b if t['why']=='SL']
avg_rdist_pct = 100*sum(abs(t['fill']-t['sl'])/t['fill'] for t in b)/n
print(f"avg SL distance: {avg_rdist_pct:.3f}% of price")
