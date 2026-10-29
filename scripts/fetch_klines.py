import urllib.request, json, time, os, sys
CACHE = "/home/z/my-project/scripts/klines_cache.json"
SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
for s in SYMS:
    if cache.get(s) and len(cache[s]) >= 5000: print(s, "cached"); continue
    out, end = [], None
    while len(out) < 5000:
        url = f"https://api.binance.com/api/v3/klines?symbol={s}&interval=5m&limit=1000"
        if end: url += f"&endTime={end}"
        for attempt in range(6):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = json.loads(r.read())
                break
            except Exception as e:
                print(s, "retry", attempt, str(e)[:40], flush=True)
                if attempt == 5: raise
                time.sleep(20 if "418" in str(e) else 3)
        if not data: break
        out = data + out
        end = data[0][0] - 1
        time.sleep(1.2)
    cache[s] = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in out[-5000:]]
    print(s, len(cache[s]), flush=True)
    json.dump(cache, open(CACHE, "w"))
print("DONE")
