package android.os;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/**
 * spiders post callbacks here; a daemon scheduler keeps the runner exitable once stdin closes.
 */
public final class Looper {

    public static final ScheduledExecutorService EXEC =
            Executors.newScheduledThreadPool(4, new ThreadFactory() {
                @Override public Thread newThread(Runnable r) {
                    Thread t = new Thread(r, "spider-main-looper");
                    t.setDaemon(true);
                    return t;
                }
            });

    private static final Looper MAIN = new Looper("main");
    private static final ThreadLocal<Looper> CURRENT = new ThreadLocal<Looper>() {
        @Override protected Looper initialValue() { return MAIN; }
    };

    private final String name;

    private Looper(String name) { this.name = name; }

    public static Looper getMainLooper() { return MAIN; }

    public static Looper myLooper() { return CURRENT.get(); }

    public static void loop() {}

    public static void prepare() {}

    public static void prepareInner() {}

    public static void quitAllowed() {}

    public String getName() { return name; }

    public Thread getThread() { return Thread.currentThread(); }

    public void quit() {}

    public void quitSafely() {}

    public ScheduledFuture<?> schedule(Runnable r, long delayMillis) {
        return EXEC.schedule(r, Math.max(0, delayMillis), TimeUnit.MILLISECONDS);
    }

    public static class Builder {
        private final String name;

        public Builder(String name) { this.name = name; }

        public Builder setThreadName(String name) { return this; }

        public Builder setQuitAllowed(boolean allowed) { return this; }

        public Builder setExtraNotificationEnabled(boolean enabled) { return this; }

        public Looper build() { return MAIN; }

        public Looper buildForCurrentThread() { return CURRENT.get(); }
    }
}
