"""直连 JSON API 驱动（type 0 / 1 / 4）。

参数拼装逻辑对照 FongMi 的 ``SiteApi.java``：
- type 0：``ac=videolist``
- type 1：``ac=detail``，筛选用 ``f=<json>``
- type 4：``ac=detail``，筛选用 ``ext=<base64url json>``，播放用 ``play=<id>&flag=<flag>``
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from .base import DriverError, JsonDriver, headers_dict
from ..net import to_ascii_url


def _b64url(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def normalize_result(data: Any) -> dict[str, Any]:
    """把源返回的 JSON 规整成 ``{list, class, filters}``。"""
    if not isinstance(data, dict):
        raise DriverError("接口返回的不是 JSON 对象")
    if "data" in data and isinstance(data["data"], dict):
        return normalize_result(data["data"])
    result = {
        "list": data.get("list") or [],
        "class": data.get("class") or data.get("classes") or [],
        "filters": data.get("filters") or {},
        "total": data.get("total"),
    }
    if not isinstance(result["list"], list):
        result["list"] = []
    return result


_CATEGORY_PARAM: dict[str, str] = {}


class JsonApiDriver(JsonDriver):
    async def _request(self, base: str, params: dict[str, str]) -> dict[str, Any]:
        url = base or self.api
        if not url:
            raise DriverError(f"站点「{self.site.title}」没有配置 api")
        if url.startswith("/"):
            raise DriverError(f"站点「{self.site.title}」的 api 不是完整地址")
        url = to_ascii_url(url)
        ext = self.site.ext if isinstance(self.site.ext, str) else ""
        payload = {**self._params(), **params}
        timeout = self.site.timeOut or 10
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, headers=self.headers
            ) as client:
                if len(ext) > 1000:
                    response = await client.post(url, data=payload)
                else:
                    response = await client.get(url, params=payload)
                response.raise_for_status()
                return normalize_result(response.json())
        except httpx.HTTPStatusError as exc:
            raise DriverError(
                f"站点「{self.site.title}」返回 HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DriverError(f"站点「{self.site.title}」请求失败：{exc.__class__.__name__}") from exc
        except ValueError as exc:
            raise DriverError(f"站点「{self.site.title}」返回内容不是 JSON") from exc

    async def home(self) -> dict[str, Any]:
        params = {"filter": "true"} if self.site.type == 4 else {}
        return await self._request(self.api, params)

    async def category(
        self, tid: str, page: int = 1, extend: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        extend = extend or {}
        base_params: dict[str, str] = {"ac": self._ac(), "pg": str(page)}
        if extend:
            if self.site.type == 1:
                base_params["f"] = json.dumps(extend, ensure_ascii=False, separators=(",", ":"))
            elif self.site.type == 4:
                base_params["ext"] = _b64url(extend)

        # 少数 MacCMS 站点只认 tid，另一些只认 t：按首次成功结果记住参数名。
        key = self.site.key or self.api
        preferred = _CATEGORY_PARAM.get(key)
        candidates = [preferred] if preferred else ["t", "tid"]
        result: dict[str, Any] = {"list": [], "class": [], "filters": {}}
        for name in candidates:
            data = await self._request(self.api, {**base_params, name: tid})
            if data["list"]:
                if not preferred:
                    _CATEGORY_PARAM[key] = name
                return data
            result = data
        return result

    async def detail(self, vod_id: str) -> dict[str, Any]:
        return await self._request(self.api, {"ac": self._ac(), "ids": vod_id})

    async def search(
        self, keyword: str, page: int = 1, quick: bool = False
    ) -> dict[str, Any]:
        params = {"wd": keyword, "quick": "true" if quick else "false", "extend": ""}
        if page > 1:
            params["pg"] = str(page)
        return await self._request(self.api, params)

    async def player(self, flag: str, vod_id: str) -> dict[str, Any]:
        if self.site.type == 4:
            data = await self._request(self.api, {"play": vod_id, "flag": flag})
            first = data["list"][0] if data["list"] else {}
            url = str(first.get("url") or "")
            parse = int(first.get("parse") or 0)
            if not url:
                raise DriverError(f"站点「{self.site.title}」没有返回播放地址")
            return {
                "kind": "parse" if parse else "direct",
                "stream": url,
                "headers": headers_dict(first.get("header")) or self.headers,
                "parse": parse,
            }
        # type 0 / 1 的选集地址本身就是播放直链或网页地址
        return {"kind": "direct", "stream": vod_id, "headers": self.headers, "parse": 0}
