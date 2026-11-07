package android.view;

import android.content.Context;

public class LayoutInflater {
    private final Context context;
    public LayoutInflater(Context context) { this.context = context; }
    public static LayoutInflater from(Context c) { return new LayoutInflater(c); }
    public View inflate(int resource, Object root) { return new View(); }
    public View inflate(int resource, Object root, boolean attach) { return new View(); }
    public View inflate(org.xmlpull.v1.XmlPullParser parser, Object root) { return new View(); }
    public Context getContext() { return context; }
    public void setFactory(Object factory) {}
}
