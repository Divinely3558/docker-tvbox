package android.util;

public final class Pair<F, S> {
    public final F first;
    public final S second;

    public Pair(F first, S second) { this.first = first; this.second = second; }

    public static <A, B> Pair<A, B> create(A a, B b) { return new Pair<>(a, b); }

    @Override public boolean equals(Object o) {
        return o instanceof Pair && java.util.Objects.equals(first, ((Pair<?, ?>) o).first)
                && java.util.Objects.equals(second, ((Pair<?, ?>) o).second);
    }

    @Override public int hashCode() { return java.util.Objects.hash(first, second) * 31; }

    @Override public String toString() { return "[" + first + ", " + second + "]"; }
}
