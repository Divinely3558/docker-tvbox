package android.webkit;

import android.net.http.SslError;

public class WebViewClient {
    public boolean shouldOverrideUrlLoading(WebView view, String url) { return false; }

    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return false; }

    public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {}

    public void onPageFinished(WebView view, String url) {}

    public void onLoadResource(WebView view, String url) {}

    public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {}

    public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {}

    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) { return null; }

    public WebResourceResponse shouldInterceptRequest(WebView view, String url) { return null; }

    public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {}
}
