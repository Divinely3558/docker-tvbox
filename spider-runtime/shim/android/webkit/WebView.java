package android.webkit;

import android.content.Context;
import android.view.View;

public class WebView extends View {

    public WebView() {
    }

    public WebView(Context context) {
    }

    public void loadUrl(String url) {}

    public void loadUrl(String url, java.util.Map<String, String> headers) {}

    public void loadData(String data, String mimeType, String encoding) {}

    public void loadDataWithBaseURL(String baseUrl, String data, String mimeType, String encoding, String historyUrl) {}

    public void setWebViewClient(WebViewClient client) {}

    public void setWebChromeClient(WebChromeClient client) {}

    public WebSettings getSettings() { return new WebSettings(); }

    public void addJavascriptInterface(Object object, String name) {}

    public void evaluateJavascript(String script, ValueCallback<String> callback) {}

    public void stopLoading() {}

    public void reload() {}

    public void destroy() {}

    public boolean canGoBack() { return false; }

    public void goBack() {}

    public void clearCache(boolean includeDiskFiles) {}

    public void setDownloadListener(DownloadListener listener) {}

    public void setLayoutParams(Object params) {}

    public void post(Runnable runnable) {}

    public void postDelayed(Runnable runnable, long delayMillis) {}

    public void setInitialScale(int scaleInPercent) {}

    public void setBackgroundColor(int color) {}

    public static void setWebContentsDebuggingEnabled(boolean enabled) {}

    public static class WebViewTransport {
        public void setWebView(WebView webview) {}
    }
}
