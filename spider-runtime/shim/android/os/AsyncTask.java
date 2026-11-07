package android.os;

import java.util.concurrent.Callable;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public abstract class AsyncTask<Params, Progress, Result> {
    private static final ExecutorService SERIAL = Executors.newSingleThreadExecutor(r -> { Thread t = new Thread(r, "spider-async"); t.setDaemon(true); return t; });
    private static final ExecutorService PARALLEL = Executors.newCachedThreadPool(r -> { Thread t = new Thread(r, "spider-async"); t.setDaemon(true); return t; });
    private volatile Future<?> future;
    private volatile boolean cancelled;

    public static ExecutorService getSerialExecutor() { return SERIAL; }
    public static void execute(Runnable r) { SERIAL.execute(r); }

    @SafeVarargs
    public final AsyncTask<Params, Progress, Result> execute(Params... params) { return executeOnExecutor(SERIAL, params); }

    @SafeVarargs
    public final AsyncTask<Params, Progress, Result> executeOnExecutor(ExecutorService exec, Params... params) {
        future = exec.submit((Callable<Object>) () -> {
            Result r = doInBackground(params);
            if (!cancelled) onPostExecute(r);
            return r;
        });
        return this;
    }

    protected abstract Result doInBackground(Params... params);
    protected void onPreExecute() {}
    protected void onPostExecute(Result result) {}
    protected void onProgressUpdate(Progress... values) {}
    protected void onCancelled() {}
    protected void onCancelled(Result result) {}

    public final boolean isCancelled() { return cancelled; }
    public final boolean cancel(boolean mayInterruptIfRunning) {
        cancelled = true;
        if (future != null) future.cancel(mayInterruptIfRunning);
        return true;
    }
    public final Result get() throws InterruptedException, java.util.concurrent.ExecutionException { return null; }
    public final Result get(long timeout, java.util.concurrent.TimeUnit unit) { return null; }
}
