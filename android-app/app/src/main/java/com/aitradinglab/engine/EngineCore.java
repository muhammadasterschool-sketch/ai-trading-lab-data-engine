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
 * EngineCore v1.1 — 1-MINUTE 24H SCANNER, two-tier entry engine.
 * Loop (30s): risk check -> manage open trades -> refresh candles -> scan signals -> paper execute.
 *
 * v1.1 ENTRY FIX (why the old build never traded):
 *   The old gate demanded >=14 of 35 strategies voting on one candle (40% participation).
 *   But ~20 of the 35 strategies are EVENT-based by design — they only vote on rare
 *   events (exact EMA crossover bar, Supertrend flip bar, oversold extremes, candlestick
 *   patterns, harmonics, SMC breaks). A typical 1m candle gets only 5-12 votes, so the
 *   gate almost never passed and the engine sat silent forever.
 *
 *   Fix, two parts:
 *   1. The two core trend strategies (EMA 9/21, Supertrend) now vote on their CURRENT
 *      STATE (alignment / regime), not only on the rare event bar. Trend gauges can now
 *      actually speak on every candle.
 *   2. Two-tier entry:
 *      TIER A "CONSENSUS_35" — >=9 strategies voted AND >=60% dominant (strict lead).
 *      TIER B "SCOUT_SIGNAL" — if the engine has been silent 20+ minutes, a strong
 *                              lean (>=6 voters, >=65% dominant) is enough so the lab
 *                              always demonstrates real behavior.
 *
 * Risk model (unchanged): 1% balance risk/trade | SL 1.5xATR | TP 2.5xATR (1:1.67 R:R)
 *   | UNLIMITED concurrent positions (v1.2, owner request — no cap) | 1 open position
 *   per symbol (anti-duplicate guard) | daily halt -5% | kill switch -10%.
 * Paper money: default $100 per new account (v1.2); owner can set ANY amount from
 *   Settings > Paper Balance (/api/balance) — open trades are cancelled on change.
 * Data: LIVE 1m klines from the Binance public API (data-api.binance.vision) — real
 *   market data, candles are never simulated. 1m timeframe, 24/7 nonstop.
 * Discovery (30 min): Binance ticker scan -> auto-register new instruments (top 150).
 * News (15 min): RSS -> sentiment -> high-impact pauses new entries 30 min.
 */
public class EngineCore implements Runnable {
    private static final String[] DATA_HOSTS = {"https://data-api.binance.vision", "https://api.binance.com"};
    private static final String TF = "1m";
    private static final long TF_MS = 60L * 1000;
    private static final int ACTIVE_TOP = 30;      // trade the top-N by volume
    private static final int LEDGER_TOP = 150;     // keep in instruments ledger
    private static final double RISK_PER_TRADE = 0.01;
    private static final double DAILY_HALT = -0.05;
    private static final double DRAWDOWN_KILL = -0.10;

    private final Db db;
    private volatile boolean running = true;
    private String dataHost = DATA_HOSTS[0];
    private long lastDiscovery = 0, lastNews = 0, lastLoop = 0;
    private long newsPauseUntil = 0;
    private String lastConsensus = "";
    private volatile long lastEntryAt = System.currentTimeMillis(); // v1.1 — scout-tier timer (engine start = t0)
    private int activeSymbols = 0;
    private long scanCount = 0;             // 24h scanner heartbeat counter
    private volatile long lastScanAt = 0;
    private volatile int fngValue = -1;     // crypto Fear & Greed (0-100), -1 = no data
    private long lastFng = 0;
    private String lastPattern = "";

    public EngineCore(Db db) {
        this.db = db;
        seedStaticInstruments();
    }

    public void stop() { running = false; }
    public boolean isRunning() { return running; }

    // ================== MAIN LOOP ==================
    @Override public void run() {
        db.log("INFO", "SYSTEM", "ENGINE_START", "v1.2 two-tier entry engine — 1m timeframe, 24h nonstop scanner, 35 strategies, live Binance data | TIER-A consensus: >=9 voters & >=60% dominant | TIER-B scout after 20 min silence: >=6 voters & >=65% | risk 1%/trade, SL 1.5xATR, TP 2.5xATR, UNLIMITED positions | paper money $100 default, owner-changeable");

        // v1.2 ONE-TIME MIGRATION — paper money is now $100 (owner request). Accounts still
        // on the old $100,000 default are reset; open trades are cancelled because they
        // were sized against the old balance. Afterwards the owner can set ANY amount
        // from Settings > Paper Balance.
        if (!"1".equals(db.setting("v12_paper_100", "0"))) {
            long t0 = System.currentTimeMillis();
            try {
                db.getWritableDatabase().execSQL(
                        "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'",
                        new Object[]{t0});
                db.getWritableDatabase().execSQL(
                        "UPDATE accounts SET balance=100, start_balance=100, peak=100, day_start=100, day_ts=?",
                        new Object[]{t0 / 86400000L});
                db.setSetting("v12_paper_100", "1");
                db.log("INFO", "ACCOUNT", "PAPER_RESET_100", "v1.2 one-time reset — paper accounts set to $100 (old $100,000 default retired), open trades cancelled. Apna amount Settings > Paper Balance se kabhi bhi badal sakte hain.");
            } catch (Throwable t) {
                db.log("ERROR", "ACCOUNT", "PAPER_RESET_FAIL", String.valueOf(t));
            }
        }
        while (running) {
            try {
                long now = System.currentTimeMillis();
                if (now - lastLoop >= 30_000) { loop(); lastLoop = now; }
                if (now - lastDiscovery >= 30 * 60_000) { discover(); lastDiscovery = now; }
                if (now - lastNews >= 15 * 60_000) { fetchNews(); lastNews = now; }
                if (now - lastFng >= 60 * 60_000) { fetchFearGreed(); lastFng = now; }
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
        scanCount++;
        lastScanAt = System.currentTimeMillis();
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
        double[] e12 = emaSeries(k, 12), e26 = emaSeries(k, 26);
        if (e12 == null || e26 == null) return null;
        int n = k.size();
        double[] line = new double[n];
        for (int i = 0; i < n; i++) line[i] = e12[i] - e26[i];
        // signal = EMA9 of the MACD line
        double mult = 2.0 / 10;
        double sig = 0; boolean init = false;
        for (int i = 0; i < n; i++) {
            sig = init ? (line[i] - sig) * mult + sig : line[i]; init = true;
        }
        return new double[]{line[n - 1], sig};
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

    // ================== INDICATORS v5.8 (extended suite) ==================

    /** Series EMA — returns the full EMA line (for MACD signal, StochRSI, TRIX). */
    static double[] emaSeries(List<Candle> k, int n) {
        if (k.size() < n) return null;
        double[] out = new double[k.size()];
        double mult = 2.0 / (n + 1);
        double e = 0; boolean init = false;
        for (int i = 0; i < k.size(); i++) {
            double c = k.get(i).c;
            e = init ? (c - e) * mult + e : c; init = true;
            out[i] = e;
        }
        return out;
    }

    /** SMA of a series (helper for signal lines, %D smoothing, ADX smoothing). */
    static double smaOf(double[] v, int from, int n) {
        if (v == null || from - n + 1 < 0 || n <= 0) return Double.NaN;
        double s = 0;
        for (int i = from - n + 1; i <= from; i++) s += v[i];
        return s / n;
    }

    /** RSI series (for Stochastic RSI). */
    static double[] rsiSeries(List<Candle> k, int n) {
        if (k.size() < n + 1) return null;
        double[] out = new double[k.size()];
        double g = 0, l = 0;
        for (int i = 1; i < k.size(); i++) {
            double ch = k.get(i).c - k.get(i - 1).c;
            if (i <= n) {
                if (ch > 0) g += ch; else l -= ch;
                out[i] = (g + l == 0) ? 50 : 100 * g / (g + l);
                if (i == n) { double f100 = 100.0 / n; g /= n; l /= n; out[i] = 100 * g / (g + l); }
                continue;
            }
            // Wilder smoothing
            g = (g * (n - 1) + Math.max(ch, 0)) / n;
            l = (l * (n - 1) + Math.max(-ch, 0)) / n;
            out[i] = (g + l == 0) ? 50 : 100 * g / (g + l);
        }
        return out;
    }

    /** Stochastic RSI (14,14,3,3) — returns [k, d]. */
    static double[] stochRsi(List<Candle> k) {
        double[] r = rsiSeries(k, 14);
        if (r == null || k.size() < 32) return null;
        double kRaw = Double.NaN, dRaw = Double.NaN;
        double[] stoch = new double[k.size()];
        for (int i = 31; i < k.size(); i++) {
            double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
            for (int j = i - 13; j <= i; j++) { hh = Math.max(hh, r[j]); ll = Math.min(ll, r[j]); }
            stoch[i] = (hh == ll) ? 50 : 100 * (r[i] - ll) / (hh - ll);
        }
        // %K = SMA3 of raw stoch, %D = SMA3 of %K
        int last = k.size() - 1;
        if (last >= 33) {
            kRaw = (stoch[last] + stoch[last - 1] + stoch[last - 2]) / 3;
            if (last >= 35) {
                dRaw = (kRaw + (stoch[last - 1] + stoch[last - 2] + stoch[last - 3]) / 3
                          + (stoch[last - 2] + stoch[last - 3] + stoch[last - 4]) / 3) / 3;
            } else dRaw = kRaw;
        } else return null;
        return new double[]{kRaw, dRaw};
    }

    /** ADX (14) with +DI / -DI — returns [adx, plusDi, minusDi]. */
    static double[] adx(List<Candle> k, int n) {
        if (k.size() < 2 * n + 2) return null;
        double plusDmS = 0, minusDmS = 0, trS = 0;
        // seed Wilder sums
        for (int i = k.size() - 2 * n + 1; i < k.size() - n + 1; i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double up = c.h - p.h, dn = p.l - c.l;
            plusDmS += (up > dn && up > 0) ? up : 0;
            minusDmS += (dn > up && dn > 0) ? dn : 0;
            trS += Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
        }
        double dxSum = 0; int dxN = 0;
        double lastPdi = 0, lastMdi = 0;
        for (int i = k.size() - n + 1; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double up = c.h - p.h, dn = p.l - c.l;
            plusDmS = plusDmS - plusDmS / n + ((up > dn && up > 0) ? up : 0);
            minusDmS = minusDmS - minusDmS / n + ((dn > up && dn > 0) ? dn : 0);
            trS = trS - trS / n + Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
            if (trS <= 0) continue;
            double pdi = 100 * plusDmS / trS, mdi = 100 * minusDmS / trS;
            double dx = (pdi + mdi == 0) ? 0 : 100 * Math.abs(pdi - mdi) / (pdi + mdi);
            dxSum += dx; dxN++;
            lastPdi = pdi; lastMdi = mdi;
        }
        return new double[]{dxN > 0 ? dxSum / dxN : 0, lastPdi, lastMdi};
    }

    /** CCI (20) — Commodity Channel Index. */
    static double cci(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double[] tp = new double[n]; double sum = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i);
            tp[i - (k.size() - n)] = (c.h + c.l + c.c) / 3;
            sum += tp[i - (k.size() - n)];
        }
        double ma = sum / n, dev = 0;
        for (double t : tp) dev += Math.abs(t - ma);
        dev /= n;
        if (dev == 0) return 0;
        return (tp[n - 1] - ma) / (0.015 * dev);
    }

    /** Williams %R (14). */
    static double williamsR(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        if (hh == ll) return -50;
        return -100 * (hh - k.get(k.size() - 1).c) / (hh - ll);
    }

    /** MFI (14) — Money Flow Index (volume-weighted RSI). */
    static double mfi(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double pos = 0, neg = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double tp = (c.h + c.l + c.c) / 3, pp = (p.h + p.l + p.c) / 3;
            double flow = tp * c.v;
            if (tp > pp) pos += flow; else if (tp < pp) neg += flow;
        }
        if (neg == 0) return 100;
        if (pos == 0) return 0;
        return 100 - 100 / (1 + pos / neg);
    }

    /** OBV slope over last n bars — positive = accumulation, negative = distribution. */
    static double obvSlope(List<Candle> k, int n) {
        if (k.size() < n + 1) return 0;
        double obvStart = 0, obvEnd = 0; boolean init = false;
        int from = k.size() - 1 - n;
        double running = 0;
        for (int i = 1; i < k.size(); i++) {
            double ch = k.get(i).c - k.get(i - 1).c;
            running += (ch > 0 ? k.get(i).v : ch < 0 ? -k.get(i).v : 0);
            if (i == from) { obvStart = running; init = true; }
        }
        obvEnd = running;
        if (!init || obvStart == 0) return 0;
        return (obvEnd - obvStart) / Math.abs(obvStart);
    }

    /** ROC (9) — Rate of Change in %. */
    static double roc(List<Candle> k, int n) {
        if (k.size() < n + 1) return 0;
        double prev = k.get(k.size() - 1 - n).c;
        if (prev == 0) return 0;
        return 100 * (k.get(k.size() - 1).c - prev) / prev;
    }

    /** Supertrend (10, 3) — returns [line, dir]; dir 1 = uptrend, -1 = downtrend. */
    static double[] supertrend(List<Candle> k) {
        int n = 10, from = Math.max(1, k.size() - 120);
        if (k.size() < n + 2) return null;
        double a = atr(k.subList(Math.max(0, k.size() - 120), k.size()), n);
        if (Double.isNaN(a) || a <= 0) return null;
        double prevUpper = Double.NaN, prevLower = Double.NaN, prevSt = Double.NaN;
        int prevDir = 1;
        for (int i = from; i < k.size(); i++) {
            Candle c = k.get(i);
            double mid = (c.h + c.l) / 2;
            double upper = mid + 3 * a, lower = mid - 3 * a;
            double prevClose = closeAt(k, i - 1);
            if (!Double.isNaN(prevUpper) && !Double.isNaN(prevClose)) {
                upper = (upper < prevUpper || prevClose > prevUpper) ? upper : prevUpper;
                lower = (lower > prevLower || prevClose < prevLower) ? lower : prevLower;
            }
            int dir;
            if (Double.isNaN(prevSt)) dir = 1;
            else if (prevSt == prevUpper) dir = (c.c > upper) ? 1 : -1;
            else dir = (c.c < lower) ? -1 : 1;
            double st = dir == 1 ? lower : upper;
            prevUpper = upper; prevLower = lower; prevSt = st; prevDir = dir;
        }
        return new double[]{prevSt, prevDir};
    }

    /** PSAR (Parabolic SAR) — returns sar value and direction [sar, dir]. */
    static double[] psar(List<Candle> k) {
        if (k.size() < 10) return null;
        boolean bull = k.get(0).c <= k.get(1).c;
        double sar = bull ? k.get(0).l : k.get(0).h;
        double ep = bull ? k.get(0).h : k.get(0).l;
        double af = 0.02;
        for (int i = 2; i < k.size(); i++) {
            Candle c = k.get(i);
            sar = sar + af * (ep - sar);
            if (bull) {
                if (c.l < sar) { bull = false; sar = ep; ep = c.l; af = 0.02; }
                else if (c.h > ep) { ep = c.h; af = Math.min(0.2, af + 0.02); }
            } else {
                if (c.h > sar) { bull = true; sar = ep; ep = c.h; af = 0.02; }
                else if (c.l < ep) { ep = c.l; af = Math.min(0.2, af + 0.02); }
            }
        }
        return new double[]{sar, bull ? 1 : -1};
    }

    /** Ichimoku — returns [tenkan, kijun, spanA, spanB] computed at current bar. */
    static double[] ichimoku(List<Candle> k) {
        if (k.size() < 52) return null;
        double[] hh = new double[k.size()], ll = new double[k.size()];
        for (int w = 0; w < k.size(); w++) {
            double h = -Double.MAX_VALUE, l = Double.MAX_VALUE;
            for (int i = Math.max(0, w - 51); i <= w; i++) { h = Math.max(h, k.get(i).h); l = Math.min(l, k.get(i).l); }
            hh[w] = h; ll[w] = l;
        }
        int last = k.size() - 1;
        double tenkan = mid(hh, ll, last, 9), kijun = mid(hh, ll, last, 26);
        double spanA = (tenkan + kijun) / 2;
        double spanB = mid(hh, ll, last, 52);
        return new double[]{tenkan, kijun, spanA, spanB};
    }

    private static double mid(double[] hh, double[] ll, int at, int w) {
        double h = -Double.MAX_VALUE, l = Double.MAX_VALUE;
        for (int i = Math.max(0, at - w + 1); i <= at; i++) { h = Math.max(h, hh[i]); l = Math.min(l, ll[i]); }
        return (h + l) / 2;
    }

    /** Aroon (14) — returns [up, down] oscillators 0..100. */
    static double[] aroon(List<Candle> k, int n) {
        if (k.size() < n + 1) return null;
        int hi = 0, lo = 0;
        double h = -Double.MAX_VALUE, l = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) {
            if (k.get(i).h >= h) { h = k.get(i).h; hi = i; }
            if (k.get(i).l <= l) { l = k.get(i).l; lo = i; }
        }
        int last = k.size() - 1;
        return new double[]{100.0 * (n - (last - hi)) / n, 100.0 * (n - (last - lo)) / n};
    }

    /** TRIX (15) — triple smoothed EMA rate of change. */
    static double trix(List<Candle> k) {
        double[] e1 = emaSeries(k, 15);
        if (e1 == null) return Double.NaN;
        double[] e2 = new double[e1.length], e3 = new double[e1.length];
        double mult = 2.0 / 16;
        double a = e1[14], b = e1[14]; boolean i2 = false, i3 = false;
        for (int i = 0; i < e1.length; i++) {
            a = i2 ? (e1[i] - a) * mult + a : e1[i]; i2 = true; e2[i] = a;
            b = i3 ? (e2[i] - b) * mult + b : e2[i]; i3 = true; e3[i] = b;
        }
        int last = e3.length - 1;
        if (last < 1 || e3[last - 1] == 0) return 0;
        return 100 * (e3[last] - e3[last - 1]) / e3[last - 1];
    }

    /** Keltner Channel (20, 2) — returns [mid, upper, lower]. */
    static double[] keltner(List<Candle> k, int n, double mult) {
        if (k.size() < n + 1) return null;
        double[] e = emaSeries(k, n);
        if (e == null) return null;
        double a = atr(k, n);
        if (Double.isNaN(a)) return null;
        double mid = e[e.length - 1];
        return new double[]{mid, mid + mult * a, mid - mult * a};
    }

    /** Ultimate Oscillator (7,14,28). */
    static double ultimateOsc(List<Candle> k) {
        if (k.size() < 29) return Double.NaN;
        double bp1 = 0, tr1 = 0, bp2 = 0, tr2 = 0, bp3 = 0, tr3 = 0;
        for (int i = k.size() - 28; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double trueLow = Math.min(c.l, p.c);
            double bp = c.c - trueLow;
            double tr = Math.max(c.h - trueLow, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
            if (i >= k.size() - 7) { bp1 += bp; tr1 += tr; }
            if (i >= k.size() - 14) { bp2 += bp; tr2 += tr; }
            bp3 += bp; tr3 += tr;
        }
        if (tr1 == 0 || tr2 == 0 || tr3 == 0) return 50;
        return 100 * (4 * bp1 / tr1 + 2 * bp2 / tr2 + bp3 / tr3) / 7;
    }

    /** Helper: previous close relative to candle list (used by Supertrend). */
    private static double closeAt(List<Candle> k, int idx) {
        return (idx >= 0 && idx < k.size()) ? k.get(idx).c : Double.NaN;
    }

    // ================== INDICATORS v5.9 — PDF ENCYCLOPEDIA SUITE ==================
    // Full library from the Complete Trading Encyclopedia PDF: every major
    // moving-average family, trend/momentum/volume indicator, pivot + fib
    // geometry, candlestick patterns, chart/harmonic patterns and SMC concepts.

    /** WMA — linearly weighted MA. */
    static double wma(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double num = 0, den = 0;
        for (int i = 0; i < n; i++) { double w = n - i; num += k.get(k.size() - n + i).c * w; den += w; }
        return num / den;
    }

    /** SMMA / RMA / Wilder MA — smoothed MA used inside RSI/ATR. */
    static double smma(List<Candle> k, int n) {
        if (k.size() < n + 3) return Double.NaN;
        double s = 0;
        for (int i = k.size() - 2 * n; i < k.size() - n; i++) s += k.get(i).c;
        double e = s / n;
        for (int i = k.size() - n; i < k.size(); i++) e = (e * (n - 1) + k.get(i).c) / n;
        return e;
    }

    /** HMA (Hull) — low-lag smooth MA, WMA(2*WMA(n/sqrt(n)) - WMA(n), sqrt(n)). */
    static double hma(List<Candle> k, int n) {
        if (k.size() < 2 * n) return Double.NaN;
        int sq = Math.max(2, (int) Math.sqrt(n));
        double w1 = wma(k, n), w2 = wma(k, n / 2);
        if (Double.isNaN(w1) || Double.isNaN(w2)) return Double.NaN;
        double raw = 2 * w2 - w1;
        // smooth raw over sqrt(n) recent values
        List<Double> raws = new ArrayList<>();
        for (int trim = 0; trim < sq; trim++) {
            List<Candle> kk = k.subList(0, k.size() - trim);
            double a = wma(kk, n), b = wma(kk, n / 2);
            if (Double.isNaN(a) || Double.isNaN(b)) break;
            raws.add(2 * b - a);
        }
        if (raws.size() < 2) return raw;
        double num = 0, den = 0;
        for (int i = 0; i < raws.size(); i++) { double w = raws.size() - i; num += raws.get(i) * w; den += w; }
        return num / den;
    }

    /** DEMA — double EMA, less lag. */
    static double dema(List<Candle> k, int n) {
        double[] e = emaSeries(k, n);
        if (e == null) return Double.NaN;
        List<Double> eOfE = new ArrayList<>();
        double m = 2.0 / (n + 1), ee = 0; boolean init = false;
        for (double v : e) { ee = init ? (v - ee) * m + ee : v; init = true; eOfE.add(ee); }
        return 2 * e[e.length - 1] - eOfE.get(eOfE.size() - 1);
    }

    /** TEMA — triple EMA. */
    static double tema(List<Candle> k, int n) {
        double[] e = emaSeries(k, n);
        if (e == null) return Double.NaN;
        double m = 2.0 / (n + 1);
        double[] e2 = new double[e.length]; double[] e3 = new double[e.length];
        double a = 0, b = 0; boolean i2 = false, i3 = false;
        for (int i = 0; i < e.length; i++) {
            a = i2 ? (e[i] - a) * m + a : e[i]; i2 = true; e2[i] = a;
            b = i3 ? (e2[i] - b) * m + b : e2[i]; i3 = true; e3[i] = b;
        }
        int last = e.length - 1;
        return 3 * e[last] - 3 * e2[last] + e3[last];
    }

    /** KAMA (Kaufman Adaptive MA) 10,2,30 — adapts to noise. */
    static double kama(List<Candle> k) {
        int n = 10, fast = 2, slow = 30;
        if (k.size() < n + slow / 2 + 2) return Double.NaN;
        double er, scfast = 2.0 / (fast + 1), scslow = 2.0 / (slow + 1);
        double kama_ = k.get(k.size() - n - 1).c;
        int from = k.size() - n;
        for (int i = from; i < k.size(); i++) {
            double change = Math.abs(k.get(i).c - k.get(i - n).c);
            double vol = 0;
            for (int j = i - n + 1; j <= i; j++) vol += Math.abs(k.get(j).c - k.get(j - 1).c);
            er = vol == 0 ? 0 : change / vol;
            double sc = Math.pow(er * (scfast - scslow) + scslow, 2);
            kama_ = kama_ + sc * (k.get(i).c - kama_);
        }
        return kama_;
    }

    /** ALMA (Arnaud Legoux) 9, 0.85, 6 — Gaussian weighted. */
    static double alma(List<Candle> k, int n, double offset, double sigma) {
        if (k.size() < n) return Double.NaN;
        double m = offset * (n - 1), s = n / sigma;
        double num = 0, den = 0;
        for (int i = 0; i < n; i++) {
            double w = Math.exp(-Math.pow(i - m, 2) / (2 * s * s));
            num += k.get(k.size() - n + i).c * w; den += w;
        }
        return den > 0 ? num / den : Double.NaN;
    }

    /** T3 (Tillson) 5, 0.7 — very smooth, v-factor 0.7. */
    static double t3(List<Candle> k, int n, double vf) {
        double[] e1 = emaSeries(k, n);
        if (e1 == null) return Double.NaN;
        double m = 2.0 / (n + 1);
        double[] e2 = new double[e1.length], e3 = new double[e1.length], e4 = new double[e1.length], e5 = new double[e1.length], e6 = new double[e1.length];
        double a = 0, b = 0, c = 0, d = 0, f = 0, g = 0;
        boolean i2 = false, i3 = false, i4 = false, i5 = false, i6 = false;
        for (int i = 0; i < e1.length; i++) {
            a = i2 ? (e1[i] - a) * m + a : e1[i]; i2 = true; e2[i] = a;
            b = i3 ? (e2[i] - b) * m + b : e2[i]; i3 = true; e3[i] = b;
            c = i4 ? (e3[i] - c) * m + c : e3[i]; i4 = true; e4[i] = c;
            d = i5 ? (e4[i] - d) * m + d : e4[i]; i5 = true; e5[i] = d;
            f = i6 ? (e5[i] - f) * m + f : e5[i]; i6 = true; e6[i] = f;
        }
        int last = e1.length - 1;
        double c1 = -vf * vf * vf, c2 = 3 * vf * vf + 3 * vf * vf * vf,
               c3 = -6 * vf * vf - 3 * vf - 3 * vf * vf * vf, c4 = 1 + 3 * vf + vf * vf * vf + 3 * vf * vf;
        return c1 * e6[last] + c2 * e5[last] + c3 * e4[last] + c4 * e3[last];
    }

    /** ZLEMA — zero-lag EMA(20). */
    static double zlema(List<Candle> k, int n) {
        if (k.size() < n + 2) return Double.NaN;
        double lag = (n - 1) / 2.0;
        List<Double> adj = new ArrayList<>();
        for (int i = 0; i < k.size(); i++) {
            int bi = i - (int) Math.round(lag);
            double base = bi >= 0 ? k.get(bi).c : k.get(0).c;
            adj.add(2 * k.get(i).c - base);
        }
        double m = 2.0 / (n + 1), e = 0; boolean init = false;
        for (double v : adj) { e = init ? (v - e) * m + e : v; init = true; }
        return e;
    }

    /** LSMA — linear regression (least squares) value. */
    static double lsma(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double sx = 0, sy = 0, sxy = 0, sxx = 0;
        for (int i = 0; i < n; i++) {
            double y = k.get(k.size() - n + i).c;
            sx += i; sy += y; sxy += i * y; sxx += i * i;
        }
        double d = n * sxx - sx * sx;
        if (d == 0) return Double.NaN;
        double slope = (n * sxy - sx * sy) / d;
        return (sy - slope * sx) / n + slope * (n - 1);
    }

    /** VWMA — volume weighted MA(20). */
    static double vwma(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double pv = 0, vv = 0;
        for (int i = k.size() - n; i < k.size(); i++) { pv += k.get(i).c * k.get(i).v; vv += k.get(i).v; }
        return vv > 0 ? pv / vv : Double.NaN;
    }

    /** McGinley Dynamic 14 — self-adjusting MA. */
    static double mcginley(List<Candle> k, int n) {
        if (k.size() < n + 5) return Double.NaN;
        double md = k.get(k.size() - n - 1).c;
        for (int i = k.size() - n; i < k.size(); i++) {
            double c = k.get(i).c;
            md = md + (c - md) / (n * Math.pow(c / Math.max(md, 1e-12), 4));
        }
        return md;
    }

    /** Donchian Channel (20) — [upper, mid, lower]. */
    static double[] donchian(List<Candle> k, int n) {
        if (k.size() < n) return null;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        return new double[]{hh, (hh + ll) / 2, ll};
    }

    /** Envelopes (20, 2.5%) — [lower, mid, upper]. */
    static double[] envelopes(List<Candle> k, int n, double pct) {
        if (k.size() < n) return null;
        double s = 0;
        for (int i = k.size() - n; i < k.size(); i++) s += k.get(i).c;
        double mid = s / n;
        return new double[]{mid * (1 - pct / 100), mid, mid * (1 + pct / 100)};
    }

    /** Standard Deviation (20). */
    static double stdev(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double sum = 0, sum2 = 0;
        for (int i = k.size() - n; i < k.size(); i++) { double c = k.get(i).c; sum += c; sum2 += c * c; }
        double mean = sum / n;
        return Math.sqrt(Math.max(0, sum2 / n - mean * mean));
    }

    /** Chandelier Exit (22, 3) — ATR trailing stop from highest high. */
    static double chandelier(List<Candle> k, int n, double mult) {
        if (k.size() < n + 1) return Double.NaN;
        double hh = -Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) hh = Math.max(hh, k.get(i).h);
        return hh - mult * atr(k, n);
    }

    /** Williams Fractals — last confirmed fractal [lastUp, lastDown] prices, -1 if none. */
    static double[] fractals(List<Candle> k) {
        double up = -1, dn = -1;
        for (int i = k.size() - 3; i >= 2; i--) {
            Candle c = k.get(i);
            if (up < 0 && c.h > k.get(i - 1).h && c.h > k.get(i - 2).h && c.h > k.get(i + 1).h && c.h > k.get(i + 2).h) up = c.h;
            if (dn < 0 && c.l < k.get(i - 1).l && c.l < k.get(i - 2).l && c.l < k.get(i + 1).l && c.l < k.get(i + 2).l) dn = c.l;
            if (up >= 0 && dn >= 0) break;
        }
        return new double[]{up, dn};
    }

    /** Vortex (14) — returns [viPlus, viMinus]. */
    static double[] vortex(List<Candle> k, int n) {
        if (k.size() < n + 1) return null;
        double vp = 0, vm = 0, tr = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            vp += Math.abs(c.h - p.l);
            vm += Math.abs(c.l - p.h);
            tr += Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
        }
        if (tr == 0) return null;
        return new double[]{vp / tr, vm / tr};
    }

    /** Mass Index (25) — range expansion reversal bulge 27/26.5. */
    static double massIndex(List<Candle> k) {
        int n = 9, sumN = 25;
        if (k.size() < n + sumN + 1) return Double.NaN;
        double[] rng = new double[k.size()];
        for (int i = 0; i < k.size(); i++) rng[i] = k.get(i).h - k.get(i).l;
        double sum = 0;
        List<Double> e1s = new ArrayList<>(), e2s = new ArrayList<>();
        double e1 = rng[0], e2 = rng[0];
        double m1 = 2.0 / (n + 1);
        for (int i = 0; i < k.size(); i++) {
            e1 = (rng[i] - e1) * m1 + e1;
            e2 = (e1 - e2) * m1 + e2;
            e1s.add(e1); e2s.add(e2);
        }
        for (int i = k.size() - sumN; i < k.size(); i++) {
            double ratio = e2s.get(i) != 0 ? e1s.get(i) / e2s.get(i) : 1;
            sum += ratio;
        }
        return sum;
    }

    /** Alligator (13/8, 8/5, 5/3) — returns [jaw, teeth, lips]. */
    static double[] alligator(List<Candle> k) {
        if (k.size() < 40) return null;
        double jaw = smma(k, 13), teeth = smma(k, 8), lips = smma(k, 5);
        return new double[]{jaw, teeth, lips};
    }

    /** Choppiness Index (14) — above 61.8 = choppy, below 38.2 = trending. */
    static double choppiness(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double sumTr = 0, hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            sumTr += Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
            hh = Math.max(hh, c.h); ll = Math.min(ll, c.l);
        }
        if (sumTr <= 0 || hh - ll <= 0) return 50;
        return 100 * Math.log10(sumTr / (hh - ll)) / Math.log10(n);
    }

    /** Schaff Trend Cycle (23, 50, 10). */
    static double schaff(List<Candle> k) {
        double[] e12 = emaSeries(k, 23), e26 = emaSeries(k, 50);
        if (e12 == null || e26 == null) return Double.NaN;
        int n = k.size();
        double[] macdLine = new double[n];
        for (int i = 0; i < n; i++) macdLine[i] = e12[i] - e26[i];
        // stochastic of MACD over 10 bars, twice smoothed
        double st = stochOfSeries(macdLine, n - 1, 10);
        // smooth with EMA3 then stoch again
        double stEma = st;
        if (n >= 14) {
            double[] s1 = new double[n];
            double m = 2.0 / 4;
            double e = macdLine[n - 11]; boolean init = false;
            for (int i = n - 11; i < n; i++) { e = init ? (macdLine[i] - e) * m + e : macdLine[i]; init = true; s1[i] = e; }
            st = stochOfSeries(s1, n - 1, 10);
        }
        return st;
    }

    private static double stochOfSeries(double[] v, int at, int n) {
        if (at - n + 1 < 0) return 50;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = at - n + 1; i <= at; i++) { hh = Math.max(hh, v[i]); ll = Math.min(ll, v[i]); }
        if (hh == ll) return 50;
        return 100 * (v[at] - ll) / (hh - ll);
    }

    /** KST (Know Sure Thing) 10-15-20-30 ROC weighted. */
    static double kst(List<Candle> k) {
        if (k.size() < 35) return Double.NaN;
        double r10 = roc(k, 10), r15 = roc(k, 15), r20 = roc(k, 20), r30 = roc(k, 30);
        return r10 + 2 * r15 + 3 * r20 + 4 * r30;
    }

    /** Coppock Curve (14, 11, 10) — long-term bottoms. */
    static double coppock(List<Candle> k) {
        if (k.size() < 32) return Double.NaN;
        double r14 = roc(k, 14), r11 = roc(k, 11);
        // WMA10 of (roc14+roc11) approximated on the last 10 computed pairs
        double num = 0, den = 0;
        for (int i = 1; i <= 10; i++) {
            if (k.size() < 32 + i) break;
            double a = roc(k.subList(0, k.size() - i + 1), 14), b = roc(k.subList(0, k.size() - i + 1), 11);
            if (Double.isNaN(a) || Double.isNaN(b)) break;
            double w = 11 - i; num += (a + b) * w; den += w;
        }
        return den > 0 ? num / den : r14 + r11;
    }

    /** APO / PPO (12, 26) — price/percentage oscillator. */
    static double[] apoPpo(List<Candle> k) {
        double[] e12 = emaSeries(k, 12), e26 = emaSeries(k, 26);
        if (e12 == null || e26 == null) return null;
        int last = k.size() - 1;
        double apo = e12[last] - e26[last];
        double ppo = e26[last] != 0 ? 100 * apo / e26[last] : 0;
        return new double[]{apo, ppo};
    }

    /** DPO (20) — detrended price oscillator. */
    static double dpo(List<Candle> k, int n) {
        if (k.size() < n + n / 2 + 1) return Double.NaN;
        int shift = n / 2 + 1;
        double s = 0;
        for (int i = k.size() - n - shift; i < k.size() - shift; i++) s += k.get(i).c;
        double sma = s / n;
        return k.get(k.size() - 1).c - sma;
    }

    /** Awesome Oscillator (5, 34) — median price SMA difference. */
    static double awesomeOsc(List<Candle> k) {
        if (k.size() < 34) return Double.NaN;
        double s5 = 0, s34 = 0;
        for (int i = k.size() - 5; i < k.size(); i++) s5 += (k.get(i).h + k.get(i).l) / 2;
        for (int i = k.size() - 34; i < k.size(); i++) s34 += (k.get(i).h + k.get(i).l) / 2;
        return s5 / 5 - s34 / 34;
    }

    /** TSI (25, 13) — double smoothed momentum, -100..100. */
    static double tsi(List<Candle> k) {
        int longN = 25, shortN = 13;
        if (k.size() < longN + shortN + 2) return Double.NaN;
        double m1 = 2.0 / (longN + 1), m2 = 2.0 / (shortN + 1);
        double em = 0, ea = 0, em2 = 0, ea2 = 0; boolean i1 = false, i2 = false;
        for (int i = 1; i < k.size(); i++) {
            double mom = k.get(i).c - k.get(i - 1).c;
            em = i1 ? (mom - em) * m1 + em : mom; i1 = true;
            ea = i1 ? (Math.abs(mom) - ea) * m1 + ea : Math.abs(mom);
            em2 = i2 ? (em - em2) * m2 + em2 : em; i2 = true;
            ea2 = (ea - ea2) * m2 + ea2;
        }
        return ea2 != 0 ? 100 * em2 / ea2 : 0;
    }

    /** CMO (Chande Momentum, 14) — -100..100. */
    static double cmo(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double up = 0, dn = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            double ch = k.get(i).c - k.get(i - 1).c;
            if (ch > 0) up += ch; else dn -= ch;
        }
        if (up + dn == 0) return 0;
        return 100 * (up - dn) / (up + dn);
    }

    /** Fisher Transform (9). */
    static double fisher(List<Candle> k) {
        int n = 9;
        if (k.size() < n + 1) return Double.NaN;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double mid = (hh + ll) / 2;
        double pos = hh == ll ? 0 : 2 * ((k.get(k.size() - 1).c - mid) / (hh - ll)) - 1;
        pos = Math.max(-0.999, Math.min(0.999, pos));
        return 0.5 * Math.log((1 + pos) / (1 - pos));
    }

    /** DeMarker (14) — 0.7 overbought / 0.3 oversold. */
    static double deMarker(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double max = 0, min = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            max += Math.max(0, c.h - p.h);
            min += Math.max(0, p.l - c.l);
        }
        if (max + min == 0) return 0.5;
        return max / (max + min);
    }

    /** Stochastic Momentum Index (10, 3, 3). */
    static double smi(List<Candle> k) {
        int n = 10;
        if (k.size() < n * 2 + 5) return Double.NaN;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - n; i < k.size(); i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double mid = (hh + ll) / 2;
        double c = k.get(k.size() - 1).c;
        double raw = hh == ll ? 0 : 100 * (c - mid) / (hh - ll);
        // double EMA3 smoothing approx
        return 0.7 * raw + 0.3 * (k.size() > 1 && k.get(k.size() - 1).c > k.get(k.size() - 2).c ? raw * 0.9 : raw * 1.1);
    }

    /** Balance of Power (14) — (close-open)/(high-low). */
    static double bop(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double s = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i);
            s += (c.h - c.l) != 0 ? (c.c - c.o) / (c.h - c.l) : 0;
        }
        return s / n;
    }

    /** Laguerre RSI (gamma 0.5) — 0..1. */
    static double laguerreRsi(List<Candle> k) {
        if (k.size() < 8) return Double.NaN;
        double g = 0.5;
        double l0 = 0, l1 = 0, l2 = 0, l3 = 0;
        for (int i = Math.max(0, k.size() - 60); i < k.size(); i++) {
            double c = k.get(i).c;
            double l0p = l0;
            l0 = (1 - g) * c + g * l0;
            l1 = -g * l0 + l0p + g * l1;
            double l1p = l1;
            l1 = Math.max(0, l1);
            l2 = -g * l1 + l1p + g * l2;
            double l2p = l2;
            l2 = Math.max(0, l2);
            l3 = -g * l2 + l2p + g * l3;
            l3 = Math.max(0, l3);
        }
        double cu = 0, cd = 0;
        if (l0 >= l1) cu += l0 - l1; else cd += l1 - l0;
        if (l1 >= l2) cu += l1 - l2; else cd += l2 - l1;
        if (l2 >= l3) cu += l2 - l3; else cd += l3 - l2;
        return (cu + cd) != 0 ? cu / (cu + cd) : 0.5;
    }

    /** RVI (Relative Vigor Index, 10) — close vs open vs range. */
    static double rvi(List<Candle> k, int n) {
        // v1.0 BUGFIX: the old guard (n+4) allowed i-3 to reach index -1/-2 on short
        // series and crash with ArrayIndexOutOfBoundsException. Need n+7 candles so
        // the earliest access k.get(i-3) stays at index >= 0.
        if (k.size() < n + 7) return Double.NaN;
        double a = 0, b = 0, c = 0, d = 0, nm = 0, dm = 0;
        for (int i = k.size() - n - 3; i < k.size(); i++) {
            double co = k.get(i).c - k.get(i).o;
            double hi = k.get(i).h - k.get(i).l;
            double w = 1;
            a = co * 1; b = k.get(i - 1).c - k.get(i - 1).o; c = k.get(i - 2).c - k.get(i - 2).o; d = k.get(i - 3).c - k.get(i - 3).o;
            double num = (a + 2 * b + 2 * c + d) / 6;
            double x1 = hi, x2 = k.get(i - 1).h - k.get(i - 1).l, x3 = k.get(i - 2).h - k.get(i - 2).l, x4 = k.get(i - 3).h - k.get(i - 3).l;
            double den = (x1 + 2 * x2 + 2 * x3 + x4) / 6;
            nm += num; dm += den;
        }
        return dm != 0 ? nm / dm : 0;
    }

    /** Elder Ray — [bullPower, bearPower] vs EMA13. */
    static double[] elderRay(List<Candle> k) {
        double e = ema(k, 13);
        if (Double.isNaN(e)) return null;
        Candle c = k.get(k.size() - 1);
        return new double[]{c.h - e, c.l - e};
    }

    /** Accumulation/Distribution line slope (20) — PDF 2.5. */
    static double adSlope(List<Candle> k, int n) {
        if (k.size() < n + 1) return 0;
        double start = 0, end = 0; boolean init = false; double run = 0;
        int from = k.size() - 1 - n;
        for (int i = 0; i < k.size(); i++) {
            Candle c = k.get(i);
            double range = c.h - c.l;
            double clv = range != 0 ? ((c.c - c.l) - (c.h - c.c)) / range : 0;
            run += clv * c.v;
            if (i == from) { start = run; init = true; }
        }
        end = run;
        if (!init) return 0;
        double base = Math.max(Math.abs(start), 1e-9);
        return (end - start) / base;
    }

    /** Chaikin Money Flow (20). */
    static double cmf(List<Candle> k, int n) {
        if (k.size() < n) return Double.NaN;
        double mfv = 0, vol = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i);
            double range = c.h - c.l;
            double clv = range != 0 ? ((c.c - c.l) - (c.h - c.c)) / range : 0;
            mfv += clv * c.v; vol += c.v;
        }
        return vol != 0 ? mfv / vol : 0;
    }

    /** Chaikin Oscillator (3, 10) — EMA3 - EMA10 of A/D. */
    static double chaikinOsc(List<Candle> k) {
        if (k.size() < 40) return Double.NaN;
        double m3 = 2.0 / 4, m10 = 2.0 / 11;
        double e3 = 0, e10 = 0; boolean i3 = false, i10 = false;
        for (int i = 0; i < k.size(); i++) {
            Candle c = k.get(i);
            double range = c.h - c.l;
            double clv = range != 0 ? ((c.c - c.l) - (c.h - c.c)) / range : 0;
            double ad = clv * c.v;
            e3 = i3 ? (ad - e3) * m3 + e3 : ad; i3 = true;
            e10 = i10 ? (ad - e10) * m10 + e10 : ad; i10 = true;
        }
        return e3 - e10;
    }

    /** Force Index (13) — price change × volume, normalized. */
    static double forceIndex(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double s = 0;
        for (int i = k.size() - n; i < k.size(); i++) s += (k.get(i).c - k.get(i - 1).c) * k.get(i).v;
        double avgV = 0;
        for (int i = k.size() - n; i < k.size(); i++) avgV += k.get(i).v;
        return avgV > 0 ? s / avgV : 0;
    }

    /** Ease of Movement (14). */
    static double eom(List<Candle> k, int n) {
        if (k.size() < n + 1) return Double.NaN;
        double s = 0;
        for (int i = k.size() - n; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double midMove = ((c.h + c.l) / 2) - ((p.h + p.l) / 2);
            double boxRatio = c.v > 0 ? (c.v / 10000) / Math.max(0.0001, (c.h - c.l)) : 0;
            s += boxRatio != 0 ? midMove / boxRatio : 0;
        }
        return s / n;
    }

    /** Klinger Volume Oscillator (34, 55, 13) — simplified sign-based. */
    static double klinger(List<Candle> k) {
        if (k.size() < 56) return Double.NaN;
        double e34 = 0, e55 = 0; boolean i34 = false, i55 = false;
        double m34 = 2.0 / 35, m55 = 2.0 / 56;
        for (int i = 1; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            double trend = (c.h + c.l + c.c) > (p.h + p.l + p.c) ? c.v : -c.v;
            e34 = i34 ? (trend - e34) * m34 + e34 : trend; i34 = true;
            e55 = i55 ? (trend - e55) * m55 + e55 : trend; i55 = true;
        }
        return e34 - e55;
    }

    /** PVT slope — price volume trend cumulative change (20). */
    static double pvtSlope(List<Candle> k, int n) {
        if (k.size() < n + 1) return 0;
        double start = 0, run = 0; boolean init = false;
        int from = k.size() - 1 - n;
        for (int i = 1; i < k.size(); i++) {
            Candle c = k.get(i), p = k.get(i - 1);
            if (p.c != 0) run += (c.c - p.c) / p.c * c.v;
            if (i == from) { start = run; init = true; }
        }
        if (!init) return 0;
        double base = Math.max(Math.abs(start), 1e-9);
        return (run - start) / base;
    }

    /** Volume Oscillator (5, 10) — fast/slow volume MA %. */
    static double volumeOsc(List<Candle> k) {
        if (k.size() < 11) return Double.NaN;
        double f = 0, s = 0;
        for (int i = k.size() - 5; i < k.size(); i++) f += k.get(i).v;
        for (int i = k.size() - 10; i < k.size(); i++) s += k.get(i).v;
        f /= 5; s /= 10;
        return s != 0 ? 100 * (f - s) / s : 0;
    }

    /** Pivot Points (Classic) — [pp, r1, r2, r3, s1, s2, s3] from previous session. */
    static double[] pivotPoints(List<Candle> k) {
        if (k.size() < 30) return null;
        // use last 15 bars as "previous session" proxy on 1m
        double h = -Double.MAX_VALUE, l = Double.MAX_VALUE, c = 0;
        for (int i = k.size() - 15; i < k.size() - 1; i++) { h = Math.max(h, k.get(i).h); l = Math.min(l, k.get(i).l); }
        c = k.get(k.size() - 2).c;
        double pp = (h + l + c) / 3;
        return new double[]{pp, 2 * pp - l, pp + (h - l), h + 2 * (pp - l), 2 * pp - h, pp - (h - l), l - 2 * (h - pp)};
    }

    /** Fibonacci retracement of last swing — [23.6, 38.2, 50, 61.8, 78.6] levels + swing dir. */
    static double[] fibLevels(List<Candle> k) {
        if (k.size() < 30) return null;
        int look = 30;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE; int hi = -1, lo = -1;
        for (int i = k.size() - look; i < k.size(); i++) {
            if (k.get(i).h > hh) { hh = k.get(i).h; hi = i; }
            if (k.get(i).l < ll) { ll = k.get(i).l; lo = i; }
        }
        boolean upSwing = hi > lo; // low came first = uptrend swing
        double range = hh - ll;
        if (range <= 0) return null;
        double[] out = new double[6];
        if (upSwing) {
            out[0] = hh - 0.236 * range; out[1] = hh - 0.382 * range; out[2] = hh - 0.5 * range;
            out[3] = hh - 0.618 * range; out[4] = hh - 0.786 * range; out[5] = 1;
        } else {
            out[0] = ll + 0.236 * range; out[1] = ll + 0.382 * range; out[2] = ll + 0.5 * range;
            out[3] = ll + 0.618 * range; out[4] = ll + 0.786 * range; out[5] = -1;
        }
        return out;
    }

    /** Candlestick pattern detector — returns name + direction (+1 bull / -1 bear). */
    static Object[] candlePattern(List<Candle> k) {
        if (k.size() < 4) return null;
        Candle c = k.get(k.size() - 1), p = k.get(k.size() - 2), p2 = k.get(k.size() - 3);
        double body = Math.abs(c.c - c.o), range = Math.max(1e-12, c.h - c.l);
        double bodyP = Math.abs(p.c - p.o), rangeP = Math.max(1e-12, p.h - p.l);
        boolean bullC = c.c > c.o, bearC = c.c < c.o;
        // Engulfing
        if (bullC && p.c < p.o && c.c > p.o && c.o < p.c && body > bodyP) return new Object[]{"Bullish Engulfing", 1};
        if (bearC && p.c > p.o && c.c < p.o && c.o > p.c && body > bodyP) return new Object[]{"Bearish Engulfing", -1};
        // Hammer / Shooting Star
        double lowerWick = Math.min(c.c, c.o) - c.l, upperWick = c.h - Math.max(c.c, c.o);
        if (lowerWick > 2 * body && upperWick < body * 0.5 && bodyP > rangeP * 0.6 && p.c < p.o)
            return new Object[]{"Hammer", 1};
        if (upperWick > 2 * body && lowerWick < body * 0.5 && bodyP > rangeP * 0.6 && p.c > p.o)
            return new Object[]{"Shooting Star", -1};
        // Doji at extremes
        if (body < range * 0.1) {
            if (p.c < p.o) return new Object[]{"Doji (after down)", 1};
            if (p.c > p.o) return new Object[]{"Doji (after up)", -1};
        }
        // Morning / Evening star
        boolean smallMid = bodyP < rangeP * 0.35;
        if (p2.c < p2.o && smallMid && bullC && c.c > (p2.c + p2.o) / 2) return new Object[]{"Morning Star", 1};
        if (p2.c > p2.o && smallMid && bearC && c.c < (p2.c + p2.o) / 2) return new Object[]{"Evening Star", -1};
        // Three soldiers / crows
        if (k.size() >= 4) {
            Candle p3 = k.get(k.size() - 4);
            if (bullC && p.c > p.o && p2.c > p2.o && p3.c > p3.o && c.c > p.c && p.c > p2.c && p2.c > p3.c)
                return new Object[]{"Three White Soldiers", 1};
            if (bearC && p.c < p.o && p2.c < p2.o && p3.c < p3.o && c.c < p.c && p.c < p2.c && p2.c < p3.c)
                return new Object[]{"Three Black Crows", -1};
        }
        // Marubozu
        if (body > range * 0.92) return new Object[]{bullC ? "Bullish Marubozu" : "Bearish Marubozu", bullC ? 1 : -1};
        // Piercing / Dark Cloud
        double midP = (p.c + p.o) / 2;
        if (bullC && p.c < p.o && c.c > midP && c.o < p.c) return new Object[]{"Piercing Line", 1};
        if (bearC && p.c > p.o && c.c < midP && c.o > p.c) return new Object[]{"Dark Cloud Cover", -1};
        // Inside / Outside bar
        if (c.h < p.h && c.l > p.l) return new Object[]{"Inside Bar", p.c > p.o ? 1 : -1};
        if (c.h > p.h && c.l < p.l) return new Object[]{"Outside Bar", bullC ? 1 : -1};
        return null;
    }

    /** Harmonic pattern scanner (Gartley/Bat/Butterfly/Crab) on last 5 pivots. */
    static Object[] harmonicPattern(List<Candle> k) {
        if (k.size() < 60) return null;
        // find 5 pivots (X, A, B, C, D) over last 60 bars via zigzag-ish extremes
        int look = 60;
        List<Integer> pivots = new ArrayList<>();
        int w = 6;
        for (int i = k.size() - look + w; i < k.size() - w; i++) {
            boolean isHigh = true, isLow = true;
            for (int j = i - w; j <= i + w; j++) {
                if (j == i || j < 0 || j >= k.size()) continue;
                if (k.get(j).h >= k.get(i).h) isHigh = false;
                if (k.get(j).l <= k.get(i).l) isLow = false;
            }
            if (isHigh || isLow) {
                if (pivots.isEmpty() || i - pivots.get(pivots.size() - 1) > w) pivots.add(i);
            }
        }
        if (pivots.size() < 5) return null;
        int n = pivots.size();
        int x = pivots.get(n - 5), a = pivots.get(n - 4), b = pivots.get(n - 3), c = pivots.get(n - 2), d = pivots.get(n - 1);
        double xa = Math.abs(k.get(a).c - k.get(x).c);
        double ab = Math.abs(k.get(b).c - k.get(a).c);
        double bc = Math.abs(k.get(c).c - k.get(b).c);
        double cd = Math.abs(k.get(d).c - k.get(c).c);
        if (xa <= 0 || bc <= 0) return null;
        double abRatio = ab / xa, cdRatio = bc != 0 ? cd / bc : 0;
        boolean bull = k.get(a).c > k.get(x).c; // X low -> A high = bull harmonic (buy at D)
        String name = null;
        if (Math.abs(abRatio - 0.618) < 0.06 && Math.abs(cdRatio - 1.272) < 0.2) name = "Gartley";
        else if (abRatio >= 0.382 && abRatio <= 0.5 && Math.abs(cdRatio - 1.618) < 0.25) name = "Bat";
        else if (Math.abs(abRatio - 0.786) < 0.06 && cdRatio >= 1.27 && cdRatio <= 1.9) name = "Butterfly";
        else if (abRatio >= 0.382 && abRatio <= 0.618 && cdRatio >= 1.5 && cdRatio <= 2.6) name = "Crab";
        if (name == null) return null;
        return new Object[]{name, bull ? 1 : -1};
    }

    /** Fair Value Gap (FVG / imbalance) — 3-candle gap; returns dir to fill (+1 gap below = buy). */
    static int fvg(List<Candle> k) {
        if (k.size() < 4) return 0;
        Candle c1 = k.get(k.size() - 3), c3 = k.get(k.size() - 1);
        // bullish FVG: c1.high < c3.low -> price tends to revisit (gap acts as support once filled)
        if (c1.h < c3.l) return 1;
        // bearish FVG: c1.low > c3.high
        if (c1.l > c3.h) return -1;
        return 0;
    }

    /** Break of Structure / CHoCH — HH/HL trend vs LH/LL. */
    static int bosVoteCalc(List<Candle> k) {
        if (k.size() < 40) return 0;
        double[] fr = fractals(k);
        if (fr == null || fr[0] < 0 || fr[1] < 0) return 0;
        double c = k.get(k.size() - 1).c;
        // BOS up: close breaks last swing high; BOS down: close breaks last swing low
        if (c > fr[0]) return 1;
        if (c < fr[1]) return -1;
        return 0;
    }

    /** Liquidity sweep / stop hunt — wick beyond prior extreme, close back inside. */
    static int sweepVoteCalc(List<Candle> k) {
        if (k.size() < 25) return 0;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - 25; i < k.size() - 1; i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        Candle c = k.get(k.size() - 1);
        if (c.h > hh && c.c < hh) return -1;  // swept buy-side liquidity -> sell
        if (c.l < ll && c.c > ll) return 1;   // swept sell-side liquidity -> buy
        return 0;
    }

    // ================== STRATEGIES (10) ==================
    /** vote: +1 buy, -1 sell, 0 neutral */
    /** 1. EMA 9/21 — v1.1: votes on CURRENT trend state (alignment), not just the rare
     *  crossover bar. In the old build this strategy stayed silent on ~99% of candles,
     *  starving the participation gate. */
    private int emaCross(List<Candle> k) {
        double e9 = ema(k, 9), e21 = ema(k, 21);
        if (Double.isNaN(e9) || Double.isNaN(e21)) return 0;
        if (e9 > e21) return 1;
        if (e9 < e21) return -1;
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
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - 16; i < k.size() - 1; i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double c = k.get(k.size() - 1).c;
        if (c > hh) return 1;
        if (c < ll) return -1;
        return 0;
    }

    // ---- v5.8 new strategy votes ----

    /** 6. Supertrend — v1.1: votes on the CURRENT regime (direction), not only on the
     *  rare flip bar. The regime itself is the signal; flips are just regime changes. */
    private int supertrendVote(List<Candle> k) {
        double[] st = supertrend(k);
        if (st == null) return 0;
        if (st[1] > 0) return 1;   // bullish regime
        if (st[1] < 0) return -1;  // bearish regime
        return 0;
    }

    /** 7. Ichimoku — price vs cloud + Tenkan/Kijun alignment. */
    private int ichimokuVote(List<Candle> k) {
        double[] i = ichimoku(k);
        if (i == null) return 0;
        double c = k.get(k.size() - 1).c;
        boolean aboveCloud = c > Math.max(i[2], i[3]);
        boolean belowCloud = c < Math.min(i[2], i[3]);
        boolean tkBull = i[0] > i[1], tkBear = i[0] < i[1];
        if (aboveCloud && tkBull) return 1;
        if (belowCloud && tkBear) return -1;
        return 0;
    }

    /** 8. ADX trend filter — trade strong trends only (ADX>25, DI dominance). */
    private int adxTrendVote(List<Candle> k) {
        double[] a = adx(k, 14);
        if (a == null) return 0;
        if (a[0] < 25) return 0; // no trade in chop
        if (a[1] > a[2] + 3) return 1;   // +DI dominant — uptrend
        if (a[2] > a[1] + 3) return -1;  // -DI dominant — downtrend
        return 0;
    }

    /** 9. CCI + Williams %R momentum extreme combo. */
    private int cciWilliamsVote(List<Candle> k) {
        double c = cci(k, 20), w = williamsR(k, 14);
        if (Double.isNaN(c) || Double.isNaN(w)) return 0;
        if (c < -100 && w < -80) return 1;   // oversold extreme
        if (c > 100 && w > -20) return -1;   // overbought extreme
        return 0;
    }

    /** 10. MFI volume flow + OBV accumulation. */
    private int mfiObvVote(List<Candle> k) {
        double m = mfi(k, 14);
        double obv = obvSlope(k, 20);
        if (Double.isNaN(m)) return 0;
        if (m < 20 && obv > 0) return 1;     // oversold but accumulating
        if (m > 80 && obv < 0) return -1;    // overbought and distributing
        return 0;
    }

    /** 11. PSAR + Aroon trend confirmation. */
    private int psarAroonVote(List<Candle> k) {
        double[] p = psar(k);
        double[] a = aroon(k, 14);
        if (p == null || a == null) return 0;
        boolean bull = p[1] > 0 && a[0] > 55 && a[0] > a[1];
        boolean bear = p[1] < 0 && a[1] > 55 && a[1] > a[0];
        return bull ? 1 : bear ? -1 : 0;
    }

    /** 12. StochRSI fast momentum trigger. */
    private int stochRsiVote(List<Candle> k) {
        double[] s = stochRsi(k);
        if (s == null) return 0;
        if (s[0] < 20 && s[0] > s[1]) return 1;   // rising from oversold
        if (s[0] > 80 && s[0] < s[1]) return -1;  // falling from overbought
        return 0;
    }

    // ---- v5.9 PDF encyclopedia votes (13-35) ----

    /** 13. Candlestick pattern vote — engulfing/hammer/star/soldiers etc. */
    private int candleVote(List<Candle> k) {
        Object[] p = candlePattern(k);
        if (p == null) return 0;
        // only trust reversal candles at extreme locations
        double r = rsi(k, 14);
        if (Double.isNaN(r)) return 0;
        int dir = (Integer) p[1];
        if (dir > 0 && r < 45) return 1;
        if (dir < 0 && r > 55) return -1;
        return 0;
    }

    /** 14. Donchian (20) channel breakout — Turtle rule. */
    private int donchianVote(List<Candle> k) {
        double[] d = donchian(k, 20);
        if (d == null) return 0;
        double c = k.get(k.size() - 1).c;
        if (c >= d[0]) return 1;   // closing at/above 20-bar high
        if (c <= d[2]) return -1;  // closing at/below 20-bar low
        return 0;
    }

    /** 15. Hull MA slope flip. */
    private int hullVote(List<Candle> k) {
        double h = hma(k, 21);
        if (Double.isNaN(h)) return 0;
        double hPrev = hma(k.subList(0, k.size() - 1), 21);
        if (Double.isNaN(hPrev)) return 0;
        if (hPrev <= h && hma(k.subList(0, k.size() - 2), 21) > hPrev) return 0; // need consistent turn
        if (h > hPrev && k.get(k.size() - 1).c > h) return 1;
        if (h < hPrev && k.get(k.size() - 1).c < h) return -1;
        return 0;
    }

    /** 16. KAMA adaptive trend. */
    private int kamaVote(List<Candle> k) {
        double km = kama(k);
        if (Double.isNaN(km)) return 0;
        double c = k.get(k.size() - 1).c;
        double kmPrev = kama(k.subList(0, k.size() - 1));
        if (Double.isNaN(kmPrev)) return 0;
        if (c > km && km > kmPrev) return 1;
        if (c < km && km < kmPrev) return -1;
        return 0;
    }

    /** 17. Vortex (14) — VI+ vs VI-. */
    private int vortexVote(List<Candle> k) {
        double[] v = vortex(k, 14);
        if (v == null) return 0;
        if (v[0] > v[1] * 1.05) return 1;
        if (v[1] > v[0] * 1.05) return -1;
        return 0;
    }

    /** 18. Alligator 13/8/5 alignment + open mouth. */
    private int alligatorVote(List<Candle> k) {
        double[] a = alligator(k);
        if (a == null) return 0;
        double c = k.get(k.size() - 1).c;
        boolean bull = c > a[0] && a[2] > a[1] && a[1] > a[0];
        boolean bear = c < a[0] && a[2] < a[1] && a[1] < a[0];
        return bull ? 1 : bear ? -1 : 0;
    }

    /** 19. TSI (25,13) sign + rising. */
    private int tsiVote(List<Candle> k) {
        double t = tsi(k);
        if (Double.isNaN(t)) return 0;
        double tPrev = tsi(k.subList(0, k.size() - 1));
        if (Double.isNaN(tPrev)) return 0;
        if (t > 0 && t > tPrev) return 1;
        if (t < 0 && t < tPrev) return -1;
        return 0;
    }

    /** 20. CMO (14) extremes reversal. */
    private int cmoVote(List<Candle> k) {
        double m = cmo(k, 14);
        if (Double.isNaN(m)) return 0;
        if (m < -50) return 1;
        if (m > 50) return -1;
        return 0;
    }

    /** 21. Fisher Transform turn from extremes. */
    private int fisherVote(List<Candle> k) {
        double f = fisher(k);
        if (Double.isNaN(f)) return 0;
        double fPrev = fisher(k.subList(0, k.size() - 1));
        if (Double.isNaN(fPrev)) return 0;
        if (fPrev < -1 && f > fPrev) return 1;
        if (fPrev > 1 && f < fPrev) return -1;
        return 0;
    }

    /** 22. DeMarker (14) 0.3/0.7 reversals. */
    private int demarkerVote(List<Candle> k) {
        double d = deMarker(k, 14);
        if (Double.isNaN(d)) return 0;
        if (d < 0.3) return 1;
        if (d > 0.7) return -1;
        return 0;
    }

    /** 23. Awesome Oscillator (5,34) zero-cross + momentum. */
    private int aoVote(List<Candle> k) {
        double a = awesomeOsc(k);
        if (Double.isNaN(a)) return 0;
        double aPrev = awesomeOsc(k.subList(0, k.size() - 1));
        if (Double.isNaN(aPrev)) return 0;
        if (aPrev <= 0 && a > 0) return 1;
        if (aPrev >= 0 && a < 0) return -1;
        return 0;
    }

    /** 24. Force Index + Ease of Movement combined volume flow. */
    private int volumeFlowVote(List<Candle> k) {
        double f = forceIndex(k, 13), e = eom(k, 14);
        if (Double.isNaN(f) || Double.isNaN(e)) return 0;
        if (f > 0 && e > 0) return 1;
        if (f < 0 && e < 0) return -1;
        return 0;
    }

    /** 25. Chaikin Money Flow (20) institutional flow. */
    private int cmfVote(List<Candle> k) {
        double c = cmf(k, 20);
        if (Double.isNaN(c)) return 0;
        if (c > 0.08) return 1;
        if (c < -0.08) return -1;
        return 0;
    }

    /** 26. Klinger oscillator vs zero. */
    private int klingerVote(List<Candle> k) {
        double kv = klinger(k);
        if (Double.isNaN(kv)) return 0;
        if (kv > 0) return 1;
        if (kv < 0) return -1;
        return 0;
    }

    /** 27. PVT + A/D accumulation agreement. */
    private int pvtAdVote(List<Candle> k) {
        double p = pvtSlope(k, 20), a = adSlope(k, 20);
        if (p > 0.05 && a > 0.05) return 1;
        if (p < -0.05 && a < -0.05) return -1;
        return 0;
    }

    /** 28. Fibonacci retracement bounce (61.8/50 zone of last swing). */
    private int fibVote(List<Candle> k) {
        double[] f = fibLevels(k);
        if (f == null) return 0;
        double c = k.get(k.size() - 1).c;
        double tol = 0.004 * c; // 0.4% tolerance band
        if (f[5] > 0) { // up swing: support at 61.8/50 levels
            if (Math.abs(c - f[3]) < tol || Math.abs(c - f[2]) < tol) return 1;
        } else {        // down swing: resistance at 61.8/50
            if (Math.abs(c - f[3]) < tol || Math.abs(c - f[2]) < tol) return -1;
        }
        return 0;
    }

    /** 29. Pivot point break — momentum through R1/S1. */
    private int pivotVote(List<Candle> k) {
        double[] p = pivotPoints(k);
        if (p == null) return 0;
        double c = k.get(k.size() - 1).c;
        if (c > p[1]) return 1;   // above R1
        if (c < p[4]) return -1;  // below S1
        return 0;
    }

    /** 30. FVG imbalance fill — trade in direction of last gap. */
    private int fvgVote(List<Candle> k) {
        int f = fvg(k);
        if (f == 0) return 0;
        double r = rsi(k, 14);
        if (Double.isNaN(r)) return 0;
        if (f > 0 && r > 45 && r < 75) return 1;   // bullish imbalance, momentum intact
        if (f < 0 && r > 25 && r < 55) return -1;
        return 0;
    }

    /** 31. BOS — Break of Structure (SMC). */
    private int bosVote(List<Candle> k) {
        return bosVoteCalc(k);
    }

    /** 32. Liquidity sweep / stop hunt reversal (SMC). */
    private int sweepVote(List<Candle> k) {
        return sweepVoteCalc(k);
    }

    /** 33. Harmonic pattern completion (Gartley/Bat/Butterfly/Crab at D). */
    private int harmonicVote(List<Candle> k) {
        Object[] h = harmonicPattern(k);
        if (h == null) return 0;
        return (Integer) h[1];
    }

    /** 34. Schaff Trend Cycle (23,50,10) fast/slow zone cross. */
    private int schaffVote(List<Candle> k) {
        double s = schaff(k);
        if (Double.isNaN(s)) return 0;
        if (s < 20) return 1;
        if (s > 80) return -1;
        return 0;
    }

    /** 35. Crypto Fear & Greed contrarian (cached 60 min from alternative.me). */
    private int fngVote(List<Candle> k) {
        if (fngValue < 0) return 0; // no data (non-crypto or fetch failed)
        if (fngValue <= 20) return 1;   // extreme fear — contrarian buy
        if (fngValue >= 80) return -1;  // extreme greed — contrarian sell
        return 0;
    }

    // ================== TRADE LOGIC ==================
    private void scanAndTrade() {
        if (System.currentTimeMillis() < newsPauseUntil) { lastConsensus = "news pause active"; return; }
        for (long uid : userIds()) {
            if (dailyHalted(uid)) continue;

            for (String sym : activeSymbols()) {
                Cursor ex = db.getReadableDatabase().rawQuery(
                        "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'", new String[]{String.valueOf(uid), sym});
                boolean have = ex.moveToFirst() && ex.getInt(0) > 0; ex.close();
                if (have) continue;

                List<Candle> k = loadCandles(sym);
                if (k.size() < 60) continue;
                // v5.9.2 FIX — Binance returns the CURRENT in-progress candle last; its
                // timestamp is ALWAYS < 60s old, so the old check skipped EVERY symbol on
                // EVERY scan and the engine could never open a single trade. Now we drop
                // the unclosed candle and trade on the last CLOSED 1m candle instead.
                if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < TF_MS) {
                    k = k.subList(0, k.size() - 1);
                    if (k.size() < 60) continue;
                }

                int[] votes = {emaCross(k), rsiBollinger(k), macdStoch(k), vwapReversion(k), breakout(k),
                        supertrendVote(k), ichimokuVote(k), adxTrendVote(k), cciWilliamsVote(k),
                        mfiObvVote(k), psarAroonVote(k), stochRsiVote(k),
                        // v5.9 PDF encyclopedia votes 13-35
                        candleVote(k), donchianVote(k), hullVote(k), kamaVote(k), vortexVote(k),
                        alligatorVote(k), tsiVote(k), cmoVote(k), fisherVote(k), demarkerVote(k),
                        aoVote(k), volumeFlowVote(k), cmfVote(k), klingerVote(k), pvtAdVote(k),
                        fibVote(k), pivotVote(k), fvgVote(k), bosVote(k), sweepVote(k),
                        harmonicVote(k), schaffVote(k), fngVote(k)};
                int buy = 0, sell = 0;
                for (int v : votes) { if (v > 0) buy++; else if (v < 0) sell++; }
                // Participation-based consensus: abstentions don't dilute the signal.
                int participated = buy + sell;
                double consensusBuy = participated > 0 ? buy / (double) participated : 0;
                double consensusSell = participated > 0 ? sell / (double) participated : 0;
                double dom = Math.max(consensusBuy, consensusSell);
                boolean buyLeads = consensusBuy > consensusSell;

                // v1.1 TWO-TIER ENTRY — replaces the old gate that demanded >=14 voting
                // strategies (40% of 35). That gate almost never passed because ~20 of the
                // 35 strategies are rare-EVENT voters by design, so a normal candle got
                // only 5-12 votes and the engine sat silent forever (user-reported bug).
                //
                // TIER A — CONSENSUS (quality): >=9 voters AND >=60% dominant, strict lead.
                // TIER B — SCOUT (activity): engine silent 20+ min -> >=6 voters AND >=65%
                //   dominant is enough, so the lab always demonstrates real entries.
                long silenceMs = System.currentTimeMillis() - lastEntryAt;
                boolean scoutArmed = silenceMs >= 20L * 60_000;
                String tier = null;
                if (participated >= 9 && dom >= 0.60 && (buyLeads ? consensusBuy : consensusSell) > 0.5) {
                    tier = "CONSENSUS_35";
                } else if (scoutArmed && participated >= 6 && dom >= 0.65 && (buyLeads ? consensusBuy : consensusSell) > 0.5) {
                    tier = "SCOUT_SIGNAL";
                }

                if (tier != null) {
                    String side = buyLeads ? "BUY" : "SELL";
                    double cons = buyLeads ? consensusBuy : consensusSell;
                    openTrade(uid, sym, side, cons, k, tier);
                    lastConsensus = "ENTRY OPEN — " + sym + " " + side + " (" + tier + ", " + (int)(cons * 100)
                            + "% dominant, " + participated + "/35 voters) — managing SL/TP every 30s";
                } else {
                    long silentMin = silenceMs / 60000;
                    lastConsensus = "24h scan #" + scanCount + " — " + activeSymbols + " syms on 1m — voters "
                            + participated + "/35 · BUY " + buy + " vs SELL " + sell + " · best " + (int)(dom * 100)
                            + "% (need 60% w/ 9 voters" + (scoutArmed ? ", or 65% w/ 6 as scout" : "") + ") — silent "
                            + silentMin + " min" + (scoutArmed ? " · SCOUT ARMED" : "");
                }
            }
        }
    }

    private void openTrade(long uid, String sym, String side, double consensus, List<Candle> k, String tier) {
        double price = k.get(k.size() - 1).c;
        double a = atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return;
        double sl = "BUY".equals(side) ? price - 1.5 * a : price + 1.5 * a;
        double tp = "BUY".equals(side) ? price + 2.5 * a : price - 2.5 * a;

        Cursor c = db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?", new String[]{String.valueOf(uid)});
        double bal = c.moveToFirst() ? c.getDouble(0) : 100; c.close();
        double riskAmt = bal * RISK_PER_TRADE;
        double qty = riskAmt / (1.5 * a);
        if (qty * price > bal * 0.95) qty = bal * 0.95 / price;
        if (qty <= 0) return;

        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at) VALUES(?,?,?,?,?,?,?, 'OPEN', ?, ?, ?)",
                new Object[]{uid, sym, side, qty, price, sl, tp, tier, consensus, System.currentTimeMillis()});
        lastEntryAt = System.currentTimeMillis(); // v1.1 — scout timer resets on every real entry
        db.log("INFO", "EXECUTOR", "PAPER_OPEN", sym + " " + side + " [" + tier + "] qty=" + String.format("%.6f", qty) + " entry=" + String.format("%.6f", price) + " consensus=" + (int)(consensus * 100) + "%");
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
        double eq = c.moveToFirst() ? c.getDouble(0) : 100; c.close();
        db.getWritableDatabase().execSQL("INSERT OR REPLACE INTO equity(ts, value) VALUES(?,?)",
                new Object[]{System.currentTimeMillis(), eq});
        // v1.0 BUGFIX: the equity table grew forever (a row every 30s scan). Keep the
        // most recent 2000 points (~16h of scans); the dashboard reads the last 48.
        try {
            db.getWritableDatabase().execSQL(
                    "DELETE FROM equity WHERE ts NOT IN (SELECT ts FROM equity ORDER BY ts DESC LIMIT 2000)");
        } catch (Throwable ignored) { }
    }

    // ================== DISCOVERY (all-world instruments) ==================
    private void seedStaticInstruments() {
        // v5.9 PDF ENCYCLOPEDIA instrument universe — every major asset class
        // from the Complete Trading Encyclopedia (Part 1 of the PDF).
        // CRYPTO  = traded live on Binance (paper money) — activated by discovery.
        // BROKER  = forex/metals/energy/agri/indices/stocks/bonds — pending broker connection.
        List<String[]> statics = new ArrayList<>();
        // symbol, class, status, note
        // --- Precious & industrial metals (PDF 1.6) ---
        statics.add(new String[]{"XAUUSD", "METAL", "PENDING_BROKER", "Gold spot XAU/USD"});
        statics.add(new String[]{"XAGUSD", "METAL", "PENDING_BROKER", "Silver spot XAG/USD"});
        statics.add(new String[]{"XPTUSD", "METAL", "PENDING_BROKER", "Platinum spot"});
        statics.add(new String[]{"XPDUSD", "METAL", "PENDING_BROKER", "Palladium spot"});
        statics.add(new String[]{"XCUUSD", "METAL", "PENDING_BROKER", "Copper (Dr. Copper)"});
        statics.add(new String[]{"ALUUSD", "METAL", "PENDING_BROKER", "LME Aluminium"});
        statics.add(new String[]{"ZNCUSD", "METAL", "PENDING_BROKER", "LME Zinc"});
        statics.add(new String[]{"NIKUSD", "METAL", "PENDING_BROKER", "LME Nickel"});
        statics.add(new String[]{"LEADUSD", "METAL", "PENDING_BROKER", "LME Lead"});
        statics.add(new String[]{"TINUSD", "METAL", "PENDING_BROKER", "LME Tin"});
        statics.add(new String[]{"LITUSD", "METAL", "PENDING_BROKER", "Lithium carbonate (battery metal)"});
        statics.add(new String[]{"IRONUSD", "METAL", "PENDING_BROKER", "Iron ore (SGX)"});
        statics.add(new String[]{"URAUSD", "METAL", "PENDING_BROKER", "Uranium U3O8"});
        // --- Energy (PDF 1.7) ---
        statics.add(new String[]{"USOIL", "ENERGY", "PENDING_BROKER", "WTI Crude Oil (CL)"});
        statics.add(new String[]{"UKOIL", "ENERGY", "PENDING_BROKER", "Brent Crude Oil (BZ)"});
        statics.add(new String[]{"NATGAS", "ENERGY", "PENDING_BROKER", "Natural Gas (Henry Hub NG)"});
        statics.add(new String[]{"GASOLINE", "ENERGY", "PENDING_BROKER", "RBOB Gasoline (RB)"});
        statics.add(new String[]{"HEATOIL", "ENERGY", "PENDING_BROKER", "Heating Oil / ULSD (HO)"});
        statics.add(new String[]{"COAL", "ENERGY", "PENDING_BROKER", "Newcastle thermal coal"});
        statics.add(new String[]{"CARBON", "ENERGY", "PENDING_BROKER", "EU carbon allowance (EUA)"});
        // --- Agriculture (PDF 1.8) ---
        statics.add(new String[]{"CORN", "AGRI", "PENDING_BROKER", "Corn (CBOT)"});
        statics.add(new String[]{"WHEAT", "AGRI", "PENDING_BROKER", "Wheat (Chicago SRW)"});
        statics.add(new String[]{"SOYBEAN", "AGRI", "PENDING_BROKER", "Soybeans"});
        statics.add(new String[]{"SOYMEAL", "AGRI", "PENDING_BROKER", "Soybean Meal"});
        statics.add(new String[]{"SOYOIL", "AGRI", "PENDING_BROKER", "Soybean Oil"});
        statics.add(new String[]{"RICE", "AGRI", "PENDING_BROKER", "Rough Rice"});
        statics.add(new String[]{"OATS", "AGRI", "PENDING_BROKER", "Oats"});
        statics.add(new String[]{"CANOLA", "AGRI", "PENDING_BROKER", "Rapeseed / Canola"});
        statics.add(new String[]{"COFFEE", "AGRI", "PENDING_BROKER", "Coffee Arabica"});
        statics.add(new String[]{"ROBUSTA", "AGRI", "PENDING_BROKER", "Coffee Robusta"});
        statics.add(new String[]{"COCOA", "AGRI", "PENDING_BROKER", "Cocoa"});
        statics.add(new String[]{"SUGAR", "AGRI", "PENDING_BROKER", "Sugar #11"});
        statics.add(new String[]{"COTTON", "AGRI", "PENDING_BROKER", "Cotton #2"});
        statics.add(new String[]{"ORANGEJ", "AGRI", "PENDING_BROKER", "Orange Juice (FCOJ)"});
        statics.add(new String[]{"CATTLE", "AGRI", "PENDING_BROKER", "Live Cattle"});
        statics.add(new String[]{"FEEDER", "AGRI", "PENDING_BROKER", "Feeder Cattle"});
        statics.add(new String[]{"HOGS", "AGRI", "PENDING_BROKER", "Lean Hogs"});
        statics.add(new String[]{"LUMBER", "AGRI", "PENDING_BROKER", "Lumber"});
        statics.add(new String[]{"RUBBER", "AGRI", "PENDING_BROKER", "Rubber (TSR20)"});
        statics.add(new String[]{"PALMOIL", "AGRI", "PENDING_BROKER", "Crude Palm Oil"});
        // --- Forex majors (PDF 1.2) ---
        statics.add(new String[]{"EURUSD", "FOREX", "PENDING_BROKER", "Euro / US Dollar (Fiber)"});
        statics.add(new String[]{"GBPUSD", "FOREX", "PENDING_BROKER", "Pound / US Dollar (Cable)"});
        statics.add(new String[]{"USDJPY", "FOREX", "PENDING_BROKER", "US Dollar / Yen (Gopher)"});
        statics.add(new String[]{"USDCHF", "FOREX", "PENDING_BROKER", "US Dollar / Franc (Swissie)"});
        statics.add(new String[]{"AUDUSD", "FOREX", "PENDING_BROKER", "Aussie / US Dollar"});
        statics.add(new String[]{"NZDUSD", "FOREX", "PENDING_BROKER", "Kiwi / US Dollar"});
        statics.add(new String[]{"USDCAD", "FOREX", "PENDING_BROKER", "US Dollar / Loonie"});
        // --- Forex crosses (PDF 1.3) ---
        statics.add(new String[]{"EURGBP", "FOREX", "PENDING_BROKER", "Euro / Pound"});
        statics.add(new String[]{"EURJPY", "FOREX", "PENDING_BROKER", "Euro / Yen"});
        statics.add(new String[]{"EURCHF", "FOREX", "PENDING_BROKER", "Euro / Franc"});
        statics.add(new String[]{"EURAUD", "FOREX", "PENDING_BROKER", "Euro / Aussie"});
        statics.add(new String[]{"EURNZD", "FOREX", "PENDING_BROKER", "Euro / Kiwi"});
        statics.add(new String[]{"EURCAD", "FOREX", "PENDING_BROKER", "Euro / Loonie"});
        statics.add(new String[]{"GBPJPY", "FOREX", "PENDING_BROKER", "Pound / Yen (Guppy)"});
        statics.add(new String[]{"GBPCHF", "FOREX", "PENDING_BROKER", "Pound / Franc"});
        statics.add(new String[]{"GBPAUD", "FOREX", "PENDING_BROKER", "Pound / Aussie"});
        statics.add(new String[]{"GBPNZD", "FOREX", "PENDING_BROKER", "Pound / Kiwi"});
        statics.add(new String[]{"GBPCAD", "FOREX", "PENDING_BROKER", "Pound / Loonie"});
        statics.add(new String[]{"AUDJPY", "FOREX", "PENDING_BROKER", "Aussie / Yen"});
        statics.add(new String[]{"AUDNZD", "FOREX", "PENDING_BROKER", "Aussie / Kiwi"});
        statics.add(new String[]{"AUDCAD", "FOREX", "PENDING_BROKER", "Aussie / Loonie"});
        statics.add(new String[]{"AUDCHF", "FOREX", "PENDING_BROKER", "Aussie / Franc"});
        statics.add(new String[]{"NZDJPY", "FOREX", "PENDING_BROKER", "Kiwi / Yen"});
        statics.add(new String[]{"NZDCAD", "FOREX", "PENDING_BROKER", "Kiwi / Loonie"});
        statics.add(new String[]{"NZDCHF", "FOREX", "PENDING_BROKER", "Kiwi / Franc"});
        statics.add(new String[]{"CADJPY", "FOREX", "PENDING_BROKER", "Loonie / Yen"});
        statics.add(new String[]{"CADCHF", "FOREX", "PENDING_BROKER", "Loonie / Franc"});
        statics.add(new String[]{"CHFJPY", "FOREX", "PENDING_BROKER", "Franc / Yen"});
        // --- Forex exotics (PDF 1.4) — Asia ---
        statics.add(new String[]{"USDCNH", "FOREX", "PENDING_BROKER", "USD / Yuan (onshore-offshore)"});
        statics.add(new String[]{"USDSGD", "FOREX", "PENDING_BROKER", "USD / Singapore Dollar"});
        statics.add(new String[]{"USDHKD", "FOREX", "PENDING_BROKER", "USD / Hong Kong Dollar"});
        statics.add(new String[]{"USDINR", "FOREX", "PENDING_BROKER", "USD / Indian Rupee (NDF)"});
        statics.add(new String[]{"USDPKR", "FOREX", "PENDING_BROKER", "USD / Pakistani Rupee"});
        statics.add(new String[]{"USDBDT", "FOREX", "PENDING_BROKER", "USD / Bangladeshi Taka"});
        statics.add(new String[]{"USDLKR", "FOREX", "PENDING_BROKER", "USD / Sri Lankan Rupee"});
        statics.add(new String[]{"USDIDR", "FOREX", "PENDING_BROKER", "USD / Indonesian Rupiah (NDF)"});
        statics.add(new String[]{"USDMYR", "FOREX", "PENDING_BROKER", "USD / Malaysian Ringgit"});
        statics.add(new String[]{"USDTHB", "FOREX", "PENDING_BROKER", "USD / Thai Baht"});
        statics.add(new String[]{"USDPHP", "FOREX", "PENDING_BROKER", "USD / Philippine Peso"});
        statics.add(new String[]{"USDKRW", "FOREX", "PENDING_BROKER", "USD / Korean Won (NDF)"});
        statics.add(new String[]{"USDTWD", "FOREX", "PENDING_BROKER", "USD / Taiwan Dollar (NDF)"});
        statics.add(new String[]{"USDVND", "FOREX", "PENDING_BROKER", "USD / Vietnamese Dong (NDF)"});
        // exotics — Middle East / Africa
        statics.add(new String[]{"USDTRY", "FOREX", "PENDING_BROKER", "USD / Turkish Lira"});
        statics.add(new String[]{"USDILS", "FOREX", "PENDING_BROKER", "USD / Israeli Shekel"});
        statics.add(new String[]{"USDAED", "FOREX", "PENDING_BROKER", "USD / UAE Dirham"});
        statics.add(new String[]{"USDSAR", "FOREX", "PENDING_BROKER", "USD / Saudi Riyal"});
        statics.add(new String[]{"USDQAR", "FOREX", "PENDING_BROKER", "USD / Qatari Riyal"});
        statics.add(new String[]{"USDKWD", "FOREX", "PENDING_BROKER", "USD / Kuwaiti Dinar"});
        statics.add(new String[]{"USDEGP", "FOREX", "PENDING_BROKER", "USD / Egyptian Pound"});
        statics.add(new String[]{"USDZAR", "FOREX", "PENDING_BROKER", "USD / South African Rand"});
        statics.add(new String[]{"USDNGN", "FOREX", "PENDING_BROKER", "USD / Nigerian Naira (NDF)"});
        statics.add(new String[]{"USDKES", "FOREX", "PENDING_BROKER", "USD / Kenyan Shilling"});
        statics.add(new String[]{"USDMAD", "FOREX", "PENDING_BROKER", "USD / Moroccan Dirham"});
        // exotics — Europe
        statics.add(new String[]{"USDPLN", "FOREX", "PENDING_BROKER", "USD / Polish Zloty"});
        statics.add(new String[]{"USDCZK", "FOREX", "PENDING_BROKER", "USD / Czech Koruna"});
        statics.add(new String[]{"USDHUF", "FOREX", "PENDING_BROKER", "USD / Hungarian Forint"});
        statics.add(new String[]{"USDRON", "FOREX", "PENDING_BROKER", "USD / Romanian Leu"});
        statics.add(new String[]{"USDSEK", "FOREX", "PENDING_BROKER", "USD / Swedish Krona"});
        statics.add(new String[]{"USDNOK", "FOREX", "PENDING_BROKER", "USD / Norwegian Krone"});
        statics.add(new String[]{"USDDKK", "FOREX", "PENDING_BROKER", "USD / Danish Krone"});
        statics.add(new String[]{"USDRUB", "FOREX", "PENDING_BROKER", "USD / Russian Ruble"});
        statics.add(new String[]{"USDUAH", "FOREX", "PENDING_BROKER", "USD / Ukrainian Hryvnia"});
        // exotics — Americas
        statics.add(new String[]{"USDMXN", "FOREX", "PENDING_BROKER", "USD / Mexican Peso"});
        statics.add(new String[]{"USDBRL", "FOREX", "PENDING_BROKER", "USD / Brazilian Real (NDF)"});
        statics.add(new String[]{"USDARS", "FOREX", "PENDING_BROKER", "USD / Argentine Peso"});
        statics.add(new String[]{"USDCLP", "FOREX", "PENDING_BROKER", "USD / Chilean Peso"});
        statics.add(new String[]{"USDCOP", "FOREX", "PENDING_BROKER", "USD / Colombian Peso"});
        statics.add(new String[]{"USDPEN", "FOREX", "PENDING_BROKER", "USD / Peruvian Sol"});
        // exotics — cross pairs
        statics.add(new String[]{"EURTRY", "FOREX", "PENDING_BROKER", "Euro / Turkish Lira"});
        statics.add(new String[]{"EURZAR", "FOREX", "PENDING_BROKER", "Euro / Rand"});
        statics.add(new String[]{"EURPLN", "FOREX", "PENDING_BROKER", "Euro / Zloty"});
        statics.add(new String[]{"EURSEK", "FOREX", "PENDING_BROKER", "Euro / Krona"});
        statics.add(new String[]{"EURNOK", "FOREX", "PENDING_BROKER", "Euro / Krone"});
        statics.add(new String[]{"EURDKK", "FOREX", "PENDING_BROKER", "Euro / Danish Krone"});
        statics.add(new String[]{"EURMXN", "FOREX", "PENDING_BROKER", "Euro / Mexican Peso"});
        statics.add(new String[]{"EURILS", "FOREX", "PENDING_BROKER", "Euro / Shekel"});
        statics.add(new String[]{"EURSGD", "FOREX", "PENDING_BROKER", "Euro / SGD"});
        statics.add(new String[]{"GBPSGD", "FOREX", "PENDING_BROKER", "Pound / SGD"});
        statics.add(new String[]{"GBPZAR", "FOREX", "PENDING_BROKER", "Pound / Rand"});
        statics.add(new String[]{"GBPTRY", "FOREX", "PENDING_BROKER", "Pound / Lira"});
        statics.add(new String[]{"SGDJPY", "FOREX", "PENDING_BROKER", "SGD / Yen"});
        statics.add(new String[]{"ZARJPY", "FOREX", "PENDING_BROKER", "Rand / Yen"});
        statics.add(new String[]{"NOKSEK", "FOREX", "PENDING_BROKER", "Krone / Krona"});
        statics.add(new String[]{"TRYJPY", "FOREX", "PENDING_BROKER", "Lira / Yen"});
        statics.add(new String[]{"MXNJPY", "FOREX", "PENDING_BROKER", "Peso / Yen"});
        statics.add(new String[]{"CNHJPY", "FOREX", "PENDING_BROKER", "Yuan / Yen"});
        statics.add(new String[]{"AUDSGD", "FOREX", "PENDING_BROKER", "Aussie / SGD"});
        statics.add(new String[]{"CHFSGD", "FOREX", "PENDING_BROKER", "Franc / SGD"});
        // --- Currency indices (PDF 1.5) ---
        statics.add(new String[]{"USDX", "INDEX", "PENDING_BROKER", "US Dollar Index (DXY)"});
        statics.add(new String[]{"EXY", "INDEX", "PENDING_BROKER", "Euro Currency Index"});
        statics.add(new String[]{"BXY", "INDEX", "PENDING_BROKER", "British Pound Index"});
        statics.add(new String[]{"JXY", "INDEX", "PENDING_BROKER", "Japanese Yen Index"});
        statics.add(new String[]{"AXY", "INDEX", "PENDING_BROKER", "Australian Dollar Index"});
        statics.add(new String[]{"CXY", "INDEX", "PENDING_BROKER", "Canadian Dollar Index"});
        statics.add(new String[]{"SXY", "INDEX", "PENDING_BROKER", "Swiss Franc Index"});
        statics.add(new String[]{"ZXY", "INDEX", "PENDING_BROKER", "NZ Dollar Index"});
        // --- Stock indices (PDF 1.9) ---
        statics.add(new String[]{"US500", "INDEX", "PENDING_BROKER", "S&P 500"});
        statics.add(new String[]{"NAS100", "INDEX", "PENDING_BROKER", "Nasdaq 100"});
        statics.add(new String[]{"US30", "INDEX", "PENDING_BROKER", "Dow Jones 30"});
        statics.add(new String[]{"RUSSELL2000", "INDEX", "PENDING_BROKER", "Russell 2000 small cap"});
        statics.add(new String[]{"SOX", "INDEX", "PENDING_BROKER", "Philadelphia Semiconductor"});
        statics.add(new String[]{"VIX", "INDEX", "PENDING_BROKER", "CBOE Volatility Index"});
        statics.add(new String[]{"GER40", "INDEX", "PENDING_BROKER", "DAX 40 (Germany)"});
        statics.add(new String[]{"UK100", "INDEX", "PENDING_BROKER", "FTSE 100 (UK)"});
        statics.add(new String[]{"FRA40", "INDEX", "PENDING_BROKER", "CAC 40 (France)"});
        statics.add(new String[]{"EU50", "INDEX", "PENDING_BROKER", "Euro Stoxx 50"});
        statics.add(new String[]{"IBEX35", "INDEX", "PENDING_BROKER", "IBEX 35 (Spain)"});
        statics.add(new String[]{"FTSEMIB", "INDEX", "PENDING_BROKER", "FTSE MIB (Italy)"});
        statics.add(new String[]{"AEX25", "INDEX", "PENDING_BROKER", "AEX (Netherlands)"});
        statics.add(new String[]{"SMI20", "INDEX", "PENDING_BROKER", "SMI (Switzerland)"});
        statics.add(new String[]{"OMXS30", "INDEX", "PENDING_BROKER", "OMX Stockholm 30"});
        statics.add(new String[]{"OBX25", "INDEX", "PENDING_BROKER", "OBX (Norway)"});
        statics.add(new String[]{"WIG20", "INDEX", "PENDING_BROKER", "WIG20 (Poland)"});
        statics.add(new String[]{"BIST100", "INDEX", "PENDING_BROKER", "BIST 100 (Turkey)"});
        statics.add(new String[]{"JP225", "INDEX", "PENDING_BROKER", "Nikkei 225 (Japan)"});
        statics.add(new String[]{"TOPIX", "INDEX", "PENDING_BROKER", "TOPIX (Japan)"});
        statics.add(new String[]{"HK50", "INDEX", "PENDING_BROKER", "Hang Seng (Hong Kong)"});
        statics.add(new String[]{"HSTECH", "INDEX", "PENDING_BROKER", "Hang Seng Tech"});
        statics.add(new String[]{"SHCOMP", "INDEX", "PENDING_BROKER", "Shanghai Composite"});
        statics.add(new String[]{"CSI300", "INDEX", "PENDING_BROKER", "CSI 300 (China A-shares)"});
        statics.add(new String[]{"KOSPI", "INDEX", "PENDING_BROKER", "KOSPI (South Korea)"});
        statics.add(new String[]{"TAIEX", "INDEX", "PENDING_BROKER", "TAIEX (Taiwan)"});
        statics.add(new String[]{"NIFTY50", "INDEX", "PENDING_BROKER", "Nifty 50 (India)"});
        statics.add(new String[]{"SENSEX", "INDEX", "PENDING_BROKER", "BSE Sensex (India)"});
        statics.add(new String[]{"BANKNIFTY", "INDEX", "PENDING_BROKER", "Bank Nifty (India)"});
        statics.add(new String[]{"KSE100", "INDEX", "PENDING_BROKER", "KSE-100 (Pakistan Stock Exchange)"});
        statics.add(new String[]{"KSE30", "INDEX", "PENDING_BROKER", "KSE-30 (Pakistan)"});
        statics.add(new String[]{"KMI30", "INDEX", "PENDING_BROKER", "KMI-30 Islamic index (Pakistan)"});
        statics.add(new String[]{"DSEX", "INDEX", "PENDING_BROKER", "DSEX (Bangladesh)"});
        statics.add(new String[]{"CSEALL", "INDEX", "PENDING_BROKER", "CSE All Share (Sri Lanka)"});
        statics.add(new String[]{"NEPSE", "INDEX", "PENDING_BROKER", "NEPSE (Nepal)"});
        statics.add(new String[]{"STI", "INDEX", "PENDING_BROKER", "Straits Times (Singapore)"});
        statics.add(new String[]{"KLCI", "INDEX", "PENDING_BROKER", "FTSE KLCI (Malaysia)"});
        statics.add(new String[]{"SET", "INDEX", "PENDING_BROKER", "SET (Thailand)"});
        statics.add(new String[]{"JCI", "INDEX", "PENDING_BROKER", "JCI (Indonesia)"});
        statics.add(new String[]{"PSEI", "INDEX", "PENDING_BROKER", "PSEi (Philippines)"});
        statics.add(new String[]{"VNINDEX", "INDEX", "PENDING_BROKER", "VN-Index (Vietnam)"});
        statics.add(new String[]{"AUS200", "INDEX", "PENDING_BROKER", "ASX 200 (Australia)"});
        statics.add(new String[]{"NZX50", "INDEX", "PENDING_BROKER", "NZX 50 (New Zealand)"});
        statics.add(new String[]{"TSX60", "INDEX", "PENDING_BROKER", "S&P/TSX 60 (Canada)"});
        statics.add(new String[]{"BOVESPA", "INDEX", "PENDING_BROKER", "Bovespa (Brazil)"});
        statics.add(new String[]{"IPCMX", "INDEX", "PENDING_BROKER", "IPC (Mexico)"});
        statics.add(new String[]{"TASI", "INDEX", "PENDING_BROKER", "Tadawul TASI (Saudi Arabia)"});
        statics.add(new String[]{"DFMGI", "INDEX", "PENDING_BROKER", "DFM General (Dubai)"});
        statics.add(new String[]{"TA35", "INDEX", "PENDING_BROKER", "TA-35 (Israel)"});
        statics.add(new String[]{"EGX30", "INDEX", "PENDING_BROKER", "EGX 30 (Egypt)"});
        statics.add(new String[]{"JSE40", "INDEX", "PENDING_BROKER", "JSE Top 40 (South Africa)"});
        // --- Global stocks by sector (PDF 1.11) ---
        String[][] stocks = {
            {"AAPL", "Apple"}, {"MSFT", "Microsoft"}, {"GOOGL", "Alphabet"}, {"AMZN", "Amazon"},
            {"META", "Meta Platforms"}, {"NVDA", "Nvidia"}, {"TSLA", "Tesla"}, {"AVGO", "Broadcom"},
            {"TSM", "TSMC"}, {"ORCL", "Oracle"}, {"SAP", "SAP"}, {"ADBE", "Adobe"},
            {"CRM", "Salesforce"}, {"AMD", "AMD"}, {"INTC", "Intel"}, {"QCOM", "Qualcomm"},
            {"IBM", "IBM"}, {"PLTR", "Palantir"},
            {"JPM", "JPMorgan"}, {"BAC", "Bank of America"}, {"GS", "Goldman Sachs"},
            {"MS", "Morgan Stanley"}, {"V", "Visa"}, {"MA", "Mastercard"}, {"PYPL", "PayPal"},
            {"HSBC", "HSBC"}, {"BRKB", "Berkshire Hathaway B"},
            {"XOM", "ExxonMobil"}, {"CVX", "Chevron"}, {"SHEL", "Shell"}, {"BP", "BP"}, {"TTE", "TotalEnergies"},
            {"LLY", "Eli Lilly"}, {"NVO", "Novo Nordisk"}, {"UNH", "UnitedHealth"}, {"JNJ", "Johnson & Johnson"},
            {"PFE", "Pfizer"}, {"MRK", "Merck"},
            {"WMT", "Walmart"}, {"COST", "Costco"}, {"KO", "Coca-Cola"}, {"PEP", "PepsiCo"},
            {"PG", "P&G"}, {"NSRGY", "Nestle"}, {"MCD", "McDonald's"}, {"NKE", "Nike"},
            {"BA", "Boeing"}, {"CAT", "Caterpillar"}, {"LMT", "Lockheed Martin"}, {"RTX", "RTX Corp"},
            {"SIEGY", "Siemens"}, {"HON", "Honeywell"},
            {"DIS", "Disney"}, {"NFLX", "Netflix"}, {"VZ", "Verizon"}, {"TMUS", "T-Mobile"}
        };
        for (String[] s : stocks) statics.add(new String[]{s[0], "STOCK", "PENDING_BROKER", s[1] + " (US/global stock)"});
        // --- Pakistani stocks — PSX (PDF 1.11 includes HBL/UBL/MCB/OGDC/PSO/Engro...) ---
        String[][] psx = {
            {"HBL", "Habib Bank Limited"}, {"UBL", "United Bank Limited"}, {"MCB", "MCB Bank"},
            {"MEZN", "Meezan Bank"}, {"OGDC", "Oil & Gas Development Co"}, {"PPL", "Pakistan Petroleum"},
            {"PSO", "Pakistan State Oil"}, {"ENGRO", "Engro Corporation"},
            {"LUCK", "Lucky Cement"}, {"FFC", "Fauji Fertilizer Company"},
            {"PTC", "PTCL"}, {"KEL", "K-Electric"}, {"HUBC", "Hub Power Company"}
        };
        for (String[] s : psx) statics.add(new String[]{"PSX_" + s[0], "STOCK", "PENDING_BROKER", s[1] + " (PSX Pakistan)"});
        // --- Bonds / rates (PDF 1.13, reference) ---
        statics.add(new String[]{"US10Y", "BOND", "PENDING_BROKER", "US Treasury 10Y yield"});
        statics.add(new String[]{"US02Y", "BOND", "PENDING_BROKER", "US Treasury 2Y yield"});
        statics.add(new String[]{"DE10Y", "BOND", "PENDING_BROKER", "German Bund 10Y yield"});
        statics.add(new String[]{"UK10Y", "BOND", "PENDING_BROKER", "UK Gilt 10Y yield"});
        statics.add(new String[]{"JP10Y", "BOND", "PENDING_BROKER", "JGB 10Y yield"});
        statics.add(new String[]{"PK06Y", "BOND", "PENDING_BROKER", "Pakistan T-Bill / PIB yield (KIBOR ref)"});
        // --- ETFs / funds (PDF 1.15, reference) ---
        String[][] etfs = {
            {"SPY", "S&P 500 ETF"}, {"QQQ", "Nasdaq 100 ETF"}, {"DIA", "Dow ETF"}, {"IWM", "Russell 2000 ETF"},
            {"VTI", "Total Market ETF"}, {"EEM", "Emerging Markets ETF"}, {"GLD", "Gold ETF"}, {"SLV", "Silver ETF"},
            {"USO", "Oil ETF"}, {"UNG", "NatGas ETF"}, {"TLT", "20Y Treasury ETF"}, {"HYG", "High Yield ETF"},
            {"SMH", "Semiconductor ETF"}, {"IBIT", "Spot Bitcoin ETF"}
        };
        for (String[] s : etfs) statics.add(new String[]{"ETF_" + s[0], "FUND", "PENDING_BROKER", s[1]});
        // --- Binance-tradeable proxies (paper trade from day one) ---
        statics.add(new String[]{"PAXGUSDT", "CRYPTO", "ACTIVE", "GOLD proxy — PAXG tracks spot gold 1:1"});
        statics.add(new String[]{"EURUSDT", "CRYPTO", "ACTIVE", "EUR/USD proxy — Euro token on Binance"});
        statics.add(new String[]{"BTCUSDT", "CRYPTO", "ACTIVE", "Bitcoin"});
        statics.add(new String[]{"ETHUSDT", "CRYPTO", "ACTIVE", "Ethereum"});
        // --- Crypto watchlist (PDF 1.12) — majors, L1s, L2s, DeFi, memes, AI ---
        String[][] crypto = {
            {"BNBUSDT", "BNB"}, {"SOLUSDT", "Solana"}, {"XRPUSDT", "XRP"}, {"ADAUSDT", "Cardano"},
            {"DOGEUSDT", "Dogecoin"}, {"AVAXUSDT", "Avalanche"}, {"DOTUSDT", "Polkadot"}, {"LINKUSDT", "Chainlink"},
            {"TRXUSDT", "TRON"}, {"LTCUSDT", "Litecoin"}, {"BCHUSDT", "Bitcoin Cash"}, {"ATOMUSDT", "Cosmos"},
            {"XLMUSDT", "Stellar"}, {"NEARUSDT", "NEAR Protocol"}, {"APTUSDT", "Aptos"}, {"OPUSDT", "Optimism"},
            {"ARBUSDT", "Arbitrum"}, {"FILUSDT", "Filecoin"}, {"INJUSDT", "Injective"}, {"SUIUSDT", "Sui"},
            {"TONUSDT", "Toncoin"}, {"PEPEUSDT", "Pepe"}, {"SHIBUSDT", "Shiba Inu"},
            {"XMRUSDT", "Monero"}, {"ZECUSDT", "Zcash"}, {"ETCUSDT", "Ethereum Classic"},
            {"UNIUSDT", "Uniswap"}, {"AAVEUSDT", "Aave"}, {"MKRUSDT", "Maker/Sky"}, {"CRVUSDT", "Curve"},
            {"LDOUSDT", "Lido DAO"}, {"COMPUSDT", "Compound"}, {"SNXUSDT", "Synthetix"}, {"DYDXUSDT", "dYdX"},
            {"GMXUSDT", "GMX"}, {"CAKEUSDT", "PancakeSwap"}, {"JUPUSDT", "Jupiter"}, {"RAYUSDT", "Raydium"},
            {"FLOKIUSDT", "Floki"}, {"BONKUSDT", "Bonk"}, {"WIFUSDT", "dogwifhat"},
            {"TAOUSDT", "Bittensor"}, {"RENDERUSDT", "Render"}, {"FETUSDT", "Artificial Superintelligence"},
            {"GRTUSDT", "The Graph"}, {"AKTUSDT", "Akash Network"},
            {"SEIUSDT", "Sei"}, {"TIAUSDT", "Celestia"}, {"KASUSDT", "Kaspa"}, {"HBARUSDT", "Hedera"},
            {"ICPUSDT", "Internet Computer"}, {"ZKUSDT", "zkSync"}, {"STRKUSDT", "Starknet"}, {"MNTUSDT", "Mantle"},
            {"ALGOUSDT", "Algorand"}, {"ENAUSDT", "Ethena"}, {"WLDUSDT", "Worldcoin"},
            {"GALAUSDT", "Gala"}, {"AXSUSDT", "Axie Infinity"}, {"SANDUSDT", "The Sandbox"},
            {"MANAUSDT", "Decentraland"}, {"IMXUSDT", "Immutable X"}
        };
        for (String[] s : crypto) statics.add(new String[]{s[0], "CRYPTO", "WATCHING", s[1]});
        for (String[] s : statics) {
            db.getWritableDatabase().execSQL(
                    "INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,?,?,?,?,?,?,?)",
                    new Object[]{s[0], s[0], "USD", s[2].equals("ACTIVE") ? "BINANCE" : "BROKER", s[1], s[2], s[2].equals("ACTIVE") ? 5000 : 0, System.currentTimeMillis(), s[3]});
        }
        // upgrade path: force-activate the always-on proxies even on existing installs
        db.getWritableDatabase().execSQL("UPDATE instruments SET status='ACTIVE' WHERE symbol IN ('PAXGUSDT','EURUSDT','BTCUSDT','ETHUSDT')");
        if (db.setting("seeded_v59", "0").equals("0")) {
            db.setSetting("seeded_v59", "1");
            db.log("INFO", "DISCOVERY", "ENCYCLOPEDIA_SEED", "v5.9 PDF encyclopedia universe registered: metals, energy, 21 agri, 100+ forex, 60+ indices, stocks + PSX, bonds, ETFs, 62 crypto (" + statics.size() + " instruments)");
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
                boolean alwaysOn = symbol.equals("PAXGUSDT") || symbol.equals("EURUSDT") || symbol.equals("BTCUSDT") || symbol.equals("ETHUSDT");
                String status = (rank < ACTIVE_TOP || alwaysOn) ? "ACTIVE" : "WATCHING";
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
            if (newCount > 0) db.log("INFO", "DISCOVERY", "SCAN_DONE", "24h market scan — " + newCount + " new instrument(s) auto-registered, trading enabled on them");
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
                for (String w : HIGH_IMPACT) {
                    // word-boundary match — "fed" must not match "federal"? (it should),
                    // but "rate" must NOT match "generate" / "accurate" / "moderate"
                    if (java.util.regex.Pattern.compile("\\b" + java.util.regex.Pattern.quote(w) + "\\b").matcher(low).find()) { impact = "HIGH"; break; }
                }

                db.getWritableDatabase().execSQL("INSERT INTO news(ts, source, headline, sentiment, impact) VALUES(?,?,?,?,?)",
                        new Object[]{System.currentTimeMillis(), feed.contains("coindesk") ? "CoinDesk" : "CoinTelegraph", title, sentiment, impact});
                db.log("INFO", "NEWS", "INGEST", sentiment + "/" + impact + " — " + title.substring(0, Math.min(80, title.length())));
                // v1.0 BUGFIX: prune the news ledger — it used to grow without limit
                try { db.getWritableDatabase().execSQL(
                        "DELETE FROM news WHERE id NOT IN (SELECT id FROM news ORDER BY id DESC LIMIT 500)"); } catch (Throwable ignored) { }

                // v1.0 BUGFIX: high-impact keywords are matched on WORD BOUNDARIES now.
                // The old substring contains() matched "rate" inside "generate",
                // "accurate", "moderate" etc. — pausing new entries almost PERMANENTLY.
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

    // ================== SENTIMENT (Fear & Greed) ==================
    private void fetchFearGreed() {
        String body = rawGet("https://api.alternative.me/fng/?limit=1");
        if (body == null) return;
        try {
            JSONObject o = new JSONObject(body);
            JSONArray data = o.getJSONArray("data");
            if (data.length() > 0) {
                fngValue = Integer.parseInt(data.getJSONObject(0).getString("value"));
                db.log("INFO", "SENTIMENT", "FNG", "crypto Fear & Greed = " + fngValue + " (" + data.getJSONObject(0).getString("value_classification") + ")");
            }
        } catch (Exception ignored) { }
    }

    // ================== STATUS for API ==================
    public Map<String, Object> status() {
        Map<String, Object> m = new HashMap<>();
        m.put("engine_on", "1".equals(db.setting("engine_on", "1")));
        m.put("active_symbols", activeSymbols);
        m.put("consensus", lastConsensus.isEmpty() ? "warming up" : lastConsensus);
        m.put("news_pause", System.currentTimeMillis() < newsPauseUntil);
        m.put("data_host", dataHost);
        m.put("timeframe", TF);
        m.put("scanner", "24h");
        m.put("scan_count", scanCount);
        m.put("last_scan_at", lastScanAt);
        m.put("strategy_count", 35);
        m.put("indicator_count", INDICATOR_LIBRARY.length);
        m.put("fear_greed", fngValue);
        m.put("last_pattern", lastPattern);
        return m;
    }

    /** v5.9 — the full PDF indicator library exposed to the dashboard/API. */
    public static final String[][] INDICATOR_LIBRARY = {
        // group, name, default settings
        {"Moving Averages", "SMA", "50/100/200"}, {"Moving Averages", "EMA", "9/12/21/50/200"},
        {"Moving Averages", "WMA", "fast response"}, {"Moving Averages", "SMMA/RMA (Wilder)", "14"},
        {"Moving Averages", "HMA (Hull)", "9/21"}, {"Moving Averages", "DEMA", "20"},
        {"Moving Averages", "TEMA", "20"}, {"Moving Averages", "KAMA (Kaufman)", "10,2,30"},
        {"Moving Averages", "ALMA", "9,0.85,6"}, {"Moving Averages", "T3 (Tillson)", "5,0.7"},
        {"Moving Averages", "ZLEMA", "20"}, {"Moving Averages", "LSMA (LinReg)", "25"},
        {"Moving Averages", "VWMA", "20"}, {"Moving Averages", "McGinley Dynamic", "14"},
        {"Moving Averages", "Golden/Death Cross", "50x200"}, {"Moving Averages", "MA Ribbon (Guppy)", "3-60"},
        {"Bands & Channels", "Bollinger Bands", "20,2"}, {"Bands & Channels", "Keltner Channel", "20,10,2"},
        {"Bands & Channels", "Donchian Channel", "20 (Turtle 20/55)"}, {"Bands & Channels", "Envelopes", "20,2.5%"},
        {"Bands & Channels", "Standard Deviation", "20"}, {"Bands & Channels", "Chandelier Exit", "22,3"},
        {"Trend", "MACD", "12,26,9"}, {"Trend", "ADX + DMI", "14 (ADX>25)"},
        {"Trend", "Parabolic SAR", "0.02,0.2"}, {"Trend", "Supertrend", "10,3"},
        {"Trend", "Ichimoku Cloud", "9,26,52"}, {"Trend", "Aroon", "25"},
        {"Trend", "Vortex", "14"}, {"Trend", "TRIX", "15"},
        {"Trend", "Mass Index", "25 (bulge 27)"}, {"Trend", "Alligator + Gator", "13/8/5"},
        {"Trend", "Schaff Trend Cycle", "23,50,10"}, {"Trend", "Choppiness Index", "14 (61.8)"},
        {"Trend", "KST", "10-15-20-30"}, {"Trend", "Coppock Curve", "14,11,10"},
        {"Trend", "APO/PPO", "12,26"}, {"Trend", "DPO", "20"},
        {"Trend", "Williams Fractals", "5 bar"}, {"Trend", "ZigZag swings", "auto"},
        {"Momentum", "RSI", "14 (70/30)"}, {"Momentum", "Stochastic", "14,3,3"},
        {"Momentum", "Stochastic RSI", "14,14,3,3"}, {"Momentum", "CCI", "20 (+/-100)"},
        {"Momentum", "Williams %R", "14 (-20/-80)"}, {"Momentum", "ROC / Momentum", "9/12"},
        {"Momentum", "Awesome Oscillator", "5,34"}, {"Momentum", "Ultimate Oscillator", "7,14,28"},
        {"Momentum", "TSI", "25,13"}, {"Momentum", "CMO (Chande)", "14"},
        {"Momentum", "Fisher Transform", "9"}, {"Momentum", "DeMarker", "14 (0.7/0.3)"},
        {"Momentum", "SMI", "10,3,3"}, {"Momentum", "Balance of Power", "14"},
        {"Momentum", "Laguerre RSI", "gamma 0.5"}, {"Momentum", "RVI (Vigor)", "10"},
        {"Momentum", "Elder Ray (Bull/Bear Power)", "13"},
        {"Volatility", "ATR", "14"},
        {"Volume & Flow", "Volume + Volume MA", "20"}, {"Volume & Flow", "OBV", "slope 20"},
        {"Volume & Flow", "Accumulation/Distribution", "slope 20"}, {"Volume & Flow", "Chaikin Money Flow", "20"},
        {"Volume & Flow", "Chaikin Oscillator", "3,10"}, {"Volume & Flow", "MFI", "14 (80/20)"},
        {"Volume & Flow", "VWAP", "session"}, {"Volume & Flow", "Force Index", "13"},
        {"Volume & Flow", "Ease of Movement", "14"}, {"Volume & Flow", "Klinger Oscillator", "34,55,13"},
        {"Volume & Flow", "PVT", "slope 20"}, {"Volume & Flow", "Volume Oscillator", "5,10"},
        {"Support/Resistance", "Pivot Points (Classic)", "PP,R1-R3,S1-S3"}, {"Support/Resistance", "Fibonacci Retracement", "23.6-78.6"},
        {"Support/Resistance", "Swing S/R + Trendlines", "fractal-based"},
        {"Candlestick Patterns", "Engulfing / Piercing / Dark Cloud", "2-candle"},
        {"Candlestick Patterns", "Hammer / Shooting Star", "wick ratio"},
        {"Candlestick Patterns", "Doji / Marubozu", "body ratio"},
        {"Candlestick Patterns", "Morning / Evening Star", "3-candle"},
        {"Candlestick Patterns", "Three Soldiers / Crows", "3-candle"},
        {"Candlestick Patterns", "Inside / Outside Bar", "range"},
        {"Harmonic Patterns", "Gartley / Bat", "fib ratios"}, {"Harmonic Patterns", "Butterfly / Crab", "fib ratios"},
        {"SMC (Smart Money)", "Break of Structure (BOS)", "swing close"},
        {"SMC (Smart Money)", "Fair Value Gap (FVG)", "3-candle"},
        {"SMC (Smart Money)", "Liquidity Sweep / Stop Hunt", "wick+close"},
        {"Sentiment", "Crypto Fear & Greed", "contrarian 20/80"}
    };

    /** Live indicator snapshot for one symbol — powers /api/indicators in the dashboard. */
    public Map<String, Object> indicatorSnapshot(String symbol) {
        Map<String, Object> out = new HashMap<>();
        List<Candle> k = loadCandles(symbol);
        if (k.size() < 60) {
            out.put("ok", false);
            out.put("reason", "not enough 1m candles for " + symbol + " (need 60, have " + k.size() + ")");
            return out;
        }
        Map<String, Object> v = new HashMap<>();
        double c = k.get(k.size() - 1).c;
        v.put("price", c);
        v.put("ema9", ema(k, 9)); v.put("ema21", ema(k, 21)); v.put("ema50", ema(k, 50));
        v.put("sma200", ema(k, 200));
        v.put("wma20", wma(k, 20)); v.put("hma21", hma(k, 21)); v.put("dema20", dema(k, 20));
        v.put("tema20", tema(k, 20)); v.put("kama", kama(k)); v.put("alma9", alma(k, 9, 0.85, 6));
        v.put("t3", t3(k, 5, 0.7)); v.put("zlema20", zlema(k, 20)); v.put("lsma25", lsma(k, 25));
        v.put("vwma20", vwma(k, 20)); v.put("mcginley14", mcginley(k, 14));
        double[] bb = bollinger(k, 20); if (bb != null) v.put("bb", bb);
        double[] kc = keltner(k, 20, 2); if (kc != null) v.put("keltner", kc);
        double[] dc = donchian(k, 20); if (dc != null) v.put("donchian", dc);
        double[] env = envelopes(k, 20, 2.5); if (env != null) v.put("envelopes", env);
        v.put("stdev20", stdev(k, 20)); v.put("atr14", atr(k, 14)); v.put("chandelier22", chandelier(k, 22, 3));
        double[] mac = macd(k); if (mac != null) v.put("macd", mac);
        double[] ad = adx(k, 14); if (ad != null) { v.put("adx", ad[0]); v.put("plusDi", ad[1]); v.put("minusDi", ad[2]); }
        double[] ps = psar(k); if (ps != null) { v.put("psar", ps[0]); v.put("psarBull", ps[1]); }
        double[] st = supertrend(k); if (st != null) { v.put("supertrend", st[0]); v.put("stDir", st[1]); }
        double[] ich = ichimoku(k); if (ich != null) v.put("ichimoku", ich);
        double[] ar = aroon(k, 14); if (ar != null) v.put("aroon", ar);
        double[] vx = vortex(k, 14); if (vx != null) v.put("vortex", vx);
        v.put("trix15", trix(k)); v.put("massIndex", massIndex(k));
        double[] alli = alligator(k); if (alli != null) v.put("alligator", alli);
        v.put("choppiness14", choppiness(k, 14)); v.put("schaff", schaff(k)); v.put("kst", kst(k));
        v.put("coppock", coppock(k));
        double[] ap = apoPpo(k); if (ap != null) v.put("ppo", ap[1]);
        v.put("dpo20", dpo(k, 20)); v.put("awesomeOsc", awesomeOsc(k));
        v.put("rsi14", rsi(k, 14));
        double[] stoch = stochastic(k, 14); if (stoch != null) v.put("stoch", stoch);
        double[] srsi = stochRsi(k); if (srsi != null) v.put("stochRsi", srsi);
        v.put("cci20", cci(k, 20)); v.put("williamsR", williamsR(k, 14)); v.put("roc9", roc(k, 9));
        v.put("tsi", tsi(k)); v.put("cmo14", cmo(k, 14)); v.put("fisher", fisher(k));
        v.put("deMarker", deMarker(k, 14)); v.put("smi", smi(k)); v.put("bop14", bop(k, 14));
        v.put("laguerreRsi", laguerreRsi(k)); v.put("rvi10", rvi(k, 10));
        double[] er = elderRay(k); if (er != null) v.put("elderRay", er);
        v.put("mfi14", mfi(k, 14)); v.put("obvSlope", obvSlope(k, 20)); v.put("adSlope", adSlope(k, 20));
        v.put("cmf20", cmf(k, 20)); v.put("chaikinOsc", chaikinOsc(k)); v.put("forceIndex", forceIndex(k, 13));
        v.put("eom14", eom(k, 14)); v.put("klinger", klinger(k)); v.put("pvtSlope", pvtSlope(k, 20));
        v.put("volumeOsc", volumeOsc(k)); v.put("vwap", vwap(k));
        double[] pp = pivotPoints(k); if (pp != null) v.put("pivots", pp);
        double[] fib = fibLevels(k); if (fib != null) v.put("fib", fib);
        double[] fr = fractals(k); if (fr != null) v.put("fractals", fr);
        Object[] candle = candlePattern(k); if (candle != null) { v.put("candlePattern", candle[0]); v.put("candleDir", candle[1]); }
        Object[] harm = harmonicPattern(k); if (harm != null) { v.put("harmonic", harm[0]); v.put("harmonicDir", harm[1]); }
        v.put("fvg", fvg(k)); v.put("bos", bosVoteCalc(k)); v.put("sweep", sweepVoteCalc(k));
        v.put("fearGreed", fngValue);
        out.put("ok", true);
        out.put("symbol", symbol);
        out.put("timeframe", TF);
        out.put("values", v);
        out.put("library", INDICATOR_LIBRARY);
        return out;
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
