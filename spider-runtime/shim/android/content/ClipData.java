package android.content;

public class ClipData {
    public static ClipData newPlainText(String l, String t) { return new ClipData(); }
    public String coerceToText(android.content.Context c) { return ""; }
}
