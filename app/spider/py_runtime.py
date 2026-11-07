"""Python 站点脚本运行时。

脚本按 URL 拉取后在内存里缓存（TTL 30 分钟），每个站点 + ext 组合只
实例化一次，之后复用实例以保留脚本内部状态（cookie、token 等）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import types
from typing import Any

from ..models import SiteConfig
from ..settings import DEFAULT_UA
from .framework import Spider, decode_header, fetch_script, install_base_modules

logger = logging.getLogger("docktvbox.pyscript")

SCRIPT_TIMEOUT = 30

_code_cache: dict[str, tuple[float, str]] = {}
_instances: dict[str, Spider] = {}
_lock = threading.Lock()


class SpiderRuntimeError(Exception):
    """脚本拉取或执行失败。"""


def _extend_text(ext: Any) -> str:
    if ext is None:
        return ""
    if isinstance(ext, str):
        return ext
    try:
        return json.dumps(ext, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(ext)


async def _script_code(site: SiteConfig) -> str:
    return await fetch_script(
        site,
        _code_cache,
        (site.api or "").strip(),
        error_cls=SpiderRuntimeError,
        timeout_floor=SCRIPT_TIMEOUT,
    )


def _configure(instance: Spider, site: SiteConfig, extend: str) -> None:
    instance.site = {"key": site.key, "name": site.name, "type": site.type, "api": site.api}
    instance.ext = extend
    instance.key = site.key or site.api
    instance.name = site.title
    instance.ua = site.ua or DEFAULT_UA
    instance.timeout = site.timeOut or 15
    headers = {"User-Agent": instance.ua}
    headers.update(decode_header(site.extHeader))
    instance.header = headers


def _build_instance(code: str, site: SiteConfig, extend: str) -> Spider:
    install_base_modules()
    module = types.ModuleType(f"docktvbox_spider_{abs(hash(site.api))}")
    module.__file__ = site.api
    namespace = module.__dict__
    try:
        exec(compile(code, site.api or "<py-spider>", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001 脚本自身的错误统一转提示
        logger.exception("站点 %s 脚本执行失败", site.title)
        raise SpiderRuntimeError(f"站点「{site.title}」脚本加载失败：{exc}") from exc

    cls = namespace.get("Spider")
    if not (isinstance(cls, type) and issubclass(cls, Spider) and cls is not Spider):
        candidates = [
            value
            for value in namespace.values()
            if isinstance(value, type) and issubclass(value, Spider) and value is not Spider
        ]
        if not candidates:
            raise SpiderRuntimeError(f"站点「{site.title}」的脚本里没有找到 Spider 类")
        cls = candidates[0]

    try:
        instance = cls()
    except Exception as exc:  # noqa: BLE001
        raise SpiderRuntimeError(f"站点「{site.title}」实例化失败：{exc}") from exc

    _configure(instance, site, extend)
    try:
        instance.init(extend)
    except Exception as exc:  # noqa: BLE001
        logger.exception("站点 %s init 失败", site.title)
        raise SpiderRuntimeError(f"站点「{site.title}」初始化失败：{exc}") from exc
    return instance


def _call_sync(site: SiteConfig, code: str, method: str, args: list[Any], extend: str) -> Any:
    cache_key = f"{site.api}|{extend}"
    with _lock:
        instance = _instances.get(cache_key)
        if instance is None:
            instance = _build_instance(code, site, extend)
            _instances[cache_key] = instance

    handler = getattr(instance, method, None)
    if handler is None:
        raise SpiderRuntimeError(f"站点「{site.title}」的脚本没有实现 {method}")
    try:
        result = handler(*args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("站点 %s 调用 %s 失败", site.title, method)
        raise SpiderRuntimeError(f"站点「{site.title}」执行失败：{exc}") from exc

    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return result


def _reset(site: SiteConfig) -> None:
    """失败后丢弃实例，下一轮重新初始化。"""
    prefix = f"{site.api}|"
    with _lock:
        for key in [key for key in _instances if key.startswith(prefix)]:
            _instances.pop(key, None)


async def call(site: SiteConfig, method: str, args: list[Any] | None = None) -> Any:
    """在后台线程里执行脚本方法，返回脚本原始结果。"""
    try:
        code = await _script_code(site)
        extend = _extend_text(site.ext)
        return await asyncio.to_thread(_call_sync, site, code, method, list(args or []), extend)
    except SpiderRuntimeError:
        _reset(site)
        raise


def _ensure_instance(site: SiteConfig, code: str, extend: str) -> None:
    cache_key = f"{site.api}|{extend}"
    with _lock:
        if cache_key in _instances:
            return
        _instances[cache_key] = _build_instance(code, site, extend)


async def prewarm(site: SiteConfig) -> None:
    """后台提前下载脚本并初始化实例，避免首次搜索撞冷启动超时。"""
    try:
        code = await _script_code(site)
        extend = _extend_text(site.ext)
        await asyncio.to_thread(_ensure_instance, site, code, extend)
    except SpiderRuntimeError:
        _reset(site)


def clear_cache() -> None:
    _code_cache.clear()
    with _lock:
        _instances.clear()
