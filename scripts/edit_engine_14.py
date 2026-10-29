#!/usr/bin/env python3
"""v1.4 3C MASTER engine — surgical edits to EngineCore.java (anchored, verified)."""
import io, sys

P = "/home/z/my-project/android-app/app/src/main/java/com/aitradinglab/engine/EngineCore.java"
src = io.open(P, encoding="utf-8").read()
count = 0

def rep(anchor_start, anchor_end, new, keep_end=True, name=""):
    """Replace src[start_of_anchor_start : start_of_anchor_end] with new (anchor_end kept if keep_end)."""
    global src, count
    i = src.find(anchor_start)
    assert i >= 0, f"START anchor not found: {name or anchor_start[:60]!r}"
    assert src.find(anchor_start, i + 1) == -1, f"START anchor not unique: {name or anchor_start[:60]!r}"
    j = src.find(anchor_end, i + len(anchor_start))
    assert j >= 0, f"END anchor not found: {name or anchor_end[:60]!r}"
    src = src[:i] + new + (src[j:] if keep_end else src[j + len(anchor_end):])
    count += 1
    print(f"  ok #{count}: {name or anchor_start[:50]!r}")

# ---------------------------------------------------------------- 1. header comment
rep("/**\n * EngineCore v1.1", "public class EngineCore implements Runnable {",
"""/**
 * EngineCore v1.4 — 3C MASTER STRATEGY ENGINE (owner request: "saari strategy delete,
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
 * Data: LIVE 5m klines from the Binance public API (data-api.binance.vision) — real
 *   market data, candles are never simulated. 24/7 nonstop scanner.
 * Discovery (30 min): Binance ticker scan -> auto-register new instruments (top 150).
 * News (15 min): RSS -> sentiment -> display only.
 */
public class EngineCore implements Runnable {""", name="header")

# ---------------------------------------------------------------- 2. constants
rep("    private static final String[] DATA_HOSTS", "    public EngineCore(Db db) {",
"""    private static final String[] DATA_HOSTS = {"https://data-api.binance.vision", "https://api.binance.com"};
    private static final String TF = "5m";                 // 3C strategy timeframe (MASTER PROMPT: M5)
    private static final long TF_MS = 5L * 60 * 1000;
    /** public for StrategyLab backtester */ public static final long TF_MS_PUB = TF_MS;
    private static final int ACTIVE_TOP = 30;      // trade the top-N by volume
    private static final int LEDGER_TOP = 150;     // keep in instruments ledger
    // ==== 3C STRATEGY CONSTANTS (MASTER PROMPT — kabhi change nahi without owner approval) ====
    public static final double THREEC_BODY_MIN = 0.70;  // C1 & C2 body >= 70% of High-Low range
    public static final int THREEC_WINDOW = 5;          // breakout window: next 5 M5 candles
    public static final double THREEC_TP_R = 3.0;       // take profit at +3R, whole position
    private static final double RISK_DEFAULT_PCT = 1.0; // settings risk_pct override

    private final Db db;
    private volatile boolean running = true;
    private String dataHost = DATA_HOSTS[0];
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

    /** v1.4 — owner-controlled risk % of equity per trade (settings risk_pct, 0.1-10). */
    public double riskPct() {
        try {
            double v = Double.parseDouble(db.setting("risk_pct", String.valueOf(RISK_DEFAULT_PCT)));
            if (v < 0.1) v = 0.1;
            if (v > 10) v = 10;
            return v;
        } catch (Exception e) { return RISK_DEFAULT_PCT; }
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

    /** v1.4 — the ONE master strategy (35-strategy consensus retired by owner request). */
    public static final String[][] STRATEGY_META = {
            {"3C Breakout (M5) — MASTER", "Price action"}
    };

""", name="constants")

# ---------------------------------------------------------------- 3. ENGINE_START log
rep('        db.log("INFO", "SYSTEM", "ENGINE_START",', "\n        // v1.2 ONE-TIME MIGRATION",
"""        db.log("INFO", "SYSTEM", "ENGINE_START", "v1.4 3C MASTER engine — 5m timeframe, 24h nonstop scanner, live Binance data | 3C rules: C1+C2 body>=70%, C3 protected close, 5-candle breakout window, close-based invalidation, SL=opposite extreme, breakeven at +1R, close ALL at +3R, no partial TP | risk " + riskPct() + "% (Settings risk_pct) | UNLIMITED daily P/L — no kill switch, no position cap (owner request) | Strategy Lab + auto-evolve every 6h");

""", name="engine_start_log")

# ---------------------------------------------------------------- 4. v1.4 migration (before while loop)
rep("        while (running) {", "\n", """        // v1.4 ONE-TIME MIGRATION — 3C era. Old ATR-era open trades are cancelled because
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
        while (running) {
""", name="v14_migration")

# ---------------------------------------------------------------- 5. autoEvolve cadence in loop
rep("                Thread.sleep(2000);", "\n", """                if (now - lastEvolve >= 6L * 3600_000) {   // v1.4 — AI har 6h mein ek nayi strategy propose karta hai
                    lastEvolve = now;
                    if (lab != null) { try { lab.autoEvolve(); } catch (Throwable t) { db.log("ERROR", "LAB", "EVOLVE_FAIL", String.valueOf(t)); } }
                }
                Thread.sleep(2000);
""", name="autoEvolve_cadence")

# ---------------------------------------------------------------- 6. loop(): remove kill-switch call
rep("        rollDay();\n        checkDrawdownKill();\n", "\n", "        rollDay();\n", keep_end=False, name="loop_remove_kill")

# ---------------------------------------------------------------- 7. remove dailyHalted + checkDrawdownKill
rep("    private boolean dailyHalted(long userId) {", "    // ================== DATA ==================",
"""    // v1.4 — dailyHalted() and checkDrawdownKill() REMOVED by owner request:
    // daily loss/profit is UNLIMITED. rollDay() stays only to keep the dashboard's
    // dayPnlPct counter honest (it no longer halts anything).

""", name="remove_halt_kill")

# ---------------------------------------------------------------- 8. THE BIG BLOCK: strategies + trade logic -> 3C engine
NEW_BLOCK = r"""    // ================== 3C MASTER STRATEGY (v1.4) ==================
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
            return s;
        }
        if (!g1 && !g2 && g3 && c3.c <= Math.max(c1.h, c2.h)) {         // SELL setup
            s.side = "SELL";
            s.boundary = s.zoneHigh;
            s.trigger = s.zoneLow * (1 - entryBuf);
            s.slPrice = s.zoneHigh * (1 + slBuf);
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

    /**
     * Chronological rebuild of the 3C state machine over closed candles. Deterministic
     * and restart-proof: har loop state real candles se dobara derive hota hai, fragile
     * memory nahi. Sirf LAST closed candle ka breakout trade kar sakta hai (purane
     * breakouts consumed/expired hote hain — ek hi baar MISSED log hota hai).
     */
    private Walk3C walk3C(String sym, List<Candle> k) {
        double entryBuf = bufSetting("threec_entry_buf_pct");
        double slBuf = bufSetting("threec_sl_buf_pct");
        Walk3C w = new Walk3C();
        Setup3C pending = null;
        int last = k.size() - 1;
        for (int i = 2; i <= last; i++) {
            Candle c = k.get(i);
            if (pending != null) {
                int winIdx = (int) ((c.ts - pending.c3Ts) / TF_MS);   // 1..5 inside the window
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
                if (s != null) {
                    pending = s;
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
            if (w.fire != null) {
                lastVotes = new int[]{"BUY".equals(w.fire.side) ? 1 : -1};
                lastVoteSym = sym;
                for (long uid : users) openTrade3C(uid, sym, w.fire, w.fill);
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

    /** 3C entry — one trade per setup per account, one open position per symbol. */
    private void openTrade3C(long uid, String sym, Setup3C s, double fill) {
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
        double riskDist = "BUY".equals(s.side) ? fill - s.slPrice : s.slPrice - fill;
        if (riskDist <= 0) return;
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * riskPct() / 100.0;
        double qty = risk / riskDist;
        if (qty * fill > bal * 0.95) qty = bal * 0.95 / fill;
        if (qty <= 0) return;
        double tp = "BUY".equals(s.side) ? fill + THREEC_TP_R * riskDist : fill - THREEC_TP_R * riskDist;
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?)",
                new Object[]{uid, sym, s.side, qty, fill, s.slPrice, tp, "3C_MASTER", 0, System.currentTimeMillis(), riskPct() / 100.0});
        db.log("INFO", "3C", "ORDER_EXECUTED",
                sym + " " + s.side + " qty=" + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(fill)
                        + " SL=" + fpx(s.slPrice) + " TP=" + fpx(tp) + " (3R) risk=$"
                        + String.format(Locale.US, "%.2f", risk) + " (" + riskPct() + "% of $" + String.format(Locale.US, "%.2f", bal) + ")");
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
                "SELECT name, spec, status FROM strategies WHERE status IN ('PAPER','ACTIVE')", null);
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

    /** Lab strategy entry — ATR SL/TP model (1.5x / 2.5x), 1% risk, same guards as 3C. */
    private void openTradeLab(long uid, String sym, String side, List<Candle> k, String tier) {
        Cursor ex = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND symbol=? AND status='OPEN'",
                new String[]{String.valueOf(uid), sym});
        boolean have = ex.moveToFirst() && ex.getInt(0) > 0;
        ex.close();
        if (have) return;
        double price = k.get(k.size() - 1).c;
        double a = atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return;
        double sl = "BUY".equals(side) ? price - 1.5 * a : price + 1.5 * a;
        double tp = "BUY".equals(side) ? price + 2.5 * a : price - 2.5 * a;
        double bal = balanceOf(uid);
        if (bal <= 0) return;
        double risk = bal * 0.01;
        double qty = risk / (1.5 * a);
        if (qty * price > bal * 0.95) qty = bal * 0.95 / price;
        if (qty <= 0) return;
        db.getWritableDatabase().execSQL(
                "INSERT INTO trades(user_id, symbol, side, qty, entry, sl, tp, status, strategy, consensus, opened_at, risk) VALUES(?,?,?,?,?,?,?,'OPEN',?,?,?,?)",
                new Object[]{uid, sym, side, qty, price, sl, tp, tier, 0.65, System.currentTimeMillis(), 0.01});
        db.log("INFO", "LAB", "ORDER_EXECUTED", sym + " " + side + " [" + tier + "] qty="
                + String.format(Locale.US, "%.6f", qty) + " entry=" + fpx(price)
                + " (Lab strategy signal — ATR SL/TP, 1% risk)");
    }

"""
rep("    // ================== STRATEGIES (10) ==================", "    private void manageOpenTrades() {", NEW_BLOCK, name="big_block_3c")

# ---------------------------------------------------------------- 9. manageOpenTrades upgrade
rep("    private void manageOpenTrades() {", "    private void closeTrade(",
"""    private void manageOpenTrades() {
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
            // last CLOSED candle high/low — stop-order semantics, close-only se zyada accurate
            Cursor cc = db.getReadableDatabase().rawQuery(
                    "SELECT h, l FROM candles WHERE symbol=? AND tf=? AND ts<=? ORDER BY ts DESC LIMIT 1",
                    new String[]{sym, TF, System.currentTimeMillis() - TF_MS});
            double hi = Double.NaN, lo = Double.NaN;
            if (cc.moveToFirst()) { hi = cc.getDouble(0); lo = cc.getDouble(1); }
            cc.close();
            if (Double.isNaN(hi)) continue;
            boolean buy = "BUY".equals(side);
            // conservative same-candle order: SL pehle, TP baad mein (kabhi optimistic nahi)
            boolean hitSl = buy ? lo <= sl : hi >= sl;
            boolean hitTp = buy ? hi >= tp : lo <= tp;
            if (hitSl || hitTp) {
                closeTrade(id, uid, hitSl ? sl : tp, hitSl ? "SL" : "TP", qty, entry, side);
                continue;
            }
            // 3C management: +1R par WHOLE position ka SL breakeven par; +3R TP already set.
            boolean is3C = strategy != null && strategy.startsWith("3C");
            if (is3C) {
                double rDist = Math.abs(tp - entry) / THREEC_TP_R;      // 1R (TP 3R door fix hai)
                boolean beMoved = buy ? sl >= entry : sl <= entry;      // SL pehle se entry par?
                boolean beHit = buy ? hi >= entry + rDist : lo <= entry - rDist;
                if (!beMoved && beHit && rDist > 0) {
                    db.getWritableDatabase().execSQL("UPDATE trades SET sl=? WHERE id=?", new Object[]{entry, id});
                    db.log("INFO", "3C", "TRADE_MANAGED",
                            "trade #" + id + " " + sym + " — +1R hit — SL moved to breakeven " + fpx(entry) + " (whole position, no partial TP)");
                }
            }
        }
    }

""", name="manageOpenTrades")

# ---------------------------------------------------------------- 10. closeTrade event names
rep('        db.log(reason.equals("SL") ? "WARN" : "INFO", "EXECUTOR", "PAPER_CLOSE_" + reason,',
    "\n", """        db.log(reason.equals("SL") ? "WARN" : "INFO", "EXECUTOR", "TRADE_CLOSED_" + reason,
""", name="closeTrade_event")

# ---------------------------------------------------------------- 11. status()
rep("    // ================== STATUS for API ==================", "    /** v5.9 — the full PDF indicator library",
"""    // ================== STATUS for API ==================
    public Map<String, Object> status() {
        Map<String, Object> m = new HashMap<>();
        m.put("engine_on", "1".equals(db.setting("engine_on", "1")));
        m.put("active_symbols", activeSymbols);
        m.put("consensus", lastConsensus.isEmpty() ? "warming up" : lastConsensus);
        m.put("data_host", dataHost);
        m.put("timeframe", TF);
        m.put("scanner", "24h");
        m.put("scan_count", scanCount);
        m.put("last_scan_at", lastScanAt);
        m.put("strategy_count", 1);
        m.put("strategy_name", "3C Breakout (M5) — MASTER");
        m.put("risk_pct", riskPct());
        m.put("limits", "UNLIMITED — daily loss/profit cap nahi, kill switch nahi, position cap nahi (owner request)");
        m.put("indicator_count", INDICATOR_LIBRARY.length);
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
        return m;
    }

""", name="status")

# ---------------------------------------------------------------- 12. fetchNews: display-only
rep('                if ("HIGH".equals(impact)) {', "            }\n        }\n    }\n\n    private List<String[]> parseRss(",
"""                // v1.4 — high-impact news sirf DISPLAY hoti hai. 3C entry kabhi news se
                // block nahi hoti (owner: unlimited trading, sirf strategy rules chalenge).
                if ("HIGH".equals(impact)) {
                    db.log("INFO", "NEWS", "HIGH_IMPACT", "display-only — entries NOT paused (" + title.substring(0, Math.min(60, title.length())) + ")");
                }
            }
        }
    }

    private List<String[]> parseRss(""", name="fetchNews_display_only")

# ---------------------------------------------------------------- 13. indicatorSnapshot text
rep('"not enough 1m candles for "', "\n", '"not enough 5m candles for "', keep_end=False, name="indicator_text")

io.open(P, "w", encoding="utf-8").write(src)
print(f"\nDONE — {count} edits applied to EngineCore.java")
