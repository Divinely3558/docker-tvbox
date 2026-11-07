package android.graphics;

public class Paint {
    public Paint() {}
    public void setAntiAlias(boolean b) {}
    public void setColor(int c) {}
    public void setStyle(android.graphics.Paint.Style s) {}

    public static enum Style {
        FILL, STROKE, FILL_AND_STROKE;
    }
}
