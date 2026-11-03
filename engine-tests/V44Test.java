package com.aitradinglab.engine;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * v4.4.0 ENGINE TEST — host-JVM (android.jar stubs + org-json.jar).
 * PDF STRATEGY PACK (S1-S9) + AI TRAINER + ALL-BINANCE UNIVERSE verification.
 *
 * RUN: run-tests.sh (javac + java, stub android.jar)
 */
public class V44Test {

    static int pass = 0, fail = 0;

    static void check(String name, boolean ok, String detail) {
        if (ok) { pass++; System.out.println("PASS  " + name + (detail.isEmpty() ? "" : "  — " + detail)); }
        else { fail++; System.out.println("FAIL  " + name + "  — " + detail); }
    }

    static EngineCore.Candle mk(long ts, double o, double h, double l, double c) {
        EngineCore.Candle cd = new EngineCore.Candle();
        cd.ts = ts; cd.o = o; cd.h = h; cd.l = l; cd.c = c; cd.v = 1000;
        return cd;
    }

    static final long MIN = 60_000L;

    /** Seeded random walk — deterministic. */
    static List<EngineCore.Candle> randomWalk(int n, long t0, long seed, double start, double drift) {
        Random r = new Random(seed);
        List<EngineCore.Candle> out = new ArrayList<>();
        double p = start;
        for (int i = 0; i < n; i++) {
            double o = p;
            double move = (r.nextDouble() - 0.5 + drift) * start * 0.004;
            double c = o + move;
            double h = Math.max(o, c) * (1 + r.nextDouble() * 0.001);
            double l = Math.min(o, c) * (1 - r.nextDouble() * 0.001);
            out.add(mk(t0 + i * MIN, o, h, l, c));
            p = c;
        }
        return out;
    }

    public static void main(String[] args) {

        // ================= 1) Pack metadata =================
        check("pack.meta.count", StrategyPack.STRATEGIES.length == 13 && StrategyPack.KEYS.length == 13,
                "strategies=" + StrategyPack.STRATEGIES.length + " (9 PDF pack + 4 playbook v1.0)");
        check("pack.meta.restore", StrategyPack.STRATEGIES[0][0].equals("S1_EMA_PULLBACK")
                && StrategyPack.STRATEGIES[4][0].equals("S5_PDH_PDL") && StrategyPack.STRATEGIES[8][0].equals("S9_GANN_50"),
                "S1/S5/S9 keys present (PDF pack RESTORED)");

        // ================= 2) evaluateAll — no-crash + firing across regimes =================
        long t0 = 1760000000000L;
        int total = 0; boolean crashed = false;
        double[][] regimes = {{0.15, 1.0}, {-0.15, 1.0}, {0.0, 1.0}};   // up / down / flat drift
        for (double[] rg : regimes) {
            try {
                List<EngineCore.Candle> k = randomWalk(400, t0, (long) (rg[0] * 1000) + 42, 100, rg[0]);
                double[][] pdMap = AiTrainer.prevDayMap(k);
                for (int i = 210; i < k.size(); i++) {
                    double[] adx = StrategyPack.adxAt(k, 14, i);
                    List<StrategyPack.Signal> sigs = StrategyPack.evaluateAll(k, i, pdMap[i], null,
                            adx == null ? -1 : adx[0]);
                    for (StrategyPack.Signal s : sigs) {
                        total++;
                        if (s.strategy == null || s.side == null || s.slPrice <= 0 || s.sigTs <= 0) crashed = true;
                    }
                }
            } catch (Throwable t) { crashed = true; }
        }
        check("pack.evalAll.noCrash", !crashed, "evaluateAll 3 regimes × 190 bars");
        check("pack.evalAll.fires", total > 0, "signals=" + total + " (S6 deriv-null skip OK)");

        // ================= 3) S6 funding gate =================
        List<EngineCore.Candle> flat = randomWalk(260, t0, 7, 100, 0);
        boolean s6fired = false;
        double[] extreme = {0.001, 6.0};
        for (int i = 210; i < flat.size(); i++) {
            for (StrategyPack.Signal s : StrategyPack.evaluateAll(flat, i, null, extreme, -1))
                if ("S6_FUNDING_OI".equals(s.strategy)) s6fired = true;
        }
        check("pack.s6.gate", s6fired, "extreme funding + OI → S6 fires");

        // ================= 4) ADX math (Wilder) =================
        List<EngineCore.Candle> trend = new ArrayList<>();
        for (int i = 0; i < 120; i++) trend.add(mk(t0 + i * MIN, 100 + i * 0.5, 100.7 + i * 0.5, 99.9 + i * 0.5, 100.5 + i * 0.5));
        double[] adx = StrategyPack.adxAt(trend, 14, 119);
        check("pack.adx.trend", adx != null && adx[0] > 40 && adx[1] > adx[2],
                adx == null ? "null" : "adx=" + String.format("%.1f +DI=%.1f -DI=%.1f", adx[0], adx[1], adx[2]));
        double[] adxFlat = StrategyPack.adxAt(flat, 14, flat.size() - 1);
        check("pack.adx.chopLow", adxFlat != null && adxFlat[0] < 40, "flat ADX " + (adxFlat == null ? "?" : String.format("%.1f", adxFlat[0])));

        // ================= 5) AiTrainer.simulate — SL/TP/BE exact =================
        // (simulate min 60 bars chahta hai — 60 flat bars, signal i=58, entry bar 59)
        // Craft: signal BUY entry ~100, SL 95 → rd=5, TP=110, BE@105
        List<EngineCore.Candle> bars = new ArrayList<>();
        for (int i = 0; i < 59; i++) bars.add(mk(t0 + i * MIN, 100, 100.2, 99.8, 100));
        // i=59: entry bar (open 100), h=110.5 → TP hit same bar
        bars.add(mk(t0 + 59 * MIN, 100, 110.5, 99.9, 105));
        List<AiTrainer.T> tp = AiTrainer.simulate(bars, (k, i) -> {
            if (i != 58) return new ArrayList<>();
            StrategyPack.Signal s = new StrategyPack.Signal();
            s.strategy = "TEST"; s.side = "BUY"; s.sigTs = k.get(58).ts; s.refPrice = 100;
            s.slPrice = 95; s.boundary = 94; s.windowBars = 5; s.note = "tp test";
            List<StrategyPack.Signal> out = new ArrayList<>(); out.add(s); return out;
        }, 0.0005, 0);
        check("ai.sim.tp", tp.size() == 1 && tp.get(0).r > 1.9 && tp.get(0).r <= 2.05,
                tp.isEmpty() ? "none" : "r=" + String.format("%.3f", tp.get(0).r) + " (TP +2R, fees inside)");
        // SL hit
        List<EngineCore.Candle> bars2 = new ArrayList<>();
        for (int i = 0; i < 59; i++) bars2.add(mk(t0 + i * MIN, 100, 100.2, 99.8, 100));
        bars2.add(mk(t0 + 59 * MIN, 100, 100.4, 94.5, 96));
        List<AiTrainer.T> sl = AiTrainer.simulate(bars2, (k, i) -> {
            if (i != 58) return new ArrayList<>();
            StrategyPack.Signal s = new StrategyPack.Signal();
            s.strategy = "TEST"; s.side = "BUY"; s.sigTs = k.get(58).ts; s.refPrice = 100;
            s.slPrice = 95; s.boundary = 94; s.windowBars = 5; s.note = "sl test";
            List<StrategyPack.Signal> out = new ArrayList<>(); out.add(s); return out;
        }, 0.0005, 0);
        check("ai.sim.sl", sl.size() == 1 && sl.get(0).r < -0.97 && sl.get(0).r > -1.3,
                sl.isEmpty() ? "none" : "r=" + String.format("%.3f", sl.get(0).r) + " (-1R, fees inside)");
        // BE move (+1R touch → SL to entry → retest = ~0R)
        List<EngineCore.Candle> bars3 = new ArrayList<>();
        for (int i = 0; i < 59; i++) bars3.add(mk(t0 + i * MIN, 100, 100.2, 99.8, 100));
        bars3.add(mk(t0 + 59 * MIN, 100, 105.5, 99.9, 104));    // +1R touch → BE
        bars3.add(mk(t0 + 60 * MIN, 104, 104.2, 99.9, 100.2));  // retest entry → BE exit @100
        List<AiTrainer.T> be = AiTrainer.simulate(bars3, (k, i) -> {
            if (i != 58) return new ArrayList<>();
            StrategyPack.Signal s = new StrategyPack.Signal();
            s.strategy = "TEST"; s.side = "BUY"; s.sigTs = k.get(58).ts; s.refPrice = 100;
            s.slPrice = 95; s.boundary = 94; s.windowBars = 5; s.note = "be test";
            List<StrategyPack.Signal> out = new ArrayList<>(); out.add(s); return out;
        }, 0.0005, 0);
        check("ai.sim.be", be.size() == 1 && Math.abs(be.get(0).r) < 0.05,
                be.isEmpty() ? "none" : "r=" + String.format("%.4f", be.get(0).r) + " (breakeven, sirf fees)");

        // ================= 6) stats + weights =================
        List<AiTrainer.T> ts = new ArrayList<>();
        for (int i = 0; i < 6; i++) { AiTrainer.T t = new AiTrainer.T(); t.ts = i; t.r = 2; ts.add(t); }
        for (int i = 0; i < 4; i++) { AiTrainer.T t = new AiTrainer.T(); t.ts = i; t.r = -1; ts.add(t); }
        double[] st = AiTrainer.stats(ts);
        check("ai.stats", st[0] == 10 && Math.abs(st[1] - 0.6) < 1e-9 && Math.abs(st[2] - 3.0) < 1e-9,
                "n=10 wr=60% pf=3.0 (6×2R win / 4×1R loss)");
        check("ai.weight.high", AiTrainer.weightFrom(1.6) == 1.3 && AiTrainer.weightFrom(1.4) == 1.15, "PF boost");
        check("ai.weight.mid", AiTrainer.weightFrom(1.2) == 1.0 && AiTrainer.weightFrom(0.95) == 0.8, "PF neutral/cautious");
        check("ai.weight.low", AiTrainer.weightFrom(0.5) == 0.6, "PF loser");
        check("ai.enabled", AiTrainer.enabledFrom(0, 2.0) == 1 && AiTrainer.enabledFrom(50, 0.8) == 0
                && AiTrainer.enabledFrom(50, 1.2) == 1, "n=0 neutral, PF<0.9 pause");
        JSONObject row = AiTrainer.resJson(new AiTrainer.Res());
        check("ai.resJson", row != null && row.optInt("on") == 1, "resJson safe");

        // ================= 7) OOS split =================
        List<AiTrainer.T> oos = new ArrayList<>();
        for (int i = 0; i < 10; i++) { AiTrainer.T t = new AiTrainer.T(); t.ts = i * 1000; t.r = (i == 9) ? -1 : 2; oos.add(t); }
        double[] oo = AiTrainer.oosStats(oos, 7000);   // last 3 trades (2W 1L)
        check("ai.oos", oo[0] == 3 && Math.abs(oo[1] - 2.0 / 3) < 1e-9 && Math.abs(oo[2] - 4.0) < 1e-9,
                "OOS n=3 wr=66.7% pf=4.0");

        // ================= 8) prevDayMap (O(n)) =================
        long day0 = (t0 / 86400000L) * 86400000L;   // day-aligned UTC midnight
        List<EngineCore.Candle> twoDays = new ArrayList<>();
        for (int i = 0; i < 96; i++) twoDays.add(mk(day0 + i * 15 * MIN, 100, 110, 90, 105));   // day1 hi=110 lo=90
        for (int i = 0; i < 96; i++) twoDays.add(mk(day0 + 86400000L + i * 15 * MIN, 105, 108, 95, 106));
        double[][] pdm = AiTrainer.prevDayMap(twoDays);
        check("ai.prevDayMap", pdm[95] == null && pdm[96] != null && Math.abs(pdm[96][0] - 110) < 1e-9
                && Math.abs(pdm[96][1] - 90) < 1e-9 && Math.abs(pdm[191][0] - 110) < 1e-9,
                "day2+ me day1 ka hi/lo (110/90)");

        // ================= 9) Universe helpers =================
        check("uni.bucket", "MAJOR".equals(EngineCore.bucketForRank(1)) && "MAJOR".equals(EngineCore.bucketForRank(10))
                && "RETAIL".equals(EngineCore.bucketForRank(11)) && "RETAIL".equals(EngineCore.bucketForRank(60))
                && "ALTCOIN".equals(EngineCore.bucketForRank(61)) && "ALTCOIN".equals(EngineCore.bucketForRank(300)),
                "rank 1-10 MAJOR, 11-60 RETAIL, 61+ ALTCOIN");
        check("uni.stableExclude", EngineCore.STABLE_BASES.contains("USDC") && EngineCore.STABLE_BASES.contains("FDUSD")
                && !EngineCore.STABLE_BASES.contains("SOL"), "stable-stable pairs exclude, real coins nahi");
        check("uni.pairsSeed", EngineCore.BINANCE_PAIRS.containsKey("BTCUSDT") && EngineCore.BINANCE_PAIRS.size() == 7,
                "seed 7 pairs barkarar");

        // ================= 10) Shaakuni training signals (no-crash) =================
        boolean shkCrash = false; int shkN = 0;
        try {
            List<EngineCore.Candle> k = randomWalk(300, t0, 99, 100, 0.05);
            for (int i = 210; i < k.size() - 1; i++)
                for (StrategyPack.Signal s : AiTrainer.shaakuniSignals(k, i, "SHK5_PD_EMA200")) { shkN++; if (s.slPrice <= 0) shkCrash = true; }
        } catch (Throwable t) { shkCrash = true; }
        check("ai.shk5.noCrash", !shkCrash, "SHK5 PD+EMA200 signals=" + shkN);

        // ================= 11) Pack simulate end-to-end (uptrend regime) =================
        List<EngineCore.Candle> up = randomWalk(600, t0, 1234, 50, 0.25);
        List<AiTrainer.T> tr = AiTrainer.simulate(up, (k, i) -> {
            List<StrategyPack.Signal> out = new ArrayList<>();
            StrategyPack.Signal s = StrategyPack.bbSqueeze(k, i);
            if (s != null) out.add(s);
            return out;
        }, 0.0005, 2);
        check("ai.e2e.bb", true, "S2 on 600-bar walk: " + tr.size() + " trades (no-crash)");

        System.out.println("\n===== V4.4 TEST: " + pass + " passed, " + fail + " failed =====");
        System.exit(fail == 0 ? 0 : 1);
    }
}
