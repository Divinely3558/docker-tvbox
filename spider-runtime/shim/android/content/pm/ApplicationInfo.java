package android.content.pm;

public class ApplicationInfo extends PackageItemInfo {
    public static final int FLAG_SYSTEM = 0x00000001;
    public String dataDir;
    public String sourceDir;
    public String nativeLibraryDir;
    public int targetSdkVersion = 28;
    public int minSdkVersion = 21;
    public int flags;
    public long uid;
}
