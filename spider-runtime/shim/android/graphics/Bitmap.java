package android.graphics;

public class Bitmap {
    public void recycle() {}
    public int getWidth() { return 0; }
    public int getHeight() { return 0; }

    public static enum Config {
        ALPHA_8, RGB_565, ARGB_4444, ARGB_8888, RGBA_F16, HARDWARE;
    }
}
