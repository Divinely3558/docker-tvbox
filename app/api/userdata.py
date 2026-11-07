"""用户数据接口：观看历史与收藏。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from .. import content, store

router = APIRouter()


class HistoryRequest(BaseModel):
    site: str
    vod_id: str
    name: str = ""
    pic: str = ""
    flag: str = ""
    episode: str = ""
    position: float = 0
    duration: float = 0
    device: str = "web"


@router.get("/api/history")
async def api_history() -> dict[str, Any]:
    return {"items": await store.list_history()}


@router.post("/api/history")
async def api_history_add(payload: HistoryRequest) -> dict[str, Any]:
    ctx = await content.load_sites()
    await store.add_history(
        ctx["source"]["id"],
        payload.site,
        payload.vod_id,
        payload.name,
        payload.pic,
        payload.flag,
        payload.episode,
        payload.position,
        payload.duration,
        payload.device,
    )
    return {"ok": True}


@router.delete("/api/history")
async def api_history_delete(site: str, vod_id: str) -> dict[str, Any]:
    await store.delete_history(site, vod_id)
    return {"ok": True}


class FavoriteRequest(BaseModel):
    site: str
    vod_id: str
    name: str = ""
    pic: str = ""


@router.get("/api/favorites")
async def api_favorites() -> dict[str, Any]:
    return {"items": await store.list_favorites()}


@router.post("/api/favorites")
async def api_favorites_add(payload: FavoriteRequest) -> dict[str, Any]:
    ctx = await content.load_sites()
    await store.add_favorite(
        ctx["source"]["id"], payload.site, payload.vod_id, payload.name, payload.pic
    )
    return {"ok": True}


@router.delete("/api/favorites")
async def api_favorites_delete(site: str, vod_id: str) -> dict[str, Any]:
    await store.remove_favorite(site, vod_id)
    return {"ok": True}
