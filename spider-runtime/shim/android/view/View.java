package android.view;

public class View {
    public static final int VISIBLE = 0;
    public static final int INVISIBLE = 4;
    public static final int GONE = 8;
    public android.view.ViewGroup getParent() { return null; }
    public android.view.ViewTreeObserver getViewTreeObserver() { return new android.view.ViewTreeObserver(); }
    public android.content.Context getContext() { return null; }
    public android.view.View setVisibility(int v) { return this; }
    public android.view.View setPadding(int l, int t, int r, int b) { return this; }
    public android.view.View setBackground(android.graphics.drawable.Drawable d) { return this; }
    public android.view.View setOnClickListener(android.view.View.OnClickListener l) { return this; }
    public android.view.View setOnFocusChangeListener(android.view.View.OnFocusChangeListener l) { return this; }
    public android.view.View setOnKeyListener(android.view.View.OnKeyListener l) { return this; }
    public android.view.View setFocusable(boolean b) { return this; }
    public android.view.View setFocusableInTouchMode(boolean b) { return this; }
    public android.view.View requestFocus() { return this; }

    public static interface OnClickListener {
        public void onClick(android.view.View v);
    }

    public static interface OnFocusChangeListener {
        public void onFocusChange(android.view.View v, boolean has);
    }

    public static interface OnKeyListener {
        public boolean onKey(android.view.View v, int code, android.view.KeyEvent e);
    }

    public static interface OnApplyWindowInsetsListener {
        public android.view.WindowInsets onApplyWindowInsets(android.view.View v, android.view.WindowInsets i);
    }

    public static interface OnLongClickListener {
        public boolean onLongClick(android.view.View v);
    }

    public static interface OnTouchListener {
        public boolean onTouch(android.view.View v, android.view.MotionEvent e);
    }
}
