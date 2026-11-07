"""FastAPI 入口：装配应用、生命周期、中间件与全局异常兜底。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import api, config_loader, content, pages, proxy, store
from .config_loader import ConfigError
from .settings import (
    LOG_LEVEL,
    PROXY_SECRET_RANDOM,
    STATIC_DIR,
    WARMUP_ENABLED,
    ensure_dirs,
)
from .spider.jar_runtime import BASE_URL as SPIDER_BASE_URL
from .spider.jar_runtime import runtime as jar_runtime

logging.basicConfig(level=LOG_LEVEL.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("docktvbox")
if PROXY_SECRET_RANDOM:
    logger.warning(
        "PROXY_SECRET 未配置，已生成随机密钥：重启后旧的代理地址失效，"
        "生产环境建议通过环境变量配置固定值"
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_dirs()
    jar_runtime.start_reaper()
    await store.init_db()
    sources: list[dict[str, Any]] = []
    try:
        index = config_loader.load_source_index()
        await store.sync_sources(index.sources)
        sources = await store.list_sources()
        active = await store.get_active_source_id()
        if not sources:
            logger.warning("config.json 中没有可用源")
        elif active not in {row["id"] for row in sources}:
            await store.set_active_source(sources[0]["id"])
            logger.info("默认使用第一个源：%s", sources[0]["name"])
    except ConfigError as exc:
        logger.error("配置源初始化失败：%s", exc)
    if WARMUP_ENABLED and sources:
        # 后台预热，不阻塞启动；用户首次搜索时站点已经是热的。
        asyncio.create_task(content.warmup())
    yield
    jar_runtime.shutdown()
    await proxy.close_client()


app = FastAPI(title="DockTVBox", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(api.router)
app.include_router(pages.router)


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """统一兜底：未捕获异常返回 JSON 而不是纯文本 500，完整堆栈留在日志。"""
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请查看容器日志"})


@app.middleware("http")
async def remember_origin(request: Request, call_next):
    """让 spider 知道浏览器是用哪个地址访问我们的，本地代理链接才拼得对。"""
    SPIDER_BASE_URL.set(str(request.base_url).rstrip("/"))
    return await call_next(request)
