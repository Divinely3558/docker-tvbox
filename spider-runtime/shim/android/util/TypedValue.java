package android.util;

public final class TypedValue {
    public static final int COMPLEX_UNIT_PX = 0, COMPLEX_UNIT_DIP = 1, COMPLEX_UNIT_SP = 2;
    public static final int COMPLEX_UNIT_PT = 3, COMPLEX_UNIT_IN = 4, COMPLEX_UNIT_MM = 5;

    public static class Theme {}

    public static float applyDimension(int unit, float value, DisplayMetrics metrics) {
        float density = metrics == null ? 1f : metrics.density;
        float scaled = metrics == null ? 1f : metrics.scaledDensity;
        switch (unit) {
            case COMPLEX_UNIT_PX: return value;
            case COMPLEX_UNIT_DIP: return value * density;
            case COMPLEX_UNIT_SP: return value * scaled;
            case COMPLEX_UNIT_PT: return value * density * 0.75f;
            case COMPLEX_UNIT_IN: return value * density;
            case COMPLEX_UNIT_MM: return value * density * 0.0393701f;
            default: return value;
        }
    }
}
