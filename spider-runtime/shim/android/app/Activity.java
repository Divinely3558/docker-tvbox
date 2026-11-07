package android.app;

import android.content.Context;
import android.content.Intent;
import android.view.View;
import android.view.Window;
import java.io.File;

public class Activity extends Context {
    private boolean finished;

    public View findViewById(int id) { return new View(); }
    public void setContentView(int layoutResID) {}
    public void setContentView(View v) {}
    public Window getWindow() { return new Window(); }
    public void finish() { finished = true; }
    public boolean isFinishing() { return finished; }
    public boolean isDestroyed() { return finished; }
    public void startActivity(Intent intent) {}
    public int requestPermissions(String[] permissions, int requestCode) { return -1; }
    public boolean checkPermission(String permission, int pid, int uid) { return true; }
    public void runOnUiThread(Runnable r) { r.run(); }
    public Object getIntent() { return null; }
    public Object getSupportFragmentManager() { return null; }
    public File getCacheDir() { return super.getCacheDir(); }
}
