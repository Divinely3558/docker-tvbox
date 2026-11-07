package android.os;

public class Build {
    public static String BOARD = "web";
    public static String BOOTLOADER = "unknown";
    public static String BRAND = "OnePlus";
    public static String DEVICE = "MT2110";
    public static String DISPLAY = "QP1A.220714.015";
    public static String FINGERPRINT = "web";
    public static String HARDWARE = "web";
    public static String ID = "web";
    public static String MANUFACTURER = "OnePlus";
    public static String MODEL = "MT2110";
    public static String PRODUCT = "yingmi-web";
    public static String SERIAL = "000000";
    public static String TAG = "Build";
    public static String CPU_ABI = "arm64-v8a";
    public static String CPU_ABI2 = "";
    public static String[] SUPPORTED_ABIS = {"arm64-v8a", "armeabi-v7a", "armeabi"};

    public static class VERSION {
        public static String CODENAME = "Base";
        public static String INCREMENTAL = "release-keys";
        public static String RELEASE = "14";
        public static int SDK_INT = 34;
        public static boolean isEngBuild() { return false; }
        public static boolean isUserBuild() { return true; }
    }

    public static class VERSION_CODES {
        public static final int BASE = 1, LOLLIPOP = 21, MARSHMALLOW = 23, N = 24, O = 26, P = 28, Q = 29, R = 30, S = 31, TIRAMISU = 33, UPSIDE_DOWN_CAKE = 34;
    }
}
