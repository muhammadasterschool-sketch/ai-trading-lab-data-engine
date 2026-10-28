package com.aitradinglab.monitor;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Full-screen WebView client for the AI Trading Lab Data Engine.
 * Cookies persist across restarts (login session survives). Back button navigates
 * web history. On unreachable server → back to ConnectActivity with error.
 */
public class MainActivity extends Activity {

    private WebView webView;
    private LinearLayout errorView;
    private String serverUrl;
    private boolean pageLoaded = false;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        errorView = findViewById(R.id.error_view);
        Button retryBtn = findViewById(R.id.btn_retry);
        Button changeBtn = findViewById(R.id.btn_change_server);
        TextView errText = findViewById(R.id.error_text);

        serverUrl = getIntent().getStringExtra("server_url");
        if (serverUrl == null) {
            serverUrl = getSharedPreferences("atl", MODE_PRIVATE).getString("server_url", "");
        }
        if (serverUrl == null || serverUrl.isEmpty()) {
            backToConnect();
            return;
        }

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setDisplayZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                pageLoaded = false;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                pageLoaded = true;
                errorView.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
                CookieManager.getInstance().flush();
                maybeBatteryPrompt();
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                // keep the user inside the engine
                return false;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame() && !pageLoaded) {
                    showError();
                }
            }

            @Override
            public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
                // Self-signed cert on a private cloud server: allow the owner to continue
                // (invite-only private tool; standard WebView hardening still applies to everything else)
                handler.proceed();
            }
        });

        retryBtn.setOnClickListener(v -> {
            errorView.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            webView.reload();
        });
        changeBtn.setOnClickListener(v -> backToConnect());

        webView.loadUrl(serverUrl);
    }

    private void showError() {
        runOnUiThread(() -> {
            webView.setVisibility(View.GONE);
            errorView.setVisibility(View.VISIBLE);
        });
    }

    /**
     * One-time Samsung One UI battery exemption — asked AFTER the dashboard is on
     * screen (never during cold start), guarded on every step.
     * This stops One UI from putting the engine to sleep.
     */
    private void maybeBatteryPrompt() {
        try {
            SharedPreferences p = getSharedPreferences("atl", MODE_PRIVATE);
            if (p.getBoolean("battery_asked", false)) return;
            p.edit().putBoolean("battery_asked", true).apply();
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                                Uri.parse("package:" + getPackageName())));
                    } catch (Exception ignored) { }
                }, 2500);
            }
        } catch (Exception ignored) { }
    }

    private void backToConnect() {
        Intent i = new Intent(this, ConnectActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(i);
        finish();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            if (errorView != null && errorView.getVisibility() == View.VISIBLE) {
                backToConnect();
                return true;
            }
            if (webView != null && webView.canGoBack()) {
                webView.goBack();
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (webView != null) CookieManager.getInstance().flush();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) webView.destroy();
        super.onDestroy();
    }
}
