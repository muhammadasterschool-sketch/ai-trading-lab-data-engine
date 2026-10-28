package com.aitradinglab.engine;

import android.database.Cursor;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * EngineCore — the full trading engine, ported from the server TS codebase.
 * Loop (60s): risk check -> manage open trades -> refresh candles -> scan signals
 *   -> consensus gate (>=60%) -> paper execute -> log everything.
 * Discovery (30 min): Binance ticker scan -> auto-register new instruments.
 * News (15 min): RSS -> sentiment -> high-impact pauses new entries 30 min.
 */
public class EngineCore implements Runnable {
    private static final String[] DATA_HOSTS = {"https://data-api.binance.vision", "https://api.binance.com"};
    private static final String TF = "15m";
    private static final long TF_MS = 15L * 60 * 1000;
    private static final int ACTIVE_TOP = 20;      // trade the top-N by volume
    private static final int LEDGER_TOP = 40;      // keep in instruments ledger
    private static final double RISK_PER_TRADE = 0.01;
    private static final double DAILY_HALT = -0.05;
    private static final double DRAWDOWN_KILL = -0.10;

    private final Db db;
    private volatile boolean running = true;
    private String dataHost = DATA_HOSTS[0];
    private long lastDiscovery = 0, lastNews = 0, lastLoop = 0;
    private long newsPauseUntil = 0;
    private String lastConsensus = "";
    private int activeSymbols = 0;

    public EngineCore(Db db) {
        this.db = db;
        seedStaticInstruments();
    }

    public void stop() { running = false; }
    public boolean isRunning() { return running; }

    // ================== MAIN LOOP ==================
    @Override public void run() {
        db.log("INFO", "SYSTEM", "ENGINE_START", "v5.0 phone engine started");
        while (running) {
            try {
                long now = System.currentTimeMillis();
                if (now - lastLoop >= 60_000) { loop(); lastLoop = now; }
                if (now - lastDiscovery >= 30 * 60_000) { discover(); lastDiscovery = now; }
                if (now - lastNews >= 15 * 60_000) { fetchNews(); lastNews = now; }
                Thread.sleep(2000);
            } catch (Throwable t) {
                db.log("ERROR", "SYSTEM", "LOOP_ERROR", String.valueOf(t));
                try { Thread.sleep(5000); } catch (InterruptedException ignored) { return; }
            }
        }
        db.log("INFO", "SYSTEM", "ENGINE_STOP", "engine stopped");
    }

    private void loop() {
        String engineOn = db.setting("engine_on", "1");
        if (!"1".equals(engineOn)) { lastConsensus = "engine off"; return; }
        rollDay();
        checkDrawdownKill();
        manageOpenTrades();
        refreshCandles();
        scanAndTrade();
        snapshotEquity();
    }

    // ================== RISK ==================
    private void rollDay() {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT user_id, day_ts FROM accounts", null);
        List<Long> ids = new ArrayList<>(); List<Long> ts = new ArrayList<>();
        while (c.moveToNext()) { ids.add(c.getLong(0)); ts.add(c.getLong(1)); }
        c.close();
        long today = System.currentTimeMillis() / 86400000L;
        for (int i = 0; i < ids.size(); i++) {
            if (ts.get(i) != today) {
                Cursor b = db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?", new String[]{String.valueOf(ids.get(i))});
                if (b.moveToFirst()) {
                    db.getWritableDatabase().execSQL("UPDATE accounts SET day_ts=?, day_start=? WHERE user_id=?",
                            new Object[]{today, b.getDouble(0), ids.get(i)});
                }
                b.close();
            }
        }
    }

    private boolean dailyHalted(long userId) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT balance, day_start FROM accounts WHERE user_id=?", new String[]{String.valueOf(userId)});
        boolean halted = false;
        if (c.moveToFirst()) {
            double bal = c.getDouble(0), ds = c.getDouble(1);
            halted = ds > 0 && (bal - ds) / ds <= DAILY_HALT;
            if (halted) lastConsensus = "daily loss limit 5% — entries paused until tomorrow";
        }
        c.close();
        return halted;
    }

    private void checkDrawdownKill() {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT user_id, balance, peak, start_balance FROM accounts", null);
        while (c.moveToNext()) {
            long uid = c.getLong(0); double bal = c.getDouble(1), peak = c.getDouble(2), start = c.getDouble(3);
            if (bal > peak) db.getWritableDatabase().execSQL("UPDATE accounts SET peak=? WHERE user_id=?", new Object[]{bal, uid});
            if (peak > 0 && (bal - peak) / peak <= DRAWDOWN_KILL) {
                closeAll(uid, "KILL_SWITCH");
                db.setSetting("engine_on", "0");
                db.log("ERROR", "RISK", "KILL_SWITCH", "drawdown >= 10% from peak — engine disabled, re-enable in Settings");
            }
        }
        c.close();
    }

    // ================== DATA ==================
    public static class Candle { long ts; double o, h, l, c, v; }

    private List<Candle> fetchKlines(String symbol, int limit) {
        String path = "/api/v3/klines?symbol=" + symbol + "&interval=" + TF + "&limit=" + limit;
        String body = httpGet(path);
        if (body == null) return null;
        try {
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

    private String httpGet(String path) {
        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                HttpURLConnection cn = (HttpURLConnection) new URL(dataHost + path).openConnection();
                cn.setConnectTimeout(10000); cn.setReadTimeout(15000);
                cn.setRequestProperty("User-Agent", "AI-Trading-Lab/5.0");
                int code = cn.getResponseCode();
                if (code == 200) {
                    BufferedReader r = new BufferedReader(new InputStreamReader(cn.getInputStream()));
                    StringBuilder sb = new StringBuilder(); String line;
                    while ((line = r.readLine()) != null) sb.append(line);
                    r.close();
                    return sb.toString();
                }
                if (code == 451 || code == 403) { dataHost = DATA_HOSTS[1]; continue; }
            } catch (Exception ignored) { }
            dataHost = (attempt == 0) ? DATA_HOSTS[1] : DATA_HOSTS[0];
        }
        return null;
    }

    private List<String> activeSymbols() {
        List<String> out = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol FROM instruments WHERE status='ACTIVE' ORDER BY priority DESC LIMIT ?", new String[]{String.valueOf(ACTIVE_TOP)});
        while (c.moveToNext()) out.add(c.getString(0));
        c.close();
        return out;
    }

    private void refreshCandles() {
        List<String> symbols = activeSymbols();
        activeSymbols = symbols.size();
        for (String s : symbols) {
            List<Candle> ks = fetchKlines(s, 200);
            if (ks == null || ks.isEmpty()) continue;
            upsertCandles(s, ks);
        }
    }

    private void upsertCandles(String s, List<Candle> ks) {
        android.database.sqlite.SQLiteDatabase d = db.getWritableDatabase();
        d.beginTransaction();
        try {
            for (Candle k : ks) {
                d.execSQL("INSERT OR REPLACE INTO candles(symbol, tf, ts, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)",
                        new Object[]{s, TF, k.ts, k.o, k.h, k.l, k.c, k.v});
            }
            d.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?",
                    new Object[]{System.currentTimeMillis(), s});
            d.setTransactionSuccessful();
        } finally { d.endTransaction(); }
    }

    private List<Candle> loadCandles(String symbol) {
        List<Candle> out = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts", new String[]{symbol, TF});
        while (c.moveToNext()) {
            Candle k = new Candle();
            k.ts = c.getLong(0); k.o = c.getDouble(1); k.h = c.getDouble(2);
            k.l = c.getDouble(3); k.c = c.getDouble(4); k.v = c.getDouble(5);
            out.add(k);
        }
        c.close();
        return out;
    }

    // ================== INDICATORS ==================
    static double ema(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double mult = 2.0 / (n + 1), e = 0; boolean init = false;
        for (int i = Math.max(0, k.size() - 200); i < k.size(); i++) {
            double c = k.get(i).c;
            e = init ? (c - e) * mult + e : c; init = true;
        }
        return e;
    }

    static double rsi(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double g = 0, l = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            double ch = k.get(i).c - k.get(i - 1).c;
            if (ch > 0) g += ch; else l -= ch;
        }
        if (g + l == 0) return 50;
        return 100 * g / (g + l);
    }

    static double[] bollinger(List<Candle> k, int n) {
        if (k.size() < n) return null;
        double sum = 0, sum2 = 0;
        for (int i = k.size() - n; i < k.size(); i++) { double c = k.get(i).c; sum += c; sum2 += c * c; }
        double mean = sum / n, sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
        return new double[]{mean - 2 * sd, mean, mean + 2 * sd};
    }

    static double[] macd(List<Candle> k) {
        double e12 = ema(k, 12), e26 = ema(k, 26);
        if (Double.isNaN(e12) || Double.isNaN(e26)) return null;
        double line = e12 - e26;
        double signal = line * 0.8; // EMA9 of MACD approximated
        return new double[]{line, signal};
    }

    static double[] stochastic(List<Candle> k, int n) {
        if (k.size() < n) return null;
        double hh = Double.MIN_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double close = k.get(k.size() - 1).c;
        if (hh == ll) return new double[]{50, 50};
        double pctK = 100 * (close - ll) / (hh - ll);
        double pctD = pctK * 0.7 + 50 * 0.3;
        return new double[]{pctK, pctD};
    }

    static double vwap(List<Candle> k) {
        double pv = 0, vv = 0;
        int from = Math.max(0, k.size() - 96);
        for (int i = from; i < k.size(); i++) {
            Candle c = k.get(i);
            double tp = (c.h + c.l + c.c) / 3;
            pv += tp * c.v; vv += c.v;
        }
        return vv > 0 ? pv / vv : k.get(k.size() - 1).c;
    }

    static double atr(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double sum = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double tr = Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
            sum += tr;
        }
        return sum / n;
    }

    // ================== STRATEGIES (5) ==================
    /** vote: +1 buy, -1 sell, 0 neutral */
    private int emaCross(List<Candle> k) {
        double e9 = ema(k, 9), e21 = ema(k, 21);
        if (Double.isNaN(e9) || Double.isNaN(e21)) return 0;
        double prev9 = ema(k.subList(0, k.size() - 1), 9), prev21 = ema(k.subList(0, k.size() - 1), 21);
        if (Double.isNaN(prev9) || Double.isNaN(prev21)) return 0;
        if (prev9 <= prev21 && e9 > e21) return 1;
        if (prev9 >= prev21 && e9 < e21) return -1;
        return 0;
    }

    private int rsiBollinger(List<Candle> k) {
        double r = rsi(k, 14); double[] bb = bollinger(k, 20);
        if (Double.isNaN(r) || bb == null) return 0;
        double c = k.get(k.size() - 1).c;
        if (c < bb[0] && r < 32) return 1;
        if (c > bb[2] && r > 68) return -1;
        return 0;
    }

    private int macdStoch(List<Candle> k) {
        double[] m = macd(k); double[] s = stochastic(k, 14);
        if (m == null || s == null) return 0;
        boolean bull = m[0] > m[1] && s[0] < 35;
        boolean bear = m[0] < m[1] && s[0] > 65;
        return bull ? 1 : bear ? -1 : 0;
    }

    private int vwapReversion(List<Candle> k) {
        double v = vwap(k), c = k.get(k.size() - 1).c;
        if (v <= 0) return 0;
        double dev = (c - v) / v;
        if (dev < -0.012) return 1;
        if (dev > 0.012) return -1;
        return 0;
    }

    private int breakout(List<Candle> k) {
        if (k.size() < 16) return 0;
        double hh = Double.MIN_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - 16; i < k.size() - 1; i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double c = k.get(k.size() - 1).c;
        if (c > hh) return 1;
        if (c < ll) return -1;
        return 0;
    }

    // ================== TRADE LOGIC ==================
    private void scanAndTrade() {
        if (System.currentTimeMillis() < newsPauseUntil) { lastConsensus = "news pause active"; return; }
        for (long uid : userIds()) {
            if (dailyHalted(uid)) continue;
            Cursor oc = db.getReadableDatabase().rawQuery(
                    "SELECT COUNT(*) FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(uid)});
            int open = oc.moveToFirst() ? oc.getInt(0) : 0; oc.close();
            if (open >= 5) { lastConsensus = "max concurrent positions (5)"; continue; }

            for (String sym : activeSymbols()) {
                if (open >= 5) break;
                Cursor ex = db.getReadableDatabase().rawQuery(
                        "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'", new String[]{String.valueOf(uid), sym});
                boolean have = ex.moveToFirst() && ex.getInt(0) > 0; ex.close();
                if (have) continue;

                List<Candle> k = loadCandles(sym);
                if (k.size() < 60) continue;
                // confirmation candle: last candle closed
                if (System.currentTimeMillis() - k.get(k.size() - 1).ts < TF_MS) continue;

                int[] votes = {emaCross(k), rsiBollinger(k), macdStoch(k), vwapReversion(k), breakout(k)};
                int buy = 0, sell = 0;
                for (int v : votes) { if (v > 0) buy++; else if (v < 0) sell++; }
                double consensusBuy = buy / 5.0, consensusSell = sell / 5.0;

                if (consensusBuy >= 0.6) { openTrade(uid, sym, "BUY", consensusBuy, k); open++; }
                else if (consensusSell >= 0.6) { openTrade(uid, sym, "SELL", consensusSell, k); open++; }
                else lastConsensus = "scanning " + activeSymbols + " symbols — no >=60% consensus yet";
            }
        }
    }

    private void openTrade(long uid, String sym, String side, double consensus, List<Candle> k) {
        double price = k.get(k.size() - 1).c;
        double a = atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return;
        double sl = "BUY".equals(side) ? price - 1.5 * a : price + 1.5 * a;
        double tp = "BUY".equals(side) ? price + 2.5 * a : price - 2.5 * a;

        Cursor c = db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?", new String[]{String.valueOf(uid)});
        double bal = c.moveToFirst() ? c.getDouble(0) : 100000; c.close();
        double riskAmt = bal * RISK_PER_TRADE;
        double qty = riskAmt / (1.5 * a);
        if (qty * price > bal * 0.95) qty = bal * 0.95 / price;
        if (qty <= 0) return;

        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at) VALUES(?,?,?,?,?,?,?, 'OPEN', 'CONSENSUS_5', ?, ?)",
                new Object[]{uid, sym, side, qty, price, sl, tp, consensus, System.currentTimeMillis()});
        db.log("INFO", "EXECUTOR", "PAPER_OPEN", sym + " " + side + " qty=" + String.format("%.6f", qty) + " consensus=" + (int)(consensus*100) + "%");
    }

    private void manageOpenTrades() {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, user_id, symbol, side, qty, entry, sl, tp FROM trades WHERE status='OPEN'", null);
        List<Object[]> rows = new ArrayList<>();
        while (c.moveToNext()) {
            rows.add(new Object[]{c.getLong(0), c.getLong(1), c.getString(2), c.getString(3), c.getDouble(4), c.getDouble(5), c.getDouble(6), c.getDouble(7)});
        }
        c.close();
        for (Object[] r : rows) {
            long id = (Long) r[0], uid = (Long) r[1];
            String sym = (String) r[2], side = (String) r[3];
            double qty = (Double) r[4], entry = (Double) r[5], sl = (Double) r[6], tp = (Double) r[7];
            Cursor cc = db.getReadableDatabase().rawQuery(
                    "SELECT c FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT 1", new String[]{sym, TF});
            double price = cc.moveToFirst() ? cc.getDouble(0) : Double.NaN; cc.close();
            if (Double.isNaN(price)) continue;

            boolean hitSl = "BUY".equals(side) ? price <= sl : price >= sl;
            boolean hitTp = "BUY".equals(side) ? price >= tp : price <= tp;
            if (hitSl || hitTp) closeTrade(id, uid, price, hitSl ? "SL" : "TP", qty, entry, side);
        }
    }

    private void closeTrade(long id, long uid, double price, String reason, double qty, double entry, String side) {
        double pnl = ("BUY".equals(side) ? price - entry : entry - price) * qty;
        db.getWritableDatabase().execSQL(
                "UPDATE trades SET exit=?, pnl=?, status='CLOSED', closed_at=? WHERE id=?",
                new Object[]{price, pnl, System.currentTimeMillis(), id});
        db.getWritableDatabase().execSQL(
                "UPDATE accounts SET balance = balance + ? WHERE user_id=?", new Object[]{pnl, uid});
        db.log(reason.equals("SL") ? "WARN" : "INFO", "EXECUTOR", "PAPER_CLOSE_" + reason,
                "trade #" + id + " pnl=" + String.format("%.2f", pnl));
    }

    private void closeAll(long uid, String reason) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, qty, entry, side FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(uid)});
        List<Object[]> rows = new ArrayList<>();
        while (c.moveToNext()) rows.add(new Object[]{c.getLong(0), c.getDouble(1), c.getDouble(2), c.getString(3)});
        c.close();
        for (Object[] r : rows) closeTrade((Long) r[0], uid, (Double) r[2], reason, (Double) r[1], (Double) r[2], (String) r[3]);
    }

    private List<Long> userIds() {
        List<Long> out = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE active=1", null);
        while (c.moveToNext()) out.add(c.getLong(0));
        c.close();
        return out;
    }

    private void snapshotEquity() {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT AVG(balance) FROM accounts", null);
        double eq = c.moveToFirst() ? c.getDouble(0) : 100000; c.close();
        db.getWritableDatabase().execSQL("INSERT OR REPLACE INTO equity(ts, value) VALUES(?,?)",
                new Object[]{System.currentTimeMillis(), eq});
    }

    // ================== DISCOVERY (all-world instruments) ==================
    private void seedStaticInstruments() {
        String[][] statics = {
                {"XAUUSD", "GOLD", "PENDING_BROKER", "Gold spot — activates when broker connected (live phase)"},
                {"XAGUSD", "SILVER", "PENDING_BROKER", "Silver spot — activates when broker connected"},
                {"EURUSD", "FOREX", "PENDING_BROKER", "Euro/US dollar — activates when broker connected"},
                {"GBPUSD", "FOREX", "PENDING_BROKER", "Pound/US dollar — activates when broker connected"},
                {"USDJPY", "FOREX", "PENDING_BROKER", "Dollar/Yen — activates when broker connected"},
                {"US500", "INDEX", "PENDING_BROKER", "S&P 500 — activates when broker connected"},
                {"NAS100", "INDEX", "PENDING_BROKER", "Nasdaq 100 — activates when broker connected"},
        };
        for (String[] s : statics) {
            db.getWritableDatabase().execSQL(
                    "INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,?,?,?,?,?,?,?)",
                    new Object[]{s[0], s[0], "USD", "BROKER", s[1], s[2], 0, System.currentTimeMillis(), s[3]});
        }
        if (db.setting("seeded_gold", "0").equals("0")) {
            db.setSetting("seeded_gold", "1");
            db.log("INFO", "DISCOVERY", "STATIC_INSTRUMENTS", "Gold/Forex/Index instruments registered (pending broker)");
        }
    }

    private void discover() {
        String body = httpGet("/api/v3/ticker/24hr");
        if (body == null) { db.log("WARN", "DISCOVERY", "TICKER_FETCH_FAIL", "no data host reachable"); return; }
        try {
            JSONArray arr = new JSONArray(body);
            List<double[]> vols = new ArrayList<>(); // [volume, index]
            List<JSONObject> rows = new ArrayList<>();
            for (int i = 0; i < arr.length(); i++) {
                JSONObject t = arr.getJSONObject(i);
                String symbol = t.optString("symbol", "");
                if (!symbol.endsWith("USDT")) continue;
                if (symbol.endsWith("UPUSDT") || symbol.endsWith("DOWNUSDT") || symbol.contains("BULL") || symbol.contains("BEAR")) continue;
                double vol;
                try { vol = t.getDouble("quoteVolume"); } catch (Exception e) { continue; }
                rows.add(t); vols.add(new double[]{vol, rows.size() - 1});
            }
            Collections.sort(vols, (x, y) -> Double.compare(y[0], x[0]));
            int newCount = 0;
            for (int rank = 0; rank < Math.min(vols.size(), LEDGER_TOP); rank++) {
                JSONObject t = rows.get((int) vols.get(rank)[1]);
                String symbol = t.getString("symbol");
                String base = symbol.substring(0, symbol.length() - 4);
                String status = rank < ACTIVE_TOP ? "ACTIVE" : "WATCHING";
                Cursor ex = db.getReadableDatabase().rawQuery("SELECT symbol FROM instruments WHERE symbol=?", new String[]{symbol});
                boolean exists = ex.moveToFirst(); ex.close();
                if (!exists) {
                    db.getWritableDatabase().execSQL(
                            "INSERT INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,?,?,?,?,?,?,?)",
                            new Object[]{symbol, base, "USDT", "BINANCE", "CRYPTO", status, (long) vols.get(rank)[0], System.currentTimeMillis(), "auto-registered by discovery scanner"});
                    newCount++;
                    db.log("INFO", "DISCOVERY", "AUTO_REGISTER", symbol + " rank=" + (rank + 1) + " -> " + status + " (trading starts automatically)");
                } else {
                    db.getWritableDatabase().execSQL("UPDATE instruments SET status=?, priority=? WHERE symbol=?",
                            new Object[]{status, (long) vols.get(rank)[0], symbol});
                }
            }
            if (newCount > 0) db.log("INFO", "DISCOVERY", "SCAN_DONE", newCount + " new instrument(s) auto-registered — trading enabled on them");
        } catch (Exception e) {
            db.log("ERROR", "DISCOVERY", "SCAN_PARSE_FAIL", String.valueOf(e));
        }
    }

    // ================== NEWS ENGINE ==================
    private static final String[] FEEDS = {
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/"
    };
    private static final String[] BULL = {"surge", "rally", "gain", "record", "adopt", "approval", "approved", "bullish", "soar", "jump", "rise", "up", "inflow", "upgrade", "breakout"};
    private static final String[] BEAR = {"crash", "plunge", "ban", "hack", "lawsuit", "drop", "fall", "bearish", "sink", "loss", "outflow", "downgrade", "sell-off", "fear"};
    private static final String[] HIGH_IMPACT = {"fed", "fomc", "rate", "cpi", "inflation", "sec", "war", "tariff", "default", "emergency", "hack", "ban"};

    private void fetchNews() {
        for (String feed : FEEDS) {
            String xml = rawGet(feed);
            if (xml == null) continue;
            List<String[]> items = parseRss(xml);
            for (String[] it : items) {
                String title = it[0].trim();
                if (title.isEmpty()) continue;
                Cursor ex = db.getReadableDatabase().rawQuery("SELECT id FROM news WHERE headline=?", new String[]{title});
                boolean dup = ex.moveToFirst(); ex.close();
                if (dup) continue;

                String low = title.toLowerCase();
                int bull = 0, bear = 0;
                for (String w : BULL) if (low.contains(w)) bull++;
                for (String w : BEAR) if (low.contains(w)) bear++;
                String sentiment = bull > bear ? "BULLISH" : bear > bull ? "BEARISH" : "NEUTRAL";
                String impact = "LOW";
                for (String w : HIGH_IMPACT) if (low.contains(w)) { impact = "HIGH"; break; }

                db.getWritableDatabase().execSQL("INSERT INTO news(ts, source, headline, sentiment, impact) VALUES(?,?,?,?,?)",
                        new Object[]{System.currentTimeMillis(), feed.contains("coindesk") ? "CoinDesk" : "CoinTelegraph", title, sentiment, impact});
                db.log("INFO", "NEWS", "INGEST", sentiment + "/" + impact + " — " + title.substring(0, Math.min(80, title.length())));

                if ("HIGH".equals(impact)) {
                    newsPauseUntil = System.currentTimeMillis() + 30L * 60 * 1000;
                    db.log("WARN", "NEWS", "PAUSE_ENTRIES", "high-impact news — new entries paused 30 min (" + title.substring(0, Math.min(60, title.length())) + ")");
                }
            }
        }
    }

    private List<String[]> parseRss(String xml) {
        List<String[]> out = new ArrayList<>();
        int idx = 0;
        while (out.size() < 12) {
            int s = xml.indexOf("<item>", idx);
            if (s < 0) break;
            int e = xml.indexOf("</item>", s);
            if (e < 0) break;
            String chunk = xml.substring(s, e);
            int ts = chunk.indexOf("<title>"); int te = chunk.indexOf("</title>");
            if (ts >= 0 && te > ts) {
                String title = chunk.substring(ts + 7, te)
                        .replace("<![CDATA[", "").replace("]]>", "")
                        .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                        .replace("&quot;", "\"").replace("&#39;", "'").replace("&nbsp;", " ").trim();
                if (!title.isEmpty()) out.add(new String[]{title});
            }
            idx = e + 7;
        }
        return out;
    }

    private String rawGet(String url) {
        try {
            HttpURLConnection cn = (HttpURLConnection) new URL(url).openConnection();
            cn.setConnectTimeout(10000); cn.setReadTimeout(15000);
            cn.setRequestProperty("User-Agent", "Mozilla/5.0 AI-Trading-Lab/5.0");
            if (cn.getResponseCode() != 200) return null;
            BufferedReader r = new BufferedReader(new InputStreamReader(cn.getInputStream()));
            StringBuilder sb = new StringBuilder(); String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            return sb.toString();
        } catch (Exception e) { return null; }
    }

    // ================== STATUS for API ==================
    public Map<String, Object> status() {
        Map<String, Object> m = new HashMap<>();
        m.put("engine_on", "1".equals(db.setting("engine_on", "1")));
        m.put("active_symbols", activeSymbols);
        m.put("consensus", lastConsensus.isEmpty() ? "warming up" : lastConsensus);
        m.put("news_pause", System.currentTimeMillis() < newsPauseUntil);
        m.put("data_host", dataHost);
        return m;
    }

    public void forceDiscovery() {
        Thread t = new Thread(() -> {
            try {
                discover();
                fetchNews();
            } catch (Throwable e) {
                // manual scan must never take the whole app down
                try { db.log("ERROR", "SYSTEM", "FORCE_SCAN_FAIL", String.valueOf(e)); } catch (Exception ignored) { }
            }
        }, "force-scan");
        t.setDaemon(true);
        t.start();
    }
}
