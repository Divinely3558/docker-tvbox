package android.content;

import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.res.Resources;
import android.net.wifi.WifiManager;
import android.view.LayoutInflater;
import com.docktvbox.shim.Prefs;
import java.io.*;

public class Context {

    public static final int MODE_PRIVATE = 0;
    public static final int MODE_WORLD_READABLE = 1;
    public static final int MODE_WORLD_WRITEABLE = 2;
    public static final int MODE_APPEND = 0x0100;
    public static final int MODE_MULTI_PROCESS = 0x0004;
    public static final int MODE_ENABLE_WRITE_AHEAD_LOGGING = 0x0008;
    public static final String WIFI_SERVICE = "wifi";
    public static final String CONNECTIVITY_SERVICE = "connectivity";
    public static final String CLIPBOARD_SERVICE = "clipboard";
    public static final String LAYOUT_INFLATER_SERVICE = "layout_inflater";
    public static final String AUDIO_SERVICE = "audio";
    public static final String WINDOW_SERVICE = "window";
    public static final String NOTIFICATION_SERVICE = "notification";
    public static final String POWER_SERVICE = "power";
    public static final int PERMISSION_GRANTED = 0;
    public static final int PERMISSION_DENIED = -1;

    private File baseDir;
    private String packageName = "com.qingsong.yingmi";

    public Context() { this(new File(System.getProperty("spider.data.dir", System.getProperty("user.dir") + "/.spider")), null); }

    public Context(File baseDir, String packageName) {
        this.baseDir = baseDir;
        if (packageName != null) this.packageName = packageName;
        baseDir.mkdirs();
    }

    public Context getApplicationContext() { return this; }
    public Context getBaseContext() { return this; }
    public String getPackageName() { return packageName; }

    private File sub(String name) {
        File d = new File(baseDir, name);
        d.mkdirs();
        return d;
    }

    public File getFilesDir() { return sub("files"); }
    public File getCacheDir() { return sub("cache"); }
    public File getCodeCacheDir() { return sub("code_cache"); }
    public File getNoBackupFilesDir() { return sub("no_backup"); }
    public File getExternalCacheDir() { return sub("external_cache"); }
    public File getExternalFilesDir(String type) { return sub("external_files" + (type == null ? "" : "/" + type)); }
    public File getDir(String name, int mode) { return sub("app_" + name); }
    public File getDatabasePath(String name) { return new File(sub("databases"), name); }

    public SharedPreferences getSharedPreferences(String name, int mode) { return Prefs.of(baseDir, name); }

    public ApplicationInfo getApplicationInfo() {
        ApplicationInfo info = new ApplicationInfo();
        info.packageName = packageName;
        info.dataDir = baseDir.getAbsolutePath();
        info.sourceDir = baseDir.getAbsolutePath();
        info.targetSdkVersion = 28;
        return info;
    }

    public PackageManager getPackageManager() { return new PackageManager(this); }
    public Resources getResources() { return Resources.shared(); }
    public LayoutInflater getLayoutInflater() { return new LayoutInflater(this); }
    public Object getSystemService(String name) {
        if (WIFI_SERVICE.equals(name)) return new WifiManager();
        return null;
    }
    public String getSystemServiceName(Class<?> svc) { return svc == null ? null : svc.getSimpleName(); }
    public void startActivity(Intent intent) {}
    public void sendBroadcast(Intent intent) {}
    public Object registerReceiver(Object receiver, Object filter) { return null; }
    public void unregisterReceiver(Object receiver) {}
    public int checkSelfPermission(String permission) { return PERMISSION_GRANTED; }
    public int checkCallingOrSelfPermission(String permission) { return PERMISSION_GRANTED; }
    public String[] fileList() { return getFilesDir().list() == null ? new String[0] : getFilesDir().list(); }
    public boolean deleteFile(String name) { return new File(getFilesDir(), name).delete(); }
    public File getFileStreamPath(String name) { return new File(getFilesDir(), name); }
    public FileInputStream openFileInput(String name) throws FileNotFoundException { return new FileInputStream(new File(getFilesDir(), name)); }
    public FileOutputStream openFileOutput(String name, int mode) throws FileNotFoundException { return new FileOutputStream(new File(getFilesDir(), name)); }
    public boolean deleteDatabase(String name) { return getDatabasePath(name).delete(); }
    public String getString(int resId) { return ""; }
    public String getString(int resId, Object... args) { return ""; }
    public CharSequence getText(int resId) { return ""; }
    public int getColor(int resId) { return 0; }
    public Object getContentResolver() { return null; }
    public android.content.res.AssetManager getAssets() { return new android.content.res.AssetManager(); }
    public ClassLoader getClassLoader() { return Context.class.getClassLoader(); }
    public Object getMainLooper() { return android.os.Looper.getMainLooper(); }
}
