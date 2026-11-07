"""TVBox Python 脚本的 ``base.spider`` 兼容层。

python 站点的脚本统一写成::

    from base.spider import Spider

    class Spider(Spider):
        def init(self, extend=""): ...
        def homeContent(self, filter): ...
        ...

这里提供脚本需要的基类、``fetch`` 请求助手与模块注入，脚本可以原样运行。
"""

from __future__ import annotations

import base64
import json
import re
import sys
import time
import types
from collections.abc import Callable
from typing import Any

import httpx
import requests
from requests import Response

from ..models import SiteConfig
from ..net import to_ascii_url
from ..settings import DEFAULT_UA


def decode_header(value: str) -> dict[str, str]:
    """解析站点 extHeader：支持 base64 JSON 或直接的 JSON 字符串。"""
    if not value:
        return {}
    text = str(value).strip()
    candidates = [text]
    try:
        padded = text + "=" * (-len(text) % 4)
        candidates.append(base64.urlsafe_b64decode(padded).decode("utf-8", "ignore"))
    except (ValueError, TypeError):
        pass
    for item in candidates:
        try:
            data = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    return {}


_HTML_HEAD = re.compile(r"^\s*(?:<\?xml|<!doctype html|<html|<head|<body|<script)", re.I)


def looks_like_web_page(text: str, content_type: str = "") -> bool:
    """反爬网关拦截脚本地址时会返回 HTML，先认出来，免得把网页当脚本去编译。"""
    return "html" in (content_type or "").lower() or bool(_HTML_HEAD.match(text or ""))


SCRIPT_TTL = 1800


async def fetch_script(
    site: SiteConfig,
    cache: dict[str, tuple[float, str]],
    cache_key: str,
    *,
    error_cls: type[Exception],
    timeout_floor: float = 30,
    transform: Callable[[str], str] | None = None,
) -> str:
    """按 URL 拉取站点脚本并缓存：JS / Python 两个脚本运行时共用同一套下载与校验。

    ``cache`` 由调用方持有（各自的 ``_code_cache``），``transform`` 用于
    下载后对代码做一次性加工（比如 JS 的 import 摊平）。
    """
    url = (site.api or "").strip()
    if not url:
        raise error_cls(f"站点「{site.title}」没有配置脚本地址")
    now = time.monotonic()
    cached = cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    headers = {"User-Agent": site.ua or DEFAULT_UA}
    headers.update(decode_header(site.extHeader))
    timeout = max(float(site.timeOut or 0), timeout_floor)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(to_ascii_url(url))
            response.raise_for_status()
            code = response.text
    except httpx.HTTPStatusError as exc:
        raise error_cls(
            f"站点「{site.title}」脚本下载失败：HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise error_cls(f"站点「{site.title}」脚本下载失败：{exc.__class__.__name__}") from exc
    if not code or not code.strip():
        raise error_cls(f"站点「{site.title}」的脚本内容为空")
    if looks_like_web_page(code, response.headers.get("content-type", "")):
        raise error_cls(
            f"站点「{site.title}」的脚本地址返回的是网页而不是脚本，"
            "通常是被接口的反爬/授权拦住了"
        )
    if transform is not None:
        code = transform(code)
    cache[cache_key] = (now + SCRIPT_TTL, code)
    return code


class Spider:
    """与 TVBox python 运行时同名同协议的基类。"""

    def __init__(self) -> None:
        self.site: dict[str, Any] = {}
        self.ext: Any = ""
        self.key = ""
        self.name = ""
        self.ua = DEFAULT_UA
        self.header: dict[str, str] = {}
        self.headers: dict[str, str] = {}
        self.timeout = 15
        self._session: requests.Session | None = None

    # ---- 可选钩子 -------------------------------------------------

    def getName(self) -> str:
        return self.name

    def init(self, extend: Any = "") -> None:
        """脚本初始化，默认什么都不做。"""

    def homeContent(self, filter: bool) -> dict[str, Any]:
        return {"class": [], "filters": {}}

    def homeVideoContent(self) -> dict[str, Any]:
        return {"list": []}

    def categoryContent(
        self, tid: str, pg: str = "1", filter: bool = True, extend: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {"list": [], "page": pg, "pagecount": 1, "limit": 20, "total": 0}

    def detailContent(self, ids: list[str] | str) -> dict[str, Any]:
        return {"list": []}

    def searchContent(self, key: str, quick: bool, pg: str = "1") -> dict[str, Any]:
        return {"list": []}

    def playerContent(
        self, flag: str, id: str, vipFlags: list[str] | None = None
    ) -> dict[str, Any]:
        return {"parse": 0, "url": "", "header": {}}

    def isVideoFormat(self, url: str) -> bool:
        return False

    def manualVideoCheck(self) -> bool:
        return False

    def localProxy(self, params: Any) -> Any:
        return None

    def destroy(self) -> None:
        session = getattr(self, "_session", None)
        if session is not None:
            session.close()

    # ---- 请求助手 -------------------------------------------------

    def fetch(self, url: str, headers: dict[str, str] | None = None, timeout: float | None = None,
              **kwargs: Any) -> Response:
        """同步请求，返回 ``requests.Response``（脚本常用 ``.text`` / ``.json()``）。"""
        session = getattr(self, "_session", None)
        if session is None:
            session = requests.Session()
            self._session = session

        merged: dict[str, str] = {}
        for attr in ("header", "headers"):
            value = getattr(self, attr, None)
            if isinstance(value, dict):
                merged.update({str(k): str(v) for k, v in value.items()})
        if headers:
            merged.update({str(k): str(v) for k, v in headers.items()})
        if not any(name.lower() == "user-agent" for name in merged):
            merged["User-Agent"] = getattr(self, "ua", "") or DEFAULT_UA

        method = str(kwargs.pop("method", "GET")).upper()
        if kwargs.pop("post", False):
            method = "POST"
        if kwargs.pop("verify", False) is False:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        request_kwargs: dict[str, Any] = {
            "headers": merged,
            "timeout": timeout or getattr(self, "timeout", 15) or 15,
        }
        request_kwargs.update(kwargs)
        return session.request(method, url, **request_kwargs)

    def getProxyUrl(self, url: str) -> str:
        return url


_MODULES_READY = False


def install_base_modules() -> None:
    """把 ``base`` / ``base.spider`` 注入 sys.modules，供脚本 import。"""
    global _MODULES_READY
    if _MODULES_READY:
        return
    package = types.ModuleType("base")
    package.__path__ = []  # 标记为包，允许 base.spider
    spider_module = types.ModuleType("base.spider")
    spider_module.Spider = Spider
    spider_module.__all__ = ["Spider"]
    package.spider = spider_module
    sys.modules["base"] = package
    sys.modules["base.spider"] = spider_module
    _MODULES_READY = True
