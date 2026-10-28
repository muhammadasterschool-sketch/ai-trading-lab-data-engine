package com.aitradinglab.engine;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Auto-starts the engine after phone reboot so paper trading never stops. */
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            try {
                context.startForegroundService(new Intent(context, ServerService.class));
            } catch (Exception ignored) { }
        }
    }
}
