package com.aitradinglab.engine;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * v3.1 BINANCE MARKET-DATA MODULE (master prompt Phase 2) — first genuine non-Yahoo provider.
 *
 * Scope: Binance SPOT public market data ONLY (read-only). No trading endpoints are
 * referenced by this class; there is no createOrder/order path here by construction.
 *
 * Design rules (per master engineering prompt):
 *  - Fail closed: malformed / stale / rate-limited responses never fabricate data.
 *  - Provenance: every stored candle carries source host, source open-time and receipt time.
 *  - Closed vs unfinished candles are explicitly marked (closed flag), never mixed silently.
 *  - Rate-limit aware: tracks X-MBX-USED-WEIGHT-1M, honours Retry-After / "IP banned until",
 *    keeps a conservative local weight budget, backs off exponentially on 429/418/5xx.
 *  - Tiered scheduling: watchlist sync + small rotating backfill batches; never "all symbols
 *    at high frequency".
 *  - Pure Java (no android.* imports) so the parsing/validation logic is host-JVM testable
 *    the same way HttpServerLoopbackTest is.
 *
 * Endpoint: official Binance public market-data host. Default
 * https://data-api.binance.vision (Binance's official market-data-only domain, same
 * /api/v3 REST contract, no API key). Setting binance_host may point to
 * https://api.binance.com. Market category: SPOT only.
 */
public final class BinanceMarketData {

    public static final String DEFAULT_HOST = "https://data-api.binance.vision";
    public static final String UA = "Mozilla/5.0 (Android) AI-Trading-Lab/3.1 (paper-research; read-only)";
    public static final String TF = "5m";                       // same timeframe as the 3C engine
    public static final long INTERVAL_MS = 5L * 60_000L;

    // ------------------------------------------------------------------ data types

    /** Discovered instrument (Binance native identifier preserved verbatim). */
    public static final class Symbol {
        public String symbol;          // native Binance symbol, e.g. BTCUSDT (never remapped)
        public String base, quote;
        public String status;          // TRADING / BREAK / HALT / etc. (exchange metadata)
        public String tickSize, stepSize, minQty, minNotional;   // raw filter strings (metadata only)
        public boolean spotAllowed;
        public long firstSeen, lastVerified;
        public boolean rejected;
        public String rejectReason;    // "" when eligible
        public String digest;          // sha256 of the metadata that matters
    }

    /** One kline observation. closed=true when closeTime < evaluation time. */
    public static final class Kline {
        public long openTime, closeTime;
        public double o, h, l, c, v;
        public boolean closed;
        public String srcHost;         // provenance: which official host served it
        public long recvTs;            // provenance: receipt time (device clock, skew-documented)
    }

    /** Minimal HTTP abstraction so tests inject fixtures and never touch the network. */
    public interface Http {
        Resp get(String url, int timeoutMs) throws Exception;
    }

    /** Response wrapper: status code, selected headers, body. */
    public static final class Resp {
        public final int code;
        public final String body;
        private final Map<String, String> headers;
        public Resp(int code, String body, Map<String, String> headers) {
            this.code = code; this.body = body; this.headers = headers == null ? new LinkedHashMap<String, String>() : headers;
        }
        public String header(String name) { String v = headers.get(name.toLowerCase(Locale.US)); return v == null ? "" : v; }
    }

    /** Default HTTP implementation (real network, read-only GETs). */
    public static final class HttpUrl implements Http {
        @Override public Resp get(String url, int timeoutMs) throws Exception {
            HttpURLConnection cn = (HttpURLConnection) new URL(url).openConnection();
            cn.setConnectTimeout(timeoutMs);
            cn.setReadTimeout(timeoutMs + 5000);
            cn.setRequestProperty("User-Agent", UA);
            cn.setRequestProperty("Accept", "application/json");
            int code = cn.getResponseCode();
            Map<String, String> h = new LinkedHashMap<String, String>();
            for (Map.Entry<String, List<String>> e : cn.getHeaderFields().entrySet()) {
                if (e.getKey() == null || e.getValue() == null || e.getValue().isEmpty()) continue;
                h.put(e.getKey().toLowerCase(Locale.US), e.getValue().get(0));
            }
            java.io.InputStream is = code >= 400 ? cn.getErrorStream() : cn.getInputStream();
            String body = "";
            if (is != null) {
                BufferedReader r = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
                r.close();
                body = sb.toString();
            }
            try { cn.disconnect(); } catch (Throwable ignored) { }
            return new Resp(code, body, h);
        }
    }

    /**
     * Storage boundary. Implemented over SQLite by EngineCore (production) and by an
     * in-memory fake in unit tests. The engine never writes Binance rows outside this
     * boundary, and Binance rows never enter the 3C strategy tables (no substitution).
     */
    public interface Store {
        String setting(String key, String def);
        void setSetting(String key, String value);
        void log(String level, String component, String event, String details);

        /** existing symbol or null */
        Symbol getSymbol(String symbol);
        void upsertSymbol(Symbol s);
        /** mark symbols that vanished from exchangeInfo or changed status */
        int markAbsentVerifiedBefore(long nowMs, String reasonPrefix, long verifyRunTs);

        boolean candleExists(String symbol, String tf, long openTime);
        void upsertCandle(String symbol, String tf, Kline k);
        long lastCandleTs(String symbol, String tf);
        long lastClosedCandleCloseTs(String symbol, String tf);

        List<String> watchlist();
        /** rotation source: eligible, non-watchlist symbols, batch starting at cursor */
        List<String> eligibleBatch(int batch, long cursor);
        long symbolCount(boolean rejectedOnly);

        String stateGet(String key, String def);
        void stateSet(String key, String value);
    }

    // ------------------------------------------------------------------ state (per engine instance)

    private long backoffUntilMs = 0L;          // global provider backoff (429/418/5xx)
    private long lastUsedWeight = -1L;         // X-MBX-USED-WEIGHT-1M last reported
    private int lastHttpStatus = 0;
    private String lastError = "";
    private long serverSkewMs = Long.MIN_VALUE; // serverTime - deviceTime (clock-skew check)

    public long backoffUntil() { return backoffUntilMs; }
    public long lastUsedWeight() { return lastUsedWeight; }
    public int lastHttpStatus() { return lastHttpStatus; }
    public String lastError() { return lastError; }
    public long serverSkewMs() { return serverSkewMs; }

    public boolean inBackoff(long nowMs) { return nowMs < backoffUntilMs; }

    private String host(Store st) {
        String h = st.setting("binance_host", DEFAULT_HOST).trim();
        if (!h.startsWith("https://")) return DEFAULT_HOST;    // cleartext hosts rejected (fail closed)
        return h;
    }

    // ------------------------------------------------------------------ parsing (pure, unit-tested)

    /** Eligibility rules (explicitly configured, never hardcoded as a coin list). */
    public static String quoteWhitelist(Store st) {
        return st.setting("binance_quotes", "USDT").trim().toUpperCase(Locale.US);
    }
    private static boolean quoteAllowed(Store st, String quote) {
        String wl = quoteWhitelist(st);
        if (wl.isEmpty() || "*".equals(wl)) return true;
        for (String q : wl.split(",")) if (quote.equalsIgnoreCase(q.trim())) return true;
        return false;
    }

    private static String digestOf(Symbol s) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            String payload = s.symbol + "|" + s.status + "|" + s.base + "|" + s.quote + "|" + s.tickSize
                    + "|" + s.stepSize + "|" + s.minQty + "|" + s.minNotional + "|" + s.spotAllowed;
            byte[] d = md.digest(payload.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : d) sb.append(String.format(Locale.US, "%02x", b));
            return sb.substring(0, 32);
        } catch (Exception e) { return ""; }
    }

    /**
     * Parse /api/v3/exchangeInfo (permissions=SPOT). Returns eligible symbols; rejected
     * instruments are ALSO returned with rejected=true + reason so the registry can report
     * them truthfully (master prompt 5.1/5.2: rejection reasons, no silent drops).
     */
    public static List<Symbol> parseExchangeInfo(String json, Store st, long nowMs) {
        List<Symbol> out = new ArrayList<Symbol>();
        if (json == null || json.isEmpty()) return out;
        JSONArray arr;
        try { arr = new JSONObject(json).getJSONArray("symbols"); } catch (Exception e) { return out; }
        for (int i = 0; i < arr.length(); i++) {
            JSONObject o = arr.optJSONObject(i);
            if (o == null) continue;                                     // malformed element skipped + counted by caller
            Symbol s = new Symbol();
            s.symbol = o.optString("symbol", "");
            s.base = o.optString("baseAsset", "");
            s.quote = o.optString("quoteAsset", "");
            s.status = o.optString("status", "UNKNOWN");
            s.spotAllowed = o.optBoolean("isSpotTradingAllowed", false);
            if (s.symbol.isEmpty() || s.base.isEmpty()) { s.rejected = true; s.rejectReason = "MALFORMED_METADATA"; }
            else if (!"TRADING".equals(s.status)) { s.rejected = true; s.rejectReason = "STATUS_" + s.status; }
            else if (!s.spotAllowed) { s.rejected = true; s.rejectReason = "NOT_SPOT_TRADABLE"; }
            else if (!s.symbol.matches("[A-Z0-9]{5,20}")) { s.rejected = true; s.rejectReason = "BAD_SYMBOL_FORMAT"; }
            else if (!quoteAllowed(st, s.quote)) { s.rejected = true; s.rejectReason = "QUOTE_FILTER_" + s.quote; }
            // filters (metadata only — tick/step/min used later for display and future risk checks)
            JSONArray fl = o.optJSONArray("filters");
            if (fl != null) {
                for (int j = 0; j < fl.length(); j++) {
                    JSONObject f = fl.optJSONObject(j);
                    if (f == null) continue;
                    String t = f.optString("filterType", "");
                    if ("PRICE_FILTER".equals(t)) s.tickSize = f.optString("tickSize", "");
                    else if ("LOT_SIZE".equals(t)) { s.stepSize = f.optString("stepSize", ""); s.minQty = f.optString("minQty", ""); }
                    else if ("NOTIONAL".equals(t)) s.minNotional = f.optString("minNotional", "");
                    else if ("MARKET_LOT_SIZE".equals(t)) { if (s.minQty == null || s.minQty.isEmpty()) s.minQty = f.optString("minQty", ""); }
                }
            }
            if (s.tickSize == null) s.tickSize = "";
            if (s.stepSize == null) s.stepSize = "";
            if (s.minQty == null) s.minQty = "";
            if (s.minNotional == null) s.minNotional = "";
            s.firstSeen = nowMs;
            s.lastVerified = nowMs;
            s.digest = digestOf(s);
            out.add(s);
        }
        return out;
    }

    /** OHLC sanity: positive prices, h >= max(o,c), l <= min(o,c), v >= 0. */
    public static boolean validOhlc(double o, double h, double l, double c, double v) {
        return o > 0 && h > 0 && l > 0 && c > 0 && v >= 0
                && h >= Math.max(o, c) && l <= Math.min(o, c) && h >= l;
    }

    public static final class ParsedKlines {
        public final List<Kline> ok = new ArrayList<Kline>();
        public int invalid, duplicates, nonMonotonic, malformed;
    }

    /**
     * Parse /api/v3/klines rows:
     * [openTime, open, high, low, close, volume, closeTime, ...]
     * Rows are ascending by openTime from Binance; we still validate monotonicity and
     * de-duplicate defensively. closed = closeTime < nowMs (explicit marking).
     */
    public static ParsedKlines parseKlines(String json, String host, long nowMs, long recvTs) {
        ParsedKlines p = new ParsedKlines();
        if (json == null || json.isEmpty()) return p;
        JSONArray arr;
        try { arr = new JSONArray(json); } catch (Exception e) { p.malformed++; return p; }
        long prevOpen = Long.MIN_VALUE;
        for (int i = 0; i < arr.length(); i++) {
            JSONArray row = arr.optJSONArray(i);
            if (row == null || row.length() < 7) { p.malformed++; continue; }
            try {
                long open = row.getLong(0), close = row.getLong(6);
                double o = row.getDouble(1), h = row.getDouble(2), l = row.getDouble(3),
                        c = row.getDouble(4), v = row.getDouble(5);
                if (open <= 0 || close <= open) { p.invalid++; continue; }
                if (!validOhlc(o, h, l, c, v)) { p.invalid++; continue; }
                if (open < prevOpen) { p.nonMonotonic++; continue; }        // out-of-order rejected, fail closed
                if (prevOpen == open) { p.duplicates++; continue; }         // duplicate rejected
                prevOpen = open;
                Kline k = new Kline();
                k.openTime = open; k.closeTime = close;
                k.o = o; k.h = h; k.l = l; k.c = c; k.v = v;
                k.closed = close < nowMs;                                   // explicit closed/unfinished marking
                k.srcHost = host; k.recvTs = recvTs;
                p.ok.add(k);
            } catch (Exception e) { p.malformed++; }
        }
        return p;
    }

    /** Detect missing intervals in an ascending list of klines. */
    public static int gapCount(List<Kline> asc, long intervalMs) {
        int gaps = 0;
        for (int i = 1; i < asc.size(); i++)
            if (asc.get(i).openTime - asc.get(i - 1).openTime > intervalMs) gaps++;
        return gaps;
    }

    // ------------------------------------------------------------------ low-level call + rate limits

    /** Thrown when the provider is rate-limited/banned — callers must fail closed. */
    public static final class RateLimitedException extends Exception {
        public RateLimitedException(String msg) { super(msg); }
    }

    /** One GET against the configured official host with weight/backoff handling. */
    public Resp call(Store st, Http http, String pathAndQuery, int timeoutMs) throws Exception {
        long now = System.currentTimeMillis();
        if (now < backoffUntilMs) {
            lastError = "BACKOFF_UNTIL_" + backoffUntilMs;
            throw new RateLimitedException("provider backoff active until " + backoffUntilMs);
        }
        long budget = parseLong(st.setting("binance_weight_budget", "1800"), 1800);
        if (lastUsedWeight >= 0 && lastUsedWeight >= budget) {
            backoffUntilMs = now + 30_000L;                          // local budget guard: 30s pause
            st.log("WARN", "BINANCE", "RATE_LIMIT_LOCAL",
                    "used-weight " + lastUsedWeight + " >= local budget " + budget + " (of exchange 6000/min)");
            throw new RateLimitedException("local weight budget reached: " + lastUsedWeight);
        }
        String url = host(st) + pathAndQuery;
        Resp r;
        try {
            r = http.get(url, timeoutMs);
        } catch (Exception e) {
            lastHttpStatus = 0;
            lastError = String.valueOf(e);
            escalateBackoff(now, 60_000L);
            throw e;                                                  // fail closed: caller skips this tick
        }
        lastHttpStatus = r.code;
        String w = r.header("X-MBX-USED-WEIGHT-1M");
        if (!w.isEmpty()) { try { lastUsedWeight = Math.max(lastUsedWeight, Long.parseLong(w.trim())); } catch (Exception ignored) { } }
        if (r.code == 429 || r.code == 418) {
            long until = backoffFrom(r, now);
            backoffUntilMs = until;
            lastError = "HTTP_" + r.code + " backoff until " + until;
            st.log("WARN", "BINANCE", "RATE_LIMIT_REMOTE", "HTTP " + r.code + " — backing off until " + until + " (body: " + snap(r.body, 160) + ")");
            throw new RateLimitedException("HTTP " + r.code + " backoff until " + until);
        }
        if (r.code != 200) {
            lastError = "HTTP_" + r.code;
            escalateBackoff(now, 60_000L);
            throw new java.io.IOException("HTTP " + r.code + " from " + url);
        }
        return r;
    }

    /** Parse Retry-After header or Binance "IP banned until <epoch-ms>" body (real 418 shape). */
    static long backoffFrom(Resp r, long now) {
        long cap = 15L * 60_000L;
        String ra = r.header("Retry-After");
        if (!ra.isEmpty()) { try { return now + Math.min(Long.parseLong(ra.trim()) * 1000L, cap); } catch (Exception ignored) { } }
        String b = r.body == null ? "" : r.body;
        int i = b.indexOf("banned until");
        if (i >= 0) {
            try {
                long[] digits = digitsAfter(b, i + "banned until".length());
                if (digits[0] > 0) {
                    long banMs = (digits[1] == 13) ? digits[0] : digits[0] * 1000L;   // body gives epoch-ms
                    return Math.min(Math.max(banMs, now + 1000L), now + cap);
                }
            } catch (Exception ignored) { }
        }
        return now + Math.min(60_000L, cap);
    }

    /** first number after index, with its digit count (to detect s vs ms). */
    private static long[] digitsAfter(String s, int from) {
        int i = from;
        while (i < s.length() && !Character.isDigit(s.charAt(i))) i++;
        int j = i;
        while (j < s.length() && Character.isDigit(s.charAt(j))) j++;
        if (j <= i) return new long[]{0, 0};
        try { return new long[]{Long.parseLong(s.substring(i, j)), j - i}; } catch (Exception e) { return new long[]{0, 0}; }
    }

    private void escalateBackoff(long now, long base) {
        long prev = backoffUntilMs - now;
        long next = (prev > 0) ? Math.min(prev * 2, 15L * 60_000L) : base;
        backoffUntilMs = now + next;
    }

    private static long parseLong(String s, long def) {
        try { return Long.parseLong(s.trim()); } catch (Exception e) { return def; }
    }
    private static int parseInt(String s, int def) {
        try { return Integer.parseInt(s.trim()); } catch (Exception e) { return def; }
    }
    private static String snap(String s, int n) {
        if (s == null) return "";
        return s.length() <= n ? s : s.substring(0, n);
    }

    // ------------------------------------------------------------------ operations

    public static final class OpResult {
        public int fetched, stored, updated, rejectedNow, skippedRateLimit, errors;
        public String error = "";
        public long tookMs;
        public String toString() {
            return "fetched=" + fetched + " stored=" + stored + " updated=" + updated
                    + " rejected=" + rejectedNow + " skippedRL=" + skippedRateLimit + " errors=" + errors
                    + (error.isEmpty() ? "" : " err=" + error) + " took=" + tookMs + "ms";
        }
    }

    /** GET /api/v3/time — clock-skew check (documented limitation: device clock dependent). */
    public long fetchServerTime(Store st, Http http) {
        try {
            Resp r = call(st, http, "/api/v3/time", 8000);
            long srv = new JSONObject(r.body).getLong("serverTime");
            serverSkewMs = srv - System.currentTimeMillis();
            return serverSkewMs;
        } catch (Exception e) { serverSkewMs = Long.MIN_VALUE; return Long.MIN_VALUE; }
    }

    /**
     * Phase 5.1/5.2 — full universe discovery + delisting/suspension detection.
     * First-seen preserved on update; metadata digest recorded; absent/changed symbols marked.
     */
    public OpResult discoverUniverse(Store st, Http http) {
        long t0 = System.currentTimeMillis();
        OpResult res = new OpResult();
        try {
            Resp r = call(st, http, "/api/v3/exchangeInfo?permissions=SPOT", 15000);
            long now = System.currentTimeMillis();
            List<Symbol> parsed = parseExchangeInfo(r.body, st, now);
            if (parsed.isEmpty()) {
                res.error = "exchangeInfo parsed to 0 symbols — fail closed, registry untouched";
                st.log("ERROR", "BINANCE", "DISCOVERY_EMPTY", res.error);
                return res;
            }
            int eligible = 0;
            for (Symbol s : parsed) {
                Symbol prev = st.getSymbol(s.symbol);
                if (prev != null) { s.firstSeen = prev.firstSeen; res.updated++; }
                st.upsertSymbol(s);
                if (!s.rejected) eligible++;
                else res.rejectedNow++;
            }
            // delist/suspension sweep: anything verified in an older run but absent here
            int gone = st.markAbsentVerifiedBefore(now, "ABSENT_OR_STATUS_CHANGE_", now);
            res.fetched = parsed.size();
            res.stored = eligible;
            st.stateSet("last_discovery_at", String.valueOf(now));
            st.stateSet("last_discovery_digest", "symbols=" + parsed.size() + " eligible=" + eligible + " rejected=" + res.rejectedNow + " absent_marked=" + gone);
            st.log("INFO", "BINANCE", "DISCOVERY_DONE", res.toString() + " absent=" + gone);
            st.setSetting("binance_last_sync", String.valueOf(now));
        } catch (RateLimitedException e) {
            res.skippedRateLimit = 1; res.error = String.valueOf(e.getMessage());
        } catch (Exception e) {
            res.errors++; res.error = String.valueOf(e);
            st.log("ERROR", "BINANCE", "DISCOVERY_FAIL", String.valueOf(e));
        }
        res.tookMs = System.currentTimeMillis() - t0;
        return res;
    }

    /** Phase 5.3 — klines for ONE symbol, validated + stored with provenance.
     *  nowMs is injectable so tests can pin the closed/unfinished boundary deterministically;
     *  production uses the device clock (skew vs exchange time is tracked separately). */
    public OpResult syncSymbol(Store st, Http http, String symbol, String tf, int limit) {
        return syncSymbol(st, http, symbol, tf, limit, System.currentTimeMillis());
    }

    public OpResult syncSymbol(Store st, Http http, String symbol, String tf, int limit, long nowMs) {
        long t0 = System.currentTimeMillis();
        OpResult res = new OpResult();
        if (!symbol.matches("[A-Z0-9]{5,20}")) { res.error = "bad symbol"; return res; }
        try {
            Resp r = call(st, http, "/api/v3/klines?symbol=" + symbol + "&interval=" + tf + "&limit="
                    + Math.max(1, Math.min(1000, limit)), 12000);
            long now = nowMs;
            ParsedKlines p = parseKlines(r.body, host(st), now, System.currentTimeMillis());
            res.fetched = p.ok.size() + p.invalid + p.duplicates + p.nonMonotonic + p.malformed;
            for (Kline k : p.ok) {
                if (!st.candleExists(symbol, tf, k.openTime)) res.stored++;
                st.upsertCandle(symbol, tf, k);      // closed flag + provenance columns travel with the row
            }
            if (p.ok.isEmpty()) { res.error = "0 valid klines (invalid=" + p.invalid + " dup=" + p.duplicates + " mono=" + p.nonMonotonic + " malformed=" + p.malformed + ")"; }
            st.log("INFO", "BINANCE", "KLINE_SYNC", symbol + " tf=" + tf + " ok=" + p.ok.size()
                    + " invalid=" + p.invalid + " dup=" + p.duplicates + " nonMono=" + p.nonMonotonic
                    + " malformed=" + p.malformed + " gaps=" + gapCount(p.ok, INTERVAL_MS));
        } catch (RateLimitedException e) {
            res.skippedRateLimit = 1; res.error = String.valueOf(e.getMessage());
        } catch (Exception e) {
            res.errors++; res.error = String.valueOf(e);
        }
        res.tookMs = System.currentTimeMillis() - t0;
        return res;
    }

    /** Phase 5.4 — tiered watchlist sync (hard cap 200 symbols — API weight safety). */
    public List<OpResult> syncWatchlist(Store st, Http http) {
        List<OpResult> out = new ArrayList<OpResult>();
        int limit = Math.min(200, parseInt(st.setting("binance_kline_limit", "200"), 200));
        int attempted = 0;
        for (String s : st.watchlist()) {
            if (attempted >= 200) { st.log("WARN", "BINANCE", "WATCHLIST_CAP", "watchlist capped at 200 per sync tick"); break; }
            if (inBackoff(System.currentTimeMillis())) break;            // stop the tier, keep remaining for next tick
            attempted++;
            out.add(syncSymbol(st, http, s.trim().toUpperCase(Locale.US), TF, limit));
        }
        st.stateSet("last_watchlist_sync", String.valueOf(System.currentTimeMillis()));
        return out;
    }

    /** Phase 5.4 — small rotating background batch over the eligible universe. */
    public OpResult backfillBatch(Store st, Http http) {
        long t0 = System.currentTimeMillis();
        OpResult res = new OpResult();
        int batch = Math.max(0, Math.min(20, parseInt(st.setting("binance_backfill_batch", "4"), 4)));
        if (batch == 0) { res.error = "backfill disabled (batch=0)"; return res; }
        long cursor = parseLong(st.stateGet("rot_cursor", "0"), 0L);
        int limit = Math.min(200, parseInt(st.setting("binance_kline_limit", "200"), 200));
        List<String> syms = st.eligibleBatch(batch, cursor);
        for (String s : syms) {
            if (inBackoff(System.currentTimeMillis())) { res.skippedRateLimit++; break; }
            OpResult r = syncSymbol(st, http, s, TF, limit);
            res.fetched += r.fetched; res.stored += r.stored; res.errors += r.errors;
            if (r.skippedRateLimit > 0) res.skippedRateLimit++;
            if (!r.error.isEmpty() && r.errors > 0) res.error = s + ": " + r.error;
        }
        if (!syms.isEmpty()) st.stateSet("rot_cursor", String.valueOf(cursor + syms.size()));
        res.tookMs = System.currentTimeMillis() - t0;
        return res;
    }

    /** Phase 5.4 — truthful coverage snapshot (never claims more than verified). */
    public Map<String, Object> coverage(Store st) {
        Map<String, Object> m = new LinkedHashMap<String, Object>();
        long now = System.currentTimeMillis();
        long staleAfterMin = Math.max(2, parseLong(st.setting("binance_stale_min", "30"), 30));
        m.put("eligible", st.symbolCount(false));
        m.put("rejected", st.symbolCount(true));
        m.put("host", host(st));
        m.put("category", "SPOT");
        m.put("tf", TF);
        m.put("read_only", true);
        m.put("order_path", "NONE");   // module invariant: no order endpoints exist for Binance
        m.put("last_discovery_at", parseLong(st.stateGet("last_discovery_at", "0"), 0L));
        m.put("last_watchlist_sync", parseLong(st.stateGet("last_watchlist_sync", "0"), 0L));
        m.put("last_error", lastError);
        m.put("last_http_status", lastHttpStatus);
        m.put("used_weight_1m", lastUsedWeight);
        m.put("weight_budget", parseLong(st.setting("binance_weight_budget", "1800"), 1800));
        m.put("backoff_until", backoffUntilMs);
        m.put("in_backoff", now < backoffUntilMs);
        m.put("server_skew_ms", serverSkewMs == Long.MIN_VALUE ? "UNKNOWN" : serverSkewMs);
        m.put("stale_after_min", staleAfterMin);
        // fresh vs stale across the monitored set (watchlist first, then backfilled)
        int fresh = 0, stale = 0, nodata = 0, gaps = 0;
        List<String> wl = st.watchlist();
        List<String> recent = new ArrayList<String>(wl);
        recent.addAll(st.eligibleBatch(50, 0));                          // sample of rotation head for gap stats
        java.util.Set<String> seen = new java.util.HashSet<String>();
        for (String s : recent) {
            if (!seen.add(s)) continue;
            long last = st.lastCandleTs(s, TF);
            if (last <= 0) { nodata++; continue; }
            long ageMin = (now - last) / 60000L;
            if (ageMin > staleAfterMin) stale++; else fresh++;
            if (st.lastClosedCandleCloseTs(s, TF) > 0 && (now - st.lastClosedCandleCloseTs(s, TF)) > INTERVAL_MS * 4) gaps++;
        }
        m.put("watchlist_size", wl.size());
        m.put("sampled_symbols", seen.size());
        m.put("fresh", fresh);
        m.put("stale", stale);
        m.put("no_data_yet", nodata);
        m.put("suspected_gaps", gaps);
        return m;
    }
}
