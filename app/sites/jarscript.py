"""``csp_*`` 站点驱动：在常驻 JVM Runner 里执行 spider jar 中的类。

对照 FongMi/catvod 的调用约定：
- ``homeContent(filter)``
- ``categoryContent(tid, pg, filter, extend)``
- ``detailContent(ids)``
- ``searchContent(key, quick, pg)``（老版只有两参）
- ``playerContent(flag, id, vipFlags)``
- ``proxy(params)``

``ext`` 写成 ``./json/x.json`` 时，APK 会先按配置地址取回文件内容再传给
spider，这里保持同样的处理。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from ..models import SiteConfig
from ..settings import OKHTTP_UA, SPIDER_OUT_DIR
from ..spider.errors import JarError
from ..spider.jar_runtime import BASE_URL as SERVER_BASE_URL
from ..spider.jar_runtime import runtime
from ..spider.jar_store import resolve as resolve_jar
from .base import DriverError, JsonDriver, headers_dict
from .jsonapi import normalize_result

_EXT_TTL = 3600
_ext_cache: dict[str, tuple[float, str]] = {}


class SiteContext:
    """一次配置加载的共享上下文：spider jar 地址与配置基准地址。"""

    def __init__(self, spider_url: str = "", base_url: str = "", flags: tuple[str, ...] = ()) -> None:
        self.spider_url = spider_url
        self.base_url = base_url
        self.flags = flags

    def url_of(self, ref: str) -> str:
        return resolve_ref(ref, self.base_url)


def resolve_ref(ref: str, base_url: str) -> str:
    """把 ``./spider.jar``、``./json/x.json`` 这类相对引用按配置目录补全。"""
    ref = (ref or "").strip()
    if not ref or ref.startswith(("http://", "https://", "/")):
        return ref
    if base_url.startswith(("http://", "https://")):
        return urljoin(base_url, ref)
    if base_url and Path(base_url).is_dir():
        return str(Path(base_url) / ref)
    return ref


def jar_ref(site: SiteConfig, ctx: SiteContext) -> str:
    """站点真正使用的 jar 引用：站点自带优先，否则用配置声明的 spider（同 APK getJar）。

    ``./spider.jar`` 按配置地址补全，``;md5;xxx`` 摘要后缀原样保留。
    """
    raw = (site.jar or "").strip() or ctx.spider_url
    if not raw:
        return ""
    head, sep, tail = raw.partition(";")
    return ctx.url_of(head.strip()) + (sep + tail if sep else "")


class JarSpiderDriver(JsonDriver):
    def __init__(self, site: SiteConfig, ctx: SiteContext | None = None) -> None:
        super().__init__(site)
        self.ctx = ctx or SiteContext()

    # ---- 基础设施 -------------------------------------------------

    async def _jar(self) -> str:
        ref = jar_ref(self.site, self.ctx)
        if not ref:
            raise DriverError(f"站点「{self.site.title}」没有可用的 spider jar")
        try:
            jar = await resolve_jar(ref)
        except JarError as exc:
            raise DriverError(str(exc)) from exc
        return str(jar)

    async def _extend(self) -> str:
        return await load_ext(self.site.ext, self.ctx.base_url)

    async def _call(
        self,
        method: str,
        args: list[Any] | None = None,
        *,
        params: dict[str, str] | None = None,
        flag: str = "",
        timeout: float | None = None,
    ) -> Any:
        try:
            return await runtime.call(
                jar=await self._jar(),
                api=self.site.api.strip(),
                ext=await self._extend(),
                method=method,
                args=args,
                params=params,
                flag=flag,
                timeout=timeout,
            )
        except JarError as exc:
            raise DriverError(str(exc)) from exc

    # ---- TVBox 接口 -----------------------------------------------

    async def home(self) -> dict[str, Any]:
        data = await self._call("homeContent", [True])
        if not _has_content(data):
            data = await self._call("homeVideoContent", [])
        return normalize_result(_as_dict(data))

    async def category(
        self, tid: str, page: int = 1, extend: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = await self._call("categoryContent", [tid, str(page), True, extend or {}])
        return normalize_result(_as_dict(data))

    async def detail(self, vod_id: str) -> dict[str, Any]:
        data = await self._call("detailContent", [[vod_id]])
        return normalize_result(_as_dict(data))

    async def search(self, keyword: str, page: int = 1, quick: bool = False) -> dict[str, Any]:
        try:
            data = await self._call("searchContent", [keyword, quick, str(page)])
        except DriverError as exc:
            if "searchContent/3" not in str(exc):
                raise
            data = await self._call("searchContent", [keyword, quick])
        return normalize_result(_as_dict(data))

    async def player(self, flag: str, vod_id: str) -> dict[str, Any]:
        data = _as_dict(await self._call("playerContent", [flag, vod_id, list(self.ctx.flags)]))
        headers = headers_dict(data.get("header") or data.get("headers")) or self.headers
        url = str(data.get("url") or "")
        if not url:
            raise DriverError(f"站点「{self.site.title}」没有返回播放地址")

        if _is_local_proxy(url, SERVER_BASE_URL.get()):
            return await self._local_proxy(url, headers)
        if int(data.get("parse") or 0) == 1:
            return {"kind": "parse", "stream": url, "headers": headers, "parse": 1}
        return {"kind": "direct", "stream": url, "headers": headers, "parse": 0}

    async def _local_proxy(self, url: str, headers: dict[str, Any]) -> dict[str, Any]:
        """``http://127.0.0.1:port/proxy?a=b`` 形式的本地代理改走 jar 的 proxy()。"""
        params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        result = await self._call("proxy", [], params=params)
        if not isinstance(result, dict):
            raise DriverError("spider proxy 没有返回内容")
        own = headers_dict(result.get("headers")) or headers_dict(headers)
        body = result.get("body")
        path = str(body.get("path") or "") if isinstance(body, dict) else ""
        text = str(body.get("preview") or "") if isinstance(body, dict) else str(body or "")
        if not path and text.startswith(("http://", "https://")):
            # 少数 spider 直接把最终地址当代理体返回
            return {"kind": "direct", "stream": text, "headers": own, "parse": 0}
        if not path and text:
            path = await dump_body(text)
        if not path:
            raise DriverError("spider proxy 没有返回内容")
        return {
            "kind": "file",
            "stream": path,
            "base": url,
            "headers": own,
            "parse": 0,
        }

    async def proxy(self, params: dict[str, str]) -> Any:
        return await self._call("proxy", [], params=params)


def _has_content(data: Any) -> bool:
    if isinstance(data, str):
        data = _as_dict(data)
    if not isinstance(data, dict):
        return False
    return bool(data.get("class") or data.get("classes") or data.get("list"))


def _as_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, str) and data.strip().startswith(("{", "[")):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise DriverError("spider 返回的内容不是合法 JSON") from exc
        return parsed if isinstance(parsed, dict) else {"list": parsed if isinstance(parsed, list) else []}
    if isinstance(data, list):
        return {"list": data}
    return {}


def _is_local_proxy(url: str, server: str = "") -> bool:
    """spider 用 SpiderApi.getAddress() 拼出来的本地代理链接，要走 jar 的 proxy()。

    手机浏览器访问时地址是局域网 IP，所以除了回环地址还得认本站自己的源地址。
    """
    parts = urlparse(url)
    if "/proxy" not in parts.path:
        return False
    host = (parts.hostname or "").lower()
    if host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
        return True
    return bool(server) and parts.netloc.lower() == urlparse(server).netloc.lower()


async def dump_body(text: str) -> str:
    """Runner 没落盘的代理体写进 out 目录，交给 /spider 提供。"""
    path = Path(SPIDER_OUT_DIR) / f"body-{uuid.uuid4().hex}.bin"
    await asyncio.to_thread(path.write_text, text, "utf-8")
    return str(path)


async def load_ext(ext: Any, base_url: str) -> str:
    """把配置里的 ext 规整成 spider init 需要的字符串。"""
    if ext is None:
        return ""
    if isinstance(ext, (dict, list)):
        return json.dumps(ext, ensure_ascii=False, separators=(",", ":"))
    text = str(ext).strip()
    if not text:
        return ""
    if text.startswith(("{", "[")):
        return text
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith(("./", "../")) or text.endswith(".json"):
        resolved = resolve_ref(text, base_url)
        if resolved.startswith(("http://", "https://")):
            return await _fetch(resolved)
        if Path(resolved).is_file():
            return await asyncio.to_thread(Path(resolved).read_text, "utf-8")
    return text


async def _fetch(url: str) -> str:
    hit = _ext_cache.get(url)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, headers={"User-Agent": OKHTTP_UA}
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
    except (httpx.HTTPError, ValueError):
        return url
    _ext_cache[url] = (time.time() + _EXT_TTL, text)
    return text
