package android.view;

public class ViewTreeObserver {
    public void addOnGlobalLayoutListener(android.view.ViewTreeObserver.OnGlobalLayoutListener l) {}
    public void removeOnGlobalLayoutListener(android.view.ViewTreeObserver.OnGlobalLayoutListener l) {}

    public static interface OnGlobalLayoutListener {
        public void onGlobalLayout();
    }
}
