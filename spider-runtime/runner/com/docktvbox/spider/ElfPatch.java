package com.docktvbox.spider;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * 运行期 ELF 修补（与 guard_unpack.patch_elf 同一套规则，纯 Java 版）。
 *
 * 有的加固壳不在 assets/*.so 里放 native 库，而是 init 时把 bionic 编译的 .so
 * 写到缓存目录再 System.load，预修补覆盖不到。ElfAgent 会在 Runtime.load0 入口
 * 先调这里的 {@link #patch(String)}：仅当检测到 bionic 标记（LIBC 版本依赖或
 * Android 专有 NEEDED）时才改写，glibc 自身的库一律原样跳过。
 */
public final class ElfPatch {

    private static final Set<String> ANDROID_ONLY = new HashSet<>(Arrays.asList(
            "liblog.so", "libandroid.so", "libGLESv2.so", "libEGL.so",
            "libOpenSLES.so", "libmediandk.so", "libnativewindow.so",
            "libjnigraphics.so", "libc++_shared.so"));

    private static final Set<Long> DROP_TAGS = new HashSet<>(Arrays.asList(
            0x6FFFFFFEL, // VERNEED
            0x6FFFFFFFL, // VERNEEDNUM
            0x6FFFFFFCL, // VERDEF
            0x6FFFFFFDL, // VERDEFNUM
            0x6FFFFFF0L, // VERSYM
            0x6FFFFFF9L  // RELACOUNT
    ));

    /** glibc 2.36 起移除的 FORTIFY 符号 → 普通函数。_chk 变体只是在签名尾部
     *  多个长度参数，AAPCS64 下多余实参被忽略，改指后语义安全。 */
    private static final String[] CHK_RENAME = {
            "__memcpy_chk", "memcpy",
            "__memmove_chk", "memmove",
            "__memset_chk", "memset",
            "__strlen_chk", "strlen",
            "__strcpy_chk", "strcpy",
            "__strncpy_chk", "strncpy",
            "__strcat_chk", "strcat",
            "__strncat_chk", "strncat",
            // arc4random_buf(buf, n) ≡ getentropy(buf, n)（int 返回值被 void 调用方忽略）
            "arc4random_buf", "getentropy",
    };

    private ElfPatch() {
    }

    public static void patch(String filename) {
        try {
            run(filename);
        } catch (Throwable ignored) {
            // 绝不能影响正常 System.load
        }
    }

    private static void run(String filename) throws Exception {
        if (filename == null || filename.isEmpty()) return;
        Path path = Paths.get(filename);
        if (!Files.isRegularFile(path)) return;
        byte[] data = Files.readAllBytes(path);
        // 小端 ELF64
        if (data.length < 64 || data[0] != 0x7f || data[1] != 'E' || data[2] != 'L' || data[3] != 'F') return;
        if (data[4] != 2 || data[5] != 1) return;

        long shoff = u64(data, 0x28);
        int shentsize = u16(data, 0x3A);
        int shnum = u16(data, 0x3C);
        int shstrndx = u16(data, 0x3E);
        if (shoff == 0 || shnum == 0 || shstrndx >= shnum) return;

        int[] sName = new int[shnum];
        long[] sOff = new long[shnum];
        long[] sSize = new long[shnum];
        for (int i = 0; i < shnum; i++) {
            int p = (int) (shoff + (long) i * shentsize);
            sName[i] = u32(data, p);
            sOff[i] = u64(data, p + 24);
            sSize[i] = u64(data, p + 32);
        }
        long strOff = sOff[shstrndx];
        int iDyn = -1, iDynstr = -1, iVer = -1, iVerR = -1;
        for (int i = 0; i < shnum; i++) {
            String name = cstr(data, strOff + sName[i]);
            if (".dynamic".equals(name)) iDyn = i;
            else if (".dynstr".equals(name)) iDynstr = i;
            else if (".gnu.version".equals(name)) iVer = i;
            else if (".gnu.version_r".equals(name)) iVerR = i;
        }
        if (iDyn < 0 || iDynstr < 0) return;
        int dynOff = (int) sOff[iDyn], dynSize = (int) sSize[iDyn];
        int strSecOff = (int) sOff[iDynstr], strSecSize = (int) sSize[iDynstr];

        // 只改有 bionic 标记的库：VERNaux 版本名 == "LIBC"，或 NEEDED 是 Android 专有
        boolean[] dropNeeded = new boolean[dynSize / 16];
        boolean androidNeeded = false;
        int n = 0;
        for (int p = dynOff; p + 16 <= dynOff + dynSize; p += 16, n++) {
            long tag = u64(data, p);
            if (tag == 0) break;
            if (tag == 1) { // DT_NEEDED
                int value = (int) u64(data, p + 8);
                String name = value >= 0 && value < strSecSize ? cstr(data, strSecOff + value) : "";
                if (ANDROID_ONLY.contains(name)) {
                    dropNeeded[n] = true;
                    androidNeeded = true;
                }
            }
        }
        boolean bionicVer = false;
        if (iVerR >= 0) {
            int vrOff = (int) sOff[iVerR];
            int end = vrOff + (int) sSize[iVerR];
            int p = vrOff;
            while (p + 16 <= end) {
                int vnCnt = u16(data, p + 2);
                int vnAux = u32(data, p + 8);
                int vnNext = u32(data, p + 12);
                int a = p + vnAux;
                for (int k = 0; k < vnCnt && a + 16 <= end; k++) {
                    int vnaName = u32(data, a + 8);
                    String ver = vnaName >= 0 && vnaName < strSecSize ? cstr(data, strSecOff + vnaName) : "";
                    if ("LIBC".equals(ver)) {
                        bionicVer = true;
                        break;
                    }
                    int vnaNext = u32(data, a + 12);
                    if (vnaNext == 0) break;
                    a += vnaNext;
                }
                if (bionicVer || vnNext == 0) break;
                p += vnNext;
            }
        }
        if (!bionicVer && !androidNeeded) return;

        // .gnu.version 全部置 1
        if (iVer >= 0) {
            int vOff = (int) sOff[iVer], vSize = (int) sSize[iVer];
            for (int p = vOff; p + 2 <= vOff + vSize; p += 2) {
                data[p] = 1;
                data[p + 1] = 0;
            }
        }
        // .gnu.version_r 留一个空 Verneed（version=1，其它全 0）
        if (iVerR >= 0) {
            int vrOff = (int) sOff[iVerR], vrSize = (int) sSize[iVerR];
            Arrays.fill(data, vrOff, vrOff + vrSize, (byte) 0);
            data[vrOff] = 1;
        }
        // .dynamic 去掉版本相关项与 Android 专有 NEEDED，后面的项前移
        long[][] entries = new long[dynSize / 16][];
        int m = 0, idx = 0;
        for (int p = dynOff; p + 16 <= dynOff + dynSize; p += 16, idx++) {
            long tag = u64(data, p);
            if (tag == 0) break;
            if (DROP_TAGS.contains(tag) || (tag == 1 && dropNeeded[idx])) continue;
            entries[m++] = new long[]{tag, u64(data, p + 8)};
        }
        for (int i = 0; i < dynSize / 16; i++) {
            w64(data, dynOff + i * 16, i < m ? entries[i][0] : 0);
            w64(data, dynOff + i * 16 + 8, i < m ? entries[i][1] : 0);
        }
        for (int i = 0; i < CHK_RENAME.length; i += 2) {
            renameSymbol(data, strSecOff, strSecOff + strSecSize, CHK_RENAME[i], CHK_RENAME[i + 1]);
        }
        path.toFile().setWritable(true, false);
        Files.write(path, data);
        System.out.println("elf-agent patched " + filename);
    }

    /** 把 .dynstr 里的完整 C 字符串 old 原地改写成更短的 new（等长覆盖，补 \0）。 */
    private static void renameSymbol(byte[] data, int from, int to, String oldName, String newName) {
        byte[] oldB = oldName.getBytes(StandardCharsets.US_ASCII);
        byte[] newB = newName.getBytes(StandardCharsets.US_ASCII);
        for (int i = from + 1; i + oldB.length + 1 <= to; i++) {
            if (data[i - 1] != 0) continue; // 必须是完整 C 字符串，不是子串
            int k = 0;
            while (k < oldB.length && data[i + k] == oldB[k]) k++;
            if (k < oldB.length || data[i + oldB.length] != 0) continue;
            System.arraycopy(newB, 0, data, i, newB.length);
            data[i + newB.length] = 0;
        }
    }

    private static int u16(byte[] d, int p) {
        return (d[p] & 0xff) | ((d[p + 1] & 0xff) << 8);
    }

    private static int u32(byte[] d, int p) {
        return (d[p] & 0xff) | ((d[p + 1] & 0xff) << 8) | ((d[p + 2] & 0xff) << 16) | ((d[p + 3] & 0xff) << 24);
    }

    private static long u64(byte[] d, long p) {
        long v = 0;
        for (int i = 7; i >= 0; i--) v = (v << 8) | (d[(int) p + i] & 0xffL);
        return v;
    }

    private static void w64(byte[] d, int p, long v) {
        for (int i = 0; i < 8; i++) {
            d[p + i] = (byte) v;
            v >>>= 8;
        }
    }

    private static String cstr(byte[] d, long off) {
        int i = (int) off;
        if (i < 0 || i >= d.length) return "";
        int j = i;
        while (j < d.length && d[j] != 0) j++;
        return new String(d, i, j - i);
    }
}
