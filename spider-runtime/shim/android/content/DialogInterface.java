package android.content;

public class DialogInterface {

    public static interface OnClickListener {
        public void onClick(android.content.DialogInterface d, int which);
    }

    public static interface OnCancelListener {
        public void onCancel(android.content.DialogInterface d);
    }

    public static interface OnDismissListener {
        public void onDismiss(android.content.DialogInterface d);
    }

    public static interface OnShowListener {
        public void onShow(android.content.DialogInterface d);
    }
}
