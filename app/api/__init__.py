"""HTTP 接口层：按职责拆分为内容、媒体代理、配置源、用户数据四组路由。"""

from __future__ import annotations

from fastapi import APIRouter

from . import content, media, sources, userdata

router = APIRouter()
for _sub in (content, media, sources, userdata):
    router.include_router(_sub.router)
