import com.aitradinglab.engine.Api;
import com.aitradinglab.engine.Db;
import com.aitradinglab.engine.EngineCore;
import com.aitradinglab.engine.HttpServer;

/**
 * HOST OBSERVATION RUNNER (default package) — engine ko PC ke JVM par chalata hai.
 * Usage: java HostMain <seconds> <dbDir> <port>
 * DB persistent hota hai — restart par balances/trades/candles as-it-is resume.
 */
public class HostMain {
    public static void main(String[] args) throws Exception {
        int seconds = args.length > 0 ? Integer.parseInt(args[0]) : 540;
        String dbDir = args.length > 1 ? args[1] : "/tmp/atl-host";
        int port = args.length > 2 ? Integer.parseInt(args[2]) : 8788;
        java.io.File dir = new java.io.File(dbDir);
        if (!dir.exists()) dir.mkdirs();

        // dashboard.html repo assets se load (Api ctor isay padhta hai)
        String repoRoot = System.getProperty("atl.repo", ".");
        android.content.res.AssetManager.setAssetsRoot(repoRoot + "/android-app/app/src/main/assets");

        android.content.Context ctx = new android.content.Context();
        ctx.setDbRoot(dir);
        Db db = new Db(ctx);
        // $100 observation seed — fresh DB par owner + trader (dono trade_ok) banao
        android.database.Cursor uc = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
        int users = uc.moveToFirst() ? uc.getInt(0) : 0;
        uc.close();
        if (users == 0) {
            long now = System.currentTimeMillis();
            db.getWritableDatabase().execSQL(
                "INSERT INTO users(email, name, pw_hash, role, totp_secret, totp_enabled, active, approved, trade_ok, created_at) VALUES(?,?,?,?,?,0,1,1,1,?)",
                new Object[]{"owner@atl.local", "Owner", com.aitradinglab.engine.Auth.hashPw("paper123"), "ADMIN", "", now});
            db.getWritableDatabase().execSQL(
                "INSERT INTO users(email, name, pw_hash, role, totp_secret, totp_enabled, active, approved, trade_ok, created_at) VALUES(?,?,?,?,?,0,1,1,1,?)",
                new Object[]{"trader@atl.local", "Trader", com.aitradinglab.engine.Auth.hashPw("paper123"), "TRADER", "", now});
            // register flow parity (Api.java:256) — $100 account rows
            db.getWritableDatabase().execSQL("INSERT OR IGNORE INTO accounts(user_id, balance, start_balance, peak, day_start, day_ts) SELECT id, 100, 100, 100, 100, ? FROM users", new Object[]{now / 86400000L});
            System.out.println("[HostMain] seeded owner + trader + $100 accounts (trade_ok=1)");
        }
        EngineCore engine = new EngineCore(db);
        HttpServer server = new HttpServer(new Api(ctx, db, engine));
        server.start();
        Thread t = new Thread(engine, "engine-core");
        t.setDaemon(true);
        t.start();
        String dbPath = dir.getAbsolutePath() + "/atl-engine.db";
        System.out.println("[HostMain] ENGINE ONLINE v1.0 — db=" + dbPath + " port=" + HttpServer.PORT + " run=" + seconds + "s");

        long end = System.currentTimeMillis() + seconds * 1000L;
        long lastBeat = 0;
        while (System.currentTimeMillis() < end) {
            Thread.sleep(1000);
            if (!t.isAlive()) { System.out.println("[HostMain] engine thread DIED — abort"); break; }
            long now = System.currentTimeMillis();
            if (now - lastBeat >= 60_000) {
                lastBeat = now;
                System.out.println("[HostMain] alive — " + (end - now) / 1000 + "s left");
            }
        }
        System.out.println("[HostMain] time up — graceful stop");
        try { engine.stop(); } catch (Throwable ignored) { }
        Thread.sleep(1500);
        try { db.close(); } catch (Throwable ignored) { }
        System.exit(0);
    }
}
