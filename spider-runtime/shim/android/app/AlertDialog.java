package android.app;

public class AlertDialog extends android.app.Dialog {

    public static class Builder {
        public Builder(android.content.Context ctx) {}
        public Builder setTitle(CharSequence t) { return this; }
        public Builder setMessage(CharSequence t) { return this; }
        public Builder setView(android.view.View v) { return this; }
        public Builder setItems(CharSequence[] i, android.content.DialogInterface.OnClickListener l) { return this; }
        public Builder setPositiveButton(CharSequence t, android.content.DialogInterface.OnClickListener l) { return this; }
        public Builder setNegativeButton(CharSequence t, android.content.DialogInterface.OnClickListener l) { return this; }
        public Builder setOnKeyListener(android.view.View.OnKeyListener l) { return this; }
        public Builder setCancelable(boolean b) { return this; }
        public android.app.AlertDialog create() { return new android.app.AlertDialog(); }
        public android.app.AlertDialog show() { return new android.app.AlertDialog(); }
    }
}
