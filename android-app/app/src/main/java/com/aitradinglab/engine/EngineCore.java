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
import java.util.Locale;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/**
 * EngineCore v1.5 — 3C MASTER STRATEGY ENGINE + SPEED (owner request: "1 trade per sec"
 * = jitne setups fire hon utne trades foran; entry breakout ke ~10s ke andar).
 * Previously v1.4 — 3C MASTER STRATEGY ENGINE (owner request: "saari strategy delete,
 * sirf 3C chalao, daily loss/profit UNLIMITED").
 *
 * THE 3C STRATEGY (M5, mechanical, verbatim from the owner's MASTER TRAINING PROMPT):
 *   BUY  setup: C1 green, C2 green — each body >= 70% of its High-Low range;
 *               C3 red (any body/wick) that does NOT close below the lowest Low of C1+C2.
 *   SELL setup: C1 red, C2 red — each body >= 70%; C3 green that does NOT close
 *               above the highest High of C1+C2.
 *   Setup zone: highest High / lowest Low of the three setup candles.
 *   Entry window: the NEXT FIVE M5 candles only (5th included) — the breakout must
 *               happen there, else the setup expires. Candle-6 breakout is NOT valid.
 *   Invalidation: a window candle CLOSING beyond the protected boundary (BUY: zone
 *               low, SELL: zone high) cancels the setup. A wick alone never cancels.
 *               Breakout + close-beyond in the same candle = sequence unknown from
 *               OHLC -> setup is skipped, never guessed.
 *   Entry: stop-order simulation at the zone extreme (+ configured entry buffer).
 *   SL: opposite extreme of the setup (+ SL buffer). 1R = |entry - SL|.
 *   Management: at +1R the whole position's SL moves to breakeven; at +3R the whole
 *               position closes. No partial take profit.
 *   Risk: settings key risk_pct (default 1% of equity) — owner controlled.
 *
 * UNLIMITED (owner request): no daily loss halt, no daily profit cap, no drawdown
 *   kill switch, no trades-per-day cap, no concurrent-position cap, no
 *   consecutive-loss stop. News is display-only — it never blocks a 3C entry.
 *   Guards that remain are mechanical correctness only: one open position per
 *   symbol per account, one entry per setup.
 *
 * Strategy Lab (v1.2, kept): AI text/YouTube -> backtest -> paper -> owner approve
 *   -> live. v1.4 adds AUTO-EVOLVE: every 6h the AI proposes ONE new complementary
 *   strategy, backtests it on real candles and notifies the owner — "aur strategies
 *   banati raho". AI kabhi khud LIVE nahi jati, sirf owner approve karta hai.
 *
 * Data (v2.1 HALAL MT5): LIVE 5m candles for 27 HALAL COMMODITIES — public commodity
 *   futures feed (Yahoo chart API) ya optional MT5 bridge (PC par MetaTrader5 +
 *   mt5-bridge.py). Real market data — candles are never simulated. 24/7 scanner.
 * Universe (v2.1): halal commodities only (metals, energy, agri) — crypto/forex/
 *   indices/stocks owner ke hukum par removed. Discovery = universe maintenance.
 * News (15 min): RSS -> sentiment -> display only.
 */
public class EngineCore implements Runnable {
    // v2.1 — Binance retired: MT5 halal commodities feed (DATA section neeche).
    private static final String TF = "5m";                 // v4.5 OWNER SHIFT: poora system 5m timeframe (3C MASTER ka original M5 design)
    private static final long TF_MS = 5L * 60 * 1000;
    /** public for StrategyLab backtester */ public static final long TF_MS_PUB = TF_MS;
    /** v4.5 — PDF pack timeframe (owner: "pure system ko 5 min ke timeframe par shift kardo" — 15m se 5m). */
    static final String TF15 = "5m";
    static final long TF15_MS = 5L * 60 * 1000;
    private static final int ACTIVE_TOP = 40;      // v4.5: 5m scan tier (top-40 by volume) — 5m PDF pack ALL pairs rotate karta hai
    // ==== 3C STRATEGY CONSTANTS (MASTER PROMPT — kabhi change nahi without owner approval) ====
    public static final double THREEC_BODY_MIN = 0.70;  // C1 & C2 body >= 70% of High-Low range
    public static final int THREEC_WINDOW = 5;          // breakout window: next 5 M5 candles
    public static final double THREEC_TP_R = 3.0;       // take profit at +3R, whole position
    private static final double RISK_DEFAULT_PCT = 1.0; // v4.1: owner "risk should be 1 percent on a trade" (was 2.0)
    // ==== v1.7 PRO GUARD — professional protections (freqtrade-inspired) ====
    /** Commodity futures/CFD taker fee per side (0.05%) — paper P/L ab realistic.
     *  freqtrade/production bots hamesha fees model karte hain warna paper results
     *  real se 10-20% door hote hain. */
    public static final double TAKER_FEE = 0.0005;
    /** Consecutive-loss guard: itne SL losses ek symbol par = cooldown. */
    private static final int CONSEC_LOSS_DEFAULT = 3;
    private static final long CONSEC_LOSS_COOLDOWN_MS = 60L * 60 * 1000; // 1 ghanta

    private final Db db;
    private volatile boolean running = true;
    private String dataHost = "BINANCE-SPOT";      // v4.1: BINANCE-SPOT ya MT5-BRIDGE (status ke liye)
    private long lastDiscovery = 0, lastNews = 0, lastLoop = 0, lastEvolve = 0;
    private String lastConsensus = "";
    private int activeSymbols = 0;
    private long scanCount = 0;             // 24h scanner heartbeat counter
    private volatile long lastScanAt = 0;
    private volatile int fngValue = -1;     // crypto Fear & Greed (0-100), -1 = no data
    private long lastFng = 0;
    private long lastYt = 0;                // v1.2 YouTube channel watcher cadence
    private String lastPattern = "";        // last 3C event text (dashboard status)

    // ===== v1.4 STRATEGY LAB + 3C STATE =====
    public StrategyLab lab;                                                        // AI strategy pipeline
    /** v1.4 — single-element compat array: dominant 3C direction of the last scanned
     *  symbol (+1 BUY setup armed, -1 SELL setup armed, 0 none). The old int[35] vote
     *  register retired together with the 35-strategy consensus. */
    public volatile int[] lastVotes = new int[1];
    public volatile String lastVoteSym = "-";
    /** Per-symbol 3C state text for the dashboard ("BUY setup armed — window 2/5 ..."). */
    public final java.util.Map<String, String> threecStates = new HashMap<>();
    /** Logged 3C event keys (dedup — every event logs exactly once per setup). */
    private final java.util.LinkedHashSet<String> threecLogged = new java.util.LinkedHashSet<>();
    // ===== v1.7 PRO GUARD state =====
    /** Per-(uid:sym) cooldown until timestamp — SL loss ke baad naya entry block. */
    private final java.util.Map<String, Long> cooldownUntil = new HashMap<>();
    /** Cooldown-block log dedup (har cooldown period mein ek hi baar log ho). */
    private final java.util.Set<String> cooldownLogged = new java.util.HashSet<>();
    /** Daily kill-switch notification dedup (per UTC day). */
    private final java.util.Set<String> killLogged = new java.util.HashSet<>();

    // ===== v3.0 QUANT PRO state =====
    /** Per-symbol fetch backoff — fail hone par exponential (60s → max 15 min).
     *  Yahoo 429/storm par request storm nahi karenge (audit fix #4). */
    private final java.util.Map<String, Long> backoffUntil = new HashMap<>();
    /** SAFE MODE — feed outage: stale data par koi entry bhi nahi, SL/TP freeze
     *  (false trigger se bachne ke liye), owner ko ek hi baar notification. */
    private volatile boolean safeMode = false;
    private volatile long safeModeSince = 0;
    /** Degradation monitor cadence (30 min) + last check. */
    private long lastDegCheck = 0;
    /** Seasonality cache: sym -> {avg[12], hit[12], years} JSON (24h refresh). */
    private final java.util.Map<String, JSONObject> seasonCache = new HashMap<>();
    /** ML-lite (FreqAI-inspired) weights cache — logistic regression on closed trades. */
    private JSONObject mlWeights = null;
    private boolean mlLoaded = false;

    /** v1.4 — owner-controlled risk % of equity per trade (settings risk_pct, 0.1-20). */
    public double riskPct() {
        try {
            double v = Double.parseDouble(db.setting("risk_pct", String.valueOf(RISK_DEFAULT_PCT)));
            if (v < 0.1) v = 0.1;
            if (v > 20) v = 20;
            return v;
        } catch (Exception e) { return RISK_DEFAULT_PCT; }
    }

    /** v1.1 TUNED — taker fee as fraction per side (settings fee_bps, default 5 = 0.05%).
     *  PAPER sim: owner 0 set karke zero-fee sim chala sakta hai (honest label rahega). */
    public double takerFee() {
        try {
            double bps = Double.parseDouble(db.setting("fee_bps", "5"));
            if (bps < 0) bps = 0;
            if (bps > 100) bps = 100;
            return bps / 10000.0;
        } catch (Exception e) { return TAKER_FEE; }
    }

    /** v1.1 TURBO — notional cap as multiple of equity (settings lev_cap, default 0.95 = spot).
     *  PAPER sim: 2/3/5 = paper leverage presets (owner TURBO control). */
    public double levCap() {
        try {
            double v = Double.parseDouble(db.setting("lev_cap", "0.95"));
            if (v < 0.1) v = 0.1;
            if (v > 10) v = 10;
            return v;
        } catch (Exception e) { return 0.95; }
    }

    /** v4.1 OWNER RULE: "min trades 25 ho phir consensus percentage par increase ho jaye
     *  aur risk should be 1 percent on a trade".
     *  - har trade ka base risk = riskPct() (default 1%)
     *  - jab tak strategy ke 25 CLOSED trades nahi, size base par hi rehta hai
     *  - 25 ke baad scale = winPct / 50 (50% WR = 1x, 75% WR = 1.5x), cap 2x
     *  Loss-heavy strategy (winPct < 25) par scale < 1 — size khud kam ho jata hai. */
    public static final int MIN_TRADES_BEFORE_SCALING = 25;

    public double dynamicRiskPct(String strategyKey) {
        double base = riskPct();
        int n = 0, w = 0;
        try {
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT COUNT(*), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) FROM trades WHERE strategy=? AND status='CLOSED'",
                    new String[]{strategyKey});
            if (c.moveToFirst()) { n = c.getInt(0); w = c.getInt(1); }
            c.close();
        } catch (Throwable ignored) { }
        if (n < MIN_TRADES_BEFORE_SCALING) return base;
        double winPct = w * 100.0 / n;
        double scale = Math.max(0.5, Math.min(2.0, winPct / 50.0));
        return Math.min(20.0, base * scale);
    }

    /** Lab/trade UI ke liye: current scaling state (trades done, win%, scale). */
    public String scalingInfo(String strategyKey) {
        int n = 0, w = 0;
        try {
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT COUNT(*), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) FROM trades WHERE strategy=? AND status='CLOSED'",
                    new String[]{strategyKey});
            if (c.moveToFirst()) { n = c.getInt(0); w = c.getInt(1); }
            c.close();
        } catch (Throwable ignored) { }
        if (n < MIN_TRADES_BEFORE_SCALING) return "base risk " + riskPct() + "% (" + n + "/" + MIN_TRADES_BEFORE_SCALING + " trades — scaling baad mein)";
        double winPct = n > 0 ? w * 100.0 / n : 0;
        double scale = Math.max(0.5, Math.min(2.0, winPct / 50.0));
        return "consensus " + Math.round(winPct) + "% → " + Math.round(scale * 100) + "% size (" + n + " trades)";
    }

    /** Configurable entry/SL buffer as percent of price (settings, default 0 = pure levels). */
    private double bufSetting(String key) {
        try {
            double v = Double.parseDouble(db.setting(key, "0"));
            if (v < 0) v = 0;
            if (v > 1) v = 1;
            return v / 100.0;
        } catch (Exception e) { return 0; }
    }

    // ===== v1.7 PRO GUARD settings (owner-configurable, freqtrade-inspired) =====

    /** SL loss ke baad us symbol par naya entry kitni der block (minutes, default 15, 0=off). */
    public int cooldownMin() {
        try {
            int v = (int) Double.parseDouble(db.setting("cooldown_min", "15"));
            if (v < 0) v = 0;
            if (v > 240) v = 240;
            return v;
        } catch (Exception e) { return 15; }
    }

    /** Consecutive SL losses ek symbol par = us symbol par 1 ghanta pause (default 3, 0=off). */
    public int consecLossN() {
        try {
            int v = (int) Double.parseDouble(db.setting("consec_loss", String.valueOf(CONSEC_LOSS_DEFAULT)));
            if (v < 0) v = 0;
            if (v > 10) v = 10;
            return v;
        } catch (Exception e) { return CONSEC_LOSS_DEFAULT; }
    }

    /** Daily kill switch: aaj ka realized P/L equity ke is % se neeche gaya to aaj aur
     *  naye entries nahi (default 0 = OFF — owner ne UNLIMITED manga tha, opt-in guard). */
    public double dailyKillPct() {
        try {
            double v = Double.parseDouble(db.setting("daily_kill_pct", "0"));
            if (v < 0) v = 0;
            if (v > 90) v = 90;
            return v;
        } catch (Exception e) { return 0; }
    }

    // ===== v3.0 QUANT PRO settings (P0-P4 roadmap — sab owner-controlled) =====

    /** Slippage/spread model (bps per side): fills ab realistic — BUY entry thoda upar,
     *  exits thoda neeche. Default 2 bps (0.02%) — futures spread+slip ka modest model.
     *  0 = off (purane exact-fill behavior). NautilusTrader fill-model parity. */
    public double slipBps() {
        try {
            double v = Double.parseDouble(db.setting("slip_bps", "2"));
            if (v < 0) v = 0; if (v > 50) v = 50;
            return v;
        } catch (Exception e) { return 2; }
    }

    /** Portfolio HEAT CAP — total open risk (|entry-sl|*qty) equity ka max %.
     *  Default 0 = OFF (owner UNLIMITED). Freqtrade max_open_trades + LEAN risk parity.
     *  27 syms x 2% = 54% simultaneous risk hota tha — owner chahe to 6-12% cap laga de. */
    public double heatMaxPct() {
        try {
            double v = Double.parseDouble(db.setting("heat_max_pct", "0"));
            if (v < 0) v = 0; if (v > 100) v = 100;
            return v;
        } catch (Exception e) { return 0; }
    }

    /** Bucket cap (METAL/ENERGY/AGRI correlated group) — ek bucket ka total open risk
     *  is % se zyada nahi. Default 0 = OFF. USOIL/UKOIL/NGAS ek hi direction mein
     *  3 positions = 6% risk ek hi macro bet par — bucket cap isse rokta hai. */
    public double bucketMaxPct() {
        try {
            double v = Double.parseDouble(db.setting("bucket_max_pct", "0"));
            if (v < 0) v = 0; if (v > 100) v = 100;
            return v;
        } catch (Exception e) { return 0; }
    }

    /** Signal Council minimum confidence (0-100). 0 = OFF (3C har valid setup par
     *  entry karega). >0 ho to council score kam wale entries block — 3C RULES KHUD
     *  NAHI BADLTE, ye sirf owner ka opt-in quality gate hai. */
    public int councilMin() {
        try {
            int v = (int) Double.parseDouble(db.setting("council_min", "0"));
            if (v < 0) v = 0; if (v > 95) v = 95;
            return v;
        } catch (Exception e) { return 0; }
    }

    /** EVENT GATE (FinRL turbulence pattern): HIGH-impact news (OPEC/CPI/FOMC) aakhri
     *  60 min mein aayi ho to naye entries pause (default OFF). Stop orders gap events
     *  par blind fill hote hain — ye unhe bachata hai. Opt-in. */
    public boolean eventGateOn() { return "1".equals(db.setting("event_gate", "0")); }

    /** Degraded AI strategy auto-pause (default OFF — sirf alert bhejta hai). */
    public boolean autoPauseDegraded() { return "1".equals(db.setting("auto_pause", "0")); }

    /** MT5 bridge LIVE MIRROR — paper trade ke saath bridge par real order bhejo
     *  (owner-only, default OFF). Sirf tab jab bridge healthy ho. */
    public boolean bridgeLive() { return "1".equals(db.setting("bridge_live", "0")); }

    /** CME maintenance halt (17:00-18:00 ET) mein naye entries band (default OFF).
     *  Mechanical session hygiene — halt mein spreads phantom wide hote hain. */
    public boolean sessionFilterOn() { return "1".equals(db.setting("session_filter", "0")); }

    /** Bridge mirror lot size (real MT5 lots per paper trade, default 0.01). */
    public double bridgeLots() {
        try {
            double v = Double.parseDouble(db.setting("bridge_lots", "0.01"));
            if (v < 0.01) v = 0.01; if (v > 100) v = 100;
            return v;
        } catch (Exception e) { return 0.01; }
    }

    // v4.4.1 — PRO FILTER PACK POORA REMOVE (owner order: "Pro filter remove kardo — is ki
    // waja se buhut saari trades place hi nahi kar raha"). ProRdMin/proEmaFilter/proAtrFloor/
    // proVolFilter getters + proFilter3C gate deleted. detect3C se guzra HAR setup ab armed
    // hota hai — koi quality gate nahi. Indicators sirf SETUP DNA (ML features) ke liye.
    /** v1.8 — dashboard candlestick chart ke liye recent 5m candles (closed, oldest→newest). */
    public List<Candle> recentCandles(String symbol, int n) {
        List<Candle> out = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT "+Math.max(1, Math.min(500, n)),
                new String[]{symbol, TF});
        while (c.moveToNext()) {
            Candle k = new Candle();
            k.ts = c.getLong(0); k.o = c.getDouble(1); k.h = c.getDouble(2);
            k.l = c.getDouble(3); k.c = c.getDouble(4); k.v = c.getDouble(5);
            out.add(k);
        }
        c.close();
        java.util.Collections.reverse(out);
        return out;
    }

    /** v1.4 — the ONE master strategy (35-strategy consensus retired by owner request). */
    public static final String[][] STRATEGY_META = {
            {"3C Breakout (M1) — MASTER", "Price action"},
            {"PDF PACK S1-S9 (5m, ALL pairs)", "Mechanical"},
            {"SHAAKUNI SSM playbooks x5", "SMC"}
    };

    public EngineCore(Db db) {
        this.db = db;
        seedStaticInstruments();
        try { lab = new StrategyLab(appContext(), db, this); } catch (Throwable t) { lab = null; }
    }

    /** app context for Notifier (set once by ServerService via appContext()). */
    private static android.content.Context appCtxRef;
    public static void appContext(android.content.Context c) { appCtxRef = c; }
    private static android.content.Context appContext() { return appCtxRef; }

    /** Public klines fetch for the Strategy Lab backtester (v2.1 MT5 commodities feed).
     *  force=true — backtest rate-limit bypass karta hai. */
    public List<Candle> klinesFor(String symbol, int limit) { return fetchKlines(symbol, limit, true); }

    public void stop() { running = false; }
    public boolean isRunning() { return running; }

    // ================== MAIN LOOP ==================
    @Override public void run() {
        db.log("INFO", "SYSTEM", "ENGINE_START", "v3.0 QUANT PRO — all 5 upgrades: [P1 PRO RISK] portfolio heat + bucket caps (opt-in), slippage/spread model, SAFE MODE stale guard, feed backoff+retry, TRUE drawdown (peak ratchet), index-window session-gap fix, persistent guards | [P2 HONEST LAB] fees+IS/OOS walk-forward+Monte Carlo in Lab backtest, EMA200 SMA-seed fix | [P3 EDGE ANALYTICS] journal R/MFE/MAE/TCA, daily P&L, per-symbol, monthly heatmap, seasonality | [P4 AI QUANT] Signal Council (4 analysts, tag+opt-in gate), ML-lite (FreqAI-inspired logistic retrain), degradation monitor, event gate | [P5 LIVE READY] order lifecycle (orders table), MT5 bridge LIVE MIRROR (owner opt-in) | 3C MASTER rules UNTOUCHED | risk " + riskPct() + "% | UNLIMITED daily P/L default — kill/heat/event sab opt-in");


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
        // v1.4 ONE-TIME MIGRATION — 3C era. Old ATR-era open trades are cancelled because
        // management semantics changed (BE at +1R, close ALL at +3R, 5m candles); stale
        // 1m candle history is purged so every symbol rebuilds on real 5m data.
        if (!"1".equals(db.setting("v14_3c_migration", "0"))) {
            long t0 = System.currentTimeMillis();
            try {
                db.getWritableDatabase().execSQL(
                        "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'",
                        new Object[]{t0});
                db.getWritableDatabase().execSQL("DELETE FROM candles WHERE tf<>'" + TF + "'");
                db.setSetting("v14_3c_migration", "1");
                db.log("INFO", "SYSTEM", "MIGRATION_3C", "v1.4 — 35-strategy consensus RETIRED, 3C MASTER (M5) installed; old open trades cancelled, 1m candles purged. Daily loss/profit now UNLIMITED (owner request).");
            } catch (Throwable t) {
                db.log("ERROR", "SYSTEM", "MIGRATION_3C_FAIL", String.valueOf(t));
            }
        }
        // v4.5 ONE-TIME MIGRATION — 5m system shift (owner: "pure system 5m timeframe").
        // 1m/15m candle history purge + open trades cancel (unke setups purane TF par
        // bane the — management semantics 5m par alag). Balances untouched.
        if (!"1".equals(db.setting("v45_tf5m_migration", "0"))) {
            long t0 = System.currentTimeMillis();
            try {
                db.getWritableDatabase().execSQL(
                        "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE status='OPEN'",
                        new Object[]{t0});
                db.getWritableDatabase().execSQL("DELETE FROM candles WHERE tf<>'" + TF + "'");
                db.setSetting("v45_tf5m_migration", "1");
                db.log("INFO", "SYSTEM", "MIGRATION_5M", "v4.5 — poora system 5m timeframe (3C + PDF pack + scan). Open trades cancelled (purane TF setups), 1m/15m candles purged. Balances unchanged.");
            } catch (Throwable t) {
                db.log("ERROR", "SYSTEM", "MIGRATION_5M_FAIL", String.valueOf(t));
            }
        }
        // v3.0 — persistent PRO GUARD state restore (watchdog restart cooldowns wipe fix)
        loadGuardState();
        while (running) {

            try {
                long now = System.currentTimeMillis();
                if (now - lastLoop >= 10_000) { loop(); lastLoop = now; }   // v1.5 — 30s→10s: breakout se entry ~10s ke andar
                if (now - lastDiscovery >= 30 * 60_000) { discover(); lastDiscovery = now; }
                if (now - lastNews >= 15 * 60_000) { fetchNews(); lastNews = now; }
                if (now - lastFng >= 60 * 60_000) { fetchFearGreed(); lastFng = now; }
                if (now - lastYt >= 15 * 60_000) {          // v1.2 — watch subscribed YouTube channel
                    lastYt = now;
                    if (lab != null) { try { lab.watchYouTube(); } catch (Throwable t) { db.log("ERROR", "LAB", "YT_WATCH_FAIL", String.valueOf(t)); } }
                }
                if (now - lastEvolve >= 6L * 3600_000) {   // v1.4 — AI har 6h mein ek nayi strategy propose karta hai
                    lastEvolve = now;
                    if (lab != null) { try { lab.autoEvolve(); } catch (Throwable t) { db.log("ERROR", "LAB", "EVOLVE_FAIL", String.valueOf(t)); } }
                }
                try { aiTrainTick(); } catch (Throwable ignored) { }   // v4.4 — AI auto-train (boot + har 24h)
                Thread.sleep(2000);

            } catch (Throwable t) {
                db.log("ERROR", "SYSTEM", "LOOP_ERROR", String.valueOf(t));
                try { Thread.sleep(5000); } catch (InterruptedException ignored) { return; }
            }
        }
        db.log("INFO", "SYSTEM", "ENGINE_STOP", "engine stopped");
    }

    private void loop() {
        long nowL = System.currentTimeMillis();
        if (nowL - lastDegCheck >= 30 * 60_000) {              // v3.0 — degradation + drift monitor (30 min)
            lastDegCheck = nowL;
            degradationCheck();
        }
        String engineOn = db.setting("engine_on", "1");
        if (!"1".equals(engineOn)) { lastConsensus = "engine off"; return; }
        rollDay();
        manageOpenTrades();
        refreshCandles();
        scanAndTrade();
        try { scanPdfPack(); } catch (Throwable t) { db.log("ERROR", "PACK", "SCAN_FAIL", String.valueOf(t)); }   // v4.5 PDF pack (5m, ALL pairs)
        try { scanPlaybook(); } catch (Throwable t) { db.log("ERROR", "PB", "SCAN_FAIL", String.valueOf(t)); }   // v1.0 5M PLAYBOOK (guide S1-S4, BTC/ETH/BNB/SOL)
        try { scanX7(); } catch (Throwable t) { db.log("ERROR", "X7", "SCAN_FAIL", String.valueOf(t)); }   // v1.1 TUNED — X7 REGIME FADE (replay-verified)
        snapshotEquity();
        try { selfLearnTick(); } catch (Throwable ignored) { }   // v4.4 — har 25 closed trades par AI re-weight
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

    // v1.4 — dailyHalted() and checkDrawdownKill() REMOVED by owner request:
    // daily loss/profit is UNLIMITED. rollDay() stays only to keep the dashboard's
    // dayPnlPct counter honest (it no longer halts anything).

    // ================== DATA (v4.1 BINANCE SPOT FEED) ==================
    public static class Candle { long ts; double o, h, l, c, v; }

    /** v4.0+ — BINANCE SPOT universe (owner request: crypto 7 pairs, 1m candles).
     *  REAL exchange candles — api.binance.com/api/v3/klines, 24/7 market (band nahi hota).
     *  Optional MT5 bridge ab fallback nahi — sirf Binance public feed primary hai;
     *  bridge setting abhi bhi kaam karta hai agar owner khud set kare. */
    static final java.util.Map<String, String> BINANCE_PAIRS = new java.util.LinkedHashMap<>();
    static {
        BINANCE_PAIRS.put("BTCUSDT", "BTC/USDT — Bitcoin (MAJOR)");
        BINANCE_PAIRS.put("ETHUSDT", "ETH/USDT — Ethereum (MAJOR)");
        BINANCE_PAIRS.put("BNBUSDT", "BNB/USDT — BNB (MAJOR)");
        BINANCE_PAIRS.put("SOLUSDT", "SOL/USDT — Solana (MAJOR)");
        BINANCE_PAIRS.put("XRPUSDT", "XRP/USDT — XRP (RETAIL)");
        BINANCE_PAIRS.put("DOGEUSDT", "DOGE/USDT — Dogecoin (RETAIL)");
        BINANCE_PAIRS.put("ADAUSDT", "ADA/USDT — Cardano (RETAIL)");
    }
    private static final String BINANCE_HOST = "https://api.binance.com";

    // ================== v4.4 ALL-BINANCE UNIVERSE (owner: "saare binance ke coins daalo, baki sab delete") ==================
    /** symbol → BINANCE tradable cache (discover()/syncBinanceUniverse() refresh karta hai). */
    final java.util.Set<String> binanceOkCache = java.util.Collections.synchronizedSet(new java.util.HashSet<>());
    /** Stable-stable pairs exclude (USDC/TUSD/FDUSD... vs USDT — real coins chahiye). */
    static final java.util.Set<String> STABLE_BASES = new java.util.HashSet<>(java.util.Arrays.asList(
            "USDC", "TUSD", "FDUSD", "BUSD", "DAI", "USDP", "EUR", "GBP", "TRY", "BRL", "ARS",
            "UAH", "JPY", "AEUR", "USDS", "SUSD", "XUSD", "USD1", "EURI", "GYEN", "PAXG"));

    /** Volume rank → risk bucket: 1-10 MAJOR, 11-60 RETAIL, 61+ ALTCOIN. */
    static String bucketForRank(int rank) {
        if (rank <= 10) return "MAJOR";
        if (rank <= 60) return "RETAIL";
        return "ALTCOIN";
    }
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
            // v3.0 EXPONENTIAL BACKOFF (audit fix #4): fail hue symbol par 60s → 2x → max
            // 15 min tak request nahi — Yahoo 429 storm nahi karenge.
            Long bo = backoffUntil.get(symbol);
            if (bo != null && System.currentTimeMillis() < bo) return new ArrayList<>();
        }
        List<Candle> out = fetchFromBinance(symbol, limit);
        if (out == null || out.isEmpty()) {
            List<Candle> y = fetchFromBridge(symbol, limit);
            if (y != null && !y.isEmpty()) out = y;
        }
        // v4.1 — one immediate retry (binance ↔ bridge cross-fallback), phir backoff
        if (out == null || out.isEmpty()) {
            List<Candle> retry = fetchFromBridge(symbol, limit);
            if (retry == null || retry.isEmpty()) retry = fetchFromBinance(symbol, limit);
            if (retry != null && !retry.isEmpty()) {
                out = retry;
                backoffUntil.remove(symbol);
            } else {
                Long prev = backoffUntil.get(symbol);
                long now = System.currentTimeMillis();
                long next = (prev != null && prev > now) ? Math.min((prev - now) * 2, 15L * 60_000) : 60_000L;
                backoffUntil.put(symbol, now + next);
            }
        } else backoffUntil.remove(symbol);
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
                if (!candleOk(cd.ts, cd.o, cd.h, cd.l, cd.c, cd.v)) continue;   // v4.4.2 NaN/zero guard
                out.add(cd);
            }
            return out;
        } catch (Exception e) { return null; }
    }

    /** BINANCE klines fetch (v4.1 primary feed). Response:
     *  [[openTime, open, high, low, close, volume, closeTime, ...], ...] — last row
     *  in-progress candle hota hai (Binance live deta hai). */
    private List<Candle> fetchFromBinance(String symbol, int limit) { return fetchFromBinance(symbol, limit, TF); }

    /** v4.5 — interval-aware (5m live + 5m PDF pack + 1d AI training).
     *  Universe gate: BINANCE_PAIRS ya instruments me exchange=BINANCE (ALL coins). */
    private List<Candle> fetchFromBinance(String symbol, int limit, String interval) {
        if (!binanceTradable(symbol)) return null;
        try {
            String body = httpGetUrl(BINANCE_HOST + "/api/v3/klines?symbol=" + symbol
                    + "&interval=" + interval + "&limit=" + Math.min(limit, 1000), 12000);
            if (body == null) return null;
            return parseBinanceKlines(body);
        } catch (Exception e) { return null; }
    }

    /** v4.4 — ALL-BINANCE gate (static 7 seed + exchangeInfo-discovered pairs). */
    private boolean binanceTradable(String symbol) {
        if (BINANCE_PAIRS.containsKey(symbol)) return true;
        synchronized (binanceOkCache) { return binanceOkCache.contains(symbol); }
    }

    /** v4.4.2 NaN/zero guard — candle sirf tab DB me jayegi jab OHLC finite + positive ho
     *  aur high/low ordering sahi ho. NaN DB me ghusa to indicators + entries sab poison. */
    static boolean candleOk(long ts, double o, double h, double l, double c, double v) {
        if (ts <= 0) return false;
        if (!(o > 0) || !(h > 0) || !(l > 0) || !(c > 0)) return false;   // NaN/0/neg — NaN>0 hamesha false
        if (!(v >= 0)) return false;
        if (h < Math.max(o, c) - 1e-9 || l > Math.min(o, c) + 1e-9) return false;
        return true;
    }

    /** v4.4.2 SAFE MODE quorum latch — hysteresis: ON jab checked>=5 aur fresh<=20%,
     *  OFF jab fresh>=60%. Ek-do stale symbol (delisted/low-liq pair) global SAFE MODE
     *  ab trigger nahi karta — poora feed out ho tabhi. Pure static — testable. */
    static boolean latchSafeMode(boolean prevLatch, int checked, int fresh) {
        if (checked < 5) return prevLatch;                       // sample chhota — koi change nahi
        double ratio = fresh * 100.0 / checked;
        if (!prevLatch && ratio <= 20.0) return true;            // feed outage — latch ON
        if (prevLatch && ratio >= 60.0) return false;            // recovery — clear
        return prevLatch;                                        // hysteresis band — hold
    }

    /** v4.1 — Binance klines JSON → Candle list (public static — host-JVM tests ke liye).
     *  Valid OHLC guard (o/h/l/c > 0), ts = openTime ms. */
    public static List<Candle> parseBinanceKlines(String body) {
        List<Candle> out = new ArrayList<>();
        try {
            JSONArray arr = new JSONArray(body);
            for (int i = 0; i < arr.length(); i++) {
                JSONArray k = arr.getJSONArray(i);
                double o = k.getDouble(1), h = k.getDouble(2), l = k.getDouble(3), c = k.getDouble(4);
                if (!candleOk(k.getLong(0), o, h, l, c, k.getDouble(5))) continue;   // v4.4.2 NaN/zero guard
                Candle cd = new Candle();
                cd.ts = k.getLong(0);                       // openTime ms
                cd.o = o; cd.h = h; cd.l = l; cd.c = c;
                cd.v = k.getDouble(5);
                out.add(cd);
            }
        } catch (Exception ignored) { }
        return out;
    }

    /** Optional MT5 bridge mode (fallback only): user ke PC par chalte MetaTrader5
     *  terminal se REAL MT5 candles. Protocol: GET {bridge}/candles?symbol=X&tf=5m&limit=200
     *  Response: JSON array [[ts_ms, open, high, low, close, volume], ...] */

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
        rotate15m(30);   // v4.5 — PDF pack 5m feed (ALL Binance pairs, rotating)
        updateFeedHealth();   // v4.4.2 — SAFE MODE quorum latch (ek stale symbol global flag flapp nahi karega)
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
            // v2.1: rolling window — 4 din se purani M5 candles purge (DB lean rakhta hai)
            d.execSQL("DELETE FROM candles WHERE symbol=? AND tf=? AND ts < ?",
                    new Object[]{s, TF, System.currentTimeMillis() - 4L * 86400000L});
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

    // ================== v4.5 — 5m PDF PACK FEED (rotating, ALL pairs) ==================
    private final java.util.List<String> rot15 = new ArrayList<>();
    private int rot15Pos = 0;
    private final Map<String, Long> lastEval15 = new HashMap<>();

    /** Har 10s tick par 30 pairs ki 5m candles refresh — 300+ pair universe bhi
     *  ~2 min me poora cycle (5m candle har 5 min close hoti hai — kaafi hai). */
    private void rotate15m(int batch) {
        try {
            if (rot15.isEmpty() || rot15Pos >= rot15.size()) {
                rot15.clear();
                Cursor c = db.getReadableDatabase().rawQuery(
                        "SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE' ORDER BY priority DESC", null);
                while (c.moveToNext()) rot15.add(c.getString(0));
                c.close();
                rot15Pos = 0;
                if (rot15.isEmpty()) return;
            }
            int end = Math.min(rot15.size(), rot15Pos + batch);
            for (int i = rot15Pos; i < end; i++) {
                String s = rot15.get(i);
                List<Candle> ks = fetchFromBinance(s, 300, TF15);
                if (ks != null && !ks.isEmpty()) upsertCandles15(s, ks);
            }
            rot15Pos = end;
        } catch (Throwable t) {
            db.log("WARN", "FEED", "ROT15_FAIL", String.valueOf(t));
        }
    }

    private void upsertCandles15(String s, List<Candle> ks) {
        android.database.sqlite.SQLiteDatabase d = db.getWritableDatabase();
        d.beginTransaction();
        try {
            for (Candle k : ks) {
                d.execSQL("INSERT OR REPLACE INTO candles(symbol, tf, ts, o, h, l, c, v) VALUES(?,?,?,?,?,?,?,?)",
                        new Object[]{s, TF15, k.ts, k.o, k.h, k.l, k.c, k.v});
            }
            d.execSQL("UPDATE instruments SET last_data_at=? WHERE symbol=?",
                    new Object[]{System.currentTimeMillis(), s});
            // 7 din se purani 5m purge (DB lean: ~2016 bars/pair) — PB symbols 16 din
            // (playbook ko 4032-bar = 14-din window chahiye)
            long keepDays = PB_SYMBOLS.contains(s) ? 16L : 7L;
            d.execSQL("DELETE FROM candles WHERE symbol=? AND tf=? AND ts < ?",
                    new Object[]{s, TF15, System.currentTimeMillis() - keepDays * 86400000L});
            d.setTransactionSuccessful();
        } finally { d.endTransaction(); }
    }

    private List<Candle> loadCandles15(String symbol) {
        List<Candle> out = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts, o, h, l, c, v FROM candles WHERE symbol=? AND tf=? ORDER BY ts", new String[]{symbol, TF15});
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

    // ================== 3C MASTER STRATEGY (v1.4) ==================
    // Mechanical implementation of the owner's 3C spec — candle roles, 70% body rule,
    // five-candle window, close-based invalidation, opposite-extreme SL, breakeven at
    // +1R, close-all at +3R. Event names follow MASTER PROMPT section 12:
    // SETUP_DETECTED / SETUP_WAITING / SETUP_INVALIDATED / SETUP_EXPIRED /
    // BREAKOUT_DETECTED / ORDER_EXECUTED / TRADE_MANAGED / TRADE_CLOSED.

    /** One armed 3C setup (per symbol). */
    public static class Setup3C {
        String side;        // "BUY" | "SELL"
        long c3Ts;          // open time of candle 3 (setup completion candle)
        double zoneHigh;    // highest High of the three setup candles
        double zoneLow;     // lowest Low of the three setup candles
        double boundary;    // protected level: BUY -> zoneLow, SELL -> zoneHigh
        double trigger;     // breakout level: BUY -> zoneHigh+buf, SELL -> zoneLow-buf
        double slPrice;     // opposite extreme +/- SL buffer
        // v3.0 — INDEX-based window (session-gap fix): Yahoo CME maintenance breaks /
        // weekends ki candles DB mein hoti hi nahi, to time-diff window counting galat
        // ginti karti thi. Ab window = candle INDEX difference — gap-proof.
        int c3Idx = -1;
        // v3.0 — ML features (entry waqt ka setup DNA, trade row me save hota hai)
        double c3Body = 0, c3VolRatio = 0, c3AtrPct = 0, c3EmaDist = 0, c3RdPct = 0;
    }

    private static class Walk3C {
        String state = "no setup";
        Setup3C fire;       // non-null when the LAST closed candle triggered a breakout
        double fill;        // stop-order fill price of that breakout
        Setup3C pending;    // setup still waiting at the end of the walk
    }

    private double bodyPct(Candle c) {
        double rng = c.h - c.l;
        if (rng <= 0) return 0;
        return Math.abs(c.c - c.o) / rng;
    }

    /** Detect a completed 3C setup on candles (i-2, i-1, i); null if none. */
    private Setup3C detect3C(List<Candle> k, int i, double entryBuf, double slBuf) {
        Candle c1 = k.get(i - 2), c2 = k.get(i - 1), c3 = k.get(i);
        boolean g1 = c1.c > c1.o, g2 = c2.c > c2.o, g3 = c3.c > c3.o;
        boolean b1 = bodyPct(c1) >= THREEC_BODY_MIN, b2 = bodyPct(c2) >= THREEC_BODY_MIN;
        if (!b1 || !b2) return null;
        Setup3C s = new Setup3C();
        s.c3Ts = c3.ts;
        s.zoneHigh = Math.max(c1.h, Math.max(c2.h, c3.h));
        s.zoneLow = Math.min(c1.l, Math.min(c2.l, c3.l));
        if (g1 && g2 && !g3 && c3.c >= Math.min(c1.l, c2.l)) {          // BUY setup
            s.side = "BUY";
            s.boundary = s.zoneLow;
            s.trigger = s.zoneHigh * (1 + entryBuf);
            s.slPrice = s.zoneLow * (1 - slBuf);
            s.c3Idx = i;
            return s;
        }
        if (!g1 && !g2 && g3 && c3.c <= Math.max(c1.h, c2.h)) {         // SELL setup
            s.side = "SELL";
            s.boundary = s.zoneHigh;
            s.trigger = s.zoneLow * (1 - entryBuf);
            s.slPrice = s.zoneHigh * (1 + slBuf);
            s.c3Idx = i;
            return s;
        }
        return null;
    }

    /** One 3C lifecycle event, logged exactly once per setup+event. */
    private void log3C(String sym, Setup3C s, String event, String details) {
        String key = sym + "|" + s.c3Ts + "|" + event;
        if (threecLogged.contains(key)) return;
        threecLogged.add(key);
        if (threecLogged.size() > 400) {
            java.util.Iterator<String> it = threecLogged.iterator();
            for (int i = 0; i < 200 && it.hasNext(); i++) { it.next(); it.remove(); }
        }
        db.log("INFO", "3C", event, sym + " — " + details);
        lastPattern = event + " " + sym;
    }

    /** TR value at index (ATR rolling-window ke liye). */
    private static double trOf(List<Candle> k, int i) {
        if (i <= 0) return k.get(0).h - k.get(0).l;
        Candle c = k.get(i), p = k.get(i - 1);
        return Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
    }

    /** Chronological rebuild of the 3C state machine over closed candles. Deterministic
     * and restart-proof: har loop state real candles se dobara derive hota hai, fragile
     * memory nahi. Sirf LAST closed candle ka breakout trade kar sakta hai (purane
     * breakouts consumed/expired hote hain — ek hi baar MISSED log hota hai).
     */
    private Walk3C walk3C(String sym, List<Candle> k) {
        double entryBuf = bufSetting("threec_entry_buf_pct");
        double slBuf = bufSetting("threec_sl_buf_pct");
        // v4.4.1 — indicators sirf SETUP DNA ke liye precompute (O(n), ek hi pass):
        // emaArr → c3EmaDist, atrArr → c3AtrPct (ML journal features). KOI FILTER NAHI —
        // volSma (sirf volume-filter ke liye tha) delete.
        int n = k.size();
        double[] emaArr = new double[n];
        double[] atrArr = new double[n];
        {
            double mult = 2.0 / 201.0;
            if (n >= 200) {
                // v3.0 WARMUP FIX (audit): index 199 par SMA200 seed — standard EMA practice.
                double sma = 0;
                for (int j = 0; j < 200; j++) sma += k.get(j).c;
                double e = sma / 200.0;
                for (int i = 0; i < 200; i++) emaArr[i] = e;   // pre-seed flat (DNA index>=200 par hi leta hai)
                for (int i = 200; i < n; i++) { e = (k.get(i).c - e) * mult + e; emaArr[i] = e; }
            } else {  // <200 candles — graceful warmup converge (purana behavior)
                double e = k.get(0).c;
                for (int i = 0; i < n; i++) { e = (k.get(i).c - e) * mult + e; emaArr[i] = e; }
            }
        }
        {
            double trSum = 0;
            for (int i = 0; i < n; i++) {
                Candle c = k.get(i);
                double tr = i == 0 ? c.h - c.l
                        : Math.max(c.h - c.l, Math.max(Math.abs(c.h - k.get(i - 1).c), Math.abs(c.l - k.get(i - 1).c)));
                trSum += tr;
                if (i >= 14) trSum -= trOf(k, i - 14);
                atrArr[i] = trSum / Math.min(i + 1, 14);
            }
        }
        Walk3C w = new Walk3C();
        Setup3C pending = null;
        int last = k.size() - 1;
        for (int i = 2; i <= last; i++) {
            Candle c = k.get(i);
            if (pending != null) {
                int winIdx = i - pending.c3Idx;                        // v3.0: INDEX window — CME gap/weekend proof
                if (winIdx > THREEC_WINDOW) {
                    log3C(sym, pending, "SETUP_EXPIRED", "no breakout by candle " + THREEC_WINDOW + " — setup expired");
                    pending = null;                                    // fall through: candle i may start a new setup
                } else {
                    boolean buy = "BUY".equals(pending.side);
                    boolean closeInvalid = buy ? c.c < pending.boundary : c.c > pending.boundary;
                    boolean broke = buy ? c.h > pending.trigger : c.l < pending.trigger;
                    if (broke && closeInvalid) {
                        // MASTER PROMPT: breakout + close-beyond boundary in ONE candle —
                        // OHLC alone cannot sequence them; kabhi guess nahi. Setup untraded dead.
                        log3C(sym, pending, "SETUP_INVALIDATED",
                                "UNKNOWN sequence — breakout + close beyond boundary in the same candle; skipped (no tick evidence)");
                        w.state = "UNKNOWN — ambiguous candle, setup skipped";
                        pending = null;
                    } else if (closeInvalid) {
                        log3C(sym, pending, "SETUP_INVALIDATED",
                                "candle CLOSED beyond protected boundary " + fpx(pending.boundary) + " (wick alone never cancels)");
                        pending = null;
                    } else if (broke) {
                        // BREAKOUT_DETECTED — stop-order fill at trigger; gap-open fills at open
                        double fill = buy ? Math.max(pending.trigger, c.o) : Math.min(pending.trigger, c.o);
                        Setup3C fired = pending;
                        pending = null;
                        log3C(sym, fired, "BREAKOUT_DETECTED",
                                "candle " + winIdx + "/" + THREEC_WINDOW + " broke " + (buy ? "above " : "below ")
                                        + fpx(fired.trigger));
                        if (i == last) {
                            w.fire = fired;
                            w.fill = fill;
                            w.state = "ENTRY " + fired.side + " — breakout on candle " + winIdx + "/"
                                    + THREEC_WINDOW + ", fill " + fpx(fill);
                            return w;
                        }
                        log3C(sym, fired, "SETUP_CONSUMED",
                                "breakout candle is history (engine busy/off tha) — stale price par late fill nahi");
                    } else {
                        w.state = pending.side + " setup armed — window " + winIdx + "/" + THREEC_WINDOW
                                + ", trigger " + fpx(pending.trigger)
                                + ", invalidation close " + (buy ? "< " : "> ") + fpx(pending.boundary);
                    }
                }
            }
            if (pending == null) {
                Setup3C s = detect3C(k, i, entryBuf, slBuf);
                // v4.4.1: proFilter3C gate REMOVED — jo setup detect3C pass kare woh seedha armed
                if (s != null) {
                    pending = s;
                    // v3.0 — setup DNA (ML features) capture: entry par trade row me save
                    Candle c3f = k.get(i);
                    s.c3Body = bodyPct(c3f);
                    double vSum = 0; int vN = 0;
                    for (int j = Math.max(0, i - 19); j <= i; j++) { vSum += k.get(j).v; vN++; }
                    s.c3VolRatio = vN > 0 && vSum > 0 ? c3f.v / (vSum / vN) : 0;
                    double aF = atrArr != null && atrArr[i] > 0 ? atrArr[i] : atr(k, 14);
                    s.c3AtrPct = (Double.isNaN(aF) || aF <= 0) ? 0 : aF / c3f.c * 100.0;
                    if (emaArr != null && i >= 200) s.c3EmaDist = (c3f.c - emaArr[i]) / emaArr[i] * 100.0;
                    s.c3RdPct = Math.abs(s.trigger - s.slPrice) / s.trigger * 100.0;
                    log3C(sym, s, "SETUP_DETECTED",
                            s.side + " — C1/C2 body " + pct(bodyPct(k.get(i - 2))) + "% / " + pct(bodyPct(k.get(i - 1)))
                                    + "%, zone " + fpx(s.zoneLow) + " - " + fpx(s.zoneHigh) + ", C3 protected close OK");
                    // SETUP_WAITING — window opens on the NEXT candle
                }
            }
        }
        w.pending = pending;
        if (pending != null && "no setup".equals(w.state)) {
            w.state = pending.side + " setup armed — waiting for first window candle, trigger " + fpx(pending.trigger);
        }
        return w;
    }

    // ================== TRADE LOGIC ==================
    private void scanAndTrade() {
        List<Long> users = userIds();
        List<String> syms = activeSymbols();
        StringBuilder armedList = new StringBuilder();
        int armed = 0;
        String fireText = null;
        for (String sym : syms) {
            List<Candle> all = loadCandles(sym);
            if (all.size() < 60) { threecStates.put(sym, "data kam — " + all.size() + "/60 candles"); continue; }
            List<Candle> k = all;
            if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < TF_MS) {
                k = k.subList(0, k.size() - 1);            // trade CLOSED candles only (v5.9.2 rule)
                if (k.size() < 8) continue;
            }
            Walk3C w = walk3C(sym, k);
            threecStates.put(sym, w.state);
            // v1.5 — LIVE stop-order trigger: breakout ka intezaar candle close tak NAHI.
            // Chalti hui (in-progress) M5 candle trigger cross karti hi foran entry —
            // bilkul real trader ke stop order jaisa. Window discipline same: live candle
            // sirf tab trigger kar sakti hai jab wo 5-candle window ke andar ho.
            if (w.fire == null && w.pending != null && !all.isEmpty()) {
                Candle live = all.get(all.size() - 1);
                Setup3C p = w.pending;
                boolean liveFresh = System.currentTimeMillis() - live.ts < TF_MS;
                int liveWin = k.size() - p.c3Idx;                  // v3.0: INDEX window (k = closed candles; live uska next index hota)
                if (liveFresh && liveWin > THREEC_WINDOW) {
                    log3C(sym, p, "SETUP_EXPIRED", "no breakout by candle " + THREEC_WINDOW + " — window khatam, live trigger band");
                    w.pending = null;
                    threecStates.put(sym, "setup expired — " + THREEC_WINDOW + "/" + THREEC_WINDOW + " window complete, breakout nahi hua");
                } else if (liveFresh && liveWin >= 1) {
                    boolean buyL = "BUY".equals(p.side);
                    // v3.0 INVALIDATION SYMMETRY (audit fix #9): live candle ka current close
                    // boundary ke paar ja chuka ho to setup dead hai — intrabar trigger us
                    // setup par entry nahi karega jo closed-candle walk UNKNOWN kehta.
                    boolean liveInvalid = buyL ? live.c < p.boundary : live.c > p.boundary;
                    if (liveInvalid) {
                        log3C(sym, p, "SETUP_INVALIDATED",
                                "LIVE candle close " + fpx(live.c) + " protected boundary " + fpx(p.boundary)
                                        + " ke paar — symmetric invalidation, intrabar entry cancel");
                        w.pending = null;
                        threecStates.put(sym, "setup invalidated — live close beyond boundary (symmetry check)");
                    } else if (buyL ? live.h > p.trigger : live.l < p.trigger) {
                        double fill = buyL ? Math.max(p.trigger, live.o) : Math.min(p.trigger, live.o);
                        lastVotes = new int[]{buyL ? 1 : -1};
                        lastVoteSym = sym;
                        for (long uid : users) openTrade3C(uid, sym, p, fill, k, p.c3Idx);
                        log3C(sym, p, "BREAKOUT_DETECTED",
                                "LIVE candle " + liveWin + "/" + THREEC_WINDOW + " broke " + (buyL ? "above " : "below ")
                                        + fpx(p.trigger) + " — intrabar stop-order fill (candle close ka intezaar nahi)");
                        fireText = "ENTRY OPEN — " + sym + " " + p.side + " @ " + fpx(fill)
                                + " (3C LIVE breakout, SL " + fpx(p.slPrice) + ", TP +3R, risk " + pct(riskPct() / 100)
                                + "%) — breakeven at +1R";
                        lastPattern = "BREAKOUT " + sym;
                        threecStates.put(sym, "ENTRY " + p.side + " — live breakout trigger " + fpx(p.trigger) + " @ " + fpx(fill));
                        w.pending = null;
                    }
                }
            }
            if (w.fire != null) {
                lastVotes = new int[]{"BUY".equals(w.fire.side) ? 1 : -1};
                lastVoteSym = sym;
                for (long uid : users) openTrade3C(uid, sym, w.fire, w.fill, k, w.fire.c3Idx);
                fireText = "ENTRY OPEN — " + sym + " " + w.fire.side + " @ " + fpx(w.fill)
                        + " (3C breakout, SL " + fpx(w.fire.slPrice) + ", TP +3R, risk " + pct(riskPct() / 100)
                        + "%) — breakeven at +1R";
                lastPattern = "BREAKOUT " + sym;
                continue;                                   // next symbol — unlimited positions allowed
            }
            if (w.pending != null) {
                lastVotes = new int[]{"BUY".equals(w.pending.side) ? 1 : -1};
                lastVoteSym = sym;
                armed++;
                if (armedList.length() > 0) armedList.append(" | ");
                if (armedList.length() < 100) armedList.append(sym).append(" ").append(w.pending.side);
            } else {
                lastVotes = new int[1];
            }
            // v1.2 Strategy Lab — custom AI/YouTube strategies (PAPER + ACTIVE) ab bhi
            // 5m candles par signal deti hain jab 3C kuch fire nahi karta.
            if (lab != null) for (long uid : users) tryCustomStrategies(uid, sym, k);
        }
        if (fireText != null) {
            lastConsensus = fireText;
        } else if (armed > 0) {
            lastConsensus = "3C M5 scan #" + scanCount + " — " + syms.size() + " syms — " + armed
                    + " setup(s) armed: " + armedList + " — breakout window chal raha hai";
        } else {
            lastConsensus = "3C M5 scan #" + scanCount + " — " + syms.size()
                    + " syms — koi valid 3C setup nahi (C1+C2 70% body + C3 protected + 5-candle breakout window)";
        }
    }

    // ================== v4.4 — PDF STRATEGY PACK SCAN + FEE-EDGE + AI TRAINER ==================
    private final Map<String, double[]> fundingCache = new HashMap<>();
    private long fundingAt = 0;

    /** S6 ke liye funding + OI 24h change (fapi.binance.com) — 15 min cache. */
    private double[] fundingOi(String sym) {
        long now = System.currentTimeMillis();
        if (now - fundingAt > 15 * 60_000L) { fundingCache.clear(); fundingAt = now; }
        if (fundingCache.containsKey(sym)) return fundingCache.get(sym);
        try {
            String fr = httpGetUrl("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=" + sym, 8000);
            if (fr == null) { fundingCache.put(sym, null); return null; }
            double funding = new JSONObject(fr).optDouble("lastFundingRate", Double.NaN);
            String oi = httpGetUrl("https://fapi.binance.com/futures/data/openInterestHist?symbol=" + sym + "&period=1h&limit=25", 8000);
            double oiChg = Double.NaN;
            if (oi != null) {
                JSONArray arr = new JSONArray(oi);
                if (arr.length() >= 2) {
                    double first = arr.getJSONObject(0).optDouble("sumOpenInterest", 0);
                    double last = arr.getJSONObject(arr.length() - 1).optDouble("sumOpenInterest", 0);
                    if (first > 0) oiChg = (last - first) / first * 100.0;
                }
            }
            if (Double.isNaN(funding)) { fundingCache.put(sym, null); return null; }
            double[] out = new double[]{funding, Double.isNaN(oiChg) ? 0 : oiChg};
            fundingCache.put(sym, out);
            return out;
        } catch (Throwable t) { fundingCache.put(sym, null); return null; }
    }

    /** Pack scan: naye CLOSED 15m candle par S1-S9 evaluate (rotating feed ka current window). */
    private void scanPdfPack() {
        if (!"1".equals(db.setting("pack_on", "0"))) return;   // v1.1 TUNED default OFF (replay: PF 0.38-0.60 fees bleed — owner toggle ON kar sakta hai)
        if (rot15.isEmpty()) return;
        int from = Math.max(0, rot15Pos - 30), end = rot15Pos;
        if (from >= end) return;
        List<Long> users = userIds();
        for (int i = from; i < end && i < rot15.size(); i++) {
            String sym = rot15.get(i);
            try {
                List<Candle> all = loadCandles15(sym);
                if (all.size() < 220) continue;
                List<Candle> k = all;
                if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < TF15_MS) {
                    k = k.subList(0, k.size() - 1);   // sirf CLOSED 15m candles (PDF rule)
                    if (k.size() < 220) continue;
                }
                Candle last = k.get(k.size() - 1);
                Long done = lastEval15.get(sym);
                if (done != null && done == last.ts) continue;   // isi candle par pehle eval ho chuka
                lastEval15.put(sym, last.ts);
                double[] prevDay = prevDayHighLow(k);
                double[] adx = StrategyPack.adxAt(k, 14, k.size() - 1);
                double chopAdx = adx == null ? -1 : adx[0];
                double[] deriv = fundingOi(sym);
                List<StrategyPack.Signal> sigs = StrategyPack.evaluateAll(k, k.size() - 1, prevDay, deriv, chopAdx);
                for (StrategyPack.Signal s : sigs) {
                    if (!"1".equals(db.setting("pack_" + s.strategy.toLowerCase(Locale.ROOT), "1"))) continue;
                    if (!aiEnabled(s.strategy)) continue;      // v4.4 AI gate (trained weights)
                    for (long uid : users) openTradePdf(uid, sym, s);
                }
            } catch (Throwable t) {
                db.log("WARN", "PACK", "EVAL_FAIL", sym + " — " + t);
            }
        }
    }

    /** v4.4 — AI weights gate: trained strategy OFF ho to trade nahi (owner force-on: ai_off_<key>=1). */
    boolean aiEnabled(String key) {
        try {
            if ("1".equals(db.setting("ai_off_" + key, "0"))) return true;   // owner force-enable
            JSONObject w = aiWeights();
            if (w == null || !w.has(key)) return true;   // untrained = neutral ON
            return w.getJSONObject(key).optInt("on", 1) == 1;
        } catch (Throwable t) { return true; }
    }

    private JSONObject aiWeightsCache;
    private long aiWeightsAt = 0;

    JSONObject aiWeights() {
        long now = System.currentTimeMillis();
        if (aiWeightsCache != null && now - aiWeightsAt < 60_000) return aiWeightsCache;
        try {
            aiWeightsCache = new JSONObject(db.setting("ai_weights_v2", "{}"));
            aiWeightsAt = now;
            return aiWeightsCache;
        } catch (Throwable t) { return null; }
    }

    void invalidateAiWeights() { aiWeightsCache = null; aiWeightsAt = 0; }

    /** PDF pack entry — pack SL/boundary/window, TP = +2R, BE at +1R, risk 1% flat (owner rule). */
    private void openTradePdf(long uid, String sym, StrategyPack.Signal s) {
        String tier = "PDF:" + s.strategy;
        if (!freshData(sym)) return;
        if (strategyPaused(tier)) return;
        if (entryBlocked(uid, sym)) return;
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }
        if (eventGateActive()) return;
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym, tier});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;
        List<Candle> k = loadCandles15(sym);
        if (k.isEmpty()) return;
        double price = livePrice(sym);
        if (price <= 0) price = k.get(k.size() - 1).c;
        double rd = Math.abs(price - s.slPrice);
        if (rd <= 0 || price <= 0) return;
        double tpDist = 2 * rd;
        if (!feeEdgeOk(tier + " " + sym, price, tpDist)) return;   // v4.4 fee-edge guard
        int council = councilScore(sym, s.side, k, k.size() - 1);
        int cMin = councilMin();
        if (cMin > 0 && council < cMin) return;
        double heatCap = heatMaxPct(), bucketCap = bucketMaxPct();
        if (heatCap > 0 && heatRiskPct(uid) + 1.0 > heatCap) return;
        if (bucketCap > 0 && bucketRiskPct(uid, bucketOf(sym)) + 1.0 > bucketCap) return;
        price = slipEntry(price, s.side);
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * dynamicRiskPct(tier) / 100.0;   // base 1%, min-25 consensus scaling
        double qty = risk / rd;
        if (qty * price > bal * levCap()) qty = bal * levCap() / price;
        if (qty <= 0) return;
        boolean buy = "BUY".equals(s.side);
        double sl = buy ? price - rd : price + rd;
        double tp = buy ? price + tpDist : price - tpDist;
        JSONObject features = new JSONObject();
        try {
            features.put("boundary", s.boundary).put("sig_ts", s.sigTs)
                    .put("window_bars", s.windowBars).put("tf", TF15).put("note", s.note);
        } catch (Throwable ignored) { }
        double riskAmt = rd * qty;
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)",
                new Object[]{uid, sym, s.side, qty, price, sl, tp, tier, 0.7, System.currentTimeMillis(), dynamicRiskPct(tier) / 100.0, riskAmt, price, council, mlWinProb(features), features.toString()});
        long tradeId = 0;
        Cursor ti = db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
        if (ti.moveToFirst()) tradeId = ti.getLong(0);
        ti.close();
        recordOrder(tradeId, uid, sym, s.side, "MARKET", price, qty, "PAPER", "FILLED");
        bridgeOrder(sym, s.side, tradeId, uid, price, qty);
        db.log("INFO", "PACK", "ORDER_EXECUTED", sym + " " + s.side + " [" + tier + "] qty="
                + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(price) + " sl=" + fpx(sl)
                + " — " + s.note + " (risk 1%, TP +2R, boundary invalidation)");
    }

    // ================== v4.4 — FEE-EDGE GUARD (professional loss-killer) ==================
    /** TP move round-trip fees (0.05%×2 + slippage×2) se chhota → trade SKIP.
     *  PDF ka bhi rule: "1m/5m scalping is dominated by fees". Default ON —
     *  owner fee_edge_on=0 se disable kar sakta hai. */
    private boolean feeEdgeOk(String where, double price, double tpDist) {
        if (!"1".equals(db.setting("fee_edge_on", "1"))) return true;
        double minEdge = 0.14;
        try { minEdge = Double.parseDouble(db.setting("min_fee_edge_pct", "0.14").trim()); } catch (Throwable ignored) { }
        if (price <= 0 || tpDist <= 0) return true;
        double tpPct = tpDist / price * 100.0;
        if (tpPct >= minEdge) return true;
        db.log("INFO", "GUARD", "FEE_EDGE_SKIP", where + " — TP move " + String.format(Locale.US, "%.3f", tpPct)
                + "% < round-trip fees+slip " + String.format(Locale.US, "%.2f", minEdge) + "% — professional skip (negative expectancy trade)");
        return false;
    }

    // ================== v1.0 — 5M PLAYBOOK (Z.ai Research 5m guide S1-S4) ==================
    /** Guide portfolio: BTC/ETH/BNB/SOL (charon coins jinhone 5 saal ke backtest me profit diya). */
    static final java.util.Set<String> PB_SYMBOLS = new java.util.HashSet<>(java.util.Arrays.asList(
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"));
    private final java.util.Map<String, Long> lastPbFill = new HashMap<>();
    private final Map<String, Long> lastEvalPb = new HashMap<>();

    /** Initial SL multiplier (guide: P1 5x, P2 4x, P3/P4 3.5x ATR). */
    static double pbSlAtrMult(String key) {
        if (key.startsWith("P1")) return 5.0;
        if (key.startsWith("P2")) return 4.0;
        return 3.5;
    }

    /** Trail multiplier (guide: P4 7x, baaki 8x ATR — 4 closed bars ke baad). */
    static double pbTrailAtrMult(String key) {
        return key.startsWith("P4") ? 7.0 : 8.0;
    }

    /** v1.0 — playbook scan: 4 guide coins, CLOSED 5m bar par eval (idempotent), har
     *  signal har user ke liye paper trade (owner + traders — multi-user design). */
    private void scanPlaybook() {
        if (!"1".equals(db.setting("pb_on", "1"))) return;
        List<Long> users = userIds();
        for (String sym : PB_SYMBOLS) {
            try {
                ensurePbHistory(sym);
                List<Candle> all = loadCandles15(sym);
                if (all.size() < 500) continue;
                List<Candle> k = all;
                if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < TF15_MS) {
                    k = k.subList(0, k.size() - 1);   // sirf CLOSED 5m candles (guide rule)
                    if (k.size() < 500) continue;
                }
                Candle last = k.get(k.size() - 1);
                Long done = lastEvalPb.get(sym);
                if (done != null && done == last.ts) continue;   // isi bar par eval ho chuka
                lastEvalPb.put(sym, last.ts);
                List<StrategyPack.Signal> sigs = StrategyPack.evaluatePlaybook(k, k.size() - 1);
                for (StrategyPack.Signal s : sigs) {
                    if (!"1".equals(db.setting("pack_" + s.strategy.toLowerCase(Locale.ROOT), "1"))) continue;
                    if (!aiEnabled(s.strategy)) continue;      // AI weights gate (untrained = ON)
                    for (long uid : users) openTradePb(uid, sym, s);
                }
            } catch (Throwable t) {
                db.log("WARN", "PB", "EVAL_FAIL", sym + " — " + t);
            }
        }
    }

    /** v1.0 — playbook ko 14-din (4032+ bars) 5m history chahiye — Binance paginated
     *  fetch (5 x 1000 bars), DB candles me accumulate. Har 5 min par ek top-up. */
    private void ensurePbHistory(String sym) {
        long now = System.currentTimeMillis();
        Long last = lastPbFill.get(sym);
        if (last != null && now - last < 5 * 60_000L) return;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*), MAX(ts) FROM candles WHERE symbol=? AND tf=?", new String[]{sym, TF15});
        int have = 0; long newest = 0;
        if (c.moveToFirst()) { have = c.getInt(0); newest = c.getLong(1); }
        c.close();
        if (have >= 4400 && now - newest < TF15_MS) { lastPbFill.put(sym, now); return; }
        List<Candle> pages = fetchFromBinancePaged(sym, TF15, 5);
        if (pages != null && !pages.isEmpty()) {
            upsertCandles15(sym, pages);
            db.log("INFO", "PB", "HISTORY_FILL", sym + " — " + pages.size() + " 5m bars fetched (deep history " + have + " → " + (have + pages.size()) + ")");
        }
        lastPbFill.put(sym, now);
    }

    /** v1.0 — Binance klines paginated (endTime backward walk) — playbook deep history. */
    private List<Candle> fetchFromBinancePaged(String symbol, String interval, int maxPages) {
        List<Candle> out = new ArrayList<>();
        Long endTime = null;
        for (int pg = 0; pg < maxPages; pg++) {
            try {
                String url = BINANCE_HOST + "/api/v3/klines?symbol=" + symbol + "&interval=" + interval
                        + "&limit=1000" + (endTime != null ? "&endTime=" + endTime : "");
                String body = httpGetUrl(url, 12000);
                if (body == null) break;
                List<Candle> page = parseBinanceKlines(body);
                if (page.isEmpty()) break;
                out.addAll(page);
                long oldest = page.get(0).ts;
                if (endTime != null && oldest >= endTime) break;
                endTime = oldest - 1;
                if (page.size() < 1000) break;
            } catch (Throwable t) { break; }
        }
        return out;
    }

    /** v1.0 — PLAYBOOK entry (guide S1-S4): risk-based sizing (guide formula), SL =
     *  slMult x ATR, NO TP — exit trail se (managePbTrade). Fee-edge guard expected
     *  move 2xATR. Leverage-cap analog: notional <= 95% balance. */
    private void openTradePb(long uid, String sym, StrategyPack.Signal s) {
        String tier = "PB:" + s.strategy;
        if (!freshData(sym)) return;
        if (strategyPaused(tier)) return;
        if (entryBlocked(uid, sym)) return;
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }
        if (eventGateActive()) return;
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym, tier});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;
        List<Candle> k = loadCandles15(sym);
        if (k.size() < 600) return;
        double atr = StrategyPack.atrAt(k, 14, k.size() - 1);
        if (!(atr > 0)) return;
        double price = livePrice(sym);
        if (price <= 0) price = k.get(k.size() - 1).c;
        double slDist = pbSlAtrMult(s.strategy) * atr;
        if (!(slDist > 0) || price <= 0) return;
        if (!feeEdgeOk(tier + " " + sym, price, 2 * atr)) return;   // fee-edge guard (expected 2xATR move)
        double heatCap = heatMaxPct(), bucketCap = bucketMaxPct();
        if (heatCap > 0 && heatRiskPct(uid) + 1.0 > heatCap) return;
        if (bucketCap > 0 && bucketRiskPct(uid, bucketOf(sym)) + 1.0 > bucketCap) return;
        price = slipEntry(price, s.side);
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * dynamicRiskPct(tier) / 100.0;   // base 1% (guide safe config), min-25 scaling
        double qty = risk / slDist;
        if (qty * price > bal * levCap()) qty = bal * levCap() / price;
        if (qty <= 0) return;
        boolean buy = "BUY".equals(s.side);
        double sl = buy ? price - slDist : price + slDist;
        double tp = buy ? price + 1000 * atr : price - 1000 * atr;   // nominal — PB exit TRAIL/SL se hota hai
        JSONObject features = new JSONObject();
        try {
            features.put("pb", 1).put("atr", atr)
                    .put("sl_mult", pbSlAtrMult(s.strategy)).put("trail_mult", pbTrailAtrMult(s.strategy))
                    .put("trail", 0).put("bars", 0).put("last_bar_ts", s.sigTs)
                    .put("sig_ts", s.sigTs).put("tf", TF15).put("note", s.note);
        } catch (Throwable ignored) { }
        double riskAmt = slDist * qty;
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)",
                new Object[]{uid, sym, s.side, qty, price, sl, tp, tier, 0.7, System.currentTimeMillis(), dynamicRiskPct(tier) / 100.0, riskAmt, price, 0, mlWinProb(features), features.toString()});
        long tradeId = 0;
        Cursor ti = db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
        if (ti.moveToFirst()) tradeId = ti.getLong(0);
        ti.close();
        recordOrder(tradeId, uid, sym, s.side, "MARKET", price, qty, "PAPER", "FILLED");
        bridgeOrder(sym, s.side, tradeId, uid, price, qty);
        db.log("INFO", "PB", "ORDER_EXECUTED", sym + " " + s.side + " [" + tier + "] qty="
                + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(price) + " sl=" + fpx(sl)
                + " — " + s.note + " (guide sizing, NO TP — trail exit)");
        try { Notifier.post(appContext(), "Playbook trade", sym + " " + s.side + " [" + s.strategy + "] — " + s.note); } catch (Throwable ignored) { }
    }

    /** v1.0 — PLAYBOOK management (guide exit rule): pehle 4 closed bars initial SL,
     *  phir har closed 5m bar ke close par trail = close -/+ trailMult x ATR (sirf
     *  behtar direction me shift, kabhi loose nahi). Exit TRAIL/SL se, TP nahi.
     *  Restart-safe: trail/bars/last_bar_ts features JSON me persist. */
    private void managePbTrade(long id, long uid, String sym, String side, double qty,
                               double entry, double sl0, boolean buy) {
        try {
            Cursor fc = db.getReadableDatabase().rawQuery("SELECT features FROM trades WHERE id=?", new String[]{String.valueOf(id)});
            String feats = fc.moveToFirst() ? fc.getString(0) : "{}";
            fc.close();
            JSONObject ft = new JSONObject(feats);
            double atr = ft.optDouble("atr", 0);
            double trailMult = ft.optDouble("trail_mult", 8.0);
            double trail = ft.optDouble("trail", 0);
            long lastBar = ft.optLong("last_bar_ts", 0);
            int barsHeld = ft.optInt("bars", 0);
            if (!(atr > 0)) return;
            long now = System.currentTimeMillis();
            // 1) CLOSED bars replay — trail advance (har closed 5m bar par ek dafa)
            Cursor cb = db.getReadableDatabase().rawQuery(
                    "SELECT ts, c FROM candles WHERE symbol=? AND tf=? AND ts>? AND ts<=? ORDER BY ts",
                    new String[]{sym, TF15, String.valueOf(lastBar), String.valueOf(now - TF15_MS)});
            List<long[]> bars = new ArrayList<>(); List<Double> closes = new ArrayList<>();
            while (cb.moveToNext()) { bars.add(new long[]{cb.getLong(0)}); closes.add(cb.getDouble(1)); }
            cb.close();
            for (int i = 0; i < bars.size(); i++) {
                long ts = bars.get(i)[0]; double cl = closes.get(i);
                if (barsHeld >= 4) {
                    double cand = buy ? cl - trailMult * atr : cl + trailMult * atr;
                    trail = (trail == 0) ? cand : (buy ? Math.max(trail, cand) : Math.min(trail, cand));
                }
                barsHeld++;
                lastBar = ts;
            }
            if (!bars.isEmpty()) {
                ft.put("trail", trail).put("last_bar_ts", lastBar).put("bars", barsHeld);
                db.getWritableDatabase().execSQL("UPDATE trades SET features=? WHERE id=?", new Object[]{ft.toString(), id});
            }
            // 2) exit check — latest closed bar + live bar (SL pehle — conservative)
            boolean trailing = barsHeld >= 4 && trail != 0;
            double activeStop = trailing ? trail : sl0;
            double[][] hl2 = new double[2][];
            Cursor cc = db.getReadableDatabase().rawQuery(
                    "SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                    new String[]{sym, TF15, String.valueOf(now - TF15_MS)});
            if (cc.moveToFirst()) hl2[0] = new double[]{cc.getDouble(0), cc.getDouble(1)};
            cc.close();
            Cursor lc = db.getReadableDatabase().rawQuery(
                    "SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts>? ORDER BY ts DESC LIMIT 1",
                    new String[]{sym, TF15, String.valueOf(now - TF15_MS)});
            if (lc.moveToFirst()) hl2[1] = new double[]{lc.getDouble(0), lc.getDouble(1)};
            lc.close();
            for (double[] hl : hl2) {
                if (hl == null) continue;
                boolean hit = buy ? hl[1] <= activeStop : hl[0] >= activeStop;
                if (hit) {
                    String reason = trailing ? "TRAIL" : "SL";
                    db.log("INFO", "PB", "PLAYBOOK_EXIT", "trade #" + id + " " + sym + " — " + reason + " hit @ " + fpx(activeStop) + " (bars=" + barsHeld + ")");
                    closeTrade(id, uid, activeStop, reason, qty, entry, side);
                    return;
                }
            }
            // MFE/MAE journal (closed bar se)
            if (hl2[0] != null) {
                double mfe = buy ? (hl2[0][0] - entry) * qty : (entry - hl2[0][1]) * qty;
                double mae = buy ? (entry - hl2[0][1]) * qty : (hl2[0][0] - entry) * qty;
                db.getWritableDatabase().execSQL(
                        "UPDATE trades SET mfe=MAX(IFNULL(mfe,0),?), mae=MAX(IFNULL(mae,0),?) WHERE id=?",
                        new Object[]{Math.max(0, mfe), Math.max(0, mae), id});
            }
        } catch (Throwable t) {
            db.log("WARN", "PB", "MANAGE_FAIL", "trade #" + id + " — " + t);
        }
    }

    // ================== v1.1 TUNED — X7 REGIME FADE (replay-verified PF 1.29-1.87) ==================
    /** Replay tuning (Nov 2026, real Binance 5m, 14-din windows): X7 = 24h VWAP ± 3.5σ
     *  deviation fade + RSI confluence (RSI<30 buy / >70 sell) + REGIME GATE (ADX(56) < 22 —
     *  sirf ranging market). SL = 1.0×ATR, TP = +2.5R, NO breakeven (tuned: BE-off), risk
     *  riskPct(), notional levCap(). Har closed 5m bar par eval, per symbol 1 open trade,
     *  SL ke baad 15-min cooldown (generic guard). Recent windows: +1.0%..+2.2%/14d @1% risk,
     *  maxDD 1.7-2.7%. TURBO controls (risk 20% + lev 5x) owner ke paas — PAPER sim. */
    static final double X7_SIGMA = 3.5, X7_TP_R = 2.5, X7_SL_ATR = 1.0, X7_RSI_LO = 30, X7_RSI_HI = 70, X7_ADX_MAX = 22.0;
    private final Map<String, Long> lastEvalX7 = new HashMap<>();

    private void scanX7() {
        if (!"1".equals(db.setting("x7_on", "1"))) return;
        List<Long> users = userIds();
        List<String> syms = activeSymbols();
        for (String sym : syms) {
            try {
                List<Candle> all = loadCandles(sym);
                if (all.size() < 300) continue;
                List<Candle> k = all;
                if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < TF_MS) {
                    k = k.subList(0, k.size() - 1);   // sirf CLOSED 5m candles
                    if (k.size() < 300) continue;
                }
                Candle last = k.get(k.size() - 1);
                Long done = lastEvalX7.get(sym);
                if (done != null && done == last.ts) continue;   // idempotent (isi bar par eval ho chuka)
                lastEvalX7.put(sym, last.ts);
                String side = x7Signal(k, k.size() - 1);
                if (side == null) continue;
                for (long uid : users) openTradeX7(uid, sym, side, k);
            } catch (Throwable t) {
                db.log("WARN", "X7", "EVAL_FAIL", sym + " — " + t);
            }
        }
    }

    /** X7 signal core (replay parity): VWAP(288) ± 3.5σ + RSI(14) confluence + ADX(56)<22. */
    static String x7Signal(List<Candle> k, int i) {
        if (i < 300 || i >= k.size()) return null;
        double pv = 0, vv = 0;
        int from = Math.max(0, i - 287);
        for (int j = from; j <= i; j++) { Candle c = k.get(j); double tp = (c.h + c.l + c.c) / 3; pv += tp * c.v; vv += c.v; }
        if (vv <= 0) return null;
        double vwap = pv / vv;
        double var = 0; int n = 0;
        for (int j = from; j <= i; j++) { double d = k.get(j).c - vwap; var += d * d; n++; }
        double sd = Math.sqrt(var / Math.max(1, n));
        if (sd <= 0) return null;
        double g = 0, l = 0;
        for (int j = i - 13; j <= i; j++) { double ch = k.get(j).c - k.get(j - 1).c; if (ch > 0) g += ch; else l -= ch; }
        if (g + l == 0) return null;
        double rsi = 100 * g / (g + l);
        double[] adx = StrategyPack.adxAt(k, 56, i);
        if (adx == null || adx[0] >= X7_ADX_MAX) return null;   // regime gate: strong trend = fade NAHI
        Candle bar = k.get(i);
        if (bar.c < vwap - X7_SIGMA * sd && rsi < X7_RSI_LO) return "BUY";
        if (bar.c > vwap + X7_SIGMA * sd && rsi > X7_RSI_HI) return "SELL";
        return null;
    }

    /** X7 entry — SL 1×ATR, TP 2.5R, fee-edge, risk%/levCap sizing, per sym+tier 1 open. */
    private void openTradeX7(long uid, String sym, String side, List<Candle> k) {
        String tier = "X7:REGIME_FADE";
        if (!freshData(sym)) return;
        if (strategyPaused(tier)) return;
        if (entryBlocked(uid, sym)) return;
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }
        if (eventGateActive()) return;
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym, tier});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;
        Candle last = k.get(k.size() - 1);
        double atr = StrategyPack.atrAt(k, 14, k.size() - 1);
        if (!(atr > 0)) return;
        double price = last.c;
        double slDist = X7_SL_ATR * atr;
        if (!(slDist > 0) || price <= 0) return;
        double tpDist = X7_TP_R * slDist;
        if (!feeEdgeOk(tier + " " + sym, price, tpDist)) return;
        double heatCap = heatMaxPct(), bucketCap = bucketMaxPct();
        if (heatCap > 0 && heatRiskPct(uid) + riskPct() > heatCap) return;
        if (bucketCap > 0 && bucketRiskPct(uid, bucketOf(sym)) + riskPct() > bucketCap) return;
        boolean buy = "BUY".equals(side);
        price = slipEntry(price, side);
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * dynamicRiskPct(tier) / 100.0;
        double qty = risk / slDist;
        if (qty * price > bal * levCap()) qty = bal * levCap() / price;
        if (qty <= 0) return;
        double sl = buy ? price - slDist : price + slDist;
        double tp = buy ? price + tpDist : price - tpDist;
        JSONObject features = new JSONObject();
        try {
            features.put("x7", 1).put("atr", atr).put("tp_r", X7_TP_R).put("sl_atr", X7_SL_ATR)
                    .put("sigma", X7_SIGMA).put("be", 0).put("tf", TF).put("note", "VWAP 3.5σ + RSI confluence + ADX regime gate");
        } catch (Throwable ignored) { }
        double riskAmt = slDist * qty;
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)",
                new Object[]{uid, sym, side, qty, price, sl, tp, tier, 0.7, System.currentTimeMillis(), dynamicRiskPct(tier) / 100.0, riskAmt, price, 0, mlWinProb(features), features.toString()});
        recordOrder(0, uid, sym, side, "MARKET", price, qty, "PAPER", "FILLED");
        db.log("INFO", "X7", "ORDER_EXECUTED", sym + " " + side + " [" + tier + "] qty="
                + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(price) + " sl=" + fpx(sl)
                + " tp=" + fpx(tp) + " — VWAP σ-fade + RSI confluence, regime ADX<22 (TP +2.5R, NO BE)");
        try { Notifier.post(appContext(), "X7 Regime Fade", sym + " " + side + " — VWAP extreme + RSI confluence"); } catch (Throwable ignored) { }
    }

    // ================== v4.4 — AI TRAINER GLUE ==================
    private long lastAiTrainCheck = 0;
    volatile boolean aiTraining = false;   // package-private (Api status ke liye)

    /** Run-loop cadence: boot par (agar kabhi train nahi hua) + har 24h auto-retrain. */
    void aiTrainTick() {
        long now = System.currentTimeMillis();
        if (now - lastAiTrainCheck < 3600_000) return;
        lastAiTrainCheck = now;
        if (!"1".equals(db.setting("ai_auto_train", "1"))) return;
        long last = 0;
        try { last = Long.parseLong(db.setting("ai_trained_at", "0").trim()); } catch (Throwable ignored) { }
        if (now - last > 24L * 3600_000) trainAiAsync();
    }

    public void trainAiAsync() {
        if (aiTraining) return;
        aiTraining = true;
        Thread t = new Thread(() -> {
            try { trainAiBlocking(); }
            catch (Throwable e) { try { db.log("ERROR", "AI", "TRAIN_FAIL", String.valueOf(e)); } catch (Throwable ignored) { } }
            finally { aiTraining = false; }
        }, "ai-trainer");
        t.setDaemon(true);
        t.start();
    }

    /** Walk-forward training — Binance REAL history (15m execution depth + 1d HTF:
     *  BTC/ETH 2017 se — Binance ka purana data yahi hai; 2006-2016 me crypto
     *  exchanges exist hi nahi karte the). Weights settings me save + report. */
    public JSONObject trainAiBlocking() {
        List<String> pairs = new ArrayList<>();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE' ORDER BY priority DESC LIMIT 12", null);
        while (c.moveToNext()) pairs.add(c.getString(0));
        c.close();
        if (pairs.isEmpty()) pairs.addAll(BINANCE_PAIRS.keySet());
        String[] keys = new String[StrategyPack.KEYS.length + 5];
        System.arraycopy(StrategyPack.KEYS, 0, keys, 0, StrategyPack.KEYS.length);
        String[] shk = {"SHK1_SSM_BULL", "SHK2_SSM_BEAR", "SHK3_KZ_SWEEP", "SHK4_OB_RETEST", "SHK5_PD_EMA200"};
        System.arraycopy(shk, 0, keys, StrategyPack.KEYS.length, 5);
        Map<String, List<AiTrainer.T>> trades = new java.util.LinkedHashMap<>();
        for (String k : keys) trades.put(k, new ArrayList<>());
        double fee = takerFee();
        double slip = slipBps();
        long minTs = Long.MAX_VALUE, maxTs = 0;
        int pairsDone = 0;
        for (String sym : pairs) {
            try {
                List<Candle> k15 = deepKlines(sym, TF15, 4);   // ~41 din 15m execution depth
                if (k15.size() >= 400) {
                    accumulate(trades, keys, k15, fee, slip);
                    minTs = Math.min(minTs, k15.get(0).ts);
                    maxTs = Math.max(maxTs, k15.get(k15.size() - 1).ts);
                    pairsDone++;
                }
                if (pairs.indexOf(sym) < 6) {
                    List<Candle> k1d = deepKlines(sym, "1d", 4);   // 1d HTF — 2017 se listing tak
                    if (k1d.size() >= 260) accumulateDaily(trades, keys, k1d, fee, slip);
                }
            } catch (Throwable t) {
                db.log("WARN", "AI", "TRAIN_PAIR_FAIL", sym + " — " + t);
            }
        }
        if (minTs == Long.MAX_VALUE) minTs = System.currentTimeMillis() - 30L * 86400000L;
        if (maxTs == 0) maxTs = System.currentTimeMillis();
        long splitTs = minTs + (long) ((maxTs - minTs) * 0.7);
        JSONObject weights = new JSONObject();
        JSONObject reportStrats = new JSONObject();
        int onCount = 0;
        for (String key : keys) {
            List<AiTrainer.T> tl = trades.get(key);
            AiTrainer.Res r = new AiTrainer.Res();
            r.key = key;
            double[] st = AiTrainer.stats(tl);
            r.n = (int) st[0]; r.wr = st[1]; r.pf = st[2]; r.expR = st[3];
            double[] oo = AiTrainer.oosStats(tl, splitTs);
            r.nOos = (int) oo[0]; r.oosWr = oo[1]; r.oosPf = oo[2];
            r.weight = r.nOos > 0 ? AiTrainer.weightFrom(r.oosPf) : 1.0;
            r.enabled = AiTrainer.enabledFrom(r.nOos, r.oosPf);
            if (r.enabled == 1) onCount++;
            try {
                weights.put(key, AiTrainer.resJson(r));
                reportStrats.put(key, AiTrainer.resJson(r));
            } catch (Throwable ignored) { }
        }
        long now = System.currentTimeMillis();
        db.setSetting("ai_weights_v2", weights.toString());
        db.setSetting("ai_trained_at", String.valueOf(now));
        invalidateAiWeights();
        JSONObject report = new JSONObject();
        try {
            report.put("trained_at", now).put("pairs", pairsDone).put("from", minTs).put("to", maxTs)
                    .put("split_is_oos", "70/30").put("strategies", reportStrats)
                    .put("on", onCount).put("total", keys.length)
                    .put("note", "Risk 1% flat (owner rule) — weights sirf enable/disable + priority. OOS PF<0.9 = auto-pause. 1d data Binance listing (BTC 2017) se — 2006-2016 crypto exchange data exist nahi karta.");
        } catch (Throwable ignored) { }
        db.setSetting("ai_train_report", report.toString());
        db.log("INFO", "AI", "TRAIN_DONE", onCount + "/" + keys.length + " strategies ON — " + pairsDone
                + " pairs (15m depth + 1d HTF 2017→), fees+slip included, IS/OOS 70/30. AI ab proven configs par focus karega.");
        return report;
    }

    /** Ek pair ke 15m bars par SAB strategies ke signals EK pass me → per-key simulate. */
    private void accumulate(Map<String, List<AiTrainer.T>> trades, String[] keys, List<Candle> k, double fee, double slip) {
        double[][] pdMap = AiTrainer.prevDayMap(k);
        Map<String, java.util.SortedMap<Integer, StrategyPack.Signal>> byKey = new java.util.LinkedHashMap<>();
        for (String key : keys) byKey.put(key, new java.util.TreeMap<>());
        String[] shkKeys = {"SHK1_SSM_BULL", "SHK2_SSM_BEAR", "SHK3_KZ_SWEEP", "SHK4_OB_RETEST", "SHK5_PD_EMA200"};
        for (int i = 210; i < k.size() - 1; i++) {
            double[] adx = StrategyPack.adxAt(k, 14, i);
            double chopAdx = adx == null ? -1 : adx[0];
            for (StrategyPack.Signal s : StrategyPack.evaluateAll(k, i, pdMap[i], null, chopAdx)) {
                java.util.SortedMap<Integer, StrategyPack.Signal> m = byKey.get(s.strategy);
                if (m != null) m.put(i, s);
            }
            for (String shkKey : shkKeys)
                for (StrategyPack.Signal s : AiTrainer.shaakuniSignals(k, i, shkKey)) {
                    java.util.SortedMap<Integer, StrategyPack.Signal> m = byKey.get(shkKey);
                    if (m != null) m.put(i, s);
                }
        }
        for (String key : keys) {
            java.util.SortedMap<Integer, StrategyPack.Signal> m = byKey.get(key);
            if (m == null || m.isEmpty()) continue;
            List<AiTrainer.T> tl = AiTrainer.simulate(k, (kk, i) -> {
                StrategyPack.Signal s = m.get(i);
                return s == null ? java.util.Collections.<StrategyPack.Signal>emptyList() : java.util.Collections.singletonList(s);
            }, fee, slip);
            trades.get(key).addAll(tl);
        }
    }

    /** 1d bars par trend-family (S1/S3/S5/S8/S9) — 2017→2026 depth (BTC/ETH listing se). */
    private void accumulateDaily(Map<String, List<AiTrainer.T>> trades, String[] keys, List<Candle> k, double fee, double slip) {
        double[][] pdMap = AiTrainer.prevDayMap(k);
        String[] dailyKeys = {"S1_EMA_PULLBACK", "S3_SUPERTREND_ADX", "S5_PDH_PDL", "S8_DOW_PULLBACK", "S9_GANN_50"};
        for (String key : dailyKeys) {
            final String fk = key;
            List<AiTrainer.T> tl = AiTrainer.simulate(k, (kk, i) -> {
                List<StrategyPack.Signal> out = new ArrayList<>();
                if (i < pdMap.length) {
                    for (StrategyPack.Signal s : StrategyPack.evaluateAll(kk, i, pdMap[i], null, -1))
                        if (s.strategy.equals(fk)) out.add(s);
                }
                return out;
            }, fee, slip);
            trades.get(key).addAll(tl);
        }
    }

    // ================== v4.4 — SELF-LEARNING (har 25 closed trades) ==================
    void selfLearnTick() {
        long now = System.currentTimeMillis();
        long lastCheck = 0;
        try { lastCheck = Long.parseLong(db.setting("self_learn_at", "0").trim()); } catch (Throwable ignored) { }
        if (lastCheck == 0) { db.setSetting("self_learn_at", String.valueOf(now)); return; }
        if (now - lastCheck < 10 * 60_000L) return;   // 10-min cadence
        db.setSetting("self_learn_at", String.valueOf(now));
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND closed_at>?",
                new String[]{String.valueOf(lastCheck)});
        int closed = c.moveToFirst() ? c.getInt(0) : 0;
        c.close();
        if (closed < 25) return;
        reweightFromLive();
    }

    /** Live trades se per-strategy PF → weights blend (0.6 backtest + 0.4 live). */
    void reweightFromLive() {
        try {
            JSONObject w = aiWeights();
            if (w == null) return;
            JSONObject fresh = new JSONObject(w.toString());
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT strategy, pnl, risk_amt FROM trades WHERE status='CLOSED' AND strategy LIKE 'PDF:%' AND closed_at>? ORDER BY id DESC LIMIT 500",
                    new String[]{String.valueOf(System.currentTimeMillis() - 30L * 86400000L)});
            Map<String, List<Double>> byKey = new HashMap<>();
            while (c.moveToNext()) {
                String strat = c.getString(0);
                if (strat == null || !strat.contains(":")) continue;
                String key = strat.substring(strat.indexOf(':') + 1);
                double ra = c.getDouble(2);
                if (ra <= 0) continue;
                List<Double> l = byKey.get(key);
                if (l == null) { l = new ArrayList<>(); byKey.put(key, l); }
                l.add(c.getDouble(1) / ra);
            }
            c.close();
            if (byKey.isEmpty()) return;
            int paused = 0;
            for (Map.Entry<String, List<Double>> e : byKey.entrySet()) {
                if (!fresh.has(e.getKey())) continue;
                List<Double> rs = e.getValue();
                if (rs.size() < 10) continue;   // kam trades → backtest weight par bharosa
                double gw = 0, gl = 0;
                for (double r : rs) { if (r > 0) gw += r; else gl += -r; }
                double livePf = gl > 0 ? gw / gl : (gw > 0 ? 99 : 0);
                JSONObject row = fresh.getJSONObject(e.getKey());
                double btW = row.optDouble("w", 1.0);
                double liveW = AiTrainer.weightFrom(livePf);
                double blended = Math.round((0.6 * btW + 0.4 * liveW) * 100.0) / 100.0;
                int on = (rs.size() >= 15 && livePf < 0.7) ? 0 : row.optInt("on", 1);
                row.put("live_pf", Math.round(livePf * 100.0) / 100.0).put("live_n", rs.size())
                        .put("w", blended).put("on", on);
                if (on == 0) paused++;
            }
            db.setSetting("ai_weights_v2", fresh.toString());
            invalidateAiWeights();
            db.log("INFO", "AI", "SELF_LEARN", "25+ closed trades → re-weight: " + byKey.size()
                    + " PDF strategies live PF se blend (0.6 BT + 0.4 live), " + paused + " auto-paused (live PF<0.7, n≥15).");
        } catch (Throwable t) {
            db.log("WARN", "AI", "SELF_LEARN_FAIL", String.valueOf(t));
        }
    }

    // ===== v2.1 OWNER TRADING GATE =====
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

    /** 3C entry — one trade per setup per account, one open position per symbol.
     *  v3.0 QUANT PRO entry pipeline (order): SAFE MODE → trading gate → dedup →
     *  session/event/heat/bucket/council gates → slippage fill → journal (features,
     *  council, win_prob, risk_amt, decision) → order row → bridge mirror. */
    private void openTrade3C(long uid, String sym, Setup3C s, double fill, List<Candle> k, int idx) {
        if (!freshData(sym)) return;                        // v3.0 SAFE MODE — stale feed par entry nahi
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD (cooldown + daily kill)
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }   // v2.1 OWNER TRADING GATE
        if (inCmeHalt()) {                                  // v3.0 session filter (opt-in)
            log3C(sym, s, "ENTRY_BLOCKED", "CME maintenance halt (17:00-18:00 ET) — session filter ON hai");
            return;
        }
        if (eventGateActive()) {                            // v3.0 event gate (opt-in)
            log3C(sym, s, "ENTRY_BLOCKED", "HIGH-impact news <60 min — event gate ON hai (OPEC/CPI/FOMC gap protection)");
            return;
        }
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;                                   // one open position per symbol
        Cursor du = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND strategy LIKE '3C%' AND opened_at>=?",
                new String[]{String.valueOf(uid), sym, String.valueOf(s.c3Ts)});
        boolean dup = du.moveToFirst() && du.getInt(0) > 0;
        du.close();
        if (dup) return;                                    // ye setup pehle hi fire ho chuka
        // v3.0 — SIGNAL COUNCIL (3C rules unchanged; confidence tag + opt-in gate)
        int council = councilScore(sym, s.side, k, Math.max(0, idx));
        int cMin = councilMin();
        if (cMin > 0 && council < cMin) {
            log3C(sym, s, "COUNCIL_BLOCKED", "council " + council + "% < min " + cMin + "% — weak confluence, owner gate active");
            return;
        }
        // v3.0 — slippage/spread model: decision = trigger, fill = adverse slip
        double decision = fill;
        double fillSlip = slipEntry(fill, s.side);
        double riskDist = "BUY".equals(s.side) ? fillSlip - s.slPrice : s.slPrice - fillSlip;
        if (riskDist <= 0) return;
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        // v3.0 — PORTFOLIO HEAT + BUCKET CAPS (opt-in, default OFF — owner UNLIMITED)
        double heatCap = heatMaxPct(), bucketCap = bucketMaxPct();
        if (heatCap > 0) {
            double newHeat = heatRiskPct(uid) + riskPct();
            if (newHeat > heatCap) {
                db.log("INFO", "GUARD", "HEAT_CAP_BLOCKED", sym + " — heat " + String.format(Locale.US, "%.1f", newHeat)
                        + "% > cap " + String.format(Locale.US, "%.1f", heatCap) + "% (total open risk limit)");
                return;
            }
        }
        if (bucketCap > 0) {
            double newBucket = bucketRiskPct(uid, bucketOf(sym)) + riskPct();
            if (newBucket > bucketCap) {
                db.log("INFO", "GUARD", "BUCKET_CAP_BLOCKED", sym + " (" + bucketOf(sym) + ") — bucket heat "
                        + String.format(Locale.US, "%.1f", newBucket) + "% > cap " + String.format(Locale.US, "%.1f", bucketCap)
                        + "% (correlated exposure limit)");
                return;
            }
        }
        double risk = bal * dynamicRiskPct("3C_MASTER") / 100.0;
        double qty = risk / riskDist;
        if (qty * fillSlip > bal * levCap()) qty = bal * levCap() / fillSlip;
        if (qty <= 0) return;
        double tp = "BUY".equals(s.side) ? fillSlip + THREEC_TP_R * riskDist : fillSlip - THREEC_TP_R * riskDist;
        if (!feeEdgeOk("3C_MASTER " + sym, fillSlip, THREEC_TP_R * riskDist)) return;   // v4.4 fee-edge guard
        double riskAmt = Math.abs(fillSlip - s.slPrice) * qty;
        // v3.0 — setup DNA features + ML win probability (FreqAI-lite, experimental)
        java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        JSONObject features = new JSONObject();
        try {
            features.put("bd", Math.round(s.c3Body * 1000.0) / 1000.0)
                    .put("vr", Math.round(s.c3VolRatio * 1000.0) / 1000.0)
                    .put("ap", Math.round(s.c3AtrPct * 1000.0) / 1000.0)
                    .put("ed", Math.round(s.c3EmaDist * 1000.0) / 1000.0)
                    .put("rd", Math.round(s.c3RdPct * 1000.0) / 1000.0)
                    .put("hr", cal.get(java.util.Calendar.HOUR_OF_DAY))
                    .put("cs", council);
        } catch (Throwable ignored) { }
        double winProb = mlWinProb(features);
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)",
                new Object[]{uid, sym, s.side, qty, fillSlip, s.slPrice, tp, "3C_MASTER", 0, System.currentTimeMillis(),
                        dynamicRiskPct("3C_MASTER") / 100.0, riskAmt, decision, council, winProb, features.toString()});
        // order lifecycle row + bridge mirror
        long tradeId = 0;
        Cursor ti = db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
        if (ti.moveToFirst()) tradeId = ti.getLong(0);
        ti.close();
        recordOrder(tradeId, uid, sym, s.side, "STOP", decision, qty, "PAPER", "FILLED");
        bridgeOrder(sym, s.side, tradeId, uid, fillSlip, qty);
        db.log("INFO", "3C", "ORDER_EXECUTED",
                sym + " " + s.side + " qty=" + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(fillSlip)
                        + " (decision " + fpx(decision) + ", slip " + String.format(Locale.US, "%.1f", slipBps()) + "bps)"
                        + " SL=" + fpx(s.slPrice) + " TP=" + fpx(tp) + " (3R) risk=$"
                        + String.format(Locale.US, "%.2f", risk) + " (" + riskPct() + "% of $" + String.format(Locale.US, "%.2f", bal) + ")"
                        + " | council " + council + "%, ML winProb " + String.format(Locale.US, "%.0f%%", winProb * 100));
    }

    private double balanceOf(long uid) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT balance FROM accounts WHERE user_id=?",
                new String[]{String.valueOf(uid)});
        double b = c.moveToFirst() ? c.getDouble(0) : 0;
        c.close();
        return b;
    }

    private static String fpx(double v) {
        return String.format(Locale.US, v >= 100 ? "%.3f" : "%.6f", v);
    }

    private static String pct(double v) {
        return String.format(Locale.US, "%.1f", v * 100);
    }

    /** v1.2 — evaluate PAPER + ACTIVE custom strategies (Strategy Lab) on one symbol. */
    private void tryCustomStrategies(long uid, String sym, List<Candle> k) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT name, spec, status FROM strategies WHERE status IN ('PAPER','ACTIVE') AND deleted_at=0", null);
        List<Object[]> rows = new ArrayList<>();
        while (c.moveToNext()) rows.add(new Object[]{c.getString(0), c.getString(1), c.getString(2)});
        c.close();
        for (Object[] r : rows) {
            String name = (String) r[0], specRaw = (String) r[1], status = (String) r[2];
            try {
                org.json.JSONObject spec = new org.json.JSONObject(specRaw);
                int dir = StrategyLab.evaluateSpec(spec.optJSONArray("conditions"),
                        "ANY".equals(spec.optString("logic")) ? 1 : 0, k);
                if (dir == 0) continue;
                String specSide = spec.optString("side", "BOTH");
                if ("BUY".equals(specSide) && dir < 0) continue;
                if ("SELL".equals(specSide) && dir > 0) continue;
                String tier = ("ACTIVE".equals(status) ? "AI:LIVE:" : "AI:PAPER:") + name;
                openTradeLab(uid, sym, dir > 0 ? "BUY" : "SELL", k, tier);
            } catch (Throwable t) {
                db.log("ERROR", "LAB", "CUSTOM_EVAL_FAIL", name + " — " + t);
            }
        }
    }

    /** Lab strategy entry — ATR SL/TP model (1.5x / 2.5x), 1% risk, same guards as 3C.
     *  v3.0: SAFE MODE + session/event/heat/bucket gates + slippage + journal + orders. */
    private void openTradeLab(long uid, String sym, String side, List<Candle> k, String tier) {
        if (!freshData(sym)) return;                        // v3.0 SAFE MODE
        if (strategyPaused(tier)) {                         // v3.0 degradation auto-pause
            db.log("INFO", "GUARD", "STRATEGY_PAUSE_BLOCK", tier + " degraded-paused — entry blocked (Control me re-enable karein)");
            return;
        }
        if (entryBlocked(uid, sym)) return;                 // v1.7 PRO GUARD
        if (!tradingAllowed(uid)) { askOwnerToEnableTrading(uid); return; }   // v2.1 OWNER TRADING GATE
        if (inCmeHalt() || eventGateActive()) return;       // v3.0 session + event gates (opt-in)
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;
        double price = k.get(k.size() - 1).c;
        // v3.0 — council + heat/bucket caps (Lab strategies bhi discipline ke daayre mein)
        int council = councilScore(sym, side, k, k.size() - 1);
        int cMin = councilMin();
        if (cMin > 0 && council < cMin) return;
        double heatCap = heatMaxPct(), bucketCap = bucketMaxPct();
        if (heatCap > 0 && heatRiskPct(uid) + 1.0 > heatCap) return;      // Lab 1% risk model
        if (bucketCap > 0 && bucketRiskPct(uid, bucketOf(sym)) + 1.0 > bucketCap) return;
        double a = atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return;
        double decision = price;
        price = slipEntry(price, side);                     // v3.0 slippage
        double sl = "BUY".equals(side) ? price - 1.5 * a : price + 1.5 * a;
        double tp = "BUY".equals(side) ? price + 2.5 * a : price - 2.5 * a;
        if (!feeEdgeOk(tier + " " + sym, price, 2.5 * a)) return;   // v4.4 fee-edge guard
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * dynamicRiskPct(tier) / 100.0;   // v4.1: min-25 → consensus scaling, base 1%
        double qty = risk / (1.5 * a);
        if (qty * price > bal * levCap()) qty = bal * levCap() / price;
        if (qty <= 0) return;
        double riskAmt = Math.abs(price - sl) * qty;
        java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        JSONObject features = new JSONObject();
        try {
            features.put("bd", Math.round(bodyPct(k.get(k.size() - 1)) * 1000.0) / 1000.0)
                    .put("ap", Math.round(a / price * 100000.0) / 1000.0)
                    .put("rd", Math.round(Math.abs(price - sl) / price * 100000.0) / 1000.0)
                    .put("hr", cal.get(java.util.Calendar.HOUR_OF_DAY)).put("cs", council);
        } catch (Throwable ignored) { }
        double winProb = mlWinProb(features);
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk, risk_amt, decision, council, win_prob, features) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?,?,?,?,?,?)",
                new Object[]{uid, sym, side, qty, price, sl, tp, tier, 0.65, System.currentTimeMillis(), dynamicRiskPct(tier) / 100.0, riskAmt, decision, council, winProb, features.toString()});
        long tradeId = 0;
        Cursor ti = db.getReadableDatabase().rawQuery("SELECT MAX(id) FROM trades", null);
        if (ti.moveToFirst()) tradeId = ti.getLong(0);
        ti.close();
        recordOrder(tradeId, uid, sym, side, "MARKET", decision, qty, "PAPER", "FILLED");
        bridgeOrder(sym, side, tradeId, uid, price, qty);
        db.log("INFO", "LAB", "ORDER_EXECUTED", sym + " " + side + " [" + tier + "] qty="
                + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(price)
                + " (Lab strategy signal — ATR SL/TP, 1% risk, council " + council + "%)");
    }

    private void manageOpenTrades() {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, user_id, symbol, side, qty, entry, sl, tp, strategy FROM trades WHERE status='OPEN'", null);
        List<Object[]> rows = new ArrayList<>();
        while (c.moveToNext()) {
            rows.add(new Object[]{c.getLong(0), c.getLong(1), c.getString(2), c.getString(3),
                    c.getDouble(4), c.getDouble(5), c.getDouble(6), c.getDouble(7), c.getString(8)});
        }
        c.close();
        for (Object[] r : rows) {
            long id = (Long) r[0], uid = (Long) r[1];
            String sym = (String) r[2], side = (String) r[3], strategy = (String) r[8];
            double qty = (Double) r[4], entry = (Double) r[5], sl = (Double) r[6], tp = (Double) r[7];
            // v3.0 SAFE MODE — stale feed par SL/TP evaluation FREEZE (purani candle par
            // false trigger se bachne ke liye). freshData() safeMode flag bhi set karta hai.
            if (!freshData(sym)) continue;
            // v1.5 — CLOSED + LIVE (in-progress) candle dono par stop-order semantics:
            // SL/TP/breakeven ab candle close ka intezaar nahi karte — 10s scan par turant.
            // Conservative same-candle order: SL pehle, TP baad mein (kabhi optimistic nahi).
            double[][] candles2 = new double[2][];
            Cursor cc = db.getReadableDatabase().rawQuery(
                    "SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                    new String[]{sym, TF, String.valueOf(System.currentTimeMillis() - TF_MS)});
            if (cc.moveToFirst()) candles2[0] = new double[]{cc.getDouble(0), cc.getDouble(1)};
            cc.close();
            Cursor lc = db.getReadableDatabase().rawQuery(
                    "SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts>? ORDER BY ts DESC LIMIT 1",
                    new String[]{sym, TF, String.valueOf(System.currentTimeMillis() - TF_MS)});
            if (lc.moveToFirst()) candles2[1] = new double[]{lc.getDouble(0), lc.getDouble(1)};
            lc.close();
            boolean buy = "BUY".equals(side);
            boolean is3C = strategy != null && strategy.startsWith("3C");
            boolean isPack = strategy != null && strategy.startsWith("PDF:");
            boolean isPB = strategy != null && strategy.startsWith("PB:");
            double rDist = isPack ? Math.abs(tp - entry) / 2.0 : Math.abs(tp - entry) / THREEC_TP_R;   // v4.4: pack TP=+2R
            // v4.4 — PDF pack trades: boundary invalidation + window expiry (15m rules)
            if (isPack) {
                try {
                    Cursor fc = db.getReadableDatabase().rawQuery("SELECT features FROM trades WHERE id=?", new String[]{String.valueOf(id)});
                    String feats = fc.moveToFirst() ? fc.getString(0) : "{}";
                    fc.close();
                    JSONObject ft = new JSONObject(feats);
                    double boundary = ft.optDouble("boundary", 0);
                    long sigTs = ft.optLong("sig_ts", 0);
                    int winBars = ft.optInt("window_bars", 5);
                    if (boundary > 0) {
                        Cursor b15 = db.getReadableDatabase().rawQuery(
                                "SELECT c FROM candles WHERE symbol=? AND tf='15m' AND ts<=? ORDER BY ts DESC LIMIT 1",
                                new String[]{sym, String.valueOf(System.currentTimeMillis() - TF15_MS)});
                        double c15 = b15.moveToFirst() ? b15.getDouble(0) : 0;
                        b15.close();
                        if (c15 > 0) {
                            boolean invalid = buy ? c15 < boundary : c15 > boundary;
                            if (invalid) {
                                db.log("INFO", "PACK", "SETUP_INVALIDATED", "trade #" + id + " " + sym + " — 15m close " + fpx(c15)
                                        + " boundary " + fpx(boundary) + " ke paar (PDF invalidation) — close @market");
                                closeTrade(id, uid, livePrice(sym), "BOUNDARY", qty, entry, side);
                                continue;
                            }
                        }
                    }
                    if (sigTs > 0 && System.currentTimeMillis() > sigTs + (winBars + 2L) * TF15_MS) {
                        db.log("INFO", "PACK", "SETUP_EXPIRED", "trade #" + id + " " + sym + " — " + winBars + "×15m window khatam bina move ke — flat exit");
                        closeTrade(id, uid, livePrice(sym), "WINDOW", qty, entry, side);
                        continue;
                    }
                } catch (Throwable ignored) { }
            }
            // v1.0 — PLAYBOOK trades: apna trail-based management (guide exit rule) —
            // generic SL/TP/BE loop se alag (PB me TP nahi hota, trail hi exit hai).
            if (isPB) {
                managePbTrade(id, uid, sym, side, qty, entry, sl, buy);
                continue;
            }
            boolean done = false;
            for (double[] hl : candles2) {
                if (hl == null || done) continue;
                double hi = hl[0], lo = hl[1];
                // v3.0 — MFE/MAE journal (professional trade analytics: trade ne apni
                // zindagi mein kitna favor/adverse move diya — SL/TP tuning ka data)
                double mfe = buy ? (hi - entry) * qty : (entry - lo) * qty;
                double mae = buy ? (entry - lo) * qty : (hi - entry) * qty;
                db.getWritableDatabase().execSQL(
                        "UPDATE trades SET mfe=MAX(IFNULL(mfe,0),?), mae=MAX(IFNULL(mae,0),?) WHERE id=?",
                        new Object[]{Math.max(0, mfe), Math.max(0, mae), id});
                boolean hitSl = buy ? lo <= sl : hi >= sl;
                boolean hitTp = buy ? hi >= tp : lo <= tp;
                if (hitSl || hitTp) {
                    closeTrade(id, uid, hitSl ? sl : tp, hitSl ? "SL" : "TP", qty, entry, side);
                    done = true;
                    continue;
                }
                // 3C/PACK management: +1R par WHOLE position ka SL breakeven par (3C TP=3R, pack TP=2R)
                // v1.1 — X7 REGIME FADE par BE NAHI (tuned: BE-off better expectancy)
                if ((is3C || isPack) && !(strategy != null && strategy.startsWith("X7"))) {
                    boolean beMoved = buy ? sl >= entry : sl <= entry;      // SL pehle se entry par?
                    boolean beHit = buy ? hi >= entry + rDist : lo <= entry - rDist;
                    if (!beMoved && beHit && rDist > 0) {
                        db.getWritableDatabase().execSQL("UPDATE trades SET sl=? WHERE id=?", new Object[]{entry, id});
                        sl = entry;   // live-candle pass ko updated SL dikhe (double BE move na ho)
                        db.log("INFO", "3C", "TRADE_MANAGED",
                                "trade #" + id + " " + sym + " — +1R hit — SL moved to breakeven " + fpx(entry) + " (whole position, no partial TP)");
                    }
                }
            }
        }
    }

    private void closeTrade(long id, long uid, double price, String reason, double qty, double entry, String side) {
        // v3.0 — slippage on EXIT (single application point: SL/TP/manual sab yahan se guzarte)
        double exitFill = slipExit(price, side);
        // v1.7 PRO GUARD — fee modeling (freqtrade-style): entry + exit dono sides par
        // Taker fee 0.05% per side. Paper results ab real trading jaise realistic.
        double fees = (qty * entry + qty * exitFill) * takerFee();
        double pnl = ("BUY".equals(side) ? exitFill - entry : entry - exitFill) * qty - fees;
        // v3.0 — journal: R-multiple + TCA (decision vs fill, professional slippage tracking)
        Cursor jc = db.getReadableDatabase().rawQuery(
                "SELECT risk_amt, decision, features FROM trades WHERE id=?", new String[]{String.valueOf(id)});
        double riskAmt = 0, decisionP = 0; String feats = "{}";
        if (jc.moveToFirst()) { riskAmt = jc.getDouble(0); decisionP = jc.getDouble(1); feats = jc.getString(2); }
        jc.close();
        boolean buy = "BUY".equals(side);
        double rMult = riskAmt > 0 ? pnl / riskAmt : 0;
        double tcaBps = decisionP > 0 ? ((buy ? exitFill - decisionP : decisionP - exitFill) / decisionP) * 10000.0 : 0;
        db.getWritableDatabase().execSQL(
                "UPDATE trades SET exit=?, pnl=?, status='CLOSED', closed_at=?, r_mult=?, tca_bps=? WHERE id=?",
                new Object[]{exitFill, pnl, System.currentTimeMillis(), Math.round(rMult * 1000.0) / 1000.0, Math.round(tcaBps * 100.0) / 100.0, id});
        db.getWritableDatabase().execSQL(
                "UPDATE accounts SET balance = balance + ? WHERE user_id=?", new Object[]{pnl, uid});
        recordOrder(id, uid, "", "EXIT_" + reason, "MARKET", exitFill, qty, "PAPER", "FILLED");
        bridgeClose("", id, uid);
        db.log(reason.equals("SL") ? "WARN" : "INFO", "EXECUTOR", "TRADE_CLOSED_" + reason,
                "trade #" + id + " exit=" + fpx(exitFill) + " (level " + fpx(price) + ", slip " + String.format(Locale.US, "%.1f", slipBps()) + "bps) pnl=" + String.format("%.2f", pnl)
                        + " = " + String.format(Locale.US, "%.2f", rMult) + "R, fees $" + String.format("%.4f", fees)
                        + " @ " + pct(takerFee()) + "%/side, TCA " + String.format(Locale.US, "%.1f", tcaBps) + "bps");
        // v3.0 — ML retrain cadence: har 20 feature-tagged closed trades par
        try {
            if (feats != null && !"{}".equals(feats)) {
                long n = Long.parseLong(db.setting("ml_n", "0")) + 1;
                db.setSetting("ml_n", String.valueOf(n));
                if (n % 20 == 0) mlTrain();
            }
        } catch (Throwable ignored) { }
        // v1.7 — SL loss par protections trigger: cooldown + consecutive-loss guard
        if ("SL".equals(reason) && pnl < 0) {
            String sym = tradeSymbol(id);
            if (sym != null) {
                int cm = cooldownMin();
                if (cm > 0) {
                    long until = System.currentTimeMillis() + cm * 60_000L;
                    cooldownUntil.put(uid + ":" + sym, until);
                    cooldownLogged.remove(uid + ":" + sym); // naya cooldown = fresh log
                    saveGuardState();                        // v3.0 — persistent guards
                    db.log("WARN", "GUARD", "COOLDOWN_SET", sym + " — SL loss ke baad "
                            + cm + " min tak naya entry band (freqtrade CooldownPeriod)");
                }
                checkConsecutiveLoss(uid, sym);
            }
        }
    }

    /** trade ki symbol nikalo (v1.7 guard ke liye). */
    private String tradeSymbol(long id) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT symbol FROM trades WHERE id=?",
                new String[]{String.valueOf(id)});
        String s = c.moveToFirst() ? c.getString(0) : null;
        c.close();
        return s;
    }

    /** v1.7 StoplossGuard — ek symbol par lagatar N SL losses = 1 ghanta cooldown. */
    private void checkConsecutiveLoss(long uid, String sym) {
        int n = consecLossN();
        if (n <= 0) return;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT pnl FROM trades WHERE user_id=? AND symbol=? AND status='CLOSED' "
                        + "ORDER BY closed_at DESC LIMIT ?",
                new String[]{String.valueOf(uid), sym, String.valueOf(n)});
        int cnt = 0;
        boolean allLoss = c.moveToFirst();
        while (allLoss && cnt < n && c.getDouble(0) < 0) { cnt++; if (!c.moveToNext()) break; }
        c.close();
        if (cnt >= n) {
            long until = System.currentTimeMillis() + CONSEC_LOSS_COOLDOWN_MS;
            String key = uid + ":" + sym;
            if (until > cooldownUntil.getOrDefault(key, 0L)) cooldownUntil.put(key, until);
            cooldownLogged.remove(key);
            db.log("WARN", "GUARD", "CONSEC_LOSS_PAUSE", sym + " — " + n
                    + " lagatar SL losses: 1 ghanta trading pause (freqtrade StoplossGuard)");
        }
    }

    /**
     * v1.7 PRO GUARD — entry se pehle teen professional checks (freqtrade-inspired).
     * Sirf NAYE entries block hoti hain — khuli positions ka SL/TP/breakeven normal
     * chalta rehta hai. 3C setups aage bhi arm hote rehte hain (discard nahi hote),
     * cooldown khatam hote hi valid setup se trade khul sakti hai.
     */
    private boolean entryBlocked(long uid, String sym) {
        long now = System.currentTimeMillis();
        String key = uid + ":" + sym;
        // 1) CooldownPeriod — SL loss ke baad symbol par naya entry band
        Long until = cooldownUntil.get(key);
        if (until != null && until > now) {
            if (cooldownLogged.add(key)) {
                long mins = (until - now) / 60000L + 1;
                db.log("INFO", "GUARD", "ENTRY_COOLDOWN_BLOCKED",
                        sym + " — cooldown active, " + mins + " min baakI (loss ke baad thanda waqt)");
            }
            return true;
        }
        if (until != null && until <= now) cooldownUntil.remove(key); // expired — clear
        // 2) Daily kill switch (opt-in, default OFF — owner ne UNLIMITED manga tha)
        double kill = dailyKillPct();
        if (kill > 0) {
            long dayStart = now / 86400000L * 86400000L; // UTC day
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT IFNULL(SUM(pnl),0) FROM trades WHERE user_id=? AND status='CLOSED' AND closed_at>=?",
                    new String[]{String.valueOf(uid), String.valueOf(dayStart)});
            double dayPnl = c.moveToFirst() ? c.getDouble(0) : 0;
            c.close();
            double eq = balanceOf(uid) - dayPnl; // day-start equity (approx)
            if (eq > 0 && dayPnl <= -eq * kill / 100.0) {
                String dayKey = uid + ":" + (dayStart / 86400000L);
                if (killLogged.add(dayKey)) {
                    db.log("WARN", "GUARD", "DAILY_KILL_SWITCH",
                            "Aaj ka P/L $" + String.format("%.2f", dayPnl) + " — daily -" + pct(kill / 100)
                                    + "% guard trigger: aaj ke naye entries band, kal UTC reset");
                    Notifier.post(appContext(), "PRO GUARD", "Daily loss limit hit — aaj ke naye entries band (open trades ka SL/TP chal raha hai)");
                }
                return true;
            }
        }
        return false;
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
        // v3.0 TRUE DRAWDOWN (audit fix #10): accounts.peak ab har loop par equity-highs
        // par RATCHET hota hai (balance + floating P/L) — dashboard ka Drawdown ab
        // actual peak-to-now drawdown hai, (balance-start)/start ka jhoota number nahi.
        try {
            Cursor ac = db.getReadableDatabase().rawQuery(
                    "SELECT a.user_id, a.balance, a.peak FROM accounts a", null);
            List<Object[]> accs = new ArrayList<>();
            while (ac.moveToNext()) accs.add(new Object[]{ac.getLong(0), ac.getDouble(1), ac.getDouble(2)});
            ac.close();
            for (Object[] a : accs) {
                long uid = (Long) a[0];
                double bal = (Double) a[1], peak = (Double) a[2];
                double floating = 0;
                Cursor fc = db.getReadableDatabase().rawQuery(
                        "SELECT symbol, side, qty, entry FROM trades WHERE user_id=? AND status='OPEN'",
                        new String[]{String.valueOf(uid)});
                while (fc.moveToNext()) {
                    double p = livePrice(fc.getString(0));
                    if (!Double.isNaN(p))
                        floating += ("BUY".equals(fc.getString(1)) ? p - fc.getDouble(3) : fc.getDouble(3) - p) * fc.getDouble(2);
                }
                fc.close();
                double eqNow = bal + floating;
                if (eqNow > peak)
                    db.getWritableDatabase().execSQL("UPDATE accounts SET peak=? WHERE user_id=?",
                            new Object[]{eqNow, uid});
            }
        } catch (Throwable ignored) { }
        // v1.0 BUGFIX: the equity table grew forever (a row every 30s scan). Keep the
        // most recent 2000 points (~16h of scans); the dashboard reads the last 48.
        try {
            db.getWritableDatabase().execSQL(
                    "DELETE FROM equity WHERE ts NOT IN (SELECT ts FROM equity ORDER BY ts DESC LIMIT 2000)");
        } catch (Throwable ignored) { }
    }

    // ================== INSTRUMENT UNIVERSE (v4.1 BINANCE 7 PAIRS) ==================
    /** v4.0+ owner request: MT5 commodities retired — BINANCE SPOT 7 pairs (1m).
     *  Bucket model: MAJOR (BTC/ETH/BNB/SOL — deep liquidity) vs RETAIL (XRP/DOGE/ADA).
     *  Crypto 24/7 chalta hai — market band nahi hota. */
    static final String[][] BINANCE_UNIVERSE = {
            {"BTCUSDT", "MAJOR", "Bitcoin — Binance spot"},
            {"ETHUSDT", "MAJOR", "Ethereum — Binance spot"},
            {"BNBUSDT", "MAJOR", "BNB — Binance spot"},
            {"SOLUSDT", "MAJOR", "Solana — Binance spot"},
            {"XRPUSDT", "RETAIL", "XRP — Binance spot"},
            {"DOGEUSDT", "RETAIL", "Dogecoin — Binance spot"},
            {"ADAUSDT", "RETAIL", "Cardano — Binance spot"}
    };

    private void seedStaticInstruments() {
        android.database.sqlite.SQLiteDatabase d = db.getWritableDatabase();
        long now = System.currentTimeMillis();
        for (String[] s : BINANCE_UNIVERSE) {
            d.execSQL("INSERT OR IGNORE INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?, 'USDT','BINANCE',?,'ACTIVE',5000,?,?)",
                    new Object[]{s[0], s[0], s[1], now, s[2]});
        }
        // upgrade path: Binance universe force-ACTIVE + purane MT5 symbols RETIRED
        StringBuilder in = new StringBuilder();
        for (String[] s : BINANCE_UNIVERSE) {
            if (in.length() > 0) in.append(',');
            in.append('\'').append(s[0]).append('\'');
        }
        d.execSQL("UPDATE instruments SET status='ACTIVE', exchange='BINANCE' WHERE symbol IN (" + in + ")");
        // v4.4 — sirf non-Binance retire (ALL-Binance universe discover() sync karta hai)
        try { d.execSQL("UPDATE instruments SET status='RETIRED' WHERE exchange IS NOT NULL AND exchange<>'BINANCE'"); } catch (Throwable ignored) { }
        for (String[] s : BINANCE_UNIVERSE) {
            synchronized (binanceOkCache) { binanceOkCache.add(s[0]); }
            synchronized (BUCKET) { BUCKET.put(s[0], s[1]); }
        }
        if (!"1".equals(db.setting("seeded_v44", "0"))) {
            db.setSetting("seeded_v44", "1");
            db.log("INFO", "DISCOVERY", "BINANCE_SEED", "v4.4 ALL-BINANCE universe: seed 7 pairs + exchangeInfo se SAARE USDT spot pairs (volume-ranked MAJOR/RETAIL/ALTCOIN). Owner: 'saare binance ke coins daalo, baki sab delete'.");
        }
    }

    /** v4.4 universe sync state. */
    private long lastUniverseSync = 0;

    /** exchangeInfo + 24hr tickers → SAARE USDT spot pairs instruments me (volume-ranked).
     *  Leveraged tokens (UP/DOWN/BULL/BEAR) + stable-stable pairs exclude. */
    private void syncBinanceUniverse() {
        try {
            String ei = httpGetUrl(BINANCE_HOST + "/api/v3/exchangeInfo", 15000);
            String tk = httpGetUrl(BINANCE_HOST + "/api/v3/ticker/24hr", 20000);
            if (ei == null || tk == null) return;
            java.util.Set<String> spot = new java.util.HashSet<>();
            org.json.JSONArray syms = new org.json.JSONObject(ei).getJSONArray("symbols");
            for (int i = 0; i < syms.length(); i++) {
                org.json.JSONObject s = syms.getJSONObject(i);
                if (!"TRADING".equals(s.optString("status"))) continue;
                if (!"USDT".equals(s.optString("quoteAsset"))) continue;
                if (!s.optBoolean("isSpotTradingAllowed", true)) continue;
                String base = s.optString("baseAsset", "").toUpperCase(Locale.ROOT);
                if (base.endsWith("UP") || base.endsWith("DOWN") || base.endsWith("BULL") || base.endsWith("BEAR")) continue;
                if (STABLE_BASES.contains(base)) continue;
                spot.add(s.optString("symbol"));
            }
            if (spot.isEmpty()) return;
            org.json.JSONArray tick = new org.json.JSONArray(tk);
            List<Object[]> vols = new ArrayList<>();
            for (int i = 0; i < tick.length(); i++) {
                org.json.JSONObject t = tick.getJSONObject(i);
                String sym = t.optString("symbol");
                if (!spot.contains(sym)) continue;
                vols.add(new Object[]{sym, t.optDouble("quoteVolume", 0)});
            }
            vols.sort((a, b) -> Double.compare((Double) b[1], (Double) a[1]));
            android.database.sqlite.SQLiteDatabase d = db.getWritableDatabase();
            long now = System.currentTimeMillis();
            int rank = 0, added = 0;
            synchronized (binanceOkCache) { binanceOkCache.clear(); }
            for (Object[] v : vols) {
                rank++;
                String sym = (String) v[0];
                double vol = (Double) v[1];
                String bucket = bucketForRank(rank);
                int priority = (int) Math.min(2_000_000_000L, Math.max(0, Math.log10(Math.max(vol, 1)) * 1000));
                String note = sym.replace("USDT", "") + "/USDT — Binance spot (rank " + rank + ", " + bucket + ")";
                synchronized (binanceOkCache) { binanceOkCache.add(sym); }
                synchronized (BUCKET) { BUCKET.put(sym, bucket); }
                try {
                    d.execSQL("INSERT INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,'USDT','BINANCE','CRYPTO','ACTIVE',?,?,?) " +
                            "ON CONFLICT(symbol) DO UPDATE SET status='ACTIVE', exchange='BINANCE', priority=?, note=?",
                            new Object[]{sym, sym.replace("USDT", ""), priority, now, note, priority, note});
                    added++;
                } catch (Throwable dupEx) {
                    try {   // older SQLite: update + insert fallback
                        android.content.ContentValues cv = new android.content.ContentValues();
                        cv.put("status", "ACTIVE");
                        cv.put("exchange", "BINANCE");
                        cv.put("priority", priority);
                        cv.put("note", note);
                        int n = d.update("instruments", cv, "symbol=?", new String[]{sym});
                        if (n == 0) d.execSQL("INSERT INTO instruments(symbol, base, quote, exchange, asset_class, status, priority, discovered_at, note) VALUES(?,?,'USDT','BINANCE','CRYPTO','ACTIVE',?,?,?)",
                                new Object[]{sym, sym.replace("USDT", ""), priority, now, note});
                        added++;
                    } catch (Throwable ignored) { }
                }
            }
            try { d.execSQL("UPDATE instruments SET status='RETIRED' WHERE exchange IS NOT NULL AND exchange<>'BINANCE'"); } catch (Throwable ignored) { }
            lastUniverseSync = now;
            db.log("INFO", "DISCOVERY", "BINANCE_UNIVERSE_SYNC", added + " USDT spot pairs ACTIVE (volume-ranked: MAJOR top-10, RETAIL 11-60, ALTCOIN 61+) — 15m PDF pack SAB par, 1m scan top-40 par");
        } catch (Throwable t) {
            db.log("WARN", "DISCOVERY", "UNIVERSE_SYNC_FAIL", String.valueOf(t));
        }
    }

    /** v2.1 — universe maintenance (Binance auto-discovery retired): halal list fixed.
     *  Data 6h+ purana (market band) -> WATCHING; data fresh -> ACTIVE. Koi naya
     *  symbol auto-register NAHI hota — universe sirf owner ke hukum se badalta hai. */
    private void discover() {
        long now = System.currentTimeMillis();
        if (now - lastUniverseSync > 6L * 3600_000) syncBinanceUniverse();   // v4.4 ALL-Binance sync (har 6h)
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

    // ================== NEWS ENGINE ==================
    // v4.1 BINANCE MODE — crypto news sources (commodities RSS retired)
    private static final String[] FEEDS = {
            "https://www.coindesk.com/arc/outboundfeeds/rss/",   // crypto market news
            "https://cointelegraph.com/rss"                      // crypto / bitcoin
    };
    private static final String[] BULL = {"surge", "rally", "gain", "record", "adopt", "approval", "approved", "bullish", "soar", "jump", "rise", "up", "inflow", "upgrade", "breakout"};
    private static final String[] BEAR = {"crash", "plunge", "ban", "hack", "lawsuit", "drop", "fall", "bearish", "sink", "loss", "outflow", "downgrade", "sell-off", "fear"};
    private static final String[] HIGH_IMPACT = {"fed", "fomc", "rate", "cpi", "inflation", "sec", "etf", "binance", "hack", "war", "sanction", "tariff", "default", "emergency"};

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
                // v1.4 — high-impact news sirf DISPLAY hoti hai. 3C entry kabhi news se
                // block nahi hoti (owner: unlimited trading, sirf strategy rules chalenge).
                if ("HIGH".equals(impact)) {
                    db.log("INFO", "NEWS", "HIGH_IMPACT", "display-only — entries NOT paused (" + title.substring(0, Math.min(60, title.length())) + ")");
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

    // ================== v3.0 QUANT PRO CORE ==================
    // Roadmap: v2.2 PRO RISK + v2.3 HONEST LAB support + v2.5 AI QUANT CORE + v3.0 LIVE READY.
    // 3C MASTER rules untouched — ye sab strategy ke AAS PAAS ki discipline hai.

    /** symbol -> correlated bucket (MAJOR/RETAIL) — LEAN sector-exposure parity. */
    private static final java.util.Map<String, String> BUCKET = new HashMap<>();
    static { for (String[] s : BINANCE_UNIVERSE) BUCKET.put(s[0], s[1]); }

    /** Latest price for a symbol (most recent candle close incl. live candle) — heat/DD ke liye. */
    private double livePrice(String sym) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT c FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT 1", new String[]{sym, TF});
        double p = Double.NaN;
        if (c.moveToFirst()) p = c.getDouble(0);
        c.close();
        return p;
    }

    static String bucketOf(String sym) { return BUCKET.getOrDefault(sym, "MAJOR"); }   // v4.1: fallback MAJOR (Binance universe)

    /** Adverse slippage on ENTRY: BUY thoda zyada par khareedta hai, SELL thoda kam par. */
    private double slipEntry(double p, String side) {
        double s = slipBps() / 10000.0;
        return "BUY".equals(side) ? p * (1 + s) : p * (1 - s);
    }

    /** Adverse slippage on EXIT: BUY thoda kam par bechta hai, SELL thoda zyada par. */
    private double slipExit(double p, String side) {
        double s = slipBps() / 10000.0;
        return "BUY".equals(side) ? p * (1 - s) : p * (1 + s);
    }

    /** Portfolio HEAT = total open risk (|entry-sl|*qty) / equity * 100 (per user).
     *  Professional prop desks 6-10% heat par cap lagate hain — hum default OFF. */
    public double heatRiskPct(long uid) {
        double floating = 0;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol, side, qty, entry, sl, status FROM trades WHERE user_id=? AND status='OPEN'",
                new String[]{String.valueOf(uid)});
        double risk = 0;
        while (c.moveToNext()) {
            String sym = c.getString(0), side = c.getString(1);
            double qty = c.getDouble(2), entry = c.getDouble(3), sl = c.getDouble(4);
            risk += Math.abs(entry - sl) * qty;
            double p = livePrice(sym);
            if (!Double.isNaN(p)) floating += ("BUY".equals(side) ? p - entry : entry - p) * qty;
        }
        c.close();
        double eq = balanceOf(uid) + floating;
        return eq > 0 ? risk / eq * 100.0 : 0;
    }

    /** Ek bucket (METAL/ENERGY/AGRI) ka total open risk % — correlated exposure. */
    public double bucketRiskPct(long uid, String bucket) {
        double floating = 0;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol, side, qty, entry, sl, status FROM trades WHERE user_id=? AND status='OPEN'",
                new String[]{String.valueOf(uid)});
        double risk = 0;
        while (c.moveToNext()) {
            if (!bucket.equals(bucketOf(c.getString(0)))) continue;
            double qty = c.getDouble(2), entry = c.getDouble(3), sl = c.getDouble(4);
            risk += Math.abs(entry - sl) * qty;
            double p = livePrice(c.getString(0));
            if (!Double.isNaN(p)) floating += ("BUY".equals(c.getString(1)) ? p - entry : entry - p) * qty;
        }
        c.close();
        double eq = balanceOf(uid) + floating;
        return eq > 0 ? risk / eq * 100.0 : 0;
    }

    /** STALE-DATA GUARD (v4.4.2 REWORK — "data nahi araha hai" flap fix):
     *  Purana design: EK bhi symbol stale ho to GLOBAL safeMode latch ho jata tha aur
     *  mixed fresh/stale universe me flag har 10s tick par ON/OFF flapp karta tha —
     *  dashboard baar-baar "SAFE MODE — data nahi aa raha" banner dikhaata tha.
     *  Ab: freshData sirf PER-SYMBOL entry gate hai (stale symbol par hi entry nahi,
     *  uska SL/TP freeze). Global SAFE MODE sirf updateFeedHealth() (quorum latch)
     *  set karta hai — poora feed out ho tabhi. */
    private boolean freshData(String sym) {
        long bars = 3;
        try { bars = Math.max(2, Integer.parseInt(db.setting("safe_mode_bars", "3").trim())); } catch (Exception ignored) { }
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts FROM candles WHERE symbol=? AND tf=? ORDER BY ts DESC LIMIT 1",
                new String[]{sym, TF});
        boolean fresh = false;
        if (c.moveToFirst()) fresh = System.currentTimeMillis() - c.getLong(0) < bars * TF_MS;
        c.close();
        return fresh;
    }

    /** v4.4.2 — global feed health (SAFE MODE quorum latch). refreshCandles() ke end me
     *  call: active symbols ki newest TF candle age dekh kar fresh ratio nikaalta hai.
     *  Latch ON sirf jab >=5 symbols checked aur <=20% fresh (asli feed outage);
     *  clear jab >=60% fresh. Ek-do delisted/low-liq pairs ab flag flapp nahi karte. */
    private void updateFeedHealth() {
        try {
            int checked = 0, freshCnt = 0;
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT symbol, MAX(ts) FROM candles WHERE tf='" + TF + "' AND symbol IN (SELECT symbol FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE') GROUP BY symbol", null);
            long now = System.currentTimeMillis();
            while (c.moveToNext() && checked < 200) {
                checked++;
                if (now - c.getLong(1) < 3 * TF_MS) freshCnt++;
            }
            c.close();
            if (checked == 0) return;   // boot pehla cycle — candles abhi bharni hain
            boolean prev = safeMode;
            safeMode = latchSafeMode(prev, checked, freshCnt);
            if (safeMode && !prev) {
                safeModeSince = now;
                db.log("WARN", "FEED", "SAFE_MODE_ON", "feed outage — " + freshCnt + "/" + checked + " symbols fresh (<=20%) — SAFE MODE: naye entries band, open trades ka SL/TP freeze. Feed recover hote hi auto-clear.");
                try { Notifier.post(appContext(), "SAFE MODE", "Feed outage — candles stale. Naye entries band, khuli trades protected."); } catch (Throwable ignored) { }
            } else if (!safeMode && prev) {
                db.log("INFO", "FEED", "SAFE_MODE_OFF", "feed recovered — " + freshCnt + "/" + checked + " symbols fresh — normal trading resumed (" + Math.max(1, (now - safeModeSince) / 60000) + " min outage)");
            }
        } catch (Throwable t) {
            db.log("WARN", "FEED", "FEED_HEALTH_FAIL", String.valueOf(t));
        }
    }

    public boolean isSafeMode() { return safeMode; }

    /** v4.1 — CRYPTO market 24/7 chalta hai (Binance band nahi hota) — hamesha false.
     *  Method naam compatibility ke liye rakha hai (status + SAFE MODE call karte hain). */
    private boolean marketClosedET() {
        return false;   // crypto 24/7
    }

    public boolean isMarketClosed() { return marketClosedET(); }

    /** EVENT GATE: aakhri 60 min mein HIGH-impact news = naye entries pause (opt-in). */
    private boolean eventGateActive() {
        if (!eventGateOn()) return false;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM news WHERE impact='HIGH' AND ts > ?",
                new String[]{String.valueOf(System.currentTimeMillis() - 60L * 60 * 1000)});
        boolean hot = c.moveToFirst() && c.getInt(0) > 0;
        c.close();
        return hot;
    }

    /** CME maintenance halt 17:00-18:00 ET (New York time) — opt-in session filter. */
    private boolean inCmeHalt() {
        if (!sessionFilterOn()) return false;
        try {
            java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("America/New_York"));
            int h = cal.get(java.util.Calendar.HOUR_OF_DAY);
            int m = cal.get(java.util.Calendar.MINUTE);
            return (h == 17 && m >= 0) && (h < 18 || (h == 17 && m < 60)); // 17:00-17:59 ET
        } catch (Throwable t) { return false; }
    }

    /** 24h news sentiment bias: BULL count - BEAR count (clamp ±10) — council input. */
    private int newsBias() {
        try {
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT sentiment, COUNT(*) FROM news WHERE ts > ? GROUP BY sentiment",
                    new String[]{String.valueOf(System.currentTimeMillis() - 24L * 3600_000)});
            int bull = 0, bear = 0;
            while (c.moveToNext()) {
                String s = c.getString(0) == null ? "" : c.getString(0);
                if (s.contains("BULL")) bull += c.getInt(1);
                else if (s.contains("BEAR")) bear += c.getInt(1);
            }
            c.close();
            int b = bull - bear;
            return Math.max(-10, Math.min(10, b));
        } catch (Throwable t) { return 0; }
    }

    /** SIGNAL COUNCIL (TradingAgents-pattern, 4 analysts, 0-100 confidence):
     *  Technical (trend+momentum) + Volatility regime + News bias + Seasonality.
     *  3C rules NAHI badalta — sirf entry par confidence tag + opt-in min-gate. */
    public int councilScore(String sym, String side, List<Candle> k, int i) {
        int score = 50;
        boolean buy = "BUY".equals(side);
        try {
            // 1) TECHNICAL — trend alignment + RSI regime
            double e = ema(k, 200);
            double c3 = k.get(i).c;
            boolean trendAligned = !Double.isNaN(e) && (buy ? c3 > e : c3 < e);
            if (trendAligned) score += 15; else score -= 15;
            double r = rsi(k, 14);
            if (!Double.isNaN(r)) {
                if (r >= 45 && r <= 65) score += 10;          // room to move
                if (buy && r > 78) score -= 12;                // overextended
                if (!buy && r < 22) score -= 12;
            }
            // 2) VOLATILITY REGIME — healthy ATR vs dead chop
            //    v4.4.1: proAtrFloor() getter REMOVED with the quality-gate pack —
            //    council scoring purane default (0.08%) par fixed, ab setting nahi.
            double a = atr(k, 14);
            if (!Double.isNaN(a) && a > 0) {
                double atrPct = a / c3 * 100.0;
                if (atrPct >= 0.16) score += 10;
                else if (atrPct < 0.08) score -= 20;
            }
            // 3) NEWS BIAS — 24h RSS sentiment (aligned bonus, opposite penalty)
            int nb = newsBias();
            score += buy ? nb : -nb;
            // 4) SEASONALITY — current month ka historical bias (commodities ka asal edge)
            JSONObject se = seasonality(sym, false);
            if (se != null) {
                org.json.JSONArray avg = se.optJSONArray("avg");
                if (avg != null) {
                    java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
                    int mon = cal.get(java.util.Calendar.MONTH);
                    double mAvg = avg.optDouble(mon, 0);
                    if (buy ? mAvg > 0 : mAvg < 0) score += 10; else if (mAvg != 0) score -= 8;
                }
            }
        } catch (Throwable t) { /* council kabhi entry nahi todta — fallback 50 */ }
        return Math.max(0, Math.min(100, score));
    }

    /** SEASONALITY (seasonality.ai pattern): ~5y daily data → avg % by month + hit rate.
     *  Cache 24h. force=true API refresh ke liye. v4.1: Binance daily klines
     *  (2× pagination — limit 1000/call → ~5.4 years). Crypto 24/7 hai — months clean. */
    public JSONObject seasonality(String sym, boolean force) {
        JSONObject cached = seasonCache.get(sym);
        long now = System.currentTimeMillis();
        if (!force && cached != null && now - cached.optLong("fetched", 0) < 24L * 3600_000) return cached;
        if (!binanceTradable(sym)) return cached;
        try {
            List<Candle> daily = new ArrayList<>();
            long end = now, start = now - 5L * 365 * 24 * 3600_000L;
            for (long from = start; from < end; ) {
                long to = Math.min(from + 999L * 24 * 3600_000L, end);
                String body = httpGetUrl(BINANCE_HOST + "/api/v3/klines?symbol=" + sym
                        + "&interval=1d&startTime=" + from + "&endTime=" + to + "&limit=1000", 15000);
                if (body == null) break;
                org.json.JSONArray arr = new org.json.JSONArray(body);
                int before = daily.size();
                for (int i = 0; i < arr.length(); i++) {
                    org.json.JSONArray k = arr.getJSONArray(i);
                    Candle cd = new Candle();
                    cd.ts = k.getLong(0); cd.o = k.getDouble(1); cd.h = k.getDouble(2);
                    cd.l = k.getDouble(3); cd.c = k.getDouble(4); cd.v = k.getDouble(5);
                    daily.add(cd);
                }
                if (arr.length() == 0 || daily.size() == before) break;
                from = arr.getJSONArray(arr.length() - 1).getLong(0) + 24L * 3600_000L;
            }
            if (daily.size() < 100) return cached;
            java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
            double[] sum = new double[12]; int[] n = new int[12]; int[] up = new int[12];
            double prev = 0; long prevMon = -1, prevYear = -1;
            for (Candle cd : daily) {
                double c = cd.c;
                if (c <= 0) continue;
                cal.setTimeInMillis(cd.ts);
                long mon = cal.get(java.util.Calendar.MONTH), yr = cal.get(java.util.Calendar.YEAR);
                if (prev > 0 && (mon != prevMon || yr != prevYear)) {   // month-close-to-month-close % change
                    double chg = (c - prev) / prev * 100.0;
                    sum[(int) prevMon] += chg; n[(int) prevMon]++;
                    if (chg > 0) up[(int) prevMon]++;
                }
                prev = c; prevMon = mon; prevYear = yr;
            }
            org.json.JSONArray avg = new org.json.JSONArray(), hit = new org.json.JSONArray();
            for (int m = 0; m < 12; m++) {
                avg.put(n[m] > 0 ? Math.round(sum[m] / n[m] * 100.0) / 100.0 : 0);
                hit.put(n[m] > 0 ? Math.round(up[m] * 100.0 / n[m]) : 0);
            }
            int yrs = Math.max(1, (int) Math.round(daily.size() / 365.0));
            JSONObject out = new JSONObject().put("symbol", sym).put("avg", avg).put("hit", hit)
                    .put("n", new org.json.JSONArray(n)).put("years", yrs).put("fetched", now);
            seasonCache.put(sym, out);
            return out;
        } catch (Throwable t) { return cached; }
    }

    // ===== ML-LITE (FreqAI-inspired) — logistic regression on closed-trade features =====
    // Har closed trade se features (body%, vol ratio, atr%, ema dist, hour, council)
    // + outcome (win) → SGD logistic. Har 20 closed trades par retrain. Drift check.

    private synchronized JSONObject mlWeights() {
        if (mlLoaded) return mlWeights;
        try {
            String raw = db.setting("ml_weights", "");
            if (raw != null && !raw.isEmpty()) mlWeights = new JSONObject(raw);
        } catch (Throwable ignored) { }
        mlLoaded = true;
        return mlWeights;
    }

    /** Nayi entry par win probability (0-1). Model na ho to 0 (unknown). */
    public double mlWinProb(JSONObject features) {
        JSONObject w = mlWeights();
        if (w == null || features == null) return 0;
        try {
            JSONObject wm = w.getJSONObject("w");
            double z = w.optDouble("b", 0);
            java.util.Iterator<String> it = wm.keys();
            while (it.hasNext()) {
                String key = it.next();
                z += wm.optDouble(key, 0) * features.optDouble(key, 0);
            }
            return 1.0 / (1.0 + Math.exp(-z));
        } catch (Throwable t) { return 0; }
    }

    /** Har 20 closed trades par rolling retrain (pure Java SGD — koi external ML lib nahi). */
    public void mlTrain() {
        try {
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT features, pnl, risk_amt FROM trades WHERE status='CLOSED' AND features!='{}' AND features IS NOT NULL "
                            + "ORDER BY closed_at DESC LIMIT 300", null);
            List<double[]> X = new ArrayList<>();
            List<Double> Y = new ArrayList<>();
            List<String> keys = java.util.Arrays.asList("bd", "vr", "ap", "ed", "rd", "hr", "cs");
            while (c.moveToNext() && X.size() < 300) {
                try {
                    JSONObject f = new JSONObject(c.getString(0));
                    double[] x = new double[keys.size()];
                    for (int j = 0; j < keys.size(); j++) x[j] = f.optDouble(keys.get(j), 0);
                    X.add(x);
                    Y.add(c.getDouble(1) > 0 ? 1.0 : 0.0);
                } catch (Throwable ignored) { }
            }
            c.close();
            if (X.size() < 40) return;   // kam data — model abhi nahi
            double[] w = new double[keys.size()]; double b = 0;
            double lr = 0.05;
            for (int ep = 0; ep < 300; ep++) {
                for (int i = 0; i < X.size(); i++) {
                    double z = b;
                    for (int j = 0; j < w.length; j++) z += w[j] * X.get(i)[j];
                    double p = 1.0 / (1.0 + Math.exp(-z));
                    double err = p - Y.get(i);
                    for (int j = 0; j < w.length; j++) w[j] -= lr * err * X.get(i)[j];
                    b -= lr * err;
                }
            }
            // train accuracy (honesty metric)
            int correct = 0;
            for (int i = 0; i < X.size(); i++) {
                double z = b;
                for (int j = 0; j < w.length; j++) z += w[j] * X.get(i)[j];
                if ((z > 0) == (Y.get(i) > 0.5)) correct++;
            }
            JSONObject wm = new JSONObject();
            for (int j = 0; j < keys.size(); j++) wm.put(keys.get(j), Math.round(w[j] * 10000.0) / 10000.0);
            JSONObject out = new JSONObject().put("w", wm).put("b", Math.round(b * 10000.0) / 10000.0)
                    .put("n", X.size()).put("acc", Math.round(correct * 100.0 / X.size())).put("ts", System.currentTimeMillis());
            db.setSetting("ml_weights", out.toString());
            mlWeights = out;
            db.log("INFO", "ML", "ML_TRAINED", "logistic retrained on " + X.size() + " trades — train acc " + out.optInt("acc") + "% (experimental FreqAI-lite)");
        } catch (Throwable t) { db.log("ERROR", "ML", "ML_TRAIN_FAIL", String.valueOf(t)); }
    }

    /** ML DRIFT check: model prediction vs actual — bada gap = drift warning. */
    private void mlDriftCheck() {
        try {
            JSONObject w = mlWeights();
            if (w == null) return;
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT win_prob, pnl FROM trades WHERE status='CLOSED' AND win_prob>0 ORDER BY closed_at DESC LIMIT 30", null);
            double predSum = 0; int n = 0, wins = 0;
            while (c.moveToNext()) { predSum += c.getDouble(0); n++; if (c.getDouble(1) > 0) wins++; }
            c.close();
            if (n >= 20) {
                double pred = predSum / n, act = (double) wins / n;
                if (Math.abs(pred - act) > 0.25)
                    db.log("WARN", "ML", "ML_DRIFT", "model avg winProb " + String.format(Locale.US, "%.2f", pred)
                            + " vs actual winrate " + String.format(Locale.US, "%.2f", act) + " — regime drift, agla retrain important");
            }
        } catch (Throwable ignored) { }
    }

    /** DEGRADATION MONITOR (audit fix #13): har strategy tag ki rolling 20-trade PF.
     *  PF < 0.7 → owner alert (+opt-in auto-pause AI strategies). Har 30 min. */
    public void degradationCheck() {
        try {
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT strategy, COUNT(*) FROM trades WHERE status='CLOSED' GROUP BY strategy HAVING COUNT(*)>=20", null);
            List<String[]> tags = new ArrayList<>();
            while (c.moveToNext()) tags.add(new String[]{c.getString(0), c.getString(1)});
            c.close();
            for (String[] tag : tags) {
                String name = tag[0];
                if (name == null) continue;
                boolean is3C = name.startsWith("3C");
                if (name.startsWith("AI:PAPER")) continue;      // paper shadow degrade check nahi
                Cursor rc = db.getReadableDatabase().rawQuery(
                        "SELECT pnl FROM trades WHERE strategy=? AND status='CLOSED' ORDER BY closed_at DESC LIMIT 20",
                        new String[]{name});
                double gw = 0, gl = 0;
                while (rc.moveToNext()) {
                    double p = rc.getDouble(0);
                    if (p > 0) gw += p; else gl += -p;
                }
                rc.close();
                if (gl <= 0) continue;
                double pf = gw / gl;
                String dedupKey = "deg_" + name;
                long last = 0;
                try { last = Long.parseLong(db.setting(dedupKey, "0")); } catch (Exception ignored) { }
                if (pf < 0.7 && System.currentTimeMillis() - last > 12L * 3600_000) {
                    db.setSetting(dedupKey, String.valueOf(System.currentTimeMillis()));
                    db.log("WARN", "GUARD", "STRATEGY_DEGRADED",
                            name + " rolling 20-trade PF " + String.format(Locale.US, "%.2f", pf) + " (<0.7) — strategy kharab chal rahi hai, owner dekhein");
                    try {
                        db.getWritableDatabase().execSQL(
                                "INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('DEGRADED',?,?,?,0,?)",
                                new Object[]{"Strategy degraded — " + name,
                                        name + " ki aakhri 20 trades ka Profit Factor " + String.format(Locale.US, "%.2f", pf) + " hai (<0.7 threshold). Strategy Lab me review karein" + (is3C ? " — 3C MASTER hai, PRO filters/settings check karein." : " — is strategy ko trash/restore kar sakte hain."),
                                        "{}", System.currentTimeMillis()});
                    } catch (Throwable ignored) { }
                    try { Notifier.post(appContext(), "STRATEGY DEGRADED", name + " rolling PF " + String.format(Locale.US, "%.2f", pf)); } catch (Throwable ignored) { }
                    if (!is3C && autoPauseDegraded()) {
                        db.setSetting("paused_" + name, "1");
                        db.log("WARN", "GUARD", "STRATEGY_PAUSED", name + " auto-paused (auto_pause ON) — Control me re-enable karein");
                    }
                }
            }
            mlDriftCheck();
        } catch (Throwable t) { db.log("ERROR", "GUARD", "DEG_CHECK_FAIL", String.valueOf(t)); }
    }

    /** Lab/AI strategy paused hai? (degradation auto-pause). */
    private boolean strategyPaused(String tag) { return "1".equals(db.setting("paused_" + tag, "0")); }

    // ===== GUARD STATE PERSISTENCE (audit fix #7 — watchdog restart par cooldowns survive) =====

    private void saveGuardState() {
        try {
            JSONObject o = new JSONObject();
            JSONObject cu = new JSONObject();
            for (Map.Entry<String, Long> e : cooldownUntil.entrySet()) cu.put(e.getKey(), e.getValue());
            o.put("cooldown", cu).put("ts", System.currentTimeMillis());
            db.setSetting("guard_state_v1", o.toString());
        } catch (Throwable ignored) { }
    }

    private void loadGuardState() {
        try {
            String raw = db.setting("guard_state_v1", "");
            if (raw == null || raw.isEmpty()) return;
            JSONObject o = new JSONObject(raw);
            JSONObject cu = o.optJSONObject("cooldown");
            if (cu != null) {
                java.util.Iterator<String> it = cu.keys();
                long now = System.currentTimeMillis();
                while (it.hasNext()) {
                    String k = it.next();
                    long until = cu.optLong(k, 0);
                    if (until > now) cooldownUntil.put(k, until);   // expired cooldowns skip
                }
            }
            if (!cooldownUntil.isEmpty())
                db.log("INFO", "GUARD", "GUARD_RESTORED", cooldownUntil.size() + " active cooldown(s) restart ke baad restore — PRO GUARD ab persistent hai");
        } catch (Throwable ignored) { }
    }

    // ===== ORDER LIFECYCLE (v3.0) — har paper/bridge order ka audit trail =====

    private void recordOrder(long tradeId, long uid, String sym, String side, String type, double price, double qty, String source, String status) {
        try {
            db.getWritableDatabase().execSQL(
                    "INSERT INTO orders(trade_id, user_id, symbol, side, type, price, qty, status, source, ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    new Object[]{tradeId, uid, sym, side, type, price, qty, status, source, System.currentTimeMillis()});
        } catch (Throwable ignored) { }
    }

    // ===== MT5 BRIDGE LIVE MIRROR (v3.0 LIVE READY — owner opt-in, default OFF) =====

    private String httpPostUrl(String url, String json, int timeoutMs) {
        try {
            HttpURLConnection cn = (HttpURLConnection) new URL(url).openConnection();
            cn.setConnectTimeout(timeoutMs); cn.setReadTimeout(timeoutMs + 5000);
            cn.setRequestMethod("POST");
            cn.setRequestProperty("Content-Type", "application/json");
            cn.setRequestProperty("User-Agent", "Mozilla/5.0 (Android) AI-Trading-Lab/3.0");
            cn.setDoOutput(true);
            java.io.OutputStream os = cn.getOutputStream();
            os.write(json.getBytes("UTF-8"));
            os.flush(); os.close();
            int code = cn.getResponseCode();
            if (code != 200) return null;
            BufferedReader r = new BufferedReader(new InputStreamReader(cn.getInputStream()));
            StringBuilder sb = new StringBuilder(); String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            return sb.toString();
        } catch (Exception e) { return null; }
    }

    /** Bridge par REAL order bhejo (fire-and-forget thread — paper engine kabhi block nahi hota). */
    private void bridgeOrder(String sym, String side, long tradeId, long uid, double price, double qty) {
        if (!bridgeLive()) return;
        final String base = mt5Bridge();
        if (base.isEmpty()) return;
        String body = "{}";
        try {
            body = new JSONObject()
                    .put("symbol", sym).put("side", side).put("volume", bridgeLots())
                    .put("trade_id", tradeId).toString();
        } catch (Throwable ignored) { }
        final String fBody = body;
        final long tid = tradeId, u = uid; final double p = price, q = qty;
        Thread t = new Thread(() -> {
            try {
                String resp = httpPostUrl(base + (base.endsWith("/") ? "" : "/") + "order", fBody, 8000);
                boolean ok = resp != null;
                recordOrder(tid, u, sym, side, "MARKET", p, q, "BRIDGE", ok ? "SENT" : "REJECTED");
                db.log(ok ? "INFO" : "WARN", "BRIDGE", ok ? "BRIDGE_ORDER_SENT" : "BRIDGE_ORDER_FAIL",
                        sym + " " + side + " " + bridgeLots() + " lots — " + (ok ? "bridge ne accept kiya" : "bridge down/reject"));
            } catch (Throwable ignored) { }
        }, "bridge-order");
        t.setDaemon(true);
        t.start();
    }

    /** Bridge par position close (fire-and-forget). */
    private void bridgeClose(String sym, long tradeId, long uid) {
        if (!bridgeLive()) return;
        final String base = mt5Bridge();
        if (base.isEmpty()) return;
        final long tid = tradeId, u = uid;
        Thread t = new Thread(() -> {
            try {
                String resp = httpPostUrl(base + (base.endsWith("/") ? "" : "/") + "close",
                        new JSONObject().put("symbol", sym).put("trade_id", tid).toString(), 8000);
                recordOrder(tid, u, sym, "CLOSE", "MARKET", 0, 0, "BRIDGE", resp != null ? "SENT" : "REJECTED");
            } catch (Throwable ignored) { }
        }, "bridge-close");
        t.setDaemon(true);
        t.start();
    }

    /** Deep backtest candles (HONEST LAB): bridge limit=8000 ya Binance 1m paginated
     *  (3× 1000 = ~50 hours of 1m data — 3C window ke liye kaafi).
     *  DB me upsert NAHI hota (rolling window clean rehta hai) — in-memory only. */
    /** v4.4 — paginated klines (koi bhi interval) — AI training + pack depth.
     *  Binance 1000/call; pages back-to-back endTime pagination. */
    public List<Candle> deepKlines(String sym, String interval, int pages) {
        List<Candle> out = new ArrayList<>();
        long end = System.currentTimeMillis();
        for (int p = 0; p < pages; p++) {
            try {
                String body = httpGetUrl(BINANCE_HOST + "/api/v3/klines?symbol=" + sym + "&interval=" + interval
                        + "&limit=1000&endTime=" + end, 15000);
                if (body == null) break;
                List<Candle> ks = parseBinanceKlines(body);
                if (ks == null || ks.isEmpty()) break;
                out.addAll(0, ks);
                end = ks.get(0).ts - 1;
                if (ks.size() < 1000) break;
            } catch (Throwable t) { break; }
        }
        return out;
    }

    public List<Candle> deepCandles(String sym, int days) {
        String base = mt5Bridge();
        if (!base.isEmpty()) {
            try {
                String body = httpGetUrl(base + (base.endsWith("/") ? "" : "/")
                        + "candles?symbol=" + sym + "&tf=5m&limit=8000", 15000);
                if (body != null) {
                    org.json.JSONArray arr = new org.json.JSONArray(body);
                    List<Candle> out = new ArrayList<>();
                    for (int i = 0; i < arr.length(); i++) {
                        org.json.JSONArray k = arr.getJSONArray(i);
                        Candle cd = new Candle();
                        cd.ts = k.getLong(0); cd.o = k.getDouble(1); cd.h = k.getDouble(2);
                        cd.l = k.getDouble(3); cd.c = k.getDouble(4); cd.v = k.getDouble(5);
                        out.add(cd);
                    }
                    if (out.size() >= 500) return out;
                }
            } catch (Throwable ignored) { }
        }
        if (!BINANCE_PAIRS.containsKey(sym)) return loadCandles(sym);
        try {
            List<Candle> out = new ArrayList<>();
            long end = System.currentTimeMillis();
            long from = end - 3L * 1000 * 60_000;          // ~3000 minutes
            while (from < end && out.size() < 2900) {
                String body = httpGetUrl(BINANCE_HOST + "/api/v3/klines?symbol=" + sym
                        + "&interval=" + TF + "&startTime=" + from + "&endTime=" + end + "&limit=1000", 15000);
                if (body == null) break;
                org.json.JSONArray arr = new org.json.JSONArray(body);
                int before = out.size();
                for (int i = 0; i < arr.length(); i++) {
                    org.json.JSONArray k = arr.getJSONArray(i);
                    Candle cd = new Candle();
                    cd.ts = k.getLong(0); cd.o = k.getDouble(1); cd.h = k.getDouble(2);
                    cd.l = k.getDouble(3); cd.c = k.getDouble(4); cd.v = k.getDouble(5);
                    out.add(cd);
                }
                if (arr.length() == 0 || out.size() == before) break;
                from = arr.getJSONArray(arr.length() - 1).getLong(0) + TF_MS;
            }
            if (out.size() >= 500) return out;
        } catch (Throwable ignored) { }
        return loadCandles(sym);   // fallback: rolling DB window
    }

    // ================== STATUS for API ==================
    public Map<String, Object> status() {
        Map<String, Object> m = new HashMap<>();
        m.put("engine_on", "1".equals(db.setting("engine_on", "1")));
        m.put("active_symbols", activeSymbols);
        m.put("consensus", lastConsensus.isEmpty() ? "warming up" : lastConsensus);
        m.put("data_host", mt5Bridge().isEmpty() ? "BINANCE (api.binance.com)" : "MT5-BRIDGE");
        m.put("feed", "Binance spot — ALL USDT pairs (volume-ranked MAJOR/RETAIL/ALTCOIN) — 1m scan top-" + ACTIVE_TOP + " + 15m PDF pack ALL pairs");
        try {
            Cursor uc = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM instruments WHERE status='ACTIVE' AND exchange='BINANCE'", null);
            m.put("universe_total", uc.moveToFirst() ? uc.getInt(0) : 0);
            uc.close();
        } catch (Throwable ignored) { }
        m.put("timeframe", TF);
        m.put("scanner", "24/7");
        m.put("scan_count", scanCount);
        m.put("last_scan_at", lastScanAt);
        m.put("strategy_count", 1 + StrategyPack.STRATEGIES.length + 5);
        m.put("strategy_name", "3C MASTER (M5) + PDF PACK (9) + 5M PLAYBOOK (4 — Z.ai guide S1-S4) + SHAAKUNI (5)");
        m.put("pdf_pack", "RESTORED v4.4 — S1 EMA pullback · S2 BB squeeze · S3 Supertrend+ADX · S4 VWAP · S5 PDH/PDL · S6 Funding+OI · S7 Candle patterns · S8 Dow pullback · S9 Gann 50%");
        m.put("risk_pct", riskPct());
        m.put("risk_scaling", scalingInfo("3C_MASTER"));
        m.put("min_trades_scaling", MIN_TRADES_BEFORE_SCALING);
        m.put("limits", "UNLIMITED daily P/L (owner) — heat/bucket/event/session caps default OFF opt-in");
        // v4.4 status
        m.put("version", "1.1");
        boolean mktClosed = marketClosedET();
        m.put("safe_mode", safeMode && !mktClosed);   // v3.0.1 — band market par SAFE MODE jhoota lagta tha
        m.put("market_closed", mktClosed);            // v3.0.1 — weekend / CME halt indicator
        m.put("slip_bps", slipBps());
        m.put("heat_max_pct", heatMaxPct());
        m.put("bucket_max_pct", bucketMaxPct());
        m.put("council_min", councilMin());
        m.put("event_gate", eventGateOn());
        m.put("session_filter", sessionFilterOn());
        m.put("bridge_live", bridgeLive());
        JSONObject mw = mlWeights();
        m.put("ml", mw != null ? "trained n=" + mw.optInt("n") + " acc=" + mw.optInt("acc") + "% (experimental)" : "warming up (40+ feature-tagged trades chahiye)");
        m.put("degraded_check", "30-min rolling PF monitor + ML drift check");
        m.put("indicator_count", SHAAKUNI_SUITE.length);
        m.put("indicator_suite", "SHAAKUNI TRAP (liquidity/OB/MSS/killzones) + CLASSIC overlay (EMA/RSI/ATR/VWAP/ADX/Supertrend) — chart par live");
        // v4.4 — AI trainer status
        long trainedAt = 0;
        try { trainedAt = Long.parseLong(db.setting("ai_trained_at", "0").trim()); } catch (Throwable ignored) { }
        m.put("ai_trained_at", trainedAt);
        m.put("ai_age_h", trainedAt > 0 ? Math.round((System.currentTimeMillis() - trainedAt) / 3600000.0) : -1);
        try {
            JSONObject w = aiWeights();
            int aiOn = 0, aiTot = 0;
            if (w != null) {
                java.util.Iterator<String> it = w.keys();
                while (it.hasNext()) { aiTot++; if (w.getJSONObject(it.next()).optInt("on", 1) == 1) aiOn++; }
            }
            m.put("ai_strategies_on", aiOn);
            m.put("ai_strategies_total", aiTot);
        } catch (Throwable ignored) { }
        m.put("fee_edge", "ON (min TP move " + db.setting("min_fee_edge_pct", "0.14") + "% — round-trip fees se kam move = professional skip)");
        m.put("min_trades_scaling", MIN_TRADES_BEFORE_SCALING);
        m.put("fear_greed", fngValue);
        m.put("last_pattern", lastPattern);
        org.json.JSONArray armed = new org.json.JSONArray();
        for (Map.Entry<String, String> e : threecStates.entrySet()) {
            if (e.getValue() != null && e.getValue().contains("armed")) {
                try { armed.put(new org.json.JSONObject().put("symbol", e.getKey()).put("state", e.getValue())); }
                catch (Throwable ignored) { }
                if (armed.length() >= 8) break;
            }
        }
        m.put("threec_armed", armed);
        // v3.0.1 — WHY-NO-TRADE diagnostics: user ko transparent pata chale ke engine
        // kya kar raha hai (setups detect hue? filters ne roka? market band hai? feed late hai?)
        try {
            Cursor fx = db.getReadableDatabase().rawQuery(
                    "SELECT MAX(ts) FROM candles WHERE tf=?", new String[]{TF});
            if (fx.moveToFirst() && fx.getLong(0) > 0)
                m.put("feed_age_min", Math.round((System.currentTimeMillis() - fx.getLong(0)) / 60000.0 * 10.0) / 10.0);
            fx.close();
        } catch (Throwable ignored) { }
        int lowData = 0;
        for (Map.Entry<String, String> e : threecStates.entrySet())
            if (e.getValue() != null && e.getValue().contains("data kam")) lowData++;
        m.put("data_low", lowData);
        try {
            JSONObject nr = new JSONObject();
            Cursor lc = db.getReadableDatabase().rawQuery(
                    "SELECT event, COUNT(*) FROM logs WHERE ts>=? AND event IN ('SETUP_DETECTED'," +
                            "'SETUP_EXPIRED','SETUP_INVALIDATED','BREAKOUT_DETECTED','ORDER_EXECUTED','ENTRY_BLOCKED'," +
                            "'COUNCIL_BLOCKED','HEAT_CAP_BLOCKED','BUCKET_CAP_BLOCKED','SAFE_MODE_ON','FEE_EDGE_SKIP') GROUP BY event",
                    new String[]{String.valueOf(System.currentTimeMillis() - 24L * 3600_000)});
            while (lc.moveToNext()) nr.put(lc.getString(0), lc.getInt(1));
            lc.close();
            m.put("no_trade_report", nr);
        } catch (Throwable ignored) { }
        return m;
    }

    /** v5.9 — the full PDF indicator library exposed to the dashboard/API. */
    // ================== SHAAKUNI TRAP SUITE (v4.1) ==================
    // OWNER REQUEST: "sare indicators delete karo — Shaakuni Trap Trader jo indicators
    // use karta hai unko add kardo". Purana 82-indicator PDF encyclopedia POORA hata
    // diya gaya. Naya suite = Shaakuni ke APNE tools — uske open-source TradingView
    // script "Shaakuni - Liquidity Levels & Order Blocks" + masterclasses se EXACT:
    // liquidity levels (PDH/PDL/PWH/PWL), equilibrium 50% (premium/discount), order
    // blocks (ATR-impulse + structure-break), MSS, liquidity sweeps, killzones.
    public static final String[][] SHAAKUNI_SUITE = {
            // group, name, default settings
            {"Liquidity", "PDH / PDL (prev day high-low)", "stop-cluster levels"},
            {"Liquidity", "PWH / PWL (prev week high-low)", "HTF stop-cluster"},
            {"Liquidity", "Liquidity Sweep (stop hunt)", "wick beyond + close back inside"},
            {"Liquidity", "EQ Equilibrium 50%", "premium above / discount below"},
            {"Structure", "MSS (Market Structure Shift)", "close beyond N=10 swing, swing >= 3 bars old"},
            {"Structure", "BOS (Break of Structure)", "continuation break (same direction)"},
            {"POI", "Order Block (OB)", "last opposite candle before impulse >= 0.7x ATR(14); untouched only"},
            {"POI", "Mitigation Block", "OB revisit after MSS — sniper entry zone"},
            {"POI", "FVG (Fair Value Gap)", "3-candle imbalance, unfilled"},
            {"Session", "Killzones (New York time)", "Asian 20-00 / London 02-05 / NY 07-10 / LDN Close 10-12"},
            {"Session", "Sweep Status Panel", "Sweep! / Broken / Active per liquidity level"},
            {"Filter", "Premium / Discount", "buy in discount (below EQ), sell in premium (above EQ)"},
            {"Candle", "OHLC + Inside Bar OB + 3-Candle", "Shaakuni shorts setups (candlePattern)"}
    };

    /** Back-compat alias (dashboard/API indicator_count isi se aata hai). */
    public static final String[][] INDICATOR_LIBRARY = SHAAKUNI_SUITE;

    // ================== SHAAKUNI ENGINE (v4.1 — pure static, testable) ==================
    // Uske TradingView script ke EXACT rules: OB lookback 10, swing >= 3 bars old,
    // impulse body >= 0.7 x ATR(14), closest opposite candle before impulse, zone
    // untouched-only (touch = mitigated), sessions NY time, sweep statuses.

    /** Order Block zone (Shaakuni definition). */
    public static class ObZone {
        public int idx; public double top, bottom; public boolean bullish; public boolean mitigated;
        ObZone(int idx, double top, double bottom, boolean bullish, boolean mitigated) {
            this.idx = idx; this.top = top; this.bottom = bottom; this.bullish = bullish; this.mitigated = mitigated;
        }
    }

    /** Structure event: MSS (shift against prior break) ya BOS (continuation). */
    public static class StructEvent {
        public String kind = "", dir = ""; public int idx = -1; public double level;
    }

    /** Previous day high/low (UTC days) — [pdh, pdl] ya null agar data kam. */
    public static double[] prevDayHighLow(List<Candle> k) {
        java.util.LinkedHashMap<Long, double[]> days = new java.util.LinkedHashMap<>();
        for (Candle c : k) {
            long day = c.ts / 86400000L;
            double[] d = days.get(day);
            if (d == null) days.put(day, new double[]{c.h, c.l});
            else { if (c.h > d[0]) d[0] = c.h; if (c.l < d[1]) d[1] = c.l; }
        }
        if (days.size() < 2) return null;
        Long prev = null, cur = null;
        for (Long key : days.keySet()) { prev = cur; cur = key; }
        return prev == null ? null : days.get(prev);   // last FULL day (aakhri bucket aaj chal raha hai)
    }

    /** Previous week high/low (UTC weeks, week = day/7) — [pwh, pwl] ya null. */
    public static double[] prevWeekHighLow(List<Candle> k) {
        java.util.LinkedHashMap<Long, double[]> weeks = new java.util.LinkedHashMap<>();
        for (Candle c : k) {
            long wk = c.ts / 86400000L / 7L;
            double[] d = weeks.get(wk);
            if (d == null) weeks.put(wk, new double[]{c.h, c.l});
            else { if (c.h > d[0]) d[0] = c.h; if (c.l < d[1]) d[1] = c.l; }
        }
        if (weeks.size() < 2) return null;
        Long prev = null, cur = null;
        for (Long key : weeks.keySet()) { prev = cur; cur = key; }
        return prev == null ? null : weeks.get(prev);
    }

    /** Sweep status ek liquidity level ka — "SWEEP" (wick beyond + close back inside),
     *  "BROKEN" (latest close beyond), "ACTIVE" (neither). high=true level upper hai. */
    public static String sweepStatus(List<Candle> k, double level, boolean high) {
        if (level <= 0 || Double.isNaN(level) || k.isEmpty()) return "NONE";
        long lastDay = k.get(k.size() - 1).ts / 86400000L;
        boolean tradedBeyond = false;
        for (int i = k.size() - 1; i >= 0; i--) {
            Candle c = k.get(i);
            if (c.ts / 86400000L != lastDay) break;         // sirf aaj ka session
            if (high ? c.h > level : c.l < level) tradedBeyond = true;
        }
        if (!tradedBeyond) return "ACTIVE";
        double close = k.get(k.size() - 1).c;
        if (high ? close > level : close < level) return "BROKEN";
        return "SWEEP";                                     // wick beyond + close back inside = Shaakuni trap
    }

    /** ORDER BLOCKS — uske script ka exact algorithm (bull + bear, latest pehle).
     *  Bull: lookback window me highest high (swing, >= 3 bars old) → close beyond =
     *  structure break → swing ke baad impulse candle (body >= 0.7xATR14, up) →
     *  impulse se pehle closest DOWN candle (swing extreme se purani nahi) = OB box.
     *  Zone untouched rehta hai; koi baad ki candle touch kare = mitigated. */
    public static List<ObZone> orderBlocks(List<Candle> k, int lookback) {
        List<ObZone> out = new ArrayList<>();
        int n = k.size();
        if (n < lookback + 5) return out;
        double atr = atr(k, 14);
        if (Double.isNaN(atr) || atr <= 0) return out;
        double impulseMin = 0.7 * atr;
        java.util.LinkedHashSet<Integer> seen = new java.util.LinkedHashSet<>();
        for (int i = n - 1; i >= lookback && out.size() < 8; i--) {
            Candle cur = k.get(i);
            int from = Math.max(0, i - lookback);
            // ---- bullish case: highest high before i
            int hIdx = -1; double hVal = -Double.MAX_VALUE;
            int lIdx = -1; double lVal = Double.MAX_VALUE;
            for (int j = from; j < i; j++) {
                if (k.get(j).h > hVal) { hVal = k.get(j).h; hIdx = j; }
                if (k.get(j).l < lVal) { lVal = k.get(j).l; lIdx = j; }
            }
            if (hIdx < 0 || lIdx < 0) continue;
            if (i - hIdx >= 3 && cur.c > hVal) {            // bullish structure break, swing >= 3 bars old
                // impulse: swing ke baad se i tak, up-candle body >= impulseMin
                int impIdx = -1;
                for (int j = hIdx + 1; j <= i; j++) {
                    if (k.get(j).c > k.get(j).o && (k.get(j).c - k.get(j).o) >= impulseMin) { impIdx = j; break; }
                }
                if (impIdx > 0) {
                    // closest down-candle before impulse (>= hIdx)
                    for (int j = impIdx - 1; j >= hIdx; j--) {
                        if (k.get(j).c < k.get(j).o) {
                            if (seen.add(j)) {
                                double top = k.get(j).h, bot = k.get(j).l;
                                boolean mitigated = false;
                                for (int m = i + 1; m < n; m++) if (k.get(m).l <= top) { mitigated = true; break; }
                                out.add(new ObZone(j, top, bot, true, mitigated));
                            }
                            break;
                        }
                    }
                }
            }
            // ---- bearish case: lowest low before i
            if (i - lIdx >= 3 && cur.c < lVal) {            // bearish structure break
                int impIdx = -1;
                for (int j = lIdx + 1; j <= i; j++) {
                    if (k.get(j).c < k.get(j).o && (k.get(j).o - k.get(j).c) >= impulseMin) { impIdx = j; break; }
                }
                if (impIdx > 0) {
                    for (int j = impIdx - 1; j >= lIdx; j--) {
                        if (k.get(j).c > k.get(j).o) {
                            if (seen.add(j)) {
                                double top = k.get(j).h, bot = k.get(j).l;
                                boolean mitigated = false;
                                for (int m = i + 1; m < n; m++) if (k.get(m).h >= bot) { mitigated = true; break; }
                                out.add(new ObZone(j, top, bot, false, mitigated));
                            }
                            break;
                        }
                    }
                }
            }
        }
        out.sort((a, b) -> b.idx - a.idx);
        return out;
    }

    /** MSS/BOS walk — uske "Advance Structure Mapping": close beyond N=10 swing;
     *  direction PRIOR break ke against = MSS (shift), same = BOS (continuation).
     *  Pehla break hamesha MSS. Latest event return hota hai. */
    public static StructEvent structureWalk(List<Candle> k, int lookback) {
        int n = k.size();
        if (n < lookback + 5) return null;
        StructEvent last = null;
        for (int i = lookback; i < n; i++) {
            int from = Math.max(0, i - lookback);
            int hIdx = -1; double hVal = -Double.MAX_VALUE;
            int lIdx = -1; double lVal = Double.MAX_VALUE;
            for (int j = from; j < i; j++) {
                if (k.get(j).h > hVal) { hVal = k.get(j).h; hIdx = j; }
                if (k.get(j).l < lVal) { lVal = k.get(j).l; lIdx = j; }
            }
            if (hIdx < 0 || lIdx < 0) continue;
            Candle cur = k.get(i);
            if (i - hIdx >= 3 && cur.c > hVal) {
                StructEvent e = new StructEvent();
                e.dir = "BULL"; e.idx = i; e.level = hVal;
                e.kind = (last != null && "BULL".equals(last.dir)) ? "BOS" : "MSS";
                last = e;
            } else if (i - lIdx >= 3 && cur.c < lVal) {
                StructEvent e = new StructEvent();
                e.dir = "BEAR"; e.idx = i; e.level = lVal;
                e.kind = (last != null && "BEAR".equals(last.dir)) ? "BOS" : "MSS";
                last = e;
            }
        }
        return last;
    }

    /** Latest UNFILLED Fair Value Gap (3-candle imbalance). bull: low[i] > high[i-2]. */
    public static double[] latestFvg(List<Candle> k) {
        int n = k.size();
        for (int i = n - 1; i >= 2; i--) {
            Candle a = k.get(i - 2), c = k.get(i);
            if (c.l > a.h) {                                 // bull FVG (gap up)
                boolean filled = false;
                for (int m = i + 1; m < n; m++) if (k.get(m).l <= a.h) { filled = true; break; }
                if (!filled) return new double[]{a.h, c.l, 1};
            }
            if (c.h < a.l) {                                 // bear FVG (gap down)
                boolean filled = false;
                for (int m = i + 1; m < n; m++) if (k.get(m).h >= a.l) { filled = true; break; }
                if (!filled) return new double[]{a.l, c.h, -1};
            }
        }
        return null;
    }

    /** Abhi kaunsa session chal raha hai (New York time) — uske panel jaisa.
     *  Asian 20:00-00:00, London 02:00-05:00, New York 07:00-10:00, London Close 10:00-12:00. */
    public static String[] sessionNow(long tsMs) {
        java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("America/New_York"));
        cal.setTimeInMillis(tsMs);
        int m = cal.get(java.util.Calendar.HOUR_OF_DAY) * 60 + cal.get(java.util.Calendar.MINUTE);
        if (m >= 20 * 60 || m < 0) return new String[]{"ASIAN", "no"};
        if (m >= 2 * 60 && m < 5 * 60) return new String[]{"LONDON", "yes"};
        if (m >= 7 * 60 && m < 10 * 60) return new String[]{"NEW YORK", "yes"};
        if (m >= 10 * 60 && m < 12 * 60) return new String[]{"LONDON CLOSE", "no"};
        return new String[]{"OFF-SESSION", "no"};
    }

    /** Live indicator snapshot for one symbol — v4.1: SHAAKUNI SUITE (purana 82-indicator
     *  PDF snapshot hata diya gaya — owner request). */
    public Map<String, Object> indicatorSnapshot(String symbol) {
        Map<String, Object> out = new HashMap<>();
        List<Candle> k = loadCandles(symbol);
        if (k.size() < 60) {
            out.put("ok", false);
            out.put("reason", "not enough 1m candles for " + symbol + " (need 60, have " + k.size() + ")");
            return out;
        }
        Map<String, Object> v = new HashMap<>();
        Candle last = k.get(k.size() - 1);
        v.put("price", last.c);
        v.put("atr14", atr(k, 14));
        // v4.4 — CLASSIC indicator strip (chart overlay + live values) — owner: "indicators dalne hai"
        double e50 = ema(k, 50), e200 = ema(k, 200), r14 = rsi(k, 14), vw = vwap(k);
        if (!Double.isNaN(e50)) v.put("ema50", e50);
        if (!Double.isNaN(e200) && e200 > 0) {
            v.put("ema200", e200);
            v.put("ema200DistPct", (last.c - e200) / e200 * 100.0);
        }
        if (!Double.isNaN(r14)) v.put("rsi14", r14);
        if (!Double.isNaN(vw) && vw > 0) v.put("vwap", vw);
        double[] adxSnap = StrategyPack.adxAt(k, 14, k.size() - 1);
        if (adxSnap != null) v.put("adx14", adxSnap[0]);
        double[] stSnap = supertrend(k);
        if (stSnap != null) v.put("stDir", (int) stSnap[1]);
        // --- liquidity levels
        double[] d = prevDayHighLow(k);
        if (d != null) {
            v.put("pdh", d[0]); v.put("pdl", d[1]);
            v.put("eqD", (d[0] + d[1]) / 2.0);                        // daily equilibrium 50%
            v.put("pdhStatus", sweepStatus(k, d[0], true));
            v.put("pdlStatus", sweepStatus(k, d[1], false));
            v.put("premiumDiscount", last.c > (d[0] + d[1]) / 2.0 ? "PREMIUM" : "DISCOUNT");
        }
        double[] w = prevWeekHighLow(k);
        if (w != null) {
            v.put("pwh", w[0]); v.put("pwl", w[1]);
            v.put("eqW", (w[0] + w[1]) / 2.0);
            v.put("pwhStatus", sweepStatus(k, w[0], true));
            v.put("pwlStatus", sweepStatus(k, w[1], false));
        }
        // --- structure + POI
        StructEvent se = structureWalk(k, 10);
        if (se != null) { v.put("structKind", se.kind); v.put("structDir", se.dir); v.put("structLevel", se.level); }
        List<ObZone> obs = orderBlocks(k, 10);
        org.json.JSONArray arr = new org.json.JSONArray();
        for (ObZone z : obs) {
            try { arr.put(new JSONObject().put("idx", z.idx).put("top", z.top).put("bottom", z.bottom)
                    .put("bull", z.bullish).put("mitigated", z.mitigated)); } catch (Throwable ignored) { }
        }
        v.put("orderBlocks", arr);
        double[] fvg = latestFvg(k);
        if (fvg != null) { v.put("fvgTop", fvg[1]); v.put("fvgBottom", fvg[0]); v.put("fvgDir", fvg[2]); }
        v.put("candlePattern", candlePattern(k) != null ? candlePattern(k)[0] : "");
        // --- session
        String[] ses = sessionNow(last.ts);
        v.put("session", ses[0]); v.put("killzone", ses[1]);
        v.put("fearGreed", fngValue);
        out.put("ok", true);
        out.put("symbol", symbol);
        out.put("timeframe", TF);
        out.put("values", v);
        out.put("library", SHAAKUNI_SUITE);
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
