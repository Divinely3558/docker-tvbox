package android.util;

public final class Log {
    public static final int VERBOSE = 2, DEBUG = 3, INFO = 4, WARN = 5, ERROR = 6, ASSERT = 7;
    private Log() {}

    private static void out(int level, String tag, String msg, Throwable t) {
        String line = "[" + levelChar(level) + "/" + tag + "] " + msg;
        // stdout carries the runner's JSON-line protocol; logs must go to stderr.
        java.io.PrintStream s = System.err;
        s.println(line);
        if (t != null) t.printStackTrace(s);
    }

    private static char levelChar(int l) { return "VDIWEA".charAt(l >= 2 && l <= 7 ? l - 2 : 3); }

    public static int v(String t, String m) { out(VERBOSE, t, m, null); return 0; }
    public static int v(String t, String m, Throwable e) { out(VERBOSE, t, m, e); return 0; }
    public static int d(String t, String m) { out(DEBUG, t, m, null); return 0; }
    public static int d(String t, String m, Throwable e) { out(DEBUG, t, m, e); return 0; }
    public static int i(String t, String m) { out(INFO, t, m, null); return 0; }
    public static int i(String t, String m, Throwable e) { out(INFO, t, m, e); return 0; }
    public static int w(String t, String m) { out(WARN, t, m, null); return 0; }
    public static int w(String t, String m, Throwable e) { out(WARN, t, m, e); return 0; }
    public static int w(Throwable e) { out(WARN, "Log", e.toString(), e); return 0; }
    public static int e(String t, String m) { out(ERROR, t, m, null); return 0; }
    public static int e(String t, String m, Throwable e) { out(ERROR, t, m, e); return 0; }
    public static int e(Throwable e) { out(ERROR, "Log", e.toString(), e); return 0; }
    public static int println(int level, String tag, String msg) { out(level, tag, msg, null); return 0; }
    public static boolean isLoggable(String tag, int level) { return false; }
    public static String getStackTraceString(Throwable e) {
        java.io.StringWriter w = new java.io.StringWriter();
        e.printStackTrace(new java.io.PrintWriter(w));
        return w.toString();
    }
}
