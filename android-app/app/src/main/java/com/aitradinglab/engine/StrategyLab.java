package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

/**
 * v1.2 STRATEGY LAB — AI strategy pipeline (owner request):
 *
 *   user text / YouTube video link
 *        -> AI compiler (web proxy, z-ai LLM) -> strategy spec JSON
 *        -> BACKTEST on real Binance 1m klines (SL 1.5xATR, TP 2.5xATR, 1% baseline)
 *        -> owner reviews results
 *        -> PAPER shadow phase (strategy trades the live paper account,
 *           tagged "AI: name", alongside the 35-strategy consensus)
 *        -> owner taps LIVE -> strategy becomes its own signal source (ACTIVE)
 *
 * YouTube channel watcher: engine polls the subscribed channel every 15 min
 * (via the web proxy /api/ai/ytlist). New videos AND live streams are
 * auto-processed into CANDIDATE strategies + status-bar notification.
 *
 * Spec schema (compiled by the web AI proxy):
 * {"name","side":"BUY|SELL|BOTH","logic":"ALL|ANY",
 *  "conditions":[{"ind":"rsi","p":14,"op":"<","v":30}, ...], "notes"}
 */
public class StrategyLab {

    /** Default AI proxy base (our web server). Override: settings key ai_base. */
    public static final String DEFAULT_AI_BASE =
            "https://preview-chat-6708bda6-7b6e-4a6f-a30c-eb65caff80bf.space-z.ai";

    private final Db db;
    private final EngineCore engine;
    private final Context ctx;

    public StrategyLab(Context ctx, Db db, EngineCore engine) {
        this.ctx = ctx.getApplicationContext();
        this.db = db;
        this.engine = engine;
    }

    // ================== AI PROXY ==================

    private String aiBase() {
        String b = db.setting("ai_base", DEFAULT_AI_BASE).trim();
        return b.endsWith("/") ? b.substring(0, b.length() - 1) : b;
    }

    /** POST JSON to the web AI proxy; returns parsed JSONObject or null. */
    private JSONObject aiPost(String path, JSONObject body, int timeoutMs) {
        try {
            HttpURLConnection cn = (HttpURLConnection) new URL(aiBase() + path).openConnection();
            cn.setRequestMethod("POST");
            cn.setConnectTimeout(timeoutMs);
            cn.setReadTimeout(timeoutMs);
            cn.setDoOutput(true);
            cn.setRequestProperty("Content-Type", "application/json");
            cn.setRequestProperty("User-Agent", "AI-Trading-Lab/1.2");
            OutputStream os = cn.getOutputStream();
            os.write(body.toString().getBytes(StandardCharsets.UTF_8));
            os.close();
            int code = cn.getResponseCode();
            BufferedReader r = new BufferedReader(new InputStreamReader(
                    code >= 400 ? cn.getErrorStream() : cn.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            if (code >= 400) {
                String msg = "{}";
                try { msg = new JSONObject(sb.toString()).optString("error", "AI error " + code); } catch (Exception ignored) { }
                lastAiError = msg;
                return null;
            }
            lastAiError = null;
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            lastAiError = "AI service unreachable: " + e.getClass().getSimpleName();
            return null;
        }
    }

    private volatile String lastAiError = null;

    // ================== ADD STRATEGIES ==================

    /** AI-compile a free-text strategy -> CANDIDATE row. Returns result JSON for the API. */
    public JSONObject addManual(String text) throws Exception {
        JSONObject spec = compileText(text);
        if (spec == null) return fail(lastAiError != null ? lastAiError : "AI compile fail — dobara try karein");
        return insert(sourceFrom(spec), spec.optString("video", "{}"), spec);
    }

    /** Compile free text via the AI proxy; returns spec JSON (with injected video meta if YT). */
    private JSONObject compileText(String text) throws Exception {
        JSONObject r = aiPost("/api/ai/strategy", new JSONObject().put("text", text), 90000);
        if (r == null || !r.optBoolean("ok")) return null;
        return r.optJSONObject("spec");
    }

    /** Watch ONE YouTube video now -> CANDIDATE row.
     *  v1.2.1: transcript PHONE se fetch hota hai (phone ka mobile/WiFi IP YouTube se
     *  block nahi hota; datacenter IPs ko "confirm you're not a bot" aata hai).
     *  Sirf transcript TEXT AI proxy ko jata hai — strategy wahan banti hai. */
    public JSONObject addYouTube(String url) throws Exception {
        String vid = extractVideoId(url);
        if (vid == null) return fail("Ye YouTube video link nahi lag raha");
        String title = "", channel = "";
        String page = httpGetStr("https://www.youtube.com/watch?v=" + vid + "&hl=en", DESKTOP_UA, 20000);
        if (page != null) {
            java.util.regex.Matcher tm = java.util.regex.Pattern.compile("<title>(.*?)</title>").matcher(page);
            if (tm.find()) {
                title = tm.group(1).replaceAll(" - YouTube$", "")
                        .replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", "\"");
            }
            java.util.regex.Matcher cm = java.util.regex.Pattern.compile("\"ownerChannelName\":\"(.*?)\"").matcher(page);
            if (cm.find()) channel = cm.group(1).replace("\\u0026", "&");
        }
        String transcript = fetchTranscript(vid);
        if (transcript == null)
            return fail("Is video ke captions nahi mile — captions wali video try karein (auto-captions bhi chalti hain)");
        JSONObject r = aiPost("/api/ai/transcript", new JSONObject()
                .put("title", title).put("channel", channel).put("transcript", transcript), 120000);
        if (r == null || !r.optBoolean("ok"))
            return fail(r == null ? (lastAiError != null ? lastAiError : "AI service unreachable")
                    : r.optString("error", "Video se strategy nahi bani"));
        JSONObject spec = r.optJSONObject("spec");
        if (spec == null) return fail("Video se strategy spec nahi bani");
        JSONObject video = new JSONObject().put("id", vid).put("title", title)
                .put("channel", channel).put("url", "https://www.youtube.com/watch?v=" + vid);
        spec.put("video", video.toString());
        spec.put("source", "YOUTUBE");
        return insert("YOUTUBE", video.toString(), spec);
    }

    private static final String DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

    /** watch/shorts/live/be URL se 11-char video ID. */
    private static String extractVideoId(String url) {
        java.util.regex.Matcher m = java.util.regex.Pattern
                .compile("(?:v=|youtu\\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})").matcher(url);
        return m.find() ? m.group(1) : null;
    }

    /** Generic HTTPS GET with UA — phone ke apne IP se (YouTube blocks datacenter IPs). */
    private static String httpGetStr(String url, String ua, int timeoutMs) {
        try {
            HttpURLConnection cn = (HttpURLConnection) new URL(url).openConnection();
            cn.setConnectTimeout(timeoutMs);
            cn.setReadTimeout(timeoutMs);
            cn.setRequestProperty("User-Agent", ua);
            cn.setRequestProperty("Accept-Language", "en-US,en;q=0.9");
            int code = cn.getResponseCode();
            if (code != 200) return null;
            BufferedReader r = new BufferedReader(new InputStreamReader(cn.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = r.readLine()) != null) sb.append(line);
            r.close();
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }

    /** Phone se captions nikalta hai: watch page → captionTracks → json3 transcript. */
    private String fetchTranscript(String vid) {
        try {
            String page = httpGetStr("https://www.youtube.com/watch?v=" + vid + "&hl=en", DESKTOP_UA, 20000);
            if (page == null) return null;
            java.util.regex.Matcher m = java.util.regex.Pattern
                    .compile("\"captionTracks\":(\\[.*?\\])(,\"audioTracks\"|,\"translationLanguages\"|\\})")
                    .matcher(page);
            if (!m.find()) return null;
            JSONArray tracks = new JSONArray(m.group(1).replace("\\u0026", "&").replace("\\\\/", "/"));
            String baseUrl = null;
            for (int pass = 0; pass < 2 && baseUrl == null; pass++) {
                for (int i = 0; i < tracks.length(); i++) {
                    JSONObject t = tracks.getJSONObject(i);
                    String lang = t.optString("languageCode", "");
                    boolean asr = "asr".equals(t.optString("kind", ""));
                    if (pass == 0 && lang.startsWith("en") && !asr) { baseUrl = t.optString("baseUrl"); break; }
                    if (pass == 1 && lang.startsWith("en")) { baseUrl = t.optString("baseUrl"); break; }
                }
            }
            if (baseUrl == null && tracks.length() > 0) baseUrl = tracks.getJSONObject(0).optString("baseUrl");
            if (baseUrl == null || baseUrl.isEmpty()) return null;
            String cap = httpGetStr(baseUrl + "&fmt=json3", DESKTOP_UA, 20000);
            if (cap == null) return null;
            StringBuilder sb = new StringBuilder();
            JSONArray events = new JSONObject(cap).optJSONArray("events");
            if (events != null) {
                for (int i = 0; i < events.length(); i++) {
                    JSONArray segs = events.getJSONObject(i).optJSONArray("segs");
                    if (segs == null) continue;
                    for (int j = 0; j < segs.length(); j++) sb.append(segs.getJSONObject(j).optString("utf8", ""));
                }
            }
            String out = sb.toString().replaceAll("\\s+", " ").trim();
            if (out.length() < 200) return null;
            return out.length() > 12000 ? out.substring(0, 12000) : out;
        } catch (Exception e) {
            return null;
        }
    }

    /** Subscribe to a channel — engine watches ALL new videos + live streams (15 min poll). */
    public JSONObject subscribeChannel(String url) throws Exception {
        JSONObject r = aiPost("/api/ai/ytlist", new JSONObject().put("url", url), 60000);
        if (r == null || !r.optBoolean("ok"))
            return fail(r == null ? (lastAiError != null ? lastAiError : "AI service unreachable")
                    : r.optString("error", "Channel resolve nahi hui"));
        JSONObject ch = r.optJSONObject("channel");
        if (ch == null) return fail("Channel ID nahi mili");
        db.setSetting("yt_channel_id", ch.optString("id"));
        db.setSetting("yt_channel_name", ch.optString("name"));
        JSONArray vids = r.optJSONArray("videos");
        // seed seen-list with current ids so we only process FUTURE uploads
        JSONArray seen = new JSONArray();
        if (vids != null) for (int i = 0; i < vids.length(); i++) seen.put(vids.optJSONObject(i).optString("id"));
        db.setSetting("yt_seen", seen.toString());
        db.log("INFO", "LAB", "YT_SUBSCRIBE", "channel '" + ch.optString("name")
                + "' — engine ab har naya video + live stream 15 min mein check karke AI se strategy banayegi");
        return r;
    }

    public void stopChannel() {
        db.setSetting("yt_channel_id", "");
        db.log("INFO", "LAB", "YT_STOP", "channel watcher stopped");
    }

    /** Every 15 min (called from EngineCore loop): process new channel videos + live. */
    public void watchYouTube() throws Exception {
        String cid = db.setting("yt_channel_id", "");
        if (cid == null || cid.isEmpty()) return;
        JSONObject r = aiPost("/api/ai/ytlist", new JSONObject().put("url",
                "https://www.youtube.com/channel/" + cid), 60000);
        if (r == null) return;
        JSONArray vids = r.optJSONArray("videos");
        if (vids == null) return;
        JSONArray seen;
        try { seen = new JSONArray(db.setting("yt_seen", "[]")); } catch (Exception e) { seen = new JSONArray(); }
        List<String> seenL = new ArrayList<>();
        for (int i = 0; i < seen.length(); i++) seenL.add(seen.optString(i));

        int added = 0;
        for (int i = 0; i < vids.length() && added < 3; i++) { // max 3 per cycle — LLM cost guard
            JSONObject v = vids.optJSONObject(i);
            String id = v.optString("id");
            if (id.isEmpty() || seenL.contains(id)) continue;
            boolean live = v.optBoolean("live");
            db.log("INFO", "LAB", "YT_PROCESS", (live ? "LIVE STREAM" : "video") + " '"
                    + v.optString("title") + "' — AI se strategy extract ho rahi hai");
            JSONObject res = addYouTube("https://www.youtube.com/watch?v=" + id);
            seenL.add(id);
            seen.put(id);
            added++;
            if (res != null && res.optBoolean("ok")) {
                Notifier.post(ctx, "Strategy Lab — YouTube",
                        (live ? "Live stream" : "Naya video") + " se strategy bani: "
                                + res.optJSONObject("strategy").optString("name") + " (Lab tab mein backtest karein)");
            }
        }
        if (added > 0) {
            while (seen.length() > 200) seen.remove(0); // cap memory
            db.setSetting("yt_seen", seen.toString());
        }
    }

    private JSONObject insert(String source, String videoMeta, JSONObject spec) {
        long now = System.currentTimeMillis();
        db.getWritableDatabase().execSQL(
                "INSERT INTO strategies(name, source, video, spec, status, stats, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                new Object[]{spec.optString("name", "Custom"), source,
                        videoMeta == null ? "{}" : videoMeta, spec.toString(), "CANDIDATE", "{}", now, now});
        db.log("INFO", "LAB", "STRATEGY_ADDED", source + " '" + spec.optString("name") + "' — CANDIDATE (backtest karein)");
        JSONObject out = new JSONObject();
        try {
            out.put("ok", true);
            out.put("strategy", new JSONObject().put("name", spec.optString("name"))
                    .put("spec", spec).put("status", "CANDIDATE").put("source", source));
            if (source.equals("YOUTUBE") && spec.has("video") == false && lastAiError != null) out.put("warn", lastAiError);
        } catch (Exception ignored) { }
        return out;
    }

    private String sourceFrom(JSONObject spec) {
        return spec != null && spec.has("source") ? spec.optString("source", "MANUAL") : "MANUAL";
    }

    // ================== v1.4 AUTO-EVOLVE ("aur strategies banati raho") ==================

    /**
     * Har 6h (EngineCore loop se call): AI ek NAYI complementary strategy propose
     * karta hai (3C MASTER se different), use foran real candles par backtest kiya
     * jata hai aur owner ko notification jati hai. Strategy BACKTESTED status mein
     * Lab list mein aati hai — PAPER/LIVE sirf owner approve karta hai. AI kabhi
     * khud live nahi jati (MASTER PROMPT category-D: hypothesis, approved nahi).
     */
    public void autoEvolve() {
        if (!"1".equals(db.setting("lab_auto", "1"))) return;
        try {
            Cursor cnt = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM strategies WHERE deleted_at=0", null);
            int n = cnt.moveToFirst() ? cnt.getInt(0) : 0;
            cnt.close();
            if (n >= 40) return; // owner review se pehle flood nahi — 40 strategies cap
            StringBuilder names = new StringBuilder();
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT name FROM strategies WHERE deleted_at=0 ORDER BY id DESC LIMIT 25", null);
            while (c.moveToNext()) { if (names.length() > 0) names.append("; "); names.append(c.getString(0)); }
            c.close();
            String prompt = "Hamara AI Trading Lab abhi 3C Breakout (M5) MASTER strategy paper-trade kar raha hai "
                    + "(3 candles: C1+C2 strong body>=70% same direction, C3 opposite protected candle, "
                    + "5-candle breakout window, SL opposite extreme, breakeven at +1R, close whole position at +3R). "
                    + "Existing lab strategies: " + (names.length() == 0 ? "(none)" : names) + ". "
                    + "Suggest ONE new complementary strategy that is DIFFERENT from all existing ones "
                    + "and can be evaluated on 5m crypto candles with these indicators only: rsi, price_vs_ema, "
                    + "ema_cross, sma, macd, bb, atr, supertrend, volume, change, stoch, cci, mfi, adx, candle. "
                    + "Sirf strategy spec do, koi lambi explanation nahi.";
            JSONObject spec = compileText(prompt);
            if (spec == null) { db.log("WARN", "LAB", "AUTO_EVOLVE_SKIP", lastAiError != null ? lastAiError : "AI spec nahi bani"); return; }
            JSONObject res = insert("AI_AUTO", "{}", spec);
            if (!res.optBoolean("ok")) return;
            long id = 0;
            Cursor ic = db.getReadableDatabase().rawQuery(
                    "SELECT id FROM strategies WHERE deleted_at=0 ORDER BY id DESC LIMIT 1", null);
            if (ic.moveToFirst()) id = ic.getLong(0);
            ic.close();
            if (id > 0) {
                JSONObject bt = backtest(id);
                JSONObject st = bt == null ? null : bt.optJSONObject("stats");
                db.log("INFO", "LAB", "AUTO_EVOLVE", "AI proposed '" + spec.optString("name", "Custom")
                        + "' — backtest: " + (st == null ? "fail" : st.optInt("trades", 0) + " trades, WR "
                        + st.optDouble("winrate", 0) + "%, net " + st.optDouble("netPct", 0) + "%"));
                Notifier.post(ctx, "Strategy Lab — Auto-Evolve",
                        "AI ne nayi strategy banayi: " + spec.optString("name", "Custom")
                                + (st != null ? " — " + st.optInt("trades", 0) + " trades, WR "
                                + st.optDouble("winrate", 0) + "%, net " + st.optDouble("netPct", 0) + "%" : "")
                                + " — Lab tab mein review karein (PAPER/LIVE aap approve karenge)");
            }
        } catch (Throwable t) {
            db.log("ERROR", "LAB", "AUTO_EVOLVE_FAIL", String.valueOf(t));
        }
    }

    // ================== LIFECYCLE ==================

    /** Backtest on real 5m klines. Symbol: settings lab_symbol (default XAUUSD — HALAL MT5). */
    public JSONObject backtest(long id) {
        JSONObject spec = rowSpec(id);
        if (spec == null) return fail("Strategy nahi mili");
        String sym = db.setting("lab_symbol", "XAUUSD");
        List<EngineCore.Candle> k = engine.klinesFor(sym, 1000);
        if (k == null || k.size() < 120) return fail(sym + " ke real candles fetch nahi hue — dobara try karein");
        // drop unclosed last candle (v5.9.2 rule)
        if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < EngineCore.TF_MS_PUB) {
            k = k.subList(0, k.size() - 1);
        }
        if (k.size() < 120) return fail("Candle data bohat chhota hai");

        double equity = 100, peak = 100, maxDD = 0;
        int wins = 0, losses = 0, bars = k.size();
        double grossWin = 0, grossLoss = 0;
        int side = spec.optString("side", "BOTH").equals("BUY") ? 1 : spec.optString("side", "BOTH").equals("SELL") ? -1 : 0;
        int logicAny = "ANY".equals(spec.optString("logic", "ALL")) ? 1 : 0;
        JSONArray conds = spec.optJSONArray("conditions");

        // sim position
        boolean open = false; int oSide = 0; double oEntry = 0, oSl = 0, oTp = 0, oQty = 0; int oBar = 0;
        List<double[]> trades = new ArrayList<>(); // [pnl, side(1/-1), bars]

        for (int i = 60; i < bars; i++) {
            List<EngineCore.Candle> hist = k.subList(0, i + 1);
            EngineCore.Candle c = k.get(i);
            if (open) {
                boolean hitSl = oSide == 1 ? c.l <= oSl : c.h >= oSl;
                boolean hitTp = oSide == 1 ? c.h >= oTp : c.l <= oTp;
                if (hitSl || hitTp) { // conservative: SL wins the tie
                    double exit = hitSl ? oSl : oTp;
                    double pnl = (oSide == 1 ? exit - oEntry : oEntry - exit) * oQty;
                    equity += pnl; peak = Math.max(peak, equity);
                    maxDD = Math.max(maxDD, peak > 0 ? (peak - equity) / peak : 0);
                    if (pnl >= 0) { wins++; grossWin += pnl; } else { losses++; grossLoss += -pnl; }
                    trades.add(new double[]{pnl, oSide, i - oBar});
                    open = false;
                }
                continue; // one sim position at a time
            }
            int dir = evaluateSpec(conds, logicAny, hist);
            if (dir == 0) continue;
            if (side != 0) dir = side;           // explicit side overrides inference
            double a = atr(hist, 14);
            if (Double.isNaN(a) || a <= 0) continue;
            double riskAmt = equity * 0.01;      // 1% baseline risk — comparable stats
            double qty = riskAmt / (1.5 * a);
            if (qty * c.c > equity * 0.95) qty = equity * 0.95 / c.c;
            if (qty <= 0) continue;
            oSide = dir; oEntry = c.c;
            oSl = dir == 1 ? c.c - 1.5 * a : c.c + 1.5 * a;
            oTp = dir == 1 ? c.c + 2.5 * a : c.c - 2.5 * a;
            oQty = qty; oBar = i; open = true;
        }
        // force-close any sim position at last close
        if (open) {
            EngineCore.Candle last = k.get(bars - 1);
            double pnl = (oSide == 1 ? last.c - oEntry : oEntry - last.c) * oQty;
            equity += pnl; peak = Math.max(peak, equity);
            maxDD = Math.max(maxDD, peak > 0 ? (peak - equity) / peak : 0);
            if (pnl >= 0) { wins++; grossWin += pnl; } else { losses++; grossLoss += -pnl; }
            trades.add(new double[]{pnl, oSide, bars - oBar});
        }

        int nT = wins + losses;
        JSONObject stats = new JSONObject();
        try {
            double pf = grossLoss > 0 ? Math.round(100.0 * grossWin / grossLoss) / 100.0 : (grossWin > 0 ? 99 : 0);
            double netPct = Math.round((equity - 100) * 100.0) / 100.0;
            // v1.8 QUALITY GATE — verdict: STRONG (PF>=1.15 & >=30 trades) / OK (PF>=1.0) / WEAK
            String verdict = (pf >= 1.15 && nT >= 30) ? "STRONG" : (pf >= 1.0 && nT >= 15) ? "OK" : "WEAK";
            stats.put("symbol", sym).put("bars", bars)
                    .put("trades", nT).put("wins", wins).put("losses", losses)
                    .put("winrate", nT > 0 ? Math.round(1000.0 * wins / nT) / 10.0 : 0)
                    .put("pf", pf)
                    .put("net", Math.round(equity - 100) * 100.0 / 100.0)
                    .put("netPct", netPct)
                    .put("maxDD", Math.round(maxDD * 1000.0) / 10.0)
                    .put("verdict", verdict)
                    .put("riskModel", "1% baseline, SL 1.5xATR, TP 2.5xATR (Lab strategies — 3C MASTER apne rules se chalta hai)");
        } catch (Exception ignored) { }

        db.getWritableDatabase().execSQL(
                "UPDATE strategies SET status=?, stats=?, updated_at=? WHERE id=?",
                new Object[]{"BACKTESTED", stats.toString(), System.currentTimeMillis(), id});
        db.log("INFO", "LAB", "BACKTEST_DONE", "strategy #" + id + " on " + sym + " — " + nT + " trades, winrate "
                + stats.optDouble("winrate", 0) + "%, PF " + stats.optDouble("pf", 0) + ", net "
                + stats.optDouble("netPct", 0) + "%, maxDD " + stats.optDouble("maxDD", 0) + "%");
        JSONObject out = new JSONObject();
        try { out.put("ok", true).put("stats", stats); } catch (Exception ignored) { }
        return out;
    }

    /** PAPER shadow phase — strategy trades the live paper account (tagged AI: name). */
    public JSONObject startPaper(long id) {
        return setStatus(id, "PAPER", "paper shadow phase shuru — ab ye strategy live candles par khud signal degi");
    }

    /** Owner approval — strategy goes LIVE as its own signal source. */
    public JSONObject approve(long id) {
        // v1.8 quality gate — WEAK verdict par owner ko warning (phir bhi approve allowed)
        JSONObject st = statsOf(id);
        String verdict = st != null ? st.optString("verdict", "") : "";
        double pf = st != null ? st.optDouble("pf", 0) : 0;
        int trades = st != null ? st.optInt("trades", 0) : 0;
        String msg = "owner ne LIVE approve kiya — ye strategy ab apne aap trade karegi";
        if ("WEAK".equals(verdict))
            msg = "owner ne LIVE approve kiya — ⚠ WARNING: backtest verdict WEAK (PF " + pf + ", " + trades
                    + " trades) — ye strategy loss de sakti hai";
        return setStatus(id, "ACTIVE", msg);
    }

    /** v1.8 — strategy ka latest backtest stats (quality gate ke liye). */
    private JSONObject statsOf(long id) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT stats FROM strategies WHERE id=?",
                new String[]{String.valueOf(id)});
        JSONObject st = null;
        if (c.moveToFirst()) { try { st = new JSONObject(c.getString(0)); } catch (Exception ignored) { } }
        c.close();
        return st;
    }

    public JSONObject reject(long id) {
        return setStatus(id, "REJECTED", "strategy reject hui");
    }

    /** v1.7 SOFT DELETE — strategy Trash mein jati hai, 7 din tak UNDO ho sakti hai.
     *  (owner request: "galti se koi strategy delete kardi ho to undo ka option ho") */
    public JSONObject remove(long id) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT name, status FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(id)});
        if (!c.moveToFirst()) { c.close(); return fail("Strategy nahi mili (shayad pehle hi delete ho chuki)"); }
        String name = c.getString(0), status = c.getString(1); c.close();
        long now = System.currentTimeMillis();
        db.getWritableDatabase().execSQL("UPDATE strategies SET deleted_at=?, updated_at=? WHERE id=?",
                new Object[]{now, now, id});
        db.log("INFO", "LAB", "STRATEGY_TRASHED", "'" + name + "' (#" + id + ", " + status
                + ") Trash mein — 7 din tak UNDO possible, phir auto-purge");
        purgeTrash();
        JSONObject out = new JSONObject();
        try { out.put("ok", true).put("message", "'" + name + "' delete hui — "
                + "ghalti se hui? 7 din tak UNDO button se wapas la sakte ho"); } catch (Exception ignored) { }
        return out;
    }

    /** v1.7 UNDO — Trash se strategy wapas layen (deleted_at=0, original status ke saath). */
    public JSONObject restore(long id) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT name FROM strategies WHERE id=? AND deleted_at>0", new String[]{String.valueOf(id)});
        if (!c.moveToFirst()) { c.close(); return fail("Trash mein aisi koi strategy nahi mili"); }
        String name = c.getString(0); c.close();
        db.getWritableDatabase().execSQL("UPDATE strategies SET deleted_at=0, updated_at=? WHERE id=?",
                new Object[]{System.currentTimeMillis(), id});
        db.log("INFO", "LAB", "STRATEGY_RESTORED", "'" + name + "' (#" + id + ") Trash se restore — UNDO kaam kar gaya");
        JSONObject out = new JSONObject();
        try { out.put("ok", true).put("message", "'" + name + "' wapas restore ho gayi — apni original status ke saath"); } catch (Exception ignored) { }
        return out;
    }

    /** v1.7 — Trash list (deleted_at>0) with remaining UNDO days. */
    public JSONObject trash() {
        JSONObject out = new JSONObject();
        try {
            JSONArray arr = new JSONArray();
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT id, name, status, deleted_at FROM strategies WHERE deleted_at>0 ORDER BY deleted_at DESC", null);
            long now = System.currentTimeMillis();
            while (c.moveToNext()) {
                long del = c.getLong(3);
                long daysLeft = 7 - ((now - del) / 86400000L);
                if (daysLeft < 0) daysLeft = 0;
                arr.put(new JSONObject()
                        .put("id", c.getLong(0)).put("name", c.getString(1))
                        .put("status", c.getString(2)).put("deleted_at", del)
                        .put("daysLeft", daysLeft));
            }
            c.close();
            out.put("trash", arr).put("ok", true);
        } catch (Exception e) { return fail("Trash load fail: " + e.getMessage()); }
        return out;
    }

    /** v1.7 — 7 din se purani deleted strategies permanently purge (auto-cleanup). */
    private void purgeTrash() {
        long cutoff = System.currentTimeMillis() - 7L * 86400000L;
        db.getWritableDatabase().execSQL("DELETE FROM strategies WHERE deleted_at>0 AND deleted_at<?", new Object[]{cutoff});
    }

    private JSONObject setStatus(long id, String status, String msg) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT name FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(id)});
        if (!c.moveToFirst()) { c.close(); return fail("Strategy nahi mili"); }
        String name = c.getString(0); c.close();
        db.getWritableDatabase().execSQL("UPDATE strategies SET status=?, updated_at=? WHERE id=?",
                new Object[]{status, System.currentTimeMillis(), id});
        db.log("INFO", "LAB", "STRATEGY_" + status, "'" + name + "' — " + msg);
        if ("ACTIVE".equals(status)) Notifier.post(ctx, "Strategy Lab", name + " ab LIVE hai — " + msg);
        JSONObject out = new JSONObject();
        try { out.put("ok", true).put("status", status).put("message", name + " — " + msg); } catch (Exception ignored) { }
        return out;
    }

    private JSONObject rowSpec(long id) {
        Cursor c = db.getReadableDatabase().rawQuery("SELECT spec FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(id)});
        JSONObject spec = null;
        if (c.moveToFirst()) { try { spec = new JSONObject(c.getString(0)); } catch (Exception ignored) { } }
        c.close();
        return spec;
    }

    private JSONObject fail(String msg) {
        JSONObject out = new JSONObject();
        try { out.put("ok", false).put("error", msg); } catch (Exception ignored) { }
        return out;
    }

    // ================== SPEC EVALUATOR ==================

    /**
     * Evaluate a compiled spec on closed candles (k's last element = last CLOSED candle).
     * Returns +1 (bullish entry), -1 (bearish entry), 0 (no signal).
     * side=BOTH: direction inferred from condition polarity (dip-style -> bull,
     * rally-style -> bear); pure-filter specs (volume/adx/atr only) default bullish.
     */
    public static int evaluateSpec(JSONArray conds, int logicAny, List<EngineCore.Candle> k) {
        if (conds == null || conds.length() == 0) return 0;
        int bull = 0, bear = 0, passed = 0;
        for (int i = 0; i < conds.length(); i++) {
            JSONObject c = conds.optJSONObject(i);
            if (c == null) continue;
            Object[] r = evalCond(c, k);          // [conditionPassed(0/1), polarity(+1 bull,-1 bear,0 filter)]
            if (r == null) continue;
            if ((int) r[0] == 1) passed++;
            int pol = (int) r[1];
            if ((int) r[0] == 1) { if (pol > 0) bull++; else if (pol < 0) bear++; }
        }
        boolean met = logicAny == 1 ? passed > 0 : passed == conds.length();
        if (!met) return 0;
        if (bull > bear) return 1;
        if (bear > bull) return -1;
        return 1; // all-neutral filters -> default long (documented)
    }

    /** returns [passed(0/1), polarity(+1/-1/0)] or null if unknown indicator */
    private static Object[] evalCond(JSONObject c, List<EngineCore.Candle> k) {
        String ind = c.optString("ind", ""), op = c.optString("op", "");
        EngineCore.Candle last = k.get(k.size() - 1);
        double px = last.c;
        switch (ind) {
            case "rsi": {
                double v = rsi(k, c.optInt("p", 14));
                if (Double.isNaN(v)) return new Object[]{0, 0};
                boolean passed = cmp(v, op, c.optDouble("v", 30));
                return new Object[]{passed ? 1 : 0, op.contains("<") ? 1 : -1};
            }
            case "price_vs_ema": {
                double e = ema(k, c.optInt("p", 50));
                if (Double.isNaN(e)) return new Object[]{0, 0};
                boolean above = px > e;
                return new Object[]{(op.equals("above") == above) ? 1 : 0, above ? 1 : -1};
            }
            case "ema_cross": {
                double f = ema(k, c.optInt("f", 9)), s = ema(k, c.optInt("s", 21));
                if (Double.isNaN(f) || Double.isNaN(s)) return new Object[]{0, 0};
                boolean golden = f > s;
                return new Object[]{(op.equals("golden") == golden) ? 1 : 0, golden ? 1 : -1};
            }
            case "sma": {
                double m = sma(k, c.optInt("p", 20));
                if (Double.isNaN(m)) return new Object[]{0, 0};
                switch (op) {
                    case "price_above": return new Object[]{px > m ? 1 : 0, 1};
                    case "price_below": return new Object[]{px < m ? 1 : 0, -1};
                    case "slope_up": {
                        double mPrev = sma(k.subList(0, k.size() - 3), c.optInt("p", 20));
                        return new Object[]{(!Double.isNaN(mPrev) && m > mPrev) ? 1 : 0, 1};
                    }
                    case "slope_down": {
                        double mPrev = sma(k.subList(0, k.size() - 3), c.optInt("p", 20));
                        return new Object[]{(!Double.isNaN(mPrev) && m < mPrev) ? 1 : 0, -1};
                    }
                    default: return new Object[]{0, 0};
                }
            }
            case "macd": {
                double[] m = macd(k, c.optInt("f", 12), c.optInt("s", 26), c.optInt("sig", 9));
                if (m == null) return new Object[]{0, 0};
                boolean bull = m[0] > m[1];
                return new Object[]{(op.equals("bull") == bull) ? 1 : 0, bull ? 1 : -1};
            }
            case "bb": {
                double[] b = bollinger(k, c.optInt("p", 20), c.optDouble("k", 2));
                if (b == null) return new Object[]{0, 0};
                switch (op) {
                    case "lower_touch": return new Object[]{px <= b[1] ? 1 : 0, 1};
                    case "upper_touch": return new Object[]{px >= b[0] ? 1 : 0, -1};
                    case "squeeze": {
                        double w = (b[0] - b[1]) / (b[2] == 0 ? 1 : b[2]);
                        return new Object[]{w < 0.03 ? 1 : 0, 0};
                    }
                    default: return new Object[]{0, 0};
                }
            }
            case "atr": {
                double a = atr(k, c.optInt("p", 14));
                if (Double.isNaN(a) || px <= 0) return new Object[]{0, 0};
                double pct = 100.0 * a / px;
                return new Object[]{cmp(pct, op, c.optDouble("v", 0.3)) ? 1 : 0, 0};
            }
            case "supertrend": {
                int st = supertrendDir(k, c.optInt("p", 10), c.optDouble("m", 3));
                boolean bull = st > 0;
                return new Object[]{(op.equals("bull") == bull) ? 1 : 0, bull ? 1 : -1};
            }
            case "volume": {
                if (k.size() < c.optInt("p", 20) + 2) return new Object[]{0, 0};
                double avg = 0; int p = c.optInt("p", 20);
                for (int i = k.size() - 1 - p; i < k.size() - 1; i++) avg += k.get(i).v;
                avg /= p;
                return new Object[]{cmp(last.v, op, avg * c.optDouble("v", 1.5)) ? 1 : 0, 0};
            }
            case "change": {
                int n = Math.max(1, c.optInt("n", 5));
                if (k.size() < n + 1) return new Object[]{0, 0};
                double prev = k.get(k.size() - 1 - n).c;
                double chg = prev != 0 ? 100.0 * (px - prev) / prev : 0;
                return new Object[]{cmp(chg, op, c.optDouble("v", 1.0)) ? 1 : 0, op.contains("<") ? -1 : 1};
            }
            case "stoch": {
                double s = stochK(k, c.optInt("p", 14));
                if (Double.isNaN(s)) return new Object[]{0, 0};
                return new Object[]{cmp(s, op, c.optDouble("v", 20)) ? 1 : 0, op.contains("<") ? 1 : -1};
            }
            case "cci": {
                double v = cci(k, c.optInt("p", 20));
                if (Double.isNaN(v)) return new Object[]{0, 0};
                return new Object[]{cmp(v, op, c.optDouble("v", -100)) ? 1 : 0, op.contains("<") ? 1 : -1};
            }
            case "mfi": {
                double v = mfi(k, c.optInt("p", 14));
                if (Double.isNaN(v)) return new Object[]{0, 0};
                return new Object[]{cmp(v, op, c.optDouble("v", 20)) ? 1 : 0, op.contains("<") ? 1 : -1};
            }
            case "adx": {
                double v = adx(k, c.optInt("p", 14));
                if (Double.isNaN(v)) return new Object[]{0, 0};
                return new Object[]{cmp(v, op, c.optDouble("v", 25)) ? 1 : 0, 0};
            }
            case "candle": {
                switch (op) {
                    case "engulf_bull": return new Object[]{engulf(k, 1) ? 1 : 0, 1};
                    case "engulf_bear": return new Object[]{engulf(k, -1) ? 1 : 0, -1};
                    case "doji": {
                        double body = Math.abs(last.c - last.o), range = last.h - last.l;
                        return new Object[]{(range > 0 && body <= 0.1 * range) ? 1 : 0, 0};
                    }
                    case "hammer": {
                        double body = Math.abs(last.c - last.o), lo = Math.min(last.c, last.o) - last.l, hi = last.h - Math.max(last.c, last.o);
                        return new Object[]{(lo > 2 * body && hi < body) ? 1 : 0, 1};
                    }
                    default: return new Object[]{0, 0};
                }
            }
            default: return new Object[]{0, 0}; // unknown indicator never passes
        }
    }

    private static boolean cmp(double a, String op, double b) {
        switch (op) {
            case "<": return a < b;
            case "<=": return a <= b;
            case ">": return a > b;
            case ">=": return a >= b;
            default: return a < b;
        }
    }

    // ================== INDICATOR HELPERS (closed-candle math) ==================

    public static double ema(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p) return Double.NaN;
        double m = 0, alpha = 2.0 / (p + 1);
        m = k.get(0).c;
        for (int i = 1; i < k.size(); i++) m = k.get(i).c * alpha + m * (1 - alpha);
        return m;
    }

    public static double sma(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p) return Double.NaN;
        double s = 0;
        for (int i = k.size() - p; i < k.size(); i++) s += k.get(i).c;
        return s / p;
    }

    public static double rsi(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p + 1) return Double.NaN;
        double g = 0, l = 0;
        for (int i = k.size() - p; i < k.size(); i++) {
            double d = k.get(i).c - k.get(i - 1).c;
            if (d > 0) g += d; else l += -d;
        }
        if (l == 0) return 100;
        double rs = (g / p) / (l / p);
        return 100 - 100 / (1 + rs);
    }

    public static double[] macd(List<EngineCore.Candle> k, int f, int s, int sig) {
        if (k == null || k.size() < s + sig + 5) return null;
        double af = 2.0 / (f + 1), as = 2.0 / (s + 1), ag = 2.0 / (sig + 1);
        double ef = k.get(0).c, es = k.get(0).c, line = 0, sg = 0;
        List<Double> lines = new ArrayList<>();
        for (int i = 1; i < k.size(); i++) {
            ef = k.get(i).c * af + ef * (1 - af);
            es = k.get(i).c * as + es * (1 - as);
            lines.add(ef - es);
        }
        sg = lines.get(0);
        for (int i = 1; i < lines.size(); i++) sg = lines.get(i) * ag + sg * (1 - ag);
        return new double[]{lines.get(lines.size() - 1), sg};
    }

    public static double[] bollinger(List<EngineCore.Candle> k, int p, double mult) {
        if (k == null || k.size() < p) return null;
        double m = sma(k, p), v = 0;
        for (int i = k.size() - p; i < k.size(); i++) v += Math.pow(k.get(i).c - m, 2);
        double sd = Math.sqrt(v / p);
        return new double[]{m + mult * sd, m - mult * sd, m};
    }

    public static double atr(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p + 1) return Double.NaN;
        double a = 0;
        for (int i = k.size() - p; i < k.size(); i++) {
            double tr = Math.max(k.get(i).h - k.get(i).l,
                    Math.max(Math.abs(k.get(i).h - k.get(i - 1).c), Math.abs(k.get(i).l - k.get(i - 1).c)));
            a += tr;
        }
        return a / p;
    }

    public static int supertrendDir(List<EngineCore.Candle> k, int p, double mult) {
        if (k == null || k.size() < p + 2) return 0;
        double a = atr(k, p);
        if (Double.isNaN(a) || a <= 0) return 0;
        double mid = 0;
        for (int i = k.size() - p; i < k.size(); i++) mid += (k.get(i).h + k.get(i).l) / 2;
        mid /= p;
        double last = k.get(k.size() - 1).c;
        return last > mid + 0 ? 1 : -1; // simplified band test — consistent across backtest & live
    }

    public static double stochK(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p) return Double.NaN;
        double hh = -Double.MAX_VALUE, ll = Double.MAX_VALUE;
        for (int i = k.size() - p; i < k.size(); i++) {
            hh = Math.max(hh, k.get(i).h); ll = Math.min(ll, k.get(i).l);
        }
        return hh == ll ? 50 : 100 * (k.get(k.size() - 1).c - ll) / (hh - ll);
    }

    public static double cci(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p) return Double.NaN;
        double m = 0;
        List<Double> tp = new ArrayList<>();
        for (int i = k.size() - p; i < k.size(); i++) {
            double v = (k.get(i).h + k.get(i).l + k.get(i).c) / 3;
            tp.add(v); m += v;
        }
        m /= p;
        double dev = 0;
        for (double v : tp) dev += Math.abs(v - m);
        dev /= p;
        double lastTp = tp.get(tp.size() - 1);
        return dev == 0 ? 0 : (lastTp - m) / (0.015 * dev);
    }

    public static double mfi(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < p + 1) return Double.NaN;
        double pos = 0, neg = 0;
        for (int i = k.size() - p; i < k.size(); i++) {
            double tp = (k.get(i).h + k.get(i).l + k.get(i).c) / 3;
            double pr = (k.get(i - 1).h + k.get(i - 1).l + k.get(i - 1).c) / 3;
            double flow = tp * k.get(i).v;
            if (tp > pr) pos += flow; else if (tp < pr) neg += flow;
        }
        return neg == 0 ? 100 : 100 - 100 / (1 + pos / neg);
    }

    public static double adx(List<EngineCore.Candle> k, int p) {
        if (k == null || k.size() < 2 * p + 2) return Double.NaN;
        double pdm = 0, ndm = 0, tr = 0;
        for (int i = k.size() - 2 * p; i < k.size(); i++) {
            double up = k.get(i).h - k.get(i - 1).h, dn = k.get(i - 1).l - k.get(i).l;
            if (up > dn && up > 0) pdm += up;
            if (dn > up && dn > 0) ndm += dn;
            tr += Math.max(k.get(i).h - k.get(i).l,
                    Math.max(Math.abs(k.get(i).h - k.get(i - 1).c), Math.abs(k.get(i).l - k.get(i - 1).c)));
        }
        if (tr == 0) return 0;
        double pdi = 100 * pdm / tr, ndi = 100 * ndm / tr;
        double sum = pdi + ndi;
        return sum == 0 ? 0 : 100 * Math.abs(pdi - ndi) / sum;
    }

    private static boolean engulf(List<EngineCore.Candle> k, int dir) {
        if (k.size() < 2) return false;
        EngineCore.Candle a = k.get(k.size() - 2), b = k.get(k.size() - 1);
        if (dir == 1) return a.c < a.o && b.c > b.o && b.c >= a.o && b.o <= a.c;
        return a.c > a.o && b.c < b.o && b.o >= a.c && b.c <= a.o;
    }

    // ================== LISTING (API) ==================

    /** All strategies: 3C MASTER (v1.4) + custom lab rows. */
    public JSONObject listStrategies() {
        JSONObject out = new JSONObject();
        try {
            JSONArray builtin = new JSONArray();
            String[][] meta = EngineCore.STRATEGY_META;
            int[] votes = engine.lastVotes;
            for (int i = 0; i < meta.length; i++) {
                builtin.put(new JSONObject()
                        .put("name", meta[i][0]).put("group", meta[i][1])
                        .put("vote", i < votes.length ? votes[i] : 0));
            }
            out.put("builtin", builtin);
            out.put("masterNote", "3C MASTER: C1+C2 body>=70%, C3 protected, 5-candle breakout window, SL opposite extreme, BE @+1R, TP @+3R — daily P/L UNLIMITED");

            JSONArray custom = new JSONArray();
            purgeTrash(); // v1.7 — 7+ din purani deleted strategies ka auto-cleanup
            Cursor c = db.getReadableDatabase().rawQuery(
                    "SELECT id, name, source, video, spec, status, stats, created_at, updated_at FROM strategies WHERE deleted_at=0 ORDER BY id DESC", null);
            while (c.moveToNext()) {
                JSONObject s = new JSONObject();
                s.put("id", c.getLong(0)).put("name", c.getString(1)).put("source", c.getString(2));
                try { s.put("video", new JSONObject(c.getString(3))); } catch (Exception e) { s.put("video", new JSONObject()); }
                try {
                    JSONObject spec = new JSONObject(c.getString(4));
                    s.put("notes", spec.optString("notes"));
                    JSONArray conds = spec.optJSONArray("conditions");
                    StringBuilder human = new StringBuilder();
                    if (conds != null) for (int i = 0; i < conds.length(); i++) {
                        JSONObject cd = conds.optJSONObject(i);
                        if (cd == null) continue;
                        if (human.length() > 0) human.append(" + ");
                        human.append(humanCond(cd));
                    }
                    s.put("rules", human.toString());
                } catch (Exception e) { s.put("rules", ""); }
                s.put("status", c.getString(5));
                try { s.put("stats", new JSONObject(c.getString(6))); } catch (Exception e) { s.put("stats", new JSONObject()); }
                s.put("created_at", c.getLong(7)).put("updated_at", c.getLong(8));
                custom.put(s);
            }
            c.close();
            out.put("custom", custom);
            // v1.7 — Trash preview (UNDO ki khabar dashboard par rehne ke liye)
            Cursor tc = db.getReadableDatabase().rawQuery(
                    "SELECT COUNT(*) FROM strategies WHERE deleted_at>0", null);
            out.put("trashCount", tc.moveToFirst() ? tc.getInt(0) : 0);
            tc.close();
            out.put("ytChannel", new JSONObject()
                    .put("id", db.setting("yt_channel_id", ""))
                    .put("name", db.setting("yt_channel_name", "")));
            out.put("lastVoteSym", engine.lastVoteSym);
            out.put("symbol", db.setting("lab_symbol", "XAUUSD"));
            out.put("ok", true);
        } catch (Exception e) {
            try { out.put("ok", false).put("error", String.valueOf(e)); } catch (Exception ignored) { }
        }
        return out;
    }

    /** Human-readable condition for the UI. */
    private static String humanCond(JSONObject c) {
        String ind = c.optString("ind"), op = c.optString("op");
        switch (ind) {
            case "rsi": return "RSI(" + c.optInt("p", 14) + ") " + op + " " + c.optDouble("v", 0);
            case "price_vs_ema": return "Price " + op + " EMA(" + c.optInt("p", 50) + ")";
            case "ema_cross": return "EMA(" + c.optInt("f", 9) + "/" + c.optInt("s", 21) + ") " + op;
            case "sma": return "SMA(" + c.optInt("p", 20) + ") " + op.replace("_", " ");
            case "macd": return "MACD " + op;
            case "bb": return "Bollinger " + op.replace("_", " ");
            case "atr": return "ATR% " + op + " " + c.optDouble("v", 0);
            case "supertrend": return "Supertrend " + op;
            case "volume": return "Volume " + op + " " + c.optDouble("v", 1.5) + "x avg";
            case "change": return "Change(" + c.optInt("n", 5) + "bar) " + op + " " + c.optDouble("v", 0) + "%";
            case "stoch": return "Stoch " + op + " " + c.optDouble("v", 0);
            case "cci": return "CCI " + op + " " + c.optDouble("v", 0);
            case "mfi": return "MFI " + op + " " + c.optDouble("v", 0);
            case "adx": return "ADX " + op + " " + c.optDouble("v", 0);
            case "candle": return "Candle: " + op.replace("_", " ");
            default: return ind + " " + op;
        }
    }
}
