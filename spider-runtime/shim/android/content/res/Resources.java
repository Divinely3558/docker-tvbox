package android.content.res;

import android.graphics.drawable.Drawable;
import android.util.DisplayMetrics;

/** Resource lookup is a no-op: spiders only ever ask for metrics and identifier probes. */
public class Resources {

    private static final Resources SHARED = new Resources();

    private final DisplayMetrics metrics = new DisplayMetrics();
    private final Configuration configuration = new Configuration();

    public static Resources shared() { return SHARED; }

    public DisplayMetrics getDisplayMetrics() { return metrics; }

    public Configuration getConfiguration() { return configuration; }

    public String getText(int id) { return ""; }

    public String getString(int id) { return ""; }

    public String getString(int id, Object... formatArgs) { return ""; }

    public int getColor(int id) { return 0; }

    public int getColor(int id, Theme theme) { return 0; }

    public ColorStateList getColorStateList(int id) { return null; }

    public float getDimension(int id) { return 0f; }

    public int getDimensionPixelOffset(int id) { return 0; }

    public int getDimensionPixelSize(int id) { return 0; }

    public Drawable getDrawable(int id) { return null; }

    public Drawable getDrawable(int id, Theme theme) { return null; }

    public XmlResourceParser getLayout(int id) { return null; }

    public XmlResourceParser getAnimation(int id) { return null; }

    public int getIdentifier(String name, String defType, String defPackage) { return 0; }

    public static class Theme {
        public void obtainStyledAttributes(int[] attrs) {}

        public void applyStyle(int resId, boolean force) {}

        public ColorStateList getColorStateList(int index) { return null; }

        public int getColor(int index) { return 0; }

        public Drawable getDrawable(int index) { return null; }
    }

    public static class NotFoundException extends RuntimeException {
        public NotFoundException(String name) { super(name); }

        public NotFoundException(String name, Throwable cause) { super(name, cause); }
    }
}
