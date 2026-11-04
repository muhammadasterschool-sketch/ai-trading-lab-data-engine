package com.aitradinglab.engine;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;

/* loaded from: classes.dex */
public class WatchdogReceiver extends BroadcastReceiver {
    public static final long INTERVAL_MS = 540000;
    public static final int REQUEST_CODE = 4242;

    public static PendingIntent pendingIntent(Context context) {
        return PendingIntent.getBroadcast(context, REQUEST_CODE, new Intent(context, (Class<?>) WatchdogReceiver.class), 201326592);
    }

    public static void schedule(Context context) {
        try {
            AlarmManager alarmManager = (AlarmManager) context.getSystemService("alarm");
            if (alarmManager == null) {
                return;
            }
            alarmManager.setExactAndAllowWhileIdle(0, System.currentTimeMillis() + INTERVAL_MS, pendingIntent(context));
        } catch (Throwable unused) {
        }
    }

    @Override // android.content.BroadcastReceiver
    public void onReceive(Context context, Intent intent) {
        schedule(context);
        try {
            if (!ServerService.isRunning()) {
                if (Build.VERSION.SDK_INT >= 26) {
                    context.startForegroundService(new Intent(context, (Class<?>) ServerService.class));
                } else {
                    context.startService(new Intent(context, (Class<?>) ServerService.class));
                }
            }
        } catch (Throwable unused) {
        }
    }
}
