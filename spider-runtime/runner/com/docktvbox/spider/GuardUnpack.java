package com.docktvbox.spider;

import android.content.Context;
import android.util.Log;

/**
 * 在 ARM JVM 里跑加固（guard）jar 的初始化，把解密出来的内层 dex 抢下来。
 *
 * 加固 jar 的外层类（``XxxGuard``）会调用 ``com.github.catvod.spider.Init``，
 * Init 再通过 ``DexNative.getLoader`` 解密 assets/*.guard 并构造 DexClassLoader。
 * 我们的 ``dalvik/system/DexClassLoader`` 桩会在构造时把文件复制到
 * ``-Dspider.capture=...`` 指定的位置，随后 native 代码删掉原文件也不影响。
 */
public class GuardUnpack {

    public static void main(String[] args) {
        try {
            run();
        } catch (Throwable t) {
            t.printStackTrace(System.out);
            // 壳的线程池不是 daemon，失败时不显式退出 JVM 会一直挂着
            System.exit(1);
        }
        // 成功也一样：壳可能留下常驻线程（如下载器），拿到 dex 后必须显式退出
        System.exit(0);
    }

    private static void run() throws Exception {
        String capture = System.getProperty("spider.capture", "");
        // catvod 的 Init.init 形参是 Application（Android 上 Context 的子类），
        // 传普通 Context 会在 native 侧被强制转换失败。
        Context context = new android.app.Application();
        System.out.println("guard-unpack context=" + context.getPackageName() + " capture=" + capture);

        Class<?> init = Class.forName("com.github.catvod.spider.Init");
        init.getMethod("init", Context.class).invoke(null, context);
        System.out.println("guard-unpack Init.init ok");

        Object loader = init.getMethod("loader").invoke(null);
        System.out.println("guard-unpack loader=" + loader);
        Log.d("guard-unpack", "loader=" + loader);

        java.io.File file = new java.io.File(capture);
        if (file.isFile() && file.length() > 0) {
            System.out.println("GUARD_CAPTURED " + capture + " bytes=" + file.length());
        } else {
            System.out.println("GUARD_CAPTURE_EMPTY " + capture);
            System.exit(2);
        }
    }
}
