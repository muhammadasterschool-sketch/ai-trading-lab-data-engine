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
 * EngineCore v5.8 — 1-MINUTE 24H SCANNER edition.
 * Loop (30s): risk check -> manage open trades -> refresh candles -> scan signals
 *   -> consensus gate (>=60% of 10 indicators) -> paper execute -> log everything.
 * Timeframe: 1m — paper trading decisions on the 1-minute chart, 24/7 nonstop.
 * Discovery (30 min): Binance ticker scan -> auto-register new instruments (top 150).
 * News (15 min): RSS -> sentiment -> high-impact pauses new entries 30 min.
 * The engine never sleeps: it runs day & night (24h market scan).
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
    private int activeSymbols = 0;
    private long scanCount = 0;             // 24h scanner heartbeat counter
    private volatile long lastScanAt = 0;

    public EngineCore(Db db) {
        this.db = db;
        seedStaticInstruments();
    }

    public void stop() { running = false; }
    public boolean isRunning() { return running; }

    // ================== MAIN LOOP ==================
    @Override public void run() {
        db.log("INFO", "SYSTEM", "ENGINE_START", "v5.8 phone engine — 1m timeframe, 24h nonstop market scanner");
        while (running) {
            try {
                long now = System.currentTimeMillis();
                if (now - lastLoop >= 30_000) { loop(); lastLoop = now; }
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

    // ================== STRATEGIES (10) ==================
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
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - 16; i < k.size() - 1; i++) { hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l); }
        double c = k.get(k.size() - 1).c;
        if (c > hh) return 1;
        if (c < ll) return -1;
        return 0;
    }

    // ---- v5.8 new strategy votes ----

    /** 6. Supertrend flip — follow the trend regime. */
    private int supertrendVote(List<Candle> k) {
        double[] st = supertrend(k);
        if (st == null) return 0;
        double[] stPrev = supertrend(k.subList(0, k.size() - 1));
        if (stPrev == null) return 0;
        if (stPrev[1] < 0 && st[1] > 0) return 1;   // flip up
        if (stPrev[1] > 0 && st[1] < 0) return -1;  // flip down
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

                int[] votes = {emaCross(k), rsiBollinger(k), macdStoch(k), vwapReversion(k), breakout(k),
                        supertrendVote(k), ichimokuVote(k), adxTrendVote(k), cciWilliamsVote(k),
                        mfiObvVote(k), psarAroonVote(k), stochRsiVote(k)};
                int buy = 0, sell = 0;
                for (int v : votes) { if (v > 0) buy++; else if (v < 0) sell++; }
                double consensusBuy = buy / (double) votes.length, consensusSell = sell / (double) votes.length;

                if (consensusBuy >= 0.6) { openTrade(uid, sym, "BUY", consensusBuy, k); open++; }
                else if (consensusSell >= 0.6) { openTrade(uid, sym, "SELL", consensusSell, k); open++; }
                else lastConsensus = "24h scan #" + scanCount + " — " + activeSymbols + " instruments on 1m — no >=60% consensus yet (best " + (int)(Math.max(consensusBuy, consensusSell) * 100) + "%)";
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
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at) VALUES(?,?,?,?,?,?,?, 'OPEN', 'CONSENSUS_12', ?, ?)",
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
        // v5.8 ALL-MARKET instrument universe — every major asset class.
        // CRYPTO  = traded live on Binance (paper money) — activated by discovery.
        // BROKER  = forex/metals/energy/indices — pending broker connection (live phase).
        String[][] statics = {
                // --- Metals ---
                {"XAUUSD", "GOLD", "PENDING_BROKER", "Gold spot XAU/USD"},
                {"XAGUSD", "SILVER", "PENDING_BROKER", "Silver spot XAG/USD"},
                {"XPTUSD", "PLATINUM", "PENDING_BROKER", "Platinum spot"},
                {"XPDUSD", "PALLADIUM", "PENDING_BROKER", "Palladium spot"},
                {"XCUUSD", "COPPER", "PENDING_BROKER", "Copper spot"},
                // --- Energy ---
                {"USOIL", "ENERGY", "PENDING_BROKER", "WTI Crude Oil"},
                {"UKOIL", "ENERGY", "PENDING_BROKER", "Brent Crude Oil"},
                {"NATGAS", "ENERGY", "PENDING_BROKER", "Natural Gas"},
                // --- Forex majors ---
                {"EURUSD", "FOREX", "PENDING_BROKER", "Euro / US Dollar"},
                {"GBPUSD", "FOREX", "PENDING_BROKER", "British Pound / US Dollar"},
                {"USDJPY", "FOREX", "PENDING_BROKER", "US Dollar / Japanese Yen"},
                {"USDCHF", "FOREX", "PENDING_BROKER", "US Dollar / Swiss Franc"},
                {"AUDUSD", "FOREX", "PENDING_BROKER", "Australian Dollar / US Dollar"},
                {"NZDUSD", "FOREX", "PENDING_BROKER", "New Zealand Dollar / US Dollar"},
                {"USDCAD", "FOREX", "PENDING_BROKER", "US Dollar / Canadian Dollar"},
                // --- Forex crosses ---
                {"EURGBP", "FOREX", "PENDING_BROKER", "Euro / Pound"},
                {"EURJPY", "FOREX", "PENDING_BROKER", "Euro / Yen"},
                {"EURCHF", "FOREX", "PENDING_BROKER", "Euro / Franc"},
                {"EURAUD", "FOREX", "PENDING_BROKER", "Euro / Aussie"},
                {"EURNZD", "FOREX", "PENDING_BROKER", "Euro / Kiwi"},
                {"EURCAD", "FOREX", "PENDING_BROKER", "Euro / Loonie"},
                {"GBPJPY", "FOREX", "PENDING_BROKER", "Pound / Yen"},
                {"GBPCHF", "FOREX", "PENDING_BROKER", "Pound / Franc"},
                {"GBPAUD", "FOREX", "PENDING_BROKER", "Pound / Aussie"},
                {"GBPNZD", "FOREX", "PENDING_BROKER", "Pound / Kiwi"},
                {"GBPCAD", "FOREX", "PENDING_BROKER", "Pound / Loonie"},
                {"AUDJPY", "FOREX", "PENDING_BROKER", "Aussie / Yen"},
                {"AUDNZD", "FOREX", "PENDING_BROKER", "Aussie / Kiwi"},
                {"AUDCAD", "FOREX", "PENDING_BROKER", "Aussie / Loonie"},
                {"AUDCHF", "FOREX", "PENDING_BROKER", "Aussie / Franc"},
                {"NZDJPY", "FOREX", "PENDING_BROKER", "Kiwi / Yen"},
                {"NZDCAD", "FOREX", "PENDING_BROKER", "Kiwi / Loonie"},
                {"NZDCHF", "FOREX", "PENDING_BROKER", "Kiwi / Franc"},
                {"CADJPY", "FOREX", "PENDING_BROKER", "Loonie / Yen"},
                {"CADCHF", "FOREX", "PENDING_BROKER", "Loonie / Franc"},
                {"CHFJPY", "FOREX", "PENDING_BROKER", "Franc / Yen"},
                // --- Indices ---
                {"US500", "INDEX", "PENDING_BROKER", "S&P 500"},
                {"NAS100", "INDEX", "PENDING_BROKER", "Nasdaq 100"},
                {"US30", "INDEX", "PENDING_BROKER", "Dow Jones 30"},
                {"GER40", "INDEX", "PENDING_BROKER", "DAX 40 (Germany)"},
                {"UK100", "INDEX", "PENDING_BROKER", "FTSE 100 (UK)"},
                {"FRA40", "INDEX", "PENDING_BROKER", "CAC 40 (France)"},
                {"EU50", "INDEX", "PENDING_BROKER", "Euro Stoxx 50"},
                {"JP225", "INDEX", "PENDING_BROKER", "Nikkei 225 (Japan)"},
                {"HK50", "INDEX", "PENDING_BROKER", "Hang Seng (Hong Kong)"},
                {"AUS200", "INDEX", "PENDING_BROKER", "ASX 200 (Australia)"},
                {"USDX", "INDEX", "PENDING_BROKER", "US Dollar Index"},
                {"VIX", "INDEX", "PENDING_BROKER", "Volatility Index"},
                // --- Binance-tradeable proxies (paper trade from day one) ---
                {"PAXGUSDT", "CRYPTO", "ACTIVE", "GOLD proxy — PAXG tracks spot gold 1:1"},
                {"EURUSDT", "CRYPTO", "ACTIVE", "EUR/USD proxy — Euro token on Binance"},
                // --- Crypto majors (also seeded so ledger shows them instantly) ---
                {"BTCUSDT", "CRYPTO", "ACTIVE", "Bitcoin"},
                {"ETHUSDT", "CRYPTO", "ACTIVE", "Ethereum"},
                {"BNBUSDT", "CRYPTO", "WATCHING", "BNB"},
                {"SOLUSDT", "CRYPTO", "WATCHING", "Solana"},
                {"XRPUSDT", "CRYPTO", "WATCHING", "XRP"},
                {"ADAUSDT", "CRYPTO", "WATCHING", "Cardano"},
                {"DOGEUSDT", "CRYPTO", "WATCHING", "Dogecoin"},
                {"AVAXUSDT", "CRYPTO", "WATCHING", "Avalanche"},
                {"DOTUSDT", "CRYPTO", "WATCHING", "Polkadot"},
                {"LINKUSDT", "CRYPTO", "WATCHING", "Chainlink"},
                {"TRXUSDT", "CRYPTO", "WATCHING", "TRON"},
                {"LTCUSDT", "CRYPTO", "WATCHING", "Litecoin"},
                {"BCHUSDT", "CRYPTO", "WATCHING", "Bitcoin Cash"},
                {"ATOMUSDT", "CRYPTO", "WATCHING", "Cosmos"},
                {"XLMUSDT", "CRYPTO", "WATCHING", "Stellar"},
                {"NEARUSDT", "CRYPTO", "WATCHING", "NEAR Protocol"},
                {"APTUSDT", "CRYPTO", "WATCHING", "Aptos"},
                {"OPUSDT", "CRYPTO", "WATCHING", "Optimism"},
                {"ARBUSDT", "CRYPTO", "WATCHING", "Arbitrum"},
                {"FILUSDT", "CRYPTO", "WATCHING", "Filecoin"},
                {"INJUSDT", "CRYPTO", "WATCHING", "Injective"},
                {"SUIUSDT", "CRYPTO", "WATCHING", "Sui"},
                {"TONUSDT", "CRYPTO", "WATCHING", "Toncoin"},
                {"PEPEUSDT", "CRYPTO", "WATCHING", "Pepe"},
                {"SHIBUSDT", "CRYPTO", "WATCHING", "Shiba Inu"},
        };
        for (String[] s : statics) {
            db.getWritableDatabase().execSQL(
                    "INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,?,?,?,?,?,?,?)",
                    new Object[]{s[0], s[0], "USD", s[2].equals("ACTIVE") ? "BINANCE" : "BROKER", s[1], s[2], s[2].equals("ACTIVE") ? 5000 : 0, System.currentTimeMillis(), s[3]});
        }
        // upgrade path: force-activate the always-on proxies even on existing installs
        db.getWritableDatabase().execSQL("UPDATE instruments SET status='ACTIVE' WHERE symbol IN ('PAXGUSDT','EURUSDT','BTCUSDT','ETHUSDT')");
        if (db.setting("seeded_v58", "0").equals("0")) {
            db.setSetting("seeded_v58", "1");
            db.log("INFO", "DISCOVERY", "ALL_MARKET_SEED", "v5.8 all-market universe registered: metals, energy, 28 forex pairs, 12 indices, crypto majors (" + statics.length + " instruments)");
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
        m.put("timeframe", TF);
        m.put("scanner", "24h");
        m.put("scan_count", scanCount);
        m.put("last_scan_at", lastScanAt);
        m.put("strategy_count", 12);
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
