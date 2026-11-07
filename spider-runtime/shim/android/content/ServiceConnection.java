package android.content;

public interface ServiceConnection {
    public void onServiceConnected(android.content.ComponentName n, android.os.IBinder s);
    public void onServiceDisconnected(android.content.ComponentName n);
}
