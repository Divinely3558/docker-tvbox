package android.text;

public final class TextUtils {
    private TextUtils() {}

    public static boolean isEmpty(CharSequence str) {
        return str == null || str.length() == 0;
    }

    public static int getTrimmedLength(CharSequence s) {
        if (s == null) return 0;
        int end = s.length();
        while (end > 0 && Character.isWhitespace(s.charAt(end - 1))) end--;
        return end;
    }

    public static CharSequence getCharSequence(CharSequence s) {
        return s;
    }

    public static CharSequence getCharSequence(CharSequence s, CharSequence defaultStr) {
        return s == null ? defaultStr : s;
    }

    public static boolean equals(CharSequence a, CharSequence b) {
        if (a == b) return true;
        if (a == null || b == null || a.length() != b.length()) return false;
        for (int i = 0; i < a.length(); i++) if (a.charAt(i) != b.charAt(i)) return false;
        return true;
    }

    public static String substring(String text, int start) {
        return text == null ? null : text.substring(Math.min(start, text.length()));
    }

    public static String substring(String text, int start, int end) {
        return text == null ? null : text.substring(start, end);
    }

    public static String[] split(String str, String separator) {
        if (str == null) return new String[0];
        return str.split(java.util.regex.Pattern.quote(separator == null ? "" : separator), -1);
    }

    public static String join(CharSequence delimiter, Object[] tokens) {
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (Object t : tokens) {
            if (!first) sb.append(delimiter);
            sb.append(t);
            first = false;
        }
        return sb.toString();
    }

    public static String join(CharSequence delimiter, Iterable<?> tokens) {
        StringBuilder sb = new StringBuilder();
        boolean first = true;
        for (Object t : tokens) {
            if (!first) sb.append(delimiter);
            sb.append(t);
            first = false;
        }
        return sb.toString();
    }

    public static String getReverse(String text) {
        return text == null ? null : new StringBuilder(text).reverse().toString();
    }

    public static void throwIfEmpty(String str, String message) {
        if (isEmpty(str)) throw new IllegalArgumentException(message);
    }

    public static boolean isNumeric(CharSequence cs) {
        if (isEmpty(cs)) return false;
        int len = cs.length();
        for (int i = 0; i < len; i++) if (!Character.isDigit(cs.charAt(i))) return false;
        return true;
    }

    public enum Trimester {
        ONE(1), TWO(2), THREE(3);

        public final int size;

        Trimester(int size) { this.size = size; }
    }
}
