"""配置源与设置接口：源列表/切换/刷新/增删、阿里云盘 token、健康检查。"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import config_loader, store
from ..config_loader import ConfigError
from ..settings import SOURCE_PASSWORD

router = APIRouter()
logger = logging.getLogger("docktvbox.sources")


def _public_source(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "url": row["url"],
        "file": row["file"],
        "enabled": bool(row["enabled"]),
        "site_count": int(row.get("site_count") or 0),
        "cached_at": row.get("cached_at"),
    }


async def _load_sources() -> list[dict[str, Any]]:
    return [_public_source(row) for row in await store.list_sources()]


async def _resolve_active(sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not sources:
        return None
    active_id = await store.get_active_source_id()
    for source in sources:
        if source["id"] == active_id:
            return source
    return sources[0]


@router.get("/api/sources")
async def api_sources() -> dict[str, Any]:
    sources = await _load_sources()
    active = await _resolve_active(sources)
    return {"sources": sources, "active": active["id"] if active else None}


@router.post("/api/sources/{source_id}/activate")
async def api_activate(source_id: int) -> dict[str, Any]:
    if not await store.get_source(source_id):
        raise HTTPException(status_code=404, detail="源不存在")
    await store.set_active_source(source_id)
    logger.info("切换到源 id=%s", source_id)
    return {"ok": True, "active": source_id}


@router.post("/api/sources/{source_id}/reload")
async def api_reload(source_id: int) -> dict[str, Any]:
    if not await store.get_source(source_id):
        raise HTTPException(status_code=404, detail="源不存在")
    try:
        payload = await config_loader.get_sites_for_source(source_id, force=True)
    except ConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "site_count": len(payload["sites"]),
        "stale": payload.get("stale", False),
    }


def _require_source_password(password: str, request: Request) -> None:
    """校验添加配置源的管理密码（Docker 环境变量 SOURCE_PASSWORD）。"""
    if not SOURCE_PASSWORD:
        raise HTTPException(
            status_code=403, detail="管理员未设置 SOURCE_PASSWORD，禁止添加配置源"
        )
    if not hmac.compare_digest(password.encode("utf-8"), SOURCE_PASSWORD.encode("utf-8")):
        logger.warning(
            "添加配置源密码错误：%s", request.client.host if request.client else "未知"
        )
        raise HTTPException(status_code=401, detail="密码错误")


class SourceAuthPayload(BaseModel):
    password: str = Field(default="", max_length=128)


@router.post("/api/sources/auth")
async def api_source_auth(payload: SourceAuthPayload, request: Request) -> dict[str, Any]:
    """添加配置源的第一步：先验证部署密码。"""
    _require_source_password(payload.password, request)
    return {"ok": True}


class AddSourcePayload(BaseModel):
    name: str = Field(default="", max_length=60)
    url: str = Field(default="", max_length=500)
    password: str = Field(default="", max_length=128)


@router.post("/api/sources")
async def api_add_source(payload: AddSourcePayload, request: Request) -> dict[str, Any]:
    """网页添加配置源：必须输入 Docker 环境变量 SOURCE_PASSWORD 设置的密码。"""
    _require_source_password(payload.password, request)
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="请填写 http(s) 开头的配置地址")
    existing = await store.list_sources()
    if any(row["url"] == url for row in existing):
        raise HTTPException(status_code=409, detail="该配置源已存在")
    name = payload.name.strip() or url
    source_id = await store.add_source(name, url)
    try:
        data = await config_loader.get_sites_for_source(source_id, force=True)
    except ConfigError as exc:
        await store.delete_source(source_id)
        raise HTTPException(status_code=502, detail=f"配置源不可用：{exc}") from exc
    site_count = len(data["sites"])
    if not site_count:
        await store.delete_source(source_id)
        raise HTTPException(status_code=502, detail="配置源里没有任何可用站点")
    logger.info("添加配置源：%s（%s 个站点）", name, site_count)
    return {"ok": True, "id": source_id, "name": name, "site_count": site_count}


class DeleteSourcePayload(BaseModel):
    password: str = Field(default="", max_length=128)


@router.post("/api/sources/{source_id}/delete")
async def api_delete_source(
    source_id: int, payload: DeleteSourcePayload, request: Request
) -> dict[str, Any]:
    """删除网页添加的配置源；config.json 里的源不允许在这里删除。"""
    _require_source_password(payload.password, request)
    row = await store.get_source(source_id)
    if not row:
        raise HTTPException(status_code=404, detail="源不存在")
    if row.get("origin") != "manual":
        raise HTTPException(status_code=403, detail="config.json 里的源不能在这里删除")
    await store.delete_source(source_id)
    if await store.get_active_source_id() == source_id:
        remaining = await store.list_sources()
        if remaining:
            await store.set_active_source(remaining[0]["id"])
    logger.info("删除配置源：%s", row["name"])
    return {"ok": True}


@router.get("/api/sites")
async def api_sites(
    source: int | None = Query(default=None, description="配置源 id，缺省为当前源"),
    refresh: bool = Query(default=False, description="强制重新拉取"),
) -> JSONResponse:
    sources = await _load_sources()
    active = await _resolve_active(sources)
    source_id = source or (active["id"] if active else None)
    if not source_id:
        raise HTTPException(status_code=404, detail="没有任何配置源")
    try:
        payload = await config_loader.get_sites_for_source(source_id, force=refresh)
    except ConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return JSONResponse({"source": source_id, **payload})


class SettingsPayload(BaseModel):
    aliyun_token: str | None = Field(default=None, max_length=4096)


@router.get("/api/settings")
async def api_settings() -> dict[str, Any]:
    return await store.aliyun_token_view()


@router.post("/api/settings")
async def api_save_settings(payload: SettingsPayload) -> dict[str, Any]:
    if payload.aliyun_token is None:
        return await store.aliyun_token_view()
    return await store.set_aliyun_token(payload.aliyun_token)


@router.get("/health")
async def health() -> dict[str, Any]:
    sources = await _load_sources()
    active = await _resolve_active(sources)
    return {
        "status": "ok",
        "sources": len(sources),
        "active": active["name"] if active else None,
    }
