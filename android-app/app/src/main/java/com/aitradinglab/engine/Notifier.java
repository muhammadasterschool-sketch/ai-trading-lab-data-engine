package com.aitradinglab.engine;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.os.Build;

/**
 * v1.9 — instant admin alerts on the phone: every new registration (any invitation
 * code) fires a high-importance status-bar notification to the owner BEFORE the new
 * user can even log in (PENDING until approved). Best-effort: never breaks the API.
 */
public class Notifier {
    private static final String CHANNEL = "atl_alerts";
    private static long seq = System.currentTimeMillis();

    /** Fired by Api.register() right after a new account is created. */
    public static void registration(Context ctx, String name, String email, String role, String invite, boolean owner) {
        if (owner) {
            post(ctx, "Owner account created — " + name,
                    name + " (" + email + ") · role ADMIN (auto-approved) · ye aapka owner account hai");
        } else {
            post(ctx, "🔔 New registration — APPROVE karein: " + name,
                    name + " (" + email + ") invite code " + invite
                            + " se register hua · role TRADER · abhi PENDING — Settings > Control > Users me APPROVE dabayen, tabhi login kar sakta hai");
        }
    }

    /** Generic high-importance alert. Safe to call from any thread; never throws. */
    public static synchronized void post(Context ctx, String title, String text) {
        try {
            NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm == null) return;
            if (Build.VERSION.SDK_INT >= 26) {
                NotificationChannel ch = nm.getNotificationChannel(CHANNEL);
                if (ch == null) {
                    ch = new NotificationChannel(CHANNEL, "Admin alerts", NotificationManager.IMPORTANCE_HIGH);
                    ch.setDescription("Instant alerts: new registrations and engine events");
                    nm.createNotificationChannel(ch);
                }
            }
            Notification.Builder b = Build.VERSION.SDK_INT >= 26
                    ? new Notification.Builder(ctx, CHANNEL)
                    : new Notification.Builder(ctx);
            b.setContentTitle(title)
                    .setContentText(text)
                    .setStyle(new Notification.BigTextStyle().bigText(text))
                    .setSmallIcon(android.R.drawable.stat_notify_chat)
                    .setAutoCancel(true)
                    .setWhen(System.currentTimeMillis());
            if (Build.VERSION.SDK_INT < 26) b.setPriority(Notification.PRIORITY_HIGH);
            nm.notify((int) (seq++ & 0x7fffffffL), b.build());
        } catch (Throwable ignored) {
            // alerts are best-effort; registration must succeed regardless
        }
    }
}
