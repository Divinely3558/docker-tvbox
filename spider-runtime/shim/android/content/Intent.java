package android.content;

import android.net.Uri;
import java.util.HashMap;
import java.util.Map;

public class Intent {
    public static final int FLAG_ACTIVITY_NEW_TASK = 0x10000000;
    private String action;
    private Uri data;
    private String type;
    private final Map<String, Object> extras = new HashMap<>();

    public Intent() {}
    public Intent(String action) { this.action = action; }
    public Intent(Context ctx, Class<?> target) {}
    public Intent(String action, Uri uri) { this.action = action; this.data = uri; }

    public Intent setAction(String a) { this.action = a; return this; }
    public String getAction() { return action; }
    public Intent setData(Uri u) { this.data = u; return this; }
    public Uri getData() { return data; }
    public Intent setDataAndType(Uri u, String t) { this.data = u; this.type = t; return this; }
    public Intent setType(String t) { this.type = t; return this; }
    public String getType() { return type; }
    public Intent setClassName(String pkg, String cls) { return this; }
    public Intent setClassName(Context c, Class<?> cls) { return this; }
    public Intent setComponent(Object component) { return this; }
    public Intent addFlags(int f) { return this; }
    public Intent addCategory(String c) { return this; }
    public Intent putExtra(String k, String v) { extras.put(k, v); return this; }
    public Intent putExtra(String k, int v) { extras.put(k, v); return this; }
    public Intent putExtra(String k, boolean v) { extras.put(k, v); return this; }
    public Intent putExtra(String k, long v) { extras.put(k, v); return this; }
    public String getDataString() { return data == null ? null : data.toString(); }
    public Object getExtra(String k) { return extras.get(k); }
    public String getStringExtra(String k) { Object v = extras.get(k); return v == null ? null : v.toString(); }
    public int getIntExtra(String k, int d) { Object v = extras.get(k); return v instanceof Number ? ((Number) v).intValue() : d; }
    public boolean getBooleanExtra(String k, boolean d) { Object v = extras.get(k); return v instanceof Boolean ? (Boolean) v : d; }
}
