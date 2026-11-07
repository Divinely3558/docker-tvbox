package com.docktvbox.spider;

import java.io.File;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.jar.JarFile;

import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/**
 * 给 ARM 解包 JVM 装的 -javaagent：织入 java.lang.Runtime.load0，在 System.load
 * 真正 dlopen 之前先对目标文件跑 {@link ElfPatch#patch(String)}。这样加固壳在
 * 运行期才释放的 bionic .so（随机文件名、预修补覆盖不到）也能被 glibc 加载。
 *
 * agentArgs 形如 ``<asm.jar>|<elfpatch.jar>``：ASM 所在 jar（dex2jar 的
 * d2j-external）与 elfpatch.jar 的路径都由调用方显式传入，追加到 bootstrap
 * classpath 后 java.lang.Runtime 可以直接引用 ElfPatch。不能靠 codeSource
 * 推断 elfpatch.jar 位置——agent 类可能被 -cp 上的同名类（build/classes）
 * 抢先加载，codeSource 就不再是 agent jar 所在目录。
 */
public class ElfAgent {

    public static void premain(String args, Instrumentation inst) {
        try {
            LoadHook hook = new LoadHook();
            String asm = args == null ? "" : args;
            String boot = "";
            int sep = asm.indexOf('|');
            if (sep >= 0) {
                boot = asm.substring(sep + 1);
                asm = asm.substring(0, sep);
            }
            if (boot.isEmpty()) {
                File self = new File(ElfAgent.class.getProtectionDomain().getCodeSource().getLocation().toURI());
                boot = new File(self.getParentFile(), "elfpatch.jar").getPath();
            }
            // 只有 ElfPatch 单独打进 elfpatch.jar 追加进 bootstrap；agent 自身的
            // 其它类若进 bootstrap，会与 app loader 里的类分裂成不同运行时包。
            inst.appendToBootstrapClassLoaderSearch(new JarFile(boot));
            if (!asm.isEmpty()) {
                inst.appendToBootstrapClassLoaderSearch(new JarFile(new File(asm)));
            }
            inst.addTransformer(hook, true);
            inst.retransformClasses(Runtime.class);
            System.out.println("elf-agent installed");
        } catch (Throwable t) {
            t.printStackTrace(System.out);
        }
    }

    static class LoadHook implements ClassFileTransformer {
        @Override
        public byte[] transform(ClassLoader loader, String className, Class<?> redefined,
                                ProtectionDomain pd, byte[] buf) {
            if (!"java/lang/Runtime".equals(className) || buf == null) return null;
            try {
                ClassReader cr = new ClassReader(buf);
                ClassWriter cw = new ClassWriter(cr, 0);
                cr.accept(new ClassVisitor(Opcodes.ASM9, cw) {
                    @Override
                    public MethodVisitor visitMethod(int access, String name, String desc,
                                                     String sig, String[] ex) {
                        MethodVisitor mv = super.visitMethod(access, name, desc, sig, ex);
                        if ("load0".equals(name) && desc.endsWith("Ljava/lang/String;)V")) {
                            int slot = stringSlot(desc);
                            return new MethodVisitor(Opcodes.ASM9, mv) {
                                @Override
                                public void visitCode() {
                                    super.visitCode();
                                    mv.visitVarInsn(Opcodes.ALOAD, slot);
                                    mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                                            "com/docktvbox/spider/ElfPatch",
                                            "patch", "(Ljava/lang/String;)V", false);
                                }
                            };
                        }
                        return mv;
                    }
                }, 0);
                return cw.toByteArray();
            } catch (Throwable t) {
                t.printStackTrace(System.out);
                return null;
            }
        }

        /** 实例方法里最后一个 String 参数的局部变量槽位（0 是 this）。 */
        private static int stringSlot(String desc) {
            String params = desc.substring(1, desc.indexOf(')'));
            int slot = 1, i = 0;
            while (i < params.length()) {
                char c = params.charAt(i);
                if (c == 'L') {
                    i = params.indexOf(';', i) + 1;
                    slot++;
                } else if (c == '[') {
                    while (params.charAt(i) == '[') i++;
                    if (params.charAt(i) == 'L') i = params.indexOf(';', i) + 1;
                    else i++;
                    slot++;
                } else {
                    slot += (c == 'J' || c == 'D') ? 2 : 1;
                    i++;
                }
            }
            return slot - 1; // 最后一个参数（已知是 String）
        }
    }
}
