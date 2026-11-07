"""Python 脚本站点驱动。"""

from __future__ import annotations

from typing import Any

from ..spider import py_runtime
from ..spider.py_runtime import SpiderRuntimeError
from .base import DriverError, ScriptDriver


class PyScriptDriver(ScriptDriver):
    """把脚本方法的结果映射成内容层需要的结构（方法名映射见基类）。"""

    async def _invoke(self, method: str, args: list[Any]) -> Any:
        try:
            return await py_runtime.call(self.site, method, args)
        except SpiderRuntimeError as exc:
            raise DriverError(str(exc)) from exc
