package android.content.res;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * 只读 AssetManager：从 spider jar 里读取 assets/*。
 *
 * 加固 jar（guard）里的 native 代码会通过 JNI 反射调用 {@code open}，
 * 因此不能返回 null，必须提供一个和 Android 签名一致的实现。
 */
public class AssetManager {

    private final File container;

    public AssetManager() {
        String jar = System.getProperty("spider.jar", "");
        this.container = jar.isEmpty() ? null : new File(jar);
    }

    public InputStream open(String fileName) throws IOException {
        return open(fileName, 1);
    }

    public InputStream open(String fileName, int mode) throws IOException {
        if (container == null || !container.isFile()) throw new FileNotFoundException(fileName);
        final ZipFile zip = new ZipFile(container);
        String entry = fileName.startsWith("assets/") ? fileName : "assets/" + fileName;
        ZipEntry found = zip.getEntry(entry);
        if (found == null) {
            zip.close();
            throw new FileNotFoundException(entry);
        }
        final InputStream in = zip.getInputStream(found);
        return new FilterInputStream(in) {
            @Override
            public void close() throws IOException {
                super.close();
                zip.close();
            }
        };
    }

    public String[] list(String path) throws IOException {
        if (container == null || !container.isFile()) return new String[0];
        String prefix = (path == null || path.isEmpty()) ? "" : (path.endsWith("/") ? path : path + "/");
        try (ZipFile zip = new ZipFile(container)) {
            return zip.stream()
                    .map(e -> e.getName())
                    .filter(name -> name.startsWith(prefix))
                    .map(name -> name.substring(prefix.length()))
                    .filter(name -> !name.isEmpty() && !name.contains("/"))
                    .distinct()
                    .toArray(String[]::new);
        }
    }

    public void close() {
    }
}
