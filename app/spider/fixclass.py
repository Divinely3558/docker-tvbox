"""修补 dex2jar 对加固/混淆 jar 的构造器误指。

dex2jar 遇到混淆字节码时常把 ``new X; X.<init>()`` 错译成 ``new java/lang/Object``
或把 ``invokespecial`` 指到错误的类，JVM 一执行就 NoSuchMethodError——关掉校验
（-Xverify:none）也救不回来。这里用数据流分析（而不是“最近的 new”启发式）
锁定真实类型：

- R1: ``invokespecial java/lang/Object.<init>`` 且前面有 ``new X`` → 改指 ``X.<init>``
- R2: ``new Object`` 后写入类型为 X 的字段/作参数传出 → new 与构造调用都改指 X
- R3: 目标类缺少对应 ``<init>`` 时，补一个委托 super 的 synthetic 构造器

加固解包链路里有两处 dex2jar 产物要经过这里：外层壳（wrapper，qemu 下跑
Init.init）与内层真实 spider（缓存后由主 Runner 加载）。
"""

from __future__ import annotations

import logging
import struct
import zipfile
from pathlib import Path

logger = logging.getLogger("docktvbox.jar")

LEN = [1]*256
for op in (0x10, 0x12, 0x15, 0x16, 0x17, 0x18, 0x19, 0x36, 0x37, 0x38, 0x39, 0x3A, 0xBC): LEN[op] = 2
for op in (0x11, 0x13, 0x14, 0x84) + tuple(range(0x99, 0xAA)) + (0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xBB, 0xBD, 0xC0, 0xC1, 0xC6, 0xC7): LEN[op] = 3
for op in (0xB9, 0xBA, 0xC8, 0xC9): LEN[op] = 5
LEN[0xC5] = 4
BRANCH = set(range(0x99, 0xAA)) | {0xC6, 0xC7, 0xC8, 0xC9, 0xBF} | set(range(0xAC, 0xB2))

NEEDED = {}  # xclass -> desc，缺构造器的类
JAR_INFO = {}  # 类名 -> (is_interface, frozenset(直接接口), super)

def scan_info(name, data):
    try:
        cp, cp_end = parse_cp(data)
        flags = struct.unpack_from(">H", data, cp_end)[0]
        n = struct.unpack_from(">H", data, cp_end + 6)[0]
        ifaces = frozenset(cp_class(cp, struct.unpack_from(">H", data, cp_end + 8 + 2*k)[0]) for k in range(n))
        JAR_INFO[this_class(cp, data, cp_end) or name[:-6]] = (bool(flags & 0x0200), ifaces, super_class(cp, data, cp_end))
    except Exception:
        pass

def implements(x, iface):
    """x 是否（直接或间接）实现 iface；x 不在 jar 里时按没有算。"""
    seen = set()
    stack = [x]
    while stack:
        c = stack.pop()
        if c in seen or c is None: continue
        seen.add(c)
        info = JAR_INFO.get(c)
        if not info: continue
        if iface in info[1]: return True
        stack.extend(info[1])
        stack.append(info[2])
    return False

def param_types(params):
    """方法描述符的参数列表 -> 每个参数的对象类型（基本类型/数组记 None）。"""
    out = []
    i = 0
    while i < len(params):
        c = params[i]
        if c == "L":
            j = params.index(";", i)
            out.append(params[i + 1:j])
            i = j + 1
        elif c == "[":
            j = i
            while params[j] == "[":
                j += 1
            if params[j] == "L":
                j = params.index(";", j)
            out.append(None)
            i = j + 1
        else:
            out.append(None)
            i += 1
    return out

def last_param(params):
    types = param_types(params)
    return types[-1] if types else None

def parse_cp(data):
    cp = [None]; i = 10
    count = struct.unpack_from(">H", data, 8)[0]
    while len(cp) < count:
        tag = data[i]; i += 1
        if tag == 1:
            ln = struct.unpack_from(">H", data, i)[0]; i += 2
            cp.append((1, data[i:i+ln].decode("utf-8", "replace"))); i += ln
        elif tag in (7, 8, 16, 19, 20):
            cp.append((tag, struct.unpack_from(">H", data, i)[0])); i += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            cp.append((tag, *struct.unpack_from(">HH", data, i))); i += 4
        elif tag == 15: cp.append((tag, data[i], struct.unpack_from(">H", data, i+1)[0])); i += 3
        elif tag in (3, 4): cp.append((tag,)); i += 4
        elif tag in (5, 6): cp.append((tag,)); cp.append(None); i += 8
        else: raise ValueError(f"tag {tag}")
    return cp, i

def cp_class(cp, idx):
    e = cp[idx]
    return cp[e[1]][1] if e and e[0] == 7 else None

def cp_ref(cp, idx):
    e = cp[idx]
    if not e or e[0] not in (9, 10, 11): return None
    nt = cp[e[2]]
    return cp_class(cp, e[1]), cp[nt[1]][1], cp[nt[2]][1]

def utf8_of(cp, idx):
    e = cp[idx]
    return e[1] if e and e[0] == 1 else None

def decode(code):
    pc, n = 0, len(code)
    while pc < n:
        op = code[pc]
        yield pc, op
        if op == 0xAA:
            pad = (4 - (pc + 1) % 4) % 4
            base = pc + 1 + pad
            low, high = struct.unpack_from(">ii", code, base + 4)
            pc = base + 12 + (high - low + 1) * 4
        elif op == 0xAB:
            pad = (4 - (pc + 1) % 4) % 4
            base = pc + 1 + pad
            npairs = struct.unpack_from(">i", code, base + 4)[0]
            pc = base + 8 + npairs * 8
        elif op == 0xC4:
            pc += 6 if code[pc+1] == 0x84 else 4
        else:
            pc += LEN[op]

def this_class(cp, data, cp_end):
    ci = struct.unpack_from(">H", data, cp_end + 2)[0]
    return cp_class(cp, ci)

def super_class(cp, data, cp_end):
    ci = struct.unpack_from(">H", data, cp_end + 4)[0]
    return cp_class(cp, ci)

def method_range(data, cp_end):
    """返回 (methods_count_off, methods_end_off)"""
    i = cp_end + 6
    niface = struct.unpack_from(">H", data, i)[0]
    i += 2 + 2 * niface
    nfields = struct.unpack_from(">H", data, i)[0]; i += 2
    for _ in range(nfields):
        na = struct.unpack_from(">H", data, i + 6)[0]; i += 8
        for _ in range(na):
            al = struct.unpack_from(">I", data, i + 2)[0]; i += 6 + al
    mcount_off = i
    nmethods = struct.unpack_from(">H", data, i)[0]; i += 2
    for _ in range(nmethods):
        na = struct.unpack_from(">H", data, i + 6)[0]; i += 8
        for _ in range(na):
            al = struct.unpack_from(">I", data, i + 2)[0]; i += 6 + al
    return mcount_off, i

class Pool:
    """常量池追加器：基于原 count 递增分配索引。"""
    def __init__(self, data, cp):
        self.data = data
        self.cp = cp
        self.entries = []
        self.classes = {}

    def _idx(self):
        return struct.unpack_from(">H", self.data, 8)[0] + len(self.entries)

    def utf8(self, s):
        idx = self._idx()
        self.entries.append(b"\x01" + struct.pack(">H", len(s)) + s.encode())
        return idx

    def class_(self, name):
        if name in self.classes:
            return self.classes[name]
        for ci, e in enumerate(self.cp):
            if e and e[0] == 7 and self.cp[e[1]][1] == name:
                self.classes[name] = ci
                return ci
        u = self.utf8(name)
        idx = self._idx()
        self.entries.append(b"\x07" + struct.pack(">H", u))
        self.classes[name] = idx
        return idx

    def ref(self, tag, cls, name, desc):
        u1 = self.utf8(name)
        u2 = self.utf8(desc)
        nt = self._idx()
        self.entries.append(b"\x0C" + struct.pack(">HH", u1, u2))
        c = self.class_(cls)
        idx = self._idx()
        self.entries.append(bytes([tag]) + struct.pack(">HH", c, nt))
        return idx

def rebuild(data, cp_end, pool, extra):
    old_count = struct.unpack_from(">H", data, 8)[0]
    out = bytearray()
    out += data[:8]
    out += struct.pack(">H", old_count + len(pool.entries))
    out += data[10:cp_end]
    for e in pool.entries:
        out += e
    out += extra(cp_end)
    return bytes(out)

def fix_class(data):
    cp, cp_end = parse_cp(data)
    pool = Pool(data, cp)
    patches = []
    mcount_off, mend = method_range(data, cp_end)
    i = mcount_off + 2
    nmethods = struct.unpack_from(">H", data, mcount_off)[0]
    for _ in range(nmethods):
        na = struct.unpack_from(">H", data, i + 6)[0]
        p = i + 8
        for _ in range(na):
            name_i = struct.unpack_from(">H", data, p)[0]
            alen = struct.unpack_from(">I", data, p + 2)[0]
            if utf8_of(cp, name_i) == "Code":
                code_len = struct.unpack_from(">I", data, p + 10)[0]
                code_start = p + 14
                code = data[code_start:code_start + code_len]
                # 数据流模型：dex2jar 常把 new 与 init 用局部变量分开
                # （new X; astore_1; new Y; astore_2; aload_2; init Y … aload_1; init X），
                # “最近的 new” 启发式会错配。这里跟踪未初始化对象的归属：
                #   new X 后紧跟 astore_n → uninit[n] = X；new; dup → 栈上对象；
                #   invokespecial 前以最近一次 aload_n / 栈上 new 锁定真实类。
                uninit = {}      # 局部变量 -> (new_pc, xclass)：new 后尚未 init
                known = {}       # 局部变量 -> (new_pc, init_pc, eff)：init 后存入的有效类
                aloads = []      # 连续 aload 序列的局部变量号（invoke/字段写的实参回溯用）
                stack_new = None # 压栈待初始化的 new（new; dup; invokespecial 形态）
                loaded = None    # 最近一次 aload 取出的未初始化对象
                fresh = None     # (new_pc, init_pc, next_pc, eff)：刚 init 完，待消费指令校验
                pending_new = None
                for pc, op in decode(code):
                    if op == 0xBB:
                        pending_new = (pc, cp_class(cp, struct.unpack_from(">H", code, pc + 1)[0]))
                        loaded = None
                        aloads = []
                    elif op == 0x3A:  # astore n
                        n = code[pc + 1]
                        if pending_new:
                            uninit[n] = pending_new
                        elif fresh and pc == fresh[2]:
                            known[n] = (fresh[0], fresh[1], fresh[3])
                            fresh = None
                        pending_new = None
                        loaded = None
                        aloads = []
                    elif 0x3B <= op <= 0x3E:  # astore_0..3
                        n = op - 0x3B
                        if pending_new:
                            uninit[n] = pending_new
                        elif fresh and pc == fresh[2]:
                            known[n] = (fresh[0], fresh[1], fresh[3])
                            fresh = None
                        pending_new = None
                        loaded = None
                        aloads = []
                    elif op == 0x59:  # dup：对象留在栈上初始化
                        if pending_new:
                            stack_new = pending_new
                        pending_new = None
                        aloads = []
                    elif op == 0x19:  # aload n
                        n = code[pc + 1]
                        loaded = uninit.get(n)
                        aloads.append(n)
                        pending_new = None
                    elif 0x2A <= op <= 0x2D:  # aload_0..3
                        n = op - 0x2A
                        loaded = uninit.get(n)
                        aloads.append(n)
                        pending_new = None
                    elif op == 0xB7:
                        pending_new = None
                        idx = struct.unpack_from(">H", code, pc + 1)[0]
                        ref = cp_ref(cp, idx)
                        src = loaded or stack_new
                        loaded = None
                        stack_new = None
                        if ref and ref[1] == "<init>" and src and pc - src[0] < 96:
                            npc, xclass = src
                            eff = None  # 修补后 new 的有效类
                            if ref[0] == "java/lang/Object" and xclass != "java/lang/Object":
                                # R1：构造调用误指 Object，以 new 的类为准
                                patches.append((code_start + pc + 1, pool.ref(10, xclass, "<init>", ref[2])))
                                NEEDED.setdefault(xclass, ref[2])
                                eff = xclass
                            elif ref[0] != "java/lang/Object" and xclass != ref[0]:
                                # new 误指（Object 或别的类），以构造调用的类为准
                                patches.append((code_start + npc + 1, pool.class_(ref[0])))
                                eff = ref[0]
                            elif ref[0] == xclass:
                                eff = xclass
                            if eff is not None:
                                fresh = (npc, pc, pc + 3, eff)
                    elif op in (0xB3, 0xB5):  # putstatic / putfield：字段类型反推
                        idx = struct.unpack_from(">H", code, pc + 1)[0]
                        ref = cp_ref(cp, idx)
                        src = None
                        if fresh and pc == fresh[2]:
                            src = (fresh[0], fresh[1], fresh[3])
                        elif aloads and aloads[-1] in known:
                            npc0, ipc0, eff0 = known[aloads[-1]]
                            src = (npc0, ipc0, eff0)
                        if src and ref and ref[2].startswith("L") and ref[2].endswith(";"):
                            xclass = ref[2][1:-1]
                            if xclass != "java/lang/Object" and xclass != src[2]:
                                patches.append((code_start + src[0] + 1, pool.class_(xclass)))
                                patches.append((code_start + src[1] + 1, pool.ref(10, xclass, "<init>", "()V")))
                                NEEDED.setdefault(xclass, "()V")
                        fresh = None
                        aloads = []
                    elif op == 0xC0 and fresh and pc == fresh[2]:  # checkcast T：目标类型即真实类型
                        t = cp_class(cp, struct.unpack_from(">H", code, pc + 1)[0])
                        if t and t != "java/lang/Object":
                            npc, ipc = fresh[0], fresh[1]
                            patches.append((code_start + npc + 1, pool.class_(t)))
                            patches.append((code_start + ipc + 1, pool.ref(10, t, "<init>", "()V")))
                            NEEDED.setdefault(t, "()V")
                            fresh = None
                        aloads = []
                    elif op in (0xB6, 0xB8, 0xB9):  # invoke：按尾部参数类型反推
                        idx = struct.unpack_from(">H", code, pc + 1)[0]
                        ref = cp_ref(cp, idx)
                        cands = []  # [(npc, ipc, cur, t)]
                        if ref and ref[2].startswith("("):
                            params = ref[2][1:ref[2].index(")")]
                            t = last_param(params)
                            if fresh and pc == fresh[2] and t:
                                cands.append((fresh[0], fresh[1], fresh[3], t))
                            types = param_types(params)
                            for back, vn in enumerate(reversed(aloads)):
                                if back >= len(types):
                                    break
                                t = types[-1 - back]
                                info = t and known.get(vn)
                                if info and t != "java/lang/Object":
                                    cands.append((info[0], info[1], info[2], t))
                        for npc, ipc, cur in {(c[0], c[1], c[2]) for c in cands}:
                            t = next(c[3] for c in cands if c[:3] == (npc, ipc, cur))
                            if t != cur and ref and ref[0] != cur:
                                target = None
                                info = JAR_INFO.get(t)
                                is_iface = info[0] if info else True  # JDK 类型按接口处理，找实现者
                                if is_iface:
                                    if not implements(cur, t):
                                        impls = [c for c, (ifc, _, _s) in JAR_INFO.items() if not ifc and implements(c, t)]
                                        if len(impls) == 1:
                                            target = impls[0]
                                elif cur == "java/lang/Object":
                                    target = t
                                if target:
                                    patches.append((code_start + npc + 1, pool.class_(target)))
                                    patches.append((code_start + ipc + 1, pool.ref(10, target, "<init>", "()V")))
                                    NEEDED.setdefault(target, "()V")
                        fresh = None
                        aloads = []
                    else:
                        pending_new = None
                        loaded = None
                        aloads = []
                    if op in BRANCH:
                        uninit.clear()
                        known.clear()
                        aloads = []
                        stack_new = None
                        loaded = None
                        fresh = None
                        pending_new = None
            p += 6 + alen
        i = p
    if not patches:
        return data
    buf = bytearray(data)
    for off, mr in patches:
        struct.pack_into(">H", buf, off, mr)
    data = bytes(buf)
    return rebuild(data, cp_end, pool, lambda e: data[e:])

def ensure_ctor(data, desc):
    """类缺少 <init>desc 时追加 synthetic 构造器：aload_0; invokespecial super.<init>; return"""
    cp, cp_end = parse_cp(data)
    mcount_off, mend = method_range(data, cp_end)
    i = mcount_off + 2
    for _ in range(struct.unpack_from(">H", data, mcount_off)[0]):
        ni, di = struct.unpack_from(">HH", data, i + 2)
        if utf8_of(cp, ni) == "<init>" and utf8_of(cp, di) == desc:
            return data
        na = struct.unpack_from(">H", data, i + 6)[0]; i += 8
        for _ in range(na):
            al = struct.unpack_from(">I", data, i + 2)[0]; i += 6 + al
    sup = super_class(cp, data, cp_end) or "java/lang/Object"
    pool = Pool(data, cp)
    name_i = pool.utf8("<init>")
    desc_i = pool.utf8(desc)
    code_i = pool.utf8("Code")
    super_ref = pool.ref(10, sup, "<init>", desc)
    code = b"\x2a\xb7" + struct.pack(">H", super_ref) + b"\xb1"
    attr = struct.pack(">HI", code_i, 2 + 2 + 4 + len(code) + 2 + 2)
    attr += struct.pack(">HHI", 1, 1, len(code)) + code + struct.pack(">HH", 0, 0)
    method = struct.pack(">HHHH", 0x0001, name_i, desc_i, 1) + attr

    def extra(e):
        out = bytearray()
        out += data[e:mcount_off]
        out += struct.pack(">H", struct.unpack_from(">H", data, mcount_off)[0] + 1)
        out += data[mcount_off + 2:mend]
        out += method
        out += data[mend:]
        return out
    return rebuild(data, cp_end, pool, extra)

def fix_jar(src: Path, dst: Path) -> int:
    """修补 ``src``（dex2jar 输出的 class jar）写入 ``dst``，返回补造的构造器数量。

    单个类修补失败只跳过该类（混淆字节码偶发解析不了），不拖垮整个 jar。
    模块级 NEEDED/JAR_INFO 是单次修补的中间状态，每次调用前清空，
    保证同一进程内连续修补多个 jar 不串味。
    """
    NEEDED.clear()
    JAR_INFO.clear()
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        blobs = {n: zin.read(n) for n in names}

    for n in list(blobs):
        if n.endswith(".class"):
            scan_info(n, blobs[n])

    for n in list(blobs):
        if n.endswith(".class"):
            try:
                blobs[n] = fix_class(blobs[n])
            except Exception:  # noqa: BLE001
                logger.debug("跳过无法修补的类 %s", n, exc_info=True)

    for xclass, desc in NEEDED.items():
        n = xclass + ".class"
        if n in blobs:
            try:
                blobs[n] = ensure_ctor(blobs[n], desc)
            except Exception:  # noqa: BLE001
                logger.debug("补造构造器失败 %s", n, exc_info=True)

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:
            zout.writestr(n, blobs[n])
    return len(NEEDED)
