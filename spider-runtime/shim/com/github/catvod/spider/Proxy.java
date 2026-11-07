package com.github.catvod.spider;

import org.json.JSONObject;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * catvod 的本地代理地址构造器。
 *
 * 内层 spider 会调用 ``Proxy.newProxyUrl(...)`` 把播放/图片地址改写成
 * ``本站地址/proxy?url=...``；宿主（本项目的 jarscript）识别到 /proxy 后
 * 会回调 spider 的 ``proxy(params)`` 方法，所以这里只要按同样格式拼 URL 即可。
 */
public class Proxy {

    public static String getUrl() {
        return getUrl(false);
    }

    public static String getUrl(boolean local) {
        String base = System.getProperty("spider.base.url", "").trim();
        if (base.isEmpty()) base = "http://127.0.0.1:9978";
        while (base.endsWith("/")) base = base.substring(0, base.length() - 1);
        return base + "/proxy";
    }

    public static String newProxyUrl(String url) {
        return newProxyUrl(url, new LinkedHashMap<>());
    }

    public static String newProxyUrl(String url, Map<String, String> headers) {
        return newProxyUrl(url, headers, "");
    }

    public static String newProxyUrl(String url, Map<String, String> headers, String tag) {
        StringBuilder sb = new StringBuilder(getUrl(true)).append("?url=").append(encode(url));
        if (headers != null && !headers.isEmpty()) {
            sb.append("&headers=").append(encode(new JSONObject(headers).toString()));
        }
        if (tag != null && !tag.isEmpty()) sb.append("&tag=").append(encode(tag));
        return sb.toString();
    }

    private static String encode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }
}
