"""站点驱动基类。

直连 JSON 接口（type 0 / 1 / 4）在 :mod:`jsonapi`，
外部脚本（Python / JavaScript）在 :mod:`pyscript` / :mod:`jsscript`。
"""

from __future__ import annotations

import base64
import json
from typing import Any

from ..models import SiteConfig
from ..settings import DEFAULT_UA
from ..spider.framework import decode_header


class DriverError(Exception):
    """站点请求失败，消息用于界面提示。"""


def script_dict(value: Any) -> dict[str, Any]:
    """脚本返回值规整为 dict（有些脚本会返回 JSON 字符串）。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if isinstance(data, dict):
                return data
    return {}


def headers_dict(value: Any) -> dict[str, str]:
    """源返回的请求头规整成字典：可能是对象、JSON 字符串，或空的 ``{}``。"""
    return {str(k): str(v) for k, v in script_dict(value).items() if v is not None}


class JsonDriver:
    """TVBox 标准 JSON API 驱动。"""

    def __init__(self, site: SiteConfig) -> None:
        self.site = site

    # ---- 公共部分 -------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        headers = {"User-Agent": self.site.ua or DEFAULT_UA}
        headers.update(decode_header(self.site.extHeader))
        return headers

    @property
    def api(self) -> str:
        """type 4 允许 ext 里携带真实 api。"""
        ext = self.site.ext
        if isinstance(ext, str) and ext.strip():
            try:
                padded = ext.strip() + "=" * (-len(ext.strip()) % 4)
                data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8", "ignore"))
                if isinstance(data, dict) and data.get("api"):
                    return str(data["api"])
            except (ValueError, TypeError, json.JSONDecodeError):
                pass
        return self.site.api

    def _ac(self) -> str:
        return "videolist" if self.site.type == 0 else "detail"

    def _params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        ext = self.site.ext if isinstance(self.site.ext, str) else ""
        if ext:
            params["extend"] = ext
        return params

    # ---- 待实现的接口（M1） ---------------------------------------

    async def home(self) -> dict[str, Any]:
        raise NotImplementedError

    async def category(self, tid: str, page: int = 1, extend: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    async def detail(self, vod_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def search(self, keyword: str, page: int = 1, quick: bool = False) -> dict[str, Any]:
        raise NotImplementedError

    async def player(self, flag: str, vod_id: str) -> dict[str, Any]:
        raise NotImplementedError


class ScriptDriver(JsonDriver):
    """Python / JavaScript 脚本站点的公共骨架。

    两个运行时只是方法名与参数形态不同（``homeContent`` vs ``home``），
    结果规整完全一致；子类通过类属性映射方法名并实现 :meth:`_invoke`。
    """

    # TVBox python 脚本风格的方法名；JS 子类整体覆盖为 drpy 风格。
    m_home = "homeContent"
    m_home_vod = "homeVideoContent"
    m_category = "categoryContent"
    m_detail = "detailContent"
    m_search = "searchContent"
    m_search_fallback: str = "searchContentPage"  # 老脚本没有 searchContent 时的分页版
    m_play = "playerContent"

    def _page_arg(self, page: int) -> Any:
        return str(page)

    def _detail_args(self, vod_id: str) -> list[Any]:
        return [[vod_id]]

    async def _invoke(self, method: str, args: list[Any]) -> Any:
        raise NotImplementedError

    async def home(self) -> dict[str, Any]:
        data = script_dict(await self._invoke(self.m_home, [True]))
        if not data.get("list"):
            try:
                extra = script_dict(await self._invoke(self.m_home_vod, []))
            except DriverError:
                extra = {}
            if extra.get("list"):
                data = {**data, "list": extra["list"]}
        return {
            "class": data.get("class") or [],
            "filters": data.get("filters") or {},
            "list": data.get("list") or [],
            "total": data.get("total"),
        }

    async def category(
        self, tid: str, page: int = 1, extend: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = script_dict(
            await self._invoke(self.m_category, [tid, self._page_arg(page), True, extend or {}])
        )
        return {
            "class": data.get("class") or [],
            "filters": data.get("filters") or {},
            "list": data.get("list") or [],
            "total": data.get("total"),
        }

    async def detail(self, vod_id: str) -> dict[str, Any]:
        data = script_dict(await self._invoke(self.m_detail, self._detail_args(vod_id)))
        items = data.get("list")
        return {"list": items if isinstance(items, list) else []}

    async def search(self, keyword: str, page: int = 1, quick: bool = False) -> dict[str, Any]:
        try:
            data = script_dict(
                await self._invoke(self.m_search, [keyword, quick, self._page_arg(page)])
            )
        except DriverError as exc:
            if not self.m_search_fallback or "没有实现" not in str(exc):
                raise
            data = script_dict(
                await self._invoke(self.m_search_fallback, [keyword, quick, self._page_arg(page)])
            )
        return {"list": data.get("list") or []}

    async def player(self, flag: str, vod_id: str) -> dict[str, Any]:
        data = script_dict(await self._invoke(self.m_play, [flag, vod_id, []]))
        raw_url = data.get("url") or data.get("playUrl") or ""
        if isinstance(raw_url, list):
            values = [str(item).strip() for item in raw_url if isinstance(item, str) and item.strip()]
            preferred = [item for item in values if item.startswith(("http://", "https://"))]
            url = (preferred or values or [""])[-1]
        else:
            url = str(raw_url).strip()
        parse = int(data.get("parse") or 0)
        if not parse and int(data.get("jx") or 0):
            parse = 1
        if not url:
            raise DriverError(f"站点「{self.site.title}」没有返回播放地址")
        return {
            "kind": "parse" if parse else "direct",
            "stream": url,
            "headers": headers_dict(data.get("header")) or self.headers,
            "parse": parse,
        }
