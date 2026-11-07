package android.content.pm;

public class PackageInfo {
    public String packageName;
    public String versionName;
    public int versionCode;
    public ApplicationInfo applicationInfo;
    public ProviderInfo[] providers = new ProviderInfo[0];
    public Signature[] signatures = new Signature[0];
    public long firstInstallTime;
    public long lastUpdateTime;
}
