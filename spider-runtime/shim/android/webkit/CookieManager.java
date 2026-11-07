package android.webkit;

public class CookieManager {

    private static final CookieManager INSTANCE = new CookieManager();

    public static CookieManager getInstance() { return INSTANCE; }

    public void setCookie(String url, String value) {}

    public String getCookie(String url) { return ""; }

    public void removeAllCookies(ValueCallback<Boolean> callback) {}

    public void setAcceptCookie(boolean accept) {}

    public boolean acceptCookie() { return true; }
}
