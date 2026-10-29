package com.aitradinglab.engine;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/**
 * v1.3 — 24/7 PROCESS WATCHDOG (periodic).
 *
 * Why: START_STICKY + the in-process 30s engine-thread watchdog are not enough.
 * When an OEM battery manager (One UI, etc.) kills the whole PROCESS, the sticky
 * restart can be postponed for hours inside Doze — and the in-process watchdog
 * dies with the process. This receiver chains a setExactAndAllowWhileIdle alarm
 * every 9 minutes (fires EVEN IN DOZE): if the foreground service is not running,
 * startForegroundService() revives it immediately. The onTaskRemoved 2s kick and
 * the boot receiver cover swipe-kill and reboot; this covers everything else.
 */
public class WatchdogReceiver extends BroadcastReceiver {
    public static final int REQUEST_CODE = 4242;
    /** 9 min — inside the 10-min Doze idle window, cheap on battery. */
    public static final long INTERVAL_MS = 9L * 60_000;

    public static PendingIntent pendingIntent(Context ctx) {
        Intent i = new Intent(ctx, WatchdogReceiver.class);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) flags |= PendingIntent.FLAG_IMMUTABLE;
        return PendingIntent.getBroadcast(ctx, REQUEST_CODE, i, flags);
    }

    /** Arms the next periodic check. Call from Service.onCreate / onStartCommand / onTaskRemoved. */
    public static void schedule(Context ctx) {
        try {
            AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            long at = System.currentTimeMillis() + INTERVAL_MS;
            if (Build.VERSION.SDK_INT >= 23) {
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pendingIntent(ctx));
            } else {
                am.setExact(AlarmManager.RTC_WAKEUP, at, pendingIntent(ctx));
            }
        } catch (Throwable ignored) { }
    }

    @Override public void onReceive(Context ctx, Intent intent) {
        // chain the next alarm FIRST — even if everything below fails, the beat continues
        schedule(ctx);
        // revive the service if the process was killed
        try {
            if (!ServerService.isRunning()) {
                if (Build.VERSION.SDK_INT >= 26) {
                    ctx.startForegroundService(new Intent(ctx, ServerService.class));
                } else {
                    ctx.startService(new Intent(ctx, ServerService.class));
                }
            }
        } catch (Throwable ignored) { }
    }
}
