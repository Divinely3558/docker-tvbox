package dalvik.system;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

/**
 * Android DexClassLoader 的占位实现。
 *
 * 加固 jar 的 native 代码会把解密出的 dex 写进临时目录，然后构造
 * {@code dalvik.system.DexClassLoader}。Android 在构造期就 mmap 并立刻删掉文件，
 * 所以这里在构造函数里先把文件复制到 {@code spider.capture}，供离线解包使用。
 */
public class DexClassLoader extends ClassLoader {

    public final String dexPath;
    public final String optimizedDirectory;
    public final String librarySearchPath;

    public DexClassLoader(String dexPath, String optimizedDirectory, String librarySearchPath, ClassLoader parent) {
        super(parent);
        this.dexPath = dexPath;
        this.optimizedDirectory = optimizedDirectory;
        this.librarySearchPath = librarySearchPath;
        String out = System.getProperty("spider.capture", "");
        if (!out.isEmpty() && dexPath != null) {
            Path source = Paths.get(dexPath);
            if (Files.isRegularFile(source)) {
                try {
                    Files.copy(source, Paths.get(out), StandardCopyOption.REPLACE_EXISTING);
                } catch (Throwable ignored) {
                    // 捕获失败不影响主流程，Runner 会看到空文件并给出明确错误。
                }
            }
        }
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        throw new ClassNotFoundException(name);
    }
}
