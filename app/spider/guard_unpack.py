"""加固 jar（guard）离线解包。

TVBox/catvod 的部分配置源把 spider 放进 ``assets/*.guard``，由 ARM64 native
代码（``assets/*_v8.so``）在 Android 上解密后交给 ``DexClassLoader``。
x86 的 JVM 无法加载这些 .so，直接调用会报
``NoClassDefFoundError: com.github.catvod.spider.DexNative``。

这里的做法是统一的、不针对具体站点：用 qemu 跑一个 ARM64 JRE，调用 jar 自带的
``com.github.catvod.spider.Init.init(context)``；我们的 ``DexClassLoader`` 桩会在
native 删除临时文件之前把解密出的内层 dex 复制出来，再用 dex2jar 转成普通 jar。
之后所有 ``csp_XxxGuard`` 都会落到内层真实类 ``Xxx``（见 Runner 的类名回退）。
"""

from __future__ import annotations

import logging
import os
import shutil
import struct
import subprocess
import tarfile
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import httpx

from ..settings import (
    ARM_JRE_URL,
    ARM_QEMU_BIN,
    ARM_ROOTFS_URL,
    ARM_RUNTIME_DIR,
    ARM_UNPACK_ENABLED,
    ARM_UNPACK_TIMEOUT,
    D2J_XMX,
    SPIDER_LIB_DIR,
    SPIDER_RUNTIME_CLASSES,
)
from .errors import JarError

logger = logging.getLogger("docktvbox.jar")

_PREPARE = Path(__file__).resolve().parents[2] / "spider-runtime" / "prepare.sh"
# 这些库只存在于 Android，glibc 环境里没有，加载前必须从 NEEDED 里去掉。
_ANDROID_ONLY = (
    "liblog.so",
    "libandroid.so",
    "libGLESv2.so",
    "libEGL.so",
    "libOpenSLES.so",
    "libmediandk.so",
    "libnativewindow.so",
    "libjnigraphics.so",
    "libc++_shared.so",
)


class GuardUnpackError(JarError):
    """加固 jar 解包失败；消息直接展示给用户。"""


def is_guard_jar(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(
                name.startswith("assets/") and name.endswith(".guard")
                for name in archive.namelist()
            )
    except (zipfile.BadZipFile, OSError):
        return False


def unpack(raw: Path, wrapper: Path, target: Path) -> Path:
    """把加固 jar 换成解密后的内层 jar，写入 ``target``。

    ``raw`` 是原始下载的 zip（classes.dex + assets），``wrapper`` 是 dex2jar
    转出来的 class jar；解包时要把 raw 里的 assets 补回 wrapper 才能跑 native。
    """
    if not ARM_UNPACK_ENABLED:
        raise GuardUnpackError("该配置源使用加固 spider（guard jar），ARM 解包已通过 ARM_UNPACK=0 关闭")
    runtime = _ensure_runtime()
    if runtime is None:
        raise GuardUnpackError(
            "该配置源使用加固 spider（guard jar），需要 ARM 解包环境；"
            "首次准备失败，请检查能否访问 GitHub/Ubuntu 镜像，或手动把 JRE 与 rootfs 放进 "
            f"{ARM_RUNTIME_DIR}"
        )
    qemu, java, rootfs, libs = runtime

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        work = Path(staging)
        guards = _guard_assets(raw)
        if not guards:
            raise GuardUnpackError("加固 jar 里没有找到 assets/*.guard")
        patches = _patched_libs(raw, work)

        last_error = "未知原因"
        # 一个 jar 里可能有多个 guard：逐个尝试，取第一个能解出内层 dex 的。
        for guard in guards:
            inner_dex = work / f"{Path(guard).stem}.dex"
            jar_copy = work / "with-patched-native.jar"
            _rebuild(wrapper, raw, jar_copy, patches)
            if _run_unpacker(qemu, java, rootfs, libs, jar_copy, inner_dex, work, guard):
                return _convert_inner(inner_dex, target, work)
            log = _tail(work / "unpack.log")
            last_error = log or "native 没有返回解密后的 dex"
            logger.warning("guard 解包失败 %s/%s：%s", wrapper.name, guard, last_error)

    raise GuardUnpackError(f"加固 spider 解包失败：{last_error}")


# ---- 解包流程 -------------------------------------------------------------


def _guard_assets(wrapper: Path) -> list[str]:
    with zipfile.ZipFile(wrapper) as archive:
        return [
            name
            for name in archive.namelist()
            if name.startswith("assets/") and name.endswith(".guard")
        ]


def _rebuild(wrapper: Path, raw: Path, out: Path, patches: dict[str, Path]) -> None:
    """合并 class jar 与原始 assets，并把 assets/*.so 换成修补后的版本。"""
    with zipfile.ZipFile(wrapper) as classes, zipfile.ZipFile(raw) as assets, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as dest:
        for item in classes.infolist():
            dest.writestr(item, classes.read(item.filename))
        for item in assets.infolist():
            if not item.filename.startswith("assets/"):
                continue
            if item.filename in patches:
                dest.write(patches[item.filename], item.filename)
            else:
                dest.writestr(item, assets.read(item.filename))


def _patched_libs(raw: Path, work: Path) -> dict[str, Path]:
    """修补 raw jar 里所有 assets/*.so，返回 {原文件名: 修补后路径}。"""
    patches: dict[str, Path] = {}
    with zipfile.ZipFile(raw) as archive:
        for item in archive.infolist():
            if not (item.filename.startswith("assets/") and item.filename.endswith(".so")):
                continue
            source = work / Path(item.filename).name
            source.write_bytes(archive.read(item.filename))
            patched = work / ("p" + source.name)
            patch_elf(source, patched)
            patches[item.filename] = patched
            logger.info("已修补 native 库 %s", item.filename)
    return patches


def _run_unpacker(
    qemu: str,
    java: str,
    rootfs: Path,
    libs: Path,
    jar: Path,
    capture: Path,
    work: Path,
    guard: str,
) -> bool:
    classpath = os.pathsep.join(
        [str(SPIDER_RUNTIME_CLASSES), str(jar)]
        + ([str(SPIDER_LIB_DIR) + "/*"] if Path(SPIDER_LIB_DIR).is_dir() else [])
    )
    data_dir = work / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        qemu,
        "-L",
        str(rootfs),
        java,
        "-Xmx" + "512m",
        "-Dfile.encoding=UTF-8",
        f"-Dspider.data.dir={data_dir}",
        f"-Dspider.jar={jar}",
        f"-Dspider.capture={capture}",
        "-cp",
        classpath,
        "com.docktvbox.spider.GuardUnpack",
    ]
    # 只把修补后的 glibc 兼容库放进 LD_LIBRARY_PATH。把 JRE 自己的 lib 也加进去
    # 会让 java launcher 间接执行 libjli 时被 qemu 误判成目标程序（Exec format error）。
    env = {**os.environ, "LD_LIBRARY_PATH": str(libs)}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=ARM_UNPACK_TIMEOUT,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        (work / "unpack.log").write_text(f"{type(exc).__name__}: {exc}", "utf-8")
        return False
    (work / "unpack.log").write_text((result.stdout or "") + (result.stderr or ""), "utf-8")
    return (
        result.returncode == 0
        and capture.is_file()
        and capture.stat().st_size > 0
        and "GUARD_CAPTURED" in (result.stdout or "")
    )


def _convert_inner(inner: Path, target: Path, work: Path) -> Path:
    """内层 dex（通常是 zip 包着 classes.dex）转成 JVM jar。"""
    kind = "dex-zip" if zipfile.is_zipfile(inner) else "raw-dex"
    out = work / "inner"
    out.mkdir(exist_ok=True)
    source = inner
    if kind == "raw-dex":
        source = work / "wrapped.jar"
        with zipfile.ZipFile(source, "w") as archive:
            archive.write(inner, "classes.dex")
    result = subprocess.run(
        ["bash", str(_PREPARE), "convert", str(source), "inner"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SPIDERS": str(out), "D2J_XMX": D2J_XMX},
    )
    produced = out / "inner.jar"
    if not produced.is_file() or produced.stat().st_size == 0:
        detail = (result.stderr or result.stdout or "")[-200:]
        raise GuardUnpackError(f"内层 dex 转换失败：{detail}")
    os.replace(produced, target)
    logger.info("加固 jar 已解包 %s -> %s", target.name, _tail(work / "unpack.log")[:120])
    return target


def _tail(path: Path, limit: int = 300) -> str:
    try:
        text = path.read_text("utf-8", "ignore").strip()
    except OSError:
        return ""
    lines = [line for line in text.splitlines() if line.strip()]
    return " | ".join(lines[-3:])[:limit]


# ---- ELF 修补 -------------------------------------------------------------


def patch_elf(raw: Path, out: Path) -> None:
    """把 Android/ARM 的 .so 修成 glibc 能加载的形态。

    - 去掉 Android 专有的 NEEDED（liblog/libandroid 等）
    - 去掉符号版本要求（``@LIBC``）：glibc 没有 bionic 的 ``LIBC`` 版本命名空间
    """
    out.write_bytes(raw.read_bytes())
    needed = _needed_libs(out)
    remove = [name for name in needed if name in _ANDROID_ONLY]
    if remove:
        args = ["patchelf"]
        for name in remove:
            args += ["--remove-needed", name]
        args.append(str(out))
        try:
            subprocess.run(args, capture_output=True, text=True, check=False)
        except OSError:
            pass
    _strip_symbol_versions(out)


def _needed_libs(path: Path) -> list[str]:
    data = path.read_bytes()
    sections, dynstr = _elf_sections(data)
    if not dynstr or ".dynamic" not in sections:
        return []
    start, size = dynstr
    offset, length = sections[".dynamic"]
    needed: list[str] = []
    for pos in range(offset, offset + length, 16):
        tag, value = struct.unpack_from("<QQ", data, pos)
        if tag != 1 or value >= size:
            continue
        name = data[start + value : start + size].split(b"\0", 1)[0].decode("utf-8", "ignore")
        if name:
            needed.append(name)
    return needed


def _strip_symbol_versions(path: Path) -> None:
    data = bytearray(path.read_bytes())
    sections, _dynstr = _elf_sections(data)
    if not sections:
        return
    touched = False
    for key, (offset, size) in sections.items():
        if size == 0:
            continue
        if key == ".gnu.version":
            for pos in range(offset, offset + size, 2):
                data[pos : pos + 2] = struct.pack("<H", 1)
            touched = True
        elif key == ".gnu.version_r":
            # 保留一个合法但空的 Verneed 记录（version=1，其它全 0），
            # 让 glibc 校验通过又没有任何版本依赖。
            data[offset : offset + size] = b"\0" * size
            struct.pack_into("<HHI", data, offset, 1, 0, 0)
            touched = True
        elif key == ".dynamic":
            # 把这些与符号版本相关的动态项整体移除（后面的项前移，避免提前出现
            # DT_NULL 截断）。glibc 看到没有 VERNEED/VERSYM 就不再做版本校验，
            # 这正是我们想要的：bionic 的 LIBC 版本在 glibc 里不存在。
            drop = {
                0x6FFFFFFE,  # VERNEED
                0x6FFFFFFF,  # VERNEEDNUM
                0x6FFFFFFC,  # VERDEF
                0x6FFFFFFD,  # VERDEFNUM
                0x6FFFFFF0,  # VERSYM
                0x6FFFFFF9,  # RELACOUNT
            }
            entries = []
            for pos in range(offset, offset + size, 16):
                tag, value = struct.unpack_from("<QQ", data, pos)
                if tag == 0:
                    break
                if tag not in drop:
                    entries.append((tag, value))
            for index, (tag, value) in enumerate(entries):
                struct.pack_into("<QQ", data, offset + index * 16, tag, value)
            for index in range(len(entries), size // 16):
                struct.pack_into("<QQ", data, offset + index * 16, 0, 0)
            touched = True
    if touched:
        path.write_bytes(bytes(data))


def _elf_sections(data: bytes) -> tuple[dict[str, tuple[int, int]], tuple[int, int] | None]:
    """返回 ({节名: (文件偏移, 大小)}, (dynstr 偏移, 大小))。"""
    if len(data) < 64 or data[:4] != b"\x7fELF":
        return {}, None
    shoff = struct.unpack_from("<Q", data, 0x28)[0]
    shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    shnum = struct.unpack_from("<H", data, 0x3C)[0]
    shstrndx = struct.unpack_from("<H", data, 0x3E)[0]
    if not shoff or not shentsize or not shnum:
        return {}, None

    def header(index: int) -> tuple[int, int, int, int, int]:
        pos = shoff + index * shentsize
        name, kind = struct.unpack_from("<II", data, pos)
        offset, size = struct.unpack_from("<QQ", data, pos + 0x18)
        link = struct.unpack_from("<I", data, pos + 0x28)[0]
        return name, kind, offset, size, link

    _, _, str_off, str_size, _ = header(shstrndx)
    strtab = data[str_off : str_off + str_size]

    sections: dict[str, tuple[int, int]] = {}
    dynstr: tuple[int, int] | None = None
    for index in range(shnum):
        name_off, kind, offset, size, link = header(index)
        if name_off >= len(strtab):
            continue
        name = strtab[name_off:].split(b"\0", 1)[0].decode("utf-8", "ignore")
        sections[name] = (offset, size)
        if kind == 3 and name == ".dynstr":
            dynstr = (offset, size)
        if kind == 6 and dynstr is None and link < shnum:
            # .dynamic 的 link 指向字符串表
            _, _, d_off, d_size, _ = header(link)
            dynstr = (d_off, d_size)
    return sections, dynstr


# ---- ARM 运行环境 ---------------------------------------------------------


def _libs_dir(rootfs: Path) -> Path:
    libs = ARM_RUNTIME_DIR / "libs"
    libs.mkdir(parents=True, exist_ok=True)
    roots = [rootfs / "lib/aarch64-linux-gnu", rootfs / "usr/lib/aarch64-linux-gnu"]
    mapping = {
        "libc.so": "libc.so.6",
        "libm.so": "libm.so.6",
        "libdl.so": "libdl.so.2",
        "libpthread.so": "libpthread.so.0",
        "librt.so": "librt.so.1",
        "libz.so": "libz.so.1",
        "libstdc++.so": "libstdc++.so.6",
    }
    for link, real in mapping.items():
        if (libs / link).exists() or (libs / link).is_symlink():
            continue
        for root in roots:
            target = root / real
            if target.is_file():
                try:
                    (libs / link).symlink_to(os.path.relpath(target, libs))
                except OSError:
                    pass
                break
    return libs


_lock = threading.Lock()
_ready: tuple[str, str, Path, Path] | None = None
_failed_at: float = 0.0
_FAIL_COOLDOWN = 300.0


def _ensure_runtime() -> tuple[str, str, Path, Path] | None:
    """返回 (qemu, java, rootfs, libs)；首次调用时准备目录与下载。"""
    global _ready, _failed_at
    if _ready is not None:
        return _ready
    if _failed_at and time.monotonic() - _failed_at < _FAIL_COOLDOWN:
        return None
    with _lock:
        if _ready is not None:
            return _ready
        if _failed_at and time.monotonic() - _failed_at < _FAIL_COOLDOWN:
            return None
        try:
            qemu = _find_qemu()
            java = _ensure_file("jre", ARM_JRE_URL, "bin/java")
            rootfs = _ensure_dir("rootfs", ARM_ROOTFS_URL, "lib/aarch64-linux-gnu/ld-linux-aarch64.so.1")
        except GuardUnpackError as exc:
            logger.warning("ARM 解包环境准备失败：%s", exc)
            _failed_at = time.monotonic()
            return None
        if not qemu or java is None or rootfs is None:
            logger.warning("ARM 解包环境不完整：qemu=%s java=%s rootfs=%s", qemu, java, rootfs)
            _failed_at = time.monotonic()
            return None
        _ready = (qemu, str(java), rootfs, _libs_dir(rootfs))
        logger.info("ARM 解包环境就绪：qemu=%s java=%s", qemu, java)
        return _ready


def _find_qemu() -> str | None:
    candidates = [
        ARM_QEMU_BIN,
        str(ARM_RUNTIME_DIR / "bin" / "qemu-aarch64-static"),
        shutil.which("qemu-aarch64-static") or "",
        "/usr/local/bin/qemu-aarch64-static",
        "/usr/bin/qemu-aarch64-static",
    ]
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return str(Path(path))
    return None


def _ensure_file(kind: str, url: str, find: str) -> Path | None:
    hit = _locate(kind, find)
    if hit is not None:
        return hit
    if not url:
        return None
    _download_tree(kind, url)
    return _locate(kind, find)


def _ensure_dir(kind: str, url: str, find: str) -> Path | None:
    """解压后返回根目录（rootfs 这种整个目录要传给 qemu -L 的）。"""
    hit = _locate(kind, find)
    if hit is not None:
        return hit.parents[find.count("/")]
    if not url:
        return None
    _download_tree(kind, url)
    hit = _locate(kind, find)
    return None if hit is None else hit.parents[find.count("/")]


def _locate(kind: str, find: str) -> Path | None:
    root = ARM_RUNTIME_DIR / kind
    direct = root / find
    if direct.is_file():
        return direct
    if root.is_dir():
        for hit in sorted(root.glob(f"*/{find}")):
            if hit.is_file():
                return hit
    return None


def _download_tree(kind: str, url: str) -> None:
    root = ARM_RUNTIME_DIR / kind
    root.mkdir(parents=True, exist_ok=True)
    archive = ARM_RUNTIME_DIR / f"{kind}.tar.gz"
    if not archive.is_file() or archive.stat().st_size == 0:
        logger.info("下载 ARM 运行时 %s：%s", kind, url)
        try:
            _download(url, archive)
        except (httpx.HTTPError, OSError) as exc:
            raise GuardUnpackError(f"下载 {kind} 失败：{exc}") from exc
    logger.info("解压 ARM 运行时 %s", kind)
    with tarfile.open(archive) as tar:
        try:
            tar.extractall(root, filter="data")
        except TypeError:
            tar.extractall(root)


def _download(url: str, target: Path) -> None:
    part = target.with_suffix(target.suffix + ".part")
    with httpx.Client(timeout=300, follow_redirects=True) as client, client.stream("GET", url) as response:
        response.raise_for_status()
        with part.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    os.replace(part, target)
