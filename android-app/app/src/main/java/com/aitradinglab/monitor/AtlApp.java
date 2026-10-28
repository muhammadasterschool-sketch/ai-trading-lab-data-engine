package com.aitradinglab.monitor;

import android.app.Application;

/**
 * Installs the global crash net BEFORE any activity or service runs.
 * Any uncaught crash is written to last-crash.txt; the next successful start
 * feeds it into the engine's system ledger (Logs tab) so no crash is ever invisible.
 */
public class AtlApp extends Application {
    @Override public void onCreate() {
        super.onCreate();
        final Thread.UncaughtExceptionHandler prev = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            try {
                String st = android.util.Log.getStackTraceString(e);
                if (st.length() > 4000) st = st.substring(0, 4000);
                java.io.OutputStream os = openFileOutput("last-crash.txt", MODE_PRIVATE);
                os.write(("time=" + System.currentTimeMillis() + "\nthread=" + t.getName() + "\n" + st).getBytes());
                os.close();
            } catch (Exception ignored) { }
            if (prev != null) prev.uncaughtException(t, e);
        });
    }
}
