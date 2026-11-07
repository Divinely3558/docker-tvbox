package android.text;

public interface Editable extends CharSequence {
    Editable append(CharSequence text);
    Editable replace(int st, int en, CharSequence source);
    void clear();
}
