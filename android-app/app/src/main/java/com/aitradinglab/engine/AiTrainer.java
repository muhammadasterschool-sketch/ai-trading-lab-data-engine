package com.aitradinglab.engine;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * v4.4.0 AI TRAINER — owner request: "ye abhi bhi loss kar raha hai — isko
 * professional aur profitable train karo".
 *
 * Kya karta hai:
 *  1. REAL Binance history par walk-forward backtest (5m execution depth + 1d HTF
 *     regime; BTC/ETH 2017 se daily data — Binance ka aakhri data yahi hai).
 *  2. Har strategy (PDF pack S1-S9 + Shaakuni playbooks SHK1-SHK5) ke trades
 *     collect → WR / PF / expectancy, fees+slippage INCLUDED.
 *  3. IS(70)/OOS(30) split — sirf OOS performance se weight: PF<0.9 → strategy
 *     AUTO-PAUSE (loss-maker), PF>1.3 → boost. Risk phir bhi 1% flat (owner rule) —
 *     weights sirf on/off + priority, risk nahi badalte.
 *  4. Self-learning: har 25 closed trades par live results weights me blend
 *     (engine selfLearn() call karta hai) — live PF<0.7 → auto-pause.
 *
 * Pure core (simulate/stats/weights) host-JVM testable — network glue engine me.
 */
public class AiTrainer {

    // ================== RESULT TYPES ==================
    public static class Res {
        public String key;
        public int n = 0, nOos = 0;
        public double wr = 0, pf = 0, expR = 0;        // full-sample
        public double oosWr = 0, oosPf = 0;            // out-of-sample (decision basis)
        public double weight = 1.0; public int enabled = 1;
        public String from = "";
    }

    /** Ek simulated/backtested trade. */
    public static class T {
        public long ts;        // entry time (ms)
        public double r;       // R-multiple net of fees
    }

    /** Signal source: index → signals (kya bhi strategy ho). */
    public interface SigFn { List<StrategyPack.Signal> at(List<EngineCore.Candle> k, int i); }

    // ================== PURE SIMULATION CORE ==================
    /** Ek strategy ko closed bars par walk-forward chalao. Entry = NEXT bar open
     *  (realistic), TP = +2R, BE at +1R, time stop 96 bars, fees+slip INCLUDED.
     *  Ek waqt me ek position per strategy (safety). */
    public static List<T> simulate(List<EngineCore.Candle> k, SigFn fn, double feePctSide, double slipBps) {
        List<T> out = new ArrayList<>();
        if (k == null || k.size() < 60) return out;
        int pos = -1;                       // entry index, -1 = flat
        double entry = 0, sl = 0, tp = 0, risk = 0;
        boolean buy = false, beDone = false;
        double slip = slipBps / 10000.0;
        for (int i = 0; i < k.size() - 1; i++) {
            if (pos >= 0) {
                EngineCore.Candle c = k.get(i);
                // 1) BE move (high/low +1R touch — conservative: close-based nahi)
                if (!beDone) {
                    if (buy && c.h >= entry + risk) { sl = Math.max(sl, entry); beDone = true; }
                    if (!buy && c.l <= entry - risk) { sl = Math.min(sl, entry); beDone = true; }
                }
                // 2) SL/TP (same bar dono touch → SL pehle = conservative)
                boolean slHit = buy ? c.l <= sl : c.h >= sl;
                boolean tpHit = buy ? c.h >= tp : c.l <= tp;
                if (slHit || tpHit || i - pos >= 96) {
                    double exit = slHit ? sl : (tpHit ? tp : c.c);
                    double feePx = (entry + exit) * (feePctSide + slip);
                    double pnl = buy ? (exit - entry - feePx) : (entry - exit - feePx);
                    T t = new T();
                    t.ts = k.get(pos).ts;
                    t.r = risk > 0 ? pnl / risk : 0;
                    if (t.r > 2.05) t.r = 2.05;               // TP cap
                    if (t.r < -1.3) t.r = -1.3;               // gap guard
                    out.add(t);
                    pos = -1;
                }
                continue;
            }
            List<StrategyPack.Signal> sigs = fn.at(k, i);
            if (sigs == null || sigs.isEmpty()) continue;
            StrategyPack.Signal s = sigs.get(0);
            EngineCore.Candle next = k.get(i + 1);
            double e = next.o;
            e = "BUY".equals(s.side) ? e * (1 + slip) : e * (1 - slip);   // slippage
            double rd = Math.abs(s.refPrice - s.slPrice);
            if (rd <= 0 || e <= 0) continue;
            pos = i + 1; entry = e; sl = s.slPrice; buy = "BUY".equals(s.side);
            risk = rd;
            tp = buy ? entry + 2 * rd : entry - 2 * rd;
            beDone = false;
            // entry bar me hi SL/TP check (gap guard)
            EngineCore.Candle ec = k.get(pos);
            boolean slHit = buy ? ec.l <= sl : ec.h >= sl;
            boolean tpHit = buy ? ec.h >= tp : ec.l <= tp;
            if (slHit || tpHit) {
                double exit = slHit ? sl : tp;
                double feePx = (entry + exit) * (feePctSide + slip);
                double pnl = buy ? (exit - entry - feePx) : (entry - exit - feePx);
                T t = new T(); t.ts = k.get(pos).ts; t.r = risk > 0 ? pnl / risk : 0;
                if (t.r > 2.05) t.r = 2.05; if (t.r < -1.3) t.r = -1.3;
                out.add(t);
                pos = -1;
            }
        }
        return out;
    }

    /** [n, winRate 0-1, profitFactor, avgR] — losses ka sum 0 ho to PF = wins>0 ? 99 : 0. */
    public static double[] stats(List<T> trades) {
        double w = 0, l = 0, gw = 0, gl = 0, sumR = 0;
        for (T t : trades) {
            sumR += t.r;
            if (t.r > 0) { w++; gw += t.r; } else if (t.r < 0) { l++; gl += -t.r; }
        }
        int n = trades.size();
        return new double[]{
                n,
                n > 0 ? w / n : 0,
                gl > 0 ? gw / gl : (gw > 0 ? 99 : 0),
                n > 0 ? sumR / n : 0
        };
    }

    /** OOS (entryTs >= splitTs) subset stats. */
    public static double[] oosStats(List<T> trades, long splitTs) {
        List<T> oos = new ArrayList<>();
        for (T t : trades) if (t.ts >= splitTs) oos.add(t);
        return stats(oos);
    }

    /** OOS PF → weight (risk 1% flat rehta hai — weight sirf gate/priority). */
    public static double weightFrom(double oosPf) {
        if (oosPf >= 1.5) return 1.3;
        if (oosPf >= 1.3) return 1.15;
        if (oosPf >= 1.1) return 1.0;
        if (oosPf >= 0.9) return 0.8;
        return 0.6;
    }

    /** OOS PF → enabled (PF<0.9 auto-pause; n==0 neutral-on). */
    public static int enabledFrom(int oosN, double oosPf) {
        if (oosN == 0) return 1;
        return oosPf < 0.9 ? 0 : 1;
    }

    /** Res → JSON row (JSONException internally wrapped — host android.jar parity). */
    public static JSONObject resJson(Res r) {
        try {
            return new JSONObject()
                    .put("n", r.n).put("wr", round(r.wr * 100, 1)).put("pf", round(r.pf, 2))
                    .put("oos_n", r.nOos).put("oos_wr", round(r.oosWr * 100, 1)).put("oos_pf", round(r.oosPf, 2))
                    .put("exp_r", round(r.expR, 3)).put("w", r.weight).put("on", r.enabled);
        } catch (org.json.JSONException e) {
            return new JSONObject();
        }
    }

    private static double round(double v, int d) {
        double m = Math.pow(10, d);
        return Math.round(v * m) / m;
    }

    // ================== SHAAKUNI PLAYBOOK SIGNAL FUNCTIONS (training ke liye) ==================
    /** SHK1 SSM Sniper Bull: PDL sweep + MSS bull. SHK2: PDH sweep + MSS bear.
     *  SHK3 Killzone Sweep: killzone + koi bhi sweep (polarity se side).
     *  SHK4 OB Retest: MSS + untouched OB me price. SHK5 PD Filter: discount + EMA200 up. */
    public static List<StrategyPack.Signal> shaakuniSignals(List<EngineCore.Candle> k, int i, String which) {
        List<StrategyPack.Signal> out = new ArrayList<>();
        EngineCore.Candle c = k.get(i);
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return out;
        double px = c.c;
        double[] d = EngineCore.prevDayHighLow(k.subList(0, i + 1));
        EngineCore.StructEvent se = EngineCore.structureWalk(k.subList(0, i + 1), 10);
        StrategyPack.Signal s = null;
        if ("SHK1_SSM_BULL".equals(which)) {
            if (d != null && se != null && "BULL".equals(se.dir) && "MSS".equals(se.kind)
                    && "SWEEP".equals(EngineCore.sweepStatus(k.subList(0, i + 1), d[1], false))) {
                s = mk("SHK1_SSM_BULL", "BUY", c, a);
            }
        } else if ("SHK2_SSM_BEAR".equals(which)) {
            if (d != null && se != null && "BEAR".equals(se.dir) && "MSS".equals(se.kind)
                    && "SWEEP".equals(EngineCore.sweepStatus(k.subList(0, i + 1), d[0], true))) {
                s = mk("SHK2_SSM_BEAR", "SELL", c, a);
            }
        } else if ("SHK3_KZ_SWEEP".equals(which)) {
            String[] ses = EngineCore.sessionNow(c.ts);
            if ("yes".equals(ses[1]) && d != null) {
                boolean pdhSweep = "SWEEP".equals(EngineCore.sweepStatus(k.subList(0, i + 1), d[0], true));
                boolean pdlSweep = "SWEEP".equals(EngineCore.sweepStatus(k.subList(0, i + 1), d[1], false));
                if (pdlSweep) s = mk("SHK3_KZ_SWEEP", "BUY", c, a);
                else if (pdhSweep) s = mk("SHK3_KZ_SWEEP", "SELL", c, a);
            }
        } else if ("SHK4_OB_RETEST".equals(which)) {
            if (se != null) {
                List<EngineCore.ObZone> obs = EngineCore.orderBlocks(k.subList(0, i + 1), 10);
                for (EngineCore.ObZone z : obs) {
                    if (z.mitigated) continue;
                    if (px >= z.bottom && px <= z.top) {
                        s = mk("SHK4_OB_RETEST", z.bullish ? "BUY" : "SELL", c, a);
                        break;
                    }
                }
            }
        } else if ("SHK5_PD_EMA200".equals(which)) {
            if (d != null) {
                double eq = (d[0] + d[1]) / 2.0;
                double e200 = emaClose(k, i, 200);
                if (!Double.isNaN(e200)) {
                    if (px < eq && px > e200) s = mk("SHK5_PD_EMA200", "BUY", c, a);
                    else if (px > eq && px < e200) s = mk("SHK5_PD_EMA200", "SELL", c, a);
                }
            }
        }
        if (s != null) out.add(s);
        return out;
    }

    private static StrategyPack.Signal mk(String key, String side, EngineCore.Candle c, double a) {
        StrategyPack.Signal s = new StrategyPack.Signal();
        s.strategy = key; s.side = side;
        s.sigTs = c.ts; s.sigIdx = -1; s.refPrice = c.c; s.windowBars = 8;
        if ("BUY".equals(side)) {
            s.slPrice = c.l - 1.5 * a; s.boundary = c.l - 2.5 * a;
        } else {
            s.slPrice = c.h + 1.5 * a; s.boundary = c.h + 2.5 * a;
        }
        s.note = "Shaakuni playbook " + key;
        return s;
    }

    private static double emaClose(List<EngineCore.Candle> k, int at, int n) {
        if (at < n - 1) return Double.NaN;
        double mult = 2.0 / (n + 1), e = 0; boolean init = false;
        for (int i = 0; i <= at; i++) {
            double c = k.get(i).c;
            e = init ? (c - e) * mult + e : c; init = true;
        }
        return e;
    }

    // ================== PREV-DAY MAP (S5 ke liye, O(n)) ==================
    /** Har index ke liye PREVIOUS closed UTC day ka [pdh, pdl] — ek pass me. */
    public static double[][] prevDayMap(List<EngineCore.Candle> k) {
        TreeMap<Long, double[]> days = new TreeMap<>();
        double[][] out = new double[k.size()][];
        long curDay = -1; double hi = 0, lo = 0;
        for (int i = 0; i < k.size(); i++) {
            EngineCore.Candle c = k.get(i);
            long day = c.ts / 86400000L;
            if (day != curDay) {
                if (curDay > 0) days.put(curDay, new double[]{hi, lo});
                curDay = day; hi = c.h; lo = c.l;
            } else {
                if (c.h > hi) hi = c.h;
                if (c.l < lo) lo = c.l;
            }
            Map.Entry<Long, double[]> prev = days.lastEntry();
            out[i] = prev == null ? null : prev.getValue();
        }
        return out;
    }
}
