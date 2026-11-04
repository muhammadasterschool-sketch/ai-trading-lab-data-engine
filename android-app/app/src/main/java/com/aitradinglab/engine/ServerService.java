package com.aitradinglab.engine;

import android.R;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.database.Cursor;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.SystemClock;
import android.util.Log;
import java.io.File;
import java.io.FileInputStream;
import java.lang.Thread;

/* loaded from: classes.dex */
public class ServerService extends Service {
    public static final String CHANNEL_ID = "atl-engine";
    public static final int NOTIF_ID = 501;
    private static ServerService instance;
    private Db db;
    private EngineCore engine;
    private Thread engineThread;
    private HttpServer server;
    private PowerManager.WakeLock wakeLock;

    @Override // android.app.Service
    public IBinder onBind(Intent intent) {
        return null;
    }

    public static boolean isRunning() {
        ServerService serverService = instance;
        return (serverService == null || serverService.server == null) ? false : true;
    }

    @Override // android.app.Service
    public void onCreate() {
        super.onCreate();
        instance = this;
        EngineCore.appContext(this);
        try {
            try {
                startForegroundInternal();
            } catch (Throwable unused) {
                startForegroundInternal();
            }
        } catch (Throwable unused2) {
        }
        try {
            installCrashLogger();
        } catch (Throwable unused3) {
        }
        try {
            this.db = new Db(this);
            repairDbIfBroken();
            feedCrashFileIntoLedger();
            this.engine = new EngineCore(this.db);
        } catch (Throwable th) {
            try {
                this.db.log("ERROR", "SYSTEM", "DB_ENGINE_INIT_FAIL", String.valueOf(th));
            } catch (Throwable unused4) {
            }
        }
        try {
            HttpServer httpServer = new HttpServer(new Api(this, this.db, this.engine));
            this.server = httpServer;
            httpServer.start();
            Thread thread = new Thread(this.engine, "engine-core");
            this.engineThread = thread;
            thread.start();
            this.db.log("INFO", "SYSTEM", "SERVICE_START", "phone server online on port 8788");
            this.db.log("INFO", "SYSTEM", "ENGINE_VERSION", "v1.0 verified stable — full bug audit: login UI fix, session persistence, news pause word-matching, table pruning, rvi guard, 40% consensus, closed-candle execution");
        } catch (Throwable th2) {
            try {
                this.db.log("ERROR", "SYSTEM", "SERVICE_START_FAIL", String.valueOf(th2));
            } catch (Throwable unused5) {
            }
        }
        try {
            PowerManager.WakeLock newWakeLock = ((PowerManager) getSystemService("power")).newWakeLock(1, "atl:engine");
            this.wakeLock = newWakeLock;
            newWakeLock.setReferenceCounted(false);
            this.wakeLock.acquire();
        } catch (Throwable unused6) {
        }
        startWatchdog();
        try {
            WatchdogReceiver.schedule(this);
        } catch (Throwable unused7) {
        }
    }

    private void startWatchdog() {
        Thread thread = new Thread(new Runnable() { // from class: com.aitradinglab.engine.ServerService$$ExternalSyntheticLambda0
            @Override // java.lang.Runnable
            public final void run() {
                ServerService.this.lambda$startWatchdog$0();
            }
        }, "engine-watchdog");
        thread.setDaemon(true);
        thread.start();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$startWatchdog$0() {
        while (true) {
            try {
                Thread.sleep(30000L);
                try {
                    Thread thread = this.engineThread;
                    if (thread == null || !thread.isAlive()) {
                        try {
                            this.db.log("WARN", "SYSTEM", "ENGINE_REVIVED", "engine thread was dead — 24/7 watchdog restarted it");
                        } catch (Throwable unused) {
                        }
                        EngineCore engineCore = this.engine;
                        if (engineCore == null) {
                            this.engine = new EngineCore(this.db);
                        } else {
                            engineCore.stop();
                        }
                        this.engine = new EngineCore(this.db);
                        Thread thread2 = new Thread(this.engine, "engine-core");
                        this.engineThread = thread2;
                        thread2.start();
                    }
                } catch (Throwable unused2) {
                }
            } catch (InterruptedException unused3) {
                return;
            }
        }
    }

    @Override // android.app.Service
    public void onTaskRemoved(Intent intent) {
        try {
            AlarmManager alarmManager = (AlarmManager) getSystemService("alarm");
            PendingIntent service = PendingIntent.getService(this, 2001, new Intent(this, (Class<?>) ServerService.class), 1140850688);
            if (alarmManager != null) {
                alarmManager.setExactAndAllowWhileIdle(2, SystemClock.elapsedRealtime() + 2000, service);
            }
        } catch (Throwable unused) {
        }
        try {
            WatchdogReceiver.schedule(this);
        } catch (Throwable unused2) {
        }
        try {
            Intent intent2 = new Intent(this, (Class<?>) ServerService.class);
            if (Build.VERSION.SDK_INT >= 26) {
                startForegroundService(intent2);
            } else {
                startService(intent2);
            }
        } catch (Throwable unused3) {
        }
        super.onTaskRemoved(intent);
    }

    private void repairDbIfBroken() {
        String[] strArr = {"SELECT COUNT(*) FROM users", "SELECT COUNT(*) FROM sessions", "SELECT COUNT(*) FROM invites", "SELECT COUNT(*) FROM instruments", "SELECT COUNT(*) FROM accounts", "SELECT COUNT(*) FROM trades", "SELECT COUNT(*) FROM logs", "SELECT COUNT(*) FROM settings"};
        for (int i = 0; i < 8; i++) {
            try {
                Cursor rawQuery = this.db.getReadableDatabase().rawQuery(strArr[i], null);
                if (rawQuery.moveToFirst()) {
                    rawQuery.getInt(0);
                }
                rawQuery.close();
            } catch (Throwable th) {
                Log.e("ATL.DB", "probe failed — rebuilding: " + th);
                try {
                    this.db.close();
                } catch (Throwable unused) {
                }
                String absolutePath = getDatabasePath("atl-engine.db").getAbsolutePath();
                String[] strArr2 = {absolutePath, absolutePath + "-wal", absolutePath + "-shm"};
                for (int i2 = 0; i2 < 3; i2++) {
                    try {
                        new File(strArr2[i2]).delete();
                    } catch (Throwable unused2) {
                    }
                }
                try {
                    Db db = new Db(this);
                    this.db = db;
                    Cursor rawQuery2 = db.getReadableDatabase().rawQuery("SELECT COUNT(*) FROM users", null);
                    if (rawQuery2.moveToFirst()) {
                        rawQuery2.getInt(0);
                    }
                    rawQuery2.close();
                    this.db.log("WARN", "SYSTEM", "DB_REBUILT", "database was corrupted — fresh schema created, re-register with invite code or use password reset");
                    return;
                } catch (Throwable th2) {
                    Log.e("ATL.DB", "rebuild failed: " + th2);
                    return;
                }
            }
        }
    }

    private void feedCrashFileIntoLedger() {
        try {
            File file = new File(getFilesDir(), "last-crash.txt");
            if (!file.exists() || file.length() <= 0) {
                return;
            }
            byte[] bArr = new byte[(int) Math.min(file.length(), 4000L)];
            FileInputStream fileInputStream = new FileInputStream(file);
            int read = fileInputStream.read(bArr);
            fileInputStream.close();
            this.db.getWritableDatabase().execSQL("INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)", new Object[]{Long.valueOf(System.currentTimeMillis()), "ERROR", "CRASH", "previous run", new String(bArr, 0, Math.max(0, read))});
            file.delete();
        } catch (Throwable unused) {
        }
    }

    private void installCrashLogger() {
        final Thread.UncaughtExceptionHandler defaultUncaughtExceptionHandler = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() { // from class: com.aitradinglab.engine.ServerService$$ExternalSyntheticLambda1
            @Override // java.lang.Thread.UncaughtExceptionHandler
            public final void uncaughtException(Thread thread, Throwable th) {
                ServerService.this.lambda$installCrashLogger$1(defaultUncaughtExceptionHandler, thread, th);
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$installCrashLogger$1(Thread.UncaughtExceptionHandler uncaughtExceptionHandler, Thread thread, Throwable th) {
        try {
            this.db.getWritableDatabase().execSQL("INSERT INTO logs(ts, level, component, event, details) VALUES(?,?,?,?,?)", new Object[]{Long.valueOf(System.currentTimeMillis()), "ERROR", "CRASH", "thread=" + thread.getName(), Log.getStackTraceString(th).substring(0, Math.min(1800, Log.getStackTraceString(th).length()))});
        } catch (Exception unused) {
        }
        if (uncaughtExceptionHandler != null) {
            uncaughtExceptionHandler.uncaughtException(thread, th);
        }
    }

    private void startForegroundInternal() {
        Notification.Builder builder = null;
        NotificationManager notificationManager = (NotificationManager) getSystemService("notification");
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel notificationChannel = new NotificationChannel(CHANNEL_ID, "Trading Engine", 2);
            notificationChannel.setDescription("AI Trading Lab paper trading engine");
            notificationManager.createNotificationChannel(notificationChannel);
        }
        if (Build.VERSION.SDK_INT >= 26) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        builder.setContentTitle("AI Trading Lab").setContentText("Paper trading engine running — tap to open dashboard").setSmallIcon(R.drawable.stat_sys_download_done).setOngoing(true);
        if (Build.VERSION.SDK_INT >= 29) {
            builder.setCategory("service");
        }
        if (Build.VERSION.SDK_INT >= 30) {
            try {
                Notification.Builder.class.getMethod("setForegroundServiceBehavior", Integer.TYPE).invoke(builder, 1);
            } catch (Exception unused) {
            }
        }
        Notification build = builder.build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIF_ID, build, 1073741824);
        } else {
            startForeground(NOTIF_ID, build);
        }
    }

    @Override // android.app.Service
    public void onTimeout(int i) {
        try {
            this.db.log("WARN", "SYSTEM", "FGS_TIMEOUT", "foreground service type " + i + " timed out — stopping cleanly, engine will restart via START_STICKY");
        } catch (Exception unused) {
        }
        stopForeground(1);
        stopSelf();
    }

    @Override // android.app.Service
    public int onStartCommand(Intent intent, int i, int i2) {
        try {
            WatchdogReceiver.schedule(this);
            return 1;
        } catch (Throwable unused) {
            return 1;
        }
    }

    @Override // android.app.Service
    public void onDestroy() {
        EngineCore engineCore = this.engine;
        if (engineCore != null) {
            engineCore.stop();
        }
        HttpServer httpServer = this.server;
        if (httpServer != null) {
            httpServer.stop();
        }
        PowerManager.WakeLock wakeLock = this.wakeLock;
        if (wakeLock != null && wakeLock.isHeld()) {
            this.wakeLock.release();
        }
        instance = null;
        super.onDestroy();
    }
}
