package android.graphics.drawable;

public class GradientDrawable extends android.graphics.drawable.Drawable {
    public GradientDrawable() {}
    public void setColor(int c) {}
    public void setCornerRadius(float r) {}
    public void setGradientType(int t) {}
    public void setOrientation(android.graphics.drawable.GradientDrawable.Orientation o) {}

    public static enum Orientation {
        TOP_BOTTOM, BOTTOM_TOP, LEFT_RIGHT, RIGHT_LEFT;
    }
}
