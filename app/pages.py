"""页面路由（Jinja2 服务端渲染）。"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import content, proxy, store
from .settings import TEMPLATES_DIR
from .sites import DriverError

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _short_error(value: Any) -> str:
    """页面只展示异常首行，完整堆栈留在日志里。"""
    text = str(value or "").strip().replace("\\n", "\n")
    line = text.splitlines()[0] if text else ""
    return line if len(line) <= 160 else line[:159] + "…"


templates.env.filters["short_error"] = _short_error
logger = logging.getLogger("docktvbox.pages")

NAV = (
    ("home", "/", "首页"),
    ("mine", "/settings", "我的"),
)


async def _base(page: str) -> dict[str, Any]:
    sources = [
        {
            "id": row["id"],
            "name": row["name"],
            "url": row["url"],
            "file": row["file"],
            "site_count": int(row.get("site_count") or 0),
            "cached_at": row.get("cached_at"),
            "manual": row.get("origin") == "manual",
        }
        for row in await store.list_sources()
    ]
    active_id = await store.get_active_source_id()
    active = next((row for row in sources if row["id"] == active_id), sources[0] if sources else None)
    return {
        "page": page,
        "nav": NAV,
        "sources": sources,
        "active": active,
        "sites": [],
        "site": None,
        "error": "",
        "stale": False,
    }


def _sites_payload(sites: list[Any]) -> list[dict[str, Any]]:
    return [content.site_info(site) for site in sites if site.supported]


async def _render(
    request: Request,
    template: str,
    page: str,
    fill: Callable[[dict[str, Any], dict[str, Any]], Awaitable[Any]],
    *,
    defaults: dict[str, Any] | None = None,
    prepare: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    label: str,
    driver_label: str,
    unknown_msg: str,
) -> HTMLResponse:
    """页面渲染骨架：_base → prepare → load_sites → fill，异常统一落成 ``ctx["error"]``。

    ``fill`` 返回一个 Response 时直接生效（详情页的重定向就用这个出口）。
    """
    ctx = await _base(page)
    if defaults:
        ctx.update(defaults)
    if prepare is not None:
        await prepare(ctx)
    try:
        data = await content.load_sites()
        ctx["sites"] = _sites_payload(data["sites"])
        ctx["stale"] = data["stale"]
        response = await fill(ctx, data)
        if response is not None:
            return response
    except content.ContentError as exc:
        ctx["error"] = str(exc)
    except DriverError as exc:
        ctx["error"] = f"{driver_label}失败：{exc}"
    except Exception:  # noqa: BLE001 页面不能因为单个源异常而白屏
        logger.exception("%s加载失败", label)
        ctx["error"] = unknown_msg
    return templates.TemplateResponse(request, template, ctx)


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request, site: str | None = None) -> HTMLResponse:
    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> None:
        saved_key = site
        if not saved_key and ctx["active"]:
            saved_key = await store.get_state(f"home_site:{ctx['active']['id']}") or None
        try:
            preferred = content.pick_site(data["sites"], saved_key)
        except content.ContentError:
            # 记忆的站点在刷新后可能已不存在，退回第一个可用站点。
            preferred = content.pick_site(data["sites"])
        site_cfg, home, failures = await content.home_with_fallback(
            data["sites"], preferred, ctx=data["site_ctx"]
        )
        if failures:
            ctx["switched"] = (
                f"站点「{preferred.title}」加载失败，已自动切换到「{site_cfg.title}」。"
            )
        ctx["site"] = content.site_info(site_cfg)
        classes = [item for item in home["class"] if item.get("type_id")]
        first_tid = str(classes[0].get("type_id")) if classes else ""
        rows = home["list"]
        # 与 APK 一致：首页默认展示第一个分类（通常是「电影」）的首屏，而不是站点推荐流。
        if first_tid:
            try:
                first_page = await content.category(site_cfg, first_tid, 1, ctx=data["site_ctx"])
                if first_page["list"]:
                    rows = first_page["list"]
                    home = {**home, "page_count": first_page.get("page_count", 1)}
            except (content.ContentError, DriverError):
                pass
        ctx["home"] = {**home, "list": rows}
        ctx["classes"] = home["class"]
        ctx["first_tid"] = first_tid
        ctx["filters"] = (home["filters"] or {}).get(first_tid, [])

    return await _render(
        request,
        "home.html",
        "home",
        fill,
        defaults={"classes": [], "filters": [], "first_tid": ""},
        label="首页",
        driver_label="内容加载",
        unknown_msg="内容加载时出现未知错误，请查看容器日志或更换配置源。",
    )


@router.get("/category", response_class=HTMLResponse)
async def category_page(
    request: Request,
    site: str | None = None,
    tid: str | None = None,
    page: int = 1,
    ext: str = "",
) -> HTMLResponse:
    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> None:
        site_cfg = content.pick_site(data["sites"], site)
        ctx["site"] = content.site_info(site_cfg)
        home = await content.home(site_cfg, data["site_ctx"])
        ctx["classes"] = home["class"]
        current_tid = tid or next(
            (str(item.get("type_id")) for item in home["class"] if item.get("type_id")), ""
        )
        ctx["tid"] = current_tid
        ctx["filters"] = (home["filters"] or {}).get(current_tid, [])
        if current_tid:
            try:
                extend = json.loads(ext) if ext else None
            except json.JSONDecodeError:
                extend = None
            ctx["extend"] = extend if isinstance(extend, dict) else {}
            result = await content.category(site_cfg, current_tid, page, extend, data["site_ctx"])
            ctx["items"] = result["list"]
            ctx["total"] = result.get("total")

    return await _render(
        request,
        "category.html",
        "category",
        fill,
        defaults={
            "tid": tid or "",
            "page_no": page,
            "ext": ext,
            "extend": {},
            "filters": [],
            "items": [],
        },
        label="分类页",
        driver_label="分类加载",
        unknown_msg="分类加载时出现未知错误，请稍后重试。",
    )


@router.get("/detail", response_class=HTMLResponse)
async def detail_page(
    request: Request, id: str, site: str | None = None, name: str = ""
) -> HTMLResponse:
    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> Any:
        try:
            site_cfg = content.pick_site(data["sites"], site)
            ctx["site"] = content.site_info(site_cfg)
            ctx["vod"] = await content.detail(site_cfg, id, data["site_ctx"])
        except (content.ContentError, DriverError) as exc:
            # 搜索型站点（如豆瓣推荐）详情为空，按 APK 的做法转为多源搜索。
            if name:
                return RedirectResponse(f"/search?wd={quote(name)}", status_code=302)
            ctx["error"] = (
                str(exc) if isinstance(exc, content.ContentError) else f"详情加载失败：{exc}"
            )
            return None
        current_key = site_cfg.key or site_cfg.api
        ctx["search_sites"] = [
            {"key": item.key or item.api, "name": item.title}
            for item in content.search_candidates(data["sites"], limit=32)
            if (item.key or item.api) != current_key
        ]
        ctx["favorite"] = await store.is_favorite(ctx["site"]["key"], id)
        ctx["resume"] = _resume_target(ctx["vod"], await store.get_history(ctx["site"]["key"], id))
        return None

    return await _render(
        request,
        "detail.html",
        "detail",
        fill,
        defaults={"vod": None, "resume": None},
        label="详情页",
        driver_label="详情加载",
        unknown_msg="详情加载时出现未知错误，请稍后重试。",
    )


def _resume_target(vod: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any] | None:
    """把历史记录（线路名 + 集名）还原成可直接播放的一集。"""
    if not history or not history.get("episode"):
        return None
    lines = vod.get("play_lines") or []
    line = next((item for item in lines if item["flag"] == history.get("flag")), None)
    if line is None:
        line = next(
            (item for item in lines if any(ep["name"] == history["episode"] for ep in item["episodes"])),
            None,
        )
    if not line:
        return None
    episode = next((ep for ep in line["episodes"] if ep["name"] == history["episode"]), None)
    if not episode:
        return None
    return {
        "flag": line["flag"],
        "episode": episode["name"],
        "url": episode["url"],
        "position": float(history.get("position") or 0),
    }


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request, wd: str = "", site: str | None = None, page: int = 1
) -> HTMLResponse:
    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> None:
        if not wd:
            return
        if site:
            site_cfg = content.pick_site(data["sites"], site)
            ctx["site"] = content.site_info(site_cfg)
            items = await content.search(site_cfg, wd, page, data["site_ctx"])
            ctx["results"] = [
                {"site": ctx["site"]["key"], "name": site_cfg.title, "list": items}
            ]
        else:
            # 多源搜索改为前端分站点并发，结果随到随显示，避免整页等待最慢的站点。
            ctx["search_sites"] = [
                {"key": item.key or item.api, "name": item.title}
                for item in content.search_candidates(data["sites"])
            ]

    return await _render(
        request,
        "search.html",
        "search",
        fill,
        defaults={"wd": wd, "results": [], "page_no": page, "site": None, "active_site": site or ""},
        label="搜索页",
        driver_label="搜索",
        unknown_msg="搜索时出现未知错误，请稍后重试。",
    )


@router.get("/play", response_class=HTMLResponse)
async def play_page(
    request: Request,
    id: str,
    site: str | None = None,
    flag: str = "",
    name: str = "",
    title: str = "",
    vod: str = "",
    pic: str = "",
) -> HTMLResponse:
    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> None:
        ctx["site"] = content.site_info(content.pick_site(data["sites"], site))

    return await _render(
        request,
        "play.html",
        "play",
        fill,
        defaults={
            "episode_id": id,
            "flag": flag,
            "episode_name": name,
            "title": title or "播放",
            "vod_id": vod,
            "pic": pic,
            "active_site": site or "",
        },
        label="播放页",
        driver_label="播放",
        unknown_msg="播放页加载时出现未知错误，请稍后重试。",
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    async def prepare(ctx: dict[str, Any]) -> None:
        # 历史与收藏里的封面可能是 TVBox 带 @Referer 的地址，统一换成图片代理。
        ctx["favorites"] = [
            {**item, "pic": proxy.pic_url(item.get("pic") or "")}
            for item in await store.list_favorites(30)
        ]
        ctx["history"] = [
            {**item, "pic": proxy.pic_url(item.get("pic") or "")}
            for item in await store.list_history(12)
        ]
        ctx.update(await store.aliyun_token_view())

    async def fill(ctx: dict[str, Any], data: dict[str, Any]) -> None:
        ctx["meta"] = data["meta"]
        ctx["site_count"] = len(data["sites"])

    return await _render(
        request,
        "settings.html",
        "mine",
        fill,
        prepare=prepare,
        label="设置页",
        driver_label="设置加载",
        unknown_msg="设置加载时出现未知错误，请稍后重试。",
    )
