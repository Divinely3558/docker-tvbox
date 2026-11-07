"""媒体代理签名与 m3u8 重写。

外链播放地址统一走 ``/media``、``/hls``，避免浏览器侧 CORS / 防盗链问题。
签名只覆盖 ``u``（目标地址）与 ``r``（Referer），密钥来自环境变量。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from .net import to_ascii_url
from .settings import (
    DEFAULT_UA,
    PIC_CACHE_DIR,
    PIC_CACHE_MB,
    PROXY_SECRET,
    SEGMENT_CACHE_DIR,
    SEGMENT_DISK_MB,
    SPIDER_OUT_DIR,
)

# m3u8 标签里的 URI="..." 属性（KEY / MAP / MEDIA 等）
URI_ATTR = re.compile(r'URI="([^"]+)"')

# 媒体请求的超时：连接要快，读取允许慢一些（大分片/低带宽源）。
MEDIA_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=15.0, pool=10.0)

_client: httpx.AsyncClient | None = None
_client_lock: asyncio.Lock | None = None

# 播放列表短缓存：VOD 的 m3u8 基本不变，直播列表只缓存几秒。
PLAYLIST_TTL_VOD = 30.0
PLAYLIST_TTL_LIVE = 2.0
MAX_PLAYLIST_ENTRIES = 200
_playlist_cache: dict[tuple[str, str], tuple[float, str, str]] = {}

# 分片缓存：内存 LRU 服务正在播放的片段，磁盘 LRU 服务拖动与重看。
SEGMENT_CACHE_BYTES = int(os.getenv("SEGMENT_CACHE_MB", "192")) * 1024 * 1024
SEGMENT_MAX_ITEM = 8 * 1024 * 1024
SEGMENT_TTL = 600.0
_segment_cache: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()
_segment_size = 0
_disk_bytes: int | None = None
_disk_pruned = 0.0

# 预取：VOD 起播预热前几片，播放中始终预取后续 2–3 片。
PREFETCH_START = max(0, int(os.getenv("HLS_PREFETCH_START", "3")))
PREFETCH_AHEAD = max(0, int(os.getenv("HLS_PREFETCH_AHEAD", "3")))
PREFETCH_CONCURRENCY = max(1, int(os.getenv("HLS_PREFETCH_CONCURRENCY", "2")))
PREFETCH_TIMEOUT = float(os.getenv("HLS_PREFETCH_TIMEOUT", "10"))
PREFETCH_MAX_TASKS = max(1, int(os.getenv("HLS_PREFETCH_MAX_TASKS", "24")))
MAX_SEGMENT_PLAYLISTS = 60
URGENT_WINDOW = 0.75

# 直连探测：缓存「上游是否允许浏览器直接取流」，顺带记录首块内容是不是 m3u8。
DIRECT_PROBE_TIMEOUT = 3.0
DIRECT_OK_TTL = 600.0
DIRECT_FAIL_TTL = 600.0
MAX_PROBE_ENTRIES = 500
_probe_cache: OrderedDict[str, tuple[float, bool, bool]] = OrderedDict()

# 回环地址：spider 的本地代理地址在本机没有监听者，不做二次抓取。
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


async def get_client() -> httpx.AsyncClient:
    """全局复用的上游客户端，靠连接池省掉每个分片的 DNS/TLS 握手。"""
    global _client, _client_lock
    if _client is None:
        if _client_lock is None:
            _client_lock = asyncio.Lock()
        async with _client_lock:
            if _client is None:
                _client = httpx.AsyncClient(
                    timeout=MEDIA_TIMEOUT,
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=128,
                        max_keepalive_connections=64,
                        keepalive_expiry=120.0,
                    ),
                )
    return _client


async def close_client() -> None:
    global _client, _prefetch_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _prefetch_client is not None:
        await _prefetch_client.aclose()
        _prefetch_client = None


def cached_playlist(url: str, referer: str = "") -> tuple[str, str] | None:
    item = _playlist_cache.get((url, referer))
    if not item:
        return None
    if item[0] <= time.monotonic():
        _playlist_cache.pop((url, referer), None)
        return None
    return item[1], item[2]


def store_playlist(url: str, final_url: str, text: str, referer: str = "") -> float:
    """缓存播放列表，返回缓存时长；直播（无 ENDLIST）只缓存 2 秒。"""
    ttl = PLAYLIST_TTL_VOD if "#EXT-X-ENDLIST" in text else PLAYLIST_TTL_LIVE
    if len(_playlist_cache) >= MAX_PLAYLIST_ENTRIES:
        _playlist_cache.clear()
    _playlist_cache[(url, referer)] = (time.monotonic() + ttl, text, final_url)
    return ttl


def segment_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return SEGMENT_CACHE_DIR / digest[:2] / digest


def cached_segment(url: str) -> tuple[bytes, str] | None:
    item = _segment_cache.get(url)
    if not item:
        return None
    if item[0] <= time.monotonic():
        _drop_segment(url)
        return None
    _segment_cache.move_to_end(url)
    return item[1], item[2]


def _cached_segment_disk(url: str) -> tuple[bytes, str] | None:
    path = segment_path(url)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    mime = "application/octet-stream"
    try:
        meta = json.loads(path.with_suffix(".json").read_text("utf-8"))
        mime = str(meta.get("type") or mime)
    except (OSError, ValueError):
        pass
    return data, mime


async def read_segment(url: str) -> tuple[bytes, str] | None:
    """内存 → 磁盘读取分片，磁盘命中后顺便放回内存 LRU。"""
    hit = cached_segment(url)
    if hit:
        return hit
    hit = await asyncio.to_thread(_cached_segment_disk, url)
    if hit:
        _store_segment_memory(url, hit[0], hit[1])
    return hit


def store_segment(url: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    if len(data) > SEGMENT_MAX_ITEM:
        return
    _store_segment_memory(url, data, content_type)
    _store_segment_disk(url, data, content_type)


def _store_segment_memory(url: str, data: bytes, content_type: str) -> None:
    global _segment_size
    if not SEGMENT_CACHE_BYTES:
        return
    old = _segment_cache.pop(url, None)
    if old:
        _segment_size -= len(old[1])
    _segment_cache[url] = (time.monotonic() + SEGMENT_TTL, data, content_type)
    _segment_size += len(data)
    while _segment_size > SEGMENT_CACHE_BYTES and _segment_cache:
        _drop_segment(next(iter(_segment_cache)))


def _store_segment_disk(url: str, data: bytes, content_type: str) -> None:
    global _disk_bytes
    if SEGMENT_DISK_MB <= 0:
        return
    path = segment_path(url)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(path)
        path.with_suffix(".json").write_text(
            json.dumps({"type": content_type}), "utf-8"
        )
    except OSError:
        tmp.unlink(missing_ok=True)
        return
    if _disk_bytes is not None:
        _disk_bytes += len(data)
    _prune_segments()


def _prune_segments() -> None:
    """磁盘超过上限就按修改时间删掉最旧的分片，控制在 90% 以内。"""
    global _disk_bytes, _disk_pruned
    if SEGMENT_DISK_MB <= 0:
        return
    now = time.monotonic()
    if now - _disk_pruned < 30:
        return
    _disk_pruned = now
    limit = SEGMENT_DISK_MB * 1024 * 1024
    try:
        files = [
            p
            for p in SEGMENT_CACHE_DIR.rglob("*")
            if p.is_file() and p.suffix != ".json" and not p.name.endswith(".tmp")
        ]
    except OSError:
        return
    total = sum(p.stat().st_size for p in files)
    _disk_bytes = total
    if total <= limit:
        return
    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        try:
            size = path.stat().st_size
            path.unlink()
            path.with_suffix(".json").unlink(missing_ok=True)
            total -= size
        except OSError:
            continue
        if total <= limit * 9 // 10:
            break
    _disk_bytes = total


def _drop_segment(url: str) -> None:
    global _segment_size
    item = _segment_cache.pop(url, None)
    if item:
        _segment_size -= len(item[1])


# ---- HLS 预取 ---------------------------------------------------------


class _SegmentPlan:
    __slots__ = ("segments", "referer")

    def __init__(self, segments: list[str], referer: str) -> None:
        self.segments = segments
        self.referer = referer


_plans: OrderedDict[tuple[str, str], _SegmentPlan] = OrderedDict()
_segment_pos: dict[tuple[str, str], tuple[_SegmentPlan, int]] = {}
_prefetch_client: httpx.AsyncClient | None = None
_prefetch_sem: asyncio.Semaphore | None = None
_prefetch_tasks: set[asyncio.Task] = set()
_prefetch_pending: dict[str, asyncio.Task] = {}
_urgent_until = 0.0


def register_segments(final_url: str, referer: str, segments: list[str]) -> None:
    """记住播放列表里的分片顺序，供「播放一片、预取后几片」使用。"""
    if not final_url or not segments:
        return
    key = (final_url, referer)
    old = _plans.pop(key, None)
    if old:
        for segment in old.segments:
            owner = _segment_pos.get((segment, referer))
            if owner and owner[0] is old:
                _segment_pos.pop((segment, referer), None)
    plan = _SegmentPlan(segments, referer)
    _plans[key] = plan
    for index, segment in enumerate(segments):
        _segment_pos[(segment, referer)] = (plan, index)
    while len(_plans) > MAX_SEGMENT_PLAYLISTS:
        _, dropped = _plans.popitem(last=False)
        for segment in dropped.segments:
            owner = _segment_pos.get((segment, referer))
            if owner and owner[0] is dropped:
                _segment_pos.pop((segment, referer), None)


def warm_playlist(segments: list[str], referer: str) -> None:
    """VOD 起播时预热前几片，减少 hls.js 首次取片的等待。"""
    if PREFETCH_START:
        schedule_prefetch(segments[:PREFETCH_START], referer)


def note_segment(url: str, referer: str = "") -> None:
    """一片开始播放后，把后面的分片排进后台队列。"""
    if not PREFETCH_AHEAD:
        return
    owner = _segment_pos.get((url, referer))
    if not owner:
        owner = next((pos for (seg, _), pos in _segment_pos.items() if seg == url), None)
    if not owner:
        return
    plan, index = owner
    schedule_prefetch(plan.segments[index + 1 : index + 1 + PREFETCH_AHEAD], plan.referer)


async def get_prefetch_client() -> httpx.AsyncClient:
    """预取单独用 2 条连接，避免和播放中的急请求抢连接池。"""
    global _prefetch_client
    if _prefetch_client is None:
        _prefetch_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=PREFETCH_TIMEOUT, write=10.0, pool=5.0),
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=PREFETCH_CONCURRENCY,
                max_keepalive_connections=PREFETCH_CONCURRENCY,
                keepalive_expiry=120.0,
            ),
        )
    return _prefetch_client


def _prefetch_gate() -> asyncio.Semaphore:
    global _prefetch_sem
    if _prefetch_sem is None:
        _prefetch_sem = asyncio.Semaphore(PREFETCH_CONCURRENCY)
    return _prefetch_sem


def prefetch_pending(url: str) -> asyncio.Task | None:
    return _prefetch_pending.get(url)


async def wait_prefetch(url: str, timeout: float = 2.5) -> None:
    """浏览器正好请求到预取中的分片时，等它落盘而不是重复回源。"""
    task = _prefetch_pending.get(url)
    if not task:
        return
    try:
        async with asyncio.timeout(timeout):
            await asyncio.shield(task)
    except Exception:  # noqa: BLE001 预取失败不影响正常请求
        return


def mark_urgent() -> None:
    """Range/拖动请求优先：短暂暂停新的后台预取。"""
    global _urgent_until
    _urgent_until = time.monotonic() + URGENT_WINDOW


def schedule_prefetch(urls: list[str], referer: str) -> None:
    if not urls:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for url in urls:
        if url in _prefetch_pending or cached_segment(url):
            continue
        if len(_prefetch_pending) >= PREFETCH_MAX_TASKS:
            return
        task = loop.create_task(_prefetch_one(url, referer))
        _prefetch_pending[url] = task
        _prefetch_tasks.add(task)
        task.add_done_callback(lambda done, key=url: _prefetch_done(key, done))


def _prefetch_done(url: str, task: asyncio.Task) -> None:
    _prefetch_pending.pop(url, None)
    _prefetch_tasks.discard(task)
    if not task.cancelled():
        try:
            task.exception()
        except Exception:  # noqa: BLE001 后台任务异常只看日志
            pass


async def _prefetch_one(url: str, referer: str) -> None:
    if _urgent_until > time.monotonic():
        await asyncio.sleep(min(URGENT_WINDOW, _urgent_until - time.monotonic()))
    async with _prefetch_gate():
        if await read_segment(url):
            return
        headers = request_headers(referer)
        headers["Accept-Encoding"] = "identity"
        try:
            client = await get_prefetch_client()
            async with asyncio.timeout(PREFETCH_TIMEOUT):
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 400:
                        return
                    declared = response.headers.get("content-length") or ""
                    if declared.isdigit() and int(declared) > SEGMENT_MAX_ITEM:
                        return
                    buffer = bytearray()
                    async for chunk in response.aiter_bytes():
                        buffer.extend(chunk)
                        if len(buffer) > SEGMENT_MAX_ITEM:
                            return
                    content_type = response.headers.get(
                        "content-type", "application/octet-stream"
                    )
            data = bytes(buffer)
            if not data or data.lstrip().startswith(b"#EXTM3U"):
                return
            await asyncio.to_thread(store_segment, url, data, content_type)
        except (httpx.HTTPError, TimeoutError, ValueError, OSError):
            return


async def probe(url: str, origin: str = "", referer: str = "") -> tuple[bool, bool]:
    """取流探测，返回 ``(可直连, 是播放列表)``。

    很多 spider 的 m3u8 地址没有 .m3u8 后缀，只能读首块内容判断类型。
    """
    now = time.monotonic()
    cached = _probe_cache.get(url)
    if cached and cached[0] > now:
        _probe_cache.move_to_end(url)
        return cached[1], cached[2]

    allowed = False
    playlist = False
    headers = {"User-Agent": DEFAULT_UA, "Accept": "*/*", "Range": "bytes=0-511"}
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer
    try:
        client = await get_client()
        request = client.build_request("GET", url, headers=headers)
        async with asyncio.timeout(DIRECT_PROBE_TIMEOUT):
            response = await client.send(request, stream=True)
            try:
                if response.status_code < 400:
                    allow_origin = (response.headers.get("access-control-allow-origin") or "").strip()
                    allowed = allow_origin == "*" or (
                        bool(origin) and allow_origin.lower() == origin.lower()
                    )
                    head = b""
                    async for chunk in response.aiter_raw():
                        head = chunk[:512]
                        break
                    if not response.headers.get("content-encoding"):
                        playlist = head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"#EXTM3U")
            finally:
                await response.aclose()
    except (httpx.HTTPError, TimeoutError):
        pass

    while len(_probe_cache) >= MAX_PROBE_ENTRIES:
        _probe_cache.popitem(last=False)
    _probe_cache[url] = (now + (DIRECT_OK_TTL if allowed else DIRECT_FAIL_TTL), allowed, playlist)
    return allowed, playlist


def _encode(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode().rstrip("=")


def decode(token: str) -> str:
    if not token:
        return ""
    try:
        padded = token + "=" * (-len(token) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _sign(u: str, r: str) -> str:
    raw = f"{u}.{r}".encode()
    return hmac.new(PROXY_SECRET.encode(), raw, hashlib.sha256).hexdigest()[:32]


def verify(u: str, r: str, s: str) -> bool:
    return bool(u and s) and hmac.compare_digest(_sign(u, r), s)


def build(prefix: str, url: str, referer: str = "") -> str:
    """生成带签名的代理地址。"""
    tu = _encode(url)
    tr = _encode(referer) if referer else ""
    return f"{prefix}?u={tu}&r={tr}&s={_sign(tu, tr)}"


# ---- spider 本地代理（jar 站点 playerContent 返回 127.0.0.1/proxy 时使用）----


def spider_url(path: str, base: str = "", headers: dict[str, str] | None = None,
               playlist: bool = False) -> str:
    """把 Runner 落盘的代理体包装成浏览器可取的签名地址。

    播放列表在地址里带上 ``.m3u8``，前端按后缀决定是否交给 hls.js。
    """
    tf = _encode(path)
    tb = _encode(base)
    th = _encode(json.dumps(headers or {}, ensure_ascii=False, separators=(",", ":")))
    prefix = "/spider/index.m3u8" if playlist else "/spider"
    return f"{prefix}?f={tf}&b={tb}&h={th}&s={_hmac((tf, tb, th))}"


def _hmac(parts: tuple[str, ...]) -> str:
    raw = ".".join(parts).encode()
    return hmac.new(PROXY_SECRET.encode(), raw, hashlib.sha256).hexdigest()[:32]


def sniff_playlist(path: Path) -> bool:
    """只看文件头，判断代理体是不是 m3u8。"""
    try:
        with path.open("rb") as handle:
            return handle.read(64).lstrip().startswith(b"#EXTM3U")
    except OSError:
        return False


def spider_body(f: str, b: str, h: str, s: str) -> tuple[Path, dict[str, str], str]:
    """校验签名并返回 (文件, 响应头, 代理原始地址)。"""
    if not hmac.compare_digest(_hmac((f, b, h)), s or ""):
        raise ValueError("代理地址签名无效")
    path = Path(decode(f)).resolve()
    root = Path(SPIDER_OUT_DIR).resolve()
    if not path.is_file() or root not in path.parents:
        raise ValueError("代理文件不存在")
    try:
        headers = json.loads(decode(h) or "{}")
    except json.JSONDecodeError:
        headers = {}
    return path, {str(k): str(v) for k, v in headers.items() if str(k)}, decode(b)


def media_url(url: str, referer: str = "") -> str:
    return build("/media", url, referer)


def hls_url(url: str, referer: str = "") -> str:
    return build("/hls", url, referer)


# ---- 海报图代理（TVBox 的 ``@Referer=`` / ``@User-Agent=`` 后缀）----

PIC_MAX_BYTES = 12 * 1024 * 1024

_PIC_SUFFIX = re.compile(r"(Referer|User-Agent)=(.*)$", re.I | re.S)
_PIC_MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
)


def split_pic(pic: str) -> tuple[str, str]:
    """拆出海报地址与 Referer：``http://x/a.jpg@Referer=http://y/@User-Agent=UA``。

    从右往左逐段剥离 ``@Key=Value``，中途遇到不认识的片段就原样保留。
    """
    url = (pic or "").strip()
    referer = ""
    while True:
        head, sep, tail = url.rpartition("@")
        if not sep:
            break
        match = _PIC_SUFFIX.match(tail)
        if not match:
            break
        if match.group(1).lower() == "referer":
            referer = match.group(2).strip()
        url = head
    return url, referer


def pic_url(pic: str) -> str:
    """把站点海报地址换成本站签名代理地址，浏览器不会再吃到防盗链。"""
    url, referer = split_pic(pic)
    if not url.startswith(("http://", "https://")) or is_internal(url):
        return url
    return build("/img", url, referer)


def image_type(data: bytes, content_type: str = "") -> str:
    """按内容判断图片类型，顺便挡掉网盘返回的网页/错误页。"""
    head = data[:16]
    for magic, mime in _PIC_MAGIC:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    declared = (content_type or "").split(";")[0].strip().lower()
    return declared if declared.startswith("image/") else ""


def pic_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return PIC_CACHE_DIR / digest[:2] / digest


def cached_pic(url: str) -> tuple[bytes, str] | None:
    path = pic_path(url)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    mime = image_type(data)
    return (data, mime) if mime else None


def store_pic(url: str, data: bytes) -> None:
    if len(data) > PIC_MAX_BYTES:
        return
    path = pic_path(url)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        return
    _prune_pics()


_pic_checked = 0.0


def clear_caches() -> int:
    """清空海报、播放列表、探测与分片缓存，返回删除的文件数。"""
    global _segment_size, _disk_bytes, _disk_pruned
    for task in list(_prefetch_tasks):
        task.cancel()
    _prefetch_tasks.clear()
    _prefetch_pending.clear()
    _plans.clear()
    _segment_pos.clear()
    _playlist_cache.clear()
    _probe_cache.clear()
    _segment_cache.clear()
    _segment_size = 0
    _disk_bytes = None
    _disk_pruned = 0.0
    removed = 0
    for root in (PIC_CACHE_DIR, SEGMENT_CACHE_DIR):
        try:
            files = [path for path in root.rglob("*") if path.is_file()]
        except OSError:
            continue
        for path in files:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed


def _prune_pics() -> None:
    """目录超过上限就按修改时间删掉最旧的一批，避免缓存吃满磁盘。"""
    global _pic_checked
    now = time.monotonic()
    if now - _pic_checked < 60:
        return
    _pic_checked = now
    limit = PIC_CACHE_MB * 1024 * 1024
    try:
        files = [p for p in PIC_CACHE_DIR.rglob("*") if p.is_file()]
    except OSError:
        return
    total = sum(p.stat().st_size for p in files)
    if total <= limit:
        return
    for path in sorted(files, key=lambda p: p.stat().st_mtime):
        try:
            size = path.stat().st_size
            path.unlink()
            total -= size
        except OSError:
            continue
        if total <= limit * 9 // 10:
            break


def is_m3u8(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".m3u8")


def is_internal(url: str) -> bool:
    """回环地址：媒体代理不替外部配置访问本机服务。"""
    return (urlparse(url).hostname or "").lower() in _LOCAL_HOSTS


def stream_url(url: str, referer: str = "") -> str:
    """按地址类型选择媒体或 HLS 代理。"""
    if not url:
        return ""
    if url.startswith(("/media?", "/hls?")):
        return url
    return hls_url(url, referer) if is_m3u8(url) else media_url(url, referer)


def rewrite_m3u8(text: str, base_url: str, referer: str = "") -> str:
    """把 m3u8 内的相对/绝对地址全部换成签名代理地址，并登记分片顺序。"""

    def absolute_of(uri: str) -> str:
        return urljoin(base_url, uri.strip()) if base_url else uri.strip()

    def to_proxy(uri: str) -> str:
        absolute = absolute_of(uri)
        # 非 http 地址与回环地址本机也取不到，原样交给播放器处理。
        if not absolute.startswith(("http://", "https://")) or is_internal(absolute):
            return uri.strip()
        return stream_url(absolute, referer)

    result: list[str] = []
    segments: list[str] = []
    # EXT-X-BYTERANGE 的 URI 指向同一大文件的不同区间，不适合按整片预取。
    media_playlist = "#EXTINF" in text and "#EXT-X-BYTERANGE" not in text
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            line = URI_ATTR.sub(lambda m: f'URI="{to_proxy(m.group(1))}"', line)
            result.append(line)
        else:
            absolute = absolute_of(stripped)
            if absolute.startswith(("http://", "https://")) and not is_internal(absolute):
                segments.append(to_ascii_url(absolute))
            result.append(to_proxy(stripped))
    if media_playlist and segments:
        register_segments(base_url, referer, segments)
        if "#EXT-X-ENDLIST" in text:
            warm_playlist(segments, referer)
    return "\n".join(result) + "\n"


MEDIA_SUFFIXES = (
    ".mp4",
    ".m4v",
    ".mkv",
    ".mov",
    ".webm",
    ".flv",
    ".avi",
    ".ts",
    ".m2ts",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
)


def has_media_suffix(url: str) -> bool:
    return urlparse(url).path.lower().endswith(MEDIA_SUFFIXES)


def can_direct(stream: str, referer: str, page_scheme: str, headers: dict[str, str]) -> bool:
    """浏览器直连：无防盗链、无 Cookie/鉴权头、不混用 HTTP/HTTPS。"""
    if not stream.startswith(("http://", "https://")) or is_internal(stream):
        return False
    if referer:
        return False
    if page_scheme == "https" and stream.startswith("http://"):
        return False
    return not ({"cookie", "authorization"} & {name.lower() for name in headers})


def request_headers(referer: str = "", user_agent: str = "") -> dict[str, str]:
    headers = {"User-Agent": user_agent or DEFAULT_UA}
    if referer:
        headers["Referer"] = referer
    return headers
