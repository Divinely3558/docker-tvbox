package android.os;

import java.io.File;

public final class Environment {
    public static final int MEDIA_MOUNTED = 1;
    public static final String DIRECTORY_DOWNLOADS = "Download";
    public static final String DIRECTORY_DCIM = "DCIM";
    public static final String DIRECTORY_MUSIC = "Music";
    public static final String DIRECTORY_PICTURES = "Pictures";
    public static final String DIRECTORY_MOVIES = "Movies";
    private Environment() {}
    public static File getExternalStorageDirectory() { return new File(System.getProperty("spider.data.dir", ".") + "/external"); }
    public static File getExternalStoragePublicDirectory(String type) { return new File(getExternalStorageDirectory(), type); }
    public static File getDataDirectory() { return new File(System.getProperty("spider.data.dir", ".")); }
    public static String getExternalStorageState() { return "mounted"; }
    public static boolean isExternalStorageEmulated() { return true; }
    public static boolean isExternalStorageRemovable() { return false; }
    public static File getRootDirectory() { return new File("/"); }
    public static boolean isSystemDirectory(File f) { return false; }
    public static boolean isExternalStorageAvailable() { return true; }
}
