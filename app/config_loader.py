"""配置加载：config.json → 远程/本地 TVBox 配置 → 站点列表。

读取流程：
1. 读取 config.json，得到若干配置源（第一条为默认）；
2. 按源的 url 或 file 拉取原始 JSON；
3. 若配置是 ``{"urls": [...]}`` 的多仓格式，取第一条再拉取；
4. 解析为 :class:`VodConfig`，写入 SQLite 缓存。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import html
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from . import store
from .models import SourceEntry, SourceIndex, SiteConfig, VodConfig
from .net import to_ascii_url
from .settings import BASE_DIR, CONFIG_FILE, CONFIG_TIMEOUT, DEFAULT_UA, OKHTTP_UA


class ConfigError(Exception):
    """配置读取或解析失败，消息直接用于界面展示。"""


logger = logging.getLogger("docktvbox.config")


# 接口导航页里的链接：优先取 data-link / data-copy，其次抓页面内所有 http 地址
HTML_LINK_ATTR = re.compile(r'data-(?:link|copy)\s*=\s*"([^"]+)"', re.I)
HTML_URL = re.compile(r'https?://[^\s"\'<>]+')
MAX_HTML_CANDIDATES = 4
HTML_PROBE_TIMEOUT = 8.0


def load_source_index() -> SourceIndex:
    """读取 config.json（只读，永不写回）。"""
    if not CONFIG_FILE.exists():
        raise ConfigError(f"找不到配置文件：{CONFIG_FILE}")
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"config.json 不是合法 JSON：第 {exc.lineno} 行 {exc.msg}") from exc
    if isinstance(raw, list):  # 兼容直接写数组的简写形式
        raw = {"sources": raw}
    if not isinstance(raw, dict):
        raise ConfigError("config.json 根节点必须是对象")
    index = SourceIndex.model_validate(raw)
    if not index.sources:
        raise ConfigError("config.json 里没有任何源，请在 sources 中添加")
    for entry in index.sources:
        if not entry.name:
            entry.name = entry.url or Path(entry.file).name or "未命名源"
    return index


def _decode_json(text: str) -> dict[str, Any]:
    """解析 JSON 文本，兼容 base64 编码的配置。"""
    text = text.lstrip("\ufeff").strip()
    if text.startswith("<"):
        raise ConfigError("该地址返回的是网页而不是 JSON 配置，请填写配置 JSON 的直链")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        compact = re.sub(r"\s+", "", text)
        if not compact or not re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact):
            raise ConfigError("配置内容不是合法 JSON") from None
        try:
            padded = compact + "=" * (-len(compact) % 4)
            data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8", "ignore"))
        except (binascii.Error, ValueError, json.JSONDecodeError) as exc:
            raise ConfigError("配置内容既不是 JSON，也不是可解码的 base64 JSON") from exc
    if not isinstance(data, dict):
        raise ConfigError("配置根节点必须是 JSON 对象")
    return data


def _dir_of(url: str) -> str:
    """配置地址所在目录，用于解析 ./spider.jar、./json/x.json 这类相对引用。"""
    return urljoin(url, "./") if url.startswith(("http://", "https://")) else url


async def _read_raw(entry: SourceEntry, headers: dict[str, str]) -> tuple[dict[str, Any], str]:
    """读取单个源的原始 JSON 与它所在的目录，返回 ``(配置, 基准地址)``。"""
    if entry.file:
        path = Path(entry.file)
        if not path.is_absolute():
            candidates = [CONFIG_FILE.parent / path, BASE_DIR / path]
            path = next((p for p in candidates if p.exists()), candidates[0])
        if not path.exists():
            raise ConfigError(f"本地配置不存在：{path}")
        return _decode_json(path.read_text(encoding="utf-8-sig")), f"{path.parent}/"

    if not entry.url:
        raise ConfigError(f"源「{entry.title}」没有配置 url 或 file")

    request_headers = {"User-Agent": DEFAULT_UA, "Accept": "application/json, text/plain, */*"}
    request_headers.update(headers)
    text, final_url = await _fetch_config(entry, request_headers)

    if text.lstrip("\ufeff").strip().startswith("<"):
        # 部分配置站按 UA 分流：浏览器 UA 会跳到留言页，okhttp UA 才返回 JSON。
        if request_headers.get("User-Agent") != OKHTTP_UA:
            retry_headers = {**request_headers, "User-Agent": OKHTTP_UA}
            try:
                retry_text, retry_url = await _fetch_config(entry, retry_headers)
            except ConfigError:
                retry_text = ""
            if retry_text and not retry_text.lstrip("\ufeff").strip().startswith("<"):
                logger.info("源「%s」浏览器 UA 返回网页，改用 okhttp UA 拿到 JSON", entry.title)
                return _decode_json(retry_text), _dir_of(retry_url)
        return await _resolve_html(entry, text, final_url, request_headers)
    return _decode_json(text), _dir_of(final_url)


async def _fetch_config(entry: SourceEntry, headers: dict[str, str]) -> tuple[str, str]:
    """按给定请求头拉取配置，返回 ``(文本, 最终地址)``。"""
    try:
        async with httpx.AsyncClient(
            timeout=CONFIG_TIMEOUT, follow_redirects=True, headers=headers
        ) as client:
            response = await client.get(to_ascii_url(entry.url))
            response.raise_for_status()
            return response.text, str(response.url)
    except httpx.HTTPStatusError as exc:
        raise ConfigError(
            f"源「{entry.title}」返回 HTTP {exc.response.status_code}，请检查地址或稍后重试"
        ) from exc
    except httpx.HTTPError as exc:
        raise ConfigError(f"源「{entry.title}」请求失败：{exc.__class__.__name__}") from exc


def _html_candidates(text: str, base_url: str) -> list[str]:
    """从接口导航页里挑出可能是配置 JSON 的地址。"""
    found = [html.unescape(item) for item in HTML_LINK_ATTR.findall(text)]
    found += [html.unescape(item) for item in HTML_URL.findall(text)]
    result: list[str] = []
    seen: set[str] = set()
    for item in found:
        url = urljoin(base_url, item.strip())
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        if url.split("?")[0].lower().endswith(
            (".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".css", ".js", ".ico")
        ):
            continue
        result.append(url)
    return result


async def _probe_config(client: httpx.AsyncClient, url: str) -> tuple[dict[str, Any], str] | None:
    try:
        response = await client.get(to_ascii_url(url))
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    text = response.text.lstrip("\ufeff").strip()
    if text.startswith("<"):
        return None
    try:
        data = _decode_json(text)
    except ConfigError:
        return None
    if data.get("sites") or data.get("urls"):
        return data, _dir_of(str(response.url))
    return None


async def _resolve_html(
    entry: SourceEntry, text: str, base_url: str, headers: dict[str, str]
) -> tuple[dict[str, Any], str]:
    """地址是接口导航页时，自动尝试页内列出的配置直链。"""
    candidates = [
        url
        for url in _html_candidates(text, base_url)
        if url != entry.url and url != base_url
    ][:MAX_HTML_CANDIDATES]
    if not candidates:
        raise ConfigError("该地址返回的是网页而不是 JSON 配置，且页面中没有找到配置链接")
    async with httpx.AsyncClient(
        timeout=HTML_PROBE_TIMEOUT, follow_redirects=True, headers=headers
    ) as client:
        results = await asyncio.gather(
            *(_probe_config(client, url) for url in candidates), return_exceptions=True
        )
    for url, hit in zip(candidates, results, strict=True):
        if isinstance(hit, tuple):
            logger.info("源「%s」从导航页解析到配置：%s", entry.title, url)
            return hit
    tried = "、".join(candidates)
    raise ConfigError(f"该地址返回的是网页而不是 JSON 配置，页面内链接均不可用：{tried}")


async def _load_dict(entry: SourceEntry, headers: dict[str, str], depth: int = 0) -> tuple[dict[str, Any], str]:
    """读取配置，必要时展开 ``urls`` 多仓格式（只取第一条）。"""
    data, base = await _read_raw(entry, headers)
    if data.get("msg"):
        raise ConfigError(f"源「{entry.title}」返回错误：{data['msg']}")

    urls = data.get("urls")
    if not data.get("sites") and isinstance(urls, list) and urls:
        if depth >= 1:
            raise ConfigError("配置的多仓层级过深，已停止解析")
        first = urls[0]
        if isinstance(first, str):
            depot = SourceEntry(name=entry.title, url=first)
        elif isinstance(first, dict):
            depot = SourceEntry(
                name=first.get("name") or entry.title,
                url=first.get("url") or "",
                file=first.get("file") or "",
                headers=first.get("headers") or headers,
            )
        else:
            raise ConfigError("urls 数组元素格式不正确")
        return await _load_dict(depot, dict(depot.headers) or headers, depth + 1)
    return data, base


def _dedupe_sites(sites: list[SiteConfig]) -> list[SiteConfig]:
    seen: dict[str, int] = {}
    result: list[SiteConfig] = []
    for site in sites:
        key = site.key or site.api
        if not key:
            continue
        if not site.name:
            site.name = site.key
        if key in seen:
            # 同 key 站点后者覆盖前者，与 TVBox 行为一致
            result[seen[key]] = site
            continue
        seen[key] = len(result)
        result.append(site)
    return result


def parse_vod_config(raw: dict[str, Any], source_name: str) -> VodConfig:
    """把原始字典解析为 :class:`VodConfig`。"""
    try:
        config = VodConfig.model_validate(raw)
    except Exception as exc:  # pydantic 校验错误统一转成中文提示
        raise ConfigError(f"源「{source_name}」配置格式不正确：{exc}") from exc
    config.sites = _dedupe_sites(config.sites)
    if not config.sites:
        raise ConfigError(f"源「{source_name}」没有可用的 sites，无法使用")
    return config


def site_payload(site: SiteConfig) -> dict[str, Any]:
    """站点在接口与页面中使用的扁平结构。"""
    return {
        "key": site.key or site.api,
        "name": site.title,
        "type": site.type,
        "api": site.api,
        "host": site.api_host,
        "runtime": site.runtime,
        "runtime_label": site.runtime_label,
        "supported": site.supported,
        "searchable": bool(site.searchable),
        "filterable": bool(site.filterable),
    }


def config_meta(config: VodConfig, entry_name: str, base_url: str = "") -> dict[str, Any]:
    return {
        "source_name": entry_name,
        "base_url": base_url,
        "site_count": len(config.sites),
        "supported_count": len(config.supported_sites),
        "spider": config.spider,
        "notice": config.notice,
        "logo": config.logo,
        "wallpaper": config.wallpaper,
        "parse_count": len(config.parses),
        "parses": [
            {
                "name": parse.name,
                "type": parse.type,
                "url": parse.url,
                "ext": parse.ext if isinstance(parse.ext, (str, int, float)) else "",
            }
            for parse in config.parses
        ],
        "flag_count": len(config.flags),
        "flags": list(config.flags),
        "live_count": len(config.lives),
    }


async def load_from_entry(entry: SourceEntry) -> tuple[VodConfig, dict[str, Any]]:
    headers = dict(entry.headers or {})
    raw, base = await _load_dict(entry, headers)
    config = parse_vod_config(raw, entry.title)
    return config, config_meta(config, entry.title, base)


async def get_sites_for_source(source_id: int, force: bool = False) -> dict[str, Any]:
    """获取某个源的站点列表，优先使用数据库缓存。

    返回结构：``{"sites": [...], "meta": {...}, "cached_at": str, "stale": bool}``
    """
    source = await store.get_source(source_id)
    if not source:
        raise ConfigError("源不存在或已被移除，请刷新页面")

    cache = None if force else await store.load_site_cache(source_id)
    if cache:
        return cache

    try:
        headers = json.loads(source["headers"] or "{}")
    except json.JSONDecodeError:
        headers = {}
    entry = SourceEntry(
        name=source["name"],
        url=source["url"],
        file=source["file"],
        headers=headers,
        enabled=bool(source["enabled"]),
    )

    try:
        config, meta = await load_from_entry(entry)
    except ConfigError as exc:
        fallback = await store.load_site_cache(source_id)
        if fallback:  # 网络失败时退回旧缓存，但标记过期
            fallback["stale"] = True
            fallback["error"] = str(exc)
            return fallback
        raise

    payload = [site_payload(site) for site in config.sites]
    raw_sites = [site.model_dump(exclude_none=True, mode="json") for site in config.sites]
    await store.save_site_cache(source_id, payload, meta, raw_sites)
    return {"sites": payload, "meta": meta, "raw_sites": raw_sites, "stale": False, "error": ""}
