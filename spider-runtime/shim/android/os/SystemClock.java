package android.os;

public final class SystemClock {
    private SystemClock() {}
    public static long elapsedRealtime() { return java.lang.management.ManagementFactory.getRuntimeMXBean().getUptime(); }
    public static long uptimeMillis() { return elapsedRealtime(); }
    public static long currentThreadTimeMillis() { return System.currentTimeMillis(); }
    public static void sleep(long ms) {
        try { Thread.sleep(ms); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
    }
}
