import urllib.request, zipfile, io, json, os, time
CACHE = "/home/z/my-project/scripts/klines_cache.json"
SYMS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT"]
MONTHS = ["2026-07", "2026-08", "2026-09"]
cache = {s: [] for s in SYMS}
if os.path.exists(CACHE):
    old = json.load(open(CACHE))
    for s in old: cache[s] = old[s]
for s in SYMS:
    if cache.get(s) and len(cache[s]) > 12000: print(s, "cached", len(cache[s])); continue
    rows = []
    for m in MONTHS:
        url = f"https://data.binance.vision/data/spot/monthly/klines/{s}/5m/{s}-5m-{m}.zip"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    z = zipfile.ZipFile(io.BytesIO(r.read()))
                    name = z.namelist()[0]
                    lines = z.read(name).decode().strip().split("\n")
                    for ln in lines:
                        p = ln.split(",")
                        if len(p) < 6: continue
                        ts = int(p[0])
                        if ts > 1e14: ts //= 1000  # us -> ms
                        rows.append([ts, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[5])])
                break
            except Exception as e:
                print(s, m, "retry", attempt, str(e)[:40], flush=True)
                if attempt == 2: raise
                time.sleep(5)
    rows.sort(key=lambda x: x[0])
    # dedupe
    seen, dd = set(), []
    for r in rows:
        if r[0] not in seen: seen.add(r[0]); dd.append(r)
    cache[s] = dd
    print(s, len(dd), flush=True)
json.dump(cache, open(CACHE, "w"))
print("DONE")
