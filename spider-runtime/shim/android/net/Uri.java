package android.net;

import java.io.File;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

/** Minimal android.net.Uri: enough for spider proxy URLs and query handling. */
public class Uri implements Comparable<Uri> {

    private final String scheme, authority, path, query, fragment, ssp;
    private final boolean opaque;

    private Uri(String scheme, String authority, String path, String query, String fragment, String ssp, boolean opaque) {
        this.scheme = scheme;
        this.authority = authority;
        this.path = path;
        this.query = query;
        this.fragment = fragment;
        this.ssp = ssp;
        this.opaque = opaque;
    }

    public static Uri parse(String uriString) {
        if (uriString == null) throw new NullPointerException("uriString");
        try {
            URI u = new URI(uriString);
            String scheme = u.getScheme();
            String authority = u.getRawAuthority();
            String path = u.getRawSchemeSpecificPart();
            if (scheme == null) return new Uri(null, null, null, null, null, uriString, false);
            String ssp = uriString.substring(scheme.length() + 1,
                    uriString.length() - (u.getRawFragment() == null ? 0 : u.getRawFragment().length() + 1));
            boolean opaque = authority == null && ssp != null && !ssp.startsWith("/");
            return new Uri(scheme, authority, u.getRawPath(), u.getRawQuery(), u.getRawFragment(), ssp, opaque);
        } catch (Exception e) {
            return new Uri(null, null, null, null, null, uriString, true);
        }
    }

    public static Uri fromFile(File file) {
        return new Uri("file", null, file.getAbsolutePath(), null, null, null, false);
    }

    public static String encode(String s) {
        return encode(s, " =:/?#[]@!$&'()*+,;%'\"<>{}|\\^`~%");
    }

    public static String encode(String s, String allow) {
        if (s == null) return null;
        StringBuilder out = new StringBuilder();
        for (byte b : s.getBytes(StandardCharsets.UTF_8)) {
            char c = (char) (b & 0xff);
            if (allow.indexOf(c) >= 0 || Character.isLetterOrDigit(c) || "-._~".indexOf(c) >= 0) out.append(c);
            else out.append(String.format("%%%02X", b & 0xff));
        }
        return out.toString();
    }

    public static String decode(String s) {
        if (s == null) return null;
        try {
            return java.net.URLDecoder.decode(s, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return s;
        }
    }

    public String getScheme() { return scheme; }

    public String getAuthority() { return authority; }

    public String getHost() {
        if (authority == null) return null;
        String a = authority;
        int at = a.lastIndexOf('@');
        if (at >= 0) a = a.substring(at + 1);
        int colon = a.lastIndexOf(':');
        if (colon > 0 && a.indexOf(']', colon) < 0) a = a.substring(0, colon);
        return a.isEmpty() ? null : a;
    }

    public int getPort() {
        if (authority == null) return -1;
        int colon = authority.lastIndexOf(':');
        if (colon < 0) return -1;
        try { return Integer.parseInt(authority.substring(colon + 1)); } catch (NumberFormatException e) { return -1; }
    }

    public String getPath() { return path == null ? null : decode(path); }

    public String getEncodedPath() { return path; }

    public String getRawPath() { return path; }

    public String getQuery() { return query == null ? null : decode(query); }

    public String getEncodedQuery() { return query; }

    public String getFragment() { return fragment; }

    public String getSchemeSpecificPart() { return ssp; }

    public boolean isOpaque() { return opaque; }

    public boolean isHierarchical() { return !opaque; }

    public String getLastPathSegment() {
        if (path == null) return null;
        String p = path.endsWith("/") ? path.substring(0, path.length() - 1) : path;
        int slash = p.lastIndexOf('/');
        return decode(slash < 0 ? p : p.substring(slash + 1));
    }

    public String getPathSegment(int index) {
        if (path == null) return null;
        String[] parts = path.split("/");
        int real = index;
        java.util.List<String> list = new java.util.ArrayList<>();
        for (String p : parts) if (!p.isEmpty()) list.add(p);
        return real < 0 || real >= list.size() ? null : decode(list.get(real));
    }

    public java.util.List<String> getPathSegments() {
        java.util.List<String> out = new java.util.ArrayList<>();
        if (path == null) return out;
        for (String p : path.split("/")) if (!p.isEmpty()) out.add(decode(p));
        return out;
    }

    public String getQueryParameter(String key) {
        Map<String, String> m = getQueryParameters();
        return m.get(key);
    }

    public String getQueryParameterOrDefault(String key, String def) {
        String v = getQueryParameter(key);
        return v == null ? def : v;
    }

    public java.util.Set<String> getQueryParameterNames() { return getQueryParameters().keySet(); }

    private Map<String, String> getQueryParameters() {
        Map<String, String> out = new LinkedHashMap<>();
        if (query == null) return out;
        for (String pair : query.split("&")) {
            if (pair.isEmpty()) continue;
            int eq = pair.indexOf('=');
            String k = eq < 0 ? pair : pair.substring(0, eq);
            String v = eq < 0 ? "" : pair.substring(eq + 1);
            out.putIfAbsent(decode(k), decode(v));
        }
        return out;
    }

    public Builder buildUpon() {
        Builder b = new Builder().scheme(scheme).authority(authority).path(path).query(query).fragment(fragment);
        if (opaque) b.ssp(ssp);
        return b;
    }

    public Uri withAppendedPath(String pathSegment) {
        return buildUpon().appendPath(pathSegment).build();
    }

    @Override public String toString() {
        StringBuilder sb = new StringBuilder();
        if (scheme != null) sb.append(scheme).append(':');
        if (opaque) return sb.append(ssp == null ? "" : ssp).toString();
        if (authority != null) sb.append("//").append(authority);
        if (path != null) sb.append(path);
        if (query != null) sb.append('?').append(query);
        if (fragment != null) sb.append('#').append(fragment);
        return sb.toString();
    }

    @Override public boolean equals(Object o) { return o instanceof Uri && toString().equals(o.toString()); }

    @Override public int hashCode() { return toString().hashCode(); }

    @Override public int compareTo(Uri other) { return toString().compareTo(other.toString()); }

    public static class Builder {
        private String scheme, authority, path, query, fragment, ssp;
        private boolean opaque;

        public Builder scheme(String scheme) { this.scheme = scheme; return this; }

        public Builder authority(String authority) { this.authority = authority; return this; }

        public Builder encodedAuthority(String authority) { this.authority = authority; return this; }

        public Builder userInfo(String userInfo) { this.authority = (authority == null ? "" : authority) ; return this; }

        public Builder path(String path) {
            this.path = path == null ? null : (path.isEmpty() ? "" : (path.startsWith("/") ? path : "/" + path));
            this.opaque = false;
            return this;
        }

        public Builder encodedPath(String path) { this.path = path; this.opaque = false; return this; }

        public Builder appendPath(String segment) {
            String s = encode(segment, "%/");
            path = path == null ? "/" + s : (path.endsWith("/") ? path + s : path + "/" + s);
            opaque = false;
            return this;
        }

        public Builder appendEncodedPath(String segment) {
            path = path == null ? "/" + segment : (path.endsWith("/") ? path + segment : path + "/" + segment);
            return this;
        }

        public Builder query(String query) { this.query = query; return this; }

        public Builder encodedQuery(String query) { this.query = query; return this; }

        public Builder appendQueryParameter(String key, String value) {
            String pair = encode(key, "%=") + "=" + encode(value, "%=");
            query = query == null || query.isEmpty() ? pair : query + "&" + pair;
            return this;
        }

        public Builder fragment(String fragment) { this.fragment = fragment; return this; }

        public Builder ssp(String ssp) { this.ssp = ssp; this.opaque = true; return this; }

        public Builder opaquePart(String ssp) { return ssp(ssp); }

        public Builder clearPath() { this.path = null; return this; }

        public Builder clearQuery() { this.query = null; return this; }

        public Builder fragment(int id) { return this; }

        public Uri build() {
            return new Uri(scheme, authority, path, query, fragment, ssp, opaque);
        }

        @Override public String toString() { return build().toString(); }
    }
}
