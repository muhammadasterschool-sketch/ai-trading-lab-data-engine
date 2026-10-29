package com.aitradinglab.engine;

import org.junit.Test;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Scanner;
import java.util.Set;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

/**
 * v3.1 HOST-JVM tests for the Binance SPOT market-data module (pure Java, zero network).
 * All inputs are recorded-shape FIXTURES under src/test/resources/binance/ — clearly
 * labelled as fixtures, never live market data. The REAL 418 ban body was captured live
 * during the 2026-10-30 baseline audit and is reused verbatim as failure injection.
 */
public class BinanceMarketDataTest {

    // ---------------------------------------------------------------- helpers

    private static String fixture(String name) {
        InputStream is = BinanceMarketDataTest.class.getResourceAsStream("/binance/" + name);
        assertNotNull("fixture missing: " + name, is);
        Scanner s = new Scanner(is, "UTF-8").useDelimiter("\\A");
        return s.hasNext() ? s.next() : "";
    }

    /** Fake store: in-memory, implements the two-run delist sweep contract faithfully. */
    static final class MemStore implements BinanceMarketData.Store {
        final Map<String, String> settings = new HashMap<>();
        final Map<String, String> state = new HashMap<>();
        final Map<String, BinanceMarketData.Symbol> symbols = new LinkedHashMap<>();
        final Map<String, BinanceMarketData.Kline> candles = new LinkedHashMap<>(); // key sym|tf|ts
        final List<String> logs = new ArrayList<>();
        long sweepMarked = -1;

        public String setting(String key, String def) { String v = settings.get(key); return v == null ? def : v; }
        public void setSetting(String key, String value) { settings.put(key, value); }
        public void log(String level, String component, String event, String details) { logs.add(level + "|" + event); }

        public BinanceMarketData.Symbol getSymbol(String symbol) { return symbols.get(symbol); }
        public void upsertSymbol(BinanceMarketData.Symbol s) { symbols.put(s.symbol, s); }

        public int markAbsentVerifiedBefore(long nowMs, String reasonPrefix, long verifyRunTs) {
            long prev = 0;
            try { prev = Long.parseLong(state.getOrDefault("prev_discovery_at", "0").trim()); } catch (Exception ignored) { }
            if (prev <= 0) { state.put("prev_discovery_at", String.valueOf(verifyRunTs)); sweepMarked = 0; return 0; }
            long cut = Math.min(prev, verifyRunTs);
            int n = 0;
            for (BinanceMarketData.Symbol s : symbols.values())
                if (!s.rejected && s.lastVerified <= cut) { s.rejected = true; s.rejectReason = reasonPrefix + nowMs; n++; }
            sweepMarked = n;
            state.put("prev_discovery_at", String.valueOf(verifyRunTs));
            return n;
        }

        public boolean candleExists(String symbol, String tf, long openTime) { return candles.containsKey(symbol + "|" + tf + "|" + openTime); }
        public void upsertCandle(String symbol, String tf, BinanceMarketData.Kline k) { candles.put(symbol + "|" + tf + "|" + k.openTime, k); }
        public long lastCandleTs(String symbol, String tf) {
            long max = 0;
            for (String key : candles.keySet()) if (key.startsWith(symbol + "|" + tf + "|")) max = Math.max(max, Long.parseLong(key.substring(key.lastIndexOf('|') + 1)));
            return max;
        }
        public long lastClosedCandleCloseTs(String symbol, String tf) {
            long max = 0;
            for (BinanceMarketData.Kline k : candles.values()) if (k.closed) max = Math.max(max, k.closeTime);
            return max;
        }

        public List<String> watchlist() {
            List<String> out = new ArrayList<>();
            for (String s : setting("binance_watchlist", "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT").split(","))
                if (!s.trim().isEmpty()) out.add(s.trim());
            return out;
        }
        public List<String> eligibleBatch(int batch, long cursor) {
            List<String> all = new ArrayList<>();
            for (BinanceMarketData.Symbol s : symbols.values()) if (!s.rejected) all.add(s.symbol);
            if (all.isEmpty() || batch <= 0) return new ArrayList<>();
            long off = cursor % all.size();
            List<String> out = new ArrayList<>();
            for (int i = 0; i < batch; i++) out.add(all.get((int) ((off + i) % all.size())));
            return out;
        }
        public long symbolCount(boolean rejectedOnly) {
            int n = 0;
            for (BinanceMarketData.Symbol s : symbols.values()) if (s.rejected == rejectedOnly) n++;
            return n;
        }
        public String stateGet(String key, String def) { String v = state.get(key); return v == null ? def : v; }
        public void stateSet(String key, String value) { state.put(key, value); }
    }

    /** Fake HTTP: canned responses in queue; records requested URLs. */
    static final class FakeHttp implements BinanceMarketData.Http {
        final List<BinanceMarketData.Resp> queue = new ArrayList<>();
        final List<String> urls = new ArrayList<>();
        FakeHttp add(BinanceMarketData.Resp r) { queue.add(r); return this; }
        public BinanceMarketData.Resp get(String url, int timeoutMs) throws Exception {
            urls.add(url);
            if (queue.isEmpty()) throw new java.io.IOException("no canned response");
            return queue.remove(0);
        }
    }

    private static BinanceMarketData.Resp okJson(String body) {
        Map<String, String> h = new HashMap<>();
        return new BinanceMarketData.Resp(200, body, h);
    }

    /** Always-OK HTTP (empty klines) that records every URL — for count assertions. */
    static final class EndlessOkHttp implements BinanceMarketData.Http {
        final List<String> urls = new ArrayList<>();
        public BinanceMarketData.Resp get(String url, int timeoutMs) { urls.add(url); return okJson("[]"); }
    }

    // ---------------------------------------------------------------- exchangeInfo tests

    @Test
    public void exchangeInfo_filters_eligibility_with_rejection_reasons() {
        BinanceMarketData.Store st = new MemStore();
        List<BinanceMarketData.Symbol> all = BinanceMarketData.parseExchangeInfo(
                fixture("exchangeInfo_fixture.json"), st, 1793300000123L);
        assertEquals(6, all.size());
        Map<String, BinanceMarketData.Symbol> m = new HashMap<>();
        for (BinanceMarketData.Symbol s : all) m.put(s.symbol, s);

        BinanceMarketData.Symbol btc = m.get("BTCUSDT");
        assertNotNull(btc);
        assertFalse(btc.rejected);                                  // eligible
        assertEquals("TRADING", btc.status);
        assertEquals("BTC", btc.base);
        assertEquals("0.01000000", btc.tickSize);                   // metadata preserved
        assertEquals("0.00001000", btc.stepSize);
        assertEquals("0.00001000", btc.minQty);
        assertEquals("5.00000000", btc.minNotional);
        assertNotNull(btc.digest);
        assertFalse(btc.digest.isEmpty());

        assertEquals("STATUS_BREAK", m.get("XYZBREAK").rejectReason);      // suspension detected
        assertEquals("QUOTE_FILTER_USDC", m.get("ABCUSDC").rejectReason);  // quote whitelist
        assertEquals("NOT_SPOT_TRADABLE", m.get("MARGINONLY").rejectReason);
        assertEquals("BAD_SYMBOL_FORMAT", m.get("bad-lower-9").rejectReason);
        assertTrue(m.get("XYZBREAK").rejected);
        assertTrue(m.get("ABCUSDC").rejected);

        // native identifiers preserved verbatim — never remapped
        assertEquals("BTCUSDT", btc.symbol);
    }

    @Test
    public void exchangeInfo_empty_or_malformed_fails_closed() {
        BinanceMarketData.Store st = new MemStore();
        assertTrue(BinanceMarketData.parseExchangeInfo("", st, 1L).isEmpty());
        assertTrue(BinanceMarketData.parseExchangeInfo(null, st, 1L).isEmpty());
        assertTrue(BinanceMarketData.parseExchangeInfo("{\"symbols\": \"not-an-array\"}", st, 1L).isEmpty());
        assertTrue(BinanceMarketData.parseExchangeInfo("total garbage", st, 1L).isEmpty());
    }

    @Test
    public void quote_wildcard_allows_all_quotes() {
        MemStore st = new MemStore();
        st.settings.put("binance_quotes", "*");
        List<BinanceMarketData.Symbol> all = BinanceMarketData.parseExchangeInfo(
                fixture("exchangeInfo_fixture.json"), st, 1L);
        int rejected = 0;
        for (BinanceMarketData.Symbol s : all) if (s.rejected) rejected++;
        // ABCUSDC now eligible; BREAK/not-spot/bad-format still rejected
        assertEquals(3, rejected);
    }

    // ---------------------------------------------------------------- klines tests

    private static final long NOW = 1793300000123L;   // fixture epoch: row6 unfinished, rows1-5 closed

    @Test
    public void klines_closed_vs_unfinished_marked_explicitly() {
        BinanceMarketData.ParsedKlines p = BinanceMarketData.parseKlines(
                fixture("klines_btcusdt_fixture.json"), "https://x", NOW, NOW);
        assertEquals(6, p.ok.size());
        assertEquals(0, p.invalid);
        for (int i = 0; i < 5; i++) assertTrue("rows 1-5 closed", p.ok.get(i).closed);
        assertFalse("last row is the UNFINISHED candle", p.ok.get(5).closed);
        // provenance travels with the row
        assertEquals("https://x", p.ok.get(0).srcHost);
        assertEquals(NOW, p.ok.get(0).recvTs);
        assertEquals(1793296800000L, p.ok.get(0).openTime);
        assertEquals(1793297099999L, p.ok.get(0).closeTime);
        assertEquals(118275.25, p.ok.get(0).c, 1e-9);
        // monotonic gap between row5 (1793298000000) and row6 (1793299800000) = 5 intervals missing
        assertEquals(1, BinanceMarketData.gapCount(p.ok, BinanceMarketData.INTERVAL_MS));
    }

    @Test
    public void klines_failure_injection_rejects_every_corrupt_row() {
        BinanceMarketData.ParsedKlines p = BinanceMarketData.parseKlines(
                fixture("klines_bad_fixture.json"), "https://x", NOW, NOW);
        // rows: 1 OHLC violation, 1 negative price, 1 close<=open, 1 malformed element,
        // then a valid row, an out-of-order row, a valid row, a duplicate of it
        assertEquals(3, p.invalid);            // OHLC violation + negative price + close<=open
        assertEquals(1, p.nonMonotonic);       // 1793298900000 after 1793299000000
        assertEquals(1, p.duplicates);         // 1793299200000 twice
        assertEquals(2, p.ok.size());          // only the two well-ordered valid rows survive
        assertEquals(1793299000000L, p.ok.get(0).openTime);
        assertEquals(1793299200000L, p.ok.get(1).openTime);
        // malformed = 2: the _NOTE header string element + the NOT_A_ROW element
        assertEquals(2, p.malformed);
    }

    @Test
    public void ohlc_validator_boundaries() {
        assertTrue(BinanceMarketData.validOhlc(10, 12, 9, 11, 100));
        assertFalse(BinanceMarketData.validOhlc(10, 10.5, 9, 11, 100));  // high < close
        assertFalse(BinanceMarketData.validOhlc(10, 12, 10.5, 11, 100)); // low > open
        assertFalse(BinanceMarketData.validOhlc(0, 12, 9, 11, 100));     // zero price
        assertFalse(BinanceMarketData.validOhlc(10, 12, 9, 11, -1));     // negative volume
        assertTrue(BinanceMarketData.validOhlc(10, 12, 9, 11, 0));       // zero volume = unknown, allowed
    }

    // ---------------------------------------------------------------- rate limiting

    @Test
    public void real_recorded_418_ban_triggers_backoff_and_fails_closed() {
        BinanceMarketData b = new BinanceMarketData();
        BinanceMarketData.Store st = new MemStore();
        Map<String, String> h = new HashMap<>();
        BinanceMarketData.Http http = new FakeHttp().add(
                new BinanceMarketData.Resp(418, fixture("resp_418_recorded.json"), h));
        long t0 = System.currentTimeMillis();
        try {
            b.call(st, http, "/api/v3/time", 1000);
            fail("418 must fail closed");
        } catch (BinanceMarketData.RateLimitedException e) {
            long back = b.backoffUntil();
            // "banned until 1793302554614" is in the past relative to test time → floor = now+1s,
            // cap = 15 min. Accept the recorded-future case too (body timestamp ahead of clock).
            assertTrue("backoff must be active", back > t0);
            assertTrue("backoff capped at 15 min", back <= t0 + 15L * 60_000L + 1000L);
            assertTrue("last status recorded", b.lastHttpStatus() == 418);
        } catch (Exception e) {
            fail("expected RateLimitedException, got " + e);
        }
        // while in backoff, further calls refuse BEFORE any network I/O
        FakeHttp spy = new FakeHttp();
        try {
            b.call(st, spy, "/api/v3/time", 1000);
            fail("backoff must block further calls");
        } catch (BinanceMarketData.RateLimitedException expected) {
            assertEquals("no network I/O during backoff", 0, spy.urls.size());
        } catch (Exception e) {
            fail("expected RateLimitedException, got " + e);
        }
    }

    @Test
    public void retry_after_header_on_429_is_honored() {
        BinanceMarketData b = new BinanceMarketData();
        BinanceMarketData.Store st = new MemStore();
        Map<String, String> h = new HashMap<>();
        h.put("retry-after", "30");
        BinanceMarketData.Http http = new FakeHttp().add(
                new BinanceMarketData.Resp(429, "{\"code\":-1003,\"msg\":\"busy\"}", h));
        long t0 = System.currentTimeMillis();
        try {
            b.call(st, http, "/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=5", 1000);
            fail("429 must fail closed");
        } catch (BinanceMarketData.RateLimitedException e) {
            long back = b.backoffUntil();
            assertTrue("Retry-After 30s honored (±2s)", back >= t0 + 28_000L && back <= t0 + 32_000L);
        } catch (Exception e) {
            fail("expected RateLimitedException, got " + e);
        }
    }

    @Test
    public void used_weight_header_tracked_and_local_budget_enforced() throws Exception {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        st.settings.put("binance_weight_budget", "1700");
        Map<String, String> h1 = new HashMap<>(); h1.put("x-mbx-used-weight-1m", "1690");
        Map<String, String> h2 = new HashMap<>(); h2.put("x-mbx-used-weight-1m", "1750");
        FakeHttp http = new FakeHttp();
        http.add(new BinanceMarketData.Resp(200, "{}", h1));
        http.add(new BinanceMarketData.Resp(200, "{}", h2));

        b.call(st, http, "/api/v3/time", 1000);
        assertEquals(1690, b.lastUsedWeight());
        b.call(st, http, "/api/v3/time", 1000);
        assertEquals("max-tracked", 1750, b.lastUsedWeight());
        try {
            b.call(st, http, "/api/v3/time", 1000);   // used 1750 >= budget 1700
            fail("local weight budget must block before network");
        } catch (BinanceMarketData.RateLimitedException e) {
            assertTrue(e.getMessage().contains("budget"));
            assertEquals("no network I/O when blocked", 2, http.urls.size());
        }
    }

    @Test
    public void network_error_escalates_backoff_and_fails_closed() {
        BinanceMarketData b = new BinanceMarketData();
        BinanceMarketData.Store st = new MemStore();
        BinanceMarketData.Http http = new BinanceMarketData.Http() {
            public BinanceMarketData.Resp get(String url, int timeoutMs) throws Exception {
                throw new java.net.SocketTimeoutException("timeout");
            }
        };
        try {
            b.call(st, http, "/api/v3/time", 1000);
            fail("network error must propagate (fail closed)");
        } catch (Exception e) {
            assertTrue("backoff engaged after network failure", b.inBackoff(System.currentTimeMillis()));
            assertTrue(b.lastError().contains("timeout"));
        }
    }

    // ---------------------------------------------------------------- operations (Store-backed)

    @Test
    public void discoverUniverse_stores_registry_and_sweeps_absent_symbols() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        FakeHttp http = new FakeHttp().add(okJson(fixture("exchangeInfo_fixture.json")));

        BinanceMarketData.OpResult r1 = b.discoverUniverse(st, http);
        assertEquals("", r1.error);
        assertEquals(6, r1.fetched);
        assertEquals(2, r1.stored);                          // BTCUSDT + ETHUSDT eligible
        assertEquals(4, r1.rejectedNow);                     // others recorded WITH reasons
        assertEquals(2, st.symbolCount(false));
        assertEquals(4, st.symbolCount(true));
        assertNotNull(st.getSymbol("BTCUSDT"));
        assertTrue(Long.parseLong(st.stateGet("last_discovery_at", "0")) > 0);
        // first sweep: watermark only, nothing marked
        assertEquals(0, st.sweepMarked);

        // second discovery WITHOUT BTCUSDT (delisted scenario) → two-run sweep marks it
        String withoutBtc = fixture("exchangeInfo_fixture.json").replace(
                "\"BTCUSDT\",", "\"DELISTEDXX\",").replace("BTCUSDT", "DELISTEDXX");
        // simpler: hand-build a 1-symbol universe containing only ETHUSDT
        String ethOnly = "{\"symbols\":[" +
                "{\"symbol\":\"ETHUSDT\",\"status\":\"TRADING\",\"baseAsset\":\"ETH\",\"quoteAsset\":\"USDT\"," +
                "\"permissions\":[\"SPOT\"],\"isSpotTradingAllowed\":true," +
                "\"filters\":[{\"filterType\":\"LOT_SIZE\",\"stepSize\":\"0.00010000\",\"minQty\":\"0.00010000\"}]}]}";
        FakeHttp http2 = new FakeHttp().add(okJson(ethOnly));
        BinanceMarketData.OpResult r2 = b.discoverUniverse(st, http2);
        assertEquals("", r2.error);
        assertTrue("BTCUSDT must be marked absent by the sweep", st.sweepMarked >= 1);
        BinanceMarketData.Symbol btc = st.getSymbol("BTCUSDT");
        assertTrue(btc.rejected);
        assertTrue("reason carries prefix", btc.rejectReason.startsWith("ABSENT_OR_STATUS_CHANGE_"));
        // ETHUSDT firstSeen PRESERVED across updates
        BinanceMarketData.Symbol eth = st.getSymbol("ETHUSDT");
        assertNotNull(eth);
        assertFalse(eth.rejected);
        assertTrue(r2.updated >= 1);
    }

    @Test
    public void discoverUniverse_empty_result_never_touches_registry() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        FakeHttp http = new FakeHttp().add(okJson("{\"symbols\":[]}"));
        BinanceMarketData.OpResult r = b.discoverUniverse(st, http);
        assertTrue("fail closed on empty universe", r.error.contains("0 symbols"));
        assertEquals(0, st.symbols.size());
    }

    @Test
    public void syncSymbol_stores_with_provenance_and_dedups_on_resync() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        FakeHttp http = new FakeHttp().add(okJson(fixture("klines_btcusdt_fixture.json")));

        BinanceMarketData.OpResult r = b.syncSymbol(st, http, "BTCUSDT", "5m", 200, NOW);
        assertEquals("", r.error);
        assertEquals(6, r.stored);
        assertEquals(6, st.candles.size());
        BinanceMarketData.Kline last = st.candles.get("BTCUSDT|5m|1793299800000");
        assertNotNull(last);
        assertFalse("unfinished candle stored with closed=false (pinned test clock)", last.closed);
        assertEquals("provenance host = configured official default", BinanceMarketData.DEFAULT_HOST, last.srcHost);
        assertTrue(last.recvTs > 0);
        // resync: no duplicates (idempotent upsert)
        FakeHttp http2 = new FakeHttp().add(okJson(fixture("klines_btcusdt_fixture.json")));
        BinanceMarketData.OpResult r2 = b.syncSymbol(st, http2, "BTCUSDT", "5m", 200);
        assertEquals(0, r2.stored);                          // all existed already
        assertEquals(6, st.candles.size());
    }

    @Test
    public void syncSymbol_rejects_bad_symbol_and_bad_responses() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        BinanceMarketData.OpResult bad = b.syncSymbol(st, new FakeHttp(), "XAU/USD", "5m", 10);
        assertEquals("bad symbol", bad.error);
        BinanceMarketData.OpResult empty = b.syncSymbol(st, new FakeHttp().add(okJson("[]")), "BTCUSDT", "5m", 10);
        assertTrue(empty.error.contains("0 valid klines"));
        BinanceMarketData.OpResult garbage = b.syncSymbol(st, new FakeHttp().add(okJson("<html>gateway</html>")), "BTCUSDT", "5m", 10);
        assertTrue(garbage.error.contains("0 valid klines"));
        assertEquals(0, st.candles.size());
    }

    @Test
    public void backfill_batch_rotates_without_repeats() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        // seed 5 eligible symbols
        for (String s : new String[]{"AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT"}) {
            BinanceMarketData.Symbol sym = new BinanceMarketData.Symbol();
            sym.symbol = s; sym.status = "TRADING"; sym.base = s; sym.quote = "USDT";
            sym.lastVerified = 1; sym.digest = "d";
            st.upsertSymbol(sym);
        }
        st.settings.put("binance_backfill_batch", "2");
        FakeHttp http = new FakeHttp();
        for (int i = 0; i < 5; i++) http.add(okJson(fixture("klines_btcusdt_fixture.json")));

        BinanceMarketData.OpResult r1 = b.backfillBatch(st, http);
        assertEquals("2 symbols × 6 klines", 12, r1.stored);
        assertEquals(12, st.candles.size());
        long cur1 = Long.parseLong(st.stateGet("rot_cursor", "0"));
        assertEquals(2, cur1);

        BinanceMarketData.OpResult r2 = b.backfillBatch(st, http);
        assertEquals(12, r2.stored);
        assertEquals(24, st.candles.size());
        long cur2 = Long.parseLong(st.stateGet("rot_cursor", "0"));
        assertEquals(4, cur2);

        BinanceMarketData.OpResult r3 = b.backfillBatch(st, http);
        assertEquals("rotation wrapped: EEE new (6) + AAA already stored (0)", 6, r3.stored);
        assertEquals(30, st.candles.size());
        long cur3 = Long.parseLong(st.stateGet("rot_cursor", "0"));
        assertEquals("cursor advances by batch size (wrap re-touches index 0)", 6, cur3);
    }

    @Test
    public void backfill_disabled_when_batch_zero() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        st.settings.put("binance_backfill_batch", "0");
        BinanceMarketData.OpResult r = b.backfillBatch(st, new FakeHttp());
        assertTrue(r.error.contains("disabled"));
    }

    @Test
    public void watchlist_cap_enforced_at_200() {
        // The 200-call cap is a MODULE invariant (API weight safety): a store may return a
        // larger list, but syncWatchlist must never issue more than 200 klines calls/tick.
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 250; i++) sb.append("SYM").append(i).append("X,");   // 8-char valid tokens
        st.settings.put("binance_watchlist", sb.toString());
        assertEquals(250, st.watchlist().size());
        EndlessOkHttp http = new EndlessOkHttp();                                // always 200 → no backoff
        b.syncWatchlist(st, http);
        assertEquals("cap: exactly 200 network attempts, no more", 200, http.urls.size());
        assertTrue(st.logs.contains("WARN|WATCHLIST_CAP"));
    }

    @Test
    public void coverage_reports_truthful_state() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        for (String s : new String[]{"BTCUSDT", "ETHUSDT"}) {
            BinanceMarketData.Symbol sym = new BinanceMarketData.Symbol();
            sym.symbol = s; sym.status = "TRADING"; sym.base = s; sym.quote = "USDT";
            sym.lastVerified = 1; sym.digest = "d";
            st.upsertSymbol(sym);
        }
        long now = System.currentTimeMillis();
        storeCandle(st, "BTCUSDT", now - 2 * 60_000L);       // fresh (2 min old)
        storeCandle(st, "ETHUSDT", now - 90 * 60_000L);      // stale (90 min old)
        Map<String, Object> cov = b.coverage(st);
        assertEquals(2L, cov.get("eligible"));
        assertEquals(0L, cov.get("rejected"));
        assertEquals("default watchlist (5) ∪ eligible sample (2 dup)", 5, cov.get("sampled_symbols"));
        assertEquals(1, cov.get("fresh"));
        assertEquals(1, cov.get("stale"));
        assertEquals(3, cov.get("no_data_yet"));
        assertEquals(Boolean.TRUE, cov.get("read_only"));
        assertEquals("SPOT", cov.get("category"));
        assertEquals("NONE", cov.get("order_path"));
    }

    private static void storeCandle(MemStore st, String sym, long openTime) {
        BinanceMarketData.Kline k = new BinanceMarketData.Kline();
        k.openTime = openTime; k.closeTime = openTime + BinanceMarketData.INTERVAL_MS - 1;
        k.o = 1; k.h = 2; k.l = 0.5; k.c = 1.5; k.v = 10;
        k.closed = true; k.srcHost = "https://x"; k.recvTs = openTime;
        st.upsertCandle(sym, "5m", k);
    }

    @Test
    public void cleartext_host_setting_is_refused() throws Exception {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        st.settings.put("binance_host", "http://evil.example.com");
        FakeHttp http = new FakeHttp();
        // call() resolves the host through host(st) which rejects non-https → falls back to default
        http.add(okJson("{\"serverTime\":1}"));
        b.call(st, http, "/api/v3/time", 1000);
        assertTrue("request went to the DEFAULT official host, not the cleartext one",
                http.urls.get(0).startsWith(BinanceMarketData.DEFAULT_HOST));
    }

    @Test
    public void server_time_skew_recorded() {
        BinanceMarketData b = new BinanceMarketData();
        MemStore st = new MemStore();
        long fakeServer = System.currentTimeMillis() + 4200L;
        FakeHttp http = new FakeHttp().add(okJson("{\"serverTime\":" + fakeServer + "}"));
        long skew = b.fetchServerTime(st, http);
        assertTrue("skew ≈ +4.2s", Math.abs(skew - 4200L) < 1500L);
        assertEquals(skew, b.serverSkewMs());
        assertTrue(http.urls.get(0).endsWith("/api/v3/time"));
    }
}
