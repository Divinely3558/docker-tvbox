"""HTTP 接口层：按职责拆分为内容、媒体代理、用户数据三组路由。"""

from __future__ import annotations

from fastapi import APIRouter

from . import content, media, userdata

router = APIRouter()
for _sub in (content, media, userdata):
    router.include_router(_sub.router)
