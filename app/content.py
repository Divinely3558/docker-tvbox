"""内容服务层。

职责：
- 从 SQLite 缓存里还原完整的站点配置；
- 按站点运行时选择驱动；
- 把驱动返回的 TVBox JSON 规整成页面/接口直接可用的结构；
- 拆分 ``vod_play_from`` / ``vod_play_url`` 为线路与选集。
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

from . import config_loader, health, proxy, store
from .config_loader import ConfigError
from .models import SiteConfig
from .settings import (
    DETAIL_TIMEOUT,
    HOME_BUDGET,
    HOME_TIMEOUT,
    SEARCH_CACHE_TTL,
    SEARCH_SITE_TIMEOUT,
)
from .sites import DriverError, SiteContext, driver_for, jar_ref
from .spider import jar_runtime, jar_store, js_runtime, py_runtime

logger = logging.getLogger("docktvbox.content")


class ContentError(Exception):
    """内容层错误，消息直接用于页面提示。"""


def site_info(site: SiteConfig) -> dict[str, Any]:
    """站点在页面与接口间传递的公共信息。"""
    return {
        "key": site.key or site.api,
        "name": site.title,
        "type": site.type,
        "runtime": site.runtime,
        "runtime_label": site.runtime_label,
    }


# 列表页只需要这些字段，避免把整条 vod 塞进 HTML。
LIST_FIELDS = (
    "vod_id",
    "vod_name",
    "vod_pic",
    "vod_remarks",
    "vod_year",
    "vod_area",
    "vod_total",
)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def compact_vod(raw: dict[str, Any]) -> dict[str, Any]:
    """列表用的精简 vod。"""
    item = {field: _text(raw.get(field)) for field in LIST_FIELDS}
    if not item["vod_remarks"]:
        item["vod_remarks"] = _text(raw.get("vod_note"))
    item["vod_pic"] = proxy.pic_url(item["vod_pic"])
    return item


def full_vod(raw: dict[str, Any]) -> dict[str, Any]:
    """详情用的完整 vod（保留未建模字段）。"""
    item = dict(raw)
    for field in ("vod_id", "vod_name", "vod_pic"):
        item[field] = _text(raw.get(field))
    item["vod_pic"] = proxy.pic_url(item["vod_pic"])
    text = _text(raw.get("vod_content") or raw.get("vod_blurb"))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\u00a0", " ")
    item["vod_content"] = re.sub(r"\n{3,}", "\n\n", text).strip()
    item["play_lines"] = parse_play_lines(raw)
    return item


def parse_play_lines(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """``$$$`` 分线路、``#`` 分集、``$`` 分名称与地址。"""
    froms = [part for part in _text(raw.get("vod_play_from")).split("$$$")]
    groups = _text(raw.get("vod_play_url")).split("$$$")
    lines: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        flag = froms[index] if index < len(froms) and froms[index] else f"线路{index + 1}"
        episodes: list[dict[str, str]] = []
        for item in group.split("#"):
            item = item.strip()
            if not item:
                continue
            name, sep, url = item.partition("$")
            if not sep:
                name, url = item, item
            episodes.append({"name": name.strip() or url.strip(), "url": url.strip()})
        if episodes:
            lines.append({"flag": flag, "episodes": episodes})
    return lines


async def load_sites(source_id: int | None = None) -> dict[str, Any]:
    """读取当前（或指定）配置源的站点配置。"""
    sources = await store.list_sources()
    if not sources:
        raise ContentError("还没有配置源，请先编辑 config.json 的 sources 数组。")

    active_id = source_id or await store.get_active_source_id()
    active = next((row for row in sources if row["id"] == active_id), sources[0])

    try:
        payload = await config_loader.get_sites_for_source(active["id"])
    except ConfigError as exc:
        raise ContentError(str(exc)) from exc
    raw_sites = payload.get("raw_sites") or []
    if raw_sites:
        sites = [SiteConfig.model_validate(item) for item in raw_sites]
    else:
        # 兼容没有 raw_sites 的旧缓存：用扁平字段重建，ext/headers 会缺失。
        sites = [
            SiteConfig(
                key=item.get("key", ""),
                name=item.get("name", ""),
                type=int(item.get("type") or 0),
                api=item.get("api", ""),
                searchable=bool(item.get("searchable", True)),
                filterable=bool(item.get("filterable", True)),
            )
            for item in payload.get("sites", [])
        ]

    if not sites:
        raise ContentError("当前配置源没有解析出任何站点。")

    # 相对地址（./spider.jar、./js/x.js）都以配置实际所在目录为基准，
    # 源地址常被 302 到 /xxx/bhvip.json 这样的子目录。
    meta = payload.get("meta") or {}
    base_url = str(meta.get("base_url") or active.get("url") or "")
    _absolutize_scripts(sites, base_url)

    ctx = SiteContext(
        spider_url=str(meta.get("spider") or ""),
        base_url=base_url,
        flags=tuple(meta.get("flags") or ()),
    )
    _prewarm_jars(sites, ctx)
    return {
        "source": active,
        "sites": sites,
        "site_ctx": ctx,
        "meta": meta,
        "stale": bool(payload.get("stale")),
    }


def _prewarm_jars(sites: list[SiteConfig], ctx: SiteContext) -> None:
    """把还没转换过的 spider jar 丢给后台，首个页面请求不用等 dex2jar。"""
    jar_store.prewarm([jar_ref(site, ctx) for site in sites if site.runtime == "spider"])


def _absolutize_scripts(sites: list[SiteConfig], base_url: str) -> None:
    """配置里的 ``./py/x.py``、``./js/x.js``、drpy 规则地址按源地址补全。"""
    if not base_url.startswith(("http://", "https://")):
        return
    for site in sites:
        api = (site.api or "").strip()
        if api and not api.startswith(("http://", "https://", "csp_", "js:", "py:")):
            if api.startswith(("./", "../", "/")) or api.endswith((".js", ".py")):
                site.api = urljoin(base_url, api)

        if site.runtime != "drpy" or not isinstance(site.ext, str):
            continue
        rule = site.ext.strip()
        if rule and "://" not in rule and not rule.startswith("js:"):
            if rule.startswith(("./", "../", "/")) or rule.endswith(".js"):
                site.ext = urljoin(base_url, rule)


def pick_site(sites: list[SiteConfig], key: str | None = None) -> SiteConfig:
    """按 key 选站点；不指定时取第一个可用站点。"""
    if key:
        for site in sites:
            if (site.key or site.api) == key:
                if not site.supported:
                    raise ContentError(f"站点「{site.title}」的 {site.runtime_label} 运行时暂不支持")
                return site
        raise ContentError(f"配置里找不到站点「{key}」，请重新拉取配置")

    for site in sites:
        if site.supported:
            return site
    raise ContentError("当前配置源没有可用站点，请换一份配置源")


def get_driver(site: SiteConfig, ctx: SiteContext | None = None):
    driver = driver_for(site, ctx)
    if driver is None:
        raise ContentError(f"站点「{site.title}」的运行时暂不支持")
    return driver


def _guard(site: SiteConfig) -> None:
    if health.is_open(site):
        raise ContentError(
            f"站点「{site.title}」连续失败，已暂停 {health.remaining(site)} 秒，"
            "可切换其它站点或稍后再试"
        )


async def _run(site: SiteConfig, factory):
    _guard(site)
    try:
        data = await factory()
    except Exception:
        health.record_failure(site)
        raise
    health.record_success(site)
    return data


async def home(site: SiteConfig, ctx: SiteContext | None = None) -> dict[str, Any]:
    data = await _run(site, lambda: get_driver(site, ctx).home())
    return {
        "class": data.get("class") or [],
        "filters": data.get("filters") or {},
        "list": [compact_vod(item) for item in data.get("list") or []],
        "total": data.get("total"),
    }


async def home_with_fallback(
    sites: list[SiteConfig],
    preferred: SiteConfig | None = None,
    max_tries: int = 6,
    ctx: SiteContext | None = None,
) -> tuple[SiteConfig, dict[str, Any], list[str]]:
    """首页优先用当前站点，失败时自动尝试后面的可用站点。

    候选顺序：当前站点 → 非 JVM 站点（直连/JS/drpy/Python，通常更快且不受加固
    jar 影响）→ 其余 spider 站点。单个站点有超时上限，整页也有总预算，
    避免一份含大量坏站点的配置让首页一直转圈。
    """
    ordered: list[SiteConfig] = []
    if preferred is not None:
        ordered.append(preferred)
    for site in sites:
        if site.supported and site not in ordered:
            ordered.append(site)

    head = ordered[:1]
    rest = ordered[1:]
    sequence = head + [site for site in rest if site.runtime != "spider"] + [
        site for site in rest if site.runtime == "spider"
    ]

    errors: list[str] = []
    deadline = time.monotonic() + HOME_BUDGET
    for site in sequence[:max_tries]:
        left = deadline - time.monotonic()
        if left <= 0:
            errors.append("其余站点：整页加载预算已用完")
            break
        try:
            data = await asyncio.wait_for(home(site, ctx), timeout=min(HOME_TIMEOUT, left))
            return site, data, errors
        except asyncio.TimeoutError:
            errors.append(f"{site.title}：加载超时（{HOME_TIMEOUT:.0f} 秒）")
        except Exception as exc:  # noqa: BLE001 - 逐站兜底，坏站点不能拖垮整页
            errors.append(f"{site.title}：{exc}")
    raise ContentError("首页内容加载失败：" + "；".join(errors[-3:]))


async def category(
    site: SiteConfig,
    tid: str,
    page: int = 1,
    extend: dict[str, Any] | None = None,
    ctx: SiteContext | None = None,
) -> dict[str, Any]:
    data = await _run(site, lambda: get_driver(site, ctx).category(tid, page, extend))
    return {
        "class": data.get("class") or [],
        "filters": data.get("filters") or {},
        "list": [compact_vod(item) for item in data.get("list") or []],
        "total": data.get("total"),
    }


async def detail(site: SiteConfig, vod_id: str, ctx: SiteContext | None = None) -> dict[str, Any]:
    try:
        data = await asyncio.wait_for(
            _run(site, lambda: get_driver(site, ctx).detail(vod_id)),
            timeout=DETAIL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        # 详情页只等有限时间，超时直接转搜索/换源，不让用户干等 45 秒。
        raise ContentError(f"详情加载超时（{DETAIL_TIMEOUT:.0f} 秒），请换源或搜索影片") from None
    items = data.get("list") or []
    if not items:
        raise ContentError("详情接口没有返回内容，可能是影片已下线")
    return full_vod(items[0])


# 站点搜索缓存与并发合并：同一站点同一关键词只打一次上游。
_SEARCH_CACHE: dict[tuple[str, str, int, bool], tuple[float, list[dict[str, Any]]]] = {}
_SEARCH_INFLIGHT: dict[tuple[str, str, int, bool], asyncio.Task] = {}
_SEARCH_CACHE_MAX = 500


def _search_key(
    site: SiteConfig, keyword: str, page: int, quick: bool
) -> tuple[str, str, int, bool]:
    return (site.key or site.api, keyword.strip().lower(), page, bool(quick))


async def _search_fetch(
    site: SiteConfig,
    keyword: str,
    page: int,
    ctx: SiteContext | None,
    quick: bool,
    key: tuple[str, str, int, bool],
) -> list[dict[str, Any]]:
    started = time.monotonic()
    data = await _run(site, lambda: get_driver(site, ctx).search(keyword, page, quick))
    items = [compact_vod(item) for item in data.get("list") or []]
    duration = time.monotonic() - started
    health.record_search(site, duration, len(items))
    if len(_SEARCH_CACHE) >= _SEARCH_CACHE_MAX:
        _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)), None)
    _SEARCH_CACHE[key] = (time.monotonic() + SEARCH_CACHE_TTL, items)
    return items


async def search(
    site: SiteConfig,
    keyword: str,
    page: int = 1,
    ctx: SiteContext | None = None,
    quick: bool = False,
) -> list[dict[str, Any]]:
    key = _search_key(site, keyword, page, quick)
    cached = _SEARCH_CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return [dict(item) for item in cached[1]]
    task = _SEARCH_INFLIGHT.get(key)
    if task is None:
        task = asyncio.create_task(_search_fetch(site, keyword, page, ctx, quick, key))
        _SEARCH_INFLIGHT[key] = task
        task.add_done_callback(lambda _done, k=key: _SEARCH_INFLIGHT.pop(k, None))
    # shield：调用方超时不会取消共享任务，结果仍会写入缓存供后续复用。
    return [dict(item) for item in await asyncio.shield(task)]


async def player(
    site: SiteConfig, flag: str, vod_id: str, ctx: SiteContext | None = None
) -> dict[str, Any]:
    return await _run(site, lambda: get_driver(site, ctx).player(flag, vod_id))


def search_candidates(sites: list[SiteConfig], limit: int = 24) -> list[SiteConfig]:
    """可参与多源搜索的站点：受支持、可搜索、未熔断，并按历史表现排序。"""
    items = [
        site
        for site in sites
        if site.supported and site.searchable and not health.is_open(site)
    ]
    items.sort(key=health.search_rank)
    return items[:limit]


async def search_all(
    sites: list[SiteConfig],
    keyword: str,
    page: int = 1,
    limit: int = 24,
    ctx: SiteContext | None = None,
) -> list[dict[str, Any]]:
    """并行搜索多个站点，单个站点失败不影响其它站点。"""
    candidates = search_candidates(sites, limit)
    semaphore = asyncio.Semaphore(10)

    async def run(site: SiteConfig) -> dict[str, Any]:
        async with semaphore:
            try:
                items = await asyncio.wait_for(
                    search(site, keyword, page, ctx),
                    timeout=health.search_timeout(site, SEARCH_SITE_TIMEOUT),
                )
                return {"site": site.key or site.api, "name": site.title, "list": items}
            except asyncio.TimeoutError:
                health.record_search_timeout(site)
                return {
                    "site": site.key or site.api,
                    "name": site.title,
                    "list": [],
                    "error": "搜索超时",
                }
            except (DriverError, ContentError) as exc:
                return {
                    "site": site.key or site.api,
                    "name": site.title,
                    "list": [],
                    "error": str(exc),
                }

    return list(await asyncio.gather(*(run(site) for site in candidates)))


async def _warm_site(site: SiteConfig, ctx: SiteContext) -> None:
    runtime = site.runtime
    if runtime == "py":
        await py_runtime.prewarm(site)
    elif runtime in ("js", "drpy"):
        await js_runtime.prewarm(site)
    elif runtime == "spider":
        ref = jar_ref(site, ctx)
        if ref:
            jar = await jar_store.resolve(ref)
            await jar_runtime.runtime.prewarm(str(jar))


async def warmup(limit: int = 24) -> None:
    """后台预热脚本下载与 spider JVM 进程，消除首次搜索的冷启动超时。"""
    try:
        data = await load_sites()
    except Exception as exc:  # noqa: BLE001
        logger.warning("站点预热跳过：%s", exc)
        return
    sites = [site for site in data["sites"] if site.supported and site.searchable][:limit]
    ctx = data["site_ctx"]
    semaphore = asyncio.Semaphore(3)

    async def one(site: SiteConfig) -> None:
        async with semaphore:
            try:
                await _warm_site(site, ctx)
            except Exception as exc:  # noqa: BLE001
                logger.debug("预热站点「%s」失败：%s", site.title, exc)

    await asyncio.gather(*(one(site) for site in sites))
    logger.info("站点预热完成：%s 个", len(sites))
