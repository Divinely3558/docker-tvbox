"""站点驱动注册表。"""

from __future__ import annotations

from ..models import SiteConfig
from .base import DriverError, JsonDriver, decode_header, headers_dict, script_dict
from .jarscript import JarSpiderDriver, SiteContext, jar_ref
from .jsonapi import JsonApiDriver, normalize_result
from .jsscript import JsScriptDriver
from .pyscript import PyScriptDriver

DRIVERS = {
    "json": JsonApiDriver,
    "py": PyScriptDriver,
    "js": JsScriptDriver,
    "drpy": JsScriptDriver,
    "spider": JarSpiderDriver,
}


def driver_for(site: SiteConfig, ctx: SiteContext | None = None) -> JsonDriver | None:
    """按站点运行时类型返回驱动；暂不支持的返回 None。"""
    factory = DRIVERS.get(site.runtime)
    if factory is None:
        return None
    if factory is JarSpiderDriver:
        return factory(site, ctx)
    return factory(site)


__all__ = [
    "DRIVERS",
    "DriverError",
    "JarSpiderDriver",
    "JsScriptDriver",
    "JsonDriver",
    "JsonApiDriver",
    "PyScriptDriver",
    "SiteContext",
    "decode_header",
    "driver_for",
    "headers_dict",
    "jar_ref",
    "normalize_result",
    "script_dict",
]
