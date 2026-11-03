package com.aitradinglab.engine;

import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * v4.4.2/v4.5.0 ENGINE TEST — host-JVM (android.jar stubs + org-json.jar).
 * DATA FAILOVER GUARDS: SAFE MODE quorum latch (flap fix), NaN/zero candle guard,
 * 5m system shift (owner: "pure system 5m timeframe"), version + UI labels.
 *
 * RUN: run-tests.sh (javac + java, stub android.jar)
 */
public class V442Test {

    static int pass = 0, fail = 0;

    static void check(String name, boolean ok, String detail) {
        if (ok) { pass++; System.out.println("PASS  " + name + (detail.isEmpty() ? "" : "  — " + detail)); }
        else { fail++; System.out.println("FAIL  " + name + "  — " + detail); }
    }

    static String src(String rel) throws Exception {
        return new String(Files.readAllBytes(Paths.get(rel)));
    }

    public static void main(String[] args) throws Exception {
        System.out.println("=== V442Test — v4.4.2 failover + v4.5.0 5m shift ===");

        // ---- 1) 5m SYSTEM SHIFT (owner: poora system 5m) ----
        check("TF15 constant = 5m", "5m".equals(EngineCore.TF15), "TF15=" + EngineCore.TF15);
        check("TF_MS public = 300000 (5m)", EngineCore.TF_MS_PUB == 300_000L, "TF_MS_PUB=" + EngineCore.TF_MS_PUB);
        check("TF15_MS = 300000 (5m)", EngineCore.TF15_MS == 300_000L, "TF15_MS=" + EngineCore.TF15_MS);
        try {
            Field f = EngineCore.class.getDeclaredField("TF");
            f.setAccessible(true);
            check("TF (3C tier) = 5m", "5m".equals(f.get(null)), "TF=" + f.get(null));
        } catch (Throwable t) {
            check("TF (3C tier) = 5m", false, String.valueOf(t));
        }

        // ---- 2) NaN / ZERO CANDLE GUARD (data pipeline poison fix) ----
        check("candleOk: valid candle accepted", EngineCore.candleOk(1700000000000L, 100, 101, 99, 100.5, 50), "");
        check("candleOk: NaN high rejected", !EngineCore.candleOk(1700000000000L, 100, Double.NaN, 99, 100.5, 50), "NaN OHLC DB me nahi jayegi");
        check("candleOk: zero close rejected", !EngineCore.candleOk(1700000000000L, 100, 101, 99, 0, 50), "");
        check("candleOk: negative open rejected", !EngineCore.candleOk(1700000000000L, -5, 101, 99, 100.5, 50), "");
        check("candleOk: h<l ordering rejected", !EngineCore.candleOk(1700000000000L, 100, 50, 99, 100.5, 50), "high low se neeche — corrupt bar");
        check("candleOk: ts=0 rejected", !EngineCore.candleOk(0, 100, 101, 99, 100.5, 50), "");
        check("candleOk: negative volume rejected", !EngineCore.candleOk(1700000000000L, 100, 101, 99, 100.5, -1), "");
        check("candleOk: NaN volume rejected", !EngineCore.candleOk(1700000000000L, 100, 101, 99, 100.5, Double.NaN), "");

        // parseBinanceKlines end-to-end: valid rows pass, corrupt row skip hoti hai
        String body = "[[1700000000000,\"100\",\"101\",\"99\",\"100.5\",\"50\"],"
                + "[1700000030000,\"0\",\"0\",\"0\",\"0\",\"0\"],"
                + "[1700000060000,\"200\",\"202\",\"198\",\"201\",\"70\"]]";
        java.util.List<EngineCore.Candle> ks = EngineCore.parseBinanceKlines(body);
        check("parseBinanceKlines: corrupt row dropped, 2 valid", ks.size() == 2, "got " + ks.size());
        check("parseBinanceKlines: ts = openTime", ks.size() == 2 && ks.get(0).ts == 1700000000000L && ks.get(1).ts == 1700000060000L, "");
        check("parseBinanceKlines: bad JSON -> empty (no throw)", EngineCore.parseBinanceKlines("not json").isEmpty(), "");
        check("parseBinanceKlines: empty array -> empty", EngineCore.parseBinanceKlines("[]").isEmpty(), "");

        // ---- 3) SAFE MODE QUORUM LATCH (flap fix — ek stale symbol global flag nahi flapp karega) ----
        check("latch: full outage (0/10 fresh) -> ON", EngineCore.latchSafeMode(false, 10, 0), "");
        check("latch: recovery (9/10 fresh) -> OFF", !EngineCore.latchSafeMode(true, 10, 9), "");
        check("latch: hysteresis hold (3/10=30%) stays ON", EngineCore.latchSafeMode(true, 10, 3), "20-60% band me purana state hold");
        check("latch: hysteresis hold (3/10=30%) stays OFF", !EngineCore.latchSafeMode(false, 10, 3), "");
        check("latch: small sample (4 checked) no change", EngineCore.latchSafeMode(true, 4, 0) && !EngineCore.latchSafeMode(false, 4, 0), "boot/low-sample par flap nahi");
        check("latch: 20% boundary latches ON", EngineCore.latchSafeMode(false, 10, 2), "");
        check("latch: 60% boundary clears", !EngineCore.latchSafeMode(true, 10, 6), "");
        check("latch: 70% stale from OFF stays OFF", !EngineCore.latchSafeMode(false, 100, 30), "single-symbol staleness ab SAFE MODE nahi lagati");

        // ---- 4) freshData ab global flag ko touch nahi karta (source-level regression guard) ----
        String ec = src("android-app/app/src/main/java/com/aitradinglab/engine/EngineCore.java");
        int fd = ec.indexOf("private boolean freshData(String sym)");
        int is = ec.indexOf("public boolean isSafeMode()");
        check("freshData region flag-free", fd > 0 && is > fd
                && !ec.substring(fd, is).contains("safeMode = true")
                && !ec.substring(fd, is).contains("safeMode = false"), "freshData sirf per-symbol gate");
        check("refreshCandles calls updateFeedHealth", ec.contains("updateFeedHealth();   // v4.4.2"), "");
        check("updateFeedHealth quorum latch used", ec.contains("safeMode = latchSafeMode(prev, checked, freshCnt)"), "");
        check("candleOk guard wired in parseBinanceKlines", ec.contains("if (!candleOk(k.getLong(0), o, h, l, c, k.getDouble(5))) continue;"), "");
        check("candleOk guard wired in fetchFromBridge", ec.contains("if (!candleOk(cd.ts, cd.o, cd.h, cd.l, cd.c, cd.v)) continue;"), "");
        check("v4.5 one-time 5m migration present", ec.contains("v45_tf5m_migration") && ec.contains("MIGRATION_5M"), "");

        // ---- 5) VERSION + UI + API LABELS ----
        String gradle = src("android-app/app/build.gradle");
        check("build.gradle versionCode 1", gradle.contains("versionCode 1"), "");
        check("build.gradle versionName 1.0", gradle.contains("versionName \"1.0\""), "");
        String api = src("android-app/app/src/main/java/com/aitradinglab/engine/Api.java");
        check("Api health: version 1.0", api.contains("\"version\", \"1.0\""), "");
        check("Api health: timeframe 5m", api.contains("\"timeframe\", \"5m\""), "");
        String dash = src("android-app/app/src/main/assets/dashboard.html");
        check("dashboard: v1.0 header", dash.contains("v1.0"), "");
        check("dashboard: 5m PDF pack banner", dash.contains("5m PDF pack SAB par"), "");
        check("dashboard: 5m scan tier", dash.contains("5m scan top-"), "");
        check("dashboard: no stale 15m label", !dash.contains("15m PDF pack"), "purana 15m text gaya");

        System.out.println("");
        System.out.println("RESULT: " + pass + " passed, " + fail + " failed");
        if (fail > 0) System.exit(1);
    }
}
