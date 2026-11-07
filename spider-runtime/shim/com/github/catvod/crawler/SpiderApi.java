package com.github.catvod.crawler;

import com.google.gson.JsonArray;

/**
 * The callback surface the host app hands to spiders (catvod declares it, jars only
 * reference it). Spiders call it to reach the player's local proxy and to log,
 * so the signatures have to match what the jars were compiled against.
 */
public interface SpiderApi {

    /** Base URL of our HTTP server as the browser sees it; the boolean asks for the IPv4 form. */
    String getAddress(boolean ipv4);

    String getPort();

    /** 0 = landscape, 1 = portrait; only used to pick image sizes. */
    int getScreenOrientation();

    void log(String content);

    /** Web-page sniffing hook, only the TVBox app can run it. */
    String webParse(String url, String ext);

    /** Batched HTTP requests, executed by the host in the app. */
    String multiReq(JsonArray requests);

    String lrcToSrt(String lrc);
}
