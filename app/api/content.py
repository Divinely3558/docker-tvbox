"""内容接口：首页、分类、详情、搜索、播放。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import content, health, parses, proxy, store
from ..content import site_info
from ..models import SiteConfig
from ..settings import HOME_TIMEOUT, LITE_MODE, LITE_SEARCH_SITE, SEARCH_SITE_TIMEOUT
from ..sites import DriverError, headers_dict

router = APIRouter()
logger = logging.getLogger("docktvbox.api.content")


def source_info(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row["id"], "name": row["name"]}


async def _context(site_key: str | None) -> tuple[dict[str, Any], SiteConfig]:
    try:
        ctx = await content.load_sites()
    except content.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        site = content.pick_site(ctx["sites"], site_key)
    except content.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ctx, site


def _driver_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


def _safe_driver_error(exc: Exception) -> HTTPException:
    """把非预期异常也转成 502，避免单个站点问题让整页 500。"""
    if isinstance(exc, (DriverError, content.ContentError, HTTPException)):
        return exc if isinstance(exc, HTTPException) else _driver_error(exc)
    logger.warning("内容接口非预期异常：%s", type(exc).__name__, exc_info=exc)
    return HTTPException(status_code=502, detail=f"内容加载失败：{exc}")


@router.get("/api/home")
async def api_home(site: str | None = Query(default=None)) -> dict[str, Any]:
    ctx, site_cfg = await _context(site)
    try:
        # 与页面路由一致的硬超时：单站卡顿（如失效的直播站）不能挂死接口。
        data = await asyncio.wait_for(
            content.home(site_cfg, ctx["site_ctx"]), timeout=HOME_TIMEOUT
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=502,
            detail=f"站点「{site_cfg.title}」加载超时（{HOME_TIMEOUT:.0f} 秒），请换源",
        ) from None
    except Exception as exc:
        raise _safe_driver_error(exc) from exc
    return {
        "source": source_info(ctx["source"]),
        "site": site_info(site_cfg),
        "stale": ctx["stale"],
        **data,
    }


@router.post("/api/home-site")
async def api_home_site(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """设置首页数据源（当前配置内的某个站点），按配置源分别记忆。"""
    key = str(payload.get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="缺少站点标识")
    try:
        ctx = await content.load_sites()
    except content.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        site = content.pick_site(ctx["sites"], key)
    except content.ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await store.set_state(f"home_site:{ctx['source']['id']}", site.key or site.api)
    return {"ok": True, "site": site_info(site)}


@router.get("/api/category")
async def api_category(
    tid: str = Query(...),
    site: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    ext: str = Query(default="", description="筛选条件 JSON"),
) -> dict[str, Any]:
    ctx, site_cfg = await _context(site)
    extend: dict[str, Any] | None = None
    if ext:
        try:
            extend = json.loads(ext)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="筛选条件不是合法 JSON") from exc
        if not isinstance(extend, dict):
            raise HTTPException(status_code=400, detail="筛选条件必须是对象")
    try:
        data = await asyncio.wait_for(
            content.category(site_cfg, tid, page, extend, ctx["site_ctx"]),
            timeout=HOME_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=502,
            detail=f"站点「{site_cfg.title}」分类加载超时（{HOME_TIMEOUT:.0f} 秒），请换源",
        ) from None
    except Exception as exc:
        raise _safe_driver_error(exc) from exc
    return {
        "source": source_info(ctx["source"]),
        "site": site_info(site_cfg),
        "tid": tid,
        "page": page,
        **data,
    }


@router.get("/api/detail")
async def api_detail(
    vod_id: str = Query(..., alias="id"),
    site: str | None = Query(default=None),
) -> dict[str, Any]:
    ctx, site_cfg = await _context(site)
    try:
        vod = await content.detail(site_cfg, vod_id, ctx["site_ctx"])
    except Exception as exc:
        raise _safe_driver_error(exc) from exc
    return {
        "source": source_info(ctx["source"]),
        "site": site_info(site_cfg),
        "vod": vod,
        "favorite": await store.is_favorite(site_info(site_cfg)["key"], vod_id),
    }


@router.get("/api/search")
async def api_search(
    wd: str = Query(..., min_length=1),
    site: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
) -> dict[str, Any]:
    ctx = await content.load_sites()
    try:
        # 轻量模式只搜索当前站点：全站并发会同时拉起多个 JVM，CPU/内存不可控。
        if site or LITE_MODE:
            site_cfg = content.pick_site(ctx["sites"], site or (LITE_SEARCH_SITE or None))
            try:
                items = await asyncio.wait_for(
                    content.search(site_cfg, wd, page, ctx["site_ctx"]),
                    timeout=health.search_timeout(site_cfg, SEARCH_SITE_TIMEOUT),
                )
            except asyncio.TimeoutError:
                health.record_search_timeout(site_cfg)
                raise _driver_error(
                    content.ContentError("搜索超时，请稍后重试")
                ) from None
            results = [{"site": site_info(site_cfg)["key"], "name": site_cfg.title, "list": items}]
        else:
            results = await content.search_all(ctx["sites"], wd, page, ctx=ctx["site_ctx"])
    except Exception as exc:
        raise _safe_driver_error(exc) from exc
    return {
        "source": source_info(ctx["source"]),
        "wd": wd,
        "page": page,
        "results": results,
    }


class PlayRequest(BaseModel):
    site: str = ""
    flag: str = ""
    id: str = Field(..., min_length=1)
    # 解析插件序号（1 起，0 = 自动挑第一个 JSON 解析）；驱动返回的 parse 只是"要不要解析"的开关
    parse: int = 0


@router.post("/api/play")
async def api_play(payload: PlayRequest, request: Request) -> dict[str, Any]:
    ctx, site_cfg = await _context(payload.site or None)
    try:
        data = await content.player(site_cfg, payload.flag, payload.id, ctx["site_ctx"])
    except (DriverError, content.ContentError) as exc:
        raise _driver_error(exc) from exc

    headers = headers_dict(data.get("headers"))
    referer = headers.get("Referer") or headers.get("referer") or ""
    stream = str(data.get("stream") or "")
    kind = str(data.get("kind") or "direct")

    if kind == "parse" and stream:
        try:
            stream = await parses.resolve(
                ctx["meta"].get("parses") or [], stream, payload.parse, headers
            )
        except parses.ParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        kind = "direct"

    if kind == "file":
        # jar spider 的本地代理体：已在服务端落盘，用签名地址提供给播放器。
        path = Path(stream)
        playlist = proxy.sniff_playlist(path)
        return {
            "site": site_info(site_cfg),
            "kind": "direct",
            "stream": "",
            "url": proxy.spider_url(stream, str(data.get("base") or ""), headers, playlist),
            "direct": "",
            "headers": headers,
            "hls": playlist,
            "parse": 0,
        }

    allowed, playlist = False, False
    if stream:
        # 后缀明确的直链不必探测，省掉起播前的一次往返；后缀不明的可能是隐藏 m3u8。
        if proxy.is_m3u8(stream) or not proxy.has_media_suffix(stream):
            allowed, playlist = await proxy.probe(
                stream, request.headers.get("origin", ""), referer
            )
    is_hls = playlist or proxy.is_m3u8(stream)
    proxied = proxy.hls_url(stream, referer) if is_hls else proxy.media_url(stream, referer)
    if is_hls:
        # 没有 .m3u8 后缀的列表不能让浏览器直连：前端按后缀决定播放方式。
        direct = stream if allowed and proxy.is_m3u8(stream) else ""
    else:
        direct = (
            stream
            if proxy.can_direct(stream, referer, request.url.scheme, headers)
            else ""
        )
    return {
        "site": site_info(site_cfg),
        "kind": kind,
        "stream": stream,
        "url": proxied,
        "direct": direct,
        "headers": headers,
        "hls": is_hls,
        "parse": 0,
    }
