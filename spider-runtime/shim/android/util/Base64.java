package android.util;

import java.nio.charset.StandardCharsets;

/** Android Base64 flags mapped onto java.util.Base64. */
public final class Base64 {
    public static final int DEFAULT = 0;
    public static final int NO_PADDING = 1;
    public static final int NO_WRAP = 2;
    public static final int CRLF = 4;
    public static final int URL_SAFE = 8;
    public static final int SIMULTANEOUS = 16;
    public static final int NO_CLOSE = 32;

    private Base64() {}

    private static java.util.Base64.Encoder encoder(int flags) {
        java.util.Base64.Encoder e = (flags & URL_SAFE) != 0
                ? java.util.Base64.getUrlEncoder() : java.util.Base64.getEncoder();
        if ((flags & NO_PADDING) != 0) e = e.withoutPadding();
        return e;
    }

    private static java.util.Base64.Decoder decoder(int flags) {
        return (flags & URL_SAFE) != 0 ? java.util.Base64.getUrlDecoder() : java.util.Base64.getMimeDecoder();
    }

    public static byte[] encode(byte[] input, int flags) {
        return encoder(flags).encode(input);
    }

    public static String encodeToString(byte[] input, int flags) {
        return new String(encoder(flags).encode(input), StandardCharsets.US_ASCII);
    }

    public static byte[] decode(String str, int flags) {
        return decoder(flags).decode(str.replaceAll("\\s", ""));
    }

    public static byte[] decode(byte[] input, int flags) {
        return decode(new String(input, StandardCharsets.US_ASCII), flags);
    }

    public static byte[] decode(byte[] input, int flags, int offset, int outputLen) {
        byte[] all = decode(new String(input, offset, outputLen, StandardCharsets.US_ASCII), flags);
        return all;
    }

    public static int decode(String str, byte[] output, int outputOffset, int flags) {
        byte[] d = decode(str, flags);
        System.arraycopy(d, 0, output, outputOffset, Math.min(d.length, output.length - outputOffset));
        return d.length;
    }

    public static int encode(byte[] input, int flags, byte[] output, int outputOffset) {
        byte[] e = encoder(flags).encode(input);
        System.arraycopy(e, 0, output, outputOffset, e.length);
        return e.length;
    }

    public static Encoder encode(int flags) {
        java.util.Base64.Encoder enc = encoder(flags);
        return new Encoder() {
            @Override public void write(byte[] b) { buf.append(new String(b, StandardCharsets.ISO_8859_1)); }
            @Override public byte[] flush() { return new byte[0]; }
            private final StringBuilder buf = new StringBuilder();
        };
    }

    public abstract static class Encoder implements java.io.Closeable {
        public abstract void write(byte[] b);
        public abstract byte[] flush();
        @Override public void close() {}
    }
}
