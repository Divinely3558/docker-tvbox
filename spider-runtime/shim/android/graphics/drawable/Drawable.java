package android.graphics.drawable;

public class Drawable {
    public void setBounds(int l, int t, int r, int b) {}
    public android.graphics.drawable.Drawable.ConstantState getConstantState() { return null; }

    public static class ConstantState {
        public android.graphics.drawable.Drawable newDrawable() { return null; }
    }
}
