package android.os;

/** Posts to {@link Looper#EXEC}; runnables and messages execute inline on that scheduler. */
public class Handler {

    public interface Callback {
        boolean handleMessage(Message m);
    }

    private final Looper looper;
    private final Callback callback;

    public Handler() { this(Looper.getMainLooper(), null); }

    public Handler(boolean async) { this(Looper.getMainLooper(), null); }

    public Handler(Callback callback) { this(Looper.getMainLooper(), callback); }

    public Handler(Looper looper) { this(looper, null); }

    public Handler(Looper looper, boolean async) { this(looper, null); }

    public Handler(Looper looper, Callback callback) {
        this.looper = looper == null ? Looper.getMainLooper() : looper;
        this.callback = callback;
    }

    public final Looper getLooper() { return looper; }

    public final Callback getCallback() { return callback; }

    public boolean post(Runnable r) {
        if (r != null) Looper.EXEC.execute(r);
        return true;
    }

    public boolean postDelayed(Runnable r, long delayMillis) {
        if (r != null) Looper.EXEC.schedule(r, Math.max(0, delayMillis), java.util.concurrent.TimeUnit.MILLISECONDS);
        return true;
    }

    public boolean postAtTime(Runnable r, long uptimeMillis) {
        return postDelayed(r, Math.max(0, uptimeMillis - SystemClock.uptimeMillis()));
    }

    public boolean postAtTime(Runnable r, Object token, long uptimeMillis) { return postAtTime(r, uptimeMillis); }

    public boolean postAtFrontOfQueue(Runnable r) { return post(r); }

    public void removeCallbacks(Runnable r) {}

    public void removeCallbacks(Runnable r, Object token) {}

    public void removeMessages(int what) {}

    public void removeMessages(int what, Object obj) {}

    public void removeCallbacksAndMessages(Object token) {}

    public boolean hasMessages(int what) { return false; }

    public boolean hasMessages(int what, Object obj) { return false; }

    public final Message obtainMessage() { return Message.obtain(this); }

    public final Message obtainMessage(int what) { return Message.obtain(this, what); }

    public final Message obtainMessage(int what, Object obj) { return Message.obtain(this, what, obj); }

    public final Message obtainMessage(int what, int arg1, int arg2) { return Message.obtain(this, what, arg1, arg2); }

    public final Message obtainMessage(int what, int arg1, int arg2, Object obj) {
        Message m = Message.obtain(this, what, arg1, arg2);
        m.obj = obj;
        return m;
    }

    public boolean sendMessage(Message msg) { return sendMessageDelayed(msg, 0); }

    public boolean sendMessageDelayed(Message msg, long delayMillis) {
        if (msg == null) return false;
        msg.target = this;
        postDelayed(() -> dispatchMessage(msg), delayMillis);
        return true;
    }

    public boolean sendEmptyMessage(int what) { return sendMessage(obtainMessage(what)); }

    public boolean sendEmptyMessageDelayed(int what, long delayMillis) { return sendMessageDelayed(obtainMessage(what), delayMillis); }

    public boolean sendEmptyMessageAtTime(int what, long uptimeMillis) { return sendMessageDelayed(obtainMessage(what), uptimeMillis); }

    public boolean dispatchMessage(Message msg) {
        if (msg == null) return false;
        if (msg.callback != null) msg.callback.run();
        if (callback != null && callback.handleMessage(msg)) return true;
        handleMessage(msg);
        return true;
    }

    public void handleMessage(Message msg) {}

    public final void dispatchLooper() {}
}
