package android.graphics;

public class Path {
    public Path() {}
    public void moveTo(float x, float y) {}
    public void lineTo(float x, float y) {}
    public void close() {}
    public void reset() {}
    public void setFillType(android.graphics.Path.FillType f) {}

    public static enum FillType {
        WINDING, EVEN_ODD, INVERSE_WINDING, INVERSE_EVEN_ODD;
    }
}
