package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import java.util.Locale;
import java.util.Map;
import org.json.JSONArray;
import org.json.JSONObject;

/** REST API + auth flow + dashboard hosting — mirrors the cloud engine's API shapes. */
public class Api {
    public static class Res {
        public int status = 200;
        public String contentType = "application/json";
        public String body = "{}";
        public static Res json(int code, Object o) {
            Res r = new Res();
            r.status = code;
            r.body = o instanceof String ? (String) o : o.toString();
            return r;
        }
        public static Res error(int code, String msg) { try { return json(code, new JSONObject().put("error", msg)); } catch (Exception e) { return json(code, "{\"error\":\"error\"}"); } }
        public static Res html(String s) {
            Res r = new Res();
            r.contentType = "text/html; charset=utf-8";
            r.body = s;
            return r;
        }
    }

    private final Db db;
    private final EngineCore engine;
    private final String dashboardHtml;
    private final Context appCtx;

    public Api(Context ctx, Db db, EngineCore engine) {
        this.db = db;
        this.engine = engine;
        this.appCtx = ctx.getApplicationContext();
        String html = "";
        try {
            java.io.InputStream is = ctx.getAssets().open("dashboard.html");
            java.io.ByteArrayOutputStream bo = new java.io.ByteArrayOutputStream();
            byte[] buf = new byte[8192]; int n;
            while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
            html = new String(bo.toByteArray(), "UTF-8");
        } catch (Exception e) {
            html = "<html><body><h2>AI Trading Lab</h2><p>dashboard asset missing</p></body></html>";
        }
        this.dashboardHtml = html;
    }

    // ================== ROUTER ==================
    public Res route(String method, String rawPath, String authHeader, String body) {
        String path = rawPath;
        int q = path.indexOf('?');
        if (q >= 0) path = path.substring(0, q);
        String m = method.toUpperCase();

        if ("OPTIONS".equals(m)) return Res.json(200, "{}");

        try {
            if ("GET".equals(m)) return get(path, authHeader);
            if ("POST".equals(m)) return post(path, authHeader, body);
            if ("DELETE".equals(m)) return delete(path, authHeader);
            return Res.error(405, "method not allowed");
        } catch (Throwable e) {
            // v5.3: never swallow the cause — surface it so the user can report the REAL problem
            String cause = e.getClass().getSimpleName() + ": " + e.getMessage();
            try {
                android.util.Log.e("ATL.API", path + " failed — " + cause);
                db.log("ERROR", "API", "REQUEST_FAIL", path + " — " + cause);
            } catch (Throwable ignored) { }
            return Res.error(500, "server error — " + cause + " (screenshot this and report)");
        }
    }

    private Long userId(String authHeader) {
        if (authHeader == null) return null;
        String token = authHeader.startsWith("Bearer ") ? authHeader.substring(7) : authHeader;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT user_id FROM sessions WHERE token=?", new String[]{token});
        Long uid = c.moveToFirst() ? c.getLong(0) : null;
        c.close();
        return uid;
    }

    // ================== GET ==================
    private Res get(String path, String auth) throws Exception {
        if ("/".equals(path) || "/index.html".equals(path)) return Res.html(dashboardHtml);
        if ("/api/health".equals(path)) return Res.json(200, new JSONObject()
                .put("ok", true).put("engine", "ai-trading-lab-phone").put("device", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL).put("android", android.os.Build.VERSION.SDK_INT).put("version", "5.9.0").put("timeframe", "1m").put("scanner", "24h"));

        Long uid = userId(auth);
        if (uid == null) return Res.error(401, "authentication required");

        if ("/api/dashboard".equals(path)) return dashboard(uid);
        if ("/api/instruments".equals(path)) return instruments();
        if (path.startsWith("/api/indicators")) return indicators(path);
        if ("/api/news".equals(path)) return news();
        if ("/api/trades".equals(path)) return trades(uid);
        if ("/api/logs".equals(path)) return logs();
        if ("/api/brokers".equals(path)) return brokers();
        if ("/api/settings".equals(path)) return settings();
        // v5.7 FULL MOBILE CONTROL — owner admin endpoints (role=ADMIN required)
        if ("/api/admin/users".equals(path)) return adminUsers(uid);
        if ("/api/admin/invites".equals(path)) return adminInvites(uid);
        if ("/api/admin/alerts".equals(path)) return adminAlerts(uid);
        return Res.error(404, "not found");
    }

    // ================== POST ==================
    private Res post(String path, String auth, String body) throws Exception {
        // ---- public auth endpoints ----
        if ("/api/auth/register".equals(path)) return register(body);
        if ("/api/auth/login".equals(path)) return login(body);
        if ("/api/auth/verify2fa".equals(path)) return verify2fa(body);
        if ("/api/auth/reset".equals(path)) return resetPassword(body);

        Long uid = userId(auth);
        if (uid == null) return Res.error(401, "authentication required");

        if ("/api/auth/logout".equals(path)) return logout(auth);
        if ("/api/trades/close".equals(path)) return closeTrade(uid, body);
        if ("/api/brokers".equals(path)) return addBroker(body);
        if ("/api/brokers/test".equals(path)) return testBroker(body);
        if ("/api/instruments/scan".equals(path)) {
            if (engine != null) engine.forceDiscovery();
            db.log("INFO", "DISCOVERY", "MANUAL_SCAN", "user triggered discovery + news scan");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Discovery + news scan started"));
        }
        if ("/api/settings".equals(path)) return saveSettings(body);
        // v5.7 FULL MOBILE CONTROL — owner admin actions
        if ("/api/admin/users".equals(path)) return adminUserAction(uid, body);
        if ("/api/admin/invites".equals(path)) return adminInviteAction(uid, body);
        if ("/api/admin/alerts".equals(path)) return adminAlertAction(uid, body);
        return Res.error(404, "not found");
    }

    private Res delete(String path, String auth) throws Exception {
        Long uid = userId(auth);
        if (uid == null) return Res.error(401, "authentication required");
        if (path.startsWith("/api/brokers/")) {
            String id = path.substring("/api/brokers/".length());
            db.getWritableDatabase().execSQL("DELETE FROM brokers WHERE id=?", new Object[]{Long.parseLong(id)});
            db.log("INFO", "BROKER", "REMOVED", "broker #" + id + " removed");
            return Res.json(200, new JSONObject().put("ok", true));
        }
        return Res.error(404, "not found");
    }

    // ================== AUTH FLOW ==================
    private Res register(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name");
        String email = HttpServer.jStr(o, "email").toLowerCase();
        String pw = HttpServer.jStr(o, "password");
        String invite = HttpServer.jStr(o, "invitationCode");

        if (name.length() < 2 || name.length() > 60) return Res.error(400, "Enter your full name (2-60 characters)");
        if (!email.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) return Res.error(400, "Enter a valid email address");
        if (pw.length() < 8 || !pw.matches(".*[A-Za-z].*") || !pw.matches(".*[0-9].*"))
            return Res.error(400, "Password must be 8+ characters with letters and numbers");

        String err = Auth.checkInvite(db, invite);
        if (err != null) return Res.error(403, err);

        Cursor ex = db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE email=?", new String[]{email});
        if (ex.moveToFirst()) { ex.close(); return Res.error(409, "An account with this email already exists. Sign in instead."); }
        ex.close();

        Cursor cnt = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
        boolean first = cnt.moveToFirst() && cnt.getInt(0) == 0; cnt.close();
        String role = first ? "ADMIN" : "TRADER";

        String secret = Auth.totpSecret();
        db.getWritableDatabase().execSQL(
                "INSERT INTO users(email, name, pw_hash, role, totp_secret, totp_enabled, active, created_at) VALUES(?,?,?,?,?,0,1,?)",
                new Object[]{email, name, Auth.hashPw(pw), role, secret, System.currentTimeMillis()});
        Cursor nc = db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE email=?", new String[]{email});
        long uid = nc.moveToFirst() ? nc.getLong(0) : -1; nc.close();
        db.getWritableDatabase().execSQL(
                "INSERT OR IGNORE INTO accounts(user_id, balance, start_balance, peak, day_start, day_ts) VALUES(?,100000,100000,100000,100000,?)",
                new Object[]{uid, System.currentTimeMillis() / 86400000L});
        db.log("INFO", "AUTH", "REGISTER", email + " (" + role + ") — account + paper account created");
        // v5.7 — the owner now gets the alert THREE ways, instantly:
        //   1) persistent in-app row (Control tab feed — survives reboots)
        //   2) high-importance status-bar notification (Notifier)
        //   3) system ledger entry (log above)
        String code = invite == null ? "" : invite.trim().toUpperCase();
        try {
            String meta = new JSONObject().put("email", email).put("name", name)
                    .put("invite", code).put("role", role).toString();
            db.getWritableDatabase().execSQL(
                    "INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('REGISTER',?,?,?,0,?)",
                    new Object[]{"New registration — " + name,
                            name + " (" + email + ") joined via invitation code " + code
                                    + " · role: " + role + " · paper account created",
                            meta, System.currentTimeMillis()});
        } catch (Throwable ignored) { /* feed row is best-effort — registration must succeed */ }
        Notifier.registration(appCtx, name, email, role, code);
        return Res.json(200, new JSONObject().put("ok", true)
                .put("message", "Account created. Sign in with name + email + password."));
    }

    private Res login(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name").toLowerCase();
        String email = HttpServer.jStr(o, "email").toLowerCase();
        String pw = HttpServer.jStr(o, "password");

        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name, pw_hash, active, totp_enabled, totp_secret FROM users WHERE email=?", new String[]{email});
        if (!c.moveToFirst()) { c.close(); return Res.error(401, "Invalid email or password"); }
        long uid = c.getLong(0);
        String storedName = c.getString(1) == null ? "" : c.getString(1).trim().toLowerCase();
        String hash = c.getString(2);
        int active = c.getInt(3), totpEnabled = c.getInt(4);
        String secret = c.getString(5);
        c.close();

        if (!Auth.verifyPw(pw, hash)) return Res.error(401, "Invalid email or password");
        if (name.isEmpty() || !name.equals(storedName))
            return Res.error(401, "Name does not match this account — enter the exact name used at registration");
        if (active == 0) return Res.error(403, "Account deactivated");

        // v5.5 DIRECT ENTRY — no TOTP wall on the phone engine.
        // This server runs on the owner's own device at 127.0.0.1 and is invite-only;
        // the authenticator-app enrollment blocked the owner from ever reaching the
        // dashboard. Password + name + email match is the full check here. TOTP stays
        // enabled on the cloud engine only.
        db.getWritableDatabase().execSQL(
                "UPDATE users SET totp_enabled=0 WHERE id=?", new Object[]{uid});
        String token = Auth.token();
        db.getWritableDatabase().execSQL("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                new Object[]{token, uid, System.currentTimeMillis()});
        JSONObject user = new JSONObject().put("id", uid).put("email", email).put("name", storedName);
        Cursor r = db.getReadableDatabase().rawQuery("SELECT role FROM users WHERE id=?", new String[]{String.valueOf(uid)});
        if (r.moveToFirst()) user.put("role", r.getString(0));
        r.close();
        db.log("INFO", "AUTH", "LOGIN", email + " signed in (direct entry)");
        return Res.json(200, new JSONObject().put("ok", true).put("token", token).put("user", user)
                .put("message", "Welcome back — opening the trading engine"));
    }

    private Res verify2fa(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String email = HttpServer.jStr(o, "email").toLowerCase();
        String code = HttpServer.jStr(o, "code");

        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, totp_secret FROM users WHERE email=?", new String[]{email});
        if (!c.moveToFirst()) { c.close(); return Res.error(401, "invalid session"); }
        long uid = c.getLong(0); String secret = c.getString(1);
        c.close();

        if (!Auth.verifyTotp(secret, code)) return Res.error(401, "Invalid or expired code — try the next one");
        db.getWritableDatabase().execSQL("UPDATE users SET totp_enabled=1 WHERE id=?", new Object[]{uid});

        String token = Auth.token();
        db.getWritableDatabase().execSQL("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)",
                new Object[]{token, uid, System.currentTimeMillis()});
        Cursor u = db.getReadableDatabase().rawQuery("SELECT email, name, role FROM users WHERE id=?", new String[]{String.valueOf(uid)});
        JSONObject user = new JSONObject().put("id", uid);
        if (u.moveToFirst()) user.put("email", u.getString(0)).put("name", u.getString(1)).put("role", u.getString(2));
        u.close();
        db.log("INFO", "AUTH", "LOGIN", email + " signed in (2FA verified)");
        return Res.json(200, new JSONObject().put("ok", true).put("token", token).put("user", user));
    }

    /**
     * v5.3 self-service recovery: name + email + master invitation code + new password.
     * Validates the invitation WITHOUT consuming a use, matches name+email against the
     * existing account, resets the password AND returns 2FA to enrollment state so the
     * user re-enrolls with a fresh secret. Local device only — the phone DB is the
     * source of truth for phone-mode accounts.
     */
    private Res resetPassword(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name");
        String email = HttpServer.jStr(o, "email").toLowerCase();
        String invite = HttpServer.jStr(o, "invitationCode");
        String pw = HttpServer.jStr(o, "newPassword");

        if (name.length() < 2) return Res.error(400, "Enter the full name on the account");
        if (!email.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) return Res.error(400, "Enter a valid email address");
        if (pw.length() < 8 || !pw.matches(".*[A-Za-z].*") || !pw.matches(".*[0-9].*"))
            return Res.error(400, "New password must be 8+ characters with letters and numbers");

        // master invite must be valid (no use consumed — recovery is not registration)
        String raw = invite == null ? "" : invite.trim().toUpperCase();
        Cursor ic = db.getReadableDatabase().rawQuery(
                "SELECT active FROM invites WHERE code=?", new String[]{raw});
        boolean valid = ic.moveToFirst() && ic.getInt(0) == 1;
        ic.close();
        if (!valid) return Res.error(403, "Valid invitation code required to reset a password");

        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name FROM users WHERE email=?", new String[]{email});
        if (!c.moveToFirst()) { c.close(); return Res.error(404, "No account found with this email on this device"); }
        long uid = c.getLong(0);
        String storedName = c.getString(1) == null ? "" : c.getString(1).trim().toLowerCase();
        c.close();
        if (!name.trim().toLowerCase().equals(storedName))
            return Res.error(401, "Name does not match this account — enter the exact name used at registration");

        db.getWritableDatabase().execSQL(
                "UPDATE users SET pw_hash=?, totp_enabled=0, totp_secret=? WHERE id=?",
                new Object[]{Auth.hashPw(pw), Auth.totpSecret(), uid});
        db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{uid});
        db.log("INFO", "AUTH", "PASSWORD_RESET", email + " — password reset via invitation code, 2FA re-enrollment required");
        return Res.json(200, new JSONObject().put("ok", true)
                .put("message", "Password changed. Sign in with your new password, then re-enroll 2FA when the setup key is shown."));
    }

    private Res logout(String auth) throws Exception {
        String token = auth != null && auth.startsWith("Bearer ") ? auth.substring(7) : auth;
        if (token != null) db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE token=?", new String[]{token});
        return Res.json(200, new JSONObject().put("ok", true));
    }

    // ================== DATA ENDPOINTS ==================
    private Res dashboard(long uid) throws Exception {
        Cursor a = db.getReadableDatabase().rawQuery(
                "SELECT balance, start_balance, peak, day_start FROM accounts WHERE user_id=?", new String[]{String.valueOf(uid)});
        double bal = 100000, start = 100000, peak = 100000, dayStart = 100000;
        if (a.moveToFirst()) { bal = a.getDouble(0); start = a.getDouble(1); peak = a.getDouble(2); dayStart = a.getDouble(3); }
        a.close();

        Cursor oc = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*), IFNULL(SUM(pnl),0) FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(uid)});
        int openCount = 0; double openPnl = 0;
        if (oc.moveToFirst()) { openCount = oc.getInt(0); openPnl = oc.getDouble(1); }
        oc.close();

        Cursor tc = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*), IFNULL(SUM(pnl),0), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) FROM trades WHERE user_id=? AND status='CLOSED'", new String[]{String.valueOf(uid)});
        int closed = 0; double totalPnl = 0; int wins = 0;
        if (tc.moveToFirst()) { closed = tc.getInt(0); totalPnl = tc.getDouble(1); wins = tc.getInt(2); }
        tc.close();

        // equity sparkline (last 48 points)
        JSONArray eq = new JSONArray();
        Cursor ec = db.getReadableDatabase().rawQuery(
                "SELECT value FROM (SELECT value, ts FROM equity ORDER BY ts DESC LIMIT 48) ORDER BY ts", null);
        while (ec.moveToNext()) eq.put(round2(ec.getDouble(0)));
        ec.close();

        // v5.3: engine can be null if its init failed — dashboard must still load
        JSONObject eng = new JSONObject();
        try { if (engine != null) eng = new JSONObject(engine.status()); } catch (Throwable t) { }

        // v5.7: full identity on the dashboard payload — boot path uses it to restore
        // USER (role drives Control-tab visibility) without a separate /api/me round trip
        Cursor uc = db.getReadableDatabase().rawQuery(
                "SELECT email, name, role FROM users WHERE id=?", new String[]{String.valueOf(uid)});
        JSONObject me = new JSONObject().put("id", uid);
        if (uc.moveToFirst()) me.put("email", uc.getString(0)).put("name", uc.getString(1)).put("role", uc.getString(2));
        uc.close();

        return Res.json(200, new JSONObject()
                .put("balance", round2(bal))
                .put("start", round2(start))
                .put("totalPnl", round2(totalPnl))
                .put("pnlPct", round2((bal - start) / start * 100))
                .put("dayPnlPct", round2((bal - dayStart) / dayStart * 100))
                .put("drawdownPct", round2(peak > 0 ? (bal - peak) / peak * 100 : 0))
                .put("openCount", openCount).put("openPnl", round2(openPnl))
                .put("closedCount", closed).put("winRate", closed > 0 ? round2(wins * 100.0 / closed) : 0)
                .put("equity", eq)
                .put("engine", eng)
                .put("user", me));
    }

    private Res instruments() throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol, exchange, asset_class, status, discovered_at, IFNULL(last_data_at,0), note FROM instruments ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'WATCHING' THEN 1 ELSE 2 END, priority DESC", null);
        int active = 0, watching = 0, pending = 0;
        while (c.moveToNext()) {
            String st = c.getString(3);
            if ("ACTIVE".equals(st)) active++; else if ("WATCHING".equals(st)) watching++; else pending++;
            arr.put(new JSONObject()
                    .put("symbol", c.getString(0)).put("exchange", c.getString(1))
                    .put("assetClass", c.getString(2)).put("status", st)
                    .put("discoveredAt", c.getLong(4)).put("lastDataAt", c.getLong(5))
                    .put("note", c.getString(6)));
        }
        c.close();
        return Res.json(200, new JSONObject()
                .put("instruments", arr).put("active", active).put("watching", watching)
                .put("pending", pending).put("total", arr.length()));
    }

    /** v5.9 — PDF encyclopedia indicator library + live values for one symbol. */
    private static double safeD(double d) { return Double.isNaN(d) || Double.isInfinite(d) ? 0 : d; }

    private Res indicators(String path) throws Exception {
        String symbol = "BTCUSDT";
        int q = path.indexOf("?symbol=");
        if (q > 0) symbol = path.substring(q + 8).toUpperCase().trim();
        if (engine == null) return Res.error(503, "engine not ready");
        Map<String, Object> snap = engine.indicatorSnapshot(symbol);
        snap.remove("library"); // String[][] can't go straight into JSONObject
        JSONObject o = new JSONObject();
        for (Map.Entry<String, Object> e : snap.entrySet()) {
            Object v = e.getValue();
            if (v instanceof double[]) {
                JSONArray a = new JSONArray();
                for (double d : (double[]) v) a.put(safeD(d));
                o.put(e.getKey(), a);
            } else if (v instanceof Object[]) {
                JSONArray a = new JSONArray();
                for (Object d : (Object[]) v) a.put(d == null ? "" : String.valueOf(d));
                o.put(e.getKey(), a);
            } else if (v instanceof Map) {
                JSONObject sub = new JSONObject();
                for (Map.Entry<?, ?> se : ((Map<?, ?>) v).entrySet()) {
                    Object sv = se.getValue();
                    if (sv instanceof Number) sub.put(String.valueOf(se.getKey()), safeD(((Number) sv).doubleValue()));
                    else sub.put(String.valueOf(se.getKey()), String.valueOf(sv));
                }
                o.put(e.getKey(), sub);
            } else if (v instanceof Number) {
                o.put(e.getKey(), safeD(((Number) v).doubleValue()));
            } else if (v instanceof Boolean) {
                o.put(e.getKey(), (Boolean) v);
            } else {
                o.put(e.getKey(), String.valueOf(v));
            }
        }
        JSONArray lib = new JSONArray();
        for (String[] row : EngineCore.INDICATOR_LIBRARY) {
            lib.put(new JSONArray().put(row[0]).put(row[1]).put(row[2]));
        }
        o.put("library", lib);
        return Res.json(200, o);
    }

    private Res news() throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts, source, headline, sentiment, impact FROM news ORDER BY id DESC LIMIT 60", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject().put("ts", c.getLong(0)).put("source", c.getString(1))
                    .put("headline", c.getString(2)).put("sentiment", c.getString(3)).put("impact", c.getString(4)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("news", arr)
                .put("pauseActive", System.currentTimeMillis() < enginePauseUntil()));
    }

    private long enginePauseUntil() {
        try {
            if (engine == null) return 0;
            JSONObject st = new JSONObject(engine.status());
            return st.optBoolean("news_pause") ? System.currentTimeMillis() + 1000 : 0;
        } catch (Throwable t) { return 0; }
    }

    private Res trades(long uid) throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, symbol, side, qty, entry, sl, tp, exit, pnl, status, strategy, consensus, opened_at, closed_at FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 100", new String[]{String.valueOf(uid)});
        while (c.moveToNext()) {
            arr.put(new JSONObject()
                    .put("id", c.getLong(0)).put("symbol", c.getString(1)).put("side", c.getString(2))
                    .put("qty", c.getDouble(3)).put("entry", c.getDouble(4)).put("sl", c.getDouble(5))
                    .put("tp", c.getDouble(6)).put("exit", c.isNull(7) ? JSONObject.NULL : c.getDouble(7))
                    .put("pnl", c.isNull(8) ? JSONObject.NULL : round2(c.getDouble(8)))
                    .put("status", c.getString(9)).put("strategy", c.getString(10))
                    .put("consensus", c.getDouble(11)).put("openedAt", c.getLong(12))
                    .put("closedAt", c.isNull(13) ? 0 : c.getLong(13)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("trades", arr));
    }

    private Res logs() throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT ts, level, component, event, details FROM logs ORDER BY id DESC LIMIT 150", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject().put("ts", c.getLong(0)).put("level", c.getString(1))
                    .put("component", c.getString(2)).put("event", c.getString(3)).put("details", c.getString(4)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("logs", arr));
    }

    private Res brokers() throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name, kind, status, added_at FROM brokers ORDER BY id DESC", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject().put("id", c.getLong(0)).put("name", c.getString(1))
                    .put("kind", c.getString(2)).put("status", c.getString(3)).put("addedAt", c.getLong(4)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("brokers", arr));
    }

    private Res addBroker(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name");
        String kind = HttpServer.jStr(o, "kind");
        String key = HttpServer.jStr(o, "apiKey");
        String secret = HttpServer.jStr(o, "apiSecret");
        String login = HttpServer.jStr(o, "login");
        String pw = HttpServer.jStr(o, "password");

        if (name.length() < 2) return Res.error(400, "Enter a broker name");
        if (key.length() < 8) return Res.error(400, "Enter the API key from your broker");
        db.getWritableDatabase().execSQL(
                "INSERT INTO brokers(name, kind, api_key, api_secret, login, password, status, added_at) VALUES(?,?,?,?,?,?, 'SAVED', ?)",
                new Object[]{name, kind.isEmpty() ? "CUSTOM" : kind, key, secret, login, pw, System.currentTimeMillis()});
        db.log("INFO", "BROKER", "ADDED", name + " (" + kind + ") — credentials saved, will connect at live trading phase");
        return Res.json(200, new JSONObject().put("ok", true)
                .put("message", "Broker saved. Credentials are stored on this device — the engine will connect it when you enable live trading."));
    }

    private Res testBroker(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name");
        return Res.json(200, new JSONObject().put("ok", true)
                .put("message", name + " credentials verified as SAVED (local storage). Live connection test happens when live trading is enabled — this build runs paper trading only."));
    }

    private Res closeTrade(long uid, String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        long id = o.optLong("id", -1);
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT qty, entry, side FROM trades WHERE id=? AND user_id=? AND status='OPEN'", new String[]{String.valueOf(id), String.valueOf(uid)});
        if (!c.moveToFirst()) { c.close(); return Res.error(404, "trade not found"); }
        double qty = c.getDouble(0), entry = c.getDouble(1); String side = c.getString(2);
        c.close();
        Cursor cc = db.getReadableDatabase().rawQuery(
                "SELECT c FROM (SELECT c FROM candles WHERE symbol=(SELECT symbol FROM trades WHERE id=?) ORDER BY ts DESC LIMIT 1)", new String[]{String.valueOf(id)});
        double price = cc.moveToFirst() ? cc.getDouble(0) : entry; cc.close();
        double pnl = ("BUY".equals(side) ? price - entry : entry - price) * qty;
        db.getWritableDatabase().execSQL("UPDATE trades SET exit=?, pnl=?, status='CLOSED', closed_at=? WHERE id=?",
                new Object[]{price, pnl, System.currentTimeMillis(), id});
        db.getWritableDatabase().execSQL("UPDATE accounts SET balance=balance+? WHERE user_id=?", new Object[]{pnl, uid});
        db.log("INFO", "EXECUTOR", "MANUAL_CLOSE", "trade #" + id + " closed by user, pnl=" + String.format(Locale.US, "%.2f", pnl));
        return Res.json(200, new JSONObject().put("ok", true).put("pnl", round2(pnl)));
    }

    private Res settings() throws Exception {
        return Res.json(200, new JSONObject()
                .put("engineOn", "1".equals(db.setting("engine_on", "1")))
                .put("version", "5.8.0"));
    }

    private Res saveSettings(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        if (o.has("engineOn")) {
            boolean on = o.optBoolean("engineOn");
            db.setSetting("engine_on", on ? "1" : "0");
            db.log("INFO", "SYSTEM", on ? "ENGINE_ENABLED" : "ENGINE_DISABLED", "user toggled engine");
        }
        return settings();
    }

    // ================== v5.7 FULL MOBILE CONTROL (owner admin) ==================

    /** Admin guard — only an active ADMIN-role account may use control endpoints. */
    private boolean isAdmin(long uid) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT role FROM users WHERE id=? AND active=1", new String[]{String.valueOf(uid)});
        boolean ok = c.moveToFirst() && "ADMIN".equals(c.getString(0));
        c.close();
        return ok;
    }

    private Res adminGuard(long uid) {
        return isAdmin(uid) ? null : Res.error(403, "Admin access required — owner account only");
    }

    /** GET /api/admin/users — full user register for the owner. */
    private Res adminUsers(long uid) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name, email, role, active, created_at, (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id) FROM users u ORDER BY id", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject()
                    .put("id", c.getLong(0)).put("name", c.getString(1))
                    .put("email", c.getString(2)).put("role", c.getString(3))
                    .put("active", c.getInt(4)).put("createdAt", c.getLong(5))
                    .put("sessions", c.getInt(6)));
        }
        c.close();
        Cursor sc = db.getReadableDatabase().rawQuery("SELECT COUNT(*), IFNULL(SUM(active),0) FROM users", null);
        int total = 0, activeUsers = 0;
        if (sc.moveToFirst()) { total = sc.getInt(0); activeUsers = sc.getInt(1); }
        sc.close();
        return Res.json(200, new JSONObject().put("users", arr)
                .put("total", total).put("activeUsers", activeUsers));
    }

    /** POST /api/admin/users — {id, action: activate|deactivate|delete}. */
    private Res adminUserAction(long uid, String body) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONObject o = HttpServer.jObj(body);
        long id = o.optLong("id", -1);
        String action = HttpServer.jStr(o, "action");
        if (id <= 0) return Res.error(400, "User id required");

        if ("activate".equals(action) || "deactivate".equals(action)) {
            if (id == uid) return Res.error(400, "You cannot deactivate your own owner account");
            boolean on = "activate".equals(action);
            Cursor ec = db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE id=?", new String[]{String.valueOf(id)});
            boolean exists = ec.moveToFirst(); ec.close();
            if (!exists) return Res.error(404, "User not found");
            db.getWritableDatabase().execSQL("UPDATE users SET active=? WHERE id=?", new Object[]{on ? 1 : 0, id});
            if (!on) db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{id});
            db.log("INFO", "ADMIN", on ? "USER_ENABLED" : "USER_DISABLED", "user #" + id + " " + action + "d by owner");
            return Res.json(200, new JSONObject().put("ok", true)
                    .put("message", on ? "User enabled — they can sign in again" : "User disabled — all their sessions ended"));
        }

        if ("delete".equals(action)) {
            if (id == uid) return Res.error(400, "You cannot delete your own owner account");
            Cursor rc = db.getReadableDatabase().rawQuery("SELECT role, name FROM users WHERE id=?", new String[]{String.valueOf(id)});
            if (!rc.moveToFirst()) { rc.close(); return Res.error(404, "User not found"); }
            String role = rc.getString(0), name = rc.getString(1); rc.close();
            if ("ADMIN".equals(role)) {
                Cursor ac = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND active=1", null);
                int admins = ac.moveToFirst() ? ac.getInt(0) : 0; ac.close();
                if (admins <= 1) return Res.error(400, "Cannot delete the last admin account");
            }
            db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{id});
            db.getWritableDatabase().execSQL("DELETE FROM accounts WHERE user_id=?", new Object[]{id});
            db.getWritableDatabase().execSQL("DELETE FROM trades WHERE user_id=?", new Object[]{id});
            db.getWritableDatabase().execSQL("DELETE FROM users WHERE id=?", new Object[]{id});
            db.log("INFO", "ADMIN", "USER_DELETED", name + " (#" + id + ") deleted by owner — sessions, paper account, trades removed");
            return Res.json(200, new JSONObject().put("ok", true).put("message", name + " deleted permanently"));
        }
        return Res.error(400, "Unknown action");
    }

    /** GET /api/admin/invites — all invitation codes with usage. */
    private Res adminInvites(long uid) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT code, label, max_uses, uses, active FROM invites ORDER BY active DESC, code", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject().put("code", c.getString(0)).put("label", c.getString(1))
                    .put("maxUses", c.getInt(2)).put("uses", c.getInt(3)).put("active", c.getInt(4)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("invites", arr).put("total", arr.length()));
    }

    /** POST /api/admin/invites — {action: create|revoke|activate}. */
    private Res adminInviteAction(long uid, String body) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONObject o = HttpServer.jObj(body);
        String action = HttpServer.jStr(o, "action");

        if ("create".equals(action)) {
            String label = HttpServer.jStr(o, "label");
            int maxUses = o.optInt("maxUses", 0);
            if (maxUses < 0) maxUses = 0;
            if (label.isEmpty()) label = "Owner invite — " + new java.text.SimpleDateFormat("MMM d", Locale.US).format(new java.util.Date());
            String code = null;
            for (int t = 0; t < 5 && code == null; t++) {
                String cand = Auth.newInviteCode();
                Cursor cc = db.getReadableDatabase().rawQuery("SELECT code FROM invites WHERE code=?", new String[]{cand});
                boolean taken = cc.moveToFirst(); cc.close();
                if (!taken) code = cand;
            }
            if (code == null) return Res.error(500, "Could not generate a unique code — try again");
            db.getWritableDatabase().execSQL(
                    "INSERT OR IGNORE INTO invites(code, label, max_uses, uses, active) VALUES(?,?,?,0,1)",
                    new Object[]{code, label, maxUses});
            db.log("INFO", "ADMIN", "INVITE_CREATED", code + " created by owner — " + label + (maxUses > 0 ? " (max " + maxUses + ")" : " (unlimited)"));
            return Res.json(200, new JSONObject().put("ok", true).put("code", code)
                    .put("message", "Naya invite code ban gaya: " + code));
        }

        String code = HttpServer.jStr(o, "code").trim().toUpperCase();
        if (code.isEmpty()) return Res.error(400, "Invite code required");
        if ("revoke".equals(action)) {
            db.getWritableDatabase().execSQL("UPDATE invites SET active=0 WHERE code=?", new Object[]{code});
            db.log("INFO", "ADMIN", "INVITE_REVOKED", code + " revoked by owner — registrations with it now fail");
            return Res.json(200, new JSONObject().put("ok", true).put("message", code + " revoked — is code se ab koi register nahi kar sakta"));
        }
        if ("activate".equals(action)) {
            db.getWritableDatabase().execSQL("UPDATE invites SET active=1 WHERE code=?", new Object[]{code});
            db.log("INFO", "ADMIN", "INVITE_ENABLED", code + " re-enabled by owner");
            return Res.json(200, new JSONObject().put("ok", true).put("message", code + " enabled again"));
        }
        return Res.error(400, "Unknown action");
    }

    /** GET /api/admin/alerts — in-app alert feed (latest 100) + unread count. */
    private Res adminAlerts(long uid) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, kind, title, body, meta, read, created_at FROM notifications ORDER BY id DESC LIMIT 100", null);
        while (c.moveToNext()) {
            JSONObject n = new JSONObject();
            n.put("id", c.getLong(0)).put("kind", c.getString(1)).put("title", c.getString(2))
                    .put("body", c.getString(3)).put("read", c.getInt(5)).put("createdAt", c.getLong(6));
            try { n.put("meta", new JSONObject(c.getString(4))); } catch (Throwable t) { n.put("meta", new JSONObject()); }
            arr.put(n);
        }
        c.close();
        Cursor uc = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM notifications WHERE read=0", null);
        int unread = uc.moveToFirst() ? uc.getInt(0) : 0; uc.close();
        return Res.json(200, new JSONObject().put("alerts", arr).put("unreadCount", unread));
    }

    /** POST /api/admin/alerts — {action: read-all | read | clear} (+ optional id). */
    private Res adminAlertAction(long uid, String body) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONObject o = HttpServer.jObj(body);
        String action = HttpServer.jStr(o, "action");
        if ("read-all".equals(action)) {
            db.getWritableDatabase().execSQL("UPDATE notifications SET read=1 WHERE read=0");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Saare alerts parh liye gaye"));
        }
        if ("read".equals(action)) {
            long id = o.optLong("id", -1);
            if (id > 0) db.getWritableDatabase().execSQL("UPDATE notifications SET read=1 WHERE id=?", new Object[]{id});
            return Res.json(200, new JSONObject().put("ok", true));
        }
        if ("clear".equals(action)) {
            db.getWritableDatabase().execSQL("DELETE FROM notifications WHERE read=1");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Read alerts cleared"));
        }
        return Res.error(400, "Unknown action");
    }

    static double round2(double v) { return Math.round(v * 100.0) / 100.0; }
}
