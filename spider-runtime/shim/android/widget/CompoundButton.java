package android.widget;

public class CompoundButton extends android.widget.Button {
    public void setOnCheckedChangeListener(CompoundButton.OnCheckedChangeListener l) {}
    public void setChecked(boolean b) {}
    public boolean isChecked() { return false; }

    public static interface OnCheckedChangeListener {
        public void onCheckedChanged(android.widget.CompoundButton b, boolean checked);
    }
}
