package com.aitradinglab.engine;

import android.R;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.os.Build;

/* loaded from: classes.dex */
public class Notifier {
    private static final String CHANNEL = "atl_alerts";
    private static long seq = System.currentTimeMillis();

    public static void registration(Context context, String str, String str2, String str3, String str4, boolean z) {
        if (z) {
            post(context, "Owner account created — " + str, str + " (" + str2 + ") · role ADMIN (auto-approved) · ye aapka owner account hai");
        } else {
            post(context, "🔔 New registration — APPROVE karein: " + str, str + " (" + str2 + ") invite code " + str4 + " se register hua · role TRADER · abhi PENDING — Settings > Control > Users me APPROVE dabayen, tabhi login kar sakta hai");
        }
    }

    public static synchronized void post(Context context, String str, String str2) {
        NotificationManager notificationManager = null;
        Notification.Builder builder = null;
        synchronized (Notifier.class) {
            try {
                notificationManager = (NotificationManager) context.getSystemService("notification");
            } catch (Throwable unused) {
            }
            if (notificationManager == null) {
                return;
            }
            if (Build.VERSION.SDK_INT >= 26 && notificationManager.getNotificationChannel(CHANNEL) == null) {
                NotificationChannel notificationChannel = new NotificationChannel(CHANNEL, "Admin alerts", 4);
                notificationChannel.setDescription("Instant alerts: new registrations and engine events");
                notificationManager.createNotificationChannel(notificationChannel);
            }
            if (Build.VERSION.SDK_INT >= 26) {
                builder = new Notification.Builder(context, CHANNEL);
            } else {
                builder = new Notification.Builder(context);
            }
            builder.setContentTitle(str).setContentText(str2).setStyle(new Notification.BigTextStyle().bigText(str2)).setSmallIcon(R.drawable.stat_notify_chat).setAutoCancel(true).setWhen(System.currentTimeMillis());
            if (Build.VERSION.SDK_INT < 26) {
                builder.setPriority(1);
            }
            long j = seq;
            seq = 1 + j;
            notificationManager.notify((int) (j & 2147483647L), builder.build());
        }
    }
}
