package android.widget;

public class FrameLayout extends android.view.ViewGroup {
    public FrameLayout() {}
    public FrameLayout(android.content.Context c) {}

    public static class LayoutParams extends android.view.ViewGroup.MarginLayoutParams {
        public LayoutParams(int w, int h) { super(w, h); }
    }
}
