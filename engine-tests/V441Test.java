package com.aitradinglab.engine;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * v4.4.1 ENGINE TEST — PRO FILTER PACK REMOVAL guard (host-JVM).
 *
 * OWNER ORDER: "Pro filter remove kardo — is ki waja se buhut saari trades place
 * hi nahi kar raha". Ye test lock karta hai ke:
 *   1) EngineCore source me proFilter3C gate ka KOI call nahi
 *   2) SETUP_FILTERED event ab kahin write nahi hota
 *   3) purane 4 filter getters/settings (proRdMin/proEmaFilter/proAtrFloor/
 *      proVolFilter + threec_*_pct keys) Api/EngineCore me nahi
 *   4) dashboard.html me PRO FILTER card/chip/setFilter helper nahi
 *   5) walk3C ka detect3C output seedha pending hota hai (no gate between)
 *
 * RUN: run-tests.sh (javac + java, stub android.jar)
 */
public class V441Test {

    static int pass = 0, fail = 0;

    static void check(String name, boolean ok, String detail) {
        if (ok) { pass++; System.out.println("PASS  " + name + (detail.isEmpty() ? "" : "  — " + detail)); }
        else { fail++; System.out.println("FAIL  " + name + "  — " + detail); }
    }

    static String read(Path p) {
        try { return new String(Files.readAllBytes(p)); }
        catch (IOException e) { return ""; }
    }

    public static void main(String[] args) throws Exception {
        Path root = Paths.get(System.getProperty("user.dir"));
        // run-tests.sh BASE = repo root; test cwd = repo root
        Path engine = root.resolve("android-app/app/src/main/java/com/aitradinglab/engine");
        Path coreSrc = engine.resolve("EngineCore.java");
        Path apiSrc = engine.resolve("Api.java");
        Path dash = root.resolve("android-app/app/src/main/assets/dashboard.html");

        String core = read(coreSrc);
        String api = read(apiSrc);
        String html = read(dash);
        check("src.files.read", !core.isEmpty() && !api.isEmpty() && !html.isEmpty(),
                "EngineCore " + core.length() + "B, Api " + api.length() + "B, dashboard " + html.length() + "B");

        // 1) gate function + call GONE
        check("core.gateFunctionGone", !core.contains("private Setup3C proFilter3C("),
                "proFilter3C() body removed");
        check("core.gateCallGone", !core.contains("s = proFilter3C("),
                "walk3C me koi filter call nahi — detect3C seedha pending");

        // 2) SETUP_FILTERED event writes GONE
        check("core.noSetupFilteredWrite", !core.contains("SETUP_FILTERED"),
                "event ab kahin log nahi hota (purane logs report se bhi hat gaye)");

        // 3) filter getters + settings keys GONE (EngineCore + Api)
        check("core.gettersGone", !core.contains("public double proRdMin()")
                && !core.contains("public boolean proEmaFilter()")
                && !core.contains("public double proAtrFloor()")
                && !core.contains("public boolean proVolFilter()"),
                "4 getter deleted");
        check("api.settingsGone", !api.contains("proRdMin") && !api.contains("proEmaFilter")
                && !api.contains("proAtrFloor") && !api.contains("proVolFilter"),
                "Api status/save handlers deleted");
        check("api.settingKeysGone", !api.contains("threec_rd_min_pct")
                && !api.contains("threec_ema_filter") && !api.contains("threec_atr_floor_pct")
                && !api.contains("threec_vol_filter"),
                "DB setting keys ka koi writer nahi");
        // filter ki DB keys ab EngineCore me bhi nahi (purani values dead)
        check("core.settingKeysGone", !core.contains("threec_rd_min_pct")
                && !core.contains("threec_ema_filter") && !core.contains("threec_atr_floor_pct")
                && !core.contains("threec_vol_filter"),
                "EngineCore keys nahi padhta");

        // 4) dashboard UI GONE
        check("dash.cardGone", !html.contains("PRO FILTER PACK") && !html.contains("PRO FILTER REJECT"),
                "Settings card + Home chip deleted");
        check("dash.helperGone", !html.contains("setFilter") && !html.contains("filterMsg"),
                "JS helper + msg div deleted");

        // 5) walk3C indicators sirf DNA ke liye — volSma array delete, ema/atr arrays rahe
        check("core.dnaIndicatorsIntact", core.contains("double[] emaArr = new double[n];")
                && core.contains("double[] atrArr = new double[n];"),
                "c3EmaDist/c3AtrPct ML features barkarar");
        check("core.volSmaGone", !core.contains("double[] volSma"),
                "sirf volume-filter ka array delete");

        // 6) version bump
        check("ver.gradle", read(root.resolve("android-app/app/build.gradle")).contains("versionCode 37")
                && read(root.resolve("android-app/app/build.gradle")).contains("versionName \"4.4.1\""),
                "build.gradle 37 / 4.4.1");
        check("ver.api", api.contains("\"4.4.1\""), "health version 4.4.1");
        check("ver.core", core.contains("\"4.4.1\""), "status version 4.4.1");

        System.out.println("\n===== V4.4.1 TEST: " + pass + " passed, " + fail + " failed =====");
        System.exit(fail == 0 ? 0 : 1);
    }
}
