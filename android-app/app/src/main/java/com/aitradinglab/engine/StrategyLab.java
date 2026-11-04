package com.aitradinglab.engine;

import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import com.aitradinglab.engine.EngineCore;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONArray;
import org.json.JSONObject;

/* loaded from: classes.dex */
public class StrategyLab {
    public static final String DEFAULT_AI_BASE = "https://preview-chat-6708bda6-7b6e-4a6f-a30c-eb65caff80bf.space-z.ai";
    private static final String DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";
    private final Context ctx;
    private final Db db;
    private final EngineCore engine;
    private volatile String lastAiError = null;
    private List<Double> simR = new ArrayList();
    private List<Double> simPnl = new ArrayList();

    public StrategyLab(Context context, Db db, EngineCore engineCore) {
        this.ctx = context.getApplicationContext();
        this.db = db;
        this.engine = engineCore;
        seedShaakuniStrategies();
    }

    private void seedShaakuniStrategies() {
        try {
            if (!"1".equals(this.db.setting("shaakuni_active_v44", "0"))) {
                this.db.setSetting("shaakuni_active_v44", "1");
                this.db.getWritableDatabase().execSQL("UPDATE strategies SET status='ACTIVE', updated_at=? WHERE source='SHAAKUNI' AND status IN ('CANDIDATE','BACKTESTED') AND deleted_at=0", new Object[]{Long.valueOf(System.currentTimeMillis())});
                this.db.log("INFO", "LAB", "SHAAKUNI_ACTIVE", "Shaakuni Trap playbooks AUTO-ACTIVE (paper) — owner request: aur trades chahiye. Strategy Lab me toggle/reject kar sakte hain.");
            }
            if ("1".equals(this.db.setting("shaakuni_seeded_v41", "0"))) {
                return;
            }
            this.db.setSetting("shaakuni_seeded_v41", "1");
            String[][] strArr = {new String[]{"SSM Sniper — PDL Sweep + MSS Bull (Shaakuni)", "[{\"ind\":\"liq_sweep\",\"op\":\"pdl_swept\"},{\"ind\":\"mss\",\"op\":\"bull\"},{\"ind\":\"killzone\",\"op\":\"any\"}]", "BUY"}, new String[]{"SSM Sniper — PDH Sweep + MSS Bear (Shaakuni)", "[{\"ind\":\"liq_sweep\",\"op\":\"pdh_swept\"},{\"ind\":\"mss\",\"op\":\"bear\"},{\"ind\":\"killzone\",\"op\":\"any\"}]", "SELL"}, new String[]{"Killzone Sweep — London/NY (Shaakuni)", "[{\"ind\":\"killzone\",\"op\":\"any\"},{\"ind\":\"liq_sweep\",\"op\":\"any\"}]", "BOTH"}, new String[]{"OB Retest Continuation (Shaakuni)", "[{\"ind\":\"mss\",\"op\":\"bull\"},{\"ind\":\"ob_retest\",\"op\":\"any\"}]", "BOTH"}, new String[]{"Discount Buy + EMA200 Trend (Shaakuni PD filter)", "[{\"ind\":\"premium_discount\",\"op\":\"discount\"},{\"ind\":\"price_vs_ema\",\"p\":200,\"op\":\"above\"}]", "BUY"}};
            int i = 0;
            for (int i2 = 0; i2 < 5; i2++) {
                String[] strArr2 = strArr[i2];
                JSONObject insert = insert("SHAAKUNI", "{}", new JSONObject().put("name", strArr2[0]).put("side", strArr2[2]).put("logic", "ALL").put("conditions", new JSONArray(strArr2[1])).put("notes", "Shaakuni Trap playbook — liquidity sweep + MSS + POI (uske TradingView script aur masterclasses se)"));
                if (insert != null && insert.optBoolean("ok")) {
                    i++;
                }
            }
            this.db.log("INFO", "LAB", "SHAAKUNI_SEED", i + "/5 Shaakuni Trap playbooks Lab me seed (CANDIDATE) — owner Backtest/Approve kare");
        } catch (Throwable th) {
            try {
                this.db.log("WARN", "LAB", "SHAAKUNI_SEED_FAIL", String.valueOf(th));
            } catch (Throwable unused) {
            }
        }
    }

    private String aiBase() {
        String trim = this.db.setting("ai_base", DEFAULT_AI_BASE).trim();
        return trim.endsWith("/") ? trim.substring(0, trim.length() - 1) : trim;
    }

    private JSONObject aiPost(String str, JSONObject jSONObject, int i) {
        try {
            HttpURLConnection httpURLConnection = (HttpURLConnection) new URL(aiBase() + str).openConnection();
            httpURLConnection.setRequestMethod("POST");
            httpURLConnection.setConnectTimeout(i);
            httpURLConnection.setReadTimeout(i);
            httpURLConnection.setDoOutput(true);
            httpURLConnection.setRequestProperty("Content-Type", "application/json");
            httpURLConnection.setRequestProperty("User-Agent", "AI-Trading-Lab/1.2");
            OutputStream outputStream = httpURLConnection.getOutputStream();
            outputStream.write(jSONObject.toString().getBytes(StandardCharsets.UTF_8));
            outputStream.close();
            int responseCode = httpURLConnection.getResponseCode();
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(responseCode >= 400 ? httpURLConnection.getErrorStream() : httpURLConnection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            while (true) {
                String readLine = bufferedReader.readLine();
                if (readLine == null) {
                    break;
                }
                sb.append(readLine);
            }
            bufferedReader.close();
            if (responseCode >= 400) {
                String str2 = "{}";
                try {
                    str2 = new JSONObject(sb.toString()).optString("error", "AI error " + responseCode);
                } catch (Exception unused) {
                }
                this.lastAiError = str2;
                return null;
            }
            this.lastAiError = null;
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            this.lastAiError = "AI service unreachable: " + e.getClass().getSimpleName();
            return null;
        }
    }

    public JSONObject addManual(String str) throws Exception {
        JSONObject compileText = compileText(str);
        if (compileText == null) {
            return fail(this.lastAiError != null ? this.lastAiError : "AI compile fail — dobara try karein");
        }
        return insert(sourceFrom(compileText), compileText.optString("video", "{}"), compileText);
    }

    private JSONObject compileText(String str) throws Exception {
        JSONObject optJSONObject = null;
        JSONObject aiPost = aiPost("/api/ai/strategy", new JSONObject().put("text", str), 90000);
        if (aiPost != null && aiPost.optBoolean("ok") && (optJSONObject = aiPost.optJSONObject("spec")) != null) {
            try {
                optJSONObject.put("compiler", "ai-proxy");
            } catch (Throwable unused) {
            }
            return optJSONObject;
        }
        JSONObject offlineCompile = offlineCompile(str);
        if (offlineCompile != null) {
            try {
                offlineCompile.put("compiler", "offline-rules");
            } catch (Throwable unused2) {
            }
            this.lastAiError = null;
        }
        return offlineCompile;
    }

    /* JADX WARN: Removed duplicated region for block: B:118:0x028a  */
    /* JADX WARN: Removed duplicated region for block: B:121:0x0238 A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:127:0x01f1  */
    /* JADX WARN: Removed duplicated region for block: B:130:0x0200  */
    /* JADX WARN: Removed duplicated region for block: B:132:0x0203  */
    /* JADX WARN: Removed duplicated region for block: B:133:0x01f3  */
    /* JADX WARN: Removed duplicated region for block: B:136:0x0184  */
    /* JADX WARN: Removed duplicated region for block: B:138:0x0187 A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:145:0x00fe A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:151:0x00c0 A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:155:0x00c7 A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:159:0x0076 A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:28:0x006f A[ADDED_TO_REGION] */
    /* JADX WARN: Removed duplicated region for block: B:33:0x009c A[Catch: all -> 0x02e3, TRY_ENTER, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:41:0x00db A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:49:0x0115 A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:55:0x013e A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:62:0x0169 A[Catch: all -> 0x02e3, TRY_ENTER, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:69:0x019e A[Catch: all -> 0x02e3, TRY_ENTER, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:72:0x01b5 A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:76:0x01d8 A[Catch: all -> 0x02e3, TRY_ENTER, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:81:0x0217 A[Catch: all -> 0x02e3, TRY_ENTER, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:87:0x024f A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:95:0x0273 A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /* JADX WARN: Removed duplicated region for block: B:97:0x028e A[Catch: all -> 0x02e3, TryCatch #0 {all -> 0x02e3, blocks: (B:4:0x0015, B:7:0x0024, B:9:0x002c, B:11:0x0032, B:15:0x003e, B:18:0x0048, B:20:0x0050, B:22:0x0056, B:26:0x0062, B:30:0x007d, B:33:0x009c, B:35:0x00a4, B:39:0x00d5, B:41:0x00db, B:43:0x00e3, B:45:0x00eb, B:47:0x010d, B:49:0x0115, B:51:0x011d, B:53:0x0138, B:55:0x013e, B:57:0x0146, B:59:0x015f, B:62:0x0169, B:64:0x016f, B:66:0x0196, B:69:0x019e, B:70:0x01af, B:72:0x01b5, B:73:0x01c6, B:76:0x01d8, B:78:0x020d, B:81:0x0217, B:83:0x021f, B:85:0x0247, B:87:0x024f, B:91:0x0263, B:93:0x026b, B:95:0x0273, B:97:0x028e, B:101:0x02a6, B:105:0x02c0, B:109:0x02cf, B:113:0x02d6, B:119:0x0227, B:123:0x023f, B:125:0x01de, B:128:0x01f4, B:131:0x0205, B:134:0x0175, B:137:0x018e, B:138:0x0187, B:141:0x014e, B:142:0x0125, B:143:0x00f3, B:147:0x0105, B:149:0x00b1, B:153:0x00cd, B:165:0x0011), top: B:164:0x0011 }] */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
        private static JSONObject offlineCompile(String str) {
        try {
            String text = str == null ? "" : str.toLowerCase();
            JSONObject out = new JSONObject();
            boolean sellish = text.contains("sell") || text.contains("short") || text.contains("bear") || text.contains("down");
            boolean buyish = text.contains("buy") || text.contains("long") || text.contains("bull") || text.contains("up");
            out.put("name", nameFrom(str));
            String side;
            if (sellish && !buyish) {
                side = "SELL";
            } else if (buyish && !sellish) {
                side = "BUY";
            } else {
                side = "BOTH";
            }
            out.put("side", side);
            out.put("logic", "ALL");
            JSONArray conds = new JSONArray();
            boolean any = false;
            if (text.contains("sweep") || text.contains("liquidity") || text.contains("stop hunt")) {
                String op = (sellish && !buyish) ? "pdh_swept" : ((buyish && !sellish) ? "pdl_swept" : "any");
                conds.put(new JSONObject().put("ind", "liq_sweep").put("op", op));
                any = true;
            }
            if (text.contains("mss") || text.contains("structure shift") || text.contains("structure break") || text.contains("market structure")) {
                conds.put(new JSONObject().put("ind", "mss").put("op", (sellish && !buyish) ? "bear" : "bull"));
                any = true;
            }
            if (text.contains("order block") || text.contains(" ob ") || text.contains("poi")) {
                conds.put(new JSONObject().put("ind", "ob_retest").put("op", "any"));
                any = true;
            }
            if (text.contains("fvg") || text.contains("fair value") || text.contains("imbalance")) {
                conds.put(new JSONObject().put("ind", "fvg").put("op", "any"));
                any = true;
            }
            if (text.contains("killzone") || text.contains("london") || text.contains("new york")) {
                String op;
                if (text.contains("new york")) {
                    op = "newyork";
                } else if (text.contains("london")) {
                    op = "london";
                } else {
                    op = "any";
                }
                conds.put(new JSONObject().put("ind", "killzone").put("op", op));
                any = true;
            }
            if (text.contains("discount")) {
                conds.put(new JSONObject().put("ind", "premium_discount").put("op", "discount"));
                any = true;
            }
            if (text.contains("premium")) {
                conds.put(new JSONObject().put("ind", "premium_discount").put("op", "premium"));
                any = true;
            }
            if (text.contains("oversold") || text.contains("rsi")) {
                boolean ob = text.contains("overbought");
                conds.put(new JSONObject().put("ind", "rsi").put("p", 14).put("op", ob ? ">" : "<").put("v", ob ? 70 : 30));
                any = true;
            }
            if (text.contains("ema 200") || text.contains("ema200") || text.contains("200 ema")) {
                conds.put(new JSONObject().put("ind", "price_vs_ema").put("p", 200).put("op", (sellish && !buyish) ? "below" : "above"));
                any = true;
            }
            if (text.contains("macd")) {
                conds.put(new JSONObject().put("ind", "macd").put("op", (sellish && !buyish) ? "bear" : "bull"));
                any = true;
            }
            if (text.contains("volume")) {
                conds.put(new JSONObject().put("ind", "volume").put("op", "spike"));
                any = true;
            }
            if (!any) {
                conds.put(new JSONObject().put("ind", "price_vs_ema").put("p", 50).put("op", (sellish && !buyish) ? "below" : "above"));
                conds.put(new JSONObject().put("ind", "rsi").put("p", 14).put("op", (sellish && !buyish) ? ">" : "<").put("v", (sellish && !buyish) ? 70 : 45));
            }
            out.put("conditions", conds);
            out.put("notes", "Offline rule-compiler (AI proxy available nahi tha) — text keywords se bana");
            return out;
        } catch (Throwable thz) {
            return null;
        }
    }

    private static String nameFrom(String str) {
        if (str == null) {
            return "Custom";
        }
        String trim = str.trim();
        if (trim.isEmpty()) {
            return "Custom";
        }
        String[] split = trim.split("\\s+");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < split.length && i < 6; i++) {
            if (sb.length() > 0) {
                sb.append(' ');
            }
            sb.append(split[i]);
        }
        String sb2 = sb.toString();
        return sb2.length() > 40 ? sb2.substring(0, 40) : sb2;
    }

    public JSONObject addYouTube(String str) throws Exception {
        String str2 = null;
        String str3 = null;
        String optString = null;
        String str4 = null;
        String extractVideoId = extractVideoId(str);
        if (extractVideoId == null) {
            return fail("Ye YouTube video link nahi lag raha");
        }
        String httpGetStr = httpGetStr("https://www.youtube.com/watch?v=" + extractVideoId + "&hl=en", DESKTOP_UA, 20000);
        str2 = "";
        if (httpGetStr == null) {
            str3 = "";
        } else {
            Matcher matcher = Pattern.compile("<title>(.*?)</title>").matcher(httpGetStr);
            if (!matcher.find()) {
                str4 = "";
            } else {
                str4 = matcher.group(1).replaceAll(" - YouTube$", "").replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", "\"");
            }
            Matcher matcher2 = Pattern.compile("\"ownerChannelName\":\"(.*?)\"").matcher(httpGetStr);
            str3 = matcher2.find() ? matcher2.group(1).replace("\\u0026", "&") : "";
            str2 = str4;
        }
        String fetchTranscript = fetchTranscript(extractVideoId);
        if (fetchTranscript == null) {
            return fail("Is video ke captions nahi mile — captions wali video try karein (auto-captions bhi chalti hain)");
        }
        JSONObject aiPost = aiPost("/api/ai/transcript", new JSONObject().put("title", str2).put("channel", str3).put("transcript", fetchTranscript), 120000);
        if (aiPost == null || !aiPost.optBoolean("ok")) {
            if (aiPost == null) {
                optString = this.lastAiError != null ? this.lastAiError : "AI service unreachable";
            } else {
                optString = aiPost.optString("error", "Video se strategy nahi bani");
            }
            return fail(optString);
        }
        JSONObject optJSONObject = aiPost.optJSONObject("spec");
        if (optJSONObject == null) {
            return fail("Video se strategy spec nahi bani");
        }
        JSONObject put = new JSONObject().put("id", extractVideoId).put("title", str2).put("channel", str3).put("url", "https://www.youtube.com/watch?v=" + extractVideoId);
        optJSONObject.put("video", put.toString());
        optJSONObject.put("source", "YOUTUBE");
        return insert("YOUTUBE", put.toString(), optJSONObject);
    }

    private static String extractVideoId(String str) {
        Matcher matcher = Pattern.compile("(?:v=|youtu\\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{11})").matcher(str);
        if (matcher.find()) {
            return matcher.group(1);
        }
        return null;
    }

    private static String httpGetStr(String str, String str2, int i) {
        try {
            HttpURLConnection httpURLConnection = (HttpURLConnection) new URL(str).openConnection();
            httpURLConnection.setConnectTimeout(i);
            httpURLConnection.setReadTimeout(i);
            httpURLConnection.setRequestProperty("User-Agent", str2);
            httpURLConnection.setRequestProperty("Accept-Language", "en-US,en;q=0.9");
            if (httpURLConnection.getResponseCode() != 200) {
                return null;
            }
            BufferedReader bufferedReader = new BufferedReader(new InputStreamReader(httpURLConnection.getInputStream(), StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            while (true) {
                String readLine = bufferedReader.readLine();
                if (readLine == null) {
                    bufferedReader.close();
                    return sb.toString();
                }
                sb.append(readLine);
            }
        } catch (Exception unused) {
            return null;
        }
    }

    private String fetchTranscript(String str) {
        String httpGetStr = null;
        try {
            String httpGetStr2 = httpGetStr("https://www.youtube.com/watch?v=" + str + "&hl=en", DESKTOP_UA, 20000);
            if (httpGetStr2 == null) {
                return null;
            }
            Matcher matcher = Pattern.compile("\"captionTracks\":(\\[.*?\\])(,\"audioTracks\"|,\"translationLanguages\"|\\})").matcher(httpGetStr2);
            if (!matcher.find()) {
                return null;
            }
            JSONArray jSONArray = new JSONArray(matcher.group(1).replace("\\u0026", "&").replace("\\\\/", "/"));
            String str2 = null;
            for (int i = 0; i < 2 && str2 == null; i++) {
                int i2 = 0;
                while (true) {
                    if (i2 < jSONArray.length()) {
                        JSONObject jSONObject = jSONArray.getJSONObject(i2);
                        String optString = jSONObject.optString("languageCode", "");
                        boolean equals = "asr".equals(jSONObject.optString("kind", ""));
                        if (i == 0 && optString.startsWith("en") && !equals) {
                            str2 = jSONObject.optString("baseUrl");
                            break;
                        }
                        if (i == 1 && optString.startsWith("en")) {
                            str2 = jSONObject.optString("baseUrl");
                            break;
                        }
                        i2++;
                    }
                }
            }
            if (str2 == null && jSONArray.length() > 0) {
                str2 = jSONArray.getJSONObject(0).optString("baseUrl");
            }
            if (str2 == null || str2.isEmpty() || (httpGetStr = httpGetStr(str2 + "&fmt=json3", DESKTOP_UA, 20000)) == null) {
                return null;
            }
            StringBuilder sb = new StringBuilder();
            JSONArray optJSONArray = new JSONObject(httpGetStr).optJSONArray("events");
            if (optJSONArray != null) {
                for (int i3 = 0; i3 < optJSONArray.length(); i3++) {
                    JSONArray optJSONArray2 = optJSONArray.getJSONObject(i3).optJSONArray("segs");
                    if (optJSONArray2 != null) {
                        for (int i4 = 0; i4 < optJSONArray2.length(); i4++) {
                            sb.append(optJSONArray2.getJSONObject(i4).optString("utf8", ""));
                        }
                    }
                }
            }
            String trim = sb.toString().replaceAll("\\s+", " ").trim();
            if (trim.length() < 200) {
                return null;
            }
            return trim.length() > 12000 ? trim.substring(0, 12000) : trim;
        } catch (Exception unused) {
        }
        return null;
    }

    public JSONObject subscribeChannel(String str) throws Exception {
        String optString = null;
        JSONObject aiPost = aiPost("/api/ai/ytlist", new JSONObject().put("url", str), 60000);
        if (aiPost == null || !aiPost.optBoolean("ok")) {
            if (aiPost == null) {
                optString = this.lastAiError != null ? this.lastAiError : "AI service unreachable";
            } else {
                optString = aiPost.optString("error", "Channel resolve nahi hui");
            }
            return fail(optString);
        }
        JSONObject optJSONObject = aiPost.optJSONObject("channel");
        if (optJSONObject == null) {
            return fail("Channel ID nahi mili");
        }
        this.db.setSetting("yt_channel_id", optJSONObject.optString("id"));
        this.db.setSetting("yt_channel_name", optJSONObject.optString("name"));
        JSONArray optJSONArray = aiPost.optJSONArray("videos");
        JSONArray jSONArray = new JSONArray();
        if (optJSONArray != null) {
            for (int i = 0; i < optJSONArray.length(); i++) {
                jSONArray.put(optJSONArray.optJSONObject(i).optString("id"));
            }
        }
        this.db.setSetting("yt_seen", jSONArray.toString());
        this.db.log("INFO", "LAB", "YT_SUBSCRIBE", "channel '" + optJSONObject.optString("name") + "' — engine ab har naya video + live stream 15 min mein check karke AI se strategy banayegi");
        return aiPost;
    }

    public void stopChannel() {
        this.db.setSetting("yt_channel_id", "");
        this.db.log("INFO", "LAB", "YT_STOP", "channel watcher stopped");
    }

    public void watchYouTube() throws Exception {
        JSONObject aiPost = null;
        JSONArray optJSONArray = null;
        JSONArray jSONArray = null;
        String str = this.db.setting("yt_channel_id", "");
        if (str == null || str.isEmpty() || (aiPost = aiPost("/api/ai/ytlist", new JSONObject().put("url", "https://www.youtube.com/channel/" + str), 60000)) == null || (optJSONArray = aiPost.optJSONArray("videos")) == null) {
            return;
        }
        try {
            jSONArray = new JSONArray(this.db.setting("yt_seen", "[]"));
        } catch (Exception unused) {
            jSONArray = new JSONArray();
        }
        ArrayList arrayList = new ArrayList();
        for (int i = 0; i < jSONArray.length(); i++) {
            arrayList.add(jSONArray.optString(i));
        }
        int i2 = 0;
        for (int i3 = 0; i3 < optJSONArray.length() && i2 < 3; i3++) {
            JSONObject optJSONObject = optJSONArray.optJSONObject(i3);
            String optString = optJSONObject.optString("id");
            if (!optString.isEmpty() && !arrayList.contains(optString)) {
                boolean optBoolean = optJSONObject.optBoolean("live");
                this.db.log("INFO", "LAB", "YT_PROCESS", (optBoolean ? "LIVE STREAM" : "video") + " '" + optJSONObject.optString("title") + "' — AI se strategy extract ho rahi hai");
                JSONObject addYouTube = addYouTube("https://www.youtube.com/watch?v=" + optString);
                arrayList.add(optString);
                jSONArray.put(optString);
                i2++;
                if (addYouTube != null && addYouTube.optBoolean("ok")) {
                    Notifier.post(this.ctx, "Strategy Lab — YouTube", (optBoolean ? "Live stream" : "Naya video") + " se strategy bani: " + addYouTube.optJSONObject("strategy").optString("name") + " (Lab tab mein backtest karein)");
                }
            }
        }
        if (i2 > 0) {
            while (jSONArray.length() > 200) {
                jSONArray.remove(0);
            }
            this.db.setSetting("yt_seen", jSONArray.toString());
        }
    }

    private JSONObject insert(String str, String str2, JSONObject jSONObject) {
        long currentTimeMillis = System.currentTimeMillis();
        this.db.getWritableDatabase().execSQL("INSERT INTO strategies(name, source, video, spec, status, stats, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)", new Object[]{jSONObject.optString("name", "Custom"), str, str2 == null ? "{}" : str2, jSONObject.toString(), "CANDIDATE", "{}", Long.valueOf(currentTimeMillis), Long.valueOf(currentTimeMillis)});
        this.db.log("INFO", "LAB", "STRATEGY_ADDED", str + " '" + jSONObject.optString("name") + "' — CANDIDATE (backtest karein)");
        JSONObject jSONObject2 = new JSONObject();
        try {
            jSONObject2.put("ok", true);
            jSONObject2.put("strategy", new JSONObject().put("name", jSONObject.optString("name")).put("spec", jSONObject).put("status", "CANDIDATE").put("source", str));
            if (str.equals("YOUTUBE") && !jSONObject.has("video") && this.lastAiError != null) {
                jSONObject2.put("warn", this.lastAiError);
            }
        } catch (Exception unused) {
        }
        return jSONObject2;
    }

    private String sourceFrom(JSONObject jSONObject) {
        return (jSONObject == null || !jSONObject.has("source")) ? "MANUAL" : jSONObject.optString("source", "MANUAL");
    }

    public void autoEvolve() {
        Throwable th = null;
        StrategyLab strategyLab = null;
        String str = null;
        int i = 0;
        String str2 = null;
        String str3 = null;
        JSONObject jSONObject = null;
        String str4 = null;
        String str5 = null;
        if (!"1".equals(this.db.setting("lab_auto", "1"))) {
            return;
        }
        try {
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM strategies WHERE deleted_at=0", null);
            int i2 = rawQuery.moveToFirst() ? rawQuery.getInt(0) : 0;
            rawQuery.close();
            if (i2 >= 40) {
                return;
            }
            StringBuilder sb = new StringBuilder();
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT name FROM strategies WHERE deleted_at=0 ORDER BY id DESC LIMIT 25", null);
            while (rawQuery2.moveToNext()) {
                if (sb.length() > 0) {
                    sb.append("; ");
                }
                sb.append(rawQuery2.getString(0));
            }
            rawQuery2.close();
            StringBuilder sb2 = new StringBuilder();
            Cursor rawQuery3 = this.db.getReadableDatabase().rawQuery("SELECT strategy, COUNT(*) FROM trades WHERE status='CLOSED' GROUP BY strategy HAVING COUNT(*)>=20", null);
            ArrayList<String[]> arrayList = new ArrayList();
            while (true) {
                i = 1;
                if (!rawQuery3.moveToNext()) {
                    break;
                } else {
                    arrayList.add(new String[]{rawQuery3.getString(0), rawQuery3.getString(1)});
                }
            }
            rawQuery3.close();
            for (String[] strArr : arrayList) {
                SQLiteDatabase readableDatabase = this.db.getReadableDatabase();
                String[] strArr2 = new String[i];
                strArr2[0] = strArr[0];
                Cursor rawQuery4 = readableDatabase.rawQuery("SELECT pnl FROM trades WHERE strategy=? AND status='CLOSED' ORDER BY closed_at DESC LIMIT 20", strArr2);
                double d = 0.0d;
                double d2 = 0.0d;
                while (rawQuery4.moveToNext()) {
                    double d3 = rawQuery4.getDouble(0);
                    if (d3 > 0.0d) {
                        d2 += d3;
                    } else {
                        d += -d3;
                    }
                }
                rawQuery4.close();
                if (d > 0.0d) {
                    sb2.append(strArr[0]).append(" rolling20 PF=").append(Math.round((d2 / d) * 100.0d) / 100.0d).append("; ");
                }
                i = 1;
            }
            StringBuilder append = new StringBuilder().append("Hamara AI Trading Lab abhi 3C Breakout (M1 BINANCE, 7 crypto pairs) MASTER strategy paper-trade kar raha hai (3 candles: C1+C2 strong body>=70% same direction, C3 opposite protected candle, 5-candle breakout window, SL opposite extreme, breakeven at +1R, close whole position at +3R). Existing lab strategies: ");
            int length = sb.length();
            CharSequence charSequence = sb;
            if (length == 0) {
                charSequence = "(none)";
            }
            StringBuilder append2 = append.append((Object) charSequence).append(". Live rolling performance (last 20 trades each): ");
            int length2 = sb2.length();
            CharSequence charSequence2 = sb2;
            if (length2 == 0) {
                charSequence2 = "(data nahi)";
            }
            JSONObject compileText = compileText(append2.append((Object) charSequence2).append(". Ye dekh kar aisi strategy suggest karo jo current WEAKNESS cover kare. Suggest ONE new complementary strategy that is DIFFERENT from all existing ones and can be evaluated on 1m Binance candles with these indicators only: rsi, price_vs_ema, ema_cross, sma, macd, bb, atr, supertrend, volume, change, stoch, cci, mfi, adx, candle, mss, bos, liq_sweep, ob_retest, fvg, killzone, premium_discount. (aakhri 7 Shaakuni Trap Trader ke indicators hain — liquidity sweep + MSS + order block + FVG + killzone + premium/discount — inhe prefer karo). Sirf strategy spec do, koi lambi explanation nahi.").toString());
            if (compileText == null) {
                this.db.log("WARN", "LAB", "AUTO_EVOLVE_SKIP", this.lastAiError != null ? this.lastAiError : "AI spec nahi bani");
                return;
            }
            if (!insert("AI_AUTO", "{}", compileText).optBoolean("ok")) {
                return;
            }
            Cursor rawQuery5 = this.db.getReadableDatabase().rawQuery("SELECT id FROM strategies WHERE deleted_at=0 ORDER BY id DESC LIMIT 1", null);
            long j = rawQuery5.moveToFirst() ? rawQuery5.getLong(0) : 0L;
            rawQuery5.close();
            if (j <= 0) {
                return;
            }
            JSONObject backtest = backtest(j);
            JSONObject optJSONObject = backtest == null ? null : backtest.optJSONObject("stats");
            Db db = this.db;
            StringBuilder append3 = new StringBuilder().append("AI proposed '").append(compileText.optString("name", "Custom")).append("' — backtest: ");
            if (optJSONObject == null) {
                str3 = "name";
                str4 = "LAB";
                jSONObject = compileText;
                str2 = "Custom";
                str5 = "fail";
            } else {
                str2 = "Custom";
                str3 = "name";
                jSONObject = compileText;
                str4 = "LAB";
                try {
                    str5 = optJSONObject.optInt("trades", 0) + " trades, WR " + optJSONObject.optDouble("winrate", 0.0d) + "%, net " + optJSONObject.optDouble("netPct", 0.0d) + "%";
                } catch (Throwable thz) {
                    strategyLab = this;
                    str = str4;
                    strategyLab.db.log("ERROR", str, "AUTO_EVOLVE_FAIL", String.valueOf(thz));
                }
            }
            str = str4;
            try {
                db.log("INFO", str, "AUTO_EVOLVE", append3.append(str5).toString());
                strategyLab = this;
                try {
                    Notifier.post(strategyLab.ctx, "Strategy Lab — Auto-Evolve", "AI ne nayi strategy banayi: " + jSONObject.optString(str3, str2) + (optJSONObject != null ? " — " + optJSONObject.optInt("trades", 0) + " trades, WR " + optJSONObject.optDouble("winrate", 0.0d) + "%, net " + optJSONObject.optDouble("netPct", 0.0d) + "%" : "") + " — Lab tab mein review karein (PAPER/LIVE aap approve karenge)");
                } catch (Throwable th2) {
                    th = th2;
                    strategyLab.db.log("ERROR", str, "AUTO_EVOLVE_FAIL", String.valueOf(th));
                }
            } catch (Throwable th3) {
                th = th3;
                strategyLab = this;
            }
        } catch (Throwable th4) {
            th = th4;
            strategyLab = this;
            str = "LAB";
        }
    }

    /* JADX WARN: Can't wrap try/catch for region: R(55:19|(1:21)(3:219|(1:221)(1:223)|222)|22|(1:24)(3:214|(1:216)(1:218)|217)|25|26|(14:28|(2:31|29)|32|33|(4:36|(3:38|39|40)(1:42)|41|34)|43|44|(1:46)(1:212)|47|(1:49)(1:211)|50|(1:52)(1:210)|53|(46:55|56|(5:58|(12:61|(4:64|(2:66|67)(2:69|70)|68|62)|71|72|(6:75|(1:77)|78|(3:84|85|86)(3:80|81|82)|83|73)|87|88|(1:90)(3:97|(1:99)(1:101)|100)|91|(2:93|94)(1:96)|95|59)|102|103|(1:105)(2:203|(1:205)(1:206)))(1:207)|106|(1:202)(2:110|(40:114|115|116|117|118|119|120|121|122|123|124|125|126|127|(4:129|130|131|132)(1:184)|133|134|135|136|137|138|139|140|141|142|143|144|145|(4:147|148|149|150)(1:172)|151|152|153|154|155|156|157|158|159|160|161))|192|(1:201)(1:200)|115|116|117|118|119|120|121|122|123|124|125|126|127|(0)(0)|133|134|135|136|137|138|139|140|141|142|143|144|145|(0)(0)|151|152|153|154|155|156|157|158|159|160|161)(1:208))(1:213)|209|56|(0)(0)|106|(1:108)|202|192|(1:194)|201|115|116|117|118|119|120|121|122|123|124|125|126|127|(0)(0)|133|134|135|136|137|138|139|140|141|142|143|144|145|(0)(0)|151|152|153|154|155|156|157|158|159|160|161) */
    /* JADX WARN: Code restructure failed: missing block: B:167:0x04f3, code lost:
    
        r10 = r17;
     */
    /* JADX WARN: Code restructure failed: missing block: B:173:0x04f6, code lost:
    
        r36 = r12;
     */
    /* JADX WARN: Code restructure failed: missing block: B:175:0x04f9, code lost:
    
        r36 = r12;
     */
    /* JADX WARN: Code restructure failed: missing block: B:176:0x04fe, code lost:
    
        r25 = r14;
     */
    /* JADX WARN: Code restructure failed: missing block: B:179:0x04fc, code lost:
    
        r56 = r12;
     */
    /* JADX WARN: Code restructure failed: missing block: B:186:0x0505, code lost:
    
        r2 = r4;
        r25 = r14;
        r10 = r17;
     */
    /* JADX WARN: Code restructure failed: missing block: B:188:0x050b, code lost:
    
        r2 = r4;
     */
    /* JADX WARN: Code restructure failed: missing block: B:189:0x0516, code lost:
    
        r25 = r14;
     */
    /* JADX WARN: Code restructure failed: missing block: B:191:0x050d, code lost:
    
        r2 = r4;
        r16 = r11;
        r35 = r13;
     */
    /* JADX WARN: Removed duplicated region for block: B:129:0x03c1  */
    /* JADX WARN: Removed duplicated region for block: B:147:0x0479 A[Catch: Exception -> 0x04f6, TRY_LEAVE, TryCatch #8 {Exception -> 0x04f6, blocks: (B:145:0x042c, B:147:0x0479), top: B:144:0x042c }] */
    /* JADX WARN: Removed duplicated region for block: B:172:0x0485  */
    /* JADX WARN: Removed duplicated region for block: B:184:0x03da  */
    /* JADX WARN: Removed duplicated region for block: B:207:0x0341  */
    /* JADX WARN: Removed duplicated region for block: B:58:0x021c  */
    /* JADX WARN: Unreachable blocks removed: 1, instructions: 2 */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    public JSONObject backtest(long id) {
        JSONObject spec = rowSpec(id);
        if (spec == null) return fail("Strategy nahi mili");
        String sym = db.setting("lab_symbol", "XAUUSD");
        // v3.0 DEEP DATA — bridge ho to 8000 bars, warna Yahoo range=1mo (~4000 5m bars)
        List<EngineCore.Candle> k = engine.deepCandles(sym, 30);
        if (k == null || k.size() < 120) return fail(sym + " ke real candles fetch nahi hue — dobara try karein");
        // drop unclosed last candle (v5.9.2 rule)
        if (!k.isEmpty() && System.currentTimeMillis() - k.get(k.size() - 1).ts < EngineCore.TF_MS_PUB) {
            k = k.subList(0, k.size() - 1);
        }
        if (k.size() < 120) return fail("Candle data bohat chhota hai");
        int bars = k.size();

        // v3.0 WALK-FORWARD: IS 70% / OOS 30% — dono segments same spec, same sim
        int isEnd = Math.max(120, (int) (bars * 0.7));
        double[] is = runSim(k, 60, isEnd, spec);
        double[] oos = runSim(k, Math.max(60, isEnd - 60), bars, spec);

        List<Double> rList = simR;   // last runSim ke R-multiples (OOS — honest sample)
        List<Double> pnlList = simPnl;

        // ===== v3.0 METRICS SUITE (OOS par — honest sample; IS comparison ke liye bhi) =====
        double pf = oos[2] > 0 ? Math.round(100.0 * oos[1] / oos[2]) / 100.0 : (oos[1] > 0 ? 99 : 0);
        double isPf = is[2] > 0 ? Math.round(100.0 * is[1] / is[2]) / 100.0 : (is[1] > 0 ? 99 : 0);
        double netPct = oos[0];
        double maxDD = oos[11];
        int nT = (int) oos[3];
        int wins = (int) oos[4];
        double fees = oos[6];

        // R-based stats (Jesse-standard)
        double avgR = 0, expectancy = 0, sharpe = 0, sortino = 0, calmar = 0;
        if (!rList.isEmpty()) {
            double sum = 0;
            for (double r : rList) sum += r;
            avgR = sum / rList.size();
            expectancy = Math.round(avgR * 1000.0) / 1000.0;
            double mean = avgR, var = 0, dvar = 0;
            for (double r : rList) { var += (r - mean) * (r - mean); if (r < 0) dvar += r * r; }
            var /= Math.max(1, rList.size() - 1);
            double sd = Math.sqrt(var);
            double dsd = Math.sqrt(dvar / Math.max(1, rList.size()));
            // trade-level Sharpe annualized (web engine parity, capped 50k)
            double years = bars * EngineCore.TF_MS_PUB / (365.25 * 24 * 3600 * 1000.0);
            double tpy = years > 0 ? rList.size() / years : 0;
            if (sd > 0) sharpe = Math.round(mean / sd * Math.sqrt(Math.min(tpy, 50000)) * 100.0) / 100.0;
            if (dsd > 0) sortino = Math.round(mean / dsd * Math.sqrt(Math.min(tpy, 50000)) * 100.0) / 100.0;
            if (maxDD > 0) calmar = Math.round(netPct / maxDD * 100.0) / 100.0;
        }

        // ===== v3.0 MONTE CARLO (Jesse pattern): trade-order shuffle → DD distribution
        //      + side-flip bootstrap → p-value (luck vs edge)
        double p5DD = 0, p50DD = 0, p95DD = 0, pValue = 1;
        String tag = "NOISE";
        if (pnlList.size() >= 10) {
            List<Double> dds = new ArrayList<>();
            int beat = 0;
            java.util.Random rnd = new java.util.Random(42);
            double actualPf = pf;
            for (int it = 0; it < 1000; it++) {
                List<Double> sh = new ArrayList<>(pnlList);
                java.util.Collections.shuffle(sh, rnd);
                double eq = 100, peak = 100, dd = 0;
                for (double p : sh) { eq += p; peak = Math.max(peak, eq); if (peak > 0) dd = Math.max(dd, (peak - eq) / peak); }
                dds.add(dd * 100);
                // side-flip test: random sign flip = luck distribution
                double gw = 0, gl = 0;
                for (double p : sh) { double v = rnd.nextBoolean() ? p : -p; if (v > 0) gw += v; else gl += -v; }
                double rpf = gl > 0 ? gw / gl : (gw > 0 ? 99 : 0);
                if (rpf >= actualPf) beat++;
            }
            java.util.Collections.sort(dds);
            p5DD = Math.round(dds.get(50) * 10.0) / 10.0;
            p50DD = Math.round(dds.get(500) * 10.0) / 10.0;
            p95DD = Math.round(dds.get(950) * 10.0) / 10.0;
            pValue = Math.round(beat / 1000.0 * 1000.0) / 1000.0;
            tag = pValue < 0.05 ? "EDGE" : pValue < 0.2 ? "MARGINAL" : "NOISE";
        }

        // v3.0 VERDICT — ab OOS + MC dono ke bina STRONG namumkin
        String verdict = (isPf >= 1.15 && pf >= 1.0 && nT >= 30 && !"NOISE".equals(tag)) ? "STRONG"
                : (isPf >= 1.0 && pf >= 0.9 && nT >= 15 && !"NOISE".equals(tag)) ? "OK" : "WEAK";

        JSONObject stats = new JSONObject();
        try {
            stats.put("symbol", sym).put("bars", bars)
                    .put("trades", nT).put("wins", wins).put("losses", nT - wins)
                    .put("winrate", nT > 0 ? Math.round(1000.0 * wins / nT) / 10.0 : 0)
                    .put("pf", pf).put("net", Math.round(oos[0] * 100.0) / 100.0).put("netPct", netPct)
                    .put("maxDD", Math.round(maxDD * 100.0) / 10.0)
                    .put("isPf", isPf).put("oosPf", pf).put("isNet", Math.round(is[0] * 100.0) / 100.0)
                    .put("expectancy", expectancy).put("avgR", Math.round(avgR * 1000.0) / 1000.0)
                    .put("sharpe", sharpe).put("sortino", sortino).put("calmar", calmar)
                    .put("fees", Math.round(fees * 100.0) / 100.0)
                    .put("avgBars", nT > 0 ? Math.round(oos[5] / nT) : 0)
                    .put("exits", new JSONObject().put("SL", (int) oos[7]).put("TP", (int) oos[8]).put("TIME", (int) oos[9]))
                    .put("mc", new JSONObject().put("p5DD", p5DD).put("p50DD", p50DD).put("p95DD", p95DD)
                            .put("pValue", pValue).put("tag", tag))
                    .put("verdict", verdict)
                    .put("riskModel", "1% baseline, SL 1.5xATR, TP 2.5xATR, fees 0.05%/side, IS70/OOS30 walk-forward + Monte Carlo (v3.0 HONEST LAB)");
        } catch (Exception ignored) { }

        db.getWritableDatabase().execSQL(
                "UPDATE strategies SET status=?, stats=?, updated_at=? WHERE id=?",
                new Object[]{"BACKTESTED", stats.toString(), System.currentTimeMillis(), id});
        db.log("INFO", "LAB", "BACKTEST_DONE", "strategy #" + id + " on " + sym + " — " + nT + " trades, WR "
                + stats.optDouble("winrate", 0) + "%, IS PF " + isPf + ", OOS PF " + pf + ", net " + netPct
                + "%, avgR " + avgR + ", MC " + tag + " (p=" + pValue + "), verdict " + verdict);
        JSONObject out = new JSONObject();
        try { out.put("ok", true).put("stats", stats); } catch (Exception ignored) { }
        return out;
    }

    private double[] runSim(List<EngineCore.Candle> list, int i, int i2, JSONObject jSONObject) {
        int i3 = 0;
        double d = 0.0d;
        boolean z = false;
        double d2 = 0.0d;
        int i4 = 0;
        int i5 = 0;
        JSONArray jSONArray = null;
        int i6 = 0;
        double d3 = 0.0d;
        int i7 = 0;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        boolean z2 = false;
        double d7 = 0.0d;
        double d8 = 0.0d;
        double d9 = 0.0d;
        double d10 = 0.0d;
        int i8 = i2;
        int i9 = 1;
        if (jSONObject.optString("side", "BOTH").equals("BUY")) {
            i3 = 1;
        } else {
            i3 = jSONObject.optString("side", "BOTH").equals("SELL") ? -1 : 0;
        }
        boolean equals = "ANY".equals(jSONObject.optString("logic", "ALL"));
        JSONArray optJSONArray = jSONObject.optJSONArray("conditions");
        this.simR = new ArrayList();
        this.simPnl = new ArrayList();
        int i10 = i;
        int i11 = 0;
        double d11 = 100.0d;
        boolean z3 = false;
        double d12 = 0.0d;
        double d13 = 0.0d;
        double d14 = 0.0d;
        double d15 = 0.0d;
        double d16 = 100.0d;
        double d17 = 0.0d;
        double d18 = 0.0d;
        double d19 = 0.0d;
        double d20 = 0.0d;
        int i12 = 0;
        int i13 = 0;
        int i14 = 0;
        double d21 = 0.0d;
        int i15 = 0;
        double d22 = 0.0d;
        int i16 = 0;
        int i17 = 0;
        int i18 = 0;
        while (i10 < i8) {
            EngineCore.Candle candle = list.get(i10);
            if (z3) {
                int i19 = i11;
                if (i11 != i9 ? candle.h < d15 : candle.l > d15) {
                    i11 = i19;
                    z2 = false;
                } else {
                    i11 = i19;
                    z2 = true;
                }
                z = z3;
                boolean z4 = i11 != 1 ? candle.l <= d19 : candle.h >= d19;
                int i20 = i10 - i14;
                boolean z5 = i20 >= 288;
                if (z2 || z4 || z5) {
                    if (z2) {
                        d7 = d15;
                    } else {
                        d7 = z4 ? d19 : candle.c;
                    }
                    double d23 = 5.0E-4d * ((d12 * d13) + (d12 * d7));
                    d14 += d23;
                    boolean z6 = z4;
                    double d24 = ((i11 == 1 ? d7 - d13 : d13 - d7) * d12) - d23;
                    double d25 = d12;
                    double d26 = d16 + d24;
                    double max = Math.max(d11, d26);
                    if (max > 0.0d) {
                        double d27 = ((max - d26) / max) * 100.0d;
                        d8 = d17;
                        d9 = max;
                        d10 = d27;
                        d16 = d26;
                    } else {
                        d16 = d26;
                        d8 = d17;
                        d9 = max;
                        d10 = 0.0d;
                    }
                    double max2 = Math.max(d8, d10);
                    double d28 = d18 > 0.0d ? d24 / d18 : 0.0d;
                    this.simR.add(Double.valueOf(d28));
                    this.simPnl.add(Double.valueOf(d24));
                    d20 += d28;
                    i12++;
                    i13 += i20;
                    if (d24 >= 0.0d) {
                        i15++;
                        d22 += d24;
                    } else {
                        d21 += -d24;
                    }
                    if (z2) {
                        i17++;
                    } else {
                        int i21 = i17;
                        if (z6) {
                            i18++;
                        } else {
                            i16++;
                        }
                        i17 = i21;
                    }
                    jSONArray = optJSONArray;
                    d11 = d9;
                    d3 = max2;
                    d12 = d25;
                    z3 = false;
                    i6 = i3;
                    i10++;
                    i8 = i2;
                    optJSONArray = jSONArray;
                    i3 = i6;
                    d17 = d3;
                    i9 = 1;
                } else {
                    jSONArray = optJSONArray;
                    d6 = d11;
                    d2 = d12;
                    d3 = d17;
                    i4 = i17;
                    i5 = i18;
                    i6 = i3;
                    z3 = z;
                    i17 = i4;
                    i18 = i5;
                    d12 = d2;
                    d11 = d6;
                    i10++;
                    i8 = i2;
                    optJSONArray = jSONArray;
                    i3 = i6;
                    d17 = d3;
                    i9 = 1;
                }
            } else {
                z = z3;
                d2 = d12;
                double d29 = d17;
                i4 = i17;
                i5 = i18;
                int i22 = i10 + 1;
                int evaluateSpec = evaluateSpec(optJSONArray, equals ? 1 : 0, list.subList(Math.max(0, i10 - 499), i22));
                if (evaluateSpec == 0) {
                    jSONArray = optJSONArray;
                    i6 = i3;
                } else {
                    if (i3 != 0) {
                        evaluateSpec = i3;
                    }
                    jSONArray = optJSONArray;
                    i6 = i3;
                    double atr = atr(list.subList(Math.max(0, i10 - 199), i22), 14);
                    if (!Double.isNaN(atr) && atr > 0.0d) {
                        double d30 = 1.5d * atr;
                        double d31 = (0.01d * d16) / d30;
                        d3 = d29;
                        double d32 = 0.95d * d16;
                        if (candle.c * d31 > d32) {
                            d31 = d32 / candle.c;
                        }
                        if (d31 <= 0.0d) {
                            d6 = d11;
                            z3 = z;
                            i17 = i4;
                            i18 = i5;
                            d12 = d2;
                            d11 = d6;
                            i10++;
                            i8 = i2;
                            optJSONArray = jSONArray;
                            i3 = i6;
                            d17 = d3;
                            i9 = 1;
                        } else {
                            double d33 = candle.c;
                            double d34 = d11;
                            d15 = evaluateSpec == 1 ? candle.c - d30 : candle.c + d30;
                            if (evaluateSpec == 1) {
                                i7 = evaluateSpec;
                                d4 = d33;
                                d5 = candle.c + (atr * 2.5d);
                            } else {
                                i7 = evaluateSpec;
                                d4 = d33;
                                d5 = candle.c - (atr * 2.5d);
                            }
                            d19 = d5;
                            d18 = Math.abs(candle.c - d15) * d31;
                            i14 = i10;
                            i11 = i7;
                            d13 = d4;
                            d12 = d31;
                            d11 = d34;
                            z3 = true;
                            i17 = i4;
                            i18 = i5;
                            i10++;
                            i8 = i2;
                            optJSONArray = jSONArray;
                            i3 = i6;
                            d17 = d3;
                            i9 = 1;
                        }
                    }
                }
                d6 = d11;
                d3 = d29;
                z3 = z;
                i17 = i4;
                i18 = i5;
                d12 = d2;
                d11 = d6;
                i10++;
                i8 = i2;
                optJSONArray = jSONArray;
                i3 = i6;
                d17 = d3;
                i9 = 1;
            }
        }
        double d35 = d11;
        double d36 = d12;
        double d37 = d17;
        int i23 = i17;
        int i24 = i18;
        if (z3) {
            EngineCore.Candle candle2 = list.get(i2 - 1);
            double d38 = ((d36 * d13) + (candle2.c * d36)) * 5.0E-4d;
            d14 += d38;
            double d39 = ((i11 == 1 ? candle2.c - d13 : d13 - candle2.c) * d36) - d38;
            double d40 = d16 + d39;
            double max3 = Math.max(d35, d40);
            d = Math.max(d37, max3 > 0.0d ? ((max3 - d40) / max3) * 100.0d : 0.0d);
            double d41 = d18 > 0.0d ? d39 / d18 : 0.0d;
            this.simR.add(Double.valueOf(d41));
            this.simPnl.add(Double.valueOf(d39));
            d20 += d41;
            i12++;
            i13 += i2 - i14;
            if (d39 >= 0.0d) {
                i15++;
                d22 += d39;
            } else {
                d21 += -d39;
            }
            i16++;
            d16 = d40;
        } else {
            d = d37;
        }
        return new double[]{d16 - 100.0d, d22, d21, i12, i15, i13, d14, i23, i24, i16, d20, d};
    }

    public JSONObject startPaper(long j) {
        return setStatus(j, "PAPER", "paper shadow phase shuru — ab ye strategy live candles par khud signal degi");
    }

    public JSONObject approve(long j) {
        String str = null;
        JSONObject statsOf = statsOf(j);
        String optString = statsOf != null ? statsOf.optString("verdict", "") : "";
        double optDouble = statsOf != null ? statsOf.optDouble("pf", 0.0d) : 0.0d;
        int optInt = statsOf != null ? statsOf.optInt("trades", 0) : 0;
        if (!"WEAK".equals(optString)) {
            str = "owner ne LIVE approve kiya — ye strategy ab apne aap trade karegi";
        } else {
            str = "owner ne LIVE approve kiya — ⚠ WARNING: backtest verdict WEAK (PF " + optDouble + ", " + optInt + " trades) — ye strategy loss de sakti hai";
        }
        return setStatus(j, "ACTIVE", str);
    }

    private JSONObject statsOf(long j) {
        JSONObject jSONObject = null;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT stats FROM strategies WHERE id=?", new String[]{String.valueOf(j)});
        if (rawQuery.moveToFirst()) {
            try {
                jSONObject = new JSONObject(rawQuery.getString(0));
            } catch (Exception unused) {
            }
            rawQuery.close();
            return jSONObject;
        }
        jSONObject = null;
        rawQuery.close();
        return jSONObject;
    }

    public JSONObject reject(long j) {
        return setStatus(j, "REJECTED", "strategy reject hui");
    }

    public JSONObject remove(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name, status FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(j)});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            return fail("Strategy nahi mili (shayad pehle hi delete ho chuki)");
        }
        String string = rawQuery.getString(0);
        String string2 = rawQuery.getString(1);
        rawQuery.close();
        long currentTimeMillis = System.currentTimeMillis();
        this.db.getWritableDatabase().execSQL("UPDATE strategies SET deleted_at=?, updated_at=? WHERE id=?", new Object[]{Long.valueOf(currentTimeMillis), Long.valueOf(currentTimeMillis), Long.valueOf(j)});
        this.db.log("INFO", "LAB", "STRATEGY_TRASHED", "'" + string + "' (#" + j + ", " + string2 + ") Trash mein — 7 din tak UNDO possible, phir auto-purge");
        purgeTrash();
        JSONObject jSONObject = new JSONObject();
        try {
            jSONObject.put("ok", true).put("message", "'" + string + "' delete hui — ghalti se hui? 7 din tak UNDO button se wapas la sakte ho");
        } catch (Exception unused) {
        }
        return jSONObject;
    }

    public JSONObject restore(long j) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name FROM strategies WHERE id=? AND deleted_at>0", new String[]{String.valueOf(j)});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            return fail("Trash mein aisi koi strategy nahi mili");
        }
        String string = rawQuery.getString(0);
        rawQuery.close();
        this.db.getWritableDatabase().execSQL("UPDATE strategies SET deleted_at=0, updated_at=? WHERE id=?", new Object[]{Long.valueOf(System.currentTimeMillis()), Long.valueOf(j)});
        this.db.log("INFO", "LAB", "STRATEGY_RESTORED", "'" + string + "' (#" + j + ") Trash se restore — UNDO kaam kar gaya");
        JSONObject jSONObject = new JSONObject();
        try {
            jSONObject.put("ok", true).put("message", "'" + string + "' wapas restore ho gayi — apni original status ke saath");
        } catch (Exception unused) {
        }
        return jSONObject;
    }

    public JSONObject trash() {
        JSONObject jSONObject = new JSONObject();
        try {
            JSONArray jSONArray = new JSONArray();
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, name, status, deleted_at FROM strategies WHERE deleted_at>0 ORDER BY deleted_at DESC", null);
            long currentTimeMillis = System.currentTimeMillis();
            while (rawQuery.moveToNext()) {
                long j = rawQuery.getLong(3);
                long j2 = 7 - ((currentTimeMillis - j) / 86400000);
                if (j2 < 0) {
                    j2 = 0;
                }
                jSONArray.put(new JSONObject().put("id", rawQuery.getLong(0)).put("name", rawQuery.getString(1)).put("status", rawQuery.getString(2)).put("deleted_at", j).put("daysLeft", j2));
            }
            rawQuery.close();
            jSONObject.put("trash", jSONArray).put("ok", true);
            return jSONObject;
        } catch (Exception e) {
            return fail("Trash load fail: " + e.getMessage());
        }
    }

    private void purgeTrash() {
        this.db.getWritableDatabase().execSQL("DELETE FROM strategies WHERE deleted_at>0 AND deleted_at<?", new Object[]{Long.valueOf(System.currentTimeMillis() - 604800000)});
    }

    private JSONObject setStatus(long j, String str, String str2) {
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT name FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(j)});
        if (!rawQuery.moveToFirst()) {
            rawQuery.close();
            return fail("Strategy nahi mili");
        }
        String string = rawQuery.getString(0);
        rawQuery.close();
        this.db.getWritableDatabase().execSQL("UPDATE strategies SET status=?, updated_at=? WHERE id=?", new Object[]{str, Long.valueOf(System.currentTimeMillis()), Long.valueOf(j)});
        this.db.log("INFO", "LAB", "STRATEGY_" + str, "'" + string + "' — " + str2);
        if ("ACTIVE".equals(str)) {
            Notifier.post(this.ctx, "Strategy Lab", string + " ab LIVE hai — " + str2);
        }
        JSONObject jSONObject = new JSONObject();
        try {
            jSONObject.put("ok", true).put("status", str).put("message", string + " — " + str2);
        } catch (Exception unused) {
        }
        return jSONObject;
    }

    private JSONObject rowSpec(long j) {
        JSONObject jSONObject = null;
        Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT spec FROM strategies WHERE id=? AND deleted_at=0", new String[]{String.valueOf(j)});
        if (rawQuery.moveToFirst()) {
            try {
                jSONObject = new JSONObject(rawQuery.getString(0));
            } catch (Exception unused) {
            }
            rawQuery.close();
            return jSONObject;
        }
        jSONObject = null;
        rawQuery.close();
        return jSONObject;
    }

    private JSONObject fail(String str) {
        JSONObject jSONObject = new JSONObject();
        try {
            jSONObject.put("ok", false).put("error", str);
        } catch (Exception unused) {
        }
        return jSONObject;
    }

    public static int evaluateSpec(JSONArray jSONArray, int i, List<EngineCore.Candle> list) {
        Object[] evalCond = null;
        if (jSONArray != null && jSONArray.length() != 0) {
            int i2 = 0;
            int i3 = 0;
            int i4 = 0;
            for (int i5 = 0; i5 < jSONArray.length(); i5++) {
                JSONObject optJSONObject = jSONArray.optJSONObject(i5);
                if (optJSONObject != null && (evalCond = evalCond(optJSONObject, list)) != null) {
                    if (((Integer) evalCond[0]).intValue() == 1) {
                        i2++;
                    }
                    int intValue = ((Integer) evalCond[1]).intValue();
                    if (((Integer) evalCond[0]).intValue() == 1) {
                        if (intValue > 0) {
                            i3++;
                        } else if (intValue < 0) {
                            i4++;
                        }
                    }
                }
            }
            if (i != 1 ? i2 == jSONArray.length() : i2 > 0) {
                return (i3 <= i4 && i4 > i3) ? -1 : 1;
            }
        }
        return 0;
    }

    /* JADX WARN: Can't fix incorrect switch cases order, some code will duplicate */
    /* JADX WARN: Code restructure failed: missing block: B:181:0x039d, code lost:
    
        if (r3.equals("price_above") == false) goto L231;
     */
    /* JADX WARN: Failed to restore switch over string. Please report as a decompilation issue */
    /* JADX WARN: Multi-variable type inference failed */
    /* JADX WARN: Type inference failed for: r19v0, types: [boolean, int] */
    /* JADX WARN: Type inference failed for: r8v1 */
    /* JADX WARN: Type inference failed for: r8v2, types: [boolean] */
    /* JADX WARN: Type inference failed for: r8v3 */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    private static Object[] evalCond(JSONObject jSONObject, List<EngineCore.Candle> list) {
        char c = '\u0000';
        int i = 0;
        int r8 = 0;
        int i2 = 0;
        int i3 = 0;
        int i4 = 0;
        int i5 = 0;
        boolean z = false;
        int i6 = 0;
        String optString = jSONObject.optString("ind", "");
        String optString2 = jSONObject.optString("op", "");
        EngineCore.Candle candle = list.get(list.size() - 1);
        double d = candle.c;
        optString.hashCode();
        char c2 = 2;
        switch (optString.hashCode()) {
            case -1698822398:
                if (optString.equals("supertrend")) {
                    c = 0;
                    break;
                }
                c = 65535;
                break;
            case -1588979731:
                if (optString.equals("price_vs_ema")) {
                    c = 1;
                    break;
                }
                c = 65535;
                break;
            case -1423570391:
                if (optString.equals("premium_discount")) {
                    c = 2;
                    break;
                }
                c = 65535;
                break;
            case -1367723251:
                if (optString.equals("candle")) {
                    c = 3;
                    break;
                }
                c = 65535;
                break;
            case -1361636432:
                if (optString.equals("change")) {
                    c = 4;
                    break;
                }
                c = 65535;
                break;
            case -810883302:
                if (optString.equals("volume")) {
                    c = 5;
                    break;
                }
                c = 65535;
                break;
            case -603815926:
                if (optString.equals("killzone")) {
                    c = 6;
                    break;
                }
                c = 65535;
                break;
            case 3136:
                if (optString.equals("bb")) {
                    c = 7;
                    break;
                }
                c = 65535;
                break;
            case 96437:
                if (optString.equals("adx")) {
                    c = '\b';
                    break;
                }
                c = 65535;
                break;
            case 96927:
                if (optString.equals("atr")) {
                    c = '\t';
                    break;
                }
                c = 65535;
                break;
            case 97734:
                if (optString.equals("bos")) {
                    c = '\n';
                    break;
                }
                c = 65535;
                break;
            case 98313:
                if (optString.equals("cci")) {
                    c = 11;
                    break;
                }
                c = 65535;
                break;
            case 101783:
                if (optString.equals("fvg")) {
                    c = '\f';
                    break;
                }
                c = 65535;
                break;
            case 108016:
                if (optString.equals("mfi")) {
                    c = '\r';
                    break;
                }
                c = 65535;
                break;
            case 108429:
                if (optString.equals("mss")) {
                    c = 14;
                    break;
                }
                c = 65535;
                break;
            case 113224:
                if (optString.equals("rsi")) {
                    c = 15;
                    break;
                }
                c = 65535;
                break;
            case 113991:
                if (optString.equals("sma")) {
                    c = 16;
                    break;
                }
                c = 65535;
                break;
            case 3343605:
                if (optString.equals("macd")) {
                    c = 17;
                    break;
                }
                c = 65535;
                break;
            case 109770515:
                if (optString.equals("stoch")) {
                    c = 18;
                    break;
                }
                c = 65535;
                break;
            case 713225601:
                if (optString.equals("liq_sweep")) {
                    c = 19;
                    break;
                }
                c = 65535;
                break;
            case 1826706746:
                if (optString.equals("ema_cross")) {
                    c = 20;
                    break;
                }
                c = 65535;
                break;
            case 2006797617:
                if (optString.equals("ob_retest")) {
                    c = 21;
                    break;
                }
                c = 65535;
                break;
            default:
                c = 65535;
                break;
        }
        switch (c) {
            case 0:
                boolean z2 = supertrendDir(list, jSONObject.optInt("p", 10), jSONObject.optDouble("m", 3.0d)) > 0;
                return new Object[]{Integer.valueOf(optString2.equals("bull") == z2 ? 1 : 0), Integer.valueOf(z2 ? 1 : -1)};
            case 1:
                double ema = ema(list, jSONObject.optInt("p", 50));
                if (Double.isNaN(ema)) {
                    return new Object[]{0, 0};
                }
                boolean z3 = d > ema;
                return new Object[]{Integer.valueOf(optString2.equals("above") == z3 ? 1 : 0), Integer.valueOf(z3 ? 1 : -1)};
            case 2:
                double[] prevDayHighLow = EngineCore.prevDayHighLow(list);
                if (prevDayHighLow == null) {
                    return new Object[]{0, 0};
                }
                int i7 = d < (prevDayHighLow[0] + prevDayHighLow[1]) / 2.0d ? 1 : 0;
                return new Object[]{Integer.valueOf(optString2.contains("discount") ? i7 : i7 == 0 ? 1 : 0), Integer.valueOf(i7 != 0 ? 1 : -1)};
            case 3:
                optString2.hashCode();
                switch (optString2) {
                    case "hammer":
                        double abs = Math.abs(candle.c - candle.o);
                        return new Object[]{Integer.valueOf((Math.min(candle.c, candle.o) - candle.l <= abs * 2.0d || candle.h - Math.max(candle.c, candle.o) >= abs) ? 0 : 1), 1};
                    case "engulf_bear":
                        return new Object[]{Integer.valueOf(engulf(list, -1) ? 1 : 0), -1};
                    case "engulf_bull":
                        return new Object[]{Integer.valueOf(engulf(list, 1) ? 1 : 0), 1};
                    case "doji":
                        double abs2 = Math.abs(candle.c - candle.o);
                        double d2 = candle.h - candle.l;
                        return new Object[]{Integer.valueOf((d2 <= 0.0d || abs2 > d2 * 0.1d) ? 0 : 1), 0};
                    default:
                        return new Object[]{0, 0};
                }
            case 4:
                int max = Math.max(1, jSONObject.optInt("n", 5));
                if (list.size() >= max + 1) {
                    double d3 = list.get((list.size() - 1) - max).c;
                    return new Object[]{Integer.valueOf(cmp(d3 != 0.0d ? ((d - d3) * 100.0d) / d3 : 0.0d, optString2, jSONObject.optDouble("v", 1.0d)) ? 1 : 0), Integer.valueOf(optString2.contains("<") ? -1 : 1)};
                }
                return new Object[]{0, 0};
            case 5:
                if (list.size() >= jSONObject.optInt("p", 20) + 2) {
                    int optInt = jSONObject.optInt("p", 20);
                    int size = (list.size() - 1) - optInt;
                    double r20 = 0.0d;
                    for (int i8 = 1; size < list.size() - i8; i8 = 1) {
                        r20 += list.get(size).v;
                        size++;
                    }
                    return new Object[]{Integer.valueOf(cmp(candle.v, optString2, jSONObject.optDouble("v", 1.5d) * (r20 / ((double) optInt))) ? 1 : 0), 0};
                }
                return new Object[]{0, 0};
            case 6:
                String[] sessionNow = EngineCore.sessionNow(candle.ts);
                if (optString2.contains("london")) {
                    i = "LONDON".equals(sessionNow[0]) ? 1 : 0;
                } else if (optString2.contains("newyork") || optString2.contains("new york")) {
                    i = "NEW YORK".equals(sessionNow[0]) ? 1 : 0;
                } else {
                    i = "yes".equals(sessionNow[1]) ? 1 : 0;
                }
                return new Object[]{Integer.valueOf(i), 0};
            case 7:
                double[] bollinger = bollinger(list, jSONObject.optInt("p", 20), jSONObject.optDouble("k", 2.0d));
                if (bollinger == null) {
                    return new Object[]{0, 0};
                }
                optString2.hashCode();
                switch (optString2) {
                    case "squeeze":
                        double d4 = bollinger[0] - bollinger[1];
                        double d5 = bollinger[2];
                        if (d5 == 0.0d) {
                            d5 = 1.0d;
                        }
                        return new Object[]{Integer.valueOf(d4 / d5 < 0.03d ? 1 : 0), 0};
                    case "lower_touch":
                        return new Object[]{Integer.valueOf(d <= bollinger[1] ? 1 : 0), 1};
                    case "upper_touch":
                        return new Object[]{Integer.valueOf(d >= bollinger[0] ? 1 : 0), -1};
                    default:
                        return new Object[]{0, 0};
                }
            case '\b':
                double adx = adx(list, jSONObject.optInt("p", 14));
                return Double.isNaN(adx) ? new Object[]{0, 0} : new Object[]{Integer.valueOf(cmp(adx, optString2, jSONObject.optDouble("v", 25.0d)) ? 1 : 0), 0};
            case '\t':
                double atr = atr(list, jSONObject.optInt("p", 14));
                if (Double.isNaN(atr) || d <= 0.0d) {
                    return new Object[]{0, 0};
                }
                return new Object[]{Integer.valueOf(cmp((atr * 100.0d) / d, optString2, jSONObject.optDouble("v", 0.3d)) ? 1 : 0), 0};
            case '\n':
                EngineCore.StructEvent structureWalk = EngineCore.structureWalk(list, 10);
                if (structureWalk == null) {
                    return new Object[]{0, 0};
                }
                boolean z4 = !optString2.contains("bear");
                boolean equals = "BULL".equals(structureWalk.dir);
                return new Object[]{Integer.valueOf((z4 == equals && "BOS".equals(structureWalk.kind)) ? 1 : 0), Integer.valueOf(equals ? 1 : -1)};
            case 11:
                double cci = cci(list, jSONObject.optInt("p", 20));
                if (Double.isNaN(cci)) {
                    return new Object[]{0, 0};
                }
                return new Object[]{Integer.valueOf(cmp(cci, optString2, jSONObject.optDouble("v", -100.0d)) ? 1 : 0), Integer.valueOf(optString2.contains("<") ? 1 : -1)};
            case '\f':
                double[] latestFvg = EngineCore.latestFvg(list);
                if (latestFvg == null) {
                    return new Object[]{0, 0};
                }
                int i9 = (int) latestFvg[2];
                return new Object[]{Integer.valueOf(("any".equals(optString2) || (optString2.contains("bull") && i9 > 0) || (optString2.contains("bear") && i9 < 0)) ? 1 : 0), Integer.valueOf(i9)};
            case '\r':
                double mfi = mfi(list, jSONObject.optInt("p", 14));
                if (Double.isNaN(mfi)) {
                    return new Object[]{0, 0};
                }
                return new Object[]{Integer.valueOf(cmp(mfi, optString2, jSONObject.optDouble("v", 20.0d)) ? 1 : 0), Integer.valueOf(optString2.contains("<") ? 1 : -1)};
            case 14:
                EngineCore.StructEvent structureWalk2 = EngineCore.structureWalk(list, 10);
                if (structureWalk2 == null) {
                    return new Object[]{0, 0};
                }
                boolean z5 = !optString2.contains("bear");
                boolean equals2 = "BULL".equals(structureWalk2.dir);
                return new Object[]{Integer.valueOf((z5 == equals2 && "MSS".equals(structureWalk2.kind)) ? 1 : 0), Integer.valueOf(equals2 ? 1 : -1)};
            case 15:
                double rsi = rsi(list, jSONObject.optInt("p", 14));
                if (Double.isNaN(rsi)) {
                    return new Object[]{0, 0};
                }
                return new Object[]{Integer.valueOf(cmp(rsi, optString2, jSONObject.optDouble("v", 30.0d)) ? 1 : 0), Integer.valueOf(optString2.contains("<") ? 1 : -1)};
            case 16:
                double sma = sma(list, jSONObject.optInt("p", 20));
                if (!Double.isNaN(sma)) {
                    optString2.hashCode();
                    switch (optString2.hashCode()) {
                        case -1089750609:
                            if (optString2.equals("slope_up")) {
                                c2 = 0;
                                break;
                            }
                            c2 = 65535;
                            break;
                        case 721181366:
                            if (optString2.equals("slope_down")) {
                                c2 = 1;
                                break;
                            }
                            c2 = 65535;
                            break;
                        case 1868520743:
                            break;
                        case 1869530555:
                            if (optString2.equals("price_below")) {
                                c2 = 3;
                                break;
                            }
                            c2 = 65535;
                            break;
                        default:
                            c2 = 65535;
                            break;
                    }
                    switch (c2) {
                        case 0:
                            double sma2 = sma(list.subList(0, list.size() - 3), jSONObject.optInt("p", 20));
                            return new Object[]{Integer.valueOf((Double.isNaN(sma2) || sma <= sma2) ? 0 : 1), 1};
                        case 1:
                            double sma3 = sma(list.subList(0, list.size() - 3), jSONObject.optInt("p", 20));
                            return new Object[]{Integer.valueOf((Double.isNaN(sma3) || sma >= sma3) ? 0 : 1), -1};
                        case 2:
                            return new Object[]{Integer.valueOf(d > sma ? 1 : 0), 1};
                        case 3:
                            return new Object[]{Integer.valueOf(d < sma ? 1 : 0), -1};
                        default:
                            return new Object[]{0, 0};
                    }
                }
                return new Object[]{0, 0};
            case 17:
                double[] macd = macd(list, jSONObject.optInt("f", 12), jSONObject.optInt("s", 26), jSONObject.optInt("sig", 9));
                if (macd == null) {
                    return new Object[]{0, 0};
                }
                boolean z6 = macd[0] > macd[1];
                return new Object[]{Integer.valueOf(optString2.equals("bull") == z6 ? 1 : 0), Integer.valueOf(z6 ? 1 : -1)};
            case 18:
                double stochK = stochK(list, jSONObject.optInt("p", 14));
                if (Double.isNaN(stochK)) {
                    return new Object[]{0, 0};
                }
                return new Object[]{Integer.valueOf(cmp(stochK, optString2, jSONObject.optDouble("v", 20.0d)) ? 1 : 0), Integer.valueOf(optString2.contains("<") ? 1 : -1)};
            case 19:
                double[] prevDayHighLow2 = EngineCore.prevDayHighLow(list);
                double[] prevWeekHighLow = EngineCore.prevWeekHighLow(list);
                if (prevDayHighLow2 != null) {
                    r8 = 1;
                    int equals3 = "SWEEP".equals(EngineCore.sweepStatus(list, prevDayHighLow2[0], true)) ? 1 : 0;
                    int i10 = equals3 != 0 ? -1 : 0;
                    if ("SWEEP".equals(EngineCore.sweepStatus(list, prevDayHighLow2[1], false))) {
                        i2 = 1;
                        i5 = equals3 + 1;
                    } else {
                        i2 = i10;
                        i5 = equals3;
                    }
                    i3 = i5;
                } else {
                    r8 = 1;
                    i2 = 0;
                    i3 = 0;
                }
                if (prevWeekHighLow != null) {
                    if ("SWEEP".equals(EngineCore.sweepStatus(list, prevWeekHighLow[0], r8 != 0))) {
                        i3++;
                        i4 = -1;
                    } else {
                        i4 = i2;
                    }
                    if ("SWEEP".equals(EngineCore.sweepStatus(list, prevWeekHighLow[r8], false))) {
                        i3++;
                        i2 = 1;
                    } else {
                        i2 = i4;
                    }
                }
                return new Object[]{Integer.valueOf((!optString2.contains("pdh") ? !(!optString2.contains("pdl") ? !(!optString2.contains("pwh") ? !(!optString2.contains("pwl") ? i3 > 0 : !(prevWeekHighLow == null || !"SWEEP".equals(EngineCore.sweepStatus(list, prevWeekHighLow[1], false)))) : !(prevWeekHighLow == null || !"SWEEP".equals(EngineCore.sweepStatus(list, prevWeekHighLow[0], true)))) : !(prevDayHighLow2 == null || !"SWEEP".equals(EngineCore.sweepStatus(list, prevDayHighLow2[1], false)))) : !(prevDayHighLow2 == null || !"SWEEP".equals(EngineCore.sweepStatus(list, prevDayHighLow2[0], true)))) ? 0 : 1), Integer.valueOf(i2)};
            case 20:
                double ema2 = ema(list, jSONObject.optInt("f", 9));
                double ema3 = ema(list, jSONObject.optInt("s", 21));
                if (Double.isNaN(ema2) || Double.isNaN(ema3)) {
                    return new Object[]{0, 0};
                }
                boolean z7 = ema2 > ema3;
                return new Object[]{Integer.valueOf(optString2.equals("golden") == z7 ? 1 : 0), Integer.valueOf(z7 ? 1 : -1)};
            case 21:
                Iterator<EngineCore.ObZone> it = EngineCore.orderBlocks(list, 10).iterator();
                z = false;
                i6 = 0;
                while (it.hasNext()) {
                    EngineCore.ObZone next = it.next();
                    if (!next.mitigated && d >= next.bottom && d <= next.top) {
                        i6 = next.bullish ? 1 : -1;
                        z = true;
                        break;
                    }
                }
                return new Object[]{Integer.valueOf((!z || (!"any".equals(optString2) && ((!optString2.contains("bull") || i6 <= 0) && (!optString2.contains("bear") || i6 >= 0)))) ? 0 : 1), Integer.valueOf(i6)};
            default:
                return new Object[]{0, 0};
        }
    }

    private static boolean cmp(double d, String str, double d2) {
        str.hashCode();
        switch (str) {
            case "<":
                if (d >= d2) {
                    break;
                }
                break;
            case ">":
                if (d <= d2) {
                    break;
                }
                break;
            case "<=":
                if (d > d2) {
                    break;
                }
                break;
            case ">=":
                if (d < d2) {
                    break;
                }
                break;
            default:
                if (d >= d2) {
                    break;
                }
                break;
        }
        return false;
    }

    public static double ema(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i) {
            return Double.NaN;
        }
        double d = 2.0d / (i + 1);
        double d2 = list.get(0).c;
        for (int i2 = 1; i2 < list.size(); i2++) {
            d2 = (d2 * (1.0d - d)) + (list.get(i2).c * d);
        }
        return d2;
    }

    public static double sma(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d += list.get(size).c;
        }
        return d / i;
    }

    public static double rsi(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = list.get(size).c - list.get(size - 1).c;
            if (d3 > 0.0d) {
                d2 += d3;
            } else {
                d += -d3;
            }
        }
        if (d == 0.0d) {
            return 100.0d;
        }
        double d4 = i;
        return 100.0d - (100.0d / (((d2 / d4) / (d / d4)) + 1.0d));
    }

    public static double[] macd(List<EngineCore.Candle> list, int i, int i2, int i3) {
        if (list == null || list.size() < i2 + i3 + 5) {
            return null;
        }
        double d = 2.0d / (i + 1);
        double d2 = 2.0d / (i2 + 1);
        double d3 = 2.0d / (i3 + 1);
        int i4 = 0;
        double d4 = list.get(0).c;
        double d5 = list.get(0).c;
        ArrayList arrayList = new ArrayList();
        int i5 = 1;
        while (i5 < list.size()) {
            d4 = (list.get(i5).c * d) + ((1.0d - d) * d4);
            d5 = (d5 * (1.0d - d2)) + (list.get(i5).c * d2);
            arrayList.add(Double.valueOf(d4 - d5));
            i5++;
            d = d;
            i4 = 0;
        }
        double doubleValue = ((Double) arrayList.get(i4)).doubleValue();
        for (int i6 = 1; i6 < arrayList.size(); i6++) {
            doubleValue = (doubleValue * (1.0d - d3)) + (((Double) arrayList.get(i6)).doubleValue() * d3);
        }
        return new double[]{((Double) arrayList.get(arrayList.size() - 1)).doubleValue(), doubleValue};
    }

    public static double[] bollinger(List<EngineCore.Candle> list, int i, double d) {
        if (list == null || list.size() < i) {
            return null;
        }
        double sma = sma(list, i);
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d2 += Math.pow(list.get(size).c - sma, 2.0d);
        }
        double sqrt = d * Math.sqrt(d2 / i);
        return new double[]{sma + sqrt, sma - sqrt, sma};
    }

    public static double atr(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            int i2 = size - 1;
            d += Math.max(list.get(size).h - list.get(size).l, Math.max(Math.abs(list.get(size).h - list.get(i2).c), Math.abs(list.get(size).l - list.get(i2).c)));
        }
        return d / i;
    }

    public static int supertrendDir(List<EngineCore.Candle> list, int i, double d) {
        if (list == null || list.size() < i + 2) {
            return 0;
        }
        double atr = atr(list, i);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return 0;
        }
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            d2 += (list.get(size).h + list.get(size).l) / 2.0d;
        }
        return list.get(list.size() - 1).c > (d2 / ((double) i)) + 0.0d ? 1 : -1;
    }

    public static double stochK(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i) {
            return Double.NaN;
        }
        double d = -1.7976931348623157E308d;
        double d2 = Double.MAX_VALUE;
        for (int size = list.size() - i; size < list.size(); size++) {
            d = Math.max(d, list.get(size).h);
            d2 = Math.min(d2, list.get(size).l);
        }
        if (d == d2) {
            return 50.0d;
        }
        return ((list.get(list.size() - 1).c - d2) * 100.0d) / (d - d2);
    }

    public static double cci(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i) {
            return Double.NaN;
        }
        ArrayList arrayList = new ArrayList();
        double d = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d2 = ((list.get(size).h + list.get(size).l) + list.get(size).c) / 3.0d;
            arrayList.add(Double.valueOf(d2));
            d += d2;
        }
        double d3 = i;
        double d4 = d / d3;
        Iterator it = arrayList.iterator();
        double d5 = 0.0d;
        while (it.hasNext()) {
            d5 += Math.abs(((Double) it.next()).doubleValue() - d4);
        }
        double d6 = d5 / d3;
        double doubleValue = ((Double) arrayList.get(arrayList.size() - 1)).doubleValue();
        if (d6 == 0.0d) {
            return 0.0d;
        }
        return (doubleValue - d4) / (d6 * 0.015d);
    }

    public static double mfi(List<EngineCore.Candle> list, int i) {
        if (list == null || list.size() < i + 1) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int size = list.size() - i; size < list.size(); size++) {
            double d3 = ((list.get(size).h + list.get(size).l) + list.get(size).c) / 3.0d;
            int i2 = size - 1;
            double d4 = ((list.get(i2).h + list.get(i2).l) + list.get(i2).c) / 3.0d;
            double d5 = list.get(size).v * d3;
            if (d3 > d4) {
                d2 += d5;
            } else if (d3 < d4) {
                d += d5;
            }
        }
        if (d == 0.0d) {
            return 100.0d;
        }
        return 100.0d - (100.0d / ((d2 / d) + 1.0d));
    }

    public static double adx(List<EngineCore.Candle> list, int i) {
        double d = 0.0d;
        if (list == null) {
            return Double.NaN;
        }
        int i2 = i * 2;
        if (list.size() < i2 + 2) {
            return Double.NaN;
        }
        int size = list.size() - i2;
        double d2 = 0.0d;
        double d3 = 0.0d;
        double d4 = 0.0d;
        while (size < list.size()) {
            int i3 = size - 1;
            double d5 = list.get(size).h - list.get(i3).h;
            double d6 = list.get(i3).l - list.get(size).l;
            if (d5 > d6) {
                d = 0.0d;
                if (d5 > 0.0d) {
                    d3 += d5;
                }
            } else {
                d = 0.0d;
            }
            if (d6 > d5 && d6 > d) {
                d4 += d6;
            }
            d2 += Math.max(list.get(size).h - list.get(size).l, Math.max(Math.abs(list.get(size).h - list.get(i3).c), Math.abs(list.get(size).l - list.get(i3).c)));
            size++;
            d3 = d3;
        }
        if (d2 == 0.0d) {
            return 0.0d;
        }
        double d7 = (d3 * 100.0d) / d2;
        double d8 = (d4 * 100.0d) / d2;
        double d9 = d7 + d8;
        if (d9 == 0.0d) {
            return 0.0d;
        }
        return (Math.abs(d7 - d8) * 100.0d) / d9;
    }

    private static boolean engulf(List<EngineCore.Candle> list, int i) {
        if (list.size() < 2) {
            return false;
        }
        EngineCore.Candle candle = list.get(list.size() - 2);
        EngineCore.Candle candle2 = list.get(list.size() - 1);
        return i == 1 ? candle.c < candle.o && candle2.c > candle2.o && candle2.c >= candle.o && candle2.o <= candle.c : candle.c > candle.o && candle2.c < candle2.o && candle2.o >= candle.c && candle2.c <= candle.o;
    }

    public JSONObject listStrategies() {
        boolean z = false;
        JSONObject jSONObject = new JSONObject();
        int i = 0;
        try {
            JSONArray jSONArray = new JSONArray();
            String[][] strArr = EngineCore.STRATEGY_META;
            int[] iArr = this.engine.lastVotes;
            int i2 = 0;
            while (i2 < strArr.length) {
                try {
                    jSONArray.put(new JSONObject().put("name", strArr[i2][0]).put("group", strArr[i2][1]).put("vote", i2 < iArr.length ? iArr[i2] : 0));
                    i2++;
                } catch (Exception e) {
                    e = e;
                    z = false;
                    try {
                        jSONObject.put("ok", z).put("error", String.valueOf(e));
                    } catch (Exception unused) {
                    }
                    return jSONObject;
                }
            }
            jSONObject.put("builtin", jSONArray);
            jSONObject.put("masterNote", "3C MASTER: C1+C2 body>=70%, C3 protected, 5-candle breakout window, SL opposite extreme, BE @+1R, TP @+3R — daily P/L UNLIMITED");
            JSONArray jSONArray2 = new JSONArray();
            purgeTrash();
            Cursor rawQuery = this.db.getReadableDatabase().rawQuery("SELECT id, name, source, video, spec, status, stats, created_at, updated_at FROM strategies WHERE deleted_at=0 ORDER BY id DESC", null);
            while (rawQuery.moveToNext()) {
                JSONObject jSONObject2 = new JSONObject();
                jSONObject2.put("id", rawQuery.getLong(i)).put("name", rawQuery.getString(1)).put("source", rawQuery.getString(2));
                try {
                    jSONObject2.put("video", new JSONObject(rawQuery.getString(3)));
                } catch (Exception unused2) {
                    jSONObject2.put("video", new JSONObject());
                }
                try {
                    JSONObject jSONObject3 = new JSONObject(rawQuery.getString(4));
                    jSONObject2.put("notes", jSONObject3.optString("notes"));
                    JSONArray optJSONArray = jSONObject3.optJSONArray("conditions");
                    StringBuilder sb = new StringBuilder();
                    if (optJSONArray != null) {
                        for (int i3 = i; i3 < optJSONArray.length(); i3++) {
                            JSONObject optJSONObject = optJSONArray.optJSONObject(i3);
                            if (optJSONObject != null) {
                                if (sb.length() > 0) {
                                    sb.append(" + ");
                                }
                                sb.append(humanCond(optJSONObject));
                            }
                        }
                    }
                    jSONObject2.put("rules", sb.toString());
                } catch (Exception unused3) {
                    jSONObject2.put("rules", "");
                }
                jSONObject2.put("status", rawQuery.getString(5));
                try {
                    jSONObject2.put("stats", new JSONObject(rawQuery.getString(6)));
                } catch (Exception unused4) {
                    jSONObject2.put("stats", new JSONObject());
                }
                jSONObject2.put("created_at", rawQuery.getLong(7)).put("updated_at", rawQuery.getLong(8));
                jSONArray2.put(jSONObject2);
                i = 0;
            }
            rawQuery.close();
            jSONObject.put("custom", jSONArray2);
            Cursor rawQuery2 = this.db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM strategies WHERE deleted_at>0", null);
            jSONObject.put("trashCount", rawQuery2.moveToFirst() ? rawQuery2.getInt(0) : 0);
            rawQuery2.close();
            jSONObject.put("ytChannel", new JSONObject().put("id", this.db.setting("yt_channel_id", "")).put("name", this.db.setting("yt_channel_name", "")));
            jSONObject.put("lastVoteSym", this.engine.lastVoteSym);
            jSONObject.put("symbol", this.db.setting("lab_symbol", "XAUUSD"));
            jSONObject.put("ok", true);
        } catch (Exception e2) {
            try {
                jSONObject.put("ok", false).put("error", String.valueOf(e2));
            } catch (Throwable ignored) { }
            return jSONObject;
        }
        return jSONObject;
    }

    private static String humanCond(JSONObject jSONObject) {
        String optString = null;
        String optString2 = null;
        optString = jSONObject.optString("ind");
        optString2 = jSONObject.optString("op");
        optString.hashCode();
        switch (optString) {
            case "supertrend":
                return "Supertrend " + optString2;
            case "price_vs_ema":
                return "Price " + optString2 + " EMA(" + jSONObject.optInt("p", 50) + ")";
            case "candle":
                return "Candle: " + optString2.replace("_", " ");
            case "change":
                return "Change(" + jSONObject.optInt("n", 5) + "bar) " + optString2 + " " + jSONObject.optDouble("v", 0.0d) + "%";
            case "volume":
                return "Volume " + optString2 + " " + jSONObject.optDouble("v", 1.5d) + "x avg";
            case "bb":
                return "Bollinger " + optString2.replace("_", " ");
            case "adx":
                return "ADX " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "atr":
                return "ATR% " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "cci":
                return "CCI " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "mfi":
                return "MFI " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "rsi":
                return "RSI(" + jSONObject.optInt("p", 14) + ") " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "sma":
                return "SMA(" + jSONObject.optInt("p", 20) + ") " + optString2.replace("_", " ");
            case "macd":
                return "MACD " + optString2;
            case "stoch":
                return "Stoch " + optString2 + " " + jSONObject.optDouble("v", 0.0d);
            case "ema_cross":
                return "EMA(" + jSONObject.optInt("f", 9) + "/" + jSONObject.optInt("s", 21) + ") " + optString2;
            default:
                return optString + " " + optString2;
        }
    }
}
