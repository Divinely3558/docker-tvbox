package com.docktvbox.shim;

import android.content.SharedPreferences;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** File-backed SharedPreferences: one java properties file per name under <base>/shared_prefs. */
public class Prefs implements SharedPreferences {

    private static final Map<String, Prefs> CACHE = new ConcurrentHashMap<>();

    private final File file;
    private final Map<String, String> data = new LinkedHashMap<>();

    public static Prefs of(File baseDir, String name) {
        String key = baseDir.getAbsolutePath() + "|" + name;
        return CACHE.computeIfAbsent(key, k -> new Prefs(new File(baseDir, "shared_prefs/" + name + ".xml")));
    }

    private Prefs(File file) {
        this.file = file;
        if (file.isFile()) {
            try (Reader r = new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8)) {
                Properties p = new Properties();
                p.load(r);
                for (String k : p.stringPropertyNames()) data.put(k, p.getProperty(k));
            } catch (IOException ignored) {}
        }
    }

    private synchronized void save() {
        file.getParentFile().mkdirs();
        Properties p = new Properties();
        data.forEach(p::setProperty);
        try (Writer w = new OutputStreamWriter(new FileOutputStream(file), StandardCharsets.UTF_8)) {
            p.store(w, "spider-runtime");
        } catch (IOException ignored) {}
    }

    @Override public synchronized Map<String, ?> getAll() { return new LinkedHashMap<>(data); }
    @Override public synchronized String getString(String k, String d) { return data.containsKey(k) ? data.get(k) : d; }
    @Override public synchronized Set<String> getStringSet(String k, Set<String> d) {
        String v = data.get(k);
        if (v == null) return d;
        Set<String> out = new LinkedHashSet<>();
        for (String part : v.split("\u0001", -1)) if (!part.isEmpty()) out.add(part);
        return out;
    }
    @Override public synchronized int getInt(String k, int d) { return (int) read(k, d); }
    @Override public synchronized long getLong(String k, long d) { return read(k, d); }
    @Override public synchronized float getFloat(String k, float d) { return (float) read(k, (double) d); }
    @Override public synchronized boolean getBoolean(String k, boolean d) {
        String v = data.get(k);
        return v == null ? d : ("1".equals(v) || "true".equalsIgnoreCase(v));
    }
    @Override public synchronized boolean contains(String k) { return data.containsKey(k); }
    @Override public Editor edit() { return new Edit(); }
    @Override public void registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l) {}
    @Override public void unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l) {}

    private long read(String k, long d) {
        String v = data.get(k);
        if (v == null) return d;
        try { return (long) Double.parseDouble(v); } catch (NumberFormatException e) { return d; }
    }

    private double read(String k, double d) {
        String v = data.get(k);
        if (v == null) return d;
        try { return Double.parseDouble(v); } catch (NumberFormatException e) { return d; }
    }

    private class Edit implements Editor {
        private final Map<String, String> pending = new LinkedHashMap<>();
        private final Set<String> removed = new LinkedHashSet<>();
        private boolean clearAll;

        private Editor put(String k, String v) { pending.put(k, v); removed.remove(k); return this; }

        @Override public Editor putString(String k, String v) { return k == null || v == null ? this : put(k, v); }
        @Override public Editor putInt(String k, int v) { return put(k, Integer.toString(v)); }
        @Override public Editor putLong(String k, long v) { return put(k, Long.toString(v)); }
        @Override public Editor putFloat(String k, float v) { return put(k, Float.toString(v)); }
        @Override public Editor putBoolean(String k, boolean v) { return put(k, v ? "true" : "false"); }
        @Override public Editor putStringSet(String k, Set<String> v) {
            return v == null ? this : put(k, TextUtils.join("\u0001", v));
        }
        @Override public Editor remove(String k) { removed.add(k); pending.remove(k); return this; }
        @Override public Editor clear() { clearAll = true; return this; }

        @Override public synchronized boolean commit() {
            if (clearAll) data.clear();
            removed.forEach(data::remove);
            data.putAll(pending);
            save();
            return true;
        }

        @Override public void apply() { commit(); }

        private static final class TextUtils {
            static String join(String d, Collection<String> v) {
                StringBuilder sb = new StringBuilder();
                for (String s : v) { if (sb.length() > 0) sb.append(d); sb.append(s); }
                return sb.toString();
            }
        }
    }
}
