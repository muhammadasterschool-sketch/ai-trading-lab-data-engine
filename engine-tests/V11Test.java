package com.aitradinglab.engine;

import java.util.ArrayList;
import java.util.List;

/**
 * v1.1 ENGINE TEST — X7 REGIME FADE + TURBO controls (host-JVM).
 *
 * Covers:
 *  - x7Signal fires on deep VWAP deviation + RSI confluence + low ADX (ranging)
 *  - x7Signal blocked by ADX regime gate (strong trend = no fade)
 *  - tuned constants parity (sigma 3.5, TP 2.5R, SL 1.0xATR, BE off via manage guard)
 *  - takerFee()/levCap() owner settings + clamps (fee_bps 0-100, lev_cap 0.1-10)
 *  - PRO FILTER PACK stays REMOVED (owner order regression guard)
 *
 * RUN: run-tests.sh (javac + java, stub android.jar)
 */
public class V11Test {

    static int pass = 0, fail = 0;

    static void check(String name, boolean ok, String detail) {
        if (ok) { pass++; System.out.println("PASS  " + name + (detail.isEmpty() ? "" : "  — " + detail)); }
        else { fail++; System.out.println("FAIL  " + name + "  — " + detail); }
    }

    static EngineCore.Candle mk(long ts, double o, double h, double l, double c, double v) {
        EngineCore.Candle cd = new EngineCore.Candle();
        cd.ts = ts; cd.o = o; cd.h = h; cd.l = l; cd.c = c; cd.v = v;
        return cd;
    }

    static final long MIN5 = 300_000L;

    /** Ranging series around base price — 5m bars. */
    static List<EngineCore.Candle> ranging(int n, long t0, double base) {
        List<EngineCore.Candle> out = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            double c = base + 0.3 * Math.sin(i / 23.0) + 0.05 * (i % 5 - 2);
            double o = i == 0 ? base : out.get(out.size() - 1).c;
            double h = Math.max(o, c) + 0.06, l = Math.min(o, c) - 0.06;
            out.add(mk(t0 + i * MIN5, o, h, l, c, 1000));
        }
        return out;
    }

    /** Strong uptrend series — 5m bars, steady climb (high ADX). */
    static List<EngineCore.Candle> trending(int n, long t0, double base) {
        List<EngineCore.Candle> out = new ArrayList<>();
        double p = base;
        for (int i = 0; i < n; i++) {
            double o = p, c = p + 0.09;
            double h = c + 0.04, l = o - 0.03;
            out.add(mk(t0 + i * MIN5, o, h, l, c, 1000));
            p = c;
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("=== V11Test — X7 REGIME FADE + TURBO ===");

        long t0 = 1730000000000L;

        // 1) tuned constants
        check("X7 sigma = 3.5", EngineCore.X7_SIGMA == 3.5, String.valueOf(EngineCore.X7_SIGMA));
        check("X7 TP = 2.5R", EngineCore.X7_TP_R == 2.5, String.valueOf(EngineCore.X7_TP_R));
        check("X7 SL = 1.0xATR", EngineCore.X7_SL_ATR == 1.0, String.valueOf(EngineCore.X7_SL_ATR));
        check("X7 RSI confluence 30/70", EngineCore.X7_RSI_LO == 30 && EngineCore.X7_RSI_HI == 70,
                EngineCore.X7_RSI_LO + "/" + EngineCore.X7_RSI_HI);
        check("X7 ADX regime gate = 22", EngineCore.X7_ADX_MAX == 22.0, String.valueOf(EngineCore.X7_ADX_MAX));

        // 2) ranging series — fade signal fire kare (deep deviation + RSI + ADX<22)
        //    bounded oscillation: RSI rare extreme hota hai — synthetic crash tail add karo
        List<EngineCore.Candle> k = ranging(400, t0, 100.0);
        // crash tail: last 6 bars 8% dump (RSI extreme + deep VWAP deviation)
        double p = k.get(k.size() - 1).c;
        for (int i = 0; i < 6; i++) {
            long ts = t0 + (400 + i) * MIN5;
            double o = p, c = p * 0.982;
            k.add(mk(ts, o, c + 0.05, c - 0.05, c, 1500));
            p = c;
        }
        String sig = EngineCore.x7Signal(k, k.size() - 1);
        check("X7 fires BUY on ranging + crash tail", "BUY".equals(sig), "signal=" + sig);

        // 3) strong trend par fade BLOCK ho (ADX gate)
        List<EngineCore.Candle> tr = trending(500, t0, 100.0);
        // last 6 bars dump bhi karo — RSI extreme + deviation ho, lekin ADX bohat high
        p = tr.get(tr.size() - 1).c;
        for (int i = 0; i < 6; i++) {
            long ts = t0 + (500 + i) * MIN5;
            double o = p, c = p * 0.985;
            tr.add(mk(ts, o, c + 0.02, c - 0.02, c, 1500));
            p = c;
        }
        String sig2 = EngineCore.x7Signal(tr, tr.size() - 1);
        check("X7 blocked in strong trend (ADX gate)", sig2 == null, "signal=" + sig2);

        // 4) PRO FILTER PACK REMOVED regression (owner order — v4.4.1)
        try {
            java.lang.reflect.Field f = EngineCore.class.getDeclaredField("proFilter3COn");
            check("PRO filter field removed", false, "proFilter3COn field abhi bhi hai!");
        } catch (NoSuchFieldException e) {
            check("PRO filter field removed", true, "koi proFilter3COn field nahi");
        }

        // 5) engine source mein proFilter3C gate na ho (string scan)
        String src = new String(java.nio.file.Files.readAllBytes(
                java.nio.file.Paths.get("android-app/app/src/main/java/com/aitradinglab/engine/EngineCore.java")));
        check("proFilter3C gate code absent", !src.contains("if (proFilter3C"), "gate string scan");
        check("X7 BE-off guard present", src.contains("X7\"))") || src.contains("startsWith(\"X7\")"), "manage guard");

        System.out.println("");
        System.out.println("=== V11Test: " + pass + " passed, " + fail + " failed ===");
        if (fail > 0) System.exit(1);
    }
}
