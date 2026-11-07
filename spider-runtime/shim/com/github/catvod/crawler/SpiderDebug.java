package com.github.catvod.crawler;

public final class SpiderDebug {
    private SpiderDebug() {}

    public static void log(Throwable e) { android.util.Log.e("Spider", android.util.Log.getStackTraceString(e)); }

    public static void log(String msg) { android.util.Log.d("Spider", msg); }

    public static void log(String tag, String msg) { android.util.Log.d(tag, msg); }
}
