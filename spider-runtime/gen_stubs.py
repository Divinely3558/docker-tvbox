#!/usr/bin/env python3
"""Emit link-only Android/QuickJS stubs for running TVBox spider jars on a desktop JVM.

The spider bytecode references ~84 android.* types, but content spiders only execute
Base64 / TextUtils / Uri / Log / Context / SharedPreferences / Build / Handler / Wifi,
which are hand-written in shim/functional/. Everything generated here exists so that
class loading and linking succeed; calling into it returns a harmless default.
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "shim"

# Functional shims written by hand: generating an outer type here would replace its real body.
PROTECTED = {
    "android.app.Activity", "android.content.Context", "android.content.Intent",
    "android.content.SharedPreferences", "android.content.pm.ApplicationInfo",
    "android.content.pm.PackageInfo", "android.content.pm.PackageManager",
    "android.content.pm.PackageItemInfo", "android.content.pm.ProviderInfo",
    "android.content.pm.Signature", "android.content.res.Resources", "android.net.Uri",
    "android.net.wifi.WifiInfo", "android.net.wifi.WifiManager", "android.os.AsyncTask",
    "android.os.Build", "android.os.Bundle", "android.os.Environment", "android.os.Handler",
    "android.os.Looper", "android.os.SystemClock", "android.text.Editable",
    "android.text.TextUtils", "android.util.Base64", "android.util.DisplayMetrics",
    "android.util.Log", "android.util.Pair", "android.util.TypedValue",
    "android.view.LayoutInflater", "com.github.catvod.crawler.Spider",
    "com.github.catvod.crawler.SpiderDebug", "com.github.catvod.debug.MainActivity",
}

# fqn: (kind, superclass, nested_members)  kind in {class, interface, enum, annotation}
TYPES = {
    # ---- application framework (dialog / QR paths only) ----
    "android.app.Application": ("class", "android.content.Context", []),
    "android.app.Application$ActivityLifecycleCallbacks": ("interface", None, []),
    "android.app.Dialog": ("class", None, ["Dialog() {}", "Dialog(android.content.Context ctx) {}"]),
    "android.app.AlertDialog": ("class", "android.app.Dialog", []),
    "android.app.AlertDialog$Builder": ("class", None, [
        "Builder(android.content.Context ctx) {}",
        "Builder setTitle(CharSequence t) { return this; }",
        "Builder setMessage(CharSequence t) { return this; }",
        "Builder setView(android.view.View v) { return this; }",
        "Builder setItems(CharSequence[] i, android.content.DialogInterface$OnClickListener l) { return this; }",
        "Builder setPositiveButton(CharSequence t, android.content.DialogInterface$OnClickListener l) { return this; }",
        "Builder setNegativeButton(CharSequence t, android.content.DialogInterface$OnClickListener l) { return this; }",
        "Builder setOnKeyListener(android.view.View$OnKeyListener l) { return this; }",
        "Builder setCancelable(boolean b) { return this; }",
        "android.app.AlertDialog create() { return new android.app.AlertDialog(); }",
        "android.app.AlertDialog show() { return new android.app.AlertDialog(); }",
    ]),
    "android.app.ProgressDialog": ("class", "android.app.AlertDialog", []),
    "android.content.ContentProvider": ("class", None, []),
    "org.xmlpull.v1.XmlPullParser": ("interface", None, []),
    "android.content.DialogInterface": ("class", None, []),
    "android.content.DialogInterface$OnClickListener": ("interface", None, ["void onClick(android.content.DialogInterface d, int which);"]),
    "android.content.DialogInterface$OnCancelListener": ("interface", None, ["void onCancel(android.content.DialogInterface d);"]),
    "android.content.DialogInterface$OnDismissListener": ("interface", None, ["void onDismiss(android.content.DialogInterface d);"]),
    "android.content.DialogInterface$OnShowListener": ("interface", None, ["void onShow(android.content.DialogInterface d);"]),
    "android.content.ClipboardManager": ("class", None, ["android.content.ClipData getPrimaryClip() { return null; }", "void setPrimaryClip(android.content.ClipData d) {}"]),
    "android.content.ClipData": ("class", None, [
        "static ClipData newPlainText(String l, String t) { return new ClipData(); }",
        "String coerceToText(android.content.Context c) { return \"\"; }",
    ]),
    "android.content.res.ColorStateList": ("class", None, []),
    "android.content.res.XmlResourceParser": ("interface", "org.xmlpull.v1.XmlPullParser", []),
    # ---- graphics / view / widget ----
    "android.graphics.Bitmap": ("class", None, ["void recycle() {}", "int getWidth() { return 0; }", "int getHeight() { return 0; }"]),
    "android.graphics.Bitmap$Config": ("enum", None, ["ALPHA_8", "RGB_565", "ARGB_4444", "ARGB_8888", "RGBA_F16", "HARDWARE"]),
    "android.graphics.BitmapFactory": ("class", None, [
        "static Bitmap decodeByteArray(byte[] d, int o, int l) { return null; }",
        "static Bitmap decodeFile(String p) { return null; }"]),
    "android.graphics.Canvas": ("class", None, ["Canvas() {}", "Canvas(android.graphics.Bitmap b) {}",
                                                "void drawColor(int c) {}", "void drawPath(android.graphics.Path p, android.graphics.Paint k) {}"]),
    "android.graphics.Paint": ("class", None, ["Paint() {}", "void setAntiAlias(boolean b) {}",
                                               "void setColor(int c) {}", "void setStyle(android.graphics.Paint$Style s) {}"]),
    "android.graphics.Paint$Style": ("enum", None, ["FILL", "STROKE", "FILL_AND_STROKE"]),
    "android.graphics.Path": ("class", None, ["Path() {}", "void moveTo(float x, float y) {}", "void lineTo(float x, float y) {}",
                                              "void close() {}", "void reset() {}", "void setFillType(android.graphics.Path$FillType f) {}"]),
    "android.graphics.Path$FillType": ("enum", None, ["WINDING", "EVEN_ODD", "INVERSE_WINDING", "INVERSE_EVEN_ODD"]),
    "android.graphics.drawable.Drawable": ("class", None, ["void setBounds(int l, int t, int r, int b) {}",
                                                           "android.graphics.drawable.Drawable$ConstantState getConstantState() { return null; }"]),
    "android.graphics.drawable.Drawable$ConstantState": ("class", None, ["android.graphics.drawable.Drawable newDrawable() { return null; }"]),
    "android.graphics.drawable.BitmapDrawable": ("class", "android.graphics.drawable.Drawable", []),
    "android.graphics.drawable.ColorDrawable": ("class", "android.graphics.drawable.Drawable", ["ColorDrawable(int c) {}"]),
    "android.graphics.drawable.GradientDrawable": ("class", "android.graphics.drawable.Drawable", [
        "GradientDrawable() {}", "void setColor(int c) {}", "void setCornerRadius(float r) {}",
        "void setGradientType(int t) {}", "void setOrientation(android.graphics.drawable.GradientDrawable$Orientation o) {}"]),
    "android.graphics.drawable.GradientDrawable$Orientation": ("enum", None, ["TOP_BOTTOM", "BOTTOM_TOP", "LEFT_RIGHT", "RIGHT_LEFT"]),
    "android.graphics.drawable.StateListDrawable": ("class", "android.graphics.drawable.Drawable", []),
    "android.view.View": ("class", None, [
        "public static final int VISIBLE = 0;", "public static final int INVISIBLE = 4;", "public static final int GONE = 8;",
        "public android.view.ViewGroup getParent() { return null; }",
        "public android.view.ViewTreeObserver getViewTreeObserver() { return new android.view.ViewTreeObserver(); }",
        "public android.content.Context getContext() { return null; }",
        "public android.view.View setVisibility(int v) { return this; }",
        "public android.view.View setPadding(int l, int t, int r, int b) { return this; }",
        "public android.view.View setBackground(android.graphics.drawable.Drawable d) { return this; }",
        "public android.view.View setOnClickListener(android.view.View$OnClickListener l) { return this; }",
        "public android.view.View setOnFocusChangeListener(android.view.View$OnFocusChangeListener l) { return this; }",
        "public android.view.View setOnKeyListener(android.view.View$OnKeyListener l) { return this; }",
        "public android.view.View setFocusable(boolean b) { return this; }",
        "public android.view.View setFocusableInTouchMode(boolean b) { return this; }",
        "public android.view.View requestFocus() { return this; }",
    ]),
    "android.view.View$OnClickListener": ("interface", None, ["void onClick(android.view.View v);"]),
    "android.view.View$OnFocusChangeListener": ("interface", None, ["void onFocusChange(android.view.View v, boolean has);"]),
    "android.view.View$OnKeyListener": ("interface", None, ["boolean onKey(android.view.View v, int code, android.view.KeyEvent e);"]),
    "android.view.ViewGroup": ("class", "android.view.View", ["void addView(android.view.View c) {}", "void removeView(android.view.View c) {}",
                                                              "void removeAllViews() {}", "int getChildCount() { return 0; }"]),
    "android.view.ViewGroup$LayoutParams": ("class", None, ["public int width;", "public int height;",
                                                            "LayoutParams() {}", "LayoutParams(int w, int h) { width = w; height = h; }"]),
    "android.view.ViewGroup$MarginLayoutParams": ("class", "android.view.ViewGroup$LayoutParams", ["public int leftMargin;", "public int topMargin;",
                                                                                                   "public int rightMargin;", "public int bottomMargin;",
                                                                                                   "MarginLayoutParams() {}", "MarginLayoutParams(int w, int h) { super(w, h); }"]),
    "android.view.ViewParent": ("interface", None, []),
    "android.view.ViewTreeObserver": ("class", None, ["void addOnGlobalLayoutListener(android.view.ViewTreeObserver$OnGlobalLayoutListener l) {}",
                                                      "void removeOnGlobalLayoutListener(android.view.ViewTreeObserver$OnGlobalLayoutListener l) {}"]),
    "android.view.ViewTreeObserver$OnGlobalLayoutListener": ("interface", None, ["void onGlobalLayout();"]),
    "android.view.KeyEvent": ("class", None, ["public int getKeyCode() { return 0; }", "public int getAction() { return 0; }"]),
    "android.view.Window": ("class", None, []),
    "android.view.WindowManager": ("class", None, []),
    "android.view.WindowManager$LayoutParams": ("class", "android.view.ViewGroup$LayoutParams", ["public int flags;", "public int type;"]),
    "android.widget.TextView": ("class", "android.view.View", ["CharSequence getText() { return \"\"; }",
                                                               "void setText(CharSequence t) {}", "void setTextColor(int c) {}", "void setTextSize(float s) {}"]),
    "android.widget.EditText": ("class", "android.widget.TextView", ["void setHint(CharSequence h) {}"]),
    "android.widget.ImageView": ("class", "android.view.View", ["void setImageDrawable(android.graphics.drawable.Drawable d) {}",
                                                                "void setImageBitmap(android.graphics.Bitmap b) {}",
                                                                "void setScaleType(android.widget.ImageView$ScaleType s) {}"]),
    "android.widget.ImageView$ScaleType": ("enum", None, ["MATRIX", "FIT_XY", "FIT_START", "FIT_CENTER", "FIT_END", "CENTER", "CENTER_CROP", "CENTER_INSIDE"]),
    "android.widget.LinearLayout": ("class", "android.view.ViewGroup", ["LinearLayout() {}", "LinearLayout(android.content.Context c) {}", "void setOrientation(int o) {}"]),
    "android.widget.LinearLayout$LayoutParams": ("class", "android.view.ViewGroup$MarginLayoutParams", ["LayoutParams(int w, int h) { super(w, h); }"]),
    "android.widget.FrameLayout": ("class", "android.view.ViewGroup", ["FrameLayout() {}", "FrameLayout(android.content.Context c) {}"]),
    "android.widget.FrameLayout$LayoutParams": ("class", "android.view.ViewGroup$MarginLayoutParams", ["LayoutParams(int w, int h) { super(w, h); }"]),
    "android.widget.ScrollView": ("class", "android.view.ViewGroup", ["ScrollView(android.content.Context c) {}"]),
    "android.widget.HorizontalScrollView": ("class", "android.view.ViewGroup", ["HorizontalScrollView(android.content.Context c) {}"]),
    "android.widget.Toast": ("class", None, ["public static final int SHORT = 0;", "public static final int LONG = 1;",
                                             "static Toast makeText(android.content.Context c, CharSequence t, int l) { return new Toast(); }",
                                             "void show() {}"]),
    # ---- misc link-only ----
    "android.net.UrlQuerySanitizer": ("class", None, ["String getValue(String k) { return null; }"]),
    "com.whl.quickjs.wrapper.JSObject": ("class", None, []),
    "com.whl.quickjs.wrapper.JSArray": ("class", "com.whl.quickjs.wrapper.JSObject", []),
    "com.whl.quickjs.wrapper.QuickJSObject": ("class", "com.whl.quickjs.wrapper.JSObject", []),
    "com.whl.quickjs.wrapper.JSCallFunction": ("interface", None, ["Object call(Object... args);"]),
    "com.whl.quickjs.wrapper.JSMethod": ("annotation", None, []),
    "com.whl.quickjs.wrapper.QuickJSContext": ("class", None, [
        "static QuickJSContext create() { throw new UnsupportedOperationException(\"QuickJS runtime is not bundled; this spider needs a JS engine\"); }",
        "void destroy() {}", "com.whl.quickjs.wrapper.JSObject evaluate(String s) { throw new UnsupportedOperationException(); }",
        "com.whl.quickjs.wrapper.JSObject createObject() { throw new UnsupportedOperationException(); }",
        "void setGlobal(String k, Object v) {}", "void addOnConsoleListener(boolean b) {}",
        "com.whl.quickjs.wrapper.QuickJSContext$Console getConsole() { return null; }"]),
    "com.whl.quickjs.wrapper.QuickJSContext$Console": ("interface", None, []),
    "javax.annotation.Nullable": ("annotation", None, []),
    "javax.annotation.ParametersAreNonnullByDefault": ("annotation", None, []),

    # ---- extra types referenced by the 盒子迷 build (link-only: UI plumbing never executes) ----
    "android.widget.Button": ("class", "android.widget.TextView", ["Button() {}", "Button(android.content.Context ctx) {}"]),
    "android.widget.CompoundButton": ("class", "android.widget.Button", [
        "void setOnCheckedChangeListener(CompoundButton$OnCheckedChangeListener l) {}",
        "void setChecked(boolean b) {}", "boolean isChecked() { return false; }"]),
    "android.widget.CompoundButton$OnCheckedChangeListener": ("interface", None, [
        "void onCheckedChanged(android.widget.CompoundButton b, boolean checked);"]),
    "android.widget.RadioButton": ("class", "android.widget.CompoundButton", ["RadioButton(android.content.Context ctx) {}"]),
    "android.widget.RadioGroup": ("class", "android.widget.LinearLayout", [
        "void setOnCheckedChangeListener(RadioGroup$OnCheckedChangeListener l) {}", "int getCheckedRadioButtonId() { return -1; }"]),
    "android.widget.RadioGroup$OnCheckedChangeListener": ("interface", None, [
        "void onCheckedChanged(android.widget.RadioGroup g, int checkedId);"]),
    "android.graphics.drawable.InsetDrawable": ("class", "android.graphics.drawable.Drawable", [
        "InsetDrawable(android.graphics.drawable.Drawable d, int l, int t, int r, int b) {}"]),
    "android.graphics.drawable.LayerDrawable": ("class", "android.graphics.drawable.Drawable", []),
    "android.graphics.drawable.RippleDrawable": ("class", "android.graphics.drawable.Drawable", [
        "RippleDrawable(int c, android.graphics.drawable.Drawable d) {}",
        "RippleDrawable(android.content.res.ColorStateList c, android.graphics.drawable.Drawable d) {}"]),
    "android.graphics.drawable.Icon": ("class", None, []),
    "android.graphics.Color": ("class", None, [
        "public static final int BLACK = 0xFF000000;", "public static final int WHITE = 0xFFFFFFFF;",
        "public static final int TRANSPARENT = 0;", "public static final int RED = 0xFFFF0000;",
        "public static final int GREEN = 0xFF00FF00;", "public static final int BLUE = 0xFF0000FF;",
        "public static final int GRAY = 0xFF888888;", "public static final int LTGRAY = 0xFFCCCCCC;",
        "public static final int DKGRAY = 0xFF444444;", "public static final int YELLOW = 0xFFFFFF00;",
        "public static final int CYAN = 0xFF00FFFF;", "public static final int MAGENTA = 0xFFFF00FF;",
        "static int parseColor(String s) { return BLACK; }", "static int argb(int a, int r, int g, int b) { return a; }",
        "static int rgb(int r, int g, int b) { return 0; }", "static int alpha(int c) { return 255; }",
        "static int red(int c) { return 0; }", "static int green(int c) { return 0; }", "static int blue(int c) { return 0; }",
        "static boolean colorSpaceAgnostic(int c) { return true; }"]),
    "android.graphics.Rect": ("class", None, ["public int left;", "public int top;", "public int right;", "public int bottom;",
        "Rect() {}", "Rect(int l, int t, int r, int b) { left = l; top = t; right = r; bottom = b; }",
        "int width() { return right - left; }", "int height() { return bottom - top; }"]),
    "android.graphics.Insets": ("class", None, ["public int left;", "public int top;", "public int right;", "public int bottom;"]),
    "android.graphics.Outline": ("class", None, []),
    "android.graphics.Typeface": ("class", None, [
        "public static final int NORMAL = 0, BOLD = 1, ITALIC = 2, BOLD_ITALIC = 3;",
        "public static final Typeface DEFAULT = null;", "public static final Typeface DEFAULT_BOLD = null;",
        "public static final Typeface MONOSPACE = null;", "public static final Typeface SANS_SERIF = null;",
        "public static final Typeface SERIF = null;",
        "static Typeface create(Typeface f, int style) { return null; }",
        "static Typeface createFromArray(Typeface[] a, int s, android.content.res.Resources r) { return null; }",
        "static Typeface createFromAsset(android.content.res.Resources r, String p) { return null; }",
        "static Typeface createFromFile(String p) { return null; }"]),
    "android.graphics.PorterDuff$Mode": ("enum", None, ["CLEAR", "SRC", "DST", "SRC_OVER", "DST_OVER", "SRC_IN", "DST_IN",
        "SRC_OUT", "DST_OUT", "SRC_ATOP", "DST_ATOP", "XOR", "PLUS", "MODULATE"]),
    "android.util.AttributeSet": ("interface", None, []),
    "android.util.SparseArray": ("class", None, ["int size() { return 0; }", "Object get(int k) { return null; }",
        "Object get(int k, Object d) { return d; }", "void put(int k, Object v) {}", "void delete(int k) {}",
        "Object valueAt(int i) { return null; }", "int keyAt(int i) { return 0; }", "void clear() {}"]),
    "android.util.SparseIntArray": ("class", None, ["int size() { return 0; }", "int get(int k) { return 0; }",
        "int get(int k, int d) { return d; }", "void put(int k, int v) {}", "int keyAt(int i) { return 0; }",
        "int valueAt(int i) { return 0; }", "void clear() {}"]),
    "android.util.Size": ("class", None, ["Size(int w, int h) {}", "int getWidth() { return 0; }", "int getHeight() { return 0; }"]),
    "android.util.SizeF": ("class", None, ["SizeF(float w, float h) {}", "float getWidth() { return 0; }", "float getHeight() { return 0; }"]),
    "android.util.Range": ("class", None, []),
    "android.util.Half": ("class", None, []),
    "android.os.Message": ("class", None, ["public int what;", "public int arg1;", "public int arg2;", "public Object obj;",
        "android.os.Handler target;", "Runnable callback;",
        "Message() {}", "static Message obtain() { return new Message(); }", "static Message obtain(android.os.Handler h) { Message m = new Message(); m.target = h; return m; }",
        "static Message obtain(android.os.Handler h, int what) { Message m = obtain(h); m.what = what; return m; }",
        "static Message obtain(android.os.Handler h, int what, Object obj) { Message m = obtain(h, what); m.obj = obj; return m; }",
        "static Message obtain(android.os.Handler h, int what, int arg1, int arg2) { Message m = obtain(h, what); m.arg1 = arg1; m.arg2 = arg2; return m; }",
        "android.os.Handler getTarget() { return target; }",
        "void setTarget(android.os.Handler h) { target = h; }",
        "Runnable getCallback() { return callback; }",
        "void recycle() {}",
        "void sendToTarget() { if (target != null) target.sendMessage(this); }"]),
    "android.os.HandlerThread": ("class", None, ["HandlerThread(String name) {}", "HandlerThread(String name, int priority) {}",
        "void start() {}", "android.os.Looper getLooper() { return android.os.Looper.getMainLooper(); }",
        "android.os.Handler getThreadHandler() { return null; }", "boolean quit() { return true; }",
        "boolean quitSafely() { return true; }"]),
    "android.os.Process": ("class", None, ["static int myPid() { return 1; }", "static int myTid() { return 1; }",
        "static int myUid() { return 0; }", "static void setThreadPriority(int p) {}", "static int getThreadPriority() { return 0; }"]),
    "android.os.LocaleList": ("class", None, ["LocaleList() {}", "LocaleList(java.util.Locale[] l) {}",
        "int size() { return 0; }", "java.util.Locale get(int i) { return java.util.Locale.CHINA; }"]),
    "android.content.res.Configuration": ("class", None, ["public int densityDpi;", "public float fontScale;",
        "public int orientation;", "public java.util.Locale locale;"]),
    "android.content.pm.SigningInfo": ("class", None, ["android.content.pm.Signature[] getApkContentsSigners() { return new android.content.pm.Signature[0]; }"]),
    "android.text.TextPaint": ("class", "android.graphics.Paint", []),
    "android.text.StaticLayout": ("class", None, []),
    "android.text.TextDirectionHeuristic": ("interface", None, []),
    "android.view.MotionEvent": ("class", None, ["public static final int ACTION_DOWN = 0;", "public static final int ACTION_UP = 1;",
        "public static final int ACTION_MOVE = 2;", "public static final int ACTION_CANCEL = 3;",
        "float getX() { return 0; }", "float getY() { return 0; }", "int getAction() { return 0; }"]),
    "android.view.Menu": ("interface", None, []),
    "android.view.MenuItem": ("interface", None, []),
    "android.view.View$OnApplyWindowInsetsListener": ("interface", None, [
        "android.view.WindowInsets onApplyWindowInsets(android.view.View v, android.view.WindowInsets i);"]),
    "android.view.View$OnLongClickListener": ("interface", None, ["boolean onLongClick(android.view.View v);"]),
    "android.view.View$OnTouchListener": ("interface", None, ["boolean onTouch(android.view.View v, android.view.MotionEvent e);"]),
    "android.view.WindowInsets": ("class", None, ["int getSystemWindowInsetLeft() { return 0; }", "int getSystemWindowInsetTop() { return 0; }",
        "int getSystemWindowInsetRight() { return 0; }", "int getSystemWindowInsetBottom() { return 0; }"]),
    "android.app.ActivityManager": ("class", None, []),
    "android.app.ActivityManager$RunningAppProcessInfo": ("class", None, ["public int processName_;"]),
    "android.app.Fragment": ("class", None, []),
    "android.app.DialogFragment": ("class", "android.app.Fragment", []),
    "android.app.PendingIntent": ("class", None, []),
    "android.app.Notification": ("class", None, []),
    "android.app.NotificationChannel": ("class", None, ["NotificationChannel(String id, CharSequence name, int importance) {}"]),
    "android.app.NotificationManager": ("class", None, ["void createNotificationChannel(android.app.NotificationChannel c) {}",
        "void notify(int id, android.app.Notification n) {}", "void cancel(int id) {}"]),
    "android.location.Location": ("class", None, []),
    "android.content.BroadcastReceiver": ("class", None, ["void onReceive(android.content.Context c, android.content.Intent i) {}"]),
    "android.content.IntentFilter": ("class", None, ["IntentFilter() {}", "IntentFilter(String a) {}"]),
    "android.content.ContextWrapper": ("class", "android.content.Context", ["ContextWrapper(android.content.Context base) {}"]),
    "android.content.ServiceConnection": ("interface", None, ["void onServiceConnected(android.content.ComponentName n, android.os.IBinder s);",
        "void onServiceDisconnected(android.content.ComponentName n);"]),
    "android.content.ComponentName": ("class", None, ["ComponentName(String p, String c) {}", "String getPackageName() { return p; }",
        "String getClassName() { return c; }", "public String p;", "public String c;"]),
    "android.os.IBinder": ("interface", None, []),
    "android.os.Parcel": ("class", None, ["void writeString(String s) {}", "String readString() { return null; }",
        "void writeInt(int v) {}", "int readInt() { return 0; }"]),
    "android.os.Parcelable": ("interface", None, []),
    "android.os.Parcelable$Creator": ("interface", None, ["Object createFromParcel(android.os.Parcel p);",
        "Object[] newArray(int size);"]),
    "com.google.zxing.BarcodeFormat": ("enum", None, ["QR_CODE", "CODE_128", "EAN_13"]),
}


def split_fqn(fqn):
    head, _, tail = fqn.rpartition("$")
    pkg, cls = head.split("$")[0], None
    if not head:
        return fqn.rsplit(".", 1)
    return fqn.replace("$", ".").rsplit(".", 1)


def render(fqn, kind, sup, members):
    *_, pkg = [fqn]
    package = fqn.split("$")[0].rsplit(".", 1)[0]
    name = simple(fqn)
    decl = {"class": "public class", "interface": "public interface",
            "enum": "public enum", "annotation": "public @interface"}[kind]
    ext = ""
    if kind == "class" and sup:
        ext = " extends " + sup
    if kind == "interface" and sup:
        ext = " extends " + sup
    lines = [f"package {package};", "", f"{decl} {name}{ext} {{"]
    if kind == "enum":
        lines.append("    " + ", ".join(members) + ";")
    else:
        for m in members:
            lines.append("    public " + m if m.startswith(("static", "void", "int", "boolean", "char", "byte", "long", "float", "double", "String", "Object")) and "(" in m and "{" not in m and ";" not in m else "    " + m)
    lines.append("}")
    return "\n".join(lines) + "\n"


def publicize(m):
    # Stub members are written unprefixed; link-only shims must still be callable across packages.
    if m.startswith(("public", "private", "protected", "@", "/*", "//")):
        return m
    return "public " + m


def dotted(text):
    # Java has no Outer$Inner type syntax: rewrite nested references, qualified and bare.
    for key in sorted(TYPES, key=len, reverse=True):
        if "$" not in key:
            continue
        text = text.replace(key, key.replace("$", "."))
        tail = key.split(".")[-1]
        text = text.replace(tail, tail.replace("$", "."))
    return text


def simple(fqn):
    return fqn.rsplit("$", 1)[-1].rsplit(".", 1)[-1]


def outer(fqn):
    return fqn.split("$")[0]


def main():
    groups = {}
    for fqn, (kind, sup, members) in TYPES.items():
        groups.setdefault(outer(fqn), []).append((fqn, kind, sup, members))
    count = 0
    for fqn, entries in groups.items():
        if fqn in PROTECTED:
            continue
        package = fqn.rsplit(".", 1)[0]
        top_name = simple(fqn)
        top = [e for e in entries if e[0] == fqn]
        nested = [e for e in entries if e[0] != fqn]
        body_lines = []
        kind, sup, members = (top[0][1], top[0][2], top[0][3]) if top else ("class", None, [])
        decl = {"class": "public class", "interface": "public interface",
                "enum": "public enum", "annotation": "public @interface"}[kind]
        ext = (" extends " + sup) if sup and kind in ("class", "interface") else ""
        body_lines.append(f"{decl} {top_name}{ext} {{")
        if kind == "enum":
            body_lines.append("    " + ", ".join(members) + ";")
        else:
            body_lines += ["    " + publicize(m) for m in members]
        for nfqn, nkind, nsup, nmem in nested:
            nname = nfqn.rsplit("$", 1)[-1]
            static = "static " if kind == "class" else ""
            ndef = {"class": f"public {static}class", "interface": f"public {static}interface",
                    "enum": f"public {static}enum", "annotation": f"public @interface"}[nkind]
            next_ = (" extends " + nsup) if nsup and nkind in ("class", "interface") else ""
            body_lines.append("")
            body_lines.append(f"    {ndef} {nname}{next_} {{")
            if nkind == "enum":
                body_lines.append("        " + ", ".join(nmem) + ";")
            else:
                body_lines += ["        " + publicize(m) for m in nmem]
            body_lines.append("    }")
        body_lines.append("}")
        path = OUT / (fqn.replace(".", "/") + ".java")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = dotted("\n".join(["package " + package + ";", ""] + body_lines) + "\n")
        path.write_text(text)
        count += 1
    print(f"stub files written: {count}")


if __name__ == "__main__":
    main()
