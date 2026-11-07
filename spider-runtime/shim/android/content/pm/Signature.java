package android.content.pm;

public class Signature {
    private final byte[] bytes;
    public Signature(byte[] bytes) { this.bytes = bytes == null ? new byte[0] : bytes; }
    public byte[] toByteArray() { return bytes; }
    public String toCharsString() {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) sb.append(String.format("%02x", b));
        return sb.toString();
    }
    @Override public String toString() { return toCharsString(); }
}
