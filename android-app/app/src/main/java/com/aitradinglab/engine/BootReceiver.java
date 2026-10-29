package com.aitradinglab.engine;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Auto-starts the engine after phone reboot so paper trading never stops. */
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            try {
                // v3.0.2 lint fix: startForegroundService is API 26+; minSdk is 24.
                // Same guard pattern as WatchdogReceiver / ServerService.onTaskRemoved.
                if (android.os.Build.VERSION.SDK_INT >= 26) {
                    context.startForegroundService(new Intent(context, ServerService.class));
                } else {
                    context.startService(new Intent(context, ServerService.class));
                }
            } catch (Exception ignored) { }
        }
    }
}
