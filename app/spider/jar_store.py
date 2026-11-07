"""spider jar 仓库：把配置里的 ``spider`` 地址变成本地可用的 JVM jar。

TVBox/catvod 的 spider 文件通常是「zip 里塞一个 classes.dex」，JVM 不能直接加载，
需要 dex2jar 转换。下载与转换结果按 URL 摘要缓存到 ``data/jars``。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import httpx

from ..net import to_ascii_url
from ..settings import D2J_XMX, OKHTTP_UA, SPIDER_JAR_DIR
from . import guard_unpack
from .errors import JarBroken, JarError

logger = logging.getLogger("docktvbox.jar")

_PREPARE = Path(__file__).resolve().parents[2] / "spider-runtime" / "prepare.sh"
_DEX_MAGIC = b"dex\n"


def key_of(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:16]


def split_qualifier(spider: str) -> tuple[str, str]:
    """``http://x.jar;md5;ABC...`` -> (地址, 摘要)。摘要参与缓存命名，配置换 jar 即失效。"""
    parts = (spider or "").strip().split(";")
    digest = ""
    for index, word in enumerate(parts[1:], 1):
        if word.strip().lower() in {"md5", "sha1", "sha256"} and index + 1 < len(parts):
            digest = parts[index + 1].strip().lower()
            break
    return parts[0].strip(), digest


def classify(path: Path) -> str:
    """jvm-jar / dex-zip / raw-dex / broken"""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except (zipfile.BadZipFile, OSError):
        try:
            with path.open("rb") as handle:
                return "raw-dex" if handle.read(4) == _DEX_MAGIC else "broken"
        except OSError:
            return "broken"
    if "classes.dex" in names:
        return "dex-zip"
    return "jvm-jar" if any(name.endswith(".class") for name in names) else "broken"


def _wrap_dex(raw: Path, out_dir: Path) -> Path:
    """裸 dex 包一层 zip，喂给 dex2jar。"""
    staged = out_dir / f"{raw.stem}-wrapped.jar"
    with zipfile.ZipFile(staged, "w") as archive:
        archive.write(raw, "classes.dex")
    return staged


def convert(raw: Path, target: Path) -> Path:
    """转换是同步阻塞的（dex2jar 要几十秒），调用方放线程里。

    先在目标目录的临时子目录里转换，再原子改名到缓存路径：
    多个进程同时命中同一个 jar 时，不会写出半个文件。
    """
    kind = classify(raw)
    if kind == "broken":
        raise JarBroken(f"spider 文件不是 jar/dex（多半是下载到了网页）：{raw.name}")

    produced = f"{raw.stem}.jar"  # prepare.sh 用输入文件名命名输出
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as staging:
        out_dir = Path(staging)
        if kind == "jvm-jar":
            shutil.copyfile(raw, out_dir / produced)
        else:
            source = _wrap_dex(raw, out_dir) if kind == "raw-dex" else raw
            result = subprocess.run(  # noqa: S603 - 固定脚本，参数不含用户输入
                # prepare.sh 在临时目录里解压，必须给绝对路径
                ["bash", str(_PREPARE), "convert", str(Path(source).resolve()), raw.stem],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "SPIDERS": str(out_dir), "D2J_XMX": D2J_XMX},
            )
            if not (out_dir / produced).is_file():
                raise JarError(f"spider jar 转换失败：{(result.stderr or result.stdout)[-240:]}")
        # 加固 jar：外层 XxxGuard 只是壳，真正能用的 spider 在内层 dex 里。
        # 解包成功后直接缓存内层 jar，之后所有 csp_XxxGuard 都走真实类。
        if guard_unpack.is_guard_jar(raw):
            logger.info("检测到加固 spider，开始离线解包 %s", raw.name)
            inner = out_dir / f"{raw.stem}-inner.jar"
            guard_unpack.unpack(raw, out_dir / produced, inner)
            produced = inner.name
        os.replace(out_dir / produced, target)
    logger.info("spider jar 已转换 %s", target.name)
    return target


def _matches(data: bytes, digest: str) -> bool:
    algo = {32: "md5", 40: "sha1", 64: "sha256"}.get(len(digest))
    return bool(algo) and hashlib.new(algo, data).hexdigest() == digest


async def download(spider: str, timeout: float = 60.0) -> Path:
    """下载 spider 原始文件到 data/jars，返回路径（已存在则跳过）。"""
    SPIDER_JAR_DIR.mkdir(parents=True, exist_ok=True)
    url, digest = split_qualifier(spider)
    if not url.startswith(("http://", "https://")):
        local = Path(url)
        if not local.is_file():
            raise JarError(f"spider 地址既不是 URL 也不是本地文件：{spider}")
        return local

    raw = SPIDER_JAR_DIR / f"{key_of(spider)}.bin"
    if raw.is_file() and raw.stat().st_size > 0:
        if not digest or _matches(raw.read_bytes(), digest):
            return raw
        raw.unlink(missing_ok=True)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True, headers={"User-Agent": OKHTTP_UA}
    ) as client:
        try:
            response = await client.get(to_ascii_url(url))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise JarError(f"spider jar 下载失败：{exc}") from exc
    content = response.content
    if digest and not _matches(content, digest):
        raise JarError("spider jar 摘要校验不通过")
    raw.write_bytes(content)
    logger.info("spider jar 已下载 %s (%d bytes)", raw.name, len(content))
    return raw


async def _resolve(url: str) -> Path:
    raw = await download(url)
    target = SPIDER_JAR_DIR / f"{key_of(url)}.jar"
    marker = SPIDER_JAR_DIR / f"{key_of(url)}.unpacked"
    guarded = guard_unpack.is_guard_jar(raw)
    if target.is_file() and target.stat().st_size > 0:
        # 加固 jar 之前可能被缓存成未解包的 wrapper：等解包成功后再复用。
        if not guarded or marker.is_file():
            return target
        target.unlink(missing_ok=True)
    result = await asyncio.to_thread(convert, raw, target)
    if guarded:
        marker.write_text("", "utf-8")
    return result


_inflight: dict[str, asyncio.Task] = {}


async def resolve(url: str) -> Path:
    """下载 + 转换，返回可直接交给 Runner 的 jar 路径。

    同一 jar 只跑一份：后台预转换与页面请求撞上时共用同一个结果。
    """
    if not url:
        raise JarError("配置没有声明 spider jar 地址")
    task = _inflight.get(url)
    if task is None:
        task = asyncio.create_task(_resolve(url))
        _inflight[url] = task
        task.add_done_callback(lambda _done, key=url: _inflight.pop(key, None))
    return await task


_prewarm_seen: set[str] = set()
_prewarm_tasks: set[asyncio.Task] = set()


def prewarm(refs: list[str], limit: int = 3) -> None:
    """后台下载并转换没见过的 jar：dex2jar 要一分多钟，不该让首个页面请求干等。

    每次只排 ``limit`` 个，避免一次把整份配置的 jar 全转一遍抢 CPU；
    后续页面加载会继续推进剩下的，用户真正点到的站点由 ``resolve`` 兜底。
    """
    todo = [ref for ref in dict.fromkeys(refs) if ref and ref not in _prewarm_seen][:limit]
    if not todo:
        return
    _prewarm_seen.update(todo)
    task = asyncio.create_task(_prewarm_all(todo))
    _prewarm_tasks.add(task)
    task.add_done_callback(_prewarm_tasks.discard)


async def _prewarm_all(refs: list[str]) -> None:
    # 一次只转换一个：dex2jar 的堆要吃 1g 以上，并发会顶满容器内存上限。
    for ref in refs:
        try:
            await resolve(ref)
        except JarBroken as exc:
            # 记住失败：这类文件重试一百次也不会变成 jar，别每次都重新下载。
            logger.info("spider 文件不可用 %s：%s", ref, exc)
        except (JarError, OSError) as exc:
            _prewarm_seen.discard(ref)
            logger.info("预转换 spider jar 失败 %s：%s", ref, exc)
