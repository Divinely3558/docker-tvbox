package android.graphics;

public class Color {
    public static final int BLACK = 0xFF000000;
    public static final int WHITE = 0xFFFFFFFF;
    public static final int TRANSPARENT = 0;
    public static final int RED = 0xFFFF0000;
    public static final int GREEN = 0xFF00FF00;
    public static final int BLUE = 0xFF0000FF;
    public static final int GRAY = 0xFF888888;
    public static final int LTGRAY = 0xFFCCCCCC;
    public static final int DKGRAY = 0xFF444444;
    public static final int YELLOW = 0xFFFFFF00;
    public static final int CYAN = 0xFF00FFFF;
    public static final int MAGENTA = 0xFFFF00FF;
    public static int parseColor(String s) { return BLACK; }
    public static int argb(int a, int r, int g, int b) { return a; }
    public static int rgb(int r, int g, int b) { return 0; }
    public static int alpha(int c) { return 255; }
    public static int red(int c) { return 0; }
    public static int green(int c) { return 0; }
    public static int blue(int c) { return 0; }
    public static boolean colorSpaceAgnostic(int c) { return true; }
}
