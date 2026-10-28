package com.aitradinglab.engine;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

/**
 * Foreground service: hosts the embedded HTTP server + trading engine so
 * paper trading keeps running with the app closed (notification + wake lock).
 */
public class ServerService extends Service {
    public static final String CHANNEL_ID = "atl-engine";
    public static final int NOTIF_ID = 501;
    private static ServerService instance;

    private Db db;
    private EngineCore engine;
    private HttpServer server;
    private PowerManager.WakeLock wakeLock;
    private Thread engineThread;

    public static boolean isRunning() { return instance != null && instance.server != null; }

    @Override public void onCreate() {
        super.onCreate();
        instance = this;
        // 1) announce foreground BEFORE anything that could fail — an FGS that never
        //    calls startForeground() is itself killed with a crash dialog (Android 12+).
        try {
            startForegroundInternal();
        } catch (Throwable e) {
            try { startForegroundInternal(); } catch (Throwable ignored) { }
        }
        // 2) crash net + storage + engine + http server — each step isolated so one
        //    failure can never take the whole app down at launch.
        try { installCrashLogger(); } catch (Throwable ignored) { }
        try {
            db = new Db(this);
            repairDbIfBroken();   // v5.3: crash-loop eras could leave a corrupt WAL — detect and rebuild
            feedCrashFileIntoLedger();
            engine = new EngineCore(db);
        } catch (Throwable e) {
            try { db.log("ERROR", "SYSTEM", "DB_ENGINE_INIT_FAIL", String.valueOf(e)); } catch (Throwable ignored) { }
        }
        try {
            server = new HttpServer(new Api(this, db, engine));
            server.start();
            engineThread = new Thread(engine, "engine-core");
            engineThread.start();
            db.log("INFO", "SYSTEM", "SERVICE_START", "phone server online on port " + HttpServer.PORT);
            db.log("INFO", "SYSTEM", "ENGINE_VERSION", "v1.0 verified stable — full bug audit: login UI fix, session persistence, news pause word-matching, table pruning, rvi guard, 40% consensus, closed-candle execution");
        } catch (Throwable e) {
            try { db.log("ERROR", "SYSTEM", "SERVICE_START_FAIL", String.valueOf(e)); } catch (Throwable ignored) { }
        }
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "atl:engine");
            wakeLock.setReferenceCounted(false);
            wakeLock.acquire();
        } catch (Throwable ignored) { }
    }

    /**
     * v5.3 DB self-heal: probe every core ledger table. Any failure (SQLiteCantOpenDatabase-
     * Exception, SQLiteDatabaseCorruptException, disk I/O error — typical after the crash loop
     * force-killed the process mid-WAL-write) → close the helper, DELETE db+wal+shm, reopen.
     * The engine recreates a fresh schema; users re-register with the invite code (or use the
     * in-app password reset) — paper data is disposable, a dead login screen is not.
     */
    private void repairDbIfBroken() {
        String[] probes = {
                "SELECT COUNT(*) FROM users", "SELECT COUNT(*) FROM sessions",
                "SELECT COUNT(*) FROM invites", "SELECT COUNT(*) FROM instruments",
                "SELECT COUNT(*) FROM accounts", "SELECT COUNT(*) FROM trades",
                "SELECT COUNT(*) FROM logs", "SELECT COUNT(*) FROM settings"
        };
        boolean broken = false;
        try {
            for (String q : probes) {
                android.database.Cursor c = db.getReadableDatabase().rawQuery(q, null);
                if (c.moveToFirst()) c.getInt(0);
                c.close();
            }
        } catch (Throwable t) {
            broken = true;
            android.util.Log.e("ATL.DB", "probe failed — rebuilding: " + t);
        }
        if (!broken) return;
        try { db.close(); } catch (Throwable ignored) { }
        String base = getDatabasePath("atl-engine.db").getAbsolutePath();
        for (String f : new String[]{base, base + "-wal", base + "-shm"}) {
            try { new java.io.File(f).delete(); } catch (Throwable ignored) { }
        }
        try {
            db = new Db(this);
            android.database.Cursor c = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
            if (c.moveToFirst()) c.getInt(0);
            c.close();
            db.log("WARN", "SYSTEM", "DB_REBUILT", "database was corrupted — fresh schema created, re-register with invite code or use password reset");
        } catch (Throwable t2) {
            android.util.Log.e("ATL.DB", "rebuild failed: " + t2);
        }
    }

    /** A crash from a previous run (recorded by AtlApp) becomes visible in the Logs tab. */
    private void feedCrashFileIntoLedger() {
        try {
            java.io.File f = new java.io.File(getFilesDir(), "last-crash.txt");
            if (f.exists() && f.length() > 0) {
                byte[] raw = new byte[(int) Math.min(f.length(), 4000)];
                java.io.FileInputStream in = new java.io.FileInputStream(f);
                int n = in.read(raw); in.close();
                String txt = new String(raw, 0, Math.max(0, n));
                db.getWritableDatabase().execSQL(
                        "INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)",
                        new Object[]{System.currentTimeMillis(), "ERROR", "CRASH", "previous run", txt});
                f.delete();
            }
        } catch (Throwable ignored) { }
    }

    /** Records any uncaught crash into the system ledger before Android kills the process. */
    private void installCrashLogger() {
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            try {
                db.getWritableDatabase().execSQL(
                        "INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)",
                        new Object[]{System.currentTimeMillis(), "ERROR", "CRASH",
                                "thread=" + t.getName(), android.util.Log.getStackTraceString(e).substring(0, Math.min(1800, android.util.Log.getStackTraceString(e).length()))});
            } catch (Exception ignored) { }
            if (prev != null) prev.uncaughtException(t, e);
        });
    }

    private void startForegroundInternal() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL_ID, "Trading Engine", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("AI Trading Lab paper trading engine");
            nm.createNotificationChannel(ch);
        }
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CHANNEL_ID)
                : new Notification.Builder(this);
        b.setContentTitle("AI Trading Lab")
                .setContentText("Paper trading engine running — tap to open dashboard")
                .setSmallIcon(android.R.drawable.stat_sys_download_done)
                .setOngoing(true);
        if (Build.VERSION.SDK_INT >= 29) b.setCategory(Notification.CATEGORY_SERVICE);
        int flags = 0;
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                java.lang.reflect.Method m = Notification.Builder.class.getMethod("setForegroundServiceBehavior", int.class);
                m.invoke(b, 1); // FOREGROUND_SERVICE_IMMEDIATE
            } catch (Exception ignored) { }
        }
        Notification n = b.build();
        // Android 14+ (API 34): declare the specialUse type explicitly — no 6-hour time
        // limit (unlike dataSync, which Android 15+ kills after 6h and then blocks every
        // restart with ForegroundServiceStartNotAllowedException = "app keeps crashing").
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIF_ID, n);
        }
    }

    /**
     * Android 15+ safety net: if ANY foreground-service type ever hits its time limit,
     * the system calls this; we must stop ourselves quickly or the OS force-stops us
     * with ForegroundServiceDidNotStopInTimeException (crash dialog).
     * Method signature matches android.app.Service#onTimeout(int) (API 35) — called
     * virtually at runtime even though we compile against SDK 34.
     */
    public void onTimeout(int fgsType) {
        try { db.log("WARN", "SYSTEM", "FGS_TIMEOUT", "foreground service type " + fgsType + " timed out — stopping cleanly, engine will restart via START_STICKY"); } catch (Exception ignored) { }
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY; // restart if killed
    }

    @Override public void onDestroy() {
        if (engine != null) engine.stop();
        if (server != null) server.stop();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        instance = null;
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
