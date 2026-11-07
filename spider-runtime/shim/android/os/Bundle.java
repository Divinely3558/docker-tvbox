package android.os;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class Bundle {
    private final Map<String, Object> map = new HashMap<>();
    public Bundle() {}
    public Bundle(Bundle o) { if (o != null) map.putAll(o.map); }
    public Bundle(int capacity) {}
    public void putString(String k, String v) { map.put(k, v); }
    public void putInt(String k, int v) { map.put(k, v); }
    public void putLong(String k, long v) { map.put(k, v); }
    public void putBoolean(String k, boolean v) { map.put(k, v); }
    public void putFloat(String k, float v) { map.put(k, v); }
    public String getString(String k) { Object v = map.get(k); return v == null ? null : v.toString(); }
    public String getString(String k, String d) { String v = getString(k); return v == null ? d : v; }
    public int getInt(String k) { Object v = map.get(k); return v instanceof Number ? ((Number) v).intValue() : 0; }
    public int getInt(String k, int d) { Object v = map.get(k); return v instanceof Number ? ((Number) v).intValue() : d; }
    public long getLong(String k) { Object v = map.get(k); return v instanceof Number ? ((Number) v).longValue() : 0L; }
    public boolean getBoolean(String k) { Object v = map.get(k); return v instanceof Boolean ? (Boolean) v : Boolean.parseBoolean(String.valueOf(v)); }
    public boolean getBoolean(String k, boolean d) { Object v = map.get(k); return v instanceof Boolean ? (Boolean) v : d; }
    public Object get(String k) { return map.get(k); }
    public boolean containsKey(String k) { return map.containsKey(k); }
    public Set<String> keySet() { return map.keySet(); }
    public int size() { return map.size(); }
    public boolean isEmpty() { return map.isEmpty(); }
    public void clear() { map.clear(); }
    public void remove(String k) { map.remove(k); }
    public String[] keyArray() { return map.keySet().toArray(new String[0]); }
}
