package android.os;

public class HandlerThread {
    public HandlerThread(String name) {}
    public HandlerThread(String name, int priority) {}
    public void start() {}
    public android.os.Looper getLooper() { return android.os.Looper.getMainLooper(); }
    public android.os.Handler getThreadHandler() { return null; }
    public boolean quit() { return true; }
    public boolean quitSafely() { return true; }
}
