package com.whl.quickjs.wrapper;

public class QuickJSContext {
    public static QuickJSContext create() { throw new UnsupportedOperationException("QuickJS runtime is not bundled; this spider needs a JS engine"); }
    public void destroy() {}
    public com.whl.quickjs.wrapper.JSObject evaluate(String s) { throw new UnsupportedOperationException(); }
    public com.whl.quickjs.wrapper.JSObject createObject() { throw new UnsupportedOperationException(); }
    public void setGlobal(String k, Object v) {}
    public void addOnConsoleListener(boolean b) {}
    public com.whl.quickjs.wrapper.QuickJSContext.Console getConsole() { return null; }

    public static interface Console {
    }
}
