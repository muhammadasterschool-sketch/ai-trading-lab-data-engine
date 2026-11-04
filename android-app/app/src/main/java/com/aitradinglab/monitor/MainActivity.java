package com.aitradinglab.monitor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.JsResult;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;

/* loaded from: classes.dex */
public class MainActivity extends Activity {
    private LinearLayout errorView;
    private boolean pageLoaded = false;
    private String serverUrl;
    private WebView webView;

    @Override // android.app.Activity
    protected void onCreate(Bundle bundle) {
        super.onCreate(bundle);
        setContentView(R.layout.activity_main);
        this.webView = (WebView) findViewById(R.id.webview);
        this.errorView = (LinearLayout) findViewById(R.id.error_view);
        Button button = (Button) findViewById(R.id.btn_retry);
        Button button2 = (Button) findViewById(R.id.btn_change_server);
        String stringExtra = getIntent().getStringExtra("server_url");
        this.serverUrl = stringExtra;
        if (stringExtra == null) {
            this.serverUrl = getSharedPreferences("atl", 0).getString("server_url", "");
        }
        String str = this.serverUrl;
        if (str == null || str.isEmpty()) {
            backToConnect();
            return;
        }
        WebSettings settings = this.webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setCacheMode(-1);
        settings.setMixedContentMode(2);
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(this.webView, true);
        this.webView.setWebViewClient(new WebViewClient() { // from class: com.aitradinglab.monitor.MainActivity.1
            @Override // android.webkit.WebViewClient
            public boolean shouldOverrideUrlLoading(WebView webView, String str2) {
                return false;
            }

            @Override // android.webkit.WebViewClient
            public void onPageStarted(WebView webView, String str2, Bitmap bitmap) {
                MainActivity.this.pageLoaded = false;
            }

            @Override // android.webkit.WebViewClient
            public void onPageFinished(WebView webView, String str2) {
                MainActivity.this.pageLoaded = true;
                MainActivity.this.errorView.setVisibility(8);
                MainActivity.this.webView.setVisibility(0);
                CookieManager.getInstance().flush();
                MainActivity.this.maybeBatteryPrompt();
            }

            @Override // android.webkit.WebViewClient
            public void onReceivedError(WebView webView, WebResourceRequest webResourceRequest, WebResourceError webResourceError) {
                super.onReceivedError(webView, webResourceRequest, webResourceError);
                if (!webResourceRequest.isForMainFrame() || MainActivity.this.pageLoaded) {
                    return;
                }
                MainActivity.this.showError();
            }

            @Override // android.webkit.WebViewClient
            public void onReceivedSslError(WebView webView, SslErrorHandler sslErrorHandler, SslError sslError) {
                sslErrorHandler.proceed();
            }
        });
        // v1.7 FIX — WebChromeClient missing tha: WebView me confirm()/alert() SILENTLY false return
        // karte the, isliye CLOSE button tap par trade band nahi hoti thi. Ab JS dialogs Android
        // dialogs ke through sahi se dikhte hain.
        this.webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                try {
                    new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton("YES", (d, w) -> result.confirm())
                        .setNegativeButton("NO", (d, w) -> result.cancel())
                        .setOnCancelListener(d -> result.cancel())
                        .show();
                } catch (Throwable t) {
                    result.cancel();
                }
                return true;
            }

            @Override
            public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                try {
                    new AlertDialog.Builder(MainActivity.this)
                        .setMessage(message)
                        .setPositiveButton("OK", (d, w) -> result.confirm())
                        .setOnCancelListener(d -> result.cancel())
                        .show();
                } catch (Throwable t) {
                    result.cancel();
                }
                return true;
            }
        });
        button.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.MainActivity$$ExternalSyntheticLambda0
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                MainActivity.this.lambda$onCreate$0(view);
            }
        });
        button2.setOnClickListener(new View.OnClickListener() { // from class: com.aitradinglab.monitor.MainActivity$$ExternalSyntheticLambda1
            @Override // android.view.View.OnClickListener
            public final void onClick(View view) {
                MainActivity.this.lambda$onCreate$1(view);
            }
        });
        this.webView.loadUrl(this.serverUrl);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$onCreate$0(View view) {
        this.errorView.setVisibility(8);
        this.webView.setVisibility(0);
        this.webView.reload();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$onCreate$1(View view) {
        backToConnect();
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void showError() {
        runOnUiThread(new Runnable() { // from class: com.aitradinglab.monitor.MainActivity$$ExternalSyntheticLambda3
            @Override // java.lang.Runnable
            public final void run() {
                MainActivity.this.lambda$showError$2();
            }
        });
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$showError$2() {
        this.webView.setVisibility(8);
        this.errorView.setVisibility(0);
    }

    /* JADX INFO: Access modifiers changed from: private */
    public void maybeBatteryPrompt() {
        try {
            PowerManager powerManager = (PowerManager) getSystemService("power");
            if (powerManager != null && !powerManager.isIgnoringBatteryOptimizations(getPackageName())) {
                getSharedPreferences("atl", 0).edit().putBoolean("battery_asked", true).apply();
                new Handler(Looper.getMainLooper()).postDelayed(new Runnable() { // from class: com.aitradinglab.monitor.MainActivity$$ExternalSyntheticLambda2
                    @Override // java.lang.Runnable
                    public final void run() {
                        MainActivity.this.lambda$maybeBatteryPrompt$3();
                    }
                }, 2500L);
            }
        } catch (Exception unused) {
        }
    }

    /* JADX INFO: Access modifiers changed from: private */
    public /* synthetic */ void lambda$maybeBatteryPrompt$3() {
        try {
            startActivity(new Intent("android.settings.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS", Uri.parse("package:" + getPackageName())));
        } catch (Exception unused) {
        }
    }

    private void backToConnect() {
        Intent intent = new Intent(this, (Class<?>) ConnectActivity.class);
        intent.setFlags(603979776);
        startActivity(intent);
        finish();
    }

    @Override // android.app.Activity, android.view.KeyEvent.Callback
    public boolean onKeyDown(int i, KeyEvent keyEvent) {
        if (i == 4) {
            LinearLayout linearLayout = this.errorView;
            if (linearLayout != null && linearLayout.getVisibility() == 0) {
                backToConnect();
                return true;
            }
            WebView webView = this.webView;
            if (webView != null && webView.canGoBack()) {
                this.webView.goBack();
                return true;
            }
        }
        return super.onKeyDown(i, keyEvent);
    }

    @Override // android.app.Activity
    protected void onPause() {
        super.onPause();
        if (this.webView != null) {
            CookieManager.getInstance().flush();
        }
    }

    @Override // android.app.Activity
    protected void onDestroy() {
        WebView webView = this.webView;
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
