package android.widget;

public class RadioGroup extends android.widget.LinearLayout {
    public void setOnCheckedChangeListener(RadioGroup.OnCheckedChangeListener l) {}
    public int getCheckedRadioButtonId() { return -1; }

    public static interface OnCheckedChangeListener {
        public void onCheckedChanged(android.widget.RadioGroup g, int checkedId);
    }
}
