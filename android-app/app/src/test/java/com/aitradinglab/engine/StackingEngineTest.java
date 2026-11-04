package com.aitradinglab.engine;

import org.junit.Before;
import org.junit.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

/**
 * v3.2 — 12 AUTOMATED TESTS for the 1-second Setup Stacking engine.
 *
 * Sab tests controllable FAKE clock + in-memory fakes par JVM par chalte hain
 * (StackingEngine pure Java hai — koi android dependency nahi). Har test ek
 * spec rule verify karta hai:
 *
 *  1.  confirmOpensFirstPosition    — CONFIRMED → pehli position foran, state ACTIVE
 *  2.  onePositionPerTickSameSecond — isi second me do calls → sirf 1 position (idempotency)
 *  3.  stacksOnePerSecond           — 5 ticks = 5 stacks (1s cadence)
 *  4.  capPerSetup                  — cap 10 → 11th stack kabhi nahi, setup RISK_BLOCKED
 *  5.  capPerInstrument             — 2 setups same symbol → combined cap 20
 *  6.  capTotal                     — alag symbols → total cap 40
 *  7.  heatCapBlocks                — open risk heat cap se zyada → stacking stop
 *  8.  dailyLossBlocks              — din ka P/L -5% se neeche → RISK_BLOCKED
 *  9.  killSwitchBlocks             — manual kill switch → foran stop
 *  10. invalidationStopsStacking    — boundary close beyond → INVALIDATED; window end → COMPLETED
 *  11. noBackfillAfterGap           — 60s gap → miss hue ticks kabhi compensate NAHI
 *  12. restartRevalidation          — persist → recover: valid resume / invalid → INVALIDATED,
 *                                     aur same second me duplicate stack nahi
 */
public class StackingEngineTest {

    // ================== FAKE CLOCK ==================
    /** Controllable clock: monoNs scheduling ke liye, wallMs idempotency ke liye. */
    static class FakeClock implements StackingEngine.Clock {
        long wall = 1_700_000_000_000L;   // epoch ms
        long mono = 0;                    // ns
        @Override public long monoNs() { return mono; }
        @Override public long wallMs() { return wall; }
        void advanceSec(int n) { wall += n * 1000L; mono += n * 1_000_000_000L; }
    }

    // ================== FAKE STORE ==================
    static class FakeStore implements StackingEngine.Store {
        String payload = "";
        final List<String> logs = new ArrayList<>();
        @Override public void save(String payload) { this.payload = payload; }
        @Override public String load() { return payload; }
        @Override public void log(String level, String event, String details) {
            logs.add(level + ":" + event + ":" + details);
        }
        boolean hasEvent(String ev) { for (String l : logs) if (l.contains(":" + ev + ":")) return true; return false; }
    }

    // ================== FAKE RISK ==================
    /** Owner-configurable risk manager ka test double — spec defaults 10/20/40. */
    static class FakeRisk implements StackingEngine.RiskGate {
        int capSetup = 10, capInstrument = 20, capTotal = 40;
        boolean heat = false, daily = false, kill = false;
        final Map<String, Integer> openBySym = new LinkedHashMap<>();
        int openTotal = 0;

        void register(String setupId, String sym, int n) {
            openBySym.merge(sym, n, Integer::sum);
            openTotal += n;
        }

        @Override public String veto(String setupId, String sym, int setupStacks) {
            if (kill) return "KILL";
            if (setupStacks >= capSetup) return "CAP_SETUP";
            if (openBySym.getOrDefault(sym, 0) >= capInstrument) return "CAP_INSTRUMENT";
            if (openTotal >= capTotal) return "CAP_TOTAL";
            if (heat) return "HEAT";
            if (daily) return "DAILY";
            return null;
        }

        @Override public String vetoSetup(String setupId, String sym) {
            return veto(setupId, sym, 0);
        }
    }

    // ================== FAKE EXECUTOR + MARKET ==================
    static class FakeExec implements StackingEngine.TradeExecutor {
        final List<String> opens = new ArrayList<>();   // "setupId#stackNo"
        FakeRisk riskRef;                               // har khuli position risk manager me count hoti hai
        @Override public boolean open(String setupId, String sym, String side, int stackNo) {
            opens.add(setupId + "#" + stackNo);
            if (riskRef != null) riskRef.register(setupId, sym, 1);
            return true;
        }
        int count(String setupId) {
            int n = 0; for (String o : opens) if (o.startsWith(setupId + "#")) n++; return n;
        }
    }

    static class FakeMarket implements StackingEngine.MarketView {
        String reason = null;                           // null = valid
        @Override public String invalidReason(String setupId, String sym, long c3Ts, long confirmedWallMs) {
            return reason;
        }
    }

    private FakeClock clock;
    private FakeStore store;
    private FakeRisk risk;
    private FakeExec exec;
    private FakeMarket market;
    private StackingEngine engine;

    private static final String SID = "1|BTCUSDT|1000|BUY";

    @Before
    public void setUp() {
        clock = new FakeClock();
        store = new FakeStore();
        risk = new FakeRisk();
        exec = new FakeExec();
        exec.riskRef = risk;                           // executor ki positions risk manager me count
        market = new FakeMarket();
        engine = new StackingEngine(clock, store, risk, exec, market);
    }

    private void tickN(int n) {
        for (int i = 0; i < n; i++) { clock.advanceSec(1); engine.tick(); }
    }

    // 1 — CONFIRMED breakout → pehli position FORAN khulti hai, state ACTIVE
    @Test
    public void test01_confirmOpensFirstPosition() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        assertEquals(1, exec.count(SID));
        assertEquals(StackingEngine.ST_ACTIVE, engine.snapshot().get(0).state);
        assertEquals(1, engine.snapshot().get(0).stacks);
        assertEquals(1, engine.activeCount());
    }

    // 2 — isi second me repeated confirm/tick → position duplicate NAHI hoti
    @Test
    public void test02_onePositionPerTickSameSecond() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000);          // duplicate confirm — ignore
        engine.tick();                                             // wahi second (koi advance nahi)
        engine.tick();
        assertEquals(1, exec.count(SID));                          // sirf pehli position
        clock.advanceSec(1);                                       // ab agla second — ek nayi stack
        engine.tick();
        assertEquals(2, exec.count(SID));
    }

    // 3 — har tick sirf EK position: 5 seconds = 5 stacks total (1s cadence)
    @Test
    public void test03_stacksOnePerSecond() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(4);
        assertEquals(5, exec.count(SID));                          // 1 foran + 4 ticks
        StackingEngine.StackSetup s = engine.snapshot().get(0);
        assertEquals(5, s.stacks);
        assertEquals(StackingEngine.ST_ACTIVE, s.state);
    }

    // 4 — per-setup cap 10: 11th stack kabhi nahi, setup RISK_BLOCKED ho jata hai
    @Test
    public void test04_capPerSetup() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(20);                                                 // 20 ticks >> cap 10
        assertEquals(10, exec.count(SID));                         // exactly cap par ruk gaya
        StackingEngine.StackSetup s = engine.snapshot().get(0);
        assertEquals(StackingEngine.ST_RISK_BLOCKED, s.state);
        assertEquals("CAP_SETUP", s.endReason);
        assertTrue(store.hasEvent("STACK_RISK_BLOCKED"));
    }

    // 5 — per-instrument cap 20: 17 positions pehle se khuli (doosre setups) → is setup
    //     ki 3 positions (18,19,20) ke baad CAP_INSTRUMENT — setup RISK_BLOCKED
    @Test
    public void test05_capPerInstrument() {
        risk.capSetup = 100;
        risk.capInstrument = 20;
        risk.register("seed-setups", "BTCUSDT", 17);               // doosre setups ki 17 khuli positions
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        assertEquals(1, exec.count(SID));                          // 18th position — under cap
        tickN(2);
        assertEquals(3, exec.count(SID));                          // 19th + 20th
        tickN(5);
        assertEquals(3, exec.count(SID));                          // cap hit — koi nayi position nahi
        assertEquals(risk.capInstrument, risk.openBySym.get("BTCUSDT").intValue());
        assertEquals(StackingEngine.ST_RISK_BLOCKED, engine.snapshot().get(0).state);
        assertEquals("CAP_INSTRUMENT", engine.snapshot().get(0).endReason);
    }

    // 6 — total cap 40: account total bhara hua → pehli position bhi nahi khulti
    @Test
    public void test06_capTotal() {
        for (int i = 0; i < 40; i++) risk.register("seed", "ETHUSDT", 1);
        assertFalse(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));   // CAP_TOTAL — confirm hi reject
        assertEquals(StackingEngine.ST_RISK_BLOCKED, engine.snapshot().get(0).state);
        assertEquals("CAP_TOTAL", engine.snapshot().get(0).endReason);
        assertEquals(0, exec.count(SID));                          // pehli position bhi nahi khuli
    }

    // 7 — heat cap: open risk equity ka 10%+ → stacking stop (RISK_BLOCKED)
    @Test
    public void test07_heatCapBlocks() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(3);
        assertEquals(4, exec.count(SID));
        risk.heat = true;                                          // heat 10%+ hit
        tickN(1);
        StackingEngine.StackSetup s = engine.snapshot().get(0);
        assertEquals(StackingEngine.ST_RISK_BLOCKED, s.state);
        assertEquals("HEAT", s.endReason);
        assertEquals(4, exec.count(SID));                          // naya stack nahi
    }

    // 8 — daily loss limit (-5%): din ka P/L limit se neeche → naye stacks band
    @Test
    public void test08_dailyLossBlocks() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(2);
        risk.daily = true;                                         // daily -5% hit
        tickN(1);
        StackingEngine.StackSetup s = engine.snapshot().get(0);
        assertEquals(StackingEngine.ST_RISK_BLOCKED, s.state);
        assertEquals("DAILY", s.endReason);
    }

    // 9 — manual kill switch: foran sab stacking band
    @Test
    public void test09_killSwitchBlocks() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(2);
        risk.kill = true;
        tickN(1);
        assertEquals(StackingEngine.ST_RISK_BLOCKED, engine.snapshot().get(0).state);
        assertEquals("KILL", engine.snapshot().get(0).endReason);
    }

    // 10 — invalidation: boundary close beyond → INVALIDATED; window end → COMPLETED
    @Test
    public void test10_invalidationStopsStacking() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(3);
        assertEquals(4, exec.count(SID));
        market.reason = "BOUNDARY";
        tickN(1);
        StackingEngine.StackSetup s = engine.snapshot().get(0);
        assertEquals(StackingEngine.ST_INVALIDATED, s.state);
        tickN(5);
        assertEquals(4, exec.count(SID));                          // invalidation ke baad kuch nahi
        assertTrue(store.hasEvent("STACK_INVALIDATED"));
        // window end par COMPLETED (WINDOW reason)
        market.reason = null;
        String sid2 = "1|ETHUSDT|1000|BUY";
        assertTrue(engine.onConfirmed(sid2, "ETHUSDT", "BUY", 1000));
        market.reason = "WINDOW";
        tickN(1);
        assertEquals(StackingEngine.ST_COMPLETED, engine.snapshot().get(1).state);
        assertTrue(store.hasEvent("STACK_COMPLETED"));
    }

    // 11 — NO BACKFILL: 60s ka gap → sirf agla tick normal, 60 stacks ka burst KABHI nahi
    @Test
    public void test11_noBackfillAfterGap() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        assertEquals(1, exec.count(SID));
        clock.advanceSec(60);                                      // engine band tha 60s (crash/Doze)
        engine.tick();                                             // ek hi tick — catch-up NAHI
        assertEquals(2, exec.count(SID));                          // sirf 1 nayi position
        assertTrue(store.hasEvent("STACK_TICK_SKIP"));             // skipped-tick note
        tickN(3);
        assertEquals(5, exec.count(SID));                          // wapas 1s cadence
    }

    // 12 — restart recovery: persist → recover; valid setup resume, boundary-broken
    //      INVALIDATED; epoch-second idempotency restart ke baad bhi duplicate nahi
    @Test
    public void test12_restartRevalidation() {
        assertTrue(engine.onConfirmed(SID, "BTCUSDT", "BUY", 1000));
        tickN(3);                                                  // 4 stacks, ACTIVE
        String saved = store.payload;
        assertFalse(saved.isEmpty());
        assertTrue(saved.contains(SID));
        long lastSec = engine.snapshot().get(0).lastStackSec;

        // NAYA engine instance (restart) — wahi store, fresh clock (process reboot)
        FakeClock clock2 = new FakeClock();
        clock2.wall = lastSec * 1000L;                             // wahi second (idempotency test)
        StackingEngine engine2 = new StackingEngine(clock2, store, risk, exec, market);
        assertEquals(1, engine2.recover());
        assertEquals(StackingEngine.ST_ACTIVE, engine2.snapshot().get(0).state);
        assertEquals(4, engine2.snapshot().get(0).stacks);

        // recovery ke foran baad USI second me tick → duplicate stack NAHI (idempotency)
        engine2.tick();
        assertEquals(4, exec.count(SID));

        // agla second → resume normal (1s cadence)
        clock2.advanceSec(1);
        engine2.tick();
        assertEquals(5, exec.count(SID));

        // invalid setup recovery — boundary toot chuka → INVALIDATED
        // (engine2 ke legitimate tick ke baad state ab 5 stacks hai — wahi recover hoga)
        market.reason = "BOUNDARY";
        FakeStore store3 = new FakeStore();
        store3.save(store.payload);
        StackingEngine engine3 = new StackingEngine(new FakeClock(), store3, risk, exec, market);
        engine3.recover();
        assertEquals(StackingEngine.ST_INVALIDATED, engine3.snapshot().get(0).state);
        assertEquals("RECOVERY_BOUNDARY", engine3.snapshot().get(0).endReason);
        assertEquals(5, engine3.snapshot().get(0).stacks);         // latest persisted state intact
    }
}
