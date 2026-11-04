package com.aitradinglab.engine;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/* loaded from: classes.dex */
public class BootReceiver extends BroadcastReceiver {
    @Override // android.content.BroadcastReceiver
    public void onReceive(Context context, Intent intent) {
        if ("android.intent.action.BOOT_COMPLETED".equals(intent.getAction())) {
            try {
                context.startForegroundService(new Intent(context, (Class<?>) ServerService.class));
            } catch (Exception unused) {
            }
        }
    }
}
