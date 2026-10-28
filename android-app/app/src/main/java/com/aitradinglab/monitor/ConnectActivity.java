package com.aitradinglab.monitor;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import com.aitradinglab.engine.HttpServer;
import com.aitradinglab.engine.ServerService;

/**
 * v5 connection screen — three modes:
 *  THIS DEVICE: the FULL engine runs on this phone (service + embedded server + WebView)
 *  LOCAL: phone and computer on the same Wi-Fi (http://<computer-ip>:81) or USB (adb reverse)
 *  CLOUD: cloud server from anywhere (https://<domain>)
 * The engine itself stays invite-only (2FA + invitation code).
 */
public class ConnectActivity extends Activity {

    private LinearLayout boxDevice, boxLocal, boxCloud;
    private TextView labelDevice, labelLocal, labelCloud, subDevice, subLocal, subCloud, modeInfo;
    private EditText urlInput;
    private TextView lastConnected;
    private SharedPreferences prefs;
    private String mode = "device";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        try {
            initUi();
        } catch (Throwable e) {
            // the launcher screen must NEVER crash — worst case, tell the user and stay up
            try {
                Toast.makeText(this, "Startup issue — reopening mode screen", Toast.LENGTH_LONG).show();
            } catch (Throwable ignored) { }
        }
    }

    private void initUi() {
        setContentView(R.layout.activity_connect);

        prefs = getSharedPreferences("atl", Context.MODE_PRIVATE);
        boxDevice = findViewById(R.id.mode_device_box);
        boxLocal = findViewById(R.id.mode_local_box);
        boxCloud = findViewById(R.id.mode_cloud_box);
        labelDevice = findViewById(R.id.mode_device_label);
        subDevice = findViewById(R.id.mode_device_sub);
        labelLocal = findViewById(R.id.mode_local_label);
        labelCloud = findViewById(R.id.mode_cloud_label);
        subLocal = findViewById(R.id.mode_local_sub);
        subCloud = findViewById(R.id.mode_cloud_sub);
        modeInfo = findViewById(R.id.mode_info);
        urlInput = findViewById(R.id.url_input);
        lastConnected = findViewById(R.id.last_connected);
        View forgetBtn = findViewById(R.id.btn_forget);
        View connectBtn = findViewById(R.id.btn_connect);

        boxDevice.setOnClickListener(v -> setMode("device"));
        boxLocal.setOnClickListener(v -> setMode("local"));
        boxCloud.setOnClickListener(v -> setMode("cloud"));

        // restore last used mode (default: this device — full phone server)
        setMode(prefs.getString("server_mode", "device"));

        urlInput.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int a, int b, int c) {}
            @Override public void onTextChanged(CharSequence s, int a, int b, int c) {}
            @Override public void afterTextChanged(Editable s) {
                boolean valid = normalize(s.toString()) != null;
                connectBtn.setEnabled(valid);
                connectBtn.setAlpha(valid ? 1f : 0.4f);
            }
        });

        urlInput.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == EditorInfo.IME_ACTION_GO) {
                connect();
                return true;
            }
            return false;
        });

        connectBtn.setOnClickListener(v -> connect());
        connectBtn.setEnabled(false);
        connectBtn.setAlpha(0.4f);

        forgetBtn.setOnClickListener(v -> {
            String key = "last_" + mode;
            prefs.edit().remove(key).apply();
            String cur = prefs.getString("server_url", "");
            String last = prefs.getString(key, "");
            if (cur.equals(last) || last.isEmpty()) prefs.edit().remove("server_url").apply();
            urlInput.setText("");
            lastConnected.setVisibility(View.GONE);
            forgetBtn.setVisibility(View.GONE);
            Toast.makeText(this, "Saved " + mode + " address removed", Toast.LENGTH_SHORT).show();
        });
    }

    private void setMode(String m) {
        try {
            applyMode(m);
        } catch (Throwable e) {
            try { Toast.makeText(this, "Mode error — reset to THIS DEVICE", Toast.LENGTH_SHORT).show(); } catch (Throwable ignored) { }
            try { applyMode("device"); } catch (Throwable ignored) { }
        }
    }

    private void applyMode(String m) {
        mode = m;
        prefs.edit().putString("server_mode", m).apply();
        boolean device = "device".equals(m);
        boolean local = "local".equals(m);

        // THIS DEVICE card: green when selected
        int selDev = getResources().getColor(R.color.green);
        boxDevice.setBackgroundTintList(ColorStateList.valueOf(device ? selDev : getResources().getColor(R.color.surface)));
        labelDevice.setTextColor(getResources().getColor(device ? R.color.text_primary : R.color.text_dim));
        labelDevice.setTypeface(null, device ? Typeface.BOLD : Typeface.NORMAL);
        subDevice.setTextColor(getResources().getColor(device ? R.color.text_primary : R.color.text_dim));

        // selected card: accent color + bold; unselected: dim
        int selBg = getResources().getColor(local ? R.color.gold : R.color.cloud);
        boxLocal.setBackgroundTintList(ColorStateList.valueOf(local ? selBg : getResources().getColor(R.color.surface)));
        boxCloud.setBackgroundTintList(ColorStateList.valueOf(!local ? selBg : getResources().getColor(R.color.surface)));
        labelLocal.setTextColor(getResources().getColor(local ? R.color.text_primary : R.color.text_dim));
        labelCloud.setTextColor(getResources().getColor(!local ? R.color.text_primary : R.color.text_dim));
        labelLocal.setTypeface(null, local ? Typeface.BOLD : Typeface.NORMAL);
        labelCloud.setTypeface(null, !local ? Typeface.BOLD : Typeface.NORMAL);
        subLocal.setTextColor(getResources().getColor(local ? R.color.text_primary : R.color.text_dim));
        subCloud.setTextColor(getResources().getColor(!local ? R.color.text_primary : R.color.text_dim));

        modeInfo.setText(device ? R.string.mode_device : local ? R.string.mode_local : R.string.mode_cloud);
        urlInput.setVisibility(device ? View.GONE : View.VISIBLE);
        findViewById(R.id.btn_connect).setVisibility(device ? View.GONE : View.VISIBLE);

        if (device) {
            lastConnected.setVisibility(View.GONE);
            findViewById(R.id.btn_forget).setVisibility(View.GONE);
            launchDeviceServer();
            return;
        }

        urlInput.setHint(local ? R.string.hint_local : R.string.hint_cloud);

        // prefill this mode's last address
        String key = "last_" + m;
        String saved = prefs.getString(key, "");
        urlInput.setText(saved);
        urlInput.setSelection(urlInput.getText().length());

        if (!saved.isEmpty()) {
            lastConnected.setText(getString(R.string.last_connected) + ": " + saved);
            lastConnected.setVisibility(View.VISIBLE);
            View forgetBtn = findViewById(R.id.btn_forget);
            forgetBtn.setVisibility(View.VISIBLE);
        } else {
            lastConnected.setVisibility(View.GONE);
            findViewById(R.id.btn_forget).setVisibility(View.GONE);
        }

        // revalidate connect button for the prefilled text
        boolean valid = normalize(urlInput.getText().toString()) != null;
        View connectBtn = findViewById(R.id.btn_connect);
        connectBtn.setEnabled(valid);
        connectBtn.setAlpha(valid ? 1f : 0.4f);
    }

    private void connect() {
        String url = normalize(urlInput.getText().toString());
        if (url == null) {
            Toast.makeText(this, getString(R.string.err_invalid), Toast.LENGTH_LONG).show();
            return;
        }
        prefs.edit()
             .putString("server_url", url)
             .putString("server_mode", mode)
             .putString("last_" + mode, url)
             .apply();
        Intent i = new Intent(this, MainActivity.class);
        i.putExtra("server_url", url);
        startActivity(i);
    }

    /** THIS DEVICE: start the engine service and open the embedded dashboard. */
    private void launchDeviceServer() {
        try {
            runDeviceServer();
        } catch (Throwable e) {
            try { Toast.makeText(this, "Engine start issue: " + e, Toast.LENGTH_LONG).show(); } catch (Throwable ignored) { }
        }
    }

    private void runDeviceServer() {
        Toast.makeText(this, R.string.starting_engine, Toast.LENGTH_SHORT).show();
        String phoneUrl = "http://127.0.0.1:" + HttpServer.PORT;
        prefs.edit().putString("server_url", phoneUrl).putString("last_device", phoneUrl).apply();
        askNotificationPermission();
        try {
            startForegroundService(new Intent(this, ServerService.class));
        } catch (Exception e) {
            try { startService(new Intent(this, ServerService.class)); } catch (Exception ignored) { }
        }
        // wait for the embedded server to come up, then open it
        final Activity act = this;
        new Thread(() -> {
            for (int i = 0; i < 30; i++) {
                try {
                    java.net.Socket s = new java.net.Socket("127.0.0.1", HttpServer.PORT);
                    s.close();
                    runOnUiThread(() -> {
                        Intent i2 = new Intent(act, MainActivity.class);
                        i2.putExtra("server_url", "http://127.0.0.1:" + HttpServer.PORT);
                        startActivity(i2);
                    });
                    return;
                } catch (Exception ignored) {
                    try { Thread.sleep(500); } catch (InterruptedException ignored2) { return; }
                }
            }
            runOnUiThread(() -> Toast.makeText(act, "Engine failed to start — reopen the app", Toast.LENGTH_LONG).show());
        }, "wait-server").start();
    }

    /**
     * Android 13+ runtime notification permission — requested from the foreground,
     * wrapped, one tap. The battery-optimization prompt lives in MainActivity
     * (after the dashboard is loaded) so the cold-start path stays minimal.
     */
    private void askNotificationPermission() {
        if (android.os.Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
            try {
                requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 901);
            } catch (Exception ignored) { }
        }
    }

    /** Accepts "192.168.1.10:81", "http://192.168.1.10", "https://x.com" and normalizes. */
    static String normalize(String raw) {
        if (raw == null) return null;
        String s = raw.trim();
        if (s.isEmpty()) return null;
        if (!s.startsWith("http://") && !s.startsWith("https://")) {
            s = "http://" + s;
        }
        // strip trailing slash
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        String hostPart = s.startsWith("https://") ? s.substring(8) : s.substring(7);
        if (hostPart.isEmpty()) return null;
        boolean validChar = hostPart.matches("[A-Za-z0-9.\\-_:\\[\\]]+");
        if (!validChar) return null;
        // default port for bare local IPs: 81 (engine gateway)
        if (!s.startsWith("https://") && !hostPart.contains(":")) {
            s = s + ":81";
        }
        return s;
    }
}
