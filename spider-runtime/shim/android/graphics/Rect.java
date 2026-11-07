package android.graphics;

public class Rect {
    public int left;
    public int top;
    public int right;
    public int bottom;
    public Rect() {}
    public Rect(int l, int t, int r, int b) { left = l; top = t; right = r; bottom = b; }
    public int width() { return right - left; }
    public int height() { return bottom - top; }
}
