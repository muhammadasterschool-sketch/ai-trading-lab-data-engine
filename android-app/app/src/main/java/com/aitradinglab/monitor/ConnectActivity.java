package com.aitradinglab.monitor;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.ColorStateList;
import android.os.Build;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.KeyEvent;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import com.aitradinglab.engine.HttpServer;
import com.aitradinglab.engine.ServerService;
import java.net.Socket;

/* loaded from: classes.dex */
public class ConnectActivity extends Activity {
    private LinearLayout boxCloud;
    private LinearLayout boxDevice;
    private LinearLayout boxLocal;
    private TextView labelCloud;
    private TextView labelDevice;
    private TextView labelLocal;
    private TextView lastConnected;
    private String mode = "device";
    private TextView modeInfo;
    private SharedPreferences prefs;
    private TextView subCloud;
    private TextView subDevice;
    private TextView subLocal;
    private EditText urlInput;

    @Override // android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        try {
            try {
                initUi();
            } catch (Throwable unused) {
            }
        } catch (Throwable unused2) {
            Toast.makeText(this, "Startup issue — reopening mode screen", 1).show();
        }
    }

    private void initUi() {
        setContentView(R.layout.activity_connect);
        this.prefs = getSharedPreferences("atl", 0);
        this.boxDevice = (LinearLayout) findViewById(R.id.mode_device_box);
        this.boxLocal = (LinearLayout) findViewById(R.id.mode_local_box);
        this.boxCloud = (LinearLayout) findViewById(R.id.mode_cloud_box);
        this.labelDevice = (TextView) findViewById(R.id.mode_device_label);
        this.subDevice = (TextView) findViewById(R.id.mode_device_sub);
        this.labelLocal = (TextView) findViewById(R.id.mode_local_label);
        this.labelCloud = (TextView) findViewById(R.id.mode_cloud_label);
        this.subLocal = (TextView) findViewById(R.id.mode_local_sub);
        this.subCloud = (TextView) findViewById(R.id.mode_cloud_sub);
        this.modeInfo = (TextView) findViewById(R.id.mode_info);
        this.urlInput = (EditText) findViewById(R.id.url_input);
        this.lastConnected = (TextView) findViewById(R.id.last_connected);
        final View findViewById = findViewById(R.id.btn_forget);
        final View findViewById2 = findViewById(R.id.btn_connect);
        this.boxDevice.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda3
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                ConnectActivity.this.lambda$initUi$0(view);
            }
        });
        this.boxLocal.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda4
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                ConnectActivity.this.lambda$initUi$1(view);
            }
        });
        this.boxCloud.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda5
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                ConnectActivity.this.lambda$initUi$2(view);
            }
        });
        setMode(this.prefs.getString("server_mode", "device"));
        this.urlInput.addTextChangedListener(new TextWatcher() { // from class: com.aitradinglab.monitor.ConnectActivity.1
            @Override // android.text.TextWatcher
            public void beforeTextChanged(CharSequence charSequence, int i, int i2, int i3) {
            }

            @Override // android.text.TextWatcher
            public void onTextChanged(CharSequence charSequence, int i, int i2, int i3) {
            }

            @Override // android.text.TextWatcher
            public void afterTextChanged(Editable editable) {
                boolean z = ConnectActivity.normalize(editable.toString()) != null;
                findViewById2.setEnabled(z);
                findViewById2.setAlpha(z ? 1.0f : 0.4f);
            }
        });
        this.urlInput.setOnEditorActionListener(new TextView.OnEditorActionListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda6
            @Override // android.widget.TextView.OnEditorActionListener
            public final boolean onEditorAction(TextView textView, int i, KeyEvent keyEvent) {
                boolean lambda$initUi$3;
                lambda$initUi$3 = ConnectActivity.this.lambda$initUi$3(textView, i, keyEvent);
                return lambda$initUi$3;
            }
        });
        findViewById2.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda7
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                ConnectActivity.this.lambda$initUi$4(view);
            }
        });
        findViewById2.setEnabled(false);
        findViewById2.setAlpha(0.4f);
        findViewById.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda8
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                ConnectActivity.this.lambda$initUi$5(findViewById, view);
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$initUi$0(View view) {
        setMode("device");
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$initUi$1(View view) {
        setMode("local");
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$initUi$2(View view) {
        setMode("cloud");
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ boolean lambda$initUi$3(TextView textView, int i, KeyEvent keyEvent) {
        if (i != 2) {
            return false;
        }
        connect();
        return true;
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$initUi$4(View view) {
        connect();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$initUi$5(View view, View view2) {
        String str = "last_" + this.mode;
        this.prefs.edit().remove(str).apply();
        String string = this.prefs.getString("server_url", "");
        String string2 = this.prefs.getString(str, "");
        if (string.equals(string2) || string2.isEmpty()) {
            this.prefs.edit().remove("server_url").apply();
        }
        this.urlInput.setText("");
        this.lastConnected.setVisibility(8);
        view.setVisibility(8);
        Toast.makeText(this, "Saved " + this.mode + " address removed", 0).show();
    }

    private void setMode(String str) {
        try {
            try {
                applyMode(str);
            } catch (Throwable unused) {
                Toast.makeText(this, "Mode error — reset to THIS DEVICE", 0).show();
                try {
                    applyMode("device");
                } catch (Throwable unused2) {
                }
            }
        } catch (Throwable unused3) {
            applyMode("device");
        }
    }

    private void applyMode(String str) {
        this.mode = str;
        this.prefs.edit().putString("server_mode", str).apply();
        boolean equals = "device".equals(str);
        boolean equals2 = "local".equals(str);
        int color = getResources().getColor(R.color.green);
        LinearLayout linearLayout = this.boxDevice;
        if (!equals) {
            color = getResources().getColor(R.color.surface);
        }
        linearLayout.setBackgroundTintList(ColorStateList.valueOf(color));
        this.labelDevice.setTextColor(getResources().getColor(equals ? R.color.text_primary : R.color.text_dim));
        this.labelDevice.setTypeface(null, equals ? 1 : 0);
        this.subDevice.setTextColor(getResources().getColor(equals ? R.color.text_primary : R.color.text_dim));
        int color2 = getResources().getColor(equals2 ? R.color.gold : R.color.cloud);
        this.boxLocal.setBackgroundTintList(ColorStateList.valueOf(equals2 ? color2 : getResources().getColor(R.color.surface)));
        LinearLayout linearLayout2 = this.boxCloud;
        if (equals2) {
            color2 = getResources().getColor(R.color.surface);
        }
        linearLayout2.setBackgroundTintList(ColorStateList.valueOf(color2));
        this.labelLocal.setTextColor(getResources().getColor(equals2 ? R.color.text_primary : R.color.text_dim));
        this.labelCloud.setTextColor(getResources().getColor(!equals2 ? R.color.text_primary : R.color.text_dim));
        this.labelLocal.setTypeface(null, equals2 ? 1 : 0);
        this.labelCloud.setTypeface(null, !equals2 ? 1 : 0);
        this.subLocal.setTextColor(getResources().getColor(equals2 ? R.color.text_primary : R.color.text_dim));
        this.subCloud.setTextColor(getResources().getColor(!equals2 ? R.color.text_primary : R.color.text_dim));
        this.modeInfo.setText(equals ? R.string.mode_device : equals2 ? R.string.mode_local : R.string.mode_cloud);
        this.urlInput.setVisibility(equals ? 8 : 0);
        findViewById(R.id.btn_connect).setVisibility(equals ? 8 : 0);
        if (equals) {
            this.lastConnected.setVisibility(8);
            findViewById(R.id.btn_forget).setVisibility(8);
            launchDeviceServer();
            return;
        }
        this.urlInput.setHint(equals2 ? R.string.hint_local : R.string.hint_cloud);
        String string = this.prefs.getString("last_" + str, "");
        this.urlInput.setText(string);
        EditText editText = this.urlInput;
        editText.setSelection(editText.getText().length());
        if (!string.isEmpty()) {
            this.lastConnected.setText(getString(R.string.last_connected) + ": " + string);
            this.lastConnected.setVisibility(0);
            findViewById(R.id.btn_forget).setVisibility(0);
        } else {
            this.lastConnected.setVisibility(8);
            findViewById(R.id.btn_forget).setVisibility(8);
        }
        boolean z = normalize(this.urlInput.getText().toString()) != null;
        View findViewById = findViewById(R.id.btn_connect);
        findViewById.setEnabled(z);
        findViewById.setAlpha(z ? 1.0f : 0.4f);
    }

    private void connect() {
        String normalize = normalize(this.urlInput.getText().toString());
        if (normalize == null) {
            Toast.makeText(this, getString(R.string.err_invalid), 1).show();
            return;
        }
        this.prefs.edit().putString("server_url", normalize).putString("server_mode", this.mode).putString("last_" + this.mode, normalize).apply();
        Intent intent = new Intent(this, (Class<?>) MainActivity.class);
        intent.putExtra("server_url", normalize);
        startActivity(intent);
    }

    private void launchDeviceServer() {
        try {
            runDeviceServer();
        } catch (Throwable th) {
            try {
                Toast.makeText(this, "Engine start issue: " + th, 1).show();
            } catch (Throwable unused) {
            }
        }
    }

    private void runDeviceServer() {
        Toast.makeText(this, R.string.starting_engine, 0).show();
        this.prefs.edit().putString("server_url", "http://127.0.0.1:8788").putString("last_device", "http://127.0.0.1:8788").apply();
        askNotificationPermission();
        try {
            try {
                startForegroundService(new Intent(this, (Class<?>) ServerService.class));
            } catch (Exception unused) {
                startService(new Intent(this, (Class<?>) ServerService.class));
            }
        } catch (Exception unused2) {
        }
        new Thread(new Runnable() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda0
            @Override // java.lang.Runnable
            public final void run() {
                ConnectActivity.this.lambda$runDeviceServer$8(ConnectActivity.this);
            }
        }, "wait-server").start();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$runDeviceServer$8(final Activity activity) {
        for (int i = 0; i < 30; i++) {
            try {
                new Socket("127.0.0.1", HttpServer.PORT).close();
                runOnUiThread(new Runnable() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda1
                    @Override // java.lang.Runnable
                    public final void run() {
                        ConnectActivity.this.lambda$runDeviceServer$6(activity);
                    }
                });
                return;
            } catch (Exception unused) {
                try {
                    Thread.sleep(500L);
                } catch (InterruptedException unused2) {
                    return;
                }
            }
        }
        runOnUiThread(new Runnable() { // from class: com.aitradinglab.monitor.ConnectActivity$$ExternalSyntheticLambda2
            @Override // java.lang.Runnable
            public final void run() {
                Toast.makeText(activity, "Engine failed to start — reopen the app", 1).show();
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$runDeviceServer$6(Activity activity) {
        Intent intent = new Intent(activity, (Class<?>) MainActivity.class);
        intent.putExtra("server_url", "http://127.0.0.1:8788");
        startActivity(intent);
    }

    private void askNotificationPermission() {
        if (Build.VERSION.SDK_INT < 33 || checkSelfPermission("android.permission.POST_NOTIFICATIONS") == 0) {
            return;
        }
        try {
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 901);
        } catch (Exception unused) {
        }
    }

    static String normalize(String str) {
        if (str == null) {
            return null;
        }
        String trim = str.trim();
        if (trim.isEmpty()) {
            return null;
        }
        if (!trim.startsWith("http://") && !trim.startsWith("https://")) {
            trim = "http://" + trim;
        }
        while (trim.endsWith("/")) {
            trim = trim.substring(0, trim.length() - 1);
        }
        String substring = trim.substring(trim.startsWith("https://") ? 8 : 7);
        if (!substring.isEmpty() && substring.matches("[A-Za-z0-9.\\-_:\\[\\]]+")) {
            return (trim.startsWith("https://") || substring.contains(":")) ? trim : trim + ":81";
        }
        return null;
    }
}
