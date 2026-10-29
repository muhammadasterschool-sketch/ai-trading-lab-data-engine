#!/usr/bin/env python3
"""v2.1 HALAL MT5 patch for EngineCore.java — marker-based surgical replacements.
Each replacement asserts its marker exists EXACTLY once before patching."""
import sys, io

PATH = "/home/z/my-project/android-app/app/src/main/java/com/aitradinglab/engine/EngineCore.java"
src = io.open(PATH, encoding="utf-8").read()
fails = []

def replace_once(tag, old, new):
    global src
    n = src.count(old)
    if n != 1:
        fails.append(f"[{tag}] marker count = {n} (expected 1)")
        return
    src = src.replace(old, new, 1)
    print(f"OK  {tag}")

# ---------- 1. class doc: data + discovery lines ----------
replace_once("doc-data",
""" * Data: LIVE 5m klines from the Binance public API (data-api.binance.vision) — real
 *   market data, candles are never simulated. 24/7 nonstop scanner.
 * Discovery (30 min): Binance ticker scan -> auto-register new instruments (top 150).""",
""" * Data (v2.1 HALAL MT5): LIVE 5m candles for 27 HALAL COMMODITIES — public commodity
 *   futures feed (Yahoo chart API) ya optional MT5 bridge (PC par MetaTrader5 +
 *   mt5-bridge.py). Real market data — candles are never simulated. 24/7 scanner.
 * Universe (v2.1): halal commodities only (metals, energy, agri) — crypto/forex/
 *   indices/stocks owner ke hukum par removed. Discovery = universe maintenance.""")

# ---------- 2. DATA_HOSTS + fee comment + ACTIVE_TOP comments ----------
replace_once("data-hosts",
'    private static final String[] DATA_HOSTS = {"https://data-api.binance.vision", "https://api.binance.com"};',
'    // v2.1 — Binance retired: MT5 halal commodities feed (DATA section neeche).')

replace_once("fee-comment",
'    /** Binance USDT-M futures taker fee per side (0.05%) — paper P/L ab realistic.',
'    /** Commodity futures/CFD taker fee per side (0.05%) — paper P/L ab realistic.')

replace_once("active-top",
'    private static final int ACTIVE_TOP = 30;      // trade the top-N by volume',
'    private static final int ACTIVE_TOP = 30;      // halal universe (27) — cap sirf safety')

# ---------- 3. klinesFor (Strategy Lab backtester) ----------
replace_once("klines-for",
"""    /** Public klines fetch for the Strategy Lab backtester (real Binance data). */
    public List<Candle> klinesFor(String symbol, int limit) { return fetchKlines(symbol, limit); }""",
"""    /** Public klines fetch for the Strategy Lab backtester (v2.1 MT5 commodities feed).
     *  force=true — backtest rate-limit bypass karta hai. */
    public List<Candle> klinesFor(String symbol, int limit) { return fetchKlines(symbol, limit, true); }""")

# ---------- 4. DATA block: Candle + fetchKlines + httpGet -> MT5 feed ----------
DATA_START = "    // ================== DATA ==================\n"
DATA_END = "    private List<String> activeSymbols() {"
i0 = src.find(DATA_START)
i1 = src.find(DATA_END)
if i0 == -1 or i1 == -1 or i1 <= i0:
    fails.append(f"[data-block] markers: start={i0} end={i1}")
else:
    new_block = """    // ================== DATA (v2.1 HALAL MT5 FEED) ==================
    public static class Candle { long ts; double o, h, l, c, v; }

    /** v2.1 — MT5-style halal commodity universe: MT5 symbol -> public futures feed
     *  (Yahoo Finance chart API, 5m interval). Ye REAL exchange candles hain (CME/CBOT
     *  futures) — MT5 broker ke spot quote se chhota basis hota hai, paper trading ke
     *  liye bilkul theek. Optional MT5 bridge (settings mt5_bridge) set ho to candles
     *  seedha user ke MetaTrader5 terminal se aati hain (real MT5 data — PC par
     *  mt5-bridge.py chalana hota hai, script downloads page par mojood hai). */
    static final java.util.Map<String, String> MT5_FEED = new java.util.LinkedHashMap<>();
    static {
        MT5_FEED.put("XAUUSD",  "GC=F");    // Gold
        MT5_FEED.put("XAGUSD",  "SI=F");    // Silver
        MT5_FEED.put("XPTUSD",  "PL=F");    // Platinum
        MT5_FEED.put("XPDUSD",  "PA=F");    // Palladium
        MT5_FEED.put("XCUUSD",  "HG=F");    // Copper
        MT5_FEED.put("ALUUSD",  "ALI=F");   // Aluminium
        MT5_FEED.put("USOIL",   "CL=F");    // WTI Crude Oil
        MT5_FEED.put("UKOIL",   "BZ=F");    // Brent Crude Oil
        MT5_FEED.put("NGAS",    "NG=F");    // Natural Gas
        MT5_FEED.put("GASOLINE","RB=F");    // RBOB Gasoline
        MT5_FEED.put("HEATOIL", "HO=F");    // Heating Oil / ULSD
        MT5_FEED.put("WHEAT",   "ZW=F");    // Wheat
        MT5_FEED.put("CORN",    "ZC=F");    // Corn
        MT5_FEED.put("SOYBEAN", "ZS=F");    // Soybeans
        MT5_FEED.put("SOYMEAL", "ZM=F");    // Soybean Meal
        MT5_FEED.put("SOYOIL",  "ZL=F");    // Soybean Oil
        MT5_FEED.put("RICE",    "ZR=F");    // Rough Rice
        MT5_FEED.put("OATS",    "ZO=F");    // Oats
        MT5_FEED.put("COFFEE",  "KC=F");    // Coffee Arabica
        MT5_FEED.put("COCOA",   "CC=F");    // Cocoa
        MT5_FEED.put("SUGAR",   "SB=F");    // Sugar #11
        MT5_FEED.put("COTTON",  "CT=F");    // Cotton #2
        MT5_FEED.put("ORANGEJ", "OJ=F");    // Orange Juice
        MT5_FEED.put("CATTLE",  "LE=F");    // Live Cattle
        MT5_FEED.put("FEEDER",  "GF=F");    // Feeder Cattle
        MT5_FEED.put("HOGS",    "HE=F");    // Lean Hogs
        MT5_FEED.put("LUMBER",  "LBR=F");   // Lumber
    }
    private static final String YAHOO_HOST = "https://query1.finance.yahoo.com";
    /** Per-symbol last fetch attempt (rate-limit guard — M5 candles 60s refresh kaafi). */
    private final java.util.Map<String, Long> lastFetchAt = new HashMap<>();

    /** Optional MT5 bridge URL (settings mt5_bridge) — khali = built-in futures feed. */
    public String mt5Bridge() {
        String s = db.setting("mt5_bridge", "");
        return s == null ? "" : s.trim();
    }

    private List<Candle> fetchKlines(String symbol, int limit) { return fetchKlines(symbol, limit, false); }

    private List<Candle> fetchKlines(String symbol, int limit, boolean force) {
        if (!force) {
            Long last = lastFetchAt.get(symbol);
            long minGap = 60_000L;
            try { minGap = Math.max(20, Integer.parseInt(db.setting("feed_interval_sec", "60").trim())) * 1000L; } catch (Exception ignored) { }
            if (last != null && System.currentTimeMillis() - last < minGap) return new ArrayList<>();
        }
        List<Candle> out = fetchFromBridge(symbol, limit);
        if (out == null) out = fetchFromYahoo(symbol, limit);
        lastFetchAt.put(symbol, System.currentTimeMillis());
        return out;
    }

    /** MT5 bridge mode: user ke PC par chalte MetaTrader5 terminal se REAL MT5 candles.
     *  Protocol: GET {bridge}/candles?symbol=XAUUSD&tf=5m&limit=200
     *  Response: JSON array [[ts_ms, open, high, low, close, volume], ...] */
    private List<Candle> fetchFromBridge(String symbol, int limit) {
        String base = mt5Bridge();
        if (base.isEmpty()) return null;
        try {
            String body = httpGetUrl(base + (base.endsWith("/") ? "" : "/")
                    + "candles?symbol=" + symbol + "&tf=5m&limit=" + limit, 8000);
            if (body == null) return null;
            JSONArray arr = new JSONArray(body);
            List<Candle> out = new ArrayList<>();
            for (int i = 0; i < arr.length(); i++) {
                JSONArray k = arr.getJSONArray(i);
                Candle cd = new Candle();
                cd.ts = k.getLong(0); cd.o = k.getDouble(1); cd.h = k.getDouble(2);
                cd.l = k.getDouble(3); cd.c = k.getDouble(4); cd.v = k.getDouble(5);
                out.add(cd);
            }
            return out;
        } catch (Exception e) { return null; }
    }

    /** Built-in feed: public commodity futures candles (Yahoo chart API, 5m, 5d). */
    private List<Candle> fetchFromYahoo(String symbol, int limit) {
        String y = MT5_FEED.get(symbol);
        if (y == null) return null;
        try {
            String body = httpGetUrl(YAHOO_HOST + "/v8/finance/chart/" + y + "?interval=5m&range=5d", 12000);
            if (body == null) return null;
            JSONObject res = new JSONObject(body).getJSONObject("chart").getJSONArray("result").getJSONObject(0);
            JSONArray ts = res.getJSONArray("timestamp");
            JSONObject q = res.getJSONObject("indicators").getJSONArray("quote").getJSONObject(0);
            JSONArray oA = q.getJSONArray("open"), hA = q.getJSONArray("high"), lA = q.getJSONArray("low");
            JSONArray cA = q.getJSONArray("close"), vA = q.getJSONArray("volume");
            List<Candle> out = new ArrayList<>();
            for (int i = 0; i < ts.length(); i++) {
                if (oA.isNull(i) || hA.isNull(i) || lA.isNull(i) || cA.isNull(i)) continue;   // session gaps
                double o = oA.getDouble(i), h = hA.getDouble(i), l = lA.getDouble(i), c = cA.getDouble(i);
                if (o <= 0 || h <= 0 || l <= 0 || c <= 0) continue;
                Candle cd = new Candle();
                cd.ts = ts.getLong(i) * 1000L;                    // Yahoo seconds -> ms
                cd.o = o; cd.h = h; cd.l = l; cd.c = c;
                cd.v = vA.isNull(i) ? 0 : vA.getDouble(i);
                out.add(cd);
            }
            if (out.size() > limit) out = new ArrayList<>(out.subList(out.size() - limit, out.size()));
            return out;
        } catch (Exception e) { return null; }
    }

    /** Full-URL HTTP GET (v2.1 MT5 feed) — failure par null (caller skip karta hai). */
    private String httpGetUrl(String url, int timeoutMs) {
        try {
            HttpURLConnection cn = (HttpURLConnection) new URL(url).openConnection();
            cn.setConnectTimeout(timeoutMs); cn.setReadTimeout(timeoutMs + 5000);
            cn.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) AI-Trading-Lab/2.1");
            int code = cn.getResponseCode();
            if (code != 200) return null;
            BufferedReader r = new BufferedReader(new InputStreamReader(cn.getInputStream()));
            StringBuilder sb = new StringBuilder(); String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            return sb.toString();
        } catch (Exception e) { return null; }
    }

"""
    src = src[:i0] + new_block + src[i1:]
    print("OK  data-block")

# ---------- 5. upsertCandles: rolling purge ----------
replace_once("upsert-purge",
"""            d.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?",
                    new Object[]{System.currentTimeMillis(), s});
            d.setTransactionSuccessful();""",
"""            d.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?",
                    new Object[]{System.currentTimeMillis(), s});
            // v2.1: rolling window — 4 din se purani M5 candles purge (DB lean rakhta hai)
            d.execSQL("DELETE FROM candles WHERE symbol=? AND tf=? AND ts < ?",
                    new Object[]{s, TF, System.currentTimeMillis() - 4L * 86400000L});
            d.setTransactionSuccessful();""")

# ---------- 6. OWNER TRADING GATE helpers (insert before openTrade3C javadoc) ----------
GATE_ANCHOR = "    /** 3C entry — one trade per setup per account, one open position per symbol. */"
GATE_BLOCK = """    // ===== v2.1 OWNER TRADING GATE =====
    /** Owner ne is user ke liye TRADING enable ki hai? (users.trade_ok; ADMIN hamesha 1). */
    private boolean tradingAllowed(long uid) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT IFNULL(trade_ok, CASE WHEN role='ADMIN' THEN 1 ELSE 0 END) FROM users WHERE id=?",
                new String[]{String.valueOf(uid)});
        boolean ok = c.moveToFirst() && c.getInt(0) == 1;
        c.close();
        return ok;
    }

    /** v2.1 — trading-disabled user ke signal par owner ko request (30 min throttle per user). */
    private final java.util.Map<String, Long> tradeAskAt = new HashMap<>();
    private void askOwnerToEnableTrading(long uid) {
        String key = String.valueOf(uid);
        long now = System.currentTimeMillis();
        Long last = tradeAskAt.get(key);
        if (last != null && now - last < 30L * 60 * 1000) return;
        tradeAskAt.put(key, now);
        String nm = "user #" + uid;
        Cursor c = db.getReadableDatabase().rawQuery("SELECT name FROM users WHERE id=?", new String[]{key});
        if (c.moveToFirst()) nm = c.getString(0);
        c.close();
        db.log("INFO", "GUARD", "TRADE_BLOCKED_PENDING",
                nm + " ke liye signal aya lekin TRADING disabled hai — owner Control > Users me ENABLE TRADING dabayen");
        try {
            db.getWritableDatabase().execSQL(
                    "INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('TRADE_REQUEST',?,?,?,0,?)",
                    new Object[]{"Trading request — " + nm,
                            nm + " trade karna chahta hai. Settings > Control > Users me ENABLE TRADING dabayen — tab engine us ke liye trades kholega.",
                            new JSONObject().put("uid", uid).put("name", nm).toString(), now});
        } catch (Throwable ignored) { }
        try {
            Notifier.post(appContext(), "TRADING request — " + nm,
                    "Control > Users me ENABLE TRADING dabayen, tab ye user trade kar sakega");
        } catch (Throwable ignored) { }
    }

"""
replace_once("gate-helpers", GATE_ANCHOR, GATE_BLOCK + GATE_ANCHOR)

# ---------- 7. gates in openTrade3C / openTradeLab ----------
replace_once("gate-3c",
"""    private void openTrade3C(long uid, String sym, Setup3C s, double fill) {
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD""",
"""    private void openTrade3C(long uid, String sym, Setup3C s, double fill) {
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }   // v2.1 OWNER TRADING GATE""")

replace_once("gate-lab",
"""    private void openTradeLab(long uid, String sym, String side, List<Candle> k, String tier) {
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD""",
"""    private void openTradeLab(long uid, String sym, String side, List<Candle> k, String tier) {
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }   // v2.1 OWNER TRADING GATE""")

# ---------- 8. DISCOVERY block -> HALAL universe + maintenance ----------
DIS_START = "    // ================== DISCOVERY (all-world instruments) ==================\n"
DIS_END = "    // ================== NEWS ENGINE =================="
j0 = src.find(DIS_START)
j1 = src.find(DIS_END)
if j0 == -1 or j1 == -1 or j1 <= j0:
    fails.append(f"[discovery-block] markers: start={j0} end={j1}")
else:
    new_disc = """    // ================== INSTRUMENT UNIVERSE (v2.1 HALAL COMMODITIES) ==================
    /** v2.1 HALAL MODE — owner request: "binance ke bajaye MT5 connect karo, sare halal
     *  commodities add karo baki delete". Universe = 27 halal physical commodities
     *  (metals, energy, agriculture) — sab LIVE (public futures feed / MT5 bridge).
     *  Crypto, forex, indices, stocks, bonds, ETFs hata diye gaye. */
    static final String[][] HALAL_COMMODITIES = {
            {"XAUUSD", "METAL", "Gold spot (MT5 XAUUSD)"},
            {"XAGUSD", "METAL", "Silver spot (MT5 XAGUSD)"},
            {"XPTUSD", "METAL", "Platinum spot"},
            {"XPDUSD", "METAL", "Palladium spot"},
            {"XCUUSD", "METAL", "Copper (Dr. Copper)"},
            {"ALUUSD", "METAL", "Aluminium"},
            {"USOIL", "ENERGY", "WTI Crude Oil"},
            {"UKOIL", "ENERGY", "Brent Crude Oil"},
            {"NGAS", "ENERGY", "Natural Gas (Henry Hub)"},
            {"GASOLINE", "ENERGY", "RBOB Gasoline"},
            {"HEATOIL", "ENERGY", "Heating Oil / ULSD"},
            {"WHEAT", "AGRI", "Wheat (Chicago)"},
            {"CORN", "AGRI", "Corn (CBOT)"},
            {"SOYBEAN", "AGRI", "Soybeans"},
            {"SOYMEAL", "AGRI", "Soybean Meal"},
            {"SOYOIL", "AGRI", "Soybean Oil"},
            {"RICE", "AGRI", "Rough Rice"},
            {"OATS", "AGRI", "Oats"},
            {"COFFEE", "AGRI", "Coffee Arabica"},
            {"COCOA", "AGRI", "Cocoa"},
            {"SUGAR", "AGRI", "Sugar #11"},
            {"COTTON", "AGRI", "Cotton #2"},
            {"ORANGEJ", "AGRI", "Orange Juice (FCOJ)"},
            {"CATTLE", "AGRI", "Live Cattle"},
            {"FEEDER", "AGRI", "Feeder Cattle"},
            {"HOGS", "AGRI", "Lean Hogs"},
            {"LUMBER", "AGRI", "Lumber"}
    };

    private void seedStaticInstruments() {
        android.database.sqlite.SQLiteDatabase d = db.getWritableDatabase();
        long now = System.currentTimeMillis();
        for (String[] s : HALAL_COMMODITIES) {
            d.execSQL("INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,'USD','MT5',?,'ACTIVE',5000,?,?)",
                    new Object[]{s[0], s[0], s[1], now, s[2]});
        }
        // upgrade path: halal universe force-ACTIVE (purane install par bhi trade-ready)
        StringBuilder in = new StringBuilder();
        for (String[] s : HALAL_COMMODITIES) {
            if (in.length() > 0) in.append(',');
            in.append('\\'').append(s[0]).append('\\'');
        }
        d.execSQL("UPDATE instruments SET status='ACTIVE', exchange='MT5' WHERE symbol IN (" + in + ")");
        if (!"1".equals(db.setting("seeded_v21", "0"))) {
            db.setSetting("seeded_v21", "1");
            db.log("INFO", "DISCOVERY", "HALAL_SEED", "v2.1 HALAL MT5 universe: " + HALAL_COMMODITIES.length
                    + " commodities (metals/energy/agri) — crypto, forex, indices, stocks, bonds, ETFs removed by owner request. Feed: public futures ya MT5 bridge.");
        }
    }

    /** v2.1 — universe maintenance (Binance auto-discovery retired): halal list fixed.
     *  Data 6h+ purana (market band) -> WATCHING; data fresh -> ACTIVE. Koi naya
     *  symbol auto-register NAHI hota — universe sirf owner ke hukum se badalta hai. */
    private void discover() {
        long now = System.currentTimeMillis();
        Cursor c = db.getReadableDatabase().rawQuery("SELECT symbol, status, IFNULL(last_data_at,0) FROM instruments", null);
        List<Object[]> upd = new ArrayList<>();
        while (c.moveToNext()) {
            String sym = c.getString(0), st = c.getString(1);
            long lastData = c.getLong(2);
            if (lastData <= 0) continue;
            if ("ACTIVE".equals(st) && now - lastData > 6L * 3600 * 1000) upd.add(new Object[]{"WATCHING", sym});
            else if ("WATCHING".equals(st) && now - lastData < 3600 * 1000) upd.add(new Object[]{"ACTIVE", sym});
        }
        c.close();
        for (Object[] u : upd) {
            db.getWritableDatabase().execSQL("UPDATE instruments SET status=? WHERE symbol=?", u);
            db.log("INFO", "DISCOVERY", "UNIVERSE_MAINT", u[1] + " -> " + u[0]
                    + ("WATCHING".equals(u[0]) ? " (data 6h+ purana — market band hai)" : " (data wapas aya)"));
        }
    }

"""
    src = src[:j0] + new_disc + src[j1:]
    print("OK  discovery-block")

# ---------- 9. news feeds: commodities ----------
replace_once("news-feeds",
"""    private static final String[] FEEDS = {
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/"
    };""",
"""    // v2.1 HALAL MODE — commodities news sources (crypto RSS retired)
    private static final String[] FEEDS = {
            "https://www.investing.com/rss/news_25.rss",    // commodities market news
            "https://oilprice.com/rss/main"                 // energy / crude
    };""")

replace_once("high-impact",
'    private static final String[] HIGH_IMPACT = {"fed", "fomc", "rate", "cpi", "inflation", "sec", "war", "tariff", "default", "emergency", "hack", "ban"};',
'    private static final String[] HIGH_IMPACT = {"fed", "fomc", "rate", "cpi", "inflation", "opec", "war", "sanction", "tariff", "default", "emergency", "drought", "frost", "strike"};')

if fails:
    print("\nFAILED markers:")
    for f in fails: print("  " + f)
    sys.exit(1)

io.open(PATH, "w", encoding="utf-8").write(src)
print("\nPatched OK ->", PATH)
