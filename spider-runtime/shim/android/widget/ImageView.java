package android.widget;

public class ImageView extends android.view.View {
    public void setImageDrawable(android.graphics.drawable.Drawable d) {}
    public void setImageBitmap(android.graphics.Bitmap b) {}
    public void setScaleType(android.widget.ImageView.ScaleType s) {}

    public static enum ScaleType {
        MATRIX, FIT_XY, FIT_START, FIT_CENTER, FIT_END, CENTER, CENTER_CROP, CENTER_INSIDE;
    }
}
