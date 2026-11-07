package android.view;

public class ViewGroup extends android.view.View {
    public void addView(android.view.View c) {}
    public void removeView(android.view.View c) {}
    public void removeAllViews() {}
    public int getChildCount() { return 0; }

    public static class LayoutParams {
        public int width;
        public int height;
        public LayoutParams() {}
        public LayoutParams(int w, int h) { width = w; height = h; }
    }

    public static class MarginLayoutParams extends android.view.ViewGroup.LayoutParams {
        public int leftMargin;
        public int topMargin;
        public int rightMargin;
        public int bottomMargin;
        public MarginLayoutParams() {}
        public MarginLayoutParams(int w, int h) { super(w, h); }
    }
}
