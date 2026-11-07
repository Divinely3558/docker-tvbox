package android.webkit;

public class WebChromeClient {
    public void onProgressChanged(WebView view, int newProgress) {}

    public boolean onJsAlert(WebView view, String url, String message, JsResult result) { return false; }

    public boolean onJsConfirm(WebView view, String url, String message, JsResult result) { return false; }

    public void onReceivedTitle(WebView view, String title) {}
}
