package com.docktvbox.spider;

import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.io.*;
import java.lang.reflect.Modifier;
import java.util.*;
import java.util.jar.*;

/**
 * 用 ASM 修补 dex2jar 输出的 class jar：
 *
 * 1) 重算 stackmap frames（JDK13+ 校验需要 frames，dex2jar 不生成）；
 * 2) R4 构造器误译：DEX 允许 ``new-instance 真实类`` 配 ``invoke-direct 超类.<init>``，
 *    dex2jar 会翻成 ``new 超类``——超类是抽象类/接口时运行期 InstantiationError。
 *    合法 jar 不可能 new 抽象类型，所以出现即误译：改指 jar 内唯一具体子类，
 *    子类缺对应 <init> 时补一个委托 super 的 synthetic 构造器。
 */
public class AsmFix {

    // 全 jar 的类信息（R4 查唯一子类要全局视角）：name -> super / access / <init> 描述符列表
    private static final Map<String, String> SUPER = new HashMap<>();
    private static final Map<String, Integer> ACCESS = new HashMap<>();
    private static final Map<String, List<String>> IFACES = new HashMap<>();
    private static final Map<String, List<String>> CTORS = new HashMap<>();
    private static Map<String, byte[]> blobs;

    public static void main(String[] args) throws Exception {
        File in = new File(args[0]), out = new File(args[1]);
        try (JarFile jar = new JarFile(in);
             FileOutputStream fos = new FileOutputStream(out);
             JarOutputStream jos = new JarOutputStream(fos)) {
            blobs = new LinkedHashMap<>();
            Enumeration<JarEntry> en = jar.entries();
            while (en.hasMoreElements()) {
                JarEntry e = en.nextElement();
                blobs.put(e.getName(), jar.getInputStream(e).readAllBytes());
            }
            SUPER.clear();
            ACCESS.clear();
            IFACES.clear();
            CTORS.clear();
            for (Map.Entry<String, byte[]> ent : blobs.entrySet()) {
                if (ent.getKey().endsWith(".class")) scan(ent.getValue());
            }
            for (Map.Entry<String, byte[]> ent : blobs.entrySet()) {
                byte[] data = ent.getValue();
                if (ent.getKey().endsWith(".class")) {
                    try {
                        data = fix(data);
                    } catch (Throwable t) {
                        System.out.println("skip " + ent.getKey() + " " + t);
                    }
                }
                jos.putNextEntry(new JarEntry(ent.getKey()));
                jos.write(data);
                jos.closeEntry();
            }
        }
        System.out.println("fixed -> " + out);
    }

    /** 第一遍：只读类结构（不读 Code），建继承/构造器表。 */
    static void scan(byte[] data) {
        ClassNode cn = new ClassNode();
        new ClassReader(data).accept(cn, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        SUPER.put(cn.name, cn.superName);
        ACCESS.put(cn.name, cn.access);
        IFACES.put(cn.name, new ArrayList<>(cn.interfaces));
        List<String> ctors = new ArrayList<>();
        for (MethodNode mn : cn.methods) {
            if (mn.name.equals("<init>")) ctors.add(mn.desc);
        }
        CTORS.put(cn.name, ctors);
    }

    static byte[] fix(byte[] data) {
        ClassNode cn = new ClassNode();
        new ClassReader(data).accept(cn, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        for (MethodNode mn : cn.methods) fixNews(mn);
        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_FRAMES) {
            @Override
            protected String getCommonSuperClass(String type1, String type2) {
                // 不加载类（classpath 不完整），退化到 Object：对校验器仍然合法
                return "java/lang/Object";
            }
        };
        cn.accept(cw);
        return cw.toByteArray();
    }

    /** R4：把「new 抽象类/接口」与配对的 invokespecial <init> 一起改指唯一具体子类。 */
    static void fixNews(MethodNode mn) {
        for (AbstractInsnNode p = mn.instructions.getFirst(); p != null; p = p.getNext()) {
            if (p.getOpcode() != Opcodes.NEW) continue;
            TypeInsnNode t = (TypeInsnNode) p;
            if (!isAbstractLike(t.desc)) continue;
            // dex2jar 的形态是 new; dup; invokespecial 紧邻，小窗口内找配对的 <init>
            int window = 0;
            for (AbstractInsnNode q = p.getNext(); q != null && window++ <= 12; q = q.getNext()) {
                if (q.getOpcode() != Opcodes.INVOKESPECIAL) continue;
                MethodInsnNode mi = (MethodInsnNode) q;
                if (!mi.name.equals("<init>") || !mi.owner.equals(t.desc)) break; // 不是配对，保守放弃
                String target = uniqueConcreteSubclass(t.desc);
                if (target != null && ensureCtor(target, mi.desc)) {
                    t.desc = target;
                    mi.owner = target;
                }
                break;
            }
        }
    }

    /** 抽象类或接口：jar 内看 access，jar 外（JDK）用 bootstrap 反射；查不到按不是处理。 */
    static boolean isAbstractLike(String name) {
        Integer acc = ACCESS.get(name);
        if (acc != null) return (acc & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_INTERFACE)) != 0;
        try {
            Class<?> c = Class.forName(name.replace('/', '.'), false, null);
            return Modifier.isAbstract(c.getModifiers()) || c.isInterface();
        } catch (Throwable t) {
            return false;
        }
    }

    /** jar 内唯一具体子类（间接也算）；0 个或多个候选都无法安全选择，返回 null。 */
    static String uniqueConcreteSubclass(String x) {
        String hit = null;
        for (String c : ACCESS.keySet()) {
            if (c.equals(x) || isAbstractLike(c)) continue;
            if (!isSubtypeOf(c, x)) continue;
            if (hit != null) return null;
            hit = c;
        }
        return hit;
    }

    static boolean isSubtypeOf(String c, String x) {
        Deque<String> stack = new ArrayDeque<>();
        stack.push(c);
        Set<String> seen = new HashSet<>();
        while (!stack.isEmpty()) {
            String cur = stack.pop();
            if (cur == null || !seen.add(cur)) continue;
            if (!cur.equals(c) && cur.equals(x)) return true; // 先判等：出 jar 的 JDK 父类也算命中
            if (!ACCESS.containsKey(cur)) continue; // 出 jar（JDK 类）：不再展开其继承链
            stack.push(SUPER.get(cur));
            for (String i : IFACES.getOrDefault(cur, List.of())) stack.push(i);
        }
        return false;
    }

    /** 子类缺 <init>desc 时补 synthetic 构造器（aload_0; super.<init>; return）。
     *  只处理 ()V（带参构造没人给实参，误译现场也都是 ()V）；已有该构造器直接可用。 */
    static boolean ensureCtor(String className, String desc) {
        if (CTORS.getOrDefault(className, List.of()).contains(desc)) return true;
        if (!"()V".equals(desc)) return false;
        byte[] data = blobs.get(className + ".class");
        if (data == null) return false;
        ClassNode cn = new ClassNode();
        new ClassReader(data).accept(cn, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
        String sup = cn.superName == null ? "java/lang/Object" : cn.superName;
        MethodVisitor mv = cn.visitMethod(Opcodes.ACC_PUBLIC | Opcodes.ACC_SYNTHETIC, "<init>", desc, null, null);
        mv.visitCode();
        mv.visitVarInsn(Opcodes.ALOAD, 0);
        mv.visitMethodInsn(Opcodes.INVOKESPECIAL, sup, "<init>", desc, false);
        mv.visitInsn(Opcodes.RETURN);
        mv.visitMaxs(0, 0); // COMPUTE_FRAMES 会重算
        mv.visitEnd();
        ClassWriter cw = new ClassWriter(ClassWriter.COMPUTE_FRAMES);
        cn.accept(cw);
        blobs.put(className + ".class", cw.toByteArray());
        CTORS.get(className).add(desc);
        return true;
    }
}
