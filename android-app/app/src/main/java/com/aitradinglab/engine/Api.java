package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import java.util.Locale;
import java.util.List;
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
    private String query = ""; // v1.2 — raw query string for /api/history/csv?y=...&m=...

    public Res route(String method, String rawPath, String authHeader, String body) {
        String path = rawPath;
        int q = path.indexOf('?');
        if (q >= 0) { query = path.substring(q + 1); path = path.substring(0, q); } else query = "";
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
                .put("ok", true).put("engine", "ai-trading-lab-phone").put("device", android.os.Build.MANUFACTURER + " " + android.os.Build.MODEL).put("android", android.os.Build.VERSION.SDK_INT).put("version", "3.0.0").put("timeframe", "5m").put("scanner", "24h").put("strategy", "3C Breakout (M5) — MASTER + QUANT PRO stack + HALAL MT5"));

        Long uid = userId(auth);
        if (uid == null) return Res.error(401, "authentication required");

        if ("/api/dashboard".equals(path)) return dashboard(uid);
        if ("/api/instruments".equals(path)) return instruments();
        if (path.startsWith("/api/indicators")) return indicators(path);
        if ("/api/news".equals(path)) return news();
        if ("/api/trades".equals(path)) return trades(uid);
        if ("/api/strategies".equals(path)) {   // v1.2 Strategy Lab listing
            if (engine == null || engine.lab == null) return Res.error(503, "Lab shuru ho raha hai — refresh karein");
            return Res.json(200, engine.lab.listStrategies());
        }
        if ("/api/history".equals(path)) return history(uid);            // v1.2 year→month→day archive
        if ("/api/history/csv".equals(path)) return historyCsv(uid);     // v1.2 month CSV export
        if ("/api/logs".equals(path)) return logs();
        if ("/api/brokers".equals(path)) return brokers();
        if ("/api/settings".equals(path)) return settings();
        if (path.startsWith("/api/candles")) return candles(path, uid == null ? 0 : uid);   // v1.8 chart (v3.0 + trade overlay)
        if ("/api/analytics".equals(path)) return analytics(uid);    // v3.0 EDGE ANALYTICS
        if (path.startsWith("/api/seasonality")) return seasonality(path);  // v3.0 seasonal edge
        if ("/api/audit.csv".equals(path)) return auditCsv(uid);     // v3.0 audit trail export
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
        if ("/api/settings".equals(path)) return saveSettings(uid, body);
        // v1.2 — owner ka apna paper amount: set ANY paper balance
        if ("/api/balance".equals(path)) return setBalance(uid, body);
        // v1.2 Strategy Lab — add/compile/watch/backtest/paper/approve
        if ("/api/strategies".equals(path)) {
            if (engine == null || engine.lab == null) return Res.error(503, "Lab shuru ho raha hai — refresh karein");
            return strategyAction(engine.lab, body);
        }
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
        // v1.9 OWNER GATE — sirf pehla account kabhi ADMIN banta hai (owner);
        // baaki SAB registrations TRADER + approved=0 (PENDING) — owner ke APPROVE
        // karne ke baad hi login possible. Second admin ban hi nahi sakta.
        String role = first ? "ADMIN" : "TRADER";
        int approved = first ? 1 : 0;
        // v2.1 OWNER TRADING GATE — registration approve hone ke baad bhi TRADING tabhi
        // chalegi jab owner Control > Users me ENABLE TRADING dabaye. Owner khud auto-on.
        int tradeOk = first ? 1 : 0;

        String secret = Auth.totpSecret();
        db.getWritableDatabase().execSQL(
                "INSERT INTO users(email, name, pw_hash, role, totp_secret, totp_enabled, active, approved, trade_ok, created_at) VALUES(?,?,?,?,?,0,1,?,?,?)",
                new Object[]{email, name, Auth.hashPw(pw), role, secret, approved, tradeOk, System.currentTimeMillis()});
        Cursor nc = db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE email=?", new String[]{email});
        long uid = nc.moveToFirst() ? nc.getLong(0) : -1; nc.close();
        db.getWritableDatabase().execSQL(
                "INSERT OR IGNORE INTO accounts(user_id, balance, start_balance, peak, day_start, day_ts) VALUES(?,100,100,100,100,?)",
                new Object[]{uid, System.currentTimeMillis() / 86400000L});
        db.log("INFO", "AUTH", "REGISTER", email + " (" + role + ") — account created, " + (first ? "owner (auto-approved)" : "PENDING owner approval"));
        // v1.9 — owner ko alert TEEN tareeqon se, foran:
        //   1) persistent in-app row (Control tab feed — reboots survive karta hai)
        //   2) high-importance status-bar notification (Notifier)
        //   3) system ledger entry (log above)
        // PENDING registration par approval bhi Home par banner banta hai.
        String code = invite == null ? "" : invite.trim().toUpperCase();
        String alertBody = first
                ? name + " (" + email + ") OWNER account ban gaya — role ADMIN (auto-approved, trading enabled)"
                : "APPROVAL ZAROORI — " + name + " (" + email + ") ne invite code " + code
                        + " se register kiya · role TRADER · Control > Users me APPROVE dabayen (tabhi login hoga) · uske baad ENABLE TRADING bhi dabayen (tabhi trade karega)";
        try {
            String meta = new JSONObject().put("email", email).put("name", name)
                    .put("invite", code).put("role", role).put("pending", first ? 0 : 1).toString();
            db.getWritableDatabase().execSQL(
                    "INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('REGISTER',?,?,?,0,?)",
                    new Object[]{first ? "Owner account created — " + name : "New registration — APPROVE karein: " + name,
                            alertBody, meta, System.currentTimeMillis()});
        } catch (Throwable ignored) { /* feed row is best-effort — registration must succeed */ }
        Notifier.registration(appCtx, name, email, role, code, first);
        return Res.json(200, new JSONObject().put("ok", true)
                .put("pending", first ? 0 : 1)
                .put("message", first
                        ? "Owner account created. Sign in karein — dashboard foran khulega."
                        : "Registration submitted! Owner ko notification chala gaya — wo APPROVE karega, phir ENABLE TRADING karega. Uske baad aap sign in karke trade kar sakenge."));
    }

    private Res login(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name").toLowerCase();
        String email = HttpServer.jStr(o, "email").toLowerCase();
        String pw = HttpServer.jStr(o, "password");

        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name, pw_hash, active, totp_enabled, totp_secret, approved FROM users WHERE email=?", new String[]{email});
        if (!c.moveToFirst()) {
            c.close();
            // v5.9.1 — fresh-install guidance: if this device has NO accounts at all,
            // the user is looking at a wiped/reinstalled app, not a wrong password.
            Cursor cnt = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
            boolean noAccounts = cnt.moveToFirst() && cnt.getInt(0) == 0; cnt.close();
            if (noAccounts) return Res.error(401,
                    "Is device par abhi koi account nahi hai (naya install). Pehle REGISTER tab se account banayen (invite code owner se lein), phir sign in karein.");
            return Res.error(401, "Invalid email or password — ya name match nahi hua. Exact wahi name aur email likhein jo registration par use hua tha.");
        }
        long uid = c.getLong(0);
        String storedName = c.getString(1) == null ? "" : c.getString(1).trim().toLowerCase();
        String hash = c.getString(2);
        int active = c.getInt(3), totpEnabled = c.getInt(4);
        String secret = c.getString(5);
        int approved = c.getInt(6);
        c.close();

        if (!Auth.verifyPw(pw, hash)) return Res.error(401, "Invalid email or password");
        if (name.isEmpty() || !name.equals(storedName))
            return Res.error(401, "Name does not match this account — enter the exact name used at registration");
        if (active == 0) return Res.error(403, "Account deactivated");
        // v1.9 OWNER GATE — PENDING registration login NAHI kar sakta jab tak owner
        // APPROVE na kare. Owner ko dobara notification bhi jata hai (best-effort).
        if (approved == 0) {
            Notifier.post(appCtx, "Approval pending — " + storedName,
                    storedName + " (" + email + ") login karne ki koshish kar raha hai lekin abhi PENDING hai. Settings > Control > Users me APPROVE dabayen.");
            try {
                db.getWritableDatabase().execSQL(
                        "INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('PENDING_LOGIN',?,?,?,0,?)",
                        new Object[]{"PENDING user login try kar raha hai: " + storedName,
                                storedName + " (" + email + ") ne login try kiya — account abhi bhi approval ka intezar kar raha hai. Control > Users me APPROVE karein.",
                                "{}", System.currentTimeMillis()});
            } catch (Throwable ignored) { }
            db.log("INFO", "AUTH", "LOGIN_BLOCKED_PENDING", email + " — login refused, owner approval chahiye");
            return Res.error(403, "Account PENDING approval — owner ne abhi approve nahi kiya. Registration par owner ko notification chala hai; jaise hi wo APPROVE karega, aap sign in kar sakenge.");
        }

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
        if (!c.moveToFirst()) {
            c.close();
            Cursor cnt = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
            boolean noAccounts = cnt.moveToFirst() && cnt.getInt(0) == 0; cnt.close();
            if (noAccounts) return Res.error(404,
                    "No account found with this email on this device — naya install hai, is liye purana account maujood nahi. REGISTER tab se pehle account banayen.");
            return Res.error(404, "No account found with this email on this device — email check karein ya REGISTER tab se account banayen.");
        }
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
        double bal = 100, start = 100, peak = 100, dayStart = 100;
        if (a.moveToFirst()) { bal = a.getDouble(0); start = a.getDouble(1); peak = a.getDouble(2); dayStart = a.getDouble(3); }
        a.close();

        Cursor oc = db.getReadableDatabase().rawQuery(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(uid)});
        int openCount = 0;
        if (oc.moveToFirst()) openCount = oc.getInt(0);
        oc.close();

        // v1.6 — REAL-TIME floating P/L: OPEN trades ka unrealized profit/loss live price
        // par (latest candle close — live candle included, engine har 10s refresh karta hai).
        // Owner request: "kitna plus mein trades ja rahi hai ya loss — zyada loss avoid kar pao".
        double openPnl = 0;
        Cursor fc = db.getReadableDatabase().rawQuery(
                "SELECT symbol, side, qty, entry FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(uid)});
        while (fc.moveToNext()) {
            double price = livePrice(fc.getString(0));
            if (Double.isNaN(price)) continue;
            double qty = fc.getDouble(2), entry = fc.getDouble(3);
            openPnl += ("BUY".equals(fc.getString(1)) ? price - entry : entry - price) * qty;
        }
        fc.close();

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
        // v1.3 24/7 — battery-optimization status: engine exemption ke baghair OEM
        // (One UI etc.) process sula deta hai. Dashboard Home iska RED banner dikhata hai.
        try {
            android.os.PowerManager pm = (android.os.PowerManager) appCtx.getSystemService(android.content.Context.POWER_SERVICE);
            eng.put("battery_ok", pm != null && pm.isIgnoringBatteryOptimizations(appCtx.getPackageName()));
        } catch (Throwable t) { eng.put("battery_ok", true); }
        try { eng.put("watchdog", "9-min Doze-safe alarm + thread watchdog + swipe-kill restart"); } catch (Throwable t) { }

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
                // v3.0 — peak ab ratchet hota hai (true HWM drawdown) + portfolio heat + bucket exposure
                .put("trueDD", true)
                .put("heat", round2(engine != null ? engine.heatRiskPct(uid) : 0))
                .put("heatCap", engine != null ? engine.heatMaxPct() : 0)
                .put("exposure", new JSONObject()
                        .put("METAL", round2(engine != null ? engine.bucketRiskPct(uid, "METAL") : 0))
                        .put("ENERGY", round2(engine != null ? engine.bucketRiskPct(uid, "ENERGY") : 0))
                        .put("AGRI", round2(engine != null ? engine.bucketRiskPct(uid, "AGRI") : 0)))
                .put("safeMode", engine != null && engine.isSafeMode())
                .put("openCount", openCount).put("openPnl", round2(openPnl))
                .put("equityNow", round2(bal + openPnl))
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

    /** v1.6 — latest price for a symbol: most recent candle close (live candle included). */
    private double livePrice(String sym) {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT c FROM candles WHERE symbol=? AND tf='5m' ORDER BY ts DESC LIMIT 1", new String[]{sym});
        double p = Double.NaN;
        if (c.moveToFirst()) p = c.getDouble(0);
        c.close();
        return p;
    }

    private Res trades(long uid) throws Exception {
        JSONArray arr = new JSONArray();
        double floating = 0; int fCount = 0;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, symbol, side, qty, entry, sl, tp, exit, pnl, status, strategy, consensus, opened_at, closed_at, IFNULL(r_mult,0), IFNULL(mfe,0), IFNULL(mae,0), IFNULL(tca_bps,0), IFNULL(council,0), IFNULL(win_prob,0) FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 100", new String[]{String.valueOf(uid)});
        while (c.moveToNext()) {
            String status = c.getString(9);
            JSONObject t = new JSONObject()
                    .put("id", c.getLong(0)).put("symbol", c.getString(1)).put("side", c.getString(2))
                    .put("qty", c.getDouble(3)).put("entry", c.getDouble(4)).put("sl", c.getDouble(5))
                    .put("tp", c.getDouble(6)).put("exit", c.isNull(7) ? JSONObject.NULL : c.getDouble(7))
                    .put("pnl", c.isNull(8) ? JSONObject.NULL : round2(c.getDouble(8)))
                    .put("status", status).put("strategy", c.getString(10))
                    .put("consensus", c.getDouble(11)).put("openedAt", c.getLong(12))
                    .put("closedAt", c.isNull(13) ? 0 : c.getLong(13))
                    // v3.0 — QUANT PRO journal columns (R-multiple, MFE/MAE, TCA, council, ML)
                    .put("rMult", c.getDouble(14)).put("mfe", round2(c.getDouble(15)))
                    .put("mae", round2(c.getDouble(16))).put("tcaBps", c.getDouble(17))
                    .put("council", c.getInt(18)).put("winProb", c.getDouble(19));
            // v1.6 — OPEN trade par LIVE price + unrealized P/L (+ R multiple for 3C trades):
            // abhi ka plus/minus dikhe to owner bada loss hone se pehle react kar sake.
            if ("OPEN".equals(status)) {
                double price = livePrice(c.getString(1));
                if (!Double.isNaN(price)) {
                    double qty = c.getDouble(3), entry = c.getDouble(4), tp = c.getDouble(6);
                    double pl = ("BUY".equals(c.getString(2)) ? price - entry : entry - price) * qty;
                    t.put("price", price).put("pnlLive", round2(pl));
                    floating += pl; fCount++;
                    String strat = c.getString(10);
                    if (strat != null && strat.startsWith("3C")) {
                        double rDist = Math.abs(tp - entry) / 3.0;
                        if (rDist > 0 && qty > 0) t.put("rNow", Math.round(pl / (rDist * qty) * 100.0) / 100.0);
                    }
                }
            }
            arr.put(t);
        }
        c.close();
        return Res.json(200, new JSONObject().put("trades", arr)
                .put("floating", round2(floating)).put("floatingCount", fCount));
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

    // ================== v3.0 EDGE ANALYTICS (FreqUI + Jesse + LEAN patterns) ==================

    /** GET /api/analytics — daily P&L (30d), per-symbol table, monthly heatmap,
     *  R-multiple histogram, fee drag — dashboard Insights cards ka data. */
    private Res analytics(long uid) throws Exception {
        // 1) Daily P&L last 30 days (FreqUI Profit page pattern)
        JSONArray daily = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT CAST(closed_at/86400000 AS INTEGER) d, SUM(pnl), COUNT(*) FROM trades "
                        + "WHERE user_id=? AND status='CLOSED' AND closed_at >= ? GROUP BY d ORDER BY d",
                new String[]{String.valueOf(uid), String.valueOf(System.currentTimeMillis() - 30L * 86400000)});
        while (c.moveToNext())
            daily.put(new JSONObject().put("day", c.getLong(0)).put("pnl", round2(c.getDouble(1))).put("n", c.getInt(2)));
        c.close();
        // 2) Per-symbol performance table (FreqUI Performance page pattern)
        JSONArray syms = new JSONArray();
        Cursor cs = db.getReadableDatabase().rawQuery(
                "SELECT symbol, COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), IFNULL(SUM(pnl),0), "
                        + "IFNULL(SUM(CASE WHEN pnl>0 THEN pnl ELSE 0 END),0), IFNULL(SUM(CASE WHEN pnl<=0 THEN -pnl ELSE 0 END),0), "
                        + "IFNULL(AVG(closed_at-opened_at),0), IFNULL(AVG(r_mult),0) FROM trades "
                        + "WHERE user_id=? AND status='CLOSED' GROUP BY symbol ORDER BY SUM(pnl) DESC", new String[]{String.valueOf(uid)});
        while (cs.moveToNext()) {
            int n = cs.getInt(1); int w = cs.getInt(2);
            double gl = cs.getDouble(5);
            syms.put(new JSONObject().put("symbol", cs.getString(0)).put("n", n).put("wins", w)
                    .put("winrate", n > 0 ? Math.round(w * 1000.0 / n) / 10.0 : 0)
                    .put("net", round2(cs.getDouble(3)))
                    .put("pf", gl > 0 ? Math.round(cs.getDouble(4) / gl * 100.0) / 100.0 : (cs.getDouble(4) > 0 ? 99 : 0))
                    .put("avgMin", Math.round(cs.getDouble(6) / 60000.0)).put("avgR", Math.round(cs.getDouble(7) * 1000.0) / 1000.0));
        }
        cs.close();
        // 3) Monthly heatmap (Jesse pattern): year×month net
        java.util.Map<String, JSONObject> months = new java.util.LinkedHashMap<>();
        Cursor cm = db.getReadableDatabase().rawQuery(
                "SELECT CAST(closed_at/86400000 AS INTEGER) d, SUM(pnl) FROM trades "
                        + "WHERE user_id=? AND status='CLOSED' GROUP BY d", new String[]{String.valueOf(uid)});
        java.util.Map<String, Double> mSum = new java.util.LinkedHashMap<>();
        while (cm.moveToNext()) {
            java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
            cal.setTimeInMillis(cm.getLong(0) * 86400000L);
            String key = cal.get(java.util.Calendar.YEAR) + "-" + String.format(Locale.US, "%02d", cal.get(java.util.Calendar.MONTH) + 1);
            mSum.merge(key, cm.getDouble(1), Double::sum);
        }
        cm.close();
        for (java.util.Map.Entry<String, Double> e : mSum.entrySet())
            months.put(e.getKey(), new JSONObject().put("month", e.getKey()).put("pnl", round2(e.getValue())));
        // 4) R-multiple histogram (professional journal) — buckets -3..+4+
        int[] rBuckets = new int[9];   // <-3, -3..-2, -2..-1, -1..0, 0..1, 1..2, 2..3, 3..4, 4+
        Cursor cr = db.getReadableDatabase().rawQuery(
                "SELECT r_mult FROM trades WHERE user_id=? AND status='CLOSED' AND r_mult != 0", new String[]{String.valueOf(uid)});
        while (cr.moveToNext()) {
            double r = cr.getDouble(0);
            int b = r < -3 ? 0 : r < -2 ? 1 : r < -1 ? 2 : r < 0 ? 3 : r < 1 ? 4 : r < 2 ? 5 : r < 3 ? 6 : r < 4 ? 7 : 8;
            rBuckets[b]++;
        }
        cr.close();
        JSONArray rh = new JSONArray();
        for (int v : rBuckets) rh.put(v);
        // 5) Fee drag + TCA aggregate
        Cursor cf = db.getReadableDatabase().rawQuery(
                "SELECT IFNULL(SUM((qty*entry+qty*exit)*0.0005),0), IFNULL(AVG(tca_bps),0), COUNT(*) FROM trades WHERE user_id=? AND status='CLOSED'", new String[]{String.valueOf(uid)});
        double feeTotal = 0, avgTca = 0; int nAll = 0;
        if (cf.moveToFirst()) { feeTotal = cf.getDouble(0); avgTca = cf.getDouble(1); nAll = cf.getInt(2); }
        cf.close();
        return Res.json(200, new JSONObject().put("ok", true)
                .put("daily", daily).put("symbols", syms)
                .put("monthly", new JSONArray(months.values()))
                .put("rHist", rh)
                .put("fees", round2(feeTotal)).put("avgTcaBps", Math.round(avgTca * 100.0) / 100.0).put("nClosed", nAll));
    }

    /** GET /api/seasonality?symbol=XAUUSD — 5y monthly seasonal edge (seasonality.ai pattern). */
    private Res seasonality(String path) throws Exception {
        String sym = "XAUUSD";
        int q = path.indexOf("?symbol=");
        if (q > 0) sym = path.substring(q + 8).toUpperCase(Locale.US).trim();
        if (!sym.matches("[A-Z0-9]{4,20}")) return Res.error(400, "Symbol galat");
        if (engine == null) return Res.error(503, "engine band hai");
        JSONObject se = engine.seasonality(sym, q > 0 && path.contains("refresh=1"));
        if (se == null) return Res.error(503, "Seasonality data abhi fetch nahi hua — dobara try karein");
        return Res.json(200, new JSONObject().put("ok", true).put("seasonality", se));
    }

    /** GET /api/audit.csv — full audit trail export (trades + orders) — LIVE READY compliance. */
    private Res auditCsv(long uid) throws Exception {
        StringBuilder sb = new StringBuilder("type,id,trade_id,symbol,side,qty_or_status,price,source_or_entry,status_or_exit,ts\n");
        Cursor t = db.getReadableDatabase().rawQuery(
                "SELECT id, symbol, side, qty, entry, exit, pnl, status, strategy, opened_at, closed_at, IFNULL(r_mult,0), IFNULL(tca_bps,0) FROM trades WHERE user_id=? ORDER BY id", new String[]{String.valueOf(uid)});
        while (t.moveToNext()) {
            sb.append("TRADE,").append(t.getLong(0)).append(",").append(t.getLong(0)).append(',').append(t.getString(1))
                    .append(',').append(t.getString(2)).append(',').append(t.getDouble(3)).append(',')
                    .append(t.getDouble(4)).append(',').append(t.getString(7)).append(',')
                    .append(t.isNull(5) ? "" : t.getDouble(5)).append(',').append(t.isNull(6) ? 0 : t.getDouble(6))
                    .append(",").append(t.getString(8)).append(',').append(t.getLong(9)).append(',')
                    .append(t.isNull(10) ? 0 : t.getLong(10)).append(',').append(t.getDouble(11)).append(',').append(t.getDouble(12)).append('\n');
        }
        t.close();
        Cursor o = db.getReadableDatabase().rawQuery(
                "SELECT id, trade_id, symbol, side, type, price, qty, status, source, ts FROM orders ORDER BY id", null);
        while (o.moveToNext()) {
            sb.append("ORDER,").append(o.getLong(0)).append(',').append(o.getLong(1)).append(',').append(o.getString(2))
                    .append(',').append(o.getString(3)).append(',').append(o.getString(8)).append(',')
                    .append(o.getDouble(5)).append(',').append(o.getDouble(6)).append(',')
                    .append(o.getString(4)).append(',').append(o.getString(7)).append(',').append(o.getLong(9)).append('\n');
        }
        o.close();
        Res r = new Res();
        r.contentType = "text/csv; charset=utf-8";
        r.body = sb.toString();
        db.log("INFO", "AUDIT", "AUDIT_EXPORT", "user #" + uid + " — full audit trail (trades + orders) exported");
        return r;
    }

    private Res brokers() throws Exception {
        JSONArray arr = new JSONArray();
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT id, name, kind, IFNULL(server,''), status, added_at FROM brokers ORDER BY id DESC", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject().put("id", c.getLong(0)).put("name", c.getString(1))
                    .put("kind", c.getString(2)).put("server", c.getString(3))
                    .put("status", c.getString(4)).put("addedAt", c.getLong(5)));
        }
        c.close();
        return Res.json(200, new JSONObject().put("brokers", arr));
    }

    private Res addBroker(String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String name = HttpServer.jStr(o, "name");
        String kind = HttpServer.jStr(o, "kind");
        String server = HttpServer.jStr(o, "server");
        String key = HttpServer.jStr(o, "apiKey");
        String secret = HttpServer.jStr(o, "apiSecret");
        String login = HttpServer.jStr(o, "login");
        String pw = HttpServer.jStr(o, "password");

        if (name.length() < 2) return Res.error(400, "Enter a broker name");
        boolean mt5 = kind.toUpperCase(Locale.US).contains("MT");
        // v2.1 — MT5/MT4 account API key nahi use karta: Login + Password + Server kaafi
        if (mt5 && (login.isEmpty() || pw.isEmpty()))
            return Res.error(400, "MT5/MT4 ke liye Login + Password zaroori hain (API key optional hai)");
        if (!mt5 && key.length() < 8) return Res.error(400, "Enter the API key from your broker");
        db.getWritableDatabase().execSQL(
                "INSERT INTO brokers(name, kind, api_key, api_secret, login, password, server, status, added_at) VALUES(?,?,?,?,?,?,?,'SAVED',?)",
                new Object[]{name, kind.isEmpty() ? "MT5" : kind, key, secret, login, pw, server, System.currentTimeMillis()});
        db.log("INFO", "BROKER", "ADDED", name + " (" + (kind.isEmpty() ? "MT5" : kind)
                + (server.isEmpty() ? "" : " @ " + server) + ") — credentials saved on this device");
        return Res.json(200, new JSONObject().put("ok", true)
                .put("message", "Broker saved. Credentials is device par safe hain — live trading phase me connect hoga. (Paper trading abhi chal rahi hai — MT5 data feed se.)"));
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
                .put("riskPct", engine != null ? engine.riskPct() : 2.0)
                // v2.1 — MT5 feed
                .put("mt5Bridge", db.setting("mt5_bridge", ""))
                // v1.7 PRO GUARD settings
                .put("cooldownMin", engine != null ? engine.cooldownMin() : 15)
                .put("consecLoss", engine != null ? engine.consecLossN() : 3)
                .put("dailyKillPct", engine != null ? engine.dailyKillPct() : 0)
                .put("feePct", 0.05)
                // v1.8 PRO FILTER PACK (backtest-proved)
                .put("proRdMin", engine != null ? engine.proRdMin() : 0.25)
                .put("proEmaFilter", engine == null || engine.proEmaFilter())
                .put("proAtrFloor", engine != null ? engine.proAtrFloor() : 0.08)
                .put("proVolFilter", engine == null || engine.proVolFilter())
                // v3.0 QUANT PRO (P1-P5)
                .put("slipBps", engine != null ? engine.slipBps() : 2)
                .put("heatMaxPct", engine != null ? engine.heatMaxPct() : 0)
                .put("bucketMaxPct", engine != null ? engine.bucketMaxPct() : 0)
                .put("councilMin", engine != null ? engine.councilMin() : 0)
                .put("eventGate", engine != null && engine.eventGateOn())
                .put("autoPause", "1".equals(db.setting("auto_pause", "0")))
                .put("sessionFilter", engine != null && engine.sessionFilterOn())
                .put("bridgeLive", engine != null && engine.bridgeLive())
                .put("bridgeLots", engine != null ? engine.bridgeLots() : 0.01)
                .put("feedIntervalSec", db.setting("feed_interval_sec", "60"))
                .put("labSymbol", db.setting("lab_symbol", "XAUUSD"))
                .put("safeMode", engine != null && engine.isSafeMode())
                .put("version", "3.0"));
    }

    /** v1.8 — candlestick chart data: GET /api/candles?symbol=XAUUSD&n=60 → 5m candles.
     *  v3.0 — + open trade overlay (entry/SL/TP levels + side) is symbol par, taake
     *  Home chart par FreqUI-style trade markers/lines draw ho sakein. */
    private Res candles(String path, long uid) throws Exception {
        String sym = qParam("symbol").toUpperCase(Locale.US).trim();
        if (!sym.matches("[A-Z0-9]{4,20}")) return Res.error(400, "Symbol galat hai (e.g. XAUUSD)");
        int n;
        try { n = Integer.parseInt(qParam("n")); } catch (Exception e) { n = 60; }
        if (engine == null) return Res.error(503, "engine band hai");
        List<EngineCore.Candle> ks = engine.recentCandles(sym, n);
        JSONArray arr = new JSONArray();
        for (EngineCore.Candle k : ks) {
            arr.put(new JSONObject().put("ts", k.ts).put("o", k.o).put("h", k.h)
                    .put("l", k.l).put("c", k.c).put("v", k.v));
        }
        JSONObject out = new JSONObject().put("ok", true).put("symbol", sym)
                .put("candles", arr).put("count", arr.length());
        // v3.0 — is user ki khuli trade is symbol par (chart overlay ke liye)
        Cursor ot = db.getReadableDatabase().rawQuery(
                "SELECT side, entry, sl, tp FROM trades WHERE user_id=? AND symbol=? AND status='OPEN' ORDER BY id DESC LIMIT 1",
                new String[]{String.valueOf(uid), sym});
        if (ot.moveToFirst())
            out.put("trade", new JSONObject().put("side", ot.getString(0)).put("entry", ot.getDouble(1))
                    .put("sl", ot.getDouble(2)).put("tp", ot.getDouble(3)));
        ot.close();
        return Res.json(200, out);
    }

    /** v1.2 — Paper Balance: owner apna paper amount khud set karta hai.
     *  Body: {amount: number}. $10 – $100,000,000 allowed. Open trades are CANCELLED
     *  (exit=entry, pnl=0) because they were sized against the old balance; risk
     *  counters (start/peak/day_start) reset so PnL% aur drawdown naye base se chale. */
    private Res setBalance(long uid, String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        double amt = o.optDouble("amount", Double.NaN);
        if (Double.isNaN(amt) || amt < 10 || amt > 100000000)
            return Res.error(400, "Paper balance $10 se $100,000,000 ke beech set karein");
        long now = System.currentTimeMillis();
        db.getWritableDatabase().execSQL(
                "UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE user_id=? AND status='OPEN'",
                new Object[]{now, uid});
        db.getWritableDatabase().execSQL(
                "UPDATE accounts SET balance=?, start_balance=?, peak=?, day_start=?, day_ts=? WHERE user_id=?",
                new Object[]{amt, amt, amt, amt, now / 86400000L, uid});
        db.log("INFO", "ACCOUNT", "BALANCE_SET", "user #" + uid + " — paper balance set to $"
                + String.format(Locale.US, "%.2f", amt) + " (open trades cancelled, risk counters reset)");
        return Res.json(200, new JSONObject().put("ok", true).put("balance", round2(amt))
                .put("message", "Paper balance set: $" + String.format(Locale.US, "%.0f", amt)
                        + " — ab 3C MASTER har trade " + (engine != null ? engine.riskPct() : 1.0) + "% risk leggi (Settings > Risk %) — daily loss/profit UNLIMITED"));
    }

    // ================== v1.2 STRATEGY LAB + PERMANENT HISTORY ==================

    /** URL-decoded query param for the current request (api/history/csv uses it). */
    private String qParam(String key) {
        if (query == null || query.isEmpty()) return "";
        for (String p : query.split("&")) {
            int eq = p.indexOf('=');
            if (eq <= 0) continue;
            if (p.substring(0, eq).equals(key)) {
                try { return java.net.URLDecoder.decode(p.substring(eq + 1), "UTF-8"); }
                catch (Exception e) { return p.substring(eq + 1); }
            }
        }
        return "";
    }

    /** Strategy Lab actions — the whole AI/backtest/paper/live pipeline is driven from here. */
    private Res strategyAction(StrategyLab lab, String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        String action = HttpServer.jStr(o, "action");
        String text = HttpServer.jStr(o, "text");
        String url = HttpServer.jStr(o, "url");
        long id = o.optLong("id", -1);
        JSONObject out;
        switch (action) {
            case "add":
                if (text.isEmpty()) return Res.error(400, "Strategy likhein — kisi bhi zubaan mein");
                out = lab.addManual(text);
                break;
            case "yt_add":
                if (url.isEmpty()) return Res.error(400, "YouTube video ka link dein");
                out = lab.addYouTube(url);
                break;
            case "yt_channel":
                if (url.isEmpty()) return Res.error(400, "Channel ka link dein (@handle ya /channel/UC...)");
                out = lab.subscribeChannel(url);
                break;
            case "yt_stop":
                lab.stopChannel();
                out = new JSONObject().put("ok", true).put("message", "Channel watcher band ho gaya");
                break;
            case "backtest": out = lab.backtest(id); break;
            case "paper":    out = lab.startPaper(id); break;
            case "approve":  out = lab.approve(id); break;
            case "reject":   out = lab.reject(id); break;
            case "delete":   out = lab.remove(id); break;
            case "restore":  out = lab.restore(id); break;   // v1.7 UNDO
            case "trash":    out = lab.trash(); break;        // v1.7 trash list
            case "set_symbol": {
                String sym = HttpServer.jStr(o, "symbol").toUpperCase(Locale.US);
                if (!sym.matches("[A-Z0-9]{5,20}")) return Res.error(400, "Symbol format galat hai (e.g. BTCUSDT)");
                db.setSetting("lab_symbol", sym);
                out = new JSONObject().put("ok", true).put("message", "Backtest symbol: " + sym);
                break;
            }
            default: return Res.error(400, "Unknown action: " + action);
        }
        if (out == null) return Res.error(502, "AI service fail — thori dair baad dobara try karein");
        if (!out.optBoolean("ok", true)) return Res.json(502, out);
        return Res.json(200, out);
    }

    /**
     * v1.2 PERMANENT HISTORY — trades kabhi delete nahi hote; ye endpoint poora
     * archive year → month → day tree mein return karta hai (wins/losses/PnL/volume).
     */
    private Res history(long uid) throws Exception {
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT CAST(strftime('%Y', opened_at/1000, 'unixepoch') AS TEXT) y, " +
                "CAST(strftime('%m', opened_at/1000, 'unixepoch') AS TEXT) m, " +
                "CAST(strftime('%d', opened_at/1000, 'unixepoch') AS TEXT) d, " +
                "COUNT(*), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0), IFNULL(ROUND(SUM(pnl),2),0), IFNULL(ROUND(SUM(qty*entry),2),0) " +
                "FROM trades WHERE user_id=? AND status='CLOSED' AND opened_at IS NOT NULL " +
                "GROUP BY y, m, d ORDER BY y DESC, m DESC, d DESC", new String[]{String.valueOf(uid)});
        java.util.Map<String, JSONObject> years = new java.util.LinkedHashMap<>();
        java.util.Map<String, JSONObject> months = new java.util.LinkedHashMap<>();
        JSONArray dayArr = new JSONArray();
        while (c.moveToNext()) {
            String y = c.getString(0), m = c.getString(1), d = c.getString(2);
            long n = c.getLong(3), w = c.getLong(4);
            double pnl = c.getDouble(5), vol = c.getDouble(6);
            JSONObject yo = years.get(y);
            if (yo == null) {
                yo = new JSONObject().put("y", y).put("trades", 0).put("wins", 0).put("pnl", 0).put("months", new JSONArray());
                years.put(y, yo);
            }
            JSONObject mo = months.get(y + "-" + m);
            if (mo == null) {
                mo = new JSONObject().put("m", m).put("y", y).put("trades", 0).put("wins", 0).put("pnl", 0).put("days", new JSONArray());
                months.put(y + "-" + m, mo);
                ((JSONArray) yo.get("months")).put(mo);
            }
            JSONObject day = new JSONObject().put("d", d).put("trades", n).put("wins", w).put("pnl", pnl).put("vol", vol);
            ((JSONArray) mo.get("days")).put(day);
            mo.put("trades", mo.optLong("trades") + n).put("wins", mo.optLong("wins") + w)
                    .put("pnl", Math.round((mo.optDouble("pnl") + pnl) * 100) / 100.0);
            yo.put("trades", yo.optLong("trades") + n).put("wins", yo.optLong("wins") + w)
                    .put("pnl", Math.round((yo.optDouble("pnl") + pnl) * 100) / 100.0);
            dayArr.put(day);
        }
        c.close();
        JSONArray yArr = new JSONArray();
        for (JSONObject yo : years.values()) yArr.put(yo);
        return Res.json(200, new JSONObject().put("ok", true).put("years", yArr));
    }

    /** v1.2 — one month's closed trades as CSV (dashboard JS se file download hoti hai). */
    private Res historyCsv(long uid) throws Exception {
        int y, m;
        try { y = Integer.parseInt(qParam("y")); m = Integer.parseInt(qParam("m")); }
        catch (Exception e) { return Res.error(400, "y aur m chahiye (e.g. ?y=2026&m=01)"); }
        if (m < 1 || m > 12 || y < 2020 || y > 2100) return Res.error(400, "Month/year range galat hai");
        java.util.Calendar cal = java.util.Calendar.getInstance(java.util.TimeZone.getTimeZone("UTC"));
        cal.set(y, m - 1, 1, 0, 0, 0); cal.set(java.util.Calendar.MILLISECOND, 0);
        long from = cal.getTimeInMillis();
        cal.add(java.util.Calendar.MONTH, 1);
        long to = cal.getTimeInMillis() - 1;
        Cursor c = db.getReadableDatabase().rawQuery(
                "SELECT symbol, side, qty, entry, sl, tp, exit, pnl, strategy, consensus, risk, opened_at, closed_at FROM trades " +
                "WHERE user_id=? AND status='CLOSED' AND opened_at BETWEEN ? AND ? ORDER BY opened_at ASC",
                new String[]{String.valueOf(uid), String.valueOf(from), String.valueOf(to)});
        StringBuilder sb = new StringBuilder(
                "date,symbol,side,qty,entry,sl,tp,exit,pnl,risk_pct,strategy,consensus_pct,opened_at_ms,closed_at_ms\n");
        java.text.SimpleDateFormat iso = new java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
        iso.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
        int n = 0;
        while (c.moveToNext()) {
            sb.append(iso.format(new java.util.Date(c.getLong(11)))).append(',')
                    .append(c.getString(0)).append(',').append(c.getString(1)).append(',')
                    .append(c.getDouble(2)).append(',').append(c.getDouble(3)).append(',')
                    .append(c.getDouble(4)).append(',').append(c.getDouble(5)).append(',')
                    .append(c.getDouble(6)).append(',').append(c.getDouble(7)).append(',')
                    .append(c.isNull(10) ? "" : String.format(Locale.US, "%.1f", c.getDouble(10) * 100)).append(',')
                    .append('"').append(c.getString(8).replace("\"", "'")).append("\",")
                    .append(c.isNull(9) ? "" : String.format(Locale.US, "%.0f", c.getDouble(9) * 100)).append(',')
                    .append(c.getLong(11)).append(',').append(c.getLong(12)).append('\n');
            n++;
        }
        c.close();
        Res r = new Res();
        r.contentType = "text/csv; charset=utf-8";
        r.body = sb.toString();
        db.log("INFO", "HISTORY", "CSV_EXPORT", "user #" + uid + " — " + y + "-" + String.format(Locale.US, "%02d", m) + ": " + n + " trades exported");
        return r;
    }

    private Res saveSettings(long uid, String body) throws Exception {
        JSONObject o = HttpServer.jObj(body);
        // v3.0.2 GOVERNANCE: the MT5 bridge is the ONLY live-order surface in the app
        // (EngineCore.bridgeOrder/bridgeClose POST real orders to the bridge when
        // bridge_live=1). Until v3.0.2 ANY authenticated TRADER could enable it here.
        // All three bridge settings are now OWNER(ADMIN)-only; unauthorized attempts
        // are rejected AND logged to the audit ledger.
        boolean admin = isAdmin(uid);
        if (o.has("mt5Bridge") || o.has("bridgeLive") || o.has("bridgeLots")) {
            if (!admin) {
                db.log("WARN", "GUARD", "SETTINGS_ADMIN_BLOCKED",
                        "user #" + uid + " (non-admin) ne MT5 bridge setting change ki koshish — REJECT (live-order surface owner-only hai)");
                return Res.error(403, "MT5 bridge settings sirf owner (ADMIN) change kar sakta hai");
            }
        }
        if (o.has("engineOn")) {
            boolean on = o.optBoolean("engineOn");
            db.setSetting("engine_on", on ? "1" : "0");
            db.log("INFO", "SYSTEM", on ? "ENGINE_ENABLED" : "ENGINE_DISABLED", "user toggled engine");
        }
        // v1.4 — 3C risk % of equity per trade (MASTER PROMPT: "The user controls risk percentage")
        // v1.8 — owner "risk increase karoo": range 0.1–20%, default 2%
        if (o.has("riskPct")) {
            double r = o.optDouble("riskPct", 2.0);
            if (r < 0.1 || r > 20) return Res.error(400, "Risk 0.1% se 20% ke beech set karein (3C default 2%)");
            db.setSetting("risk_pct", String.valueOf(r));
            db.log("INFO", "RISK", "RISK_SET", "3C per-trade risk = " + r + "% of equity (owner setting)");
        }
        // v1.8 PRO FILTER PACK toggles (backtest-proved defaults)
        if (o.has("proRdMin")) {
            double v = o.optDouble("proRdMin", 0.25);
            if (v < 0 || v > 2) return Res.error(400, "Risk-distance min 0–2% ke beech set karein (0 = off)");
            db.setSetting("threec_rd_min_pct", String.valueOf(v));
            db.log("INFO", "FILTER", "RD_MIN_SET", "3C min risk-distance = " + v + "% of price");
        }
        if (o.has("proEmaFilter")) {
            db.setSetting("threec_ema_filter", o.optBoolean("proEmaFilter") ? "1" : "0");
            db.log("INFO", "FILTER", "EMA_FILTER_SET", "EMA200 trend filter = " + o.optBoolean("proEmaFilter"));
        }
        if (o.has("proAtrFloor")) {
            double v = o.optDouble("proAtrFloor", 0.08);
            if (v < 0 || v > 2) return Res.error(400, "ATR floor 0–2% ke beech set karein (0 = off)");
            db.setSetting("threec_atr_floor_pct", String.valueOf(v));
            db.log("INFO", "FILTER", "ATR_FLOOR_SET", "3C ATR floor = " + v + "% of price");
        }
        if (o.has("proVolFilter")) {
            db.setSetting("threec_vol_filter", o.optBoolean("proVolFilter") ? "1" : "0");
            db.log("INFO", "FILTER", "VOL_FILTER_SET", "Volume filter = " + o.optBoolean("proVolFilter"));
        }
        // v1.7 PRO GUARD — SL-loss cooldown minutes (0=off)
        if (o.has("cooldownMin")) {
            int c = (int) o.optDouble("cooldownMin", 15);
            if (c < 0 || c > 240) return Res.error(400, "Cooldown 0–240 minutes ke beech set karein (0 = off)");
            db.setSetting("cooldown_min", String.valueOf(c));
            db.log("INFO", "GUARD", "COOLDOWN_SET", "SL-loss cooldown = " + c + " min (owner setting)");
        }
        // v1.7 — consecutive-loss pause trigger count (0=off)
        if (o.has("consecLoss")) {
            int n = (int) o.optDouble("consecLoss", 3);
            if (n < 0 || n > 10) return Res.error(400, "Consecutive losses 0–10 ke beech set karein (0 = off)");
            db.setSetting("consec_loss", String.valueOf(n));
            db.log("INFO", "GUARD", "CONSEC_LOSS_SET", "StoplossGuard = " + n + " lagatar SL losses → 1 ghanta pause");
        }
        // v1.7 — daily kill switch % (0 = OFF default — owner UNLIMITED chahta hai)
        if (o.has("dailyKillPct")) {
            double k = o.optDouble("dailyKillPct", 0);
            if (k < 0 || k > 90) return Res.error(400, "Daily kill 0–90% ke beech set karein (0 = off)");
            db.setSetting("daily_kill_pct", String.valueOf(k));
            db.log("INFO", "GUARD", "DAILY_KILL_SET", "Daily kill switch = " + k + "%" + (k <= 0 ? " (OFF — unlimited)" : ""));
        }
        // v2.1 — optional MT5 bridge URL: PC par MetaTrader5 terminal + mt5-bridge.py
        // chalao aur yahan uska URL dalo — candles phir REAL MT5 terminal se aayengi.
        if (o.has("mt5Bridge")) {
            String b = o.optString("mt5Bridge", "").trim();
            if (b.length() > 300) return Res.error(400, "Bridge URL bohat lamba hai (max 300 chars)");
            if (!b.isEmpty() && !b.startsWith("http://") && !b.startsWith("https://"))
                return Res.error(400, "Bridge URL http:// ya https:// se shuru hona chahiye");
            db.setSetting("mt5_bridge", b);
            db.log("INFO", "DATA", "MT5_BRIDGE_SET", b.isEmpty()
                    ? "MT5 bridge cleared — built-in halal commodities feed use hoga"
                    : "MT5 bridge set: " + b + " — candles ab MetaTrader5 terminal se aayengi");
        }
        // ===== v3.0 QUANT PRO settings =====
        if (o.has("slipBps")) {
            double v = o.optDouble("slipBps", 2);
            if (v < 0 || v > 50) return Res.error(400, "Slippage 0–50 bps ke beech set karein (0 = exact fills)");
            db.setSetting("slip_bps", String.valueOf(v));
            db.log("INFO", "FILL", "SLIP_SET", "slippage/spread model = " + v + " bps per side");
        }
        if (o.has("heatMaxPct")) {
            double v = o.optDouble("heatMaxPct", 0);
            if (v < 0 || v > 100) return Res.error(400, "Heat cap 0–100% ke beech set karein (0 = OFF/unlimited)");
            db.setSetting("heat_max_pct", String.valueOf(v));
            db.log("INFO", "GUARD", "HEAT_SET", "portfolio heat cap = " + v + "%" + (v <= 0 ? " (OFF — unlimited, owner default)" : ""));
        }
        if (o.has("bucketMaxPct")) {
            double v = o.optDouble("bucketMaxPct", 0);
            if (v < 0 || v > 100) return Res.error(400, "Bucket cap 0–100% ke beech set karein (0 = OFF)");
            db.setSetting("bucket_max_pct", String.valueOf(v));
            db.log("INFO", "GUARD", "BUCKET_SET", "bucket (METAL/ENERGY/AGRI) cap = " + v + "%" + (v <= 0 ? " (OFF)" : ""));
        }
        if (o.has("councilMin")) {
            int v = (int) o.optDouble("councilMin", 0);
            if (v < 0 || v > 95) return Res.error(400, "Council min 0–95 ke beech set karein (0 = tag-only, koi block nahi)");
            db.setSetting("council_min", String.valueOf(v));
            db.log("INFO", "COUNCIL", "COUNCIL_SET", "Signal Council min confidence = " + v + "%" + (v <= 0 ? " (tag-only mode)" : ""));
        }
        if (o.has("eventGate")) {
            db.setSetting("event_gate", o.optBoolean("eventGate") ? "1" : "0");
            db.log("INFO", "GUARD", "EVENT_GATE_SET", "HIGH-impact news entry pause = " + o.optBoolean("eventGate"));
        }
        if (o.has("autoPause")) {
            db.setSetting("auto_pause", o.optBoolean("autoPause") ? "1" : "0");
            db.log("INFO", "GUARD", "AUTO_PAUSE_SET", "degraded strategy auto-pause = " + o.optBoolean("autoPause"));
        }
        if (o.has("sessionFilter")) {
            db.setSetting("session_filter", o.optBoolean("sessionFilter") ? "1" : "0");
            db.log("INFO", "GUARD", "SESSION_SET", "CME halt (17-18 ET) entry filter = " + o.optBoolean("sessionFilter"));
        }
        if (o.has("bridgeLive")) {
            db.setSetting("bridge_live", o.optBoolean("bridgeLive") ? "1" : "0");
            db.log("WARN", "BRIDGE", "BRIDGE_LIVE_SET", "MT5 bridge LIVE MIRROR = " + o.optBoolean("bridgeLive")
                    + (o.optBoolean("bridgeLive") ? " — paper trades ke saath bridge par real orders jayenge (owner responsibility)" : " (safe: sirf paper)"));
        }
        if (o.has("bridgeLots")) {
            double v = o.optDouble("bridgeLots", 0.01);
            if (v < 0.01 || v > 100) return Res.error(400, "Bridge lots 0.01–100 ke beech set karein");
            db.setSetting("bridge_lots", String.valueOf(v));
            db.log("INFO", "BRIDGE", "BRIDGE_LOTS_SET", "bridge mirror lot size = " + v);
        }
        if (o.has("feedIntervalSec")) {
            int v = (int) o.optDouble("feedIntervalSec", 60);
            if (v < 20 || v > 600) return Res.error(400, "Feed interval 20–600 seconds ke beech set karein");
            db.setSetting("feed_interval_sec", String.valueOf(v));
            db.log("INFO", "DATA", "FEED_INTERVAL_SET", "per-symbol feed refresh = " + v + "s");
        }
        if (o.has("labSymbol")) {
            String v = o.optString("labSymbol", "XAUUSD").toUpperCase(Locale.US).trim();
            if (!v.matches("[A-Z0-9]{4,20}")) return Res.error(400, "Lab symbol galat (e.g. XAUUSD)");
            db.setSetting("lab_symbol", v);
            db.log("INFO", "LAB", "LAB_SYMBOL_SET", "Lab backtest symbol = " + v);
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
                "SELECT id, name, email, role, active, created_at, (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id), IFNULL(approved,1), IFNULL(trade_ok, CASE WHEN role='ADMIN' THEN 1 ELSE 0 END) FROM users u ORDER BY id", null);
        while (c.moveToNext()) {
            arr.put(new JSONObject()
                    .put("id", c.getLong(0)).put("name", c.getString(1))
                    .put("email", c.getString(2)).put("role", c.getString(3))
                    .put("active", c.getInt(4)).put("createdAt", c.getLong(5))
                    .put("sessions", c.getInt(6)).put("approved", c.getInt(7))
                    .put("tradeOk", c.getInt(8)));
        }
        c.close();
        Cursor sc = db.getReadableDatabase().rawQuery("SELECT COUNT(*), IFNULL(SUM(active),0), SUM(CASE WHEN IFNULL(approved,1)=0 THEN 1 ELSE 0 END) FROM users", null);
        int total = 0, activeUsers = 0, pendingUsers = 0;
        if (sc.moveToFirst()) { total = sc.getInt(0); activeUsers = sc.getInt(1); pendingUsers = sc.getInt(2); }
        sc.close();
        return Res.json(200, new JSONObject().put("users", arr)
                .put("total", total).put("activeUsers", activeUsers).put("pendingUsers", pendingUsers));
    }

    /** POST /api/admin/users — {id, action: approve|activate|deactivate|delete}. */
    private Res adminUserAction(long uid, String body) throws Exception {
        Res g = adminGuard(uid); if (g != null) return g;
        JSONObject o = HttpServer.jObj(body);
        long id = o.optLong("id", -1);
        String action = HttpServer.jStr(o, "action");
        if (id <= 0) return Res.error(400, "User id required");

        // v1.9 OWNER GATE — approve: PENDING user ko login permission milta hai
        if ("approve".equals(action)) {
            Cursor ec = db.getReadableDatabase().rawQuery("SELECT name, email FROM users WHERE id=?", new String[]{String.valueOf(id)});
            if (!ec.moveToFirst()) { ec.close(); return Res.error(404, "User not found"); }
            String nm = ec.getString(0), em = ec.getString(1); ec.close();
            db.getWritableDatabase().execSQL("UPDATE users SET approved=1 WHERE id=?", new Object[]{id});
            db.log("INFO", "ADMIN", "USER_APPROVED", nm + " (" + em + ") approved by owner — ab sign in kar sakta hai");
            return Res.json(200, new JSONObject().put("ok", true)
                    .put("message", nm + " APPROVED — ab wo sign in kar sakta hai"));
        }

        // v2.1 OWNER TRADING GATE — {id, action:'trade', value:1|0}:
        // owner decide karta hai kaun user engine se trade kar sakta hai
        if ("trade".equals(action)) {
            int val = o.optInt("value", -1);
            if (val != 0 && val != 1) return Res.error(400, "value 0 ya 1 required");
            if (id == uid && val == 0) return Res.error(400, "Apna khud ka trading band nahi kar sakte (aap owner hain)");
            Cursor ec = db.getReadableDatabase().rawQuery("SELECT name FROM users WHERE id=?", new String[]{String.valueOf(id)});
            if (!ec.moveToFirst()) { ec.close(); return Res.error(404, "User not found"); }
            String nm = ec.getString(0); ec.close();
            db.getWritableDatabase().execSQL("UPDATE users SET trade_ok=? WHERE id=?", new Object[]{val, id});
            db.log("INFO", "ADMIN", val == 1 ? "TRADING_ENABLED" : "TRADING_DISABLED",
                    nm + " trading " + (val == 1 ? "ENABLED" : "DISABLED") + " by owner");
            return Res.json(200, new JSONObject().put("ok", true)
                    .put("message", nm + " — trading " + (val == 1
                            ? "ENABLED — ab engine is user ke liye trades kholega"
                            : "DISABLED — is user ke liye naye trades nahi khulenge")));
        }

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
