"""JavaScript 脚本站点驱动（Node 运行时）。"""

from __future__ import annotations

from typing import Any

from ..spider import js_runtime
from ..spider.js_runtime import JsRuntimeError
from .base import DriverError, ScriptDriver


class JsScriptDriver(ScriptDriver):
    """drpy 风格的方法名；页码用数字、detail 直接传 vod_id。"""

    m_home = "home"
    m_home_vod = "homeVod"
    m_category = "category"
    m_detail = "detail"
    m_search = "search"
    m_search_fallback = ""
    m_play = "play"

    def _page_arg(self, page: int) -> Any:
        return page

    def _detail_args(self, vod_id: str) -> list[Any]:
        return [vod_id]

    async def _invoke(self, method: str, args: list[Any]) -> Any:
        try:
            return await js_runtime.call(self.site, method, args)
        except JsRuntimeError as exc:
            raise DriverError(str(exc)) from exc
