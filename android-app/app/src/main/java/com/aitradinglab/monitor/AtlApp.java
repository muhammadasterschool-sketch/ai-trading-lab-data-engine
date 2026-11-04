package com.aitradinglab.monitor;

import android.app.Application;
import android.util.Log;
import java.io.FileOutputStream;
import java.lang.Thread;

/* loaded from: classes.dex */
public class AtlApp extends Application {
    @Override // android.app.Application
    public void onCreate() {
        super.onCreate();
        final Thread.UncaughtExceptionHandler defaultUncaughtExceptionHandler = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(new Thread.UncaughtExceptionHandler() { // from class: com.aitradinglab.monitor.AtlApp$$ExternalSyntheticLambda0
            @Override // java.lang.Thread.UncaughtExceptionHandler
            public final void uncaughtException(Thread thread, Throwable th) {
                AtlApp.this.lambda$onCreate$0(defaultUncaughtExceptionHandler, thread, th);
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$onCreate$0(Thread.UncaughtExceptionHandler uncaughtExceptionHandler, Thread thread, Throwable th) {
        try {
            String stackTraceString = Log.getStackTraceString(th);
            if (stackTraceString.length() > 4000) {
                stackTraceString = stackTraceString.substring(0, 4000);
            }
            FileOutputStream openFileOutput = openFileOutput("last-crash.txt", 0);
            openFileOutput.write(("time=" + System.currentTimeMillis() + "\nthread=" + thread.getName() + "\n" + stackTraceString).getBytes());
            openFileOutput.close();
        } catch (Exception unused) {
        }
        if (uncaughtExceptionHandler != null) {
            uncaughtExceptionHandler.uncaughtException(thread, th);
        }
    }
}
