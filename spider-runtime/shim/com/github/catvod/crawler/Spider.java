package com.github.catvod.crawler;

import android.content.Context;
import java.io.ByteArrayInputStream;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import okhttp3.Dns;

/**
 * The TVBox/CatVod spider contract. Jars are compiled against this type but do not
 * bundle it, so the runtime must supply a signature-compatible copy.
 */
public abstract class Spider {

    /** Set by the loader; spiders use it to build proxy and danmaku URLs. */
    public String siteKey;

    /** Host callbacks (proxy address, log, sniff); injected through {@link #initApi}. */
    protected SpiderApi api;

    /** Called before {@code init}: some spiders need the proxy address to build their first URL. */
    public void initApi(SpiderApi api) {
        this.api = api;
    }

    public boolean initApi(SpiderApi api, String siteKey) {
        boolean first = this.api == null;
        this.api = api;
        if (siteKey != null && !siteKey.isEmpty()) this.siteKey = siteKey;
        initApi(api);
        return first;
    }

    public void init(Context context) throws Exception {}

    public void init(Context context, String extend) throws Exception {
        init(context);
    }

    public String homeContent(boolean filter) throws Exception {
        return "{\"class\":[]}";
    }

    public String homeVideoContent() throws Exception {
        return "{\"list\":[]}";
    }

    public String categoryContent(String tid, String pg, boolean filter, HashMap<String, String> extend) throws Exception {
        return "{\"list\":[]}";
    }

    public String detailContent(List<String> ids) throws Exception {
        return "{\"list\":[]}";
    }

    /**
     * catvod's default pair: the paged overload falls back to the two-arg one, so a spider
     * that only implements {@code search(key, quick)} still answers our paged calls. Throwing
     * here (not returning an empty list) keeps "site has no search" from looking like "no hits".
     */
    public String searchContent(String key, boolean quick) throws Exception {
        throw new UnsupportedOperationException(siteKey + " 未实现搜索");
    }

    public String searchContent(String key, boolean quick, String pg) throws Exception {
        return searchContent(key, quick);
    }

    public String playerContent(String flag, String id, List<String> vipFlags) throws Exception {
        return "{}";
    }

    public String liveContent(String url) throws Exception {
        return "";
    }

    public boolean manualVideoCheck() throws Exception {
        return false;
    }

    public boolean isVideoFormat(String url) throws Exception {
        return false;
    }

    /** {@code new Object[]{code, headersOrContentType, InputStream}} */
    public Object[] proxy(Map<String, String> params) throws Exception {
        return new Object[]{404, "text/plain", new ByteArrayInputStream(new byte[0])};
    }

    public Object[] proxyLocal(Map<String, String> params) throws Exception {
        return proxy(params);
    }

    public String action(String action) throws Exception {
        return "{}";
    }

    public void cancelByTag() {}

    public void destroy() {}

    /** Referenced directly by the bundled catvod networking layer. */
    public static Dns safeDns() {
        return hostname -> java.util.Arrays.asList(java.net.InetAddress.getAllByName(hostname));
    }

    public String proxyUrl() {
        return "/spider?do=jar&siteKey=" + (siteKey == null ? "" : siteKey);
    }

    public String proxyUrl(Map<String, String> params) {
        StringBuilder sb = new StringBuilder(proxyUrl());
        if (params != null) for (Map.Entry<String, String> e : params.entrySet()) sb.append('&').append(e.getKey()).append('=').append(e.getValue());
        return sb.toString();
    }
}
