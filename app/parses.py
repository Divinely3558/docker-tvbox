"""网页解析插件（config 的 parses）。

目前支持 type 1（JSON 解析接口）：``GET {parse.url + 播放页地址}`` 返回
``{"url": "直链"}``。其余类型需要浏览器嗅探，暂不支持。
"""

from __future__ import annotations

from typing import Any

import httpx

from .net import to_ascii_url
from .settings import CONFIG_TIMEOUT, DEFAULT_UA


class ParseError(Exception):
    """解析失败，消息直接用于界面提示。"""


def _pick(parses: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    if 0 < index <= len(parses):
        return parses[index - 1]
    for item in parses:
        if int(item.get("type") or 0) == 1:
            return item
    return parses[0] if parses else None


async def resolve(
    parses: list[dict[str, Any]],
    url: str,
    index: int = 0,
    headers: dict[str, str] | None = None,
) -> str:
    """把需要解析的播放页地址转成可直接播放的直链。"""
    if not parses:
        raise ParseError("当前配置源没有解析插件，无法播放该线路")
    parse = _pick(parses, index)
    if not parse:
        raise ParseError("当前配置源没有解析插件，无法播放该线路")
    if int(parse.get("type") or 0) != 1:
        raise ParseError(
            f"解析插件「{parse.get('name') or '未命名'}」需要网页嗅探，"
            "当前只支持 JSON 解析接口，换一条线路试试"
        )

    base = str(parse.get("url") or "").strip()
    if not base:
        raise ParseError(f"解析插件「{parse.get('name') or '未命名'}」没有配置地址")

    request_headers = {"User-Agent": DEFAULT_UA, "Referer": url}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items()})

    target = to_ascii_url(base + url)
    name = str(parse.get("name") or "未命名")
    try:
        async with httpx.AsyncClient(
            timeout=CONFIG_TIMEOUT, follow_redirects=True, headers=request_headers
        ) as client:
            response = await client.get(target)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ParseError(f"解析插件「{name}」请求失败：{exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise ParseError(f"解析插件「{name}」返回的内容不是 JSON") from exc

    final = ""
    if isinstance(data, dict):
        final = str(data.get("url") or data.get("playUrl") or "")
    if not final.startswith(("http://", "https://")):
        raise ParseError(f"解析插件「{name}」没有返回有效播放地址")
    return final
