package android.widget;

import android.content.Context;

public class ProgressBar {

    private int progress;
    private int max = 100;

    public ProgressBar() {
    }

    public ProgressBar(Context context) {
    }

    public ProgressBar(Context context, android.util.AttributeSet attrs) {
    }

    public void setProgress(int progress) { this.progress = progress; }

    public int getProgress() { return progress; }

    public void setMax(int max) { this.max = max; }

    public int getMax() { return max; }

    public void setVisibility(int visibility) {
    }
}
