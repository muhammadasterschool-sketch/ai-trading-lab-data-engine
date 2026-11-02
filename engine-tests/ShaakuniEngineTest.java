package com.aitradinglab.engine;

import java.util.ArrayList;
import java.util.List;
import java.util.ArrayList;
import java.util.List;

/**
 * v4.1 SHAAKUNI ENGINE TEST — host-JVM (stubs + org.json.jar ke saath).
 * Shaakuni Trap Trader ke indicators ka synthetic-data verification:
 * uske apne TradingView script ke exact rules par assertions.
 *
 * RUN: javac + java (see run.sh)
 */
public class ShaakuniEngineTest {

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

    static final long MIN = 60_000L, DAY = 86_400_000L;
    static final long T0 = 1_760_000_000_000L;   // fixed epoch (2025-10-09 approx) — deterministic

    public static void main(String[] args) {
        // ================= 1) Binance klines parser =================
        String kl = "[[1760000000000,\"100\",\"110\",\"95\",\"105\",\"123.45\",1760000059999,\"0\"],"
                  + "[1760000060000,\"105\",\"112\",\"104\",\"111\",\"150\",1760000119999,\"0\"]]";
        List<EngineCore.Candle> parsed = EngineCore.parseBinanceKlines(kl);
        check("binance.parse.rows", parsed.size() == 2, "rows=" + parsed.size());
        check("binance.parse.values", parsed.size() == 2 && parsed.get(0).o == 100 && parsed.get(1).c == 111
                && parsed.get(0).ts == 1760000000000L, "o=" + (parsed.isEmpty() ? "-" : parsed.get(0).o));
        check("binance.parse.badOhlcSkipped", EngineCore.parseBinanceKlines("[[1,\"0\",\"0\",\"0\",\"0\",\"5\",2,\"x\"]]").isEmpty(),
                "zero-OHLC rows reject hone chahiye");

        // ================= 2) Prev day high/low =================
        List<EngineCore.Candle> twoDays = new ArrayList<>();
        long d0 = (T0 / DAY) * DAY;                     // day boundary
        for (int i = 0; i < 60; i++) twoDays.add(mk(d0 - DAY + i * MIN, 100, 110, 90, 105));   // yesterday: H=110 L=90
        for (int i = 0; i < 60; i++) twoDays.add(mk(d0 + i * MIN, 105, 120, 95, 118));          // today: H=120 L=95
        double[] pd = EngineCore.prevDayHighLow(twoDays);
        check("levels.prevDay", pd != null && Math.abs(pd[0] - 110) < 1e-9 && Math.abs(pd[1] - 90) < 1e-9,
                pd == null ? "null" : ("pdh=" + pd[0] + " pdl=" + pd[1]));
        check("levels.prevDaySingleDayNull", EngineCore.prevDayHighLow(twoDays.subList(0, 60)) == null, "1 din = null");

        // ================= 3) Sweep statuses =================
        // today: wick above PDH(110) but close back inside => SWEEP
        List<EngineCore.Candle> sweepDay = new ArrayList<>();
        for (int i = 0; i < 40; i++) sweepDay.add(mk(d0 - DAY + i * MIN, 100, 110, 90, 105));
        for (int i = 0; i < 30; i++) sweepDay.add(mk(d0 + i * MIN, 105, 106, 104, 105));
        sweepDay.add(mk(d0 + 30 * MIN, 105, 112, 104, 108));   // wick beyond 110, close 108 (inside)
        check("sweep.SWEEP", "SWEEP".equals(EngineCore.sweepStatus(sweepDay, 110, true)), "wick beyond + close inside");
        List<EngineCore.Candle> brokenDay = new ArrayList<>(sweepDay);
        brokenDay.set(brokenDay.size() - 1, mk(d0 + 30 * MIN, 105, 114, 104, 113));   // close beyond
        check("sweep.BROKEN", "BROKEN".equals(EngineCore.sweepStatus(brokenDay, 110, true)), "close beyond level");
        List<EngineCore.Candle> activeDay = new ArrayList<>();
        for (int i = 0; i < 40; i++) activeDay.add(mk(d0 - DAY + i * MIN, 100, 110, 90, 105));
        for (int i = 0; i < 20; i++) activeDay.add(mk(d0 + i * MIN, 100, 103, 98, 102));
        check("sweep.ACTIVE", "ACTIVE".equals(EngineCore.sweepStatus(activeDay, 110, true)), "level touch nahi hua aaj");

        // ================= 4) Structure walk (MSS/BOS) =================
        List<EngineCore.Candle> trend = new ArrayList<>();
        long ts = d0 - 2 * DAY;
        // 15 falling candles (downtrend)
        for (int i = 0; i < 15; i++) { trend.add(mk(ts, 120 - i, 121 - i, 100 - i, 101 - i)); ts += MIN; }
        // strong up impulse breaking the 10-bar swing high (body >> 0.7*ATR)
        trend.add(mk(ts, 90, 130, 89, 129)); ts += MIN;
        EngineCore.StructEvent se = EngineCore.structureWalk(trend, 10);
        check("structure.MSSbull", se != null && "BULL".equals(se.dir) && "MSS".equals(se.kind),
                se == null ? "null" : (se.kind + "/" + se.dir + " level=" + se.level));
        // second bull break => BOS (continuation) — pullback highs DESCEND karo
        // (Shaakuni rule: swing >= 3 bars old, tab hi break valid)
        trend.add(mk(ts, 129, 131, 125, 128)); ts += MIN;   // pullback 1 (h=131)
        trend.add(mk(ts, 128, 129, 126, 128.5)); ts += MIN; // pullback 2
        trend.add(mk(ts, 128.5, 128.8, 127, 128.6)); ts += MIN;  // pullback 3 — swing (131) ab 3 bars purana
        trend.add(mk(ts, 128.6, 140, 128, 139)); ts += MIN; // break => BOS
        EngineCore.StructEvent se2 = EngineCore.structureWalk(trend, 10);
        check("structure.BOSbull", se2 != null && "BOS".equals(se2.kind) && "BULL".equals(se2.dir),
                se2 == null ? "null" : (se2.kind + "/" + se2.dir));

        // ================= 5) Order blocks =================
        List<EngineCore.Candle> obSeq = new ArrayList<>();
        ts = d0 - DAY;
        // 20 down candles: price 120 -> 100 (down-candles exist before impulse)
        for (int i = 0; i < 20; i++) { obSeq.add(mk(ts, 120 - i, 121 - i, 119 - i, 119.5 - i)); ts += MIN; }
        // down candle @ idx20 = OB candidate (o=100,c=99.5)
        obSeq.add(mk(ts, 100, 100.5, 98, 99.5)); ts += MIN;
        // impulse up candle: body 20 (>= 0.7*ATR14)
        obSeq.add(mk(ts, 99.5, 120, 99, 120)); ts += MIN;
        // break-candle closing beyond the 10-bar swing high (~121 from earlier)
        obSeq.add(mk(ts, 120, 135, 119, 134)); ts += MIN;
        List<EngineCore.ObZone> obs = EngineCore.orderBlocks(obSeq, 10);
        boolean foundBull = false;
        for (EngineCore.ObZone z : obs) if (z.bullish && !z.mitigated) foundBull = true;
        check("ob.bullFound", foundBull, "zones=" + obs.size() + (obs.isEmpty() ? "" : " first=" + obs.get(0).bottom + "-" + obs.get(0).top));
        // mitigation: touch the zone afterwards
        if (!obs.isEmpty()) {
            EngineCore.ObZone z0 = obs.get(0);
            List<EngineCore.Candle> obSeq2 = new ArrayList<>(obSeq);
            obSeq2.add(mk(ts, 122, 123, z0.top - 0.5, 122.5));   // dips back into zone
            List<EngineCore.ObZone> obs2 = EngineCore.orderBlocks(obSeq2, 10);
            boolean mit = false;
            for (EngineCore.ObZone z : obs2) if (z.idx == z0.idx && z.mitigated) mit = true;
            check("ob.mitigated", mit, "touch => mitigated flag");
        } else {
            check("ob.mitigated", false, "OB hi nahi mila");
        }

        // ================= 6) FVG =================
        List<EngineCore.Candle> fvgSeq = new ArrayList<>();
        ts = d0;
        fvgSeq.add(mk(ts, 100, 101, 99, 100.5)); ts += MIN;
        fvgSeq.add(mk(ts, 100.5, 108, 100.2, 107.5)); ts += MIN;
        fvgSeq.add(mk(ts, 107.5, 110, 107, 109));             // low 107 > high[0] 101 => bull FVG
        double[] g = EngineCore.latestFvg(fvgSeq);
        check("fvg.bull", g != null && g[2] == 1 && Math.abs(g[0] - 101) < 1e-9 && Math.abs(g[1] - 107) < 1e-9,
                g == null ? "null" : (g[0] + "-" + g[1] + " dir=" + g[2]));

        // ================= 7) Sessions (NY time) =================
        java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("America/New_York"));
        cal.set(2026, java.util.Calendar.NOVEMBER, 2, 8, 30, 0); cal.set(java.util.Calendar.MILLISECOND, 0);
        EngineCore.Candle probe = mk(cal.getTimeInMillis(), 1, 1, 1, 1);
        check("session.newyork", "NEW YORK".equals(EngineCore.sessionNow(probe.ts)[0]) && "yes".equals(EngineCore.sessionNow(probe.ts)[1]),
                EngineCore.sessionNow(probe.ts)[0]);
        cal.set(2026, java.util.Calendar.NOVEMBER, 2, 3, 0, 0);
        check("session.london", "LONDON".equals(EngineCore.sessionNow(cal.getTimeInMillis())[0]),
                EngineCore.sessionNow(cal.getTimeInMillis())[0]);
        cal.set(2026, java.util.Calendar.NOVEMBER, 2, 22, 0, 0);
        check("session.asian", "ASIAN".equals(EngineCore.sessionNow(cal.getTimeInMillis())[0]),
                EngineCore.sessionNow(cal.getTimeInMillis())[0]);

        // ================= 8) Suite integrity =================
        check("suite.defined", EngineCore.SHAAKUNI_SUITE.length == 13 && EngineCore.INDICATOR_LIBRARY == EngineCore.SHAAKUNI_SUITE,
                "suite=" + EngineCore.SHAAKUNI_SUITE.length + " (82-indicator PDF library retired)");

        // ================= 9) Prev week =================
        List<EngineCore.Candle> twoWeeks = new ArrayList<>();
        long w0 = (T0 / (7 * DAY)) * (7 * DAY);
        for (int i = 0; i < 100; i++) twoWeeks.add(mk(w0 - 7 * DAY + i * 100 * MIN, 50, 55, 45, 52));
        for (int i = 0; i < 100; i++) twoWeeks.add(mk(w0 + i * 100 * MIN, 52, 60, 48, 58));
        double[] pw = EngineCore.prevWeekHighLow(twoWeeks);
        check("levels.prevWeek", pw != null && Math.abs(pw[0] - 55) < 1e-9 && Math.abs(pw[1] - 45) < 1e-9,
                pw == null ? "null" : ("pwh=" + pw[0] + " pwl=" + pw[1]));

        System.out.println("\n===== SHAAKUNI TEST: " + pass + " passed, " + fail + " failed =====");
        System.exit(fail == 0 ? 0 : 1);
    }
}
