package com.docktvbox.spider;

import android.content.Context;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONObject;

import com.google.gson.JsonArray;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.lang.reflect.Array;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Persistent dex->JVM spider host. One JSON request per stdin line, one JSON response per stdout line.
 */
public class Runner {

    private static final Map<String, URLClassLoader> LOADERS = new ConcurrentHashMap<>();
    private static final Map<String, Object> INSTANCES = new ConcurrentHashMap<>();
    private static final java.util.Set<String> ORIGIN_READY = ConcurrentHashMap.newKeySet();
    private static Context context;
    private static Path outDir;
    /** What the browser used to reach us; spiders build local-proxy URLs out of it. */
    private static volatile String baseUrl = System.getProperty("spider.base.url", "");
    private static final com.github.catvod.crawler.SpiderApi API = new HostApi();

    public static void main(String[] args) throws Exception {
        String dataDir = System.getProperty("spider.data.dir", "./.spider");
        outDir = Paths.get(System.getProperty("spider.out.dir", dataDir + "/out"));
        Files.createDirectories(outDir);
        Files.createDirectories(Paths.get(dataDir));
        context = new TestContext();

        java.io.BufferedReader in = new java.io.BufferedReader(new java.io.InputStreamReader(System.in, StandardCharsets.UTF_8));
        java.io.PrintWriter out = new java.io.PrintWriter(new java.io.OutputStreamWriter(System.out, StandardCharsets.UTF_8), true);
        // Spiders log to stdout; hijack it so only the JSON-line protocol reaches the caller.
        System.setOut(new java.io.PrintStream(new java.io.FileOutputStream(java.io.FileDescriptor.err), true));
        out.println("{\"ok\":true,\"ready\":true}");
        out.flush();

        String line;
        while ((line = in.readLine()) != null) {
            if (line.isBlank()) continue;
            long t0 = System.currentTimeMillis();
            JSONObject req;
            try {
                req = new JSONObject(line);
            } catch (Exception e) {
                out.println("{\"ok\":false,\"error\":\"bad request: " + escape(String.valueOf(line)) + "\"}");
                continue;
            }
            String resp = handle(req);
            Log.d("spider-perf", req.optString("method") + " " + req.optString("api") + " -> " + (System.currentTimeMillis() - t0) + "ms");
            out.println(resp);
            out.flush();
            if (req.optBoolean("exit")) break;
        }
        System.exit(0);
    }

    private static String handle(JSONObject req) {
        try {
            String jar = req.optString("jar", System.getProperty("spider.jar", ""));
            URLClassLoader loader = loaderFor(jar);
            String cls = resolveClass(req.optString("api", req.optString("cls", "")), loader);
            if (cls.isEmpty()) throw new IllegalArgumentException("no api class");
            String method = req.optString("method", "homeContent");
            boolean fresh = req.optBoolean("fresh", false);
            String base = req.optString("base", "");
            if (!base.isEmpty()) {
                baseUrl = trimTrailingSlash(base);
                // 供 com.github.catvod.spider.Proxy 构造对浏览器可达的本地代理地址
                System.setProperty("spider.base.url", baseUrl);
            }

            initOrigin(loader, jar);
            Class<?> type = Class.forName(cls, true, loader);
            String key = jar + "|" + cls + "|" + req.optString("ext", "") + "|" + req.optString("flag", "");
            String siteKey = cls.startsWith("csp_") ? cls.substring(4) : simpleName(cls);
            Object spider = fresh ? null : INSTANCES.get(key);
            if (spider == null) {
                spider = type.getDeclaredConstructor().newInstance();
                injectField(spider, "siteKey", siteKey);
                String extend = req.optString("ext", "");
                invokeInit(spider, extend);
                if (!fresh) INSTANCES.put(key, spider);
            }
            // Re-injected on every request: spiders cache the address, and the origin can change.
            invokeInitApi(spider, siteKey);

            JSONArray args = req.optJSONArray("args");
            if (args == null) args = new JSONArray();
            if (method.equals("proxy") || method.equals("proxyLocal")) {
                Map<String, String> params = new LinkedHashMap<>();
                JSONObject p = req.optJSONObject("params");
                if (p != null) for (Iterator<String> it = p.keys(); it.hasNext(); ) { String k = it.next(); params.put(k, p.optString(k)); }
                return result(req, invokeProxy(spider, method, params));
            }
            if (method.equals("init")) return result(req, (Object) null);

            Object r = call(spider, method, args, req);
            return result(req, r);
        } catch (InvocationTargetException e) {
            return error(req, e.getCause() == null ? e : e.getCause());
        } catch (Throwable t) {
            return error(req, t);
        }
    }

    /** catvod packs spiders as com.github.catvod.spider.X referenced from config as csp_X */
    private static String resolveClass(String api, ClassLoader loader) {
        if (api.isEmpty()) return api;
        String cls = api.contains(".")
                ? api
                : "com.github.catvod.spider." + api.substring(api.startsWith("csp_") ? 4 : 0);
        // 加固 jar 的配置写的是外层 XxxGuard，解包后的内层 jar 只有真实类 Xxx。
        if (loader != null && cls.endsWith("Guard") && !exists(cls, loader)) {
            String inner = cls.substring(0, cls.length() - "Guard".length());
            if (exists(inner, loader)) return inner;
        }
        return cls;
    }

    private static boolean exists(String cls, ClassLoader loader) {
        try {
            Class.forName(cls, false, loader);
            return true;
        } catch (ClassNotFoundException | LinkageError e) {
            return false;
        }
    }

    /**
     * 一些新版 catvod spider 依赖 ``com.github.catvod.spider.InitOrigin.init(context)``
     * 初始化全局上下文；jar 里有这个类时先调用一次（best-effort，失败不阻断）。
     */
    private static void initOrigin(ClassLoader loader, String jar) {
        if (loader == null || !ORIGIN_READY.add(jar)) return;
        try {
            Class<?> origin = Class.forName("com.github.catvod.spider.InitOrigin", false, loader);
            Method init = origin.getMethod("init", Context.class);
            init.invoke(null, context);
            Log.d("spider-init", "InitOrigin.init ok for " + jar);
        } catch (ClassNotFoundException ignored) {
            // 普通 jar 没有 InitOrigin，保持静默。
        } catch (Throwable t) {
            // 只尝试一次：InitOrigin 里可能带联网自检，失败也不该每个请求重试。
            Throwable cause = t.getCause() == null ? t : t.getCause();
            Log.d("spider-init", "InitOrigin.init failed for " + jar + ": " + cause);
        }
    }

    private static String simpleName(String cls) {
        int i = cls.lastIndexOf('.');
        String s = i < 0 ? cls : cls.substring(i + 1);
        return s.toLowerCase();
    }

    private static URLClassLoader loaderFor(String jar) throws Exception {
        String cp = System.getProperty("java.class.path");
        List<URL> urls = new ArrayList<>();
        if (!jar.isEmpty()) urls.add(new File(jar).toURI().toURL());
        String libs = System.getProperty("spider.lib.dir", "");
        if (!libs.isEmpty()) {
            File[] fs = new File(libs).listFiles((d, n) -> n.endsWith(".jar"));
            if (fs != null) for (File f : fs) urls.add(f.toURI().toURL());
        }
        String key = String.valueOf(urls);
        URLClassLoader old = LOADERS.get(key);
        if (old != null) return old;
        // Parent must not see the spider jar: shim classes live in the app classpath only.
        URLClassLoader loader = new URLClassLoader(urls.toArray(new URL[0]), Runner.class.getClassLoader());
        LOADERS.put(key, loader);
        return loader;
    }

    private static void injectField(Object spider, String name, Object value) {
        try {
            Class<?> c = spider.getClass();
            while (c != null) {
                try {
                    java.lang.reflect.Field f = c.getDeclaredField(name);
                    f.setAccessible(true);
                    if (f.get(spider) == null) f.set(spider, value);
                    return;
                } catch (NoSuchFieldException ignored) {
                }
                c = c.getSuperclass();
            }
        } catch (Throwable ignored) {
        }
    }

    /** catvod gives spiders the host callbacks either through the 1-arg or the 2-arg overload. */
    private static void invokeInitApi(Object spider, String siteKey) {
        try {
            Method two = spider.getClass().getMethod("initApi", com.github.catvod.crawler.SpiderApi.class, String.class);
            two.setAccessible(true);
            two.invoke(spider, API, siteKey);
            return;
        } catch (NoSuchMethodException ignored) {
        } catch (Exception e) {
            Log.d("spider-api", "initApi(api, key) failed: " + e);
        }
        try {
            Method one = spider.getClass().getMethod("initApi", com.github.catvod.crawler.SpiderApi.class);
            one.setAccessible(true);
            one.invoke(spider, API);
        } catch (NoSuchMethodException ignored) {
        } catch (Exception e) {
            Log.d("spider-api", "initApi(api) failed: " + e);
        }
    }

    private static String trimTrailingSlash(String url) {
        int end = url.length();
        while (end > 0 && url.charAt(end - 1) == '/') end--;
        return url.substring(0, end);
    }

    private static void invokeInit(Object spider, String extend) throws Exception {
        try {
            Method m = spider.getClass().getMethod("init", Context.class, String.class);
            m.invoke(spider, context, extend);
        } catch (NoSuchMethodException e) {
            spider.getClass().getMethod("init", Context.class).invoke(spider, context);
        }
    }

    private static Object call(Object spider, String method, JSONArray args, JSONObject req) throws Exception {
        Class<?> c = spider.getClass();
        Throwable last = null;
        for (Method m : visibleMethods(c)) {
            if (!m.getName().equals(method) || m.getParameterCount() != args.length()) continue;
            try {
                Object[] argv = coerce(m, args, req);
                if (argv == null) continue;
                m.setAccessible(true);
                return m.invoke(spider, argv);
            } catch (IllegalArgumentException e) {
                last = e;
            } catch (InvocationTargetException e) {
                throw e;
            }
        }
        if (last != null) throw new InvocationTargetException(last);
        throw new NoSuchMethodException(c.getName() + "." + method + "/" + args.length());
    }

    private static List<Method> visibleMethods(Class<?> c) {
        List<Method> all = new ArrayList<>();
        for (Class<?> k = c; k != null; k = k.getSuperclass()) {
            try {
                for (Method m : k.getDeclaredMethods()) if (!m.isSynthetic()) all.add(m);
            } catch (Throwable ignored) {
            }
        }
        return all;
    }

    private static Object[] coerce(Method m, JSONArray args, JSONObject req) {
        Class<?>[] pts = m.getParameterTypes();
        Object[] out = new Object[pts.length];
        for (int i = 0; i < pts.length; i++) {
            Object a = args.opt(i);
            Class<?> p = pts[i];
            if (p == boolean.class || p == Boolean.class) {
                if (!(a instanceof Boolean)) return null;
                out[i] = a;
            } else if (p == int.class || p == Integer.class) {
                if (!(a instanceof Number)) return null;
                out[i] = ((Number) a).intValue();
            } else if (p == String.class) {
                if (a instanceof JSONObject) return null;
                out[i] = a == null ? null : String.valueOf(a);
                if (out[i].equals("null")) out[i] = null;
            } else if (List.class.isAssignableFrom(p)) {
                List<String> list = new ArrayList<>();
                if (a instanceof JSONArray) {
                    JSONArray arr = (JSONArray) a;
                    for (int j = 0; j < arr.length(); j++) list.add(arr.optString(j));
                } else if (a instanceof String) {
                    list.add((String) a);
                } else if (a == null) {
                    return null;
                }
                out[i] = list;
            } else if (Map.class.isAssignableFrom(p)) {
                Map<String, String> map = new HashMap<>();
                if (a instanceof JSONObject) {
                    JSONObject o = (JSONObject) a;
                    for (Iterator<String> it = o.keys(); it.hasNext(); ) { String k = it.next(); map.put(k, o.optString(k)); }
                }
                out[i] = map;
            } else if (p.isArray()) {
                if (!(a instanceof JSONArray)) return null;
                JSONArray arr = (JSONArray) a;
                Object java = Array.newInstance(p.getComponentType(), arr.length());
                for (int j = 0; j < arr.length(); j++) Array.set(java, j, arr.opt(j));
                out[i] = java;
            } else {
                return null;
            }
        }
        return out;
    }

    private static JSONObject invokeProxy(Object spider, String method, Map<String, String> params) throws Exception {
        Object[] r;
        try {
            Method m = spider.getClass().getMethod(method, Map.class);
            m.setAccessible(true);
            r = (Object[]) m.invoke(spider, params);
        } catch (NoSuchMethodException e) {
            Method m = spider.getClass().getMethod("proxy", Map.class);
            m.setAccessible(true);
            r = (Object[]) m.invoke(spider, params);
        }
        JSONObject o = new JSONObject();
        o.put("kind", "proxy");
        if (r == null) {
            o.put("code", 404);
            o.put("body", "");
            return o;
        }
        o.put("code", r.length > 0 && r[0] instanceof Integer ? r[0] : 200);
        JSONObject headers = new JSONObject();
        if (r.length > 1 && r[1] instanceof Map) for (Map.Entry<?, ?> e : ((Map<?, ?>) r[1]).entrySet()) headers.put(String.valueOf(e.getKey()), e.getValue());
        o.put("headers", headers);
        if (r.length > 2) o.put("body", dumpBody(r[2]));
        return o;
    }

    private static Object dumpBody(Object body) throws Exception {
        if (body == null) return "";
        if (body instanceof byte[]) return save((byte[]) body);
        if (body instanceof InputStream) {
            InputStream in = (InputStream) body;
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) bos.write(buf, 0, n);
            in.close();
            return save(bos.toByteArray());
        }
        return String.valueOf(body);
    }

    private static Object save(byte[] data) throws Exception {
        String name = "body-" + System.nanoTime() + ".bin";
        Path p = outDir.resolve(name);
        Files.write(p, data);
        JSONObject o = new JSONObject();
        o.put("path", p.toString());
        o.put("bytes", data.length);
        if (data.length < 4096) {
            String s = new String(data, StandardCharsets.UTF_8);
            if (s.startsWith("{") || s.startsWith("[") || s.startsWith("<")) o.put("preview", s);
        }
        return o;
    }

    private static String result(JSONObject req, Object r) throws Exception {
        JSONObject o = new JSONObject();
        o.put("id", req.opt("id"));
        o.put("ok", true);
        if (r == null) o.put("result", JSONObject.NULL);
        else if (r instanceof String) o.put("result", r);
        else if (r instanceof JSONObject) o.put("result", r);
        else if (r instanceof JSONArray) o.put("result", r);
        else if (r instanceof Map) o.put("result", new JSONObject((Map<?, ?>) r));
        else if (r instanceof List) o.put("result", new JSONArray((List<?>) r));
        else if (r instanceof Boolean) o.put("result", r);
        else o.put("result", String.valueOf(r));
        return o.toString();
    }

    private static String error(JSONObject req, Throwable t) {
        StringBuilder sb = new StringBuilder();
        for (Throwable c = t; c != null; c = c.getCause()) {
            sb.append(c.getClass().getName()).append(": ").append(c.getMessage());
            if (c.getCause() != null) sb.append(" | caused by ");
        }
        for (StackTraceElement e : t.getStackTrace()) {
            if (sb.length() > 1200) break;
            sb.append("\n  at ").append(e);
        }
        JSONObject o = new JSONObject();
        try {
            o.put("id", req.opt("id"));
            o.put("ok", false);
            o.put("error", escape(sb.toString()));
        } catch (Exception ignored) {
            return "{\"ok\":false}";
        }
        return o.toString();
    }

    private static String escape(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default: if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
            }
        }
        return b.toString();
    }

    /** Minimal Context: the shim supplies storage; spiders only need file paths and package info. */
    static class TestContext extends android.app.Application {
    }

    /**
     * Host side of the catvod SpiderApi contract. Sniffing (webParse), batched requests
     * (multiReq) and subtitle conversion need the player, which we do not have: they log
     * and come back empty so the spider keeps going without that extra.
     */
    static class HostApi implements com.github.catvod.crawler.SpiderApi {

        @Override public String getAddress(boolean ipv4) {
            return baseUrl;
        }

        @Override public String getPort() {
            try {
                java.net.URI uri = java.net.URI.create(baseUrl);
                int port = uri.getPort();
                if (port > 0) return String.valueOf(port);
                return "https".equalsIgnoreCase(uri.getScheme()) ? "443" : "80";
            } catch (Exception e) {
                return "80";
            }
        }

        @Override public int getScreenOrientation() {
            return 0;
        }

        @Override public void log(String content) {
            Log.d("spider", content);
        }

        @Override public String webParse(String url, String ext) {
            Log.d("spider-api", "webParse needs a browser: " + url);
            return "";
        }

        @Override public String multiReq(JsonArray requests) {
            Log.d("spider-api", "multiReq is not implemented: " + requests);
            return "";
        }

        @Override public String lrcToSrt(String lrc) {
            return "";
        }
    }
}
