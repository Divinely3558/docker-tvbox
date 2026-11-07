package android.content.pm;

import android.content.Context;
import android.content.Intent;
import java.util.ArrayList;
import java.util.List;

public class PackageManager {
    public static final int GET_META_DATA = 128;
    public static final int GET_PROVIDERS = 4096;
    public static final int MATCH_DEFAULT_ONLY = 65536;
    public static final int NAME_NOT_FOUND = 1;
    public static final String FEATURE_TOUCHSCREEN = "android.hardware.touchscreen";

    private final Context context;
    public PackageManager(Context context) { this.context = context; }

    public PackageInfo getPackageInfo(String packageName, int flags) throws NameNotFoundException {
        PackageInfo info = new PackageInfo();
        info.packageName = packageName;
        info.versionName = "2.6.5";
        info.versionCode = 265;
        info.applicationInfo = context.getApplicationInfo();
        return info;
    }

    public PackageInfo getPackageInfo(String packageName) throws NameNotFoundException { return getPackageInfo(packageName, 0); }

    public ApplicationInfo getApplicationInfo(String packageName, int flags) throws NameNotFoundException {
        return context.getApplicationInfo();
    }

    public boolean hasSystemFeature(String name) { return false; }
    public Intent getLaunchIntentForPackage(String packageName) { return new Intent(); }
    public ProviderInfo resolveContentProvider(String authority, int flags) { return null; }
    public List<PackageInfo> getInstalledPackages(int flags) { return new ArrayList<>(); }
    public String getPackageNameForUid(int uid) { return context.getPackageName(); }
    public int getUidForSharedUser(String sharedUserName) { return -1; }
    public String[] getPackagesForUid(int uid) { return new String[]{context.getPackageName()}; }
    public String getInstallerPackageName(String packageName) { return null; }
    public String resolveActivityInfo(Object info) { return null; }
    public Object getApplicationLabel(ApplicationInfo info) { return info.packageName; }
    public Object getInstantAppCookie() { return null; }

    public static class NameNotFoundException extends Exception {
        public NameNotFoundException() { super("package not found"); }
        public NameNotFoundException(String name) { super(name); }
    }
}
