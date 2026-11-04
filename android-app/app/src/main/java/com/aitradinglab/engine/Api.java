package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;
import android.os.PowerManager;
import android.util.Log;
import com.aitradinglab.engine.EngineCore;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.URLDecoder;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TimeZone;
import java.util.function.BiFunction;
import org.json.JSONArray;
import org.json.JSONObject;

/* loaded from: classes.dex */
public class Api {
    private final Context appCtx;
    private final String dashboardHtml;
    private final Db db;
    private final EngineCore engine;
    private String query = "";

    public static class Res {
        public int status = 200;
        public String contentType = "application/json";
        public String body = "{}";

        public static Res json(int i, Object obj) {
            Res res = new Res();
            res.status = i;
            res.body = obj instanceof String ? (String) obj : obj.toString();
            return res;
        }

        public static Res error(int i, String str) {
            try {
                return json(i, new JSONObject().put("error", str));
            } catch (Exception unused) {
                return json(i, "{\"error\":\"error\"}");
            }
        }

        public static Res html(String str) {
            Res res = new Res();
            res.contentType = "text/html; charset=utf-8";
            res.body = str;
            return res;
        }
    }

    public Api(Context context, Db db, EngineCore engineCore) {
        String str = null;
        this.db = db;
        this.engine = engineCore;
        this.appCtx = context.getApplicationContext();
        try {
            InputStream open = context.getAssets().open("dashboard.html");
            ByteArrayOutputStream byteArrayOutputStream = new ByteArrayOutputStream();
            byte[] bArr = new byte[8192];
            while (true) {
                int read = open.read(bArr);
                if (read <= 0) {
                    break;
                } else {
                    byteArrayOutputStream.write(bArr, 0, read);
                }
            }
            str = new String(byteArrayOutputStream.toByteArray(), "UTF-8");
        } catch (Exception unused) {
            str = "<html><body><h2>AI Trading Lab</h2><p>dashboard asset missing</p></body></html>";
        }
        this.dashboardHtml = str;
    }

    public Res route(String str, String str2, String str3, String str4) {
        int indexOf = str2.indexOf(63);
        if (indexOf >= 0) {
            this.query = str2.substring(indexOf + 1);
            str2 = str2.substring(0, indexOf);
        } else {
            this.query = "";
        }
        String upperCase = str.toUpperCase();
        if ("OPTIONS".equals(upperCase)) {
            return Res.json(200, "{}");
        }
        try {
            return "GET".equals(upperCase) ? get(str2, str3) : "POST".equals(upperCase) ? post(str2, str3, str4) : "DELETE".equals(upperCase) ? delete(str2, str3) : Res.error(405, "method not allowed");
        } catch (Throwable th) {
            String str5 = th.getClass().getSimpleName() + ": " + th.getMessage();
            try {
                Log.e("ATL.API", str2 + " failed — " + str5);
                this.db.log("ERROR", "API", "REQUEST_FAIL", str2 + " — " + str5);
            } catch (Throwable unused) {
            }
            return Res.error(500, "server error — " + str5 + " (screenshot this and report)");
        }
    }

    private Long userId(String str) {
        if (str == null) {
            return null;
        }
        if (str.startsWith("Bearer ")) {
            str = str.substring(7);
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT user_id FROM sessions WHERE token=?", new String[]{str});
        Long valueOf = rawQuery.moveToFirst() ? Long.valueOf(rawQuery.getLong(0)) : null;
        rawQuery.close();
        return valueOf;
    }

    private Res get(String str, String str2) throws Exception {
        if ("/".equals(str) || "/index.html".equals(str)) {
            return Res.html(this.dashboardHtml);
        }
        if ("/api/health".equals(str)) {
            return Res.json(200, new JSONObject().put("ok", true).put("engine", "ai-trading-lab-phone").put("device", Build.MANUFACTURER + " " + Build.MODEL).put("android", Build.VERSION.SDK_INT).put("version", "1.1").put("timeframe", "5m").put("scanner", "24/7").put("strategy", "3C MASTER (M5) + PDF PACK (9, 5m) + 5M PLAYBOOK (4, guide-tuned) + SHAAKUNI (5) + AI TRAINER"));
        }
        Long userId = userId(str2);
        if (userId == null) {
            return Res.error(401, "authentication required");
        }
        if ("/api/dashboard".equals(str)) {
            return dashboard(userId.longValue());
        }
        if ("/api/instruments".equals(str)) {
            return instruments();
        }
        if (str.startsWith("/api/indicators")) {
            return indicators(str);
        }
        if ("/api/news".equals(str)) {
            return news();
        }
        if ("/api/trades".equals(str)) {
            return trades(userId.longValue());
        }
        if ("/api/strategies".equals(str)) {
            EngineCore engineCore = this.engine;
            if (engineCore == null || engineCore.lab == null) {
                return Res.error(503, "Lab shuru ho raha hai — refresh karein");
            }
            return Res.json(200, this.engine.lab.listStrategies());
        }
        if ("/api/history".equals(str)) {
            return history(userId.longValue());
        }
        if ("/api/history/csv".equals(str)) {
            return historyCsv(userId.longValue());
        }
        if ("/api/logs".equals(str)) {
            return logs();
        }
        if ("/api/brokers".equals(str)) {
            return brokers();
        }
        if ("/api/settings".equals(str)) {
            return settings();
        }
        if (str.startsWith("/api/candles")) {
            return candles(str, userId == null ? 0L : userId.longValue());
        }
        return "/api/analytics".equals(str) ? analytics(userId.longValue()) : str.startsWith("/api/seasonality") ? seasonality(str) : "/api/audit.csv".equals(str) ? auditCsv(userId.longValue()) : "/api/ai_status".equals(str) ? aiStatus() : "/api/pack".equals(str) ? packStatus() : "/api/admin/users".equals(str) ? adminUsers(userId.longValue()) : "/api/admin/invites".equals(str) ? adminInvites(userId.longValue()) : "/api/admin/alerts".equals(str) ? adminAlerts(userId.longValue()) : Res.error(404, "not found");
    }

    private Res aiStatus() {
        long j = 0L;
        if (this.engine == null) {
            return Res.error(503, "engine not ready");
        }
        JSONObject jSONObject = new JSONObject();
        try {
            j = Long.parseLong(this.db.setting("ai_trained_at", "0").trim());
        } catch (Throwable unused) {
            j = 0;
        }
        try {
            jSONObject.put("trained_at", j);
            jSONObject.put("auto_train", "1".equals(this.db.setting("ai_auto_train", "1")));
            jSONObject.put("running", this.engine.aiTraining);
            try {
                jSONObject.put("report", new JSONObject(this.db.setting("ai_train_report", "{}")));
            } catch (Throwable unused2) {
            }
            try {
                jSONObject.put("weights", new JSONObject(this.db.setting("ai_weights_v2", "{}")));
            } catch (Throwable unused3) {
            }
            jSONObject.put("fee_edge_on", "1".equals(this.db.setting("fee_edge_on", "1")));
            jSONObject.put("min_fee_edge_pct", this.db.setting("min_fee_edge_pct", "0.14"));
            return Res.json(200, jSONObject);
        } catch (Throwable th) {
            return Res.error(500, String.valueOf(th));
        }
    }

    private Res packStatus() {
        JSONObject jSONObject = new JSONObject();
        try {
            JSONArray jSONArray = new JSONArray();
            for (String[] strArr : StrategyPack.STRATEGIES) {
                jSONArray.put(new JSONObject().put("key", strArr[0]).put("name", strArr[1]).put("rating", strArr[2]).put("on", "1".equals(this.db.setting("pack_" + strArr[0].toLowerCase(Locale.ROOT), "1"))));
            }
            jSONObject.put("strategies", jSONArray);
            jSONObject.put("pack_on", "1".equals(this.db.setting("pack_on", "0")));
            return Res.json(200, jSONObject);
        } catch (Throwable th) {
            return Res.error(500, String.valueOf(th));
        }
    }

    private Res post(String str, String str2, String str3) throws Exception {
        if ("/api/auth/register".equals(str)) {
            return register(str3);
        }
        if ("/api/auth/login".equals(str)) {
            return login(str3);
        }
        if ("/api/auth/verify2fa".equals(str)) {
            return verify2fa(str3);
        }
        if ("/api/auth/reset".equals(str)) {
            return resetPassword(str3);
        }
        Long userId = userId(str2);
        if (userId == null) {
            return Res.error(401, "authentication required");
        }
        if ("/api/auth/logout".equals(str)) {
            return logout(str2);
        }
        if ("/api/trades/close".equals(str)) {
            return closeTrade(userId.longValue(), str3);
        }
        if ("/api/brokers".equals(str)) {
            return addBroker(str3);
        }
        if ("/api/brokers/test".equals(str)) {
            return testBroker(str3);
        }
        if ("/api/instruments/scan".equals(str)) {
            EngineCore engineCore = this.engine;
            if (engineCore != null) {
                engineCore.forceDiscovery();
            }
            this.db.log("INFO", "DISCOVERY", "MANUAL_SCAN", "user triggered discovery + news scan");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Discovery + news scan started"));
        }
        if ("/api/settings".equals(str)) {
            return saveSettings(str3);
        }
        if ("/api/balance".equals(str)) {
            return setBalance(userId.longValue(), str3);
        }
        if ("/api/ai_train".equals(str)) {
            if (!isAdmin(userId.longValue())) {
                return Res.error(403, "sirf owner (ADMIN) AI train kar sakta hai");
            }
            EngineCore engineCore2 = this.engine;
            if (engineCore2 == null) {
                return Res.error(503, "engine not ready");
            }
            engineCore2.trainAiAsync();
            this.db.log("INFO", "AI", "TRAIN_TRIGGERED", "owner ne TRAIN AI dabaya — Binance history walk-forward shuru (15m depth + 1d 2017→)");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "AI training shuru — Binance history (top-12 pairs, 15m depth + 1d HTF) walk-forward chal raha hai. 5-15 min; report Home > AI TRAINER card me aayegi."));
        }
        if (!"/api/strategies".equals(str)) {
            return "/api/admin/users".equals(str) ? adminUserAction(userId.longValue(), str3) : "/api/admin/invites".equals(str) ? adminInviteAction(userId.longValue(), str3) : "/api/admin/alerts".equals(str) ? adminAlertAction(userId.longValue(), str3) : Res.error(404, "not found");
        }
        EngineCore engineCore3 = this.engine;
        if (engineCore3 == null || engineCore3.lab == null) {
            return Res.error(503, "Lab shuru ho raha hai — refresh karein");
        }
        return strategyAction(this.engine.lab, str3);
    }

    private Res delete(String str, String str2) throws Exception {
        if (userId(str2) == null) {
            return Res.error(401, "authentication required");
        }
        if (str.startsWith("/api/brokers/")) {
            String substring = str.substring(13);
            this.db.getWritableDatabase().execSQL("DELETE FROM brokers WHERE id=?", new Object[]{Long.valueOf(Long.parseLong(substring))});
            this.db.log("INFO", "BROKER", "REMOVED", "broker #" + substring + " removed");
            return Res.json(200, new JSONObject().put("ok", true));
        }
        return Res.error(404, "not found");
    }

    /* JADX WARN: Multi-variable type inference failed */
    private Res register(String str) throws Exception {
        String str2 = null;
        JSONObject jObj = HttpServer.jObj(str);
        String jStr = HttpServer.jStr(jObj, "name");
        String lowerCase = HttpServer.jStr(jObj, "email").toLowerCase();
        String jStr2 = HttpServer.jStr(jObj, "password");
        String jStr3 = HttpServer.jStr(jObj, "invitationCode");
        if (jStr.length() < 2 || jStr.length() > 60) {
            return Res.error(400, "Enter your full name (2-60 characters)");
        }
        if (!lowerCase.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) {
            return Res.error(400, "Enter a valid email address");
        }
        if (jStr2.length() < 8 || !jStr2.matches(".*[A-Za-z].*") || !jStr2.matches(".*[0-9].*")) {
            return Res.error(400, "Password must be 8+ characters with letters and numbers");
        }
        String checkInvite = Auth.checkInvite(this.db, jStr3);
        if (checkInvite != null) {
            return Res.error(403, checkInvite);
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE email=?", new String[]{lowerCase});
        if (rawQuery.moveToFirst()) {
            rawQuery.close();
            return Res.error(409, "An account with this email already exists. Sign in instead.");
        }
        rawQuery.close();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
        int i = (rawQuery2.moveToFirst() && rawQuery2.getInt(0) == 0) ? 1 : 0;
        rawQuery2.close();
        String str3 = i != 0 ? "ADMIN" : "TRADER";
        this.db.getWritableDatabase().execSQL("INSERT INTO users(email, name, pw_hash, role, totp_secret, totp_enabled, active, approved, trade_ok, created_at) VALUES(?,?,?,?,?,0,1,?,?,?)", new Object[]{lowerCase, jStr, Auth.hashPw(jStr2), str3, Auth.totpSecret(), Integer.valueOf(i), Integer.valueOf(i), Long.valueOf(System.currentTimeMillis())});
        Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE email=?", new String[]{lowerCase});
        long j = rawQuery3.moveToFirst() ? rawQuery3.getLong(0) : -1L;
        rawQuery3.close();
        this.db.getWritableDatabase().execSQL("INSERT OR IGNORE INTO accounts(user_id, balance, start_balance, peak, day_start, day_ts) VALUES(?,100,100,100,100,?)", new Object[]{Long.valueOf(j), Long.valueOf(System.currentTimeMillis() / 86400000)});
        this.db.log("INFO", "AUTH", "REGISTER", lowerCase + " (" + str3 + ") — account created, " + (i != 0 ? "owner (auto-approved)" : "PENDING owner approval"));
        String upperCase = jStr3 == null ? "" : jStr3.trim().toUpperCase();
        try {
            str2 = "pending";
            try {
                this.db.getWritableDatabase().execSQL("INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('REGISTER',?,?,?,0,?)", new Object[]{(i != 0 ? new StringBuilder("Owner account created — ") : new StringBuilder("New registration — APPROVE karein: ")).append(jStr).toString(), i != 0 ? jStr + " (" + lowerCase + ") OWNER account ban gaya — role ADMIN (auto-approved, trading enabled)" : "APPROVAL ZAROORI — " + jStr + " (" + lowerCase + ") ne invite code " + upperCase + " se register kiya · role TRADER · Control > Users me APPROVE dabayen (tabhi login hoga) · uske baad ENABLE TRADING bhi dabayen (tabhi trade karega)", new JSONObject().put("email", lowerCase).put("name", jStr).put("invite", upperCase).put("role", str3).put(str2, i ^ 1).toString(), Long.valueOf(System.currentTimeMillis())});
            } catch (Throwable unused) {
            }
        } catch (Throwable unused2) {
            str2 = "pending";
        }
        Notifier.registration(this.appCtx, jStr, lowerCase, str3, upperCase, i != 0);
        return Res.json(200, new JSONObject().put("ok", true).put(str2, i ^ 1).put("message", i != 0 ? "Owner account created. Sign in karein — dashboard foran khulega." : "Registration submitted! Owner ko notification chala gaya — wo APPROVE karega, phir ENABLE TRADING karega. Uske baad aap sign in karke trade kar sakenge."));
    }

    private Res login(String str) throws Exception {
        JSONObject jObj = HttpServer.jObj(str);
        String lowerCase = HttpServer.jStr(jObj, "name").toLowerCase();
        String lowerCase2 = HttpServer.jStr(jObj, "email").toLowerCase();
        String jStr = HttpServer.jStr(jObj, "password");
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, name, pw_hash, active, totp_enabled, totp_secret, approved FROM users WHERE email=?", new String[]{lowerCase2});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
            boolean z = rawQuery2.moveToFirst() && rawQuery2.getInt(0) == 0;
            rawQuery2.close();
            if (z) {
                return Res.error(401, "Is device par abhi koi account nahi hai (naya install). Pehle REGISTER tab se account banayen (invite code owner se lein), phir sign in karein.");
            }
            return Res.error(401, "Invalid email or password — ya name match nahi hua. Exact wahi name aur email likhein jo registration par use hua tha.");
        }
        long j = rawQuery.getLong(0);
        String lowerCase3 = rawQuery.getString(1) == null ? "" : rawQuery.getString(1).trim().toLowerCase();
        String string = rawQuery.getString(2);
        int i = rawQuery.getInt(3);
        rawQuery.getInt(4);
        rawQuery.getString(5);
        int i2 = rawQuery.getInt(6);
        rawQuery.close();
        if (!Auth.verifyPw(jStr, string)) {
            return Res.error(401, "Invalid email or password");
        }
        if (lowerCase.isEmpty() || !lowerCase.equals(lowerCase3)) {
            return Res.error(401, "Name does not match this account — enter the exact name used at registration");
        }
        if (i == 0) {
            return Res.error(403, "Account deactivated");
        }
        if (i2 == 0) {
            Notifier.post(this.appCtx, "Approval pending — " + lowerCase3, lowerCase3 + " (" + lowerCase2 + ") login karne ki koshish kar raha hai lekin abhi PENDING hai. Settings > Control > Users me APPROVE dabayen.");
            try {
                this.db.getWritableDatabase().execSQL("INSERT INTO notifications(kind, title, body, meta, read, created_at) VALUES('PENDING_LOGIN',?,?,?,0,?)", new Object[]{"PENDING user login try kar raha hai: " + lowerCase3, lowerCase3 + " (" + lowerCase2 + ") ne login try kiya — account abhi bhi approval ka intezar kar raha hai. Control > Users me APPROVE karein.", "{}", Long.valueOf(System.currentTimeMillis())});
            } catch (Throwable unused) {
            }
            this.db.log("INFO", "AUTH", "LOGIN_BLOCKED_PENDING", lowerCase2 + " — login refused, owner approval chahiye");
            return Res.error(403, "Account PENDING approval — owner ne abhi approve nahi kiya. Registration par owner ko notification chala hai; jaise hi wo APPROVE karega, aap sign in kar sakenge.");
        }
        this.db.getWritableDatabase().execSQL("UPDATE users SET totp_enabled=0 WHERE id=?", new Object[]{Long.valueOf(j)});
        String str2 = Auth.token();
        this.db.getWritableDatabase().execSQL("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", new Object[]{str2, Long.valueOf(j), Long.valueOf(System.currentTimeMillis())});
        JSONObject put = new JSONObject().put("id", j).put("email", lowerCase2).put("name", lowerCase3);
        Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT role FROM users WHERE id=?", new String[]{String.valueOf(j)});
        if (rawQuery3.moveToFirst()) {
            put.put("role", rawQuery3.getString(0));
        }
        rawQuery3.close();
        this.db.log("INFO", "AUTH", "LOGIN", lowerCase2 + " signed in (direct entry)");
        return Res.json(200, new JSONObject().put("ok", true).put("token", str2).put("user", put).put("message", "Welcome back — opening the trading engine"));
    }

    private Res verify2fa(String str) throws Exception {
        JSONObject jObj = HttpServer.jObj(str);
        String lowerCase = HttpServer.jStr(jObj, "email").toLowerCase();
        String jStr = HttpServer.jStr(jObj, "code");
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, totp_secret FROM users WHERE email=?", new String[]{lowerCase});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            return Res.error(401, "invalid session");
        }
        long j = rawQuery.getLong(0);
        String string = rawQuery.getString(1);
        rawQuery.close();
        if (!Auth.verifyTotp(string, jStr)) {
            return Res.error(401, "Invalid or expired code — try the next one");
        }
        this.db.getWritableDatabase().execSQL("UPDATE users SET totp_enabled=1 WHERE id=?", new Object[]{Long.valueOf(j)});
        String str2 = Auth.token();
        this.db.getWritableDatabase().execSQL("INSERT INTO sessions(token, user_id, created_at) VALUES(?,?,?)", new Object[]{str2, Long.valueOf(j), Long.valueOf(System.currentTimeMillis())});
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT email, name, role FROM users WHERE id=?", new String[]{String.valueOf(j)});
        JSONObject put = new JSONObject().put("id", j);
        if (rawQuery2.moveToFirst()) {
            put.put("email", rawQuery2.getString(0)).put("name", rawQuery2.getString(1)).put("role", rawQuery2.getString(2));
        }
        rawQuery2.close();
        this.db.log("INFO", "AUTH", "LOGIN", lowerCase + " signed in (2FA verified)");
        return Res.json(200, new JSONObject().put("ok", true).put("token", str2).put("user", put));
    }

    private Res resetPassword(String str) throws Exception {
        JSONObject jObj = HttpServer.jObj(str);
        String jStr = HttpServer.jStr(jObj, "name");
        String lowerCase = HttpServer.jStr(jObj, "email").toLowerCase();
        String jStr2 = HttpServer.jStr(jObj, "invitationCode");
        String jStr3 = HttpServer.jStr(jObj, "newPassword");
        if (jStr.length() < 2) {
            return Res.error(400, "Enter the full name on the account");
        }
        if (!lowerCase.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")) {
            return Res.error(400, "Enter a valid email address");
        }
        if (jStr3.length() < 8 || !jStr3.matches(".*[A-Za-z].*") || !jStr3.matches(".*[0-9].*")) {
            return Res.error(400, "New password must be 8+ characters with letters and numbers");
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT active FROM invites WHERE code=?", new String[]{jStr2 == null ? "" : jStr2.trim().toUpperCase()});
        boolean z = rawQuery.moveToFirst() && rawQuery.getInt(0) == 1;
        rawQuery.close();
        if (!z) {
            return Res.error(403, "Valid invitation code required to reset a password");
        }
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT id, name FROM users WHERE email=?", new String[]{lowerCase});
        if (!rawQuery2.moveToFirst()) {
            rawQuery2.close();
            Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
            boolean z2 = rawQuery3.moveToFirst() && rawQuery3.getInt(0) == 0;
            rawQuery3.close();
            if (z2) {
                return Res.error(404, "No account found with this email on this device — naya install hai, is liye purana account maujood nahi. REGISTER tab se pehle account banayen.");
            }
            return Res.error(404, "No account found with this email on this device — email check karein ya REGISTER tab se account banayen.");
        }
        long j = rawQuery2.getLong(0);
        String lowerCase2 = rawQuery2.getString(1) != null ? rawQuery2.getString(1).trim().toLowerCase() : "";
        rawQuery2.close();
        if (!jStr.trim().toLowerCase().equals(lowerCase2)) {
            return Res.error(401, "Name does not match this account — enter the exact name used at registration");
        }
        this.db.getWritableDatabase().execSQL("UPDATE users SET pw_hash=?, totp_enabled=0, totp_secret=? WHERE id=?", new Object[]{Auth.hashPw(jStr3), Auth.totpSecret(), Long.valueOf(j)});
        this.db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{Long.valueOf(j)});
        this.db.log("INFO", "AUTH", "PASSWORD_RESET", lowerCase + " — password reset via invitation code, 2FA re-enrollment required");
        return Res.json(200, new JSONObject().put("ok", true).put("message", "Password changed. Sign in with your new password, then re-enroll 2FA when the setup key is shown."));
    }

    private Res logout(String str) throws Exception {
        if (str != null && str.startsWith("Bearer ")) {
            str = str.substring(7);
        }
        if (str != null) {
            this.db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE token=?", new String[]{str});
        }
        return Res.json(200, new JSONObject().put("ok", true));
    }

    private Res dashboard(long j) throws Exception {
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        double d4 = 0.0d;
        int i = 0;
        int i2 = 0;
        double d5 = 0.0d;
        JSONArray jSONArray = null;
        JSONObject jSONObject = null;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT balance, start_balance, peak, day_start FROM accounts WHERE user_id=?", new String[]{String.valueOf(j)});
        int i3 = 3;
        int i4 = 2;
        if (rawQuery.moveToFirst()) {
            d = rawQuery.getDouble(0);
            d2 = rawQuery.getDouble(1);
            d3 = rawQuery.getDouble(2);
            d4 = rawQuery.getDouble(3);
        } else {
            d = 100.0d;
            d2 = 100.0d;
            d3 = 100.0d;
            d4 = 100.0d;
        }
        rawQuery.close();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        int i5 = rawQuery2.moveToFirst() ? rawQuery2.getInt(0) : 0;
        rawQuery2.close();
        Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT symbol, side, qty, entry FROM trades WHERE user_id=? AND status='OPEN'", new String[]{String.valueOf(j)});
        double d6 = 0.0d;
        while (rawQuery3.moveToNext()) {
            double livePrice = livePrice(rawQuery3.getString(0));
            if (!Double.isNaN(livePrice)) {
                double d7 = rawQuery3.getDouble(i4);
                double d8 = rawQuery3.getDouble(i3);
                d6 += ("BUY".equals(rawQuery3.getString(1)) ? livePrice - d8 : d8 - livePrice) * d7;
                i3 = 3;
                i4 = 2;
            }
        }
        rawQuery3.close();
        Cursor rawQuery4 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*), IFNULL(SUM(pnl),0), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0) FROM trades WHERE user_id=? AND status='CLOSED'", new String[]{String.valueOf(j)});
        if (rawQuery4.moveToFirst()) {
            i = rawQuery4.getInt(0);
            d5 = rawQuery4.getDouble(1);
            i2 = rawQuery4.getInt(2);
        } else {
            i = 0;
            i2 = 0;
            d5 = 0.0d;
        }
        rawQuery4.close();
        JSONArray jSONArray2 = new JSONArray();
        int i6 = i2;
        Cursor rawQuery5 = this.db.getReadableDatabase().rawQuery("SELECT value FROM (SELECT value, ts FROM equity ORDER BY ts DESC LIMIT 48) ORDER BY ts", null);
        while (rawQuery5.moveToNext()) {
            jSONArray2.put(round2(rawQuery5.getDouble(0)));
            i = i;
        }
        int i7 = i;
        rawQuery5.close();
        JSONObject jSONObject2 = new JSONObject();
        try {
            if (this.engine != null) {
                jSONObject2 = new JSONObject(this.engine.status());
            }
        } catch (Throwable unused) {
        }
        try {
            PowerManager powerManager = (PowerManager) this.appCtx.getSystemService("power");
            jSONObject2.put("battery_ok", powerManager != null && powerManager.isIgnoringBatteryOptimizations(this.appCtx.getPackageName()));
        } catch (Throwable unused2) {
            jSONObject2.put("battery_ok", true);
        }
        try {
            jSONObject2.put("watchdog", "9-min Doze-safe alarm + thread watchdog + swipe-kill restart");
        } catch (Throwable unused3) {
        }
        JSONObject jSONObject3 = jSONObject2;
        Cursor rawQuery6 = this.db.getReadableDatabase().rawQuery("SELECT email, name, role FROM users WHERE id=?", new String[]{String.valueOf(j)});
        JSONObject put = new JSONObject().put("id", j);
        if (rawQuery6.moveToFirst()) {
            jSONArray = jSONArray2;
            jSONObject = put;
            put.put("email", rawQuery6.getString(0)).put("name", rawQuery6.getString(1)).put("role", rawQuery6.getString(2));
        } else {
            jSONArray = jSONArray2;
            jSONObject = put;
        }
        rawQuery6.close();
        JSONObject put2 = new JSONObject().put("balance", round2(d)).put("start", round2(d2)).put("totalPnl", round2(d5)).put("pnlPct", round2(((d - d2) / d2) * 100.0d)).put("dayPnlPct", round2(((d - d4) / d4) * 100.0d)).put("drawdownPct", round2(d3 > 0.0d ? ((d - d3) / d3) * 100.0d : 0.0d)).put("trueDD", true);
        EngineCore engineCore = this.engine;
        JSONObject put3 = put2.put("heat", round2(engineCore != null ? engineCore.heatRiskPct(j) : 0.0d));
        EngineCore engineCore2 = this.engine;
        JSONObject put4 = put3.put("heatCap", engineCore2 != null ? engineCore2.heatMaxPct() : 0.0d);
        JSONObject jSONObject4 = new JSONObject();
        EngineCore engineCore3 = this.engine;
        JSONObject put5 = jSONObject4.put("METAL", round2(engineCore3 != null ? engineCore3.bucketRiskPct(j, "METAL") : 0.0d));
        EngineCore engineCore4 = this.engine;
        JSONObject put6 = put5.put("ENERGY", round2(engineCore4 != null ? engineCore4.bucketRiskPct(j, "ENERGY") : 0.0d));
        EngineCore engineCore5 = this.engine;
        JSONObject put7 = put4.put("exposure", put6.put("AGRI", round2(engineCore5 != null ? engineCore5.bucketRiskPct(j, "AGRI") : 0.0d)));
        EngineCore engineCore6 = this.engine;
        return Res.json(200, put7.put("safeMode", engineCore6 != null && engineCore6.isSafeMode()).put("openCount", i5).put("openPnl", round2(d6)).put("equityNow", round2(d + d6)).put("closedCount", i7).put("winRate", i7 > 0 ? round2((i6 * 100.0d) / i7) : 0.0d).put("equity", jSONArray).put("engine", jSONObject3).put("user", jSONObject));
    }

    private Res instruments() throws Exception {
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, exchange, asset_class, status, discovered_at, IFNULL(last_data_at,0), note FROM instruments ORDER BY CASE status WHEN 'ACTIVE' THEN 0 WHEN 'WATCHING' THEN 1 ELSE 2 END, priority DESC", null);
        int i = 0;
        int i2 = 0;
        int i3 = 0;
        while (rawQuery.moveToNext()) {
            String string = rawQuery.getString(3);
            if ("ACTIVE".equals(string)) {
                i++;
            } else if ("WATCHING".equals(string)) {
                i2++;
            } else {
                i3++;
            }
            jSONArray.put(new JSONObject().put("symbol", rawQuery.getString(0)).put("exchange", rawQuery.getString(1)).put("assetClass", rawQuery.getString(2)).put("status", string).put("discoveredAt", rawQuery.getLong(4)).put("lastDataAt", rawQuery.getLong(5)).put("note", rawQuery.getString(6)));
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("instruments", jSONArray).put("active", i).put("watching", i2).put("pending", i3).put("total", jSONArray.length()));
    }

    private static double safeD(double d) {
        if (Double.isNaN(d) || Double.isInfinite(d)) {
            return 0.0d;
        }
        return d;
    }

    private Res indicators(String str) throws Exception {
        int indexOf = str.indexOf("?symbol=");
        String trim = indexOf > 0 ? str.substring(indexOf + 8).toUpperCase().trim() : "BTCUSDT";
        EngineCore engineCore = this.engine;
        if (engineCore == null) {
            return Res.error(503, "engine not ready");
        }
        Map<String, Object> indicatorSnapshot = engineCore.indicatorSnapshot(trim);
        indicatorSnapshot.remove("library");
        JSONObject jSONObject = new JSONObject();
        Iterator<Map.Entry<String, Object>> it = indicatorSnapshot.entrySet().iterator();
        while (true) {
            int i = 0;
            if (!it.hasNext()) {
                break;
            }
            Map.Entry<String, Object> next = it.next();
            Object value = next.getValue();
            if (value instanceof double[]) {
                JSONArray jSONArray = new JSONArray();
                double[] dArr = (double[]) value;
                int length = dArr.length;
                while (i < length) {
                    jSONArray.put(safeD(dArr[i]));
                    i++;
                }
                jSONObject.put(next.getKey(), jSONArray);
            } else if (value instanceof Object[]) {
                JSONArray jSONArray2 = new JSONArray();
                Object[] objArr = (Object[]) value;
                int length2 = objArr.length;
                while (i < length2) {
                    Object obj = objArr[i];
                    jSONArray2.put(obj == null ? "" : String.valueOf(obj));
                    i++;
                }
                jSONObject.put(next.getKey(), jSONArray2);
            } else if (value instanceof Map) {
                JSONObject jSONObject2 = new JSONObject();
                for (Map.Entry entry : ((Map<Object, Object>) value).entrySet()) {
                    Object value2 = entry.getValue();
                    if (value2 instanceof Number) {
                        jSONObject2.put(String.valueOf(entry.getKey()), safeD(((Number) value2).doubleValue()));
                    } else {
                        jSONObject2.put(String.valueOf(entry.getKey()), String.valueOf(value2));
                    }
                }
                jSONObject.put(next.getKey(), jSONObject2);
            } else if (value instanceof Number) {
                jSONObject.put(next.getKey(), safeD(((Number) value).doubleValue()));
            } else if (value instanceof Boolean) {
                jSONObject.put(next.getKey(), (Boolean) value);
            } else {
                jSONObject.put(next.getKey(), String.valueOf(value));
            }
        }
        JSONArray jSONArray3 = new JSONArray();
        for (String[] strArr : EngineCore.INDICATOR_LIBRARY) {
            jSONArray3.put(new JSONArray().put(strArr[0]).put(strArr[1]).put(strArr[2]));
        }
        jSONObject.put("library", jSONArray3);
        return Res.json(200, jSONObject);
    }

    private Res news() throws Exception {
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts, source, headline, sentiment, impact FROM news ORDER BY id DESC LIMIT 60", null);
        while (true) {
            if (!rawQuery.moveToNext()) {
                break;
            }
            jSONArray.put(new JSONObject().put("ts", rawQuery.getLong(0)).put("source", rawQuery.getString(1)).put("headline", rawQuery.getString(2)).put("sentiment", rawQuery.getString(3)).put("impact", rawQuery.getString(4)));
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("news", jSONArray).put("pauseActive", System.currentTimeMillis() < enginePauseUntil()));
    }

    private long enginePauseUntil() {
        try {
            if (this.engine != null && new JSONObject(this.engine.status()).optBoolean("news_pause")) {
                return System.currentTimeMillis() + 1000;
            }
            return 0L;
        } catch (Throwable unused) {
            return 0L;
        }
    }

    private double livePrice(String str) {
        // v1.4: engine ka 1-second LIVE TICK pehle (fresh <10s), warna candle fallback
        EngineCore engineCore = this.engine;
        if (engineCore != null) {
            try {
                double p = engineCore.livePrice(str);
                if (p > 0.0d && !Double.isNaN(p)) {
                    return p;
                }
            } catch (Throwable unused) {
            }
        }
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT c FROM candles WHERE symbol=? AND tf='5m' ORDER BY ts DESC LIMIT 1", new String[]{str});
        double d = rawQuery.moveToFirst() ? rawQuery.getDouble(0) : Double.NaN;
        rawQuery.close();
        return d;
    }

    private Res trades(long j) throws Exception {
        JSONArray jSONArray = null;
        Api api = this;
        JSONArray jSONArray2 = new JSONArray();
        int i = 1;
        int i2 = 0;
        Cursor rawQuery = api.db.getReadableDatabase().rawQuery("SELECT id, symbol, side, qty, entry, sl, tp, exit, pnl, status, strategy, consensus, opened_at, closed_at, IFNULL(r_mult,0), IFNULL(mfe,0), IFNULL(mae,0), IFNULL(tca_bps,0), IFNULL(council,0), IFNULL(win_prob,0) FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 100", new String[]{String.valueOf(j)});
        int i3 = 0;
        double d = 0.0d;
        while (rawQuery.moveToNext()) {
            String string = rawQuery.getString(9);
            double d2 = d;
            JSONObject put = new JSONObject().put("id", rawQuery.getLong(i2)).put("symbol", rawQuery.getString(i)).put("side", rawQuery.getString(2)).put("qty", rawQuery.getDouble(3)).put("entry", rawQuery.getDouble(4)).put("sl", rawQuery.getDouble(5)).put("tp", rawQuery.getDouble(6)).put("exit", rawQuery.isNull(7) ? JSONObject.NULL : Double.valueOf(rawQuery.getDouble(7))).put("pnl", rawQuery.isNull(8) ? JSONObject.NULL : Double.valueOf(round2(rawQuery.getDouble(8)))).put("status", string).put("strategy", rawQuery.getString(10)).put("consensus", rawQuery.getDouble(11)).put("openedAt", rawQuery.getLong(12)).put("closedAt", rawQuery.isNull(13) ? 0L : rawQuery.getLong(13)).put("rMult", rawQuery.getDouble(14)).put("mfe", round2(rawQuery.getDouble(15))).put("mae", round2(rawQuery.getDouble(16))).put("tcaBps", rawQuery.getDouble(17)).put("council", rawQuery.getInt(18)).put("winProb", rawQuery.getDouble(19));
            if ("OPEN".equals(string)) {
                double livePrice = api.livePrice(rawQuery.getString(i));
                if (!Double.isNaN(livePrice)) {
                    double d3 = rawQuery.getDouble(3);
                    double d4 = rawQuery.getDouble(4);
                    double d5 = rawQuery.getDouble(6);
                    double d6 = ("BUY".equals(rawQuery.getString(2)) ? livePrice - d4 : d4 - livePrice) * d3;
                    jSONArray = jSONArray2;
                    put.put("price", livePrice).put("pnlLive", round2(d6));
                    double d7 = d2 + d6;
                    i3++;
                    String string2 = rawQuery.getString(10);
                    if (string2 != null && string2.startsWith("3C")) {
                        if (Math.abs(d5 - d4) / 3.0d > 0.0d && d3 > 0.0d) {
                            put.put("rNow", Math.round((d6 / (Math.abs(d5 - d4) * d3)) * 100.0d) / 100.0d);
                        }
                    }
                    d2 = d7;
                    jSONArray.put(put);
                    api = this;
                    jSONArray2 = jSONArray;
                    d = d2;
                    i = 1;
                    i2 = 0;
                }
            }
            jSONArray = jSONArray2;
            jSONArray.put(put);
            api = this;
            jSONArray2 = jSONArray;
            d = d2;
            i = 1;
            i2 = 0;
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("trades", jSONArray2).put("floating", round2(d)).put("floatingCount", i3));
    }

    private Res logs() throws Exception {
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT ts, level, component, event, details FROM logs ORDER BY id DESC LIMIT 150", null);
        while (rawQuery.moveToNext()) {
            jSONArray.put(new JSONObject().put("ts", rawQuery.getLong(0)).put("level", rawQuery.getString(1)).put("component", rawQuery.getString(2)).put("event", rawQuery.getString(3)).put("details", rawQuery.getString(4)));
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("logs", jSONArray));
    }

    private Res analytics(long j) throws Exception {
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        JSONArray jSONArray = new JSONArray();
        int i = 2;
        int i2 = 0;
        int i3 = 1;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT CAST(closed_at/86400000 AS INTEGER) d, SUM(pnl), COUNT(*) FROM trades WHERE user_id=? AND status='CLOSED' AND closed_at >= ? GROUP BY d ORDER BY d", new String[]{String.valueOf(j), String.valueOf(System.currentTimeMillis() - 2592000000L)});
        while (rawQuery.moveToNext()) {
            jSONArray.put(new JSONObject().put("day", rawQuery.getLong(0)).put("pnl", round2(rawQuery.getDouble(1))).put("n", rawQuery.getInt(2)));
        }
        rawQuery.close();
        JSONArray jSONArray2 = new JSONArray();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT symbol, COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), IFNULL(SUM(pnl),0), IFNULL(SUM(CASE WHEN pnl>0 THEN pnl ELSE 0 END),0), IFNULL(SUM(CASE WHEN pnl<=0 THEN -pnl ELSE 0 END),0), IFNULL(AVG(closed_at-opened_at),0), IFNULL(AVG(r_mult),0) FROM trades WHERE user_id=? AND status='CLOSED' GROUP BY symbol ORDER BY SUM(pnl) DESC", new String[]{String.valueOf(j)});
        while (true) {
            d = 0.0d;
            if (!rawQuery2.moveToNext()) {
                break;
            }
            int i4 = rawQuery2.getInt(i3);
            int i5 = rawQuery2.getInt(i);
            double d4 = rawQuery2.getDouble(5);
            JSONObject put = new JSONObject().put("symbol", rawQuery2.getString(i2)).put("n", i4).put("wins", i5).put("winrate", i4 > 0 ? Math.round((i5 * 1000.0d) / i4) / 10.0d : 0.0d).put("net", round2(rawQuery2.getDouble(3)));
            if (d4 > 0.0d) {
                d3 = Math.round((rawQuery2.getDouble(4) / d4) * 100.0d) / 100.0d;
            } else {
                d3 = rawQuery2.getDouble(4) > 0.0d ? 99 : 0;
            }
            jSONArray2.put(put.put("pf", d3).put("avgMin", Math.round(rawQuery2.getDouble(6) / 60000.0d)).put("avgR", Math.round(rawQuery2.getDouble(7) * 1000.0d) / 1000.0d));
            i = 2;
            i2 = 0;
            i3 = 1;
        }
        rawQuery2.close();
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        int i6 = 0;
        Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT CAST(closed_at/86400000 AS INTEGER) d, SUM(pnl) FROM trades WHERE user_id=? AND status='CLOSED' GROUP BY d", new String[]{String.valueOf(j)});
        LinkedHashMap linkedHashMap2 = new LinkedHashMap();
        while (rawQuery3.moveToNext()) {
            Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
            calendar.setTimeInMillis(rawQuery3.getLong(i6) * 86400000);
            linkedHashMap2.merge(calendar.get(1) + "-" + String.format(Locale.US, "%02d", Integer.valueOf(calendar.get(2) + 1)), Double.valueOf(rawQuery3.getDouble(1)), new BiFunction() { // from class: com.aitradinglab.engine.Api$$ExternalSyntheticLambda0
                @Override // java.util.function.BiFunction
                public final Object apply(Object obj, Object obj2) {
                    double sum = 0.0d;
                    sum = Double.sum(((Double) obj).doubleValue(), ((Double) obj2).doubleValue());
                    return Double.valueOf(sum);
                }
            });
            i6 = 0;
        }
        rawQuery3.close();
        for (Map.Entry entry : ((Map<Object, Object>) linkedHashMap2).entrySet()) {
            linkedHashMap.put((String) entry.getKey(), new JSONObject().put("month", entry.getKey()).put("pnl", round2(((Double) entry.getValue()).doubleValue())));
        }
        int[] iArr = new int[9];
        int i7 = 0;
        Cursor rawQuery4 = this.db.getReadableDatabase().rawQuery("SELECT r_mult FROM trades WHERE user_id=? AND status='CLOSED' AND r_mult != 0", new String[]{String.valueOf(j)});
        while (rawQuery4.moveToNext()) {
            double d5 = rawQuery4.getDouble(i7);
            char c = d5 < -3.0d ? (char) 0 : d5 < -2.0d ? (char) 1 : d5 < -1.0d ? (char) 2 : d5 < 0.0d ? (char) 3 : d5 < 1.0d ? (char) 4 : d5 < 2.0d ? (char) 5 : d5 < 3.0d ? (char) 6 : d5 < 4.0d ? (char) 7 : '\b';
            iArr[c] = iArr[c] + 1;
            i7 = 0;
        }
        rawQuery4.close();
        JSONArray jSONArray3 = new JSONArray();
        for (int i8 = 0; i8 < 9; i8++) {
            jSONArray3.put(iArr[i8]);
        }
        int i9 = 0;
        Cursor rawQuery5 = this.db.getReadableDatabase().rawQuery("SELECT IFNULL(SUM((qty*entry+qty*exit)*0.0005),0), IFNULL(AVG(tca_bps),0), COUNT(*) FROM trades WHERE user_id=? AND status='CLOSED'", new String[]{String.valueOf(j)});
        if (rawQuery5.moveToFirst()) {
            d = rawQuery5.getDouble(0);
            d2 = rawQuery5.getDouble(1);
            i9 = rawQuery5.getInt(2);
        } else {
            d2 = 0.0d;
        }
        rawQuery5.close();
        return Res.json(200, new JSONObject().put("ok", true).put("daily", jSONArray).put("symbols", jSONArray2).put("monthly", new JSONArray(linkedHashMap.values())).put("rHist", jSONArray3).put("fees", round2(d)).put("avgTcaBps", Math.round(d2 * 100.0d) / 100.0d).put("nClosed", i9));
    }

    private Res seasonality(String str) throws Exception {
        int indexOf = str.indexOf("?symbol=");
        String trim = indexOf > 0 ? str.substring(indexOf + 8).toUpperCase(Locale.US).trim() : "BTCUSDT";
        if (!trim.matches("[A-Z0-9]{4,20}")) {
            return Res.error(400, "Symbol galat");
        }
        EngineCore engineCore = this.engine;
        if (engineCore == null) {
            return Res.error(503, "engine band hai");
        }
        JSONObject seasonality = engineCore.seasonality(trim, indexOf > 0 && str.contains("refresh=1"));
        if (seasonality == null) {
            return Res.error(503, "Seasonality data abhi fetch nahi hua — dobara try karein");
        }
        return Res.json(200, new JSONObject().put("ok", true).put("seasonality", seasonality));
    }

    private Res auditCsv(long j) throws Exception {
        StringBuilder sb = new StringBuilder("type,id,trade_id,symbol,side,qty_or_status,price,source_or_entry,status_or_exit,ts\n");
        int i = 0;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, symbol, side, qty, entry, exit, pnl, status, strategy, opened_at, closed_at, IFNULL(r_mult,0), IFNULL(tca_bps,0) FROM trades WHERE user_id=? ORDER BY id", new String[]{String.valueOf(j)});
        while (rawQuery.moveToNext()) {
            sb.append("TRADE,").append(rawQuery.getLong(0)).append(",").append(rawQuery.getLong(0)).append(',').append(rawQuery.getString(1)).append(',').append(rawQuery.getString(2)).append(',').append(rawQuery.getDouble(3)).append(',').append(rawQuery.getDouble(4)).append(',').append(rawQuery.getString(7)).append(',').append(rawQuery.isNull(5) ? "" : Double.valueOf(rawQuery.getDouble(5))).append(',').append(rawQuery.isNull(6) ? 0.0d : rawQuery.getDouble(6)).append(",").append(rawQuery.getString(8)).append(',').append(rawQuery.getLong(9)).append(',').append(rawQuery.isNull(10) ? 0L : rawQuery.getLong(10)).append(',').append(rawQuery.getDouble(11)).append(',').append(rawQuery.getDouble(12)).append('\n');
        }
        rawQuery.close();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT id, trade_id, symbol, side, type, price, qty, status, source, ts FROM orders ORDER BY id", null);
        while (rawQuery2.moveToNext()) {
            sb.append("ORDER,").append(rawQuery2.getLong(i)).append(',').append(rawQuery2.getLong(1)).append(',').append(rawQuery2.getString(2)).append(',').append(rawQuery2.getString(3)).append(',').append(rawQuery2.getString(8)).append(',').append(rawQuery2.getDouble(5)).append(',').append(rawQuery2.getDouble(6)).append(',').append(rawQuery2.getString(4)).append(',').append(rawQuery2.getString(7)).append(',').append(rawQuery2.getLong(9)).append('\n');
            i = 0;
        }
        rawQuery2.close();
        Res res = new Res();
        res.contentType = "text/csv; charset=utf-8";
        res.body = sb.toString();
        this.db.log("INFO", "AUDIT", "AUDIT_EXPORT", "user #" + j + " — full audit trail (trades + orders) exported");
        return res;
    }

    private Res brokers() throws Exception {
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, name, kind, IFNULL(server,''), status, added_at FROM brokers ORDER BY id DESC", null);
        while (rawQuery.moveToNext()) {
            jSONArray.put(new JSONObject().put("id", rawQuery.getLong(0)).put("name", rawQuery.getString(1)).put("kind", rawQuery.getString(2)).put("server", rawQuery.getString(3)).put("status", rawQuery.getString(4)).put("addedAt", rawQuery.getLong(5)));
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("brokers", jSONArray));
    }

    private Res addBroker(String str) throws Exception {
        JSONObject jObj = HttpServer.jObj(str);
        String jStr = HttpServer.jStr(jObj, "name");
        String jStr2 = HttpServer.jStr(jObj, "kind");
        String jStr3 = HttpServer.jStr(jObj, "server");
        String jStr4 = HttpServer.jStr(jObj, "apiKey");
        String jStr5 = HttpServer.jStr(jObj, "apiSecret");
        String jStr6 = HttpServer.jStr(jObj, "login");
        String jStr7 = HttpServer.jStr(jObj, "password");
        if (jStr.length() < 2) {
            return Res.error(400, "Enter a broker name");
        }
        boolean contains = jStr2.toUpperCase(Locale.US).contains("MT");
        if (contains && (jStr6.isEmpty() || jStr7.isEmpty())) {
            return Res.error(400, "MT5/MT4 ke liye Login + Password zaroori hain (API key optional hai)");
        }
        if (!contains && jStr4.length() < 8) {
            return Res.error(400, "Enter the API key from your broker");
        }
        this.db.getWritableDatabase().execSQL("INSERT INTO brokers(name, kind, api_key, api_secret, login, password, server, status, added_at) VALUES(?,?,?,?,?,?,?,'SAVED',?)", new Object[]{jStr, jStr2.isEmpty() ? "MT5" : jStr2, jStr4, jStr5, jStr6, jStr7, jStr3, Long.valueOf(System.currentTimeMillis())});
        Db db = this.db;
        StringBuilder append = new StringBuilder().append(jStr).append(" (");
        if (jStr2.isEmpty()) {
            jStr2 = "MT5";
        }
        db.log("INFO", "BROKER", "ADDED", append.append(jStr2).append(jStr3.isEmpty() ? "" : " @ " + jStr3).append(") — credentials saved on this device").toString());
        return Res.json(200, new JSONObject().put("ok", true).put("message", "Broker saved. Credentials is device par safe hain — live trading phase me connect hoga. (Paper trading abhi chal rahi hai — MT5 data feed se.)"));
    }

    private Res testBroker(String str) throws Exception {
        return Res.json(200, new JSONObject().put("ok", true).put("message", HttpServer.jStr(HttpServer.jObj(str), "name") + " credentials verified as SAVED (local storage). Live connection test happens when live trading is enabled — this build runs paper trading only."));
    }

    private Res closeTrade(long j, String str) throws Exception {
        long optLong = HttpServer.jObj(str).optLong("id", -1L);
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT qty, entry, side, symbol FROM trades WHERE id=? AND user_id=? AND status='OPEN'", new String[]{String.valueOf(optLong), String.valueOf(j)});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            return Res.error(404, "trade not found");
        }
        double d = rawQuery.getDouble(0);
        double d2 = rawQuery.getDouble(1);
        String string = rawQuery.getString(2);
        String string4 = rawQuery.getString(3);
        rawQuery.close();
        // v1.4: manual close ab 1-second LIVE price par — owner tap kare to market price par hi band ho
        double d3 = livePrice(string4);
        if (Double.isNaN(d3) || d3 <= 0.0d) {
            d3 = d2;
        }
        double d4 = ("BUY".equals(string) ? d3 - d2 : d2 - d3) * d;
        this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=?, pnl=?, status='CLOSED', closed_at=? WHERE id=?", new Object[]{Double.valueOf(d3), Double.valueOf(d4), Long.valueOf(System.currentTimeMillis()), Long.valueOf(optLong)});
        this.db.getWritableDatabase().execSQL("UPDATE accounts SET balance=balance+? WHERE user_id=?", new Object[]{Double.valueOf(d4), Long.valueOf(j)});
        this.db.log("INFO", "EXECUTOR", "MANUAL_CLOSE", "trade #" + optLong + " closed by user, pnl=" + String.format(Locale.US, "%.2f", Double.valueOf(d4)));
        return Res.json(200, new JSONObject().put("ok", true).put("pnl", round2(d4)));
    }

    private Res settings() throws Exception {
        JSONObject put = new JSONObject().put("engineOn", "1".equals(this.db.setting("engine_on", "1")));
        EngineCore engineCore = this.engine;
        JSONObject put2 = put.put("riskPct", engineCore != null ? engineCore.riskPct() : 2.0d).put("mt5Bridge", this.db.setting("mt5_bridge", ""));
        EngineCore engineCore2 = this.engine;
        JSONObject put3 = put2.put("cooldownMin", engineCore2 != null ? engineCore2.cooldownMin() : 15);
        EngineCore engineCore3 = this.engine;
        JSONObject put4 = put3.put("consecLoss", engineCore3 != null ? engineCore3.consecLossN() : 3);
        EngineCore engineCore4 = this.engine;
        JSONObject put5 = put4.put("dailyKillPct", engineCore4 != null ? engineCore4.dailyKillPct() : 0.0d).put("feePct", 0.05d);
        EngineCore engineCore5 = this.engine;
        JSONObject put6 = put5.put("levCap", engineCore5 != null ? engineCore5.levCap() : 0.95d).put("feeBps", this.db.setting("fee_bps", "5")).put("x7On", "1".equals(this.db.setting("x7_on", "1")));
        EngineCore engineCore6 = this.engine;
        JSONObject put7 = put6.put("slipBps", engineCore6 != null ? engineCore6.slipBps() : 2.0d);
        EngineCore engineCore7 = this.engine;
        JSONObject put8 = put7.put("heatMaxPct", engineCore7 != null ? engineCore7.heatMaxPct() : 0.0d);
        EngineCore engineCore8 = this.engine;
        JSONObject put9 = put8.put("bucketMaxPct", engineCore8 != null ? engineCore8.bucketMaxPct() : 0.0d);
        EngineCore engineCore9 = this.engine;
        boolean z = false;
        JSONObject put10 = put9.put("councilMin", engineCore9 != null ? engineCore9.councilMin() : 0);
        EngineCore engineCore10 = this.engine;
        JSONObject put11 = put10.put("eventGate", engineCore10 != null && engineCore10.eventGateOn()).put("autoPause", "1".equals(this.db.setting("auto_pause", "0")));
        EngineCore engineCore11 = this.engine;
        JSONObject put12 = put11.put("sessionFilter", engineCore11 != null && engineCore11.sessionFilterOn());
        EngineCore engineCore12 = this.engine;
        JSONObject put13 = put12.put("bridgeLive", engineCore12 != null && engineCore12.bridgeLive());
        EngineCore engineCore13 = this.engine;
        JSONObject put14 = put13.put("bridgeLots", engineCore13 != null ? engineCore13.bridgeLots() : 0.01d).put("aiAutoTrain", "1".equals(this.db.setting("ai_auto_train", "1"))).put("feeEdgeOn", "1".equals(this.db.setting("fee_edge_on", "1"))).put("minFeeEdgePct", this.db.setting("min_fee_edge_pct", "0.14")).put("packOn", "1".equals(this.db.setting("pack_on", "0"))).put("aiTrainedAt", this.db.setting("ai_trained_at", "0")).put("feedIntervalSec", this.db.setting("feed_interval_sec", "60")).put("labSymbol", this.db.setting("lab_symbol", "BTCUSDT"));
        EngineCore engineCore14 = this.engine;
        if (engineCore14 != null && engineCore14.isSafeMode()) {
            z = true;
        }
        return Res.json(200, put14.put("safeMode", z).put("version", "4.4"));
    }

    private Res candles(String str, long j) throws Exception {
        int i = 0;
        String trim = qParam("symbol").toUpperCase(Locale.US).trim();
        if (!trim.matches("[A-Z0-9]{4,20}")) {
            return Res.error(400, "Symbol galat hai (e.g. BTCUSDT)");
        }
        try {
            i = Integer.parseInt(qParam("n"));
        } catch (Exception unused) {
            i = 60;
        }
        EngineCore engineCore = this.engine;
        if (engineCore == null) {
            return Res.error(503, "engine band hai");
        }
        List<EngineCore.Candle> recentCandles = engineCore.recentCandles(trim, i);
        JSONArray jSONArray = new JSONArray();
        for (EngineCore.Candle candle : recentCandles) {
            jSONArray.put(new JSONObject().put("ts", candle.ts).put("o", candle.o).put("h", candle.h).put("l", candle.l).put("c", candle.c).put("v", candle.v));
        }
        JSONObject put = new JSONObject().put("ok", true).put("symbol", trim).put("candles", jSONArray).put("count", jSONArray.length());
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT side, entry, sl, tp FROM trades WHERE user_id=? AND symbol=? AND status='OPEN' ORDER BY id DESC LIMIT 1", new String[]{String.valueOf(j), trim});
        if (rawQuery.moveToFirst()) {
            put.put("trade", new JSONObject().put("side", rawQuery.getString(0)).put("entry", rawQuery.getDouble(1)).put("sl", rawQuery.getDouble(2)).put("tp", rawQuery.getDouble(3)));
        }
        rawQuery.close();
        return Res.json(200, put);
    }

    private Res setBalance(long j, String str) throws Exception {
        double optDouble = HttpServer.jObj(str).optDouble("amount", Double.NaN);
        if (Double.isNaN(optDouble) || optDouble < 10.0d || optDouble > 1.0E8d) {
            return Res.error(400, "Paper balance $10 se $100,000,000 ke beech set karein");
        }
        long currentTimeMillis = System.currentTimeMillis();
        this.db.getWritableDatabase().execSQL("UPDATE trades SET exit=entry, pnl=0, status='CANCELLED', closed_at=? WHERE user_id=? AND status='OPEN'", new Object[]{Long.valueOf(currentTimeMillis), Long.valueOf(j)});
        this.db.getWritableDatabase().execSQL("UPDATE accounts SET balance=?, start_balance=?, peak=?, day_start=?, day_ts=? WHERE user_id=?", new Object[]{Double.valueOf(optDouble), Double.valueOf(optDouble), Double.valueOf(optDouble), Double.valueOf(optDouble), Long.valueOf(currentTimeMillis / 86400000), Long.valueOf(j)});
        this.db.log("INFO", "ACCOUNT", "BALANCE_SET", "user #" + j + " — paper balance set to $" + String.format(Locale.US, "%.2f", Double.valueOf(optDouble)) + " (open trades cancelled, risk counters reset)");
        JSONObject put = new JSONObject().put("ok", true).put("balance", round2(optDouble));
        StringBuilder append = new StringBuilder("Paper balance set: $").append(String.format(Locale.US, "%.0f", Double.valueOf(optDouble))).append(" — ab 3C MASTER har trade ");
        EngineCore engineCore = this.engine;
        return Res.json(200, put.put("message", append.append(engineCore != null ? engineCore.riskPct() : 1.0d).append("% risk leggi (Settings > Risk %) — daily loss/profit UNLIMITED").toString()));
    }

    private String qParam(String str) {
        String str2 = this.query;
        if (str2 != null && !str2.isEmpty()) {
            for (String str3 : this.query.split("&")) {
                int indexOf = str3.indexOf(61);
                if (indexOf > 0 && str3.substring(0, indexOf).equals(str)) {
                    int i = indexOf + 1;
                    try {
                        return URLDecoder.decode(str3.substring(i), "UTF-8");
                    } catch (Exception unused) {
                        return str3.substring(i);
                    }
                }
            }
        }
        return "";
    }

    private Res strategyAction(StrategyLab strategyLab, String str) throws Exception {
        JSONObject jObj = null;
        String jStr = null;
        String jStr2 = null;
        String jStr3 = null;
        long optLong = 0L;
        JSONObject remove = null;
        jObj = HttpServer.jObj(str);
        jStr = HttpServer.jStr(jObj, "action");
        jStr2 = HttpServer.jStr(jObj, "text");
        jStr3 = HttpServer.jStr(jObj, "url");
        optLong = jObj.optLong("id", -1L);
        jStr.hashCode();
        switch (jStr) {
            case "delete":
                remove = strategyLab.remove(optLong);
                break;
            case "set_symbol":
                String upperCase = HttpServer.jStr(jObj, "symbol").toUpperCase(Locale.US);
                if (!upperCase.matches("[A-Z0-9]{5,20}")) {
                    return Res.error(400, "Symbol format galat hai (e.g. BTCUSDT)");
                }
                this.db.setSetting("lab_symbol", upperCase);
                remove = new JSONObject().put("ok", true).put("message", "Backtest symbol: " + upperCase);
                break;
            case "reject":
                remove = strategyLab.reject(optLong);
                break;
            case "yt_stop":
                strategyLab.stopChannel();
                remove = new JSONObject().put("ok", true).put("message", "Channel watcher band ho gaya");
                break;
            case "approve":
                remove = strategyLab.approve(optLong);
                break;
            case "yt_add":
                if (!jStr3.isEmpty()) {
                    remove = strategyLab.addYouTube(jStr3);
                    break;
                } else {
                    return Res.error(400, "YouTube video ka link dein");
                }
            case "add":
                if (!jStr2.isEmpty()) {
                    remove = strategyLab.addManual(jStr2);
                    break;
                } else {
                    return Res.error(400, "Strategy likhein — kisi bhi zubaan mein");
                }
            case "paper":
                remove = strategyLab.startPaper(optLong);
                break;
            case "trash":
                remove = strategyLab.trash();
                break;
            case "restore":
                remove = strategyLab.restore(optLong);
                break;
            case "yt_channel":
                if (!jStr3.isEmpty()) {
                    remove = strategyLab.subscribeChannel(jStr3);
                    break;
                } else {
                    return Res.error(400, "Channel ka link dein (@handle ya /channel/UC...)");
                }
            case "backtest":
                remove = strategyLab.backtest(optLong);
                break;
            default:
                return Res.error(400, "Unknown action: " + jStr);
        }
        if (remove == null) {
            return Res.error(502, "AI service fail — thori dair baad dobara try karein");
        }
        return !remove.optBoolean("ok", true) ? Res.json(502, remove) : Res.json(200, remove);
    }

    private Res history(long j) throws Exception {
        int i = 1;
        int i2 = 0;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT CAST(strftime('%Y', opened_at/1000, 'unixepoch') AS TEXT) y, CAST(strftime('%m', opened_at/1000, 'unixepoch') AS TEXT) m, CAST(strftime('%d', opened_at/1000, 'unixepoch') AS TEXT) d, COUNT(*), IFNULL(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0), IFNULL(ROUND(SUM(pnl),2),0), IFNULL(ROUND(SUM(qty*entry),2),0) FROM trades WHERE user_id=? AND status='CLOSED' AND opened_at IS NOT NULL GROUP BY y, m, d ORDER BY y DESC, m DESC, d DESC", new String[]{String.valueOf(j)});
        LinkedHashMap linkedHashMap = new LinkedHashMap();
        LinkedHashMap linkedHashMap2 = new LinkedHashMap();
        JSONArray jSONArray = new JSONArray();
        while (rawQuery.moveToNext()) {
            String string = rawQuery.getString(i2);
            String string2 = rawQuery.getString(i);
            String string3 = rawQuery.getString(2);
            long j2 = rawQuery.getLong(3);
            long j3 = rawQuery.getLong(4);
            double d = rawQuery.getDouble(5);
            JSONArray jSONArray2 = jSONArray;
            double d2 = rawQuery.getDouble(6);
            JSONObject jSONObject = (JSONObject) linkedHashMap.get(string);
            Cursor cursor = rawQuery;
            if (jSONObject == null) {
                jSONObject = new JSONObject().put("y", string).put("trades", 0).put("wins", 0).put("pnl", 0).put("months", new JSONArray());
                linkedHashMap.put(string, jSONObject);
            }
            LinkedHashMap linkedHashMap3 = linkedHashMap;
            JSONObject jSONObject2 = (JSONObject) linkedHashMap2.get(string + "-" + string2);
            if (jSONObject2 == null) {
                jSONObject2 = new JSONObject().put("m", string2).put("y", string).put("trades", 0).put("wins", 0).put("pnl", 0).put("days", new JSONArray());
                linkedHashMap2.put(string + "-" + string2, jSONObject2);
                ((JSONArray) jSONObject.get("months")).put(jSONObject2);
            }
            JSONObject put = new JSONObject().put("d", string3).put("trades", j2).put("wins", j3).put("pnl", d);
            JSONObject jSONObject3 = jSONObject;
            JSONObject put2 = put.put("vol", d2);
            ((JSONArray) jSONObject2.get("days")).put(put2);
            jSONObject2.put("trades", jSONObject2.optLong("trades") + j2).put("wins", jSONObject2.optLong("wins") + j3).put("pnl", Math.round((jSONObject2.optDouble("pnl") + d) * 100.0d) / 100.0d);
            jSONObject3.put("trades", jSONObject3.optLong("trades") + j2).put("wins", jSONObject3.optLong("wins") + j3).put("pnl", Math.round((jSONObject3.optDouble("pnl") + d) * 100.0d) / 100.0d);
            jSONArray2.put(put2);
            linkedHashMap2 = linkedHashMap2;
            jSONArray = jSONArray2;
            rawQuery = cursor;
            linkedHashMap = linkedHashMap3;
            i = 1;
            i2 = 0;
        }
        rawQuery.close();
        JSONArray jSONArray3 = new JSONArray();
        Iterator it = linkedHashMap.values().iterator();
        while (it.hasNext()) {
            jSONArray3.put((JSONObject) it.next());
        }
        return Res.json(200, new JSONObject().put("ok", true).put("years", jSONArray3));
    }

    private Res historyCsv(long j) throws Exception {
        try {
            int parseInt = Integer.parseInt(qParam("y"));
            int parseInt2 = Integer.parseInt(qParam("m"));
            int i = 1;
            if (parseInt2 < 1 || parseInt2 > 12 || parseInt < 2020 || parseInt > 2100) {
                return Res.error(400, "Month/year range galat hai");
            }
            Calendar calendar = Calendar.getInstance(TimeZone.getTimeZone("UTC"));
            calendar.set(parseInt, parseInt2 - 1, 1, 0, 0, 0);
            int i2 = 0;
            calendar.set(14, 0);
            long timeInMillis = calendar.getTimeInMillis();
            int i3 = 2;
            calendar.add(2, 1);
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT symbol, side, qty, entry, sl, tp, exit, pnl, strategy, consensus, risk, opened_at, closed_at FROM trades WHERE user_id=? AND status='CLOSED' AND opened_at BETWEEN ? AND ? ORDER BY opened_at ASC", new String[]{String.valueOf(j), String.valueOf(timeInMillis), String.valueOf(calendar.getTimeInMillis() - 1)});
            StringBuilder sb = new StringBuilder("date,symbol,side,qty,entry,sl,tp,exit,pnl,risk_pct,strategy,consensus_pct,opened_at_ms,closed_at_ms\n");
            SimpleDateFormat simpleDateFormat = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US);
            simpleDateFormat.setTimeZone(TimeZone.getTimeZone("UTC"));
            int i4 = 0;
            while (rawQuery.moveToNext()) {
                String str = "";
                StringBuilder append = sb.append(simpleDateFormat.format(new Date(rawQuery.getLong(11)))).append(',').append(rawQuery.getString(i2)).append(',').append(rawQuery.getString(i)).append(',').append(rawQuery.getDouble(i3)).append(',').append(rawQuery.getDouble(3)).append(',').append(rawQuery.getDouble(4)).append(',').append(rawQuery.getDouble(5)).append(',').append(rawQuery.getDouble(6)).append(',').append(rawQuery.getDouble(7)).append(',').append(rawQuery.isNull(10) ? "" : String.format(Locale.US, "%.1f", Double.valueOf(rawQuery.getDouble(10) * 100.0d))).append(",\"").append(rawQuery.getString(8).replace("\"", "'")).append("\",");
                if (!rawQuery.isNull(9)) {
                    str = String.format(Locale.US, "%.0f", Double.valueOf(rawQuery.getDouble(9) * 100.0d));
                }
                append.append(str).append(',').append(rawQuery.getLong(11)).append(',').append(rawQuery.getLong(12)).append('\n');
                i4++;
                i3 = 2;
                i2 = 0;
                i = 1;
            }
            rawQuery.close();
            Res res = new Res();
            res.contentType = "text/csv; charset=utf-8";
            res.body = sb.toString();
            this.db.log("INFO", "HISTORY", "CSV_EXPORT", "user #" + j + " — " + parseInt + "-" + String.format(Locale.US, "%02d", Integer.valueOf(parseInt2)) + ": " + i4 + " trades exported");
            return res;
        } catch (Exception unused) {
            return Res.error(400, "y aur m chahiye (e.g. ?y=2026&m=01)");
        }
    }

    private Res saveSettings(String str) throws Exception {
        String str2 = null;
        JSONObject jObj = HttpServer.jObj(str);
        if (jObj.has("engineOn")) {
            boolean optBoolean = jObj.optBoolean("engineOn");
            this.db.setSetting("engine_on", optBoolean ? "1" : "0");
            this.db.log("INFO", "SYSTEM", optBoolean ? "ENGINE_ENABLED" : "ENGINE_DISABLED", "user toggled engine");
        }
        if (jObj.has("packOn")) {
            this.db.setSetting("pack_on", jObj.optBoolean("packOn") ? "1" : "0");
            this.db.log("INFO", "PACK", "PACK_SET", "PDF Strategy Pack = " + jObj.optBoolean("packOn"));
        }
        if (jObj.has("packKey") && jObj.has("packVal")) {
            String optString = jObj.optString("packKey", "");
            if (optString.matches("[A-Za-z0-9_]+")) {
                this.db.setSetting("pack_" + optString.toLowerCase(Locale.ROOT), jObj.optBoolean("packVal") ? "1" : "0");
                this.db.log("INFO", "PACK", "STRATEGY_TOGGLE", optString + " = " + jObj.optBoolean("packVal"));
            }
        }
        if (jObj.has("aiAutoTrain")) {
            this.db.setSetting("ai_auto_train", jObj.optBoolean("aiAutoTrain") ? "1" : "0");
            this.db.log("INFO", "AI", "AUTO_TRAIN_SET", "AI auto-retrain (24h) = " + jObj.optBoolean("aiAutoTrain"));
        }
        if (jObj.has("feeEdgeOn")) {
            this.db.setSetting("fee_edge_on", jObj.optBoolean("feeEdgeOn") ? "1" : "0");
            this.db.log("INFO", "GUARD", "FEE_EDGE_SET", "Fee-edge guard = " + jObj.optBoolean("feeEdgeOn"));
        }
        if (jObj.has("minFeeEdgePct")) {
            double optDouble = jObj.optDouble("minFeeEdgePct", 0.14d);
            if (optDouble < 0.0d || optDouble > 1.0d) {
                return Res.error(400, "Fee edge 0-1% ke beech set karein (default 0.14% = round-trip fees)");
            }
            this.db.setSetting("min_fee_edge_pct", String.valueOf(optDouble));
            this.db.log("INFO", "GUARD", "FEE_EDGE_MIN_SET", "Min TP move = " + optDouble + "% (fees+slip round-trip)");
        }
        if (jObj.has("aiForceKey")) {
            String optString2 = jObj.optString("aiForceKey", "");
            if (optString2.matches("[A-Za-z0-9_]+")) {
                this.db.setSetting("ai_off_" + optString2, jObj.optBoolean("aiForceVal", true) ? "1" : "0");
                EngineCore engineCore = this.engine;
                if (engineCore != null) {
                    engineCore.invalidateAiWeights();
                }
                this.db.log("INFO", "AI", "STRATEGY_FORCE", optString2 + " owner force " + (jObj.optBoolean("aiForceVal", true) ? "ON" : "AI-weight"));
            }
        }
        if (jObj.has("riskPct")) {
            double optDouble2 = jObj.optDouble("riskPct", 2.0d);
            if (optDouble2 < 0.1d || optDouble2 > 20.0d) {
                return Res.error(400, "Risk 0.1% se 20% ke beech set karein (3C default 2%)");
            }
            this.db.setSetting("risk_pct", String.valueOf(optDouble2));
            this.db.log("INFO", "RISK", "RISK_SET", "3C per-trade risk = " + optDouble2 + "% of equity (owner setting)");
        }
        if (jObj.has("levCap")) {
            double optDouble3 = jObj.optDouble("levCap", 0.0d);
            if (optDouble3 < 0.0d || optDouble3 > 10.0d) {
                return Res.error(400, "Leverage cap 0 = UNCAPPED (TRUE risk% sizing — v1.2 default) ya 0.1x–10x — PAPER ONLY");
            }
            this.db.setSetting("lev_cap", String.valueOf(optDouble3));
            this.db.log("WARN", "TURBO", "LEV_SET", optDouble3 <= 0.0d ? "notional cap OFF (UNCAPPED) — har trade ab poora risk% leta hai (default 1%); pehle 0.95 clamp risk ko ~0.05% tak tod raha tha" : ("paper notional cap = " + optDouble3 + "x equity" + (optDouble3 > 1.0d ? " — TURBO mode (PAPER ONLY, koi real order nahi)" : " (spot sizing)")));
        }
        if (jObj.has("feeBps")) {
            double optDouble4 = jObj.optDouble("feeBps", 5.0d);
            if (optDouble4 < 0.0d || optDouble4 > 100.0d) {
                return Res.error(400, "Fee 0–100 bps ke beech set karein (5 = Binance VIP 0.05%, 0 = zero-fee sim)");
            }
            this.db.setSetting("fee_bps", String.valueOf(optDouble4));
            this.db.log("INFO", "TURBO", "FEE_SET", "paper taker fee = " + optDouble4 + " bps/side" + (optDouble4 == 0.0d ? " (zero-fee sim)" : ""));
        }
        if (jObj.has("x7On")) {
            this.db.setSetting("x7_on", jObj.optBoolean("x7On") ? "1" : "0");
            this.db.log("INFO", "X7", "X7_SET", "X7 REGIME FADE strategy = ".concat(jObj.optBoolean("x7On") ? "ON" : "OFF"));
        }
        if (jObj.has("cooldownMin")) {
            int optDouble5 = (int) jObj.optDouble("cooldownMin", 15.0d);
            if (optDouble5 < 0 || optDouble5 > 240) {
                return Res.error(400, "Cooldown 0–240 minutes ke beech set karein (0 = off)");
            }
            this.db.setSetting("cooldown_min", String.valueOf(optDouble5));
            this.db.log("INFO", "GUARD", "COOLDOWN_SET", "SL-loss cooldown = " + optDouble5 + " min (owner setting)");
        }
        if (jObj.has("consecLoss")) {
            int optDouble6 = (int) jObj.optDouble("consecLoss", 3.0d);
            if (optDouble6 < 0 || optDouble6 > 10) {
                return Res.error(400, "Consecutive losses 0–10 ke beech set karein (0 = off)");
            }
            this.db.setSetting("consec_loss", String.valueOf(optDouble6));
            this.db.log("INFO", "GUARD", "CONSEC_LOSS_SET", "StoplossGuard = " + optDouble6 + " lagatar SL losses → 1 ghanta pause");
        }
        if (jObj.has("dailyKillPct")) {
            double optDouble7 = jObj.optDouble("dailyKillPct", 0.0d);
            if (optDouble7 < 0.0d || optDouble7 > 90.0d) {
                return Res.error(400, "Daily kill 0–90% ke beech set karein (0 = off)");
            }
            this.db.setSetting("daily_kill_pct", String.valueOf(optDouble7));
            this.db.log("INFO", "GUARD", "DAILY_KILL_SET", "Daily kill switch = " + optDouble7 + "%" + (optDouble7 <= 0.0d ? " (OFF — unlimited)" : ""));
        }
        if (jObj.has("mt5Bridge")) {
            String trim = jObj.optString("mt5Bridge", "").trim();
            if (trim.length() > 300) {
                return Res.error(400, "Bridge URL bohat lamba hai (max 300 chars)");
            }
            if (!trim.isEmpty() && !trim.startsWith("http://") && !trim.startsWith("https://")) {
                return Res.error(400, "Bridge URL http:// ya https:// se shuru hona chahiye");
            }
            this.db.setSetting("mt5_bridge", trim);
            Db db = this.db;
            if (trim.isEmpty()) {
                str2 = "MT5 bridge cleared — built-in halal commodities feed use hoga";
            } else {
                str2 = "MT5 bridge set: " + trim + " — candles ab MetaTrader5 terminal se aayengi";
            }
            db.log("INFO", "DATA", "MT5_BRIDGE_SET", str2);
        }
        if (jObj.has("slipBps")) {
            double optDouble8 = jObj.optDouble("slipBps", 2.0d);
            if (optDouble8 < 0.0d || optDouble8 > 50.0d) {
                return Res.error(400, "Slippage 0–50 bps ke beech set karein (0 = exact fills)");
            }
            this.db.setSetting("slip_bps", String.valueOf(optDouble8));
            this.db.log("INFO", "FILL", "SLIP_SET", "slippage/spread model = " + optDouble8 + " bps per side");
        }
        if (jObj.has("heatMaxPct")) {
            double optDouble9 = jObj.optDouble("heatMaxPct", 0.0d);
            if (optDouble9 < 0.0d || optDouble9 > 100.0d) {
                return Res.error(400, "Heat cap 0–100% ke beech set karein (0 = OFF/unlimited)");
            }
            this.db.setSetting("heat_max_pct", String.valueOf(optDouble9));
            this.db.log("INFO", "GUARD", "HEAT_SET", "portfolio heat cap = " + optDouble9 + "%" + (optDouble9 <= 0.0d ? " (OFF — unlimited, owner default)" : ""));
        }
        if (jObj.has("bucketMaxPct")) {
            double optDouble10 = jObj.optDouble("bucketMaxPct", 0.0d);
            if (optDouble10 < 0.0d || optDouble10 > 100.0d) {
                return Res.error(400, "Bucket cap 0–100% ke beech set karein (0 = OFF)");
            }
            this.db.setSetting("bucket_max_pct", String.valueOf(optDouble10));
            this.db.log("INFO", "GUARD", "BUCKET_SET", "bucket (METAL/ENERGY/AGRI) cap = " + optDouble10 + "%" + (optDouble10 <= 0.0d ? " (OFF)" : ""));
        }
        if (jObj.has("councilMin")) {
            int optDouble11 = (int) jObj.optDouble("councilMin", 0.0d);
            if (optDouble11 < 0 || optDouble11 > 95) {
                return Res.error(400, "Council min 0–95 ke beech set karein (0 = tag-only, koi block nahi)");
            }
            this.db.setSetting("council_min", String.valueOf(optDouble11));
            this.db.log("INFO", "COUNCIL", "COUNCIL_SET", "Signal Council min confidence = " + optDouble11 + "%" + (optDouble11 <= 0 ? " (tag-only mode)" : ""));
        }
        if (jObj.has("eventGate")) {
            this.db.setSetting("event_gate", jObj.optBoolean("eventGate") ? "1" : "0");
            this.db.log("INFO", "GUARD", "EVENT_GATE_SET", "HIGH-impact news entry pause = " + jObj.optBoolean("eventGate"));
        }
        if (jObj.has("autoPause")) {
            this.db.setSetting("auto_pause", jObj.optBoolean("autoPause") ? "1" : "0");
            this.db.log("INFO", "GUARD", "AUTO_PAUSE_SET", "degraded strategy auto-pause = " + jObj.optBoolean("autoPause"));
        }
        if (jObj.has("sessionFilter")) {
            this.db.setSetting("session_filter", jObj.optBoolean("sessionFilter") ? "1" : "0");
            this.db.log("INFO", "GUARD", "SESSION_SET", "CME halt (17-18 ET) entry filter = " + jObj.optBoolean("sessionFilter"));
        }
        if (jObj.has("bridgeLive")) {
            this.db.setSetting("bridge_live", jObj.optBoolean("bridgeLive") ? "1" : "0");
            this.db.log("WARN", "BRIDGE", "BRIDGE_LIVE_SET", "MT5 bridge LIVE MIRROR = " + jObj.optBoolean("bridgeLive") + (jObj.optBoolean("bridgeLive") ? " — paper trades ke saath bridge par real orders jayenge (owner responsibility)" : " (safe: sirf paper)"));
        }
        if (jObj.has("bridgeLots")) {
            double optDouble12 = jObj.optDouble("bridgeLots", 0.01d);
            if (optDouble12 < 0.01d || optDouble12 > 100.0d) {
                return Res.error(400, "Bridge lots 0.01–100 ke beech set karein");
            }
            this.db.setSetting("bridge_lots", String.valueOf(optDouble12));
            this.db.log("INFO", "BRIDGE", "BRIDGE_LOTS_SET", "bridge mirror lot size = " + optDouble12);
        }
        if (jObj.has("feedIntervalSec")) {
            int optDouble13 = (int) jObj.optDouble("feedIntervalSec", 60.0d);
            if (optDouble13 < 20 || optDouble13 > 600) {
                return Res.error(400, "Feed interval 20–600 seconds ke beech set karein");
            }
            this.db.setSetting("feed_interval_sec", String.valueOf(optDouble13));
            this.db.log("INFO", "DATA", "FEED_INTERVAL_SET", "per-symbol feed refresh = " + optDouble13 + "s");
        }
        if (jObj.has("labSymbol")) {
            String trim2 = jObj.optString("labSymbol", "BTCUSDT").toUpperCase(Locale.US).trim();
            if (!trim2.matches("[A-Z0-9]{4,20}")) {
                return Res.error(400, "Lab symbol galat (e.g. BTCUSDT)");
            }
            this.db.setSetting("lab_symbol", trim2);
            this.db.log("INFO", "LAB", "LAB_SYMBOL_SET", "Lab backtest symbol = " + trim2);
        }
        return settings();
    }

    private boolean isAdmin(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT role FROM users WHERE id=? AND active=1", new String[]{String.valueOf(j)});
        boolean z = rawQuery.moveToFirst() && "ADMIN".equals(rawQuery.getString(0));
        rawQuery.close();
        return z;
    }

    private Res adminGuard(long j) {
        if (isAdmin(j)) {
            return null;
        }
        return Res.error(403, "Admin access required — owner account only");
    }

    private Res adminUsers(long j) throws Exception {
        int i = 0;
        int i2 = 0;
        int i3 = 0;
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, name, email, role, active, created_at, (SELECT COUNT(*) FROM sessions s WHERE s.user_id=u.id), IFNULL(approved,1), IFNULL(trade_ok, CASE WHEN role='ADMIN' THEN 1 ELSE 0 END) FROM users u ORDER BY id", null);
        while (true) {
            i = 0;
            if (!rawQuery.moveToNext()) {
                break;
            }
            jSONArray.put(new JSONObject().put("id", rawQuery.getLong(0)).put("name", rawQuery.getString(1)).put("email", rawQuery.getString(2)).put("role", rawQuery.getString(3)).put("active", rawQuery.getInt(4)).put("createdAt", rawQuery.getLong(5)).put("sessions", rawQuery.getInt(6)).put("approved", rawQuery.getInt(7)).put("tradeOk", rawQuery.getInt(8)));
        }
        rawQuery.close();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*), IFNULL(SUM(active),0), SUM(CASE WHEN IFNULL(approved,1)=0 THEN 1 ELSE 0 END) FROM users", null);
        if (rawQuery2.moveToFirst()) {
            i = rawQuery2.getInt(0);
            i2 = rawQuery2.getInt(1);
            i3 = rawQuery2.getInt(2);
        } else {
            i2 = 0;
            i3 = 0;
        }
        rawQuery2.close();
        return Res.json(200, new JSONObject().put("users", jSONArray).put("total", i).put("activeUsers", i2).put("pendingUsers", i3));
    }

    private Res adminUserAction(long j, String str) throws Exception {
        String str2 = null;
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONObject jObj = HttpServer.jObj(str);
        long optLong = jObj.optLong("id", -1L);
        String jStr = HttpServer.jStr(jObj, "action");
        if (optLong <= 0) {
            return Res.error(400, "User id required");
        }
        if ("approve".equals(jStr)) {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name, email FROM users WHERE id=?", new String[]{String.valueOf(optLong)});
            if (!rawQuery.moveToFirst()) {
                rawQuery.close();
                return Res.error(404, "User not found");
            }
            String string = rawQuery.getString(0);
            String string2 = rawQuery.getString(1);
            rawQuery.close();
            this.db.getWritableDatabase().execSQL("UPDATE users SET approved=1 WHERE id=?", new Object[]{Long.valueOf(optLong)});
            this.db.log("INFO", "ADMIN", "USER_APPROVED", string + " (" + string2 + ") approved by owner — ab sign in kar sakta hai");
            return Res.json(200, new JSONObject().put("ok", true).put("message", string + " APPROVED — ab wo sign in kar sakta hai"));
        }
        if ("trade".equals(jStr)) {
            int optInt = jObj.optInt("value", -1);
            if (optInt != 0 && optInt != 1) {
                return Res.error(400, "value 0 ya 1 required");
            }
            if (optLong == j && optInt == 0) {
                return Res.error(400, "Apna khud ka trading band nahi kar sakte (aap owner hain)");
            }
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT name FROM users WHERE id=?", new String[]{String.valueOf(optLong)});
            if (!rawQuery2.moveToFirst()) {
                rawQuery2.close();
                return Res.error(404, "User not found");
            }
            String string3 = rawQuery2.getString(0);
            rawQuery2.close();
            this.db.getWritableDatabase().execSQL("UPDATE users SET trade_ok=? WHERE id=?", new Object[]{Integer.valueOf(optInt), Long.valueOf(optLong)});
            this.db.log("INFO", "ADMIN", optInt == 1 ? "TRADING_ENABLED" : "TRADING_DISABLED", string3 + " trading " + (optInt == 1 ? "ENABLED" : "DISABLED") + " by owner");
            JSONObject put = new JSONObject().put("ok", true);
            StringBuilder append = new StringBuilder().append(string3).append(" — trading ");
            if (optInt == 1) {
                str2 = "ENABLED — ab engine is user ke liye trades kholega";
            } else {
                str2 = "DISABLED — is user ke liye naye trades nahi khulenge";
            }
            return Res.json(200, put.put("message", append.append(str2).toString()));
        }
        if ("activate".equals(jStr) || "deactivate".equals(jStr)) {
            if (optLong == j) {
                return Res.error(400, "You cannot deactivate your own owner account");
            }
            boolean equals = "activate".equals(jStr);
            Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT id FROM users WHERE id=?", new String[]{String.valueOf(optLong)});
            boolean moveToFirst = rawQuery3.moveToFirst();
            rawQuery3.close();
            if (!moveToFirst) {
                return Res.error(404, "User not found");
            }
            this.db.getWritableDatabase().execSQL("UPDATE users SET active=? WHERE id=?", new Object[]{Integer.valueOf(equals ? 1 : 0), Long.valueOf(optLong)});
            if (!equals) {
                this.db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{Long.valueOf(optLong)});
            }
            this.db.log("INFO", "ADMIN", equals ? "USER_ENABLED" : "USER_DISABLED", "user #" + optLong + " " + jStr + "d by owner");
            return Res.json(200, new JSONObject().put("ok", true).put("message", equals ? "User enabled — they can sign in again" : "User disabled — all their sessions ended"));
        }
        if (!"delete".equals(jStr)) {
            return Res.error(400, "Unknown action");
        }
        if (optLong == j) {
            return Res.error(400, "You cannot delete your own owner account");
        }
        Cursor rawQuery4 = this.db.getReadableDatabase().rawQuery("SELECT role, name FROM users WHERE id=?", new String[]{String.valueOf(optLong)});
        if (!rawQuery4.moveToFirst()) {
            rawQuery4.close();
            return Res.error(404, "User not found");
        }
        String string4 = rawQuery4.getString(0);
        String string5 = rawQuery4.getString(1);
        rawQuery4.close();
        if ("ADMIN".equals(string4)) {
            Cursor rawQuery5 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND active=1", null);
            int i = rawQuery5.moveToFirst() ? rawQuery5.getInt(0) : 0;
            rawQuery5.close();
            if (i <= 1) {
                return Res.error(400, "Cannot delete the last admin account");
            }
        }
        this.db.getWritableDatabase().execSQL("DELETE FROM sessions WHERE user_id=?", new Object[]{Long.valueOf(optLong)});
        this.db.getWritableDatabase().execSQL("DELETE FROM accounts WHERE user_id=?", new Object[]{Long.valueOf(optLong)});
        this.db.getWritableDatabase().execSQL("DELETE FROM trades WHERE user_id=?", new Object[]{Long.valueOf(optLong)});
        this.db.getWritableDatabase().execSQL("DELETE FROM users WHERE id=?", new Object[]{Long.valueOf(optLong)});
        this.db.log("INFO", "ADMIN", "USER_DELETED", string5 + " (#" + optLong + ") deleted by owner — sessions, paper account, trades removed");
        return Res.json(200, new JSONObject().put("ok", true).put("message", string5 + " deleted permanently"));
    }

    private Res adminInvites(long j) throws Exception {
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT code, label, max_uses, uses, active FROM invites ORDER BY active DESC, code", null);
        while (rawQuery.moveToNext()) {
            jSONArray.put(new JSONObject().put("code", rawQuery.getString(0)).put("label", rawQuery.getString(1)).put("maxUses", rawQuery.getInt(2)).put("uses", rawQuery.getInt(3)).put("active", rawQuery.getInt(4)));
        }
        rawQuery.close();
        return Res.json(200, new JSONObject().put("invites", jSONArray).put("total", jSONArray.length()));
    }

    private Res adminInviteAction(long j, String str) throws Exception {
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONObject jObj = HttpServer.jObj(str);
        String jStr = HttpServer.jStr(jObj, "action");
        if ("create".equals(jStr)) {
            String jStr2 = HttpServer.jStr(jObj, "label");
            char c = 0;
            int optInt = jObj.optInt("maxUses", 0);
            if (optInt < 0) {
                optInt = 0;
            }
            if (jStr2.isEmpty()) {
                jStr2 = "Owner invite — " + new SimpleDateFormat("MMM d", Locale.US).format(new Date());
            }
            String str2 = null;
            int i = 0;
            while (i < 5 && str2 == null) {
                String newInviteCode = Auth.newInviteCode();
                SQLiteDatabase readableDatabase = this.db.getReadableDatabase();
                String[] strArr = new String[1];
                strArr[c] = newInviteCode;
                Cursor rawQuery = readableDatabase.rawQuery("SELECT code FROM invites WHERE code=?", strArr);
                boolean moveToFirst = rawQuery.moveToFirst();
                rawQuery.close();
                if (!moveToFirst) {
                    str2 = newInviteCode;
                }
                i++;
                c = 0;
            }
            if (str2 == null) {
                return Res.error(500, "Could not generate a unique code — try again");
            }
            this.db.getWritableDatabase().execSQL("INSERT OR IGNORE INTO invites(code, label, max_uses, uses, active) VALUES(?,?,?,0,1)", new Object[]{str2, jStr2, Integer.valueOf(optInt)});
            this.db.log("INFO", "ADMIN", "INVITE_CREATED", str2 + " created by owner — " + jStr2 + (optInt > 0 ? " (max " + optInt + ")" : " (unlimited)"));
            return Res.json(200, new JSONObject().put("ok", true).put("code", str2).put("message", "Naya invite code ban gaya: " + str2));
        }
        String upperCase = HttpServer.jStr(jObj, "code").trim().toUpperCase();
        if (upperCase.isEmpty()) {
            return Res.error(400, "Invite code required");
        }
        if ("revoke".equals(jStr)) {
            this.db.getWritableDatabase().execSQL("UPDATE invites SET active=0 WHERE code=?", new Object[]{upperCase});
            this.db.log("INFO", "ADMIN", "INVITE_REVOKED", upperCase + " revoked by owner — registrations with it now fail");
            return Res.json(200, new JSONObject().put("ok", true).put("message", upperCase + " revoked — is code se ab koi register nahi kar sakta"));
        }
        if ("activate".equals(jStr)) {
            this.db.getWritableDatabase().execSQL("UPDATE invites SET active=1 WHERE code=?", new Object[]{upperCase});
            this.db.log("INFO", "ADMIN", "INVITE_ENABLED", upperCase + " re-enabled by owner");
            return Res.json(200, new JSONObject().put("ok", true).put("message", upperCase + " enabled again"));
        }
        return Res.error(400, "Unknown action");
    }

    private Res adminAlerts(long j) throws Exception {
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONArray jSONArray = new JSONArray();
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, kind, title, body, meta, read, created_at FROM notifications ORDER BY id DESC LIMIT 100", null);
        while (true) {
            if (!rawQuery.moveToNext()) {
                break;
            }
            JSONObject jSONObject = new JSONObject();
            jSONObject.put("id", rawQuery.getLong(0)).put("kind", rawQuery.getString(1)).put("title", rawQuery.getString(2)).put("body", rawQuery.getString(3)).put("read", rawQuery.getInt(5)).put("createdAt", rawQuery.getLong(6));
            try {
                jSONObject.put("meta", new JSONObject(rawQuery.getString(4)));
            } catch (Throwable unused) {
                jSONObject.put("meta", new JSONObject());
            }
            jSONArray.put(jSONObject);
        }
        rawQuery.close();
        Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM notifications WHERE read=0", null);
        int i = rawQuery2.moveToFirst() ? rawQuery2.getInt(0) : 0;
        rawQuery2.close();
        return Res.json(200, new JSONObject().put("alerts", jSONArray).put("unreadCount", i));
    }

    private Res adminAlertAction(long j, String str) throws Exception {
        Res adminGuard = adminGuard(j);
        if (adminGuard != null) {
            return adminGuard;
        }
        JSONObject jObj = HttpServer.jObj(str);
        String jStr = HttpServer.jStr(jObj, "action");
        if ("read-all".equals(jStr)) {
            this.db.getWritableDatabase().execSQL("UPDATE notifications SET read=1 WHERE read=0");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Saare alerts parh liye gaye"));
        }
        if ("read".equals(jStr)) {
            long optLong = jObj.optLong("id", -1L);
            if (optLong > 0) {
                this.db.getWritableDatabase().execSQL("UPDATE notifications SET read=1 WHERE id=?", new Object[]{Long.valueOf(optLong)});
            }
            return Res.json(200, new JSONObject().put("ok", true));
        }
        if ("clear".equals(jStr)) {
            this.db.getWritableDatabase().execSQL("DELETE FROM notifications WHERE read=1");
            return Res.json(200, new JSONObject().put("ok", true).put("message", "Read alerts cleared"));
        }
        return Res.error(400, "Unknown action");
    }

    static double round2(double d) {
        return Math.round(d * 100.0d) / 100.0d;
    }
}
