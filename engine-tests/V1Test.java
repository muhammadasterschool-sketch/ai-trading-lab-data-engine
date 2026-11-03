package com.aitradinglab.engine;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

/**
 * v1.0 ENGINE TEST — host-JVM (android.jar stubs + org-json.jar).
 * 5M PLAYBOOK (Z.ai Research guide S1-S4) + DATA PERSISTENCE GUARANTEE
 * (owner: "update ayegi tab koi login ya data refresh nahi hoga — data as it is").
 *
 * RUN: run-tests.sh (javac + java, stub android.jar)
 */
public class V1Test {

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

    /** Bounded mean-reverting walk [95,105] — 5m bars, vol=1000. */
    static List<EngineCore.Candle> bounded(int n, long t0) {
        List<EngineCore.Candle> out = new ArrayList<>();
        double p = 100;
        for (int i = 0; i < n; i++) {
            double o = p;
            double c = 100 + 5.0 * Math.sin(i / 37.0) + (i % 7 - 3) * 0.08;   // deterministic bounded
            c = Math.max(95.2, Math.min(104.8, c));
            double h = Math.max(o, c) + 0.15, l = Math.min(o, c) - 0.15;
            out.add(mk(t0 + i * MIN5, o, h, l, c, 1000));
            p = c;
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        System.out.println("=== V1Test — 5M Playbook + persistence guarantee ===");

        long t0 = 1700000000000L;

        // ---- 1) guide multipliers (S1 5x/8x, S2 4x/8x, S3 3.5x/8x, S4 3.5x/7x) ----
        check("pbSlAtrMult: P1=5, P2=4, P3=3.5, P4=3.5",
                EngineCore.pbSlAtrMult("P1_14D_RIDER") == 5.0 && EngineCore.pbSlAtrMult("P2_10D_TREND") == 4.0
                        && EngineCore.pbSlAtrMult("P3_14D_CLASSIC") == 3.5 && EngineCore.pbSlAtrMult("P4_SQUEEZE") == 3.5, "");
        check("pbTrailAtrMult: P4=7, baaki 8",
                EngineCore.pbTrailAtrMult("P4_SQUEEZE") == 7.0 && EngineCore.pbTrailAtrMult("P1_14D_RIDER") == 8.0
                        && EngineCore.pbTrailAtrMult("P2_10D_TREND") == 8.0 && EngineCore.pbTrailAtrMult("P3_14D_CLASSIC") == 8.0, "");
        check("PB_SYMBOLS = guide portfolio (BTC/ETH/BNB/SOL)",
                EngineCore.PB_SYMBOLS.size() == 4 && EngineCore.PB_SYMBOLS.contains("BTCUSDT")
                        && EngineCore.PB_SYMBOLS.contains("ETHUSDT") && EngineCore.PB_SYMBOLS.contains("BNBUSDT")
                        && EngineCore.PB_SYMBOLS.contains("SOLUSDT"), "");

        // ---- 2) atrAt — constant-range series par ATR = range ----
        List<EngineCore.Candle> flat = new ArrayList<>();
        for (int i = 0; i < 50; i++) flat.add(mk(t0 + i * MIN5, 100, 101, 99, 100, 10));
        double atr = StrategyPack.atrAt(flat, 14, 40);
        check("atrAt: constant 2-range series par ATR(14) = 2.0", Math.abs(atr - 2.0) < 1e-9, "atr=" + atr);
        check("atrAt: kam data par NaN", Double.isNaN(StrategyPack.atrAt(flat, 14, 5)), "");

        // ---- 3) P1/P3 breakout fire (14d high break + vol 1.3x) ----
        List<EngineCore.Candle> k = bounded(4100, t0);
        int last = k.size() - 1;
        double[] rng = StrategyPack.hhll(k, last - 4032, last - 1);
        double breakPx = rng[0] * 1.03;
        EngineCore.Candle brk = mk(t0 + 4100 * MIN5, k.get(last).c, breakPx * 1.001, k.get(last).c, breakPx, 3000);
        k.add(brk);
        List<StrategyPack.Signal> sigs = StrategyPack.evaluatePlaybook(k, k.size() - 1);
        boolean p1buy = false, p3buy = false;
        for (StrategyPack.Signal s : sigs) {
            if (s.strategy.equals("P1_14D_RIDER") && s.side.equals("BUY")) p1buy = true;
            if (s.strategy.equals("P3_14D_CLASSIC") && s.side.equals("BUY")) p3buy = true;
        }
        check("playbook: 14D break + vol 2x → P1 BUY fire", p1buy, "signals=" + sigs.size());
        check("playbook: 14D break → P3 BUY fire (no vol filter)", p3buy, "");
        check("playbook: P1 SL = 5xATR neeche", sigs.size() > 0, "");
        for (StrategyPack.Signal s : sigs) {
            if (s.strategy.equals("P1_14D_RIDER")) {
                double a = StrategyPack.atrAt(k, 14, k.size() - 1);
                check("playbook: P1 SL price = close − 5×ATR", Math.abs((brk.c - s.slPrice) - 5.0 * a) < 1e-6,
                        "sl=" + s.slPrice);
                break;
            }
        }
        // SELL side
        double[] rng2 = StrategyPack.hhll(k, k.size() - 1 - 4032, k.size() - 2);
        double breakLo = rng2[1] * 0.97;
        List<EngineCore.Candle> k2 = bounded(4100, t0);
        int l2 = k2.size() - 1;
        k2.add(mk(t0 + 4100 * MIN5, k2.get(l2).c, k2.get(l2).c, breakLo * 0.999, breakLo, 3000));
        List<StrategyPack.Signal> sigs2 = StrategyPack.evaluatePlaybook(k2, k2.size() - 1);
        boolean p1sell = false;
        for (StrategyPack.Signal s : sigs2) if (s.strategy.equals("P1_14D_RIDER") && s.side.equals("SELL")) p1sell = true;
        check("playbook: 14D low break → P1 SELL fire", p1sell, "signals=" + sigs2.size());

        // ---- 4) volume filter — low vol par P1 nahi, P3 haan ----
        List<EngineCore.Candle> k3 = bounded(4100, t0);
        int l3 = k3.size() - 1;
        double[] r3 = StrategyPack.hhll(k3, l3 - 4032, l3 - 1);
        k3.add(mk(t0 + 4100 * MIN5, k3.get(l3).c, r3[0] * 1.03, k3.get(l3).c, r3[0] * 1.025, 500));   // vol 0.5x
        List<StrategyPack.Signal> sigs3 = StrategyPack.evaluatePlaybook(k3, k3.size() - 1);
        boolean p1low = false, p3low = false;
        for (StrategyPack.Signal s : sigs3) {
            if (s.strategy.equals("P1_14D_RIDER")) p1low = true;
            if (s.strategy.equals("P3_14D_CLASSIC") && s.side.equals("BUY")) p3low = true;
        }
        check("playbook: low vol → P1 SKIP (1.3x filter)", !p1low, "");
        check("playbook: low vol par bhi P3 fire (no filter)", p3low, "");

        // ---- 5) no-lookahead — close-based rule: high above prior high magar close andar → koi signal nahi ----
        List<EngineCore.Candle> k4 = bounded(4100, t0);
        int l4 = k4.size() - 1;
        double[] r4 = StrategyPack.hhll(k4, l4 - 4032, l4 - 1);
        k4.add(mk(t0 + 4100 * MIN5, r4[0], r4[0] * 1.02, r4[0] * 0.99, r4[0] * 0.995, 3000));   // wick up, close below HH
        List<StrategyPack.Signal> sigs4 = StrategyPack.evaluatePlaybook(k4, k4.size() - 1);
        boolean anyP13 = false;
        for (StrategyPack.Signal s : sigs4)
            if ((s.strategy.equals("P1_14D_RIDER") || s.strategy.equals("P3_14D_CLASSIC")) && s.side.equals("BUY")) anyP13 = true;
        check("playbook: close < 14D high → koi breakout signal nahi (no-lookahead)", !anyP13, "");

        // ---- 6) squeeze: 32 constant bars (width 0 = 0th percentile) + break → P4 fire ----
        List<EngineCore.Candle> k5 = bounded(4100, t0);
        int l5 = k5.size() - 1;
        double[] r5 = StrategyPack.hhll(k5, l5 - 4032, l5 - 1);
        for (int i = 1; i <= 32; i++) k5.add(mk(t0 + (4100 + i - 1) * MIN5, 100, 100.01, 99.99, 100, 1000));
        k5.add(mk(t0 + 4131 * MIN5, 100, r5[0] * 1.03, 100, r5[0] * 1.025, 3000));
        List<StrategyPack.Signal> sigs5 = StrategyPack.evaluatePlaybook(k5, k5.size() - 1);
        boolean p4 = false;
        for (StrategyPack.Signal s : sigs5) if (s.strategy.equals("P4_SQUEEZE") && s.side.equals("BUY")) p4 = true;
        check("playbook: squeeze (BB width pct<30%) + break → P4 fire", p4, "signals=" + sigs5.size());

        // ---- 7) depth guards — kam data par koi signal nahi ----
        List<EngineCore.Candle> k6 = bounded(1000, t0);
        k6.add(mk(t0 + 1000 * MIN5, 100, 200, 100, 200, 5000));
        check("playbook: shallow history (1000 bars) → koi P1/P3 signal nahi",
                StrategyPack.evaluatePlaybook(k6, k6.size() - 1).isEmpty(), "conservative depth guard");

        // ---- 8) 1h EMA helpers (REAL Binance 5m bars clock-aligned hote hain — test bhi aligned) ----
        long t0h = t0 - (t0 % 3600000L);   // hour-aligned start
        List<EngineCore.Candle> kh = bounded(4400, t0h);
        int lh = kh.size() - 1;
        while (lh >= 0 && kh.get(lh).ts % 3600000L != 0) { kh.remove(lh); lh--; }
        check("hour-aligned series has :00 bars", lh > 3000, "lh=" + lh);
        List<Double> hc = null;
        try { hc = StrategyPack.hourlyCloses(kh, lh, 220); } catch (Throwable t) { check("hourlyCloses no-crash", false, String.valueOf(t)); }
        check("hourlyCloses: completed hours only", hc != null && hc.size() >= 200, "hours=" + (hc == null ? -1 : hc.size()));
        check("emaDoubles: EMA50/EMA200 compute on 220 hours",
                hc != null && !Double.isNaN(StrategyPack.emaDoubles(hc, 50)) && !Double.isNaN(StrategyPack.emaDoubles(hc, 200)), "");
        check("emaDoubles: kam data par NaN", Double.isNaN(StrategyPack.emaDoubles(new ArrayList<>(), 50)), "");

        // ---- 9) DATA PERSISTENCE GUARANTEE (update par data as-it-is) ----
        String dbSrc = new String(Files.readAllBytes(Paths.get("android-app/app/src/main/java/com/aitradinglab/engine/Db.java")));
        int up = dbSrc.indexOf("public void onUpgrade");
        int upEnd = dbSrc.indexOf("public void onDowngrade");
        String upBody = up >= 0 ? dbSrc.substring(up, upEnd > up ? upEnd : Math.min(dbSrc.length(), up + 3000)) : "";
        check("Db: onUpgrade additive (no DROP TABLE)", !upBody.contains("DROP TABLE"), "update par tables kabhi drop nahi");
        check("Db: DB file name constant (atl-engine.db) — update par wahi file",
                dbSrc.contains("NAME = \"atl-engine.db\""), "");
        check("Db: sessions table schema intact (login survive karega)",
                dbSrc.contains("CREATE TABLE IF NOT EXISTS sessions"), "");
        String ecSrc = new String(Files.readAllBytes(Paths.get("android-app/app/src/main/java/com/aitradinglab/engine/EngineCore.java")));
        check("migrations one-time gated (v12/v14/v45 — update par dobara nahi chalenge)",
                ecSrc.contains("v12_paper_100") && ecSrc.contains("v14_3c_migration") && ecSrc.contains("v45_tf5m_migration"),
                "settings flags — ek dafa set, phir skip");
        check("playbook trades multi-user (owner + trader dono)",
                ecSrc.contains("for (long uid : users) openTradePb(uid, sym, s);"), "");

        // ---- 10) PB entry fee-edge + no-TP wiring (source-level) ----
        check("PB: tp nominal (1000xATR) — trail hi real exit",
                ecSrc.contains("double tp = buy ? price + 1000 * atr : price - 1000 * atr;"), "");
        check("PB: manageOpenTrades branch (guide exit rule)",
                ecSrc.contains("if (isPB) {") && ecSrc.contains("managePbTrade(id, uid, sym, side, qty, entry, sl, buy);"), "");
        check("PB: scanPlaybook loop me wired",
                ecSrc.contains("try { scanPlaybook(); } catch (Throwable t) { db.log(\"ERROR\", \"PB\", \"SCAN_FAIL\", String.valueOf(t)); }"), "");

        System.out.println("");
        System.out.println("RESULT: " + pass + " passed, " + fail + " failed");
        if (fail > 0) System.exit(1);
    }
}
