package com.aitradinglab.engine;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import com.aitradinglab.engine.AiTrainer;
import com.aitradinglab.engine.EngineCore;
import com.aitradinglab.engine.StrategyPack;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.TimeZone;
import java.util.TreeMap;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

/* loaded from: classes.dex */
public class EngineCore implements Runnable {
    private static final int ACTIVE_TOP = 40;
    private static final String[] BEAR;
    private static final String BINANCE_HOST = "https://api.binance.com";
    static final Map<String, String> BINANCE_PAIRS;
    static final String[][] BINANCE_UNIVERSE;
    private static final Map<String, String> BUCKET;
    private static final String[] BULL;
    private static final long CONSEC_LOSS_COOLDOWN_MS = 3600000;
    private static final int CONSEC_LOSS_DEFAULT = 3;
    private static final String[] FEEDS;
    private static final String[] HIGH_IMPACT;
    public static final String[][] INDICATOR_LIBRARY;
    public static final int MIN_TRADES_BEFORE_SCALING = 25;
    static final Set<String> PB_SYMBOLS;
    private static final double RISK_DEFAULT_PCT = 1.0d;
    public static final String[][] SHAAKUNI_SUITE;
    static final Set<String> STABLE_BASES;
    public static final String[][] STRATEGY_META = {new String[]{"3C Breakout (M1) — MASTER", "Price action"}, new String[]{"PDF PACK S1-S9 (5m, ALL pairs)", "Mechanical"}, new String[]{"SHAAKUNI SSM playbooks x5", "SMC"}};
    public static final double TAKER_FEE = 5.0E-4d;
    private static final String TF = "5m";
    static final String TF15 = "5m";
    static final long TF15_MS = 300000;
    private static final long TF_MS = 300000;
    public static final long TF_MS_PUB = 300000;
    public static final double THREEC_BODY_MIN = 0.7d;
    public static final double THREEC_TP_R = 3.0d;
    public static final int THREEC_WINDOW = 5;
    static final double X7_ADX_MAX = 22.0d;
    static final double X7_RSI_HI = 70.0d;
    static final double X7_RSI_LO = 30.0d;
    static final double X7_SIGMA = 3.5d;
    static final double X7_SL_ATR = 1.0d;
    static final double X7_TP_R = 2.5d;
    private static Context appCtxRef;
    private JSONObject aiWeightsCache;
    private final Db db;
    public StrategyLab lab;
    private volatile boolean running = true;
    // v1.4 LIVE TICK — 1-second Binance price cache (owner: "data 1 sec mai ana chahiye, live P&L chahiye")
    // map: symbol -> [price, tsMs]; livePxLoop har 1s update karta hai (batch ticker/price, weight 2)
    private final java.util.concurrent.ConcurrentHashMap<String, double[]> livePx = new java.util.concurrent.ConcurrentHashMap<String, double[]>();
    private volatile boolean livePxLogged = false;
    private String dataHost = "BINANCE-SPOT";
    private long lastDiscovery = 0;
    private long lastNews = 0;
    private long lastLoop = 0;
    private long lastEvolve = 0;
    private String lastConsensus = "";
    private int activeSymbols = 0;
    private long scanCount = 0;
    private volatile long lastScanAt = 0;
    private volatile int fngValue = -1;
    private long lastFng = 0;
    private long lastYt = 0;
    private String lastPattern = "";
    public volatile int[] lastVotes = new int[1];
    public volatile String lastVoteSym = "-";
    public final Map<String, String> threecStates = new HashMap();
    private final LinkedHashSet<String> threecLogged = new LinkedHashSet<>();
    private final Map<String, Long> cooldownUntil = new HashMap();
    private final Set<String> cooldownLogged = new HashSet();
    private final Set<String> killLogged = new HashSet();
    private final Map<String, Long> backoffUntil = new HashMap();
    private volatile boolean safeMode = false;
    private volatile long safeModeSince = 0;
    private long lastDegCheck = 0;
    private final Map<String, JSONObject> seasonCache = new HashMap();
    private JSONObject mlWeights = null;
    private boolean mlLoaded = false;
    final Set<String> binanceOkCache = Collections.synchronizedSet(new HashSet());
    private final Map<String, Long> lastFetchAt = new HashMap();
    private final List<String> rot15 = new ArrayList();
    private int rot15Pos = 0;
    private final Map<String, Long> lastEval15 = new HashMap();
    private final Map<String, double[]> fundingCache = new HashMap();
    private long fundingAt = 0;
    private long aiWeightsAt = 0;
    private final Map<String, Long> lastPbFill = new HashMap();
    private final Map<String, Long> lastEvalPb = new HashMap();
    private final Map<String, Long> lastEvalX7 = new HashMap();
    private long lastAiTrainCheck = 0;
    volatile boolean aiTraining = false;
    private final Map<String, Long> tradeAskAt = new HashMap();
    private long lastUniverseSync = 0;

    public static class Candle {
        double c = 0.0d;
        double h = 0.0d;
        double l = 0.0d;
        double o = 0.0d;
        long ts = 0L;
        double v = 0.0d;
    }

    public static class Setup3C {
        double boundary = 0.0d;
        long c3Ts = 0L;
        String side = null;
        double slPrice = 0.0d;
        double trigger = 0.0d;
        double zoneHigh = 0.0d;
        double zoneLow = 0.0d;
        int c3Idx = -1;
        double c3Body = 0.0d;
        double c3VolRatio = 0.0d;
        double c3AtrPct = 0.0d;
        double c3EmaDist = 0.0d;
        double c3RdPct = 0.0d;
    }

    public static class StructEvent {
        public double level;
        public String kind = "";
        public String dir = "";
        public int idx = -1;
    }

    static boolean latchSafeMode(boolean z, int i, int i2) {
        if (i < 5) {
            return z;
        }
        double d = (i2 * 100.0d) / i;
        if (!z && d <= 20.0d) {
            return true;
        }
        if (!z || d < 60.0d) {
            return z;
        }
        return false;
    }

    private boolean marketClosedET() {
        return false;
    }

    public double riskPct() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("risk_pct", String.valueOf(1.0d)));
            if (parseDouble < 0.1d) {
                parseDouble = 0.1d;
            }
            if (parseDouble > 20.0d) {
                return 20.0d;
            }
            return parseDouble;
        } catch (Exception unused) {
            return 1.0d;
        }
    }

    public double takerFee() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("fee_bps", "5"));
            if (parseDouble < 0.0d) {
                parseDouble = 0.0d;
            }
            if (parseDouble > 100.0d) {
                parseDouble = 100.0d;
            }
            return parseDouble / 10000.0d;
        } catch (Exception unused) {
            return 5.0E-4d;
        }
    }

    public double levCap() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("lev_cap", "0").trim());
            if (parseDouble <= 0.0d) {
                return 1000000.0d; // v1.2 RISK FIX: 0 = UNCAPPED — har trade poora risk% (default 1%) leta hai; notional clamp sirf tab jab owner khud cap set kare (0.1x–10x)
            }
            if (parseDouble < 0.1d) {
                parseDouble = 0.1d;
            }
            if (parseDouble > 10.0d) {
                return 10.0d;
            }
            return parseDouble;
        } catch (Exception unused) {
            return 1000000.0d;
        }
    }

    // v1.3 OWNER RULE: RISK 1% ON EVERY TRADE — win-rate scaling REMOVED.
    // Har trade (MIN25 filler, PDF, PB, X7, 3C, Lab) EXACT riskPct% (default 1%) of balance risks karta hai.
    // Consensus/council sirf ye decide karta hai ke 25 ke BAAD aur kitne trades KHULEN — risk size kabhi scale nahi hota.
    public double dynamicRiskPct(String str) {
        return riskPct();
    }

    public String scalingInfo(String str) {
        int i = 0;
        int i2 = 0;
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) FROM trades WHERE strategy=? AND status='CLOSED'", new String[]{str});
            if (rawQuery.moveToFirst()) {
                int i3 = rawQuery.getInt(0);
                try {
                    i = rawQuery.getInt(1);
                    i2 = i3;
                } catch (Throwable unused) {
                    i = 0;
                    i2 = i3;
                }
            } else {
                i = 0;
            }
            try {
                rawQuery.close();
            } catch (Throwable unused2) {
            }
        } catch (Throwable unused3) {
            i = 0;
        }
        // v1.3 FLAT RISK — scaling removed (owner: "Risk should be 1 percent on every trade")
        return "flat risk " + riskPct() + "% — har trade EXACT (win-rate scaling OFF)";
    }

    private double bufSetting(String str) {
        try {
            double parseDouble = Double.parseDouble(this.db.setting(str, "0"));
            double d = parseDouble >= 0.0d ? parseDouble : 0.0d;
            if (d > 1.0d) {
                d = 1.0d;
            }
            return d / 100.0d;
        } catch (Exception unused) {
            return 0.0d;
        }
    }

    // v4.6 OWNER TUNE — sab settings owner override kar sakta hai (DB settings table)
    public double threecTpR() {
        try {
            double d = Double.parseDouble(this.db.setting("threec_tp_r", "3.0").trim());
            if (d < 0.5d) return 0.5d;
            if (d > 10.0d) return 10.0d;
            return d;
        } catch (Exception unused) {
            return 3.0d;
        }
    }

    public double threecVolMin() {
        try {
            double d = Double.parseDouble(this.db.setting("threec_vol_min", "0").trim());
            if (d < 0.0d) return 0.0d;
            if (d > 10.0d) return 10.0d;
            return d;
        } catch (Exception unused) {
            return 0.0d;
        }
    }

    public String threecSide() {
        try {
            String s = this.db.setting("threec_side", "BOTH").trim().toUpperCase(Locale.US);
            if ("BUY".equals(s) || "SELL".equals(s)) return s;
            return "BOTH";
        } catch (Exception unused) {
            return "BOTH";
        }
    }

    // v4.7 MIN-25 CONCURRENT — owner rule: minimum 25 trades ek sath OPEN.
    public int minOpenTrades() {
        try {
            int i = Integer.parseInt(this.db.setting("min_open_trades", "25").trim());
            if (i < 0) return 0;
            return Math.min(i, 40);
        } catch (Exception unused) {
            return 25;
        }
    }

    public boolean universeMajors() {
        try {
            return "MAJORS".equals(this.db.setting("universe_mode", "ALL").trim().toUpperCase(Locale.US));
        } catch (Exception unused) {
            return false;
        }
    }

    private static final String[] MAJOR_PAIRS = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"};

    public int cooldownMin() {
        try {
            int parseDouble = (int) Double.parseDouble(this.db.setting("cooldown_min", "15"));
            if (parseDouble < 0) {
                parseDouble = 0;
            }
            if (parseDouble > 240) {
                return 240;
            }
            return parseDouble;
        } catch (Exception unused) {
            return 15;
        }
    }

    public int consecLossN() {
        try {
            int parseDouble = (int) Double.parseDouble(this.db.setting("consec_loss", String.valueOf(CONSEC_LOSS_DEFAULT)));
            if (parseDouble < 0) {
                parseDouble = 0;
            }
            if (parseDouble > 10) {
                return 10;
            }
            return parseDouble;
        } catch (Exception unused) {
            return CONSEC_LOSS_DEFAULT;
        }
    }

    public double dailyKillPct() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("daily_kill_pct", "0"));
            double d = parseDouble >= 0.0d ? parseDouble : 0.0d;
            if (d > 90.0d) {
                return 90.0d;
            }
            return d;
        } catch (Exception unused) {
            return 0.0d;
        }
    }

    public double slipBps() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("slip_bps", "2"));
            if (parseDouble < 0.0d) {
                parseDouble = 0.0d;
            }
            if (parseDouble > 50.0d) {
                return 50.0d;
            }
            return parseDouble;
        } catch (Exception unused) {
            return 2.0d;
        }
    }

    public double heatMaxPct() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("heat_max_pct", "0"));
            double d = parseDouble >= 0.0d ? parseDouble : 0.0d;
            if (d > 100.0d) {
                return 100.0d;
            }
            return d;
        } catch (Exception unused) {
            return 0.0d;
        }
    }

    public double bucketMaxPct() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("bucket_max_pct", "0"));
            double d = parseDouble >= 0.0d ? parseDouble : 0.0d;
            if (d > 100.0d) {
                return 100.0d;
            }
            return d;
        } catch (Exception unused) {
            return 0.0d;
        }
    }

    public int councilMin() {
        try {
            int parseDouble = (int) Double.parseDouble(this.db.setting("council_min", "0"));
            int i = parseDouble >= 0 ? parseDouble : 0;
            if (i > 95) {
                return 95;
            }
            return i;
        } catch (Exception unused) {
            return 0;
        }
    }

    public boolean eventGateOn() {
        return "1".equals(this.db.setting("event_gate", "0"));
    }

    public boolean autoPauseDegraded() {
        return "1".equals(this.db.setting("auto_pause", "0"));
    }

    public boolean bridgeLive() {
        return "1".equals(this.db.setting("bridge_live", "0"));
    }

    public boolean sessionFilterOn() {
        return "1".equals(this.db.setting("session_filter", "0"));
    }

    public double bridgeLots() {
        try {
            double parseDouble = Double.parseDouble(this.db.setting("bridge_lots", "0.01"));
            double d = parseDouble >= 0.01d ? parseDouble : 0.01d;
            if (d > 100.0d) {
                return 100.0d;
            }
            return d;
        } catch (Exception unused) {
            return 0.01d;
        }
    }

    public List<Candle> recentCandles(String str, int i) {
        ArrayList arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT " + Math.max(1, Math.min(500, i)), new String[]{str, "5m"});
        while (rawQuery.moveToNext()) {
            Candle candle = new Candle();
            candle.ts = rawQuery.getLong(0);
            candle.o = rawQuery.getDouble(1);
            candle.h = rawQuery.getDouble(2);
            candle.l = rawQuery.getDouble(CONSEC_LOSS_DEFAULT);
            candle.c = rawQuery.getDouble(4);
            candle.v = rawQuery.getDouble(5);
            arrayList.add(candle);
        }
        rawQuery.close();
        Collections.reverse(arrayList);
        return arrayList;
    }

    static {
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        BINANCE_PAIRS = linkedHashMap;
        linkedHashMap.put("BTCUSDT", "BTC/USDT — Bitcoin (MAJOR)");
        linkedHashMap.put("ETHUSDT", "ETH/USDT — Ethereum (MAJOR)");
        linkedHashMap.put("BNBUSDT", "BNB/USDT — BNB (MAJOR)");
        linkedHashMap.put("SOLUSDT", "SOL/USDT — Solana (MAJOR)");
        linkedHashMap.put("XRPUSDT", "XRP/USDT — XRP (RETAIL)");
        linkedHashMap.put("DOGEUSDT", "DOGE/USDT — Dogecoin (RETAIL)");
        linkedHashMap.put("ADAUSDT", "ADA/USDT — Cardano (RETAIL)");
        STABLE_BASES = new HashSet(Arrays.asList("USDC", "TUSD", "FDUSD", "BUSD", "DAI", "USDP", "EUR", "GBP", "TRY", "BRL", "ARS", "UAH", "JPY", "AEUR", "USDS", "SUSD", "XUSD", "USD1", "EURI", "GYEN", "PAXG"));
        PB_SYMBOLS = new HashSet(Arrays.asList("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"));
        String[][] strArr = {new String[]{"BTCUSDT", "MAJOR", "Bitcoin — Binance spot"}, new String[]{"ETHUSDT", "MAJOR", "Ethereum — Binance spot"}, new String[]{"BNBUSDT", "MAJOR", "BNB — Binance spot"}, new String[]{"SOLUSDT", "MAJOR", "Solana — Binance spot"}, new String[]{"XRPUSDT", "RETAIL", "XRP — Binance spot"}, new String[]{"DOGEUSDT", "RETAIL", "Dogecoin — Binance spot"}, new String[]{"ADAUSDT", "RETAIL", "Cardano — Binance spot"}};
        BINANCE_UNIVERSE = strArr;
        FEEDS = new String[]{"https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss"};
        BULL = new String[]{"surge", "rally", "gain", "record", "adopt", "approval", "approved", "bullish", "soar", "jump", "rise", "up", "inflow", "upgrade", "breakout"};
        BEAR = new String[]{"crash", "plunge", "ban", "hack", "lawsuit", "drop", "fall", "bearish", "sink", "loss", "outflow", "downgrade", "sell-off", "fear"};
        HIGH_IMPACT = new String[]{"fed", "fomc", "rate", "cpi", "inflation", "sec", "etf", "binance", "hack", "war", "sanction", "tariff", "default", "emergency"};
        BUCKET = new HashMap();
        for (String[] strArr2 : strArr) {
            BUCKET.put(strArr2[0], strArr2[1]);
        }
        String[][] strArr3 = {new String[]{"Liquidity", "PDH / PDL (prev day high-low)", "stop-cluster levels"}, new String[]{"Liquidity", "PWH / PWL (prev week high-low)", "HTF stop-cluster"}, new String[]{"Liquidity", "Liquidity Sweep (stop hunt)", "wick beyond + close back inside"}, new String[]{"Liquidity", "EQ Equilibrium 50%", "premium above / discount below"}, new String[]{"Structure", "MSS (Market Structure Shift)", "close beyond N=10 swing, swing >= 3 bars old"}, new String[]{"Structure", "BOS (Break of Structure)", "continuation break (same direction)"}, new String[]{"POI", "Order Block (OB)", "last opposite candle before impulse >= 0.7x ATR(14); untouched only"}, new String[]{"POI", "Mitigation Block", "OB revisit after MSS — sniper entry zone"}, new String[]{"POI", "FVG (Fair Value Gap)", "3-candle imbalance, unfilled"}, new String[]{"Session", "Killzones (New York time)", "Asian 20-00 / London 02-05 / NY 07-10 / LDN Close 10-12"}, new String[]{"Session", "Sweep Status Panel", "Sweep! / Broken / Active per liquidity level"}, new String[]{"Filter", "Premium / Discount", "buy in discount (below EQ), sell in premium (above EQ)"}, new String[]{"Candle", "OHLC + Inside Bar OB + 3-Candle", "Shaakuni shorts setups (candlePattern)"}};
        SHAAKUNI_SUITE = strArr3;
        INDICATOR_LIBRARY = strArr3;
    }

    public EngineCore(Db db) {
        this.db = db;
        seedStaticInstruments();
        try {
            this.lab = new StrategyLab(appContext(), db, this);
        } catch (Throwable unused) {
            this.lab = null;
        }
    }

    public static void appContext(Context context) {
        appCtxRef = context;
    }

    private static Context appContext() {
        return appCtxRef;
    }

    public List<Candle> klinesFor(String str, int i) {
        return fetchKlines(str, i, true);
    }

    public void stop() {
        this.running = false;
    }

    public boolean isRunning() {
        return this.running;
    }

    @Override // java.lang.Runnable
    public void run() {
        this.db.log("INFO", "SYSTEM", "ENGINE_START", "v3.0 QUANT PRO — all 5 upgrades: [P1 PRO RISK] portfolio heat + bucket caps (opt-in), slippage/spread model, SAFE MODE stale guard, feed backoff+retry, TRUE drawdown (peak ratchet), index-window session-gap fix, persistent guards | [P2 HONEST LAB] fees+IS/OOS walk-forward+Monte Carlo in Lab backtest, EMA200 SMA-seed fix | [P3 EDGE ANALYTICS] journal R/MFE/MAE/TCA, daily P&L, per-symbol, monthly heatmap, seasonality | [P4 AI QUANT] Signal Council (4 analysts, tag+opt-in gate), ML-lite (FreqAI-inspired logistic retrain), degradation monitor, event gate | [P5 LIVE READY] order lifecycle (orders table), MT5 bridge LIVE MIRROR (owner opt-in) | 3C MASTER rules UNTOUCHED | risk " + riskPct() + "% | UNLIMITED daily P/L default — kill/heat/event sab opt-in");
        if (!"1".equals(this.db.setting("v12_paper_100", "0"))) {
            long currentTimeMillis = System.currentTimeMillis();
            try {
                this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'", new Object[]{Long.valueOf(currentTimeMillis)});
                this.db.getWritableDatabase().execSQL("UPDATE accounts SET balance=100, start_balance=100, peak=100, day_start=100, day_ts=?", new Object[]{Long.valueOf(currentTimeMillis / 86400000)});
                this.db.setSetting("v12_paper_100", "1");
                this.db.log("INFO", "ACCOUNT", "PAPER_RESET_100", "v1.2 one-time reset — paper accounts set to $100 (old $100,000 default retired), open trades cancelled. Apna amount Settings > Paper Balance se kabhi bhi badal sakte hain.");
            } catch (Throwable th) {
                this.db.log("ERROR", "ACCOUNT", "PAPER_RESET_FAIL", String.valueOf(th));
            }
        }
        if (!"1".equals(this.db.setting("v14_3c_migration", "0"))) {
            try {
                this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'", new Object[]{Long.valueOf(System.currentTimeMillis())});
                this.db.getWritableDatabase().execSQL("DELETE FROM candles WHERE tf<>'5m'");
                this.db.setSetting("v14_3c_migration", "1");
                this.db.log("INFO", "SYSTEM", "MIGRATION_3C", "v1.4 — 35-strategy consensus RETIRED, 3C MASTER (M5) installed; old open trades cancelled, 1m candles purged. Daily loss/profit now UNLIMITED (owner request).");
            } catch (Throwable th2) {
                this.db.log("ERROR", "SYSTEM", "MIGRATION_3C_FAIL", String.valueOf(th2));
            }
        }
        if (!"1".equals(this.db.setting("v45_tf5m_migration", "0"))) {
            try {
                this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'", new Object[]{Long.valueOf(System.currentTimeMillis())});
                this.db.getWritableDatabase().execSQL("DELETE FROM candles WHERE tf<>'5m'");
                this.db.setSetting("v45_tf5m_migration", "1");
                this.db.log("INFO", "SYSTEM", "MIGRATION_5M", "v4.5 — poora system 5m timeframe (3C + PDF pack + scan). Open trades cancelled (purane TF setups), 1m/15m candles purged. Balances unchanged.");
            } catch (Throwable th3) {
                this.db.log("ERROR", "SYSTEM", "MIGRATION_5M_FAIL", String.valueOf(th3));
            }
        }
        if (!"1".equals(this.db.setting("v12_risk_sizing_fix", "0"))) {
            try {
                String lc0 = this.db.setting("lev_cap", "").trim();
                boolean uncap = true;
                if (!lc0.isEmpty()) {
                    double lcv = Double.parseDouble(lc0);
                    uncap = lcv <= 0.0d || lcv == 0.95d; // owner ka khud ka TURBO cap (2/3/5/10) preserve hota hai
                }
                if (uncap) {
                    this.db.setSetting("lev_cap", "0");
                }
                this.db.setSetting("fee_max_r", "0.5");
                this.db.setSetting("v12_risk_sizing_fix", "1");
                this.db.log("INFO", "RISK", "V12_RISK_FIX", "1% RISK FIX: notional cap 0.95 (spot) → UNCAPPED (har trade ab poora risk% — default 1% — leta hai; pehle clamp ki wajah se sirf ~0.05% risk lag raha tha) + fee guard ab R-aware (fees+slip TP ke 0.5R se zyada nahi — pehle 0.14% floor EXACTLY RT cost thi, isliye profit 0 se upar nahi jata tha). Balances/trades/login sab unchanged.");
            } catch (Throwable th4) {
                this.db.setSetting("lev_cap", "0");
                this.db.setSetting("fee_max_r", "0.5");
                this.db.setSetting("v12_risk_sizing_fix", "1");
                this.db.log("ERROR", "RISK", "V12_RISK_FIX_FAIL", String.valueOf(th4));
            }
        }
        // v4.6 OWNER TUNE — 30-day Binance 5m backtest (QuantSim, real klines) se tuned config.
        // Har setting owner dashboard/settings se badal sakta hai — ye sirf defaults set karta hai.
        if (!"1".equals(this.db.setting("v46_owner_tune", "0"))) {
            try {
                this.db.setSetting("threec_tp_r", "1.5");      // TP 3R -> 1.5R (winrate 25% -> 61%)
                this.db.setSetting("threec_vol_min", "1.0");   // C3 volume ratio >= 1.0 quality filter
                this.db.setSetting("threec_side", "SELL");     // sim: SELL side positive expectancy, BUY side negative
                this.db.setSetting("universe_mode", "MAJORS"); // sirf BTC/ETH/BNB/SOL (majors par edge, alts par nahi)
                this.db.setSetting("paused_X7:REGIME_FADE", "1"); // X7 VWAP fade sim me losing — paused (owner re-enable kar sakta hai)
                this.db.setSetting("v46_owner_tune", "1");
                this.db.log("INFO", "RISK", "V46_OWNER_TUNE", "STRATEGY TUNE (30d real-data backtest): 3C TP 1.5R + vol filter 1.0 + SELL-only + MAJORS-only universe + X7 paused. 1% risk per trade unchanged. Owner in settings ko kabhi bhi badal sakta hai.");
            } catch (Throwable th5) {
                this.db.log("ERROR", "RISK", "V46_OWNER_TUNE_FAIL", String.valueOf(th5));
            }
        }
        // v4.7 MIN-25 CONCURRENT — owner rule: kam az kam 25 trades ek sath OPEN hone chahiye.
        // Pehle MAJORS-only (4 syms × 1 trade/symbol) + SELL-only the — isliye kabhi 25 concurrent nahi khul rahe the.
        if (!"1".equals(this.db.setting("v47_min25", "0"))) {
            try {
                this.db.setSetting("universe_mode", "ALL");    // ALL Binance USDT universe — 25 concurrent possible
                this.db.setSetting("threec_side", "BOTH");     // SELL-only trade count aadha kar raha tha
                this.db.setSetting("min_open_trades", "25");   // MIN 25 concurrent OPEN (owner editable)
                this.db.setSetting("lev_cap", "0");            // re-affirm uncapped — har trade poora risk% (1%) le
                this.db.setSetting("v47_min25", "1");
                this.db.log("INFO", "SYSTEM", "V47_MIN25", "MIN-25 CONCURRENT ON: universe ALL + side BOTH + min_open_trades=25. Nizam: 25 se KAM open trades → engine best momentum setups se fill karta hai (har trade EXACT 1% risk, ATR SL, TP 1.5R). 25 hone ke BAAD filler band — naye trades sirf consensus par (3C breakout + council; risk hamesha FLAT 1%). Balances/login/data unchanged.");
            } catch (Throwable th6) {
                this.db.log("ERROR", "SYSTEM", "V47_MIN25_FAIL", String.valueOf(th6));
            }
        }
        loadGuardState();
        // v1.4 LIVE TICK thread — 1 second Binance price (live market + live P&L)
        try {
            Thread pxThread = new Thread(new Runnable() {
                public void run() {
                    livePxLoop();
                }
            }, "ATL-LIVEPX");
            pxThread.setDaemon(true);
            pxThread.start();
        } catch (Throwable thPx) {
            this.db.log("WARN", "FEED", "LIVEPX_FAIL", String.valueOf(thPx));
        }
        while (this.running) {
            try {
                long currentTimeMillis2 = System.currentTimeMillis();
                if (currentTimeMillis2 - this.lastLoop >= 10000) {
                    loop();
                    this.lastLoop = currentTimeMillis2;
                }
                if (currentTimeMillis2 - this.lastDiscovery >= 1800000) {
                    discover();
                    this.lastDiscovery = currentTimeMillis2;
                }
                if (currentTimeMillis2 - this.lastNews >= 900000) {
                    fetchNews();
                    this.lastNews = currentTimeMillis2;
                }
                if (currentTimeMillis2 - this.lastFng >= CONSEC_LOSS_COOLDOWN_MS) {
                    fetchFearGreed();
                    this.lastFng = currentTimeMillis2;
                }
                if (currentTimeMillis2 - this.lastYt >= 900000) {
                    this.lastYt = currentTimeMillis2;
                    StrategyLab strategyLab = this.lab;
                    if (strategyLab != null) {
                        try {
                            strategyLab.watchYouTube();
                        } catch (Throwable th4) {
                            this.db.log("ERROR", "LAB", "YT_WATCH_FAIL", String.valueOf(th4));
                        }
                    }
                }
                if (currentTimeMillis2 - this.lastEvolve >= 21600000) {
                    this.lastEvolve = currentTimeMillis2;
                    StrategyLab strategyLab2 = this.lab;
                    if (strategyLab2 != null) {
                        try {
                            strategyLab2.autoEvolve();
                        } catch (Throwable th5) {
                            this.db.log("ERROR", "LAB", "EVOLVE_FAIL", String.valueOf(th5));
                        }
                    }
                }
                try {
                    aiTrainTick();
                } catch (Throwable unused) {
                }
                Thread.sleep(2000L);
            } catch (Throwable th6) {
                this.db.log("ERROR", "SYSTEM", "LOOP_ERROR", String.valueOf(th6) + " @ " + (th6.getStackTrace().length > 0 ? th6.getStackTrace()[0] : "?") + " ← " + (th6.getStackTrace().length > 1 ? th6.getStackTrace()[1] : "?") + " ← " + (th6.getStackTrace().length > 2 ? th6.getStackTrace()[2] : "?"));
                try {
                    Thread.sleep(5000L);
                } catch (InterruptedException unused2) {
                    return;
                }
            }
        }
        this.db.log("INFO", "SYSTEM", "ENGINE_STOP", "engine stopped");
    }

    private void loop() {
        long currentTimeMillis = System.currentTimeMillis();
        if (currentTimeMillis - this.lastDegCheck >= 1800000) {
            this.lastDegCheck = currentTimeMillis;
            degradationCheck();
        }
        if (!"1".equals(this.db.setting("engine_on", "1"))) {
            this.lastConsensus = "engine off";
            return;
        }
        rollDay();
        // v4.7 STAGE ISOLATION — ek stage ka fail doosri stage ko bhookha na chhode
        try {
            manageOpenTrades();
        } catch (Throwable thStage1) {
            this.db.log("ERROR", "SYSTEM", "STAGE_FAIL", "manageOpenTrades: " + String.valueOf(thStage1));
        }
        try {
            refreshCandles();
        } catch (Throwable thStage2) {
            this.db.log("ERROR", "SYSTEM", "STAGE_FAIL", "refreshCandles: " + String.valueOf(thStage2));
        }
        try {
            scanAndTrade();
        } catch (Throwable thStage3) {
            this.db.log("ERROR", "SYSTEM", "STAGE_FAIL", "scanAndTrade: " + String.valueOf(thStage3));
        }
        try {
            ensureMinOpen();
        } catch (Throwable thMin25) {
            this.db.log("ERROR", "MIN25", "FILL_FAIL", String.valueOf(thMin25));
        }
        try {
            scanPdfPack();
        } catch (Throwable th) {
            this.db.log("ERROR", "PACK", "SCAN_FAIL", String.valueOf(th));
        }
        try {
            scanPlaybook();
        } catch (Throwable th2) {
            this.db.log("ERROR", "PB", "SCAN_FAIL", String.valueOf(th2));
        }
        try {
            scanX7();
        } catch (Throwable th3) {
            this.db.log("ERROR", "X7", "SCAN_FAIL", String.valueOf(th3));
        }
        snapshotEquity();
        try {
            selfLearnTick();
        } catch (Throwable unused) {
        }
        this.scanCount++;
        this.lastScanAt = System.currentTimeMillis();
    }

    private void rollDay() {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT user_id, day_ts FROM accounts", null);
        ArrayList arrayList = new ArrayList();
        ArrayList arrayList2 = new ArrayList();
        while (rawQuery.moveToNext()) {
            arrayList.add(Long.valueOf(rawQuery.getLong(0)));
            arrayList2.add(Long.valueOf(rawQuery.getLong(1)));
        }
        rawQuery.close();
        long currentTimeMillis = System.currentTimeMillis() / 86400000;
        for (int i = 0; i < arrayList.size(); i++) {
            if (((Long) arrayList2.get(i)).longValue() != currentTimeMillis) {
                Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?", new String[]{String.valueOf(arrayList.get(i))});
                if (rawQuery2.moveToFirst()) {
                    this.db.getWritableDatabase().execSQL("UPDATE accounts SET day_ts=?, day_start=? WHERE user_id=?", new Object[]{Long.valueOf(currentTimeMillis), Double.valueOf(rawQuery2.getDouble(0)), arrayList.get(i)});
                }
                rawQuery2.close();
            }
        }
    }

    static String bucketForRank(int i) {
        if (i <= 10) {
            return "MAJOR";
        }
        if (i <= 60) {
            return "RETAIL";
        }
        return "ALTCOIN";
    }

    public String mt5Bridge() {
        String str = this.db.setting("mt5_bridge", "");
        return str == null ? "" : str.trim();
    }

    private List<Candle> fetchKlines(String str, int i) {
        return fetchKlines(str, i, false);
    }

    private List<Candle> fetchKlines(String str, int i, boolean z) {
        List<Candle> fetchFromBridge = null;
        long j = 0L;
        long j2 = 60000;
        if (!z) {
            Long l = this.lastFetchAt.get(str);
            try {
                j = Math.max(20, Integer.parseInt(this.db.setting("feed_interval_sec", "60").trim())) * 1000;
            } catch (Exception unused) {
                j = 60000;
            }
            if (l != null && System.currentTimeMillis() - l.longValue() < j) {
                return new ArrayList();
            }
            Long l2 = this.backoffUntil.get(str);
            if (l2 != null && System.currentTimeMillis() < l2.longValue()) {
                return new ArrayList();
            }
        }
        List<Candle> fetchFromBinance = fetchFromBinance(str, i);
        if ((fetchFromBinance == null || fetchFromBinance.isEmpty()) && (fetchFromBridge = fetchFromBridge(str, i)) != null && !fetchFromBridge.isEmpty()) {
            fetchFromBinance = fetchFromBridge;
        }
        if (fetchFromBinance == null || fetchFromBinance.isEmpty()) {
            List<Candle> fetchFromBridge2 = fetchFromBridge(str, i);
            if (fetchFromBridge2 == null || fetchFromBridge2.isEmpty()) {
                fetchFromBridge2 = fetchFromBinance(str, i);
            }
            if (fetchFromBridge2 != null && !fetchFromBridge2.isEmpty()) {
                this.backoffUntil.remove(str);
                fetchFromBinance = fetchFromBridge2;
            } else {
                Long l3 = this.backoffUntil.get(str);
                long currentTimeMillis = System.currentTimeMillis();
                if (l3 != null && l3.longValue() > currentTimeMillis) {
                    j2 = Math.min((l3.longValue() - currentTimeMillis) * 2, 900000L);
                }
                this.backoffUntil.put(str, Long.valueOf(currentTimeMillis + j2));
            }
        } else {
            this.backoffUntil.remove(str);
        }
        this.lastFetchAt.put(str, Long.valueOf(System.currentTimeMillis()));
        return fetchFromBinance;
    }

    private List<Candle> fetchFromBridge(String str, int i) {
        String mt5Bridge = mt5Bridge();
        List<Candle> list = null;
        if (mt5Bridge.isEmpty()) {
            return null;
        }
        try {
            String httpGetUrl = httpGetUrl(mt5Bridge + (mt5Bridge.endsWith("/") ? "" : "/") + "candles?symbol=" + str + "&tf=5m&limit=" + i, 8000);
            if (httpGetUrl == null) {
                return null;
            }
            JSONArray jSONArray = new JSONArray(httpGetUrl);
            ArrayList arrayList = new ArrayList();
            int i2 = 0;
            int i3 = 0;
            while (i3 < jSONArray.length()) {
                JSONArray jSONArray2 = jSONArray.getJSONArray(i3);
                Candle candle = new Candle();
                candle.ts = jSONArray2.getLong(i2);
                candle.o = jSONArray2.getDouble(1);
                candle.h = jSONArray2.getDouble(2);
                candle.l = jSONArray2.getDouble(CONSEC_LOSS_DEFAULT);
                candle.c = jSONArray2.getDouble(4);
                candle.v = jSONArray2.getDouble(5);
                try {
                    JSONArray jSONArray3 = jSONArray;
                    if (candleOk(candle.ts, candle.o, candle.h, candle.l, candle.c, candle.v)) {
                        arrayList.add(candle);
                    }
                    i3++;
                    jSONArray = jSONArray3;
                    list = null;
                    i2 = 0;
                } catch (Exception unused) {
                    return null;
                }
            }
            return arrayList;
        } catch (Exception unused2) {
            return list;
        }
    }

    private List<Candle> fetchFromBinance(String str, int i) {
        return fetchFromBinance(str, i, "5m");
    }

    private List<Candle> fetchFromBinance(String str, int i, String str2) {
        if (!binanceTradable(str)) {
            return null;
        }
        try {
            String httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/klines?symbol=" + str + "&interval=" + str2 + "&limit=" + Math.min(i, 1000), 12000);
            if (httpGetUrl == null) {
                return null;
            }
            return parseBinanceKlines(httpGetUrl);
        } catch (Exception unused) {
            return null;
        }
    }

    private boolean binanceTradable(String str) {
        boolean contains = false;
        if (BINANCE_PAIRS.containsKey(str)) {
            return true;
        }
        synchronized (this.binanceOkCache) {
            contains = this.binanceOkCache.contains(str);
        }
        return contains;
    }

    static boolean candleOk(long j, double d, double d2, double d3, double d4, double d5) {
        return j > 0 && d > 0.0d && d2 > 0.0d && d3 > 0.0d && d4 > 0.0d && d5 >= 0.0d && d2 >= Math.max(d, d4) - 1.0E-9d && d3 <= Math.min(d, d4) + 1.0E-9d;
    }

    public static List<Candle> parseBinanceKlines(String str) {
        ArrayList arrayList = new ArrayList();
        try {
            JSONArray jSONArray = new JSONArray(str);
            for (int i = 0; i < jSONArray.length(); i++) {
                JSONArray jSONArray2 = jSONArray.getJSONArray(i);
                double d = jSONArray2.getDouble(1);
                double d2 = jSONArray2.getDouble(2);
                double d3 = jSONArray2.getDouble(CONSEC_LOSS_DEFAULT);
                double d4 = jSONArray2.getDouble(4);
                if (candleOk(jSONArray2.getLong(0), d, d2, d3, d4, jSONArray2.getDouble(5))) {
                    Candle candle = new Candle();
                    candle.ts = jSONArray2.getLong(0);
                    candle.o = d;
                    candle.h = d2;
                    candle.l = d3;
                    candle.c = d4;
                    candle.v = jSONArray2.getDouble(5);
                    arrayList.add(candle);
                }
            }
        } catch (Exception unused) {
        }
        return arrayList;
    }

    private String httpGetUrl(String str, int i) {
        try {
            HttpURLConnection httpURLConnection = (HttpURLConnection) new URL(str).openConnection();
            httpURLConnection.setConnectTimeout(i);
            httpURLConnection.setReadTimeout(i + 5000);
            httpURLConnection.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) AI-Trading-Lab/2.1");
            if (httpURLConnection.getResponseCode() != 200) {
                return null;
            }
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(httpURLConnection.getInputStream()));
            StringBuilder sb = new StringBuilder();
            while (true) {
                String readLine = bufferedReader.readLine();
                if (readLine == null) {
                    bufferedReader.close();
                    return sb.toString();
                }
                sb.append(readLine);
            }
        } catch (Exception unused) {
            return null;
        }
    }

    private List<String> activeSymbols() {
        ArrayList arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol FROM instruments WHERE status='ACTIVE' ORDER BY priority DESC LIMIT ?", new String[]{String.valueOf(ACTIVE_TOP)});
        while (rawQuery.moveToNext()) {
            arrayList.add(rawQuery.getString(0));
        }
        rawQuery.close();
        // v4.6 OWNER TUNE: universe_mode=MAJORS — sirf BTC/ETH/BNB/SOL (discovery baad me baaki pairs wapas ACTIVE kare to bhi yahan filter lagta hai)
        if (universeMajors() && !arrayList.isEmpty()) {
            ArrayList majors = new ArrayList();
            for (String m : MAJOR_PAIRS) {
                if (arrayList.contains(m)) majors.add(m);
            }
            if (!majors.isEmpty()) return majors;
        }
        return arrayList;
    }

    private void refreshCandles() {
        List<String> activeSymbols = activeSymbols();
        this.activeSymbols = activeSymbols.size();
        for (String str : activeSymbols) {
            List<Candle> fetchKlines = fetchKlines(str, 200);
            if (fetchKlines != null && !fetchKlines.isEmpty()) {
                upsertCandles(str, fetchKlines);
            }
        }
        rotate15m(30);
        updateFeedHealth();
    }

    private void upsertCandles(String str, List<Candle> list) {
        SQLiteDatabase writableDatabase = this.db.getWritableDatabase();
        writableDatabase.beginTransaction();
        try {
            for (Candle candle : list) {
                writableDatabase.execSQL("INSERT OR REPLACE INTO candles(symbol, tf, ts, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)", new Object[]{str, "5m", Long.valueOf(candle.ts), Double.valueOf(candle.o), Double.valueOf(candle.h), Double.valueOf(candle.l), Double.valueOf(candle.c), Double.valueOf(candle.v)});
            }
            writableDatabase.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?", new Object[]{Long.valueOf(System.currentTimeMillis()), str});
            writableDatabase.execSQL("DELETE FROM candles WHERE symbol=? AND tf=? AND ts < ?", new Object[]{str, "5m", Long.valueOf(System.currentTimeMillis() - 345600000)});
            writableDatabase.setTransactionSuccessful();
        } finally {
            writableDatabase.endTransaction();
        }
    }

    private List<Candle> loadCandles(String str) {
        ArrayList arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts", new String[]{str, "5m"});
        while (rawQuery.moveToNext()) {
            Candle candle = new Candle();
            candle.ts = rawQuery.getLong(0);
            candle.o = rawQuery.getDouble(1);
            candle.h = rawQuery.getDouble(2);
            candle.l = rawQuery.getDouble(CONSEC_LOSS_DEFAULT);
            candle.c = rawQuery.getDouble(4);
            candle.v = rawQuery.getDouble(5);
            arrayList.add(candle);
        }
        rawQuery.close();
        return arrayList;
    }

    private void rotate15m(int i) {
        try {
            if (this.rot15.isEmpty() || this.rot15Pos >= this.rot15.size()) {
                this.rot15.clear();
                Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE' ORDER BY priority DESC", null);
                while (rawQuery.moveToNext()) {
                    this.rot15.add(rawQuery.getString(0));
                }
                rawQuery.close();
                this.rot15Pos = 0;
                if (this.rot15.isEmpty()) {
                    return;
                }
            }
            int min = Math.min(this.rot15.size(), this.rot15Pos + i);
            for (int i2 = this.rot15Pos; i2 < min; i2++) {
                String str = this.rot15.get(i2);
                List<Candle> fetchFromBinance = fetchFromBinance(str, 300, "5m");
                if (fetchFromBinance != null && !fetchFromBinance.isEmpty()) {
                    upsertCandles15(str, fetchFromBinance);
                }
            }
            this.rot15Pos = min;
        } catch (Throwable th) {
            this.db.log("WARN", "FEED", "ROT15_FAIL", String.valueOf(th));
        }
    }

    private void upsertCandles15(String str, List<Candle> list) {
        SQLiteDatabase writableDatabase = this.db.getWritableDatabase();
        writableDatabase.beginTransaction();
        try {
            for (Candle candle : list) {
                writableDatabase.execSQL("INSERT OR REPLACE INTO candles(symbol, tf, ts, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)", new Object[]{str, "5m", Long.valueOf(candle.ts), Double.valueOf(candle.o), Double.valueOf(candle.h), Double.valueOf(candle.l), Double.valueOf(candle.c), Double.valueOf(candle.v)});
            }
            writableDatabase.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?", new Object[]{Long.valueOf(System.currentTimeMillis()), str});
            writableDatabase.execSQL("DELETE FROM candles WHERE symbol=? AND tf=? AND ts < ?", new Object[]{str, "5m", Long.valueOf(System.currentTimeMillis() - ((PB_SYMBOLS.contains(str) ? 16L : 7L) * 86400000))});
            writableDatabase.setTransactionSuccessful();
        } finally {
            writableDatabase.endTransaction();
        }
    }

    private List<Candle> loadCandles15(String str) {
        ArrayList arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts", new String[]{str, "5m"});
        while (rawQuery.moveToNext()) {
            Candle candle = new Candle();
            candle.ts = rawQuery.getLong(0);
            candle.o = rawQuery.getDouble(1);
            candle.h = rawQuery.getDouble(2);
            candle.l = rawQuery.getDouble(CONSEC_LOSS_DEFAULT);
            candle.c = rawQuery.getDouble(4);
            candle.v = rawQuery.getDouble(5);
            arrayList.add(candle);
        }
        rawQuery.close();
        return arrayList;
    }

    static double ema(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 2.0d / (i + 1);
        boolean z = false;
        int max = Math.max(0, list.size() - 200);
        double d2 = 0.0d;
        while (max < list.size()) {
            double d3 = list.get(max).c;
            if (z) {
                d3 = ((d3 - d2) * d) + d2;
            }
            d2 = d3;
            max++;
            z = true;
        }
        return d2;
    }

    static double rsi(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = list.get(size).c - list.get(size - 1).c;
            if (d3 > 0.0d) {
                d += d3;
            } else {
                d2 -= d3;
            }
        }
        double d4 = d2 + d;
        if (d4 == 0.0d) {
            return 50.0d;
        }
        return (d * 100.0d) / d4;
    }

    static double[] bollinger(List<Candle> list, int i) {
        if (list.size() < i) {
            return null;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = list.get(size).c;
            d += d3;
            d2 += d3 * d3;
        }
        double d4 = i;
        double d5 = d / d4;
        double sqrt = Math.sqrt(Math.max(0.0d, (d2 / d4) - (d5 * d5))) * 2.0d;
        return new double[]{d5 - sqrt, d5, sqrt + d5};
    }

    static double[] macd(List<Candle> list) {
        double[] emaSeries = emaSeries(list, 12);
        double[] emaSeries2 = emaSeries(list, 26);
        if (emaSeries == null || emaSeries2 == null) {
            return null;
        }
        int size = list.size();
        double[] dArr = new double[size];
        for (int i = 0; i < size; i++) {
            dArr[i] = emaSeries[i] - emaSeries2[i];
        }
        double d = 0.0d;
        int i2 = 0;
        boolean z = false;
        while (i2 < size) {
            d = z ? ((dArr[i2] - d) * 0.2d) + d : dArr[i2];
            i2++;
            z = true;
        }
        return new double[]{dArr[size - 1], d};
    }

    static double[] stochastic(List<Candle> list, int i) {
        if (list.size() < i) {
            return null;
        }
        double d = Double.MIN_VALUE;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - i; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        double d3 = list.get(list.size() - 1).c;
        if (d == d2) {
            return new double[]{50.0d, 50.0d};
        }
        double d4 = ((d3 - d2) * 100.0d) / (d - d2);
        return new double[]{d4, (0.7d * d4) + 15.0d};
    }

    static double vwap(List<Candle> list) {
        double d = 0.0d;
        double d2 = 0.0d;
        for (int max = Math.max(0, list.size() - 96); max < list.size(); max++) {
            Candle candle = list.get(max);
            d2 += (((candle.h + candle.l) + candle.c) / 3.0d) * candle.v;
            d += candle.v;
        }
        return d > 0.0d ? d2 / d : list.get(list.size() - 1).c;
    }

    static double atr(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            d += Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
        }
        return d / i;
    }

    static double[] emaSeries(List<Candle> list, int i) {
        if (list.size() < i) {
            return null;
        }
        double[] dArr = new double[list.size()];
        double d = 2.0d / (i + 1);
        int i2 = 0;
        double d2 = 0.0d;
        boolean z = false;
        while (i2 < list.size()) {
            double d3 = list.get(i2).c;
            if (z) {
                d3 = ((d3 - d2) * d) + d2;
            }
            d2 = d3;
            dArr[i2] = d2;
            i2++;
            z = true;
        }
        return dArr;
    }

    static double smaOf(double[] dArr, int i, int i2) {
        int i3 = 0;
        if (dArr == null || (i3 = (i - i2) + 1) < 0 || i2 <= 0) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (i3 = (i - i2) + 1; i3 <= i; i3++) {
            d += dArr[i3];
        }
        return d / i2;
    }

    static double[] rsiSeries(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return null;
        }
        double[] dArr = new double[list.size()];
        double d = 0.0d;
        double d2 = 0.0d;
        for (int i2 = 1; i2 < list.size(); i2++) {
            double d3 = list.get(i2).c - list.get(i2 - 1).c;
            if (i2 <= i) {
                if (d3 > 0.0d) {
                    d += d3;
                } else {
                    d2 -= d3;
                }
                double d4 = d + d2;
                dArr[i2] = d4 == 0.0d ? 50.0d : (d * 100.0d) / d4;
                if (i2 == i) {
                    double d5 = i;
                    d /= d5;
                    d2 /= d5;
                    dArr[i2] = (100.0d * d) / (d + d2);
                }
            } else {
                double d6 = i - 1;
                double d7 = i;
                d = ((d * d6) + Math.max(d3, 0.0d)) / d7;
                d2 = ((d2 * d6) + Math.max(-d3, 0.0d)) / d7;
                double d8 = d + d2;
                dArr[i2] = d8 == 0.0d ? 50.0d : (d * 100.0d) / d8;
            }
        }
        return dArr;
    }

    static double[] stochRsi(List<Candle> list) {
        double d = 0.0d;
        double[] rsiSeries = rsiSeries(list, 14);
        if (rsiSeries != null && list.size() >= 32) {
            double[] dArr = new double[list.size()];
            for (int i = 31; i < list.size(); i++) {
                double d2 = -1.7976931348623157E308d;
                double d3 = Double.MAX_VALUE;
                for (int i2 = i - 13; i2 <= i; i2++) {
                    d2 = Math.max(d2, rsiSeries[i2]);
                    d3 = Math.min(d3, rsiSeries[i2]);
                }
                dArr[i] = d2 == d3 ? 50.0d : ((rsiSeries[i] - d3) * 100.0d) / (d2 - d3);
            }
            int size = list.size();
            int i3 = size - 1;
            if (i3 >= 33) {
                double d4 = dArr[i3];
                double d5 = dArr[size - 2];
                double d6 = dArr[size - 3];
                double d7 = ((d4 + d5) + d6) / 3.0d;
                if (i3 >= 35) {
                    double d8 = dArr[size - 4];
                    d = (((((d5 + d6) + d8) / 3.0d) + d7) + (((d6 + d8) + dArr[size - 5]) / 3.0d)) / 3.0d;
                } else {
                    d = d7;
                }
                return new double[]{d7, d};
            }
        }
        return null;
    }

    static double[] adx(List<Candle> list, int i) {
        List<Candle> list2 = list;
        int i2 = i;
        int i3 = i2 * 2;
        if (list.size() < i3 + 2) {
            return null;
        }
        int size = list.size() - i3;
        int i4 = size + 1;
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        for (int i5 = 1; i4 < (list.size() - i2) + i5; i5 = 1) {
            Candle candle = list2.get(i4);
            Candle candle2 = list2.get(i4 - 1);
            double d4 = candle.h - candle2.h;
            double d5 = candle2.l - candle.l;
            d += (d4 <= d5 || d4 <= 0.0d) ? 0.0d : d4;
            if (d5 <= d4 || d5 <= 0.0d) {
                d5 = 0.0d;
            }
            d2 += d5;
            d3 += Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
            i4++;
            list2 = list;
            i2 = i;
        }
        double d6 = 0.0d;
        int i6 = 0;
        double d7 = 0.0d;
        double d8 = 0.0d;
        for (int size2 = (list.size() - i) + 1; size2 < list.size(); size2++) {
            double d9 = d8;
            Candle candle3 = list.get(size2);
            Candle candle4 = list.get(size2 - 1);
            double d10 = d7;
            double d11 = d6;
            double d12 = candle3.h - candle4.h;
            int i7 = i6;
            double d13 = candle4.l - candle3.l;
            double d14 = i;
            d = (d - (d / d14)) + ((d12 <= d13 || d12 <= 0.0d) ? 0.0d : d12);
            double d15 = d2 - (d2 / d14);
            if (d13 <= d12 || d13 <= 0.0d) {
                d13 = 0.0d;
            }
            d2 = d15 + d13;
            d3 = (d3 - (d3 / d14)) + Math.max(candle3.h - candle3.l, Math.max(Math.abs(candle3.h - candle4.c), Math.abs(candle3.l - candle4.c)));
            if (d3 <= 0.0d) {
                i6 = i7;
                d8 = d9;
                d7 = d10;
                d6 = d11;
            } else {
                double d16 = (d * 100.0d) / d3;
                double d17 = (d2 * 100.0d) / d3;
                double d18 = d16 + d17;
                i6 = i7 + 1;
                d6 = d11 + (d18 == 0.0d ? 0.0d : (Math.abs(d16 - d17) * 100.0d) / d18);
                d8 = d17;
                d7 = d16;
            }
        }
        int i8 = i6;
        return new double[]{i8 > 0 ? d6 / i8 : 0.0d, d7, d8};
    }

    static double cci(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double[] dArr = new double[i];
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            dArr[size - (list.size() - i)] = ((candle.h + candle.l) + candle.c) / 3.0d;
            d += dArr[size - (list.size() - i)];
        }
        double d2 = i;
        double d3 = d / d2;
        double d4 = 0.0d;
        for (int i2 = 0; i2 < i; i2++) {
            d4 += Math.abs(dArr[i2] - d3);
        }
        double d5 = d4 / d2;
        if (d5 == 0.0d) {
            return 0.0d;
        }
        return (dArr[i - 1] - d3) / (d5 * 0.015d);
    }

    static double williamsR(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - i; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        if (d == d2) {
            return -50.0d;
        }
        return ((d - list.get(list.size() - 1).c) * (-100.0d)) / (d - d2);
    }

    static double mfi(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            double d3 = ((candle.h + candle.l) + candle.c) / 3.0d;
            double d4 = ((candle2.h + candle2.l) + candle2.c) / 3.0d;
            double d5 = candle.v * d3;
            if (d3 > d4) {
                d2 += d5;
            } else if (d3 < d4) {
                d += d5;
            }
        }
        if (d == 0.0d) {
            return 100.0d;
        }
        if (d2 == 0.0d) {
            return 0.0d;
        }
        return 100.0d - (100.0d / ((d2 / d) + 1.0d));
    }

    static double obvSlope(List<Candle> list, int i) {
        double d = 0.0d;
        if (list.size() < i + 1) {
            return 0.0d;
        }
        int size = (list.size() - 1) - i;
        boolean z = false;
        double d2 = 0.0d;
        double d3 = 0.0d;
        for (int i2 = 1; i2 < list.size(); i2++) {
            double d4 = list.get(i2).c - list.get(i2 - 1).c;
            if (d4 > 0.0d) {
                d = list.get(i2).v;
            } else {
                d = d4 < 0.0d ? -list.get(i2).v : 0.0d;
            }
            d2 += d;
            if (i2 == size) {
                z = true;
                d3 = d2;
            }
        }
        if (!z || d3 == 0.0d) {
            return 0.0d;
        }
        return (d2 - d3) / Math.abs(d3);
    }

    static double roc(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return 0.0d;
        }
        double d = list.get((list.size() - 1) - i).c;
        if (d == 0.0d) {
            return 0.0d;
        }
        return ((list.get(list.size() - 1).c - d) * 100.0d) / d;
    }

    /* JADX WARN: Code restructure failed: missing block: B:24:0x0080, code lost:
    
        if (r4 >= r12) goto L28;
     */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    static double[] supertrend(List<Candle> list) {
        int max = Math.max(1, list.size() - 120);
        if (list.size() < 12) {
            return null;
        }
        double atr = atr(list.subList(Math.max(0, list.size() - 120), list.size()), 10);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        double d = Double.NaN;
        int i = 1;
        double d2 = Double.NaN;
        double d3 = Double.NaN;
        while (max < list.size()) {
            Candle candle = list.get(max);
            double d4 = (candle.h + candle.l) / 2.0d;
            double d5 = 3.0d * atr;
            double d6 = d4 + d5;
            double d7 = d4 - d5;
            double closeAt = closeAt(list, max - 1);
            if (!Double.isNaN(d2) && !Double.isNaN(closeAt)) {
                if (d6 >= d2 && closeAt <= d2) {
                    d6 = d2;
                }
                if (d7 <= d3) {
                }
            }
            d3 = d7;
            if (Double.isNaN(d)) {
                i = 1;
            } else {
                int i2 = -1;
                if (d != d2 ? candle.c >= d3 : candle.c > d6) {
                    i2 = 1;
                }
                i = i2;
            }
            d = i == 1 ? d3 : d6;
            max++;
            d2 = d6;
        }
        return new double[]{d, i};
    }

    static double[] psar(List<Candle> list) {
        boolean z = false;
        double d = 0.0d;
        if (list.size() < 10) {
            return null;
        }
        boolean z2 = list.get(0).c <= list.get(1).c;
        Candle candle = list.get(0);
        double d2 = z2 ? candle.l : candle.h;
        Candle candle2 = list.get(0);
        double d3 = z2 ? candle2.h : candle2.l;
        double d4 = 0.02d;
        for (int i = 2; i < list.size(); i++) {
            Candle candle3 = list.get(i);
            d2 += (d3 - d2) * d4;
            if (z2) {
                z = z2;
                if (candle3.l < d2) {
                    d2 = d3;
                    d4 = 0.02d;
                    d3 = candle3.l;
                    z2 = false;
                } else {
                    if (candle3.h > d3) {
                        d = candle3.h;
                        d4 = Math.min(0.2d, d4 + 0.02d);
                        d3 = d;
                    }
                    z2 = z;
                }
            } else {
                z = z2;
                if (candle3.h > d2) {
                    d2 = d3;
                    d4 = 0.02d;
                    d3 = candle3.h;
                    z2 = true;
                } else {
                    if (candle3.l < d3) {
                        d = candle3.l;
                        d4 = Math.min(0.2d, d4 + 0.02d);
                        d3 = d;
                    }
                    z2 = z;
                }
            }
        }
        return new double[]{d2, z2 ? 1.0d : -1.0d};
    }

    static double[] ichimoku(List<Candle> list) {
        if (list.size() < 52) {
            return null;
        }
        double[] dArr = new double[list.size()];
        double[] dArr2 = new double[list.size()];
        for (int i = 0; i < list.size(); i++) {
            double d = -1.7976931348623157E308d;
            double d2 = Double.MAX_VALUE;
            for (int max = Math.max(0, i - 51); max <= i; max++) {
                d = Math.max(d, list.get(max).h);
                d2 = Math.min(d2, list.get(max).l);
            }
            dArr[i] = d;
            dArr2[i] = d2;
        }
        int size = list.size() - 1;
        double mid = mid(dArr, dArr2, size, 9);
        double mid2 = mid(dArr, dArr2, size, 26);
        return new double[]{mid, mid2, (mid + mid2) / 2.0d, mid(dArr, dArr2, size, 52)};
    }

    private static double mid(double[] dArr, double[] dArr2, int i, int i2) {
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int max = Math.max(0, (i - i2) + 1); max <= i; max++) {
            d = Math.max(d, dArr[max]);
            d2 = Math.min(d2, dArr2[max]);
        }
        return (d + d2) / 2.0d;
    }

    static double[] aroon(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return null;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        int i2 = 0;
        int i3 = 0;
        for (int size = list.size() - i; size < list.size(); size++) {
            if (list.get(size).h >= d) {
                d = list.get(size).h;
                i2 = size;
            }
            if (list.get(size).l <= d2) {
                d2 = list.get(size).l;
                i3 = size;
            }
        }
        int size2 = list.size() - 1;
        double d3 = i;
        return new double[]{((i - (size2 - i2)) * 100.0d) / d3, ((i - (size2 - i3)) * 100.0d) / d3};
    }

    static double trix(List<Candle> list) {
        double[] emaSeries = emaSeries(list, 15);
        if (emaSeries == null) {
            return Double.NaN;
        }
        double[] dArr = new double[emaSeries.length];
        int length = emaSeries.length;
        double[] dArr2 = new double[length];
        double d = emaSeries[14];
        int i = 0;
        boolean z = false;
        boolean z2 = false;
        double d2 = d;
        while (i < emaSeries.length) {
            d = z ? ((emaSeries[i] - d) * 0.125d) + d : emaSeries[i];
            dArr[i] = d;
            d2 = z2 ? ((d - d2) * 0.125d) + d2 : d;
            dArr2[i] = d2;
            i++;
            z = true;
            z2 = true;
        }
        int i2 = length - 1;
        if (i2 < 1) {
            return 0.0d;
        }
        double d3 = dArr2[length - 2];
        if (d3 == 0.0d) {
            return 0.0d;
        }
        return ((dArr2[i2] - d3) * 100.0d) / d3;
    }

    static double[] keltner(List<Candle> list, int i, double d) {
        double[] emaSeries = null;
        if (list.size() < i + 1 || (emaSeries = emaSeries(list, i)) == null) {
            return null;
        }
        double atr = atr(list, i);
        if (Double.isNaN(atr)) {
            return null;
        }
        double d2 = emaSeries[emaSeries.length - 1];
        double d3 = d * atr;
        return new double[]{d2, d2 + d3, d2 - d3};
    }

    static double ultimateOsc(List<Candle> list) {
        if (list.size() < 29) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        for (int size = list.size() - 28; size < list.size(); size++) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            double d7 = d4;
            double d8 = d6;
            double min = Math.min(candle.l, candle2.c);
            double d9 = candle.c - min;
            double d10 = d2;
            double d11 = d5;
            double max = Math.max(candle.h - min, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
            if (size >= list.size() - 7) {
                d3 += d9;
                d += max;
            }
            if (size >= list.size() - 14) {
                d5 = d11 + d9;
                d2 = d10 + max;
            } else {
                d2 = d10;
                d5 = d11;
            }
            d6 = d8 + d9;
            d4 = d7 + max;
        }
        double d12 = d2;
        double d13 = d4;
        double d14 = d5;
        double d15 = d6;
        if (d == 0.0d || d12 == 0.0d || d13 == 0.0d) {
            return 50.0d;
        }
        return (((((d3 * 4.0d) / d) + ((d14 * 2.0d) / d12)) + (d15 / d13)) * 100.0d) / 7.0d;
    }

    private static double closeAt(List<Candle> list, int i) {
        if (i < 0 || i >= list.size()) {
            return Double.NaN;
        }
        return list.get(i).c;
    }

    static double wma(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int i2 = 0; i2 < i; i2++) {
            double d3 = i - i2;
            d += list.get((list.size() - i) + i2).c * d3;
            d2 += d3;
        }
        return d / d2;
    }

    static double smma(List<Candle> list, int i) {
        if (list.size() < i + CONSEC_LOSS_DEFAULT) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - (i * 2); size < list.size() - i; size++) {
            d += list.get(size).c;
        }
        double d2 = i;
        double d3 = d / d2;
        for (int size2 = list.size() - i; size2 < list.size(); size2++) {
            d3 = ((d3 * (i - 1)) + list.get(size2).c) / d2;
        }
        return d3;
    }

    static double hma(List<Candle> list, int i) {
        if (list.size() < i * 2) {
            return Double.NaN;
        }
        int max = Math.max(2, (int) Math.sqrt(i));
        double wma = wma(list, i);
        int i2 = i / 2;
        double wma2 = wma(list, i2);
        if (Double.isNaN(wma) || Double.isNaN(wma2)) {
            return Double.NaN;
        }
        double d = (wma2 * 2.0d) - wma;
        ArrayList arrayList = new ArrayList();
        for (int i3 = 0; i3 < max; i3++) {
            List<Candle> subList = list.subList(0, list.size() - i3);
            double wma3 = wma(subList, i);
            double wma4 = wma(subList, i2);
            if (Double.isNaN(wma3) || Double.isNaN(wma4)) {
                break;
            }
            arrayList.add(Double.valueOf((wma4 * 2.0d) - wma3));
        }
        if (arrayList.size() < 2) {
            return d;
        }
        double d2 = 0.0d;
        double d3 = 0.0d;
        for (int i4 = 0; i4 < arrayList.size(); i4++) {
            double size = arrayList.size() - i4;
            d2 += ((Double) arrayList.get(i4)).doubleValue() * size;
            d3 += size;
        }
        return d2 / d3;
    }

    static double dema(List<Candle> list, int i) {
        double[] emaSeries = emaSeries(list, i);
        if (emaSeries == null) {
            return Double.NaN;
        }
        ArrayList arrayList = new ArrayList();
        double d = 2.0d / (i + 1);
        int length = emaSeries.length;
        int i2 = 0;
        double d2 = 0.0d;
        boolean z = false;
        while (i2 < length) {
            double d3 = emaSeries[i2];
            if (z) {
                d3 = ((d3 - d2) * d) + d2;
            }
            d2 = d3;
            arrayList.add(Double.valueOf(d2));
            i2++;
            z = true;
        }
        return (emaSeries[emaSeries.length - 1] * 2.0d) - ((Double) arrayList.get(arrayList.size() - 1)).doubleValue();
    }

    static double tema(List<Candle> list, int i) {
        double[] emaSeries = emaSeries(list, i);
        if (emaSeries == null) {
            return Double.NaN;
        }
        double d = 2.0d / (i + 1);
        double[] dArr = new double[emaSeries.length];
        double[] dArr2 = new double[emaSeries.length];
        int i2 = 0;
        double d2 = 0.0d;
        double d3 = 0.0d;
        boolean z = false;
        while (true) {
            boolean z2 = z;
            if (i2 < emaSeries.length) {
                d2 = z ? ((emaSeries[i2] - d2) * d) + d2 : emaSeries[i2];
                dArr[i2] = d2;
                d3 = z2 ? ((d2 - d3) * d) + d3 : d2;
                dArr2[i2] = d3;
                i2++;
                z = true;
            } else {
                int length = emaSeries.length - 1;
                return ((emaSeries[length] * 3.0d) - (dArr[length] * 3.0d)) + dArr2[length];
            }
        }
    }

    static double kama(List<Candle> list) {
        if (list.size() < 27) {
            return Double.NaN;
        }
        double d = 2.0d / CONSEC_LOSS_DEFAULT;
        double d2 = 2.0d / 31;
        double d3 = list.get(list.size() - 11).c;
        for (int size = list.size() - 10; size < list.size(); size++) {
            double abs = Math.abs(list.get(size).c - list.get(size - 10).c);
            double d4 = 0.0d;
            for (int i = size - 9; i <= size; i++) {
                d4 += Math.abs(list.get(i).c - list.get(i - 1).c);
            }
            d3 += Math.pow(((d4 == 0.0d ? 0.0d : abs / d4) * (d - d2)) + d2, 2.0d) * (list.get(size).c - d3);
        }
        return d3;
    }

    static double alma(List<Candle> list, int i, double d, double d2) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d3 = (i - 1) * d;
        double d4 = i / d2;
        double d5 = 0.0d;
        double d6 = 0.0d;
        for (int i2 = 0; i2 < i; i2++) {
            double exp = Math.exp((-Math.pow(i2 - d3, 2.0d)) / ((2.0d * d4) * d4));
            d6 += list.get((list.size() - i) + i2).c * exp;
            d5 += exp;
        }
        if (d5 > 0.0d) {
            return d6 / d5;
        }
        return Double.NaN;
    }

    static double t3(List<Candle> list, int i, double d) {
        double[] emaSeries = emaSeries(list, i);
        if (emaSeries == null) {
            return Double.NaN;
        }
        double d2 = 2.0d / (i + 1);
        double[] dArr = new double[emaSeries.length];
        double[] dArr2 = new double[emaSeries.length];
        double[] dArr3 = new double[emaSeries.length];
        double[] dArr4 = new double[emaSeries.length];
        double[] dArr5 = new double[emaSeries.length];
        double d3 = 0.0d;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        int i2 = 0;
        boolean z = false;
        boolean z2 = false;
        boolean z3 = false;
        boolean z4 = false;
        boolean z5 = false;
        double d7 = 0.0d;
        while (i2 < emaSeries.length) {
            d3 = z ? ((emaSeries[i2] - d3) * d2) + d3 : emaSeries[i2];
            dArr[i2] = d3;
            d7 = z2 ? ((d3 - d7) * d2) + d7 : d3;
            dArr2[i2] = d7;
            d4 = z3 ? ((d7 - d4) * d2) + d4 : d7;
            dArr3[i2] = d4;
            d5 = z4 ? ((d4 - d5) * d2) + d5 : d4;
            dArr4[i2] = d5;
            d6 = z5 ? ((d5 - d6) * d2) + d6 : d5;
            dArr5[i2] = d6;
            i2++;
            z = true;
            z2 = true;
            z3 = true;
            z4 = true;
            z5 = true;
        }
        int length = emaSeries.length - 1;
        double d8 = 3.0d * d;
        double d9 = d8 * d;
        double d10 = d9 * d;
        return ((-d) * d * d * dArr5[length]) + ((d9 + d10) * dArr4[length]) + ((((((-6.0d) * d) * d) - d8) - d10) * dArr3[length]) + ((d8 + 1.0d + (d * d * d) + d9) * dArr2[length]);
    }

    static double zlema(List<Candle> list, int i) {
        if (list.size() < i + 2) {
            return Double.NaN;
        }
        double d = (i - 1) / 2.0d;
        ArrayList arrayList = new ArrayList();
        boolean z = false;
        for (int i2 = 0; i2 < list.size(); i2++) {
            int round = i2 - ((int) Math.round(d));
            arrayList.add(Double.valueOf((list.get(i2).c * 2.0d) - (round >= 0 ? list.get(round) : list.get(0)).c));
        }
        double d2 = 2.0d / (i + 1);
        Iterator it = arrayList.iterator();
        double d3 = 0.0d;
        while (it.hasNext()) {
            double doubleValue = ((Double) it.next()).doubleValue();
            if (z) {
                doubleValue = ((doubleValue - d3) * d2) + d3;
            }
            d3 = doubleValue;
            z = true;
        }
        return d3;
    }

    static double lsma(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        double d4 = 0.0d;
        for (int i2 = 0; i2 < i; i2++) {
            double d5 = list.get((list.size() - i) + i2).c;
            double d6 = i2;
            d2 += d6;
            d3 += d5;
            d4 += d6 * d5;
            d += i2 * i2;
        }
        double d7 = i;
        double d8 = (d * d7) - (d2 * d2);
        if (d8 == 0.0d) {
            return Double.NaN;
        }
        double d9 = ((d4 * d7) - (d2 * d3)) / d8;
        return ((d3 - (d2 * d9)) / d7) + (d9 * (i - 1));
    }

    static double vwma(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d2 += list.get(size).c * list.get(size).v;
            d += list.get(size).v;
        }
        if (d > 0.0d) {
            return d2 / d;
        }
        return Double.NaN;
    }

    static double mcginley(List<Candle> list, int i) {
        if (list.size() < i + 5) {
            return Double.NaN;
        }
        double d = list.get((list.size() - i) - 1).c;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d2 = list.get(size).c;
            d += (d2 - d) / (i * Math.pow(d2 / Math.max(d, 1.0E-12d), 4.0d));
        }
        return d;
    }

    static double[] donchian(List<Candle> list, int i) {
        if (list.size() < i) {
            return null;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - i; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        return new double[]{d, (d + d2) / 2.0d, d2};
    }

    static double[] envelopes(List<Candle> list, int i, double d) {
        if (list.size() < i) {
            return null;
        }
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d2 += list.get(size).c;
        }
        double d3 = d2 / i;
        double d4 = d / 100.0d;
        return new double[]{(1.0d - d4) * d3, d3, (d4 + 1.0d) * d3};
    }

    static double stdev(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = list.get(size).c;
            d += d3;
            d2 += d3 * d3;
        }
        double d4 = i;
        double d5 = d / d4;
        return Math.sqrt(Math.max(0.0d, (d2 / d4) - (d5 * d5)));
    }

    static double chandelier(List<Candle> list, int i, double d) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d2 = -1.7976931348623157E308d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d2 = Math.max(d2, list.get(size).h);
        }
        return d2 - (d * atr(list, i));
    }

    static double[] fractals(List<Candle> list) {
        double d = -1.0d;
        double d2 = -1.0d;
        for (int size = list.size() - 3; size >= 2; size--) {
            Candle candle = list.get(size);
            if (d < 0.0d && candle.h > list.get(size - 1).h && candle.h > list.get(size - 2).h && candle.h > list.get(size + 1).h && candle.h > list.get(size + 2).h) {
                d = candle.h;
            }
            if (d2 < 0.0d && candle.l < list.get(size - 1).l && candle.l < list.get(size - 2).l && candle.l < list.get(size + 1).l && candle.l < list.get(size + 2).l) {
                d2 = candle.l;
            }
            if (d >= 0.0d && d2 >= 0.0d) {
                break;
            }
        }
        return new double[]{d, d2};
    }

    static double[] vortex(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return null;
        }
        int size = list.size() - i;
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        while (size < list.size()) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            double abs = d2 + Math.abs(candle.h - candle2.l);
            double abs2 = d3 + Math.abs(candle.l - candle2.h);
            d += Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
            size++;
            d2 = abs;
            d3 = abs2;
        }
        if (d == 0.0d) {
            return null;
        }
        return new double[]{d2 / d, d3 / d};
    }

    static double massIndex(List<Candle> list) {
        if (list.size() < 35) {
            return Double.NaN;
        }
        double[] dArr = new double[list.size()];
        for (int i = 0; i < list.size(); i++) {
            dArr[i] = list.get(i).h - list.get(i).l;
        }
        ArrayList arrayList = new ArrayList();
        ArrayList arrayList2 = new ArrayList();
        double d = dArr[0];
        double d2 = 2.0d / 10;
        double d3 = d;
        for (int i2 = 0; i2 < list.size(); i2++) {
            d += (dArr[i2] - d) * d2;
            d3 += (d - d3) * d2;
            arrayList.add(Double.valueOf(d));
            arrayList2.add(Double.valueOf(d3));
        }
        double d4 = 0.0d;
        for (int size = list.size() - 25; size < list.size(); size++) {
            d4 += ((Double) arrayList2.get(size)).doubleValue() != 0.0d ? ((Double) arrayList.get(size)).doubleValue() / ((Double) arrayList2.get(size)).doubleValue() : 1.0d;
        }
        return d4;
    }

    static double[] alligator(List<Candle> list) {
        if (list.size() < ACTIVE_TOP) {
            return null;
        }
        return new double[]{smma(list, 13), smma(list, 8), smma(list, 5)};
    }

    static double choppiness(List<Candle> list, int i) {
        List<Candle> list2 = list;
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        int size = list.size() - i;
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        double d3 = 0.0d;
        while (size < list.size()) {
            Candle candle = list2.get(size);
            Candle candle2 = list2.get(size - 1);
            d3 += Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
            d = Math.max(d, candle.h);
            d2 = Math.min(d2, candle.l);
            size++;
            list2 = list;
        }
        if (d3 <= 0.0d) {
            return 50.0d;
        }
        double d4 = d - d2;
        if (d4 <= 0.0d) {
            return 50.0d;
        }
        return (Math.log10(d3 / d4) * 100.0d) / Math.log10(i);
    }

    static double schaff(List<Candle> list) {
        double[] emaSeries = emaSeries(list, 23);
        double[] emaSeries2 = emaSeries(list, 50);
        if (emaSeries == null || emaSeries2 == null) {
            return Double.NaN;
        }
        int size = list.size();
        double[] dArr = new double[size];
        boolean z = false;
        for (int i = 0; i < size; i++) {
            dArr[i] = emaSeries[i] - emaSeries2[i];
        }
        int i2 = size - 1;
        double stochOfSeries = stochOfSeries(dArr, i2, 10);
        if (size < 14) {
            return stochOfSeries;
        }
        double[] dArr2 = new double[size];
        int i3 = size - 11;
        double d = dArr[i3];
        while (i3 < size) {
            d = z ? ((dArr[i3] - d) * 0.5d) + d : dArr[i3];
            dArr2[i3] = d;
            i3++;
            z = true;
        }
        return stochOfSeries(dArr2, i2, 10);
    }

    private static double stochOfSeries(double[] dArr, int i, int i2) {
        int i3 = (i - i2) + 1;
        if (i3 < 0) {
            return 50.0d;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        while (i3 <= i) {
            d = Math.max(d, dArr[i3]);
            d2 = Math.min(d2, dArr[i3]);
            i3++;
        }
        if (d == d2) {
            return 50.0d;
        }
        return ((dArr[i] - d2) * 100.0d) / (d - d2);
    }

    static double kst(List<Candle> list) {
        if (list.size() < 35) {
            return Double.NaN;
        }
        return roc(list, 10) + (roc(list, 15) * 2.0d) + (roc(list, 20) * 3.0d) + (roc(list, 30) * 4.0d);
    }

    static double coppock(List<Candle> list) {
        if (list.size() < 32) {
            return Double.NaN;
        }
        int i = 14;
        double roc = roc(list, 14);
        double roc2 = roc(list, 11);
        int i2 = 1;
        double d = 0.0d;
        double d2 = 0.0d;
        while (i2 <= 10 && list.size() >= i2 + 32) {
            double roc3 = roc(list.subList(0, (list.size() - i2) + 1), i);
            double roc4 = roc(list.subList(0, (list.size() - i2) + 1), 11);
            if (Double.isNaN(roc3) || Double.isNaN(roc4)) {
                break;
            }
            double d3 = 11 - i2;
            d += (roc3 + roc4) * d3;
            d2 += d3;
            i2++;
            roc = roc;
            i = 14;
        }
        return d2 > 0.0d ? d / d2 : roc + roc2;
    }

    static double[] apoPpo(List<Candle> list) {
        double[] emaSeries = emaSeries(list, 12);
        double[] emaSeries2 = emaSeries(list, 26);
        if (emaSeries == null || emaSeries2 == null) {
            return null;
        }
        int size = list.size() - 1;
        double d = emaSeries[size];
        double d2 = emaSeries2[size];
        double d3 = d - d2;
        return new double[]{d3, d2 != 0.0d ? (100.0d * d3) / d2 : 0.0d};
    }

    static double dpo(List<Candle> list, int i) {
        int i2 = i / 2;
        if (list.size() < i + i2 + 1) {
            return Double.NaN;
        }
        int i3 = i2 + 1;
        double d = 0.0d;
        for (int size = (list.size() - i) - i3; size < list.size() - i3; size++) {
            d += list.get(size).c;
        }
        return list.get(list.size() - 1).c - (d / i);
    }

    static double awesomeOsc(List<Candle> list) {
        if (list.size() < 34) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - 5; size < list.size(); size++) {
            d2 += (list.get(size).h + list.get(size).l) / 2.0d;
        }
        for (int size2 = list.size() - 34; size2 < list.size(); size2++) {
            d += (list.get(size2).h + list.get(size2).l) / 2.0d;
        }
        return (d2 / 5.0d) - (d / 34.0d);
    }

    static double tsi(List<Candle> list) {
        if (list.size() < ACTIVE_TOP) {
            return Double.NaN;
        }
        double d = 2.0d / 26;
        double d2 = 2.0d / 14;
        boolean z = false;
        boolean z2 = false;
        int i = 1;
        double d3 = 0.0d;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        while (i < list.size()) {
            int i2 = i;
            double d7 = d3;
            double d8 = list.get(i).c - list.get(i - 1).c;
            d5 = z ? ((d8 - d5) * d) + d5 : d8;
            d6 = ((Math.abs(d8) - d6) * d) + d6;
            d4 = z2 ? ((d5 - d4) * d2) + d4 : d5;
            d3 = ((d6 - d7) * d2) + d7;
            i = i2 + 1;
            z = true;
            z2 = true;
        }
        double d9 = d3;
        if (d9 != 0.0d) {
            return (d4 * 100.0d) / d9;
        }
        return 0.0d;
    }

    static double cmo(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = list.get(size).c - list.get(size - 1).c;
            if (d3 > 0.0d) {
                d += d3;
            } else {
                d2 -= d3;
            }
        }
        double d4 = d + d2;
        if (d4 == 0.0d) {
            return 0.0d;
        }
        return ((d - d2) * 100.0d) / d4;
    }

    static double fisher(List<Candle> list) {
        if (list.size() < 10) {
            return Double.NaN;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - 9; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        double max = Math.max(-0.999d, Math.min(0.999d, d == d2 ? 0.0d : (((list.get(list.size() - 1).c - ((d + d2) / 2.0d)) / (d - d2)) * 2.0d) - 1.0d));
        return Math.log((max + 1.0d) / (1.0d - max)) * 0.5d;
    }

    static double deMarker(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            d += Math.max(0.0d, candle.h - candle2.h);
            d2 += Math.max(0.0d, candle2.l - candle.l);
        }
        double d3 = d2 + d;
        if (d3 == 0.0d) {
            return 0.5d;
        }
        return d / d3;
    }

    static double smi(List<Candle> list) {
        if (list.size() < 25) {
            return Double.NaN;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - 10; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        double d3 = d == d2 ? 0.0d : ((list.get(list.size() - 1).c - ((d + d2) / 2.0d)) * 100.0d) / (d - d2);
        return (0.7d * d3) + (0.3d * d3 * ((list.size() <= 1 || list.get(list.size() - 1).c <= list.get(list.size() + (-2)).c) ? 1.1d : 0.9d));
    }

    static double bop(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            d += candle.h - candle.l != 0.0d ? (candle.c - candle.o) / (candle.h - candle.l) : 0.0d;
        }
        return d / i;
    }

    static double laguerreRsi(List<Candle> list) {
        double d = 0.0d;
        double d2 = 0.0d;
        if (list.size() < 8) {
            return Double.NaN;
        }
        int max = Math.max(0, list.size() - 60);
        double d3 = 0.0d;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        while (max < list.size()) {
            double d7 = (list.get(max).c * 0.5d) + (0.5d * d3);
            double d8 = ((-0.5d) * d7) + d3 + (d4 * 0.5d);
            d4 = Math.max(0.0d, d8);
            double d9 = ((-0.5d) * d4) + d8 + (d5 * 0.5d);
            d5 = Math.max(0.0d, d9);
            d6 = Math.max(0.0d, ((-0.5d) * d5) + d9 + (0.5d * d6));
            max++;
            d3 = d7;
        }
        if (d3 >= d4) {
            d2 = (d3 - d4) + 0.0d;
            d = 0.0d;
        } else {
            d = (d4 - d3) + 0.0d;
            d2 = 0.0d;
        }
        if (d4 >= d5) {
            d2 += d4 - d5;
        } else {
            d += d5 - d4;
        }
        if (d5 >= d6) {
            d2 += d5 - d6;
        } else {
            d += d6 - d5;
        }
        double d10 = d + d2;
        if (d10 != 0.0d) {
            return d2 / d10;
        }
        return 0.5d;
    }

    static double rvi(List<Candle> list, int i) {
        if (list.size() < i + 7) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = (list.size() - i) - 3; size < list.size(); size++) {
            double d3 = list.get(size).c - list.get(size).o;
            double d4 = list.get(size).h - list.get(size).l;
            int i2 = size - 1;
            int i3 = size - 2;
            double d5 = d2;
            int i4 = size - 3;
            double d6 = ((((d3 * 1.0d) + ((list.get(i2).c - list.get(i2).o) * 2.0d)) + ((list.get(i3).c - list.get(i3).o) * 2.0d)) + (list.get(i4).c - list.get(i4).o)) / 6.0d;
            double d7 = (((d4 + ((list.get(i2).h - list.get(i2).l) * 2.0d)) + ((list.get(i3).h - list.get(i3).l) * 2.0d)) + (list.get(i4).h - list.get(i4).l)) / 6.0d;
            d2 = d5 + d6;
            d += d7;
        }
        double d8 = d;
        double d9 = d2;
        if (d8 != 0.0d) {
            return d9 / d8;
        }
        return 0.0d;
    }

    static double[] elderRay(List<Candle> list) {
        double ema = ema(list, 13);
        if (Double.isNaN(ema)) {
            return null;
        }
        Candle candle = list.get(list.size() - 1);
        return new double[]{candle.h - ema, candle.l - ema};
    }

    static double adSlope(List<Candle> list, int i) {
        int i2 = 0;
        double d = 0.0d;
        double d2 = 0.0d;
        if (list.size() < i + 1) {
            return 0.0d;
        }
        int size = (list.size() - 1) - i;
        int i3 = 0;
        double d3 = 0.0d;
        double d4 = 0.0d;
        boolean z = false;
        while (i3 < list.size()) {
            Candle candle = list.get(i3);
            double d5 = candle.h - candle.l;
            if (d5 != d2) {
                i2 = i3;
                d = ((candle.c - candle.l) - (candle.h - candle.c)) / d5;
            } else {
                i2 = i3;
                d = 0.0d;
            }
            d3 += d * candle.v;
            int i4 = i2;
            if (i4 == size) {
                d4 = d3;
                z = true;
            }
            i3 = i4 + 1;
            d2 = 0.0d;
        }
        if (!z) {
            return 0.0d;
        }
        return (d3 - d4) / Math.max(Math.abs(d4), 1.0E-9d);
    }

    static double cmf(List<Candle> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        int size = list.size() - i;
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        while (size < list.size()) {
            Candle candle = list.get(size);
            double d4 = candle.h - candle.l;
            d3 += (d4 != d ? ((candle.c - candle.l) - (candle.h - candle.c)) / d4 : 0.0d) * candle.v;
            d2 += candle.v;
            size++;
            d = 0.0d;
        }
        double d5 = d;
        return d2 != d5 ? d3 / d2 : d5;
    }

    static double chaikinOsc(List<Candle> list) {
        double d = 0.0d;
        double d2 = 0.0d;
        if (list.size() < ACTIVE_TOP) {
            return Double.NaN;
        }
        int i = 0;
        double d3 = 0.0d;
        boolean z = false;
        boolean z2 = false;
        double d4 = 0.0d;
        double d5 = 0.0d;
        while (i < list.size()) {
            Candle candle = list.get(i);
            double d6 = candle.h - candle.l;
            if (d6 != d3) {
                d = d5;
                d2 = ((candle.c - candle.l) - (candle.h - candle.c)) / d6;
            } else {
                d = d5;
                d2 = 0.0d;
            }
            double d7 = d2 * candle.v;
            d4 = z ? ((d7 - d4) * 0.5d) + d4 : d7;
            if (z2) {
                d7 = ((d7 - d) * 0.18181818181818182d) + d;
            }
            d5 = d7;
            i++;
            z2 = true;
            z = true;
            d3 = 0.0d;
        }
        return d4 - d5;
    }

    static double forceIndex(List<Candle> list, int i) {
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d += (list.get(size).c - list.get(size - 1).c) * list.get(size).v;
        }
        double d2 = 0.0d;
        for (int size2 = list.size() - i; size2 < list.size(); size2++) {
            d2 += list.get(size2).v;
        }
        if (d2 > 0.0d) {
            return d / d2;
        }
        return 0.0d;
    }

    static double eom(List<Candle> list, int i) {
        double d = 0.0d;
        double d2 = 0.0d;
        if (list.size() < i + 1) {
            return Double.NaN;
        }
        double d3 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            Candle candle = list.get(size);
            Candle candle2 = list.get(size - 1);
            double d4 = ((candle.h + candle.l) / 2.0d) - ((candle2.h + candle2.l) / 2.0d);
            if (candle.v > 0.0d) {
                d2 = (candle.v / 10000.0d) / Math.max(1.0E-4d, candle.h - candle.l);
                d = 0.0d;
            } else {
                d = 0.0d;
                d2 = 0.0d;
            }
            d3 += d2 != d ? d4 / d2 : d;
        }
        return d3 / i;
    }

    static double klinger(List<Candle> list) {
        if (list.size() < 56) {
            return Double.NaN;
        }
        boolean z = false;
        double d = 0.0d;
        double d2 = 0.0d;
        int i = 1;
        boolean z2 = false;
        while (i < list.size()) {
            Candle candle = list.get(i);
            Candle candle2 = list.get(i - 1);
            double d3 = d;
            double d4 = (candle.h + candle.l) + candle.c > (candle2.h + candle2.l) + candle2.c ? candle.v : -candle.v;
            double d5 = z ? ((d4 - d3) * 0.05714285714285714d) + d3 : d4;
            if (z2) {
                d4 = ((d4 - d2) * 0.03571428571428571d) + d2;
            }
            d2 = d4;
            i++;
            d = d5;
            z = true;
            z2 = true;
        }
        return d - d2;
    }

    static double pvtSlope(List<Candle> list, int i) {
        double d = 0.0d;
        if (list.size() < i + 1) {
            return 0.0d;
        }
        int size = (list.size() - 1) - i;
        boolean z = false;
        int i2 = 1;
        double d2 = 0.0d;
        double d3 = 0.0d;
        while (i2 < list.size()) {
            Candle candle = list.get(i2);
            Candle candle2 = list.get(i2 - 1);
            if (candle2.c != d) {
                d3 += ((candle.c - candle2.c) / candle2.c) * candle.v;
            }
            if (i2 == size) {
                d2 = d3;
                z = true;
            }
            i2++;
            d = 0.0d;
        }
        if (!z) {
            return 0.0d;
        }
        return (d3 - d2) / Math.max(Math.abs(d2), 1.0E-9d);
    }

    static double volumeOsc(List<Candle> list) {
        if (list.size() < 11) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - 5; size < list.size(); size++) {
            d += list.get(size).v;
        }
        double d2 = 0.0d;
        for (int size2 = list.size() - 10; size2 < list.size(); size2++) {
            d2 += list.get(size2).v;
        }
        double d3 = d / 5.0d;
        double d4 = d2 / 10.0d;
        if (d4 != 0.0d) {
            return ((d3 - d4) * 100.0d) / d4;
        }
        return 0.0d;
    }

    static double[] pivotPoints(List<Candle> list) {
        if (list.size() < 30) {
            return null;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - 15; size < list.size() - 1; size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        double d3 = ((d + d2) + list.get(list.size() - 2).c) / 3.0d;
        double d4 = d3 * 2.0d;
        double d5 = d - d2;
        return new double[]{d3, d4 - d2, d3 + d5, d + ((d3 - d2) * 2.0d), d4 - d, d3 - d5, d2 - ((d - d3) * 2.0d)};
    }

    static double[] fibLevels(List<Candle> list) {
        if (list.size() < 30) {
            return null;
        }
        int i = -1;
        double d = Double.MAX_VALUE;
        double d2 = -1.7976931348623157E308d;
        int i2 = -1;
        for (int size = list.size() - 30; size < list.size(); size++) {
            if (list.get(size).h > d2) {
                d2 = list.get(size).h;
                i = size;
            }
            if (list.get(size).l < d) {
                d = list.get(size).l;
                i2 = size;
            }
        }
        boolean z = i > i2;
        double d3 = d2 - d;
        if (d3 <= 0.0d) {
            return null;
        }
        double[] dArr = new double[6];
        if (z) {
            dArr[0] = d2 - (0.236d * d3);
            dArr[1] = d2 - (0.382d * d3);
            dArr[2] = d2 - (0.5d * d3);
            dArr[CONSEC_LOSS_DEFAULT] = d2 - (0.618d * d3);
            dArr[4] = d2 - (d3 * 0.786d);
            dArr[5] = 1.0d;
        } else {
            dArr[0] = d + (0.236d * d3);
            dArr[1] = d + (0.382d * d3);
            dArr[2] = d + (0.5d * d3);
            dArr[CONSEC_LOSS_DEFAULT] = (0.618d * d3) + d;
            dArr[4] = d + (d3 * 0.786d);
            dArr[5] = -1.0d;
        }
        return dArr;
    }

    static Object[] candlePattern(List<Candle> list) {
        boolean z = false;
        Candle candle = null;
        Candle candle2 = null;
        Candle candle3 = null;
        Candle candle4 = null;
        Candle candle5 = null;
        if (list.size() < 4) {
            return null;
        }
        Candle candle6 = list.get(list.size() - 1);
        Candle candle7 = list.get(list.size() - 2);
        Candle candle8 = list.get(list.size() - 3);
        double abs = Math.abs(candle6.c - candle6.o);
        double max = Math.max(1.0E-12d, candle6.h - candle6.l);
        double abs2 = Math.abs(candle7.c - candle7.o);
        double max2 = Math.max(1.0E-12d, candle7.h - candle7.l);
        boolean z2 = candle6.c > candle6.o;
        boolean z3 = candle6.c < candle6.o;
        if (z2) {
            candle = candle7;
            z = z2;
            if (candle.c < candle.o && candle6.c > candle.o && candle6.o < candle.c && abs > abs2) {
                return new Object[]{"Bullish Engulfing", 1};
            }
        } else {
            z = z2;
            candle = candle7;
        }
        if (z3 && candle.c > candle.o && candle6.c < candle.o && candle6.o > candle.c && abs > abs2) {
            return new Object[]{"Bearish Engulfing", -1};
        }
        double min = Math.min(candle6.c, candle6.o) - candle6.l;
        boolean z4 = z3;
        Candle candle9 = candle;
        double max3 = candle6.h - Math.max(candle6.c, candle6.o);
        double d = abs * 2.0d;
        if (min <= d || max3 >= abs * 0.5d || abs2 <= max2 * 0.6d) {
            candle2 = candle6;
            candle3 = candle9;
            candle4 = candle8;
        } else {
            candle3 = candle9;
            candle2 = candle6;
            candle4 = candle8;
            if (candle3.c < candle3.o) {
                return new Object[]{"Hammer", 1};
            }
        }
        if (max3 > d && min < 0.5d * abs && abs2 > 0.6d * max2 && candle3.c > candle3.o) {
            return new Object[]{"Shooting Star", -1};
        }
        if (abs < 0.1d * max) {
            if (candle3.c < candle3.o) {
                return new Object[]{"Doji (after down)", 1};
            }
            if (candle3.c > candle3.o) {
                return new Object[]{"Doji (after up)", -1};
            }
        }
        Candle candle10 = candle4;
        boolean z5 = abs2 < max2 * 0.35d;
        if (candle10.c < candle10.o && z5 && z) {
            candle5 = candle2;
            if (candle5.c > (candle10.c + candle10.o) / 2.0d) {
                return new Object[]{"Morning Star", 1};
            }
        } else {
            candle5 = candle2;
        }
        if (candle10.c > candle10.o && z5 && z4 && candle5.c < (candle10.c + candle10.o) / 2.0d) {
            return new Object[]{"Evening Star", -1};
        }
        if (list.size() >= 4) {
            Candle candle11 = list.get(list.size() - 4);
            if (z && candle3.c > candle3.o && candle10.c > candle10.o && candle11.c > candle11.o && candle5.c > candle3.c && candle3.c > candle10.c && candle10.c > candle11.c) {
                return new Object[]{"Three White Soldiers", 1};
            }
            if (z4 && candle3.c < candle3.o && candle10.c < candle10.o && candle11.c < candle11.o && candle5.c < candle3.c && candle3.c < candle10.c && candle10.c < candle11.c) {
                return new Object[]{"Three Black Crows", -1};
            }
        }
        if (abs > max * 0.92d) {
            return new Object[]{z ? "Bullish Marubozu" : "Bearish Marubozu", Integer.valueOf(z ? 1 : -1)};
        }
        double d2 = (candle3.c + candle3.o) / 2.0d;
        if (z && candle3.c < candle3.o && candle5.c > d2 && candle5.o < candle3.c) {
            return new Object[]{"Piercing Line", 1};
        }
        if (z4 && candle3.c > candle3.o && candle5.c < d2 && candle5.o > candle3.c) {
            return new Object[]{"Dark Cloud Cover", -1};
        }
        if (candle5.h < candle3.h && candle5.l > candle3.l) {
            return new Object[]{"Inside Bar", Integer.valueOf(candle3.c > candle3.o ? 1 : -1)};
        }
        if (candle5.h <= candle3.h || candle5.l >= candle3.l) {
            return null;
        }
        return new Object[]{"Outside Bar", Integer.valueOf(z ? 1 : -1)};
    }

    static Object[] harmonicPattern(List<Candle> list) {
        String str = null;
        if (list.size() < 60) {
            return null;
        }
        ArrayList arrayList = new ArrayList();
        for (int size = list.size() - 54; size < list.size() - 6; size++) {
            boolean z = true;
            boolean z2 = true;
            for (int i = size - 6; i <= size + 6; i++) {
                if (i != size && i >= 0 && i < list.size()) {
                    if (list.get(i).h >= list.get(size).h) {
                        z = false;
                    }
                    if (list.get(i).l <= list.get(size).l) {
                        z2 = false;
                    }
                }
            }
            if ((z || z2) && (arrayList.isEmpty() || size - ((Integer) arrayList.get(arrayList.size() - 1)).intValue() > 6)) {
                arrayList.add(Integer.valueOf(size));
            }
        }
        if (arrayList.size() < 5) {
            return null;
        }
        int size2 = arrayList.size();
        int intValue = ((Integer) arrayList.get(size2 - 5)).intValue();
        int intValue2 = ((Integer) arrayList.get(size2 - 4)).intValue();
        int intValue3 = ((Integer) arrayList.get(size2 - 3)).intValue();
        int intValue4 = ((Integer) arrayList.get(size2 - 2)).intValue();
        int intValue5 = ((Integer) arrayList.get(size2 - 1)).intValue();
        double abs = Math.abs(list.get(intValue2).c - list.get(intValue).c);
        double abs2 = Math.abs(list.get(intValue3).c - list.get(intValue2).c);
        double abs3 = Math.abs(list.get(intValue4).c - list.get(intValue3).c);
        double abs4 = Math.abs(list.get(intValue5).c - list.get(intValue4).c);
        if (abs <= 0.0d || abs3 <= 0.0d) {
            return null;
        }
        double d = abs2 / abs;
        double d2 = abs3 != 0.0d ? abs4 / abs3 : 0.0d;
        boolean z3 = list.get(intValue2).c > list.get(intValue).c;
        if (Math.abs(d - 0.618d) < 0.06d && Math.abs(d2 - 1.272d) < 0.2d) {
            str = "Gartley";
        } else if (d >= 0.382d && d <= 0.5d && Math.abs(d2 - 1.618d) < 0.25d) {
            str = "Bat";
        } else if (Math.abs(d - 0.786d) >= 0.06d || d2 < 1.27d || d2 > 1.9d) {
            str = (d < 0.382d || d > 0.618d || d2 < 1.5d || d2 > 2.6d) ? null : "Crab";
        } else {
            str = "Butterfly";
        }
        if (str == null) {
            return null;
        }
        return new Object[]{str, Integer.valueOf(z3 ? 1 : -1)};
    }

    static int fvg(List<Candle> list) {
        if (list.size() < 4) {
            return 0;
        }
        Candle candle = list.get(list.size() - 3);
        Candle candle2 = list.get(list.size() - 1);
        if (candle.h < candle2.l) {
            return 1;
        }
        return candle.l > candle2.h ? -1 : 0;
    }

    static int bosVoteCalc(List<Candle> list) {
        double[] fractals = null;
        if (list.size() >= ACTIVE_TOP && (fractals = fractals(list)) != null && fractals[0] >= 0.0d && fractals[1] >= 0.0d) {
            double d = list.get(list.size() - 1).c;
            if (d > fractals[0]) {
                return 1;
            }
            if (d < fractals[1]) {
                return -1;
            }
        }
        return 0;
    }

    static int sweepVoteCalc(List<Candle> list) {
        if (list.size() < 25) {
            return 0;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - 25; size < list.size() - 1; size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        Candle candle = list.get(list.size() - 1);
        if (candle.h <= d || candle.c >= d) {
            return (candle.l >= d2 || candle.c <= d2) ? 0 : 1;
        }
        return -1;
    }

    private static class Walk3C {
        double fill = 0.0d;
        Setup3C fire = null;
        Setup3C pending = null;
        String state = null;

        private Walk3C() {
            this.state = "no setup";
        }
    }

    private double bodyPct(Candle candle) {
        double d = candle.h - candle.l;
        if (d <= 0.0d) {
            return 0.0d;
        }
        return Math.abs(candle.c - candle.o) / d;
    }

    private Setup3C detect3C(List<Candle> list, int i, double d, double d2) {
        boolean z = false;
        Candle candle = list.get(i - 2);
        Candle candle2 = list.get(i - 1);
        Candle candle3 = list.get(i);
        boolean z2 = candle.c > candle.o;
        boolean z3 = candle2.c > candle2.o;
        boolean z4 = candle3.c > candle3.o;
        boolean z5 = bodyPct(candle) >= 0.7d;
        boolean z6 = bodyPct(candle2) >= 0.7d;
        if (!z5 || !z6) {
            return null;
        }
        Setup3C setup3C = new Setup3C();
        setup3C.c3Ts = candle3.ts;
        setup3C.zoneHigh = Math.max(candle.h, Math.max(candle2.h, candle3.h));
        setup3C.zoneLow = Math.min(candle.l, Math.min(candle2.l, candle3.l));
        if (z2 && z3 && !z4) {
            z = z3;
            if (candle3.c >= Math.min(candle.l, candle2.l)) {
                setup3C.side = "BUY";
                setup3C.boundary = setup3C.zoneLow;
                setup3C.trigger = setup3C.zoneHigh * (d + 1.0d);
                setup3C.slPrice = setup3C.zoneLow * (1.0d - d2);
                setup3C.c3Idx = i;
                return setup3C;
            }
        } else {
            z = z3;
        }
        if (z2 || z || !z4 || candle3.c > Math.max(candle.h, candle2.h)) {
            return null;
        }
        setup3C.side = "SELL";
        setup3C.boundary = setup3C.zoneHigh;
        setup3C.trigger = setup3C.zoneLow * (1.0d - d);
        setup3C.slPrice = setup3C.zoneHigh * (d2 + 1.0d);
        setup3C.c3Idx = i;
        return setup3C;
    }

    private void log3C(String str, Setup3C setup3C, String str2, String str3) {
        String str4 = str + "|" + setup3C.c3Ts + "|" + str2;
        if (this.threecLogged.contains(str4)) {
            return;
        }
        this.threecLogged.add(str4);
        if (this.threecLogged.size() > 400) {
            Iterator<String> it = this.threecLogged.iterator();
            for (int i = 0; i < 200 && it.hasNext(); i++) {
                it.next();
                it.remove();
            }
        }
        this.db.log("INFO", "3C", str2, str + " — " + str3);
        this.lastPattern = str2 + " " + str;
    }

    private static double trOf(List<Candle> list, int i) {
        if (i <= 0) {
            return list.get(0).h - list.get(0).l;
        }
        Candle candle = list.get(i);
        Candle candle2 = list.get(i - 1);
        return Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
    }

    /* JADX WARN: Multi-variable type inference failed */
    /* JADX WARN: Removed duplicated region for block: B:36:0x025e  */
    /* JADX WARN: Removed duplicated region for block: B:66:0x0364  */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    private Walk3C walk3C(String str, List<Candle> list) {
        double entryBuf = bufSetting("threec_entry_buf_pct");
        double slBuf = bufSetting("threec_sl_buf_pct");
        int size = list.size();
        Walk3C w = new Walk3C();
        if (size < 3) {
            w.state = "data kam — " + size + " candles";
            return w;
        }
        // EMA200 (SMA-seeded pehle 200 close)
        double[] ema = new double[size];
        if (size >= 200) {
            double sum = 0.0d;
            for (int i = 0; i < 200; i++) sum += list.get(i).c;
            double e = sum / 200.0d;
            for (int i = 0; i < 200; i++) ema[i] = e;
            for (int i = 200; i < size; i++) {
                e = ((list.get(i).c - e) * 0.009950248756218905d) + e;
                ema[i] = e;
            }
        } else {
            double e = list.get(0).c;
            for (int i = 0; i < size; i++) {
                e += (list.get(i).c - e) * 0.009950248756218905d;
                ema[i] = e;
            }
        }
        // Wilder ATR(14) array
        double[] atrArr = new double[size];
        double trSum = 0.0d;
        for (int i = 0; i < size; i++) {
            Candle c = list.get(i);
            double tr = i == 0 ? c.h - c.l : Math.max(c.h - c.l, Math.max(Math.abs(c.h - list.get(i - 1).c), Math.abs(c.l - list.get(i - 1).c)));
            trSum += tr;
            if (i >= 14) trSum -= trOf(list, i - 14);
            atrArr[i] = trSum / Math.min(i + 1, 14);
        }
        int last = size - 1;
        Setup3C pending = null;
        for (int i = 2; i <= last; i++) {
            Candle c = list.get(i);
            if (pending != null) {
                int window = i - pending.c3Idx;
                if (window > 5) {
                    log3C(str, pending, "SETUP_EXPIRED", "no breakout by candle 5 — setup expired");
                    pending = null;
                } else {
                    boolean buy = "BUY".equals(pending.side);
                    boolean closedBeyond = buy ? c.c < pending.boundary : c.c > pending.boundary;
                    boolean brokeTrigger = buy ? c.h > pending.trigger : c.l < pending.trigger;
                    if (brokeTrigger && closedBeyond) {
                        log3C(str, pending, "SETUP_INVALIDATED", "UNKNOWN sequence — breakout + close beyond boundary in the same candle; skipped (no tick evidence)");
                        w.state = "UNKNOWN — ambiguous candle, setup skipped";
                        pending = null;
                    } else if (closedBeyond) {
                        log3C(str, pending, "SETUP_INVALIDATED", "candle CLOSED beyond protected boundary " + fpx(pending.boundary) + " (wick alone never cancels)");
                        pending = null;
                    } else if (brokeTrigger) {
                        double fill = buy ? Math.max(pending.trigger, c.o) : Math.min(pending.trigger, c.o);
                        log3C(str, pending, "BREAKOUT_DETECTED", "candle " + window + "/5 broke " + (buy ? "above " : "below ") + fpx(pending.trigger));
                        if (i == last) {
                            w.fire = pending;
                            w.fill = fill;
                            w.state = "ENTRY " + pending.side + " — breakout on candle " + window + "/5, fill " + fpx(fill);
                            return w;
                        }
                        log3C(str, pending, "SETUP_CONSUMED", "breakout candle is history (engine busy/off tha) — stale price par late fill nahi");
                        pending = null;
                    } else {
                        w.state = pending.side + " setup armed — window " + window + "/5, trigger " + fpx(pending.trigger) + ", invalidation close " + (buy ? "< " : "> ") + fpx(pending.boundary);
                    }
                }
            }
            if (pending == null) {
                Setup3C s = detect3C(list, i, entryBuf, slBuf);
                if (s != null) {
                    Candle c3 = list.get(i);
                    s.c3Body = bodyPct(c3);
                    double volSum = 0.0d;
                    int vn = 0;
                    for (int k = Math.max(0, i - 19); k <= i; k++) { volSum += list.get(k).v; vn++; }
                    s.c3VolRatio = (vn <= 0 || volSum <= 0.0d) ? 0.0d : c3.v / (volSum / vn);
                    double a = atrArr[i] > 0.0d ? atrArr[i] : atr(list, 14);
                    s.c3AtrPct = (Double.isNaN(a) || a <= 0.0d) ? 0.0d : (a / c3.c) * 100.0d;
                    if (size >= 200 && ema[i] > 0.0d) s.c3EmaDist = ((c3.c - ema[i]) / ema[i]) * 100.0d;
                    s.c3RdPct = (Math.abs(s.trigger - s.slPrice) / s.trigger) * 100.0d;
                    log3C(str, s, "SETUP_DETECTED", s.side + " — C1/C2 body " + pct(bodyPct(list.get(i - 2))) + "% / " + pct(bodyPct(list.get(i - 1))) + "%, zone " + fpx(s.zoneLow) + " - " + fpx(s.zoneHigh) + ", C3 protected close OK");
                    pending = s;
                }
            }
        }
        w.pending = pending;
        if (pending != null && "no setup".equals(w.state)) {
            w.state = pending.side + " setup armed — waiting for first window candle, trigger " + fpx(pending.trigger);
        }
        return w;
    }

    /* JADX WARN: Code restructure failed: missing block: B:100:0x0125, code lost:
    
        if (r1.c > r2.boundary) goto L42;
     */
    /* JADX WARN: Code restructure failed: missing block: B:73:0x0118, code lost:
    
        if (r1.c < r2.boundary) goto L42;
     */
    /* JADX WARN: Code restructure failed: missing block: B:74:0x0171, code lost:
    
        if (r17 == false) goto L48;
     */
    /* JADX WARN: Code restructure failed: missing block: B:76:0x0179, code lost:
    
        if (r1.h <= r2.trigger) goto L43;
     */
    /* JADX WARN: Code restructure failed: missing block: B:77:0x0161, code lost:
    
        r12 = r7;
        r13 = r8;
        r5 = "BREAKOUT ";
        r14 = r16;
        r7 = r28;
        r8 = r29;
        r3 = null;
        r28 = r10;
        r10 = r27;
     */
    /* JADX WARN: Code restructure failed: missing block: B:78:0x0184, code lost:
    
        r3 = r2.trigger;
        r0 = r1.o;
     */
    /* JADX WARN: Code restructure failed: missing block: B:79:0x0188, code lost:
    
        if (r17 == false) goto L53;
     */
    /* JADX WARN: Code restructure failed: missing block: B:80:0x018a, code lost:
    
        r0 = java.lang.Math.max(r3, r0);
     */
    /* JADX WARN: Code restructure failed: missing block: B:81:0x0193, code lost:
    
        r12 = r0;
     */
    /* JADX WARN: Code restructure failed: missing block: B:82:0x0194, code lost:
    
        if (r17 == false) goto L57;
     */
    /* JADX WARN: Code restructure failed: missing block: B:83:0x0196, code lost:
    
        r0 = 1;
     */
    /* JADX WARN: Code restructure failed: missing block: B:84:0x019a, code lost:
    
        r9.lastVotes = new int[]{r0};
        r9.lastVoteSym = r7;
        r31 = r10.iterator();
     */
    /* JADX WARN: Code restructure failed: missing block: B:86:0x01aa, code lost:
    
        if (r31.hasNext() == false) goto L122;
     */
    /* JADX WARN: Code restructure failed: missing block: B:87:0x01ac, code lost:
    
        r32 = r2;
        r29 = r29;
        openTrade3C(r31.next().longValue(), r7, r32, r12, r15, r2.c3Idx);
        r21 = r21;
        r7 = r7;
        r8 = r8;
        r10 = r10;
        r2 = r32;
        r6 = r6;
        r12 = r12;
        r28 = r28;
        r16 = r16;
        r14 = r14;
     */
    /* JADX WARN: Code restructure failed: missing block: B:89:0x01f5, code lost:
    
        r32 = r2;
        r34 = r6;
        r35 = r12;
        r26 = r14;
        r14 = r16;
        r16 = r28;
        r12 = r7;
        r13 = r8;
        r28 = r10;
        r0 = new java.lang.StringBuilder("LIVE candle ").append(r21).append("/5 broke ");
     */
    /* JADX WARN: Code restructure failed: missing block: B:90:0x0218, code lost:
    
        if (r17 == false) goto L65;
     */
    /* JADX WARN: Code restructure failed: missing block: B:91:0x021a, code lost:
    
        r1 = "above ";
     */
    /* JADX WARN: Code restructure failed: missing block: B:92:0x021f, code lost:
    
        r9.log3C(r12, r32, "BREAKOUT_DETECTED", r0.append(r1).append(fpx(r32.trigger)).append(" — intrabar stop-order fill (candle close ka intezaar nahi)").toString());
        r10 = r27;
        r8 = r29;
        r7 = r16;
        r0 = r14 + r12 + " " + r32.side + r10 + fpx(r35) + " (3C LIVE breakout, SL " + fpx(r32.slPrice) + r8 + pct(riskPct() / 100.0d) + r7;
        r5 = r26;
        r9.lastPattern = r5 + r12;
        r9.threecStates.put(r12, "ENTRY " + r32.side + " — live breakout trigger " + fpx(r32.trigger) + r10 + fpx(r35));
        r6 = r34;
        r3 = null;
        r6.pending = null;
        r0 = r0;
     */
    /* JADX WARN: Code restructure failed: missing block: B:93:0x021d, code lost:
    
        r1 = "below ";
     */
    /* JADX WARN: Code restructure failed: missing block: B:94:0x0198, code lost:
    
        r0 = -1;
     */
    /* JADX WARN: Code restructure failed: missing block: B:95:0x018f, code lost:
    
        r0 = java.lang.Math.min(r3, r0);
     */
    /* JADX WARN: Code restructure failed: missing block: B:97:0x0182, code lost:
    
        if (r1.l >= r2.trigger) goto L43;
     */
    /* JADX WARN: Code restructure failed: missing block: B:98:0x0127, code lost:
    
        r9.log3C(r7, r2, "SETUP_INVALIDATED", "LIVE candle close " + fpx(r1.c) + " protected boundary " + fpx(r2.boundary) + " ke paar — symmetric invalidation, intrabar entry cancel");
        r6.pending = null;
        r9.threecStates.put(r7, "setup invalidated — live close beyond boundary (symmetry check)");
     */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    // ===================== v4.7 MIN-25 CONCURRENT (owner rule) =====================
    // Owner rule: kam az kam 25 trades ek sath OPEN hone chahiye.
    // OPEN < min_open_trades  → universe ke best momentum setups se fill (har trade EXACT risk% — default 1% —, ATR SL, TP 1.5R).
    // OPEN >= min_open_trades → filler BAND — naye trades sirf consensus par (3C breakout fires + council; risk hamesha FLAT riskPct%).
    private int openCountOf(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        int i = rawQuery.moveToFirst() ? rawQuery.getInt(0) : 0;
        rawQuery.close();
        return i;
    }

    private int openSymsOf(long j, String str) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'", new String[]{String.valueOf(j), str});
        int i = rawQuery.moveToFirst() ? rawQuery.getInt(0) : 0;
        rawQuery.close();
        return i;
    }

    private long lastTradeId() {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
        long j = rawQuery.moveToFirst() ? rawQuery.getLong(0) : 0L;
        rawQuery.close();
        return j;
    }

    static double avgVol(List<Candle> list, int i) {
        if (list.size() < 2) return 0.0d;
        int n = Math.min(i, list.size() - 1);
        double d = 0.0d;
        for (int k = list.size() - n; k < list.size(); k++) d += list.get(k).v;
        return d / Math.max(1, n);
    }

    private void ensureMinOpen() {
        int minOpen = minOpenTrades();
        if (minOpen <= 0) return;
        List<Long> users = userIds();
        if (users.isEmpty()) return;
        List<String> syms = activeSymbols();
        for (int u = 0; u < users.size(); u++) {
            long uid = users.get(u).longValue();
            try {
                if (!tradingAllowed(uid)) continue;
                double bal = balanceOf(uid);
                if (bal <= 0.0d) continue;
                int open = openCountOf(uid);
                if (open >= minOpen) continue;
                ArrayList<Object[]> cand = new ArrayList<>();
                for (int s = 0; s < syms.size(); s++) {
                    String sym = syms.get(s);
                    if (openSymsOf(uid, sym) > 0) continue;
                    if (!freshData(sym)) continue;
                    List<Candle> cs = loadCandles(sym);
                    if (cs.size() < 30) continue;
                    Candle last = cs.get(cs.size() - 1);
                    if (System.currentTimeMillis() - last.ts >= TF_MS_PUB) continue;
                    double a = atr(cs, 14);
                    if (!(a > 0.0d)) continue;
                    double c5 = cs.get(cs.size() - 6).c;
                    if (!(c5 > 0.0d)) continue;
                    double ret5 = (last.c - c5) / c5;
                    double av = avgVol(cs, 20);
                    double volr = av > 0.0d ? last.v / av : 1.0d;
                    double score = Math.abs(ret5) * Math.min(5.0d, Math.max(0.2d, volr));
                    cand.add(new Object[]{sym, last, Double.valueOf(ret5), Double.valueOf(a), Double.valueOf(score)});
                }
                Collections.sort(cand, new Comparator<Object[]>() {
                    public int compare(Object[] x, Object[] y) {
                        return Double.compare(((Double) y[4]).doubleValue(), ((Double) x[4]).doubleValue());
                    }
                });
                int filled = 0;
                for (int i = 0; i < cand.size() && open < minOpen; i++) {
                    Object[] o = cand.get(i);
                    String sym = (String) o[0];
                    Candle last = (Candle) o[1];
                    double ret5 = ((Double) o[2]).doubleValue();
                    double a = ((Double) o[3]).doubleValue();
                    String side = ret5 > 0.0d ? "BUY" : "SELL";
                    double entry = slipEntry(last.c, side);
                    double slDist = Math.max(a * 1.5d, entry * 0.0015d);
                    if (!(slDist > 0.0d) || !(entry > 0.0d)) continue;
                    double sl = "BUY".equals(side) ? entry - slDist : entry + slDist;
                    double riskAmt = (riskPct() * bal) / 100.0d;
                    double qty = riskAmt / slDist;
                    if (qty * entry > levCap() * bal) qty = (levCap() * bal) / entry;
                    if (!(qty > 0.0d)) continue;
                    double tp = "BUY".equals(side) ? entry + slDist * threecTpR() : entry - slDist * threecTpR();
                    double riskPctActual = (slDist * qty * 100.0d) / bal;
                    JSONObject f = new JSONObject();
                    try {
                        f.put("src", "MIN25").put("ret5", Math.round(ret5 * 10000.0d) / 10000.0d).put("atrp", Math.round((a / entry) * 10000.0d) / 10000.0d);
                    } catch (Throwable tt) { }
                    this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(uid), sym, side, Double.valueOf(qty), Double.valueOf(entry), Double.valueOf(sl), Double.valueOf(tp), "MIN25_FILL", Integer.valueOf(0), Long.valueOf(System.currentTimeMillis()), Double.valueOf(riskPct() / 100.0d), Double.valueOf(slDist * qty), Double.valueOf(entry), Integer.valueOf(0), Double.valueOf(0.5d), f.toString()});
                    recordOrder(lastTradeId(), uid, sym, side, "MARKET", last.c, qty, "PAPER", "FILLED");
                    open++;
                    filled++;
                    this.db.log("INFO", "MIN25", "ORDER_EXECUTED", sym + " " + side + " [" + open + "/" + minOpen + "] qty=" + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(entry) + " SL=" + fpx(sl) + " TP=" + fpx(tp) + " — risk=$" + String.format(Locale.US, "%.2f", slDist * qty) + " (" + String.format(Locale.US, "%.2f", riskPctActual) + "% of $" + String.format(Locale.US, "%.2f", bal) + ") — min-25 fill, TP " + threecTpR() + "R");
                }
                if (open < minOpen && filled == 0) {
                    this.db.log("INFO", "MIN25", "FILL_WAIT", "open " + open + "/" + minOpen + " — fresh momentum candidates nahi mile (data/one-per-symbol), agle scan par dobara");
                }
            } catch (Throwable t) {
                this.db.log("ERROR", "MIN25", "FILL_FAIL", "user #" + uid + ": " + String.valueOf(t));
            }
        }
    }

    private void scanAndTrade() {
        List<Candle> list = null;
        List<Long> list2 = null;
        String str = null;
        String str2 = null;
        String str3 = null;
        int i = 0;
        String str4 = null;
        String str5 = null;
        Object obj = null;
        String str6 = null;
        String str7 = null;
        StringBuilder sb = null;
        String str8 = null;
        EngineCore engineCore = this;
        List<Long> userIds = userIds();
        List<String> activeSymbols = activeSymbols();
        StringBuilder sb2 = new StringBuilder();
        Iterator<String> it = activeSymbols.iterator();
        String str9 = null;
        int i2 = 0;
        while (it.hasNext()) {
            String next = it.next();
            List<Candle> loadCandles = engineCore.loadCandles(next);
            if (loadCandles.size() < 60) {
                engineCore.threecStates.put(next, "data kam — " + loadCandles.size() + "/60 candles");
            } else {
                // v4.7 FIX: list per-symbol reset — pehle stale/null reh jata tha (NPE root)
                list = loadCandles;
                if (!loadCandles.isEmpty() && System.currentTimeMillis() - loadCandles.get(loadCandles.size() - 1).ts < TF_MS_PUB) {
                    List<Candle> subList = loadCandles.subList(0, loadCandles.size() - 1);
                    if (subList.size() >= 8) {
                        list = subList;
                    }
                }
                Walk3C walk3C = engineCore.walk3C(next, list);
                engineCore.threecStates.put(next, walk3C.state);
                String str10 = "BREAKOUT ";
                Iterator<String> it2 = it;
                List<String> list3 = activeSymbols;
                StringBuilder sb3 = sb2;
                if (walk3C.fire != null || walk3C.pending == null || loadCandles.isEmpty()) {
                    list2 = userIds;
                    str = "BUY";
                    str2 = " @ ";
                    str3 = next;
                    i = i2;
                    str4 = "%) — breakeven at +1R";
                    str5 = ", TP +3R, risk ";
                    obj = null;
                    str6 = "ENTRY OPEN — ";
                    str7 = "BREAKOUT ";
                } else {
                    Candle candle = loadCandles.get(loadCandles.size() - 1);
                    Setup3C setup3C = walk3C.pending;
                    String str11 = "%) — breakeven at +1R";
                    String str12 = ", TP +3R, risk ";
                    boolean z = System.currentTimeMillis() - candle.ts < TF_MS_PUB;
                    String str13 = "ENTRY OPEN — ";
                    int size = list.size() - setup3C.c3Idx;
                    if (z && size > 5) {
                        engineCore.log3C(next, setup3C, "SETUP_EXPIRED", "no breakout by candle 5 — window khatam, live trigger band");
                        walk3C.pending = null;
                        engineCore.threecStates.put(next, "setup expired — 5/5 window complete, breakout nahi hua");
                    } else if (z && size >= 1) {
                        boolean equals = "BUY".equals(setup3C.side);
                        int i3 = size;
                        if (equals) {
                            str = "BUY";
                            str8 = " @ ";
                        } else {
                            str = "BUY";
                            str8 = " @ ";
                        }
                    }
                    str = "BUY";
                    str7 = "BREAKOUT ";
                    str6 = str13;
                    obj = null;
                    str3 = next;
                    str4 = str11;
                    list2 = userIds;
                    str2 = " @ ";
                    i = i2;
                    str5 = str12;
                }
                if (walk3C.fire != null) {
                    engineCore.lastVotes = new int[]{str.equals(walk3C.fire.side) ? 1 : -1};
                    engineCore.lastVoteSym = str3;
                    // v4.6 OWNER TUNE: side + volume quality gate (settings threec_side / threec_vol_min)
                    boolean sideOk = "BOTH".equals(threecSide()) || threecSide().equals(walk3C.fire.side);
                    boolean volOk = threecVolMin() <= 0.0d || walk3C.fire.c3VolRatio >= threecVolMin();
                    if (sideOk && volOk) {
                        Iterator<Long> it3 = list2.iterator();
                        while (it3.hasNext()) {
                            openTrade3C(it3.next().longValue(), str3, walk3C.fire, walk3C.fill, list, walk3C.fire.c3Idx);
                            str5 = str5;
                            walk3C = walk3C;
                            str4 = str4;
                            list = list;
                            obj = obj;
                            str7 = str7;
                            i = i;
                        }
                    } else {
                        engineCore.log3C(str3, walk3C.fire, "TUNE_GATE", "setup owner-tune gate se skip (side=" + threecSide() + ", volMin=" + threecVolMin() + ", volRatio=" + String.format(Locale.US, "%.2f", Double.valueOf(walk3C.fire.c3VolRatio)) + ")");
                    }
                    int i4 = i;
                    Walk3C walk3C2 = walk3C;
                    str9 = str6 + str3 + " " + walk3C2.fire.side + str2 + fpx(walk3C2.fill) + " (3C breakout, SL " + fpx(walk3C2.fire.slPrice) + str5 + pct(riskPct() / 100.0d) + str4;
                    this.lastPattern = str7 + str3;
                    engineCore = this;
                    it = it2;
                    activeSymbols = list3;
                    sb2 = sb3;
                    i2 = i4;
                } else {
                    EngineCore engineCore2 = engineCore;
                    int i5 = i;
                    List<Candle> list4 = list;
                    String str14 = str;
                    Walk3C walk3C3 = walk3C;
                    if (walk3C3.pending != null) {
                        engineCore2.lastVotes = new int[]{str14.equals(walk3C3.pending.side) ? 1 : -1};
                        engineCore2.lastVoteSym = str3;
                        i2 = i5 + 1;
                        if (sb3.length() > 0) {
                            sb = sb3;
                            sb.append(" | ");
                        } else {
                            sb = sb3;
                        }
                        if (sb.length() < 100) {
                            sb.append(str3).append(" ").append(walk3C3.pending.side);
                        }
                    } else {
                        sb = sb3;
                        engineCore2.lastVotes = new int[1];
                        i2 = i5;
                    }
                    if (engineCore2.lab != null) {
                        Iterator<Long> it4 = list2.iterator();
                        while (it4.hasNext()) {
                            engineCore2.tryCustomStrategies(it4.next().longValue(), str3, list4);
                        }
                    }
                    engineCore = engineCore2;
                    sb2 = sb;
                    it = it2;
                    activeSymbols = list3;
                }
                userIds = list2;
            }
        }
        int i6 = i2;
        EngineCore engineCore3 = engineCore;
        List<String> list5 = activeSymbols;
        StringBuilder sb4 = sb2;
        if (str9 != null) {
            engineCore3.lastConsensus = str9;
        } else if (i6 > 0) {
            engineCore3.lastConsensus = "3C M5 scan #" + engineCore3.scanCount + " — " + list5.size() + " syms — " + i6 + " setup(s) armed: " + ((Object) sb4) + " — breakout window chal raha hai";
        } else {
            engineCore3.lastConsensus = "3C M5 scan #" + engineCore3.scanCount + " — " + list5.size() + " syms — koi valid 3C setup nahi (C1+C2 70% body + C3 protected + 5-candle breakout window)";
        }
    }

    private double[] fundingOi(String str) {
        long currentTimeMillis = System.currentTimeMillis();
        if (currentTimeMillis - this.fundingAt > 900000) {
            this.fundingCache.clear();
            this.fundingAt = currentTimeMillis;
        }
        if (this.fundingCache.containsKey(str)) {
            return this.fundingCache.get(str);
        }
        try {
            String httpGetUrl = httpGetUrl("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=" + str, 8000);
            if (httpGetUrl == null) {
                this.fundingCache.put(str, null);
                return null;
            }
            double d = Double.NaN;
            double optDouble = new JSONObject(httpGetUrl).optDouble("lastFundingRate", Double.NaN);
            String httpGetUrl2 = httpGetUrl("https://fapi.binance.com/futures/data/openInterestHist?symbol=" + str + "&period=1h&limit=25", 8000);
            double d2 = 0.0d;
            if (httpGetUrl2 != null) {
                JSONArray jSONArray = new JSONArray(httpGetUrl2);
                if (jSONArray.length() >= 2) {
                    double optDouble2 = jSONArray.getJSONObject(0).optDouble("sumOpenInterest", 0.0d);
                    double optDouble3 = jSONArray.getJSONObject(jSONArray.length() - 1).optDouble("sumOpenInterest", 0.0d);
                    if (optDouble2 > 0.0d) {
                        d = 100.0d * ((optDouble3 - optDouble2) / optDouble2);
                    }
                }
            }
            if (Double.isNaN(optDouble)) {
                this.fundingCache.put(str, null);
                return null;
            }
            if (!Double.isNaN(d)) {
                d2 = d;
            }
            double[] dArr = {optDouble, d2};
            this.fundingCache.put(str, dArr);
            return dArr;
        } catch (Throwable unused) {
            this.fundingCache.put(str, null);
            return null;
        }
    }

    private void scanPdfPack() {
        int max = 0;
        int i = 0;
        if ("1".equals(this.db.setting("pack_on", "0")) && !this.rot15.isEmpty() && (max = Math.max(0, this.rot15Pos - 30)) < (i = this.rot15Pos)) {
            List<Long> userIds = userIds();
            for (max = Math.max(0, this.rot15Pos - 30); max < i && max < this.rot15.size(); max++) {
                String str = this.rot15.get(max);
                try {
                    List<Candle> loadCandles15 = loadCandles15(str);
                    if (loadCandles15.size() >= 220) {
                        if (!loadCandles15.isEmpty() && System.currentTimeMillis() - loadCandles15.get(loadCandles15.size() - 1).ts < TF_MS_PUB) {
                            loadCandles15 = loadCandles15.subList(0, loadCandles15.size() - 1);
                            if (loadCandles15.size() < 220) {
                            }
                        }
                        List<Candle> list = loadCandles15;
                        Candle candle = list.get(list.size() - 1);
                        Long l = this.lastEval15.get(str);
                        if (l == null || l.longValue() != candle.ts) {
                            this.lastEval15.put(str, Long.valueOf(candle.ts));
                            double[] prevDayHighLow = prevDayHighLow(list);
                            double[] adxAt = StrategyPack.adxAt(list, 14, list.size() - 1);
                            for (StrategyPack.Signal signal : StrategyPack.evaluateAll(list, list.size() - 1, prevDayHighLow, fundingOi(str), adxAt == null ? -1.0d : adxAt[0])) {
                                if ("1".equals(this.db.setting("pack_" + signal.strategy.toLowerCase(Locale.ROOT), "1")) && aiEnabled(signal.strategy)) {
                                    Iterator<Long> it = userIds.iterator();
                                    while (it.hasNext()) {
                                        openTradePdf(it.next().longValue(), str, signal);
                                    }
                                }
                            }
                        }
                    }
                } catch (Throwable th) {
                    this.db.log("WARN", "PACK", "EVAL_FAIL", str + " — " + th);
                }
            }
        }
    }

    boolean aiEnabled(String str) {
        JSONObject aiWeights = null;
        try {
            if (!"1".equals(this.db.setting("ai_off_" + str, "0")) && (aiWeights = aiWeights()) != null && aiWeights.has(str)) {
                return aiWeights.getJSONObject(str).optInt("on", 1) == 1;
            }
            return true;
        } catch (Throwable unused) {
            return true;
        }
    }

    JSONObject aiWeights() {
        long currentTimeMillis = System.currentTimeMillis();
        JSONObject jSONObject = this.aiWeightsCache;
        if (jSONObject != null && currentTimeMillis - this.aiWeightsAt < 60000) {
            return jSONObject;
        }
        try {
            JSONObject jSONObject2 = new JSONObject(this.db.setting("ai_weights_v2", "{}"));
            this.aiWeightsCache = jSONObject2;
            this.aiWeightsAt = currentTimeMillis;
            return jSONObject2;
        } catch (Throwable unused) {
            return null;
        }
    }

    void invalidateAiWeights() {
        this.aiWeightsCache = null;
        this.aiWeightsAt = 0L;
    }

    private void openTradePdf(long j, String str, StrategyPack.Signal signal) {
        String str2 = "PDF:" + signal.strategy;
        if (!freshData(str) || strategyPaused(str2) || entryBlocked(j, str)) {
            return;
        }
        if (!tradingAllowed(j)) {
            askOwnerToEnableTrading(j);
            return;
        }
        if (eventGateActive()) {
            return;
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'", new String[]{String.valueOf(j), str, str2});
        boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) > 0;
        rawQuery.close();
        if (z) {
            return;
        }
        List<Candle> loadCandles15 = loadCandles15(str);
        if (loadCandles15.isEmpty()) {
            return;
        }
        double livePrice = livePrice(str);
        if (livePrice <= 0.0d) {
            livePrice = loadCandles15.get(loadCandles15.size() - 1).c;
        }
        double d = livePrice;
        double abs = Math.abs(d - signal.slPrice);
        if (abs <= 0.0d || d <= 0.0d) {
            return;
        }
        double d2 = abs * 2.0d;
        if (feeEdgeOk(str2 + " " + str, d, d2)) {
            int councilScore = councilScore(str, signal.side, loadCandles15, loadCandles15.size() - 1);
            int councilMin = councilMin();
            if (councilMin <= 0 || councilScore >= councilMin) {
                double heatMaxPct = heatMaxPct();
                double bucketMaxPct = bucketMaxPct();
                if (heatMaxPct <= 0.0d || heatRiskPct(j) + 1.0d <= heatMaxPct) {
                    if (bucketMaxPct > 0.0d && bucketRiskPct(j, bucketOf(str)) + 1.0d > bucketMaxPct) {
                        return;
                    }
                    double slipEntry = slipEntry(d, signal.side);
                    double balanceOf = balanceOf(j);
                    if (balanceOf <= 0.0d) {
                        return;
                    }
                    double dynamicRiskPct = ((dynamicRiskPct(str2) * balanceOf) / 100.0d) / abs;
                    if (dynamicRiskPct * slipEntry > levCap() * balanceOf) {
                        dynamicRiskPct = (balanceOf * levCap()) / slipEntry;
                    }
                    double d3 = dynamicRiskPct;
                    if (d3 <= 0.0d) {
                        return;
                    }
                    boolean equals = "BUY".equals(signal.side);
                    double d4 = equals ? slipEntry - abs : slipEntry + abs;
                    double d5 = equals ? slipEntry + d2 : slipEntry - d2;
                    JSONObject jSONObject = new JSONObject();
                    try {
                        jSONObject.put("boundary", signal.boundary).put("sig_ts", signal.sigTs).put("window_bars", signal.windowBars).put("tf", "5m").put("note", signal.note);
                    } catch (Throwable unused) {
                    }
                    this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), str, signal.side, Double.valueOf(d3), Double.valueOf(slipEntry), Double.valueOf(d4), Double.valueOf(d5), str2, Double.valueOf(0.7d), Long.valueOf(System.currentTimeMillis()), Double.valueOf(dynamicRiskPct(str2) / 100.0d), Double.valueOf(abs * d3), Double.valueOf(slipEntry), Integer.valueOf(councilScore), Double.valueOf(mlWinProb(jSONObject)), jSONObject.toString()});
                    Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
                    long j2 = rawQuery2.moveToFirst() ? rawQuery2.getLong(0) : 0L;
                    rawQuery2.close();
                    recordOrder(j2, j, str, signal.side, "MARKET", slipEntry, d3, "PAPER", "FILLED");
                    bridgeOrder(str, signal.side, j2, j, slipEntry, d3);
                    this.db.log("INFO", "PACK", "ORDER_EXECUTED", str + " " + signal.side + " [" + str2 + "] qty=" + String.format(Locale.US, "%.6f", Double.valueOf(d3)) + " entry=" + fpx(slipEntry) + " sl=" + fpx(d4) + " — " + signal.note + " (risk 1%, TP +2R, boundary invalidation)");
                }
            }
        }
    }

    private boolean feeEdgeOk(String str, double d, double d2) {
        double d3 = 0.0d;
        if (!"1".equals(this.db.setting("fee_edge_on", "1"))) {
            return true;
        }
        try {
            d3 = Double.parseDouble(this.db.setting("min_fee_edge_pct", "0.14").trim());
        } catch (Throwable unused) {
            d3 = 0.14d;
        }
        if (d <= 0.0d || d2 <= 0.0d) {
            return true;
        }
        // v1.2 RISK FIX: cost-aware floor — RT fees+slip TP distance ke fee_max_r (default 0.5R) se zyada nahi ho sakte.
        // Pehle floor 0.14% = EXACTLY RT cost thi, isliye fees poori TP kha jate the → profit hamesha 0 ke aas paas atak jata tha.
        double feeMaxR = 0.0d;
        try {
            feeMaxR = Double.parseDouble(this.db.setting("fee_max_r", "0.5").trim());
        } catch (Throwable unused2) {
            feeMaxR = 0.5d;
        }
        double costPct = (takerFee() + (slipBps() / 10000.0d)) * 2.0d * 100.0d;
        double dFloor = d3;
        if (feeMaxR > 0.0d) {
            double dyn = costPct * (2.0d / feeMaxR);
            if (dyn > dFloor) {
                dFloor = dyn;
            }
        }
        double d4 = (d2 / d) * 100.0d;
        if (d4 >= dFloor) {
            return true;
        }
        this.db.log("INFO", "GUARD", "FEE_EDGE_SKIP", str + " — TP move " + String.format(Locale.US, "%.3f", Double.valueOf(d4)) + "% < costs " + String.format(Locale.US, "%.2f", Double.valueOf(dFloor)) + "% (fees+slip " + String.format(Locale.US, "%.3f", Double.valueOf(costPct)) + "%, cap " + feeMaxR + "R) — skip (fees edge kha jate the, isliye profit 0 atakta tha)");
        return false;
    }

    static double pbSlAtrMult(String str) {
        if (str.startsWith("P1")) {
            return 5.0d;
        }
        if (str.startsWith("P2")) {
            return 4.0d;
        }
        return X7_SIGMA;
    }

    static double pbTrailAtrMult(String str) {
        return str.startsWith("P4") ? 7.0d : 8.0d;
    }

    private void scanPlaybook() {
        if ("1".equals(this.db.setting("pb_on", "1"))) {
            List<Long> userIds = userIds();
            for (String str : PB_SYMBOLS) {
                try {
                    ensurePbHistory(str);
                    List<Candle> loadCandles15 = loadCandles15(str);
                    if (loadCandles15.size() >= 500) {
                        if (!loadCandles15.isEmpty() && System.currentTimeMillis() - loadCandles15.get(loadCandles15.size() - 1).ts < TF_MS_PUB) {
                            loadCandles15 = loadCandles15.subList(0, loadCandles15.size() - 1);
                            if (loadCandles15.size() < 500) {
                            }
                        }
                        Candle candle = loadCandles15.get(loadCandles15.size() - 1);
                        Long l = this.lastEvalPb.get(str);
                        if (l == null || l.longValue() != candle.ts) {
                            this.lastEvalPb.put(str, Long.valueOf(candle.ts));
                            for (StrategyPack.Signal signal : StrategyPack.evaluatePlaybook(loadCandles15, loadCandles15.size() - 1)) {
                                if ("1".equals(this.db.setting("pack_" + signal.strategy.toLowerCase(Locale.ROOT), "1")) && aiEnabled(signal.strategy)) {
                                    Iterator<Long> it = userIds.iterator();
                                    while (it.hasNext()) {
                                        openTradePb(it.next().longValue(), str, signal);
                                    }
                                }
                            }
                        }
                    }
                } catch (Throwable th) {
                    this.db.log("WARN", "PB", "EVAL_FAIL", str + " — " + th);
                }
            }
        }
    }

    private void ensurePbHistory(String str) {
        long j = 0L;
        long currentTimeMillis = System.currentTimeMillis();
        Long l = this.lastPbFill.get(str);
        if (l == null || currentTimeMillis - l.longValue() >= TF_MS_PUB) {
            int i = 0;
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*), MAX(ts) FROM candles WHERE symbol=? AND tf=?", new String[]{str, "5m"});
            if (rawQuery.moveToFirst()) {
                i = rawQuery.getInt(0);
                j = rawQuery.getLong(1);
            } else {
                j = 0;
            }
            rawQuery.close();
            if (i >= 4400 && currentTimeMillis - j < TF_MS_PUB) {
                this.lastPbFill.put(str, Long.valueOf(currentTimeMillis));
                return;
            }
            List<Candle> fetchFromBinancePaged = fetchFromBinancePaged(str, "5m", 5);
            if (fetchFromBinancePaged != null && !fetchFromBinancePaged.isEmpty()) {
                upsertCandles15(str, fetchFromBinancePaged);
                this.db.log("INFO", "PB", "HISTORY_FILL", str + " — " + fetchFromBinancePaged.size() + " 5m bars fetched (deep history " + i + " → " + (i + fetchFromBinancePaged.size()) + ")");
            }
            this.lastPbFill.put(str, Long.valueOf(currentTimeMillis));
        }
    }

    private List<Candle> fetchFromBinancePaged(String str, String str2, int i) {
        ArrayList arrayList = new ArrayList();
        Long l = null;
        for (int i2 = 0; i2 < i; i2++) {
            try {
                String httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/klines?symbol=" + str + "&interval=" + str2 + "&limit=1000" + (l != null ? "&endTime=" + l : ""), 12000);
                if (httpGetUrl == null) {
                    break;
                }
                List<Candle> parseBinanceKlines = parseBinanceKlines(httpGetUrl);
                if (parseBinanceKlines.isEmpty()) {
                    break;
                }
                arrayList.addAll(parseBinanceKlines);
                long j = parseBinanceKlines.get(0).ts;
                if (l != null && j >= l.longValue()) {
                    break;
                }
                l = Long.valueOf(j - 1);
                if (parseBinanceKlines.size() < 1000) {
                    break;
                }
            } catch (Throwable unused) {
            }
        }
        return arrayList;
    }

    private void openTradePb(long j, String str, StrategyPack.Signal signal) {
        String str2 = "PB:" + signal.strategy;
        if (!freshData(str) || strategyPaused(str2) || entryBlocked(j, str)) {
            return;
        }
        if (!tradingAllowed(j)) {
            askOwnerToEnableTrading(j);
            return;
        }
        if (eventGateActive()) {
            return;
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'", new String[]{String.valueOf(j), str, str2});
        boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) > 0;
        rawQuery.close();
        if (z) {
            return;
        }
        List<Candle> loadCandles15 = loadCandles15(str);
        if (loadCandles15.size() < 600) {
            return;
        }
        double atrAt = StrategyPack.atrAt(loadCandles15, 14, loadCandles15.size() - 1);
        if (atrAt <= 0.0d) {
            return;
        }
        double livePrice = livePrice(str);
        if (livePrice <= 0.0d) {
            livePrice = loadCandles15.get(loadCandles15.size() - 1).c;
        }
        double d = livePrice;
        double pbSlAtrMult = pbSlAtrMult(signal.strategy) * atrAt;
        if (pbSlAtrMult <= 0.0d || d <= 0.0d) {
            return;
        }
        if (feeEdgeOk(str2 + " " + str, d, atrAt * 2.0d)) {
            double heatMaxPct = heatMaxPct();
            double bucketMaxPct = bucketMaxPct();
            if (heatMaxPct <= 0.0d || heatRiskPct(j) + 1.0d <= heatMaxPct) {
                if (bucketMaxPct > 0.0d && bucketRiskPct(j, bucketOf(str)) + 1.0d > bucketMaxPct) {
                    return;
                }
                double slipEntry = slipEntry(d, signal.side);
                double balanceOf = balanceOf(j);
                if (balanceOf <= 0.0d) {
                    return;
                }
                double dynamicRiskPct = ((dynamicRiskPct(str2) * balanceOf) / 100.0d) / pbSlAtrMult;
                if (dynamicRiskPct * slipEntry > levCap() * balanceOf) {
                    dynamicRiskPct = (balanceOf * levCap()) / slipEntry;
                }
                double d2 = dynamicRiskPct;
                if (d2 <= 0.0d) {
                    return;
                }
                boolean equals = "BUY".equals(signal.side);
                double d3 = equals ? slipEntry - pbSlAtrMult : slipEntry + pbSlAtrMult;
                double d4 = 1000.0d * atrAt;
                double d5 = equals ? slipEntry + d4 : slipEntry - d4;
                JSONObject jSONObject = new JSONObject();
                try {
                    jSONObject.put("pb", 1).put("atr", atrAt).put("sl_mult", pbSlAtrMult(signal.strategy)).put("trail_mult", pbTrailAtrMult(signal.strategy)).put("trail", 0).put("bars", 0).put("last_bar_ts", signal.sigTs).put("sig_ts", signal.sigTs).put("tf", "5m").put("note", signal.note);
                } catch (Throwable unused) {
                }
                this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), str, signal.side, Double.valueOf(d2), Double.valueOf(slipEntry), Double.valueOf(d3), Double.valueOf(d5), str2, Double.valueOf(0.7d), Long.valueOf(System.currentTimeMillis()), Double.valueOf(dynamicRiskPct(str2) / 100.0d), Double.valueOf(pbSlAtrMult * d2), Double.valueOf(slipEntry), 0, Double.valueOf(mlWinProb(jSONObject)), jSONObject.toString()});
                Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
                long j2 = rawQuery2.moveToFirst() ? rawQuery2.getLong(0) : 0L;
                rawQuery2.close();
                recordOrder(j2, j, str, signal.side, "MARKET", slipEntry, d2, "PAPER", "FILLED");
                bridgeOrder(str, signal.side, j2, j, slipEntry, d2);
                this.db.log("INFO", "PB", "ORDER_EXECUTED", str + " " + signal.side + " [" + str2 + "] qty=" + String.format(Locale.US, "%.6f", Double.valueOf(d2)) + " entry=" + fpx(slipEntry) + " sl=" + fpx(d3) + " — " + signal.note + " (guide sizing, NO TP — trail exit)");
                try {
                    Notifier.post(appContext(), "Playbook trade", str + " " + signal.side + " [" + signal.strategy + "] — " + signal.note);
                } catch (Throwable unused2) {
                }
            }
        }
    }

    /* JADX WARN: Removed duplicated region for block: B:73:0x01e1  */
    /* JADX WARN: Removed duplicated region for block: B:93:0x01e4  */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    private void managePbTrade(long j, long j2, String str, String str2, double d, double d2, double d3, boolean z) {
        Throwable th = null;
        String str3 = null;
        String str4 = null;
        String str5 = null;
        JSONObject jSONObject = null;
        double optDouble = 0.0d;
        double optDouble2 = 0.0d;
        double optDouble3 = 0.0d;
        long optLong = 0L;
        int optInt = 0;
        long j3 = 0L;
        char c = '\u0000';
        double d4 = 0.0d;
        String str6 = null;
        EngineCore engineCore = this;
        String str7 = " — ";
        String str8 = "trade #";
        try {
            Cursor rawQuery = engineCore.db.getReadableDatabase().rawQuery("SELECT features FROM trades WHERE id=?", new String[]{String.valueOf(j)});
            String string = rawQuery.moveToFirst() ? rawQuery.getString(0) : "{}";
            rawQuery.close();
            jSONObject = new JSONObject(string);
            optDouble = jSONObject.optDouble("atr", 0.0d);
            optDouble2 = jSONObject.optDouble("trail_mult", 8.0d);
            optDouble3 = jSONObject.optDouble("trail", 0.0d);
            optLong = jSONObject.optLong("last_bar_ts", 0L);
            optInt = jSONObject.optInt("bars", 0);
        } catch (Throwable thz) {
            str3 = "PB";
        }
        if (optDouble <= 0.0d) {
            return;
        }
        long currentTimeMillis = System.currentTimeMillis();
        SQLiteDatabase readableDatabase = engineCore.db.getReadableDatabase();
        long j4 = currentTimeMillis - TF_MS_PUB;
        Cursor rawQuery2 = readableDatabase.rawQuery("SELECT ts, c FROM candles WHERE symbol=? AND tf=? AND ts>? AND ts<=? ORDER BY ts", new String[]{str, "5m", String.valueOf(optLong), String.valueOf(j4)});
        ArrayList arrayList = new ArrayList();
        ArrayList arrayList2 = new ArrayList();
        while (rawQuery2.moveToNext()) {
            arrayList.add(new long[]{rawQuery2.getLong(0)});
            arrayList2.add(Double.valueOf(rawQuery2.getDouble(1)));
            optInt = optInt;
        }
        int i = optInt;
        rawQuery2.close();
        int i2 = i;
        int i3 = 0;
        String str9 = "PB";
        String str10 = "trade #";
        double d5 = optDouble3;
        while (true) {
            j3 = optLong;
            try {
                if (i3 >= arrayList.size()) {
                    break;
                }
                optLong = ((long[]) arrayList.get(i3))[0];
                double doubleValue = ((Double) arrayList2.get(i3)).doubleValue();
                if (i2 >= 4) {
                    double d6 = optDouble2 * optDouble;
                    double d7 = z ? doubleValue - d6 : doubleValue + d6;
                    if (d5 != 0.0d) {
                        d7 = z ? Math.max(d5, d7) : Math.min(d5, d7);
                    }
                    d5 = d7;
                }
                i2++;
                i3++;
            } catch (Throwable th2) {
                th = th2;
                engineCore = this;
            }
        }
        if (arrayList.isEmpty()) {
            engineCore = this;
        } else {
            engineCore = this;
            try {
                jSONObject.put("trail", d5).put("last_bar_ts", j3).put("bars", i2);
                engineCore.db.getWritableDatabase().execSQL("UPDATE trades SET features=? WHERE id=?", new Object[]{jSONObject.toString(), Long.valueOf(j)});
            } catch (Throwable th3) {
                th = th3;
            }
        }
        boolean z2 = i2 >= 4 && d5 != 0.0d;
        double d8 = z2 ? d5 : d3;
        double[][] dArr = new double[2][];
        Cursor rawQuery3 = engineCore.db.getReadableDatabase().rawQuery("SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts<=? ORDER BY ts DESC LIMIT 1", new String[]{str, "5m", String.valueOf(j4)});
        if (rawQuery3.moveToFirst()) {
            dArr[0] = new double[]{rawQuery3.getDouble(0), rawQuery3.getDouble(1)};
        }
        rawQuery3.close();
        Cursor rawQuery4 = engineCore.db.getReadableDatabase().rawQuery("SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts>? ORDER BY ts DESC LIMIT 1", new String[]{str, "5m", String.valueOf(j4)});
        if (rawQuery4.moveToFirst()) {
            dArr[1] = new double[]{rawQuery4.getDouble(0), rawQuery4.getDouble(1)};
        }
        rawQuery4.close();
        int i4 = 0;
        while (i4 < 2) {
            double[] dArr2 = dArr[i4];
            if (dArr2 != null) {
                if (z) {
                    if (dArr2[1] <= d8) {
                        String str11 = !z2 ? "TRAIL" : "SL";
                        Db db = engineCore.db;
                        str8 = str10;
                        String str12 = null;
                        try {
                            str12 = str8 + j + " " + str + str7 + str11 + " hit @ " + fpx(d8) + " (bars=" + i2 + ")";
                            str6 = str9;
                        } catch (Throwable th4) {
                            th = th4;
                            str4 = str7;
                            str3 = str9;
                            str5 = str8;
                            engineCore.db.log("WARN", str3, "MANAGE_FAIL", str5 + j + str4 + th);
                            return;
                        }
                        try {
                            db.log("INFO", str6, "PLAYBOOK_EXIT", str12);
                            closeTrade(j, j2, d8, str11, d, d2, str2);
                            return;
                        } catch (Throwable th5) {
                            th = th5;
                            str3 = str6;
                            str4 = str7;
                            str5 = str8;
                            engineCore.db.log("WARN", str3, "MANAGE_FAIL", str5 + j + str4 + th);
                            return;
                        }
                    }
                } else if (dArr2[0] >= d8) {
                    String str112 = !z2 ? "TRAIL" : "SL";
                    Db db2 = engineCore.db;
                    str8 = str10;
                    String str122 = str8 + j + " " + str + str7 + str112 + " hit @ " + fpx(d8) + " (bars=" + i2 + ")";
                    str6 = str9;
                    try {
                        db2.log("INFO", str6, "PLAYBOOK_EXIT", str122);
                        closeTrade(j, j2, d8, str112, d, d2, str2);
                        return;
                    } catch (Throwable thz2) {
                        str4 = str7;
                        str3 = str9;
                        str5 = str10;
                        engineCore.db.log("WARN", str3, "MANAGE_FAIL", str5 + j + str4 + thz2);
                        return;
                    }
                }
            }
            str4 = str7;
            str3 = str9;
            str5 = str10;
            i4++;
            str10 = str5;
            str7 = str4;
            str9 = str3;
        }
        double[] dArr3 = dArr[0];
        if (dArr3 != null) {
            if (z) {
                d4 = (dArr3[0] - d2) * d;
                c = 1;
            } else {
                c = 1;
                d4 = (d2 - dArr3[1]) * d;
            }
            engineCore.db.getWritableDatabase().execSQL("UPDATE trades SET mfe=MAX(IFNULL(mfe,0),?), mae=MAX(IFNULL(mae,0),?) WHERE id=?", new Object[]{Double.valueOf(Math.max(0.0d, d4)), Double.valueOf(Math.max(0.0d, (z ? d2 - dArr3[c] : dArr3[0] - d2) * d)), Long.valueOf(j)});
        }
    }

    private void scanX7() {
        if ("1".equals(this.db.setting("x7_on", "1"))) {
            List<Long> userIds = userIds();
            for (String str : activeSymbols()) {
                try {
                    List<Candle> loadCandles = loadCandles(str);
                    if (loadCandles.size() >= 300) {
                        if (!loadCandles.isEmpty() && System.currentTimeMillis() - loadCandles.get(loadCandles.size() - 1).ts < TF_MS_PUB) {
                            loadCandles = loadCandles.subList(0, loadCandles.size() - 1);
                            if (loadCandles.size() < 300) {
                            }
                        }
                        List<Candle> list = loadCandles;
                        Candle candle = list.get(list.size() - 1);
                        Long l = this.lastEvalX7.get(str);
                        if (l == null || l.longValue() != candle.ts) {
                            this.lastEvalX7.put(str, Long.valueOf(candle.ts));
                            String x7Signal = x7Signal(list, list.size() - 1);
                            if (x7Signal != null) {
                                Iterator<Long> it = userIds.iterator();
                                while (it.hasNext()) {
                                    openTradeX7(it.next().longValue(), str, x7Signal, list);
                                }
                            }
                        }
                    }
                } catch (Throwable th) {
                    this.db.log("WARN", "X7", "EVAL_FAIL", str + " — " + th);
                }
            }
        }
    }

    static String x7Signal(List<Candle> list, int i) {
        if (i < 300 || i >= list.size()) {
            return null;
        }
        int max = Math.max(0, i - 287);
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        for (int i2 = max; i2 <= i; i2++) {
            Candle candle = list.get(i2);
            d3 += (((candle.h + candle.l) + candle.c) / 3.0d) * candle.v;
            d2 += candle.v;
        }
        if (d2 <= 0.0d) {
            return null;
        }
        double d4 = d3 / d2;
        double d5 = 0.0d;
        int i3 = 0;
        while (max <= i) {
            double d6 = list.get(max).c - d4;
            d5 += d6 * d6;
            i3++;
            max++;
        }
        double sqrt = Math.sqrt(d5 / Math.max(1, i3));
        if (sqrt <= 0.0d) {
            return null;
        }
        int i4 = i - 13;
        double d7 = 0.0d;
        double d8 = 0.0d;
        while (i4 <= i) {
            double d9 = list.get(i4).c - list.get(i4 - 1).c;
            if (d9 > 0.0d) {
                d7 += d9;
            } else {
                d8 -= d9;
            }
            i4++;
            d = 0.0d;
        }
        double d10 = d8 + d7;
        if (d10 == d) {
            return null;
        }
        double d11 = (d7 * 100.0d) / d10;
        double[] adxAt = StrategyPack.adxAt(list, 56, i);
        if (adxAt == null || adxAt[0] >= X7_ADX_MAX) {
            return null;
        }
        Candle candle2 = list.get(i);
        double d12 = candle2.c;
        double d13 = sqrt * X7_SIGMA;
        if (d12 < d4 - d13 && d11 < X7_RSI_LO) {
            return "BUY";
        }
        if (candle2.c <= d4 + d13 || d11 <= X7_RSI_HI) {
            return null;
        }
        return "SELL";
    }

    private void openTradeX7(long j, String str, String str2, List<Candle> list) {
        if (!freshData(str) || strategyPaused("X7:REGIME_FADE") || entryBlocked(j, str)) {
            return;
        }
        if (!tradingAllowed(j)) {
            askOwnerToEnableTrading(j);
            return;
        }
        if (eventGateActive()) {
            return;
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'", new String[]{String.valueOf(j), str, "X7:REGIME_FADE"});
        boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) > 0;
        rawQuery.close();
        if (z) {
            return;
        }
        Candle candle = list.get(list.size() - 1);
        double atrAt = StrategyPack.atrAt(list, 14, list.size() - 1);
        if (atrAt <= 0.0d) {
            return;
        }
        double d = candle.c;
        double d2 = atrAt * 1.0d;
        if (d2 <= 0.0d || d <= 0.0d) {
            return;
        }
        double d3 = d2 * X7_TP_R;
        if (feeEdgeOk("X7:REGIME_FADE " + str, d, d3)) {
            double heatMaxPct = heatMaxPct();
            double bucketMaxPct = bucketMaxPct();
            if (heatMaxPct <= 0.0d || heatRiskPct(j) + riskPct() <= heatMaxPct) {
                if (bucketMaxPct > 0.0d && bucketRiskPct(j, bucketOf(str)) + riskPct() > bucketMaxPct) {
                    return;
                }
                boolean equals = "BUY".equals(str2);
                double slipEntry = slipEntry(d, str2);
                double balanceOf = balanceOf(j);
                if (balanceOf <= 0.0d) {
                    return;
                }
                double dynamicRiskPct = ((dynamicRiskPct("X7:REGIME_FADE") * balanceOf) / 100.0d) / d2;
                if (dynamicRiskPct * slipEntry > levCap() * balanceOf) {
                    dynamicRiskPct = (balanceOf * levCap()) / slipEntry;
                }
                double d4 = dynamicRiskPct;
                if (d4 <= 0.0d) {
                    return;
                }
                double d5 = equals ? slipEntry - d2 : slipEntry + d2;
                double d6 = equals ? slipEntry + d3 : slipEntry - d3;
                JSONObject jSONObject = new JSONObject();
                try {
                    jSONObject.put("x7", 1).put("atr", atrAt).put("tp_r", X7_TP_R).put("sl_atr", 1.0d).put("sigma", X7_SIGMA).put("be", 0).put("tf", "5m").put("note", "VWAP 3.5σ + RSI confluence + ADX regime gate");
                } catch (Throwable unused) {
                }
                this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), str, str2, Double.valueOf(d4), Double.valueOf(slipEntry), Double.valueOf(d5), Double.valueOf(d6), "X7:REGIME_FADE", Double.valueOf(0.7d), Long.valueOf(System.currentTimeMillis()), Double.valueOf(dynamicRiskPct("X7:REGIME_FADE") / 100.0d), Double.valueOf(d2 * d4), Double.valueOf(slipEntry), 0, Double.valueOf(mlWinProb(jSONObject)), jSONObject.toString()});
                recordOrder(0L, j, str, str2, "MARKET", slipEntry, d4, "PAPER", "FILLED");
                this.db.log("INFO", "X7", "ORDER_EXECUTED", str + " " + str2 + " [X7:REGIME_FADE] qty=" + String.format(Locale.US, "%.6f", Double.valueOf(d4)) + " entry=" + fpx(slipEntry) + " sl=" + fpx(d5) + " tp=" + fpx(d6) + " — VWAP σ-fade + RSI confluence, regime ADX<22 (TP +2.5R, NO BE)");
                try {
                    Notifier.post(appContext(), "X7 Regime Fade", str + " " + str2 + " — VWAP extreme + RSI confluence");
                } catch (Throwable unused2) {
                }
            }
        }
    }

    void aiTrainTick() {
        long j = 0L;
        long currentTimeMillis = System.currentTimeMillis();
        if (currentTimeMillis - this.lastAiTrainCheck < CONSEC_LOSS_COOLDOWN_MS) {
            return;
        }
        this.lastAiTrainCheck = currentTimeMillis;
        if ("1".equals(this.db.setting("ai_auto_train", "1"))) {
            try {
                j = Long.parseLong(this.db.setting("ai_trained_at", "0").trim());
            } catch (Throwable unused) {
                j = 0;
            }
            if (currentTimeMillis - j > 86400000) {
                trainAiAsync();
            }
        }
    }

    public void trainAiAsync() {
        if (this.aiTraining) {
            return;
        }
        this.aiTraining = true;
        Thread thread = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda1
            @Override // java.lang.Runnable
            public final void run() {
                EngineCore.this.lambda$trainAiAsync$0();
            }
        }, "ai-trainer");
        thread.setDaemon(true);
        thread.start();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$trainAiAsync$0() {
        try {
            trainAiBlocking();
        } catch (Throwable th) {
            try {
                this.db.log("ERROR", "AI", "TRAIN_FAIL", String.valueOf(th));
            } catch (Throwable unused) {
            }
        }
        this.aiTraining = false;
    }

    public JSONObject trainAiBlocking() {
        Throwable th = null;
        String str = null;
        int i = 0;
        LinkedHashMap linkedHashMap = null;
        int i2 = 0;
        long j = 0L;
        long j2 = 0L;
        long j3 = 0L;
        long j4 = 0L;
        ArrayList<String> arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE' ORDER BY priority DESC LIMIT 12", null);
        while (rawQuery.moveToNext()) {
            arrayList.add(rawQuery.getString(0));
        }
        rawQuery.close();
        if (arrayList.isEmpty()) {
            arrayList.addAll(BINANCE_PAIRS.keySet());
        }
        int length = StrategyPack.KEYS.length + 5;
        String[] strArr = new String[length];
        System.arraycopy(StrategyPack.KEYS, 0, strArr, 0, StrategyPack.KEYS.length);
        int i3 = 4;
        System.arraycopy(new String[]{"SHK1_SSM_BULL", "SHK2_SSM_BEAR", "SHK3_KZ_SWEEP", "SHK4_OB_RETEST", "SHK5_PD_EMA200"}, 0, strArr, StrategyPack.KEYS.length, 5);
        LinkedHashMap linkedHashMap2 = new LinkedHashMap();
        for (int i4 = 0; i4 < length; i4++) {
            linkedHashMap2.put(strArr[i4], new ArrayList());
        }
        double takerFee = takerFee();
        double slipBps = slipBps();
        int i5 = 0;
        long j5 = 0;
        long j6 = Long.MAX_VALUE;
        for (String str2 : arrayList) {
            try {
                List<Candle> deepKlines = deepKlines(str2, "5m", i3);
                try {
                    if (deepKlines.size() >= 400) {
                        str = "AI";
                        int i6 = i5;
                        long j7 = j5;
                        long j8 = j6;
                        linkedHashMap = linkedHashMap2;
                        try {
                            accumulate(linkedHashMap2, strArr, deepKlines, takerFee, slipBps);
                            j4 = j8;
                            try {
                                j6 = Math.min(j4, deepKlines.get(0).ts);
                                try {
                                    j3 = j7;
                                    try {
                                        j2 = Math.max(j3, deepKlines.get(deepKlines.size() - 1).ts);
                                        i2 = i6 + 1;
                                        j = j6;
                                    } catch (Throwable thz) {
                                        i5 = i6;
                                        j5 = j3;
                                        i = 4;
                                        this.db.log("WARN", str, "TRAIN_PAIR_FAIL", str2 + " — " + thz);
                                        linkedHashMap2 = linkedHashMap;
                                        i3 = i;
                                    }
                                } catch (Throwable th2) {
                                    th = th2;
                                    j3 = j7;
                                }
                            } catch (Throwable th3) {
                                th = th3;
                                j3 = j7;
                                i5 = i6;
                                j6 = j4;
                                j5 = j3;
                                i = 4;
                                this.db.log("WARN", str, "TRAIN_PAIR_FAIL", str2 + " — " + th);
                                linkedHashMap2 = linkedHashMap;
                                i3 = i;
                            }
                        } catch (Throwable th4) {
                            th = th4;
                            j3 = j7;
                            j4 = j8;
                        }
                    } else {
                        str = "AI";
                        linkedHashMap = linkedHashMap2;
                        i2 = i5;
                        j = j6;
                        j2 = j5;
                    }
                    try {
                        if (arrayList.indexOf(str2) < 6) {
                            try {
                                List<Candle> deepKlines2 = deepKlines(str2, "1d", 4);
                                if (deepKlines2.size() >= 260) {
                                    i = 4;
                                    try {
                                        accumulateDaily(linkedHashMap, strArr, deepKlines2, takerFee, slipBps);
                                    } catch (Throwable th5) {
                                        th = th5;
                                        i5 = i2;
                                        j5 = j2;
                                        j6 = j;
                                        this.db.log("WARN", str, "TRAIN_PAIR_FAIL", str2 + " — " + th);
                                        linkedHashMap2 = linkedHashMap;
                                        i3 = i;
                                    }
                                } else {
                                    i = 4;
                                }
                            } catch (Throwable th6) {
                                th = th6;
                                i = 4;
                            }
                        } else {
                            i = 4;
                        }
                        i5 = i2;
                        j5 = j2;
                        j6 = j;
                    } catch (Throwable th7) {
                        th = th7;
                        i = 4;
                    }
                } catch (Throwable th8) {
                    th = th8;
                    str = "AI";
                    linkedHashMap = linkedHashMap2;
                    i = 4;
                    j5 = j5;
                    this.db.log("WARN", str, "TRAIN_PAIR_FAIL", str2 + " — " + th);
                    linkedHashMap2 = linkedHashMap;
                    i3 = i;
                }
            } catch (Throwable th9) {
                th = th9;
                str = "AI";
                i = i3;
                linkedHashMap = linkedHashMap2;
            }
            linkedHashMap2 = linkedHashMap;
            i3 = i;
        }
        String str3 = "AI";
        LinkedHashMap linkedHashMap3 = linkedHashMap2;
        long j9 = j5;
        long j10 = j6;
        long currentTimeMillis = j10 == Long.MAX_VALUE ? System.currentTimeMillis() - 2592000000L : j10;
        long currentTimeMillis2 = j9 == 0 ? System.currentTimeMillis() : j9;
        long j11 = ((long) ((currentTimeMillis2 - currentTimeMillis) * 0.7d)) + currentTimeMillis;
        JSONObject jSONObject = new JSONObject();
        JSONObject jSONObject2 = new JSONObject();
        int i7 = 0;
        int i8 = 0;
        while (i7 < length) {
            String str4 = strArr[i7];
            String[] strArr2 = strArr;
            List<AiTrainer.T> list = (List<AiTrainer.T>) linkedHashMap3.get(str4);
            String str5 = str3;
            AiTrainer.Res res = new AiTrainer.Res();
            res.key = str4;
            double[] stats = AiTrainer.stats(list);
            long j12 = currentTimeMillis2;
            res.n = (int) stats[0];
            long j13 = currentTimeMillis;
            res.wr = stats[1];
            res.pf = stats[2];
            res.expR = stats[CONSEC_LOSS_DEFAULT];
            double[] oosStats = AiTrainer.oosStats(list, j11);
            res.nOos = (int) oosStats[0];
            long j14 = j11;
            res.oosWr = oosStats[1];
            res.oosPf = oosStats[2];
            res.weight = res.nOos > 0 ? AiTrainer.weightFrom(res.oosPf) : 1.0d;
            res.enabled = AiTrainer.enabledFrom(res.nOos, res.oosPf);
            if (res.enabled == 1) {
                i8++;
            }
            try {
                jSONObject.put(str4, AiTrainer.resJson(res));
                jSONObject2.put(str4, AiTrainer.resJson(res));
            } catch (Throwable unused) {
            }
            i7++;
            strArr = strArr2;
            str3 = str5;
            currentTimeMillis2 = j12;
            currentTimeMillis = j13;
            j11 = j14;
        }
        long j15 = currentTimeMillis2;
        long j16 = currentTimeMillis;
        String str6 = str3;
        long currentTimeMillis3 = System.currentTimeMillis();
        this.db.setSetting("ai_weights_v2", jSONObject.toString());
        this.db.setSetting("ai_trained_at", String.valueOf(currentTimeMillis3));
        invalidateAiWeights();
        JSONObject jSONObject3 = new JSONObject();
        try {
            jSONObject3.put("trained_at", currentTimeMillis3).put("pairs", i5).put("from", j16).put("to", j15).put("split_is_oos", "70/30").put("strategies", jSONObject2).put("on", i8).put("total", length).put("note", "Risk 1% flat (owner rule) — weights sirf enable/disable + priority. OOS PF<0.9 = auto-pause. 1d data Binance listing (BTC 2017) se — 2006-2016 crypto exchange data exist nahi karta.");
        } catch (Throwable unused2) {
        }
        this.db.setSetting("ai_train_report", jSONObject3.toString());
        this.db.log("INFO", str6, "TRAIN_DONE", i8 + "/" + length + " strategies ON — " + i5 + " pairs (15m depth + 1d HTF 2017→), fees+slip included, IS/OOS 70/30. AI ab proven configs par focus karega.");
        return jSONObject3;
    }

    private void accumulate(Map<String, List<AiTrainer.T>> map, String[] strArr, List<Candle> list, double d, double d2) {
        double[][] prevDayMap = AiTrainer.prevDayMap(list);
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        for (String str : strArr) {
            linkedHashMap.put(str, new TreeMap());
        }
        String[] strArr2 = {"SHK1_SSM_BULL", "SHK2_SSM_BEAR", "SHK3_KZ_SWEEP", "SHK4_OB_RETEST", "SHK5_PD_EMA200"};
        for (int i = 210; i < list.size() - 1; i++) {
            double[] adxAt = StrategyPack.adxAt(list, 14, i);
            for (StrategyPack.Signal signal : StrategyPack.evaluateAll(list, i, prevDayMap[i], null, adxAt == null ? -1.0d : adxAt[0])) {
                SortedMap sortedMap = (SortedMap) linkedHashMap.get(signal.strategy);
                if (sortedMap != null) {
                    sortedMap.put(Integer.valueOf(i), signal);
                }
            }
            for (int i2 = 0; i2 < 5; i2++) {
                String str2 = strArr2[i2];
                for (StrategyPack.Signal signal2 : AiTrainer.shaakuniSignals(list, i, str2)) {
                    SortedMap sortedMap2 = (SortedMap) linkedHashMap.get(str2);
                    if (sortedMap2 != null) {
                        sortedMap2.put(Integer.valueOf(i), signal2);
                    }
                }
            }
        }
        for (String str3 : strArr) {
            final SortedMap sortedMap3 = (SortedMap) linkedHashMap.get(str3);
            if (sortedMap3 != null && !sortedMap3.isEmpty()) {
                map.get(str3).addAll(AiTrainer.simulate(list, new AiTrainer.SigFn() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda3
                    @Override // com.aitradinglab.engine.AiTrainer.SigFn
                    public final List at(List list2, int i3) {
                        return EngineCore.lambda$accumulate$1(sortedMap3, list2, i3);
                    }
                }, d, d2));
            }
        }
    }

    static /* synthetic */ List lambda$accumulate$1(SortedMap sortedMap, List list, int i) {
        StrategyPack.Signal signal = (StrategyPack.Signal) sortedMap.get(Integer.valueOf(i));
        return signal == null ? Collections.emptyList() : Collections.singletonList(signal);
    }

    private void accumulateDaily(Map<String, List<AiTrainer.T>> map, String[] strArr, List<Candle> list, double d, double d2) {
        final double[][] prevDayMap = AiTrainer.prevDayMap(list);
        String[] strArr2 = {"S1_EMA_PULLBACK", "S3_SUPERTREND_ADX", "S5_PDH_PDL", "S8_DOW_PULLBACK", "S9_GANN_50"};
        for (int i = 0; i < 5; i++) {
            final String str = strArr2[i];
            map.get(str).addAll(AiTrainer.simulate(list, new AiTrainer.SigFn() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda6
                @Override // com.aitradinglab.engine.AiTrainer.SigFn
                public final List at(List list2, int i2) {
                    return EngineCore.lambda$accumulateDaily$2(prevDayMap, str, list2, i2);
                }
            }, d, d2));
        }
    }

    static /* synthetic */ List lambda$accumulateDaily$2(double[][] dArr, String str, List list, int i) {
        ArrayList arrayList = new ArrayList();
        if (i < dArr.length) {
            for (StrategyPack.Signal signal : (List<StrategyPack.Signal>) StrategyPack.evaluateAll(list, i, dArr[i], null, -1.0d)) {
                if (signal.strategy.equals(str)) {
                    arrayList.add(signal);
                }
            }
        }
        return arrayList;
    }

    void selfLearnTick() {
        long j = 0L;
        long currentTimeMillis = System.currentTimeMillis();
        try {
            j = Long.parseLong(this.db.setting("self_learn_at", "0").trim());
        } catch (Throwable unused) {
            j = 0;
        }
        if (j == 0) {
            this.db.setSetting("self_learn_at", String.valueOf(currentTimeMillis));
            return;
        }
        if (currentTimeMillis - j < 600000) {
            return;
        }
        this.db.setSetting("self_learn_at", String.valueOf(currentTimeMillis));
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND closed_at>?", new String[]{String.valueOf(j)});
        int i = rawQuery.moveToFirst() ? rawQuery.getInt(0) : 0;
        rawQuery.close();
        if (i < 25) {
            return;
        }
        reweightFromLive();
    }

    void reweightFromLive() {
        double d = 0.0d;
        try {
            JSONObject aiWeights = aiWeights();
            if (aiWeights == null) {
                return;
            }
            JSONObject jSONObject = new JSONObject(aiWeights.toString());
            int i = 0;
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT strategy, pnl, risk_amt FROM trades WHERE status='CLOSED' AND strategy LIKE 'PDF:%' AND closed_at>? ORDER BY id DESC LIMIT 500", new String[]{String.valueOf(System.currentTimeMillis() - 2592000000L)});
            HashMap hashMap = new HashMap();
            while (true) {
                d = 0.0d;
                if (!rawQuery.moveToNext()) {
                    break;
                }
                String string = rawQuery.getString(0);
                if (string != null && string.contains(":")) {
                    String substring = string.substring(string.indexOf(58) + 1);
                    double d2 = rawQuery.getDouble(2);
                    if (d2 > 0.0d) {
                        List list = (List) hashMap.get(substring);
                        if (list == null) {
                            list = new ArrayList();
                            hashMap.put(substring, list);
                        }
                        list.add(Double.valueOf(rawQuery.getDouble(1) / d2));
                    }
                }
            }
            rawQuery.close();
            if (hashMap.isEmpty()) {
                return;
            }
            int i2 = 0;
            for (Map.Entry entry : ((Map<Object, Object>) hashMap).entrySet()) {
                if (jSONObject.has((String) entry.getKey())) {
                    List list2 = (List) entry.getValue();
                    if (list2.size() >= 10) {
                        Iterator it = list2.iterator();
                        double d3 = d;
                        double d4 = d3;
                        while (it.hasNext()) {
                            int i3 = i2;
                            double doubleValue = ((Double) it.next()).doubleValue();
                            if (doubleValue > d) {
                                d4 += doubleValue;
                            } else {
                                d3 += -doubleValue;
                            }
                            i2 = i3;
                        }
                        int i4 = i2;
                        double d5 = d3 > d ? d4 / d3 : d4 > d ? 99 : i;
                        JSONObject jSONObject2 = jSONObject.getJSONObject((String) entry.getKey());
                        double round = Math.round(((jSONObject2.optDouble("w", 1.0d) * 0.6d) + (AiTrainer.weightFrom(d5) * 0.4d)) * 100.0d) / 100.0d;
                        int optInt = (list2.size() < 15 || d5 >= 0.7d) ? jSONObject2.optInt("on", 1) : 0;
                        jSONObject2.put("live_pf", Math.round(d5 * 100.0d) / 100.0d).put("live_n", list2.size()).put("w", round).put("on", optInt);
                        i2 = optInt == 0 ? i4 + 1 : i4;
                        i = 0;
                        d = 0.0d;
                    }
                }
            }
            this.db.setSetting("ai_weights_v2", jSONObject.toString());
            invalidateAiWeights();
            this.db.log("INFO", "AI", "SELF_LEARN", "25+ closed trades → re-weight: " + hashMap.size() + " PDF strategies live PF se blend (0.6 BT + 0.4 live), " + i2 + " auto-paused (live PF<0.7, n≥15).");
        } catch (Throwable th) {
            this.db.log("WARN", "AI", "SELF_LEARN_FAIL", String.valueOf(th));
        }
    }

    private boolean tradingAllowed(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT IFNULL(trade_ok, CASE WHEN role='ADMIN' THEN 1 ELSE 0 END) FROM users WHERE id=?", new String[]{String.valueOf(j)});
        boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) == 1;
        rawQuery.close();
        return z;
    }

    private void askOwnerToEnableTrading(long j) {
        String valueOf = String.valueOf(j);
        long currentTimeMillis = System.currentTimeMillis();
        Long l = this.tradeAskAt.get(valueOf);
        if (l == null || currentTimeMillis - l.longValue() >= 1800000) {
            this.tradeAskAt.put(valueOf, Long.valueOf(currentTimeMillis));
            String str = "user #" + j;
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name FROM users WHERE id=?", new String[]{valueOf});
            if (rawQuery.moveToFirst()) {
                str = rawQuery.getString(0);
            }
            rawQuery.close();
            this.db.log("INFO", "GUARD", "TRADE_BLOCKED_PENDING", str + " ke liye signal aya lekin TRADING disabled hai — owner Control > Users me ENABLE TRADING dabayen");
            try {
                this.db.getWritableDatabase().execSQL("INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('TRADE_REQUEST',?,?,?,0,?)", new Object[]{"Trading request — " + str, str + " trade karna chahta hai. Settings > Control > Users me ENABLE TRADING dabayen — tab engine us ke liye trades kholega.", new JSONObject().put("uid", j).put("name", str).toString(), Long.valueOf(currentTimeMillis)});
            } catch (Throwable unused) {
            }
            try {
                Notifier.post(appContext(), "TRADING request — " + str, "Control > Users me ENABLE TRADING dabayen, tab ye user trade kar sakega");
            } catch (Throwable unused2) {
            }
        }
    }

    /* JADX WARN: Unreachable blocks removed: 1, instructions: 1 */
    private void openTrade3C(long j, String str, Setup3C setup3C, double d, List<Candle> list, int i) {
        if (freshData(str) && !entryBlocked(j, str)) {
            if (!tradingAllowed(j)) {
                askOwnerToEnableTrading(j);
                return;
            }
            if (inCmeHalt()) {
                log3C(str, setup3C, "ENTRY_BLOCKED", "CME maintenance halt (17:00-18:00 ET) — session filter ON hai");
                return;
            }
            if (eventGateActive()) {
                log3C(str, setup3C, "ENTRY_BLOCKED", "HIGH-impact news <60 min — event gate ON hai (OPEC/CPI/FOMC gap protection)");
                return;
            }
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'", new String[]{String.valueOf(j), str});
            boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) > 0;
            rawQuery.close();
            if (z) {
                return;
            }
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy LIKE '3C%' AND opened_at>=?", new String[]{String.valueOf(j), str, String.valueOf(setup3C.c3Ts)});
            boolean z2 = rawQuery2.moveToFirst() && rawQuery2.getInt(0) > 0;
            rawQuery2.close();
            if (z2) {
                return;
            }
            int councilScore = councilScore(str, setup3C.side, list, Math.max(0, i));
            int councilMin = councilMin();
            if (councilMin > 0 && councilScore < councilMin) {
                log3C(str, setup3C, "COUNCIL_BLOCKED", "council " + councilScore + "% < min " + councilMin + "% — weak confluence, owner gate active");
                return;
            }
            double slipEntry = slipEntry(d, setup3C.side);
            boolean equals = "BUY".equals(setup3C.side);
            double d2 = setup3C.slPrice;
            double d3 = equals ? slipEntry - d2 : d2 - slipEntry;
            if (d3 <= 0.0d) {
                return;
            }
            double balanceOf = balanceOf(j);
            if (balanceOf <= 0.0d) {
                return;
            }
            double heatMaxPct = heatMaxPct();
            double bucketMaxPct = bucketMaxPct();
            if (heatMaxPct > 0.0d) {
                double heatRiskPct = heatRiskPct(j) + riskPct();
                if (heatRiskPct > heatMaxPct) {
                    this.db.log("INFO", "GUARD", "HEAT_CAP_BLOCKED", str + " — heat " + String.format(Locale.US, "%.1f", Double.valueOf(heatRiskPct)) + "% > cap " + String.format(Locale.US, "%.1f", Double.valueOf(heatMaxPct)) + "% (total open risk limit)");
                    return;
                }
            }
            if (bucketMaxPct > 0.0d) {
                double bucketRiskPct = bucketRiskPct(j, bucketOf(str)) + riskPct();
                if (bucketRiskPct > bucketMaxPct) {
                    this.db.log("INFO", "GUARD", "BUCKET_CAP_BLOCKED", str + " (" + bucketOf(str) + ") — bucket heat " + String.format(Locale.US, "%.1f", Double.valueOf(bucketRiskPct)) + "% > cap " + String.format(Locale.US, "%.1f", Double.valueOf(bucketMaxPct)) + "% (correlated exposure limit)");
                    return;
                }
            }
            double dynamicRiskPct = (dynamicRiskPct("3C_MASTER") * balanceOf) / 100.0d;
            double d4 = dynamicRiskPct / d3;
            if (d4 * slipEntry > levCap() * balanceOf) {
                d4 = (levCap() * balanceOf) / slipEntry;
            }
            double d5 = d4;
            if (d5 <= 0.0d) {
                return;
            }
            double d6 = "BUY".equals(setup3C.side) ? slipEntry + (d3 * threecTpR()) : slipEntry - (d3 * threecTpR());
            if (feeEdgeOk("3C_MASTER " + str, slipEntry, threecTpR() * d3)) {
                double abs = Math.abs(slipEntry - setup3C.slPrice) * d5;
                Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
                JSONObject jSONObject = new JSONObject();
                try {
                    jSONObject.put("bd", Math.round(setup3C.c3Body * 1000.0d) / 1000.0d).put("vr", Math.round(setup3C.c3VolRatio * 1000.0d) / 1000.0d).put("ap", Math.round(setup3C.c3AtrPct * 1000.0d) / 1000.0d).put("ed", Math.round(setup3C.c3EmaDist * 1000.0d) / 1000.0d).put("rd", Math.round(setup3C.c3RdPct * 1000.0d) / 1000.0d).put("hr", calendar.get(11)).put("cs", councilScore);
                } catch (Throwable unused) {
                }
                double mlWinProb = mlWinProb(jSONObject);
                this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), str, setup3C.side, Double.valueOf(d5), Double.valueOf(slipEntry), Double.valueOf(setup3C.slPrice), Double.valueOf(d6), "3C_MASTER", 0, Long.valueOf(System.currentTimeMillis()), Double.valueOf(dynamicRiskPct("3C_MASTER") / 100.0d), Double.valueOf(abs), Double.valueOf(d), Integer.valueOf(councilScore), Double.valueOf(mlWinProb), jSONObject.toString()});
                Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
                long j2 = rawQuery3.moveToFirst() ? rawQuery3.getLong(0) : 0L;
                rawQuery3.close();
                recordOrder(j2, j, str, setup3C.side, "STOP", d, d5, "PAPER", "FILLED");
                bridgeOrder(str, setup3C.side, j2, j, slipEntry, d5);
                this.db.log("INFO", "3C", "ORDER_EXECUTED", str + " " + setup3C.side + " qty=" + String.format(Locale.US, "%.6f", Double.valueOf(d5)) + " entry=" + fpx(slipEntry) + " (decision " + fpx(d) + ", slip " + String.format(Locale.US, "%.1f", Double.valueOf(slipBps())) + "bps) SL=" + fpx(setup3C.slPrice) + " TP=" + fpx(d6) + " (3R) risk=$" + String.format(Locale.US, "%.2f", Double.valueOf(dynamicRiskPct)) + " (" + riskPct() + "% of $" + String.format(Locale.US, "%.2f", Double.valueOf(balanceOf)) + ") | council " + councilScore + "%, ML winProb " + String.format(Locale.US, "%.0f%%", Double.valueOf(mlWinProb * 100.0d)));
            }
        }
    }

    private double balanceOf(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?", new String[]{String.valueOf(j)});
        double d = rawQuery.moveToFirst() ? rawQuery.getDouble(0) : 0.0d;
        rawQuery.close();
        return d;
    }

    private static String fpx(double d) {
        return String.format(Locale.US, d >= 100.0d ? "%.3f" : "%.6f", Double.valueOf(d));
    }

    private static String pct(double d) {
        return String.format(Locale.US, "%.1f", Double.valueOf(d * 100.0d));
    }

    private void tryCustomStrategies(long j, String str, List<Candle> list) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name, spec, status FROM strategies WHERE status IN ('PAPER','ACTIVE') AND deleted_at=0", null);
        ArrayList<Object[]> arrayList = new ArrayList();
        while (rawQuery.moveToNext()) {
            arrayList.add(new Object[]{rawQuery.getString(0), rawQuery.getString(1), rawQuery.getString(2)});
        }
        rawQuery.close();
        for (Object[] objArr : arrayList) {
            String str2 = (String) objArr[0];
            String str3 = (String) objArr[1];
            String str4 = (String) objArr[2];
            try {
                JSONObject jSONObject = new JSONObject(str3);
                int evaluateSpec = StrategyLab.evaluateSpec(jSONObject.optJSONArray("conditions"), "ANY".equals(jSONObject.optString("logic")) ? 1 : 0, list);
                if (evaluateSpec != 0) {
                    String optString = jSONObject.optString("side", "BOTH");
                    if (!"BUY".equals(optString) || evaluateSpec >= 0) {
                        if (!"SELL".equals(optString) || evaluateSpec <= 0) {
                            openTradeLab(j, str, evaluateSpec > 0 ? "BUY" : "SELL", list, ("ACTIVE".equals(str4) ? "AI:LIVE:" : "AI:PAPER:") + str2);
                        }
                    }
                }
            } catch (Throwable th) {
                this.db.log("ERROR", "LAB", "CUSTOM_EVAL_FAIL", str2 + " — " + th);
            }
        }
    }

    private void openTradeLab(long j, String str, String str2, List<Candle> list, String str3) {
        if (freshData(str)) {
            if (strategyPaused(str3)) {
                this.db.log("INFO", "GUARD", "STRATEGY_PAUSE_BLOCK", str3 + " degraded-paused — entry blocked (Control me re-enable karein)");
                return;
            }
            if (entryBlocked(j, str)) {
                return;
            }
            if (!tradingAllowed(j)) {
                askOwnerToEnableTrading(j);
                return;
            }
            if (inCmeHalt() || eventGateActive()) {
                return;
            }
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'", new String[]{String.valueOf(j), str});
            boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) > 0;
            rawQuery.close();
            if (z) {
                return;
            }
            double d = list.get(list.size() - 1).c;
            int councilScore = councilScore(str, str2, list, list.size() - 1);
            int councilMin = councilMin();
            if (councilMin <= 0 || councilScore >= councilMin) {
                double heatMaxPct = heatMaxPct();
                double bucketMaxPct = bucketMaxPct();
                if (heatMaxPct <= 0.0d || heatRiskPct(j) + 1.0d <= heatMaxPct) {
                    if (bucketMaxPct > 0.0d && bucketRiskPct(j, bucketOf(str)) + 1.0d > bucketMaxPct) {
                        return;
                    }
                    double atr = atr(list, 14);
                    if (Double.isNaN(atr) || atr <= 0.0d) {
                        return;
                    }
                    double slipEntry = slipEntry(d, str2);
                    double d2 = "BUY".equals(str2) ? slipEntry - (atr * 1.5d) : slipEntry + (atr * 1.5d);
                    boolean equals = "BUY".equals(str2);
                    double d3 = atr * X7_TP_R;
                    double d4 = equals ? slipEntry + d3 : slipEntry - d3;
                    if (feeEdgeOk(str3 + " " + str, slipEntry, atr * X7_TP_R)) {
                        double balanceOf = balanceOf(j);
                        if (balanceOf <= 0.0d) {
                            return;
                        }
                        double dynamicRiskPct = ((dynamicRiskPct(str3) * balanceOf) / 100.0d) / (1.5d * atr);
                        if (dynamicRiskPct * slipEntry > levCap() * balanceOf) {
                            dynamicRiskPct = (balanceOf * levCap()) / slipEntry;
                        }
                        double d5 = dynamicRiskPct;
                        if (d5 <= 0.0d) {
                            return;
                        }
                        double abs = Math.abs(slipEntry - d2) * d5;
                        Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
                        JSONObject jSONObject = new JSONObject();
                        try {
                            jSONObject.put("bd", Math.round(bodyPct(list.get(list.size() - 1)) * 1000.0d) / 1000.0d).put("ap", Math.round((atr / slipEntry) * 100000.0d) / 1000.0d).put("rd", Math.round((Math.abs(slipEntry - d2) / slipEntry) * 100000.0d) / 1000.0d).put("hr", calendar.get(11)).put("cs", councilScore);
                        } catch (Throwable unused) {
                        }
                        this.db.getWritableDatabase().execSQL("INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), str, str2, Double.valueOf(d5), Double.valueOf(slipEntry), Double.valueOf(d2), Double.valueOf(d4), str3, Double.valueOf(0.65d), Long.valueOf(System.currentTimeMillis()), Double.valueOf(dynamicRiskPct(str3) / 100.0d), Double.valueOf(abs), Double.valueOf(d), Integer.valueOf(councilScore), Double.valueOf(mlWinProb(jSONObject)), jSONObject.toString()});
                        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
                        long j2 = rawQuery2.moveToFirst() ? rawQuery2.getLong(0) : 0L;
                        rawQuery2.close();
                        recordOrder(j2, j, str, str2, "MARKET", d, d5, "PAPER", "FILLED");
                        bridgeOrder(str, str2, j2, j, slipEntry, d5);
                        this.db.log("INFO", "LAB", "ORDER_EXECUTED", str + " " + str2 + " [" + str3 + "] qty=" + String.format(Locale.US, "%.6f", Double.valueOf(d5)) + " entry=" + fpx(slipEntry) + " (Lab strategy signal — ATR SL/TP, 1% risk, council " + councilScore + "%)");
                    }
                }
            }
        }
    }

    /* JADX WARN: Code restructure failed: missing block: B:207:0x0225, code lost:
    
        if (r53 > r45) goto L73;
     */
    /* JADX WARN: Code restructure failed: missing block: B:95:0x0584, code lost:
    
        r0 = r40;
     */
    /* JADX WARN: Removed duplicated region for block: B:40:0x04b1  */
    /* JADX WARN: Removed duplicated region for block: B:44:0x04db  */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    // v1.3 REWRITE — purana manageOpenTrades decompiled-flow ka soup tha jis mein non-PB trades
    // galti se managePbTrade (PB-only trailing manager) mein jaate the: features.atr missing → instant
    // return → SL/TP KABHI check nahi hota tha → trades kabhi close nahi hoti → PnL hamesha 0 (owner
    // ka "profit 0 se upar nahi" bug). Naya clean nizam:
    //   PB:*            → managePbTrade (SL + ATR trail)
    //   PDF:*           → boundary invalidation + window expiry + fixed SL/TP + BE
    //   3C / MIN25 / X7 / Lab → fixed SL/TP (SL priority) + MFE/MAE journal + breakeven (non-3C)
    private void manageOpenTrades() {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, user_id, symbol, side, qty, entry, sl, tp, strategy, features FROM trades WHERE status='OPEN'", null);
        ArrayList<Object[]> openTrades = new ArrayList<>();
        while (rawQuery.moveToNext()) {
            openTrades.add(new Object[]{Long.valueOf(rawQuery.getLong(0)), Long.valueOf(rawQuery.getLong(1)), rawQuery.getString(2), rawQuery.getString(3), Double.valueOf(rawQuery.getDouble(4)), Double.valueOf(rawQuery.getDouble(5)), Double.valueOf(rawQuery.getDouble(6)), Double.valueOf(rawQuery.getDouble(7)), rawQuery.getString(8), rawQuery.getString(9)});
        }
        rawQuery.close();
        long now = System.currentTimeMillis();
        long splitTs = now - TF_MS_PUB;
        for (int ti = 0; ti < openTrades.size(); ti++) {
            Object[] t = openTrades.get(ti);
            long id = ((Long) t[0]).longValue();
            long uid = ((Long) t[1]).longValue();
            String sym = (String) t[2];
            String side = (String) t[3];
            double qty = ((Double) t[4]).doubleValue();
            double entry = ((Double) t[5]).doubleValue();
            double sl = ((Double) t[6]).doubleValue();
            double tp = ((Double) t[7]).doubleValue();
            String strat = (String) t[8];
            String featStr = (String) t[9];
            try {
                if (!freshData(sym)) {
                    continue;
                }
                boolean buy = "BUY".equals(side);
                boolean isPB = strat != null && strat.startsWith("PB:");
                boolean isPDF = strat != null && strat.startsWith("PDF:");
                boolean is3C = strat != null && strat.startsWith("3C");
                if (isPB) {
                    // PB playbook trades → ATR trailing manager (SL jab tak trail arm na ho, phir trail exit)
                    managePbTrade(id, uid, sym, side, qty, entry, sl, buy);
                    continue;
                }
                // v1.4 LIVE TICK: SL/TP 1s price par bhi check — candle close ka wait nahi (real exchange jaisa)
                double[] liveTick = this.livePx.get(sym);
                if (liveTick != null && liveTick[0] > 0.0d && System.currentTimeMillis() - ((long) liveTick[1]) < 5000L) {
                    double pxNow = liveTick[0];
                    if (buy ? pxNow <= sl : pxNow >= sl) {
                        closeTrade(id, uid, sl, "SL", qty, entry, side);
                        continue;
                    }
                    if (buy ? pxNow >= tp : pxNow <= tp) {
                        closeTrade(id, uid, tp, "TP", qty, entry, side);
                        continue;
                    }
                }
                // candles: [0] = last CLOSED, [1] = in-progress (live h/l — har loop pass update)
                double[][] candles = new double[2][];
                Cursor c1 = this.db.getReadableDatabase().rawQuery("SELECT h, l, c FROM candles WHERE symbol=? AND tf=? AND ts<=? ORDER BY ts DESC LIMIT 1", new String[]{sym, "5m", String.valueOf(splitTs)});
                if (c1.moveToFirst()) {
                    candles[0] = new double[]{c1.getDouble(0), c1.getDouble(1), c1.getDouble(2)};
                }
                c1.close();
                Cursor c2 = this.db.getReadableDatabase().rawQuery("SELECT h, l, c FROM candles WHERE symbol=? AND tf=? AND ts>? ORDER BY ts DESC LIMIT 1", new String[]{sym, "5m", String.valueOf(splitTs)});
                if (c2.moveToFirst()) {
                    candles[1] = new double[]{c2.getDouble(0), c2.getDouble(1), c2.getDouble(2)};
                }
                c2.close();
                // PDF extras: boundary invalidation (candle CLOSE beyond protected boundary) + window expiry
                if (isPDF && featStr != null) {
                    boolean pdfClosed = false;
                    try {
                        JSONObject f = new JSONObject(featStr);
                        double boundary = f.optDouble("boundary", 0.0d);
                        long sigTs = f.optLong("sig_ts", 0L);
                        int windowBars = f.optInt("window_bars", 5);
                        if (candles[0] != null && boundary > 0.0d) {
                            boolean closedBeyond = buy ? candles[0][2] < boundary : candles[0][2] > boundary;
                            if (closedBeyond) {
                                closeTrade(id, uid, livePrice(sym), "BOUNDARY", qty, entry, side);
                                pdfClosed = true;
                            }
                        }
                        if (!pdfClosed && sigTs > 0L && now - sigTs > (windowBars + 2) * TF_MS_PUB) {
                            closeTrade(id, uid, livePrice(sym), "WINDOW", qty, entry, side);
                            pdfClosed = true;
                        }
                    } catch (Throwable tt) {
                    }
                    if (pdfClosed) {
                        continue;
                    }
                }
                // fixed SL/TP — SL conservative priority (same-candle ambiguity par SL maano)
                double beAbs = Math.abs(tp - entry) / 3.0d;
                boolean beDone = Math.abs(sl - entry) <= Math.abs(entry) * 1e-9d;
                for (int ci = 0; ci < 2; ci++) {
                    double[] cd = candles[ci];
                    if (cd == null) {
                        continue;
                    }
                    double hi = cd[0];
                    double lo = cd[1];
                    try {
                        this.db.getWritableDatabase().execSQL("UPDATE trades SET mfe=MAX(IFNULL(mfe,0),?), mae=MAX(IFNULL(mae,0),?) WHERE id=?", new Object[]{Double.valueOf(Math.max(0.0d, (buy ? hi - entry : entry - lo) * qty)), Double.valueOf(Math.max(0.0d, (buy ? entry - lo : hi - entry) * qty)), Long.valueOf(id)});
                    } catch (Throwable tt) {
                    }
                    boolean slHit = buy ? lo <= sl : hi >= sl;
                    boolean tpHit = buy ? hi >= tp : lo <= tp;
                    if (slHit) {
                        closeTrade(id, uid, sl, "SL", qty, entry, side);
                        break;
                    }
                    if (tpHit) {
                        closeTrade(id, uid, tp, "TP", qty, entry, side);
                        break;
                    }
                    // breakeven: +|tp-entry|/3 move par SL entry par shift (non-3C, non-PDF) — ek dafa
                    if (!is3C && !isPDF && !beDone && beAbs > 0.0d) {
                        boolean beHit = buy ? hi >= entry + beAbs : lo <= entry - beAbs;
                        if (beHit) {
                            this.db.getWritableDatabase().execSQL("UPDATE trades SET sl=? WHERE id=?", new Object[]{Double.valueOf(entry), Long.valueOf(id)});
                            this.db.log("INFO", "EXECUTOR", "TRADE_MANAGED", "trade #" + id + " " + sym + " — +" + fpx(beAbs) + " favorable move — SL moved to breakeven " + fpx(entry));
                            beDone = true;
                        }
                    }
                }
            } catch (Throwable tt) {
                this.db.log("WARN", "EXECUTOR", "MANAGE_FAIL", "trade #" + id + ": " + String.valueOf(tt));
            }
        }
    }
    private void closeTrade(long j, long j2, double d, String str, double d2, double d3, String str2) {
        String str3 = null;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        String tradeSymbol = null;
        long j3 = 0L;
        double slipExit = slipExit(d, str2);
        double takerFee = ((d2 * d3) + (d2 * slipExit)) * takerFee();
        double d7 = (("BUY".equals(str2) ? slipExit - d3 : d3 - slipExit) * d2) - takerFee;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT risk_amt, decision, features FROM trades WHERE id=?", new String[]{String.valueOf(j)});
        if (rawQuery.moveToFirst()) {
            d4 = rawQuery.getDouble(0);
            d5 = rawQuery.getDouble(1);
            str3 = rawQuery.getString(2);
        } else {
            str3 = "{}";
            d4 = 0.0d;
            d5 = 0.0d;
        }
        rawQuery.close();
        boolean equals = "BUY".equals(str2);
        double d8 = d4 > 0.0d ? d7 / d4 : 0.0d;
        if (d5 > 0.0d) {
            d6 = ((equals ? slipExit - d5 : d5 - slipExit) / d5) * 10000.0d;
        } else {
            d6 = 0.0d;
        }
        String str4 = str3;
        this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=?, pnl=?, status='CLOSED', closed_at=?, r_mult=?, tca_bps=? WHERE id=?", new Object[]{Double.valueOf(slipExit), Double.valueOf(d7), Long.valueOf(System.currentTimeMillis()), Double.valueOf(Math.round(d8 * 1000.0d) / 1000.0d), Double.valueOf(Math.round(d6 * 100.0d) / 100.0d), Long.valueOf(j)});
        this.db.getWritableDatabase().execSQL("UPDATE accounts SET balance = balance + ? WHERE user_id=?", new Object[]{Double.valueOf(d7), Long.valueOf(j2)});
        recordOrder(j, j2, "", "EXIT_" + str, "MARKET", slipExit, d2, "PAPER", "FILLED");
        bridgeClose("", j, j2);
        this.db.log(str.equals("SL") ? "WARN" : "INFO", "EXECUTOR", "TRADE_CLOSED_" + str, "trade #" + j + " exit=" + fpx(slipExit) + " (level " + fpx(d) + ", slip " + String.format(Locale.US, "%.1f", Double.valueOf(slipBps())) + "bps) pnl=" + String.format("%.2f", Double.valueOf(d7)) + " = " + String.format(Locale.US, "%.2f", Double.valueOf(d8)) + "R, fees $" + String.format("%.4f", Double.valueOf(takerFee)) + " @ " + pct(takerFee()) + "%/side, TCA " + String.format(Locale.US, "%.1f", Double.valueOf(d6)) + "bps");
        if (str4 != null) {
            try {
                if (!"{}".equals(str4)) {
                    long parseLong = Long.parseLong(this.db.setting("ml_n", "0")) + 1;
                    this.db.setSetting("ml_n", String.valueOf(parseLong));
                    if (parseLong % 20 == 0) {
                        mlTrain();
                    }
                }
            } catch (Throwable unused) {
            }
        }
        if (!"SL".equals(str) || d7 >= 0.0d || (tradeSymbol = tradeSymbol(j)) == null) {
            return;
        }
        int cooldownMin = cooldownMin();
        if (cooldownMin > 0) {
            j3 = j2;
            this.cooldownUntil.put(j3 + ":" + tradeSymbol, Long.valueOf(System.currentTimeMillis() + (cooldownMin * 60000)));
            this.cooldownLogged.remove(j3 + ":" + tradeSymbol);
            saveGuardState();
            this.db.log("WARN", "GUARD", "COOLDOWN_SET", tradeSymbol + " — SL loss ke baad " + cooldownMin + " min tak naya entry band (freqtrade CooldownPeriod)");
        } else {
            j3 = j2;
        }
        checkConsecutiveLoss(j3, tradeSymbol);
    }

    private String tradeSymbol(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol FROM trades WHERE id=?", new String[]{String.valueOf(j)});
        String string = rawQuery.moveToFirst() ? rawQuery.getString(0) : null;
        rawQuery.close();
        return string;
    }

    private void checkConsecutiveLoss(long j, String str) {
        int consecLossN = consecLossN();
        if (consecLossN <= 0) {
            return;
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT pnl FROM trades WHERE user_id=? AND symbol=? AND status='CLOSED' ORDER BY closed_at DESC LIMIT ?", new String[]{String.valueOf(j), str, String.valueOf(consecLossN)});
        boolean moveToFirst = rawQuery.moveToFirst();
        int i = 0;
        while (moveToFirst && i < consecLossN && rawQuery.getDouble(0) < 0.0d) {
            i++;
            if (!rawQuery.moveToNext()) {
                break;
            }
        }
        rawQuery.close();
        if (i >= consecLossN) {
            long currentTimeMillis = System.currentTimeMillis() + CONSEC_LOSS_COOLDOWN_MS;
            String str2 = j + ":" + str;
            if (currentTimeMillis > this.cooldownUntil.getOrDefault(str2, 0L).longValue()) {
                this.cooldownUntil.put(str2, Long.valueOf(currentTimeMillis));
            }
            this.cooldownLogged.remove(str2);
            this.db.log("WARN", "GUARD", "CONSEC_LOSS_PAUSE", str + " — " + consecLossN + " lagatar SL losses: 1 ghanta trading pause (freqtrade StoplossGuard)");
        }
    }

    private boolean entryBlocked(long j, String str) {
        long currentTimeMillis = System.currentTimeMillis();
        String str2 = j + ":" + str;
        Long l = this.cooldownUntil.get(str2);
        if (l != null && l.longValue() > currentTimeMillis) {
            if (this.cooldownLogged.add(str2)) {
                this.db.log("INFO", "GUARD", "ENTRY_COOLDOWN_BLOCKED", str + " — cooldown active, " + (((l.longValue() - currentTimeMillis) / 60000) + 1) + " min baakI (loss ke baad thanda waqt)");
            }
            return true;
        }
        if (l != null && l.longValue() <= currentTimeMillis) {
            this.cooldownUntil.remove(str2);
        }
        double dailyKillPct = dailyKillPct();
        if (dailyKillPct <= 0.0d) {
            return false;
        }
        long j2 = (currentTimeMillis / 86400000) * 86400000;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT IFNULL(SUM(pnl),0) FROM trades WHERE user_id=? AND status='CLOSED' AND closed_at>=?", new String[]{String.valueOf(j), String.valueOf(j2)});
        double d = rawQuery.moveToFirst() ? rawQuery.getDouble(0) : 0.0d;
        rawQuery.close();
        double balanceOf = balanceOf(j) - d;
        if (balanceOf <= 0.0d || d > ((-balanceOf) * dailyKillPct) / 100.0d) {
            return false;
        }
        if (!this.killLogged.add(j + ":" + (j2 / 86400000))) {
            return true;
        }
        this.db.log("WARN", "GUARD", "DAILY_KILL_SWITCH", "Aaj ka P/L $" + String.format("%.2f", Double.valueOf(d)) + " — daily -" + pct(dailyKillPct / 100.0d) + "% guard trigger: aaj ke naye entries band, kal UTC reset");
        Notifier.post(appContext(), "PRO GUARD", "Daily loss limit hit — aaj ke naye entries band (open trades ka SL/TP chal raha hai)");
        return true;
    }

    private void closeAll(long j, String str) {
        char c = '\u0000';
        char c2 = '\u0000';
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, qty, entry, side FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        ArrayList<Object[]> arrayList = new ArrayList();
        while (true) {
            c = 3;
            c2 = 2;
            if (!rawQuery.moveToNext()) {
                break;
            } else {
                arrayList.add(new Object[]{Long.valueOf(rawQuery.getLong(0)), Double.valueOf(rawQuery.getDouble(1)), Double.valueOf(rawQuery.getDouble(2)), rawQuery.getString(CONSEC_LOSS_DEFAULT)});
            }
        }
        rawQuery.close();
        for (Object[] objArr : arrayList) {
            closeTrade(((Long) objArr[0]).longValue(), j, ((Double) objArr[c2]).doubleValue(), str, ((Double) objArr[1]).doubleValue(), ((Double) objArr[c2]).doubleValue(), (String) objArr[c]);
            c = c;
            c2 = c2;
        }
    }

    private List<Long> userIds() {
        ArrayList arrayList = new ArrayList();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE active=1", null);
        while (rawQuery.moveToNext()) {
            arrayList.add(Long.valueOf(rawQuery.getLong(0)));
        }
        rawQuery.close();
        return arrayList;
    }

    private void snapshotEquity() {
        char c = '\u0000';
        char c2 = '\u0000';
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT AVG(balance) FROM accounts", null);
        int i = 0;
        double d = rawQuery.moveToFirst() ? rawQuery.getDouble(0) : 100.0d;
        rawQuery.close();
        this.db.getWritableDatabase().execSQL("INSERT OR REPLACE INTO equity(ts, value) VALUES(?,?)", new Object[]{Long.valueOf(System.currentTimeMillis()), Double.valueOf(d)});
        try {
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT a.user_id, a.balance, a.peak FROM accounts a", null);
            ArrayList<Object[]> arrayList = new ArrayList();
            while (true) {
                c = 2;
                if (!rawQuery2.moveToNext()) {
                    break;
                } else {
                    arrayList.add(new Object[]{Long.valueOf(rawQuery2.getLong(0)), Double.valueOf(rawQuery2.getDouble(1)), Double.valueOf(rawQuery2.getDouble(2))});
                }
            }
            rawQuery2.close();
            for (Object[] objArr : arrayList) {
                long longValue = ((Long) objArr[i]).longValue();
                double doubleValue = ((Double) objArr[1]).doubleValue();
                double doubleValue2 = ((Double) objArr[c]).doubleValue();
                SQLiteDatabase readableDatabase = this.db.getReadableDatabase();
                String[] strArr = new String[1];
                strArr[i] = String.valueOf(longValue);
                Cursor rawQuery3 = readableDatabase.rawQuery("SELECT symbol, side, qty, entry FROM trades WHERE user_id=? AND status='OPEN'", strArr);
                double d2 = 0.0d;
                while (rawQuery3.moveToNext()) {
                    double livePrice = livePrice(rawQuery3.getString(i));
                    if (Double.isNaN(livePrice)) {
                        c2 = c;
                    } else {
                        c2 = 2;
                        d2 += ("BUY".equals(rawQuery3.getString(1)) ? livePrice - rawQuery3.getDouble(CONSEC_LOSS_DEFAULT) : rawQuery3.getDouble(CONSEC_LOSS_DEFAULT) - livePrice) * rawQuery3.getDouble(2);
                    }
                    c = c2;
                    i = 0;
                }
                char c3 = c;
                rawQuery3.close();
                double d3 = doubleValue + d2;
                if (d3 > doubleValue2) {
                    this.db.getWritableDatabase().execSQL("UPDATE accounts SET peak=? WHERE user_id=?", new Object[]{Double.valueOf(d3), Long.valueOf(longValue)});
                }
                c = c3;
                i = 0;
            }
        } catch (Throwable unused) {
        }
        try {
            this.db.getWritableDatabase().execSQL("DELETE FROM equity WHERE ts NOT IN (SELECT ts FROM equity ORDER BY ts DESC LIMIT 2000)");
        } catch (Throwable unused2) {
        }
    }

    private void seedStaticInstruments() {
        SQLiteDatabase writableDatabase = this.db.getWritableDatabase();
        long currentTimeMillis = System.currentTimeMillis();
        for (String[] strArr : BINANCE_UNIVERSE) {
            String str = strArr[0];
            writableDatabase.execSQL("INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?, 'USDT','BINANCE',?,'ACTIVE',5000,?,?)", new Object[]{str, str, strArr[1], Long.valueOf(currentTimeMillis), strArr[2]});
        }
        StringBuilder sb = new StringBuilder();
        for (String[] strArr2 : BINANCE_UNIVERSE) {
            if (sb.length() > 0) {
                sb.append(',');
            }
            sb.append('\'').append(strArr2[0]).append('\'');
        }
        writableDatabase.execSQL("UPDATE instruments SET status='ACTIVE', exchange='BINANCE' WHERE symbol IN (" + ((Object) sb) + ")");
        try {
            writableDatabase.execSQL("UPDATE instruments SET status='RETIRED' WHERE exchange IS NOT NULL AND exchange<>'BINANCE'");
        } catch (Throwable unused) {
        }
        for (String[] strArr3 : BINANCE_UNIVERSE) {
            synchronized (this.binanceOkCache) {
                this.binanceOkCache.add(strArr3[0]);
            }
            Map<String, String> map = BUCKET;
            synchronized (map) {
                map.put(strArr3[0], strArr3[1]);
            }
        }
        if ("1".equals(this.db.setting("seeded_v44", "0"))) {
            return;
        }
        this.db.setSetting("seeded_v44", "1");
        this.db.log("INFO", "DISCOVERY", "BINANCE_SEED", "v4.4 ALL-BINANCE universe: seed 7 pairs + exchangeInfo se SAARE USDT spot pairs (volume-ranked MAJOR/RETAIL/ALTCOIN). Owner: 'saare binance ke coins daalo, baki sab delete'.");
    }

    private void syncBinanceUniverse() {
        char c = '\u0000';
        try {
            String httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/exchangeInfo", 15000);
            String httpGetUrl2 = httpGetUrl("https://api.binance.com/api/v3/ticker/24hr", 20000);
            if (httpGetUrl != null && httpGetUrl2 != null) {
                HashSet hashSet = new HashSet();
                JSONArray jSONArray = new JSONObject(httpGetUrl).getJSONArray("symbols");
                char c2 = 0;
                for (int i = 0; i < jSONArray.length(); i++) {
                    JSONObject jSONObject = jSONArray.getJSONObject(i);
                    if ("TRADING".equals(jSONObject.optString("status")) && "USDT".equals(jSONObject.optString("quoteAsset")) && jSONObject.optBoolean("isSpotTradingAllowed", true)) {
                        String upperCase = jSONObject.optString("baseAsset", "").toUpperCase(Locale.ROOT);
                        if (!upperCase.endsWith("UP") && !upperCase.endsWith("DOWN") && !upperCase.endsWith("BULL") && !upperCase.endsWith("BEAR") && !STABLE_BASES.contains(upperCase)) {
                            hashSet.add(jSONObject.optString("symbol"));
                        }
                    }
                }
                if (hashSet.isEmpty()) {
                    return;
                }
                JSONArray jSONArray2 = new JSONArray(httpGetUrl2);
                ArrayList<Object[]> arrayList = new ArrayList();
                for (int i2 = 0; i2 < jSONArray2.length(); i2++) {
                    JSONObject jSONObject2 = jSONArray2.getJSONObject(i2);
                    String optString = jSONObject2.optString("symbol");
                    if (hashSet.contains(optString)) {
                        arrayList.add(new Object[]{optString, Double.valueOf(jSONObject2.optDouble("quoteVolume", 0.0d))});
                    }
                }
                arrayList.sort(new Comparator() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda0
                    @Override // java.util.Comparator
                    public final int compare(Object obj, Object obj2) {
                        int compare = 0;
                        compare = Double.compare(((Double) ((Object[]) obj2)[1]).doubleValue(), ((Double) ((Object[]) obj)[1]).doubleValue());
                        return compare;
                    }
                });
                SQLiteDatabase writableDatabase = this.db.getWritableDatabase();
                long currentTimeMillis = System.currentTimeMillis();
                synchronized (this.binanceOkCache) {
                    this.binanceOkCache.clear();
                }
                int i3 = 0;
                int i4 = 0;
                for (Object[] objArr : arrayList) {
                    i3++;
                    String str = (String) objArr[c2];
                    double doubleValue = ((Double) objArr[1]).doubleValue();
                    String bucketForRank = bucketForRank(i3);
                    long j = currentTimeMillis;
                    int min = (int) Math.min(2.0E9d, Math.max(0.0d, Math.log10(Math.max(doubleValue, 1.0d)) * 1000.0d));
                    String str2 = str.replace("USDT", "") + "/USDT — Binance spot (rank " + i3 + ", " + bucketForRank + ")";
                    synchronized (this.binanceOkCache) {
                        this.binanceOkCache.add(str);
                    }
                    Map<String, String> map = BUCKET;
                    synchronized (map) {
                        map.put(str, bucketForRank);
                    }
                    try {
                        try {
                            writableDatabase.execSQL("INSERT INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,'USDT','BINANCE','CRYPTO','ACTIVE',?,?,?) ON CONFLICT(symbol) DO UPDATE SET status='ACTIVE', exchange='BINANCE', priority=?, note=?", new Object[]{str, str.replace("USDT", ""), Integer.valueOf(min), Long.valueOf(j), str2, Integer.valueOf(min), str2});
                            i4++;
                        } catch (Throwable unused) {
                        }
                        c = 0;
                    } catch (Throwable unused2) {
                        ContentValues contentValues = new ContentValues();
                        contentValues.put("status", "ACTIVE");
                        contentValues.put("exchange", "BINANCE");
                        contentValues.put("priority", Integer.valueOf(min));
                        contentValues.put("note", str2);
                        String[] strArr = new String[1];
                        c = 0;
                        try {
                            strArr[0] = str;
                            if (writableDatabase.update("instruments", contentValues, "symbol=?", strArr) == 0) {
                                writableDatabase.execSQL("INSERT INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,'USDT','BINANCE','CRYPTO','ACTIVE',?,?,?)", new Object[]{str, str.replace("USDT", ""), Integer.valueOf(min), Long.valueOf(j), str2});
                            }
                            i4++;
                        } catch (Throwable unused3) {
                        }
                    }
                    c2 = c;
                    currentTimeMillis = j;
                }
                long j2 = currentTimeMillis;
                try {
                    writableDatabase.execSQL("UPDATE instruments SET status='RETIRED' WHERE exchange IS NOT NULL AND exchange<>'BINANCE'");
                } catch (Throwable unused4) {
                }
                this.lastUniverseSync = j2;
                this.db.log("INFO", "DISCOVERY", "BINANCE_UNIVERSE_SYNC", i4 + " USDT spot pairs ACTIVE (volume-ranked: MAJOR top-10, RETAIL 11-60, ALTCOIN 61+) — 15m PDF pack SAB par, 1m scan top-40 par");
            }
        } catch (Throwable th) {
            this.db.log("WARN", "DISCOVERY", "UNIVERSE_SYNC_FAIL", String.valueOf(th));
        }
    }

    private void discover() {
        long currentTimeMillis = System.currentTimeMillis();
        if (currentTimeMillis - this.lastUniverseSync > 21600000) {
            syncBinanceUniverse();
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, status, IFNULL(last_data_at,0) FROM instruments", null);
        ArrayList<Object[]> arrayList = new ArrayList();
        while (rawQuery.moveToNext()) {
            String string = rawQuery.getString(0);
            String string2 = rawQuery.getString(1);
            long j = rawQuery.getLong(2);
            if (j > 0) {
                if ("ACTIVE".equals(string2) && currentTimeMillis - j > 21600000) {
                    arrayList.add(new Object[]{"WATCHING", string});
                } else if ("WATCHING".equals(string2) && currentTimeMillis - j < CONSEC_LOSS_COOLDOWN_MS) {
                    arrayList.add(new Object[]{"ACTIVE", string});
                }
            }
        }
        rawQuery.close();
        for (Object[] objArr : arrayList) {
            this.db.getWritableDatabase().execSQL("UPDATE instruments SET status=? WHERE symbol=?", objArr);
            this.db.log("INFO", "DISCOVERY", "UNIVERSE_MAINT", objArr[1] + " -> " + objArr[0] + ("WATCHING".equals(objArr[0]) ? " (data 6h+ purana — market band hai)" : " (data wapas aya)"));
        }
    }

    private void fetchNews() {
        String str = null;
        String str2 = null;
        int i = 0;
        String[] strArr = FEEDS;
        int length = strArr.length;
        int i2 = 0;
        int i3 = 0;
        while (i3 < length) {
            String str3 = strArr[i3];
            String rawGet = rawGet(str3);
            if (rawGet != null) {
                Iterator<String[]> it = parseRss(rawGet).iterator();
                while (it.hasNext()) {
                    String trim = it.next()[i2].trim();
                    if (!trim.isEmpty()) {
                        SQLiteDatabase readableDatabase = this.db.getReadableDatabase();
                        String[] strArr2 = new String[1];
                        strArr2[i2] = trim;
                        Cursor rawQuery = readableDatabase.rawQuery("SELECT id FROM news WHERE headline=?", strArr2);
                        boolean moveToFirst = rawQuery.moveToFirst();
                        rawQuery.close();
                        if (!moveToFirst) {
                            String lowerCase = trim.toLowerCase();
                            String[] strArr3 = BULL;
                            int length2 = strArr3.length;
                            int i4 = i2;
                            int i5 = i4;
                            while (i4 < length2) {
                                if (lowerCase.contains(strArr3[i4])) {
                                    i5++;
                                }
                                i4++;
                            }
                            String[] strArr4 = BEAR;
                            int length3 = strArr4.length;
                            int i6 = i2;
                            int i7 = i6;
                            while (i6 < length3) {
                                if (lowerCase.contains(strArr4[i6])) {
                                    i7++;
                                }
                                i6++;
                            }
                            if (i5 > i7) {
                                str = "BULLISH";
                            } else {
                                str = i7 > i5 ? "BEARISH" : "NEUTRAL";
                            }
                            String[] strArr5 = HIGH_IMPACT;
                            int length4 = strArr5.length;
                            int i8 = i2;
                            while (true) {
                                if (i8 >= length4) {
                                    str2 = "LOW";
                                    break;
                                }
                                if (Pattern.compile("\\b" + Pattern.quote(strArr5[i8]) + "\\b").matcher(lowerCase).find()) {
                                    str2 = "HIGH";
                                    break;
                                }
                                i8++;
                            }
                            this.db.getWritableDatabase().execSQL("INSERT INTO news(ts, source, headline, sentiment, impact) VALUES(?,?,?,?,?)", new Object[]{Long.valueOf(System.currentTimeMillis()), str3.contains("coindesk") ? "CoinDesk" : "CoinTelegraph", trim, str, str2});
                            this.db.log("INFO", "NEWS", "INGEST", str + "/" + str2 + " — " + trim.substring(0, Math.min(80, trim.length())));
                            try {
                                this.db.getWritableDatabase().execSQL("DELETE FROM news WHERE id NOT IN (SELECT id FROM news ORDER BY id DESC LIMIT 500)");
                            } catch (Throwable unused) {
                            }
                            if ("HIGH".equals(str2)) {
                                i = 0;
                                this.db.log("INFO", "NEWS", "HIGH_IMPACT", "display-only — entries NOT paused (" + trim.substring(0, Math.min(60, trim.length())) + ")");
                            } else {
                                i = 0;
                            }
                            i2 = i;
                        }
                    }
                }
            }
            i3++;
            i2 = i2;
        }
    }

    private List<String[]> parseRss(String str) {
        int indexOf = 0;
        int indexOf2 = 0;
        ArrayList arrayList = new ArrayList();
        int i = 0;
        while (arrayList.size() < 12 && (indexOf = str.indexOf("<item>", i)) >= 0 && (indexOf2 = str.indexOf("</item>", indexOf)) >= 0) {
            String substring = str.substring(indexOf, indexOf2);
            int indexOf3 = substring.indexOf("<title>");
            int indexOf4 = substring.indexOf("</title>");
            if (indexOf3 >= 0 && indexOf4 > indexOf3) {
                String trim = substring.substring(indexOf3 + 7, indexOf4).replace("<![CDATA[", "").replace("]]>", "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", "\"").replace("&#39;", "'").replace("&nbsp;", " ").trim();
                if (!trim.isEmpty()) {
                    arrayList.add(new String[]{trim});
                }
            }
            i = indexOf2 + 7;
        }
        return arrayList;
    }

    private String rawGet(String str) {
        try {
            HttpURLConnection httpURLConnection = (HttpURLConnection) new URL(str).openConnection();
            httpURLConnection.setConnectTimeout(10000);
            httpURLConnection.setReadTimeout(15000);
            httpURLConnection.setRequestProperty("User-Agent", "Mozilla/5.0 AI-Trading-Lab/5.0");
            if (httpURLConnection.getResponseCode() != 200) {
                return null;
            }
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(httpURLConnection.getInputStream()));
            StringBuilder sb = new StringBuilder();
            while (true) {
                String readLine = bufferedReader.readLine();
                if (readLine == null) {
                    bufferedReader.close();
                    return sb.toString();
                }
                sb.append(readLine);
            }
        } catch (Exception unused) {
            return null;
        }
    }

    private void fetchFearGreed() {
        String rawGet = rawGet("https://api.alternative.me/fng/?limit=1");
        if (rawGet == null) {
            return;
        }
        try {
            JSONArray jSONArray = new JSONObject(rawGet).getJSONArray("data");
            if (jSONArray.length() > 0) {
                this.fngValue = Integer.parseInt(jSONArray.getJSONObject(0).getString("value"));
                this.db.log("INFO", "SENTIMENT", "FNG", "crypto Fear & Greed = " + this.fngValue + " (" + jSONArray.getJSONObject(0).getString("value_classification") + ")");
            }
        } catch (Exception unused) {
        }
    }

    public double livePrice(String str) {
        // v1.4: pehle 1s LIVE TICK (10s tak fresh), warna candle close fallback
        double[] liveTick = this.livePx.get(str);
        if (liveTick != null && liveTick[0] > 0.0d && System.currentTimeMillis() - ((long) liveTick[1]) < 10000L) {
            return liveTick[0];
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT c FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT 1", new String[]{str, "5m"});
        double d = rawQuery.moveToFirst() ? rawQuery.getDouble(0) : Double.NaN;
        rawQuery.close();
        return d;
    }

    // v1.4 LIVE TICK LOOP — active symbols ka batch price har 1s (Binance /api/v3/ticker/price, weight 2)
    private void livePxLoop() {
        long backoff = 1000L;
        while (this.running) {
            try {
                List<String> syms = activeSymbols();
                if (syms.isEmpty()) {
                    Thread.sleep(2000L);
                    continue;
                }
                StringBuilder sb = new StringBuilder("[");
                for (int i = 0; i < syms.size(); i++) {
                    if (i > 0) sb.append(',');
                    sb.append('"').append(syms.get(i)).append('"');
                }
                sb.append(']');
                String body = httpGetUrl("https://api.binance.com/api/v3/ticker/price?symbols=" + java.net.URLEncoder.encode(sb.toString(), "UTF-8"), 5000);
                if (body == null) throw new IllegalStateException("no body");
                JSONArray arr = new JSONArray(body);
                long now = System.currentTimeMillis();
                for (int i = 0; i < arr.length(); i++) {
                    JSONObject o = arr.getJSONObject(i);
                    String s = o.optString("symbol");
                    double p = o.optDouble("price", 0.0d);
                    if (s.length() > 0 && p > 0.0d) {
                        this.livePx.put(s, new double[]{p, (double) now});
                    }
                }
                backoff = 1000L;
                if (!this.livePxLogged) {
                    this.livePxLogged = true;
                    this.db.log("INFO", "FEED", "LIVEPX_ON", "1-second LIVE price feed chal raha hai — " + arr.length() + " symbols @ 1s tick (live market + live P&L)");
                }
                Thread.sleep(1000L);
            } catch (InterruptedException ie) {
                return;
            } catch (Throwable t) {
                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException ie2) {
                    return;
                }
                if (backoff < 10000L) backoff *= 2L;
            }
        }
    }

    static String bucketOf(String str) {
        return BUCKET.getOrDefault(str, "MAJOR");
    }

    private double slipEntry(double d, String str) {
        double slipBps = slipBps() / 10000.0d;
        return "BUY".equals(str) ? d * (slipBps + 1.0d) : d * (1.0d - slipBps);
    }

    private double slipExit(double d, String str) {
        double slipBps = slipBps() / 10000.0d;
        return "BUY".equals(str) ? d * (1.0d - slipBps) : d * (slipBps + 1.0d);
    }

    public double heatRiskPct(long j) {
        int i = 1;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, side, qty, entry, sl, status FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        double d = 0.0d;
        double d2 = 0.0d;
        while (rawQuery.moveToNext()) {
            String string = rawQuery.getString(0);
            String string2 = rawQuery.getString(i);
            double d3 = rawQuery.getDouble(2);
            double d4 = rawQuery.getDouble(CONSEC_LOSS_DEFAULT);
            d2 += Math.abs(d4 - rawQuery.getDouble(4)) * d3;
            double livePrice = livePrice(string);
            if (!Double.isNaN(livePrice)) {
                d += ("BUY".equals(string2) ? livePrice - d4 : d4 - livePrice) * d3;
            }
            i = 1;
        }
        rawQuery.close();
        double balanceOf = balanceOf(j) + d;
        if (balanceOf > 0.0d) {
            return (d2 / balanceOf) * 100.0d;
        }
        return 0.0d;
    }

    public double bucketRiskPct(long j, String str) {
        int i = 0;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, side, qty, entry, sl, status FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        double d = 0.0d;
        double d2 = 0.0d;
        while (rawQuery.moveToNext()) {
            if (str.equals(bucketOf(rawQuery.getString(i)))) {
                double d3 = rawQuery.getDouble(2);
                double d4 = rawQuery.getDouble(CONSEC_LOSS_DEFAULT);
                d2 += Math.abs(d4 - rawQuery.getDouble(4)) * d3;
                double livePrice = livePrice(rawQuery.getString(i));
                if (!Double.isNaN(livePrice)) {
                    d += ("BUY".equals(rawQuery.getString(1)) ? livePrice - d4 : d4 - livePrice) * d3;
                }
                i = 0;
            }
        }
        rawQuery.close();
        double balanceOf = balanceOf(j) + d;
        if (balanceOf > 0.0d) {
            return (d2 / balanceOf) * 100.0d;
        }
        return 0.0d;
    }

    private boolean freshData(String str) {
        long j = 0L;
        try {
            j = Math.max(2, Integer.parseInt(this.db.setting("safe_mode_bars", "3").trim()));
        } catch (Exception unused) {
            j = 3;
        }
        boolean z = false;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT 1", new String[]{str, "5m"});
        if (rawQuery.moveToFirst() && System.currentTimeMillis() - rawQuery.getLong(0) < j * TF_MS_PUB) {
            z = true;
        }
        rawQuery.close();
        return z;
    }

    private void updateFeedHealth() {
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, MAX(ts) FROM candles WHERE tf='5m' AND symbol IN (SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE') GROUP BY symbol", null);
            long currentTimeMillis = System.currentTimeMillis();
            int i = 0;
            int i2 = 0;
            while (rawQuery.moveToNext() && i < 200) {
                i++;
                if (currentTimeMillis - rawQuery.getLong(1) < 900000) {
                    i2++;
                }
            }
            rawQuery.close();
            if (i == 0) {
                return;
            }
            boolean z = this.safeMode;
            this.safeMode = latchSafeMode(z, i, i2);
            if (this.safeMode && !z) {
                this.safeModeSince = currentTimeMillis;
                this.db.log("WARN", "FEED", "SAFE_MODE_ON", "feed outage — " + i2 + "/" + i + " symbols fresh (<=20%) — SAFE MODE: naye entries band, open trades ka SL/TP freeze. Feed recover hote hi auto-clear.");
                try {
                    Notifier.post(appContext(), "SAFE MODE", "Feed outage — candles stale. Naye entries band, khuli trades protected.");
                    return;
                } catch (Throwable unused) {
                    return;
                }
            }
            if (this.safeMode || !z) {
                return;
            }
            this.db.log("INFO", "FEED", "SAFE_MODE_OFF", "feed recovered — " + i2 + "/" + i + " symbols fresh — normal trading resumed (" + Math.max(1L, (currentTimeMillis - this.safeModeSince) / 60000) + " min outage)");
        } catch (Throwable th) {
            this.db.log("WARN", "FEED", "FEED_HEALTH_FAIL", String.valueOf(th));
        }
    }

    public boolean isSafeMode() {
        return this.safeMode;
    }

    public boolean isMarketClosed() {
        return marketClosedET();
    }

    private boolean eventGateActive() {
        boolean z = false;
        if (!eventGateOn()) {
            return false;
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM news WHERE impact='HIGH' AND ts > ?", new String[]{String.valueOf(System.currentTimeMillis() - CONSEC_LOSS_COOLDOWN_MS)});
        if (rawQuery.moveToFirst() && rawQuery.getInt(0) > 0) {
            z = true;
        }
        rawQuery.close();
        return z;
    }

    private boolean inCmeHalt() {
        if (!sessionFilterOn()) {
            return false;
        }
        try {
            Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("America/New_York"));
            int i = calendar.get(11);
            int i2 = calendar.get(12);
            if (i != 17 || i2 < 0) {
                return false;
            }
            return i < 18 || (i == 17 && i2 < 60);
        } catch (Throwable unused) {
            return false;
        }
    }

    private int newsBias() {
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT sentiment, COUNT(*) FROM news WHERE ts > ? GROUP BY sentiment", new String[]{String.valueOf(System.currentTimeMillis() - 86400000)});
            int i = 0;
            int i2 = 0;
            while (rawQuery.moveToNext()) {
                String string = rawQuery.getString(0) == null ? "" : rawQuery.getString(0);
                if (string.contains("BULL")) {
                    i += rawQuery.getInt(1);
                } else if (string.contains("BEAR")) {
                    i2 += rawQuery.getInt(1);
                }
            }
            rawQuery.close();
            return Math.max(-10, Math.min(10, i - i2));
        } catch (Throwable unused) {
            return 0;
        }
    }

    /* JADX WARN: Code restructure failed: missing block: B:58:0x0026, code lost:
    
        if (r5 < r3) goto L11;
     */
    /* JADX WARN: Removed duplicated region for block: B:12:0x003a  */
    /* JADX WARN: Removed duplicated region for block: B:31:0x0082 A[Catch: all -> 0x00ce, TryCatch #0 {all -> 0x00ce, blocks: (B:3:0x000b, B:10:0x002d, B:16:0x004c, B:20:0x0059, B:24:0x0063, B:25:0x0065, B:29:0x0075, B:31:0x0082, B:34:0x008e, B:35:0x0090, B:38:0x0098, B:40:0x009f, B:42:0x00a7), top: B:2:0x000b }] */
    /* JADX WARN: Removed duplicated region for block: B:32:0x0085  */
    /* JADX WARN: Removed duplicated region for block: B:37:0x0096  */
    /* JADX WARN: Removed duplicated region for block: B:48:0x00cc  */
    /* JADX WARN: Removed duplicated region for block: B:56:0x0097  */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    public int councilScore(String str, String str2, List<Candle> list, int i) {
        double ema = 0.0d;
        double d = 0.0d;
        int i2 = 0;
        double rsi = 0.0d;
        double atr = 0.0d;
        JSONObject seasonality = null;
        JSONArray optJSONArray = null;
        double optDouble = 0.0d;
        double d2 = 0.0d;
        boolean equals = "BUY".equals(str2);
        int i3 = 50;
        try {
            ema = ema(list, 200);
            d = list.get(i).c;
        } catch (Throwable unused) {
        }
        if (!Double.isNaN(ema)) {
            if (equals) {
                i2 = d > ema ? 65 : 35;
            }
            int i4 = i2;
            rsi = rsi(list, 14);
            if (!Double.isNaN(rsi)) {
                if (rsi >= 45.0d && rsi <= 65.0d) {
                    i4 += 10;
                }
                if (equals && rsi > 78.0d) {
                    i4 -= 12;
                }
                if (!equals && rsi < X7_ADX_MAX) {
                    i4 -= 12;
                }
            }
            atr = atr(list, 14);
            if (!Double.isNaN(atr) && atr > 0.0d) {
                d2 = (atr / d) * 100.0d;
                if (d2 < 0.16d) {
                    i4 += 10;
                } else if (d2 < 0.08d) {
                    i4 -= 20;
                }
            }
            int newsBias = newsBias();
            if (equals) {
                newsBias = -newsBias;
            }
            i3 = i4 + newsBias;
            seasonality = seasonality(str, false);
            if (seasonality != null && (optJSONArray = seasonality.optJSONArray("avg")) != null) {
                optDouble = optJSONArray.optDouble(Calendar.getInstance(TimeZone.getTimeZone("UTC")).get(2), 0.0d);
                if (equals ? optDouble < 0.0d : optDouble > 0.0d) {
                    i3 += 10;
                } else if (optDouble != 0.0d) {
                    i3 -= 8;
                }
            }
            return Math.max(0, Math.min(100, i3));
        }
        int i42 = i2;
        rsi = rsi(list, 14);
        if (!Double.isNaN(rsi)) {
        }
        atr = atr(list, 14);
        if (!Double.isNaN(atr)) {
            d2 = (atr / d) * 100.0d;
            if (d2 < 0.16d) {
            }
        }
        int newsBias2 = newsBias();
        if (equals) {
        }
        i3 = i42 + newsBias2;
        seasonality = seasonality(str, false);
        if (seasonality != null) {
            optDouble = optJSONArray.optDouble(Calendar.getInstance(TimeZone.getTimeZone("UTC")).get(2), 0.0d);
            if (equals) {
                if (optDouble != 0.0d) {
                }
            } else if (optDouble != 0.0d) {
            }
        }
        return Math.max(0, Math.min(100, i3));
    }

    public JSONObject seasonality(String str, boolean z) {
        int[] iArr = null;
        long j = 0L;
        long j2 = 0L;
        JSONObject jSONObject = this.seasonCache.get(str);
        long currentTimeMillis = System.currentTimeMillis();
        if ((!z && jSONObject != null && currentTimeMillis - jSONObject.optLong("fetched", 0L) < 86400000) || !binanceTradable(str)) {
            return jSONObject;
        }
        try {
            ArrayList arrayList = new ArrayList();
            long j3 = currentTimeMillis - 157680000000L;
            while (true) {
                int i = 0;
                if (j3 >= currentTimeMillis) {
                    break;
                }
                String httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/klines?symbol=" + str + "&interval=1d&startTime=" + j3 + "&endTime=" + Math.min(j3 + 86313600000L, currentTimeMillis) + "&limit=1000", 15000);
                if (httpGetUrl == null) {
                    break;
                }
                JSONArray jSONArray = new JSONArray(httpGetUrl);
                int size = arrayList.size();
                int i2 = 0;
                while (i2 < jSONArray.length()) {
                    JSONArray jSONArray2 = jSONArray.getJSONArray(i2);
                    Candle candle = new Candle();
                    candle.ts = jSONArray2.getLong(i);
                    candle.o = jSONArray2.getDouble(1);
                    candle.h = jSONArray2.getDouble(2);
                    candle.l = jSONArray2.getDouble(CONSEC_LOSS_DEFAULT);
                    candle.c = jSONArray2.getDouble(4);
                    candle.v = jSONArray2.getDouble(5);
                    arrayList.add(candle);
                    i2++;
                    i = 0;
                }
                if (jSONArray.length() == 0 || arrayList.size() == size) {
                    break;
                }
                j3 = jSONArray.getJSONArray(jSONArray.length() - 1).getLong(0) + 86400000;
            }
            if (arrayList.size() < 100) {
                return jSONObject;
            }
            Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
            double[] dArr = new double[12];
            int[] iArr2 = new int[12];
            int[] iArr3 = new int[12];
            Iterator it = arrayList.iterator();
            long j4 = -1;
            String str2 = "fetched";
            long j5 = -1;
            double d = 0.0d;
            while (it.hasNext()) {
                Candle candle2 = (Candle) it.next();
                long j6 = j5;
                double d2 = candle2.c;
                if (d2 <= 0.0d) {
                    j5 = j6;
                } else {
                    Iterator it2 = it;
                    String str3 = str2;
                    calendar.setTimeInMillis(candle2.ts);
                    long j7 = calendar.get(2);
                    Calendar calendar2 = calendar;
                    long j8 = calendar.get(1);
                    if (d <= 0.0d || (j7 == j6 && j8 == j4)) {
                        j2 = j8;
                    } else {
                        double d3 = ((d2 - d) / d) * 100.0d;
                        j2 = j8;
                        int i3 = (int) j6;
                        dArr[i3] = dArr[i3] + d3;
                        iArr2[i3] = iArr2[i3] + 1;
                        if (d3 > 0.0d) {
                            iArr3[i3] = iArr3[i3] + 1;
                        }
                    }
                    j4 = j2;
                    calendar = calendar2;
                    d = d2;
                    j5 = j7;
                    str2 = str3;
                    it = it2;
                }
            }
            String str4 = str2;
            JSONArray jSONArray3 = new JSONArray();
            JSONArray jSONArray4 = new JSONArray();
            int i4 = 0;
            for (int i5 = 12; i4 < i5; i5 = 12) {
                jSONArray3.put(iArr2[i4] > 0 ? Math.round((dArr[i4] / iArr2[i4]) * 100.0d) / 100.0d : 0.0d);
                int i6 = iArr2[i4];
                if (i6 > 0) {
                    iArr = iArr3;
                    j = Math.round((iArr3[i4] * 100.0d) / i6);
                } else {
                    iArr = iArr3;
                    j = 0;
                }
                jSONArray4.put(j);
                i4++;
                iArr3 = iArr;
            }
            JSONObject put = new JSONObject().put("symbol", str).put("avg", jSONArray3).put("hit", jSONArray4).put("n", new JSONArray(iArr2)).put("years", Math.max(1, (int) Math.round(arrayList.size() / 365.0d))).put(str4, currentTimeMillis);
            this.seasonCache.put(str, put);
            return put;
        } catch (Throwable unused) {
            return jSONObject;
        }
    }

    private synchronized JSONObject mlWeights() {
        if (this.mlLoaded) {
            return this.mlWeights;
        }
        try {
            String str = this.db.setting("ml_weights", "");
            if (str != null && !str.isEmpty()) {
                this.mlWeights = new JSONObject(str);
            }
        } catch (Throwable unused) {
        }
        this.mlLoaded = true;
        return this.mlWeights;
    }

    public double mlWinProb(JSONObject jSONObject) {
        JSONObject mlWeights = mlWeights();
        if (mlWeights != null && jSONObject != null) {
            try {
                JSONObject jSONObject2 = mlWeights.getJSONObject("w");
                double optDouble = mlWeights.optDouble("b", 0.0d);
                Iterator<String> keys = jSONObject2.keys();
                while (keys.hasNext()) {
                    String next = keys.next();
                    optDouble += jSONObject2.optDouble(next, 0.0d) * jSONObject.optDouble(next, 0.0d);
                }
                return 1.0d / (Math.exp(-optDouble) + 1.0d);
            } catch (Throwable unused) {
            }
        }
        return 0.0d;
    }

    public void mlTrain() {
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT features, pnl, risk_amt FROM trades WHERE status='CLOSED' AND features!='{}' AND features IS NOT NULL ORDER BY closed_at DESC LIMIT 300", null);
            ArrayList arrayList = new ArrayList();
            ArrayList arrayList2 = new ArrayList();
            int i = 0;
            List asList = Arrays.asList("bd", "vr", "ap", "ed", "rd", "hr", "cs");
            while (true) {
                double d = 1.0d;
                if (!rawQuery.moveToNext() || arrayList.size() >= 300) {
                    break;
                }
                try {
                    JSONObject jSONObject = new JSONObject(rawQuery.getString(i));
                    double[] dArr = new double[asList.size()];
                    for (int i2 = i; i2 < asList.size(); i2++) {
                        dArr[i2] = jSONObject.optDouble((String) asList.get(i2), 0.0d);
                    }
                    arrayList.add(dArr);
                    if (rawQuery.getDouble(1) <= 0.0d) {
                        d = 0.0d;
                    }
                    arrayList2.add(Double.valueOf(d));
                } catch (Throwable unused) {
                }
                i = 0;
            }
            rawQuery.close();
            if (arrayList.size() < ACTIVE_TOP) {
                return;
            }
            int size = asList.size();
            double[] dArr2 = new double[size];
            double d2 = 0.0d;
            for (int i3 = 0; i3 < 300; i3++) {
                for (int i4 = 0; i4 < arrayList.size(); i4++) {
                    double d3 = d2;
                    for (int i5 = 0; i5 < size; i5++) {
                        d3 += dArr2[i5] * ((double[]) arrayList.get(i4))[i5];
                    }
                    double exp = (1.0d / (Math.exp(-d3) + 1.0d)) - ((Double) arrayList2.get(i4)).doubleValue();
                    for (int i6 = 0; i6 < size; i6++) {
                        dArr2[i6] = dArr2[i6] - ((0.05d * exp) * ((double[]) arrayList.get(i4))[i6]);
                    }
                    d2 -= 0.05d * exp;
                }
            }
            int i7 = 0;
            for (int i8 = 0; i8 < arrayList.size(); i8++) {
                double d4 = d2;
                for (int i9 = 0; i9 < size; i9++) {
                    d4 += dArr2[i9] * ((double[]) arrayList.get(i8))[i9];
                }
                if ((d4 > 0.0d) == (((Double) arrayList2.get(i8)).doubleValue() > 0.5d)) {
                    i7++;
                }
            }
            JSONObject jSONObject2 = new JSONObject();
            for (int i10 = 0; i10 < asList.size(); i10++) {
                jSONObject2.put((String) asList.get(i10), Math.round(dArr2[i10] * 10000.0d) / 10000.0d);
            }
            JSONObject put = new JSONObject().put("w", jSONObject2).put("b", Math.round(d2 * 10000.0d) / 10000.0d).put("n", arrayList.size()).put("acc", Math.round((i7 * 100.0d) / arrayList.size())).put("ts", System.currentTimeMillis());
            this.db.setSetting("ml_weights", put.toString());
            this.mlWeights = put;
            this.db.log("INFO", "ML", "ML_TRAINED", "logistic retrained on " + arrayList.size() + " trades — train acc " + put.optInt("acc") + "% (experimental FreqAI-lite)");
        } catch (Throwable th) {
            this.db.log("ERROR", "ML", "ML_TRAIN_FAIL", String.valueOf(th));
        }
    }

    private void mlDriftCheck() {
        try {
            if (mlWeights() == null) {
                return;
            }
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT win_prob, pnl FROM trades WHERE status='CLOSED' AND win_prob>0 ORDER BY closed_at DESC LIMIT 30", null);
            double d = 0.0d;
            int i = 0;
            int i2 = 0;
            while (rawQuery.moveToNext()) {
                d += rawQuery.getDouble(0);
                i++;
                if (rawQuery.getDouble(1) > 0.0d) {
                    i2++;
                }
            }
            rawQuery.close();
            if (i >= 20) {
                double d2 = i;
                double d3 = d / d2;
                double d4 = i2 / d2;
                if (Math.abs(d3 - d4) > 0.25d) {
                    this.db.log("WARN", "ML", "ML_DRIFT", "model avg winProb " + String.format(Locale.US, "%.2f", Double.valueOf(d3)) + " vs actual winrate " + String.format(Locale.US, "%.2f", Double.valueOf(d4)) + " — regime drift, agla retrain important");
                }
            }
        } catch (Throwable unused) {
        }
    }

    public void degradationCheck() {
        int i = 0;
        long j = 0L;
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT strategy, COUNT(*) FROM trades WHERE status='CLOSED' GROUP BY strategy HAVING COUNT(*)>=20", null);
            ArrayList arrayList = new ArrayList();
            while (true) {
                i = 1;
                if (!rawQuery.moveToNext()) {
                    break;
                } else {
                    arrayList.add(new String[]{rawQuery.getString(0), rawQuery.getString(1)});
                }
            }
            rawQuery.close();
            Iterator it = arrayList.iterator();
            while (it.hasNext()) {
                String str = ((String[]) it.next())[0];
                if (str != null) {
                    boolean startsWith = str.startsWith("3C");
                    if (!str.startsWith("AI:PAPER")) {
                        SQLiteDatabase readableDatabase = this.db.getReadableDatabase();
                        String[] strArr = new String[i];
                        strArr[0] = str;
                        Cursor rawQuery2 = readableDatabase.rawQuery("SELECT pnl FROM trades WHERE strategy=? AND status='CLOSED' ORDER BY closed_at DESC LIMIT 20", strArr);
                        double d = 0.0d;
                        double d2 = 0.0d;
                        while (rawQuery2.moveToNext()) {
                            boolean z = startsWith;
                            double d3 = rawQuery2.getDouble(0);
                            if (d3 > 0.0d) {
                                d2 += d3;
                            } else {
                                d += -d3;
                            }
                            startsWith = z;
                        }
                        boolean z2 = startsWith;
                        rawQuery2.close();
                        if (d > 0.0d) {
                            double d4 = d2 / d;
                            String str2 = "deg_" + str;
                            try {
                                j = Long.parseLong(this.db.setting(str2, "0"));
                            } catch (Exception unused) {
                                j = 0;
                            }
                            if (d4 < 0.7d && System.currentTimeMillis() - j > 43200000) {
                                this.db.setSetting(str2, String.valueOf(System.currentTimeMillis()));
                                this.db.log("WARN", "GUARD", "STRATEGY_DEGRADED", str + " rolling 20-trade PF " + String.format(Locale.US, "%.2f", Double.valueOf(d4)) + " (<0.7) — strategy kharab chal rahi hai, owner dekhein");
                                try {
                                    this.db.getWritableDatabase().execSQL("INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('DEGRADED',?,?,?,0,?)", new Object[]{"Strategy degraded — " + str, str + " ki aakhri 20 trades ka Profit Factor " + String.format(Locale.US, "%.2f", Double.valueOf(d4)) + " hai (<0.7 threshold). Strategy Lab me review karein" + (z2 ? " — 3C MASTER hai, PRO filters/settings check karein." : " — is strategy ko trash/restore kar sakte hain."), "{}", Long.valueOf(System.currentTimeMillis())});
                                } catch (Throwable unused2) {
                                }
                                try {
                                    Notifier.post(appContext(), "STRATEGY DEGRADED", str + " rolling PF " + String.format(Locale.US, "%.2f", Double.valueOf(d4)));
                                } catch (Throwable unused3) {
                                }
                                if (!z2 && autoPauseDegraded()) {
                                    this.db.setSetting("paused_" + str, "1");
                                    this.db.log("WARN", "GUARD", "STRATEGY_PAUSED", str + " auto-paused (auto_pause ON) — Control me re-enable karein");
                                }
                            }
                        }
                        i = 1;
                    }
                }
            }
            mlDriftCheck();
        } catch (Throwable th) {
            this.db.log("ERROR", "GUARD", "DEG_CHECK_FAIL", String.valueOf(th));
        }
    }

    private boolean strategyPaused(String str) {
        return "1".equals(this.db.setting("paused_" + str, "0"));
    }

    private void saveGuardState() {
        try {
            JSONObject jSONObject = new JSONObject();
            JSONObject jSONObject2 = new JSONObject();
            for (Map.Entry<String, Long> entry : this.cooldownUntil.entrySet()) {
                jSONObject2.put(entry.getKey(), entry.getValue());
            }
            jSONObject.put("cooldown", jSONObject2).put("ts", System.currentTimeMillis());
            this.db.setSetting("guard_state_v1", jSONObject.toString());
        } catch (Throwable unused) {
        }
    }

    private void loadGuardState() {
        try {
            String str = this.db.setting("guard_state_v1", "");
            if (str != null && !str.isEmpty()) {
                JSONObject optJSONObject = new JSONObject(str).optJSONObject("cooldown");
                if (optJSONObject != null) {
                    Iterator<String> keys = optJSONObject.keys();
                    long currentTimeMillis = System.currentTimeMillis();
                    while (keys.hasNext()) {
                        String next = keys.next();
                        long optLong = optJSONObject.optLong(next, 0L);
                        if (optLong > currentTimeMillis) {
                            this.cooldownUntil.put(next, Long.valueOf(optLong));
                        }
                    }
                }
                if (this.cooldownUntil.isEmpty()) {
                    return;
                }
                this.db.log("INFO", "GUARD", "GUARD_RESTORED", this.cooldownUntil.size() + " active cooldown(s) restart ke baad restore — PRO GUARD ab persistent hai");
            }
        } catch (Throwable unused) {
        }
    }

    private void recordOrder(long j, long j2, String str, String str2, String str3, double d, double d2, String str4, String str5) {
        try {
            this.db.getWritableDatabase().execSQL("INSERT INTO orders(trade_id, user_id, symbol, side, type, price, qty, status, source, ts) VALUES(?,?,?,?,?,?,?,?,?,?)", new Object[]{Long.valueOf(j), Long.valueOf(j2), str, str2, str3, Double.valueOf(d), Double.valueOf(d2), str5, str4, Long.valueOf(System.currentTimeMillis())});
        } catch (Throwable unused) {
        }
    }

    private String httpPostUrl(String str, String str2, int i) {
        try {
            HttpURLConnection httpURLConnection = (HttpURLConnection) new URL(str).openConnection();
            httpURLConnection.setConnectTimeout(i);
            httpURLConnection.setReadTimeout(i + 5000);
            httpURLConnection.setRequestMethod("POST");
            httpURLConnection.setRequestProperty("Content-Type", "application/json");
            httpURLConnection.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) AI-Trading-Lab/3.0");
            httpURLConnection.setDoOutput(true);
            OutputStream outputStream = httpURLConnection.getOutputStream();
            outputStream.write(str2.getBytes("UTF-8"));
            outputStream.flush();
            outputStream.close();
            if (httpURLConnection.getResponseCode() != 200) {
                return null;
            }
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(httpURLConnection.getInputStream()));
            StringBuilder sb = new StringBuilder();
            while (true) {
                String readLine = bufferedReader.readLine();
                if (readLine == null) {
                    bufferedReader.close();
                    return sb.toString();
                }
                sb.append(readLine);
            }
        } catch (Exception unused) {
            return null;
        }
    }

    private void bridgeOrder(final String str, final String str2, final long j, final long j2, final double d, final double d2) {
        String str3 = null;
        if (bridgeLive()) {
            final String mt5Bridge = mt5Bridge();
            if (mt5Bridge.isEmpty()) {
                return;
            }
            try {
                try {
                } catch (Throwable unused) {
                    str3 = "{}";
                    final String str4 = str3;
                    Thread thread = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda4
                        @Override // java.lang.Runnable
                        public final void run() {
                            EngineCore.this.lambda$bridgeOrder$4(mt5Bridge, str4, j, j2, str, str2, d, d2);
                        }
                    }, "bridge-order");
                    thread.setDaemon(true);
                    thread.start();
                }
                try {
                } catch (Throwable unused2) {
                    str3 = "{}";
                    final String str42 = str3;
                    Thread thread2 = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda4
                        @Override // java.lang.Runnable
                        public final void run() {
                            EngineCore.this.lambda$bridgeOrder$4(mt5Bridge, str42, j, j2, str, str2, d, d2);
                        }
                    }, "bridge-order");
                    thread2.setDaemon(true);
                    thread2.start();
                }
                try {
                    str3 = new JSONObject().put("symbol", str).put("side", str2).put("volume", bridgeLots()).put("trade_id", j).toString();
                } catch (Throwable unused3) {
                    str3 = "{}";
                    final String str422 = str3;
                    Thread thread22 = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda4
                        @Override // java.lang.Runnable
                        public final void run() {
                            EngineCore.this.lambda$bridgeOrder$4(mt5Bridge, str422, j, j2, str, str2, d, d2);
                        }
                    }, "bridge-order");
                    thread22.setDaemon(true);
                    thread22.start();
                }
            } catch (Throwable unused4) {
            }
            final String str4222 = str3;
            Thread thread222 = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda4
                @Override // java.lang.Runnable
                public final void run() {
                    EngineCore.this.lambda$bridgeOrder$4(mt5Bridge, str4222, j, j2, str, str2, d, d2);
                }
            }, "bridge-order");
            thread222.setDaemon(true);
            thread222.start();
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$bridgeOrder$4(String str, String str2, long j, long j2, String str3, String str4, double d, double d2) {
        try {
            boolean z = httpPostUrl(new StringBuilder().append(str).append(str.endsWith("/") ? "" : "/").append("order").toString(), str2, 8000) != null;
            recordOrder(j, j2, str3, str4, "MARKET", d, d2, "BRIDGE", z ? "SENT" : "REJECTED");
            this.db.log(z ? "INFO" : "WARN", "BRIDGE", z ? "BRIDGE_ORDER_SENT" : "BRIDGE_ORDER_FAIL", str3 + " " + str4 + " " + bridgeLots() + " lots — " + (z ? "bridge ne accept kiya" : "bridge down/reject"));
        } catch (Throwable unused) {
        }
    }

    private void bridgeClose(final String str, final long j, final long j2) {
        if (bridgeLive()) {
            final String mt5Bridge = mt5Bridge();
            if (mt5Bridge.isEmpty()) {
                return;
            }
            Thread thread = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda2
                @Override // java.lang.Runnable
                public final void run() {
                    EngineCore.this.lambda$bridgeClose$5(mt5Bridge, str, j, j2);
                }
            }, "bridge-close");
            thread.setDaemon(true);
            thread.start();
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$bridgeClose$5(String str, String str2, long j, long j2) {
        try {
            recordOrder(j, j2, str2, "CLOSE", "MARKET", 0.0d, 0.0d, "BRIDGE", httpPostUrl(new StringBuilder().append(str).append(str.endsWith("/") ? "" : "/").append("close").toString(), new JSONObject().put("symbol", str2).put("trade_id", j).toString(), 8000) != null ? "SENT" : "REJECTED");
        } catch (Throwable unused) {
        }
    }

    public List<Candle> deepKlines(String str, String str2, int i) {
        List<Candle> parseBinanceKlines = null;
        ArrayList arrayList = new ArrayList();
        long currentTimeMillis = System.currentTimeMillis();
        int i2 = 0;
        while (i2 < i) {
            try {
                String httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/klines?symbol=" + str + "&interval=" + str2 + "&limit=1000&endTime=" + currentTimeMillis, 15000);
                if (httpGetUrl == null || (parseBinanceKlines = parseBinanceKlines(httpGetUrl)) == null || parseBinanceKlines.isEmpty()) {
                    break;
                }
                arrayList.addAll(0, parseBinanceKlines);
                long j = parseBinanceKlines.get(0).ts - 1;
                if (parseBinanceKlines.size() < 1000) {
                    break;
                }
                i2++;
                currentTimeMillis = j;
            } catch (Throwable unused) {
            }
        }
        return arrayList;
    }

    public List<Candle> deepCandles(String str, int i) {
        String httpGetUrl = null;
        String mt5Bridge = mt5Bridge();
        boolean isEmpty = mt5Bridge.isEmpty();
        char c = 5;
        int i2 = CONSEC_LOSS_DEFAULT;
        int i3 = 2;
        if (!isEmpty) {
            try {
                String httpGetUrl2 = httpGetUrl(mt5Bridge + (mt5Bridge.endsWith("/") ? "" : "/") + "candles?symbol=" + str + "&tf=5m&limit=8000", 15000);
                if (httpGetUrl2 != null) {
                    JSONArray jSONArray = new JSONArray(httpGetUrl2);
                    ArrayList arrayList = new ArrayList();
                    for (int i4 = 0; i4 < jSONArray.length(); i4++) {
                        JSONArray jSONArray2 = jSONArray.getJSONArray(i4);
                        Candle candle = new Candle();
                        candle.ts = jSONArray2.getLong(0);
                        candle.o = jSONArray2.getDouble(1);
                        candle.h = jSONArray2.getDouble(2);
                        candle.l = jSONArray2.getDouble(CONSEC_LOSS_DEFAULT);
                        candle.c = jSONArray2.getDouble(4);
                        candle.v = jSONArray2.getDouble(5);
                        arrayList.add(candle);
                    }
                    if (arrayList.size() >= 500) {
                        return arrayList;
                    }
                }
            } catch (Throwable unused) {
            }
        }
        if (!BINANCE_PAIRS.containsKey(str)) {
            return loadCandles(str);
        }
        try {
            ArrayList arrayList2 = new ArrayList();
            long currentTimeMillis = System.currentTimeMillis();
            long j = currentTimeMillis - 180000000;
            while (j < currentTimeMillis && arrayList2.size() < 2900 && (httpGetUrl = httpGetUrl("https://api.binance.com/api/v3/klines?symbol=" + str + "&interval=5m&startTime=" + j + "&endTime=" + currentTimeMillis + "&limit=1000", 15000)) != null) {
                JSONArray jSONArray3 = new JSONArray(httpGetUrl);
                int size = arrayList2.size();
                int i5 = 0;
                while (i5 < jSONArray3.length()) {
                    JSONArray jSONArray4 = jSONArray3.getJSONArray(i5);
                    Candle candle2 = new Candle();
                    candle2.ts = jSONArray4.getLong(0);
                    candle2.o = jSONArray4.getDouble(1);
                    candle2.h = jSONArray4.getDouble(i3);
                    candle2.l = jSONArray4.getDouble(i2);
                    candle2.c = jSONArray4.getDouble(4);
                    candle2.v = jSONArray4.getDouble(5);
                    arrayList2.add(candle2);
                    i5++;
                    c = 5;
                    i2 = CONSEC_LOSS_DEFAULT;
                    i3 = 2;
                }
                char c2 = c;
                if (jSONArray3.length() == 0 || arrayList2.size() == size) {
                    break;
                }
                j = TF_MS_PUB + jSONArray3.getJSONArray(jSONArray3.length() - 1).getLong(0);
                c = c2;
                i2 = CONSEC_LOSS_DEFAULT;
                i3 = 2;
            }
            if (arrayList2.size() >= 500) {
                return arrayList2;
            }
        } catch (Throwable unused2) {
        }
        return loadCandles(str);
    }

    public Map<String, Object> status() {
        long j = 0L;
        int i = 0;
        int i2 = 0;
        HashMap hashMap = new HashMap();
        hashMap.put("engine_on", Boolean.valueOf("1".equals(this.db.setting("engine_on", "1"))));
        hashMap.put("active_symbols", Integer.valueOf(this.activeSymbols));
        hashMap.put("consensus", this.lastConsensus.isEmpty() ? "warming up" : this.lastConsensus);
        hashMap.put("data_host", mt5Bridge().isEmpty() ? "BINANCE (api.binance.com)" : "MT5-BRIDGE");
        hashMap.put("feed", "Binance spot — ALL USDT pairs (volume-ranked MAJOR/RETAIL/ALTCOIN) — 1m scan top-40 + 15m PDF pack ALL pairs");
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE'", null);
            hashMap.put("universe_total", Integer.valueOf(rawQuery.moveToFirst() ? rawQuery.getInt(0) : 0));
            rawQuery.close();
        } catch (Throwable unused) {
        }
        hashMap.put("timeframe", "5m");
        hashMap.put("scanner", "24/7");
        hashMap.put("scan_count", Long.valueOf(this.scanCount));
        hashMap.put("last_scan_at", Long.valueOf(this.lastScanAt));
        hashMap.put("strategy_count", Integer.valueOf(StrategyPack.STRATEGIES.length + 6));
        hashMap.put("strategy_name", "3C MASTER (M5) + PDF PACK (9) + 5M PLAYBOOK (4 — Z.ai guide S1-S4) + SHAAKUNI (5)");
        hashMap.put("pdf_pack", "RESTORED v4.4 — S1 EMA pullback · S2 BB squeeze · S3 Supertrend+ADX · S4 VWAP · S5 PDH/PDL · S6 Funding+OI · S7 Candle patterns · S8 Dow pullback · S9 Gann 50%");
        hashMap.put("risk_pct", Double.valueOf(riskPct()));
        hashMap.put("risk_scaling", scalingInfo("3C_MASTER"));
        hashMap.put("min_trades_scaling", 25);
        hashMap.put("limits", "UNLIMITED daily P/L (owner) — heat/bucket/event/session caps default OFF opt-in");
        hashMap.put("version", "1.2");
        boolean marketClosedET = marketClosedET();
        hashMap.put("safe_mode", Boolean.valueOf(this.safeMode && !marketClosedET));
        hashMap.put("market_closed", Boolean.valueOf(marketClosedET));
        hashMap.put("slip_bps", Double.valueOf(slipBps()));
        hashMap.put("heat_max_pct", Double.valueOf(heatMaxPct()));
        hashMap.put("bucket_max_pct", Double.valueOf(bucketMaxPct()));
        hashMap.put("council_min", Integer.valueOf(councilMin()));
        hashMap.put("event_gate", Boolean.valueOf(eventGateOn()));
        hashMap.put("session_filter", Boolean.valueOf(sessionFilterOn()));
        hashMap.put("bridge_live", Boolean.valueOf(bridgeLive()));
        JSONObject mlWeights = mlWeights();
        hashMap.put("ml", mlWeights != null ? "trained n=" + mlWeights.optInt("n") + " acc=" + mlWeights.optInt("acc") + "% (experimental)" : "warming up (40+ feature-tagged trades chahiye)");
        hashMap.put("degraded_check", "30-min rolling PF monitor + ML drift check");
        hashMap.put("indicator_count", Integer.valueOf(SHAAKUNI_SUITE.length));
        hashMap.put("indicator_suite", "SHAAKUNI TRAP (liquidity/OB/MSS/killzones) + CLASSIC overlay (EMA/RSI/ATR/VWAP/ADX/Supertrend) — chart par live");
        try {
            j = Long.parseLong(this.db.setting("ai_trained_at", "0").trim());
        } catch (Throwable unused2) {
            j = 0;
        }
        hashMap.put("ai_trained_at", Long.valueOf(j));
        hashMap.put("ai_age_h", Long.valueOf(j > 0 ? Math.round((System.currentTimeMillis() - j) / 3600000.0d) : -1L));
        try {
            JSONObject aiWeights = aiWeights();
            if (aiWeights != null) {
                Iterator<String> keys = aiWeights.keys();
                i = 0;
                i2 = 0;
                while (keys.hasNext()) {
                    i2++;
                    if (aiWeights.getJSONObject(keys.next()).optInt("on", 1) == 1) {
                        i++;
                    }
                }
            } else {
                i = 0;
                i2 = 0;
            }
            hashMap.put("ai_strategies_on", Integer.valueOf(i));
            hashMap.put("ai_strategies_total", Integer.valueOf(i2));
        } catch (Throwable unused3) {
        }
        hashMap.put("fee_edge", "ON (min TP move " + this.db.setting("min_fee_edge_pct", "0.14") + "% — round-trip fees se kam move = professional skip)");
        hashMap.put("min_trades_scaling", 25);
        hashMap.put("fear_greed", Integer.valueOf(this.fngValue));
        hashMap.put("last_pattern", this.lastPattern);
        JSONArray jSONArray = new JSONArray();
        for (Map.Entry<String, String> entry : this.threecStates.entrySet()) {
            if (entry.getValue() != null && entry.getValue().contains("armed")) {
                try {
                    jSONArray.put(new JSONObject().put("symbol", entry.getKey()).put("state", entry.getValue()));
                } catch (Throwable unused4) {
                }
                if (jSONArray.length() >= 8) {
                    break;
                }
            }
        }
        hashMap.put("threec_armed", jSONArray);
        try {
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT MAX(ts) FROM candles WHERE tf=?", new String[]{"5m"});
            if (rawQuery2.moveToFirst() && rawQuery2.getLong(0) > 0) {
                hashMap.put("feed_age_min", Double.valueOf(Math.round(((System.currentTimeMillis() - rawQuery2.getLong(0)) / 60000.0d) * 10.0d) / 10.0d));
            }
            rawQuery2.close();
        } catch (Throwable unused5) {
        }
        int i3 = 0;
        for (Map.Entry<String, String> entry2 : this.threecStates.entrySet()) {
            if (entry2.getValue() != null && entry2.getValue().contains("data kam")) {
                i3++;
            }
        }
        hashMap.put("data_low", Integer.valueOf(i3));
        try {
            JSONObject jSONObject = new JSONObject();
            Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT event, COUNT(*) FROM logs WHERE ts>=? AND event IN ('SETUP_DETECTED','SETUP_EXPIRED','SETUP_INVALIDATED','BREAKOUT_DETECTED','ORDER_EXECUTED','ENTRY_BLOCKED','COUNCIL_BLOCKED','HEAT_CAP_BLOCKED','BUCKET_CAP_BLOCKED','SAFE_MODE_ON','FEE_EDGE_SKIP') GROUP BY event", new String[]{String.valueOf(System.currentTimeMillis() - 86400000)});
            while (rawQuery3.moveToNext()) {
                jSONObject.put(rawQuery3.getString(0), rawQuery3.getInt(1));
            }
            rawQuery3.close();
            hashMap.put("no_trade_report", jSONObject);
        } catch (Throwable unused6) {
        }
        return hashMap;
    }

    public static class ObZone {
        public double bottom;
        public boolean bullish;
        public int idx;
        public boolean mitigated;
        public double top;

        ObZone(int i, double d, double d2, boolean z, boolean z2) {
            this.idx = i;
            this.top = d;
            this.bottom = d2;
            this.bullish = z;
            this.mitigated = z2;
        }
    }

    public static double[] prevDayHighLow(List<Candle> list) {
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        for (Candle candle : list) {
            long j = candle.ts / 86400000;
            double[] dArr = (double[]) linkedHashMap.get(Long.valueOf(j));
            if (dArr == null) {
                linkedHashMap.put(Long.valueOf(j), new double[]{candle.h, candle.l});
            } else {
                if (candle.h > dArr[0]) {
                    dArr[0] = candle.h;
                }
                if (candle.l < dArr[1]) {
                    dArr[1] = candle.l;
                }
            }
        }
        if (linkedHashMap.size() < 2) {
            return null;
        }
        Long l = null;
        Long lPrev = null;
        for (Object l2o : linkedHashMap.keySet()) {
            Long l2 = (Long) l2o;
            lPrev = l;
            l = l2;
        }
        if (lPrev == null) {
            return null;
        }
        return (double[]) linkedHashMap.get(lPrev);
    }

    public static double[] prevWeekHighLow(List<Candle> list) {
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        for (Candle candle : list) {
            long j = (candle.ts / 86400000) / 7;
            double[] dArr = (double[]) linkedHashMap.get(Long.valueOf(j));
            if (dArr == null) {
                linkedHashMap.put(Long.valueOf(j), new double[]{candle.h, candle.l});
            } else {
                if (candle.h > dArr[0]) {
                    dArr[0] = candle.h;
                }
                if (candle.l < dArr[1]) {
                    dArr[1] = candle.l;
                }
            }
        }
        if (linkedHashMap.size() < 2) {
            return null;
        }
        Long l = null;
        Long lPrev = null;
        for (Object l2o : linkedHashMap.keySet()) {
            Long l2 = (Long) l2o;
            lPrev = l;
            l = l2;
        }
        if (lPrev == null) {
            return null;
        }
        return (double[]) linkedHashMap.get(lPrev);
    }

    public static String sweepStatus(List<Candle> list, double d, boolean z) {
        if (d <= 0.0d || Double.isNaN(d) || list.isEmpty()) {
            return "NONE";
        }
        long j = list.get(list.size() - 1).ts / 86400000;
        boolean z2 = false;
        for (int size = list.size() - 1; size >= 0; size--) {
            Candle candle = list.get(size);
            if (candle.ts / 86400000 != j) {
                break;
            }
            if (z) {
                if (candle.h <= d) {
                }
                z2 = true;
            } else {
                if (candle.l >= d) {
                }
                z2 = true;
            }
        }
        if (!z2) {
            return "ACTIVE";
        }
        double d2 = list.get(list.size() - 1).c;
        if (z) {
            if (d2 > d) {
                return "BROKEN";
            }
            return "SWEEP";
        }
        if (d2 < d) {
            return "BROKEN";
        }
        return "SWEEP";
    }

    public static List<ObZone> orderBlocks(List<Candle> list, int i) {
        int i2 = 0;
        double d = 0.0d;
        ArrayList arrayList = null;
        int i3 = 0;
        int i4 = 0;
        boolean z = false;
        int i5 = 0;
        boolean z2 = false;
        int i6 = i;
        ArrayList arrayList2 = new ArrayList();
        int size = list.size();
        if (size < i6 + 5) {
            return arrayList2;
        }
        double atr = atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return arrayList2;
        }
        double d2 = atr * 0.7d;
        LinkedHashSet linkedHashSet = new LinkedHashSet();
        int i7 = size - 1;
        while (i7 >= i6 && arrayList2.size() < 8) {
            Candle candle = list.get(i7);
            int max = Math.max(0, i7 - i6);
            double d3 = -1.7976931348623157E308d;
            double d4 = Double.MAX_VALUE;
            int i8 = -1;
            int i9 = -1;
            while (max < i7) {
                ArrayList arrayList3 = arrayList2;
                if (list.get(max).h > d3) {
                    d3 = list.get(max).h;
                    i8 = max;
                }
                if (list.get(max).l < d4) {
                    d4 = list.get(max).l;
                    i9 = max;
                }
                max++;
                arrayList2 = arrayList3;
            }
            ArrayList arrayList4 = arrayList2;
            if (i8 < 0 || i9 < 0) {
                i2 = size;
                d = d2;
                arrayList = arrayList4;
            } else {
                if (i7 - i8 >= CONSEC_LOSS_DEFAULT) {
                    int i10 = size;
                    if (candle.c > d3) {
                        int i11 = i8 + 1;
                        while (true) {
                            if (i11 > i7) {
                                i5 = i8;
                                i11 = -1;
                                break;
                            }
                            i5 = i8;
                            if (list.get(i11).c > list.get(i11).o && list.get(i11).c - list.get(i11).o >= d2) {
                                break;
                            }
                            i11++;
                            i8 = i5;
                        }
                        if (i11 > 0) {
                            while (true) {
                                i11--;
                                int i12 = i5;
                                if (i11 < i12) {
                                    break;
                                }
                                i5 = i12;
                                if (list.get(i11).c < list.get(i11).o) {
                                    if (linkedHashSet.add(Integer.valueOf(i11))) {
                                        double d5 = list.get(i11).h;
                                        double d6 = list.get(i11).l;
                                        int i13 = i7 + 1;
                                        while (true) {
                                            if (i13 >= i10) {
                                                i3 = i10;
                                                d = d2;
                                                z2 = false;
                                                break;
                                            }
                                            i3 = i10;
                                            d = d2;
                                            if (list.get(i13).l <= d5) {
                                                z2 = true;
                                                break;
                                            }
                                            i13++;
                                            i10 = i3;
                                            d2 = d;
                                        }
                                        arrayList = arrayList4;
                                        arrayList.add(new ObZone(i11, d5, d6, true, z2));
                                    }
                                }
                            }
                        }
                    }
                    i3 = i10;
                } else {
                    i3 = size;
                }
                d = d2;
                arrayList = arrayList4;
                if (i7 - i9 >= CONSEC_LOSS_DEFAULT && candle.c < d4) {
                    int i14 = i9 + 1;
                    while (true) {
                        if (i14 > i7) {
                            i4 = -1;
                            break;
                        }
                        if (list.get(i14).c < list.get(i14).o && list.get(i14).o - list.get(i14).c >= d) {
                            i4 = i14;
                            break;
                        }
                        i14++;
                    }
                    if (i4 > 0) {
                        int i15 = i4 - 1;
                        /* v1.2.1 HANG FIX: pehle sirf bearish branch me i15-- tha — bullish candle par
                           zone add hone ke baad i15 ruk jata tha aur add() dobara false return karti
                           thi -> INFINITE LOOP (Poora /api/indicators + Lab backtest + AI trainer hang).
                           Ab har branch me index aage badhta hai — loop guaranteed terminate hota hai. */
                        while (i15 >= i9) {
                            if (list.get(i15).c <= list.get(i15).o) {
                                i15--;
                            } else {
                                if (linkedHashSet.add(Integer.valueOf(i15))) {
                                    double d7 = list.get(i15).h;
                                    double d8 = list.get(i15).l;
                                    int i16 = i7 + 1;
                                    i2 = i3;
                                    while (true) {
                                        if (i16 >= i2) {
                                            z = false;
                                            break;
                                        }
                                        if (list.get(i16).h >= d8) {
                                            z = true;
                                            break;
                                        }
                                        i16++;
                                    }
                                    arrayList.add(new ObZone(i15, d7, d8, false, z));
                                }
                                i15--;
                            }
                        }
                    }
                }
                i2 = i3;
            }
            i7--;
            i6 = i;
            arrayList2 = arrayList;
            size = i2;
            d2 = d;
        }
        ArrayList arrayList5 = arrayList2;
        arrayList5.sort(new Comparator() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda7
            @Override // java.util.Comparator
            public final int compare(Object obj, Object obj2) {
                return EngineCore.lambda$orderBlocks$6((EngineCore.ObZone) obj, (EngineCore.ObZone) obj2);
            }
        });
        return arrayList5;
    }

    static /* synthetic */ int lambda$orderBlocks$6(ObZone obZone, ObZone obZone2) {
        return obZone2.idx - obZone.idx;
    }

    public static StructEvent structureWalk(List<Candle> list, int i) {
        StructEvent structEvent = null;
        int size = list.size();
        StructEvent structEvent2 = null;
        if (size < i + 5) {
            return null;
        }
        for (int i2 = i; i2 < size; i2++) {
            int i3 = -1;
            double d = Double.MAX_VALUE;
            double d2 = -1.7976931348623157E308d;
            int i4 = -1;
            for (int max = Math.max(0, i2 - i); max < i2; max++) {
                if (list.get(max).h > d2) {
                    d2 = list.get(max).h;
                    i3 = max;
                }
                if (list.get(max).l < d) {
                    d = list.get(max).l;
                    i4 = max;
                }
            }
            if (i3 >= 0 && i4 >= 0) {
                Candle candle = list.get(i2);
                if (i2 - i3 >= CONSEC_LOSS_DEFAULT && candle.c > d2) {
                    structEvent = new StructEvent();
                    structEvent.dir = "BULL";
                    structEvent.idx = i2;
                    structEvent.level = d2;
                    structEvent.kind = (structEvent2 == null || !"BULL".equals(structEvent2.dir)) ? "MSS" : "BOS";
                } else if (i2 - i4 >= CONSEC_LOSS_DEFAULT && candle.c < d) {
                    structEvent = new StructEvent();
                    structEvent.dir = "BEAR";
                    structEvent.idx = i2;
                    structEvent.level = d;
                    structEvent.kind = (structEvent2 == null || !"BEAR".equals(structEvent2.dir)) ? "MSS" : "BOS";
                }
                structEvent2 = structEvent;
            }
        }
        return structEvent2;
    }

    public static double[] latestFvg(List<Candle> list) {
        int size = list.size();
        for (int i = size - 1; i >= 2; i--) {
            Candle candle = list.get(i - 2);
            Candle candle2 = list.get(i);
            if (candle2.l > candle.h) {
                for (int i2 = i + 1; i2 < size; i2++) {
                    if (list.get(i2).l > candle.h) {
                    }
                }
                return new double[]{candle.h, candle2.l, 1.0d};
            }
            if (candle2.h < candle.l) {
                for (int i3 = i + 1; i3 < size; i3++) {
                    if (list.get(i3).h >= candle.l) {
                        break;
                    }
                }
                return new double[]{candle.l, candle2.h, -1.0d};
            }
        }
        return null;
    }

    public static String[] sessionNow(long j) {
        Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("America/New_York"));
        calendar.setTimeInMillis(j);
        int i = (calendar.get(11) * 60) + calendar.get(12);
        if (i >= 1200 || i < 0) {
            return new String[]{"ASIAN", "no"};
        }
        if (i >= 120 && i < 300) {
            return new String[]{"LONDON", "yes"};
        }
        if (i >= 420 && i < 600) {
            return new String[]{"NEW YORK", "yes"};
        }
        if (i >= 600 && i < 720) {
            return new String[]{"LONDON CLOSE", "no"};
        }
        return new String[]{"OFF-SESSION", "no"};
    }

    public Map<String, Object> indicatorSnapshot(String str) {
        char c = '\u0000';
        Object obj = null;
        HashMap hashMap = new HashMap();
        List<Candle> loadCandles = loadCandles(str);
        if (loadCandles.size() < 60) {
            hashMap.put("ok", false);
            hashMap.put("reason", "not enough 1m candles for " + str + " (need 60, have " + loadCandles.size() + ")");
            return hashMap;
        }
        HashMap hashMap2 = new HashMap();
        Candle candle = loadCandles.get(loadCandles.size() - 1);
        hashMap2.put("price", Double.valueOf(candle.c));
        hashMap2.put("atr14", Double.valueOf(atr(loadCandles, 14)));
        double ema = ema(loadCandles, 50);
        double ema2 = ema(loadCandles, 200);
        double rsi = rsi(loadCandles, 14);
        double vwap = vwap(loadCandles);
        if (!Double.isNaN(ema)) {
            hashMap2.put("ema50", Double.valueOf(ema));
        }
        if (!Double.isNaN(ema2) && ema2 > 0.0d) {
            hashMap2.put("ema200", Double.valueOf(ema2));
            hashMap2.put("ema200DistPct", Double.valueOf(((candle.c - ema2) / ema2) * 100.0d));
        }
        if (!Double.isNaN(rsi)) {
            hashMap2.put("rsi14", Double.valueOf(rsi));
        }
        if (!Double.isNaN(vwap) && vwap > 0.0d) {
            hashMap2.put("vwap", Double.valueOf(vwap));
        }
        double[] adxAt = StrategyPack.adxAt(loadCandles, 14, loadCandles.size() - 1);
        if (adxAt != null) {
            hashMap2.put("adx14", Double.valueOf(adxAt[0]));
        }
        double[] supertrend = supertrend(loadCandles);
        if (supertrend != null) {
            hashMap2.put("stDir", Integer.valueOf((int) supertrend[1]));
        }
        double[] prevDayHighLow = prevDayHighLow(loadCandles);
        if (prevDayHighLow != null) {
            hashMap2.put("pdh", Double.valueOf(prevDayHighLow[0]));
            hashMap2.put("pdl", Double.valueOf(prevDayHighLow[1]));
            hashMap2.put("eqD", Double.valueOf((prevDayHighLow[0] + prevDayHighLow[1]) / 2.0d));
            hashMap2.put("pdhStatus", sweepStatus(loadCandles, prevDayHighLow[0], true));
            hashMap2.put("pdlStatus", sweepStatus(loadCandles, prevDayHighLow[1], false));
            hashMap2.put("premiumDiscount", candle.c > (prevDayHighLow[0] + prevDayHighLow[1]) / 2.0d ? "PREMIUM" : "DISCOUNT");
        }
        double[] prevWeekHighLow = prevWeekHighLow(loadCandles);
        if (prevWeekHighLow != null) {
            hashMap2.put("pwh", Double.valueOf(prevWeekHighLow[0]));
            hashMap2.put("pwl", Double.valueOf(prevWeekHighLow[1]));
            hashMap2.put("eqW", Double.valueOf((prevWeekHighLow[0] + prevWeekHighLow[1]) / 2.0d));
            hashMap2.put("pwhStatus", sweepStatus(loadCandles, prevWeekHighLow[0], true));
            hashMap2.put("pwlStatus", sweepStatus(loadCandles, prevWeekHighLow[1], false));
        }
        StructEvent structureWalk = structureWalk(loadCandles, 10);
        if (structureWalk != null) {
            hashMap2.put("structKind", structureWalk.kind);
            hashMap2.put("structDir", structureWalk.dir);
            hashMap2.put("structLevel", Double.valueOf(structureWalk.level));
        }
        List<ObZone> orderBlocks = orderBlocks(loadCandles, 10);
        JSONArray jSONArray = new JSONArray();
        for (ObZone obZone : orderBlocks) {
            try {
                jSONArray.put(new JSONObject().put("idx", obZone.idx).put("top", obZone.top).put("bottom", obZone.bottom).put("bull", obZone.bullish).put("mitigated", obZone.mitigated));
            } catch (Throwable unused) {
            }
        }
        hashMap2.put("orderBlocks", jSONArray);
        double[] latestFvg = latestFvg(loadCandles);
        if (latestFvg != null) {
            hashMap2.put("fvgTop", Double.valueOf(latestFvg[1]));
            hashMap2.put("fvgBottom", Double.valueOf(latestFvg[0]));
            hashMap2.put("fvgDir", Double.valueOf(latestFvg[2]));
        }
        if (candlePattern(loadCandles) != null) {
            c = 0;
            obj = candlePattern(loadCandles)[0];
        } else {
            c = 0;
            obj = "";
        }
        hashMap2.put("candlePattern", obj);
        String[] sessionNow = sessionNow(candle.ts);
        hashMap2.put("session", sessionNow[c]);
        hashMap2.put("killzone", sessionNow[1]);
        hashMap2.put("fearGreed", Integer.valueOf(this.fngValue));
        hashMap.put("ok", true);
        hashMap.put("symbol", str);
        hashMap.put("timeframe", "5m");
        hashMap.put("values", hashMap2);
        hashMap.put("library", SHAAKUNI_SUITE);
        return hashMap;
    }

    public void forceDiscovery() {
        Thread thread = new Thread(new Runnable() { // from class: com.aitradinglab.engine.EngineCore$$ExternalSyntheticLambda5
            @Override // java.lang.Runnable
            public final void run() {
                EngineCore.this.lambda$forceDiscovery$7();
            }
        }, "force-scan");
        thread.setDaemon(true);
        thread.start();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$forceDiscovery$7() {
        try {
            discover();
            fetchNews();
        } catch (Throwable th) {
            try {
                this.db.log("ERROR", "SYSTEM", "FORCE_SCAN_FAIL", String.valueOf(th));
            } catch (Exception unused) {
            }
        }
    }
}
